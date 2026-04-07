"""
OWASP Security Audit - Test All Pages for Top 10 Vulnerabilities
Tests for: XSS, Injection, Broken Auth, Security Misconfig, etc.
"""

import re
from pathlib import Path

print("="*70)
print("OWASP SECURITY AUDIT - ALL PAGES")
print("="*70)
print()

# Navigate from tests/ directory to project root
project_root = Path(__file__).parent.parent
templates_dir = project_root / "Login_system" / "templates"
html_files = list(templates_dir.glob("*.html"))

print(f"Found {len(html_files)} HTML templates to audit\n")

# OWASP Top 10 Checks
issues = []

def check_xss_protection(content, filename):
    """A01:2021 - Broken Access Control & A03:2021 - Injection"""
    problems = []
    
    # Check for innerHTML usage (XSS risk)
    if re.search(r'\.innerHTML\s*=', content):
        problems.append(f"  ⚠️  innerHTML usage (XSS risk) - use textContent instead")
    
    # Check for eval() usage
    if re.search(r'\beval\(', content):
        problems.append(f"  🚨 CRITICAL: eval() detected (Code Injection)")
    
    # Check for document.write
    if re.search(r'document\.write\(', content):
        problems.append(f"  ⚠️  document.write() (XSS risk)")
    
    # Check for unescaped user data in JavaScript
    if re.search(r'\$\{.*?\}', content) and 'DOMPurify' not in content:
        problems.append(f"  ℹ️  Template literals found - verify sanitization")
    
    return problems

def check_csrf_protection(content, filename):
    """A01:2021 - Broken Access Control"""
    problems = []
    
    # Check forms have CSRF tokens
    has_form = bool(re.search(r'<form', content, re.IGNORECASE))
    has_csrf = bool(re.search(r'csrf_token|x-csrf-token', content, re.IGNORECASE))
    
    if has_form and not has_csrf and filename not in ['Login.html', 'register.html']:
        problems.append(f"  🚨 CRITICAL: Form without CSRF protection")
    
    # Check fetch/axios includes CSRF token
    has_fetch = bool(re.search(r'fetch\(|axios\.|\.post\(|\.put\(|\.delete\(', content))
    has_csrf_header = bool(re.search(r'X-CSRF-Token|csrf_token', content))
    
    if has_fetch and not has_csrf_header:
        problems.append(f"  ⚠️  AJAX requests may lack CSRF tokens")
    
    return problems

def check_auth_security(content, filename):
    """A07:2021 - Identification and Authentication Failures"""
    problems = []
    
    # Check for hardcoded credentials
    if re.search(r'password\s*=\s*["\'][^"\']+["\']', content, re.IGNORECASE):
        problems.append(f"  🚨 CRITICAL: Possible hardcoded password")
    
    # Check for weak password requirements
    if 'password' in content.lower() and 'type="password"' in content:
        if not re.search(r'minlength|min-length', content, re.IGNORECASE):
            problems.append(f"  ⚠️  Password field without length validation")
    
    # Check for autocomplete on sensitive fields
    if re.search(r'type=["\']password["\']', content):
        if not re.search(r'autocomplete=["\']off["\']|autocomplete=["\']new-password["\']', content):
            problems.append(f"  ℹ️  Consider autocomplete control on password fields")
    
    return problems

def check_sensitive_data(content, filename):
    """A02:2021 - Cryptographic Failures"""
    problems = []
    
    # Check for sensitive data in client-side code
    if re.search(r'api[_-]?key|secret|token\s*=\s*["\'][^"\']+', content, re.IGNORECASE):
        problems.append(f"  🚨 CRITICAL: Possible API key/secret in client code")
    
    # Check for localStorage/sessionStorage with sensitive data
    if re.search(r'localStorage\.setItem.*(?:password|token|secret)', content, re.IGNORECASE):
        problems.append(f"  🚨 CRITICAL: Sensitive data in localStorage")
    
    return problems

def check_security_headers(content, filename):
    """A05:2021 - Security Misconfiguration"""
    problems = []
    
    # Check for Content Security Policy
    has_csp = bool(re.search(r'Content-Security-Policy', content, re.IGNORECASE))
    
    # Check for X-Frame-Options (Clickjacking protection)
    if '<iframe' in content.lower():
        problems.append(f"  ℹ️  iframe usage - ensure X-Frame-Options is set")
    
    return problems

def check_input_validation(content, filename):
    """A03:2021 - Injection"""
    problems = []
    
    # Check inputs have validation
    input_count = len(re.findall(r'<input', content, re.IGNORECASE))
    validated_count = len(re.findall(r'required|pattern|maxlength|minlength', content, re.IGNORECASE))
    
    if input_count > 0 and validated_count < input_count:
        problems.append(f"  ℹ️  {input_count} inputs, {validated_count} with HTML5 validation")
    
    # Check for SQL query construction in JavaScript (shouldn't happen but check)
    # Improved regex to avoid false positives from querySelector, classList, etc.
    if re.search(r'(SELECT\s+\*\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\s+', content, re.IGNORECASE):
        problems.append(f"  🚨 CRITICAL: SQL query in client code")
    
    return problems

def check_access_control(content, filename):
    """A01:2021 - Broken Access Control"""
    problems = []
    
    # Check for role-based content without server validation
    if re.search(r'role\s*==|role\s*===', content):
        problems.append(f"  ℹ️  Client-side role checks - ensure server validates too")
    
    # Check for admin-only pages
    if 'admin' in filename.lower():
        if not re.search(r'admin|require.*role|authorization', content, re.IGNORECASE):
            problems.append(f"  ⚠️  Admin page - verify server-side auth")
    
    return problems

def check_logging_monitoring(content, filename):
    """A09:2021 - Security Logging and Monitoring Failures"""
    problems = []
    
    # Check for console.log with sensitive data
    if re.search(r'console\.log.*(?:password|token|secret|key)', content, re.IGNORECASE):
        problems.append(f"  🚨 CRITICAL: Logging sensitive data to console")
    
    return problems

def check_ssrf_vulnerabilities(content, filename):
    """A10:2021 - Server-Side Request Forgery"""
    problems = []
    
    # Check for user-controlled URLs (but allow numeric IDs and encodeURIComponent usage)
    # Only flag if using string concatenation with user input without encoding
    if re.search(r'fetch\([^)]*\+.*[^)]*\)', content) and 'encodeURIComponent' not in content:
        problems.append(f"  ⚠️  Dynamic URL in fetch - validate/sanitize")
    
    return problems

# Audit all files
for html_file in sorted(html_files):
    filename = html_file.name
    print(f"📄 {filename}")
    
    try:
        content = html_file.read_text(encoding='utf-8')
        
        file_issues = []
        
        # Run all checks
        file_issues.extend(check_xss_protection(content, filename))
        file_issues.extend(check_csrf_protection(content, filename))
        file_issues.extend(check_auth_security(content, filename))
        file_issues.extend(check_sensitive_data(content, filename))
        file_issues.extend(check_security_headers(content, filename))
        file_issues.extend(check_input_validation(content, filename))
        file_issues.extend(check_access_control(content, filename))
        file_issues.extend(check_logging_monitoring(content, filename))
        file_issues.extend(check_ssrf_vulnerabilities(content, filename))
        
        if file_issues:
            for issue in file_issues:
                print(issue)
                issues.append((filename, issue))
        else:
            print(f"  ✅ No issues found")
        
        print()
        
    except Exception as e:
        print(f"  ❌ ERROR reading file: {e}\n")

# Summary
print("="*70)
print("SUMMARY")
print("="*70)

critical = [i for i in issues if '🚨 CRITICAL' in i[1]]
warnings = [i for i in issues if '⚠️' in i[1]]
info = [i for i in issues if 'ℹ️' in i[1]]

print(f"🚨 Critical Issues: {len(critical)}")
print(f"⚠️  Warnings: {len(warnings)}")
print(f"ℹ️  Info/Best Practices: {len(info)}")
print(f"\nTotal findings: {len(issues)} across {len(html_files)} files")

if critical:
    print("\n🚨 CRITICAL ISSUES THAT MUST BE FIXED:")
    for filename, issue in critical:
        print(f"  {filename}: {issue.strip()}")

print("\n" + "="*70)
print("Audit complete. Generating fixes...")
print("="*70)
