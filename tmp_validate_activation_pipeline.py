import json
import shutil
import time
from pathlib import Path

import requests

BASE_LOGIN = "http://127.0.0.1:7001"
BASE_RAG = "http://127.0.0.1:7000"
ROOT = Path(__file__).resolve().parent
ASSETS_DIR = ROOT / "backend" / "assets"
TMP_PDF = ROOT / "tmp_validation_Principles_of_Management.pdf"

QUERIES = [
    "What is this document about?",
    "List all units in the book",
    "What are the six Ms of management?",
    "What is discussed in Unit 4?",
    "What does this document say about machine learning?",
]


def login_admin(session: requests.Session) -> None:
    r = session.post(
        f"{BASE_LOGIN}/login",
        data={"username": "admin", "password": "admin"},
        allow_redirects=False,
        timeout=20,
    )
    r.raise_for_status()


def get_json(session: requests.Session, url: str, **kwargs):
    r = session.get(url, timeout=60, **kwargs)
    r.raise_for_status()
    return r.json()


def post_json(session: requests.Session, url: str, **kwargs):
    r = session.post(url, timeout=120, **kwargs)
    r.raise_for_status()
    return r.json()


def find_management_pdf() -> Path:
    candidates = sorted(ASSETS_DIR.glob("*Principles_of_Management.pdf"))
    if candidates:
        return candidates[-1]
    raise FileNotFoundError("No Principles_of_Management.pdf found in backend/assets")


def ensure_temp_pdf_source() -> Path:
    src = find_management_pdf()
    shutil.copy2(src, TMP_PDF)
    return TMP_PDF


def clean_start(session: requests.Session) -> dict:
    post_json(session, f"{BASE_RAG}/rag/doc-mode", json={"mode": "single", "active_sources": []})
    files_before = get_json(session, f"{BASE_RAG}/rag/files").get("files", [])
    deleted = []
    for item in files_before:
        filename = item.get("filename")
        if not filename:
            continue
        d = post_json(session, f"{BASE_RAG}/rag/delete", params={"doc_prefix": filename})
        deleted.append({"filename": filename, "deleted": d.get("deleted", 0)})
    files_after = get_json(session, f"{BASE_RAG}/rag/files").get("files", [])
    debug_after = get_json(session, f"{BASE_RAG}/rag/debug")
    return {
        "files_before": files_before,
        "deleted": deleted,
        "files_after": files_after,
        "debug_count_after": debug_after.get("count", -1),
    }


def upload_pdf(session: requests.Session, pdf_path: Path) -> dict:
    csrf = session.cookies.get("csrf_token") or "dev-csrf"
    session.cookies.set("csrf_token", csrf)
    with pdf_path.open("rb") as f:
        r = session.post(
            f"{BASE_RAG}/upload_rag",
            files={"file": (pdf_path.name, f, "application/pdf")},
            headers={"x-csrf-token": csrf},
            timeout=900,
        )
    r.raise_for_status()
    return r.json()


def wait_ready(session: requests.Session, timeout_s: int = 120) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        last = get_json(session, f"{BASE_RAG}/rag/ready")
        if last.get("ready"):
            return last
        time.sleep(1.0)
    return last


def query_and_retrieve(session: requests.Session) -> list:
    out = []
    for q in QUERIES:
        ret = get_json(session, f"{BASE_RAG}/rag/retrieve-debug", params={"query": q, "top_k": 5})
        ans = post_json(session, f"{BASE_RAG}/query", json={"text": q})
        out.append(
            {
                "question": q,
                "answer": ans.get("answer", ""),
                "retrieval_count": ret.get("count", 0),
                "retrieval_results": ret.get("results", []),
            }
        )
    return out


def main() -> None:
    session = requests.Session()
    login_admin(session)

    src = ensure_temp_pdf_source()
    clean = clean_start(session)
    upload = upload_pdf(session, src)
    ready = wait_ready(session)
    qres = query_and_retrieve(session)
    files = get_json(session, f"{BASE_RAG}/rag/files")
    debug = get_json(session, f"{BASE_RAG}/rag/debug")

    report = {
        "clean_start": clean,
        "upload": upload,
        "ready": ready,
        "files": files,
        "debug": {
            "count": debug.get("count", 0),
        },
        "queries": qres,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
