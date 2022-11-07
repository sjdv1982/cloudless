# cloudless

Web framework on top of Seamless.

## How it works

Cloudless launches *web service instances* from *web service templates*.
Each template is a .seamless workflow graph file.
Each instance runs in a Docker container launched by Cloudless. 
The Docker container must be able to connect to a Seamless database, and potentially to Jobless.
Network traffic (HTTP GET and PUT requests) and their responses are redirected into/from the container.
Each instance has its workflow graph monitored, and regularly saved.
By default, instance containers are killed after 10 minutes of no network activity. This does not cancel any job that they have launched.
Instances are restarted dynamically by Cloudless upon network activity

The underlying buffers of the web service templates must already be in the database. You are recommended to copy them as .zip files
into the /zips directory, and add them using `seamless-add-zip`.

Cloudless has an admin interface under /admin, to kill instances etc.

Instances themselves (/instance/.../) are accessible to everyone, also for modification.

The `connect-instance` script registers a Docker container running on the same machine as Cloudless, but that was not launched by Cloudless, as a Cloudless instance. This is done by a PUT request on the "/connect_instance" URL.

The `cloudless-to-cloudless` script creates a web socket that connects a local Cloudless server to a remote Cloudless server. The local Cloudless server can be reached using /proxy/.../. This is done by a PUT request on the "/connect_to_cloudless" URL. See the "Cloudless-to-Cloudless" section below.


## Installation

- Pull the Seamless Docker image (`docker pull rpbs/seamless`)

- Create a new Python environment with seamless-cli and silk  in it:
`conda create -n cloudless -c rpbs -c conda-forge python==3.8 seamless-cli silk -y && conda activate cloudless`

- Install Cloudless requirements with `pip install -r requirements.txt`.

- Define the following variables in your .bashrc:  
  - $CLOUDLESS_GRAPHS_DIR
  (where you will store the service template graphs)
  - $CLOUDLESS_ZIPS_DIR
  (where you will store the zipped buffers of the service template graph)
  - $CLOUDLESS_INSTANCES_DIR
  (where you will store the service instance graphs)
  
- Make sure that the Seamless database is running, e.g. with `seamless-database`.
  If the Seamless database runs on a remote machine, define $SEAMLESS_DATABASE_IP in your .bashrc, and if necessary, $SEAMLESS_DATABASE_PORT.

- If you use jobless, make sure that it is running.
  If jobless runs on a remote machine, define $SEAMLESS_COMMUNION_IP in your .bashrc, and if necessary, $SEAMLESS_COMMUNION_PORT.

- Run `init.sh` . This will create the CLOUDLESS_XXX_DIR directories and populate them with the default status visualization graph.
  It is not necessary (but harmless) to re-run init.sh every time you start Cloudless. You must however re-run init.sh whenever you update Seamless (with `docker pull rpbs/seamless`)

- Start Cloudless. You have the choice between:
    - `start-cloudless-fat.sh` . All computation is done locally by the instance Docker containers themselves.
    - `start-cloudless-jobless.sh` . All computation is done by Jobless. Failure to delegate a computation to Jobless results in an error. This is appropriate if Jobless has been configured with support for generic transformations.
    - `start-cloudless-fat-jobless.sh` . Computation is done by Jobless. A computation that cannot be delegated to Jobless will be done locally by the instance Docker container itself.

Cloudless runs on port 3124. Open http://localhost:3124/ to access it. Open http://localhost:3124/admin to access the admin interface.

## Deploying services

This can be done while Cloudless is running.

1. In Seamless, export your workflow with `ctx.save_graph(...)` to create a .seamless file. If you use a Seamless project, the graph will be available in \<project dir\>/graphs/\<project name\>.seamless . Copy this into $CLOUDLESS_GRAPHS_DIR.

2. In Seamless, export your workflow buffers with `ctx.save_zip(...)`. Then, copy the .zip file into $CLOUDLESS_ZIPS_DIR (not strictly necessary). Finally, add the buffers to the database with `seamless-add-zip` \<name of zipfile\>.

Step 2. can be omitted if your workflow takes huge datasets as input. In that case, you must copy yourself the required buffers (e.g. from a Seamless vault) into the /buffers directory of the Seamless database

3. Repeat step 1. and 2. for the custom web status workflow, if you have it. If you use a Seamless project, the graph will be available in \<project dir\>/graphs/\<project name\>-webctx.seamless . Copy this into $CLOUDLESS_GRAPHS_DIR. To create the zip file, run `seamless-load-project` and then do `webctx.save_zip(...)`

4. In the admin interface, refresh the list of services.

## Nginx setup

Cloudless runs under under port 3124 andlistens only for local connections, so you can't connect to it from another machine.
If you want to run a public Cloudless server, you want to accept public connections, coming in under port 80, potentially using HTTPS. 
To set that up, you need a reverse proxy, listening on port 80 and redirecting traffic to port 3124. This can be done using Nginx, follow the instructions in `nginx/README.md` .

## Cloudless-to-Cloudless communication

(experimental!)

With a public Cloudless server accessible via http://myserver.com/cloudless, you can connect a local Cloudless instance to it. The syntax is `$CLOUDLESSDIR/cloudless-to-cloudless http://localhost:3124 ws://myserver.com/cloudless PROXYNAME`. As long as cloudless-to-cloudless is running, a URL such as `http://myserver.com/cloudless/proxy/PROXYNAME/1234567` is redirected to `http://localhost:3124/instance/1234567`. The proxying is done by cloudless-to-cloudless, much like an SSH tunnel, i.e. no public IP address or URL for the local machine is needed. (This is in contrast to `$CLOUDLESSDIR/connect_instance`, where the ports are on the *public server*, not on the local machine that calls `connect_instance`).

Only Seamless instances are proxied; the admin page or "create new instance" page is not.