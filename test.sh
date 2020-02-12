#!/bin/bash

set -u -e

bridge_ip=$(docker network inspect bridge \
  | python3 -c '''
import json, sys 
bridge = json.load(sys.stdin)
print(bridge[0]["IPAM"]["Config"][0]["Gateway"])
''')

name=TEST-JOBSLAVE
name2=TEST-GRAPH-SERVER
set +e
docker stop $name >& /dev/null
set -e
cd graphs
echo 'Start jobslave container' $name 
../docker/commands/seamless-devel-jobslave $name
port=$(docker port $name | grep 8602 | sed 's/:/ /' | awk '{print $4}')
export SEAMLESS_COMMUNION_INCOMING=$bridge_ip:$port
../docker/test-commands/thin $name2 share-pdb.seamless
docker stop $name
