#!/bin/bash

port=$1
: ${port:=""}

# Starts up Cloudless with fat Seamless instances, i.e. that do their own computation  without jobslaves.
echo 'Starting up Cloudless web server...'
python3 -u scripts/cloudless.py cloudless-serve-graph-fat-jobless $port