#!/usr/bin/env python3
"""
Reindex Philosophy PDF with FRESH ChromaDB and FIXED role assignment logic.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from pathlib import Path
from PyPDF2 import PdfReader
import shutil
import chromadb

print("=" * 80)
print("REINDEX PHILOSOPHY PDF - REBUILDING CHROMADB")
print("=" * 80)

# Paths
pdf_path = Path(__file__).parent / "assets" / "37f3c4f4_Introduction_to_Philosophy-WEB_cszrKYp-compressed.pdf"
chroma_db_path = Path(__file__).parent / "chroma_db_v3"

print(f"\n[1/5] Checking PDF: {pdf_path}")
if not pdf_path.exists():
    print(f"❌ ERROR: PDF not found at {pdf_path}")
    sys.exit(1)
print(f"✓ PDF exists ({pdf_path.stat().st_size / 1024 / 1024:.1f} MB)")

# Delete and rebuild ChromaDB
print(f"\n[2/5] Rebuilding ChromaDB (deleting old corrupted database)...")
if chroma_db_path.exists():
    print(f"  Deleting {chroma_db_path}...")
    try:
        shutil.rmtree(str(chroma_db_path))
        print(f"  ✓ Old database deleted")
    except Exception as e:
        print(f"  ⚠ Warning: Could not delete old database: {e}")
        print(f"  Attempting to continue anyway...")
else:
    print(f"  No old database found (starting fresh)")

# Create fresh ChromaDB client
print(f"  Creating fresh ChromaDB client...")
try:
    client = chromadb.PersistentClient(path=str(chroma_db_path))
    print(f"  ✓ Fresh ChromaDB initialized")
except Exception as e:
    print(f"❌ Error creating ChromaDB: {e}")
    sys.exit(1)

# Load and extract text from PDF
print(f"\n[3/5] Loading and extracting PDF text...")
try:
    reader = PdfReader(str(pdf_path))
    num_pages = len(reader.pages)
    print(f"  PDF has {num_pages} pages")
    
    pdf_text = ""
    for page_idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        # Add page marker so chunker can extract page numbers
        if text.strip():
            pdf_text += f"[PAGE_START:{page_idx+1}]{text}[PAGE_END:{page_idx+1}]\n\n"
    
    if not pdf_text.strip():
        print("❌ ERROR: Could not extract text from PDF")
        sys.exit(1)
    
    print(f"  Extracted {len(pdf_text)} characters")
    print(f"  Sample (first 200 chars): {pdf_text[:200]}")
except Exception as e:
    print(f"❌ Error loading PDF: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Now import knowledge_base AFTER creating fresh ChromaDB
print(f"\n[4/5] Reindexing with fixed metadata logic...")
try:
    from knowledge_base import chunk_and_add_document, get_or_create_collection
    
    metadata = {
        "source": "Philosophy PDF",
        "doc_type": "textbook",
        "version": "fixed_roles",
    }
    result = chunk_and_add_document(
        doc_id="philosophy_pdf_main",
        text=pdf_text,
        metadata=metadata,
        return_details=True
    )
     
    if isinstance(result, dict):
        print(f"  ✓ Reindexing complete!")
        print(f"    Chunks generated: {result.get('generated_chunks', '?')}")
        print(f"    Chunks indexed: {result.get('indexed_chunks', '?')}")
        print(f"    Collection: {result.get('collection', '?')}")
        if result.get('reason'):
            print(f"    Note: {result['reason']}")
    else:
        print(f"  ✓ Reindexing complete! ({result} chunks)")
        
except Exception as e:
    print(f"❌ Error during reindexing: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Run diagnostics
print(f"\n" + "=" * 80)
print("METADATA DIAGNOSTICS")
print("=" * 80)

try:
    collection = get_or_create_collection()
    if not collection:
        print("❌ No active collection")
        sys.exit(1)
    
    total_count = collection.count()
    print(f"\n✓ Total chunks: {total_count}")
    
    # Fetch all chunks to analyze metadata
    print(f"  Fetching all {total_count} chunks for analysis...")
    all_data = collection.get(include=['metadatas'])
    
    metadatas = all_data.get('metadatas', [])
    
    # Analyze role distribution
    role_counts = {}
    chapter_counts = {}
    section_counts = {}
    
    for meta in metadatas:
        if not isinstance(meta, dict):
            continue
        
        # Count roles
        role = meta.get('chunk_role', 'unknown')
        role_counts[role] = role_counts.get(role, 0) + 1
        
        # Count chapters
        chapter = meta.get('chapter', '').strip()
        if chapter:
            chapter_counts[chapter] = chapter_counts.get(chapter, 0) + 1
        
        # Count sections
        section = meta.get('section', '').strip()
        if section:
            section_counts[section] = section_counts.get(section, 0) + 1
    
    print(f"\nRole Distribution (should be mostly 'content'):")
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
    
    print(f"\n" + "=" * 80)
    
except Exception as e:
    print(f"❌ Error running diagnostics: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("✓ Reindexing and diagnostics complete!")
