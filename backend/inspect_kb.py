import argparse, sys, time, json, os
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--filename", required=True)
    p.add_argument("--top_k", type=int, default=10)
    p.add_argument("--ocr-if-scanned", action="store_true", default=False)
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

    try:
        from config import ASSETS_DIR as CFG_ASSETS
        ASSETS_DIR = Path(CFG_ASSETS)
    except Exception:
        # fallback to project assets folder
        ASSETS_DIR = repo_root / "archived_pdfs"
    ASSETS_DIR = Path(ASSETS_DIR)
    file_path = ASSETS_DIR / args.filename
    if not file_path.exists():
        print(f"ERROR: file not found in assets: {file_path}")
        return

    try:
        from PyPDF2 import PdfReader
    except Exception as e:
        print("Install PyPDF2 in your env: pip install PyPDF2")
        return

    reader = PdfReader(file_path)
    pages = []
    for i, p in enumerate(reader.pages, start=1):
        try:
            txt = p.extract_text() or ""
        except Exception:
            txt = ""
        pages.append(txt)

    def print_page(n):
        print("===== RAW PAGE START: %d =====" % n)
        print(pages[n-1])
        print("===== RAW PAGE END:   %d =====" % n)

    print("\n--- 1) Raw extracted text — PAGE 1 ---")
    print_page(1)
    print("\n--- 2) Raw extracted text — PAGE 2 ---")
    print_page(2)

    scanned_pages = [i+1 for i,t in enumerate(pages) if len((t or "").strip()) < 50]
    if scanned_pages:
        print("\n--- 7) OCR run required on pages (low text detected) ---")
        print(scanned_pages)
    else:
        print("\n--- 7) OCR run required: No (no pages below threshold) ---")

    ocr_texts = {}
    if args.ocr_if_scanned and scanned_pages:
        try:
            from pdf2image import convert_from_path
            import pytesseract
        except Exception:
            print("Install pdf2image and pytesseract to run OCR: pip install pdf2image pytesseract")
        else:
            print("\nRunning OCR on scanned pages...")
            images = convert_from_path(str(file_path), first_page=min(scanned_pages), last_page=max(scanned_pages))
            for sp in scanned_pages:
                idx = sp - min(scanned_pages)
                img = images[idx]
                tstart = time.time()
                txt = pytesseract.image_to_string(img)
                tend = time.time()
                ocr_texts[sp] = txt
                print(f"  OCR page {sp}: {len(txt)} chars, time {tend-tstart:.2f}s")

    # Access Chroma collection via backend.knowledge_base if available
    collection = None
    try:
        from backend.knowledge_base import get_or_create_collection
        collection = get_or_create_collection()
    except Exception:
        try:
            import chromadb
            client = chromadb.Client()
            cols = client.list_collections()
            collection = client.get_collection(cols[0].name) if cols else None
        except Exception:
            collection = None

    if not collection:
        print("\nWARNING: Could not access vector collection. Ensure chromadb is available and backend.knowledge_base exposes collection.")
        return

    try:
        # Chroma get() supports include: documents, embeddings, metadatas, distances, uris, data
        res = collection.get(include=["metadatas", "documents"], limit=args.top_k)
        metadatas = res.get("metadatas", [])
        documents = res.get("documents", [])
        ids = res.get("ids", []) if "ids" in res else []
    except Exception:
        res = collection.get(include=["metadatas", "documents"])
        metadatas = res.get("metadatas", [])[:args.top_k]
        documents = res.get("documents", [])[:args.top_k]
        ids = []

    print(f"\n--- 3) First {min(len(documents), args.top_k)} chunks from vector DB ---")
    for i, (doc, meta, _id) in enumerate(zip(documents, metadatas, ids), start=1):
        print(f"\n--- CHUNK #{i} ---")
        print("chunk_id:", _id)
        print("metadata:", json.dumps(meta, ensure_ascii=False))
        print("text:")
        print(doc)

    # 4) Detect headings
    import re
    heading_patterns = [
        r'^(Chapter\s+\d+[:.\s].*)$',
        r'^(CHAPTER\s+\d+[:.\s].*)$',
        r'^(Section\s+\d+(\.\d+)*[:.\s].*)$',
        r'^(Table of Contents)$',
        r'^(Abstract)$',
        r'^(References)$',
    ]
    headings = []
    for pi, txt in enumerate(pages, start=1):
        if not txt:
            continue
        for line in txt.splitlines():
            s = line.strip()
            if not s:
                continue
            for pat in heading_patterns:
                if re.match(pat, s, flags=re.IGNORECASE):
                    headings.append({"page": pi, "title": s})
    print("\n--- 4) Detected section/chapter titles (heuristic) ---")
    print(f"Found {len(headings)} candidate headings. (listing up to 200)")
    for h in headings[:200]:
        print(f"page {h['page']}: {h['title']}")

    # 5) Retrieval for query
    q = "Summarize Chapter 6 in 3 bullet points"
    top_k = args.top_k
    try:
        query_res = collection.query(query_texts=[q], n_results=top_k, include=["documents","metadatas","distances"]) 
        docs = query_res.get("documents", [[]])[0]
        metas = query_res.get("metadatas", [[]])[0]
        dists = query_res.get("distances", [[]])[0]
        print(f"\n--- 5) Top {len(docs)} retrieved chunks for query: {q} ---")
        for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), start=1):
            sim = 1.0 - dist if dist is not None else None
            print(f"\nRANK {i} | similarity: {sim}")
            print("metadata:", json.dumps(meta, ensure_ascii=False))
            print("text:", doc)
    except Exception as e:
        print("Could not run collection.query():", e)

    # 6) Chunking strategy inference
    sample_meta = metadatas[0] if metadatas else {}
    print("\n--- 6) Chunking strategy inference ---")
    if sample_meta and ("section" in sample_meta or "page" in sample_meta):
        print("Found metadata keys suggesting structure-aware chunking. Sample metadata keys:", list(sample_meta.keys()))
    else:
        print("No explicit 'section'/'page' metadata present in sample chunk metadata keys:", list(sample_meta.keys()))
    lens = [len(d.split()) for d in documents] if documents else []
    if lens:
        avg_words = sum(lens)/len(lens)
        print(f"Average chunk length (words) of first {len(lens)} chunks: {avg_words:.1f}")
    else:
        print("No chunk texts available to compute sizes.")

    # 8) metadata fields for first chunk
    if metadatas:
        print("\n--- 8) Exact metadata fields for chunk #1 ---")
        print(json.dumps(metadatas[0], ensure_ascii=False, indent=2))
    else:
        print("\nNo metadata found in collection.get() result.")

if __name__ == "__main__":
    main()
