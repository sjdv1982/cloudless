import os, sys, subprocess, json

currdir = os.path.split(os.path.abspath(__file__))[0]
docker_cmd_dir = currdir + "/../docker/commands"
name_template = "cloudless-jobslave"

def get_bridge_ip():
    bridge = subprocess.getoutput("docker network inspect bridge")
    bridge = json.loads(bridge)
    return bridge[0]["IPAM"]["Config"][0]["Gateway"]

def get_ephemeral_port(name):
    output = subprocess.getoutput("docker port {}".format(name))
    for l in output.splitlines():
        fields = l.split("->")
        if len(fields) != 2:
            continue
        container_port = fields[0].strip()
        ff = fields[1].split(":")
        if len(ff) != 2:
            continue
        try:
            host_port = int(ff[1])
        except ValueError:
            continue
        if container_port == '8602/tcp':
            return host_port


def start_jobslave(name):
    err, output = subprocess.getstatusoutput(
        "{}/seamless-devel-jobslave {}".format(docker_cmd_dir,name)
    )
    if err != 0:
        print(output, file=sys.stderr)
        raise RuntimeError("Error code {}".format(err))

def main():
    bridge_ip = get_bridge_ip()
    var = ""
    for n in range(4):
        name = "{}-{}".format(name_template, n+1)
        start_jobslave(name)
        ephemeral_port = get_ephemeral_port(name)
        assert ephemeral_port is not None
        if n > 0:
            var += ","
        var += "{}:{}".format(bridge_ip, ephemeral_port)
    print(var)

if __name__ == "__main__":
    main()