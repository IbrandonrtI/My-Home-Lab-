#!/usr/bin/env python3
"""Unit test of the message the installer gives when the folders for the services cannot be made because a drive folder is locked (the drives tool locks the
folder of an unmounted drive on purpose). Run: python3 tests/t_folders.py   (last line is OK or FAIL)"""
import importlib.machinery
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.join(HERE, "..", "installer", "homelab-setup")
os.environ["HLS_FAKE"] = "1"
loader = importlib.machinery.SourceFileLoader("hls", PROG)
spec = importlib.util.spec_from_loader("hls", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

bad = 0


def check(name, ok, extra=""):
    global bad
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   " + str(extra)))


err = PermissionError(1, "Operation not permitted")
m.locked_mountpoint = lambda path: path == "/mnt/storage"
msg = m.folder_problem("/mnt/storage/immich", err)
check("a folder under a locked, unmounted /mnt/storage: plain words and the commands to run", "/mnt/storage is not mounted right now" in msg and "sudo drives remount" in msg and "sudo homelab-setup refresh" in msg and "PermissionError" not in msg, msg)
msg = m.folder_problem("/mnt/backup/x", err)
check("another folder (backup is not locked here): the general message names the folder and the reason", "/mnt/backup/x could not be made" in msg and "Operation not permitted" in msg and "sudo drives" in msg, msg)
msg = m.folder_problem("/opt/adguard-docker", err)
check("a folder that is not on a drive: the general message", "could not be made" in msg and "not mounted right now" not in msg, msg)


# the step turns the error into a clean failure the person can read (an Abort), not "unexpected error"
orig = m.mkdirs


def failing(path, u=None, g=None, mode=0o755):
    raise err


m.mkdirs = failing
try:
    m.Folders().run()
    check("the Folders step stops with a readable message", False, "no error")
except m.Abort as e:
    check("the Folders step stops with a readable message (an Abort, not an unexpected error)", "/mnt/storage" in str(e) and "sudo drives remount" in str(e), str(e))
except Exception as e:  # noqa: BLE001
    check("the Folders step stops with a readable message", False, repr(e))
m.mkdirs = orig
print("OK" if not bad else "FAIL")
