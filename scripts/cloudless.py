from aiohttp import web
import asyncio
import glob, os
import traceback
import random
import subprocess
import time
import threading
from functools import partial
import tempfile
import sys
import re

import reverse_proxy as reverse_proxy_module
import icicle

currdir = os.path.split(os.path.abspath(__file__))[0]  # /scripts

cloudless_port = 3124

INACTIVE_TIMEOUT = 10 * 60

rest_server = "http://localhost"
update_server = "http://localhost"  # still http, not ws!

launch_threads = []

graph_dir = None
instances_dir = None


def _load_services():
    global services
    services = {}
    for f in glob.glob("{}/*.seamless".format(graph_dir)):
        if f.endswith("-webctx.seamless"):
            continue
        service_dir, service_file = os.path.split(f)
        service_name = os.path.splitext(service_file)[0]
        service_status_file = service_name + "-webctx.seamless"
        if not os.path.exists(os.path.join(service_dir, service_status_file)):
            service_status_file = None
        services[service_name] = service_dir, service_file, service_status_file
        print(service_name, service_dir, service_file, service_status_file)


async def load_services(req):
    _data = await req.post()
    try:
        _load_services()
    except Exception:
        exc = traceback.format_exc()
        return web.Response(status=500, text=exc)
    else:
        return web.Response(status=200)


async def browser_load_services(req):
    response = await load_services(req)
    if response.status == 200:
        raise web.HTTPFound("/admin/overview", text="Services reloaded")
    return response


class Instance:
    complete = True
    container = None
    service_name = None
    service_dir = None
    container_logger = None
    custom_status_graph = False
    proxy_websocket = None
    temp_dir = None
    last_request_time = None
    error = False

    def __init__(self, update_port, rest_port):
        self.update_port = update_port
        self.rest_port = rest_port
        self.last_request_time = time.time()


class IncompleteInstance:
    """Class to describe instances that are launching, or where launch failed"""

    complete = False
    service_name = None
    error = False
    error_message = None
    container = None
    creation_time = None
    custom_status_graph = None


instances = {
    # 1: Instance(32876, 32875)
}
proxies = {}


def get_new_instance():
    """Returns a new unused random instance ID"""
    while 1:
        instance = random.choice(range(1000000, 10000000))
        if instance not in instances:
            break
    return instance


def launch(instance, service_name, existing_graph=None):
    print("LAUNCHING", instance)
    ininst = instances[instance]
    service_dir, service_file, service_status_file = services[service_name]
    service_dir = os.path.abspath(service_dir)
    temp_dir = tempfile.TemporaryDirectory()
    if existing_graph is not None:
        graph = existing_graph
    else:
        with open(os.path.join(service_dir, service_file)) as f:
            graph = f.read()
    status_graph_arg = "'$SEAMLESSDIR/graphs/status-visualization.seamless'"
    if service_status_file is not None:
        status_graph_arg = "status-graph.seamless"
        with open(os.path.join(service_dir, service_status_file)) as f:
            status_graph = f.read()
        with open(os.path.join(temp_dir.name, status_graph_arg), "w") as f:
            f.write(status_graph)
    with open(os.path.join(temp_dir.name, "graph.seamless"), "w") as f:
        f.write(graph)

    with open(icicle.get_graph_output_file(instance, service_name), "w") as f:
        f.write(graph)
    launch_command = "seamless-serve-graph-safe --delegate 4"
    container = "cloudless-{}".format(instance)
    ininst.container = container
    cmd = """
    export SEAMLESS_DOCKER_PUBLISH_SHARESERVER_PORTS='--detach --expose 5813 --expose 5138 -P'
    cd {} && \
    {} graph.seamless --status-graph {}
    docker port {}
    """.format(
        temp_dir.name, launch_command, status_graph_arg, container
    )

    env = os.environ.copy()
    env["SEAMLESS_DOCKER_CONTAINER_NAME"] = container
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, env=env
    )
    err = proc.returncode
    output = ""
    try:
        output += proc.stdout.decode()
    except Exception:
        pass
    try:
        output += "Standard error\n\n" + proc.stderr.decode()
    except Exception:
        pass
    if err:
        msg = "Launch output:\n{}\n{}".format(err, output)
        ininst.error = True
        ininst.error_message = msg
        return
    else:
        logfile = "{}/{}.log".format(instances_dir, container)
        cmd = "cd {} && docker attach {} > {} 2>&1"
        container_logger = subprocess.Popen(
            cmd.format(service_dir, container, logfile), shell=True
        )
        try:
            container_logger.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        if container_logger.returncode is not None:
            output0 = output.strip()
            output = (
                "***Docker return code***\n" + str(container_logger.returncode) + "\n\n"
            )
            if len(output0):
                output += "***Docker launch output***\n" + output0 + "\n\n"
            logfile2 = os.path.join(service_dir, logfile)
            if os.path.exists(logfile2):
                output += "***Container logfile***\n"
                logcontent = open(logfile2).read().strip()
                if (
                    logcontent
                    == "You cannot attach to a stopped container, start it first"
                    or not len(logcontent)
                ):
                    err2, logcontent2 = subprocess.getstatusoutput(
                        "cd {} && docker logs {}".format(service_dir, container)
                    )
                    if err2 == 0:
                        logcontent = logcontent2
                output += logcontent + "\n"
            subprocess.getstatusoutput("docker rm {0}".format(container))
            ininst.error = True
            ininst.error_message = output
            return
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
        if container_port == "5138/tcp":
            update_port = host_port
        elif container_port == "5813/tcp":
            rest_port = host_port
    if update_port is None:
        msg = "Seamless shareserver websocket update port was not bound"
        ininst.error = True
        ininst.error_message = msg
        return
    if rest_port is None:
        msg = "Seamless shareserver REST port was not bound"
        ininst.error = True
        ininst.error_message = msg
        return
    inst = Instance(update_port, rest_port)
    inst.container = container
    inst.service_dir = service_dir
    inst.service_name = service_name
    status_file = services.get(service_name, ("", "", None))[2]
    custom_status_graph = status_file is not None
    inst.custom_status_graph = custom_status_graph
    inst.container_logger = container_logger
    inst.temp_dir = temp_dir
    instances[instance] = inst
    print("LAUNCHED", instance)
    return instance


def launch_instance(service, *, instance=None, existing_graph=None):
    launch_threads[:] = [t for t in launch_threads if t.is_alive()]
    if instance is None:
        instance = get_new_instance()
    else:
        assert existing_graph is not None
    ininst = IncompleteInstance()
    ininst.creation_time = time.time()
    ininst.service_name = service
    status_file = services.get(service, ("", "", None))[2]
    custom_status_graph = status_file is not None
    ininst.custom_status_graph = custom_status_graph
    instances[instance] = ininst
    kill_inactive_instances(INACTIVE_TIMEOUT)
    t = threading.Thread(
        target=launch,
        args=(instance, service),
        kwargs={"existing_graph": existing_graph},
    )
    t.name = instance
    launch_threads.append(t)
    t.start()
    icicle.snoop(instance, service, 2)
    return instance


async def browser_launch_instance(req):
    data = await req.post()
    service = data.get("service", None)
    if service is None:
        return web.Response(status=400, text="Need to specify service name")
    if service not in services:
        return web.Response(status=409, text="Unknown service")

    try:
        instance = launch_instance(service)
    except Exception:
        exc = traceback.format_exc()
        return web.Response(status=500, text=exc)
    raise web.HTTPFound("/instance/{}/".format(instance))


def stop_container(inst):
    container = inst.container
    cwd = os.getcwd()
    if container is not None:
        if inst.service_dir:
            os.chdir(inst.service_dir)
        subprocess.getstatusoutput(
            "docker kill --signal=SIGINT {0} && docker rm {0}".format(container)
        )
        subprocess.getstatusoutput(
            "docker inspect {0} && docker kill --signal=SIGHUP {0} && docker rm {0}".format(
                container
            )
        )
        subprocess.getstatusoutput(
            "docker inspect {0} && docker stop {0} && docker rm {0}".format(container)
        )
        if inst.container_logger:
            try:
                inst.container_logger.communicate(timeout=5)
            except:
                traceback.print_exc()
        if inst.service_dir:
            os.system("rm -f {}/{}.log".format(instances_dir, container))
            os.chdir(cwd)


async def kill_instance(req):
    data = await req.post()
    instance = data.get("instance", None)
    if instance is None:
        return web.Response(status=400, text="Need to specify instance ID")
    try:
        instance = int(instance)
    except ValueError:
        pass
    if instance not in instances:
        return web.Response(status=409, text="Instance does not exist")
    inst = instances.pop(instance)
    icicle.unsnoop(instance)
    stop_container(inst)
    return web.Response(status=200)


async def browser_kill_instance(req):
    response = await kill_instance(req)
    if response.status == 200:
        raise web.HTTPFound("/admin/overview", text="Job was successfully killed")
    return response


async def admin_overview(req):
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
    <br>
    <form action="./load_services" method="post">
        <input type="submit" value="Reload service list">
    </form>
    <br>
    <h1>List of instances</h1>
    <table>
    <tr><th>Instance</th><th>Service</th><th></th><th></th><th></th></tr>
    {}
    </table>
    <h1>List of instances on ice</h1>
    <table>
    <tr><th>Instance</th><th>Service</th><th></th><th></th><th></th></tr>
    {}
    </table>
</body>
</html>
    """

    launch_form = """<form action="../launch" method="post">
  <input type="hidden" name="service" value="{}">
  <input type="submit" value="Launch instance">
</form>"""

    service_txt = ""
    for service_name in services:
        cform = launch_form.format(service_name)
        s = "<tr><th>{}</th><th>{}</th></tr>".format(service_name, cform)
        service_txt += "    " + s + "\n"

    kill_form = """<form action="./kill" method="post">
  <input type="hidden" name="instance" value="{}">
  <input type="submit" value="{}">
</form>"""
    instance_txt = ""
    for instance in instances:
        inst = instances[instance]
        service_name = inst.service_name
        if isinstance(inst, IncompleteInstance):
            container = True
        else:
            container = inst.container
        go_link = "../instance/{}/".format(instance)
        cgo_link = "<a href='{}'>Go to instance</a>".format(go_link)
        status_link = "../instance/{}/status/".format(instance)
        if inst.custom_status_graph:
            status_link += "status.html"
        cstatus_link = "<a href='{}'>Go to status</a>".format(status_link)
        msg = "Kill instance" if container else "Disconnect from instance"
        ckill_form = kill_form.format(instance, msg)
        s = "<tr><th>{}</th><th>{}</th><th>{}</th><th>{}</th><th>{}</th></tr>".format(
            instance, service_name, cgo_link, cstatus_link, ckill_form
        )
        instance_txt += "    " + s + "\n"
    ice_instance_txt = ""
    for filename in sorted(glob.glob("{}/*-*.seamless".format(instances_dir))):
        instance = None
        filename2 = os.path.split(filename)[1]
        try:
            service_name, instance = re.match("(.*)-(.*)\.seamless", filename2).groups()
            instance = int(instance)
        except Exception:
            pass
        if not isinstance(instance, int):
            continue
        if instance in instances:
            continue
        go_link = "../instance/{}/".format(instance)
        cgo_link = "<a href='{}'>Go to instance</a>".format(go_link)
        status_link = "../instance/{}/status/".format(instance)
        status_file = services.get(service_name, ("", "", None))[2]
        custom_status_graph = status_file is not None
        if custom_status_graph:
            status_link += "status.html"
        cstatus_link = "<a href='{}'>Go to status</a>".format(status_link)
        s = "<tr><th>{}</th><th>{}</th><th>{}</th><th>{}</th></tr>".format(
            instance, service_name, cgo_link, cstatus_link
        )
        ice_instance_txt += "    " + s + "\n"

    return web.Response(
        status=200,
        body=txt.format(service_txt, instance_txt, ice_instance_txt),
        content_type="text/html",
    )


async def admin_redirect(req):
    raise web.HTTPFound("/admin/overview")


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

    service_txt = ""
    for service_name in services:
        cform = form.format(service_name)
        s = "<tr><th>{}</th><th>{}</th></tr>".format(service_name, cform)
        service_txt += "    " + s + "\n"
    return web.Response(
        status=200, body=txt.format(service_txt), content_type="text/html"
    )


async def redirect(req):
    raise web.HTTPFound("/index.html")


def kill_inactive_instances(timeout):
    # timeout in secs
    t = time.time()
    print(t)
    for instance_name, inst in list(instances.items()):
        try:
            if isinstance(inst, IncompleteInstance):
                if inst.container is not None and inst.creation_time + timeout < t:
                    instances.pop(instance_name)
                    stop_container(inst)
                    print("CANCEL", instance_name)
                continue
            if inst.container is not None and inst.last_request_time + timeout < t:
                instances.pop(instance_name)
                icicle.unsnoop(instance_name)
                stop_container(inst)
                print("KILL", instance_name)
        except Exception:
            traceback.print_exc()


reverse_proxy_module.launch_instance = launch_instance

if __name__ == "__main__":

    loop = asyncio.get_event_loop()

    graph_dir = sys.argv[1]
    assert os.path.isdir(graph_dir)

    instances_dir = sys.argv[2]
    assert os.path.isdir(instances_dir)

    host = sys.argv[3]

    _load_services()
    icicle.rest_server = rest_server
    icicle.instances = instances
    icicle.currdir = currdir
    icicle.instances_dir = instances_dir

    with_communion = False

    def read_environ_flag(varname):
        flag = os.environ.get(varname)
        if flag is None or flag == "":
            return False
        try:
            flag = int(flag)
            if flag == 0:
                return False
            return True
        except Exception:
            return True

    app = web.Application()
    app.router.add_route("GET", "/", redirect)
    app.router.add_route("GET", "/index.html", main_page)
    rp = partial(
        reverse_proxy_module.reverse_proxy,
        instances=instances,
        rest_server=rest_server,
        update_server=update_server,
    )
    app.router.add_route("*", "/instance/{instance}/{tail:.*}", rp)

    app.router.add_route("POST", "/launch", browser_launch_instance)
    app.router.add_route("GET", "/admin", admin_redirect)
    app.router.add_route("GET", "/admin/overview", admin_overview)
    app.router.add_route("POST", "/admin/kill_instance", kill_instance)
    app.router.add_route("POST", "/admin/load_services", browser_load_services)
    app.router.add_route("POST", "/admin/kill", browser_kill_instance)

    async def on_shutdown(_app):
        print("Shutting down...")
        shutdown_time = time.time() + 20
        for t in launch_threads:
            if t.is_alive():
                print("Awaiting launch thread", t.name)
                timeout = shutdown_time - time.time()
                if timeout < 0.2:
                    timeout = 0.2
                t.join(timeout=timeout)
        for instance, inst in instances.items():
            if not inst.complete:
                continue
            print("Killing instance", instance)
            try:
                icicle.unsnoop(instance)
                stop_container(inst)
            except Exception:
                traceback.print_exc()
        while len(icicle.dead_snoopers):
            await icicle.dead_snoopers[0].runner

    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host=host, port=cloudless_port)
