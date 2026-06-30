# Assistify RAG System — Comprehensive Test Plan

*Generated: 2026-06-25. Based on ARCHITECTURE_DISCOVERY.md.*

> **Scope note:** This plan covers every identified data-access path, role boundary, and failure mode confirmed during code reading. Test cases are written as direct API/WS calls, not UI navigation, so they can be automated. Where the exact API shape was inferred rather than confirmed, that is noted.

---

## 1. Tenant Isolation Tests

The central isolation mechanism is collection-per-tenant in ChromaDB: `t{id}_support_docs_v3_latest` for non-default tenants; `support_docs_v3_latest` for tenant 1. These tests verify the boundaries hold under adversarial conditions.

---

### TI-01: RAG query for Tenant A cannot return Tenant B's documents

**Risk:** If collection scoping breaks, `search_documents()` could return chunks from a different business's knowledge base.

**Setup:**
- Tenant 1 has document "Product A Manual" indexed.
- Tenant 2 has document "Product B Manual" indexed.
- Admin of Tenant 2 is logged in (session cookie with `active_tenant_id=2`).

**Steps:**
1. Open WebSocket to `ws://localhost:7000/ws` with Tenant 2 admin session cookie.
2. Send control: `{"type": "control", "action": "set_active_tenant", "tenant_id": 2}`.
3. Send text: `{"text": "Tell me about Product A", "tenant_id": 2, ...}`.
4. Collect all `aiResponseChunk` and `aiResponseDone` messages.

**Expected:** Response says "Product A" details not found / not in knowledge base. Response does NOT contain any text from Tenant 1's "Product A Manual".

**Currently automatable:** Yes — pytest + asyncio websockets library. No additional infrastructure needed beyond test data setup.

---

### TI-02: Tenant A admin cannot upload to Tenant B's collection

**Risk:** `POST /upload_rag` resolves tenant from the session cookie. A crafted request could attempt to specify a different tenant.

**Setup:**
- Admin of Tenant 2 is authenticated.
- Tenant 1 has an existing collection.

**Steps:**
1. POST `/upload_rag` with Tenant 2 admin session cookie, upload a PDF.
2. Inspect ChromaDB directly: confirm new chunks appear only in `t2_support_docs_v3_latest`, not in `support_docs_v3_latest`.

**Expected:** Upload creates chunks exclusively in Tenant 2's collection. The `require_request_tenant(user)` call in `upload_rag` ignores any body parameter and reads from session only.

**Currently automatable:** Yes — pytest + httpx + direct ChromaDB inspection. Requires access to ChromaDB persistent path.

---

### TI-03: Tenant A admin cannot delete Tenant B's documents

**Risk:** `POST /rag/delete` accepts a `doc_prefix` parameter. If the tenant filtering in `delete_documents_by_source_identity()` fails, a Tenant 2 admin could delete chunks from Tenant 1's collection.

**Setup:**
- Tenant 1 has file "shared_name.pdf" indexed.
- Tenant 2 also has a file "shared_name.pdf" indexed.
- Tenant 2 admin authenticated.

**Steps:**
1. POST `/rag/delete?doc_prefix=shared_name.pdf` with Tenant 2 admin session cookie.
2. After response, inspect ChromaDB to count remaining chunks in both collections.

**Expected:** Chunks deleted only from Tenant 2's collection. Tenant 1's chunks for "shared_name.pdf" remain intact. `_collection_owned_by_tenant(c, 2)` must filter correctly.

**Currently automatable:** Yes — pytest + httpx + ChromaDB inspection.

---

### TI-04: Default tenant (1) cannot access non-default tenant collections via naming convention failure

**Risk:** The `_collection_owned_by_tenant(c, 1)` scan in `get_or_create_collection(tenant_id=None)` excludes collections with `t{n}_` prefix. If a Tenant 3 collection was mistakenly created without the `t3_` prefix, it would be served to Tenant 1 queries.

**Setup:**
- Manually create a ChromaDB collection named `support_docs_v3_extra` (no `t{n}_` prefix) and insert Tenant 3's private documents into it.
- Tenant 1 admin authenticated.

**Steps:**
1. Send a query from Tenant 1 for content unique to the `support_docs_v3_extra` collection.
2. Observe response.

**Expected:** Response does NOT contain Tenant 3's private content. `_collection_owned_by_tenant(c, 1)` must exclude `support_docs_v3_extra` (it would actually include it because it has no `t{n}_` prefix — this is a known risk from Section 4.3 Risk 1 of ARCHITECTURE_DISCOVERY.md).

**Currently automatable:** Yes — this test may reveal a real isolation bug. Requires direct ChromaDB manipulation.

---

### TI-05: Tenant A customer cannot switch active_tenant to Tenant B via API

**Risk:** `POST /api/session/active-tenant` on login server allows a customer to switch their active business. A customer with only `approved` membership in Tenant 1 should not be able to switch to Tenant 2.

**Setup:**
- Customer "alice" has approved membership in Tenant 1 only.
- Alice is authenticated (session cookie).

**Steps:**
1. POST `/api/session/active-tenant` with body `{"active_tenant_id": 2}`.
2. If response is 200, try to send a chat message with `tenant_id=2`.
3. Check that `assert_chat_tenant_allowed()` in `tenant_access.py` blocks the query.

**Expected:** Either `POST /api/session/active-tenant` returns 403, or subsequent chat query with `tenant_id=2` returns 403 when `ENFORCE_CHAT_TENANT_MEMBERSHIP=true`.

**Currently automatable:** Yes — pytest + httpx. Requires `ENFORCE_CHAT_TENANT_MEMBERSHIP=true` in test environment.

---

### TI-06: Guest user cannot access authenticated tenant data

**Risk:** Guest sessions (identified by `X-Guest-Owner: guest_{32-hex}`) share the default tenant's knowledge base. A guest should not be able to query non-default tenant knowledge bases.

**Setup:**
- Tenant 2 has private documents indexed.
- No authenticated session (guest cookie only).

**Steps:**
1. Open WS to `/ws` with `X-Guest-Owner: guest_{valid_id}` header.
2. Send `{"text": "...", "tenant_id": 2, ...}`.
3. Observe whether `assert_chat_tenant_allowed()` checks guest access to Tenant 2.

**Expected:** Either 403 on WebSocket, or the guest is silently served only the default tenant's knowledge base. Tenant 2's private documents must not appear in the response.

**Currently automatable:** Yes — pytest + websockets library.

---

### TI-07: Conversation history does not leak across tenants

**Risk:** The `ui_conversations` table is filtered by `(tenant_id, username)`. If a customer chats with Tenant 1 and then Tenant 2, messages must be scoped to the correct tenant.

**Setup:**
- Customer "bob" has approved access to both Tenant 1 and Tenant 2.
- Bob sends message M1 to Tenant 1, then switches to Tenant 2 and sends message M2.

**Steps:**
1. Create conversation C1 with `active_tenant_id=1`, append message M1.
2. Create conversation C2 with `active_tenant_id=2`, append message M2.
3. GET `/conversations/{C1}` with Bob's session.
4. GET `/conversations/{C2}` with Bob's session.

**Expected:** C1 messages contain only M1 (tenant_id=1). C2 messages contain only M2 (tenant_id=2). No cross-tenant message bleed.

**Currently automatable:** Yes — pytest + httpx.

---

### TI-08: Analytics API does not expose Tenant B data to Tenant A admin

**Risk:** `GET /analytics/summary` and `GET /analytics/comprehensive` must be scoped to the calling admin's tenant.

**Setup:**
- Tenant 1 admin authenticated.
- Tenant 2 has usage records in `analytics.db`.

**Steps:**
1. GET `/analytics/summary` with Tenant 1 admin session.
2. Inspect response `usage_stats` data.

**Expected:** Response contains only Tenant 1 usage records. `analytics_scope_tenant(user)` returns Tenant 1 ID for non-superadmin, not None.

**Currently automatable:** Yes — pytest + httpx + SQLite inspection.

---

### TI-09: KB events WebSocket does not broadcast Tenant B events to Tenant A admin

**Risk:** If the broadcast path for `_kb_event_subscribers` does not filter by the stored `sub_tenant_id`, all admin subscribers would see all tenants' KB mutations.

**Setup:**
- Tenant 1 admin connected to `ws://localhost:7000/ws/kb-events`.
- Tenant 2 admin uploads a document (triggering a KB event).

**Steps:**
1. Open `ws/kb-events` as Tenant 1 admin, listen for messages.
2. Trigger a KB upload from Tenant 2 admin in a separate HTTP call.
3. Observe whether Tenant 1 admin's WS receives a `kb_updated` event.

**Expected:** Tenant 1 admin does NOT receive events from Tenant 2's KB mutations.

**Currently automatable:** Yes — requires two concurrent WebSocket connections in test.

---

## 2. RAG Correctness Tests

### RAG-01: Retrieved chunks come only from the active tenant's collection

**Setup:** Tenant 1 has "Document Foo" with phrase "UNIQUETOKEN_A". Tenant 2 has "Document Bar" with phrase "UNIQUETOKEN_B". Authenticated as Tenant 2 admin.

**Steps:**
1. Query: "What is UNIQUETOKEN_A?" with `tenant_id=2`.
2. Inspect `aiResponseDone.fullText`.

**Expected:** Response says "not found in help materials". Does NOT contain "UNIQUETOKEN_A" text from Tenant 1's document.

**Currently automatable:** Yes.

---

### RAG-02: Answer is grounded in retrieved context, not hallucinated

**Setup:** Tenant 1 has a document containing "Refund policy: 30 days." No other document mentions refunds.

**Steps:**
1. Query: "What is the refund policy?"
2. Capture `aiResponseDone.fullText`.

**Expected:** Response mentions "30 days" — directly from the context. Response does not invent a different number (e.g. "60 days").

**Currently automatable:** Yes, but requires manual verification or an LLM-as-judge step.

---

### RAG-03: No-match behavior when no relevant chunks exist

**Setup:** Tenant 1 has only a "Refund Policy" document. Query is completely unrelated.

**Steps:**
1. Query: "What is the capital of France?"

**Expected:** Response is the warm no-match string (`CS_NO_MATCH_RESPONSE_EN`) or equivalent, not a hallucinated answer. Response does NOT say "Paris".

**Currently automatable:** Yes — check that response contains the known no-match phrase or pattern.

---

### RAG-04: Distance threshold correctly rejects low-relevance chunks

**Setup:** Tenant 1 KB has only a document about "bicycle maintenance".

**Steps:**
1. Query: "What are quantum computing applications?" (clearly unrelated).
2. Inspect whether Ollama is even called (check `aiResponseChunk` events vs. direct no-match).

**Expected:** Either (a) no `aiResponseChunk` events (direct no-match return) or (b) LLM is called but uses empty context and returns a no-match. The bicycle maintenance text must not appear in the response.

**Currently automatable:** Yes.

---

### RAG-05: Duplicate / re-uploaded document does not create duplicate chunks

**Setup:** Tenant 1 has "Policy.pdf" already indexed with N chunks.

**Steps:**
1. Re-upload the same "Policy.pdf".
2. Wait for indexing to complete (poll `/kb_status`).
3. Count total chunks in collection.

**Expected:** Chunk count is the same N (not 2N). The deduplication logic (delete before re-index) must work correctly.

**Currently automatable:** Yes — ChromaDB `collection.count()` before and after.

---

### RAG-06: Delete document removes all associated chunks

**Setup:** Tenant 1 has "Policy.pdf" indexed with N chunks.

**Steps:**
1. POST `/rag/delete?doc_prefix=Policy.pdf` (or the stored filename).
2. Query the collection for any remaining chunks with `source_doc_id` matching the deleted file.

**Expected:** Zero chunks remain for the deleted document. `delete_documents_by_source_identity()` must catch all alias keys.

**Currently automatable:** Yes.

---

### RAG-07: Conflicting information in two documents produces a grounded answer

**Setup:** Tenant 1 has Doc A: "Refund window: 30 days" and Doc B: "Refund window: 60 days".

**Steps:**
1. Query: "How long is the refund window?"

**Expected:** Response presents both values from context without fabricating a third value. May include a note that documents differ.

**Currently automatable:** Partially — requires manual/LLM-judge check for hallucination.

---

## 3. Ingestion Pipeline Tests

### ING-01: Malformed / corrupt PDF returns an error, not a server crash

**Setup:** Create a file named "corrupt.pdf" containing random bytes (not a valid PDF).

**Steps:**
1. POST `/upload_rag` with the corrupt file as Tenant 1 admin.
2. Poll `/kb_status` until state is not "uploading".
3. Observe final `stage` in kb_status.

**Expected:** HTTP 200 with `"status": "processing"` from the upload endpoint (async). Background task fails gracefully, logs an error, sets `_kb_pipeline_state` to an error state. No HTTP 500 from the upload endpoint itself. No server crash.

**Currently automatable:** Yes.

---

### ING-02: Very large PDF (>10MB) uploads successfully

**Setup:** A synthetic PDF file of ~15MB.

**Steps:**
1. POST `/upload_rag` with the large PDF.
2. Poll `/kb_status` with 60-second timeout.
3. Check chunk count after indexing completes.

**Expected:** Upload accepted (HTTP 200 immediately). Background indexing completes within timeout. Warning logged but no failure. `kb_status.stage == "complete"`.

**Currently automatable:** Yes — requires generating a large test PDF.

---

### ING-03: Scanned (image-only) PDF with OCR disabled returns graceful fallback

**Setup:** A PDF containing only scanned images, no extractable text. `pytesseract` not installed in test environment.

**Steps:**
1. POST `/upload_rag` with the image-only PDF.
2. Poll `/kb_status`.
3. Query for content from the PDF.

**Expected:** Either (a) indexing produces 0 chunks and `kb_status` reports this clearly, or (b) OCR runs and extracts text. No server crash. Query returns no-match response.

**Currently automatable:** Yes — requires a test image-PDF.

---

### ING-04: Unsupported file type rejected at upload time

**Steps:**
1. POST `/upload_rag` with a `.docx` file.

**Expected:** Response `{"message": "Unsupported file type. Use PDF or TXT."}` immediately (confirmed in code line 42739-42740). No background task created.

**Currently automatable:** Yes.

---

### ING-05: TXT file ingested correctly

**Steps:**
1. POST `/upload_rag` with a small `.txt` file containing known phrases.
2. Query for a phrase from the file.

**Expected:** Query returns the phrase grounded in the context. TXT chunking path (short-document mode) works correctly.

**Currently automatable:** Yes.

---

### ING-06: Re-indexing via `/rag/reindex-all` preserves only current files on disk

**Setup:** Two files on disk, "File1.pdf" and "File2.pdf", both indexed. Manually delete "File2.pdf" from disk.

**Steps:**
1. POST `/rag/reindex-all`.
2. Poll `/kb_status`.
3. GET `/rag/files`.

**Expected:** After reindex, only "File1.pdf" appears in the file list. Chunks for "File2.pdf" are gone.

**Currently automatable:** Yes — requires filesystem access.

---

### ING-07: Concurrent uploads from the same tenant do not corrupt the collection

**Steps:**
1. As Tenant 1 admin, simultaneously POST `/upload_rag` for "File1.pdf" and "File2.pdf" (two concurrent requests).
2. Wait for both background tasks to complete.
3. Count chunks for each file.

**Expected:** Both files are indexed with correct chunk counts. No duplicate chunks, no missing chunks. Collection is internally consistent.

**Currently automatable:** Yes — pytest asyncio concurrent tasks.

---

## 4. Auth / Role Matrix Tests

The following endpoints require specific roles. Each row is a separate test asserting the correct HTTP status code is returned.

### AUTH-01 through AUTH-N: Role × Endpoint Matrix

| Test ID | Endpoint | Caller Role | Expected Status | Risk |
|---|---|---|---|---|
| AUTH-01 | `POST /upload_rag` | `customer` | 403 | Customer uploading docs to a business's KB |
| AUTH-02 | `POST /upload_rag` | `employee` | 403 | Employee uploading docs (only admin/master_admin allowed) |
| AUTH-03 | `POST /upload_rag` | `admin` | 200 | Positive case |
| AUTH-04 | `POST /upload_rag` | unauthenticated | 401 | |
| AUTH-05 | `POST /rag/delete` | `customer` | 403 | |
| AUTH-06 | `POST /rag/delete` | `employee` | 403 | |
| AUTH-07 | `POST /rag/delete` | `admin` | 200 | Positive case |
| AUTH-08 | `GET /admin/analytics` | `customer` | 403 | |
| AUTH-09 | `GET /admin/analytics` | `employee` | 403 | |
| AUTH-10 | `GET /admin/analytics` | `admin` | 200 | Positive case |
| AUTH-11 | `GET /api/kb-stats` | `customer` | 403 | |
| AUTH-12 | `WS /ws/kb-events` | `customer` | WS close 4003 | |
| AUTH-13 | `WS /ws/kb-events` | `admin` | 200 (connected) | Positive case |
| AUTH-14 | `GET /api/tenants` (login server) | `admin` | 403 | Admin should not see all tenants |
| AUTH-15 | `GET /api/tenants` (login server) | `superadmin` | 200 | Positive case |
| AUTH-16 | `POST /api/tenants/create` | `master_admin` | 403 | Only superadmin creates tenants |
| AUTH-17 | `POST /api/tenants/create` | `superadmin` | 200 | Positive case |
| AUTH-18 | `POST /api/users/{id}/change-role` assigning `superadmin` | `master_admin` | 403 | Role escalation prevention |
| AUTH-19 | `POST /api/users/{id}/change-role` assigning `admin` to user in different tenant | `admin` | 403 | Cross-tenant management |
| AUTH-20 | `GET /conversations` (RAG server) | unauthenticated, no guest header | 401 | |
| AUTH-21 | `GET /conversations` (RAG server) | unauthenticated with valid `X-Guest-Owner` | 200 | Guest access to conversations |
| AUTH-22 | `POST /query` | unauthenticated | 401 | |
| AUTH-23 | `GET /internal/preflight` | unauthenticated | 200 | This endpoint has no auth — confirm whether that is intentional |
| AUTH-24 | `POST /upload_rag` | `superadmin` | 403 | Superadmin is not in `require_tenant_staff()` — confirm this is intentional |

**All test cases:** Currently automatable — Yes. Tooling: pytest + httpx with session cookie fixtures per role.

---

### AUTH-25: Session cookie cannot be forged / replayed

**Steps:**
1. Copy a valid admin session cookie.
2. Modify the payload (e.g. change `role` to `superadmin`).
3. Send a request that requires superadmin.

**Expected:** 401 or 403. `itsdangerous.URLSafeSerializer` signature verification fails on tampered cookies.

**Currently automatable:** Yes.

---

### AUTH-26: Expired session is rejected

**Steps:**
1. Obtain a valid session token.
2. Manually set `created_at` to `now - 90000` (>24h ago) in a locally re-serialized cookie.
3. Send any authenticated request.

**Expected:** 401 "Session expired (absolute timeout)". **Note:** This requires knowing the `SESSION_SECRET` to re-sign, so it is better tested as a unit test of `validate_session()` directly.

**Currently automatable:** Yes — unit test of `validate_session()` in `login_server.py`.

---

### AUTH-27: Account lockout after 5 failed logins

**Steps:**
1. POST `/login` with correct username and wrong password, 5 times.
2. POST `/login` with correct credentials on the 6th attempt.

**Expected:** 6th attempt returns 429 or 403 with lockout message. Lockout duration: 15 minutes.

**Currently automatable:** Yes — pytest + httpx. Requires resetting the lockout state between test runs.

---

## 5. WebSocket Tests

### WS-01: WebSocket requires valid session or guest header

**Steps:**
1. Open WebSocket `/ws` with no cookies and no `X-Guest-Owner` header.
2. Send a text message.

**Expected:** Connection is accepted (WS protocol), but the message is either rejected with `{"type": "error"}` or the server continues as anonymous and falls back to default tenant. When `ALLOW_PUBLIC_GUEST_CHAT=false`, the connection should be rejected or messages should return 401.

**Currently automatable:** Yes — websockets library.

---

### WS-02: Reconnect with exponential backoff works correctly

**Steps:**
1. Connect WS, verify `connected=true`.
2. Forcibly close the server-side connection.
3. Observe client reconnect behavior (log timing of reconnect attempts).

**Expected:** Client reconnects with delays following `min(1000ms * attempt, 5000ms)` pattern. After 12 failed attempts, `connectionError` state is set to "Disconnected. Please refresh."

**Currently automatable:** Yes — frontend unit test or integration test with a mock WS server.

---

### WS-03: Message ordering is preserved under concurrent text messages

**Steps:**
1. Connect WS.
2. Send messages M1, M2, M3 in rapid succession without waiting for responses.
3. Collect all `aiResponseDone` events.

**Expected:** Responses arrive in order M1→R1, M2→R2, M3→R3. No response interleaving. **Note:** The current architecture has no explicit message sequencing — each message triggers an `asyncio` task. Under load, responses could arrive out of order. This test may reveal a design gap.

**Currently automatable:** Yes — requires timing measurements.

---

### WS-04: `interrupt` control message cancels active TTS

**Steps:**
1. Connect WS, send a query that produces a long TTS response.
2. While receiving binary audio frames, send `{"type": "control", "action": "interrupt"}`.
3. Observe: binary frames stop arriving; next `ttsAudioEnd` or `ttsFallback` message arrives.

**Expected:** TTS stream cancelled. Client transitions back to listening state.

**Currently automatable:** Yes — requires TTS to be enabled and working.

---

### WS-05: Binary audio sent by unauthenticated client is discarded, not processed

**Steps:**
1. Connect WS with a guest header or no auth.
2. Send raw PCM16 binary frames.
3. Observe whether Whisper is invoked.

**Expected:** For guest connections, Whisper should still run (guests can use voice if `ALLOW_PUBLIC_GUEST_CHAT=true`). For completely anonymous connections (no guest header, no session), binary frames should be silently discarded or an error returned.

**Currently automatable:** Yes.

---

### WS-06: Two sessions from different tenants cannot share a WebSocket

**Setup:** Two different tenant admins connect to `/ws` simultaneously.

**Steps:**
1. Tenant 1 admin connects to WS (conn1), sets `active_tenant=1`.
2. Tenant 2 admin connects to WS (conn2), sets `active_tenant=2`.
3. Tenant 1 admin sends a query; observe that conn2 receives no response for it.

**Expected:** Each connection is completely isolated. `session_tenant_ref` is per-connection (confirmed as a local list, not a global variable).

**Currently automatable:** Yes — two concurrent WebSocket clients in a test.

---

### WS-07: WebSocket rate limiter rejects messages above threshold

**Steps:**
1. Connect WS as authenticated user.
2. Send 21 messages within 60 seconds.

**Expected:** 21st message (or subsequent) receives `{"type": "error"}` or is silently dropped per the `WebSocketRateLimiter` (20 messages/60s). **Note:** Rate limiter is in `login_server.py` for proxied WS; unclear if it applies to direct `/ws` on the RAG server.

**Currently automatable:** Yes.

---

## 6. Voice / Whisper Tests

### VOICE-01: Valid audio produces correct transcript

**Setup:** A pre-recorded 16 kHz PCM16 WAV file containing the phrase "What is the refund policy?".

**Steps:**
1. Connect WS.
2. Stream PCM16 bytes from the WAV file as binary frames.
3. Send `{"type": "control", "action": "stop_recording"}`.
4. Observe `{"type": "transcript", "final": true}`.

**Expected:** Transcript text closely matches the spoken phrase. `final=true` triggers the RAG pipeline.

**Currently automatable:** Yes — requires a pre-recorded audio fixture.

---

### VOICE-02: Silence produces no transcript

**Setup:** PCM16 data composed of all zeros (silence).

**Steps:**
1. Stream silence frames.
2. After 12 silence chunks (silence_chunks_needed), observe server behavior.

**Expected:** Server triggers transcription after silence timeout. Whisper returns empty or near-empty transcript. No `aiResponseChunk` events (or a very short conversational response). No server error.

**Currently automatable:** Yes.

---

### VOICE-03: Audio in wrong format (e.g. 44.1 kHz stereo) is handled gracefully

**Steps:**
1. Stream 44.1 kHz stereo PCM16 bytes directly without resampling.

**Expected:** Whisper may produce garbage transcript or empty result. No server crash. Client receives either a low-quality transcript or `stt_failed`.

**Currently automatable:** Yes — requires creating the wrong-format audio data.

---

### VOICE-04: STT watchdog fires on Whisper timeout

**Setup:** Whisper is artificially delayed (mock slow transcription or disable it entirely with `ASSISTIFY_DISABLE_WHISPER=true`).

**Steps:**
1. Send audio and trigger transcription.
2. Wait 3.5 seconds (beyond the 3-second client-side `STT_PENDING_WATCHDOG_MS`).
3. Observe client-side state.

**Expected:** Client transitions to `"error"` state with "Didn't catch that — try again" message. Retry button appears.

**Currently automatable:** Yes — frontend unit test. Backend simulation of slow Whisper requires a mock.

---

### VOICE-05: Barge-in interrupts TTS correctly

**Steps:**
1. Send a long text query, wait for TTS to start streaming binary audio.
2. While audio is playing, speak loudly (inject high-energy audio buffer — energy > 0.09).
3. Observe client state transition.

**Expected:** Client detects barge-in (`computeEnergy(buffer) > 0.09`), calls `bargeIn()`, sends `interrupt` + `clear_audio_buffer` controls. TTS stops. State transitions to `interrupted` then `listening`.

**Currently automatable:** Frontend unit test — inject mock energy data into `captureBufferRef`.

---

### VOICE-06: Voice semaphore blocks concurrent voice processing

**Setup:** Two simultaneous voice WS connections from the same (or different) users.

**Steps:**
1. Both connections send audio simultaneously.
2. Observe whether both trigger Whisper concurrently or one is queued.

**Expected:** Voice semaphore (limit 1 per session based on `voice_semaphore`) blocks the second request. Second client receives `{"type": "system_busy", "message": "..."}`. No two Whisper runs execute concurrently per session.

**Currently automatable:** Yes — two concurrent WS clients.

---

## 7. Admin Provisioning Tests

### PROV-01: New tenant creation end-to-end

**Steps:**
1. POST `/api/tenants/create {"name": "Acme Corp", "slug": "acme"}` as superadmin.
2. Verify tenant appears in `GET /api/tenants`.
3. Assign an admin user via `POST /api/tenants/{id}/managers`.
4. Log in as that admin user; upload a document.
5. Verify document appears in `t{id}_support_docs_v3_latest` ChromaDB collection.
6. Query the new tenant's chat endpoint.

**Expected:** Each step succeeds. No data bleeds to other tenants.

**Currently automatable:** Yes — pytest + httpx end-to-end test. Requires a test user to be assignable as manager.

---

### PROV-02: Deactivated tenant cannot be chatted with

**Setup:** Tenant 2 exists and is active. Customer "alice" has approved membership.

**Steps:**
1. POST `/api/tenants/2/deactivate` as superadmin.
2. Alice tries to send a chat message with `tenant_id=2`.

**Expected:** `assert_chat_tenant_allowed()` returns 403 "Tenant is not active". Query does not reach Ollama.

**Currently automatable:** Yes.

---

### PROV-03: Reactivated tenant works correctly after reactivation

**Steps:**
1. Deactivate Tenant 2 (from PROV-02).
2. POST `/api/tenants/2/activate` as superadmin.
3. Alice retries the chat message.

**Expected:** Chat succeeds. KB data is intact.

**Currently automatable:** Yes.

---

### PROV-04: Tenant deletion / offboarding — ChromaDB and assets cleanup

**Steps:**
1. Deactivate Tenant 2.
2. Manually delete or archive Tenant 2's data: ChromaDB collection `t2_*`, files in `assets/tenant_2/`, rows in analytics/conversations DB.
3. Verify no orphan data remains.

**Expected:** All Tenant 2 data is cleaned up. Tenant 1 is unaffected.

**Currently automatable:** Partial — requires writing a cleanup script and verifying results. No built-in tenant-delete endpoint was confirmed in code.

---

### PROV-05: Customer access request flow end-to-end

**Steps:**
1. Customer "charlie" is registered (role=customer, no memberships).
2. Charlie calls `POST /api/access-requests {"tenant_id": 2}`.
3. Tenant 2 admin reviews: `GET /api/access-requests`.
4. Admin approves: `POST /api/access-requests/{id}/approve`.
5. Charlie sends a chat message with `tenant_id=2`.

**Expected:** Step 2 creates a "pending" membership. Step 4 sets status to "approved". Step 5 succeeds when `ENFORCE_CHAT_TENANT_MEMBERSHIP=true`.

**Currently automatable:** Yes.

---

### PROV-06: Rejected access request prevents chat

**Steps:**
1. Customer "dave" requests access to Tenant 2.
2. Admin rejects: `POST /api/access-requests/{id}/reject`.
3. Dave sends a chat message with `tenant_id=2`.

**Expected:** Step 3 returns 403 "Tenant membership required".

**Currently automatable:** Yes.

---

### PROV-07: Revoked membership prevents further chat

**Steps:**
1. Customer "eve" has approved membership in Tenant 2.
2. Admin revokes: `POST /api/memberships/{id}/revoke`.
3. Eve sends a chat message with `tenant_id=2`.

**Expected:** 403 after revocation.

**Currently automatable:** Yes.

---

## 8. Load / Streaming Tests

### LOAD-01: Concurrent chat sessions from different users do not interfere

**Setup:** 10 simulated users, each with a session scoped to a different tenant or the same tenant.

**Steps:**
1. Open 10 concurrent WebSocket connections.
2. Each sends the same text query simultaneously.
3. Collect all `aiResponseDone` events and verify each connection received exactly one complete response.

**Expected:** All 10 responses are complete. No response is delivered to the wrong connection. No server error. `_TenantScope` ContextVar correctly isolates each async task.

**Currently automatable:** Yes — pytest + asyncio + websockets library. Requires a running Ollama instance or a mock LLM.

---

### LOAD-02: LLM streaming under load — no token interleaving

**Setup:** 5 concurrent WS connections from the same tenant.

**Steps:**
1. All 5 send chat queries simultaneously.
2. Collect tokens per connection (track `aiResponseChunk` sequences by connection ID).

**Expected:** Each connection's token stream is internally consistent and not intermixed with another connection's tokens. `session_tenant_ref` and WS write locks prevent interleaving.

**Currently automatable:** Yes.

---

### LOAD-03: Knowledge base upload does not block active chat sessions

**Steps:**
1. Open a WS connection from a customer and start a chat session.
2. Simultaneously, as admin, upload a large PDF (>5MB) to the same tenant's KB.
3. Continue sending chat messages during indexing.

**Expected:** Chat messages during indexing receive either the old KB answers or a "loading" message, but the WS connection does not hang or crash. The `_kb_pipeline_state` gate should respond to chat queries with a wait message if configured.

**Currently automatable:** Yes.

---

### LOAD-04: Repeated large PDF uploads do not cause ChromaDB corruption

**Steps:**
1. Upload a 5MB PDF to Tenant 1's KB 5 times in succession (waiting for each to complete).
2. After each upload, count chunks and verify consistency.

**Expected:** Chunk count remains stable (dedup logic removes old chunks before adding new ones). ChromaDB collection is internally consistent after each cycle.

**Currently automatable:** Yes — requires generating test PDFs.

---

### LOAD-05: System recovers after Ollama restart

**Steps:**
1. Send a chat query; observe `aiResponseDone`.
2. Stop the Ollama process.
3. Send another chat query; observe the error response.
4. Restart Ollama.
5. Send a third query.

**Expected:** Step 3 returns `{"type": "error", "message": "..."}` (no hang, timeout respects `LLM_REQUEST_TIMEOUT=30s`). Step 5 succeeds after Ollama restarts.

**Currently automatable:** Yes — requires controlling the Ollama process in the test environment.

---

## 9. Test Infrastructure Assessment

### Currently Available Infrastructure

| What | Status | Notes |
|---|---|---|
| pytest (17 existing test files) | Available | Unit tests for memberships, chunking, validators, Arabic TTS, TOON, OWASP |
| `tests/test_multitenant.py` | Available | Uses in-memory SQLite; good template for new tenant isolation unit tests |
| `backend/database.py` in-memory test support | Available | `sqlite3.connect(":memory:")` used in multitenant tests |
| ChromaDB in-memory mode | Available | `chromadb.Client()` (no persistence) for unit tests |
| httpx (async HTTP client) | Needs installing | Standard for FastAPI testing; not confirmed in requirements |
| websockets library | Needs installing | For WS integration tests |
| pytest-asyncio | Needs installing | Required for async test functions |

### Needs New Infrastructure

| What | Why Needed | Effort |
|---|---|---|
| **Integration test server fixture** | Both Login server (7001) and RAG server (7000) need to be running together for end-to-end tests. Currently no such fixture exists. | Medium — pytest fixture that starts both servers as subprocesses or uses `TestClient`. |
| **ChromaDB test isolation** | Each test run needs its own ChromaDB instance. Use `chromadb.Client()` (ephemeral) or a temp directory. | Low — add `@pytest.fixture` for ephemeral client. |
| **SQLite test databases** | `users.db`, `conversations.db`, `analytics.db` must be isolated per test. | Low — `tmp_path` fixture + patch `DB_PATH`. |
| **Mock Ollama** | Integration tests cannot depend on a live GPU-enabled Ollama service in CI. Need a mock that returns streaming JSON responses. | Medium — a simple `asyncio` HTTP server returning `{"message": {"content": "..."}, "done": false}` then `{"done": true}`. |
| **Test audio fixtures** | PCM16 WAV files at 16 kHz for voice tests. | Low — generate with `numpy` + `wave` stdlib. |
| **Role/session fixtures** | Factory for signed session cookies per role (`customer`, `admin`, `superadmin`, etc.). | Low — reuse `itsdangerous.URLSafeSerializer` with the test `SESSION_SECRET`. |
| **LLM-as-judge for RAG correctness** | Tests RAG-02 and RAG-07 require evaluating whether an answer is grounded. Needs a separate LLM call or human review. | High — requires either a test oracle or a secondary LLM evaluation step. |
| **Load test tooling** | LOAD-01 through LOAD-05 need `locust` or `k6` for concurrent load generation. | Medium — locust is easy to add but needs server up. |

### Test Prioritization Recommendation

**Priority 1 (implement first — highest risk):**
- TI-01 through TI-06 (tenant isolation) — directly tests the most critical security property.
- AUTH-01 through AUTH-24 (role matrix) — confirms all access control boundaries.

**Priority 2 (implement next — correctness):**
- RAG-01 through RAG-06 (retrieval correctness and grounding).
- PROV-01 through PROV-07 (provisioning and membership lifecycle).

**Priority 3 (implement when infrastructure ready):**
- ING-01 through ING-07 (edge-case ingest scenarios).
- WS-01 through WS-07 (WebSocket protocol correctness).
- VOICE-01 through VOICE-06 (voice pipeline).

**Priority 4 (load testing — last):**
- LOAD-01 through LOAD-05 — requires a full running environment with Ollama.

### Gaps That Require Manual Testing or Cannot Be Automated Today

- **TI-04** (naming convention collection leak) — may reveal a real isolation bug; requires ChromaDB manipulation and careful manual verification.
- **RAG-07** (conflicting documents) — requires human or LLM-judge evaluation of the answer quality.
- **PROV-04** (tenant offboarding) — no built-in deletion endpoint confirmed; requires manual cleanup + verification.
- **AUTH-23** (`/internal/preflight` auth) — need to confirm whether this endpoint intentionally has no auth or is a gap.
- **AUTH-24** (superadmin cannot upload) — need to confirm with the team whether this is intentional behavior or a bug.
- **TI-09** (KB events cross-tenant broadcast) — requires reading `broadcast` path in `assistify_rag_server.py` (not read during discovery) to determine if filtering is present; if absent this is a confirmed data leak.
