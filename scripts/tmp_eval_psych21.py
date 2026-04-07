import json
import re
import time
import sys
from pathlib import Path
from dataclasses import dataclass

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.assistify_rag_server import live_rag


LOGIN_URL = "http://127.0.0.1:7001/login"
QUERY_URL = "http://127.0.0.1:7000/query"


@dataclass
class QCase:
    idx: int
    question: str
    category: str
    expected_keywords: list[str]
    must_be_not_found: bool = False
    list_only: bool = False
    one_sentence: bool = False


QUESTIONS = [
    QCase(1, "What is psychology?", "basic", ["science", "behavior", "mental"]),
    QCase(2, "Who founded the first psychological laboratory and when?", "basic", ["wundt", "1879"]),
    QCase(3, "What are the main goals of psychology?", "basic", ["observation", "description", "prediction", "control"]),
    QCase(4, "Define behavior in psychology.", "basic", ["behavior", "actions", "observable"]),
    QCase(5, "What is the scientific method in psychology?", "basic", ["scientific", "hypothesis", "observation", "experiment"]),
    QCase(6, "What are the different perspectives in psychology?", "section", ["biological", "behavioral", "cognitive", "psychodynamic"]),
    QCase(7, "Explain the biological approach in psychology.", "section", ["biological", "brain", "nervous", "physiological"]),
    QCase(8, "What is the psychodynamic approach and who founded it?", "section", ["psychodynamic", "freud"]),
    QCase(9, "What is functionalism?", "section", ["functionalism", "william james", "function"]),
    QCase(10, "What is structuralism?", "section", ["structuralism", "introspection", "wundt"]),
    QCase(11, "Compare structuralism and functionalism.", "comparison", ["structuralism", "functionalism", "difference"]),
    QCase(12, "Compare biological and behavioral approaches.", "comparison", ["biological", "behavioral", "difference"]),
    QCase(13, "What are the misconceptions about psychologists?", "deep", ["misconception", "psychologist"]),
    QCase(14, "Explain how psychology evolved from philosophy.", "deep", ["philosophy", "evolved", "scientific"]),
    QCase(15, "What are the contributions of Greek philosophers to psychology?", "deep", ["greek", "philosopher", "socrates", "plato", "aristotle"]),
    QCase(16, "List ONLY the goals of psychology.", "format", ["observation", "description", "prediction", "control"], list_only=True),
    QCase(17, "Give a ONE sentence definition of psychology.", "format", ["psychology", "behavior", "mental"], one_sentence=True),
    QCase(18, "Extract the list of psychology branches only.", "format", ["branch", "psychology"]),
    QCase(19, "What is the capital of France?", "hallucination", [], must_be_not_found=True),
    QCase(20, "Who invented artificial intelligence according to this document?", "hallucination", [], must_be_not_found=True),
    QCase(21, "Explain psychology AND mention its goals AND give one real-life example.", "complex", ["psychology", "goals", "example"]),
]


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z]{3,}", (text or "").lower()))


def _score_retrieval(question: str, docs: list[dict], expected_keywords: list[str]) -> tuple[int, dict]:
    if not docs:
        return 0, {"doc_count": 0, "junk_count": 0, "kw_hit": 0}

    junk_markers = ("table of contents", "contents", "index", "front matter")
    junk_count = 0
    corpus = []
    for d in docs:
        txt = str((d or {}).get("text") or "").lower()
        sec = str(((d or {}).get("metadata") or {}).get("section") or "").lower()
        corpus.append(txt)
        if any(m in sec for m in junk_markers) or any(m in txt[:200] for m in junk_markers):
            junk_count += 1

    merged = "\n".join(corpus)
    kw_hit = sum(1 for k in expected_keywords if k.lower() in merged) if expected_keywords else 0

    score = 10
    if len(docs) > 4:
        score -= 2
    if junk_count:
        score -= min(5, junk_count)
    if expected_keywords:
        if kw_hit == 0:
            score -= 5
        elif kw_hit < max(1, len(expected_keywords) // 2):
            score -= 2
    return max(0, score), {"doc_count": len(docs), "junk_count": junk_count, "kw_hit": kw_hit}


def _score_answer(case: QCase, answer: str) -> tuple[int, int, int, str]:
    ans = (answer or "").strip()
    ans_l = ans.lower()

    if case.must_be_not_found:
        good = ans == "Not found in the document."
        val = 10 if good else 0
        return val, val, 10 if good else 0, "PASS" if good else "FAIL"

    kw_hit = sum(1 for k in case.expected_keywords if k.lower() in ans_l)
    need = max(1, len(case.expected_keywords) // 2)

    accuracy = 10
    if kw_hit == 0:
        accuracy = 2
    elif kw_hit < need:
        accuracy = 6

    grounding = 9
    if "according to" not in ans_l and case.category in {"deep", "comparison", "complex"}:
        grounding -= 1
    if any(tag in ans_l for tag in ["as an ai", "generally", "outside", "i think"]):
        grounding = max(0, grounding - 4)

    formatting = 10
    if case.list_only:
        has_lines = "\n" in ans
        if not has_lines:
            formatting -= 4
        if re.search(r"\b(the goals are|psychology is)\b", ans_l):
            formatting -= 2
    if case.one_sentence:
        sentence_count = len([s for s in re.split(r"[.!?]+", ans) if s.strip()])
        if sentence_count != 1:
            formatting -= 5

    if not ans or ans == "Not found in the document.":
        accuracy = min(accuracy, 3)
        grounding = min(grounding, 4)

    passed = "PASS" if (accuracy >= 8 and grounding >= 8 and formatting >= 8) else "FAIL"
    return accuracy, grounding, max(0, formatting), passed


def main():
    s = requests.Session()
    login = s.post(LOGIN_URL, data={"username": "admin", "password": "admin"}, allow_redirects=False, timeout=20)
    if login.status_code not in (200, 302, 303, 307):
        raise RuntimeError(f"Login failed: {login.status_code}")

    rows = []
    for case in QUESTIONS:
        t0 = time.perf_counter()
        docs = live_rag.search(case.question, top_k=3, distance_threshold=0.70, return_dicts=True)
        retrieval_score, retrieval_meta = _score_retrieval(case.question, docs, case.expected_keywords)

        r = s.post(QUERY_URL, json={"text": case.question}, timeout=180)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if r.status_code != 200:
            answer = f"<HTTP {r.status_code}>"
        else:
            answer = (r.json() or {}).get("answer", "")

        accuracy, grounding, formatting, status = _score_answer(case, answer)
        rows.append({
            "id": case.idx,
            "category": case.category,
            "question": case.question,
            "retrieval_score": retrieval_score,
            "answer_accuracy": accuracy,
            "grounding": grounding,
            "formatting": formatting,
            "status": status,
            "latency_ms": round(elapsed_ms, 1),
            "retrieval": retrieval_meta,
            "top_chunks": [
                {
                    "section": (d.get("metadata") or {}).get("section"),
                    "page": (d.get("metadata") or {}).get("page"),
                    "score": d.get("score"),
                    "preview": str(d.get("text") or "")[:180],
                }
                for d in docs[:3]
            ],
            "answer": answer,
        })

        print(f"Q{case.idx:02d} {status} | R={retrieval_score} A={accuracy} G={grounding} F={formatting} | {elapsed_ms:.0f}ms")

    with open("rag_eval_21_report.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    must_pass_ids = {1, 2, 3, 4, 5, 16, 17, 18, 19, 20, 21}
    failing_must = [r for r in rows if r["id"] in must_pass_ids and r["status"] == "FAIL"]
    failing_any = [r for r in rows if r["status"] == "FAIL"]

    print("\n=== SUMMARY ===")
    print("total:", len(rows), "fail_any:", len(failing_any), "fail_must:", len(failing_must))
    if failing_must:
        print("must-fail IDs:", [r["id"] for r in failing_must])
    if failing_any:
        print("all-fail IDs:", [r["id"] for r in failing_any])


if __name__ == "__main__":
    main()
