# ---------- the control panel's door: `sudo drives panel ACTION` ----------
# The control panel (the Drives tab of the dashboard) runs as the lab's own user and is allowed to run exactly these commands as root, without
# a password (the installer writes /etc/sudoers.d/homelab-panel). Nothing else. Every word is checked here again, because the rule only
# matches the start of the line. The commands never ask a question and never change anything but what their name says.
#   panel status | health | check | actions     look only (JSON)
#   panel rename ID NAME                          give a pool drive a name of your own (NAME auto: the automatic name again)
#   panel sleep ID | panel wake ID                put a spinning hard drive to sleep / wake it (ID is like sda)
#   panel remount                                 mount the drives again after an unplug (refused while a backup or upload runs)
#   Stage 4 (these change or erase drives; every one is refused while a backup or upload runs, and none asks a question):
#   panel add DISK main|backup keep|erase [WORD...]   add a spare drive to a pool, keeping its files or erasing it first (erase needs /dev/DISK and ERASE typed)
#   panel wipe DISK empty|format [WORD...]            erase a spare drive (needs /dev/DISK and ERASE typed)
#   panel disconnect LABEL yes|no [WORD...]           take a drive out of its pool; yes = copy its files to the other drives first (no needs CONTINUE typed)
#   panel move LABEL keep|erase yes|no [WORD...]      move a drive to the other pool; keep|erase = what happens to the files on the drive (erase needs
#                                                     /dev/DISK and ERASE, keep needs KEEP); yes|no = copy its files to the other drives of its old pool first
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

panel_refuse() { note "$1 Nothing was changed."; return 1; }

panel_main() {
  local act=${1:-} n=$# i w
  case "$act" in
    status|health|check|actions|remount) [ "$n" -eq 1 ] || { panel_refuse "panel $act takes no more words."; return 1; } ;;
    rename)       [ "$n" -eq 3 ] || { panel_refuse "panel rename takes a drive and a name."; return 1; } ;;
    sleep|wake)   [ "$n" -eq 2 ] || { panel_refuse "panel $act takes one drive."; return 1; } ;;
    add)          [ "$n" -ge 4 ] && [ "$n" -le 8 ] || { panel_refuse "panel add takes a drive, main or backup, keep or erase, and the typed words."; return 1; } ;;
    wipe)         [ "$n" -ge 3 ] && [ "$n" -le 7 ] || { panel_refuse "panel wipe takes a drive, empty or format, and the typed words."; return 1; } ;;
    disconnect)   [ "$n" -ge 3 ] && [ "$n" -le 7 ] || { panel_refuse "panel disconnect takes a drive, yes or no, and the typed words."; return 1; } ;;
    move)         [ "$n" -ge 4 ] && [ "$n" -le 8 ] || { panel_refuse "panel move takes a drive, keep or erase, yes or no, and the typed words."; return 1; } ;;
    *) panel_refuse "Unknown panel command."; return 1 ;;
  esac
  if [ "$n" -ge 2 ] && ! [[ "$2" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]]; then panel_refuse "That drive id is not allowed."; return 1; fi
  local typed_from=0 arg_ok=1 keep="" role=""
  case "$act" in
    rename)
      if [ "$3" != auto ]; then
        if [ "${#3}" -gt 40 ] || [ "$(LC_ALL=C clean_name "$3")" != "$3" ] || [ -z "$3" ]; then
          panel_refuse "A name may have up to 40 letters, numbers, spaces and . ( ) + , - (no space, dot or dash at the start or the end)."; return 1
        fi
      fi ;;
    add)        role=$3; [[ "$3" =~ ^(main|backup)$ ]] && [[ "$4" =~ ^(keep|erase)$ ]] || arg_ok=0; typed_from=5 ;;
    wipe)       [[ "$3" =~ ^(empty|format)$ ]] || arg_ok=0; typed_from=4 ;;
    disconnect) [[ "$3" =~ ^(yes|no)$ ]] || arg_ok=0; typed_from=4 ;;
    move)       [[ "$3" =~ ^(keep|erase)$ ]] && [[ "$4" =~ ^(yes|no)$ ]] || arg_ok=0; typed_from=5 ;;
  esac
  [ "$arg_ok" = 1 ] || { panel_refuse "One of the choices is not allowed."; return 1; }
  PANEL_TYPED=()
  if [ "$typed_from" -gt 0 ]; then
    for ((i = typed_from; i <= n; i++)); do
      w=${!i}
      [[ "$w" =~ ^(ERASE|CONTINUE|REMOVE|KEEP|/dev/[a-z0-9]{1,16})$ ]] || { panel_refuse "A typed word is not allowed."; return 1; }
      PANEL_TYPED+=("$w")
    done
  fi
  [ "$(id -u)" = 0 ] || die "Run this with sudo:  sudo drives"
  case "$act" in
    status|health|check|actions) ;;      # looking only: these may run beside each other and beside a change (the panel does not start them during a change)
    *) take_lock ;;
  esac
  PANEL_MODE=1
  ASSUME_YES=0      # nothing is ever answered with yes for the person; a question nobody can answer means no
  local why
  case "$act" in
    rename|sleep|wake|status|health|check|actions) ASSUME_YES=1 ;;      # (these never ask anything that matters)
    *) why=""
       # a drive that joins a running pool stops nothing, so a backup or an upload may go on
       if [ "$act" = add ] && [[ "${3:-}" =~ ^(main|backup)$ ]] && pool_is_live "$3"; then :; else why=$(busy_reason); fi
       if [ -n "$why" ]; then note "Not a good moment: $why. Nothing was changed. Try again when it has finished."; return 1; fi
       NOW=1 ;;
  esac
  case "$act" in
    status)  JSON=1; with_name_cache json_drives; printf ',"last_backup":%s,"boot_free_bytes":%s}\n' "$(json_str "$(last_backup_line)")" "$(json_num "$(boot_free_bytes)")" ;;
    health)  JSON=1; health_flow ;;
    check)   JSON=1; check_flow ;;
    actions) with_name_cache panel_actions_json ;;
    rename)  PANEL_ID=$2; PANEL_NAME=$3; run_changing rename_flow ;;
    sleep)   PANEL_ID=$2; sleep_flow ;;
    wake)    PANEL_ID=$2; wake_flow ;;
    remount) ASSUME_YES=1; run_changing remount_flow ;;
    add)
      # the drive must be one of the spare drives; keep needs one ext4 partition (connect_flow checks that again before it changes anything)
      grep -qx "/dev/$2" <<<"$(candidate_disks)" || { panel_refuse "$2 is not a spare drive that can be added."; return 1; }
      run_changing connect_flow "/dev/$2" "$3" "$([ "$4" = keep ] && echo 2 || echo 1)" ;;
    wipe)
      PANEL_ID=$2; PANEL_ARG=$3; run_changing wipe_flow ;;
    disconnect)
      PANEL_ID=$2; PANEL_COPY=$3; run_changing disconnect_flow ;;
    move)
      PANEL_ID=$2; PANEL_KEEP=$([ "$3" = keep ] && echo yes || echo no); PANEL_COPY=$4; run_changing move_flow ;;
  esac
}
