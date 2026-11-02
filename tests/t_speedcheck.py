#!/usr/bin/env python3
"""Tests of the parts of tools/speedcheck.py that do not need root: counting started programs and the plain-language findings.
Run: python3 tests/t_speedcheck.py   (last line is OK or FAIL)"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("speedcheck", os.path.join(HERE, "..", "tools", "speedcheck.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
bad = 0


def check(name, got, want):
    global bad
    ok = got == want
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   got %r, wanted %r" % (got, want)))


TRACE = """1234 execve("/usr/bin/drives", ["drives"], 0x7ffd /* 30 vars */) = 0
1235 execve("/usr/bin/lsblk", ["lsblk", "-d"], 0x7ffd /* 30 vars */) = 0
1236 execve("/usr/bin/lsblk", ["lsblk", "-n"], 0x7ffd /* 30 vars */) = 0
1237 execve("/usr/local/bin/lsblk", ["lsblk"], 0x7ffd) = -1 ENOENT (No such file or directory)
1238 execve("/usr/bin/awk", ["awk"], 0x7ffd) = 0
1239 +++ exited with 0 +++
"""
c = m.count_programs(TRACE)
check("programs are counted by name", dict(c), {"drives": 1, "lsblk": 2, "awk": 1})
check("a failed start is not counted", c["lsblk"], 2)
check("a quiet command gets no findings", m.hints("x", 1.0, 20, c), [])
check("a slow command is named", len(m.hints("x", 9.0, 20, c)), 1)
check("many programs are named", len(m.hints("x", 1.0, 900, c)), 1)
check("a repeated scan is named", m.hints("drives list", 1.0, 100, m.collections.Counter({"lsblk": 80, "bash": 90})),
      ["drives list starts 'lsblk' 80 times; a scan that could be done once and reused"])
check("the median is the middle value", m.median([3.0, 1.0, 2.0]), 2.0)
check("an empty list has median 0", m.median([]), 0.0)
check("the user commands are wrapped with sudo -u", m.wrap(["homelab"], True, "bob")[:4], ["sudo", "-u", "bob", "-H"])
check("the root commands are not", m.wrap(["drives"], False, "bob")[0], "env")
check("a backup lock that is not there is no running backup", m.backup_running() if not os.path.exists(m.BACKUP_LOCK) else False, False)
print("OK" if bad == 0 else "FAIL")
sys.exit(bad)
