pool_can_grow() {
  local role=$1 pool; pool=$(role_pool "$1")
  [ -z "$(branches_of "$role")" ] && mountpoint -q "$pool" || return 0
  if [ "$role" = main ]; then
    note "$pool is currently one plain drive. Convert it into a pool first (sudo drives > Settings and upgrades > Convert the current single data drive), then add $2."
  else
    note "$pool is already mounted by something else. Check: findmnt $pool"
  fi
  return 1
}

pick_disk_list() {
  local prompt=$1; shift
  local -a devs=("$@") items=() bases=()
  local d i j same seen idx
  for d in "${devs[@]}"; do bases+=("$(disk_base_name "$d")"); done
  for i in "${!devs[@]}"; do
    same=0; seen=0
    for j in "${!devs[@]}"; do
      if [ "${bases[$j]}" = "${bases[$i]}" ]; then same=$((same + 1)); [ "$j" -le "$i" ] && seen=$((seen + 1)); fi
    done
    d=${devs[$i]}
    if [ "$same" -gt 1 ]; then items+=("${bases[$i]} $seen  $(disk_details "$d")")
    else items+=("$(disk_summary "$d")"); fi
  done
  idx=$(choose "$prompt" "${items[@]}") || return 1
  echo "${devs[$idx]}"
}

pick_new_disk() {
  local -a devs=()
  mapfile -t devs < <(candidate_disks)
  if [ ${#devs[@]} -eq 0 ]; then
    note "No new drive found. Connect the drive, wait 10 seconds and try again."
    return 1
  fi
  note "New or unassigned drives (the boot drive and your pool drives are never listed):"
  pick_disk_list "Which drive do you want to connect? " "${devs[@]}"
}

confirm_erase() {
  say ""
  say "Warning: data will be erased"
  say "Everything on $1 will be permanently deleted."
  typed "$1" "Type the drive name exactly ($1) to continue: " || { say "Cancelled. Nothing was changed."; return 1; }
  typed "ERASE" "Type ERASE in capital letters to confirm: " || { say "Cancelled. Nothing was changed."; return 1; }
}

connect_flow() {
  connect_flow_run "$@"
  local rc=$?
  crit_release
  return "$rc"
}

# connect_flow [dev] [role] [force_erase: 1 = erase without asking, 2 = keep the files without asking] [already_confirmed]: add a drive to a pool.
connect_flow_run() {
  array_guard || return 1
  local dev=${1:-} role=${2:-} force=${3:-0} confirmed=${4:-0} label part mode="erase" idx uuid mp
  local gate=pre_change; [ "$confirmed" = 1 ] && gate=dry_gate
  need_tools || return 1
  [ -n "$dev" ] || { dev=$(pick_new_disk) || return 1; }
  refuse_unsafe_disk "$dev"
  describe_disk "$dev"
  if [ -z "$role" ]; then
    idx=$(choose "Use this drive for: " "Main pool (photos and files used by your services)" "Backup pool (daily copy of the Main pool)") || return 1
    if [ "$idx" = 0 ]; then role=main; else role=backup; fi
  fi
  pool_can_grow "$role" "this drive" || return 1
  label=$(take_label "$role")
  local base same=0 b
  base=$(disk_base_name "$dev")
  for b in $(all_branches); do [ "$(branch_base_name "$b")" = "$base" ] && same=$((same + 1)); done
  say "This drive: $base  ($dev)"
  say "It will be added to the $([ "$role" = main ] && echo Main || echo Backup) storage."
  [ "$same" -gt 0 ] && say "A drive with this name already exists, so drives with this name are numbered (1, 2, ...)."

  if [ "$force" = 2 ]; then
    local -a kparts; mapfile -t kparts < <(parts_of "$dev")
    if [ ${#kparts[@]} -eq 1 ] && [ "$(fs_type "${kparts[0]}")" = ext4 ]; then mode="keep"; part=${kparts[0]}
    else die "$dev does not have one ext4 partition, so its files cannot be kept."; fi
  elif [ "$force" != 1 ]; then
    local -a parts; mapfile -t parts < <(parts_of "$dev")
    if [ ${#parts[@]} -eq 1 ] && [ "$(fs_type "${parts[0]}")" = ext4 ]; then
      say "This drive already has one ext4 partition (label '$(fs_label "${parts[0]}")') with data on it."
      idx=$(choose "Choose an action: " "Keep the data and add the drive as it is" "Erase everything and format it") || return 1
      if [ "$idx" = 0 ]; then mode="keep"; part=${parts[0]}; fi
    fi
  fi

  if [ "$mode" = erase ]; then
    [ "$confirmed" = 1 ] || confirm_erase "$dev" || return 1
    $gate "Erase $dev and format it as a new drive ($base)." \
               "Stop the containers that use the $role pool briefly." \
               "Add the drive to the $role pool and mount the pool again." \
               "Start the containers again." && return 0
    if abort_requested; then ABORTED=1; note "Stopped before $dev was erased. Nothing was changed."; return 1; fi
    progress 10 "Erasing and formatting (this cannot be stopped)"
    part=$(format_disk "$dev" "$label") || return 1
    chosen_name_del "$label"
  else
    $gate "Keep the files on $dev and add the drive as it is ($base)." \
               "Stop the containers that use the $role pool briefly." \
               "Add the drive to the $role pool and mount the pool again." \
               "Start the containers again." && return 0
    if abort_requested; then ABORTED=1; note "Stopped before $dev was added. Nothing was changed."; return 1; fi
    progress 10 "Getting the drive ready"
    umount_disk_parts "$dev"
    local oldlabel; oldlabel=$(fs_label "$part")
    if [ "$oldlabel" != "$label" ]; then
      e2label "$part" "$label" || die "Could not set the label on $part"
      chosen_name_del "$label"
      carry_name "$oldlabel" "$label"
    fi
  fi

  pool_is_live "$role" || batch_barrier || { ABORTED=1; note "Stopped. Nothing was changed."; return 1; }
  crit_enter || true
  uuid=$(blkid -s UUID -o value "$part") || true
  [ -n "$uuid" ] || die "Could not read the UUID of $part"
  mp="$DISKS_DIR/$label"
  name_store_put "$label" "$base"
  apply_remembered_name "$dev" "$label"
  mark_added "$label"
  progress 60 "Mounting the drive"

  local live=0
  pool_is_live "$role" && live=1
  [ "$live" = 1 ] || stop_containers "$(role_pool "$role")"
  fstab_snapshot
  ensure_mp "$mp"
  fstab_add "UUID=$uuid  $mp  ext4  $BRANCH_OPTS  0  2"
  sd_reload
  if ! mount_fstab "$mp"; then fstab_rollback; die "Could not mount $part at $mp. fstab was restored."; fi
  progress 75 "Adding the drive to the $role pool"
  if [ "$live" = 1 ]; then
    if [ "$mode" = erase ] && [ "$role" = main ]; then give_to_owner "$mp"; fi
    fstab_set_pool "$role"
    sd_reload
    if pool_live_apply "$role"; then
      note "The drive joined the running $role pool. No container was stopped."
      [ "$role" = main ] && snapraid_active && snapraid_conf_write
      power_apply "$mp" "$role"
      say ""
      progress 100 "Done"
      say "Done. $(branch_name "$mp") is connected to the $role pool ($(role_pool "$role"))."
      log "connected $label ($part, $base) to $role (live)"
      return 0
    fi
    warn "The running pool could not take the drive directly, so the pool is mounted again the usual way."
    stop_containers "$(role_pool "$role")"
  fi
  if ! absorb_plain_pool "$role" "$mp"; then
    fstab_rollback
    pool_umount "$mp"
    start_containers
    die "The files in $(role_pool "$role") could not be moved to the new drive. fstab was restored."
  fi
  if [ "$mode" = erase ] && [ "$role" = main ]; then
    give_to_owner "$mp"
  fi
  if ! apply_pool "$role"; then
    fstab_rollback
    pool_umount "$mp"
    die "The $role pool did not mount. fstab was restored.$(hint " Check: sudo drives status" " Press Fix Drives, or look at the Drives screen.")"
  fi
  progress 90 "Starting the containers"
  start_containers
  power_apply "$mp" "$role"
  progress 100 "Done"
  say ""
  say "Done. $(branch_name "$mp") is connected to the $role pool ($(role_pool "$role"))."
  log "connected $label ($part, $base) to $role"
  return 0
}

