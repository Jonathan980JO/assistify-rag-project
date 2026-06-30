# Phase 14D-A Relation & Topic Extraction Audit Report

## Executive Summary

Phase 14D-A was executed as an investigation-only audit. No retrieval, routing, ingestion, embedding, tenant, definition, summary, overview, upload, or Ollama behavior was modified.

The evidence harness was created at `scripts/phase14d_relation_evidence.py` and produced:

- `logs/phase14d_relation_evidence.json`
- `logs/phase14d_relation_evidence.md`

The first harness run followed `/kb_status` and selected tenant `1`, whose active corpus was the Meridian support corpus rather than the psychology corpus. That run proved the generic tenant-preference behavior but was not useful for the requested relation/topic audit. The audit evidence below is from the explicit tenant `3` run, which targets the uploaded psychology document evidence.

The main findings:

- Relation extraction failures are not caused by Chroma, embeddings, ingestion, or tenant isolation. Retrieved evidence often contains the answer, but the fact extractor either captures descriptor fragments as names, selects a competing candidate, or fails when the relation is expressed without a strict `founded/proposed/developed` verb.
- Topic extraction failures are concentrated in the `list_entity` path. The retrieved chunks often include structural metadata such as `title`, `chapter`, `section`, and `heading`, but the list extractor synthesizes answers from body text only and returns not-found or narrow local lists.
- Trace marker capture from `logs/rag.log` returned no marker lines during the run. The root-cause mapping therefore uses `/rag/retrieve-debug`, WebSocket responses, metadata, latency, and the mapped code paths.

## Relation Extraction Findings

Relation queries classify as `fact_entity` and `fact_type=who`.

Relevant code paths:

- `backend/retrieval/routing.py`
  - `_detect_fact_query_type(...)` lines 10818-10846
  - `_extract_fact_route_answer(...)` starts at line 1832
  - `_extract_fact_from_context(...)` starts at line 11062
  - `person_name_re`, `verb_person_re`, `passive_person_re` lines 11102-11108
  - `_normalize_person_name(...)` lines 11214-11253
  - `_person_candidate_rejection_reason(...)` lines 11255-11285

Key root-cause evidence:

```text
person_name_re = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b"
verb_person_re = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})...(?:established|proposed|developed|founded|introduced|created|coined)\b"
```

The name normalizer then keeps the last three tokens:

```text
if len(use) > 3:
    use = use[-3:]
```

That explains outputs such as `American Psychologist William` and `Deprivation States Sigmund`: capitalized descriptor fragments pass as names and are truncated/normalized as if they were person names.

## Topic Extraction Findings

Topic queries classify as `list_entity`.

Relevant code paths:

- `backend/retrieval/routing.py`
  - `_is_targeted_list_question(...)` lines 17065-17108
  - `_classify_query_family_v2(...)` lines 17147-17193
  - `list_entity` branch in `_shared_rag_final_answer_decision(...)` lines 23775-23891
  - `_extract_list_from_context(...)` lines 24749 onward
  - `_extract_document_headings(...)` lines 8830-8870, metadata-aware but used by overview/summary paths, not the `list_entity` answer synthesis

The `list_entity` extractor reads chunk body text:

```text
deterministic_list = _extract_list_from_context(query, list_context, ...)
single_ctx = str((d_single or {}).get("page_content") or (d_single or {}).get("text") or "")
```

Metadata-aware heading extraction exists elsewhere:

```text
for key in ("unit", "chapter", "section", "title"):
    value = ... md.get(key) ...
```

But that path is not used to synthesize topic answers for the audited `list_entity` queries. This explains the topic failures where retrieved chunks contain `title`, `chapter`, or `heading` metadata but the user receives not-found.

## Root Cause Table

| Query | Answer Produced | Result | Category | Responsible Function |
| --- | --- | --- | --- | --- |
| `Who founded behaviorism?` | `American Psychologist William` | Wrong answer | Relation A: retrieval did not contain the answer-bearing relation; extractor still chose irrelevant capitalized text | `_extract_fact_from_context`, `_normalize_person_name` |
| `Who founded functionalism?` | Not found UX | Failed | Relation D: retrieved text contains `William James` as the leading precursor of functionalist psychology, but extraction requires a stricter attribution relation | `_extract_fact_from_context` |
| `Who founded Gestalt psychology?` | `Wilhelm Wundt` | Wrong answer | Relation C: retrieved rank 1 contains `Max Wertheimer` / Gestalt founders, but a competing `Wilhelm Wundt` candidate was selected | `_extract_fact_from_context` candidate ranking |
| `Who founded structuralism?` | `American Psychologist William` | Wrong/truncated answer | Relation B: answer evidence includes `Edward B. Tichener` / `Edward Bradford Tichener`, but extraction returned a descriptor/name fragment | `_normalize_person_name`, `_person_candidate_rejection_reason` |
| `Who created psychoanalysis?` | `Deprivation States Sigmund` | Wrong/truncated answer | Relation B: evidence contains `Founded by Sigmund Freud`, but name extraction captured preceding heading/table words | `_normalize_person_name`, `person_name_re` |
| `Who developed analytical psychology?` | `Carl Gustav Jung` | Passed, slow | No failure: answer originates from retrieved Jung evidence | `_extract_fact_from_context` |
| `Who proposed classical conditioning?` | Not found UX | Failed | Relation A: retrieved chunks mention classical conditioning details but do not include an answer-bearing person name in captured evidence | Retrieval evidence for this query |
| `List major topics in this document` | Not found UX | Failed | Topic B: structural metadata exists but is ignored by topic synthesis | `list_entity` branch, `_extract_list_from_context` |
| `What subjects are covered?` | Not found UX | Failed | Topic B: retrieved chunks include heading/title metadata, but the extractor attempts body-text list extraction | `list_entity` branch, `_extract_list_from_context` |
| `What chapters are covered?` | Not found UX | Failed | Topic B: `chapter`/`title` metadata appears in retrieved chunks but is not used to form a chapter/topic list | `list_entity` branch, `_extract_list_from_context` |
| `What are the main concepts?` | `Here are the steps... Artificial concepts...` | Partial/local answer | Topic C: extractor reads a local body list under `Concepts`, not document-level topics | `_extract_list_from_context` |
| `What are the major themes?` | `The major themes include personal and collective unconscious,` | Partial/local answer, high latency | Topic C: fallback reads local body text and returns a fragment, not an evidence-based topic list | `list_entity` / fallback generation path |

## Evidence Per Query

### `Who founded behaviorism?`

- Final answer: `American Psychologist William`
- Latency: `757 ms`
- Retrieval evidence: top chunks include Thorndike, Wundt, structuralism, Freud, and William James evidence, but no answer-bearing behaviorism-founder text was retrieved.
- Failure category: Relation A, with secondary symptom of name-boundary over-capture.

### `Who founded functionalism?`

- Final answer: not-found UX
- Latency: `6332 ms`
- Retrieval evidence: chunk 40 contains `William James He was the leading precursor of functionalist psychology`.
- Failure category: Relation D. The answer-bearing person is present, but the relation is phrased as `leading precursor`, not as a strict `founded by` pattern.

### `Who founded Gestalt psychology?`

- Final answer: `Wilhelm Wundt`
- Latency: `559 ms`
- Retrieval evidence: rank 1 contains `Three German psychologists Max Wertheimer, Kurt Koffka and Wolfgang Kohler were regarded as the founders of gestalt school` and `Max Wertheimer "  The founder of Gestalt Psychology`.
- Failure category: Relation C. Correct evidence was retrieved, but the selected candidate was from a competing retrieved chunk.

### `Who founded structuralism?`

- Final answer: `American Psychologist William`
- Latency: `507 ms`
- Retrieval evidence: rank 1 contains `Edward B. Tichener Known as the formal founder of Structuralism Edward Bradford Tichener`.
- Failure category: Relation B. Candidate extraction/normalization returned a descriptor fragment instead of the person name.

### `Who created psychoanalysis?`

- Final answer: `Deprivation States Sigmund`
- Latency: `398 ms`
- Retrieval evidence: rank 1 contains `Founder of psychoanalysis` and `Sigmund Freud`.
- Failure category: Relation B. Candidate extraction captured preceding words and truncated the full name.

### `Who developed analytical psychology?`

- Final answer: `Carl Gustav Jung`
- Latency: `15880 ms`
- Retrieval evidence: rank 1 metadata title is `2. Carl Gustav Jung (1875-1961)` and text says `founder of the analytical school of psychology`.
- Failure category: none. Correct answer, but latency is high relative to other deterministic fact answers.

### `Who proposed classical conditioning?`

- Final answer: not-found UX
- Latency: `15955 ms`
- Retrieval evidence: returned chunks describe classical conditioning and salivation/dogs, but captured evidence does not include the person name.
- Failure category: Relation A. Retrieval evidence did not contain the answer-bearing person.

### `List major topics in this document`

- Final answer: not-found UX
- Latency: `636 ms`
- Retrieval evidence: chunks include structural metadata such as `chapter=Chapter 1`, `title=6. Sociocultural Perspective`, `title=1. Psychodynamic Approach`, and `title=2. Concepts`.
- Failure category: Topic B. Metadata exists but the topic extractor ignores it.

### `What subjects are covered?`

- Final answer: not-found UX
- Latency: `771 ms`
- Retrieval evidence: chunks include headings/titles such as `3. Field Experiments`, `5. Projective tests`, `2. Concepts`, and body text under `Popular areas of psychology`.
- Failure category: Topic B. Metadata and headings exist but are not synthesized.

### `What chapters are covered?`

- Final answer: not-found UX
- Latency: `678 ms`
- Retrieval evidence: chunks include `chapter=Chapter 1` and title metadata such as `1. Psychodynamic Approach`, `3. Old Age`, `5. Projective tests`, and `2. Concepts`.
- Failure category: Topic B. Chapter/title metadata exists but the list path reads body text only.

### `What are the main concepts?`

- Final answer: `Here are the steps from our help materials: - A rtificial concepts - Natural concepts - Prototype concepts`
- Latency: `618 ms`
- Retrieval evidence: rank 1 contains a local list under `Concepts`.
- Failure category: Topic C. The extractor only reads local body text and returns a narrow concept-type list, not document-level main concepts.

### `What are the major themes?`

- Final answer: `The major themes include personal and collective unconscious,`
- Latency: `31276 ms`
- Retrieval evidence: rank 1 is local Jung/psychodynamic material with `Main concepts Conscious and Unconscious`.
- Failure category: Topic C. The fallback returns a local fragment rather than synthesizing document-level topics.

## Latency Findings

| Query | Total ms |
| --- | ---: |
| `Who founded behaviorism?` | 757 |
| `Who founded functionalism?` | 6332 |
| `Who founded Gestalt psychology?` | 559 |
| `Who founded structuralism?` | 507 |
| `Who created psychoanalysis?` | 398 |
| `Who developed analytical psychology?` | 15880 |
| `Who proposed classical conditioning?` | 15955 |
| `List major topics in this document` | 636 |
| `What subjects are covered?` | 771 |
| `What chapters are covered?` | 678 |
| `What are the main concepts?` | 618 |
| `What are the major themes?` | 31276 |

Fast wrong answers indicate deterministic extraction returned bad candidates. Slow fact/topic answers indicate deterministic extraction likely failed and later fallback work occurred.

## Audit Review Gate

The 80% same-root-cause gate is not met for relation extraction. Relation failures split across retrieval absence, candidate truncation/name-boundary failure, candidate ranking, and relation-pattern failure.

Topic extraction failures do cluster around one theme: the `list_entity` topic path ignores structural metadata and relies on body-text list extraction. However, the attached Phase 14D-A plan explicitly requires stopping after the audit report unless implementation is approved.

## Artifacts Created

- `scripts/phase14d_relation_evidence.py`
- `logs/phase14d_relation_evidence.json`
- `logs/phase14d_relation_evidence.md`
- `Phase14D_Audit_Report.md`

No production code paths were modified.

## Genericity Assessment

The investigation harness is document-agnostic. It uses only query text, retrieved chunks, metadata returned by retrieval-debug, WebSocket responses, and generic log marker matching. It does not contain entity-specific scoring, PDF-name checks, or document-specific routing logic. The explicit tenant `3` run was an audit execution choice to target the uploaded evidence corpus and did not modify tenant routing behavior.

## Evidence-Origin Assessment

All audit conclusions originate from retrieved evidence and WebSocket outputs captured in `logs/phase14d_relation_evidence.json` and `.md`. Wrong answers such as `American Psychologist William` and `Deprivation States Sigmund` are shown against the retrieved chunks that caused them. Topic failures are grounded in retrieved metadata and body text, not assumptions about the PDF.

## Future-Document Compatibility Assessment

The audit findings are generic and apply to future documents. Relation failures come from capitalization-based person extraction, name-boundary normalization, relation-pattern coverage, and candidate ranking. Topic failures come from a structural mismatch: metadata exists but the `list_entity` extractor synthesizes from body text only. These are document-agnostic failure modes and do not depend on psychology-specific entities or known answers.
