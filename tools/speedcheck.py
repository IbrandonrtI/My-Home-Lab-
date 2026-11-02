#!/usr/bin/env python3
"""speedcheck - measure how long the lab's look-only commands take, how many programs each one starts, and whether any of them
wakes a sleeping drive. It changes nothing (homelab-sample writes its normal readings, nothing else is written).

    sudo python3 tools/speedcheck.py                 about 2 minutes; prints a table and saves homelab-speedcheck-DATE.txt in your home folder
    sudo python3 tools/speedcheck.py --runs 5        more runs per command (steadier numbers)
    sudo python3 tools/speedcheck.py --no-strace     skip counting programs (strace is optional:  sudo apt install -y strace)

Send the saved file when you want a speed question looked at. It holds command names, times and counts, no file contents.
It stops without running when a backup is running (it would slow the backup down).
"""
import argparse
import collections
import fcntl
import glob
import os
import pwd
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

BACKUP_LOCK = "/var/lock/homelab-backup.lock"
FAST_ENOUGH = 1.5   # seconds: a command faster than this is not reported for starting many programs
SLOW_SECONDS = 5.0           # a look-only command slower than this is worth a look
MANY_PROGRAMS = 300          # more programs than this started by one command
REPEATED = 40                # one program started this often by one command: a scan that is repeated

# label, command, runs as the normal user (True) or as root (False)
COMMANDS = [
    ("homelab (login screen)", ["homelab"], True),
    ("homelab status", ["homelab", "status"], True),
    ("homelab commands", ["homelab", "commands"], True),
    ("drives status", ["drives", "status"], False),
    ("drives list", ["drives", "list"], False),
    ("drives health", ["drives", "health"], False),
    ("drives usage", ["drives", "usage"], False),
    ("drives preset (the list)", ["drives", "preset"], False),
    ("drives wizard --dry-run", ["drives", "wizard", "--dry-run"], False),
    ("homelab-setup (checklist)", ["homelab-setup"], False),
    ("homelab-update list", ["homelab-update", "list"], True),
    ("homelab-sample", ["homelab-sample"], False),
]


def median(values):
    return statistics.median(values) if values else 0.0


def count_programs(strace_text):
    """From the lines of `strace -f -e trace=execve`: {program name: times it was started}. Failed starts are not counted."""
    count = collections.Counter()
    for line in strace_text.splitlines():
        if "execve(" not in line or line.rstrip().endswith("ENOENT (No such file or directory)") or "= -1 " in line:
            continue
        start = line.find('execve("')
        if start < 0:
            continue
        path = line[start + 8:line.find('"', start + 8)]
        count[os.path.basename(path)] += 1
    return count


def hints(label, seconds, procs, programs):
    """Plain sentences about what looks wasteful in one command."""
    out = []
    if seconds > SLOW_SECONDS:
        out.append("%s takes %.1f s; a look-only command should answer in a few seconds" % (label, seconds))
    if seconds < FAST_ENOUGH:   # an answer in about a second is fine: starting many small programs is not worth changing then
        return out
    if procs > MANY_PROGRAMS:
        out.append("%s starts %d programs; most of the time is probably spent starting them" % (label, procs))
    for prog, n in programs.most_common(5):
        if n >= REPEATED and prog not in ("bash", "sh"):
            out.append("%s starts '%s' %d times; a scan that could be done once and reused" % (label, prog, n))
    return out


def backup_running():
    if not os.path.exists(BACKUP_LOCK):
        return False
    try:
        fd = os.open(BACKUP_LOCK, os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except OSError:
        return True
    finally:
        os.close(fd)


def sleeping_drives():
    """Spinning drives that are in standby right now (hdparm -C): their names."""
    if not shutil.which("hdparm"):
        return None
    out = []
    for blk in sorted(glob.glob("/sys/block/sd*")):
        try:
            if open(os.path.join(blk, "queue/rotational")).read().strip() != "1":
                continue
        except OSError:
            continue
        dev = "/dev/" + os.path.basename(blk)
        r = subprocess.run(["hdparm", "-C", dev], capture_output=True, text=True)
        if "standby" in r.stdout or "sleeping" in r.stdout:
            out.append(dev)
    return out


def wrap(cmd, as_user, user):
    if as_user:
        return ["sudo", "-u", user, "-H", "env", "TERM=dumb"] + cmd
    return ["env", "TERM=dumb"] + cmd


def timed_run(argv, home):
    t0 = time.perf_counter()
    c0 = os.times()
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=240, stdin=subprocess.DEVNULL, cwd=home)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        rc = 124
    c1 = os.times()
    return time.perf_counter() - t0, (c1.children_user - c0.children_user) + (c1.children_system - c0.children_system), rc


def main():
    ap = argparse.ArgumentParser(description="time the look-only commands of the lab")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--no-strace", action="store_true")
    args = ap.parse_args()
    if os.geteuid() != 0:
        print("Run it with sudo:  sudo python3 tools/speedcheck.py")
        return 1
    if backup_running():
        print("A backup is running right now, so nothing was measured (it would slow the backup down). Run it again after the backup.")
        return 1
    user = os.environ.get("SUDO_USER") or "root"
    try:
        home = pwd.getpwnam(user).pw_dir
    except KeyError:
        home = "/root"
    use_strace = not args.no_strace and shutil.which("strace") is not None
    if not args.no_strace and not use_strace:
        print("strace is not installed, so the programs are not counted (sudo apt install -y strace).")
    asleep_before = sleeping_drives()
    woke = {}
    rows, notes = [], []
    for label, cmd, as_user in COMMANDS:
        if shutil.which(cmd[0]) is None:
            notes.append("%s: not installed, skipped" % label)
            continue
        argv = wrap(cmd, as_user, user)
        times, cpus, rc = [], [], 0
        for _ in range(max(1, args.runs)):
            t, c, rc = timed_run(argv, home)
            times.append(t)
            cpus.append(c)
        procs, programs = 0, collections.Counter()
        if use_strace:
            fd, path = tempfile.mkstemp(prefix="hlprof-")
            os.close(fd)
            subprocess.run(["strace", "-f", "-qq", "-e", "trace=execve", "-o", path] + argv, capture_output=True, stdin=subprocess.DEVNULL, cwd=home, timeout=600)
            programs = count_programs(open(path, errors="replace").read())
            os.remove(path)
            procs = sum(programs.values())
        if asleep_before:
            now = sleeping_drives() or []
            for dev in [d for d in asleep_before if d not in now and d not in woke]:
                woke[dev] = label
        rows.append({"label": label, "sec": median(times), "worst": max(times), "cpu": median(cpus), "procs": procs, "programs": programs, "rc": rc})
    rows.sort(key=lambda r: -r["sec"])
    lines = ["homelab speedcheck   %s   %d run(s) per command" % (time.strftime("%F %T"), args.runs), ""]
    lines.append("%-30s %8s %8s %8s %8s  %s" % ("command", "median s", "worst s", "cpu s", "programs", "most started"))
    for r in rows:
        top = ", ".join("%s x%d" % (p, n) for p, n in r["programs"].most_common(4))
        lines.append("%-30s %8.2f %8.2f %8.2f %8s  %s%s" % (r["label"], r["sec"], r["worst"], r["cpu"], r["procs"] if use_strace else "-", top,
                                                            "" if r["rc"] in (0, 1) else "   (exit %s)" % r["rc"]))
    lines.append("")
    found = []
    for r in rows:
        found += hints(r["label"], r["sec"], r["procs"], r["programs"])
    if asleep_before is None:
        lines.append("Sleeping drives: hdparm is not installed, so this was not checked.")
    elif not asleep_before:
        lines.append("Sleeping drives: none were asleep at the start, so waking could not be tested. Run again when the drives have been idle (for example in the morning).")
    elif woke:
        for dev, label in woke.items():
            found.append("%s was asleep and woke up while '%s' ran; look-only commands should leave it asleep" % (dev, label))
    else:
        lines.append("Sleeping drives: %s stayed asleep during every command. Good." % ", ".join(asleep_before))
    lines.append("What looks wasteful:" if found else "Nothing looks wasteful.")
    lines += ["  - " + f for f in found]
    lines += ["  (" + n + ")" for n in notes]
    text = "\n".join(lines)
    print(text)
    path = os.path.join(home, "homelab-speedcheck-%s.txt" % time.strftime("%Y%m%d-%H%M"))
    try:
        with open(path, "w") as fh:
            fh.write(text + "\n")
        os.chmod(path, 0o600)
        if home != "/root":
            shutil.chown(path, user)
        print("\nSaved in " + path)
    except OSError as e:
        print("\nCould not save the file (%s)." % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
