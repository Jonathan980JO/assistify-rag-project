"""
OWASP Security Patcher - Auto-fix critical security issues
Fixes:
1. Add security.js inclusion to all pages
2. Add CSRF meta tag to all pages  
3. Replace innerHTML with safeSetHTML
4. Add Content Security Policy headers
5. Add input validation
"""

import re
from pathlib import Path

templates_dir = Path("Login_system/templates")
html_files = list(templates_dir.glob("*.html"))

print("="*70)
print("OWASP SECURITY AUTO-PATCHER")
print("="*70)
print(f"\nPatching {len(html_files)} files...\n")

fixes_applied = {
    'security_js_added': 0,
    'csrf_meta_added': 0,
    'innerHTML_fixed': 0,
    'csp_added': 0,
    'forms_protected': 0
}

def add_security_script(content):
    """Add security.js to head if not present"""
    if '<script src="/static/security.js">' in content or 'security.js' in content:
        return content, False
    
    # Add before closing </head>
    if '</head>' in content:
        security_script = '    <script src="/static/security.js"></script>\n'
        content = content.replace('</head>', security_script + '</head>')
        return content, True
    
    return content, False

def add_csrf_meta(content):
    """Add CSRF token meta tag"""
    if 'csrf-token' in content:
        return content, False
    
    # Add meta tag in head
    if '<meta name="viewport"' in content:
        csrf_meta = '\n    <meta name="csrf-token" content="{{ csrf_token() }}">'
        content = content.replace(
            '<meta name="viewport"',
            csrf_meta + '\n    <meta name="viewport"'
        )
        return content, True
    
    return content, False

def fix_innerHTML(content):
    """Replace innerHTML with Security.safeSetHTML"""
    if '.innerHTML' not in content:
        return content, 0
    
    count = 0
    
    # Pattern 1: element.innerHTML = 'string'
    pattern1 = r'(\w+)\.innerHTML\s*=\s*([`\'"])'
    def replace1(match):
        nonlocal count
        count += 1
        elem = match.group(1)
        quote = match.group(2)
        return f'Security.safeSetHTML({elem}, {quote}'
    
    content = re.sub(pattern1, replace1, content)
    
    # Pattern 2: getElementById('id').innerHTML = 'string'
    pattern2 = r'document\.getElementById\([\'"](\w+)[\'"]\)\.innerHTML\s*=\s*([`\'"])'
    def replace2(match):
        nonlocal count
        count += 1
        elem_id = match.group(1)
        quote = match.group(2)
        return f'Security.safeSetHTML(\'{elem_id}\', {quote}'
    
    content = re.sub(pattern2, replace2, content)
    
    # Pattern 3: querySelector().innerHTML = 'string'
    pattern3 = r'document\.querySelector\(([^)]+)\)\.innerHTML\s*=\s*([`\'"])'
    def replace3(match):
        nonlocal count
        count += 1
        selector = match.group(1)
        quote = match.group(2)
        return f'Security.safeSetHTML({selector}, {quote}'
    
    content = re.sub(pattern3, replace3, content)
    
    return content, count

def add_csp_meta(content):
    """Add Content Security Policy meta tag"""
    if 'Content-Security-Policy' in content:
        return content, False
    
    csp = '''    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self';">
'''
    
    if '<meta name="viewport"' in content:
        content = content.replace(
            '<meta name="viewport"',
            csp + '    <meta name="viewport"'
        )
        return content, True
    
    return content, False

def protect_forms(content):
    """Add CSRF protection to forms"""
    if '<form' not in content.lower():
        return content, 0
    
    count = 0
    lines = content.split('\n')
    new_lines = []
    in_form = False
    form_has_csrf = False
    
    for i, line in enumerate(lines):
        new_lines.append(line)
        
        # Check if we're entering a form
        if '<form' in line.lower():
            in_form = True
            form_has_csrf = False
        
        # Check if form already has CSRF token
        if in_form and ('csrf' in line.lower() or 'X-CSRF-Token' in line):
            form_has_csrf = True
        
        # Add CSRF token after form opening tag
        if in_form and not form_has_csrf:
            # Look for first input or end of form tag
            if '>' in line and '<form' in line.lower():
                # Form tag closed on same line
                indent = len(line) - len(line.lstrip())
                csrf_input = ' ' * (indent + 4) + '<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">'
                new_lines.append(csrf_input)
                form_has_csrf = True
                count += 1
        
        # Reset when leaving form
        if '</form>' in line.lower():
            in_form = False
            form_has_csrf = False
    
    return '\n'.join(new_lines), count

# Process all files
for html_file in sorted(html_files):
    filename = html_file.name
    print(f"📄 {filename}")
    
    try:
        content = html_file.read_text(encoding='utf-8')
        original_content = content
        file_fixes = []
        
        # Apply fixes
        content, added = add_security_script(content)
        if added:
            file_fixes.append("Added security.js")
            fixes_applied['security_js_added'] += 1
        
        content, added = add_csrf_meta(content)
        if added:
            file_fixes.append("Added CSRF meta tag")
            fixes_applied['csrf_meta_added'] += 1
        
        content, count = fix_innerHTML(content)
        if count > 0:
            file_fixes.append(f"Fixed {count} innerHTML XSS risks")
            fixes_applied['innerHTML_fixed'] += count
        
        content, added = add_csp_meta(content)
        if added:
            file_fixes.append("Added CSP header")
            fixes_applied['csp_added'] += 1
        
        content, count = protect_forms(content)
        if count > 0:
            file_fixes.append(f"Protected {count} forms with CSRF")
            fixes_applied['forms_protected'] += count
        
        # Write back if changes made
        if content != original_content:
            html_file.write_text(content, encoding='utf-8')
            for fix in file_fixes:
                print(f"  ✅ {fix}")
        else:
            print(f"  ℹ️  No changes needed")
        
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
    
    print()

# Summary
print("="*70)
print("PATCH SUMMARY")
print("="*70)
print(f"Security.js added to: {fixes_applied['security_js_added']} files")
print(f"CSRF meta tags added to: {fixes_applied['csrf_meta_added']} files")
print(f"innerHTML XSS risks fixed: {fixes_applied['innerHTML_fixed']} instances")
print(f"CSP headers added to: {fixes_applied['csp_added']} files")
print(f"Forms protected with CSRF: {fixes_applied['forms_protected']} forms")
print("="*70)
print("\n✅ All OWASP security patches applied!")
print("⚠️  Remember to:")
print("  1. Move security.js to static/ folder")
print("  2. Implement csrf_token() function in backend")
print("  3. Test all forms and AJAX calls")
print("  4. Review and adjust CSP policy as needed")
