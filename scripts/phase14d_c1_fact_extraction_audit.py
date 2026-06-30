from __future__ import annotations

"""Phase 14D-C1   Fact Extraction Failure Audit harness (READ-ONLY, NO FIXES).

Scope (per task): investigate ONLY backend/retrieval/routing.py fact extraction
(`_extract_fact_from_context` + helpers). Do NOT modify production code, retrieval,
reranking, embeddings, Chroma, ingestion, parsing, tenant routing, topic
extraction, compare/summary/streaming/Ollama/timeouts.

This harness COLLECTS EVIDENCE ONLY. It:

  1. Loads the EXACT captured retrieved/reranked chunks for the six audit queries
     from logs/phase14d_relation_evidence.json (live capture; rerank order; the
     capture recorded score == rerank_score).
  2. Re-drives the REAL, UNMODIFIED extractor functions in routing.py
     (`_detect_fact_query_type`, `_extract_relation_subject_terms`,
     `_extract_fact_from_context`) over those chunk texts, capturing the
     extractor's own [FACT ...] markers in-memory (Steps 3,4,5 authoritative).
  3. Adds a per-sentence Step-1 (evidence presence) and Step-2 (attribution
     pattern) audit by applying the EXACT regexes/gate copied verbatim from
     routing.py (with line citations) to each sentence. These mirrors are used
     ONLY to explain WHY the real extractor behaved as observed; the real
     extractor remains the source of truth for candidate/decision evidence.

Outputs:
  - logs/phase14d_c1_fact_extraction.json   (machine-readable evidence)

No behavior is altered; only observed.
"""

import json
import re
from pathlib import Path
from typing import Any

import backend.assistify_rag_server as server  # auto-binds routing (read-only)
import backend.retrieval.routing as routing


# --- the six audit queries (exact strings from the task) -------------------
AUDIT_QUERIES = [
    "Who founded Gestalt psychology?",
    "Who founded structuralism?",
    "Who founded behaviorism?",
    "Who created psychoanalysis?",
    "Who developed analytical psychology?",
    "Who proposed classical conditioning?",
]

# Final authoritative A-F classification (per task taxonomy), derived from the
# captured evidence below. Recorded alongside the auto-computed signals so the
# JSON and the markdown report agree. A0 = correct evidence not present in the
# retrieved chunks (upstream retrieval gap; outside the extraction A-F taxonomy,
# which presupposes evidence presence).
FINAL_CLASSIFICATION = {
    "Who founded Gestalt psychology?": {
        "category": "A",
        "title": "Correct evidence exists but no extraction pattern matched",
        "death_point": "routing.py:11395 verb-gate `continue`",
        "rationale": (
            "Rank-1 chunk contains 'Max Wertheimer * The founder of Gestalt Psychology'. "
            "founder_noun_re (routing.py:11401) DOES capture 'Max Wertheimer', but the "
            "attribution-verb gate (requires_attribution_verb=True from 'founded' in query; "
            "verb_hit_count=0; no 'father of') executes `continue` and drops the sentence "
            "BEFORE the who_patterns loop runs. The correct candidate is never generated."
        ),
        "contributing": "Subject-blind & rank-blind scoring (routing.py:11413) then lets off-subject 'Wilhelm Wundt' (no 'gestalt' token) win, producing the wrong final answer.",
    },
    "Who founded structuralism?": {
        "category": "A",
        "title": "Correct evidence exists but no extraction pattern matched",
        "death_point": "routing.py:11395 verb-gate `continue`",
        "rationale": (
            "Rank-1 chunk contains 'Edward B. Tichener ... formal founder of Structuralism', "
            "OCR-merged into one run-on sentence with verb_hit_count=0. Gate drops it before "
            "patterns run; the correct candidate is never generated."
        ),
        "contributing": "Subject-blind/rank-blind scoring elevates off-subject 'Wilhelm Wundt' from the rank-2 chunk to win.",
    },
    "Who founded behaviorism?": {
        "category": "A0",
        "title": "No correct evidence in retrieved chunks (upstream retrieval gap - outside A-F)",
        "death_point": "upstream of extraction (retrieval/ingestion)",
        "rationale": (
            "No retrieved/reranked chunk contains 'Watson' or even the token 'behaviorism'. "
            "Step 1 = NO for all chunks, so the A-F extraction taxonomy (which presupposes "
            "evidence presence) does not apply. The extractor had no correct evidence to work with."
        ),
        "contributing": "Subject-blind scoring then returns off-subject 'Sigmund Freud'.",
    },
    "Who created psychoanalysis?": {
        "category": "C",
        "title": "Candidate generated but rejected",
        "death_point": "routing.py:11341/11317 _validate_candidate -> _person_candidate_rejection_reason=non_name_morphology",
        "rationale": (
            "Gate does NOT fire ('created' is absent from the gate regex at routing.py:11392), so "
            "who_patterns run. founder_noun_re matches the OCR-contaminated span and captures "
            "'Demands Deprivation States Sigmund Freud'; after name normalization the candidate "
            "'Demands Deprivation States' is rejected (non_name_morphology). The clean 'Sigmund "
            "Freud' is never isolated as its own candidate. Extractor returns None."
        ),
        "contributing": "OCR junk glued to the name (positional NAME-capture in founder_noun_re grabs leading tokens, not the trailing real name).",
    },
    "Who developed analytical psychology?": {
        "category": "A",
        "title": "Correct evidence exists but no extraction pattern matched",
        "death_point": "routing.py:11395 verb-gate `continue`",
        "rationale": (
            "Rank-1 chunk: 'A Swiss psychiatrist, founder of the analytical school of psychology, "
            "Jung...'. Gate fires ('developed' in query), verb_hit_count=0 -> sentence dropped "
            "before patterns. (Even if it ran, founder_noun_re captures the descriptor 'Swiss "
            "psychiatrist', not 'Jung', because the name follows the noun.) Extractor returns None."
        ),
        "contributing": "Pattern is position-fragile: it captures the NAME before 'founder', but here the name ('Jung') comes after. Runtime later recovered the correct answer via a non-deterministic fallback OUTSIDE this function.",
    },
    "Who proposed classical conditioning?": {
        "category": "A0",
        "title": "No correct evidence in retrieved chunks (upstream retrieval gap - outside A-F)",
        "death_point": "upstream of extraction (retrieval/ingestion)",
        "rationale": (
            "Retrieved chunks discuss classical conditioning and describe Pavlov's work "
            "('won Nobel Prize ... 1904', 'salivation reflex in dogs') but NEVER name 'Pavlov'. "
            "Step 1 = NO for all chunks; no extractor could produce the name. Extractor returns None."
        ),
        "contributing": "None at extraction layer; the naming evidence was not retrieved.",
    },
}

# Known-correct answer (history of psychology) used ONLY to mark "contains answer?"
# in Step 1. Not fed to the extractor.
CORRECT_ANSWER = {
    "Who founded Gestalt psychology?": ["Max Wertheimer", "Wertheimer", "Koffka", "Kohler", "Kohler"],
    "Who founded structuralism?": ["Titchener", "Tichener", "Edward B. Tichener", "Edward Titchener"],
    "Who founded behaviorism?": ["Watson", "John B. Watson", "John Watson"],
    "Who created psychoanalysis?": ["Sigmund Freud", "Freud"],
    "Who developed analytical psychology?": ["Carl Gustav Jung", "Carl Jung", "Jung"],
    "Who proposed classical conditioning?": ["Pavlov", "Ivan Pavlov"],
}


# --------------------------------------------------------------------------
# EXACT mirrors of the gate + attribution patterns from routing.py.
# Copied verbatim (see line citations) so Step 2 reports precisely what the
# real extractor tests. These are NOT re-implementations of behavior beyond the
# specific lines cited; the real extractor is re-driven separately for truth.
# --------------------------------------------------------------------------
PERSON_TOKEN = r"(?:[A-Z][a-z]+|[A-Z]\.)"  # routing.py:11140

# routing.py:11392  (the attribution-VERB GATE applied to the QUERY)
GATE_VERB_RE = re.compile(r"\b(established|proposed|developed|founded|introduced)\b")
# routing.py:11393  founder_query flag
FOUNDER_QUERY_RE = re.compile(r"\bfounder\s+of\b")
# routing.py:11395  father-of escape hatch (applied to the SENTENCE)
FATHER_OF_RE = re.compile(r"\bfather\s+of\b")

# routing.py:11206-11224  _verb_hit_count patterns (applied to the SENTENCE, lower)
VERB_HIT_PATTERNS = [
    r"\bproposed\b", r"\bdeveloped\b", r"\bintroduced\b", r"\bestablished\b",
    r"\bfounded\b", r"\bcreated\b", r"\bcoined\b", r"\bconsidered\b",
    r"\bformed\b", r"\bstarted\b", r"\boriginated\b", r"\bemerged\b",
]

# routing.py:11142-11144  verb_person_re (active: NAME ... <verb>)
VERB_PERSON_RE = re.compile(
    rf"\b({PERSON_TOKEN}(?:\s+{PERSON_TOKEN}){{1,4}})(?:\s+in\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){{0,2}})?\s+(?:has\s+)?(?:established|proposed|developed|founded|introduced|created|coined)\b"
)
# routing.py:11145-11148  passive_person_re (<verb> by NAME)
PASSIVE_PERSON_RE = re.compile(
    rf"\b(?:established|proposed|developed|founded|introduced|created|coined)\s+by\s+({PERSON_TOKEN}(?:\s+{PERSON_TOKEN}){{1,4}})\b",
    flags=re.IGNORECASE,
)
# routing.py:11401-11404  founder-NOUN pattern (NAME ... founder/creator/originator/establisher)
FOUNDER_NOUN_RE = re.compile(
    rf"\b({PERSON_TOKEN}(?:\s+{PERSON_TOKEN}){{1,4}})\b[^.\n]{{0,120}}\b(?:founder|creator|originator|establisher)\b",
    flags=re.IGNORECASE,
)
# routing.py:11149  father_re (NAME ... the father of)  [NOTE: defined but NOT in who_patterns loop]
FATHER_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:is\s+)?(?:considered\s+)?the\s+father\s+of\b",
    flags=re.IGNORECASE,
)

PATTERN_CATALOG = [
    ("verb_person_re (active NAME+verb)", "routing.py:11142", VERB_PERSON_RE, True),
    ("passive_person_re (verb by NAME)", "routing.py:11145", PASSIVE_PERSON_RE, True),
    ("founder_noun_re (NAME..founder/creator)", "routing.py:11401", FOUNDER_NOUN_RE, True),
    ("father_re (NAME..father of) [defined, NOT looped]", "routing.py:11149", FATHER_RE, False),
]


def _sentences_of(chunk_clean: str) -> list[str]:
    # routing.py:11378 sentence split (verbatim regex)
    return [s.strip() for s in re.split(r"(?<![A-Z]\.)(?<=[.!?])\s+|\n+", chunk_clean) if str(s or "").strip()]


def _contains_answer(sentence: str, answers: list[str]) -> bool:
    sl = sentence.lower()
    return any(a.lower() in sl for a in answers)


class _CaptureLogger:
    def __init__(self) -> None:
        self.records: list[str] = []

    def _emit(self, msg: str, args: tuple[Any, ...]) -> None:
        try:
            self.records.append(str(msg) % args if args else str(msg))
        except Exception:
            self.records.append(str(msg) + " " + repr(args))

    def info(self, msg: str, *a: Any) -> None:
        self._emit(msg, a)

    def debug(self, msg: str, *a: Any) -> None:
        self._emit(msg, a)

    def warning(self, msg: str, *a: Any) -> None:
        self._emit(msg, a)

    def error(self, msg: str, *a: Any) -> None:
        self._emit(msg, a)


def _load_evidence() -> dict[str, dict[str, Any]]:
    path = Path("logs/phase14d_relation_evidence.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data if isinstance(data, list) else data.get("results", [])
    return {str(r.get("query") or "").strip(): r for r in results}


def _markers(records: list[str], needle: str) -> list[str]:
    return [r for r in records if needle in r]


def _step2_pattern_audit(query: str, answers: list[str], ordered_chunks: list[dict]) -> list[dict]:
    """Per answer-bearing sentence: gate outcome + which patterns match."""
    q_low = query.strip().lower()
    requires_attribution_verb = bool(GATE_VERB_RE.search(q_low))
    founder_query = bool(FOUNDER_QUERY_RE.search(q_low))

    rows: list[dict] = []
    for c in ordered_chunks:
        rank = c.get("rank")
        raw = str(c.get("text") or "")
        chunk_clean = routing._extract_fact_from_context.__wrapped__ if False else raw  # noqa
        # Apply the SAME OCR cleanup the extractor applies (routing._cleanup_ocr_for_fact_text
        # is a nested local; re-drive truth comes from the real extractor markers. Here we use
        # the raw chunk split to locate answer-bearing sentences for reporting.)
        for sent in _sentences_of(raw):
            s = re.sub(r"\s+", " ", sent).strip()
            if not _contains_answer(s, answers):
                continue
            sl = s.lower()
            verb_hits = sum(1 for p in VERB_HIT_PATTERNS if re.search(p, sl))
            father_of = bool(FATHER_OF_RE.search(sl))
            gate_drops = bool(requires_attribution_verb and verb_hits == 0 and not father_of)

            pattern_results = []
            for label, cite, rx, looped in PATTERN_CATALOG:
                m = rx.search(s)
                pattern_results.append({
                    "pattern": label,
                    "source": cite,
                    "in_who_patterns_loop": looped,
                    "matched": bool(m),
                    "captured_group": (m.group(1) if m else None),
                })

            rows.append({
                "chunk_rank": rank,
                "answer_bearing_sentence": s[:400],
                "gate": {
                    "requires_attribution_verb": requires_attribution_verb,
                    "founder_query": founder_query,
                    "verb_hit_count": verb_hits,
                    "father_of_in_sentence": father_of,
                    "sentence_dropped_by_gate_before_patterns": gate_drops,
                },
                "patterns": pattern_results,
                "any_looped_pattern_would_match": any(
                    p["matched"] and p["in_who_patterns_loop"] for p in pattern_results
                ),
            })
    return rows


def _classify(query: str, retrieval_has_answer: bool, step2_rows: list[dict],
              cand_lines: list[str], reject_lines: list[str], decision: str | None) -> dict:
    """A-F classification per the task taxonomy.

    A: Correct evidence exists but no extraction pattern matched.
    B: Pattern matched but candidate not generated.
    C: Candidate generated but rejected.
    D: Candidate accepted but lost scoring.
    E: Candidate won scoring but lost later.
    F: Multiple failures.
    (We also record 'A0' = no correct evidence retrieved -> upstream, out of scope.)
    """
    decision_correct = bool(decision and _contains_answer(decision, CORRECT_ANSWER[query]))

    if not retrieval_has_answer:
        return {
            "category": "A0 (no correct evidence in retrieved chunks - upstream/out-of-scope)",
            "rationale": "No retrieved/reranked chunk contains the correct answer; extraction cannot succeed.",
            "decision_correct": decision_correct,
        }

    if decision_correct:
        return {
            "category": "No failure (correct fact extracted)",
            "rationale": f"Extractor returned correct answer: {decision!r}.",
            "decision_correct": True,
        }

    gate_dropped_all = step2_rows and all(
        r["gate"]["sentence_dropped_by_gate_before_patterns"] for r in step2_rows
    )
    any_pattern_match = any(r["any_looped_pattern_would_match"] for r in step2_rows)
    correct_candidate_generated = any(
        any(_contains_answer(ln, CORRECT_ANSWER[query]) for _ in [0]) and
        _contains_answer(ln, CORRECT_ANSWER[query]) for ln in cand_lines
    )
    correct_candidate_rejected = any(
        _contains_answer(ln, CORRECT_ANSWER[query]) for ln in reject_lines
    )

    flags = []
    if gate_dropped_all:
        flags.append("gate_dropped_all_answer_bearing_sentences")
    if correct_candidate_rejected:
        flags.append("correct_candidate_rejected_by_validator")
    if correct_candidate_generated and not decision_correct:
        flags.append("correct_candidate_generated_but_lost_scoring")

    # Decide primary category
    if correct_candidate_rejected and not correct_candidate_generated:
        cat = "C (candidate generated but rejected)"
    elif gate_dropped_all and not any_pattern_match_after_gate(step2_rows):
        cat = "A (correct evidence exists but no extraction pattern matched - gate dropped sentence before patterns ran)"
    elif gate_dropped_all and any_pattern_match:
        cat = "A (gate dropped sentence pre-pattern; a non-looped/blocked pattern would have matched)"
    elif correct_candidate_generated and not decision_correct:
        cat = "D (candidate accepted but lost scoring to off-subject candidate)"
    else:
        cat = "A (correct evidence exists but no extraction pattern matched)"

    if len(flags) >= 2:
        cat = "F (multiple failures): " + cat

    return {
        "category": cat,
        "rationale": "; ".join(flags) or "see step evidence",
        "flags": flags,
        "decision_correct": decision_correct,
        "redriven_decision": decision,
    }


def any_pattern_match_after_gate(step2_rows: list[dict]) -> bool:
    # If the gate drops a sentence, the who_patterns loop never runs on it.
    for r in step2_rows:
        if not r["gate"]["sentence_dropped_by_gate_before_patterns"] and r["any_looped_pattern_would_match"]:
            return True
    return False


def _trace_one(query: str, ev: dict[str, Any]) -> dict[str, Any]:
    answers = CORRECT_ANSWER[query]
    chunks_meta = ev.get("retrieved_chunks") or []
    ordered = sorted(chunks_meta, key=lambda c: int(c.get("rank") or 0))
    chunk_texts = [str(c.get("text") or "") for c in ordered]

    # --- Step 1: evidence presence (top retrieved == top reranked; capture noted score==rerank_score)
    step1 = []
    retrieval_has_answer = False
    for c in ordered:
        text = str(c.get("text") or "")
        ans_sents = [re.sub(r"\s+", " ", s).strip() for s in _sentences_of(text)
                     if _contains_answer(s, answers)]
        contains = bool(ans_sents)
        retrieval_has_answer = retrieval_has_answer or contains
        step1.append({
            "rank": c.get("rank"),
            "retrieval_score": c.get("score"),
            "rerank_score": c.get("rerank_score"),
            "chunk_index": c.get("chunk_index"),
            "page": c.get("page"),
            "contains_answer": "YES" if contains else "NO",
            "answer_bearing_sentences": ans_sents[:3],
            "text_preview": re.sub(r"\s+", " ", text)[:300],
        })

    # --- Step 2: attribution pattern audit (mirrors)
    step2 = _step2_pattern_audit(query, answers, ordered)

    # --- Steps 3,4,5: re-drive REAL extractor, capture its markers
    cap = _CaptureLogger()
    real_logger = getattr(server, "logger", None)
    server.logger = cap
    try:
        fact_type = routing._detect_fact_query_type(query)
        subject_terms = routing._extract_relation_subject_terms(query, fact_type)
        decision = routing._extract_fact_from_context(query, chunk_texts)
    finally:
        if real_logger is not None:
            server.logger = real_logger
    rec = cap.records

    cand_lines = _markers(rec, "[FACT CANDIDATE]")
    reject_lines = _markers(rec, "[FACT PERSON VALIDATOR]")
    decision_lines = _markers(rec, "[FACT DECISION]")
    accepted_lines = _markers(rec, "[FACT ACCEPTED]")
    nocand_lines = _markers(rec, "no_candidates")
    rejected_best_lines = _markers(rec, "best_candidate_rejected")

    classification = _classify(query, retrieval_has_answer, step2, cand_lines, reject_lines, decision)

    return {
        "query": query,
        "fact_type_detected": fact_type,
        "subject_terms": subject_terms,
        "retrieval_has_answer": retrieval_has_answer,
        "redriven_fact_decision": decision,
        "observed_runtime_answer": ev.get("answer"),
        "step1_evidence_presence": step1,
        "step2_attribution_patterns": step2,
        "step3_candidate_generation": {
            "fact_candidate_markers": cand_lines,
            "no_candidates_marker": nocand_lines,
        },
        "step4_candidate_rejection": {
            "person_validator_markers": reject_lines,
            "best_candidate_rejected_markers": rejected_best_lines,
        },
        "step5_candidate_scoring": {
            "fact_candidate_markers": cand_lines,  # contain score=
            "fact_decision_markers": decision_lines,
            "fact_accepted_markers": accepted_lines,
            "scoring_uses_retrieval_rank": False,
            "scoring_uses_rerank_score": False,
            "scoring_evidence": "routing.py:11413 score = 6.0 + 2.5*overlap + 0.6*subj_hits + 0.8*verb_hits + completeness_bonus + clarity_bonus; chunk_idx logged (11415) but never read in score; no reference to retrieval score/rerank_score/rank.",
        },
        "step6_root_cause": {
            "final_classification": FINAL_CLASSIFICATION[query],
            "auto_signals": classification,
        },
        "all_records": rec,
    }


def main() -> int:
    by_query = _load_evidence()
    traces = []
    for q in AUDIT_QUERIES:
        ev = by_query.get(q)
        if ev is None:
            traces.append({"query": q, "error": "no captured evidence for this query"})
            continue
        traces.append(_trace_one(q, ev))

    out = {
        "harness": "phase14d_c1_fact_extraction_audit",
        "scope": "Evidence-only. Read-only re-drive of real _extract_fact_from_context over captured reranked chunks. No production code modified.",
        "source_evidence": "logs/phase14d_relation_evidence.json",
        "routing_function": "backend/retrieval/routing.py::_extract_fact_from_context (line 11100)",
        "queries": traces,
    }
    out_path = Path("logs/phase14d_c1_fact_extraction.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")

    for t in traces:
        if t.get("error"):
            print(f"\n=== {t['query']!r}: ERROR {t['error']}")
            continue
        print(f"\n=== {t['query']!r} (type={t['fact_type_detected']}, subj={t['subject_terms']}) ===")
        print(f"  retrieval_has_answer : {t['retrieval_has_answer']}")
        print(f"  re-driven decision   : {t['redriven_fact_decision']!r}")
        print(f"  CATEGORY             : {t['step6_root_cause']['final_classification']['category']} - {t['step6_root_cause']['final_classification']['title']}")
        for r in t["step2_attribution_patterns"]:
            g = r["gate"]
            print(f"    rank{r['chunk_rank']} gate_drop={g['sentence_dropped_by_gate_before_patterns']} "
                  f"verb_hits={g['verb_hit_count']} | {r['answer_bearing_sentence'][:90]!r}")
        for ln in t["step3_candidate_generation"]["fact_candidate_markers"]:
            print("    CAND:", ln)
        for ln in t["step4_candidate_rejection"]["person_validator_markers"]:
            print("    REJECT:", ln)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
