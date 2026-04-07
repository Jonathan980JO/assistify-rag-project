import re
import os

with open('assistify_rag_server.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1) Make sure `aiResponseDone` is ALWAYS sent in `call_llm_streaming` if there is a failure.
# We make `call_llm_streaming` a wrapper.
wrapper_code = """async def call_llm_streaming(websocket: WebSocket, text: str, connection_id: str, user, cancel_event: asyncio.Event = None, t_meta=None, language: str = "en"):
    try:
        if globals().get("ASSISTIFY_SAFE_MODE", False):
            # force text only mode and override TTS flags if defined
            pass
        await _call_llm_streaming_impl(websocket, text, connection_id, user, cancel_event, t_meta, language)
    except Exception as e:
        import traceback
        logger.error(f'[{connection_id}] call_llm_streaming completely failed: {e}\\n{traceback.format_exc()}')
        try:
            _lock = _ws_write_locks.get(connection_id)
            if _lock:
                async with _lock:
                    await websocket.send_json({"type": "aiResponseChunk", "text": "\\n\\n[Connection Interrupted]"})
            else:
                await websocket.send_json({"type": "aiResponseChunk", "text": "\\n\\n[Connection Interrupted]"})
        except Exception:
            pass
    finally:
        try:
            _lock = _ws_write_locks.get(connection_id) 
            if _lock:
                async with _lock:
                    await websocket.send_json({"type": "aiResponseDone"})
            else:
                await websocket.send_json({"type": "aiResponseDone"})
        except Exception as e:
            logger.error(f"[{connection_id}] Error in aiResponseDone finally block: {e}")

async def _call_llm_streaming_impl(websocket: WebSocket, text: str, connection_id: str, user, cancel_event: asyncio.Event = None, t_meta=None, language: str = "en"):"""

if "def _call_llm_streaming_impl" not in text:
    text = text.replace(
        'async def call_llm_streaming(websocket: WebSocket, text: str, connection_id: str, user, cancel_event: asyncio.Event = None, t_meta=None, language: str = "en"):', 
        wrapper_code
    )

# 2) If ASSISTIFY_DISABLE_TTS is set, immediately return from tts_consumer
# Find async def tts_consumer():
disable_tts_code = """async def tts_consumer():
          if globals().get("ASSISTIFY_DISABLE_TTS", False): 
              return"""

if "ASSISTIFY_DISABLE_TTS" not in disable_tts_code in text:
    text = text.replace('async def tts_consumer():', disable_tts_code)

# 3) Check other infinite waiters in read loops
text = re.sub(
    r'(async for chunk in resp\.content\.iter_chunked\(\d+\):)',
    r'\1\n                                if globals().get("ASSISTIFY_DISABLE_TTS", False): break',
    text
)

# 4) Reduce default model loading context if safe mode is on
# E.g. Ollama streaming payload options
text = re.sub(
    r'("num_ctx":\s*)3072',
    r'\1 1024 if globals().get("ASSISTIFY_SAFE_MODE", False) else 3072',
    text
)

text = re.sub(
    r'("num_predict":\s*)(\d+)',
    r'\1 150 if globals().get("ASSISTIFY_SAFE_MODE", False) else \2',
    text
)

with open('assistify_rag_server.py', 'w', encoding='utf-8') as f:
    f.write(text)
