# Adapted from the Seamless source code

import requests
import json
from hashlib import sha3_256

def calculate_checksum(content, hex=False):
    if isinstance(content, str):
        content = content.encode()
    if not isinstance(content, bytes):
        raise TypeError(type(content))
    hash = sha3_256(content)
    result = hash.digest()
    if hex:
        result = result.hex()
    return result

def parse_checksum(checksum, as_bytes=False):
    """Parses checksum and returns it as string"""
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
    if isinstance(checksum, str):
        checksum = bytes.fromhex(checksum)

    if isinstance(checksum, bytes):
        assert len(checksum) == 32, len(checksum)
        if as_bytes:
            return checksum
        else:
            return checksum.hex()
    
    if checksum is None:
        return
    raise TypeError(type(checksum))

class BufferInfo:
    __slots__ = (
        "checksum", "length", "is_utf8", "is_json", "json_type", 
        "is_json_numeric_array", "is_json_numeric_scalar",
        "is_numpy", "dtype", "shape", "is_seamless_mixed", 
        "str2text", "text2str", "binary2bytes", "bytes2binary",
        "binary2json", "json2binary"
    )
    def __init__(self, checksum, params:dict={}):
        for slot in self.__slots__:            
            setattr(self, slot, params.get(slot))
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        self.checksum = checksum
    
    def __setattr__(self, attr, value):
        if value is not None:                
            if attr == "length":
                if not isinstance(value, int):
                    raise TypeError(type(value))
                if not value >= 0:
                    raise ValueError
            if attr.startswith("is_"):
                if not isinstance(value, bool):
                    raise TypeError(type(value))
        if attr.find("2") > -1 and value is not None:
            if isinstance(value, bytes):
                value = value.hex()
        super().__setattr__(attr, value)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

    def __getitem__(self, item):
        return getattr(self, item)

    def update(self, other):
        if not isinstance(other, BufferInfo):
            raise TypeError
        for attr in self.__slots__:
            v = getattr(other, attr)
            if v is not None:
                setattr(self, attr, v)
    
    def get(self, attr, default=None):
        value = getattr(self, attr)
        if value is None:
            return default
        else:
            return value
    
    def as_dict(self):
        result = {}
        for attr in self.__slots__:
            if attr == "checksum":
                continue
            v = getattr(self, attr)
            if v is not None:
                result[attr] = v
        return result

session = requests.Session()

EMPTY_DICT = "d0a1b2af1705c1b8495b00145082ef7470384e62ac1c4d9b9cdbbe0476c28f8c"
B_EMPTY_DICT = bytes.fromhex(EMPTY_DICT)
BUFFER_EMPTY_DICT = b'{}\n'

class DatabaseClient:
    active = False
    PROTOCOL = ("seamless", "database", "0.1")
    def _connect(self, host, port):
        self.host = host
        self.port = port
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "protocol",
        }
        response = session.get(url, data=json.dumps(request))
        try:
            assert response.json() == list(self.PROTOCOL)
        except (AssertionError, ValueError, json.JSONDecodeError):
            raise Exception("Incorrect Seamless database protocol") from None
        self.active = True

    def connect(self, *, host='localhost',port=5522):
        self._connect(host, port)

    def has_buffer(self, checksum):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "has_buffer",
            "checksum": parse_checksum(checksum),
        }
        response = session.get(url, data=json.dumps(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response.json() == True

    def has_buffer(self, checksum):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "has_buffer",
            "checksum": parse_checksum(checksum),
        }
        response = session.get(url, data=json.dumps(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response.json() == True

    def send_request(self, request):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        if isinstance(request, bytes):
            rqbuf = request
        else:
            rqbuf = json.dumps(request)
        response = session.get(url, data=rqbuf)
        if response.status_code == 404:
            return None
        elif response.status_code >= 400:
            raise Exception(response.text)
        return response

    def send_put_request(self, request):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        if isinstance(request, bytes):
            rqbuf = request
        else:
            rqbuf = json.dumps(request)
        response = session.put(url, data=rqbuf)
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response

    def get_buffer(self, checksum):
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        if checksum == B_EMPTY_DICT:
            return BUFFER_EMPTY_DICT
        request = {
            "type": "buffer",
            "checksum": checksum.hex(),
        }
        response = self.send_request(request)
        if response is not None:
            result = response.content
            hash = sha3_256(result)
            verify_checksum = hash.digest()
            assert checksum == verify_checksum, "Database corruption!!! Checksum {}".format(checksum.hex())
            return result

    def get_buffer_info(self, checksum) -> BufferInfo:
        request = {
            "type": "buffer_info",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_request(request)
        if response is not None:
            return BufferInfo(checksum, response.json())

    def get_filename(self, checksum):
        request = {
            "type": "filename",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_request(request)
        if response is not None:
            return response.text

    def get_directory(self, checksum):
        request = {
            "type": "directory",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_request(request)
        if response is not None:
            return response.text


    def set_transformation_result(self, tf_checksum, checksum):        
        request = {
            "type": "transformation",
            "checksum": parse_checksum(tf_checksum),
            "value": parse_checksum(checksum),
        }
        return self.send_put_request(request)

    def set_buffer(self, checksum, buffer, persistent):
        ps = chr(int(persistent)).encode()
        rqbuf = b'SEAMLESS_BUFFER' + parse_checksum(checksum).encode() + ps + buffer

        return self.send_put_request(rqbuf)

from silk.mixed.io.serialization import serialize
