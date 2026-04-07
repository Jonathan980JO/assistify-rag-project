import asyncio
import json
import websockets

async def m():
    uri = 'ws://127.0.0.1:7000/ws'
    async with websockets.connect(uri, max_size=2**22, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({'text': 'What is psychology?', 'language': 'en'}))
        chunks = []
        done = None
        for _ in range(400):
            msg = await asyncio.wait_for(ws.recv(), timeout=120)
            if isinstance(msg, (bytes, bytearray)):
                continue
            data = json.loads(msg)
            if data.get('type') == 'aiResponseChunk':
                chunks.append((data.get('text') or '').strip())
            if data.get('type') == 'aiResponseDone':
                done = data
                break
        print('chunks', len(chunks))
        print('preview', ' | '.join([c for c in chunks if c][:3]))
        print('full', (done or {}).get('fullText', ''))

asyncio.run(m())

