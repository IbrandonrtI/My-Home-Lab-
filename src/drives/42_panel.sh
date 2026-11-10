# ---------- the control panel's door: `sudo drives panel ACTION` ----------
# The control panel (the Drives tab of the dashboard) runs as the lab's own user and is allowed to run exactly these commands as root, without
# a password (the installer writes /etc/sudoers.d/homelab-panel). Nothing else. Every word is checked here again, because the rule only
# matches the start of the line. The commands never ask a question and never change anything but what their name says.
#   panel status | health | check | actions     look only (JSON)
#   panel rename ID NAME                          give a pool drive a name of your own (NAME auto: the automatic name again)
#   panel sleep ID | panel wake ID                put a spinning hard drive to sleep / wake it (ID is like sda)
#   panel remount                                 mount the drives again after an unplug (refused while a backup or upload runs)
#   panel abort                                   Stop: the add / move / disconnect that runs now stops at the next safe moment (not while a drive is being erased)
#   Stage 4 (these change or erase drives; every one is refused while a backup or upload runs, and none asks a question):
#   panel add DISK main|backup keep|erase [WORD...]   add a spare drive to a pool, keeping its files or erasing it first (erase needs /dev/DISK and ERASE typed)
#   panel wipe DISK empty|format [WORD...]            erase a spare drive (needs /dev/DISK and ERASE typed)
#   panel disconnect LABEL yes|no [WORD...]           take a drive out of its pool; yes = copy its files to the other drives first (no needs CONTINUE typed)
#   panel move LABEL keep|erase yes|no [WORD...]      move a drive to the other pool; keep|erase = what happens to the files on the drive (erase needs
#                                                     /dev/DISK and ERASE, keep needs KEEP); yes|no = copy its files to the other drives of its old pool first
#   panel setups | panel setup NAME DISK,DISK,... [WORD...]   Configure Drives: rank the ready-made setups for the spare drives / build one (needs NAME and ERASE typed)
#   panel bootadd main|backup GB [WORD...]            part of the boot drive becomes a drive of that pool (needs CONTINUE typed)
#   WORD is what the person typed: ERASE, CONTINUE, REMOVE, KEEP or a /dev/NAME. A word only counts when the question that asks for it gets exactly it.

panel_branch() {   # panel_branch LABEL -> the mount point of the pool drive with that label (nothing and 1 when there is none)
  local mp
  for mp in $(all_branches); do
    [ "$(basename "$mp")" = "$1" ] && { echo "$mp"; return 0; }
  done
  note "There is no pool drive called '$1'. Nothing was changed."
  return 1
}

panel_actions_json() {   # what the Drives tab may offer: pool drives (rename, move, take out), spare drives (add, erase) and spinning drives (sleep, wake)
  local mp label dev first=1 chosen role others used data boot kept
  printf '{"rename":['
  for mp in $(all_branches); do
    label=$(basename "$mp"); chosen=$(chosen_name "$label"); role=$(branch_role "$mp")
    others=$(branches_of "$role" | grep -vxc "$mp" || true)
    data=false; used=0
    if mountpoint -q "$mp"; then used=$(used_bytes "$mp" 2>/dev/null || true); case "$used" in ""|*[!0-9]*) used=0 ;; esac; has_data "$mp" && data=true; fi
    boot=false; is_boot_section "$mp" && boot=true
    [ "$first" = 1 ] || printf ','
    first=0
    printf '{"id":%s,"name":%s,"role":%s,"custom":%s,"connected":%s,"others":%s,"has_data":%s,"boot_section":%s,"used_bytes":%s}' "$(json_str "$label")" "$(json_str "$(branch_name "$mp")")" \
      "$(json_str "$role")" "$([ -n "$chosen" ] && echo true || echo false)" "$(mountpoint -q "$mp" && echo true || echo false)" "$(json_num "${others:-0}")" "$data" "$boot" "$(json_num "$used")"
  done
  printf '],"spare":['
  first=1
  for dev in $(candidate_disks); do
    local -a kp=(); mapfile -t kp < <(parts_of "$dev")
    kept=false; [ ${#kp[@]} -eq 1 ] && [ "$(fs_type "${kp[0]}")" = ext4 ] && kept=true
    [ "$first" = 1 ] || printf ','
    first=0
    printf '{"id":%s,"device":%s,"name":%s,"size_bytes":%s,"keep_ok":%s,"partitions":%s}' "$(json_str "$(basename "$dev")")" "$(json_str "$dev")" "$(json_str "$(disk_base_name "$dev")")" \
      "$(json_num "$(lsblk -dnbo SIZE "$dev" 2>/dev/null | head -1 | tr -d ' ')")" "$kept" "$(json_num "${#kp[@]}")"
  done
  printf '],"power":['
  first=1
  if command -v hdparm >/dev/null 2>&1; then
    for dev in $(spinning_disks); do
      [ "$first" = 1 ] || printf ','
      first=0
      printf '{"id":%s,"name":%s,"role":%s,"state":%s}' "$(json_str "$(basename "$dev")")" "$(json_str "$(disk_base_name "$dev")")" \
        "$(json_str "$(disk_role_of "$dev")")" "$(json_str "$(power_state "$dev")")"
    done
  fi
  printf '],"can_sleep":%s}\n' "$(command -v hdparm >/dev/null 2>&1 && echo true || echo false)"
}

panel_list() {   # panel_list WORDS: "sdc" or "sdc,sdd" or "sdc:keep,sdd:erase" -> PANEL_IDS and PANEL_MODES (up to 8 drives, none twice)
  local t id m seen=","
  local -a toks
  IFS=, read -ra toks <<<"$1"
  if [ "${#toks[@]}" -lt 1 ] || [ "${#toks[@]}" -gt 8 ]; then panel_refuse "Choose between one and eight drives."; return 1; fi
  for t in "${toks[@]}"; do
    id=${t%%:*}; m=""; [ "$id" != "$t" ] && m=${t#*:}
    [[ "$id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] && { [ -z "$m" ] || [[ "$m" =~ ^(keep|erase)$ ]]; } || { panel_refuse "That drive id is not allowed."; return 1; }
    case "$seen" in *",$id,"*) panel_refuse "A drive cannot be chosen twice."; return 1 ;; esac
    seen="$seen$id,"
    PANEL_IDS+=("$id"); PANEL_MODES+=("$m")
  done
  return 0
}

panel_one() {   # panel_one add|move|disconnect ID MODE: one drive of a batch (sets ABORTED and PUTBACK when Stop ended it)
  local act=$1 id=$2 mode=$3 rc=0 mp part
  PROG_ITEM=$id; PROG_LO=0; PROG_HI=100; ABORTED=0; PUTBACK=0; NOROOM=0
  if [ "$act" != add ] && [ -n "$PANEL_RESERVE_DIR" ]; then      # where the drive came from, in case Stop is pressed after it is done and it has to go back
    mp=$(panel_branch "$id" 2>/dev/null); part=$(branch_part "$mp")
    if ! is_boot_section "$mp"; then      # (a boot drive section is deleted when it leaves: it cannot be put back)
      printf '%s\n' "$(branch_role "$mp")" >"$PANEL_RESERVE_DIR/$id.role"
      printf '%s\n' "$(disk_of_part "$part")" >"$PANEL_RESERVE_DIR/$id.dev"
    fi
  fi
  progress 0 "Waiting to start"
  case "$act" in
    add) connect_flow "/dev/$id" "$PANEL_ROLE" "$([ "$mode" = keep ] && echo 2 || echo 1)" || rc=1 ;;
    move) PANEL_ID=$id; PANEL_KEEP=$([ "$mode" = keep ] && echo yes || echo no); move_flow || rc=1 ;;
    disconnect) PANEL_ID=$id; disconnect_flow || rc=1 ;;
  esac
  PROG_LO=0; PROG_HI=100
  if [ "$rc" = 0 ]; then progress 100 "Done"
  elif [ "$PUTBACK" = 1 ]; then progress 0 "Put back"
  elif [ "$NOROOM" = 1 ]; then progress 0 "No room, left as it is"
  elif [ "$ABORTED" = 1 ]; then progress 0 "Stopped"; fi
  return "$rc"
}

panel_job_end() {   # panel_job_end ID RC: what a drive's own process leaves for the batch to read (its result, the containers it left stopped, the ones that did not start)
  local id=$1 rc=$2 state="done"
  if [ "$rc" != 0 ]; then
    if [ "$PUTBACK" = 1 ]; then state=putback; elif [ "$ABORTED" = 1 ]; then state=stopped; elif [ "$NOROOM" = 1 ]; then state=noroom; else state=failed; fi
  elif abort_requested; then state=late
  fi
  printf '%s\n' "$state" >"$PANEL_RESERVE_DIR/$id.state"
  printf '%s\n' "${STOPPED:-}" >"$PANEL_RESERVE_DIR/$id.stopped"
  printf '%s\n' "${START_FAILED:-}" >"$PANEL_RESERVE_DIR/$id.startfailed"
  [ "$state" = failed ] && : >"$ABORT_FILE"      # something went wrong: the other drives stop too, at the next safe moment
  return 0
}

# shellcheck disable=SC2034      # (nameof is read through a name reference by panel_batch_report)
panel_batch() {   # panel_batch add|move|disconnect: the drives of PANEL_IDS, up to PANEL_JOBS at the same time (the busy check was made once, FileBrowser is told once at the end)
  local act=$1 n=${#PANEL_IDS[@]} i id mode sameall=${PANEL_ALL:-} rc=0 mp r
  # every drive is checked before the first one is touched
  if [ "$act" = add ]; then
    for id in "${PANEL_IDS[@]}"; do
      grep -qx "/dev/$id" <<<"$(candidate_disks)" || { panel_refuse "$id is not a spare drive that can be added."; return 1; }
    done
  else
    for id in "${PANEL_IDS[@]}"; do panel_branch "$id" >/dev/null || return 1; done
    if [ "$n" -gt 1 ] && [ "$act" = move ]; then      # several drives moving at once must leave at least one Main drive (a single drive gets its own, longer explanation from the flow)
      local keepleft
      keepleft=$(branches_of main | wc -l)
      for id in "${PANEL_IDS[@]}"; do [ "$(branch_role "$(panel_branch "$id" 2>/dev/null)")" = main ] && keepleft=$((keepleft - 1)); done
      if [ "$keepleft" -lt 1 ]; then panel_refuse "That would take every drive out of the Main pool. Keep at least one Main drive."; return 1; fi
    fi
  fi
  PANEL_RESERVE_DIR=$(mktemp -d) || { panel_refuse "No room for working files."; return 1; }
  rm -f "$ABORT_FILE"; echo $$ >"$BATCH_PID_FILE"
  local -A nameof=()
  local par=$PANEL_JOBS      # (when every drive of a pool leaves there is nothing to copy to: the files stay on the drives, and the flow asks for the words)
  [ "$n" -gt 1 ] || par=1
  PANEL_LEAVING=()
  [ "$n" -gt 1 ] && { PANEL_HOLD=1; PANEL_BARRIER=1; }
  local -a started=()
  for id in "${PANEL_IDS[@]}"; do
    if [ "$act" = add ]; then nameof[$id]=$(disk_base_name "/dev/$id")
    else mp=$(panel_branch "$id"); nameof[$id]=$(branch_name "$mp"); PANEL_LEAVING+=("$mp"); fi
  done
  # the drives, each in its own process when there are several (a process that stops with an error stops only itself)
  for ((i = 0; i < n; i++)); do
    id=${PANEL_IDS[$i]}; mode=${PANEL_MODES[$i]:-$sameall}
    if [ "$n" = 1 ]; then
      panel_one "$act" "$id" "$mode" || { if [ "$ABORTED" = 1 ]; then rc=4; else rc=1; fi; }
      continue
    fi
    while [ "$(batch_copying "${started[@]}")" -ge "$par" ]; do sleep 0.5; done      # (a drive that is only waiting for the others does not count: the next one can start copying)
    if abort_requested; then printf 'notstarted\n' >"$PANEL_RESERVE_DIR/$id.state"; progress_for "$id" 0 "Not started"; continue; fi
    started+=("$id")
    ( trap 'panel_job_end "$id" $?' EXIT; panel_one "$act" "$id" "$mode" ) &
  done
  : >"$PANEL_RESERVE_DIR/launched-all"
  wait
  PANEL_BARRIER=0
  if [ "$n" -gt 1 ] && [ "$act" != add ] && abort_requested; then panel_undo_done "$act"; fi      # Stop was pressed: the drives that were already done go back where they were
  batch_start_held; PANEL_HOLD=0
  [ "$n" = 1 ] && { rm -f "$BATCH_PID_FILE" "$ABORT_FILE"; rm -rf "$PANEL_RESERVE_DIR"; PANEL_RESERVE_DIR=""; PANEL_LEAVING=(); return "$rc"; }
  panel_batch_report "$act" nameof
  rc=$?
  rm -f "$BATCH_PID_FILE" "$ABORT_FILE"; rm -rf "$PANEL_RESERVE_DIR"; PANEL_RESERVE_DIR=""; PANEL_LEAVING=()
  return "$rc"
}

branch_of_dev() {   # branch_of_dev /dev/sdX -> the mount point of the pool drive that lives on that disk
  local b part
  for b in $(all_branches); do
    part=$(branch_part "$b")
    [ -n "$part" ] && [ "$(disk_of_part "$part")" = "$1" ] && { echo "$b"; return 0; }
  done
  return 1
}

panel_undo_one() {   # panel_undo_one ACT ID: a finished drive goes back to the pool it came from, with the files it has now (nothing is erased)
  local act=$1 id=$2 dev role mp rc=0
  dev=$(cat "$PANEL_RESERVE_DIR/$id.dev" 2>/dev/null); role=$(cat "$PANEL_RESERVE_DIR/$id.role" 2>/dev/null)
  [ -n "$dev" ] && [ -n "$role" ] || return 2
  PROG_ITEM=$id; PROG_LO=0; PROG_HI=100; PANEL_LEAVING=()
  progress 10 "Putting the drive back"
  if [ "$act" = move ]; then
    mp=$(branch_of_dev "$dev") || return 1
    PANEL_COPY=no
    detach_branch "$mp" || return 1
  fi
  connect_flow "$dev" "$role" 2 1 || rc=1
  [ "$rc" = 0 ] && progress 100 "Put back"
  return "$rc"
}

panel_undo_done() {   # panel_undo_done ACT: Stop was pressed. Every drive that was already done goes back (one after the other; the Stop request no longer counts)
  local act=$1 id st
  ABORT_IGNORE=1; PANEL_UNDO=1
  for id in "${PANEL_IDS[@]}"; do
    st=$(cat "$PANEL_RESERVE_DIR/$id.state" 2>/dev/null)
    case "$st" in done|late) ;; *) continue ;; esac
    say "Stopped as you asked. Putting back a drive that was already done..."
    panel_undo_one "$act" "$id"
    case $? in
      0) printf 'undone\n' >"$PANEL_RESERVE_DIR/$id.state" ;;
      2) ;;      # (it cannot be put back: it stays done)
      *) printf 'undofailed\n' >"$PANEL_RESERVE_DIR/$id.state"; progress_for "$id" 100 "Could not put back" ;;
    esac
  done
  ABORT_IGNORE=0; PANEL_UNDO=0
  return 0
}

progress_for() {   # progress_for ID PERCENT "Text": a progress line for a drive that has no process of its own
  [ "$PANEL_MODE" = 1 ] || return 0
  printf 'PROGRESS %s %s %s\n' "$1" "$2" "$3"
}

panel_batch_report() {   # panel_batch_report ACT NAMEOF: read what each drive's process left, say what happened, and give the batch's exit code (0 all done, 1 something failed, 4 stopped on request)
  local act=$1 id st name f
  local -n nm=$2
  local -a okl=() failed=() stopped=() back=() late=() skipped=() undone=() undofail=() noroom=()
  for id in "${PANEL_IDS[@]}"; do
    st=$(cat "$PANEL_RESERVE_DIR/$id.state" 2>/dev/null); [ -n "$st" ] || st=failed
    name=${nm[$id]:-$id}
    case "$st" in
      done) okl+=("$name") ;;
      late) late+=("$name") ;;
      putback) back+=("$name") ;;
      noroom) noroom+=("$name") ;;
      undone) undone+=("$name") ;;
      undofailed) undofail+=("$name") ;;
      stopped) stopped+=("$name") ;;
      notstarted) skipped+=("$name") ;;
      *) failed+=("$name") ;;
    esac
    f=$(cat "$PANEL_RESERVE_DIR/$id.stopped" 2>/dev/null); [ -n "${f// /}" ] && STOPPED="${STOPPED:-} $f"
    f=$(cat "$PANEL_RESERVE_DIR/$id.startfailed" 2>/dev/null); [ -n "${f// /}" ] && START_FAILED="${START_FAILED:-}$f"
  done
  joinl() { local out="" x; for x in "$@"; do out="${out:+$out, }$x"; done; printf '%s' "$out"; }
  if [ ${#failed[@]} -gt 0 ]; then
    [ ${#stopped[@]} -gt 0 ] && say "The other drives were stopped with nothing lost: $(joinl "${stopped[@]}")."
    [ ${#back[@]} -gt 0 ] && say "Put back where they were: $(joinl "${back[@]}")."
    local why_f why_all=""
    for id in "${PANEL_IDS[@]}"; do      # what each failed drive complained about
      [ "$(cat "$PANEL_RESERVE_DIR/$id.state" 2>/dev/null)" = failed ] || [ ! -f "$PANEL_RESERVE_DIR/$id.state" ] || continue
      why_f=$(cat "$PANEL_RESERVE_DIR/$id.err" 2>/dev/null || tail -1 "$PANEL_RESERVE_DIR/$id.warn" 2>/dev/null)
      [ -n "$why_f" ] && why_all="${why_all:+$why_all; }${nm[$id]:-$id}: $why_f"
    done
    [ -n "$why_all" ] && say "What went wrong: $why_all"
    say "Stopped because of a problem with $(joinl "${failed[@]}"): ${#okl[@]} of ${#PANEL_IDS[@]} drives were done."
    return 1
  fi
  if [ ${#noroom[@]} -gt 0 ] && [ ${#stopped[@]} -eq 0 ] && [ ${#undone[@]} -eq 0 ]; then
    [ ${#okl[@]} -gt 0 ] && say "Done: $(joinl "${okl[@]}")."
    say "Not taken out, because the drives that stay do not have room for its files (the drive and its files are untouched): $(joinl "${noroom[@]}")."
    return 1
  fi
  if [ ${#stopped[@]} -gt 0 ] || [ ${#back[@]} -gt 0 ] || [ ${#skipped[@]} -gt 0 ] || [ ${#undone[@]} -gt 0 ] || [ ${#undofail[@]} -gt 0 ]; then
    local msg="Stopped as you asked."
    [ ${#okl[@]} -gt 0 ] && msg="$msg Finished before the stop: $(joinl "${okl[@]}")."
    [ ${#late[@]} -gt 0 ] && msg="$msg Could not be stopped, finished: $(joinl "${late[@]}")."
    [ ${#stopped[@]} -gt 0 ] && msg="$msg Stopped with nothing lost: $(joinl "${stopped[@]}")."
    [ ${#back[@]} -gt 0 ] && msg="$msg Put back where it was: $(joinl "${back[@]}")."
    [ ${#undone[@]} -gt 0 ] && msg="$msg Already done, now put back where it was: $(joinl "${undone[@]}")."
    [ ${#undofail[@]} -gt 0 ] && msg="$msg COULD NOT be put back (add it again from the Drives box): $(joinl "${undofail[@]}")."
    [ ${#skipped[@]} -gt 0 ] && msg="$msg Not started: $(joinl "${skipped[@]}")."
    say "$msg"
    return 4
  fi
  return 0
}

panel_abort() {   # Stop: the drive change that runs now stops at the next safe moment (a copy is cut off; a drive that is being erased cannot be stopped)
  local pid
  pid=$(cat "$BATCH_PID_FILE" 2>/dev/null)
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    : >"$ABORT_FILE"
    pkill -TERM -f -- '--info=progress2 --no-inc-recursive' 2>/dev/null || true
    say "Stop requested. The drives are stopped at the next safe moment."
    return 0
  fi
  note "No drive change is running right now. Nothing was changed."
  return 1
}

panel_refuse() { note "$1 Nothing was changed."; return 1; }

panel_main() {
  local act=${1:-} n=$# i w
  case "$act" in
    setups)       [ "$n" -le 2 ] && { [ "$n" -eq 1 ] || [[ "$2" =~ ^[A-Za-z0-9][A-Za-z0-9._,-]{0,200}$ ]]; } || { panel_refuse "panel setups takes no words, or the drives to leave out."; return 1; } ;;
    status|health|check|actions|remount|abort) [ "$n" -eq 1 ] || { panel_refuse "panel $act takes no more words."; return 1; } ;;
    rename)       [ "$n" -eq 3 ] || { panel_refuse "panel rename takes a drive and a name."; return 1; } ;;
    sleep|wake)   [ "$n" -eq 2 ] || { panel_refuse "panel $act takes one drive."; return 1; } ;;
    add)          [ "$n" -ge 4 ] && [ "$n" -le 24 ] || { panel_refuse "panel add takes a drive, main or backup, keep or erase, and the typed words."; return 1; } ;;
    bootadd)      [ "$n" -ge 3 ] && [ "$n" -le 6 ] || { panel_refuse "panel bootadd takes main or backup, a size in GB and the typed words."; return 1; } ;;
    setup)        [ "$n" -ge 4 ] && [ "$n" -le 8 ] || { panel_refuse "panel setup takes a setup name, the drives and the typed words."; return 1; } ;;
    wipe)         [ "$n" -ge 3 ] && [ "$n" -le 7 ] || { panel_refuse "panel wipe takes a drive, empty or format, and the typed words."; return 1; } ;;
    disconnect)   [ "$n" -ge 3 ] && [ "$n" -le 22 ] || { panel_refuse "panel disconnect takes a drive, yes or no, and the typed words."; return 1; } ;;
    move)         [ "$n" -ge 4 ] && [ "$n" -le 24 ] || { panel_refuse "panel move takes a drive, keep or erase, yes or no, and the typed words."; return 1; } ;;
    *) panel_refuse "Unknown panel command."; return 1 ;;
  esac
  PANEL_IDS=(); PANEL_MODES=()
  case "$act" in
    add|move|disconnect) panel_list "$2" || return 1 ;;      # one drive, or several (ID,ID,... and with "each" ID:keep or ID:erase)
    setup) [[ "$2" =~ ^[a-z0-9-]{3,12}$ ]] || { panel_refuse "That setup name is not allowed."; return 1; } ;;
    *) if [ "$n" -ge 2 ] && ! [[ "$2" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]]; then panel_refuse "That drive id is not allowed."; return 1; fi ;;
  esac
  local typed_from=0 arg_ok=1 keep="" role=""
  case "$act" in
    rename)
      if [ "$3" != auto ]; then
        if [ "${#3}" -gt 40 ] || [ "$(LC_ALL=C clean_name "$3")" != "$3" ] || [ -z "$3" ]; then
          panel_refuse "A name may have up to 40 letters, numbers, spaces and . ( ) + , - (no space, dot or dash at the start or the end)."; return 1
        fi
      fi ;;
    add)        role=$3; [[ "$3" =~ ^(main|backup)$ ]] && [[ "$4" =~ ^(keep|erase|each)$ ]] || arg_ok=0; typed_from=5 ;;
    wipe)       [[ "$3" =~ ^(empty|format)$ ]] || arg_ok=0; typed_from=4 ;;
    disconnect) [[ "$3" =~ ^(yes|no)$ ]] || arg_ok=0; typed_from=4 ;;
    move)       [[ "$3" =~ ^(keep|erase|each)$ ]] && [[ "$4" =~ ^(yes|no)$ ]] || arg_ok=0; typed_from=5 ;;
    setup)      typed_from=4 ;;
    bootadd)    [[ "$2" =~ ^(main|backup)$ ]] && [[ "$3" =~ ^[0-9]{1,6}$ ]] || arg_ok=0; typed_from=4 ;;
  esac
  # a drive with its own choice (ID:keep) needs the word "each"; without it every drive gets the same choice
  if [ "$arg_ok" = 1 ] && [[ "$act" =~ ^(add|move)$ ]]; then
    local m modeword=$3
    [ "$act" = add ] && modeword=$4
    for m in "${PANEL_MODES[@]}"; do
      if [ "$modeword" = each ]; then [ -n "$m" ] || arg_ok=0; else [ -z "$m" ] || arg_ok=0; fi
    done
  fi
  [ "$arg_ok" = 1 ] || { panel_refuse "One of the choices is not allowed."; return 1; }
  PANEL_TYPED=(); PANEL_NOW=0
  if [ "$typed_from" -gt 0 ]; then
    for ((i = typed_from; i <= n; i++)); do
      w=${!i}
      [[ "$w" =~ ^(ERASE|CONTINUE|REMOVE|KEEP|NOW|/dev/[a-z0-9]{1,16}|pool|mirror|snapraid1|snapraid2|zfs-stripe|zfs-mirror|zfs-raidz1|zfs-raidz2|zfs-raidz3|md-raid0|md-raid1|md-raid5|md-raid6|md-raid10)$ ]] || { panel_refuse "A typed word is not allowed."; return 1; }
      if [ "$w" = NOW ]; then PANEL_NOW=1; else PANEL_TYPED+=("$w"); fi
    done
  fi
  [ "$(id -u)" = 0 ] || die "Run this with sudo:  sudo drives"
  case "$act" in
    status|health|check|actions|abort|setups) ;;      # looking only (and Stop): these may run beside each other and beside a change (the panel does not start the looking ones during a change)
    *) take_lock ;;
  esac
  PANEL_MODE=1
  ASSUME_YES=0      # nothing is ever answered with yes for the person; a question nobody can answer means no
  local why
  case "$act" in
    rename|sleep|wake|status|health|check|actions|abort|setups) ASSUME_YES=1 ;;      # (these never ask anything that matters)
    *) why=""
       # a drive that joins a running pool stops nothing, so a backup or an upload may go on
       if [ "$PANEL_NOW" = 1 ]; then :      # the person chose "Go Ahead Anyway"
       elif [ "$act" = add ] && [[ "${3:-}" =~ ^(main|backup)$ ]] && pool_is_live "$3"; then :; else why=$(busy_reason); fi
       if [ -n "$why" ]; then note "Not a good moment: $why. Nothing was changed. Try again when it has finished."; return 1; fi
       NOW=1 ;;
  esac
  case "$act" in
    status)  JSON=1; with_name_cache json_drives; printf ',"last_backup":%s,"boot_free_bytes":%s,"boot_limits":%s}\n' "$(json_str "$(last_backup_line)")" "$(json_num "$(boot_free_bytes)")" "$(bootsection_limits_json)" ;;
    health)  JSON=1; health_flow ;;
    check)   JSON=1; check_flow ;;
    actions) with_name_cache panel_actions_json ;;
    abort)   panel_abort ;;
    setups)  PANEL_SKIP=${2:-}; panel_setups_json ;;
    bootadd) PANEL_ROLE=$2; PANEL_UNITS=$3; PROG_ITEM=bootadd; run_changing panel_bootadd_flow ;;
    setup)   PANEL_ID=$2; run_changing panel_setup_run "$2" "$3" ;;
    rename)  PANEL_ID=$2; PANEL_NAME=$3; run_changing rename_flow ;;
    sleep)   PANEL_ID=$2; sleep_flow ;;
    wake)    PANEL_ID=$2; wake_flow ;;
    remount) ASSUME_YES=1; run_changing remount_flow ;;
    add)
      PANEL_ROLE=$3; PANEL_ALL=$4
      run_changing panel_batch add ;;
    wipe)
      PANEL_ID=$2; PANEL_ARG=$3; run_changing wipe_flow ;;
    disconnect)
      PANEL_COPY=$3
      run_changing panel_batch disconnect ;;
    move)
      PANEL_ALL=$3; PANEL_COPY=$4
      run_changing panel_batch move ;;
  esac
}
