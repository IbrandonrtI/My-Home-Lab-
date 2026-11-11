#!/usr/bin/env python3
"""Test of the Updates tab's server side in scripts/homelab-panel: what is waiting (read from the state files), the buttons that run commands in the
background (FAKE commands, nothing real), the restart that needs a confirmation, one job at a time, and the plain-words problems.
Run: python3 tests/t_updates_tab.py   (last line is OK or FAIL)"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import t_panel  # noqa: E402  (the same panel harness)

check = t_panel.check


def wait_done(p, limit=20):
    end = time.time() + limit
    while time.time() < end:
        st, js, _, _ = p.req("GET", "/api/updates/job")
        if st == 200 and not js["running"]:
            return js
        time.sleep(0.2)
    return {}


def main():
    tmp = tempfile.mkdtemp(prefix="hlupd-")
    state = os.path.join(tmp, "hlstate")
    os.makedirs(state)
    reboot = os.path.join(tmp, "reboot-required")
    ok_cmd = os.path.join(tmp, "ok.sh")
    slow_cmd = os.path.join(tmp, "slow.sh")
    fail_cmd = os.path.join(tmp, "fail.sh")
    for path, text in ((ok_cmd, "#!/bin/sh\necho 'step one'\nprintf '\\033[32mgreen\\033[0m done\\n'\n"),
                       (slow_cmd, "#!/bin/sh\necho started\nsleep 2\necho finished\n"),
                       (fail_cmd, "#!/bin/sh\necho 'sudo: a password is required'\nexit 1\n")):
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, 0o755)
    steps = {"check": [[ok_cmd]], "containers": [[slow_cmd]], "system": [[ok_cmd], [ok_cmd]], "restart": [[fail_cmd]]}
    p = t_panel.Panel(tmp, {"HLP_UPDATE_STATE": state, "HLP_REBOOT_FILE": reboot, "HLP_UPDATE_STEPS": json.dumps(steps)})
    try:
        p.set_password()
        p.start()
        st, js, _, _ = p.req("GET", "/api/updates")
        check("updates: the state needs a login", st == 401, st)
        st, js, _, _ = p.req("POST", "/api/updates/start", {"what": "check"})
        check("updates: starting needs a login", st == 401, st)
        p.login()
        st, js, _, _ = p.req("POST", "/api/updates/start", {"what": "check"}, headers={"Origin": "https://evil.example.com"})
        check("updates: a request from another website is refused", st == 403, st)

        st, js, _, _ = p.req("GET", "/api/updates")
        check("updates: with no files yet nothing is waiting and the system count is unknown", st == 200 and js["containers"] == [] and js["system"] is None and js["restart"] is False and js["checked"] == 0, (st, js))
        with open(os.path.join(state, "image-updates"), "w") as f:
            f.write("1700000000\nimmich  ghcr.io/immich=new\nnextcloud  nc=new\n")
        with open(os.path.join(state, "apt"), "w") as f:
            f.write("7|2\n")
        open(reboot, "w").close()
        st, js, _, _ = p.req("GET", "/api/updates")
        check("updates: what is waiting is read from the files", [c["name"] for c in js["containers"]] == ["immich", "nextcloud"] and js["system"] == 7 and js["restart"] is True and js["checked"] == 1700000000, js)

        st, js, _, _ = p.req("POST", "/api/updates/start", {"what": "rm -rf /"})
        check("updates: only the known buttons work", st == 400, (st, js))
        st, js, _, _ = p.req("POST", "/api/updates/start", {"what": "restart"})
        check("updates: a restart needs the confirmation", st == 400 and "Confirm" in js["error"], (st, js))

        st, js, _, _ = p.req("POST", "/api/updates/start", {"what": "containers"})
        check("updates: the containers button starts a background job", st == 200 and js["ok"], (st, js))
        st2, js2, _, _ = p.req("POST", "/api/updates/start", {"what": "check"})
        check("updates: a second job is refused while one runs", st2 == 409 and "already" in js2["error"], (st2, js2))
        job = wait_done(p)
        check("updates: the job's lines are shown and it ends well", job.get("rc") == 0 and "finished" in job["lines"] and job["message"] == "finished", job)

        st, js, _, _ = p.req("POST", "/api/updates/start", {"what": "system"})
        job = wait_done(p)
        check("updates: the system update runs both commands and strips colors", job.get("rc") == 0 and job["lines"].count("step one") == 2 and "green done" in job["lines"], job)

        st, js, _, _ = p.req("POST", "/api/updates/start", {"what": "restart", "confirm": True})
        job = wait_done(p)
        check("updates: a refused sudo is explained in words", st == 200 and job.get("rc") == 1 and "not allowed" in job["message"], job)
        st, js, _, _ = p.req("GET", "/api/updates")
        check("updates: the state carries the last job", js["job"]["action"] == "restart" and js["job"]["running"] is False, js["job"])
    finally:
        p.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    ok = all(t_panel.results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
