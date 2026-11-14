#!/usr/bin/env bash
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
reset_env() {
  if [ -n "$S" ]; then DRIVES_STATE_DIR="$S" bash "$DRIVES" test-cleanup >/dev/null 2>&1; rm -rf "$S"; fi
  chattr -i /mnt/test-main /mnt/test-backup /mnt/test-disks/* 2>/dev/null
  rm -rf /mnt/test-main /mnt/test-backup /mnt/test-disks 2>/dev/null
  S=$(mktemp -d); export DRIVES_STATE_DIR="$S"
}
cleanup() { reset_env; rm -rf "$S"; chattr -i /mnt/test-main /mnt/test-backup 2>/dev/null; rm -rf /mnt/test-main /mnt/test-backup /mnt/test-disks 2>/dev/null; }
trap cleanup EXIT
loop_of() { losetup -ln -O NAME,BACK-FILE | awk -v f="$S/disk$1.img" '$2 == f {print $1}'; }
make_part_disk() {
  local L; L=$(loop_of "$1")
  parted -s "$L" mklabel gpt mkpart p ext4 1MiB 100% >/dev/null 2>&1; partprobe "$L" >/dev/null 2>&1; sleep 1
  mkfs.ext4 -q -L OLDDATA "${L}p1" || return 1
  mkdir -p "$S/m"; mount "${L}p1" "$S/m" || return 1
  echo "old file of drive $1" >"$S/m/old.txt"; umount "$S/m"
}
wiz() { printf '%s' "$1" | timeout 180 $D wizard "${@:2}" 2>&1; }

reset_env; $D test-setup 1 300M >/dev/null 2>&1
OUT=$(wiz $'\n' --first-run)
has "one empty drive: the plain pool is suggested" "$OUT" "Suggested setup: Plain pool"
has "one empty drive: a yes or no question is asked" "$OUT" "Format this drive and set up the plain pool now? [Y/n]"
hasnt "no menu of setups is shown" "$OUT" "Which one do you want?"
hasnt "ERASE is not asked for an empty drive" "$OUT" "Type ERASE"
hasnt "no 'data will be erased' warning for an empty drive" "$OUT" "Warning: data will be erased"
has "the plan lists the empty drive" "$OUT" "Empty drive to format:"
has "pressing Enter builds the plain pool" "$OUT" "Plain pool is ready"
check "the Main pool is mounted" "$(mountpoint -q /mnt/test-main && echo yes || echo no)" "yes"

reset_env; $D test-setup 1 300M >/dev/null 2>&1
OUT=$(wiz $'n\n' --first-run)
has "answering n changes nothing" "$OUT" "Nothing was changed. The install continues without a data drive."
check "the Main pool is not mounted after n" "$(mountpoint -q /mnt/test-main && echo yes || echo no)" "no"
check "the answer is remembered so the install does not ask again" "$(cut -d'|' -f2 "$S/wizard" 2>/dev/null)" "not-now"

reset_env; $D test-setup 2 300M >/dev/null 2>&1
OUT=$(wiz $'\n' --first-run)
has "two empty drives: still the plain pool by default" "$OUT" "Format these 2 drives and set up the plain pool now? [Y/n]"
has "two empty drives: both are formatted" "$OUT" "Plain pool is ready"

reset_env; $D test-setup 2 300M >/dev/null 2>&1
make_part_disk 1
OUT=$(wiz $'3\n\n' --first-run)
has "a drive with files is still asked about" "$OUT" "What should be done with this drive?"
hasnt "no quick question when a drive with files is involved and skipped drives remain empty-less" "$OUT" "Type ERASE in capital letters to confirm: ERASE"
reset_env; $D test-setup 2 300M >/dev/null 2>&1
make_part_disk 1
OUT=$(wiz $'2\n1\nERASE\n' --first-run)
has "erasing a drive with files still needs ERASE" "$OUT" "Type ERASE in capital letters to confirm"

reset_env; $D test-setup 1 300M >/dev/null 2>&1
OUT=$(wiz $'1\nERASE\n')
has "a manual run of the wizard keeps the full menu" "$OUT" "Which one do you want?"
has "a manual run still asks for ERASE" "$OUT" "Type ERASE in capital letters"

echo
if [ "$bad" = 0 ]; then echo OK; else echo "FAILED: $bad"; exit 1; fi
