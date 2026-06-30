# Phase 13E Fix Report

## 1. Files Modified

- `backend/retrieval/routing.py`
- `backend/services/rag_service.py`
- `backend/services/streaming_service.py`
- `tests/test_phase13e_document_summary.py`
- `tests/test_phase13e_streaming.py`
- `Phase13E_Fix_Report.md`

## 2. Exact Root Causes Fixed

### Root Cause 1: document_summary used keyword context gating

`_has_sufficient_context()` required extracted query keyword overlap for all default generation requests. For overview prompts such as `What is this document about?`, the keyword extractor can produce no useful content keywords, causing `token_hits=0` and `sufficient=False` even when retrieval found chunks.

Fix: `document_summary` now has an early sufficiency branch based on retrieved chunk count and retrieved text length only.

### Root Cause 2: document_summary entered definition processing

Document-summary prompts could still trigger definition-style parsing through `_is_definition_style_query()` and `_extract_entity_from_definition_query()`, causing strict definition preference, weak-definition rejection, entity filters, and contamination guards to run against fake entities such as `this document about`.

Fix: HTTP and WebSocket RAG paths now explicitly exclude `family_v2_current == "document_summary"` before definition extraction/filtering. The streaming pre-RAG memory rewrite branch also excludes `document_summary` so summary prompts proceed to grounded RAG generation.

### Root Cause 3: document-summary grammar missed `discussed`

The document-summary detector recognized `discuss`, `discusses`, and `discussing`, but not `discussed`.

Fix: the grammar now supports `discuss`, `discusses`, `discussing`, and `discussed`. The implementation is still grammar-based and avoids document-specific terms. It also avoids overclassifying targeted requests such as `What are the major schools ... discussed in this document?` as document summaries.

### Root Cause 4: streaming could finalize incomplete responses

The streaming loop previously broke on mid-token timeout and allowed a non-empty partial response to continue to finalization. In runtime, list-style answers also used the short simple-fact generation cap, which could end a streamed answer mid-item.

Fix: mid-token timeout now triggers the existing non-stream fallback with `reset_partial=True`; if fallback fails, the partial output is replaced with a failure message instead of being finalized. List answers now use a modest 180-token generation budget instead of the 96-token simple-fact cap, preserving timeout protection while avoiding premature list truncation.

## 3. Before / After Behavior

| Scenario | Before | After |
|---|---|---|
| `What is this document about?` | Could fail context sufficiency with `token_hits=0`; could enter definition extraction as `this document about`. | Routes as `document_summary`, bypasses keyword sufficiency and definition processing, and generates from retrieved chunks. |
| `Give me a summary of this document.` | Could be intercepted by the streaming memory-rewrite branch and return not-found when no prior answer existed. | Routes as `document_summary` and proceeds to grounded RAG generation. |
| `What ... discussed in this document?` overview forms | `discussed` was not recognized by summary grammar. | `discussed` overview forms are recognized. |
| `What are the major schools of psychology discussed in this document?` | Could be affected by partial stream truncation, e.g. stopping after `The major`. | Streams a complete list-style answer from retrieved chunks. |

## 4. Test Results

Command:

```powershell
python -m pytest tests/test_phase13e_document_summary.py tests/test_phase13e_streaming.py tests/test_llm_stream_scope.py tests/test_active_source_filter.py -q
```

Result:

```text
12 passed, 5 warnings in 12.81s
```

Linter diagnostics:

```text
No linter errors found.
```

## 5. Runtime Proof

Runtime proof used a fresh headless WebSocket streaming invocation against tenant 2's active Chroma collection `t2_support_docs_v3_latest` with 422 indexed chunks. TTS was disabled for text proof only; retrieval, routing, generation, and final WebSocket response handling used the runtime code path.

### Prompt 1

Query: `What is this document about?`

Observed runtime markers:

- `FAMILY: document_summary`
- `DONE_COUNT: 1`
- `FINAL_CHARS: 1023`
- `[LLM GENERATION CONTEXT CHECK][WS] chunks=3 token_hits=0 sufficient=True`

Answer preview:

```text
This document appears to be an overview of memory types and processes, along with some information on mental health classification systems. Key ideas: - memory is discussed at different levels...
```

### Prompt 2

Query: `Give me a summary of this document.`

Observed runtime markers:

- `FAMILY: document_summary`
- `DONE_COUNT: 1`
- `FINAL_CHARS: 553`

Answer preview:

```text
This document covers key concepts in genetics and psychology. It explains that genes determine heredity and how sex is determined by a combination of chromosomes from parents...
```

### Prompt 3

Query: `What are the major schools of psychology discussed in this document?`

Observed runtime markers:

- `FAMILY: list_entity`
- `DONE_COUNT: 1`
- `FINAL_CHARS: 564`
- `num_predict=180`

Answer:

```text
The major schools of psychology discussed in this document include: - Structuralism: focused on studying the conscious experience by looking into its individual parts or elements. - Functionalism: focused on what the mind does and how it does. - Gestalt psychology: focused on studying the whole experience of a person rather than breaking it into individual components. - Psychodynamic School: focuses on the unconscious forces that drive / motivate human behavior. - Behaviorist / Behavioral School: focuses on studying the behavior that is observable and overt.
```

## 6. Hardcoding / Scope Verification

- No hardcoded answers were added.
- No document-specific, psychology-specific, company-specific, product-specific, metric-specific, or value-specific logic was added.
- Retrieval logic was not modified.
- Embeddings were not modified.
- Chroma configuration/storage was not modified.
- Tenant routing was not modified.

## 7. Required Assessments

### Genericity Assessment

The changes are generic. They depend on query grammar (`document_summary`, list family), retrieved chunk count, retrieved text length, and stream completion behavior. They do not depend on any known document, domain, entity, company, value, or dataset.

### Evidence-Origin Assessment

Answers continue to originate from retrieved chunks. The runtime proof shows generation used retrieved document chunks from the active tenant collection; no answer content or factual value is returned from code constants.

### Future-Document Compatibility Assessment

The implementation remains compatible with future unknown documents. Any future document can satisfy document-summary sufficiency through retrieved chunks and context length, while targeted list/detail questions continue through their existing grounded retrieval/generation path.
