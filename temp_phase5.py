import re

file_path = r'backend/assistify_rag_server.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('"health", "introduction", "lesson", ', '"introduction", ')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
