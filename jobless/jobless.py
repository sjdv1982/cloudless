import time

class CommunionError(Exception):
    pass


import logging
logger = logging.getLogger("jobless")

def print_info(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.info(msg)

def print_warning(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.warning(msg)

def print_debug(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.debug(msg)

def print_error(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.error(msg)

def is_port_in_use(address, port): # KLUDGE: For some reason, websockets does not test this??
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((address, port)) == 0

import os, sys, asyncio, time, functools, json, traceback, base64, websockets

# TODO: read this from YAML config

port = None
_port = os.environ.get("JOBLESS_PORT")

try:
    port = int(_port)
except TypeError:
    print_error("JOBLESS_PORT: invalid port '%s'" % port)
jobless_address = os.environ.get("JOBLESS_ADDRESS")
if jobless_address is None:
    jobless_address = "localhost"


master_config = {
    "buffer": False,
    "buffer_status": False,
    "buffer_length": False,
    "transformation_job": False,
    "transformation_status": False,
    "semantic_to_syntactic": False,
}

servant_config = {
    "buffer": False,
    "buffer_status": False,
    "buffer_length": False,
    "transformation_job": True,
    "transformation_status": True,
    "semantic_to_syntactic": False,
    "hard_cancel": True,  # allow others to hard cancel our jobs
    "clear_exception": True, # allow others to clear exceptions on our jobs
}

from communion_encode import communion_encode, communion_decode
import numpy as np


"""
Jobs are submitted by checksum. There is also a job status API, which can return
    a code and a return value. The return value depends on the code:
    -3: Job checksum is unknown (cache miss in the server's checksum to buffer)
        None is returned, i.e. "return -3, None"
    -2: Job input checksums are unknown. None is returned.
    -1: Job is not runnable. None is returned.
    0: Job has exception. Exception is returned as a string, i.e. "return 0, exc"
    1: Job is runnable. None is returned.
    2: Job is running; progress and preliminary checksum are returned, i.e. "return 2, progress, prelim"
    3: Job is known; job checksum is returned, i.e. "return 3, job_checksum"
"""

class JoblessServer:
    future = None
    PROTOCOL = ("seamless", "communion", "0.2.1")
    _started = False
    def __init__(self):
        cid = os.environ.get("JOBLESS_COMMUNION_ID")
        if cid is None:
            cid = hash(int(id(self)) + int(10000*time.time()))
        self.id = cid
        self.peers = {}  # peer-id => connection, config
        self.rev_peers = {} # connection => peer-id
        self.message_count = {}
        self.transformations = {} # checksum => jobhandler
        self.peer_transformations = {} # peer-id => checksums
        self.transformation_peers = {}  # checksum => peer-cid
        self.jobhandlers = []
        self.hard_canceled = set()

    async def _listen_peer(self, websocket, peer_config):
        peer_id = peer_config["id"]
        if peer_id in self.peers:
            return
        if peer_config["protocol"] != list(self.PROTOCOL):
            print_warning("Protocol mismatch, peer '%s': %s, our protocol: %s" % (peer_config["id"], peer_config["protocol"], self.PROTOCOL))
            await websocket.send("Protocol mismatch: %s" % str(self.PROTOCOL))
            websocket.close()
            return
        else:
            await websocket.send("Protocol OK")
        try:
            protocol_message = await websocket.recv()
        except (websockets.exceptions.ConnectionClosed, ConnectionResetError):
            return
        if protocol_message != "Protocol OK":
            return
        print_debug("listen_peer", peer_config)
        self.peers[peer_id] = websocket, peer_config
        self.rev_peers[websocket] = peer_id
        if peer_id not in self.peer_transformations:
            self.peer_transformations[peer_id] = set()
        self.message_count[websocket] = 0

        try:
            while 1:
                message = await websocket.recv()
                asyncio.ensure_future(self._process_message_from_peer(websocket, message))
        except (websockets.exceptions.ConnectionClosed, ConnectionResetError):
            pass
        except Exception:
            print_error(traceback.format_exc())
        finally:
            self.peers.pop(peer_id)
            self.rev_peers.pop(websocket)
            # Don't decref peer_transformations or transformation_peers:
            #  client may lose connection after submitting job
            self.message_count.pop(websocket)

    async def _serve(self, config, websocket, path):
        peer_config = await websocket.recv()
        peer_config = json.loads(peer_config)
        if "id" not in peer_config:
            await websocket.send("No Seamless communion id provided")
            websocket.close()
            return
        print_warning("OUTGOING", self.id, peer_config["id"])
        await websocket.send(json.dumps(config))
        await self._listen_peer(websocket, peer_config)

    async def start(self):
        config = {
            "protocol": self.PROTOCOL,
            "id": self.id,
            "master": master_config,
            "servant": servant_config
        }
        import websockets

        coros = []
        if is_port_in_use(jobless_address, port): # KLUDGE
            print("ERROR: port %d already in use" % port)
            raise Exception
        server = functools.partial(self._serve, config)
        coro_server = websockets.serve(server, jobless_address, port)
        print("Set up a communion port %d" % port)
        await coro_server


    async def _process_request_from_peer(self, peer, message):
        #print("MESSAGE", message)
        type = message["type"]
        message_id = message["id"]
        content = message["content"]
        result = None
        error = False

        try:

            if type == "transformation_status":
                checksum = bytes.fromhex(content)
                if checksum in self.hard_canceled:
                    result = 0, "HardCancelError"
                else:
                    peer_id = self.rev_peers[peer]  # TODO: check that peer_id actually submitted?
                    if checksum in self.transformations:
                        jobhandler = self.transformations[checksum]
                        result = jobhandler.get_status(checksum)
                    else:
                        transformation_buffer = database_client.get_buffer(checksum)
                        if transformation_buffer is None:
                            result = -3, None
                        else:
                            try:
                                transformation = json.loads(transformation_buffer)
                            except Exception:
                                result = -3, None
                            else:
                                # For now, just 1 or -1
                                for jobhandler in self.jobhandlers:
                                    result = jobhandler.can_accept_transformation(checksum, transformation)
                                    if result == 1:
                                        result = 1, None
                                        break
                                else:
                                    result = -1, None

            elif type == "transformation_job":
                checksum = bytes.fromhex(content)
                peer_id = self.rev_peers[peer]
                if checksum in self.transformation_peers:
                    self.transformation_peers[checksum].add(peer_id)
                    result = "OK"
                    return
                transformation_buffer = database_client.get_buffer(checksum)
                if transformation_buffer is None:
                    raise ValueError("Unknown transformation checksum %s" % checksum.hex())
                transformation = json.loads(transformation_buffer)
                result = self.run_transformation(checksum, transformation, peer_id)
                return

            elif type == "transformation_wait":
                checksum = bytes.fromhex(content)
                if checksum in self.hard_canceled:
                    result = "OK"
                    return
                peer_id = self.rev_peers[peer]  # TODO: check that peer_id actually submitted?
                if checksum in self.transformations:
                    jobhandler = self.transformations[checksum]
                    await jobhandler.wait_for(checksum)
                    result = "OK"
                    return


            elif type == "transformation_cancel":
                checksum = bytes.fromhex(content)
                peer_id = self.rev_peers[peer]
                self.cancel(checksum, peer_id)
                result = "OK"
                return

            elif type == "transformation_hard_cancel":
                checksum = bytes.fromhex(content)
                peer_id = self.rev_peers[peer]
                self.hard_cancel(checksum, peer_id)
                result = "OK"
                return

            elif type == "transformation_clear_exception":
                checksum = bytes.fromhex(content)
                peer_id = self.rev_peers[peer]
                self.hard_cancel(checksum, peer_id)
                self.hard_canceled.discard(checksum)
                result = "OK"
                return



        except Exception as exc:
            print_error(traceback.format_exc())
            error = True
            result = repr(exc)
        finally:
            print_debug("REQUEST", message_id)
            response = {
                "mode": "response",
                "id": message_id,
                "content": result
            }
            if error:
                response["error"] = True
            msg = communion_encode(response)
            assert isinstance(msg, bytes)
            try:
                peer_id = self.rev_peers[peer]
                print_info("  Communion response: send %d bytes to peer '%s' (#%d)" % (len(msg), peer_id, response["id"]))
                print_debug("  RESPONSE:", msg, "/RESPONSE")
            except KeyError:
                pass
            else:
                await peer.send(msg)


    def run_transformation(self, checksum, transformation, peer_id):
        # For now, just 1 or -1
        for jobhandler in self.jobhandlers:
            result = jobhandler.can_accept_transformation(checksum, transformation)
            if result == 1:
                jobhandler.run_transformation(checksum, transformation)
                self.transformations[checksum] = jobhandler
                self.transformation_peers[checksum] = set([peer_id])
                self.peer_transformations[peer_id].add(checksum)
                result = "OK"
                break
        else:
            raise Exception("No jobhandler has accepted the transformation")

        return result

    def cancel(self, checksum, peer_id):
        if checksum not in self.transformation_peers:
            raise ValueError("Unknown transformation")
        checksums = self.peer_transformations[peer_id]
        if checksum not in checksums:
            raise ValueError("Unknown transformation")
        self.peer_transformations[peer_id].remove(checksum)
        peers = self.transformation_peers[checksum]
        peers.discard(peer_id)
        if not len(peers):
            self.transformation_peers.pop(checksum)
            jobhandler = self.transformations.pop(checksum)
            jobhandler.cancel_transformation(checksum)

    def hard_cancel(self, checksum, peer_id):
        if checksum not in self.transformation_peers:
            raise ValueError("Unknown transformation")
        #  TODO: validate peer_id, to be: one of the clients who submitted? an admin/monitor client?

        self.hard_canceled.add(checksum)
        peers = self.transformation_peers.pop(checksum)
        for peer_id in peers:
            self.peer_transformations[peer_id].remove(checksum)
        self.transformation_peers.pop(checksum)
        jobhandler = self.transformations.pop(checksum)
        jobhandler.cancel_transformation(checksum)



    async def _process_message_from_peer(self, peer, msg):
        message = communion_decode(msg)
        peer_id = self.rev_peers[peer]
        report = "  Communion %s: receive %d bytes from peer '%s' (#%d)"
        print_info(report  % (message["mode"], len(msg), peer_id, message["id"]), message.get("type"))
        print_debug("message from peer", peer_id, ": ", message)
        mode = message["mode"]
        assert mode in ("request", "response"), mode
        if mode != "request":
            print_info("Client sends response, but jobless doesn't make requests")
        return await self._process_request_from_peer(peer, message)


if __name__ == "__main__":

    from database_client import DatabaseClient
    database_client = DatabaseClient()
    database_client.connect()

    jobless_server = JoblessServer()
    asyncio.get_event_loop().run_until_complete(jobless_server.start())

    """
    TODO: config: read yaml
    => import jobhandlers and start them up
    """

    # Hard coded:
    from jobhandlers import (
        BashTransformerPlugin, DockerTransformerPlugin,
        ShellBashBackend, ShellDockerBackend,
        SlurmBashBackend, SlurmDockerBackend,
    )

    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor()

    class ShellBashTransformer(BashTransformerPlugin, ShellBashBackend):
        pass

    class ShellDockerTransformer(DockerTransformerPlugin, ShellDockerBackend):
        pass

    class SlurmBashTransformer(BashTransformerPlugin, SlurmBashBackend):
        pass

    class SlurmDockerTransformer(DockerTransformerPlugin, SlurmDockerBackend):
        pass

    jobless_server.jobhandlers = [
        """
        ShellBashTransformer(
            database_client,
            executor=executor,
            rewriter=("/data/", "~/.seamless/database/")
        ),
        ShellDockerTransformer(
            database_client,
            executor=executor,
            rewriter=("/data/", "~/.seamless/database/")
        ),
        """
    ]
    jobless_server.jobhandlers = [
        SlurmBashTransformer(
            database_client,
            executor=executor,
            rewriter=("/data/", "~/.seamless/database/")
        ),
        """
        SlurmDockerTransformer(
            database_client,
            executor=executor,
            rewriter=("/data/", "~/.seamless/database/")
        ),
        """
    ]


    asyncio.get_event_loop().run_forever()
