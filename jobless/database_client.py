# Adapted from the Seamless source code
# However, ip and port are specified in .connect
#   and not read from os.environ[SEAMLESS_DATABASE_IP/PORT]

import requests
import json
from hashlib import sha3_256
import os

from util import calculate_checksum, parse_checksum, BufferInfo

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

    def connect(self, host, port: int):
        port = int(port)
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

    def get_filename(self, checksum, filezones):
        request = {
            "type": "filename",
            "checksum": parse_checksum(checksum),
            "filezones": filezones,
        }
        response = self.send_request(request)
        if response is not None:
            return response.text

    def get_directory(self, checksum, filezones):
        request = {
            "type": "directory",
            "checksum": parse_checksum(checksum),
            "filezones": filezones,
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

    def get_transformation_result(self, checksum):
        request = {
            "type": "transformation",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_request(request)
        if response is not None:
            return bytes.fromhex(response.content.decode())

    def set_buffer(self, checksum, buffer, persistent):
        ps = chr(int(persistent)).encode()
        rqbuf = b'SEAMLESS_BUFFER' + parse_checksum(checksum).encode() + ps + buffer

        return self.send_put_request(rqbuf)

from silk.mixed.io.serialization import serialize
