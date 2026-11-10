#!/usr/bin/env python3
"""What the panel tells after a drive change: a finished change is its "Done." line alone, a failed one the warnings it
ended with, and nothing is cut in the middle of a sentence. Run: python3 tests/t_drivemsg.py   (last line is OK or FAIL)"""
import importlib.machinery
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader("homelab_panel", os.path.join(HERE, "..", "scripts", "homelab-panel"))
spec = importlib.util.spec_from_loader("homelab_panel", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

bad = 0


def check(name, got, want):
    global bad
    if got == want:
        print("ok   " + name)
    else:
        bad += 1
        print("FAIL %s\n   got:    %r\n   wanted: %r" % (name, got, want))


rename = ("Done. Cruzer Test is now called Test Eight. Homepage already sees the pools.\n"
          "—— FileBrowser ——————\n"
          "Updating FileBrowser's drive folders: Backup-Pool/Test Eight waiting for FileBrowser ... ✓ FileBrowser now shows: Backup-Pool/Test Eight")
check("a finished change is told by its Done line alone", m.drive_message(rename, ""),
      "Done. Cruzer Test is now called Test Eight. Homepage already sees the pools.")

failed = ("!! ERASE WARNING !!\nEverything on these 2 drives will be permanently deleted:\n"
          "Copying the files of the Main pool into the new setup.\n"
          "WARNING: The copy stopped with an error (code 20).\n"
          "WARNING: /mnt/storage-new is busy, using a lazy unmount\n"
          "WARNING: The move to the new setup did not finish. Your Main pool is as it was and its files are untouched.\n"
          "Homepage already sees the pools.")
check("a change that did not work is told by its warnings", m.drive_message(failed, "", 1500, problem=True),
      "The copy stopped with an error (code 20). The move to the new setup did not finish. Your Main pool is as it was and its files are untouched.")

refused = ("Drive: 8 GB USB DISK 2.0 Flash (/dev/sdd, 7.2G, USB DISK 2.0, usb)  Serial: 070A54E574469F32  SMART health: unknown\n"
           "NAME SIZE FSTYPE LABEL MOUNTPOINTS\nsdd 7.2G\n"
           "This drive: 8 GB USB DISK 2.0 Flash (/dev/sdd)\nIt will be added to the Backup storage.\n"
           "ERROR: /dev/sdd does not have one ext4 partition, so its files cannot be kept.")
check("a change the tool refused is told by the reason alone, without the drive's table before it", m.drive_message(refused, "", 1500, problem=True),
      "/dev/sdd does not have one ext4 partition, so its files cannot be kept.")

long_out = "\n".join("Line number %d says something quite long to fill the space." % i for i in range(60))
msg = m.drive_message(long_out, "", 300)
check("a long text is cut between lines, not in the middle of one", msg.startswith("Line number "), True)

print("OK" if bad == 0 else "FAIL")
sys.exit(1 if bad else 0)
