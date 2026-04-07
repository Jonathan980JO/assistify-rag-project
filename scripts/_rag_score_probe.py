# -*- coding: utf-8 -*-
import os, sys
from pathlib import Path
root = Path(r"G:\Grad_Project\assistify-rag-project-main")
os.chdir(root); sys.path.insert(0, str(root))
from backend.assistify_rag_server import live_rag

queries = [
    "return paragraph about goals",
    "return paragraph scientific management",
    "steps in the planning process",
    "best e-commerce website",
]
for q in queries:
    raw = live_rag.vs.search(query=q, top_k=10, threshold=-2.0)
    sims = [round(float(r.get('similarity', r.get('score', 0.0))), 4) for r in raw[:5]]
    print(q, sims)
