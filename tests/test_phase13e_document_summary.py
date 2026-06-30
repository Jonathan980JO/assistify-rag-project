from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from backend.assistify_rag_server import (  # noqa: E402
    _classify_query_family_v2,
    _has_sufficient_context,
    _is_document_summary_query,
)


def test_document_summary_context_sufficiency_uses_chunks_and_text_not_keywords():
    query = "What is this document about?"
    context = (
        "The source introduces a broad subject, its main themes, and the "
        "relationships among several ideas across the uploaded material."
    )

    assert _classify_query_family_v2(query) == "document_summary"
    assert _has_sufficient_context(query, context, relevant_chunks=3) is True


def test_non_summary_context_sufficiency_still_requires_keyword_overlap():
    query = "What policy controls account access?"
    context = (
        "The source introduces a broad subject, its main themes, and the "
        "relationships among several ideas across the uploaded material."
    )

    assert _classify_query_family_v2(query) != "document_summary"
    assert _has_sufficient_context(query, context, relevant_chunks=3) is False


def test_document_summary_discuss_grammar_accepts_inflections():
    queries = [
        "What does this document discuss?",
        "What does this document discusses?",
        "What is this document discussing?",
        "What topics are discussed in this document?",
    ]

    for query in queries:
        assert _is_document_summary_query(query) is True, query
        assert _classify_query_family_v2(query) == "document_summary", query


def test_targeted_discussed_query_is_not_document_summary():
    query = "What are the major schools of a field discussed in this document?"

    assert _is_document_summary_query(query) is False
    assert _classify_query_family_v2(query) != "document_summary"


def test_document_summary_is_excluded_from_definition_pipelines():
    service_paths = [
        ROOT / "backend" / "services" / "rag_service.py",
        ROOT / "backend" / "services" / "streaming_service.py",
    ]

    for path in service_paths:
        source = path.read_text(encoding="utf-8")
        assert 'family_v2_current != "document_summary"' in source
        assert 'if family_v2_current != "document_summary":' in source


def test_streaming_memory_rewrite_excludes_document_summary():
    source = (ROOT / "backend" / "services" / "streaming_service.py").read_text(encoding="utf-8")

    assert '_classify_query_family_v2(text) != "document_summary"' in source
    assert 'and _classify_query_family_v2(text) != "document_summary"' in source
