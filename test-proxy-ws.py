import websockets
import asyncio
import sys
async def echo(uri):
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            print("WS ECHO", message)

url = sys.argv[1]
time = int(sys.argv[2])
ws = echo(url)
asyncio.ensure_future(ws)
asyncio.get_event_loop().run_until_complete(asyncio.sleep(time))