import asyncio
import websockets
import json
import sys

async def validate():
    uri = "ws://127.0.0.1:7000/ws"
    queries = ['What are the goals of psychology', 'What is scientific management', 'Tell me more about Control of human behavior']
    
    results = []
    
    try:
        async with websockets.connect(uri) as websocket:
            for query in queries:
                print(f"--- Query: {query} ---")
                payload = {'text': query, 'language': 'en'}
                await websocket.send(json.dumps(payload))
                
                msg_counts = {}
                tts_start_count = 0
                tts_end_count = 0
                binary_frames = 0
                binary_bytes = 0
                full_text = ""
                done = False
                
                while not done:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=180)
                        if isinstance(message, str):
                            data = json.loads(message)
                            msg_type = data.get('type')
                            msg_counts[msg_type] = msg_counts.get(msg_type, 0) + 1
                            
                            if msg_type == 'ttsAudioStart':
                                tts_start_count += 1
                            elif msg_type == 'ttsAudioEnd':
                                tts_end_count += 1
                            elif msg_type == 'aiResponse':
                                full_text += data.get('text', '')
                            elif msg_type == 'aiResponseDone':
                                done = True
                        else:
                            binary_frames += 1
                            binary_bytes += len(message)
                    except asyncio.TimeoutError:
                        print(f"Timeout reached for query: {query}")
                        done = True
                
                results.append({
                    'query': query,
                    'done': done,
                    'msg_counts': msg_counts,
                    'tts_start': tts_start_count,
                    'tts_end': tts_end_count,
                    'binary_frames': binary_frames,
                    'binary_bytes': binary_bytes,
                    'preview': full_text[:100]
                })
                print(f"Status - Done: {done}, Binary Bytes: {binary_bytes}")

        overall_pass = True
        for res in results:
            print(f"Summary for '{res['query']}': Done={res['done']}, Bytes={res['binary_bytes']}, MsgCounts={res['msg_counts']}")
            if not res['done'] or res['binary_bytes'] == 0:
                overall_pass = False
        
        if overall_pass:
            print("RESULT: PASS")
        else:
            print("RESULT: FAIL")
            
    except Exception as e:
        print(f"Error: {e}")
        print("RESULT: FAIL")

if __name__ == '__main__':
    asyncio.run(validate())
