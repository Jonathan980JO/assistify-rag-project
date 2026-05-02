You are editing a strict generic RAG system.



Read `AI\_AGENT\_RULES.md` first and obey it fully before making any code changes.



Your job:

1\. Inspect the current codebase, especially `backend/assistify\_rag\_server.py`

2\. Find and remove all cheating or hardcoded behavior

3\. Preserve only generic retrieval-grounded logic

4\. Keep the system strict: unsupported questions must return exactly `Not found in the document.`

5\. Make only minimal, surgical changes



Important bans:

\- no hardcoded answers

\- no psychology words

\- no document-specific term lists

\- no fake fallback definitions

\- no query-to-answer mappings

\- no special handling for known test questions

\- no hidden domain-specific shortcuts



Allowed:

\- generic retrieval improvements

\- generic ranking improvements

\- generic extraction improvements

\- generic OCR cleanup

\- generic grounding validation

\- stale active-document/state fixes

\- strict evidence-based routing



Before changing code, perform this audit:

\- list every suspicious hardcoded block

\- explain why it is cheating or risky

\- propose a generic replacement

\- then patch only the unsafe parts



After patching, provide:

\- what was removed

\- what was replaced

\- why the new logic is generic

\- what remains to inspect

\---

\## Compiler / VS Code Diagnostics Must Be Clean

This section is **mandatory**. Do not consider the task complete until all diagnostics are clean for every file edited.

\### Rule 1 — No stopping with open problems

Do not stop after code edits until every modified file shows **zero VS Code / Pylance / compiler problems** introduced by the patch.

\### Rule 2 — Required checks after every patch

After every code change, run **all** of the following:

1\. VS Code / Pylance diagnostics for every modified Python file (use `get_errors` tool or equivalent)

2\. Python compile check for every modified file:

   ```
   python -m py_compile <modified_file>
   ```

3\. Any relevant syntax or lint check available in the workspace

\### Rule 3 — Errors must be fixed before stopping

If diagnostics reveal any of the following caused by the patch:

\- syntax errors

\- undefined names / missing imports

\- unreachable or broken code

\- type / compile failures

\- warnings introduced by the patch

Then:

1\. Fix the problem immediately

2\. Rerun all diagnostics

3\. Repeat until clean

\### Rule 4 — No false success reports

Do **not** report success while VS Code still shows problems in any file that was edited.

\### Rule 5 — Separate pre-existing warnings from new problems

If a file already had unrelated warnings before the task:

\- clearly separate pre-existing warnings from new problems introduced by the patch

\- do not introduce new problems

\- fix all new problems before stopping

Pre-existing warnings that were not introduced by this task are allowed to remain, but must be explicitly noted.

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

