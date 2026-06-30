from pathlib import Path

p = Path("backend/voice_audio/tts/streaming.py")
t = p.read_text(encoding="utf-8")
repls = [
    ("_log_tts_cancelled", "log_tts_cancelled"),
    ("_ws_tts_is_active", "ws_tts_is_active"),
    ("_normalize_tts_chunk_cache_text", "normalize_tts_chunk_cache_text"),
    ("_preprocess_for_tts", "preprocess_for_tts"),
    ("_tts_cache_key", "tts_cache_key"),
    ("_tts_cache_get", "tts_cache_get"),
    ("_tts_cache_put", "tts_cache_put"),
    ("_wav_bytes_to_pcm16", "wav_bytes_to_pcm16"),
]
for a, b in repls:
    t = t.replace(a, b)
if "def _arabic_off_topic_response" not in t:
    helper = (
        "def _arabic_off_topic_response() -> str:\n"
        "    try:\n"
        "        from backend.assistify_rag_server import ARABIC_OFF_TOPIC_RESPONSE\n"
        "        return ARABIC_OFF_TOPIC_RESPONSE\n"
        "    except Exception:\n"
        "        return \"\"\n\n\n"
    )
    t = t.replace("logger = logging.getLogger", helper + "logger = logging.getLogger", 1)
    t = t.replace("text.strip() == ARABIC_OFF_TOPIC_RESPONSE", "text.strip() == _arabic_off_topic_response()")
p.write_text(t, encoding="utf-8")
print("fixed")
