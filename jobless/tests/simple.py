import os
os.environ["SEAMLESS_COMMUNION_ID"] = "seamless"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:5533"
from seamless.highlevel import Context

import seamless
seamless.set_ncores(0)
from seamless import communion_server

communion_server.configure_master(
    transformation_job=True,
    transformation_status=True,
)

seamless.database_sink.connect()
seamless.database_cache.connect()
communion_server.start()

ctx = Context()
ctx.a = 10
ctx.a.celltype = "int"

def double_it(a):
    return 2 * a

ctx.tf = double_it
ctx.tf.a = ctx.a
ctx.result = ctx.tf
ctx.result.celltype = "int"
ctx.compute()
print(ctx.result.value)
print(ctx.tf.status)
print(ctx.tf.exception)
print(ctx.tf.get_transformation())

'''
ctx.tf.meta = {"duration" : "short"}
ctx.translate()
ctx.tf.clear_exception()
seamless.set_ncores(1)
ctx.compute()
print(ctx.result.value)
print(ctx.tf.status)
print(ctx.tf.exception)
'''