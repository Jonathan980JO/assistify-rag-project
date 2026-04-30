# PHASE AR-0 — Arabic Pipeline Analysis Report
**Date**: 2025 | **Status**: Read-Only Analysis — No Code Modified  
**Files examined**: `frontend/index.html`, `Login_system/login_server.py`, `backend/assistify_rag_server.py` (~34,694 lines), `tts_service/piper_server.py`, `backend/config_head.py`

---

## A. Arabic Pipeline Diagram (End-to-End)

### A1. Text Path

```
[User clicks AR 🇸🇦 button]
  → setLanguage('ar')                             frontend/index.html ~line 666
      ├─ Update button active states
      ├─ Apply UI_STRINGS.ar (placeholder, status text, etc.)
      ├─ chatLog.style.direction = 'rtl'
      └─ checkArabicModels() (first AR select only, per arabicModelsChecked flag)
           └─ GET /arabic/status  ─(login proxy, line 2496)──► GET /arabic/status [RAG server]
                Returns: {multilingual_model_ready, multilingual_model_loaded,
                          multilingual_model_on_disk, xtts_arabic_ready ⚠️, download_state}
                If !multilingual_model_ready → show Arabic Download Modal

[Arabic Download Modal — Download button]
  → POST /arabic/download ─(login proxy, line 2519)──► POST /arabic/download [RAG server]
       └─ Async background task: downloads faster-whisper-small via HF hub
            → loads model into whisper_model_multilingual global immediately

[Arabic text input + Send]
  → chatForm.onsubmit                              frontend/index.html ~line 1020
      ├─ effectiveLang = 'ar'  (or auto → detectArabicText())
      └─ ws.send(JSON.stringify({text:"...", language:"ar"}))
           └─ Login server WS proxy (rate-limited text, no binary limit)
                └─ RAG server WS /ws receives JSON frame

[RAG Server WebSocket handler — Arabic mode]          backend/assistify_rag_server.py
  → session_language = 'ar', arabic_mode = True
  → xtts_lang = 'ar'
  → _is_arabic_small_talk(text)?
       YES → plays opener/ack PCM directly, routes to LLM with arabic_mode=True
       NO  → asyncio.gather(
               _send_ack_coro()                    plays _arabic_ack_pcm via binary WS frames
                                                   sends: ttsAudioStart / PCM bytes / ttsAudioEnd
               _translate_coro()                   translate AR→EN:
                                                     1. _translation_cache_get()  (LRU 512 entries)
                                                     2. deep_translator.GoogleTranslator (AR→EN)
                                                     3. translate_with_llm() fallback (Ollama)
             )

  → RAG search: _search_with_query_expansion(text_for_rag)   # uses ENGLISH translated text
       └─ Off-topic guard: if no docs found →
            send ARABIC_OFF_TOPIC_RESPONSE  →  _tts_single_response()  →  done

  → call_llm_streaming(language='ar')              Qwen2.5-7B via Ollama
       ├─ system_prompt: English RAG context blocks
       ├─ user message:  original Arabic question   (NOT the translation)
       ├─ assistant prefill: Arabic opener phrase   (round-robin across 10 phrases)
       │    purpose: steer Chinese-first model to output Arabic not Chinese
       ├─ LLM streams Arabic answer tokens directly
       └─ Fallback (line ~31947): if LLM outputs 0 Arabic chars:
             if Chinese output → direct Arabic re-prompt
             else              → translate_with_llm(en→ar)
             → sends corrected Arabic as {replace: true} aiResponseChunk

  → send_final_response(arabic_mode=True)
       └─ ws.send_json: {type:"aiResponseDone", arabic_mode:true, ...}

  → _tts_arabic_response(answer, ws, ...)          line 28808
       ├─ Split Arabic answer at sentence boundaries (≤200 chars per chunk)
       ├─ For each chunk:
       │    POST XTTS_SERVICE_URL/synthesize → Piper port 5002
       │    {text: chunk, language: "ar"}
       │    → Piper: _resolve_voice_tag("ar") → models/piper/ar/voice.onnx
       │    → synthesize → resample to 24kHz → WAV bytes
       │    → skip 44-byte WAV header → raw PCM16
       │    → ws.send_bytes (under _ws_write_locks[connection_id])
       │    → ws.send_json: {type:"ttsAudioStart"} and {type:"ttsAudioEnd"}
       └─ ws.send_json: {type:"arabic_tts_complete"}

[Frontend — receiving Arabic response]
  → aiResponseChunk events → appendMsg() with .arabic-msg class + dir:rtl
  → aiResponseDone (arabic_mode:true) → skips English TTS cleanup, waits for arabic_tts_complete
  → binary WS frames → _handleWsAudioChunk() → Int16Array → Float32 → Web Audio API at 24kHz
  → arabic_tts_complete → reset audio state, hide AI speaking indicator, resume live call
```

### A2. Voice (STT) Path

```
[User presses Start button — AR mode]
  → effectiveLang = 'ar'
  → ws.send({type:'control', action:'set_language', language:'ar'})
  → backend: session_language = 'ar'

[Browser records microphone audio]
  → ScriptProcessor (4096 sample buffer)
  → downsample to 16kHz, convert to PCM16 (Int16Array)
  → binary WS frames → Login proxy (no rate limit on binary)
  → RAG server audio_buffer

[Silence detection: 10 consecutive silent chunks × ~50ms = ~500ms]
  → auto_transcribe(lang='ar')                    line 33989
       ├─ IF whisper_model_multilingual loaded:
       │    WhisperModel = faster-whisper-small (multilingual)
       │    beam_size=5, language='ar', initial_prompt=_ARABIC_STT_INITIAL_PROMPT ⚠️
       └─ ELSE (model not loaded):
            Falls back to whisper_model (tiny.en) — *** COMPLETE FAILURE FOR ARABIC ***
  → ws.send_json: {type:'transcript', text: transcribed_arabic_text}
  → Optionally: ws.send_json: {type:'transcriptCorrection', text: corrected}
  → call_llm_streaming(language='ar') → same as text path above
```

---

## B. Exact Files & Functions

### B1. `frontend/index.html` (1,911 lines)

| Function / Handler | Line | Role |
|---|---|---|
| Language buttons | 503–507 | `<button onclick="setLanguage('ar')">AR 🇸🇦</button>` |
| `currentLanguage` | 629 | `let currentLanguage = 'en'` — `'en' \| 'ar' \| 'auto'` |
| `arabicModelsChecked` flag | 630 | Shows modal only once per session |
| `UI_STRINGS` | ~635 | EN and AR string tables; auto maps to EN strings |
| `setLanguage(lang)` | 666 | Switch active button, update UI strings, RTL, trigger model check |
| `checkArabicModels()` | 697 | GET /arabic/status; show download modal if needed |
| `startArabicDownload()` | ~700 | POST /arabic/download |
| `detectArabicText(text)` | ~1035 | >20% Unicode Arabic chars (`\u0600–\u06FF`) → 'ar' |
| Form submit handler | ~1020 | `effectiveLang` calc; `ws.send({text, language:effectiveLang})` |
| `appendMsg()` | ~1196 | Adds `.arabic-msg` CSS, `dir:rtl`, labels `أنت:` / `المساعد:` |
| Start button / `startRecording()` | 1230 | Sends `{type:'control', action:'set_language', language:effectiveLang}` |
| `_handleWsAudioChunk()` | ~1300 | Binary PCM16 → Float32 → Web Audio scheduled at 24kHz |
| `aiResponseDone` handler | ~1060 | If `data.arabic_mode` → wait for `arabic_tts_complete` |
| `arabic_tts_complete` handler | ~1080 | Reset audio state, hide AI speaking, resume live call |
| `transcriptCorrection` handler | ~1090 | Update last user bubble in-place |
| Language restore | 792–794 | Reads `localStorage.getItem('assistify_lang')`, accepts 'en'/'ar'/'auto' |

### B2. `Login_system/login_server.py`

| Function | Line | Role |
|---|---|---|
| `arabic_status_proxy()` | 2496 | GET /arabic/status → forward to RAG server |
| `arabic_download_proxy()` | 2519 | POST /arabic/download → forward to RAG server |
| `tts_proxy()` | 2544 | POST /tts → stream audio response back |
| `websocket_proxy()` | 3542 | Bidirectional WS bridge; binary audio bypasses rate limit |
| Auth handshake | ~3610 | Sends `{type:'auth', user:user}` to backend WS after connect |

### B3. `backend/assistify_rag_server.py`

| Function | Line | Role |
|---|---|---|
| `XTTS_SERVICE_URL` | config_head.py 175 | `os.environ.get("XTTS_SERVICE_URL", "http://127.0.0.1:5002")` |
| `whisper_model_multilingual` | 5037 | Global `Optional[WhisperModel]`; None if not loaded |
| `_MULTILINGUAL_MODEL_PATH` | 5040 | `backend/Models/faster-whisper-small/` |
| `_find_ml_model_path()` | 5484 | Checks direct folder, then HF cache snapshot |
| `_is_arabic_small_talk(text)` | ~6200 | frozenset of greeting/farewell phrases |
| `ARABIC_OFF_TOPIC_RESPONSE` | 6202 | Hardcoded Arabic refusal string (⚠️ may be domain-specific) |
| `_AR_EN_CACHE` | 6240 | `OrderedDict`, max 512, LRU eviction |
| `_sanitize_arabic_text(text)` | 6364 | Strip English words; keep numbers and generic codes |
| `_preprocess_for_tts(text)` | 6452 | Strip markdown, expand digits to Arabic words, normalize punctuation |
| `translate_with_llm(text, src, tgt)` | 6505 | AR↔EN via Ollama local LLM, retry once |
| `_detect_language(text)` | 7889 | >20% Arabic chars → 'ar'; else 'en' |
| `_ARABIC_STT_INITIAL_PROMPT` | 15417 | Domain-specific Arabic text for Whisper priming ⚠️ |
| `_tts_arabic_response(text, ws, ...)` | 28808 | Chunk answer → Piper → stream PCM binary WS frames |
| `_tts_single_response(text, ws, ...)` | 28920 | Single TTS call (off-topic, small replies) |
| `send_final_response(arabic_mode=True)` | 29054 | Sends aiResponseDone with `arabic_mode:true` flag |
| Arabic WS handler block | 29366 | `arabic_mode = (language == "ar")`, translation, RAG, guard |
| Arabic opener prefill | 31255–31259 | `messages.append({role:"assistant", content:_chosen_opener})` |
| Arabic fallback (CJK/EN→AR) | 31947 | If LLM outputs non-Arabic → translate or re-prompt |
| `auto_transcribe(lang)` | 33989 | STT model selection; Arabic uses multilingual or falls back |
| `arabic_status()` GET /arabic/status | 32719 | Returns model readiness (xtts_arabic_ready always False ⚠️) |
| `arabic_download_models()` POST | 32736 | Async faster-whisper-small download + load |

### B4. `tts_service/piper_server.py`

| Function | Line | Role |
|---|---|---|
| `_load_all_voices()` | ~80 | Loads `models/piper/en/voice.onnx` and `models/piper/ar/voice.onnx` at startup |
| `_resolve_voice_tag(language)` | ~100 | Maps 'ar'/'ar-sa'/etc. → 'ar'; 'en'/etc. → 'en' |
| `_normalize_arabic(text)` | ~140 | Strip emoji, deduplicate Arabic punctuation |
| `synthesize(req)` POST /synthesize | ~275 | Main synthesis endpoint, returns WAV response |
| Arabic voice fallback | ~290 | If AR voice not loaded → fall back to any loaded voice (silently) |
| `_synth_lock` | threading.Lock | Thread-safety guard for synthesis |
| Output sample rate | `OUTPUT_SR` | 24,000 Hz |

---

## C. What Currently Works

1. **Language button switching (EN/AR)** — RTL/LTR chatLog toggle works correctly
2. **Arabic UI strings** — placeholders, status text, labels (أنت: / المساعد:) render correctly
3. **checkArabicModels() modal flow** — GET /arabic/status triggers Download modal when multilingual model missing
4. **`/arabic/download` endpoint** — downloads faster-whisper-small, loads it immediately
5. **Multilingual Whisper model discovery via HF cache** — `models--Systran--faster-whisper-small` **exists** at `backend/Models/models--Systran--faster-whisper-small/snapshots/<hash>/`; `_find_ml_model_path()` will find it at startup
6. **Arabic text translation pipeline** — `_translation_cache_get()` → `deep_translator` Google → `translate_with_llm()` fallback; cache prevents repeated Google calls
7. **RAG retrieval with English text** — `_search_with_query_expansion(text_for_rag)` works on translated English
8. **Off-topic guard** — no RAG docs found → Arabic refusal, no English answer returned
9. **Arabic small-talk detection** — `_is_arabic_small_talk()` routes greetings correctly
10. **LLM Arabic answer generation** — Arabic question + English context + opener prefill = LLM outputs Arabic directly; CJK/English fallback handles Qwen language drift
11. **`_tts_arabic_response()`** — correctly chunks answer, POSTs to Piper with `language:"ar"`, streams binary PCM16
12. **Piper Arabic voice file EXISTS** — `models/piper/ar/voice.onnx` (~6MB) + `voice.onnx.json` confirmed present
13. **Binary PCM streaming** — same protocol as English (binary WS frames → Web Audio at 24kHz); works
14. **`arabic_tts_complete` event** — frontend correctly waits for this before cleanup in Arabic mode
15. **`transcriptCorrection` event** — STT correction updates user bubble in-place
16. **WS write lock per connection** — `_ws_write_locks[connection_id]` prevents interleaved binary frames
17. **Language persistence** — `localStorage.setItem('assistify_lang', lang)` / restore on load
18. **Login server WS proxy** — binary frames forwarded without rate limiting; text rate-limited correctly
19. **Arabic ack PCM (if warmup enabled)** — `ASSISTIFY_ENABLE_ARABIC_TTS_WARMUP=1` pre-renders opener pool; default OFF

---

## D. What is Missing or Risky

### D1. CRITICAL Issues

**C-1: Arabic STT fallback is silent and catastrophic**  
Location: `auto_transcribe(lang)` line 33989  
If `whisper_model_multilingual` fails to load (OOM, GPU failure, model corrupt), Arabic voice input falls through to `whisper_model` (English tiny.en). There is **no warning to user**. Arabic speech through a monolingual English ASR model produces complete garbage transcription, which is then sent to the RAG pipeline as the query. This is a silent, catastrophic failure mode.

**C-2: `_ARABIC_STT_INITIAL_PROMPT` is hard-coded Amazon domain vocabulary**  
Location: line 15417  
```python
_ARABIC_STT_INITIAL_PROMPT = (
    "لماذا يجب أن أبيع على أمازون؟..."  # Amazon-specific
)
```
This violates AI_AGENT_RULES.md generic system rules. Any deployment outside the Amazon seller context will prime Whisper with wrong domain vocabulary, reducing accuracy for non-Amazon queries.

**C-3: `xtts_arabic_ready` always returns `False`**  
Location: `/arabic/status` endpoint line 32719  
The response includes `xtts_arabic_ready: xtts_model is not None`. But `xtts_model` is **always** `None` (XTTS was replaced by Piper microservice). The frontend modal reads this field — it always shows the XTTS status as "not ready" even though Piper Arabic voice IS ready and working. This misleads users and any code logic checking this field.

### D2. HIGH RISK Issues

**H-1: Auto mode breaks Arabic voice STT**  
Location: `auto_transcribe()` + WS handler  
When Auto mode is active and user presses Start, `effectiveLang` is computed via `detectArabicText()` for *text* — but for voice, Auto sends `set_language:'auto'` → `session_language = 'auto'`. In `_run_stt()`: `if lang == "ar": use multilingual` — since `lang = 'auto' ≠ 'ar'`, it falls through to English tiny.en even for Arabic voice input. The user hears no error; the transcript is garbage.

**H-2: Arabic Download Modal has stale, domain-specific text**  
Location: `frontend/index.html` line ~542  
Modal still references:  
- "XTTS v2 Arabic TTS — already included" (XTTS replaced by Piper)  
- "Amazon services" (hard-coded domain name — violates generic rules)  

This is confusing to users and non-compliant with AI_AGENT_RULES.md.

**H-3: `ARABIC_OFF_TOPIC_RESPONSE` needs review for domain specificity**  
Location: line 6202  
The hardcoded Arabic refusal string may reference the Amazon/seller domain. Needs to be reviewed against AI_AGENT_RULES.md and made generic.

### D3. MEDIUM RISK Issues

**M-1: Translation latency on first Arabic query**  
No cache hit on first query of each session → ~700–900ms Google Translate round-trip + concurrent ack audio. If Google is unreachable → `translate_with_llm()` Ollama fallback adds ~2–3 seconds additional wait.

**M-2: LLM Chinese drift fallback adds variable latency**  
Qwen2.5 occasionally ignores Arabic opener prefill and outputs Chinese. The fallback (CJK detection → direct Arabic re-prompt or `translate_with_llm`) works but adds ~1–3 seconds extra latency unpredictably.

**M-3: No streaming TTS for Arabic (unlike English)**  
English TTS streams sentence-by-sentence as the LLM generates. Arabic TTS (`_tts_arabic_response`) waits for full LLM response, then chunks it for Piper. For long answers, first-audio latency is: full LLM generation time + first Piper chunk. This can be 5–10 seconds for detailed answers.

**M-4: Piper Arabic fallback is silent**  
If `models/piper/ar/voice.onnx` is corrupt/missing in future, Piper falls back to English voice (wrong phonology for Arabic text) without any error to frontend. Currently the file exists and is healthy.

**M-5: History stripped in Arabic mode with KB context**  
Line 31241: `if not relevant_docs: messages.extend(history[-10:])`. Arabic queries with KB context always strip conversation history from LLM context. Design choice, but multi-turn Arabic conversations feel stateless.

### D4. LOW RISK Issues

**L-1: `XTTS_SPEAKER = "Claribel Dervla"` sent to Piper**  
Piper ignores the `speaker` field entirely (logs it, no effect). But misleading config name.

**L-2: LocalStorage may hold 'auto' value across sessions**  
After removing Auto button (Phase AR-1), users with saved `'auto'` in localStorage would have a stale language preference restored. Requires cleanup in the restore logic.

**L-3: `_detect_language()` threshold may misfire**  
"20% Arabic chars" threshold: a short English message with an Arabic word or emoji could incorrectly trigger Arabic mode in Auto path. Not critical since Auto is being removed.

---

## E. Auto Mode Removal Safety Analysis

**Verdict: SAFE TO REMOVE**

Auto mode (`'auto'`) exists in three places; all branches can be removed without breaking any other system component.

### E1. Frontend (`frontend/index.html`)

| Location | Current Code | Change |
|---|---|---|
| Line 507 | `<button onclick="setLanguage('auto')">Auto 🔍</button>` | Remove element |
| `setLanguage()` ~line 666 | `classList.toggle('active', lang==='auto')` | Remove branch |
| `getUIStr()` | `auto` → English strings | Remove or ignore (dead code if no 'auto' call) |
| Language restore 792–794 | Accepts `'auto'` from localStorage | Replace 'auto' with 'en' fallback |
| Text submit ~line 1020 | `effectiveLang = currentLanguage === 'auto' ? detectArabicText(...) : currentLanguage` | Simplify to `effectiveLang = currentLanguage` |
| `startRecording()` line 1230 | `effectiveLang` can be 'auto' | Same simplification |

### E2. Backend (`backend/assistify_rag_server.py`)

| Location | Current Code | Change |
|---|---|---|
| WS text payload ~line 29366 | `if language == "auto": language = _detect_language(text)` | Remove block |
| `set_language` action handler | Accepts 'auto', sets `session_language = 'auto'` | Remove 'auto' from accepted values |

### E3. What is NOT affected by Auto removal
- `_detect_language()` function — stays (still used internally for other logic)
- `detectArabicText()` in frontend — can stay or be removed (currently only used for Auto)
- All RAG/STT/TTS paths — none depend on 'auto' being passed

### E4. Risk of removing Auto
**Zero functional risk.** Auto mode:  
- For text: was a convenience heuristic (>20% Arabic chars threshold)  
- For voice: was always broken (passed 'auto' to STT, which selected English model for Arabic speech)  
Removing it improves correctness (users explicitly choose their language) and eliminates the silent STT degradation bug (H-1 above).

---

## F. Recommended Phase AR-1 Fix Plan

### Priority 1 — Correctness & Compliance (No optional steps)

**AR1-001: Remove Auto button from frontend**  
Files: `frontend/index.html`  
- Remove `<button onclick="setLanguage('auto')">Auto 🔍</button>` element
- Remove 'auto' branches from `setLanguage()`, `getUIStr()`, language restore logic
- Simplify text submit + startRecording to use `currentLanguage` directly
- In language restore: if stored value is 'auto', fallback to 'en'

**AR1-002: Remove 'auto' from backend WS handler**  
Files: `backend/assistify_rag_server.py`  
- Remove `if language == "auto": language = _detect_language(text)` from text payload handler
- Remove 'auto' acceptance from `set_language` control action

**AR1-003: Replace `_ARABIC_STT_INITIAL_PROMPT` with generic content**  
Files: `backend/assistify_rag_server.py` line 15417  
- Remove Amazon-specific Arabic vocabulary from Whisper initial prompt
- Use a generic, domain-agnostic Arabic business/information prompt
- Or set to empty string (Whisper still performs well on Arabic without initial_prompt)

**AR1-004: Fix Arabic Download Modal text**  
Files: `frontend/index.html` lines ~542–570  
- Replace "XTTS v2 Arabic TTS — already included" with "Piper Arabic TTS — already included"  
- Remove any "Amazon" or domain-specific references from modal copy
- Update modal to reflect current architecture (Piper not XTTS)

**AR1-005: Review and fix `ARABIC_OFF_TOPIC_RESPONSE`**  
Files: `backend/assistify_rag_server.py` line 6202  
- Review hardcoded Arabic text for domain-specific references
- Ensure it's generic enough to be valid in any RAG deployment context

### Priority 2 — UX Quality

**AR1-006: Fix `xtts_arabic_ready` field in `/arabic/status`**  
Files: `backend/assistify_rag_server.py` line 32719  
- Rename to `piper_arabic_ready` and populate from Piper Arabic voice load status
- Or remove the field entirely if frontend doesn't use it for display logic
- Current state (always False) is misleading and should not remain

**AR1-007: Add Arabic STT degradation indicator to frontend**  
Files: `frontend/index.html`, `backend/assistify_rag_server.py`  
- In `/arabic/status` response: surface `multilingual_model_loaded` (already returned)
- In frontend: if `!multilingual_model_loaded` and language is 'ar', show a warning indicator on the Start button area: "Arabic voice unavailable — please download multilingual model"

**AR1-008: Add STT fallback logging guard (backend)**  
Files: `backend/assistify_rag_server.py` `auto_transcribe()`  
- When Arabic voice falls back to English model, send a WS event to frontend indicating STT degradation rather than silently transcribing garbage

### Priority 3 — Polish (Low urgency)

**AR1-009: Rename XTTS_ config constants to TTS_**  
Files: `backend/config_head.py`, `backend/assistify_rag_server.py`  
- `XTTS_SERVICE_URL` → `TTS_SERVICE_URL`  
- `XTTS_SPEAKER` → `TTS_SPEAKER`  
- `XTTS_SAMPLE_RATE` → `TTS_SAMPLE_RATE`  
- Low priority — working correctly, rename is cosmetic cleanup only

---

## G. What NOT to Touch (Yet)

The following are **verified working** and must not be modified in Phase AR-1:

| Component | Location | Reason |
|---|---|---|
| `_tts_arabic_response()` | line 28808 | Correctly chunks → Piper Arabic → PCM stream |
| `_search_with_query_expansion()` | RAG core | Language-agnostic; always receives English text for Arabic queries |
| `translate_with_llm()` | line 6505 | AR↔EN working; cache+fallback chain functional |
| `_translation_cache_get/set()` | line ~6240 | LRU cache working correctly |
| Arabic opener prefill pattern | line 31255 | Critical for Qwen Arabic output; do not remove |
| `_arabic_opener_pool` warmup | line 5722 | Pre-renders opener phrases when warmup enabled |
| Arabic LLM fallback (CJK/EN→AR) | line 31947 | Correctly handles Qwen language drift |
| `_sanitize_arabic_text()` | line 6364 | Required clean input for Piper Arabic TTS |
| `_preprocess_for_tts()` | line 6452 | Required for Piper-safe Arabic text |
| `auto_transcribe()` core STT logic | line 33989 | Only change: initial_prompt (AR1-003) |
| `_is_arabic_small_talk()` | line ~6200 | Working greeting detection |
| Binary PCM WS streaming protocol | multiple | Same protocol for EN+AR; do not change |
| Login server WS proxy | line 3542 | Binary forwarding + text rate limiting correct |
| Web Audio playback (frontend) | ~line 1300 | Working for both EN and AR audio |
| `_ws_write_locks[connection_id]` | global dict | Per-connection write lock prevents interleaving |
| Piper TTS microservice | `tts_service/piper_server.py` | Working; both EN+AR voices loaded |
| `arabic_tts_complete` WS event | frontend + backend | Correct cleanup protocol |

---

## H. Key Architecture Facts (Summary)

| Component | Technology | Port | Status |
|---|---|---|---|
| Frontend | Single HTML page | Served via 7001 | Working |
| Login/Proxy Server | FastAPI | 7001 | Working |
| RAG + STT + WS Server | FastAPI | 7000 | Working |
| TTS Microservice | Piper TTS (FastAPI) | 5002 | Working |
| LLM | Qwen2.5-7B via Ollama | 11434 | Working |
| English STT | faster-whisper tiny.en (via HF cache) | embedded | Working |
| Arabic STT | faster-whisper-small multilingual (via HF cache) | embedded | Loads at startup via HF cache |
| English Voice | `models/piper/en/voice.onnx` | embedded in Piper | Working |
| Arabic Voice | `models/piper/ar/voice.onnx` | embedded in Piper | **File exists — Working** |
| Variable `XTTS_SERVICE_URL` | = `http://127.0.0.1:5002` (Piper) | — | Name is legacy; points to Piper |

**Arabic STT model status**: `backend/Models/faster-whisper-small/` does NOT exist as a direct folder, but `backend/Models/models--Systran--faster-whisper-small/snapshots/<hash>/` **exists**. The `_find_ml_model_path()` function correctly finds and uses the HF cache path. Arabic STT should load at startup without requiring `/arabic/download`.

**Arabic TTS model status**: `models/piper/ar/voice.onnx` (~6MB) and `models/piper/ar/voice.onnx.json` both exist and are loaded by Piper at startup.

---

*End of Phase AR-0 Analysis Report — No code was modified during this phase.*
