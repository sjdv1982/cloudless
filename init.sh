set -u -e

[ ! -d $CLOUDLESSDIR/instances ] && mkdir $CLOUDLESSDIR/instances
[ ! -d $CLOUDLESSDIR/graphs ] && mkdir $CLOUDLESSDIR/graphs
cd $CLOUDLESSDIR/graphs
container=$(docker create rpbs/seamless)

docker cp $container:/home/jovyan/seamless-tests/highlevel/share-pdb.zip testgraph.zip
docker cp $container:/home/jovyan/seamless-tests/highlevel/share-pdb.seamless testgraph.seamless
seamless-add-zip testgraph.zip

docker cp $container:/home/jovyan/seamless-tests/highlevel/share-pdb-docker.zip testgraph-docker.zip
docker cp $container:/home/jovyan/seamless-tests/highlevel/share-pdb-docker.seamless testgraph-docker.seamless
seamless-add-zip testgraph-docker.zip

# Run the following to update the status-visualization from the Seamless Docker image
docker cp $container:/home/jovyan/software/seamless/graphs/status-visualization.zip status-visualization.zip
docker cp $container:/home/jovyan/software/seamless/graphs/status-visualization.seamless status-visualization.seamless
# /Run

seamless-add-zip status-visualization.zip

rm testgraph.zip testgraph-docker.zip status-visualization.zip
docker rm $container