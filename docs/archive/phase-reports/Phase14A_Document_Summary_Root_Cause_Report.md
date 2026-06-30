# Phase 14A Document Summary Root Cause Report

## Evidence Snapshot

- Snapshot JSON: `logs/phase14a_document_summary_evidence.json`
- Snapshot Markdown: `logs/phase14a_document_summary_evidence.md`
- Queries:
  - `What is this document about?`
  - `Give me a summary of this document.`
  - `Provide a chapter-by-chapter overview of this document.`

The evidence harness shows that all three queries are classified as `document_summary` and rewritten to the same retrieval seed:

`document overview summary introduction table of contents units chapters key topics`

In the current before-state run, the live endpoint returned zero overview-seed candidates and websocket tracing closed cleanly before an `aiResponseDone` payload, so `selected_context` and `final answer` are recorded as empty/error evidence. The KB status shows the active collection is `support_docs_v3_latest` with 35 indexed chunks and active sources including `meridian_financial_handbook_clean.pdf` plus `favicon.ico`.

This is a valid before-state failure mode: the document-summary seed is not reliably retrieving representative chunks from the current index, even before context assembly has a chance to improve coverage.

## Code Trace Findings

1. `document_summary` queries do not search with the user's raw query. The retrieval query is a fixed overview seed from `_overview_seed_query()` in `backend/retrieval/routing.py`.
2. Production ingestion preserves structure in metadata (`section`, `chapter`, `title`, `unit`, `chunk_role`) but does not prepend that structure to the embedded text in `backend/knowledge_base.py`. The embedding input is raw chunk body text.
3. Cross-encoder reranking scores `[overview_seed, chunk_text]` pairs, which optimizes semantic similarity to the seed. It does not optimize representative document coverage across early pages, TOC, chapters, lessons, or headings.
4. The websocket path explicitly skips the user-query intent rerank for `document_summary`, so early-page / TOC / introduction boosts in the query-intent reranker never run for summaries.
5. `_select_generation_context_docs()` penalizes TOC-like chunks with `toc_like_penalty`, which works against document-summary and chapter-overview coverage.
6. Heading debug code extracts heading candidates from chunk body lines, but production ingestion strips heading lines from chunk text and stores them only as metadata. This explains `raw_candidates=[]` for documents that still have `title`/`section`/`chapter` metadata.

## Root Cause

Document summaries currently depend on semantic similarity between one generic overview seed and raw body chunks. Structural evidence exists, but it is mostly metadata-only, skipped by the embedding search, skipped by summary reranking, and penalized during generation-context selection.

The fix should therefore make retrieval and context selection structure-aware and coverage-aware. It should not add deterministic answer paths, document-specific rules, or special-case outputs.

## Assessments

- Genericity Assessment: The findings are based on query family, metadata fields, ranking mechanics, and ingestion behavior. No document-specific entities or values are used.
- Evidence-Origin Assessment: The report references live evidence artifacts and code paths. Future answer content must still originate from retrieved chunks, not constants.
- Future-Document Compatibility Assessment: The proposed direction uses generic structural metadata and coverage selection, so it applies to new documents and domains when their structure can be extracted or inferred.
