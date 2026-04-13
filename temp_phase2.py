import re

file_path = r'backend/assistify_rag_server.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Remove rescue docs assignments for table of contents lesson psychology entirely
content = re.sub(
    r'\s+if rescue_family in \{"toc_structure", "lesson_lookup", "sequence_lookup"\}:\s+relevant_docs = _search_fast_minimal\("table of contents lesson psychology", top_k=10\) or \[\]',
    '',
    content,
    flags=re.MULTILINE
)

content = re.sub(
    r'\s+elif rescue_family == "list_entity":\s+relevant_docs = _search_fast_minimal\(text \+ " psychology", top_k=10\) or \[\]',
    '',
    content,
    flags=re.MULTILINE
)

# Remove lesson_lookup, sequence_lookup, 	oc_structure from all sets
content = re.sub(r', "lesson_lookup", "sequence_lookup"', '', content)
content = re.sub(r'"toc_structure", ', '', content)
content = re.sub(r'"lesson_lookup": "overview_chapter_compare",', '', content)

# Remove _docs_looks_lesson_structured call and format mismatch guard
content = re.sub(
    r'\s+lesson_structured = _docs_look_lesson_structured.*?items_count=0\)',
    '',
    content,
    flags=re.DOTALL
)

# Remove lesson_lookup mode blocks
content = re.sub(
    r'\s+if family == "lesson_lookup":.*?items_count=0\)',
    '',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'\s+if family == "sequence_lookup":.*?items_count=0\)',
    '',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'\s+if family == "toc_structure":.*?items_count=0\)',
    '',
    content,
    flags=re.DOTALL
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Phase 2 cleanup done!')
