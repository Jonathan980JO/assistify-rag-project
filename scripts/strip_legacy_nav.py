import re
from pathlib import Path

templates_dir = Path(__file__).resolve().parents[1] / "Login_system" / "templates"
files = [
    "main.html",
    "admin.html",
    "admin_users.html",
    "admin_knowledge.html",
    "admin_analytics.html",
    "admin_audit_logs.html",
    "employee.html",
    "employee_customers.html",
    "employee_tickets.html",
    "customer_tickets.html",
    "notifications.html",
    "profile.html",
    "superadmin.html",
    "admin_tickets.html",
    "admin_access_requests.html",
    "select_business.html",
    "change_username.html",
]

nav_script = re.compile(r'\s*<script src="/static/navigation\.js" defer></script>\s*')
open_close_nav = re.compile(
    r"\s*<script>\s*function openNav\(\)[\s\S]*?function closeNav\(\)[\s\S]*?</script>\s*",
    re.MULTILINE,
)
legacy_body = re.compile(
    r"\s*(?:<!-- Navigation Overlay -->|<!-- Side Navigation Menu -->|<!-- Header with hamburger button -->)?\s*"
    r'<div class="nav-overlay"[\s\S]*?</header>\s*',
    re.MULTILINE,
)
legacy_css = re.compile(
    r"\s*/\* (?:Header and Menu Styles|Navigation Menu Styles) \*/[\s\S]*?"
    r"(?:\.nav-link svg \{[\s\S]*?\}\s*)",
    re.MULTILINE,
)

for name in files:
    p = templates_dir / name
    if not p.exists():
        print("MISSING", name)
        continue
    text = p.read_text(encoding="utf-8")
    orig = text
    text = nav_script.sub('\n    {% include "_nav_shell.html" %}\n', text)
    text = open_close_nav.sub("\n", text)
    text = legacy_body.sub("\n", text)
    text = legacy_css.sub("\n", text)
    if text != orig:
        p.write_text(text, encoding="utf-8")
        print("UPDATED", name)
    else:
        print("UNCHANGED", name)
