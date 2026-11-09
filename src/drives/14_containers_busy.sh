# ---------- containers ----------
docker_ok() { command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; }

containers_using() {   # containers_using PATH...  -> names of containers with a mount under any PATH
  docker_ok || return 0
  local name srcs src p
  {
    while IFS='|' read -r name srcs; do
      for src in $srcs; do
        for p in "$@"; do
          case "$src" in
            "$p"|"$p"/*) echo "${name#/}"; continue 3 ;;
          esac
        done
      done
    done < <(docker ps -aq | xargs -r docker inspect --format '{{.Name}}|{{range .Mounts}}{{.Source}} {{end}}' 2>/dev/null)
  } | sort -u
}

docker_each() {   # docker_each stop|start NAME...: the containers go together (8 at a time), not one after the other; prints the names that did not work
  local act=$1 n tmp; shift
  tmp=$(mktemp) || return 0
  for n in "$@"; do
    ( docker "$act" "$n" >/dev/null 2>&1 || echo "$n" >>"$tmp" ) 6>&- 8>&- 9>&- &
    if [ "$(jobs -rp | wc -l)" -ge 8 ]; then wait -n 2>/dev/null || true; fi
  done
  wait
  cat "$tmp"; rm -f "$tmp"
}

stop_containers() {   # stop_containers PATH...
  local list bad held n new=""
  list=$(containers_using "$@" | tr '\n' ' ')
  if [ "$PANEL_HOLD" = 1 ] && [ -n "$PANEL_RESERVE_DIR" ]; then      # several drives at once: the batch stops each container once and starts it once, when every drive is done
    held=$(cat "$PANEL_RESERVE_DIR/held" 2>/dev/null | tr '\n' ' ')
    for n in $list; do case " $held " in *" $n "*) ;; *) new="$new $n" ;; esac; done
    STOPPED=""
    [ -n "${new// /}" ] || return 0
    note "Stopping containers that use this storage (they stay stopped until every drive is done):$new"
    # shellcheck disable=SC2086
    bad=$(docker_each stop $new)
    [ -z "${bad// /}" ] || warn "Some containers did not stop cleanly"
    for n in $new; do echo "$n" >>"$PANEL_RESERVE_DIR/held"; done
    return 0
  fi
  [ -n "${list// /}" ] || { STOPPED=""; return 0; }
  note "Stopping containers that use this storage: $list"
  # shellcheck disable=SC2086
  bad=$(docker_each stop $list)
  [ -z "${bad// /}" ] || warn "Some containers did not stop cleanly"
  STOPPED=$list
}

sync_fs() {   # write out the data of just these drives (sync -f); a plain `sync` waits for every write on the whole computer and can take minutes on a busy one
  sync -f "$@" 2>/dev/null || sync
}

# ---------- before anything is changed: is a backup or an upload running? is this only a dry run? ----------
YOUNG_SECS="${YOUNG_SECS:-1800}"      # a drive that was added less than this long ago is not counted when looking for an upload (a new drive keeps writing by itself for a while)

mark_added() {   # mark_added LABEL: remember when a drive joined a pool
  mkdir -p "$STATE_DIR/added" 2>/dev/null && date +%s >"$STATE_DIR/added/$1" 2>/dev/null
  return 0
}

young_drive() {   # young_drive LABEL -> 0 when it joined a pool a short while ago
  local t now
  t=$(cat "$STATE_DIR/added/$1" 2>/dev/null) || return 1
  [[ "$t" =~ ^[0-9]+$ ]] || return 1
  now=$(date +%s)
  [ $(( now - t )) -lt "$YOUNG_SECS" ]
}

pool_devices() {   # the whole drives behind the pools (not the boot drive), one name per line; a drive that was added a short while ago is left out
  local src tgt dsk
  while read -r src tgt; do
    [[ "$src" == /dev/* ]] || continue
    young_drive "$(basename "$tgt")" && continue
    dsk=$(lsblk -no pkname "$src" 2>/dev/null | head -n 1)
    printf '%s\n' "${dsk:-${src#/dev/}}"
  done < <(findmnt -rn -o SOURCE,TARGET 2>/dev/null | awk -v d="$DISKS_DIR" 'index($2, d "/") == 1 {print $1, $2}') | sort -u
}

sectors_written() {   # sectors written to the pool drives so far (field 7 of /sys/block/DEV/stat)
  local d t=0 w
  while read -r d; do
    [ -n "$d" ] || continue
    w=$(awk '{print $7}' "/sys/block/$d/stat" 2>/dev/null)
    [[ "$w" =~ ^[0-9]+$ ]] && t=$((t + w))
  done < <(pool_devices)
  echo "$t"
}

busy_reason() {   # prints why it is a bad moment to stop the containers, or nothing
  if [ "$TEST_MODE" = 1 ]; then   # test hooks: a fixed reason, or a file whose text is the reason while it exists
    if [ -n "${DRIVES_BUSY:-}" ]; then [ "$DRIVES_BUSY" = none ] || echo "$DRIVES_BUSY"; return 0; fi
    if [ -n "${DRIVES_BUSY_FILE:-}" ] && [ -s "$DRIVES_BUSY_FILE" ]; then cat "$DRIVES_BUSY_FILE"; return 0; fi
    if [ -n "${DRIVES_BUSY_COUNT_FILE:-}" ] && [ -s "$DRIVES_BUSY_COUNT_FILE" ]; then   # busy for the next N checks, then free (no timing involved)
      local left; left=$(cat "$DRIVES_BUSY_COUNT_FILE"); echo $(( left - 1 )) > "$DRIVES_BUSY_COUNT_FILE"
      [ "$left" -gt 0 ] && { echo "a backup is running right now"; return 0; }
    fi
  fi
  if [ -e "$BACKUP_LOCK" ] && ! ( exec 7<"$BACKUP_LOCK" && flock -n 7 ) 2>/dev/null; then
    echo "a backup is running right now"; return 0
  fi
  [ "$TEST_MODE" = 1 ] && return 0
  local a b secs=${BUSY_SAMPLE_SECS:-2}      # (a short look is enough: an upload writes a lot every second)
  a=$(sectors_written); sleep "$secs"; b=$(sectors_written)
  # more than about 300 KB per second written to the pool drives: files are coming in
  if [ $(( (b - a) * 512 / secs )) -gt 300000 ]; then echo "files are being written to a storage pool (an upload?)"; fi
  return 0
}

wait_text() {   # 21600 -> "6 hours", 90 -> "90 seconds"
  if [ "$1" -ge 3600 ]; then echo "$(( $1 / 3600 )) hours"; else echo "$1 seconds"; fi
}

busy_gate() {   # called before the first change: when a backup or an upload runs, say so and wait for it (or stop)
  local why waited=0
  [ "$NOW" = 1 ] && return 0
  why=$(busy_reason)
  [ -n "$why" ] || return 0
  if [ "$DRY_RUN" = 1 ]; then
    note "Note: $why. A real run would wait for it to finish first (add --now to go on anyway)."
    return 0
  fi
  warn "Not a good moment: $why. Stopping the containers now could cut it short."
  yn "Wait until it finishes, then go on?" || die "Stopped because $why. Nothing was changed. (To go on anyway, add --now.)"
  note "Waiting, checking every ${BUSY_POLL_SECS}s for up to $(wait_text "$BUSY_MAX_WAIT_SECS"). Nothing has been changed yet; Ctrl+C cancels."
  while [ -n "$why" ]; do
    [ "$waited" -lt "$BUSY_MAX_WAIT_SECS" ] || die "Still busy after $(wait_text "$BUSY_MAX_WAIT_SECS") ($why). Nothing was changed."
    sleep "$BUSY_POLL_SECS"; waited=$((waited + BUSY_POLL_SECS))
    why=$(busy_reason)
    if [ -n "$why" ] && [ $((waited % 300)) -lt "$BUSY_POLL_SECS" ]; then note "  still waiting: $why"; fi
  done
  note "It finished. Going on."
}

dry_gate() {   # dry_gate STEP...: with --dry-run, list the steps, change nothing and return 0 (the caller then returns)
  [ "$DRY_RUN" = 1 ] || return 1
  local st i=1
  say ""
  say "DRY RUN: this is what would happen now."
  for st in "$@"; do say "  $i. $st"; i=$((i + 1)); done
  say "Nothing was changed. Run the same command without --dry-run to do it."
  return 0
}

pre_change() {   # pre_change STEP...: the last stop before the first change. 0 = this was a dry run, so the caller returns
  busy_gate
  dry_gate "$@"
}

# The Main storage can be left empty on purpose (every Main drive taken out). The services that use it must NOT start then: they would
# write into the bare folder on the boot drive. They are written down here and start again when a Main drive is back.
main_hold_file() { printf '%s' "$STATE_DIR/main-empty-stopped"; }

main_hold_apply() {   # takes the containers that use the Main storage out of STOPPED when Main has no drive
  [ -z "$(branches_of main)" ] || return 0
  local keep n rest="" mine=""
  keep=$(containers_using "$MAIN_POOL" | tr '\n' ' ')
  for n in $STOPPED; do case " $keep " in *" $n "*) mine="$mine $n" ;; *) rest="$rest $n" ;; esac; done
  [ -n "${mine// /}" ] || return 0
  mkdir -p "$STATE_DIR" 2>/dev/null
  for n in $mine; do echo "$n" >>"$(main_hold_file)"; done
  note "The Main storage is empty, so these containers stay stopped until a Main drive is added:$mine"
  STOPPED=${rest# }
}

main_hold_resume() {   # a Main drive is back and mounted: the containers that were kept stopped join the ones to start
  local f; f=$(main_hold_file)
  [ -s "$f" ] || return 0
  [ -n "$(branches_of main)" ] && mountpoint -q "$MAIN_POOL" 2>/dev/null || return 0
  # shellcheck disable=SC2046
  STOPPED=$({ printf '%s\n' $STOPPED; cat "$f"; } | sort -u | grep . | tr '\n' ' ')
  rm -f "$f"
}

start_containers() {
  main_hold_resume
  [ -n "${STOPPED// /}" ] || return 0
  main_hold_apply
  [ -n "${STOPPED// /}" ] || return 0
  local failed=""
  note "Starting containers: $STOPPED"
  # shellcheck disable=SC2086
  failed=$(docker_each start $STOPPED | tr '\n' ' ')
  [ -z "${failed// /}" ] || failed=" ${failed% }"
  STOPPED=""
  if [ -n "${failed// /}" ]; then
    START_FAILED="$START_FAILED$failed"
    warn "These containers did not start:$failed"
    note "Start them again with:  sudo docker start$failed"
  fi
}

main_pool_ok() {   # true when the main storage is mounted the way fstab says (or it is not set up at all)
  [ -n "$(branches_of main)" ] || pool_in_fstab "$MAIN_POOL" || return 0
  mountpoint -q "$MAIN_POOL"
}

batch_start_held() {   # the end of a batch of several drives: the containers it stopped start again (when the pools are mounted the way fstab says)
  local f="$PANEL_RESERVE_DIR/held" list
  [ -s "$f" ] || { start_containers; return 0; }      # (nothing was stopped by this batch; containers kept stopped for an empty Main may start now)
  list=$(tr '\n' ' ' <"$f"); rm -f "$f"
  PANEL_HOLD=0
  if main_pool_ok; then
    STOPPED=$list
    start_containers
  else
    STOPPED=$list
    note "The pools are not mounted the way they should be, so the containers stay stopped."
  fi
}

restore_services() {   # a step failed after the containers were stopped: when the old setup is back, mount it and start them again
  [ -n "${STOPPED// /}" ] && [ "$ROLLED_BACK" = 1 ] || return 0
  local role mp
  for role in main backup; do
    [ -n "$(branches_of "$role")" ] || continue
    for mp in $(branches_of "$role"); do mountpoint -q "$mp" || mount_fstab "$mp" 2>/dev/null; done
    mountpoint -q "$(role_pool "$role")" || mount_fstab "$(role_pool "$role")" 2>/dev/null
  done
  if main_pool_ok; then
    note "The old setup is back in place. Starting the containers again."
    start_containers
  fi
}

on_exit() {
  release_started
  if [ -n "${STOPPED// /}" ]; then
    note ""
    note "The containers ($STOPPED) are still STOPPED because something went wrong."
    note "${HOLD_HINT:-Fix the problem, then run:  sudo drives remount}"
  fi
  if [ -n "${PANEL_RESERVE_DIR:-}" ] && [ -s "$PANEL_RESERVE_DIR/held" ]; then
    note ""; note "The containers ($(tr '\n' ' ' <"$PANEL_RESERVE_DIR/held")) are still STOPPED because something went wrong."; note "${HOLD_HINT:-Fix the problem, then run:  sudo drives remount}"
  fi
  if [ -n "$PENDING_NOTE" ]; then note ""; note "$PENDING_NOTE"; fi
  if [ -n "${PANEL_RESERVE_DIR:-}" ]; then rm -f "$BATCH_PID_FILE" "$ABORT_FILE"; rm -rf "$PANEL_RESERVE_DIR"; fi      # (a drive change of the panel that ended some other way)
  [ -n "${BALANCE_TMP:-}" ] && rm -rf "$BALANCE_TMP"
  [ -n "${SETTINGS_SNAP:-}" ] && rm -f "$SETTINGS_SNAP"
  [ -n "${NAME_CACHE:-}" ] && rm -rf "$NAME_CACHE"
  return 0
}
trap on_exit EXIT

