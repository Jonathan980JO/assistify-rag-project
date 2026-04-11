import os
import re
import uuid
import time
import logging
import asyncio
import torch
import numpy as np
from typing import List, Dict, Any, Optional

import PyPDF2
import pdfplumber
from pydantic import BaseModel, Field
from datetime import datetime

# OCR dependencies
try:
    import pytesseract
    from pdf2image import convert_from_path
except ImportError:
    pytesseract = None
    convert_from_path = None

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
try:
    from sentence_transformers import CrossEncoder
except Exception:
    CrossEncoder = None

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("RAG_PDF_Pipeline")

# ================= STEP 15: PERFORMANCE CONFIG =================
BATCH_SIZE = 16
# Use GPU for embedding when available — the embedding model (~500MB) fits
# alongside Ollama. Falls back to CPU if CUDA is unavailable.
try:
    if torch.cuda.is_available():
        DEVICE = "cuda"
    else:
        DEVICE = "cpu"
except Exception as e:
    import logging
    logging.getLogger("RAG_PDF_Pipeline").error(f"Fallback to CPU due to exception: {e}", exc_info=True)
    DEVICE = "cpu"

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
RERANKER_MODEL = os.environ.get("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# ================= MODELS =================
class DocumentChunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    page: int
    section: str = "Unknown"
    section_title: str = "Unknown"
    chapter: str = "Unknown"
    title: str = "Unknown"
    detected_entity: Optional[str] = None
    chunk_role: str = "content"
    document_type: str
    source: str
    timestamp: float = Field(default_factory=time.time)


# ================= EMBEDDING STORE =================
class VectorStore:
    def __init__(self, persist_directory: str = "./chroma_db"):
        from backend.knowledge_base import client as kb_client
        self.client = kb_client
        self.collection = self._resolve_active_collection()
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL} on {DEVICE}")
        self.embedding_model_name = EMBEDDING_MODEL
        self.embedding_model = SentenceTransformer(self.embedding_model_name, device=DEVICE)
        self.embedding_dim = int(self.embedding_model.get_sentence_embedding_dimension())
        # After loading the embedding model, verify compatibility with the
        # selected Chroma collection. If the collection already contains
        # embeddings with a different dimensionality, attempt to switch the
        # runtime embedding model to one that matches the collection to avoid
        # InvalidDimensionException during queries. This keeps retrieval
        # behavior consistent without reindexing unless explicitly required.
        try:
            probe = self.collection.get(include=["embeddings"], limit=1) or {}
            embs = probe.get("embeddings") or []
            collection_dim = None
            # Try to robustly find the first numeric embedding vector regardless
            # of nesting structure that Chroma might return.
            if embs and isinstance(embs, list):
                first_emb = None
                for entry in embs:
                    if entry is None:
                        continue
                    # entry may be a list-of-lists or a flat list
                    if isinstance(entry, list) and entry:
                        # If inner element is a list of numbers
                        candidate = entry[0]
                        if isinstance(candidate, (list, tuple)):
                            first_emb = candidate
                            break
                        # Or entry itself might be a flat vector
                        try:
                            # check if entry is a numeric sequence
                            _ = float(entry[0])
                            first_emb = entry
                            break
                        except Exception:
                            # not numeric at first position; continue scanning
                            continue
                    else:
                        # Unexpected shape — skip
                        continue
                if first_emb:
                    try:
                        collection_dim = len(first_emb)
                    except Exception:
                        collection_dim = None

            if collection_dim and collection_dim != self.embedding_dim:
                logger.warning(
                    f"Embedding dimension mismatch: runtime={self.embedding_dim} vs collection={collection_dim}."
                )
                # Map known dims to reasonable model choices. This is a
                # conservative runtime-only fix: prefer switching runtime model
                # to match the already-indexed collection rather than reindexing.
                model_by_dim = {
                    768: os.environ.get("EMBEDDING_MODEL_768", "intfloat/multilingual-e5-base"),
                    384: os.environ.get("EMBEDDING_MODEL_384", "sentence-transformers/all-MiniLM-L6-v2"),
                }
                target_model = model_by_dim.get(collection_dim)
                if target_model:
                    switched = self._switch_embedding_model(target_model)
                    if switched:
                        logger.info(f"Switched embedding model to match collection dim={collection_dim}")
                        self.embedding_dim = int(self.embedding_model.get_sentence_embedding_dimension())
                else:
                    logger.warning(
                        f"No known embedding model mapped to collection_dim={collection_dim}; queries may fail."
                    )
        except Exception:
            # If any introspection fails, continue — we'll surface errors during queries
            pass

        logger.info(
            f"Embedding model loaded (dim={self.embedding_dim}). Active collection={self.collection.name} count={self.collection.count()}"
        )

        # Monkey-patch the collection.query method so that callers using
        # `query_texts` (instead of `query_embeddings`) will have embeddings
        # computed by the runtime `self.embedding_model`. This prevents
        # accidental use of a different embedding function and reduces the
        # chance of dimensionality mismatches when tests or external code
        # call `live_rag.vs.collection.query(...)` directly.
        try:
            orig_query = self.collection.query

            def _patched_query(*args, **kwargs):
                # If caller supplied `query_texts`, compute embeddings and
                # forward as `query_embeddings` to the original query.
                q_texts = None
                if 'query_texts' in kwargs:
                    q_texts = kwargs.pop('query_texts')
                elif len(args) >= 1 and isinstance(args[0], (list, tuple)) and isinstance(args[0][0], str):
                    # positional first arg may be query_texts
                    q_texts = args[0]
                    args = args[1:]

                if q_texts is not None:
                    emb_list = self.embedding_model.encode(list(q_texts), show_progress_bar=False)
                    # Ensure converted to plain Python lists for chroma
                    q_embs = [e.tolist() if hasattr(e, 'tolist') else list(e) for e in emb_list]
                    kwargs['query_embeddings'] = q_embs
                return orig_query(*args, **kwargs)

            # Attach the original for introspection if needed
            _patched_query._orig = orig_query
            self.collection.query = _patched_query
        except Exception:
            # If monkey-patch fails, it's safe to continue — callers can still
            # call the collection directly but may face dimension errors.
            pass

        self.reranker = None
        
        DISABLE_RERANKER_FLAG = os.environ.get("ASSISTIFY_DISABLE_RERANKER", "0") == "1" or os.environ.get("ASSISTIFY_SAFE_MODE", "0") == "1"

        if CrossEncoder is not None and not DISABLE_RERANKER_FLAG:
            try:
                logger.info(f"Loading reranker model: {RERANKER_MODEL} on {DEVICE}")
                self.reranker = CrossEncoder(RERANKER_MODEL, device=DEVICE)
                logger.info("Reranker model loaded.")
            except Exception as rerank_err:
                logger.warning(f"Reranker disabled (failed to load): {rerank_err}")
        elif DISABLE_RERANKER_FLAG:
            logger.info("Reranker is explicitly disabled by Safe Mode or env var.")

    def _resolve_active_collection(self):
        """Pick a usable collection with data; avoid binding to an empty default."""
        preferred = os.environ.get("ASSISTIFY_COLLECTION_NAME", "").strip()
        if preferred:
            try:
                col = self.client.get_or_create_collection(name=preferred, metadata={"hnsw:space": "cosine"})
                expected_dim = int(self.embedding_model.get_sentence_embedding_dimension()) if hasattr(self, "embedding_model") else None
                if expected_dim:
                    probe_embedding = [0.0] * expected_dim
                    try:
                        col.query(query_embeddings=[probe_embedding], n_results=1, include=["distances"])
                    except Exception as probe_err:
                        msg = str(probe_err).lower()
                        if "dimensionality" in msg or "attribute 'dimensionality'" in msg:
                            logger.warning(f"Preferred collection '{preferred}' incompatible/corrupt; recreating: {probe_err}")
                            try:
                                self.client.delete_collection(name=preferred)
                            except Exception:
                                pass
                            col = self.client.get_or_create_collection(name=preferred, metadata={"hnsw:space": "cosine"})
                logger.info(f"Using collection from ASSISTIFY_COLLECTION_NAME={preferred} (count={col.count()})")
                return col
            except Exception as e:
                logger.warning(f"Requested collection '{preferred}' unavailable: {e}")

        existing = {c.name: c for c in self.client.list_collections()}

        # 2) Prefer newest non-empty support_docs_v3* collection
        v3_candidates = sorted([name for name in existing if name.startswith("support_docs_v3")], reverse=True)
        for name in v3_candidates:
            try:
                col = self.client.get_collection(name=name)
                if col.count() > 0:
                    logger.info(f"Auto-selected populated collection: {name} (count={col.count()})")
                    return col
            except Exception as e:
                logger.warning(f"Skipping collection '{name}': {e}")

        # 3) Legacy fallback
        if "support_docs" in existing:
            try:
                col = self.client.get_collection(name="support_docs")
                if col.count() > 0:
                    logger.info(f"Auto-selected legacy collection: support_docs (count={col.count()})")
                    return col
            except Exception:
                pass

        # 4) No populated collection found — create or return the designated
        # support_docs_v3_latest collection (do NOT fallback to adaptive_rag_collection).
        logger.warning("No populated collection found; creating or using support_docs_v3_latest instead of adaptive_rag_collection")
        return self.client.get_or_create_collection(
            name="support_docs_v3_latest",
            metadata={"hnsw:space": "cosine"}
        )

    def _switch_embedding_model(self, model_name: str) -> bool:
        """Switch embedding model at runtime (used for dimension recovery)."""
        try:
            logger.warning(f"Switching embedding model to {model_name} for collection compatibility")
            self.embedding_model = SentenceTransformer(model_name, device=DEVICE)
            self.embedding_model_name = model_name
            self.embedding_dim = int(self.embedding_model.get_sentence_embedding_dimension())
            logger.info(f"Embedding model switched successfully (dim={self.embedding_dim})")
            return True
        except Exception as e:
            logger.error(f"Failed to switch embedding model to {model_name}: {e}")
            return False

    def _manual_query_fallback(self, query_embedding: np.ndarray, n_results: int, filter_meta: Dict[str, Any] = None):
        """Fallback retrieval using stored embeddings when Chroma HNSW query fails.

        This implementation is defensive and version-compatible with ChromaDB
        instances that do not accept 'ids' in the `include` parameter.
        """
        # Attempt to call get() in a version-safe way: avoid asking for 'ids'
        # inside include because some chroma versions reject it.
        data = None
        tried_variants = []
        try:
            tried_variants.append("include=documents,metadatas,embeddings")
            data = self.collection.get(include=["documents", "metadatas", "embeddings"])
        except Exception as e1:
            logger.debug(f"collection.get(include=[docs,metadatas,embs]) failed: {e1}")
            try:
                tried_variants.append("get() no include")
                data = self.collection.get()
            except Exception as e2:
                logger.warning(f"collection.get() failed during manual fallback: {e2}")
                data = {}

        if data is None:
            data = {}

        # Debug logging
        logger.info(f"[MANUAL FALLBACK] activated; tried variants={tried_variants}")

        embs = data.get("embeddings")
        docs = data.get("documents")
        metas = data.get("metadatas")
        ids = data.get("ids") if "ids" in data else None

        # Normalize possible numpy arrays and single-nested lists
        def _to_list(x):
            if x is None:
                return []
            if isinstance(x, np.ndarray):
                try:
                    return x.tolist()
                except Exception:
                    return list(x)
            return x

        embs = _to_list(embs)
        docs = _to_list(docs)
        metas = _to_list(metas)
        ids = _to_list(ids)

        # Flatten one-level nested shapes that Chroma sometimes returns
        if isinstance(docs, list) and len(docs) == 1 and isinstance(docs[0], list):
            docs = docs[0]
        if isinstance(metas, list) and len(metas) == 1 and isinstance(metas[0], list):
            metas = metas[0]
        if isinstance(embs, list) and len(embs) == 1 and isinstance(embs[0], list):
            embs = embs[0]
        if isinstance(ids, list) and len(ids) == 1 and isinstance(ids[0], list):
            ids = ids[0]

        docs = docs or []
        metas = metas or []
        embs = embs or []
        ids = ids or []

        logger.info(f"[MANUAL FALLBACK] counts - docs={len(docs)} metadatas={len(metas)} embeddings={len(embs)} ids={len(ids)}")

        if not docs or not embs:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        query_vec = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(query_vec) + 1e-12
        scored = []

        # Iterate defensively; zip may truncate so iterate indices
        for i in range(len(docs)):
            try:
                doc = docs[i]
                emb = embs[i] if i < len(embs) else None
                meta = metas[i] if i < len(metas) else {}

                if doc is None or emb is None:
                    continue

                if not isinstance(meta, dict):
                    meta = meta or {}

                if filter_meta:
                    matched = True
                    for k, v in filter_meta.items():
                        if meta.get(k) != v:
                            matched = False
                            break
                    if not matched:
                        continue

                emb_vec = np.array(emb, dtype=np.float32)
                if emb_vec.shape[0] != query_vec.shape[0]:
                    continue

                sim = float(np.dot(query_vec, emb_vec) / (q_norm * (np.linalg.norm(emb_vec) + 1e-12)))
                dist = 1.0 - sim
                scored.append((sim, dist, doc, meta))
            except Exception:
                # Skip problematic entries
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: max(1, n_results)]

        docs_out = [item[2] for item in top]
        metas_out = [item[3] for item in top]
        dists_out = [item[1] for item in top]

        logger.info(f"[MANUAL FALLBACK] valid candidates after parsing: {len(docs_out)}")

        return {
            "documents": [docs_out],
            "metadatas": [metas_out],
            "distances": [dists_out],
        }

    @staticmethod
    def _normalize_query_text(query: str) -> str:
        return re.sub(r"\s+", " ", (query or "").strip())

    @staticmethod
    def _contains_arabic(text: str) -> bool:
        return any('\u0600' <= ch <= '\u06FF' for ch in (text or ""))

    @staticmethod
    def _to_e5_passage(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        return f"passage: {cleaned}" if cleaned else "passage:"

    @staticmethod
    def _to_e5_query(query: str) -> str:
        cleaned = re.sub(r"\s+", " ", (query or "").strip())
        return f"query: {cleaned}" if cleaned else "query:"

    @staticmethod
    def _is_toc_like(text: str, metadata: Dict[str, Any]) -> bool:
        section = str((metadata or {}).get("section", "")).lower()
        snippet = str(text or "")[:500].lower()
        hay = f"{section}\n{snippet}"
        if any(t in hay for t in ["table of contents", "contents", "index", "toc", "brief contents"]):
            return True
        if re.search(r"\.{3,}\s*\d+", hay):
            return True
        # Aggressive heuristic: if there are many numbers at the end of lines, it's likely a TOC
        if len(re.findall(r"\d+\s*$", hay, re.MULTILINE)) > 4:
            return True
        return False

    @staticmethod
    def _query_profile(query: str) -> Dict[str, bool]:
        q = (query or "").lower()
        chapter_match = re.search(r"\b(?:chapter|unit)\s+(\d+)\b", q)
        return {
            "chapter_query": bool(chapter_match),
            "chapter_num": int(chapter_match.group(1)) if chapter_match else None,
            "structure_query": any(k in q for k in ["chapter", "unit", "section", "list", "topics", "table of contents", "contents"]),
            "overview_query": any(k in q for k in ["overview", "summary", "summarize", "what is this document about", "main ideas", "topics covered", "introduction"]),
            "list_chapters_query": ("list" in q and ("chapter" in q or "unit" in q)) or ("chapters in the book" in q) or ("units in the book" in q),
            "chapter_sections_query": bool(re.search(r"sections?\s+in\s+(?:chapter|unit)\s+\d+", q)),
            "chapter_topics_query": bool(chapter_match) and any(k in q for k in ["about", "topics", "covered", "discussed"]),
        }

    @staticmethod
    def _is_low_quality_candidate(text: str, metadata: Dict[str, Any]) -> bool:
        section = str((metadata or {}).get("section", "")).lower()
        title = str((metadata or {}).get("title", "")).lower()
        snippet = str(text or "")[:900].lower()
        hay = f"{section}\n{title}\n{snippet}"
        if re.search(r"\b(references|bibliography|works cited)\b", hay):
            return True
        if "index" in hay and not re.search(r"\b(?:chapter|unit)\s+\d+\b", hay):
            return True
        if snippet.strip().startswith("page ") and len(snippet.split()) < 15:
            return True
        if len(re.findall(r"\[[0-9]{1,3}\]|\([12][0-9]{3}\)", snippet)) >= 8 and len(snippet.split()) < 150:
            return True
        return False

    @staticmethod
    def _tokenize_words(text: str) -> List[str]:
        return re.findall(r"[A-Za-z\u0600-\u06FF0-9]+", str(text or ""))

    @staticmethod
    def _ocr_garbage_ratio(text: str) -> float:
        tokens = VectorStore._tokenize_words(text)
        if not tokens:
            return 1.0
        short_tokens = sum(1 for tok in tokens if len(tok) <= 2)
        weird_tokens = sum(1 for tok in tokens if re.search(r"[^A-Za-z\u0600-\u06FF0-9]", tok))
        non_alpha = sum(1 for tok in tokens if not re.search(r"[A-Za-z\u0600-\u06FF]", tok))
        return (short_tokens + weird_tokens + non_alpha) / float(3 * max(1, len(tokens)))

    @staticmethod
    def _heading_dominance_ratio(text: str) -> float:
        lines = [ln.strip() for ln in re.split(r"\n+", str(text or "")) if ln.strip()]
        if not lines:
            return 0.0

        heading_like = 0
        for line in lines:
            line_tokens = re.findall(r"[A-Za-z\u0600-\u06FF0-9]+", line)
            if not line_tokens:
                continue
            if len(line_tokens) <= 6 and not re.search(r"[.!?؟:;]", line):
                heading_like += 1
                continue
            if re.match(r"^\s*(?:lesson|chapter|unit|section)\b", line, flags=re.IGNORECASE):
                heading_like += 1
                continue
            if re.match(r"^\s*\d+(?:\.\d+)*\s+[A-Za-z\u0600-\u06FF]", line):
                heading_like += 1

        return heading_like / float(max(1, len(lines)))

    @staticmethod
    def _low_quality_reason(text: str, metadata: Dict[str, Any]) -> Optional[str]:
        raw_text = str(text or "")
        lowered = raw_text.lower()
        tokens = VectorStore._tokenize_words(raw_text)
        word_count = sum(1 for tok in tokens if re.search(r"[A-Za-z\u0600-\u06FF]", tok))

        if re.search(r"\b(table\s+of\s+contents|brief\s+contents|contents)\b", lowered):
            return "toc_like"

        numeric_tokens = sum(1 for tok in tokens if tok.isdigit())
        numeric_ratio = numeric_tokens / float(max(1, len(tokens)))
        if len(tokens) >= 16 and numeric_ratio >= 0.35:
            return "number_heavy"

        if word_count < 40:
            return "too_short"

        heading_ratio = VectorStore._heading_dominance_ratio(raw_text)
        if heading_ratio >= 0.60:
            return "heading_dominated"

        if VectorStore._ocr_garbage_ratio(raw_text) >= 0.45:
            return "ocr_garbage"

        if VectorStore._is_toc_like(raw_text, metadata or {}):
            return "toc_index_like"

        return None

    @staticmethod
    def _content_density_score(text: str) -> float:
        raw_text = str(text or "")
        tokens = VectorStore._tokenize_words(raw_text)
        if not tokens:
            return 0.0

        alpha_tokens = [tok for tok in tokens if re.search(r"[A-Za-z\u0600-\u06FF]", tok)]
        if not alpha_tokens:
            return 0.0

        meaningful = sum(1 for tok in alpha_tokens if len(tok) > 4)
        meaningful_ratio = meaningful / float(max(1, len(alpha_tokens)))

        sentence_markers = len(re.findall(r"[\.:]", raw_text))
        sentence_signal = min(1.0, sentence_markers / 3.0)

        score = (0.7 * meaningful_ratio) + (0.3 * sentence_signal)
        return float(max(0.0, min(1.0, score)))

    @staticmethod
    def _has_real_sentence_structure(text: str) -> bool:
        raw_text = str(text or "")
        if raw_text.count(".") < 2:
            return False
        words = [tok for tok in VectorStore._tokenize_words(raw_text) if re.search(r"[A-Za-z\u0600-\u06FF]", tok)]
        if len(words) < 40:
            return False
        if VectorStore._heading_dominance_ratio(raw_text) >= 0.55:
            return False
        return True

    @staticmethod
    def _dedup_key(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip().lower())

    @staticmethod
    def _select_top_high_quality(candidates: List[Dict[str, Any]], max_items: int = 3) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        seen = set()

        for cand in candidates:
            text = str(cand.get("text") or cand.get("page_content") or "")
            key = VectorStore._dedup_key(text)
            if not key or key in seen:
                continue
            if not VectorStore._has_real_sentence_structure(text):
                continue
            seen.add(key)
            selected.append(cand)
            if len(selected) >= max_items:
                break

        return selected

    @staticmethod
    def _chunk_role_bonus(chunk_role: str, profile: Dict[str, bool]) -> float:
        role = str(chunk_role or "").strip().lower()
        if not role:
            return 0.0
        if profile.get("structure_query"):
            if role == "toc":
                return 0.22
            if role in {"chapter_heading", "section_heading", "chapter_intro", "summary", "introduction", "key_terms"}:
                return 0.18
            if role == "reference":
                return -0.55
        if profile.get("overview_query"):
            if role in {"introduction", "summary", "key_terms", "chapter_intro", "toc"}:
                return 0.12
            if role == "reference":
                return -0.50
        if role == "reference":
            return -0.30
        return 0.0

    @staticmethod
    def _content_richness_bonus(text: str) -> float:
        txt = str(text or "").strip()
        if not txt:
            return -0.15
        words = txt.split()
        sentences = [s for s in re.split(r"(?<=[.!?؟])\s+", txt) if s.strip()]
        word_bonus = min(0.10, max(0.0, (len(words) - 70) / 1200.0))
        sentence_bonus = min(0.08, len(sentences) * 0.01)
        return word_bonus + sentence_bonus

    @staticmethod
    def _structure_marker_bonus(text: str, metadata: Dict[str, Any], profile: Dict[str, bool]) -> float:
        txt = str(text or "")[:1200]
        txt_l = txt.lower()
        md = metadata or {}
        section = str(md.get("section", "") or "")
        title = str(md.get("title", "") or "")
        chapter = str(md.get("chapter", "") or "")
        hay = f"{section}\n{title}\n{chapter}\n{txt_l}"

        bonus = 0.0
        has_chapter = bool(re.search(r"\bchapter\s+\d+\b", hay, re.IGNORECASE))
        has_numeric_section = bool(re.search(r"\b\d+(?:\.\d+){1,3}\b", hay))
        has_toc = any(t in txt_l for t in ["table of contents", "contents", "brief contents"])
        has_intro_summary = any(t in txt_l for t in ["introduction", "summary", "key terms", "key concepts"])

        if profile.get("structure_query"):
            if has_chapter:
                bonus += 0.16
            if has_numeric_section:
                bonus += 0.08
            if has_toc:
                bonus += 0.10
            if not (has_chapter or has_numeric_section or has_toc):
                bonus -= 0.14
        if profile.get("overview_query") and has_intro_summary:
            bonus += 0.12

        return bonus

    def add_chunks(self, chunks: List[DocumentChunk]):
        if not chunks:
            return

        texts = [c.text for c in chunks]
        embedding_docs = [self._to_e5_passage(t) for t in texts]
        metadatas = [
            {
                "page": c.page,
                "section": c.section,
                "section_title": c.section_title,
                "chapter": c.chapter,
                "title": c.title,
                "detected_entity": (c.detected_entity or ""),
                "chunk_role": c.chunk_role,
                "document_type": c.document_type,
                "source": c.source,
                "chunk_id": c.chunk_id,
                "timestamp": c.timestamp,
                "embedding_model": EMBEDDING_MODEL,
            }
            for c in chunks
        ]
        ids = [c.chunk_id for c in chunks]

        # Batch encode
        embeddings = self.embedding_model.encode(embedding_docs, batch_size=BATCH_SIZE, show_progress_bar=False)

        # Upsert (log metadata only — no behavior changes)
        logger.info("[INGESTION UPSERT] preparing upsert | chunks=%s ids_sample=%s", len(chunks), ids[:6])
        self.collection.upsert(
            documents=texts,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
            ids=ids
        )
        logger.info(f"Inserted {len(chunks)} chunks into Vector DB.")
    def search(self, query: str, top_k: int = 5, distance_threshold: float = 1.0, filter_meta: Dict[str, Any] = None, return_dicts: bool = False, enable_rerank: bool = True):
        """Perform semantic search with structural boosting and optional reranking."""
        requested_top_k = int(top_k or 1)
        top_k = max(1, min(requested_top_k, 120))
        logger.info("[TOPK TRACE] requested=%s actual=%s function=VectorStore.search", requested_top_k, top_k)
        normalized_query = self._normalize_query_text(query)
        query_for_embedding = self._to_e5_query(normalized_query)
        query_profile = self._query_profile(normalized_query)
        if enable_rerank:
            logger.info("[RERANK ACTIVE]")
        
        logger.info(f"[RAG] Search: '{normalized_query}' | top_k={top_k}")

        query_embedding = self.embedding_model.encode([query_for_embedding], show_progress_bar=False)[0]
        
        # Lower candidate pool for faster retrieval latency while keeping
        # enough recall for downstream ranking.
        candidate_pool = max(40, min(240, top_k * 4))

        results = None
        last_query_exception = None

        for attempt_pool in (candidate_pool, 15, 10, 5):
            try:
                logger.info(f"[RAG] attempting chroma.query n_results={attempt_pool}")
                results = self.collection.query(
                    query_embeddings=[query_embedding.tolist()],
                    n_results=attempt_pool,
                    where=filter_meta
                )
                logger.info(f"[RAG] chroma.query succeeded with n_results={attempt_pool}")
                break
            except Exception as query_err:
                last_query_exception = query_err
                msg = str(query_err).lower()
                logger.warning(f"Chroma query attempt (n_results={attempt_pool}) failed: {query_err}")
                # If the error message suggests an HNSW/contiguous-array limitation,
                # continue to try with smaller pools. Otherwise also try smaller
                # pools but keep logging the exception.
                continue

        if results is None:
            logger.warning(f"All Chroma query attempts failed; falling back to manual retrieval. last_err={last_query_exception}")
            try:
                results = self._manual_query_fallback(query_embedding, candidate_pool, filter_meta)
            except Exception as fb_err:
                logger.error(f"Manual fallback also failed: {fb_err}")
                # Final safe return: no candidates
                results = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        
        candidates = []
        # Robustly read Chroma-style nested results by aligning indices across
        # documents, metadatas, distances and ids. This guarantees each candidate
        # keeps its chunk text, metadata and score together.
        if results and "documents" in results and len(results["documents"]) > 0:
            documents = results.get("documents", [[]])[0] if results.get("documents") else []
            metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
            distances = results.get("distances", [[]])[0] if results.get("distances") else []
            ids = results.get("ids", [[]])[0] if results.get("ids") else []

            # Use the minimum length to avoid index mismatches
            max_i = min(len(documents), len(metadatas) if metadatas is not None else len(documents), len(distances) if distances is not None else len(documents))
            if max_i == 0:
                max_i = len(documents)

            for i in range(max_i):
                doc_item = documents[i] if i < len(documents) else None
                meta_item = metadatas[i] if i < len(metadatas) else {}
                dist = distances[i] if i < len(distances) else 0.5
                cid = ids[i] if i < len(ids) else (meta_item.get("chunk_id") if isinstance(meta_item, dict) and meta_item.get("chunk_id") else f"id_{i}")

                if doc_item is None:
                    continue

                sim = 1.0 - float(dist)

                # Apply structural boosts (moderate)
                target_chapter_num = query_profile.get("chapter_num")
                if target_chapter_num is not None:
                    chunk_chapter = str(meta_item.get("chapter", "")).lower() if isinstance(meta_item, dict) else ""
                    if f"chapter {target_chapter_num}" in chunk_chapter or f"unit {target_chapter_num}" in chunk_chapter:
                        sim += 0.15
                    elif f"section {target_chapter_num}." in str(meta_item.get("section", "")).lower() if isinstance(meta_item, dict) else False:
                        sim += 0.10

                # Simplified and correct extraction of chunk text from Chroma results.
                # Chroma typically returns documents as a list-of-list of strings:
                # results['documents'] = [["chunk1", "chunk2", ...]]
                # So treat strings as strings (not sequences) to avoid splitting
                # into characters.
                chunk_text = ""

                # CASE 1: normal Chroma string
                if isinstance(doc_item, str):
                    chunk_text = doc_item

                # CASE 2: dict-like object
                elif isinstance(doc_item, dict):
                    chunk_text = (
                        doc_item.get("text")
                        or doc_item.get("content")
                        or doc_item.get("page_content")
                        or ""
                    )

                # CASE 3: list/tuple (rare) — prefer first element
                elif isinstance(doc_item, (list, tuple)):
                    if len(doc_item) > 0:
                        first = doc_item[0]
                        if isinstance(first, str):
                            chunk_text = first
                        else:
                            chunk_text = str(first)

                # FINAL FALLBACK
                if not chunk_text or not str(chunk_text).strip():
                    chunk_text = str(doc_item)

                candidates.append({
                    "text": chunk_text,
                    "page_content": chunk_text,
                    "content": chunk_text,
                    "metadata": meta_item or {},
                    "id": cid,
                    "distance": float(dist),
                    "similarity": float(sim),
                    "score": float(sim),
                    # TRACE fields to guarantee alignment through sorting/transfer
                    "trace_page": (meta_item.get("page") if isinstance(meta_item, dict) else None),
                    "trace_chunk_index": (meta_item.get("chunk_index") if isinstance(meta_item, dict) else None),
                    "trace_id": cid,
                    "trace_preview": (chunk_text[:120] if chunk_text else ""),
                })
        logger.info("[DOC COUNT TRACE] stage=VectorStore.search.candidates_raw count=%s", len(candidates))

        # --- STEP: RERANKING (optional) ---
        if enable_rerank and self.reranker and candidates:
            logger.info(f"[RAG] Reranking {len(candidates)} candidates for query: '{normalized_query}'")
            # Create pairs for cross-encoder
            pairs = [[normalized_query, c["text"]] for c in candidates]
            rerank_scores = self.reranker.predict(pairs)

            for i, score in enumerate(rerank_scores):
                candidates[i]["rerank_score"] = float(score)
                # keep similarity separately; use rerank_score as semantic refinement
                candidates[i]["score"] = float(score)

        before_filter_candidates = list(candidates)
        dropped_chunks: List[Dict[str, Any]] = []

        quality_filtered: List[Dict[str, Any]] = []
        for cand in candidates:
            text = str(cand.get("text") or cand.get("page_content") or "")
            metadata = dict(cand.get("metadata") or {})
            reason = self._low_quality_reason(text, metadata)
            if reason:
                dropped_chunks.append(
                    {
                        "reason": reason,
                        "score": float(cand.get("score", 0.0) or 0.0),
                        "text": text,
                        "id": cand.get("id"),
                    }
                )
                continue
            quality_filtered.append(cand)

        if quality_filtered:
            candidates = quality_filtered
        else:
            logger.info("[RAG QUALITY FILTER] all candidates filtered; falling back to original list")
            candidates = before_filter_candidates

        for cand in candidates:
            if cand.get("reranker_score") is not None:
                semantic_score = float(cand.get("reranker_score"))
            elif cand.get("rerank_score") is not None:
                semantic_score = float(cand.get("rerank_score"))
            else:
                semantic_score = float(cand.get("similarity", 0.0) or 0.0)

            content_density = self._content_density_score(cand.get("text") or cand.get("page_content") or "")
            final_score = (semantic_score * 0.7) + (content_density * 0.3)

            cand["semantic_score_used"] = float(semantic_score)
            cand["content_density"] = float(content_density)
            cand["final_score"] = float(final_score)
            cand["score"] = float(final_score)

        candidates.sort(key=lambda item: item.get("final_score", 0.0), reverse=True)

        max_selected = max(1, min(3, top_k))
        selected_high_quality = self._select_top_high_quality(candidates, max_items=max_selected)
        if selected_high_quality:
            final_results = selected_high_quality
        else:
            final_results = candidates[:max_selected]

        self.last_search_debug = {
            "query": normalized_query,
            "before_count": len(before_filter_candidates),
            "after_count": len(candidates),
            "filtered_count": len(dropped_chunks),
            "before_top": [
                {
                    "score": float(doc.get("similarity", doc.get("score", 0.0)) or 0.0),
                    "text": str(doc.get("text") or doc.get("page_content") or ""),
                    "id": doc.get("id"),
                }
                for doc in before_filter_candidates[:8]
            ],
            "dropped": dropped_chunks,
            "selected": [
                {
                    "score": float(doc.get("final_score", 0.0) or 0.0),
                    "text": str(doc.get("text") or doc.get("page_content") or ""),
                    "id": doc.get("id"),
                }
                for doc in final_results
            ],
        }

        logger.info(
            "[RAG QUALITY FILTER] before=%s after=%s dropped=%s selected=%s",
            len(before_filter_candidates),
            len(candidates),
            len(dropped_chunks),
            len(final_results),
        )
        for dropped in dropped_chunks[:10]:
            logger.info(
                "[RAG QUALITY DROP] reason=%s score=%.4f preview=%s",
                dropped.get("reason"),
                float(dropped.get("score", 0.0) or 0.0),
                str(dropped.get("text") or "")[:180].replace("\n", " "),
            )

        logger.info("[DOC COUNT TRACE] stage=VectorStore.search.final_results count=%s", len(final_results))

        # Enhanced debug logging for top results
        for i, res in enumerate(final_results[:min(10, len(final_results))]):
            logger.info(
                "[RAG Result %d] semantic=%.4f | density=%.4f | final=%.4f | Page=%s | Source=%s",
                i + 1,
                res.get("semantic_score_used", 0.0),
                res.get("content_density", 0.0),
                res.get("final_score", 0.0),
                res.get("metadata", {}).get("page"),
                res.get("metadata", {}).get("source"),
            )

        # Hard assertion: top result must contain actual text (debugging guard)
        if final_results:
            try:
                assert final_results[0].get("page_content"), "final_results[0] has empty page_content"
            except AssertionError as ae:
                logger.error("[FINAL ASSERT FAIL] final_results[0] missing page_content")
                raise

        if return_dicts:
            logger.info("[DOC COUNT TRACE] stage=VectorStore.search.return_dicts count=%s", len(final_results))
            return final_results

        logger.info("[DOC COUNT TRACE] stage=VectorStore.search.return_text count=%s", len(final_results))
        return [c["text"] for c in final_results]




# ================= PIPELINE CLASS =================
class AdaptiveRAGPipeline:
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        self.debug_mode = False

    def enable_debug(self):
        self.debug_mode = True
        logger.setLevel(logging.DEBUG)

    # --- STEP 1 & 2: PDF TYPE DETECTION & OCR ---
    def _clean_text(self, text: str) -> str:
        """Normalize whitespace and fix common OCR/PDF artifacts."""
        if not text:
            return ""
        # Fix broken spaces in words (e.g., "P s y c h o l o g y" -> "Psychology")
        # This is high-risk, so we only do it for single characters separated by spaces
        text = re.sub(r'(?<=\b[A-Za-z])\s(?=[A-Za-z]\b)', '', text)
        # Normalize multiple spaces and newlines
        text = re.sub(r'\s+', ' ', text)
        # Fix merged words (basic check)
        # text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        return text.strip()

    # --- STEP 1 & 2: PDF TYPE DETECTION & OCR ---
    def extract_text_from_pdf(self, file_path: str) -> List[Dict[str, Any]]:
        pages = []
        try:
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                logger.info(f"Extracting {total_pages} pages using pdfplumber")
                
                for page_num, page in enumerate(pdf.pages, start=1):
                    start_time = time.time()
                    
                    # Layout-aware text extraction
                    text = page.extract_text(layout=True) or ""
                    
                    # Step 1: Detect Scanned PDF or poor extraction
                    if len(text.strip()) < 100:
                        logger.info(f"Page {page_num} text too sparse ({len(text.strip())} chars) — attempting OCR")
                        if pytesseract and convert_from_path:
                            try:
                                # Step 2: OCR Extraction (fallback)
                                images = convert_from_path(file_path, first_page=page_num, last_page=page_num)
                                if images:
                                    text = pytesseract.image_to_string(images[0])
                            except Exception as e:
                                logger.error(f"OCR failed for page {page_num}: {e}")
                        else:
                            logger.warning("OCR tools (pytesseract/pdf2image) not installed!")
                    
                    ocr_time = time.time() - start_time
                    if self.debug_mode:
                        logger.debug(f"Extracted page {page_num} in {ocr_time:.2f}s")

                    # Step 3: Page Structure Preservation
                    pages.append({
                        "page": page_num,
                        "text": text,
                        "raw_text": text # preserve original for structural analysis
                    })
        except Exception as e:
            logger.error(f"Failed to process PDF {file_path}: {e}")
            # Fallback to PyPDF2 if pdfplumber fails
            try:
                reader = PyPDF2.PdfReader(file_path)
                for i, page in enumerate(reader.pages):
                    pages.append({"page": i+1, "text": page.extract_text() or ""})
            except Exception as e2:
                logger.error(f"All PDF extraction methods failed: {e2}")
        return pages

    # --- STEP 4: DOCUMENT STRUCTURE DETECTION ---
    def extract_structure(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        structured_pages = []
        current_section = "Front Matter"
        
        # A more strict pattern for Chapter/Unit bodies
        section_pattern = re.compile(r"^(Chapter\s+\d+|Unit\s+\d+|Section\s+\d+\.\d+|\d+\.\s+[A-Z])", re.IGNORECASE)
        toc_line_pattern = re.compile(r"(\.{3,}|\s+\d+$)")
        
        in_toc = False
        
        for p in pages:
            lines = p["text"].split("\n")
            
            # Heuristic to detect TOC pages (multiple dotted leaders or page numbers)
            toc_indicators = 0
            for line in lines:
                if re.search(r"\.{3,}\s*\d+", line) or re.search(r"(?i)\bTable of Contents\b", line):
                    toc_indicators += 1
            if toc_indicators >= 2:
                in_toc = True
            elif in_toc and toc_indicators == 0 and p["page"] > 10:
                in_toc = False
                
            page_section = current_section
            if in_toc:
                page_section = "Table of Contents"
                
            processed_lines = []
            
            for line in lines:
                clean_line = line.strip()
                
                if not in_toc:
                    match = section_pattern.match(clean_line)
                    # Exclude TOC-like lines that might have bled into body
                    if match and not toc_line_pattern.search(clean_line):
                        if len(clean_line) < 100:
                            current_section = match.group(0).strip()
                            clean_chapter_match = re.match(r"^((?:Chapter|Unit)\s+\d+)", current_section, re.IGNORECASE)
                            if clean_chapter_match:
                                current_section = clean_chapter_match.group(1).title()  # E.g., "Chapter 6" or "Unit 2"
                            page_section = current_section
                            
                processed_lines.append(line)
                
            structured_pages.append({
                "page": p["page"],
                "text": "\n".join(processed_lines),
                "section": page_section
            })
            
        return structured_pages

    # --- STEP 5: DOCUMENT TYPE CLASSIFICATION ---
    def classify_document(self, text_content: str) -> str:
        text_content_lower = text_content.lower()
        if "abstract" in text_content_lower and "references" in text_content_lower:
            return "Research paper"
        elif "chapter 1" in text_content_lower or "table of contents" in text_content_lower:
            return "Book"
        elif "terms and conditions" in text_content_lower or "agreement" in text_content_lower:
            return "Legal document"
        elif "manual" in text_content_lower or "instructions" in text_content_lower:
            return "Manual"
        elif "report" in text_content_lower:
            return "Report"
        return "Unknown"

    # --- STEP 6: SMART CHUNKING ---
    def smart_chunking(self, structured_pages: List[Dict], doc_type: str, file_name: str) -> List[DocumentChunk]:
        chunks = []

        MIN_CHUNK_WORDS = 200
        MAX_CHUNK_WORDS = 300
        TARGET_CHUNK_WORDS = 240
        OVERLAP_WORDS = 25

        heading_re = re.compile(r"^(?:chapter\s+\d+|unit\s+\d+|section\s+\d+(?:\.\d+)?|\d+(?:\.\d+)*\s+.+)$", re.I)
        bullet_re = re.compile(r"^\s*(?:[-•*]|\d+[.)])\s+")
        table_sep_re = re.compile(r"^\s*[+\-|=]{3,}\s*$")
        definition_res = [
            re.compile(r"^\s*([A-Za-z][A-Za-z0-9\s\-()/]{1,90}?)\s+is\s+", re.I),
            re.compile(r"^\s*([A-Za-z][A-Za-z0-9\s\-()/]{1,90}?)\s+refers\s+to\s+", re.I),
            re.compile(r"^\s*([A-Za-z][A-Za-z0-9\s\-()/]{1,90}?)\s+can\s+be\s+defined\s+as\s+", re.I),
        ]

        def _word_count(text: str) -> int:
            return len(re.findall(r"\S+", text or ""))

        def _tail_words(text: str, n_words: int) -> str:
            words = re.findall(r"\S+", text or "")
            return " ".join(words[-n_words:]) if words else ""

        def _split_to_word_windows(text: str) -> List[str]:
            words = re.findall(r"\S+", text or "")
            if not words:
                return []
            out = []
            start = 0
            step = max(1, TARGET_CHUNK_WORDS - OVERLAP_WORDS)
            while start < len(words):
                end = min(start + TARGET_CHUNK_WORDS, len(words))
                out.append(" ".join(words[start:end]).strip())
                if end >= len(words):
                    break
                start += step
            return [x for x in out if x]

        def _is_heading_line(line: str) -> bool:
            if not line:
                return False
            s = line.strip()
            if not s:
                return False
            if heading_re.match(s):
                return True
            wc = _word_count(s)
            if 2 <= wc <= 10 and s == s.upper() and re.search(r"[A-Z]", s) and not s.endswith((",", ".", ";", "?", "!")):
                return True
            return False

        def _detect_definition_entity(text: str) -> Optional[str]:
            if not text:
                return None
            snippet = text.strip().split("\n", 1)[0].strip()
            blocked_singletons = {"this", "that", "it", "these", "those", "there", "they", "he", "she", "we", "you", "i"}
            for rx in definition_res:
                match = rx.match(snippet)
                if match:
                    entity = match.group(1).strip(" -:;,.\t")
                    entity_words = re.findall(r"[A-Za-z0-9]+", entity)
                    if len(entity_words) == 1 and entity_words[0].lower() in blocked_singletons:
                        return None
                    return entity
            return None

        def _is_table_line(line: str) -> bool:
            s = line.strip()
            if not s:
                return False
            if s.count("|") >= 2:
                return True
            if table_sep_re.match(s):
                return True
            if len(re.findall(r"\s{2,}", s)) >= 2 and _word_count(s) >= 4:
                return True
            return False

        def _topic_key(unit: Dict[str, Any]) -> str:
            if unit["kind"] == "definition":
                return f"definition::{(unit.get('detected_entity') or '').lower()}"
            return f"{unit['kind']}::{(unit.get('section_title') or '').lower()}"

        def _emit_chunk_text(text: str, base: Dict[str, Any], chunk_role: str = "content"):
            for part in _split_to_word_windows(text):
                if not part.strip():
                    continue
                meta_prefix = (
                    f"[Source: {file_name} | Page: {base['page']} | {base['chapter']} | "
                    f"{base['section']} | {base['section_title']}] "
                )
                chunks.append(DocumentChunk(
                    text=meta_prefix + part,
                    page=base["page"],
                    chapter=base["chapter"],
                    section=base["section"],
                    section_title=base["section_title"],
                    title=base["section_title"],
                    detected_entity=base.get("detected_entity"),
                    chunk_role=chunk_role,
                    document_type=doc_type,
                    source=file_name
                ))

        current_chapter = "Unknown"
        current_section = "Unknown"
        current_section_title = "Unknown"
        units: List[Dict[str, Any]] = []

        def _append_unit(text: str, page: int, kind: str, chapter: str, section: str, section_title: str):
            cleaned = self._clean_text(text).strip()
            if not cleaned:
                return
            detected_entity = _detect_definition_entity(cleaned)
            units.append({
                "text": cleaned,
                "page": page,
                "chapter": chapter,
                "section": section,
                "section_title": section_title,
                "kind": "definition" if detected_entity else kind,
                "detected_entity": detected_entity,
            })

        for p in structured_pages:
            page_num = p["page"]
            page_section = (p.get("section") or current_section or "Unknown").strip() or "Unknown"
            text = p.get("text", "")
            lines = [ln.rstrip() for ln in text.split("\n")]

            if page_section:
                current_section = page_section
                current_section_title = page_section

            i = 0
            while i < len(lines):
                raw_line = lines[i]
                line = raw_line.strip()
                if not line:
                    i += 1
                    continue

                chap_match = re.search(r"\bChapter\s+(\d+)\b", line, re.I)
                if chap_match:
                    current_chapter = f"Chapter {chap_match.group(1)}"

                sec_match = re.search(r"\bSection\s+(\d+(?:\.\d+)?)\b", line, re.I)
                if sec_match:
                    current_section = f"Section {sec_match.group(1)}"

                if _is_heading_line(line):
                    current_section_title = line[:180]
                    i += 1
                    continue

                if _is_table_line(line):
                    table_lines = [line]
                    j = i + 1
                    while j < len(lines):
                        nxt = lines[j].strip()
                        if not nxt or not _is_table_line(nxt):
                            break
                        table_lines.append(nxt)
                        j += 1
                    _append_unit("\n".join(table_lines), page_num, "table", current_chapter, current_section, current_section_title)
                    i = j
                    continue

                if bullet_re.match(line):
                    bullet_lines = [line]
                    j = i + 1
                    while j < len(lines):
                        nxt = lines[j].strip()
                        if not nxt or not bullet_re.match(nxt):
                            break
                        bullet_lines.append(nxt)
                        j += 1
                    _append_unit("\n".join(bullet_lines), page_num, "bullet", current_chapter, current_section, current_section_title)
                    i = j
                    continue

                para_lines = [line]
                j = i + 1
                while j < len(lines):
                    nxt = lines[j].strip()
                    if not nxt or _is_heading_line(nxt) or _is_table_line(nxt) or bullet_re.match(nxt):
                        break
                    para_lines.append(nxt)
                    j += 1
                _append_unit(" ".join(para_lines), page_num, "paragraph", current_chapter, current_section, current_section_title)
                i = j

        current_units: List[Dict[str, Any]] = []
        current_words = 0
        current_key = ""
        current_kind = ""

        def _flush_current():
            nonlocal current_units, current_words, current_key, current_kind
            if not current_units:
                return
            chunk_text = " ".join(u["text"] for u in current_units).strip()
            if not chunk_text:
                current_units = []
                current_words = 0
                current_key = ""
                current_kind = ""
                return
            base = current_units[0]
            role = "definition" if base.get("kind") == "definition" else "content"
            _emit_chunk_text(chunk_text, base, chunk_role=role)
            current_units = []
            current_words = 0
            current_key = ""
            current_kind = ""

        for unit in units:
            unit_words = _word_count(unit["text"])
            if unit_words == 0:
                continue

            unit_key = _topic_key(unit)
            unit_kind = unit["kind"]

            if not current_units:
                current_units = [unit]
                current_words = unit_words
                current_key = unit_key
                current_kind = unit_kind
                continue

            must_separate = (
                unit_key != current_key
                or unit_kind != current_kind
                or (unit_kind == "definition" or current_kind == "definition")
                or (unit_kind == "table" or current_kind == "table")
            )

            if must_separate:
                _flush_current()
                current_units = [unit]
                current_words = unit_words
                current_key = unit_key
                current_kind = unit_kind
                continue

            if current_words + unit_words <= MAX_CHUNK_WORDS:
                current_units.append(unit)
                current_words += unit_words
                continue

            prev_text = " ".join(u["text"] for u in current_units).strip()
            _flush_current()

            if current_kind not in {"definition", "table"}:
                overlap_text = _tail_words(prev_text, OVERLAP_WORDS)
                if overlap_text:
                    current_units = [{
                        "text": overlap_text,
                        "page": unit["page"],
                        "chapter": unit["chapter"],
                        "section": unit["section"],
                        "section_title": unit["section_title"],
                        "kind": unit_kind,
                        "detected_entity": unit.get("detected_entity"),
                    }]
                    current_words = _word_count(overlap_text)
                    current_key = unit_key
                    current_kind = unit_kind
                else:
                    current_units = []
                    current_words = 0
                    current_key = ""
                    current_kind = ""

            if not current_units:
                current_units = [unit]
                current_words = unit_words
                current_key = unit_key
                current_kind = unit_kind
            else:
                if current_words + unit_words <= MAX_CHUNK_WORDS:
                    current_units.append(unit)
                    current_words += unit_words
                else:
                    _flush_current()
                    current_units = [unit]
                    current_words = unit_words
                    current_key = unit_key
                    current_kind = unit_kind

        _flush_current()

        # Final pass: ensure chunks over max words are already split and tiny chunks only remain for isolated units.
        if chunks:
            logger.info("Chunking complete: %s chunks (target=%s words, max=%s, overlap=%s)", len(chunks), TARGET_CHUNK_WORDS, MAX_CHUNK_WORDS, OVERLAP_WORDS)
            below_target = sum(1 for c in chunks if _word_count(c.text) < MIN_CHUNK_WORDS)
            logger.info("Chunking stats: chunks_below_200_words=%s", below_target)

        return chunks
    # --- STEP 11: QUERY UNDERSTANDING ---
    def analyze_query(self, query: str) -> Dict[str, Any]:
        intent = "search"
        if query.lower().startswith("summarize"):
            intent = "summarization"
        elif query.lower().startswith("compare"):
            intent = "comparison"
        elif query.lower().startswith("define") or query.lower().startswith("what is"):
            intent = "definition"
            
        # Extract section if mentioned
        section_filter = None
        match = re.search(r"(chapter \d+|section \d+)", query.lower())
        if match:
            section_filter = match.group(1)
            
        return {
            "intent": intent,
            "section_filter": section_filter
        }

    # --- MAIN INGESTION ---
    def ingest_pdf(self, file_path: str):
        t0 = time.time()
        file_name = os.path.basename(file_path)
        logger.info(f"Starting ingestion for {file_name}")
        
        # Step 1, 2, 3
        pages = self.extract_text_from_pdf(file_path)
        if not pages:
            logger.error("No pages extracted. Aborting.")
            return

        # Step 4
        structured_pages = self.extract_structure(pages)
        
        # Step 5
        full_text = "\n".join([p["text"] for p in structured_pages[:5]]) # use first few pages for classification
        doc_type = self.classify_document(full_text)
        logger.info(f"Document classified as: {doc_type}")
        
        # Step 6, 7
        chunks = self.smart_chunking(structured_pages, doc_type, file_name)
        for idx, ch in enumerate(chunks[:5], start=1):
            preview = ch.text.replace("\n", " ")[:220]
            logger.info(
                "[INGEST DEBUG] chunk_%s | page=%s | section_title=%s | detected_entity=%s | words=%s | preview=%s",
                idx,
                ch.page,
                ch.section_title,
                ch.detected_entity,
                len(re.findall(r"\S+", ch.text)),
                preview,
            )
        
        # Step 8, 9
        self.vector_store.add_chunks(chunks)
        
        t1 = time.time()
        logger.info(f"Ingested {file_name}: {len(pages)} pages, {len(chunks)} chunks in {t1-t0:.2f}s")
        
        if self.debug_mode:
            logger.debug(f"[DEBUG] Average chunk size: {sum(len(c.text) for c in chunks)/len(chunks):.0f} characters")

    # --- STEP 10 & 12: RETRIEVAL & CONTEXT ASSEMBLY ---
    def retrieve_context(self, query: str, top_k: int = 5) -> str:
        t0 = time.time()
        
        # Step 11
        query_analysis = self.analyze_query(query)
        filter_meta = None
        
        # Example filter application
        if query_analysis["section_filter"]:
            # Note: exact match in chromadb, might need adjustment based on exact section formats
            # filter_meta = {"section": {"$ilike": f"%{query_analysis['section_filter']}%"}} 
            pass  # Simplified for robust execution

        results = self.vector_store.search(query, top_k=top_k, threshold=0.1, filter_meta=filter_meta)
        
        # Step 12: Context assembly
        assembled_context = []
        total_tokens = 0
        
        for res in results:
            text = res["text"]
            meta = res["metadata"]
            assembled_context.append(f"--- [Doc: {meta['source']} | Page: {meta['page']} | Section: {meta['section']}] ---\n{text}")
            total_tokens += len(text.split()) # rough token estimate
            
        t1 = time.time()
        
        logger.info(f"Retrieved {len(results)} chunks in {t1-t0:.2f}s (approx {total_tokens} tokens sent to LLM)")
        if self.debug_mode:
            for r in results:
                logger.debug(f"[DEBUG] Match score: {r['similarity']:.3f}, Meta: {r['metadata']}")

        return "\n\n".join(assembled_context)


# ================= STEP 13: SYSTEM DIAGNOSTICS =================
def analyze_rag_pipeline(vector_store: VectorStore):
    print("\n" + "="*50)
    print("RAG PIPELINE SYSTEM DIAGNOSTICS")
    print("="*50)
    
    try:
        col = vector_store.collection
        count = col.count()
        print(f"Total chunks stored     : {count}")
        
        if count > 0:
            sample = col.peek(limit=count)
            sources = set(m["source"] for m in sample["metadatas"] if m and "source" in m)
            doc_types = set(m["document_type"] for m in sample["metadatas"] if m and "document_type" in m)
            
            print(f"Total documents         : {len(sources)}")
            print(f"Document types detected : {', '.join(doc_types)}")
            if sample["metadatas"] and len(sample["metadatas"]) > 0:
                print(f"Metadata fields used    : {list(sample['metadatas'][0].keys())}")
        
        print("Retrieval Config        : top_k=5, threshold=0.5, metrics=cosine")
        print("System Health Status    : ONLINE")
    except Exception as e:
        print(f"System Health Status    : ERROR ({e})")
    
    print("="*50 + "\n")


if __name__ == "__main__":
    # Quick Test Execution
    store = VectorStore()
    pipeline = AdaptiveRAGPipeline(store)
    pipeline.enable_debug()
    
    test_pdf = os.path.join("archived_pdfs", "1_sequence_diagram.pdf")
    if os.path.exists(test_pdf):
        pipeline.ingest_pdf(test_pdf)
        print("\n--- Testing Retrieval ---")
        context = pipeline.retrieve_context("sequence diagram")
        print(context)
    
    analyze_rag_pipeline(store)
