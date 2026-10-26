#!/bin/bash
# Fake findmnt and lsblk for the simulation. Installed as symlinks named findmnt and lsblk.
# Without $SIM_DIR/disks.txt every question fails, like a machine where the drives cannot be read.
# disks.txt lines:  MOUNT|SOURCE|DISK|MODEL|SIZE-IN-BYTES|LABEL     e.g.  /mnt/disks/MAIN1|/dev/sdb1|sdb|TOSHIBA_DT01ACA100|1000204886016|MAIN1
f="$SIM_DIR/disks.txt"; [ -f "$f" ] || exit 1
last="${*: -1}"
if [ "$(basename "$0")" = findmnt ]; then
  awk -F'|' -v t="$last" '$1 == t {print $2; ok = 1} END {exit !ok}' "$f"
  exit
fi
case "$*" in
  *"-nslo NAME,TYPE"*) awk -F'|' -v d="$last" '$2 == d {n = $2; sub("/dev/", "", n); print n " part"; print $3 " disk"; ok = 1} END {exit !ok}' "$f" ;;
  *"-dnbo MODEL,SIZE"*) awk -F'|' -v d="$last" '"/dev/" $3 == d {print $4 "   " $5; ok = 1} END {exit !ok}' "$f" ;;
  *"-no LABEL"*) awk -F'|' -v d="$last" '$2 == d {print $6; ok = 1} END {exit !ok}' "$f" ;;
  *) exit 1 ;;
esac
