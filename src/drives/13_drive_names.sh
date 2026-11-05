# ---------- drive names ----------
BRAND_TABLE='SAMSUNG|^MZ[- ]?[A-Z0-9_]|^HM[0-9]{3}|^HN-M	Samsung
TOSHIBA|^MQ0[0-9]|^DT0[0-9]|^HDW|^MK[0-9]{4}|^MG0[0-9]|^KBG|^KXG	Toshiba
WESTERN DIGITAL|^WDC|^WD ?[0-9]|^WDS	Western Digital
HGST|^HU[SH]	HGST
HITACHI|^HT[ES][0-9]|^HDS	Hitachi
SEAGATE|^ST[0-9]{3,}[A-Z]{2}	Seagate
CRUCIAL|^CT[0-9]{2,}	Crucial
KINGSTON|^SA400|^SKC|^SNV|^SUV|^SV300	Kingston
SANDISK|^SDSSD|^SD[A-Z]{2}[0-9]	SanDisk
INTEL|^SSDSC|^SSDPE	Intel
MICRON|^MTFD	Micron
ADATA|^SU[0-9]{3}	ADATA
LEXAR	Lexar
CORSAIR	Corsair
SABRENT	Sabrent
PATRIOT	Patriot
PLEXTOR	Plextor
KIOXIA	Kioxia
TRANSCEND	Transcend
LITE-?ON	Lite-On
SK ?HYNIX	SK hynix
MAXTOR	Maxtor
FUJITSU	Fujitsu
(^| )PNY( |$)	PNY
TEAM ?GROUP|^TEAM 	TeamGroup'

# The name helpers below use only what bash can do itself (no tr, sed, grep or awk): a status screen asks for the name of every
# drive several times, and starting four or five programs for each question made `sudo drives status` slow with many drives.
drive_brand() {   # drive_brand "TOSHIBA MQ01ABD100" -> Toshiba (nothing when the maker is not known)
  local LC_ALL=C text=${1^^} pat name
  text=${text//_/ }
  while [[ $text == *"  "* ]]; do text=${text//  / }; done
  text=${text# }; text=${text% }
  while IFS=$'\t' read -r pat name; do
    if [[ $text =~ $pat ]]; then printf '%s' "$name"; return 0; fi
  done <<<"$BRAND_TABLE"
  return 0
}

pretty_size() {   # bytes -> "1 TB", "750 GB" (as the drive is sold)
  local b=$1 t
  [[ $b =~ ^[0-9]+$ ]] || b=0
  b=$((10#$b))
  if [ "$b" -ge 950000000000 ]; then
    t=$(( (b + 50000000000) / 100000000000 ))                      # tenths of a TB, rounded
    if [ $((t % 10)) -eq 0 ]; then printf '%d TB' $((t / 10)); else printf '%d.%d TB' $((t / 10)) $((t % 10)); fi
  elif [ "$b" -ge 1000000000 ]; then printf '%d GB' $(( (b + 500000000) / 1000000000 ))
  else printf '%d MB' $(( (b + 500000) / 1000000 )); fi
}

clean_name() {   # safe as a folder name and inside a Docker volume line
  local LC_ALL=C s=${1//_/ } lead trail
  s=${s//[^A-Za-z0-9 .()+,-]/ }
  while [[ $s == *"  "* ]]; do s=${s//  / }; done
  lead=${s%%[! .-]*}; s=${s#"$lead"}                             # leading spaces, dots and dashes
  trail=${s##*[! .-]}; s=${s%"$trail"}                            # trailing ones
  printf '%s' "$s"
}

drive_kind() {   # drive_kind /dev/sdX "model" -> SSD, HDD, or nothing when it cannot be told
  local LC_ALL=C model=${2^^} line rota tran
  model=${model//_/ }
  if [[ $model =~ (^|[^A-Z0-9])SSD([^A-Z0-9]|$)|NVME ]]; then printf SSD; return 0; fi
  line=$(lsblk -dnbo ROTA,TRAN "$1" 2>/dev/null); line=${line%%$'\n'*}
  read -r rota tran <<<"$line"
  [ "${tran,,}" = nvme ] && { printf SSD; return 0; }
  case "$rota" in 1) printf HDD ;; 0) printf SSD ;; esac
  return 0
}

disk_base_name() {   # disk_base_name /dev/sdX -> "1 TB Samsung HDD"
  local d=$1 model size brand kind name
  model=$(lsblk -dno MODEL "$d" 2>/dev/null | sed 's/ *$//')
  size=$(lsblk -dnbo SIZE "$d" 2>/dev/null | head -1 | tr -d ' ')
  brand=$(drive_brand "$model")
  kind=$(drive_kind "$d" "$model")
  name="$([ -n "$size" ] && pretty_size "$size") ${brand:-$model} $kind"
  name=$(clean_name "$name")
  if [ -z "$name" ] || [ "$name" = "$(clean_name "$([ -n "$size" ] && pretty_size "$size")")" ]; then name=$(clean_name "$(pretty_size "${size:-0}") drive"); fi
  printf '%s' "$name"
}

chosen_name() {   # a name set in DRIVE_NAMES_FILE for this label
  [ -r "$DRIVE_NAMES_FILE" ] || return 0
  local n
  n=$(awk -F= -v k="$1" '{ gsub(/^[ \t]+|[ \t]+$/, "", $1) } $1 == k && !/^[ \t]*#/ { sub(/^[^=]*=/, ""); print; exit }' "$DRIVE_NAMES_FILE")
  clean_name "$n"
}

name_store_put() {   # name_store_put LABEL "name"
  local tmp
  mkdir -p "$(dirname "$NAME_STORE")" 2>/dev/null || return 0
  tmp=$(mktemp) || return 0
  { [ -r "$NAME_STORE" ] && awk -F'|' -v k="$1" '$1 != k' "$NAME_STORE"; printf '%s|%s\n' "$1" "$2"; } >"$tmp" 2>/dev/null
  cat "$tmp" >"$NAME_STORE" 2>/dev/null || true
  rm -f "$tmp"
}

name_store_del() {   # name_store_del LABEL
  [ -r "$NAME_STORE" ] || return 0
  local tmp; tmp=$(mktemp) || return 0
  awk -F'|' -v k="$1" '$1 != k' "$NAME_STORE" >"$tmp" 2>/dev/null; cat "$tmp" >"$NAME_STORE" 2>/dev/null || true
  rm -f "$tmp"
}

name_store_get() { [ -r "$NAME_STORE" ] && awk -F'|' -v k="$1" '$1 == k {print $2; exit}' "$NAME_STORE"; return 0; }

# While a look-only command runs, NAME_CACHE is a temporary folder holding the names already worked out, so each drive is asked about once
# instead of once for every other drive. It is created and removed by with_name_cache and is never set while anything is being changed.
name_cached() {   # name_cached KIND MOUNTPOINT function -> prints the name, from the cache when there is one
  local f
  if [ -n "${NAME_CACHE:-}" ] && [ -d "$NAME_CACHE" ]; then
    f="$NAME_CACHE/$1${2//\//_}"
    if [ -f "$f" ]; then cat "$f"; return 0; fi
    "$3" "$2" | tee "$f"
    return 0
  fi
  "$3" "$2"
}
with_name_cache() {   # with_name_cache function [args]: run a look-only function with the name cache switched on
  local rc=0
  NAME_CACHE=$(mktemp -d 2>/dev/null) || NAME_CACHE=""
  "$@" || rc=$?
  [ -n "$NAME_CACHE" ] && rm -rf "$NAME_CACHE"
  NAME_CACHE=""
  return "$rc"
}

branch_base_name() { name_cached base "$1" branch_base_calc; }
branch_base_calc() {   # the name of one pool drive, before numbering: chosen, else scanned now, else the one kept, else the label
  local mp=$1 label n part img
  label=$(basename "$mp")
  n=$(chosen_name "$label")
  [ -n "$n" ] && { printf '%s' "$n"; return 0; }
  if is_boot_section "$mp"; then   # "100 GB boot drive section", from the size of its file
    img=$(boot_image_of "$mp")
    if [ -f "$img" ]; then
      n="$(pretty_size "$(stat -c %s "$img")") boot drive section"
      [ "$(name_store_get "$label")" = "$n" ] || name_store_put "$label" "$n"
      printf '%s' "$n"; return 0
    fi
    n=$(name_store_get "$label"); printf '%s' "${n:-boot drive section}"; return 0
  fi
  part=$(branch_part "$mp")
  if [ -n "$part" ] && mountpoint -q "$mp"; then
    n=$(disk_base_name "$(disk_of_part "$part")")
    if [ -n "$n" ]; then
      [ "$(name_store_get "$label")" = "$n" ] || name_store_put "$label" "$n"
      printf '%s' "$n"; return 0
    fi
  fi
  n=$(name_store_get "$label")
  printf '%s' "${n:-$label}"
}

branch_name() { name_cached shown "$1" branch_name_calc; }
branch_name_calc() {   # the name shown for a pool drive; a name shared with another pool drive gets a number (1, 2, ...)
  local mp=$1 b n base total=0 mine=0
  base=$(branch_base_name "$mp")
  for b in $(all_branches); do
    n=$(branch_base_name "$b")
    if [ "$n" = "$base" ]; then total=$((total + 1)); [ "$b" = "$mp" ] && mine=$total; fi
  done
  if [ "$total" -gt 1 ] && [ "$mine" -gt 0 ]; then printf '%s %s' "$base" "$mine"; else printf '%s' "$base"; fi
}

disk_details() {   # "(/dev/sdb, 931.5G, TOSHIBA MQ01ABD100, sata)"
  local d=$1
  printf '(%s, %s, %s, %s)' "$d" "$(lsblk -dno SIZE "$d" | tr -d ' ')" "$(lsblk -dno MODEL "$d" | sed 's/ *$//')" "$(lsblk -dno TRAN "$d" | sed 's/ *$//')"
}

disk_summary() {   # "1 TB Toshiba HDD  (/dev/sdb, 931.5G, TOSHIBA MQ01ABD100, sata)"
  printf '%s  %s' "$(disk_base_name "$1")" "$(disk_details "$1")"
}

smart_health() {
  [ "$TEST_MODE" = 1 ] && { echo "skipped (test mode)"; return; }
  command -v smartctl >/dev/null 2>&1 || { echo "smartctl not installed"; return; }
  local o opt
  for opt in "" "-d sat"; do
    # shellcheck disable=SC2086
    o=$(smartctl -H $opt "$1" 2>&1)
    if grep -Eq 'PASSED|: OK' <<<"$o"; then echo "PASSED"; return; fi
    if grep -q 'FAILED' <<<"$o"; then echo "FAILED"; return; fi
  done
  echo "unknown"
}

describe_disk() {
  local d=$1
  say ""
  say "Drive: $(disk_summary "$d")"
  say "Serial: $(lsblk -dno SERIAL "$d" | sed 's/ *$//')"
  say "SMART health: $(smart_health "$d")"
  lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS "$d"
  say ""
}

fs_label() { blkid -p -s LABEL -o value "$1" 2>/dev/null | sed 's/ *$//'; }
fs_type()  { blkid -p -s TYPE  -o value "$1" 2>/dev/null | sed 's/ *$//'; }

first_part() {
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    lsblk -lnpo NAME,TYPE "$1" 2>/dev/null | awk '$2 == "part" {print $1; exit}' | grep . && return 0
    sleep 1
  done
  return 1
}

parts_of() { lsblk -lnpo NAME,TYPE "$1" 2>/dev/null | awk '$2 == "part" {print $1}'; }

umount_disk_parts() {
  local p
  for p in $(parts_of "$1"); do
    if findmnt -rn -S "$p" >/dev/null 2>&1; then
      umount "$p" 2>/dev/null || die "Could not unmount $p. Close anything using it and try again."
    fi
  done
  if findmnt -rn -S "$1" >/dev/null 2>&1; then umount "$1" 2>/dev/null || true; fi
}

next_label() {
  local p n=1
  p=$(role_prefix "$1")
  while grep -Eq "^[^#]*[[:space:]]${DISKS_DIR}/${p}${n}[[:space:]]" "$FSTAB" || [ -e "/dev/disk/by-label/${p}${n}" ]; do n=$((n + 1)); done
  echo "$p$n"
}

format_disk() {   # format_disk /dev/sdX LABEL -> prints partition path
  local dev=$1 label=$2 p vg
  refuse_unsafe_disk "$dev"
  umount_disk_parts "$dev"
  if command -v pvs >/dev/null 2>&1; then
    for vg in $(pvs --noheadings -o pv_name,vg_name 2>/dev/null | awk -v d="$dev" 'index($1, d) == 1 && $2 != "" {print $2}' | sort -u); do
      note "Deactivating old LVM group $vg on this drive..."
      vgchange -an "$vg" >/dev/null 2>&1 || warn "Could not deactivate $vg"
    done
  fi
  for p in $(parts_of "$dev"); do wipefs -a "$p" >/dev/null 2>&1 || true; done
  wipefs -a "$dev" >/dev/null 2>&1 || die "wipefs failed on $dev"
  parted -s "$dev" mklabel gpt mkpart storage ext4 1MiB 100% >/dev/null 2>&1 || die "parted failed on $dev"
  partprobe "$dev" >/dev/null 2>&1 || true
  udevadm settle 2>/dev/null || true
  p=$(first_part "$dev") || die "The new partition did not appear on $dev"
  wipefs -a "$p" >/dev/null 2>&1 || true
  mkfs.ext4 -F -q -L "$label" -m 0 "$p" >&2 || die "mkfs failed on $p"
  udevadm settle 2>/dev/null || true
  log "formatted $dev -> $p label $label"
  echo "$p"
}

