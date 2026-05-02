"""Fix the remaining 2 failed patches."""
import re

TARGET = r"g:\Grad_Project\assistify-rag-project-main\backend\assistify_rag_server.py"

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

# Fix 1: bullet_num_re in _extract_list_from_context
# Old: [A-Z]\.  →  New: [A-Za-z][.)]
old1 = (
    "    # MP-C6: also accept single uppercase letter (A./B./...) line starts so the\n"
    "    # exploded inline-enumeration items are matched as bullets.\n"
    "    bullet_num_re = re.compile(r\"^\\s*(?:[-\u2022*\ufffd]|\\d+[.)]|[A-Z]\\.)\\ s*(.+)$\")"
)
# Try matching without the specific comment
marker = r'bullet_num_re = re.compile(r"^\s*(?:[-\u2022*\ufffd]|\d+[.)]|[A-Z]\\.)\s*(.+)$")'
# Use the actual bytes
search1 = 'bullet_num_re = re.compile(r"^\\s*(?:[-\u2022*\ufffd]|\\d+[.)]|[A-Z]\\.)\\ s*(.+)$")'

# Let's find the pattern directly
idx = src.find('[A-Z]\\.')
print(f"Found [A-Z]\\. at index: {idx}")
if idx >= 0:
    context = src[idx-50:idx+50]
    print(f"Context: {repr(context)}")

# Try specific search
BULLET_PATTERN_OLD = (
    '    bullet_num_re = re.compile(r"^\\s*(?:[-\u2022*\ufffd]|\\d+[.)]|[A-Z]\\.)\\s*(.+)$")\n'
    '    caption_re = re.compile(r"^\\s*(?:figure|fig\\.?|table)\\b", flags=re.IGNORECASE)'
)
BULLET_PATTERN_NEW = (
    '    bullet_num_re = re.compile(r"^\\s*(?:[-\u2022*\ufffd]|\\d+[.)]|[A-Za-z][.)])\\s*(.+)$")\n'
    '    caption_re = re.compile(r"^\\s*(?:figure|fig\\.?|table)\\b", flags=re.IGNORECASE)'
)
count1 = src.count(BULLET_PATTERN_OLD)
print(f"bullet_num_re pattern count: {count1}")
if count1 == 1:
    src = src.replace(BULLET_PATTERN_OLD, BULLET_PATTERN_NEW)
    print("  Applied bullet_num_re fix")
else:
    print("  SKIPPED (not found or multiple matches)")

# Fix 2: _normalize_item — also strip lowercase alpha prefixes
NORMALIZE_OLD = (
    '        item = re.sub(r"^\\s*(?:[-\u2022*\ufffd]|\\d+[.)]|[A-Z]\\.)\\s*", "", item)\n'
    '        item = re.sub(r"^\\s*\\d+\\s*:\\s*", "", item)'
)
NORMALIZE_NEW = (
    '        item = re.sub(r"^\\s*(?:[-\u2022*\ufffd]|\\d+[.)]|[A-Za-z][.)])\\s*", "", item)\n'
    '        item = re.sub(r"^\\s*\\d+\\s*:\\s*", "", item)'
)
count2 = src.count(NORMALIZE_OLD)
print(f"_normalize_item pattern count: {count2}")
if count2 == 1:
    src = src.replace(NORMALIZE_OLD, NORMALIZE_NEW)
    print("  Applied _normalize_item fix")
else:
    print("  SKIPPED (not found or multiple matches)")
    # Debug: find what's there
    idx2 = src.find('[A-Z]\\.')
    while idx2 >= 0:
        ctx = src[max(0,idx2-80):idx2+80]
        print(f"  Occurrence at {idx2}: {repr(ctx)}")
        idx2 = src.find('[A-Z]\\.', idx2+1)

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(src)
print("Done.")
