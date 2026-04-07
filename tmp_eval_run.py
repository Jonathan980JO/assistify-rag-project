import json
import requests
import scripts.final_rag_eval as e

e.TIMEOUT = 120

session = requests.Session()
e.authenticate(session)
route = e.discover_live_answer_channel(session)

questions = []
questions += [("in_scope_definition_entity", q) for q in e.DEFINITION_ENTITY_QUESTIONS]
questions += [("in_scope_list_structure", q) for q in e.LIST_STRUCTURE_QUESTIONS]
questions += [("in_scope_overview_compare", q) for q in e.OVERVIEW_COMPARE_QUESTIONS]
questions += [("out_of_scope", q) for q in e.OUT_OF_SCOPE_QUESTIONS]

results = []
for index, (category, question) in enumerate(questions, 1):
    try:
        asked = e.ask_http(session, route, question) if route.kind == "http" else e.ask_ws(session, question)
        answer = asked.get("answer", "")
        status, reason, flags = e.classify(question, answer, category)
        results.append({
            "i": index,
            "category": category,
            "question": question,
            "status": status,
            "reason": reason,
            "latency_ms": asked.get("latency_ms"),
            "answer": answer,
        })
        print(f"{index:02d}. {status:<7} | {asked.get('latency_ms')}ms | {question}")
    except Exception as exc:
        results.append({
            "i": index,
            "category": category,
            "question": question,
            "status": "FAIL",
            "reason": f"exception:{exc}",
            "latency_ms": None,
            "answer": "",
        })
        print(f"{index:02d}. FAIL    | EXCEPTION | {question} | {exc}")

pass_count = sum(1 for row in results if row["status"] == "PASS")
partial_count = sum(1 for row in results if row["status"] == "PARTIAL")
fail_count = sum(1 for row in results if row["status"] == "FAIL")

triplet_questions = {
    "Who is Frederick Taylor?",
    "What is bureaucracy?",
    "Steps in planning process",
}
triplet = [row for row in results if row["question"] in triplet_questions]
fails = [
    {
        "question": row["question"],
        "reason": row["reason"],
        "category": row["category"],
    }
    for row in results
    if row["status"] == "FAIL"
]

summary = {
    "total": len(results),
    "pass": pass_count,
    "partial": partial_count,
    "fail": fail_count,
    "triplet": triplet,
    "fails": fails,
}

print("---SUMMARY---")
print(json.dumps(summary, ensure_ascii=False, indent=2))

with open("tests/final_rag_report_live_custom.json", "w", encoding="utf-8") as fh:
    json.dump({"route": {"kind": route.kind, "base": route.base, "path": route.path}, "results": results, "summary": summary}, fh, ensure_ascii=False, indent=2)
