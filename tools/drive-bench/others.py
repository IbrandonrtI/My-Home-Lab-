"""The other commands of the project: homelab, homelab-sample, homelab-backup, homelab-update, homelab-restore-configs,
homelab-selftest, homelab-check, hdd-recover.

Two parts:
  1. layout runs   the commands that can be pointed at the fake pools (HOMELAB_* settings) run on every layout
  2. real runs     every command on THIS server, as it is (you chose "fully real"), in tiers:
        safe        only reads and prints (version, help, status, list ...)
        asks        the command is started and every question is answered "no" / Enter, so nothing is changed
        real        really does its job (a backup, a self-test, a recover, an update check ...)
        dangerous   would change the server for good (update --yes, restore, install, theme edits): NOT run, listed in the report
    Before the real runs the bench stops when a backup is running or files are being uploaded, and asks you to type a word.
"""
import os
import shutil
import subprocess
import sys
import time

import bench

# (id, tier, command, arguments, stdin answers, note)
REAL = [
    ("homelab", "safe", "homelab", [], "", "the login screen"),
    ("homelab status", "safe", "homelab", ["status"], "", ""),
    ("homelab commands", "safe", "homelab", ["commands"], "", ""),
    ("homelab docs", "safe", "homelab", ["docs"], "", ""),
    ("homelab login", "safe", "homelab", ["login"], "", ""),
    ("homelab version", "safe", "homelab", ["version"], "", ""),
    ("homelab help", "safe", "homelab", ["help"], "", ""),
    ("homelab unknown word", "safe", "homelab", ["bogus"], "", "must say what is wrong and exit 1"),
    ("homelab secrets", "safe", "homelab", ["secrets"], "", "prints a checklist, never the values"),
    ("homelab theme", "dangerous", "homelab", ["theme"], "", "edits the Homepage design files"),
    ("homelab bookmark", "dangerous", "homelab", ["bookmark"], "", "edits the Homepage bookmarks"),
    ("homelab-update version", "safe", "homelab-update", ["version"], "", ""),
    ("homelab-update help", "safe", "homelab-update", ["help"], "", ""),
    ("homelab-update list", "safe", "homelab-update", ["list"], "", ""),
    ("homelab-update unknown word", "safe", "homelab-update", ["bogus"], "", "must say what is wrong and exit 1"),
    ("homelab-update refresh", "real", "homelab-update", ["refresh"], "", "re-reads the list without the internet"),
    ("homelab-update check", "real", "homelab-update", ["check"], "", "looks online for newer images, downloads nothing"),
    ("homelab-update auto", "real", "homelab-update", ["auto"], "", "what cron runs"),
    ("homelab-update clean (answer no)", "asks", "homelab-update", ["clean"], "n\nn\nn\n", "shows what would be deleted and asks"),
    ("homelab-update (answer no to every stack)", "asks", "homelab-update", [], "n\nn\nn\nn\nn\nn\nn\nn\nn\nn\n",
     "downloads, then asks before each stack"),
    ("homelab-update --yes", "dangerous", "homelab-update", ["--yes"], "", "updates every stack for real"),
    ("homelab-update clean --yes", "dangerous", "homelab-update", ["clean", "--yes"], "", "deletes saved old versions"),
    ("homelab-restore-configs version", "safe", "homelab-restore-configs", ["version"], "", ""),
    ("homelab-restore-configs help", "safe", "homelab-restore-configs", ["help"], "", ""),
    ("homelab-restore-configs list", "safe", "homelab-restore-configs", ["list"], "", ""),
    ("homelab-restore-configs check", "safe", "homelab-restore-configs", ["check"], "", "preview only"),
    ("homelab-restore-configs unknown word", "safe", "homelab-restore-configs", ["bogus"], "", "must say what is wrong and exit 1"),
    ("homelab-restore-configs (answer no)", "asks", "homelab-restore-configs", [], "n\nn\nn\n", "shows what differs, asks before copying"),
    ("homelab-restore-configs volume (answer no)", "asks", "homelab-restore-configs", ["volume"], "n\nn\nn\n", ""),
    ("homelab-restore-configs restore", "dangerous", "homelab-restore-configs", ["restore"], "y\ny\ny\n", "overwrites config files"),
    ("homelab-sample version", "safe", "homelab-sample", ["version"], "", ""),
    ("homelab-sample help", "safe", "homelab-sample", ["help"], "", ""),
    ("homelab-sample unknown word", "safe", "homelab-sample", ["bogus"], "", "must say what is wrong and exit 1"),
    ("homelab-sample", "real", "homelab-sample", [], "", "takes the readings the login screen shows"),
    ("homelab-sample widgets", "real", "homelab-sample", ["widgets"], "", "rewrites the Homepage drive pills"),
    ("homelab-selftest version", "safe", "homelab-selftest", ["version"], "", ""),
    ("homelab-selftest help", "safe", "homelab-selftest", ["help"], "", ""),
    ("homelab-selftest", "real", "homelab-selftest", [], "", "checks the whole lab, writes a report file in your home"),
    ("homelab-check", "safe", "homelab-check", ["version"], "", ""),
    ("homelab-backup", "real", "homelab-backup", [], "", "the real daily backup"),
    ("hdd-recover", "real", "hdd-recover", [], "", "stops the containers, remounts the drives, starts them again"),
    ("drives status (real)", "safe", "drives", ["status"], "", "the real pools, read only"),
    ("drives version (real)", "safe", "drives", ["version"], "", ""),
    ("drives power (real)", "real", "drives", ["power"], "", "applies the real power settings"),
    ("drives bogus (real)", "safe", "drives", ["bogus"], "", ""),
    ("homelab-setup (no argument)", "safe", "homelab-setup", [], "", "the checklist screen"),
    ("homelab-setup help", "safe", "homelab-setup", ["help"], "", ""),
    ("homelab-setup install", "dangerous", "homelab-setup", ["install"], "", "the full installer"),
    ("homelab-setup refresh", "dangerous", "homelab-setup", ["refresh"], "", "re-runs steps of the installer"),
]

# commands that can run on a fake layout (settings point them at the fake pools)
LAYOUT_RUNS = [
    ("homelab status", "homelab", ["status"], ""),
    ("homelab login", "homelab", ["login"], ""),
    ("homelab-sample", "homelab-sample", [], ""),
    ("homelab-sample widgets", "homelab-sample", ["widgets"], ""),
    ("homelab-backup", "homelab-backup", [], ""),
    ("homelab-backup (second run)", "homelab-backup", [], ""),
]


def find(env, name):
    p = os.path.join(env.scripts, name)
    if os.path.exists(p):
        return p
    return shutil.which(name)


def interpreter(path):
    """bash for shell scripts, python for the python ones (homelab-check)."""
    try:
        first = open(path, errors="replace").readline()
    except OSError:
        first = ""
    return [sys.executable, path] if "python" in first else ["bash", path]


def run_plain(cmd, stdin, env_vars, timeout):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                           timeout=timeout, env=env_vars, cwd="/")
        return p.returncode, p.stdout, time.time() - t0, False
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return 124, out + "\n[drive-bench] timed out\n", time.time() - t0, True


def judge(rc, out, timed_out, expect_fail=False):
    outcome, flags, msg = bench.classify(rc, out, timed_out, [], False, "cli")
    if rc == 0 and outcome in ("NOTHING", "CANCELLED"):
        outcome = "OK"
    if rc == 0 and outcome == "DONE":
        outcome = "OK"
    if expect_fail and rc != 0 and outcome in ("REFUSED", "SILENT-FAIL"):
        outcome = "REFUSED"
    return outcome, flags, msg


def record(rec, cid, layout, flow, args, stdin, rc, out, secs, outcome, flags, msg, note, hide=False):
    rec.add({"id": cid, "layout": layout, "flow": flow, "args": args, "answers": [x for x in stdin.split("\n") if x], "fault": None,
             "note": note, "rc": rc, "secs": round(secs, 2), "outcome": outcome, "flags": flags, "msg": msg, "changed": False,
             "prompts": [], "output": "[output hidden: it may hold secrets]" if hide else bench.trim(out), "docker": [], "probe": None,
             "full": "[output hidden: it may hold secrets]" if hide else out})


def layout_pass(env, rec, layouts, log):
    """The commands that can follow the fake pools, on every layout."""
    for layout in layouts:
        if env.current != layout.key or env.dirty:
            if bench.build_layout(env, layout):
                continue
        for name, cmd, args, stdin in LAYOUT_RUNS:
            path = find(env, cmd)
            cid = "layout-other|%s|%s" % (layout.key, name)
            if not path or cid in rec.done:
                continue
            if env.dirty or env.current != layout.key:
                bench.restore_layout(env)
                env.current = layout.key
            conf = os.path.join(env.work, "backup.conf")
            state = os.path.join(env.work, "homelab-state")
            os.makedirs(state, exist_ok=True)
            with open(conf, "w") as f:
                f.write('SRC="%s"\nDEST_POOL="%s"\nLOGFILE="%s/backup.log"\nSTATUS_FILE="%s/last-run"\nCONFIG_PATHS=()\nMIN_FREE_GB=0\nNEXTCLOUD_DB_CONTAINER="nextcloud"\n'
                        % (env.main, env.backup, state, state))
            e = env.environ()
            e.update({"HOMELAB_MAIN_POOL": env.main, "HOMELAB_BACKUP_POOL": env.backup, "HOMELAB_DISKS_DIR": env.disks,
                      "HOMELAB_STATE_DIR": state, "HOMELAB_CACHE_DIR": os.path.join(state, "cache"),
                      "HOMELAB_BOOT_SECTION_DIR": os.path.join(env.state, "boot-sections"),
                      "HOMELAB_LAST_RUN_FILE": os.path.join(state, "last-run"), "BACKUP_CONF": conf,
                      "HOMELAB_USER": "root", "HOMELAB_ALLOW_ROOT": "1"})
            nolock = os.path.join(env.work, "nolock.sh")
            with open(nolock, "w") as f:
                f.write("flock() { return 0; }\n")     # a test run must not take the lock of the real backup
            e["BASH_ENV"] = nolock
            rc, out, secs, to = run_plain(interpreter(path) + args, stdin, e, 240)
            if cmd == "homelab-backup":   # the backup prints nothing to the screen: its reasons are in its log
                try:
                    out += "\n[backup log]\n" + "".join(open(os.path.join(state, "backup.log")).readlines()[-6:])
                    out += "[last-run] " + open(os.path.join(state, "last-run")).read()
                except OSError:
                    pass
            outcome, flags, msg = judge(rc, out, to)
            if cmd == "homelab-backup" and rc != 0 and "No space left on device" in out and "|FAILED" in out:
                flags = [f for f in flags if not f.startswith("bash-error")]         # a full backup drive: it failed, said so, and recorded it
                outcome = "REFUSED"
            fp = bench.fingerprint(env)
            if fp != env.base_fp:
                env.dirty = True
            record(rec, cid, layout.key, "other:" + name, args, stdin, rc, out, secs, outcome, flags, msg, "")
        bench.teardown(env)


def guard_real(env, log, yes):
    """Stop (and say why) when it is a bad moment: a backup is running, files are coming in."""
    lock = "/var/lock/homelab-backup.lock"
    r = subprocess.run("exec 7>%s && flock -n 7" % lock, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        log("A backup is running right now. The real commands will not start. Run the bench again when it has finished.")
        return False
    hu = find_script_for_busy(env)
    if hu:
        r = subprocess.run(["bash", "-c", 'HLU_SOURCE_ONLY=1 . "%s" 2>/dev/null; busy_reason' % hu], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, timeout=60)
        why = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        if why:
            log("It is a bad moment for the real commands: %s. Run the bench again later." % why)
            return False
    return True


def find_script_for_busy(env):
    return find(env, "homelab-update")


def run(env, rec, a, log):
    # 1. the commands that follow the fake pools
    if a.other_only or a.level != "quick":
        lay = bench.layouts_for(a.level, a.layout)
        pick = lay if a.level == "full" else lay[::3] + lay[-1:]
        log("other commands on %d fake layouts" % len(pick))
        layout_pass(env, rec, pick, log)
        if not getattr(a, "no_truth", False):
            import truth
            log("do the screens tell the truth? (known situations, on %d layouts)" % len(lay))
            truth.run_contract(env, rec, log)
            for layout in lay:
                if env.current != layout.key or env.dirty:
                    if bench.build_layout(env, layout):
                        continue
                truth.layout_truth(env, rec, layout, log)
    # 2. the real runs
    if a.real == "off":
        return
    tiers = ["safe"] if a.real == "safe" else ["safe", "asks", "real"]
    if a.real == "full":
        log("")
        log("REAL RUNS on this server: %s" % ", ".join(tiers))
        log("It will run a real backup, a real self-test and a real recover (containers stop for about a minute)")
        log("and start (but decline) updates and restores. Nothing marked 'dangerous' is run.")
        if not a.yes_real:
            try:
                word = input("Type REAL and press Enter to go on, or just Enter to run only the safe ones: ").strip()
            except EOFError:
                word = ""
            if word != "REAL":
                tiers = ["safe"]
        if tiers != ["safe"] and not guard_real(env, log, a.yes_real):
            tiers = ["safe"]
    for cid, tier, cmd, args, stdin, note in REAL:
        key = "real|%s" % cid
        if key in rec.done:
            continue
        path = find(env, cmd)
        if tier == "dangerous":
            record(rec, key, "this server", "real:" + cid, args, stdin, 0, "", 0, "NOT-RUN", ["dangerous: would change the server for good"],
                   "", note)
            continue
        if tier not in tiers:
            continue
        if not path:
            record(rec, key, "this server", "real:" + cid, args, stdin, 127, "", 0, "MISSING", ["command not found: %s" % cmd], "", note)
            continue
        e = dict(os.environ)
        e["LC_ALL"] = "C"
        hide = cid == "homelab secrets"
        rc, out, secs, to = run_plain(interpreter(path) + args, stdin, e, 900)
        expect_fail = "unknown word" in cid or "bogus" in cid
        outcome, flags, msg = judge(rc, out, to, expect_fail)
        if rc == 0 and expect_fail:
            outcome, flags = "SILENT-FAIL", flags + ["an unknown word was accepted with exit code 0"]
        log("  real %-46s %-10s %5.1fs" % (cid, outcome, secs))
        record(rec, key, "this server", "real:" + cid, args, stdin, rc, out, secs, outcome, flags, msg, "%s tier: %s" % (tier, note), hide)
