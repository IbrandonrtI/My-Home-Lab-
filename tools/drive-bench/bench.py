#!/usr/bin/env python3
"""drive-bench - tries every drive command, option, answer and pool layout on fake (loop) drives and writes a report.

Run it with the launcher:   sudo tools/drive-bench/drive-bench [--level quick|standard|full] ...

How it works
  * Fake drives are files turned into drives with `losetup`. They get ext4 and are mounted by the REAL `drives` script in its
    test mode (DRIVES_TEST=1): its own test folders and test fstab. The real pools, /etc/fstab and the real containers are never
    touched by the drive tests. `docker`, `lsblk` (drive model and type), `hdparm`, `smartctl` and `mount` are replaced by fakes
    that only exist in the bench's own folder.
  * A layout is how many drives each pool has (0 to 5 or more), their types and sizes, what is on them and which spare drives are
    plugged in. The layout is built once with the real `connect` flow, saved, and copied back before every run that changed it.
  * Every command is run with scripted answers. The answers are explored like a tree: the first run answers nothing (so the
    first question is seen), then every answer that makes sense for that question is tried, and so on, most normal answers first.
  * After each run the bench checks the machine (fstab, mounts, pools, containers, files) and runs `drives status` as a health probe.
  * Everything goes to results.jsonl; report.py turns it into report.txt and report.html.
"""
import argparse
import collections
import fcntl
import hashlib
import itertools
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

# ---------------------------------------------------------------------------------------------------------------- drives
# (model, rotational, transport): what lsblk would say about a real drive; names in `drives` are made from these
MODELS = [
    ("TOSHIBA MQ01ABD100", 1, "sata"),
    ("Samsung SSD 870 EVO 500GB", 0, "sata"),
    ("WDC WD40EZRZ-00GXCB0", 1, "usb"),
    ("KINGSTON SA400S37480G", 0, "sata"),
    ("ST1000DM010-2EP102", 1, "sata"),
    ("", None, ""),                      # a drive that says nothing about itself
    ("Samsung SSD 970 EVO", 0, "nvme"),
]


SAFE_DEVS = set()      # the fake drives of this run: the only devices the bench may ever name in an 'erase' answer


class Drive:
    def __init__(self, size_mb=48, model=0, fs="pool", fill="few", label=None):
        self.size_mb = size_mb
        self.model = model if isinstance(model, tuple) else MODELS[model % len(MODELS)]
        self.fs = fs          # pool = connected with the real flow; blank | ext4data | vfat = a spare drive
        self.fill = fill      # empty | few | half | nearly | full
        self.label = label

    def spec(self):
        return "%dM/%s/%s/%s" % (self.size_mb, self.model[0] or "unknown", self.fs, self.fill)


class Layout:
    def __init__(self, name, main=0, backup=0, spares=(), boot=(), fill="few", sizes=None, models=None, note="", kind="pool"):
        self.name = name
        self.note = note
        self.kind = kind          # pool | legacy (one plain drive mounted at the main pool path, the old setup) | oldpool (a pool that fills evenly)
        self.fill = fill
        sizes = sizes or [48]
        models = models if models is not None else list(range(len(MODELS)))
        k = itertools.count()

        def make(n, fill):
            out = []
            for _ in range(n):
                i = next(k)
                out.append(Drive(sizes[i % len(sizes)], models[i % len(models)], "pool", fill))
            return out
        self.main = make(main, fill)
        self.backup = make(backup, fill)
        self.spares = [d if isinstance(d, Drive) else Drive(48, models[next(k) % len(models)], d, "few" if d == "ext4data" else "empty")
                       for d in spares]
        self.boot = tuple(boot)           # ("main",) ("backup",) ("main", "backup")

    @property
    def key(self):
        return self.name

    def all_drives(self):
        return self.main + self.backup + self.spares

    def describe(self):
        bits = ["%d main" % len(self.main), "%d backup" % len(self.backup)]
        if self.spares:
            bits.append("%d spare (%s)" % (len(self.spares), ", ".join(s.fs for s in self.spares)))
        if self.boot:
            bits.append("boot section: " + "+".join(self.boot))
        if self.fill != "few":
            bits.append("data: " + self.fill)
        if self.kind != "pool":
            bits.append({"legacy": "old setup: ONE plain data drive mounted at the main pool path",
                         "oldpool": "old pool that does not fill drive by drive",
                         "uneven": "the first main drive is 2/3 full, the second one is nearly empty"}[self.kind])
        return ", ".join(bits)


def layouts_for(level, only=None):
    L = []
    if level == "quick":
        pairs = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (2, 2), (3, 1), (5, 5)]
        spare_mix = ["blank"]
    elif level == "standard":
        pairs = [(m, b) for m in range(6) for b in range(6)] + [(6, 0), (0, 6), (8, 8)]
        spare_mix = ["blank", "ext4data"]
    else:
        pairs = [(m, b) for m in range(6) for b in range(6)] + [(6, 0), (0, 6), (6, 6), (8, 8)]
        spare_mix = ["blank", "ext4data", "vfat"]
    for m, b in pairs:
        L.append(Layout("m%d-b%d" % (m, b), m, b, spares=spare_mix))
    L.append(Layout("legacy-single-drive", 0, 0, spares=["ext4data", "blank"], kind="legacy", note="the old single data drive"))
    L.append(Layout("oldpool-m2-b1", 2, 1, spares=["blank"], kind="oldpool"))
    L.append(Layout("m2-b1-uneven", 2, 1, spares=["blank"], kind="uneven"))
    if level == "quick":
        L.append(Layout("m1-b1-bootsec", 1, 1, spares=["blank"], boot=("main", "backup")))
    else:
        L.append(Layout("m0-b0-nospare", 0, 0, spares=[], note="no spare drive plugged in"))
        L.append(Layout("m2-b1-nospare", 2, 1, spares=[], note="no spare drive plugged in"))
        for name, kw in [
            ("m1-b1-bootmain", {"main": 1, "backup": 1, "boot": ("main",)}),
            ("m1-b1-bootbackup", {"main": 1, "backup": 1, "boot": ("backup",)}),
            ("m2-b2-bootboth", {"main": 2, "backup": 2, "boot": ("main", "backup")}),
            ("m0-b1-bootbackup", {"main": 0, "backup": 1, "boot": ("backup",)}),
            ("m3-b2-mixedsizes", {"main": 3, "backup": 2, "sizes": [48, 96, 64, 160, 48]}),
            ("m3-b1-nearlyfull", {"main": 3, "backup": 1, "fill": "nearly"}),
            ("m2-b1-half", {"main": 2, "backup": 1, "fill": "half"}),
            ("m2-b2-empty", {"main": 2, "backup": 2, "fill": "empty"}),
            ("m3-b3-samemodel", {"main": 3, "backup": 3, "models": [0]}),
            ("m4-b2-ssdonly", {"main": 4, "backup": 2, "models": [1, 3, 6]}),
            ("m2-b2-unknownmodels", {"main": 2, "backup": 2, "models": [5]}),
        ]:
            L.append(Layout(name, spares=spare_mix[:2], **kw))
        if level == "full":
            L.append(Layout("m5-b5-mixed-everything", 5, 5, spares=spare_mix, sizes=[48, 64, 96], boot=("main", "backup"), fill="half"))
    if only:
        pats = [re.compile(p) for p in only]
        L = [x for x in L if any(p.search(x.name) for p in pats)]
    return L


# ---------------------------------------------------------------------------------------------------------------- the environment
class Env:
    def __init__(self, work, drives, scripts_dir, timeout=120):
        self.work = os.path.abspath(work)
        self.drives = os.path.abspath(drives)
        self.scripts = os.path.abspath(scripts_dir)
        self.timeout = timeout
        j = lambda *a: os.path.join(self.work, *a)
        self.state, self.disks, self.main, self.backup = j("state"), j("disks"), j("main"), j("backup")
        self.fstab, self.log, self.bin, self.tpl = j("fstab"), j("drives.log"), j("bin"), j("tpl")
        self.ctl, self.flags, self.runs = j("ctl"), j("flags"), j("runs")
        self.props = j("ctl", "props")
        self.answers, self.events, self.counter = j("ctl", "answers"), j("ctl", "events"), j("ctl", "counter")
        self.current = None           # the layout whose state is on disk now
        self.dirty = True
        self.base_fp = None
        self.base_mounts = set()
        self.base_files = None
        self.layout = None
        self.shim = os.path.join(HERE, "shim.sh")
        self.devs = []                # loop devices of the layout, in drive order

    # the environment of every `drives` run
    def environ(self, extra=None):
        e = dict(os.environ)
        e.update({
            "DRIVES_TEST": "1", "DRIVES_STATE_DIR": self.state, "DISKS_DIR": self.disks, "MAIN_POOL": self.main,
            "BACKUP_POOL": self.backup, "FSTAB": self.fstab, "LOGFILE": self.log,
            "HOMELAB_EXTRA_PATH": self.bin, "BENCH_ANSWERS": self.answers, "BENCH_EVENTS": self.events,
            "BENCH_COUNTER": self.counter, "BENCH_SLEEPERS": os.path.join(self.ctl, "sleepers"), "BENCH_FLAGS": self.flags, "BENCH_PROPS": self.props,
            "DRIVES_SMARTCTL": os.path.join(self.bin, "smartctl-health"),
            "DRIVES_MINFREE": "2M", "DRIVES_OWNER": "root", "LC_ALL": "C",
            "DRAIN_SPARE_BYTES": "1048576",      # the real tool keeps 2 GB free when it copies a drive off; the fake drives are tiny
            # `drives` offers to run the backup and looks for the newest backup: both must use the fake pools, never the real backup
            "HOMELAB_BACKUP_CMD": os.path.join(self.bin, "homelab-backup"), "BACKUP_CONF": os.path.join(self.work, "backup.conf"),
            "BACKUP_STATUS_FILE": os.path.join(self.work, "homelab-state", "last-run"),
        })
        e.pop("BENCH_FAULT_AT", None)
        e.pop("BENCH_FAULT_CMD", None)
        if extra:
            e.update(extra)
        return e


def sh(cmd, timeout=60, check=False, env=None, cwd="/"):
    p = subprocess.run(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       timeout=timeout, env=env, cwd=cwd, stdin=subprocess.DEVNULL)
    if check and p.returncode != 0:
        raise RuntimeError("command failed: %s\n%s" % (cmd, p.stdout))
    return p


FAKE_DOCKER = r'''#!/bin/bash
# fake docker for drive-bench: three containers that use the test pools; records what was asked
D="$BENCH_FLAGS"; echo "docker $*" >>"$D/docker.log"
case "$1" in
  info) exit 0 ;;
  ps) cut -d'|' -f1 "$D/containers" ;;
  inspect)
    shift; [ "$1" = "--format" ] && shift 2
    for id in "$@"; do srcs=$(grep "^$id|" "$D/containers" | cut -d'|' -f2); echo "/$id|$srcs "; done ;;
  stop)
    shift
    if [ -e "$D/stop-fails" ]; then echo "Error response from daemon: cannot stop container" >&2; exit 1; fi
    for n in "$@"; do echo "$n" >>"$D/stopped"; echo "$n"; done ;;
  start)
    shift
    if [ -e "$D/start-fails" ]; then echo "Error response from daemon: cannot start container" >&2; exit 1; fi
    for n in "$@"; do grep -vx "$n" "$D/stopped" >"$D/stopped.new" 2>/dev/null; mv -f "$D/stopped.new" "$D/stopped" 2>/dev/null; echo "$n"; done ;;
  exec) head -c 4096 /dev/urandom ;;
  *) exit 0 ;;
esac
'''

FAKE_LSBLK = r'''#!/bin/bash
# lsblk that tells drive-bench's made-up model, type and serial for the fake drives, and the truth for everything else
REAL=""; for c in /usr/bin/lsblk /bin/lsblk /usr/sbin/lsblk /sbin/lsblk; do [ -x "$c" ] && REAL=$c && break; done
dev="${*: -1}"
if [ -f "$BENCH_PROPS" ] && grep -q "^$dev|" "$BENCH_PROPS"; then
  line=$(grep -m1 "^$dev|" "$BENCH_PROPS"); IFS='|' read -r _ model rota tran serial <<<"$line"
  case "$*" in
    "-dno MODEL "*)       echo "$model"; exit 0 ;;
    "-dnbo ROTA,TRAN "*)  [ -n "$rota" ] && echo "$rota $tran"; exit 0 ;;
    "-dno TRAN "*)        echo "$tran"; exit 0 ;;
    "-dno SERIAL "*)      echo "$serial"; exit 0 ;;
  esac
fi
# `drives` lists every drive of the machine to offer as a new drive: in the bench only the fake drives may be offered, so that the
# real drives of this machine can never be chosen (and never be erased). The fake drives are listed by `drives` through losetup.
case "$*" in "-dnpo NAME,TYPE") exit 0 ;; esac
exec "$REAL" "$@"
'''

FAKE_SMARTCTL = r'''#!/bin/bash
# a made-up smartctl for drive-bench. BENCH_SMART changes what it says: fail, pending (bad sectors waiting), realloc, hot, asleep
dev="${*: -1}"
if [ "${BENCH_SMART:-}" = asleep ]; then
  case " $* " in *" -n standby "*) echo "Device is in STANDBY mode, exit(2)"; exit 2 ;; esac
fi
n=${dev//[^0-9]/}; n=${n:-0}
temp=$((30 + n % 10)); res=PASSED; pend=0; re=0
case "${BENCH_SMART:-}" in fail) res="FAILED!" ;; pending) pend=8 ;; realloc) re=3 ;; hot) temp=58 ;; esac
echo "smartctl 7.4 (drive-bench)"
echo "=== START OF READ SMART DATA SECTION ==="
echo "SMART overall-health self-assessment test result: $res"
echo "ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE"
printf '  5 Reallocated_Sector_Ct   0x0033   100   100   010    Pre-fail  Always       -       %s\n' "$re"
printf '  9 Power_On_Hours          0x0032   097   097   000    Old_age   Always       -       %s\n' "$((1000 + n))"
printf '194 Temperature_Celsius     0x0022   036   040   000    Old_age   Always       -       %s (Min/Max 20/45)\n' "$temp"
printf '197 Current_Pending_Sector  0x0032   100   100   000    Old_age   Always       -       %s\n' "$pend"
'''

FAKE_MOUNT = r'''#!/bin/bash
# mount that can be told to fail for the fstab (mount -T ...), and is the real mount otherwise
if [ -e "$BENCH_FLAGS/mount-fails" ]; then case " $* " in *" -T "*) echo "mount: bench: cannot mount (made to fail)" >&2; exit 32 ;; esac; fi
for c in /usr/bin/mount /bin/mount /usr/sbin/mount; do [ -x "$c" ] && exec "$c" "$@"; done
exit 127
'''

FAKE_HDPARM = r'''#!/bin/bash
# a made-up hdparm for drive-bench: remembers which drives are asleep. BENCH_HDPARM changes it:
#   asleep = every drive starts asleep; ignore = the sleep command does nothing (many USB adapters); silent = -C says nothing
echo "hdparm $*" >>"$BENCH_FLAGS/tools.log"
dev="${*: -1}"; key=$(basename "$dev"); F="$BENCH_FLAGS"; mode="${BENCH_HDPARM:-}"
case "$1" in
  -C)
    [ "$mode" = silent ] && exit 0
    if [ -e "$F/asleep-$key" ] || { [ "$mode" = asleep ] && [ ! -e "$F/awake-$key" ]; }; then s=standby; else s="active/idle"; fi
    printf '\n%s:\n drive state is:  %s\n' "$dev" "$s" ;;
  -y|-Y)
    [ "$mode" = ignore ] || { rm -f "$F/awake-$key"; : >"$F/asleep-$key"; } ;;
  --read-sector)
    rm -f "$F/asleep-$key"; : >"$F/awake-$key" ;;
esac
exit 0
'''

FAKE_SETFATTR = r'''#!/usr/bin/env python3
# setfattr for drive-bench (the real one is not installed everywhere): sets an extended attribute with python.
# BENCH_SETFATTR=fail makes it fail, as a pool that cannot change its settings while it runs would
import os, sys
if os.environ.get("BENCH_SETFATTR") == "fail":
    sys.exit(1)
a = sys.argv[1:]
name = value = None
while len(a) > 1:
    if a[0] == "-n":
        name = a[1]; a = a[2:]
    elif a[0] == "-v":
        value = a[1]; a = a[2:]
    else:
        break
try:
    os.setxattr(a[0], name, value.encode())
except (OSError, AttributeError, IndexError) as e:
    sys.stderr.write("setfattr: %s\n" % e)
    sys.exit(1)
'''

FAKE_UDISKS = r'''#!/bin/bash
# a made-up udisksctl: remembers which drives were powered off
echo "udisksctl $*" >>"$BENCH_FLAGS/tools.log"
if [ "$1" = power-off ]; then : >"$BENCH_FLAGS/poweroff-$(basename "${*: -1}")"; fi
exit 0
'''

FAKE_LOGGER = r'''#!/bin/bash
echo "$(basename "$0") $*" >>"$BENCH_FLAGS/tools.log"
case "$(basename "$0")" in
  smartctl) echo "SMART overall-health self-assessment test result: PASSED" ;;
esac
exit 0
'''


def real_backup_stamp():
    """When the real backup log and status were last written: the fake-drive tests must never change them."""
    out = []
    for f in ("/var/log/homelab-backup.log", "/var/lib/homelab-backup/last-run"):
        try:
            st = os.stat(f)
            out.append((f, st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((f, 0, 0))
    return out


def install_fake_backup(env):
    """The real homelab-backup script, pointed at the fake pools (own settings, own log, no lock, fake docker)."""
    state = os.path.join(env.work, "homelab-state")
    os.makedirs(state, exist_ok=True)
    with open(os.path.join(env.work, "backup.conf"), "w") as f:
        f.write('SRC="%s"\nDEST_POOL="%s"\nDEST_FALLBACK=""\nLOGFILE="%s/backup.log"\nSTATUS_FILE="%s/last-run"\n'
                'CONFIG_PATHS=()\nMIN_FREE_GB=0\nNEXTCLOUD_DB_CONTAINER="nextcloud"\n' % (env.main, env.backup, state, state))
    nolock = os.path.join(env.work, "nolock.sh")
    with open(nolock, "w") as f:
        f.write("flock() { return 0; }\n")     # a test run must not take the lock of the real backup
    path = os.path.join(env.bin, "homelab-backup")
    with open(path, "w") as f:
        f.write('#!/bin/bash\nexport BACKUP_CONF="%s" BASH_ENV="%s" HOMELAB_USER=root HOMELAB_ALLOW_ROOT=1\nexec bash "%s" "$@"\n'
                % (os.path.join(env.work, "backup.conf"), nolock, os.path.join(env.scripts, "homelab-backup")))
    os.chmod(path, 0o755)


def install_fakes(env):
    for d in (env.bin, env.ctl, env.flags):
        os.makedirs(d, exist_ok=True)
    for name, body in (("docker", FAKE_DOCKER), ("lsblk", FAKE_LSBLK), ("mount", FAKE_MOUNT), ("hdparm", FAKE_HDPARM),
                       ("smartctl", FAKE_LOGGER), ("udisksctl", FAKE_UDISKS)):
        path = os.path.join(env.bin, name)
        with open(path, "w") as f:
            f.write(body)
        os.chmod(path, 0o755)
    path = os.path.join(env.bin, "setfattr")
    with open(path, "w") as f:
        f.write(FAKE_SETFATTR)
    os.chmod(path, 0o755)
    path = os.path.join(env.bin, "smartctl-health")
    with open(path, "w") as f:
        f.write(FAKE_SMARTCTL)
    os.chmod(path, 0o755)
    install_fake_backup(env)
    with open(os.path.join(env.flags, "containers"), "w") as f:
        f.write("immich_server|%s %s\nnextcloud|%s\nfilebrowser|%s %s %s\n" % (
            env.main, env.disks, env.main, env.main, env.backup, env.disks))


# ---------------------------------------------------------------------------------------------------------------- mounts and loops
def mounts_under(work):
    out = []
    try:
        with open("/proc/self/mountinfo") as f:
            for line in f:
                p = line.split()
                tgt = p[4].replace("\\040", " ")
                if tgt == work or tgt.startswith(work + "/"):
                    out.append(tgt)
    except OSError:
        pass
    return out


def mount_types(work):
    """{mount point: file system type} for everything the bench mounted."""
    out = {}
    try:
        with open("/proc/self/mountinfo") as f:
            for line in f:
                p = line.split()
                tgt = p[4].replace("\\040", " ")
                if tgt == work or tgt.startswith(work + "/"):
                    dash = p.index("-")
                    out[tgt] = p[dash + 1]
    except (OSError, ValueError):
        pass
    return out


def kill_sleepers(env):
    """Stop the programs a 'busy' failure started to hold a drive or a pool."""
    pidf = os.path.join(env.ctl, "sleepers")
    if os.path.exists(pidf):
        for line in open(pidf):
            try:
                os.kill(int(line.strip()), signal.SIGKILL)
            except (ValueError, OSError):
                pass
        os.remove(pidf)


UDEV_RULE = "/run/udev/rules.d/99-drive-bench.rules"


def block_automount(env):
    """A desktop (udisks) mounts every new drive it sees under /media; then the loop devices can not be released and pile up.
    This rule tells udisks to leave the bench's fake drives alone (removed again at the end)."""
    try:
        os.makedirs(os.path.dirname(UDEV_RULE), exist_ok=True)
        with open(UDEV_RULE, "w") as f:
            f.write('SUBSYSTEM=="block", KERNEL=="loop[0-9]*p[0-9]*", ENV{UDISKS_IGNORE}="1", ENV{UDISKS_AUTO}="0"\n'
                    'SUBSYSTEM=="block", KERNEL=="loop[0-9]*", ATTR{loop/backing_file}=="%s/*", ENV{UDISKS_IGNORE}="1", ENV{UDISKS_AUTO}="0"\n' % env.work)
        sh("udevadm control --reload", timeout=20)
    except OSError:
        pass


def unblock_automount():
    try:
        os.remove(UDEV_RULE)
        sh("udevadm control --reload", timeout=20)
    except OSError:
        pass


def bench_loops(env):
    r = sh("losetup -ln -O NAME,BACK-FILE")
    out = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].strip().startswith(env.work + "/"):
            out.append(parts[0])
    return out


def unmount_loops(env):
    """Unmount whatever is mounted from the bench's loop drives, wherever it is (the desktop may have mounted them under /media)."""
    loops = bench_loops(env)
    if not loops:
        return
    r = sh("findmnt -rn -o SOURCE,TARGET")
    for line in r.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        src, tgt = parts[0], parts[1].replace("\\x20", " ")
        if any(src == d or re.match(re.escape(d) + r"p\d+$", src) for d in loops) and sh(["umount", tgt], timeout=30).returncode != 0:
            sh(["umount", "-l", tgt], timeout=30)


def teardown(env):
    """Stop everything the bench started: sleepers, mounts (pools first), loop devices."""
    kill_sleepers(env)
    for _ in range(3):
        mts = mounts_under(env.work)
        if not mts:
            break
        order = sorted(mts, key=lambda m: (0 if m in (env.main, env.backup) else 1, -m.count("/")))
        for m in order:
            r = sh(["umount", m], timeout=30)
            if r.returncode != 0:
                sh(["umount", "-l", m], timeout=30)
    unmount_loops(env)
    for dev in bench_loops(env):
        sh(["losetup", "-d", dev])


def teardown_pools(env):
    for m in (env.main, env.backup):
        if m in mounts_under(env.work):
            if sh(["umount", m]).returncode != 0:
                sh(["umount", "-l", m])


def wipe(env, keep_tpl=True):
    teardown(env)
    for d in (env.state, env.disks, env.main, env.backup):
        if os.path.exists(d):
            sh(["chattr", "-R", "-i", d])
            shutil.rmtree(d, ignore_errors=True)
    for f in (env.fstab, env.log):
        if os.path.exists(f):
            os.remove(f)


def attach_images(env):
    """Attach every disk*.img of the state folder to a loop device (with partition scanning); write the model table."""
    imgs = sorted((f for f in os.listdir(env.state) if re.match(r"disk\d+\.img$", f)),
                  key=lambda f: int(re.findall(r"\d+", f)[0]))
    env.devs = []
    SAFE_DEVS.clear()
    lines = []
    for i, f in enumerate(imgs):
        r = sh(["losetup", "-f", "-P", "--show", os.path.join(env.state, f)])
        dev = r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else ""
        if not dev.startswith("/dev/"):
            raise RuntimeError("losetup failed: %s" % r.stdout)
        env.devs.append(dev)
        SAFE_DEVS.add(dev)
        sh(["partprobe", dev])   # makes the partition files appear (a machine without udev does not do it by itself)
        drv = env.layout.all_drives()[i] if env.layout and i < len(env.layout.all_drives()) else None
        model = drv.model if drv else MODELS[0]
        lines.append("%s|%s|%s|%s|BENCH%04d" % (dev, model[0], "" if model[1] is None else model[1], model[2], i + 1))
    with open(env.props, "w") as f:
        f.write("\n".join(lines) + "\n")
    sh("udevadm settle", timeout=20)


def reset_ctl(env, answers=()):
    os.makedirs(env.ctl, exist_ok=True)
    with open(env.answers, "w") as f:
        for a in answers:
            f.write(a.replace("\n", " ") + "\n")
    for f in (env.events, env.counter):
        if os.path.exists(f):
            os.remove(f)
    open(env.events, "w").close()
    with open(env.counter, "w") as f:
        f.write("0\n")
    for name in os.listdir(env.flags):
        if name not in ("containers",):
            os.remove(os.path.join(env.flags, name))


def hung_report(pgid):
    """What the stuck run was doing when it timed out: its processes, and the kernel function each one waits in."""
    r = sh(["ps", "-o", "pid,stat,wchan:22,etime,args", "-g", str(pgid)], timeout=10)
    lines = [ln[:150] for ln in (r.stdout or "").splitlines()[:12]]
    if not lines:
        return ""
    return "[drive-bench] it was still running these when it was stopped:\n" + "\n".join("  " + ln for ln in lines) + "\n"


def run_shim(env, args, answers=(), timeout=None, fault=None, extra_env=None):
    """Run `drives ARGS` (or a function) with scripted answers. Returns (rc, output, events, seconds, timed_out)."""
    reset_ctl(env, answers)
    e = env.environ(extra_env)
    if fault:
        e["BENCH_FAULT_AT"] = str(fault[0])
        e["BENCH_FAULT_CMD"] = fault[1]
    t0 = time.time()
    timed_out = False
    p = subprocess.Popen(["bash", env.shim, env.drives] + list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, env=e, cwd="/", start_new_session=True, text=True, errors="replace")
    try:
        out, _ = p.communicate(timeout=timeout or env.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        stuck = hung_report(p.pid)
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        out, _ = p.communicate()
        out = (out or "") + "\n[drive-bench] timed out\n" + stuck
    secs = time.time() - t0
    return p.returncode, out or "", read_events(env), secs, timed_out


def read_events(env):
    ev = []
    try:
        with open(env.events, errors="replace") as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if p and p[0] == "BENCH-LOOP":
                    ev.append({"n": int(p[1] or 0), "kind": "loop", "answer": "", "prompt": "", "items": []})
                    continue
                if len(p) < 4:
                    continue
                ev.append({"n": int(p[0]), "kind": p[1], "answer": p[2], "prompt": p[3].replace("\\n", "\n"),
                           "items": [x for x in (p[4].split("\x1f") if len(p) > 4 else []) if x]})
    except OSError:
        pass
    return ev


# ---------------------------------------------------------------------------------------------------------------- building layouts
def listing(path):
    out = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != "lost+found"]
        for f in files:
            fp = os.path.join(root, f)
            try:
                out.append((os.path.relpath(fp, path), os.path.getsize(fp)))
            except OSError:
                pass
    return sorted(out)


def fingerprint(env):
    """A short summary of everything a run could change: fstab, mounts, files on the drives, names, state files."""
    h = hashlib.sha1()
    try:
        h.update(open(env.fstab, "rb").read())
    except OSError:
        h.update(b"nofstab")
    for m in sorted(mounts_under(env.work)):
        h.update(m.encode())
    for d in sorted(os.listdir(env.disks)) if os.path.isdir(env.disks) else []:
        h.update(d.encode())
        h.update(repr(listing(os.path.join(env.disks, d))).encode())
    for f in sorted(os.listdir(env.state)) if os.path.isdir(env.state) else []:
        fp = os.path.join(env.state, f)
        if f.startswith("fstab.bak") or f == "drives.log":
            continue
        if os.path.isfile(fp):
            h.update(f.encode())
            if not f.endswith(".img"):
                h.update(open(fp, "rb").read())
        else:       # a folder counts only through the files inside (an empty folder being made is not a change)
            for rel, size in listing(fp):
                h.update(("%s/%s %d" % (f, rel, size)).encode())
    r = sh("losetup -ln -O NAME,BACK-FILE")
    # the files that are attached, not the number of the loop device they got (mounting a drive again may give it another number)
    h.update("".join(sorted(l.split(None, 1)[1] for l in r.stdout.splitlines() if env.work in l and len(l.split(None, 1)) == 2)).encode())
    # a spare drive can be erased: its partition table sits in the first MiB (a mount only changes the file system behind it)
    lay = env.layout
    if lay is not None:
        first = len(lay.main) + len(lay.backup)
        for j in range(len(lay.spares)):
            if lay.kind == "legacy" and j == 0:
                continue      # that one is mounted as the main storage
            try:
                with open(os.path.join(env.state, "disk%d.img" % (first + j + 1)), "rb") as f:
                    h.update(hashlib.sha1(f.read(1024 * 1024)).digest())
            except OSError:
                h.update(b"noimage%d" % j)
    try:
        h.update(" ".join(sorted(n for n in os.listdir(env.flags) if n.startswith(("asleep-", "awake-", "poweroff-")))).encode())
    except OSError:
        pass
    return h.hexdigest()


def write_files(mp, fill, size_mb, idx):
    """Put files on one drive: empty | few | half | nearly | full."""
    if fill == "empty":
        return
    os.makedirs(os.path.join(mp, "photos"), exist_ok=True)
    os.makedirs(os.path.join(mp, "docs"), exist_ok=True)
    for i in range(3):
        with open(os.path.join(mp, "photos", "img%d_%d.jpg" % (idx, i)), "wb") as f:
            f.write(os.urandom(200 * 1024))
    with open(os.path.join(mp, "docs", "note%d.txt" % idx), "w") as f:
        f.write("bench file %d\n" % idx)
    frac = {"half": 0.5, "nearly": 0.93, "full": 0.99}.get(fill)
    if frac:
        sh(["sync"])
        st = os.statvfs(mp)
        total = st.f_blocks * st.f_frsize
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        want = int(total * frac) - used
        if want > 0:
            sh(["fallocate", "-l", str(want), os.path.join(mp, "photos", "big%d.bin" % idx)])


def make_spare(env, dev, drive):
    """A drive that is plugged in but not in a pool: blank, an ext4 partition with files, or a vfat partition."""
    if drive.fs == "blank":
        return
    sh(["parted", "-s", dev, "mklabel", "gpt", "mkpart", "old", "1MiB", "100%"])
    sh(["partprobe", dev])
    sh("udevadm settle", timeout=20)
    part = dev + "p1"
    for _ in range(20):
        if os.path.exists(part):
            break
        time.sleep(0.2)
    if drive.fs == "ext4data":
        sh(["mkfs.ext4", "-F", "-q", "-L", "OLDDATA", part])
        mp = os.path.join(env.work, "spare-mnt")
        os.makedirs(mp, exist_ok=True)
        sh(["mount", part, mp])
        write_files(mp, "few", drive.size_mb, 99)
        sh(["umount", mp])
    elif drive.fs == "vfat":
        r = sh(["mkfs.vfat", "-n", "USBSTICK", part])
        if r.returncode != 0:
            sh(["mkfs.ext2", "-F", "-q", part])


def build_layout(env, layout, log=print):
    """Make the layout with the real flows and save it. Returns True when the layout could be built."""
    env.layout = layout
    wipe(env)
    for d in (env.state, env.disks, env.main, env.backup):
        os.makedirs(d, exist_ok=True)
    open(env.fstab, "w").close()
    install_fakes(env)
    drives = layout.all_drives()
    for i, d in enumerate(drives, 1):
        with open(os.path.join(env.state, "disk%d.img" % i), "wb") as f:
            f.truncate(d.size_mb * 1024 * 1024)
    attach_images(env)
    problems = []
    n_main = len(layout.main)
    plan = None
    skip_spare = -1
    if layout.kind == "legacy":
        # the old setup: one ext4 drive (the first "spare") that is mounted straight at the main pool path: no pool, no label
        plan, skip_spare = [], 0
        make_spare(env, env.devs[0], Drive(48, 0, "ext4data"))
        part = env.devs[0] + "p1"
        sh(["e2label", part, "STORAGE"])
        uuid = sh(["blkid", "-s", "UUID", "-o", "value", part]).stdout.strip()
        with open(env.fstab, "a") as f:
            f.write("UUID=%s  %s  ext4  defaults,nofail  0  2\n" % (uuid, env.main))
        sh(["mount", "-T", env.fstab, env.main])
        write_files(env.main, "few", 48, 1)
    if plan is None:
        plan = [(layout.main[i], env.devs[i], "main") for i in range(n_main)] + \
               [(layout.backup[i], env.devs[n_main + i], "backup") for i in range(len(layout.backup))]
    for _drv, dev, role in plan:
        rc, out, ev, secs, to = run_shim(env, ["__call", "connect_flow", dev, role, "1"], [dev, "ERASE"], timeout=180)
        if rc != 0 or "Done." not in out:
            problems.append("could not connect %s as %s drive: %s" % (dev, role, out.strip().splitlines()[-1:] or rc))
    # data
    idx = 0
    for role in ("main", "backup"):
        res = sh("grep -o '%s/%s%s[0-9]*' %s | sort -uV" % (env.disks, "TMAIN" if role == "main" else "TBACKUP", "", env.fstab))
        drv_list = layout.main if role == "main" else layout.backup
        for mp, drv in zip(res.stdout.split(), drv_list):
            idx += 1
            write_files(mp, drv.fill, drv.size_mb, idx)
    if layout.kind == "uneven":
        # the first main drive gets 8 files of 3 MB in folders (about 2/3 of it); the second one keeps its few files
        first_main = os.path.join(env.disks, "TMAIN1")
        for i in range(8):
            d = os.path.join(first_main, "bulk", "set%d" % (i % 3))
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "big file %d.bin" % i), "wb") as f:
                f.write(os.urandom(3 * 1024 * 1024))
    # spares
    for j, drv in enumerate(layout.spares):
        if j != skip_spare:
            make_spare(env, env.devs[len(plan) + j], drv)
    # boot sections
    for role in layout.boot:
        rc, out, ev, secs, to = run_shim(env, ["__call", "bootsection_flow"], ["1" if role == "main" else "2", "CONTINUE", "20", "y"],
                                         timeout=120)
        if "Done." not in out:
            problems.append("could not make the %s boot section: %s" % (role, out.strip().splitlines()[-1:]))
    if layout.backup or "backup" in layout.boot:
        # a backup copy of the main pool, so restore and "replace a dead drive" have something to copy back from
        sh([os.path.join(env.bin, "homelab-backup")], timeout=300, env=env.environ())
    if layout.kind == "oldpool" and not problems:
        # an older pool: no per-drive free-space limit and "most free space" instead of "fill the first drive first"
        teardown_pools(env)
        txt = open(env.fstab).read()
        txt = re.sub(r"=RW,\d+K", "", txt).replace("category.create=ff", "category.create=mfs")
        open(env.fstab, "w").write(txt)
        run_shim(env, ["__call", "__remount"], timeout=120)
    if problems:
        return problems
    # save: everything in the state folder plus the fstab
    teardown(env)
    shutil.rmtree(env.tpl, ignore_errors=True)
    os.makedirs(env.tpl)
    sh(["cp", "-a", "--sparse=always", env.state, os.path.join(env.tpl, "state")], check=True)
    sh(["cp", "-a", env.fstab, os.path.join(env.tpl, "fstab")], check=True)
    env.current, env.dirty = layout.key, True
    return []


def restore_layout(env):
    """Put the saved layout back on disk and mount it, exactly as it was after building."""
    wipe(env)
    for d in (env.disks, env.main, env.backup):
        os.makedirs(d, exist_ok=True)
    sh(["cp", "-a", "--sparse=always", os.path.join(env.tpl, "state"), env.state], check=True)
    sh(["cp", "-a", os.path.join(env.tpl, "fstab"), env.fstab], check=True)
    install_fakes(env)
    attach_images(env)
    run_shim(env, ["__call", "__remount"], timeout=120)
    env.base_fp = fingerprint(env)
    env.base_mounts = set(mounts_under(env.work))
    env.base_files = {r: set(listing(p)) for r, p in (("main", env.main), ("backup", env.backup))}
    env.dirty = False


# ---------------------------------------------------------------------------------------------------------------- results
SH = r"(?m)^[^\n]*?: (?:eval: )?line \d+: [^\n]*"      # a shell error line: "drives: line 120: ..."
BASH_ERRORS = [
    (re.compile(SH + "unbound variable"), "unbound variable"),
    (re.compile(SH + "syntax error"), "syntax error"),
    (re.compile(SH + "command not found"), "command not found"),
    (re.compile(SH + "bad substitution"), "bad substitution"),
    (re.compile(SH + "integer expression expected"), "integer expression expected"),
    (re.compile(SH + "unary operator expected"), "unary operator expected"),
    (re.compile(SH + "(No such file or directory|Permission denied|ambiguous redirect)"), "shell error on a line"),
    (re.compile(r"Traceback \(most recent call last\)"), "python traceback"),
    (re.compile(SH + "(arithmetic syntax error|division by 0|value too great for base)"), "arithmetic error"),
]


def has_message(out, events):
    """True when the last thing printed is an explanation, not just the last question that was asked."""
    lines = [l for l in out.splitlines() if l.strip()]
    if not lines:
        return False
    prompts = [e["prompt"].strip() for e in events if e.get("prompt", "").strip()]
    return not any(lines[-1].startswith(p) for p in prompts)


def classify(rc, out, timed_out, events, changed, flow=""):
    flags = []
    for rx, name in BASH_ERRORS:
        if rx.search(out):
            flags.append("bash-error: " + name)
    if timed_out:
        flags.append("timeout")
    if any(e["kind"] == "loop" for e in events):
        flags.append("endless-prompt")
    msg = ""
    m = re.search(r"^(ERROR: .*)$", out, re.M)
    if m:
        msg = m.group(1)
    if flags:
        outcome = "CRASH"
    elif rc == 0:
        ended_at_question = bool(events) and events[-1].get("answer") == "<EOF>"
        if changed:
            outcome = "DONE"
        elif re.search(r"Cancelled", out) or ended_at_question:
            outcome = "CANCELLED"
        elif flow not in ("status", "menu", "cli", "wish", "power", "list", "usage", "health", "check", "scan") and "DRY RUN" not in out and re.search(
                r"is the only|[Cc]annot |[Cc]ould not|No new drive|No drives|nothing to |is not mounted|Not removing|enough free space|not enough|too small|too big", out):
            outcome = "REFUSED"
            flags.append("exit 0 although the command refused")
        else:
            outcome = "NOTHING"
    elif rc == 1 and (re.search(r"Cancelled", out) or (events and events[-1].get("answer") == "<EOF>" and not msg)):
        outcome = "CANCELLED"
    elif rc == 1 and flow in ("health", "check") and re.search(r"PROBLEM|FAILED|failing|\"ok\":false", out):
        outcome = "NOTHING"     # it found a problem and said so: that is what these two commands are for
    elif rc == 1 and (msg or has_message(out, events)):
        outcome = "REFUSED"
    elif rc == 1:
        outcome = "SILENT-FAIL"
        flags.append("exit 1 without any explanation")
    else:
        outcome = "CRASH"
        flags.append("exit code %s" % rc)
    return outcome, flags, msg


def check_invariants(env, flow, out, before_files, changed=False, unplugged=False, rc=0, mountfail=False, fault_run=False):
    """Look at the machine after a run. Returns a list of problems (strings)."""
    bad = []
    try:
        fl = open(env.fstab).read().splitlines()
    except OSError:
        return ["fstab is gone"]
    act = [l.split() for l in fl if l.strip() and not l.lstrip().startswith("#")]
    mps = [a[1] for a in act if len(a) > 1]
    dup = [m for m, c in collections.Counter(mps).items() if c > 1]
    if dup:
        bad.append("INV-fstab-duplicate: mount point listed twice: " + ", ".join(os.path.basename(d) for d in dup))
    # drives of a pool in the fstab but its pool line missing / pool mounted without drives
    for role, pool, pref in (("main", env.main, "TMAIN"), ("backup", env.backup, "TBACKUP")):
        branches = [m for m in mps if re.search(r"/%s(\d+|BOOT)$" % pref, m)]
        has_line = any(len(a) > 2 and a[1] == pool and a[2] == "fuse.mergerfs" for a in act)
        mounted = mount_types(env.work).get(pool, "").endswith("mergerfs")
        if branches and not has_line:
            bad.append("INV-pool-line: %s has drives in the fstab but no pool line" % role)
        if not branches and has_line:
            bad.append("INV-pool-line: %s has a pool line but no drives" % role)
        if branches and has_line and not mounted and all(os.path.ismount(b) for b in branches):
            bad.append("INV-pool-mount: %s drives are mounted but the pool is not" % role)
        if not branches and mounted:
            bad.append("INV-pool-mount: %s pool is mounted although it has no drives" % role)
    for a in act:
        if len(a) > 1 and a[0].startswith("UUID=") and not os.path.ismount(a[1]) and os.path.isdir(a[1]):
            pass
    if flow in ("rename", "sleep", "wake", "eject", "wipe") and not unplugged:
        # these act on one drive: the fstab and the mounts of the pools must be exactly as they were
        try:
            if open(env.fstab).read() != open(os.path.join(env.tpl, "fstab")).read():
                bad.append("INV-fstab-touched: '%s' only acts on one drive, but /etc/fstab (the test copy) is different now" % flow)
        except OSError:
            pass
        if set(mounts_under(env.work)) != env.base_mounts:
            bad.append("INV-mounts-touched: '%s' only acts on one drive, but the set of mounts is different now" % flow)
    if flow == "balance" and not unplugged:
        for pool_prefix in ("TMAIN", "TBACKUP"):
            seen = collections.Counter()
            for d in sorted(os.listdir(env.disks)) if os.path.isdir(env.disks) else []:
                if re.fullmatch(pool_prefix + r"\d+", d):
                    for rel, _size in listing(os.path.join(env.disks, d)):
                        seen[rel] += 1
            twice = [rel for rel, n in seen.items() if n > 1]
            if twice:
                bad.append("INV-balance-twice: %d file(s) are on more than one %s drive after balance (e.g. %s)" % (len(twice), pool_prefix, twice[0]))
    if changed and flow in LOOK_FLOWS and not fault_run:       # a fault that was put in on purpose (a drive pulled) is itself a change
        bad.append("INV-lookonly-changed: '%s' only looks, but the drives, mounts, files or settings are different now" % flow)
    if changed and not fault_run and re.search(r"Nothing was changed", out):
        bad.append("INV-false-claim: it says 'Nothing was changed' but the drives, mounts or files are different now")
    # containers
    stopped = os.path.join(env.flags, "stopped")
    if os.path.exists(stopped) and open(stopped).read().strip():
        if "stay stopped on purpose" in out or "stay stopped until the" in out:
            pass     # kept down on purpose (a drive is missing, or a restore is not finished): the message says what to do
        elif mountfail and "still STOPPED" in out:
            pass     # every mount fails in this run: the pools cannot come back, so the containers must not start
        elif "still STOPPED" in out:
            bad.append("INV-left-stopped: the command stopped the services and failed, so they stay down until 'sudo hdd-recover' is run")
        elif rc == 0 or "did not start" not in out:
            bad.append("INV-containers: containers were left stopped but the command ended as if all was well%s"
                       % (" (it printed a warning)" if "did not start" in out else " (nothing was said)"))
    # files
    if not unplugged and flow in ("connect", "adopt", "power", "fillorder", "recover", "status", "bootsection", "restore", "replace", "move",
                                  "rename", "sleep", "wake", "eject", "wipe", "balance", "limit", "resize", "fillorder"):
        for role, pool in (("main", env.main), ("backup", env.backup)):
            if mount_types(env.work).get(pool, "").endswith("mergerfs") and role in before_files:
                now = set(listing(pool))
                lost = before_files[role] - now
                if lost:
                    bad.append("INV-files: %d file(s) in the %s pool are gone after '%s' (e.g. %s)" % (len(lost), role, flow, sorted(lost)[0][0]))
    return bad


LOOK_FLOWS = ("status", "list", "usage", "health", "check", "scan")


class Recorder:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "a")
        self.done = set()
        if os.path.exists(path):
            for line in open(path):
                try:
                    self.done.add(json.loads(line)["id"])
                except Exception:
                    pass
        self.count = 0

    def transcript(self, rec, full):
        """The whole screen of every run, nothing cut out, one file per layout (transcripts/LAYOUT.txt). results.jsonl keeps the short form."""
        folder = os.path.join(os.path.dirname(self.path), "transcripts")
        try:
            os.makedirs(folder, exist_ok=True)
            name = re.sub(r"[^A-Za-z0-9._-]+", "-", rec["layout"]) + ".txt"
            cmd = "sudo " + " ".join([rec["flow"].split(":", 1)[-1] if rec["flow"].startswith(("other:", "real:")) else "drives"] + list(rec["args"]))
            if rec["flow"].startswith(("other:", "real:")):
                cmd = rec["flow"].split(":", 1)[1]
            head = ["#" * 100, "layout: %s    command: %s" % (rec["layout"], cmd.strip())]
            if rec.get("answers"):
                head.append("answers typed, in order: %s" % " | ".join(repr(x) for x in rec["answers"]))
            if rec.get("pre"):
                head.append("before the command: %s" % ", ".join(rec["pre"]))
            if rec.get("fault"):
                head.append("during the command: %s" % ":".join(str(x) for x in rec["fault"]))
            if rec.get("note"):
                head.append("what it tries: %s" % rec["note"])
            head.append("exit code: %s    result: %s%s" % (rec["rc"], rec["outcome"], ("    flags: " + "; ".join(rec["flags"])) if rec["flags"] else ""))
            head.append("-" * 100)
            with open(os.path.join(folder, name), "a") as f:
                f.write("\n".join(head) + "\n" + full.rstrip("\n") + "\n\n")
        except OSError:
            pass

    def add(self, rec):
        full = rec.pop("full", None)
        if full is not None:
            self.transcript(rec, full)
        self.f.write(json.dumps(rec) + "\n")
        self.f.flush()
        self.done.add(rec["id"])
        self.count += 1


def trim(text, head=3500, tail=1500):
    if len(text) <= head + tail + 40:
        return text
    return text[:head] + "\n...[%d characters left out]...\n" % (len(text) - head - tail) + text[-tail:]


def case_id(layout, args, answers, fault, pre=(), tag=""):
    return "|".join([layout, " ".join(args), "\x1e".join(answers), "%s:%s" % fault if fault else "", ",".join(pre), tag])


def lose_files(env, n=3):
    """Some files vanish from the main pool (what `drives restore` is for)."""
    gone = 0
    for root, _dirs, files in os.walk(env.main):
        for f in sorted(files):
            if gone < n and not f.startswith("."):
                try:
                    os.remove(os.path.join(root, f))
                    gone += 1
                except OSError:
                    pass


def run_case(env, rec, layout, flow, args, answers, fault=None, note="", extra_env=None, timeout=None, probe=True, pre=(), tag="", expect=None, before_run=None):
    """One scripted run of `drives` on the saved layout. `pre` = things that went wrong BEFORE the command starts
    (for example a drive that was unplugged). Returns the record, or None when it was already done."""
    cid = case_id(layout.key, args, answers, fault, pre, tag)
    if cid in rec.done:
        return None
    if env.current != layout.key or env.dirty:
        restore_layout(env)
        env.current = layout.key
    if pre:
        for spec in pre:
            if spec == "lose-files":
                lose_files(env)
            else:
                run_shim(env, ["__call", "__bench_fault"] + spec.split(), timeout=60)
        env.base_fp = fingerprint(env)
        env.base_mounts = set(mounts_under(env.work))
        env.base_files = {r: set(listing(p)) for r, p in (("main", env.main), ("backup", env.backup))}
        env.dirty = True
    before_files = env.base_files
    if before_run:
        before_run()
    rc, out, events, secs, to = run_shim(env, args, answers, fault=fault, extra_env=extra_env, timeout=timeout)
    kill_sleepers(env)
    docker = ""
    try:
        docker = open(os.path.join(env.flags, "docker.log")).read()
    except OSError:
        pass
    fp = fingerprint(env)
    changed = fp != env.base_fp
    outcome, flags, msg = classify(rc, out, to, events, changed, flow)
    invariants = check_invariants(env, flow, out, before_files, changed,
                                    any("unplug" in x for x in list(pre) + [fault[1] if fault else ""]), rc,
                                    bool(fault) and "mount-fails" in fault[1], fault_run=bool(fault)) if not to else []
    probe_rec = None
    if probe and changed:
        pdoc = run_shim(env, ["status"], timeout=60)
        pflags = [f for f in classify(pdoc[0], pdoc[1], pdoc[4], pdoc[2], False)[1] if not f.startswith("exit 0 although")]
        if pflags or pdoc[0] != 0:
            probe_rec = {"rc": pdoc[0], "flags": pflags, "text": trim(pdoc[1], 1500, 500)}
            invariants.append("INV-status-after: 'drives status' fails after this run (%s)" % (", ".join(pflags) or "exit %s" % pdoc[0]))
    if changed:
        env.dirty = True
    asked = [e for e in events if e["kind"] != "loop"]
    r = {
        "id": cid, "layout": layout.key, "flow": flow, "args": args, "answers": answers, "fault": fault, "pre": list(pre), "note": note,
        "rc": rc, "secs": round(secs, 2), "outcome": outcome, "flags": flags + invariants, "msg": msg, "changed": changed,
        "prompts": [{"n": e["n"], "kind": e["kind"], "prompt": e["prompt"], "items": e["items"], "answer": e["answer"]} for e in asked],
        "output": trim(out), "docker": docker.strip().splitlines()[:12], "probe": probe_rec, "full": out,
    }
    if "--json" in args and not to and (rc == 0 or flow in ("health", "check")):
        try:
            json.loads(out)
        except ValueError as e:
            r["flags"].append("INV-json-invalid: the output is not valid JSON (%s)" % str(e)[:60])
    if flow in ("list", "usage", "health", "check", "status") and not pre and not extra_env and not to and rc != 0 and "--dry-run" not in args:
        r["flags"].append("INV-look-failed: '%s' exited with %s on a healthy layout" % (flow, rc))
    if expect and not to:
        r["flags"] += expect(r)
    rec.add(r)
    return r


# ---------------------------------------------------------------------------------------------------------------- the answer tree
def last_menu_options(out_before):
    opts = re.findall(r"^\s*(\d+)\) ", out_before, re.M)
    return [o for o in opts if o != "0"]


def candidates(ev, transcript_before, level, layout):
    """Answers worth trying for one question, most normal first. Returns [(answer, is_deviation)]."""
    kind, prompt, items = ev["kind"], ev["prompt"], ev["items"]
    rich = {"quick": 0, "standard": 1, "full": 2}[level]
    c = []
    if kind == "choose":
        for i in range(1, len(items) + 1):
            c.append((str(i), i > 1))
        c.append(("0", True))
        if rich >= 1:
            c.append(("", True))
            c.append(("99", True))
        if rich >= 2:
            c += [("abc", True), ("-1", True), (" 1", True), ("1 ", True)]
    elif kind == "yn":
        c = [("y", False), ("n", True)]
        if rich >= 1:
            c.append(("", True))
        if rich >= 2:
            c += [("maybe", True), ("YES", True), ("yes", True)]
    elif kind == "typed":
        m = re.search(r"Type (?:the drive name exactly )?\(?([^\s():]+)\)?", prompt)
        exp = None
        mm = re.search(r"\((/dev/[^)]+)\)", prompt)
        if mm:
            exp = mm.group(1)
        elif "ERASE" in prompt:
            exp = "ERASE"
        elif "CONTINUE" in prompt:
            exp = "CONTINUE"
        elif m:
            exp = m.group(1)
        if exp and exp.startswith("/dev/") and exp not in SAFE_DEVS:
            c = [("", True)]       # never type the name of a drive that is not one of the fake drives
        elif exp:
            c.append((exp, False))
            c.append(("", True))
            if rich >= 1:
                c.append((exp.lower() if exp != exp.lower() else exp.upper(), True))
            if rich >= 2:
                c += [(exp + " ", True), ("x", True)]
        else:
            c = [("", True), ("x", True)]
    else:   # free text: a menu number, a size, or a name
        if "Type a number and press Enter" in prompt:
            opts = last_menu_options(transcript_before) or ["1", "2", "3"]
            for o in opts:
                c.append((o, int(o) > 1))
            c.append(("0", True))
            if rich >= 1:
                c += [("", True), ("9", True)]
            if rich >= 2:
                c += [("x", True), ("-1", True)]
        elif "New size in" not in prompt and re.search(r"\[(\d+) to (\d+) ", prompt):
            lo, hi = map(int, re.search(r"\[(\d+) to (\d+) ", prompt).groups())
            mid = str(min(hi, max(lo, (lo + hi) // 2 if hi - lo < 40 else lo + 4)))
            c.append((mid, False))
            c.append(("", True))
            if rich >= 1:
                c += [(str(lo - 1), True), (str(hi + 1), True), ("abc", True)]
            if rich >= 2:
                c += [(str(lo), True), (str(hi), True), ("0", True), ("-5", True), ("%sMB" % mid, True), ("1.5", True), ("99999999999999999999", True)]
        elif "New free-space limit" in prompt:     # limit: a good value first, then what could be typed wrongly
            c = [("8%", False), ("", True), ("auto", True), ("0%", True), ("99%", True), ("50GB", True), ("abc", True), ("1MB", True)]
            if rich >= 1:
                c += [("10 %", True), ("1.5mb", True), ("8", True)]
        elif "New size in" in prompt:     # resize: bigger, the smallest, the same, then wrong
            lo, hi = map(int, re.search(r"\[(\d+) to (\d+) ", prompt).groups())
            c = [(str(lo + 8), False), (str(lo), True), (str(lo + 4), True), ("", True), (str(lo - 1), True), (str(hi + 1), True), ("abc", True)]
        elif "New name" in prompt:     # rename: a good name first, then what could be typed wrongly
            c = [("Photos drive", False), ("", True), ("auto", True), ("!!!", True), ("A" * 41, True), ("50 MB Toshiba HDD", True)]
            if rich >= 1:
                c += [("a/b", True), ("  Two   spaces  ", True), ("MAIN1=x", True)]
        else:
            c = [("", True), ("x", True)]
            if rich >= 1:
                c += [("My Drive", True), ("a/b", True)]
    return c


def explore(env, rec, layout, flow, args, level, budget, max_dev, max_depth=8, pre=(), note="", prefix=()):
    """Run a command with answer sequences, most normal first. `prefix` = answers that are always given first.
    Returns the list of records run."""
    heap = [(0, 0, list(prefix))]      # (deviations, order, answers)
    seq = itertools.count(1)
    seen = set()
    out = []
    runs = 0
    happy = None
    while heap and runs < budget:
        heap.sort(key=lambda x: (x[0], len(x[2]), x[1]))
        dev, _, ans = heap.pop(0)
        key = tuple(ans)
        if key in seen:
            continue
        seen.add(key)
        r = run_case(env, rec, layout, flow, args, ans, pre=pre, note=note)
        if r is None:      # done in an earlier session (resume): still walk its children from the saved record
            continue
        runs += 1
        out.append(r)
        k = len(ans) + 1
        nxt = next((p for p in r["prompts"] if p["n"] == k and p["answer"] == "<EOF>"), None)
        if nxt is None:
            if happy is None or len(ans) > len(happy):
                if r["outcome"] in ("DONE", "NOTHING"):
                    happy = ans
            continue
        if len(ans) >= max_depth:
            continue
        before = r["output"]
        # the part of the screen before this prompt (for menu numbers)
        idx = before.find(nxt["prompt"])
        text_before = before[:idx] if idx >= 0 else before
        text_before = text_before.rsplit("\n\n", 1)[-1] if text_before.count("\n\n") > 3 else text_before
        for a, is_dev in candidates(nxt, text_before, level, layout):
            nd = dev + (1 if is_dev else 0)
            if nd <= max_dev:
                heap.append((nd, next(seq), ans + [a]))
    return out, happy


# ---------------------------------------------------------------------------------------------------------------- what to run
FLOWS = [
    # name,        args,           what it is
    ("menu", [], "the menu (no argument)"),
    ("status", ["status"], "status"),
    ("list", ["list"], "list the drives"),
    ("usage", ["usage"], "space used and free"),
    ("health", ["health"], "SMART health"),
    ("check", ["check"], "quick check for file system errors"),
    ("scan", ["check", "--full"], "full read-only scan of one drive"),
    ("connect", ["connect"], "connect a new drive"),
    ("disconnect", ["disconnect"], "disconnect a drive"),
    ("move", ["move"], "move a drive between main and backup"),
    ("adopt", ["adopt"], "convert the single data drive"),
    ("power", ["power"], "apply the power settings"),
    ("recover", ["recover"], "recover after an unplug"),
    ("replace", ["replace"], "replace a dead drive"),
    ("fillorder", ["fillorder"], "fill drives one at a time"),
    ("release", ["release"], "take all drives out of the pools"),
    ("bootsection", ["bootsection"], "use part of the boot drive"),
    ("restore", ["restore"], "copy back the missing files from the backup"),
    ("balance", ["balance"], "even out the used space between drives"),
    ("limit", ["limit"], "how much free space a drive keeps"),
    ("resize", ["resize"], "make a boot drive section bigger or smaller"),
    ("rename", ["rename"], "give a pool drive a name of your own"),
    ("sleep", ["sleep"], "put a spinning drive to sleep"),
    ("wake", ["wake"], "wake a spinning drive up"),
    ("eject", ["eject"], "get a spare drive ready to unplug"),
    ("wipe", ["wipe"], "erase a spare drive"),
]

# commands typed on the command line that are not one of the flows above
CLI_VARIANTS = [
    ("version", ["version"]), ("unknown word", ["bogus"]), ("help word", ["help"]), ("--help", ["--help"]), ("-h", ["-h"]),
    ("status with an extra word", ["status", "extra"]), ("connect with a device and a pool", ["connect", "/dev/loop0", "main"]),
    ("--yes", ["--yes"]), ("--dry-run", ["--dry-run"]), ("status --json", ["status", "--json"]),
    ("test-setup without test mode flag", ["test-cleanup"]),
]

# words a person might expect to work; each is tried as `drives WORD` and reported as supported or not
WISHES = [
    ("rename", "give a drive a name of your own"), ("name", "give a drive a name of your own"),
    ("smart", "show a drive's SMART health"), ("health", "show a drive's health"),
    ("sleep", "put a drive to sleep now"), ("wake", "wake a drive now"), ("spindown", "spin a drive down now"), ("standby", "standby now"),
    ("wipe", "erase a drive outside the pools"), ("format", "format a drive"), ("erase", "erase a drive"),
    ("eject", "power a drive off so it can be unplugged"), ("unmount", "unmount one drive"), ("mount", "mount one drive"),
    ("list", "list all drives"), ("fsck", "check a drive's file system"), ("scrub", "check the files on a drive"),
    ("balance", "spread files evenly over the drives"), ("rebalance", "spread files evenly over the drives"),
    ("reorder", "change the order the drives fill in"), ("priority", "change the order the drives fill in"),
    ("limit", "change how much free space a drive keeps"), ("resize", "change the size of the boot drive section"),
    ("snapshot", "save the drive setup"), ("benchmark", "test a drive's speed"), ("identify", "blink / identify a drive"),
    ("check", "check the pools"), ("fix", "repair the pools"), ("verify", "verify the pools"),
    ("add", "add a drive (other word for connect)"), ("remove", "remove a drive (other word for disconnect)"),
    ("usage", "show how much space is used"), ("df", "show how much space is used"),
]


def level_settings(level):
    """budget = runs per command and layout; deep = the layouts that also get the unplug / full / busy scenarios and the failure runs."""
    if level == "quick":
        return {"budget": 14, "max_dev": 1, "depth": 6, "faults": False, "variants": False, "wishes": False, "deep": None, "pre": 0,
                "safety": SAFETY_LAYOUTS}
    if level == "standard":
        return {"budget": 20, "max_dev": 2, "depth": 8, "faults": True, "variants": True, "wishes": True, "pre": 3,
                    "deep": [r"^m[123]-b[12]$", r"boot", r"^legacy", r"^oldpool", r"nearlyfull", r"mixedsizes", r"^m0-b1$", r"^m1-b0$"]}
    return {"budget": 40, "max_dev": 3, "depth": 10, "faults": True, "variants": True, "wishes": True, "pre": len(PRE_SCENARIOS), "deep": [r"."]}


FAULTS = [
    ("unplug first main drive", "unplug TMAIN1"), ("unplug last backup drive", "unplug TBACKUP_LAST"),
    ("drive full", "fill TMAIN1"), ("drive becomes read-only", "readonly TMAIN1"),
    ("something holds a drive busy", "busy TMAIN1"), ("something holds the main pool busy", "poolbusy main"),
    ("containers will not stop", "docker-stop-fails x"), ("containers will not start", "docker-start-fails x"),
    ("mounting fails", "mount-fails x"),
]
PRE_SCENARIOS = [     # the first ones are used at the standard level
    ("a main drive is unplugged", ["unplug TMAIN1"]),
    ("a backup drive is unplugged", ["unplug TBACKUP_LAST"]),
    ("something holds the main pool busy", ["poolbusy main"]),
    ("a main and a backup drive are unplugged", ["unplug TMAIN1", "unplug TBACKUP_LAST"]),
    ("a main drive is full", ["fill TMAIN1"]),
    ("a main drive is read-only", ["readonly TMAIN1"]),
]
PRE_FLOWS = ["status", "list", "usage", "health", "check", "scan", "rename", "sleep", "wake", "eject", "wipe", "balance", "limit", "resize", "fillorder", "recover", "replace", "disconnect", "move", "release", "restore", "connect"]
FAULT_FLOWS = ["connect", "disconnect", "move", "replace", "recover", "release", "bootsection", "restore", "adopt", "scan"]


def last_label(layout, role):
    n = len(layout.main if role == "main" else layout.backup)
    return ("TMAIN%d" if role == "main" else "TBACKUP%d") % n if n else None


def resolve_fault(layout, spec):
    what, label = spec.split()
    if label == "TBACKUP_LAST":
        label = last_label(layout, "backup")
    if label == "TMAIN1" and not layout.main:
        label = last_label(layout, "backup")
    if not label:
        return None
    return "%s %s" % (what, label)


def run_layout(env, rec, layout, level, st, only_flows, log):
    problems = build_layout(env, layout, log)
    if problems:
        rec.add({"id": "build|" + layout.key, "layout": layout.key, "flow": "build", "args": [], "answers": [], "fault": None,
                 "note": "; ".join(problems), "rc": 1, "secs": 0, "outcome": "BUILD-FAIL", "flags": problems, "msg": "", "changed": False,
                 "prompts": [], "output": "\n".join(problems), "docker": [], "probe": None})
        log("  could not build %s: %s" % (layout.key, problems[0]))
        return
    happy_paths = {}
    for name, args, _what in FLOWS:
        if only_flows and name not in only_flows:
            continue
        t0 = time.time()
        results, happy = explore(env, rec, layout, name, args, level, st["budget"], st["max_dev"], st["depth"])
        happy_paths[name] = happy
        if re.search(st.get("safety") or ".", layout.key):
            run_safety(env, rec, layout, name, results, happy, log)
        bad = sum(1 for r in results if r["outcome"] in ("CRASH", "SILENT-FAIL") or any(f.startswith("INV-") for f in r["flags"]))
        log("  %-12s %3d runs  %4.0fs%s" % (name, len(results), time.time() - t0, ("   !! %d problem(s)" % bad) if bad else ""))
    if re.search(st.get("safety") or ".", layout.key) and (not only_flows or set(only_flows) & {"cli", "list", "usage", "health", "check", "scan"}):
        run_look(env, rec, layout, log)
    if re.search(st.get("safety") or ".", layout.key) and (not only_flows or set(only_flows) & {"rename", "sleep", "wake", "eject", "wipe", "actions"}):
        run_actions(env, rec, layout, log)
    deep = st["faults"] and (st["deep"] is None or any(re.search(p, layout.name) for p in st["deep"]))
    if st["variants"] and (not only_flows or "connect" in only_flows) and len(layout.spares) >= 2 and layout.spares[1].fs == "ext4data":
        # the second spare drive already holds files: connect it and choose "Erase everything" (too deep in the answer tree to be reached by chance)
        explore(env, rec, layout, "connect", FLOWS_BY_NAME["connect"], level, 6, 1, st["depth"], prefix=("2", "1", "2"),
                note="a spare drive with files: choose to erase it")
    if deep and (not only_flows or "restore" in only_flows or "faults" in only_flows):
        explore(env, rec, layout, "restore", FLOWS_BY_NAME["restore"], level, max(6, st["budget"] // 2), 1, st["depth"],
                pre=("lose-files",), note="before the command: some files are gone from the main pool")
    if deep:
        for sname, specs in PRE_SCENARIOS[:st["pre"]]:
            real = [resolve_fault(layout, x) for x in specs]
            if not all(real):
                continue
            for name in PRE_FLOWS:
                if only_flows and name not in only_flows and "faults" not in only_flows:
                    continue
                results, happy = explore(env, rec, layout, name, FLOWS_BY_NAME[name], level, max(6, st["budget"] // 2), min(st["max_dev"], 1),
                                         st["depth"], pre=tuple(real), note="before the command: " + sname)
                if happy and name in FAULT_FLOWS:
                    happy_paths.setdefault(name + "|" + sname, happy)
                bad = sum(1 for r in results if r["outcome"] in ("CRASH", "SILENT-FAIL") or any(f.startswith("INV-") for f in r["flags"]))
                log("  %-12s %3d runs  (%s)%s" % (name, len(results), sname, ("   !! %d problem(s)" % bad) if bad else ""))
    if st["variants"]:
        for label, args in CLI_VARIANTS:
            if only_flows and "cli" not in only_flows:
                continue
            run_case(env, rec, layout, "cli", args, [], note=label, probe=True)
    if deep:
        for name in FAULT_FLOWS:
            if only_flows and name not in only_flows and "faults" not in only_flows:
                continue
            ans = happy_paths.get(name)
            if not ans:
                continue
            n_run = 0
            for fname, spec in FAULTS:
                fs = resolve_fault(layout, spec)
                if not fs:
                    continue
                for at in sorted({1, max(1, len(ans) // 2 + 1), len(ans)}):
                    r = run_case(env, rec, layout, name, FLOWS_BY_NAME[name], ans, fault=(at, fs), note="fault: %s (after answer %d)" % (fname, at))
                    n_run += 1 if r else 0
            log("  %-12s %3d fault runs" % (name + " +faults", n_run))
    teardown(env)


FLOWS_BY_NAME = {n: a for n, a, _ in FLOWS}


CHANGING_FLOWS = ("connect", "disconnect", "move", "adopt", "recover", "replace", "fillorder", "release", "bootsection", "restore", "power", "scan",
                  "rename", "sleep", "wake", "eject", "wipe", "balance", "limit", "resize")
NO_BUSY_FLOWS = ("power", "rename", "sleep", "wake", "eject", "wipe", "fillorder", "limit")      # they stop no container, so they do not wait for a backup
SAFETY_LAYOUTS = r"^(m1-b1|m2-b2|m1-b0|legacy-single-drive|oldpool-m2-b1|m1-b1-bootsec|m2-b1-uneven)$"
BUSY_NOW = "a backup is running right now"


def run_safety(env, rec, layout, name, results, happy, log):
    """--dry-run, --yes and the 'a backup is running' check, on the happy path of one command."""
    if name not in CHANGING_FLOWS or not happy:
        return
    hp = next((r for r in results if r["answers"] == happy and r["outcome"] in ("DONE", "NOTHING")), None)
    if hp is None:
        return
    args = FLOWS_BY_NAME[name]
    kinds = {p["n"]: p["kind"] for p in hp["prompts"]}

    def keep(drop):
        return [a for i, a in enumerate(happy) if kinds.get(i + 1) not in drop]

    def same_result(label):
        def chk(r):
            bad = []
            if r["outcome"] != hp["outcome"] or r["changed"] != hp["changed"]:
                bad.append("INV-%s: the result was %s (changed=%s) but the same answers typed by hand gave %s (changed=%s)"
                           % (label, r["outcome"], r["changed"], hp["outcome"], hp["changed"]))
            return bad
        return chk

    def dry(r):
        bad = []
        if r["changed"]:
            bad.append("INV-dryrun-changed: --dry-run changed the drives, mounts, files or settings")
        if any(l.startswith("docker stop") or l.startswith("docker start") for l in r["docker"]):
            bad.append("INV-dryrun-docker: --dry-run stopped or started containers")
        if r["rc"] != 0:
            bad.append("INV-dryrun-failed: --dry-run exited with %s" % r["rc"])
        elif "DRY RUN" not in r["output"] and "already" not in r["output"]:
            bad.append("INV-dryrun-silent: --dry-run printed no plan")
        return bad

    n = 0
    n += bool(run_case(env, rec, layout, name, args + ["--dry-run"], keep(("typed",)), note="--dry-run", tag="dry", expect=dry))
    yes_only = all(str(a).strip().lower().startswith("y") for i, a in enumerate(happy) if kinds.get(i + 1) == "yn")

    def yes_check(r):    # --yes answers yes to every question; the typed path said "no" somewhere, so the two may differ on purpose
        return same_result("yes-differs")(r) if yes_only else []
    n += bool(run_case(env, rec, layout, name, args + ["--yes", "--confirm-erase"], keep(("yn", "typed")), note="--yes --confirm-erase",
                       tag="yes", expect=yes_check))
    if name not in NO_BUSY_FLOWS and (hp["outcome"] == "DONE" or name == "scan"):
        busy = {"DRIVES_BUSY": BUSY_NOW}

        def declined(r):
            bad = []
            if r["changed"]:
                bad.append("INV-busy-changed: a backup was running, the answer was no, but things changed")
            if r["rc"] != 1 or "Nothing was changed" not in r["output"]:
                bad.append("INV-busy-message: a backup was running and the answer was no: expected a refusal saying nothing was changed (rc=%s)" % r["rc"])
            return bad

        def timed_out(r):
            bad = []
            if r["changed"]:
                bad.append("INV-busy-changed: it gave up waiting for the backup but things changed")
            if r["rc"] != 1 or "Still busy" not in r["output"]:
                bad.append("INV-busy-message: waiting ran out: expected 'Still busy' and exit 1 (rc=%s)" % r["rc"])
            return bad

        def waited(r):
            bad = same_result("busy-wait")(r)
            if "It finished" not in r["output"]:
                bad.append("INV-busy-wait: after the backup ended it did not say it went on")
            return bad

        def with_busy(ans):   # the busy question comes after the person's own answers, except in fillorder: its own question is asked after its first change
            return ans + happy if name == "fillorder" else happy + ans

        n += bool(run_case(env, rec, layout, name, args, with_busy([""]), note="a backup is running, answer no", tag="busy-no",
                           extra_env=busy, expect=declined))
        n += bool(run_case(env, rec, layout, name, args + ["--now"], happy, note="a backup is running, but --now", tag="busy-now",
                           extra_env=busy, expect=same_result("busy-now-differs")))
        n += bool(run_case(env, rec, layout, name, args, with_busy(["y"]), note="a backup is running, wait for too long", tag="busy-long",
                           extra_env=dict(busy, BUSY_POLL_SECS="1", BUSY_MAX_WAIT_SECS="2"), expect=timed_out))
        count_file = os.path.join(env.work, "busy-count.txt")

        def start_wait():   # busy for the next 3 checks, then free: no clock involved, so a slow machine cannot make this flaky
            with open(count_file, "w") as f:
                f.write("3\n")

        n += bool(run_case(env, rec, layout, name, args, with_busy(["y"]), note="a backup is running, wait until it ends", tag="busy-wait",
                           extra_env={"DRIVES_BUSY_COUNT_FILE": count_file, "BUSY_POLL_SECS": "1", "BUSY_MAX_WAIT_SECS": "60"},
                           before_run=start_wait, expect=waited))
    log("  %-12s %3d safety runs (--dry-run, --yes, backup running)" % (name + " +safety", n))


# the look-only commands in words and forms a person or a script may use: (what it is, arguments, expected exit code, text that must appear)
LOOK_CLI = [
    ("list --json", ["list", "--json"], 0, '"drives"'), ("usage --json", ["usage", "--json"], 0, '"pools"'),
    ("usage --folders", ["usage", "--folders"], 0, "Biggest folders"), ("usage --folders --json", ["usage", "--folders", "--json"], 0, '"folders"'),
    ("health --json", ["health", "--json"], 0, '"ok":true'), ("check --json", ["check", "--json"], 0, '"ok":true'),
    ("status --json", ["status", "--json"], 0, '"last_backup"'),
    ("help", ["help"], 0, "Usage:"), ("help release", ["help", "release"], 0, "release"), ("release --help", ["release", "--help"], 0, "release"),
    ("connect -h", ["connect", "-h"], 0, "connect"), ("help with an unknown command", ["help", "bogus"], 1, "no command called"),
    ("--json with a changing command", ["release", "--json"], 1, "--json works with"), ("--full with another command", ["list", "--full"], 1, "--full works with"),
    ("--folders with another command", ["status", "--folders"], 1, "--folders works with"),
    ("a stray word after a command", ["release", "dry-run"], 1, "Unexpected word"), ("an unknown option", ["list", "--bogus"], 1, "Unknown option"),
    ("check --dry-run", ["check", "--dry-run"], 0, "Checked"),
]
# things that go wrong with a drive, and what the look-only commands must then say: (name, environment, before the command, [(flow, args, exit code, text)])
LOOK_SCENARIOS = [
    ("a drive reports it is failing", {"BENCH_SMART": "fail"}, [],
     [("health", ["health"], 1, "FAILED"), ("health", ["health", "--json"], 1, '"ok":false'),
      ("check", ["check"], 1, "SMART says the drive is failing"), ("check", ["check", "--json"], 1, '"result":"problem"')]),
    ("a drive has sectors waiting to be remapped", {"BENCH_SMART": "pending"}, [],
     [("health", ["health"], 1, "waiting to be remapped"), ("check", ["check"], 1, "waiting to be remapped")]),
    ("a drive has remapped sectors", {"BENCH_SMART": "realloc"}, [], [("health", ["health"], 0, "remapped"), ("check", ["check"], 0, "remapped")]),
    ("a drive is hot", {"BENCH_SMART": "hot"}, [], [("health", ["health"], 0, "hot")]),
    ("a drive is asleep", {"BENCH_SMART": "asleep"}, [], [("health", ["health"], 0, "asleep"), ("check", ["check"], 0, "Nothing was changed")]),
    ("a main drive is unplugged", None, ["unplug TMAIN1"],
     [("check", ["check"], 1, "not connected"), ("list", ["list"], 0, "MISSING"), ("usage", ["usage"], 0, ""), ("health", ["health"], 0, "")]),
    ("a main drive turns read-only", None, ["readonly TMAIN1"], [("check", ["check"], 1, "read-only")]),
]


def run_look(env, rec, layout, log):
    """The look-only commands: every form a person or a script may type, and every sick drive they must notice."""
    def want(rc, text):
        def chk(r):
            bad = []
            if r["rc"] != rc:
                bad.append("INV-look-rc: expected exit code %s but it was %s" % (rc, r["rc"]))
            if text not in r["output"]:
                bad.append("INV-look-text: the output should contain '%s'" % text)
            return bad
        return chk

    n = 0
    pooled = bool(layout.main or layout.backup)    # `check` only looks at pool drives; with none it says so (health still sees every drive)
    for label, args, rc, text in LOOK_CLI:
        if not pooled and text == "Checked":
            text = "nothing to check"
        if not pooled and text in ("Biggest folders", '"folders"'):
            text = "NOT MOUNTED" if text == "Biggest folders" else '"mounted":false'      # with no pool there is no folder to measure
        n += bool(run_case(env, rec, layout, "cli", args, [], note=label, probe=False, tag="look", expect=want(rc, text)))
    for sname, envx, specs, checks in LOOK_SCENARIOS:
        real = [resolve_fault(layout, x) for x in specs]
        if not all(real):
            continue
        for flow, args, rc, text in checks:
            if flow == "check" and not pooled:
                continue
            n += bool(run_case(env, rec, layout, flow, args, [], pre=tuple(real), extra_env=envx, note="before the command: " + sname,
                               probe=False, tag="look", expect=want(rc, text)))
    log("  %-12s %3d runs (every form of the look-only commands, sick drives)" % ("look-only", n))


def run_actions(env, rec, layout, log):
    """rename, sleep, wake, eject and wipe: the cases the answer tree cannot reach by itself (a names file that already has lines,
    a USB adapter that ignores the sleep command, a drive that starts asleep) and a look at the result afterwards."""
    n = 0
    spin = any(d.model[1] == 1 for d in layout.all_drives())
    pooled = layout.main or layout.backup
    label = "TMAIN1" if layout.main else ("TBACKUP1" if layout.backup else None)
    names_file = os.path.join(env.state, "drive-names-chosen")

    def want(rc, text, more=None):
        def chk(r):
            bad = []
            if r["rc"] != rc:
                bad.append("INV-action-rc: expected exit code %s but it was %s" % (rc, r["rc"]))
            if text not in r["output"]:
                bad.append("INV-action-text: the output should contain '%s'" % text)
            if more:
                bad += more(r)
            return bad
        return chk

    def seed_names():
        with open(names_file, "w") as f:
            f.write("# my names\nOTHER9=Keep me\n%s=Old name\n" % label)
        env.base_fp = fingerprint(env)

    def renamed(r):
        bad = []
        txt = open(names_file).read() if os.path.exists(names_file) else ""
        lines = [l for l in txt.splitlines() if l.startswith(label + "=")]
        if lines != [label + "=Photos drive"]:
            bad.append("INV-rename-file: the names file should have exactly the line '%s=Photos drive' for this drive, it has %r" % (label, lines))
        if "# my names" not in txt or "OTHER9=Keep me" not in txt:
            bad.append("INV-rename-file: rename removed lines that belong to other drives or comments")
        out = run_shim(env, ["list"], timeout=60)[1]
        if "Photos drive" not in out or "Old name" in out:
            bad.append("INV-rename-list: 'drives list' does not show the new name after rename")
        return bad

    def back_to_auto(r):
        bad = []
        txt = open(names_file).read() if os.path.exists(names_file) else ""
        if (label + "=") in txt or "# my names" not in txt or "OTHER9=Keep me" not in txt:
            bad.append("INV-rename-auto: 'auto' should remove only this drive's line, the file is now %r" % txt)
        if "Old name" in run_shim(env, ["list"], timeout=60)[1]:
            bad.append("INV-rename-list: 'drives list' still shows the old name after 'auto'")
        return bad

    if pooled:
        n += bool(run_case(env, rec, layout, "rename", ["rename"], ["1", "Photos drive"], note="the names file already has lines: rename keeps them",
                           tag="act", before_run=seed_names, expect=want(0, "Done.", renamed), probe=False))
        n += bool(run_case(env, rec, layout, "rename", ["rename"], ["1", "auto"], note="'auto' removes only this drive's name",
                           tag="act", before_run=seed_names, expect=want(0, "Done.", back_to_auto), probe=False))
    cases = [
        ("sleep", {}, ["1"], 0, "is asleep"), ("sleep", {"BENCH_HDPARM": "ignore"}, ["1"], 1, "did not go to sleep"),
        ("sleep", {"BENCH_HDPARM": "silent"}, ["1"], 0, "cannot say"), ("sleep", {"BENCH_HDPARM": "asleep"}, ["1"], 0, "already asleep"),
        ("wake", {"BENCH_HDPARM": "asleep"}, ["1"], 0, "is awake"), ("wake", {}, ["1"], 0, "already awake"),
        ("wake", {"BENCH_HDPARM": "silent"}, ["1"], 0, "cannot say"),
    ]
    for flow, envx, answers, rc, text in cases:
        if not spin:
            rc, text, answers = 1, "No spinning hard drive", []
        n += bool(run_case(env, rec, layout, flow, [flow], answers, extra_env=envx, note="%s%s" % (flow, (" (" + envx["BENCH_HDPARM"] + ")") if envx else ""),
                           tag="act", expect=want(rc, text), probe=False))
        if not spin:
            break

    def wiped_with(fmt):
        def more(r):
            items = r["prompts"][0]["items"] if r["prompts"] else []
            m = re.search(r"\((/dev/[^,)]+)", items[0]) if items else None
            if not m:
                return ["INV-wipe-dev: could not tell which drive was wiped"]
            dev = m.group(1)
            bad = []
            # blkid -p reads the drive itself (lsblk would use the udev database, which does not exist in every container)
            part = sh(["blkid", "-p", "-s", "TYPE", "-s", "LABEL", "-o", "export", dev + "p1"]).stdout
            whole = sh(["blkid", "-p", "-o", "export", dev]).stdout.strip()
            if fmt:
                if "TYPE=ext4" not in part or "LABEL=SPARE" not in part:
                    bad.append("INV-wipe-format: %sp1 should be an empty ext4 drive labelled SPARE, blkid says %r" % (dev, part.split()))
            elif part.strip() or whole or os.path.exists(dev + "p1"):
                bad.append("INV-wipe-empty: %s still has a partition or a file system after the wipe (blkid: %r %r)" % (dev, whole, part.split()))
            return bad
        return more

    spares = len(layout.spares) - (1 if layout.kind == "legacy" else 0)      # the plain data drive of the old setup is in use, never offered
    if spares > 0:
        # --confirm-erase types the drive name and ERASE; the first drive of the list is the one that is wiped
        for fmt in (False, True):
            n += bool(run_case(env, rec, layout, "wipe", ["wipe", "--confirm-erase"], ["1", "2" if fmt else "1"],
                               note="wipe and %s" % ("format it" if fmt else "leave it empty"), tag="act", probe=False,
                               expect=want(0, "Done.", wiped_with(fmt))))
        n += bool(run_case(env, rec, layout, "eject", ["eject"], ["1"], note="get the first spare drive ready to unplug", tag="act",
                           probe=False, expect=want(0, "Done.")))
    n += run_pool_changes(env, rec, layout, want)
    log("  %-12s %3d runs (rename, sleep, wake, wipe, balance, fill order, limit, resize scenarios)" % ("actions", n))


def xattr(pool, name):
    """What the RUNNING mergerfs pool says about itself (None when it cannot be read)."""
    try:
        return os.getxattr(os.path.join(pool, ".mergerfs"), name).decode()
    except OSError:
        return None


def pool_fstab_line(env, pool):
    try:
        for line in open(env.fstab):
            f = line.split()
            if len(f) > 2 and not line.lstrip().startswith("#") and f[1] == pool:
                return line
    except OSError:
        pass
    return ""


def tree_hashes(path):
    """{relative path: sha1} of every file below a folder."""
    out = {}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != "lost+found"]
        for f in files:
            fp = os.path.join(root, f)
            try:
                out[os.path.relpath(fp, path)] = hashlib.sha1(open(fp, "rb").read()).hexdigest()
            except OSError:
                pass
    return out


def run_pool_changes(env, rec, layout, want):
    """balance, fillorder (policy and order), limit and resize: the cases the answer tree cannot reach, each followed by a look at what
    the running pool, the fstab and the files say."""
    n = 0
    roles = [r for r, d in (("main", layout.main), ("backup", layout.backup)) if d]
    if not roles:
        return 0
    role = roles[0]
    pool = env.main if role == "main" else env.backup
    first = "TMAIN1" if role == "main" else "TBACKUP1"
    pick = ["1"] if len(roles) == 2 else []          # the question "Which storage?" is asked when both storages have drives

    def branch_limits():
        line = pool_fstab_line(env, pool)
        out = {}
        for b in (line.split() or [""])[0].split(":"):
            if "=RW," in b:
                path, k = b.split("=RW,")
                out[os.path.basename(path)] = int(k.rstrip("K"))
        return out

    def limit_is(pct):
        def more(r):
            bad = []
            sv = os.statvfs(os.path.join(env.disks, first))
            expect_k = (sv.f_blocks * sv.f_frsize) * pct // 100 // 1024
            got = branch_limits().get(first)
            if got is None or abs(got - expect_k) > 2:
                bad.append("INV-limit-fstab: the pool line should keep ~%dK free on %s (%d%%), it says %r" % (expect_k, first, pct, got))
            live = xattr(pool, "user.mergerfs.branches")
            if live is not None and ("%s=RW,%dK" % (os.path.join(env.disks, first), got or -1)) not in live:
                bad.append("INV-limit-live: the running pool does not use the limit of the fstab line (%r)" % live)
            return bad
        return more

    # --- limit: a size/percent, then auto -------------------------------------------------------------------------------------------
    n += bool(run_case(env, rec, layout, "limit", ["limit"], ["1", "8%"], note="limit 8%", tag="pool", probe=False,
                       expect=want(0, "Done.", limit_is(8))))
    n += bool(run_case(env, rec, layout, "limit", ["limit"], ["1", "auto"], note="limit auto when nothing was set", tag="pool", probe=False,
                       expect=want(0, "already automatic")))
    n += bool(run_case(env, rec, layout, "limit", ["limit"], ["1", "8%", "y"], note="limit 8% when the pool cannot take it while it runs, you say yes",
                       tag="pool-nolive", extra_env={"BENCH_SETFATTR": "fail"}, probe=False, expect=want(0, "Done.", limit_is(8))))
    n += bool(run_case(env, rec, layout, "limit", ["limit"], ["1", "8%", "n"], note="limit 8% when the pool cannot take it while it runs, you say no",
                       tag="pool-nolive-no", extra_env={"BENCH_SETFATTR": "fail"}, probe=False, expect=want(0, "after the next restart")))
    n += bool(run_case(env, rec, layout, "limit", ["limit"], ["1", "8%", "y", "n"], note="limit 8% needs a remount, a backup is running, you say no",
                       tag="pool-busy", extra_env={"BENCH_SETFATTR": "fail", "DRIVES_BUSY": BUSY_NOW}, probe=False,
                       expect=lambda r: want(1, "Nothing was changed")(r) + (["INV-limit-undone: the limit was kept although you stopped it"]
                                                                              if r["changed"] else [])))

    # --- fill order: spread, and it survives the next rebuild of the pool ---------------------------------------------------------
    def spread(r):
        bad = []
        if "category.create=mfs" not in pool_fstab_line(env, pool):
            bad.append("INV-policy-fstab: the pool line does not say category.create=mfs")
        live = xattr(pool, "user.mergerfs.category.create")
        if live is not None and live != "mfs":
            bad.append("INV-policy-live: the running pool says category.create=%s" % live)
        run_shim(env, ["__call", "apply_pool", role], timeout=120)       # any later change rebuilds the pool line
        if "category.create=mfs" not in pool_fstab_line(env, pool):
            bad.append("INV-policy-lost: after the pool line was rebuilt it is back to the old policy")
        return bad

    n += bool(run_case(env, rec, layout, "fillorder", ["fillorder"], pick + ["2"], note="fill order: spread", tag="pool", probe=False,
                       expect=want(0, "Done.", spread)))
    if len(layout.main if role == "main" else layout.backup) >= 2:
        def reordered(r):
            bad = []
            line = pool_fstab_line(env, pool)
            firstb = (line.split() or [""])[0].split(":")[0]
            second = "TMAIN2" if role == "main" else "TBACKUP2"
            if os.path.basename(firstb.split("=")[0]) != second:
                bad.append("INV-order-fstab: %s should be the first drive of the pool line, it is %s" % (second, firstb))
            live = xattr(pool, "user.mergerfs.branches")
            if live is not None and os.path.basename(live.split(":")[0].split("=")[0]) != second:
                bad.append("INV-order-live: the running pool does not use the new order (%r)" % live)
            return bad
        n += bool(run_case(env, rec, layout, "fillorder", ["fillorder"], pick + ["3", "2"], note="fill order: the second drive first", tag="pool",
                           probe=False, expect=want(0, "Done.", reordered)))

    # --- balance: uneven drives really get even, and no file is lost or doubled -------------------------------------------------------
    if layout.kind == "uneven":
        box = {}

        def before_balance():
            box["files"] = tree_hashes(env.main)

        def balanced(r):
            bad = []
            now = tree_hashes(env.main)
            if now != box.get("files"):
                lost = set(box.get("files", {})) - set(now)
                bad.append("INV-balance-files: the main storage changed: %d file(s) missing, %d different" % (
                    len(lost), sum(1 for k in now if k in box["files"] and now[k] != box["files"][k])))
            pcts = []
            for d in ("TMAIN1", "TMAIN2"):
                sv = os.statvfs(os.path.join(env.disks, d))
                pcts.append(100 - 100 * sv.f_bavail // max(1, sv.f_blocks))
            if abs(pcts[0] - pcts[1]) > 25:
                bad.append("INV-balance-uneven: after balance the first two main drives are still %d%% and %d%% full" % tuple(pcts))
            return bad

        n += bool(run_case(env, rec, layout, "balance", ["balance"], ["y"], note="balance the uneven drives", tag="pool", probe=False,
                           before_run=before_balance, expect=want(0, "Done.", balanced)))

    # --- resize a boot drive section: bigger, smaller, too small ---------------------------------------------------------------------
    if layout.boot:
        brole = layout.boot[0]
        bmp = os.path.join(env.disks, "TMAINBOOT" if brole == "main" else "TBACKUPBOOT")
        bpick = ["1"] if len(layout.boot) == 2 else []
        img = os.path.join(env.state, "boot-sections", brole + ".img")
        box = {}

        def fill_section(mb):
            def hook():
                os.makedirs(os.path.join(bmp, "data"), exist_ok=True)
                for i in range(mb // 3):
                    fp = os.path.join(bmp, "data", "f%d.bin" % i)
                    try:
                        with open(fp, "wb") as f:
                            f.write(os.urandom(3 * 1024 * 1024))
                    except OSError:                # the section is full: keep what fits
                        os.unlink(fp)
                        break
                sh(["sync"])
                box["files"] = tree_hashes(bmp)
                box["before"] = os.path.getsize(img)
                env.base_fp = fingerprint(env)
                env.dirty = True
            return hook

        def resized(mb):
            def more(r):
                bad = []
                if not 0 <= mb * 1000000 - os.path.getsize(img) < 8192:        # resize2fs trims the file to whole blocks
                    bad.append("INV-resize-size: the section file should be %d MB, it is %d bytes" % (mb, os.path.getsize(img)))
                if tree_hashes(bmp) != box.get("files"):
                    bad.append("INV-resize-files: the files in the section are not the same after the resize")
                if sh(["e2fsck", "-fn", img]).returncode != 0:
                    bad.append("INV-resize-fsck: the file system of the section has errors after the resize")
                if not os.path.ismount(bmp) or not os.path.ismount(env.main if brole == "main" else env.backup):
                    bad.append("INV-resize-mounts: the section or its pool is not mounted after the resize")
                return bad
            return more

        n += bool(run_case(env, rec, layout, "resize", ["resize"], bpick + ["28", "y"], note="resize: bigger", tag="pool", probe=False,
                           before_run=fill_section(6), expect=want(0, "Done.", resized(28))))
        n += bool(run_case(env, rec, layout, "resize", ["resize", "--confirm-erase"], bpick + ["16", "y"], note="resize: smaller", tag="pool",
                           probe=False, before_run=fill_section(6), expect=want(0, "Done.", resized(16))))
        n += bool(run_case(env, rec, layout, "resize", ["resize", "--confirm-erase"], bpick + ["10", ""], note="resize: too small for its files",
                           tag="pool-small", probe=False, before_run=fill_section(12),
                           expect=lambda r: want(1, "too small")(r) + (["INV-resize-changed: a refused resize changed something"] if r["changed"] else [])))
    return n


def run_wishes(env, rec, layout, log):
    """Which words does `drives` understand? Everything that is only the usage text is 'not supported'."""
    for word, what in WISHES:
        run_case(env, rec, layout, "wish", [word], [], note="%s: %s" % (word, what), probe=False)


def main():
    ap = argparse.ArgumentParser(description="Try every drive command on fake drives and write a report.")
    ap.add_argument("--level", choices=["quick", "standard", "full"], default="standard")
    ap.add_argument("--work", default="/var/tmp/drive-bench", help="folder for the fake drives and the results")
    ap.add_argument("--drives", default=os.path.join(REPO, "scripts", "drives"), help="the drives script to test")
    ap.add_argument("--scripts", default=os.path.join(REPO, "scripts"), help="folder with the other commands")
    ap.add_argument("--layout", action="append", help="only layouts whose name matches this regular expression (repeatable)")
    ap.add_argument("--flow", action="append", help="only this flow (repeatable): " + ", ".join(n for n, _, _ in FLOWS) + ", cli, faults")
    ap.add_argument("--budget", type=int, help="runs per flow and layout (overrides the level)")
    ap.add_argument("--timeout", type=int, default=120, help="seconds before one run is stopped")
    ap.add_argument("--resume", action="store_true", help="continue a stopped run: cases already in results.jsonl are skipped")
    ap.add_argument("--no-other", action="store_true", help="skip the other commands (homelab, homelab-update, ...)")
    ap.add_argument("--other-only", action="store_true", help="only run the other commands")
    ap.add_argument("--no-truth", action="store_true", help="skip the checks that compare the screens of the other commands with the real situation")
    ap.add_argument("--real", choices=["off", "safe", "full"], default="full",
                    help="the other commands on this real server: off, safe (read-only ones) or full (all of them, after you confirm)")
    ap.add_argument("--yes-real", action="store_true", help="do not ask for the typed confirmation before the real commands")
    ap.add_argument("--report-only", action="store_true", help="only rebuild report.txt / report.html from results.jsonl")
    ap.add_argument("--out", help="where the report goes (default: the work folder)")
    a = ap.parse_args()

    if os.geteuid() != 0 and not a.report_only:
        sys.exit("Run it with sudo (loop drives and mounts need root).")
    os.makedirs(a.work, exist_ok=True)
    out_dir = a.out or a.work
    results = os.path.join(a.work, "results.jsonl")
    import report
    if a.report_only:
        report.build(results, out_dir)
        return
    lock = open("/var/tmp/drive-bench.lock", "w")      # kept open until the program ends; not passed on to the commands it starts
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("Another drive-bench is already running on this server. Two runs at once break each other.\n"
                 "Look at it with: tmux attach -t bench     (leave it again with Ctrl+B, then D)\n"
                 "To stop it: tmux attach -t bench, then press Ctrl+C and wait until it says 'finished'.")
    lock.write("%d\n" % os.getpid())
    lock.flush()
    if not a.resume and os.path.exists(results):
        os.rename(results, results + ".old")
    st = level_settings(a.level)
    if a.budget:
        st["budget"] = a.budget
    with open(os.path.join(a.work, "meta.json"), "w") as f:
        json.dump({"level": a.level, "drives": os.path.abspath(a.drives), "started": time.strftime("%F %T"), "host": os.uname().nodename,
                   "budget": st["budget"]}, f)
    env = Env(os.path.join(a.work, "env"), a.drives, a.scripts, a.timeout)
    block_automount(env)
    t_start = time.time()

    def log(*x):
        print(time.strftime("%H:%M:%S"), *x, flush=True)

    def on_term(signum, frame):
        raise SystemExit("stopped (signal %d)" % signum)
    signal.signal(signal.SIGTERM, on_term)
    free = shutil.disk_usage(a.work).free
    if free < 3 * 1024 ** 3:
        sys.exit("Not enough free space in %s (%.1f GB free, 3 GB needed). Use --work with another folder." % (a.work, free / 1024 ** 3))
    for bad in ("/mnt/storage", "/mnt/backup", "/mnt/disks"):
        if os.path.abspath(a.work).startswith(bad):
            sys.exit("--work must not be inside %s" % bad)
    rec = Recorder(results)
    for tool in ("losetup", "mkfs.ext4", "mergerfs", "parted", "rsync", "fallocate", "blkid", "e2label", "wipefs", "partprobe"):
        if not shutil.which(tool):
            sys.exit("Missing tool: %s   (sudo apt install -y mergerfs rsync parted e2fsprogs util-linux)" % tool)
    if not os.path.exists(a.drives):
        sys.exit("The drives script is not there: %s" % a.drives)
    install_fakes(env)
    teardown(env)       # leftovers of an earlier stopped run
    rc, out, _, _, _ = run_shim(env, ["__call", "__check_env"], timeout=30)
    want = "1|%s|%s|%s|%s|%s" % (env.fstab, env.main, env.backup, env.disks, env.state)
    if want not in out:
        sys.exit("This drives script does not use the bench's test folders (it printed: %s). Refusing to run, so that nothing real is touched." % out.strip()[-300:])
    try:
        if not a.other_only:
            before = real_backup_stamp()
            lay = layouts_for(a.level, a.layout)
            log("level %s: %d layouts, up to %d runs per flow" % (a.level, len(lay), st["budget"]))
            flows = set(a.flow or [])
            for i, layout in enumerate(lay, 1):
                log("[%d/%d] layout %s  (%s)" % (i, len(lay), layout.name, layout.describe()))
                run_layout(env, rec, layout, a.level, st, flows, log)
            after = real_backup_stamp()
            if after != before:
                log("WARNING: the real backup log or status changed while the fake drives were tested. Something started the real backup.")
            if st["wishes"] and (not flows or "wish" in flows):
                lay0 = layouts_for(a.level, ["^m2-b1$"]) or layouts_for(a.level)[:1]
                if lay0:
                    log("probing words people might expect (rename, smart, sleep ...)")
                    if build_layout(env, lay0[0]) == []:
                        run_wishes(env, rec, lay0[0], log)
        if not a.no_other or a.other_only:
            import others
            others.run(env, rec, a, log)
    finally:
        teardown(env)
        unblock_automount()
        log("finished %d runs in %.0f minutes" % (rec.count, (time.time() - t_start) / 60))
    report.build(results, out_dir)
    log("report: %s/report.html and %s/report.txt" % (out_dir, out_dir))


if __name__ == "__main__":
    main()
