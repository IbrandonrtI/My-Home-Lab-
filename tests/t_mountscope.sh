#!/usr/bin/env bash
# shellcheck disable=SC2034  # PANEL_MODE and SYSTEMD_DIR are read by the sourced drives tool
# Test: a mount made from the control panel runs in its own systemd scope (so restarting the panel cannot end the pool's daemon); a mount made
# from a terminal is made as before. Nothing real is touched: mount, systemd-run and mountpoint are replaced by functions.
# Run: bash tests/t_mountscope.sh   (last line is OK or FAIL)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bad=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
if [ "$(id -u)" != 0 ]; then echo "skipped: needs root (the drives tool insists on it)"; echo OK; exit 0; fi
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
export DRIVES_TEST=1 DRIVES_STATE_DIR="$TMP/state" FSTAB="$TMP/fstab" DRIVE_NAMES_FILE_TEST="$TMP/chosen" SYSTEMD_DIR="$TMP/systemd"
: >"$FSTAB"; mkdir -p "$TMP/systemd"
# shellcheck disable=SC1091
source "$HERE/../scripts/drives"
LOG="$TMP/calls"
mount() { echo "mount $*" >>"$LOG"; }
systemd-run() { echo "systemd-run $*" >>"$LOG"; while [ "${1:-}" != mount ] && [ $# -gt 0 ]; do shift; done; "$@"; }
mountpoint() { return 0; }

PANEL_MODE=1; : >"$LOG"; mount_fstab /mnt/x; rc=$?
check "from the panel: the mount goes through systemd-run --scope" "$(head -1 "$LOG" | cut -c1-24)" "systemd-run --scope --qu"
check "from the panel: the mount command itself still runs, with the fstab and the mount point" "$(grep -c "^mount -T $FSTAB /mnt/x$" "$LOG")" "1"
check "from the panel: the result is a success" "$rc" "0"

PANEL_MODE=0; : >"$LOG"; mount_fstab /mnt/x; rc=$?
check "from a terminal: no scope, a plain mount" "$(cat "$LOG")" "mount -T $FSTAB /mnt/x"
check "from a terminal: the result is a success" "$rc" "0"

PANEL_MODE=1; SYSTEMD_DIR="$TMP/none"; : >"$LOG"; mount_fstab /mnt/x
check "without systemd (a container, a test): a plain mount" "$(cat "$LOG")" "mount -T $FSTAB /mnt/x"

SYSTEMD_DIR="$TMP/systemd"; mountpoint() { return 1; }; : >"$LOG"; mount_fstab /mnt/x; rc=$?
check "a mount that does not really mount is a failure, also in a scope" "$rc" "1"

[ "$bad" = 0 ] && echo OK || echo FAIL
[ "$bad" = 0 ]
