# ---------- actions on one drive: rename, sleep, wake, eject, wipe ----------
need_cmds() {   # need_cmds tool... -> 0 when every tool is installed, else says what to install
  local t missing=""
  for t in "$@"; do command -v "$t" >/dev/null 2>&1 || missing="$missing $t"; done
  [ -z "$missing" ] && return 0
  note "Missing tools:$missing"
  note "Install them with:  sudo apt install -y hdparm parted e2fsprogs util-linux"
  return 1
}

chosen_name_put() {   # chosen_name_put LABEL "name": keeps every other line (and comments) of DRIVE_NAMES_FILE
  local tmp
  mkdir -p "$(dirname "$DRIVE_NAMES_FILE")" 2>/dev/null || die "Could not write $DRIVE_NAMES_FILE"
  tmp=$(mktemp) || die "Could not make a temporary file"
  {
    if [ -r "$DRIVE_NAMES_FILE" ]; then
      awk -v k="$1" '{ key = $0; sub(/=.*/, "", key); gsub(/^[ \t]+|[ \t]+$/, "", key) } !(key == k && $0 !~ /^[ \t]*#/)' "$DRIVE_NAMES_FILE"
    else
      echo "# Names you chose for your drives: LABEL=Name (change them with: sudo drives rename)"
    fi
    printf '%s=%s\n' "$1" "$2"
  } >"$tmp"
  cat "$tmp" >"$DRIVE_NAMES_FILE" || { rm -f "$tmp"; die "Could not write $DRIVE_NAMES_FILE"; }
  chmod 644 "$DRIVE_NAMES_FILE" 2>/dev/null || true
  rm -f "$tmp"
}

chosen_name_del() {   # chosen_name_del LABEL
  [ -r "$DRIVE_NAMES_FILE" ] || return 0
  local tmp; tmp=$(mktemp) || return 0
  awk -v k="$1" '{ key = $0; sub(/=.*/, "", key); gsub(/^[ \t]+|[ \t]+$/, "", key) } !(key == k && $0 !~ /^[ \t]*#/)' "$DRIVE_NAMES_FILE" >"$tmp"
  cat "$tmp" >"$DRIVE_NAMES_FILE" || true
  rm -f "$tmp"
}

carry_name() {   # carry_name OLDLABEL NEWLABEL: a drive that gets a new label keeps the name you chose for it (names are kept by label)
  local nm
  [ -n "$1" ] && [ "$1" != "$2" ] || return 0
  nm=$(chosen_name "$1")
  [ -n "$nm" ] || return 0
  [ -z "$(chosen_name "$2")" ] || return 0
  chosen_name_put "$2" "$nm"
  chosen_name_del "$1"
}

rename_flow() {   # give a pool drive a name of your own (kept by the drive's label, so it stays when the drive is plugged in again)
  local mp label cur new b lower
  if [ -n "${PANEL_ID:-}" ]; then mp=$(panel_branch "$PANEL_ID") || return 1      # the control panel names the drive and the new name itself
  else mp=$(pick_branch "Which drive do you want to rename? ") || return 1; fi
  label=$(basename "$mp"); cur=$(branch_name "$mp")
  if [ -n "${PANEL_ID:-}" ]; then
    new=$PANEL_NAME
  else
    say ""
    say "This drive is called: $cur"
    if [ -n "$(chosen_name "$label")" ]; then say "You chose this name. Type  auto  to go back to the automatic name (size, make and type)."
    else say "The name is made from the size, make and type of the drive."; fi
    new=$(ask "New name (letters, numbers and spaces, up to 40 characters; Enter cancels): ")
  fi
  [ -n "$new" ] || { say "Cancelled. Nothing was changed."; return 1; }
  if [ "$new" = auto ]; then
    if [ -z "$(chosen_name "$label")" ]; then say "$cur already has its automatic name. Nothing was changed."; return 0; fi
    dry_gate "Remove your name for $cur from $DRIVE_NAMES_FILE." "Update the FileBrowser folders and the dashboard." && return 0
    chosen_name_del "$label"
    say ""; say "Done. The drive is called $(branch_name "$mp") again."
    log "rename $label -> automatic"
    return 0
  fi
  new=$(clean_name "$new")
  if [ -z "$new" ]; then note "That name has no letters or numbers. Nothing was changed."; return 1; fi
  if [ "${#new}" -gt 40 ]; then note "That name is longer than 40 characters. Nothing was changed."; return 1; fi
  lower=${new,,}
  for b in $(all_branches); do
    [ "$b" = "$mp" ] && continue
    if [ "$(branch_base_name "$b" | tr '[:upper:]' '[:lower:]')" = "$lower" ]; then
      note "Another drive is already called '$(branch_base_name "$b")'. Choose a different name. Nothing was changed."; return 1
    fi
  done
  if [ "$new" = "$cur" ]; then say "The drive is already called $cur. Nothing was changed."; return 0; fi
  dry_gate "Save the name '$new' for $cur in $DRIVE_NAMES_FILE." \
           "Update the FileBrowser folders and the dashboard so they show the new name." && return 0
  chosen_name_put "$label" "$new"
  say ""
  say "Done. $cur is now called $(branch_name "$mp")."
  log "rename $label ($cur) -> $new"
  return 0
}

disk_role_of() {   # disk_role_of /dev/sdX -> main, backup, plain-data or spare (a pool drive's role is read from the pools)
  local mp p
  for mp in $(all_branches); do
    p=$(branch_part "$mp")
    [ -n "$p" ] && [ "$(disk_of_part "$p")" = "$1" ] && { branch_role "$mp"; return 0; }
  done
  for mp in $(parity_mounts); do
    p=$(branch_part "$mp")
    [ -n "$p" ] && [ "$(disk_of_part "$p")" = "$1" ] && { echo parity; return 0; }
  done
  if grep -qx "$1" <<<"$(array_disks)"; then echo array; return 0; fi
  if grep -qx "$1" <<<"$(legacy_disks)"; then echo plain-data; else echo spare; fi
}

spinning_disks() {   # hard drives with moving parts (the boot drive, SSDs, flash sticks and drives that do not say what they are are left out)
  local d prot model
  prot=$(protected_disks)
  for d in $(all_disks | sort -u); do
    grep -qx "$d" <<<"$prot" && continue
    [ "$(lsblk -dno RM "$d" 2>/dev/null | tr -d ' ' | head -1)" = 1 ] && continue      # a removable stick: it has no motor, yet it often claims to be a spinning drive and to be asleep
    model=$(lsblk -dno MODEL "$d" 2>/dev/null | sed 's/ *$//')
    [ "$(drive_kind "$d" "$model")" = HDD ] && echo "$d"
  done
}

power_state() {   # power_state /dev/sdX -> asleep, awake or unknown (hdparm -C asks the drive without waking it)
  local o
  command -v hdparm >/dev/null 2>&1 || { echo unknown; return 0; }
  o=$(hdparm -C "$1" 2>/dev/null)
  case "$o" in *standby*|*sleeping*) echo asleep ;; *active*|*idle*) echo awake ;; *) echo unknown ;; esac
}

power_action() {   # power_action sleep|wake: pick a spinning hard drive and put it to sleep or wake it
  local verb=$1 dev name role state after i
  local -a devs=() items=()
  need_cmds hdparm || return 1
  mapfile -t devs < <(spinning_disks)
  if [ ${#devs[@]} -eq 0 ]; then
    note "No spinning hard drive found. SSDs, the boot drive and drives that do not say what they are have nothing to put to sleep."
    return 1
  fi
  if [ -n "${PANEL_ID:-}" ]; then      # the control panel names the drive itself: it must be one of the listed spinning drives
    dev=/dev/$PANEL_ID
    grep -qx "$dev" <<<"$(printf '%s\n' "${devs[@]}")" || { note "$PANEL_ID is not a spinning hard drive that can be put to sleep. Nothing was changed."; return 1; }
  else
    for dev in "${devs[@]}"; do items+=("$(disk_base_name "$dev")  ($(disk_role_of "$dev"))  $(power_state "$dev")"); done
    i=$(choose "Which drive do you want to $([ "$verb" = sleep ] && echo "put to sleep" || echo "wake up")? " "${items[@]}") || return 1
    dev=${devs[$i]}
  fi
  refuse_unsafe_disk_power "$dev" || return 1
  name=$(disk_base_name "$dev"); role=$(disk_role_of "$dev"); state=$(power_state "$dev")
  if [ "$verb" = sleep ]; then
    if [ "$state" = asleep ]; then say "$name is already asleep. Nothing was changed."; return 0; fi
    case "$role" in main|backup) say "Note: $name is in the $role pool. Anything that reads it wakes it up again at once$([ "$role" = main ] && echo " (main drives are set to never sleep)")." ;; esac
    dry_gate "Tell $dev ($name) to go to sleep (spin down)." && return 0
    hdparm -y "$dev" >/dev/null 2>&1 || true
    log "sleep $dev ($name)"
    after=$(power_state "$dev")
    case "$after" in
      asleep)  say "Done. $name is asleep. It wakes up by itself when something reads it." ;;
      unknown) say "The sleep command was sent to $name. This drive (or its USB adapter) cannot say if it is asleep now. Nothing else was changed." ;;
      *)       warn "$name did not go to sleep. Many USB adapters ignore this command; nothing is wrong with the drive."; return 1 ;;
    esac
  else
    if [ "$state" = awake ]; then say "$name is already awake. Nothing was changed."; return 0; fi
    dry_gate "Read one sector from $dev ($name) so that it spins up." && return 0
    hdparm --read-sector 0 "$dev" >/dev/null 2>&1 || dd if="$dev" of=/dev/null bs=4096 count=1 iflag=direct status=none 2>/dev/null || true
    log "wake $dev ($name)"
    after=$(power_state "$dev")
    case "$after" in
      awake)   say "Done. $name is awake." ;;
      unknown) say "$name was asked to wake up. This drive (or its USB adapter) cannot say if it is awake now. Nothing else was changed." ;;
      *)       warn "$name is still asleep. Many USB adapters hide the drive's state; try reading a file from it."; return 1 ;;
    esac
  fi
  return 0
}

refuse_unsafe_disk_power() {   # the boot/system drive is never offered, but check again before the command is sent
  grep -qx "$1" <<<"$(protected_disks)" && { note "$1 holds the operating system. Refusing."; return 1; }
  return 0
}

sleep_flow() { power_action sleep; }
wake_flow()  { power_action wake; }

eject_flow() {   # get a spare drive ready to unplug: unmount it, write out its data and power it off
  local dev name tran
  local -a devs=()
  mapfile -t devs < <(candidate_disks)
  if [ ${#devs[@]} -eq 0 ]; then
    note "No spare drive found. A drive that is in a pool is never listed here: take it out first with  sudo drives disconnect"
    note "(it copies the files off safely and unmounts the drive), then it is a spare drive."
    return 1
  fi
  note "Spare drives (a drive in a pool and the boot drive are never listed; for a pool drive use  sudo drives disconnect  first):"
  dev=$(pick_disk_list "Which drive do you want to unplug? " "${devs[@]}") || return 1
  refuse_unsafe_disk "$dev"
  name=$(disk_base_name "$dev"); tran=$(lsblk -dno TRAN "$dev" 2>/dev/null | head -1 | tr -d ' ')
  say ""
  say "$name  $(disk_details "$dev")"
  dry_gate "Unmount everything that is mounted from $dev." \
           "Write out the data of $dev." \
           "$([ "$tran" = usb ] && echo "Power the drive off, so it is safe to unplug." || echo "Tell the drive to stop spinning (it is not a USB drive, so it cannot be powered off).")" && return 0
  umount_disk_parts "$dev"
  command -v blockdev >/dev/null 2>&1 && blockdev --flushbufs "$dev" 2>/dev/null
  log "eject $dev ($name)"
  if [ "$tran" = usb ] && command -v udisksctl >/dev/null 2>&1; then
    if udisksctl power-off -b "$dev" >/dev/null 2>&1; then
      say ""; say "Done. $name is unmounted and powered off. You can unplug it now."
    else
      warn "$name is unmounted and its data is written out, but it could not be powered off."
      say "It is still safe to unplug it when its light has stopped blinking."
    fi
  else
    command -v hdparm >/dev/null 2>&1 && hdparm -y "$dev" >/dev/null 2>&1
    say ""
    say "Done. $name is unmounted and its data is written out. It was not powered off because it is not a USB drive."
    say "Only unplug it if your computer supports unplugging a drive while it runs."
  fi
  return 0
}

wipe_disk() {   # wipe_disk /dev/sdX: removes the file systems and the partition table (both ends of the drive)
  local dev=$1 p vg sectors
  refuse_unsafe_disk "$dev"
  umount_disk_parts "$dev"
  if command -v pvs >/dev/null 2>&1; then
    for vg in $(pvs --noheadings -o pv_name,vg_name 2>/dev/null | awk -v d="$dev" 'index($1, d) == 1 && $2 != "" {print $2}' | sort -u); do
      note "Deactivating old LVM group $vg on this drive..."
      vgchange -an "$vg" >/dev/null 2>&1 || warn "Could not deactivate $vg"
    done
  fi
  for p in $(parts_of "$dev"); do wipefs -a "$p" >/dev/null 2>&1 || true; done
  wipefs -a "$dev" >/dev/null 2>&1 || die "wipefs failed on $dev"
  # a GPT partition table keeps a copy at the end of the drive: clear the first and the last 1 MiB too
  dd if=/dev/zero of="$dev" bs=1M count=1 conv=fsync status=none 2>/dev/null || die "Could not clear the start of $dev"
  sectors=$(blockdev --getsz "$dev" 2>/dev/null)
  if [[ "$sectors" =~ ^[0-9]+$ ]] && [ "$sectors" -gt 8192 ]; then
    dd if=/dev/zero of="$dev" bs=512 seek=$((sectors - 2048)) count=2048 conv=fsync status=none 2>/dev/null || die "Could not clear the end of $dev"
  fi
  partprobe "$dev" >/dev/null 2>&1 || true
  udevadm settle 2>/dev/null || true
  log "wiped $dev"
}

wipe_flow() {   # erase a spare drive (never a pool drive, the boot drive or a drive in use), and optionally format it
  local dev name idx part
  local -a devs=()
  need_cmds wipefs parted mkfs.ext4 blkid partprobe || return 1
  mapfile -t devs < <(candidate_disks)
  if [ ${#devs[@]} -eq 0 ]; then
    note "No spare drive found. A drive that is in a pool is never erased here. To erase one, first take it out with"
    note "  sudo drives disconnect   (its files can be copied to the other drives first)"
    return 1
  fi
  if [ -n "${PANEL_ID:-}" ]; then      # the control panel names the spare drive and what to do with it
    dev=/dev/$PANEL_ID
    grep -qx "$dev" <<<"$(printf '%s\n' "${devs[@]}")" || { note "$PANEL_ID is not a spare drive that can be erased. Nothing was changed."; return 1; }
    refuse_unsafe_disk "$dev"
    describe_disk "$dev"
    name=$(disk_base_name "$dev")
    if [ "$PANEL_ARG" = format ]; then idx=1; else idx=0; fi
  else
    note "Spare drives (a drive in a pool and the boot drive are never listed):"
    dev=$(pick_disk_list "Which drive do you want to erase? " "${devs[@]}") || return 1
    refuse_unsafe_disk "$dev"
    describe_disk "$dev"
    name=$(disk_base_name "$dev")
    idx=$(choose "What should I do with the drive? " \
          "Erase it and leave it empty (no file system)" \
          "Erase it and format it as a new empty drive (ext4), ready to connect") || return 1
  fi
  confirm_erase "$dev" || return 1
  dry_gate "Unmount $dev and erase everything on $name (file systems and partition table)." \
           "$([ "$idx" = 1 ] && echo "Format it as a new empty ext4 drive (label SPARE)." || echo "Leave it empty, without a file system.")" && return 0
  if [ "$idx" = 1 ]; then
    part=$(format_disk "$dev" SPARE) || return 1
    say ""; say "Done. $name was erased and formatted as an empty ext4 drive ($part). Add it to a pool with:  sudo drives connect"
  else
    wipe_disk "$dev"
    say ""; say "Done. $name was erased and is empty. Format it or add it to a pool with:  sudo drives connect"
  fi
  log "erased $dev ($name)"
  return 0
}

actions_menu() {
  local c
  while :; do
    say ""
    say "Actions on one drive"
    say "  1) Rename a drive"
    say "  2) Put a drive to sleep"
    say "  3) Wake a drive up"
    say "  4) Get a spare drive ready to unplug"
    say "  5) Erase a spare drive"
    say "  0) Back"
    c=$(ask_choice)
    case "$c" in
      1) intro "Rename a drive" \
           "Next you pick a drive of the pools and type a name of your own." \
           "The name also shows in FileBrowser and on the dashboard. Nothing is erased or moved." &&
         { rename_flow && sync_filebrowser; } ;;
      2) intro "Put a drive to sleep" \
           "Next you pick a spinning hard drive. It spins down now and wakes up by itself when something reads it." \
           "No files are touched." &&
         sleep_flow ;;
      3) intro "Wake a drive up" \
           "Next you pick a spinning hard drive. One sector is read from it so that it spins up." \
           "No files are touched." &&
         wake_flow ;;
      4) intro "Get a spare drive ready to unplug" \
           "Next I list the spare drives (not the ones in a pool). The one you pick is unmounted, its data is written out" \
           "and a USB drive is powered off. Nothing is erased." &&
         eject_flow ;;
      5) intro "Erase a spare drive" \
           "Next I list the spare drives (not the ones in a pool). You pick one and say if it should stay empty or be formatted." \
           "You must type the drive name and ERASE before anything is erased." &&
         wipe_flow ;;
      0|"") return 0 ;;
      *) say "Please type a number from the list." ;;
    esac
  done
}

