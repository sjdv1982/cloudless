#!/bin/bash
echo 'Starting up job slaves...'
nslaves=$1
: ${nslaves:=4}
port=$2
: ${port:=""}
set -u -e
dummy=$CLOUDLESS_NODES
name_template=cloudless-jobslave
nodes=($(echo $CLOUDLESS_NODES | sed 's/,/ /g'))
nodeIPs=''
for node in $nodes; do
    nodeIP=$(ssh -G $node | awk '$1=="hostname" {print $2}')
    nodeIPs=$nodeIPs" "$nodeIP
done
nodeIPs=("${nodeIPs:1}")

communion_incoming=''
for (( n=0; n<${#nodeIPs[@]}; n++ )); do
    nodeIP="${nodeIPs[n]}"
    node="${nodes[n]}"
    echo $nodeIP $node
    communion_incoming2=$(ssh $node "bash -l -c 'cd \$CLOUDLESSDIR && python3 scripts/jobslaves.py $nslaves $name_template --remote --ip $nodeIP --master-ip \$masterIP'")
    communion_incoming=$communion_incoming','$communion_incoming2
done
communion_incoming="${communion_incoming:1}"

echo "Job slaves are listening at " $communion_incoming
export SEAMLESS_COMMUNION_INCOMING=$communion_incoming
echo 'Starting up Cloudless web server...'
rm -f instances/*
python3 -u scripts/cloudless.py cloudless-devel-serve-graph-thin $port
if [ $nslaves -gt 0 ]; then
    for node in $nodes; do
        echo $node
        ssh $node "bash -l -c 'cd \$CLOUDLESSDIR && ./kill-jobslaves.sh $nslaves $name_template'"
    done
fi