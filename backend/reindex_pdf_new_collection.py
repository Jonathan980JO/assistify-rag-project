import os
import sys
import time
import uuid
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('reindex')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Config
PDF_FILENAME = "02bdcc93_Cyper_Knowledge_test.pdf"
SRC_DIR = Path(__file__).resolve().parents[1] / 'backend' / 'assets'
PDF_PATH = SRC_DIR / PDF_FILENAME
NEW_CHROMA_DIR = Path(__file__).resolve().parents[1] / 'backend' / 'chroma_db_v3'
NEW_COLLECTION_NAME = f"support_docs_v3_{int(time.time())}"
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'intfloat/multilingual-e5-base')

# OCR tools
try:
    import pytesseract
    from pdf2image import convert_from_path
except Exception:
    pytesseract = None
    convert_from_path = None

try:
    from PyPDF2 import PdfReader
except Exception:
    logger.error('PyPDF2 not installed. Install with pip install PyPDF2')
    raise

try:
    import chromadb
    from chromadb.config import Settings
except Exception:
    logger.error('chromadb not installed. Install with pip install chromadb')
    raise

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    logger.error('sentence-transformers missing. Install pip install sentence-transformers')
    raise

# Device
device = 'cpu'
try:
    import torch
    if torch.cuda.is_available():
        device = 'cuda'
except Exception:
    device = 'cpu'

EMBED_BATCH = 512 if device == 'cuda' else 128
UPSERT_BATCH = 1000 if device == 'cuda' else 100

# Read PDF pages, detect scanned pages and OCR when needed

def extract_pages(pdf_path: Path):
    reader = PdfReader(str(pdf_path))
    pages = []
    ocr_pages = []
    extract_times = {}
    total_pages = len(reader.pages)
    logger.info(f"PDF pages detected: {total_pages}")
    # Use convert_from_path once for OCR pages when needed to optimize
    ocr_image_cache = {}

    for i, p in enumerate(reader.pages, start=1):
        t0 = time.time()
        try:
            txt = p.extract_text() or ""
        except Exception as e:
            logger.warning(f"Page {i}: PyPDF2.extract_text() failed: {e}")
            txt = ""
        t1 = time.time()
        extract_times[i] = t1 - t0
        # Heuristic: scanned if text length small
        if len(txt.strip()) < 50:
            logger.info(f"Page {i} detected as scanned — switching to OCR")
            ocr_pages.append(i)
            if pytesseract and convert_from_path:
                try:
                    imgs = convert_from_path(str(pdf_path), first_page=i, last_page=i)
                    if imgs:
                        ocr_t0 = time.time()
                        ocr_text = pytesseract.image_to_string(imgs[0])
                        ocr_t1 = time.time()
                        txt = ocr_text
                        extract_times[i] = (t1 - t0) + (ocr_t1 - ocr_t0)
                except Exception as e:
                    logger.error(f"OCR failed for page {i}: {e}")
            else:
                logger.warning("OCR tools not available (pytesseract/pdf2image)")
        pages.append({'page': i, 'text': txt})
    return pages, ocr_pages, extract_times

# Simple structure detection
import re

# Strict match for primary chapter headings.
section_pattern = re.compile(r"^\s*(Chapter\s+\d+|Section\s+\d+(?:\.\d+)*)\b", re.IGNORECASE)
toc_line_pattern = re.compile(r"(\.{3,}|\bContents\b)", re.IGNORECASE)

def detect_sections(pages: List[Dict[str, Any]]):
    # This will now process the pages inplace to update sections
    current_section = "Front Matter"
    in_toc = False
    sections_log = []
    
    for p in pages:
        lines = p['text'].splitlines()
        
        # Determine if this page is likely a TOC page
        toc_indicators = 0
        for line in lines:
            if re.search(r"\.{3,}\s*\d+", line) or re.search(r"^\s*Contents\s*$", line, re.IGNORECASE):
                toc_indicators += 1
                
        if toc_indicators >= 2:
            in_toc = True
        elif in_toc and toc_indicators == 0 and p['page'] > 15:
            in_toc = False
            
        page_section = current_section
        if in_toc:
            page_section = "Table of Contents"
            
        for line in lines:
            clean_line = line.strip()
            if not in_toc:
                # Match "Chapter X" even if preceeded by page numbers or followed by a distinct symbol
                match = re.search(r"^(?:\d+\s+)?(Chapter\s+\d+)", clean_line, re.IGNORECASE)
                if match and not toc_line_pattern.search(clean_line):
                    if len(clean_line) < 100:
                        raw_sect = match.group(1).title()
                        if raw_sect != current_section:
                            current_section = raw_sect
                            page_section = current_section
                            sections_log.append({'page': p['page'], 'title': current_section})
        
        # Attach the resolved section to the page dictionary for chunking
        p['resolved_section'] = page_section
        
    return sections_log

# Chunking logic (paragraph-first, replicate knowledge_base behavior)

def chunk_pages(pages: List[Dict[str, Any]], file_name: str, document_type: str):
    chunks = []
    
    TARGET_MIN_WORDS = 300
    TARGET_MAX_WORDS = 500
    TARGET_WORDS = 420
    OVERLAP_WORDS = 70
    heading_hint_pattern = re.compile(r"(?i)^(?:chapter|section|lesson|unit)\s+[0-9A-Za-z.-]+\b")

    def _normalize_para(raw: str) -> str:
        return re.sub(r'\s+', ' ', (raw or '').strip()).strip()

    def _is_heading(text_block: str) -> bool:
        line = (text_block or '').strip()
        if not line:
            return False
        words = line.split()
        if len(words) > 14:
            return False
        if heading_hint_pattern.search(line):
            return True
        if line.endswith(('.', '?', '؟', '!', ',', '،', ':', ';')):
            return False
        return sum(1 for w in words if w[:1].isupper()) >= max(1, len(words) // 2)
    
    all_paragraphs = []
    current_heading = ""
    for p in pages:
        page_num = p['page']
        text = p['text'].replace('\r\n', '\n').replace('\r', '\n')
        paragraphs = re.split(r'\n{2,}', text)
        page_section = p.get('resolved_section', 'Unknown')
        
        for para in paragraphs:
            para = _normalize_para(para)
            if len(para) < 20:
                continue
            if _is_heading(para):
                current_heading = para
                continue
            if current_heading and current_heading.lower() not in para.lower():
                para = f"{current_heading}\n{para}"
            all_paragraphs.append({
                'text': para,
                'page': page_num,
                'section': page_section
            })
            
    current_chunk_words = []
    current_chunk_page = 1
    current_chunk_section = "Unknown"
    
    def emit_chunk(words, page, section):
        return {
            'chunk_id': str(uuid.uuid4()),
            'text': " ".join(words).strip(),
            'page': page,
            'section': section,
            'document_type': document_type,
            'source': file_name,
            'timestamp': time.time()
        }
    
    for pa in all_paragraphs:
        words = pa['text'].split()
        if not words: continue
        
        if not current_chunk_words:
            current_chunk_page = pa['page']
            current_chunk_section = pa['section']
            # Prepend section metadata context
            header_text = f"[{pa['section']}] "
            current_chunk_words.extend(header_text.split())
            
        if len(current_chunk_words) + len(words) > TARGET_MAX_WORDS and len(current_chunk_words) >= TARGET_MIN_WORDS:
            chunks.append(emit_chunk(current_chunk_words, current_chunk_page, current_chunk_section))
            current_chunk_words = current_chunk_words[-OVERLAP_WORDS:]
            current_chunk_page = pa['page']
            current_chunk_section = pa['section']
            header_text = f"[{pa['section']}] "
            current_chunk_words = header_text.split() + current_chunk_words

        current_chunk_words.extend(words)
        
        if len(current_chunk_words) >= TARGET_WORDS:
            chunks.append(emit_chunk(current_chunk_words, current_chunk_page, current_chunk_section))
            # Keep overlap words
            current_chunk_words = current_chunk_words[-OVERLAP_WORDS:]
            
            # If the overlapping part is mostly from the middle of a paragraph, 
            # we don't know the exact page/section of those specific words easily, 
            # but usually they belong to the current paragraph `pa`
            current_chunk_page = pa['page']
            current_chunk_section = pa['section']
            header_text = f"[{pa['section']}] "
            overlap_prefix = header_text.split()
            # Ensure header is at the start of the overlap chunk too
            current_chunk_words = overlap_prefix + current_chunk_words
            
    # Add remaining if it's substantial (more than just the overlap/header)
    if len(current_chunk_words) >= max(80, TARGET_MIN_WORDS // 3): 
        chunks.append(emit_chunk(current_chunk_words, current_chunk_page, current_chunk_section))
        
    return chunks


def _e5_passage(text: str) -> str:
    cleaned = re.sub(r'\s+', ' ', (text or '').strip())
    return f"passage: {cleaned}" if cleaned else "passage:"


def _e5_query(text: str) -> str:
    cleaned = re.sub(r'\s+', ' ', (text or '').strip())
    return f"query: {cleaned}" if cleaned else "query:"

# Main

def main():
    if not PDF_PATH.exists():
        logger.error(f"PDF not found: {PDF_PATH}")
        return
    logger.info(f"Reindexing PDF: {PDF_PATH}")

    pages, ocr_pages, times = extract_pages(PDF_PATH)
    logger.info(f"Pages extracted: {len(pages)}; OCR pages: {len(ocr_pages)} -> {ocr_pages}")

    # detect sections
    sections = detect_sections(pages)
    logger.info(f"Detected {len(sections)} candidate sections/headings (sample up to 50)")
    for s in sections[:50]:
        logger.info(f"  page {s['page']}: {s['title']}")

    # simple doc type classification
    sample_text = '\n'.join([p['text'] for p in pages[:5]])
    doc_type = 'Unknown'
    if 'abstract' in sample_text.lower() and 'references' in sample_text.lower():
        doc_type = 'Research paper'
    elif 'chapter' in sample_text.lower() or 'table of contents' in sample_text.lower():
        doc_type = 'Book'

    # chunk
    chunks = chunk_pages(pages, PDF_FILENAME, doc_type)
    logger.info(f"Total chunks created: {len(chunks)}")

    # Initialize Chroma client on new folder
    NEW_CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Creating new Chroma DB at: {NEW_CHROMA_DIR}")
    client = chromadb.PersistentClient(path=str(NEW_CHROMA_DIR))
    collection = client.get_or_create_collection(name=NEW_COLLECTION_NAME)
    logger.info(f"Created collection: {NEW_COLLECTION_NAME}")

    # load embedder
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL} on {device}")
    embedder = SentenceTransformer(EMBEDDING_MODEL, device=device)

    # batch embed and upsert
    docs = [c['text'] for c in chunks]
    embedding_docs = [_e5_passage(d) for d in docs]
    metas = [{k: v for k, v in c.items() if k != 'text'} for c in chunks]
    ids = [c['chunk_id'] for c in chunks]

    success = 0
    for i in range(0, len(docs), UPSERT_BATCH):
        batch_docs = docs[i:i+UPSERT_BATCH]
        batch_embedding_docs = embedding_docs[i:i+UPSERT_BATCH]
        batch_ids = ids[i:i+UPSERT_BATCH]
        batch_metas = metas[i:i+UPSERT_BATCH]
        # embed in sub-batches to limit memory
        embeddings = []
        for j in range(0, len(batch_embedding_docs), EMBED_BATCH):
            sub = batch_embedding_docs[j:j+EMBED_BATCH]
            emb = embedder.encode(sub, batch_size=len(sub), show_progress_bar=False)
            embeddings.append(emb)
        import numpy as _np
        batch_embeddings = _np.vstack(embeddings).tolist()
        # upsert
        try:
            collection.upsert(ids=batch_ids, documents=batch_docs, embeddings=batch_embeddings, metadatas=batch_metas)
            success += len(batch_docs)
            logger.info(f"Upserted chunks {i}-{i+len(batch_docs)-1}")
        except Exception as e:
            logger.error(f"Upsert failed for batch {i}-{i+len(batch_docs)-1}: {e}")

    logger.info(f"Indexing complete: {success}/{len(docs)} chunks added to {NEW_COLLECTION_NAME}")

    # Post-index checks
    # 1) first 10 chunks
    try:
        res = collection.get(include=["documents", "metadatas"], limit=10)
        docs_out = res.get('documents', [])
        metas_out = res.get('metadatas', [])
        logger.info("First 10 chunks and metadata:")
        for idx, (d,m) in enumerate(zip(docs_out, metas_out), start=1):
            print('\n--- CHUNK %d ---' % idx)
            print('metadata:', json.dumps(m, ensure_ascii=False))
            print('text:\n', d[:2000])
    except Exception as e:
        logger.error(f"Failed to get first 10 chunks: {e}")

    # 2) list detected section titles
    print('\n--- Detected Sections / Headings (sample up to 200) ---')
    for s in sections[:200]:
        print(f"page {s['page']}: {s['title']}")

    # 3) run retrieval for query
    q = "Summarize Chapter 6 in 3 bullet points"
    try:
        q_emb = embedder.encode([_e5_query(q)], show_progress_bar=False)[0].tolist()
        query_res = collection.query(query_embeddings=[q_emb], n_results=10, include=["documents", "metadatas", "distances"])
        docs_q = query_res.get('documents', [[]])[0]
        metas_q = query_res.get('metadatas', [[]])[0]
        dists_q = query_res.get('distances', [[]])[0]
        print('\n--- Retrieval Results for query:', q, '---')
        for i, (doc, meta, dist) in enumerate(zip(docs_q, metas_q, dists_q), start=1):
            sim = 1.0 - dist if dist is not None else None
            print(f"\nRANK {i} | similarity: {sim}")
            print('metadata:', json.dumps(meta, ensure_ascii=False))
            print('text:\n', doc[:2000])
    except Exception as e:
        logger.error(f"Query failed: {e}")

    # confirm query works
    try:
        _ = collection.count()
        logger.info("Collection count() OK — new collection is queryable")
    except Exception as e:
        logger.error(f"collection.count() failed: {e}")

if __name__ == '__main__':
    main()
