#!/bin/bash
echo 'Starting up job slaves...'
nslaves=$1
: ${nslaves:=4}
shift 1

if [ -z "$SEAMLESS_DATABASE_PORT" ]; then
  export SEAMLESS_DATABASE_PORT=5522
fi

set -u -e

export SEAMLESS_DOCKER_PUBLISH_SHARESERVER_PORTS='--detach --expose 5813 --expose 5138 -P'

name_template=cloudless-jobslave
communion_incoming=$(python3 scripts/jobslaves.py $nslaves $name_template)
echo "Job slaves are listening at " $communion_incoming
export SEAMLESS_COMMUNION_INCOMING=$communion_incoming

export CLOUDLESS_WITH_COMMUNION=1
export CLOUDLESS_NO_FAT=1
echo 'Starting up Cloudless web server...'
set +e
python3 -u scripts/cloudless.py $*

if [ $nslaves -gt 0 ]; then
    echo
    ./kill-jobslaves.sh $nslaves $name_template
fi