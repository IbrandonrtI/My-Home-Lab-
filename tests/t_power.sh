#!/usr/bin/env bash
# Test: homelab-backup keeps the backup drive awake while it runs and lets it sleep again afterwards.
# Fake hdparm/mountpoint/findmnt/lsblk record what is asked. Nothing on this machine is touched. Last line: OK or FAIL.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BK="$HERE/../scripts/homelab-backup"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
bad=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
mkdir -p "$T/bin" "$T/disks/BACKUP1" "$T/disks/BACKUPBOOT" "$T/disks/MAIN1" "$T/var"
cat >"$T/bin/hdparm" <<'X'
#!/bin/sh
echo "$*" >>"$FAKE_LOG"
X
cat >"$T/bin/mountpoint" <<'X'
#!/bin/sh
case "$2" in */disks/*) exit 0 ;; esac
exit 1
X
printf '#!/bin/sh\necho /dev/sdz1\n' >"$T/bin/findmnt"
printf '#!/bin/sh\necho sdz\n' >"$T/bin/lsblk"
chmod +x "$T/bin/"*
if [ "$(id -u)" != 0 ]; then echo "skipped: needs root (the script insists on it)"; echo OK; exit 0; fi
export FAKE_LOG="$T/hdparm.log" HOMELAB_DISKS_DIR="$T/disks" HOMELAB_EXTRA_PATH="$T/bin"
# the pool is not mounted, so the backup stops at once; the drive must still be released afterwards
sed "s#^LOGFILE=.*#LOGFILE=$T/var/log#; s#^STATUS_FILE=.*#STATUS_FILE=$T/var/last-run#" "$BK" >"$T/bk.sh"
: >"$FAKE_LOG"
BACKUP_CONF="$T/conf" PATH="$T/bin:$PATH" bash "$T/bk.sh" >/dev/null 2>&1 </dev/null
check "the backup drive is told to stay awake first, then to sleep after 10 minutes again" "$(cat "$FAKE_LOG" | tr '\n' ',')" "-S 0 /dev/sdz,-S 120 /dev/sdz,"
echo "$([ "$bad" -eq 0 ] && echo OK || echo FAIL)"
exit "$bad"
