# Installation guide

# A. First installation steps

## Installation of the Cloudless master

- Install Seamless (`docker pull rpbs/seamless && conda install -c rpbs seamless-cli`)

- Install Cloudless requirements with `pip install -r requirements.txt`.

- Define $CLOUDLESSDIR in your .bashrc

## Setup of the database adapter

  1. You need to setup a database.yaml, see /cloudless/jobless/tests/database-minimal.yaml for an example.
  2. Define a database startup command.
     For an example script that uses singularity, see /cloudless/jobless/tests/start-seamless-database.
     To start it up using Docker, copy and adapt `seamless-database`
  3. Start the Seamless database. For the rest of the guide, it is assumed to be always running.

### How to delete your database

Deletion has to be done for each backend separately.

If your DB has a flatfile backend:
    `cd <DB_DIRECTORY>`, then:
    `rm *-* -f`

If your DB has a Redis backend:
    Flush Redis DB: `docker exec redis-container redis-cli flushall`

## Setting up jobless

Like Cloudless, jobless runs without containerization.
Jobless configuration needs to be done in a .yaml file.
See /cloudless/jobless/tests/local.yaml for a minimal example, where bash transformers and Docker transformers
 are run as jobs locally.
Launch jobless with python3 /cloudless/jobless/jobless.py jobless-config.yaml

### Testing jobless

- Delete the database
- Make sure that the Docker images "ubuntu", "rpbs/seamless" and "rpbs/autodock" are available
  as Docker or singularity images in the place where the jobs will be run.
- Go to /cloudless/jobless/tests
- Launch a shell in a Seamless container with `seamless-bash`
- Run the tests bash.py, docker_.py and autodock.py with python3.
  See the .expected-output files in the same folder.
  If the output contains instead `Local computation has been disabled for this Seamless instance`, then the test has failed.

## Installation on remote nodes (if any)

- Clone the Cloudless repo. Define $CLOUDLESSDIR in your .bashrc.

- Install Seamless (`docker pull rpbs/seamless && conda install -c rpbs seamless-cli`)

- Define the variable `$masterIP` with `export` in `.bashrc.`


# B. Network communication testing

Make a backup of your DB if needed. Below, it is assumed that it does not contain anything else that needs to be saved, and can be deleted at will.

## Master-to-master communication tests

This involves two terminals on the master

### Test basic master-to-master Seamless-to-Seamless communion.

This test is  only necessary if Cloudless is deployed with jobslaves, leading to "thin"
graph-serving Seamless containers.
They are not necessary if the graph-serving Seamless containers
are "fat", i.e. they do all the work either themselves or delegate it to jobless.

- In one terminal, do:

    `seamless python3 /home/jovyan/seamless-scripts/jobslave.py --communion_id JOBSLAVE --communion_outgoing 6543`

- In another terminal:

    Delete your DB.

    Then, do:
    ```bash
    cd $CLOUDLESSDIR
    seamless-bash
    export SEAMLESS_COMMUNION_INCOMING=localhost:6543
    python3 test-jobslave.py
    ```

    The first lines should contain `INCOMING` and `ADD SERVANT`

    The last line should be `None`, not `Local computation has been disabled for this Seamless instance`

The last line should be `None`.
If is instead `Local computation has been disabled for this Seamless instance`, then the test has failed.

Do Ctrl-C in the first terminal, type `exit` in the second.

### Test Seamless-to-jobless communion, with Docker bridge networking.

See "testing jobless".

### Test master-to-master Seamless-to-Seamless communion, with Docker bridge networking.

The first test is useful to see if Docker bridge networking is working properly.

For the rest, these tests are only necessary if Cloudless is deployed with jobslaves, leading to "thin"
graph-serving Seamless containers.
They are not necessary if the graph-serving Seamless containers
are "fat", i.e. they do all the work either themselves or delegate it to jobless.

- In one terminal, do:

    - `cd $CLOUDLESSDIR`

    - `docker/commands/cloudless-jobslave jobslave-container && docker attach jobslave-container`

- In a second terminal, do:

    - Delete the DB

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
        -e "SEAMLESS_DATABASE_HOST="$bridge_ip \
        -e "SEAMLESS_COMMUNION_INCOMING="$bridge_ip:$port \
        -u `id -u` \
        --group-add users \
        -v $(pwd):/cwd \
        --workdir /cwd \
        rpbs/seamless \
        start.sh python3 test-jobslave.py
        ```
The first lines should contain `INCOMING` and `ADD SERVANT`

The last line should be `None`.
If is instead `Local computation has been disabled for this Seamless instance`, then the test has failed.

Do Ctrl-C in the first terminal.

## Master-to-node and node-to-master communication tests

This involves one terminal on the master, one on the remote Seamless node. Repeat for each remote node.
These tests are only necessary if Cloudless is deployed with remote jobslaves.
They are not necessary if:
- If there are no jobslaves. This is the case for "fat" graph-serving Seamless containers,
  that do all the work either themselves or delegate it to jobless.
- If all jobslaves are local, i.e. there are no remote Seamless nodes.

### Test if the node can reach an open port on the master

- On the master: `docker run --rm --network=host rpbs/seamless`

- On the node: `curl -v $masterIP:8888`

This should print something like:

```
< HTTP/1.1 302 Found
< Server: TornadoServer/6.0.3
< Content-Type: text/html; charset=UTF-8
< Date: Tue, 07 Jul 2020 09:13:31 GMT
< Location: /tree?
< Content-Length: 0
<
* Connection #0 to host XXX.XXX.X.XX left intact
```

### Test if the master can reach an open port on the node

- On the node: `docker run --rm --network=host rpbs/seamless`

- On the master: define nodeIP, then `curl -v $nodeIP:8888`

This should print the same as for the previous test.


### Test if Redis on the master is reachable from the node, with Docker host networking:

This test is only necessary if:
1. the database has a Redis backend,
2. a database adapter runs on each node.

- On the master, populate Redis with the Seamless default graph for status monitoring:

    `seamless python3 /home/jovyan/seamless-scripts/add-zip.py /home/jovyan/software/seamless/graphs/status-visualization.zip`

- On the node, do:
    - `seamless-bash -e masterIP`
    - `ping $masterIP`
    - `redis-cli -h $masterIP`
    - type `keys *` and you will see some entries starting with "buf:" and "bfl:".
    - `exit` (redis-cli)
    - `exit` (Docker container)

### Test master-to-node Seamless-to-Seamless communion, with Docker host networking.
- On the node, do:
    - `seamless-bash -e masterIP`
    - `set -u -e`
    - `export SEAMLESS_DATABASE_HOST=$masterIP`
    - `export SEAMLESS_COMMUNION_OUTGOING_ADDRESS=0.0.0.0`
    - `python3 ~/seamless-scripts/jobslave.py --communion_id JOBSLAVE --communion_outgoing 6543`
- On the master, do:
    - Delete the DB
    - Define the variable `nodeIP` as the IP address of the node. Use `export` to make it an environment variable.
    - `cd $CLOUDLESSDIR`
    - `seamless-bash -e nodeIP`
    - `set -u -e`
    - `export SEAMLESS_COMMUNION_INCOMING=$nodeIP:6543`
    - `python3 test-jobslave.py`

The first lines should contain `INCOMING` and `ADD SERVANT`

The last line should be `None`.
If is instead `Local computation has been disabled for this Seamless instance`, then the test has failed.



### Switching from host networking to bridge networking

For both the master and the node, make sure that the bridge network can reach the main network. See [this link](https://docs.docker.com/network/bridge/#enable-forwarding-from-docker-containers-to-the-outside-world). Test it with the command: `docker run --rm rpbs/seamless bash -c 'ping www.google.fr'`

### Test if Redis on the master is reachable from the node, with Docker bridge networking

This test is only necessary if:
1. the database has a Redis backend,
2. a database adapter runs on each node.

- On the master, populate Redis with the Seamless default graph for status monitoring:

    `seamless python3 /home/jovyan/seamless-scripts/add-zip.py /home/jovyan/software/seamless/graphs/status-visualization.zip`

- On the node, do:
    ```bash
    docker run --rm \
    -it \
    -e "SEAMLESS_DATABASE_HOST="$masterIP \
    -u `id -u` \
    --group-add users \
    rpbs/seamless \
    start.sh
    ```
- `ping $SEAMLESS_DATABASE_HOST`
- `redis-cli -h $SEAMLESS_DATABASE_HOST`
- type `keys *` and you will see some entries starting with "buf:" and "bfl:".
- `exit` (redis-cli)
- `exit` (Docker container)

### Test master-to-node Seamless-to-Seamless communion, with Docker bridge networking.

- On the node, do:
    - `cd $CLOUDLESSDIR`
    - `docker/commands/cloudless-jobslave-remote jobslave-container $masterIP && docker attach jobslave-container`
- On the node, in a second terminal, find out the ephemeral Docker port:

`port=$(docker port jobslave-container| grep 8602 | sed 's/:/ /' | awk '{print $4}'); echo '$port='$port`

- On the master, do:
    - Define the variable `nodeIP` as the IP address of the node. Use `export` to make it an environment variable.
    - The same for the variable `port` from the command above
    - Delete the DB

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
        -e "SEAMLESS_DATABASE_HOST="$bridge_ip \
        -e "SEAMLESS_COMMUNION_INCOMING="$nodeIP:$port \
        -v `pwd`:/cwd \
        --workdir /cwd \
        -u `id -u` \
        --group-add users \
        rpbs/seamless \
        start.sh python3 test-jobslave.py
        ```

The first lines should contain `INCOMING` and `ADD SERVANT`

The last line should be `None`.
If is instead `Local computation has been disabled for this Seamless instance`, then the test has failed.

- After the testing, delete the DB

# C. Starting Cloudless

- If `init.sh` has been run already, and there is no new Seamless version, you can skip the next two steps.

- Make a backup of your DB. Then, clean up entries that do not correspond to computation results that you want to keep.

- Run `init.sh`.

- Deploy your services. For each service, you will need `service.seamless` and `service.zip` in a directory `$DIR`.
Then, do:
```bash
cd $DIR
$CLOUDLESSDIR/docker/commands/cloudless-add-zip service.zip
cp service.seamless $CLOUDLESSDIR/graphs
```
(A future version of Cloudless will support dynamic deployment/re-deployment)

- Start Cloudless with one of the ./start-cloudless*.sh scripts. The three basic options are "fat", "local" and "remote".

Whenever a Seamless instance is launched, Cloudless will create a Docker container for it, that serves the graph.
A graph-serving container are named cloudless-123456, where 123456 is the instance ID.

With option "fat", the graph-serving containers are fat, i.e. they do all computation by themselves,
 unless they can delegate it to jobless.
Otherwise, the containers are thin, i.e. they redirect all computation to the jobslaves.
The jobslaves are Docker containers named "cloudless-jobslave-1" etc.

With option "local", the jobslaves run on the master. The number of jobslaves is by default 4, but can be set via the command line.

With open "remote", the jobslaves run remotely.
On the master, this requires the environment variable "CLOUDLESS_NODES" to be set to a comma-separated lists of SSH hosts
(i.e. IP addresses or entries in ~/.ssh/config)

On each node:
    - Cloudless must be installed, and $CLOUDLESSDIR must be defined
    - $masterIP must be defined
    - $CLOUDLESS_JOBSLAVES must be defined

- Stopping Cloudless kills both the jobslave and the graph serving containers. A future version of Cloudless will monitor the graphs and store them in Redis, so that the graph serving containers can be reconstituted at will.

# D. Cloudless testing

First, run `init.sh`.

It is assumed that you can forward ports to the browser, either by manual SSH tunneling or using VSCode.
If not, you may want to go to section E first.

## Command-line test

### Basic fat graph serving (no jobslaves), with host networking:

Open three terminals on the master. In the first terminal, do the following:

```bash
cd $CLOUDLESSDIR/graphs
../docker/test-commands/fat-host-networking TEST-FAT testgraph.seamless
```
In the IPython window, `ctx.status` should give OK.

Forward the ports 5813 and 5138 (Seamless ports).

Then, in the browser, open: http://localhost:5813/ctx/index.html

This should reveal the web form of the test service.

In the second terminal, start Cloudless with `./start-cloudless-fat.sh`

In the third terminal, connect the instance to Cloudless with:
`./connect-instance http://localhost:3124 TEST-INSTANCE --update_port 5138 --rest_port 5813`
This should print "Status: 200"

Forward the port 3124 (Cloudless port)

Then, in the browser, open: http://localhost:3124/admin

Click "Go to instance", or open http://localhost:3124/instance/TEST-INSTANCE/ctx/index.html

Again, this should reveal the web form of the test service.

To terminate, do Ctrl-D in the first terminal, Ctrl-C in the second.

### Basic fat graph serving (no jobslaves), with normal networking (bridge network):
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
   => open http://localhost:3124/admin
   => Click "Go to instance" or open http://localhost:3124/instance/TEST-INSTANCE/ctx/index.html
  - Ctrl-D in the first terminal, Ctrl-C in the second.

  ...

### Thin graph serving (with local jobslaves)
See test.sh, test-while-running-local.sh, test-while-running-local2.sh.

## Browser tests
See http://localhost:3124, http://localhost:3124/admin/

# E. Web proxying

## nginx setup

Follow the instructions in nginx/README.md . After that, you can run the tests in section D, substituting http://myserver.com/cloudless for http://localhost:3124 .

## Cloudless-to-Cloudless communication

With a public Cloudless server accessible via http://myserver.com/cloudless, you can connect a local Cloudless instance to it. The syntax is `$CLOUDLESSDIR/cloudless-to-cloudless http://localhost:3124 ws://myserver.com/cloudless PROXYNAME`. As long as cloudless-to-cloudless is running, a URL such as `http://myserver.com/cloudless/proxy/PROXYNAME/1234567/ctx/index.html` is redirected to `http://localhost:3124/instances/1234567/ctx/index.html`. The proxying is done by cloudless-to-cloudless, much like an SSH tunnel, i.e. no public IP address or URL for the local machine is needed. (This is in contrast to `$CLOUDLESSDIR/connect_instance`, where the ports are on the *public server*, not on the local machine that calls `connect_instance`).

Only Seamless instances are proxied; the admin page or "create new instance" page is not.

`test-proxy.sh` provides a test for Cloudless-to-Cloudless communication by setting up two local Cloudless instances, with one of them running under port 4000, and one proxying the other.
