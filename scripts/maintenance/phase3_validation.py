"""Phase 3 + Phase 6 WS validation — domain cleanup + conversation intelligence
+ smart memory tests A through H.

Mirrors phase2_validation.py contract: send {"text": q, "language": ...}; wait
for aiResponseDone; collect final text + message-type counts.

Run AFTER backend is bound to ws://127.0.0.1:7000/ws.
"""

import asyncio
import json
import time

import websockets

WS_URI = "ws://127.0.0.1:7000/ws"
RECV_TIMEOUT = 240.0
NOT_FOUND = "not found in the document"


# Each group runs in its own connection so connection_id-scoped memory is
# preserved within a group but never leaks across groups.
TEST_GROUPS: dict[str, dict] = {
    "A_domain_cleanup": {
        "queries": [
            "What is bitcoin?",
            "What is ethereum?",
            "What is artificial intelligence?",
        ],
        "expect": "EXACTLY 'Not found in the document.' (no domain blocklist, strict grounding)",
    },
    "B_conversation_intelligence": {
        "queries": [
            "hi",
            "what can you help with?",
            "thanks",
            "what do you mean?",
        ],
        "expect": "natural meta/smalltalk; no RAG dump; clarification with no prior grounded answer -> not_found",
    },
    "C_smart_memory_compare": {
        "queries": [
            "What is psychology?",
            "What is management?",
            "What is the difference?",
        ],
        "expect": "grounded comparison rewritten from stable concept pair",
    },
    "D_list_followup": {
        "queries": [
            "What are the 5 functions of management?",
            "Explain the first one.",
        ],
        "expect": "grounded explanation of first item (or strict not-found if unsupported)",
    },
    "E_list_does_not_overwrite_concepts": {
        "queries": [
            "What is psychology?",
            "What are the six Ms?",
            "What is management?",
            "What is the difference?",
        ],
        "expect": "compare psychology vs management (list-entity must not overwrite stable concept pair)",
    },
    "F_invalid_comparison": {
        "queries": [
            "What are the six Ms?",
            "What is the difference?",
        ],
        "expect": "EXACTLY 'Not found in the document.' (no comparable concept pair)",
    },
    "G_regression": {
        "queries": [
            "What is managment",
            "What is psycology",
            "What are the six Ms?",
            "tell me about help",
            "random nonsense xqzzplm",
        ],
        "expect": "typo recovery + clean list + weak generic -> not_found",
        "expected_per_query": [
            "grounded",  # typo recovered
            "grounded",  # typo recovered
            "grounded",  # six Ms list
            "not_found",  # weak generic
            "not_found",  # nonsense
        ],
    },
    "H_clarification_with_prior": {
        "queries": [
            "What is psychology?",
            "What do you mean?",
        ],
        "expect": "clarification grounded in previous answer (not_found also acceptable, but no open-domain leakage)",
    },
}


async def send_query(ws, query: str, language: str = "en") -> dict:
    payload = {"text": query, "language": language}
    await ws.send(json.dumps(payload))
    msg_counts: dict[str, int] = {}
    full_text = ""
    tts_start = 0
    tts_end = 0
    binary_frames = 0
    done_seen = 0
    final_text = ""
    sources_count = -1
    t0 = time.time()
    while True:
        try:
            message = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT)
        except asyncio.TimeoutError:
            return {
                "query": query,
                "elapsed_ms": int((time.time() - t0) * 1000),
                "msg_counts": msg_counts,
                "full_text": full_text,
                "final_text": final_text,
                "tts_start": tts_start,
                "tts_end": tts_end,
                "binary_frames": binary_frames,
                "done_seen": done_seen,
                "sources": sources_count,
                "timeout": True,
            }
        if isinstance(message, str):
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue
            mt = data.get("type") or "?"
            msg_counts[mt] = msg_counts.get(mt, 0) + 1
            if mt == "aiResponse":
                full_text += data.get("text", "") or ""
            elif mt == "ttsAudioStart":
                tts_start += 1
            elif mt == "ttsAudioEnd":
                tts_end += 1
            elif mt == "aiResponseDone":
                done_seen += 1
                final_text = data.get("fullText") or full_text
                sources_count = int(data.get("sources") or 0)
                # Wait briefly for any duplicate.
                try:
                    extra = await asyncio.wait_for(ws.recv(), timeout=1.5)
                    if isinstance(extra, str):
                        try:
                            d2 = json.loads(extra)
                            mt2 = d2.get("type") or "?"
                            msg_counts[mt2] = msg_counts.get(mt2, 0) + 1
                            if mt2 == "aiResponseDone":
                                done_seen += 1
                        except Exception:
                            pass
                except asyncio.TimeoutError:
                    pass
                break
        else:
            binary_frames += 1
    return {
        "query": query,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "msg_counts": msg_counts,
        "full_text": full_text,
        "final_text": final_text,
        "tts_start": tts_start,
        "tts_end": tts_end,
        "binary_frames": binary_frames,
        "done_seen": done_seen,
        "sources": sources_count,
        "timeout": False,
    }


def is_not_found(text: str) -> bool:
    return (text or "").strip().rstrip(".").lower() == NOT_FOUND


def classify_result(group: str, idx: int, q: str, res: dict, group_meta: dict) -> tuple[str, str]:
    text = (res.get("final_text") or res.get("full_text") or "").strip()
    nf = is_not_found(text)
    if res.get("timeout"):
        return "FAIL", "timeout"
    if res.get("done_seen", 0) > 1:
        return "FAIL", f"duplicate aiResponseDone ({res['done_seen']})"
    if res.get("done_seen", 0) == 0:
        return "FAIL", "no aiResponseDone"

    if group == "A_domain_cleanup":
        # Per AI_AGENT_RULES, queries about concepts not in indexed PDFs must
        # return strict not-found via grounding (no hardcoded blocklist).
        return ("PASS", "strict not-found via grounding") if nf else \
               ("FAIL", f"expected not-found, got: {text[:120]}")

    if group == "B_conversation_intelligence":
        # hi / what can you help with / thanks should be conversational; "what
        # do you mean" with no prior state is allowed to return not-found.
        if idx in (0, 1, 2):
            if nf:
                return "FAIL", "smalltalk/meta returned not-found"
            if len(text) > 600:
                return "WARN", f"reply unusually long ({len(text)} chars)"
            return "PASS", "conversation reply"
        # idx 3: "what do you mean?" no prior grounded answer
        return "PASS", ("strict not-found accepted" if nf else f"clarif ({len(text)} chars)")

    if group == "C_smart_memory_compare":
        if idx < 2:
            return "PASS", f"definition turn ({len(text)} chars)" if not nf else "WARN: definition turn returned not-found"
        # final compare
        if nf:
            return "WARN", "compare turn returned not-found (acceptable strict)"
        # heuristics for grounded comparison
        if len(text) < 30:
            return "FAIL", f"compare reply too short: {text!r}"
        return "PASS", f"compare reply ({len(text)} chars)"

    if group == "D_list_followup":
        if idx == 0:
            return ("PASS", f"list turn ({len(text)} chars)") if not nf else ("WARN", "list turn not-found")
        # second: explain first
        if nf:
            return "PASS", "strict not-found accepted (unsupported explanation)"
        if len(text) < 20:
            return "FAIL", f"explanation too short: {text!r}"
        return "PASS", f"explanation ({len(text)} chars)"

    if group == "E_list_does_not_overwrite_concepts":
        if idx < 3:
            return "PASS", f"setup turn {idx} ({len(text)} chars)"
        # final compare expected to be psychology vs management
        if nf:
            return "WARN", "compare turn returned not-found"
        low = text.lower()
        # We expect both stable concepts to appear, NOT 'six ms'
        if "six" in low and "m" in low and "psychology" not in low:
            return "FAIL", f"compare locked onto list-entity instead of concept pair: {text[:160]}"
        return "PASS", f"compare reply ({len(text)} chars)"

    if group == "F_invalid_comparison":
        if idx == 0:
            return "PASS", f"list turn ({len(text)} chars)"
        return ("PASS", "strict not-found preserved") if nf else \
               ("FAIL", f"expected not-found, got: {text[:160]}")

    if group == "G_regression":
        expected = group_meta.get("expected_per_query", [])[idx]
        if expected == "not_found":
            return ("PASS", "strict not-found preserved") if nf else \
                   ("FAIL", f"expected not-found, got: {text[:120]}")
        return ("PASS", f"answered ({len(text)} chars)") if not nf and len(text) > 5 else \
               ("FAIL", f"weak/short reply: {text[:120]}")

    if group == "H_clarification_with_prior":
        if idx == 0:
            return "PASS", f"definition turn ({len(text)} chars)"
        if nf:
            return "PASS", "strict not-found accepted"
        if len(text) < 10:
            return "FAIL", f"clarification too short: {text!r}"
        return "PASS", f"clarification reply ({len(text)} chars)"

    return "WARN", "unknown group"


async def run_group(name: str, group: dict) -> list[dict]:
    print(f"\n=== {name} === expect: {group['expect']}")
    out = []
    async with websockets.connect(WS_URI, max_size=None) as ws:
        for idx, q in enumerate(group["queries"]):
            print(f"  > {q}")
            try:
                res = await send_query(ws, q)
            except Exception as e:
                res = {"query": q, "error": str(e)}
            if "error" in res:
                verdict, reason = "FAIL", res["error"]
            else:
                verdict, reason = classify_result(name, idx, q, res, group)
            res["verdict"] = verdict
            res["reason"] = reason
            preview = (res.get("final_text") or res.get("full_text") or "")[:160].replace("\n", " ")
            print(f"    [{verdict}] {reason} | {preview}")
            out.append(res)
    return out


async def main():
    overall = []
    for name, group in TEST_GROUPS.items():
        results = await run_group(name, group)
        for r in results:
            overall.append((name, r.get("query"), r.get("verdict"), r.get("reason"), (r.get("final_text") or r.get("full_text") or "")[:160].replace("\n", " ")))

    print("\n\n================ SUMMARY ================")
    fails = 0
    warns = 0
    for name, q, verdict, reason, preview in overall:
        marker = "OK" if verdict == "PASS" else verdict
        print(f"[{marker:4s}] {name} :: {q} | {reason} | {preview}")
        if verdict == "FAIL":
            fails += 1
        elif verdict == "WARN":
            warns += 1
    print(f"\nTOTAL: {len(overall)}  PASS: {len(overall)-fails-warns}  WARN: {warns}  FAIL: {fails}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
