#!/usr/bin/env bash
# homelab - cheat sheet and live status for the home lab server.
#
#   homelab           the whole screen: a summary, the current status (checked live), the dashboard addresses and suggested commands
#   homelab commands  every command I use, in groups
#                     ("Suggested Commands" are up to six that fit the current state)
#   homelab status    only the status block
#   homelab login     the short screen shown when a terminal opens (a few lines, read from the bell's file)
#   homelab docs      list the sections of the README and of the guides in docs/
#   homelab secrets   rebuild check: what must be in your password manager, and what the
#                     server can confirm (values are never shown; sudo gives a fuller check)
#   homelab version   the version of this command
#
#   Short forms (they run the real command with sudo and say which one):
#   homelab backup | update | upgrade | setup | drives | cards | selftest   [options]
#                     = sudo homelab-backup | homelab-update | homelab-setup upgrade | homelab-setup | drives | homelab-cards | homelab-selftest
#
#   homelab theme     change the Homepage dashboard's background, and the colour of all cards or of one card (homelab theme shows how)
#   homelab bookmark  add, list, move or remove bookmarks, by category; logos come from Brandfetch as SVG files
#
# Apart from theme and bookmark (which edit the Homepage files in your own home folder) and the short
# forms above (which ask sudo for the real command), it only reads information and never needs sudo.
# ~/.bashrc runs the short form, "homelab login", when a terminal opens (the installer adds that line): a few lines read from
# the bell's file, so it appears at once.

VERSION="2.1"
MAIN_POOL="${HOMELAB_MAIN_POOL:-/mnt/storage}"
BACKUP_POOL="${HOMELAB_BACKUP_POOL:-/mnt/backup}"
LAST_RUN_FILE="${HOMELAB_LAST_RUN_FILE:-/var/lib/homelab-backup/last-run}"
DOCS_DIR="${HOMELAB_DOCS_DIR:-$HOME/My-Home-Lab-}"
REPO_URL="${HOMELAB_REPO_URL:-https://github.com/IbrandonrtI/My-Home-Lab-.git}"
STALE_HOURS="${HOMELAB_STALE_HOURS:-36}"
BOOT_PATH="${HOMELAB_BOOT_PATH:-/}"
STATE_DIR="${HOMELAB_STATE_DIR:-/var/lib/homelab}"        # readings saved by homelab-sample
TEMP_WARN="${HOMELAB_TEMP_WARN:-50}"                       # drive temperature (C) that turns yellow
TEMP_BAD="${HOMELAB_TEMP_BAD:-60}"                         # ... and red
SAMPLE_STALE_MIN="${HOMELAB_SAMPLE_STALE_MIN:-60}"         # minutes before the readings count as old
ALERTS_MAX_AGE="${HOMELAB_ALERTS_MAX_AGE:-900}"            # the bell's file (alerts.json) is trusted by the login screen for this many seconds (cron rewrites it every 5 minutes)
URL_CACHE_SECS="${HOMELAB_URL_CACHE_SECS:-3600}"           # the dashboard addresses are looked up at most this often
BOOT_GRACE_SECS="${HOMELAB_BOOT_GRACE_SECS:-600}"          # after a boot the login screen only does light checks for this long
JUST_BOOTED=0

# colours only when printing to a terminal that supports them
if { [ -t 1 ] || [ "${HOMELAB_COLOR:-}" = 1 ]; } && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then   # HOMELAB_COLOR=1: the login hook writes to a file first but the screen is shown in colour
  B=$'\033[1m'; D=$'\033[2m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'
else
  B=""; D=""; G=""; Y=""; R=""; N=""
fi
# symbols: plain ones if the terminal is not UTF-8
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
  *[Uu][Tt][Ff]-8*|*[Uu][Tt][Ff]8*) S_OK="✓"; S_WARN="!"; S_BAD="✗"; S_DOT="·"; S_RULE="─" ;;
  *)                                S_OK="+"; S_WARN="!"; S_BAD="x"; S_DOT="-"; S_RULE="-" ;;
esac

# The real window width: the terminal is asked first. $COLUMNS is only a copy made when the shell started, and sudo passes it on.
