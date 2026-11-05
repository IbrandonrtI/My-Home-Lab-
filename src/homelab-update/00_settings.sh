#!/usr/bin/env bash
# homelab-update - find newer container images, download them, and update the containers one stack at a time.
#
#   sudo homelab-update            check, download, then update each stack that has something new (asks before each)
#   sudo homelab-update --yes      the same without the questions (a Nextcloud major version jump is still left to you)
#   sudo homelab-update --now      do not wait for uploads or a running backup to finish (see below)
#   sudo homelab-update --backup   also run the full backup first (by default only a quick database dump is made)
#   sudo homelab-update check      only look: which images have a newer version online (downloads nothing)
#   homelab-update list            show the last result and the order to update in (no sudo needed)
#   sudo homelab-update clean      delete the saved old versions and leftover old images NOW (shows first, asks)
#   sudo homelab-update clean --old   only the saved copies older than 30 days
#   sudo homelab-update auto       for cron: refresh the list, and run the weekly check when it is due
#   sudo homelab-update refresh    for cron: re-read the list without using the internet
#   homelab-update version
#
# What it does for each stack: a quick dump of the database (Nextcloud and Immich only, seconds), then the same as
# "Update the stack" in Portainer (it asks Portainer through the key the installer saved), then it waits until the
# containers are running and healthy. Portainer itself is recreated from the terminal. It stops BEFORE touching
# anything while files are being written to a pool (an upload) or a backup is running; run it again when that is done.
# It compares the image behind the tag a container runs. For a tag fixed to one version (v2.6.0) it also looks up newer
# version numbers at the registry (v2.7.0). It never touches images locked to an exact fingerprint (@sha256) or listed in HOLD.
#
# Files it writes in /var/lib/homelab/:
#   image-updates   what the login screen reads: line 1 = time of the last check, then one line per stack
#   image-state     the details behind it (stack, image, fingerprint or new version found online, time found)
# Settings can be changed in /etc/homelab-update.conf (see the guide).

set -u
export PATH="${HOMELAB_EXTRA_PATH:+$HOMELAB_EXTRA_PATH:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

VERSION="1.2"
STATE_DIR="${HOMELAB_STATE_DIR:-/var/lib/homelab}"
CONF="${HLU_CONF:-/etc/homelab-update.conf}"
BACKUP_CMD="${HLU_BACKUP_CMD:-/usr/local/sbin/homelab-backup}"
BACKUP_STATUS="${HLU_BACKUP_STATUS:-/var/lib/homelab-backup/last-run}"
LOCKFILE="${HLU_LOCKFILE:-/run/homelab-update.lock}"

HOLD=(immich_postgres immich_redis)   # containers never checked or updated here (Immich locks these on purpose)
CHECK_EVERY_DAYS=7                    # how often "auto" looks online
RETRY_HOURS=6                         # after a failed check, wait this long before "auto" tries again
MIN_FREE_GB=5                         # refuse to download with less free space than this
ROLLBACK_KEEP_DAYS=30                 # "clean" removes saved old versions older than this
REGISTRY_TIMEOUT=60                   # seconds to wait for one registry answer
# shellcheck disable=SC1090
[ -r "$CONF" ] && . "$CONF"

