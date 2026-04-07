import sys
import os
import requests
import json
from pathlib import Path
from backend.assistify_rag_server import LiveRAGManager
import re
from config import OLLAMA_HOST, OLLAMA_PORT, OLLAMA_MODEL

def generate_answer(query):
    print(f"\n===========================")
    print(f"QUERY: {query}")
    rag = LiveRAGManager()
    
    # Force print to show up
    import sys
    
    res = rag.search(query, top_k=10, return_dicts=True)
    
    # Emulate format_rag_context_toon
    context = ""
    for idx, c in enumerate(res):
        context += f"Chunk {idx+1}:\n{c['text']}\n\n"
        
    prompt = f"Using ONLY the following excerpts from the book:\n\n{context}\n\nAnswer the following question: {query}"
    
    if "paragraph" in query:
        prompt = f"Using ONLY the following excerpts:\n\n{context}\n\nQuote the exact paragraph answering: {query}"
        
    url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False
    }
    
    resp = requests.post(url, json=payload).json()
    print("FINAL ANSWER:")
    print(resp['message']['content'])
    print("===========================\n")

if __name__ == "__main__":
    queries = [
        "Summarize Chapter 1 in 3 bullet points",
        "Summarize Chapter 2 in 3 bullet points",
        "Summarize Chapter 6 in 3 bullet points",
        "Summarize Chapter 7 in 3 bullet points",
        "Return the paragraph that explains weak passwords",
    ]
    for q in queries:
        generate_answer(q)
