#!/usr/bin/env python3
"""A fake `drives` for the panel tests: it only records the words it was given (FAKE_DRIVES_LOG) and answers like the real one.
FAKE_DRIVES_MODE: ok (default) | nosudo (sudo wants a password) | busy (remount is refused) | slow (remount takes 2 seconds) | bad (not JSON)
| single (each pool has just one drive) | jobslow (add / wipe / disconnect / move print progress lines for a few seconds) | jobfail (they end with a refusal, exit 1)."""
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
if act == "status":
    print(json.dumps({"pools": [{"role": "main", "path": "/mnt/storage", "mounted": True, "filesystem": "fuse.mergerfs", "size_bytes": 2000000000000, "used_bytes": 500000000000, "free_bytes": 1500000000000},
                                {"role": "backup", "path": "/mnt/backup", "mounted": False, "filesystem": "", "size_bytes": None, "used_bytes": None, "free_bytes": None}],
                      "drives": [{"name": "1 TB Toshiba HDD", "role": "main", "device": "/dev/sdb1", "size_bytes": 1000000000000, "used_bytes": 250000000000, "free_bytes": 750000000000, "state": "connected", "mount": "/mnt/disks/MAIN1"},
                                 {"name": "2 TB Seagate HDD", "role": "backup", "device": "-", "size_bytes": None, "used_bytes": None, "free_bytes": None, "state": "MISSING", "mount": "/mnt/disks/BACKUP1"},
                                 {"name": "2 TB Seagate HDD 2", "role": "main", "device": "/dev/sdd1", "size_bytes": 2000000000000, "used_bytes": 0, "free_bytes": 2000000000000, "state": "connected", "mount": "/mnt/disks/MAIN2"},
                                 {"name": "63 GB Cruzer HDD", "role": "spare", "device": "/dev/sdc", "size_bytes": 63100000000, "used_bytes": None, "free_bytes": None, "state": "not connected to a pool", "mount": ""}],
                      "last_backup": "Never", "boot_free_bytes": 40000000000}))
elif act == "actions":
    print(json.dumps({"rename": [{"id": "MAIN1", "name": "1 TB Toshiba HDD", "role": "main", "custom": False, "connected": True, "others": 0 if mode == "single" else 1, "has_data": True, "boot_section": False, "used_bytes": 250000000000},
                                 {"id": "BACKUP1", "name": "Old Backup", "role": "backup", "custom": True, "connected": False, "others": 0, "has_data": False, "boot_section": False, "used_bytes": 0},
                                 {"id": "MAIN2", "name": "2 TB Seagate HDD 2", "role": "main", "custom": False, "connected": True, "others": 0 if mode == "single" else 1, "has_data": False, "boot_section": False, "used_bytes": 0}],
                      "spare": [{"id": "sdc", "device": "/dev/sdc", "name": "63 GB Cruzer HDD", "size_bytes": 63100000000, "keep_ok": True, "partitions": 1}],
                      "power": [{"id": "sdb", "name": "1 TB Toshiba HDD", "role": "main", "state": "awake"}], "can_sleep": True}))
elif act == "health":
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
    if mode == "jobslow":
        for i in range(1, 5):
            print("Copying files, step %d of 4..." % i, flush=True)
            time.sleep(0.7)
    if mode == "jobfail":
        sys.stderr.write("Cancelled. Nothing was changed.\n")
        sys.exit(1)
    print("Done. 63 GB Cruzer HDD was %s." % {"add": "added", "wipe": "erased", "disconnect": "taken out of its pool", "move": "moved"}[act])
elif act == "rename":
    print("Done. 1 TB Toshiba HDD is now called %s." % args[3])
elif act in ("sleep", "wake"):
    print("Done. 1 TB Toshiba HDD is %s." % ("asleep" if act == "sleep" else "awake"))
else:
    sys.stderr.write("Unknown panel command. Nothing was changed.\n")
    sys.exit(1)
