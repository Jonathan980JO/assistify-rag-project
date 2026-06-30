#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scan the Assistify repo for likely-unnecessary files (report only, no deletions).

Usage:
  python scripts/scan_unnecessary_files.py
  python scripts/scan_unnecessary_files.py --json docs/unnecessary_files.json
  python scripts/scan_unnecessary_files.py --output docs/UNNECESSARY_FILES_REPORT.md
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SKIP_DIR_NAMES = {
    ".git",
    ".cursor",
    "__pycache__",
    ".pytest_cache",
    "venv",
    "env",
    "ENV",
    "node_modules",
    "models",
    "backend/Models",
    "chroma_db",
    "chroma_db_v3",
    "chroma_db_reindex",
    "logs",
    "graduation",
}

SKIP_DIR_PARTS = {"Models", "models"}

ENTRY_POINTS = [
    "start_main_servers.py",
    "scripts/project_start_server.py",
    "scripts/project_start_split.py",
    "backend/assistify_rag_server.py",
    "backend/main_llm_server.py",
    "Login_system/login_server.py",
    "tts_service/piper_server.py",
    "config.py",
    "run_all.py",
]

KEEP_EXACT = {
    "start_main_servers.py",
    "config.py",
    "run_all.py",
    "environment_main.yml",
    "environment_main_locked.yml",
    "environment_xtts.yml",
    "environment_xtts_locked.yml",
    ".env.example",
    ".gitignore",
    "README.md",
}

KEEP_PREFIXES = (
    "backend/assistify_rag_server.py",
    "backend/main_llm_server.py",
    "backend/knowledge_base.py",
    "backend/database.py",
    "backend/pdf_ingestion_rag.py",
    "backend/analytics.py",
    "Login_system/login_server.py",
    "Login_system/init_users_db.py",
    "Login_system/memberships.py",
    "scripts/project_start_server.py",
    "scripts/project_start_split.py",
    "scripts/service_inventory.py",
    "scripts/preflight_check.py",
    "scripts/migrate_to_multitenant.py",
    "scripts/launch_windows/write_launch_scripts.py",
    "tts_service/",
    "tests/test_",
)

DUPLICATE_EXCLUDE_NAMES = {
    "__init__.py",
    "admin.html",
    "admin_analytics.html",
    "admin_knowledge.html",
    "admin_users.html",
    "verify_otp.html",
    "verify_email_change.html",
    "verify_password_change.html",
}

ROOT_DEBUG_ALLOWLIST = {
    "start_main_servers.py",
    "config.py",
    "run_all.py",
}

STALE_PATH_PATTERNS = [
    re.compile(r"G:\\Grad_Project", re.I),
    re.compile(r"G:/Grad_Project", re.I),
    re.compile(r"D:\\Grad_Project", re.I),
    re.compile(r"D:/Grad_Project", re.I),
]

GITIGNORE_PATTERNS = [
    "*.pre_mt_backup",
    "temp_launchers/",
    "temp_phase*.py",
    "._*",
    "rag_verification_report.json",
    "docs/UNNECESSARY_FILES_REPORT.md",
    "docs/unnecessary_files.json",
]

IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
    re.MULTILINE,
)


@dataclass
class FileFinding:
    rel_path: str
    tier: str
    reasons: list[str] = field(default_factory=list)
    size_bytes: int = 0
    stale_path: bool = False
    duplicate_of: list[str] = field(default_factory=list)
    unreferenced: bool = False

    @property
    def primary_reason(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "-"


def _norm_rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _should_skip_dir(path: Path) -> bool:
    parts = path.parts
    if path.name in SKIP_DIR_NAMES:
        return True
    if path.name in SKIP_DIR_PARTS and "backend" in parts:
        return True
    rel = _norm_rel(path) if path.is_relative_to(REPO_ROOT) else str(path)
    for skip in SKIP_DIR_NAMES:
        if skip in rel.split("/"):
            return True
    return False


def iter_repo_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(_should_skip_dir(parent) for parent in path.parents if parent != REPO_ROOT):
            continue
        if _should_skip_dir(path.parent):
            continue
        files.append(path)
    return sorted(files, key=lambda p: _norm_rel(p))


def _is_keep(rel: str) -> bool:
    if rel in KEEP_EXACT:
        return True
    for prefix in KEEP_PREFIXES:
        if rel.startswith(prefix) or rel == prefix.rstrip("/"):
            return True
    if rel.startswith("tests/test_") and rel.endswith(".py"):
        return True
    if rel.startswith("assistify-ui-design/"):
        return True
    if rel.startswith("docs/") and "UNNECESSARY" not in rel and "unnecessary_files" not in rel:
        return True
    return False


def _read_text_snippet(path: Path, limit: int = 65536) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _has_stale_path(content: str) -> bool:
    return any(p.search(content) for p in STALE_PATH_PATTERNS)


def _matches_gitignore_pattern(rel: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        return rel.startswith(pattern.rstrip("/") + "/") or rel == pattern.rstrip("/")
    if "/" not in pattern and "*" in pattern:
        return fnmatch.fnmatch(Path(rel).name, pattern)
    return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(Path(rel).name, pattern)


def _rule_pre_mt_backup(rel: str) -> bool:
    return rel.endswith(".pre_mt_backup")


def _rule_temp_scratch(rel: str) -> bool:
    name = Path(rel).name
    if rel.startswith("temp_launchers/"):
        return True
    if rel.startswith("non_functional/"):
        return True
    if name.startswith("temp_") or name.startswith("tmp_"):
        return True
    return False


def _rule_patch_leftover(rel: str) -> bool:
    if not rel.startswith("backend/") and not rel.startswith("tools/testing/"):
        return False
    name = Path(rel).name
    if name.startswith("patch") and name.endswith(".py"):
        return True
    if name.startswith("fix_indent") and name.endswith(".py"):
        return True
    if name.startswith("reindex_") and name.endswith(".py"):
        return True
    if name in ("fix_remaining_patches.py", "patch_phase2_fixes.py"):
        return True
    return False


def _rule_eval_output(rel: str) -> bool:
    name = Path(rel).name.lower()
    if name == "conversations.json":
        return True
    if name.endswith(".json") and "report" in name:
        return True
    return False


def _rule_os_junk(rel: str) -> bool:
    name = Path(rel).name
    if name.startswith("._"):
        return True
    if name == "4.0":
        return True
    return False


def _rule_root_debug(rel: str) -> bool:
    if "/" in rel:
        return False
    if not rel.endswith(".py"):
        return False
    if rel in ROOT_DEBUG_ALLOWLIST:
        return False
    return True


def _rule_audit_markdown(rel: str) -> bool:
    if not rel.endswith(".md"):
        return False
    if rel.startswith("docs/"):
        audit_names = ("EVIDENCE", "PHASE_", "PATCH", "METADATA_FIX", "RAW_EVIDENCE", "BUGFIX")
        return any(x in Path(rel).name.upper() for x in audit_names)
    root_audit = {
        "EVIDENCE_REPORT.md",
        "RAW_EVIDENCE_FINAL.md",
        "PHASE_AR0_ANALYSIS_REPORT.md",
        "PHASE_AR1B_FINAL_REPORT.md",
        "PATCHES_APPLIED.md",
        "UPSTREAM_PATCH_BUNDLES.md",
        "BUGFIX_LIST_QUERIES_SUMMARY.md",
        "AGENT_TASK_PROMPT.md",
    }
    return rel in root_audit


def _rule_root_stubs(rel: str) -> bool:
    if rel in {"playwright.py", "pyotp.py", "reportlab.py", "pyttsx3.py"}:
        return True
    if rel in {"TTS", "TTS/"} or rel.startswith("TTS/"):
        return True
    return False


def _rule_legacy_xtts(rel: str) -> bool:
    return (
        rel.startswith("tools/testing/_legacy_xtts/")
        or rel == "start_xtts_service.bat.disabled"
        or rel.startswith("non_functional/old_python/")
    )


def _rule_iterative_dumps(rel: str) -> bool:
    name = Path(rel).name
    iterative = {
        "dump_chunks.py",
        "dump_chunks_sql.py",
        "dump_chunks_sql_v2.py",
        "extract_chunks.py",
        "extract_chunks_full.py",
        "extract_chunk_texts.py",
        "upload_principles.py",
    }
    return name in iterative


def _assign_tier(reasons: list[str], rel: str) -> str:
    if _is_keep(rel):
        return "E"

    tier_a = {
        "pre_mt_backup",
        "temp_scratch",
        "os_junk",
        "eval_output",
        "patch_leftover",
        "non_functional",
    }
    tier_b = {"duplicate_basename", "iterative_dump", "legacy_xtts", "root_duplicate"}
    tier_c = {"stale_path"}
    tier_d = {"audit_markdown", "root_stubs", "root_debug_clutter", "unreferenced", "gitignore_mismatch", "misnamed_test"}

    reason_set = set(reasons)
    if reason_set & tier_a:
        return "A"
    if reason_set & tier_b:
        return "B"
    if reason_set & tier_c:
        return "C"
    if reason_set & tier_d:
        return "D"
    if reasons:
        return "D"
    return "E"


def build_duplicate_map(files: list[Path]) -> dict[str, list[str]]:
    by_name: dict[str, list[str]] = defaultdict(list)
    for path in files:
        rel = _norm_rel(path)
        name = path.name
        if name in DUPLICATE_EXCLUDE_NAMES:
            continue
        by_name[name].append(rel)
    return {name: paths for name, paths in by_name.items() if len(paths) > 1}


def build_import_graph(py_files: list[Path]) -> tuple[dict[str, set[str]], set[str]]:
    """Map module-ish names to files that import them; return unreferenced root .py files."""
    module_to_importers: dict[str, set[str]] = defaultdict(set)
    file_imports: dict[str, set[str]] = {}

    for path in py_files:
        rel = _norm_rel(path)
        content = _read_text_snippet(path)
        imports: set[str] = set()
        for m in IMPORT_RE.finditer(content):
            mod = m.group(1) or m.group(2)
            if mod:
                top = mod.split(".")[0]
                imports.add(top)
                module_to_importers[top].add(rel)
        file_imports[rel] = imports

    entry_modules = set()
    for ep in ENTRY_POINTS:
        p = Path(ep)
        if p.suffix == ".py":
            entry_modules.add(p.stem)
            if "/" in ep or "\\" in ep:
                parts = ep.replace("\\", "/").split("/")
                if len(parts) >= 2:
                    entry_modules.add(parts[-1].replace(".py", ""))

    reachable: set[str] = set()
    queue = list(ENTRY_POINTS)
    while queue:
        rel = queue.pop(0)
        if rel in reachable:
            continue
        reachable.add(rel)
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        content = _read_text_snippet(path)
        for m in IMPORT_RE.finditer(content):
            mod = m.group(1) or m.group(2)
            if not mod:
                continue
            for candidate in py_files:
                crel = _norm_rel(candidate)
                stem = candidate.stem
                if mod == stem or mod.endswith("." + stem):
                    if crel not in reachable:
                        queue.append(crel)

    unreferenced_root: set[str] = set()
    for path in py_files:
        rel = _norm_rel(path)
        if "/" in rel:
            continue
        if rel in ROOT_DEBUG_ALLOWLIST or rel in KEEP_EXACT:
            continue
        if rel not in reachable:
            importers = module_to_importers.get(Path(rel).stem, set())
            if not importers:
                unreferenced_root.add(rel)

    return dict(module_to_importers), unreferenced_root


def scan_files() -> list[FileFinding]:
    files = iter_repo_files()
    dup_map = build_duplicate_map(files)
    py_files = [p for p in files if p.suffix == ".py"]
    _, unreferenced_root = build_import_graph(py_files)

    findings: list[FileFinding] = []

    for path in files:
        rel = _norm_rel(path)
        try:
            size = path.stat().st_size
        except OSError:
            size = 0

        reasons: list[str] = []
        stale = False
        duplicate_of: list[str] = []

        if _is_keep(rel):
            continue

        if _rule_pre_mt_backup(rel):
            reasons.append("pre_mt_backup")
        if _rule_temp_scratch(rel):
            reasons.append("temp_scratch")
            if rel.startswith("non_functional/"):
                reasons.append("non_functional")
        if _rule_patch_leftover(rel):
            reasons.append("patch_leftover")
        if _rule_eval_output(rel):
            reasons.append("eval_output")
        if _rule_os_junk(rel):
            reasons.append("os_junk")
        if _rule_root_debug(rel):
            reasons.append("root_debug_clutter")
        if _rule_audit_markdown(rel):
            reasons.append("audit_markdown")
        if _rule_root_stubs(rel):
            reasons.append("root_stubs")
        if _rule_legacy_xtts(rel):
            reasons.append("legacy_xtts")
        if _rule_iterative_dumps(rel):
            reasons.append("iterative_dump")

        name = path.name
        if name in dup_map:
            others = [p for p in dup_map[name] if p != rel]
            if others:
                reasons.append("duplicate_basename")
                duplicate_of = others
                if rel.count("/") == 0 and any(o.startswith("tools/testing/") for o in others):
                    reasons.append("root_duplicate")

        if rel == "backend/test":
            reasons.append("misnamed_test")

        text_ext = {".py", ".bat", ".ps1", ".md", ".json", ".txt", ".sh"}
        if path.suffix.lower() in text_ext or path.suffix == "":
            content = _read_text_snippet(path)
            if _has_stale_path(content):
                stale = True
                reasons.append("stale_path")

        if rel in unreferenced_root:
            reasons.append("unreferenced")

        for pattern in GITIGNORE_PATTERNS:
            if _matches_gitignore_pattern(rel, pattern):
                reasons.append("gitignore_mismatch")
                break

        tier = _assign_tier(reasons, rel)
        if not reasons and tier == "E":
            continue

        if reasons or tier != "E":
            findings.append(
                FileFinding(
                    rel_path=rel,
                    tier=tier,
                    reasons=sorted(set(reasons)),
                    size_bytes=size,
                    stale_path=stale,
                    duplicate_of=duplicate_of,
                    unreferenced=rel in unreferenced_root,
                )
            )

    findings.sort(key=lambda f: (f.tier, f.rel_path))
    return findings


def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def write_markdown(findings: list[FileFinding], output: Path) -> None:
    by_tier: dict[str, list[FileFinding]] = defaultdict(list)
    for f in findings:
        by_tier[f.tier].append(f)

    tier_labels = {
        "A": "Tier A — High confidence unnecessary",
        "B": "Tier B — Likely redundant (keep one canonical copy)",
        "C": "Tier C — Stale path bindings",
        "D": "Tier D — Review before touching",
        "E": "Tier E — Flagged but kept / informational",
    }

    lines = [
        "# Unnecessary Files Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Repo: `{REPO_ROOT}`",
        "",
        "**Report only — no files were deleted.**",
        "",
        "## Summary",
        "",
        "| Tier | Label | Count |",
        "|------|-------|-------|",
    ]

    for tier in ("A", "B", "C", "D", "E"):
        count = len(by_tier.get(tier, []))
        lines.append(f"| {tier} | {tier_labels[tier]} | {count} |")

    lines.extend(["", f"| **Total flagged** | | **{len(findings)}** |", ""])

    lines.extend(
        [
            "## Recommended next actions",
            "",
            "- **Tier A:** Safe to delete after manual spot-check (backups, temp scripts, OS junk).",
            "- **Tier B:** Consolidate duplicates; keep canonical copy under `scripts/` or `tools/testing/`.",
            "- **Tier C:** Fix paths to repo-relative or delete if obsolete debug scripts.",
            "- **Tier D:** Archive audit markdown to `docs/archive/`; verify stub modules before removal.",
            "",
        ]
    )

    for tier in ("A", "B", "C", "D"):
        items = by_tier.get(tier, [])
        if not items:
            continue
        lines.append(f"## {tier_labels[tier]}")
        lines.append("")
        lines.append("| Path | Reason | Size | Stale path | Duplicates |")
        lines.append("|------|--------|------|------------|------------|")
        for f in items:
            dup = ", ".join(f"`{d}`" for d in f.duplicate_of[:3])
            if len(f.duplicate_of) > 3:
                dup += f" (+{len(f.duplicate_of) - 3} more)"
            stale = "yes" if f.stale_path else "-"
            lines.append(
                f"| `{f.rel_path}` | {f.primary_reason} | {format_size(f.size_bytes)} | {stale} | {dup or '-'} |"
            )
        lines.append("")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(findings: list[FileFinding], output: Path) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "total_flagged": len(findings),
        "by_tier": {
            tier: len([f for f in findings if f.tier == tier]) for tier in ("A", "B", "C", "D", "E")
        },
        "findings": [
            {
                "path": f.rel_path,
                "tier": f.tier,
                "reasons": f.reasons,
                "size_bytes": f.size_bytes,
                "stale_path": f.stale_path,
                "duplicate_of": f.duplicate_of,
                "unreferenced": f.unreferenced,
            }
            for f in findings
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def print_console_summary(findings: list[FileFinding]) -> None:
    by_tier = defaultdict(int)
    for f in findings:
        by_tier[f.tier] += 1

    print("=" * 60)
    print("  Assistify Unnecessary Files Scan")
    print("=" * 60)
    print(f"  Repo   : {REPO_ROOT}")
    print(f"  Flagged: {len(findings)} files")
    for tier in ("A", "B", "C", "D"):
        print(f"  Tier {tier}  : {by_tier.get(tier, 0)}")
    print()
    core_hits = [f for f in findings if f.tier == "A" and _is_keep(f.rel_path)]
    if core_hits:
        print("  WARNING: core runtime files in Tier A:")
        for f in core_hits:
            print(f"    - {f.rel_path}")
    else:
        print("  OK: no core runtime files in Tier A")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan repo for likely-unnecessary files")
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "docs" / "UNNECESSARY_FILES_REPORT.md"),
        help="Markdown report path",
    )
    parser.add_argument(
        "--json",
        default="",
        help="Optional JSON output path (e.g. docs/unnecessary_files.json)",
    )
    args = parser.parse_args()

    findings = scan_files()
    output = Path(args.output)
    write_markdown(findings, output)
    print(f"[SCAN] Wrote {output.relative_to(REPO_ROOT)}")

    if args.json:
        json_path = Path(args.json)
        if not json_path.is_absolute():
            json_path = REPO_ROOT / json_path
        write_json(findings, json_path)
        print(f"[SCAN] Wrote {json_path.relative_to(REPO_ROOT)}")

    print_console_summary(findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
