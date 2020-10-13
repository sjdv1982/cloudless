# Adapted from the Seamless source code

import requests
import numpy as np
import json

session = requests.Session()

class DatabaseClient:
    active = False
    PROTOCOL = ("seamless", "database", "0.0.2")
    def _connect(self, host, port):
        self.host = host
        self.port = port
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "protocol",
        }
        response = session.get(url, data=serialize(request))
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
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "has buffer",
            "checksum": checksum.hex(),
        }
        response = session.get(url, data=serialize(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response.text == "1"

    def has_key(self, key):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "has key",
            "key": key,
        }
        response = session.get(url, data=serialize(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response.text == "1"

    def send_request(self, request):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        response = session.get(url, data=serialize(request))
        if response.status_code == 404:
            return None
        elif response.status_code >= 400:
            raise Exception(response.text)
        return response

    def get_buffer(self, checksum):
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        request = {
            "type": "buffer",
            "checksum": checksum.hex(),
        }
        response = self.send_request(request)
        if response is not None:
            return response.content

    def get_buffer_length(self, checksum):
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        request = {
            "type": "buffer length",
            "checksum": checksum.hex(),
        }
        response = self.send_request(request)
        if response is not None:
            return int(response.json())


    def get_filename(self, checksum):
        if isinstance(checksum, str):
            checksum = bytes.fromhex(checksum)
        request = {
            "type": "filename",
            "checksum": checksum.hex(),
        }
        response = self.send_request(request)
        if response is not None:
            return response.text


    def set_transformation_result(self, tf_checksum, checksum):
        request = {
            "type": "transformation result",
            "checksum": tf_checksum.hex(),
            "value": checksum.hex(),
        }
        url = "http://" + self.host + ":" + str(self.port)
        response = session.put(url, data=serialize(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response

    def set_buffer(self, checksum, buffer):
        # use compact buffer format (non-persistent)
        compact_data = b'SEAMLESS_COMPACT'
        compact_data += checksum
        compact_data += buffer
        url = "http://" + self.host + ":" + str(self.port)
        response = session.put(url, data=compact_data)
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response

### from ...mixed.io.serialization import serialize
import json
def serialize(request):
    return json.dumps(request)
