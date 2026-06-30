"""Regression tests for RAG chunking and table/heading heuristics."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from backend.rag_chunk_heuristics import looks_table_or_heading_like_chunk as _looks_table_or_heading_like_chunk
from backend.knowledge_base import chunk_and_add_document


def _chunk_texts_from_doc(text: str, *, doc_id: str = "test_doc", metadata: dict | None = None) -> list[str]:
    mock_collection = MagicMock()
    mock_collection.name = "test_rag_chunk_fixes"
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = np.array([[0.1] * 8])

    with patch("backend.knowledge_base.client") as mock_client, patch(
        "backend.knowledge_base.get_or_create_collection",
        return_value=mock_collection,
    ), patch("backend.knowledge_base.embedder", mock_embedder):
        mock_client.get_or_create_collection.return_value = mock_collection
        details = chunk_and_add_document(
            doc_id,
            text,
            metadata=metadata or {"file_ext": "pdf"},
            return_details=True,
            target_collection_name="test_rag_chunk_fixes",
        )
    return list(details.get("chunk_texts") or [])


# --- Bug 1: colon-led definition bullets must not be penalized ---

COLON_DEFINITION_NOT_TABLE = [
    "Brake Fluid: Hygroscopic (absorbs moisture over time), replacement every 2-3 years.",
    "Coolant (Antifreeze): A mixture of water and ethylene glycol that prevents freezing in cold climates.",
    "Engine Oil: 5W-30 viscosity is recommended for most passenger vehicles in moderate climates.",
    "ATF: Automatic transmission fluid lubricates gears and must meet manufacturer specifications.",
    "Power Steering Fluid: Hydraulic fluid that assists steering and should be checked monthly.",
    (
        "Battery Electrolyte: Sulfuric acid solution that stores chemical energy and requires "
        "periodic inspection of fluid levels in non-sealed batteries."
    ),
]

COLON_DEFINITION_SHOULD_BE_TABLE_LIKE = [
    "Chapter 3: Engine Systems",
    "Section 2.1: Overview",
    "INTRODUCTION TO VEHICLES",
    "Table 4: Fluid Specifications",
    "[TABLE DATA]\nOil Type | Viscosity | API Rating\n5W-30 | Standard | SN\nSynthetic | High | SP",
    "Name          Role          Year\nTaylor        Management    1911\nFayol         Admin         1916",
    "a | b | c",
    "1. Scientific Management Taylor\n2. Administrative Theory Fayol\n3. Bureaucracy Weber",
    "Figure 2: Engine cross-section diagram",
    "Classification\nType A\nType B\nType C\nType D\nType E\nType F\nType G\nType H",
]


@pytest.mark.parametrize("text", COLON_DEFINITION_NOT_TABLE)
def test_colon_definition_bullets_not_table_like(text: str):
    assert _looks_table_or_heading_like_chunk(text) is False


@pytest.mark.parametrize("text", COLON_DEFINITION_SHOULD_BE_TABLE_LIKE)
def test_true_headings_and_tables_still_table_like(text: str):
    assert _looks_table_or_heading_like_chunk(text) is True


def test_colon_definition_multi_bullet_chunk_not_table_like():
    chunk = "\n".join(COLON_DEFINITION_NOT_TABLE[:4])
    assert _looks_table_or_heading_like_chunk(chunk) is False


# --- Bug 2: prose and [TABLE DATA] must never share a chunk ---

def test_table_data_forces_chunk_boundary():
    prose_token = "VISCOSITYPROSE"
    prose = " ".join([prose_token] * 250)
    table = "[TABLE DATA]\nOil Type | Viscosity | Notes\n5W-30 | Standard | API SN"
    text = f"[PAGE_START: 1]\n{prose}\n\n{table}\n[PAGE_END: 1]"

    chunks = _chunk_texts_from_doc(text)
    assert chunks, "expected at least one chunk"

    mixed = [
        c for c in chunks
        if prose_token in c and "[TABLE DATA]" in c
    ]
    assert mixed == [], f"prose/table mixed in chunks: {mixed[:2]}"


def test_colon_bullet_before_table_stays_retrievable():
    bullet = (
        "Brake Fluid: Hygroscopic (absorbs moisture over time), replacement every 2-3 years."
    )
    table = "[TABLE DATA]\nFluid | Interval\nBrake Fluid | 2-3 years"
    text = f"[PAGE_START: 1]\n{bullet}\n\n{table}\n[PAGE_END: 1]"

    chunks = _chunk_texts_from_doc(text)
    bullet_chunks = [c for c in chunks if "Brake Fluid: Hygroscopic" in c]
    assert bullet_chunks, "colon-led bullet chunk missing"
    assert _looks_table_or_heading_like_chunk(bullet_chunks[0]) is False
    assert all("[TABLE DATA]" not in c for c in bullet_chunks)


# --- Bug 3: section headings must NOT be injected/repeated inside chunk text ---

def test_heading_not_repeated_inside_chunk():
    # A numbered section heading followed by a multi-line body must never have the
    # heading text spliced between sentences or repeated once per line. This is
    # the corruption signature that produced
    # "1. About Meridian Financial Services" between every sentence.
    heading = "1. About Meridian Financial Services"
    body_lines = [
        "Meridian Financial Services is a digital-first bank operating across the United States.",
        "Deposit accounts are held with our partner bank and are FDIC-insured up to $250,000.",
        "We serve individuals and small businesses through our mobile app and web banking.",
    ]
    text = "[PAGE_START: 1]\n" + heading + "\n" + "\n".join(body_lines) + "\n[PAGE_END: 1]"

    chunks = _chunk_texts_from_doc(text)
    joined = "\n".join(chunks)
    assert "Meridian Financial Services is a digital-first bank" in joined
    for c in chunks:
        assert heading not in c, f"section heading injected into chunk text: {c!r}"
        assert "United States. 1. About" not in c, f"heading spliced mid-text: {c!r}"


def test_table_header_kept_once_with_rows():
    # A pipe table header must appear exactly once and stay attached to its rows
    # (not dropped, not repeated before every row).
    text = (
        "[PAGE_START: 1]\n"
        "2. Deposit Accounts\n"
        "Account | Monthly fee | Min. balance | Highlights\n"
        "Everyday Checking | $0 | $0 | No overdraft fees, early direct deposit\n"
        "High-Yield Savings | $0 | $0 | Competitive APY\n"
        "Money Market | $0 | $1,000 | Tiered APY, check-writing\n"
        "[PAGE_END: 1]"
    )
    chunks = _chunk_texts_from_doc(text)
    table_chunks = [c for c in chunks if "Money Market" in c]
    assert table_chunks, "table chunk missing"
    c = table_chunks[0]
    assert c.count("Account | Monthly fee | Min. balance | Highlights") == 1
    assert "Money Market | $0 | $1,000" in c
    assert "Everyday Checking | $0 | $0" in c


def test_bullet_list_under_heading_keeps_full_sentences():
    heading = "Maintenance Fluids"
    bullets = "\n".join(COLON_DEFINITION_NOT_TABLE[:4])
    text = f"[PAGE_START: 1]\n{heading}\n\n{bullets}\n[PAGE_END: 1]"

    chunks = _chunk_texts_from_doc(text)
    joined = "\n".join(chunks)
    assert "Brake Fluid: Hygroscopic" in joined
    assert "Coolant (Antifreeze): A mixture" in joined
    assert not any(
        c.strip() == heading and len(c.split()) <= 4
        for c in chunks
    ), "heading-only fragment chunk detected"


# --- Phase 14E: FAQ pair selection, multi-entity compare, table preservation ---

from backend.pdf_ingestion_rag import VectorStore
from backend.retrieval.routing import (
    _compare_entities_from_query,
    _compose_grounded_generation_answer,
    _extract_best_faq_answer,
    _extract_comparison_table_rows,
    _is_comparison_table_evidence,
    _parse_faq_pairs,
    _rescue_support_procedural_from_docs,
)

_MULTI_FAQ_CHUNK = (
    "Q: How do I reset my password? A: Go to login and click Forgot Password, then follow the email link. "
    "Q: How do I add a teammate? A: Open Settings, choose Team, and click Invite Member. "
    "Q: Can I use SSO? A: Yes, enable SSO under Security settings for your organization. "
    "Q: How do I transfer ownership? A: Only the current owner can transfer ownership from Account settings."
)

_MULTI_FAQ_DOCS = [{"page_content": _MULTI_FAQ_CHUNK, "metadata": {"id": "support_faq"}}]


def test_phase14e_parse_faq_pairs_finds_all_entries() -> None:
    pairs = _parse_faq_pairs(_MULTI_FAQ_CHUNK)
    assert len(pairs) == 4


def test_phase14e_extract_best_faq_answer_selects_matching_pair_only() -> None:
    answer = _extract_best_faq_answer("How do I reset my password?", _MULTI_FAQ_CHUNK)
    assert answer
    assert "forgot password" in answer.lower()
    assert "invite member" not in answer.lower()


def test_phase14e_rescue_support_procedural_avoids_faq_contamination() -> None:
    out = _rescue_support_procedural_from_docs("How do I reset my password?", _MULTI_FAQ_DOCS)
    assert out
    assert "forgot password" in out.lower()
    assert "invite member" not in out.lower()


def test_phase14e_compose_grounded_generation_uses_faq_pair() -> None:
    out = _compose_grounded_generation_answer("Can I use SSO?", _MULTI_FAQ_CHUNK)
    assert out and "sso" in out.lower()


def test_phase14e_compare_entities_two_way() -> None:
    assert _compare_entities_from_query("Compare Starter and Growth plans") == ["starter", "growth"]


def test_phase14e_compare_entities_three_way_no_merge() -> None:
    assert _compare_entities_from_query("Compare Growth, Business, and Enterprise plans") == [
        "growth",
        "business",
        "enterprise",
    ]


def test_phase14e_compare_entities_vm_families() -> None:
    entities = _compare_entities_from_query("Compare General and GPU VM families")
    assert len(entities) == 2
    assert entities[0] == "general"
    assert "gpu" in entities[1]


def test_phase14e_compare_entities_four_way() -> None:
    assert _compare_entities_from_query("Compare Alpha, Beta, Gamma, and Delta tiers") == [
        "alpha",
        "beta",
        "gamma",
        "delta",
    ]


def test_phase14e_heading_dominated_exempts_table_chunks() -> None:
    table_text = "[TABLE DATA]\nFeature | Basic | Pro\nStorage | 10 | 100\nSupport | Email | Phone\n"
    assert VectorStore._low_quality_reason(table_text, {"chunk_role": "table"}) is None


def test_phase14e_comparison_table_evidence_detection() -> None:
    assert _is_comparison_table_evidence("Plan | SSO | HIPAA\nStarter | No | No\nGrowth | Yes | No\n")


def test_phase14e_extract_comparison_table_rows_per_entity() -> None:
    docs = [{"page_content": "Plan | SSO | HIPAA\nStarter | No | No\nGrowth | Yes | No\n", "metadata": {}}]
    rows = _extract_comparison_table_rows(docs, ["starter", "growth"])
    assert "starter" in rows
    assert "growth" in rows
    assert "yes" in rows["growth"].lower()


def test_phase14e_decontaminate_faq_answer() -> None:
    from backend.retrieval.routing import _decontaminate_faq_answer

    blob = (
        "Q: How do I transfer ownership? A: Only the current owner can transfer ownership from Account settings. "
        "Q: I forgot my password or lost my phone - how do I get back in? A: Use Forgot Password on the login screen."
    )
    out = _decontaminate_faq_answer("How do I transfer ownership?", blob)
    assert out
    assert "transfer ownership" in out.lower()
    assert "forgot password" not in out.lower()
    docs = [{"page_content": "Plan | SSO | HIPAA\nStarter | No | No\nGrowth | Yes | No\n", "metadata": {}}]
    rows = _extract_comparison_table_rows(docs, ["starter", "growth"])
    assert "starter" in rows
    assert "growth" in rows
    assert "yes" in rows["growth"].lower()


# --- Phase 14F: attribute lookup routing and table cell extraction ---

from backend.retrieval.generation import _resolve_grounded_answer_route
from backend.retrieval.routing import (
    _classify_query_family_v2,
    _compare_all_class_tokens,
    _discover_compare_entities_from_tables,
    _extract_table_cell_answer,
    _format_structured_table_comparison,
    _is_attribute_lookup_query,
    _is_table_header_token,
    _parse_pipe_table_rows,
)

_PHASE14F_PLAN_TABLE = (
    "Plan | Monthly fee | Named TAM | SSO | HIPAA\n"
    "Growth | $99 | No | Yes | No\n"
    "Business | $249 | No | Yes | Yes\n"
    "Enterprise | Custom | Yes | Yes | Yes\n"
)
_PHASE14F_PLAN_DOCS = [{"page_content": _PHASE14F_PLAN_TABLE, "metadata": {"chunk_role": "table"}}]
_PHASE14F_VM_TABLE = (
    "Family | Memory | Best for\n"
    "General | 16 GB | Databases\n"
    "GPU | 80 GB | Machine Learning\n"
    "Memory-Optimized | 256 GB | Large datasets\n"
)
_PHASE14F_VM_DOCS = [{"page_content": _PHASE14F_VM_TABLE, "metadata": {"chunk_role": "table"}}]


def test_phase14f_attribute_lookup_classifier() -> None:
    query = "What is the support response time for Business?"
    assert _is_attribute_lookup_query(query)
    assert _classify_query_family_v2(query) == "attribute_lookup"
    assert _resolve_grounded_answer_route(query) == "attribute"


def test_phase14f_reverse_table_lookup_named_tam() -> None:
    answer = _extract_table_cell_answer("Which plan includes a named TAM?", _PHASE14F_PLAN_DOCS)
    assert answer and answer.lower() == "enterprise"
    assert not _is_table_header_token(answer)


def test_phase14f_structured_comparison_no_synthesis() -> None:
    entities = _compare_entities_from_query("Compare Growth and Enterprise plans")
    out = _format_structured_table_comparison(_PHASE14F_PLAN_DOCS, entities)
    assert out and "Growth" in out and "Enterprise" in out
    assert "SYNTHESIS:" not in out


def test_phase14f_compare_all_discovery() -> None:
    assert _compare_all_class_tokens("Compare all plans") == ["plans"]
    entities = _discover_compare_entities_from_tables(_PHASE14F_PLAN_DOCS, ["plans"])
    assert "growth" in entities and "enterprise" in entities


def test_phase14f_superlative_vm_memory() -> None:
    answer = _extract_table_cell_answer("Which VM family has the most memory?", _PHASE14F_VM_DOCS)
    assert answer and "memory" in answer.lower()


def test_phase14f_parse_pipe_table_rows() -> None:
    rows = _parse_pipe_table_rows(_PHASE14F_PLAN_TABLE)
    assert len(rows) == 4
    assert rows[0][0].lower() == "plan"


def test_phase14f_person_identity_beats_theory() -> None:
    import backend.assistify_rag_server as srv
    from backend.retrieval import routing as routing_mod
    from backend.retrieval.routing import _extract_definition_route_answer

    previous = routing_mod.S
    routing_mod.S = srv
    try:
        docs = [
            {
                "page_content": (
                    "Freud's idea that libido is the prime impulse of life shaped psychoanalytic theory. "
                    "Sigmund Freud was an Austrian neurologist and the founder of psychoanalysis."
                ),
                "metadata": {"id": "psychology_chunk"},
            }
        ]
        answer = _extract_definition_route_answer("Who is Freud?", docs)
    finally:
        routing_mod.S = previous
    assert answer
    assert "freud" in answer.lower()
    assert "libido" not in answer.lower()


# --- Phase 14G: attribute reliability, FAQ, spelling, person guard ---

from backend.retrieval.routing import (
    _extract_best_faq_answer,
    _extract_best_faq_answer_from_docs,
    _format_reverse_lookup_labels,
    _is_compact_table_answer,
    _is_person_identity_query,
    _lightweight_spelling_correction,
    _table_cell_is_affirmative,
)

_PHASE14G_PLAN_TABLE = (
    "Plan | Monthly fee | Named TAM | Audit logs | SSO\n"
    "Starter | $0 | No | No | No\n"
    "Business | $499 | No | Yes | Yes\n"
    "Enterprise | Custom | Yes | Yes | Yes\n"
)
_PHASE14G_PLAN_DOCS = [{"page_content": _PHASE14G_PLAN_TABLE, "metadata": {"chunk_role": "table"}}]


def test_phase14g_reverse_lookup_multiple_plans() -> None:
    answer = _extract_table_cell_answer("Which plan includes audit logs?", _PHASE14G_PLAN_DOCS)
    assert answer
    low = answer.lower()
    assert "business" in low and "enterprise" in low


def test_phase14g_forward_lookup_monthly_fee() -> None:
    answer = _extract_table_cell_answer("What is the monthly fee for Business?", _PHASE14G_PLAN_DOCS)
    assert answer
    assert "$499" in answer or "499" in answer
    assert "|" not in answer


def test_phase14g_compact_table_answer_rejects_table_blob() -> None:
    blob = "Plan | Fee\nGrowth | $99\nBusiness | $499"
    assert not _is_compact_table_answer(blob)
    assert _is_compact_table_answer("$99")


def test_phase14g_faq_pair_margin_selects_ownership() -> None:
    blob = (
        "Q: How do I reset my password? A: Click Forgot Password on the login page. "
        "Q: How do I transfer ownership? A: Open Settings, choose Transfer Ownership, and confirm."
    )
    answer = _extract_best_faq_answer("How do I transfer ownership?", blob) or ""
    assert "transfer" in answer.lower()
    assert "forgot password" not in answer.lower()


def test_phase14g_spelling_preserves_provide() -> None:
    query = "What uptime guarantee does Nimbus provide?"
    corrected = _lightweight_spelling_correction(query)
    assert "provider" not in corrected.lower()
    assert "provide" in corrected.lower()


def test_phase14g_person_identity_query_detects_ceo() -> None:
    assert _is_person_identity_query("Who is the CEO of Nimbus?")


def test_phase14g_table_cell_affirmative_rejects_plan_name() -> None:
    assert not _table_cell_is_affirmative("Starter")
    assert _table_cell_is_affirmative("Yes")


def test_phase14g_format_reverse_lookup_labels() -> None:
    assert _format_reverse_lookup_labels(["Business", "Enterprise"]) == "Business and Enterprise"


_GLUE_PLAN_TABLE = (
    "Plan | Monthly platform fee | Support response | Named TAM "
    "Starter | $0 | Email, next business day | No "
    "Growth | $99 | Chat, < 4 business hours | No "
    "Business | $499 | 24 / 7 chat + phone, < 1 hour | No "
    "Enterprise | Custom | 24 / 7, < 15 min, named TAM | Yes"
)
_GLUE_VM_TABLE = (
    "2.1 Virtual machine families Family | Best for | v CPU range | memory range | On-dem and price "
    "General (g-series) | Web apps, APIs, dev / test | 1 - 64 | 1 - 256 GB | from $0.0085 / v CPU-hr "
    "Compute (c-series) | Batch, encoding, simulation | 2 - 96 | 4 - 192 GB | from $0.0110 / v CPU-hr "
    "Memory (m-series) | Databases, caches, analytics | 2 - 128 | 16 - 1024 GB | from $0.0140 / "
    "GPU (x-series) | ML training, inference, render | 8 - 96 | 64 - 1152 GB | from $1.95 / GPU-hr"
)


def test_phase14g_glued_plan_monthly_fee() -> None:
    docs = [{"page_content": _GLUE_PLAN_TABLE, "metadata": {"chunk_role": "table"}}]
    answer = _extract_table_cell_answer("What is the monthly fee for Growth?", docs)
    assert answer
    assert "99" in answer


def test_phase14g_glued_plan_support_response() -> None:
    docs = [{"page_content": _GLUE_PLAN_TABLE, "metadata": {"chunk_role": "table"}}]
    answer = _extract_table_cell_answer("What is the support response time for Business?", docs)
    assert answer
    low = answer.lower()
    assert "hour" in low or "1" in low


def test_phase14g_glued_vm_superlative_memory() -> None:
    docs = [{"page_content": _GLUE_VM_TABLE, "metadata": {"chunk_role": "table"}}]
    answer = _extract_table_cell_answer("Which VM family has the most memory?", docs)
    assert answer
    low = answer.lower()
    assert "gpu" in low or "1152" in low
    assert answer.count("|") < 2


def test_phase14g_glued_vm_superlative_vcpu() -> None:
    docs = [{"page_content": _GLUE_VM_TABLE, "metadata": {"chunk_role": "table"}}]
    answer = _extract_table_cell_answer("Which VM family has the largest vCPU range?", docs)
    assert answer
    low = answer.lower()
    assert "memory" in low or "128" in low


def test_phase14g_vm_compare_entity_normalization() -> None:
    from backend.retrieval.routing import _compare_entities_from_query, _format_structured_table_comparison

    entities = _compare_entities_from_query("Compare General and GPU VM families")
    assert "general" in entities
    assert any("gpu" in entity for entity in entities)
    docs = [{"page_content": _GLUE_VM_TABLE, "metadata": {"chunk_role": "table"}}]
    out = _format_structured_table_comparison(docs, entities)
    assert out
    assert "General" in out or "general" in out.lower()
    assert "GPU" in out or "gpu" in out.lower()


def test_phase14g_process_sentence_onboarding() -> None:
    from backend.retrieval.routing import _extract_process_sentence_answer, _rescue_support_procedural_from_docs

    docs = [
        {
            "page_content": (
                "Onboarding begins when you create an account. The setup process includes verifying "
                "your email, choosing a plan, and configuring your first project in a guided workflow."
            ),
            "metadata": {},
        }
    ]
    answer = _extract_process_sentence_answer("How does onboarding work?", docs) or ""
    assert answer
    low = answer.lower()
    assert any(tok in low for tok in ("onboard", "setup", "step", "process", "workflow"))
    rescued = _rescue_support_procedural_from_docs("How does onboarding work?", docs)
    assert rescued


def test_phase14g_person_not_found_regression() -> None:
    import backend.assistify_rag_server as srv
    from backend.retrieval import routing as routing_mod
    from backend.retrieval.routing import _has_person_evidence_in_docs, _is_person_identity_query

    assert _is_person_identity_query("Who is the CEO of Nimbus?")
    docs = [{"page_content": "Enterprise plans include custom pricing and named TAM support.", "metadata": {}}]
    previous = routing_mod.S
    routing_mod.S = srv
    try:
        assert not _has_person_evidence_in_docs("Who is the CEO of Nimbus?", docs)
    finally:
        routing_mod.S = previous


# --- Phase 14H: final remaining answer-quality fixes ---

from backend.retrieval.routing import (
    _accept_attribute_route_answer,
    _collapse_attribute_table_answer,
    _extract_attribute_route_answer,
    _extract_definition_route_answer,
    _has_exact_who_person_evidence,
    _is_evidence_fragment_answer,
    _rescue_support_procedural_from_docs,
)

_GLUE_PLAN_TABLE_SSO = (
    "Plan | Monthly platform fee | Support response | Named TAM | SSO "
    "Starter | $0 | Email, next business day | No | No "
    "Growth | $99 | Chat, < 4 business hours | No | No "
    "Business | $499 | 24 / 7 chat + phone, < 1 hour | No | Yes "
    "Enterprise | Custom | 24 / 7, < 15 min, named TAM | Yes | Yes"
)
_GLUE_SSO_DOCS = [{"page_content": _GLUE_PLAN_TABLE_SSO, "metadata": {"chunk_role": "table"}}]


def test_phase14h_who_is_jung_surname_identity() -> None:
    docs = [
        {
            "page_content": "Jung was a Swiss psychiatrist who developed analytical psychology.",
            "metadata": {"id": "psychology_chunk"},
        }
    ]
    assert _has_exact_who_person_evidence("Who is Jung?", docs)
    answer = _extract_definition_route_answer("Who is Jung?", docs)
    assert answer
    assert "jung" in answer.lower()
    assert "psychiatrist" in answer.lower() or "swiss" in answer.lower()


def test_phase14h_what_is_psychoanalysis() -> None:
    docs = [
        {
            "page_content": (
                "Psychoanalysis is a clinical method focused on unconscious processes, "
                "developed by Sigmund Freud."
            ),
            "metadata": {"id": "psychology_chunk"},
        }
    ]
    answer = _extract_definition_route_answer("What is psychoanalysis?", docs)
    assert answer
    low = answer.lower()
    assert "psychoanalysis" in low
    assert any(tok in low for tok in ("clinical", "method", "unconscious", "process"))


def test_phase14h_what_is_analytical_psychology() -> None:
    docs = [
        {
            "page_content": (
                "Analytical psychology is a therapeutic approach emphasizing the collective unconscious, "
                "developed by Carl Jung."
            ),
            "metadata": {"id": "psychology_chunk"},
        }
    ]
    answer = _extract_definition_route_answer("What is analytical psychology?", docs)
    assert answer
    low = answer.lower()
    assert "analytical" in low and "psychology" in low


def test_phase14h_sso_reverse_lookup_accept_path() -> None:
    docs = [{"page_content": _PHASE14G_PLAN_TABLE, "metadata": {"chunk_role": "table"}}]
    answer = _extract_attribute_route_answer("Which plans support SSO?", docs)
    assert answer
    low = answer.lower()
    assert "business" in low and "enterprise" in low
    assert "|" not in answer


def test_phase14h_monthly_fee_accept_path() -> None:
    docs = [{"page_content": _PHASE14G_PLAN_TABLE, "metadata": {"chunk_role": "table"}}]
    accepted = _accept_attribute_route_answer("What is the monthly fee for Business?", "$499")
    assert accepted == "$499"
    assert not _is_evidence_fragment_answer("What is the monthly fee for Business?", "$499")
    answer = _extract_attribute_route_answer("What is the monthly fee for Business?", docs)
    assert answer
    assert "499" in answer


def test_phase14h_collapse_table_blob_to_plan_labels() -> None:
    blob = _PHASE14G_PLAN_TABLE
    collapsed = _collapse_attribute_table_answer("Which plans support SSO?", blob, _GLUE_SSO_DOCS)
    assert collapsed
    low = collapsed.lower()
    assert "business" in low and "enterprise" in low


def test_phase14h_refund_policy_rescue() -> None:
    docs = [
        {
            "page_content": (
                "Q: What refund options are available? "
                "A: Unused prepaid credits may be refunded within 30 days of purchase as account credit."
            ),
            "metadata": {},
        }
    ]
    answer = _rescue_support_procedural_from_docs("What is the refund policy?", docs)
    assert answer
    assert len(answer) >= 20
    low = answer.lower()
    assert "refund" in low or "credit" in low


def test_phase14h_elon_musk_still_not_found() -> None:
    import backend.assistify_rag_server as srv
    from backend.retrieval import routing as routing_mod

    docs = [{"page_content": "Enterprise plans include custom pricing.", "metadata": {}}]
    previous = routing_mod.S
    routing_mod.S = srv
    try:
        assert not _has_exact_who_person_evidence("Who is Elon Musk?", docs)
    finally:
        routing_mod.S = previous
