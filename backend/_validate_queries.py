"""
Validation script: exercises _validate_query_ui_equivalent for 4 required queries.
Run from the project root: python -m backend._validate_queries
"""
import sys
import os
import json
import logging

# Make sure the backend package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING)

QUERIES = [
    "List the goals of psychology.",
    "What are the branches of psychology?",
    "List the schools of thought.",
    "List the stages of Freud's development.",
]

def main():
    # Import the validation helper — this will trigger module load
    print("=" * 70)
    print("LOADING MODULE (this may take a moment)...")
    print("=" * 70)
    try:
        from backend.assistify_rag_server import _validate_query_ui_equivalent
    except Exception as e:
        print(f"FATAL: Could not import validation helper: {e}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("RUNNING VALIDATION ON 4 QUERIES")
    print("=" * 70)

    results = []
    for i, q in enumerate(QUERIES, 1):
        print(f"\n{'-' * 60}")
        print(f"  QUERY {i}: {q}")
        print(f"{'-' * 60}")
        try:
            r = _validate_query_ui_equivalent(q)
            results.append(r)

            print(f"  Normalized query : {r.get('query_normalized', '')[:100]}")
            print(f"  Retrieval count  : {r.get('retrieval_count', 0)}")
            print(f"  Context summary  : {r.get('context_summary', '')[:200]}")

            shortcut = r.get("internal_shortcut_result", {})
            ui = r.get("ui_equivalent_result", {})

            print(f"  ---")
            print(f"  INTERNAL SHORTCUT:")
            print(f"    answer_type : {shortcut.get('answer_type')}")
            print(f"    source_mode : {shortcut.get('source_mode')}")
            print(f"    used_llm    : {shortcut.get('used_llm')}")
            sa = str(shortcut.get('answer', ''))
            if len(sa) > 300:
                sa = sa[:300] + "..."
            print(f"    answer      : {sa}")

            print(f"  UI-EQUIVALENT:")
            print(f"    answer_type : {ui.get('answer_type')}")
            print(f"    source_mode : {ui.get('source_mode')}")
            print(f"    used_llm    : {ui.get('used_llm')}")
            ua = str(ui.get('answer', ''))
            if len(ua) > 300:
                ua = ua[:300] + "..."
            print(f"    answer      : {ua}")

            print(f"  DIFFER: {r.get('results_differ', False)}")
            print(f"  TIMING: {r.get('timing_ms', 0):.0f}ms")

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append({"error": str(e)})

    print(f"\n{'=' * 70}")
    print("VALIDATION SUMMARY")
    print(f"{'=' * 70}")
    for i, (q, r) in enumerate(zip(QUERIES, results), 1):
        if "error" in r:
            status = "ERROR"
        else:
            ui_result = r.get("ui_equivalent_result", {})
            ui_ans = str(ui_result.get("answer", ""))
            used_llm = ui_result.get("used_llm", False)
            has_context = r.get("retrieval_count", 0) > 0
            if used_llm and has_context:
                # System has context and delegates to LLM — expected to succeed at runtime
                status = "LLM DELEGATED (context available, LLM will format)"
            elif "Not found" in ui_ans:
                status = "NOT FOUND (deterministic rejection)"
            else:
                item_count = len([ln for ln in ui_ans.splitlines() if ln.strip().startswith("- ")])
                status = f"ACCEPTED ({item_count} items)" if item_count > 0 else "ACCEPTED (prose)"
        print(f"  {i}. {q}")
        print(f"     -> {status}")

if __name__ == "__main__":
    main()
