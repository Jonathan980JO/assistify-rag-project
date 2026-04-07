# Lightweight test harness for the modified _generic_clean_items
import re
from pprint import pprint

SRC = r"g:\Grad_Project\assistify-rag-project-main\backend\assistify_rag_server.py"
with open(SRC, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start = None
indent = None
for i, l in enumerate(lines):
    if l.lstrip().startswith('def _generic_clean_items'):
        start = i
        indent = len(l) - len(l.lstrip())
        break
if start is None:
    raise SystemExit('Could not find _generic_clean_items in source')

end = len(lines)
for j in range(start + 1, len(lines)):
    # Prefer to end at the first `return cleaned` inside the function (safer)
    if lines[j].strip().startswith('return cleaned'):
        end = j + 1
        break
# Fallback: if not found, fall back to next sibling def at same indent
if end == len(lines):
    for j in range(start + 1, len(lines)):
        lj = lines[j]
        if lj.lstrip().startswith('def ') and (len(lj) - len(lj.lstrip())) == indent:
            end = j
            break

# Normalize indentation to module-level for exec
func_block = ''.join([ln[indent:] if ln.startswith(' ' * indent) else ln for ln in lines[start:end]])
# Execute function in isolated namespace (provide 're' from stdlib)
import re as _re
ns = {'re': _re}
exec(func_block, ns)
if '_generic_clean_items' not in ns:
    raise SystemExit('Function extraction failed')

# Ensure we didn't hardcode 'markets' inside the function block
contains_markets = bool(re.search(r"\bmarkets\b", func_block, flags=re.IGNORECASE))

# Test input (extracted items BEFORE cleaning)
extracted_before = [
    'people',
    'money',
    'machines',
    'materials',
    'methods',
    'expanding into new markets'
]
print('Extracted BEFORE cleaning:')
print(' -', '\n - '.join(extracted_before))

cleaned = ns['_generic_clean_items'](extracted_before, max_words=4)
print('\nCleaned AFTER _generic_clean_items:')
for it in cleaned:
    print(' -', it)

import difflib
print('\nDebug: closest match for "markets" against prior items ->', difflib.get_close_matches('markets', extracted_before[:-1], n=1, cutoff=0.82))

print('\nContains "markets" in cleaned items? ->', any(re.search(r"\bmarkets\b", it, flags=re.IGNORECASE) for it in cleaned))
print('Function block contains literal "markets"? ->', contains_markets)
