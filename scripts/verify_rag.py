import os
import sys
import json
import time

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from backend.assistify_rag_server import live_rag

# Golden Questions
GOLDEN_QUESTIONS = [
    {
        "id": "q1_factual",
        "question": "What is the official definition of psychology as stated in the text?",
        "expected_topics": ["scientific study", "mind", "behavior"]
    },
    {
        "id": "q2_entity",
        "question": "Who was Peter Drucker and what did he say about management by objectives?",
        "expected_topics": ["Peter Drucker", "MBO", "Management by Objectives", "targets", "goals"]
    },
    {
        "id": "q3_deep",
        "question": "What are the key takeaways from the later sections of the document?",
        "expected_topics": ["conclusion", "review", "summary"]
    },
    {
        "id": "q4_outofscope",
        "question": "What is the capital of France?",
        "expected_response": ["Not found in the document.", "\u0639\u0630\u0631\u0627\u060c \u0644\u0645 \u0623\u062c\u062f \u0647\u0630\u0627 \u0641\u064a \u0627\u0644\u0645\u0633\u062a\u0646\u062f."]
    }
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
