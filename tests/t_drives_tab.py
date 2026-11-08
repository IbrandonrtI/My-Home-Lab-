#!/usr/bin/env python3
"""Test of the Drives tab's server side in scripts/homelab-panel: the panel asks the drives tool (here a FAKE one that only records what it is asked)
for exactly the allowed words, refuses everything else before it asks, and turns the answers into plain sentences.
Run: python3 tests/t_drives_tab.py   (last line is OK or FAIL)"""
import json
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import t_panel  # noqa: E402  (the same panel harness)

check = t_panel.check
FAKE = os.path.join(HERE, "fake_drives.py")
ALLOWED = {"status", "health", "check", "actions", "remount", "rename", "sleep", "wake", "add", "wipe", "disconnect", "move"}


def main():
    tmp = tempfile.mkdtemp(prefix="hldrives-")
    log = os.path.join(tmp, "drives.log")
    p = t_panel.Panel(tmp, {"HLP_DRIVES": FAKE, "FAKE_DRIVES_LOG": log})
    try:
        p.set_password()
        p.start()

        def calls():
            if not os.path.exists(log):
                return []
            with open(log) as f:
                return [json.loads(x) for x in f if x.strip()]

        st, js, _, _ = p.req("GET", "/api/drives")
        check("drives: the list needs a login", st == 401, st)
        st, js, _, _ = p.req("POST", "/api/drives/remount", {})
        check("drives: an action needs a login", st == 401, st)
        check("drives: nothing was asked of the drives tool without a login", calls() == [], calls())
        p.login()
        st, js, _, _ = p.req("POST", "/api/drives/remount", {}, headers={"X-Panel": ""})
        check("drives: an action without the panel header is refused", st in (400, 401, 403), st)
        st, js, _, _ = p.req("POST", "/api/drives/remount", {}, headers={"Origin": "https://evil.example.com"})
        check("drives: an action from another website is refused", st == 403, st)
        check("drives: ... and nothing was asked of the drives tool", calls() == [], calls())

        # ---- look
        st, js, _, _ = p.req("GET", "/api/drives")
        check("drives: the list has pools, drives, the last backup and what can be renamed or put to sleep",
              st == 200 and js["status"]["pools"][0]["role"] == "main" and js["status"]["last_backup"] == "Never" and js["actions"]["power"][0]["id"] == "sdb"
              and js["actions"]["rename"][1]["custom"] is True, (st, js))
        check("drives: the list asked only for status and actions", calls() == [["panel", "status"], ["panel", "actions"]], calls())
        st, js, _, _ = p.req("GET", "/api/drives/health")
        check("drives: health still answers when a drive is failing (the tool exits 1)", st == 200 and js["ok"] is False and js["drives"][0]["health"] == "FAILED", (st, js))
        st, js, _, _ = p.req("GET", "/api/drives/check")
        check("drives: the quick check answers with its findings", st == 200 and js["drives"][1]["findings"][0]["level"] == "problem", (st, js))

        # ---- rename: exact words, checked before the tool is asked
        st, js, _, _ = p.req("POST", "/api/drives/rename", {"id": "MAIN1", "name": "Photos  Drive"})
        check("drives: rename passes the drive and the name (spaces tidied)", st == 200 and "now called Photos Drive" in js["message"] and calls()[-1] == ["panel", "rename", "MAIN1", "Photos Drive"], (st, js, calls()[-1:]))
        st, js, _, _ = p.req("POST", "/api/drives/rename", {"id": "BACKUP1", "name": "auto"})
        check("drives: auto goes back to the automatic name", st == 200 and calls()[-1] == ["panel", "rename", "BACKUP1", "auto"], (st, calls()[-1:]))
        n1 = len(calls())
        bad = [({"id": "MAIN1", "name": "a/b"}, "slash"), ({"id": "MAIN1", "name": 'a"b'}, "quote"), ({"id": "MAIN1", "name": "a_b"}, "underscore"), ({"id": "MAIN1", "name": "-x"}, "leading dash"),
               ({"id": "MAIN1", "name": "x "}, "trailing space is tidied, but a trailing dot is not"),
               ({"id": "MAIN1", "name": "a" * 41}, "41 letters"), ({"id": "MAIN1", "name": ""}, "empty"), ({"id": "MAIN1", "name": 5}, "a number"),
               ({"id": "MAIN1"}, "no name"), ({"id": "../etc", "name": "ok"}, "path as id"), ({"id": "MAIN1 x", "name": "ok"}, "space in id"), ({"id": "--dry-run", "name": "ok"}, "option as id"),
               ({"id": "", "name": "ok"}, "empty id"), ({"id": ["MAIN1"], "name": "ok"}, "list as id"), ({"name": "ok"}, "no id"), ({"id": "MAIN1", "name": "a."}, "trailing dot")]
        for body, what in bad:
            st, js, _, _ = p.req("POST", "/api/drives/rename", body)
            if what.startswith("trailing space"):
                check("drives: rename tidies a trailing space", st == 200 and calls()[-1] == ["panel", "rename", "MAIN1", "x"], (st, js))
                n1 = len(calls())
                continue
            check("drives: rename refuses %s before asking the tool" % what, st == 400 and "error" in js and len(calls()) == n1, (st, js))
        # ---- sleep, wake
        st, js, _, _ = p.req("POST", "/api/drives/sleep", {"id": "sdb"})
        check("drives: sleep passes the drive", st == 200 and calls()[-1] == ["panel", "sleep", "sdb"], (st, calls()[-1:]))
        st, js, _, _ = p.req("POST", "/api/drives/wake", {"id": "sdb"})
        check("drives: wake passes the drive", st == 200 and calls()[-1] == ["panel", "wake", "sdb"], (st, calls()[-1:]))
        n2 = len(calls())
        st, js, _, _ = p.req("POST", "/api/drives/sleep", {"id": "sdb; reboot"})
        check("drives: a drive id with shell characters is refused before asking", st == 400 and len(calls()) == n2, (st, js))
        for word in ("eject", "release", "connect", "replace", "restore", "preset", "format"):
            st, js, _, _ = p.req("POST", "/api/drives/" + word, {"id": "sdb"})
            check("drives: '%s' is not there either" % word, st == 404 and len(calls()) == n2, st)
        check("drives: only allowed words were ever asked of the tool", all(c[0] == "panel" and c[1] in ALLOWED for c in calls()), [c for c in calls() if c[1] not in ALLOWED])


        # ---- changes that run in the background: add, wipe, disconnect, move
        def wait_job(limit=15):
            for _ in range(int(limit * 10)):
                st, j, _, _ = p.req("GET", "/api/drives/job")
                if st == 200 and not j["running"]:
                    return j
                time.sleep(0.1)
            return j

        st, js, _, _ = p.req("GET", "/api/drives/job")
        check("drives: no job yet", st == 200 and js["running"] is False and js["id"] == 0, (st, js))
        n3 = len(calls())
        bad_jobs = [("add", {"id": "sdc", "role": "middle", "mode": "erase", "typed": []}, "a bad role"), ("add", {"id": "sdc", "role": "main", "mode": "both", "typed": []}, "a bad mode"),
                    ("add", {"id": "sdc", "role": "main", "mode": "erase", "typed": ["yes"]}, "a typed word that is not allowed"), ("add", {"id": "sdc", "role": "main", "mode": "erase", "typed": ["/dev/sdc;reboot"]}, "a typed word with a shell character"),
                    ("add", {"id": "sdc", "role": "main", "mode": "erase", "typed": ["ERASE"] * 5}, "too many typed words"), ("add", {"id": "sdc", "role": "main", "mode": "erase", "typed": "ERASE"}, "typed that is not a list"),
                    ("add", {"id": "../x", "role": "main", "mode": "erase", "typed": []}, "a path as the drive"), ("add", {"role": "main", "mode": "erase", "typed": []}, "no drive"),
                    ("wipe", {"id": "sdc", "mode": "shred", "typed": []}, "a bad wipe mode"), ("disconnect", {"id": "MAIN1", "copy": "maybe", "typed": []}, "a bad copy choice"),
                    ("move", {"id": "MAIN1", "keep": "both", "copy": "yes", "typed": []}, "a bad keep choice"), ("move", {"id": "MAIN1", "keep": "keep", "typed": []}, "a missing copy choice")]
        for word, body, what in bad_jobs:
            st, js, _, _ = p.req("POST", "/api/drives/" + word, body)
            check("drives: %s refuses %s before asking the tool" % (word, what), st in (400, 404) and "error" in js and len(calls()) == n3, (st, js))
        st, js, _, _ = p.req("POST", "/api/drives/add", {"id": "sdc", "role": "main", "mode": "erase", "typed": ["/dev/sdc", "ERASE"]})
        check("drives: add starts a job", st == 200 and js["ok"] is True and js["job"] == 1, (st, js))
        j = wait_job()
        check("drives: the job finishes with the tool's words and exit code 0", j["rc"] == 0 and "added" in j["message"] and j["action"] == "add", j)
        check("drives: add passes exactly the words", calls()[-1] == ["panel", "add", "sdc", "main", "erase", "/dev/sdc", "ERASE"], calls()[-1:])
        for body, words in (({"id": "sdc", "mode": "format", "typed": ["/dev/sdc", "ERASE"]}, ["panel", "wipe", "sdc", "format", "/dev/sdc", "ERASE"]),):
            p.req("POST", "/api/drives/wipe", body); wait_job()
            check("drives: wipe passes exactly the words", calls()[-1] == words, calls()[-1:])
        p.req("POST", "/api/drives/disconnect", {"id": "MAIN1", "copy": "no", "typed": ["CONTINUE"]}); wait_job()
        check("drives: disconnect passes exactly the words", calls()[-1] == ["panel", "disconnect", "MAIN1", "no", "CONTINUE"], calls()[-1:])
        p.req("POST", "/api/drives/move", {"id": "MAIN1", "keep": "keep", "copy": "yes", "typed": ["KEEP"]}); wait_job()
        check("drives: move passes exactly the words", calls()[-1] == ["panel", "move", "MAIN1", "keep", "yes", "KEEP"], calls()[-1:])
        st, js, _, _ = p.req("POST", "/api/drives/move", {"id": "MAIN1", "keep": "erase", "copy": "no", "typed": ["/dev/sdb", "ERASE", "CONTINUE"]}); wait_job()
        check("drives: move (erase, no copy) passes all its typed words", calls()[-1] == ["panel", "move", "MAIN1", "erase", "no", "/dev/sdb", "ERASE", "CONTINUE"], calls()[-1:])
        p.stop()
        p.env["FAKE_DRIVES_MODE"] = "jobfail"
        p.start(); p.login()
        p.req("POST", "/api/drives/wipe", {"id": "sdc", "mode": "empty", "typed": []})
        j = wait_job()
        check("drives: a refused change ends with rc 1 and the tool's sentence", j["rc"] == 1 and "Cancelled. Nothing was changed." in j["message"], j)
        p.stop()
        p.env["FAKE_DRIVES_MODE"] = "jobslow"
        p.start(); p.login()
        st, js, _, _ = p.req("POST", "/api/drives/move", {"id": "MAIN1", "keep": "keep", "copy": "yes", "typed": ["KEEP"]})
        time.sleep(1.0)
        st, j, _, _ = p.req("GET", "/api/drives/job")
        check("drives: a running job shows its progress lines", st == 200 and j["running"] is True and any("Copying files" in x for x in j["lines"]), (st, j))
        st, js, _, _ = p.req("GET", "/api/drives")
        check("drives: the list waits while a job runs (try again)", st == 409, (st, js))
        st, js, _, _ = p.req("POST", "/api/drives/wipe", {"id": "sdc", "mode": "empty", "typed": []})
        check("drives: a second change cannot start while one runs", st == 409 and "Another drive command is running" in js["error"], (st, js))
        st, js, _, _ = p.req("GET", "/api/state")
        check("drives: the rest of the panel works while a job runs", st == 200, st)
        j = wait_job()
        check("drives: the slow job finished well", j["rc"] == 0, j)
        p.stop()
        p.env["FAKE_DRIVES_MODE"] = "ok"
        p.start(); p.login()
        p.stop()
        p.env["FAKE_DRIVES_MODE"] = "ok"

        p.start(); p.login()
        # ---- remount, and what goes wrong
        st, js, _, _ = p.req("POST", "/api/drives/remount", {})
        check("drives: remount asks for exactly that", st == 200 and "Recovered." in js["message"] and calls()[-1] == ["panel", "remount"], (st, js))
        p.stop()
        p.env["FAKE_DRIVES_MODE"] = "busy"
        p.start(); p.login()
        st, js, _, _ = p.req("POST", "/api/drives/remount", {})
        check("drives: a refused remount shows the tool's own sentence", st == 409 and "backup is running right now" in js["error"], (st, js))
        p.stop()
        p.env["FAKE_DRIVES_MODE"] = "nosudo"
        p.start(); p.login()
        st, js, _, _ = p.req("GET", "/api/drives")
        check("drives: when sudo says no, the answer tells what to run", st == 502 and "sudo homelab-setup upgrade" in js["error"], (st, js))
        st, js, _, _ = p.req("POST", "/api/drives/sleep", {"id": "sdb"})
        check("drives: ... also for an action", st in (409, 502) and "sudo homelab-setup upgrade" in js["error"], (st, js))
        p.stop()
        p.env["FAKE_DRIVES_MODE"] = "bad"
        p.start(); p.login()
        st, js, _, _ = p.req("GET", "/api/drives")
        check("drives: an answer that is not JSON gives a plain error, not a crash", st == 502 and "error" in js, (st, js))
        p.stop()
        p.env["HLP_DRIVES"] = os.path.join(tmp, "no-such-tool")
        p.start(); p.login()
        st, js, _, _ = p.req("GET", "/api/drives")
        check("drives: when the drives tool is not installed the answer says so", st == 502 and "not installed" in js["error"], (st, js))
        p.stop()

        # ---- a long remount does not block the rest of the panel
        p.env["HLP_DRIVES"] = FAKE
        p.env["FAKE_DRIVES_MODE"] = "slow"
        p.start(); p.login()
        out = {}
        t = threading.Thread(target=lambda: out.update(zip(("st", "js"), p.req("POST", "/api/drives/remount", {})[:2])))
        t.start()
        time.sleep(0.6)
        st, js, _, _ = p.req("GET", "/api/state")
        check("drives: the rest of the panel works while a remount runs", st == 200 and "look" in js, st)
        st, js, _, _ = p.req("GET", "/api/drives")
        check("drives: a second drive command at the same time waits its turn (try again)", st == 409 and "Another drive command is running" in js["error"], (st, js))
        t.join(10)
        check("drives: the slow remount finished well", out.get("st") == 200, out)
    finally:
        p.stop()
    ok = all(t_panel.results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
