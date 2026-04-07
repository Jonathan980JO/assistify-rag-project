import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.assistify_rag_server import live_rag, call_llm_with_rag, _should_use_direct_structured_extraction, _extract_structured_items_from_context

QUERIES = [
    "What are the six Ms?",
    "What are the phases of the pre-scientific management period?",
    "What are the five levels in Maslow's hierarchy of needs?",
    "What is management?",
    "Who is Taylor?",
    "What does this document say about blockchain?",
]

async def run_one(q):
    print('\n' + '='*60)
    print('Query:', q)
    relevant_docs = live_rag.search(q, top_k=10, return_dicts=True)
    top_doc = relevant_docs[0] if relevant_docs else None
    # top retrieval confidence signals
    top_signals = {
        'top_similarity': float(top_doc.get('similarity')) if top_doc and top_doc.get('similarity') is not None else None,
        'top_exact': bool(top_doc.get('exact_phrase_matched')) if top_doc else False,
        'top_concept_hits': int(top_doc.get('concept_hits') or 0) if top_doc else 0,
        'matched_tokens': top_doc.get('matched_tokens') if top_doc else [],
    }
    print('Top retrieval signals:', top_signals)

    # routing decision
    should_struct = _should_use_direct_structured_extraction(q, relevant_docs)
    routing = 'structured_extraction' if should_struct else 'grounded_llm_or_not_found'
    print('Routing decision (pre-check):', routing)

    # if structured extraction allowed, run extractor on combined context
    extractor_used = False
    extractor_items = []
    if should_struct:
        extractor_used = True
        context_joined = '\n\n'.join([str(d.get('text','')) for d in relevant_docs])
        extractor_items = _extract_structured_items_from_context(q, context_joined)
        print('Extractor items:', extractor_items)

    # Now call the full RAG pipeline (grounded LLM path) -- note: call_llm_with_rag returns (text, docs)
    answer, docs = await call_llm_with_rag(q, connection_id='test', user={'username':'tester','role':'tester'})
    print('LLM/extractor answer:', answer)
    print('Extractor used in pipeline decision:', extractor_used)
    # final correctness heuristic (manual check placeholder)
    return {
        'query': q,
        'routing_decision': routing,
        'top_signals': top_signals,
        'extractor_used': extractor_used,
        'extractor_items': extractor_items,
        'final_answer': answer,
    }

async def main():
    results = []
    for q in QUERIES:
        r = await run_one(q)
        results.append(r)
    print('\n--- SUMMARY ---')
    for r in results:
        print('\nQuery:', r['query'])
        print('Routing:', r['routing_decision'])
        print('Top signals:', r['top_signals'])
        print('Extractor used:', r['extractor_used'])
        print('Extractor items:', r['extractor_items'])
        print('Final answer:', r['final_answer'][:400])

if __name__ == '__main__':
    asyncio.run(main())
