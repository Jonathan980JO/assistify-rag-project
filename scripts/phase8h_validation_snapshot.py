"""Behavioral snapshot for the Phase 8H-3 quality/evidence guard helpers
moved into backend/retrieval/validation.py.

Usage:
    python scripts/phase8h_validation_snapshot.py <label> <out.json>
    python scripts/phase8h_validation_snapshot.py --diff a.json b.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SENTENCES = [
    "Money is a medium of exchange used to settle debts.",
    "The system processes input and returns output.",
    "1. Alpha 2. Beta 3. Gamma",
    "see page 12 fig 3",
    "A B C D E F G H I J",
    "This refers to the aforementioned process described above.",
    "",
    "Photosynthesis is the process by which plants convert light into energy.",
]
ITEMS = ["Alpha", "Beta module system", "a very long item label that exceeds the typical word budget for a list", "x", "1.5%", "Gamma-Delta"]
QUERIES = ["what is money", "list the five components", "define the system",
           "how many steps are there", "name three things", "explain the relationship", ""]


def _r(v):
    try:
        return repr(v)
    except Exception as e:  # noqa: BLE001
        return f"<unrepr:{type(e).__name__}>"


def _argkey(args):
    return "(" + ",".join(_r(a)[:36] for a in args) + ")"


def _call(res, srv, name, *args):
    fn = getattr(srv, name, None)
    if fn is None:
        res[f"{name}{_argkey(args)}"] = "MISSING_FN"
        return
    try:
        res[f"{name}{_argkey(args)}"] = _r(fn(*args))
    except Exception as e:  # noqa: BLE001
        res[f"{name}{_argkey(args)}"] = f"EXC:{type(e).__name__}:{str(e)[:160]}"


def capture() -> dict:
    srv = __import__("backend.assistify_rag_server", fromlist=["app"])
    res: dict = {}
    for s in SENTENCES:
        _call(res, srv, "_preview_for_quality_log", s, 180)
        _call(res, srv, "_definition_direct_pattern_match", s, "")
        _call(res, srv, "_definition_direct_pattern_match", s, "money")
        _call(res, srv, "_is_definition_boilerplate_sentence" if False else "_definition_quality_rejected_reason", s, "", True, "")
        _call(res, srv, "_definition_quality_rejected_reason", s, "money", False, "what is money")
        for q in QUERIES:
            _call(res, srv, "_ocr_filter_rejected_reason", s, q)
    for q in QUERIES:
        _call(res, srv, "_list_query_count_target", q)
    for it in ITEMS:
        _call(res, srv, "_strict_list_label_reject_reason", it, 5, False)
        _call(res, srv, "_strict_list_label_reject_reason", it, 8, True)
    return res


def main():
    if sys.argv[1] == "--diff":
        a = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        b = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
        keys = sorted(set(a) | set(b))
        diffs = [(k, a.get(k, "<absent>"), b.get(k, "<absent>")) for k in keys if a.get(k) != b.get(k)]
        if diffs:
            print(f"SNAPSHOT DIFF: {len(diffs)}/{len(keys)} mismatches")
            for k, av, bv in diffs[:60]:
                print(f"  {k}\n    before={av}\n    after ={bv}")
            sys.exit(1)
        print(f"SNAPSHOT MATCH: all {len(keys)} cases identical")
        return
    label, out = sys.argv[1], sys.argv[2]
    data = capture()
    Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{label}] captured {len(data)} cases -> {out}")


if __name__ == "__main__":
    main()
