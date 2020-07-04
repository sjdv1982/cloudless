# Installation guide
This guide
***Note: Unless indicated otherwise, it is assumed that you do each phase A-D in order***

# A. First installation steps

- Install Seamless (`docker pull rpbs/seamless && conda -c rpbs install seamless-cli`)

- Install Cloudless requirements with `pip install -r requirements.txt`.

- Define $CLOUDLESSDIR in your .bashrc

- Start Redis: `seamless-redis`. It is assumed to be always running.


# B. Network communication testing

- Make sure that the master and each node can reach each other, preferably with ssh-without-password.

It is assumed that your Redis instance does not contain anything else that needs to be saved.

## Master-to-master communication tests

This involves two terminals on the master

### Test master-to-master Seamless-to-Seamless communion.

   - In one terminal, do:

        `seamless python3 /home/jovyan/seamless-scripts/jobslave.py --communion_id JOBSLAVE --communion_outgoing 6543`

   - In another terminal:

        - Flush Redis DB: `docker exec redis-container redis-cli flushall`

        - `cd $CLOUDLESSDIR`

        - `seamless-bash`

        - `export SEAMLESS_COMMUNION_INCOMING=localhost:6543`

        - `python3 test-jobslave.py`

   The first lines should contain `INCOMING` and `ADD SERVANT`

   The last line should be `None`, not `Local computation has been disabled for this Seamless instance`


### Test master-to-master Seamless-to-Seamless communion, with Docker bridge networking.
    - In one terminal, do:
        - `cd $CLOUDLESSDIR`
        - `docker/commands/cloudless-jobslave jobslave-container && docker attach jobslave-container`
    - In a second terminal, do:

        - Flush Redis DB: `docker exec redis-container redis-cli flushall`

        - Find out the bridge IP:
            ```bash
            export bridge_ip=$(docker network inspect bridge \
            | python3 -c '''import json, sys; bridge = json.load(sys.stdin); print(bridge[0]["IPAM"]["Config"][0]["Gateway"])''')
            echo '$bridge_ip='$bridge_ip
            ```

        - Find out the ephemeral Docker port: `export port=$(docker port jobslave-container| grep 8602 | sed 's/:/ /' | awk '{print $4}'); echo '$port='$port`

        - `cd $CLOUDLESSDIR`

        -  Run the following:
            ```bash
            docker run --rm \
            -e "REDIS_HOST="$bridge_ip \
            -e "SEAMLESS_COMMUNION_INCOMING="$bridge_ip:$port \
            -u jovyan \
            rpbs/seamless \
            python3 test-jobslave.py
            ```


## Master-to-master communication tests

This involves one terminal on the master, one on the remote node. Repeat for each remote node.


### Remote node installation

- Clone the Cloudless repo. Define $CLOUDLESSDIR in your .bashrc.

- Install Seamless (`docker pull rpbs/seamless && conda -c rpbs install seamless-cli`)

### Test if Redis on the master is reachable from the node, with Docker host networking:

    - On the master, populate Redis with the Seamless default graph for status monitoring:

        `seamless python3 /home/jovyan/seamless-scripts/add-zip.py /home/jovyan/software/seamless/graphs/status-visualization.zip`

    - On the node, start a container with `seamless-bash`, and test
        - `ping $masterIP`
        - `redis-cli -h $masterIP`
        - type `keys *` and you will see some entries starting with "buf:" and "bfl:".
        - `exit` (Redis)
        - `exit` (Docker container)

### Test master-to-node Seamless-to-Seamless communion, with Docker host networking.
    - On the node, do:
        - `seamless-bash`
        - `export REDIS_HOST=$masterIP`
        - `export SEAMLESS_COMMUNION_OUTGOING_ADDRESS=$nodeIP`
        - `python3 ~/seamless-scripts/jobslave.py --communion_id JOBSLAVE --communion_outgoing 6543`
    - On the master, do:
        - Flush Redis DB: `docker exec redis-container redis-cli flushall`
        - `cd $CLOUDLESSDIR`
        - `seamless-bash`
        - `export SEAMLESS_COMMUNION_INCOMING=$nodeIP:6543`
        - `python3 test-jobslave.py`

   The first lines should contain `INCOMING` and `ADD SERVANT`

   The last line should be `None`, not `Local computation has been disabled for this Seamless instance`


### Switching from host networking to bridge networking

For both the master and the node, make sure that the bridge network can reach the main network. See (https://docs.docker.com/network/bridge/#enable-forwarding-from-docker-containers-to-the-outside-world)[]. Test it with the command: `docker run rpbs/seamless bash -c 'ping www.google.fr'`

### Test if Redis on the master is reachable from the node, with Docker bridge networking
    - On the node, do:
            ```bash
            docker run --rm \
            -it \
            -e "REDIS_HOST="$masterIP \
            -u jovyan \
            rpbs/seamless \
            bash
            ```
    - `ping $REDIS_HOST`
    - `redis-cli -h $REDIS_HOST`
    - type `keys *` and you will see some entries starting with "buf:" and "bfl:".
    - `exit` (Redis)
    - `exit` (Docker container)

### Test master-to-node Seamless-to-Seamless communion, with Docker bridge networking.
    - On the node, do:
        - `cd $CLOUDLESSDIR`
        - `docker/commands/cloudless-jobslave-remote jobslave-container $masterIP && docker attach jobslave-container`
    - On the node, in a second terminal, find out the ephemeral Docker port: `export port=$(docker port jobslave-container| grep 8602 | sed 's/:/ /' | awk '{print $4}'); echo '$port='$port`

    - On the master, do:
        - Flush Redis DB: `docker exec redis-container redis-cli flushall`

        - Find out the bridge IP:
            ```bash
            export bridge_ip=$(docker network inspect bridge \
            | python3 -c '''import json, sys; bridge = json.load(sys.stdin); print(bridge[0]["IPAM"]["Config"][0]["Gateway"])''')
            echo '$bridge_ip='$bridge_ip
            ```

        - `cd $CLOUDLESSDIR`

        -  Run the following:
            ```bash
            docker run --rm \
            -e "REDIS_HOST="$bridge_ip \
            -e "SEAMLESS_COMMUNION_INCOMING="$nodeIP:$port \
            -u jovyan \
            rpbs/seamless \
            python3 test-jobslave.py
            ```

   The first lines should contain `INCOMING` and `ADD SERVANT`

   The last line should be `None`, not `Local computation has been disabled for this Seamless instance`

- After the testing, flush Redis with `docker exec redis-container redis-cli flushall`

# C. Starting Cloudless

- Run `init.sh`

- Deploy your services. For each service, you will need `service.seamless` and `service.zip` in a directory `$DIR`.
Then, do:
```bash
cd $DIR
$CLOUDLESSDIR/docker/commands/cloudless-add-zip service.zip
cp service.seamless $CLOUDLESSDIR/graphs
```
(A future version of Cloudless will support dynamic deployment/re-deployment)

- Start Cloudless with one of the ./start-cloudless*.sh scripts
OR:
- Proceed to the next section

# D. Cloudless testing
(this section is a stub)

It is assumed that you can forward ports to the browser, either by manual SSH tunneling or using VSCode.
If not, you may want to go to section E first

## Basic fat graph serving (no jobslaves), with host networking:
  ```bash
  cd $CLOUDLESSDIR/graphs
  ../docker/test-commands/fat-host-networking TEST-FAT testgraph.seamless
  ```
  In the IPython window, `ctx.status` should give OK.
  => port-forward 5813, 5138
  => open http://localhost:5813/ctx/index.html

  - In a second terminal, start Cloudless with `./start-cloudless-fat.sh`
  - In a third terminal, connect the instance to Cloudless with:
   `./connect-instance http://localhost:3124 TEST-INSTANCE --update_port 5138 --rest_port 5813`
   This should print "Status: 200"
   => port-forward 3124 (Cloudless port)
   => open http://localhost:3124/admin/instance_page
   => Click "Go to instance" or open http://localhost:3124/instance/TEST-INSTANCE/ctx/index.html
  - Ctrl-D in the first terminal, Ctrl-C in the second.


## Basic fat graph serving (no jobslaves), with normal networking (bridge network):
  ```bash
  cd $CLOUDLESSDIR/graphs
  ../docker/test-commands/fat TEST-FAT testgraph.seamless
  ```
  In the IPython window, `ctx.status` should give OK.

  - In a second terminal, start Cloudless with `./start-cloudless-fat.sh`
  - In a third terminal, figure out the bridge port forwarding with:
    `docker port TEST-FAT` .
    The update port will be from 5138, i.e. `update_port=$(docker port TEST-FAT 5138 | awk -F ':' '{print $NF}')`
    The REST port will be from 5138, i.e. `rest_port=$(docker port TEST-FAT 5813 | awk -F ':' '{print $NF}')`
    Connect the instance to Cloudless with:
    `./connect-instance http://localhost:3124 TEST-INSTANCE --update_port $update_port --rest_port $rest_port`
   This should print "Status: 200"
   => port-forward 3124 (Cloudless port)
   => open http://localhost:3124/admin/instance_page
   => Click "Go to instance" or open http://localhost:3124/instance/TEST-INSTANCE/ctx/index.html
  - Ctrl-D in the first terminal, Ctrl-C in the second.

  ...

## Basic fat graph serving (no jobslaves), launching graph instances from Cloudless:
...


## Thin graph serving (with local jobslaves)
... (see test.sh, test-while-running-local.sh, test-while-running-local2.sh)

## Thin graph serving (with local jobslaves), launching graph instances from Cloudless:
... (same as for fat, but can monitor docker logs)

## Thin graph serving (with remote jobslaves)
... TODO!!

## Thin graph serving (with remote jobslaves), launching graph instances from Cloudless:
... (same as for fat, but can monitor docker logs on remote machine)


# E. Web proxying
(this section is a stub)

## nginx setup
... (see in config/; TODO make Docker image with .conf inside, need to share port 3124 or use host network!)

## Cloudless-to-Cloudless communication

- Cloudless-to-Cloudless: first: test-proxy.sh => wget. then, use it for Cloudless on a different machine (localhost => RPBS)
