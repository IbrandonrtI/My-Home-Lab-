#!/usr/bin/env python3
"""Test: the drive bench's own logic (no drives are made): answer choices, run classification, the report builder, the safety guards.
Last line: OK or FAIL."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.join(HERE, "..", "tools", "drive-bench")
sys.path.insert(0, B)
import bench   # noqa: E402
import report  # noqa: E402

bad = 0


def check(name, got, want):
    global bad
    if got == want:
        print("ok   ", name)
    else:
        bad += 1
        print("FAIL ", name, "  got", repr(got), " wanted", repr(want))


# scripts compile
for f in ("bench.py", "report.py", "others.py"):
    r = subprocess.run([sys.executable, "-m", "py_compile", os.path.join(B, f)], capture_output=True)
    check("compiles " + f, r.returncode, 0)
for f in ("shim.sh", "drive-bench"):
    r = subprocess.run(["bash", "-n", os.path.join(B, f)], capture_output=True)
    check("bash -n " + f, r.returncode, 0)

# answers: a menu question, a yes/no question, the typed confirmations, a size
menu = {"kind": "ask", "prompt": "Type a number and press Enter: ", "items": [], "answer": "<EOF>"}
c = [a for a, _ in bench.candidates(menu, "  1) A\n  2) B\n  3) C\n  0) Quit\n", "standard", None)]
check("menu answers come from the screen", c[:3], ["1", "2", "3"])
check("menu also gets Enter and a wrong number", "" in c and "9" in c, True)
yn = {"kind": "yn", "prompt": "Continue? [y/N]: ", "items": [], "answer": "<EOF>"}
check("yes/no tries yes first", [a for a, _ in bench.candidates(yn, "", "quick", None)], ["y", "n"])
ch = {"kind": "choose", "prompt": "Which? ", "items": ["a", "b", "c"], "answer": "<EOF>"}
check("a list tries every entry, then 0", [a for a, _ in bench.candidates(ch, "", "quick", None)], ["1", "2", "3", "0"])
bench.SAFE_DEVS.clear()
bench.SAFE_DEVS.add("/dev/loop7")
ty = {"kind": "typed", "prompt": "Type the drive name exactly (/dev/sda) to continue: ", "items": [], "answer": "<EOF>"}
check("never types the name of a drive that is not a fake drive", [a for a, _ in bench.candidates(ty, "", "full", None)], [""])
ty = {"kind": "typed", "prompt": "Type the drive name exactly (/dev/loop7) to continue: ", "items": [], "answer": "<EOF>"}
check("types the name of a fake drive", bench.candidates(ty, "", "quick", None)[0], ("/dev/loop7", False))
sz = {"kind": "ask", "prompt": "How many MB should the section have? [16 to 900 MB, Enter to cancel]: ", "items": [], "answer": "<EOF>"}
c = [a for a, _ in bench.candidates(sz, "", "full", None)]
check("a size: a good one first, then too small and too big", c[0].isdigit() and "15" in c and "901" in c and "abc" in c, True)

# classification
ev_eof = [{"n": 1, "kind": "yn", "prompt": "Go? [y/N]: ", "answer": "<EOF>", "items": []}]
check("ended at a question = cancelled", bench.classify(0, "Go? [y/N]: \n", False, ev_eof, False, "move")[0], "CANCELLED")
check("a change = done", bench.classify(0, "Done.\n", False, [], True, "connect")[0], "DONE")
check("a refusal that exits 0 is reported", bench.classify(0, "X is the only main drive.\n", False, [], False, "disconnect")[1], ["exit 0 although the command refused"])
check("status text is not a refusal", bench.classify(0, "not mounted\n", False, [], False, "status")[0], "NOTHING")
check("exit 1 with a message = refused", bench.classify(1, "ERROR: no\n", False, [], False, "x")[0], "REFUSED")
check("exit 1 with nothing = silent fail", bench.classify(1, "", False, [], False, "x")[0], "SILENT-FAIL")
check("unbound variable = crash", bench.classify(0, "drives: line 3: x: unbound variable\n", False, [], False, "x")[0], "CRASH")
check("the words 'syntax error' in normal text are not a crash", bench.classify(0, "ok  every script passes the syntax error check\n", False, [], False, "x")[0], "NOTHING")
check("a cancel with exit 1 is a cancel", bench.classify(1, "Cancelled. Nothing was changed.\n", False, [], False, "x")[0], "CANCELLED")
check("a dry run that mentions 'only backup drive' is not a refusal", bench.classify(0, "WARNING: X is the only backup drive.\nDRY RUN: this is what would happen now.\n", False, [], False, "disconnect")[0], "NOTHING")
check("the same command with another option is another case", bench.case_id("l", ["x"], ["1"], None, (), "dry") != bench.case_id("l", ["x"], ["1"], None, (), "yes"), True)
check("timeout = crash", bench.classify(124, "", True, [], False, "x")[0], "CRASH")

# the report
T = tempfile.mkdtemp()
rows = [
    {"id": "1", "layout": "m1-b1", "flow": "disconnect", "args": ["disconnect"], "answers": ["1"], "fault": None, "pre": [], "note": "", "rc": 0,
     "secs": 1, "outcome": "REFUSED", "flags": ["exit 0 although the command refused"], "msg": "", "changed": False,
     "prompts": [{"n": 1, "kind": "choose", "prompt": "Which drive? ", "items": ["a", "b"], "answer": "1"}], "output": "Which drive? 1\nX is the only main drive.\n",
     "docker": [], "probe": None},
    {"id": "2", "layout": "m2-b1", "flow": "move", "args": ["move"], "answers": ["1", "y", "n", "CONTINUE"], "fault": None, "pre": [], "note": "",
     "rc": 0, "secs": 2, "outcome": "CANCELLED", "flags": ["INV-false-claim: it says 'Nothing was changed' but things changed"], "msg": "", "changed": True,
     "prompts": [], "output": "Cancelled. Nothing was changed.\n", "docker": [], "probe": None},
    {"id": "3", "layout": "m2-b1", "flow": "connect", "args": ["connect"], "answers": ["1", "1", "/dev/loop2", "ERASE"], "fault": None, "pre": [], "note": "",
     "rc": 0, "secs": 3, "outcome": "DONE", "flags": [], "msg": "", "changed": True,
     "prompts": [{"n": 2, "kind": "choose", "prompt": "Use this drive for: ", "items": ["Main", "Backup"], "answer": "1"}], "output": "Done.\n", "docker": [], "probe": None},
    {"id": "4", "layout": "m2-b1", "flow": "wish", "args": ["rename"], "answers": [], "fault": None, "pre": [], "note": "rename: give a drive a name", "rc": 0,
     "secs": 0, "outcome": "NOTHING", "flags": [], "msg": "", "changed": False, "prompts": [], "output": "Usage: sudo drives [menu|status]\n", "docker": [], "probe": None},
]
rp = os.path.join(T, "results.jsonl")
with open(rp, "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
with open(os.path.join(T, "meta.json"), "w") as f:
    json.dump({"level": "quick", "drives": os.path.join(HERE, "..", "scripts", "drives")}, f)
report.build(rp, T)
txt = open(os.path.join(T, "report.txt")).read()
page = open(os.path.join(T, "report.html")).read()
fj = json.load(open(os.path.join(T, "findings.json")))
check("report: the serious problem comes first", fj["findings"][0]["severity"], "HIGH")
check("report: says how to repeat it", "answers typed, in order: 1 | y | n | CONTINUE" in txt, True)
check("report: a word that is not supported is listed", "rename" in txt and "NOT SUPPORTED" in txt, True)
check("report: Connect to Main shows as working", any(c["title"].startswith("Connect a drive to the Main") and c["status"] == "WORKS" for c in fj["capabilities"]), True)
check("report: html page is made", page.startswith("<!doctype html>") and "Layout" in page, True)
check("report: an idea comes from a missing word", any(i["id"] == "rename" for i in fj["ideas"]), True)

# the safety guard: the real drives are hidden from `drives`
check("lsblk fake hides the real drives", "-dnpo NAME,TYPE" in bench.FAKE_LSBLK, True)
print("OK" if bad == 0 else "FAIL")
sys.exit(0 if bad == 0 else 1)
