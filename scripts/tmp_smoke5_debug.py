import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.assistify_rag_server import (
    live_rag,
    RAG_STRICT_DISTANCE_THRESHOLD,
    _is_simple_factual_text_query,
    _detect_language,
    _rerank_docs_for_query_intent,
)

LOGIN_URL = "http://127.0.0.1:7001/login"
QUERY_URL = "http://127.0.0.1:7000/query"

QUESTIONS = [
    "What is psychology?",
    "Who founded the first psychological laboratory and when?",
    "List ONLY the goals of psychology.",
    "What are the different perspectives in psychology?",
    "What is the capital of France?",
]


def preview(text: str, n: int = 220) -> str:
    return re.sub(r"\s+", " ", text or "")[:n]


def main() -> None:
    s = requests.Session()
    login = s.post(LOGIN_URL, data={"username": "admin", "password": "admin"}, allow_redirects=False, timeout=20)
    print("login_status:", login.status_code)

    report = []

    for q in QUESTIONS:
        simple = _is_simple_factual_text_query(q)
        lang = _detect_language(q)
        top_k_req = 3 if simple else 10

        docs_raw = live_rag.search(q, top_k=10, distance_threshold=RAG_STRICT_DISTANCE_THRESHOLD, return_dicts=True)
        docs_chosen = live_rag.search(q, top_k=top_k_req, distance_threshold=RAG_STRICT_DISTANCE_THRESHOLD, return_dicts=True)
        docs_chosen = _rerank_docs_for_query_intent(q, docs_chosen)

        r = s.post(QUERY_URL, json={"text": q}, timeout=180)
        answer = ""
        if r.status_code == 200:
            answer = (r.json() or {}).get("answer", "")

        item = {
            "question": q,
            "query_meta": {
                "simple_factual": simple,
                "language": lang,
                "top_k_selected": top_k_req,
                "threshold": RAG_STRICT_DISTANCE_THRESHOLD,
            },
            "raw_top10": [
                {
                    "i": i + 1,
                    "score": float(d.get("score", d.get("similarity", 0.0)) or 0.0),
                    "section": (d.get("metadata") or {}).get("section"),
                    "page": (d.get("metadata") or {}).get("page"),
                    "preview": preview(d.get("text", "")),
                }
                for i, d in enumerate(docs_raw[:10])
            ],
            "chosen_final_chunks": [
                {
                    "i": i + 1,
                    "score": float(d.get("score", d.get("similarity", 0.0)) or 0.0),
                    "section": (d.get("metadata") or {}).get("section"),
                    "page": (d.get("metadata") or {}).get("page"),
                    "preview": preview(d.get("text", "")),
                }
                for i, d in enumerate(docs_chosen[:top_k_req])
            ],
            "answer": answer,
        }
        report.append(item)

    out = ROOT / "smoke5_debug_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nSaved:", out)
    for item in report:
        print("\n" + "=" * 90)
        print("Q:", item["question"])
        print("meta:", item["query_meta"])
        print("answer:", item["answer"])
        print("chosen_final_chunks:")
        for ch in item["chosen_final_chunks"]:
            print(f"  [{ch['i']}] score={ch['score']:.4f} section={ch['section']} page={ch['page']}")
            print("      ", ch["preview"])


if __name__ == "__main__":
    main()
