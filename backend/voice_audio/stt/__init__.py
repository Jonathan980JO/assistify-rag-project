from backend.voice_audio.stt.transcribe import (
    TranscriptionResult,
    run_transcription,
    _arabic_stt_unclear,
    _looks_like_english_stt_garbage_for_arabic,
)
from backend.voice_audio.stt.loader import (
    load_multilingual_whisper_model_if_available,
    resolve_multilingual_model_path,
    arabic_multilingual_model_ready,
    MULTILINGUAL_MODEL_PATH,
)
