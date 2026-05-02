"""Direct /tts perceived-latency probe.

Sends three POSTs to the live backend's /tts endpoint:
  1. Short phrase A
  2. Long phrase B (>80 chars) — exercises the policy warning
  3. Short phrase A again — should be served from the in-process cache

Prints elapsed time per request and the response size. Use after running
`tools/testing/regression_smoke_ws.py` to see the new
[TTS QUEUE]/[TTS CACHE STORE]/[TTS CACHE HIT] log lines fire.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:8000/tts"


def call_tts(text: str) -> tuple[int, int, int]:
    body = json.dumps({"text": text, "language": "en"}).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
        status = resp.status
    return status, len(data), int((time.perf_counter() - t0) * 1000)


def main() -> int:
    a = "Hello world."
    b = "This is a longer sentence that will deliberately exceed the 80 character chunking ceiling."
    plan = [("A1", a), ("B1", b), ("A2", a)]
    rc = 0
    for label, t in plan:
        try:
            status, n, ms = call_tts(t)
            print(f"  {label} status={status} bytes={n} elapsed_ms={ms} text_len={len(t)}")
        except Exception as e:
            print(f"  {label} FAIL: {e}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
