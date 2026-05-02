"""
TTS PERF probe: drive the /ws + /tts pipeline like the real browser would so the
new [TTS PERF] / [TTS PLAYBACK] instrumentation can be observed end-to-end.

For each query:
  1. Open /ws, send the text query, collect the streamed answer.
  2. POST the final answer to /tts and stream the WAV body.
  3. Print real client-side timing (request start, first audio chunk, audio
     finished) — mimicking the [TTS PLAYBACK] logs the browser would emit.

Behavior of the RAG system is NOT changed; this is read-only probing.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Optional

import aiohttp
import websockets


WS_URL   = "ws://127.0.0.1:7000/ws"
TTS_URL  = "http://127.0.0.1:7000/tts"

QUERIES = [
    "What is psychology?",
    "What is psychology?",
    "List the goals of psychology",
    "so what about the Control of human behavior in the goals of psychology what does it means",
]


async def ws_query(question: str) -> tuple[str, dict[str, float]]:
    timing: dict[str, float] = {}
    timing["t_send"] = time.perf_counter()
    async with websockets.connect(
        WS_URL,
        max_size=None,
        ping_interval=None,   # don't kill long generations with keepalive timeouts
        open_timeout=60,
        close_timeout=10,
    ) as ws:
        await ws.send(json.dumps({"text": question}))
        full = ""
        first_token_at: Optional[float] = None
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=180.0)
            except asyncio.TimeoutError:
                print("[probe] WS timeout")
                break
            if isinstance(msg, (bytes, bytearray)):
                continue
            try:
                data = json.loads(msg)
            except Exception:
                continue
            if data.get("type") == "aiResponseChunk":
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                    timing["t_first_token"] = first_token_at
                full += data.get("text", "")
            elif data.get("type") == "aiResponseDone":
                if "fullText" in data:
                    full = data["fullText"]
                timing["t_text_done"] = time.perf_counter()
                break
            elif "error" in data:
                print(f"[probe] WS error: {data['error']}")
                break
    return full, timing


async def post_tts(text: str) -> dict[str, float]:
    timing: dict[str, float] = {}
    text_clean = re.sub(r"[\U00010000-\U0010ffff]", "", text or "").strip()
    if not text_clean:
        print("[probe] empty answer; skipping /tts")
        return timing
    # Truncate to ~600 chars to avoid massive synthesis (browser also splits)
    text_clean = text_clean[:600]
    timing["pb_request_start"] = time.perf_counter()
    print(f"[TTS PLAYBACK probe] request started | text_len={len(text_clean)}")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            TTS_URL,
            json={"text": text_clean},
            timeout=aiohttp.ClientTimeout(total=180, sock_connect=5, sock_read=None),
        ) as resp:
            timing["pb_headers"] = time.perf_counter()
            print(
                f"[TTS PLAYBACK probe] headers status={resp.status} "
                f"req->headers={int((timing['pb_headers'] - timing['pb_request_start']) * 1000)}ms"
            )
            if resp.status != 200:
                body = await resp.text()
                print(f"[probe] /tts failed: {resp.status} {body[:160]}")
                return timing
            bytes_total = 0
            chunk_count = 0
            async for chunk in resp.content.iter_chunked(4096):
                if "pb_first_audio" not in timing:
                    timing["pb_first_audio"] = time.perf_counter()
                    print(
                        f"[TTS PLAYBACK probe] first audio chunk | "
                        f"req->first_audio={int((timing['pb_first_audio'] - timing['pb_request_start']) * 1000)}ms "
                        f"chunk_bytes={len(chunk)}"
                    )
                bytes_total += len(chunk)
                chunk_count += 1
            timing["pb_audio_finished"] = time.perf_counter()
            print(
                f"[TTS PLAYBACK probe] audio finished | "
                f"total_ms={int((timing['pb_audio_finished'] - timing['pb_request_start']) * 1000)} "
                f"bytes={bytes_total} chunks={chunk_count}"
            )
    return timing


def _ms(a: Optional[float], b: Optional[float]) -> str:
    if a is None or b is None:
        return "N/A"
    return f"{int(round((b - a) * 1000))} ms"


async def main() -> None:
    for i, q in enumerate(QUERIES, 1):
        print("\n" + "=" * 70)
        print(f"[probe] Query {i}/{len(QUERIES)}: {q}")
        print("=" * 70)
        try:
            answer, t_ws = await ws_query(q)
        except Exception as e:
            print(f"[probe] WS error: {e}")
            continue
        print(f"[probe] answer chars={len(answer)} preview={answer[:120]!r}")
        # Skip /tts on the not-found canonical short string to keep the probe fair
        if not answer or answer.strip().lower().startswith("not found in the document"):
            print("[probe] Not-found / empty answer — calling /tts anyway to capture timing")
        try:
            t_tts = await post_tts(answer or " ")
        except Exception as e:
            print(f"[probe] /tts error: {e}")
            t_tts = {}

        # Real timing comparison
        t_send       = t_ws.get("t_send")
        t_first_tok  = t_ws.get("t_first_token")
        t_text_done  = t_ws.get("t_text_done")
        pb_start     = t_tts.get("pb_request_start")
        pb_first     = t_tts.get("pb_first_audio")
        pb_done      = t_tts.get("pb_audio_finished")

        print("-" * 70)
        print("[probe] TIMING COMPARISON (real, end-to-end)")
        print(f"  WS send                  -> first text token : {_ms(t_send, t_first_tok)}")
        print(f"  WS send                  -> text response done: {_ms(t_send, t_text_done)}")
        print(f"  text done                -> /tts started      : {_ms(t_text_done, pb_start)}")
        print(f"  /tts started             -> first audio chunk : {_ms(pb_start, pb_first)}")
        print(f"  /tts started             -> audio finished    : {_ms(pb_start, pb_done)}")
        print(f"  WS send                  -> first audio chunk : {_ms(t_send, pb_first)}")
        print(f"  WS send                  -> audio finished    : {_ms(t_send, pb_done)}")
        print("-" * 70)
        # small gap so logs don't interleave
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(main())
