"""Voice/audio subsystem: STT, TTS, WebSocket audio handling."""


async def init_voice_audio(app, *, safe_mode: bool = False, disable_warmup: bool = False):
    from backend.voice_audio.lifecycle import init_voice_audio as _init

    return await _init(app, safe_mode=safe_mode, disable_warmup=disable_warmup)


async def shutdown_voice_audio():
    from backend.voice_audio.lifecycle import shutdown_voice_audio as _shutdown

    return await _shutdown()


def register_voice_routes(app, require_login=None) -> None:
    from backend.voice_audio.tts.routes import router as tts_router

    app.include_router(tts_router)
    if require_login is not None:
        from backend.voice_audio.stt.routes import register_stt_routes
        from fastapi import APIRouter

        stt_router = APIRouter()
        register_stt_routes(stt_router, require_login)
        app.include_router(stt_router)
