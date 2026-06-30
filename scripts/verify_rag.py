import os
import sys
import json
import time

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from backend.assistify_rag_server import live_rag

# Golden questions aligned with backend/load_documents.py support KB
GOLDEN_QUESTIONS = [
    {
        "id": "kb_return_policy",
        "question": "How many days do I have to return a product?",
        "expected_topics": ["30 days", "return", "receipt"],
    },
    {
        "id": "kb_password_reset",
        "question": "How do I reset my password?",
        "expected_topics": ["Forgot Password", "email", "reset link"],
    },
    {
        "id": "kb_shipping",
        "question": "When is shipping free?",
        "expected_topics": ["$50", "free", "shipping"],
    },
    {
        "id": "kb_outofscope",
        "question": "What is the capital of France?",
        "expected_topics": [],
    },
]

def verify_rag(questions=GOLDEN_QUESTIONS):
    print("Starting RAG Verification...")
    results = []
    
    for q in questions:
        print(f"\nEvaluating: '{q['question']}'")
        start_time = time.time()
        
        # Use live_rag.search directly
        # Note: LiveRAGManager returns text chunks or dicts depending on return_dicts
        raw_chunks = live_rag.search(q['question'], top_k=5, return_dicts=True)
        duration = time.time() - start_time
        
        chunk_texts = [c['text'] for c in raw_chunks]
        
        # Check topics (soft check)
        found_topics = []
        if "expected_topics" in q:
            for topic in q["expected_topics"]:
                if any(topic.lower() in chunk.lower() for chunk in chunk_texts):
                    found_topics.append(topic)
        
        # Check out-of-scope response logic
        # For out-of-scope, search should usually return few or no high-similarity chunks
        # or the LLM would later refuse. Here we just check what was retrieved.
        
        res = {
            "id": q['id'],
            "question": q['question'],
            "num_chunks": len(raw_chunks),
            "top_similarity": raw_chunks[0]['similarity'] if raw_chunks else 0.0,
            "found_topics": found_topics,
            "missing_topics": [t for t in q.get("expected_topics", []) if t not in found_topics],
            "duration_s": round(duration, 3)
        }
        results.append(res)
        
        print(f"  - Chunks retrieved: {len(raw_chunks)}")
        print(f"  - Top Similarity: {res['top_similarity']:.4f}")
        if found_topics:
            print(f"  - Found topics: {', '.join(found_topics)}")
        if res['missing_topics']:
            print(f"  - Missing topics: {', '.join(res['missing_topics'])}")

    return results

if __name__ == "__main__":
    report = verify_rag()
    with open("rag_verification_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\nVerification report saved to rag_verification_report.json")
