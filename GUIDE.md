- Make sure that the master and each node can reach each other, preferably with ssh-without-password.

# Network communication testing

On the master:

- Install Seamless (Docker and conda)

- Install Cloudless requirements.txt with pip

- Start Redis: `seamless-redis` . It is assumed that your Redis instance does not contain anything else that needs to be saved.

- Test master-to-master Seamless-to-Seamless communion.

   - In one terminal, do:

        `seamless python3 /home/jovyan/seamless-scripts/jobslave.py --communion_id JOBSLAVE --communion_outgoing 6543`

   - In another terminal:

        - Re-initialize Redis DB: `docker exec redis-container redis-cli flushall`

        - `cd $CLOUDLESSDIR`

        - `seamless-bash`

        - `export SEAMLESS_COMMUNION_INCOMING=localhost:6543`

        - `python3 test-jobslave.py`

   The first lines should contain `INCOMING` and `ADD SERVANT`

   The last line should be `None`, not `Local computation has been disabled for this Seamless instance`


- Test master-to-master Seamless-to-Seamless communion, with Docker bridge networking.
    - In one terminal, do:
        - `cd $CLOUDLESSDIR`
        - `docker/commands/seamless-jobslave jobslave-container && docker attach jobslave-container`
    - In a second terminal, do:

        - Re-initialize Redis DB: `docker exec redis-container redis-cli flushall`

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
            -v `pwd`:/cwd \
            --workdir /cwd \
            -u jovyan \
            rpbs/seamless \
            python3 test-jobslave.py
            ```



On each remote node:

- Clone the Cloudless repo

- Install Seamless (Docker and conda)

- On the master, populate Redis with the Seamless default graph for status monitoring:

    `seamless python3 /home/jovyan/seamless-scripts/add-zip.py /home/jovyan/software/seamless/graphs/status-visualization.zip`

- On the node, start a container with `seamless-bash`, and test if Redis on the master is reachable from the node:
    - `ping $masterIP`
    - `redis-cli -h $masterIP`
    - type `keys *` and you will see some entries starting with "buf:" and "bfl:".
    - `exit` (Redis)
    - `exit` (Docker container)

- Test master-to-node Seamless-to-Seamless communion, with Docker host networking.
    - On the node, do:
        - `seamless-bash`
        - `export REDIS_HOST=$masterIP`
        - `export SEAMLESS_COMMUNION_OUTGOING_ADDRESS=$nodeIP`
        - `python3 ~/seamless-scripts/jobslave.py --communion_id JOBSLAVE --communion_outgoing 6543`
    - On the master, do:
        - Re-initialize Redis DB: `docker exec redis-container redis-cli flushall`
        - `cd $CLOUDLESSDIR`
        - `seamless-bash`
        - `export SEAMLESS_COMMUNION_INCOMING=$nodeIP:6543`
        - `python3 test-jobslave.py`

   The first lines should contain `INCOMING` and `ADD SERVANT`

   The last line should be `None`, not `Local computation has been disabled for this Seamless instance`

- For both the master and the node, make sure that the bridge network can reach the main network. See (https://docs.docker.com/network/bridge/#enable-forwarding-from-docker-containers-to-the-outside-world)[]. Test it with the command: `docker run rpbs/seamless bash -c 'ping www.google.fr'`

- Test if Redis on the master is reachable from the node, with Docker bridge networking
    - On the node, do:
            ```bash
            docker run --rm \
            -it \
            -e "REDIS_HOST="$masterIP \
            -v `pwd`:/cwd \
            --workdir /cwd \
            -u jovyan \
            rpbs/seamless \
            bash
            ```
    - `ping $REDIS_HOST`
    - `redis-cli -h $REDIS_HOST`
    - type `keys *` and you will see some entries starting with "buf:" and "bfl:".
    - `exit` (Redis)
    - `exit` (Docker container)

- Test master-to-node Seamless-to-Seamless communion, with Docker bridge networking.
    - On the node, do:
        - `cd $CLOUDLESSDIR`
        - `docker/commands/seamless-jobslave-remote jobslave-container $masterIP && docker attach jobslave-container`
    - On the node, in a second terminal, find out the ephemeral Docker port: `export port=$(docker port jobslave-container| grep 8602 | sed 's/:/ /' | awk '{print $4}'); echo '$port='$port`

    - On the master, do:
        - Re-initialize Redis DB: `docker exec redis-container redis-cli flushall`

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
            -v `pwd`:/cwd \
            --workdir /cwd \
            -u jovyan \
            rpbs/seamless \
            python3 test-jobslave.py
            ```

   The first lines should contain `INCOMING` and `ADD SERVANT`

   The last line should be `None`, not `Local computation has been disabled for this Seamless instance`

# Starting Cloudless

- Populate Redis with the Seamless default graph for status monitoring:
    `seamless python3 /home/jovyan/seamless-scripts/add-zip.py /home/jovyan/software/seamless/graphs/status-visualization.zip`

- ...
