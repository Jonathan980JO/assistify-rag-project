"""TTS text chunking and preprocessing."""
from __future__ import annotations

import re

try:
    from backend.config_head import RAG_NO_MATCH_RESPONSE
except Exception:
    RAG_NO_MATCH_RESPONSE = "Not found in the document."

_AR_TTS_DIGIT_MAP = {
    '0': 'صِفر', '1': 'واحِد', '2': 'اثنان', '3': 'ثلاثة',
    '4': 'أربعة', '5': 'خمسة', '6': 'ستة', '7': 'سبعة',
    '8': 'ثمانية', '9': 'تسعة',
}

def normalize_tts_chunk_cache_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_tts_not_found_text(value: str) -> bool:
    return normalize_tts_chunk_cache_text(value).lower() == RAG_NO_MATCH_RESPONSE.lower()


def is_tts_bullet_unit(value: str) -> bool:
    return bool(re.match(r"^\s*(?:[-*\u2022]|\d+[.)])\s+\S", str(value or "")))


def join_tts_units(units: list[str]) -> str:
    cleaned = [str(unit or "").strip() for unit in units if str(unit or "").strip()]
    if not cleaned:
        return ""
    if any(is_tts_bullet_unit(unit) for unit in cleaned):
        return "\n".join(cleaned).strip()
    return " ".join(cleaned).strip()


def split_long_tts_unit(unit: str, max_chars: int) -> list[str]:
    text = str(unit or "").strip()
    if len(text) <= max_chars:
        return [text] if text else []
    words = text.split()
    if len(words) <= 1:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word]).strip()
        if current and len(candidate) > max_chars:
            parts.append(" ".join(current).strip())
            current = [word]
        else:
            current.append(word)
    if current:
        parts.append(" ".join(current).strip())
    return [part for part in parts if part]


def spoken_tts_units(text: str) -> list[str]:
    units: list[str] = []
    for line in re.split(r"\n+", str(text or "")):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            continue
        if is_tts_bullet_unit(line):
            units.extend(split_long_tts_unit(line, 240))
            continue
        start = 0
        for match in re.finditer(r"[.!?\u061f\u060c\u061b;:]+(?:\s+|$)", line):
            piece = line[start:match.end()].strip()
            if piece:
                units.extend(split_long_tts_unit(piece, 240))
            start = match.end()
        tail = line[start:].strip()
        if tail:
            units.extend(split_long_tts_unit(tail, 240))
    return [unit for unit in units if unit]


def split_spoken_text_for_tts(text: str, language: str = "en") -> list[str]:
    spoken_text = str(text or "").strip()
    if not spoken_text:
        return []
    total_chars = len(spoken_text)
    if is_tts_not_found_text(spoken_text) or total_chars <= 150:
        return [spoken_text]

    units = spoken_tts_units(spoken_text)
    if not units:
        return [spoken_text]
    if len(units) == 1 and len(units[0]) <= 240:
        return [spoken_text]

    first_target = max(45, min(180, int(total_chars * 0.28)))
    first_max = max(70, min(220, int(total_chars * 0.35)))
    rest_target = 210 if str(language or "").lower() == "ar" else 230
    rest_max = 280

    chunks: list[str] = []
    current_units: list[str] = []
    current_limit = first_max
    first_done = False

    for unit in units:
        candidate = join_tts_units(current_units + [unit])
        if current_units and len(candidate) > current_limit:
            chunk = join_tts_units(current_units)
            if chunk:
                chunks.append(chunk)
            current_units = [unit]
            if not first_done:
                first_done = True
            current_limit = rest_max
            continue

        current_units.append(unit)
        current_text = join_tts_units(current_units)
        if not first_done and (len(current_text) >= first_target or len(current_text) >= first_max):
            chunks.append(current_text)
            current_units = []
            first_done = True
            current_limit = rest_max
        elif first_done and len(current_text) >= rest_target:
            chunks.append(current_text)
            current_units = []

    if current_units:
        chunks.append(join_tts_units(current_units))

    merged: list[str] = []
    for chunk in [chunk for chunk in chunks if chunk.strip()]:
        if merged and len(chunk) < 35:
            merged[-1] = join_tts_units([merged[-1], chunk])
        else:
            merged.append(chunk)
    if len(merged) > 1 and len(merged[-1]) < 35:
        last = merged.pop()
        merged[-1] = join_tts_units([merged[-1], last])
    return merged or [spoken_text]
def preprocess_for_tts(text: str, language: str = "ar") -> str:
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
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)   # headings
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)          # bold/italic
    # Numbered list items: replace "1." / "2." etc. with a comma separator
    text = re.sub(r'(?m)^\s*\d+\.\s+', '، ', text)
    # Bullet list items
    text = re.sub(r'(?m)^\s*[-•]\s+', '، ', text)

    if language == "ar":
        # 2. Expand isolated single digits ('3 سنوات' → 'ثلاثة سنوات')
        text = re.sub(
            r'(?<!\d)\d(?!\d)',
            lambda m: _AR_TTS_DIGIT_MAP.get(m.group(), m.group()),
            text,
        )

        # 3. Collapse repeated punctuation
        text = re.sub(r'[،,]{2,}', '،', text)
        text = re.sub(r'[؟?!]{2,}', lambda m: m.group()[0], text)

        # 4. Add trailing pause if chunk ends without punctuation
        #    (signals XTTS that the phrase is complete → prevents rushed ending)
        if text and text[-1] not in '.؟?!،,؛:':
            text = text + '،'

    # 5. Remove emoji
    text = re.sub(
        r'[\U0001F300-\U0001FAFF\U0001F900-\U0001F9FF\U00002600-\U000027BF]',
        '', text,
    )

    # Collapse multiple spaces / newlines
    text = re.sub(r'\s+', ' ', text).strip()
    return text
