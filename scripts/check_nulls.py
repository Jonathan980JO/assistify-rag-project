from pathlib import Path
p = Path('backend/config_head.py')
b = p.read_bytes()
print('len', len(b))
print('nul_count', b.count(b'\x00'))
print('preview', repr(b[:500]))
