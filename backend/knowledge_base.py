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

def search_documents(query: str, top_k: int = 3):
    """
    Search for relevant documents using semantic similarity
    
    Args:
        query: User's question
        top_k: Number of results to return
        
    Returns:
        List of relevant document texts
    """
    try:
        collection = get_or_create_collection()
        if not collection:
            return []
            
        query_embedding = embedder.encode(query).tolist()
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        documents = results['documents'][0] if results['documents'] else []
        logger.info(f"Found {len(documents)} relevant documents for: {query[:50]}...")
        return documents
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
