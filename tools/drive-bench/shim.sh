#!/usr/bin/env bash
# shim.sh - runs ONE `drives` command for drive-bench with scripted answers.
#
#   shim.sh DRIVES_SCRIPT ARGS...        run: drives ARGS...   (the same dispatcher as `sudo drives`)
#   shim.sh DRIVES_SCRIPT __call FUNC..  run one function of the script (used to build and rebuild test layouts)
#
# It loads the real script (so it tests the real code), then replaces only the function that reads the keyboard:
# every prompt is answered from the file $BENCH_ANSWERS (one answer per line, an empty line = just Enter) and written to
# $BENCH_EVENTS as one line:  number TAB kind TAB answer TAB prompt TAB list-of-choices (separated by 0x1f)
# When the answers run out the prompt gets "" and the line says <EOF>: that is what a person pressing Enter does.
#
# Environment (set by drive-bench):  BENCH_ANSWERS BENCH_EVENTS BENCH_COUNTER
#   BENCH_FAULT_AT  = after the answer to this prompt number is given, BENCH_FAULT_CMD runs (an unplug, a full drive ...)
#   BENCH_MAX_EOF   = stop the run when it asks this many times AFTER the answers ran out (a prompt that never lets go)

DRIVES=$1; shift
# shellcheck disable=SC1090
source "$DRIVES"
set +e   # the script sets -u; errors must reach its own code, not end this shim

: "${BENCH_ANSWERS:?}" "${BENCH_EVENTS:?}" "${BENCH_COUNTER:?}"
BENCH_MAX_EOF=${BENCH_MAX_EOF:-25}
flock() { return 0; }   # the bench never takes the real lock of `drives` (a real "sudo drives" running at the same time is not disturbed)
__ITEMS=()
: >"$BENCH_COUNTER"; echo 0 >"$BENCH_COUNTER"
__EOF_N=0

# keep the real choose(): it prints the numbered list and loops until it gets a number
eval "$(declare -f choose | sed '1s/^choose/__orig_choose/')"
choose() {
  __ITEMS=("${@:2}")
  __orig_choose "$@"
  local rc=$?
  __ITEMS=()
  return $rc
}

__bench_fault() {   # things that go wrong in the middle of a flow; all work on the test folders only
  local what=$1 label=$2 mp dev
  mp="$DISKS_DIR/$label"
  case "$what" in
    unplug)    # the drive disappears: its mount is cut and the device is detached
      dev=$(findmnt -no SOURCE "$mp" 2>/dev/null | sed 's/\[.*//')
      umount -l "$mp" 2>/dev/null
      [ -n "$dev" ] && losetup -d "$(lsblk -nsrpo NAME,TYPE "$dev" 2>/dev/null | awk '$2 == "loop" {print $1; exit}')" 2>/dev/null ;;
    fill)      fallocate -l "$(df -B1 --output=avail "$mp" | tail -1 | tr -d ' ')" "$mp/.bench-fill" 2>/dev/null ;;
    readonly)  mount -o remount,ro "$mp" 2>/dev/null ;;
    busy)      ( cd "$mp" 2>/dev/null && exec sleep 600 ) >/dev/null 2>&1 9>&- & echo $! >>"$BENCH_SLEEPERS" ;;
    poolbusy)  ( cd "$(role_pool "$label")" 2>/dev/null && exec sleep 600 ) >/dev/null 2>&1 9>&- & echo $! >>"$BENCH_SLEEPERS" ;;
    docker-stop-fails)  touch "$BENCH_FLAGS/stop-fails" ;;
    docker-start-fails) touch "$BENCH_FLAGS/start-fails" ;;
    mount-fails)        touch "$BENCH_FLAGS/mount-fails" ;;
  esac
}

ask() {
  local prompt=$1 n total ans="" kind=ask items="" i eofn
  n=$(( $(cat "$BENCH_COUNTER") + 1 )); echo "$n" >"$BENCH_COUNTER"
  total=$(wc -l <"$BENCH_ANSWERS")
  if [ "${#__ITEMS[@]}" -gt 0 ]; then kind=choose
    for i in "${__ITEMS[@]}"; do items+="${i//$'\n'/ }"$'\x1f'; done
  elif [[ "$prompt" == *"[y/N]: " ]]; then kind=yn
  elif [[ "$prompt" == Type* && "$prompt" != "Type a number"* ]]; then kind=typed
  fi
  if [ "$n" -le "$total" ]; then
    ans=$(sed -n "${n}p" "$BENCH_ANSWERS")
    printf '%s\t%s\t%s\t%s\t%s\n' "$n" "$kind" "$ans" "${prompt//$'\n'/\\n}" "$items" >>"$BENCH_EVENTS"
  else
    printf '%s\t%s\t%s\t%s\t%s\n' "$n" "$kind" "<EOF>" "${prompt//$'\n'/\\n}" "$items" >>"$BENCH_EVENTS"
    eofn=$(( n - total ))
    if [ "$eofn" -gt "$BENCH_MAX_EOF" ]; then
      printf 'BENCH-LOOP\t%s\t\t\t\n' "$n" >>"$BENCH_EVENTS"
      printf '\n[drive-bench] this command keeps asking after the answers ran out: stopped\n' >&2
      kill -9 $$ 2>/dev/null; exit 99
    fi
  fi
  printf '%s%s\n' "$prompt" "$ans" >&2   # a transcript that reads like the screen
  if [ -n "${BENCH_FAULT_AT:-}" ] && [ "$n" = "$BENCH_FAULT_AT" ]; then
    # shellcheck disable=SC2086
    __bench_fault $BENCH_FAULT_CMD
  fi
  printf '%s' "$ans"
}

__check_env() {   # the test settings must really be used by the script, or the bench stops before it touches anything
  printf '%s|%s|%s|%s|%s|%s\n' "$TEST_MODE" "$FSTAB" "$MAIN_POOL" "$BACKUP_POOL" "$DISKS_DIR" "$STATE_DIR"
}

__remount() {   # after a test layout was copied back: mount every drive and every pool the way the fstab says
  local mp role
  for mp in $(all_branches); do ensure_mp "$mp"; mount_fstab "$mp" 2>/dev/null; done
  for role in main backup; do
    ensure_mp "$(role_pool "$role")"
    if [ -n "$(branches_of "$role")" ] || fstab_active | awk -v m="$(role_pool "$role")" '$2 == m {f = 1} END {exit !f}'; then
      mount_fstab "$(role_pool "$role")" 2>/dev/null
    fi
  done
  return 0
}

# the commands the real tools would find are replaced through HOMELAB_EXTRA_PATH (see drive-bench); here only the entry point
if [ "${1:-}" = __call ]; then
  shift
  "$@"
  exit $?
fi
main "$@"
