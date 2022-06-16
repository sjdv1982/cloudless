import os, sys, subprocess, json

currdir = os.path.split(os.path.abspath(__file__))[0]
docker_cmd_dir = currdir + "/../docker/commands"

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


def start_jobslave(name,remote, master_ip):
    
    if remote:
        cmd = "{}/cloudless-jobslave-remote {} {}".format(docker_cmd_dir,name, master_ip)
    else:
        cmd = "{}/cloudless-jobslave {}".format(docker_cmd_dir,name)
    
    # TODO: adapt seamless-jobslave so that cloudless-jobslaveX is accommodated as params...
    # cmd = "seamless-jobslave {} --database".format(name)
    
    err, output = subprocess.getstatusoutput(cmd)
    if err != 0:
        print(output, file=sys.stderr)
        raise RuntimeError("Error code {}".format(err))

def main(nslaves, name_template, remote, ip, master_ip):    
    if not remote:
        ip = get_bridge_ip()
    var = ""
    for n in range(nslaves):
        name = "{}-{}".format(name_template, n+1)
        start_jobslave(name,remote, master_ip)
        ephemeral_port = get_ephemeral_port(name)
        assert ephemeral_port is not None
        if n > 0:
            var += ","
        var += "{}:{}".format(ip, ephemeral_port)
    print(var)

if __name__ == "__main__":
    import sys, argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("nslaves", type=int)
    parser.add_argument("name_template", nargs="?", default="cloudless-jobslave")
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--master-ip", help="IP address of the master node")
    parser.add_argument("--ip", help="IP address of the current node, as visible from the master")
    args = parser.parse_args()
    if args.remote and not args.ip:
        raise ValueError("--remote requires --ip")
    if args.remote and not args.master_ip:
        raise ValueError("--remote requires --master-ip")
    main(args.nslaves, args.name_template, args.remote, args.ip, args.master_ip)
