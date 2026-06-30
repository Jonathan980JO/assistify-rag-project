#!/usr/bin/env python3
"""
Archive Tier A and Tier B clutter from docs/unnecessary_files.json into _archived_cleanup/.

Usage:
  python cleanup_repo.py              # dry-run (default)
  python cleanup_repo.py --execute    # move files + write manifest + patch .gitignore
  python cleanup_repo.py --gitignore-only
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
JSON_PATH = REPO_ROOT / "docs" / "unnecessary_files.json"
SCAN_SCRIPT = REPO_ROOT / "scripts" / "scan_unnecessary_files.py"
ARCHIVE_DIR = REPO_ROOT / "_archived_cleanup"
MANIFEST_PATH = ARCHIVE_DIR / "manifest.json"

# Tier B canonical copies — never archive these paths.
CANONICAL_KEEP = frozenset(
    p.replace("\\", "/")
    for p in (
        "README.md",
        "backend/response_validator.py",
        "backend/test_ws.py",
        "tools/testing/do_scrub.py",
        "tools/testing/evidence_collection.py",
        "tools/testing/pad_wav.py",
        "tools/testing/read_chunks.py",
        "tools/testing/test_queries_ws.py",
        "xtts_service/xtts_server.py",
        "xtts_service/stress_test.py",
    )
)

NEVER_MOVE = frozenset(
    p.replace("\\", "/")
    for p in (
        "cleanup_repo.py",
        "scripts/scan_unnecessary_files.py",
    )
)

ENTRY_POINTS = frozenset(
    p.replace("\\", "/")
    for p in (
        "start_main_servers.py",
        "scripts/project_start_server.py",
        "scripts/project_start_split.py",
        "backend/assistify_rag_server.py",
        "backend/main_llm_server.py",
        "Login_system/login_server.py",
        "tts_service/piper_server.py",
        "config.py",
        "run_all.py",
    )
)

GITIGNORE_MARKER_START = "# >>> cleanup_repo.py"
GITIGNORE_MARKER_END = "# <<< cleanup_repo.py"

# Reuse scan script patterns plus cleanup-specific entries.
GITIGNORE_PATTERNS = [
    "_archived_cleanup/",
    "*.pre_mt_backup",
    "temp_launchers/",
    "temp_phase*.py",
    "._*",
    "rag_verification_report.json",
    "**/final_rag_report*.json",
    "backend/conversations.json",
    "scripts/tmp_*.py",
    "backend/tmp_*.py",
    "tools/testing/_legacy_xtts/",
    "start_xtts_service.bat.disabled",
    "non_functional/old_python/",
]


def _norm(rel: str) -> str:
    return rel.replace("\\", "/")


def load_findings() -> tuple[list[dict], str]:
    if not JSON_PATH.is_file():
        print(f"Missing {JSON_PATH.relative_to(REPO_ROOT)} — regenerating via scan script...")
        subprocess.run(
            [sys.executable, str(SCAN_SCRIPT), "--json", str(JSON_PATH)],
            cwd=REPO_ROOT,
            check=True,
        )
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    return data.get("findings", []), str(JSON_PATH.relative_to(REPO_ROOT))


def plan_moves(findings: list[dict]) -> tuple[list[dict], list[dict]]:
    moves: list[dict] = []
    skipped: list[dict] = []

    for item in findings:
        tier = item.get("tier", "")
        if tier not in ("A", "B"):
            continue

        rel = _norm(item["path"])
        src = REPO_ROOT / rel

        if rel in NEVER_MOVE or rel in ENTRY_POINTS:
            skipped.append({"path": rel, "reason": "protected_entry", "tier": tier})
            continue
        if rel.startswith("_archived_cleanup/"):
            skipped.append({"path": rel, "reason": "already_archived", "tier": tier})
            continue
        if rel in CANONICAL_KEEP:
            skipped.append({"path": rel, "reason": "canonical_keep", "tier": tier})
            continue

        dest = ARCHIVE_DIR / rel
        if not src.exists():
            skipped.append({"path": rel, "reason": "missing", "tier": tier})
            continue
        if dest.exists():
            skipped.append({"path": rel, "reason": "dest_exists", "tier": tier})
            continue

        moves.append(
            {
                "from": rel,
                "to": _norm(str(dest.relative_to(REPO_ROOT))),
                "tier": tier,
            }
        )

    moves.sort(key=lambda m: m["from"])
    return moves, skipped


def patch_gitignore(dry_run: bool) -> list[str]:
    gitignore_path = REPO_ROOT / ".gitignore"
    existing_lines = gitignore_path.read_text(encoding="utf-8").splitlines()
    existing_set = set(existing_lines)

    to_add = [p for p in GITIGNORE_PATTERNS if p not in existing_set]

    if not to_add:
        print(".gitignore: all cleanup patterns already present.")
        return []

    block_lines = [GITIGNORE_MARKER_START, "# Repo cleanup / archive"]
    block_lines.extend(to_add)
    block_lines.append(GITIGNORE_MARKER_END)

    print(".gitignore: would append:")
    for line in to_add:
        print(f"  + {line}")

    if not dry_run:
        new_content = gitignore_path.read_text(encoding="utf-8").rstrip("\n")
        if GITIGNORE_MARKER_START in new_content:
            # Replace existing marked block.
            start = new_content.index(GITIGNORE_MARKER_START)
            end = new_content.index(GITIGNORE_MARKER_END) + len(GITIGNORE_MARKER_END)
            new_content = new_content[:start].rstrip("\n") + "\n\n" + "\n".join(block_lines) + "\n"
        else:
            new_content += "\n\n" + "\n".join(block_lines) + "\n"
        gitignore_path.write_text(new_content, encoding="utf-8")
        print(".gitignore: updated.")

    return to_add


def execute_moves(moves: list[dict]) -> list[dict]:
    moved: list[dict] = []
    for entry in moves:
        src = REPO_ROOT / entry["from"]
        dest = REPO_ROOT / entry["to"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        moved.append(entry)
        print(f"  moved {entry['from']} -> {entry['to']}")
    return moved


def write_manifest(source: str, moved: list[dict], skipped: list[dict]) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "moved": moved,
        "skipped": skipped,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote manifest: {MANIFEST_PATH.relative_to(REPO_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive Tier A/B files into _archived_cleanup/")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform moves, write manifest, and patch .gitignore",
    )
    parser.add_argument(
        "--gitignore-only",
        action="store_true",
        help="Only patch .gitignore (no file moves)",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    if args.gitignore_only:
        patch_gitignore(dry_run=False)
        return 0

    findings, source = load_findings()
    moves, skipped = plan_moves(findings)

    tier_a = sum(1 for m in moves if m["tier"] == "A")
    tier_b = sum(1 for m in moves if m["tier"] == "B")
    print(f"Source: {source}")
    print(f"Planned moves: {len(moves)} (Tier A: {tier_a}, Tier B: {tier_b})")
    print(f"Skipped: {len(skipped)}")

    if moves:
        print("\nMoves:")
        for entry in moves:
            print(f"  [{entry['tier']}] {entry['from']} -> {entry['to']}")
    else:
        print("\nNo moves planned.")

    if skipped:
        by_reason: dict[str, int] = {}
        for s in skipped:
            by_reason[s["reason"]] = by_reason.get(s["reason"], 0) + 1
        print("\nSkip reasons:", ", ".join(f"{k}={v}" for k, v in sorted(by_reason.items())))

    print("\n--- .gitignore ---")
    patch_gitignore(dry_run=dry_run)

    if dry_run:
        print("\nDry-run complete. Re-run with --execute to apply.")
        return 0

    if moves:
        print("\nExecuting moves...")
        moved = execute_moves(moves)
    else:
        moved = []

    write_manifest(source, moved, skipped)
    print(f"\nDone. Archived {len(moved)} file(s) under _archived_cleanup/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
