#!/bin/bash
echo 'Starting up job slaves...'
communion_incoming=$(python3 scripts/jobslaves.py)
echo "Job slaves are listening at " $communion_incoming
export SEAMLESS_COMMUNION_INCOMING=$communion_incoming
echo 'Starting up Cloudless web server...'
python3 scripts/cloudless.py
echo
echo 'Killing job slaves'
docker stop cloudless-jobslave-1 cloudless-jobslave-2 cloudless-jobslave-3 cloudless-jobslave-4
