import sys

file_path = 'backend/assistify_rag_server.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    # 4384: father_phrase_hit
    if "father_phrase_hit = bool(" in line and "re.search" in line:
        skip = True
    elif skip and "ellis_action_hit = bool(" in line:
        pass
    elif skip and "and re.search(r\"\\b(?:developed" in line:
        pass
    elif skip and ")" in line.strip() and "person_name_for_meta" in lines[i+1]:
        skip = False
        continue
    
    if skip:
        continue
        
    if "father_phrase_hit" in line or "modern_psych_founder_hit" in line or "ancient_person_hit" in line or "abc_phrase_hit" in line or "ellis_action_hit" in line or "ellis_hit" in line:
        if "if " in line or "elif " in line:
            continue # skip the if blocks that use these
    
    if "father" in line and "re.search(r\"\\bfather\\b\"" in line:
        continue
    
    # In apply_heading_boost_for_family:
    if "penalties_for_definition = [" in line and "students will" in line:
        continue
    if "if any(p in hay for p in penalties_for_definition):" in line:
        continue
    if "boost -= 2.2" in line and lines[i-1].strip().startswith("if any(p in hay"):
        continue
    if "if re.search(r\"\\blesson\\s*\\d+\\b\", hay):" in line:
        continue
    if "boost += 0.65" in line and lines[i-1].strip().startswith("if re.search(r\"\\blesson"):
        continue

    new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Scrub completed!")
