import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
from backend.assistify_rag_server import _TenantScope, _validate_query_ui_equivalent, _compare_terms_from_query, _compare_answer_from_docs_strict, _search_fast_minimal
qs = [
    "What's the difference between AWD and 4WD as described in the document?",
]
with _TenantScope(3):
    for q in qs:
        print("compare terms:", _compare_terms_from_query(q))
        docs = _search_fast_minimal(q, top_k=8)
        if "AWD" in q:
            ans = _compare_answer_from_docs_strict(q, docs)
            print("strict compare:", (ans or "")[:200])
        d = _validate_query_ui_equivalent(q)
        ui = d.get("ui_equivalent_result") or {}
        sc = d.get("internal_shortcut_result") or {}
        print("Q:", q[:70])
        print("  retrieval:", d.get("retrieval_count"))
        print("  shortcut:", sc.get("answer_type"), (sc.get("answer") or "")[:140])
        print("  ui:", ui.get("answer_type"), (ui.get("answer") or "")[:140])
        print()
