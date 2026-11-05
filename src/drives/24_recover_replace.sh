# ---------- remount (after an unplug or a power cut) ----------
remount_flow() {
  array_guard || return 1
  local mp fail=0
  if [ -z "$(all_branches)" ] && ! pool_in_fstab "$MAIN_POOL" && ! pool_in_fstab "$BACKUP_POOL"; then
    note "No drive is assigned to a pool, so there is nothing to remount."
    note "Choose the drives first:  sudo drives"
    return 1
  fi
  pre_change "Stop the containers that use the storage." \
             "Unmount the pools and the drives, then mount every drive and pool again from the saved setup." \
             "Apply the drive power settings and start the containers again." && return 0
  stop_containers "$MAIN_POOL" "$BACKUP_POOL" "$DISKS_DIR"
  # pools first, then the drives under them
  pool_umount "$BACKUP_POOL" 2>/dev/null
  pool_umount "$MAIN_POOL" 2>/dev/null
  for mp in $(all_branches); do
    mountpoint -q "$mp" && { umount -l "$mp" 2>/dev/null; }
  done
  sleep 2
  for mp in $(all_branches); do
    if ! mount_fstab "$mp" 2>/dev/null; then
      if [ "$(branch_role "$mp")" = main ]; then
        echo "Drive not found. Check the cable. ($(branch_name "$mp"))"
        fail=1
      else
        warn "Backup drive $(branch_name "$mp") not found."
      fi
    fi
  done
  # the backup pool does not depend on the main drives: bring it back even when a main drive is missing
  if [ -n "$(branches_of backup)" ]; then
    mount_fstab "$BACKUP_POOL" || warn "The backup pool did not mount."
  fi
  if [ "$fail" = 1 ]; then
    HOLD_HINT="They stay stopped on purpose: with a main drive missing they would write to an incomplete storage. Plug the drive in and run  sudo drives remount  again. If it is dead:  sudo drives replace"
    return 1
  fi
  # main storage: the pool, or the plain drive before it is converted
  if pool_in_fstab "$MAIN_POOL"; then
    mount_fstab "$MAIN_POOL" || { echo "The main pool did not mount. Check the cable."; return 1; }
  fi
  power_all >/dev/null 2>&1
  start_containers
  echo "Recovered."
}

# ---------- replace a dead drive ----------
missing_branches() {   # missing_branches main|backup -> mount points of pool drives whose drive cannot be found
  local mp
  for mp in $(branches_of "$1"); do
    is_boot_section "$mp" && continue
    [ -n "$(branch_part "$mp")" ] || echo "$mp"
  done
}

backup_candidates() {   # folders that may hold the latest backup (a folder with main/ inside), best guess first
  local dest="" conf="${BACKUP_CONF:-/etc/homelab-backup.conf}"
  [ -r "$BACKUP_STATUS_FILE" ] && dest=$(awk -F'|' 'NR == 1 {print $3}' "$BACKUP_STATUS_FILE")
  printf '%s\n' "${DRIVES_RESTORE_SRC:-}" "$dest" "$BACKUP_POOL"
  # shellcheck disable=SC1090
  if [ -r "$conf" ] && { [ "$TEST_MODE" != 1 ] || [ -n "${BACKUP_CONF:-}" ]; }; then ( DEST_FALLBACK=""; . "$conf" >/dev/null 2>&1; printf '%s\n' "$DEST_FALLBACK" ); fi
}

find_backup_source() {   # prints the folder that holds main/, or fails
  local c
  while read -r c; do
    [ -n "$c" ] || continue
    if [ -d "$c/main" ] && has_data "$c/main"; then echo "$c"; return 0; fi
  done < <(backup_candidates)
  return 1
}

show_backup_source() {   # show_backup_source folder -> asks to continue when the last backup did not end OK
  local src=$1 stamp="" result="" dest=""
  say "Backup copy to restore from: $src/main"
  if [ -r "$BACKUP_STATUS_FILE" ]; then
    IFS='|' read -r stamp result dest _ <"$BACKUP_STATUS_FILE"
    say "Last backup run: $stamp  result: $result  destination: $dest"
    if [ "$result" != OK ]; then
      warn "The last backup run did not end with OK. The copy may be incomplete."
      yn "Use this copy anyway?" || return 1
    fi
    if [ "$dest" != "$src" ]; then
      warn "The last backup run wrote to $dest, but the copy found is in $src."
      yn "Use $src anyway?" || return 1
    fi
  else
    warn "There is no record of a backup run. I cannot tell how old this copy is."
    yn "Use this copy anyway?" || return 1
  fi
  return 0
}

stat_num() {   # stat_num "Total transferred file size" file -> the number, without commas
  awk -F': ' -v k="$1" 'index($0, k ":") == 1 {gsub(/[^0-9]/, "", $2); print $2; exit}' "$2"
}

restore_files() {   # restore_files folder  (main pool mounted, containers stopped): preview, ask, copy only what is missing, verify
  local src=$1 base out list n bytes avail miss tag
  base="$src/main/"
  tag=$(date +%Y%m%d-%H%M%S)
  out="$STATE_DIR/restore-$tag.out"; list="$STATE_DIR/restore-$tag.txt"
  mkdir -p "$STATE_DIR"
  say ""
  say "Checking what is missing from $MAIN_POOL (nothing is copied yet)..."
  if ! rsync -aHn --numeric-ids --ignore-existing --exclude=/lost+found --itemize-changes --stats "$base" "$MAIN_POOL/" >"$out" 2>"$out.err"; then
    warn "The check failed: $(tail -3 "$out.err" | tr '\n' ' ')"
    return 1
  fi
  grep -E '^[<>ch][fLDS]' "$out" | sed -E 's/^[^ ]+ //' >"$list" || true
  n=$(wc -l <"$list" | tr -d ' ')
  bytes=$(stat_num "Total transferred file size" "$out"); bytes=${bytes:-0}
  if [ "$n" -eq 0 ]; then
    say "Nothing is missing. Every file in the backup is already in $MAIN_POOL."
    return 0
  fi
  avail=$(avail_bytes "$MAIN_POOL")
  say ""
  say "Missing from the pool but present in the backup: $n files, $(human "$bytes")"
  say "First 20:"
  head -20 "$list" | sed 's/^/  /'
  [ "$n" -gt 20 ] && say "  ... and $((n - 20)) more. Full list: $list"
  say ""
  say "What this will and will not do:"
  say "  - Files that are already in the pool are never overwritten."
  say "  - Files you deleted since the last backup come back too (the backup still has them)."
  say "  - Files created or changed since the last backup are not in the backup, so they cannot come back."
  if [ "$bytes" -gt $((avail - DRAIN_SPARE_BYTES)) ]; then
    warn "Not enough free space in $MAIN_POOL: $(human "$avail") free, $(human "$bytes") needed plus $(human "$DRAIN_SPARE_BYTES") spare."
    return 1
  fi
  typed "RESTORE" "Type RESTORE (capitals) to copy these $n files: " || { say "Cancelled. Nothing was copied."; return 1; }
  if [ -z "${STOPPED// /}" ]; then   # the check above changes nothing: the containers are stopped only now, for the copy
    pre_change "Stop the containers that use the main storage." \
               "Copy the $n missing files ($(human "$bytes")) from the backup into the main storage. Files already there are never overwritten." \
               "Check that every file is there, then start the containers again." && return 0
    stop_containers "$MAIN_POOL"
    HOLD_HINT="The containers stay stopped until the restore is checked. Run  sudo drives restore  again, or  sudo drives remount  to start them without restoring."
  fi
  say "Copying (the services stay stopped)..."
  local prog=--info=stats1
  [ -t 1 ] && prog=--info=progress2
  rsync -aH --numeric-ids --ignore-existing --exclude=/lost+found "$prog" "$base" "$MAIN_POOL/" || { warn "The copy stopped with an error."; return 1; }
  local -a mains=()
  mapfile -t mains < <(branches_of main)
  sync_fs "${mains[@]}" "$MAIN_POOL"
  say ""
  say "Checking that every file in the backup is now in the pool..."
  miss=$(comm -23 -z \
    <(cd "$src/main" && find . -path ./lost+found -prune -o \( -type f -o -type l \) -print0 | sort -z) \
    <(cd "$MAIN_POOL" && find . -path ./lost+found -prune -o \( -type f -o -type l \) -print0 | sort -z) | tr '\0' '\n')
  if [ -n "$miss" ]; then
    warn "These files from the backup are still missing in the pool (first 20):"
    printf '%s\n' "$miss" | head -20 | sed 's/^/  /' >&2
    return 1
  fi
  say "Verified: all $n restored files, and every other file in the backup, are in the pool."
  log "restored $n files ($(human "$bytes")) from $src/main into $MAIN_POOL"
  return 0
}

after_restore_hints() {
  say ""
  say "Next steps:"
  say "  - Check a few things in Immich, Nextcloud and FileBrowser."
  if docker_ok && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx nextcloud; then
    say "  - Tell Nextcloud about the restored files:  docker exec -u www-data nextcloud php occ files:scan --all"
  fi
  say "  - Run the backup again when you are happy:  sudo homelab-backup"
}

restore_flow() {   # restore only the missing files from the backup into the main pool
  need_tools || return 1
  mountpoint -q "$MAIN_POOL" || { note "$MAIN_POOL is not mounted. Connect the drive and run sudo drives remount first."; return 1; }
  local src
  src=$(find_backup_source) || { note "No backup copy of the main storage was found, so there is nothing to restore from."; return 1; }
  show_backup_source "$src" || { say "Cancelled."; return 1; }
  restore_files "$src" || return 1
  [ "$DRY_RUN" = 1 ] && return 0
  HOLD_HINT=""
  start_containers
  after_restore_hints
  return 0
}

replace_flow() {
  array_guard || return 1
  need_tools || return 1
  local -a miss=() items=()
  local role m mp idx label pool src dev part uuid size need have o left
  for role in main backup; do
    while read -r m; do [ -n "$m" ] && miss+=("$m"); done < <(missing_branches "$role")
  done
  if [ ${#miss[@]} -eq 0 ]; then
    say "No pool drive is missing, so there is nothing to replace."
    say "  - A drive that was only unplugged: plug it in and run  sudo drives remount"
    say "  - A working drive you want to swap: use  sudo drives  > Add or remove drives > Disconnect, then Connect"
    return 1
  fi
  for m in "${miss[@]}"; do items+=("$(branch_name "$m")  ($(branch_role "$m"))  not found"); done
  say "Pool drives that cannot be found:"
  idx=$(choose "Which drive is dead? " "${items[@]}") || return 1
  mp=${miss[$idx]}; role=$(branch_role "$mp"); label=$(basename "$mp"); pool=$(role_pool "$role")
  local shown; shown=$(branch_name "$mp")

  say ""
  say "$shown will be replaced by a new drive. The new drive takes its place in the $role storage and is named by what it is."
  if [ "$role" = main ]; then
    say "The files that were on the dead drive are copied back from the backup. Only missing files are copied."
    src=$(find_backup_source) || { note "No backup copy of the main storage was found. Nothing was changed."; return 1; }
    show_backup_source "$src" || { say "Cancelled. Nothing was changed."; return 1; }
    say "Measuring the backup copy (this can take a minute)..."
    need=$(du -sb "$src/main" 2>/dev/null | awk '{print $1}'); need=${need:-0}
    have=0
    for o in $(branches_of main); do mountpoint -q "$o" && [ -n "$(branch_part "$o")" ] && have=$((have + $(used_bytes "$o"))); done
    need=$((need > have ? need - have : 0))
    say "The backup holds about $(human "$need") more than the remaining main drives. The new drive should be larger than that."
  else
    say "A new backup drive starts empty. The next backup run copies everything to it again."
    say "Older versions of deleted files (the _deleted folders) that were on the dead drive are gone."
    need=0
  fi

  dev=$(pick_new_disk) || return 1
  refuse_unsafe_disk "$dev"
  describe_disk "$dev"
  size=$(lsblk -bdno SIZE "$dev" | tr -d ' ')
  if [ "$role" = main ] && [ "${#miss[@]}" -eq 1 ] && [ "$size" -lt $((need + DRAIN_SPARE_BYTES)) ]; then
    warn "This drive ($(human "$size")) is smaller than the files to restore ($(human "$need")) plus $(human "$DRAIN_SPARE_BYTES") spare."
    typed "CONTINUE" "Type CONTINUE to use it anyway, or press Enter to cancel: " || { say "Cancelled. Nothing was changed."; return 1; }
  fi
  confirm_erase "$dev" || return 1
  pre_change "Stop the containers that use the $role storage." \
             "Erase $dev and format it as the new drive for $shown." \
             "Add it to the $role storage and mount the pool again." \
             "$([ "$role" = main ] && echo "Copy the missing files back from the backup, then start the containers." || echo "Start the containers. The next backup run fills the new drive.")" && return 0

  stop_containers "$pool"
  if [ "$role" = main ]; then
    HOLD_HINT="The containers stay stopped until the drive is replaced and the files are restored. Continue with:  sudo drives replace  or  sudo drives restore"
  fi
  pool_umount "$pool"
  mountpoint -q "$mp" && { umount "$mp" 2>/dev/null || umount -l "$mp"; }
  part=$(format_disk "$dev" "$label") || return 1
  uuid=$(blkid -s UUID -o value "$part") || true
  [ -n "$uuid" ] || die "Could not read the UUID of $part"
  fstab_snapshot
  fstab_remove_mp "$mp"
  ensure_mp "$mp"
  fstab_add "UUID=$uuid  $mp  ext4  $BRANCH_OPTS  0  2"
  sd_reload
  if ! mount_fstab "$mp"; then fstab_rollback; die "Could not mount $part at $mp. fstab was restored."; fi
  if [ "$role" = main ]; then give_to_owner "$mp"; fi
  name_store_put "$label" "$(disk_base_name "$dev")"
  log "replaced dead drive $label ($shown) with $part (UUID $uuid) in the $role pool"

  left=$(for m in $(missing_branches "$role"); do printf '%s, ' "$(branch_name "$m")"; done)
  if [ -n "${left// /}" ]; then
    say ""
    say "$(branch_name "$mp") is replaced. Other $role drives are still missing: ${left%, }"
    say "The $role pool cannot start until all of them are replaced. Run  sudo drives replace  again."
    return 0
  fi
  if ! apply_pool "$role"; then
    fstab_rollback
    pool_umount "$pool"
    die "The $role pool did not mount. fstab was restored. Check: sudo drives status"
  fi
  power_apply "$mp" "$role"
  say ""
  say "$(branch_name "$mp") is in place and the $role pool is mounted."

  if [ "$role" = main ]; then
    restore_files "$src" || { warn "The restore is not finished. The containers stay stopped."; return 1; }
    HOLD_HINT=""
    start_containers
    after_restore_hints
  else
    start_containers
    local bcmd="${HOMELAB_BACKUP_CMD:-$(command -v homelab-backup || echo /usr/local/sbin/homelab-backup)}"
    if [ -x "$bcmd" ] && yn "Run the backup now to fill the new drive (it can take a long time)?"; then
      "$bcmd" 9>&- || warn "The backup run reported an error. Read: sudo tail -20 /var/log/homelab-backup.log"
    else
      say "Run  sudo homelab-backup  when you are ready. The 6:00 backup also fills the drive."
    fi
  fi
  say ""
  say "Done. If the old drive ever turns up again, do not plug it in next to the new one: the computer sees both as the same drive."
  return 0
}

