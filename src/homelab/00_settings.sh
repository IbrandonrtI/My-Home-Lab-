#!/usr/bin/env bash

usage() {
  cat <<'HELP'
homelab - cheat sheet and live status for the home lab server.

  homelab           the whole screen: a summary, the current status (checked live), the dashboard addresses and suggested commands
  homelab commands  every command, in groups
                    ("Suggested Commands" are up to six that fit the current state)
  homelab status    only the status block
  homelab login     the screen shown when a terminal opens: the summary, the status and the browser addresses (no suggestions)
  homelab docs      list the sections of the README and of the guides in docs/
  homelab secrets   rebuild check: what must be in your password manager, and what the
                    server can confirm (values are never shown; sudo gives a fuller check)
  homelab version   the version of this command

  Short forms (they run the real command with sudo and say which one):
  homelab backup | update | upgrade | uninstall | setup | drives | cards | selftest   [options]
                    = sudo homelab-backup | homelab-update | homelab-setup upgrade | homelab-setup uninstall | homelab-setup | drives | homelab-cards | homelab-selftest

  homelab theme     change the Homepage dashboard's background, and the color of all cards or of one card (homelab theme shows how)
  homelab bookmark  add, list, move or remove bookmarks, by category; logos come from Brandfetch as SVG files

Apart from theme and bookmark (which edit the Homepage files in your own home folder) and the short
forms above (which ask sudo for the real command), it only reads information and never needs sudo.
~/.bashrc runs the shorter form, "homelab login", when a terminal opens (the installer adds that line).
HELP
}

VERSION="2.1"
MAIN_POOL="${HOMELAB_MAIN_POOL:-/mnt/storage}"
BACKUP_POOL="${HOMELAB_BACKUP_POOL:-/mnt/backup}"
LAST_RUN_FILE="${HOMELAB_LAST_RUN_FILE:-/var/lib/homelab-backup/last-run}"
DOCS_DIR="${HOMELAB_DOCS_DIR:-$HOME/My-Home-Lab-}"
REPO_URL="${HOMELAB_REPO_URL:-https://github.com/IbrandonrtI/My-Home-Lab-.git}"
STALE_HOURS="${HOMELAB_STALE_HOURS:-36}"
BOOT_PATH="${HOMELAB_BOOT_PATH:-/}"
STATE_DIR="${HOMELAB_STATE_DIR:-/var/lib/homelab}"
TEMP_WARN="${HOMELAB_TEMP_WARN:-50}"
TEMP_BAD="${HOMELAB_TEMP_BAD:-60}"
SAMPLE_STALE_MIN="${HOMELAB_SAMPLE_STALE_MIN:-60}"
LOGIN_CACHE_SECS="${HOMELAB_LOGIN_CACHE_SECS:-120}"
URL_CACHE_SECS="${HOMELAB_URL_CACHE_SECS:-3600}"
BOOT_GRACE_SECS="${HOMELAB_BOOT_GRACE_SECS:-600}"
JUST_BOOTED=0

if { [ -t 1 ] || [ "${HOMELAB_COLOR:-}" = 1 ]; } && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then
  B=$'\033[1m'; D=$'\033[2m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'
else
  B=""; D=""; G=""; Y=""; R=""; N=""
fi
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
  *[Uu][Tt][Ff]-8*|*[Uu][Tt][Ff]8*) S_OK="✓"; S_WARN="!"; S_BAD="✗"; S_DOT="·"; S_RULE="─" ;;
  *)                                S_OK="+"; S_WARN="!"; S_BAD="x"; S_DOT="-"; S_RULE="-" ;;
esac
