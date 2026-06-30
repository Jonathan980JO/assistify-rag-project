"""Router tests for conversational (non-document) user messages."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config_head import (
    CONVERSATIONAL_PRESENCE_EN,
    CONVERSATIONAL_REDIRECT_EN,
    CS_NO_MATCH_RESPONSE_EN,
    RAG_NO_MATCH_RESPONSE,
)
from backend.assistify_rag_server import (
    _apply_customer_support_tone,
    _assistant_meta_direct_answer,
    _build_grounded_explanations_for_items,
    _classify_assistant_meta_intent,
    _classify_smalltalk_intent,
    _finalize_user_visible_answer,
    _is_pure_smalltalk_query,
    _is_support_procedural_query,
    _rescue_support_procedural_from_docs,
    _smalltalk_response,
    classify_query_route,
)

_PASSWORD_DOCS = [
    {
        "page_content": (
            "To reset your password, follow these steps: 1) Go to the login page "
            "and click 'Forgot Password' 2) Enter your registered email address."
        ),
        "metadata": {"id": "password_reset"},
    }
]

_FAQ_CONTAMINATION_DOCS = [
    {
        "page_content": (
            "Q: How do I reset my password? A: Go to login and click Forgot Password. "
            "Q: How do I add a teammate? A: Open Settings and click Invite Member. "
            "Q: Can I use SSO? A: Enable SSO under Security settings."
        ),
        "metadata": {"id": "support_faq"},
    }
]


def test_classify_query_route_conversational() -> None:
    cases = [
        ("tell me are you getting my messages", "conversational_ack"),
        ("are you getting me ??", "conversational_ack"),
        ("are you getting me", "conversational_ack"),
        ("do you get me", "conversational_ack"),
        ("Can you listen to me?", "conversational_ack"),
        ("can you hear me", "conversational_ack"),
        ("are you there", "conversational_ack"),
        ("why are you only having to find the document", "assistant_meta"),
        ("Why do you keep saying not found in the document", "assistant_meta"),
        ("So tell me how to reset the password", "document_question"),
        ("tell me how to reset my password", "document_question"),
        ("How do I reset my password?", "document_question"),
        ("Tell me how can I change my password?", "document_question"),
    ]
    for query, expected_route in cases:
        assert classify_query_route(query) == expected_route, f"{query!r} -> {classify_query_route(query)!r}"


def test_finalize_maps_sentinel_for_conversational() -> None:
    out = _finalize_user_visible_answer("can you hear me", RAG_NO_MATCH_RESPONSE)
    assert out != RAG_NO_MATCH_RESPONSE
    assert "here to help" in out.lower() or "support" in out.lower()


def test_finalize_maps_sentinel_for_getting_me() -> None:
    out = _finalize_user_visible_answer("are you getting me", RAG_NO_MATCH_RESPONSE)
    assert out != RAG_NO_MATCH_RESPONSE
    assert out == CONVERSATIONAL_PRESENCE_EN


def test_finalize_cs_tone_for_document_miss() -> None:
    out = _finalize_user_visible_answer(
        "What is quantum physics?",
        RAG_NO_MATCH_RESPONSE,
    )
    assert out != RAG_NO_MATCH_RESPONSE
    assert out == CS_NO_MATCH_RESPONSE_EN
    assert "Not found in the document." not in out
    assert "your document" not in out.lower()
    assert "our help materials" in out.lower()


def test_cs_no_match_response_is_kb_generic() -> None:
    lowered = CS_NO_MATCH_RESPONSE_EN.lower()
    assert "our help materials" in lowered
    assert "your document" not in lowered
    assert "orders" not in lowered
    assert "returns" not in lowered


def test_apply_customer_support_tone_list_intro() -> None:
    answer = "- Set objectives\n- Analyze alternatives\n- Select course of action"
    out = _apply_customer_support_tone(
        "What are the steps in the planning process?",
        answer,
    )
    assert "Here are the steps from our help materials:" in out
    assert "- Set objectives" in out


def test_apply_customer_support_tone_maps_not_found() -> None:
    out = _apply_customer_support_tone(
        "What is the capital of France?",
        RAG_NO_MATCH_RESPONSE,
    )
    assert out == CS_NO_MATCH_RESPONSE_EN


def test_grounded_explanations_undirected_explain_more_not_repetitive() -> None:
    items = [
        "Set objectives",
        "boundaries",
        "evaluated",
        "Analyze alternatives",
        "very important",
    ]
    context_docs = [
        {
            "page_content": (
                "The planning process includes the following steps: "
                "1) Set objectives 2) Analyze alternatives 3) Select course of action."
            ),
        }
    ]
    out = _build_grounded_explanations_for_items(
        "What are the steps in the planning process?",
        items,
        context_docs,
        user_text="explain more",
        targeted_item=None,
    )
    assert out
    assert "which in the document is associated" not in out.lower()
    assert out.count("Regarding") <= 1


def test_finalize_maps_sentinel_for_behavior_complaint() -> None:
    out = _finalize_user_visible_answer(
        "why are you only having to find the document",
        RAG_NO_MATCH_RESPONSE,
    )
    assert out != RAG_NO_MATCH_RESPONSE
    assert "knowledge base" in out.lower() or "documents" in out.lower()


def test_conversational_redirect_constant() -> None:
    assert "help" in CONVERSATIONAL_REDIRECT_EN.lower()
    assert "password reset" in CONVERSATIONAL_REDIRECT_EN.lower()


def test_support_procedural_voice_phrasing() -> None:
    assert _is_support_procedural_query("So tell me how to reset the password")
    assert _is_support_procedural_query("tell me how to reset my password")
    assert _is_support_procedural_query("Tell me how can I change my password?")
    assert not _is_support_procedural_query("What are the steps in the planning process?")
    assert not _is_support_procedural_query("What are the six Ms of management?")


def test_support_procedural_rescue_from_docs() -> None:
    out = _finalize_user_visible_answer(
        "So tell me how to reset the password",
        RAG_NO_MATCH_RESPONSE,
        retrieved_docs=_PASSWORD_DOCS,
    )
    assert out != RAG_NO_MATCH_RESPONSE
    assert "forgot password" in out.lower()
    assert _rescue_support_procedural_from_docs("So tell me how to reset the password", _PASSWORD_DOCS)


def test_support_procedural_rescue_avoids_faq_contamination() -> None:
    out = _rescue_support_procedural_from_docs("How do I reset my password?", _FAQ_CONTAMINATION_DOCS)
    assert out
    assert "forgot password" in out.lower()
    assert "invite member" not in out.lower()
    assert "sso" not in out.lower()


def test_password_change_phrasing_rescued_from_docs() -> None:
    out = _finalize_user_visible_answer(
        "Tell me how can I change my password?",
        RAG_NO_MATCH_RESPONSE,
        retrieved_docs=_PASSWORD_DOCS,
    )
    assert out != RAG_NO_MATCH_RESPONSE
    assert "Not found in the document." not in out
    assert "forgot password" in out.lower()


def test_password_change_no_docs_uses_cs_not_blunt() -> None:
    out = _finalize_user_visible_answer(
        "Tell me how can I change my password?",
        RAG_NO_MATCH_RESPONSE,
    )
    assert out != RAG_NO_MATCH_RESPONSE
    assert out == CS_NO_MATCH_RESPONSE_EN
    assert "Not found in the document." not in out


def test_assistant_meta_capability_questions() -> None:
    cases = [
        ("What are your capabilities?", "capabilities"),
        ("What can I ask you?", "ask_scope"),
        ("Who are you?", "identity"),
    ]
    for query, expected_intent in cases:
        assert _classify_assistant_meta_intent(query) == expected_intent
        answer = _assistant_meta_direct_answer(query)
        assert answer
        assert "Not found in the document." not in answer


def test_thank_you_smalltalk_routing() -> None:
    thanks_cases = [
        "Okay, thank you.",
        "ok thank you",
        "thanks",
        "okay thanks",
        "much appreciated",
    ]
    for query in thanks_cases:
        assert classify_query_route(query) == "smalltalk", f"{query!r} -> {classify_query_route(query)!r}"
        assert _classify_smalltalk_intent(query) == "thanks", query
        response = _smalltalk_response(query)
        assert "welcome" in response.lower(), response

    assert classify_query_route("thanks, what is logistic regression?") == "document_question"
    assert not _is_pure_smalltalk_query("thanks, what is logistic regression?")


def test_finalize_maps_sentinel_for_thank_you() -> None:
    out = _finalize_user_visible_answer("Okay, thank you.", RAG_NO_MATCH_RESPONSE)
    assert out != RAG_NO_MATCH_RESPONSE
    assert out != CS_NO_MATCH_RESPONSE_EN
    assert "welcome" in out.lower()


def test_repeated_letter_greeting_variants() -> None:
    variants = ["hi", "hii", "hiii", "hello", "helloo", "hey", "heyy", "thanks", "thankss", "ok", "okk"]
    for query in variants:
        assert classify_query_route(query) == "smalltalk", query
        assert _is_pure_smalltalk_query(query), query
        response = _smalltalk_response(query)
        assert response
        assert "Not found in the document." not in response


if __name__ == "__main__":
    test_classify_query_route_conversational()
    test_finalize_maps_sentinel_for_conversational()
    test_finalize_maps_sentinel_for_getting_me()
    test_finalize_cs_tone_for_document_miss()
    test_cs_no_match_response_is_kb_generic()
    test_apply_customer_support_tone_list_intro()
    test_apply_customer_support_tone_maps_not_found()
    test_grounded_explanations_undirected_explain_more_not_repetitive()
    test_finalize_maps_sentinel_for_behavior_complaint()
    test_conversational_redirect_constant()
    test_support_procedural_voice_phrasing()
    test_support_procedural_rescue_from_docs()
    test_password_change_phrasing_rescued_from_docs()
    test_password_change_no_docs_uses_cs_not_blunt()
    test_assistant_meta_capability_questions()
    test_thank_you_smalltalk_routing()
    test_finalize_maps_sentinel_for_thank_you()
    test_repeated_letter_greeting_variants()
    print("All conversational router tests passed.")
