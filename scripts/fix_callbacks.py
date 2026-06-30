"""Rebuild WS callback functions from git original with correct indentation."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "backend" / "assistify_rag_server.py"

original = subprocess.check_output(
    ["git", "show", "HEAD:backend/assistify_rag_server.py"],
    cwd=ROOT,
    text=True,
    encoding="utf-8",
)
lines = original.splitlines()


def strip_min_indent(block_lines: list[str]) -> list[str]:
    indents = [len(l) - len(l.lstrip()) for l in block_lines if l.strip()]
    min_indent = min(indents) if indents else 0
    out = []
    for l in block_lines:
        if l.strip():
            out.append(l[min_indent:])
        else:
            out.append("")
    return out


def to_function_body(block_lines: list[str]) -> str:
    stripped = strip_min_indent(block_lines)
    return "\n".join("    " + ln if ln else "" for ln in stripped)


voice_body = to_function_body(lines[43738:43841])
voice_body = voice_body.replace("requested_voice_lang", "lang")

text_stripped = strip_min_indent(lines[44087:44436])
if text_stripped and text_stripped[0].startswith('elif "text" in payload:'):
    text_stripped = text_stripped[1:]
text_body = "\n".join("    " + ln if ln else "" for ln in text_stripped)
text_body = text_body.replace("_cancel_active_ws_tts(", "cancel_active_ws_tts(")
text_body = text_body.replace("_activate_conversation(", "activate_conversation(")
text_body = text_body.replace("_conversation_ws(", "conversation_ws_factory(")
text_body = text_body.replace(
    "session_language = msg_lang  # update session preference",
    "session_language = msg_lang\n        session_language_ref[0] = msg_lang",
)

callbacks = f'''
# ========== VOICE WS CALLBACKS (Phase 1 — post-STT / typed text stay in RAG server) ==========

async def _process_voice_transcript_ws(
    *,
    ws,
    conn_id: str,
    full_text: str,
    lang: str,
    t_meta,
    user,
    active_conversation_id,
    _activate_conversation,
    _conversation_ws,
    segments_list=None,
):
{voice_body}

async def _process_ws_text_message(
    *,
    websocket,
    connection_id: str,
    payload: dict,
    user,
    session_language_ref: list,
    ws_tenant_id: int,
    ws_owner,
    activate_conversation,
    conversation_ws_factory,
):
    session_language = session_language_ref[0]
{text_body}

def _build_voice_ws_deps():
    return VoiceWebSocketDeps(
        resolve_request_tenant=resolve_request_tenant,
        coerce_owner=_coerce_owner,
        get_or_create_conversation=get_or_create_conversation,
        bind_conversation_memory=bind_conversation_memory,
        append_conversation_message=append_conversation_message,
        persist_runtime_memory=persist_runtime_memory,
        send_final_response=send_final_response,
        process_voice_transcript=_process_voice_transcript_ws,
        process_text_message=_process_ws_text_message,
        emit_perf_report=_emit_perf_report,
        session_cookie=SESSION_COOKIE,
        serializer=serializer,
        set_request_tenant_id=_request_tenant_id.set,
        get_memory_snapshot=_get_memory_snapshot,
        get_stable_memory_snapshot=_get_stable_memory_snapshot,
        conversation_history=conversation_history,
        conversation_timestamps=conversation_timestamps,
        active_ws_connections=_active_ws_connections,
    )

_rag_ws_handler = create_rag_ws_handler(_build_voice_ws_deps())


@app.websocket("/ws")
async def rag_ws_endpoint(websocket: WebSocket):  # pyright: ignore
    await _rag_ws_handler(websocket)


'''

text = SRC.read_text(encoding="utf-8")
start = text.find("# ========== VOICE WS CALLBACKS (Phase 1")
end = text.find("# ========== WEBSOCKET: Admin KB-events real-time feed ==========")
if start < 0 or end < 0:
    raise RuntimeError("callback markers not found")
text = text[:start] + callbacks + text[end:]
SRC.write_text(text, encoding="utf-8")
print("rebuilt callbacks")
