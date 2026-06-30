"""Extracted retrieval helpers (Phase 8H).

Moved verbatim from ``assistify_rag_server.py``. This module is a leaf in the
retrieval package and never imports the server. Shared mutable state, the
logger, and engine functions still in the monolith are reached through ``S``,
the server module injected via ``bind_server`` at registration time. Behavior is
identical to the monolith original.
"""
from __future__ import annotations

from backend.config_head import *  # noqa: F401,F403 - mirrors the server module
from backend.core.config import LLM_URL
from backend.retrieval.followup import _AR_QUERY_STOPWORDS
from backend.utils.text import _is_arabic_text
import re as _re_mod
import aiohttp
import asyncio
import re
import time

S = None


def bind_server(server) -> None:
    """Bind the live server module so extracted helpers can reach shared state."""
    global S
    S = server

_FINAL_AR_TRANSLATION_CACHE_MAX = 256

_AR_ITEM_TRANSLATION_CACHE_MAX = 1024

def _is_compact_arabic_item_translation(source_item: str, translated_item: str) -> bool:
    candidate = re.sub(r"\s+", " ", str(translated_item or "").strip())
    if not S._is_clean_cached_arabic_translation(candidate, min_ar_chars=2):
        return False
    if "\n" in str(translated_item or "") or len(candidate) > 90:
        return False
    if any(mark in candidate for mark in ('"', "'", ":", "：")):
        return False
    source_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", str(source_item or ""))
    candidate_words = [
        word for word in candidate.split()
        if any("\u0600" <= ch <= "\u06FF" for ch in word)
    ]
    if not candidate_words:
        return False
    if len(source_words) <= 4 and len(candidate_words) > max(5, len(source_words) + 3):
        return False
    return True

def _final_ar_translation_cache_key(
    answer_text: str, target_lang: str = "ar", answer_type: str = "final"
) -> str:
    source_text = re.sub(r"\s+", " ", str(answer_text or "")).strip()
    normalized_answer = source_text.lower()
    bucket = str(answer_type or "final").strip().lower()
    target = str(target_lang or "").strip().lower()
    return f"{bucket}||{target}||{normalized_answer}||{source_text}"

def _final_ar_translation_cache_get(
    answer_text: str, target_lang: str = "ar", answer_type: str = "final"
) -> "str | None":
    if str(target_lang or "").strip().lower() != "ar":
        return None
    normalized_answer = re.sub(r"\s+", " ", str(answer_text or "")).strip()
    if not normalized_answer or normalized_answer == "Not found in the document.":
        return None
    key = _final_ar_translation_cache_key(normalized_answer, target_lang, answer_type)
    if key in S._FINAL_AR_TRANSLATION_CACHE:
        S._FINAL_AR_TRANSLATION_CACHE.move_to_end(key)
        cached = S._FINAL_AR_TRANSLATION_CACHE[key]
        if S._is_clean_cached_arabic_translation(cached):
            return cached
        S._FINAL_AR_TRANSLATION_CACHE.pop(key, None)
        S.logger.info("[AR TRANSLATION CACHE] evicted_invalid=True branch=%s", answer_type)
    return None

def _final_ar_translation_cache_put(
    answer_text: str, translated_text: str, target_lang: str = "ar", answer_type: str = "final"
) -> None:
    if str(target_lang or "").strip().lower() != "ar":
        return
    normalized_answer = re.sub(r"\s+", " ", str(answer_text or "")).strip()
    translated = str(translated_text or "").strip()
    if not normalized_answer or normalized_answer == "Not found in the document." or not translated:
        return
    if not S._is_clean_cached_arabic_translation(translated):
        S.logger.info("[AR TRANSLATION CACHE] store_skipped_invalid=True branch=%s", answer_type)
        return
    key = _final_ar_translation_cache_key(normalized_answer, target_lang, answer_type)
    S._FINAL_AR_TRANSLATION_CACHE[key] = translated
    S._FINAL_AR_TRANSLATION_CACHE.move_to_end(key)
    while len(S._FINAL_AR_TRANSLATION_CACHE) > _FINAL_AR_TRANSLATION_CACHE_MAX:
        S._FINAL_AR_TRANSLATION_CACHE.popitem(last=False)

def _ar_item_translation_cache_key(
    item_text: str, target_lang: str = "ar", answer_type: str = "list_item"
) -> str:
    source_item = re.sub(r"\s+", " ", str(item_text or "")).strip()
    normalized_item = source_item.lower()
    bucket = str(answer_type or "list_item").strip().lower()
    target = str(target_lang or "").strip().lower()
    return f"{bucket}||{target}||{normalized_item}||{source_item}"

def _ar_item_translation_cache_get(
    item_text: str, target_lang: str = "ar", answer_type: str = "list_item"
) -> "str | None":
    if str(target_lang or "").strip().lower() != "ar":
        return None
    normalized_item = re.sub(r"\s+", " ", str(item_text or "")).strip().lower()
    if not normalized_item:
        return None
    key = _ar_item_translation_cache_key(item_text, target_lang, answer_type)
    if key in S._AR_ITEM_TRANSLATION_CACHE:
        S._AR_ITEM_TRANSLATION_CACHE.move_to_end(key)
        cached = S._AR_ITEM_TRANSLATION_CACHE[key]
        if _is_compact_arabic_item_translation(item_text, cached):
            return cached
        S._AR_ITEM_TRANSLATION_CACHE.pop(key, None)
        S.logger.info("[AR ITEM TRANSLATION CACHE] evicted_invalid=True item_len=%s", len(item_text or ""))
    return None

def _ar_item_translation_cache_put(
    item_text: str, translated_item: str, target_lang: str = "ar", answer_type: str = "list_item"
) -> None:
    if str(target_lang or "").strip().lower() != "ar":
        return
    normalized_item = re.sub(r"\s+", " ", str(item_text or "")).strip().lower()
    translated = str(translated_item or "").strip()
    if not normalized_item or not translated:
        return
    if not _is_compact_arabic_item_translation(item_text, translated):
        S.logger.info("[AR ITEM TRANSLATION CACHE] store_skipped_invalid=True item_len=%s", len(item_text or ""))
        return
    key = _ar_item_translation_cache_key(item_text, target_lang, answer_type)
    S._AR_ITEM_TRANSLATION_CACHE[key] = translated
    S._AR_ITEM_TRANSLATION_CACHE.move_to_end(key)
    while len(S._AR_ITEM_TRANSLATION_CACHE) > _AR_ITEM_TRANSLATION_CACHE_MAX:
        S._AR_ITEM_TRANSLATION_CACHE.popitem(last=False)

_BULLET_LINE_RE = re.compile(r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+\S)\s*$")

def _parse_bullet_list_items(text: str) -> "list[str]":
    """Return the bullet items found in `text` if it looks like a bullet list.

    Generic detection only — used to mirror existing list formatting in
    Arabic output. No domain content. Returns an empty list when the input
    is not a multi-line bullet list with at least two items.
    """
    raw = str(text or "")
    if not raw or "\n" not in raw:
        return []
    items: list[str] = []
    for line in raw.splitlines():
        m = _BULLET_LINE_RE.match(line)
        if not m:
            continue
        item = re.sub(r"\s+", " ", m.group(1)).strip(" \t-•*.,;:")
        if item:
            items.append(item)
    return items if len(items) >= 2 else []

_ALLOWED_LATIN_BRANDS = frozenset()

def _allow_latin_token_in_arabic_text(token: str) -> bool:
    stripped = str(token or "").strip(".,!?;:()\"'،؟؛")
    if not stripped:
        return False
    if stripped.lower() in _ALLOWED_LATIN_BRANDS:
        return True
    if re.fullmatch(r"[A-Z]{2,8}", stripped):
        return True
    if any(ch.isdigit() for ch in stripped) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+_.-]{1,15}", stripped):
        return True
    return False

def _sanitize_arabic_text(text: str) -> str:
    """Strip English words from Arabic text, keeping numbers and generic codes.

    Prevents the TTS engine from trying to pronounce stray English words
    (e.g. "ت cost أقل") that the LLM sometimes leaks. Purely-English responses
    are returned as-is (the caller handles that case separately).
    """
    # Strip CJK characters FIRST — before the Arabic-check early return.
    # A chunk that is entirely Chinese (no Arabic at all) must be emptied here;
    # the early-return below would otherwise pass it through unchanged.
    _CJK_RE_EARLY = (
        '[\u2e80-\u2fff'
        '\u3000-\u9fff'
        '\uf900-\ufaff'
        '\ufe30-\ufe4f'
        '\uff00-\uffef'
        ']+'
    )
    text = _re_mod.sub(_CJK_RE_EARLY, '', text).strip()
    if not text:
        return ''  # was entirely CJK — caller's len() check will drop it

    # If text has no Arabic characters at all, return as-is (caller decides)
    if not any('\u0600' <= c <= '\u06FF' for c in text):
        return text

    tokens = text.split()
    cleaned: list[str] = []
    for tok in tokens:
        # Keep punctuation-only tokens
        stripped = tok.strip(".,!?;:()\"'،؟؛")
        if not stripped:
            cleaned.append(tok)
            continue
        # Keep if contains Arabic
        if any('\u0600' <= c <= '\u06FF' for c in stripped):
            cleaned.append(tok)
            continue
        # Keep if it's a number
        if stripped.replace('.', '').replace(',', '').isdigit():
            cleaned.append(tok)
            continue
        # Keep if it's a generic acronym/code-like token.
        if _allow_latin_token_in_arabic_text(stripped):
            cleaned.append(tok)
            continue
        # Drop English word
        continue

    result = " ".join(cleaned).strip()
    # Strip CJK / Chinese / Japanese / Korean characters that the LLM sometimes
    # injects mid-sentence (e.g. "في两天" gets sub-word joined → Arabic check
    # keeps the whole token; the regex below scrubs the CJK portion out).
    # IMPORTANT: must NOT use raw string r'...' here — Python must interpret
    # the \u escapes into real Unicode codepoints before the regex engine runs.
    _CJK_RE = (
        '[\u2e80-\u2fff'   # CJK Radicals / Kangxi
        '\u3000-\u9fff'    # CJK Unified Ideographs + punctuation
        '\uf900-\ufaff'    # CJK Compatibility Ideographs
        '\ufe30-\ufe4f'    # CJK Compatibility Forms
        '\uff00-\uffef'    # Halfwidth/Fullwidth forms (includes ｡、。)
        ']+'
    )
    result = _re_mod.sub(_CJK_RE, '', result).strip()
    # Remove "حسناً" / "حسنا" / "بالتأكيد" filler at the very start
    result = _re_mod.sub(r'^(حسناً|حسنا|بالتأكيد)[,،.]?\s*', '', result).strip()
    # Re-join isolated single Arabic letters to the following Arabic word.
    # The LLM sometimes outputs "ت شمل" (with a space) instead of "تشمل",
    # causing TTS to read the lone letter as a standalone character.
    # Pattern: (word-boundary / start)(single Arabic letter)(space+)(Arabic letter follows) → merge.
    result = _re_mod.sub(
        r'(^|\s)([\u0621-\u064a])\s+(?=[\u0621-\u064a])',
        r'\1\2',
        result,
    )
    # Collapse any double-spaces left by stripping
    result = _re_mod.sub(r'  +', ' ', result).strip()
    return result if result else text  # fallback to original if everything was stripped

_AR_TTS_DIGIT_MAP = {
    '0': 'صِفر', '1': 'واحِد', '2': 'اثنان', '3': 'ثلاثة',
    '4': 'أربعة', '5': 'خمسة', '6': 'ستة', '7': 'سبعة',
    '8': 'ثمانية', '9': 'تسعة',
}

def _preprocess_for_tts(text: str, language: str = "ar") -> str:
    """Normalize a text chunk just before it is sent to XTTS synthesis.

    Targets the most common causes of XTTS stuttering and unnatural pacing:
      1. Strip markdown (##, **, *, numbered/bullet lists) — XTTS reads
         symbols aloud or hesitates at them.
      2. Expand isolated single Western digits to Arabic word equivalents so
         XTTS doesn't trip over a lone '3' inside Arabic text.
      3. Remove consecutive duplicate punctuation ('،،' → '،').
      4. Ensure the chunk ends with a light pause character ('،') when it
         trails off mid-phrase — gives XTTS a natural breath boundary.
      5. Strip emoji / private-use characters.
    """
    if not text:
        return text

    # 1. Strip markdown formatting
    text = _re_mod.sub(r'^#+\s*', '', text, flags=_re_mod.MULTILINE)   # headings
    text = _re_mod.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)          # bold/italic
    # Numbered list items: replace "1." / "2." etc. with a comma separator
    text = _re_mod.sub(r'(?m)^\s*\d+\.\s+', '، ', text)
    # Bullet list items
    text = _re_mod.sub(r'(?m)^\s*[-•]\s+', '، ', text)

    if language == "ar":
        # 2. Expand isolated single digits ('3 سنوات' → 'ثلاثة سنوات')
        text = _re_mod.sub(
            r'(?<!\d)\d(?!\d)',
            lambda m: _AR_TTS_DIGIT_MAP.get(m.group(), m.group()),
            text,
        )

        # 3. Collapse repeated punctuation
        text = _re_mod.sub(r'[،,]{2,}', '،', text)
        text = _re_mod.sub(r'[؟?!]{2,}', lambda m: m.group()[0], text)

        # 4. Add trailing pause if chunk ends without punctuation
        #    (signals XTTS that the phrase is complete → prevents rushed ending)
        if text and text[-1] not in '.؟?!،,؛:':
            text = text + '،'

    # 5. Remove emoji
    text = _re_mod.sub(
        r'[\U0001F300-\U0001FAFF\U0001F900-\U0001F9FF\U00002600-\U000027BF]',
        '', text,
    )

    # Collapse multiple spaces / newlines
    text = _re_mod.sub(r'\s+', ' ', text).strip()
    return text

async def translate_with_llm(text: str, source_lang: str, target_lang: str) -> str:
    """Translate text between Arabic and English using the local LLM.

    Uses the same Ollama model already loaded in VRAM — no external API needed.
    Returns the translated text, or the original text if translation fails.
    """
    global llm_session
    lang_names = {"ar": "Arabic", "en": "English"}
    src = lang_names.get(source_lang, source_lang)
    tgt = lang_names.get(target_lang, target_lang)

    # Build a very directive prompt — small models like qwen2.5:3b need explicit task framing
    if target_lang == "ar":
        system_msg = (
            "أنت مترجم محترف. مهمتك الوحيدة هي ترجمة النص إلى اللغة العربية.\n"
            "القواعد الصارمة:\n"
            "- اكتب فقط النص العربي المترجم\n"
            "- لا تكتب أي كلمة بالإنجليزية\n"
            "- لا تضف شرحاً أو ملاحظات\n"
            "- لا تكرر النص الأصلي\n"
            "الإخراج يجب أن يكون بالعربية فقط."
        )
        user_msg = f"ترجم هذا النص إلى العربية:\n\n{text}"
    else:
        system_msg = (
            "You are a professional translator. Your only task is to translate text to English.\n"
            "Strict rules:\n"
            "- Output ONLY the English translation\n"
            "- Do NOT output any Arabic\n"
            "- Do NOT add explanations or notes\n"
            "- Do NOT repeat the original text"
        )
        user_msg = f"Translate this text to English:\n\n{text}"

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": -1,
        "options": {"num_ctx": 3072, "num_gpu": 99, "temperature": 0.05, "num_predict": 512},
    }
    try:
        timeout = aiohttp.ClientTimeout(total=30, connect=5, sock_read=25)
        _sess = S.llm_session
        if _sess is None or _sess.closed:
            _sess = aiohttp.ClientSession()
        S.logger.info("[OLLAMA CALL] endpoint=%s model=%s query_type=translate", LLM_URL, OLLAMA_MODEL)
        async with _sess.post(LLM_URL, json=payload, timeout=timeout) as resp:
            S.logger.info("[OLLAMA CALL RESULT] status=%s endpoint=%s", resp.status, LLM_URL)
            if resp.status == 200:
                data = await resp.json()
                translated = data["message"]["content"].strip()

                # Validate: if translating to Arabic, result must contain Arabic characters
                if target_lang == "ar":
                    arabic_char_count = sum(1 for c in translated if '\u0600' <= c <= '\u06FF')
                    if arabic_char_count < 3:
                        S.logger.warning(
                            f"Translation to Arabic failed — model returned non-Arabic output: '{translated[:80]}'. Retrying with stricter prompt."
                        )
                        # Retry once with an even simpler, purely Arabic system prompt
                        retry_messages = [
                            {"role": "system", "content": "مترجم. أجب بالعربية فقط. لا إنجليزية إطلاقاً."},
                            {"role": "user", "content": f"ترجم: {text}"},
                        ]
                        payload["messages"] = retry_messages
                        S.logger.info("[OLLAMA CALL] endpoint=%s model=%s query_type=translate_retry", LLM_URL, OLLAMA_MODEL)
                        async with _sess.post(LLM_URL, json=payload, timeout=timeout) as resp2:
                            S.logger.info("[OLLAMA CALL RESULT] status=%s endpoint=%s", resp2.status, LLM_URL)
                            if resp2.status == 200:
                                data2 = await resp2.json()
                                translated = data2["message"]["content"].strip()
                                arabic_char_count2 = sum(1 for c in translated if '\u0600' <= c <= '\u06FF')
                                if arabic_char_count2 < 3:
                                    S.logger.warning(f"Arabic translation retry also failed. Falling back to original.")
                                    return text

                S.logger.info(f"Translation ({src}→{tgt}): '{text[:60]}' → '{translated[:60]}'")
                return translated
    except Exception as e:
        S.logger.warning(f"Translation failed ({src}→{tgt}): {e}")
    return text  # Fallback: return original text

def _clean_english_search_query_candidate(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip().strip('"\'`'))
    cleaned = re.sub(r"^(?:english\s+(?:translation|query)\s*[:\-]\s*)", "", cleaned, flags=re.IGNORECASE).strip()
    if not cleaned or len(cleaned) > 260:
        return ""
    if re.search(r"[\u0600-\u06FF]", cleaned):
        return ""
    if len(re.findall(r"[A-Za-z]{2,}", cleaned)) < 2:
        return ""
    return cleaned

def _expand_english_retrieval_query_terms(query_text: str) -> str:
    query = _clean_english_search_query_candidate(query_text)
    if not query:
        return ""
    lower = query.lower()
    additions: list[str] = []
    if re.search(r"\b(?:organi[sz]ation|organi[sz]ations|regulation)\b", lower):
        additions.extend(["organization", "organisation", "organizing", "organising", "organizational", "organisational"])
    if re.search(r"\b(?:recruitment|recruiting|human\s+resources?|hr)\b", lower):
        additions.extend(["staffing", "hiring", "employment", "personnel"])
    if re.search(r"\bstaffing\b", lower):
        additions.extend(["recruitment", "hiring", "employment", "personnel"])
    if not additions:
        return query
    seen: set[str] = set()
    ordered: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z\-']+", query) + additions:
        key = token.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(token)
    expanded = " ".join(ordered)
    return expanded[:260].strip()

async def _translate_arabic_query_for_search_with_llm(query_text: str) -> str:
    """Produce an English retrieval query when literal MT produced weak evidence."""
    global llm_session
    query_key = re.sub(r"\s+", " ", str(query_text or "").strip())
    if not query_key:
        return ""
    cached = S._translation_cache_get(query_key + "\n[llm_search_query]")
    if cached:
        return cached
    system_msg = (
        "You translate Arabic user questions into concise English search queries for retrieval. "
        "Preserve every Latin-script word or proper noun exactly. Choose natural English course/document terms when an Arabic term is ambiguous. "
        "For questions about functions, roles, processes, or relationships, use the functional sense rather than legal/regulatory or hiring-campaign senses. "
        "Do not answer the question. Output only the English query."
    )
    user_msg = f"Arabic question:\n{query_key}\n\nEnglish search query:"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "keep_alive": -1,
        "options": {"num_ctx": 2048, "num_gpu": 99, "temperature": 0.0, "num_predict": 96},
    }
    try:
        timeout = aiohttp.ClientTimeout(total=18, connect=5, sock_read=15)
        session = S.llm_session
        if session is None or session.closed:
            session = aiohttp.ClientSession()
        S.logger.info("[OLLAMA CALL] endpoint=%s model=%s query_type=ar_search_translation", LLM_URL, OLLAMA_MODEL)
        async with session.post(LLM_URL, json=payload, timeout=timeout) as resp:
            S.logger.info("[OLLAMA CALL RESULT] status=%s endpoint=%s", resp.status, LLM_URL)
            if resp.status == 200:
                data = await resp.json()
                candidate = _clean_english_search_query_candidate((data.get("message") or {}).get("content") or "")
                if candidate:
                    S._translation_cache_put(query_key + "\n[llm_search_query]", candidate)
                    return candidate
    except Exception as exc:
        S.logger.warning("[AR TRANSLATION FALLBACK] llm_search_query_failed=%s", exc)
    return ""

def _extract_latin_runs_from_query(query_text: str) -> list[str]:
    runs: list[str] = []
    for match in re.finditer(r"[A-Za-z][A-Za-z0-9+_.-]*(?:[ \t]+[A-Za-z][A-Za-z0-9+_.-]*)*", str(query_text or "")):
        run = re.sub(r"\s+", " ", match.group(0)).strip()
        if run and run not in runs:
            runs.append(run)
    return runs[:6]

def _normalize_arabic_keyword_for_non_llm_query(token: str) -> str:
    keyword = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", str(token or ""))
    keyword = re.sub(r"[إأآٱ]", "ا", keyword)
    keyword = keyword.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي").replace("ة", "ه")
    keyword = re.sub(r"[^\u0621-\u064A]", "", keyword).strip()
    if len(keyword) > 3 and keyword[0] in {"و", "ف"} and keyword[1:] not in _AR_QUERY_STOPWORDS:
        keyword = keyword[1:]
    return keyword

def _arabic_structural_search_hints(normalized_query: str) -> list[str]:
    normalized = f" {str(normalized_query or '').strip()} "
    hints: list[str] = []

    def _add(values: list[str]) -> None:
        for value in values:
            if value not in hints:
                hints.append(value)

    if re.search(r"\s(?:لماذا|ليش)\s|\b(?:سبب|اسباب|اهميه|مهم|مهمه)\b", normalized):
        _add(["why", "importance", "important", "reason", "purpose", "significance"])
    if re.search(r"\b(?:علاقه|العلاقه|يرتبط|ترتبط|ارتباط|بين)\b", normalized):
        _add(["relationship", "between", "related", "linked", "connected", "connection"])
    if re.search(r"\sكيف\s|\b(?:يدعم|تدعم|يساعد|تساعد|يساهم|تساهم)\b", normalized):
        _add(["how", "support", "supports", "helps", "role"])
    if re.search(r"\b(?:وظيفه|وظائف|عمليه|عمليات|دور)\b", normalized):
        _add(["function", "process", "role"])
    if not hints:
        hints.append("explanation")
    return hints[:8]

def _build_non_llm_arabic_explanation_query(query_text: str) -> str:
    original = re.sub(r"\s+", " ", str(query_text or "").strip())
    if not original:
        return ""
    normalized_query = S._normalize_arabic_query_surface(original)
    keywords: list[str] = []
    seen_keywords: set[str] = set()

    def _add_keyword(value: str) -> None:
        keyword = _normalize_arabic_keyword_for_non_llm_query(value)
        if len(keyword) < 3 or keyword in _AR_QUERY_STOPWORDS:
            return
        if keyword in seen_keywords:
            return
        seen_keywords.add(keyword)
        keywords.append(keyword)

    for token in re.findall(r"[\u0621-\u064A]+", original):
        _add_keyword(token)
    for token in S._query_tokens_for_evidence(original):
        if _is_arabic_text(token):
            _add_keyword(token)

    latin_runs = _extract_latin_runs_from_query(original)
    structural_hints = _arabic_structural_search_hints(normalized_query)
    parts = [original]
    if keywords:
        parts.append(" ".join(keywords[:10]))
    for latin_run in latin_runs:
        if latin_run and latin_run not in parts:
            parts.append(latin_run)
    if structural_hints:
        parts.append(" ".join(structural_hints))
    return re.sub(r"\s+", " ", " ".join(part for part in parts if part).strip())[:520]

def _repair_fast_arabic_search_query(original_arabic_query: str, english_query: str) -> str:
    query = _clean_english_search_query_candidate(english_query)
    if not query:
        return ""
    original_norm = S._normalize_arabic_query_surface(original_arabic_query)

    # Tiny phrase-sense repair for Arabic function wording only. This changes
    # retrieval-query wording, never the answer, and only when the user's own
    # Arabic phrasing indicates a function/process sense.
    if "وظيفه" in original_norm or "وظائف" in original_norm:
        query = re.sub(r"\brecruitment\s+function\b", "staffing", query, flags=re.IGNORECASE)
        query = re.sub(r"\brecruitment\b", "staffing", query, flags=re.IGNORECASE)
        query = re.sub(r"\brecruiting\b", "staffing", query, flags=re.IGNORECASE)
        if "تنظيم" in original_norm and not re.search(r"\b(?:law|legal|policy|rule|rules|regulatory)\b", query, flags=re.IGNORECASE):
            query = re.sub(r"\ban\s+organization\b", "organising", query, flags=re.IGNORECASE)
            query = re.sub(r"\borganization\b", "organising", query, flags=re.IGNORECASE)
            query = re.sub(r"\borganizing\b", "organising", query, flags=re.IGNORECASE)
            query = re.sub(r"\bregulation\b", "organising", query, flags=re.IGNORECASE)
    if "رقابه" in original_norm and ("تخطيط" in original_norm or "اداره" in original_norm or "علاقه" in original_norm):
        query = re.sub(r"\bmonitoring\b", "controlling", query, flags=re.IGNORECASE)
        query = re.sub(r"\bsupervision\b", "controlling", query, flags=re.IGNORECASE)

    for latin_run in _extract_latin_runs_from_query(original_arabic_query):
        if latin_run and latin_run not in query:
            query = f"{query} {latin_run}".strip()
    return _clean_english_search_query_candidate(query)

async def _build_fast_arabic_explanation_query(query_text: str, t_meta: dict | None = None) -> tuple[str, str]:
    query_key = re.sub(r"\s+", " ", str(query_text or "").strip())
    if not query_key:
        return "", "empty"
    t0 = time.perf_counter()
    provider = "non_llm_query_builder"
    cached_entry = S._ar_non_llm_query_cache_get(query_key)
    cache_hit = bool(cached_entry and cached_entry.get("normalized_query"))
    if cache_hit:
        candidate = str((cached_entry or {}).get("normalized_query") or "").strip()
    else:
        candidate = _build_non_llm_arabic_explanation_query(query_key)
        if candidate:
            S._ar_non_llm_query_cache_put(query_key, {
                "normalized_query": candidate,
                "provider": provider,
            })
    if not candidate:
        provider = "failed"
    elapsed_ms = int(round((time.perf_counter() - t0) * 1000))
    if t_meta is not None:
        t_meta["ar_fast_query_ms"] = elapsed_ms
        t_meta["query_translation_ms"] = elapsed_ms
        t_meta["query_translation_skipped"] = True
        t_meta["ar_fast_query_provider"] = provider
        t_meta["query_translation_cache_hit"] = cache_hit
    S.logger.info("[AR FAST QUERY] original=%s", query_key[:240])
    S.logger.info("[AR FAST QUERY] retrieval_query=%s", candidate[:240])
    S.logger.info("[AR FAST QUERY] cache_hit=%s", cache_hit)
    S.logger.info("[AR FAST QUERY] provider=%s time_ms=%s", provider, elapsed_ms)
    return candidate, provider

async def _build_llm_arabic_explanation_query(query_text: str, t_meta: dict | None = None) -> tuple[str, str]:
    query_key = re.sub(r"\s+", " ", str(query_text or "").strip())
    if not query_key:
        return "", "empty"
    t0 = time.perf_counter()
    provider = "llm_search_query"
    cached = S._translation_cache_get(query_key + "\n[llm_search_query]")
    if cached:
        provider = "llm_search_query_cache"
        candidate = cached
    else:
        candidate = await _translate_arabic_query_for_search_with_llm(query_key)
    candidate = _repair_fast_arabic_search_query(query_key, candidate)
    if not candidate:
        provider = "external_translation"
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: __import__('deep_translator', fromlist=['GoogleTranslator'])
                           .GoogleTranslator(source='ar', target='en').translate(query_key)
            )
            candidate = _repair_fast_arabic_search_query(query_key, result if result else "")
        except Exception as exc:
            S.logger.warning("[AR FAST QUERY] external_translation_failed=%s", exc)
            candidate = ""
    if not candidate:
        provider = "failed"
    elapsed_ms = int(round((time.perf_counter() - t0) * 1000))
    if t_meta is not None:
        t_meta["query_translation_ms"] = elapsed_ms
        t_meta["query_translation_skipped"] = False
        t_meta["ar_llm_query_ms"] = elapsed_ms
        t_meta["ar_llm_query_provider"] = provider
        t_meta["query_translation_cache_hit"] = bool(provider == "llm_search_query_cache")
    S.logger.info("[AR LLM QUERY FALLBACK] provider=%s time_ms=%s", provider, elapsed_ms)
    S.logger.info("[AR LLM QUERY FALLBACK] english_query=%s", candidate[:240])
    return candidate, provider

async def _build_external_arabic_explanation_query(query_text: str, t_meta: dict | None = None) -> tuple[str, str]:
    query_key = re.sub(r"\s+", " ", str(query_text or "").strip())
    if not query_key:
        return "", "empty"
    t0 = time.perf_counter()
    provider = "external_translation"
    cache_key = query_key + "\n[external_search_query]"
    cached = S._translation_cache_get(cache_key)
    if cached:
        provider = "external_translation_cache"
        candidate = cached
    else:
        candidate = ""
        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: __import__('deep_translator', fromlist=['GoogleTranslator'])
                               .GoogleTranslator(source='ar', target='en').translate(query_key),
                ),
                timeout=6.0,
            )
            candidate = _repair_fast_arabic_search_query(query_key, result if result else "")
            if candidate:
                S._translation_cache_put(cache_key, candidate)
        except Exception as exc:
            S.logger.warning("[AR NON-LLM QUERY FALLBACK] external_translation_failed=%s", exc)
            candidate = ""
    candidate = _repair_fast_arabic_search_query(query_key, candidate)
    if not candidate:
        provider = "failed"
    elapsed_ms = int(round((time.perf_counter() - t0) * 1000))
    if t_meta is not None:
        t_meta["ar_external_query_ms"] = elapsed_ms
        t_meta["ar_external_query_provider"] = provider
        if provider == "external_translation_cache":
            t_meta["query_translation_cache_hit"] = True
    S.logger.info("[AR NON-LLM QUERY FALLBACK] provider=%s time_ms=%s", provider, elapsed_ms)
    S.logger.info("[AR NON-LLM QUERY FALLBACK] english_query=%s", candidate[:240])
    return candidate, provider

def _retrieval_candidate_strength(query_text: str, docs: list[dict] | None) -> float:
    if not docs:
        return -999.0
    try:
        metrics = S._retrieval_evidence_metrics(query_text, docs or [])
    except Exception:
        metrics = {"coverage": 0.0, "focus_ratio": 0.0, "semantic_density": 0.0, "max_similarity": 0.0}
    try:
        weak = S._is_weak_retrieval_evidence(query_text, S._classify_query_family(query_text), docs or [])
    except Exception:
        weak = False
    best_rank = S._best_doc_rank_score(docs or [])
    return (
        best_rank
        + (float(metrics.get("coverage", 0.0) or 0.0) * 2.0)
        + (float(metrics.get("focus_ratio", 0.0) or 0.0) * 0.8)
        + min(len(docs or []), 6) * 0.05
        - (1.5 if weak and best_rank < 0.0 else 0.0)
    )

def _translation_retrieval_is_weak(query_text: str, docs: list[dict] | None) -> bool:
    if not docs:
        return True
    best_rank = S._best_doc_rank_score(docs or [])
    try:
        metrics = S._retrieval_evidence_metrics(query_text, docs or [])
    except Exception:
        metrics = {"coverage": 0.0, "focus_ratio": 0.0}
    if best_rank >= 0.5 and float(metrics.get("coverage", 0.0) or 0.0) > 0.0:
        return False
    if best_rank < 0.0 and float(metrics.get("coverage", 0.0) or 0.0) < 0.70:
        return True
    try:
        return bool(S._is_weak_retrieval_evidence(query_text, S._classify_query_family(query_text), docs or []))
    except Exception:
        return best_rank < 0.0

async def _maybe_improve_arabic_translation_retrieval(
    original_arabic_query: str,
    translated_query: str,
    translated_docs: list[dict] | None,
    protected_terms: list[str] | None,
    t_meta: dict | None = None,
) -> tuple[str, list[dict] | None]:
    if not _translation_retrieval_is_weak(translated_query, translated_docs):
        return translated_query, translated_docs
    llm_query = await _translate_arabic_query_for_search_with_llm(original_arabic_query)
    if not llm_query or llm_query.strip().lower() == str(translated_query or "").strip().lower():
        return translated_query, translated_docs
    candidate_queries = [llm_query]
    expanded_query = _expand_english_retrieval_query_terms(llm_query)
    if expanded_query and expanded_query.lower() != llm_query.lower():
        candidate_queries.append(expanded_query)
    t_start = time.perf_counter()
    best_query = ""
    best_docs: list[dict] | None = None
    best_strength = -999.0
    for candidate_query in candidate_queries:
        try:
            candidate_docs = S._search_with_query_expansion(
                candidate_query,
                top_k=10,
                distance_threshold=S._distance_threshold_for_query(candidate_query),
                return_dicts=True,
            ) or []
            if protected_terms:
                candidate_docs = S._filter_docs_by_protected_terms(candidate_docs or [], protected_terms)
        except Exception:
            S.logger.exception("[AR TRANSLATION FALLBACK] llm_search_retrieval_failed=True query=%s", candidate_query[:160])
            continue
        candidate_strength_local = _retrieval_candidate_strength(candidate_query, candidate_docs)
        if candidate_query == expanded_query and candidate_docs:
            candidate_strength_local += 0.25
        if candidate_strength_local > best_strength:
            best_strength = candidate_strength_local
            best_query = candidate_query
            best_docs = candidate_docs
    if t_meta is not None:
        t_meta["llm_search_translation_retrieval_ms"] = int(round((time.perf_counter() - t_start) * 1000))
    current_strength = _retrieval_candidate_strength(translated_query, translated_docs)
    candidate_strength = best_strength
    accepted = bool(best_docs and best_query and candidate_strength > current_strength + 0.35)
    S.logger.info(
        "[AR TRANSLATION FALLBACK] llm_search_query=%s docs=%s current_strength=%.3f candidate_strength=%.3f accepted=%s",
        best_query[:160],
        len(best_docs or []),
        current_strength,
        candidate_strength,
        accepted,
    )
    if accepted:
        S._translation_cache_put(original_arabic_query, best_query)
        return best_query, best_docs
    return translated_query, translated_docs

