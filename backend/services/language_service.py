"""Language-resolution business logic for the RAG backend.

Extracted verbatim from ``assistify_rag_server.py`` during the Phase 3 refactor.
These are pure, document-agnostic heuristics (script detection only) with no
module-global state, no DB access and no FastAPI imports.
"""


def _detect_language(text: str) -> str:
    """Heuristic language detection: returns 'ar' if Arabic chars dominate, else 'en'."""
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    return "ar" if arabic_chars > len(text) * 0.2 else "en"


def _resolve_user_language(query_text: str, ui_language: str | None) -> str:
    """Resolve the user's effective language for both answer-generation and TTS.

    The script of the user's actual query is the source of truth; the UI/session
    language is only a hint. This is intentionally generic — it never inspects
    document content or domain words and works for any Arabic / English text.

    Returns "ar" or "en". Falls back to the UI language only when the query
    itself contains no Arabic and no Latin letters.
    """
    s = str(query_text or "")
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in s)
    has_latin = any(('a' <= c.lower() <= 'z') for c in s)
    if has_arabic and not has_latin:
        return "ar"
    if has_latin and not has_arabic:
        return "en"
    if has_arabic:
        # Mixed: use the same proportion rule as _detect_language.
        return _detect_language(s)
    ui = str(ui_language or "").strip().lower()
    return ui if ui in ("ar", "en") else "en"
