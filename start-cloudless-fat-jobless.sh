#!/bin/bash

set -u -e

echo $CLOUDLESS_GRAPHS_DIR
echo $CLOUDLESS_INSTANCES_DIR

export SEAMLESS_DOCKER_PUBLISH_SHARESERVER_PORTS='--detach --expose 5813 --expose 5138 -P'

export CLOUDLESS_WITH_COMMUNION=1
export CLOUDLESS_NO_FAT=0
echo 'Starting up Cloudless web server...'
python3 -u scripts/cloudless.py $CLOUDLESS_GRAPHS_DIR $CLOUDLESS_INSTANCES_DIR $*