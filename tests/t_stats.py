#!/usr/bin/env python3
"""Tests of scripts/homelab-stats: the numbers for the STATS tab. Immich and Nextcloud are small real web servers on this machine,
docker / smartctl / lsblk are stand-ins, the pools are plain folders. Nothing outside a temp folder is touched.
Run: python3 tests/t_stats.py   (last line is OK or FAIL)"""
import http.server
import re
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
    music = os.path.join(main, "music")
    os.makedirs(os.path.join(music, "Artist C", "Album"))
    for name, size in (("Artist A - Song One.mp3", 1000), ("Artist A, Guest - Song Two.mp3", 2000), ("Artist B - Song Three.flac", 4000),
                       ("cover.jpg", 9999), ("Artist C/Album/track.mp3", 8000)):
        with open(os.path.join(music, name), "wb") as f:
            f.write(b"m" * size)
    import datetime
    noon = lambda back: datetime.datetime.combine(datetime.date.today() - datetime.timedelta(days=back), datetime.time(12)).timestamp()
    for name, back in (("Artist A - Song One.mp3", 0), ("Artist A, Guest - Song Two.mp3", 1), ("Artist B - Song Three.flac", 3), ("Artist C/Album/track.mp3", 20)):
        os.utime(os.path.join(music, name), (noon(back), noon(back)))
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
        f.write("BACKUP1|/dev/sdc|41|%d\nMAIN1|/dev/sdb|36|%d\nboot|/dev/sda|30|%d\n" % (time.time(), time.time(), time.time()))
    bk = os.path.join(T, "last-run")
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - 3 * 3600))
    with open(bk, "w") as f:
        f.write("%s|OK|%s|72|%d\n" % (when, backup, 3 * 1024 ** 3))

    bindir = os.path.join(T, "bin")
    os.makedirs(bindir)
    script(os.path.join(bindir, "docker"), """#!/bin/sh
case "$1" in
  ps) case "$*" in
        *Image*) printf 'downtify|ghcr.io/example/downtify:latest\\n' ;;
        *) printf 'immich|running|Up 2 days\\nnextcloud|running|Up 2 days (unhealthy)\\nold|exited|Exited (0) 3 days ago\\n' ;;
      esac ;;
  inspect) case "$*" in *Destination*Source*|*Mounts*) printf '/music|%s\\n/config|/nowhere\\n' "$HL_TEST_MUSIC" ;; *) exit 1 ;; esac ;;
esac
""")
    script(os.path.join(bindir, "lsblk"), """#!/bin/sh
case "$*" in
  *-dno*) printf 'sdb disk\\nsdc disk\\nsda disk\\n' ;;
  *sdb) echo 'LABEL="MAIN1" MOUNTPOINT="/mnt/disks/MAIN1"' ;;
  *sdc) [ -e "%s" ] || echo 'LABEL="BACKUP1" MOUNTPOINT="/mnt/disks/BACKUP1"' ;;
  *sda) echo 'LABEL="" MOUNTPOINT="/"' ;;
esac
""" % os.path.join(T, "no-backup-drive"))
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
               HOMELAB_STATS_OUT=out, HL_TEST_MUSIC=music)

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
    check("Immich totals", d["immich"]["photos"] == "12,345" and d["immich"]["videos"] == "678" and d["immich"]["storage"] == "5.4 GB"
          and d["immich"]["users"] == "2", d["immich"])
    check("Nextcloud totals", d["nextcloud"]["files"] == "4,321" and d["nextcloud"]["shares"] == "7" and d["nextcloud"]["free"] == "215 GB"
          and d["nextcloud"]["users"] == "2", d["nextcloud"])
    check("the keys from the cards are used", ("/api/server/statistics", "immich-secret", None) in srv.seen
          and any(s[2] == "nc-secret" for s in srv.seen), srv.seen)
    check("pool space", d["main"]["percent"].endswith("%") and d["main"]["total"] != "-" and d["backup"]["free"] != "-", d["main"])
    check("health is Healthy", d["main"]["health"] == "Healthy" and d["backup"]["health"] == "Healthy", (d["main"], d["backup"]))
    check("drive list keeps the temperature", {x["label"]: x["temp"] for x in d["drives"]} == {"MAIN1": 36, "BACKUP1": 41}, d["drives"])
    check("drive temperatures: boot first, then main, then backup", [(x["name"], x["label"]) for x in d["temps"]]
          == [("Boot Drive", "30 °C"), ("Main 1", "36 °C"), ("Backup 1", "41 °C")], d["temps"])
    check("the Updated text is a clock time", re.match(r"^\d{1,2}:\d{2} (AM|PM)$", d["updated_text"]) is not None, d["updated_text"])
    check("music library: songs, artists, size (found through the Downtify container)", d["music"]["songs"] == "4" and d["music"]["artists"] == "3"
          and d["music"]["size"] == "15.0 KB" and d["music"]["folder"] == music, d["music"])
    rec = d["music"]["recent"]
    check("recently saved songs: newest first, with when", [(x["name"], x["label"]) for x in rec][:3] == [
        ("Artist A - Song One", "Today"), ("Artist A, Guest - Song Two", "Yesterday"), ("Artist B - Song Three", "3 days ago")]
          and rec[3]["name"] == "track" and re.match(r"^[A-Z][a-z]{2} \d{1,2}$", rec[3]["label"]) and len(rec) == 4, rec)
    check("last backup saved to the backup pool", d["last_backup"]["saved_to"] == "Backup pool" and d["glance"]["backup_saved"] == "Backup pool", d["last_backup"])
    lb = d["last_backup"]
    check("last backup", lb["result"] == "OK" and lb["size"] == "3.2 GB" and lb["took"] == "1 min 12 s" and lb["ago"] == "3 h ago", lb)
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
                            if isinstance(w["mappings"], dict):          # a list card (display: dynamic-list): the list itself must be in the file
                                fields.append(w["mappings"]["items"])
                            else:
                                fields += [mp["field"] for mp in w["mappings"]]
        missing = []
        for fld in fields:
            v = d
            for part in fld.split("."):
                v = v.get(part) if isinstance(v, dict) else None
            if fld in ("temps", "music.recent"):
                if not (isinstance(v, list) and v and all(isinstance(x.get("name"), str) and isinstance(x.get("label"), str) for x in v)):
                    missing.append(fld)
            elif not isinstance(v, str) or v == "":
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

    # --- the temperatures: sleeping, warm, hot, none
    with open(os.path.join(state, "temps"), "w") as f:
        f.write("MAIN1|/dev/sdb|standby|1\nBACKUP1|/dev/sdc|52|1\nboot|/dev/sda|63|1\nWDC_Blue|/dev/sdd|40|1\n")
    run()
    d = load()
    check("temperatures: Resting, Warm, Hot, a model name", [(x["name"], x["label"]) for x in d["temps"]]
          == [("Boot Drive", "63 °C, Hot"), ("Main 1", "Resting"), ("Backup 1", "52 °C, Warm"), ("WDC Blue", "40 °C")], d["temps"])
    with open(os.path.join(state, "temps"), "w") as f:
        f.write("boot|/dev/sda|30|1\nMAIN1|/dev/sdb|36|1\nCruzer_Flash|/dev/sdc|none|1\n")
    run()
    d = load()
    check("temperatures: an array drive without a reading is listed as No Reading", [(x["name"], x["label"]) for x in d["temps"]]
          == [("Boot Drive", "30 °C"), ("Main 1", "36 °C"), ("Cruzer Flash", "No Reading")], d["temps"])
    os.remove(os.path.join(state, "temps"))
    run()
    check("no readings yet is said in words", load()["temps"] == [{"name": "No readings yet", "label": ""}])

    # --- the music folder: chosen by hand, changed, missing
    os.makedirs(os.path.join(T, "mine"))
    with open(os.path.join(T, "mine", "Solo - One.opus"), "wb") as f:
        f.write(b"z" * 2048)
    with open(os.path.join(state, "music-dir"), "w") as f:
        f.write(os.path.join(T, "mine") + "\n")
    run()
    d = load()
    check("a folder in /var/lib/homelab/music-dir is used first", d["music"]["songs"] == "1" and d["music"]["artists"] == "1" and d["music"]["size"] == "2.0 KB", d["music"])
    with open(os.path.join(state, "music-dir"), "w") as f:
        f.write(os.path.join(T, "does-not-exist") + "\n")
    run()
    d = load()
    check("a chosen folder that is not there says Not found", d["music"]["songs"] == "Not found" and d["music"]["size"] == "-", d["music"])
    os.remove(os.path.join(state, "music-dir"))
    run()
    check("the choice removed: the folder of the Downtify container again", load()["music"]["songs"] == "4")
    run("quick")
    check("quick: a library that was counted is shown from the cache", load()["music"]["songs"] == "4")

    # --- a backup that went to the boot drive
    with open(bk, "w") as f:
        f.write("%s|OK|%s|72|%d\n" % (when, os.path.join(T, "boot-drive-files", "backup-interim"), 5 * 1024 ** 3))
    run()
    d = load()
    check("a backup in the boot-drive fallback folder is called that", d["last_backup"]["saved_to"] == "Boot drive"
          and d["last_backup"]["saved_note"] == "Boot drive (no backup drive connected)" and d["glance"]["backup_saved"] == "Boot drive", d["last_backup"])

    # --- a backup folder without a backup drive
    open(os.path.join(T, "no-backup-drive"), "w").close()
    run()
    d = load()
    check("no backup drive: Not connected, not 0% and not No drives found", d["backup"]["health"] == "Not connected" and d["backup"]["percent"] == "Not connected"
          and d["glance"]["backup_pct"] == "Not connected" and d["backup"]["used"] == "-" and d["folders"]["backup"] == "Not connected", (d["backup"], d["glance"]))
    check("the main pool is still shown", d["main"]["percent"].endswith("%") and d["main"]["health"] == "Healthy", d["main"])
    os.remove(os.path.join(T, "no-backup-drive"))

    # --- a pool that is not connected
    shutil.rmtree(backup)
    run()
    d = load()
    check("backup pool not connected", d["backup"]["health"] == "Not connected" and d["folders"]["backup"] == "Not connected", (d["backup"], d["folders"]))
    check("and its percent says so", d["backup"]["percent"] == "Not connected" and d["glance"]["backup_pct"] == "Not connected", d["glance"])

    # --- no backup yet
    os.remove(bk)
    run()
    d = load()
    check("no backup yet", d["last_backup"]["when"] == "Never" and d["last_backup"]["saved_to"] == "-", d["last_backup"])

    # --- the times are shown in the time zone of the weather city (the server may keep UTC), and the sizes use the units a drive is sold in
    os.makedirs(backup, exist_ok=True)
    with open(bk, "w") as f:
        f.write("%s|OK|%s|72|%d\n" % (time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - 3 * 3600)), backup, 3 * 1000 ** 3))
    import zoneinfo
    env["HOMELAB_DISPLAY_TZ"] = "Pacific/Kiritimati"
    run()
    d = load()
    now_k = datetime.datetime.now(zoneinfo.ZoneInfo("Pacific/Kiritimati"))
    ok_clock = {t.strftime("%I:%M %p").lstrip("0") for t in (now_k, now_k - datetime.timedelta(minutes=1))}
    check("the Updated time is the clock of the chosen time zone", d["updated_text"] in ok_clock, (d["updated_text"], ok_clock))
    check("the last backup is told in that time zone too", re.match(r"^(Today|Yesterday) \d\d:\d\d$", d["last_backup"]["when"]) is not None, d["last_backup"])
    check("sizes are decimal: 3,000,000,000 bytes are 3.0 GB", d["last_backup"]["size"] == "3.0 GB", d["last_backup"])
    del env["HOMELAB_DISPLAY_TZ"]
    with open(os.path.join(hp, "widgets.yaml"), "w") as f:
        f.write("- openmeteo:\n    label: \"New York\"\n    latitude: 40.7143\n    longitude: -74.0060\n    units: imperial\n- search:\n    provider: google\n")
    with open(os.path.join(state, "display-timezone"), "w") as f:
        f.write("40.7143,-74.0060 Asia/Tokyo %d\n" % int(time.time()))
    run()
    d = load()
    now_t = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Tokyo"))
    check("the time zone of the weather pill is remembered and used", d["updated_text"] in {t.strftime("%I:%M %p").lstrip("0") for t in (now_t, now_t - datetime.timedelta(minutes=1))}, d["updated_text"])

    # --- a RAID or ZFS Main pool: its health is the array's, not "No drives found"
    os.remove(os.path.join(state, "display-timezone"))
    script(os.path.join(bindir, "zpool"), "#!/bin/sh\necho ONLINE\n")
    dstate = os.path.join(os.path.dirname(state), "drives-state")      # (where `drives` keeps its notes: not the folder of the readings)
    os.makedirs(dstate, exist_ok=True)
    env["HOMELAB_DRIVES_STATE_DIR"] = dstate
    with open(os.path.join(dstate, "preset"), "w") as f:
        f.write("zfs-stripe|2026-11-09|sdc,sdd\n")
    script(os.path.join(bindir, "lsblk"), "#!/bin/sh\ncase \"$*\" in\n  *-dno*) printf 'sda disk\\n' ;;\n  *sda) echo 'LABEL=\"\" MOUNTPOINT=\"/\"' ;;\nesac\n")
    run()
    d = load()
    check("a ZFS Main pool says Healthy", d["main"]["health"] == "Healthy" and d["main"]["drives"] == "ZFS", d["main"])
    script(os.path.join(bindir, "zpool"), "#!/bin/sh\necho DEGRADED\n")
    run()
    check("a degraded ZFS Main pool is a problem", load()["main"]["health"].startswith("PROBLEM"), load()["main"])

    # --- help
    r = run("nonsense")
    check("an unknown option is refused", r.returncode == 1 and "Usage" in r.stdout, r.stdout)
    r = run("version")
    check("version", r.stdout.startswith("homelab-stats "), r.stdout)
finally:
    shutil.rmtree(T, ignore_errors=True)

print("OK" if bad == 0 else "FAIL (%d)" % bad)
sys.exit(1 if bad else 0)
