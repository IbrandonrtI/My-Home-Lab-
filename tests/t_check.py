#!/usr/bin/env python3
"""Tests for scripts/homelab-repocheck's secret scan: real-looking values are reported, placeholders are not.
Run: python3 tests/t_check.py   (last line is OK or FAIL; nothing outside a temp folder is touched)"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK = os.path.join(HERE, "..", "scripts", "homelab-repocheck")


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
    ("ignore marker is respected", "DB_PASSWORD=Zq8xK2mVb9Lp4Rt7  <!-- homelab-repocheck: ignore -->", False),
]

bad = 0
for name, body, should_flag in CASES:
    rc, out = run(body)
    flagged = "looks like" in out
    ok = flagged == should_flag
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name)

def installer_case(name, edit):
    """homelab-repocheck compares installer/homelab-setup with the join of src/installer/NN_*.py: a copy that differs must be reported."""
    global bad
    with tempfile.TemporaryDirectory() as d:
        for sub in ("scripts", "stacks", os.path.join("src", "installer"), "installer"):
            os.makedirs(os.path.join(d, sub))
        with open(os.path.join(d, "README.md"), "w") as f:
            f.write("# Test\n")
        parts = {"10_a.py": "A = 1\n", "20_b.py": "B = 2\n"}
        for fn, text in parts.items():
            with open(os.path.join(d, "src", "installer", fn), "w") as f:
                f.write(text)
        with open(os.path.join(d, "installer", "homelab-setup"), "w") as f:
            f.write(edit("".join(parts.values())))
        p = subprocess.run([sys.executable, CHECK, d], capture_output=True, text=True)
        out = p.stdout + p.stderr
        ok = ("exactly the join of the 2 files" in out) if name.startswith("matching") else ("not the join" in out)
        bad += not ok
        print(("ok   " if ok else "FAIL ") + name)


def old_pieces_case():
    """Old src/pNN_*.py pieces that were left behind after the move to src/installer/ are reported (a warning)."""
    global bad
    with tempfile.TemporaryDirectory() as d:
        for sub in ("scripts", "stacks", "src", "installer"):
            os.makedirs(os.path.join(d, sub))
        with open(os.path.join(d, "README.md"), "w") as f:
            f.write("# Test\n")
        with open(os.path.join(d, "src", "p01_core.py"), "w") as f:
            f.write("A = 1\n")
        with open(os.path.join(d, "installer", "homelab-setup"), "w") as f:
            f.write("A = 1\n")
        p = subprocess.run([sys.executable, CHECK, d], capture_output=True, text=True)
        ok = "src/ still holds the old installer pieces" in (p.stdout + p.stderr)
        bad += not ok
        print(("ok   " if ok else "FAIL ") + "old installer pieces left in src/ are reported")


old_pieces_case()
installer_case("matching installer and src/ files are accepted", lambda joined: joined)
installer_case("an installer that differs from src/ is reported", lambda joined: joined + "C = 3\n")
print("OK" if not bad else "FAIL")
sys.exit(1 if bad else 0)
