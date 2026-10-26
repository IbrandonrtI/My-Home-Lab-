#!/usr/bin/env python3
"""Build a fake machine that looks like a server built by hand: everything running, built by hand, no installer state."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simlib
from simlib import DEFAULT

R = simlib.ROOT
H = R + "/home/testuser"
w = json.loads(json.dumps(DEFAULT))
stacks = {
 "adguard": ["adguardhome"], "beszel": ["beszel"], "beszel-agent": ["beszel-agent"], "netdata": ["netdata-netdata-1"],
 "speedtest-tracker": ["speedtest-tracker"], "filebrowser": ["filebrowser-filebrowser-1"],
 "immich": ["immich_server", "immich_postgres", "immich_machine_learning", "immich_redis"],
 "nextcloud": ["nextcloud", "nextcloud_db", "nextcloud_redis", "nextcloud_cron"], "homepage": ["homepage"]}
for st, cs in stacks.items():
    for c in cs:
        w["containers"][c] = {"image": "x", "stack": st, "running": True}
w["containers"]["portainer"] = {"image": "portainer/portainer-ce", "stack": "", "running": True}
w["pkgs"] += ["curl", "ca-certificates", "gnupg", "rsync", "cron", "python3-yaml", "smartmontools", "hdparm", "mergerfs", "parted", "docker-ce", "tailscale"]
w["bin"] = ["docker"]
w["units"].update({"systemd-resolved": "inactive", "tailscaled": "active", "docker": "active"})
w["users_in_docker"] = ["testuser"]
w["ts"].update(logged_in=True, approved=True, https=True, hostname="pc",
               serve={str(p): "http://192.168.50.23:%d" % port for p, port in
                      [(1000, 3001), (1001, 9000), (1002, 2283), (1003, 8090), (1004, 3000), (1005, 8082), (1006, 8081), (1007, 8088), (1008, 19999)]})
w["portainer"].update(admin="OldAdmin", pw="OldPassword1234", tokens={"ptr_EXISTINGKEY": "homepage"},
                      endpoints=[{"Id": 3, "Name": "local"}], stacks=[])
w["adguard"].update(configured=True, user="OldAdmin", pw="OldPassword1234")
w["immich"].update(user={"email": "b@example.com", "pw": "OldPassword1234", "name": "OldAdmin"}, keys={"imkey-EXISTING": ["server.statistics"]})
w["beszel"].update(users={"b@example.com": "OldPassword1234"}, superusers={"b@example.com": "OldPassword1234"})
w["nc"].update(calls=99, token="ncTOKENexisting", conf={"allow_local_remote_servers": "true"},
               domains={"1": "192.168.50.23", "2": "pc.sim-tail.ts.net"})
w["speedtest"]["tokens"] = ["st|EXISTING"]
w["fb"].update(user="OldAdmin", pw="OldPassword1234", gen="")
w["crontab"] = ""
os.makedirs(simlib.SIM, exist_ok=True)
json.dump(w, open(simlib.WORLD, "w"), indent=1)

def put(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(text)
    os.chmod(path, mode)

# folders
for d in ["/mnt/storage/immich", "/mnt/storage/filebrowser", "/mnt/storage/nextcloud", "/home/testuser/nextcloud/html",
          "/home/testuser/nextcloud/db", "/home/testuser/immich/postgres", "/home/testuser/speedtest-tracker",
          "/home/testuser/homepage-config", "/home/testuser/750GB_HDD", "/opt/adguard-docker/conf", "/opt/adguard-docker/work"]:
    os.makedirs(R + d, exist_ok=True)
put(R + "/opt/adguard-docker/conf/AdGuardHome.yaml",
    "http:\n  address: 0.0.0.0:3000\nusers:\n  - name: OldAdmin\n    password: $2a$10$x\ndns:\n  upstream_dns:\n    - https://dns.quad9.net/dns-query\n")
# Homepage config as it is on the real server: real values, real keys
repo = os.environ["REPO"]
svc = open(repo + "/homepage-config/services.yaml").read()
svc = svc.replace("192.168.X.X", "192.168.50.23").replace("pc.your-tailnet.ts.net", "pc.sim-tail.ts.net")
svc = svc.replace("username: your-own-key", "username: OldAdmin")
vals = iter(["OldPassword1234", "nTESTCNTRL", "tskey-api-VALID123", "b@example.com", "OldPassword1234",
             "st|EXISTING", "ptr_EXISTINGKEY", "OldPassword1234", "imkey-EXISTING", "ncTOKENexisting"])
out = []
for line in svc.split("\n"):
    if "your-own-key" in line or "your-email@example.com" in line:
        k = line.split(":")[0]
        line = k + ": " + next(vals)
    out.append(line)
svc = "\n".join(out)
put(H + "/homepage-config/services.yaml", svc)
for f in ["settings.yaml", "widgets.yaml", "bookmarks.yaml", "custom.css"]:
    put(H + "/homepage-config/" + f, open(repo + "/homepage-config/" + f).read())
# scripts as installed
sys.argv = ["x"]
for n, d in [("drives", "sbin"), ("homelab-backup", "sbin"), ("homelab-update", "sbin"), ("homelab-restore-configs", "sbin"),
             ("homelab-sample", "sbin"), ("hdd-recover", "bin"), ("homelab", "bin"), ("homelab-check", "bin")]:
    t = open(repo + "/scripts/" + n).read().replace("$(getent passwd 1000 | cut -d: -f1)", "testuser")
    put(R + "/usr/local/%s/%s" % (d, n), t, 0o755)
put(R + "/usr/local/sbin/homelab-setup", open(repo + "/installer/homelab-setup").read(), 0o755)
put(R + "/etc/homelab-backup.conf", 'DEST_FALLBACK="/home/testuser/750GB_HDD/backup-interim"\n')
put(H + "/.bashrc", "# existing\n\n# >>> homelab login display >>>\nif true; then\n  timeout 20 homelab\nfi\n# <<< homelab login display <<<\n")
put(simlib.SIM + "/crontab",
    "@reboot sleep 60 && /usr/local/sbin/drives power >/dev/null 2>&1\n0 6 * * * echo x >> /var/log/loadcycles.log\n"
    '@reboot sleep 60 && /usr/sbin/hdparm -B 254 "/dev/$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)")"\n'
    "0 6 * * * /usr/local/sbin/homelab-backup\n*/15 * * * * /usr/local/sbin/homelab-sample\n13 * * * * /usr/local/sbin/homelab-update auto\n")
# the typical pieces the program reads
os.makedirs(R + "/bin-dummy", exist_ok=True)
# symlinks for installed bins
inst = simlib.SIM + "/bin-installed"
os.makedirs(inst, exist_ok=True)
for b in ("docker", "tailscale", "tailscaled"):
    try: os.remove(inst + "/" + b)
    except OSError: pass
    os.symlink(os.path.dirname(os.path.abspath(__file__)) + "/fakecmd.py", inst + "/" + b)
print("existing machine built")
