import sys
from pathlib import Path
import re

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

PDF = _ROOT / "backend" / "assets" / "02bdcc93_Cyper_Knowledge_test.pdf"

try:
    from PyPDF2 import PdfReader
except Exception:
    print('Install PyPDF2: pip install PyPDF2')
    raise

reader = PdfReader(str(PDF))
patterns = [
    r'^(Chapter\s+\d+[:.\s].*)$',
    r'^(CHAPTER\s+\d+[:.\s].*)$',
    r'^(Section\s+\d+(\.\d+)*[:.\s].*)$',
    r'^(Table of Contents)$',
    r'^(Abstract)$',
    r'^(References)$',
    r'^\d+\.\s+[A-Z].{0,120}$',
]
headings = []
for i,page in enumerate(reader.pages, start=1):
    try:
        txt = page.extract_text() or ''
    except Exception:
        txt = ''
    for line in txt.splitlines():
        s = line.strip()
        if not s:
            continue
        for pat in patterns:
            if re.match(pat, s, flags=re.IGNORECASE):
                headings.append({'page': i, 'title': s})

print(f"Found {len(headings)} candidate headings (listing up to 500):")
for h in headings[:500]:
    print(f"page {h['page']}: {h['title']}")

if not headings:
    print('No headings detected by heuristics')
else:
    print('\nDone')
