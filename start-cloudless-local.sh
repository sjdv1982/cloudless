#!/bin/bash
echo 'Starting up job slaves...'
nslaves=$1
: ${nslaves:=4}
port=$2
: ${port:=""}
set -u -e
name_template=cloudless-jobslave
communion_incoming=$(python3 scripts/jobslaves.py $nslaves $name_template)
echo "Job slaves are listening at " $communion_incoming
export SEAMLESS_COMMUNION_INCOMING=$communion_incoming
echo 'Starting up Cloudless web server...'
python3 scripts/cloudless.py cloudless-serve-graph-thin $port
if [ $nslaves -gt 0 ]; then
    echo
    ./kill-jobslaves.sh $nslaves $name_template
fi