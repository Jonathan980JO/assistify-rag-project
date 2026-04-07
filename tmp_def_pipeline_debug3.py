from backend import assistify_rag_server as srv

q = "what is scientific management"

docs = srv._search_fast_definition_minimal(q)
print("docs_len:", len(docs))
for i, d in enumerate(docs[:8], 1):
    m = d.get("metadata") or {}
    t = (d.get("page_content") or d.get("text") or "").replace("\n", " ")
    print(f"doc[{i}] page={m.get('page')} chunk={m.get('chunk_index')} len={len(t)} preview={t[:130]}")

ans_simple = srv._extract_simple_definition_sentence(q, docs)
print("simple_extractor:", ans_simple)

ctx = "\n\n".join([(d.get("page_content") or d.get("text") or "") for d in docs[:3]])
ans_general = srv._extract_definition_sentence(ctx, q, mode=srv._definition_mode_from_query(q))
print("general_extractor:", ans_general)
