import os
os.environ["SEAMLESS_COMMUNION_ID"] = "jobmaster"
k="SEAMLESS_COMMUNION_INCOMING"
if k not in os.environ:
    raise Exception("environment variable {} must be set, e.g. 'node1:8602,node2:8603' ".format(k))

import seamless
seamless.set_ncores(0)
from seamless import communion_server

params = {}
db_host = os.environ.get("SEAMLESS_DATABASE_IP")
if db_host is not None:
    params["host"] = db_host
db_port = os.environ.get("SEAMLESS_DATABASE_PORT")
if db_port is not None:
    params["port"] = db_port
seamless.database_sink.connect(**params)
seamless.database_cache.connect(**params)

communion_server.configure_master(
    transformation_job=True,
    transformation_status=True,
)

import asyncio; asyncio.get_event_loop().run_until_complete(asyncio.sleep(2))

import math
from seamless.highlevel import Context, Cell
import json
ctx = Context()
ctx.pi = math.pi
ctx.doubleit = lambda a: 2 * a
ctx.doubleit.a = ctx.pi
ctx.twopi = ctx.doubleit
ctx.translate()

ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)

ctx.doubleit.code = lambda a: 42
ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)

ctx.translate(force=True)
ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)
print()

ctx.doubleit.code = lambda a: 2 * a
ctx.compute()
print(ctx.pi.value)
print(ctx.twopi.value)

print(ctx.doubleit.exception)