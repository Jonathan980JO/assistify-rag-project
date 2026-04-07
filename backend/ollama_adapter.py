from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import os
import subprocess
import shlex
import asyncio

app = FastAPI(title="Ollama Adapter")


class ChatRequest(BaseModel):
    model: str
    messages: List[dict]
    max_tokens: int = 150
    temperature: float = 0.7


def build_prompt(messages: List[dict]) -> str:
    # Simple concatenation: system, then assistant/user turns
    parts = []
    for m in messages:
        role = m.get('role', 'user')
        content = m.get('content', '')
        parts.append(f"[{role}] {content}")
    return "\n".join(parts)


async def run_ollama_cmd(cmd_args, timeout=60):
    # Run subprocess asynchronously and capture stdout/stderr
    proc = await asyncio.create_subprocess_exec(
        *cmd_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise
    return proc.returncode, (stdout.decode(errors='ignore') if stdout else ''), (stderr.decode(errors='ignore') if stderr else '')


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    model = req.model or os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b')
    prompt = build_prompt(req.messages)

    # Try a few common ollama CLI invocations (compat shim across versions)
    attempts = [
        ["ollama", "generate", model, "--prompt", prompt],
        ["ollama", "run", model, "--prompt", prompt],
        ["ollama", "run", model]
    ]

    last_err = ""
    for args in attempts:
        try:
            code, out, err = await run_ollama_cmd(args, timeout=60)
            if code == 0 and out:
                # Ollama usually prints the generated text to stdout
                text = out.strip()
                return {"choices": [{"message": {"content": text}}]}
            last_err = err or out or f"exit={code}"
        except Exception as e:
            last_err = str(e)

    # If we get here, all attempts failed
    return {"error": "Failed to invoke Ollama CLI", "details": last_err}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
