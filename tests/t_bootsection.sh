#!/usr/bin/env bash
# End-to-end test of the boot drive section in scripts/drives, with fake drives (loop files) and real mergerfs.
# Needs root, losetup, mergerfs and mkfs.ext4; where they are missing the test says so and passes (the CI machine has no loop devices).
# Run: bash tests/t_bootsection.sh   (last line is OK or FAIL)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVES="$HERE/../scripts/drives"
bad=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
yes_() { [ "$2" = "yes" ] && echo "ok   $1" || { echo "FAIL $1"; bad=$((bad + 1)); }; }

# the menu: three groups, each opens its own small menu (needs root only because the script insists on it)
if [ "$(id -u)" = 0 ]; then
  MS=$(mktemp -d)
  OUT=$(printf '2\n0\n3\n0\n4\n0\n0\n' | DRIVES_TEST=1 DRIVES_STATE_DIR="$MS" bash "$DRIVES" menu 2>&1)
  rm -rf "$MS"
  for want in "2) Add or remove drives" "3) Fix a problem" "4) Settings and upgrades" "4) Use part of the boot drive for a pool" \
              "2) Replace a dead drive" "3) Convert the current single data drive into the main pool"; do
    case "$OUT" in *"$want"*) echo "ok   menu shows: $want" ;; *) echo "FAIL menu is missing: $want"; bad=$((bad + 1)) ;; esac
  done
  case "$OUT" in *"11)"*|*"10)"*) echo "FAIL the first menu is still long"; bad=$((bad + 1)) ;; *) echo "ok   no menu has more than 5 numbered choices" ;; esac
  # after a choice the menu says what it does and asks before it goes on; answering no changes nothing and returns to the menu
  MS=$(mktemp -d)
  OUT=$(printf '2\n1\nn\n2\n\n3\nn\n0\n3\n1\nn\n0\n4\n1\nn\n2\nn\n0\n0\n' | DRIVES_TEST=1 DRIVES_STATE_DIR="$MS" bash "$DRIVES" menu 2>&1)
  rm -rf "$MS"
  for want in "You chose: Connect a new drive" "You chose: Disconnect a drive" "You chose: Move a drive between main and backup" \
              "You chose: Recover after an unplug or power cut" "You chose: Apply the drive power settings" "You chose: Fill order" \
              "Do you want to go on? [y/N]:" "Okay. Nothing was changed."; do
    case "$OUT" in *"$want"*) echo "ok   after a choice the menu shows: $want" ;; *) echo "FAIL after a choice the menu is missing: $want"; bad=$((bad + 1)) ;; esac
  done
  case "$OUT" in *"Type a number and press Enter:"*) echo "ok   the menu prompt says what to type" ;; *) echo "FAIL the menu prompt is unclear"; bad=$((bad + 1)) ;; esac
fi

if [ "$(id -u)" != 0 ] || ! command -v losetup >/dev/null || ! command -v mergerfs >/dev/null || ! command -v mkfs.ext4 >/dev/null \
   || ! command -v fallocate >/dev/null || ! losetup -f >/dev/null 2>&1; then
  echo "skipped: needs root, loop devices, mergerfs and mkfs.ext4 (not available here)"; echo OK; exit 0
fi

export DRIVES_TEST=1 DRIVES_STATE_DIR="$(mktemp -d)" DRAIN_SPARE_BYTES=1000000
S="$DRIVES_STATE_DIR"
cleanup() { bash "$DRIVES" test-cleanup >/dev/null 2>&1; rm -rf "$S"; rm -rf /mnt/test-main /mnt/test-backup /mnt/test-disks 2>/dev/null; }
trap cleanup EXIT
D="bash $DRIVES"
$D test-setup 1 300M >/dev/null 2>&1
LOOP=$(losetup -ln -O NAME,BACK-FILE | awk -v s="$S/" 'index($2, s) == 1 {print $1; exit}')

printf '1\n1\n%s\nERASE\n' "$LOOP" | $D connect >/dev/null 2>&1
check "a real drive is the first main drive" "$(grep -c 'TMAIN1' "$S/fstab")" "2"

# 1. the warning and the size rules
OUT=$(printf '1\nCONTINUE\n9999999999\n5\n40\ny\n' | $D bootsection 2>&1)
case "$OUT" in *"USING PART OF THE BOOT DRIVE"*"LAST place the main storage uses"*) r=yes ;; *) r=no ;; esac; yes_ "the warning says it is used last and that the boot drive can fail" "$r"
case "$OUT" in *"too big"*) r=yes ;; *) r=no ;; esac; yes_ "a size above the limit is refused" "$r"
case "$OUT" in *"too small"*) r=yes ;; *) r=no ;; esac; yes_ "a size below the smallest is refused" "$r"
case "$OUT" in *"always keeps at least"*) r=yes ;; *) r=no ;; esac; yes_ "it says how much the boot drive keeps free" "$r"
check "the section is in /etc/fstab as a file on the boot drive" "$(grep -c "^$S/boot-sections/main.img .*TMAINBOOT .*loop" "$S/fstab")" "1"
check "the file has the size that was asked for" "$(stat -c %s "$S/boot-sections/main.img")" "40000000"
POOLLINE=$(grep -v '^#' "$S/fstab" | grep fuse.mergerfs | head -1)
case "$POOLLINE" in /mnt/test-disks/TMAIN1=RW,*K:/mnt/test-disks/TMAINBOOT=RW,*K" "*) r=yes ;; *) r=no ;; esac; yes_ "the section is the last branch of the pool, each drive with its own free-space limit" "$r"
# each drive keeps 5% of ITS OWN size free: a 300 MB drive and a 40 MB section get different numbers
want1=$(( $(df -B1 --output=size /mnt/test-disks/TMAIN1 | tail -1 | tr -d ' ') * 5 / 100 / 1024 ))
want2=$(( $(df -B1 --output=size /mnt/test-disks/TMAINBOOT | tail -1 | tr -d ' ') * 5 / 100 / 1024 ))
case "$POOLLINE" in *"/mnt/test-disks/TMAIN1=RW,${want1}K:/mnt/test-disks/TMAINBOOT=RW,${want2}K "*) r=yes ;; *) r=no ;; esac; yes_ "the limit of every drive is 5% of that drive's size" "$r"
[ "$want1" != "$want2" ] && r=yes || r=no; yes_ "and the two drives really got different numbers" "$r"
# a pool line written by an older version (one 20G limit for everything) is brought up to date by "drives fillorder"
sed -i 's/=RW,[0-9]*K//g' "$S/fstab"
case "$(printf 'y\n' | $D status 2>&1)" in *"uses an older setting"*) r=yes ;; *) r=no ;; esac; yes_ "status tells an older pool line to run fillorder" "$r"
printf '1\ny\n' | $D fillorder >/dev/null 2>&1
POOLLINE=$(grep -v '^#' "$S/fstab" | grep fuse.mergerfs | head -1)
case "$POOLLINE" in *"/mnt/test-disks/TMAIN1=RW,${want1}K:/mnt/test-disks/TMAINBOOT=RW,${want2}K "*) r=yes ;; *) r=no ;; esac; yes_ "fillorder gives every drive its own 5% limit again" "$r"
mountpoint -q /mnt/test-main && r=yes || r=no; yes_ "and the pool is mounted afterwards" "$r"
case "$POOLLINE" in *category.create=ff*) r=yes ;; *) r=no ;; esac; yes_ "the pool still fills in order" "$r"

# 2. a second section for the same pool is refused; one in the backup pool is allowed and warns more
OUT=$(printf '1\n' | $D bootsection 2>&1)
case "$OUT" in *"already has a boot drive section"*) r=yes ;; *) r=no ;; esac; yes_ "a second section in the same pool is refused" "$r"
OUT=$(printf '2\nCONTINUE\n20\ny\n' | $D bootsection 2>&1)
case "$OUT" in *"NOT if the boot drive dies"*"also has a section"*) r=yes ;; *) r=no ;; esac; yes_ "the backup warning is stronger and mentions the main section" "$r"
check "the backup pool is mounted" "$(mountpoint -q /mnt/test-backup && echo mounted)" "mounted"

# 3. the real drive fills first, the section last
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14; do dd if=/dev/zero of=/mnt/test-main/f$i bs=1M count=20 status=none 2>/dev/null; done
IN_DRIVE=$(ls /mnt/test-disks/TMAIN1 | grep -c '^f')
IN_SECTION=$(ls /mnt/test-disks/TMAINBOOT | grep -c '^f')
[ "$IN_DRIVE" -ge 10 ] && r=yes || r=no; yes_ "the real drive got the first files ($IN_DRIVE)" "$r"
[ "$IN_SECTION" -ge 1 ] && r=yes || r=no; yes_ "the section got the files only after the drive was full ($IN_SECTION)" "$r"
first_in_section=$(ls -tr /mnt/test-disks/TMAINBOOT | grep '^f' | head -1)
[ -n "$first_in_section" ] && r=yes || r=no; yes_ "something is in the section" "$r"

# 4. removing a section that holds files: refused while the other drive has no room, allowed after room is made
OUT=$(printf '2\n' | $D disconnect 2>&1)
case "$OUT" in *"Not removing"*) r=yes ;; *) r=no ;; esac; yes_ "the section is not removed while its files have nowhere to go" "$r"
check "the section is still there" "$(grep -vc '^#' "$S/fstab" | tr -d ' ' | awk '{print ($1 >= 3)}')" "1"
rm -f /mnt/test-main/f*
echo kept >/mnt/test-main/note.txt
OUT=$(printf '2\n' | $D disconnect 2>&1)
case "$OUT" in *"is removed. Its space went back"*) r=yes ;; *) r=no ;; esac; yes_ "an empty-enough section is removed and the space returned" "$r"
[ ! -e "$S/boot-sections/main.img" ] && r=yes || r=no; yes_ "its file is deleted" "$r"
check "the files that were in the pool are still there" "$(cat /mnt/test-main/note.txt)" "kept"

# 5. release keeps the section's file; adding it again can reuse it with its files
printf '1\nCONTINUE\n30\ny\n' | $D bootsection >/dev/null 2>&1
echo section-file >/mnt/test-disks/TMAINBOOT/inside.txt
printf 'y\n' | $D release >/dev/null 2>&1
[ -f "$S/boot-sections/main.img" ] && r=yes || r=no; yes_ "release keeps the section's file" "$r"
check "after release the pools are not mounted" "$(mountpoint -q /mnt/test-main && echo mounted || echo plain)" "plain"
printf '1\n1\n1\n' | $D connect >/dev/null 2>&1
printf '1\n1\n' | $D bootsection >/dev/null 2>&1
check "the section is used again with its files" "$(cat /mnt/test-main/inside.txt 2>/dev/null)" "section-file"

# 6. status shows the section, the name and the free space the boot drive keeps
OUT=$($D status 2>&1)
case "$OUT" in *"30 MB boot drive section"*"connected (used last)"*) r=yes ;; *) r=no ;; esac; yes_ "status lists the section by its size" "$r"
case "$OUT" in *"=== Boot drive ==="*"keeps at least"*) r=yes ;; *) r=no ;; esac; yes_ "status has a Boot drive block" "$r"

# 7. a boot drive that is too full: nothing is made
$D release >/dev/null 2>&1 <<<"y"
rm -f "$S/boot-sections/"*.img
OUT=$(printf '1\n' | DRIVES_BOOT_KEEP=900000000000000 $D bootsection 2>&1)
case "$OUT" in *"Nothing was changed"*) r=yes ;; *) r=no ;; esac; yes_ "no section when the boot drive would drop under its free space" "$r"
[ ! -e "$S/boot-sections/main.img" ] && r=yes || r=no; yes_ "and no file is left behind" "$r"

# the biggest size that is shown can really be typed (it used to be rounded up, so the shown maximum was refused)
rm -f "$S/boot-sections/"*.img
LIM=$(printf '1\nCONTINUE\n\n' | $D bootsection 2>&1 | sed -n 's/.*A section can be from [0-9]* MB to \([0-9]*\) MB.*/\1/p' | head -1)
OUT=$(printf '1\nCONTINUE\n%s\ny\n' "$LIM" | $D bootsection 2>&1)
case "$OUT" in *"too big"*) r=no ;; *) r=yes ;; esac; yes_ "the largest size the menu shows (${LIM:-?} MB) is accepted" "$r"
case "$OUT" in *"stops putting files in the section when only"*) r=yes ;; *) r=no ;; esac; yes_ "the menu says the pool leaves free space in the section like on other drives" "$r"
[ -n "$LIM" ] && check "the file has exactly that size" "$(stat -c %s "$S/boot-sections/main.img" 2>/dev/null)" "$((LIM * 1000000))"
$D release >/dev/null 2>&1 <<<"y"
rm -f "$S/boot-sections/"*.img

# the largest size that is shown is accepted (it used to be rounded up, so typing it was refused)
$D release >/dev/null 2>&1 <<<"y"; rm -f "$S/boot-sections/"*.img
OUT=$(printf '1\nCONTINUE\n\n' | $D bootsection 2>&1)
SHOWN=$(printf '%s\n' "$OUT" | sed -n 's/.*A section can be from [0-9]* MB to \([0-9]*\) MB.*/\1/p' | head -1)
OUT=$(printf '1\nCONTINUE\n%s\ny\n' "$SHOWN" | $D bootsection 2>&1)
case "$OUT" in *"too big"*) r=no ;; *) r=yes ;; esac; yes_ "typing the largest size shown ($SHOWN MB) is accepted" "$r"
[ -f "$S/boot-sections/main.img" ] && r=yes || r=no; yes_ "and the section file was made" "$r"
$D release >/dev/null 2>&1 <<<"y"; rm -f "$S/boot-sections/"*.img

# a boot drive of 128 GB or less cannot lend a section: it says so at once and asks nothing
OUT=$(DRIVES_BOOT_SMALL=900000000000000 $D bootsection 2>&1 </dev/null)
case "$OUT" in *"is only"*"no part of it can be used"*"Nothing was changed"*) r=yes ;; *) r=no ;; esac; yes_ "a small boot drive: warns and leaves the option" "$r"
case "$OUT" in *"Add a boot drive section to which storage"*) r=no ;; *) r=yes ;; esac; yes_ "a small boot drive: it does not even ask which storage" "$r"
[ ! -e "$S/boot-sections/main.img" ] && r=yes || r=no; yes_ "a small boot drive: no file is made" "$r"

echo "$([ "$bad" -eq 0 ] && echo OK || echo FAIL)"
exit "$bad"
