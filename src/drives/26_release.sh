# ---------- release all drives ----------
release_flow() {   # take every drive out of both pools; the files on the drives are not touched
  local mp p dir
  if array_active; then array_release_flow; return $?; fi
  local -a all=()
  mapfile -t all < <(all_branches; parity_mounts)
  if [ ${#all[@]} -eq 0 ]; then
    say "No drive is assigned to a pool, so there is nothing to release."
    return 1
  fi
  say "These drives are assigned to the pools:"
  for mp in "${all[@]}"; do
    case "$(basename "$mp")" in "$PARITY_PREFIX"[0-9]*) say "  - $(branch_base_name "$mp")  (SnapRAID protection)" ;; *) say "  - $(branch_name "$mp")  ($(branch_role "$mp"))" ;; esac
  done
  say ""
  say "Releasing takes every drive out of both pools. The files on the drives are NOT touched and nothing is erased."
  say "Afterwards $MAIN_POOL and $BACKUP_POOL are plain folders on the boot drive, and you choose the drives again with:"
  say "  sudo drives     (Connect a new drive; for a drive with files, choose 'Keep the data')"
  say "Immich, Nextcloud and the other services that use the storage are stopped for a minute."
  yn "Release all drives?" || { say "Cancelled. Nothing was changed."; return 1; }
  pre_change "Stop the containers that use the storage." \
             "Take all ${#all[@]} drives out of both pools. The files on the drives are not touched." \
             "Make $MAIN_POOL and $BACKUP_POOL plain folders on the boot drive, then start the containers." && return 0

  stop_containers "$MAIN_POOL" "$BACKUP_POOL" "$DISKS_DIR"
  sync_fs "${all[@]}"
  for p in "$BACKUP_POOL" "$MAIN_POOL"; do
    if mountpoint -q "$p" && ! pool_umount "$p"; then
      start_containers
      die "Could not unmount $p (something is using it). Nothing was changed."
    fi
  done
  fstab_snapshot
  for mp in "${all[@]}"; do
    mountpoint -q "$mp" && { umount "$mp" 2>/dev/null || umount -l "$mp"; }
    fstab_remove_mp "$mp"
  done
  [ -n "$(branches_of main)" ] || fstab_remove_mp "$MAIN_POOL"
  [ -n "$(branches_of backup)" ] || fstab_remove_mp "$BACKUP_POOL"
  [ -n "$(preset_current)" ] && { snapraid_forget; say "The record of the ready-made setup was removed (and, for SnapRAID, its settings and schedule)."; }
  sd_reload
  for mp in "${all[@]}"; do
    is_boot_section "$mp" || name_store_del "$(basename "$mp")"
    chattr -i "$mp" 2>/dev/null || true
    rmdir "$mp" 2>/dev/null || true
  done
  for dir in "$MAIN_POOL" "$BACKUP_POOL"; do
    mountpoint -q "$dir" && continue
    chattr -i "$dir" 2>/dev/null || true
    mkdir -p "$dir"
  done
  # the folders the services expect, so they keep running on the boot drive until a drive is chosen again
  mkdir -p "$MAIN_POOL/immich" "$MAIN_POOL/nextcloud"
  give_to_owner "$MAIN_POOL/immich"
  chown 33:33 "$MAIN_POOL/nextcloud" 2>/dev/null || true
  start_containers
  log "released all pool drives (${#all[@]})"
  say ""
  say "Done. No drive is assigned to a pool now. Their files are still on the drives."
  ls "$BOOT_SECTION_DIR"/*.img >/dev/null 2>&1 && say "The files of the boot drive sections are kept in $BOOT_SECTION_DIR. Adding a section again (sudo drives bootsection) can use them."
  say "Choose the drives you want with:  sudo drives"
}

