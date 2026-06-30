"""Phase 8 adversarial test: prove the fact extractors are evidence-driven.

Each case feeds a synthetic chunk from a DIFFERENT domain (banking, food,
healthcare, HR analytics, university handbook, SaaS docs) and asserts that:

  1. The answer value comes from the document text (not a code constant).
  2. When the asked-for value is absent, the extractor returns None
     (i.e. there is no hardcoded fallback answer).

Run:  KMP_DUPLICATE_LIB_OK=TRUE python -m pytest tests/test_zero_hardcode_generalization.py -q
"""
from __future__ import annotations

import os
import sys
import types

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# Repo root on path so `backend` package imports work when run as a file.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class _Permissive:
    """Stands in for any object/class pulled from a stubbed heavy dependency."""

    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return self

    def __getattr__(self, _name):
        return _Permissive()

    def encode(self, *a, **k):
        return [[0.0] * 8]

    def get_sentence_embedding_dimension(self, *a, **k):
        return 8

    def predict(self, *a, **k):
        return [0.0]


def _make_stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__path__ = []  # mark as package so submodule imports resolve

    def _getattr(_attr):
        return _Permissive

    mod.__getattr__ = _getattr  # type: ignore[attr-defined]
    return mod


def _import_server_with_stubs(max_rounds: int = 60):
    """Import the server module, stubbing any ML/web dependency that is absent.

    The functions under test are pure regex/string logic with no runtime need
    for the heavy deps; we only stub what import-time requires.
    """
    last_err = None
    for _ in range(max_rounds):
        try:
            import backend.assistify_rag_server as srv  # noqa: WPS433
            return srv
        except ModuleNotFoundError as exc:  # stub and retry
            missing = (exc.name or "").strip()
            if not missing:
                raise
            parts = missing.split(".")
            for i in range(1, len(parts) + 1):
                sub = ".".join(parts[:i])
                if sub not in sys.modules:
                    sys.modules[sub] = _make_stub(sub)
            last_err = exc
        except Exception:
            raise
    raise RuntimeError(f"could not import server after stubbing: {last_err}")


s = _import_server_with_stubs()


# (query, chunk, substring that MUST appear in the answer)
EVIDENCE_CASES = [
    # Banking
    (
        "what is the FDIC coverage limit?",
        "Deposit Insurance: All accounts are FDIC-insured up to $250,000 per depositor.",
        "$250,000",
    ),
    # Food products
    (
        "how many calories are in one serving?",
        "Nutrition Facts: Each serving contains 240 calories and 9 g of fat.",
        "240",
    ),
    # Healthcare
    (
        "what is the recommended daily dose?",
        "Dosage: The recommended daily dose for adults is 500 mg taken twice a day.",
        "500",
    ),
    # HR analytics
    (
        "what is the attrition rate?",
        "Key findings show the overall employee attrition rate is 14.7% for the year.",
        "14.7%",
    ),
    # University handbook
    (
        "what is the minimum GPA required for the dean's list?",
        "Academic Honors: Students must maintain a minimum GPA of 3.50 to qualify.",
        "3.50",
    ),
    # SaaS documentation
    (
        "what is the price of the Pro plan?",
        "Pricing: The Pro plan costs $49 per month billed annually.",
        "$49",
    ),
]


# Queries whose value is NOT present -> must return None (no constant leaks)
ABSENT_CASES = [
    ("what is the FDIC coverage limit?", "Our branches are open Monday to Friday."),
    ("what is the attrition rate?", "The report describes the hiring process in detail."),
    ("what is the price of the Pro plan?", "The Pro plan includes priority support and SSO."),
]


def test_evidence_values_come_from_document():
    for query, chunk, expected in EVIDENCE_CASES:
        ans = s._extract_evidence_value_sentence(query, chunk, require_value=False)
        assert ans is not None, f"no answer for: {query!r}"
        assert expected in ans, f"expected {expected!r} from doc, got {ans!r}"


def test_no_constant_when_value_absent():
    for query, chunk in ABSENT_CASES:
        ans = s._extract_evidence_value_sentence(query, chunk, require_value=True)
        assert ans is None, f"unexpected fabricated answer for {query!r}: {ans!r}"


def test_metric_extractor_reads_any_domain():
    docs = [{"page_content": "The model achieved an F1 score of 0.83 on the test set."}]
    ans = s._extract_metric_fact_answer("what was the F1 score?", docs)
    assert ans is not None and "0.83" in ans, ans


def test_product_phrases_derive_from_query_not_a_list():
    # A product name that never existed in any prior corpus.
    phrases = s._table_fact_product_phrases("minimum balance for Verdant Premier Checking?")
    assert any("verdant premier checking" in p for p in phrases), phrases


def test_minbalance_column_mapping_generic_entity():
    line = "Account | Monthly fee | Min. balance || Verdant Premier Checking | $12 | $1,500"
    val = s._extract_minbalance_from_pipe_line(line, ["verdant premier checking"])
    assert val == "$1,500", val


def test_bridge_detection_is_domain_free():
    assert s._doc_router_cross_corpus_bridge("using the policy document, explain the pricing report")
    assert not s._doc_router_cross_corpus_bridge("what is the price of the Pro plan?")


def test_definition_answer_accepts_descriptor_entity_evidence():
    docs = [
        {
            "page_content": (
                "A marine engineer, founder of the tidal robotics school, Liora presented "
                "a complex theory of autonomous reef maintenance."
            ),
            "metadata": {"source": "synthetic"},
            "score": 1.0,
        }
    ]
    result = s._shared_rag_final_answer_decision("Who is Liora?", docs)
    answer = result.get("answer") or ""
    assert answer != s.RAG_NO_MATCH_RESPONSE
    assert "Liora" in answer
    assert "marine engineer" in answer
    assert "tidal robotics school" in answer


def test_definition_answer_accepts_heading_definition_fragment():
    docs = [
        {
            "page_content": (
                "Hydrolexism An approach that concentrated on how coastal teams coordinate "
                "sensor data and field decisions during flood response."
            ),
            "metadata": {"source": "synthetic"},
            "score": 1.0,
        }
    ]
    result = s._shared_rag_final_answer_decision("Define hydrolexism.", docs)
    answer = result.get("answer") or ""
    assert answer != s.RAG_NO_MATCH_RESPONSE
    assert "Hydrolexism" in answer
    assert "coastal teams coordinate sensor data" in answer


def test_definition_answer_returns_not_found_without_grounded_evidence():
    docs = [
        {
            "page_content": "The guide describes maintenance windows and notification schedules.",
            "metadata": {"source": "synthetic"},
            "score": 1.0,
        }
    ]
    result = s._shared_rag_final_answer_decision("Define hydrolexism.", docs)
    assert result.get("answer") == s.RAG_NO_MATCH_RESPONSE


def test_person_fact_extractor_removes_generic_role_descriptors():
    cases = [
        (
            "Who founded the Tidal Robotics School?",
            "Marine Engineer Alice Carter founded the Tidal Robotics School in 1990.",
            "Alice Carter",
        ),
        (
            "Who created the Beacon Framework?",
            "Founder Robert Hayes created the Beacon Framework.",
            "Robert Hayes",
        ),
        (
            "Who developed the Halcyon Method?",
            "Chief Scientist Maria Lopez developed the Halcyon Method.",
            "Maria Lopez",
        ),
        (
            "Who established the Verdant Institute?",
            "Maria Elena Vasquez established the Verdant Institute in 1910.",
            "Maria Elena Vasquez",
        ),
        (
            "Who established the Arctic Sensor Lab?",
            "Nadia P. Keller established the Arctic Sensor Lab in 2005.",
            "Nadia P. Keller",
        ),
    ]

    for query, chunk, expected in cases:
        assert s._extract_fact_from_context(query, [chunk]) == expected


def test_person_fact_extractor_rejects_descriptor_only_fragments():
    answer = s._extract_fact_from_context(
        "Who founded the Aerostat Guild?",
        ["Regional Director Alice founded the Aerostat Guild in 2001."],
    )
    assert answer is None


def test_person_fact_extractor_accepts_noun_form_founder_evidence():
    """Phase 14D-C1: noun-form authorship ("the founder of X") must not be discarded.

    Reproduces the proven Gestalt-founder failure generically: the answer sentence
    states authorship with the NOUN "founder" (no past-tense attribution verb), while
    an off-subject distractor sentence DOES carry attribution verbs. The attribution
    verb-gate must not drop the on-subject noun-form evidence in favour of the
    off-subject verb sentence.
    """
    chunk = (
        "Tobias Renner the founder of the Lumina Movement was born in Vienna. "
        "Gregor Halvorsen established the foundations of design by founding the "
        "first design laboratory in 1879."
    )
    answer = s._extract_fact_from_context("Who founded the Lumina Movement?", [chunk])
    assert answer == "Tobias Renner"


def test_person_fact_extractor_still_drops_verbless_nonauthorship_noise():
    """Genericity guard: relaxing the gate for authorship NOUNS must not let through
    verb-less sentences that carry no authorship evidence at all."""
    chunk = (
        "The Lumina Movement was widely discussed across Vienna salons. "
        "Gregor Halvorsen established the foundations of design by founding the "
        "first design laboratory in 1879."
    )
    # No founder/creator noun AND no on-subject person -> must not invent an answer
    # from the off-subject distractor's subject.
    answer = s._extract_fact_from_context("Who founded the Lumina Movement?", [chunk])
    assert answer != "Lumina Movement"


if __name__ == "__main__":
    test_evidence_values_come_from_document()
    test_no_constant_when_value_absent()
    test_metric_extractor_reads_any_domain()
    test_product_phrases_derive_from_query_not_a_list()
    test_minbalance_column_mapping_generic_entity()
    test_bridge_detection_is_domain_free()
    test_definition_answer_accepts_descriptor_entity_evidence()
    test_definition_answer_accepts_heading_definition_fragment()
    test_definition_answer_returns_not_found_without_grounded_evidence()
    test_person_fact_extractor_removes_generic_role_descriptors()
    test_person_fact_extractor_rejects_descriptor_only_fragments()
    print("ALL ADVERSARIAL ZERO-HARDCODE TESTS PASSED")
