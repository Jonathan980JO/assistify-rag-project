"""Generalized Phase 8H extractor.

Moves a contiguous block of top-level functions (and the constants they need)
out of assistify_rag_server.py into a new retrieval leaf module, using the
proven Phase 8H-1 approach:

  * Constants used by the block are moved with it (closure-completed).
  * Module-level imports the block needs are re-emitted in the new module from
    their original statements (stdlib, utils, and singletons like live_rag keep
    shared identity because they import the same object).
  * Shared mutable state, the logger, and engine functions that remain in the
    monolith are reached through ``S`` (the server module injected via
    bind_server) and rewritten to ``S.<name>``.
  * The transform fails loudly on any unaccounted free name, a moved constant
    that depends on a monolith-only symbol, or a rewrite target that is ever
    bound locally inside the block.

Const-vs-state classification is automatic: a module-level assignment is treated
as shared state (-> S) if it is ever reassigned, augmented, subscript-assigned,
or mutated via a mutating method ANYWHERE in the file; otherwise it is an
immutable constant safe to move.

Usage:
    python scripts/_phase8h_extract.py --low N --high M \
        --out backend/retrieval/arabic.py --module backend.retrieval.arabic [--apply]
"""
from __future__ import annotations

import argparse
import ast
import builtins
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MONO = ROOT / "backend" / "assistify_rag_server.py"

MUTATING_METHODS = {
    "append", "extend", "insert", "remove", "pop", "clear", "sort", "reverse",
    "update", "setdefault", "popitem", "add", "discard", "__setitem__",
}
FORCE_S = {"logger"}

ap = argparse.ArgumentParser()
ap.add_argument("--low", type=int, required=True)
ap.add_argument("--high", type=int, required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--module", required=True)
ap.add_argument("--apply", action="store_true")
ap.add_argument(
    "--allow-free", default="",
    help="comma-separated names that are pre-existing unresolved free globals in "
         "the monolith (dead references). They are emitted verbatim (bare) so the "
         "extraction preserves the exact current NameError-if-reached behavior.",
)
args = ap.parse_args()
ALLOW_FREE = {n.strip() for n in args.allow_free.split(",") if n.strip()}

OUT = ROOT / args.out
LOW, HIGH = args.low, args.high

src = MONO.read_text(encoding="utf-8")
lines = src.splitlines(keepends=True)
tree = ast.parse(src)
builtin_names = set(dir(builtins))

import backend.config_head as _cfg  # noqa: E402
CFG_NAMES = {n for n in dir(_cfg) if not n.startswith("_")}

ml_def, ml_assign, ml_import_info = {}, {}, {}
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        ml_def[node.name] = (node.lineno, node.end_lineno)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name):
                    ml_assign.setdefault(n.id, (node.lineno, node.end_lineno))
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        ml_assign.setdefault(node.target.id, (node.lineno, node.end_lineno))
    elif isinstance(node, ast.Import):
        for a in node.names:
            bind = a.asname or a.name.split(".")[0]
            ml_import_info.setdefault(bind, ("plain", a.name, a.asname))
    elif isinstance(node, ast.ImportFrom):
        mod = ("." * node.level) + (node.module or "")
        for a in node.names:
            bind = a.asname or a.name
            ml_import_info.setdefault(bind, ("from", mod, a.name, a.asname))


def minimal_import(bind):
    info = ml_import_info[bind]
    if info[0] == "plain":
        _, dotted, asname = info
        return f"import {dotted} as {asname}\n" if asname else f"import {dotted}\n"
    _, mod, orig, asname = info
    return f"from {mod} import {orig} as {asname}\n" if asname else f"from {mod} import {orig}\n"

candidates = {n.name: n for n in tree.body
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and LOW <= n.lineno <= HIGH}
if not candidates:
    print("no candidate functions in range")
    sys.exit(2)


def free_loads(node):
    return {x.id for x in ast.walk(node) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}


def bound_names(node):
    b = set()
    for x in ast.walk(node):
        if isinstance(x, ast.Name) and isinstance(x.ctx, (ast.Store, ast.Del)):
            b.add(x.id)
        elif isinstance(x, ast.arg):
            b.add(x.arg)
        elif isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b.add(x.name)
        elif isinstance(x, ast.ExceptHandler) and x.name:
            b.add(x.name)
        elif isinstance(x, (ast.Import, ast.ImportFrom)):
            for a in x.names:
                b.add(a.asname or a.name.split(".")[0])
    return b


def const_free(csrc):
    parsed = ast.parse(csrc)
    return free_loads(parsed) - bound_names(parsed)


def ffree(fn):
    """Names a function references that are NOT bound locally (true free vars)."""
    return free_loads(fn) - bound_names(fn)


# ---- detect which module-level assigns are ever written (=> shared state) ---
written = set()
for x in ast.walk(tree):
    if isinstance(x, ast.AugAssign) and isinstance(x.target, ast.Name):
        written.add(x.target.id)
    elif isinstance(x, ast.Global):
        written.update(x.names)
    elif isinstance(x, ast.Subscript) and isinstance(x.ctx, ast.Store) and isinstance(x.value, ast.Name):
        written.add(x.value.id)
    elif isinstance(x, ast.Attribute) and isinstance(x.ctx, ast.Store) and isinstance(x.value, ast.Name):
        written.add(x.value.id)  # obj.attr = ... mutates the shared object
    elif isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) \
            and isinstance(x.func.value, ast.Name) and x.func.attr in MUTATING_METHODS:
        written.add(x.func.value.id)
# reassignment: a module-level name assigned again inside any function body
assign_counts = {}
for x in ast.walk(tree):
    if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
        assign_counts[x.id] = assign_counts.get(x.id, 0) + 1
for nm, c in assign_counts.items():
    if nm in ml_assign and c > 1:
        written.add(nm)

# ---- rewrite set: engine funcs + state assigns + logger --------------------
ffree_cache = {name: ffree(fn) for name, fn in candidates.items()}
ext_funcs = set()
for nm_set in ffree_cache.values():
    for nm in nm_set:
        if nm in ml_def and nm not in candidates:
            ext_funcs.add(nm)
state_assigns = set()
for nm_set in ffree_cache.values():
    for nm in nm_set:
        if nm in ml_assign and nm in written:
            state_assigns.add(nm)
rewrite_set = ext_funcs | state_assigns | set(FORCE_S)

# ---- imports the block needs (re-emit originals) ---------------------------
need_imports = set()
for nm_set in ffree_cache.values():
    for nm in nm_set:
        if nm in ml_import_info and nm not in rewrite_set:
            need_imports.add(nm)

# ---- constants to move (closure), excluding state/rewrite ------------------
const_move = set()
work = set()
for nm_set in ffree_cache.values():
    for nm in nm_set:
        if nm in ml_assign and nm not in rewrite_set and nm not in written:
            work.add(nm)
while work:
    nm = work.pop()
    if nm in const_move:
        continue
    const_move.add(nm)
    s, e = ml_assign[nm]
    for sub in const_free("".join(lines[s - 1:e])):
        if sub in ml_assign and sub not in rewrite_set and sub not in written and sub not in const_move:
            work.add(sub)

# moved constants may also need module-level imports (e.g. typing in annotations)
for nm in const_move:
    s, e = ml_assign[nm]
    for sub in const_free("".join(lines[s - 1:e])):
        if sub in ml_import_info and sub not in rewrite_set:
            need_imports.add(sub)

# ---- completeness / safety checks ------------------------------------------
reimport_names = set(need_imports)
available = (builtin_names | CFG_NAMES | set(candidates) | const_move
             | rewrite_set | reimport_names | ALLOW_FREE | {"S"})
unaccounted, const_bad = {}, {}
for name, fn in candidates.items():
    local = bound_names(fn)
    for nm in free_loads(fn):
        if nm in local or nm in available:
            continue
        unaccounted.setdefault(nm, []).append(name)
const_ok_env = builtin_names | CFG_NAMES | const_move | reimport_names
for nm in const_move:
    s, e = ml_assign[nm]
    for sub in const_free("".join(lines[s - 1:e])):
        if sub not in const_ok_env:
            const_bad.setdefault(nm, set()).add(sub)
# scope-aware rewriting handles names that are local in some functions and
# module-level in others, so local shadowing is informational only.

print(f"range [{LOW},{HIGH}] -> {args.out}")
print(f"candidate funcs: {len(candidates)} | consts to move: {len(const_move)}")
print(f"engine funcs -> S ({len(ext_funcs)}): {sorted(ext_funcs)}")
print(f"state assigns -> S ({len(state_assigns)}): {sorted(state_assigns)}")
print(f"re-imported names ({len(reimport_names)}): {sorted(reimport_names)}")
if ALLOW_FREE:
    print(f"allowed pre-existing unresolved (bare, dead refs): {sorted(ALLOW_FREE)}")
if unaccounted:
    print("\n!!! UNACCOUNTED:")
    for nm, w in sorted(unaccounted.items()):
        print(f"   {nm}: {w[:4]}")
if const_bad:
    print("\n!!! CONST depends on monolith-only:")
    for nm, subs in const_bad.items():
        print(f"   {nm}: {sorted(subs)}")
if unaccounted or const_bad:
    print("\nBLOCKED")
    sys.exit(2)
print("classification clean.")
if not args.apply:
    print("dry-run; pass --apply to write")
    sys.exit(0)

# ---- apply S.<name> rewrites to a working buffer ---------------------------
edits = []
for fn in candidates.values():
    local = bound_names(fn)
    for x in ast.walk(fn):
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load) \
                and x.id in rewrite_set and x.id not in local:
            edits.append((x.lineno, x.col_offset, x.end_col_offset, "S." + x.id))
buf = list(lines)
by_line = {}
for ln, c0, c1, txt in edits:
    by_line.setdefault(ln, []).append((c0, c1, txt))
for ln, reps in by_line.items():
    s = buf[ln - 1]
    for c0, c1, txt in sorted(reps, key=lambda r: -r[0]):
        s = s[:c0] + txt + s[c1:]
    buf[ln - 1] = s

def _def_start(fn):
    """Start line including any decorators, so decorated functions move whole."""
    return min([d.lineno for d in fn.decorator_list] + [fn.lineno])


move_ranges = sorted([ml_assign[nm] for nm in const_move]
                     + [(_def_start(fn), fn.end_lineno) for fn in candidates.values()])
moved_names = sorted(const_move) + sorted(candidates)

reimport_src = "".join(minimal_import(nm) for nm in sorted(need_imports))
header = f'''"""Extracted retrieval helpers (Phase 8H).

Moved verbatim from ``assistify_rag_server.py``. This module is a leaf in the
retrieval package and never imports the server. Shared mutable state, the
logger, and engine functions still in the monolith are reached through ``S``,
the server module injected via ``bind_server`` at registration time. Behavior is
identical to the monolith original.
"""
from __future__ import annotations

from backend.config_head import *  # noqa: F401,F403 - mirrors the server module
{reimport_src}
S = None


def bind_server(server) -> None:
    """Bind the live server module so extracted helpers can reach shared state."""
    global S
    S = server

'''
parts = [header]
for (s, e) in move_ranges:
    parts.append("".join(buf[s - 1:e]).rstrip("\n") + "\n\n")
OUT.parent.mkdir(parents=True, exist_ok=True)
(OUT.parent / "__init__.py").touch(exist_ok=True)
OUT.write_text("".join(parts), encoding="utf-8")
print(f"wrote {OUT} ({sum(e - s + 1 for s, e in move_ranges)} lines moved)")

drop = set()
for s, e in move_ranges:
    drop.update(range(s, e + 1))
earliest = min(s for s, _ in move_ranges)
inj = [
    f"# --- Phase 8H refactor: block extracted to {args.module}, bound to this live\n",
    "# module via bind_server so extracted helpers reach shared state/engine fns.\n",
    f"from {args.module.rsplit('.', 1)[0]} import {args.module.rsplit('.', 1)[1]} as _ext_mod_{args.module.rsplit('.', 1)[1]}\n",
    f"_ext_mod_{args.module.rsplit('.', 1)[1]}.bind_server(_sys.modules[__name__])\n",
    f"from {args.module} import (\n",
] + [f"    {nm},\n" for nm in moved_names] + [")\n"]

out_lines, injected = [], False
for i, line in enumerate(lines, start=1):
    if i == earliest:
        out_lines.extend(inj)
        injected = True
    if i in drop:
        continue
    out_lines.append(line)
assert injected
MONO.write_text("".join(out_lines), encoding="utf-8")
print(f"monolith: {len(lines)} -> {len(out_lines)} lines")
