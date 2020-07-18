set -u -e

docker exec redis-container redis-cli flushall

[ ! -d $CLOUDLESSDIR/graphs ] && mkdir $CLOUDLESSDIR/graphs
cd $CLOUDLESSDIR/graphs
container=$(docker create rpbs/seamless)

docker cp $container:/home/jovyan/seamless-tests/highlevel/share-pdb.zip testgraph.zip
docker cp $container:/home/jovyan/seamless-tests/highlevel/share-pdb.seamless testgraph.seamless
$CLOUDLESSDIR/docker/commands/cloudless-add-zip testgraph.zip

docker cp $container:/home/jovyan/seamless-tests/highlevel/share-pdb-docker.zip testgraph-docker.zip
docker cp $container:/home/jovyan/seamless-tests/highlevel/share-pdb-docker.seamless testgraph-docker.seamless
$CLOUDLESSDIR/docker/commands/cloudless-add-zip testgraph-docker.zip

# Run the following to update the status-visualization from the Seamless Docker image
docker cp $container:/home/jovyan/software/seamless/graphs/status-visualization.zip status-visualization.zip
docker cp $container:/home/jovyan/software/seamless/graphs/status-visualization.seamless status-visualization.seamless
# /Run

$CLOUDLESSDIR/docker/commands/cloudless-add-zip status-visualization.zip

rm testgraph.zip testgraph-docker.zip status-visualization.zip
docker rm $container