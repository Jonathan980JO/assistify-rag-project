#!/usr/bin/env python3
"""Collect evidence from the live running server."""
import asyncio
import json
import time
import websockets

print("=== COLLECTING EVIDENCE ===\n")

# Query via WebSocket
print("[STEP 1] Sending query via WebSocket to /ws...")
ws_response = None
try:
    async def test_ws():
        global ws_response
        try:
            async with websockets.connect('ws://127.0.0.1:7000/ws', ping_interval=None) as ws:
                payload = {
                    'text': 'List the goals of psychology',
                    'language': 'en'
                }
                await ws.send(json.dumps(payload))
                # Collect all messages until done
                messages = []
                try:
                    while True:
                        msg = await asyncio.wait_for(ws.recv(), timeout=120.0)
                        messages.append(msg)
                        # Check if this is the final response
                        try:
                            data = json.loads(msg)
                            if data.get("type") == "aiResponseDone":
                                # Final answer received
                                ws_response = msg
                                print("\n=== REAL /ws OUTPUT ===")
                                print(msg)
                                break
                        except:
                            pass
                except asyncio.TimeoutError:
                    if messages:
                        ws_response = messages[-1]  # Last message received
                        print("\n=== REAL /ws OUTPUT ===")
                        print(ws_response)
        except Exception as e:
            print(f"WebSocket error: {e}")
    
    asyncio.run(test_ws())
except Exception as e:
    print(f"Error setting up WebSocket: {e}")

# Now read the log file for the full debug output
print("\n[STEP 2] Reading server log for debug info...")
time.sleep(3)  # Wait a moment for logs to be written

try:
    with open('C:\\Users\\MK\\Desktop\\assistify_rag_live.log', 'r') as f:
        content = f.read()
    
    # Extract the log lines with the keywords we need
    print("\n=== WS LOG BLOCK ===")
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if any(keyword in line for keyword in [
            'RAG Result',
            'RAG FINAL SELECTED',
            'SELECTED CHUNK INDEXES',
            'QUERY TOKEN DEBUG',
            'SECTION DEBUG',
            'LIST DEBUG',
            'LIST FINAL DECISION',
            'FINAL DECISION DEBUG',
            'WS FINAL ANSWER',
            'retrieved_chunks',
            'final_answer',
            'List the goals',
            'aiResponseDone'
        ]):
            print(line)
            
except Exception as e:
    print(f"Error reading log: {e}")
