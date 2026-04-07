# -*- coding: utf-8 -*-
import asyncio
import json
import websockets

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
    "ما هو الذكاء الاصطناعي؟",
    "مين كسب كاس العالم 2022؟",
]

async def ask_one(q: str):
    uri = "ws://127.0.0.1:7000/ws"
    async with websockets.connect(uri, max_size=2**22, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({"text": q, "language": "ar"}, ensure_ascii=False))
        while True:
            msg = await ws.recv()
            if isinstance(msg, (bytes, bytearray)):
                continue
            data = json.loads(msg)
            if data.get("type") == "aiResponseDone":
                return {"q": q, "a": data.get("fullText"), "sources": data.get("sources")}


async def main():
    results = []
    for q in QUESTIONS:
        try:
            r = await asyncio.wait_for(ask_one(q), timeout=120)
        except Exception as exc:
            r = {"q": q, "a": f"<ERROR: {exc}>", "sources": 0}
        results.append(r)
        print("Q:", r["q"])
        print("A:", r["a"])
        print("SOURCES:", r["sources"])
        print("-" * 80)

    with open("rag_eval_results_ws.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
