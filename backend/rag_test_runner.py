import asyncio
import logging
from backend import assistify_rag_server as ars

live_rag = ars.live_rag
_extract_structured_items_from_context = ars._extract_structured_items_from_context
_should_use_direct_structured_extraction = ars._should_use_direct_structured_extraction
RAG_NO_MATCH_RESPONSE = ars.RAG_NO_MATCH_RESPONSE
_is_simple_factual_text_query = ars._is_simple_factual_text_query

logging.basicConfig(level=logging.INFO)

TESTS = [
    # Structured extraction
    ("What are the six Ms?", "A1"),
    ("What are the phases of the pre-scientific management period?", "A2"),
    ("What are the five levels in Maslow's hierarchy of needs?", "A3"),

    # LLM grounded
    ("What is management?", "B4"),
    ("Who is Taylor?", "B5"),
    ("Explain management according to this book", "B6"),

    # Out-of-scope
    ("What does this document say about blockchain?", "C7"),
    ("What does this document say about machine learning?", "C8"),
]

async def run_test(q, tag):
    print(f"--- {tag} QUERY: {q}")
    relevant_docs = live_rag.search(q, top_k=10, return_dicts=True)
    found = bool(relevant_docs)
    print("Retrieved docs:", len(relevant_docs))

    # Structured extraction decision
    allowed = _should_use_direct_structured_extraction(q, relevant_docs)
    print("_should_use_direct_structured_extraction:", allowed)

    # Extraction from top doc and full context
    top_ctx = str((relevant_docs[0] if relevant_docs else {}).get('text') or "")
    ext_top = _extract_structured_items_from_context(q, top_ctx)
    full_ctx = "\n".join([str(d.get('text') or "") for d in relevant_docs])
    ext_full = _extract_structured_items_from_context(q, full_ctx)
    print("extracted_top:", ext_top)
    print("extracted_full:", ext_full)

    # Simple heuristic: would system likely return Not found? (no LLM call here)
    if not found:
        print("Decision: NOT_FOUND (no retrieval)")
    else:
        if ("blockchain" in q.lower() or "machine learning" in q.lower()) and not (ext_top or ext_full):
            print('Decision: NOT_FOUND (out-of-scope)')
        else:
            if allowed and (ext_top or ext_full):
                print('Decision: USE_EXTRACTOR')
            else:
                print('Decision: USE_LLM')
    print()

async def main():
    for q, tag in TESTS:
        await run_test(q, tag)

if __name__ == '__main__':
    asyncio.run(main())
