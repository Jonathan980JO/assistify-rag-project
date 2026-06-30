"""Regression tests for KB/RAG final RCA fixes (status, validation, greetings)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.assistify_rag_server import (
    _classify_smalltalk_intent,
    _definition_quality_rejected_reason,
    _detect_fact_query_type,
    _extract_table_fact_answer,
    _is_numeric_fact_lookup_query,
    _normalize_query_for_router,
    _resolve_grounded_answer_route,
    _set_kb_pipeline_stage,
    classify_query_route,
)
from backend.config_head import RAG_NO_MATCH_RESPONSE
from backend.rag_query_prep import is_pure_conversational_only, prepare_query_for_rag, strip_conversational_prefix


MERIDIAN_DOCS = [
    {
        "page_content": (
            "Meridian Financial Services is a regional bank offering personal and business banking.\n\n"
            "[TABLE DATA]\n"
            "Everyday Checking | $500 minimum balance | No monthly fee\n"
            "Premium Checking | $2,500 minimum balance | Waived fees with direct deposit\n\n"
            "FDIC insurance covers deposits up to $250,000 per depositor, per insured bank."
        ),
        "metadata": {"filename": "Meridian_Financial_Handbook.pdf"},
    }
]


def test_greeting_variants_normalize_and_classify() -> None:
    variants = {
        "hi": "greeting",
        "hii": "greeting",
        "hiii": "greeting",
        "hello": "greeting",
        "helloo": "greeting",
        "hey": "greeting",
        "heyy": "greeting",
        "thanks": "thanks",
        "thankss": "thanks",
        "ok": "ack",
        "okk": "ack",
    }
    for raw, expected in variants.items():
        norm = _normalize_query_for_router(raw)
        assert _classify_smalltalk_intent(raw) == expected, f"{raw!r} norm={norm!r}"
        assert classify_query_route(raw) == "smalltalk", raw


def test_greeting_variants_strip_prefix() -> None:
    for variant in ("hii", "heyy", "helloo", "thankss", "okk"):
        assert strip_conversational_prefix(variant) == ""


def test_prepare_greeting_variants_smalltalk() -> None:
    for variant in ("hi", "hii", "hiii", "helloo", "heyy", "thankss", "okk"):
        prepared = asyncio.run(prepare_query_for_rag(variant))
        assert prepared.direct_response is not None, variant
        assert prepared.rag_query == "", variant


def test_numeric_fact_query_detection() -> None:
    assert _is_numeric_fact_lookup_query("What is the FDIC coverage limit?")
    assert _is_numeric_fact_lookup_query(
        "What is the minimum balance requirement for Everyday Checking?"
    )
    assert _detect_fact_query_type("What is the FDIC coverage limit?") == "numeric"
    assert _resolve_grounded_answer_route("What is the FDIC coverage limit?") == "fact"


def test_table_fact_fdic_extraction() -> None:
    answer = _extract_table_fact_answer("What is the FDIC coverage limit?", MERIDIAN_DOCS)
    assert answer is not None
    assert "250" in answer
    assert answer != RAG_NO_MATCH_RESPONSE


def test_table_fact_minimum_balance_extraction() -> None:
    answer = _extract_table_fact_answer(
        "What is the minimum balance requirement for Everyday Checking?",
        MERIDIAN_DOCS,
    )
    assert answer is not None
    assert "500" in answer
    assert "minimum balance" in answer.lower()
    assert "everyday checking" in answer.lower()
    assert "premium" not in answer.lower()


def test_definition_quality_accepts_insured_sentence() -> None:
    sentence = "FDIC insurance covers deposits up to $250,000 per depositor."
    reason = _definition_quality_rejected_reason(
        sentence,
        entity_l="fdic coverage limit",
        query_text="What is the FDIC coverage limit?",
    )
    assert reason is None, reason


def test_kb_pipeline_stage_clamps_indexed_to_total() -> None:
    from backend import assistify_rag_server as srv

    srv._kb_pipeline_state["state"] = "processing"
    srv._kb_pipeline_state["stage"] = "writing"
    _set_kb_pipeline_stage("writing", indexed=120, total=100, percent=100)
    assert srv._kb_pipeline_state["indexed_chunks"] == 100
    assert srv._kb_pipeline_state["total_chunks"] == 100


if __name__ == "__main__":
    test_greeting_variants_normalize_and_classify()
    test_greeting_variants_strip_prefix()
    test_prepare_greeting_variants_smalltalk()
    test_numeric_fact_query_detection()
    test_table_fact_fdic_extraction()
    test_table_fact_minimum_balance_extraction()
    test_definition_quality_accepts_insured_sentence()
    test_kb_pipeline_stage_clamps_indexed_to_total()
    print("All KB/RAG final fix tests passed.")
