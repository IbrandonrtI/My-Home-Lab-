#!/usr/bin/env bash
# End-to-end test of the Stage 4 words of `drives panel` (add, wipe, disconnect, move) with FAKE drives (loop files) and real mergerfs.
# Every choice of the Drives tab is tried: keep or erase the files, copy them to the old pool or not, and what happens when a typed word is missing.
# Needs root, losetup, mergerfs, mkfs.ext4 and parted; where they are missing it says so and passes.
# Run: bash tests/t_drivepanel4.sh   (last line is OK or FAIL)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVES="$HERE/../scripts/drives"
bad=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
has() { case "$2" in *"$3"*) echo "ok   $1" ;; *) echo "FAIL $1   (missing: $3)   got: $(printf '%s' "$2" | tail -4)"; bad=$((bad + 1)) ;; esac; }
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
P() { timeout 120 $D panel "$@" </dev/null 2>&1; }
fstab_lines() { grep -c '^UUID=' "$S/fstab" 2>/dev/null; }
actions() { $D panel actions 2>/dev/null; }
jq_() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
# 3 empty drives: main A and B, backup C
setup3() {
  reset_env; $D test-setup 3 300M >/dev/null 2>&1
  L1=$(loop_of 1); L2=$(loop_of 2); L3=$(loop_of 3)
  P add "${L1#/dev/}" main erase "$L1" ERASE >/dev/null; P add "${L2#/dev/}" main erase "$L2" ERASE >/dev/null; P add "${L3#/dev/}" backup erase "$L3" ERASE >/dev/null
}
label_of() { actions | jq_ "[r['id'] for r in d['rename'] if r['role']=='$1'][$2]"; }
make_part_disk() {   # make_part_disk N: drive N gets one ext4 partition holding old.txt
  local L; L=$(loop_of "$1")
  parted -s "$L" mklabel gpt mkpart p ext4 1MiB 100% >/dev/null 2>&1; partprobe "$L" >/dev/null 2>&1; sleep 1
  mkfs.ext4 -q -L OLDDATA "${L}p1" || return 1
  mkdir -p "$S/m"; mount "${L}p1" "$S/m" || return 1; echo "old file of drive $1" >"$S/m/old.txt"; umount "$S/m"
}

# ---------------- exact words
reset_env; $D test-setup 2 300M >/dev/null 2>&1
L1=$(loop_of 1); id1=${L1#/dev/}
has "add: an unknown role is refused" "$(P add "$id1" middle erase "$L1" ERASE)" "One of the choices is not allowed"
has "add: an unknown mode is refused" "$(P add "$id1" main both "$L1" ERASE)" "One of the choices is not allowed"
has "add: a typed word that is not in the list is refused" "$(P add "$id1" main erase "$L1" ERASE yes)" "A typed word is not allowed"
has "add: a typed word with a shell character is refused" "$(P add "$id1" main erase '/dev/sdb;reboot' ERASE)" "A typed word is not allowed"
has "add: too few words are refused" "$(P add "$id1" main)" "takes a drive"
has "wipe: a bad mode is refused" "$(P wipe "$id1" shred "$L1" ERASE)" "One of the choices is not allowed"
has "disconnect: a bad copy choice is refused" "$(P disconnect X maybe)" "One of the choices is not allowed"
has "move: a bad keep choice is refused" "$(P move X both yes)" "One of the choices is not allowed"
has "add: a drive that is not a spare is refused" "$(P add sda main erase /dev/sda ERASE)" "is not a spare drive"
check "nothing was changed by the refusals" "$(fstab_lines)" "0"
echo "a backup is running right now" >"$S/busy"; export DRIVES_BUSY_FILE="$S/busy"
has "add: refused while a backup runs" "$(P add "$id1" main erase "$L1" ERASE)" "Not a good moment: a backup is running right now"
has "wipe: refused while a backup runs" "$(P wipe "$id1" empty "$L1" ERASE)" "Not a good moment"
has "disconnect: refused while a backup runs" "$(P disconnect X yes)" "Not a good moment"
has "move: refused while a backup runs" "$(P move X erase yes)" "Not a good moment"
unset DRIVES_BUSY_FILE
check "still nothing changed while busy" "$(fstab_lines)" "0"

# ---------------- add: erase needs both typed words; keep needs one ext4 partition
has "add erase: the drive name alone is not enough" "$(P add "$id1" main erase "$L1")" "Cancelled. Nothing was changed."
has "add erase: ERASE alone is not enough" "$(P add "$id1" main erase ERASE)" "Cancelled. Nothing was changed."
has "add erase: a wrong drive name is not enough" "$(P add "$id1" main erase /dev/loop99 ERASE)" "Cancelled. Nothing was changed."
check "still nothing added" "$(fstab_lines)" "0"
has "add erase: both words add the drive to Main" "$(P add "$id1" main erase "$L1" ERASE)" "connected to the main storage"
check "the pool has one drive" "$(fstab_lines)" "1"
has "add keep on an empty drive (no partition) is refused" "$(P add "$(loop_of 2 | sed 's|/dev/||')" backup keep)" "does not have one ext4 partition"
make_part_disk 2
check "a drive with one ext4 partition is offered as keepable" "$(actions | jq_ "[s['keep_ok'] for s in d['spare']][0]")" "True"
has "add keep: the drive joins Backup with its files" "$(P add "$(loop_of 2 | sed 's|/dev/||')" backup keep)" "connected to the backup storage"
check "its file is in the Backup storage" "$(cat /mnt/test-backup/old.txt 2>/dev/null)" "old file of drive 2"

# ---------------- add to a RUNNING pool: the drive joins it as it runs (no container stops, so a backup or an upload may go on); a pool that is not running is mounted the usual way
if command -v setfattr >/dev/null && command -v getfattr >/dev/null; then
  reset_env; $D test-setup 3 300M >/dev/null 2>&1
  L1=$(loop_of 1); L2=$(loop_of 2); L3=$(loop_of 3)
  P add "${L1#/dev/}" main erase "$L1" ERASE >/dev/null
  echo "a backup is running right now" >"$S/busy"; export DRIVES_BUSY_FILE="$S/busy"
  LIVE=$(P add "${L2#/dev/}" main erase "$L2" ERASE)
  has "a second Main drive joins the running pool" "$LIVE" "joined the running main storage. No container was stopped."
  hasnt "a backup that runs does not hold back a drive that joins a running pool" "$LIVE" "Not a good moment"
  has "the same while a backup runs is refused for a pool that is not running" "$(P add "${L3#/dev/}" backup erase "$L3" ERASE)" "Not a good moment"
  unset DRIVES_BUSY_FILE
  check "the running pool has both drives (no remount)" "$(getfattr -n user.mergerfs.branches --only-values /mnt/test-main/.mergerfs 2>/dev/null | tr ':' '\n' | grep -c '^/')" "2"
  check "the saved setup (fstab) has both drives too" "$(grep fuse.mergerfs "$S/fstab" | grep -o '/mnt/test-disks/[A-Za-z0-9]*' | sort -u | wc -l)" "2"
  echo live >/mnt/test-main/live.txt
  check "the pool works: a file can be written" "$(cat /mnt/test-main/live.txt 2>/dev/null)" "live"
  check "the pool is still mounted as one pool" "$(findmnt -no FSTYPE /mnt/test-main)" "fuse.mergerfs"
else
  echo "skipped: the live add needs setfattr and getfattr (package attr)"
fi

# ---------------- several drives at once (add, move, take out): one answer for all, or one answer for each; the busy check is made once; progress lines name each drive
reset_env; $D test-setup 4 300M >/dev/null 2>&1
L1=$(loop_of 1); L2=$(loop_of 2); L3=$(loop_of 3); L4=$(loop_of 4); i2=${L2#/dev/}; i3=${L3#/dev/}; i4=${L4#/dev/}
P add "${L1#/dev/}" main erase "$L1" ERASE >/dev/null
has "several: a drive named twice is refused" "$(P add "$i2,$i2" main erase "$L2" ERASE)" "cannot be chosen twice"
has "several: more than eight drives are refused" "$(P add a1,a2,a3,a4,a5,a6,a7,a8,a9 main erase ERASE)" "between one and eight"
has "several: 'each' needs a choice for every drive" "$(P add "$i2,$i3" main each "$L2" "$L3" ERASE)" "One of the choices is not allowed"
has "several: a choice for a drive needs the word 'each'" "$(P add "$i2:erase,$i3:erase" main erase "$L2" "$L3" ERASE)" "One of the choices is not allowed"
has "several: a drive that is not a spare stops the whole batch before anything changes" "$(P add "$i2,sda" main erase "$L2" ERASE)" "is not a spare drive"
check "several: nothing was added by the refusals" "$(fstab_lines)" "1"
OUT=$(P add "$i2:erase,$i3:erase" main each "$L2" "$L3" ERASE)
check "several: two drives joined the Main storage one after the other" "$(printf '%s\n' "$OUT" | grep -c 'is connected to the main storage')" "2"
has "several: the progress names the first drive" "$OUT" "PROGRESS $i2 100 Done"
has "several: and the second" "$OUT" "PROGRESS $i3 100 Done"
check "several: Main has three drives now" "$(fstab_lines)" "3"
echo one >/mnt/test-main/one.txt; echo two >/mnt/test-main/two.txt
A=$(label_of main 1); B=$(label_of main 2)
P add "$i4" backup erase "$L4" ERASE >/dev/null
echo "a backup is running right now" >"$S/busy"; export DRIVES_BUSY_FILE="$S/busy"
has "several: moving is refused while a backup runs" "$(P move "$A,$B" keep yes KEEP)" "Not a good moment"
OUT=$(P move "$A,$B" keep yes KEEP NOW)
unset DRIVES_BUSY_FILE
check "several: the word NOW goes on anyway and both drives moved" "$(printf '%s\n' "$OUT" | grep -c 'is connected to the backup storage')" "2"
has "several: a move shows its own progress for the first drive" "$OUT" "PROGRESS $A 100 Done"
pool_drives() { grep -v '^#' "$S/fstab" | grep " /mnt/test-$1 fuse.mergerfs" | grep -o '/mnt/test-disks/[A-Za-z0-9]*' | sort -u | wc -l; }
check "several: Backup has three drives, Main has one" "$(pool_drives backup)-$(pool_drives main)" "3-1"
check "several: the files that were in Main are still in Main" "$(cat /mnt/test-main/one.txt /mnt/test-main/two.txt 2>/dev/null | tr '\n' ' ')" "one two "
has "several: all the Main drives cannot be moved in one batch" "$(P move "$(label_of main 0),$(label_of backup 0)" keep yes KEEP)" "Keep at least one Main drive"
C=$(label_of backup 0); D2=$(label_of backup 1)
has "several: two drives are taken out together" "$(P disconnect "$C,$D2" yes)" "is disconnected from the backup storage"
check "several: both are spare drives now" "$(actions | jq_ "len(d['spare'])")" "2"

# ---------------- disconnect
setup3
for i in 1 2 3 4 5; do echo "f$i" >"/mnt/test-main/f$i.txt"; done; echo "b1" >/mnt/test-backup/b1.txt
A=$(label_of main 0); B=$(label_of main 1); C=$(label_of backup 0)
has "the actions list says how many other drives a pool drive has and whether it holds files" "$(actions | jq_ "sorted([(r['role'], r['others'], r['has_data']) for r in d['rename']])")" "('backup', 0, True), ('main', 1, False), ('main', 1, True)"
has "the only Backup drive: backups would stop, so REMOVE is asked for" "$(P disconnect "$C" yes)" "Type REMOVE to continue"
check "the only Backup drive: without REMOVE nothing happens" "$(P disconnect "$C" yes | grep -c 'Cancelled')" "1"
check "the Backup drive is still there" "$(actions | jq_ "len([r for r in d['rename'] if r['role']=='backup'])")" "1"
FULL=$A; EMPTY=$B; [ "$(actions | jq_ "[r['has_data'] for r in d['rename'] if r['id']=='$A'][0]")" = True ] || { FULL=$B; EMPTY=$A; }
has "disconnect with copy: the drive with files goes after its files are copied" "$(P disconnect "$FULL" yes)" "is disconnected from the main storage"
check "all 5 files are still in Main" "$(ls /mnt/test-main/f*.txt | wc -l)" "5"
check "the drive is a spare drive now" "$(actions | jq_ "len(d['spare'])")" "1"
has "disconnect the last Main drive is refused" "$(P disconnect "$EMPTY" yes)" "is the only main drive"
check "Main still has its drive" "$(ls /mnt/test-main/f*.txt | wc -l)" "5"
# add it back (keep: its files are still on it), then take it out without copying
SP=$(actions | jq_ "d['spare'][0]['id']")
has "the disconnected drive keeps its files and can be added again with keep" "$(P add "$SP" main keep)" "connected to the main storage"
FULL=$(label_of main 0); [ "$(actions | jq_ "[r['has_data'] for r in d['rename'] if r['id']=='$FULL'][0]")" = True ] || FULL=$(label_of main 1)
has "disconnect without copying needs CONTINUE" "$(P disconnect "$FULL" no)" "Cancelled."
check "nothing was disconnected" "$(actions | jq_ "len(d['spare'])")" "0"
has "disconnect without copying: with CONTINUE it goes" "$(P disconnect "$FULL" no CONTINUE)" "is disconnected from the main storage"

# ---------------- move: the four choices
move_case() {   # move_case NAME KEEP COPY WORDS... : a Main drive with files moves to Backup
  setup3; for i in 1 2 3 4; do echo "m$i" >"/mnt/test-main/m$i.txt"; done
  local f; f=$(label_of main 0); [ "$(actions | jq_ "[r['has_data'] for r in d['rename'] if r['id']=='$f'][0]")" = True ] || f=$(label_of main 1)
  MOVED=$f; MOVED_DEV=/dev/$(readlink -f "$(findmnt -n -o SOURCE "/mnt/test-disks/$f")" | sed 's|/dev/||; s|p\?[0-9]*$||')
}
# 1. erase the drive, copy its files to the old pool first
move_case x; OUT=$(P move "$MOVED" erase yes "$MOVED_DEV" ERASE)
has "move (erase, copy first): done" "$OUT" "is connected to the backup storage"
check "move (erase, copy first): all Main files are still in Main" "$(ls /mnt/test-main/m*.txt | wc -l)" "4"
check "move (erase, copy first): the drive is empty in Backup" "$(ls /mnt/test-backup/m*.txt 2>/dev/null | wc -l)" "0"
check "move (erase, copy first): Backup has 2 drives, Main has 1" "$(actions | jq_ "sorted([r['role'] for r in d['rename']])")" "['backup', 'backup', 'main']"
# 2. erase the drive, do not copy: its files are gone
move_case x
has "move (erase, no copy): without CONTINUE it is cancelled" "$(P move "$MOVED" erase no "$MOVED_DEV" ERASE)" "Cancelled."
check "move (erase, no copy): nothing moved" "$(actions | jq_ "sorted([r['role'] for r in d['rename']])")" "['backup', 'main', 'main']"
check "move (erase, no copy): the files are still all there" "$(ls /mnt/test-main/m*.txt | wc -l)" "4"
has "move (erase, no copy): with CONTINUE it moves" "$(P move "$MOVED" erase no "$MOVED_DEV" ERASE CONTINUE)" "is connected to the backup storage"
check "move (erase, no copy): the files of that drive are gone from Main" "$(ls /mnt/test-main/m*.txt 2>/dev/null | wc -l)" "0"
# 3. keep the files on the drive and copy them to the old pool first: the files are in both pools
move_case x
has "move (keep, copy first): needs KEEP typed" "$(P move "$MOVED" keep yes)" "Cancelled."
check "move (keep, copy first): nothing moved without KEEP" "$(actions | jq_ "sorted([r['role'] for r in d['rename']])")" "['backup', 'main', 'main']"
has "move (keep, copy first): with KEEP it moves" "$(P move "$MOVED" keep yes KEEP)" "is connected to the backup storage"
check "move (keep, copy first): Main still has all its files" "$(ls /mnt/test-main/m*.txt | wc -l)" "4"
check "move (keep, copy first): the files are also shown in Backup" "$(ls /mnt/test-backup/m*.txt | wc -l)" "4"
# 4. keep the files on the drive, do not copy: the files go with the drive to the other pool
move_case x
has "move (keep, no copy): the files go with the drive" "$(P move "$MOVED" keep no KEEP CONTINUE)" "is connected to the backup storage"
check "move (keep, no copy): Main lost them" "$(ls /mnt/test-main/m*.txt 2>/dev/null | wc -l)" "0"
check "move (keep, no copy): Backup has them" "$(ls /mnt/test-backup/m*.txt | wc -l)" "4"
# a drive that cannot be moved with its files kept (no single ext4 partition) is refused before it leaves its pool
setup3
has "move: a boot drive section or an unknown drive is refused" "$(P move NOPE1 erase yes /dev/loop1 ERASE)" "There is no pool drive called"

# ---------------- wipe
reset_env; $D test-setup 3 300M >/dev/null 2>&1
L1=$(loop_of 1); id1=${L1#/dev/}; L2=$(loop_of 2); id2=${L2#/dev/}; make_part_disk 1; make_part_disk 2
has "wipe: without the typed words nothing is erased" "$(P wipe "$id1" empty)" "Cancelled. Nothing was changed."
check "wipe: the drive still has its partition" "$(lsblk -lnpo TYPE "$L1" | grep -c part)" "1"
has "wipe: empty" "$(P wipe "$id1" empty "$L1" ERASE)" "was erased and is empty"
check "wipe: no partition is left" "$(lsblk -lnpo TYPE "$L1" | grep -c part)" "0"
has "wipe: format" "$(P wipe "$id2" format "$L2" ERASE)" "formatted as an empty ext4 drive"
check "wipe: the old file is gone" "$(mkdir -p "$S/m"; mount "${L2}p1" "$S/m" 2>/dev/null; find "$S/m" -name old.txt | wc -l; umount "$S/m" 2>/dev/null)" "0"
# a pool drive is never erased
setup3; A=$(label_of main 0)
has "wipe: a pool drive is refused (no spare drive is left to erase)" "$(P wipe "$A" empty /dev/loop1 ERASE)" "No spare drive found"
has "wipe: the boot drive is refused" "$(P wipe sda empty /dev/sda ERASE)" "No spare drive found"
check "the pool is untouched" "$(fstab_lines)" "3"

echo "$([ "$bad" -eq 0 ] && echo OK || echo FAIL)"
exit "$bad"
