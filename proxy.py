import aiohttp
from aiohttp import web
import asyncio
import logging
import pprint
import struct
import pickle

_proxies = {}
_proxied_websockets = {}

modes = ("http", "ws", "ws_create")

def msg_pack(mode, header, payload):
    assert mode in modes, (mode, modes)
    if mode == "ws":        
        if isinstance(payload, str):
            paybuffer = payload.encode()
        else:
            paybuffer = payload
    else:
        paybuffer = pickle.dumps(payload)    
    h = str(modes.index(mode))
    header2 = h + str(header)
    headerbuf = header2.encode()
    headerlength = struct.pack("!H", len(headerbuf))
    msg = headerlength + headerbuf + paybuffer
    return msg

def msg_unpack(msg):
    headerlength, msg = msg[:2], msg[2:]
    headerlength = struct.unpack("!H", headerlength)[0]
    header2, payload = msg[:headerlength], msg[headerlength:]
    header2 = header2.decode()
    mode_index, header = int(header2[0]), header2[1:]
    mode = modes[mode_index]
    return mode, header, payload

class Proxy:
    def __init__(self, name, ws_proxied):
        self.name = name
        self.ws_proxied = ws_proxied
        self.queue = asyncio.Queue()
        self.http_futures = {}
        self.ws_futures = {}
        self.ws_connections = {}
        self.future = None
        self._req_count = 0
    
    async def _serve(self):
        async for msg in self.ws_proxied:
            #logger.info('>>> msg: %s',pprint.pformat(msg))
            #print('>>> msg1: %s',pprint.pformat(msg))
            mt = msg.type
            md = msg.data
            if mt == aiohttp.WSMsgType.TEXT:
                raise ValueError("Proxied Cloudless should send bytes")                
            elif mt == aiohttp.WSMsgType.BINARY:
                await self._serve_message(md)
            else:
                raise ValueError('unexpected message type: %s',pprint.pformat(msg))

        _proxies[self.name] = None
        for ws_connection in self.ws_connections.values():
            await ws_connection.close(
                code=ws_connection.close_code
            )
        for ws_future in self.ws_futures.values():
            ws_future.set_result(None)
        for http_future in self.http_futures.values():
            response = {
                "status":502
            }
            http_future.set_result(response)

    async def _serve_message(self, msg):
        mode, header, payload = msg_unpack(msg)
        if mode == "http": #HTTP
            id = header
            if id not in self.http_futures:
                print("Unknown HTTP connection ID: {}".format(id))
                return
            fut = self.http_futures[id]
            response = pickle.loads(payload)
            #print("PROXY RESPONSE", id, response)
            fut.set_result(response)
        elif mode == "ws":
            mt, id = header[0], header[1:]
            if id not in self.ws_connections:
                print("Unknown websocket connection ID: {}".format(id))
                return
            ws_connection = self.ws_connections[id]
            if mt == "0":
                await ws_connection.send_bytes(payload)
            elif mt == "1":
                await ws_connection.send_str(payload.decode())
            else:
                print("Unknown message type for websocket connection {}".format(id))
        else:
            print("Proxied Cloudless may not create websockets")


    def serve(self):
        assert self.future is None
        future = asyncio.ensure_future(self._serve())
        self.future = future

    async def http_request(self, reqdata):
        self._req_count += 1
        req_count = str(self._req_count)
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self.http_futures[req_count] = fut
        msg = msg_pack("http", req_count, reqdata)
        await self.ws_proxied.send_bytes(msg)
        await fut
        if self.http_futures.get(req_count) is fut:
            self.http_futures.pop(req_count)
        return fut.result()

    async def websocket_connect(self, ws_connection, tail, instance, cookies):
        self._req_count += 1
        req_count = str(self._req_count)
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self.ws_connections[req_count] = ws_connection
        self.ws_futures[req_count] = fut
        payload = {
            "tail": tail,
            "instance": instance,
            "cookies": cookies
        }
        msg = msg_pack("ws_create", req_count, payload)
        await self.ws_proxied.send_bytes(msg)
        await fut
        if self.ws_connections.get(req_count) is ws_connection:
            self.ws_connections.pop(req_count)
        if self.ws_futures.get(req_count) is fut:
            self.ws_futures.pop(req_count)


async def create_proxy(name, req):
    ws_proxied = web.WebSocketResponse()
    await ws_proxied.prepare(req)    
    if name in _proxies:
        """
        # Disable this, because proxies can be closed... can we check this?
        return web.Response(
            status=400,
            text="Proxy '{}' already exists".format(name)
        )
        """
        print("RECREATED PROXY", name)
    else:
        print("CREATED PROXY", name)
    proxy = Proxy(name, ws_proxied)
    _proxies[name] = proxy
    ###proxy.serve()
    await proxy._serve()
    

async def _serve_myself_message_ws(
    ws_proxying, cookies, connection_id, update_server, update_port, tail, ws_connections
):
    from reverse_proxy import reverse_proxprox_websocket
    async with aiohttp.ClientSession(cookies=cookies) as client:        
        async with client.ws_connect(
        "{}:{}/{}".format(update_server, update_port, tail),
        ) as ws_client:
            try:
                ws_connections[connection_id] = ws_client
                await reverse_proxprox_websocket(ws_proxying, ws_client, connection_id)
            finally:
                ws_connections.pop(connection_id)
    
async def _serve_myself_message(
    ws_proxying, msg,  
    rest_server, update_server, 
    instances, ws_connections
):
    from reverse_proxy import (
        reverse_proxy_http, 
        reverse_proxprox_websocket,
    )

    mode, header, payload =  msg_unpack(msg)
    
    if mode in ("http", "ws_create"):
        id = header
        requestdata = pickle.loads(payload)
        try:
            cookies = requestdata["cookies"]
            tail = requestdata["tail"]
            instance = requestdata["instance"]
        except (KeyError, ValueError):
            err = "Malformatted HTTP request data"
            import traceback; traceback.print_exc()
            return {"id": id, "status": "400", "body": err}
        try:
            instance = int(instance)
        except ValueError:
            pass
        if instance not in instances:
            err = "Unknown Seamless instance '{}'".format(instance)
            return {"id": id, "status": "400", "body": err}
        inst = instances[instance]
        rest_port = inst.rest_port
        update_port = inst.update_port
        if mode == "http":
            async with aiohttp.ClientSession(cookies=cookies) as client:
                response = await reverse_proxy_http(
                    requestdata, client, rest_server, rest_port, tail
                )
                return {
                    "id": id,
                    "status": response.status,
                    "body": response.body,
                    "headers": {k:v for k,v in response.headers.items()}
                }
        else: #ws_create
            coro =_serve_myself_message_ws(
                ws_proxying, cookies,
                id, update_server, update_port, tail,
                ws_connections
            )
            asyncio.ensure_future(coro)
    elif mode == "ws":
        print("Seamless 0.01 ignores all messages sent to its websocket server...")
        pass
    else:
        raise ValueError("Malformatted proxy request")
    
async def serve_myself_through_proxy(client, url, rest_server, update_server, instances):
    print("""Cloudless is now served through a proxy 
This will last until you press Ctrl-C on the process that launched the connect_to_cloudless request
In addition, Cloudless is still available via its original port""")
    
    while 1:
        async with client.ws_connect(url) as ws_proxying:
            ws_connections = {}
            async for msg in ws_proxying:
                #print('>>> msg2: %s',pprint.pformat(msg))            
                mt = msg.type
                md = msg.data
                if mt == aiohttp.WSMsgType.TEXT:
                    raise ValueError("Proxying Cloudless should send bytes")                
                elif mt == aiohttp.WSMsgType.BINARY:
                    result = await _serve_myself_message(
                        ws_proxying,
                        md, rest_server, update_server, instances, ws_connections
                    )
                    #print("MSG RESULT", result)
                    if result is not None:
                        id = result.pop("id")
                        msg = msg_pack("http", id, result)
                        await ws_proxying.send_bytes(msg)
                else:
                    raise ValueError('unexpected message type: %s',pprint.pformat(msg))
            print("Reopen proxy...")

async def ws_listen(ws_connection, prox):
    async for msg in ws_connection:
        print("Seamless 0.01 ignores all messages sent to its websocket server... (2)", msg)
        pass

async def forward_proxy(req):
    reqH = req.headers.copy()
    proxy_name = req.match_info.get('proxy_name')
    instance = req.match_info.get('instance')
    tail = req.match_info.get('tail')
    if proxy_name not in _proxies:
        return web.Response(status=404,text="Unknown proxy '{}'".format(proxy_name))

    prox = _proxies[proxy_name]
    
    async with aiohttp.ClientSession(cookies=req.cookies) as client:
        if reqH.get('connection','').lower() == 'upgrade' \
          and reqH.get('upgrade', '').lower() == 'websocket' \
          and req.method == 'GET':
            ws_connection = web.WebSocketResponse()
            await ws_connection.prepare(req)
            cookies = {k:v for k,v in req.cookies.items()}
            coro1 = prox.websocket_connect(ws_connection, tail, instance, cookies)
            coro2 = ws_listen(ws_connection, prox)
            await asyncio.wait([coro1, coro2],return_when=asyncio.FIRST_COMPLETED)
        else:
            reqdata = {
                "method": req.method,
                "query": {k:v for k,v in req.query.items()},                
                "headers": {k:v for k,v in reqH.items()},
                "allow_redirects": False,
                "instance": instance,
                "tail": tail,
                "cookies": {k:v for k,v in req.cookies.items()},
                "data": await req.read(),                
            }            
            response = await prox.http_request(reqdata)
            return web.Response(
                status = response["status"],
                body = response["body"],
                headers = response.get("headers")
            )
