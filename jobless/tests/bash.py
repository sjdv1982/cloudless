
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

ctx = Context()
ctx.code = "head -$lines testdata > RESULT"
ctx.code.celltype = "text"
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "bash"
ctx.tf.testdata = "a \nb \nc \nd \ne \nf \n"
ctx.tf.lines = 3
ctx.tf.code = ctx.code
ctx.result = ctx.tf
ctx.result.celltype = "mixed"
ctx.translate(force=True)
ctx.compute()
print(ctx.result.value)
ctx.code = "head -3 testdata > firstdata; tar hczf RESULT testdata firstdata"
ctx.compute()
print(ctx.result.value)
ctx.code = "python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'; cat test.npy > RESULT"
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.status)
print(ctx.tf.exception)