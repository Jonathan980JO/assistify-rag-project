import re

with open('assistify_rag_server.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace the sentence = await asyncio.wait_for(...) in tts_consumer with a try-except.
# First, revert the patch if it's there.
text = text.replace('sentence = await asyncio.wait_for(sentence_queue.get(), timeout=15.0)', 'sentence = await sentence_queue.get()')

fix_queue_code = """
                try:
                    sentence = await asyncio.wait_for(sentence_queue.get(), timeout=8.0)
                except asyncio.TimeoutError:
                    if cancel_event and cancel_event.is_set():
                        break
                    continue
"""
text = text.replace('sentence = await sentence_queue.get()', fix_queue_code)

# Replace the Ollama default behavior in Safe Mode - disable background heavy warmup
text = text.replace(
    'await _warmup_llm()',
    'if not globals().get("ASSISTIFY_SAFE_MODE", False): await _warmup_llm()'
)

text = text.replace(
    'await _warmup_xtts()',
    'if not globals().get("ASSISTIFY_DISABLE_TTS", False): await _warmup_xtts()'
)

# And RAG search timeout - _async_rag_search
text = text.replace(
    'async with _rag_lock:',
    'async with _rag_lock:\n        if globals().get("ASSISTIFY_SAFE_MODE", False):\n            kwargs["top_k"] = RAG_TOP_K_DEFAULT'
)

# Fix max_tokens block for call_llm_streaming context_block
text = text.replace('token_limit = 260', 'token_limit = 150 if globals().get("ASSISTIFY_SAFE_MODE", False) else 260')

with open('assistify_rag_server.py', 'w', encoding='utf-8') as f:
    f.write(text)
