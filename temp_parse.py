import json
text = open('test_blue_green_utf8.log', 'r', encoding='utf-16le').read()
lines = text.split('\n')
results = []
for line in lines:
    if any(k in line for k in ['Testing', 'Querying:', 'Found', 'Top match', 'NO MATCHES']):
        results.append(line.strip())
with open('results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2)
