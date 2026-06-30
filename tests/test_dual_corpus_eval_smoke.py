"""Unit tests for dual-corpus eval rubric scorer (no live LLM)."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _safe_preview(text: str, limit: int = 80) -> str:
    raw = str(text or "")[:limit].replace("\n", " ")
    return raw.encode("ascii", "replace").decode("ascii")


def _load_eval_module():
    import sys
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import eval_dual_corpus_protocol as mod
    return mod


def test_phase1_attrition_pass():
    mod = _load_eval_module()
    case = next(c for c in mod.EVAL_CASES if c.test_id == 1)
    answer = "The attrition rate is 16.12%. Sales department has the highest at 20.63%."
    score = mod.score_answer(case, answer)
    assert score["status"] == "pass"


def test_phase5_warm_refusal_pass():
    mod = _load_eval_module()
    case = next(c for c in mod.EVAL_CASES if c.test_id == 14)
    answer = (
        "The IBM HR report mentions logistic regression and ROC-AUC metrics, "
        "but the uploaded materials do not include the exact mathematical formula or coefficient weights."
    )
    score = mod.score_answer(case, answer)
    assert score["status"] == "pass"


def test_phase5_invented_coefficients_fail():
    mod = _load_eval_module()
    case = next(c for c in mod.EVAL_CASES if c.test_id == 14)
    answer = "The formula is logit(p) = β0 + β1*OverTime + β2*Age with β1 = 0.42"
    score = mod.score_answer(case, answer)
    assert score["status"] == "fail"


def test_phase5_dsm_code_fail():
    mod = _load_eval_module()
    case = next(c for c in mod.EVAL_CASES if c.test_id == 16)
    answer = "The DSM-5-TR code is F43.8 for Employee Burnout Syndrome."
    score = mod.score_answer(case, answer)
    assert score["status"] == "fail"


def test_cross_corpus_bridge_detector():
    from backend.assistify_rag_server import _doc_router_cross_corpus_bridge

    q = (
        "The HR report identifies JobSatisfaction. Using the Health Psychology chapter "
        "from the Psychology textbook, explain stress."
    )
    assert _doc_router_cross_corpus_bridge(q) is True


def test_active_source_filter_fallback():
    from backend.assistify_rag_server import (
        _filter_doc_dicts_to_active_sources,
        _set_active_sources,
    )
    from backend.pdf_ingestion_rag import VectorStore

    vs = VectorStore()
    hits = vs.search("16.12 attrition", top_k=2, return_dicts=True, enable_rerank=False, distance_threshold=1.2)
    docs = [{"metadata": (h or {}).get("metadata") or {}, "page_content": (h or {}).get("text") or ""} for h in (hits or [])]
    assert docs, "expected retrieval hits for attrition probe"
    _set_active_sources(["doc_stale_does_not_exist"])
    kept = _filter_doc_dicts_to_active_sources(docs)
    assert kept, "stale active_sources must not empty retrieval docs"
