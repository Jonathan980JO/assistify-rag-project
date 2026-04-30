# PHASE AR-1B Final Report - Arabic Routing and Answer Language

## Status

Completed and validated against the live login-proxied WebSocket and the visible chat UI.

## Files Changed

- `backend/assistify_rag_server.py`

No embeddings, reranker model, chunking, or global `top_k` settings were changed.

## What Changed

### 1. Arabic standalone vs follow-up routing

Added a generic Arabic route classifier that uses query structure rather than domain vocabulary:

- Arabic interrogative/new-question patterns such as `ما هو`, `ما هي`, `كيف`, `لماذا`, `هل`, `اذكر`, `عدد`, `اشرح`, `قارن`, and `ما الفرق بين` classify standalone questions when they contain a real topic.
- Explicit deictic/contextual Arabic phrases such as `وضح أكثر`, `تابع`, `ماذا تقصد`, and `اشرح أكثر عنه` can still classify as true follow-ups.
- Fresh bare comparisons such as `ما الفرق؟` remain protected by the strict no-history fallback path.

Integrated the classifier into:

- `_is_followup_query`
- `call_llm_streaming`
- text `/ws` routing
- voice transcript routing

### 2. Arabic final answer language

Added final-language enforcement before display, history save, and TTS handoff:

- `_ensure_arabic_answer_language(...)`
- `_language_letter_counts(...)`
- `_is_mostly_english_text(...)`
- `_has_latin_script_contamination(...)`
- `_has_non_arabic_letter_contamination(...)`
- `_needs_arabic_language_rewrite(...)`
- `_translate_to_arabic_external_fallback(...)`

The exact strict fallback remains unchanged:

```text
Not found in the document.
```

Important validation discovery: Qwen can translate English into malformed mixed-script Arabic such as `النفسologia` or `processe...`. The guard now rejects any alphabetic contamination outside Arabic script, not only mostly-English text. Local LLM translation is tried first; if it fails clean-Arabic validation, a generic `deep_translator` fallback is used. This is not a hardcoded answer path.

### 3. Arabic Piper TTS guard

Added `_guard_arabic_tts_text(...)` at all Arabic Piper handoff points:

- `_tts_arabic_response`
- `_tts_single_response`
- WebSocket TTS consumer

Arabic Piper now receives clean Arabic text for supported Arabic answers. If conversion cannot produce clean Arabic, Arabic Piper is not called. The exact strict fallback is preserved as-is.

### 4. Generic Arabic prompt and fallback cleanup

The Arabic system prompt was generalized away from older domain-specific wording. Arabic no-document fallback now uses the exact strict fallback string.

## Validation

### Static validation

- Pylance syntax check: passed
- `py_compile`: passed
- VS Code Problems for `backend/assistify_rag_server.py`: no errors

### Live `/ws` validation through login proxy

All tests were sent through `ws://127.0.0.1:7001/ws` from the authenticated frontend page.

| Query | Language | Result | Sources | Script check | TTS |
|---|---:|---|---:|---|---|
| `ما هو علم النفس؟` | ar | `علم النفس هو الدراسة العلمية للسلوك والعمليات العقلية.` | 5 | Arabic 46, Latin 0, other 0 | Piper Arabic called |
| `ما هي وظائف الإدارة الخمسة؟` after psychology in the same connection | ar | `التخطيط التنظيم توظيف القيادة الرقابة` | 3 | Arabic 33, Latin 0, other 0 | Piper Arabic called |
| `ما الفرق؟` in fresh connection | ar | `Not found in the document.` | 0 | strict fallback preserved | Piper Arabic called for strict fallback |
| `ما هي أهداف علم النفس؟` | ar | `الملاحظة الوصف الفهم الشرح التنبؤ السيطرة على سلوك الإنسان والعمليات العقلية` | 4 | Arabic 66, Latin 0, other 0 | Piper Arabic called |
| `ما الفرق بين علم النفس والإدارة؟` | ar | Arabic grounded comparison of psychology vs management | 6 | Arabic 306, Latin 0, other 0 | Piper Arabic called |
| `What are the 5 functions of management?` | en | English management list | 1 | English unchanged | English TTS called |
| `What are the goals of psychology?` | en | English psychology goals list | 3 | English unchanged | English TTS called |

### Visible UI validation

The actual frontend page at `http://127.0.0.1:7001/frontend/index.html` was tested in Arabic mode.

Input:

```text
ما هي وظائف الإدارة الخمسة؟
```

Displayed transcript:

```text
أنت: ما هي وظائف الإدارة الخمسة؟
المساعد: التخطيط التنظيم توظيف الموظفين القيادة الرقابة
```

UI proof:

- input direction: `rtl`
- assistant Arabic letters: 48
- assistant Latin letters: 0

## Proof Logs

Backend proof log excerpts from `C:\Users\MK\Desktop\assistify_rag_live.log`:

```text
[ARABIC ROUTE] standalone=True reason=arabic_interrogative_with_topic
[ARABIC TRANSLATION FALLBACK] provider=deep_translator success=True
[ARABIC ANSWER LANGUAGE] converted=True reason=send_final_response:definition_route_deterministic:translated_from_english
[ARABIC TTS GUARD] passed=True reason=_tts_single_response:arabic_clean
[ARABIC TTS] engine=piper language=ar
[WS FINAL ANSWER BEFORE SEND] علم النفس هو الدراسة العلمية للسلوك والعمليات العقلية.
```

```text
[ARABIC ROUTE] standalone=True reason=arabic_interrogative_with_topic
[ARABIC ANSWER LANGUAGE] converted=True reason=send_final_response:list_lexical_rescue:translated_from_english
[ARABIC TTS GUARD] passed=True reason=_tts_single_response:arabic_clean
[ARABIC TTS] engine=piper language=ar
[WS FINAL ANSWER BEFORE SEND] التخطيط التنظيم توظيف القيادة الرقابة
```

```text
[ARABIC ROUTE] standalone=False reason=arabic_bare_comparison_guard
[ARABIC ANSWER LANGUAGE] converted=False reason=send_final_response:bare_comparison_no_history:strict_fallback
[ARABIC TTS GUARD] passed=True reason=_tts_single_response:strict_fallback
[WS FINAL ANSWER BEFORE SEND] Not found in the document.
```

## Before / After

Before AR-1B:

- Arabic mode called Arabic TTS but could send English final text to Piper.
- Arabic standalone questions could be misrouted as follow-ups.
- `ما هي وظائف الإدارة الخمسة؟` could return the previous psychology answer.

After AR-1B:

- Arabic standalone questions route into normal translated RAG.
- Same-session `ما هي وظائف الإدارة الخمسة؟` after a psychology question returns the management functions.
- Supported Arabic-mode final answers are clean Arabic before TTS.
- English behavior remains intact.
- Strict fallback remains exactly `Not found in the document.`

## Notes

The fallback translator only runs when the local LLM fails clean-Arabic validation. It is generic translation, not an answer template, and does not alter retrieval, reranking, chunking, or grounding rules.