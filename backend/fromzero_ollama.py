from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import os
import shlex

app = FastAPI(title="FromZero Ollama Adapter")


class ChatRequest(BaseModel):
    model: Optional[str]
    messages: List[dict]
    max_tokens: int = 150
    temperature: float = 0.7


def build_prompt(messages: List[dict]) -> str:
    parts = []
    for m in messages:
        role = m.get('role', 'user')
        content = m.get('content', '')
        parts.append(f"[{role}] {content}")
    return "\n".join(parts)


async def run_ollama_cmd(cmd_args, timeout=60):
    proc = await asyncio.create_subprocess_exec(
        *cmd_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise
    return proc.returncode, (stdout.decode(errors='ignore') if stdout else ''), (stderr.decode(errors='ignore') if stderr else '')


@app.post('/v1/chat/completions')
async def chat_completions(req: ChatRequest):
    model = req.model or os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b')
    prompt = build_prompt(req.messages)

    # Use Ollama CLI; prefer `ollama generate` then `ollama run` for compatibility
    attempts = [
        ["ollama", "generate", model, "--prompt", prompt, "--temperature", str(req.temperature)],
        ["ollama", "run", model, "--prompt", prompt, "--temperature", str(req.temperature)],
        ["ollama", "run", model]
    ]

    last_err = ""
    for args in attempts:
        try:
            code, out, err = await run_ollama_cmd(args, timeout=120)
            if code == 0 and out:
                text = out.strip()
                return {
                    "id": "chatcmpl-ollama",
                    "object": "chat.completion",
                    "created": int(__import__('time').time()),
                    "model": model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                }
            last_err = err or out or f"exit={code}"
        except Exception as e:
            last_err = str(e)

    return {"error": "Failed to invoke Ollama CLI", "details": last_err}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8100)
