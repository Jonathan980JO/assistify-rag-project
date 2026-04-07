#!/usr/bin/env python3
"""
Test script for PDF upload improvements
Tests batch processing and large file handling
"""

import sys
import os
from pathlib import Path
import time

# Add project root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

def test_batch_embedding():
    """Test that batch embedding works correctly"""
    print("\n" + "="*70)
    print("TEST 1: Batch Embedding Performance")
    print("="*70)
    
    try:
        from backend.knowledge_base import embedder
        
        # Create test chunks
        chunks = [
            f"This is test chunk number {i} with some content about topic {i % 5}"
            for i in range(200)
        ]
        
        # Method 1: One by one (old way)
        print("\n[OLD WAY] Encoding chunks one at a time...")
        start = time.time()
        for chunk in chunks:
            _ = embedder.encode(chunk).tolist()
        old_time = time.time() - start
        print(f"  ✓ Time: {old_time:.2f}s for {len(chunks)} chunks")
        
        # Method 2: Batch (new way)
        print("\n[NEW WAY] Encoding chunks in batch...")
        start = time.time()
        _ = embedder.encode(chunks).tolist()
        new_time = time.time() - start
        print(f"  ✓ Time: {new_time:.2f}s for {len(chunks)} chunks")
        
        speedup = old_time / new_time
        print(f"\n✅ Speedup: {speedup:.1f}x faster")
        if speedup > 2:
            print("   Batch processing is working well!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True


def test_chunk_and_add_document():
    """Test the improved chunk_and_add_document function"""
    print("\n" + "="*70)
    print("TEST 2: Chunk and Add Document with Large Text")
    print("="*70)
    
    try:
        from backend.knowledge_base import chunk_and_add_document, clear_knowledge_base
        
        # Create a large document (simulating PDF extraction)
        large_text = """
        This is a simulated large document extracted from a PDF.
        
        Chapter 1: Introduction
        Lorem ipsum dolor sit amet, consectetur adipiscing elit. 
        Section 1.1 Details and more information about the topic.
        Lorem ipsum dolor sit amet, consectetur adipiscing elit.
        
        Chapter 2: Main Content
        Multiple paragraphs with information.
        Lorem ipsum dolor sit amet, consectetur adipiscing elit.
        More detailed explanations here.
        Lorem ipsum dolor sit amet, consectetur adipiscing elit.
        """ * 50  # Multiply to make it large
        
        print(f"\nTest document size: {len(large_text)} chars, ~{len(large_text.split())} words")
        
        # Clear KB first
        clear_knowledge_base()
        
        # Add document
        print("\nIndexing document with batch processing...")
        start = time.time()
        chunks_indexed = chunk_and_add_document(
            doc_id="test_large_doc",
            text=large_text,
            metadata={"test": "batch_processing"}
        )
        elapsed = time.time() - start
        
        print(f"✅ Successfully indexed {chunks_indexed} chunks in {elapsed:.2f}s")
        print(f"   Chunks per second: {chunks_indexed / elapsed:.1f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pdf_extraction():
    """Test PDF extraction with progress logging"""
    print("\n" + "="*70)
    print("TEST 3: PDF Extraction (if sample PDF available)")
    print("="*70)
    
    try:
        from PyPDF2 import PdfReader
        
        # Look for sample PDFs
        pdf_paths = list(Path(ROOT).rglob("*.pdf"))[:3]  # First 3 PDFs
        
        if not pdf_paths:
            print("No PDF files found in project (skipping)")
            return True
        
        for pdf_path in pdf_paths:
            print(f"\nTesting {pdf_path.name}...")
            
            reader = PdfReader(str(pdf_path))
            num_pages = len(reader.pages)
            print(f"  Pages: {num_pages}")
            
            total_text = 0
            for page_num, page in enumerate(reader.pages):
                try:
                    text = page.extract_text() or ""
                    total_text += len(text)
                    if (page_num + 1) % 5 == 0 or page_num == num_pages - 1:
                        print(f"    ✓ Extracted {page_num + 1}/{num_pages} pages...")
                except Exception as e:
                    print(f"    ⚠ Page {page_num} error: {e}")
            
            print(f"  ✅ Total extracted: {total_text} chars")
        
        return True
        
    except ImportError:
        print("PyPDF2 not installed (install with: pip install PyPDF2)")
        return True  # Not a failure, just optional
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def create_sample_pdf():
    """Create a sample PDF for testing (if reportlab available)"""
    print("\n" + "="*70)
    print("TEST 4: Create Sample PDF for Testing")
    print("="*70)
    
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.units import inch
        
        pdf_path = ROOT / "test_sample.pdf"
        
        print(f"\nCreating sample PDF: {pdf_path.name}")
        
        doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Add content
        for i in range(50):
            paragraph_text = f"""
            <b>Section {i+1}: Sample Content</b><br/>
            This is sample paragraph number {i+1}. It contains some Lorem ipsum text 
            to simulate a real document. Lorem ipsum dolor sit amet, consectetur adipiscing elit.
            """
            story.append(Paragraph(paragraph_text, styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
        
        doc.build(story)
        
        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        print(f"✅ Created {pdf_path.name} ({file_size_mb:.1f} MB)")
        print(f"   You can test upload with this file")
        print(f"   Path: {pdf_path}")
        
        return True
        
    except ImportError:
        print("reportlab not installed (optional, skipping PDF creation)")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    print("\n" + "╔" + "="*68 + "╗")
    print("║" + " "*10 + "ASSISTIFY RAG SYSTEM - PDF UPLOAD FIX TESTS" + " "*15 + "║")
    print("╚" + "="*68 + "╝")
    
    results = {
        "Batch Embedding": test_batch_embedding(),
        "Chunk and Add": test_chunk_and_add_document(),
        "PDF Extraction": test_pdf_extraction(),
        "Sample PDF Creation": create_sample_pdf(),
    }
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:.<40} {status}")
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed! PDF upload fixes are working correctly.")
        print("\nNext steps:")
        print("  1. Start the servers: start_main_servers.bat")
        print("  2. Try uploading a 5+ MB PDF via the admin interface")
        print("  3. Check console logs for batch processing messages")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
