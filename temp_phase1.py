import re

file_path = r'backend/assistify_rag_server.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove _extract_lesson_lines_from_docs to _docs_look_lesson_structured
content = re.sub(
    r'\n\ndef _extract_lesson_lines_from_docs.*?def _extract_named_psychology_list',
    '\n\ndef _extract_fallback_list',
    content,
    flags=re.DOTALL
)

# 2. Rename _extract_named_psychology_list
content = content.replace('def _extract_named_psychology_list', 'def _extract_fallback_list')

# 3. Clean OCR noise functions
content = content.replace(
    'paragraph = re.split(r"\\b(Before Conditioning|Copyright|Introduction to Psychology)\\b", paragraph, maxsplit=1, flags=re.IGNORECASE)[0]',
    'paragraph = re.split(r"\\b(Copyright|Table of Contents)\\b", paragraph, maxsplit=1, flags=re.IGNORECASE)[0]'
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Phase 1 cleanup done!')
