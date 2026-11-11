#!/usr/bin/env python3
"""Test of the Backups section's server side in scripts/homelab-panel: the panel asks the backup tool (the real one, on temporary folders) for exactly
the allowed words, refuses everything else before it asks, runs a backup, a preview and a restore in the background, and turns problems into
plain sentences.
Run: python3 tests/t_backup_tab.py   (last line is OK or FAIL)"""
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import t_panel  # noqa: E402  (the same panel harness)

check = t_panel.check
ENGINE = os.path.join(HERE, "..", "scripts", "homelab-backup-tasks")


def wait_job(p, limit=60):
    end = time.time() + limit
    js = {}
    while time.time() < end:
        js = p.req("GET", "/api/backup/job")[1]
        if js and not js["running"]:
            return js
        time.sleep(0.2)
    return js


def main():
    tmp = tempfile.mkdtemp(prefix="hlbtab-")
    src, dst = os.path.join(tmp, "src"), os.path.join(tmp, "dst")
    os.makedirs(os.path.join(src, "sub"))
    os.makedirs(dst)
    with open(os.path.join(src, "a.txt"), "w") as f:
        f.write("alpha\n")
    with open(os.path.join(src, "sub", "b.txt"), "w") as f:
        f.write("bravo\n")
    legacy = os.path.join(tmp, "legacy")
    with open(legacy, "w") as f:
        f.write('#!/bin/bash\n( flock -n 9 || exit 1; sleep 2; echo legacy done ) 9>"$HLB_LOCK"\n')      # (the real nightly tool holds the same lock)
    os.chmod(legacy, 0o755)
    env = {"HLP_BACKUP": "%s %s panel" % (sys.executable, ENGINE), "HLB_CONF": os.path.join(tmp, "tasks.json"), "HLB_STATE": os.path.join(tmp, "bstate"),
           "HLB_LOCK": os.path.join(tmp, "lock"), "HLB_LOGFILE": os.path.join(tmp, "log"), "HLB_ROOTS": tmp, "HLB_ALLOW_ROOTFS": "1",
           "HLB_LEGACY": legacy, "HLB_LEGACY_CONF": os.path.join(tmp, "none.conf"), "HLB_KEY": os.path.join(tmp, "key"),
           "HLB_MOUNTS_FILE": os.path.join(tmp, "mounts"), "HLB_RCLONE": os.path.join(HERE, "fake_rclone.py"), "FAKE_RCLONE_DIR": os.path.join(tmp, "cloud")}
    p = t_panel.Panel(tmp, env)
    try:
        p.set_password()
        p.start()
        st, js, _, _ = p.req("GET", "/api/backup")
        check("backup: the list needs a login", st == 401, st)
        st, js, _, _ = p.req("POST", "/api/backup/run", {"id": "nightly"})
        check("backup: a run needs a login", st == 401, st)
        p.login()
        st, js, _, _ = p.req("POST", "/api/backup/save", {}, headers={"Origin": "https://evil.example.com"})
        check("backup: a save from another website is refused", st == 403, st)
        st, js, _, _ = p.req("POST", "/api/backup/run", {"id": "nightly"}, headers={"X-Panel": ""})
        check("backup: a run without the panel header is refused", st in (400, 401, 403), st)
        check("backup: nothing was created without a login", not os.path.exists(env["HLB_CONF"]))

        st, js, _, _ = p.req("GET", "/api/backup")
        check("backup: the list has the nightly task first, drives, ssh and cloud", st == 200 and js["tasks"][0]["id"] == "nightly" and set(js) >= {"drives", "ssh", "cloud", "running"}, (st, js))

        good = {"name": "Documents", "source": src, "dest": {"type": "local", "path": dst}, "schedule": {"kind": "daily", "time": "02:00"},
                "keep": {"daily": 3, "weekly": 0, "monthly": 0, "yearly": 0, "hourly": 0}, "exclude": [], "evil": "ignored"}
        st, js, _, _ = p.req("POST", "/api/backup/save", dict(good, name=""))
        check("backup: a bad task is refused with the tool's own sentence", st == 409 and "name" in js["error"], (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/save", dict(good, id="../x"))
        check("backup: a made-up id is refused by the panel", st == 400 and "Choose a backup task" in js["error"], (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/save", good)
        tid = (js or {}).get("id")
        check("backup: a good task is saved", st == 200 and js["ok"] and tid, (st, js))
        check("backup: unknown fields are not passed on", "evil" not in open(env["HLB_CONF"]).read())

        # ---- a run, a preview, versions, browsing, a restore (in the background)
        st, js, _, _ = p.req("POST", "/api/backup/dry", {"id": tid})
        check("backup: a preview starts", st == 200 and js["ok"], (st, js))
        job = wait_job(p)
        check("backup: a preview ends well and says what it would do", job["rc"] == 0 and "first run would copy 2 files" in job["message"] and job["action"] == "dry", job)
        st, js, _, _ = p.req("POST", "/api/backup/run", {"id": tid})
        job = wait_job(p)
        check("backup: a run ends well", st == 200 and job["rc"] == 0 and job["pct"] == 100 and "OK" in job["message"], (st, job))
        st, js, _, _ = p.req("GET", "/api/backup")
        t = [x for x in js["tasks"] if x["id"] == tid][0]
        check("backup: the list shows the result", t["last"]["result"] == "OK" and t["running"] is False, t)
        st, js, _, _ = p.req("GET", "/api/backup/versions?id=" + tid)
        ver = js["versions"][0]["name"] if st == 200 else ""
        check("backup: versions are listed", st == 200 and len(js["versions"]) == 1, (st, js))
        st, js, _, _ = p.req("GET", "/api/backup/browse?id=%s&v=%s" % (tid, ver))
        check("backup: the top of a version is browsable", st == 200 and [e["name"] for e in js["entries"]] == ["sub", "a.txt"], (st, js))
        st, js, _, _ = p.req("GET", "/api/backup/browse?id=%s&v=%s&rel=sub" % (tid, ver))
        check("backup: a sub folder is browsable", st == 200 and [e["name"] for e in js["entries"]] == ["b.txt"], (st, js))
        st, js, _, _ = p.req("GET", "/api/backup/browse?id=%s&v=%s&rel=../.." % (tid, ver))
        check("backup: browsing with .. is refused", st == 400, (st, js))
        st, js, _, _ = p.req("GET", "/api/backup/browse?id=%s&v=../../etc" % tid)
        check("backup: a made-up version is refused", st == 400, (st, js))
        st, js, _, _ = p.req("GET", "/api/backup/versions?id=Bad_Id")
        check("backup: a made-up id is refused on a look", st == 400, (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/restore", {"id": tid, "version": ver, "rel": "a.txt", "target": "elsewhere"})
        check("backup: a restore with an unknown target is refused", st == 400, (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/restore", {"id": tid, "version": ver, "rel": "../a.txt", "target": "folder"})
        check("backup: a restore with .. is refused", st == 400, (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/restore", {"id": tid, "version": ver, "rel": "a.txt", "target": "folder"})
        job = wait_job(p)
        done = [os.path.join(r, "a.txt") for r, _, fs in os.walk(os.path.join(src, "_restored")) if "a.txt" in fs]
        check("backup: a restore to a safe folder works", st == 200 and job["rc"] == 0 and len(done) == 1 and "Restored" in job["message"], (job, done))
        with open(os.path.join(src, "a.txt"), "w") as f:
            f.write("ruined\n")
        st, js, _, _ = p.req("POST", "/api/backup/restore", {"id": tid, "version": ver, "rel": "a.txt", "target": "original"})
        job = wait_job(p)
        check("backup: a restore to the original place brings the file back", job["rc"] == 0 and open(os.path.join(src, "a.txt")).read() == "alpha\n", job)

        # ---- one job at a time
        st, js, _, _ = p.req("POST", "/api/backup/run", {"id": "nightly"})
        check("backup: the nightly run starts", st == 200, (st, js))
        time.sleep(0.5)
        st, js, _, _ = p.req("POST", "/api/backup/run", {"id": tid})
        check("backup: a second job is turned away while one runs", st == 409 and "running already" in js["error"], (st, js))
        st, js, _, _ = p.req("GET", "/api/backup")
        check("backup: the list says a backup is running", st == 200 and js["running"] is True, js.get("running"))
        job = wait_job(p)
        check("backup: the nightly run ends", job["rc"] == 0 and "finished" in job["message"], job)

        # ---- quick things
        st, js, _, _ = p.req("POST", "/api/backup/toggle", {"id": tid, "enabled": False})
        st2, js2, _, _ = p.req("GET", "/api/backup")
        check("backup: a task can be switched off", st == 200 and [x for x in js2["tasks"] if x["id"] == tid][0]["enabled"] is False, (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/sshtest", {"host": "bad host"})
        check("backup: a bad ssh host is refused by the panel", st == 400, (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/cloud-add", {"type": "drive", "name": "x", "key_id": "abcd", "key": "abcdef"})
        check("backup: Google Drive is pointed to the terminal", st == 409 and "rclone config" in js["error"], (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/delete", {"id": tid, "data": "maybe"})
        check("backup: delete needs keep or erase", st == 400, (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/delete", {"id": "nightly", "data": "keep"})
        check("backup: the nightly task cannot be deleted", st == 409 and "cannot be deleted" in js["error"], (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/delete", {"id": tid, "data": "erase"})
        check("backup: a task is deleted with its copies", st == 200 and not os.path.exists(os.path.join(dst, tid)), (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/nosuch", {})
        check("backup: an unknown address is refused", st == 404, st)
        p.stop()

        # ---- the tool missing, or sudo saying no
        p.env["HLP_BACKUP"] = os.path.join(tmp, "no-such-tool")
        p.start(); p.login()
        st, js, _, _ = p.req("GET", "/api/backup")
        check("backup: a missing tool is explained", st == 502 and "not installed" in js["error"], (st, js))
        st, js, _, _ = p.req("POST", "/api/backup/dry", {"id": "nightly"})
        job = wait_job(p)
        check("backup: a missing tool is explained for a background job too", job["rc"] == 127 and "not installed" in job["message"], job)
        p.stop()
        deny = os.path.join(tmp, "deny")
        with open(deny, "w") as f:
            f.write("#!/bin/bash\necho 'sudo: a password is required' >&2\nexit 1\n")
        os.chmod(deny, 0o755)
        p.env["HLP_BACKUP"] = deny
        p.start(); p.login()
        st, js, _, _ = p.req("GET", "/api/backup")
        check("backup: a sudo refusal is explained", st == 502 and "not allowed" in js["error"], (st, js))
    finally:
        p.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    ok = all(t_panel.results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
