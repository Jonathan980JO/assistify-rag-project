# UPSTREAM FIXES: Chunk Ranking & Section Promotion

## Changes Map

| Function | Line | Issue | Fix |
|----------|------|-------|-----|
| `_doc_query_token_signals()` | 12290-12340 | Generic penalty applies even when marker_score HIGH | Don't penalize when markers present; reward instead |
| `_apply_heading_boost_for_family()` | 12384-12398 | Heading hits weighted at 0.75, marker_score at 0.35 | Add list bonus (+0.80) when marker_score>=0.8; weight markers at 0.95 |
| `_retrieve_with_section_bias()` | ~11280-11380 (approx) | Local window threshold 3.9 too strict for sparse lists | Lower to 2.5 for list queries; add marker_density override |

---

## PATCH 1: `_doc_query_token_signals()` - Lines 12290-12340

**Issue:** Generic penalty subtracts 0.9-1.65 for list queries with NO heading matches, even if marker_score is HIGH. This makes pages with actual lists score LOWER than pages with generic "psychology" text.

**Example:** Query="List the goals of psychology"
- Page 4 (actual list, no "goals" heading): token_hits=0, heading_hits=0, marker_score=1.8 → penalty=0.9+0.35=1.25 → final_penalty=1.25
- Page 47 ("Psychology Overview"): token_hits=2, heading_hits=1, marker_score=0 → penalty=0 → no loss

**Fix:** When marker_score >= 0.8 (indicates actual list), DON'T apply heading_hits/token_hits penalties. Apply POSITIVE reward instead.

```python
def _doc_query_token_signals(query_text: str, family_v2: str, doc: dict) -> dict[str, float]:
    tokens = _query_section_tokens(query_text, family_v2)
    section_phrases = _query_section_phrases(query_text)
    phrase_tokens: set[str] = set()
    for ph in section_phrases:
        for pt in re.findall(r"[a-z0-9]{3,}", ph.lower()):
            phrase_tokens.add(pt[:-1] if pt.endswith("s") and len(pt) > 4 else pt)
    md = dict((doc or {}).get("metadata") or {})
    txt = str((doc or {}).get("page_content") or (doc or {}).get("text") or "")
    low_txt = txt.lower()
    norm_txt = _normalize_phrase_text(txt)
    local_promoted = bool(md.get("_local_window_promoted") or md.get("local_window_promoted"))
    local_focus_hits_raw = float(md.get("local_focus_hits") or md.get("_local_focus_hits") or 0.0)
    local_heading_match_raw = float(md.get("local_heading_match") or md.get("_local_heading_match") or 0.0)
    local_list_density_raw = float(md.get("local_list_density") or md.get("_local_list_density") or 0.0)
    local_conf_raw = float(md.get("local_confidence_score") or md.get("_local_confidence_score") or md.get("_local_window_score") or 0.0)
    local_conf_norm = min(1.0, (local_conf_raw / 6.0)) if local_conf_raw > 1.0 else max(0.0, local_conf_raw)
    heading_src = _resolve_doc_heading_source(query_text, doc)
    heading_parts: list[str] = []
    chosen_heading = str(heading_src.get("chosen_heading") or "").strip()
    if chosen_heading:
        heading_parts.append(chosen_heading)
    for k in ("heading", "section", "title", "chapter", "role"):
        val = str(md.get(k) or "").strip()
        if not val:
            continue
        if _is_placeholder_heading_text(val):
            logger.info('[HEADING SOURCE DEBUG] raw_heading="%s" rejected_as_placeholder=True', val[:120])
            continue
        if _is_document_title_heading_text(val):
            logger.info('[HEADING SOURCE DEBUG] raw_heading="%s" rejected_as_document_title=True', val[:120])
            continue
        heading_parts.append(val)
    heading_lines = [str(x).strip() for x in (heading_src.get("heading_lines") or []) if str(x).strip()]
    heading_parts.extend(heading_lines)
    heading_blob = " ".join(heading_parts).lower()
    norm_heading = _normalize_phrase_text(" ".join(heading_parts))
    heading_detected = bool(chosen_heading)
    toc_like = bool(re.search(r"\b(?:table\s+of\s+contents|contents?)\b", f"{heading_blob}\n{low_txt[:900]}"))

    if not tokens:
        return {
            "token_hits": 0.0,
            "heading_hits": 0.0,
            "missing_penalty": 0.0,
            "generic_penalty": 0.0,
            "density": 0.0,
        }

    token_hits = 0.0
    heading_hits = 0.0
    focus_hits = 0.0
    matched = 0
    for tok in tokens:
        tok_weight = 1.0
        if family_v2 in {"list_entity", "list_structure"} and phrase_tokens:
            tok_weight = 1.0 if tok in phrase_tokens else 0.25
        in_heading_exact = bool(_token_match_light(heading_blob, tok))
        in_heading_near = False
        in_body_exact = bool(_token_match_light(low_txt, tok))
        in_body_near = False
        if in_heading_exact:
            heading_hits += 1.0 * tok_weight
        elif in_heading_near:
            heading_hits += 0.65 * tok_weight
        if in_body_exact:
            token_hits += 1.0 * tok_weight
        elif in_body_near:
            token_hits += 0.55 * tok_weight
        if tok in phrase_tokens and (in_heading_exact or in_heading_near or in_body_exact or in_body_near):
            focus_hits += 1.0
        if in_heading_exact or in_heading_near or in_body_exact or in_body_near:
            matched += 1

    missing = max(0, len(tokens) - matched)
    words = re.findall(r"[a-z0-9]+", low_txt)
    density = (token_hits + (1.2 * heading_hits)) / max(12.0, float(len(words)))

    phrase_hits = 0.0
    for ph in section_phrases:
        ph_norm = _normalize_phrase_text(ph)
        if not ph_norm:
            continue
        if ph_norm in norm_heading:
            phrase_hits += 2.2
            heading_hits += 0.9
            heading_detected = True
            continue
        if ph_norm in norm_txt[:1800]:
            phrase_hits += 1.4
            continue

        ph_toks = [t for t in re.findall(r"[a-z0-9]{3,}", ph_norm)]
        if ph_toks:
            heading_overlap = sum(1 for t in ph_toks if _token_match_light(heading_blob, t)) / max(1, len(ph_toks))
            body_overlap = sum(1 for t in ph_toks if _token_match_light(low_txt[:1800], t)) / max(1, len(ph_toks))
            if heading_overlap >= 0.60:
                phrase_hits += 0.95
                heading_hits += 0.55
                heading_detected = True
            elif body_overlap >= 0.60:
                phrase_hits += 0.60

    if tokens and heading_lines:
        for ln in heading_lines[:6]:
            ln_low = ln.lower()
            overlap = sum(1 for tok in tokens if _token_match_light(ln_low, tok))
            ratio = overlap / max(1, len(tokens))
            if overlap >= 1 and ratio >= 0.35:
                heading_hits += 0.65 + (0.25 * min(1.0, ratio))
                heading_detected = True

    marker_score = _list_marker_score(txt) if family_v2 in {"list_entity", "list_structure"} else 0.0
    if local_promoted:
        marker_score = max(marker_score, min(1.5, local_list_density_raw * 1.8))
        focus_hits += max(0.0, 0.65 * local_focus_hits_raw)
        heading_hits += max(0.0, 0.45 * local_heading_match_raw)
        phrase_hits += max(0.0, 0.25 * local_heading_match_raw)

    generic_penalty = 0.0
    if family_v2 in {"list_entity", "list_structure"}:
        # PATCH: When list markers are strong (>=0.8), don't penalize missing heading matches
        has_strong_marker = marker_score >= 0.8
        
        if not has_strong_marker:
            # Only apply penalties if markers are WEAK
            if heading_hits <= 0.0 and token_hits <= 0.0:
                generic_penalty += 0.9
            if re.search(r"\b(?:introduction|overview|summary|historical\s+background|important\s+terminology|key\s+terms?)\b", heading_blob):
                generic_penalty += 0.55
            if marker_score <= 0.05:
                generic_penalty += 0.35
            if heading_hits <= 0.0 and marker_score <= 0.10 and phrase_hits <= 0.0:
                generic_penalty += 0.85
            if phrase_tokens and focus_hits <= 0.0:
                generic_penalty += 0.75
        else:
            # When markers are strong, apply POSITIVE reward for being a list
            generic_penalty -= 0.80  # Strong reward for actual list content
            
        if toc_like:
            # Keep TOC chunks as heading hints, but lower content priority for answers.
            generic_penalty += 0.45
            if phrase_hits > 0.0 or heading_hits > 0.0:
                heading_hits += 0.25
                phrase_hits += 0.20
            else:
                generic_penalty += 0.55
        if local_promoted:
            generic_penalty -= (0.45 * local_conf_norm)
            generic_penalty -= (0.20 * min(1.0, local_focus_hits_raw / 2.0))
            generic_penalty -= (0.20 * min(1.0, local_list_density_raw / 0.2))
            generic_penalty = max(0.0, generic_penalty)

    return {
        "token_hits": float(token_hits),
        "heading_hits": float(heading_hits),
        "phrase_hits": float(phrase_hits),
        "focus_hits": float(focus_hits),
        "marker_score": float(marker_score),
        "missing_penalty": float(0.45 * missing),
        "generic_penalty": float(generic_penalty),
        "density": float(density),
        "local_promoted": float(1.0 if local_promoted else 0.0),
        "local_focus_hits": float(local_focus_hits_raw),
        "local_heading_match": float(local_heading_match_raw),
        "local_list_density": float(local_list_density_raw),
        "local_confidence_score": float(local_conf_norm),
        "toc_hint": float(1.0 if toc_like else 0.0),
        "heading_detected": float(1.0 if heading_detected else 0.0),
        "heading_placeholder_rejected": float(1.0 if heading_src.get("placeholder_rejected") else 0.0),
        "heading_document_title_rejected": float(1.0 if heading_src.get("document_title_rejected") else 0.0),
    }
```

**Root Cause Fixed:** "generic heading boost for unrelated content" - Page 47 with "Psychology emerged" was beating Page 4 with actual list

---

## PATCH 2: `_apply_heading_boost_for_family()` - Lines 12384-12398

**Issue:** Heading hits get 0.75 weight, token hits get 0.45, but marker_score (MOST important for lists) only gets 0.35. Plus NO special list bonus exists.

**Fix:** Add list bonus (+0.80 when marker_score >= 0.8); increase marker_score weight from 0.35 to 0.95.

```python
def _apply_heading_boost_for_family(query_text: str, family_v2: str, docs: list[dict]) -> list[dict]:
    if not docs:
        return docs

    context_tokens, focus_tokens = _split_query_context_focus_tokens(query_text, family_v2)

    def _doc_debug_key(doc: dict) -> str:
        md_local = dict((doc or {}).get("metadata") or {})
        src = str(md_local.get("source") or md_local.get("filename") or md_local.get("id") or "")
        return f"{src}::{md_local.get('chunk_index')}"

    scored: list[tuple[float, dict, float, float]] = []
    base_rank_items: list[tuple[float, str]] = []
    heading_debug_rows: list[dict[str, Any]] = []
    for d in docs:
        md = dict((d or {}).get("metadata") or {})
        txt = str((d or {}).get("page_content") or (d or {}).get("text") or "")
        head = " ".join(str(md.get(k) or "") for k in ("section", "title", "chapter", "heading", "role")).lower()
        hay = f"{head}\n{txt[:1800].lower()}"

        base = 0.0
        for k in ("score", "final_score", "similarity"):
            if k in (d or {}):
                try:
                    base = float((d or {}).get(k) or 0.0)
                except Exception:
                    base = 0.0
                break
        base_rank_items.append((base, _doc_debug_key(d)))

        boost = 0.0
        sig = _doc_query_token_signals(query_text, family_v2, d)
        
        # PATCH: For lists, weight marker_score much higher (0.95 instead of 0.35)
        # and apply special list bonus when markers are strong
        if family_v2 in {"list_entity", "list_structure"}:
            marker_score = sig.get("marker_score", 0.0)
            boost += (0.75 * sig.get("heading_hits", 0.0))
            boost += (0.45 * sig.get("token_hits", 0.0))
            boost += (0.85 * sig.get("phrase_hits", 0.0))
            boost += (0.95 * marker_score)  # CHANGED from 0.35 to 0.95
            boost += (20.0 * sig.get("density", 0.0))
            # ADDED: Special bonus for strong list markers
            if marker_score >= 0.8:
                boost += 0.80
        else:
            boost += (0.75 * sig.get("heading_hits", 0.0))
            boost += (0.45 * sig.get("token_hits", 0.0))
            boost += (0.85 * sig.get("phrase_hits", 0.0))
            boost += (0.35 * sig.get("marker_score", 0.0))
            boost += (20.0 * sig.get("density", 0.0))
        
        boost -= sig.get("missing_penalty", 0.0)
        boost -= sig.get("generic_penalty", 0.0)
        if family_v2 in {"toc_structure"}:
            if "table of contents" in hay:
                boost += 0.85
        if family_v2 in {"definition_entity", "fact_entity"}:
            if re.search(r"\bdefined\s+as\b|\brefers\s+to\b", hay):
                boost += 1.1

        noise = _doc_ocr_noise_score(txt)
        if noise > 0:
            boost -= min(0.9, 0.15 * noise)

        final_score = base + boost
        d2 = dict(d)
        d2["_heading_boost"] = round(boost, 4)
        d2["_noise_score"] = round(noise, 4)
        d2["_boosted_score"] = round(final_score, 4)
        d2["_section_token_hits"] = round(sig.get("token_hits", 0.0), 4)
        d2["_section_heading_hits"] = round(sig.get("heading_hits", 0.0), 4)
        d2["_section_phrase_hits"] = round(sig.get("phrase_hits", 0.0), 4)
        d2["_section_marker_score"] = round(sig.get("marker_score", 0.0), 4)
        d2["_section_density"] = round(sig.get("density", 0.0), 6)
        heading_src = _resolve_doc_heading_source(query_text, d)
        heading_line = str(heading_src.get("chosen_heading") or "").strip()
        if not heading_line:
            heading_lines_local = _extract_heading_like_lines_from_chunk(txt, max_lines=8)
            heading_line = heading_lines_local[0] if heading_lines_local else ""
        heading_l = heading_line.lower()
        heading_query_match = bool(any(re.search(rf"\b{re.escape(t)}\b", heading_l) for t in context_tokens)) if context_tokens else False
        heading_focus_match = bool(any(re.search(rf"\b{re.escape(t)}\b", heading_l) for t in focus_tokens)) if focus_tokens else False
        heading_bonus_component = (0.75 * sig.get("heading_hits", 0.0))
        heading_debug_rows.append({
            "key": _doc_debug_key(d),
            "chunk": md.get("chunk_index"),
            "heading": heading_line,
            "query_match": heading_query_match,
            "focus_match": heading_focus_match,
            "heading_bonus": round(float(heading_bonus_component), 4),
        })
        scored.append((final_score, d2, boost, noise))

    scored.sort(key=lambda x: x[0], reverse=True)
    boosted_docs = [x[1] for x in scored]

    if family_v2 in {"list_entity", "list_structure"}:
        base_rank_items.sort(key=lambda x: x[0], reverse=True)
        base_rank_map = {key: idx for idx, (_base_score, key) in enumerate(base_rank_items)}
        boosted_rank_map = {_doc_debug_key(d): idx for idx, d in enumerate(boosted_docs)}
        heading_debug_map = {row.get("key"): row for row in heading_debug_rows}
        for d in boosted_docs[: min(5, len(boosted_docs))]:
            key = _doc_debug_key(d)
            row = heading_debug_map.get(key) or {}
            before_rank = base_rank_map.get(key, 999)
            after_rank = boosted_rank_map.get(key, 999)
            won_by_heading = bool(after_rank < before_rank)
            logger.info(
                "[HEADING DEBUG] chunk=%s heading=%s query_match=%s focus_match=%s heading_bonus=%.3f won_by_heading_boost=%s",
                row.get("chunk"),
                (row.get("heading") or "")[:120],
                bool(row.get("query_match")),
                bool(row.get("focus_match")),
                float(row.get("heading_bonus", 0.0) or 0.0),
                won_by_heading,
            )

    if family_v2 in {"list_entity", "list_structure", "toc_structure"} and len(boosted_docs) >= 2:
        best_i = 0
        best_cluster_score = -10**9
        for i, d in enumerate(boosted_docs[: min(8, len(boosted_docs))]):
            md = dict((d or {}).get("metadata") or {})
            source_id = str(md.get("source") or md.get("filename") or md.get("id") or "")
            chunk_idx = md.get("chunk_index")
            try:
                chunk_idx_int = int(chunk_idx)
            except Exception:
                chunk_idx_int = None

            center = float((d or {}).get("_boosted_score", 0.0) or 0.0)
            cluster = center
            if source_id and chunk_idx_int is not None:
                for j, dj in enumerate(boosted_docs[: min(12, len(boosted_docs))]):
                    if j == i:
                        continue
                    mdj = dict((dj or {}).get("metadata") or {})
                    source_j = str(mdj.get("source") or mdj.get("filename") or mdj.get("id") or "")
                    if source_j != source_id:
                        continue
                    try:
                        cj = int(mdj.get("chunk_index"))
                    except Exception:
                        continue
                    if abs(cj - chunk_idx_int) <= 1:
                        cluster += 0.45 * float((dj or {}).get("_boosted_score", 0.0) or 0.0)
            if cluster > best_cluster_score:
                best_cluster_score = cluster
                best_i = i

        if best_i > 0:
            anchor = boosted_docs[best_i]
            md_a = dict((anchor or {}).get("metadata") or {})
            src_a = str(md_a.get("source") or md_a.get("filename") or md_a.get("id") or "")
            try:
                idx_a = int(md_a.get("chunk_index"))
            except Exception:
                idx_a = None
            front: list[dict] = [anchor]
            if src_a and idx_a is not None:
                for d in boosted_docs:
                    if d is anchor:
                        continue
                    md_d = dict((d or {}).get("metadata") or {})
                    src_d = str(md_d.get("source") or md_d.get("filename") or md_d.get("id") or "")
                    if src_d != src_a:
                        continue
                    try:
                        idx_d = int(md_d.get("chunk_index"))
                    except Exception:
                        continue
                    if abs(idx_d - idx_a) <= 1:
                        front.append(d)
            tail = [d for d in boosted_docs if d not in front]
            boosted_docs = front + tail
            logger.info("[SECTION CONSISTENCY] family=%s anchor_moved_from=%s cluster_docs=%s", family_v2, best_i, len(front))

    top_trace = []
    for idx, d in enumerate(boosted_docs[:3]):
        md = dict((d or {}).get("metadata") or {})
        top_trace.append({
            "rank": idx,
            "id": str(md.get("id") or md.get("doc_id") or md.get("source") or "unknown"),
            "chunk_index": md.get("chunk_index"),
            "boost": d.get("_heading_boost"),
            "noise": d.get("_noise_score"),
        })
    logger.info("[HEADING BOOST] family=%s trace=%s", family_v2, top_trace)
    return boosted_docs
```

**Root Cause Fixed:** "wrong chunk ranking" - Page 47 was getting 0.75 for heading hits while Page 4 was only getting 0.35 for marker_score

---

## PATCH 3: Local Window Threshold (in existing code, find `_best_local_window` calls)

**Location:** Where `_best_local_window()` scores are compared, or in `_retrieve_with_section_bias()`, look for:
```
if ... score >= 3.9:
```

**Issue:** Threshold 3.9 too high for lists with sparse headings. A list section "Goals:" with 4 items only scores ~3.5.

**Fix:** Change threshold from 3.9 to 2.5 for list queries.

Search for this in `_retrieve_with_section_bias()` and replace:
```python
# BEFORE:
if local_score >= 3.9 and conditions_met:
    # promote

# AFTER:
threshold = 2.5 if family_v2 in {"list_entity", "list_structure"} else 3.9
if local_score >= threshold and conditions_met:
    # promote
```

---

## Summary of Changes

| Change | Before | After | Impact |
|--------|--------|-------|--------|
| Penalty for lists with strong markers | -0.9 to -1.65 | -0.80 (reward) | Page 4 now scores +0.80 instead of -1.25 |
| Heading bonus weight (list queries) | 0.75 | unchanged | Combined with PATCH 1, headings no longer override markers |
| Marker score weight (list queries) | 0.35 | 0.95 | Page 4 list bonus: 0.35*1.8=0.63 → 0.95*1.8=1.71 (+1.08) |
| List specific bonus | None | +0.80 when marker>=0.8 | Page 4 additional +0.80 |
| Local window threshold | 3.9 | 2.5 for lists | More sections promoted → better fallback path works |

**Net result:** For "List the goals of psychology":
- Page 47 baseline: ~0.65 + 0.75*1.0 + 0.45*2.0 = ~1.90 - no penalty
- Page 4 baseline: ~0.50 + 1.71 (markers) + 0.80 (bonus) - 0 = 3.01 ✅ **WINS**

---

## Exact Functions Changed

1. `_doc_query_token_signals()` - Complete replacement above
2. `_apply_heading_boost_for_family()` - Complete replacement above
3. Find & execute in existing code: Search for "score >= 3.9" and change to conditional threshold
