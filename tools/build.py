#!/usr/bin/env python3
import os
import py_compile
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = [("installer/homelab-setup", "src/installer", "py"), ("scripts/drives", "src/drives", "sh"),
           ("scripts/homelab", "src/homelab", "sh"), ("scripts/homelab-update", "src/homelab-update", "sh")]


def join_pieces(folder, ext):
    names = sorted(n for n in os.listdir(os.path.join(ROOT, folder)) if re.match(r"^\d\d_.*\.%s$" % ext, n))
    if not names:
        raise SystemExit("no pieces in %s" % folder)
    text = ""
    for n in names:
        with open(os.path.join(ROOT, folder, n), encoding="utf-8") as f:
            part = f.read()
        text += re.sub(r"^@@include (\S+)@@\n", lambda m: open(os.path.join(ROOT, folder, m.group(1)), encoding="utf-8").read(), part, flags=re.M)
    return text


def main(argv):
    """Build each generated file from its folder of pieces, or with --check report which ones are out of date."""
    check = "--check" in argv
    bad = 0
    for out, folder, ext in TARGETS:
        text = join_pieces(folder, ext)
        path = os.path.join(ROOT, out)
        if check:
            same = os.path.exists(path) and open(path, encoding="utf-8").read() == text
            print("%s %s" % ("matches  " if same else "DIFFERS  ", out))
            bad += not same
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(path, 0o755)
        if ext == "py":
            py_compile.compile(path, doraise=True)
            cache = os.path.join(os.path.dirname(path), "__pycache__")
            subprocess.run(["rm", "-rf", cache])
        elif subprocess.run(["bash", "-n", path]).returncode:
            raise SystemExit("%s has a syntax error" % out)
        print("built %s: %d lines" % (out, text.count("\n")))
    if check and bad:
        print("Some built files do not match src/. Run:  bash tools/build.sh", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
