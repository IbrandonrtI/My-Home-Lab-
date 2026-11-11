#!/usr/bin/env python3
"""Test of scripts/homelab-backup-tasks (the backup task engine): schedules, checking what is sent, versions with hard links, keep rules,
dry run, restore, another computer (SSH, with a stand-in that runs the command here), the cloud (a stand-in rclone over a folder), the
nightly task (a stand-in for the older tool), the lock, and the panel's words.
Real rsync runs. Run: python3 tests/t_backup_tasks.py   (last line is OK or FAIL)"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "..", "scripts", "homelab-backup-tasks")
results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   " + str(extra)))


T = tempfile.mkdtemp(prefix="hlb-test-")
SRC, DST, CLOUD, REM = (os.path.join(T, x) for x in ("src", "dst", "cloud", "remote"))
for d in (SRC, DST, CLOUD, REM):
    os.makedirs(d)
ENV = dict(os.environ, HLB_CONF=os.path.join(T, "tasks.json"), HLB_STATE=os.path.join(T, "state"), HLB_LOCK=os.path.join(T, "lock"),
           HLB_LOGFILE=os.path.join(T, "log"), HLB_KEY=os.path.join(T, "key"), HLB_ROOTS=T, HLB_ALLOW_ROOTFS="1",
           HLB_SSH=os.path.join(HERE, "fake_ssh.sh"), HLB_RCLONE=os.path.join(HERE, "fake_rclone.py"), FAKE_RCLONE_DIR=CLOUD,
           HLB_LEGACY=os.path.join(T, "legacy"), HLB_LEGACY_CONF=os.path.join(T, "legacy.conf"), HLB_RCLONE_CONF=os.path.join(T, "rclone.conf"),
           HLB_MOUNTS_FILE=os.path.join(T, "mounts"), HLB_CRONTAB="true", FAKE_SSH_LOG=os.path.join(T, "ssh.log"), HLB_NOW="2026-03-10 02:00:00")
open(ENV["HLB_KEY"], "w").write("dummy\n")
legacy = os.path.join(T, "legacy")
with open(legacy, "w") as f:
    f.write("#!/bin/bash\necho legacy ran\nexit ${LEGACY_RC:-0}\n")
os.chmod(legacy, 0o755)
with open(ENV["HLB_LEGACY_CONF"], "w") as f:
    f.write('SRC="/mnt/storage"\nDEST_POOL="%s"\nRETENTION_DAYS=14\n' % os.path.join(T, "pool"))


def eng(*args, now=None, stdin=None, env=None):
    e = dict(ENV, **(env or {}))
    if now:
        e["HLB_NOW"] = now
    p = subprocess.run([sys.executable, ENGINE] + list(args), capture_output=True, text=True, env=e, input=stdin, timeout=120)
    return p.returncode, p.stdout + p.stderr


def panel(*args, now=None, stdin=None, env=None):
    rc, out = eng("panel", *args, now=now, stdin=stdin, env=env)
    try:
        return rc, json.loads(out.strip().split("\n")[-1])
    except ValueError:
        return rc, {"raw": out}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def save(**kw):
    t = {"name": "Docs", "source": SRC, "dest": {"type": "local", "path": DST}, "schedule": {"kind": "daily", "time": "02:00"},
         "keep": {"hourly": 0, "daily": 3, "weekly": 0, "monthly": 0, "yearly": 0}, "exclude": []}
    t.update(kw)
    return panel("save", stdin=json.dumps(t))


loader = importlib.machinery.SourceFileLoader("hlb", ENGINE)
spec = importlib.util.spec_from_loader("hlb", loader)
hlb = importlib.util.module_from_spec(spec)
loader.exec_module(hlb)
D = datetime.datetime


# ---------------------------------------------------------------- schedules and keep rules (pure functions)
ref = D(2026, 3, 10, 12, 0)            # a Tuesday
check("daily: last scheduled is today at the time", hlb.last_scheduled({"kind": "daily", "time": "02:00"}, ref) == D(2026, 3, 10, 2, 0))
check("daily: before the time, last scheduled is yesterday", hlb.last_scheduled({"kind": "daily", "time": "23:00"}, ref) == D(2026, 3, 9, 23, 0))
check("daily: next is tomorrow", hlb.next_scheduled({"kind": "daily", "time": "02:00"}, ref) == D(2026, 3, 11, 2, 0))
check("hourly: last", hlb.last_scheduled({"kind": "hourly", "minute": 30}, ref) == D(2026, 3, 10, 11, 30))
check("hourly: next", hlb.next_scheduled({"kind": "hourly", "minute": 30}, ref) == D(2026, 3, 10, 12, 30))
w = {"kind": "weekly", "dow": 6, "time": "03:00"}      # Sunday
check("weekly: last is the Sunday before", hlb.last_scheduled(w, ref) == D(2026, 3, 8, 3, 0))
check("weekly: next is the next Sunday", hlb.next_scheduled(w, ref) == D(2026, 3, 15, 3, 0))
m = {"kind": "monthly", "dom": 15, "time": "04:00"}
check("monthly: last is the 15th of last month", hlb.last_scheduled(m, ref) == D(2026, 2, 15, 4, 0))
check("monthly: next is this month's 15th", hlb.next_scheduled(m, ref) == D(2026, 3, 15, 4, 0))
check("monthly across a year end", hlb.next_scheduled(m, D(2026, 12, 20, 0, 0)) == D(2027, 1, 15, 4, 0))
check("monthly, early January looks back to December", hlb.last_scheduled(m, D(2026, 1, 5, 0, 0)) == D(2025, 12, 15, 4, 0))
check("schedule text", hlb.describe_schedule(w) == "Every Sunday at 03:00")

stamps = ["2026-03-%02d_020000" % d for d in range(1, 11)]
check("keep daily 3 keeps the 3 newest days", sorted(hlb.keep_set(stamps, {"daily": 3})) == stamps[-3:])
two = ["2026-03-10_010000", "2026-03-10_020000", "2026-03-09_020000"]
check("keep daily keeps one version per day (the newest of the day)", sorted(hlb.keep_set(two, {"daily": 5})) == ["2026-03-09_020000", "2026-03-10_020000"])
check("the newest version is always kept", hlb.keep_set(stamps, {"yearly": 0}) == {stamps[-1]})
mixed = ["2026-01-05_020000", "2026-02-05_020000", "2026-03-05_020000", "2026-03-09_020000", "2026-03-10_020000"]
check("keep monthly 2 + daily 1", sorted(hlb.keep_set(mixed, {"monthly": 2, "daily": 1})) == ["2026-02-05_020000", "2026-03-10_020000"])

# ---------------------------------------------------------------- checking what is sent
write(os.path.join(SRC, "a.txt"), "alpha\n")
write(os.path.join(SRC, "sub", "b.txt"), "bravo\n")
rc, r = save(source="/")
check("source '/' refused", rc and "cannot be backed up" in r.get("error", ""), r)
rc, r = save(source="/proc/1")
check("source under /proc refused", rc and "cannot be backed up" in r.get("error", ""), r)
rc, r = save(source=os.path.join(T, "nope"))
check("missing source refused", rc and "does not exist" in r.get("error", ""), r)
rc, r = save(source="relative/path")
check("relative source refused", rc and "full folder path" in r.get("error", ""), r)
rc, r = save(source=SRC + "/../src")
check("source with .. refused", rc, r)
rc, r = save(dest={"type": "local", "path": os.path.join(SRC, "inside")})
check("destination inside the source refused", rc and "inside each other" in r.get("error", ""), r)
rc, r = save(dest={"type": "local", "path": "/etc/backup"})
check("destination outside the drive folders refused", rc and "connected drive" in r.get("error", ""), r)
rc, r = save(name="")
check("empty name refused", rc, r)
rc, r = save(schedule={"kind": "daily", "time": "25:00"})
check("bad time refused", rc, r)
rc, r = save(schedule={"kind": "monthly", "dom": 31, "time": "02:00"})
check("day 31 refused", rc, r)
rc, r = save(keep={"daily": 0})
check("keeping nothing refused", rc and "at least one" in r.get("error", ""), r)
rc, r = save(keep={"daily": 5000})
check("silly keep number refused", rc, r)
rc, r = save(dest={"type": "ssh", "host": "bad host", "path": "/x"})
check("bad ssh host refused", rc and "user@name" in r.get("error", ""), r)
rc, r = save(dest={"type": "ssh", "host": "u@h", "path": "/"})
check("ssh top folder refused", rc, r)
rc, r = save(dest={"type": "cloud", "remote": "bad name!", "path": ""}, keep={"days": 30})
check("bad cloud name refused", rc, r)
rc, r = save(dest={"type": "cloud", "remote": "gd", "path": "../x"}, keep={"days": 30})
check("cloud path with .. refused", rc, r)
rc, r = save(exclude=["x"] * 60)
check("too many skip patterns refused", rc, r)
rc, r = save(dest={"type": "wat"})
check("unknown destination type refused", rc, r)

# ---------------------------------------------------------------- first task: a folder on a drive
rc, r = save()
check("a good task is saved", rc == 0 and r.get("ok"), r)
tid = r.get("id")
rc, st = panel("state")
names = [t["name"] for t in st.get("tasks", [])]
check("the nightly task is seeded first", names[:1] == ["Nightly: Main to Backup"] and "Docs" in names, names)
nt = st["tasks"][0]
check("nightly defaults: 06:00 daily", nt["schedule"] == {"kind": "daily", "time": "06:00"} and nt["id"] == "nightly", nt)
check("state lists drives, ssh key state and cloud availability", set(st) >= {"drives", "ssh", "cloud", "roots", "running"}, list(st))

rc, out = eng("run", tid, "--dry-run")
check("dry run before any copy says the first run copies everything", rc == 0 and "first run would copy 2 files" in out, out)
check("dry run changed nothing", not os.path.exists(os.path.join(DST, tid)), os.listdir(DST))

rc, out = eng("run", tid, now="2026-03-10 02:00:05")
check("first run works", rc == 0 and "OK" in out, out)
v1 = os.path.join(DST, tid, "2026-03-10_020005")
check("version folder holds the files", read(os.path.join(v1, "a.txt")) == "alpha\n" and read(os.path.join(v1, "sub", "b.txt")) == "bravo\n")
check("latest link points to it", os.path.islink(os.path.join(DST, tid, "latest")) and os.readlink(os.path.join(DST, tid, "latest")) == "2026-03-10_020005")
check("no .partial left", not [n for n in os.listdir(os.path.join(DST, tid)) if n.endswith(".partial")])

write(os.path.join(SRC, "a.txt"), "alpha changed\n")
write(os.path.join(SRC, "c.txt"), "charlie\n")
rc, out = eng("run", tid, "--dry-run", now="2026-03-11 02:00:00")
check("dry run counts only the changes", rc == 0 and "2 files" in out, out)
check("dry run created no version", len(os.listdir(os.path.join(DST, tid))) == 2, os.listdir(os.path.join(DST, tid)))
rc, out = eng("run", tid, now="2026-03-11 02:00:05")
v2 = os.path.join(DST, tid, "2026-03-11_020005")
check("second run works", rc == 0, out)
check("changed file differs between versions", read(os.path.join(v1, "a.txt")) == "alpha\n" and read(os.path.join(v2, "a.txt")) == "alpha changed\n")
check("unchanged file is a hard link (no extra space)", os.stat(os.path.join(v1, "sub", "b.txt")).st_ino == os.stat(os.path.join(v2, "sub", "b.txt")).st_ino)

os.remove(os.path.join(SRC, "c.txt"))
rc, out = eng("run", tid, now="2026-03-12 02:00:05")
v3 = os.path.join(DST, tid, "2026-03-12_020005")
check("a deleted file is gone from the new version but kept in the old", not os.path.exists(os.path.join(v3, "c.txt")) and read(os.path.join(v2, "c.txt")) == "charlie\n")

rc, out = eng("run", tid, now="2026-03-13 02:00:05")
vs = sorted(n for n in os.listdir(os.path.join(DST, tid)) if n[0].isdigit())
check("keep daily 3 removed the oldest version", vs == ["2026-03-11_020005", "2026-03-12_020005", "2026-03-13_020005"], vs)
check("latest moved on", os.readlink(os.path.join(DST, tid, "latest")) == "2026-03-13_020005")
rc, st = panel("state", now="2026-03-13 03:00:00")
t = [x for x in st["tasks"] if x["id"] == tid][0]
check("state shows the last run", t["last"]["result"] == "OK" and t["last"]["size_bytes"] and len(t["runs"]) == 4, t["last"])
check("state shows the next run", t["next_run"] == "2026-03-14 02:00", t["next_run"])

# ---------------------------------------------------------------- versions, browsing, restore
rc, r = panel("versions", tid)
check("versions newest first", [v["name"] for v in r["versions"]] == ["2026-03-13_020005", "2026-03-12_020005", "2026-03-11_020005"], r)
rc, r = panel("browse", tid, "2026-03-11_020005")
check("browse the top of a version (folders first)", [e["name"] for e in r["entries"]] == ["sub", "a.txt", "c.txt"], r)
rc, r = panel("browse", tid, "2026-03-11_020005", "sub")
check("browse a sub folder", [e["name"] for e in r["entries"]] == ["b.txt"], r)
rc, r = panel("browse", tid, "2026-03-11_020005", "../x")
check("browse refuses ..", rc and "error" in r, r)
rc, r = panel("browse", tid, "../../etc")
check("browse refuses a made-up version", rc and "error" in r, r)

rc, r = panel("restore", tid, "2026-03-11_020005", "c.txt", "folder", now="2026-03-14 09:00:00")
check("restore a file to the safe folder", rc == 0 and read(os.path.join(SRC, "_restored", "2026-03-14_090000", "c.txt")) == "charlie\n", r)
check("the safe-folder restore did not touch the original files", read(os.path.join(SRC, "a.txt")) == "alpha changed\n")
rc, r = panel("restore", tid, "2026-03-11_020005", "sub", "folder", now="2026-03-14 09:00:01")
check("restore a folder to the safe folder", read(os.path.join(SRC, "_restored", "2026-03-14_090001", "sub", "b.txt")) == "bravo\n", r)
write(os.path.join(SRC, "a.txt"), "ruined\n")
rc, r = panel("restore", tid, "2026-03-13_020005", "a.txt", "original", now="2026-03-14 09:00:02")
check("restore a file to its original place", rc == 0 and read(os.path.join(SRC, "a.txt")) == "alpha changed\n", r)
check("what it replaced was kept", read(os.path.join(SRC, "_restored", "2026-03-14_090002-replaced", "a.txt")) == "ruined\n")
rc, r = panel("restore", tid, "2026-03-13_020005", ".", "folder", now="2026-03-14 09:00:03")
check("restore a whole version to the safe folder", read(os.path.join(SRC, "_restored", "2026-03-14_090003", "sub", "b.txt")) == "bravo\n", r)
rc, r = panel("restore", tid, "2026-03-13_020005", "a.txt", "somewhere")
check("restore refuses an unknown target", rc and "error" in r, r)
shutil.rmtree(os.path.join(SRC, "_restored"))

# ---------------------------------------------------------------- safety refusals and the lock
empty = os.path.join(T, "empty")
os.makedirs(empty)
rc, r = save(name="Empty", source=empty, dest={"type": "local", "path": os.path.join(DST, "e")})
rc2, out = eng("run", r["id"], now="2026-03-13 04:00:00")
check("an empty source is refused (nothing is emptied)", rc2 == 1 and "looks empty" in out, out)
rc, st = panel("state")
e = [x for x in st["tasks"] if x["id"] == r["id"]][0]
check("the failure is recorded", e["last"]["result"] == "FAILED" and "looks empty" in e["last"]["message"], e["last"])

import fcntl  # noqa: E402
fd = os.open(ENV["HLB_LOCK"], os.O_WRONLY | os.O_CREAT, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX)
rc, out = eng("run", tid, now="2026-03-14 02:00:05")
check("a run refuses while another backup holds the lock", rc == 1 and "running" in out, out)
rc, r = panel("restore", tid, "2026-03-13_020005", "a.txt", "folder")
check("restore refuses while a backup runs", rc and "running" in r.get("error", ""), r)
rc, r = panel("delete", tid, "keep")
check("delete refuses while a backup runs", rc and "running" in r.get("error", ""), r)
rc, st = panel("state")
check("state says a backup is running", st["running"] is True)
os.close(fd)

# ---------------------------------------------------------------- when tasks are due
tasks = hlb.load_tasks()
nowdt = D(2026, 3, 14, 3, 0)
os.environ["HLB_STATE"] = ENV["HLB_STATE"]
hlb.STATE = ENV["HLB_STATE"]
hlb.CONF = ENV["HLB_CONF"]
due = [t["id"] for t in hlb.due_tasks(hlb.load_tasks(), nowdt)]
check("a daily task whose time has passed since its last start is due", tid in due, due)
check("a task that already ran today is not due", tid not in [t["id"] for t in hlb.due_tasks(hlb.load_tasks(), D(2026, 3, 13, 3, 0))])
check("the nightly task is due once 06:00 has passed", "nightly" in [t["id"] for t in hlb.due_tasks(hlb.load_tasks(), D(2026, 3, 14, 6, 1))])
check("the nightly task is not due before 06:00 (new task starts from its creation)", "nightly" not in [t["id"] for t in hlb.due_tasks(hlb.load_tasks(), D(2026, 3, 10, 5, 0))])
panel("toggle", tid, "off")
check("a task that is off is never due", tid not in [t["id"] for t in hlb.due_tasks(hlb.load_tasks(), nowdt)])
panel("toggle", tid, "on")
rc, out = eng("due", now="2026-03-14 02:10:00")
check("`due` runs what is due", "Docs: OK" in out, out)
rc, out = eng("due", now="2026-03-14 02:15:00")
check("`due` runs nothing twice", "Docs" not in out, out)

# ---------------------------------------------------------------- editing, skip list, deleting
rc, r = save(id=tid, name="Docs renamed", exclude=["*.tmp", "cache/"])
check("a task can be edited", rc == 0 and r["id"] == tid, r)
write(os.path.join(SRC, "junk.tmp"), "x")
write(os.path.join(SRC, "cache", "z"), "x")
eng("run", tid, now="2026-03-15 02:00:05")
v = os.path.join(DST, tid, "2026-03-15_020005")
check("skipped patterns are not copied", os.path.exists(os.path.join(v, "a.txt")) and not os.path.exists(os.path.join(v, "junk.tmp")) and not os.path.exists(os.path.join(v, "cache")))
rc, r = panel("delete", tid, "keep")
check("delete (keep the copies) removes only the task", rc == 0 and os.path.isdir(os.path.join(DST, tid)) and tid not in open(ENV["HLB_CONF"]).read())
rc, r = save()
tid2 = r["id"]
eng("run", tid2, now="2026-03-16 02:00:05")
check("a new task made its own folder", os.path.isdir(os.path.join(DST, tid2)))
rc, r = panel("delete", tid2, "erase")
check("delete with erase removes the copies", rc == 0 and not os.path.exists(os.path.join(DST, tid2)))
rc, r = panel("delete", "nightly", "keep")
check("the nightly task cannot be deleted", rc and "cannot be deleted" in r.get("error", ""), r)
rc, r = panel("delete", "nosuch", "keep")
check("delete of an unknown task refused", rc and "error" in r, r)

# ---------------------------------------------------------------- another computer over SSH (stand-in)
rc, r = save(name="To PC", dest={"type": "ssh", "host": "backup@pc.example.ts.net", "path": REM + "/bk"})
sid = r.get("id")
check("an ssh task is saved", rc == 0, r)
rc, out = eng("run", sid, "--dry-run")
check("ssh dry run before any copy", rc == 0 and "first run would copy" in out, out)
rc, out = eng("run", sid, now="2026-03-17 02:00:05")
sv1 = os.path.join(REM, "bk", sid, "2026-03-17_020005")
check("ssh run copies the files", rc == 0 and read(os.path.join(sv1, "a.txt")) == "alpha changed\n", out)
check("ssh latest link", os.path.islink(os.path.join(REM, "bk", sid, "latest")))
write(os.path.join(SRC, "d.txt"), "delta\n")
rc, out = eng("run", sid, now="2026-03-18 02:00:05")
sv2 = os.path.join(REM, "bk", sid, "2026-03-18_020005")
check("ssh second run hard-links unchanged files", rc == 0 and os.stat(os.path.join(sv1, "a.txt")).st_ino == os.stat(os.path.join(sv2, "a.txt")).st_ino, out)
rc, r = panel("versions", sid)
check("ssh versions listed", [v["name"] for v in r["versions"]] == ["2026-03-18_020005", "2026-03-17_020005"], r)
rc, r = panel("browse", sid, "2026-03-18_020005")
check("ssh browse", sorted(e["name"] for e in r["entries"]) == ["a.txt", "cache", "d.txt", "sub"] or "d.txt" in [e["name"] for e in r["entries"]], r)
rc, r = panel("restore", sid, "2026-03-18_020005", "d.txt", "folder", now="2026-03-19 09:00:00")
check("ssh restore", read(os.path.join(SRC, "_restored", "2026-03-19_090000", "d.txt")) == "delta\n", r)
shutil.rmtree(os.path.join(SRC, "_restored"))
write(os.path.join(SRC, "with space.txt"), "spaced\n")
eng("run", sid, now="2026-03-19 02:00:05")
rc, r = panel("restore", sid, "2026-03-19_020005", "with space.txt", "folder", now="2026-03-19 09:00:01")
check("ssh restore of a name with a space", read(os.path.join(SRC, "_restored", "2026-03-19_090001", "with space.txt")) == "spaced\n", r)
shutil.rmtree(os.path.join(SRC, "_restored"))
os.remove(ENV["HLB_KEY"])
rc, out = eng("run", sid, now="2026-03-20 02:00:05")
check("ssh run without a key says what to do", rc == 1 and "SSH key" in out, out)
open(ENV["HLB_KEY"], "w").write("dummy\n")
rc, r = panel("sshtest", "bad host")
check("sshtest refuses a bad host", rc and "error" in r, r)
rc, r = panel("sshtest", "backup@pc.example.ts.net", env={"HLB_SSH": os.path.join(HERE, "fake_ssh.sh")})
check("sshtest passes when rsync answers", rc == 0 and r.get("ok") and "rsync" in r.get("message", ""), r)
if shutil.which("ssh-keygen"):
    rc, r = panel("sshkey", env={"HLB_KEY": os.path.join(T, "newkey")})
    check("sshkey makes a key and returns the public half", rc == 0 and r.get("key", "").startswith("ssh-ed25519 "), r)
    rc, r2 = panel("sshkey", env={"HLB_KEY": os.path.join(T, "newkey")})
    check("sshkey returns the same key the second time", r2.get("key") == r.get("key"))
else:
    print("SKIP  sshkey (ssh-keygen is not installed here)")
    rc, r = panel("sshkey", env={"HLB_KEY": os.path.join(T, "newkey")})
    check("sshkey says plainly when it cannot make a key", rc and "Could not make the SSH key" in r.get("error", ""), r)

# ---------------------------------------------------------------- the cloud (stand-in rclone)
rc, r = save(name="To cloud", dest={"type": "cloud", "remote": "gd", "path": "homelab"}, keep={"days": 10})
cid = r.get("id")
check("a cloud task is saved", rc == 0, r)
rc, r = save(name="To missing cloud", dest={"type": "cloud", "remote": "nope", "path": ""}, keep={"days": 10})
rc2, out = eng("run", r["id"], now="2026-03-20 02:00:00")
check("a cloud account rclone does not know is refused", rc2 == 1 and "not set up" in out, out)
rc, out = eng("run", cid, now="2026-03-20 02:00:05")
check("cloud run copies the files", rc == 0 and read(os.path.join(CLOUD, "gd", "homelab", cid, "current", "a.txt")) == "alpha changed\n", out)
write(os.path.join(SRC, "a.txt"), "alpha v3\n")
rc, out = eng("run", cid, "--dry-run", now="2026-03-21 02:00:00")
check("cloud dry run counts the change", rc == 0 and "1 changes" in out, out)
rc, out = eng("run", cid, now="2026-03-21 02:00:05")
check("cloud run updates the latest copy", read(os.path.join(CLOUD, "gd", "homelab", cid, "current", "a.txt")) == "alpha v3\n", out)
check("the replaced file went to the changes folder", read(os.path.join(CLOUD, "gd", "homelab", cid, "changes", "2026-03-21_020005", "a.txt")) == "alpha changed\n")
rc, r = panel("versions", cid)
check("cloud versions: latest copy plus change sets", [v["name"] for v in r["versions"]] == ["current", "2026-03-21_020005"], r)
rc, r = panel("browse", cid, "current")
check("cloud browse", "a.txt" in [e["name"] for e in r["entries"]], r)
rc, r = panel("restore", cid, "2026-03-21_020005", "a.txt", "folder", now="2026-03-22 09:00:00")
check("cloud restore of an older copy", read(os.path.join(SRC, "_restored", "2026-03-22_090000", "a.txt")) == "alpha changed\n", r)
rc, r = panel("restore", cid, "current", "sub", "folder", now="2026-03-22 09:00:01")
check("cloud restore of a folder", read(os.path.join(SRC, "_restored", "2026-03-22_090001", "sub", "b.txt")) == "bravo\n", r)
shutil.rmtree(os.path.join(SRC, "_restored"))
write(os.path.join(SRC, "a.txt"), "alpha v4\n")
eng("run", cid, now="2026-04-05 02:00:05")
ch = sorted(os.listdir(os.path.join(CLOUD, "gd", "homelab", cid, "changes")))
check("old change sets are removed after the keep days", ch == ["2026-04-05_020005"], ch)
rc, r = panel("state", env={"FAKE_RCLONE_REMOTES": "gd,b2"})
check("state lists cloud accounts", r["cloud"]["installed"] and r["cloud"]["remotes"] == ["gd", "b2"], r["cloud"])
rc, r = panel("cloud-add", stdin=json.dumps({"type": "b2", "name": "bb", "key_id": "abc123", "key": "SECRETKEY123"}))
conf = read(ENV["HLB_RCLONE_CONF"]) or ""
check("cloud-add writes a B2 account (root-only file)", rc == 0 and "[bb]" in conf and "type = b2" in conf and oct(os.stat(ENV["HLB_RCLONE_CONF"]).st_mode)[-3:] == "600", r)
rc, r = panel("cloud-add", stdin=json.dumps({"type": "b2", "name": "gd", "key_id": "abc123", "key": "SECRETKEY123"}))
check("cloud-add refuses a name that exists", rc and "already exists" in r.get("error", ""), r)
rc, r = panel("cloud-add", stdin=json.dumps({"type": "b2", "name": "x", "key_id": "ab", "key": "has space"}))
check("cloud-add refuses odd keys", rc and "error" in r, r)
rc, r = panel("cloud-add", stdin=json.dumps({"type": "drive", "name": "x", "key_id": "abcd", "key": "abcdef"}))
check("cloud-add points Google Drive to the terminal", rc and "rclone config" in r.get("error", ""), r)
rc, st = panel("state", env={"HLB_RCLONE": "/nonexistent/rclone"})
check("state tolerates rclone being absent", st["cloud"]["installed"] is False, st["cloud"])

# ---------------------------------------------------------------- the nightly task (stand-in for the older tool)
os.remove(ENV["HLB_CONF"])
rc, st = panel("state")
n = st["tasks"][0]
check("nightly reads the old settings file", n["source"] == "/mnt/storage" and n["dest"]["path"] == os.path.join(T, "pool") and n["keep"]["days"] == 14, n)
shutil.rmtree(ENV["HLB_STATE"], ignore_errors=True)
os.remove(ENV["HLB_CONF"])
rc, st = panel("state", env={"HLB_CRONTAB": "echo '30 5 * * * /usr/local/sbin/homelab-backup'"})
check("nightly keeps the time the older cron job had", st["tasks"][0]["schedule"] == {"kind": "daily", "time": "05:30"}, st["tasks"][0])
os.remove(ENV["HLB_CONF"])
rc, st = panel("state", env={"HLB_CRONTAB": "echo '*/5 * * * * /usr/local/sbin/homelab-backup-tasks due'"})
check("the scheduler's own cron line is not mistaken for the older job", st["tasks"][0]["schedule"] == {"kind": "daily", "time": "06:00"}, st["tasks"][0])
os.remove(ENV["HLB_CONF"])
panel("state")
rc, out = eng("run", "nightly", now="2026-03-23 06:00:00")
check("nightly runs the older tool", rc == 0 and "nightly backup finished" in out, out)
rc, out = eng("run", "nightly", env={"LEGACY_RC": "3"}, now="2026-03-24 06:00:00")
check("nightly reports a failed run", rc == 1 and "FAILED" in out, out)
rc, out = eng("run", "nightly", "--dry-run")
check("nightly says a dry run is not available", rc == 0 and "not available" in out, out)
rc, r = save(id="nightly", name="Nightly renamed", schedule={"kind": "daily", "time": "05:30"}, enabled=False, source="/etc", dest={"type": "local", "path": "/mnt/x"})
rc, st = panel("state")
n = st["tasks"][0]
check("only the name, switch and schedule of nightly can change", n["name"] == "Nightly renamed" and n["schedule"]["time"] == "05:30" and not n["enabled"] and n["source"] == "/mnt/storage", n)
pool = os.path.join(T, "pool")
write(os.path.join(pool, "main", "a.txt"), "now\n")
write(os.path.join(pool, "_deleted", "2026-03-20", "main", "old.txt"), "old\n")
write(os.path.join(pool, "_deleted", "2026-03-22", "main", "older.txt"), "older\n")
rc, r = panel("versions", "nightly")
check("nightly versions: current plus per-day deleted sets", [v["name"] for v in r["versions"]] == ["current", "2026-03-22", "2026-03-20"], r)
rc, r = panel("browse", "nightly", "2026-03-20")
check("nightly browse of a day", [e["name"] for e in r["entries"]] == ["old.txt"], r)

# ---------------------------------------------------------------- the engine's own small things
rc, out = eng("version")
check("version", rc == 0 and out.startswith("homelab-backup-tasks "), out)
rc, out = eng("help")
check("help prints the usage", rc == 0 and "Usage" in out and "due" in out, out)
rc, out = eng("frobnicate")
check("unknown command refused", rc == 2, out)
rc, out = eng("run")
check("run without an id refused", rc == 2, out)
rc, out = eng("list")
check("list prints tasks", rc == 0 and "Nightly renamed" in out, out)
rc, out = eng("panel", "bogus")
check("unknown panel word refused", rc == 1 and "error" in out, out)
rc, r = panel("save", stdin="not json")
check("save refuses non-JSON", rc and "error" in r, r)
write(ENV["HLB_MOUNTS_FILE"], "/dev/sdb1 %s ext4 rw 0 0\n/dev/sdc1 /mnt/other ext4 rw 0 0\ntmpfs %s tmpfs rw 0 0\n" % (T, T + "/t"))
rc, st = panel("state")
check("state lists only real drive mounts under the allowed roots", [d["path"] for d in st["drives"]] == [T], st["drives"])

shutil.rmtree(T, ignore_errors=True)
print()
print("OK" if all(results) else "FAIL (%d of %d failed)" % (results.count(False), len(results)))
sys.exit(0 if all(results) else 1)
