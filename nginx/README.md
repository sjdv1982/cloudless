Installation and configuration of Cloudless under nginx
=======================================================

NOTE: Seamless does not use anything like CGI.
It receives HTTP user data over its REST API, either from the browser (Javascript)
or from command line. In fact, Seamless cannot tell the difference between requests
from the browser or from command line.

Seamless has a very liberal limit (1 GB) on max request sizes, allowing the upload
of large files. In contrast, nginx enforces a limit of 1 MB by default.
To adjust this, set "client_max_body_size" in your nginx configuration.

## Option A: run nginx in a Docker container

This container listens on http://localhost:80/cloudless, and forwards traffic to Cloudless (port 3124 on the host). Nothing else is done.
This is the best option if the Cloudless server is already behind an existing web server (nginx or apache) that takes care of
SSL, DDoS protection, etc.

- Go to the folder `docker/`.
- If necessary, adapt the `nginx.conf`. Note that the existing `nginx.conf` assumes that the Docker bridge network IP is 172.17.0.1.
- You can launch it as follows: `docker pull nginx && docker run --rm --name nginx-cloudless-container -p 80:80 -v $(pwd)/nginx.conf:/etc/nginx/nginx.conf:ro nginx`
- Alternatively, build the Docker image with `docker build -t nginx-cloudless . `
- Then, you can launch it as `docker run --rm --name nginx-cloudless-container -p 80:80 nginx-cloudless`
- In both cases, add a detach (`-d`) option if you don't want to keep the shell open.

## Option B: adding Cloudless to an existing nginx server

- Add the following to your main `nginx.conf` (inside the http block)

```
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}
```

- If necessary, adapt the `cloudless.conf`. Note that the existing conf assumes that nginx runs inside a Docker container connected to the default Docker network with IP 172.17.0.1. If it runs on bare metal, change the IP address to "localhost". 

- Add "cloudless.conf" to /etc/nginx. 

- Set up the server configuration.

If you have already a NGINX virtual server set up, just add `include /etc/nginx/cloudless.conf` to it.

If you don't have one: the following will set up a default port 80 virtual server that just listens to cloudless.

```
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    include /etc/nginx/cloudless.conf;
}
```

Put this in a file and save it (e.g. as `/etc/nginx/sites-available/cloudless`).
You may need to adapt it, adding HTTPS/SSL etc.
Add a soft-link to it in `/etc/nginx/sites-enabled`.

- Restart nginx
