# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

root = Path(r"G:\Grad_Project\assistify-rag-project-main")
os.chdir(root)
sys.path.insert(0, str(root))

from backend.assistify_rag_server import live_rag, RAG_STRICT_DISTANCE_THRESHOLD

queries = [
    "ما هي الإدارة؟",
    "ما هو التنظيم؟",
    "ارجع فقرة عن الأهداف",
    "ارجع فقرة تشرح الإدارة العلمية",
    "ما هي خطوات عملية التخطيط؟",
    "ما هو أفضل موقع للتجارة الإلكترونية؟",
]

for q in queries:
    docs = live_rag.search(q, top_k=10, distance_threshold=RAG_STRICT_DISTANCE_THRESHOLD, return_dicts=True)
    print("="*80)
    print(q)
    print(f"docs={len(docs)}")
    if docs:
        top = docs[0]
        sim = top.get("similarity", top.get("score", None))
        print(f"top_sim={sim}")
        preview = (top.get("text") or "").replace("\n", " ")[:180]
        print(f"top_preview={preview}")
