
import os
os.environ["SEAMLESS_COMMUNION_ID"] = "seamless"
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
ctx.code = "head -$lines testdata > RESULT"
ctx.code.celltype = "text"
ctx.tf = lambda lines, testdata: None
ctx.tf.language = "bash"
ctx.tf.docker_image = "ubuntu"
ctx.tf.testdata = "a \nb \nc \nd \ne \nf \n"
ctx.tf.lines = 3
ctx.tf.code = ctx.code
ctx.result = ctx.tf
ctx.result.celltype = "mixed"
ctx.translate()
ctx.compute()
print(ctx.result.value)
print(ctx.tf.status)
print(ctx.tf.exception)
ctx.code = "head -3 testdata > firstdata; mkdir RESULT; cp testdata firstdata RESULT"
ctx.compute()
print(ctx.result.value)
ctx.tf.docker_image = "rpbs/seamless"
ctx.code = "python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'; cat test.npy > RESULT"
ctx.compute()
print(ctx.tf.result.value)
print(ctx.tf.status)
print(ctx.tf.exception)
ctx.code = """
python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'
echo 'hello' > test.txt
mkdir RESULT
cp test.npy test.txt RESULT
"""
ctx.result = ctx.tf
ctx.result.celltype = "structured"
ctx.result_npy = ctx.result["test.npy"]
ctx.result_txt = ctx.result["test.txt"]
ctx.compute()
print("")
print(ctx.result.value)
print(ctx.result_npy.value)
print(ctx.result_txt.value)
print(ctx.tf.status)