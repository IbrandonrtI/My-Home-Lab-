#!/usr/bin/env bash
# End-to-end test of `drives wizard` with drives that HOLD FILES: for each one the person chooses keep / erase / leave alone.
# Uses fake drives (loop files) and real mergerfs. Needs root, losetup, mergerfs, mkfs.ext4 and parted; where they are missing it
# says so and passes (the CI machine has no loop devices).
# Run: bash tests/t_wizard_keep.sh   (last line is OK or FAIL)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVES="$HERE/../scripts/drives"
bad=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
has() { case "$2" in *"$3"*) echo "ok   $1" ;; *) echo "FAIL $1   (missing: $3)"; bad=$((bad + 1)) ;; esac; }
hasnt() { case "$2" in *"$3"*) echo "FAIL $1   (should not be there: $3)"; bad=$((bad + 1)) ;; *) echo "ok   $1" ;; esac; }

if [ "$(id -u)" != 0 ] || ! command -v losetup >/dev/null || ! command -v mergerfs >/dev/null || ! command -v mkfs.ext4 >/dev/null \
   || ! command -v parted >/dev/null || ! command -v fallocate >/dev/null || ! losetup -f >/dev/null 2>&1; then
  echo "skipped: needs root, loop devices, mergerfs, mkfs.ext4 and parted (not available here)"; echo OK; exit 0
fi

export DRIVES_TEST=1 DRAIN_SPARE_BYTES=1000000
D="bash $DRIVES"
S=""
reset_env() {   # a new, clean set of fake drives
  if [ -n "$S" ]; then DRIVES_STATE_DIR="$S" bash "$DRIVES" test-cleanup >/dev/null 2>&1; rm -rf "$S"; fi
  chattr -i /mnt/test-main /mnt/test-backup /mnt/test-disks/* 2>/dev/null
  rm -rf /mnt/test-main /mnt/test-backup /mnt/test-disks 2>/dev/null
  S=$(mktemp -d); export DRIVES_STATE_DIR="$S"
}
cleanup() { reset_env; rm -rf "$S"; chattr -i /mnt/test-main /mnt/test-backup 2>/dev/null; rm -rf /mnt/test-main /mnt/test-backup /mnt/test-disks 2>/dev/null; }
trap cleanup EXIT
loop_of() { losetup -ln -O NAME,BACK-FILE | awk -v f="$S/disk$1.img" '$2 == f {print $1}'; }
settle() { sleep 1; }
make_part_disk() {   # make_part_disk N MB: drive N gets one ext4 partition (label OLDDATA) holding old.txt (and MB megabytes of filler)
  local L; L=$(loop_of "$1")
  parted -s "$L" mklabel gpt mkpart p ext4 1MiB 100% >/dev/null 2>&1; partprobe "$L" >/dev/null 2>&1; settle
  mkfs.ext4 -q -L OLDDATA "${L}p1" || return 1
  mkdir -p "$S/m"; mount "${L}p1" "$S/m" || return 1
  echo "old file of drive $1" >"$S/m/old.txt"
  [ "${2:-0}" -gt 0 ] && fallocate -l "${2}M" "$S/m/filler.bin"
  umount "$S/m"
}
make_whole_disk() {   # make_whole_disk N: drive N has a file system on the whole drive (no partition): its files cannot be kept
  local L; L=$(loop_of "$1")
  mkfs.ext4 -q -L WHOLE "$L" || return 1
  mkdir -p "$S/m"; mount "$L" "$S/m" || return 1
  echo "old" >"$S/m/old.txt"; umount "$S/m"
}
wiz() { printf '%s' "$1" | timeout 180 $D wizard "${@:2}" 2>&1; }

# 1. keep the files of one drive, the other is empty: the mirror keeps the files as the Main drive
reset_env; $D test-setup 2 300M >/dev/null 2>&1
make_part_disk 1 0
OUT=$(wiz $'1\n1\nmirror\nERASE\n')
has "the scan lists the drive with files and what is on it" "$OUT" "label 'OLDDATA'"
has "a keepable drive offers: keep" "$OUT" "Keep its files and use the drive as it is"
has "a keepable drive offers: erase" "$OUT" "Erase everything on it and use it as a new, empty drive"
has "a keepable drive offers: leave alone" "$OUT" "Leave it alone"
has "with kept files the mirror is suggested" "$OUT" "Mirror (nightly copy)   [mirror]"
has "with kept files the plain pool is the alternative" "$OUT" "Plain pool   [pool]"
hasnt "no ZFS suggestion when files are kept" "$OUT" "[zfs-mirror]"
has "the plan says the files are kept" "$OUT" "[its files are KEPT]"
has "the plan lists the kept drive" "$OUT" "are KEPT as they are"
has "the setup is built" "$OUT" "Mirror (nightly copy) is ready"
check "the old file is still there in the Main storage" "$(cat /mnt/test-main/old.txt 2>/dev/null)" "old file of drive 1"
check "the erase warning lists only the empty drive" "$(printf '%s' "$OUT" | sed -n '/ERASE WARNING/,/KEPT as they are/p' | grep -c '^  - /dev/')" "1"

# 2. erase the drive that holds files: it is used like an empty drive, and the old file is gone
reset_env; $D test-setup 2 300M >/dev/null 2>&1
make_part_disk 1 0
OUT=$(wiz $'2\n1\nmirror\nERASE\n')
has "an erased drive's files are named in the warning" "$OUT" "<- it has files"
hasnt "nothing is said to be kept" "$OUT" "are KEPT as they are"
has "the first suggestion is the same as for two empty drives" "$OUT" "Mirror (nightly copy)   [mirror]"
has "ZFS is offered again when nothing is kept" "$OUT" "[zfs-mirror]"
has "the setup is built after erasing" "$OUT" "Mirror (nightly copy) is ready"
check "the old file is gone" "$(ls /mnt/test-main/old.txt /mnt/test-backup/old.txt 2>/dev/null | wc -l)" "0"

# 3. leave the only drive with files alone: nothing is used, nothing changes
reset_env; $D test-setup 1 300M >/dev/null 2>&1
make_part_disk 1 0
OUT=$(wiz $'3\n')
has "leaving it alone says no drive is left" "$OUT" "No drive is left to use"
check "no storage was made" "$(cat "$S/fstab" 2>/dev/null | grep -c .)" "0"
L=$(loop_of 1); mkdir -p "$S/m"; mount "${L}p1" "$S/m"
check "the drive still has its file" "$(cat "$S/m/old.txt" 2>/dev/null)" "old file of drive 1"; umount "$S/m"

# 4. a drive that cannot be kept (file system on the whole drive) only offers erase or leave alone
reset_env; $D test-setup 1 300M >/dev/null 2>&1
make_whole_disk 1
OUT=$(wiz $'2\n')
has "a not-keepable drive says why" "$OUT" "Its files cannot be kept"
hasnt "a not-keepable drive does not offer to keep" "$OUT" "Keep its files and use the drive as it is"
has "it can still be erased or left alone" "$OUT" "Erase everything on it and use it as a new, empty drive"

# 5. --yes never decides about files: the drive with files is left alone
reset_env; $D test-setup 2 300M >/dev/null 2>&1
make_part_disk 1 0
OUT=$(printf 'pool\nERASE\n' | timeout 180 $D wizard --yes --dry-run 2>&1)
has "--yes leaves the drive with files alone" "$OUT" "left alone"
hasnt "--yes does not plan to erase it" "$OUT" "<- it has files"

# 6. two drives with files, both kept: only the plain pool, both keep their files
reset_env; $D test-setup 2 300M >/dev/null 2>&1
make_part_disk 1 0; make_part_disk 2 0
OUT=$(wiz $'1\n1\n1\npool\n')
has "two kept drives offer the plain pool" "$OUT" "Plain pool   [pool]"
hasnt "two kept drives do not offer the mirror" "$OUT" "[mirror]"
has "the pool is built" "$OUT" "Plain pool is ready"
hasnt "nothing is erased, so there is no ERASE question" "$OUT" "Type ERASE"
check "both old files are in the pool" "$(ls /mnt/test-main/old.txt 2>/dev/null | wc -l)" "1"
check "the pool has both drives" "$(grep -c '^UUID=' "$S/fstab" 2>/dev/null)" "2"

# 7. the copy drive is smaller than the files that stay: no mirror is suggested
reset_env
truncate -s 100M "$S/disk2.img"; $D test-setup 1 300M >/dev/null 2>&1; $D test-setup 2 300M >/dev/null 2>&1
make_part_disk 1 150
OUT=$(wiz $'1\n1\npool\n')
hasnt "a too small copy drive means no mirror" "$OUT" "[mirror]"
has "the plain pool is suggested instead" "$OUT" "Plain pool   [pool]"

# 8. ZFS and RAID are refused from the full list when files are kept
reset_env; $D test-setup 3 300M >/dev/null 2>&1
make_part_disk 1 0
OUT=$(wiz $'1\n2\n7\n')
has "from the full list a RAID setup is refused with a reason" "$OUT" "erases every drive, so it cannot keep the files"
check "the old file is untouched" "$(L=$(loop_of 1); mkdir -p "$S/m"; mount "${L}p1" "$S/m" && cat "$S/m/old.txt"; umount "$S/m" 2>/dev/null)" "old file of drive 1"

if [ "$bad" -eq 0 ]; then echo OK; else echo "FAIL ($bad)"; exit 1; fi
