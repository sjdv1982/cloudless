from . import Backend, SeamlessTransformationError, JoblessRemoteError

import asyncio
import os, tempfile, shutil
import psutil
import json
import subprocess, tarfile
from functools import partial
import numpy as np
from io import BytesIO

import multiprocessing as mp
import traceback

########################################
# From https://stackoverflow.com/questions/19924104/python-multiprocessing-handling-child-errors-in-parent

class Process(mp.Process):
    def __init__(self, *args, **kwargs):
        mp.Process.__init__(self, *args, **kwargs)
        self._pconn, self._cconn = mp.Pipe()
        self._exception = None

    def run(self):
        try:
            mp.Process.run(self)
            self._cconn.send(None)
        except Exception as e:
            tb = traceback.format_exc()
            self._cconn.send((e, tb))

    @property
    def exception(self):
        if self._pconn.poll():
            self._exception = self._pconn.recv()
        return self._exception

########################################

PROCESS = None
def kill_children():
    process = PROCESS
    if process is None:
        return
    children = []
    try:
        children = psutil.Process(process.pid).children(recursive=True)
    except:
        pass
    for child in children:
        try:
            child.kill()
        except:
            pass

class ShellBackend(Backend):
    support_symlinks = True
    def __init__(self, *args, executor, **kwargs):
        self.executor = executor
        self.coros = {}
        super().__init__(*args, **kwargs)

    def get_job_status(self, checksum, identifier):
        return 2, None, None

    async def run(self, checksum, transformation, prepared_transformation, tempdir, env):
        """Return awaitable. To be implemented by subclass"""
        raise NotImplementedError

    def _run(self, checksum, transformation, prepared_transformation):
        from .file_transformer_plugin import write_files
        global PROCESS
        PROCESS = None
        old_cwd = os.getcwd()
        tempdir = tempfile.mkdtemp(prefix="jobless-")
        try:
            os.chdir(tempdir)
            env = {}
            write_files(prepared_transformation, env, self.support_symlinks)
            return self.run(checksum, transformation, prepared_transformation, tempdir, env)
        finally:
            kill_children()
            os.chdir(old_cwd)
            shutil.rmtree(tempdir, ignore_errors=True)


    def launch_transformation(self, checksum, transformation, prepared_transformation):
        prepared_transformation = prepared_transformation.copy()
        for key in prepared_transformation:
            filename, value, env_value = prepared_transformation[key]
            if filename is None:
                continue
            prepared_transformation[key] = os.path.abspath(os.path.expanduser(filename)), value, env_value

        queue = mp.Queue()

        def func(queue):
            result = self._run(checksum, transformation, prepared_transformation)
            queue.put(result)

        def func2():
            try:
                p = Process(target=func, args=(queue,))
                p.start()
                p.join()
                if p.exception:
                    exc, tb = p.exception
                    if isinstance(exc, SeamlessTransformationError):
                        raise exc
                    else:
                        raise JoblessRemoteError(exc, tb)
                else:
                    result = queue.get()
                    return result
            finally:
                self.coros.pop(checksum, None)

        coro = asyncio.get_event_loop().run_in_executor(self.executor, func2)
        self.coros[checksum] = coro
        return coro, None


    def cancel_job(self, checksum, identifier):
        if checksum in self.coros:
            coro = self.coros.pop(checksum)
            coro.cancel()



def read_data(data):
    try:
        npdata = BytesIO(data)
        np.load(npdata)
        return data
    except (ValueError, OSError):
        try:
            try:
                sdata = data.decode()
            except Exception:
                arr = np.frombuffer(data, dtype=np.uint8)
                return arr.tobytes()
            try:
                result = json.loads(sdata)
            except:
                result = sdata
            return (json.dumps(result) + "\n").encode()
        except ValueError:
            return data

def execute_local(bashcode, env, resultfile):
    global PROCESS
    try:
        bash_header = """set -u -e
trap 'jobs -p | xargs -r kill' EXIT
"""
        bashcode2 = bash_header + bashcode
        process = subprocess.run(
            bashcode2, capture_output=True, shell=True, check=True,
            executable='/bin/bash',
            env=env
        )
        PROCESS = process
    except subprocess.CalledProcessError as exc:
        stdout = exc.stdout
        try:
            stdout = stdout.decode()
        except:
            pass
        stderr = exc.stderr
        try:
            stderr = stderr.decode()
        except:
            pass
        raise SeamlessTransformationError("""
Bash transformer exception
==========================

*************************************************
* Command
*************************************************
{}
*************************************************

*************************************************
* Standard output
*************************************************
{}
*************************************************

*************************************************
* Standard error
*************************************************
{}
*************************************************
""".format(bashcode, stdout, stderr)) from None
    if not os.path.exists(resultfile):
        msg = """
Bash transformer exception
==========================

*************************************************
* Command
*************************************************
{}
*************************************************
Error: Result file {} does not exist
""".format(bashcode, resultfile)
        try:
            stdout = process.stdout.decode()
            if len(stdout):
                msg += """*************************************************
* Standard output
*************************************************
{}
*************************************************
""".format(stdout)
            stderr = process.stderr.decode()
            if len(stderr):
                msg += """*************************************************
* Standard error
*************************************************
{}
*************************************************
""".format(stderr)

        except:
            pass

        raise SeamlessTransformationError(msg)
    else:
        stdout = process.stdout
        try:
            stdout = stdout.decode()
        except Exception:
            pass

        stderr = process.stderr
        try:
            stderr = stderr.decode()
        except Exception:
            pass
        return parse_resultfile(resultfile)


def execute_docker(docker_command, docker_image, tempdir, env, resultfile):
    """Ignore docker_options"""
    from requests.exceptions import ConnectionError
    from urllib3.exceptions import ProtocolError
    import docker as docker_module

    docker_client = docker_module.from_env()
    volumes, options = {}, {}
    volumes[tempdir] = {"bind": "/run", "mode": "rw"}
    options["working_dir"] = "/run"
    options["volumes"] = volumes
    options["environment"] = env
    with open("DOCKER-COMMAND","w") as f:
        bash_header = """set -u -e
""" # don't add "trap 'jobs -p | xargs -r kill' EXIT" as it gives serious problems

        f.write(bash_header)
        f.write(docker_command)
    full_docker_command = "bash DOCKER-COMMAND"
    try:
        try:
            _creating_container = True
            container = docker_client.containers.create(
                docker_image,
                full_docker_command,
                **options
            )
        finally:
            _creating_container = False
        try:
            container.start()
            exit_status = container.wait()['StatusCode']

            stdout = container.logs(stdout=True, stderr=False)
            try:
                stdout = stdout.decode()
            except:
                pass
            stderr = container.logs(stdout=False, stderr=True)
            try:
                stderr = stderr.decode()
            except:
                pass

            if exit_status != 0:
                raise SeamlessTransformationError("""
Docker transformer exception
============================

*************************************************
* Command
*************************************************
{}
*************************************************
Exit code: {}
*************************************************
* Standard output
*************************************************
{}
*************************************************
* Standard error
*************************************************
{}
*************************************************
""".format(docker_command, exit_status, stdout, stderr)) from None
        except ConnectionError as exc:
            msg = "Unknown connection error"
            if len(exc.args) == 1:
                exc2 = exc.args[0]
                if isinstance(exc2, ProtocolError):
                    if len(exc2.args) == 2:
                        a, exc3 = exc2.args
                        msg = "Docker gave an error: {}: {}".format(a, exc3)
                        if a.startswith("Connection aborted"):
                            if isinstance(exc3, FileNotFoundError):
                                if len(exc3.args) == 2:
                                    a1, a2 = exc3.args
                                    if a1 == 2 or a2 == "No such file or directory":
                                        msg = "Cannot connect to Docker; did you expose the Docker socket to Seamless?"
            raise SeamlessTransformationError(msg) from None

        if not os.path.exists(resultfile):
            msg = """
Docker transformer exception
============================

*************************************************
* Command
*************************************************
{}
*************************************************
Error: Result file RESULT does not exist
""".format(docker_command)
            try:
                stdout = container.logs(stdout=True, stderr=False)
                try:
                    stdout = stdout.decode()
                except Exception:
                    pass
                if len(stdout):
                    msg += """*************************************************
* Standard output
*************************************************
{}
*************************************************
""".format(stdout)
                stderr = container.logs(stdout=False, stderr=True)
                try:
                    stderr = stderr.decode()
                except Exception:
                    pass
                if len(stderr):
                    msg += """*************************************************
* Standard error
*************************************************
{}
*************************************************
""".format(stderr)
            except Exception:
                pass

            raise SeamlessTransformationError(msg)
        else:
            if len(stdout):
                print(stdout)
            if len(stderr):
                print(stderr, file=sys.stderr)
        return parse_resultfile(resultfile)

    finally:
        try:
            container.remove()
        except:
            pass


def parse_resultfile(resultfile):
    try:
        tar = tarfile.open(resultfile)
        result = {}
        for member in tar.getnames():
            data = tar.extractfile(member).read()
            result[member] = data.decode()
        return json.dumps(result).encode()
    except (ValueError, tarfile.CompressionError, tarfile.ReadError):
        with open(resultfile, "rb") as f:
            resultdata = f.read()
        result = read_data(resultdata)
    return result


####################################################################################

class ShellBashBackend(ShellBackend):
    support_symlinks = True
    def run(self, checksum, transformation, prepared_transformation, tempdir, env):
        bashcode = prepared_transformation["bashcode"][1]
        resultfile = "RESULT"
        try:
            return execute_local(bashcode, env, resultfile)
        except SeamlessTransformationError as exc:
            raise exc from None

class ShellDockerBackend(ShellBackend):
    support_symlinks = False

    def __init__(self, *args, **kwargs):
        import docker as docker_module
        from requests.exceptions import ConnectionError
        super().__init__(*args, **kwargs)

    def run(self, checksum, transformation, prepared_transformation, tempdir, env):
        docker_command = prepared_transformation["docker_command"][1]
        docker_image = prepared_transformation["docker_image"][1]
        resultfile = "RESULT"
        try:
            return execute_docker(docker_command, docker_image, tempdir, env, resultfile)
        except SeamlessTransformationError as exc:
            raise exc from None
