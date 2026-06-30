import asyncio
import re
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.assistify_rag_server import live_rag

QUERIES = [
    "What are the six Ms?",
    "What are the phases of the pre-scientific management period?",
    "What are the five levels in Maslow's hierarchy of needs?",
]

anchors_global = ["six ms", "6 ms", "six m", "6 m", "5 levels", "phases", "principles", "levels"]
blacklist = {"fayol management", "weber", "taylor", "principles", "business management", "unit", "introduction concepts", "nature scope", "management evolution", "management thought", "contribution", "objectives", "significance", "chapter", "section"}


def split_and_clean_list(text: str):
    parts = [p.strip(' .:;,-\n\t') for p in re.split(r',|;|\n', text) if p.strip()]
    out = []
    for p in parts:
        wc = len(p.split())
        if 1 <= wc <= 6:
            out.append(p)
    return out


def generic_clean_items(items: list[str], max_words: int = 4):
    import re
    from difflib import get_close_matches
    if not items:
        return []
    cleaned = []
    seen = []
    verb_indicators = {' is ', ' are ', ' was ', ' were ', ' will ', ' include', ' includes', ' including', 'consists', 'consist', 'describe', 'describes', 'describing', 'explain', 'explains', 'explaining', 'represent', 'represents', 'should', 'must'}
    gerund_re = re.compile(r"\b\w+ing\b", flags=re.IGNORECASE)
    junk_tokens = {'chapter', 'section', 'unit', 'table', 'figure', 'introduction', 'references', 'bibliography'}
    out = []
    for it in items:
        if not it:
            continue
        s = re.sub(r'\s+', ' ', it).strip(' .:;,-()[]')
        if not s:
            continue
        s = re.sub(r'^(the|a|an)\s+', '', s, flags=re.IGNORECASE)
        low = s.lower()
        if any(tok in low for tok in junk_tokens):
            continue
        if any(ind in f' {low} ' for ind in verb_indicators):
            continue
        wc = len(s.split())
        if wc > max_words:
            continue
        if s.endswith('.') and wc > 4:
            continue
        if wc > 2 and gerund_re.search(s):
            continue
        if re.search(r'https?://|@|\[\d+\]', s):
            continue
        key = low
        close = get_close_matches(key, seen, n=1, cutoff=0.82)
        if close:
            continue
        seen.append(key)
        out.append(s)
    return out


def diagnostic_for_query(q: str):
    print('\n' + '='*80)
    print('Query:', q)
    relevant_docs = live_rag.search(q, top_k=10, return_dicts=True)
    if not relevant_docs:
        print('No docs retrieved')
        return
    # top retrieved chunks (top 5)
    top_docs = relevant_docs[:5]
    print('\nTop retrieved chunks:')
    for i, d in enumerate(top_docs, 1):
        meta = d.get('metadata') or {}
        print(f" {i}. source={d.get('source') or meta.get('source') or ''} page={meta.get('page') or d.get('page') or ''} sim={d.get('similarity')} exact={d.get('exact_phrase_matched')} concepts={d.get('concept_hits')} matched_tokens={d.get('matched_tokens')} chunk_role={meta.get('chunk_role')}")

    top_doc = relevant_docs[0]
    top_signals = {
        'top_similarity': float(top_doc.get('similarity') or 0.0),
        'top_exact': bool(top_doc.get('exact_phrase_matched')),
        'top_concept_hits': int(top_doc.get('concept_hits') or 0),
        'matched_tokens': top_doc.get('matched_tokens') or []
    }
    print('\nTop chunk score/confidence signals:', top_signals)

    # Selected anchor
    qnorm = q.lower()
    anchor_phrase = None
    for a in anchors_global:
        if a in qnorm:
            anchor_phrase = a
            break
    print('\nSelected anchor (from query):', anchor_phrase)

    # Extraction window text (attempt to mimic function)
    raw_top = str(top_doc.get('text') or '')
    raw_norm = raw_top.lower()
    anchor_found = False
    local_start = 0
    local_end = len(raw_top)
    local_ctx = raw_top
    if anchor_phrase:
        idx = raw_norm.find(anchor_phrase)
        if idx != -1:
            anchor_found = True
            local_start = max(0, idx - 250)
            local_end = min(len(raw_top), idx + 400)
            local_ctx = raw_top[local_start:local_end]
    print('\nAnchor found in top chunk:', anchor_found)
    print('\nExtraction window text (excerpt):')
    print(local_ctx[:1200])

    # Now reproduce extraction patterns to capture raw candidates before cleaning
    extracted_stage = []
    pattern_used = None
    # Pattern A
    if anchor_phrase and anchor_found:
        m = re.search(rf"{re.escape(anchor_phrase)}\s*[:\-–]\s*([^\n]{{1,400}})", local_ctx, flags=re.IGNORECASE)
        if m:
            items = split_and_clean_list(m.group(1))
            extracted_stage = [it for it in items if it.lower() not in blacklist]
            pattern_used = 'Pattern A: colon/comma list after anchor'
    if not extracted_stage and anchor_phrase and anchor_found:
        m2 = re.search(rf"{re.escape(anchor_phrase)}[\s\S]{{0,30}}?\b(?:are|is)\b\s*([^\n]{{1,400}})", local_ctx, flags=re.IGNORECASE)
        if m2:
            items = split_and_clean_list(m2.group(1))
            extracted_stage = [it for it in items if it.lower() not in blacklist]
            pattern_used = 'Pattern B: "are/is" followed by list'
    # Inline/token fallback
    try:
        if anchor_phrase and anchor_found:
            idx = raw_norm.find(anchor_phrase)
            after = raw_top[idx: idx + 300]
            tokens = re.findall(r"\b[a-zA-Z]{3,}\b", after.lower())
            stopwords = {"include", "are", "the", "and", "of", "to", "in", "for", "with", "by", "on", "as", "an", "a", "or", "etc", "is"}
            meaningful = [t for t in tokens if t not in stopwords and len(t) > 2]
            segment = raw_top[idx: idx + 120]
            inline_followed_by_colon_or_list = False
            if re.search(rf'{re.escape(anchor_phrase)}\s*[:\-–]', segment, flags=re.IGNORECASE):
                inline_followed_by_colon_or_list = True
            if re.search(r'\n\s*\d+\)', raw_top[idx: idx + 400]):
                inline_followed_by_colon_or_list = True
            if len(meaningful) >= 5 and inline_followed_by_colon_or_list:
                # numbered/bulleted
                numbered = re.search(r'\n\s*\d+\)', raw_top[idx: idx + 400])
                if numbered:
                    after_block = raw_top[idx: idx + 400]
                    bullets = []
                    for line in after_block.splitlines():
                        m_num = re.match(r'^\s*(?:\d+[\.)]|\d+\))\s*(.+)', line)
                        if m_num:
                            cand = m_num.group(1).strip(' .:;,-')
                            if 1 <= len(cand.split()) <= 8:
                                bullets.append(cand)
                    bullets = [b for b in bullets if b.lower() not in blacklist]
                    if bullets:
                        extracted_stage = bullets
                        pattern_used = 'Inline numbered block after anchor'
                if not extracted_stage:
                    items = meaningful
                    items = [it for it in items if it.lower() not in blacklist]
                    if items:
                        extracted_stage = items
                        pattern_used = 'Inline token fallback'
    except Exception:
        pass

    # Pattern C: bullet lines after anchor
    if not extracted_stage and anchor_found:
        bullets = []
        lower_local = local_ctx.lower()
        pos = lower_local.find(anchor_phrase)
        after_anchor = local_ctx[pos:] if pos != -1 else local_ctx
        for line in after_anchor.splitlines():
            s = line.strip()
            if not s:
                continue
            m_b = re.match(r'^(?:[\-\u2022\*]|\d+\.|\d+\))\s*(.+)', s)
            if m_b:
                item = m_b.group(1).strip(' .:;,-')
                if 1 <= len(item.split()) <= 4:
                    bullets.append(item)
        bullets = [b for b in bullets if b.lower() not in blacklist]
        if bullets:
            extracted_stage = bullets
            pattern_used = 'Pattern C: bullets after anchor'

    # Fallback: full-context candidate generation
    candidates = []
    raw = '\n'.join(str(d.get('text') or '') for d in relevant_docs)
    # 1) bullets
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r'^(?:\s*[\-\u2022\*]|\d+\.|\d+\))\s*(.+)', s)
        if m:
            item = m.group(1).strip(' .:;,-')
            if 1 <= len(item.split()) <= 5:
                candidates.append((item, 'bullet'))
    # 2) comma fragments
    for line in raw.splitlines():
        part = line.strip()
        if not part:
            continue
        comma_frags = [p.strip() for p in part.split(',') if p.strip()]
        if len(comma_frags) >= 3 and len(part.split()) <= 40:
            for frag in comma_frags:
                wc = len(re.findall(r"\w+", frag))
                if 1 <= wc <= 5:
                    candidates.append((frag.strip(' .:;,-'), 'comma'))
    # 3) inline title-case matches when no anchor
    if not anchor_found:
        inline_matches = re.findall(r"(?<!\w)([A-Z][a-z0-9\-']{0,40}(?:\s+[A-Z][a-z0-9\-']{0,40})?)(?!\w)", raw)
        for im in inline_matches:
            im = im.strip()
            wc = len(im.split())
            if 1 <= wc <= 5:
                candidates.append((im, 'inline'))
    # 4) label-style
    label_re = re.compile(r"(?m)^\s*([A-Za-z][A-Za-z0-9\s\-]{0,60}):\s*$")
    for m in label_re.finditer(raw):
        item = m.group(1).strip()
        if 1 <= len(item.split()) <= 5:
            candidates.append((item, 'label'))

    # Deduplicate preserve order
    cleaned_pairs = []
    seen = set()
    for c, src in candidates:
        norm = re.sub(r"\s+", " ", c).strip()
        if not norm:
            continue
        key = norm.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_pairs.append((norm, src))

    # Filter by presence
    filtered_pairs = [(i, s) for i, s in cleaned_pairs if raw.lower().count(i.lower()) >= 1]

    # Final quality filter mimic
    final = []
    generic_headings = set(list(blacklist) + ['introduction', 'concepts', 'objectives', 'nature', 'scope', 'significance', 'table', 'types'])
    for item, src in filtered_pairs:
        words = item.split()
        wc = len(words)
        low = item.lower()
        if wc < 1 or wc > 4:
            continue
        if any(g in low for g in generic_headings):
            continue
        if wc == 1 and re.match(r'^[A-Z][a-z]+$', item) and src not in ('bullet', 'comma', 'label'):
            continue
        if len(item) <= 2 or item.lower() in {'you', 'it', 'this', 'they', 'we'}:
            continue
        final.append(item)

    # Post-process strip prefixes and drop query-subject tokens
    normalized_final = []
    q_tokens = set(re.findall(r"\w+", q.lower()))
    for it in final:
        if ':' in it:
            left, right = it.split(':', 1)
            if len(left.split()) <= 6:
                it = right.strip()
        it_norm = it.strip().lower()
        it_norm_base = re.sub(r"'s$", '', it_norm)
        if it_norm in q_tokens or it_norm_base in q_tokens:
            continue
        normalized_final.append(it)

    # If extracted_stage is non-empty, treat that as "raw extracted candidates before cleaning"
    raw_extracted_candidates = extracted_stage if extracted_stage else [c for c, s in cleaned_pairs]

    # Run generic_clean on raw_extracted_candidates
    cleaned_final_items = generic_clean_items(raw_extracted_candidates, max_words=5)

    print('\nPattern used:', pattern_used)
    print('\nRaw extracted candidates before cleaning:')
    for c in raw_extracted_candidates:
        print(' -', c)
    print('\nCandidates from fallback generation (sample 20):')
    for c, s in cleaned_pairs[:20]:
        print(' -', c, f'[{s}]')

    print('\nCleaned final items (after generic cleaning):')
    for it in cleaned_final_items:
        print(' -', it)

    print('\nFinal normalized_final (post-filters):')
    for it in normalized_final:
        print(' -', it)

    # Run original extractor on top chunk and full context to show what pipeline returned
    from backend.assistify_rag_server import _extract_structured_items_from_context
    top_only = _extract_structured_items_from_context(q, raw_top)
    full_ctx = _extract_structured_items_from_context(q, raw)
    print('\nExtractor result on TOP chunk (original function):', top_only)
    print('Extractor result on FULL context (original function):', full_ctx)

    # Determine root-cause heuristics
    reason = []
    # If expected tokens about 'markets' present in raw but not in cleaned_final_items and raw_extracted_candidates included forms with gerunds
    if any('market' in (x.lower()) for x in raw.splitlines()) and not any('market' in x.lower() for x in cleaned_final_items):
        reason.append('post-cleaning over-pruning (candidate contained gerund/phrase dropped by heuristics)')
    # If final includes items that are from other sections (e.g., 'Scientific Management' in pre-scientific request)
    if anchor_phrase and not anchor_found and any('scientific' in d.get('text','').lower() for d in relevant_docs[:3]):
        reason.append('anchor/window selection failed (anchor not found in top chunk) leading to mixed-section contamination')
    # If many inline 'Theory Y' etc in candidates
    if any(re.match(r'^(Theory|Theory\s+Y|Theory\s+X)', c, flags=re.IGNORECASE) for c, s in cleaned_pairs):
        reason.append('extraction candidate generation noisy (inline title-case matches captured unrelated headings)')
    # OCR noise heuristic: presence of odd tokens like 'Conversely', 'Harold' mixed in
    if any(re.search(r'[A-Z][a-z]{3,}\s+(Conversely|Harold|Conversely)', raw, flags=re.IGNORECASE) for _ in [0]):
        # cheap heuristic: check for known noisy tokens
        pass

    if not reason:
        # fallback diagnosis: if raw_extracted_candidates empty but full_ctx contains list-like items
        if raw_extracted_candidates and not cleaned_final_items:
            reason.append('post-cleaning over-pruning (cleaner removed most candidates)')
        elif not raw_extracted_candidates and cleaned_pairs:
            reason.append('extraction candidate generation failed to capture target tokens; fallback candidates available')
        else:
            reason.append('mixed/uncertain: likely mixed-section contamination and noisy extraction')

    print('\nInferred root-cause(s):')
    for r in reason:
        print(' -', r)


async def main():
    for q in QUERIES:
        diagnostic_for_query(q)

if __name__ == '__main__':
    asyncio.run(main())
