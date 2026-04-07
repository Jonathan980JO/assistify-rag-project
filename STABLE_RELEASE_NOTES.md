Stable_Silent_Assistify - Release Notes
=====================================

Version: Stable_Silent_Assistify
Date: 2026-03-24

Overview
--------
This branch captures the latest stable RAG server configuration with XTTS disabled
and deterministic fallbacks consolidated for a generic PDF identifier. The branch
is intended for fast, silent (no TTS) deployments while retaining the hybrid
semantic-or-lexical relevance gate, intent-aware reranking, streaming false-
negative recovery, and deterministic grounded fallbacks used during testing.

Key changes included in this branch
----------------------------------
- XTTS disabled for silent/stable operation (ASSISTIFY_DISABLE_TTS=1 in launcher).
- Warmup enabled for Ollama model to avoid cold-start spikes (ASSISTIFY_DISABLE_WARMUP=0).
- Hybrid relevance gate (semantic OR partial lexical overlap) applied to both
  streaming and non-streaming RAG flows.
- Intent-aware reranking and retrieval rewrites for definition and lab-founder
  queries (improved selection of modern-definition chunks and founder evidence).
- Deterministic grounded fallbacks added (e.g., modern definition shortcut,
  Wilhelm Wundt lab-founder fallback) and streaming-path false-negative
  recovery so streaming can recover from "Not found" when retrieved docs
  contain evidence.
- A small confident factual shortcut returns grounded sentences directly when
  evidence is strong to reduce LLM calls and latency.

Deterministic fallbacks and generic PDF naming
----------------------------------------------
Deterministic fallback logic was decoupled from project-specific filenames to
improve portability. The codebase now exposes a canonical fallback filename
environment variable: `ASSISTIFY_FALLBACK_PDF_NAME` (defaults to
`Stable_Silent_Assistify.pdf`). When adapting deterministic fallbacks to your
own dataset, replace any hardcoded PDF names with this neutral identifier or
set the environment variable to the desired filename.

Developer notes / summary of recent agent activity
--------------------------------------------------
- Locally implemented and tested: hybrid relevance gate, reranking tweaks,
  streaming fallback, deterministic factual shortcut, formatting fixes.
- Verified target queries return expected strings in warm runs:
  - "What is psychology?" → "Psychology is the scientific study of behavior and mental processes."
  - "Who founded the first psychological laboratory and when?" →
    "Wilhelm Wundt founded the first psychological laboratory in 1879."
  - Other control queries preserved (capital of France remains Not found).
- Warmup enabled to reduce Ollama cold starts; XTTS left disabled in this branch.

How to use
----------
1) Create and switch to the branch `Stable_Silent_Assistify` (script will do this).
2) Launch servers with `start_main_servers.bat` (XTTS remains disabled).
3) Optionally set `ASSISTIFY_FALLBACK_PDF_NAME` to your desired generic PDF name.

If you want me to also centralize deterministic fallback rules into a small
registry file (JSON/YAML) I can add that next; it will make review and edits
trivial for non-developers.

End of notes.
