import aiohttp
from aiohttp import web
from aiohttp.client_exceptions import ClientConnectionError
import asyncio
import pprint
import traceback
import time
import struct
import pickle

_msg_modes = ("http", "ws", "ws_create")


def launch_instance(service, *, instance=None, existing_graph=None):
    raise NotImplementedError("launch_instance must be redefined by importing module")


def msg_pack(mode, header, payload):
    assert mode in _msg_modes, (mode, _msg_modes)
    if mode == "ws":
        if isinstance(payload, str):
            paybuffer = payload.encode()
        else:
            paybuffer = payload
    else:
        paybuffer = pickle.dumps(payload)
    h = str(_msg_modes.index(mode))
    header2 = h + str(header)
    headerbuf = header2.encode()
    headerlength = struct.pack("!H", len(headerbuf))
    msg = headerlength + headerbuf + paybuffer
    return msg


async def reverse_proxprox_websocket(ws_proxying, ws_client, connection_id):
    # print("PROXPROX")
    async for msg in ws_client:
        # print('>>> msg-proxprox: %s',pprint.pformat(msg))
        mt = msg.type
        md = msg.data
        if mt == aiohttp.WSMsgType.TEXT:
            mt = "1"
        elif mt == aiohttp.WSMsgType.BINARY:
            mt = "0"
        else:
            raise ValueError("unexpected message type: {}".format(pprint.pformat(msg)))
        header = mt + connection_id
        msg_wrapped = msg_pack("ws", header, md)
        await ws_proxying.send_bytes(msg_wrapped)


"""
Reverse proxy code from:
https://github.com/oetiker/aio-reverse-proxy/blob/master/paraview-proxy.py'
(Copyright (c) 2018 Tobias Oetiker, MIT License)
"""


async def reverse_proxy_websocket(req, client, update_server, port, tail):
    ws_server = web.WebSocketResponse()
    await ws_server.prepare(req)
    # logger.info('##### WS_SERVER %s' % pprint.pformat(ws_server))

    async with client.ws_connect(
        "{}:{}/{}".format(update_server, port, tail),
    ) as ws_client:
        # logger.info('##### WS_CLIENT %s' % pprint.pformat(ws_client))

        async def ws_forward(ws_from, ws_to):
            async for msg in ws_from:
                # logger.info('>>> msg: %s',pprint.pformat(msg))
                mt = msg.type
                md = msg.data
                if mt == aiohttp.WSMsgType.TEXT:
                    await ws_to.send_str(md)
                elif mt == aiohttp.WSMsgType.BINARY:
                    await ws_to.send_bytes(md)
                else:
                    raise ValueError(
                        "unexpected message type: {}".format(pprint.pformat(msg))
                    )

        # keep forwarding websocket data in both directions
        await asyncio.wait(
            [ws_forward(ws_server, ws_client), ws_forward(ws_client, ws_server)],
            return_when=asyncio.FIRST_COMPLETED,
        )


async def reverse_proxy_http(reqdata, client, rest_server, port, tail, instance=None):
    reqH = reqdata["headers"]
    async with client.request(
        reqdata["method"],
        "{}:{}/{}".format(rest_server, port, tail),
        params=reqdata["query"],
        headers=reqH,
        allow_redirects=False,
        data=reqdata["data"],
    ) as res:
        headers = res.headers.copy()
        del headers["content-length"]
        if "location" in headers:
            instance_name = reqdata["instance"]
            headers["location"] = "/instance/{}{}".format(
                instance_name, headers["location"]
            )
        if instance is not None:
            instance.last_request_time = time.time()
        body = await res.read()
        if instance is not None:
            instance.last_request_time = time.time()
        return web.Response(headers=headers, status=res.status, body=body)


async def reverse_proxy(req, rest_server, update_server, instances):
    reqH = req.headers.copy()
    instance = req.match_info.get("instance")
    try:
        instance = int(instance)
    except ValueError:
        pass
    tail = req.match_info.get("tail")
    if instance not in instances:
        graph = get_graph(instance)
        if graph is None:
            return web.Response(status=404, text="Unknown instance")
        graph, service = graph
        try:
            launch_instance(service, instance=instance, existing_graph=graph)
            assert instance in instances
        except Exception:
            exc = traceback.format_exc()
            return web.Response(status=500, text=exc)

    inst = instances[instance]

    if not inst.complete:
        if inst.error:
            return web.Response(
                status=500, text="***Launch error***\n\n" + inst.error_message
            )
        else:
            if req.method == "GET":
                return web.Response(
                    status=202,
                    text="""
<head>
  <meta http-equiv="refresh" content="3">
</head>
<body>
Loading...
</body>
                    """,
                    content_type="text/html",
                )
            else:
                for _retries in range(30):
                    await asyncio.sleep(1)
                    inst = instances.get(instance)
                    if inst is None:
                        return web.Response(status=500)
                    if inst.complete:
                        break

    update_port = inst.update_port
    rest_port = inst.rest_port
    for _retries in range(5):
        try:
            async with aiohttp.ClientSession(cookies=req.cookies) as client:
                if (
                    reqH.get("connection", "").lower() == "upgrade"
                    and reqH.get("upgrade", "").lower() == "websocket"
                    and req.method == "GET"
                ):
                    await reverse_proxy_websocket(
                        req, client, update_server, update_port, tail
                    )
                    return web.Response(status=200)
                else:
                    inst.last_request_time = time.time()
                    reqdata = {
                        "method": req.method,
                        "headers": req.headers.copy(),
                        "query": req.query,
                        "instance": req.match_info.get("instance"),
                        "data": await req.read(),
                    }
                    inst.last_request_time = time.time()
                    return await reverse_proxy_http(
                        reqdata, client, rest_server, rest_port, tail, inst
                    )
        except ClientConnectionError:
            await asyncio.sleep(3)


from icicle import get_graph
