#!/bin/bash

set -u -e

bridge_ip=$(docker network inspect bridge \
  | python3 -c '''
import json, sys 
bridge = json.load(sys.stdin)
print(bridge[0]["IPAM"]["Config"][0]["Gateway"])
''')

name=cloudless-jobslave-1
name2=TEST-GRAPH-SERVER
cd docker/test-commands
port=$(docker port $name | grep 8602 | sed 's/:/ /' | awk '{print $4}')
export SEAMLESS_COMMUNION_INCOMING=$bridge_ip:$port
./thin $name2 docker_.seamless
