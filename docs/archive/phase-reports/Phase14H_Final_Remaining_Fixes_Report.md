# Phase 14H - Final Remaining Fixes Report

## Files Modified

- backend/retrieval/routing.py
- backend/retrieval/generation.py
- tests/test_rag_chunk_retrieval_fixes.py

## Root Cause by Group

**Group A:** Person early guard required First Last names; concept scorer rejected definitional sentences with attribution cues.

**Group B:** SSO queries matched support-procedural, blocking attribute lookup and triggering 40-char fragment rejection on plan label answers.

**Group C:** Currency cell values rejected by _is_evidence_fragment_answer.

**Group D:** Route conflict (definition vs support-procedural), FAQ paraphrase mismatch, fragment floor on policy answers.

## Implementation Summary

- Relaxed surname-led person evidence and concept entity-subject definition paths
- Prioritized reverse table lookups in attribute classification; currency exception for fee queries
- Table blob collapse, glued-table normalization, wide-column rechunk inference
- Support-procedural route priority, FAQ policy synonyms, policy fragment relaxation

## Before / After (unit deterministic)

| Query | After |
|-------|-------|
| Who is Jung? | Identity sentence from biography chunk |
| What is psychoanalysis? | Definitional sentence with clinical description |
| What is analytical psychology? | Multi-token concept definition |
| Which plans support SSO? | Business and Enterprise |
| What is the monthly fee for Business? |  |
| What is the refund policy? | Grounded FAQ/policy sentence |

## Regression Results

64/64 tests passed in tests/test_rag_chunk_retrieval_fixes.py

## Genericity Assessment

Pattern-based only; no entity whitelists or hardcoded answers.

## Evidence-Origin Assessment

All answers from retrieved table cells, sentences, or FAQ pairs.

## Future-Document Compatibility Assessment

Works for new documents with standard biography, definition, table, and FAQ shapes.
