#!/usr/bin/env python3
"""A fake `drives` for the panel tests: it only records the words it was given (FAKE_DRIVES_LOG) and answers like the real one.
FAKE_DRIVES_MODE: ok (default) | nosudo (sudo wants a password) | busy (remount is refused) | slow (remount takes 2 seconds) | bad (not JSON)
| slowhealth (health takes 2 seconds) | single (each pool has just one drive) | jobslow (add / wipe / disconnect / move print progress lines for a few seconds) | jobfail (they end with a refusal, exit 1) | jobbusy (they are refused with Not a good moment unless the word NOW is among the words) | twospares (a second spare drive is plugged in) | tight (the other Main drive is nearly full) | bootsec (a boot drive section is in Backup) | bootlend (the boot drive can lend space, no section yet)."""
import json
import os
import sys
import time

args = sys.argv[1:]
with open(os.environ["FAKE_DRIVES_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
mode = os.environ.get("FAKE_DRIVES_MODE", "ok")
if mode == "nosudo":
    sys.stderr.write("sudo: a password is required\n")
    sys.exit(1)
if args[:1] != ["panel"] or len(args) < 2:
    sys.stderr.write("Unknown panel command. Nothing was changed.\n")
    sys.exit(1)
act = args[1]
if mode == "bad":
    print("this is not json")
    sys.exit(0)
SPARE2_DRIVE = {"name": "32 GB Kingston HDD", "role": "spare", "device": "/dev/sde", "size_bytes": 32000000000, "used_bytes": None, "free_bytes": None, "state": "not connected to a pool", "mount": ""}
SPARE2_ACTION = {"id": "sde", "device": "/dev/sde", "name": "32 GB Kingston HDD", "size_bytes": 32000000000, "keep_ok": False, "partitions": 2}
if act == "status":
    STATUS = ({"pools": [{"role": "main", "path": "/mnt/storage", "mounted": True, "filesystem": "fuse.mergerfs", "size_bytes": 2000000000000, "used_bytes": 500000000000, "free_bytes": 1500000000000},
                                {"role": "backup", "path": "/mnt/backup", "mounted": False, "filesystem": "", "size_bytes": None, "used_bytes": None, "free_bytes": None}],
                      "drives": [{"name": "1 TB Toshiba HDD", "role": "main", "device": "/dev/sdb1", "size_bytes": 1000000000000, "used_bytes": 250000000000, "free_bytes": 750000000000, "state": "connected", "mount": "/mnt/disks/MAIN1"},
                                 {"name": "2 TB Seagate HDD", "role": "backup", "device": "-", "size_bytes": None, "used_bytes": None, "free_bytes": None, "state": "MISSING", "mount": "/mnt/disks/BACKUP1"},
                                 {"name": "2 TB Seagate HDD 2", "role": "main", "device": "/dev/sdd1", "size_bytes": 2000000000000, "used_bytes": 0, "free_bytes": 2000000000000, "state": "connected", "mount": "/mnt/disks/MAIN2"},
                                 {"name": "63 GB Cruzer HDD", "role": "spare", "device": "/dev/sdc", "size_bytes": 63100000000, "used_bytes": None, "free_bytes": None, "state": "not connected to a pool", "mount": ""}],
                      "last_backup": "Never", "boot_free_bytes": 40000000000})
    if "twospares" in mode:
        STATUS["drives"].append(SPARE2_DRIVE)
    if "tight" in mode:
        STATUS["drives"][2].update(used_bytes=1999000000000, free_bytes=1000000000)
    if "bootsec" in mode or "bootlend" in mode:
        STATUS["boot_limits"] = {"min_bytes": 10000000000, "max_bytes": 30000000000, "unit_bytes": 1000000000, "unit": "GB", "small": False, "main": False, "backup": "bootsec" in mode}
    if "bootsec" in mode:
        STATUS["drives"].append({"name": "546 GB boot drive section", "role": "backup", "device": "boot drive", "size_bytes": 536000000000, "used_bytes": 12000000000, "free_bytes": 524000000000, "state": "connected (used last)", "mount": "/mnt/disks/BACKUPBOOT"})
    print(json.dumps(STATUS))
elif act == "actions":
    ACTIONS = ({"rename": [{"id": "MAIN1", "name": "1 TB Toshiba HDD", "role": "main", "custom": False, "connected": True, "others": 0 if mode == "single" else 1, "has_data": True, "boot_section": False, "used_bytes": 250000000000},
                                 {"id": "BACKUP1", "name": "Old Backup", "role": "backup", "custom": True, "connected": False, "others": 0, "has_data": False, "boot_section": False, "used_bytes": 0},
                                 {"id": "MAIN2", "name": "2 TB Seagate HDD 2", "role": "main", "custom": False, "connected": True, "others": 0 if mode == "single" else 1, "has_data": False, "boot_section": False, "used_bytes": 0}],
                      "spare": [{"id": "sdc", "device": "/dev/sdc", "name": "63 GB Cruzer HDD", "size_bytes": 63100000000, "keep_ok": True, "partitions": 1}],
                      "power": [{"id": "sdb", "name": "1 TB Toshiba HDD", "role": "main", "state": "awake"}], "can_sleep": True})
    if "twospares" in mode:
        ACTIONS["spare"].append(SPARE2_ACTION)
    if "bootsec" in mode:
        ACTIONS["rename"].append({"id": "BACKUPBOOT", "name": "546 GB boot drive section", "role": "backup", "custom": False, "connected": True, "others": 0 if "alone" in mode else 1, "has_data": True, "boot_section": True, "used_bytes": 12000000000})
    print(json.dumps(ACTIONS))
elif act == "health":
    if mode == "slowhealth":
        time.sleep(2)
    print(json.dumps({"drives": [{"name": "1 TB Toshiba HDD", "device": "/dev/sdb", "model": "TOSHIBA DT01ACA100", "serial": "X7ABCDEF", "health": "FAILED", "temperature_c": 61, "power_on_hours": 12345, "reallocated_sectors": 3, "pending_sectors": 2, "note": "the drive says it is failing: back up its files now"}], "ok": False}))
    sys.exit(1)
elif act == "check":
    print(json.dumps({"drives": [{"name": "1 TB Toshiba HDD", "device": "/dev/sdb1", "result": "ok", "findings": []},
                                 {"name": "Old Backup", "device": "-", "result": "problem", "findings": [{"level": "problem", "text": "it is not connected or not mounted"}]}], "ok": False}))
    sys.exit(1)
elif act == "remount":
    if mode == "busy":
        sys.stderr.write("Not a good moment: a backup is running right now. Nothing was changed. Try again when it has finished.\n")
        sys.exit(1)
    if mode == "slow":
        time.sleep(2)
    print("Recovered.")
elif act in ("add", "wipe", "disconnect", "move"):
    ids = [t.split(":")[0] for t in args[2].split(",")] if act != "wipe" else [args[2]]
    if mode == "jobbusy" and "NOW" not in args:
        sys.stderr.write("Not a good moment: files are being written to a storage pool (an upload?). Nothing was changed. Try again when it has finished.\n")
        sys.exit(1)
    if "jobslow" in mode:
        flag = os.environ["FAKE_DRIVES_LOG"]
        open(flag + ".running", "w").close()
        if os.path.exists(flag + ".abort"):
            os.remove(flag + ".abort")
        for it in ids:
            for i in range(1, 5):
                print("PROGRESS %s %d Copying files %d%%" % (it, i * 22, i * 25), flush=True)
                print("Copying files, step %d of 4..." % i, flush=True)
                time.sleep(0.7)
                if os.path.exists(flag + ".abort"):
                    os.remove(flag + ".abort")
                    os.remove(flag + ".running")
                    print("PROGRESS %s 0 Stopped" % it, flush=True)
                    print("Stopped as you asked. Stopped with nothing lost: %s." % it, flush=True)
                    sys.exit(4)
        os.remove(flag + ".running")
    if mode == "jobfail":
        sys.stderr.write("Cancelled. Nothing was changed.\n")
        sys.exit(1)
    print("Done. 63 GB Cruzer HDD was %s." % {"add": "added", "wipe": "erased", "disconnect": "taken out of its pool", "move": "moved"}[act])
elif act == "setups":
    def opt(i, title, fits, usable, tol, drives, why="", kind="pool", nightly=False, mn=2):
        return {"id": i, "title": title, "blurb": "About " + title + ".", "kind": kind, "fits": fits, "min": mn, "drives": drives, "usable_bytes": usable, "used_bytes": usable * 2,
                "tolerates": tol, "nightly": nightly, "score": 600, "can_build": fits and not why, "why": why if fits else "Needs %d empty drives; 3 found." % mn, "needs_tool": False}
    block = "The Main storage still has drives in it. A new setup builds a new Main storage, so take the drives out of Main first." if "blocked" in mode else ""
    print(json.dumps({"spare": [{"id": "sdc", "device": "/dev/sdc", "name": "63 GB Cruzer HDD", "size_bytes": 63100000000, "blank": False, "keep_ok": True},
                                {"id": "sde", "device": "/dev/sde", "name": "32 GB Kingston HDD", "size_bytes": 32000000000, "blank": True},
                                {"id": "sdf", "device": "/dev/sdf", "name": "32 GB Kingston HDD 2", "size_bytes": 32000000000, "blank": True}],
                      "total_bytes": 127100000000, "current": "",
                      "recommended": "zfs-raidz1",
                      "options": [opt("zfs-raidz1", "ZFS, RAIDZ1 (1 drive can die)", True, 64000000000, 1, ["sdc", "sde", "sdf"], block, "zfs", mn=3),
                                  opt("snapraid1", "SnapRAID, 1 protection drive", True, 64000000000, 1, ["sdc", "sde", "sdf"], block, "pool", True, 3),
                                  opt("pool", "Plain pool", True, 127100000000, 0, ["sdc", "sde", "sdf"], block, "pool", False, 1),
                                  opt("zfs-raidz2", "ZFS, RAIDZ2 (2 drives can die)", False, 0, 0, [], "", "zfs", False, 4)],
                      }))
elif act == "bootadd":
    print("PROGRESS bootadd 50 Making the section")
    print("Done. The boot drive section was added.")
elif act == "setup":
    if "NOW" not in args and mode == "jobbusy":
        sys.stderr.write("Not a good moment: a backup is running right now. Nothing was changed. Try again when it has finished.\n")
        sys.exit(1)
    print("Setup: %s. Done. The setup is ready." % args[2])
elif act == "abort":
    if not os.path.exists(os.environ["FAKE_DRIVES_LOG"] + ".running"):
        sys.stderr.write("No drive change is running right now. Nothing was changed.\n")
        sys.exit(1)
    open(os.environ["FAKE_DRIVES_LOG"] + ".abort", "w").close()
    print("Stop requested. The drives are stopped at the next safe moment.")
elif act == "rename":
    print("Done. 1 TB Toshiba HDD is now called %s." % args[3])
elif act in ("sleep", "wake"):
    print("Done. 1 TB Toshiba HDD is %s." % ("asleep" if act == "sleep" else "awake"))
else:
    sys.stderr.write("Unknown panel command. Nothing was changed.\n")
    sys.exit(1)
