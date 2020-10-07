#!/bin/bash
set -u -e
nslaves=$1
name_template=$2
echo 'Killing job slaves'
jobslaves=$(seq $nslaves | awk -v name_template=$name_template '{print name_template "-" $1}')
docker stop $jobslaves
