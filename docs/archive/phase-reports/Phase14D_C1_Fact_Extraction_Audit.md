# Phase 14D-C1 — Fact Extraction Failure Audit

**Status:** EVIDENCE ONLY. No fixes. No code modifications. No solutions proposed.
**Scope (enforced):** `backend/retrieval/routing.py` only — `_extract_fact_from_context`
(line 11100) and its helpers (`_detect_fact_query_type` 10856, `_extract_relation_subject_terms`
6445, candidate patterns 11142–11149 / 11401–11404, the verb-gate 11391–11396, candidate
scoring 11413, candidate validation 11341 / 11302–11339). NOT investigated: Chroma,
embeddings, ingestion, PDF parsing, tenant routing, topic extraction, compare/summary
queries, streaming, Ollama, timeouts.

**How this evidence was produced (read-only, authoritative):**
`scripts/phase14d_c1_fact_extraction_audit.py` imports the **real** server module
(`backend.assistify_rag_server`, which binds `backend.retrieval.routing`) and calls the
**real, unmodified** `_extract_fact_from_context` over the **exact** reranked chunk texts
captured live in `logs/phase14d_relation_evidence.json`. The extractor's own `[FACT …]`
markers are captured in-memory (Steps 3–5 are the extractor's own output, not a
re-implementation). Steps 1–2 apply the **verbatim** regexes/gate from `routing.py` (with
line citations) to each sentence to explain *why* the real extractor behaved as observed.

**Machine-readable evidence:** `logs/phase14d_c1_fact_extraction.json`

> Note on Step 1 "Top 10 retrieved vs Top 10 reranked": the captured evidence
> (`logs/phase14d_relation_evidence.json`) recorded the **final reranked set** delivered to
> the fact layer (≤5 chunks per query) with `score == rerank_score` for every chunk (verified
> in the JSON). A *separate* pre-rerank top-10 was not captured by the original live harness,
> and per phase scope retrieval/reranking are out of bounds to re-run. Where only N<10 chunks
> exist, all N are shown; retrieved order == reranked order here because `score == rerank_score`.

---

## Executive result

| # | Query | Step 1: evidence present? | Re-driven decision | Category | Death point |
|---|---|:---:|---|:---:|---|
| 1 | Who founded Gestalt psychology? | **YES** (rank 1) | `Wilhelm Wundt` (wrong) | **A** | verb-gate `continue` (routing.py:11395) |
| 2 | Who founded structuralism? | **YES** (rank 1) | `Wilhelm Wundt` (wrong) | **A** | verb-gate `continue` (routing.py:11395) |
| 3 | Who founded behaviorism? | **NO** | `Sigmund Freud` (wrong) | **A0** | upstream retrieval (out of A–F) |
| 4 | Who created psychoanalysis? | **YES** (rank 1) | `None` (abstain) | **C** | validator reject `non_name_morphology` (11317/11341) |
| 5 | Who developed analytical psychology? | **YES** (rank 1) | `None` (abstain) | **A** | verb-gate `continue` (routing.py:11395) |
| 6 | Who proposed classical conditioning? | **NO** (work described, name absent) | `None` (abstain) | **A0** | upstream retrieval (out of A–F) |

**Where valid fact evidence dies (the two dominant mechanisms):**

1. **The attribution-VERB gate (routing.py:11391–11396) kills noun-form founder sentences
   before any pattern runs.** For every query whose text contains a gate verb
   (`established|proposed|developed|founded|introduced` — note: **not** `created`/`coined`),
   each candidate sentence must itself contain a past-tense attribution verb or it is
   `continue`-skipped. Sentences that state authorship with the **noun** ("*The founder of
   Gestalt Psychology*", "*formal founder of Structuralism*", "*founder of the analytical
   school*") have `verb_hit_count == 0` and are discarded — **even though the dedicated
   `founder/creator/originator` pattern at line 11401 would have captured the correct name.**
   Proven below: `founder_noun_re` captures `Max Wertheimer`, but the gate drops the sentence
   first.

2. **Candidate scoring is structurally subject-blind and rank-blind (routing.py:11413).**
   `_extract_fact_from_context(query, context_chunks: List[str])` receives **only text
   strings** — no retrieval score, no rerank score, no rank (call sites: routing.py:1890,
   23439, 23492; chunk list built as strings at 23413–23417). The per-candidate score
   `6.0 + 2.5·overlap + 0.6·subj + 0.8·verb + bonuses` uses only features of the candidate's
   own sentence. After mechanism (1) removes the correct on-subject sentence, an **off-subject**
   Wundt sentence (no "gestalt"/"structuralism" token) wins on the generic token "psychology"
   plus attribution verbs.

---

## Step 1 — Evidence Presence Audit

Source: captured reranked chunks (`score == rerank_score`). "Contains answer?" = the correct
person name appears in the chunk text. Quotes are the answer-bearing sentence(s) as captured.

### 1. Who founded Gestalt psychology?  (correct: Max Wertheimer)
| Rank | chunk_index | rerank_score | Contains answer? | Evidence sentence |
|:---:|:---:|:---:|:---:|---|
| 1 | 43 | 7.738 | **YES** | "*Max Wertheimer • The founder of Gestalt Psychology, born in Prague…*" (also "*Three German psychologists Max Wertheimer, Kurt Koffka and Wolfgang Kohler were regarded as the founders of gestalt school*") |
| 2 | 29 | — | NO | Wilhelm Wundt / emergence-of-schools passage (no "gestalt") |
| 3 | — | — | NO | — |
| 4 | — | — | partial | "*Kurt Koffka • Wrote…Principles of Gestalt Psychology*", "*Wolfgang Kohler*" (co-founders, not the queried founder) |
| 5 | — | — | NO | — |

### 2. Who founded structuralism?  (correct: Edward B. Titchener)
| Rank | chunk_index | Contains answer? | Evidence sentence |
|:---:|:---:|:---:|---|
| 1 | 38 | **YES** | "*…Hugo Munsterberg First to apply psychology to industry and law **Edward B. Tichener Known as the formal founder of Structuralism**…*" (OCR-merged into one run-on segment) |
| 2 | 29 | NO | Wilhelm Wundt emergence passage |
| 3 | 36 | NO | Cognitive Approach passage |

### 3. Who founded behaviorism?  (correct: John B. Watson)
| Rank | chunk_index | Contains answer? | Note |
|:---:|:---:|:---:|---|
| 1 | 75 | **NO** | Thorndike passage |
| 2 | 29 | **NO** | Wundt passage |
| 3 | 38 | **NO** | Cattell/Kraeplin/Munsterberg/Tichener passage |
| 4 | 52 | **NO** | Psychodynamic/Freud passage |
| 5 | 40 | **NO** | Functionalism passage |

The token **"behaviorism" and the name "Watson" appear in NONE of the 5 retrieved chunks.**
→ Retrieval/ingestion gap (upstream; outside the extraction A–F taxonomy).

### 4. Who created psychoanalysis?  (correct: Sigmund Freud)
| Rank | chunk_index | Contains answer? | Evidence sentence |
|:---:|:---:|:---:|---|
| 1 | — | **YES** | "*Demands Deprivation States **Sigmund Freud**: 1856-1939 Physiological Arousals • **Founder of psychoanalysis** Energy For…*" (OCR-contaminated prefix glued to the name) |

### 5. Who developed analytical psychology?  (correct: Carl Gustav Jung)
| Rank | chunk_index | Contains answer? | Evidence sentence |
|:---:|:---:|:---:|---|
| 1 | — | **YES** | "*A Swiss psychiatrist, **founder of the analytical school of psychology, Jung** presented a complex theory of personality.*" |
| 2 | — | partial | "*1913: left the inner circle of Freud's students…although he had chosen **Jung** as his successor.*" |

### 6. Who proposed classical conditioning?  (correct: Ivan Pavlov)
| Rank | chunk_index | Contains answer? | Evidence sentence |
|:---:|:---:|:---:|---|
| 1 | 80 | **NO** | "*Extensions of the Main Classical Conditioning Model…*" (concept, no person) |
| 2 | 78 | **NO** | "*…of classical conditioning. In the later years of the 19th century studied the basic process of digestion and **won Nobel Prize…in 1904**…**salivation reflex in dogs**…*" (Pavlov's work described, **Pavlov never named**) |

The name **"Pavlov" appears in NONE of the retrieved chunks** → upstream retrieval gap.

---

## Step 2 — Attribution Pattern Audit

Patterns tested are the **actual** ones in `_extract_fact_from_context`:
- `verb_person_re` — `NAME … (established|proposed|developed|founded|introduced|created|coined)` (routing.py:11142)
- `passive_person_re` — `(…verbs…) by NAME` (routing.py:11145)
- `founder_noun_re` — `NAME …{0,120} (founder|creator|originator|establisher)` (routing.py:11401, **inside** the `who_patterns` loop)
- `father_re` — `NAME … the father of` (routing.py:11149, **defined but NOT in the loop**)

…and the **gate** that runs *before* the loop (routing.py:11391–11396):
```python
requires_attribution_verb = bool(re.search(r"\b(established|proposed|developed|founded|introduced)\b", q_low))   # 11392
...
verb_hits = _verb_hit_count(sl)                                                                                   # 11394
if requires_attribution_verb and verb_hits == 0 and not re.search(r"\bfather\s+of\b", sl):                        # 11395
    continue                                                                                                       # <-- sentence dropped before who_patterns
```

### 1. Gestalt — answer-bearing sentence "Max Wertheimer • The founder of Gestalt Psychology, born in Prague…"
| Pattern | Matched? | Captured | Note |
|---|:---:|---|---|
| GATE (requires_attribution_verb=True, verb_hits=0, father_of=False) | **DROPS sentence** | — | `continue` at 11395 — patterns below never run |
| `verb_person_re` | NO | — | no attribution verb in sentence |
| `passive_person_re` | NO | — | no "by NAME" |
| `founder_noun_re` | **YES** | **`Max Wertheimer`** | *would* capture the correct name — **but the gate already dropped the sentence** |
| `father_re` | NO | — | (also not in loop) |

**This is the headline proof:** the correct pattern matches the correct name, yet the
sentence is gated out before that pattern is ever executed.

### 2. Structuralism — run-on sentence "…Edward B. Tichener Known as the formal founder of Structuralism…"
| Pattern | Matched? | Note |
|---|:---:|---|
| GATE (req=True, verb_hits=0) | **DROPS sentence** | `continue` at 11395 |
| `founder_noun_re` (if it ran) | would match | OCR run-on may mis-capture the leading name; moot — gate drops first |

### 3. Behaviorism — no answer-bearing sentence exists (Step 1 = NO) → patterns not applicable.

### 4. Psychoanalysis — sentence "Demands Deprivation States Sigmund Freud: 1856-1939 … Founder of psychoanalysis …"
| Pattern | Matched? | Captured | Note |
|---|:---:|---|---|
| GATE | **does NOT fire** | — | "created" ∉ gate regex (11392) ⇒ requires_attribution_verb=False ⇒ sentence kept |
| `founder_noun_re` | **YES** | **`Demands Deprivation States Sigmund Freud`** | positional NAME-capture grabs the OCR-junk prefix together with the name |

### 5. Analytical psychology — sentence "A Swiss psychiatrist, founder of the analytical school of psychology, Jung presented…"
| Pattern | Matched? | Captured | Note |
|---|:---:|---|---|
| GATE (req=True, verb_hits=0) | **DROPS sentence** | — | `continue` at 11395 |
| `founder_noun_re` (if it ran) | YES | **`Swiss psychiatrist`** | captures the descriptor *before* "founder", NOT "Jung" (the name follows the noun) — position-fragile; moot, gate drops first |

### 6. Classical conditioning — no answer-bearing sentence exists (Step 1 = NO) → patterns not applicable.

---

## Step 3 — Candidate Generation Audit

Real extractor `[FACT CANDIDATE]` / `no_candidates` markers (captured):

| Query | Correct candidate generated? | Markers |
|---|:---:|---|
| Gestalt | **NO** | only `candidate=Wilhelm Wundt score=8.883` (chunk 1 emergence sentence) ×2 windows. **Max Wertheimer never generated.** |
| Structuralism | **NO** | only `candidate=Wilhelm Wundt score=7.450` ×2. **Tichener never generated.** |
| Behaviorism | n/a (no evidence) | `Sigmund Freud 8.700`, `Wilhelm Wundt 7.450` ×2 — all off-subject |
| Psychoanalysis | **NO** | no `[FACT CANDIDATE]`; the only attempt was rejected at validation (see Step 4) → `no_candidates` |
| Analytical psychology | **NO** | `no_candidates` (gate dropped every answer-bearing sentence) |
| Classical conditioning | **NO** | `no_candidates` (no name in evidence) |

**Result:** for every query where the correct answer existed in the chunks (1, 2, 4, 5), the
**correct candidate was never generated.**

---

## Step 4 — Candidate Rejection Audit

Real `[FACT PERSON VALIDATOR]` markers (captured):

| Query | Candidate offered to validator | Accepted/Rejected | Reason | Source |
|---|---|:---:|---|---|
| Gestalt | Wilhelm Wundt | Accepted | — | `_validate_candidate("who")` 11341 |
| Structuralism | Wilhelm Wundt | Accepted | — | 11341 |
| Behaviorism | Sigmund Freud | Accepted | — | 11341 |
| **Psychoanalysis** | **`Demands Deprivation States`** | **Rejected** | **`non_name_morphology`** | `_person_candidate_rejection_reason` 11317 |
| Analytical psychology | (none reached validator) | — | gate-dropped upstream | — |
| Classical conditioning | (none) | — | no evidence | — |

**Result:** the validator never rejected a *correct* candidate — because the correct candidate
was never produced. For psychoanalysis the validator correctly rejected the OCR-junk span; the
clean "Sigmund Freud" was never isolated and offered.

---

## Step 5 — Candidate Scoring Audit

Accepted candidates and scores (from `[FACT CANDIDATE]`):

| Query | Candidate | Score | Source chunk_idx (in truncated list) | Retrieval score | Rerank score |
|---|---|---:|:---:|:---:|:---:|
| Gestalt | Wilhelm Wundt | 8.883 | 1 | **not passed to function** | **not passed to function** |
| Structuralism | Wilhelm Wundt | 7.450 | 1 | not passed | not passed |
| Behaviorism | Sigmund Freud | 8.700 | 3 | not passed | not passed |
| Behaviorism | Wilhelm Wundt | 7.450 | 1 | not passed | not passed |

**Does candidate scoring use retrieval rank?  → NO.**
**Does candidate scoring use rerank score?  → NO.**

**Code evidence:**
- Signature receives **only strings**: `def _extract_fact_from_context(query: str, context_chunks: List[str])` (routing.py:11100).
- Call sites pass plain text only, scores stripped: `fact_context_chunks = [str(d.get("page_content") or d.get("text") …) for d in …]` (routing.py:23413–23417) → `_extract_fact_from_context(query, fact_context_chunks)` (23439; also 1890, 23492).
- Score formula uses only sentence-local features:
  ```python
  "score": 6.0 + (2.5 * _keyword_overlap_score(sl)) + (0.6 * float(_subject_hit_count(sl)))
           + (0.8 * float(verb_hits)) + completeness_bonus + clarity_bonus,   # routing.py:11413
  ```
- `chunk_idx` is carried on the candidate and **logged** (11415, 11499–11506) but **never read**
  in any score expression. There is no reference anywhere in the function to `score`,
  `rerank_score`, or `rank` of the source chunk.

**Consequence:** an off-subject candidate from a lower-ranked chunk (e.g. Wundt from chunk_idx
1/2) outscores nothing on subject relevance and is selected purely on generic-token overlap +
verb hits; the original retrieval/rerank ordering has zero influence on which candidate wins.

---

## Step 6 — Root Cause Classification

Taxonomy (per task):
**A** correct evidence exists but no extraction pattern matched · **B** pattern matched but
candidate not generated · **C** candidate generated but rejected · **D** candidate accepted but
lost scoring · **E** candidate won scoring but lost later · **F** multiple failures.
*(A0 = no correct evidence in retrieved chunks — an upstream retrieval gap that falls outside
the A–F extraction taxonomy, which presupposes evidence presence. Recorded for honesty.)*

| Query | Category | Why (one line) |
|---|:---:|---|
| **Who founded Gestalt psychology?** | **A** | Correct sentence present AND `founder_noun_re` captures "Max Wertheimer", but the verb-gate (11395) `continue`-drops the sentence before the pattern loop runs → correct candidate never generated. *(Contributing: subject-/rank-blind scoring 11413 then elevates off-subject "Wilhelm Wundt" → wrong answer surfaces.)* |
| **Who founded structuralism?** | **A** | Tichener sentence present (OCR run-on, verb_hits=0); verb-gate drops it before patterns. *(Contributing: scoring elevates off-subject Wundt from a lower-ranked chunk.)* |
| **Who founded behaviorism?** | **A0** | "Watson"/"behaviorism" in **none** of the retrieved chunks; extraction had no correct evidence. Upstream retrieval gap (out of A–F scope). |
| **Who created psychoanalysis?** | **C** | Gate does NOT fire ("created" ∉ gate regex); `founder_noun_re` matches and **generates** a candidate, but the OCR-glued span "Demands Deprivation States" is **rejected** (`non_name_morphology`); clean "Sigmund Freud" never isolated. |
| **Who developed analytical psychology?** | **A** | "founder of the analytical school…, Jung" present; verb-gate drops it before patterns. *(Pattern is also position-fragile here: it would capture "Swiss psychiatrist", not "Jung".)* |
| **Who proposed classical conditioning?** | **A0** | "Pavlov" named in **no** retrieved chunk (his work is described but unnamed); extraction had no correct evidence. Upstream retrieval gap (out of A–F scope). |

### Where valid fact evidence dies — conclusion (proof only, no fix)

For every query in scope where the answer **was** retrieved (Gestalt, structuralism, analytical
psychology), the valid evidence dies at **the attribution-verb gate, routing.py:11395**, which
`continue`-skips the answer-bearing noun-form sentence **before** the `who_patterns` loop —
even though `founder_noun_re` (11401) is proven to capture the correct name on that exact
sentence. Psychoanalysis dies one stage later (**Category C**): the gate doesn't fire, the
pattern generates a candidate, but OCR contamination makes the captured span fail person-name
validation (`non_name_morphology`, 11317). Behaviorism and classical conditioning are **not
extraction failures at all** — the correct name is absent from the retrieved chunks (**A0**,
upstream retrieval, explicitly out of this phase's scope).

A second, systemic defect compounds the wrong *answers* (as opposed to abstentions): candidate
scoring (**routing.py:11413**) is **structurally** rank-blind and rerank-blind — the function
only ever receives text strings (11100; call sites 23413–23439) — so once the correct
candidate is gone, an off-subject candidate from a lower-ranked chunk wins on generic token
overlap.

---

## Stop condition

Investigation complete. No fixes implemented. No production code modified. No solutions
proposed. Each query is classified with captured, reproducible evidence
(`logs/phase14d_c1_fact_extraction.json`, regenerable via
`PYTHONPATH=. python scripts/phase14d_c1_fact_extraction_audit.py`).
