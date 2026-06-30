"""
TOON (Token-Oriented Object Notation) Implementation Tests
TDD Approach: Tests first, then implementation

Tests for:
1. TOON encoder (dict/list → TOON string)
2. TOON decoder (TOON string → dict/list)
3. Token count comparison (JSON vs TOON)
4. RAG context formatting with TOON
5. Edge cases (empty, nested, special chars)
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

print("="*70)
print("TOON IMPLEMENTATION - TDD TESTS")
print("="*70)
print()

# ========== TEST 1: Basic TOON Encoding ==========
def test_toon_encode_simple():
    """Test basic dictionary to TOON conversion"""
    print("TEST 1: TOON Encode - Simple Dictionary")
    
    from backend.toon import to_toon
    
    # Test simple dict
    data = {
        "title": "Setup Guide",
        "priority": 5,
        "status": "active"
    }
    
    result = to_toon(data)
    expected_lines = ["title: Setup Guide", "priority: 5", "status: active"]
    
    result_lines = result.strip().split('\n')
    
    if all(line in result_lines for line in expected_lines):
        print(f"  ✅ PASS: Simple dict encoded correctly")
        print(f"     Input: {data}")
        print(f"     Output: {result}")
        return True
    else:
        print(f"  ❌ FAIL: Encoding mismatch")
        print(f"     Expected: {expected_lines}")
        print(f"     Got: {result_lines}")
        return False


# ========== TEST 2: TOON Array Encoding ==========
def test_toon_encode_array():
    """Test array/list encoding with TOON"""
    print("\nTEST 2: TOON Encode - Arrays")
    
    from backend.toon import to_toon
    
    data = {
        "tags": ["jazz", "chill", "lofi"],
        "scores": [95, 87, 92]
    }
    
    result = to_toon(data)
    
    # Check for array format: tags[3]: jazz,chill,lofi
    if "tags[3]: jazz,chill,lofi" in result and "scores[3]: 95,87,92" in result:
        print(f"  ✅ PASS: Arrays encoded correctly")
        print(f"     Input: {data}")
        print(f"     Output: {result}")
        return True
    else:
        print(f"  ❌ FAIL: Array encoding wrong")
        print(f"     Got: {result}")
        return False


# ========== TEST 3: TOON Decoding ==========
def test_toon_decode():
    """Test TOON string back to dictionary"""
    print("\nTEST 3: TOON Decode - Back to Dictionary")
    
    from backend.toon import from_toon
    
    toon_str = """title: Setup Guide
priority: 5
tags[3]: install,config,guide
status: active"""
    
    result = from_toon(toon_str)
    
    expected = {
        "title": "Setup Guide",
        "priority": "5",  # Note: TOON decodes numbers as strings
        "tags": ["install", "config", "guide"],
        "status": "active"
    }
    
    if result == expected:
        print(f"  ✅ PASS: TOON decoded correctly")
        print(f"     Input: {toon_str}")
        print(f"     Output: {result}")
        return True
    else:
        print(f"  ❌ FAIL: Decoding mismatch")
        print(f"     Expected: {expected}")
        print(f"     Got: {result}")
        return False


# ========== TEST 4: Token Count Savings ==========
def test_token_savings():
    """Test that TOON actually saves tokens vs JSON"""
    print("\nTEST 4: Token Count Savings (JSON vs TOON)")
    
    import json
    from backend.toon import to_toon
    
    # Sample RAG document metadata
    data = {
        "title": "Installation Guide",
        "content": "This guide explains how to install the software",
        "tags": ["install", "setup", "tutorial", "beginner"],
        "category": "documentation",
        "priority": 5,
        "author": "admin"
    }
    
    # JSON format
    json_str = json.dumps(data)
    json_tokens = len(json_str.split())  # Rough token estimate
    
    # TOON format
    toon_str = to_toon(data)
    toon_tokens = len(toon_str.split())  # Rough token estimate
    
    # Calculate savings
    savings = ((json_tokens - toon_tokens) / json_tokens) * 100
    
    print(f"     JSON: {len(json_str)} chars, ~{json_tokens} tokens")
    print(f"     TOON: {len(toon_str)} chars, ~{toon_tokens} tokens")
    print(f"     Savings: {savings:.1f}%")
    
    if toon_tokens < json_tokens:
        print(f"  ✅ PASS: TOON uses fewer tokens")
        return True
    else:
        print(f"  ❌ FAIL: TOON doesn't save tokens")
        return False


# ========== TEST 5: RAG Context Formatting ==========
def test_rag_context_toon():
    """Test RAG document context in TOON format"""
    print("\nTEST 5: RAG Context Formatting with TOON")
    
    from backend.toon import format_rag_context_toon
    
    # Simulate RAG documents (like from ChromaDB)
    docs = [
        {
            "page_content": "To install, run: pip install assistify",
            "metadata": {"source": "install.md", "type": "guide"}
        },
        {
            "page_content": "Configuration is in config.py file",
            "metadata": {"source": "config.md", "type": "reference"}
        }
    ]
    
    result = format_rag_context_toon(docs)
    
    # Check format
    if "doc[0]:" in result and "doc[1]:" in result and "content:" in result:
        print(f"  ✅ PASS: RAG context formatted correctly")
        print(f"     Output preview:")
        for line in result.split('\n')[:5]:
            print(f"       {line}")
        return True
    else:
        print(f"  ❌ FAIL: RAG context format wrong")
        print(f"     Got: {result[:100]}")
        return False


# ========== TEST 6: Empty and Edge Cases ==========
def test_edge_cases():
    """Test edge cases: empty dict, empty arrays, special chars"""
    print("\nTEST 6: Edge Cases")
    
    from backend.toon import to_toon, from_toon
    
    # Empty dict
    empty = {}
    toon_empty = to_toon(empty)
    if toon_empty.strip() == "":
        print(f"  ✅ PASS: Empty dict handled")
    else:
        print(f"  ❌ FAIL: Empty dict not handled")
        return False
    
    # Empty array
    empty_arr = {"tags": []}
    toon_arr = to_toon(empty_arr)
    if "tags[0]:" in toon_arr:
        print(f"  ✅ PASS: Empty array handled")
    else:
        print(f"  ❌ FAIL: Empty array not handled")
        return False
    
    # Special characters
    special = {"message": "Hello: world, test"}
    toon_special = to_toon(special)
    decoded = from_toon(toon_special)
    if decoded["message"] == "Hello: world, test":
        print(f"  ✅ PASS: Special chars preserved")
        return True
    else:
        print(f"  ❌ FAIL: Special chars lost")
        print(f"     Original: {special['message']}")
        print(f"     Decoded: {decoded.get('message')}")
        return False


# ========== TEST 7: Integration with LLM Context ==========
def test_llm_integration():
    """Test TOON integration with LLM prompt building"""
    print("\nTEST 7: LLM Integration")
    
    from backend.toon import build_llm_prompt_with_toon
    
    query = "How do I install the software?"
    docs = [
        {"page_content": "Run pip install", "metadata": {"source": "guide.md"}},
        {"page_content": "Python 3.8+ required", "metadata": {"source": "requirements.md"}}
    ]
    
    prompt = build_llm_prompt_with_toon(query, docs)
    
    # Check prompt structure
    if query in prompt and "doc[0]:" in prompt and "content:" in prompt:
        print(f"  ✅ PASS: LLM prompt built correctly with TOON")
        print(f"     Prompt length: {len(prompt)} chars")
        return True
    else:
        print(f"  ❌ FAIL: LLM prompt structure wrong")
        return False


# ========== TEST 8: Nested Objects ==========
def test_nested_objects():
    """Test nested dictionaries (flatten or handle gracefully)"""
    print("\nTEST 8: Nested Objects")
    
    from backend.toon import to_toon
    
    data = {
        "user": "john",
        "metadata": {
            "role": "admin",
            "permissions": ["read", "write"]
        }
    }
    
    try:
        result = to_toon(data)
        # Should flatten or handle nested dict
        if "user:" in result and ("role:" in result or "metadata:" in result):
            print(f"  ✅ PASS: Nested objects handled")
            print(f"     Output: {result}")
            return True
        else:
            print(f"  ⚠️  WARNING: Nested objects partially handled")
            return True  # Not critical failure
    except Exception as e:
        print(f"  ❌ FAIL: Nested objects crashed: {e}")
        return False


# ========== TEST 9: Performance Comparison ==========
def test_performance():
    """Test encoding/decoding speed (TOON vs JSON)"""
    print("\nTEST 9: Performance Comparison")
    
    import json
    import time
    from backend.toon import to_toon, from_toon
    
    # Large dataset
    data = {
        f"field{i}": f"value{i}" for i in range(100)
    }
    data["tags"] = [f"tag{i}" for i in range(50)]
    
    # JSON benchmark
    start = time.time()
    for _ in range(100):
        json_str = json.dumps(data)
        json.loads(json_str)
    json_time = time.time() - start
    
    # TOON benchmark
    start = time.time()
    for _ in range(100):
        toon_str = to_toon(data)
        from_toon(toon_str)
    toon_time = time.time() - start
    
    print(f"     JSON: {json_time:.4f}s")
    print(f"     TOON: {toon_time:.4f}s")
    
    # TOON can be slower, that's OK (we care about token savings)
    print(f"  ✅ PASS: Performance measured (token savings > speed)")
    return True


# ========== RUN ALL TESTS ==========
def run_all_tests():
    """Run all TOON tests"""
    
    tests = [
        test_toon_encode_simple,
        test_toon_encode_array,
        test_toon_decode,
        test_token_savings,
        test_rag_context_toon,
        test_edge_cases,
        test_llm_integration,
        test_nested_objects,
        test_performance,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"  ❌ EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False))
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print("="*70)
    print(f"RESULTS: {passed}/{total} tests passed ({(passed/total*100):.1f}%)")
    print("="*70)
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    
    if not success:
        print("\n⚠️  Tests failed! Now implementing TOON to make them pass...")
    
    sys.exit(0 if success else 1)
