
# ---------- moving the Main pool into a new ZFS / RAID setup ----------
# The new setup is built on spare drives and filled from the old Main pool while that is still in use (the containers are stopped).
# Only when the copy is checked does the new setup take the Main path; then the old Main drives are released (their files are not touched).
ARRAY_MOUNT=""      # where zfs_build / md_build mount the new setup (empty = the Main path)

main_is_pool() { [ -n "$(branches_of main)" ] && mountpoint -q "$MAIN_POOL" && [ "$(findmnt -no FSTYPE "$MAIN_POOL" 2>/dev/null)" = fuse.mergerfs ]; }
pool_used_bytes() { df -B1 --output=used "$MAIN_POOL" 2>/dev/null | awk 'NR == 2 {print $1 + 0}'; }
migrate_need_bytes() { local u=${1:-0}; echo $((u + u / 50 + 67108864)); }      # the files, 2% extra for the way the new file system stores them, and 64 MB

fstab_move_mp() {   # fstab_move_mp OLD NEW: the line that mounts at OLD mounts at NEW
  local tmp; tmp=$(mktemp)
  awk -v o="$1" -v n="$2" '!/^[[:space:]]*#/ && $2 == o { sub(o, n) } { print }' "$FSTAB" >"$tmp" && cat "$tmp" >"$FSTAB"
  rm -f "$tmp"
  log "fstab move mount point: $1 -> $2"
}

migrate_copy() {   # copy everything from the Main pool into the new setup, then compare
  local rc=0 changed
  local -a skip=(--exclude=/.mergerfs --exclude=/lost+found)
  say "Copying the files of the Main pool into the new setup. This can take a long time on big drives..."
  rsync -aHAX --numeric-ids "${skip[@]}" "$MAIN_POOL"/ "$MIGRATE_DIR"/ 9>&- >&2 || rc=$?
  case $rc in 0|24) ;; *) warn "The copy stopped with an error (code $rc)."; return 1 ;; esac
  say "Checking the copy..."
  changed=$(rsync -aHAXni --numeric-ids --delete "${skip[@]}" "$MAIN_POOL"/ "$MIGRATE_DIR"/ 9>&- 2>/dev/null | grep -cE '^(>f|\*deleting|cL|hf)') || true
  if [ "${changed:-0}" -gt 0 ]; then warn "$changed file(s) are not the same in the copy."; return 1; fi
  say "The copy is complete and matches."
}

migrate_discard() {   # migrate_discard ID DISK...: take the half-built new setup apart again (the old Main pool was not changed)
  local id=$1 d; shift
  pool_umount "$MIGRATE_DIR" || true
  if [ "$(preset_kind "$id")" = zfs ]; then
    zpool destroy -f "$ZFS_POOL_NAME" 9>&- >/dev/null 2>&1 || true
    rm -f "$ZFS_SCRUB_CRON" "$KEY_DIR/$ZFS_POOL_NAME.key"
  else
    fstab_remove_mp "$MIGRATE_DIR"
    md_undo "$@"
    md_conf_forget
    sd_reload
  fi
  for d in "$@"; do wipefs -a "$d" >/dev/null 2>&1 || true; done
  rmdir "$MIGRATE_DIR" 2>/dev/null || true
}

migrate_retire_main() {   # the old Main drives leave the Main pool; their files stay on them and they are spare drives now
  local mp
  for mp in "$@"; do
    mountpoint -q "$mp" && { umount "$mp" 2>/dev/null || umount -l "$mp"; }
    fstab_remove_mp "$mp"
  done
  sd_reload
  for mp in "$@"; do
    is_boot_section "$mp" || name_store_del "$(basename "$mp")"
    chattr -i "$mp" 2>/dev/null || true
    rmdir "$mp" 2>/dev/null || true
  done
}

migrate_switch() {   # migrate_switch ID: the new setup (mounted at MIGRATE_DIR, filled) takes the Main path; the old drives are released
  local id=$1 kind
  local -a old_mps=()
  kind=$(preset_kind "$id")
  mapfile -t old_mps < <(branches_of main)
  sync_fs "$MIGRATE_DIR" "${old_mps[@]}"
  if ! pool_umount "$MAIN_POOL" || mountpoint -q "$MAIN_POOL"; then warn "Could not unmount $MAIN_POOL (something is using it)."; return 1; fi
  fstab_snapshot
  fstab_remove_mp "$MAIN_POOL"
  local ok=1
  if [ "$kind" = zfs ]; then
    zfs set mountpoint="$MAIN_POOL" "$ZFS_POOL_NAME" 9>&- >&2 || ok=0
    mountpoint -q "$MAIN_POOL" || ok=0
  else
    pool_umount "$MIGRATE_DIR" || ok=0
    fstab_move_mp "$MIGRATE_DIR" "$MAIN_POOL"
    sd_reload
    [ "$ok" = 1 ] && { mount_fstab "$MAIN_POOL" || ok=0; }
  fi
  if [ "$ok" != 1 ]; then
    if [ "$kind" = zfs ]; then zfs set mountpoint="$MIGRATE_DIR" "$ZFS_POOL_NAME" >/dev/null 2>&1 || true; fi
    fstab_rollback
    apply_pool main || warn "The old Main pool could not be mounted again. Run  sudo drives remount"
    return 1
  fi
  migrate_retire_main "${old_mps[@]}"
  rmdir "$MIGRATE_DIR" 2>/dev/null || true
  log "Main moved into a $id setup; released: ${old_mps[*]}"
  return 0
}
