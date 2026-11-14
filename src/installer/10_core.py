#!/usr/bin/env python3

import atexit
import base64
import contextlib
import getpass
import fcntl
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

ROOT = os.environ.get("HLS_ROOT", "").rstrip("/")
FAKE = os.environ.get("HLS_FAKE") == "1"
HOST_OVERRIDE = os.environ.get("HLS_HOST", "")


def P(path):
    """Prefix a path with the test root (HLS_ROOT) when one is set, so tests never touch the real system."""
    return ROOT + path


STATE_DIR = P("/var/lib/homelab-setup")
STATE_FILE = STATE_DIR + "/state.json"
PROGRESS_DIR = P("/var/lib/homelab")
PROGRESS_FILE = PROGRESS_DIR + "/setup-progress"
BOOT_GRACE = 600
SECRET_DIR = P("/root/.homelab-setup")
SECRET_FILE = SECRET_DIR + "/secrets.env"
LOG_FILE = P("/var/log/homelab-setup.log")

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
    "music-downloader": ("music-downloader.yaml", ["downtify", "metube"]),
    "navidrome": ("navidrome.yaml", ["navidrome"]),
    "audiomuse": ("audiomuse.yaml", ["audiomuse-postgres", "audiomuse-flask", "audiomuse-worker"]),
    "navilist": ("navilist.yaml", ["navilist"]),
}
STACK_ORDER = ["homepage", "adguard", "beszel", "netdata", "speedtest-tracker", "filebrowser",
               "immich", "nextcloud", "beszel-agent", "music-downloader"]

PORTS = {"homepage": 3001, "portainer": 9000, "immich": 2283, "beszel": 8090, "adguard": 3000,
         "nextcloud": 8082, "filebrowser": 8081, "speedtest": 8088, "netdata": 19999, "navidrome": 4533, "audiomuse": 8100, "navilist": 8200}
SERVE = [(1000, "homepage"), (1001, "portainer"), (1002, "immich"), (1003, "beszel"), (1004, "adguard"),
         (1005, "nextcloud"), (1006, "filebrowser"), (1007, "speedtest"), (1008, "netdata")]

PH_USER = "your-username"
PH_FQDN = "pc.your-tailnet.ts.net"
PH_LAN = "192.168.X.X"
PH_KEY = "your-own-key"
PH_MAIL = "your-email@example.com"

OLD_USER = os.environ.get("HOMELAB_OLD_USER", "")
OLD_LAN = os.environ.get("HOMELAB_OLD_LAN", "")
OLD_FQDN = os.environ.get("HOMELAB_OLD_FQDN", "")
OLD_TAILNET = OLD_FQDN.split(".", 1)[1] if "." in OLD_FQDN else ""


class Abort(Exception):
    """Stops the current step and shows the message to the user."""
    pass


class NeedsPerson(Abort):
    """A step that cannot continue until the user does something; it stays open instead of failing."""
    pass


class NeedsPassword(NeedsPerson):
    pass


class Opt:
    """Command-line options for the current run."""
    dry = False
    yes = False
    backup = None
    no_restore = False
    no_background = False
    force_existing = False
    all = False
    wipe_data = False
    wipe_drives = False
    details = False
    repo = None
