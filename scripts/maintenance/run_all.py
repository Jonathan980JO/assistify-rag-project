import sys
import os
import re
import subprocess

queries = [
    "What is psychology?",
    "List the goals of psychology.",
    "What are the branches of psychology?",
    "List the schools of thought.",
    "List the stages of Freud's development."
]

with open('backend/_debug_guard.py', 'r', encoding='utf-8') as f:
    template = f.read()

for i, q in enumerate(queries):
    # Match the entire line starting with query = 
    text = re.sub(r'^query\s*=.*', f'query = "{q}"', template, flags=re.MULTILINE)
    with open('backend/_debug_guard.tmp.py', 'w', encoding='utf-8') as f:
        f.write(text)
    
    print(f"\n--- Testing Query: {q} ---")
    proc = subprocess.run(['python', 'backend/_debug_guard.tmp.py'], capture_output=True, text=True, encoding='utf-8')
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)
