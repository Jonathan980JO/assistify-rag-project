
import os
from backend.assistify_rag_server import ASSETS_DIR
from pathlib import Path
try:
    import pdftotext
except ImportError:
    import PyPDF2

p = ASSETS_DIR / 'f57fa92f_Principles_of_Management.pdf'
text = ""
if 'pdftotext' in globals():
    with open(p, 'rb') as f:
        pdf = pdftotext.PDF(f)
        text = '\n'.join(pdf)
else:
    from PyPDF2 import PdfReader
    reader = PdfReader(p)
    text = "\n".join([page.extract_text() for page in reader.pages])

# Search for the combination of 6 keywords
keywords = ["Money", "Machin", "Material", "Manpower", "Market", "Method"]
text_lower = text.lower()

current_pos = 0
while True:
    pos = text_lower.find("money", current_pos)
    if pos == -1:
        break
    
    # Check if others are nearby (within 500 chars)
    window = text_lower[pos:pos+500]
    matches = sum(1 for k in keywords if k.lower() in window)
    if matches >= 4:
        print(f"FOUND CLUSTER at {pos} (matches={matches})")
        print(text[max(0, pos-100):pos+600])
        break
    current_pos = pos + 1
else:
    print("NO CLUSTER FOUND")
