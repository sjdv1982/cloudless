"""Generic transformer plugin, using a rpbs/seamless-minimal container
and an external conda env
"""
import json
import os
import shutil
import copy
import time
import asyncio
import subprocess
import tempfile

from . import TransformerPlugin, SeamlessTransformationError

class GenericTransformerPlugin(TransformerPlugin):
    CONDA_ENV_MODIFY_COMMAND = "seamless-conda-env-modify"

    def prepare_conda_env_modify_env(self, env):
        pass

    def allowed_docker_image(self, docker_image):
        return False

    def allowed_powers(self, powers):
        return powers is None or len(powers) == 0

    def allowed_conda(self, conda):
        return True

    def can_accept_transformation(self, checksum, transformation):
        env = None
        if "__env__" in transformation:
            env_buf = self.database_client.get_buffer(transformation["__env__"])
            if env_buf is None:
                return False
            try:
                env = json.loads(env_buf)
            except:
                return False
            powers = env.get("powers")
            if not self.allowed_powers(powers):
                return False
            docker_image = env.get("docker", {}).get("name")
            if docker_image is not None:
                if not self.allowed_docker_image(docker_image):
                    return False
            conda = env.get("conda", [])
            if not self.allowed_conda(conda): 
                return False
        return True

    def __init__(self, 
        *args, 
        filezones,
        exported_conda_env_directory,
        temp_conda_env_directory,
        temp_conda_env_lifetime,
        **kwargs
    ):
        self.filezones = copy.deepcopy(filezones)
        assert os.path.exists(exported_conda_env_directory), exported_conda_env_directory
        self.exported_conda_env_directory = exported_conda_env_directory
        assert os.path.exists(temp_conda_env_directory), temp_conda_env_directory
        self.temp_conda_env_directory = temp_conda_env_directory
        self.temp_conda_env_lifetime = float(temp_conda_env_lifetime)
        self.transformation_to_conda_env = {}
        self.conda_env_to_transformations = {}
        self.conda_env_last_used = {}
        self.cleanup_coro = asyncio.ensure_future(self._cleanup())

    def _get_temp_conda_env_dir(self, conda_env):
        if conda_env is None:
            conda_env = "DEFAULT"
        return os.path.join(self.temp_conda_env_directory, conda_env)

    async def _cleanup(self):
        while 1:
            t = time.time()
            for conda_env, tfs in self.conda_env_to_transformations.items():
                if len(tfs):
                    continue
                last_used = self.conda_env_last_used[conda_env]
                if last_used - t < self.temp_conda_env_lifetime:
                    continue
                conda_env_dir = self._get_temp_conda_env_dir(conda_env)
                shutil.rmtree(conda_env_dir)
                self.conda_env_to_transformations.pop(conda_env)
                self.conda_env_last_used.pop(conda_env)
            await asyncio.sleep(2)

    def _create_conda_env(self, conda_env, conda_buf):
        d = self._get_temp_conda_env_dir(conda_env)
        if not os.path.exists(d):

            # does not work...
            #shutil.copytree(self.exported_conda_env_directory, d, ignore_dangling_symlinks=True)
            os.system("cp -r {} {}".format(self.exported_conda_env_directory, d))
            
            if conda_env is not None:
                with tempfile.NamedTemporaryFile(suffix=".yml") as f:
                    f.write(conda_buf.encode())
                    f.flush()
                    env = os.environ.copy()            
                    self.prepare_conda_env_modify_env(env)
                    cmd = [self.CONDA_ENV_MODIFY_COMMAND, d, f.name]
                    cmd2 = " ".join(cmd)  
                    print("conda env modify command:", cmd2)               
                    try:
                        subprocess.run(cmd2, shell=True, env=env)
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
Generic transformer error
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
""".format(cmd2, stdout, stderr)) from None

        self.conda_env_last_used[conda_env] = time.time()
        self.conda_env_to_transformations[conda_env] = []

    def prepare_transformation(self, checksum, transformation):
        conda_env = None
        conda_buf = None
        if "__env__" in transformation:
            env_buf = self.database_client.get_buffer(transformation["__env__"])
            env = json.loads(env_buf)
            conda = env.get("conda")
            if conda is not None:
                conda_buf = json.dumps(conda, sort_keys=True, indent=2)
                conda_env = calculate_checksum(conda_buf, hex=True)
        if conda_env not in self.conda_env_last_used:
            self._create_conda_env(conda_env, conda_buf)
        d = self._get_temp_conda_env_dir(conda_env)
        return {
            "__checksum__": checksum.hex(),
            "__generic__": True,
            "conda_env": conda_env,
            "temp_conda_env_dir": d,
            "filezones": self.filezones
        }

    def transformation_finished2(self, checksum, future):
        checksum = parse_checksum(checksum)
        conda_env = self.transformation_to_conda_env.pop(checksum)
        self.conda_env_to_transformations[conda_env].remove(checksum)
        self.conda_env_last_used[conda_env] = time.time()


class GenericSingularityTransformerPlugin(GenericTransformerPlugin):
    CONDA_ENV_MODIFY_COMMAND = None  #to be set from YAML
    def prepare_conda_env_modify_env(self, env):
        env["SEAMLESS_MINIMAL_SINGULARITY_IMAGE"] = self.SINGULARITY_IMAGE_FILE



from util import calculate_checksum, parse_checksum        