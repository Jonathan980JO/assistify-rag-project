import sys, os
sys.path.insert(0, os.getcwd())
from backend import assistify_rag_server as srv

for q in [
    "What are the characteristics of management?",
    "What are the steps in the planning process?",
    "What are the six Ms of management?",
    "What is scientific management?",
    "What is quantum computing?",
]:
    fam = srv._classify_query_family_v2(q)
    ctx, focus = srv._split_query_context_focus_tokens(q, fam)
    print(f"Q: {q}")
    print(f"  family_v2={fam}")
    print(f"  focus={focus}")
    print(f"  context={ctx}")
