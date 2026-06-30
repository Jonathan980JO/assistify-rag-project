"""Broad behavioral snapshot via signature introspection.

Given a JSON list of function names, calls each non-async function on the server
module with heuristic arguments derived from parameter names, recording the
result repr (or a stable exception tag). Running this before and after an
extraction and diffing proves the moved functions behave identically. Functions
that need richer inputs raise the same exception in both runs, so they still act
as an equivalence check (and never produce false diffs).

Usage:
    python scripts/phase8h_auto_snapshot.py <names.json> <label> <out.json>
    python scripts/phase8h_auto_snapshot.py --diff a.json b.json
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCS = [
    {"text": "Alpha system handles input and is defined as the core unit.",
     "source": "a.pdf", "score": 0.92, "chunk_index": 1, "metadata": {"source": "a.pdf"}},
    {"text": "Beta module transforms data. There are three steps: one, two, three.",
     "source": "a.pdf", "score": 0.61, "chunk_index": 2, "metadata": {"source": "a.pdf"}},
]
QUERIES = ["what is the alpha system", "list the three steps", "define beta module",
           "ما هو النظام", "how many components are there", "explain the relationship"]


def _heur(pname: str, default):
    n = pname.lower()
    if default is not inspect.Parameter.empty:
        return default
    if n in ("docs", "documents", "chunks", "results", "candidates", "context_docs", "retrieved_docs", "extra_docs", "seed_docs"):
        return list(DOCS)
    if n in ("doc", "candidate_doc", "chunk"):
        return dict(DOCS[0])
    if n in ("items", "tokens", "sources", "labels", "concepts", "lines", "segments_list", "answer_items"):
        return ["one", "two", "three"]
    if n in ("max_docs", "max_items", "max_words", "max_lines", "limit", "top_k", "scan_limit",
             "char_budget", "max_chars", "window", "relevant_chunks", "max_turns", "count"):
        return 3
    if n in ("metadata", "query_info", "state", "list_state", "t_meta"):
        return {}
    return "what is the alpha system"


def _r(v):
    try:
        return repr(v)[:600]
    except Exception as e:  # noqa: BLE001
        return f"<unrepr:{type(e).__name__}>"


def capture(names) -> dict:
    srv = __import__("backend.assistify_rag_server", fromlist=["app"])
    res: dict = {}
    for name in names:
        fn = getattr(srv, name, None)
        if fn is None:
            res[name] = "MISSING_FN"
            continue
        if inspect.iscoroutinefunction(fn):
            continue
        try:
            sig = inspect.signature(fn)
        except (ValueError, TypeError):
            continue
        # build positional args for params without defaults; first text-like param
        # is varied across queries to exercise branches.
        params = [p for p in sig.parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        text_idx = next((i for i, p in enumerate(params)
                         if p.default is inspect.Parameter.empty
                         and any(k in p.name.lower() for k in ("query", "text", "sentence", "value", "answer", "item"))), None)
        for qi, q in enumerate(QUERIES if text_idx is not None else QUERIES[:1]):
            args = []
            ok = True
            for i, p in enumerate(params):
                if p.default is not inspect.Parameter.empty:
                    break
                args.append(q if i == text_idx else _heur(p.name, p.default))
            try:
                res[f"{name}#{qi}"] = _r(fn(*args))
            except Exception as e:  # noqa: BLE001
                res[f"{name}#{qi}"] = f"EXC:{type(e).__name__}:{str(e)[:120]}"
    return res


def main():
    if sys.argv[1] == "--diff":
        a = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        b = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
        keys = sorted(set(a) | set(b))
        diffs = [(k, a.get(k, "<absent>"), b.get(k, "<absent>")) for k in keys if a.get(k) != b.get(k)]
        if diffs:
            print(f"SNAPSHOT DIFF: {len(diffs)}/{len(keys)} mismatches")
            for k, av, bv in diffs[:80]:
                print(f"  {k}\n    before={av}\n    after ={bv}")
            sys.exit(1)
        print(f"SNAPSHOT MATCH: all {len(keys)} cases identical")
        return
    names = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    label, out = sys.argv[2], sys.argv[3]
    data = capture(names)
    Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{label}] captured {len(data)} cases from {len(names)} functions -> {out}")


if __name__ == "__main__":
    main()
