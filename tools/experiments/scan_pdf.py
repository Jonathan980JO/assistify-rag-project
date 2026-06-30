
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

target = "Manpower"
pos = text.lower().find(target.lower())
if pos != -1:
    print(f"FOUND 'Manpower' at {pos}")
    print(text[max(0, pos-200):pos+1200])
else:
    print("NOT FOUND 'Manpower'")
