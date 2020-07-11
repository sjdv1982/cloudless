#!/bin/bash
echo 'Starting up job slaves...'
nslaves=$1
: ${nslaves:=4}
set -u -e
name_template=cloudless-jobslave
nodes=$(echo $CLOUDLESS_NODES | sed 's/,/ /g')
nodeIPs=''
for node in $nodes; do
    nodeIP=$(ssh -G $node | awk '$1=="hostname" {print $2}')
    nodeIPs=$nodeIPs" "$nodeIP
done
nodeIPs="${nodeIPs:1}"

communion_incoming=''
for nodeIP in $nodeIPs; do
    communion_incoming2=$(ssh $nodeIP "bash -l -c 'cd $CLOUDLESSDIR && python3 scripts/jobslaves.py $nslaves $name_template --remote --ip $nodeIP --master-ip $masterIP'")
    communion_incoming=$communion_incoming','$communion_incoming2
done
communion_incoming="${communion_incoming:1}"

echo "Job slaves are listening at " $communion_incoming
export SEAMLESS_COMMUNION_INCOMING=$communion_incoming
echo 'Starting up Cloudless web server...'
###python3 scripts/cloudless.py cloudless-serve-graph-thin
if [ $nslaves -gt 0 ]; then
    for nodeIP in $nodeIPs; do
        ssh $nodeIP "bash -l -c 'cd $CLOUDLESSDIR && ./kill-jobslaves.sh $nslaves $name_template'"
    done
fi