# knowledge_base.py - RAG Knowledge Base with ChromaDB (FIXED)
import os
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY_IMPL'] = 'none'

import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path

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
    CHROMA_DB_PATH = Path(__file__).resolve().parent / "chroma_db"
    EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KnowledgeBase")

# Initialize ChromaDB (persistent storage)
client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))

# Initialize embedding model (lightweight, fast) — forced to CPU to save GPU VRAM
embedder = SentenceTransformer(EMBEDDING_MODEL, device='cpu')

def get_or_create_collection():
    """Get collection or create if doesn't exist"""
    try:
        collection = client.get_or_create_collection(name="support_docs")
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
            
        embedding = embedder.encode(text).tolist()
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


def chunk_and_add_document(doc_id: str, text: str, metadata: dict = None, kb_version: int = 0) -> int:
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

    Args:
        doc_id: Base document identifier (chunk suffix appended automatically).
        text: Full document text to chunk and embed.
        metadata: Optional extra metadata merged into every chunk's metadata.
        kb_version: Global KB version counter at the time of indexing (for audit).

    Returns the number of chunks successfully indexed.
    """
    import re as _re
    from datetime import datetime as _dt

    # Normalise Windows line-endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Step 1: split on blank lines
    paragraphs = _re.split(r'\n{2,}', text)

    chunks: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > 400:
            # Step 2: split long paragraph on single newlines
            for line in para.split('\n'):
                line = line.strip()
                if line:
                    chunks.append(line)
        else:
            chunks.append(para)

    # Step 3: drop trivially short chunks
    chunks = [c for c in chunks if len(c) >= 10]

    if not chunks:
        logger.warning(f"chunk_and_add_document: no usable chunks from doc_id={doc_id}")
        return 0

    collection = get_or_create_collection()
    if not collection:
        return 0

    success = 0
    now_iso = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    for idx, chunk in enumerate(chunks):
        chunk_id = f"{doc_id}_chunk_{idx}"
        chunk_meta = dict(metadata or {})
        chunk_meta["chunk_index"] = idx
        chunk_meta["chunk_total"] = len(chunks)
        chunk_meta["updated_at"] = now_iso
        chunk_meta["kb_version"] = kb_version
        try:
            embedding = embedder.encode(chunk).tolist()
            # upsert instead of add so re-indexing an existing file never
            # raises a duplicate-ID error — it simply overwrites the old entry.
            collection.upsert(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk],
                metadatas=[chunk_meta],
            )
            success += 1
        except Exception as e:
            logger.error(f"Error upserting chunk {chunk_id}: {e}")

    logger.info(f"✓ Indexed {success}/{len(chunks)} chunks for doc_id={doc_id}")
    return success

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
        normalised_query = query.strip().lower()
        query_embedding = embedder.encode(normalised_query).tolist()
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
        collection = get_or_create_collection()
        if not collection:
            return 0

        # Get all ids and filter by prefix
        # NOTE: "ids" must NOT be in include — ChromaDB always returns ids automatically
        # and raises ValueError if you explicitly request them.
        result = collection.get(include=["metadatas"]) or {}
        ids = result.get("ids", [])
        to_delete = [i for i in ids if str(i).startswith(prefix)]
        if not to_delete:
            return 0

        collection.delete(ids=to_delete)
        logger.info(f"✓ Deleted {len(to_delete)} documents with prefix: {prefix}")
        return len(to_delete)
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
        collection = get_or_create_collection()
        if not collection:
            return 0
        result = collection.get(include=["metadatas"]) or {}
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])

        # Strip any leading UUID prefix (8 hex chars + underscore) from the
        # target filename so we can match both prefixed and unprefixed variants.
        import re as _re
        bare_name = _re.sub(r'^[0-9a-fA-F]{8}_', '', filename)

        to_delete = set()
        for doc_id, meta in zip(ids, metadatas):
            sid = str(doc_id)
            fn = meta.get("filename", "") if isinstance(meta, dict) else ""

            # Strategy 1: exact metadata.filename match
            if fn == filename:
                to_delete.add(sid)
                continue

            # Strategy 2: metadata.filename ends with the bare name
            #   e.g. fn="ab12cd34_Best_player.txt", bare_name="Best_player.txt"
            if bare_name and fn.endswith(bare_name):
                to_delete.add(sid)
                continue

            # Strategy 3: doc_id contains the filename
            if filename in sid or bare_name in sid:
                to_delete.add(sid)
                continue

        if not to_delete:
            logger.info(f"delete_documents_by_filename: nothing found for '{filename}'")
            return 0

        collection.delete(ids=list(to_delete))
        logger.info(f"✓ Deleted {len(to_delete)} chunks matching filename '{filename}'")
        return len(to_delete)
    except Exception as e:
        logger.error(f"Error deleting documents by filename {filename}: {e}")
        return 0


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
            filename = meta.get("filename")
            if not filename:
                continue
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
