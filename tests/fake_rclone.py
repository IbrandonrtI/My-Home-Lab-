#!/usr/bin/env python3
"""Stand-in for rclone in tests. The remote "NAME:" is the folder $FAKE_RCLONE_DIR/NAME. Understands the few commands the backup engine uses:
listremotes, sync, copy (with --backup-dir and --exclude), lsf --dirs-only, lsjson, purge."""
import json
import os
import subprocess
import sys

BASE = os.environ["FAKE_RCLONE_DIR"]
REMOTES = os.environ.get("FAKE_RCLONE_REMOTES", "gd").split(",")


def real(spec):
    if ":" in spec and not spec.startswith("/"):
        name, path = spec.split(":", 1)
        return os.path.join(BASE, name, path.lstrip("/"))
    return spec


def main(argv):
    cmd = argv[0]
    opts = {}
    pos = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in ("--backup-dir", "--stats"):
            opts[a] = argv[i + 1]
            i += 2
        elif a.startswith("--"):
            opts[a.split("=")[0]] = a.split("=", 1)[1] if "=" in a else True
            i += 1
        elif a == "-v":
            i += 1
        else:
            pos.append(a)
            i += 1
    excl = [a for a in argv if a.startswith("--exclude=")]
    if cmd == "listremotes":
        for r in REMOTES:
            print(r + ":")
        return 0
    if cmd in ("sync", "copy"):
        src, dst = real(pos[0]), real(pos[1])
        os.makedirs(dst, exist_ok=True)
        src_arg = src.rstrip("/") + "/" if os.path.isdir(src) else src
        a = ["rsync", "-a"] + excl
        if cmd == "sync":
            a.append("--delete")
        bd = None
        if "--backup-dir" in opts:
            bd = real(opts["--backup-dir"])
            a += ["--backup", "--backup-dir=" + bd]
        if "--dry-run" in opts:
            p = subprocess.run(a + ["-n", "-i", src_arg, dst.rstrip("/") + "/"], capture_output=True, text=True)
            for line in p.stdout.split("\n"):
                if line.startswith(">f"):
                    print("NOTICE: %s: Skipped copy as --dry-run is set" % line[12:])
                elif line.startswith("*deleting"):
                    print("NOTICE: %s: Skipped delete as --dry-run is set" % line[9:].strip())
            return p.returncode
        rc = subprocess.call(a + [src_arg, dst.rstrip("/") + "/"])
        if bd and os.path.isdir(bd) and not os.listdir(bd):
            os.rmdir(bd)
        return rc
    if cmd == "lsf":
        d = real(pos[0])
        if not os.path.isdir(d):
            return 3
        for n in sorted(os.listdir(d)):
            if os.path.isdir(os.path.join(d, n)):
                print(n + "/")
        return 0
    if cmd == "lsjson":
        d = real(pos[0])
        if not os.path.isdir(d):
            return 3
        out = []
        for n in sorted(os.listdir(d)):
            p = os.path.join(d, n)
            out.append({"Name": n, "IsDir": os.path.isdir(p), "Size": 0 if os.path.isdir(p) else os.path.getsize(p)})
        print(json.dumps(out))
        return 0
    if cmd == "purge":
        subprocess.call(["rm", "-rf", real(pos[0])])
        return 0
    print("fake rclone: unknown command " + cmd, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
