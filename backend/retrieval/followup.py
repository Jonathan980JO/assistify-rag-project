"""Follow-up / Arabic / memory-rewrite retrieval helpers.

Extracted verbatim from ``assistify_rag_server.py`` during Phase 8H-1. These
functions detect follow-up/clarification intent, resolve Arabic ordinal and
anaphoric references, rewrite prior answers from memory, and ground follow-up
explanations against previously retrieved chunks.

This module is a leaf in the retrieval package: it never imports
``assistify_rag_server``. Functions that need shared server state (the in-memory
answer/list state, the live RAG handle) or engine functions that have not yet
been extracted reach them through ``S``, the server module injected by
``bind_server`` at registration time. ``logger`` is likewise the server logger.
Behavior is identical to the monolith original.
"""
from __future__ import annotations

import math
import re
import re as _re_followup
import time
from typing import Optional

from backend.config_head import *  # noqa: F401,F403 - mirrors the server module
from backend.utils.text import _dedup_preserve_order, _is_arabic_text

# Injected server module (set by bind_server). Holds shared mutable state and
# engine functions referenced as S.<name> below.
S = None


def bind_server(server) -> None:
    """Bind the live server module so extracted helpers can reach shared state."""
    global S
    S = server

_FOLLOWUP_STATE_TTL = 1800  # seconds (30 min)

_FOLLOWUP_MAX_QUERY_LEN = 140

_FOLLOWUP_CHUNK_CHAR_BUDGET = 1800

_FOLLOWUP_KEEP_TOP_K = 3

_FOLLOWUP_SAVED_CHUNK_CHAR_LIMIT = 1800

_FOLLOWUP_GROUND_RATIO_MIN = 0.20

_FOLLOWUP_PATTERNS = [
    _re_followup.compile(p, _re_followup.IGNORECASE) for p in [
        r"^\s*what\s+do\s+you\s+mean\b",
        r"^\s*what\s+are\s+you\s+saying\b",
        r"^\s*what\s+does\s+that\s+mean\b",
        r"^\s*explain\s+(more|further|that|it|again|please|this)\b",
        r"^\s*explain\s*[?.!]?\s*$",
        r"^\s*(can|could)\s+you\s+explain\b",
        r"^\s*tell\s+me\s+more\b",
        r"^\s*say\s+more\b",
        r"^\s*go\s+on\s*[?.!]?\s*$",
        r"^\s*continue\s*[?.!]?\s*$",
        r"^\s*more\s+(detail|details|info|information)\b",
        r"^\s*(give|show)\s+me\s+more\b",
        r"^\s*elaborate\b",
        r"^\s*clarify\b",
        r"^\s*simplify\b",
        r"^\s*make\s+it\s+(simpler|easier|clearer|shorter)\b",
        r"^\s*in\s+simpler\s+(terms|words)\b",
        r"^\s*rephrase\b",
        r"^\s*reword\b",
        r"^\s*break\s+(it|this|that)\s+down\b",
        r"^\s*(can|could)\s+you\s+(simplify|clarify|rephrase|elaborate|explain)\b",
        r"^\s*i\s+don'?t\s+(get|understand)\s*(it|that|this)?\s*[?.!]?\s*$",
    ]
]

_FOLLOWUP_CONTEXT_PATTERNS = [
    _re_followup.compile(p, _re_followup.IGNORECASE) for p in [
        # "explain Money", "explain what does Money means in this process",
        # "explain the second one", etc. (any "explain ..." form)
        r"^\s*explain\b",
        # "what does Money mean", "what does that mean", "what does X means"
        r"^\s*what\s+does\s+.+\bmean(s|ing)?\b",
        # "what about Money", "what about that"
        r"^\s*what\s+about\s+\S+",
        # "how about Money"
        r"^\s*how\s+about\s+\S+",
        # "tell me about Money", "tell me more about Money"
        r"^\s*tell\s+me\s+(more\s+)?about\s+\S+",
        # "simplify that", "rephrase that", "clarify that", "elaborate that"
        r"^\s*(simplify|rephrase|clarify|elaborate|reword)\s+\S+",
        # "and Money?", "and the second?"  — short anaphoric pivot
        r"^\s*and\s+\S+\s*\??\s*$",
        # P11A: ordinal-reference clarifications targeting a previously
        # listed item, e.g. "what is the second one?", "how does it
        # connect to the last one?", "tell me about the third item".
        # Strictly generic (no domain words). Requires prior state
        # because this is a CONTEXT pattern.
        r"\b(?:the\s+)?(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last|previous|next|final|\d{1,2}(?:st|nd|rd|th))\s+(?:one|item|element|thing|point|step|function|part|option|reason|principle|stage|phase|category|type|kind)\b",
    ]
]

_FOLLOWUP_NEW_QUESTION_PATTERNS = [
    _re_followup.compile(p, _re_followup.IGNORECASE) for p in [
        r"^\s*(what|which)\s+(is|are|was|were)\b",
        r"^\s*(how|why|when|where|who)\b",
        r"^\s*(list|name|enumerate)\b",
        r"^\s*(define|definition\s+of)\b",
        r"^\s*give\s+me\s+(a\s+)?(list|definition|example)\b",
        r"^\s*(?:ما|ماذا|من)\s+(?:هو|هي|هى|هم|تكون|يكون|يعني|تعني)\b",
        r"^\s*(?:لماذا|كيف|متى|اين|أين|هل)\b",
        r"^\s*(?:اذكر|عدد|عرّف|عرف|تعريف|قارن|استخرج)\b",
    ]
]

_FOLLOWUP_SHORT_WORD_LIMIT = 7

_AR_FOLLOWUP_STRONG_RE = _re_followup.compile(
    r"^\s*(?:طيب\s+|طيّب\s+|حسنا\s+|حسناً\s+|حسنًا\s+|اوكي\s+|أوك\s+|اوك\s+|ok\s+)?"
    r"(?:"
    r"(?:اشرح|وضح|بسط|بسّط|فسر|فسّر)(?:ها|ه|هما|هم)"
    r"|(?:اشرح|وضح|بسط|بسّط|فسر|فسّر)\s+(?:ذلك|ذاك|هذا|هذه|الأمر|النقطة|إجابتك|اجابتك|كلامك|قولك)"
    r"|(?:اشرح|وضح|بسط|بسّط|فسر|فسّر)\s+(?:أكثر|اكثر|بشكل\s+أوضح|بشكل\s+اوضح|ببساطة|ببساطه)"
    r"|ماذا\s+(?:تقصد|تعني)"
    r"|ما\s+(?:قصدك|تعنيه|الذي\s+تعني|الذي\s+تقصد|تعني\s+بذلك)"
    r")"
    r"(?:\s|[؟?.!،,؛;]|$)",
    _re_followup.IGNORECASE,
)

_AR_FOLLOWUP_CONTEXT_RE = _re_followup.compile(
    r"^\s*و?\s*(?:ما|وما)\s+علاقت(?:ها|ه|هما|هم)\b"
    r"|^\s*و?\s*كيف\s+(?:ترتبط|يرتبط|ترتبطين|يرتبطان)\b"
    r"|^\s*و?\s*(?:ما|وما)\s+الفرق\s+بين(?:هم|هما|ها)\b"
    r"|^\s*و?\s*كيف\s+(?:تختلف|يختلف)\b"
    r"|\b(?:الأولى|الاولى|الثانية|الثاني|الثالثة|الثالث|الرابعة|الرابع|الخامسة|الخامس|السادسة|السادس|السابعة|السابع|الثامنة|الثامن|التاسعة|التاسع|العاشرة|الأخيرة|الاخيرة|الأخير|الاخير|السابقة|السابق|التالية|التالي)\b",
    _re_followup.IGNORECASE,
)

_AR_ANAPHOR_RE = _re_followup.compile(
    r"\b(?:هذا|هذه|ذلك|ذاك|تلك|هؤلاء|هم|هما|هي|هو|دي|ده|عليه|عليها|عنه|عنها|بينهم|بينهما)\b",
    _re_followup.IGNORECASE,
)

def _is_arabic_followup_strong(text: str) -> bool:
    return bool(_AR_FOLLOWUP_STRONG_RE.search(str(text or "")))

def _is_arabic_followup_context(text: str) -> bool:
    return bool(_AR_FOLLOWUP_CONTEXT_RE.search(str(text or "")))

_AR_ORDINAL_TO_INDEX: dict[str, int] = {
    "الأولى": 1, "الاولى": 1, "الأول": 1, "الاول": 1,
    "الثانية": 2, "الثاني": 2,
    "الثالثة": 3, "الثالث": 3,
    "الرابعة": 4, "الرابع": 4,
    "الخامسة": 5, "الخامس": 5,
    "السادسة": 6, "السادس": 6,
    "السابعة": 7, "السابع": 7,
    "الثامنة": 8, "الثامن": 8,
    "التاسعة": 9, "التاسع": 9,
    "العاشرة": 10, "العاشر": 10,
    "الأخيرة": -1, "الاخيرة": -1, "الأخير": -1, "الاخير": -1,
    "النهائية": -1, "النهائي": -1,
}

def _resolve_arabic_ordinal_target_from_items(target_text: str, items: list[str]) -> str:
    target = re.sub(r"\s+", " ", str(target_text or "").strip(" ـ؟?.،,؛;"))
    if not target or not items:
        return ""
    for word, idx in _AR_ORDINAL_TO_INDEX.items():
        if re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", target):
            try:
                return str(items[-1] if idx == -1 else items[idx - 1]).strip(" .;:،؛-")
            except IndexError:
                return ""
    return ""

def _build_arabic_item_explain_query(target_item: str, state: dict, list_state: dict) -> str:
    target_clean = str(target_item or "").strip(" .;:،؛-")
    if not target_clean:
        return ""
    context_query = re.sub(
        r"\s+",
        " ",
        str(
            state.get("list_query")
            or list_state.get("query")
            or state.get("query")
            or ""
        ).strip(),
    )
    if context_query and target_clean.lower() not in context_query.lower():
        if re.search(r"[A-Za-z]", target_clean):
            return f"Explain {target_clean} in context: {context_query}"
        return f"اشرح {target_clean} ضمن سياق: {context_query}؟"
    return f"اشرح {target_clean}؟"

def _maybe_resolve_arabic_followup_reference(text: str, connection_id) -> tuple[str, str]:
    """Rewrite Arabic follow-ups with pronoun/ordinal references into an
    explicit, grounded query using the last saved answer state.

    Returns ("", "") when no resolution applies. The rewritten query
    reuses entities/items already pulled from previously retrieved
    evidence — no domain word lists, no fabricated content. The caller
    should send the rewritten query through normal RAG retrieval.
    """
    if not text or not connection_id:
        return "", ""
    raw_text = str(text or "")
    if not re.search(r"[\u0600-\u06FF]", raw_text):
        return "", ""
    raw_text = re.sub(r"\s+", " ", raw_text).strip()
    if not raw_text:
        return "", ""
    state = S.last_answer_state.get(connection_id) or S._last_good_answer_state.get(connection_id)
    if not state:
        return "", ""
    try:
        if (time.time() - float(state.get("ts", 0))) > _FOLLOWUP_STATE_TTL:
            state = S._last_good_answer_state.get(connection_id)
    except Exception:
        state = S._last_good_answer_state.get(connection_id)
    if not state:
        return "", ""

    entities_raw = list(state.get("last_grounded_entities") or [])
    list_state = S._last_list_state.get(connection_id) or {}
    items = [str(it).strip() for it in (state.get("items") or list_state.get("items") or []) if str(it).strip()]

    primary = ""
    for ent in entities_raw:
        ent_clean = str(ent or "").strip(" .;:،؛-")
        if ent_clean:
            primary = ent_clean
            break
    if not primary:
        try:
            concept = _extract_definition_concept_from_query_surface(state.get("query") or "")
        except Exception:
            concept = ""
        if concept:
            primary = concept
    if not primary:
        try:
            primary = _extract_arabic_concept_from_query_surface(state.get("query") or "")
        except Exception:
            primary = ""
    if not primary:
        try:
            primary = _extract_focus_concept_from_explain_query_surface(state.get("query") or "")
        except Exception:
            primary = ""
    if not primary:
        try:
            primary = _extract_focus_concept_from_explanatory_query_surface(state.get("query") or "")
        except Exception:
            primary = ""

    # 1) "(و)ما علاقتها/علاقته/علاقتهما/علاقتهم بـ X؟" -> relationship.
    m = re.match(
        r"^و?\s*(?:ما|وما)\s+علاقت(?:ها|ه|هما|هم)\s+ب(?:ـ\s*)?(.+?)\s*[؟?.!]*\s*$",
        raw_text,
    )
    if m and primary:
        target = m.group(1).strip(" ـ؟?.،,؛;")
        target = _resolve_arabic_ordinal_target_from_items(target, items) or target
        if target and target != primary:
            rewritten = f"ما العلاقة بين {primary} و{target}؟"
            return rewritten, "ar_relation_pronoun"

    # 2) "كيف ترتبط/يرتبط بـ X؟"
    m = re.match(
        r"^و?\s*كيف\s+(?:ترتبط|يرتبط|ترتبطين|يرتبطان)\s+ب(?:ـ\s*)?(.+?)\s*[؟?.!]*\s*$",
        raw_text,
    )
    if m and primary:
        target = m.group(1).strip(" ـ؟?.،,؛;")
        target = _resolve_arabic_ordinal_target_from_items(target, items) or target
        if target and target != primary:
            return f"ما العلاقة بين {primary} و{target}؟", "ar_relation_verb"

    # 3) Arabic ordinal references into the previous list.
    found_idx = None
    found_word = ""
    for word, idx in _AR_ORDINAL_TO_INDEX.items():
        if re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", raw_text):
            found_idx = idx
            found_word = word
            break
    if found_idx is not None and items:
        try:
            target_item = items[-1] if found_idx == -1 else items[found_idx - 1]
        except IndexError:
            target_item = ""
        if target_item:
            target_clean = str(target_item).strip(" .;:،؛-")
            # 3a) "اشرح/وضح/فسر/بسط <ordinal>"
            if re.search(r"^\s*(?:اشرح|وضح|فسر|فسّر|بسط|بسّط|عرف|عرّف)\b", raw_text):
                return _build_arabic_item_explain_query(target_clean, state, list_state), "ar_ordinal_explain"
            # 3b) relationship to ordinal: "كيف ترتبط بالأخيرة" / "وكيف ترتبط بالأخيرة"
            if re.search(r"(?:علاقت(?:ها|ه|هما|هم)|ترتبط|يرتبط)", raw_text) and primary and primary != target_clean:
                return f"ما العلاقة بين {primary} و{target_clean}؟", "ar_ordinal_relation"
            # 3c) "وما الفرق بينها وبين <ord>" simple fall-through
            if re.search(r"الفرق", raw_text) and primary and primary != target_clean:
                return f"ما الفرق بين {primary} و{target_clean}؟", "ar_ordinal_difference"
            # 3d) generic standalone ordinal request -> explain that item
            if re.fullmatch(r"\s*و?\s*" + re.escape(found_word) + r"\s*[؟?.!]*\s*", raw_text):
                return f"اشرح {target_clean}؟", "ar_ordinal_default"

    # 4) "(و)ما الفرق بينهم/بينهما؟" -> compare prior entities/items.
    if re.search(r"(?:^|\s)(?:ما|وما)\s+الفرق\b", raw_text) and re.search(r"بين(?:هم|هما|ها)", raw_text):
        pair: list[str] = []
        for ent in entities_raw:
            ent_clean = str(ent or "").strip(" .;:،؛-")
            if ent_clean and ent_clean not in pair:
                pair.append(ent_clean)
            if len(pair) == 2:
                break
        if len(pair) < 2:
            for it in items:
                it_clean = str(it).strip(" .;:،؛-")
                if it_clean and it_clean not in pair:
                    pair.append(it_clean)
                if len(pair) == 2:
                    break
        if len(pair) == 2:
            return f"ما الفرق بين {pair[0]} و{pair[1]}؟", "ar_diff_pronoun"

    return "", ""

def _mark_arabic_resolved_followup(connection_id, query: str, reason: str) -> None:
    if not connection_id or not query:
        return
    S._ar_resolved_followup_queries[connection_id] = {
        "query": re.sub(r"\s+", " ", str(query or "").strip()),
        "reason": str(reason or ""),
        "ts": time.time(),
    }

def _is_marked_arabic_resolved_followup(connection_id, query: str) -> bool:
    if not connection_id or not query:
        return False
    marker = S._ar_resolved_followup_queries.get(connection_id)
    if not marker:
        return False
    try:
        if (time.time() - float(marker.get("ts", 0))) > _FOLLOWUP_STATE_TTL:
            S._ar_resolved_followup_queries.pop(connection_id, None)
            return False
    except Exception:
        return False
    marker_query = re.sub(r"\s+", " ", str(marker.get("query") or "").strip())
    query_text = re.sub(r"\s+", " ", str(query or "").strip())
    return bool(marker_query and query_text and marker_query == query_text)

def _get_marked_arabic_resolved_followup_reason(connection_id, query: str) -> str:
    if not _is_marked_arabic_resolved_followup(connection_id, query):
        return ""
    marker = S._ar_resolved_followup_queries.get(connection_id) or {}
    return str(marker.get("reason") or "")

def _resolve_and_mark_arabic_followup_for_ws(text: str, connection_id, stage: str = "") -> tuple[str, str]:
    if _is_memory_rewrite_query(text):
        return text, ""
    try:
        resolved, reason = _maybe_resolve_arabic_followup_reference(text, connection_id)
        if resolved and resolved != text:
            S.logger.info(
                "[AR FOLLOWUP MEMORY] resolved_query=%s reason=%s original=%s",
                resolved[:200],
                reason,
                (text or "")[:200],
            )
            _mark_arabic_resolved_followup(connection_id, resolved, reason)
            return resolved, reason
    except Exception:
        S.logger.exception("[AR FOLLOWUP MEMORY] %s resolution failed; continuing", stage or "ws")
    return text, ""

_WEAK_GENERIC_REQUEST_RE = _re_followup.compile(
    r"^\s*(?:tell\s+me\s+about|about|explain|describe|overview\s+of|talk\s+about)\s+"
    r"(?:help|assistance|assist|support|ability|abilities|capability|capabilities|features?)\s*[?.!]*\s*$",
    _re_followup.IGNORECASE,
)

def _is_weak_generic_request(text: str) -> bool:
    return bool(_WEAK_GENERIC_REQUEST_RE.match(str(text or "").strip()))

_MEMORY_REFERENCE_WORDS_RE = _re_followup.compile(
    r"\b(?:that|this|it|what\s+you\s+(?:just\s+)?said|what\s+you\s+(?:just\s+)?explained|"
    r"your\s+(?:answer|response)|the\s+(?:previous|last)\s+(?:answer|response)|previous\s+answer|last\s+answer|above)\b",
    _re_followup.IGNORECASE,
)

def _classify_memory_rewrite_intent(text: str) -> str:
    """Classify generic requests to rewrite the last visible answer only."""
    raw_text = re.sub(r"\s+", " ", str(text or "").strip())
    if not raw_text:
        return ""
    lowered_text = raw_text.lower()
    has_arabic = bool(_ARABIC_CHAR_RE.search(raw_text)) if "_ARABIC_CHAR_RE" in globals() else bool(re.search(r"[\u0600-\u06FF]", raw_text))
    if has_arabic:
        arabic_compact = re.sub(r"[؟?.!،,؛;:\s]+", " ", raw_text).strip()
        if re.search(r"(?:ماذا\s+تقصد|ما\s+قصدك|ما\s+الذي\s+تقصد)", arabic_compact):
            return "simple"
        if re.search(r"(?:أعد|اعد)\s+صياغ", arabic_compact):
            return "rephrase"
        if re.search(r"(?:اشرح(?:ها|ه)?\s+ببساطة|ببساطة|بشكل\s+بسيط)", arabic_compact):
            return "simple"
        if re.search(r"\b(?:اختصر|اختصرها|اختصره)\b", arabic_compact):
            return "shorten"
        if re.search(r"\b(?:لخص|لخّص|تلخيص)\b", arabic_compact):
            if re.search(r"(?:ذلك|هذا|هذه|ما\s+قلت|ما\s+قلته|إجابتك|اجابتك|الجواب|الإجابة|الاجابة)", arabic_compact):
                return "summary"
            if len(arabic_compact.split()) <= 2:
                return "summary"
        return ""

    if re.search(r"\bwhat\s+do\s+you\s+mean\b", lowered_text):
        return "simple"
    if re.search(r"\bwhat\s+does\s+(?:that|this|it)\s+mean\b", lowered_text):
        return "simple"
    if re.search(r"\b(?:explain|say)\s+(?:that|this|it)?\s*(?:more\s+)?(?:simply|in\s+simple\s+(?:terms|words))\b", lowered_text):
        return "simple"
    if re.search(r"\b(?:simplify|make\s+it\s+(?:simpler|easier|clearer|simple)|in\s+simpler\s+(?:terms|words)|easier\s+explanation)\b", lowered_text):
        return "simple"
    if re.search(r"\b(?:rephrase|reword|say\s+(?:that|this|it)\s+(?:another|a\s+different)\s+way)\b", lowered_text):
        return "rephrase"
    if re.search(r"\b(?:make\s+it\s+shorter|shorter|briefly|in\s+brief|short\s+version|shorten\s+(?:that|this|it)?)\b", lowered_text):
        return "shorten"
    document_container_ref = re.search(
        r"\b(?:this|that|the|current|uploaded|attached|provided|whole|entire)\s+(?:documents?|docs?|pdfs?|files?|books?|texts?|papers?|reports?|articles?|whitepapers?|presentations?|slides?|materials?|uploads?)\b",
        lowered_text,
    )
    if re.search(r"\b(?:summari[sz]e|sum\s+up)\b", lowered_text):
        if document_container_ref:
            return ""
        if _MEMORY_REFERENCE_WORDS_RE.search(lowered_text):
            return "summary"
        if re.fullmatch(r"(?:please\s+)?(?:can\s+you\s+|could\s+you\s+|would\s+you\s+)?(?:summari[sz]e|sum\s+up)\s*(?:please)?[?.!]*", lowered_text):
            return "summary"
    if re.search(r"\bsummary\s+of\s+(?:that|this|it|your\s+(?:answer|response)|what\s+you\s+(?:just\s+)?said)\b", lowered_text):
        if document_container_ref:
            return ""
        return "summary"
    return ""

def _is_memory_rewrite_query(text: str) -> bool:
    return bool(_classify_memory_rewrite_intent(text))

def _extract_focus_concept_from_explain_query_surface(query: str) -> str:
    """Extract the object from generic explain/describe-style queries.

    Used only for conversation memory resolution, not for answering. It is
    structural (verb + trailing object) and domain-agnostic.
    """
    raw = re.sub(r"\s+", " ", str(query or "").strip())
    if not raw:
        return ""
    match = re.match(
        r"^(?:اشرح|وضح|فسر|فسّر|بسط|بسّط|explain|describe|clarify)\s+(.+?)\s*[؟?.!]*$",
        raw,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    concept = match.group(1).strip(" \t\r\n\"'`.,;:!?؟،؛-")
    concept = re.split(r"\s+(?:ضمن|في)\s+سياق\s*[:：]?|\s+in\s+context\s*[:：]?", concept, maxsplit=1, flags=re.IGNORECASE)[0]
    concept = concept.strip(" \t\r\n\"'`.,;:!?؟،؛-")
    if not concept:
        return ""
    if concept.lower() in {"ذلك", "هذا", "هذه", "it", "this", "that"}:
        return ""
    if len(concept.split()) > 8:
        return ""
    return concept

def _extract_focus_concept_from_explanatory_query_surface(query: str) -> str:
    """Extract the subject from generic explanatory questions.

    Examples: "Why is planning important?" -> "planning" and
    "كيف يرتبط X بـ Y؟" is deliberately not handled here because the
    relationship resolver handles explicit pairs separately.
    """
    raw = re.sub(r"\s+", " ", str(query or "").strip())
    if not raw:
        return ""
    lowered = raw.lower().strip(" ؟?.!")
    match = re.match(
        r"^(?:why\s+(?:is|are|was|were)|how\s+(?:is|are|was|were))\s+(.+?)\s+"
        r"(?:important|needed|necessary|useful|related|connected|relevant|significant|helpful)\b",
        lowered,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.match(r"^لماذا\s+(.+?)\s+(?:مهم|مهمة|مهمه|ضروري|ضرورية|مرتبط|مرتبطة)\b", raw)
    if not match:
        return ""
    concept = re.sub(r"\b(?:the|a|an)\b", " ", match.group(1), flags=re.IGNORECASE)
    concept = re.sub(r"\s+", " ", concept).strip(" \t\r\n\"'`.,;:!?؟،؛-")
    if not concept or len(concept.split()) > 8:
        return ""
    return concept

def _extract_last_grounded_entities(query: str, answer: str, answer_items: list[str] | None = None) -> list[str]:
    candidates: list[str] = []
    for item_text in answer_items or []:
        if item_text:
            candidates.append(str(item_text))
    concept = _extract_definition_concept_from_query_surface(query)
    if concept:
        candidates.append(concept)
    # P12C-1: also pull an Arabic-script concept when the query is Arabic so
    # later Arabic follow-ups can resolve "ها/هي/ذلك" against it. Generic
    # surface extraction — no domain word lists.
    try:
        ar_concept = _extract_arabic_concept_from_query_surface(query)
    except Exception:
        ar_concept = ""
    if ar_concept:
        candidates.append(ar_concept)
    focus_concept = _extract_focus_concept_from_explain_query_surface(query)
    if focus_concept:
        candidates.append(focus_concept)
    explanatory_concept = _extract_focus_concept_from_explanatory_query_surface(query)
    if explanatory_concept:
        candidates.append(explanatory_concept)
    if not candidates:
        answer_is_list, extracted_items = _extract_followup_items_from_answer(answer)
        if answer_is_list:
            candidates.extend(extracted_items)
    return _dedup_preserve_order(candidates)[:12]

_AR_QUERY_STOPWORDS: set[str] = {
    "ما", "ماذا", "من", "كيف", "لماذا", "متى", "اين", "هل", "هي", "هو", "هذا", "هذه",
    "ذلك", "في", "علي", "علا", "من", "إلى", "الي", "عن", "ب", "ل", "و", "أو", "او",
    "مهم", "مهمة", "مهمه", "تعريف", "العلاقة", "العلاقه", "الفرق", "بين", "اذكر",
    "عرف", "عدد", "اشرح", "وضح", "هل", "كان", "تكون", "يكون",
}

def _extract_arabic_concept_from_query_surface(query: str) -> str:
    """Return a single Arabic noun-phrase concept from the surface form of
    an Arabic question (e.g. "لماذا التخطيط مهم في الإدارة؟" -> "التخطيط").
    Strictly generic — picks the first non-stopword Arabic token of length
    >= 3. Returns empty string when nothing qualifies. No domain words.
    """
    raw = re.sub(r"\s+", " ", str(query or "").strip())
    if not raw or not re.search(r"[\u0600-\u06FF]", raw):
        return ""
    tokens = re.findall(r"[\u0600-\u06FF]+", raw)
    for tok in tokens:
        clean = tok.strip()
        if len(clean) < 3:
            continue
        if clean in _AR_QUERY_STOPWORDS:
            continue
        # Strip trailing question-particle artifacts (rare on tokens).
        return clean
    return ""

def _split_memory_answer_units(answer: str) -> list[str]:
    answer_text = re.sub(r"[ \t]+", " ", str(answer or "")).strip()
    if not answer_text:
        return []
    units: list[str] = []
    for line_text in answer_text.splitlines():
        cleaned_line = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)]|[A-Za-z][.)])\s+", "", line_text).strip()
        if cleaned_line:
            units.append(cleaned_line)
    if len(units) >= 2:
        return units
    sentence_units = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?؟])\s+|\n+", answer_text)
        if sentence and sentence.strip()
    ]
    return sentence_units or ([answer_text] if answer_text else [])

def _join_memory_items(items: list[str]) -> str:
    clean_items = _dedup_preserve_order(items)
    if not clean_items:
        return ""
    if len(clean_items) == 1:
        return clean_items[0]
    if len(clean_items) == 2:
        return f"{clean_items[0]} and {clean_items[1]}"
    return ", ".join(clean_items[:-1]) + f", and {clean_items[-1]}"

def _memory_item_summary_label(item: str) -> str:
    item_text = re.sub(r"\s+", " ", str(item or "").strip().strip(" .;:-"))
    if not item_text:
        return ""
    if ":" in item_text:
        label_text = item_text.split(":", 1)[0].strip(" .;:-")
        if label_text and len(label_text) <= 90 and len(label_text.split()) <= 8:
            return label_text
    first_unit = re.split(r"(?<=[.!?؟])\s+", item_text, maxsplit=1)[0].strip(" .;:-")
    words = first_unit.split()
    if len(words) > 12:
        return " ".join(words[:12]).strip(" .;:-")
    return first_unit

def _limit_memory_lines(text: str, max_lines: int = 3) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[:max_lines]).strip()

def _limit_memory_rewrite_text(text: str, answer_is_arabic: bool, max_lines: int = 3) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    if answer_is_arabic:
        cleaned = S._clean_arabic_final_text(cleaned)
        if not S._is_structured_bullet_answer(cleaned) and len(cleaned) > 220:
            cleaned = S._shorten_arabic_spoken_answer("", cleaned)
        return _limit_memory_lines(cleaned, min(2, max_lines))
    return _limit_memory_lines(S._polish_final_response_text("", cleaned), max_lines)

def _rewrite_previous_answer_from_memory(previous_answer: str, action: str) -> str:
    answer_text = re.sub(r"[ \t]+", " ", str(previous_answer or "")).strip()
    if not answer_text or answer_text.lower() == RAG_NO_MATCH_RESPONSE.lower():
        return RAG_NO_MATCH_RESPONSE
    answer_is_arabic = _is_arabic_text(answer_text) if "_is_arabic_text" in globals() else bool(re.search(r"[\u0600-\u06FF]", answer_text))

    def _simple_memory_rewrite(units: list[str]) -> str:
        selected_units: list[str] = []
        for unit in units[:2]:
            cleaned_unit = re.sub(r"\s+", " ", str(unit or "")).strip(" \t\r\n-•*.,;:،؛")
            cleaned_unit = re.sub(r"^(?:in\s+simple\s+terms|simply|briefly|ببساطه|ببساطة|باختصار)[:：,،\s-]*", "", cleaned_unit, flags=re.IGNORECASE).strip()
            if not cleaned_unit:
                continue
            parts = [part.strip() for part in re.split(r"\s*[؛;]\s+", cleaned_unit) if part.strip()]
            if parts:
                cleaned_unit = parts[0]
            if len(cleaned_unit.split()) > 24:
                comma_parts = [part.strip() for part in re.split(r"\s*[,،]\s+", cleaned_unit) if part.strip()]
                if comma_parts and len(comma_parts[0].split()) >= 5:
                    cleaned_unit = comma_parts[0]
            if cleaned_unit and not re.search(r"[.!?؟]$", cleaned_unit):
                cleaned_unit += "؟" if answer_is_arabic and cleaned_unit.endswith("؟") else "."
            if cleaned_unit:
                selected_units.append(cleaned_unit)
        simple_text = " ".join(selected_units[:2]).strip()
        if not simple_text:
            return RAG_NO_MATCH_RESPONSE
        prefix = "ببساطة: " if answer_is_arabic else "In simple terms: "
        if re.sub(r"\W+", "", simple_text.lower()) == re.sub(r"\W+", "", answer_text.lower()):
            return _limit_memory_rewrite_text(prefix + simple_text, answer_is_arabic, 2)
        return _limit_memory_rewrite_text(prefix + simple_text, answer_is_arabic, 2)

    answer_is_list, answer_items = _extract_followup_items_from_answer(answer_text)
    if answer_is_list and answer_items:
        summary_items = [
            label for label in (_memory_item_summary_label(item_text) for item_text in answer_items)
            if label
        ]
        joined_items = _join_memory_items(summary_items or answer_items)
        if action in {"summary", "shorten"} and len(joined_items) > 360:
            joined_items = "; ".join((summary_items or answer_items)[:3]).strip()
        if action in {"summary", "shorten"}:
            if joined_items and not re.search(r"[.!?؟]$", joined_items):
                joined_items += "."
            return _limit_memory_rewrite_text(joined_items, answer_is_arabic, 2 if answer_is_arabic else 3)
        if action == "simple":
            prefix = "ببساطة: " if answer_is_arabic else "In simple terms: "
            return _limit_memory_rewrite_text(f"{prefix}{joined_items}.", answer_is_arabic, 2)
        return _limit_memory_rewrite_text(joined_items, answer_is_arabic, 2 if answer_is_arabic else 3)

    units = _split_memory_answer_units(answer_text)
    if not units:
        return RAG_NO_MATCH_RESPONSE
    if action in {"summary", "shorten"}:
        return _limit_memory_rewrite_text("\n".join(units[:2]), answer_is_arabic, 2 if answer_is_arabic else 3)
    if action == "simple":
        return _simple_memory_rewrite(units)
    return _limit_memory_rewrite_text("\n".join(units[:3]), answer_is_arabic, 2 if answer_is_arabic else 3)

async def _handle_memory_rewrite_query(text: str, connection_id: str):
    action = _classify_memory_rewrite_intent(text)
    if not action:
        return (RAG_NO_MATCH_RESPONSE, [])
    state = _get_last_answer_state(connection_id)
    # P12C-1: fall back to the preserved last-good state when the active
    # state is missing OR was wiped by an intervening not-found turn.
    fallback_used = False
    if not state or str(state.get("last_assistant_answer") or state.get("answer") or "").strip().lower() in {"", RAG_NO_MATCH_RESPONSE.lower()}:
        good_state = S._last_good_answer_state.get(connection_id)
        if good_state:
            try:
                if (time.time() - float(good_state.get("ts", 0))) <= _FOLLOWUP_STATE_TTL:
                    state = good_state
                    fallback_used = True
            except Exception:
                pass
    if not state:
        S.logger.info("[MEMORY SUMMARY MODE] skipped reason=no_recent_answer action=%s", action)
        return (RAG_NO_MATCH_RESPONSE, [])
    previous_answer = str(
        state.get("last_assistant_answer")
        or state.get("answer")
        or ""
    ).strip()
    if not previous_answer or previous_answer.lower() == RAG_NO_MATCH_RESPONSE.lower():
        S.logger.info("[MEMORY SUMMARY MODE] skipped reason=no_grounded_answer action=%s", action)
        return (RAG_NO_MATCH_RESPONSE, [])
    memory_answer = _rewrite_previous_answer_from_memory(previous_answer, action)
    memory_answer = re.sub(r"[ \t]+", " ", str(memory_answer or "")).strip()
    if not memory_answer or memory_answer.lower() == RAG_NO_MATCH_RESPONSE.lower():
        S.logger.info("[MEMORY SUMMARY MODE] rejected reason=empty_rewrite action=%s", action)
        return (RAG_NO_MATCH_RESPONSE, [])
    memory_answer = _limit_memory_rewrite_text(memory_answer, _is_arabic_text(memory_answer), 3)
    next_state = dict(state)
    next_state.update({
        "query": (text or "").strip(),
        "answer": memory_answer,
        "last_assistant_answer": memory_answer,
        "answer_type": f"memory_{action}",
        "last_answer_type": f"memory_{action}",
        "last_grounded_entities": list(state.get("last_grounded_entities") or state.get("items") or []),
        "ts": time.time(),
    })
    S.last_answer_state[connection_id] = next_state
    S.logger.info(
        "[MEMORY SUMMARY MODE] language=%s retrieval_bypassed=True rerank_bypassed=True vector_db_bypassed=True action=%s lines=%d",
        S._route_response_language(text),
        action,
        len([line_text for line_text in memory_answer.splitlines() if line_text.strip()]),
    )
    return (memory_answer, [])

def _has_recent_followup_state(connection_id) -> bool:
    """True iff there is a non-expired saved answer state for this conn
    AND that state actually contains a substantive prior answer.

    P8: previously the function only checked TTL, so an empty saved-state
    placeholder could still trigger anaphor (it/this/that) follow-ups even
    when there was nothing to follow up on.
    """
    if not connection_id:
        return False
    state = S.last_answer_state.get(connection_id)
    if not state:
        return False
    try:
        if (time.time() - float(state.get("ts", 0))) > _FOLLOWUP_STATE_TTL:
            return False
    except Exception:
        return False
    answer = str((state or {}).get("answer") or "").strip()
    items = (state or {}).get("items") or []
    if not answer and not items:
        return False
    if answer == RAG_NO_MATCH_RESPONSE:
        return False
    return True

_CONV_LEAD_STRIP = _re_followup.compile(
    r"^\s*(?:"
    r"ok(?:ay)?(?:\s+so)?|"
    r"so|well|now|actually|alright|right|hmm|hey|"
    r"i\s+mean|i\s+wanted\s+to\s+ask|"
    r"can\s+you\s+(?:please\s+)?tell\s+me|please\s+tell\s+me|tell\s+me|"
    r"could\s+you\s+(?:please\s+)?tell\s+me|"
    r"please|just"
    r")\b[\s,]*",
    _re_followup.IGNORECASE,
)

_CONV_TRAIL_STRIP = _re_followup.compile(
    r"\s+(?:exactly|really|then|though|now|please)\s*([?.!]*)\s*$",
    _re_followup.IGNORECASE,
)


_DOCUMENT_ANCHORED_EXPLAIN_RE = _re_followup.compile(
    r"^\s*(?:please\s+)?(?:explain|describe|clarify)\s+.+\b(?:according\s+to|in|from|within)\s+(?:the\s+)?(?:documents?|docs?|pdfs?|files?|books?|texts?|sources?|passages?|chapters?|sections?)\b",
    _re_followup.IGNORECASE,
)


def _is_document_anchored_explain_query(text: str) -> bool:
    return bool(_DOCUMENT_ANCHORED_EXPLAIN_RE.search(str(text or "").strip()))

_CONV_DEF_RE_ASK_PATTERNS = [
    _re_followup.compile(p, _re_followup.IGNORECASE) for p in [
        r"^\s*what\s+about\s+(?:the\s+)?(?:definition|meaning|concept|idea|notion|sense)\s+of\s+(.+?)\s*\??\s*$",
        r"^\s*what\s+(?:is|was|'?s)\s+(?:the\s+)?(?:definition|meaning|concept|idea|notion|sense)\s+of\s+(.+?)\s*\??\s*$",
        r"^\s*(?:the\s+)?(?:definition|meaning|concept|idea|notion|sense)\s+of\s+(.+?)\s*\??\s*$",
        r"^\s*(?:can|could)\s+you\s+(?:please\s+)?(?:define|explain)\s+(.+?)\s*\??\s*$",
    ]
]

def _normalize_conversational_definition_query(text: str) -> str:
    """Rewrite conversational definition re-asks into canonical
    "what is X?" form. Returns the original text if no rewrite applies.
    Generic; no domain words.
    """
    if not text:
        return text
    t = text.strip()
    if _is_weak_generic_request(t):
        return text
    if _is_document_anchored_explain_query(t):
        return text
    # Strip leading conversational fillers (possibly stacked).
    prev = None
    while prev != t:
        prev = t
        t = _CONV_LEAD_STRIP.sub("", t).strip()
    # Strip trailing intensifiers ("exactly?", "really?", "then?")
    m = _CONV_TRAIL_STRIP.search(t)
    if m:
        # Preserve the trailing punctuation
        tail_punc = m.group(1) or ""
        t = _CONV_TRAIL_STRIP.sub(tail_punc, t).strip()
    if not t:
        return text
    # Apply rewrite patterns: extract entity tail and produce "what is X?"
    for pat in _CONV_DEF_RE_ASK_PATTERNS:
        m = pat.match(t)
        if m:
            ent = (m.group(1) or "").strip().strip(" \t\n\r\"'`.,;:!?-")
            if len(ent) >= 2:
                return f"what is {ent}?"
    return t

_ABOUT_ENTITY_VAGUE_TOKENS = {
    # Anaphoric pronouns / demonstratives
    "it", "this", "that", "these", "those", "them", "they", "there",
    "above", "previous", "last", "next", "one", "ones", "another",
    "thing", "things",
    # Ordinals commonly used to pick from a previously listed set
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
    "eighth", "ninth", "tenth",
    # Assistant / meta references
    "help", "ability", "abilities", "capability", "capabilities",
    "support", "assistance", "feature", "features", "function",
    "functions", "you", "yourself", "yours", "your", "me", "myself",
    "us", "we",
    # Document-meta references that ask for "more of the same" rather
    # than a brand-new entity (kept short and generic — no domain words).
    "more", "other", "others", "rest", "remainder", "details", "detail",
    "information", "info", "summary", "list", "lists", "items", "item",
    "parts", "part", "section", "sections", "step", "steps", "point",
    "points", "example", "examples",
    # Pure quantifiers
    "anything", "something", "nothing", "everything", "all", "some",
    "any", "many", "much", "few", "several",
}

_ABOUT_ENTITY_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "but", "to", "for",
    "in", "on", "at", "by", "with", "is", "are", "was", "were",
    "be", "been", "being", "do", "does", "did", "have", "has", "had",
    "what", "why", "how", "when", "where", "who", "which",
    "about", "please", "just", "really", "exactly",
}

_ABOUT_ENTITY_EN_PATTERNS = [
    _re_followup.compile(
        r"^\s*(?:and\s+)?what\s+about\s+(?:the\s+)?(.+?)\s*[?.!]*\s*$",
        _re_followup.IGNORECASE,
    ),
    _re_followup.compile(
        r"^\s*how\s+about\s+(?:the\s+)?(.+?)\s*[?.!]*\s*$",
        _re_followup.IGNORECASE,
    ),
    _re_followup.compile(
        r"^\s*tell\s+me\s+(?:more\s+)?about\s+(?:the\s+)?(.+?)\s*[?.!]*\s*$",
        _re_followup.IGNORECASE,
    ),
    _re_followup.compile(
        r"^\s*explain\s+(?:to\s+me\s+)?(?:the\s+)?(.+?)\s*[?.!]*\s*$",
        _re_followup.IGNORECASE,
    ),
    # Bare "and X?" pivot — kept last so the more specific patterns above
    # win. Constrained to <= 4 trailing tokens by the post-validation step
    # below (token count + vague-word filter).
    _re_followup.compile(
        r"^\s*and\s+(?:the\s+)?(.+?)\s*[?.!]*\s*$",
        _re_followup.IGNORECASE,
    ),
]

_ABOUT_ENTITY_AR_PATTERNS = [
    # وماذا عن X / ماذا عن X
    _re_followup.compile(r"^\s*و?\s*ماذا\s+عن\s+(.+?)\s*[؟?.!]*\s*$"),
    # طب و X / طيب و X (with space)
    _re_followup.compile(r"^\s*(?:طب|طيب)\s+و\s+(.+?)\s*[؟?.!]*\s*$"),
    # طب والX / طيب والX (و prefix attached)
    _re_followup.compile(r"^\s*(?:طب|طيب)\s+و(\S.+?)\s*[؟?.!]*\s*$"),
    # اشرح X / اشرح لي X
    _re_followup.compile(r"^\s*اشرح\s+(?:لي\s+)?(.+?)\s*[؟?.!]*\s*$"),
]

_ARABIC_CHAR_RE = _re_followup.compile(r"[\u0600-\u06FF]")

_NEW_QUESTION_HEAD_RE = _re_followup.compile(
    r"^\s*(?:"
    r"(?:what|which)\s+(?:is|are|was|were|'?s)\b"
    r"|why\b|when\b|where\b|who\b"
    r"|how\s+(?:do|does|did|can|could|should|would|will|is|are|much|many|long|often)\b"
    r"|list\b|name\b|enumerate\b|define\b|definition\s+of\b"
    r"|give\s+me\s+(?:a\s+)?(?:list|definition|example)\b"
    r")",
    _re_followup.IGNORECASE,
)

def _extract_about_entity_question(query: str) -> Optional[str]:
    """Detect a "what about X / how about X / and X / tell me about X /
    explain X" style query that introduces a NEW entity, and return a
    normalized standalone question for X ("What is X?" / "ما هي X؟").

    Returns ``None`` when X is missing, vague (pronoun / meta /
    document-relative), or otherwise not a content phrase. Strictly
    generic — no domain word lists.
    """
    raw = (query or "").strip()
    if not raw:
        S.logger.info("[ABOUT ENTITY ROUTE] detected=False reason=empty")
        return None
    # Skip clear standalone question shapes — they don't need rewriting.
    if _NEW_QUESTION_HEAD_RE.match(raw):
        return None
    # Skip weak generic / meta-help phrasings ("tell me about help").
    if _is_weak_generic_request(raw):
        S.logger.info("[ABOUT ENTITY ROUTE] detected=False reason=weak_generic query=%s", raw[:120])
        return None
    if _is_document_anchored_explain_query(raw):
        S.logger.info("[ABOUT ENTITY ROUTE] detected=False reason=document_anchored_explain query=%s", raw[:120])
        return None
    is_arabic = bool(_ARABIC_CHAR_RE.search(raw))
    patterns = _ABOUT_ENTITY_AR_PATTERNS if is_arabic else _ABOUT_ENTITY_EN_PATTERNS
    entity = None
    for pat in patterns:
        m = pat.match(raw)
        if not m:
            continue
        entity = (m.group(1) or "").strip().strip(" \t\n\r\"'`.,;:!?-؟،")
        if entity:
            break
    if not entity:
        S.logger.info("[ABOUT ENTITY ROUTE] detected=False reason=no_pattern query=%s", raw[:120])
        return None
    tokens = [tok for tok in _re_followup.split(r"\s+", entity) if tok]
    if not tokens or len(tokens) > 6:
        S.logger.info("[ABOUT ENTITY ROUTE] detected=False reason=bad_token_count entity=%s", entity)
        return None
    lowered = [tok.lower().strip(" \t\n\r\"'`.,;:!?-؟،") for tok in tokens]
    # Reject if every token is either vague/meta or a stopword.
    if all((tok in _ABOUT_ENTITY_VAGUE_TOKENS or tok in _ABOUT_ENTITY_STOPWORDS) for tok in lowered):
        S.logger.info("[ABOUT ENTITY ROUTE] detected=False reason=vague_or_stopword entity=%s", entity)
        return None
    # Reject if any vague/meta pronoun is mixed in — ambiguous reference.
    if any(tok in _ABOUT_ENTITY_VAGUE_TOKENS for tok in lowered):
        S.logger.info("[ABOUT ENTITY ROUTE] detected=False reason=contains_vague entity=%s", entity)
        return None
    # Require at least one real word token (>=3 chars, contains a letter).
    if not any(
        len(tok) >= 3 and _re_followup.search(r"[A-Za-z\u0600-\u06FF]", tok)
        for tok in lowered
    ):
        S.logger.info("[ABOUT ENTITY ROUTE] detected=False reason=no_word_token entity=%s", entity)
        return None
    rewritten = f"ما هي {entity}؟" if is_arabic else f"What is {entity}?"
    S.logger.info(
        "[ABOUT ENTITY ROUTE] detected=True entity=%s rewritten_query=%s",
        entity,
        rewritten,
    )
    return rewritten

def _maybe_rewrite_about_entity_question(text: str) -> str:
    """Apply the about-entity rewrite if it fires; otherwise return
    ``text`` unchanged. Shared preprocessing helper used by both the
    typed WebSocket path and the voice transcript path so the logic
    cannot drift between them.
    """
    try:
        rewritten = _extract_about_entity_question(text)
    except Exception:
        S.logger.exception("[ABOUT ENTITY ROUTE] extractor raised — leaving query unchanged")
        return text
    if not rewritten or rewritten == text:
        return text
    S.logger.info(
        "[ABOUT ENTITY ROUTE] applied original=%r rewritten=%r",
        (text or "")[:160],
        rewritten[:160],
    )
    return rewritten

def _is_followup_query(text: str, connection_id=None) -> bool:
    """Generic follow-up intent detector. Domain-agnostic.

    Tiering:
      1. STRONG patterns -> always follow-up (no context needed).
      2. CONTEXTUAL patterns -> follow-up ONLY if a recent saved answer
         state exists for ``connection_id``.
      3. SHORT-utterance fallback (≤ _FOLLOWUP_SHORT_WORD_LIMIT words)
         -> follow-up ONLY if prior state exists AND the utterance
         does NOT look like a brand-new question.
    Callers without a connection (e.g. plain helpers) may omit
    ``connection_id`` to use only the strong tier.
    """
    t = (text or "").strip()
    if not t or len(t) > _FOLLOWUP_MAX_QUERY_LEN:
        return False
    if _is_weak_generic_request(t):
        S.logger.info("[ANSWER PERMISSION] allowed=False reason=weak_generic_followup_candidate query=%s", t[:180])
        return False
    if _is_memory_rewrite_query(t):
        return _has_recent_followup_state(connection_id)
    # P12C-1: Arabic strong follow-up patterns require state to actually
    # answer (handler still returns Not found if state missing) but they
    # qualify as follow-up *intent* so the WS path skips the heavy
    # router/RAG and avoids classifying them as unsupported_unclear.
    if _is_arabic_followup_strong(t):
        if _has_recent_followup_state(connection_id) or S._last_good_answer_state.get(connection_id):
            S.logger.info("[AR FOLLOWUP MEMORY] detected=True kind=strong query=%s", t[:160])
            return True
    for pat in _FOLLOWUP_PATTERNS:
        if pat.search(t):
            return True
    if not _has_recent_followup_state(connection_id):
        return False
    for pat in _FOLLOWUP_CONTEXT_PATTERNS:
        if pat.search(t):
            return True
    if _is_arabic_followup_context(t):
        S.logger.info("[AR FOLLOWUP MEMORY] detected=True kind=context query=%s", t[:160])
        return True
    if len(t.split()) <= _FOLLOWUP_SHORT_WORD_LIMIT:
        for pat in _FOLLOWUP_NEW_QUESTION_PATTERNS:
            if pat.search(t):
                return False
        state = _get_last_answer_state(connection_id)
        answer_text = str((state or {}).get("answer") or "")
        state_items = [str(item or "") for item in ((state or {}).get("items") or [])]
        _prev_is_list, extracted_items = _extract_followup_items_from_answer(answer_text)
        candidate_items = [item for item in (extracted_items or state_items) if item]
        if candidate_items:
            try:
                targeted_item, _target_reason = _select_followup_target_item(candidate_items, t)
                if targeted_item:
                    return True
            except Exception:
                pass
        if _re_followup.search(r"\b(?:it|this|that|these|those|them|there|above|previous|first|second|third|last|one|ones)\b", t, _re_followup.IGNORECASE):
            return True
        if _AR_ANAPHOR_RE.search(t):
            S.logger.info("[AR FOLLOWUP MEMORY] detected=True kind=short_anaphor query=%s", t[:160])
            return True
        S.logger.info("[FOLLOWUP] short_fallback_rejected query=%s", t[:180])
        return False
    return False

def _classify_followup_intent(text: str) -> str:
    t = (text or "").lower()
    # P8: word-boundary checks so accidental substrings (e.g. "phrase" vs.
    # "rephrase", "shortage" vs. "shorter") cannot misroute intent.
    if re.search(r"\b(?:simpl\w*|easier|clearer|shorter)\b", t):
        return "simplify"
    if re.search(r"\b(?:rephrase|reword)\b", t) or re.search(r"\bbreak\b.*\bdown\b", t):
        return "rephrase"
    return "explain"

def _extract_followup_items_from_answer(answer: str) -> tuple[bool, list[str]]:
    """Extract list items from a prior answer using only generic structure."""
    answer_text = str(answer or "")
    if not answer_text.strip():
        return False, []

    # P4: include lettered list markers (a) b) A. B.) in addition to dashes,
    # bullets and digits. Generic across documents.
    _list_marker_re = r"(?:[-*\u2022]|\d+[.)]|[A-Za-z][.)])"

    def _dedup_items(items: list[str]) -> list[str]:
        # P4: dedup by normalized lowercase alnum form so "Planning",
        # "planning.", and "  planning " collapse to one entry.
        seen: set[str] = set()
        out: list[str] = []
        for it in items:
            key = re.sub(r"[^a-z0-9]+", " ", str(it or "").lower()).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    list_lines = [
        line.strip() for line in answer_text.splitlines()
        if _re_followup.match(rf"^\s*{_list_marker_re}\s+\S", line)
    ]
    extracted_items: list[str] = []
    if len(list_lines) >= 2:
        for list_line in list_lines:
            item = _re_followup.sub(
                rf"^\s*{_list_marker_re}\s*", "", list_line
            ).strip()
            if item:
                extracted_items.append(item)
        if extracted_items:
            return True, _dedup_items(extracted_items)

    bullet_parts_raw = _re_followup.split(
        rf"(?:^|\s){_list_marker_re}\s+", answer_text
    )
    bullet_parts = [
        part.strip().rstrip(".")
        for part in bullet_parts_raw
        if part and part.strip()
    ]
    if len(bullet_parts) >= 3 and all(len(part) <= 60 for part in bullet_parts):
        return True, _dedup_items(bullet_parts)

    comma_parts = [
        part.strip().rstrip(".")
        for part in _re_followup.split(r"[,;]", answer_text)
        if part.strip()
    ]
    if len(comma_parts) >= 3 and all(len(part) <= 60 for part in comma_parts):
        first_item = comma_parts[0]
        intro_match = _re_followup.search(
            r"\b(?:are|include|includes|consist of|consists of|namely)\s+",
            first_item,
            _re_followup.IGNORECASE,
        )
        if intro_match:
            first_item = first_item[intro_match.end():].strip()
        if comma_parts:
            comma_parts[-1] = _re_followup.sub(
                r"^\s*and\s+", "", comma_parts[-1], flags=_re_followup.IGNORECASE
            ).strip()
        comma_parts[0] = first_item
        extracted_items = [part for part in comma_parts if part]
        if len(extracted_items) >= 3:
            return True, _dedup_items(extracted_items)

    return False, []

def _infer_followup_answer_type(query: str, answer: str) -> str:
    """Classify saved answer shape for later follow-up routing."""
    is_list_answer, _items = _extract_followup_items_from_answer(answer)
    try:
        query_is_list = S._is_list_query(query)
    except Exception:
        query_is_list = False
    if is_list_answer or query_is_list:
        return "list"
    try:
        query_is_compare = S._is_compare_query(query) or _is_bare_comparison_followup_query(query)
    except Exception:
        query_is_compare = False
    if query_is_compare:
        return "text"
    query_low = re.sub(r"\s+", " ", str(query or "").strip().lower())
    if _re_followup.match(
        r"^(?:what\s+(?:is|are|was|were)|define|definition\b)", query_low
    ):
        return "definition"
    return "text"

def _extract_definition_concept_from_query_surface(query: str) -> str:
    query_value = re.sub(r"\s+", " ", str(query or "").strip())
    if not query_value:
        return ""
    try:
        if S._is_compare_query(query_value) or _is_bare_comparison_followup_query(query_value):
            return ""
    except Exception:
        pass
    match = re.match(
        r"^(?:what|who)\s+(?:is|are|was|were)\s+(.+?)\??$",
        query_value,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.match(
            r"^(?:define|definition\s+of)\s+(.+?)\??$",
            query_value,
            flags=re.IGNORECASE,
        )
    if not match:
        return ""
    concept = re.sub(r"\b(?:the|a|an)\b", " ", match.group(1), flags=re.IGNORECASE)
    concept = re.sub(r"\s+", " ", concept).strip(" \t\r\n.,;:!?()[]{}")
    tokens = [
        token for token in re.findall(r"[a-z0-9]{3,}", concept.lower())
        if token not in _EVIDENCE_STOPWORDS
    ]
    if not tokens or len(tokens) > 6:
        return ""
    return concept

def _format_compare_memory_concepts(concepts: list[str]) -> str:
    return "[" + ", ".join(str(concept or "").strip() for concept in concepts if str(concept or "").strip()) + "]"

def _save_last_answer_state(connection_id, query, answer, doc_dicts) -> None:
    """Persist the most recent grounded answer for follow-up explanations.

    Skips storage for empty answers. For the strict not-found response we
    actively CLEAR any previously saved state for this connection so that a
    later follow-up ("explain more", "what do you mean?") cannot leak the
    previous successful answer into a turn that ended in not-found.
    """
    try:
        if not connection_id:
            return
        ans = (answer or "").strip()
        if not ans:
            return
        try:
            if ans.lower() == RAG_NO_MATCH_RESPONSE.lower():
                # Latest turn produced a not-found result. Drop the active
                # state so ordinary follow-ups have nothing to explain.
                # Preserve the separate last-good store only when the failed
                # turn itself was a follow-up; clear it for unrelated new
                # topics so stale summaries cannot cross topic boundaries.
                latest_query = (query or "").strip()
                preserve_last_good = False
                try:
                    preserve_last_good = bool(
                        _is_memory_rewrite_query(latest_query)
                        or _is_arabic_followup_strong(latest_query)
                        or _is_arabic_followup_context(latest_query)
                        or _is_marked_arabic_resolved_followup(connection_id, latest_query)
                        or _is_followup_query(latest_query, connection_id)
                    )
                except Exception:
                    preserve_last_good = False
                if connection_id in S.last_answer_state:
                    S.last_answer_state.pop(connection_id, None)
                    S.logger.info(
                        "[FOLLOWUP] cleared stale state for connection_id=%s "
                        "(latest answer was not-found)",
                        connection_id,
                    )
                    S.logger.info("[SMART MEMORY] rejected_reason=not_found_clears_state")
                if not preserve_last_good:
                    S._last_good_answer_state.pop(connection_id, None)
                    S._last_list_state.pop(connection_id, None)
                    S.logger.info("[SMART MEMORY] rejected_reason=not_found_topic_shift_clears_last_good")
                else:
                    S.logger.info("[SMART MEMORY] source=last_good preserved_after_followup_not_found=True")
                S._ar_resolved_followup_queries.pop(connection_id, None)
                S.recent_grounded_definition_concepts.pop(connection_id, None)
                return
        except Exception:
            pass
        answer_is_list, answer_items = _extract_followup_items_from_answer(ans)
        answer_type = _infer_followup_answer_type(query, ans)
        doc_candidates = list(doc_dicts or [])
        if answer_is_list and answer_items:
            scored_candidates: list[tuple[float, int, dict]] = []
            for order, doc_dict in enumerate(doc_candidates):
                if not isinstance(doc_dict, dict):
                    continue
                doc_text = str(
                    doc_dict.get("text")
                    or doc_dict.get("page_content")
                    or doc_dict.get("content")
                    or ""
                ).strip()
                support_score = _followup_list_chunk_support_score(answer_items, doc_text)
                if support_score > 0:
                    scored_candidates.append((support_score, order, doc_dict))
            if scored_candidates:
                scored_candidates.sort(key=lambda row: (-row[0], row[1]))
                max_support = scored_candidates[0][0]
                min_support = 1.0
                if max_support >= 3.0:
                    min_support = max(3.0, max_support * 0.75)
                doc_candidates = [
                    doc_dict
                    for support_score, _order, doc_dict in scored_candidates
                    if support_score >= min_support
                ]
        kept = []
        for doc_dict in doc_candidates[:_FOLLOWUP_KEEP_TOP_K]:
            if not isinstance(doc_dict, dict):
                continue
            txt = str(
                doc_dict.get("text")
                or doc_dict.get("page_content")
                or doc_dict.get("content")
                or ""
            ).strip()
            if not txt:
                continue
            src = doc_dict.get("source")
            md = doc_dict.get("metadata")
            if (not src) and isinstance(md, dict):
                src = md.get("source") or md.get("doc_id") or md.get("file")
            kept_doc = {"text": txt[:_FOLLOWUP_SAVED_CHUNK_CHAR_LIMIT], "source": src}
            if isinstance(md, dict):
                kept_doc["metadata"] = {
                    "source": md.get("source"),
                    "doc_id": md.get("doc_id"),
                    "file": md.get("file"),
                    "page": md.get("page"),
                    "chunk_index": md.get("chunk_index"),
                }
            kept.append(kept_doc)
        next_state = {
            "query": (query or "").strip(),
            "answer": ans,
            "last_assistant_answer": ans,
            "chunks": kept,
            "ts": time.time(),
            "answer_type": answer_type,
            "last_answer_type": answer_type,
            "last_grounded_entities": _extract_last_grounded_entities(query, ans, answer_items),
        }
        if answer_is_list and answer_items:
            next_state["items"] = answer_items
            next_state["list_query"] = (query or "").strip()
            next_state["list_answer"] = ans
        S.last_answer_state[connection_id] = next_state
        # P12C-1: mirror grounded answers to a separate "good" store that
        # survives a single not-found / failed follow-up turn so Arabic
        # memory rewrites ("طيب اختصر أكثر") can still operate on the
        # previous useful answer. Mirror only NON-not-found grounded
        # answers (the early-return above already handled the not-found
        # path before we get here).
        try:
            S._last_good_answer_state[connection_id] = dict(next_state)
            if answer_is_list and answer_items:
                S._last_list_state[connection_id] = {
                    "items": list(answer_items),
                    "query": (query or "").strip(),
                    "answer": ans,
                    "ts": time.time(),
                }
        except Exception:
            S.logger.exception("[FOLLOWUP] failed to mirror good/list state")
        S._ar_resolved_followup_queries.pop(connection_id, None)
        if answer_type == "list":
            S.logger.info("[COMPARE MEMORY] ignored=list_entity")
            S.logger.info("[SMART MEMORY] source=last_list rejected_reason=list_does_not_overwrite_concept_pair")
        if answer_type == "definition" and kept:
            concept = _extract_definition_concept_from_query_surface(query)
            if concept:
                recent_items = list(S.recent_grounded_definition_concepts.get(connection_id, []) or [])
                concept_key = concept.lower()
                recent_items = [item for item in recent_items if str((item or {}).get("concept") or "").lower() != concept_key]
                recent_items.append({"concept": concept, "ts": time.time()})
                S.recent_grounded_definition_concepts[connection_id] = recent_items[-4:]
                stable_concepts = [
                    str((item or {}).get("concept") or "")
                    for item in S.recent_grounded_definition_concepts[connection_id]
                    if str((item or {}).get("concept") or "").strip()
                ]
                S.logger.info("[COMPARE MEMORY] stable=%s", _format_compare_memory_concepts(stable_concepts))
                S.logger.info(
                    "[COMPARE FOLLOWUP STATE] connection_id=%s concepts=%s",
                    connection_id,
                    [str((item or {}).get("concept") or "") for item in S.recent_grounded_definition_concepts[connection_id]],
                )
                S.logger.info("[SMART MEMORY] source=last_definition resolved_reference=%s", concept)
    except Exception:
        S.logger.exception("[FOLLOWUP] failed to save last answer state")

def _get_last_answer_state(connection_id):
    state = S.last_answer_state.get(connection_id)
    if not state:
        return None
    try:
        if (time.time() - float(state.get("ts", 0))) > _FOLLOWUP_STATE_TTL:
            S.last_answer_state.pop(connection_id, None)
            return None
    except Exception:
        return None
    return state

def _is_bare_comparison_followup_query(query_text: str) -> bool:
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    if not q:
        return False
    has_comparison_intent = bool(
        re.search(r"\b(?:difference|differences|distinction)\b", q)
        or re.search(r"\b(?:different)\b", q)
        or re.search(r"\b(?:compare|comparison|contrast|contrasts)\b", q)
        or re.search(r"\b(?:differentiate|distinguish)\b", q)
        or re.search(r"\b(?:relationship|relation|relate|relates|related)\b", q)
        or re.search(r"\b(?:versus|vs\.?)\b", q)
        or re.search(r"(?:ما\s+)?الفرق|قارن|مقارنة", q)
    )
    if not has_comparison_intent:
        return False
    explicit_pair = bool(
        re.search(r"\bbetween\b.+\band\b", q)
        or re.search(r"\bcompare\b.+\band\b", q)
        or re.search(r"\b(?:relationship|relation)\b.+\bbetween\b.+\band\b", q)
        or re.search(r"\brelat(?:e|es|ed)\b.+\b(?:to|with)\b", q)
        or re.search(r"\b(?:versus|vs\.?)\b", q)
        or re.search(r"\bبين\b.+\bو\b", q)
    )
    return not explicit_pair

def _extract_recent_definition_concepts_from_history(history: list[dict], max_turns: int = 6) -> list[str]:
    concepts: list[str] = []
    seen: set[str] = set()
    if not history:
        return concepts
    for index in range(len(history) - 1, -1, -1):
        entry = history[index] if isinstance(history[index], dict) else {}
        if entry.get("role") != "user":
            continue
        user_text = str(entry.get("content") or "")
        try:
            if S._is_list_query(user_text):
                S.logger.info("[COMPARE MEMORY] ignored=list_entity")
                continue
        except Exception:
            pass
        next_entry = history[index + 1] if index + 1 < len(history) and isinstance(history[index + 1], dict) else {}
        if next_entry.get("role") == "assistant":
            assistant_text = str(next_entry.get("content") or "").strip()
            if not assistant_text or assistant_text.lower() == RAG_NO_MATCH_RESPONSE.lower():
                continue
            answer_is_list, _answer_items = _extract_followup_items_from_answer(assistant_text)
            if answer_is_list:
                S.logger.info("[COMPARE MEMORY] ignored=list_entity")
                continue
        concept = _extract_definition_concept_from_query_surface(user_text)
        if not concept:
            continue
        concept_key = concept.lower()
        if concept_key in seen:
            continue
        seen.add(concept_key)
        concepts.append(concept)
        if len(concepts) >= max_turns:
            break
    return list(reversed(concepts))

def _rewrite_bare_comparison_query_from_history(query_text: str, history: list[dict], connection_id: str | None = None) -> str:
    if not _is_bare_comparison_followup_query(query_text):
        return str(query_text or "")
    concepts: list[str] = []
    if connection_id:
        recent_items = list(S.recent_grounded_definition_concepts.get(connection_id, []) or [])
        concepts = [
            str((item or {}).get("concept") or "").strip()
            for item in recent_items[-2:]
            if str((item or {}).get("concept") or "").strip()
        ]
        if concepts:
            S.logger.info("[COMPARE MEMORY] stable=%s", _format_compare_memory_concepts(concepts))
    if len(concepts) != 2:
        concepts = _extract_recent_definition_concepts_from_history(history)[-2:]
        if concepts:
            S.logger.info("[COMPARE MEMORY] stable=%s", _format_compare_memory_concepts(concepts))
    if len(concepts) != 2:
        S.logger.info(
            "[COMPARE FOLLOWUP REWRITE] skipped history_len=%d concepts=%s",
            len(history or []),
            concepts,
        )
        S.logger.info("[SMART MEMORY] rejected_reason=insufficient_stable_concepts_for_comparison concepts=%d", len(concepts))
        return str(query_text or "")
    left, right = concepts
    if not left or not right or left.lower() == right.lower():
        return str(query_text or "")
    S.logger.info("[COMPARE ENTITIES] left=%s right=%s source=history", left, right)
    S.logger.info("[SMART MEMORY] resolved_reference=comparison_pair source=last_comparison left=%s right=%s", left, right)
    return f"What is the difference between {left} and {right}?"

def _append_conversation_turn(connection_id: str, user_text: str, assistant_text: str) -> None:
    try:
        history = S.conversation_history[connection_id]
        history.append({"role": "user", "content": str(user_text or "").strip()})
        history.append({"role": "assistant", "content": str(assistant_text or "").strip()})
    except Exception:
        pass

_EXPLAIN_VERB_RE = _re_followup.compile(
    r"\b(?:"
    r"is|are|was|were|means?|refer(?:s|red|ring)?\s+to|"
    r"defin(?:e[ds]?|ing)\b|involv(?:e[ds]?|ing)|"
    r"represent(?:s|ed|ing)?|consist(?:s|ed|ing)?\s+of|"
    r"denot(?:e[ds]?|ing)|signif(?:ies|ied|ying)|"
    r"pertain(?:s|ed|ing)?\s+to|deal(?:s|t|ing)?\s+with|"
    r"describ(?:e[ds]?|ing)|provid(?:e[ds]?|ing)|"
    r"ensur(?:e[ds]?|ing)|focus(?:es|ed|ing)?\s+on|"
    r"entail(?:s|ed|ing)?|cover(?:s|ed|ing)?|"
    r"requir(?:e[ds]?|ing)|necessitat(?:e[ds]?|ing)"
    r")\b"
)

_FOLLOWUP_EXPLANATORY_CUE_RE = _re_followup.compile(
    r"\b(?:is|are|was|were|means?|refers?\s+to|defined\s+as|involv(?:e[sd]?|ing))\b",
    _re_followup.IGNORECASE,
)

_EVIDENCE_STOPWORDS = frozenset({
    "this", "that", "these", "those", "with", "from", "into", "than",
    "then", "have", "been", "being", "were", "they", "them", "their",
    "there", "which", "what", "when", "where", "while", "about", "also",
    "such", "some", "more", "most", "many", "much", "will", "would",
    "could", "should", "does", "done", "other", "each", "every", "only",
    "just", "very", "here", "well", "like", "same", "used", "make",
    "made", "take", "give", "need", "know", "keep", "even", "still",
    "back", "over", "under", "between", "work", "said", "says",
    "listed", "items", "item", "list", "above", "below", "following",
    "mentioned", "presents", "presented",
})

def _evidence_has_explicit_explanation(item_name: str, evidence_text: str) -> bool:
    """Return True when *evidence_text* contains a sentence that genuinely
    explains *item_name* — a definition, description, or substantive
    predicate about the item — rather than a passing mention or list
    membership.

    Heuristic signals (generic, no domain vocabulary):
      1. Item appears in a sentence with an explanatory verb within a
         proximity window AND >= 3 substantive content words nearby.
      2. Item appears in a window with >= 6 content words (high
         informational density even without an explicit verb).

    Bare-list sentences (>=3 bullet/dash/comma separators with low word
    density) are skipped automatically.
    """
    if not item_name or not evidence_text:
        return False
    item_low = item_name.strip().lower()
    if not item_low:
        return False
    ev_low = evidence_text.lower()
    item_re = _re_followup.compile(r"\b" + _re_followup.escape(item_low) + r"\b")
    if not item_re.search(ev_low):
        return False

    # Rough sentence splitting
    sents = _re_followup.split(r"(?<=[.!?:;])\s+|\n+|---+", ev_low)

    for sent in sents:
        sent = sent.strip()
        if len(sent) < 20 or not item_re.search(sent):
            continue
        # Skip bare-list sentences (many items separated by delimiters)
        seps = len(_re_followup.findall(r"(?:^|\s)[-*\u2022]\s|\s[-\u2013]\s|,\s", sent))
        words = _re_followup.findall(r"[a-z]{3,}", sent)
        if seps >= 3 and len(words) < seps * 5:
            continue

        for m in item_re.finditer(sent):
            ws = max(0, m.start() - 40)
            we = min(len(sent), m.end() + 120)
            window = sent[ws:we]

            has_verb = bool(_EXPLAIN_VERB_RE.search(window))
            # Count substantive content words (4+ chars, not stopwords,
            # not the item itself)
            win_words = _re_followup.findall(r"[a-z]{4,}", window)
            content = [
                w for w in win_words
                if w not in _EVIDENCE_STOPWORDS
                and w != item_low
                and not w.startswith(item_low[:min(4, len(item_low))])
            ]
            n = len(content)

            if has_verb and n >= 3:
                return True
            if n >= 6:
                return True
    return False

_FOLLOWUP_INFERRED_SUFFIX = (
    "(The document mentions this concept but does not provide a detailed explanation.)"
)

_FOLLOWUP_EXPL_GROUND_THRESHOLD = 0.60

def _compute_explanation_grounding_score(
    explanation: str, excerpts_block: str, last_a: str
) -> float:
    """Return the fraction of content words in *explanation* that appear
    (whole-word) in *excerpts_block* or *last_a*.

    Used as an anti-hallucination guard for the controlled-explanation
    mode.  Generic: only stopword filtering + whole-word matching.
    """
    _stop = {
        "the", "a", "an", "of", "and", "or", "to", "in", "on", "for",
        "with", "by", "from", "at", "is", "are", "was", "were", "be",
        "been", "being", "this", "that", "these", "those", "it", "its",
        "as", "but", "not", "also", "then", "when", "where", "which",
        "who", "what", "how", "if", "so", "do", "does", "did", "has",
        "have", "had", "will", "would", "can", "could", "should", "may",
        "might", "must", "shall", "such", "each", "more", "most", "some",
        "any", "all", "one", "two", "three", "their", "they", "them",
        "we", "you", "i", "my", "your", "our",
    }
    haystack = ((excerpts_block or "") + " " + (last_a or "")).lower()
    content_words = [
        w for w in re.findall(r"[a-z]{3,}", (explanation or "").lower())
        if w not in _stop
    ]
    if not content_words:
        return 1.0  # empty explanation: no content to check
    matched = sum(
        1 for w in content_words
        if re.search(rf"\b{re.escape(w)}\b", haystack)
    )
    return matched / len(content_words)

def _infer_previous_list_relation_phrase(previous_query: str) -> str:
    """Return a short generic phrase describing what the previous list was about.

    The phrase is derived only from the user's previous question, so follow-up
    explanations can say "one of the goals of X" without introducing any new
    domain knowledge.
    """
    q = re.sub(r"\s+", " ", str(previous_query or "").strip().strip("?!."))
    if not q:
        return "the listed items"
    patterns = (
        r"^\s*(?:what|which)\s+(?:are|were)\s+(?:the\s+)?(.+?)\s*$",
        r"^\s*(?:list|name|mention|identify|give)\s+(?:the\s+)?(.+?)\s*$",
    )
    phrase = ""
    for patt in patterns:
        m = re.search(patt, q, flags=re.IGNORECASE)
        if m:
            phrase = re.sub(r"\s+", " ", (m.group(1) or "")).strip(" ,;:-")
            break
    if not phrase:
        return "the listed items"
    phrase = re.sub(r"^(?:main|major|primary|basic|different|various)\s+", "", phrase, flags=re.IGNORECASE).strip()
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", phrase)
    if len(words) > 10:
        return "the listed items"
    if not re.match(r"^(?:the|a|an)\b", phrase, flags=re.IGNORECASE):
        phrase = "the " + phrase
    return phrase

def _join_short_item_names(items: list[str], max_items: int = 5) -> str:
    cleaned: list[str] = []
    for item in items:
        s = re.sub(r"\s+", " ", str(item or "").strip().strip(" .;:-"))
        if not s:
            continue
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", s)
        if not words or len(words) > 9:
            continue
        cleaned.append(s)
        if len(cleaned) >= max_items:
            break
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"

def _build_followup_list_context_mini_explanation(
    target_item: str,
    previous_items: list[str],
    previous_query: str,
) -> str | None:
    """Build a grounded follow-up explanation from the prior list only.

    This deliberately does not invent examples or domain details. It states the
    only relationship that is grounded when the document merely listed the item.
    """
    target = re.sub(r"\s+", " ", str(target_item or "").strip().strip(" .;:-"))
    if not target:
        return None
    items = [re.sub(r"\s+", " ", str(it or "").strip().strip(" .;:-")) for it in (previous_items or [])]
    items = [it for it in items if it]
    if target not in items:
        return None
    if len(items) < 2:
        return None

    relation_phrase = _infer_previous_list_relation_phrase(previous_query)
    others = [it for it in items if it != target]
    others_text = _join_short_item_names(others, max_items=5)

    sentences = [f"The document refers to this as {target}, one of {relation_phrase}."]
    if others_text:
        sentences.append(
            f"It appears in the same list with {others_text}, so the grounded context is the list relationship."
        )
    sentences.append("The document does not provide a detailed explanation for it.")
    return " ".join(sentences)

_FOLLOWUP_TARGET_STOPWORDS = _EVIDENCE_STOPWORDS | frozenset({
    "explain", "explains", "explained", "clarify", "clarifies", "clarified",
    "elaborate", "elaborates", "elaborated", "rephrase", "rephrases",
    "rephrased", "simplify", "simplifies", "simplified", "tell", "about",
    "please", "mean", "means", "meaning", "what", "does", "more", "detail",
    "details", "further",
})

def _followup_item_head(item: str) -> str:
    return re.sub(r"\s+", " ", str(item or "").split(":", 1)[0]).strip(" .;:-")

def _followup_content_tokens(value: str) -> list[str]:
    return [
        token for token in _re_followup.findall(r"[a-z0-9]{3,}", str(value or "").lower())
        if token not in _FOLLOWUP_TARGET_STOPWORDS
    ]

def _followup_query_surface_focus_phrase(item: str, user_text: str) -> str:
    item_tokens = set(_followup_content_tokens(_followup_item_head(item)))
    if not item_tokens:
        return ""
    text_value = str(user_text or "")
    token_matches = list(_re_followup.finditer(r"[a-z0-9]{3,}", text_value.lower()))
    matching_indexes = [
        index for index, match in enumerate(token_matches)
        if match.group(0) in item_tokens
    ]
    if not matching_indexes:
        return ""
    first_index = matching_indexes[0]
    last_index = matching_indexes[-1]
    if last_index - first_index > 7:
        return ""
    start = token_matches[first_index].start()
    end = token_matches[last_index].end()
    phrase = re.sub(r"\s+", " ", text_value[start:end]).strip(" \t\r\n.,;:!?()[]{}")
    if len(_followup_content_tokens(phrase)) < 1:
        return ""
    if len(phrase) > 90:
        return ""
    return phrase

def _followup_query_focus_phrase(item: str, user_text: str) -> str:
    item_head = _followup_item_head(item)
    surface_phrase = _followup_query_surface_focus_phrase(item_head, user_text)
    if surface_phrase:
        return surface_phrase
    item_tokens = _followup_content_tokens(item_head)
    query_tokens = set(_followup_content_tokens(user_text))
    overlap = [token for token in item_tokens if token in query_tokens]
    if overlap:
        return " ".join(overlap[:3]).strip()
    if len(item_tokens) > 6:
        return " ".join(item_tokens[:4]).strip() or item_head
    return item_head

def _followup_text_mentions_item(text: str, item: str) -> bool:
    text_low = str(text or "").lower()
    item_head = _followup_item_head(item)
    item_low = item_head.lower()
    if not text_low.strip() or not item_low:
        return False
    if _re_followup.search(r"\b" + _re_followup.escape(item_low) + r"\b", text_low):
        return True
    item_tokens = _followup_content_tokens(item_head)
    if not item_tokens:
        return False
    text_tokens = set(_re_followup.findall(r"[a-z0-9]{3,}", text_low))
    if len(item_tokens) == 1:
        return item_tokens[0] in text_tokens
    overlap = sum(1 for token in item_tokens if token in text_tokens)
    needed = max(2, int(math.ceil(len(item_tokens) * 0.55)))
    if overlap >= needed:
        return True
    first_token = item_tokens[0]
    return len(first_token) >= 5 and first_token in text_tokens

def _followup_list_chunk_support_score(items: list[str], text: str) -> float:
    """Score how strongly a chunk supports a previously returned list."""
    text_value = str(text or "")
    if not text_value.strip():
        return 0.0
    text_low = text_value.lower()
    score = 0.0
    matched_items = 0
    for item in items or []:
        item_head = _followup_item_head(item)
        item_low = item_head.lower()
        if not item_low:
            continue
        if _re_followup.search(r"\b" + _re_followup.escape(item_low) + r"\b", text_low):
            score += 2.0
            matched_items += 1
        elif _followup_text_mentions_item(text_value, item_head):
            score += 1.0
            matched_items += 1
    if matched_items >= 3:
        score += 3.0
    return score

def _followup_text_has_item_head_anchor(text: str, item: str) -> bool:
    """True when text contains the full item head or its first content token."""
    text_low = str(text or "").lower()
    item_head = _followup_item_head(item)
    item_low = item_head.lower()
    if not text_low.strip() or not item_low:
        return False
    if _re_followup.search(r"\b" + _re_followup.escape(item_low) + r"\b", text_low):
        return True
    item_tokens = _followup_content_tokens(item_head)
    if not item_tokens:
        return False
    first_token = item_tokens[0]
    if len(first_token) < 3:
        return False
    return bool(_re_followup.search(r"\b" + _re_followup.escape(first_token) + r"\b", text_low))

_FOLLOWUP_ORDINAL_WORDS: dict[str, int] = {
    "first": 1, "1st": 1,
    "second": 2, "2nd": 2,
    "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4,
    "fifth": 5, "5th": 5,
    "sixth": 6, "6th": 6,
    "seventh": 7, "7th": 7,
    "eighth": 8, "8th": 8,
    "ninth": 9, "9th": 9,
    "tenth": 10, "10th": 10,
}

_FOLLOWUP_ORDINAL_RE = _re_followup.compile(
    r"\b(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|"
    r"sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|last|final)\b"
    r"(?:\s+(?:one|item|element|thing|point|step|function|part|option|reason|"
    r"principle|stage|phase|category|type|kind))?",
    _re_followup.IGNORECASE,
)

def _resolve_followup_ordinal(items: list[str], text: str) -> tuple[str | None, str]:
    """Return (item, reason) when the query contains an unambiguous ordinal
    reference into ``items``. Generic — no domain words.
    Returns (None, "") when no ordinal applies, ("", "ambiguous") when
    multiple distinct ordinals are mentioned (caller should fall through
    to other matching strategies), or ("", "out_of_range") when the
    ordinal exceeds the list length.
    """
    if not items:
        return None, ""
    matches = _FOLLOWUP_ORDINAL_RE.findall(str(text or ""))
    if not matches:
        return None, ""
    indices: list[int] = []
    for tok in matches:
        low = tok.lower()
        if low in ("last", "final"):
            indices.append(len(items))
        else:
            n = _FOLLOWUP_ORDINAL_WORDS.get(low)
            if n is not None:
                indices.append(n)
    indices = list(dict.fromkeys(indices))  # dedupe, preserve order
    if not indices:
        return None, ""
    if len(indices) > 1:
        # E.g. "how does the first one differ from the last one?" — the
        # query references multiple items; let the token-overlap path
        # decide instead of forcing a single pick.
        return "", "ambiguous"
    idx = indices[0]
    if idx < 1 or idx > len(items):
        return "", "out_of_range"
    return items[idx - 1], f"ordinal_{idx}"

def _select_followup_target_item(items: list[str], text: str) -> tuple[str | None, str]:
    """Return the single prior-list item referenced by a follow-up query."""
    cleaned_items = [
        re.sub(r"\s+", " ", str(item or "").strip().strip(" .;:-"))
        for item in (items or [])
    ]
    cleaned_items = [item for item in cleaned_items if item]
    if not cleaned_items:
        return None, "no_items"

    # P11A: try unambiguous ordinal resolution first ("the second one",
    # "the last function", "explain 2nd"). Falls through on no match,
    # ambiguity, or out-of-range so the existing token-overlap path runs.
    ord_item, ord_reason = _resolve_followup_ordinal(cleaned_items, text)
    if ord_item:
        return ord_item, ord_reason

    query_low = str(text or "").lower()
    query_tokens = {
        token for token in _re_followup.findall(r"[a-z0-9]{3,}", query_low)
        if token not in _FOLLOWUP_TARGET_STOPWORDS
    }
    if not query_tokens:
        return None, "no_query_tokens"

    token_owner_count: dict[str, int] = {}
    item_tokens_by_item: dict[str, list[str]] = {}
    for item in cleaned_items:
        tokens = _followup_content_tokens(_followup_item_head(item))
        item_tokens_by_item[item] = tokens
        for token in set(tokens):
            token_owner_count[token] = token_owner_count.get(token, 0) + 1

    candidates: list[tuple[float, str, str]] = []
    for item in cleaned_items:
        item_head = _followup_item_head(item)
        item_low = item_head.lower()
        item_tokens = item_tokens_by_item.get(item) or []
        if not item_low or not item_tokens:
            continue
        if _re_followup.search(r"\b" + _re_followup.escape(item_low) + r"\b", query_low):
            candidates.append((3.0, item, "phrase"))
            continue
        overlap_tokens = [token for token in item_tokens if token in query_tokens]
        if not overlap_tokens:
            continue
        if len(item_tokens) == 1:
            candidates.append((2.5, item, "single_token"))
            continue
        first_token = item_tokens[0]
        unique_first = (
            first_token in query_tokens
            and token_owner_count.get(first_token, 0) == 1
            and len(first_token) >= 5
        )
        if len(overlap_tokens) >= 2:
            score = 2.0 + (len(overlap_tokens) / max(1, len(item_tokens)))
            candidates.append((score, item, "token_overlap"))
        elif unique_first:
            candidates.append((1.8, item, "unique_head_token"))

    if not candidates:
        return None, "no_match"
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    best_score, best_item, best_reason = candidates[0]
    tied = [candidate for candidate in candidates if abs(candidate[0] - best_score) < 0.01]
    if len(tied) > 1:
        return None, "ambiguous"
    return best_item, best_reason

def _sentence_mentions_many_followup_items(sentence: str, items: list[str]) -> bool:
    hits = 0
    for item in items or []:
        if _followup_text_mentions_item(sentence, item):
            hits += 1
        if hits >= 3:
            return True
    return False

def _split_followup_sentences(text: str) -> list[str]:
    pieces = _re_followup.split(r"(?<=[.!?:;])\s+|\n+|---+", str(text or ""))
    return [re.sub(r"\s+", " ", piece).strip() for piece in pieces if piece and piece.strip()]

def _split_followup_explanation_sentences(text: str) -> list[str]:
    pieces = _re_followup.split(r"(?<=[.!?])\s+|\n+|---+", str(text or ""))
    return [re.sub(r"\s+", " ", piece).strip() for piece in pieces if piece and piece.strip()]

_FOLLOWUP_COURSE_HEADER_RE = _re_followup.compile(
    r"^\s*"
    r"(?:(?i:Introduction\s+to)\s+[^.!?;:\n]{1,90}?\s+[\-\u2013\u2014]?\s*)?"
    r"[A-Z]{2,}\s*[\- ]?\d{2,}[A-Z0-9-]*\b"
    r"[\s,;:\-\u2013\u2014]*(?:[A-Z]{2,6}\b[\s,;:\-\u2013\u2014]*)?"
)

_FOLLOWUP_COPYRIGHT_PREFIX_RE = _re_followup.compile(
    r"^\s*(?:\u00a9\s*)?copyright\b[^.!?]{0,180}(?:[.!?]\s*|\s+|$)",
    _re_followup.IGNORECASE,
)

_FOLLOWUP_PAGE_PREFIX_RE = _re_followup.compile(
    r"^\s*(?:page\s*)?\d+\s*(?:of|/)\s*\d+\b[\s:;,\.\-]*",
    _re_followup.IGNORECASE,
)

_FOLLOWUP_ORPHAN_HEADER_TOKEN_RE = _re_followup.compile(
    r"^\s*[A-Z]{2,6}\b[\s,;:\-\u2013\u2014]+"
)

_FOLLOWUP_FRAGMENT_START_RE = _re_followup.compile(
    r"^\s*(?:and|or|but|which|who|whose|where|when|while|because|although|though|"
    r"of|from|to|into|by|with|than)\b",
    _re_followup.IGNORECASE,
)

_FOLLOWUP_FRAGMENT_CLAUSE_RE = _re_followup.compile(
    r"^[^.!?]{5,180}[;:]\s+(?:and\s+)?(?=(?:this|that|these|those|it|they|there|the|a|an)\b)",
    _re_followup.IGNORECASE,
)

_FOLLOWUP_LEADING_CONJUNCTION_RE = _re_followup.compile(
    r"^\s*(?:and|but|or)\s+(?=(?:this|that|these|those|it|they|there|the|a|an)\b)",
    _re_followup.IGNORECASE,
)

_FOLLOWUP_OCR_SPLIT_WORD_RE = _re_followup.compile(
    r"\b([a-z]{4,})\s+"
    r"(eved|ieved|tion|sion|ment|ments|ness|able|ible|ally|ance|ence|ive|ous|ful|less|ing|ed|ine|ves)\b",
    _re_followup.IGNORECASE,
)

_OCR_MERGED_PREFIX_WORD_RE = _re_followup.compile(
    r"\b(the|and|for|from|with|into|onto|about|after|before)([a-z]{5,18})\b",
    _re_followup.IGNORECASE,
)

_OCR_PREFIX_REMAINDER_SUFFIX_RE = _re_followup.compile(
    r"(?:tion|sion|ment|ments|ness|ities|ity|ance|ence|ure|ures|ism|isms|ist|ists|ship|ships|logy|ology|graphy|ess)$",
    _re_followup.IGNORECASE,
)

def _followup_capitalize_sentence_start(value: str) -> str:
    if value and value[0].islower():
        return value[0].upper() + value[1:]
    return value

def _followup_strip_header_prefix(value: str) -> tuple[str, bool]:
    cleaned = str(value or "")
    changed = False
    for _ in range(3):
        before = cleaned
        cleaned = _FOLLOWUP_COPYRIGHT_PREFIX_RE.sub("", cleaned)
        cleaned = _FOLLOWUP_PAGE_PREFIX_RE.sub("", cleaned)
        cleaned = _FOLLOWUP_COURSE_HEADER_RE.sub("", cleaned)
        if cleaned != before:
            changed = True
            cleaned = cleaned.lstrip(" \t\r\n,;:-\u2013\u2014")
            cleaned = _FOLLOWUP_ORPHAN_HEADER_TOKEN_RE.sub("", cleaned).lstrip(" \t\r\n,;:-\u2013\u2014")
            continue
        break
    return cleaned, changed

def _followup_merge_safe_ocr_split_words(value: str) -> tuple[str, bool]:
    changed = False

    def _merge(match: re.Match) -> str:
        nonlocal changed
        left = match.group(1)
        right = match.group(2)
        if left.lower() in _EVIDENCE_STOPWORDS or right.lower() in _EVIDENCE_STOPWORDS:
            return match.group(0)
        combined = left + right
        if not (6 <= len(combined) <= 20):
            return match.group(0)
        if not re.search(r"[aeiou]", combined):
            return match.group(0)
        if re.search(r"([a-z])\1\1", combined):
            return match.group(0)
        changed = True
        return combined

    cleaned = _FOLLOWUP_OCR_SPLIT_WORD_RE.sub(_merge, str(value or ""))
    return cleaned, changed

def _split_safe_ocr_merged_prefix_words(value: str) -> tuple[str, bool]:
    changed = False

    def _split(match: re.Match) -> str:
        nonlocal changed
        prefix = match.group(1)
        remainder = match.group(2)
        combined = prefix + remainder
        if not (8 <= len(combined) <= 24):
            return match.group(0)
        if remainder.lower() in _EVIDENCE_STOPWORDS:
            return match.group(0)
        if not re.search(r"[aeiou]", remainder, flags=re.IGNORECASE):
            return match.group(0)
        if not _OCR_PREFIX_REMAINDER_SUFFIX_RE.search(remainder):
            return match.group(0)
        changed = True
        return f"{prefix} {remainder}"

    cleaned = _OCR_MERGED_PREFIX_WORD_RE.sub(_split, str(value or ""))
    return cleaned, changed

def _followup_salvage_fragment_clause(value: str) -> tuple[str, bool]:
    match = _FOLLOWUP_FRAGMENT_CLAUSE_RE.search(value or "")
    if not match:
        return value, False
    candidate = (value or "")[match.end():].strip(" \t\r\n,;:-\u2013\u2014")
    candidate = _FOLLOWUP_LEADING_CONJUNCTION_RE.sub("", candidate).strip()
    if not candidate:
        return value, False
    return _followup_capitalize_sentence_start(candidate), True

def _cleanup_followup_extracted_answer(
    sentence: str,
    target_item: str,
) -> tuple[str, bool, str]:
    """Clean an already-grounded follow-up sentence without adding content."""
    original = re.sub(r"\s+", " ", str(sentence or "")).strip(" \t\r\n-*\u2022")
    if not original:
        return "", False, "empty"

    cleaned, header_removed = _followup_strip_header_prefix(original)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n-*\u2022")
    cleaned, prefix_changed = _split_safe_ocr_merged_prefix_words(cleaned)
    cleaned, ocr_changed = _followup_merge_safe_ocr_split_words(cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n,;:-\u2013\u2014")

    fragment_changed = False
    if header_removed and cleaned and cleaned[0].islower():
        salvaged, fragment_changed = _followup_salvage_fragment_clause(cleaned)
        if fragment_changed:
            cleaned = salvaged
        elif not _followup_text_has_item_head_anchor(cleaned, target_item):
            return "", (cleaned != original or prefix_changed or ocr_changed), "fragment_after_header"

    if _FOLLOWUP_FRAGMENT_START_RE.match(cleaned):
        before = cleaned
        cleaned = _FOLLOWUP_LEADING_CONJUNCTION_RE.sub("", cleaned).strip()
        if cleaned == before:
            return "", (cleaned != original or prefix_changed or ocr_changed), "fragment_start"
        fragment_changed = True

    cleaned = _followup_capitalize_sentence_start(cleaned.strip())
    if target_item and not _followup_text_has_item_head_anchor(cleaned, target_item):
        return "", (cleaned != original or prefix_changed or ocr_changed or fragment_changed), "target_removed"
    if not cleaned:
        return "", (cleaned != original or prefix_changed or ocr_changed or fragment_changed), "empty_after_cleanup"
    if not re.search(r"[.!?]$", cleaned):
        cleaned += "."
    return cleaned[:1000].strip(), (cleaned != original or prefix_changed or ocr_changed or fragment_changed), ""

def _extract_followup_context_window(text: str, target_item: str, char_budget: int = 1800) -> str:
    """Return nearby sentences/paragraph text around a targeted list item."""
    if not text or not target_item:
        return ""
    paragraphs = [
        paragraph.strip()
        for paragraph in _re_followup.split(r"\n\s*\n|---+", str(text or ""))
        if paragraph and paragraph.strip()
    ]
    selected: list[str] = []
    for paragraph in paragraphs:
        if not _followup_text_mentions_item(paragraph, target_item):
            continue
        sentences = _split_followup_sentences(paragraph)
        if not sentences:
            selected.append(re.sub(r"\s+", " ", paragraph)[:char_budget])
            continue
        for index, sentence in enumerate(sentences):
            if not _followup_text_mentions_item(sentence, target_item):
                continue
            start_index = max(0, index - 2)
            end_index = min(len(sentences), index + 4)
            selected.append(" ".join(sentences[start_index:end_index]))
    if not selected:
        return ""
    compact = " ".join(dict.fromkeys(selected))
    return re.sub(r"\s+", " ", compact).strip()[:char_budget]

def _build_followup_excerpts(last_chunks: list[dict], target_item: str | None = None) -> str:
    """Build saved follow-up context, focused around the target when present."""
    excerpt_parts: list[str] = []
    total_chars = 0
    if target_item:
        for chunk in (last_chunks or [])[:_FOLLOWUP_KEEP_TOP_K]:
            if not isinstance(chunk, dict):
                continue
            chunk_text = str(chunk.get("text") or "").strip()
            focused = _extract_followup_context_window(chunk_text, target_item)
            if not focused:
                continue
            remaining = _FOLLOWUP_CHUNK_CHAR_BUDGET - total_chars
            if remaining <= 0:
                break
            excerpt_parts.append(focused[:remaining])
            total_chars += len(excerpt_parts[-1])
    if not excerpt_parts:
        for chunk in (last_chunks or [])[:_FOLLOWUP_KEEP_TOP_K]:
            if not isinstance(chunk, dict):
                continue
            chunk_text = str(chunk.get("text") or "").strip()
            if not chunk_text:
                continue
            remaining = _FOLLOWUP_CHUNK_CHAR_BUDGET - total_chars
            if remaining <= 0:
                break
            excerpt_parts.append(chunk_text[:remaining])
            total_chars += len(excerpt_parts[-1])
    return "\n\n---\n\n".join(excerpt_parts)

def _extract_followup_strong_explanation(
    target_item: str,
    excerpts_block: str,
    previous_items: list[str],
    emit_cleanup_logs: bool = True,
    apply_cleanup: bool = True,
) -> str:
    """Extract a coherent explanatory block for a targeted item, if present."""
    if not target_item or not excerpts_block:
        return ""
    best_block = ""
    best_raw_block = ""
    best_cleanup_changed = False
    best_score = -1
    sections = [
        re.sub(r"\s+", " ", section).strip()
        for section in _re_followup.split(r"\n\s*(?:---+|={3,}|\*{3,})\s*\n|\n\s*\n", excerpts_block)
        if section and section.strip()
    ] or [re.sub(r"\s+", " ", excerpts_block).strip()]

    def _sentence_content_tokens(sentence_value: str) -> list[str]:
        return [
            word for word in _re_followup.findall(r"[a-z0-9]{4,}", sentence_value.lower())
            if word not in _EVIDENCE_STOPWORDS
        ]

    def _sentence_is_noisy_list_fragment(sentence_value: str) -> bool:
        separators_local = len(_re_followup.findall(r"(?:^|\s)[-*\u2022]\s|\s[-\u2013]\s|,\s", sentence_value))
        words_local = _re_followup.findall(r"[a-z]{3,}", sentence_value.lower())
        if (
            _sentence_mentions_many_followup_items(sentence_value, previous_items)
            and separators_local >= 2
            and len(words_local) < separators_local * 7
        ):
            return True
        return bool(separators_local >= 3 and len(words_local) < separators_local * 5)

    def _sentence_is_ocr_fragment(sentence_value: str) -> bool:
        sentence_clean = re.sub(r"\s+", " ", str(sentence_value or "")).strip()
        if not sentence_clean:
            return True
        words_local = _re_followup.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", sentence_clean)
        if len(words_local) < 4:
            return True
        if _re_followup.search(r"(?:\b[A-Za-z]\s+){4,}[A-Za-z]\b", sentence_clean):
            return True
        if not _EXPLAIN_VERB_RE.search(sentence_clean.lower()) and len(words_local) < 7:
            return True
        return False

    def _sentence_content_count(sentence_value: str) -> int:
        return len(_sentence_content_tokens(sentence_value))

    def _definition_style_score(sentence_value: str) -> float:
        sentence_low = sentence_value.lower()
        score_local = 0.0
        if _FOLLOWUP_EXPLANATORY_CUE_RE.search(sentence_value):
            score_local += 6.0
        if _EXPLAIN_VERB_RE.search(sentence_low):
            score_local += 3.0
        if _re_followup.search(r"\b(?:because|therefore|thus|so|so that|in order to)\b", sentence_low):
            score_local += 1.5
        if _followup_text_has_item_head_anchor(sentence_value, target_item):
            score_local += 2.0
        if _sentence_content_count(sentence_value) >= 8:
            score_local += 1.0
        return score_local

    def _labeled_item_block(section_value: str) -> str:
        target_head = _followup_item_head(target_item)
        if not target_head:
            return ""
        target_pattern = _re_followup.compile(
            r"(?:^|\s)(?:[A-Z]\s*[\.)]\s*)?"
            + _re_followup.escape(target_head)
            + r"\s*[:\-]\s*",
            _re_followup.IGNORECASE,
        )
        match = target_pattern.search(section_value)
        if not match:
            return ""
        tail = section_value[match.end():]
        stop_at = len(tail)
        for other_item in previous_items or []:
            other_head = _followup_item_head(other_item)
            if not other_head or other_head.lower() == target_head.lower():
                continue
            other_pattern = _re_followup.compile(
                r"\s+[A-Z]\s*[\.)]\s*"
                + _re_followup.escape(other_head)
                + r"\s*[:\-]\s*",
                _re_followup.IGNORECASE,
            )
            other_match = other_pattern.search(tail)
            if other_match:
                stop_at = min(stop_at, other_match.start())
        candidate = f"{target_head}: {tail[:stop_at]}"
        candidate_sentences = _split_followup_explanation_sentences(candidate)
        candidate = " ".join(candidate_sentences[:3]).strip()
        if not candidate or len(_sentence_content_tokens(candidate)) < 8:
            return ""
        if not (_EXPLAIN_VERB_RE.search(candidate.lower()) or _FOLLOWUP_EXPLANATORY_CUE_RE.search(candidate)):
            return ""
        if _sentence_mentions_many_followup_items(candidate, previous_items):
            return ""
        clean_candidate = candidate
        if apply_cleanup:
            clean_candidate, cleanup_changed, reject_reason = _cleanup_followup_extracted_answer(
                candidate, target_item
            )
            if reject_reason:
                if emit_cleanup_logs:
                    S.logger.info(
                        "[FOLLOWUP NOISY SENTENCE REJECTED] reason=%s sentence=%r",
                        reject_reason,
                        candidate[:180],
                    )
                return ""
            if emit_cleanup_logs and cleanup_changed:
                S.logger.info(
                    "[FOLLOWUP CLEANUP APPLIED] before=%r after=%r",
                    candidate[:180],
                    clean_candidate[:180],
                )
        clean_candidate = re.sub(r"\s+", " ", clean_candidate).strip(" \t\r\n-*")
        if clean_candidate and not re.search(r"[.!?]$", clean_candidate):
            clean_candidate += "."
        return clean_candidate[:1000].strip()

    def _continuity_score(sentence_value: str, running_tokens: set[str], anchor_tokens: set[str]) -> float:
        sentence_tokens = set(_sentence_content_tokens(sentence_value))
        if not sentence_tokens:
            return -1.0
        overlap_running = len(sentence_tokens & running_tokens)
        overlap_anchor = len(sentence_tokens & anchor_tokens)
        connector = bool(
            _re_followup.match(
                r"^\s*(?:this|that|these|those|it|they|such|another|also|therefore|thus|because)\b",
                sentence_value,
                _re_followup.IGNORECASE,
            )
        )
        cue = bool(_FOLLOWUP_EXPLANATORY_CUE_RE.search(sentence_value) or _EXPLAIN_VERB_RE.search(sentence_value.lower()))
        score_local = 0.0
        score_local += min(3.0, float(overlap_running) * 1.25)
        score_local += min(2.0, float(overlap_anchor))
        if connector:
            score_local += 2.0
        if cue:
            score_local += 1.5
        return score_local

    for section in sections:
        labeled_block = _labeled_item_block(section)
        if labeled_block:
            if emit_cleanup_logs:
                S.logger.info("[FOLLOWUP CLEAN ANSWER] %s", labeled_block[:240])
            return labeled_block
        sentences = _split_followup_explanation_sentences(section)
        for index, sentence in enumerate(sentences):
            if not _followup_text_has_item_head_anchor(sentence, target_item):
                continue
            if _sentence_is_noisy_list_fragment(sentence) or _sentence_is_ocr_fragment(sentence):
                continue
            has_verb = bool(_EXPLAIN_VERB_RE.search(sentence.lower()))
            content_count = _sentence_content_count(sentence)
            if not ((has_verb and content_count >= 3) or content_count >= 7):
                continue
            has_explanatory_cue = bool(_FOLLOWUP_EXPLANATORY_CUE_RE.search(sentence))
            complete_statement = bool(
                has_explanatory_cue
                and len(_re_followup.findall(r"[a-z0-9]{3,}", sentence.lower())) >= 8
            )

            anchor_tokens = set(_sentence_content_tokens(sentence))
            target_tokens = set(_followup_content_tokens(target_item))
            block_sentences = [sentence]

            if index > 0:
                previous_sentence = sentences[index - 1]
                if (
                    not _sentence_is_noisy_list_fragment(previous_sentence)
                    and not _sentence_is_ocr_fragment(previous_sentence)
                    and _sentence_content_count(previous_sentence) >= 4
                ):
                    previous_tokens = set(_sentence_content_tokens(previous_sentence))
                    previous_connected = bool(
                        (previous_tokens & (anchor_tokens | target_tokens))
                        or _FOLLOWUP_EXPLANATORY_CUE_RE.search(previous_sentence)
                        or _EXPLAIN_VERB_RE.search(previous_sentence.lower())
                    )
                    if previous_connected:
                        block_sentences.insert(0, previous_sentence)

            running_tokens = set()
            for block_sentence in block_sentences:
                running_tokens.update(_sentence_content_tokens(block_sentence))
            running_tokens.update(target_tokens)

            continuity_total = 0.0
            for next_sentence in sentences[index + 1:index + 4]:
                if len(block_sentences) >= 4:
                    break
                if _sentence_is_noisy_list_fragment(next_sentence) or _sentence_is_ocr_fragment(next_sentence):
                    break
                next_content_count = _sentence_content_count(next_sentence)
                if next_content_count < 4:
                    break
                continuation_score = _continuity_score(next_sentence, running_tokens, anchor_tokens | target_tokens)
                if continuation_score < 2.0:
                    break
                continuity_total += continuation_score
                block_sentences.append(next_sentence)
                running_tokens.update(_sentence_content_tokens(next_sentence))

            unique_sentence_count = len([s for s in dict.fromkeys(block_sentences) if s])
            if unique_sentence_count < 2:
                continue

            raw_block = " ".join(block_sentences)
            if _sentence_mentions_many_followup_items(raw_block, previous_items):
                if emit_cleanup_logs:
                    S.logger.info(
                        "[FOLLOWUP NOISY SENTENCE REJECTED] reason=multi_item_enumeration sentence=%r",
                        raw_block[:180],
                    )
                continue
            separators = len(_re_followup.findall(r"(?:^|\s)[-*\u2022]\s|\s[-\u2013]\s|,\s", raw_block))
            topic_consistency = 0.0
            for block_sentence in block_sentences:
                sentence_tokens = set(_sentence_content_tokens(block_sentence))
                if sentence_tokens:
                    topic_consistency += len(sentence_tokens & (anchor_tokens | target_tokens)) / max(1.0, float(len(sentence_tokens)))
            score = (
                content_count
                + (4 if has_verb else 0)
                + (6 if has_explanatory_cue else 0)
                + (2 if complete_statement else 0)
                + _definition_style_score(sentence)
                + continuity_total
                + (3 * (unique_sentence_count - 1))
                + (4.0 * topic_consistency)
                - (3 if separators >= 2 else 0)
            )
            cleanup_changed = False
            clean_block = raw_block
            if apply_cleanup:
                clean_block, cleanup_changed, reject_reason = _cleanup_followup_extracted_answer(
                    raw_block, target_item
                )
                if reject_reason:
                    if emit_cleanup_logs:
                        S.logger.info(
                            "[FOLLOWUP NOISY SENTENCE REJECTED] reason=%s sentence=%r",
                            reject_reason,
                            raw_block[:180],
                        )
                    continue
                clean_sentence_count = len(_split_followup_explanation_sentences(clean_block))
                if clean_sentence_count < 2 or clean_sentence_count > 4:
                    continue
                if not cleanup_changed:
                    score += 2
            if score > best_score:
                best_score = score
                best_block = clean_block
                best_raw_block = raw_block
                best_cleanup_changed = cleanup_changed
    if not best_block:
        return ""
    best_block = re.sub(r"\s+", " ", best_block).strip(" \t\r\n-*")
    if not re.search(r"[.!?]$", best_block):
        best_block += "."
    if emit_cleanup_logs and best_cleanup_changed:
        S.logger.info(
            "[FOLLOWUP CLEANUP APPLIED] before=%r after=%r",
            best_raw_block[:180],
            best_block[:180],
        )
    if emit_cleanup_logs:
        S.logger.info("[FOLLOWUP CLEAN ANSWER] %s", best_block[:240])
    return best_block[:1000].strip()

def _followup_explanation_candidate_score(
    target_item: str,
    candidate_text: str,
    previous_items: list[str] | None = None,
) -> float:
    """Score a follow-up candidate by generic explanatory sentence shape."""
    text_value = re.sub(r"\s+", " ", str(candidate_text or "")).strip()
    if not text_value or not _followup_text_mentions_item(text_value, target_item):
        return -1.0

    score = 0.0
    item_tokens = _followup_content_tokens(_followup_item_head(target_item))
    text_tokens = set(_re_followup.findall(r"[a-z0-9]{3,}", text_value.lower()))
    if item_tokens:
        overlap = 0
        for item_token in item_tokens:
            if item_token in text_tokens:
                overlap += 1
                continue
            if len(item_token) >= 5 and any(
                text_token.startswith(item_token) or item_token.startswith(text_token)
                for text_token in text_tokens
            ):
                overlap += 1
        score += min(8.0, overlap * 2.0)
        if len(item_tokens) >= 3 and overlap <= 1:
            score -= 8.0

    if _extract_followup_strong_explanation(
        target_item,
        text_value,
        previous_items or [],
        emit_cleanup_logs=False,
        apply_cleanup=False,
    ):
        score += 12.0
    if _evidence_has_explicit_explanation(target_item, text_value):
        score += 8.0

    for sentence in _split_followup_sentences(text_value):
        if not _followup_text_has_item_head_anchor(sentence, target_item):
            continue
        words = _re_followup.findall(r"[a-z0-9]{3,}", sentence.lower())
        separators = len(_re_followup.findall(r"(?:^|\s)[-*\u2022]\s|\s[-\u2013]\s|,\s", sentence))
        if _FOLLOWUP_EXPLANATORY_CUE_RE.search(sentence):
            score += 4.0
        if len(words) >= 8 and re.search(r"[.!?]$", sentence.strip()):
            score += 2.0
        if len(sentence) >= 80:
            score += 1.0
        if separators >= 3:
            score -= 4.0
        if previous_items and _sentence_mentions_many_followup_items(sentence, previous_items):
            score -= 3.0
    return score

def _followup_doc_text(candidate_doc: dict) -> str:
    return str(
        (candidate_doc or {}).get("text")
        or (candidate_doc or {}).get("page_content")
        or (candidate_doc or {}).get("content")
        or ""
    ).strip()

def _followup_doc_source(candidate_doc: dict) -> str:
    metadata = (candidate_doc or {}).get("metadata")
    source = (candidate_doc or {}).get("source")
    if (not source) and isinstance(metadata, dict):
        source = metadata.get("source") or metadata.get("doc_id") or metadata.get("file")
    return str(source or "").strip()

def _followup_doc_chunk_index(candidate_doc: dict) -> int | None:
    metadata = (candidate_doc or {}).get("metadata")
    raw_index = metadata.get("chunk_index") if isinstance(metadata, dict) else None
    if raw_index is None:
        raw_index = (candidate_doc or {}).get("chunk_index")
    if raw_index is None:
        return None
    try:
        return int(raw_index)
    except Exception:
        return None

def _followup_fetch_adjacent_chunk(
    source_name: str,
    chunk_index: int,
    target_item: str,
    allowed_sources: set[str],
) -> dict | None:
    try:
        collection = getattr(getattr(S.live_rag, "vs", None), "collection", None)
    except Exception:
        collection = None
    if collection is None or not source_name:
        return None

    rows = None
    where_candidates = [
        {"$and": [{"source": source_name}, {"chunk_index": int(chunk_index)}]},
        {"$and": [{"source": source_name}, {"chunk_index": str(chunk_index)}]},
    ]
    for where_clause in where_candidates:
        try:
            rows = collection.get(where=where_clause, include=["documents", "metadatas"])
        except Exception:
            rows = None
        if rows and rows.get("documents"):
            break
    if not rows or not rows.get("documents"):
        return None

    documents = rows.get("documents") or []
    metadatas = rows.get("metadatas") or []
    adjacent_text = str(documents[0] or "").strip() if documents else ""
    adjacent_metadata = dict(metadatas[0] or {}) if metadatas else {}
    adjacent_source = str(
        adjacent_metadata.get("source")
        or adjacent_metadata.get("doc_id")
        or adjacent_metadata.get("file")
        or source_name
        or ""
    ).strip()
    if allowed_sources and adjacent_source not in allowed_sources:
        return None
    if not adjacent_text or not _followup_text_mentions_item(adjacent_text, target_item):
        return None
    adjacent_focus = _extract_followup_context_window(adjacent_text, target_item) or adjacent_text
    return {"text": adjacent_focus[:600], "source": adjacent_source, "metadata": adjacent_metadata}

def _followup_expand_adjacent_chunks(
    seed_docs: list[dict],
    target_item: str,
    allowed_sources: set[str],
    previous_items: list[str],
) -> list[dict]:
    expanded: list[dict] = []
    seen_keys: set[tuple[str, int]] = set()
    for seed_doc in seed_docs or []:
        seed_source = _followup_doc_source(seed_doc)
        seed_index = _followup_doc_chunk_index(seed_doc)
        if not seed_source or seed_index is None:
            continue
        for adjacent_index in (seed_index - 1, seed_index + 1):
            adjacent_key = (seed_source, adjacent_index)
            if adjacent_key in seen_keys:
                continue
            seen_keys.add(adjacent_key)
            adjacent_doc = _followup_fetch_adjacent_chunk(
                seed_source, adjacent_index, target_item, allowed_sources
            )
            if adjacent_doc is None:
                continue
            expanded.append(adjacent_doc)
    expanded.sort(
        key=lambda candidate: _followup_explanation_candidate_score(
            target_item, _followup_doc_text(candidate), previous_items
        ),
        reverse=True,
    )
    return expanded[:2]

def _followup_lexical_explanation_rescue(
    focus_phrase: str,
    target_item: str,
    allowed_sources: set[str],
    previous_items: list[str],
    max_candidates: int = 16,
) -> list[dict]:
    """Find same-source chunks containing the focused item phrase.

    This is a bounded lexical rescue for follow-ups only. It uses the active
    Chroma collection as stored evidence, then applies the same generic
    explanatory sentence scoring used by semantic rescue.
    """
    phrase = re.sub(r"\s+", " ", str(focus_phrase or "").strip())
    if not phrase:
        return []
    try:
        collection = getattr(getattr(S.live_rag, "vs", None), "collection", None)
    except Exception:
        collection = None
    if collection is None:
        return []

    phrase_variants: list[str] = []
    for variant in (phrase, phrase.lower(), phrase.title()):
        if variant and variant not in phrase_variants:
            phrase_variants.append(variant)

    candidates: list[tuple[float, int, dict]] = []
    seen_keys: set[tuple[str, str]] = set()
    for phrase_variant in phrase_variants:
        try:
            rows = collection.get(
                where_document={"$contains": phrase_variant},
                include=["documents", "metadatas"],
                limit=max_candidates,
            )
        except TypeError:
            rows = collection.get(
                where_document={"$contains": phrase_variant},
                include=["documents", "metadatas"],
            )
        except Exception:
            S.logger.exception("[FOLLOWUP LEXICAL RESCUE] collection lookup failed")
            continue
        documents = (rows or {}).get("documents") or []
        metadatas = (rows or {}).get("metadatas") or []
        for order, document_text in enumerate(documents[:max_candidates]):
            text_value = str(document_text or "").strip()
            if not text_value:
                continue
            metadata = dict(metadatas[order] or {}) if order < len(metadatas) else {}
            source_value = str(
                metadata.get("source")
                or metadata.get("doc_id")
                or metadata.get("file")
                or ""
            ).strip()
            if allowed_sources and source_value not in allowed_sources:
                continue
            candidate_doc = {
                "text": text_value[:600],
                "source": source_value,
                "metadata": metadata,
            }
            if not _followup_text_mentions_item(text_value, focus_phrase):
                continue
            chunk_key = (source_value, str(metadata.get("chunk_index")))
            if chunk_key in seen_keys:
                continue
            seen_keys.add(chunk_key)
            score = _followup_explanation_candidate_score(
                target_item, text_value, previous_items
            )
            if score < 1.0:
                continue
            focused_text = (
                _extract_followup_context_window(text_value, focus_phrase)
                or _extract_followup_context_window(text_value, target_item)
                or text_value
            )
            candidate_doc["text"] = focused_text[:600]
            candidates.append((score, order, candidate_doc))

    candidates.sort(key=lambda row: (-row[0], row[1]))
    return [row[2] for row in candidates[:12]]

def _build_grounded_explanation(query, item, context_docs):
    S.logger.info("[FOLLOWUP EXPLANATION MODE] weak_evidence")

    item_text = _followup_item_head(item)
    if not item_text:
        S.logger.info("[FOLLOWUP EXPLANATION SOURCE] sentences_used=0")
        return RAG_NO_MATCH_RESPONSE

    if isinstance(context_docs, (str, bytes)) or context_docs is None:
        docs_iterable = [context_docs]
    else:
        try:
            docs_iterable = list(context_docs)
        except TypeError:
            docs_iterable = [context_docs]

    context_parts: list[str] = []
    for context_doc in docs_iterable:
        if context_doc is None:
            continue
        if isinstance(context_doc, dict):
            context_text = (
                context_doc.get("text")
                or context_doc.get("page_content")
                or context_doc.get("content")
                or ""
            )
        else:
            context_text = context_doc.decode("utf-8", errors="ignore") if isinstance(context_doc, bytes) else str(context_doc)
        context_text = re.sub(r"[ \t\r\f\v]+", " ", context_text or "")
        context_text = re.sub(r"\n{3,}", "\n\n", context_text).strip()
        if context_text:
            context_parts.append(context_text)

    context_text = "\n\n".join(context_parts)
    if not context_text:
        S.logger.info("[FOLLOWUP EXPLANATION SOURCE] sentences_used=0")
        return RAG_NO_MATCH_RESPONSE
    context_text = re.sub(r"(?m)(?:^|\s)[-*\u2022]\s+(?=[A-Za-z0-9])", "\n", context_text)
    context_text = re.sub(r"(?m)(?:^|\s)\d+[.)]\s+(?=[A-Za-z0-9])", "\n", context_text)

    strong_sentence = _extract_followup_strong_explanation(item_text, context_text, [])
    if strong_sentence:
        S.logger.info(
            "[FOLLOWUP EXPLANATION SOURCE] sentences_used=%d",
            max(1, len(_split_followup_explanation_sentences(strong_sentence))),
        )
        S.logger.info("[FOLLOWUP EXPLANATION LEVEL] weak_interpreted")
        return strong_sentence

    sentences = _split_followup_sentences(context_text)
    item_sentence_indexes = [
        index for index, sentence in enumerate(sentences)
        if _followup_text_has_item_head_anchor(sentence, item_text)
    ]
    if not item_sentence_indexes:
        S.logger.info("[FOLLOWUP EXPLANATION SOURCE] sentences_used=0")
        return RAG_NO_MATCH_RESPONSE

    query_tokens = set(_followup_content_tokens(query or ""))
    item_tokens = set(_followup_content_tokens(item_text))

    def _strip_marker(value: str) -> str:
        cleaned = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", value or "")
        return re.sub(r"\s+", " ", cleaned).strip(" \t\r\n.;")

    def _inline_phrase(value: str) -> str:
        phrase = _strip_marker(value).strip(" :")
        phrase = re.sub(
            r"\s+(?:are|were|is|was|include|includes|included|including|"
            r"consist(?:s|ed)?\s+of|comprise|comprises|contain|contains|"
            r"has|have)(?:\s+the\s+following)?\s*$",
            "",
            phrase,
            flags=re.IGNORECASE,
        ).strip(" :")
        if phrase.startswith("The "):
            phrase = "the " + phrase[4:]
        return phrase

    def _content_token_count(value: str) -> int:
        return len([
            token for token in _followup_content_tokens(value or "")
            if token not in item_tokens
        ])

    def _useful_phrase(value: str) -> bool:
        return bool(value and _content_token_count(value) > 0)

    def _relation_from_sentence(sentence: str) -> str:
        cleaned = _strip_marker(sentence)
        if not cleaned:
            return ""
        item_match = re.search(r"\b" + re.escape(item_text) + r"\b", cleaned, flags=re.IGNORECASE)
        before_item = cleaned[:item_match.start()] if item_match else cleaned
        relation_match = re.search(
            r"^(.+?)\s+(?:are|were|is|was|include|includes|included|including|"
            r"consist(?:s|ed)?\s+of|comprise|comprises|contain|contains|"
            r"has|have)(?:\s+the\s+following)?\b",
            before_item,
            flags=re.IGNORECASE,
        )
        if relation_match:
            phrase = _inline_phrase(relation_match.group(1))
            return phrase if _useful_phrase(phrase) else ""
        if cleaned.endswith(":") or re.search(
            r"\b(?:are|were|is|was|include|includes|included|including|"
            r"consist(?:s|ed)?\s+of|comprise|comprises|contain|contains|"
            r"has|have)\b",
            cleaned,
            flags=re.IGNORECASE,
        ):
            phrase = _inline_phrase(cleaned)
            return phrase if _useful_phrase(phrase) else ""
        return ""

    def _definition_fragment(sentence: str) -> str:
        cleaned = _strip_marker(sentence)
        item_match = re.search(r"\b" + re.escape(item_text) + r"\b", cleaned, flags=re.IGNORECASE)
        if not item_match:
            return ""
        after_item = cleaned[item_match.end():]
        fragment_match = re.match(r"\s*(?:[:\-\u2013\u2014]|is|are|means?|refers?\s+to)\s+(.+)$", after_item, flags=re.IGNORECASE)
        if not fragment_match:
            return ""
        fragment = _inline_phrase(fragment_match.group(1))
        return fragment if _useful_phrase(fragment) else ""

    selected_sentences: list[str] = []
    context_phrase = ""
    sibling_items: list[str] = []

    def _collect_sibling_items(item_index: int) -> list[str]:
        collected: list[str] = []
        sibling_window_start = max(0, item_index - 5)
        sibling_window_end = min(len(sentences), item_index + 6)
        for sibling_sentence in sentences[sibling_window_start:sibling_window_end]:
            sibling_label = _strip_marker(sibling_sentence)
            if not sibling_label or _followup_text_mentions_item(sibling_label, item_text):
                continue
            if len(_followup_content_tokens(sibling_label)) > 8:
                continue
            if re.search(r"[.!?]", sibling_label):
                continue
            collected.append(sibling_label)
            if len(collected) >= 3:
                break
        return collected

    relation_from_query = _infer_previous_list_relation_phrase(query or "")
    if relation_from_query and relation_from_query != "the listed items":
        first_item_index = item_sentence_indexes[0]
        context_phrase = relation_from_query
        selected_sentences = [sentences[first_item_index]]
        sibling_items = _collect_sibling_items(first_item_index)

    for item_index in item_sentence_indexes:
        if context_phrase:
            break
        item_sentence = sentences[item_index]
        selected_sentences.append(item_sentence)

        fragment = _definition_fragment(item_sentence)
        if fragment:
            context_phrase = fragment
            break

        for lookback_index in range(item_index, max(-1, item_index - 6), -1):
            candidate = sentences[lookback_index]
            relation = _relation_from_sentence(candidate)
            if relation:
                candidate_tokens = set(_followup_content_tokens(candidate))
                if not query_tokens or candidate_tokens.intersection(query_tokens) or lookback_index == item_index:
                    context_phrase = relation
                    if candidate not in selected_sentences:
                        selected_sentences.insert(0, candidate)
                    break
        if context_phrase:
            sibling_items = _collect_sibling_items(item_index)
            break

    if not context_phrase:
        for item_index in item_sentence_indexes:
            window_start = max(0, item_index - 1)
            window_end = min(len(sentences), item_index + 2)
            nearby = [_strip_marker(sentence) for sentence in sentences[window_start:window_end]]
            nearby = [sentence for sentence in nearby if sentence]
            joined = " ".join(dict.fromkeys(nearby)).strip()
            if _useful_phrase(joined):
                context_phrase = joined[:350].strip()
                selected_sentences = sentences[window_start:window_end]
                break

    if not _useful_phrase(context_phrase):
        S.logger.info("[FOLLOWUP EXPLANATION SOURCE] sentences_used=0")
        return RAG_NO_MATCH_RESPONSE

    if sibling_items:
        sibling_text = _join_short_item_names(sibling_items, max_items=3)
        if sibling_text:
            context_phrase = f"{context_phrase} in the same list as {sibling_text}"

    sentences_used = len([sentence for sentence in dict.fromkeys(selected_sentences) if sentence])
    S.logger.info("[FOLLOWUP EXPLANATION SOURCE] sentences_used=%d", sentences_used)
    S.logger.info("[FOLLOWUP EXPLANATION LEVEL] weak_interpreted")
    return f"This refers to {item_text}, which in the document is associated with {context_phrase}."

def _is_undirected_explain_more(user_text) -> bool:
    """True when a follow-up is a broad 'explain more' (no specific item),
    e.g. 'explain more', 'tell me more', 'elaborate', 'expand'."""
    t = re.sub(r"\s+", " ", str(user_text or "").strip().lower())
    if not t:
        return False
    if t in {"more", "more please", "explain", "explain more", "tell me more", "elaborate", "expand"}:
        return True
    return bool(
        re.fullmatch(
            r"(?:please\s+)?(?:can\s+you\s+)?(?:explain|elaborate|expand|tell\s+me)"
            r"(?:\s+(?:more|further|again|on\s+(?:it|this|that)|it|this|that))?",
            t,
        )
    )

def _build_consolidated_grounded_explanation(query, items, context_docs) -> str:
    """For an undirected 'explain more', produce ONE concise, grounded
    summary instead of a repetitive per-item template. Only items that
    actually appear in the retrieved context are referenced."""
    parts: list[str] = []
    docs_iterable = context_docs if isinstance(context_docs, (list, tuple)) else [context_docs]
    for context_doc in docs_iterable:
        if context_doc is None:
            continue
        if isinstance(context_doc, dict):
            text = (
                context_doc.get("text")
                or context_doc.get("page_content")
                or context_doc.get("content")
                or ""
            )
        elif isinstance(context_doc, bytes):
            text = context_doc.decode("utf-8", errors="ignore")
        else:
            text = str(context_doc)
        text = re.sub(r"\s+", " ", text or "").strip()
        if text:
            parts.append(text)
    context_text = " ".join(parts).strip()
    if not context_text:
        return ""

    haystack = context_text.lower()
    anchored: list[str] = []
    seen: set[str] = set()
    for raw_item in items or []:
        head = _followup_item_head(raw_item)
        if not head:
            continue
        key = head.lower()
        if key in seen:
            continue
        if _followup_text_mentions_item(haystack, head):
            anchored.append(head)
            seen.add(key)
    if not anchored:
        return ""

    names = _join_short_item_names(anchored, max_items=6) or ", ".join(anchored)
    return (
        "Regarding your question, here are the related points from our help "
        f"materials: {names}."
    )

def _build_grounded_explanations_for_items(
    query, items, context_docs, user_text=None, targeted_item=None
):
    # Directed follow-up about one specific item keeps the precise,
    # per-item grounded explanation.
    if targeted_item:
        explanation = _build_grounded_explanation(query, targeted_item, context_docs)
        if explanation and explanation != RAG_NO_MATCH_RESPONSE:
            return explanation
        return ""

    # Broad/undirected "explain more" gets a single consolidated answer so
    # the customer doesn't receive a repetitive template per list item.
    if user_text is not None and _is_undirected_explain_more(user_text):
        consolidated = _build_consolidated_grounded_explanation(query, items, context_docs)
        if consolidated:
            return consolidated

    explanations: list[str] = []
    for explanation_item in items or []:
        explanation = _build_grounded_explanation(query, explanation_item, context_docs)
        if explanation and explanation != RAG_NO_MATCH_RESPONSE:
            explanations.append(explanation)
    return "\n".join(explanations).strip()

def _build_followup_targeted_evidence_answer(
    target_item: str,
    previous_items: list[str],
    previous_query: str,
    previous_answer: str,
    excerpts_block: str,
) -> tuple[str, str]:
    """Three-level strict response for targeted list-item follow-ups."""
    anchored_items = _followup_items_anchored([target_item], excerpts_block, previous_answer)
    if not anchored_items:
        return RAG_NO_MATCH_RESPONSE, "no_evidence"

    strong_answer = _extract_followup_strong_explanation(
        target_item, excerpts_block, previous_items
    )
    if strong_answer:
        return strong_answer, "strong"

    return "", "weak"

def _followup_items_anchored(
    items: list[str], excerpts_block: str, last_a: str
) -> list[str]:
    """Return the subset of *items* whose name appears (whole-word) in the
    retrieved chunks (``excerpts_block``) or in the previous answer
    (which itself was generated from those chunks). Used as the safety
    gate for the controlled-explanation mode: an item that never appears
    in the document context is NEVER explained by the LLM.
    """
    if not items:
        return []
    haystack = ((excerpts_block or "") + "\n" + (last_a or "")).lower()
    if not haystack.strip():
        return []
    anchored: list[str] = []
    for it in items:
        head = _followup_item_head(it)
        if not head:
            continue
        if _followup_text_mentions_item(haystack, head):
            anchored.append(it)
    return anchored

async def _followup_controlled_explanation(
    items: list[str],
    last_q: str,
    last_a: str,
    excerpts_block: str,
    user_text: str,
) -> str:
    """Build controlled follow-up explanations from saved grounded text only."""
    if not items:
        return ""
    grounded_query = (last_q or user_text or "").strip()
    return _build_grounded_explanations_for_items(
        grounded_query,
        items,
        [{"text": excerpts_block}, {"text": last_a}],
    )

async def _handle_followup_query(text: str, connection_id: str):
    """Answer a follow-up clarification using ONLY the previous answer +
    a small window of the previously retrieved chunks. No new retrieval
    is performed in the primary path, keeping latency well below a normal
    query. Returns (answer_text, doc_dicts_list)."""
    if _is_weak_generic_request(text):
        S.logger.info("[ANSWER PERMISSION] allowed=False reason=weak_generic_followup_request")
        return (RAG_NO_MATCH_RESPONSE, [])
    if _is_memory_rewrite_query(text):
        return await _handle_memory_rewrite_query(text, connection_id)
    state = _get_last_answer_state(connection_id)
    if not state:
        S.logger.info("[FOLLOWUP] no prior state for connection_id=%s -> not_found", connection_id)
        S.logger.info("[SMART MEMORY] rejected_reason=no_prior_grounded_answer")
        return (RAG_NO_MATCH_RESPONSE, [])

    followup_action = _classify_followup_intent(text)
    intent = "explanation"
    is_followup = True
    S.logger.info("[FOLLOWUP MODE] list_lock_disabled=True")
    S.logger.info("[FOLLOWUP MERGE] enabled=True")
    last_q = state.get("query", "") or ""
    last_a = state.get("answer", "") or ""
    last_chunks = state.get("chunks", []) or []
    base_list_q = state.get("list_query", "") or last_q
    base_list_a = state.get("list_answer", "") or last_a
    stored_items = [
        re.sub(r"\s+", " ", str(item or "").strip().strip(" .;:-"))
        for item in (state.get("items") or [])
    ]
    stored_items = [item for item in stored_items if item]
    excerpts_block = _build_followup_excerpts(last_chunks)

    # --- detect whether the current saved answer is a list ---
    prev_is_list, extracted_items = _extract_followup_items_from_answer(last_a)
    list_detected = prev_is_list
    if is_followup:
        list_detected = False
    target_item_pool = extracted_items if extracted_items else stored_items
    previous_list_items_all = list(extracted_items if extracted_items else stored_items)

    # --- single-item targeting -------------------------------------
    # If the user's follow-up query mentions exactly ONE of the items
    # we extracted from the previous answer, restrict the rest of the
    # follow-up flow to just that item. Matching is purely against the
    # previously extracted list items (no hardcoded vocabulary).
    targeted_item: str | None = None
    if target_item_pool:
        try:
            targeted_item, target_reason = _select_followup_target_item(
                target_item_pool, text
            )
            if targeted_item:
                S.logger.info(
                    "[FOLLOWUP ITEM DETECTION] item=%r reason=%s query=%r",
                    targeted_item, target_reason, (text or "")[:120],
                )
                S.logger.info(
                    "[FOLLOWUP ITEM TARGET] item=%r query=%r",
                    targeted_item, (text or "")[:120],
                )
            else:
                S.logger.info(
                    "[FOLLOWUP ITEM DETECTION] no_single_item reason=%s query=%r",
                    target_reason, (text or "")[:120],
                )
        except Exception:
            S.logger.exception("[FOLLOWUP ITEM TARGET] detection failed")
            targeted_item = None

    if targeted_item is not None and not extracted_items and stored_items:
        prev_is_list = True
        extracted_items = list(stored_items)
        previous_list_items_all = list(stored_items)
        last_q = base_list_q
        last_a = base_list_a

    # When a single item is targeted, narrow the working item list to
    # just that item. Everything downstream (prompt template, retry,
    # coverage check, deterministic placeholder) then operates on the
    # single item only.
    if targeted_item is not None:
        extracted_items = [targeted_item]
        excerpts_block = _build_followup_excerpts(last_chunks, targeted_item)
        S.logger.info(
            "[FOLLOWUP CONTEXT BUILD] target=%r chars=%d chunks=%d",
            targeted_item, len(excerpts_block or ""), len(last_chunks or []),
        )

    def _update_followup_state(answer_text: str) -> None:
        try:
            answer_is_list, answer_items = _extract_followup_items_from_answer(answer_text)
            preserved_items = list(stored_items or previous_list_items_all or [])
            primary_entities = [targeted_item] if targeted_item else []
            preserved_entities = _dedup_preserve_order(
                primary_entities + list(state.get("last_grounded_entities") or []) + preserved_items
            )
            next_state = {
                "query": (text or "").strip(),
                "answer": str(answer_text or "").strip(),
                "last_assistant_answer": str(answer_text or "").strip(),
                "chunks": last_chunks,
                "ts": time.time(),
                "answer_type": "followup",
                "last_answer_type": "followup",
                "last_grounded_entities": preserved_entities,
                "base_answer_type": state.get("base_answer_type") or state.get("answer_type"),
            }
            if preserved_items:
                next_state["items"] = preserved_items
                next_state["list_query"] = base_list_q
                next_state["list_answer"] = base_list_a
            elif answer_is_list and answer_items:
                next_state["items"] = answer_items
                next_state["list_query"] = (text or "").strip()
                next_state["list_answer"] = str(answer_text or "").strip()
                next_state["base_answer_type"] = "list"
                next_state["last_grounded_entities"] = _dedup_preserve_order(
                    preserved_entities + answer_items
                )
            S.last_answer_state[connection_id] = next_state
        except Exception:
            S.logger.exception("[FOLLOWUP] failed to update follow-up state")

    # --- targeted micro-retrieval (item rescue) --------------------
    # When ONE item is targeted from a previous list answer and the
    # already-saved follow-up chunks do not mention that item, perform
    # a tiny same-source retrieval to give the LLM a chance to produce
    # a real grounded explanation instead of "(not described in the
    # source)". Bounded: top_k=3, scoped to the source(s) of the saved
    # chunks, no rerank, no cross-document leakage.
    if targeted_item is not None and prev_is_list:
        try:
            _item_head = _followup_item_head(targeted_item)
            # Only spend the round-trip when the saved excerpts clearly
            # don't carry an explanation for this specific item. If the
            # item name already appears alongside other content in the
            # saved excerpts, the existing prompt path is sufficient.
            _has_strong_local = bool(
                _extract_followup_strong_explanation(
                    targeted_item, excerpts_block, previous_list_items_all
                )
            )
            _needs_rescue = not _has_strong_local
            if _needs_rescue and _item_head:
                _query_focus_item = _followup_query_focus_phrase(targeted_item, text)
                # Scope to the source(s) of the previously saved chunks.
                _allowed_sources = {
                    (c.get("source") or "").strip()
                    for c in (last_chunks or [])
                    if isinstance(c, dict) and c.get("source")
                }
                if not _allowed_sources:
                    S.logger.info(
                        "[FOLLOWUP MICRO-RETRIEVAL] skipped item=%r reason=no_prior_source_scope",
                        targeted_item,
                    )
                    _raw_rescue = []
                    _seed_adjacent_rescue = []
                else:
                    _seed_adjacent_rescue = _followup_expand_adjacent_chunks(
                        last_chunks,
                        _query_focus_item,
                        _allowed_sources,
                        previous_list_items_all,
                    )
                    _rescue_query = f"{_query_focus_item} explanation".strip()
                    S.logger.info("[FOLLOWUP QUERY] %s", _rescue_query)
                    try:
                        _raw_rescue = S._active_rag().search(
                            query=_rescue_query,
                            top_k=3,
                            return_dicts=True,
                            enable_rerank=False,
                        ) or []
                    except Exception:
                        S.logger.exception("[FOLLOWUP MICRO-RETRIEVAL] search failed")
                        _raw_rescue = []
                    S.logger.info(
                        "[FOLLOWUP CONTEXT QUERY] query=%r",
                        _rescue_query[:180],
                    )
                _rescue_candidates: list[tuple[float, int, dict]] = []
                for _candidate_order, _candidate_doc in enumerate(_raw_rescue):
                    if not isinstance(_candidate_doc, dict):
                        continue
                    _txt = (
                        _candidate_doc.get("text")
                        or _candidate_doc.get("page_content")
                        or _candidate_doc.get("content")
                        or ""
                    ).strip()
                    if not _txt:
                        continue
                    _src = _candidate_doc.get("source")
                    _md = _candidate_doc.get("metadata")
                    if (not _src) and isinstance(_md, dict):
                        _src = _md.get("source") or _md.get("doc_id") or _md.get("file")
                    _src = (_src or "").strip()
                    # Same-document gate: only keep chunks from a source
                    # that was already part of the prior answer's chunks.
                    if _allowed_sources and _src not in _allowed_sources:
                        continue
                    # Require the targeted item name to actually appear in
                    # the rescue chunk; otherwise it is not a real rescue.
                    if not _followup_text_mentions_item(_txt, _query_focus_item):
                        continue
                    _candidate_score = _followup_explanation_candidate_score(
                        targeted_item, _txt, previous_list_items_all
                    )
                    if _candidate_score < 1.0:
                        continue
                    _focused_txt = (
                        _extract_followup_context_window(_txt, _query_focus_item)
                        or _extract_followup_context_window(_txt, targeted_item)
                        or _txt
                    )
                    _rescue_candidates.append((
                        _candidate_score,
                        _candidate_order,
                        {
                            "text": _focused_txt[:600],
                            "source": _src,
                            "metadata": dict(_md or {}) if isinstance(_md, dict) else {},
                        },
                    ))
                _rescue_candidates.sort(key=lambda row: (-row[0], row[1]))
                _kept_rescue = [row[2] for row in _rescue_candidates[:2]]
                _adjacent_rescue = []
                _lexical_rescue = []
                if _allowed_sources:
                    _adjacent_rescue = _followup_expand_adjacent_chunks(
                        _kept_rescue,
                        _query_focus_item,
                        _allowed_sources,
                        previous_list_items_all,
                    )
                    _lexical_rescue = _followup_lexical_explanation_rescue(
                        _query_focus_item,
                        targeted_item,
                        _allowed_sources,
                        previous_list_items_all,
                    )
                if _seed_adjacent_rescue or _adjacent_rescue or _lexical_rescue:
                    _last_chunk_indexes_by_source: dict[str, list[int]] = {}
                    for _last_doc in last_chunks or []:
                        if not isinstance(_last_doc, dict):
                            continue
                        _last_src = _followup_doc_source(_last_doc)
                        _last_idx = _followup_doc_chunk_index(_last_doc)
                        if _last_src and _last_idx is not None:
                            _last_chunk_indexes_by_source.setdefault(_last_src, []).append(_last_idx)

                    def _followup_rescue_distance(candidate: dict) -> int | None:
                        _cand_src = _followup_doc_source(candidate)
                        _cand_idx = _followup_doc_chunk_index(candidate)
                        if not (_cand_src and _cand_idx is not None):
                            return None
                        _anchor_indexes = _last_chunk_indexes_by_source.get(_cand_src) or []
                        if not _anchor_indexes:
                            return None
                        return min(abs(_cand_idx - _anchor_idx) for _anchor_idx in _anchor_indexes)

                    def _followup_rescue_sort_score(candidate: dict) -> float:
                        _base_score = _followup_explanation_candidate_score(
                            targeted_item,
                            _followup_doc_text(candidate),
                            previous_list_items_all,
                        )
                        _min_distance = _followup_rescue_distance(candidate)
                        if _min_distance is not None:
                            if _min_distance <= 1:
                                _base_score += 28.0
                            elif _min_distance <= 5:
                                _base_score += 22.0
                            elif _min_distance <= 12:
                                _base_score += 10.0
                            elif _min_distance <= 25:
                                _base_score -= 8.0
                            elif _min_distance < 50:
                                _base_score -= 14.0
                            elif _min_distance >= 50:
                                _base_score -= 18.0
                        return _base_score

                    _merged_rescue: list[dict] = []
                    _seen_rescue: set[tuple[str, str]] = set()
                    for _rescue_doc in (
                        _seed_adjacent_rescue
                        + _kept_rescue
                        + _adjacent_rescue
                        + _lexical_rescue
                    ):
                        _key = (
                            _followup_doc_source(_rescue_doc),
                            str(_followup_doc_chunk_index(_rescue_doc)),
                        )
                        if _key in _seen_rescue:
                            continue
                        _seen_rescue.add(_key)
                        _merged_rescue.append(_rescue_doc)
                    _merged_rescue.sort(key=_followup_rescue_sort_score, reverse=True)
                    _nearby_rescue = [
                        _rescue_doc for _rescue_doc in _merged_rescue
                        if (_followup_rescue_distance(_rescue_doc) or 9999) <= 12
                    ]
                    _strong_rescue = [
                        _rescue_doc for _rescue_doc in _merged_rescue
                        if _followup_explanation_candidate_score(
                            targeted_item,
                            _followup_doc_text(_rescue_doc),
                            previous_list_items_all,
                        ) >= 12.0
                    ]
                    _candidate_rescue_pool = list(_nearby_rescue or _merged_rescue)
                    _candidate_pool_has_strong = any(
                        _followup_explanation_candidate_score(
                            targeted_item,
                            _followup_doc_text(_rescue_doc),
                            previous_list_items_all,
                        ) >= 12.0
                        for _rescue_doc in _candidate_rescue_pool
                    )
                    if not _candidate_pool_has_strong:
                        _candidate_keys = {
                            (
                                _followup_doc_source(_rescue_doc),
                                str(_followup_doc_chunk_index(_rescue_doc)),
                            )
                            for _rescue_doc in _candidate_rescue_pool
                        }
                        for _rescue_doc in _strong_rescue:
                            _key = (
                                _followup_doc_source(_rescue_doc),
                                str(_followup_doc_chunk_index(_rescue_doc)),
                            )
                            if _key not in _candidate_keys:
                                _candidate_rescue_pool.append(_rescue_doc)
                                _candidate_keys.add(_key)
                    _candidate_rescue_pool.sort(key=_followup_rescue_sort_score, reverse=True)
                    _kept_rescue = _candidate_rescue_pool[:4]
                if _kept_rescue:
                    S.logger.info(
                        "[FOLLOWUP MICRO-RETRIEVAL] item=%r rescued=%d sources=%r",
                        targeted_item, len(_kept_rescue),
                        sorted({str(c.get("source")) for c in _kept_rescue if c.get("source")}),
                    )
                    # Append to excerpts_block (do not replace the prior
                    # context; just enrich it). Keeps the LLM grounded on
                    # everything we know.
                    _rescue_text = "\n\n---\n\n".join(c["text"] for c in _kept_rescue)
                    if excerpts_block:
                        excerpts_block = excerpts_block + "\n\n---\n\n" + _rescue_text
                    else:
                        excerpts_block = _rescue_text
                else:
                    S.logger.info(
                        "[FOLLOWUP MICRO-RETRIEVAL] item=%r no usable rescue chunks",
                        targeted_item,
                    )
        except Exception:
            S.logger.exception("[FOLLOWUP MICRO-RETRIEVAL] unexpected failure")

    if targeted_item is not None and prev_is_list and len(extracted_items) == 1:
        ai_text, evidence_level = _build_followup_targeted_evidence_answer(
            targeted_item,
            previous_list_items_all,
            last_q,
            last_a,
            excerpts_block,
        )
        S.logger.info(
            "[FOLLOWUP CONTROLLED LEVEL] level=%s item=%r",
            evidence_level, targeted_item,
        )
        if ai_text == RAG_NO_MATCH_RESPONSE:
            S.logger.info("[FOLLOWUP GROUNDING VERIFIED] level=no_evidence")
            try:
                S.last_answer_state.pop(connection_id, None)
            except Exception:
                pass
            return (RAG_NO_MATCH_RESPONSE, [])
        if evidence_level == "strong":
            S.logger.info("[FOLLOWUP STRONG EVIDENCE] item=%r", targeted_item)
        elif evidence_level == "weak":
            S.logger.info(
                "[FOLLOWUP STRICT MODE TRIGGERED] item=%r reason=no_explanatory_sentence list_lock_disabled=True",
                targeted_item,
            )
            S.logger.info("[FOLLOWUP GROUNDING VERIFIED] level=no_explanatory_evidence")
            try:
                S.last_answer_state.pop(connection_id, None)
            except Exception:
                pass
            return (RAG_NO_MATCH_RESPONSE, [])
        S.logger.info("[FOLLOWUP GROUNDING VERIFIED] level=%s", evidence_level)
        _update_followup_state(ai_text)
        S.logger.info(
            "[FOLLOWUP] answered locally | intent=%s prev_list=%s len=%d",
            intent, prev_is_list, len(ai_text),
        )
        return (ai_text, [])

    # --- build instruction by intent + prior-answer shape ---
    if prev_is_list and extracted_items:
        items_block = "\n".join(f"- {item}" for item in extracted_items)
        if followup_action == "simplify":
            instruction = (
                "The PREVIOUS ANSWER contains the following list items:\n\n"
                f"{items_block}\n\n"
                "OUTPUT REQUIREMENT: For EACH item above, output EXACTLY one line in this format:\n"
                "ItemName: one short plain-language clarification (max ~15 words)\n\n"
                "Rules:\n"
                "- Each line MUST start with the item name followed by a colon.\n"
                "- Use simpler language than the original.\n"
                "- Draw information ONLY from SOURCE EXCERPTS or PREVIOUS ANSWER.\n"
                "- Do NOT invent new items, names, numbers, or examples.\n"
                "- Do NOT skip any item.\n"
                "- If you do not explain each item individually, the answer is INCORRECT."
            )
        elif followup_action == "rephrase":
            instruction = (
                "The PREVIOUS ANSWER contains the following list items:\n\n"
                f"{items_block}\n\n"
                "OUTPUT REQUIREMENT: For EACH item above, output EXACTLY one line in this format:\n"
                "ItemName: one short rephrased description using different wording\n\n"
                "Rules:\n"
                "- Each line MUST start with the item name followed by a colon.\n"
                "- Use different wording than the original.\n"
                "- Draw information ONLY from SOURCE EXCERPTS or PREVIOUS ANSWER.\n"
                "- Do NOT add new items or facts.\n"
                "- Do NOT skip any item.\n"
                "- If you do not explain each item individually, the answer is INCORRECT."
            )
        else:  # explain
            instruction = (
                "The PREVIOUS ANSWER contains the following list items:\n\n"
                f"{items_block}\n\n"
                "OUTPUT REQUIREMENT: For EACH item above, output EXACTLY one line in this format:\n"
                "ItemName: brief explanation of what this item means (1-2 sentences max)\n\n"
                "Rules:\n"
                "- Each line MUST start with the item name followed by a colon.\n"
                "- Explain what the item MEANS, do NOT just repeat it.\n"
                "- Draw information ONLY from SOURCE EXCERPTS or PREVIOUS ANSWER.\n"
                "- Do NOT add any new item, name, number, or example not already present.\n"
                "- Do NOT skip any item.\n"
                "- Do NOT write a paragraph summary — explain EACH item separately.\n"
                "- If you do not explain each item individually, the answer is INCORRECT."
            )
    elif prev_is_list:
        # Fallback: we know it's a list but couldn't extract items cleanly.
        # Still force per-item format.
        if followup_action == "simplify":
            instruction = (
                "The PREVIOUS ANSWER is a list. For EACH item in the list, output one line:\n"
                "ItemName: short plain-language clarification (max ~15 words)\n\n"
                "Each line MUST start with the item name followed by a colon.\n"
                "Draw ONLY from SOURCE EXCERPTS or PREVIOUS ANSWER.\n"
                "Do NOT invent new items. Do NOT skip any item.\n"
                "If you do not explain each item individually, the answer is INCORRECT."
            )
        elif followup_action == "rephrase":
            instruction = (
                "The PREVIOUS ANSWER is a list. For EACH item in the list, output one line:\n"
                "ItemName: rephrased description in different wording\n\n"
                "Each line MUST start with the item name followed by a colon.\n"
                "Draw ONLY from SOURCE EXCERPTS or PREVIOUS ANSWER.\n"
                "Do NOT add new items. Do NOT skip any item.\n"
                "If you do not explain each item individually, the answer is INCORRECT."
            )
        else:  # explain
            instruction = (
                "The PREVIOUS ANSWER is a list. For EACH item in the list, output one line:\n"
                "ItemName: brief explanation of what this item means (1-2 sentences)\n\n"
                "Each line MUST start with the item name followed by a colon.\n"
                "Explain what each item MEANS — do NOT just repeat it.\n"
                "Draw ONLY from SOURCE EXCERPTS or PREVIOUS ANSWER.\n"
                "Do NOT add new items. Do NOT skip any item.\n"
                "If you do not explain each item individually, the answer is INCORRECT."
            )
    else:
        if followup_action == "simplify":
            instruction = (
                "Restate the PREVIOUS ANSWER in 2-4 short sentences using simpler, plainer "
                "language. Use ONLY information already present in the PREVIOUS ANSWER and "
                "SOURCE EXCERPTS. Do NOT add any fact, name, number, definition, or example "
                "that is not already there."
            )
        elif followup_action == "rephrase":
            instruction = (
                "Rephrase the PREVIOUS ANSWER in 2-4 sentences using clearer, different "
                "wording. Use ONLY information already present in the PREVIOUS ANSWER and "
                "SOURCE EXCERPTS. Do NOT introduce any new fact."
            )
        else:  # explain
            instruction = (
                "Briefly expand on the PREVIOUS ANSWER in 2-5 short sentences using ONLY the "
                "SOURCE EXCERPTS and the previous answer itself. Stay close to their wording. "
                "Do NOT introduce any new fact, name, number, definition, example, or concept "
                "that is not already present in those texts."
            )

    # IMPORTANT: do NOT instruct the LLM to write "Not found in the document."
    # itself — that often gets appended to otherwise-grounded explanations.
    # The grounding gate below decides not_found instead.
    system_prompt = (
        "You are a strict grounded clarification assistant. " + instruction +
        " Output ONLY the clarification text. Do NOT add disclaimers, meta-commentary, "
        "or phrases like 'Not found' / 'Based on the document' / 'According to the previous "
        "answer'. Do NOT invent content beyond the provided PREVIOUS ANSWER and SOURCE EXCERPTS."
    )

    context_text = (
        f"PREVIOUS USER QUESTION: {last_q}\n\n"
        f"PREVIOUS ANSWER:\n{last_a}\n\n"
        f"SOURCE EXCERPTS:\n{excerpts_block if excerpts_block else '(none)'}"
    )

    try:
        ai_text = await S.call_llm_with_context(text.strip(), context_text, system_prompt)
    except Exception:
        S.logger.exception("[FOLLOWUP] LLM call failed")
        ai_text = ""

    ai_text = (ai_text or "").strip()

    # ---- LIST-SHAPED RETRY -------------------------------------------
    # When the previous answer is a list AND we extracted item names,
    # require that the LLM output contains per-item "ItemName: ..."
    # lines for at least half the items. If not, retry once with an
    # even stricter prompt that pre-fills the item names. Lightweight:
    # no new retrieval — same saved chunks.
    def _per_item_coverage(out: str, items: list[str]) -> int:
        if not out or not items:
            return 0
        out_l = out.lower()
        hits = 0
        for it in items:
            head = (it.split(":", 1)[0]).strip().lower()
            if not head:
                continue
            # Look for "<item>:" on a line (allow leading bullets/whitespace)
            if _re_followup.search(
                r"(?m)^\s*(?:[-*\u2022]|\d+[.)])?\s*" + _re_followup.escape(head) + r"\s*:\s*\S",
                out_l,
            ):
                hits += 1
        return hits

    if prev_is_list and extracted_items:
        needed = min(len(extracted_items), max(2, (len(extracted_items) + 1) // 2))
        coverage = _per_item_coverage(ai_text, extracted_items)
        if coverage < needed:
            S.logger.info(
                "[FOLLOWUP LIST RETRY] coverage=%d/%d items=%d -> stricter retry",
                coverage, len(extracted_items), len(extracted_items),
            )
            stricter_items_block = "\n".join(
                f"{i+1}. {item}" for i, item in enumerate(extracted_items)
            )
            stricter_instruction = (
                "Your previous response was REJECTED because it did not follow the "
                "required format.\n\n"
                "You MUST output one line per item below, in the SAME ORDER, using "
                "EXACTLY this format (no preamble, no summary, no extra text):\n\n"
                f"{stricter_items_block}\n\n"
                "Replace each numbered line with:\n"
                "ItemName: <one short grounded explanation, 1-2 sentences>\n\n"
                "Hard rules:\n"
                "- Output EXACTLY one line per item, in the order listed above.\n"
                "- Each line MUST start with the item name followed by ': '.\n"
                "- Use ONLY information from PREVIOUS ANSWER and SOURCE EXCERPTS.\n"
                "- Do NOT add a header, intro, conclusion, or summary paragraph.\n"
                "- Do NOT skip, merge, rename, or invent items.\n"
                "- If a source does not explain an item, write: "
                "'<ItemName>: (not described in the source)' for that one line."
            )
            stricter_system = (
                "You are a strict grounded clarification assistant. "
                + stricter_instruction
                + " Output ONLY the per-item lines."
            )
            try:
                retry_text = await S.call_llm_with_context(
                    text.strip(), context_text, stricter_system
                )
            except Exception:
                S.logger.exception("[FOLLOWUP LIST RETRY] LLM call failed")
                retry_text = ""
            retry_text = (retry_text or "").strip()
            if retry_text:
                retry_coverage = _per_item_coverage(retry_text, extracted_items)
                # Quick local grounding check so we do not swap a grounded
                # paragraph for a per-item retry that hallucinates content
                # not present in the source. Same token math as the gate
                # below; kept inline to keep the swap decision local.
                def _local_ground_ratio(_t: str) -> float:
                    _toks = _re_followup.findall(r"[a-zA-Z0-9]{4,}", (_t or "").lower())
                    _content = [
                        w for w in _toks if w not in {
                            "this","that","these","those","with","from","into","than","then",
                            "have","been","being","were","they","them","their","there","which",
                            "what","when","where","while","about","also","such","some","more",
                            "most","many","much","your","would","could","should","will","shall",
                            "does","doing","done","answer","previous","above","below","thus",
                            "because","however","therefore","based","means","meaning","refers",
                            "include","includes","including","example","examples","simply",
                            "essentially","namely","specifically","respectively","various",
                            "different","important","things","thing","people","person","each",
                            "every","another","other",
                        }
                    ]
                    if not _content:
                        return 1.0
                    _corpus = (last_a + " " + excerpts_block).lower()
                    _hit = sum(1 for w in _content if w in _corpus)
                    return _hit / max(1, len(_content))
                retry_ground = _local_ground_ratio(retry_text)
                orig_ground = _local_ground_ratio(ai_text)
                S.logger.info(
                    "[FOLLOWUP LIST RETRY] retry_coverage=%d/%d retry_ground=%.2f orig_ground=%.2f",
                    retry_coverage, len(extracted_items), retry_ground, orig_ground,
                )
                # Only swap to the retry when it (a) materially improves
                # coverage AND (b) does not regress grounding below the
                # acceptance threshold and not worse than the original.
                if (
                    (retry_coverage >= needed or retry_coverage > coverage)
                    and retry_ground >= _FOLLOWUP_GROUND_RATIO_MIN
                    and retry_ground >= orig_ground - 0.05
                ):
                    ai_text = retry_text

        # Final per-item enforcement: if neither attempt produced per-item
        # coverage at or above the threshold, try the controlled
        # explanation mode (LLM, anchored to the document's domain) for
        # the items that actually appear in the retrieved chunks before
        # falling back to a deterministic placeholder.
        final_coverage = _per_item_coverage(ai_text, extracted_items)
        if final_coverage < needed:
            S.logger.info(
                "[FOLLOWUP LIST DETERMINISTIC] final_coverage=%d/%d -> attempt controlled explanation",
                final_coverage, len(extracted_items),
            )
            _anchored = _followup_items_anchored(
                extracted_items, excerpts_block, last_a
            )
            _ce = ""
            if _anchored:
                S.logger.info("[FOLLOWUP EXPLANATION MODE TRIGGERED]")
                for _it in _anchored:
                    S.logger.info("[FOLLOWUP EXPLANATION ITEM = %s]", _it)
                _ce = await _followup_controlled_explanation(
                    _anchored, last_q, last_a, excerpts_block, text
                )
            if _ce:
                _expl_score_d = _compute_explanation_grounding_score(
                    _ce, excerpts_block, last_a
                )
                S.logger.info(
                    "[FOLLOWUP GROUNDING SCORE] score=%.2f threshold=%.2f",
                    _expl_score_d, _FOLLOWUP_EXPL_GROUND_THRESHOLD,
                )
                if _expl_score_d < _FOLLOWUP_EXPL_GROUND_THRESHOLD:
                    S.logger.info(
                        "[FOLLOWUP STRICT MODE TRIGGERED] score=%.2f -> limited explanation",
                        _expl_score_d,
                    )
                    S.logger.info("[FOLLOWUP LIMITED EXPLANATION]")
                    ai_text = _build_grounded_explanations_for_items(
                        last_q,
                        extracted_items,
                        [{"text": excerpts_block}, {"text": last_a}],
                    )
                    if not ai_text:
                        return (RAG_NO_MATCH_RESPONSE, [])
                else:
                    S.logger.info(
                        "[FOLLOWUP EXPLANATION SOURCE = inferred_from_context]"
                    )
                    ai_text = _ce.rstrip() + "\n\n" + _FOLLOWUP_INFERRED_SUFFIX
            elif targeted_item is not None and len(extracted_items) == 1:
                ai_text = _build_grounded_explanation(
                    last_q,
                    extracted_items[0],
                    [{"text": excerpts_block}, {"text": last_a}],
                )
                if ai_text == RAG_NO_MATCH_RESPONSE:
                    return (RAG_NO_MATCH_RESPONSE, [])
            else:
                ai_text = _build_grounded_explanations_for_items(
                    last_q,
                    extracted_items,
                    [{"text": excerpts_block}, {"text": last_a}],
                )
                if not ai_text:
                    return (RAG_NO_MATCH_RESPONSE, [])

    # Strip a trailing not-found sentinel that the model sometimes appends
    # despite the instruction. Done BEFORE the empty/not-found check so a
    # genuinely good explanation isn't thrown away.
    _nf = RAG_NO_MATCH_RESPONSE.strip()
    _nf_re = _re_followup.compile(
        r"\s*" + _re_followup.escape(_nf).replace(r"\.", r"\.?") + r"\s*$",
        _re_followup.IGNORECASE,
    )
    cleaned_ai = _nf_re.sub("", ai_text).strip()
    # Also handle a stray leading not-found.
    cleaned_ai = _nf_re.sub("", cleaned_ai).strip()
    if cleaned_ai and cleaned_ai.lower() != _nf.lower():
        ai_text = cleaned_ai

    if (not ai_text) or ai_text.lower() == _nf.lower():
        S.logger.info("[FOLLOWUP] empty/not-found from LLM -> strict not_found")
        return (RAG_NO_MATCH_RESPONSE, [])

    # Lightweight grounding check: a modest portion of the answer's content
    # tokens must appear in the combined corpus of (previous answer + source
    # excerpts). Threshold is loose so paraphrased clarifications pass; open-
    # domain hallucinations still fall below it because they introduce many
    # foreign content words.
    grounded_corpus = (last_a + " " + excerpts_block).lower()
    ans_tokens = _re_followup.findall(r"[a-zA-Z0-9]{4,}", ai_text.lower())
    _FU_STOPWORDS = {
        "this", "that", "these", "those", "with", "from", "into", "than", "then",
        "have", "been", "being", "were", "they", "them", "their", "there", "which",
        "what", "when", "where", "while", "about", "also", "such", "some", "more",
        "most", "many", "much", "your", "would", "could", "should", "will", "shall",
        "does", "doing", "done", "answer", "previous", "above", "below", "thus",
        "because", "however", "therefore", "based", "means", "meaning", "refers",
        "include", "includes", "including", "example", "examples", "simply", "essentially",
        "namely", "specifically", "respectively", "various", "different", "important",
        "things", "thing", "people", "person", "each", "every", "another", "other",
    }
    content_tokens = [w for w in ans_tokens if w not in _FU_STOPWORDS]
    if content_tokens:
        overlap = sum(1 for w in content_tokens if w in grounded_corpus)
        ratio = overlap / max(1, len(content_tokens))
        if ratio < _FOLLOWUP_GROUND_RATIO_MIN:
            # If the previous answer was a list and we have explicit items,
            # honour the per-item shape. First try a controlled explanation
            # (LLM, anchored to the document's domain) for the items that
            # actually appear in the retrieved chunks; only fall back to a
            # deterministic placeholder when no item is anchored or the LLM
            # produces nothing usable.
            if prev_is_list and extracted_items:
                S.logger.info(
                    "[FOLLOWUP LIST FALLBACK] grounding_ratio=%.2f -> attempt controlled explanation for %d items",
                    ratio, len(extracted_items),
                )
                _anchored = _followup_items_anchored(
                    extracted_items, excerpts_block, last_a
                )
                _ce = ""
                if _anchored:
                    S.logger.info("[FOLLOWUP EXPLANATION MODE TRIGGERED]")
                    for _it in _anchored:
                        S.logger.info("[FOLLOWUP EXPLANATION ITEM = %s]", _it)
                    _ce = await _followup_controlled_explanation(
                        _anchored, last_q, last_a, excerpts_block, text
                    )
                if _ce:
                    _expl_score_w = _compute_explanation_grounding_score(
                        _ce, excerpts_block, last_a
                    )
                    S.logger.info(
                        "[FOLLOWUP GROUNDING SCORE] score=%.2f threshold=%.2f",
                        _expl_score_w, _FOLLOWUP_EXPL_GROUND_THRESHOLD,
                    )
                    if _expl_score_w < _FOLLOWUP_EXPL_GROUND_THRESHOLD:
                        S.logger.info(
                            "[FOLLOWUP STRICT MODE TRIGGERED] score=%.2f -> limited explanation",
                            _expl_score_w,
                        )
                        S.logger.info("[FOLLOWUP LIMITED EXPLANATION]")
                        S.logger.info("[FOLLOWUP GROUNDING VERIFIED]")
                        ai_text = _build_grounded_explanations_for_items(
                            last_q,
                            extracted_items,
                            [{"text": excerpts_block}, {"text": last_a}],
                        )
                        if not ai_text:
                            return (RAG_NO_MATCH_RESPONSE, [])
                    else:
                        S.logger.info(
                            "[FOLLOWUP EXPLANATION SOURCE = inferred_from_context]"
                        )
                        ai_text = _ce.rstrip() + "\n\n" + _FOLLOWUP_INFERRED_SUFFIX
                elif targeted_item is not None and len(extracted_items) == 1:
                    ai_text = _build_grounded_explanation(
                        last_q,
                        extracted_items[0],
                        [{"text": excerpts_block}, {"text": last_a}],
                    )
                    if ai_text == RAG_NO_MATCH_RESPONSE:
                        return (RAG_NO_MATCH_RESPONSE, [])
                else:
                    ai_text = _build_grounded_explanations_for_items(
                        last_q,
                        extracted_items,
                        [{"text": excerpts_block}, {"text": last_a}],
                    )
                    if not ai_text:
                        return (RAG_NO_MATCH_RESPONSE, [])
            else:
                S.logger.info(
                    "[FOLLOWUP GROUNDING WEAK] overlap_ratio=%.2f threshold=%.2f -> not_found",
                    ratio, _FOLLOWUP_GROUND_RATIO_MIN,
                )
                return (RAG_NO_MATCH_RESPONSE, [])
        else:
            S.logger.info("[FOLLOWUP GROUNDING OK] overlap_ratio=%.2f", ratio)

    # --- weak-evidence anti-inference guard (targeted items only) ----------
    # Even after grounding passes, the LLM may over-explain an item from
    # evidence that merely *mentions* it (incidental co-occurrence) rather
    # than truly *explaining* it.  When the evidence lacks a real
    # explanatory sentence about the targeted item we no longer collapse
    # straight to a placeholder; instead we enter a controlled
    # explanation mode that gives the user a useful, contextual answer
    # while clearly disclosing it was inferred from context.
    if (
        targeted_item is not None
        and prev_is_list
        and len(extracted_items) == 1
        and not _evidence_has_explicit_explanation(targeted_item, excerpts_block)
    ):
        _itm = extracted_items[0]
        # When the retrieved evidence only lists the item without an
        # explanatory sentence, do not fall back to a list-relationship
        # explanation. Follow-up explanation mode must be grounded in
        # descriptive document text or fail strictly.
        S.logger.info(
            "[FOLLOWUP STRICT MODE TRIGGERED] item=%r no_explicit_evidence list_lock_disabled=True",
            _itm,
        )
        S.logger.info("[FOLLOWUP GROUNDING VERIFIED] level=no_explanatory_evidence")
        try:
            S.last_answer_state.pop(connection_id, None)
        except Exception:
            pass
        return (RAG_NO_MATCH_RESPONSE, [])

    # Update state so successive "explain more" works on the latest explanation,
    # but PRESERVE the original chunks (never broaden the grounding window).
    _update_followup_state(ai_text)

    S.logger.info(
        "[FOLLOWUP] answered locally | intent=%s prev_list=%s len=%d",
        intent, prev_is_list, len(ai_text),
    )
    return (ai_text, [])

