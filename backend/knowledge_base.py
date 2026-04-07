import os
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY_IMPL'] = 'none'

import re
import torch
import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path
from typing import Optional

# If posthog is present but incompatible, stub capture to avoid runtime errors
try:
    import posthog
    def _safe_capture(*a, **k):
        try:
            return posthog.capture(*a, **k)
        except Exception:
            return None
    posthog.capture = _safe_capture
except Exception:
    import sys
    class _PosthogStub:
        @staticmethod
        def capture(*a, **k):
            return None
        @staticmethod
        def identify(*a, **k):
            return None
    sys.modules['posthog'] = _PosthogStub()
try:
    # Prefer project-level config if available
    from config import CHROMA_DB_PATH, EMBEDDING_MODEL
except Exception:
    # Fallbacks for cases where config isn't importable
    CHROMA_DB_PATH = Path(__file__).resolve().parent / "chroma_db_v3"
    EMBEDDING_MODEL = 'intfloat/multilingual-e5-base'

# Wait, if config is imported, CHROMA_DB_PATH might still be the old one. We should override it for now.
CHROMA_DB_PATH = Path(__file__).resolve().parent / "chroma_db_v3"

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KnowledgeBase")

# Initialize ChromaDB (persistent storage)
client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))

# Embedding device: Use GPU for fast embedding during upload/indexing.
# Falls back to CPU if CUDA is unavailable.
try:
    if torch.cuda.is_available():
        device = "cuda"
        gpu_name = torch.cuda.get_device_name(0)
        logger.info(f"✓ Embedding device: CUDA ({gpu_name})")
    else:
        device = "cpu"
        logger.info("✓ Embedding device: CPU (CUDA not available)")
except Exception as e:
    logger.error(f"Fallback to CPU due to exception: {e}", exc_info=True)
    device = 'cpu'

# Initialize embedding model with GPU support
embedder = SentenceTransformer(EMBEDDING_MODEL, device=device)


def _e5_passage(text: str) -> str:
    cleaned = " ".join((text or "").split())
    return f"passage: {cleaned}" if cleaned else "passage:"


def _e5_query(text: str) -> str:
    cleaned = " ".join((text or "").split())
    return f"query: {cleaned}" if cleaned else "query:"

def get_or_create_collection(allow_empty: bool = False):
    """Get collection or create if doesn't exist.
    
    Args:
        allow_empty: If True, return a collection even if it has 0 documents.
                     Use this after delete_all_documents() to ensure the same
                     collection is reused for re-indexing.
    """
    try:
        expected_dim = int(embedder.get_sentence_embedding_dimension())
        # Default collection name (force populated collection usage)
        collection_name = "support_docs_v3_latest"
        preferred = os.environ.get("ASSISTIFY_COLLECTION_NAME", "").strip() or collection_name
        if preferred:
            try:
                col = client.get_or_create_collection(name=preferred)
                probe_embedding = [0.0] * expected_dim
                try:
                    col.query(query_embeddings=[probe_embedding], n_results=1, include=["distances"])
                except Exception as probe_err:
                    msg = str(probe_err).lower()
                    if "dimensionality" in msg or "attribute 'dimensionality'" in msg:
                        logger.warning(f"Preferred collection '{preferred}' incompatible/corrupt; recreating: {probe_err}")
                        try:
                            client.delete_collection(name=preferred)
                        except Exception:
                            pass
                        col = client.get_or_create_collection(name=preferred, metadata={"hnsw:space": "cosine"})
                return col
            except Exception as pref_err:
                logger.warning(f"Preferred collection '{preferred}' unavailable: {pref_err}")

        # Dynamically load the newest v3 collection
        collections = client.list_collections()
        if collections:
            candidate_names = sorted([c.name for c in collections if "support_docs" in c.name], reverse=True)
            for col_name in candidate_names:
                try:
                    col = client.get_collection(name=col_name)
                    # Prefer collections that actually contain chunks.
                    # If allow_empty is set (after a delete_all), accept the
                    # first matching collection even if empty — the caller is
                    # about to re-fill it.
                    if col.count() > 0 or allow_empty:
                        probe_embedding = [0.0] * expected_dim
                        try:
                            col.query(query_embeddings=[probe_embedding], n_results=1, include=["distances"])
                        except Exception:
                            # Query might fail on a just-emptied collection; that's OK
                            if not allow_empty:
                                raise
                        return col
                    # otherwise skip empty collections and try the next candidate
                    continue
                except Exception as probe_err:
                    logger.warning(f"Skipping broken collection '{col_name}': {probe_err}")
                    continue
            
        fallback_name = preferred
        collection = client.get_or_create_collection(name=fallback_name)
        return collection
    except Exception as e:
        logger.error(f"Error getting collection: {e}")
        return None

def add_document(doc_id: str, text: str, metadata: dict = None):
    """
    Add a document to the knowledge base
    
    Args:
        doc_id: Unique identifier for the document
        text: The document content
        metadata: Optional metadata (category, type, etc.)
    """
    try:
        collection = get_or_create_collection()
        if not collection:
            return False
            
        embedding = embedder.encode(_e5_passage(text), show_progress_bar=False).tolist()
        collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata or {}]
        )
        logger.info(f"✓ Added document: {doc_id}")
        return True
    except Exception as e:
        logger.error(f"Error adding document {doc_id}: {e}")
        return False


def chunk_and_add_document(doc_id: str, text: str, metadata: dict = None, kb_version: int = 0, return_details: bool = False, target_collection_name: str = None):
    """
    Split *text* into fine-grained chunks and store each one with its own
    embedding.  This is the correct way to index a file that contains many
    independent facts (e.g. one fact per line or per paragraph), because a
    single embedding for the whole file averages all facts together and makes
    individual lookups imprecise.

    Chunking strategy:
      1. Split on blank lines (paragraphs).  
      2. If a paragraph is still > 400 chars, split further on single newlines.
      3. Skip chunks shorter than 10 chars (headers, blank lines, etc.).

    Uses batch embedding and batch upsert for large files to prevent:
      - ChromaDB locking on large uploads
      - Slow single-chunk embedding generation
      - GUI timeouts on large PDFs

    Args:
        doc_id: Base document identifier (chunk suffix appended automatically).
        text: Full document text to chunk and embed.
        metadata: Optional extra metadata merged into every chunk's metadata.
        kb_version: Global KB version counter at the time of indexing (for audit).
        target_collection_name: If set, use this specific collection (important
                                after delete_all to reuse the same collection).

    Returns the number of chunks successfully indexed.
    """
    import re as _re
    from datetime import datetime as _dt

    # Normalise Windows line-endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    page_blocks: list[tuple[Optional[int], str]] = []
    page_pattern = _re.compile(r'\[PAGE_START:\s*(\d+)\](.*?)\[PAGE_END:\s*\1\]', _re.DOTALL | _re.IGNORECASE)
    for match in page_pattern.finditer(text):
        page_num = int(match.group(1))
        page_text = (match.group(2) or "").strip()
        if page_text:
            page_blocks.append((page_num, page_text))
    if not page_blocks:
        page_blocks = [(None, text)]

    chunk_records: list[dict] = []
    current_unit = ""
    current_section = ""
    current_heading = ""

    TARGET_MIN_WORDS = 220
    TARGET_MAX_WORDS = 360
    TARGET_WORDS = 300
    OVERLAP_WORDS = 50

    unit_pattern = _re.compile(r'\bunit\s*(\d+)\b', _re.IGNORECASE)
    section_pattern = _re.compile(r'(?im)^\s*((?:unit|chapter|section|lesson)\s+[0-9A-Za-z.-]+[^\n]{0,120})\s*$')
    heading_hint_pattern = _re.compile(r'(?i)^(?:unit|chapter|section|lesson)\s+[0-9A-Za-z.-]+\b')
    chapter_heading_pattern = _re.compile(r'(?i)^\s*chapter\s+(\d+)\b')
    chapter_inline_pattern = _re.compile(r'(?i)\bchapter\s+(\d+)\b')
    chapter_from_section_pattern = _re.compile(r'(?i)^\s*section\s+(\d+)\.\d+')
    numeric_section_heading_pattern = _re.compile(
        r'^\s*(?:section\s+)?(\d{1,2}(?:\.\d{1,2}){1,2})(?:\s*[:.\-]\s*|\s+)[A-Za-z]'
    )
    toc_line_pattern = _re.compile(r'(?im)^\s*(?:chapter\s+\d+|\d{1,2}\.\d{1,2})[^\n]{0,140}(?:\.{2,}|\s{2,})\d{1,4}\s*$')
    reference_heading_pattern = _re.compile(r'(?i)^\s*(references|bibliography|works\s+cited|index|glossary|appendix)\s*$')

    def _is_toc_page(text_block: str) -> bool:
        txt = str(text_block or "")
        txt_l = txt.lower()
        chapter_hits = len(_re.findall(r'(?i)\bchapter\s+\d+\b', txt))
        section_hits = len(_re.findall(r'\b\d{1,2}\.\d{1,2}\b', txt))
        dotted_hits = len(_re.findall(r'(?m)\.{2,}\s*\d{1,4}\s*$', txt))
        if ("table of contents" in txt_l or "contents" in txt_l) and chapter_hits >= 2:
            return True
        if chapter_hits >= 6 and (section_hits >= 6 or dotted_hits >= 3):
            return True
        return False

    page_toc_flags: dict[int, bool] = {}
    page_chapter_hints: dict[int, str] = {}
    for page_num, page_text in page_blocks:
        if page_num is None:
            continue
        is_toc_page = _is_toc_page(page_text)
        page_toc_flags[page_num] = is_toc_page
        if is_toc_page:
            continue

        numeric_hits = [int(x) for x in _re.findall(r'\b(\d{1,2})\.\d{1,2}\b', str(page_text or ""))]
        if numeric_hits:
            counts: dict[int, int] = {}
            for n in numeric_hits:
                counts[n] = counts.get(n, 0) + 1
            chapter_num, freq = max(counts.items(), key=lambda kv: kv[1])
            if freq >= 2:
                page_chapter_hints[page_num] = f"Chapter {chapter_num}"
                continue

        chapter_hits = _re.findall(r'(?i)\bchapter\s+(\d{1,2})\b', str(page_text or ""))
        if chapter_hits:
            page_chapter_hints[page_num] = f"Chapter {chapter_hits[0]}"

    def _normalize_para(raw: str) -> str:
        cleaned = (raw or "").strip()
        cleaned = _re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _is_noise_chunk(text_block: str) -> bool:
        txt = (text_block or "").strip()
        if not txt:
            return True
        txt_l = txt.lower()
        if reference_heading_pattern.match(txt):
            return True
        if txt_l.startswith("page ") and len(txt.split()) <= 6:
            return True
        if _re.search(r'\b(doi:|isbn|issn|www\.|http[s]?://)\b', txt_l) and len(txt.split()) < 30:
            return True
        if len(_re.findall(r'\[[0-9]{1,3}\]|\([0-9]{4}\)', txt)) >= 5 and len(txt.split()) < 120:
            return True
        return False

    def _is_heading(text_block: str) -> bool:
        line = (text_block or "").strip()
        if not line:
            return False
        words = line.split()
        if len(words) > 14:
            return False
        if heading_hint_pattern.search(line):
            return True
        if any(sym in line for sym in [":", ";"]):
            return False
        if line.endswith((".", "؟", "?", "!", ",", "،")):
            return False
        titleish = sum(1 for w in words if w[:1].isupper())
        return titleish >= max(1, len(words) // 2)

    def _infer_chunk_role(text_block: str, section_val: str, title_val: str, chapter_val: str, page_val: Optional[int]) -> str:
        """
        Classify chunk role based on ACTUAL TEXT CONTENT, not metadata.
        
        Only classify as heading/toc if the text itself looks like that type.
        Normal body content that happens to be in a section should be "content", not "section_heading".
        """
        txt = str(text_block or "").strip()
        txt_l = txt.lower()
        word_count = len(txt.split())

        # TOC: only if text contains explicit toc markers or matches toc line pattern (table of contents, contents lines, etc.)
        toc_markers = ("table of contents", "brief contents", "of contents")
        chapter_entry_hits = len(_re.findall(r'(?i)\bchapter\s+\d+\b', txt[:3200]))
        section_entry_hits = len(_re.findall(r'\b\d{1,2}\.\d{1,2}\b', txt[:3200]))
        if (
            any(m in txt_l for m in toc_markers)
            or bool(toc_line_pattern.search(txt[:2200]))
            or chapter_entry_hits >= 3
            or (section_entry_hits >= 6 and word_count <= 260)
        ):
            return "toc"

        # Reference/Bibliography: explicit markers in the actual text
        if reference_heading_pattern.search(txt):
            return "reference"

        # Chapter heading: ONLY if text itself starts with "Chapter N" and is short
        if _re.search(r'(?im)^\s*chapter\s+\d+\b', txt) and word_count <= 20:
            return "chapter_heading"

        # Section heading: ONLY if text itself starts with numeric section AND is very short (like "9.6 Section Title")
        if _re.match(r'^\s*(?:section\s+)?\d{1,2}(?:\.\d{1,2}){1,2}(?:\s*[:.\-]\s*|\s+)[A-Za-z]', txt) and word_count <= 20:
            return "section_heading"

        # Summary/Conclusion: only if explicit markers in text itself
        if any(k in txt_l for k in ("summary", "conclusion", "recap", "in this chapter")) and word_count <= 50:
            return "summary"

        # Introduction: only if explicit markers in text itself
        if any(k in txt_l for k in ("introduction", "overview", "learning objectives", "objectives")) and word_count <= 50:
            return "introduction"

        # Key terms/Glossary: only if explicit markers
        if any(k in txt_l for k in ("key terms", "key concepts", "glossary")) and word_count <= 60:
            return "key_terms"

        # Default: normal body/content chunks
        return "content"

    def _split_long_text_to_windows(text_block: str, target_words: int, overlap_words: int) -> list[str]:
        tokens = text_block.split()
        if len(tokens) <= TARGET_MAX_WORDS:
            return [text_block]
        windows: list[str] = []
        start = 0
        step = max(1, target_words - overlap_words)
        while start < len(tokens):
            end = min(start + target_words, len(tokens))
            segment = " ".join(tokens[start:end]).strip()
            if segment:
                windows.append(segment)
            if end >= len(tokens):
                break
            start += step
        return windows

    structured_units: list[dict] = []
    current_chapter = ""

    for page_num, page_text in page_blocks:
        raw_paragraphs = _re.split(r'\n{2,}', page_text)
        page_hint_chapter = page_chapter_hints.get(page_num) if page_num is not None else ""
        page_is_toc = bool(page_toc_flags.get(page_num, False)) if page_num is not None else False
        for raw_para in raw_paragraphs:
            para = _normalize_para(raw_para)
            if len(para) < 20:
                continue
            if _is_noise_chunk(para):
                continue

            para_chapter_hits = len(_re.findall(r'(?i)\bchapter\s+\d+\b', para))
            para_section_hits = len(_re.findall(r'\b\d{1,2}\.\d{1,2}\b', para))
            para_is_toc = (
                page_is_toc
                or "table of contents" in para.lower()
                or bool(toc_line_pattern.search(para))
                or (para_chapter_hits >= 3 and para_section_hits >= 3)
            )

            if para_is_toc:
                structured_units.append({
                    "text": para,
                    "page": page_num,
                    "unit": current_unit,
                    "section": "Table of Contents",
                    "heading": "Table of Contents",
                    "title": "Table of Contents",
                    "chapter": "",
                })
                continue

            if page_hint_chapter and (not current_chapter or str(current_section or "").lower().startswith("page ")):
                current_chapter = page_hint_chapter
                if not current_section or str(current_section).lower().startswith("page "):
                    current_section = page_hint_chapter

            chapter_inline_match = chapter_inline_pattern.search(para)
            if chapter_inline_match:
                current_chapter = f"Chapter {chapter_inline_match.group(1)}"

            if _is_heading(para):
                current_heading = para
                section_match = section_pattern.search(para)
                if section_match:
                    current_section = section_match.group(1).strip()
                    sec_to_ch = chapter_from_section_pattern.search(current_section)
                    if sec_to_ch:
                        current_chapter = f"Chapter {sec_to_ch.group(1)}"
                chapter_match = chapter_heading_pattern.search(para)
                if chapter_match:
                    current_chapter = f"Chapter {chapter_match.group(1)}"
                    current_section = current_chapter
                unit_match = unit_pattern.search(para)
                if unit_match:
                    current_unit = unit_match.group(1)
                continue

            unit_match = unit_pattern.search(para)
            if unit_match:
                current_unit = unit_match.group(1)

            section_match = section_pattern.search(para)
            if section_match:
                current_section = section_match.group(1).strip()
                sec_to_ch = chapter_from_section_pattern.search(current_section)
                if sec_to_ch:
                    current_chapter = f"Chapter {sec_to_ch.group(1)}"
            else:
                numeric_match = numeric_section_heading_pattern.search(para[:120])
                if numeric_match:
                    current_section = f"Section {numeric_match.group(1)}"
                    current_chapter = f"Chapter {numeric_match.group(1).split('.')[0]}"

            if not current_section and current_chapter:
                current_section = current_chapter

            if not current_section and current_unit:
                current_section = f"Unit {current_unit}"

            if current_heading and current_heading.lower() not in para.lower():
                para = f"{current_heading}\n{para}"

            structured_units.append({
                "text": para,
                "page": page_num,
                "unit": current_unit,
                "section": current_section or (f"Page {page_num}" if page_num is not None else "Document"),
                "heading": current_heading,
                "title": current_heading,
                "chapter": current_chapter,
            })

    # Fallback for PDFs with weak paragraph structure (single newlines, OCR-ish text).
    if not structured_units:
        flat_text = _re.sub(r"\s+", " ", text).strip()
        line_units: list[tuple[Optional[int], str]] = []
        for page_num, page_text in page_blocks:
            for raw_line in _re.split(r"\n+", page_text):
                cleaned_line = _normalize_para(raw_line)
                if len(cleaned_line) >= 40:
                    line_units.append((page_num, cleaned_line))

        if line_units:
            for page_num, ln in line_units:
                fallback_section = f"Page {page_num}" if page_num is not None else "Document"
                structured_units.append({
                    "text": ln,
                    "page": page_num,
                    "unit": "",
                    "section": fallback_section,
                    "heading": "",
                    "title": "",
                    "chapter": "",
                })
        elif len(flat_text) >= 120:
            structured_units.append({
                "text": flat_text,
                "page": None,
                "unit": "",
                "section": "Document",
                "heading": "",
                "title": "",
                "chapter": "",
            })

    curr_words: list[str] = []
    curr_page = None
    curr_unit = ""
    curr_section = ""
    curr_chapter = ""
    curr_title = ""

    def _emit_current_chunk() -> None:
        nonlocal curr_words, curr_page, curr_unit, curr_section, curr_chapter, curr_title
        if not curr_words:
            return
        chunk_text = " ".join(curr_words).strip()
        if not chunk_text:
            return
        if _is_noise_chunk(chunk_text):
            return
        chunk_records.append({
            "text": chunk_text,
            "page": curr_page,
            "unit": curr_unit,
            "section": curr_section,
            "chapter": curr_chapter,
            "title": curr_title,
            "chunk_role": _infer_chunk_role(chunk_text, curr_section, curr_title, curr_chapter, curr_page),
        })

    for unit in structured_units:
        unit_text = str(unit.get("text") or "").strip()
        if not unit_text:
            continue

        next_section = str(unit.get("section") or "")
        next_chapter = str(unit.get("chapter") or "")
        next_title = str(unit.get("title") or unit.get("heading") or "")

        # Metadata consistency guard:
        # when structure boundary changes, flush current buffer so one chunk
        # does not span multiple chapter/section/title labels.
        structure_changed = bool(
            curr_words
            and (
                (next_section and curr_section and next_section != curr_section)
                or (next_chapter and curr_chapter and next_chapter != curr_chapter)
                or (next_title and curr_title and next_title != curr_title)
            )
        )
        if structure_changed and len(curr_words) >= max(60, TARGET_MIN_WORDS // 3):
            _emit_current_chunk()
            curr_words = []
            curr_page = unit.get("page")
            curr_unit = str(unit.get("unit") or "")
            curr_section = next_section
            curr_chapter = next_chapter
            curr_title = next_title

        windows = _split_long_text_to_windows(unit_text, TARGET_WORDS, OVERLAP_WORDS)
        for window_text in windows:
            window_words = window_text.split()
            if not window_words:
                continue

            if not curr_words:
                curr_page = unit.get("page")
                curr_unit = str(unit.get("unit") or "")
                curr_section = next_section
                curr_chapter = next_chapter
                curr_title = next_title

            if len(curr_words) + len(window_words) > TARGET_MAX_WORDS and len(curr_words) >= TARGET_MIN_WORDS:
                _emit_current_chunk()
                overlap = curr_words[-OVERLAP_WORDS:] if len(curr_words) > OVERLAP_WORDS else curr_words[:]
                curr_words = overlap[:]
                curr_page = unit.get("page")
                curr_unit = str(unit.get("unit") or curr_unit)
                curr_section = str(unit.get("section") or curr_section)
                curr_chapter = str(unit.get("chapter") or curr_chapter)
                curr_title = str(unit.get("title") or unit.get("heading") or curr_title)

            curr_words.extend(window_words)

            if len(curr_words) >= TARGET_WORDS:
                _emit_current_chunk()
                overlap = curr_words[-OVERLAP_WORDS:] if len(curr_words) > OVERLAP_WORDS else curr_words[:]
                curr_words = overlap[:]
                curr_page = unit.get("page")
                curr_unit = str(unit.get("unit") or curr_unit)
                curr_section = str(unit.get("section") or curr_section)
                curr_chapter = str(unit.get("chapter") or curr_chapter)
                curr_title = str(unit.get("title") or unit.get("heading") or curr_title)

    if curr_words and len(curr_words) >= max(60, TARGET_MIN_WORDS // 3):
        _emit_current_chunk()

    for record in chunk_records:
        page_val = record.get("page")
        if page_val is None:
            continue
        mapped_chapter = page_chapter_hints.get(page_val)
        if not mapped_chapter:
            continue

        role_l = str(record.get("chunk_role") or "").strip().lower()
        section_l = str(record.get("section") or "").strip().lower()
        if role_l == "toc" or "table of contents" in section_l:
            continue

        record["chapter"] = mapped_chapter

        section_text = str(record.get("section") or "").strip()
        sec_num_match = chapter_from_section_pattern.search(section_text)
        if not section_text or section_text.lower().startswith("page "):
            record["section"] = mapped_chapter
        elif sec_num_match and f"Chapter {sec_num_match.group(1)}" != mapped_chapter:
            record["section"] = mapped_chapter

    chunks = [r["text"] for r in chunk_records]
    details = {
        "doc_id": str(doc_id),
        "collection": None,
        "generated_chunks": len(chunks),
        "indexed_chunks": 0,
        "batch_errors": [],
        "reason": "",
    }

    if not chunks:
        reason = f"No usable chunks generated from text (len={len(text or '')}, structured_units={len(structured_units)})"
        logger.warning(f"chunk_and_add_document: {reason} | doc_id={doc_id}")
        details["reason"] = reason
        return details if return_details else 0

    collection = None
    # If a target collection was specified (e.g. after delete_all), use it directly
    if target_collection_name:
        try:
            collection = client.get_or_create_collection(name=target_collection_name)
            logger.info(f"chunk_and_add_document: using target collection '{target_collection_name}'")
        except Exception as e:
            logger.warning(f"chunk_and_add_document: target collection '{target_collection_name}' failed: {e}")
    if not collection:
        collection = get_or_create_collection(allow_empty=True)
    if not collection:
        reason = "No active collection available"
        logger.error(f"chunk_and_add_document: {reason} | doc_id={doc_id}")
        details["reason"] = reason
        return details if return_details else 0

    details["collection"] = getattr(collection, "name", "unknown")
    logger.info(
        "chunk_and_add_document start | doc_id=%s collection=%s text_chars=%s generated_chunks=%s",
        doc_id,
        details["collection"],
        len(text or ""),
        len(chunks),
    )

    success = 0
    now_iso = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # GPU-OPTIMIZED BATCH PROCESSING:
    # GPU can handle much larger batches than CPU (1000s of texts at once)
    # CPU is more limited (128-256 texts per batch recommended)
    if device == 'cuda':
        EMBEDDING_BATCH_SIZE = 64  # GPU: reduced to prevent OOM
        UPSERT_BATCH_SIZE = 128    # Chroma can take larger upserts
    else:
        EMBEDDING_BATCH_SIZE = 64  # CPU: smaller batches
        UPSERT_BATCH_SIZE = 100
    
    logger.info(f"Processing {len(chunks)} chunks using {device.upper()} (embed_batch={EMBEDDING_BATCH_SIZE}, upsert_batch={UPSERT_BATCH_SIZE})")
    
    for batch_start in range(0, len(chunks), UPSERT_BATCH_SIZE):
        batch_end = min(batch_start + UPSERT_BATCH_SIZE, len(chunks))
        batch_records = chunk_records[batch_start:batch_end]
        batch_chunks = [r["text"] for r in batch_records]
        batch_indices = range(batch_start, batch_end)
        
        try:
            # On GPU: encode entire batch in one go for maximum speed
            # On CPU: encode in sub-batches to avoid memory issues
            embedding_inputs = [_e5_passage(chunk) for chunk in batch_chunks]

            if device == 'cuda':
                batch_embeddings = embedder.encode(embedding_inputs, batch_size=EMBEDDING_BATCH_SIZE, show_progress_bar=False).tolist()
            else:
                embeddings = []
                for i in range(0, len(embedding_inputs), EMBEDDING_BATCH_SIZE):
                    sub = embedding_inputs[i:i+EMBEDDING_BATCH_SIZE]
                    sub_emb = embedder.encode(sub, batch_size=len(sub), show_progress_bar=False)
                    embeddings.append(sub_emb)
                import numpy as _np
                batch_embeddings = _np.vstack(embeddings).tolist()
            
            # Prepare batch metadata and upsert
            batch_ids = [f"{doc_id}_chunk_{idx}" for idx in batch_indices]
            batch_metas = []
            base_meta = dict(metadata or {})
            source_filename = str(base_meta.get("filename", "") or base_meta.get("source", "") or "")

            def _coerce_page_value(record: dict, fallback_text: str) -> Optional[int]:
                raw_page = record.get("page")
                try:
                    if raw_page is not None and str(raw_page).strip() != "":
                        p = int(raw_page)
                        if p > 0:
                            return p
                except Exception:
                    pass

                section_hint = str(record.get("section") or "")
                title_hint = str(record.get("title") or "")
                chapter_hint = str(record.get("chapter") or "")
                combined_hint = "\n".join([section_hint, title_hint, chapter_hint, str(fallback_text or "")[:400]])

                m = re.search(r"\bpage\s*(\d{1,5})\b", combined_hint, flags=re.IGNORECASE)
                if m:
                    try:
                        p = int(m.group(1))
                        if p > 0:
                            return p
                    except Exception:
                        pass
                return None

            for local_idx, idx in enumerate(batch_indices):
                record = batch_records[local_idx]
                chunk_meta = dict(metadata or {})
                chunk_meta["chunk_index"] = idx
                chunk_meta["chunk_total"] = len(chunks)
                chunk_meta["document_id"] = str(doc_id)
                chunk_meta["base_doc_id"] = str(doc_id)
                chunk_meta["updated_at"] = now_iso
                chunk_meta["kb_version"] = kb_version
                chunk_meta["unit"] = str(record.get("unit") or "")
                chunk_meta["section"] = str(record.get("section") or chunk_meta.get("section") or "")
                chunk_meta["chapter"] = str(record.get("chapter") or chunk_meta.get("chapter") or "")
                chunk_meta["title"] = str(record.get("title") or chunk_meta.get("title") or "")
                chunk_meta["chunk_role"] = str(record.get("chunk_role") or chunk_meta.get("chunk_role") or "content")
                resolved_page = _coerce_page_value(record, record.get("text") or "")
                if resolved_page is not None:
                    chunk_meta["page"] = int(resolved_page)
                chunk_meta["source_filename"] = source_filename
                if source_filename:
                    chunk_meta["source"] = source_filename
                logger.info(
                    "[PAGE META] chunk_id=%s page=%s source=%s",
                    batch_ids[local_idx],
                    (chunk_meta.get("page") if chunk_meta.get("page") is not None else "None"),
                    (chunk_meta.get("source") or chunk_meta.get("source_filename") or ""),
                )
                # Chroma metadata must be scalar primitive values and cannot include None.
                clean_meta = {}
                for mk, mv in chunk_meta.items():
                    if mv is None:
                        continue
                    if isinstance(mv, (str, int, float, bool)):
                        clean_meta[mk] = mv
                    else:
                        clean_meta[mk] = str(mv)
                batch_metas.append(clean_meta)
            
            # Batch upsert (much faster than individual upserts)
            collection.upsert(
                ids=batch_ids,
                embeddings=batch_embeddings,
                documents=batch_chunks,
                metadatas=batch_metas,
            )
            success += len(batch_chunks)
            logger.info(f"  ✓ Indexed [{batch_start}-{batch_end-1}]/{len(chunks)} chunks")
            
        except Exception as e:
            err_msg = f"Error upserting batch [{batch_start}-{batch_end-1}] for doc_id={doc_id}: {e}"
            details["batch_errors"].append(err_msg)
            logger.exception(err_msg)
            # Continue so we can capture all failing batches and return full diagnostics.

    details["indexed_chunks"] = int(success)
    logger.info(
        "chunk_and_add_document done | doc_id=%s collection=%s indexed=%s/%s errors=%s",
        doc_id,
        details["collection"],
        success,
        len(chunks),
        len(details["batch_errors"]),
    )

    if success == 0 and details["batch_errors"]:
        raise RuntimeError("All upsert batches failed. First error: " + details["batch_errors"][0])

    return details if return_details else success

def search_documents(query: str, top_k: int = 3, distance_threshold: float = 1.2):
    """
    Search for relevant documents using semantic similarity.

    Only returns documents whose L2 distance is below *distance_threshold*.
    ChromaDB always returns the nearest neighbours regardless of how unrelated
    they are, so without this gate the LLM would receive irrelevant context for
    every query (e.g. a Breaking Bad quote returning a football document).

    Args:
        query: User's question
        top_k: Maximum number of results to consider
        distance_threshold: Maximum L2 distance to accept (lower = stricter).
                            Typical values for all-MiniLM-L6-v2:
                              < 0.5  → very high relevance
                              0.5–1.0 → good relevance
                              > 1.0  → likely unrelated (filtered out)

    Returns:
        List of relevant document texts (may be empty if nothing is close enough)
    """
    try:
        collection = get_or_create_collection()
        if not collection:
            return []

        # Guard: ChromaDB raises if n_results > number of stored documents
        count = collection.count()
        if count == 0:
            logger.info("Knowledge base is empty — no documents to search")
            return []
        n_results = min(top_k, count)

        # Normalise query: strip whitespace and lowercase so "Say My Name" and
        # "say my name" produce identical embeddings and rank equally.
        normalised_query = " ".join(query.strip().split())
        query_embedding = embedder.encode(_e5_query(normalised_query), show_progress_bar=False).tolist()
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "distances"],
        )

        # Safely unpack results (ChromaDB may return None for empty results)
        if not results or not results.get('documents') or not results.get('distances'):
            return []
        
        raw_docs      = results['documents'][0] if results['documents'][0] else []
        raw_distances = results['distances'][0]  if results['distances'][0] else []

        # Filter by relevance threshold
        relevant = []
        for doc, dist in zip(raw_docs, raw_distances):
            if dist <= distance_threshold:
                relevant.append(doc)
                logger.info(f"  ✓ Accepted doc (dist={dist:.3f}): {doc[:60]}...")
            else:
                logger.info(f"  ✗ Rejected doc (dist={dist:.3f} > threshold={distance_threshold}): {doc[:60]}...")

        logger.info(
            f"RAG search: query='{query[:50]}...' | candidates={len(raw_docs)} | accepted={len(relevant)}"
        )
        return relevant
    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        return []

def get_all_documents():
    """Get all documents in the knowledge base"""
    try:
        collection = get_or_create_collection()
        if not collection:
            return []
            
        result = collection.get()
        return result['documents']
    except Exception as e:
        logger.error(f"Error getting documents: {e}")
        return []

def delete_document(doc_id: str):
    """Delete a document from the knowledge base"""
    try:
        collection = get_or_create_collection()
        if not collection:
            return False
            
        collection.delete(ids=[doc_id])
        logger.info(f"✓ Deleted document: {doc_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting document {doc_id}: {e}")
        return False


def delete_documents_with_prefix(prefix: str) -> int:
    """
    Delete all documents whose id starts with the given prefix.

    Returns the number of documents deleted.
    """
    try:
        deleted_total = 0
        try:
            collections = list(client.list_collections() or [])
        except Exception:
            collections = []

        if not collections:
            fallback = get_or_create_collection(allow_empty=True)
            collections = [fallback] if fallback else []

        for col in collections:
            if not col:
                continue
            try:
                col_name = getattr(col, "name", "<unknown>")
                result = col.get(include=["metadatas"]) or {}
                ids = result.get("ids", [])
                to_delete = [i for i in ids if str(i).startswith(prefix)]
                if not to_delete:
                    continue
                col.delete(ids=to_delete)
                deleted_total += len(to_delete)
                logger.info(f"✓ Deleted {len(to_delete)} documents with prefix '{prefix}' from '{col_name}'")
            except Exception as col_err:
                logger.warning(f"delete_documents_with_prefix: failed in collection '{getattr(col, 'name', '<unknown>')}': {col_err}")

        return deleted_total
    except Exception as e:
        logger.error(f"Error deleting documents with prefix {prefix}: {e}")
        return 0


def delete_documents_by_filename(filename: str) -> int:
    """
    Delete ALL chunks associated with a particular filename, regardless of the
    doc_id prefix used when indexing them.

    Uses multiple matching strategies so it catches:
      - Exact metadata.filename match  (e.g. "Best_player.txt")
      - UUID-prefixed variants         (e.g. "ab12cd34_Best_player.txt")
      - doc_id containing the filename (e.g. "upload_ab12cd34_Best_player.txt_chunk_0")

    Returns the number of documents deleted.
    """
    try:
        import re as _re

        # Strip any leading UUID prefix (8 hex chars + underscore) from the
        # target filename so we can match both prefixed and unprefixed variants.
        bare_name = _re.sub(r'^[0-9a-fA-F]{8}_', '', filename)
        deleted_total = 0

        try:
            collections = list(client.list_collections() or [])
        except Exception:
            collections = []

        if not collections:
            fallback = get_or_create_collection(allow_empty=True)
            collections = [fallback] if fallback else []

        for col in collections:
            if not col:
                continue
            try:
                col_name = getattr(col, "name", "<unknown>")
                result = col.get(include=["metadatas"]) or {}
                ids = result.get("ids", [])
                metadatas = result.get("metadatas", [])

                to_delete = set()
                for doc_id, meta in zip(ids, metadatas):
                    sid = str(doc_id)
                    fn = meta.get("filename", "") if isinstance(meta, dict) else ""
                    src = meta.get("source", "") if isinstance(meta, dict) else ""

                    if fn == filename or src == filename:
                        to_delete.add(sid)
                        continue

                    if bare_name and (fn.endswith(bare_name) or src.endswith(bare_name)):
                        to_delete.add(sid)
                        continue

                    if filename in sid or bare_name in sid:
                        to_delete.add(sid)
                        continue

                if not to_delete:
                    continue

                col.delete(ids=list(to_delete))
                deleted_total += len(to_delete)
                logger.info(f"✓ Deleted {len(to_delete)} chunks matching filename '{filename}' from '{col_name}'")
            except Exception as col_err:
                logger.warning(f"delete_documents_by_filename: failed in collection '{getattr(col, 'name', '<unknown>')}': {col_err}")

        if deleted_total == 0:
            logger.info(f"delete_documents_by_filename: nothing found for '{filename}'")
        return deleted_total
    except Exception as e:
        logger.error(f"Error deleting documents by filename {filename}: {e}")
        return 0


def garbage_collect_support_collections(active_collection_name: str = "", delete_non_empty: bool = False, prefix: str = "support_docs_v3_") -> dict:
    """Delete old support collections except the currently active one.

    Args:
        active_collection_name: Collection name that must be preserved.
        delete_non_empty: If True, delete stale collections even if they contain chunks.
                          If False, only empty stale collections are deleted.
        prefix: Collection-name prefix considered part of the support KB lifecycle.

    Returns:
        Dict with deleted/skipped collection names and counts.
    """
    deleted: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    active = str(active_collection_name or "").strip()
    try:
        collections = list(client.list_collections() or [])
    except Exception as e:
        logger.warning(f"garbage_collect_support_collections: list_collections failed: {e}")
        return {"deleted": deleted, "skipped": skipped, "errors": [str(e)]}

    for col in collections:
        name = str(getattr(col, "name", "") or "").strip()
        if not name:
            continue
        if prefix and not name.startswith(prefix):
            continue
        if active and name == active:
            skipped.append(name)
            continue
        try:
            count = int(col.count() or 0)
            if count > 0 and not delete_non_empty:
                skipped.append(name)
                continue
            client.delete_collection(name=name)
            deleted.append(name)
            logger.info(f"garbage_collect_support_collections: deleted '{name}' (count={count})")
        except Exception as col_err:
            errors.append(f"{name}: {col_err}")
            logger.warning(f"garbage_collect_support_collections: failed for '{name}': {col_err}")

    return {
        "deleted": deleted,
        "skipped": skipped,
        "errors": errors,
        "deleted_count": len(deleted),
        "skipped_count": len(skipped),
    }


def update_document(doc_id: str, text: str, metadata: dict = None) -> int:
    """
    Replace an existing uploaded document (and its chunked children) with
    new text.  This deletes any existing chunks with the same prefix and
    reindexes the new content using `chunk_and_add_document`.

    Returns the number of chunks indexed for the updated document.
    """
    try:
        # Remove existing chunks that were created from this doc_id
        delete_documents_with_prefix(str(doc_id))
        # Add new chunks
        return chunk_and_add_document(doc_id=doc_id, text=text, metadata=metadata)
    except Exception as e:
        logger.error(f"Error updating document {doc_id}: {e}")
        return 0


def find_base_doc_id_by_filename(filename: str) -> str | None:
    """
    Find the base doc_id (before the "_chunk_" suffix) for any indexed chunks
    that have metadata.filename == filename. Returns the base doc_id or None.
    """
    try:
        collection = get_or_create_collection()
        if not collection:
            return None
        # NOTE: "ids" must NOT be in include — ChromaDB always returns ids automatically
        result = collection.get(include=["metadatas"]) or {}
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        if not ids or not metadatas:
            return None

        for doc_id, meta in zip(ids, metadatas):
            if isinstance(meta, dict) and meta.get("filename") == filename:
                # If the id ends with _chunk_\d+, strip that suffix
                sid = str(doc_id)
                if "_chunk_" in sid:
                    return sid.split("_chunk_")[0]
                return sid
        return None
    except Exception as e:
        logger.error(f"Error finding base doc id by filename {filename}: {e}")
        return None


def delete_documents_by_ids(ids: list) -> int:
    """
    Delete specific document ids from the collection. Returns number deleted.
    """
    try:
        collection = get_or_create_collection()
        if not collection:
            return 0
        if not ids:
            return 0
        collection.delete(ids=ids)
        logger.info(f"✓ Deleted {len(ids)} specified documents")
        return len(ids)
    except Exception as e:
        logger.error(f"Error deleting documents by ids: {e}")
        return 0


def delete_all_documents() -> tuple[int, str]:
    """Delete all chunks from the currently active collection.
    
    Returns (deleted_count, collection_name) so the caller can pass the
    collection name to chunk_and_add_document to reuse the same collection.
    """
    try:
        collection = get_or_create_collection()
        if not collection:
            return 0, ""
        col_name = getattr(collection, "name", "")
        result = collection.get() or {}
        ids = result.get("ids", []) or []
        if not ids:
            return 0, col_name
        # Delete in batches to avoid oversized payloads on large collections
        batch_size = 2000
        deleted = 0
        for start in range(0, len(ids), batch_size):
            batch = ids[start:start + batch_size]
            collection.delete(ids=batch)
            deleted += len(batch)
        logger.info(f"✓ Deleted all chunks from collection '{col_name}': {deleted}")
        return deleted, col_name
    except Exception as e:
        logger.error(f"Error deleting all documents: {e}")
        return 0, ""


def list_uploaded_files() -> list:
    """
    Return a list of uploaded files discovered in the collection, along with
    the number of chunked entries indexed for each filename and the base
    doc_id used when originally indexed.

    Returns: [{"filename": str, "chunks": int, "doc_id": str}, ...]
    """
    out = {}
    try:
        collection = get_or_create_collection()
        if not collection:
            return []
        # NOTE: "ids" must NOT be in include — ChromaDB always returns ids automatically
        result = collection.get(include=["metadatas"]) or {}
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        for doc_id, meta in zip(ids, metadatas):
            if not isinstance(meta, dict):
                continue
            # Support multiple metadata keys that may contain the original
            # uploaded filename. Historically some indexing paths stored the
            # name under 'source' or 'source_filename' instead of 'filename'.
            filename = meta.get("filename") or meta.get("source") or meta.get("source_filename")
            if not filename:
                continue
            # Normalize to a string
            filename = str(filename)
            base = str(doc_id)
            if "_chunk_" in base:
                base = base.split("_chunk_")[0]
            k = (filename, base)
            out.setdefault(k, 0)
            out[k] += 1
        # Build result list
        res = []
        for (filename, doc_id), cnt in out.items():
            res.append({"filename": filename, "chunks": cnt, "doc_id": doc_id})
        return res
    except Exception as e:
        logger.error(f"Error listing uploaded files: {e}")
        return []

def clear_knowledge_base():
    """Clear all documents from knowledge base"""
    try:
        # Delete collection if exists
        try:
            client.delete_collection(name="support_docs")
            logger.info("✓ Deleted old collection")
        except Exception as e:
            # Log the exception info instead of silently swallowing all exceptions
            logger.info("No existing collection to delete or deletion error: %s", e)
        
        # Create fresh collection
        client.create_collection(name="support_docs")
        logger.info("✓ Created new collection")
        return True
    except Exception as e:
        logger.error(f"Error clearing knowledge base: {e}")
        return False

def count_documents():
    """Count total documents in knowledge base"""
    try:
        collection = get_or_create_collection()
        if not collection:
            return 0
        result = collection.count()
        return result
    except Exception as e:
        logger.error(f"Error counting documents: {e}")
        return 0

if __name__ == "__main__":
    # Test the knowledge base
    print("Testing Knowledge Base...")
    
    # Clear first
    clear_knowledge_base()
    
    # Add test document
    add_document(
        doc_id="test_1",
        text="Our support hours are Monday to Friday, 9 AM to 5 PM EST.",
        metadata={"category": "general", "type": "info"}
    )
    
    # Search
    results = search_documents("What are your hours?")
    print(f"\nSearch Results: {results}")
    
    # Count
    count = count_documents()
    print(f"\nTotal documents: {count}")
