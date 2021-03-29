"""
Module to allow on-the-fly reconstruction of an instance from its graph
This is done using two things:
- To snoop running instances for their graph value (using the status graph) and save it to disk
- To return the graph value on the fly
"""
import asyncio
import aiohttp
import os
import glob

rest_server = None # to be set by importing module
instances = None # to be set by importing module
instances = None # to be set by importing module
currdir = None # to be set by importing module

def get_graph_output_file(instance, service_name):
    fname = "../instances/{}-{}.seamless".format(service_name, instance)
    fname2 = os.path.join(currdir, fname)
    return fname2

def get_graph(instance):
    pat = "../instances/*-{}.seamless".format(instance)
    pat2 = os.path.join(currdir, pat)
    filenames = sorted(glob.glob(pat2))
    if len(filenames):
        filename = filenames[0]
        tail = os.path.split(filename)[1]
        service = tail[:tail.rindex("-")]
        with open(filename) as f:
            graph = f.read()
        return graph, service

class Snooper:
    def __init__(self, instance, service_name, delay):
        self.instance = instance
        self.service_name = service_name
        self.delay = delay
        self.running = True
        self.runner = asyncio.ensure_future(self._run())
        self.graph = None

    async def _run(self):
        url = None
        async with aiohttp.ClientSession() as session:
            while self.running:
                await asyncio.sleep(self.delay)
                if not self.running:
                    break
                if url is None:
                    inst = instances[self.instance]
                    if not inst.complete:
                        continue
                    port = inst.rest_port
                    url = "{}:{}/status/graph".format(rest_server, port)
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    graph = await resp.text()
                if graph != self.graph:
                    self.graph = graph
                    fname = get_graph_output_file(self.instance, self.service_name)
                    print("WRITE", self.instance)
                    with open(fname, "w") as f:
                        f.write(graph)



snoopers = {}
def snoop(instance, service_name, delay):
    assert instance not in snoopers
    snooper = Snooper(instance, service_name, delay)
    snoopers[instance] = snooper

def unsnoop(instance):
    if instance not in snoopers:
        return
    snooper = snoopers.pop(instance)
    snooper.running = False
