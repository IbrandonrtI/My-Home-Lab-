# ---------- power settings ----------
power_apply() {   # power_apply mountpoint role
  [ "$TEST_MODE" = 1 ] && return 0
  is_boot_section "$1" && return 0
  command -v hdparm >/dev/null 2>&1 || return 0
  local src dsk
  src=$(findmnt -no SOURCE "$1" 2>/dev/null) || return 0
  dsk=$(disk_of_part "$src"); [ -n "$dsk" ] || return 0
  if [ "$2" = backup ]; then
    hdparm -B 254 -S 120 "$dsk" >/dev/null 2>&1 && log "power: $dsk backup settings (sleep after 10 min idle)"
  else
    hdparm -B 254 -S 0 "$dsk" >/dev/null 2>&1 && log "power: $dsk main settings (never sleeps)"
  fi
  return 0
}

power_all() {
  local mp
  dry_gate "Apply the drive power settings to every pool drive (main drives never sleep, backup drives sleep after 10 minutes idle)." && return 0
  for mp in $(branches_of main); do mountpoint -q "$mp" && power_apply "$mp" main; done
  for mp in $(branches_of backup); do mountpoint -q "$mp" && power_apply "$mp" backup; done
  if [ -z "$(branches_of main)" ] && mountpoint -q "$MAIN_POOL"; then power_apply "$MAIN_POOL" main; fi
  say "Power settings applied (main drives never sleep, backup drives sleep after 10 minutes idle)."
  say "Some USB adapters ignore these commands. That is harmless."
}

need_tools() {
  local t missing=""
  for t in mergerfs rsync parted wipefs mkfs.ext4 e2label blkid partprobe; do
    command -v "$t" >/dev/null 2>&1 || missing="$missing $t"
  done
  if [ -n "$missing" ]; then
    note "Missing tools:$missing"
    note "Install them with:  sudo apt install -y mergerfs rsync parted e2fsprogs util-linux"
    return 1
  fi
}

# ---------- files that sit in a pool folder on the boot drive ----------
# Before any drive is assigned, /mnt/storage is a plain folder on the boot drive and the services already put folders
# (and maybe files) in it. A pool cannot be mounted over a folder that has things in it, so when the first drive of a pool
# is connected, whatever is in the folder moves onto the new drive first.
absorb_plain_pool() {   # absorb_plain_pool main|backup /mnt/disks/MAIN1  (the drive is already mounted)
  local role=$1 drive=$2 pool
  pool=$(role_pool "$role")
  mountpoint -q "$pool" && return 0
  [ -d "$pool" ] || return 0
  chattr -i "$pool" 2>/dev/null || true
  [ -n "$(ls -A "$pool" 2>/dev/null)" ] || return 0
  say "$pool already holds files on the boot drive ($(human "$(du -sb "$pool" 2>/dev/null | awk '{print $1}')")). They move onto the new drive first."
  rsync -aH --numeric-ids --ignore-existing --exclude=/lost+found "$pool/" "$drive/" || { warn "Copying the files to the new drive failed. Nothing was removed."; return 1; }
  if rsync -aHn --numeric-ids --ignore-existing --itemize-changes --exclude=/lost+found "$pool/" "$drive/" | grep -q '^[>c]'; then
    warn "Not every file reached the new drive. Nothing was removed from the boot drive."
    return 1
  fi
  find "$pool" -mindepth 1 -delete 2>/dev/null || true
  log "moved the files of $pool on the boot drive onto $drive"
  return 0
}

