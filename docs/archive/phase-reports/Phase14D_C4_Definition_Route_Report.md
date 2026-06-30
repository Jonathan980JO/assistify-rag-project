# Phase 14D-C4 - Definition Route Failure Investigation

Status: evidence-only investigation. No code was changed. All findings are static traces of the live code paths in `backend/retrieval/routing.py`, `backend/retrieval/generation.py`, `backend/retrieval/validation.py`, `backend/services/rag_service.py`, `backend/services/streaming_service.py`, and `backend/rag_query_prep.py`.

Two failures analyzed:

1. `Who is Freud?` selects the theory sentence "Freud's idea that libido is the prime impulse of life ..." instead of the biography chunk.
2. `Who is Elon Musk?` mutates Elon to "even" and Musk to "must" despite the guard logging `[EXACT ENTITY GUARD] spelling_correction_skipped=True`.

---

## Failure 1 - `Who is Freud?` picks the libido theory sentence

### Executive finding

The biography sentence is never selected because it is eliminated by two present-tense / anti-biographical filters inside the definition route, while the libido theory sentence survives every filter and wins the ranked selection.

- The biography is rejected at two points:
  - the doc-scan only collects present-tense definition verbs, so any `Freud was ...` biography sentence is excluded (`routing.py:744`).
  - any biography/attribution sentence that does reach scoring is hard-rejected with `biographical_or_attribution_noise` (`routing.py:656`) and penalized as `_is_biography_or_history_style` (`routing.py:688`, predicate at `routing.py:549-557`).
- The libido sentence, which is rejected by the `who is` person extractor (`routing.py:13336`, no `_person_signal`), is re-admitted by the generic doc-scan at `routing.py:746` and then committed as the final answer at `routing.py:783`.

Exact line where a previously-rejected sentence becomes the selected answer: `backend/retrieval/routing.py:746` (re-admission into `collected`) then `backend/retrieval/routing.py:783` (`return _append_rich_definition_context(...)`).

### Stage trace

#### 1. Retrieval / classification

`Who is Freud?` is classified as a definition entity, not a fact entity. `_is_definition_style_query` matches the `who is` starter:

```10208:10209:backend/retrieval/routing.py
    if re.match(r"^(?:what\s+is|define|who\s+is|who\s+was|who\s+introduced|who\s+is\s+considered)", q):
        return True
```

`_classify_query_family_v2` therefore returns `definition_entity`:

```17435:17436:backend/retrieval/routing.py
    if _is_definition_style_query(q):
        return "definition_entity"
```

Because `family_v2 == "definition_entity"`, the answer route is forced to `definition` and the deterministic definition extractor is invoked:

```22884:22918:backend/retrieval/routing.py
    if family_v2 == "definition_entity":
        answer_route = "definition"
    ...
        route_answer = _extract_definition_route_answer(query, route_docs)
        if route_answer:
            S.logger.info("[ANSWER ROUTE] mode=definition deterministic=true answer=%s", route_answer[:220])
            return _result(route_answer, used_llm=False, answer_type="definition_route_deterministic", items_count=1)
```

#### 2. Concept filter

The concept filter (`_apply_concept_filter_to_docs`, `routing.py:6292`; logs `[CONCEPT FILTER] ... kept=...` at `routing.py:6305`) only keeps chunks that mention the entity. It does not prefer biography over theory; both the biography chunk and the chunk containing the libido sentence mention `Freud`, so both survive. The concept filter is not the loss point.

#### 3. Candidate generation inside `_extract_definition_route_answer`

```716:720:backend/retrieval/routing.py
    candidates = [
        _extract_best_scored_concept_sentence_from_docs(query_text, docs, max_docs=4),
        _extract_simple_definition_sentence(query_text, docs),
    ]
    collected.extend([str(c or "") for c in candidates if str(c or "").strip()])
```

`_extract_best_scored_concept_sentence_from_docs` immediately returns `None` for a `who is` query because it only accepts `what is` / `define`:

```12914:12916:backend/retrieval/routing.py
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    if not (q.startswith("what is") or q.startswith("define")):
        return None
```

`_extract_simple_definition_sentence` runs the `who`-identity branch. For the libido sentence it passes the entity/verb checks but is rejected because the sentence has no two-consecutive-capitalized-words person signal:

```13336:13337:backend/retrieval/routing.py
                    if not _person_signal(s):
                        continue
```

`_person_signal` requires a `Firstname Lastname` shape:

```13205:13206:backend/retrieval/routing.py
            if re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", s):
                return True
```

"Freud's idea that libido is the prime impulse of life" has only one capitalized token (`Freud`), so `_person_signal` is `False` and the libido sentence is rejected here.

#### 4. The generic doc-scan re-admits the rejected libido sentence

Immediately after candidate generation, `_extract_definition_route_answer` runs a generic per-doc sentence scan that has none of the `who`-query person/biography guards. It only requires the entity plus a present-tense definition verb:

```738:746:backend/retrieval/routing.py
        for s in scan_sents:
            cs = _clean_definition_like_sentence(s)
            if not cs:
                continue
            if entity_l and not re.search(rf"\b{re.escape(entity_l)}\b", cs.lower()):
                continue
            if not re.search(r"\b(?:is|are|refers\s+to|defined\s+as|means|involves|includes|focuses\s+on|characterized\s+by)\b", cs.lower()):
                continue
            collected.append(cs)
```

Two consequences at `routing.py:744` / `routing.py:746`:

- The verb whitelist is present tense only (`is|are|refers to|...`). It does not include `was`. A biography sentence such as `Freud was an Austrian neurologist ... founder of psychoanalysis` uses `was` and is therefore never collected.
- "Freud's idea that libido is the prime impulse of life" contains `freud` and `is`, so it is appended to `collected` at `routing.py:746`, the exact line where the sentence the `who` extractor rejected re-enters the pipeline.

#### 5. Definition scoring + quality rejection

Each collected candidate is scored by the nested `_score_definition_candidate` (`routing.py:635`). The biography-style content is hard-rejected:

```656:658:backend/retrieval/routing.py
        if re.search(r"\b(?:believed|famous|educator|founder|introduced\s+by|developed\s+by|born|died|stimulus\s+response)\b", low):
            _log_definition_quality_rejection(s, "biographical_or_attribution_noise")
            return -10**9
```

```688:689:backend/retrieval/routing.py
        if _is_biography_or_history_style(s):
            score -= 3.0
```

The generic quality gate `_definition_quality_rejected_reason` (`backend/retrieval/validation.py:242`) does not save the biography either. It rejects OCR/list/heading fragments, missing entity, missing cue and pronoun-led fragments, but a `was`-form biography that reached scoring is already killed at `routing.py:656`.

The libido sentence, by contrast, scores positively: it has the `is` verb (`+3.0`, `routing.py:669-670`), contains `freud` (`+1.5`, `routing.py:677-678`), and is not biographical, so it survives quality rejection.

`defines_other_concept` does not reject the libido sentence, because the sentence starts with the entity (`Freud's ...`), which the function treats as the entity being the subject:

```5904:5906:backend/retrieval/routing.py
    entity_subject_re = re.compile(rf"^(?:the\s+)?{re.escape(e)}\b")
    if entity_subject_re.search(s):
        return False
```

#### 6. Fallback / final selection

The ranked loop sorts surviving candidates and returns the first one that passes the (lenient) strict relevance guard:

```778:784:backend/retrieval/routing.py
    if ranked:
        ranked.sort(key=lambda x: x[0], reverse=True)
        for _score, candidate in ranked:
            if _passes_strict_definition_relevance_guard(query_text, candidate):
                S.logger.info("[DEF QUALITY] selected_sentence=%s", _preview_for_quality_log(candidate, 220))
                return _append_rich_definition_context(query_text, docs, candidate)
            _log_definition_quality_rejection(candidate, "strict_definition_guard_failed")
```

`_passes_strict_definition_relevance_guard` only checks non-empty / non-OCR / non-boilerplate / entity-referenced. It cannot distinguish a biography from a theory sentence:

```16967:16971:backend/retrieval/routing.py
    if not _definition_entity_or_reference_match(query_text, s):
        S.logger.info("[STRICT DEF PREF MISS] query=%s reason=entity_not_referenced", q_low[:120])
        return False
    S.logger.info("[STRICT DEF PREF PASS] query=%s reason=generic_grounded_check", q_low[:120])
    return True
```

The libido sentence references `Freud`, passes the guard, and is returned at `routing.py:783` (wrapped by `_append_rich_definition_context`, `routing.py:1207`).

The secondary fallback loop (`routing.py:786-804`) re-walks the original `candidates` list without `_score_definition_candidate`, so it is also capable of resurrecting a quality-rejected sentence on `who`-style queries. It is not reached here because the ranked loop already returned at `routing.py:783`.

### Freud - wrong-selection summary

| Stage | Function / line | Effect on biography | Effect on libido sentence |
| --- | --- | --- | --- |
| Classification | `routing.py:10208`, `17435` | routed as `definition_entity` | routed as `definition_entity` |
| Route entry | `routing.py:22915` | `_extract_definition_route_answer` | same |
| `who` extractor | `routing.py:13336` | accepted only if `Firstname Lastname` present | rejected (no `_person_signal`) |
| Doc-scan re-admit | `routing.py:744` / `746` | excluded (`was`, not present tense) | re-admitted (`is` + `freud`) |
| Quality rejection | `routing.py:656`, `688` | hard-rejected as biographical noise | survives (positive score) |
| Final selection | `routing.py:783` | never reaches it | selected and returned |

Exact line where a previously rejected sentence becomes the selected answer: re-admission `routing.py:746`, committed at `routing.py:783`.

---

## Failure 2 - `Who is Elon Musk?` becomes "even must" despite the guard

### Executive finding

There are two independent spelling-correction code paths:

1. A guarded path, `_spelling_correction_preserving_exact_terms` (`routing.py:12242`), which detects the protected proper noun and logs `[EXACT ENTITY GUARD] spelling_correction_skipped=True`.
2. An unguarded path, `_normalize_definition_query_before_retrieval` (`routing.py:12251`), which calls `_lightweight_spelling_correction` directly and never consults the guard.

For `Who is Elon Musk?` the guard fires and skips correction on the full query, but the query is then classified as `definition_entity` (not `fact_entity`), so the unguarded normalizer runs afterward, lowercases the entity to `elon musk`, and mutates it to `even must`.

- Guard that executes: `_spelling_correction_preserving_exact_terms` (`routing.py:12242-12245`).
- Function that ignores the guard: `_normalize_definition_query_before_retrieval` (`routing.py:12251`), specifically the unguarded call at `routing.py:12316`.
- Mutation site: `_lightweight_spelling_correction._replace_token`, committed at `routing.py:12206` via the `re.sub` at `routing.py:12208`.

### Stage trace

#### Stage A - query prep guard (where the log line comes from)

In the WS / query-prep flow, `prepare_query_for_rag` calls `_apply_spelling_correction`:

```224:231:backend/rag_query_prep.py
def _apply_spelling_correction(text: str) -> str:
    try:
        from backend.assistify_rag_server import _spelling_correction_preserving_exact_terms

        corrected = _spelling_correction_preserving_exact_terms(text)
        return corrected if corrected else text
    except Exception:
        return text
```

The HTTP flow calls the same guard directly:

```236:238:backend/services/rag_service.py
    _spell_norm = _spelling_correction_preserving_exact_terms(text)
    if _spell_norm and _spell_norm.strip().lower() != (text or "").strip().lower():
        text = _spell_norm
```

The guard body detects protected exact terms and short-circuits:

```12242:12249:backend/retrieval/routing.py
def _spelling_correction_preserving_exact_terms(query_text: str, seed_docs: list[dict] | None = None) -> str:
    if S._extract_protected_exact_query_terms(query_text):
        S.logger.info("[EXACT ENTITY GUARD] spelling_correction_skipped=True query=%s", str(query_text or "")[:160])
        return query_text
    try:
        return _lightweight_spelling_correction(query_text, seed_docs=seed_docs)
    except Exception:
        return query_text
```

`_extract_protected_exact_query_terms` detects `Elon Musk` because the proper-name regex requires two or more capitalized words:

```156:158:backend/retrieval/generation.py
_LATIN_PROPER_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Z][A-Za-z]+|[A-Z]{2,})(?:[\s\-]+(?:[A-Z][A-Za-z]+|[A-Z]{2,})){1,5}(?![A-Za-z0-9])"
)
```

```255:259:backend/retrieval/generation.py
    for match in _LATIN_PROPER_NAME_RE.finditer(raw):
        term = match.group(0)
        parts = re.findall(r"[A-Za-z][A-Za-z'.-]*", term)
        if len(parts) >= 2 or any(part.isupper() and len(part) > 1 for part in parts):
            _add(term)
```

So `Who is Elon Musk?` yields protected term `Elon Musk`, the guard logs `spelling_correction_skipped=True` and returns the query unchanged. This is the log line the user observed. The guard itself works correctly.

#### Stage B - classification routes to the unguarded normalizer

`Who is Elon Musk?` is not a fact query (`who is` maps to `definition_entity`, via `routing.py:10208` / `17435`). Both the HTTP and WS entrypoints therefore enter the unguarded normalizer.

HTTP (`call_llm_with_rag`):

```300:311:backend/services/rag_service.py
    is_fact_query_early = _classify_query_family_v2(text) == "fact_entity"
    if not is_fact_query_early:
        normalized_query, corrected_concept = _normalize_definition_query_before_retrieval(text)
        if normalized_query and normalized_query.strip().lower() != (text or "").strip().lower():
            S.logger.info(
                "RAG pre-retrieval definition normalization applied | original='%s' normalized='%s' concept='%s'",
                (text or "")[:120],
                normalized_query[:120],
                (corrected_concept or "")[:80],
            )
            S.logger.info("[FLOW] query_after = %s", (normalized_query or "")[:400])
            text = normalized_query
```

WS (`call_llm_streaming`):

```1413:1424:backend/services/streaming_service.py
    is_fact_query_early = _classify_query_family_v2(text) == "fact_entity"
    if not is_fact_query_early:
        normalized_query, corrected_concept = _normalize_definition_query_before_retrieval(text)
        if normalized_query and normalized_query.strip().lower() != (text or "").strip().lower():
            S.logger.info(
                "WS pre-retrieval normalization applied | original='%s' normalized='%s' concept='%s'",
                (text or "")[:120],
                normalized_query[:120],
                (corrected_concept or "")[:80],
            )
            S.logger.info("[FLOW] query_after = %s", (normalized_query or "")[:400])
            text = normalized_query
```

Ordering note: in `rag_service.py` the guard at line 236 runs first and correctly skips, then the normalizer at line 302 runs and re-introduces correction on the entity. The guard result is discarded.

#### Stage C - the normalizer calls correction unguarded

Inside `_normalize_definition_query_before_retrieval`, the `who is` branch extracts the entity, lowercases it, and calls `_lightweight_spelling_correction` directly, with no `_extract_protected_exact_query_terms` check:

```12309:12323:backend/retrieval/routing.py
    starter_m = re.match(r"^\s*(what\s+is|define|who\s+is)\b\s*(.+?)\s*\??\s*$", q, flags=re.IGNORECASE)
    if not starter_m:
        return q, ""

    starter = (starter_m.group(1) or "").strip().lower()
    entity_raw = (starter_m.group(2) or "").strip(" \t\n\r\"'`.,;:!?()[]{}")
    entity_l = entity_raw.lower()
    corrected_entity = _lightweight_spelling_correction(entity_l)
    corrected_entity = re.sub(r"\s+", " ", str(corrected_entity or "").strip())
    if not corrected_entity:
        corrected_entity = entity_l
    concept_aliases = {}
    corrected_entity = concept_aliases.get(corrected_entity, corrected_entity)

    normalized_query = f"{starter} {corrected_entity}".strip()
```

Two compounding facts at `routing.py:12315-12316`:

- `entity_l = "elon musk"`, the entity is lowercased, so even the in-function capitalization heuristics inside `_lightweight_spelling_correction` (which skip all-uppercase tokens) cannot protect it.
- `_lightweight_spelling_correction(entity_l)` is called with no guard. This is the function that ignores `[EXACT ENTITY GUARD]`.

The same unguarded call exists for the `meaning of` / `what is meant by` branch at `routing.py:12290`.

#### Stage D - the mutation

Inside `_lightweight_spelling_correction`, `_replace_token` corrects each word. Neither `elon` nor `musk` is in the protected function-word set (`routing.py:12106-12115`), so both are eligible:

```12116:12117:backend/retrieval/routing.py
        if low in _PROTECTED:
            return token
```

`_PROTECTED` contains words like `must`, `that`, `were`, etc.; it is keyed on the original token `low`, so `musk` / `elon` are not protected even though the replacement `must` is itself a protected word.

- `elon` to `even`: edit distance 2 (`elon` vs `even`); `elon` is not in the KB vocab, so `min_confidence = 0.88` and the computed confidence `0.90` clears it.
- `musk` to `must`: edit distance 1, high-frequency dictionary/vocab word `must`, confidence about `0.95`.

Candidate search and acceptance:

```12140:12166:backend/retrieval/routing.py
        for cand in candidates:
            if cand == low:
                continue
            dist = _edit_distance_leq(low, cand, cap=2)
            if dist > 2:
                continue
            ...
        if best_dist > 2 or best == token:
            return token
```

The mutation is committed here:

```12200:12208:backend/retrieval/routing.py
        correction_events.append({
            "before": token,
            "after": best,
            "confidence": confidence,
            "source": source_map.get(best, "document_vocab"),
        })
        return _case_like(token, best)

    corrected = re.sub(r"\b[a-zA-Z]{2,}\b", _replace_token, q)
```

Result: `entity_l = "elon musk"` becomes `corrected_entity = "even must"` and `normalized_query = "who is even must"`, assigned back to `text` at `rag_service.py:311` / `streaming_service.py:1424`. Retrieval then runs on the mutated query.

### Elon Musk - guard vs. mutation summary

| Question | Answer (function / line) |
| --- | --- |
| Which guard executes? | `_spelling_correction_preserving_exact_terms` - `routing.py:12242-12245` (called from `rag_query_prep.py:228`, `rag_service.py:236`, `voice_service.py:509`). |
| Why does the guard fire? | `_extract_protected_exact_query_terms` matches `Elon Musk` via `_LATIN_PROPER_NAME_RE` (two or more capitalized words) - `generation.py:156`, `255-259`. |
| Which later function ignores the guard? | `_normalize_definition_query_before_retrieval` - `routing.py:12251`, invoked at `rag_service.py:302` and `streaming_service.py:1415`. |
| Why does it run? | `Who is Elon Musk?` classifies as `definition_entity`, not `fact_entity`, so `is_fact_query_early == False`. |
| Where is the guard bypassed? | Direct unguarded call `_lightweight_spelling_correction(entity_l)` - `routing.py:12316` (also `12290`). The entity is lowercased first (`routing.py:12315`). |
| Where does the mutation occur? | `_lightweight_spelling_correction._replace_token` - accepted at `routing.py:12165-12206`, applied via `re.sub` at `routing.py:12208`. elon to even (dist 2), musk to must (dist 1). |

---

## Root-cause statements (no fixes)

- Freud: the definition route's `who is` person extractor rejects the theory sentence (`routing.py:13336`), but a separate generic doc-scan re-admits it (`routing.py:746`) using a present-tense-only verb whitelist (`routing.py:744`) that simultaneously excludes the `was`-form biography. The scorer then hard-rejects any biography that reaches it (`routing.py:656`, `688`), leaving the libido sentence as the top survivor, selected at `routing.py:783`.
- Elon Musk: the exact-entity guard and the definition normalizer are two separate code paths. The guard (`routing.py:12244`) correctly skips, but the normalizer (`routing.py:12251`) calls `_lightweight_spelling_correction` directly on the lowercased entity (`routing.py:12316`) without re-checking `_extract_protected_exact_query_terms`, so the mutation happens at `routing.py:12206`.

## Genericity assessment

The investigation used only generic, document-agnostic properties: query-grammar classifiers, verb whitelists, edit-distance correction thresholds, proper-noun regexes, and the definition scorer structural predicates. No finding depends on the words "Freud", "Elon", or any specific document, value, or entity; the same code paths apply to any single-name `who is X?` query and any two-word proper noun.

## Evidence-origin assessment

Every claim is anchored to a concrete function and line range in the current source tree (`backend/retrieval/routing.py`, `backend/retrieval/generation.py`, `backend/retrieval/validation.py`, `backend/services/rag_service.py`, `backend/services/streaming_service.py`, `backend/rag_query_prep.py`). Runtime confirmation markers for these paths are `[EXACT ENTITY GUARD]`, `[FLOW] query_after`, `[DEF QUALITY] rejected_reason=...`, `[DEF QUALITY] selected_sentence=...`, `[STRICT DEF PREF PASS/MISS]`, and `[ANSWER ROUTE] mode=definition deterministic=true`.

## Future-document compatibility assessment

Both failure mechanisms generalize to future documents:

- Any future `who is <single-name>?` whose biography is phrased in past tense (`X was ...`, `founder of ...`, `born in ...`) will be filtered out by the same present-tense doc-scan and biographical-noise scorer, and a present-tense theory or attribution sentence mentioning the name will be selected instead.
- Any future multi-word proper noun in a `who is` / `what is` / `define` query will be protected by the guard but then lowercased and silently corrected by the definition normalizer, regardless of domain.

No code changes were made.
