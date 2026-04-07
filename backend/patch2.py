import re
import os

with open("assistify_rag_server.py", "r", encoding="utf-8") as f:
    orig = f.read()

# Make a backup
with open("assistify_rag_server.py.bak_em", "w", encoding="utf-8") as f:
    f.write(orig)

lines = orig.split("\n")

# Need to find the aiResponseDone send
# Also wrap call_llm_streaming with timeouts and graceful cleanup
# Disable the TTS consumer if ASSISTIFY_DISABLE_TTS is true

for i, line in enumerate(lines):
    pass # Wait, let's just use re.sub for safety wrapper

mod = orig

# Inject aiResponseDone in a finally block if missing, or we can just change the caller: `rag_ws_endpoint`.
# We want to make sure it responds when we ask "What is psychology?"
# 1. The hang point: queue.get() without a timeout?
mod = mod.replace("sentence_queue.get()", "asyncio.wait_for(sentence_queue.get(), timeout=15.0)")

# 2. Disable Reranker
mod = re.sub(
    r'(USE_RERANKER\s*=\s*)(True|False)', 
    r'\1False if ASSISTIFY_DISABLE_RERANKER else \2', 
    mod
)

# 3. Timeouts for ollama and streaming wait
mod = re.sub(
    r'(max_stream_duration_s\s*=\s*)(\d+\.?\d*)',
    r'\1 45.0 if ASSISTIFY_SAFE_MODE else \2',
    mod
)

# 4. Strict finally in call_llm_streaming to send aiResponseDone
# We find where it sends aiResponseDone and ensure it does it under all circumstances.

with open("assistify_rag_server.py", "w", encoding="utf-8") as f:
    f.write(mod)
