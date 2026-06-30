"""Unit tests for evidence fragment detection (Problem 1 gates)."""
from __future__ import annotations
import sys
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from backend.retrieval.routing import (
    _extract_evidence_value_sentence,
    _is_evidence_fragment_answer,
    _query_needs_explanatory_answer,
)
def test_query_needs_explanatory_answer():
    assert _query_needs_explanatory_answer("Why isn't the money available immediately?")
    assert _query_needs_explanatory_answer("When will I receive my tax forms?")
    assert _query_needs_explanatory_answer("What happens if I exceed my balance?")
    assert not _query_needs_explanatory_answer("What is the minimum balance for a Money Market account?")
def test_is_evidence_fragment_answer():
    q = "Why isn't the money from my mobile check deposit available immediately?"
    assert _is_evidence_fragment_answer(q, "1")
    assert _is_evidence_fragment_answer(q, "$0")
    assert not _is_evidence_fragment_answer(
        q,
        "Mobile check deposits may be held for 1-5 business days for verification.",
    )
def test_extract_evidence_value_sentence_range_not_single_digit():
    corpus = (
        "Mobile check deposit | Held 1-5 business days | $10,000 / day | Free\n"
        "New or larger deposits may be held 1-5 business days for verification."
    )
    q = "Why isn't the money from my mobile check deposit available immediately?"
    answer = _extract_evidence_value_sentence(q, corpus, require_value=True)
    assert answer is not None
    assert "1" in answer
    assert answer.strip() not in {"1.", "1"}
