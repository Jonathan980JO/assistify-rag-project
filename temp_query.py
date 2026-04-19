import asyncio
import websockets
import json

async def query_ws():
    uri = 'ws://localhost:7000/ws'
    payload = {'text': 'What are the main characteristics of management? Please be brief.'}
    try:
        async with websockets.connect(uri) as websocket:
            print('Connected...')
            await websocket.send(json.dumps(payload))
            print('Payload sent...')
            while True:
                response = await websocket.recv()
                data = json.loads(response)
                # Print any incoming data for debugging
                print(f'Received: {list(data.keys())}') 
                if 'aiResponseDone' in data:
                    print('\nFULL TEXT:')
                    print(data['aiResponseDone']['fullText'])
                    break
    except Exception as e:
        print(f'Error: {e}')

if __name__ == '__main__':
    try:
        asyncio.run(asyncio.wait_for(query_ws(), timeout=240))
    except Exception as e:
        print(f'Timeout or Final Error: {e}')
