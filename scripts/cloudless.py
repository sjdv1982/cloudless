from aiohttp import web
import aiohttp
import asyncio
import pprint
import glob, os
import traceback
import random
import subprocess
import time

"""
Reverse proxy code from:
https://github.com/oetiker/aio-reverse-proxy/blob/master/paraview-proxy.py'
(Copyright (c) 2018 Tobias Oetiker, MIT License)
"""

currdir = os.path.split(os.path.abspath(__file__))[0]
os.chdir(currdir)

cloudless_port = 3124

rest_server = "http://localhost"
update_server = "http://localhost" # still http!

services = {}
for f in glob.glob("../graphs/*.seamless"):
    service_dir, service_file = os.path.split(f)
    service_name = os.path.splitext(service_file)[0]
    services[service_name] = service_dir, service_file

instances = {
    #1: (32876, 32875, None, None, False)
}


async def reverse_proxy_websocket(req, client, port, tail):
    ws_server = web.WebSocketResponse()
    await ws_server.prepare(req)
    #logger.info('##### WS_SERVER %s' % pprint.pformat(ws_server))
    
    async with client.ws_connect(
        "{}:{}/{}".format(update_server, port, tail),
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

async def reverse_proxy_http(req, client, port, tail):    
    reqH = req.headers.copy()
    async with client.request(
        req.method,"{}:{}/{}".format(rest_server, port, tail),
        params=req.query,
        headers = reqH,
        allow_redirects=False,
        data = await req.read()
    ) as res:
        headers = res.headers.copy()
        del headers['content-length']
        if "location" in headers:
            instance = req.match_info.get('instance')
            headers["location"] = "/instance/{}{}".format(
                instance,
                headers["location"]
            )
        body = await res.read()
        return web.Response(
            headers = headers,
            status = res.status,
            body = body
        )        

async def reverse_proxy(req):
    reqH = req.headers.copy()
    instance = req.match_info.get('instance')
    try:
        instance = int(instance)
    except ValueError:
        pass
    tail = req.match_info.get('tail')
    if instance not in instances:
        return web.Response(status=404,text="Unknown instance")

    update_port, rest_port, _, _, _ = instances[instance]
    async with aiohttp.ClientSession(cookies=req.cookies) as client:
        if reqH.get('connection','').lower() == 'upgrade' \
        and reqH.get('upgrade', '').lower() == 'websocket' \
        and req.method == 'GET':
            return await reverse_proxy_websocket(req, client, update_port, tail)
        else:
            return await reverse_proxy_http(req, client, rest_port, tail)

async def connect_instance(req):
    req = req.rel_url
    query = req.query
    instance = query.get("instance", None)
    if instance is None:
        return web.Response(
            status=400,
            text="Need to specify instance ID"
        )
    try:
        instance = int(instance)
    except ValueError:
        pass
    update_port = query.get("update_port", None)
    try:
        update_port = int(update_port)
        assert update_port >= 1000
    except:
        return web.Response(
            status=400,
            text="Need to specify integer update_port"
        )

    rest_port = query.get("rest_port", None)
    try:
        rest_port = int(rest_port)
        assert rest_port >= 1000
    except:
        return web.Response(
            status=400,
            text="Need to specify integer rest_port"
        )

    if instance in instances:
        if instances[instance][:2] != (update_port, rest_port):
            return web.Response(
                status=409,
                text="Instance already exists"
            )
        return web.Response(status=200)

    instances[instance] = update_port, rest_port, None, None, False
    return web.Response(status=200)

class LaunchError(Exception):
    pass

def launch(service_name, with_status=False):
    while 1:
        instance = random.choice(range(1000000, 10000000))
        container = "cloudless-{}".format(instance)
        if instance not in instances:
            break
    service_dir, service_file = services[service_name]
    cwd = os.getcwd()
    launch_command = os.path.abspath("../docker/commands/seamless-devel-serve-graph")
    try:
        os.chdir(service_dir)        
        cmd = "{} {} {}".format(launch_command, container, service_file)
        if with_status:
            d = "/home/jovyan/software/seamless/graphs/status-visualization"
            cmd += " --status-graph {0}.seamless".format(d)
        err, output = subprocess.getstatusoutput(cmd)        
        if err:
            raise LaunchError("Launch output:\n{}\n{}".format(err, output))
        update_port, rest_port = None, None
        for l in output.splitlines():
            fields = l.split("->")
            if len(fields) != 2:
                continue
            container_port = fields[0].strip()
            ff = fields[1].split(":")
            if len(ff) != 2:
                continue
            try:
                host_port = int(ff[1])
            except ValueError:
                continue
            if container_port == '5138/tcp':
                update_port = host_port
            elif container_port == "5813/tcp":
                rest_port = host_port
        if update_port is None:
            raise LaunchError("Seamless shareserver websocket update port was not bound")
        if rest_port is None:
            raise LaunchError("Seamless shareserver REST port was not bound")
        instances[instance] = update_port, rest_port, container, service_name, with_status
    finally:
        os.chdir(cwd)
    return instance


async def launch_instance(req):    
    data = await req.post()
    service = data.get("service", None)
    with_status = data.get("with_status", None)
    if with_status == "1":
        with_status = True
    if service is None:
        return web.Response(
            status=400,
            text="Need to specify service name"
        )
    if service not in services:
        return web.Response(
            status=409,
            text="Unknown service"
        )
    try:
        instance = launch(service, with_status)
    except LaunchError as exc:
        return web.Response(
            status=500,
            text=exc.args[0]
        )
    except Exception:
        exc = traceback.format_exc()
        return web.Response(
            status=500,
            text=exc
        )
    else:        
        return instance

async def browser_launch_instance(req):
    result = await launch_instance(req)
    if isinstance(result, int):   # instance
        _, rest_port, _, _, _ = instances[result]
        t = time.time()
        while 1:
            try:
                async with aiohttp.ClientSession(cookies=req.cookies) as client:
                    async with client.get(
                        "{}:{}/".format(rest_server, rest_port)
                    ) as response:
                        if response.status < 400:
                            await asyncio.sleep(2)
                            break
                        if time.time() - t > 10:
                            break
            except aiohttp.client_exceptions.ClientError:
                pass
            await asyncio.sleep(0.5)
        raise web.HTTPFound('/instance/{}/'.format(result))
    else:
        return result

async def kill_instance(req):
    data = await req.post()
    instance = data.get("instance", None)
    if instance is None:
        return web.Response(
            status=400,
            text="Need to specify instance ID"
        )
    try:
        instance = int(instance)
    except ValueError:
        pass
    if instance not in instances:
        return web.Response(
            status=409,
            text="Instance does not exist"
        )
    _, _, container, _, _ = instances.pop(instance)
    if container is not None:
        subprocess.getstatusoutput("docker stop {}".format(container))
    return web.Response(status=200)

async def browser_kill_instance(req):
    response = await kill_instance(req)
    if response.status == 200:
        raise web.HTTPFound('/admin/instance_page',body="Job was successfully killed")
    return response

async def instance_page(req):
    txt = """
<!DOCTYPE html>
<html lang="en" >
<head>
    <meta charset="UTF-8">
    <title>RPBS Seamless server</title>
</head>
<body>
    <h1>RPBS Seamless server</h1>
    <h1>List of instances</h1>
    <table>
    <tr><th>Instance</th><th>Service</th><th></th><th></th><th></th></tr>
    {}
    </table>
</body>
</html>
    """
    kill_form = """<form action="./kill" method="post">
  <input type="hidden" name="instance" value="{}">
  <input type="submit" value="Kill instance">
</form>"""    
    service_txt = ""
    for instance in instances:
        _, _, _, service_name, with_status = instances[instance]
        go_link="../instance/{}/".format(instance)
        cgo_link = "<a href='{}'>Go to instance</a>".format(go_link)
        cstatus_link = ""
        if with_status:
            status_link="../instance/{}/status/".format(instance)
            cstatus_link = "<a href='{}'>Go to status</a>".format(status_link)
        ckill_form = kill_form.format(instance)
        s = "<tr><th>{}</th><th>{}</th><th>{}</th><th>{}</th><th>{}</th></tr>".format(
            instance, service_name, cgo_link, cstatus_link, ckill_form
        )
        service_txt += "    " + s + "\n"
    return web.Response(
        status=200,
        body=txt.format(service_txt),
        content_type='text/html'
    )
async def admin_redirect(req):
    raise web.HTTPFound('/admin/instance_page')

async def main_page(req):
    txt = """
<!DOCTYPE html>
<html lang="en" >
<head>
    <meta charset="UTF-8">
    <title>RPBS Seamless server</title>
</head>
<body>
    <h1>RPBS Seamless server</h1>
    <h1>List of services</h1>    
    <table>
    <tr><th>Service</th><th></th></tr>
    {}
    </table>
</body>
</html>
    """
    form = """<form action="./launch" method="post">
  <input type="hidden" name="service" value="{}">
  <input type="submit" value="Launch instance">
</form>"""    
    form2 = """<form action="./launch" method="post">
  <input type="hidden" name="service" value="{}">
  <input type="hidden" name="with_status" value="1">
  <input type="submit" value="Launch with status monitor">
</form>"""    

    service_txt = ""
    for service_name in services:
        cform = form.format(service_name)
        cform2 = form2.format(service_name)
        s = "<tr><th>{}</th><th>{}</th><th>{}</th></tr>".format(
            service_name, cform, cform2
        )
        service_txt += "    " + s + "\n"
    return web.Response(
        status=200,
        body=txt.format(service_txt),
        content_type='text/html'
    )

async def redirect(req):
    raise web.HTTPFound('/index.html')

app = web.Application()
app.router.add_route('GET','/', redirect)
app.router.add_route('GET','/index.html', main_page)
app.router.add_route('*','/instance/{instance}/{tail:.*}', reverse_proxy)
app.router.add_route('PUT','/connect_instance', connect_instance)
app.router.add_route('POST','/launch_instance', launch_instance)
app.router.add_route('POST','/launch', browser_launch_instance)
app.router.add_route('GET','/admin', admin_redirect)
app.router.add_route('GET','/admin/instance_page', instance_page)
app.router.add_route('POST','/admin/kill_instance', kill_instance)
app.router.add_route('POST','/admin/kill', browser_kill_instance)
web.run_app(app,port=cloudless_port)