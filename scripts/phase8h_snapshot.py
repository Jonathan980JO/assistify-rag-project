"""Behavioral snapshot harness for the Phase 8H follow-up cluster.

Captures deterministic outputs of the follow-up / Arabic / memory-rewrite
helper functions so a before/after diff can prove the extraction into
``backend/retrieval/followup.py`` preserved behavior. The standard Phase 8
validation gate does not execute any retrieval logic, so this harness is the
only check that covers the actual function behavior.

Usage:
    python scripts/phase8h_snapshot.py <label> <out.json>     # capture
    python scripts/phase8h_snapshot.py --diff a.json b.json    # compare
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EN = [
    "explain more", "what do you mean?", "tell me about Money",
    "what is the capital", "list the items", "and the second one?",
    "simplify that", "explain", "make it shorter", "i don't get it", "",
    "compare the two", "what about that", "the third one", "go on",
]
AR = ["اشرحها", "ماذا تقصد", "وما علاقتها", "الثانية", "ها؟", "اشرح اكثر", "الأخيرة"]
ALL_TEXT = EN + AR

ITEMS = ["Alpha system", "Beta module", "Gamma process", "Delta unit"]
ANSWER_LIST = "1. Alpha system\n2. Beta module\n3. Gamma process\n4. Delta unit"
ANSWER_PROSE = (
    "The process has several parts. Alpha system handles input. "
    "Beta module transforms it. Gamma process validates the result."
)
HISTORY = [
    {"role": "user", "content": "what is alpha"},
    {"role": "assistant", "content": "Alpha is the first component."},
    {"role": "user", "content": "list the components"},
    {"role": "assistant", "content": ANSWER_LIST},
]
DOC_DICTS = [
    {"text": "Alpha system handles input processing reliably.", "source": "doc_a.pdf", "score": 0.91, "chunk_index": 1},
    {"text": "Beta module transforms data between stages.", "source": "doc_a.pdf", "score": 0.84, "chunk_index": 2},
]


def _r(v):
    """Stable repr for snapshotting."""
    try:
        return repr(v)
    except Exception as e:  # noqa: BLE001
        return f"<unrepr:{type(e).__name__}>"


def _call(results, srv, name, *args):
    fn = getattr(srv, name, None)
    if fn is None:
        results[f"{name}{_argkey(args)}"] = "MISSING_FN"
        return
    try:
        results[f"{name}{_argkey(args)}"] = _r(fn(*args))
    except Exception as e:  # noqa: BLE001
        results[f"{name}{_argkey(args)}"] = f"EXC:{type(e).__name__}:{str(e)[:160]}"


def _argkey(args):
    return "(" + ",".join(_r(a)[:40] for a in args) + ")"


def capture() -> dict:
    srv = __import__("backend.assistify_rag_server", fromlist=["app"])

    # Fixed in-memory state so state-reading helpers are deterministic.
    fixed_state = {
        "alpha": {
            "query": "list the components",
            "answer": ANSWER_LIST,
            "list_query": "list the components",
            "list_answer": ANSWER_LIST,
            "items": list(ITEMS),
            "chunks": list(DOC_DICTS),
            "last_assistant_answer": ANSWER_LIST,
            "timestamp": 1_700_000_000.0,
        }
    }
    try:
        srv.last_answer_state = dict(fixed_state)
        srv._last_good_answer_state = dict(fixed_state)
        srv._last_list_state = dict(fixed_state)
    except Exception:
        pass

    res: dict = {}

    for t in ALL_TEXT:
        _call(res, srv, "_is_arabic_followup_strong", t)
        _call(res, srv, "_is_arabic_followup_context", t)
        _call(res, srv, "_is_weak_generic_request", t)
        _call(res, srv, "_is_memory_rewrite_query", t)
        _call(res, srv, "_classify_memory_rewrite_intent", t)
        _call(res, srv, "_classify_followup_intent", t)
        _call(res, srv, "_is_undirected_explain_more", t)
        _call(res, srv, "_is_bare_comparison_followup_query", t)
        _call(res, srv, "_normalize_conversational_definition_query", t)
        _call(res, srv, "_extract_focus_concept_from_explain_query_surface", t)
        _call(res, srv, "_extract_focus_concept_from_explanatory_query_surface", t)
        _call(res, srv, "_extract_arabic_concept_from_query_surface", t)
        _call(res, srv, "_extract_definition_concept_from_query_surface", t)
        _call(res, srv, "_followup_capitalize_sentence_start", t)
        _call(res, srv, "_followup_strip_header_prefix", t)
        _call(res, srv, "_followup_merge_safe_ocr_split_words", t)
        _call(res, srv, "_split_safe_ocr_merged_prefix_words", t)
        _call(res, srv, "_followup_salvage_fragment_clause", t)
        _call(res, srv, "_followup_item_head", t)
        _call(res, srv, "_followup_content_tokens", t)
        _call(res, srv, "_split_followup_sentences", t)
        _call(res, srv, "_split_followup_explanation_sentences", t)
        _call(res, srv, "_is_followup_query", t)
        _call(res, srv, "_maybe_rewrite_about_entity_question", t)
        _call(res, srv, "_extract_about_entity_question", t)

    for ans in (ANSWER_LIST, ANSWER_PROSE):
        _call(res, srv, "_extract_followup_items_from_answer", ans)
        _call(res, srv, "_split_memory_answer_units", ans)
        _call(res, srv, "_limit_memory_lines", ans, 3)

    for it in ITEMS:
        _call(res, srv, "_memory_item_summary_label", it)
        _call(res, srv, "_followup_item_head", it)
        _call(res, srv, "_followup_query_focus_phrase", it, "explain it more")
        _call(res, srv, "_followup_query_surface_focus_phrase", it, "explain it more")
        _call(res, srv, "_followup_text_mentions_item", ANSWER_PROSE, it)
        _call(res, srv, "_followup_text_has_item_head_anchor", ANSWER_PROSE, it)

    _call(res, srv, "_join_memory_items", ITEMS)
    _call(res, srv, "_join_short_item_names", ITEMS, 5)
    _call(res, srv, "_followup_list_chunk_support_score", ITEMS, ANSWER_PROSE)
    _call(res, srv, "_sentence_mentions_many_followup_items", ANSWER_PROSE, ITEMS)
    _call(res, srv, "_infer_previous_list_relation_phrase", "list the components")

    for t in ["the second one", "explain the third", "first", "الثانية", "tell me about the last item"]:
        _call(res, srv, "_resolve_followup_ordinal", ITEMS, t)
        _call(res, srv, "_select_followup_target_item", ITEMS, t)
        _call(res, srv, "_resolve_arabic_ordinal_target_from_items", t, ITEMS)
        _call(res, srv, "_infer_followup_answer_type", t, ANSWER_LIST)

    for prev, action in [(ANSWER_PROSE, "shorten"), (ANSWER_PROSE, "simplify"),
                         (ANSWER_LIST, "expand"), (ANSWER_PROSE, "rephrase")]:
        _call(res, srv, "_rewrite_previous_answer_from_memory", prev, action)

    _call(res, srv, "_extract_recent_definition_concepts_from_history", HISTORY, 6)
    _call(res, srv, "_rewrite_bare_comparison_query_from_history", "compare them", HISTORY, "alpha")
    _call(res, srv, "_evidence_has_explicit_explanation", "Alpha system", ANSWER_PROSE)
    _call(res, srv, "_extract_followup_context_window", ANSWER_PROSE, "Beta module", 1800)
    _call(res, srv, "_build_followup_excerpts", DOC_DICTS, "Alpha system")
    _call(res, srv, "_get_last_answer_state", "alpha")
    _call(res, srv, "_has_recent_followup_state", "alpha")
    _call(res, srv, "_is_marked_arabic_resolved_followup", "alpha", "اشرحها")

    return res


def main():
    if sys.argv[1] == "--diff":
        a = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        b = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
        keys = sorted(set(a) | set(b))
        diffs = [(k, a.get(k, "<absent>"), b.get(k, "<absent>")) for k in keys if a.get(k) != b.get(k)]
        if diffs:
            print(f"SNAPSHOT DIFF: {len(diffs)} mismatches out of {len(keys)} cases")
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
