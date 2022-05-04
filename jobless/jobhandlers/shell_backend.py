from . import Backend, SeamlessTransformationError, JoblessRemoteError

import asyncio
import sys, os, tempfile, shutil
import psutil
import json
import subprocess, tarfile
from functools import partial
import numpy as np
from io import BytesIO

import multiprocessing as mp
import traceback


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
    JOB_TEMPDIR = None
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
        tempdir = tempfile.mkdtemp(prefix="jobless-", dir=self.JOB_TEMPDIR)
        print("Running shell job in {}".format(tempdir), file=sys.stderr)
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
            if key in ("__checksum__", "__env__"):
                continue
            filename, value, env_value = prepared_transformation[key]
            if filename is None:
                continue
            prepared_transformation[key] = os.path.abspath(os.path.expanduser(filename)), value, env_value
        return launch(
            checksum, transformation, prepared_transformation, 
            self._run, self.coros, self.executor
        )




    def cancel_job(self, checksum, identifier):
        if checksum in self.coros:
            coro = self.coros.pop(checksum)
            task = asyncio.ensure_future(coro)
            task.cancel()


def launch(checksum, transformation, prepared_transformation, runner, coros, executor):
    def func(queue):
        try:
            result = runner(checksum, transformation, prepared_transformation)
            queue.put((False, result))
        except Exception as exc:
            tb = traceback.format_exc()
            queue.put((True, (exc, tb)))

    def func2():
        try:
            with mp.Manager() as manager:
                queue = manager.Queue()
                p = mp.Process(target=func, args=(queue,))
                p.start()
                p.join()
                has_error, payload = queue.get()
                if has_error:
                    exc, tb = payload
                    if isinstance(exc, SeamlessTransformationError):
                        raise exc
                    else:
                        raise JoblessRemoteError(exc, tb)
                else:
                    result = payload
                    return result
        finally:
            coros.pop(checksum, None)

    coro = asyncio.get_event_loop().run_in_executor(executor, func2)
    coros[checksum] = asyncio.ensure_future(coro)
    return coro, None

def get_docker_command_and_image(prepared_transformation):
    if "bashcode" in prepared_transformation:
        docker_command = prepared_transformation["bashcode"][1]
    else:
        docker_command = prepared_transformation["docker_command"][1]
        if isinstance(docker_command, bytes):
            docker_command = docker_command.decode()
    if "docker_image_" in prepared_transformation:
        docker_image = prepared_transformation["docker_image_"][1]
        if isinstance(docker_image, bytes):
            docker_image = docker_image.decode()
    else:
        docker_image = prepared_transformation.get("__env__", {}).get("docker", {}).get("name")
    return docker_command, docker_image

def read_data(data):
    try:
        npdata = BytesIO(data)
        return np.load(npdata)
    except (ValueError, OSError):
        try:
            try:
                sdata = data.decode()
            except Exception:
                return np.frombuffer(data, dtype=np.uint8)
            return json.loads(sdata)
        except ValueError:
            return sdata

def execute_local(bashcode, env, resultfile):
    global PROCESS
    try:
        bash_header = """set -u -e
""" # don't add "trap 'jobs -p | xargs -r kill' EXIT" as it gives serious problems

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

Error: Result file {} does not exist

*************************************************
* Command
*************************************************
{}
*************************************************

""".format(resultfile, bashcode)
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
        trap 'chmod -R 777 /run' EXIT
""" # don't add "trap 'jobs -p | xargs -r kill' EXIT" as it gives serious problems

        f.write(bash_header)
        f.write(docker_command)
        f.write("\nchmod -R 777 /run")
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

Exit code: {}

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
* Standard error
*************************************************
{}
*************************************************
""".format(exit_status, docker_command, stdout, stderr)) from None
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

Error: Result file RESULT does not exist

*************************************************
* Command
*************************************************
{}
*************************************************
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
                print(stdout[:1000])
            if len(stderr):
                print(stderr[:1000], file=sys.stderr)
        return parse_resultfile(resultfile)

    finally:
        try:
            container.remove()
        except:
            pass


def parse_resultfile(resultfile):
    if os.path.isdir(resultfile):
        result0 = {}
        for dirpath, _, filenames in os.walk(resultfile):
            for filename in filenames:
                full_filename = os.path.join(dirpath, filename)
                assert full_filename.startswith(resultfile + "/")
                member = full_filename[len(resultfile) + 1:]
                data = open(full_filename, "rb").read()
                rdata = read_data(data)
                result0[member] = rdata
        result = {}
        for k in sorted(result0.keys()):
            result[k] = result0[k]
            del result0[k]
    else:
        try:
            tar = tarfile.open(resultfile)
            result = {}
            for member in tar.getnames():
                data = tar.extractfile(member).read()
                result[member] = read_data(data)
        except (ValueError, tarfile.CompressionError, tarfile.ReadError):
            with open(resultfile, "rb") as f:
                resultdata = f.read()
            result = read_data(resultdata)
    return serialize(result)


####################################################################################

class ShellBashBackend(ShellBackend):
    support_symlinks = True
    def run(self, checksum, transformation, prepared_transformation, tempdir, env):
        msg = "Submit shell bash job, checksum {}"
        print(msg.format(prepared_transformation["__checksum__"]), file=sys.stderr)
        bashcode = prepared_transformation["bashcode"][1]
        resultfile = "RESULT"
        try:
            return execute_local(bashcode, env, resultfile)
        except SeamlessTransformationError as exc:
            raise exc from None

class ShellBashDockerBackend(ShellBackend):
    support_symlinks = False

    def __init__(self, *args, **kwargs):
        import docker as docker_module
        from requests.exceptions import ConnectionError
        super().__init__(*args, **kwargs)

    def run(self, checksum, transformation, prepared_transformation, tempdir, env):
        docker_command, docker_image = get_docker_command_and_image(
            prepared_transformation
        )
        msg = "Submit shell docker job, checksum {}, image {}"
        print(
            msg.format(
                prepared_transformation["__checksum__"],
                docker_image
            ),
            file=sys.stderr
        )
        resultfile = "RESULT"
        try:
            return execute_docker(docker_command, docker_image, tempdir, env, resultfile)
        except SeamlessTransformationError as exc:
            raise exc from None

from silk.mixed.io.serialization import serialize