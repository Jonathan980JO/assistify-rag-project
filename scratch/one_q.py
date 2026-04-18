import asyncio,json,sys,websockets
async def go(q):
    async with websockets.connect('ws://localhost:7000/ws',max_size=None) as w:
        await w.send(json.dumps({'text': q}))
        while True:
            m=await asyncio.wait_for(w.recv(),timeout=120)
            if isinstance(m,(bytes,bytearray)):continue
            d=json.loads(m)
            if d.get('type')=='aiResponseDone':
                print('ANS:',d.get('fullText',''));break
asyncio.run(go(sys.argv[1]))
import asyncio,json,websockets
async def go():
    async with websockets.connect('ws://localhost:7000/ws',max_size=None) as w:
        await w.send(json.dumps({'text':"What are Fayols principles of management?"}))
        while True:
            m=await asyncio.wait_for(w.recv(),timeout=120)
            if isinstance(m,(bytes,bytearray)):continue
            d=json.loads(m)
            if d.get('type')=='aiResponseDone':print('ANS:',d.get('fullText',''));break
asyncio.run(go())
