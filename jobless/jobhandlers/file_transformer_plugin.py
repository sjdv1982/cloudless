""" Plugin for file-based transformers (bash and Docker transformers)
NOTE: there are some semantic differences with executor.py of the bash- and docker-transformers
 for local job execution as implemented by Seamless itself.
 This is because in Jobless, we are dealing with buffers (potentially already in a file)
 and local job execution in Seamless deals with deserialized values (from Seamless pins)

Probably keep the current code as the proper semantics, and adapt Seamless pin implementation
   (to provide buffers instead of values if so specified)
"""
import json
import os
import shutil
import copy

from . import TransformerPlugin, CacheMissError

class FileTransformerPluginBase(TransformerPlugin):

    REQUIRED_TRANSFORMER_PINS = []  # to be defined in subclass
    TRANSFORMER_CODE_CHECKSUMS = []  # to be defined in subclass

    def __init__(self, *args, filezones, **kwargs):
        self.filezones = copy.deepcopy(filezones)
        super().__init__(*args, **kwargs)

    def allowed_docker_image(self, docker_image):
        return False

    def allowed_powers(self, powers):
        return powers is None or len(powers) == 0

    def required_pin_handler(self, pin, transformation):
        """Obtain the value of required pins (such as bashcode etc.)
        To be re-implemented by the subclass

        return tuple (skip, json_value_only, json_buffer, write_env)

        skip: if True, skip the pin altogether
        json_value_only:  if True, the buffer must be interpreted as JSON,
                     and does not need to be written to file
        json_buffer: if True, the buffer must be interpreted as JSON,
                      then written to a new file.
                     if False, an existing filename for the pin may be
                     obtained from the database client and used;
                     else, the buffer will be written as-is to a new file
                     if None, the buffer (which must be in mixed format)
                      will be checked for JSON content (pure-plain).
        write_env: if True, the content of the buffer will be UTF8-decoded,
                   cast to string, and written as an environment variable
                   of the same name as the pin.
                   This will be done but only if the buffer has
                   less than 1000 characters.
        """
        raise NotImplementedError

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
            if len(env.get("conda", [])):
                return False

        for key in self.REQUIRED_TRANSFORMER_PINS:
            missed = True
            if isinstance(key, tuple):
                keylist = key
            else:
                keylist = (key,)
            for key in keylist:
                if key in transformation:
                    missed = False
                    break
            if missed:
                return False
        if not "code" in transformation:
            return False
        code = transformation["code"]
        if not isinstance(code, list) or len(code) != 3 or code[:2] != ['python', 'transformer']:
            return False
        code_checksum = code[-1]
        if code_checksum not in self.TRANSFORMER_CODE_CHECKSUMS:
            return False
        for fmt in transformation.get("__format__", {}).values():
            if not fmt.get("filesystem"):
                if fmt.get("hash_pattern"):
                    return False
        return True

    def prepare_transformation(self, checksum, transformation):
        tdict = {"__checksum__": checksum.hex()}
        if "__env__" in transformation:
            env_buf = self.database_client.get_buffer(transformation["__env__"])
            env = json.loads(env_buf)
            tdict["__env__"] = env
        as_ = transformation.get("__as__", {})

        required_transformer_pins = []
        for key in self.REQUIRED_TRANSFORMER_PINS:
            if isinstance(key, str):
                required_transformer_pins.append(key)
            else:
                required_transformer_pins += list(key)
        for pin in transformation:
            if pin == "code" or (pin.startswith("__") and pin.endswith("__")):
                continue
            celltype, subcelltype, pin_checksum = transformation[pin]
            json_value_only = False
            skip, json_buffer, write_env  = None, None, None            

            if pin in required_transformer_pins:
                skip, json_value_only, json_buffer, write_env = self.required_pin_handler(pin, transformation)
                if write_env:
                    write_env = None   # still check that the buffer isn't too large
            elif celltype == "mixed":
                skip = False
                json_buffer = None
                write_env = None
            elif celltype in ("plain", "int", "str", "float", "bool"):
                skip = False
                json_buffer = True
                write_env = None
            else:
                skip = False
                json_buffer = False
                write_env = None

            if skip:
                continue

            value = None
            pin_buf = None
            pin_buf_info = -1
            can_use_filename = False
            if celltype in ("text", "bytes", "binary"):
                can_use_filename = True

            if write_env is None:
                pin_buf_len = None
                if pin_buf_info == -1:
                    pin_buf_info = self.database_client.get_buffer_info(pin_checksum) 
                if pin_buf_info is not None:
                    pin_buf_len = pin_buf_info.length
                if pin_buf_len is not None:
                    if pin_buf_len <= 1000:
                        if pin_buf_info.is_utf8 != False:
                            write_env = True
                    else:
                        write_env = False
            
            if json_buffer is None: 
                assert celltype == "mixed"
                if pin_buf_info == -1:
                    pin_buf_info = self.database_client.get_buffer_info(pin_checksum)
                if pin_buf_info is not None:
                    json_buffer = pin_buf_info.is_json
                    if pin_buf_info.is_numpy:
                        can_use_filename = True

            if json_buffer is None or write_env is None or json_value_only:
                pin_buf = self.database_client.get_buffer(pin_checksum)
                if pin_buf is None:
                    raise CacheMissError(pin_checksum)
                if write_env is None:
                    if len(pin_buf) <= 1000:
                        write_env = True
                    else:
                        write_env = False
                if json_buffer is None:
                    assert celltype == "mixed"
                    json_buffer = is_json(pin_buf)
                    if not json_buffer:
                        if pin_buf.startswith(MAGIC_NUMPY):
                            can_use_filename = True

            

            filename = None            
            if not json_value_only:
                fs = transformation.get("__format__", {}).get(pin, {}).get("filesystem") 
                if fs is not None:
                    # optional = fs["optional"]  # ignore this. for mode=file, always optional. for mode=directory, never optional.
                    mode = fs["mode"]
                    if mode == "file":
                        can_use_filename = True
                    if mode == "directory":
                        filename = self.database_client.get_directory(
                            pin_checksum,
                            filezones=self.filezones
                        )
                        if filename is None:
                            raise CacheMissError(pin_checksum)
                if filename is None and can_use_filename:
                    filename = self.database_client.get_filename(
                        pin_checksum,
                        filezones=self.filezones
                    )                        
                        
                if filename is None or write_env:
                    if pin_buf is None:
                        pin_buf = self.database_client.get_buffer(pin_checksum)
                    if pin_buf is None:
                        raise CacheMissError(pin_checksum)

            
            if filename is None or write_env: 
                # we need the value. We have pin_buf already.
                if json_value_only:
                    if celltype in ("plain", "mixed", "int", "float", "bool", "str"):
                        value = json.loads(pin_buf)
                    elif celltype in ("text", "python", "ipython", "cson", "yaml", "checksum"):
                        value = pin_buf.decode()
                    else:
                        value = pin_buf
                elif json_buffer:
                    if pin_buf[:1] == b'"' and pin_buf[-2:-1] == b'"':
                        value = json.loads(pin_buf)
                    elif pin_buf[-1:] != b'\n':
                        value = json.loads(pin_buf)
                    else:
                        value = None  # we can use the buffer directly

            env_value = None
            if write_env:
                if value is None:
                    if json_buffer:
                        env_value = json.loads(pin_buf.decode())
                    else:
                        try:
                            env_value = pin_buf.decode()
                        except Exception:
                            env_value = None
                    if isinstance(env_value, (list, dict)):
                        env_value = None
                elif isinstance(value, (list, dict)):
                    env_value = None
                else:
                    env_value = value

            pin_as = as_.get(pin, pin)
            tdict[pin_as] = filename, value, env_value
        return tdict



MAGIC_NUMPY = b"\x93NUMPY"
MAGIC_SEAMLESS_MIXED = b'\x94SEAMLESS-MIXED'

def is_json(data):
    """Poor man's version of mixed_deserialize + get_form

    Maybe use this in real bash transformers as well?
    """
    assert isinstance(data, bytes)
    if data.startswith(MAGIC_NUMPY):
        return False
    elif data.startswith(MAGIC_SEAMLESS_MIXED):
        return False
    else:  # pure json
        return True

def write_files(prepared_transformation, env, support_symlinks):
    if prepared_transformation.get("__generic__"):
        return
    for pin in prepared_transformation:
        if pin in ("__checksum__", "__env__"):
            continue
        filename, value, env_value = prepared_transformation[pin]
        pinfile = "./" + pin
        if filename is not None:
            if support_symlinks:
                os.symlink(filename, pinfile)
            else:
                try:
                    os.link(filename, pinfile)
                except Exception:
                    shutil.copy(filename, pinfile)
        elif value is not None:
            if isinstance(value, bytes):
                with open(pinfile, "bw") as f:
                    f.write(value)
            elif isinstance(value, str):
                with open(pinfile, "w") as f:
                    f.write(value)
                    f.write("\n")
            else:
                with open(pinfile, "w") as f:
                    json.dump(value, f)
                    f.write("\n")
        if env_value is not None:
            env[pin] = str(env_value)
