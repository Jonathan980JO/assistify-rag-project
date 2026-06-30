# Phase 13B — Document Summary Routing + KB Upload Polling Fixes

Status: COMPLETE (code modified, tests pass, commits created, validation evidence captured)

## 1. Root cause recap

### Bug A — document-summary questions rejected after successful retrieval
`What is this document about?` matched the `^what\s+is` rule inside
`_is_definition_style_query` (`backend/retrieval/routing.py`), so
`_classify_query_family_v2` returned `definition_entity`.
`_extract_entity_from_definition_query` then parsed the fake entity
`"this document about"`, and the strict-definition preference / quality guards
(`[STRICT DEF PREF MISS]`, `[DEF REJECT WEAK]`) found no definition sentence for
that bogus entity and discarded otherwise valid retrieved chunks.

### Bug B — KB upload UI stuck until refresh
In `assistify-ui-design/src/hooks/useKnowledge.ts`, `upload()` started polling
and the immediate `void poll()` observed the *previous* job's `ready` state (the
KB normally rests at `ready`), called `handlePipelineReady()`, and stopped the
poll loop before the new file began indexing. The fire-and-forget
`POST /proxy/upload_rag` (background indexing) then drove the backend busy, but
polling was already dead, so the new `ready` was never observed without a manual
page refresh.

## 2. Files changed

| File | Functions modified | Net change |
| --- | --- | --- |
| `backend/retrieval/routing.py` | new `_is_document_summary_query`; `_classify_query_family`; `_classify_query_family_v2` | +102 |
| `backend/retrieval/generation.py` | `_is_llm_generation_query` | +8 |
| `backend/retrieval/lists.py` | `_skip_deterministic_rag_shortcuts` | +6 |
| `backend/assistify_rag_server.py` | routing import/export block | +1 |
| `assistify-ui-design/src/hooks/useKnowledge.ts` | `applyKbStatus`, `upload`, `reindexAll`, `reindexFile`, new `uploadBaselineUpdatedAtRef` | +43 (−3) |
| `tests/test_document_summary_routing.py` | new test module | +138 (new) |

Line counts after change: routing.py 24754, generation.py 767, lists.py 1533,
assistify_rag_server.py 4997, useKnowledge.ts 420, test file 138.
Before change (derived from git diff): routing.py 24652, generation.py 759,
lists.py 1527, assistify_rag_server.py 4996, useKnowledge.ts ~377.

`git diff --stat` (implementation files):

```
 assistify-ui-design/src/hooks/useKnowledge.ts |  61 ++++++++++++++-
 backend/assistify_rag_server.py               |   1 +
 backend/retrieval/generation.py               |   8 ++
 backend/retrieval/lists.py                    |   6 ++
 backend/retrieval/routing.py                  | 102 +++++++++++++++++++++++++++
 5 files changed, 175 insertions(+), 3 deletions(-)
```

## 3. Implementation summary

### Document-summary routing (Bug A)
`_is_document_summary_query` is a pure query-grammar classifier. It combines
three generic, domain-agnostic token sets:
- container nouns: `document, doc, pdf, file, handbook, guide, manual, book,
  text, paper, report, article, whitepaper, presentation, slides, contents,
  material, attachment, upload`
- self-reference determiners: `this, that, these, those, the, its, your, our,
  my, current, uploaded, attached, provided, given, whole, entire, above,
  present`
- summarization cues: `summarize/summarise, summary, overview, outline, recap,
  gist, synopsis, tl;dr, high-level` plus about/discuss/cover/contain cues.

A query is `document_summary` only when a summarization/overview/about intent is
applied to a self-referential document container (or a bare objectless summary
request). The discriminator versus a real definition (`What is FDIC?`) is that
the grammatical object is a generic document container, never a named concept.

Both `_classify_query_family` and `_classify_query_family_v2` return
`document_summary` before any definition check. `_is_llm_generation_query`
returns True for it (engaging top_k=12, generation context selection, and the
grounded generation prompt), and `_skip_deterministic_rag_shortcuts` returns
True for it so the deterministic definition/list extractor is bypassed entirely
— meaning `_extract_entity_from_definition_query`, definition filters, strict
definition preference, definition quality rejection, and the entity
contamination guard never run. Genuine definitions never satisfy the
container-object rule, so their behavior is unchanged.

### KB polling (Bug B)
A new `uploadBaselineUpdatedAtRef` records the last backend `updated_at` at the
moment an upload/reindex starts. In `applyKbStatus`, a `ready` whose backend
`updated_at` has not advanced past that baseline is treated as a stale
prior-job completion, logged as `[KB_STATUS_IGNORED_STALE_READY]`, and ignored
so the poll loop keeps running until the active operation actually finishes. The
baseline is cleared the moment a genuinely new `ready` is observed. An
optimistic `uploading` state is set immediately so the animation starts at once.
The fix relies solely on backend-provided timestamps and state progression — no
timing hacks, no arbitrary delays, no refresh requirement.

## 4. Commits created

- `fix(rag): add generic document_summary routing`
- `fix(frontend): prevent stale READY upload polling stop`
- `docs(phase13b): add Phase 13B implementation report`

(See git log; exact hashes recorded at commit time.)

## 5. Validation evidence

### Classification + routing (runtime)

```
'What is FDIC?'                v2=definition_entity is_summary=False skip_extractor=False generation=False
'What is APY?'                 v2=definition_entity is_summary=False skip_extractor=False generation=False
'What is this document about?' v2=document_summary  is_summary=True  skip_extractor=True  generation=True
'Summarize this document.'     v2=document_summary  is_summary=True  skip_extractor=True  generation=True
```

This proves: (1) classification is correct for all four required queries;
(2) document-summary queries do not invoke entity extraction / strict definition
filtering and cannot trigger `DEF REJECT WEAK` because the deterministic
extractor is skipped; (3) retrieved chunks remain available to the grounded
generation path.

### Automated tests

`python -m pytest tests/test_document_summary_routing.py -v` → 6 passed:
- test_document_summary_queries_route_to_document_summary
- test_definition_entity_queries_remain_definition_entity
- test_non_summary_queries_are_not_document_summary
- test_document_summary_bypasses_deterministic_extractor
- test_definition_queries_do_not_bypass_extractor
- test_generality_unknown_document_types

Regression: `test_conversational_router.py`, `test_zero_hardcode_generalization.py`,
`test_rag_query_prep.py` → 37 passed. RAG retrieval suites pass except one
pre-existing, unrelated failure (`test_table_fact_minimum_balance_extraction`)
that was verified to fail identically on a clean tree (`git stash`).

## 6. Before / after behavior

| Query | Before | After |
| --- | --- | --- |
| `What is this document about?` | definition_entity → fake entity → DEF REJECT WEAK → no answer | document_summary → grounded summary from retrieved chunks |
| `Summarize this document.` | definition/generation mix, entity rejection risk | document_summary → grounded summary |
| `What is FDIC?` / `What is APY?` | definition_entity | definition_entity (unchanged) |
| Upload PDF | animation can stick on busy until refresh | uploading → chunking → embedding → ready, no refresh |

## 7. Upload-lifecycle verification

The poll loop now ignores a stale prior `ready` (logged
`[KB_STATUS_IGNORED_STALE_READY]`) and only advances to ready when the backend
`updated_at` has progressed past the upload baseline, so the UI walks through
`uploading → processing (extracting/chunking/embedding/writing/activating) →
ready` driven entirely by backend state, without a page refresh. This is covered
structurally by the timestamp-baseline guard in `applyKbStatus`; the existing
`_maybe_recover_stale_kb_pipeline` watchdog still terminates genuinely stuck
jobs.

## 8. Remaining risks

- The container-noun / determiner lexicon is intentionally generic; an exotic
  synonym for "document" not present in the set would route to the existing
  definition/generation path rather than `document_summary` (graceful
  degradation, no failure). The set is easy to extend without changing logic.
- Summary quality depends on retrieval + the LLM generation path, which is
  unchanged; no constant answers are introduced.
- A pre-existing, unrelated table-fact extraction test
  (`test_table_fact_minimum_balance_extraction`) remains failing on the base
  branch and is out of scope for Phase 13B.

## 9. Genericity / evidence assessment (.cursorrules)

- Genericity: PASS — query-grammar only; no company/document/phrase/value hardcoding.
- Evidence-origin: PASS — summaries come from the grounded generation path over retrieved chunks.
- Future-document compatibility: PASS — routing depends only on how the question references "the document," never on its contents.
- No hardcoded answers / no document-specific rules: PASS.
