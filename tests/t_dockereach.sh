#!/usr/bin/env bash
# shellcheck disable=SC2034  # STOPPED and the like are read by the sourced drives tool
# Test: containers stop and start together (not one after the other), a failing one is named, and the list of the stopped ones is kept.
# Nothing real is touched: docker is a function that waits half a second and writes down what it was asked.
# Run: bash tests/t_dockereach.sh   (last line is OK or FAIL)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bad=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
if [ "$(id -u)" != 0 ]; then echo "skipped: needs root (the drives tool insists on it)"; echo OK; exit 0; fi
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
export DRIVES_TEST=1 DRIVES_STATE_DIR="$TMP/state" FSTAB="$TMP/fstab" DRIVE_NAMES_FILE_TEST="$TMP/chosen"
: >"$FSTAB"
# shellcheck disable=SC1091
source "$HERE/../scripts/drives"
LOG="$TMP/calls"
docker() { sleep 0.5; echo "docker $*" >>"$LOG"; [ "${2:-}" = bad ] && return 1; return 0; }
containers_using() { printf '%s\n' a b c d e f g h i j; }
note() { :; }; warn() { echo "WARN $*" >>"$TMP/warn"; }

: >"$LOG"; start=$(date +%s.%N)
stop_containers /mnt/x
secs=$(echo "$(date +%s.%N) - $start" | bc)
check "ten containers stopped" "$(grep -c '^docker stop' "$LOG")" "10"
check "they stopped together: 10 x half a second took under 2.5 seconds" "$(echo "$secs < 2.5" | bc)" "1"
check "the stopped containers are remembered, in order" "$STOPPED" "a b c d e f g h i j "

: >"$LOG"; start=$(date +%s.%N)
start_containers
secs=$(echo "$(date +%s.%N) - $start" | bc)
check "ten containers started" "$(grep -c '^docker start' "$LOG")" "10"
check "they started together" "$(echo "$secs < 2.5" | bc)" "1"
check "nothing failed to start" "${START_FAILED:-}" ""
check "the list is empty afterwards" "${STOPPED// /}" ""

STOPPED="a bad c"; START_FAILED=""; : >"$LOG"
start_containers
check "a container that does not start is named" "${START_FAILED// /}" "bad"
check "the others started anyway" "$(grep -c '^docker start' "$LOG")" "3"

containers_using() { printf '%s\n' ok1 bad ok2; }; : >"$TMP/warn"
stop_containers /mnt/x
check "a container that does not stop gives a warning" "$(grep -c 'did not stop cleanly' "$TMP/warn")" "1"
check "and the stopped ones are still remembered" "$STOPPED" "ok1 bad ok2 "

# --- a drive that joined a pool a short while ago is not counted when looking for an upload; progress lines are for the panel only
mark_added NEWONE
young_drive NEWONE && r=young || r=old
check "a drive added just now counts as young" "$r" "young"
young_drive NOTMARKED && r=young || r=old
check "a drive that was never marked is not young" "$r" "old"
echo $(( $(date +%s) - 4000 )) >"$STATE_DIR/added/OLDONE"
young_drive OLDONE && r=young || r=old
check "a drive added over half an hour ago is not young any more" "$r" "old"
PANEL_MODE=0; PROG_ITEM=sdx
check "progress prints nothing outside the panel" "$(progress 50 "Half")" ""
PANEL_MODE=1
check "in the panel progress names the drive, the percent and the step" "$(progress 50 "Half way")" "PROGRESS sdx 50 Half way"
PROG_LO=0; PROG_HI=55
check "a step may use only part of the bar" "$(progress 100 "Left the pool")" "PROGRESS sdx 55 Left the pool"
PROG_LO=0; PROG_HI=100
rsync() { printf '  1,000  10%%  1MB/s  0:00:09\r  5,000  50%%  1MB/s  0:00:05\r 10,000 100%%  1MB/s  0:00:00 (xfr#1)\n'; return "${FAKE_RSYNC_RC:-0}"; }
out=$(rsync_run 5 60 "Copying files" -a /x /y)
check "rsync percent moves the bar between FROM and TO" "$(printf '%s\n' "$out" | tr '\n' ',')" "PROGRESS sdx 10 Copying files 10%,PROGRESS sdx 32 Copying files 50%,PROGRESS sdx 60 Copying files 100%,"
FAKE_RSYNC_RC=23; rsync_run 5 60 "Copying files" -a /x /y >/dev/null; rc=$?
check "a failing rsync still fails" "$rc" "23"
FAKE_RSYNC_RC=0; PANEL_MODE=0; rsync_run 5 60 "Copying files" -a /x /y >/dev/null; rc=$?
check "outside the panel rsync is plain" "$rc" "0"

[ "$bad" = 0 ] && echo OK || echo FAIL
[ "$bad" = 0 ]
