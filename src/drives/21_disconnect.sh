# ---------- disconnect ----------
has_data() { [ -n "$(find "$1" -mindepth 1 -maxdepth 1 ! -name lost+found -print -quit 2>/dev/null)" ]; }

avail_bytes() { df -B1 --output=avail "$1" | tail -1 | tr -d ' '; }
used_bytes()  { df -B1 --output=used  "$1" | tail -1 | tr -d ' '; }
total_bytes() { echo $(( $(used_bytes "$1") + $(avail_bytes "$1") )); }   # as the pool or drive reports it: used + free

pick_branch() {
  local -a items=() mps=()
  local mp own=""
  # the list below only looks: each name is worked out once (see with_name_cache); the cache is gone before anything can change
  if [ -z "${NAME_CACHE:-}" ]; then NAME_CACHE=$(mktemp -d 2>/dev/null) && own=1 || NAME_CACHE=""; fi
  for mp in $(all_branches); do
    mps+=("$mp")
    if mountpoint -q "$mp"; then
      items+=("$(branch_name "$mp")  ($(branch_role "$mp"))  used $(human "$(used_bytes "$mp")") of $(human "$(total_bytes "$mp")")")
    else
      items+=("$(branch_name "$mp")  ($(branch_role "$mp"))  NOT CONNECTED")
    fi
  done
  if [ -n "$own" ]; then rm -rf "$NAME_CACHE"; NAME_CACHE=""; fi
  if [ ${#mps[@]} -eq 0 ]; then note "No drives are connected to a pool yet."; return 1; fi
  local idx
  idx=$(choose "${1:-Which drive? }" "${items[@]}") || return 1
  echo "${mps[$idx]}"
}

not_leaving() {   # a filter: the mount points on stdin that do not leave their pool in this batch
  local l
  while IFS= read -r l; do
    local x leave=0
    for x in "${PANEL_LEAVING[@]}"; do [ "$x" = "$l" ] && leave=1; done
    [ "$leave" = 1 ] || printf '%s\n' "$l"
  done
  return 0
}

drain_branch() {   # (the real work is below; the lock on the drive that is copied to is let go however it ends)
  drain_branch_run "$@"
  local rc=$?
  target_unlock
  return "$rc"
}

drain_branch_run() {   # copy everything from branch $1 to the emptiest other branch of the same role
  local mp=$1 role used target pool
  local -a cands=()
  role=$(branch_role "$mp"); pool=$(role_pool "$role")
  mapfile -t cands < <(branches_of "$role" | grep -vx "$mp" | not_leaving)      # a drive that leaves in the same batch is not a place to copy to
  used=$(used_bytes "$mp")
  if ! target=$(space_pick "$mp" "$used" "${cands[@]}") || [ -z "$target" ]; then
    warn "No other $role drive has enough free space ($(human "$used") needed plus $(human "$DRAIN_SPARE_BYTES") spare). $(branch_name "$mp") stays where it is."
    NOROOM=1
    return 1
  fi
  if ! target_lock "$target"; then ABORTED=1; space_release "$mp"; note "Stopped before copying. Nothing was changed."; return 1; fi
  if abort_requested; then ABORTED=1; space_release "$mp"; note "Stopped before copying. Nothing was changed."; return 1; fi
  say "Copying $(human "$used") from $(branch_name "$mp") to $(branch_name "$target") (pass 1, services keep running)..."
  progress 5 "Copying files to $(branch_name "$target")"
  if ! rsync_run 5 60 "Copying files" -aH --numeric-ids --exclude=/lost+found "$mp/" "$target/"; then
    space_release "$mp"
    if abort_requested; then ABORTED=1; note "Stopped while copying. Nothing was removed. The files copied so far stay as extra copies on $(branch_name "$target")."; else warn "Copy failed"; fi
    return 1
  fi
  space_release "$mp"
  if abort_requested; then ABORTED=1; note "Stopped. Nothing was changed."; return 1; fi
  target_unlock      # (the other drives may copy to this drive while this one waits for them)
  batch_barrier || { ABORTED=1; note "Stopped. Nothing was changed."; return 1; }
  target_lock "$target" || { ABORTED=1; note "Stopped. Nothing was changed."; return 1; }
  crit_enter abortable || { ABORTED=1; note "Stopped. Nothing was changed."; return 1; }      # from here the containers are stopped and the pool changes: one drive at a time
  progress 62 "Stopping the containers"
  stop_containers "$pool"
  say "Pass 2 (catching changes made during the first pass)..."
  progress 66 "Copying the last changes"
  if ! rsync_run 66 74 "Copying the last changes" -aH --numeric-ids --exclude=/lost+found "$mp/" "$target/"; then
    if abort_requested; then ABORTED=1; note "Stopped. Nothing was removed."; else warn "Second copy failed"; fi
    start_containers; crit_release; return 1
  fi
  if rsync -aHn --numeric-ids --itemize-changes --exclude=/lost+found "$mp/" "$target/" | grep -q '^>f'; then
    warn "Verification found files that are not copied yet. Nothing was removed."
    start_containers
    crit_release
    return 1
  fi
  say "Verified: every file from $(branch_name "$mp") is also on $(branch_name "$target")."
  return 0
}

detach_branch() {   # (the real work is below; the pool lock is let go however it ends)
  detach_branch_run "$@"
  local rc=$?
  crit_release
  return "$rc"
}

detach_branch_run() {   # detach_branch mountpoint [STEP...]  (leaves the data on the drive untouched; the STEPs are extra lines for the dry-run plan)
  local mp=$1 role label pool others dev part img
  shift
  role=$(branch_role "$mp"); label=$(branch_name "$mp"); pool=$(role_pool "$role")
  img=$(boot_image_of "$mp")
  mapfile -t others < <(branches_of "$role" | grep -vx "$mp" | not_leaving)      # (a drive that leaves in the same batch does not count: nothing is copied to it)
  part=$(branch_part "$mp"); dev=""; [ -n "$part" ] && ! is_boot_section "$mp" && dev=$(disk_of_part "$part")
  local drain=0 copyq=""

  if is_boot_section "$mp" && [ "$KEEP_IMG" != 1 ] && mountpoint -q "$mp" && has_data "$mp"; then
    if [ ${#others[@]} -eq 0 ]; then
      warn "$label holds files and there is no other $role drive to copy them to."
      warn "Taking the section out deletes it, and every file in it is permanently lost."
      typed "ERASE" "Type ERASE to delete the section and its files: " || { say "Cancelled. Nothing was changed."; return 1; }
    else
      say "$label holds files. Removing the section deletes it, so they are copied to another $role drive first."
      drain=1
    fi
  fi

  if [ ${#others[@]} -eq 0 ]; then
    if [ "$role" = main ]; then
      warn "$label is the only main drive. Taking it out leaves the Main pool empty."
      warn "The services that use it (Immich, Nextcloud, FileBrowser...) stay stopped until a main drive is added again. Nothing on the drive is deleted."
    else
      warn "$label is the only backup drive. Backups will stop until another backup drive is connected."
    fi
    typed "REMOVE" "Type REMOVE to continue: " || { say "Cancelled."; return 1; }
  elif { ! is_boot_section "$mp" || [ "$KEEP_IMG" = 1 ]; } && mountpoint -q "$mp" && has_data "$mp"; then
    say "$label holds files. They will disappear from the $role pool unless they are copied to another $role drive."
    if [ "$PANEL_MODE" = 1 ] && [ -n "$PANEL_COPY" ]; then copyq=$PANEL_COPY      # the control panel already asked
    elif yn "Copy them to another $role drive first (recommended)?"; then copyq=yes
    else copyq=no; fi
    if [ "$copyq" = yes ]; then
      drain=1
    else
      warn "Continuing without copying. The files stay on the drive but will not show in the pool."
      typed "CONTINUE" "Type CONTINUE to confirm: " || { say "Cancelled."; return 1; }
    fi
  fi

  local -a plan=()
  [ "$drain" = 1 ] && plan+=("Copy the files of $label to another $role drive and check every file.")
  plan+=("Stop the containers that use the $role pool for a minute.")
  if is_boot_section "$mp"; then plan+=("Take $label out of the $role pool and delete the section file (its space goes back to the boot drive).")
  else plan+=("Take $label out of the $role pool (the data on the drive is not touched)."); fi
  plan+=("Start the containers again." "$@")
  pre_change "${plan[@]}" && return 0
  if [ "$drain" = 1 ]; then drain_branch "$mp" || { note "Not removing $label."; return 1; }; fi

  if [ "$CRIT_DEPTH" = 0 ] && abort_requested; then ABORTED=1; note "Stopped. Nothing was changed."; return 1; fi
  batch_barrier || { ABORTED=1; note "Stopped. Nothing was changed."; return 1; }
  crit_enter abortable || { ABORTED=1; note "Stopped. Nothing was changed."; return 1; }
  progress 75 "Stopping the containers"
  if [ -z "${STOPPED// /}" ]; then stop_containers "$pool"; fi
  progress 78 "Taking the drive out of the pool"
  sync_fs "$mp"
  fstab_snapshot
  pool_umount "$pool"
  mountpoint -q "$mp" && { umount "$mp" 2>/dev/null || umount -l "$mp"; }
  fstab_remove_mp "$mp"
  sd_reload
  if ! apply_pool "$role"; then
    fstab_rollback
    mount_fstab "$mp" 2>/dev/null; mount_fstab "$pool" 2>/dev/null
    die "The pool did not mount after removing $label. fstab was restored."
  fi
  progress 84 "Starting the containers"
  start_containers
  log "disconnected $label ($(basename "$mp")) from $role"
  if is_boot_section "$mp"; then
    if [ "$KEEP_IMG" != 1 ]; then rm -f "$img"; fi      # (a section that moves to the other pool keeps its file)
    name_store_del "$(basename "$mp")"
    chattr -i "$mp" 2>/dev/null || true
    rmdir "$mp" 2>/dev/null || true
    if [ "$KEEP_IMG" = 1 ]; then say "$label is out of the $role pool."; else say "$label is removed. Its space went back to the boot drive."; fi
  else
    say "$label is disconnected from the $role pool. The data on the drive was not touched."
  fi
  DETACHED_DEV=$dev
  return 0
}

disconnect_flow() {
  array_guard || return 1
  local mp dev
  if [ "$PANEL_MODE" = 1 ]; then mp=$(panel_branch "$PANEL_ID") || return 1
  else mp=$(pick_branch "Which drive do you want to disconnect? ") || return 1; fi
  DETACHED_DEV=""
  detach_branch "$mp" || return 1
  [ "$DRY_RUN" = 1 ] && return 0
  dev=$DETACHED_DEV
  is_boot_section "$mp" && return 0
  if [ "$PANEL_MODE" = 1 ]; then      # a spare drive now: do not power it off, it can be added to a pool or erased from the panel
    say "The drive is a spare drive now. It is safe to unplug, or you can add it to a pool or erase it in the Drives tab."
  elif [ "$TEST_MODE" != 1 ] && [ -n "$dev" ] && command -v udisksctl >/dev/null 2>&1; then
    if yn "Power the drive off so it is safe to unplug?"; then
      udisksctl power-off -b "$dev" >/dev/null 2>&1 && say "Powered off. You can unplug it." || say "Could not power it off. It is still safe to unplug now."
    fi
  else
    say "It is safe to unplug the drive now."
  fi
}

move_flow() {
  array_guard || return 1
  local mp role newrole part dev keep=no oldname
  if [ "$PANEL_MODE" = 1 ]; then mp=$(panel_branch "$PANEL_ID") || return 1; keep=$PANEL_KEEP
  else mp=$(pick_branch "Which drive do you want to move? ") || return 1; fi
  role=$(branch_role "$mp"); newrole=$(other_role "$role"); oldname=$(branch_name "$mp")
  if is_boot_section "$mp"; then bootmove_flow "$mp"; return $?; fi
  part=$(branch_part "$mp"); [ -n "$part" ] || die "That drive is not connected, so it cannot be moved."
  dev=$(disk_of_part "$part")
  # everything that can still be refused or cancelled is checked BEFORE the drive leaves its pool
  need_tools || return 1
  grep -qx "$dev" <<<"$(protected_disks)" && die "$dev holds the operating system. Refusing."
  pool_can_grow "$newrole" "this drive" || return 1
  if [ "$keep" = yes ]; then      # the drive keeps its files, so it must have exactly one ext4 partition to be added as it is
    local -a kparts; mapfile -t kparts < <(parts_of "$dev")
    if ! { [ ${#kparts[@]} -eq 1 ] && [ "$(fs_type "${kparts[0]}")" = ext4 ]; }; then note "$dev does not have one ext4 partition, so its files cannot be kept. Nothing was changed."; return 1; fi
  fi
  say "$(branch_name "$mp") will move from $role to $newrole pool."
  if [ "$keep" = yes ]; then
    say "The drive keeps its files and is added to the $newrole pool as it is, so the files on it show up in the $newrole pool."
  else
    say "The drive is erased and formatted for $newrole, so the files on it are gone from the drive."
  fi
  if [ "$PANEL_MODE" != 1 ]; then yn "Continue?" || { say "Cancelled."; return 1; }; fi
  if [ "$keep" = yes ]; then
    if [ "$PANEL_MODE" = 1 ]; then typed KEEP "Type KEEP to add the files on the drive to the $newrole pool as they are: " || { say "Cancelled. Nothing was changed."; return 1; }; fi
  else
    confirm_erase "$dev" || return 1
  fi
  DETACHED_DEV=""
  PROG_LO=0; PROG_HI=55      # leaving the pool is the first part of the bar, joining the other pool the rest
  if [ "$keep" = yes ]; then detach_branch "$mp" "Then add $dev to the $newrole pool with its files as they are." || { PROG_HI=100; return 1; }
  else detach_branch "$mp" "Then erase $dev, format it and add it to the $newrole pool." || { PROG_HI=100; return 1; }; fi
  [ "$DRY_RUN" = 1 ] && { PROG_HI=100; return 0; }
  PENDING_NOTE="$(branch_name "$mp") already left the $role pool and was not added to the $newrole pool. Add it with:  sudo drives > Add or remove drives > Connect a new drive"
  PROG_LO=55; PROG_HI=100
  if ! connect_flow "$dev" "$newrole" "$([ "$keep" = yes ] && echo 2 || echo 1)" 1; then
    if [ "$ABORTED" = 1 ]; then      # Stop was pressed before the drive was erased: it goes back where it came from, with all its files
      PROG_LO=0; PROG_HI=100
      progress 90 "Putting the drive back"
      say "Stopped. Putting $oldname back into the $role pool with its files..."
      ABORT_IGNORE=1
      if connect_flow "$dev" "$role" 2 1; then PUTBACK=1; say "$oldname is back in the $role pool."
      else note ""; note "$PENDING_NOTE"; fi
      ABORT_IGNORE=0; PENDING_NOTE=""
      return 1
    fi
    PROG_LO=0; note ""; note "$PENDING_NOTE"; PENDING_NOTE=""; return 1
  fi
  PROG_LO=0
  PENDING_NOTE=""
}

