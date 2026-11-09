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

drive_kind() {   # drive_kind /dev/sdX "model" -> SSD, HDD, Flash (a USB stick), or nothing when it cannot be told
  local LC_ALL=C model=${2^^} line rota tran
  model=${model//_/ }
  if [[ $model =~ (^|[^A-Z0-9])SSD([^A-Z0-9]|$)|NVME ]]; then printf SSD; return 0; fi
  line=$(lsblk -dnbo ROTA,TRAN "$1" 2>/dev/null); line=${line%%$'\n'*}
  read -r rota tran <<<"$line"
  [ "${tran,,}" = nvme ] && { printf SSD; return 0; }
  # a USB stick: it plugs in with USB, can be pulled out (removable) and often claims to spin like a hard drive; or its model says so
  if [ "${tran,,}" = usb ]; then
    if [[ $model =~ CRUZER|DATATRAVELER|FLASH|JUMPDRIVE|ULTRA\ FIT|STORE\ N\ GO|TRANSMEMORY|MICRO\ SD|CARD\ READER ]] || [ "$(lsblk -dno RM "$1" 2>/dev/null | head -1 | tr -d ' ')" = 1 ]; then printf Flash; return 0; fi
  fi
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
  while grep -Eq "^[^#]*[[:space:]]${DISKS_DIR}/${p}${n}[[:space:]]" "$FSTAB" || [ -e "/dev/disk/by-label/${p}${n}" ] || { [ -n "$PANEL_RESERVE_DIR" ] && [ -e "$PANEL_RESERVE_DIR/label-${p}${n}" ]; }; do n=$((n + 1)); done
  echo "$p$n"
}

disk_holder_pids() {   # disk_holder_pids /dev/sdX -> the processes that still have the drive (or a partition of it) mounted in their own view of the system, or open
  local dev=$1 mm f pid
  for mm in $(lsblk -lno MAJ:MIN "$dev" 2>/dev/null | tr -d ' '); do
    for f in /proc/[0-9]*/mountinfo; do
      awk -v m="$mm" '$3 == m {found = 1; exit} END {exit !found}' "$f" 2>/dev/null || continue
      pid=${f#/proc/}; echo "${pid%/mountinfo}"
    done
  done
  # shellcheck disable=SC2046
  fuser $(lsblk -lnpo NAME "$dev" 2>/dev/null) 2>/dev/null | tr -s ' ' '\n'
}

disk_holders() {   # disk_holders /dev/sdX -> one readable line for everything that still holds the drive
  local dev=$1 d n pid
  d=${dev#/dev/}
  for pid in $(disk_holder_pids "$dev" | sort -un); do
    [ -d "/proc/$pid" ] && echo "process $pid ($(cat "/proc/$pid/comm" 2>/dev/null))"
  done
  for n in "/sys/block/$d"/holders/* "/sys/block/$d/$d"*/holders/*; do [ -e "$n" ] && echo "kernel: held by $(basename "$n")"; done
  grep -q "^$dev" /proc/swaps 2>/dev/null && echo "used as swap space"
  return 0
}

unmount_in_views() {   # unmount_in_views /dev/sdX: a program (often a container) that has its own copy of the old mount is told to let go of it, without stopping the program
  local dev=$1 mm pid ns seen=" " tgt
  for mm in $(lsblk -lno MAJ:MIN "$dev" 2>/dev/null | tr -d ' '); do
    for pid in $(disk_holder_pids "$dev" | sort -un); do
      ns=$(readlink "/proc/$pid/ns/mnt" 2>/dev/null) || continue
      case "$seen" in *" $ns|$mm "*) continue ;; esac
      seen="$seen$ns|$mm "
      while read -r tgt; do
        [ -n "$tgt" ] && nsenter -t "$pid" -m -- umount -l "$tgt" >/dev/null 2>&1
      done < <(awk -v m="$mm" '$3 == m {print $5}' "/proc/$pid/mountinfo" 2>/dev/null)
    done
  done
  return 0
}

release_disk() {   # release_disk /dev/sdX: first every program with its own copy of the old mount lets go of it; a container that still holds the drive after that is stopped for a moment (HOLDER_STOPPED; format_disk starts it again)
  local dev=$1 pid ns cpid cname cns held=""
  command -v nsenter >/dev/null 2>&1 && unmount_in_views "$dev"
  [ -z "$(disk_holder_pids "$dev")" ] && return 0
  docker_ok || return 0
  for pid in $(disk_holder_pids "$dev" | sort -un); do
    ns=$(readlink "/proc/$pid/ns/mnt" 2>/dev/null) || continue
    while read -r cpid cname; do
      [ "${cpid:-0}" -gt 0 ] 2>/dev/null || continue
      cns=$(readlink "/proc/$cpid/ns/mnt" 2>/dev/null)
      [ -n "$cns" ] && [ "$cns" = "$ns" ] && held="$held ${cname#/}"
    done < <(docker ps -q | xargs -r docker inspect --format '{{.State.Pid}} {{.Name}}' 2>/dev/null)
  done
  held=$(echo "$held" | tr ' ' '\n' | sort -u | tr '\n' ' ')
  [ -n "${held// /}" ] || return 0
  note "These containers still hold the old drive: $held. Stopping them for a moment."
  # shellcheck disable=SC2086
  docker_each stop $held >/dev/null
  HOLDER_STOPPED="$HOLDER_STOPPED $held"
}

release_started() {   # start the containers that release_disk stopped
  [ -n "${HOLDER_STOPPED// /}" ] || return 0
  # shellcheck disable=SC2086
  docker_each start $HOLDER_STOPPED >/dev/null
  HOLDER_STOPPED=""
}

retry_busy() {   # retry_busy COMMAND...: a drive that was just unplugged from a pool or just changed is sometimes still looked at by the system for a moment ("busy"): try again a few times
  local i
  for i in 1 2 3 4 5 6; do
    "$@" && return 0
    sleep 2; udevadm settle 2>/dev/null || true
  done
  "$@"
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
  udevadm settle 2>/dev/null || true
  if ! wipefs -a "$dev" >/dev/null 2>&1; then
    release_disk "$dev"
    umount_disk_parts "$dev"
    retry_busy wipefs -a "$dev" >/dev/null 2>&1 || { release_started; die "wipefs failed on $dev (the drive is busy: $(wipefs -a "$dev" 2>&1 | tail -1 | sed 's/^wipefs: error: //'); held by: $(disk_holders "$dev" | tr '\n' ';' | sed 's/;$//'; true))"; }
  fi
  retry_busy parted -s "$dev" mklabel gpt mkpart storage ext4 1MiB 100% >/dev/null 2>&1 || die "parted failed on $dev"
  partprobe "$dev" >/dev/null 2>&1 || true
  udevadm settle 2>/dev/null || true
  p=$(first_part "$dev") || die "The new partition did not appear on $dev"
  wipefs -a "$p" >/dev/null 2>&1 || true
  retry_busy mkfs.ext4 -F -q -L "$label" -m 0 "$p" >&2 || die "mkfs failed on $p"
  udevadm settle 2>/dev/null || true
  release_started
  log "formatted $dev -> $p label $label"
  echo "$p"
}

