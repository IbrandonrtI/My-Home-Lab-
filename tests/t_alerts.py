#!/usr/bin/env python3
"""Test of scripts/homelab-alerts (the file behind the bell): fake docker and tailscale commands, a made-up state folder and stats.json.
Run: python3 tests/t_alerts.py   (last line is OK or FAIL)"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "homelab-alerts")
bad = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   " + str(extra)[:300]))
    if not cond:
        bad.append(name)


def put(path, text, mode=None):
    with open(path, "w") as f:
        f.write(text)
    if mode:
        os.chmod(path, mode)


with tempfile.TemporaryDirectory() as d:
    state = os.path.join(d, "state")
    os.makedirs(state)
    out = os.path.join(d, "images", "alerts.json")
    docker = os.path.join(d, "docker")
    put(docker, "#!/bin/sh\ncat \"$DOCKER_LIST\"\n", 0o755)
    ts = os.path.join(d, "tailscale")
    put(ts, "#!/bin/sh\necho \"$TS_JSON\"\n", 0o755)
    lst = os.path.join(d, "ps.txt")
    stats = os.path.join(d, "stats.json")
    env = dict(os.environ, HOMELAB_STATE_DIR=state, HOMELAB_ALERTS_OUT=out, HOMELAB_STATS_IN=stats, HOMELAB_DOCKER=docker, HOMELAB_TAILSCALE=ts,
               HOMELAB_REBOOT_FILE=os.path.join(d, "no-reboot"), HOMELAB_ROOT_PATH=d, HOMELAB_BACKUP_STATUS=os.path.join(d, "last-run"),
               HOMELAB_APT_GET=os.path.join(d, "no-such-apt"), DOCKER_LIST=lst, TS_JSON=json.dumps({"BackendState": "Running"}))

    def run(args=()):
        return subprocess.run([sys.executable, SCRIPT] + list(args), capture_output=True, text=True, env=env, timeout=60)

    def items():
        with open(out) as f:
            return json.load(f)

    # everything fine: an empty list
    put(lst, "homepage|running|Up 2 days\nimmich_server|running|Up 2 days (healthy)\n")
    put(stats, json.dumps({"main": {"percent": "41%", "health": "Healthy", "free": "500 GB"}, "backup": {"percent": "30%", "health": "Healthy", "free": "600 GB"},
                           "last_backup": {"result": "OK", "when": "Today 06:00"}}))
    put(env["HOMELAB_BACKUP_STATUS"], time.strftime("%Y-%m-%d %H:%M", time.localtime()) + "|OK|/mnt/backup|60|1000\n")
    r = run()
    check("it runs and writes the file", r.returncode == 0 and os.path.exists(out), r.stderr)
    data = items()
    check("nothing to report on a healthy lab", data["items"] == [] and data["counts"] == {"bad": 0, "warn": 0, "info": 0}, data)
    check("the file is readable by everyone (the dashboard serves it)", (os.stat(out).st_mode & 0o444) == 0o444)

    # a stopped and an unhealthy container, updates, restart, pool problems, failed backup, hot drive, tailscale down
    put(lst, "homepage|running|Up 2 days\nimmich_server|exited|Exited (1) 3 minutes ago\nnavidrome|running|Up 1 hour (unhealthy)\nnetdata-netdata-1|running|Up 1 day\n")
    put(os.path.join(state, "image-updates"), "1700000000\nimmich  ghcr.io/x=new\nnextcloud  nc=new\n")
    put(os.path.join(state, "apt"), "7|2\n")
    put(env["HOMELAB_REBOOT_FILE"], "*** System restart required ***\n")
    put(os.path.join(state, "temps"), "boot|x|44\nMAIN1|x|63\nBACKUP1|x|52\nMAIN2|x|standby\n")
    put(stats, json.dumps({"main": {"percent": "96%", "health": "PROBLEM: check drives", "free": "40 GB"}, "backup": {"percent": "Not connected", "health": "Not connected"},
                           "last_backup": {"result": "Failed: see the log", "when": "Today 06:00"}}))
    env["TS_JSON"] = json.dumps({"BackendState": "Stopped"})
    r = run()
    data = items()
    ids = {i["id"]: i for i in data["items"]}
    check("a stopped container is reported as a problem with its status", ids.get("down:immich_server", {}).get("level") == "bad" and "Exited" in ids["down:immich_server"]["detail"], ids)
    check("its name is made readable", ids["down:immich_server"]["title"] == "Immich server is not running", ids["down:immich_server"])
    check("an unhealthy container is a warning", ids.get("sick:navidrome", {}).get("level") == "warn", ids)
    check("running containers are left out", "down:homepage" not in ids and "down:netdata-netdata-1" not in ids)
    check("container updates are listed with an update action", ids.get("updates:containers", {}).get("action") == "update" and "immich" in ids["updates:containers"]["detail"], ids)
    check("system updates are counted", "7 system updates" in ids.get("updates:system", {}).get("title", ""), ids)
    check("a needed restart is a warning", ids.get("restart", {}).get("level") == "warn", ids)
    check("a pool that is almost full is a problem", ids.get("main:space", {}).get("level") == "bad", ids)
    check("a drive with a problem is reported", ids.get("main:health", {}).get("level") == "bad", ids)
    check("a missing backup drive is only information", ids.get("backup:missing", {}).get("level") == "info", ids)
    check("a failed backup is a problem", ids.get("backup:failed", {}).get("level") == "bad", ids)
    check("a hot drive is a problem, a warm one a warning", ids.get("temp:MAIN1", {}).get("level") == "bad" and ids.get("temp:BACKUP1", {}).get("level") == "warn" and "temp:boot" not in ids, ids)
    check("a sleeping drive is not a temperature alert", "temp:MAIN2" not in ids)
    check("Tailscale that is not running is a problem", ids.get("tailscale", {}).get("level") == "bad", ids)
    levels = [i["level"] for i in data["items"]]
    check("the worst come first", levels == sorted(levels, key=lambda x: {"bad": 0, "warn": 1, "info": 2}[x]), levels)
    check("the counts match the items", data["counts"]["bad"] == levels.count("bad") and data["counts"]["info"] == levels.count("info"), data["counts"])

    # apt itself is asked for the count (the saved number is only refreshed every few hours)
    apt = os.path.join(d, "apt-get")
    put(apt, "#!/bin/sh\necho 'Inst a [1] (2)'\necho 'Inst b [1] (2)'\necho 'Conf a (2)'\n", 0o755)
    env["HOMELAB_APT_GET"] = apt
    run()
    check("the system update count comes from apt, not the old saved number", "2 system updates" in {i["id"]: i for i in items()["items"]}.get("updates:system", {}).get("title", ""), items())
    put(apt, "#!/bin/sh\necho 'Reading package lists...'\n", 0o755)
    run()
    check("nothing waiting in apt means no system update alert, even if the saved number is old", "updates:system" not in {i["id"] for i in items()["items"]}, items())
    env["HOMELAB_APT_GET"] = os.path.join(d, "no-such-apt")

    # an old backup, and the file never half written
    put(stats, json.dumps({"main": {"percent": "41%", "health": "Healthy"}, "backup": {"percent": "30%", "health": "Healthy"}, "last_backup": {"result": "OK", "when": "3 days ago"}}))
    put(env["HOMELAB_BACKUP_STATUS"], "2020-01-01 06:00|OK|/mnt/backup|60|1000\n")
    env["TS_JSON"] = json.dumps({"BackendState": "Running"})
    run()
    check("a backup older than a day is a warning", {i["id"] for i in items()["items"]} >= {"backup:late"}, items())
    check("no leftover temporary file", not os.path.exists(out + ".tmp"))

    # docker not answering
    put(docker, "#!/bin/sh\nexit 1\n", 0o755)
    run()
    check("Docker that does not answer is reported", any(i["id"] == "docker" for i in items()["items"]), items())

    # show prints, writes nothing new
    os.remove(out)
    r = run(["show"])
    check("show prints and writes nothing", r.returncode == 0 and "Docker does not answer" in r.stdout and not os.path.exists(out), r.stdout + r.stderr)
    r = run(["bogus"])
    check("an unknown word is refused", r.returncode == 1 and "Unknown option" in r.stderr, r.stderr)
    r = run(["help"])
    check("help works", r.returncode == 0 and "homelab-alerts" in r.stdout)

print("OK" if not bad else "FAIL")
sys.exit(1 if bad else 0)
