import re

file_path = r'backend/assistify_rag_server.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Remove operant conditioning hardcoded answer
content = re.sub(
    r'\s+elif right\.lower\(\) == "operant conditioning":\s+right_sent = "Operant conditioning forms an association between a behavior and its consequences, which strengthens or weakens that behavior\."',
    '',
    content
)

# Remove "psychology", "psychological" from sets/lists
content = content.replace('"psychology", "psychological", ', '')
content = content.replace('"Psychology", "Lesson", ', '')

# Remove in psychology replacement
content = re.sub(
    r'\s+out = re\.sub\(r"\\bin\\s\+psychology\\s\*\$", "", out, flags=re\.IGNORECASE\)',
    '',
    content
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Phase 4 cleanup done!')
