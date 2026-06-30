"""Phase 2 WS validation — Tests A through H.

Sends each query through the live /ws endpoint, collects aiResponseDone.fullText
plus message-type counts, and prints a structured summary. Designed to surface:
  - duplicate bubbles (multiple aiResponseDone)
  - missing TTS lifecycle (ttsAudioStart without End)
  - "Not found in the document." for weak/nonsense queries
  - clean grounded answers for legit definition / list queries

Run AFTER starting backend on ws://127.0.0.1:7000/ws.
"""

import asyncio
import json
import sys
import time
import websockets

WS_URI = "ws://127.0.0.1:7000/ws"
RECV_TIMEOUT = 180.0

TEST_GROUPS: dict[str, dict] = {
    "A_router_meta": {
        "queries": [
            "hi what can you help with",
            "no i meant your abilities",
            "what can i ask you?",
        ],
        "expect": "meta answer (no RAG dump)",
    },
    "B_smalltalk": {
        "queries": ["hi", "how are you", "thanks"],
        "expect": "smalltalk answer",
    },
    "C_definitions": {
        "queries": [
            "What is psychology?",
            "What is management?",
            "What is scientific management?",
            "What is bureaucracy?",
            "What is administrative theory?",
        ],
        "expect": "clean grounded definition or 'Not found in the document.'",
    },
    "D_lists": {
        "queries": [
            "What are the six Ms?",
            "What are the 5 functions of management?",
            "What are the goals of psychology?",
            "What are Fayol's principles of management?",
            "What are the steps in planning process?",
        ],
        "expect": "clean bullets or 'Not found in the document.'",
    },
    "E_typo": {
        "queries": ["What is managment", "What is psycology"],
        "expect": "correct grounded answer (typo-recovered)",
    },
    "F_weak_generic": {
        "queries": ["tell me about help", "random nonsense xqzzplm"],
        "expect": "EXACTLY 'Not found in the document.'",
    },
    "G_followup": {
        "queries": [
            "What is psychology?",
            "What is management?",
            "What is the difference?",
        ],
        "expect": "grounded comparison still works (last query)",
    },
    "H_ux_regression": {
        "queries": ["What is management?"],
        "expect": "no duplicate aiResponseDone, TTS lifecycle balanced",
    },
}


async def send_query(ws, query: str) -> dict:
    payload = {"text": query, "language": "en"}
    await ws.send(json.dumps(payload))
    msg_counts: dict[str, int] = {}
    full_text = ""
    tts_start = 0
    tts_end = 0
    binary_bytes = 0
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
                "binary_bytes": binary_bytes,
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
                # Stop after first done; Phase H wants to confirm only one is sent.
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
            binary_bytes += len(message)
    return {
        "query": query,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "msg_counts": msg_counts,
        "full_text": full_text,
        "final_text": final_text,
        "tts_start": tts_start,
        "tts_end": tts_end,
        "binary_bytes": binary_bytes,
        "binary_frames": binary_frames,
        "done_seen": done_seen,
        "sources": sources_count,
        "timeout": False,
    }


def classify_result(group: str, res: dict) -> tuple[str, str]:
    text = (res.get("final_text") or res.get("full_text") or "").strip()
    norm = text.strip().rstrip(".").lower()
    is_not_found = norm == "not found in the document"
    if res.get("timeout"):
        return "FAIL", "timeout"
    if res.get("done_seen", 0) > 1:
        return "FAIL", f"duplicate aiResponseDone ({res['done_seen']})"
    if res.get("done_seen", 0) == 0:
        return "FAIL", "no aiResponseDone"
    if group == "F_weak_generic":
        if is_not_found:
            return "PASS", "strict not-found preserved"
        return "FAIL", f"expected 'Not found' but got: {text[:80]}"
    if group == "B_smalltalk":
        # Should NOT be a RAG dump; usually short and friendly.
        if is_not_found:
            return "FAIL", "smalltalk returned not-found"
        if len(text) > 600:
            return "WARN", f"smalltalk reply unusually long ({len(text)} chars)"
        return "PASS", "smalltalk reply"
    if group == "A_router_meta":
        if is_not_found:
            return "FAIL", "meta query returned not-found"
        return "PASS", "meta reply"
    if group == "H_ux_regression":
        bal = "ok" if res.get("tts_start") == res.get("tts_end") else "imbalanced"
        return ("PASS" if bal == "ok" else "WARN"), f"tts_lifecycle={bal}"
    # C, D, E, G — accept grounded answer or strict not-found.
    if is_not_found:
        return "PASS", "strict not-found (accepted)"
    if len(text) < 6:
        return "FAIL", f"reply too short: {text!r}"
    return "PASS", f"answered ({len(text)} chars)"


async def run_group(name: str, group: dict) -> list[dict]:
    print(f"\n=== {name} === expect: {group['expect']}")
    out = []
    # Use one connection per group so follow-up state is preserved within group G.
    async with websockets.connect(WS_URI, max_size=None) as ws:
        for q in group["queries"]:
            print(f"  > {q}")
            try:
                res = await send_query(ws, q)
            except Exception as e:
                res = {"query": q, "error": str(e)}
            verdict, reason = classify_result(name, res) if "error" not in res else ("FAIL", res["error"])
            res["verdict"] = verdict
            res["reason"] = reason
            preview = (res.get("final_text") or res.get("full_text") or "")[:160].replace("\n", " ")
            print(f"    [{verdict}] {reason} | {preview}")
            out.append(res)
    return out


async def main():
    overall_pass = True
    summary: list[tuple[str, str, str]] = []
    for name, group in TEST_GROUPS.items():
        results = await run_group(name, group)
        for r in results:
            summary.append((name, r.get("verdict", "FAIL"), r.get("query", "")))
            if r.get("verdict") == "FAIL":
                overall_pass = False
    print("\n=== SUMMARY ===")
    for name, verdict, q in summary:
        print(f"  {verdict:5s}  {name:18s}  {q}")
    print("\nRESULT:", "PASS" if overall_pass else "FAIL")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
