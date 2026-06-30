from __future__ import annotations


def test_phase14_validation_questions_are_declared_in_order() -> None:
    from scripts.phase14_rag_validation import VALIDATION_QUESTIONS

    assert [item["id"] for item in VALIDATION_QUESTIONS] == [
        "q1_document_about",
        "q2_document_summary",
        "q3_major_schools",
        "q4_long_term_memory",
        "q5_freud",
        "q6_chapter_overview",
    ]
    assert VALIDATION_QUESTIONS[0]["query"] == "What is this document about?"


def test_phase14_partial_fragment_detection_flags_known_truncation() -> None:
    from scripts.phase14_rag_validation import is_partial_fragment

    assert is_partial_fragment("The major") is True
    assert is_partial_fragment("The major schools discussed include structuralism and functionalism.") is False
    assert is_partial_fragment("Not found in the document.") is False


def test_ws_phase14_trace_meta_is_opt_in_and_sanitized() -> None:
    from backend.services.voice_service import _build_phase14_trace_meta

    assert _build_phase14_trace_meta({"text": "hello"}) == {}

    meta = _build_phase14_trace_meta(
        {
            "text": "hello",
            "phase14_trace": True,
            "client_trace_id": "abc 123 !@#",
        }
    )

    assert meta == {
        "phase14_trace": True,
        "client_trace_id": "abc-123-",
    }


def test_streaming_phase14_doc_trace_limits_content_and_metadata() -> None:
    from backend.services.streaming_service import _phase14_doc_trace_rows

    docs = [
        {
            "id": "chunk-1",
            "similarity": 0.91,
            "metadata": {
                "source": "doc_a",
                "filename": "sample.pdf",
                "page": 3,
                "section": "Intro",
                "tenant_id": 2,
                "secret": "do-not-include",
            },
            "text": "A" * 500,
        }
    ]

    rows = _phase14_doc_trace_rows(docs, limit=1, preview_chars=40)

    assert rows == [
        {
            "rank": 1,
            "id": "chunk-1",
            "score": 0.91,
            "source": "doc_a",
            "filename": "sample.pdf",
            "page": 3,
            "section": "Intro",
            "preview": "A" * 40,
        }
    ]


def test_retrieve_debug_row_exposes_scores_metadata_and_heading_evidence() -> None:
    from backend.routers.kb_router import _build_retrieve_debug_row

    doc = {
        "id": "chunk-7",
        "similarity": 0.42,
        "rerank_score": 8.75,
        "metadata": {
            "source": "doc_a",
            "filename": "sample.pdf",
            "page": 5,
            "section": "Lesson 2",
            "chapter": "Chapter 1",
            "title": "Learning Objectives",
            "unit": "1",
            "chunk_role": "introduction",
            "tenant_id": 2,
        },
        "text": "Learning objectives introduce the chapter themes.",
    }
    heading = {
        "chosen_heading": "Learning Objectives",
        "chosen_from": "metadata",
        "raw_candidates": ["Learning Objectives"],
    }

    row = _build_retrieve_debug_row(doc, rank=1, heading=heading)

    assert row["rank"] == 1
    assert row["id"] == "chunk-7"
    assert row["similarity"] == 0.42
    assert row["rerank_score"] == 8.75
    assert row["score"] == 8.75
    assert row["page"] == 5
    assert row["section"] == "Lesson 2"
    assert row["chapter"] == "Chapter 1"
    assert row["title"] == "Learning Objectives"
    assert row["unit"] == "1"
    assert row["chunk_role"] == "introduction"
    assert row["metadata"]["tenant_id"] == 2
    assert row["heading"] == heading
    assert "Learning objectives" in row["text_preview"]


def test_phase14a_evidence_report_declares_required_snapshot_sections() -> None:
    from scripts.phase14a_document_summary_evidence import (
        DOCUMENT_SUMMARY_EVIDENCE_QUERIES,
        render_markdown_report,
    )

    assert [item["query"] for item in DOCUMENT_SUMMARY_EVIDENCE_QUERIES] == [
        "What is this document about?",
        "Give me a summary of this document.",
        "Provide a chapter-by-chapter overview of this document.",
    ]

    report = render_markdown_report(
        [
            {
                "id": "q1_document_about",
                "query": "What is this document about?",
                "retrieval": {
                    "retrieval_query": "document overview summary introduction table of contents units chapters key topics",
                    "results": [
                        {
                            "rank": 1,
                            "page": 1,
                            "rerank_score": 4.2,
                            "metadata": {"title": "Introduction", "chunk_role": "introduction"},
                            "heading": {"chosen_heading": "Introduction", "raw_candidates": ["Introduction"]},
                            "text_preview": "Introduction preview",
                        }
                    ],
                },
                "selected_context": [{"rank": 1, "page": 1, "section": "Introduction", "preview": "Selected"}],
                "answer": "Final answer",
            }
        ]
    )

    assert "Top 20 Retrieved Chunks" in report
    assert "Page Numbers" in report
    assert "Rerank Scores" in report
    assert "Chunk Metadata" in report
    assert "Heading Metadata" in report
    assert "Selected Context Sent To The LLM" in report
    assert "Final Answer" in report


def test_generation_context_prefers_structural_chunks_for_document_summary() -> None:
    from backend.retrieval.generation import _select_generation_context_docs

    docs = [
        {
            "id": "body",
            "score": 1.0,
            "page_content": "A body paragraph includes a definition-like sentence and unrelated details.",
            "metadata": {"page": 55, "section": "Body", "chunk_role": "content"},
        },
        {
            "id": "toc",
            "score": 0.5,
            "page_content": "Table of Contents Chapter 1 Introduction Chapter 2 Learning Chapter 3 Memory",
            "metadata": {"page": 2, "section": "Table of Contents", "title": "Table of Contents", "chunk_role": "toc"},
        },
    ]

    selected = _select_generation_context_docs("Give me a summary of this document.", docs, max_docs=1)

    assert selected[0]["id"] == "toc"


def test_structural_embedding_text_prefixes_metadata_without_replacing_body() -> None:
    from backend.knowledge_base import _embedding_text_with_structure

    text = _embedding_text_with_structure(
        "Body text remains the stored document payload.",
        {"chapter": "Chapter 1", "section": "Lesson 1", "title": "Learning Objectives"},
    )

    assert text.startswith("Chapter: Chapter 1 | Section: Lesson 1 | Title: Learning Objectives")
    assert text.endswith("Body text remains the stored document payload.")


def test_websocket_header_kwargs_match_installed_websockets_api() -> None:
    from scripts.phase14_rag_validation import websocket_header_kwargs

    kwargs = websocket_header_kwargs("session=abc")

    assert kwargs in (
        {"additional_headers": [("Cookie", "session=abc")]},
        {"extra_headers": [("Cookie", "session=abc")]},
    )
    assert not ({"additional_headers", "extra_headers"} <= set(kwargs))


def test_document_summary_uses_generic_overview_retrieval_seed() -> None:
    from backend.retrieval.routing import _overview_seed_query
    from backend.services.streaming_service import _retrieval_query_for_family

    assert _retrieval_query_for_family("What is this document about?", "document_summary") == _overview_seed_query()
    assert _retrieval_query_for_family("Explain memory", "explanatory_compare") == "Explain memory"


def test_evaluator_prefers_websocket_trace_retrieval_and_flags_uploaded_materials_not_found() -> None:
    from scripts.phase14_rag_validation import evaluate_result

    payload = {
        "timing": {
            "phase14_retrieved_count": 4,
            "phase14_selected_context": [{"preview": "evidence"}],
        }
    }

    result = evaluate_result(
        "Warmly, the detail is not in the uploaded materials.",
        {"results": []},
        payload,
    )

    assert result["has_retrieval"] is True
    assert result["retrieved_count"] == 4
    assert result["has_selected_context"] is True
    assert result["is_not_found"] is True


def test_document_summary_skips_targeted_rerank() -> None:
    from backend.services.streaming_service import _should_apply_query_intent_rerank

    assert _should_apply_query_intent_rerank("document_summary") is False
    assert _should_apply_query_intent_rerank("fact_entity") is False
    assert _should_apply_query_intent_rerank("out_of_scope_candidate") is True


def test_evaluator_flags_timeout_placeholder_as_failure() -> None:
    from scripts.phase14_rag_validation import evaluate_result

    result = evaluate_result(
        "Sorry, request timed out. Please try again.",
        {"results": []},
        {"timing": {"phase14_retrieved_count": 2, "phase14_selected_context": [{"preview": "evidence"}]}},
    )

    assert result["is_timeout"] is True
    assert result["websocket_error"] is True


def test_document_summary_no_match_uses_retrieved_evidence_fallback() -> None:
    from backend import assistify_rag_server  # noqa: F401 - binds routing helpers to live server module
    from backend.retrieval.routing import RAG_NO_MATCH_RESPONSE, _apply_not_found_ux

    docs = [
        {
            "page_content": "Introduction to Example. The document explains research methods and learning concepts. It also covers memory systems.",
            "metadata": {"section": "Introduction", "page": 1},
        },
        {
            "page_content": "Learning section. Classical conditioning and operant conditioning are discussed with examples.",
            "metadata": {"section": "Learning", "page": 2},
        },
    ]

    answer = _apply_not_found_ux("Give me a summary of this document.", RAG_NO_MATCH_RESPONSE, docs)

    assert "couldn't find" not in answer.lower()
    assert "not found" not in answer.lower()
    assert any(term in answer.lower() for term in ("research methods", "learning", "classical conditioning"))


def test_document_anchored_entity_no_match_extracts_entity_evidence() -> None:
    from backend import assistify_rag_server  # noqa: F401 - binds routing helpers to live server module
    from backend.retrieval.routing import RAG_NO_MATCH_RESPONSE, _apply_not_found_ux

    docs = [
        {
            "page_content": "The psychodynamic approach was founded by Sigmund Freud. Freud argued that unconscious forces can motivate behavior.",
            "metadata": {"page": 28, "section": "Psychodynamic Approach"},
        },
    ]

    answer = _apply_not_found_ux("What does the document say about Freud?", RAG_NO_MATCH_RESPONSE, docs)

    assert "couldn't find" not in answer.lower()
    assert "freud" in answer.lower()
    assert "psychodynamic" in answer.lower() or "unconscious" in answer.lower()


def test_document_summary_mixed_not_found_prefix_uses_fallback() -> None:
    from backend import assistify_rag_server  # noqa: F401 - binds routing helpers to live server module
    from backend.retrieval.routing import _apply_not_found_ux

    docs = [
        {
            "page_content": "Lesson 1 introduces psychology as the science of behavior and mental processes. Lesson 2 discusses major perspectives.",
            "metadata": {"section": "Lesson 1", "page": 2},
        }
    ]
    mixed = "Warmly, the detail about a chapter-by-chapter overview is not actually in any of the uploaded materials. However, I can summarize the key ideas."

    answer = _apply_not_found_ux("Provide a chapter-by-chapter overview of this document.", mixed, docs)

    assert "not in the uploaded materials" not in answer.lower()
    assert "lesson" in answer.lower() or "psychology" in answer.lower()


def test_document_summary_strips_mixed_refusal_preface_from_generated_answer() -> None:
    from backend import assistify_rag_server  # noqa: F401 - binds routing helpers to live server module
    from backend.retrieval.routing import _apply_not_found_ux

    mixed = (
        "Warmly, the detail about a chapter-by-chapter overview is not in the uploaded materials. "
        "However, based on the context provided, here's a summary: Chapter 1 introduces psychology."
    )

    answer = _apply_not_found_ux(
        "Provide a chapter-by-chapter overview of this document.",
        mixed,
        [{"page_content": "Lesson 1 introduces psychology.", "metadata": {"section": "Lesson 1"}}],
    )

    assert "not in the uploaded materials" not in answer.lower()
    assert "chapter 1 introduces psychology" in answer.lower() or "lesson 1" in answer.lower()


def test_ws_trace_docs_for_fallback_convert_selected_context() -> None:
    from backend.services.streaming_service import (
        _phase14_trace_docs_for_fallback,
        _strip_mixed_not_found_preface,
        _ws_generated_not_found_like,
    )

    docs = _phase14_trace_docs_for_fallback(
        {
            "phase14_selected_context": [
                {"preview": "Lesson 1 introduces psychology.", "page": 2, "section": "Lesson 1"}
            ]
        }
    )

    assert docs == [
        {
            "page_content": "Lesson 1 introduces psychology.",
            "metadata": {"source": None, "filename": None, "page": 2, "section": "Lesson 1"},
        }
    ]
    assert _ws_generated_not_found_like("the detail is not in the uploaded materials. However, here is a summary")
    cleaned = _strip_mixed_not_found_preface(
        "Warmly, the detail is not in the uploaded materials. However, based on the context provided, here is a summary."
    )
    assert "not in the uploaded materials" not in cleaned.lower()
    assert cleaned.startswith("Based on the context")


def test_chapter_overview_no_match_uses_summary_fallback_before_unanswerable_guard() -> None:
    from backend import assistify_rag_server  # noqa: F401 - binds routing helpers to live server module
    from backend.retrieval.routing import RAG_NO_MATCH_RESPONSE, _apply_not_found_ux

    docs = [
        {
            "page_content": "Lesson 1 introduces psychology as the science of behavior and mental processes. Lesson 9 covers research methods in psychology.",
            "metadata": {"section": "Lesson 1", "page": 2},
        }
    ]

    answer = _apply_not_found_ux("Provide a chapter-by-chapter overview of this document.", RAG_NO_MATCH_RESPONSE, docs)

    assert "not in the uploaded materials" not in answer.lower()
    assert "lesson" in answer.lower() or "psychology" in answer.lower()
