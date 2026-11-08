#!/usr/bin/env bash
# Test: the door the control panel uses (`drives panel ...`): exact words only, no questions, rename / sleep / wake / remount with FAKE drives.
# Nothing real is touched: the pools, the drives and hdparm are replaced by functions, the names file is a temp file.
# Run: bash tests/t_drivepanel.sh   (last line is OK or FAIL)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bad=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
has()   { case "$2" in *"$3"*) echo "ok   $1" ;; *) echo "FAIL $1   (missing: $3)   got: $2"; bad=$((bad + 1)) ;; esac; }
if [ "$(id -u)" != 0 ]; then echo "skipped: needs root (the drives tool insists on it)"; echo OK; exit 0; fi
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
export DRIVES_TEST=1 DRIVES_STATE_DIR="$TMP/state" FSTAB="$TMP/fstab" DRIVE_NAMES_FILE_TEST="$TMP/chosen"
: >"$FSTAB"
# shellcheck disable=SC1091
source "$HERE/../scripts/drives"

# --- fake machine: two pool drives, three disks (two spinning, one SSD), hdparm remembers what it was told
all_branches() { printf '%s\n' /mnt/fake/MAIN1 /mnt/fake/BACKUP1; }
branch_role() { case "$1" in *MAIN1) echo main ;; *) echo backup ;; esac; }
branch_base_name() {   # the chosen name, else the automatic one
  local c; c=$(chosen_name "$(basename "$1")"); if [ -n "$c" ]; then echo "$c"; return 0; fi
  case "$1" in *MAIN1) echo "1 TB Toshiba HDD" ;; *) echo "2 TB Seagate HDD" ;; esac
}
branch_name() { branch_base_name "$1"; }
mountpoint() { [ "$2" != /mnt/fake/BACKUP1 ]; }          # BACKUP1 is unplugged
spinning_disks() { printf '%s\n' /dev/sdb /dev/sdc; }
disk_base_name() { echo "disk-${1##*/}"; }
disk_role_of() { case "$1" in /dev/sdb) echo main ;; *) echo backup ;; esac; }
protected_disks() { echo /dev/sda; }
SLEEPING="$TMP/sleeping"; : >"$SLEEPING"
power_state() { if grep -qx "$1" "$SLEEPING"; then echo asleep; else echo awake; fi; }
hdparm() {
  case "$1" in
    -y) echo "$2" >>"$SLEEPING" ;;
    --read-sector) grep -vx "$3" "$SLEEPING" >"$SLEEPING.n"; mv "$SLEEPING.n" "$SLEEPING" ;;
  esac
  return 0
}
export -f hdparm 2>/dev/null
sync_filebrowser() { echo "synced" >>"$TMP/sync.log"; }
busy_reason() { [ -f "$TMP/busy" ] && cat "$TMP/busy"; return 0; }
remount_flow() { echo "remount-ran" >>"$TMP/remount.log"; echo Recovered.; }
last_backup_line() { echo "never"; }
boot_free_bytes() { echo 12345; }
json_drives() { printf '{"pools":[],"drives":[]'; }

P() { ( panel_main "$@" ) 2>&1 </dev/null; }     # a subshell: die() exits; stdin is empty: a question would get no answer

# --- exact words only
has "an unknown action is refused" "$(P frobnicate)" "Unknown panel command"
has "extra words after status are refused" "$(P status now)" "takes no more words"
has "rename needs a drive and a name" "$(P rename MAIN1)" "takes a drive and a name"
has "sleep needs one drive" "$(P sleep sdb sdc)" "takes one drive"
has "an option cannot be slipped in as a drive" "$(P sleep --dry-run)" "not allowed"
has "a path is not a drive id" "$(P sleep ../etc/passwd)" "not allowed"
has "a drive id with a space is refused" "$(P rename "MAIN1 x" "Name")" "not allowed"
has "a name with a quote is refused" "$(P rename MAIN1 'Bad"name')" "A name may have up to 40"
has "a name with a slash is refused" "$(P rename MAIN1 'a/b')" "A name may have up to 40"
has "a name with an underscore is refused (it would be changed)" "$(P rename MAIN1 'a_b')" "A name may have up to 40"
has "a name with a leading dash is refused" "$(P rename MAIN1 '-x')" "A name may have up to 40"
has "a too long name is refused" "$(P rename MAIN1 "$(printf 'a%.0s' {1..41})")" "A name may have up to 40"
has "an empty name is refused" "$(P rename MAIN1 '')" "A name may have up to 40"
check "nothing was written by the refusals" "$([ -e "$DRIVE_NAMES_FILE" ] && echo yes || echo no)" "no"

# --- look only
out=$(P status); has "status prints the pools and drives and the extras" "$out" '"last_backup":"never","boot_free_bytes":12345}'
out=$(P actions)
has "actions lists the pool drives that can be renamed" "$out" '{"id":"MAIN1","name":"1 TB Toshiba HDD","role":"main","custom":false,"connected":true}'
has "an unplugged pool drive is marked not connected" "$out" '"id":"BACKUP1","name":"2 TB Seagate HDD","role":"backup","custom":false,"connected":false'
has "actions lists the spinning drives with their state" "$out" '{"id":"sdb","name":"disk-sdb","role":"main","state":"awake"}'
has "the boot drive is not offered" "$(P actions | grep -c sda)" "0"
python3 -c 'import json,sys; json.loads(sys.argv[1])' "$out" && echo "ok   actions is valid JSON" || { echo "FAIL actions is not valid JSON"; bad=$((bad + 1)); }

# --- rename
has "rename says what it did" "$(P rename MAIN1 'Photos Drive')" "is now called Photos Drive"
check "the name is saved under the drive's label" "$(grep -c '^MAIN1=Photos Drive$' "$DRIVE_NAMES_FILE")" "1"
check "FileBrowser and the dashboard were updated" "$(cat "$TMP/sync.log" 2>/dev/null | wc -l | tr -d ' ')" "1"
has "the actions list shows the chosen name" "$(P actions)" '"id":"MAIN1","name":"Photos Drive","role":"main","custom":true'
has "a name used by another drive is refused" "$(P rename BACKUP1 'photos drive')" "already called"
has "renaming to the same name changes nothing" "$(P rename MAIN1 'Photos Drive')" "Nothing was changed"
has "a drive that does not exist is refused" "$(P rename NOPE1 'Name')" "no pool drive called"
has "auto goes back to the automatic name" "$(P rename MAIN1 auto)" "is called 1 TB Toshiba HDD again"
check "the chosen name is gone from the file" "$(grep -c '^MAIN1=' "$DRIVE_NAMES_FILE")" "0"
has "auto on a drive without a chosen name says so" "$(P rename MAIN1 auto)" "already has its automatic name"

# --- sleep and wake
has "sleep puts a spinning drive to sleep" "$(P sleep sdb)" "asleep"
check "hdparm was told about the right drive" "$(cat "$SLEEPING")" "/dev/sdb"
has "sleep on a sleeping drive changes nothing" "$(P sleep sdb)" "already asleep"
has "wake wakes it" "$(P wake sdb)" "awake"
check "the drive is awake again" "$(cat "$SLEEPING")" ""
has "wake on an awake drive changes nothing" "$(P wake sdb)" "already awake"
has "the boot drive cannot be put to sleep" "$(P sleep sda)" "not a spinning hard drive"
has "an unknown drive cannot be put to sleep" "$(P sleep sdz)" "not a spinning hard drive"
check "no wrong drive was told to sleep" "$(cat "$SLEEPING")" ""

# --- remount
echo "a backup is running right now" >"$TMP/busy"
has "remount is refused while a backup runs" "$(P remount)" "Not a good moment: a backup is running right now"
check "remount did not run" "$(cat "$TMP/remount.log" 2>/dev/null | wc -l | tr -d ' ')" "0"
rm -f "$TMP/busy"
has "remount runs when nothing is busy" "$(P remount)" "Recovered."
check "remount ran once, without a question" "$(cat "$TMP/remount.log" | wc -l | tr -d ' ')" "1"

# --- a flash stick (removable, but it says it spins) is never offered for sleep or wake; a USB hard drive that is not removable still is
( unset -f spinning_disks disk_base_name disk_role_of protected_disks
  # shellcheck disable=SC1091
  source "$HERE/../scripts/drives"
  all_disks() { printf '%s\n' /dev/sda /dev/sdb /dev/sdc; }
  protected_disks() { echo /dev/sda; }
  drive_kind() { echo HDD; }
  lsblk() { case "$*" in *"-dno RM /dev/sdc"*) echo " 1" ;; *"-dno RM"*) echo " 0" ;; *"-dno MODEL"*) echo "SOMETHING" ;; esac; }
  spinning_disks ) >"$TMP/spin.txt" 2>&1
check "a removable flash stick is not a spinning drive (sdb stays, sdc and the boot drive do not)" "$(tr '\n' ' ' <"$TMP/spin.txt")" "/dev/sdb "

echo "$([ "$bad" -eq 0 ] && echo OK || echo FAIL)"
exit "$bad"
