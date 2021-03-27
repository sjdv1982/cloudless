set -u -e

[ ! -d $CLOUDLESSDIR/instances ] && mkdir $CLOUDLESSDIR/instances
[ ! -d $CLOUDLESSDIR/graphs ] && mkdir $CLOUDLESSDIR/graphs

cd $CLOUDLESSDIR/graphs
container=$(docker create rpbs/seamless)

# Run the following to update the status-visualization from the Seamless Docker image
docker cp $container:/home/jovyan/software/seamless/graphs/status-visualization.zip DEFAULT-status.zip
docker cp $container:/home/jovyan/software/seamless/graphs/status-visualization.seamless DEFAULT-status.seamless
# /Run

seamless-add-zip DEFAULT-status.zip

rm DEFAULT-status.zip
docker rm $container