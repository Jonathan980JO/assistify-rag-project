import os
from pathlib import Path
import chromadb

# Force clean collection selection during this rebuild
os.environ["ASSISTIFY_COLLECTION_NAME"] = "adaptive_rag_collection"
os.environ.setdefault("ASSISTIFY_DISABLE_RERANKER", "1")
os.environ.setdefault("ASSISTIFY_SAFE_MODE", "1")

from backend.pdf_ingestion_rag import VectorStore, AdaptiveRAGPipeline

DB_PATH = Path(r"g:\Grad_Project\assistify-rag-project-main\backend\chroma_db_v3")
PDF_PATH = Path(r"g:\Grad_Project\assistify-rag-project-main\backend\assets\3f4e6aee_Introduction to Psychology  (Complete) (14).pdf")

if not PDF_PATH.exists():
    raise FileNotFoundError(f"PDF not found: {PDF_PATH}")

client = chromadb.PersistentClient(path=str(DB_PATH))
try:
    client.delete_collection(name="adaptive_rag_collection")
    print("Deleted old adaptive_rag_collection")
except Exception:
    print("No previous adaptive_rag_collection to delete")

# Create clean collection
client.get_or_create_collection(name="adaptive_rag_collection", metadata={"hnsw:space": "cosine"})
print("Created fresh adaptive_rag_collection")

vs = VectorStore(persist_directory=str(DB_PATH))
pipeline = AdaptiveRAGPipeline(vs)
pipeline.ingest_pdf(str(PDF_PATH))

print("Active collection:", vs.collection.name)
print("Chunk count:", vs.collection.count())
