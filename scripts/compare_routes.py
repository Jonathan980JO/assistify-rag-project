"""Compare route decorators between current code and audit snapshot."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTE_RE = re.compile(
    r"@(?:app|router)\.(get|post|put|patch|delete|websocket)\(\s*['\"]([^'\"]+)['\"]"
)


def extract(*paths: Path) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in ROUTE_RE.finditer(text):
            routes.add((m.group(1).upper(), m.group(2)))
    return routes


login_current = extract(
    ROOT / "Login_system" / "login_server.py",
    *list((ROOT / "Login_system" / "routers").glob("*.py")),
)
login_audit = extract(ROOT / "assistify_refactor_audit" / "login_server.py")
rag_current = extract(
    ROOT / "backend" / "assistify_rag_server.py",
    *list((ROOT / "backend" / "routers").glob("*.py")),
)
rag_audit = extract(ROOT / "assistify_refactor_audit" / "assistify_rag_server.py")

print("LOGIN decorator routes: current", len(login_current), "audit", len(login_audit))
print("RAG decorator routes: current", len(rag_current), "audit", len(rag_audit))
print("Login missing vs audit:", len(login_audit - login_current), sorted(login_audit - login_current)[:15])
print("Login extra vs audit:", len(login_current - login_audit), sorted(login_current - login_audit)[:15])
print("RAG missing vs audit:", len(rag_audit - rag_current), sorted(rag_audit - rag_current)[:15])
print("RAG extra vs audit:", len(rag_current - rag_audit), sorted(rag_current - rag_audit)[:15])
