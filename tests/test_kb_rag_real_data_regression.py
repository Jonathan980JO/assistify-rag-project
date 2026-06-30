"""Regression tests against REAL OCR-polluted KB chunks.

The chunk strings below are copied verbatim from the live ChromaDB collection
(see scripts/diag_kb_queries.py). They reproduce the exact pollution that broke
the FDIC and Everyday Checking answers:

  * glued prepositions: "perdepositor", "perownership"
  * section headings injected mid-sentence: "... per ownership 7. Deposit Insurance category ..."
  * prose + table header + data row concatenated on one physical line
  * decoy currency rows ("Limit (standard) | $100,000 / day", savings "$1,000")

These tests run CPU-only with no Chroma/GPU dependency, so they lock in the fix
permanently. If ingestion pollution returns, these fail fast.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.assistify_rag_server import (
    _extract_table_fact_answer,
    _shared_rag_final_answer_decision,
    _strip_repeated_kb_headings,
)
from backend.config_head import RAG_NO_MATCH_RESPONSE
from backend.pdf_ingestion_rag import _repair_split_words


def _doc(text: str, ci: int) -> dict:
    return {"page_content": text, "metadata": {"chunk_index": ci, "filename": "Meridian_Financial_Handbook.pdf"}}


# --- Verbatim polluted chunks retrieved for "What is the FDIC coverage limit?" ---
FDIC_DOCS = [
    _doc(
        "7. Deposit Insurance Eligible deposit balances are insured by the FDIC up to $250,000 "
        "perdepositor, perownership 7. Deposit Insurance category, through our partner bank. "
        "Investment products held with Meridian Invest are not 7. Deposit Insurance FDIC-insured, "
        "are not bank-guaranteed, and may lose value.",
        22,
    ),
    # Decoy: transfer-limit table whose "Limit (standard)" column + $100,000 row
    # previously hijacked the FDIC answer via the generic 'limit' focus token.
    _doc(
        "2. Funding & Transfers Transfer type | Typical timing | Limit (standard) | Fee "
        "2. Funding & Transfers ACH (bank-to-bank) | 1-3 business days | $25,000 / day | Free "
        "2. Funding & Transfers Domestic wire | Same business day | $100,000 / day | $15 outgoing",
        8,
    ),
]

# --- Verbatim polluted chunks retrieved for the Everyday Checking min-balance query ---
EVERYDAY_DOCS = [
    # Decoy Cards/Fraud chunk (previously surfaced as the answer).
    _doc(
        "3. Card Disputes & Unauthorized Transactions (cid:127) Confirmed fraud is refunded in full "
        "and a replacement card is issued. 4. Overdrafts & Returned Items Everyday Checking has no "
        "overdraft fees.",
        11,
    ),
    # Answer-bearing chunk: prose + header + Everyday row glued on one line.
    _doc(
        "1. About Meridian Financial Services through our mobile app and webbanking, with no physical "
        "branches and a 24/7 support team. 1. About Meridian Financial Services Meridian is not "
        "investment advice. Investment products are offered through Meridian Invest LLC, a 1. About "
        "Meridian Financial Services registered broker-dealer, and are not FDIC-insured, may lose "
        "value, and are not bank-guaranteed. Account | Monthly fee | Min. balance | Highlights "
        "Everyday Checking | $0 | $0 | No overdraft fees, early direct deposit, free ATM network",
        1,
    ),
    # Decoy savings table (Money Market has $1,000 min balance — must not be picked).
    _doc(
        "Account | Monthly fee | Min. balance | Highlights High-Yield Savings | $0 | $0 | Competitive "
        "APY Account | Monthly fee | Min. balance | Highlights Money Market | $0 | $1,000 | Tiered APY",
        2,
    ),
]

FDIC_QUERY = "What is the FDIC coverage limit?"
EVERYDAY_QUERY = "What is the minimum balance requirement for Everyday Checking?"


def test_heading_cleaner_repairs_glued_per_tokens() -> None:
    cleaned = _strip_repeated_kb_headings(FDIC_DOCS[0]["page_content"])
    assert "perdepositor" not in cleaned
    assert "perownership" not in cleaned
    assert "per depositor" in cleaned
    assert "per ownership" in cleaned


def test_heading_cleaner_removes_injected_numbered_heading() -> None:
    cleaned = _strip_repeated_kb_headings(FDIC_DOCS[0]["page_content"])
    # The injected mid-sentence copy must be gone so "category" rejoins "ownership".
    assert "per ownership category" in cleaned
    assert "per ownership 7. Deposit Insurance category" not in cleaned


def test_repair_split_words_keeps_per_separate() -> None:
    # The shared OCR repair must never glue the preposition "per" to the next word.
    assert _repair_split_words("$250,000 per depositor") == "$250,000 per depositor"


def test_fdic_extraction_returns_250k_not_decoy() -> None:
    answer = _extract_table_fact_answer(FDIC_QUERY, FDIC_DOCS)
    assert answer is not None
    assert "$250,000" in answer
    assert "per depositor" in answer.lower()
    assert "per ownership category" in answer.lower()
    assert "$100,000" not in answer  # transfer-limit decoy must not win


def test_fdic_final_decision() -> None:
    decision = _shared_rag_final_answer_decision(FDIC_QUERY, FDIC_DOCS, llm_text=None)
    answer = str(decision.get("answer") or "")
    assert decision.get("answer_type") == "fact_route_deterministic"
    assert answer != RAG_NO_MATCH_RESPONSE
    assert "$250,000 per depositor, per ownership category" in answer


def test_everyday_extraction_picks_correct_row() -> None:
    answer = _extract_table_fact_answer(EVERYDAY_QUERY, EVERYDAY_DOCS)
    assert answer is not None
    assert "$0 minimum balance" in answer.lower()
    assert "everyday checking" in answer.lower()
    # Must not leak prose-label garbage or the savings decoy value.
    assert "about meridian" not in answer.lower()
    assert "$1,000" not in answer
    assert "fraud" not in answer.lower()


def test_everyday_final_decision() -> None:
    decision = _shared_rag_final_answer_decision(EVERYDAY_QUERY, EVERYDAY_DOCS, llm_text=None)
    answer = str(decision.get("answer") or "")
    assert decision.get("answer_type") == "fact_route_deterministic"
    assert answer != RAG_NO_MATCH_RESPONSE
    assert "$0 minimum balance" in answer.lower()
    assert "everyday checking" in answer.lower()


if __name__ == "__main__":
    test_heading_cleaner_repairs_glued_per_tokens()
    test_heading_cleaner_removes_injected_numbered_heading()
    test_repair_split_words_keeps_per_separate()
    test_fdic_extraction_returns_250k_not_decoy()
    test_fdic_final_decision()
    test_everyday_extraction_picks_correct_row()
    test_everyday_final_decision()
    print("All real-data KB/RAG regression tests passed.")
