import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.assistify_rag_server import live_rag, _extract_structured_items_from_context

QUERIES = [
    "What are the phases of the pre-scientific management period?",
    "What are the five levels in Maslow's hierarchy of needs?",
]

async def run_one(q):
    print('\n' + '='*60)
    print('Query:', q)
    relevant_docs = live_rag.search(q, top_k=10, return_dicts=True)
    top_doc = relevant_docs[0] if relevant_docs else None
    top_text = (top_doc or {}).get('text') or ''
    print('Top doc page/source:', (top_doc or {}).get('metadata', {}).get('page'), (top_doc or {}).get('metadata', {}).get('source'))
    # run extractor on top chunk first
    items_top = _extract_structured_items_from_context(q, top_text)
    print('Extractor (top chunk) items:', items_top)
    # run extractor on full joined context
    full_ctx = '\n\n'.join([str(d.get('text','')) for d in relevant_docs])
    items_full = _extract_structured_items_from_context(q, full_ctx)
    print('Extractor (full context) items:', items_full)
    return {
        'query': q,
        'top_doc_meta': (top_doc or {}).get('metadata'),
        'items_top': items_top,
        'items_full': items_full,
    }

async def main():
    results = []
    for q in QUERIES:
        r = await run_one(q)
        results.append(r)
    print('\n--- SUMMARY ---')
    for r in results:
        print('\nQuery:', r['query'])
        print('Top doc meta:', r['top_doc_meta'])
        print('Top-chunk items:', r['items_top'])
        print('Full-context items:', r['items_full'])

if __name__ == '__main__':
    asyncio.run(main())
