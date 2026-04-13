import re

file_path = r'backend/assistify_rag_server.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# is_person_attribution_query = bool(re.match(r"^who\s+is\s+considered\s+the\s+father\s+of\b", q)) or q.startswith("who introduced")
content = re.sub(
    r'bool\(re\.match\(r"\^who\\s\+is\\s\+considered\\s\+the\\s\+father\\s\+of\\b",\s*(q_low|q_early|q)\)\)\s*or\s*(q_low|q_early|q)\.startswith\("who introduced"\)',
    r'\1.startswith("who introduced") or \1.startswith("who developed")',
    content
)

# Replace instances of father of in regexes:
content = content.replace(r'father of|', '')
content = content.replace(r'|father of', '')
content = content.replace(r'father\s+of|', '')
content = content.replace(r'|father\s+of', '')
content = content.replace(r'|known\s+as\s+the\s+father\s+of', '')
content = content.replace(r' father of ', ' founder of ')
content = content.replace(r'"father",', '')

# Remove specific logic blocks
# if "father of" in q: return f"{mapped_name} is considered the father of {concept_title}."
content = re.sub(
    r'\s+if "father of" in q:\s+return f"\{mapped_name\} is considered the father of \{concept_title\}."',
    '',
    content,
    flags=re.MULTILINE
)

# Remove the query_has_father section logic
content = re.sub(
    r'\s+query_has_father = "father" in q_low',
    '',
    content
)
content = re.sub(
    r'\s+if query_has_father and \(" father " in low or " father of " in low\):.*?return ".*?"',
    '',
    content,
    flags=re.DOTALL
)

# Remove specific father_re logic around line 7421
content = re.sub(
    r'\s+is_father_query = False.*?flags=re.IGNORECASE\)',
    '',
    content,
    flags=re.DOTALL
)

content = re.sub(r'\s+if is_father_query:.*?(?=\s+for fp in father_patterns:)', '', content, flags=re.DOTALL)
content = re.sub(r'\s+for fp in father_patterns:.*?(?=\s+for m in father_re.finditer\(s\):)', '', content, flags=re.DOTALL)
content = re.sub(r'\s+for m in father_re.finditer\(s\):.*?(?=\s+has_founder_signal)', '', content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Phase 3 cleanup done!')
