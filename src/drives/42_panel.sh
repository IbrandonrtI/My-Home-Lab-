# ---------- the control panel's door: `sudo drives panel ACTION` ----------
# The control panel (the Drives tab of the dashboard) runs as the lab's own user and is allowed to run exactly these commands as root, without
# a password (the installer writes /etc/sudoers.d/homelab-panel). Nothing else. Every word is checked here again, because the rule only
# matches the start of the line. The commands never ask a question and never change anything but what their name says.
#   panel status | health | check | actions     look only (JSON)
#   panel rename ID NAME                          give a pool drive a name of your own (NAME auto: the automatic name again)
#   panel sleep ID | panel wake ID                put a spinning hard drive to sleep / wake it (ID is like sda)
#   panel remount                                 mount the drives again after an unplug (refused while a backup or upload runs)

panel_branch() {   # panel_branch LABEL -> the mount point of the pool drive with that label (nothing and 1 when there is none)
  local mp
  for mp in $(all_branches); do
    [ "$(basename "$mp")" = "$1" ] && { echo "$mp"; return 0; }
  done
  note "There is no pool drive called '$1'. Nothing was changed."
  return 1
}

panel_actions_json() {   # what the Drives tab may offer: the drives that can be renamed and the spinning drives that can sleep
  local mp label dev first=1 chosen
  printf '{"rename":['
  for mp in $(all_branches); do
    label=$(basename "$mp"); chosen=$(chosen_name "$label")
    [ "$first" = 1 ] || printf ','
    first=0
    printf '{"id":%s,"name":%s,"role":%s,"custom":%s,"connected":%s}' "$(json_str "$label")" "$(json_str "$(branch_name "$mp")")" \
      "$(json_str "$(branch_role "$mp")")" "$([ -n "$chosen" ] && echo true || echo false)" "$(mountpoint -q "$mp" && echo true || echo false)"
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

panel_main() {
  local act=${1:-} n=$#
  case "$act" in
    status|health|check|actions|remount) [ "$n" -eq 1 ] || { note "panel $act takes no more words. Nothing was changed."; return 1; } ;;
    rename)       [ "$n" -eq 3 ] || { note "panel rename takes a drive and a name. Nothing was changed."; return 1; } ;;
    sleep|wake)   [ "$n" -eq 2 ] || { note "panel $act takes one drive. Nothing was changed."; return 1; } ;;
    *) note "Unknown panel command. Nothing was changed."; return 1 ;;
  esac
  if [ "$n" -ge 2 ] && ! [[ "$2" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]]; then note "That drive id is not allowed. Nothing was changed."; return 1; fi
  if [ "$act" = rename ]; then
    if [ "$3" != auto ]; then
      if [ "${#3}" -gt 40 ] || [ "$(LC_ALL=C clean_name "$3")" != "$3" ] || [ -z "$3" ]; then
        note "A name may have up to 40 letters, numbers, spaces and . ( ) + , - (no space, dot or dash at the start or the end). Nothing was changed."; return 1
      fi
    fi
  fi
  [ "$(id -u)" = 0 ] || die "Run this with sudo:  sudo drives"
  take_lock
  ASSUME_YES=1
  local why
  case "$act" in
    status)  JSON=1; with_name_cache json_drives; printf ',"last_backup":%s,"boot_free_bytes":%s}\n' "$(json_str "$(last_backup_line)")" "$(json_num "$(boot_free_bytes)")" ;;
    health)  JSON=1; health_flow ;;
    check)   JSON=1; check_flow ;;
    actions) with_name_cache panel_actions_json ;;
    rename)  PANEL_ID=$2; PANEL_NAME=$3; run_changing rename_flow ;;
    sleep)   PANEL_ID=$2; sleep_flow ;;
    wake)    PANEL_ID=$2; wake_flow ;;
    remount)
      why=$(busy_reason)
      if [ -n "$why" ]; then note "Not a good moment: $why. Nothing was changed. Try again when it has finished."; return 1; fi
      NOW=1
      run_changing remount_flow ;;
  esac
}
