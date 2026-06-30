# Phase 14D-C1 — Counterfactual Fix Simulation (read-only, no fixes)

**Status:** INVESTIGATION ONLY. No production code modified. No edits to `routing.py`.
No fixes implemented. No commits.

**Method (and why it is trustworthy):**
`scripts/phase14d_c1b_counterfactual_matrix.py` builds a **verbatim mirror** of the
WHO-branch of `_extract_fact_from_context` (closures copied with line citations from
`backend/retrieval/routing.py`; module-level name helpers imported from the real module).
Before any counterfactual is trusted, the harness runs a **fidelity gate (STEP 0)**: it
executes the mirror in baseline mode and asserts it reproduces the **real** extractor's
current decision for all six audit queries. It does — exactly:

```
[OK] Gestalt        mirror='Wilhelm Wundt'  real='Wilhelm Wundt'
[OK] structuralism  mirror='Wilhelm Wundt'  real='Wilhelm Wundt'
[OK] behaviorism    mirror='Sigmund Freud'  real='Sigmund Freud'
[OK] psychoanalysis mirror=None             real=None
[OK] analytical     mirror=None             real=None
[OK] classical cond mirror=None             real=None
```

Because the baseline mirror == the live extractor, the single-lever perturbations below
are faithful what-ifs of the real code path.

**The three levers (each toggles exactly one behavior of `routing.py`):**

| Lever | What it simulates | Exact code point neutralized/added |
|---|---|---|
| **GATE** | disable the attribution-verb gate | skip the `continue` at routing.py:11395 |
| **OCR** | ignore OCR corruption | feed de-corrupted chunk text (junk tokens removed / dropped sentence boundary restored); **no reordering, no rewording** |
| **RANK** | rank-aware scoring | add `rank_weight·(N−rank+1)` to the score (routing.py:11413 is currently rank-blind) |

**Machine-readable evidence:** `logs/phase14d_c1b_counterfactual_matrix.json`
(per-mode winning candidate, all candidates, scores, source rank, sentence).

---

## The Matrix

Legend: ✅ correct · ❌ wrong person · ∅ abstain (returns None)

| Query | Current | Gate Only | OCR Only | Rank Only | Gate+Rank | OCR+Rank | All Fixes |
|---|---|---|---|---|---|---|---|
| **Who founded Gestalt psychology?** | ❌ Wilhelm Wundt | ✅ **Max Wertheimer** | ❌ Wilhelm Wundt | ❌ Wilhelm Wundt | ✅ Max Wertheimer | ❌ Wilhelm Wundt | ✅ Max Wertheimer |
| **Who founded structuralism?** | ❌ Wilhelm Wundt | ❌ Wilhelm Wundt | ❌ Wilhelm Wundt | ❌ Wilhelm Wundt | ❌ Wilhelm Wundt | ❌ Wilhelm Wundt | ✅ **Edward B. Tichener** |
| **Who created psychoanalysis?** | ∅ None | ∅ None | ✅ **Sigmund Freud** | ∅ None | ∅ None | ✅ Sigmund Freud | ✅ Sigmund Freud |
| **Who developed analytical psychology?** | ∅ None | ∅ None | ∅ None | ∅ None | ∅ None | ∅ None | ∅ None |

*(The harness also computes the `Gate+OCR` two-lever combo, recorded in the JSON. For
structuralism `Gate+OCR` = ✅ Edward B. Tichener at score 8.500 vs Wundt 7.450 — i.e.
rank is **not** required; "All Fixes" succeeds only because it includes Gate+OCR.)*

---

## Per-query trace (chunk → candidate → rejection → winner → answer)

### 1. Who founded Gestalt psychology? — answer in **chunk rank 1**
- **Chunk w/ answer (rank 1):** *"Max Wertheimer • The founder of Gestalt Psychology, born in Prague…"* (clean — no OCR damage)
- **Current:** the answer sentence has `verb_hit_count=0`; the verb-gate (11395) `continue`-drops it **before** patterns run. Only surviving candidate = off-subject *Wilhelm Wundt* (rank-2 chunk, "…established…by founding…"). Winner **Wilhelm Wundt** ❌.
- **Gate Only:** gate removed → `founder_noun_re` (11401) captures **Max Wertheimer**; validated; score **9.517** (subject overlap "gestalt"+"psychology"=1.0) beats Wundt **8.883**. Winner **Max Wertheimer** ✅.
- **OCR Only:** no OCR fault here → identical to current ❌.
- **Rank Only:** Wertheimer still gate-dropped, so rank can only reorder Wundt-vs-Wundt → ❌.
- **Minimal change → GATE (single).**

### 2. Who founded structuralism? — answer in **chunk rank 1**
- **Chunk w/ answer (rank 1):** *"…Edward B. Tichener Known as the formal founder of Structuralism…"* — but OCR **dropped the sentence periods**, merging Cattell/Kraeplin/Munsterberg/Tichener into one **453-char** run-on.
- **Current / Gate Only:** the run-on is **453 > 360**, so the length filter (11382) skips it **before** the gate even applies. Gate removal alone changes nothing — the sentence is already gone. Winner **Wilhelm Wundt** ❌.
- **OCR Only:** restoring the boundary yields *"Edward B. Tichener known as the formal founder of Structuralism."* (≤360) — but the **gate** then drops it (`verb_hit_count=0`). Winner **Wilhelm Wundt** ❌.
- **Gate + OCR:** boundary restored *and* gate removed → `founder_noun_re` captures **Edward B. Tichener**, score **8.500** > Wundt **7.450**. Winner ✅. (Rank not needed.)
- **Minimal change → GATE + OCR (two changes).** Each alone is insufficient: OCR removes the length-filter block; GATE removes the noun-form block. Both blocks sit on the same sentence.

### 3. Who created psychoanalysis? — answer in **chunk rank 1**
- **Chunk w/ answer (rank 1):** *"Demands Deprivation States **Sigmund Freud**: 1856-1939 Physiological Arousals • **Founder of psychoanalysis** Energy For…"* — interleaved column bleed-through glued to the name.
- **Current:** gate does **not** fire ("created" ∉ gate regex, 11392), so patterns run; `founder_noun_re` captures the contaminated span **"Demands Deprivation States Sigmund Freud"**; name-normalization → **"Demands Deprivation States"**, **rejected** `non_name_morphology` (11317). No candidate → **None** ∅.
- **OCR Only:** remove the junk tokens (no reordering) → *"Sigmund Freud: 1856-1939 Founder of psychoanalysis…"*; `founder_noun_re` captures **Sigmund Freud**; validated. Winner **Sigmund Freud** ✅.
- **Gate Only / Rank Only:** irrelevant — the gate isn't the blocker and rank can't rescue a rejected candidate → ∅.
- **Minimal change → OCR (single).**

### 4. Who developed analytical psychology? — answer in **chunk rank 1**
- **Chunk w/ answer (rank 1):** *"A Swiss psychiatrist, **founder of** the analytical school of psychology, **Jung** presented…"* — name **after** the role noun.
- **Current:** gate fires ("developed"), `verb_hit_count=0` → sentence dropped → **None** ∅.
- **Gate Only:** sentence survives, but `founder_noun_re` is positional `NAME …{0,120} founder` — it captures the tokens **before** "founder" = **"Swiss psychiatrist"** (a descriptor), which is rejected. "Jung" sits *after* "founder" and is never captured → **None** ∅.
- **OCR / Rank / every combo:** same structural mismatch → **None** ∅ in all 7 modes.
- **Minimal change → NONE of GATE/OCR/RANK.** Root cause is a **missing extraction pattern** (no "role-noun + NAME" / name-after-role pattern). This is a *latent* failure, not a wrong answer — the deterministic extractor abstains.

---

## Answers to the five questions

### 1. Which single change fixes each query?
| Query | Minimal fix | Note |
|---|---|---|
| Gestalt | **GATE** (single) | correct sentence + correct pattern already present; only the gate blocks it |
| Structuralism | **GATE + OCR** (two) | OCR removes the 453-char length-filter block; GATE removes the noun-form block |
| Psychoanalysis | **OCR** (single) | gate already inactive for "created"; junk removal lets the pattern capture Freud |
| Analytical | **none of the three** | needs a new name-after-role extraction pattern (out of these levers) |

### 2. Which single change fixes the most queries overall?
**GATE.** It outright fixes Gestalt and is a *required* component of the structuralism fix —
i.e. GATE participates in **2 of the 3 fixable** queries. OCR outright fixes psychoanalysis
and is the other half of structuralism (also 2 of 3). But as a **standalone single lever**,
GATE and OCR each fully resolve exactly **one** query (Gestalt; psychoanalysis respectively);
no single lever resolves two queries on its own. RANK resolves **zero**.

### 3. Does rank blindness actually cause any observed failures?
**No.** In every row, `Rank Only` equals `Current`, and `Gate+Rank` / `OCR+Rank` never beat
`Gate` / `OCR` alone. Where the correct candidate exists *and* survives extraction, it
**already outscores** the off-subject Wundt candidate on its own subject-overlap term
(Gestalt 9.517 > 8.883; structuralism 8.500 > 7.450) — so rank weighting is never the
deciding factor. Rank blindness is a real design weakness (scoring is structurally
rank-/rerank-blind, routing.py:11413, signature 11100) but it is **not the cause of any of
the four observed failures**. Its damage is *masked* because the correct candidate is
eliminated upstream (gate/length/OCR) before scoring matters.

### 4. Would deterministic fact extraction still be safe after the best fix?
**Yes, with a caveat.** Disabling the gate does **not** weaken person-name validation: every
candidate still passes `_person_candidate_rejection_reason` (11302). In simulation, removing
the gate produced **no new wrong answers** in any of the four queries — it converted
Gestalt from wrong→correct and left the others unchanged. The gate's *intended* job
(suppressing non-attribution noise) is largely redundant with the existing `who_patterns` +
person validator, which already require an attribution verb/role-noun structurally. **Caveat:**
this was simulated on these 4 queries only; a gate change is broad and should be regression-
tested against the full fact-query suite before trusting it in production (per scope, not done
here).

### 5. Which fix should be implemented first?
**GATE first** (highest value, lowest blast-radius-per-query-fixed):
- It is the **sole** fix needed for Gestalt and a **necessary half** of structuralism.
- It is a one-line behavioral change (the `continue` at 11395) rather than new infrastructure.
- It introduced **zero** regressions in simulation.

Recommended sequencing (evidence-based, not an instruction to implement now):
1. **GATE** — unblocks the most queries; safest single change.
2. **OCR normalization** — unblocks psychoanalysis outright and completes structuralism;
   higher effort (ingestion/parsing territory, partly outside this module's scope).
3. **New name-after-role pattern** — required for analytical; smallest reach, do last.
4. **RANK-aware scoring** — fixes nothing observed here; defer (treat as robustness hardening,
   not a bug fix).

---

## Stop condition

Evidence produced. No production code changed, no `routing.py` edits, no fixes implemented,
no commits. Matrix and per-mode candidate evidence regenerable via
`PYTHONPATH=. python scripts/phase14d_c1b_counterfactual_matrix.py`
→ `logs/phase14d_c1b_counterfactual_matrix.json`.
