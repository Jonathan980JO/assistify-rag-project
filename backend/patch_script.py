import re
import os

with open('assistify_rag_server.py', 'r', encoding='utf-8') as f:
    text = f.read()

safe_mode_code = """import os

# ========== SAFE MODE & RESOURCE LIMITS ==========
ASSISTIFY_SAFE_MODE = os.environ.get('ASSISTIFY_SAFE_MODE', '1') == '1'
ASSISTIFY_DISABLE_TTS = os.environ.get('ASSISTIFY_DISABLE_TTS', '1' if ASSISTIFY_SAFE_MODE else '0') == '1'
ASSISTIFY_DISABLE_RERANKER = os.environ.get('ASSISTIFY_DISABLE_RERANKER', '1' if ASSISTIFY_SAFE_MODE else '0') == '1'
RAG_TOP_K_DEFAULT = 3 if ASSISTIFY_SAFE_MODE else 4
MAX_CONTEXT_CHARS = 1500 if ASSISTIFY_SAFE_MODE else 4000
"""

if 'ASSISTIFY_SAFE_MODE' not in text:
    text = text.replace('import os\n', safe_mode_code, 1)

# Now, we need to locate call_llm_streaming and wrap the TTS call or queue get so it doesn't block
# We also need to add strict timeouts over ollama post.

with open('assistify_rag_server.py', 'w', encoding='utf-8') as f:
    f.write(text)
