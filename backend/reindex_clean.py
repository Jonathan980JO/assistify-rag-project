#!/usr/bin/env python3
"""
Reindex Philosophy PDF - Clean approach without Chroma caching issues.
"""
import sys
import os
import shutil

# Delete ANY existing chroma_db_v3 first (this is CRITICAL)
backend_dir = os.path.dirname(os.path.abspath(__file__))
chroma_path = os.path.join(backend_dir, "chroma_db_v3")
if os.path.exists(chroma_path):
    print(f"Removing old chroma_db_v3 at {chroma_path}...")
    shutil.rmtree(chroma_path)
    print("✓ Removed")

# THEN import knowledge_base (which will create fresh client)
sys.path.insert(0, backend_dir)

from pathlib import Path
from PyPDF2 import PdfReader
from knowledge_base import chunk_and_add_document, get_or_create_collection

print("=" * 80)
print("REINDEX PHILOSOPHY PDF WITH FIXED ROLE ASSIGNMENT")
print("=" * 80)

pdf_path = Path(backend_dir) / "assets" / "37f3c4f4_Introduction_to_Philosophy-WEB_cszrKYp-compressed.pdf"

print(f"\n✓ PDF: {pdf_path.name} ({pdf_path.stat().st_size / 1024 / 1024:.1f} MB)")

# Load PDF
print(f"\nExtracting PDF text...")
reader = PdfReader(str(pdf_path))
num_pages = len(reader.pages)
print(f"  Pages: {num_pages}")

pdf_text = ""
for page_idx, page in enumerate(reader.pages):
    text = page.extract_text() or ""
    if text.strip():
        pdf_text += f"[PAGE_START:{page_idx+1}]{text}[PAGE_END:{page_idx+1}]\n\n"

print(f"  Extracted: {len(pdf_text)} chars")

# Reindex
print(f"\nReindexing with fixed metadata logic...")
result = chunk_and_add_document(
    doc_id="philosophy_pdf_main",
    text=pdf_text,
    metadata={"source": "Philosophy PDF", "version": "fixed_roles"},
    return_details=True
)

if isinstance(result, dict):
    print(f"  ✓ Chunks generated: {result.get('generated_chunks', '?')}")
    print(f"  ✓ Chunks indexed: {result.get('indexed_chunks', '?')}")
else:
    print(f"  ✓ Reindexed: {result} chunks")

# Diagnostics
print(f"\n" + "=" * 80)
print("METADATA DIAGNOSTICS")
print("=" * 80)

collection = get_or_create_collection()
total_count = collection.count()
print(f"\nTotal chunks: {total_count}")

all_data = collection.get(include=['metadatas'])
metadatas = all_data.get('metadatas', [])

role_counts = {}
chapter_counts = {}
section_counts = {}

for meta in metadatas:
    if not isinstance(meta, dict):
        continue
    
    role = meta.get('chunk_role', 'unknown')
    role_counts[role] = role_counts.get(role, 0) + 1
    
    chapter = meta.get('chapter', '').strip()
    if chapter:
        chapter_counts[chapter] = chapter_counts.get(chapter, 0) + 1
    
    section = meta.get('section', '').strip()
    if section:
        section_counts[section] = section_counts.get(section, 0) + 1

print(f"\nRole Distribution:")
for role, count in sorted(role_counts.items(), key=lambda x: -x[1]):
    pct = 100 * count / total_count if total_count > 0 else 0
    bar = "█" * int(pct / 2)
    print(f"  {role:20s}: {count:4d} ({pct:5.1f}%) {bar}")

print(f"\nTop 10 Chapters:")
for chapter, count in sorted(chapter_counts.items(), key=lambda x: -x[1])[:10]:
    print(f"  {chapter:20s}: {count:4d}")

print(f"\nTop 15 Sections:")
for section, count in sorted(section_counts.items(), key=lambda x: -x[1])[:15]:
    print(f"  {section:30s}: {count:4d}")

print(f"\n✓ Reindexing complete!")
