import re

with open('assistify_rag_server.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix all invalid indents of this specific injected line
text = re.sub(
    r'(async for chunk in resp\.content\.iter_chunked\(4096\):)\n\s+if globals\(\)\.get\("ASSISTIFY_DISABLE_TTS", False\): break',
    r'\1\n                        if globals().get("ASSISTIFY_DISABLE_TTS", False): break',
    text
)

with open('assistify_rag_server.py', 'w', encoding='utf-8') as f:
    f.write(text)
