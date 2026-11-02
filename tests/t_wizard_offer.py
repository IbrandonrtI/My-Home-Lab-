#!/usr/bin/env python3
"""Tests of the offer the installer makes at the end of the first install: `sudo drives wizard --first-run`, once, and only
when it is safe to ask. Run: python3 tests/t_wizard_offer.py   (last line is OK or FAIL; nothing outside a temp folder is touched)"""
import importlib.machinery
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.join(HERE, "..", "installer", "homelab-setup")
os.environ["HLS_FAKE"] = "1"
loader = importlib.machinery.SourceFileLoader("hls", PROG)
spec = importlib.util.spec_from_loader("hls", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

bad = 0
calls = []


def check(name, got, want):
    global bad
    ok = got == want
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   got %r, wanted %r" % (got, want)))


tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "usr/local/sbin"))
drives = os.path.join(tmp, "usr/local/sbin/drives")
m.P = lambda p: os.path.join(tmp, p.lstrip("/"))
m.State.save = lambda: None
m.subprocess.call = lambda a, *x, **k: calls.append(list(a)) or 0
m.out = lambda *a, **k: None
m.say = lambda *a, **k: None
m.rule = lambda *a, **k: None


def offer(fake=False, yes=False, dry=False, tty=True, script=True, mounted=False, done=False):
    calls.clear()
    m.FAKE = fake
    m.Opt.yes, m.Opt.dry = yes, dry
    m.interactive = lambda: tty
    m.State.data = {"wizard_offered": "x"} if done else {}
    m.os.path.ismount = lambda p: mounted
    if script and not os.path.exists(drives):
        open(drives, "w").close()
    if not script and os.path.exists(drives):
        os.remove(drives)
    m.offer_drive_wizard()
    return list(calls)


check("a normal first install asks once", offer(), [[drives, "wizard", "--first-run"]])
check("it remembers that it asked", "wizard_offered" in m.State.data, True)
check("the test machine never asks", offer(fake=True), [])
check("--yes never asks (nobody to answer)", offer(yes=True), [])
check("--dry-run never asks", offer(dry=True), [])
check("no terminal, no question", offer(tty=False), [])
check("asked before: not again", offer(done=True), [])
check("no drives command installed: nothing to start", offer(script=False), [])
check("a drive is already mounted at /mnt/storage: nothing to offer", offer(mounted=True), [])
print("OK" if bad == 0 else "FAIL")
sys.exit(bad)
