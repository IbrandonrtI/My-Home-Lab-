# ---------- mount helpers ----------
give_to_owner() {   # give_to_owner PATH: the user who runs the lab owns it (nothing happens when that user is unknown)
  id -u "$OWNER" >/dev/null 2>&1 && chown "$OWNER:$OWNER" "$1"
  return 0
}

ensure_mp() {
  mkdir -p "$1"
  if ! mountpoint -q "$1"; then chattr +i "$1" 2>/dev/null || true; fi
}

mount_fstab() {   # fd 9 is the lock (and fd 8 the pool lock of a batch): the mergerfs daemon must not inherit them
  # From the control panel the daemon of a pool would live inside the panel's service, and a restart of the panel (an upgrade does that) would end it and
  # unmount the pool. In its own scope it belongs to the system instead.
  if [ "$PANEL_MODE" = 1 ] && [ -d "${SYSTEMD_DIR:-/run/systemd/system}" ] && command -v systemd-run >/dev/null 2>&1; then
    systemd-run --scope --quiet --collect --slice=system.slice mount -T "$FSTAB" "$1" 6>&- 8>&- 9>&- || return 1
  else
    mount -T "$FSTAB" "$1" 6>&- 8>&- 9>&- || return 1
  fi
  mountpoint -q "$1"   # a mount that "succeeds" without mounting counts as a failure
}

pool_is_live() {   # pool_is_live main|backup -> 0 when that pool is mounted right now as a mergerfs pool that can take a new drive without stopping anything
  local pool
  pool=$(role_pool "$1") || return 1
  command -v setfattr >/dev/null 2>&1 || return 1
  mountpoint -q "$pool" 2>/dev/null || return 1
  [ "$(findmnt -no FSTYPE "$pool" 2>/dev/null)" = fuse.mergerfs ] && [ -e "$pool/.mergerfs" ]
}

pool_umount() {
  local mp=$1
  mountpoint -q "$mp" || return 0
  umount "$mp" 2>/dev/null && return 0
  fusermount -u "$mp" 2>/dev/null && return 0
  warn "$mp is busy, using a lazy unmount"
  umount -l "$mp"
}

apply_pool() {   # rebuild the pool line for a role and (re)mount the pool
  local role=$1 mp
  mp=$(role_pool "$role")
  ensure_mp "$mp"
  fstab_set_pool "$role"
  sd_reload
  pool_umount "$mp"
  if [ -n "$(branches_of "$role")" ]; then mount_fstab "$mp" || return 1; fi
  [ "$role" = main ] && snapraid_active && snapraid_conf_write   # the drives of the Main storage changed: SnapRAID has to know
  return 0
}

# ---------- disks ----------
disk_of_part() {
  local src=${1%%\[*}
  lsblk -nsrpo NAME,TYPE "$src" 2>/dev/null | awk '$2 == "disk" || $2 == "loop" {print $1; exit}'
}

protected_disks() {
  {
    local t s
    for t in / /boot /boot/efi /var/lib/docker; do
      s=$(findmnt -nT "$t" -o SOURCE 2>/dev/null)
      [ -n "$s" ] && disk_of_part "$s"
    done
    swapon --noheadings --show=NAME 2>/dev/null | while read -r s; do disk_of_part "$s"; done
  } | sort -u
}

busy_disks() {   # drives with something mounted outside the desktop's /media auto-mount (in use: never offered, never erased)
  findmnt -rn -o SOURCE,TARGET 2>/dev/null | while read -r src tgt; do
    case "$src" in /dev/*) ;; *) continue ;; esac
    case "$tgt" in /media/*|/run/media/*) continue ;; esac
    disk_of_part "$src"
  done | sort -u
}

managed_disks() {
  local mp p
  for mp in $(all_branches) $(parity_mounts); do
    p=$(branch_part "$mp")
    [ -n "$p" ] && disk_of_part "$p"
  done | sort -u
  array_disks
}

all_disks() {
  lsblk -dnpo NAME,TYPE 2>/dev/null | awk '$2 == "disk" && $1 !~ /zram|\/ram[0-9]/ {print $1}'
  if [ "$TEST_MODE" = 1 ]; then
    losetup -ln -O NAME,BACK-FILE 2>/dev/null | awk -v s="$STATE_DIR/disk" 'index($2, s) == 1 {print $1}'
  fi
}

legacy_disks() {   # drives mounted directly at a pool path (before conversion to a pool)
  local mp s
  array_active && return 0      # a RAID array is mounted at the Main pool path: its drives are not "the old single data drive"
  for mp in "$MAIN_POOL" "$BACKUP_POOL"; do
    mountpoint -q "$mp" || continue
    [ "$(findmnt -no FSTYPE "$mp")" = ext4 ] || continue
    s=$(findmnt -no SOURCE "$mp")
    disk_of_part "$s"
  done | sort -u
}

refuse_unsafe_disk() {   # refuse_unsafe_disk /dev/sdX: stops the whole command for the system drive or a drive in use
  grep -qx "$1" <<<"$(protected_disks)" && die "$1 holds the operating system. Refusing."
  grep -qx "$1" <<<"$(busy_disks)" && die "$1 is in use (something on it is mounted). Refusing."
  return 0
}

candidate_disks() {
  local excl d
  excl=$( { protected_disks; managed_disks; legacy_disks; busy_disks; } | sort -u )
  for d in $(all_disks | sort -u); do
    grep -qx "$d" <<<"$excl" && continue
    echo "$d"
  done
}

