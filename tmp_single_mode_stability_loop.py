import asyncio
import json
import time
from pathlib import Path

import requests
import websockets

BASE_RAG = "http://127.0.0.1:7000"
BASE_LOGIN = "http://127.0.0.1:7001"
WS_URL = "ws://127.0.0.1:7000/ws"
PDF_DIR = Path(r"C:\Users\MK\Desktop\Notes\PDF")
PDFS = sorted(PDF_DIR.glob("*.pdf"))[:3]
NOT_FOUND = "Not found in the document."


def login_admin(session: requests.Session):
    r = session.post(
        f"{BASE_LOGIN}/login",
        data={"username": "admin", "password": "admin"},
        allow_redirects=False,
        timeout=20,
    )
    if r.status_code not in (200, 302, 303):
        raise RuntimeError(f"login failed: {r.status_code} {r.text[:150]}")


def set_mode(session: requests.Session):
    r = session.post(f"{BASE_RAG}/rag/doc-mode", json={"mode": "single", "active_sources": []}, timeout=30)
    r.raise_for_status()


def upload_pdf(session: requests.Session, pdf_path: Path):
    csrf = f"tok_{int(time.time()*1000)}"
    session.cookies.set("csrf_token", csrf)
    with pdf_path.open("rb") as f:
        r = session.post(
            f"{BASE_RAG}/upload_rag",
            files={"file": (pdf_path.name, f, "application/pdf")},
            headers={"x-csrf-token": csrf},
            timeout=600,
        )
    r.raise_for_status()
    return r.json()


async def ask_ws(session: requests.Session, question: str):
    cookie = "; ".join([f"{c.name}={c.value}" for c in session.cookies])
    t0 = time.perf_counter()
    first_token_ms = None
    answer = NOT_FOUND
    sources = 0
    try:
        async with websockets.connect(WS_URL, additional_headers={"Cookie": cookie}, max_size=2**22) as ws:
            await ws.send(json.dumps({"text": question, "language": "en"}))
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=180)
                if isinstance(msg, (bytes, bytearray)):
                    continue
                data = json.loads(msg)
                if data.get("type") == "aiResponseChunk" and first_token_ms is None:
                    first_token_ms = (time.perf_counter() - t0) * 1000
                if data.get("type") == "aiResponseDone":
                    answer = data.get("fullText", "")
                    sources = data.get("sources", 0)
                    break
    except Exception:
        pass

    total_ms = (time.perf_counter() - t0) * 1000
    return {
        "answer": answer,
        "sources": sources,
        "first_token_ms": round(first_token_ms or -1, 1),
        "total_ms": round(total_ms, 1),
    }


def retrieval_count(session: requests.Session, question: str):
    r = session.get(f"{BASE_RAG}/rag/retrieve-debug", params={"query": question, "top_k": 3}, timeout=40)
    r.raise_for_status()
    payload = r.json()
    return payload.get("count", 0), payload


async def main():
    if len(PDFS) < 3:
        raise RuntimeError("Need at least 3 PDFs in test folder")

    session = requests.Session()
    login_admin(session)

    rounds = 4
    for round_idx in range(1, rounds + 1):
        print(f"\n=== SINGLE-MODE ROUND {round_idx} ===")
        round_ok = True
        for pdf in PDFS:
            set_mode(session)
            up = upload_pdf(session, pdf)
            indexed_filename = up.get("filename")
            char_count = up.get("extracted_char_count")
            chunks_generated = up.get("chunks_generated")
            chunks_indexed = up.get("chunks_indexed")

            # one definition + one list + one factual + one OOS
            questions = [
                "What is this document about?",
                "List only key points from this document as bullets, one item per line.",
                "Who is mentioned in this document?",
                "What is the capital of France?",
            ]

            retrieval_total = 0
            fails = []
            for q in questions:
                ws = await ask_ws(session, q)
                rc, dbg = retrieval_count(session, q)
                retrieval_total += rc
                if q == "What is the capital of France?":
                    if ws["answer"].strip() != NOT_FOUND:
                        fails.append("oos_not_found_rule")
                else:
                    if chunks_indexed == 0 or rc == 0:
                        fails.append("no_retrieval")

            passed = (chunks_indexed or 0) > 0 and len(fails) == 0
            round_ok = round_ok and passed

            print({
                "indexed_filename": indexed_filename,
                "extracted_char_count": char_count,
                "chunks_generated": chunks_generated,
                "chunks_indexed": chunks_indexed,
                "retrieval_count": retrieval_total,
                "pass": passed,
                "root_cause": ",".join(sorted(set(fails))) if fails else "",
            })

        if round_ok:
            print("\nSINGLE-MODE STABLE: PASS")
            return 0

    print("\nSINGLE-MODE STABLE: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
