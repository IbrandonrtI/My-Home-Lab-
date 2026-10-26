#!/usr/bin/env python3
"""Tests for scripts/homelab-check's secret scan: real-looking values are reported, placeholders are not.
Run: python3 tests/t_check.py   (last line is OK or FAIL; nothing outside a temp folder is touched)"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "..", "scripts", "homelab-check")


def run(body):
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "scripts"))
        os.makedirs(os.path.join(d, "stacks"))
        with open(os.path.join(d, "README.md"), "w") as f:
            f.write("# Test\n\n" + body + "\n")
        p = subprocess.run([sys.executable, CHECK, d], capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


CASES = [
    ("real password line is reported", "NEXTCLOUD_PASSWORD=Zq8xK2mVb9Lp4Rt7", True),
    ("Tailscale key is reported", "key tskey-" + "auth-abcdefghijklmnop123", True),
    ("placeholder password is fine", "DB_PASSWORD=your-password-here", False),
    ("changeme is fine", "ADMIN_PASSWORD=changeme-please-now", False),
    ("variable reference is fine", "DB_PASSWORD=${DB_PASSWORD_VALUE}", False),
    ("ignore marker is respected", "DB_PASSWORD=Zq8xK2mVb9Lp4Rt7  <!-- homelab-check: ignore -->", False),
]

bad = 0
for name, body, should_flag in CASES:
    rc, out = run(body)
    flagged = "looks like" in out
    ok = flagged == should_flag
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name)
print("OK" if not bad else "FAIL")
sys.exit(1 if bad else 0)
