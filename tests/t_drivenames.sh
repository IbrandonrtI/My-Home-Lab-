#!/usr/bin/env bash
# Tests for the drive names in scripts/drives (size, maker, HDD or SSD, numbering of identical drives) and that they
# agree with the names the installer gives FileBrowser. lsblk is replaced by a function; no real drive is read.
# Run: bash tests/t_drivenames.sh   (last line is OK or FAIL)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bad=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
export DRIVES_TEST=1 DRIVES_STATE_DIR="$TMP/state" FSTAB="$TMP/fstab" DRIVE_NAMES_FILE_TEST="$TMP/chosen"
: >"$FSTAB"
# shellcheck disable=SC1091
source "$HERE/../scripts/drives"

# disks: name|model|size|rota|tran
DISKS="/dev/sdb|TOSHIBA_MQ01ABD100|1000204886016|1|sata
/dev/sdc|Samsung_SSD_860|250059350016|0|sata
/dev/sdd|ST1000DM010-2EP102|1000204886016|1|sata
/dev/sde|ST1000DM010-2EP102|1000204886016|1|sata
/dev/sdf|USB_DISK_3.0|500107862016|1|usb
/dev/sdg||2000398934016||
/dev/nvme0n1|Samsung_SSD_980|500107862016|0|nvme"
lsblk() {   # only the forms drives uses for names
  local d=${*: -1} line
  line=$(awk -F'|' -v d="$d" '$1 == d' <<<"$DISKS")
  [ -n "$line" ] || return 1
  IFS='|' read -r _ model size rota tran <<<"$line"
  case "$*" in
    *"-dno MODEL"*) echo "${model//_/ }" ;;
    *"-dnbo SIZE"*) echo "$size" ;;
    *"-dno SIZE"*) echo "$size" ;;
    *"-dnbo ROTA,TRAN"*) [ -n "$rota" ] && echo "$rota $tran" ;;
    *"-dno TRAN"*) echo "$tran" ;;
  esac
}

check "name: hard drive" "$(disk_base_name /dev/sdb)" "1 TB Toshiba HDD"
check "name: SSD by the model text" "$(disk_base_name /dev/sdc)" "250 GB Samsung SSD"
check "name: Seagate from its model number" "$(disk_base_name /dev/sdd)" "1 TB Seagate HDD"
check "name: unknown maker keeps the model text" "$(disk_base_name /dev/sdf)" "500 GB USB DISK 3.0 HDD"
check "name: nothing known but the size" "$(disk_base_name /dev/sdg)" "2 TB drive"
check "name: NVMe is an SSD" "$(disk_base_name /dev/nvme0n1)" "500 GB Samsung SSD"

# the same table through the installer's code: both must give the same maker and size text
PY=$(python3 - "$HERE/../installer/homelab-setup" <<'PYEOF'
import importlib.machinery, importlib.util, os, sys
os.environ["HLS_FAKE"] = "1"
ld = importlib.machinery.SourceFileLoader("hls", sys.argv[1])
sp = importlib.util.spec_from_loader("hls", ld)
m = importlib.util.module_from_spec(sp); ld.exec_module(m)
for model in ["TOSHIBA MQ01ABD100", "WDC WD10EZEX-08WN4A0", "WD10EZEX", "HGST HUS724040ALE640", "ST1000DM010-2EP102", "CT500MX500SSD1",
              "KINGSTON SA400S37", "SanDisk SDSSDA", "INTEL SSDSC2BW", "Samsung SSD 860", "MZ-76E250", "HITACHI HTS547575A9E384",
              "ADATA SU800", "USB DISK 3.0", "Foo Bar", "PNY CS900", "TEAM T253"]:
    print(model + "|" + m.drive_brand(model))
for b in [1000204886016, 250059350016, 750156374016, 500107862016, 2000398934016, 120034123776, 64023257088]:
    print(str(b) + "|" + m.pretty_size(b))
PYEOF
)
while IFS='|' read -r key want; do
  case "$key" in
    *[!0-9]*) check "maker of $key (same as the installer)" "$(drive_brand "$key")" "$want" ;;
    *) check "size $key (same as the installer)" "$(pretty_size "$key")" "$want" ;;
  esac
done <<<"$PY"

# numbering: identical drives get 1, 2, ...; a different drive gets no number; a name that was chosen wins
MP1=$DISKS_DIR/TMAIN1; MP2=$DISKS_DIR/TMAIN2; MP3=$DISKS_DIR/TBACKUP1
all_branches() { printf '%s\n' "$MP1" "$MP2" "$MP3"; }
branch_part() { case "$1" in "$MP1") echo p1 ;; "$MP2") echo p2 ;; "$MP3") echo p3 ;; esac; }
disk_of_part() { case "$1" in p1) echo /dev/sdd ;; p2) echo /dev/sde ;; p3) echo /dev/sdb ;; esac; }
mountpoint() { return 0; }
check "two identical drives: first" "$(branch_name "$MP1")" "1 TB Seagate HDD 1"
check "two identical drives: second" "$(branch_name "$MP2")" "1 TB Seagate HDD 2"
check "a different drive has no number" "$(branch_name "$MP3")" "1 TB Toshiba HDD"
echo "TMAIN2=Photos drive" >"$DRIVE_NAMES_FILE_TEST"
check "a chosen name wins" "$(branch_name "$MP2")" "Photos drive"
check "after that the other one is alone" "$(branch_name "$MP1")" "1 TB Seagate HDD"
rm -f "$DRIVE_NAMES_FILE_TEST"
# a drive that is unplugged keeps the name it had
mountpoint() { return 1; }
check "an unplugged drive keeps its scanned name" "$(branch_name "$MP3")" "1 TB Toshiba HDD"
check "a drive never seen shows its label" "$(branch_base_name "$DISKS_DIR/TMAIN9")" "TMAIN9"

# new pools fill one drive at a time
check "pool options: fill in order" "$(grep -c 'category.create=ff' <<<"$POOL_OPTS_BASE")" "1"
check "pool options: keep space free" "$(grep -c 'minfreespace=' <<<"$POOL_OPTS_BASE")" "1"
check "pool options: no spreading policy left" "$(grep -c 'mfs' <<<"$POOL_OPTS_BASE")" "0"

[ "$bad" -eq 0 ] && echo OK || echo FAIL
[ "$bad" -eq 0 ]
