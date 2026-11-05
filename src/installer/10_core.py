#!/usr/bin/env python3
# homelab-setup - build a Linux machine into the home lab from the GitHub repo.
#
#   sudo homelab-setup                 show the checklist (what is done, what is left)
#   sudo homelab-setup install         set the whole lab up (asks first, safe to run again)
#   sudo homelab-setup install --dry-run   show what it WOULD do, change nothing
#   sudo homelab-setup refresh         re-check everything, continue what is now possible
#   sudo homelab-setup fill            walk through the keys and logins that need you
#   sudo homelab-setup done STEP       mark a by-hand step as done   (skip STEP: not wanted)
#   sudo homelab-setup secrets         show the generated passwords (once, then keep them in a password manager)
#   homelab-setup progress | version | help
#
# It never formats or erases a drive (the one exception: it can grow an LVM system volume into unused space, after asking). It never stores the password you type.
# Python 3 standard library only.

import atexit
import base64
import getpass
import glob
import gzip
import hashlib
import ipaddress
import json
import os
import pwd
import re
import secrets as pysecrets
import shutil
import signal
import socket
import string
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0"

# ---------------------------------------------------------------- paths
ROOT = os.environ.get("HLS_ROOT", "").rstrip("/")          # tests point this at a fake root
FAKE = os.environ.get("HLS_FAKE") == "1"                    # tests: no root check, no chown
HOST_OVERRIDE = os.environ.get("HLS_HOST", "")              # tests: where the services answer


def P(path):
    """Path of `path` inside the machine's root folder (the real root, or the fake one under test)."""
    return ROOT + path


STATE_DIR = P("/var/lib/homelab-setup")
STATE_FILE = STATE_DIR + "/state.json"
PROGRESS_DIR = P("/var/lib/homelab")
PROGRESS_FILE = PROGRESS_DIR + "/setup-progress"
BOOT_GRACE = 600      # seconds after a boot during which scheduled checks wait (apps are still starting)
SECRET_DIR = P("/root/.homelab-setup")
SECRET_FILE = SECRET_DIR + "/secrets.env"
LOG_FILE = P("/var/log/homelab-setup.log")

# ---------------------------------------------------------------- the nine stacks (and Navidrome and AudioMuse-AI, two optional ones)
# name -> (file in stacks/, containers that must run)
STACKS = {
    "adguard": ("adguard.yaml", ["adguardhome"]),
    "beszel": ("beszel.yaml", ["beszel"]),
    "netdata": ("netdata.yaml", ["netdata-netdata-1"]),
    "speedtest-tracker": ("speedtest-tracker.yaml", ["speedtest-tracker"]),
    "filebrowser": ("filebrowser.yaml", ["filebrowser-filebrowser-1"]),
    "immich": ("immich.yaml", ["immich_server", "immich_postgres", "immich_machine_learning", "immich_redis"]),
    "nextcloud": ("nextcloud.yaml", ["nextcloud", "nextcloud_db", "nextcloud_redis", "nextcloud_cron"]),
    "homepage": ("homepage.yaml", ["homepage"]),
    "beszel-agent": ("beszel-agent.yaml", ["beszel-agent"]),
    "navidrome": ("navidrome.yaml", ["navidrome"]),        # optional: only on a machine with a music folder (see NavidromeStack)
    "audiomuse": ("audiomuse.yaml", ["audiomuse-postgres", "audiomuse-flask", "audiomuse-worker"]),   # optional: `homelab-setup audiomuse` (see AudioMuseStack)
}
STACK_ORDER = ["adguard", "beszel", "netdata", "speedtest-tracker", "filebrowser",
               "immich", "nextcloud", "homepage", "beszel-agent"]

# local port of each service, and the HTTPS port Tailscale Serve uses for it
PORTS = {"homepage": 3001, "portainer": 9000, "immich": 2283, "beszel": 8090, "adguard": 3000,
         "nextcloud": 8082, "filebrowser": 8081, "speedtest": 8088, "netdata": 19999, "navidrome": 4533, "audiomuse": 8100}
SERVE = [(1000, "homepage"), (1001, "portainer"), (1002, "immich"), (1003, "beszel"), (1004, "adguard"),
         (1005, "nextcloud"), (1006, "filebrowser"), (1007, "speedtest"), (1008, "netdata")]

# The placeholders the repository files use, replaced by this machine's values (see subst).
PH_USER = "your-username"
PH_FQDN = "pc.your-tailnet.ts.net"
PH_LAN = "192.168.X.X"
PH_KEY = "your-own-key"
PH_MAIL = "your-email@example.com"

# Optional: the values of an EARLIER server, for restoring a backup made there. The repository itself holds none.
# Set HOMELAB_OLD_USER, HOMELAB_OLD_LAN and HOMELAB_OLD_FQDN (for example pc.example.ts.net) before running the installer.
OLD_USER = os.environ.get("HOMELAB_OLD_USER", "")
OLD_LAN = os.environ.get("HOMELAB_OLD_LAN", "")
OLD_FQDN = os.environ.get("HOMELAB_OLD_FQDN", "")
OLD_TAILNET = OLD_FQDN.split(".", 1)[1] if "." in OLD_FQDN else ""


class Abort(Exception):
    """A step that cannot continue. The message is shown to the person."""


# ---------------------------------------------------------------- global switches
class Opt:
    """Command-line options."""
    dry = False
    yes = False
    backup = None
    no_restore = False
    force_existing = False
    all = False
    details = False
    repo = None
