"""Validation tests for the generalized ``document_summary`` query family.

These tests prove (Bug A fix):

1. Genuine entity-definition queries still route to ``definition_entity``.
2. Self-referential document-overview queries route to ``document_summary``.
3. ``document_summary`` queries bypass the deterministic definition/list
   extractor (``_skip_deterministic_rag_shortcuts`` is True) and engage the
   grounded generation path (``_is_llm_generation_query`` is True), so the
   retrieved evidence is preserved and summarized rather than rejected.
4. The classifier is purely grammar-based: a never-before-seen document type
   still classifies correctly, demonstrating there is no per-document,
   per-company, or per-phrase hardcoding.

Everything is exercised through the bound server module so the shared ``S``
runtime (logger etc.) is initialised exactly as in production.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.assistify_rag_server import (  # noqa: E402
    _classify_query_family,
    _classify_query_family_v2,
    _is_document_summary_query,
    _is_llm_generation_query,
    _skip_deterministic_rag_shortcuts,
)

# Self-referential document-overview phrasings. These target the active
# uploaded corpus itself, not a domain concept.
DOCUMENT_SUMMARY_QUERIES = [
    "What is this document about?",
    "What is this PDF about?",
    "What is this file about?",
    "Summarize this document.",
    "Summarize the uploaded document.",
    "Give me an overview.",
    "What does this document discuss?",
    "Explain this handbook.",
    "Explain this guide.",
    "what is in this document",
    "tell me about the uploaded file",
    "provide a summary",
    "can you summarize this",
]

# Genuine entity-definition questions. These name a concept that lives INSIDE
# the document and must keep using the definition pipeline.
DEFINITION_ENTITY_QUERIES = [
    "What is FDIC?",
    "What is a checking account?",
    "What is APY?",
]

# Queries that are neither document-summary nor should be misclassified as one.
NON_SUMMARY_QUERIES = [
    "What is FDIC?",
    "What is a checking account?",
    "What is APY?",
    "What is the minimum balance for this account?",
    "what is the fee in this guide",
    "what is the outgoing wire fee?",
]


def test_document_summary_queries_route_to_document_summary():
    for q in DOCUMENT_SUMMARY_QUERIES:
        assert _is_document_summary_query(q) is True, q
        assert _classify_query_family_v2(q) == "document_summary", q
        assert _classify_query_family(q) == "document_summary", q


def test_definition_entity_queries_remain_definition_entity():
    for q in DEFINITION_ENTITY_QUERIES:
        assert _is_document_summary_query(q) is False, q
        assert _classify_query_family_v2(q) == "definition_entity", q
        assert _classify_query_family(q) == "definition_entity", q


def test_non_summary_queries_are_not_document_summary():
    for q in NON_SUMMARY_QUERIES:
        assert _is_document_summary_query(q) is False, q
        assert _classify_query_family_v2(q) != "document_summary", q


def test_document_summary_bypasses_deterministic_extractor():
    # The deterministic definition/list extractor must be skipped so the
    # grounded generation path answers from the retrieved chunks instead of
    # rejecting them via the definition-quality guards.
    for q in DOCUMENT_SUMMARY_QUERIES:
        assert _skip_deterministic_rag_shortcuts(q) is True, q
        assert _is_llm_generation_query(q) is True, q


def test_definition_queries_do_not_bypass_extractor():
    # Definition questions keep the deterministic extractor path.
    for q in DEFINITION_ENTITY_QUERIES:
        assert _skip_deterministic_rag_shortcuts(q) is False, q
        assert _is_llm_generation_query(q) is False, q


def test_generality_unknown_document_types():
    # Synthetic, never-before-seen container phrasings must still classify as
    # document_summary purely from grammar — no document/company/phrase list is
    # involved. This guards against regressions toward hardcoded matching.
    unseen = [
        "summarize this whitepaper",
        "what is this manual about",
        "give me an overview of the attached report",
        "explain the uploaded presentation",
        "what does this paper cover",
    ]
    for q in unseen:
        assert _is_document_summary_query(q) is True, q
        assert _classify_query_family_v2(q) == "document_summary", q


if __name__ == "__main__":
    import traceback

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print("ALL PASS" if failures == 0 else f"{failures} FAILURE(S)")
    sys.exit(1 if failures else 0)


def test_document_summary_does_not_intercept_targeted_about_entity_queries():
    targeted = [
        "What does the document say about Freud?",
        "What does this document say about long-term memory?",
    ]
    for q in targeted:
        assert _is_document_summary_query(q) is False, q
        assert _classify_query_family_v2(q) != "document_summary", q


def test_objectless_document_summary_is_not_memory_rewrite():
    from backend.retrieval.followup import _is_memory_rewrite_query

    q = "Give me a summary of this document."

    assert _is_document_summary_query(q) is True
    assert _classify_query_family_v2(q) == "document_summary"
    assert _is_memory_rewrite_query(q) is False


def test_explain_concept_according_to_document_avoids_strict_definition_family():
    q = "Explain long-term memory according to the document."

    assert _is_document_summary_query(q) is False
    assert _classify_query_family_v2(q) != "definition_entity"


def test_document_anchored_explain_queries_are_not_rewritten_to_what_is():
    from backend.retrieval.followup import (
        _maybe_rewrite_about_entity_question,
        _normalize_conversational_definition_query,
    )

    q = "Explain long-term memory according to the document."

    assert _maybe_rewrite_about_entity_question(q) == q
    assert _normalize_conversational_definition_query(q) == q


def test_document_anchored_generation_queries_skip_deterministic_shortcuts():
    from backend.retrieval.lists import _skip_deterministic_rag_shortcuts

    assert _skip_deterministic_rag_shortcuts("Explain long-term memory according to the document.") is True
    assert _skip_deterministic_rag_shortcuts("What does the document say about Freud?") is True


def test_document_summary_coverage_selector_prioritizes_structure_and_diversity():
    from backend.retrieval.routing import _select_document_summary_coverage_docs

    docs = [
        {
            "id": "deep-1",
            "score": 9.5,
            "page_content": "Deep body discussion with repeated topical prose.",
            "metadata": {"page": 74, "section": "Body", "title": "Advanced Topic", "chunk_role": "content"},
        },
        {
            "id": "deep-2",
            "score": 9.1,
            "page_content": "Another body discussion from the same section.",
            "metadata": {"page": 75, "section": "Body", "title": "Advanced Topic", "chunk_role": "content"},
        },
        {
            "id": "intro",
            "score": 2.0,
            "page_content": "The introduction explains the document scope.",
            "metadata": {"page": 1, "section": "Introduction", "title": "Introduction", "chunk_role": "introduction"},
        },
        {
            "id": "toc",
            "score": 1.5,
            "page_content": "Contents Chapter 1 Chapter 2 Chapter 3",
            "metadata": {"page": 2, "section": "Table of Contents", "title": "Table of Contents", "chunk_role": "toc"},
        },
        {
            "id": "chapter",
            "score": 1.2,
            "page_content": "Chapter 1 overview and learning objectives.",
            "metadata": {"page": 8, "section": "Chapter 1", "title": "Learning Objectives", "chapter": "Chapter 1", "chunk_role": "chapter_heading"},
        },
    ]

    selected = _select_document_summary_coverage_docs(docs, max_docs=4)
    selected_ids = [doc["id"] for doc in selected]

    assert "intro" in selected_ids
    assert "toc" in selected_ids
    assert "chapter" in selected_ids
    assert selected_ids.count("deep-1") + selected_ids.count("deep-2") <= 1


def test_heading_source_uses_metadata_when_body_has_no_heading_lines():
    from backend import assistify_rag_server  # noqa: F401 - binds routing helpers to live server module
    from backend.retrieval.routing import _resolve_doc_heading_source

    doc = {
        "page_content": "This paragraph contains ordinary prose with no standalone heading line.",
        "metadata": {
            "title": "Learning Objectives",
            "section": "Lesson 1",
            "chapter": "Chapter 1",
        },
    }

    result = _resolve_doc_heading_source("Provide a chapter-by-chapter overview of this document.", doc)

    assert result["chosen_heading"] == "Learning Objectives"
    assert result["chosen_from"] == "metadata"
    assert "Learning Objectives" in result["raw_candidates"]


def test_document_summary_structural_rerank_moves_intro_ahead_of_deep_body():
    from backend.retrieval.routing import _rerank_document_summary_for_coverage

    docs = [
        {"id": "deep", "score": 10.0, "page_content": "Deep body", "metadata": {"page": 74, "section": "Body", "chunk_role": "content"}},
        {"id": "intro", "score": 1.0, "page_content": "Intro", "metadata": {"page": 1, "section": "Introduction", "chunk_role": "introduction"}},
    ]

    reranked = _rerank_document_summary_for_coverage(docs)

    assert reranked[0]["id"] == "intro"
