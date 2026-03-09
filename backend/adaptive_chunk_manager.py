"""
Adaptive TTS Chunk Manager — Timer + Word-Count State Machine
==============================================================
Optimised for **perceived response speed** (time-to-first-audio), NOT
total pipeline completion time.

Strategy
--------
FIRST CHUNK  – Fire as fast as possible:
  • 6-8 words accumulated  OR  700 ms since first LLM token
  • Punctuation is IGNORED for the first chunk.

SUBSEQUENT CHUNKS – Balance quality vs latency:
  • 10-14 words accumulated  OR  500 ms buffer timeout  OR  sentence ends
  • Punctuation is a *preference*, never a hard gate.

The manager also tracks first-chunk latency across queries and adjusts
the word targets (via performance tiers) so slow systems automatically
use fewer words per chunk.

Performance Tiers (applied to *subsequent* chunks only):
  - Fast   (< 4 s first-chunk):  12-15 words
  - Medium (4-6 s first-chunk):  10-12 words
  - Slow   (> 6 s first-chunk):   8-10 words
"""

from __future__ import annotations

import logging
import re
import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("adaptive_chunk")

# ---------------------------------------------------------------------------
# Performance tier definitions (for subsequent chunks)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Tier:
    name: str
    min_words: int
    max_words: int
    buffer_delay: float  # seconds between TTS chunks (0 = no delay)


TIER_FAST   = _Tier("fast",   10, 14, 0.0)
TIER_MEDIUM = _Tier("medium",  8, 12, 0.05)
TIER_SLOW   = _Tier("slow",    6,  8, 0.15)

# ---------------------------------------------------------------------------
# First-chunk policy — aggressive low-latency
# ---------------------------------------------------------------------------

FIRST_CHUNK_MIN_WORDS  = 5       # send first chunk after this many words …
FIRST_CHUNK_MAX_WORDS  = 8       # … or hard-cap at this many
FIRST_CHUNK_TIMEOUT_MS = 380     # … or after 380 ms since first token (whichever is first)

# ---------------------------------------------------------------------------
# Subsequent-chunk flush policy
# ---------------------------------------------------------------------------

SUBSEQUENT_TIMEOUT_MS  = 500     # flush accumulated words after 500 ms even without punctuation

# Thresholds (seconds) for the first TTS chunk latency → tier classification
_FAST_THRESHOLD   = 1.0
_MEDIUM_THRESHOLD = 2.0

# How many recent measurements to keep for rolling average.
# Keep this small so the tier re-classifies quickly when latency improves
# (e.g. after switching from inference() to inference_stream()).
_HISTORY_SIZE = 5


# ---------------------------------------------------------------------------
# Per-query snapshot
# ---------------------------------------------------------------------------

@dataclass
class ChunkPerformanceSnapshot:
    """Immutable record of how one query performed."""
    first_chunk_latency_s: float
    tier: _Tier
    words_per_chunk: int
    buffer_delay_s: float
    total_chunks: int = 0
    total_tts_time_s: float = 0.0


# ---------------------------------------------------------------------------
# Adaptive Chunk Manager (singleton-friendly, thread-safe)
# ---------------------------------------------------------------------------

class AdaptiveChunkManager:
    """Decides how many words each TTS chunk should contain.

    The LLM producer calls :meth:`begin_query` at the start of each query,
    then uses the first-chunk and subsequent-chunk policies to decide when
    to dispatch accumulated words to TTS — *without* blocking on punctuation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        self._latency_history: deque[float] = deque(maxlen=_HISTORY_SIZE)
        self._tier: _Tier = TIER_FAST
        self._words_per_chunk: int = TIER_FAST.max_words
        self._buffer_delay: float = TIER_FAST.buffer_delay

        self._total_queries: int = 0
        self._snapshots: deque[ChunkPerformanceSnapshot] = deque(maxlen=50)
        self._first_chunk_recorded: bool = False

        logger.info(
            "AdaptiveChunkManager initialised | tier=%s words=%d buf=%.2fs",
            self._tier.name, self._words_per_chunk, self._buffer_delay,
        )

    # ── public API ──────────────────────────────────────────────

    def begin_query(self) -> tuple[int, float]:
        """Call at the start of each query.  Returns (subsequent_words, buffer_delay).

        NOTE: Tier re-evaluation is deferred until after the first chunk
        is flushed (via :meth:`record_first_chunk_latency`).  This ensures
        the first-chunk override is never influenced by tier switching.
        """
        with self._lock:
            self._first_chunk_recorded = False
            self._total_queries += 1
            # Tier re-evaluation is intentionally NOT done here.
            # It happens in record_first_chunk_latency() — only after
            # the first chunk has already been flushed by the producer.
            return self._words_per_chunk, self._buffer_delay

    # ---------- first chunk policy ----------

    @staticmethod
    def first_chunk_min_words() -> int:
        return FIRST_CHUNK_MIN_WORDS

    @staticmethod
    def first_chunk_max_words() -> int:
        return FIRST_CHUNK_MAX_WORDS

    @staticmethod
    def first_chunk_timeout_s() -> float:
        return FIRST_CHUNK_TIMEOUT_MS / 1000.0

    # ---------- subsequent chunk policy ----------

    def subsequent_words(self) -> int:
        """Target word count for chunks after the first."""
        with self._lock:
            return self._words_per_chunk

    def subsequent_hard_max(self) -> int:
        with self._lock:
            return self._words_per_chunk + 4

    @staticmethod
    def subsequent_timeout_s() -> float:
        return SUBSEQUENT_TIMEOUT_MS / 1000.0

    def get_buffer_delay(self) -> float:
        with self._lock:
            return self._buffer_delay

    # ---------- latency feedback ----------

    def record_first_chunk_latency(self, latency_s: float) -> tuple[int, float]:
        """Record the first-chunk TTS latency and THEN re-evaluate the tier.

        This is the ONLY place where tier switching is allowed.  It is
        called by tts_consumer *after* the first chunk has already been
        flushed and sent — so the first chunk is never affected by tier
        changes.
        """
        with self._lock:
            if self._first_chunk_recorded:
                return self._words_per_chunk, self._buffer_delay

            self._first_chunk_recorded = True
            self._latency_history.append(latency_s)

            # --- tier switch happens HERE, safely after first flush ---
            old_tier = self._tier
            self._tier = self._classify_tier(latency_s)
            self._words_per_chunk = self._pick_word_count(self._tier)
            self._buffer_delay = self._tier.buffer_delay

            # Also apply rolling-average re-evaluation for future queries
            if len(self._latency_history) > 1:
                self._reevaluate_tier()

            if self._tier != old_tier:
                logger.info(
                    "Tier changed AFTER first flush: %s → %s  (latency=%.2fs)  words=%d  buf=%.2fs",
                    old_tier.name, self._tier.name, latency_s,
                    self._words_per_chunk, self._buffer_delay,
                )

            logger.info(
                "First-chunk latency=%.2fs | tier=%s | words=%d | buf=%.2fs",
                latency_s, self._tier.name, self._words_per_chunk, self._buffer_delay,
            )
            return self._words_per_chunk, self._buffer_delay

    def current_chunk_size(self) -> tuple[int, float]:
        with self._lock:
            return self._words_per_chunk, self._buffer_delay

    def finish_query(self, total_chunks: int = 0, total_tts_time_s: float = 0.0):
        with self._lock:
            latency = self._latency_history[-1] if self._latency_history else 0.0
            snap = ChunkPerformanceSnapshot(
                first_chunk_latency_s=latency,
                tier=self._tier,
                words_per_chunk=self._words_per_chunk,
                buffer_delay_s=self._buffer_delay,
                total_chunks=total_chunks,
                total_tts_time_s=total_tts_time_s,
            )
            self._snapshots.append(snap)

    def get_stats(self) -> dict:
        with self._lock:
            avg_latency = (
                sum(self._latency_history) / len(self._latency_history)
                if self._latency_history else 0.0
            )
            return {
                "current_tier": self._tier.name,
                "words_per_chunk": self._words_per_chunk,
                "buffer_delay_s": self._buffer_delay,
                "total_queries": self._total_queries,
                "rolling_avg_latency_s": round(avg_latency, 3),
                "latency_history": [round(l, 3) for l in self._latency_history],
                "recent_snapshots": [
                    {
                        "first_chunk_latency_s": round(s.first_chunk_latency_s, 3),
                        "tier": s.tier.name,
                        "words_per_chunk": s.words_per_chunk,
                        "buffer_delay_s": s.buffer_delay_s,
                        "total_chunks": s.total_chunks,
                        "total_tts_time_s": round(s.total_tts_time_s, 3),
                    }
                    for s in list(self._snapshots)[-10:]
                ],
            }

    # ── internal helpers ────────────────────────────────────────

    @staticmethod
    def _classify_tier(latency_s: float) -> _Tier:
        if latency_s < _FAST_THRESHOLD:
            return TIER_FAST
        elif latency_s < _MEDIUM_THRESHOLD:
            return TIER_MEDIUM
        else:
            return TIER_SLOW

    @staticmethod
    def _pick_word_count(tier: _Tier) -> int:
        return (tier.min_words + tier.max_words) // 2

    def _reevaluate_tier(self):
        avg = sum(self._latency_history) / len(self._latency_history)
        new_tier = self._classify_tier(avg)
        if new_tier != self._tier:
            logger.info(
                "Tier adjusted (rolling avg %.2fs): %s → %s | words=%d buf=%.2fs",
                avg, self._tier.name, new_tier.name,
                self._pick_word_count(new_tier), new_tier.buffer_delay,
            )
        self._tier = new_tier
        self._words_per_chunk = self._pick_word_count(new_tier)
        self._buffer_delay = new_tier.buffer_delay


# ---------------------------------------------------------------------------
# Word-aware text chunker (utility — used outside the streaming pipeline)
# ---------------------------------------------------------------------------

_SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?])\s')


def chunk_text_by_words(
    text: str,
    target_words: int,
    *,
    hard_max_words: int | None = None,
) -> list[str]:
    """Split *text* into chunks of approximately *target_words* words,
    preferring to break at sentence boundaries when possible.
    """
    if hard_max_words is None:
        hard_max_words = target_words + 5

    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    buf: list[str] = []

    for word in words:
        buf.append(word)
        at_sentence_end = bool(re.search(r'[.!?]$', word))
        reached_target = len(buf) >= target_words
        reached_hard_max = len(buf) >= hard_max_words

        if (at_sentence_end and reached_target) or reached_hard_max:
            chunks.append(" ".join(buf))
            buf = []

    if buf:
        if chunks and len(buf) <= 3:
            chunks[-1] += " " + " ".join(buf)
        else:
            chunks.append(" ".join(buf))

    return [c.strip() for c in chunks if c.strip()]


# Module-level singleton
adaptive_manager = AdaptiveChunkManager()
