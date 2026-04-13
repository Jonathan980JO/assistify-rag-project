\# Assistify RAG Project — Mandatory AI Agent Rules



\## Purpose

This project is a real generic RAG system.  

The AI agent must NEVER solve failures by hardcoding answers, document-specific words, or fake logic that bypasses real retrieval and grounding.



\---



\## CORE NON-NEGOTIABLE RULES



\### 1) No hardcoded answers

The agent must never add:

\- fixed answers to specific questions

\- prewritten definitions for known terms

\- manual answer dictionaries

\- hidden canned responses

\- question → answer mappings

\- special-case outputs for known evaluation questions



Forbidden examples:

\- if "what is psychology" in query: return ...

\- if query contains "six goals of psychology": return ...

\- if query == "what is structuralism": return ...

\- HARDCODED\_FAQ = {...}

\- TERM\_DEFINITIONS = {...}



\---



\### 2) No document-specific cheating

The agent must never inject words, phrases, entities, concepts, chapter names, or domain terms taken from a known PDF just to make retrieval or answering look better.



This includes:

\- psychology-specific words

\- management-specific words

\- philosophy-specific words

\- literature-specific words

\- names of people, theories, models, chapters, acts, scenes, or topics copied from a tested PDF



The system must stay domain-agnostic and document-agnostic.



\---



\### 3) No fake “smart” fallback

If the answer is not grounded in retrieved context, the system must return exactly:



`Not found in the document.`



The agent must not:

\- guess

\- complete from model memory

\- use prior knowledge

\- synthesize unsupported answers

\- generate “probably” answers

\- use broad educational knowledge to fill missing retrieval



\---



\### 4) Retrieval must be the source of truth

All final answers must come from retrieved document evidence.

The agent may improve:

\- chunking

\- ranking

\- filtering

\- context focusing

\- extraction

\- sentence cleaning

\- OCR cleanup

\- grounding checks

\- confidence thresholds



The agent may NOT bypass retrieval by writing direct answer logic.



\---



\### 5) No query-triggered shortcuts

The agent must never implement logic like:

\- if query contains definition words, return first sentence

\- if query contains "list", return handcrafted bullets

\- if query contains known course words, route to custom hardcoded branch

\- if query contains known evaluation questions, apply special behavior



Allowed: generic intent handling  

Forbidden: domain/test-question-specific handling



\---



\### 6) No hidden domain lexicons for passing tests

The agent must not create:

\- special keyword boosts for one tested PDF only

\- domain-only regexes tied to a known file

\- handpicked concept lists from psychology/management/etc.

\- manual whitelists/blacklists designed to pass current questions only



Allowed only if fully generic across domains:

\- generic heading detection

\- generic definition cues

\- generic list markers

\- generic OCR cleanup

\- generic sentence scoring



\---



\### 7) All fixes must be generic

Any new logic must generalize across different document types:

\- academic notes

\- technical PDFs

\- business material

\- literature

\- scanned OCR PDFs

\- structured and unstructured documents



Before writing code, the agent must ask:

“Would this still make sense for an unrelated PDF in another domain?”

If no, do not implement it.



\---



\### 8) Preserve strict out-of-scope behavior

If retrieval evidence is weak, mixed, irrelevant, or absent:

return exactly:



`Not found in the document.`



Do not weaken this rule for nicer-looking answers.



\---



\### 9) Ban cheating patterns explicitly

The agent must not introduce any of the following patterns anywhere in the codebase:



\- `if "<topic>" in query: return ...`

\- `elif query == "...":`

\- dictionaries of known questions/answers

\- domain term banks copied from tested PDFs

\- fallback definitions from model knowledge

\- baked-in bullets for “goals”, “advantages”, “types”, “steps”

\- special casing for psychology, management, philosophy, literature, etc.

\- answering from prior conversation instead of current retrieved evidence

\- silent retry with fabricated answer when retrieval fails



\---



\### 10) Allowed areas for improvement

The agent SHOULD focus on real improvements only:

\- retrieval quality

\- ranking quality

\- reranking logic

\- context trimming/focusing

\- sentence extraction quality

\- list extraction quality

\- OCR cleanup

\- duplicate suppression

\- better grounding validation

\- latency-safe generic improvements

\- stricter evidence scoring

\- stale-state / active-document consistency fixes

\- collection/document refresh correctness



\---



\## REQUIRED VALIDATION BEFORE ANY CODE CHANGE



Before making edits, the agent must verify:



1\. Is this change generic?

2\. Does it depend on specific document vocabulary?

3\. Does it add a fake shortcut?

4\. Does it answer without retrieved evidence?

5\. Would it still work on a completely different PDF?

6\. If retrieval fails, does it still return exactly `Not found in the document.`?



If any answer is unsafe, the change must be rejected.



\---



\## REQUIRED CLEANUP TASK

When reviewing existing code, the agent must search for and remove:

\- hardcoded topic words

\- domain-specific answer logic

\- fake fallbacks

\- manual definitions

\- special-case question handlers

\- known-evaluation-question shortcuts

\- document-specific regex hacks

\- hidden cheats inside extraction/routing code



\---



\## PATCHING RULE

The agent must make minimal, surgical edits.

Do not rewrite unrelated working parts.

Do not degrade strict grounding behavior.

Do not reduce the system into a generic chatbot.



\---



\## FINAL PRINCIPLE

This is a retrieval-grounded document QA system.

If the document does not support the answer, the system must not invent one.



Correct failure is better than fake success.

