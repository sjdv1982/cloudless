from aiohttp import web
from aiohttp import client
import aiohttp
import asyncio
import pprint

"""
Reverse proxy code from:
https://github.com/oetiker/aio-reverse-proxy/blob/master/paraview-proxy.py'
(Copyright (c) 2018 Tobias Oetiker, MIT License)
"""

cloudless_port = 3124
rest_server = "http://localhost:5813"
update_server = "http://localhost:5138" # still http!

async def reverse_proxy_websocket(req):
    ws_server = web.WebSocketResponse()
    await ws_server.prepare(req)
    #logger.info('##### WS_SERVER %s' % pprint.pformat(ws_server))

    client_session = aiohttp.ClientSession(cookies=req.cookies)
    tail = req.match_info.get('tail')    
    async with client_session.ws_connect(
        update_server + "/" + tail,
    ) as ws_client:
        #logger.info('##### WS_CLIENT %s' % pprint.pformat(ws_client))

        async def ws_forward(ws_from,ws_to):
            async for msg in ws_from:
                #logger.info('>>> msg: %s',pprint.pformat(msg))
                mt = msg.type
                md = msg.data
                if mt == aiohttp.WSMsgType.TEXT:
                    await ws_to.send_str(md)
                elif mt == aiohttp.WSMsgType.BINARY:
                    await ws_to.send_bytes(md)
                elif mt == aiohttp.WSMsgType.PING:
                    await ws_to.ping()
                elif mt == aiohttp.WSMsgType.PONG:
                    await ws_to.pong()
                elif ws_to.closed:
                    await ws_to.close(code=ws_to.close_code,message=msg.extra)
                else:
                    raise ValueError('unexpected message type: %s',pprint.pformat(msg))

        # keep forwarding websocket data in both directions
        await asyncio.wait([ws_forward(ws_server,ws_client),ws_forward(ws_client,ws_server)],return_when=asyncio.FIRST_COMPLETED)

        return ws_server

async def reverse_proxy_http(req):
    tail = req.match_info.get('tail')
    reqH = req.headers.copy()
    async with client.request(
        req.method,rest_server + "/" + tail,
        params=req.query,
        headers = reqH,
        allow_redirects=False,
        data = await req.read()
    ) as res:
        headers = res.headers.copy()
        del headers['content-length']
        body = await res.read()
        return web.Response(
            headers = headers,
            status = res.status,
            body = body
        )        

async def reverse_proxy(req):    
    reqH = req.headers.copy()
    if reqH.get('connection','').lower() == 'upgrade' \
      and reqH.get('upgrade', '').lower() == 'websocket' \
      and req.method == 'GET':
        return await reverse_proxy_websocket(req)
    else:
        return await reverse_proxy_http(req)

app = web.Application()
app.router.add_route('*','/{tail:.*}', reverse_proxy)
web.run_app(app,port=cloudless_port)