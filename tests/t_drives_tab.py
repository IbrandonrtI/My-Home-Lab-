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
                    ("add", {"id": "sdc", "role": "main", "mode": "erase", "typed": ["ERASE"] * 21}, "too many typed words"), ("add", {"id": "sdc", "role": "main", "mode": "erase", "typed": "ERASE"}, "typed that is not a list"),
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
        # ---- several drives at once, a choice for each drive, and the word NOW
        bad_many = [({"ids": ["sdc", "sdc"], "role": "main", "mode": "erase", "typed": []}, "a drive named twice"), ({"ids": [], "role": "main", "mode": "erase", "typed": []}, "no drive"),
                    ({"ids": ["a%d" % i for i in range(9)], "role": "main", "mode": "erase", "typed": []}, "nine drives"), ({"ids": ["sdc", "sdd:keep"], "role": "main", "typed": []}, "a choice for only one of two drives"),
                    ({"ids": ["sdc;reboot", "sdd"], "role": "main", "mode": "erase", "typed": []}, "a shell character in an id"), ({"ids": "sdc,sdd", "role": "main", "mode": "erase", "typed": []}, "ids that are not a list"),
                    ({"ids": ["sdc:both"], "role": "main", "typed": []}, "a bad per-drive choice")]
        n4 = len(calls())
        for body, what in bad_many:
            st, js, _, _ = p.req("POST", "/api/drives/add", body)
            check("drives: add refuses %s before asking the tool" % what, st in (400, 404) and "error" in js and len(calls()) == n4, (st, js))
        p.req("POST", "/api/drives/add", {"ids": ["sdc", "sdd"], "role": "main", "mode": "erase", "typed": ["/dev/sdc", "/dev/sdd", "ERASE"]}); wait_job()
        check("drives: two drives with one choice go as one list", calls()[-1] == ["panel", "add", "sdc,sdd", "main", "erase", "/dev/sdc", "/dev/sdd", "ERASE"], calls()[-1:])
        p.req("POST", "/api/drives/add", {"ids": ["sdc:keep", "sdd:erase"], "role": "backup", "typed": ["/dev/sdd", "ERASE"]}); wait_job()
        check("drives: a choice for each drive goes as 'each'", calls()[-1] == ["panel", "add", "sdc:keep,sdd:erase", "backup", "each", "/dev/sdd", "ERASE"], calls()[-1:])
        p.req("POST", "/api/drives/move", {"ids": ["MAIN1", "MAIN2"], "keep": "keep", "copy": "yes", "typed": ["KEEP", "NOW"]}); wait_job()
        check("drives: move of two drives, with the word NOW, passes exactly the words", calls()[-1] == ["panel", "move", "MAIN1,MAIN2", "keep", "yes", "KEEP", "NOW"], calls()[-1:])
        p.req("POST", "/api/drives/disconnect", {"ids": ["MAIN1", "MAIN2"], "copy": "yes", "typed": []}); wait_job()
        check("drives: disconnect of two drives goes as one list", calls()[-1] == ["panel", "disconnect", "MAIN1,MAIN2", "yes"], calls()[-1:])
        p.stop()
        p.env["FAKE_DRIVES_MODE"] = "jobfail"
        p.start(); p.login()
        p.req("POST", "/api/drives/wipe", {"id": "sdc", "mode": "empty", "typed": []})
        j = wait_job()
        check("drives: a refused change ends with rc 1 and the tool's sentence", j["rc"] == 1 and "Cancelled. Nothing was changed." in j["message"], j)
        p.stop()
        p.env["FAKE_DRIVES_MODE"] = "jobbusy"
        p.start(); p.login()
        p.req("POST", "/api/drives/move", {"ids": ["MAIN1"], "keep": "keep", "copy": "yes", "typed": ["KEEP"]})
        j = wait_job()
        check("drives: a change refused as busy ends with the tool's sentence (the page offers Go Ahead Anyway)", j["rc"] == 1 and "Not a good moment" in j["message"], j)
        p.req("POST", "/api/drives/move", {"ids": ["MAIN1"], "keep": "keep", "copy": "yes", "typed": ["KEEP", "NOW"]})
        j = wait_job()
        check("drives: with the word NOW it goes on", j["rc"] == 0, j)
        p.stop()
        p.env["FAKE_DRIVES_MODE"] = "jobslow"
        p.start(); p.login()
        st, js, _, _ = p.req("POST", "/api/drives/move", {"id": "MAIN1", "keep": "keep", "copy": "yes", "typed": ["KEEP"]})
        time.sleep(1.0)
        st, j, _, _ = p.req("GET", "/api/drives/job")
        check("drives: a running job shows its progress lines", st == 200 and j["running"] is True and any("Copying files" in x for x in j["lines"]), (st, j))
        check("drives: a running job shows the bar of its drive (and the progress lines stay out of the text)", j["items"] == ["MAIN1"] and j["progress"].get("MAIN1", {}).get("pct", 0) >= 22 and "Copying files" in j["progress"]["MAIN1"]["text"] and not any(x.startswith("PROGRESS") for x in j["lines"]), (st, j))
        st, js, _, _ = p.req("GET", "/api/drives")
        check("drives: the list waits while a job runs (the page follows the progress instead)", st == 409 and "drive change is running" in js["error"], (st, js))
        st, js, _, _ = p.req("POST", "/api/drives/wipe", {"id": "sdc", "mode": "empty", "typed": []})
        check("drives: a second change cannot start while one runs", st == 409 and "Another drive command is running" in js["error"], (st, js))
        st, js, _, _ = p.req("GET", "/api/state")
        check("drives: the rest of the panel works while a job runs", st == 200, st)
        j = wait_job()
        check("drives: the slow job finished well", j["rc"] == 0, j)
        # ---- the Abort button
        st, js, _, _ = p.req("POST", "/api/drives/abort", {})
        check("abort: with no change running it says so (nothing is sent to the tool)", st == 409 and "No drive change is running" in js["error"] and ["panel", "abort"] not in calls(), (st, js))
        p.req("POST", "/api/drives/move", {"ids": ["MAIN1", "MAIN2"], "keep": "keep", "copy": "yes", "typed": ["KEEP"]})
        time.sleep(1.0)
        st, js, _, _ = p.req("POST", "/api/drives/abort", {})
        check("abort: Stop is passed on to the tool while the change runs (the drive gate does not hold it back)", st == 200 and "Stop requested" in js["message"] and calls()[-1] == ["panel", "abort"], (st, js, calls()[-1:]))
        st, j, _, _ = p.req("GET", "/api/drives/job")
        check("abort: the job says it is stopping", j["running"] is True and j["stopping"] is True, j)
        j = wait_job()
        check("abort: the change ends with the tool's own last sentence, code 4", j["rc"] == 4 and "Stopped as you asked" in j["message"] and j["stopping"] is False, j)
        st, js, _, _ = p.req("POST", "/api/drives/wipe", {"id": "sdc", "mode": "empty", "typed": ["/dev/sdc", "ERASE"]})
        time.sleep(0.5)
        st, js, _, _ = p.req("POST", "/api/drives/abort", {})
        check("abort: an erase cannot be stopped", st == 409 and "cannot be stopped" in js["error"], (st, js))
        wait_job()
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

        # ---- looking at the drives never collides with other looks; a change waits for the looks that run, and the looks wait for no one
        p.env["HLP_DRIVES"] = FAKE
        p.env["FAKE_DRIVES_MODE"] = "slowhealth"
        p.start(); p.login()
        outh = {}
        th = threading.Thread(target=lambda: outh.update(zip(("st", "js"), p.req("GET", "/api/drives/health")[:2])))
        th.start()
        time.sleep(0.5)
        t0 = time.time()
        st, js, _, _ = p.req("GET", "/api/drives")
        check("drives: the list can be read while the health is being read (no 'another command' error)", st == 200 and "status" in js, (st, js))
        st, js, _, _ = p.req("GET", "/api/drives/check")
        check("drives: two looks at once are fine", st == 200 and "drives" in js, (st, js))
        st, js, _, _ = p.req("POST", "/api/drives/add", {"id": "sdc", "role": "main", "mode": "erase", "typed": ["/dev/sdc", "ERASE"]})
        check("drives: a change waits for the look that runs, then starts", st == 200 and js.get("ok") is True, (st, js, time.time() - t0))
        wait_job()
        th.join(10)
        check("drives: the slow look finished well", outh.get("st") == 200 and "drives" in (outh.get("js") or {}), outh)
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
        check("drives: a look at the drives during a change is turned away, with words that say why (the page shows the progress)", st == 409 and "drive change is running" in js["error"], (st, js))
        t.join(10)
        check("drives: the slow remount finished well", out.get("st") == 200, out)
    finally:
        p.stop()
    ok = all(t_panel.results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
