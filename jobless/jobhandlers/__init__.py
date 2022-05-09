"""
A jobhandler consists of two parts:
- A TransformerPlugin. Currently, there is FileTransformerPluginBase, that is specialized into
  BashTransformerPlugin and BashDockerTransformerPlugin
- A Backend. Currently, there is ShellBashBackend, ShellBashDockerBackend and SlurmBackend for file transformers.

Jobs are submitted by checksum. There is also a job status API, which can return
    a code and a return value. The return value depends on the code:
    -3: Job checksum is unknown (cache miss in the server's checksum to buffer)
        None is returned, i.e. "return -3, None"
    -2: Job input checksums are unknown. None is returned.
    -1: Job is not runnable. None is returned.
    0: Job has exception. Exception is returned as a string, i.e. "return 0, exc"
    1: Job is runnable. None is returned.
    2: Job is running; progress and preliminary checksum are returned, i.e. "return 2, progress, prelim"
    3: Job result is known; job result checksum is returned, i.e. "return 3, job_checksum"

"""

import asyncio
import traceback
from functools import partial
from hashlib import sha3_256

from .util import parse_checksum

class Checksum:
    def __init__(self, value):
        self.value = value

class TransformerPlugin:
    def can_accept_transformation(self, checksum, transformation):
        # To be implemented by backend.
        raise NotImplementedError

    def prepare_transformation(self, checksum, transformation):
        # To be implemented by backend.
        raise NotImplementedError

class Backend:

    def __init__(self,  database_client, *args, **kwargs):
        self.database_client = database_client
        self.transformations = {}
        self.identifiers = {}
        self.results = {}

    def get_status(self, checksum):
        if checksum in self.results:
            if self.results[checksum] is None:
                return 0, "Unknown error when parsing the results"
            return 3, self.results[checksum]

        if checksum in self.transformations:
            fut = self.transformations[checksum]
            if fut.done():
                try:
                    result = fut.result()
                    return 2, None, None   # coro is done, need to calculate checksum of the result
                except CacheMissError:
                    return -2, None
                except Exception as exc:
                    exc_str = traceback.format_exc()
                    if isinstance(exc,SeamlessTransformationError):
                        exc_str = None
                        if len(exc.args):
                            exc_str = exc.args[0]
                        if exc_str is not None:
                            h = SeamlessTransformationError.__module__
                            h += "." + SeamlessTransformationError.__name__
                            if exc_str.startswith(h):
                                exc_str = exc_str[len(h)+1:].lstrip().rstrip("\n")
                    elif isinstance(exc, JoblessRemoteError):
                        e, tb = exc.args
                        exc_str = tb + "\n" + "\n".join(traceback.format_exception_only(type(e), e))
                    return 0, exc_str
            else:
                identifier = self.identifiers[checksum]
                return self.get_job_status(checksum, identifier)
        else:
            return -3, None


    def get_job_status(self, checksum, identifier):
        # To be implemented by backend.
        raise NotImplementedError

    def launch_transformation(self, checksum, transformation, prepared_transformation):
        """ Launches a prepared transformation
        To be implemented by backend.
        Function must return a tuple (awaitable, identifier)
        """
        raise NotImplementedError

    def run_transformation(self, checksum, transformation):
        prepared_transformation = self.prepare_transformation(checksum, transformation)
        awaitable, identifier = self.launch_transformation(checksum, transformation, prepared_transformation)
        future = asyncio.ensure_future(awaitable)
        future.add_done_callback(partial(self.transformation_finished, checksum))
        self.transformations[checksum] = future
        self.identifiers[checksum] = identifier

    def transformation_finished(self, checksum, future):
        try:
            result = future.result()
        except:
            return
        if result is None:
            return        
        try:
            if isinstance(result, Checksum):
                result_checksum = result.value
                result_checksum = parse_checksum(result_checksum, as_bytes=True)
                if result_checksum is None:
                    return
                result_buffer = self.database_client.get_buffer(
                    result_checksum
                )
                if result_buffer is None:
                    raise CacheMissError
            else:
                result_buffer = result
                hash = sha3_256(result_buffer)
                result_checksum = hash.digest()
                self.database_client.set_buffer(
                    result_checksum,
                    result,
                    False
                )
            self.database_client.set_transformation_result(
                checksum,
                result_checksum
            )
            self.results[checksum] = result_checksum.hex()
        except Exception as exc:
            self.results[checksum] = None
            raise exc from None



    def cancel_job(self, checksum, identifier):
        """Stop awaitable. Completely forget job. Doesn't matter if the job actually finished or not
        To be implemented by backend.
        """
        raise NotImplementedError

    def cancel_transformation(self, checksum):
        identifier = self.identifiers.pop(checksum)
        self.transformations.pop(checksum)
        self.cancel_job(checksum, identifier)

    async def wait_for(self, checksum):
        future = asyncio.shield(self.transformations[checksum])
        try:
            await future
        except Exception:
            pass


class CacheMissError(Exception):
    pass

class SeamlessTransformationError(Exception):
    pass

class JoblessRemoteError(Exception):
    pass

from .bash_transformer_plugin import BashTransformerPlugin
from .bashdocker_transformer_plugin import BashDockerTransformerPlugin
from .shell_backend import ShellBashBackend, ShellBashDockerBackend
from .slurm_backend import SlurmBashBackend, SlurmSingularityBackend, SlurmGenericSingularityBackend
from .generic_transformer_plugin import GenericTransformerPlugin, GenericSingularityTransformerPlugin
from .generic_backend import GenericBackend, GenericSingularityBackend