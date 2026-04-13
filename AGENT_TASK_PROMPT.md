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

