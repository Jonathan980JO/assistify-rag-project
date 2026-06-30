"""
Chat Performance Test - Measure response times and identify bottlenecks
Tests WebSocket chat with proper authentication
"""

import asyncio
import aiohttp
import time
from statistics import mean, median
from itsdangerous import URLSafeSerializer
import sys
import os

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Test configuration
WS_URL = "ws://127.0.0.1:7001/ws"
NUM_TESTS = 3

print("="*70)
print("CHAT PERFORMANCE TEST")
print("="*70)
print()

# Create authenticated session cookie
s = URLSafeSerializer(config.SESSION_SECRET)
token = s.dumps({"username": "admin", "role": "admin"})
cookies = {config.SESSION_COOKIE: token}

print("Testing WebSocket chat with admin credentials...")
print()

# Test queries of varying complexity
test_queries = [
    "Hello",
    "What is your name?",
    "Can you help me with a technical issue?",
]

results = {
    "response_times": [],
    "query_details": []
}

async def test_chat_query(query_text, test_num):
    """Send a query via WebSocket and measure response time"""
    start_time = time.time()
    response_text = None
    error = None
    ws = None
    session = None
    
    try:
        # Create session with cookies
        cookie_str = f"{config.SESSION_COOKIE}={cookies[config.SESSION_COOKIE]}"
        headers = {"Cookie": cookie_str}
        
        timeout = aiohttp.ClientTimeout(total=30)
        session = aiohttp.ClientSession()
        ws = await session.ws_connect(WS_URL, headers=headers, timeout=timeout)
        
        # Send text query
        await ws.send_json({"text": query_text})
        
        # Wait for response with timeout
        try:
            async with asyncio.timeout(30):
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = msg.json()
                        
                        # Look for AI response
                        if data.get("type") == "aiResponse":
                            response_text = data.get("text", "")
                            break
                        elif "error" in data:
                            error = data["error"]
                            break
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        error = "WebSocket error"
                        break
        except asyncio.TimeoutError:
            error = "TIMEOUT (>30s)"
                
    except asyncio.TimeoutError:
        error = "Connection TIMEOUT"
    except aiohttp.ClientConnectorError:
        error = "Cannot connect - server not running on port 7001"
    except Exception as e:
        error = str(e)
    finally:
        # Proper cleanup to prevent event loop errors
        if ws and not ws.closed:
            await ws.close()
        if session and not session.closed:
            await session.close()
    
    elapsed = time.time() - start_time
    
    return {
        "query": query_text,
        "test_num": test_num,
        "time": elapsed,
        "response": response_text,
        "error": error
    }

async def run_all_tests():
    """Run all performance tests"""
    print(f"Running {NUM_TESTS} tests per query...\n")
    
    for query_text in test_queries:
        print(f"\n📝 Query: '{query_text}'")
        print("-" * 70)
        
        for i in range(NUM_TESTS):
            result = await test_chat_query(query_text, i + 1)
            
            if result["error"]:
                print(f"  Test {i+1}: ERROR - {result['error']}")
                if "Cannot connect" in result["error"]:
                    print("\n⚠️  Server is not running. Please start the server first:")
                    print("     python scripts/project_start_server.py --reload")
                    return results
            else:
                print(f"  Test {i+1}: {result['time']:.3f}s")
                results["response_times"].append(result["time"])
                results["query_details"].append(result)
            
            # Small delay between tests
            await asyncio.sleep(0.5)
    
    return results

# Run the async tests with proper event loop handling
try:
    if sys.platform == 'win32':
        # Fix for Windows ProactorEventLoop
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    loop_results = asyncio.run(run_all_tests())
except KeyboardInterrupt:
    print("\n\n⚠️  Test interrupted by user")
    loop_results = results
except Exception as e:
    print(f"\n\n❌ Test failed: {e}")
    loop_results = results

print("\n")
print("="*70)
print("PERFORMANCE SUMMARY")
print("="*70)

if results["response_times"]:
    print(f"\n⏱️  Chat Response Times:")
    print(f"  Tests completed: {len(results['response_times'])}/{NUM_TESTS * len(test_queries)}")
    print(f"  Average: {mean(results['response_times']):.3f}s")
    print(f"  Median:  {median(results['response_times']):.3f}s")
    print(f"  Min:     {min(results['response_times']):.3f}s")
    print(f"  Max:     {max(results['response_times']):.3f}s")
    
    avg_time = mean(results['response_times'])
    if avg_time > 10.0:
        print(f"\n  🚨 CRITICAL: Chat is VERY SLOW (avg > 10s)")
        print(f"     Users will experience significant lag!")
        print(f"\n  💡 Possible causes:")
        print(f"     1. LLM running on CPU instead of GPU")
        print(f"     2. Large model size without quantization")
        print(f"     3. Network latency between servers")
        print(f"     4. Database query bottlenecks")
    elif avg_time > 5.0:
        print(f"\n  ⚠️  WARNING: Chat is SLOW (avg > 5s)")
        print(f"     Users will notice delays")
        print(f"\n  💡 Suggestions:")
        print(f"     - Enable GPU acceleration (CUDA)")
        print(f"     - Use quantized models (Q4/Q5)")
        print(f"     - Reduce max_tokens in generation")
    elif avg_time > 3.0:
        print(f"\n  ℹ️  INFO: Chat is acceptable but noticeable (3-5s)")
        print(f"     Consider minor optimizations")
    else:
        print(f"\n  ✅ Chat is fast and responsive!")
    
    # Show individual query breakdown
    print(f"\n📊 Response Time Breakdown:")
    for detail in results["query_details"]:
        status = "✅" if detail["time"] < 3.0 else "⚠️" if detail["time"] < 5.0 else "🚨"
        print(f"  {status} '{detail['query'][:40]}...' - {detail['time']:.3f}s")
else:
    print("\n❌ No successful tests completed!")
    print("   Possible issues:")
    print("   - Servers not running (check ports 7001, 7000, 8000)")
    print("   - Authentication failed")
    print("   - WebSocket connection blocked")

print("\n" + "="*70)

