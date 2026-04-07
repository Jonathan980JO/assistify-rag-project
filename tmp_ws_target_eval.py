import asyncio
import json
from datetime import datetime
import websockets

URI = "ws://127.0.0.1:7000/ws"

QUESTIONS = [
    "What is psychology?",
    "Who founded modern psychology?",
    "When was the first psychology lab established?",
    "What are the goals of psychology?",
    "Explain the difference between behavior and mental processes",
    "Why is psychology considered a science?",
    "What is the scientific method in psychology?",
    "List all goals of psychology",
    "List all branches of psychology mentioned",
    "List the theoretical perspectives of psychology",
    "What are the components of the scientific method?",
    "What does Lesson 1 talk about?",
    "What topics are covered in this course?",
    "What is Lesson 5 about?",
    "What comes after Learning in the course?",
    "Explain classical conditioning with example",
    "What is operant conditioning and how is it different?",
    "Explain Freud’s structure of personality",
    "What are defense mechanisms?",
    "What does this document say about blockchain?",
    "Explain quantum psychology",
    "What is machine learning?",
    "Who is Wilhelm Wundt?",
    "What is tabula rasa?",
    "What is phrenology?",
    "What are the disadvantages of psychology?",
    "What is Chapter 50 about?",
    "What happens in Scene III?",
]


async def ask_one(ws, question: str):
    await ws.send(json.dumps({"text": question}))
    full_text = ""
    logs = []
    while True:
        msg = await asyncio.wait_for(ws.recv(), timeout=90)
        if isinstance(msg, bytes):
            continue
        data = json.loads(msg)
        t = data.get("type")
        if t in {"aiResponse", "aiResponseChunk", "aiResponseDone"}:
            logs.append(data)
        if t == "aiResponseDone":
            full_text = str(data.get("fullText") or "").strip()
            break
    return {
        "question": question,
        "answer": full_text,
        "events": logs,
    }


async def main():
    out = {
        "ts": datetime.now().isoformat(),
        "uri": URI,
        "results": [],
    }
    async with websockets.connect(URI, max_size=2_000_000, ping_interval=20, ping_timeout=20) as ws:
        for q in QUESTIONS:
            result = await ask_one(ws, q)
            out["results"].append(result)
            print(f"Q: {q}\nA: {result['answer']}\n{'-'*60}")

    path = f"run_queries_results_ui_ws_{int(datetime.now().timestamp())}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(path)


if __name__ == "__main__":
    asyncio.run(main())
