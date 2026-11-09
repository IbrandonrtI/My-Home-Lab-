#!/usr/bin/env bash
# Test of the boot drive section in the control panel's door (`drives panel bootadd`, `panel move` and `panel disconnect` of a section) with FAKE drives
# (loop files) and real mergerfs: a section is made for a pool, moves to the other pool with or without its files, and is taken out again.
# Needs root, losetup, mergerfs, mkfs.ext4 and parted; where they are missing it says so and passes.
# Run: bash tests/t_bootpanel.sh   (last line is OK or FAIL)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVES="$HERE/../scripts/drives"
bad=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
has() { case "$2" in *"$3"*) echo "ok   $1" ;; *) echo "FAIL $1   (missing: $3)   got: $(printf '%s' "$2" | tail -6)"; bad=$((bad + 1)) ;; esac; }
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
P() { timeout 240 $D panel "$@" </dev/null 2>&1; }
jq_() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
pool_drives() { grep -v '^#' "$S/fstab" | grep " /mnt/test-$1 fuse.mergerfs" | grep -o '/mnt/test-disks/[A-Za-z0-9]*' | sort -u | wc -l; }
img() { echo "$S/boot-sections/$1.img"; }

reset_env; $D test-setup 2 300M >/dev/null 2>&1
L1=$(loop_of 1); L2=$(loop_of 2)
P add "${L1#/dev/}" main erase "$L1" ERASE >/dev/null; P add "${L2#/dev/}" backup erase "$L2" ERASE >/dev/null
echo "main file" >/mnt/test-main/m.txt

# ---------------- the limits the panel shows
J=$($D panel status 2>/dev/null)
check "status: the boot drive limits are there" "$(echo "$J" | jq_ "'boot_limits' in d")" "True"
check "status: the unit is MB in test mode and the smallest section is 16 MB" "$(echo "$J" | jq_ "d['boot_limits']['unit'] + str(d['boot_limits']['min_bytes'] // 1000000)")" "MB16"
check "status: neither pool has a section yet" "$(echo "$J" | jq_ "d['boot_limits']['main'] or d['boot_limits']['backup']")" "False"

# ---------------- making a section
has "bootadd: too small is refused" "$(P bootadd backup 5 CONTINUE)" "too small"
has "bootadd: without CONTINUE nothing happens" "$(P bootadd backup 40)" "Cancelled"
check "bootadd: so no section was made" "$(ls "$S/boot-sections" 2>/dev/null | wc -l)" "0"
OUT=$(P bootadd backup 40 CONTINUE)
has "bootadd: a 40 MB section is made for Backup" "$OUT" "is part of the backup storage"
check "bootadd: the Backup pool has two drives now" "$(pool_drives backup)" "2"
check "bootadd: the file is 40 MB" "$(stat -c %s "$(img backup)")" "40000000"
has "bootadd: a second one for the same pool is refused" "$(P bootadd backup 40 CONTINUE)" "already has a boot drive section"
J=$($D panel actions 2>/dev/null)
check "actions: the section is listed as a boot section of Backup" "$(echo "$J" | jq_ "[(r['id'], r['role']) for r in d['rename'] if r['boot_section']]")" "[('TBACKUPBOOT', 'backup')]"
echo "backup file" >/mnt/test-disks/TBACKUPBOOT/b.txt

# ---------------- moving it to Main with its files
has "move: keep needs the word KEEP" "$(P move TBACKUPBOOT keep no CONTINUE)" "Cancelled"
OUT=$(P move TBACKUPBOOT keep no KEEP CONTINUE)
check "move keep: Main has two drives, Backup one" "$(pool_drives main)-$(pool_drives backup)" "2-1"
check "move keep: the file went along in the section" "$(cat /mnt/test-disks/TMAINBOOT/b.txt 2>/dev/null)" "backup file"
check "move keep: the section file is now the Main one" "$([ -f "$(img main)" ] && [ ! -f "$(img backup)" ] && echo yes)" "yes"
check "move keep: the Main pool shows the file" "$(cat /mnt/test-main/b.txt 2>/dev/null)" "backup file"

# ---------------- moving it back, as a new empty section (its files are copied to the other Main drive first)
OUT=$(P move TMAINBOOT erase yes ERASE)
check "move erase: Backup has two drives again, Main one" "$(pool_drives main)-$(pool_drives backup)" "1-2"
check "move erase: the section is empty (a new one)" "$(find /mnt/test-disks/TBACKUPBOOT -mindepth 1 -maxdepth 1 ! -name lost+found | wc -l)" "0"
check "move erase: the files were copied to the Main drive first" "$(cat /mnt/test-main/b.txt 2>/dev/null)" "backup file"
check "move erase: it is the same size" "$(stat -c %s "$(img backup)")" "40000000"

# ---------------- taking it out: the space goes back to the boot drive
echo "more" >/mnt/test-disks/TBACKUPBOOT/c.txt
OUT=$(P disconnect TBACKUPBOOT yes)
has "take out: it says the space went back to the boot drive" "$OUT" "Its space went back to the boot drive"
check "take out: Backup has one drive again" "$(pool_drives backup)" "1"
check "take out: the section file is gone" "$([ -e "$(img backup)" ] && echo left || echo gone)" "gone"

# ---------------- a section that is alone in its pool and holds files: it can still be taken out, its files are deleted after ERASE
reset_env; $D test-setup 1 300M >/dev/null 2>&1
L1=$(loop_of 1)
P add "${L1#/dev/}" main erase "$L1" ERASE >/dev/null
P bootadd backup 40 CONTINUE >/dev/null
check "alone: Backup has only the section" "$(pool_drives backup)" "1"
echo "only copy" >/mnt/test-disks/TBACKUPBOOT/only.txt
has "alone: without ERASE nothing happens and the files are safe" "$(P disconnect TBACKUPBOOT yes REMOVE)" "Cancelled"
check "alone: the section is still there with its file" "$(cat /mnt/test-disks/TBACKUPBOOT/only.txt 2>/dev/null)" "only copy"
OUT=$(P disconnect TBACKUPBOOT yes ERASE REMOVE)
has "alone: with ERASE and REMOVE the section is removed" "$OUT" "Its space went back to the boot drive"
check "alone: the section file is gone" "$([ -e "$(img backup)" ] && echo left || echo gone)" "gone"
check "alone: Backup has no drive" "$(pool_drives backup)" "0"

echo
if [ "$bad" = 0 ]; then echo OK; else echo "FAIL ($bad)"; exit 1; fi
