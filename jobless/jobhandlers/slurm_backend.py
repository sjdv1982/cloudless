from . import Backend, SeamlessTransformationError, JoblessRemoteError

import asyncio
import sys, os, tempfile, shutil
import psutil
import json
import subprocess, tarfile
from functools import partial
import numpy as np
from io import BytesIO
import traceback

class SlurmBackend(Backend):
    support_symlinks = True
    STATUS_POLLING_INTERVAL = 2.0   # TODO: conf file
    SLURM_EXTRA_HEADER = None # TODO: conf file
    JOB_TEMPDIR = None
    RESULT_FILENAME = "RESULT"  # set to None to read no result file

    def __init__(self, *args, executor, **kwargs):
        self.executor = executor
        self.coros = {}
        self.jobs = set()
        super().__init__(*args, **kwargs)

    def prepare_slurm_env(self, env):
        pass

    def get_job_status(self, checksum, identifier):
        # TODO: invoke squeue in real time (will be a few sec more up-to-date)
        return 2, None, None


    def get_code(self, transformation, prepared_transformation):
        """To be implemented by subclass"""
        raise NotImplementedError

    def launch_transformation(self, checksum, transformation, prepared_transformation):
        from .file_transformer_plugin import write_files

        prepared_transformation = prepared_transformation.copy()
        if not prepared_transformation.get("__generic__"):
            for key in prepared_transformation:
                if key in ("__checksum__", "__env__"):
                    continue
                filename, value, env_value = prepared_transformation[key]
                if filename is None:
                    continue
                prepared_transformation[key] = os.path.abspath(os.path.expanduser(filename)), value, env_value

        jobname = "seamless-" + checksum.hex()
        code = self.get_code(transformation, prepared_transformation)

        old_cwd = os.getcwd()
        tempdir = tempfile.mkdtemp(prefix="jobless-",dir=self.JOB_TEMPDIR)
        print("Running slurm job in {}".format(tempdir), file=sys.stderr)
        try:
            os.chdir(tempdir)
            env = {}
            write_files(prepared_transformation, env, self.support_symlinks)
            jobid = self.submit_job(jobname, self.SLURM_EXTRA_HEADER, env, code, prepared_transformation)
        except subprocess.CalledProcessError as exc:
            error_message = str(exc)
            if len(exc.stderr.strip()):
                error_message += "\nError message: {}".format(exc.stderr.strip().decode())
            async def get_error():
                raise SeamlessTransformationError(error_message)
            coro = get_error()
            jobid = None
            os.chdir(old_cwd)
            shutil.rmtree(tempdir, ignore_errors=True)
        finally:
            os.chdir(old_cwd)

        if jobid is not None:
            coro = self.await_job(
                checksum,
                jobname, jobid, code, self.TF_TYPE, tempdir, 
                self.STATUS_POLLING_INTERVAL
            )
            self.jobs.add(jobid)

        coro = asyncio.ensure_future(coro)
        self.coros[checksum] = coro
        return coro, jobid

    def submit_job(self, jobname, slurm_extra_header, env, code, prepared_transformation):
        """To be implemented by subclass"""
        raise NotImplementedError

    async def await_job(self, checksum, jobname, identifier, code, tftype, tempdir, polling_interval):
        return await await_job(jobname, identifier, code, tftype, tempdir, polling_interval, "RESULT")

    def cancel_job(self, checksum, identifier):
        jobid = identifier
        if jobid not in self.jobs:
            return
        cmd = "scancel {}".format(jobid)
        try:
            subprocess.run(cmd, shell=True, check=True)
        except subprocess.CalledProcessError:
            traceback.print_exc()
        if checksum in self.coros:
            coro = self.coros.pop(checksum)
            task = asyncio.ensure_future(coro)
            task.cancel()


from .shell_backend import parse_resultfile


def submit_job(jobname, slurm_extra_header, env, code, *, use_host_environment):
    export = "ALL" if use_host_environment else "NONE"
    env_names = ",".join(sorted(env.keys()))
    slurmheader = """#!/bin/bash
#SBATCH -o {}.out
#SBATCH -e {}.err
#SBATCH --export={},{}
""".format(jobname, jobname, export, env_names)
    code2 = slurmheader
    if slurm_extra_header is not None:
        code2 += slurm_extra_header + "\n"
    code2 += code + "\n"
    with open("SLURMFILE", "w") as f:
        f.write(code2)
    os.chmod("SLURMFILE", 0o755)
    cmd = "sbatch -J {} SLURMFILE".format(jobname)
    env2 = os.environ.copy()
    env2.update(env)

    # This is ridiculous... Even with an error message such as "sbatch: error: No PATH environment variable", the error code is 0!!
    ### result = subprocess.check_output(cmd, env=env2, shell=True)
    # Let's try to fix that...
    process = subprocess.run(cmd, shell=True, env=env2, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = process.stdout
    if len(process.stderr.strip()):
        if len(result):
            identifier = result.decode().split()[-1]
            subprocess.run("scancel {}".format(identifier), shell=True)
        raise subprocess.CalledProcessError(cmd=cmd, returncode=1, stderr=process.stderr)

    identifier = result.decode().split()[-1]
    return identifier

async def await_job(jobname, identifier, code, tftype, tempdir, polling_interval, resultfile):
    status_command = "squeue -j {} | awk 'NR > 1'".format(identifier)
    while 1:
        result = subprocess.check_output(status_command, shell=True)
        result = result.decode().strip("\n").strip()
        if not len(result):
            break
        await asyncio.sleep(polling_interval)
    #  Let's try to retrieve an exit code
    exit_code = 0
    try:
        cmd = "scontrol show job {}".format(identifier)
        result = subprocess.check_output(cmd, shell=True)
        marker = " ExitCode="
        for l in result.decode().splitlines():
            pos = l.find(marker)
            if pos > -1:
                ll = l[pos+len(marker)]
                pos2 = ll.find(":")
                if pos2 > -1:
                    ll = ll[:pos2]
                exit_code = int(ll)
    except Exception:
        pass
    #print("EXIT CODE", exit_code)
    stdout = ""
    stderr = ""
    result = None

    old_cwd = os.getcwd()
    try:
        os.chdir(tempdir)
        try:
            stdout = open("{}.out".format(jobname), "rb").read()
            stdout = stdout.decode()
        except Exception:
            pass
        try:
            stderr = open("{}.err".format(jobname), "rb").read()
            stderr = stderr.decode()
        except Exception:
            pass
        if exit_code == 0 and resultfile is not None and os.path.exists(resultfile):
            result = parse_resultfile(resultfile)
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tempdir, ignore_errors=True)

    error_msg = None
    if exit_code > 0:
        error_msg = "Error: Non-zero exit code {}".format(exit_code)
    elif result is None and resultfile is not None:
        error_msg = "Error: Result file {} does not exist".format(resultfile)

    if error_msg is None:
        return result
    else:
        msg = """
{tftype} transformer exception
==========================

*************************************************
* Command
*************************************************
{}
*************************************************
{}
""".format(code, error_msg, tftype=tftype)

        if len(stdout):
            msg += """*************************************************
* Standard output
*************************************************
{}
*************************************************
""".format(stdout)

        if len(stderr):
            msg += """*************************************************
* Standard error
*************************************************
{}
*************************************************
""".format(stderr)

        raise SeamlessTransformationError(msg)

####################################################################################

class SlurmBashBackend(SlurmBackend):
    support_symlinks = True
    TF_TYPE = "Bash"
    USE_HOST_ENVIRONMENT = True

    def get_code(self, transformation, prepared_transformation):
        return prepared_transformation["bashcode"][1]

    def submit_job(self, jobname, slurm_extra_header, env, code, prepared_transformation):
        self.prepare_slurm_env(env)
        msg = "Submit slurm bash job {}"
        print(msg.format(jobname), file=sys.stderr)
        return submit_job(
            jobname, slurm_extra_header, env, code,
            use_host_environment=self.USE_HOST_ENVIRONMENT
        )

class SlurmSingularityBackend(SlurmBackend):
    support_symlinks = False
    TF_TYPE = "BashDocker"
    USE_HOST_ENVIRONMENT = False

    def get_code(self, transformation, prepared_transformation):
        docker_command, _ = get_docker_command_and_image(
            prepared_transformation
        )
        return docker_command

    def get_singularity_command(self, env, code, prepared_transformation):
        _, docker_image = get_docker_command_and_image(
            prepared_transformation
        )
        with open("CODE.bash", "w") as f:
            f.write(code + "\n")
        os.chmod("CODE.bash", 0o755)
        sif = "{}/{}.sif".format(
            self.SINGULARITY_IMAGE_DIR,
            docker_image
        )
        singularity_command = "{} {} ./CODE.bash".format(
            self.SINGULARITY_EXEC,
            sif
        )
        msg = "Submit slurm singularity job {{}}, image {}"
        message = msg.format(sif)
        return singularity_command, message

    def submit_job(self, jobname, slurm_extra_header, env, code, prepared_transformation):
        singularity_command, message = self.get_singularity_command(env, code, prepared_transformation)
        self.prepare_slurm_env(env)
        print(message.format(jobname), file=sys.stderr)
        return submit_job(
            jobname, slurm_extra_header, env, singularity_command,
            use_host_environment=self.USE_HOST_ENVIRONMENT
        )

class SlurmGenericSingularityBackend(SlurmSingularityBackend):
    support_symlinks = True
    TF_TYPE = "Generic"
    USE_HOST_ENVIRONMENT = True
    SINGULARITY_IMAGE_FILE = None # to be defined by jobless
    
    def prepare_slurm_env(self, env):
        env["SEAMLESS_MINIMAL_SINGULARITY_IMAGE"] = self.SINGULARITY_IMAGE_FILE

    def get_code(self, transformation, prepared_transformation):
        cmd = [            
            self.CONDA_ENV_RUN_TRANSFORMATION_COMMAND,
        ]
        d = prepared_transformation["temp_conda_env_dir"]
        checksum = prepared_transformation["__checksum__"]
        cmd.append(d)
        cmd.append(checksum)
        filezones = prepared_transformation["filezones"]
        if filezones is not None:
            for filezone in filezones:
                cmd.append("--filezone")
                cmd.append(filezone)

        code = " ".join(cmd)
        return code

    async def await_job(self, checksum, jobname, identifier, code, tftype, tempdir, polling_interval):
        await await_job(jobname, identifier, code, tftype, tempdir, polling_interval, resultfile=None)
        result_checksum = self.database_client.get_transformation_result(checksum)
        if result_checksum is not None:
            return Checksum(result_checksum)


    def get_singularity_command(self, env, code, prepared_transformation):

        with open("CODE.bash", "w") as f:
            f.write(code + "\n")
        os.system("chmod 775 CODE.bash")

        # in fact, all singulary invocation is now inside CODE.bash
        singularity_command = "./CODE.bash"
        
        checksum = prepared_transformation["__checksum__"]
        msg = "Submit slurm generic singularity job {{}}, checksum {}"
        message = msg.format(checksum)
        return singularity_command, message


from .shell_backend import get_docker_command_and_image
from . import Checksum