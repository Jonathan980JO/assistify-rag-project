# Phase 14C Definition & Fact Pipeline Report

## Summary

Phase 14C focused only on definition/fact answer generation. Retrieval, reranking, Chroma configuration, embeddings, ingestion, active-source filtering, tenant routing, document summaries, chapter overview, and upload logic were not changed.

The root cause was not retrieval. For the failing definition questions, the answer-bearing chunks were already present in retrieved or selected evidence, but the post-retrieval definition pipeline required a strict textbook-style sentence. Evidence fragments such as:

- `A Swiss psychiatrist, founder of the analytical school of psychology, Jung presented...`
- `Structuralism - The school of thought that focused...`
- `Functionalism An approach that concentrated...`

were rejected or routed into the wrong extractor because they did not look like direct `X is ...` sentences.

The fix keeps retrieval and reranking intact, keeps grounding/OCR/contamination checks, and adds a generic evidence-preserving definition synthesis fallback for retrieved chunks that contain the answer but express it as descriptor/entity or heading/definition evidence.

## Code Paths

- Harness: `scripts/phase14c_definition_evidence.py`
  - Runs `/kb_status`, `/rag/retrieve-debug`, and WebSocket `/ws` with `phase14_trace: true`.
  - Auto-selects the active tenant by probing evidence-bearing tenants.
  - Writes `logs/phase14c_* / phase14c_definition_evidence.json` and `.md`.

- Definition/fact routing: `backend/retrieval/routing.py`
  - `_shared_rag_final_answer_decision(...)`
  - `_extract_definition_route_answer(...)`
  - `_extract_evidence_preserving_definition_answer(...)`
  - `_extract_minbalance_from_pipe_line(...)`

Important changed paths:

- `definition_entity` now stays on the definition route instead of being diverted to the fact route for `Who is ...` questions.
- Definition validator rescue now tries evidence-preserving synthesis before returning `definition_candidate_rejected`.
- Strict definition hard-stop now tries evidence-preserving synthesis before `definition_not_found_strict`.
- Row-level minimum-balance table facts now read the value from the cell containing the requested attribute, not a neighboring fee cell.

## Root Cause Evidence

Baseline evidence file: `logs/phase14c_definition_evidence.md`

Before-state failures:

| Query | Answer evidence in retrieved/selected context | Before user answer | Root cause |
| --- | --- | --- | --- |
| `Who is Jung?` | Chunk 69: `A Swiss psychiatrist, founder of the analytical school of psychology, Jung presented...` | Not found | `definition_entity` went through fact-style `who` extraction, produced a short fragment, then OCR/post-answer validation rejected it. |
| `Define behaviorism.` | Selected context included Watson/radical behaviorism evidence | Not found | Deterministic definition path could not synthesize from indirect evidence. |
| `Define structuralism.` | Chunk 36: `Structuralism - The school of thought that focused...` | Not found | Heading + definition fragment rejected as `no_predicate_fragment` / strict definition shape failure. |
| `Define functionalism.` | Chunk 39: `Functionalism An approach that concentrated...` | Not found | Heading + definition fragment rejected because no direct `X is ...` predicate existed. |

Runtime log evidence from the focused probe showed the rejection pattern:

```text
[ANSWER ROUTE] selected=fact family=definition_entity docs=1
[FACT DECISION] type=who final=Marine Engineer ...
[OCR FILTER] rejected=Marine Engineer reason=too_short_fragment
[FINAL CANDIDATE REJECTED] reason=fragmentary_ocr answer=Marine Engineer
```

For heading fragments:

```text
[DEF QUALITY] rejected_reason=no_predicate_fragment sentence=Hydrolexism An approach...
[DEFINITION CANDIDATE REJECTED] reason=entity_or_grounding_validation_failed answer=Hydrolexism An approach...
```

Root-cause confirmation:

- `STRICT DEF PREF`: involved in rejecting non-`X is` candidates.
- `OCR FILTER`: involved for `Who is ...` when fact extraction produced a too-short fragment.
- `FACT DECISION`: involved for `Who is ...` because the route selector chose `fact` despite `family_v2=definition_entity`.
- `Runtime Acceptance`: involved when raw heading fragments were later rejected as invalid definitions.
- `CONCEPT FILTER`, `ENTITY DEF FILTER`, `CONTAMINATION GUARD`: not the primary cause in the confirmed failures.

## Before/After Answers

Final warmed evidence file: `logs/phase14c_final_clean_warm/phase14c_definition_evidence.md`

| Query | Before | After |
| --- | --- | --- |
| `Who is Jung?` | Not found | `Jung was a Swiss psychiatrist, founder of the analytical school of psychology.` |
| `What does the document say about Jung?` | Answered | Answered |
| `Define behaviorism.` | Not found | `Behaviorism is described as a revolutionary, pragmatic approach often known as radical behaviorism.` |
| `Define structuralism.` | Not found | `Structuralism is the school of thought that focused upon the study of mind and conscious experience.` |
| `Define functionalism.` | Not found | `Functionalism is an approach that concentrated on what the mind does...` |
| `What is long-term memory?` | Answered | Answered |
| `What is psychology?` | Answered | Answered |
| `What is classical conditioning?` | Answered | Answered |
| `What is operant conditioning?` | Answered | Answered |
| `What is Gestalt psychology?` | Answered | Answered |

## Latency

The harness records total WebSocket response latency and per-stage timing fields when available. The final clean restart pass proves correctness after `python start_main_servers.py`; the warmed pass is the steady-state latency reference.

| Query | Before total ms | Final warmed total ms | Result |
| --- | ---: | ---: | --- |
| `Who is Jung?` | 595 | 676 | Answer now returned; small added deterministic synthesis cost. |
| `What does the document say about Jung?` | 234 | 242 | Still answered; no meaningful regression. |
| `Define behaviorism.` | 852 | 795 | Improved and now answered. |
| `Define structuralism.` | 452 | 417 | Improved and now answered. |
| `Define functionalism.` | 476 | 409 | Improved and now answered. |
| `What is long-term memory?` | 275 | 271 | Slightly improved. |
| `What is psychology?` | 284 | 284 | No regression. |
| `What is classical conditioning?` | 269 | 272 | No meaningful regression. |
| `What is operant conditioning?` | 339 | 300 | Improved. |
| `What is Gestalt psychology?` | 318 | 312 | Slightly improved. |

Clean restart validation also passed all 10 queries in `logs/phase14c_final_clean/phase14c_definition_evidence.md`.

## Files Changed

- `scripts/phase14c_definition_evidence.py`
  - New investigation/validation harness.
- `backend/retrieval/routing.py`
  - Added generic evidence-preserving definition synthesis.
  - Kept `definition_entity` on the definition route.
  - Added synthesis rescue in post-answer validation.
  - Added row-level minimum-balance fact extraction.
- `tests/test_zero_hardcode_generalization.py`
  - Added generic non-psychology regression tests for descriptor/entity evidence, heading/definition evidence, and no-evidence not-found behavior.

## Tests And Validation

Commands run:

```text
python -m pytest tests\test_zero_hardcode_generalization.py tests\test_kb_rag_final_fixes.py tests\test_kb_rag_real_data_regression.py -q
```

Result:

```text
24 passed, 5 warnings
```

Stack restart and validation:

```text
python start_main_servers.py
python scripts\verify_stack.py
python scripts\phase14c_definition_evidence.py --output-dir logs\phase14c_final_clean
python scripts\phase14c_definition_evidence.py --output-dir logs\phase14c_final_clean_warm
```

Final clean validation:

```text
PASS q1_who_jung
PASS q2_document_jung
PASS q3_define_behaviorism
PASS q4_define_structuralism
PASS q5_define_functionalism
PASS q6_long_term_memory
PASS q7_psychology
PASS q8_classical_conditioning
PASS q9_operant_conditioning
PASS q10_gestalt_psychology
```

## Genericity Assessment

No psychology-specific, Jung-specific, Freud-specific, document-specific, PDF-name-specific, or value-specific logic was added. The new definition synthesis uses only generic query entity extraction plus evidence shapes found in retrieved chunks: descriptor-before-entity, entity-heading followed by a definition fragment, and generic `known as` phrasing. The min-balance fix is column/row-attribute based and derives product names from the query.

## Evidence-Origin Assessment

All returned answers originate from retrieved/selected chunk text. The synthesis path only rearranges retrieved evidence into a readable answer and requires `_is_answer_grounded_in_docs(...)`, entity/reference match, OCR rejection check, and other-concept rejection before returning. The fact fix extracts currency from the matched table row/cell in the supplied evidence.

## Future-Document Compatibility Assessment

The changes are document-agnostic. They support future documents that express definitions through headings, labels, fragments, or descriptor clauses rather than perfect textbook `X is ...` sentences. If no retrieved evidence mentions the queried entity or the synthesized answer cannot be grounded, the pipeline still returns not found.
