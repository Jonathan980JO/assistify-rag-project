"""
Test script for Response Validation
Run this to test the validation module independently
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from response_validator import validate_response

def test_validation():
    """Run validation tests"""
    
    print("="*60)
    print("RESPONSE VALIDATION TEST SUITE")
    print("="*60)
    print()
    
    test_cases = [
        {
            "response": "Hello! I'd be happy to help you with your account.",
            "query": "help with my account",
            "name": "✅ Clean Response",
            "should_pass": True
        },
        {
            "response": "Your fucking account has been suspended!",
            "query": "account status",
            "name": "❌ Profanity Test",
            "should_pass": False
        },
        {
            "response": "Please email me at support@company.com for help.",
            "query": "need support",
            "name": "❌ PII - Email Test",
            "should_pass": False
        },
        {
            "response": "Your SSN is 123-45-6789, please verify.",
            "query": "verify identity",
            "name": "❌ PII - SSN Test",
            "should_pass": False
        },
        {
            "response": "I don't know the answer to that question.",
            "query": "advanced technical question",
            "name": "⚠️ Uncertainty Test (auto-disclaimer)",
            "should_pass": True
        },
        {
            "response": "The weather is nice today.",
            "query": "help with my password",
            "name": "⚠️ Irrelevant Response",
            "should_pass": True  # Warning but not blocked
        },
        {
            "response": "I can help you reset your password. Go to Settings > Security.",
            "query": "password reset",
            "name": "✅ Normal Response",
            "should_pass": True
        },
        {
            "response": "Call me at 555-123-4567 for assistance.",
            "query": "need help",
            "name": "❌ PII - Phone Number",
            "should_pass": False
        },
    ]
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['name']}")
        print("-" * 60)
        print(f"Query:    {test['query']}")
        print(f"Response: {test['response'][:80]}{'...' if len(test['response']) > 80 else ''}")
        
        result = validate_response(test['response'], test['query'])
        
        # Check if result matches expectation
        test_passed = result.is_valid == test['should_pass']
        
        if test_passed:
            print(f"✓ TEST PASSED")
            passed += 1
        else:
            print(f"✗ TEST FAILED")
            failed += 1
        
        print(f"Valid:    {result.is_valid}")
        print(f"Severity: {result.severity}")
        
        if result.issues:
            print(f"Issues:")
            for issue in result.issues:
                print(f"  - [{issue['severity']}] {issue['message']}")
        
        if result.modified_response and result.modified_response != test['response']:
            print(f"Modified: {result.modified_response[:80]}{'...' if len(result.modified_response) > 80 else ''}")
    
    print()
    print("="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60)
    
    if failed == 0:
        print("🎉 All tests passed!")
    else:
        print(f"⚠️ {failed} test(s) failed")
    
    return failed == 0


if __name__ == "__main__":
    success = test_validation()
    sys.exit(0 if success else 1)
