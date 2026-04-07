from backend.assistify_rag_server import _extract_list_from_context

# Sample contexts for testing
ctx_phases = """
Prior to 1880
Figure 3.1: Timeline
Domestic System, Handicraft Period, Guilds, Cottage Period, Industrial Revolution
Some explanatory paragraph.
"""

ctx_steps = """
Planning Process:
1. Define objectives
2. Gather data
3. Analyze information
4. Develop plan
5. Implement
6. Monitor and adjust
"""

ctx_disadvantages = """
Principles:
- Principle of Scientific Management
Advantages:
- Increased efficiency
Disadvantages:
- Worker alienation
- Overspecialization
- Neglect of human factors
"""


def run_tests():
    print("Test 1: Phases of pre-scientific management")
    out1 = _extract_list_from_context("Phases of pre-scientific management", ctx_phases)
    print(out1 or "<no list detected>")
    print('\nTest 2: Steps in planning process')
    out2 = _extract_list_from_context("Steps in planning process", ctx_steps)
    print(out2 or "<no list detected>")
    print('\nTest 3: Disadvantages of scientific management')
    out3 = _extract_list_from_context("Disadvantages of scientific management", ctx_disadvantages)
    print(out3 or "<no list detected>")

if __name__ == '__main__':
    run_tests()
