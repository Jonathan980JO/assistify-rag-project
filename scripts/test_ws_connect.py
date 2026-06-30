import asyncio
import aiohttp

async def main():
    url = 'ws://127.0.0.1:7001/ws'
    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(url, timeout=5) as ws:
                print('Connected to', url)
                await ws.send_json({'type':'ping'})
                try:
                    msg = await ws.receive(timeout=5)
                    print('Received:', msg)
                except asyncio.TimeoutError:
                    print('No response from server (timeout)')
        except Exception as e:
            print('Connection failed:', e)

if __name__ == '__main__':
    asyncio.run(main())
