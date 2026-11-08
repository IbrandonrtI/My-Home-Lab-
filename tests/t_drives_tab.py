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
ALLOWED = {"status", "health", "check", "actions", "remount", "rename", "sleep", "wake"}


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
        st, js, _, _ = p.req("POST", "/api/drives/wipe", {"id": "sdb"})
        check("drives: erasing is not there (not found)", st == 404 and len(calls()) == n2, st)
        for word in ("disconnect", "move", "eject", "release", "connect", "replace"):
            st, js, _, _ = p.req("POST", "/api/drives/" + word, {"id": "sdb"})
            check("drives: '%s' is not there either" % word, st == 404 and len(calls()) == n2, st)
        check("drives: only allowed words were ever asked of the tool", all(c[0] == "panel" and c[1] in ALLOWED for c in calls()), [c for c in calls() if c[1] not in ALLOWED])

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
