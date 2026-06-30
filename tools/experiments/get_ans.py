import sys
import os

with open('backend/_debug_guard.py', 'r', encoding='utf-8') as f:
    template = f.read()

import re
import subprocess

text = re.sub(r'^query\s*=.*', 'query = "List the goals of psychology."', template, flags=re.MULTILINE)
text = text.replace('print(f"  answer[:200]: {str(ans)[:200]}")', 'print(f"  answer[:2000]: {str(ans)[:2000]}")')

with open('backend/_debug_guard.tmp.py', 'w', encoding='utf-8') as f:
    f.write(text)

proc = subprocess.run(['python', 'backend/_debug_guard.tmp.py'], capture_output=True, text=True, encoding='utf-8')
for line in proc.stdout.split('\n'):
    if 'answer[:2000]' in line:
        print(line)
