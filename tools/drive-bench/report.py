"""report.py - turns results.jsonl (one line per run) into report.txt, report.html and findings.json.

Sections: summary, problems (ranked, with how to reproduce them), what works and what does not, the layout x command grid,
the messages that explain what is refused, every question the commands asked, the other commands, and ideas to add.
"""
import collections
import html
import json
import os
import re

SEVERITY = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}


def load(path):
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path):
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def norm(text):
    """Make a message the same for every layout: numbers, devices, folders and drive labels are replaced."""
    t = re.sub(r"/dev/loop\d+(p\d+)?", "DEV", text)
    t = re.sub(r"/var/tmp/[^\s'\"]+", "PATH", t)
    t = re.sub(r"\bT(MAIN|BACKUP)\d*(BOOT)?\b", "LABEL", t)
    t = re.sub(r"\d+", "#", t)
    return t.strip()


def severity_of(r, flag):
    if flag.startswith("INV-left-stopped"):
        return "MEDIUM"
    if r["outcome"] in ("CRASH", "BUILD-FAIL") or flag.startswith("INV-") or flag.startswith("bash-error") or flag in ("timeout", "endless-prompt"):
        return "HIGH"
    if r["outcome"] == "SILENT-FAIL" or flag.startswith("exit 1 without") or flag.startswith("an unknown word"):
        return "MEDIUM"
    if flag.startswith("exit 0 although"):
        return "LOW"
    if r["outcome"] in ("MISSING",):
        return "MEDIUM"
    if flag.startswith("dangerous"):
        return "INFO"
    return "LOW"


def last_lines(out, n=6, prompts=()):
    lines = [l for l in out.splitlines() if l.strip()]
    if prompts:
        keep = [l for l in lines if not any(p and l.startswith(p) and len(l) <= len(p) + 40 for p in prompts)]
        lines = keep or lines
    return "\n".join(lines[-n:])


def message_block(r, n=2):
    """What the command said at the end: the first lines after its last question (or from the start when it asked nothing)."""
    lines = [l for l in r["output"].splitlines() if l.strip()]
    ps = prompt_texts(r)
    idx = -1
    for i, l in enumerate(lines):
        if any(p and l.startswith(p) for p in ps):
            idx = i
    block = lines[idx + 1:] if idx >= 0 and idx + 1 < len(lines) else (lines if idx < 0 else lines[idx:])
    return " / ".join(l.strip() for l in block[:n])


def prompt_texts(r):
    return [p["prompt"].strip() for p in r.get("prompts", [])]


def reproduce(r):
    if r["flow"].startswith("real:"):
        return "on this server run:  %s%s" % (r["flow"][5:], ("   (answers: " + " | ".join(r["answers"]) + ")") if r["answers"] else "")
    if r["flow"].startswith("other:"):
        return "layout: %s; run:  %s%s" % (r["layout"], r["flow"][6:], ("   (answers: " + " | ".join(r["answers"]) + ")") if r["answers"] else "")
    bits = ["layout: %s" % r["layout"]]
    if r.get("pre"):
        bits.append("before the command: " + ", ".join(r["pre"]))
    bits.append("command: sudo drives %s" % " ".join(r["args"]) if r["args"] else "command: sudo drives")
    if r["answers"]:
        bits.append("answers typed, in order: " + " | ".join(repr(a) if a == "" or a.strip() != a else a for a in r["answers"]))
    else:
        bits.append("answers: none (Enter at the first question)")
    if r.get("fault"):
        bits.append("then, after answer %s: %s" % tuple(r["fault"]))
    return "; ".join(bits)


def findings(R):
    groups = collections.OrderedDict()
    for r in R:
        flags = list(r["flags"])
        if r["outcome"] == "BUILD-FAIL":
            flags = ["layout could not be built: " + (r["note"] or "")[:120]]
        for fl in flags:
            sev = severity_of(r, fl)
            key = (r["flow"], sev, norm(fl)[:120], r.get("note", "")[:0])
            g = groups.setdefault(key, {"flow": r["flow"], "severity": sev, "flag": fl, "runs": [], "layouts": set()})
            g["runs"].append(r)
            g["layouts"].add(r["layout"])
    out = []
    for g in groups.values():
        ex = min(g["runs"], key=lambda r: (len(r["answers"]), len(r.get("pre", [])), len(r["output"])))
        out.append({
            "severity": g["severity"], "flow": g["flow"], "problem": g["flag"], "count": len(g["runs"]),
            "layouts": sorted(g["layouts"]), "example": reproduce(ex), "example_id": ex["id"],
            "what_you_see": last_lines(ex["output"], 7, prompt_texts(ex)) if ex["flow"].startswith(("real:", "other:")) else last_lines(ex["output"], 7), "note": ex.get("note", ""),
        })
    out.sort(key=lambda f: (SEVERITY[f["severity"]], -f["count"]))
    return out


# ---------------------------------------------------------------------------------------------------------------- grid
CELL_ORDER = ["BUG", "DONE", "REFUSED", "CANCELLED", "NOTHING", "OK"]


def cell_state(rs):
    if not rs:
        return "none"
    bug = any(r["outcome"] in ("CRASH", "SILENT-FAIL", "BUILD-FAIL") or any(f.startswith("INV-") for f in r["flags"]) for r in rs)
    if bug:
        return "BUG"
    if any(r["outcome"] == "DONE" for r in rs):
        return "DONE"
    if any(r["outcome"] == "REFUSED" for r in rs):
        return "REFUSED"
    if any(r["outcome"] in ("NOTHING", "OK") for r in rs):
        return "OK"
    return "CANCELLED"


def grid(R, flows_order):
    layouts = []
    cells = collections.defaultdict(list)
    for r in R:
        if r["flow"].startswith(("real:", "other:", "wish", "cli", "build")) or r["layout"] == "this server":
            continue
        if r["layout"] not in layouts:
            layouts.append(r["layout"])
        cells[(r["layout"], r["flow"])].append(r)
    flows = [f for f in flows_order if any(k[1] == f for k in cells)]
    return layouts, flows, cells


# ---------------------------------------------------------------------------------------------------------------- messages
def refusal_messages(R):
    """For every flow: the explanations printed when a command did not do what was asked, and where."""
    msgs = collections.OrderedDict()
    for r in R:
        if r["outcome"] not in ("REFUSED",) or r["flow"].startswith(("real:", "wish")):
            continue
        text = r["msg"] or message_block(r)
        key = (r["flow"], norm(text)[:200])
        m = msgs.setdefault(key, {"flow": r["flow"], "text": text[:300], "layouts": set(), "count": 0, "example": r})
        m["layouts"].add(r["layout"])
        m["count"] += 1
    return sorted(msgs.values(), key=lambda m: (m["flow"], -m["count"]))


def prompt_map(R):
    """Every question each command asked, how often it was reached and what was answered."""
    pm = collections.OrderedDict()
    for r in R:
        if r["flow"].startswith(("real:", "other:", "wish", "cli", "build")):
            continue
        for p in r["prompts"]:
            key = (r["flow"], norm(p["prompt"])[:150], p["kind"])
            m = pm.setdefault(key, {"flow": r["flow"], "prompt": p["prompt"].strip(), "kind": p["kind"], "reached": 0, "answers": collections.Counter(),
                                    "items": p["items"]})
            m["reached"] += 1
            m["answers"][p["answer"]] += 1
    return list(pm.values())


# ---------------------------------------------------------------------------------------------------------------- what works
def of(R, flow, **kw):
    out = []
    for r in R:
        if r["flow"] != flow:
            continue
        if "pre" in kw and bool(r.get("pre")) != kw["pre"]:
            continue
        out.append(r)
    return out


def ans_at(r, prompt_start, value=None):
    for p in r["prompts"]:
        if p["prompt"].startswith(prompt_start) and p["answer"] != "<EOF>":
            if value is None or p["answer"] == value:
                return True
    return False


def capabilities(R, meta):
    caps = []

    def add(title, rs, ok_words, how_found, none_msg, ok=("DONE",)):
        done = [r for r in rs if r["outcome"] in ok]
        refused = [r for r in rs if r["outcome"] == "REFUSED"]
        bug = [r for r in rs if r["outcome"] in ("CRASH", "SILENT-FAIL") or any(f.startswith("INV-") for f in r["flags"])]
        lays = sorted({r["layout"] for r in done})
        if not rs:
            caps.append({"title": title, "status": "NOT TESTED", "detail": none_msg})
            return
        if bug and done:
            status = "WORKS, WITH PROBLEMS"
        elif bug:
            status = "BROKEN"
        elif done:
            status = "WORKS"
        elif refused:
            status = "REFUSED EVERY TIME"
        else:
            status = "NOT REACHED"
        d = "worked in %d layout(s)" % len(lays) if done else "never completed"
        if refused:
            d += "; refused in %d run(s) in %d layout(s)" % (len(refused), len({r['layout'] for r in refused}))
        if bug:
            d += "; %d run(s) with problems" % len(bug)
        caps.append({"title": title, "status": status, "detail": d, "layouts": lays[:6]})

    c = of(R, "connect", pre=False)
    add("Connect a drive to the Main pool", [r for r in c if ans_at(r, "Use this drive for", "1")], 0, "", "no run reached the question")
    add("Connect a drive to the Backup pool", [r for r in c if ans_at(r, "Use this drive for", "2")], 0, "", "no run reached the question")
    add("Connect a drive that already has files, keeping them", [r for r in c if ans_at(r, "What should I do?", "1")], 0, "", "needs a spare drive with an ext4 partition")
    add("Connect a drive that already has files, erasing it", [r for r in c if ans_at(r, "What should I do?", "2")], 0, "", "needs a spare drive with an ext4 partition")
    nosp = [r for r in R if r["flow"] == "connect" and "nospare" in r["layout"]]
    add("Connect when no spare drive is plugged in (a clear message)", nosp, 0, "", "layout not run")
    d = of(R, "disconnect", pre=False)
    add("Disconnect a drive and copy its files to the others first", [r for r in d if ans_at(r, "Copy them to another", "y")], 0, "", "no run reached the question")
    add("Disconnect a drive without copying its files", [r for r in d if ans_at(r, "Type CONTINUE to confirm")], 0, "", "no run reached the question")
    add("Disconnect the last Backup drive (typing REMOVE)", [r for r in d if ans_at(r, "Type REMOVE")], 0, "", "no run reached the question")
    add("Move a drive between Main and Backup", of(R, "move", pre=False), 0, "", "not run")
    add("Replace a dead drive (restores its files from the backup)", of(R, "replace", pre=True), 0, "", "needs the unplug scenarios")
    add("Recover after an unplug or power cut", of(R, "recover", pre=True), 0, "", "needs the unplug scenarios", ok=("DONE", "NOTHING"))
    add("Recover when nothing is wrong", of(R, "recover", pre=False), 0, "", "not run", ok=("DONE", "NOTHING"))
    add("Use part of the boot drive as a pool drive", of(R, "bootsection", pre=False), 0, "", "not run")
    add("Take all drives out of the pools", of(R, "release", pre=False), 0, "", "not run")
    add("Copy back only the missing files from the backup", of(R, "restore", pre=False), 0, "", "not run")
    add("Convert the old single data drive into a pool", of(R, "adopt", pre=False), 0, "", "needs the legacy layout")
    add("Make an older pool fill drive by drive", of(R, "fillorder", pre=False), 0, "", "needs the old-pool layout", ok=("DONE", "NOTHING"))
    add("Apply the power settings (test mode only prints; hdparm is not run)", of(R, "power", pre=False), 0, "", "not run", ok=("DONE", "NOTHING"))
    add("Show the status", of(R, "status", pre=False), 0, "", "not run", ok=("DONE", "NOTHING"))
    add("List the drives", of(R, "list", pre=False), 0, "", "not run", ok=("DONE", "NOTHING"))
    add("Show space used and free", of(R, "usage", pre=False), 0, "", "not run", ok=("DONE", "NOTHING"))
    add("Show the health of every drive (SMART)", of(R, "health", pre=False), 0, "", "not run", ok=("DONE", "NOTHING"))
    add("Quick check for file system errors", of(R, "check", pre=False), 0, "", "not run", ok=("DONE", "NOTHING"))
    add("Full read-only scan of one drive", of(R, "scan", pre=False), 0, "", "not run", ok=("DONE", "NOTHING"))
    add("Walk through the menu", of(R, "menu", pre=False), 0, "", "not run", ok=("DONE", "NOTHING", "CANCELLED"))
    return caps


def what_you_see_lines(r, n=7):
    return last_lines(r["output"], n, prompt_texts(r))


def wishes(R):
    out = []
    for r in R:
        if r["flow"] != "wish":
            continue
        word, _, what = r["note"].partition(": ")
        usage = ("Usage:" in r["output"] or "Unknown command" in r["output"]) and not r["changed"]
        out.append({"word": word, "what": what, "supported": not usage, "output": last_lines(r["output"], 2)})
    return out


def cli_checks(R):
    return [r for r in R if r["flow"] == "cli"]


def static_scan(path):
    if not path or not os.path.exists(path):
        return {}
    t = open(path, errors="replace").read()
    return {
        "knows_about_backup": bool(re.search(r"homelab-backup\.lock|pgrep[^\n]*backup|flock[^\n]*backup", t)),
        "smart_only_when_connecting": len(re.findall(r"smartctl", t)) <= 3,
        "power_all_only": "power_all" in t and "power_one" not in t and "power_drive" not in t,
        "skips_in_test_mode": sorted(set(re.findall(r'\[ "\$TEST_MODE" (?:=|!=) 1 \][^\n]{0,80}', t)))[:12],
        "has_rename": bool(re.search(r"rename_flow|name_flow|rename\)", t)),
        "main_cmds": re.findall(r"^\s{4}([a-z-]+)\)\s+[a-z_]+", t, re.M),
    }


def no(w, *words):
    """True when at least one of these words was tried and `drives` did not know it."""
    return any(w.get(x) is False for x in words)


IDEAS = [
    # id, title, why, how, condition(wishes dict, cli list, scan, findings)
    ("rename", "Rename a drive from the menu", "A drive's name can only be set by editing a file; people would expect a 'Rename a drive' item.",
     "Add a rename flow that writes LABEL=Name into the names file, and a menu item under 'Add or remove drives'.",
     lambda w, c, s, f: no(w, "rename", "name")),
    ("smart", "Health (SMART) of every drive, any time", "SMART is only read when a drive is connected. `drives status` shows the column but nothing checks on request.",
     "Add `drives health` that runs smartctl for each pool drive, with the same two attempts (plain, -d sat) as `homelab-sample`.",
     lambda w, c, s, f: no(w, "smart", "health")),
    ("sleepwake", "Put one drive to sleep or wake it now", "The power settings are applied to all drives at once; there is no way to spin one drive down or wake it.",
     "Add `drives sleep LABEL` / `drives wake LABEL` using hdparm -y / a small read, and show the state in `drives status`.",
     lambda w, c, s, f: no(w, "sleep", "wake")),
    ("wipe", "Erase or format a drive that is not in a pool", "Only `connect` formats, and only to put the drive in a pool. A spare drive cannot be cleaned on its own.",
     "Add `drives wipe` that lists the unassigned drives and asks the same two typed confirmations as connect.",
     lambda w, c, s, f: no(w, "wipe", "format", "erase")),
    ("balance", "Even out the files over the drives", "The pool fills the first drive first. After adding a drive nothing moves; there is no way to spread files.",
     "Add `drives balance` using mergerfs.balance (or rsync between branches) with a preview and a stop button.",
     lambda w, c, s, f: no(w, "balance", "rebalance")),
    ("order", "Change the order drives fill in", "`fillorder` only converts an older pool. The order is the order of connecting; it cannot be changed.",
     "Add a menu item that moves a drive up or down in the pool line (reorder fstab branches, remount).",
     lambda w, c, s, f: no(w, "reorder", "priority")),
    ("limit", "Change how much free space a drive keeps", "The 5% limit is fixed (an environment setting). A person cannot change it per drive.",
     "Add `drives limit LABEL 10%` and write it into the pool line.", lambda w, c, s, f: no(w, "limit")),
    ("resize", "Change the size of a boot drive section", "The guide says: remove it and add it again. That drains and copies the files twice.",
     "Add a resize flow that grows the image file and runs resize2fs (shrinking needs a copy first).", lambda w, c, s, f: no(w, "resize")),
    ("fsck", "Check a drive's file system", "Nothing checks a drive that had an unclean unplug apart from the kernel's own replay.",
     "Add `drives check LABEL` that unmounts the drive, runs e2fsck -n (read-only) and shows the result.",
     lambda w, c, s, f: no(w, "fsck", "scrub")),
    ("list", "A short list for scripts (and --json)", "`status` prints a long human report only.", "Add `drives list` (one line per drive) and `drives status --json`.",
     lambda w, c, s, f: no(w, "list")),
    ("help", "Real help text", "`drives help`, `--help` and `-h` print only the one-line usage.",
     "Print the list of commands with one sentence each (the menu already has the sentences).",
     lambda w, c, s, f: any(x["note"] in ("help word", "--help", "-h") and "Usage:" in x["output"] and len(x["output"].strip().splitlines()) <= 2 for x in c)),
    ("noninteractive", "Run without questions (--yes, a drive and a pool on the command line)", "`drives connect /dev/sdb main` still asks every question; `connect_flow` already accepts a device and pool inside.",
     "Pass the arguments to connect_flow and add --yes for the typed confirmations (keep the ERASE confirmation unless --force-erase is given).",
     lambda w, c, s, f: any(x["note"] == "connect with a device and a pool" and x["prompts"] for x in c)),
    ("dryrun", "A dry run (--dry-run) for every change", "The installer has one; the drive tool shows what it will do only through its own questions.",
     "Print the steps (fstab lines, mounts, containers to stop) and exit before the first change.", lambda w, c, s, f: any(x["note"] == "--dry-run" and ("Usage:" in x["output"] or "Unknown command" in x["output"]) for x in c)),
    ("exitcodes", "Exit code 1 when a command is refused", "Commands that refuse ('is the only main drive', 'No new drive found') exit with 0, so a script cannot tell.",
     "Make each flow's refusal end with `exit 1` (the dispatcher already runs `sync_filebrowser` after, which hides the code).",
     lambda w, c, s, f: any(x["severity"] == "LOW" and x["problem"].startswith("exit 0 although") for x in f)),
    ("backupaware", "Wait or warn when a backup or an upload is running", "disconnect, move, release, recover and replace stop containers and unmount pools with no check; `homelab-update` has one.",
     "Reuse `busy_reason` from homelab-update: before stopping containers, say 'a backup is running' and ask to wait.",
     lambda w, c, s, f: s and not s.get("knows_about_backup", True)),
    ("testmode", "Make the power and health steps testable", "In test mode power_apply, smart_health, udisksctl and the Homepage/FileBrowser sync are skipped, so the bench cannot see if they work.",
     "Let them run against the bench's fake hdparm/smartctl when DRIVES_TEST=1 and a HOMELAB_EXTRA_PATH fake is present.",
     lambda w, c, s, f: True),
]


def ideas(R, scan, fnds):
    w = {x["word"]: x["supported"] for x in wishes(R)}
    c = cli_checks(R)
    out = []
    for iid, title, why, how, cond in IDEAS:
        try:
            if cond(w, c, scan, fnds):
                out.append({"id": iid, "title": title, "why": why, "how": how})
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------------------------------------------- other commands
def others(R):
    rows = []
    for r in R:
        if r["flow"].startswith(("real:", "other:")):
            rows.append(r)
    return rows


# ---------------------------------------------------------------------------------------------------------------- output
FLOW_ORDER = ["menu", "status", "list", "usage", "health", "check", "scan", "connect", "disconnect", "move", "adopt", "power", "recover", "replace", "fillorder", "release", "bootsection", "restore"]


def stats(R):
    c = collections.Counter(r["outcome"] for r in R)
    return c


def text_report(R, meta, fnds, caps, wl, scan, ide, lay, flows, cells, refs, pm, oth):
    o = []

    def p(*a):
        o.append(" ".join(str(x) for x in a))

    def h(t):
        o.append("")
        o.append("=" * 110)
        o.append(t)
        o.append("=" * 110)

    st = stats(R)
    p("DRIVE-BENCH REPORT")
    p("level: %s    drives script: %s    runs: %d    layouts: %d    other commands: %d" % (
        meta.get("level", "?"), meta.get("drives", "?"), len(R), len(lay), len(oth)))
    p("outcomes: " + ", ".join("%s %d" % (k, v) for k, v in st.most_common()))
    h("1. PROBLEMS (most serious first)")
    if not fnds:
        p("No problems found.")
    sev = collections.Counter(f["severity"] for f in fnds)
    p("HIGH %d   MEDIUM %d   LOW %d   INFO %d" % (sev["HIGH"], sev["MEDIUM"], sev["LOW"], sev["INFO"]))
    for i, f in enumerate(fnds, 1):
        p("")
        p("[%s] #%d  %s  -  %s" % (f["severity"], i, f["flow"], f["problem"]))
        p("    seen %d time(s) in %d layout(s): %s%s" % (f["count"], len(f["layouts"]), ", ".join(f["layouts"][:8]), " ..." if len(f["layouts"]) > 8 else ""))
        p("    how to reproduce: " + f["example"])
        if f["note"]:
            p("    scenario: " + f["note"])
        for l in f["what_you_see"].splitlines():
            p("      | " + l)
    h("2. WHAT WORKS AND WHAT DOES NOT")
    for c in caps:
        p("%-22s %s" % (c["status"], c["title"]))
        p("%-22s   %s" % ("", c["detail"]))
    p("")
    if wl:
        p("Words people might expect (typed as `sudo drives WORD`):")
    for x in wl:
        p("  %-14s %-14s %s" % (x["word"], "supported" if x["supported"] else "NOT SUPPORTED", x["what"]))
    h("3. WHAT IS REFUSED, AND WHY (the messages people see)")
    cur = None
    for m in refs:
        if m["flow"] != cur:
            cur = m["flow"]
            p("")
            p("[%s]" % cur)
        p("  %3dx  %s" % (m["count"], m["text"].replace("\n", " ")))
        p("        in: " + ", ".join(sorted(m["layouts"])[:8]) + (" ..." if len(m["layouts"]) > 8 else ""))
    h("4. LAYOUT x COMMAND  (D = completed, R = refused with a message, B = bug, o = ran without changes, c = cancelled, . = not run)")
    sym = {"BUG": "B", "DONE": "D", "REFUSED": "R", "OK": "o", "CANCELLED": "c", "none": "."}
    p("%-26s " % "layout" + " ".join("%-4s" % f[:4] for f in flows))
    for l in lay:
        p("%-26s " % l + " ".join("%-4s" % sym[cell_state(cells.get((l, f), []))] for f in flows))
    h("5. EVERY QUESTION THE COMMANDS ASKED")
    cur = None
    for m in pm:
        if m["flow"] != cur:
            cur = m["flow"]
            p("")
            p("[%s]" % cur)
        ans = ", ".join("%r x%d" % (a, n) for a, n in m["answers"].most_common(8))
        p("  (%s, reached %d times) %s" % (m["kind"], m["reached"], m["prompt"][:120].replace("\n", " ")))
        if m["items"]:
            p("      choices: " + " | ".join(i[:48] for i in m["items"][:6]))
        p("      answers tried: " + ans)
    h("6. THE OTHER COMMANDS")
    for r in oth:
        p("%-12s %-52s rc=%-3s %5.1fs  %s" % (r["outcome"], r["flow"][:52] + (" @ " + r["layout"] if r["layout"] != "this server" else ""), r["rc"], r["secs"],
                                          "; ".join(r["flags"])[:90]))
    h("7. IDEAS TO ADD (what a full set of drive controls still needs)")
    for i, x in enumerate(ide, 1):
        p("%d. %s" % (i, x["title"]))
        p("   why: " + x["why"])
        p("   how: " + x["how"])
    h("8. NOT COVERED BY TEST MODE")
    for t in scan.get("skips_in_test_mode", []):
        p("  " + t)
    p("The bench cannot see: real hdparm power settings, SMART readings, udisksctl power-off, the Homepage and FileBrowser sync after a change.")
    slow = sorted(R, key=lambda r: -r["secs"])[:8]
    h("9. SLOWEST RUNS")
    for r in slow:
        p("%6.1fs  %-12s %s" % (r["secs"], r["flow"], r["layout"]))
    return "\n".join(o) + "\n"


def esc(x):
    return html.escape(str(x))


def html_report(R, meta, fnds, caps, wl, scan, ide, lay, flows, cells, refs, pm, oth):
    st = stats(R)
    sev = collections.Counter(f["severity"] for f in fnds)
    css = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2230;--mute:#667085;--line:#e3e6ec;--hi:#c0332b;--med:#c27a0a;--low:#587ea8;--ok:#2f8f4e;--ref:#c8a03a;--none:#d9dde5}
@media (prefers-color-scheme:dark){:root{--bg:#10141c;--card:#171c27;--ink:#e6e9ef;--mute:#9aa3b2;--line:#283041;--hi:#ff6b62;--med:#e3a43a;--low:#7fa8d6;--ok:#58c47a;--ref:#d9b755;--none:#2b3344}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
main{max-width:1200px;margin:0 auto;padding:24px 16px 80px}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:34px 0 10px}
.sub{color:var(--mute);margin-bottom:18px}.cards{display:flex;gap:10px;flex-wrap:wrap}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;min-width:130px}
.card b{display:block;font-size:24px}.hi b{color:var(--hi)}.med b{color:var(--med)}.low b{color:var(--low)}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;font-size:14px}th{background:var(--bg);font-weight:600}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;color:#fff}.HIGH{background:var(--hi)}.MEDIUM{background:var(--med)}.LOW{background:var(--low)}.INFO{background:var(--mute)}
.WORKS{background:var(--ok)}.BROKEN{background:var(--hi)}.REFUSED{background:var(--ref)}.PROB{background:var(--med)}.NOT{background:var(--none);color:var(--ink)}
.grid td,.grid th{text-align:center;padding:4px 6px;font-size:12px}.grid td.l{text-align:left;font-weight:600}
.c-BUG{background:var(--hi);color:#fff}.c-DONE{background:var(--ok);color:#fff}.c-REFUSED{background:var(--ref);color:#222}.c-OK{background:color-mix(in srgb,var(--ok) 35%,var(--card))}.c-CANCELLED{background:color-mix(in srgb,var(--ref) 25%,var(--card))}.c-none{background:var(--none);color:var(--mute)}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;overflow:auto;font-size:12.5px;white-space:pre-wrap;margin:6px 0}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:8px 0}summary{cursor:pointer;font-weight:600}
.mute{color:var(--mute)}input,select{padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}.bar{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.scroll{overflow:auto}
"""
    o = ["<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Drive bench report</title><style>%s</style><main>" % css]
    o.append("<h1>Drive bench report</h1><div class=sub>level %s · %d runs · %d layouts · drives script %s</div>" % (
        esc(meta.get("level", "?")), len(R), len(lay), esc(meta.get("drives", "?"))))
    o.append("<div class=cards><div class='card hi'><b>%d</b>high</div><div class='card med'><b>%d</b>medium</div><div class='card low'><b>%d</b>low</div>" % (sev["HIGH"], sev["MEDIUM"], sev["LOW"]))
    for k, v in st.most_common(8):
        o.append("<div class=card><b>%d</b>%s</div>" % (v, esc(k.lower())))
    o.append("</div>")
    o.append("<h2>1. Problems</h2><div class=bar><select id=sevf><option value=''>All severities<option>HIGH<option>MEDIUM<option>LOW<option>INFO</select>"
             "<input id=txt placeholder='filter by command or text' size=30></div><div id=fl>")
    for i, f in enumerate(fnds, 1):
        o.append("<details data-sev=%s data-text='%s'><summary><span class='pill %s'>%s</span> #%d <b>%s</b> — %s <span class=mute>(%d run%s, %d layout%s)</span></summary>"
                 % (f["severity"], esc((f["flow"] + " " + f["problem"]).lower()), f["severity"], f["severity"], i, esc(f["flow"]), esc(f["problem"]),
                    f["count"], "" if f["count"] == 1 else "s", len(f["layouts"]), "" if len(f["layouts"]) == 1 else "s"))
        o.append("<p class=mute>Layouts: %s</p><p><b>How to reproduce:</b> %s</p>" % (esc(", ".join(f["layouts"][:12])), esc(f["example"])))
        if f["note"]:
            o.append("<p><b>Scenario:</b> %s</p>" % esc(f["note"]))
        o.append("<pre>%s</pre></details>" % esc(f["what_you_see"]))
    if not fnds:
        o.append("<p>No problems found.</p>")
    o.append("</div><h2>2. What works and what does not</h2><div class=scroll><table><tr><th>Status<th>Capability<th>Detail")
    cls = {"WORKS": "WORKS", "WORKS, WITH PROBLEMS": "PROB", "BROKEN": "BROKEN", "REFUSED EVERY TIME": "REFUSED", "NOT TESTED": "NOT", "NOT REACHED": "NOT"}
    for c in caps:
        o.append("<tr><td><span class='pill %s'>%s</span><td>%s<td class=mute>%s" % (cls.get(c["status"], "NOT"), esc(c["status"]), esc(c["title"]), esc(c["detail"])))
    o.append("</table></div>")
    if wl:
        o.append("<h3>Words people might expect (<code>sudo drives WORD</code>)</h3><div class=scroll><table><tr><th>Word<th>Supported?<th>What it would do")
        for x in wl:
            o.append("<tr><td><code>%s</code><td>%s<td>%s" % (esc(x["word"]), "yes" if x["supported"] else "<span class='pill NOT'>no</span>", esc(x["what"])))
        o.append("</table></div>")
    o.append("<h2>3. Layout × command</h2><p class=mute>D completed · R refused with a message · B bug · o ran, no change · c cancelled · empty = not run. Hover for counts.</p><div class=scroll><table class=grid><tr><th>layout")
    for f in flows:
        o.append("<th>%s" % esc(f))
    for l in lay:
        o.append("<tr><td class=l>%s" % esc(l))
        for f in flows:
            rs = cells.get((l, f), [])
            s = cell_state(rs)
            sym = {"BUG": "B", "DONE": "D", "REFUSED": "R", "OK": "o", "CANCELLED": "c", "none": ""}[s]
            tip = "%d runs: %s" % (len(rs), ", ".join("%s %d" % (k, v) for k, v in collections.Counter(r["outcome"] for r in rs).most_common()))
            o.append("<td class='c-%s' title='%s'>%s" % (s, esc(tip), sym))
    o.append("</table></div><h2>4. What is refused, and why</h2><div class=scroll><table><tr><th>Command<th>Message<th>Times<th>Layouts")
    for m in refs:
        o.append("<tr><td>%s<td>%s<td>%d<td class=mute>%s" % (esc(m["flow"]), esc(m["text"]), m["count"], esc(", ".join(sorted(m["layouts"])[:6]))))
    o.append("</table></div><h2>5. Every question the commands asked</h2>")
    cur = None
    for m in pm:
        if m["flow"] != cur:
            if cur is not None:
                o.append("</table></details>")
            cur = m["flow"]
            o.append("<details><summary>%s</summary><table><tr><th>Kind<th>Question<th>Reached<th>Answers tried" % esc(cur))
        o.append("<tr><td>%s<td>%s%s<td>%d<td class=mute>%s" % (esc(m["kind"]), esc(m["prompt"][:140]),
                 ("<br><span class=mute>" + esc(" | ".join(i[:40] for i in m["items"][:5])) + "</span>") if m["items"] else "",
                 m["reached"], esc(", ".join("%r×%d" % (a, n) for a, n in m["answers"].most_common(8)))))
    if cur is not None:
        o.append("</table></details>")
    o.append("<h2>6. The other commands</h2><div class=scroll><table><tr><th>Result<th>Command<th>Where<th>Exit<th>Seconds<th>Notes")
    for r in oth:
        o.append("<tr><td>%s<td>%s<td>%s<td>%s<td>%.1f<td class=mute>%s" % (esc(r["outcome"]), esc(r["flow"]), esc(r["layout"]), r["rc"], r["secs"],
                                                                      esc("; ".join(r["flags"] + ([r["note"]] if r["note"] else []))[:200])))
    o.append("</table></div><h2>7. Ideas to add</h2>")
    for i, x in enumerate(ide, 1):
        o.append("<details><summary>%d. %s</summary><p><b>Why:</b> %s</p><p><b>How:</b> %s</p></details>" % (i, esc(x["title"]), esc(x["why"]), esc(x["how"])))
    o.append("<h2>8. Not covered by test mode</h2><pre>%s</pre>" % esc("\n".join(scan.get("skips_in_test_mode", []))))
    o.append("""<script>
const f=document.getElementById('sevf'),t=document.getElementById('txt');
function ap(){const s=f.value,q=t.value.toLowerCase();document.querySelectorAll('#fl details').forEach(d=>{d.style.display=((!s||d.dataset.sev===s)&&(!q||d.dataset.text.includes(q)))?'':'none'})}
f.onchange=ap;t.oninput=ap;</script></main>""")
    return "\n".join(o)


def build(results, out_dir):
    all_rows = load(results)
    meta = {}
    meta_path = os.path.join(os.path.dirname(results), "meta.json")
    if os.path.exists(meta_path):
        meta = json.load(open(meta_path))
    R = [r for r in all_rows if "id" in r]
    fnds = findings(R)
    lay, flows, cells = grid(R, FLOW_ORDER)
    scan = static_scan(meta.get("drives"))
    caps = capabilities(R, meta)
    wl = wishes(R)
    ide = ideas(R, scan, fnds)
    refs = refusal_messages(R)
    pm = prompt_map(R)
    oth = others(R)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "report.txt"), "w") as f:
        f.write(text_report(R, meta, fnds, caps, wl, scan, ide, lay, flows, cells, refs, pm, oth))
    with open(os.path.join(out_dir, "report.html"), "w") as f:
        f.write(html_report(R, meta, fnds, caps, wl, scan, ide, lay, flows, cells, refs, pm, oth))
    with open(os.path.join(out_dir, "findings.json"), "w") as f:
        json.dump({"findings": fnds, "capabilities": caps, "wishes": wl, "ideas": ide}, f, indent=1)
    print("report written to", out_dir)
