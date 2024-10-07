# cloudless

Webserver on top of Seamless.

TODO: On Cloudless startup, check for proper env vars and contact assistant
TODO: check that seamless-serve-graph is available when Cloudless is launched

## How it works

Cloudless launches *web service instances* from *web service templates*.
Each template is a .seamless workflow graph file.
Each instance runs in a Docker container launched by Cloudless.
The Docker container must be able to connect to Seamless delegation (assistant, hashserver, database).
Network traffic (HTTP GET and PUT requests) and their responses are redirected into/from the container.
Each instance has its workflow graph monitored, and regularly saved.
By default, instance containers are killed after 10 minutes of no network activity. This does not cancel any job that they have launched.
Instances are restarted dynamically by Cloudless upon new network activity

The underlying buffers of the web service templates must already be in the database. You are recommended to upload them using cloudless-upload-zip.

Cloudless has an admin interface under /admin, to kill instances etc.

Instances themselves (/instance/.../) are accessible to everyone, also for modification.

## Installation

TODO: create rpbs/cloudless conda package.
TODO: make a seamless-cloudless Docker compose script with rpbs/cloudless and rpbs/seamless-cli in it.

- Pull the Seamless Docker image (`docker pull rpbs/seamless`)

- Create a new Python environment with seamless-cli in it:
`conda create -n cloudless -c rpbs -c conda-forge seamless-cli -y && conda activate cloudless`

- Install Cloudless dependencies. They are currently in meta.yaml.

- Define the following variables in your .bashrc:  
  - $CLOUDLESS_DEPLOYMENT_DIR
  - $CLOUDLESS_IP. Optional: defaults to 0.0.0.0 (all interfaces).
  
- Start up Seamless delegation. You can enable quick local delegation using `cloudless-delegate`. Else, set up `seamless-delegate-remote`.

- Start Cloudless with `./cloudless`.

- You can stop delegation with `cloudless-delegate-stop`.
  
Cloudless runs on port 3124. Open <http://localhost:3124/> to access it. Open <http://localhost:3124/admin> to access the admin interface.

## Deploying services

This can be done while Cloudless is running.

1. In Seamless, export your workflow graph. If you use a Seamless project, do `save()` and the graph will be available in \<project dir\>/graphs/\<project name\>.seamless . If you are not using a project, do `ctx.save_graph(...)` to create a .seamless file. Copy this into $CLOUDLESS_DEPLOYMENT_DIR/graphs.

2. In Seamless, export your workflow buffers. If you use a Seamless project, do `export()` and the graph will be available in \<project dir\>/graphs/\<project name\>.zip . If you are not using a project, do `ctx.save_zip(...)` to create a .zip file. Copy this into $CLOUDLESS_DEPLOYMENT_DIR/graphs.

3. Repeat step 1. and 2. for the web status workflow. If you use a Seamless project, the graph and zip will have been saved already in \<project dir\>/graphs/\<project name\>-webctx.seamless and ...-webctx.zip. If you are not using a project, you probably won't have such a workflow. If you do, and if it is called `webctx`, use `webctx.save_zip(...)` and `webctx.save_graph(...)`.

4. In the admin interface, refresh the list of services.

## Production environment: nginx setup

Cloudless runs under under port 3124. In production, you are recommended to set CLOUDLESS_IP to e.g. 'localhost' so that Cloudless listens only for local connections.
If you want to run a public Cloudless server, you want to accept public connections, coming in under port 80, potentially using HTTPS.
To set that up, you need a reverse proxy, listening on port 80 and redirecting traffic to port 3124. This can be done using Nginx, follow the instructions in `nginx/README.md` .
