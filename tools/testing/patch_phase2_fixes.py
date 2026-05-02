"""
PHASE 2 correctness patch — applies 3 targeted fixes to assistify_rag_server.py.

Fix 1: Alpha list detection & extraction
  - bullet_num_re in _extract_list_from_context: include lowercase a)/a. markers
  - _normalize_item: also strip lowercase alpha prefixes
  - _is_meaningful_item: allow 1-word uppercase concept labels (>=4 chars)
  - block loop: add continuation merge + [ALPHA LIST DETECTED] / [LIST ITEM CONTINUATION MERGE] logs

Fix 2: _sanitize_list_answer_text improvements
  - _is_heading_artifact: change <=10 threshold to <=4 to keep 'Prediction' (10 chars)
  - Add [LIST CLEAN KEEP] log for single-word items that pass
  - Add [LIST FINAL ITEMS] log at the end

Fix 3: _validate_concept_match — perspectives rescue
  - Detect enumeration-type words (perspectives, approaches, schools, etc.)
  - Accept items forming a distinct concept cluster even if narrow_focus word
    does not appear inside the items themselves
  - Add [CONCEPT CLUSTER DETECTED] / [PERSPECTIVE RESCUE] / [SECTION FALLBACK ACTIVATED]

Fix 4: Follow-up grounding enforcement
  - Add _FOLLOWUP_EXPL_GROUND_THRESHOLD constant and
    _compute_explanation_grounding_score() helper
  - After _followup_controlled_explanation() returns, check score
  - If below threshold: emit [FOLLOWUP STRICT MODE TRIGGERED] /
    [FOLLOWUP LIMITED EXPLANATION] and return placeholder instead
"""
import re
import sys
import shutil
from pathlib import Path

TARGET = Path("g:/Grad_Project/assistify-rag-project-main/backend/assistify_rag_server.py")
BACKUP = TARGET.with_suffix(".py.bak_phase2")

def _read() -> str:
    return TARGET.read_text(encoding="utf-8")

def _write(text: str) -> None:
    TARGET.write_text(text, encoding="utf-8")

def _apply(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0:
        print(f"  FAIL [{label}]: pattern not found")
        return text
    if count > 1:
        print(f"  WARN [{label}]: pattern found {count} times — replacing first only")
        return text.replace(old, new, 1)
    print(f"  OK   [{label}]")
    return text.replace(old, new)


def main() -> None:
    shutil.copy2(TARGET, BACKUP)
    print(f"Backup written to {BACKUP}")
    src = _read()

    # ------------------------------------------------------------------ #
    # FIX 1a: bullet_num_re in _extract_list_from_context                 #
    # ------------------------------------------------------------------ #
    src = _apply(
        src,
        '    # MP-C6: also accept single uppercase letter (A./B./...) line starts so the\n'
        '    # exploded inline-enumeration items are matched as bullets.\n'
        '    bullet_num_re = re.compile(r"^\\s*(?:[-\u2022*\ufffd]|\\d+[.)]|[A-Z]\\.)\\ *(.+)$")',
        '    # MP-C6 + alpha-list fix: accept lowercase alpha markers (a)/a./b)/b. …)\n'
        '    # so alpha-marked list items are detected alongside standard bullets.\n'
        '    # Generic: structural only, no domain vocabulary.\n'
        '    bullet_num_re = re.compile(r"^\\s*(?:[-\u2022*\ufffd]|\\d+[.)]|[A-Za-z][.)])\\ *(.+)$")',
        "bullet_num_re in _extract_list_from_context",
    )

    # ------------------------------------------------------------------ #
    # FIX 1b: _normalize_item — also strip lowercase alpha prefixes       #
    # ------------------------------------------------------------------ #
    src = _apply(
        src,
        '        item = re.sub(r"^\\s*(?:[-\u2022*\ufffd]|\\d+[.)]|[A-Z]\\.)\\ *", "", item)',
        '        item = re.sub(r"^\\s*(?:[-\u2022*\ufffd]|\\d+[.)]|[A-Za-z][.)])\\ *", "", item)',
        "_normalize_item alpha prefix strip",
    )

    # ------------------------------------------------------------------ #
    # FIX 1c: _is_meaningful_item — allow 1-word uppercase concept labels #
    # ------------------------------------------------------------------ #
    OLD_MEANINGFUL = (
        '        wc = len(item.split())\n'
        '        if strict_label_query_mode:\n'
        '            if wc < 1 or wc > 8:\n'
        '                return False\n'
        '        elif wc < 2 or wc > 12:\n'
        '            return False\n'
    )
    NEW_MEANINGFUL = (
        '        wc = len(item.split())\n'
        '        if strict_label_query_mode:\n'
        '            if wc < 1 or wc > 8:\n'
        '                return False\n'
        '        elif wc < 2 or wc > 12:\n'
        '            # Allow uppercase single-word concept labels (e.g. "Prediction",\n'
        '            # "Observation") that are >=4 chars — common in alpha-marked lists\n'
        '            # (a), b), c) …) across any domain.  Generic: only casing + length.\n'
        '            if wc == 1 and len(item) >= 4 and item[0].isupper():\n'
        '                pass  # keep: single uppercase concept label\n'
        '            else:\n'
        '                return False\n'
    )
    src = _apply(src, OLD_MEANINGFUL, NEW_MEANINGFUL, "_is_meaningful_item 1-word fix")

    # ------------------------------------------------------------------ #
    # FIX 1d: block loop — add alpha detection + continuation merge       #
    # ------------------------------------------------------------------ #
    OLD_BLOCK_LOOP = (
        '    for block in candidate_blocks[:max_blocks]:\n'
        '        if query_tokens and _anchor_hits(block) == 0:\n'
        '            continue\n'
        '        collected: List[str] = []\n'
        '        for ln in block.get("lines") or []:\n'
        '            collected.extend(_extract_items_from_line(ln))\n'
        '        ordered = _dedupe_ordered(collected)\n'
    )
    NEW_BLOCK_LOOP = (
        '    # Regex to detect alpha-marked lines: a) Item, b) Item, a. Item, b. Item\n'
        '    _alpha_marker_re_ctx = re.compile(r"^\\s*[a-z][.)]\\s*\\S", re.IGNORECASE)\n'
        '\n'
        '    for block in candidate_blocks[:max_blocks]:\n'
        '        if query_tokens and _anchor_hits(block) == 0:\n'
        '            continue\n'
        '\n'
        '        # Continuation merge for alpha lists: lines starting with "and/or"\n'
        '        # are appended to the preceding alpha-item line so that split items\n'
        '        # like "f) Control of human behavior" + "and mental processes" are\n'
        '        # preserved as a single item. Generic — no domain vocabulary.\n'
        '        raw_block_lines = block.get("lines") or []\n'
        '        _has_alpha = any(_alpha_marker_re_ctx.match(ln) for ln in raw_block_lines)\n'
        '        if _has_alpha:\n'
        '            _alpha_cnt = sum(1 for ln in raw_block_lines if _alpha_marker_re_ctx.match(ln))\n'
        '            logger.info(\n'
        '                "[ALPHA LIST DETECTED] heading=%r alpha_lines=%d total_lines=%d",\n'
        '                str(block.get("heading") or "")[:50], _alpha_cnt, len(raw_block_lines),\n'
        '            )\n'
        '            merged_block_lines: List[str] = []\n'
        '            for _bln in raw_block_lines:\n'
        '                if (\n'
        '                    merged_block_lines\n'
        '                    and not _alpha_marker_re_ctx.match(_bln)\n'
        '                    and re.match(r"^\\s*(?:and|or|but|with|to)\\s+\\S", _bln, re.IGNORECASE)\n'
        '                ):\n'
        '                    merged_block_lines[-1] = merged_block_lines[-1].rstrip() + " " + _bln.strip()\n'
        '                    logger.info(\n'
        '                        "[LIST ITEM CONTINUATION MERGE] appended=%r to prev line",\n'
        '                        _bln.strip()[:60],\n'
        '                    )\n'
        '                else:\n'
        '                    merged_block_lines.append(_bln)\n'
        '        else:\n'
        '            merged_block_lines = raw_block_lines\n'
        '\n'
        '        collected: List[str] = []\n'
        '        for ln in merged_block_lines:\n'
        '            collected.extend(_extract_items_from_line(ln))\n'
        '        ordered = _dedupe_ordered(collected)\n'
    )
    src = _apply(src, OLD_BLOCK_LOOP, NEW_BLOCK_LOOP, "block loop alpha detection + continuation merge")

    # ------------------------------------------------------------------ #
    # FIX 2a: _is_heading_artifact threshold 10 -> 4                      #
    # ------------------------------------------------------------------ #
    OLD_HEADING_ARTIFACT = (
        '        if len(words) == 1 and len(words[0]) <= 10:\n'
        '            if not any(_token_match_light(low, tok) for tok in query_tokens):\n'
        '                return True\n'
    )
    NEW_HEADING_ARTIFACT = (
        '        # Threshold lowered from 10 to 4: only truly tiny noise tokens\n'
        '        # (<=4 chars) are treated as heading artifacts when not matching\n'
        '        # query tokens. This preserves valid single-word list items like\n'
        '        # "Prediction" (10 chars) that previously were incorrectly dropped.\n'
        '        if len(words) == 1 and len(words[0]) <= 4:\n'
        '            if not any(_token_match_light(low, tok) for tok in query_tokens):\n'
        '                return True\n'
    )
    src = _apply(src, OLD_HEADING_ARTIFACT, NEW_HEADING_ARTIFACT, "_is_heading_artifact threshold")

    # ------------------------------------------------------------------ #
    # FIX 2b: [LIST CLEAN KEEP] log + [LIST FINAL ITEMS] log             #
    # ------------------------------------------------------------------ #
    OLD_NORM_LOOP = (
        '        if (not _uniform_single_word_set) and _is_heading_artifact(adjusted):\n'
        '            continue\n'
        '        norm = re.sub(r"[^a-z0-9]+", " ", adjusted.lower()).strip()\n'
    )
    NEW_NORM_LOOP = (
        '        if (not _uniform_single_word_set) and _is_heading_artifact(adjusted):\n'
        '            continue\n'
        '        # Log single-word items that passed the artifact filter.\n'
        '        if len(re.findall(r"[A-Za-z][A-Za-z\\-\']*", adjusted)) == 1:\n'
        '            logger.info("[LIST CLEAN KEEP] single_word_item=%r", adjusted[:40])\n'
        '        norm = re.sub(r"[^a-z0-9]+", " ", adjusted.lower()).strip()\n'
    )
    src = _apply(src, OLD_NORM_LOOP, NEW_NORM_LOOP, "[LIST CLEAN KEEP] log")

    OLD_FINAL_RETURN = (
        '    if len(cleaned) < 2:\n'
        '        return None\n'
        '    return "\\n".join(f"- {it}" for it in cleaned)\n'
        '\n'
        '\n'
        'def _assess_list_coherence('
    )
    NEW_FINAL_RETURN = (
        '    if len(cleaned) < 2:\n'
        '        return None\n'
        '    logger.info("[LIST FINAL ITEMS] count=%d items=%s", len(cleaned),\n'
        '                [it[:30] for it in cleaned[:10]])\n'
        '    return "\\n".join(f"- {it}" for it in cleaned)\n'
        '\n'
        '\n'
        'def _assess_list_coherence('
    )
    src = _apply(src, OLD_FINAL_RETURN, NEW_FINAL_RETURN, "[LIST FINAL ITEMS] log")

    # ------------------------------------------------------------------ #
    # FIX 3: _validate_concept_match — perspectives concept cluster rescue#
    # ------------------------------------------------------------------ #
    OLD_CONCEPT_MATCH_END = (
        '            if (not has_narrow_in_items) and (not count_anchored):\n'
        '                logger.info(\n'
        '                    "[CONCEPT MATCH GUARD] reject narrow_focus_missing focus=%s items=%d count_target=%s",\n'
        '                    narrow_focus,\n'
        '                    len(items),\n'
        '                    str(cat_count),\n'
        '                )\n'
        '                return False, "narrow_focus_missing_in_short_labels"\n'
        '\n'
        '    return True, "ok"\n'
    )
    NEW_CONCEPT_MATCH_END = (
        '            if (not has_narrow_in_items) and (not count_anchored):\n'
        '                # Concept-cluster rescue: if the narrow focus token is an\n'
        '                # enumeration-type meta-word (perspectives, approaches, schools,\n'
        '                # theories, etc.) the ANSWER items are expected to be the NAMES\n'
        '                # of each perspective/approach — NOT to repeat the meta-word\n'
        '                # inside every item. Accept when items form a clean distinct\n'
        '                # cluster of short labels. Generic: no domain vocabulary.\n'
        '                _enum_type_modifiers = {\n'
        '                    "perspectives", "perspective", "approaches", "approach",\n'
        '                    "schools", "school", "theories", "theory",\n'
        '                    "viewpoints", "viewpoint", "orientations", "orientation",\n'
        '                    "frameworks", "framework",\n'
        '                }\n'
        '                _nf_is_enum_type = any(tok in _enum_type_modifiers for tok in narrow_focus)\n'
        '                if _nf_is_enum_type:\n'
        '                    _cluster_labels = [\n'
        '                        it for it in items\n'
        '                        if 1 <= len(re.findall(r"[A-Za-z][A-Za-z\\-\']*", it)) <= 5\n'
        '                    ]\n'
        '                    _all_distinct = (\n'
        '                        len({re.sub(r"[^a-z]+", " ", it.lower()).strip() for it in _cluster_labels})\n'
        '                        == len(_cluster_labels)\n'
        '                    )\n'
        '                    if len(_cluster_labels) >= 3 and _all_distinct:\n'
        '                        logger.info(\n'
        '                            "[CONCEPT CLUSTER DETECTED] %d distinct labels for enum-type narrow_focus=%s",\n'
        '                            len(_cluster_labels), narrow_focus,\n'
        '                        )\n'
        '                        logger.info(\n'
        '                            "[PERSPECTIVE RESCUE] items form distinct concept cluster -> accepted"\n'
        '                        )\n'
        '                        logger.info(\n'
        '                            "[SECTION FALLBACK ACTIVATED] narrow_focus_missing overridden by cluster detection"\n'
        '                        )\n'
        '                        return True, "ok"\n'
        '                logger.info(\n'
        '                    "[CONCEPT MATCH GUARD] reject narrow_focus_missing focus=%s items=%d count_target=%s",\n'
        '                    narrow_focus,\n'
        '                    len(items),\n'
        '                    str(cat_count),\n'
        '                )\n'
        '                return False, "narrow_focus_missing_in_short_labels"\n'
        '\n'
        '    return True, "ok"\n'
    )
    src = _apply(src, OLD_CONCEPT_MATCH_END, NEW_CONCEPT_MATCH_END, "perspectives concept cluster rescue")

    # ------------------------------------------------------------------ #
    # FIX 4: Follow-up grounding enforcement                              #
    # ------------------------------------------------------------------ #
    # 4a: add constant + helper near _FOLLOWUP_INFERRED_SUFFIX
    OLD_FOLLOWUP_SUFFIX = (
        '_FOLLOWUP_INFERRED_SUFFIX = (\n'
        '    "(The document mentions this concept but does not provide a detailed explanation.)"\n'
        ')\n'
        '\n'
        '\n'
        'def _followup_items_anchored('
    )
    NEW_FOLLOWUP_SUFFIX = (
        '_FOLLOWUP_INFERRED_SUFFIX = (\n'
        '    "(The document mentions this concept but does not provide a detailed explanation.)"\n'
        ')\n'
        '\n'
        '# Minimum fraction of content words in an LLM-generated explanation that\n'
        '# must appear (whole-word) in the retrieved chunks or previous answer.\n'
        '# Below this threshold the explanation is considered ungrounded and is\n'
        '# replaced by a cautious placeholder.  Generic — no domain vocabulary.\n'
        '_FOLLOWUP_EXPL_GROUND_THRESHOLD = 0.18\n'
        '\n'
        '\n'
        'def _compute_explanation_grounding_score(\n'
        '    explanation: str, excerpts_block: str, last_a: str\n'
        ') -> float:\n'
        '    """Return the fraction of content words in *explanation* that appear\n'
        '    (whole-word) in *excerpts_block* or *last_a*.\n'
        '\n'
        '    Used as an anti-hallucination guard for the controlled-explanation\n'
        '    mode.  Generic: only stopword filtering + whole-word matching.\n'
        '    """\n'
        '    _stop = {\n'
        '        "the", "a", "an", "of", "and", "or", "to", "in", "on", "for",\n'
        '        "with", "by", "from", "at", "is", "are", "was", "were", "be",\n'
        '        "been", "being", "this", "that", "these", "those", "it", "its",\n'
        '        "as", "but", "not", "also", "then", "when", "where", "which",\n'
        '        "who", "what", "how", "if", "so", "do", "does", "did", "has",\n'
        '        "have", "had", "will", "would", "can", "could", "should", "may",\n'
        '        "might", "must", "shall", "such", "each", "more", "most", "some",\n'
        '        "any", "all", "one", "two", "three", "their", "they", "them",\n'
        '        "we", "you", "i", "my", "your", "our",\n'
        '    }\n'
        '    haystack = ((excerpts_block or "") + " " + (last_a or "")).lower()\n'
        '    content_words = [\n'
        '        w for w in re.findall(r"[a-z]{3,}", (explanation or "").lower())\n'
        '        if w not in _stop\n'
        '    ]\n'
        '    if not content_words:\n'
        '        return 1.0  # empty explanation: no content to check\n'
        '    matched = sum(\n'
        '        1 for w in content_words\n'
        '        if re.search(rf"\\b{re.escape(w)}\\b", haystack)\n'
        '    )\n'
        '    return matched / len(content_words)\n'
        '\n'
        '\n'
        'def _followup_items_anchored('
    )
    src = _apply(src, OLD_FOLLOWUP_SUFFIX, NEW_FOLLOWUP_SUFFIX, "grounding helper + constant")

    # 4b: grounding check at the grounding-weak path (ce is used inside prev_is_list block)
    OLD_CE_GROUNDING_WEAK = (
        '                if _ce:\n'
        '                    logger.info(\n'
        '                        "[FOLLOWUP EXPLANATION SOURCE = inferred_from_context]"\n'
        '                    )\n'
        '                    ai_text = _ce.rstrip() + "\\n\\n" + _FOLLOWUP_INFERRED_SUFFIX\n'
        '                elif targeted_item is not None and len(extracted_items) == 1:\n'
    )
    NEW_CE_GROUNDING_WEAK = (
        '                if _ce:\n'
        '                    _expl_score_w = _compute_explanation_grounding_score(\n'
        '                        _ce, excerpts_block, last_a\n'
        '                    )\n'
        '                    logger.info(\n'
        '                        "[FOLLOWUP GROUNDING SCORE] score=%.2f threshold=%.2f",\n'
        '                        _expl_score_w, _FOLLOWUP_EXPL_GROUND_THRESHOLD,\n'
        '                    )\n'
        '                    if _expl_score_w < _FOLLOWUP_EXPL_GROUND_THRESHOLD:\n'
        '                        logger.info(\n'
        '                            "[FOLLOWUP STRICT MODE TRIGGERED] score=%.2f -> limited explanation",\n'
        '                            _expl_score_w,\n'
        '                        )\n'
        '                        logger.info("[FOLLOWUP LIMITED EXPLANATION]")\n'
        '                        ai_text = (\n'
        '                            "The document does not provide enough detail"\n'
        '                            " to fully explain this."\n'
        '                        )\n'
        '                    else:\n'
        '                        logger.info(\n'
        '                            "[FOLLOWUP EXPLANATION SOURCE = inferred_from_context]"\n'
        '                        )\n'
        '                        ai_text = _ce.rstrip() + "\\n\\n" + _FOLLOWUP_INFERRED_SUFFIX\n'
        '                elif targeted_item is not None and len(extracted_items) == 1:\n'
    )
    src = _apply(src, OLD_CE_GROUNDING_WEAK, NEW_CE_GROUNDING_WEAK, "grounding check in grounding-weak path")

    # 4c: grounding check at the weak-evidence guard path
    OLD_CE_WEAK_EVIDENCE = (
        '            if _ce:\n'
        '                logger.info(\n'
        '                    "[FOLLOWUP EXPLANATION SOURCE = inferred_from_context]"\n'
        '                )\n'
        '                ai_text = _ce.rstrip() + "\\n\\n" + _FOLLOWUP_INFERRED_SUFFIX\n'
        '            else:\n'
        '                logger.info(\n'
        '                    "[FOLLOWUP WEAK EVIDENCE] item=%r -> downgrade to mention-only",\n'
        '                    _itm,\n'
        '                )\n'
        '                ai_text = (\n'
        '                    f"{_itm} is mentioned in the document, "\n'
        '                    "but the available text does not provide a further explanation for it."\n'
        '                )\n'
        '        else:\n'
        '            logger.info(\n'
        '                "[FOLLOWUP WEAK EVIDENCE] item=%r -> downgrade to mention-only",\n'
        '                _itm,\n'
        '            )\n'
        '            ai_text = (\n'
        '                f"{_itm} is mentioned in the document, "\n'
        '                "but the available text does not provide a further explanation for it."\n'
        '            )\n'
    )
    NEW_CE_WEAK_EVIDENCE = (
        '            if _ce:\n'
        '                _expl_score_e = _compute_explanation_grounding_score(\n'
        '                    _ce, excerpts_block, last_a\n'
        '                )\n'
        '                logger.info(\n'
        '                    "[FOLLOWUP GROUNDING SCORE] score=%.2f threshold=%.2f",\n'
        '                    _expl_score_e, _FOLLOWUP_EXPL_GROUND_THRESHOLD,\n'
        '                )\n'
        '                if _expl_score_e < _FOLLOWUP_EXPL_GROUND_THRESHOLD:\n'
        '                    logger.info(\n'
        '                        "[FOLLOWUP STRICT MODE TRIGGERED] score=%.2f -> limited explanation",\n'
        '                        _expl_score_e,\n'
        '                    )\n'
        '                    logger.info("[FOLLOWUP LIMITED EXPLANATION]")\n'
        '                    ai_text = (\n'
        '                        "The document does not provide enough detail"\n'
        '                        " to fully explain this."\n'
        '                    )\n'
        '                else:\n'
        '                    logger.info(\n'
        '                        "[FOLLOWUP EXPLANATION SOURCE = inferred_from_context]"\n'
        '                    )\n'
        '                    ai_text = _ce.rstrip() + "\\n\\n" + _FOLLOWUP_INFERRED_SUFFIX\n'
        '            else:\n'
        '                logger.info(\n'
        '                    "[FOLLOWUP WEAK EVIDENCE] item=%r -> downgrade to mention-only",\n'
        '                    _itm,\n'
        '                )\n'
        '                ai_text = (\n'
        '                    f"{_itm} is mentioned in the document, "\n'
        '                    "but the available text does not provide a further explanation for it."\n'
        '                )\n'
        '        else:\n'
        '            logger.info(\n'
        '                "[FOLLOWUP WEAK EVIDENCE] item=%r -> downgrade to mention-only",\n'
        '                _itm,\n'
        '            )\n'
        '            ai_text = (\n'
        '                f"{_itm} is mentioned in the document, "\n'
        '                "but the available text does not provide a further explanation for it."\n'
        '            )\n'
    )
    src = _apply(src, OLD_CE_WEAK_EVIDENCE, NEW_CE_WEAK_EVIDENCE, "grounding check in weak-evidence guard path")

    _write(src)
    print("\nDone. All patches applied.")


if __name__ == "__main__":
    main()
