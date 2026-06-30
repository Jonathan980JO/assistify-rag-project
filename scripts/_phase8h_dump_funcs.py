import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
mono = ROOT / "backend" / "assistify_rag_server.py"
low, high = int(sys.argv[1]), int(sys.argv[2])
out = sys.argv[3]
tree = ast.parse(mono.read_text(encoding="utf-8"))
names = [n.name for n in tree.body
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and low <= n.lineno <= high]
Path(out).write_text(json.dumps(names), encoding="utf-8")
print(f"dumped {len(names)} function names -> {out}")
