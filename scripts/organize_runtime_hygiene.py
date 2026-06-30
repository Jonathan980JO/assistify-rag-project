#!/usr/bin/env python3
"""Relocate files that can harm runtime."""
from __future__ import annotations
import argparse, json, shutil
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_ROOT = REPO_ROOT / "_runtime_hygiene_archive"
SCAN_JSON = REPO_ROOT / "docs" / "unnecessary_files.json"
MANIFEST = ARCHIVE_ROOT / "manifest.json"
ROOT_STUB_DIRS = ("TTS",)
ROOT_DEBUG = ("test_list_patch.py","test_search.py","hotswap_validation.py","_write_phase13d_report.py")
ROOT_REPORT_GLOBS = ("Phase*.md","*_Validation_Report.md","*_Investigation_Report.md","*_Investigation*.md","Generation_Pipeline_*.md","MFA_Disable_*.md","Release_Blockers_Report.md","Server_Startup_Report.md","Frontend_Artifact_Audit.md","AGENT_TASK_PROMPT.md")
ROOT_GENERATED = ("repo_tree_after_phase11b.txt","repo_tree_after_phase12a.txt")

def _norm(rel): return rel.replace("\\", "/")

def tier_a_paths():
    if not SCAN_JSON.is_file(): return []
    data = json.loads(SCAN_JSON.read_text(encoding="utf-8"))
    return [_norm(i["path"]) for i in data.get("findings",[]) if i.get("tier")=="A"]

def plan_moves():
    moves = []
    for name in ROOT_STUB_DIRS:
        if (REPO_ROOT/name).is_dir():
            moves.append({"from":name,"to":f"legacy/stubs/{name}","category":"import_shadow"})
    for name in ROOT_DEBUG:
        if (REPO_ROOT/name).is_file():
            moves.append({"from":name,"to":f"tools/experiments/{name}","category":"root_debug"})
    for pattern in ROOT_REPORT_GLOBS:
        for src in REPO_ROOT.glob(pattern):
            if src.is_file() and src.name != "README.md":
                moves.append({"from":src.name,"to":f"docs/archive/phase-reports/{src.name}","category":"root_report"})
    for name in ROOT_GENERATED:
        if (REPO_ROOT/name).is_file():
            moves.append({"from":name,"to":f"archive/generated/{name}","category":"generated_dump"})
    for rel in tier_a_paths():
        if rel.startswith(("_runtime_hygiene_archive/","_archived_cleanup/","legacy/stubs/")): continue
        if rel.startswith("archived_pdfs/") and "tmp_" not in Path(rel).name: continue
        if not (REPO_ROOT/rel).exists(): continue
        moves.append({"from":rel,"to":f"_runtime_hygiene_archive/{rel}","category":"tier_a_clutter"})
    seen=set(); out=[]
    for m in moves:
        if m["from"] not in seen: seen.add(m["from"]); out.append(m)
    return sorted(out, key=lambda x: x["from"])

def execute_moves(moves):
    done=[]
    for e in moves:
        src, dest = REPO_ROOT/e["from"], REPO_ROOT/e["to"]
        if dest.exists():
            print(f"  SKIP: {e['from']}"); continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest)); done.append(e)
        print(f"  moved [{e['category']}] {e['from']} -> {e['to']}")
    return done

def main():
    p=argparse.ArgumentParser(); p.add_argument("--execute", action="store_true"); args=p.parse_args()
    moves=plan_moves(); print(f"Runtime hygiene plan: {len(moves)} moves")
    for e in moves: print(f"  [{e['category']}] {e['from']} -> {e['to']}")
    if not args.execute: print("Dry-run. Use --execute."); return 0
    moved=execute_moves(moves)
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({"archived_at":datetime.now(timezone.utc).isoformat(),"moved":moved}, indent=2), encoding="utf-8")
    print(f"Done. Moved {len(moved)}.")
    return 0
if __name__=="__main__": raise SystemExit(main())
