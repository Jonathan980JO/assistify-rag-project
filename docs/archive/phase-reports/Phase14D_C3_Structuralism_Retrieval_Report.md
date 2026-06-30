# Phase 14D-C3 Structuralism Retrieval Investigation

Status: evidence-only investigation. No code changes were made for this phase.

Query: `Who founded structuralism?`

Tenant used for runtime probes: `tenant_id=3`

## Executive Finding

The Edward Bradford Tichener evidence is not lost by Chroma retrieval, reranking, semantic filtering, quality filtering, fact rescue retrieval, anchor selection, or final context selection.

The first failing stage is relation validation inside anchor selection:

`_prefilter_fact_docs_by_relation(...)`

That function returns `0` valid docs because `_chunk_satisfies_fact_relation_rule(...)` requires a WHO relation sentence to contain a person name, an action verb such as `founded`, `created`, or `developed`, and the query subject term. The answer evidence uses a noun-form relation:

`Edward B. Tichener Known as the formal founder of Structuralism Edward Bradford Tichener ...`

So chunk `38` survives the candidate pool, but it is not recognized as valid relation evidence. Anchor scoring then reorders it behind chunks `36` and `29`, and compact fact context later fragments the evidence into a sentence whose first accepted candidate is the shortened surname `Tichener`.

## Stage Trace

### 1. Chroma Collection Existence

Direct tenant collection probe:

- Collection: `t3_support_docs_v3_latest`
- Collection count: `422`
- Tichener/Structuralism-related matches found: `8`
- Answer-bearing chunk: `doc_e9336e9c82eb08a5_chunk_38`
- Metadata: `chunk_index=38`, `page=19`
- Contains full evidence: `Edward Bradford Tichener`

Evidence preview:

`Introduction to Psychology -PSY101 VU James Mckeen Cattell Known for his work on individual differences and "Mental Tests". Emil Kraeplin Postulated a physical cause of mental illness In 1883, he gave the first classification system of mental disorders Hugo Munsterberg First to apply psychology to industry and law Edward B. Tichener Known as the formal founder of Structuralism Edward Bradford Tichener ...`

Verdict: the chunk exists in Chroma.

### 2. Raw Chroma Candidates Before Reranking

Direct `VectorStore.collection.query(...)` probe with the same E5 query used by the vector store:

- Candidate pool requested: `80`
- Raw Chroma candidates returned: `80`
- Chunk `38` rank before reranking: `1`
- Raw similarity: `0.8112785220146179`
- Full evidence present: `true`

Top raw candidates:

| Raw Rank | Chunk | Similarity | Contains Tichener / Structuralism Evidence |
| ---: | ---: | ---: | :---: |
| 1 | 38 | 0.8112785220146179 | YES |
| 2 | 29 | 0.8077689409255981 | partial/context |
| 3 | 36 | 0.8006539344787598 | partial/context |
| 4 | 42 | 0.798450231552124 | partial/context |
| 5 | 39 | 0.7929359078407288 | partial/context |

Verdict: the answer-bearing chunk is retrieved before reranking, and it is the top raw candidate.

### 3. Reranker Ranking

`VectorStore.search(... enable_rerank=True)` evidence:

- Rerank candidates: `80`
- Rerank prefilter: `before=80 after=80 dropped=0 fallback_used=False`
- Reranker ran: `true`
- Semantic filter after rerank: `before=80 after=3 dropped=77`
- Quality filter: `before=3 after=3 dropped=0`

Post-rerank / post-filter final retrieval results:

| Rank | Chunk | Rerank Score | Final Score | Full Evidence Present |
| ---: | ---: | ---: | ---: | :---: |
| 1 | 38 | 3.740072727203369 | 2.8187651947566437 | YES |
| 2 | 29 | 2.371380090713501 | 1.8588772382845509 | NO |
| 3 | 36 | 0.1293669492006302 | 0.28413794552152216 | NO |

Verdict: reranking promotes chunk `38` to rank 1. Reranking does not remove the answer evidence.

### 4. Semantic Filter

Vector store log evidence:

`[RAG SEMANTIC FILTER] threshold=0.00 before=80 after=3 dropped=77`

The surviving top 3 include chunk `38` as rank 1.

Verdict: semantic filtering does not remove the Tichener chunk.

### 5. Quality Filter

Vector store log evidence:

`[RAG QUALITY FILTER] before=3 after=3 dropped=0 selected=3`

The surviving final results still include chunk `38` as rank 1.

Verdict: quality filtering does not remove the Tichener chunk.

### 6. Fact Rescue

Fact rescue query generation:

`_build_fact_rescue_queries("Who founded structuralism?", []) -> ["Who founded structuralism?"]`

Fact rescue result:

| Rescue Rank | Chunk | Rerank Score | Full Evidence Present |
| ---: | ---: | ---: | :---: |
| 1 | 38 | 3.740072727203369 | YES |
| 2 | 29 | 2.371380090713501 | NO |
| 3 | 36 | 0.1293669492006302 | NO |

Relation validation over rescue docs:

`RESCUE_VALID 0 []`

Verdict: fact rescue retrieves the Tichener chunk, but relation validation rejects all rescue docs because the relation rule does not accept noun-form `known as ... founder` evidence.

### 7. Anchor Selection

Input to anchor selection:

| Input Rank | Chunk | Full Evidence Present |
| ---: | ---: | :---: |
| 1 | 38 | YES |
| 2 | 29 | NO |
| 3 | 36 | NO |

Relation prefilter result:

`RELATION_PREFILTER_VALID 0 []`

Anchor scoring evidence:

| Anchor Rank | Chunk | Anchor Score | Full Evidence Present |
| ---: | ---: | ---: | :---: |
| 1 | 36 | 1.3926 | NO |
| 2 | 29 | 1.2288 | NO |
| 3 | 38 | 0.8728 | YES |

Anchor selection output:

`ANCHOR_SELECTED [(1, 36, 'strict_relation', False), (2, 29, 'strict_relation', False), (3, 38, 'strict_relation', True)]`

Verdict: anchor selection does not remove chunk `38`, but this is the first stage that damages priority. Chunk `38` falls from retrieval rank 1 to anchor rank 3 because relation prefilter fails and generic anchor scoring prefers chunks `36` and `29`.

### 8. Final Context / Compact Fact Context

Compact fact context generated from anchored docs:

| Context Rank | Source Chunk | Full Evidence Present | Preview |
| ---: | ---: | :---: | --- |
| 1 | 29 | NO | This school founded by the American psychologist William James, became prominent in the1900s. |
| 2 | 36 | NO | Earlier Schools of Thought Structuralism ... |
| 3 | 29 | NO | The following early approaches or conceptual models ... Structuralism ... |
| 4 | 38 | YES | Tichener Known as the formal founder of Structuralism Edward Bradford Tichener ... |
| 5 | 38 | NO | It was Mentalistic Structuralism studied only verbal reports ... |

Extractor trace over compact context:

- Candidate 1: `Tichener`
- Candidate 2: `Edward Bradford Tichener`
- Observed decision in probe: `Tichener`

Verdict: final compact context still contains full evidence in context item 4. The chunk is not removed. The failure is that upstream relation validation/anchor selection lets unrelated or definition-style snippets outrank chunk `38`, and the compact sentence from chunk `38` begins with surname-only `Tichener`.

## First Loss Point

The Tichener chunk itself never disappears.

The first stage where relation authority is lost is:

`_prefilter_fact_docs_by_relation(...)`

Evidence:

`RELATION_PREFILTER_VALID 0 []`

Reason:

`_chunk_satisfies_fact_relation_rule(...)` only accepts a WHO relation sentence when it contains:

- a likely person name
- an action verb from `proposed|developed|introduced|established|founded|created|coined|considered`
- the query subject term

The answer sentence has a noun-form relation:

`Known as the formal founder of Structuralism`

That is not accepted by the relation rule. As a result:

1. Relation prefilter rejects chunk `38`.
2. Relation rescue also retrieves chunk `38` but validates `0` docs.
3. Anchor scoring falls back to the original pipeline.
4. Chunk `38` is demoted from retrieval rank 1 to anchor rank 3.
5. Compact context still includes chunk `38`, but its extracted sentence begins with surname-only `Tichener`.

## Direct Answers

1. Whether the chunk containing Edward Bradford Tichener exists in Chroma:

Yes. It exists in tenant collection `t3_support_docs_v3_latest`, chunk `38`, page `19`, document id `doc_e9336e9c82eb08a5_chunk_38`.

2. Whether the chunk is retrieved before reranking:

Yes. Raw Chroma query ranks chunk `38` at rank `1` with similarity `0.8112785220146179`.

3. Whether the chunk is removed during reranking:

No. Reranking keeps chunk `38` at rank `1` with rerank score `3.740072727203369`.

4. Whether the chunk survives retrieval but is removed by semantic filter, quality filter, relation rescue, or anchor selection:

It survives semantic filter, quality filter, fact rescue retrieval, anchor selection, and final context. It is not removed. The relation prefilter and rescue validator fail to recognize it as relation evidence, and anchor selection demotes it.

5. First stage where Tichener evidence is lost:

No stage loses the chunk. The first stage where relation authority is lost is `_prefilter_fact_docs_by_relation(...)`, because noun-form `known as ... founder of Structuralism` does not satisfy the current relation rule.

## Genericity Assessment

This investigation used only generic evidence properties: collection membership, raw vector rank, rerank score, filter counts, relation-rule predicates, chunk ids, and retrieved text. It did not depend on a hardcoded answer path or document-specific logic.

## Evidence-Origin Assessment

All claims originate from retrieved document evidence in tenant `3` Chroma and the live retrieval pipeline outputs. The answer-bearing evidence is chunk `38`, page `19`, containing `Edward B. Tichener Known as the formal founder of Structuralism Edward Bradford Tichener ...`.

## Future-Document Compatibility Assessment

The finding generalizes beyond this psychology PDF: any future document using noun-form attribution such as `known as the founder of`, `formal founder of`, or similar role-noun phrasing may be retrieved successfully but fail relation validation if the relation rule only accepts verb-form attribution.
