"""Phase 8 decomposition validation gate.

Runs the four required checks after every extraction phase and exits non-zero
on the first failure so the pipeline can stop immediately:

  1. py_compile   - the monolith plus any modules passed on the CLI
  2. import       - core backend modules import without error
  3. route parity - the live RAG app exposes the same routes as the
                    pre-refactor audit snapshot (no missing routes)
  4. startup      - ``backend.assistify_rag_server.app`` builds successfully

Usage:
    python scripts/validate_phase8.py [extra_module_to_compile ...]

Extra arguments are file paths compiled in step 1 (e.g. newly extracted
modules for the current phase).
"""
from __future__ import annotations

import ast
import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Matches FastAPI route decorators in source text (same logic as
# scripts/compare_routes.py). Text-based parity is robust because the audit
# snapshot is a frozen .py file that is not importable as a package.
_ROUTE_RE = re.compile(
    r"@(?:app|router)\.(get|post|put|patch|delete|websocket)\(\s*['\"]([^'\"]+)['\"]"
)

# Modules that must always import cleanly (mirrors full_regression_test Phase 1).
CORE_IMPORTS = [
    "backend.database",
    "backend.knowledge_base",
    "backend.assistify_rag_server",
]


def _fail(step: str, detail: str) -> None:
    print(f"[{step}] FAIL: {detail}")
    sys.exit(1)


def step_pycompile(extra: list[str]) -> None:
    targets = [ROOT / "backend" / "assistify_rag_server.py"]
    for item in extra:
        targets.append(Path(item) if Path(item).is_absolute() else ROOT / item)
    for target in targets:
        if not target.exists():
            _fail("py_compile", f"missing file {target}")
        try:
            py_compile.compile(str(target), doraise=True)
        except py_compile.PyCompileError as exc:
            _fail("py_compile", str(exc))
    print(f"[py_compile] PASS ({len(targets)} files)")


def step_imports() -> None:
    for mod in CORE_IMPORTS:
        if mod in sys.modules:
            del sys.modules[mod]
        try:
            __import__(mod)
        except Exception as exc:  # noqa: BLE001 - report any import failure
            _fail("import", f"{mod}: {exc!r}")
    print(f"[import] PASS ({len(CORE_IMPORTS)} modules)")


def _routes_from_text(*paths: Path) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in _ROUTE_RE.finditer(text):
            routes.add((m.group(1).upper(), m.group(2)))
    return routes


def step_route_parity() -> None:
    current = _routes_from_text(
        ROOT / "backend" / "assistify_rag_server.py",
        *list((ROOT / "backend" / "routers").glob("*.py")),
    )
    audit = _routes_from_text(
        ROOT / "assistify_refactor_audit" / "assistify_rag_server.py"
    )
    if not audit:
        _fail("route_parity", "audit snapshot has no routes (file missing?)")
    missing = audit - current
    extra = current - audit
    if missing:
        _fail("route_parity", f"missing {len(missing)} routes vs audit: "
              f"{sorted(missing)[:20]}")
    if extra:
        print(f"[route_parity] WARN: {len(extra)} extra routes vs audit: "
              f"{sorted(extra)[:20]}")
    print(f"[route_parity] PASS (current={len(current)} audit={len(audit)} missing=0)")


_SERVER_ATTR_RE = re.compile(r"\bserver\.([A-Za-z_][A-Za-z0-9_]*)")


def step_router_attrs() -> None:
    """Every ``server.<attr>`` referenced by a router must exist on the live
    server module. Handler bodies are not executed by this gate, so this static
    check is the safety net for the factory-router extractions."""
    server = __import__("backend.assistify_rag_server", fromlist=["app"])
    router_dir = ROOT / "backend" / "routers"
    missing: list[str] = []
    checked = 0
    for path in router_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in sorted(set(_SERVER_ATTR_RE.findall(text))):
            # dunder/module attributes are always present
            if name.startswith("__"):
                continue
            checked += 1
            if not hasattr(server, name):
                missing.append(f"{path.name}: server.{name}")
    if missing:
        _fail("router_attrs", f"{len(missing)} unresolved server attrs: {missing}")
    print(f"[router_attrs] PASS ({checked} server.* refs resolve)")


# Pre-existing dead references inherited from before the voice_audio extraction:
# call_llm_streaming's inline XTTS-synthesis block uses these underscore names,
# but the real objects were renamed (no underscore) and moved to
# backend/voice_audio/tts/client.py. They resolve to nothing in the monolith
# today (that block is dead, superseded by tts_progressive_response), so the
# refactor preserves them verbatim rather than silently activating dead code.
KNOWN_UNRESOLVED = {
    "_XTTS_SYNTH_SEM", "_tts_cache_get", "_tts_cache_key", "_tts_cache_put",
    "_wav_bytes_to_pcm16",
}


def _free_globals(func, builtins_set):
    """Global names a function references (loads not bound locally, excluding
    attribute access targets)."""
    bound = set()
    for x in ast.walk(func):
        if isinstance(x, ast.Name) and isinstance(x.ctx, (ast.Store, ast.Del)):
            bound.add(x.id)
        elif isinstance(x, ast.arg):
            bound.add(x.arg)
        elif isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(x.name)
        elif isinstance(x, ast.ExceptHandler) and x.name:
            bound.add(x.name)
        elif isinstance(x, (ast.Import, ast.ImportFrom)):
            for a in x.names:
                bound.add(a.asname or a.name.split(".")[0])
    loads = {x.id for x in ast.walk(func) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}
    return {n for n in (loads - bound) if n not in builtins_set}


def _injected_module_paths() -> list[tuple[str, Path]]:
    """All server-injection modules to free-global check: every file under
    backend/retrieval plus any backend/services module using the bind_server/S
    pattern. Returns (dotted_module_name, path) pairs."""
    out: list[tuple[str, Path]] = []
    retr = ROOT / "backend" / "retrieval"
    if retr.exists():
        for path in sorted(retr.glob("*.py")):
            if path.name != "__init__.py":
                out.append((f"backend.retrieval.{path.stem}", path))
    for pkg in ("services", "core"):
        pkg_dir = ROOT / "backend" / pkg
        if not pkg_dir.exists():
            continue
        for path in sorted(pkg_dir.glob("*.py")):
            if path.name == "__init__.py":
                continue
            if "def bind_server" in path.read_text(encoding="utf-8", errors="ignore"):
                out.append((f"backend.{pkg}.{path.stem}", path))
    return out


def step_retrieval_globals() -> None:
    """Every free global referenced by a function in a server-injection module
    must resolve in that module's namespace. Catches missing imports that the
    import and startup steps miss because function bodies are not executed."""
    import builtins as _b
    builtins_set = set(dir(_b))
    modules = _injected_module_paths()
    if not modules:
        print("[retrieval_globals] SKIP (no injection modules)")
        return
    missing, checked = [], 0
    for mod_name, path in modules:
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        mod = __import__(mod_name, fromlist=["*"])
        ns = set(vars(mod))
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        # Only top-level functions and class methods: nested closures correctly
        # see enclosing locals as bound, so checking the outer scope suffices.
        funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            funcs += [m for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for node in funcs:
            for nm in _free_globals(node, builtins_set):
                checked += 1
                if nm not in ns and nm not in KNOWN_UNRESOLVED:
                    missing.append(f"{path.name}: {node.name} -> {nm}")
    if missing:
        _fail("retrieval_globals", f"{len(missing)} unresolved globals: {missing[:30]}")
    print(f"[retrieval_globals] PASS ({checked} global refs resolve, {len(modules)} modules)")


def step_startup() -> None:
    mod = __import__("backend.assistify_rag_server", fromlist=["app"])
    app = mod.app
    if not getattr(app, "routes", None):
        _fail("startup", "app has no routes")
    print(f"[startup] PASS (app={type(app).__name__} routes={len(app.routes)})")


def main() -> None:
    extra = sys.argv[1:]
    step_pycompile(extra)
    step_route_parity()
    step_imports()
    step_router_attrs()
    step_retrieval_globals()
    step_startup()
    print("ALL VALIDATION CHECKS PASSED")


if __name__ == "__main__":
    main()
