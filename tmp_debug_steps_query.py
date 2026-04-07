import asyncio

from backend.assistify_rag_server import call_llm_with_rag


async def main() -> None:
    answer, docs = await call_llm_with_rag(
        "Steps in planning process",
        "dbg_steps",
        {"username": "perf_test", "role": "admin"},
    )
    print("ANSWER:", answer)
    print("DOCS:", len(docs or []))
    for index, doc in enumerate((docs or [])[:5]):
        text = (doc.get("page_content") or doc.get("text") or "").replace("\n", " ")
        print(index, text[:260])


if __name__ == "__main__":
    asyncio.run(main())
