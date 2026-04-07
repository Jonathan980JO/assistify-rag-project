# -*- coding: utf-8 -*-
import asyncio
import io
import json
import re
from contextlib import redirect_stdout

import aiohttp
from backend import assistify_rag_server as srv

QUESTIONS = [
    "ما هو علم النفس؟",
    "ما هو تعريف علم النفس؟",
    "ما هي أهداف علم النفس؟",
    "لماذا ندرس علم النفس؟",
    "اذكر أهداف علم النفس",
    "عدد أهداف علم النفس",
    "اشرح المدارس الفكرية في علم النفس",
    "ما هو Structuralism؟",
    "ما هو Functionalism؟",
    "ما الفرق بين Functionalism و Structuralism؟",
    "لخص Lesson 1 في 3 نقاط",
    "لخص Lesson 2 في 3 نقاط",
]


def _parse_normalized(stdout_text: str, fallback: str) -> str:
    m = re.search(r"Normalized Retrieval Query:\s*'([^']*)'", stdout_text)
    if m:
        return m.group(1)
    return fallback


def _contains_arabic(text: str) -> bool:
    return any("\u0600" <= c <= "\u06FF" for c in (text or ""))


async def main():
    if srv.llm_session is None or srv.llm_session.closed:
        srv.llm_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))

    rows = []
    for q in QUESTIONS:
        q_style = srv._analyze_query_style(q)
        top_k = 15 if q_style.get("is_compare") else (12 if q_style.get("is_list") else 10)

        buf = io.StringIO()
        with redirect_stdout(buf):
            final_docs = srv.live_rag.search(
                q,
                top_k=top_k,
                distance_threshold=srv.RAG_STRICT_DISTANCE_THRESHOLD,
                return_dicts=True,
            )
        log_text = buf.getvalue()
        normalized = _parse_normalized(log_text, q)

        retrieval_query = q if _contains_arabic(q) else normalized
        raw_docs = []
        try:
            raw_docs = srv.live_rag.vs.search(query=retrieval_query, top_k=15, threshold=-2.0, filter_meta=None)
        except Exception as e:
            raw_docs = [{"text": f"<raw search error: {e}>", "metadata": {}, "score": 0.0}]

        answer, _ = await srv.call_llm_with_rag(q, "dbg_pass", {"username": "debug", "role": "admin"})

        item = {
            "question": q,
            "normalized_query": normalized,
            "retrieval_query": retrieval_query,
            "search_stdout": log_text,
            "raw_top_chunks": [
                {
                    "rank": i + 1,
                    "source_filename": str((d.get("metadata") or {}).get("source") or (d.get("metadata") or {}).get("filename") or ""),
                    "page": (d.get("metadata") or {}).get("page"),
                    "section": str((d.get("metadata") or {}).get("section") or ""),
                    "score": d.get("score", d.get("similarity")),
                    "text": str(d.get("text") or "")[:1200],
                }
                for i, d in enumerate(raw_docs[:15])
            ],
            "final_chunks": [
                {
                    "rank": i + 1,
                    "source_filename": str((d.get("metadata") or {}).get("source") or (d.get("metadata") or {}).get("filename") or ""),
                    "page": (d.get("metadata") or {}).get("page"),
                    "section": str((d.get("metadata") or {}).get("section") or ""),
                    "score": d.get("score", d.get("similarity")),
                    "text": str(d.get("text") or "")[:1200],
                }
                for i, d in enumerate(final_docs or [])
            ],
            "final_merged_context": "\n\n---\n\n".join(str(d.get("text") or "") for d in (final_docs or []))[:12000],
            "answer": answer,
        }
        rows.append(item)

        print("=" * 100)
        print("Q:", q)
        print("Normalized:", normalized)
        print("Final docs:", len(final_docs or []))
        print("Answer:", answer)

    with open("retrieval_debug_report.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    if srv.llm_session and not srv.llm_session.closed:
        await srv.llm_session.close()


if __name__ == "__main__":
    asyncio.run(main())
