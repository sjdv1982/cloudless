#!/bin/bash

set -u -e

echo $CLOUDLESS_GRAPHS_DIR
echo $CLOUDLESS_INSTANCES_DIR

export SEAMLESS_DOCKER_PUBLISH_SHARESERVER_PORTS='--detach --expose 5813 --expose 5138 -P'

# Starts up Cloudless with fat Seamless instances, i.e. that do their own computation  without jobslaves.
echo 'Starting up Cloudless web server...'
python3 -u scripts/cloudless.py $CLOUDLESS_GRAPHS_DIR $CLOUDLESS_INSTANCES_DIR $*