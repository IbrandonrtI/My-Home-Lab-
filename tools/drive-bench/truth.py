"""Does the screen tell the truth?

The other commands (homelab, homelab-sample, homelab-update ...) are run in situations that are set up on purpose (a pool that is not
mounted, a backup that failed, a drive that is too hot, a container that is down ...) and what they print is compared with what is
really there. Two parts:

  1. scenarios   (on fake layouts)  one known situation -> the exact words and numbers that must be on the screen
  2. contract    (once)             version, help, unknown words and the commands named in the lists: every word printed in a list
                                    of commands must be a command that exists, and every word a script accepts must be in its help

Flags that start with INV-truth are numbers or sentences that do not match the situation. "unclear:" flags are about help texts.
"""
import math
import os
import re
import shutil
import subprocess
import time

import bench
import others

LAB_DOCKER = r'''#!/bin/bash
# a made-up docker for the homelab scripts: LAB_CONTAINERS has one line per container: name|state|restart policy|restarts|started|health
case "$1" in
  info) [ -e "$LAB_DOCKER_DOWN" ] && exit 1; exit 0 ;;
  ps)
    case "$*" in
      *health=unhealthy*) awk -F'|' '$6 == "unhealthy" {print $1}' "$LAB_CONTAINERS" ;;
      *-aq*|*-q*) cut -d'|' -f1 "$LAB_CONTAINERS" ;;
      *--format*) cut -d'|' -f1 "$LAB_CONTAINERS" ;;
    esac ;;
  inspect)
    shift; ids=(); fmt=""
    while [ $# -gt 0 ]; do if [ "$1" = "--format" ]; then fmt=$2; shift 2; else ids+=("$1"); shift; fi; done
    for id in "${ids[@]}"; do
      case "$fmt" in
        *Config.Image*) awk -F'|' -v n="$id" '$1 == n {print $1 "|/" $1 "|" $1 ":latest|sha256:" $1 "|" $1}' "$LAB_CONTAINERS" ;;
        *) awk -F'|' -v n="$id" '$1 == n {print "/" $1, $2, $3, $4, $5}' "$LAB_CONTAINERS" ;;
      esac
    done ;;
  exec) head -c 4096 /dev/urandom ;;
  *) exit 0 ;;
esac
'''

ICON = r"(?:\+|!|x|✓|✗)"
OK, WARN, BAD = "ok", "warn", "bad"
MARK = {"+": OK, "✓": OK, "!": WARN, "x": BAD, "✗": BAD}


def iec(n):
    """numfmt --to=iec --suffix=B (rounds up), as homelab prints sizes."""
    n = float(n)
    units = ["", "K", "M", "G", "T", "P"]
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024.0
        i += 1
    if i == 0:
        return "%dB" % int(n)
    if n < 10:
        return "%.1f%sB" % (math.ceil(n * 10) / 10.0, units[i])      # numfmt always writes one decimal below 10
    return "%d%sB" % (math.ceil(n), units[i])


def size_in_bytes(text):
    m = re.fullmatch(r"([\d.]+)\s*([KMGTP]?)(?:i?B)?", text.strip())
    if not m:
        return None
    return float(m.group(1)) * 1024 ** ("", "K", "M", "G", "T", "P").index(m.group(2))


def close(shown, truth):
    """A size printed by df -h (rounded up to the shown unit) must match the real size to within one unit of what is printed."""
    s = size_in_bytes(shown)
    if s is None:
        return False
    unit = 1024 ** int(math.log(max(s, 1), 1024)) if s >= 1024 else 1
    return abs(s - truth) <= max(unit * 1.01, truth * 0.02)


def status_rows(out):
    """{name: (mark, text)} from the lines of the Status block."""
    rows = {}
    if re.search(r"^\s*[-─]+ Status [-─]+", out, re.M):       # the summary line above the block looks like a row: leave it out
        out = re.split(r"^\s*[-─]+ Status [-─]+\s*$", out, maxsplit=1, flags=re.M)[-1]
        out = re.split(r"^\s*[-─]+ Suggested Commands", out, maxsplit=1, flags=re.M)[0]
    for line in out.splitlines():
        m = re.match(r"^\s+(%s)\s{1,3}(\S[^\n]*?)\s{2,}(\S.*)$" % ICON, line)
        if m:
            rows[m.group(2).strip()] = (MARK[m.group(1)], m.group(3).strip())
    return rows


class Ctx:
    def __init__(self, env, layout, tag):
        self.env, self.layout, self.tag = env, layout, tag
        self.dir = os.path.join(env.work, "truth", re.sub(r"\W", "_", tag))
        shutil.rmtree(self.dir, ignore_errors=True)
        self.state = os.path.join(self.dir, "state")
        self.cache = os.path.join(self.dir, "cache")
        self.sections = os.path.join(self.dir, "sections")
        self.bin = os.path.join(self.dir, "bin")
        for d in (self.state, self.cache, self.sections, self.bin):
            os.makedirs(d, exist_ok=True)
        self.last_run = os.path.join(self.state, "last-run")
        self.containers = os.path.join(self.dir, "containers")
        self.docker_down = os.path.join(self.dir, "docker-down")
        with open(os.path.join(self.bin, "docker"), "w") as f:
            f.write(LAB_DOCKER)
        os.chmod(os.path.join(self.bin, "docker"), 0o755)
        self.conf = os.path.join(self.dir, "backup.conf")
        self.log_file = os.path.join(self.state, "backup.log")
        self.nolock = os.path.join(self.dir, "nolock.sh")
        with open(self.nolock, "w") as f:
            f.write("flock() { return 0; }\n")     # a test run must not take the lock of the real backup
        self.write_conf()
        self.write_containers([("nextcloud", "running", "always", 0, "2026-01-01T00:00:00Z", ""),
                               ("immich_server", "running", "unless-stopped", 0, "2026-01-01T00:00:00Z", ""),
                               ("filebrowser", "running", "always", 0, "2026-01-01T00:00:00Z", "")])

    def write_conf(self, min_free_gb=0, fallback=""):
        with open(self.conf, "w") as f:
            f.write('SRC="%s"\nDEST_POOL="%s"\nDEST_FALLBACK="%s"\nLOGFILE="%s"\nSTATUS_FILE="%s"\nCONFIG_PATHS=()\nMIN_FREE_GB=%d\n'
                    'NEXTCLOUD_DB_CONTAINER="nextcloud"\n' % (self.env.main, self.env.backup, fallback, self.log_file, self.last_run, min_free_gb))

    def write_containers(self, rows):
        with open(self.containers, "w") as f:
            for r in rows:
                f.write("|".join(str(x) for x in r) + "\n")

    def write_state(self, name, text):
        with open(os.path.join(self.state, name), "w") as f:
            f.write(text)

    def environ(self, extra=None):
        e = self.env.environ()
        e.update({"HOMELAB_MAIN_POOL": self.env.main, "HOMELAB_BACKUP_POOL": self.env.backup, "HOMELAB_DISKS_DIR": self.env.disks,
                  "HOMELAB_STATE_DIR": self.state, "HOMELAB_CACHE_DIR": self.cache, "HOMELAB_LAST_RUN_FILE": self.last_run,
                  "HOMELAB_BOOT_SECTION_DIR": self.sections, "HOMELAB_USER": "root", "HOMELAB_ALLOW_ROOT": "1",
                  "HOMELAB_UPTIME": "999999", "LAB_CONTAINERS": self.containers, "LAB_DOCKER_DOWN": self.docker_down,
                  "BACKUP_CONF": self.conf, "BASH_ENV": self.nolock,
                  "HOMELAB_EXTRA_PATH": self.bin + ":" + e.get("HOMELAB_EXTRA_PATH", ""), "PATH": self.bin + ":" + e.get("PATH", ""), "HOME": self.dir, "NAMES_FILE": os.path.join(self.dir, "no-names"),
                  "HOMELAB_NAMES_FILE": os.path.join(self.dir, "no-names")})
        if extra:
            e.update(extra)
        return e

    def run(self, cmd, args, extra=None, stdin="", timeout=120):
        path = others.find(self.env, cmd)
        return others.run_plain(others.interpreter(path) + args, stdin, self.environ(extra), timeout)


def stamp_ago(hours):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - hours * 3600))


# ------------------------------------------------------------------------------------------------------------ the scenarios
# Every scenario: (name, setup(ctx), command args, extra env, check(ctx, rc, out) -> list of problems)
def want(*pairs):
    """pairs of (row name, mark or None, regex of the text or None, regex that must NOT be there or None)"""
    def check(ctx, rc, out):
        bad = []
        rows = status_rows(out)
        for name, mark, rx, nrx in pairs:
            if name not in rows:
                bad.append("INV-truth-row: the line '%s' is missing from the status" % name)
                continue
            m, text = rows[name]
            if mark and m != mark:
                bad.append("INV-truth-mark: '%s' is shown as %s but it should be %s (%s)" % (name, m, mark, text))
            if rx and not re.search(rx, text):
                bad.append("INV-truth-text: '%s' says %r, it should match %r" % (name, text, rx))
            if nrx and re.search(nrx, text):
                bad.append("INV-truth-text: '%s' says %r, which must not match %r" % (name, text, nrx))
        if rc != 0:
            bad.append("INV-truth-rc: homelab status exited with %s" % rc)
        return bad
    return check


def none(ctx):
    pass


def real_pools(ctx, out):
    """The pool lines against what is mounted, with the real sizes."""
    bad = []
    env = ctx.env
    rows = status_rows(out)

    def mounted(path):
        return subprocess.run(["findmnt", "-n", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    for name, pool in (("Main pool", env.main), ("Backup pool", env.backup)):
        if name not in rows:
            bad.append("INV-truth-row: '%s' is missing" % name)
            continue
        mark, text = rows[name]
        if mounted(pool):
            if not text.startswith("mounted"):
                bad.append("INV-truth-pool: %s is mounted but the screen says %r" % (name, text))
            m = re.search(r"mounted, (\S+) used of (\S+)", text)
            if name == "Main pool" and m:
                sv = os.statvfs(pool)
                total, used = sv.f_blocks * sv.f_frsize, (sv.f_blocks - sv.f_bfree) * sv.f_frsize
                if not close(m.group(1), used):
                    bad.append("INV-truth-number: Main pool 'used' says %s, the real value is %s" % (m.group(1), iec(used)))
                if not close(m.group(2), total):
                    bad.append("INV-truth-number: Main pool 'size' says %s, the real value is %s" % (m.group(2), iec(total)))
            if name == "Main pool" and not m:
                bad.append("INV-truth-text: Main pool is mounted but the line has no 'N used of M': %r" % text)
        else:
            want_text = "NOT MOUNTED" if name == "Main pool" else "not connected"
            if want_text not in text and "no data drive set up yet" not in text:
                bad.append("INV-truth-pool: %s is NOT mounted but the screen says %r" % (name, text))
            if name == "Main pool" and mark != BAD and "no data drive" not in text:
                bad.append("INV-truth-mark: an unmounted main pool must be shown as a failure")
    return bad


def boot_drive(ctx, out):
    rows = status_rows(out)
    if "Boot drive" not in rows:
        return ["INV-truth-row: 'Boot drive' is missing"]
    text = rows["Boot drive"][1]
    sv = os.statvfs("/")
    used_pct = math.ceil(100.0 * (sv.f_blocks - sv.f_bfree) / (sv.f_blocks - sv.f_bfree + sv.f_bavail))
    free = sv.f_bavail * sv.f_frsize
    m = re.match(r"(\d+)% used, (\S+) free", text)
    if not m:
        return ["INV-truth-text: Boot drive says %r (expected 'N%% used, X free')" % text]
    bad = []
    if abs(int(m.group(1)) - used_pct) > 1:
        bad.append("INV-truth-number: Boot drive says %s%% used, the real value is %d%%" % (m.group(1), used_pct))
    if not close(m.group(2), free):
        bad.append("INV-truth-number: Boot drive says %s free, the real value is %s" % (m.group(2), iec(free)))
    return bad


def setup_none(ctx):
    pass


def setup_lastrun(stamp_hours, result="OK", bytes_=27013182, dest=None):
    def f(ctx):
        ctx.write_state("last-run", "%s|%s|%s|0|%s\n" % (stamp_ago(stamp_hours), result, dest or ctx.env.backup, bytes_ if bytes_ is not None else ""))
    return f


def setup_temps(rows, age_min=1):
    def f(ctx):
        ep = int(time.time()) - age_min * 60
        ctx.write_state("temps", "".join("%s|/dev/sd%s|%s|%d\n" % (lab, chr(97 + i), t, ep) for i, (lab, t) in enumerate(rows)))
    return f


def setup_umount_pools(which):
    def f(ctx):
        for p in which(ctx):
            subprocess.run(["umount", "-l", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ctx.env.dirty = True
    return f


def seq(*fs):
    def f(ctx):
        for g in fs:
            g(ctx)
    return f


def setup_containers(rows):
    return lambda ctx: ctx.write_containers(rows)


def setup_docker_down(ctx):
    open(ctx.docker_down, "w").close()


def setup_sections(sizes):
    def f(ctx):
        for i, sz in enumerate(sizes):
            with open(os.path.join(ctx.sections, "s%d.img" % i), "wb") as fh:
                fh.truncate(sz)
    return f


def pools_and(extra):
    def check(ctx, rc, out):
        return real_pools(ctx, out) + extra(ctx, rc, out)
    return check


def with_rows(*pairs):
    w = want(*pairs)
    return lambda ctx, rc, out: w(ctx, rc, out)


T0 = "2026-01-01T00:00:00Z"


def scenarios():
    S = []

    def add(name, setup, check, args=("status",), extra=None):
        S.append((name, setup, list(args), extra or {}, check))

    add("pools as they are, with the real sizes", setup_none, lambda c, rc, o: real_pools(c, o))
    add("boot drive line is the real one", setup_none, lambda c, rc, o: boot_drive(c, o))
    add("both pools unmounted", setup_umount_pools(lambda c: [c.env.main, c.env.backup]), lambda c, rc, o: real_pools(c, o))
    add("main pool unmounted, 'no data drive' marker", seq(setup_umount_pools(lambda c: [c.env.main]), lambda c: c.write_state("no-data-drive", "")),
        lambda c, rc, o: with_rows(("Main pool", WARN, r"no data drive set up yet", None))(c, rc, o))
    # last backup
    add("last backup: fresh and OK", setup_lastrun(0), with_rows(("Last backup", OK, r"\(0 h ago\)", None)))
    add("last backup: 5 hours old", setup_lastrun(5), with_rows(("Last backup", OK, r"\(5 h ago\)", None)))
    add("last backup: 40 hours old", setup_lastrun(40), with_rows(("Last backup", WARN, r"\(40 h ago\).*older than 36 h", None)))
    add("last backup: failed", setup_lastrun(1, "FAILED"), with_rows(("Last backup", BAD, r"FAILED.*homelab-backup\.log", None)))
    add("last backup: no result yet (folder exists)", lambda c: None, with_rows(("Last backup", WARN, r"no result found", None)))
    add("last backup: never ran", lambda c: None, with_rows(("Last backup", WARN, r"no backup has run yet", None)),
        extra={"HOMELAB_LAST_RUN_FILE": "/nonexistent-dir-for-truth/last-run"})
    # backup size and schedule
    add("backup size: 26 MB", setup_lastrun(0, "OK", 27013182), with_rows(("Backup size", OK, r"^%s in the backup" % re.escape(iec(27013182)), None)))
    add("backup size: 3 GB", setup_lastrun(0, "OK", 3221225472), with_rows(("Backup size", OK, r"^3\.0GB in the backup|^3GB in the backup", None)))
    add("backup size: unknown until the next run", setup_lastrun(0, "OK", None), with_rows(("Backup size", OK, r"size shows after the next backup run", None)))
    add("backup schedule: daily 06:00", seq(setup_lastrun(0), lambda c: c.write_state("schedule", "0|6|*|*|*|%d\n" % int(time.time()))),
        with_rows(("Backup size", OK, r"next run 06:00 \(in (\d+ h|\d+ min|soon)\)", None)))
    add("backup schedule: not a plain daily line", seq(setup_lastrun(0), lambda c: c.write_state("schedule", "*/5|*|*|*|*|%d\n" % int(time.time()))),
        with_rows(("Backup size", OK, r"next run see root's crontab", None)))
    # temperatures
    add("temps: none yet", setup_none, with_rows(("Drive temps", WARN, r"no readings yet", None)))
    add("temps: empty file", lambda c: c.write_state("temps", ""), with_rows(("Drive temps", WARN, r"no readings \(is smartmontools", None)))
    add("temps: all fine", setup_temps([("MAIN1", 35), ("BACKUP1", 38)]), with_rows(("Drive temps", OK, r"35°C.*38°C", r"warm|hot")))
    add("temps: getting warm (50)", setup_temps([("MAIN1", 35), ("BACKUP1", 50)]), with_rows(("Drive temps", WARN, r"50°C.*getting warm", None)))
    add("temps: just under warm (49)", setup_temps([("MAIN1", 49)]), with_rows(("Drive temps", OK, r"49°C", r"warm|hot")))
    add("temps: too hot (60)", setup_temps([("MAIN1", 60)]), with_rows(("Drive temps", BAD, r"60°C.*too hot", None)))
    add("temps: a drive asleep", setup_temps([("MAIN1", "standby"), ("BACKUP1", 40)]), with_rows(("Drive temps", OK, r"asleep.*40°C|40°C.*asleep", None)))
    add("temps: readings are old", setup_temps([("MAIN1", 35)], age_min=120), with_rows(("Drive temps", WARN, r"readings are 120 min old", None)))
    # updates
    add("updates: system up to date", lambda c: c.write_state("apt", "0|%d\n" % int(time.time())), with_rows(("Updates", OK, r"system is up to date", None)))
    add("updates: 5 waiting", lambda c: c.write_state("apt", "5|%d\n" % int(time.time())), with_rows(("Updates", WARN, r"5 system update\(s\)", None)))
    add("updates: newer images", lambda c: c.write_state("image-updates", "%d\nnextcloud x\nimmich y\n" % (int(time.time()) - 2 * 86400)),
        with_rows(("Updates", WARN, r"newer images: nextcloud, immich.*checked 2 d ago", None)))
    add("updates: images up to date", lambda c: c.write_state("image-updates", "%d\n" % int(time.time())),
        with_rows(("Updates", OK, r"container images up to date.*checked 0 d ago", None)))
    # containers
    add("containers: all running", setup_none, with_rows(("Containers", OK, r"^3 of 3 running$", None)))
    add("containers: one down", setup_containers([("nextcloud", "running", "always", 0, T0, ""), ("immich_server", "exited", "unless-stopped", 0, T0, ""),
                                                 ("filebrowser", "running", "always", 0, T0, "")]),
        with_rows(("Containers", BAD, r"^2 of 3 running; not running: immich_server$", None)))
    add("containers: stopped on purpose is ignored", setup_containers([("nextcloud", "running", "always", 0, T0, ""), ("old", "exited", "no", 0, T0, "")]),
        with_rows(("Containers", OK, r"^1 of 1 running$", None)))
    add("containers: one unhealthy", setup_containers([("nextcloud", "running", "always", 0, T0, "unhealthy"), ("filebrowser", "running", "always", 0, T0, "")]),
        with_rows(("Containers", WARN, r"^2 of 2 running; unhealthy: nextcloud$", None)))
    add("containers: Docker cannot be read", setup_docker_down, with_rows(("Containers", WARN, r"cannot read Docker|not running", None)))
    add("containers: right after a boot (login screen)", setup_none,
        lambda c, rc, o: with_rows(("Containers", WARN, r"just started", None))(c, rc, o), args=("login",), extra={"HOMELAB_UPTIME": "60"})
    # the boot drive and the sections
    add("boot drive with a section file", setup_sections([5 * 10 ** 9, 2 * 10 ** 9]),
        with_rows(("Boot drive", None, r"sections for pools: 5 GB, 2 GB", None)))
    # the login screen counts
    add("login: the count matches the lines", lambda c: c.write_state("apt", "3|%d\n" % int(time.time())), login_count, args=("login",))
    add("login: all good wording", seq(setup_lastrun(0), lambda c: c.write_state("apt", "0|%d\n" % int(time.time())),
                                         setup_temps([("MAIN1", 35)]), lambda c: c.write_state("schedule", "0|6|*|*|*|1\n")), login_count, args=("login",))
    return S


def login_count(ctx, rc, out):
    """The sentence at the top of the login screen must agree with the marks in the status block: problems if any line is a failure,
    otherwise the number of lines to look at, otherwise 'Everything looks fine'."""
    bad = []
    rows = status_rows(out)
    nbad = sum(1 for m, _ in rows.values() if m == BAD)
    nwarn = sum(1 for m, _ in rows.values() if m == WARN)
    top = out.split("Status ---")[0] if "Status ---" in out else out
    if nbad:
        want = r"\b%d problem%s %s you\." % (nbad, "" if nbad == 1 else "s", "needs" if nbad == 1 else "need")
        why = "%d problem(s)" % nbad
    elif nwarn:
        want = r"\b%d thing%s to look at\." % (nwarn, "" if nwarn == 1 else "s")
        why = "%d thing(s) to look at" % nwarn
    else:
        want = r"Everything looks fine\."
        why = "everything fine"
    if not re.search(want, top):
        bad.append("INV-truth-count: the status has %s but the top of the login screen says %r" % (why, [l.strip() for l in top.splitlines() if l.strip()][1:3]))
    sug = re.findall(r"^\s+(sudo [^\n]+|docker [^\n]+)$", out.split("Suggested Commands")[-1], re.M) if "Suggested Commands" in out else []
    if len(sug) > 6:
        bad.append("INV-truth-count: %d suggested commands are shown, the most is 6" % len(sug))
    return bad


# ------------------------------------------------------------------------------------------------------- the backup, the sampler ...
def tree_hashes(path, skip=()):
    import hashlib
    out = {}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != "lost+found" and os.path.join(root, d) not in skip]
        for f in files:
            fp = os.path.join(root, f)
            try:
                out[os.path.relpath(fp, path)] = hashlib.sha1(open(fp, "rb").read()).hexdigest()
            except OSError:
                pass
    return out


def last_run_fields(ctx):
    try:
        f = open(ctx.last_run).read().strip().split("|")
    except OSError:
        return None
    return f + [""] * (5 - len(f))


def backup_scenarios(env, rec, layout, log):
    """homelab-backup: what it copies, what it keeps of deleted and changed files, and that it refuses instead of emptying the backup."""
    done = 0
    pooled = bool(layout.main) and bool(layout.backup)
    if not pooled:
        return 0

    def full(ctx, rc, out, log_text, pre):
        """The backup drive has no room (a nearly full layout): the backup must fail, say so and record it."""
        f = last_run_fields(ctx)
        bad = []
        if rc == 0:
            bad.append("INV-truth-rc: the backup exited with 0 although the backup drive has no room")
        if not f or not f[1].startswith("FAILED"):
            bad.append("INV-truth-backup: the backup drive is full but the last-run file says %r" % (f and f[1]))
        return bad

    def go(name, setup, check, min_free=0, fallback=""):
        nonlocal done
        cid = "truth|%s|backup: %s" % (layout.key, name)
        if cid in rec.done:
            return
        if env.current != layout.key or env.dirty:
            bench.restore_layout(env)
            env.current = layout.key
        ctx = Ctx(env, layout, "%s-backup-%s" % (layout.key, name))
        ctx.write_conf(min_free, fallback)
        pre = setup(ctx) if setup else None
        rc, out, secs, to = ctx.run("homelab-backup", [])
        log_text = open(ctx.log_file).read() if os.path.exists(ctx.log_file) else ""
        shown = out + "\n[backup log]\n" + "".join(log_text.splitlines(True)[-8:]) + "[last-run] " + (open(ctx.last_run).read() if os.path.exists(ctx.last_run) else "(none)\n")
        if "No space left on device" in shown and name in ("a normal backup copies every file", "a second backup changes nothing",
                                                          "the database container is not running: files are still copied"):
            problems = full(ctx, rc, out, log_text, pre) + bad_text(shown)
        else:
            problems = check(ctx, rc, out, log_text, pre) + bad_text(shown)
        outcome, flags, msg = others.judge(rc, out, to, expect_fail=True)
        # run by cron the backup prints nothing: its reasons are in its log (shown below the output)
        flags = [f for f in flags if not f.startswith(("exit 0 although", "exit 1 without"))
                 and not (f.startswith("bash-error") and "No space left on device" in shown)] + problems
        if problems:
            outcome = "BUG"
        elif rc != 0:
            outcome = "REFUSED"
        env.dirty = True
        others.record(rec, cid, layout.key, "other:truth: backup: " + name, [], "", rc, shown, secs, outcome, flags, msg, "")
        done += 1

    def normal(ctx, rc, out, log_text, pre):
        bad = []
        f = last_run_fields(ctx)
        if rc != 0:
            bad.append("INV-truth-rc: a normal backup exited with %s" % rc)
        if not f or f[1] != "OK":
            bad.append("INV-truth-backup: the last-run file says %r, it should say OK" % (f and f[1]))
            return bad
        if f[2] != ctx.env.backup:
            bad.append("INV-truth-backup: the backup went to %s, it should go to %s" % (f[2], ctx.env.backup))
        src = tree_hashes(ctx.env.main)
        dst = tree_hashes(os.path.join(ctx.env.backup, "main"))
        miss = [k for k in src if k not in dst]
        diff = [k for k in src if k in dst and src[k] != dst[k]]
        if miss or diff:
            bad.append("INV-truth-backup: %d file(s) are missing and %d differ in the backup (e.g. %s)" % (len(miss), len(diff), (miss + diff)[0]))
        extra = [k for k in dst if k not in src]
        if extra:
            bad.append("INV-truth-backup: the backup has %d file(s) that the main storage does not (e.g. %s)" % (len(extra), extra[0]))
        real = int(subprocess.run(["du", "-sb", ctx.env.backup], stdout=subprocess.PIPE, text=True).stdout.split()[0])
        if f[4].isdigit() and abs(int(f[4]) - real) > max(real * 0.03, 70000):
            bad.append("INV-truth-number: last-run says the backup is %s bytes, it is %d bytes (the login screen shows this size)" % (f[4], real))
        if "finished: OK" not in log_text:
            bad.append("INV-truth-backup: the log has no 'finished: OK' line")
        return bad

    go("a normal backup copies every file", None, normal)

    def twice(ctx):
        ctx.run("homelab-backup", [])
        pre = {"first": tree_hashes(ctx.env.backup)}
        return pre

    def second(ctx, rc, out, log_text, pre):
        bad = normal(ctx, rc, out, log_text, pre)
        after = tree_hashes(ctx.env.backup)
        added = [k for k in after if k not in pre["first"] and not k.startswith(("_deleted", "db-dumps", "boot-configs"))]
        if added:
            bad.append("INV-truth-backup: a second backup without changes added %d file(s) (e.g. %s)" % (len(added), added[0]))
        return bad

    go("a second backup changes nothing", twice, second)

    def keep_old(ctx):
        ctx.run("homelab-backup", [])
        files = sorted(tree_hashes(ctx.env.main))
        gone, changed = files[0], files[-1]
        os.unlink(os.path.join(ctx.env.main, gone))
        old_hash = tree_hashes(os.path.join(ctx.env.backup, "main")).get(changed)
        if old_hash is None:          # the first backup could not copy everything (a nearly full backup drive): nothing to compare
            return {"na": "the first backup did not copy %s" % changed}
        with open(os.path.join(ctx.env.main, changed), "ab") as fh:
            fh.write(b"changed after the first backup")
        return {"gone": gone, "changed": changed, "old": old_hash}

    def kept(ctx, rc, out, log_text, pre):
        bad = []
        if "na" in pre:
            return bad
        today = time.strftime("%F")
        base = os.path.join(ctx.env.backup, "_deleted", today, "main")
        if os.path.exists(os.path.join(ctx.env.backup, "main", pre["gone"])):
            bad.append("INV-truth-backup: a file deleted from the main storage is still in the backup's main folder")
        if not os.path.exists(os.path.join(base, pre["gone"])):
            bad.append("INV-truth-backup: the deleted file %s was not kept in _deleted/%s" % (pre["gone"], today))
        old = tree_hashes(base).get(pre["changed"])
        if old != pre["old"]:
            bad.append("INV-truth-backup: the old version of the changed file %s was not kept in _deleted/%s" % (pre["changed"], today))
        if rc != 0:
            bad.append("INV-truth-rc: the backup exited with %s" % rc)
        return bad

    go("deleted and changed files are kept for 30 days", keep_old, kept)

    def refuse(what, fragment, setup):
        def check(ctx, rc, out, log_text, pre):
            bad = []
            f = last_run_fields(ctx)
            if rc == 0:
                bad.append("INV-truth-rc: the backup exited with 0 although %s" % what)
            if not f or not f[1].startswith("FAILED") or fragment not in f[1]:
                bad.append("INV-truth-backup: the last-run file should say FAILED ... %r, it says %r" % (fragment, f and f[1]))
            if pre and "snapshot" in pre:
                if tree_hashes(os.path.join(ctx.env.backup, "main")) != pre["snapshot"]:
                    bad.append("INV-truth-backup: a refused backup changed the existing backup")
            return bad
        return setup, check

    def unmount_backup(ctx):
        subprocess.run(["umount", "-l", ctx.env.backup], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {}
    s_, c_ = refuse("the backup storage is not mounted", "not mounted", unmount_backup)
    go("the backup storage is not mounted", s_, c_)

    def unmount_main(ctx):
        subprocess.run(["umount", "-l", ctx.env.main], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {}
    s_, c_ = refuse("the main storage is not mounted", "not mounted", unmount_main)
    go("the main storage is not mounted", s_, c_)

    def emptied(ctx):
        ctx.run("homelab-backup", [])
        snap = tree_hashes(os.path.join(ctx.env.backup, "main"))
        for name in os.listdir(ctx.env.main):
            if name != "lost+found":
                subprocess.run(["rm", "-rf", os.path.join(ctx.env.main, name)])
        return {"snapshot": snap}
    s_, c_ = refuse("the main storage is empty (it must not empty the backup)", "looks empty", emptied)
    go("the main storage is empty: the backup is not emptied", s_, c_)

    def no_db(ctx):
        ctx.write_containers([("filebrowser", "running", "always", 0, T0, "")])
        return {}

    def db_check(ctx, rc, out, log_text, pre):
        bad = []
        f = last_run_fields(ctx)
        if rc == 0:
            bad.append("INV-truth-rc: the backup exited with 0 although the database was not dumped")
        if not f or "database not dumped" not in f[1]:
            bad.append("INV-truth-backup: the last-run file should say the database was not dumped, it says %r" % (f and f[1]))
        src, dst = tree_hashes(ctx.env.main), tree_hashes(os.path.join(ctx.env.backup, "main"))
        if any(k not in dst for k in src):
            bad.append("INV-truth-backup: the files were not copied after the database step failed (they should be)")
        return bad
    go("the database container is not running: files are still copied", no_db, db_check)

    def small(ctx):
        return {}
    s_, c_ = refuse("there is not enough free space", "need at least", small)
    go("not enough free space", s_, c_, min_free=100000)
    return done


def sampler_scenarios(env, rec, layout, log):
    cid = "truth|%s|sample: schedule and files" % layout.key
    if cid in rec.done:
        return 0
    if env.current != layout.key or env.dirty:
        bench.restore_layout(env)
        env.current = layout.key
    ctx = Ctx(env, layout, "%s-sample" % layout.key)
    with open(os.path.join(ctx.bin, "crontab"), "w") as f:
        f.write('#!/bin/bash\n[ "$1" = "-l" ] && { echo "# m h dom mon dow command"; echo "30 3 * * * /usr/local/sbin/homelab-backup"; }\nexit 0\n')
    os.chmod(os.path.join(ctx.bin, "crontab"), 0o755)
    rc, out, secs, to = ctx.run("homelab-sample", [])
    bad = bad_text(out)
    sched = os.path.join(ctx.state, "schedule")
    got = open(sched).read().strip().split("|") if os.path.exists(sched) else []
    if got[:5] != ["30", "3", "*", "*", "*"]:
        bad.append("INV-truth-sample: the backup line of the crontab is 30 3 * * *, the saved schedule is %r" % got[:5])
    for name in ("temps", "apt", "schedule"):
        if not os.path.exists(os.path.join(ctx.state, name)):
            bad.append("INV-truth-sample: the file '%s' was not written" % name)
        elif name not in out:
            bad.append("INV-truth-text: the file '%s' was written but the screen does not list it" % name)
    if rc != 0:
        bad.append("INV-truth-rc: homelab-sample exited with %s" % rc)
    # what the status then says about the schedule
    ctx.write_state("last-run", "%s|OK|%s|1|1000\n" % (stamp_ago(0), env.backup))
    rc2, out2, _, _ = ctx.run("homelab", ["status"])
    row = status_rows(out2).get("Backup size", ("", ""))[1]
    if "next run 03:30" not in row:
        bad.append("INV-truth-text: the saved schedule is 03:30 daily but the status says %r" % row)
    outcome, flags, msg = others.judge(rc, out, to)
    flags = [f for f in flags if not f.startswith("exit 0 although")] + bad
    others.record(rec, cid, layout.key, "other:truth: sample: schedule and files", [], "", rc, out + "\n" + out2, secs, "BUG" if bad else outcome, flags, msg, "")
    return 1


def smoke_scenarios(env, rec, layout, log):
    """Commands that read a lot of the machine: they must not print shell errors, and must exit 0 when they only read."""
    done = 0
    for cmd, args, rc_ok in (("homelab-update", ["list"], (0,)), ("homelab-restore-configs", ["list"], (0, 1)),
                             ("homelab-restore-configs", ["check"], (0, 1)), ("homelab", ["docs"], (0,)), ("homelab", ["commands"], (0,)),
                             ("homelab", ["secrets"], (0, 1)), ("drives", ["list"], (0,)), ("drives", ["usage"], (0,)),
                             ("drives", ["status"], (0,)), ("homelab-check", ["version"], (0,))):
        cid = "truth|%s|smoke: %s %s" % (layout.key, cmd, " ".join(args))
        if cid in rec.done or not others.find(env, cmd):
            continue
        if env.current != layout.key or env.dirty:
            bench.restore_layout(env)
            env.current = layout.key
        ctx = Ctx(env, layout, "%s-smoke-%s-%s" % (layout.key, cmd, "-".join(args)))
        extra = {"HOMELAB_DOCS_DIR": os.path.dirname(os.path.dirname(others.find(env, "homelab")))} if cmd == "homelab" and args == ["docs"] else None
        rc, out, secs, to = ctx.run(cmd, args, extra, timeout=120)
        bad = bad_text(out)
        if rc not in rc_ok:
            bad.append("INV-truth-rc: '%s %s' exited with %s (expected %s)" % (cmd, " ".join(args), rc, " or ".join(map(str, rc_ok))))
        if to:
            bad.append("timeout")
        others.record(rec, cid, layout.key, "other:truth: smoke: %s %s" % (cmd, " ".join(args)), args, "", rc, out, secs, "BUG" if bad else "OK", bad, "", "")
        done += 1
    return done


# -------------------------------------------------------------------------------------------------------------- the contract
CLI = [
    # script, words that print the help, words that print the version, the unknown word
    ("homelab", ["help", "--help", "-h"], ["version", "--version"]),
    ("homelab-update", ["help", "--help", "-h"], ["version", "--version"]),
    ("homelab-restore-configs", ["help", "--help", "-h"], ["version", "--version"]),
    ("homelab-sample", ["help", "--help", "-h"], ["version", "--version"]),
    ("homelab-selftest", ["help", "--help", "-h"], ["version", "--version"]),
    ("drives", ["help", "--help", "-h"], ["version", "--version"]),
]

ALIASES = ("priority", "rebalance", "reorder", "recover", "menu")     # other names of a command that is listed (recover = hdd-recover)
BAD_TEXT = [r"unbound variable", r"syntax error", r"command not found", r"Traceback \(most recent", r"\$\{[A-Za-z_]", r"\(null\)",
            r"\bundefined\b", r"bad substitution", r"integer expression expected", r"\[: .*: (?:unary|binary) operator expected"]


def bad_text(out):
    return ["INV-truth-text: the output has '%s'" % re.search(rx, out).group(0) for rx in BAD_TEXT if re.search(rx, out)]


def script_version(path):
    for line in open(path, errors="replace"):
        m = re.match(r'^VERSION=["\']?([^"\'\s#]+)', line)
        if m:
            return m.group(1)
    return None


def dispatch_words(path):
    """The words the last top-level `case "$1"` of a script accepts."""
    text = open(path, errors="replace").read()
    heads = [m.start() for m in re.finditer(r'^\s*case "\$\{(?:1|ARGS\[0\]|cmd)[^}]*\}" in\s*$', text, re.M)]
    if not heads:
        return []
    block = text[heads[-1]:]
    end = re.search(r"^esac\b", block, re.M)
    block = block[:end.start()] if end else block
    words = set()
    for m in re.finditer(r"^\s{2,6}([\w|\-\"*/]+)\)", block, re.M):
        for w in m.group(1).split("|"):
            w = w.strip('"')
            if re.fullmatch(r"[a-z][a-z-]+", w):
                words.add(w)
    return sorted(words)


def run_contract(env, rec, log):
    ctx = Ctx(env, None, "contract")
    n = 0
    mapped = {}
    for script, helps, versions in CLI:
        path = others.find(env, script)
        if not path:
            continue
        ver = script_version(path)

        def go(args, script=script):
            return ctx.run(script, args, timeout=60)
        # version
        for w in versions:
            rc, out, secs, to = go([w])
            bad = bad_text(out)
            if rc != 0 or not re.fullmatch(r"%s %s\s*" % (re.escape(script), re.escape(ver or "?")), out):
                bad.append("INV-truth-version: '%s %s' printed %r (rc %s), the script says VERSION=%s" % (script, w, out.strip()[:60], rc, ver))
            n += 1
            others.record(rec, "truth|contract|%s|%s" % (script, w), "contract", "other:truth: %s %s" % (script, w), [w], "", rc, out, secs,
                          "OK" if not bad else "BUG", bad, "", "the version word")
        # help
        help_out = ""
        for w in helps:
            rc, out, secs, to = go([w])
            help_out = help_out or out
            bad = bad_text(out)
            if rc != 0:
                bad.append("INV-truth-rc: '%s %s' exited with %s" % (script, w, rc))
            if len(out.strip()) < 40:
                bad.append("INV-truth-text: '%s %s' printed almost nothing: %r" % (script, w, out.strip()))
            n += 1
            others.record(rec, "truth|contract|%s|%s" % (script, w), "contract", "other:truth: %s %s" % (script, w), [w], "", rc, out, secs,
                          "OK" if not bad else "BUG", bad, "", "the help word")
        # every accepted word is described in the help
        words = [w for w in dispatch_words(path) if w not in ("help", "version", "run") and not w.startswith("test-") and w not in ALIASES]
        miss = [w for w in words if not re.search(r"\b%s\b" % re.escape(w), help_out)]
        flags = ["unclear: the word '%s' works but the help of %s does not mention it" % (w, script) for w in miss]
        n += 1
        others.record(rec, "truth|contract|%s|words" % script, "contract", "other:truth: %s words in help" % script, [], "", 0,
                      "words: %s\nnot in help: %s\n" % (", ".join(words), ", ".join(miss) or "none"), 0, "OK" if not flags else "NOTE", flags, "",
                      "every word the script accepts is in its help")
        mapped[script] = words
        # an unknown word is refused: exit code 1, and the checks do not start
        if True:
            rc, out, secs, to = go(["bogus-word"])
            bad = bad_text(out)
            if rc == 0:
                bad.append("an unknown word was accepted with exit code 0")
            elif script == "homelab-selftest" and "Part 1" in out:
                bad.append("INV-truth-refuse: 'homelab-selftest bogus-word' ignored the word and started all the checks")
            elif not re.search(r"[Uu]nknown|[Uu]sage|no command called|[Tt]ry", out):
                bad.append("INV-truth-text: the unknown word was refused but the screen does not say what to do: %r" % out.strip()[:80])
            n += 1
            others.record(rec, "truth|contract|%s|bogus" % script, "contract", "other:truth: %s bogus-word" % script, ["bogus-word"], "", rc, out, secs,
                          "REFUSED" if not [b for b in bad if b.startswith(("INV", "an unknown"))] else "BUG", bad, "", "an unknown word")
    # help for a topic that does not exist
    rc, out, secs, to = ctx.run("drives", ["help", "bogus-word"], timeout=60)
    bad = [] if rc != 0 else ["exit 0 although 'drives help bogus-word' says there is no such command"]
    others.record(rec, "truth|contract|drives|help-bogus", "contract", "other:truth: drives help bogus-word", ["help", "bogus-word"], "", rc, out, secs,
                  "REFUSED" if rc else "NOTE", bad, "", "help about a command that does not exist")
    n += 1
    # the commands named in the lists exist
    n += check_named_commands(ctx, env, rec, mapped)
    log("  truth contract %3d checks" % n)
    return n


def check_named_commands(ctx, env, rec, mapped):
    """Every `sudo drives WORD` (or other command) in `homelab commands` and the login suggestions must be real."""
    rc, out, secs, to = ctx.run("homelab", ["commands"], timeout=60)
    n = 0
    bad = bad_text(out)
    named = re.findall(r"^\s+(?:sudo )?((?:drives|homelab[\w-]*|hdd-recover)(?: [a-z-]+)?)\s*$", out, re.M)
    for item in sorted(set(named)):
        parts = item.split()
        cmd = parts[0]
        if not others.find(env, cmd):
            bad.append("INV-truth-command: the list names '%s' but there is no such command" % cmd)
            continue
        if len(parts) > 1:
            known = set(mapped.get(cmd, []))
            if cmd == "drives":
                r2 = ctx.run("drives", ["help", parts[1]], timeout=60)
                if "There is no command called" in r2[1]:
                    bad.append("INV-truth-command: the list names 'sudo drives %s' but drives does not know that word" % parts[1])
            elif known and parts[1] not in known:
                bad.append("INV-truth-command: the list names '%s' but the script does not accept '%s'" % (item, parts[1]))
    others.record(rec, "truth|contract|commands-list", "contract", "other:truth: every command in 'homelab commands' exists", ["commands"], "", rc, out, secs,
                  "OK" if not bad else "BUG", bad, "", "%d commands named" % len(set(named)))
    n += 1
    # the opposite: commands of `drives` that the list never mentions (a hint, not an error)
    dr = [w for w in mapped.get("drives", []) if w not in ("menu", "status") and w not in ALIASES]
    unlisted = [w for w in dr if not re.search(r"drives %s\b" % re.escape(w), out)]
    flags = ["unclear: 'homelab commands' does not list sudo drives %s" % w for w in unlisted[:20]]
    others.record(rec, "truth|contract|commands-missing", "contract", "other:truth: drives commands missing from 'homelab commands'", [], "", 0,
                  "not listed: %s\n" % (", ".join(unlisted) or "none"), 0, "OK" if not flags else "NOTE", flags, "", "a hint for the list of commands")
    return n + 1


# ------------------------------------------------------------------------------------------------------------------ the pass
def layout_truth(env, rec, layout, log):
    """Every scenario on one layout."""
    done = 0
    for name, setup, args, extra, check in scenarios():
        cid = "truth|%s|%s" % (layout.key, name)
        if cid in rec.done:
            continue
        if env.current != layout.key or env.dirty:
            bench.restore_layout(env)
            env.current = layout.key
        ctx = Ctx(env, layout, "%s-%s" % (layout.key, name))
        # a state folder that exists (the last-run file is looked for in it) unless the scenario points somewhere else
        setup(ctx)
        rc, out, secs, to = ctx.run("homelab", args, extra)
        problems = check(ctx, rc, out) + bad_text(out)
        outcome, flags, msg = others.judge(rc, out, to)
        flags = [f for f in flags if not f.startswith("exit 0 although")] + problems
        if problems:
            outcome = "BUG"
        others.record(rec, cid, layout.key, "other:truth: " + name, args, "", rc, out, secs, outcome, flags, msg, "")
        done += 1
    done += backup_scenarios(env, rec, layout, log)
    done += sampler_scenarios(env, rec, layout, log)
    done += smoke_scenarios(env, rec, layout, log)
    bench.teardown(env)
    log("  truth %-26s %3d scenarios" % (layout.key, done))
    return done
