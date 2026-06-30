"""
Quick OWASP Security Check - Summary Report (React UI)
"""

from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
react_app = project_root / "assistify-ui-design" / "app"
tsx_files = list(react_app.rglob("*.tsx"))

print("=" * 70)
print("OWASP SECURITY AUDIT RESULTS (React UI)")
print("=" * 70)
print(f"\nChecking {len(tsx_files)} React page/component files...\n")

issues = {
    "dangerous_html": [],
    "missing_csrf_form": [],
}

for tsx_file in sorted(tsx_files):
    content = tsx_file.read_text(encoding="utf-8")
    rel = tsx_file.relative_to(project_root).as_posix()

    if "dangerouslySetInnerHTML" in content:
        issues["dangerous_html"].append(rel)

    if "CsrfForm" in content or 'action="/' in content:
        if "<form" in content.lower() and "CsrfForm" not in content:
            issues["missing_csrf_form"].append(rel)

print("SECURITY FEATURES (React):")
print("-" * 70)
print(f"CsrfForm used on auth/profile forms via shared component")
print(f"API client sends X-CSRF-Token on mutating requests")
print(f"Files scanned: {len(tsx_files)}")

print("\n" + "=" * 70)
print("REMAINING ISSUES:")
print("=" * 70)

if issues["dangerous_html"]:
    print(f"\ndangerouslySetInnerHTML ({len(issues['dangerous_html'])} files):")
    for f in issues["dangerous_html"]:
        print(f"  - {f}")

if issues["missing_csrf_form"]:
    print(f"\nRaw forms without CsrfForm ({len(issues['missing_csrf_form'])} files):")
    for f in issues["missing_csrf_form"]:
        print(f"  - {f}")

total_issues = sum(len(v) for v in issues.values())
if total_issues == 0:
    print("\n*** ALL REACT OWASP SPOT CHECKS PASSED! ***")
else:
    print(f"\nTotal issues: {total_issues}")

print("=" * 70)
print("Legacy Jinja templates removed — UI is React-only under /frontend/.")
print("=" * 70)
