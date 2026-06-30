"""Fix nested function in handler.py."""
from pathlib import Path

p = Path("backend/voice_audio/ws/handler.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
out = []
skip_inner_def = False
for ln in lines:
    if "async def rag_ws_endpoint(websocket: WebSocket)" in ln:
        continue  # drop inner duplicate def
    out.append(ln)

text = "".join(out)
# Remove one indent level from handler body (4 spaces) between rag_ws_handler and return
fixed = []
in_handler = False
for ln in text.splitlines(keepends=True):
    if ln.startswith("    async def rag_ws_handler"):
        in_handler = True
        fixed.append(ln)
        continue
    if in_handler and ln.strip() == "return rag_ws_handler":
        in_handler = False
        fixed.append(ln)
        continue
    if in_handler and ln.startswith("            "):
        fixed.append(ln[4:])
    else:
        fixed.append(ln)

p.write_text("".join(fixed), encoding="utf-8")
print("fixed handler indentation")
