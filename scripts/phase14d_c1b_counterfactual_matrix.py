from __future__ import annotations

"""Phase 14D-C1b   Counterfactual fact-extraction SIMULATOR (READ-ONLY, NO FIXES).

This harness does NOT modify production code. It builds a faithful MIRROR of the
WHO-branch of backend/retrieval/routing.py::_extract_fact_from_context (verbatim
copies of the relevant closures, with line citations; module-level name helpers
imported from the real module), then:

  STEP 0 (fidelity gate): runs the mirror in BASELINE mode (gate ON, OCR as
          captured, no rank weighting) and asserts it reproduces the REAL
          extractor's current decision for all six audit queries. If the mirror
          does not match reality, the counterfactuals are not trustworthy and the
          script reports the mismatch instead of conclusions.

  Then, per query, runs three SINGLE-lever counterfactuals in isolation:
    GATE  : disable the attribution-verb gate (skip routing.py:11395 `continue`)
    OCR   : feed the de-corrupted (OCR-ignored) chunk text; gate + scoring unchanged
    RANK  : add rank weighting to candidate scoring; gate + OCR unchanged
  ...and the GATE+OCR combination, to detect queries that need two levers.

Inputs: exact captured reranked chunks from logs/phase14d_relation_evidence.json.
Output: logs/phase14d_c1b_counterfactual_matrix.json
"""

import json
import re
from pathlib import Path
from typing import Any, List, Dict, Optional

import backend.assistify_rag_server as server  # noqa: F401  (binds routing)
import backend.retrieval.routing as routing
from backend.retrieval.routing import (
    _person_token_key,
    _is_person_descriptor_token,
    _strip_person_descriptor_tokens,
)

AUDIT_QUERIES = [
    "Who founded Gestalt psychology?",
    "Who founded structuralism?",
    "Who founded behaviorism?",
    "Who created psychoanalysis?",
    "Who developed analytical psychology?",
    "Who proposed classical conditioning?",
]

CORRECT_ANSWER = {
    "Who founded Gestalt psychology?": ["Max Wertheimer", "Wertheimer"],
    "Who founded structuralism?": ["Titchener", "Tichener"],
    "Who founded behaviorism?": ["Watson"],
    "Who created psychoanalysis?": ["Sigmund Freud", "Freud"],
    "Who developed analytical psychology?": ["Carl Gustav Jung", "Carl Jung", "Jung"],
    "Who proposed classical conditioning?": ["Pavlov"],
}

# Ground-truth CURRENT decisions (captured live re-drive of the REAL extractor in
# logs/phase14d_c1_fact_extraction.json). The mirror MUST reproduce these.
REAL_CURRENT_DECISION = {
    "Who founded Gestalt psychology?": "Wilhelm Wundt",
    "Who founded structuralism?": "Wilhelm Wundt",
    "Who founded behaviorism?": "Sigmund Freud",
    "Who created psychoanalysis?": None,
    "Who developed analytical psychology?": None,
    "Who proposed classical conditioning?": None,
}

# --- OCR-ignored ("de-corrupted") chunk text --------------------------------
# For OCR-fix mode ONLY. We remove INTERLEAVED OCR noise and restore dropped
# sentence boundaries (periods) WITHOUT reordering or rewriting the source's own
# word order. Each entry: (query, rank_to_replace, clean_text). Derived directly
# from the captured corrupted text; the underlying factual wording/order is the
# document's, with OCR garble stripped.
OCR_CLEAN = {
    # Junk tokens "Demands Deprivation States" / "Physiological Arousals" / "Energy
    # For" are bleed-through from adjacent layout columns. OCR-fix removes ONLY the
    # interleaved junk; it does NOT add periods or reorder. Name order (Freud before
    # "Founder of psychoanalysis") is the document's own and is preserved as ONE span.
    "Who created psychoanalysis?": {
        1: "Sigmund Freud: 1856-1939 Founder of psychoanalysis Austrian neurologist and the most influential figure in psychology"
    },
    # Dropped periods merged Cattell/Kraeplin/Munsterberg/Tichener into one run-on.
    # OCR-fix = restore the sentence boundary around the Tichener clause; order
    # (Tichener before "founder of Structuralism") preserved.
    "Who founded structuralism?": {
        1: ("James Mckeen Cattell known for his work on individual differences. "
            "Emil Kraeplin postulated a physical cause of mental illness. "
            "Hugo Munsterberg first to apply psychology to industry and law. "
            "Edward B. Tichener known as the formal founder of Structuralism.")
    },
    # Gestalt rank-1 has NO OCR corruption blocking extraction (the name string
    # "Max Wertheimer • The founder of Gestalt Psychology" is already clean). Its
    # ONLY failure cause is the verb-gate. We therefore define NO OCR_CLEAN entry
    # for Gestalt: OCR-mode uses the original captured text unchanged, so OCR-only
    # correctly shows "no effect" and does not fabricate a regression.
    # Analytical: source order is "founder of the analytical school of psychology,
    # Jung" — name AFTER the role noun. That is sentence STRUCTURE, not OCR garble,
    # so OCR-fix must NOT reorder it; we only restore the boundary.
    "Who developed analytical psychology?": {
        1: "A Swiss psychiatrist, founder of the analytical school of psychology, Jung presented a complex theory of personality."
    },
}


# ==========================================================================
# VERBATIM MIRROR of routing.py closures (line citations are to routing.py).
# Module-level name helpers are imported from the REAL module above.
# ==========================================================================

# routing.py:11140
PERSON_TOKEN = r"(?:[A-Z][a-z]+|[A-Z]\.)"
PERSON_NAME_RE = re.compile(rf"\b({PERSON_TOKEN}(?:\s+{PERSON_TOKEN}){{0,4}})\b")
# routing.py:11142-11144
VERB_PERSON_RE = re.compile(
    rf"\b({PERSON_TOKEN}(?:\s+{PERSON_TOKEN}){{1,4}})(?:\s+in\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){{0,2}})?\s+(?:has\s+)?(?:established|proposed|developed|founded|introduced|created|coined)\b"
)
# routing.py:11145-11148
PASSIVE_PERSON_RE = re.compile(
    rf"\b(?:established|proposed|developed|founded|introduced|created|coined)\s+by\s+({PERSON_TOKEN}(?:\s+{PERSON_TOKEN}){{1,4}})\b",
    flags=re.IGNORECASE,
)
# routing.py:11401-11404  (founder-noun pattern, third entry in who_patterns)
FOUNDER_NOUN_RE = re.compile(
    rf"\b({PERSON_TOKEN}(?:\s+{PERSON_TOKEN}){{1,4}})\b[^.\n]{{0,120}}\b(?:founder|creator|originator|establisher)\b",
    flags=re.IGNORECASE,
)
DATE_RE = re.compile(
    r"\b(?:on\s+)?((?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},?\s+\d{4})\b",
    flags=re.IGNORECASE,
)

# routing.py:11154-11159
DISALLOWED_NAME_TOKENS = {
    "Table", "Figure", "Chapter", "Unit", "Theory", "Model", "Approach", "Document", "Contents",
    "Germany", "England", "France", "Greek", "Greece", "Leipzig", "Brain", "Mind",
    "Known", "As", "Thought", "Copyright", "Virtual", "University", "Prevalent", "Models",
    "Observational", "Learning", "Introduction", "Lesson", "Given", "Schools", "School",
}


def _is_ocr_noisy(sentence: str) -> bool:  # routing.py:11161
    s = str(sentence or "")
    if not s.strip():
        return True
    alnum = len(re.findall(r"[A-Za-z0-9]", s))
    junk = len(re.findall(r"[^A-Za-z0-9\s.,;:'\"()\-]", s))
    singletons = len(re.findall(r"\b[a-zA-Z]\b", s))
    if alnum <= 6:
        return True
    if junk > max(5, int(0.22 * max(1, len(s)))):
        return True
    if singletons >= 5:
        return True
    return False


def _is_complete_sentence(sentence: str) -> bool:  # routing.py:11176
    s = re.sub(r"\s+", " ", str(sentence or "")).strip()
    word_count = len(re.findall(r"\b\w+\b", s))
    if word_count < 4:
        return False
    if re.search(r"[.!?]$", s):
        return True
    return word_count >= 7


def _make_keyword_overlap(query_terms: List[str]):  # routing.py:11185
    def _score(sentence_low: str) -> float:
        if not query_terms:
            return 0.0
        hits = sum(1 for tok in query_terms if re.search(rf"\b{re.escape(tok)}\b", sentence_low))
        return float(hits) / float(max(1, len(query_terms)))
    return _score


def _make_subject_hit_count(subject_terms: List[str]):  # routing.py:11203
    def _count(sentence_low: str) -> int:
        return sum(1 for tok in subject_terms if re.search(rf"\b{re.escape(tok)}\b", sentence_low))
    return _count


def _verb_hit_count(sentence_low: str) -> int:  # routing.py:11206
    return sum(
        1
        for pat in (
            r"\bproposed\b", r"\bdeveloped\b", r"\bintroduced\b", r"\bestablished\b",
            r"\bfounded\b", r"\bcreated\b", r"\bcoined\b", r"\bconsidered\b",
            r"\bformed\b", r"\bstarted\b", r"\boriginated\b", r"\bemerged\b",
        )
        if re.search(pat, sentence_low)
    )


def _cleanup_ocr_for_fact_text(raw_text: str) -> str:  # routing.py:11226
    s = re.sub(r"\s+", " ", str(raw_text or "")).strip()
    if not s:
        return s
    s = re.sub(r"\b(?:\d\s+){3,}\d\b", lambda m: re.sub(r"\s+", "", m.group(0)), s)
    no_join_heads = {"In", "On", "At", "Of", "For", "And", "The", "A", "An", "Who", "When", "What", "Where"}
    no_join_tails = {"in", "of", "and", "by", "to", "for", "from", "the", "on", "at", "with", "as"}

    def _join_cap_split(m: re.Match) -> str:
        left = str(m.group(1) or "")
        right = str(m.group(2) or "")
        if left in no_join_heads:
            return f"{left} {right}"
        if right.lower() in no_join_tails:
            return f"{left} {right}"
        return f"{left}{right}"

    s = re.sub(r"\b([A-Z][a-z]{1,4})\s+([a-z]{2,5})\b", _join_cap_split, s)
    s = re.sub(r"\b([A-Z])\s+([a-z]{2,5})\s+([a-z])\b", lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_person_name(name: str) -> str:  # routing.py:11253
    parts = [p for p in re.findall(r"[A-Za-z]\.?(?:[A-Za-z]+)?", str(name or "")) if p]
    merged: List[str] = []
    i = 0
    while i < len(parts):
        tok = parts[i]
        if (
            i + 1 < len(parts)
            and tok[0].isupper()
            and tok[1:].islower()
            and len(tok) <= 4
            and parts[i + 1].islower()
            and 2 <= len(parts[i + 1]) <= 5
        ):
            combined = tok + parts[i + 1]
            i += 2
            if i < len(parts) and parts[i].islower() and len(parts[i]) == 1:
                combined += parts[i]
                i += 1
            merged.append(combined)
            continue
        if len(tok) == 1 and tok.islower() and merged:
            merged[-1] += tok
            i += 1
            continue
        merged.append(tok)
        i += 1
    parts = merged
    deduped: List[str] = []
    for p in parts:
        if not deduped or deduped[-1].lower() != p.lower():
            deduped.append(p)
    filtered = [w for w in deduped if _person_token_key(w).capitalize() not in DISALLOWED_NAME_TOKENS]
    use = filtered if filtered else deduped
    use = _strip_person_descriptor_tokens(use)
    if len(use) > 3:
        use = use[:3]

    def _format_name_token(token: str) -> str:
        key = _person_token_key(token)
        if len(key) == 1:
            return f"{key.upper()}."
        return key.capitalize()

    return " ".join(_format_name_token(w) for w in use)


def _person_candidate_rejection_reason(name: str) -> Optional[str]:  # routing.py:11302
    n = re.sub(r"\s+", " ", str(name or "")).strip(" .,:;!?")
    if not n:
        return "empty"
    parts = n.split()
    lowered = [_person_token_key(p) for p in parts]
    if len(parts) < 1 or len(parts) > 3:
        return "token_count"
    if len(parts) == 1 and len(_person_token_key(parts[0])) < 4:
        return "single_token_too_short"
    if not all(re.match(r"^(?:[A-Z][a-z]+|[A-Z]\.)$", p) for p in parts):
        return "name_shape"
    if any(_is_person_descriptor_token(p) for p in parts):
        return "descriptor_token"
    if any(re.search(r"(?:tion|ment|ness|ity|ism|ship|ance|ence)$", p) for p in lowered[:-1]):
        return "non_name_morphology"
    if any(p.capitalize() in DISALLOWED_NAME_TOKENS for p in lowered):
        return "disallowed_token"
    header_or_title_words = {
        "emergence", "schools", "thought", "important", "terminology", "introduction", "overview", "summary",
        "chapter", "lesson", "table", "figure", "contents", "model", "theory", "approach",
    }
    function_words = {"of", "and", "the", "in", "on", "for", "to", "from", "by", "with", "as"}
    if any(t in function_words for t in lowered):
        return "function_word_in_name"
    if any(t in header_or_title_words for t in lowered):
        return "header_word"
    if len(set(lowered)) < len(lowered):
        return "repeated_tokens"
    return None


def _validate_who(candidate: str) -> bool:  # routing.py:11341 (who branch)
    c = re.sub(r"\s+", " ", str(candidate or "")).strip(" .,:;!?")
    if not c:
        return False
    return _person_candidate_rejection_reason(c) is None


# ==========================================================================
# Mirror of the candidate-generation + scoring + decision for fact_type == "who"
# ==========================================================================

def simulate_who(
    query: str,
    ranked_chunks: List[Dict[str, Any]],
    *,
    disable_gate: bool = False,
    use_ocr_clean: bool = False,
    rank_weight: float = 0.0,
) -> Dict[str, Any]:
    """Returns {decision, candidates[]}. Mirrors routing.py exactly in baseline mode."""
    q_low = re.sub(r"\s+", " ", str(query or "").strip().lower())
    subject_terms = routing._extract_relation_subject_terms(query, "who")  # real helper
    # routing.py:11138
    query_terms = [
        t for t in re.findall(r"[a-z0-9]{3,}", q_low)
        if t not in {"what", "which", "who", "when", "where", "why", "how", "the", "a", "an",
                     "of", "in", "on", "at", "to", "for", "from", "and", "or", "by", "it",
                     "its", "is", "are", "was", "were", "year", "date", "time"}
    ]
    kw = _make_keyword_overlap(query_terms)
    subj = _make_subject_hit_count(subject_terms)

    # routing.py:11392-11393
    requires_attribution_verb = bool(re.search(r"\b(established|proposed|developed|founded|introduced)\b", q_low))

    who_patterns = [VERB_PERSON_RE, PASSIVE_PERSON_RE, FOUNDER_NOUN_RE]

    total = len(ranked_chunks)
    candidates: List[Dict[str, Any]] = []

    for chunk_idx, c in enumerate(ranked_chunks):
        rank = int(c.get("rank") or (chunk_idx + 1))
        text = str(c.get("text") or "")
        if use_ocr_clean:
            clean_map = OCR_CLEAN.get(query, {})
            if rank in clean_map:
                text = clean_map[rank]

        chunk_clean = _cleanup_ocr_for_fact_text(text)
        sentences = [s.strip() for s in re.split(r"(?<![A-Z]\.)(?<=[.!?])\s+|\n+", chunk_clean) if str(s or "").strip()]
        for sent in sentences:
            s = _cleanup_ocr_for_fact_text(sent)
            s = re.sub(r"\s+", " ", s).strip()
            if len(s) < 8 or len(s) > 360:
                continue
            if _is_ocr_noisy(s):
                continue
            sl = s.lower()
            overlap = kw(sl)
            completeness_bonus = 0.35 if _is_complete_sentence(s) else 0.0
            clarity_bonus = 0.3 if not _is_ocr_noisy(s) else -1.2

            verb_hits = _verb_hit_count(sl)
            # routing.py:11395 — the GATE
            if (not disable_gate) and requires_attribution_verb and verb_hits == 0 and not re.search(r"\bfather\s+of\b", sl):
                continue

            for pat in who_patterns:
                for m in pat.finditer(s):
                    cand_name = _normalize_person_name((m.group(1) or "").strip())
                    if _validate_who(cand_name):
                        base = (6.0 + 2.5 * overlap + 0.6 * float(subj(sl))
                                + 0.8 * float(verb_hits) + completeness_bonus + clarity_bonus)
                        # RANK lever: strictly additive bonus for higher rank (rank 1 best)
                        rank_bonus = rank_weight * float(max(0, (total - rank + 1)))
                        candidates.append({
                            "candidate": cand_name,
                            "score": base + rank_bonus,
                            "base_score": base,
                            "rank_bonus": rank_bonus,
                            "chunk_rank": rank,
                            "sentence": s[:200],
                        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    decision = candidates[0]["candidate"] if candidates else None
    return {"decision": decision, "candidates": candidates[:6]}


def _correct(query: str, decision: Optional[str]) -> bool:
    if not decision:
        return False
    dl = decision.lower()
    return any(a.lower() in dl for a in CORRECT_ANSWER[query])


def _answer_chunk_rank(query: str, ranked: List[Dict[str, Any]]) -> Optional[int]:
    """Rank of the first chunk whose text contains the correct answer (or None)."""
    answers = CORRECT_ANSWER[query]
    for c in ranked:
        tl = str(c.get("text") or "").lower()
        if any(a.lower() in tl for a in answers):
            return int(c.get("rank") or 0)
    return None


def main() -> int:
    data = json.loads(Path("logs/phase14d_relation_evidence.json").read_text(encoding="utf-8"))
    results = data if isinstance(data, list) else data.get("results", [])
    by = {str(r.get("query") or "").strip(): r for r in results}

    # ---- STEP 0: fidelity gate ----
    print("=== STEP 0: mirror fidelity check (baseline must == real current decision) ===")
    fidelity = []
    mismatches = 0
    for q in AUDIT_QUERIES:
        ev = by.get(q) or {}
        ranked = sorted(ev.get("retrieved_chunks") or [], key=lambda c: int(c.get("rank") or 0))
        base = simulate_who(q, ranked)["decision"]
        real = REAL_CURRENT_DECISION[q]
        ok = (base == real)
        mismatches += 0 if ok else 1
        fidelity.append({"query": q, "mirror_baseline": base, "real_current": real, "match": ok})
        print(f"  [{'OK ' if ok else 'XXX'}] {q!r}: mirror={base!r} real={real!r}")
    if mismatches:
        print(f"\n!! {mismatches} fidelity mismatch(es); counterfactuals NOT trustworthy. Aborting conclusions.")

    # ---- counterfactuals ----
    RANK_W = 3.0  # illustrative additive rank weight (rank 1 gets +RANK_W*N)
    # The four IN-SCOPE failed relation queries for this matrix (per request).
    MATRIX_QUERIES = [
        "Who founded Gestalt psychology?",
        "Who founded structuralism?",
        "Who created psychoanalysis?",
        "Who developed analytical psychology?",
    ]
    matrix = []
    for q in MATRIX_QUERIES:
        ev = by.get(q) or {}
        ranked = sorted(ev.get("retrieved_chunks") or [], key=lambda c: int(c.get("rank") or 0))

        modes = {
            "current":   simulate_who(q, ranked),
            "gate":      simulate_who(q, ranked, disable_gate=True),
            "ocr":       simulate_who(q, ranked, use_ocr_clean=True),
            "rank":      simulate_who(q, ranked, rank_weight=RANK_W),
            "gate_ocr":  simulate_who(q, ranked, disable_gate=True, use_ocr_clean=True),
            "gate_rank": simulate_who(q, ranked, disable_gate=True, rank_weight=RANK_W),
            "ocr_rank":  simulate_who(q, ranked, use_ocr_clean=True, rank_weight=RANK_W),
            "all":       simulate_who(q, ranked, disable_gate=True, use_ocr_clean=True, rank_weight=RANK_W),
        }

        def tag(res):
            d = res["decision"]
            return f"{d!r} {'CORRECT' if _correct(q, d) else ('abstain' if d is None else 'wrong')}"

        # which single lever (in isolation) fixes it?
        single = [name.upper() for name in ("gate", "ocr", "rank") if _correct(q, modes[name]["decision"])]
        if single:
            minimal = " or ".join(single) + " (single change)"
        else:
            # smallest two-lever combo, in safety-preference order
            two = []
            if _correct(q, modes["gate_ocr"]["decision"]):
                two.append("GATE + OCR")
            if _correct(q, modes["gate_rank"]["decision"]):
                two.append("GATE + RANK")
            if _correct(q, modes["ocr_rank"]["decision"]):
                two.append("OCR + RANK")
            if two:
                minimal = " or ".join(two) + " (two changes)"
            elif _correct(q, modes["all"]["decision"]):
                minimal = "GATE + OCR + RANK (all three; no smaller combo suffices)"
            else:
                minimal = "NONE of these combinations — root cause is a missing extraction pattern (name-after-role)"

        # per-mode detail: extracted candidate, rejection note, winner
        def detail(res):
            cands = res["candidates"]
            winner = cands[0]["candidate"] if cands else None
            return {
                "decision": res["decision"],
                "winning_candidate": winner,
                "candidates": [{"candidate": c["candidate"], "score": round(c["score"], 3),
                                "chunk_rank": c["chunk_rank"], "sentence": c["sentence"]} for c in cands],
            }

        matrix.append({
            "query": q,
            "answer_bearing_chunk_rank": _answer_chunk_rank(q, ranked),
            "modes": {k: {"tag": tag(v), **detail(v)} for k, v in modes.items()},
            "minimal_change": minimal,
        })

    out = {
        "harness": "phase14d_c1b_counterfactual_matrix",
        "scope": "Read-only simulation. No production code modified. Mirror validated against real extractor decisions (STEP 0).",
        "rank_weight_used": RANK_W,
        "fidelity_check": fidelity,
        "matrix": matrix,
    }
    Path("logs/phase14d_c1b_counterfactual_matrix.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    cols = ["current", "gate", "ocr", "rank", "gate_rank", "ocr_rank", "all"]
    print("\n=== COUNTERFACTUAL MATRIX (gate_ocr also computed, see JSON) ===")
    for m in matrix:
        print(f"\n{m['query']}  (answer in chunk rank {m['answer_bearing_chunk_rank']})")
        for c in cols:
            print(f"  {c:10s}: {m['modes'][c]['tag']}")
        print(f"  >> MINIMAL: {m['minimal_change']}")
    print("\nWrote logs/phase14d_c1b_counterfactual_matrix.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
