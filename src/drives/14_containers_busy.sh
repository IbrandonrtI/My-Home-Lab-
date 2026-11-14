docker_ok() { command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; }

containers_using() {
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

docker_each() {
  local act=$1 n tmp; shift
  tmp=$(mktemp) || return 0
  for n in "$@"; do
    ( docker "$act" "$n" >/dev/null 2>&1 || echo "$n" >>"$tmp" ) 6>&- 8>&- 9>&- &
    if [ "$(jobs -rp | wc -l)" -ge 8 ]; then wait -n 2>/dev/null || true; fi
  done
  wait
  cat "$tmp"; rm -f "$tmp"
}

# stop_containers PATH...: stop the containers that use the given paths.
stop_containers() {
  local list bad held n new=""
  list=$(containers_using "$@" | tr '\n' ' ')
  if [ "$PANEL_HOLD" = 1 ] && [ -n "$PANEL_RESERVE_DIR" ]; then
    held=$(cat "$PANEL_RESERVE_DIR/held" 2>/dev/null | tr '\n' ' ')
    for n in $list; do case " $held " in *" $n "*) ;; *) new="$new $n" ;; esac; done
    STOPPED=""
    [ -n "${new// /}" ] || return 0
    note "Stopping the containers that use this pool. They stay stopped until all drives are done:$new"
    # shellcheck disable=SC2086
    bad=$(docker_each stop $new)
    [ -z "${bad// /}" ] || warn "Some containers did not stop cleanly"
    for n in $new; do echo "$n" >>"$PANEL_RESERVE_DIR/held"; done
    return 0
  fi
  [ -n "${list// /}" ] || { STOPPED=""; return 0; }
  note "Stopping containers that use this pool: $list"
  # shellcheck disable=SC2086
  bad=$(docker_each stop $list)
  [ -z "${bad// /}" ] || warn "Some containers did not stop cleanly"
  STOPPED=$list
}

sync_fs() {
  sync -f "$@" 2>/dev/null || sync
}

YOUNG_SECS="${YOUNG_SECS:-1800}"

mark_added() {
  mkdir -p "$STATE_DIR/added" 2>/dev/null && date +%s >"$STATE_DIR/added/$1" 2>/dev/null
  return 0
}

young_drive() {
  local t now
  t=$(cat "$STATE_DIR/added/$1" 2>/dev/null) || return 1
  [[ "$t" =~ ^[0-9]+$ ]] || return 1
  now=$(date +%s)
  [ $(( now - t )) -lt "$YOUNG_SECS" ]
}

pool_devices() {
  local src tgt dsk
  while read -r src tgt; do
    [[ "$src" == /dev/* ]] || continue
    young_drive "$(basename "$tgt")" && continue
    dsk=$(lsblk -no pkname "$src" 2>/dev/null | head -n 1)
    printf '%s\n' "${dsk:-${src#/dev/}}"
  done < <(findmnt -rn -o SOURCE,TARGET 2>/dev/null | awk -v d="$DISKS_DIR" 'index($2, d "/") == 1 {print $1, $2}') | sort -u
}

sectors_written() {
  local d t=0 w
  while read -r d; do
    [ -n "$d" ] || continue
    w=$(awk '{print $7}' "/sys/block/$d/stat" 2>/dev/null)
    [[ "$w" =~ ^[0-9]+$ ]] && t=$((t + w))
  done < <(pool_devices)
  echo "$t"
}

busy_reason() {
  if [ "$TEST_MODE" = 1 ]; then
    if [ -n "${DRIVES_BUSY:-}" ]; then [ "$DRIVES_BUSY" = none ] || echo "$DRIVES_BUSY"; return 0; fi
    if [ -n "${DRIVES_BUSY_FILE:-}" ] && [ -s "$DRIVES_BUSY_FILE" ]; then cat "$DRIVES_BUSY_FILE"; return 0; fi
    if [ -n "${DRIVES_BUSY_COUNT_FILE:-}" ] && [ -s "$DRIVES_BUSY_COUNT_FILE" ]; then
      local left; left=$(cat "$DRIVES_BUSY_COUNT_FILE"); echo $(( left - 1 )) > "$DRIVES_BUSY_COUNT_FILE"
      [ "$left" -gt 0 ] && { echo "a backup is running"; return 0; }
    fi
  fi
  if [ -e "$BACKUP_LOCK" ] && ! ( exec 7<"$BACKUP_LOCK" && flock -n 7 ) 2>/dev/null; then
    echo "a backup is running"; return 0
  fi
  [ "$TEST_MODE" = 1 ] && return 0
  local a b secs=${BUSY_SAMPLE_SECS:-2}
  a=$(sectors_written); sleep "$secs"; b=$(sectors_written)
  if [ $(( (b - a) * 512 / secs )) -gt 300000 ]; then echo "files are being written to a storage pool (for example an upload)"; fi
  return 0
}

wait_text() {
  if [ "$1" -ge 3600 ]; then echo "$(( $1 / 3600 )) hours"; else echo "$1 seconds"; fi
}

busy_gate() {
  local why waited=0
  [ "$NOW" = 1 ] && return 0
  why=$(busy_reason)
  [ -n "$why" ] || return 0
  if [ "$DRY_RUN" = 1 ]; then
    note "Note: $why. A real run waits for this to finish first. Add --now to continue without waiting."
    return 0
  fi
  warn "Not safe to continue now: $why. Stopping the containers now could interrupt it."
  yn "Wait until it finishes, then continue?" || die "Stopped because $why. Nothing was changed. To continue anyway, add --now."
  note "Waiting, checking every ${BUSY_POLL_SECS}s for up to $(wait_text "$BUSY_MAX_WAIT_SECS"). Nothing has been changed yet; Ctrl+C cancels."
  while [ -n "$why" ]; do
    [ "$waited" -lt "$BUSY_MAX_WAIT_SECS" ] || die "Still busy after $(wait_text "$BUSY_MAX_WAIT_SECS") ($why). Nothing was changed."
    sleep "$BUSY_POLL_SECS"; waited=$((waited + BUSY_POLL_SECS))
    why=$(busy_reason)
    if [ -n "$why" ] && [ $((waited % 300)) -lt "$BUSY_POLL_SECS" ]; then note "  still waiting: $why"; fi
  done
  note "Finished. Continuing."
}

dry_gate() {
  [ "$DRY_RUN" = 1 ] || return 1
  local st i=1
  say ""
  say "Dry run: these are the steps that would run."
  for st in "$@"; do say "  $i. $st"; i=$((i + 1)); done
  say "Nothing was changed. Run the same command without --dry-run to do it."
  return 0
}

pre_change() {
  busy_gate
  dry_gate "$@"
}

main_hold_file() { printf '%s' "$STATE_DIR/main-empty-stopped"; }

main_hold_apply() {
  [ -z "$(branches_of main)" ] || return 0
  array_active && return 0
  boot_folder_ready
  return 0
}

main_hold_resume() {
  local f; f=$(main_hold_file)
  [ -s "$f" ] || return 0
  { [ -n "$(branches_of main)" ] || array_active; } && mountpoint -q "$MAIN_POOL" 2>/dev/null || return 0
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

main_pool_ok() {
  [ -n "$(branches_of main)" ] || pool_in_fstab "$MAIN_POOL" || return 0
  mountpoint -q "$MAIN_POOL"
}

batch_start_held() {
  local f="$PANEL_RESERVE_DIR/held" list
  [ -s "$f" ] || { start_containers; return 0; }
  list=$(tr '\n' ' ' <"$f"); rm -f "$f"
  PANEL_HOLD=0
  if main_pool_ok; then
    STOPPED=$list
    start_containers
  else
    STOPPED=$list
    note "The pools are not mounted correctly, so the containers stay stopped."
  fi
}

restore_services() {
  [ -n "${STOPPED// /}" ] && [ "$ROLLED_BACK" = 1 ] || return 0
  local role mp
  for role in main backup; do
    [ -n "$(branches_of "$role")" ] || continue
    for mp in $(branches_of "$role"); do mountpoint -q "$mp" || mount_fstab "$mp" 2>/dev/null; done
    mountpoint -q "$(role_pool "$role")" || mount_fstab "$(role_pool "$role")" 2>/dev/null
  done
  if main_pool_ok; then
    note "The previous configuration was restored. Starting the containers again."
    start_containers
  fi
}

on_exit() {
  release_started
  boot_view_close
  if [ -n "${STOPPED// /}" ]; then
    note ""
    note "The containers ($STOPPED) are still stopped because a step failed."
    note "${HOLD_HINT:-Fix the problem, then $(hint "run:  sudo drives remount" "press Fix Drives.")}"
  fi
  if [ -n "${PANEL_RESERVE_DIR:-}" ] && [ -s "$PANEL_RESERVE_DIR/held" ]; then
    note ""; note "The containers ($(tr '\n' ' ' <"$PANEL_RESERVE_DIR/held")) are still stopped because a step failed."; note "${HOLD_HINT:-Fix the problem, then $(hint "run:  sudo drives remount" "press Fix Drives.")}"
  fi
  if [ -n "$PENDING_NOTE" ]; then note ""; note "$PENDING_NOTE"; fi
  if [ -n "${PANEL_RESERVE_DIR:-}" ]; then rm -f "$BATCH_PID_FILE" "$ABORT_FILE"; rm -rf "$PANEL_RESERVE_DIR"; fi
  [ -n "${BALANCE_TMP:-}" ] && rm -rf "$BALANCE_TMP"
  [ -n "${SETTINGS_SNAP:-}" ] && rm -f "$SETTINGS_SNAP"
  [ -n "${NAME_CACHE:-}" ] && rm -rf "$NAME_CACHE"
  return 0
}
trap on_exit EXIT

