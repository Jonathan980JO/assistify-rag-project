"""Test list extraction directly without WebSocket"""
import sys
sys.path.insert(0, r'G:\Grad_Project\assistify-rag-project-main')

# Mock the test data
test_text = "The goals of psychology include description, explanation, prediction, control of behavior and mental processes."

print("="*60)
print("Testing _extract_inline_concept_items directly")
print("="*60)

# Import the function
from backend.assistify_rag_server import _assess_list_coherence

# Test with sample data
query = "List the goals of psychology"
answer_text = test_text

print(f"\nQuery: {query}")
print(f"Answer text: {answer_text}")
print("\nCalling _assess_list_coherence with strict_fast=True...\n")

ok, reason, shaped = _assess_list_coherence(query, answer_text, strict_fast=True)

print(f"\nResult:")
print(f"  ok = {ok}")
print(f"  reason = {reason}")
print(f"  shaped = {shaped}")
