#!/bin/bash
echo 'Starting up job slaves...'
nslaves=$1
: ${nslaves:=4}
communion_incoming=$(python3 scripts/jobslaves.py $nslaves)
echo "Job slaves are listening at " $communion_incoming
export SEAMLESS_COMMUNION_INCOMING=$communion_incoming
echo 'Starting up Cloudless web server...'
python3 scripts/cloudless.py
if [ $nslaves -gt 0 ]; then
    echo
    echo 'Killing job slaves'
    jobslaves=$(seq $nslaves | awk '{print "cloudless-jobslave-" $1}')
    docker stop $jobslaves
fi