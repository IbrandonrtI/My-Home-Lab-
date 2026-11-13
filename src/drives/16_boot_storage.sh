# ---------- the boot drive as the default storage of the Main pool ----------
# The services must keep running no matter what. With no drive in Main, or with its drive missing, /mnt/storage is a plain folder on the
# boot drive and the services use it. As soon as a drive is in Main, the drive is the storage. What was saved on the boot drive in the
# meantime is not lost: it lies under the mounted pool, and `sudo drives moveboot` copies it to the pool (and asks before it removes the old files).
IMMICH_DIRS="upload library thumbs encoded-video profile backups"      # Immich looks for a hidden .immich file in each of these

main_boot_flag() { printf '%s' "$STATE_DIR/main-on-boot"; }       # exists while Main should have a drive but the boot drive is the storage
boot_kept_flag() { printf '%s' "$STATE_DIR/boot-files-kept"; }    # exists while copies are left on the boot drive under the mounted pool

boot_folder_ready() {   # the Main pool path becomes a usable plain folder (with the folders Immich and Nextcloud expect); nothing happens while a pool is mounted there
  mountpoint -q "$MAIN_POOL" 2>/dev/null && return 0
  chattr -i "$MAIN_POOL" 2>/dev/null || true
  local d
  mkdir -p "$MAIN_POOL/immich" "$MAIN_POOL/nextcloud" || return 1
  give_to_owner "$MAIN_POOL/immich"
  chown 33:33 "$MAIN_POOL/nextcloud" 2>/dev/null || true
  # Immich refuses to start when its folders exist without the marker file (it would otherwise show an empty library by mistake). This folder is
  # the storage on purpose, so the markers are made here.
  for d in $IMMICH_DIRS; do
    mkdir -p "$MAIN_POOL/immich/$d"
    [ -e "$MAIN_POOL/immich/$d/.immich" ] || : >"$MAIN_POOL/immich/$d/.immich"
    give_to_owner "$MAIN_POOL/immich/$d"; give_to_owner "$MAIN_POOL/immich/$d/.immich"
  done
  return 0
}

BOOT_VIEW=""; BOOT_UNDER=""
boot_view_open() {   # sets BOOT_UNDER to the folder of the Main pool that lies UNDER the mounted pool (what was saved while the boot drive was the storage)
  local fsroot rel
  fsroot=$(findmnt -nT "$(dirname "$MAIN_POOL")" -o TARGET 2>/dev/null) || return 1
  [ -n "$fsroot" ] || return 1
  BOOT_VIEW=$(mktemp -d "$STATE_DIR/bootview.XXXXXX" 2>/dev/null) || return 1
  if ! mount --bind "$fsroot" "$BOOT_VIEW" 6>&- 8>&- 9>&-; then rmdir "$BOOT_VIEW" 2>/dev/null; BOOT_VIEW=""; return 1; fi
  rel=${MAIN_POOL#"$fsroot"}; rel=${rel#/}
  BOOT_UNDER="$BOOT_VIEW/$rel"
  [ -d "$BOOT_UNDER" ] || { boot_view_close; return 1; }
  return 0
}

boot_view_close() {
  [ -n "$BOOT_VIEW" ] || return 0
  umount "$BOOT_VIEW" 2>/dev/null || umount -l "$BOOT_VIEW" 2>/dev/null
  rmdir "$BOOT_VIEW" 2>/dev/null
  BOOT_VIEW=""; BOOT_UNDER=""
  return 0
}

boot_has_files() {   # boot_has_files FOLDER: real files (the Immich marker files and empty folders do not count)
  [ -d "$1" ] && [ -n "$(find "$1" ! -type d ! -name .immich ! -path '*/lost+found/*' -print -quit 2>/dev/null)" ]
}

boot_files_bytes() { du -sb --exclude=.immich --exclude=lost+found "$1" 2>/dev/null | awk '{print $1 + 0}'; }

boot_files_pending() {   # 0 when the Main pool is mounted and files saved on the boot drive lie under it
  mountpoint -q "$MAIN_POOL" 2>/dev/null || return 1
  [ -n "$(branches_of main)" ] || return 1
  array_active && return 1
  local rc=1
  if boot_view_open; then boot_has_files "$BOOT_UNDER" && rc=0; boot_view_close; fi
  return $rc
}

main_drive_missing() {   # 0 when Main has drives in its setup, but the pool is not mounted (a drive is missing or unplugged)
  array_active && return 1
  { [ -n "$(branches_of main)" ] || pool_in_fstab "$MAIN_POOL"; } || return 1
  ! mountpoint -q "$MAIN_POOL" 2>/dev/null
}

main_fallback_start() {   # the boot drive is the storage until the Main drive is back
  boot_folder_ready || return 1
  mkdir -p "$STATE_DIR" 2>/dev/null
  [ -e "$(main_boot_flag)" ] || date '+%F %T' >"$(main_boot_flag)"
  log "Main drive not available: the services use the boot drive"
  return 0
}

# ---------- sudo drives guard: run at start-up, before Docker ----------
guard_flow() {
  array_active && return 0
  if ! main_drive_missing; then
    # no drive in Main: a plain folder on the boot drive; a mounted pool: nothing to do
    mountpoint -q "$MAIN_POOL" 2>/dev/null || boot_folder_ready
    if boot_files_pending; then date '+%F %T' >"$(boot_kept_flag)" 2>/dev/null; else rm -f "$(main_boot_flag)"; fi
    return 0
  fi
  local mp all=1
  # (the pool is only mounted when EVERY Main drive is there: a pool over a missing drive would look empty)
  for mp in $(branches_of main); do mountpoint -q "$mp" || mount_fstab "$mp" 2>/dev/null || all=0; done
  if [ "$all" = 1 ] && mount_fstab "$MAIN_POOL" 2>/dev/null; then
    log "guard: the Main pool is mounted"
    boot_files_pending && date '+%F %T' >"$(boot_kept_flag)" 2>/dev/null
    rm -f "$(main_boot_flag)"
    return 0
  fi
  main_fallback_start
  note "The Main drive was not found. The services use the boot drive for now."
  return 0
}

# ---------- sudo drives moveboot ----------
moveboot_core() {   # moveboot_core: the containers are stopped. Copies what lies under the pool to the pool, checks it, asks before removing it. 0 = nothing left behind
  local src=$BOOT_UNDER bytes free diff
  bytes=$(boot_files_bytes "$src"); free=$(df -B1 --output=avail "$MAIN_POOL" 2>/dev/null | tail -1 | tr -d ' ')
  if [ -n "$free" ] && [ "${bytes:-0}" -gt "$free" ] 2>/dev/null; then
    note "The pool has only $(human "$free") free, and $(human "$bytes") are waiting on the boot drive. Nothing was copied."
    return 1
  fi
  say "Copying $(human "${bytes:-0}") from the boot drive to the Main pool ..."
  progress 0 "Copying files"
  if ! rsync_bytes_run "${bytes:-0}" "Copying files" -aH --numeric-ids --ignore-existing --exclude=/lost+found "$src/" "$MAIN_POOL/"; then
    warn "Copying failed. Nothing was removed from the boot drive."
    return 1
  fi
  diff=$(rsync -aHn --numeric-ids --itemize-changes --exclude=.immich --exclude=/lost+found "$src/" "$MAIN_POOL/" 2>/dev/null | grep -c '^[<>c][fL]')
  if [ "${diff:-0}" != 0 ]; then
    warn "$diff file(s) exist both on the boot drive and in the pool with different content. The pool's version was kept, and nothing was removed from the boot drive."
    date '+%F %T' >"$(boot_kept_flag)" 2>/dev/null
    return 1
  fi
  say "Every file is on the pool now."
  # (the terminal asks; the panel's "Move the files" button was the person's yes, and every file was just checked)
  if [ "${PANEL_MOVEBOOT:-0}" = 1 ] || { [ "$PANEL_MODE" != 1 ] && yn_yes "Remove the old copies from the boot drive now (they only use up space there)?"; }; then
    find "$src" -mindepth 1 ! -type d ! -name .immich -delete 2>/dev/null
    find "$src" -mindepth 1 -depth -type d -empty -delete 2>/dev/null
    rm -f "$(boot_kept_flag)" "$(main_boot_flag)"
    log "moved the files saved on the boot drive to the Main pool and removed the copies"
    say "The old copies are removed."
    return 0
  fi
  date '+%F %T' >"$(boot_kept_flag)" 2>/dev/null
  rm -f "$(main_boot_flag)"
  log "copied the files saved on the boot drive to the Main pool; the copies stay"
  say "The old copies stay on the boot drive (hidden while the pool is mounted). Remove them later with:  sudo drives moveboot"
  return 0
}

moveboot_flow() {
  array_guard || return 1
  if [ -z "$(branches_of main)" ]; then
    say "No drive is in the Main pool, so the boot drive is the storage right now. There is nothing to move."
    return 0
  fi
  if ! mountpoint -q "$MAIN_POOL"; then
    note "The Main pool is not mounted, so its drive is missing and the services use the boot drive for now."
    note "Plug the drive in and run:  sudo drives remount"
    return 1
  fi
  boot_view_open || die "Could not look at the boot drive folder under the Main pool."
  if ! boot_has_files "$BOOT_UNDER"; then
    boot_view_close
    rm -f "$(boot_kept_flag)" "$(main_boot_flag)"
    say "No files are waiting on the boot drive. Everything is on the Main pool."
    return 0
  fi
  say "Files were saved on the boot drive while the Main pool had no drive: $(human "$(boot_files_bytes "$BOOT_UNDER")")."
  say "They are not visible while the pool is mounted. This copies them to the pool (nothing is replaced), checks them, and only then asks about removing the old ones."
  if pre_change "Stop the containers that use the Main pool." \
                "Copy the files from the boot drive to the Main pool and check every file." \
                "Ask whether to remove the old copies from the boot drive." \
                "Start the containers again."; then
    boot_view_close; return 0
  fi
  stop_containers "$MAIN_POOL"
  local rc=0
  moveboot_core || rc=$?
  boot_view_close
  start_containers
  return $rc
}

panel_moveboot_flow() {   # the Drives tab's "Move the files to the drive" button: copy, check every file, remove the old copies, start the services again
  PANEL_MOVEBOOT=1
  progress 0 "Looking at the files"
  moveboot_flow
  local rc=$?
  progress 100 "Done"
  return $rc
}

moveboot_offer() {   # after the Main pool came back (Fix Drives): the containers are stopped; asks in the terminal, only says so in the panel
  boot_files_pending || return 0
  boot_view_open || return 0
  if [ "$PANEL_MODE" = 1 ] || [ "$DRY_RUN" = 1 ]; then
    note "Files saved on the boot drive while Main had no drive ($(human "$(boot_files_bytes "$BOOT_UNDER")")) are waiting. Copy them to the pool with:  sudo drives moveboot"
    date '+%F %T' >"$(boot_kept_flag)" 2>/dev/null
    boot_view_close; return 0
  fi
  say ""
  say "Files were saved on the boot drive while the Main pool had no drive: $(human "$(boot_files_bytes "$BOOT_UNDER")")."
  if yn "Copy them to the Main pool now?"; then moveboot_core || true
  else date '+%F %T' >"$(boot_kept_flag)" 2>/dev/null; say "Later:  sudo drives moveboot"; fi
  boot_view_close
}
