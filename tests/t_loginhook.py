#!/usr/bin/env python3
"""The login screen hook in ~/.bashrc must never freeze a login. On Ubuntu 26.04 (uutils `timeout`) running the screen straight on
the terminal under `timeout` froze the login when the terminal stops background output (TOSTOP) and Ctrl+C did nothing.
This opens a real terminal with that setting, runs the hook from the installer with a stand-in `homelab`, and checks the prompt comes.
Run: python3 tests/t_loginhook.py   (last line is OK or FAIL)"""
import os
import pty
import re
import select
import shutil
import signal
import sys
import tempfile
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "..", "src", "p08_system2.py"), encoding="utf-8").read()
m = re.search(r'LOGIN_BLOCK = """(.*?)"""', src, re.S)
bad = 0


def check(name, ok, extra=""):
    global bad
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   " + extra))


check("the hook is found in the installer source", bool(m))
if not m:
    print("FAIL")
    sys.exit(1)
block = m.group(1)
check("the hook builds the screen out of sight and in the foreground group", "--foreground 20 homelab login" in block and ">\"$_hl_out\"" in block and "</dev/null" in block)

tmp = tempfile.mkdtemp()
try:
    os.makedirs(os.path.join(tmp, "bin"))
    stub = os.path.join(tmp, "bin", "homelab")
    with open(stub, "w") as f:
        f.write("#!/bin/sh\necho 'HOMELAB-SCREEN'\nstty size </dev/tty >/dev/null 2>&1\nsleep 0.2\necho 'HOMELAB-END'\n")
    os.chmod(stub, 0o755)
    rc = os.path.join(tmp, "rc")
    with open(rc, "w") as f:
        f.write("PATH=%s/bin:$PATH\nPS1='READY> '\n%s\n" % (tmp, block))
    if not shutil.which("timeout") or not shutil.which("bash"):
        print("skipped: needs bash and timeout")
        print("OK")
        sys.exit(0)

    def session(tostop):
        pid, fd = pty.fork()
        if pid == 0:
            if tostop:
                a = termios.tcgetattr(0)
                a[3] |= termios.TOSTOP
                termios.tcsetattr(0, termios.TCSANOW, a)
            os.environ["TERM"] = "xterm-256color"
            os.execvp("bash", ["bash", "--noprofile", "--rcfile", rc, "-i"])
        start, out = time.time(), b""
        while time.time() - start < 15:
            r, _, _ = select.select([fd], [], [], 0.5)
            if r:
                try:
                    d = os.read(fd, 65536)
                except OSError:
                    break
                if not d:
                    break
                out += d
            if b"READY>" in out:
                break
        took = time.time() - start
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        return out.decode(errors="replace"), took

    for tostop in (False, True):
        out, took = session(tostop)
        label = "with" if tostop else "without"
        check("the prompt comes %s TOSTOP set" % label, "READY>" in out, "got %r after %.1fs" % (out[-200:], took))
        check("the screen is shown %s TOSTOP set" % label, "HOMELAB-SCREEN" in out and "HOMELAB-END" in out)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("OK" if bad == 0 else "FAIL")
sys.exit(1 if bad else 0)
