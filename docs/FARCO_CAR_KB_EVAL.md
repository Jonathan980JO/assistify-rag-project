# Farco Car Knowledge Base — Golden Eval Suite

Tenant **Farco** (`tenant_id=3`, slug `adwya`) uses `backend/assets/tenant_3/*_car_knowledge_base.pdf`, indexed into Chroma collection `t3_support_docs_v3_latest`.

This document describes the 18-question golden set used to regression-test retrieval and answers for automotive content.

## Run the eval

```powershell
# Re-index after chunking changes (tenant 3 only)
python scripts/reindex_farco_car_kb.py

# Run all 18 questions (in-process, uses _validate_query_ui_equivalent)
python scripts/farco_car_kb_eval.py
```

Reports are written to:

- `tests/farco_car_kb_eval_report.json`
- `tests/farco_car_kb_eval_report.txt`

### Scoring dimensions

| Metric | Meaning |
|--------|---------|
| **retrieval_pass** | Expected keywords appear in top retrieved chunks |
| **answer_pass** | Final UI-equivalent answer contains keywords and is not a not-found fallback |
| **passed** | Both retrieval and answer pass (strict) |

Restart the RAG server after reindexing so the live WebSocket/UI path picks up the new index.

## Question tiers

### A — Single-fact lookup

| ID | Question | Expected gist |
|----|----------|---------------|
| Q1 | Four phases of four-stroke cycle | Intake, Compression, Power, Exhaust |
| Q2 | Diesel ignition | Compression ignition, no spark plug |
| Q3 | Meaning of 5W in 5W-30 | Winter / cold-flow |
| Q4 | Brake fluid replacement interval | Every 2–3 years, hygroscopic |
| Q5 | 45 in 225/45R17 | Aspect ratio / sidewall % |
| Q6 | 12V battery lifespan | 3–5 years |

### B — Same-section reasoning

| ID | Question | Expected gist |
|----|----------|---------------|
| Q7 | Turbo + premium fuel | Knock / octane |
| Q8 | Grinding brakes | Worn pads, urgent |
| Q9 | AWD vs 4WD | Auto traction vs off-road selectable |
| Q10 | Oil pressure light | Stop driving, lubrication damage |

### C — Cross-section synthesis

| ID | Question | Expected gist |
|----|----------|---------------|
| Q11 | BEV vs FCEV charge time & cost | Minutes vs hours; running cost |
| Q12 | Timing belt interval criticality | 60k–100k mi, engine damage risk |
| Q13 | Diesel vs gas economy | Compression ratio + fuel density |
| Q14 | No multi-speed transmission | BEV, single-speed motor torque |
| Q15 | Two belt-driven systems | Water pump + alternator |

### D — Negative / trap

| ID | Question | Expected behavior |
|----|----------|-------------------|
| Q16 | Sedan tire pressure PSI | Refuse specific PSI; door-jamb sticker |
| Q17 | Solid-state batteries | Not covered |
| Q18 | Spark plugs on EV | Trap — EVs have no spark plugs |

## Tuning notes (2025-06)

Initial baseline after chunk-heuristic fixes:

- **Retrieval** ~14/18 — drivetrain, diesel, four-stroke chunks retrieve correctly.
- **Full pass** lower — answer guards (`generic_low_confidence_blocked`, compare entity parsing, list extraction) often block good chunks.

Tuning applied for this suite:

1. **Chunking** — see [RAG_CHUNK_RETRIEVAL_FIXES.md](./RAG_CHUNK_RETRIEVAL_FIXES.md)
2. **Quality filter** — numbered colon lists (drivetrain bullets) no longer `heading_dominated`; maintenance tables exempt from `number_heavy`
3. **Compare queries** — strip trailing “as described in the document”; shared-chunk path for AWD/4WD-style sections

Remaining gaps are mostly in the **answer synthesis layer** (not retrieval): list questions returning `list_llm_required` + not-found, and definition fast-path blocking short acronym queries.
