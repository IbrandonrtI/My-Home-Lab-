#!/usr/bin/env bash
# Tests of "build a RAID / ZFS setup while Main already has drives": the new setup is built on spare drives, the files of Main are copied
# into it and checked, the new setup takes the Main path, and the old Main drives are released (their files stay on them).
# Stand-in mdadm / zpool / zfs programs are used (the array is the first drive), real loop drives, real mergerfs.
# Run: bash tests/t_migrate.sh   (last line is OK or FAIL)
# shellcheck disable=SC2034,SC2046,SC2086
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVES="$HERE/../scripts/drives"
bad=0
check() { if [ "$2" = "$3" ]; then :; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
has() { case "$2" in *"$3"*) ;; *) echo "FAIL $1   (missing '$3' in: $(echo "$2" | tail -5 | tr '\n' '|'))"; bad=$((bad + 1)) ;; esac; }
export DRIVES_TEST=1

if [ "$(id -u)" != 0 ] || ! command -v losetup >/dev/null || ! command -v mergerfs >/dev/null || ! command -v mkfs.ext4 >/dev/null \
   || ! command -v parted >/dev/null || ! command -v rsync >/dev/null || ! losetup -f >/dev/null 2>&1; then
  echo "skipped: needs root, loop devices, mergerfs, mkfs.ext4, parted and rsync (not available here)"
  echo OK; exit 0
fi

D="bash $DRIVES"
S=""
FAKEBIN=$(mktemp -d)
cat >"$FAKEBIN/mdadm" <<'SH'
#!/bin/sh
# stand-in: the array is simply its first drive
case "$1" in
  --create) dev=$2; shift 2; for a in "$@"; do case "$a" in /dev/*) ln -sf "$a" "$dev"; break ;; esac; done ;;
  --stop) rm -f "$2" ;;
esac
exit 0
SH
cat >"$FAKEBIN/zpool" <<'SH'
#!/bin/sh
# stand-in: the pool is its first drive, mounted where the pool says
st="$FAKE_ZFS_STATE"
case "$1" in
  create)
    mp=""; dev=""
    for a in "$@"; do case "$a" in mountpoint=*) mp=${a#mountpoint=} ;; /dev/*) [ -n "$dev" ] || dev=$a ;; esac; done
    mkdir -p "$mp"; mkfs.ext4 -F -q "$dev" || exit 1; mount "$dev" "$mp" || exit 1
    echo "$dev $mp" >"$st" ;;
  destroy) read -r dev mp <"$st" 2>/dev/null && umount "$mp" 2>/dev/null; rm -f "$st" ;;
  list) exit 0 ;;
esac
exit 0
SH
cat >"$FAKEBIN/zfs" <<'SH'
#!/bin/sh
st="$FAKE_ZFS_STATE"
if [ "$1" = set ]; then
  new=${2#mountpoint=}; read -r dev mp <"$st" || exit 1
  umount "$mp" 2>/dev/null; mkdir -p "$new"; mount "$dev" "$new" || exit 1; echo "$dev $new" >"$st"
fi
exit 0
SH
chmod +x "$FAKEBIN"/mdadm "$FAKEBIN"/zpool "$FAKEBIN"/zfs

reset_env() {
  if [ -n "$S" ]; then DRIVES_STATE_DIR="$S" bash "$DRIVES" test-cleanup >/dev/null 2>&1; umount /mnt/test-newmain 2>/dev/null; rm -rf "$S"; fi
  chattr -i /mnt/test-main /mnt/test-backup /mnt/test-disks/* 2>/dev/null
  rm -rf /mnt/test-main /mnt/test-backup /mnt/test-disks /mnt/test-newmain 2>/dev/null
  S=$(mktemp -d); export DRIVES_STATE_DIR="$S" DRIVES_MD_DEVICE="$S/md-homelab" FAKE_ZFS_STATE="$S/zfs-state"
}
cleanup() { reset_env; rm -rf "$S" "$FAKEBIN"; chattr -i /mnt/test-main /mnt/test-backup 2>/dev/null; rm -rf /mnt/test-main /mnt/test-backup /mnt/test-disks /mnt/test-newmain 2>/dev/null; }
trap cleanup EXIT
loop_of() { losetup -ln -O NAME,BACK-FILE | awk -v f="$S/disk$1.img" '$2 == f {print $1}'; }
P() { HOMELAB_EXTRA_PATH="$FAKEBIN${FAKE_EXTRA:+:$FAKE_EXTRA}" timeout 300 $D panel "$@" </dev/null 2>&1; }
jq_() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
pool_drives() { grep -v '^#' "$S/fstab" | grep " /mnt/test-$1 fuse.mergerfs" | grep -o '/mnt/test-disks/[A-Za-z0-9]*' | sort -u | wc -l; }
main_fs() { findmnt -no FSTYPE /mnt/test-main 2>/dev/null; }
sums() { (cd /mnt/test-main && find . -type f ! -name '.mergerfs' -print0 | sort -z | xargs -0 sha1sum 2>/dev/null | sha1sum | cut -c1-12); }
fill_main() {
  mkdir -p /mnt/test-main/photos/2026 /mnt/test-main/.hidden
  echo "hello" >/mnt/test-main/photos/2026/a.txt; echo "secret" >/mnt/test-main/.hidden/s.txt
  head -c 30000000 /dev/urandom >/mnt/test-main/photos/big.bin; ln -s photos/big.bin /mnt/test-main/link
}
two_pool() {   # a Main Pool of two drives and two more spare drives
  reset_env; $D test-setup 4 300M >/dev/null 2>&1
  L1=$(loop_of 1); L2=$(loop_of 2); L3=$(loop_of 3); L4=$(loop_of 4)
  P setup pool "${L1#/dev/},${L2#/dev/}" pool ERASE >/dev/null
  fill_main
}

# ---------------- RAID 1: the files move over, the old drives are released
two_pool
BEFORE=$(sums)
J=$(HOMELAB_EXTRA_PATH="$FAKEBIN" $D panel setups 2>/dev/null)
check "scan: Main has drives" "$(echo "$J" | jq_ "d['main_has_drives']")" "True"
check "scan: RAID 1 can be built now (it moves Main)" "$(echo "$J" | jq_ "[o['can_build'] for o in d['options'] if o['id'] == 'md-raid1'][0]")" "True"
check "scan: and it says it moves Main" "$(echo "$J" | jq_ "[o['migrate'] for o in d['options'] if o['id'] == 'md-raid1'][0]")" "True"
check "scan: a SnapRAID setup still has to wait" "$(echo "$J" | jq_ "[o['migrate'] for o in d['options'] if o['id'] == 'snapraid1'][0]")" "False"
OUT=$(P setup md-raid1 "${L3#/dev/},${L4#/dev/}" md-raid1 ERASE)
has "raid1: the size check is shown" "$OUT" "Everything fits"
has "raid1: it says it is ready" "$OUT" "is ready"
has "raid1: the copy reports a percent for the panel's bars (on both new drives)" "$OUT" "PROGRESS ${L3#/dev/} "
has "raid1: ... with the words Copying files" "$OUT" "Copying files"
has "raid1: ... for the second new drive too" "$OUT" "PROGRESS ${L4#/dev/} "
check "raid1: Main is the new file system now (not a pool)" "$(main_fs)" "ext4"
check "raid1: every file is there and the same" "$(sums)" "$BEFORE"
check "raid1: the link is kept" "$(readlink /mnt/test-main/link)" "photos/big.bin"
check "raid1: no drive is in the Main Pool any more" "$(pool_drives main)" "0"
check "raid1: the build folder is gone" "$([ -e /mnt/test-newmain ] && echo there || echo gone)" "gone"
check "raid1: the fstab line is at the Main path" "$(grep -v '^#' "$S/fstab" | awk '$2 == "/mnt/test-main" {print $3}')" "ext4"
check "raid1: nothing is left of the build path in fstab" "$(grep -v '^#' "$S/fstab" | grep -c test-newmain)" "0"
check "raid1: the setup is recorded" "$(cut -d'|' -f1 "$S/preset")" "md-raid1"
J=$(HOMELAB_EXTRA_PATH="$FAKEBIN" $D panel setups 2>/dev/null)
check "raid1: the two old drives are spare drives with files that can be kept" "$(echo "$J" | jq_ "len([x for x in d['spare'] if not x['blank'] and x['keep_ok']])")" "2"
mkdir -p "$S/o1" "$S/o2"; mount -o ro "${L1}p1" "$S/o1"; mount -o ro "${L2}p1" "$S/o2"
check "raid1: the old drives still hold all the files (they were copied, not moved)" "$(find "$S/o1" "$S/o2" -type f -name '*.bin' -o -type f -name 'a.txt' | wc -l)" "2"
umount "$S/o1" "$S/o2"

# ---------------- too small: nothing is changed
two_pool
head -c 200000000 /dev/urandom >/mnt/test-main/big1.bin; head -c 90000000 /dev/urandom >/mnt/test-main/big2.bin
OUT=$(P setup md-raid1 "${L3#/dev/},${L4#/dev/}" md-raid1 ERASE)
has "small: it says the new setup is too small" "$OUT" "too small"
check "small: Main is still the pool" "$(main_fs)" "fuse.mergerfs"
check "small: both drives are still in Main" "$(pool_drives main)" "2"
check "small: the new drives were not touched" "$(echo "$(HOMELAB_EXTRA_PATH="$FAKEBIN" $D panel setups 2>/dev/null)" | jq_ "len([x for x in d['spare'] if x['blank']])")" "2"
J=$(HOMELAB_EXTRA_PATH="$FAKEBIN" $D panel setups 2>/dev/null)
has "small: the list says why it cannot be built" "$(echo "$J" | jq_ "[o['why'] for o in d['options'] if o['id'] == 'md-raid1'][0]")" "Too small"

# ---------------- the copy fails: Main is as it was and the new setup is taken apart again
two_pool
BEFORE=$(sums)
mkdir -p "$S/failbin"; printf '#!/bin/sh\nexit 23\n' >"$S/failbin/rsync"; chmod +x "$S/failbin/rsync"
FAKE_EXTRA="$S/failbin" OUT=$(FAKE_EXTRA="$S/failbin" P setup md-raid1 "${L3#/dev/},${L4#/dev/}" md-raid1 ERASE)
has "failed copy: it says it did not finish" "$OUT" "did not finish"
check "failed copy: Main is still the pool" "$(main_fs)" "fuse.mergerfs"
check "failed copy: both drives are still in Main" "$(pool_drives main)" "2"
check "failed copy: the files are the same" "$(sums)" "$BEFORE"
check "failed copy: no build path in fstab" "$(grep -v '^#' "$S/fstab" | grep -c test-newmain)" "0"
check "failed copy: the build folder is gone" "$([ -e /mnt/test-newmain ] && echo there || echo gone)" "gone"
check "failed copy: the record still says pool" "$(cut -d'|' -f1 "$S/preset")" "pool"

# ---------------- Stop is pressed while the files are copied: calm "Stopped", Main as it was, the new setup taken apart
two_pool
BEFORE=$(sums)
mkdir -p "$S/stopbin"; printf '#!/bin/sh\n: >"%s/panel-abort"\nexit 20\n' "$S" >"$S/stopbin/rsync"; chmod +x "$S/stopbin/rsync"
OUT=$(FAKE_EXTRA="$S/stopbin" P setup md-raid1 "${L3#/dev/},${L4#/dev/}" md-raid1 ERASE; echo "rc=$?")
has "stop: it ends with the exit code for a stop (4)" "$OUT" "rc=4"
has "stop: it says it was stopped as asked" "$OUT" "Stopped as you asked"
has "stop: the last sentence says Main was not changed" "$(echo "$OUT" | grep -v '^rc=' | tail -1)" "untouched"
case "$OUT" in *"did not finish"*|*"WARNING:"*) echo "FAIL stop: it must not look like an error (got: $(echo "$OUT" | tail -3 | tr '\n' '|'))"; bad=$((bad + 1)) ;; esac
check "stop: Main is still the pool" "$(main_fs)" "fuse.mergerfs"
check "stop: both drives are still in Main" "$(pool_drives main)" "2"
check "stop: the files are the same" "$(sums)" "$BEFORE"
check "stop: no build path in fstab" "$(grep -v '^#' "$S/fstab" | grep -c test-newmain)" "0"
check "stop: the stop mark is cleaned up" "$([ -e "$S/panel-abort" ] && echo there || echo gone)" "gone"
check "stop: the record still says pool" "$(cut -d'|' -f1 "$S/preset")" "pool"

# ---------------- ZFS (stand-in programs)
two_pool
BEFORE=$(sums)
OUT=$(P setup zfs-mirror "${L3#/dev/},${L4#/dev/}" zfs-mirror ERASE)
has "zfs: it says it is ready" "$OUT" "is ready"
check "zfs: Main is the new file system" "$(main_fs)" "ext4"
check "zfs: every file is there and the same" "$(sums)" "$BEFORE"
check "zfs: no drive is in the Main Pool any more" "$(pool_drives main)" "0"
check "zfs: the pool is mounted at the Main path" "$(awk '{print $2}' "$S/zfs-state")" "/mnt/test-main"

echo
if [ "$bad" = 0 ]; then echo OK; else echo "FAIL ($bad)"; exit 1; fi
