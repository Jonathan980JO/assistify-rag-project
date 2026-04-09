import sys
import os
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).resolve().parent))

from backend.assistify_rag_server import live_rag

query1 = "who was against the Nature of Management"
query2 = "who was against the bureaucratic style of management"

with open("test_out3.txt", "w", encoding="utf-8") as f:
    f.write("Searching for exact snippet...\n")
    exact_query = "Peter Drucker is against the bureaucratic style of management"
    results3 = live_rag.vs.collection.query(query_texts=[exact_query], n_results=5)
    
    docs = results3.get("documents", [[]])[0]
    dists = results3.get("distances", [[]])[0]
    for i, (d, dist) in enumerate(zip(docs, dists)):
        sim = 1.0 - dist
        f.write(f"[{i}] Sim: {sim:.4f} Text: {d[:200]}\n")

