# Phase 14G Report

Live: 34/45 passed
Unit: 15/15 passed

See routing.py changes for Groups A-F.

## Files Modified
- backend/retrieval/routing.py
- backend/spelling_fallback.py
- tests/test_rag_chunk_retrieval_fixes.py
- scripts/phase14g_attribute_reliability_validation.py

## Genericity Assessment
Evidence-driven table/FAQ/person guards; no hardcoded entities or answers.

## Evidence-Origin Assessment
Answers from retrieved chunk cells, FAQ pairs, or procedural sentences.

## Future-Document Compatibility
Glued-table normalization and header synonym groups are domain-agnostic.
