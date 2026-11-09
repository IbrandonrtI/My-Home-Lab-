#!/usr/bin/env bash
# End-to-end test of taking several drives out or moving them together (`drives panel disconnect|move A,B ...`) with FAKE drives (loop files) and real mergerfs:
# files are only ever copied to drives that stay, a drive whose files do not fit is left alone, up to three drives work at the same time, and Stop
# (`drives panel abort`) leaves every file where it was and puts finished drives back.
# Needs root, losetup, mergerfs, mkfs.ext4 and parted; where they are missing it says so and passes.
# Run: bash tests/t_drivebatch.sh   (last line is OK or FAIL)
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
actions() { $D panel actions 2>/dev/null; }
jq_() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
label_of() { actions | jq_ "[r['id'] for r in d['rename'] if r['role']=='$1'][$2]"; }
pool_drives() { grep -v '^#' "$S/fstab" | grep " /mnt/test-$1 fuse.mergerfs" | grep -o '/mnt/test-disks/[A-Za-z0-9]*' | sort -u | wc -l; }
# N drives: the first $1 are Main, the last one Backup
setup() {
  local n=$1 i L
  reset_env; $D test-setup "$((n + 1))" 300M >/dev/null 2>&1
  for i in $(seq 1 "$n"); do L=$(loop_of "$i"); P add "${L#/dev/}" main erase "$L" ERASE >/dev/null; done
  L=$(loop_of "$((n + 1))"); P add "${L#/dev/}" backup erase "$L" ERASE >/dev/null
}

# ---------------- files are copied only to a drive that stays
setup 3
A=$(label_of main 0); B=$(label_of main 1); C=$(label_of main 2)
echo "from A" >"/mnt/test-disks/$A/fa.txt"; echo "from B" >"/mnt/test-disks/$B/fb.txt"; echo "from C" >"/mnt/test-disks/$C/fc.txt"
OUT=$(P disconnect "$A,$B" yes)
has "two drives are taken out together" "$OUT" "is disconnected from the main storage"
has "the progress of both drives is reported" "$OUT" "PROGRESS $A 100 Done"
check "the files of both went to the drive that stays" "$(cat /mnt/test-disks/$C/fa.txt /mnt/test-disks/$C/fb.txt /mnt/test-disks/$C/fc.txt 2>/dev/null | tr '\n' ',')" "from A,from B,from C,"
check "the pool still shows every file" "$(cat /mnt/test-main/fa.txt /mnt/test-main/fb.txt /mnt/test-main/fc.txt 2>/dev/null | tr '\n' ',')" "from A,from B,from C,"
check "only one Main drive is left" "$(pool_drives main)" "1"
hasnt "no drive was copied onto a drive that was leaving" "$OUT" "No other main drive has enough free space"
has "all the Main drives cannot leave together" "$(P disconnect "$C,$(label_of backup 0)" yes)" "Keep at least one Main drive"

# ---------------- not enough room on the drives that stay: that drive is left where it is, nothing is lost
setup 3
A=$(label_of main 0); B=$(label_of main 1); C=$(label_of main 2)
fallocate -l 130M "/mnt/test-disks/$A/bigA.bin"; fallocate -l 130M "/mnt/test-disks/$B/bigB.bin"; fallocate -l 100M "/mnt/test-disks/$C/bigC.bin"
OUT=$(P disconnect "$A,$B" yes)
has "no room: the report says which drive was left" "$OUT" "do not have room for its files"
check "no room: only one of the two left, the other stays" "$(pool_drives main)" "2"
check "no room: every file is still in the pool" "$(find /mnt/test-main -maxdepth 1 -name 'big*.bin' | wc -l)" "3"
has "no room: its bar says so" "$OUT" "No room, left as it is"

# ---------------- up to three drives copy at the same time
setup 5
M=(); for i in 0 1 2 3 4; do M+=("$(label_of main $i)"); done
for i in 0 1 2; do fallocate -l 40M "/mnt/test-disks/${M[$i]}/big$i.bin"; done
mkdir -p "$S/bin"
cat >"$S/bin/rsync" <<'RS'
#!/bin/sh
# (slows every copy down so that the test can see them overlap)
echo "start $$ $(date +%s.%N)" >>"$RSYNC_TRACE"
/usr/bin/rsync --bwlimit=10000 "$@"
rc=$?
echo "end $$ $(date +%s.%N)" >>"$RSYNC_TRACE"
exit $rc
RS
chmod +x "$S/bin/rsync"
export RSYNC_TRACE="$S/trace"; : >"$RSYNC_TRACE"
OUT=$(HOMELAB_EXTRA_PATH="$S/bin" P disconnect "${M[0]},${M[1]},${M[2]}" yes)
has "three drives were taken out" "$(printf '%s\n' "$OUT" | grep -c 'is disconnected from the main storage')" "3"
# the first copies of the three drives overlap in time: the second one starts before the first one ends
python3 - "$RSYNC_TRACE" >"$S/overlap" <<'PY'
import sys
ev = [l.split() for l in open(sys.argv[1]) if l.strip()]
running = best = 0
for kind, _pid, t in sorted(ev, key=lambda e: float(e[2])):
    running += 1 if kind == "start" else -1
    best = max(best, running)
print(best)
PY
check "copies of several drives ran at the same time" "$([ "$(cat "$S/overlap")" -ge 2 ] && echo yes || echo no)" "yes"
check "at most three copies at once" "$([ "$(cat "$S/overlap")" -le 3 ] && echo yes || echo no)" "yes"
check "all the files are still in the pool" "$(find /mnt/test-main -maxdepth 1 -name 'big[012].bin' | wc -l)" "3"
unset RSYNC_TRACE

# ---------------- Stop: a copy is cut off, nothing is lost, a drive that was already done goes back
setup 3
A=$(label_of main 0); B=$(label_of main 1); C=$(label_of main 2)
fallocate -l 120M "/mnt/test-disks/$A/bigA.bin"; echo "hello" >"/mnt/test-disks/$C/c.txt"
has "stop: there is nothing to stop right now" "$(P abort)" "No drive change is running"
RSYNC_TRACE=/dev/null HOMELAB_EXTRA_PATH="$S/bin" P move "$A,$B" keep yes KEEP >"$S/out" &
for _ in $(seq 1 100); do grep -q "PROGRESS $A [0-9]* Copying files" "$S/out" 2>/dev/null && break; sleep 0.3; done
sleep 1
has "stop: Stop is accepted while a drive is copying" "$(P abort)" "Stop requested"
wait
OUT=$(cat "$S/out")
has "stop: the report says it was stopped" "$OUT" "Stopped as you asked"
check "stop: the big file is still on the drive it was on" "$(find /mnt/test-disks/$A -maxdepth 1 -name bigA.bin | wc -l)" "1"
check "stop: and in the pool" "$(find /mnt/test-main -maxdepth 1 -name bigA.bin | wc -l)" "1"
check "stop: Main has all three drives, Backup only its own" "$(pool_drives main)-$(pool_drives backup)" "3-1"
check "stop: the other drive (already done) was put back too" "$(printf '%s\n' "$OUT" | grep -c 'put back where it was')" "1"
check "stop: the small file is untouched" "$(cat /mnt/test-main/c.txt)" "hello"
check "stop: Stop did not leave its request behind" "$([ -e "$S/panel-abort" ] && echo left || echo clean)" "clean"
has "stop: a new change can start right away" "$(P rename "$A" "Photos")" "Photos"

echo
if [ "$bad" = 0 ]; then echo OK; else echo "FAIL ($bad)"; exit 1; fi
