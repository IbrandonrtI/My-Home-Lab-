#!/usr/bin/env bash
# Test of Configure Drives (`drives panel setups` and `drives panel setup`) with FAKE drives (loop files) and real mergerfs:
# the ranking of the ready-made setups for the spare drives (equal and mixed sizes), why a setup cannot be built yet, and building a pool and a mirror.
# Needs root, losetup, mergerfs, mkfs.ext4 and parted; where they are missing it says so and passes.
# Run: bash tests/t_drivesetups.sh   (last line is OK or FAIL)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVES="$HERE/../scripts/drives"
bad=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
has() { case "$2" in *"$3"*) echo "ok   $1" ;; *) echo "FAIL $1   (missing: $3)   got: $(printf '%s' "$2" | tail -6)"; bad=$((bad + 1)) ;; esac; }

export DRIVES_TEST=1 DRAIN_SPARE_BYTES=1000000

# ---- the ranking itself (no drives needed)
# shellcheck source=/dev/null
( source "$DRIVES"
  GB=1000000000
  pick() { setup_choose "$@"; }
  r=$(pick zfs-raidz1 $((1000 * GB)) $((500 * GB)) $((500 * GB)) $((63 * GB)))
  echo "RAIDZ1_ON_MIXED=$r"
  r=$(pick pool $((1000 * GB)) $((500 * GB)) $((63 * GB)))
  echo "POOL_ON_MIXED=$r"
  r=$(pick mirror $((1000 * GB)) $((500 * GB)) $((63 * GB)))
  echo "MIRROR_ON_THREE=$r"
  r=$(pick zfs-raidz3 $((1000 * GB)) $((1000 * GB)) $((1000 * GB)) || echo none)
  echo "RAIDZ3_ON_THREE=$r"
  # equal drives: raidz1 beats a plain pool and a mirror; unequal drives (one huge, three small): a plain pool wins over raidz2
  s1=$(setup_score zfs-raidz1 1 $((2000 * GB)) $((3000 * GB))); s2=$(setup_score pool 0 $((3000 * GB)) $((3000 * GB))); s3=$(setup_score zfs-mirror 2 $((1000 * GB)) $((3000 * GB)))
  [ "$s1" -gt "$s2" ] && echo "RAIDZ1_BEATS_POOL=yes" || echo "RAIDZ1_BEATS_POOL=no($s1,$s2)"
  [ "$s1" -gt "$s3" ] && echo "RAIDZ1_BEATS_MIRROR3=yes" || echo "RAIDZ1_BEATS_MIRROR3=no($s1,$s3)"
  m1=$(setup_score zfs-raidz2 2 $((126 * GB)) $((2063 * GB))); m2=$(setup_score pool 0 $((2063 * GB)) $((2063 * GB)))
  [ "$m2" -gt "$m1" ] && echo "POOL_BEATS_RAIDZ2_ON_MIXED=yes" || echo "POOL_BEATS_RAIDZ2_ON_MIXED=no($m2,$m1)"
) >/tmp/setups-rank.$$ 2>&1
RANK=$(cat /tmp/setups-rank.$$); rm -f /tmp/setups-rank.$$
has "RAID5-style on mixed sizes uses the three biggest (3 x 500 GB wasted nothing, the 63 GB drive is left out)" "$RANK" "RAIDZ1_ON_MIXED=3 1000000000000"
has "a plain pool uses every drive" "$RANK" "POOL_ON_MIXED=3 1563000000000"
has "a mirror uses the two biggest drives" "$RANK" "MIRROR_ON_THREE=2 500000000000"
has "RAIDZ3 does not fit three drives" "$RANK" "RAIDZ3_ON_THREE=none"
has "equal drives: RAIDZ1 beats a plain pool" "$RANK" "RAIDZ1_BEATS_POOL=yes"
has "equal drives: RAIDZ1 beats a three drive mirror" "$RANK" "RAIDZ1_BEATS_MIRROR3=yes"
has "one huge drive and small ones: a plain pool beats RAIDZ2 (which would waste the big one)" "$RANK" "POOL_BEATS_RAIDZ2_ON_MIXED=yes"

if [ "$(id -u)" != 0 ] || ! command -v losetup >/dev/null || ! command -v mergerfs >/dev/null || ! command -v mkfs.ext4 >/dev/null \
   || ! command -v parted >/dev/null || ! command -v fallocate >/dev/null || ! losetup -f >/dev/null 2>&1; then
  echo "skipped the drive part: needs root, loop devices, mergerfs, mkfs.ext4 and parted (not available here)"
  if [ "$bad" = 0 ]; then echo OK; else echo "FAIL ($bad)"; exit 1; fi
  exit 0
fi

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

# ---------------- three empty drives: the scan, the ranking, what can be built
reset_env; $D test-setup 3 300M >/dev/null 2>&1
J=$($D panel setups 2>/dev/null)
check "scan: three spare drives are found" "$(echo "$J" | jq_ "len(d['spare'])")" "3"
check "scan: every setup of the list is there" "$(echo "$J" | jq_ "len(d['options'])")" "14"
check "scan: the list is ordered from best to worst (scores never go up)" "$(echo "$J" | jq_ "'ok' if all(a['score'] >= b['score'] for a, b in zip(d['options'], d['options'][1:])) else 'no'")" "ok"
check "scan: the recommended setup is the first one that fits" "$(echo "$J" | jq_ "d['recommended'] == [o for o in d['options'] if o['fits']][0]['id']")" "True"
check "scan: three equal drives recommend a RAIDZ1 (it protects one drive and keeps two thirds of the space)" "$(echo "$J" | jq_ "d['recommended']")" "zfs-raidz1"
check "scan: RAIDZ2 needs four drives, so it does not fit" "$(echo "$J" | jq_ "[o for o in d['options'] if o['id'] == 'zfs-raidz2'][0]['fits']")" "False"
check "scan: the plain pool can be built now" "$(echo "$J" | jq_ "[o for o in d['options'] if o['id'] == 'pool'][0]['can_build']")" "True"
check "scan: a plain pool lists all three drives" "$(echo "$J" | jq_ "len([o for o in d['options'] if o['id'] == 'pool'][0]['drives'])")" "3"

# ---------------- a wrong word, or a drive that is not a spare, changes nothing
L1=$(loop_of 1); L2=$(loop_of 2); L3=$(loop_of 3)
OUT=$(P setup pool "${L1#/dev/},${L2#/dev/}" pool)
check "build: without ERASE nothing happens" "$(pool_drives main)" "0"
OUT=$(P setup pool "sda" pool ERASE)
has "build: a drive that is not a spare is refused" "$OUT" "not a spare drive"
OUT=$(P setup nonsense "${L1#/dev/}" nonsense ERASE)
has "build: an unknown setup name is refused as a typed word, before anything is looked at" "$OUT" "typed word is not allowed"
OUT=$(P setup nonsense "${L1#/dev/}" ERASE)
has "build: an unknown setup is refused" "$OUT" "does not exist"

# ---------------- build a plain pool on the three drives
OUT=$(P setup pool "${L1#/dev/},${L2#/dev/},${L3#/dev/}" pool ERASE)
has "build: the plain pool says it is ready" "$OUT" "is ready"
check "build: the three drives joined the Main pool" "$(pool_drives main)" "3"
J=$($D panel setups 2>/dev/null)
check "after: no spare drive is left" "$(echo "$J" | jq_ "len(d['spare'])")" "0"

# ---------------- Main has drives: a new setup is refused, with the reason
reset_env; $D test-setup 4 300M >/dev/null 2>&1
L1=$(loop_of 1); P add "${L1#/dev/}" main erase "$L1" ERASE >/dev/null
J=$($D panel setups 2>/dev/null)
check "blocked: the scan still ranks the three spare drives" "$(echo "$J" | jq_ "len(d['spare'])")" "3"
check "blocked: nothing can be built while Main has drives" "$(echo "$J" | jq_ "[o['can_build'] for o in d['options']].count(True)")" "0"
has "blocked: it says to take the drives out of Main first" "$(echo "$J" | jq_ "[o['why'] for o in d['options'] if o['id'] == 'pool'][0]")" "take the drives out of Main first"
L2=$(loop_of 2); L3=$(loop_of 3)
OUT=$(P setup pool "${L2#/dev/},${L3#/dev/}" pool ERASE)
check "blocked: building anyway changes nothing" "$(pool_drives main)" "1"

# ---------------- a mirror: one Main drive and one Backup drive
reset_env; $D test-setup 2 300M >/dev/null 2>&1
L1=$(loop_of 1); L2=$(loop_of 2)
OUT=$(P setup mirror "${L1#/dev/},${L2#/dev/}" mirror ERASE)
has "mirror: it says it is ready" "$OUT" "is ready"
check "mirror: one drive in Main and one in Backup" "$(pool_drives main)-$(pool_drives backup)" "1-1"

# ---------------- SnapRAID: a data drive keeps its files, the biggest of the others holds the protection (a stand-in snapraid program is used)
FAKEBIN=$(mktemp -d); printf '#!/bin/sh\nexit 0\n' >"$FAKEBIN/snapraid"; chmod +x "$FAKEBIN/snapraid"
reset_env; $D test-setup 3 300M >/dev/null 2>&1
L1=$(loop_of 1); L2=$(loop_of 2); L3=$(loop_of 3)
for n in 1 2 3; do      # three drives that each hold a file and are then taken out again (so they are spare drives with files)
  eval "LL=\$L$n"
  P add "${LL#/dev/}" main erase "$LL" ERASE >/dev/null
  echo "photos $n" >"/mnt/test-main/keep$n.txt"
  IDN=$(basename "$(grep -v '^#' "$S/fstab" | grep -o '/mnt/test-disks/[A-Za-z0-9]*' | head -1)")
  P disconnect "$IDN" no REMOVE >/dev/null
done
J=$(HOMELAB_EXTRA_PATH="$FAKEBIN" $D panel setups 2>/dev/null)
check "snapraid keep: the scan says SnapRAID can keep files" "$(echo "$J" | jq_ "[o['can_keep'] for o in d['options'] if o['id'] == 'snapraid1'][0]")" "True"
check "snapraid keep: and the ZFS setups cannot" "$(echo "$J" | jq_ "[o['can_keep'] for o in d['options'] if o['id'] == 'zfs-raidz1'][0]")" "False"
check "snapraid keep: all three drives are spare drives with files" "$(echo "$J" | jq_ "len([x for x in d['spare'] if not x['blank'] and x['keep_ok']])")" "3"
OUT=$(HOMELAB_EXTRA_PATH="$FAKEBIN" P setup snapraid1 "${L1#/dev/}:keep,${L2#/dev/}:keep,${L3#/dev/}:keep" snapraid1 ERASE)
has "snapraid keep: when every drive keeps its files nothing is left for the protection" "$OUT" "none left for that"
OUT=$(HOMELAB_EXTRA_PATH="$FAKEBIN" P setup snapraid1 "${L1#/dev/}:keep,${L2#/dev/}:keep,${L3#/dev/}:erase" snapraid1 ERASE)
has "snapraid keep: it says it is ready" "$OUT" "is ready"
check "snapraid keep: two data drives are in Main" "$(pool_drives main)" "2"
check "snapraid keep: the files of the kept drives are there and show in Main" "$(cat /mnt/test-main/keep1.txt /mnt/test-main/keep2.txt 2>/dev/null | tr '\n' ',')" "photos 1,photos 2,"
rm -rf "$FAKEBIN"

echo
if [ "$bad" = 0 ]; then echo OK; else echo "FAIL ($bad)"; exit 1; fi
