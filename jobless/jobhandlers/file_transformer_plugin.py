""" Plugin for file-based transformers (bash and Docker transformers)
NOTE: there are some semantic differences with executor.py of bash- and docker-transformers
 because we are dealing with buffers (potentially already in a file)
 and executor.py deals with deserialized values (from Seamless pins)
Probably keep the current code as the proper semantics, and adapt Seamless pin implementation
   (to provide buffers instead of values if so specified)
"""
import asyncio
import json
import traceback
import os
import shutil

from . import TransformerPlugin, CacheMissError

class FileTransformerPluginBase(TransformerPlugin):

    def __init__(self, *args, rewriter=None, **kwargs):
        self.rewriter = rewriter
        super().__init__(*args, **kwargs)

    REQUIRED_TRANSFORMER_PINS = []  # to be defined in subclass
    TRANSFORMER_CODE_CHECKSUMS = []  # to be defined in subclass

    def required_pin_handler(self, pin, transformation):
        """return tuple (skip, value_only, json_buffer, write_env)
        To be re-implemented by the subclass

        skip: if True, skip the pin altogether
        value_only:  if True, the buffer must be interpreted as JSON,
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
                   if None, the above will be done but only if the buffer has
                   less than 1000 characters.
        """
        raise NotImplementedError

    def can_accept_transformation(self, checksum, transformation):
        for key in self.REQUIRED_TRANSFORMER_PINS:
            if key not in transformation:
                return -1
        if not "code" in transformation:
            return -1
        code = transformation["code"]
        if not isinstance(code, list) or len(code) != 3 or code[:2] != ['python', 'transformer']:
            return -1
        code_checksum = code[-1]
        return code_checksum in self.TRANSFORMER_CODE_CHECKSUMS

    def prepare_transformation(self, checksum, transformation):
        tdict = {"__checksum__": checksum.hex()}
        for pin in transformation:
            if pin in ("__output__", "code"):
                continue
            celltype, subcelltype, pin_checksum = transformation[pin]
            value_only = False
            skip, json_buffer, write_env  = None, None, None

            if pin in self.REQUIRED_TRANSFORMER_PINS:
                skip, value_only, json_buffer, write_env = self.required_pin_handler(pin, transformation)
            elif celltype == "mixed":
                skip = False
                json_buffer = None
                write_env = None
            elif celltype == "plain":
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

            if json_buffer == False and write_env is None:
                pin_buf_len = self.database_client.get_buffer_length(pin_checksum)
                if pin_buf_len is not None:
                    if pin_buf_len <= 1000:
                        write_env = True
                    else:
                        write_env = False
            if (json_buffer is None or json_buffer == True) or \
              (write_env is None or write_env == True) or value_only:
                pin_buf = self.database_client.get_buffer(pin_checksum)
                if pin_buf is None:
                    raise CacheMissError
                if write_env is None:
                    if len(pin_buf) <= 1000:
                        write_env = True
                    else:
                        write_env = False
                if json_buffer is None:
                    assert celltype == "mixed"
                    if is_binary(pin_buf):
                        json_buffer = False
                    else:
                        json_buffer = True
            if value_only:
                if celltype in ("plain", "mixed", "int", "float", "bool", "str"):
                    value = json.loads(pin_buf)
                elif celltype in ("text", "python", "ipython", "cson", "yaml", "checksum"):
                    value = pin_buf.decode()
                else:
                    value = pin_buf
            elif json_buffer:
                if pin_buf[:1] == b'"' and pin_buf[-2:-1] == b'"':
                    value = json.loads(pin_buf)
                    value_only = True
                elif pin_buf[-1:] != b'\n':
                    value = json.loads(pin_buf)
                    value_only = True
                else:
                    pass  # we can use the buffer directly

            filename = None
            env_value = None
            if write_env:
                env_value = value
                if isinstance(env_value, (list, dict)):
                    env_value = None
                elif env_value is None:
                    env_value = pin_buf.decode()
                    if json_buffer:
                        env_value = json.loads(env_value)
                        if isinstance(env_value, (list, dict)):
                            env_value = None
                    else:
                        env_value = str(env_value).rstrip("\n")

            if not value_only:
                """
                ### Disable this for now, for security reasons...
                filename = self.database_client.get_filename(pin_checksum)
                """
                filename = None ###
                if filename is None:
                    pin_buf = self.database_client.get_buffer(pin_checksum)
                    if pin_buf is None:
                        raise CacheMissError
                    value = pin_buf
                elif self.rewriter is not None:
                    pre, post = self.rewriter
                    if filename.startswith(pre):
                        tail = filename[len(pre):]
                        filename = post + tail
            tdict[pin] = filename, value, env_value
        return tdict



MAGIC_NUMPY = b"\x93NUMPY"
MAGIC_SEAMLESS_MIXED = b'\x94SEAMLESS-MIXED'

def is_binary(data):
    """Poor man's version of mixed_deserialize + get_form

    Maybe use this in real bash transformers as well?
    Normally, we don't want mixed-plain or mixed-binary,
     since command line tools can't read it...
    """
    assert isinstance(data, bytes)
    if data.startswith(MAGIC_NUMPY):
        return True
    elif data.startswith(MAGIC_SEAMLESS_MIXED):
        raise ValueError("mixed binary/plain buffers are not supported")
    else:
        return False

def write_files(prepared_transformation, env, support_symlinks):
    for pin in prepared_transformation:
        if pin == "__checksum__":
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
