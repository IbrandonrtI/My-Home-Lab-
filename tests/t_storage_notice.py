#!/usr/bin/env python3
"""Tests of what the installer says when the Main pool has no drive (/mnt/storage is a locked, unmounted folder): the steps that need it are marked
as waiting for a Main drive, the notice explains what is paused and what to do, and the control panel is still updated. No file outside a temp folder is touched.
Run: python3 tests/t_storage_notice.py   (last line is OK or FAIL)"""
import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "installer", "homelab-setup")
bad = 0


def check(name, ok, extra=""):
    global bad
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   " + str(extra)[:700]))


g = {"__name__": "hls_under_test", "__file__": SRC}
with open(SRC, encoding="utf-8") as f:
    exec(compile(f.read(), SRC, "exec"), g)      # noqa: S102 (our own installer file, run as a module)
g["load_all"]()
STEPS, BY_ID = g["STEPS"], g["BY_ID"]

check("the stacks and the web terminal wait for the folders step", g["waits_for_folders"](BY_ID["stack-immich"]) and g["waits_for_folders"](BY_ID["terminal"]), "")
check("the system steps do not wait for it", not g["waits_for_folders"](BY_ID["os"]), "")

class R:      # a stand-in for Result
    def __init__(self, state, detail=""):
        self.state, self.detail = state, detail

res = {s.id: R("blocked" if g["waits_for_folders"](s) else "done") for s in STEPS}
res["folders"] = R("failed", "x")

g["main_storage_missing"] = lambda: False
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    g["storage_notice"](res)
check("with a drive in Main the notice says nothing", buf.getvalue().strip() == "", buf.getvalue())

g["main_storage_missing"] = lambda: True
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    g["storage_notice"](res)
txt = " ".join(buf.getvalue().split())
check("the notice has a title and says the update itself is fine", "The Main pool has no drive" in txt and "the new scripts and the control panel are installed" in txt, txt)
check("it names what waits (the groups and the web terminal)", "steps wait for it" in txt and "Services (" in txt and "web terminal" in txt, txt)
check("it says what to do: the panel Drives tab or sudo drives, then refresh", "drag a drive into Main pool" in txt and "sudo drives" in txt and "sudo homelab-setup refresh" in txt, txt)

buf = io.StringIO()
res2 = dict(res)
with contextlib.redirect_stdout(buf):
    g["show_checklist"](res2)
txt = " ".join(buf.getvalue().split())
check("the checklist marks the waiting steps", "(waits for a Main drive)" in txt, txt)

g["locked_mountpoint"] = lambda path: path == "/mnt/storage"
msg = g["folder_problem"]("/mnt/storage/immich", OSError(13, "Permission denied"))
check("the folder message explains both cases (a drive that is away, or no drive at all)", "sudo drives remount" in msg and "drag a drive into it" in msg and "sudo homelab-setup refresh" in msg, msg)

g["main_storage_missing"] = lambda: False
res3 = dict(res)
check("the panel is not touched when the storage is fine", g["update_panel_when_blocked"](res3) is False, "")

print("OK" if not bad else "FAIL (%d)" % bad)
sys.exit(1 if bad else 0)
