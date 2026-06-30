"""Lightweight English dictionary fallback for typo correction when KB vocab misses."""
from __future__ import annotations

# Common English support / help-desk vocabulary (no external dependency).
_COMMON_ENGLISH_WORDS: frozenset[str] = frozenset({
    "about", "account", "address", "after", "again", "agent", "answer", "apply",
    "available", "back", "before", "billing", "business", "cancel", "card", "change",
    "charge", "chat", "check", "claim", "clear", "click", "close", "code", "company",
    "confirm", "contact", "cost", "could", "credit", "customer", "date", "days",
    "delivery", "detail", "discount", "does", "email", "error", "every", "expire",
    "failed", "feature", "first", "follow", "free", "from", "fuel", "gasoline",
    "guide", "have", "help", "here", "hours", "how", "information", "issue",
    "item", "know", "last", "like", "link", "list", "login", "make", "manage",
    "message", "method", "money", "more", "name", "need", "next", "number",
    "offer", "online", "open", "order", "other", "package", "password", "payment",
    "phone", "place", "plan", "please", "policy", "price", "problem", "process",
    "product", "provide", "purchase", "question", "quote", "rate", "reason",
    "receive", "refund", "register", "replace", "reply", "request", "reset",
    "response", "return", "review", "right", "same", "search", "second", "send", "service",
    "enterprise", "growth", "business", "audit", "memory", "compliance", "kubernetes",
    "ship", "shipping", "should", "sign", "since", "start", "status", "still",
    "submit", "support", "system", "take", "tell", "thank", "that", "their",
    "them", "there", "these", "they", "thing", "this", "those", "through",
    "ticket", "time", "today", "total", "track", "tracking", "trial", "try",
    "under", "update", "upgrade", "user", "using", "verify", "version", "want",
    "warranty", "week", "what", "when", "where", "which", "while", "will",
    "with", "within", "without", "work", "would", "wrong", "year", "your",
})


def english_dictionary_fallback(token: str) -> str | None:
    """Return the token if it is a known common English word (lowercase lookup)."""
    low = (token or "").strip().lower()
    if len(low) < 4 or not low.isalpha():
        return None
    if low in _COMMON_ENGLISH_WORDS:
        return low
    return None
