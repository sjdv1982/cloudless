#!/bin/bash

set -u -e

echo TODO
exit

# Run this test while Cloudless has been started up using ./start-cloudless-local.sh

# test-while-running-local, but:
# - using Docker images in the transformation
# - adding a status monitoring

bridge_ip=$(docker network inspect bridge \
  | python3 -c '''
import json, sys
bridge = json.load(sys.stdin)
print(bridge[0]["IPAM"]["Config"][0]["Gateway"])
''')

name=cloudless-jobslave-1
name2=TEST-GRAPH-SERVER
cd graphs
port=$(docker port $name | grep 8602 | sed 's/:/ /' | awk '{print $4}')
export SEAMLESS_COMMUNION_INCOMING=$bridge_ip:$port
../docker/test-commands/thin $name2 testgraph-docker.seamless \
  --status-graph /home/jovyan/software/seamless/graphs/status-visualization.seamless \
  --add-zip /home/jovyan/software/seamless/graphs/status-visualization.zip
