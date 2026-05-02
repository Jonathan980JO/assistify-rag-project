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

\---

\## Compiler / VS Code Diagnostics Must Be Clean

This section is **mandatory**. The agent must not consider any task complete until all diagnostics are clean for every file it edited.

\### Rule 1 — No stopping with open problems

The agent must not stop after code edits until every modified file shows **zero VS Code / Pylance / compiler problems** introduced by the patch.

\### Rule 2 — Required checks after every patch

After every code change, the agent must run **all** of the following:

1\. VS Code / Pylance diagnostics for every modified Python file (use `get_errors` tool or equivalent)

2\. Python compile check for every modified file:

   ```
   python -m py_compile <modified_file>
   ```

3\. Any relevant syntax or lint check available in the workspace

\### Rule 3 — Errors must be fixed before stopping

If diagnostics reveal any of the following caused by the agent's patch:

\- syntax errors

\- undefined names / missing imports

\- unreachable or broken code

\- type / compile failures

\- warnings introduced by the patch

Then the agent must:

1\. Fix the problem immediately

2\. Rerun all diagnostics

3\. Repeat until clean

\### Rule 4 — No false success reports

The agent must **not** report success while VS Code still shows problems in any file it edited.

\### Rule 5 — Separate pre-existing warnings from new problems

If the file already had unrelated warnings before the task:

\- clearly separate pre-existing warnings from new problems introduced by the patch

\- do not introduce new problems

\- fix all new problems before stopping

Pre-existing warnings that the agent did not introduce are allowed to remain, but must be explicitly noted.

\### Rule 6 — Final report requirements

Every final report must include:

\- list of modified files

\- diagnostics command / tool used

\- compile result for each modified Python file

\- confirmation: **"VS Code/Pylance diagnostics are clean for modified files"**

\- confirmation: **"py\_compile passed for modified Python files"**

\---

\## Task Prompt Authoring Guidelines

When writing future task prompts, prefer reusable generic instructions. Every new task prompt should include or reference the following checklist:

\- **Strict no-hardcoding rule** — no fixed answers, no domain term lists, no question→answer maps

\- **Read AGENT\_TASK\_PROMPT.md first** before starting any work

\- **Read AI\_AGENT\_RULES.md second** and obey it fully

\- **Preserve RAG grounding** — all answers must come from retrieved evidence

\- **Run real WebSocket validation** when the behavior change affects `/ws` routes

\- **Run compiler and VS Code diagnostics** before submitting the final answer

