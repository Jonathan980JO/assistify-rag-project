import re

with open('assistify_rag_server.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if 'if globals().get("ASSISTIFY_DISABLE_TTS", False): break' in line:
        # Check previous line's indent
        prev_indent = len(lines[i-1]) - len(lines[i-1].lstrip())
        new_indent = prev_indent + 4
        new_lines.append(' ' * new_indent + 'if globals().get("ASSISTIFY_DISABLE_TTS", False): break\n')
    else:
        new_lines.append(line)

with open('assistify_rag_server.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
