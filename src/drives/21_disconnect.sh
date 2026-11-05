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

drain_branch() {   # copy everything from branch $1 to the emptiest other branch of the same role
  local mp=$1 role others o best="" bestfree=0 free used target pool
  role=$(branch_role "$mp"); pool=$(role_pool "$role")
  mapfile -t others < <(branches_of "$role" | grep -vx "$mp")
  for o in "${others[@]}"; do
    mountpoint -q "$o" || continue
    free=$(avail_bytes "$o")
    if [ "$free" -gt "$bestfree" ]; then best=$o; bestfree=$free; fi
  done
  used=$(used_bytes "$mp")
  if [ -z "$best" ] || [ "$bestfree" -lt $((used + DRAIN_SPARE_BYTES)) ]; then
    warn "No other $role drive has enough free space ($(human "$used") needed plus $(human "$DRAIN_SPARE_BYTES") spare)."
    return 1
  fi
  target=$best
  say "Copying $(human "$used") from $(branch_name "$mp") to $(branch_name "$target") (pass 1, services keep running)..."
  rsync -aH --numeric-ids --exclude=/lost+found "$mp/" "$target/" || { warn "Copy failed"; return 1; }
  stop_containers "$pool"
  say "Pass 2 (catching changes made during the first pass)..."
  rsync -aH --numeric-ids --exclude=/lost+found "$mp/" "$target/" || { warn "Second copy failed"; start_containers; return 1; }
  if rsync -aHn --numeric-ids --itemize-changes --exclude=/lost+found "$mp/" "$target/" | grep -q '^>f'; then
    warn "Verification found files that are not copied yet. Nothing was removed."
    start_containers
    return 1
  fi
  say "Verified: every file from $(branch_name "$mp") is also on $(branch_name "$target")."
  return 0
}

detach_branch() {   # detach_branch mountpoint [STEP...]  (leaves the data on the drive untouched; the STEPs are extra lines for the dry-run plan)
  local mp=$1 role label pool others dev part img
  shift
  role=$(branch_role "$mp"); label=$(branch_name "$mp"); pool=$(role_pool "$role")
  img=$(boot_image_of "$mp")
  mapfile -t others < <(branches_of "$role" | grep -vx "$mp")
  part=$(branch_part "$mp"); dev=""; [ -n "$part" ] && ! is_boot_section "$mp" && dev=$(disk_of_part "$part")
  local drain=0

  if is_boot_section "$mp" && mountpoint -q "$mp" && has_data "$mp"; then
    if [ ${#others[@]} -eq 0 ]; then
      note "$label holds files and there is no other $role drive to copy them to. Nothing was changed."
      return 1
    fi
    say "$label holds files. Removing the section deletes it, so they are copied to another $role drive first."
    drain=1
  fi

  if [ ${#others[@]} -eq 0 ]; then
    if [ "$role" = main ]; then
      note "$label is the only main drive. Removing it would take away the storage your services use."
      note "Add another main drive first (sudo drives > Add or remove drives > Connect a new drive), then try again."
      return 1
    fi
    warn "$label is the only backup drive. Backups will stop until another backup drive is connected."
    typed "REMOVE" "Type REMOVE to continue: " || { say "Cancelled."; return 1; }
  elif ! is_boot_section "$mp" && mountpoint -q "$mp" && has_data "$mp"; then
    say "$label holds files. They will disappear from the $role storage unless they are copied to another $role drive."
    if yn "Copy them to another $role drive first (recommended)?"; then
      drain=1
    else
      warn "Continuing without copying. The files stay on the drive but will not show in the pool."
      typed "CONTINUE" "Type CONTINUE to confirm: " || { say "Cancelled."; return 1; }
    fi
  fi

  local -a plan=()
  [ "$drain" = 1 ] && plan+=("Copy the files of $label to another $role drive and check every file.")
  plan+=("Stop the containers that use the $role storage for a minute.")
  if is_boot_section "$mp"; then plan+=("Take $label out of the $role storage and delete the section file (its space goes back to the boot drive).")
  else plan+=("Take $label out of the $role storage (the data on the drive is not touched)."); fi
  plan+=("Start the containers again." "$@")
  pre_change "${plan[@]}" && return 0
  if [ "$drain" = 1 ]; then drain_branch "$mp" || { note "Not removing $label."; return 1; }; fi

  if [ -z "${STOPPED// /}" ]; then stop_containers "$pool"; fi
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
  start_containers
  log "disconnected $label ($(basename "$mp")) from $role"
  if is_boot_section "$mp"; then
    rm -f "$img"
    name_store_del "$(basename "$mp")"
    chattr -i "$mp" 2>/dev/null || true
    rmdir "$mp" 2>/dev/null || true
    say "$label is removed. Its space went back to the boot drive."
  else
    say "$label is disconnected from the $role storage. The data on the drive was not touched."
  fi
  DETACHED_DEV=$dev
  return 0
}

disconnect_flow() {
  array_guard || return 1
  local mp dev
  mp=$(pick_branch "Which drive do you want to disconnect? ") || return 1
  DETACHED_DEV=""
  detach_branch "$mp" || return 1
  [ "$DRY_RUN" = 1 ] && return 0
  dev=$DETACHED_DEV
  is_boot_section "$mp" && return 0
  if [ "$TEST_MODE" != 1 ] && [ -n "$dev" ] && command -v udisksctl >/dev/null 2>&1; then
    if yn "Power the drive off so it is safe to unplug?"; then
      udisksctl power-off -b "$dev" >/dev/null 2>&1 && say "Powered off. You can unplug it." || say "Could not power it off. It is still safe to unplug now."
    fi
  else
    say "It is safe to unplug the drive now."
  fi
}

move_flow() {
  array_guard || return 1
  local mp role newrole part dev
  mp=$(pick_branch "Which drive do you want to move? ") || return 1
  role=$(branch_role "$mp"); newrole=$(other_role "$role")
  if is_boot_section "$mp"; then note "A boot drive section cannot be moved. Remove it (sudo drives > Add or remove drives > Disconnect) and add one to the other pool (Use part of the boot drive)."; return 1; fi
  part=$(branch_part "$mp"); [ -n "$part" ] || die "That drive is not connected, so it cannot be moved."
  dev=$(disk_of_part "$part")
  # everything that can still be refused or cancelled is checked BEFORE the drive leaves its pool
  need_tools || return 1
  grep -qx "$dev" <<<"$(protected_disks)" && die "$dev holds the operating system. Refusing."
  pool_can_grow "$newrole" "this drive" || return 1
  say "$(branch_name "$mp") will move from $role to $newrole storage."
  say "Its files are copied to another $role drive first, then the drive is erased and formatted for $newrole."
  yn "Continue?" || { say "Cancelled."; return 1; }
  confirm_erase "$dev" || return 1
  DETACHED_DEV=""
  detach_branch "$mp" "Then erase $dev, format it and add it to the $newrole storage." || return 1
  [ "$DRY_RUN" = 1 ] && return 0
  PENDING_NOTE="$(branch_name "$mp") already left the $role storage and was not added to the $newrole storage. Add it with:  sudo drives > Add or remove drives > Connect a new drive"
  connect_flow "$dev" "$newrole" 1 1 || { note ""; note "$PENDING_NOTE"; PENDING_NOTE=""; return 1; }
  PENDING_NOTE=""
}

