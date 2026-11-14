test_setup() {
  [ "$TEST_MODE" = 1 ] || die "Test setup only works with DRIVES_TEST=1"
  local i f count=${1:-3} size=${2:-1G}
  for i in $(seq 1 "$count"); do
    f="$STATE_DIR/disk$i.img"
    [ -f "$f" ] || truncate -s "$size" "$f"
    losetup -j "$f" | grep -q . || losetup -f -P --show "$f" >/dev/null
  done
  say "Test disks:"; losetup -ln -O NAME,BACK-FILE | awk -v s="$STATE_DIR/" 'index($2, s) == 1'
}

test_cleanup() {
  [ "$TEST_MODE" = 1 ] || die "Test cleanup only works with DRIVES_TEST=1"
  local mp dev
  pool_umount "$BACKUP_POOL"; pool_umount "$MAIN_POOL"
  for mp in "$DISKS_DIR"/*; do [ -d "$mp" ] && mountpoint -q "$mp" && umount "$mp"; done
  for dev in $(losetup -ln -O NAME,BACK-FILE | awk -v s="$STATE_DIR/disk" 'index($2, s) == 1 {print $1}'); do losetup -d "$dev"; done
  rm -rf "$BOOT_SECTION_DIR"
  rm -f "$STATE_DIR"/disk*.img "$STATE_DIR"/fstab "$STATE_DIR"/fstab.bak-drives-*
  say "Test setup removed."
}

