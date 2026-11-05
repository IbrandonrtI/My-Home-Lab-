# ---------- adopt the current single data drive ----------
adopt_flow() {
  array_guard || return 1
  need_tools || return 1
  [ -z "$(branches_of main)" ] || { note "A main pool already exists. Nothing to convert."; return 1; }
  mountpoint -q "$MAIN_POOL" || { note "$MAIN_POOL is not mounted. Plug the drive in, run sudo hdd-recover, then try again."; return 1; }
  local src fst uuid part label cur before after pool="$MAIN_POOL" mp
  src=$(findmnt -no SOURCE "$pool"); fst=$(findmnt -no FSTYPE "$pool")
  [ "$fst" = ext4 ] || { note "$pool is $fst, not a plain ext4 drive. Cannot convert."; return 1; }
  part=${src%%\[*}
  uuid=$(blkid -s UUID -o value "$part"); [ -n "$uuid" ] || die "Could not read the UUID of $part"
  cur=$(fs_label "$part")
  label=$(next_label main); mp="$DISKS_DIR/$label"
  say ""
  say "This converts your current data drive into the first drive of the main pool."
  say "  Drive:        $(disk_summary "$(disk_of_part "$part")")"
  say "  Now:          mounted directly at $pool"
  say "  After:        mounted as a pool drive, and $pool becomes the pool"
  say "  Your files are not moved or copied. Containers using $pool will be stopped for a minute."
  yn "Continue?" || { say "Cancelled."; return 1; }
  pre_change "Stop the containers that use $pool for a minute." \
             "Mount the drive as a pool drive and make $pool the pool. Your files are not moved or copied." \
             "Check the pool shows the same files, then start the containers again." && return 0

  before=$(ls -A "$pool" | wc -l)
  stop_containers "$pool"
  fstab_snapshot
  sync_fs "$pool"
  umount "$pool" 2>/dev/null || { start_containers; die "Could not unmount $pool (something is using it). Nothing was changed."; }
  if [ "$cur" != "$label" ]; then e2label "$part" "$label" || { fstab_rollback; mount_fstab "$pool"; start_containers; die "Could not set the label."; }; fi
  ensure_mp "$mp"
  fstab_remove_mp "$pool"
  fstab_add "UUID=$uuid  $mp  ext4  $BRANCH_OPTS  0  2"
  sd_reload
  if ! mount_fstab "$mp"; then
    fstab_rollback; mount_fstab "$pool"; start_containers
    die "Could not mount the drive at $mp. fstab was restored and the old mount is back."
  fi
  if ! apply_pool main; then
    fstab_rollback; pool_umount "$pool"; mountpoint -q "$mp" && umount "$mp"
    mount_fstab "$pool"; start_containers
    die "The pool did not mount. fstab was restored and the old mount is back."
  fi
  after=$(ls -A "$pool" | wc -l)
  if [ "$before" != "$after" ]; then
    warn "The pool shows $after items but the drive showed $before. Rolling back."
    fstab_rollback; pool_umount "$pool"; mountpoint -q "$mp" && umount "$mp"
    mount_fstab "$pool"; start_containers
    die "Rolled back. Nothing was lost."
  fi
  start_containers
  power_apply "$mp" main
  name_store_put "$label" "$(disk_base_name "$(disk_of_part "$part")")"
  log "adopted $part as $label; pool at $pool"
  say ""
  say "Done. $pool is now a pool containing $(branch_name "$mp"). Check: sudo drives status"
  if [ "$TEST_MODE" != 1 ]; then
    say "Reminder: replace the old STORAGE lines in root's crontab with the new one (see the guide)."
  fi
  return 0
}

