# RAG Chunk Retrieval Fixes

This document describes three production retrieval bugs that caused correct answers to exist in the knowledge base but fail to reach the user, along with what we changed and why.

**Production path (unchanged):** PDF upload → `extract_pdf_asset_text()` → `chunk_and_add_document()` in `backend/knowledge_base.py` → retrieval via `VectorStore.search` in Chroma.

**Files touched:**
- `backend/rag_chunk_heuristics.py` — table/heading detection heuristic (extracted for testability)
- `backend/knowledge_base.py` — chunking boundaries and heading propagation
- `backend/assistify_rag_server.py` — imports the heuristic (same call sites as before)
- `tests/test_rag_chunk_retrieval_fixes.py` — regression tests (21 cases)

---

## Symptom (all three bugs)

Queries with clear, verbatim answers in the source document (e.g. *"what is the brake fluid replacement interval"*) sometimes returned the no-answer fallback (`RAG_NO_MATCH_RESPONSE`) even though the sentence was indexed. Live traces showed true-positive chunks being dropped or downranked before they reached the LLM.

---

## Bug 1: Colon-led definition bullets misclassified as table/heading

### Problem

The retrieval ranker applies a **~0.35 penalty** to chunks flagged by `_looks_table_or_heading_like_chunk()`. That heuristic was designed to deprioritize TOC lines, pipe-separated table rows, and bare section headings.

It also fired on legitimate **definition bullets** — short lines with an early colon and a full explanation, such as:

```
Brake Fluid: Hygroscopic (absorbs moisture over time), replacement every 2-3 years.
Coolant (Antifreeze): A mixture of water and ethylene glycol that prevents freezing.
```

These are prose bullets, not table rows or headings. They pattern-match on "short line + colon + capitalized tokens" and get penalized during reranking, pushing them below the distance threshold or out of the top-k window.

### Fix

Added colon-led **definition prose** detection in `backend/rag_chunk_heuristics.py`:

- If a chunk (or a majority of its lines) looks like `Term: full explanation`, return **not table-like** early.
- A line qualifies when text after `:` has **>8 words**, contains a **verb** (including domain verbs like `absorbs`, `prevents`, `lubricates`), or has a **parenthetical clause** with ≥5 words.
- Structural labels (`Chapter 3`, `Section 2.1`, numeric-only labels) are **excluded** so real headings still get penalized.
- Pipe-heavy lines (`a | b | c`) are **not** exempt.

### Why this approach

Colon bullets and table rows look similar at a glance (label + delimiter + value). The distinguishing signal is **whether the post-colon text is a full clause/sentence** vs. a short cell value or bare title. Length, verbs, and parentheticals are reliable, document-agnostic signals that do not require domain-specific rules.

---

## Bug 2: Prose merged with `[TABLE DATA]` in one chunk

### Problem

During PDF extraction, `pdfplumber` appends tables to page text under a `[TABLE DATA]` marker:

```
…5W-30 is recommended for most climates…

[TABLE DATA]
Oil Type | Viscosity | API Rating
5W-30    | Standard  | SN
```

`chunk_and_add_document` uses a sliding **word window** (target ~300 words, overlap 50 for normal docs). Without a hard boundary, the tail of a prose paragraph and the head of a `[TABLE DATA]` block could land in **one chunk**.

Any chunk containing `[TABLE DATA]` matches `\btable\b` in the heading/table heuristic and receives the table penalty. Clean explanatory prose bundled inside that chunk was downranked along with the table.

### Fix

In `chunk_and_add_document`:

1. **`_split_prose_and_table_blocks()`** — split any paragraph at `[TABLE DATA]` into separate structured units before chunking.
2. **Hard flush** — when the chunker reaches a unit that starts with `[TABLE DATA]`, emit the current prose buffer first so prose and table content never share a chunk.

### Why this approach

Tables and the paragraphs that introduce them are semantically different retrieval targets. Merging them produces embeddings that average two intents, and triggers table-like penalties on prose. A hard seam at `[TABLE DATA]` matches how extraction already marks table boundaries and requires no changes to the PDF pipeline.

---

## Bug 3: Section heading lost after the first word-window

### Problem

Standalone heading paragraphs (e.g. `Fluid Specifications`) are not indexed alone. The chunker stores them in `current_heading` and prepends them to the **next** body paragraph:

```python
if current_heading and current_heading.lower() not in para.lower():
    para = f"{current_heading}\n{para}"
```

That prepend happened **once per paragraph**, before `_split_long_text_to_windows()`. Long sections split into multiple windows (step = target − overlap) only kept the heading on the **first** window. Later windows from the same section had no heading context, and multi-bullet lists could come back as fragmented or heading-only text.

### Fix

1. **Removed** the one-time prepend on the full paragraph.
2. **After** word-windowing, prepend `current_heading` to **every** window derived from that unit (unless the heading text is already present in that window).

### Why this approach

Headings are retrieval anchors: users often query by section name or topic. Each window is a separate embedding in Chroma, so each window needs the heading for consistent recall. Prepending per-window is cheaper than duplicating heading metadata in a side channel and matches how readers experience the document (every continuation still belongs to the same section).

---

## Verification

Regression tests live in `tests/test_rag_chunk_retrieval_fixes.py`.

```powershell
python -m pytest tests/test_rag_chunk_retrieval_fixes.py -v
```

Tests assert:

| Check | Expectation |
|-------|-------------|
| Colon definition bullets | `_looks_table_or_heading_like_chunk` → `False` |
| Real headings, `[TABLE DATA]`, pipe rows | Still → `True` |
| Prose + `[TABLE DATA]` in one doc | No single chunk contains both |
| Long section under one heading | Heading appears in ≥3 word-windows |
| Bullet list under heading | Full sentence text retained, no heading-only fragments |

### Operational note

**Restart the RAG server** after deploying these changes. **Re-ingest** documents that were indexed before the fix — existing chunks in Chroma still use the old boundaries and heading logic until re-uploaded or reindexed.

---

## Out of scope (intentionally unchanged)

- `AdaptiveRAGPipeline` / `smart_chunking` in `pdf_ingestion_rag.py` — tenant uploads do not use this path.
- `RAG_STRICT_DISTANCE_THRESHOLD` (default `1.0`) — not changed; fixes address ranking and chunk quality upstream of the threshold gate.
- Retrieval top-k values — unchanged.

---

## Related configuration (reference)

| Setting | Default | Role |
|---------|---------|------|
| `RAG_STRICT_DISTANCE_THRESHOLD` | `1.0` | Max Chroma cosine distance to keep a hit |
| Chunk target (normal docs) | 300 words | `chunk_and_add_document` |
| Chunk overlap (normal docs) | 50 words | Sliding window step = target − overlap |
| Table-like penalty | ~0.35 | Applied when heuristic returns `True` |
