"""Tests for hybrid RAG query preparation."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.rag_query_prep import (
    PreparedQuery,
    is_pure_conversational_only,
    needs_llm_query_prep,
    prepare_query_for_rag,
    strip_conversational_prefix,
)


def test_strip_hello_prefix() -> None:
    assert strip_conversational_prefix("hello what is gasoline") == "what is gasoline"
    assert strip_conversational_prefix("Hello, what is gasoline?") == "what is gasoline?"


def test_strip_thanks_prefix() -> None:
    assert strip_conversational_prefix("thanks, what is logistic regression?") == (
        "what is logistic regression?"
    )


def test_strip_hello_only() -> None:
    assert strip_conversational_prefix("hello") == ""


def test_strip_repeated_letter_greetings() -> None:
    for variant in ("hii", "hiii", "helloo", "heyy", "thankss", "okk"):
        assert strip_conversational_prefix(variant) == "", variant


def test_pure_conversational_hello() -> None:
    assert is_pure_conversational_only("hello", strip_conversational_prefix("hello"))


def test_not_pure_when_question_remains() -> None:
    stripped = strip_conversational_prefix("hello what is gasoline")
    with patch(
        "backend.assistify_rag_server._is_pure_smalltalk_query",
        return_value=False,
    ):
        assert not is_pure_conversational_only("hello what is gasoline", stripped)


def test_prepare_hello_smalltalk() -> None:
    prepared = asyncio.run(prepare_query_for_rag("hello"))
    assert prepared.direct_response is not None
    assert prepared.rag_query == ""
    assert prepared.prep_source == "rules"


def test_prepare_hello_question_rules() -> None:
    with patch(
        "backend.rag_query_prep._apply_spelling_correction",
        side_effect=lambda t: t,
    ):
        prepared = asyncio.run(prepare_query_for_rag("hello what is gasoline"))
    assert prepared.direct_response is None
    assert "gasoline" in prepared.rag_query.lower()
    assert "hello" not in prepared.rag_query.lower()


def test_prepare_llm_fallback_on_invalid_json() -> None:
    with patch(
        "backend.rag_query_prep.needs_llm_query_prep",
        return_value=True,
    ), patch(
        "backend.rag_query_prep.llm_normalize_rag_query",
        new=AsyncMock(return_value=None),
    ), patch(
        "backend.rag_query_prep._apply_spelling_correction",
        side_effect=lambda t: t,
    ):
        prepared = asyncio.run(prepare_query_for_rag("hello, also what is gasoline"))
    assert prepared.direct_response is None
    assert "gasoline" in prepared.rag_query.lower()


def test_prepare_llm_smalltalk_action() -> None:
    llm_result = PreparedQuery(
        original="hello, also, thanks",
        rag_query="",
        direct_response="Hello! How can I help?",
        prep_source="llm",
    )
    with patch(
        "backend.rag_query_prep.is_pure_conversational_only",
        return_value=False,
    ), patch(
        "backend.rag_query_prep.needs_llm_query_prep",
        return_value=True,
    ), patch(
        "backend.rag_query_prep.llm_normalize_rag_query",
        new=AsyncMock(return_value=llm_result),
    ):
        prepared = asyncio.run(prepare_query_for_rag("hello, also, thanks"))
    assert prepared.direct_response == "Hello! How can I help?"
    assert prepared.prep_source == "llm"


def test_gazoline_corrected_to_gasoline() -> None:
    from backend.assistify_rag_server import _lightweight_spelling_correction

    seed = [{"page_content": "gasoline engine fuel powertrain", "text": "gasoline engine"}]
    corrected = _lightweight_spelling_correction("what is gazoline", seed_docs=seed)
    assert "gasoline" in corrected.lower()
    assert "gazoline" not in corrected.lower()


def test_gasoline_unchanged() -> None:
    from backend.assistify_rag_server import _lightweight_spelling_correction

    seed = [{"page_content": "gasoline engine fuel", "text": "gasoline"}]
    corrected = _lightweight_spelling_correction("what is gasoline", seed_docs=seed)
    assert corrected.lower() == "what is gasoline"


def test_needs_llm_on_comma_mix() -> None:
    stripped = strip_conversational_prefix("hello, also what is gasoline")
    assert needs_llm_query_prep("hello, also what is gasoline", stripped)
