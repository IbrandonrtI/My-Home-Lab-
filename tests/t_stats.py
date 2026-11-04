#!/usr/bin/env python3
"""Tests of scripts/homelab-stats: the numbers for the STATS tab. Immich and Nextcloud are small real web servers on this machine,
docker / smartctl / lsblk are stand-ins, the pools are plain folders. Nothing outside a temp folder is touched.
Run: python3 tests/t_stats.py   (last line is OK or FAIL)"""
import http.server
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.join(HERE, "..", "scripts", "homelab-stats")
bad = 0


def check(name, ok, extra=""):
    global bad
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   " + str(extra)[:600]))


IMMICH = {"photos": 12345, "videos": 678, "usage": 5 * 1024 ** 3, "usageByUser": [{"a": 1}, {"b": 2}]}
NEXTCLOUD = {"ocs": {"data": {"nextcloud": {"storage": {"num_files": 4321}, "shares": {"num_shares": 7},
                                            "system": {"freespace": 200 * 1024 ** 3}}, "activeUsers": {"last24hours": 2}}}}


class Web(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        seen = self.server.seen
        seen.append((self.path, self.headers.get("x-api-key"), self.headers.get("NC-Token")))
        if self.server.down:
            self.send_response(500)
            self.end_headers()
            return
        body = IMMICH if self.path.startswith("/api/server/statistics") else NEXTCLOUD
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *a):
        pass


def port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def script(path, text):
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


T = tempfile.mkdtemp(prefix="t_stats_")
try:
    hp = os.path.join(T, "hp")
    os.makedirs(os.path.join(hp, "images"))
    state = os.path.join(T, "state")
    os.makedirs(state)
    main = os.path.join(T, "storage")
    backup = os.path.join(T, "backup")
    for d in ("nextcloud", "immich"):
        os.makedirs(os.path.join(main, d))
    os.makedirs(backup)
    with open(os.path.join(main, "nextcloud", "a.bin"), "wb") as f:
        f.write(b"x" * 3000)
    with open(os.path.join(main, "immich", "b.bin"), "wb") as f:
        f.write(b"y" * 5000)
    p = port()
    srv = http.server.HTTPServer(("127.0.0.1", p), Web)
    srv.seen, srv.down = [], False
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    with open(os.path.join(hp, "services.yaml"), "w") as f:
        f.write("""- Files & Photos:
    - Immich:
        id: immich-card
        widget:
          type: immich
          url: http://127.0.0.1:%d
          key: immich-secret
          version: 2
    - Nextcloud:
        id: nextcloud-card
        widget:
          type: nextcloud
          url: http://127.0.0.1:%d
          key: nc-secret
""" % (p, p))
    with open(os.path.join(state, "homepage-dir"), "w") as f:
        f.write(hp + "\n")
    with open(os.path.join(state, "image-updates"), "w") as f:
        f.write("%d\nnextcloud  new image\n" % int(time.time() - 2 * 86400))
    with open(os.path.join(state, "apt"), "w") as f:
        f.write("3|%d\n" % int(time.time()))
    with open(os.path.join(state, "temps"), "w") as f:
        f.write("MAIN1|/dev/sdb|36|%d\nBACKUP1|/dev/sdc|41|%d\n" % (time.time(), time.time()))
    bk = os.path.join(T, "last-run")
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - 3 * 3600))
    with open(bk, "w") as f:
        f.write("%s|OK|/mnt/backup|72|%d\n" % (when, 3 * 1024 ** 3))

    bindir = os.path.join(T, "bin")
    os.makedirs(bindir)
    script(os.path.join(bindir, "docker"), """#!/bin/sh
case "$1" in
  ps) printf 'immich|running|Up 2 days\\nnextcloud|running|Up 2 days (unhealthy)\\nold|exited|Exited (0) 3 days ago\\n' ;;
  inspect) exit 1 ;;
esac
""")
    script(os.path.join(bindir, "lsblk"), """#!/bin/sh
case "$*" in
  *-dno*) printf 'sdb disk\\nsdc disk\\nsda disk\\n' ;;
  *sdb) echo 'LABEL="MAIN1" MOUNTPOINT="/mnt/disks/MAIN1"' ;;
  *sdc) echo 'LABEL="BACKUP1" MOUNTPOINT="/mnt/disks/BACKUP1"' ;;
  *sda) echo 'LABEL="" MOUNTPOINT="/"' ;;
esac
""")
    smart = os.path.join(T, "smart-mode")
    with open(smart, "w") as f:
        f.write("passed")
    script(os.path.join(bindir, "smartctl"), """#!/bin/sh
m=$(cat "%s")
case "$m" in
  passed) echo 'SMART overall-health self-assessment test result: PASSED' ;;
  failed) echo 'SMART overall-health self-assessment test result: FAILED!' ;;
  asleep) echo 'Device is in STANDBY mode, exit(2)'; exit 2 ;;
esac
""" % smart)

    out = os.path.join(hp, "images", "stats.json")
    env = dict(os.environ, PATH=bindir + ":" + os.environ["PATH"], HOMELAB_STATE_DIR=state, HOMELAB_MAIN_POOL=main,
               HOMELAB_BACKUP_POOL=backup, HLU_BACKUP_STATUS=bk, HOMELAB_STATS_NOMOUNT="1", HOMELAB_STATS_LOCK=os.path.join(T, "lock"),
               HOMELAB_STATS_OUT=out)

    def run(*a):
        return subprocess.run([sys.executable, PROG] + list(a), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True, timeout=120)

    def load():
        with open(out) as f:
            return json.load(f)

    # --- a first run
    r = run()
    check("runs and exits 0", r.returncode == 0, r.stdout)
    d = load()
    check("Immich totals", d["immich"]["photos"] == "12,345" and d["immich"]["videos"] == "678" and d["immich"]["storage"] == "5.0 GB"
          and d["immich"]["users"] == "2", d["immich"])
    check("Nextcloud totals", d["nextcloud"]["files"] == "4,321" and d["nextcloud"]["shares"] == "7" and d["nextcloud"]["free"] == "200 GB"
          and d["nextcloud"]["users"] == "2", d["nextcloud"])
    check("the keys from the cards are used", ("/api/server/statistics", "immich-secret", None) in srv.seen
          and any(s[2] == "nc-secret" for s in srv.seen), srv.seen)
    check("pool space", d["main"]["percent"].endswith("%") and d["main"]["total"] != "-" and d["backup"]["free"] != "-", d["main"])
    check("health is Healthy", d["main"]["health"] == "Healthy" and d["backup"]["health"] == "Healthy", (d["main"], d["backup"]))
    check("drive list keeps the temperature", {x["label"]: x["temp"] for x in d["drives"]} == {"MAIN1": 36, "BACKUP1": 41}, d["drives"])
    lb = d["last_backup"]
    check("last backup", lb["result"] == "OK" and lb["size"] == "3.0 GB" and lb["took"] == "1 min 12 s" and lb["ago"] == "3 h ago", lb)
    check("containers", d["containers"]["running"] == "2 of 3" and "1 stopped" in d["containers"]["problems"]
          and "1 unhealthy" in d["containers"]["problems"], d["containers"])
    check("updates", d["updates"]["images"] == "1 waiting" and d["updates"]["system"] == "3 waiting" and d["updates"]["total"] == "4"
          and d["updates"]["checked"] == "2 days ago", d["updates"])
    check("folder sizes are counted", d["folders"]["nextcloud"].endswith(" KB") and d["folders"]["immich"].endswith(" KB"), d["folders"])
    check("glance row", d["glance"]["photos"] == "12,345" and d["glance"]["files"] == "4,321" and d["glance"]["containers"] == "2 of 3"
          and d["glance"]["updates"] == "4", d["glance"])
    check("file is readable by everyone", os.stat(out).st_mode & 0o044 == 0o044)

    # --- every field the STATS cards of the dashboard ask for is in the file, as text
    try:
        import yaml
    except ImportError:
        yaml = None
    if yaml:
        with open(os.path.join(HERE, "..", "homepage-config", "services.yaml")) as f:
            groups = yaml.safe_load(f)
        fields = []
        for g in groups:
            for cards in g.values():
                for c in cards or []:
                    for card in c.values():
                        w = card.get("widget") or {}
                        if w.get("type") == "customapi":
                            fields += [mp["field"] for mp in w["mappings"]]
        missing = []
        for fld in fields:
            v = d
            for part in fld.split("."):
                v = v.get(part) if isinstance(v, dict) else None
            if not isinstance(v, str) or v == "":
                missing.append(fld)
        check("every field of the STATS cards is in the file as text (%d fields)" % len(fields), len(fields) >= 30 and not missing, missing)
    else:
        print("skip  (no PyYAML here) the fields of the STATS cards")

    # --- folder sizes are only counted again when something changed
    cache_file = os.path.join(state, "stats-folders.json")
    with open(cache_file) as f:
        cache = json.load(f)
    at0 = cache["nextcloud"]["at"]
    time.sleep(1.1)
    run()
    with open(cache_file) as f:
        check("nothing changed: not counted again", json.load(f)["nextcloud"]["at"] == at0)
    with open(os.path.join(main, "nextcloud", "c.bin"), "wb") as f:
        f.write(b"z" * 2000)
    for k in cache:
        cache[k]["fp"] = -1                      # "the pool's used space changed" ... but less than an hour ago
    with open(cache_file, "w") as f:
        json.dump(cache, f)
    run()
    with open(cache_file) as f:
        c2 = json.load(f)
    check("changed but counted less than an hour ago: waits", c2["nextcloud"]["at"] == at0, c2["nextcloud"])
    for k in c2:
        c2[k]["at"] -= 7200
    at1 = c2["nextcloud"]["at"]
    with open(cache_file, "w") as f:
        json.dump(c2, f)
    run()
    with open(cache_file) as f:
        c3 = json.load(f)
    check("changed and older than an hour: counted again", c3["nextcloud"]["at"] > at1 and c3["nextcloud"]["bytes"] >= 5000, c3["nextcloud"])
    for k in c3:
        c3[k]["at"] -= 7200
    at2 = c3["nextcloud"]["at"]
    with open(cache_file, "w") as f:
        json.dump(c3, f)
    run()
    with open(cache_file) as f:
        check("not changed and older than an hour: kept", json.load(f)["nextcloud"]["at"] == at2)

    # --- quick mode does not count
    os.remove(cache_file)
    r = run("quick")
    d = load()
    check("quick: sizes say Counting...", d["folders"]["immich"] == "Counting..." and not os.path.exists(cache_file), d["folders"])

    # --- the apps do not answer: the last good numbers stay
    run()
    srv.down = True
    run()
    d = load()
    check("an app that does not answer keeps the last numbers", d["immich"]["photos"] == "12,345" and d["nextcloud"]["files"] == "4,321", d["immich"])

    # --- health
    with open(smart, "w") as f:
        f.write("failed")
    run()
    d = load()
    check("a failing drive is shown", d["main"]["health"].startswith("PROBLEM") and d["backup"]["health"].startswith("PROBLEM"), d["main"])
    with open(smart, "w") as f:
        f.write("passed")
    run()
    with open(smart, "w") as f:
        f.write("asleep")
    run()
    d = load()
    check("a sleeping drive keeps its last health", d["main"]["health"] == "Healthy", d["main"])

    # --- a pool that is not connected
    shutil.rmtree(backup)
    run()
    d = load()
    check("backup pool not connected", d["backup"]["health"] == "Not connected" and d["folders"]["backup"] == "Not connected", (d["backup"], d["folders"]))

    # --- no backup yet
    os.remove(bk)
    run()
    d = load()
    check("no backup yet", d["last_backup"]["when"] == "Never", d["last_backup"])

    # --- help
    r = run("nonsense")
    check("an unknown option is refused", r.returncode == 1 and "Usage" in r.stdout, r.stdout)
    r = run("version")
    check("version", r.stdout.startswith("homelab-stats "), r.stdout)
finally:
    shutil.rmtree(T, ignore_errors=True)

print("OK" if bad == 0 else "FAIL (%d)" % bad)
sys.exit(1 if bad else 0)
