"""Phase 14B Ollama generation-timing evidence harness.

Investigation-only. Sends representative /api/chat streaming requests to the
LIVE Ollama endpoint and measures, from the client's perspective:

  - wall-clock first-token latency (what streaming_service's first-token
    timeout actually races against),
  - total wall-clock generation duration,
  - tokens generated (eval_count) and decode throughput (tok/s),
  - prompt-eval (prefill) duration,
  - whether the model is STILL producing tokens at the 30s / 45s marks
    that Assistify uses as cut-off points.

No product code is touched. No models are changed. The model name and
options mirror backend/services/rag_service.py + streaming_service.py.
"""
import json
import time
import sys
import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:7b"  # runtime model per config.py:178 / api/ps loaded model

# Assistify cut-off marks we want to test the model against.
MARK_STREAM_TOTAL = 30.0          # STREAM_TOTAL_TIMEOUT_S (gather wrapper)
MARK_FORMAT_FIRST_TOKEN = 45.0    # executive_memo/quiz/extreme first-token tmo
MARK_DEFAULT_FIRST_TOKEN = 15.0   # STREAM_FIRST_TOKEN_TIMEOUT_S

# A long-ish context block so prefill cost is realistic for a RAG generation
# query (the executive_memo path uses num_ctx=6144, num_predict=900).
_FILLER = ("Introduction to Psychology. " * 400).strip()


def _payload(profile):
    if profile == "executive_memo":
        system = (
            "You are an enterprise assistant. Using ONLY the context below, "
            "write a detailed executive memo with sections and bullet points.\n\n"
            "CONTEXT:\n" + _FILLER
        )
        user = "Write a full executive memo summarizing this document."
        options = {"num_ctx": 6144, "num_gpu": 99, "num_predict": 900,
                   "temperature": 0.2, "top_p": 0.9}
    else:  # general RAG answer
        system = (
            "You are a friendly support assistant. Answer using ONLY the "
            "context below.\n\nCONTEXT:\n" + _FILLER
        )
        user = "Give me a thorough summary of this document."
        options = {"num_ctx": 3072, "num_gpu": 99, "num_predict": 150,
                   "temperature": 0.2, "top_p": 0.9}
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "keep_alive": -1,
        "options": options,
    }


def measure(profile):
    payload = _payload(profile)
    print(f"\n===== PROFILE: {profile} "
          f"(num_ctx={payload['options']['num_ctx']}, "
          f"num_predict={payload['options']['num_predict']}) =====")
    t0 = time.perf_counter()
    first_token_t = None
    tokens = 0
    crossed = {"15s": None, "30s": None, "45s": None}
    done_obj = None

    with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=600) as r:
        print(f"HTTP status: {r.status_code}")
        if r.status_code != 200:
            print("body:", r.text[:500])
            return
        for line in r.iter_lines():
            if not line:
                continue
            now = time.perf_counter()
            elapsed = now - t0
            try:
                obj = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            tok = obj.get("message", {}).get("content", "")
            if tok:
                if first_token_t is None:
                    first_token_t = elapsed
                    print(f"  [first-token] wall={elapsed:.2f}s")
                tokens += 1
                for mark, secs in (("15s", 15.0), ("30s", 30.0), ("45s", 45.0)):
                    if crossed[mark] is None and elapsed >= secs:
                        crossed[mark] = tokens
            if obj.get("done"):
                done_obj = obj
                break

    total_wall = time.perf_counter() - t0
    print(f"  [total wall] {total_wall:.2f}s | tokens_streamed={tokens}")
    print(f"  [first-token latency] "
          f"{first_token_t:.2f}s" if first_token_t is not None else
          "  [first-token latency] NONE (no token before stream ended)")
    print(f"  still generating at 15s? {'YES' if total_wall > 15 else 'no'} "
          f"(tokens by 15s={crossed['15s']})")
    print(f"  still generating at 30s? {'YES' if total_wall > 30 else 'no'} "
          f"(tokens by 30s={crossed['30s']})")
    print(f"  still generating at 45s? {'YES' if total_wall > 45 else 'no'} "
          f"(tokens by 45s={crossed['45s']})")

    if done_obj:
        ns = 1e9
        ld = done_obj.get("load_duration", 0) / ns
        pe = done_obj.get("prompt_eval_count", 0)
        ped = done_obj.get("prompt_eval_duration", 0) / ns
        ec = done_obj.get("eval_count", 0)
        ed = done_obj.get("eval_duration", 0) / ns
        td = done_obj.get("total_duration", 0) / ns
        print("  --- Ollama internal timing ---")
        print(f"    load_duration       : {ld:.2f}s")
        print(f"    prompt_eval_count   : {pe} tokens")
        print(f"    prompt_eval_duration: {ped:.2f}s "
              f"({pe/ped:.1f} tok/s prefill)" if ped else "")
        print(f"    eval_count          : {ec} tokens generated")
        print(f"    eval_duration       : {ed:.2f}s "
              f"({ec/ed:.1f} tok/s decode)" if ed else "")
        print(f"    total_duration      : {td:.2f}s")


if __name__ == "__main__":
    profiles = sys.argv[1:] or ["general", "executive_memo"]
    for p in profiles:
        measure(p)
