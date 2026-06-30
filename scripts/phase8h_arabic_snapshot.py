"""Behavioral snapshot for the Phase 8H-2 Arabic retrieval/translation helpers.

Covers the deterministic (non-async, non-network) functions moved into
backend/retrieval/arabic.py so a before/after diff proves the extraction
preserved behavior. Async/LLM functions are intentionally excluded.

Usage:
    python scripts/phase8h_arabic_snapshot.py <label> <out.json>
    python scripts/phase8h_arabic_snapshot.py --diff a.json b.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AR = ["ما هو النظام", "اشرح العملية", "ما الفرق بين الالف والباء", "قائمة العناصر",
      "النظام alpha يعمل", "تعريف الوحدة", "كيف يرتبط هذا", ""]
EN = ["what is the system", "list the items", "explain the process",
      "the alpha-beta system (v2)", "  define   module  ", "AWS S3 bucket"]
TOKENS = ["alpha", "beta2", "S3", "نظام", "v2", "the", "a", "ABC"]
BULLETS = "- Alpha\n- Beta\n* Gamma\n1. Delta\n2. Epsilon"
DOCS = [
    {"text": "Alpha system handles input.", "source": "a.pdf", "score": 0.9, "chunk_index": 1},
    {"text": "Beta module transforms data.", "source": "a.pdf", "score": 0.4, "chunk_index": 2},
]


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
    for t in AR + EN:
        _call(res, srv, "_sanitize_arabic_text", t)
        _call(res, srv, "_preprocess_for_tts", t, "ar")
        _call(res, srv, "_preprocess_for_tts", t, "en")
        _call(res, srv, "_clean_english_search_query_candidate", t)
        _call(res, srv, "_expand_english_retrieval_query_terms", t)
        _call(res, srv, "_extract_latin_runs_from_query", t)
        _call(res, srv, "_normalize_arabic_keyword_for_non_llm_query", t)
        _call(res, srv, "_arabic_structural_search_hints", t)
        _call(res, srv, "_build_non_llm_arabic_explanation_query", t)
        _call(res, srv, "_retrieval_candidate_strength", t, DOCS)
        _call(res, srv, "_translation_retrieval_is_weak", t, DOCS)
        _call(res, srv, "_retrieval_candidate_strength", t, None)
        _call(res, srv, "_translation_retrieval_is_weak", t, [])
    for tok in TOKENS:
        _call(res, srv, "_allow_latin_token_in_arabic_text", tok)
        _call(res, srv, "_normalize_arabic_keyword_for_non_llm_query", tok)
    _call(res, srv, "_parse_bullet_list_items", BULLETS)
    for a in AR[:4]:
        for e in EN[:3]:
            _call(res, srv, "_repair_fast_arabic_search_query", a, e)
            _call(res, srv, "_is_compact_arabic_item_translation", a, e)
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
