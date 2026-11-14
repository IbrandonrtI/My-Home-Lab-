PRESET_IDS="pool mirror snapraid1 snapraid2 zfs-stripe zfs-mirror zfs-raidz1 zfs-raidz2 zfs-raidz3 md-raid0 md-raid1 md-raid5 md-raid6 md-raid10"

preset_alias() {
  case "$1" in
    raidz1|raidz2|raidz3) echo "zfs-$1" ;;
    raid0|raid1|raid5|raid6|raid10) echo "md-$1" ;;
    *) echo "$1" ;;
  esac
}
preset_known() { case " $PRESET_IDS " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
preset_kind() { case "$1" in zfs-*) echo zfs ;; md-*) echo md ;; *) echo pool ;; esac; }
preset_is_array() { case "$1" in zfs-*|md-*) return 0 ;; *) return 1 ;; esac; }
preset_title() {
  case "$1" in
    pool)       echo "Plain pool" ;;
    mirror)     echo "Mirror (nightly copy)" ;;
    snapraid1)  echo "SnapRAID, 1 parity drive" ;;
    snapraid2)  echo "SnapRAID, 2 parity drives" ;;
    zfs-stripe) echo "ZFS, striped (fast, no redundancy)" ;;
    zfs-mirror) echo "ZFS, mirror" ;;
    zfs-raidz1) echo "ZFS, RAIDZ1 (tolerates 1 failed drive)" ;;
    zfs-raidz2) echo "ZFS, RAIDZ2 (tolerates 2 failed drives)" ;;
    zfs-raidz3) echo "ZFS, RAIDZ3 (tolerates 3 failed drives)" ;;
    md-raid0)   echo "RAID 0, striped (fast, no redundancy)" ;;
    md-raid1)   echo "RAID 1, mirror" ;;
    md-raid5)   echo "RAID 5 (tolerates 1 failed drive)" ;;
    md-raid6)   echo "RAID 6 (tolerates 2 failed drives)" ;;
    md-raid10)  echo "RAID 10, mirrored stripes" ;;
  esac
}
preset_blurb() {
  case "$1" in
    pool)       echo "All drives are combined into one pool. New files fill one drive after another. There is no redundancy: if a drive fails, the files on it are lost." ;;
    mirror)     echo "One Main drive and one Backup drive. The Backup drive receives a copy of the Main drive every night. The copy is not instant." ;;
    snapraid1)  echo "The largest drive holds only parity data, so the contents of one failed drive can be rebuilt. Parity is updated every night at 04:00, not instantly." ;;
    snapraid2)  echo "The two largest drives hold only parity data, so the contents of two failed drives can be rebuilt. Parity is updated every night at 04:00, not instantly." ;;
    zfs-stripe) echo "ZFS spreads every file across all drives. This is fast and uses all the space, but there is no redundancy: if one drive fails, all data is lost. Use it only for files that can be recovered elsewhere." ;;
    zfs-mirror) echo "ZFS keeps the same data on every drive. Only the space of one drive is usable. The data is safe as long as one drive still works." ;;
    zfs-raidz1) echo "ZFS that uses the space of one drive for parity. If one drive fails, it can be replaced without losing data." ;;
    zfs-raidz2) echo "ZFS that uses the space of two drives for parity. Two drives can fail at the same time without data loss." ;;
    zfs-raidz3) echo "ZFS that uses the space of three drives for parity. Three drives can fail at the same time without data loss." ;;
    md-raid0)   echo "Linux RAID that spreads every file across all drives. This is fast and uses all the space, but there is no redundancy: if one drive fails, all data is lost." ;;
    md-raid1)   echo "Linux RAID that keeps the same data on every drive. Only the space of one drive is usable. The data is safe as long as one drive still works." ;;
    md-raid5)   echo "Linux RAID that uses the space of one drive for parity. If one drive fails, it can be replaced without losing data." ;;
    md-raid6)   echo "Linux RAID that uses the space of two drives for parity. Two drives can fail at the same time without data loss." ;;
    md-raid10)  echo "Linux RAID that mirrors pairs of drives and spreads files across the pairs. It is fast and uses half the space. If a drive fails, its mirror partner keeps the data." ;;
  esac
}
preset_min()  { case "$1" in pool) echo 1 ;; mirror|zfs-stripe|zfs-mirror|md-raid0|md-raid1) echo 2 ;; snapraid1|zfs-raidz1|md-raid5) echo 3 ;; snapraid2|zfs-raidz2|md-raid6|md-raid10) echo 4 ;; zfs-raidz3) echo 5 ;; esac; }
preset_max()  { case "$1" in mirror) echo 2 ;; *) echo 0 ;; esac; }
preset_parity_count() { case "$1" in snapraid1) echo 1 ;; snapraid2) echo 2 ;; *) echo 0 ;; esac; }
preset_drives_text() {
  local min max; min=$(preset_min "$1"); max=$(preset_max "$1")
  if [ "$max" -eq "$min" ]; then echo "exactly $min"; elif [ "$min" -eq 1 ]; then echo "1 or more"; else echo "$min or more"; fi
}
preset_tool_hint() {
  case "$(preset_kind "$1")" in
    zfs) command -v zpool >/dev/null 2>&1 && command -v zfs >/dev/null 2>&1 || echo "sudo apt install -y zfsutils-linux" ;;
    md)  command -v mdadm >/dev/null 2>&1 || echo "sudo apt install -y mdadm" ;;
    *)   case "$1" in snapraid*) command -v snapraid >/dev/null 2>&1 || echo "sudo apt install -y snapraid" ;; esac ;;
  esac
  return 0
}

# preset_capacity ID SIZE...: the usable space in bytes, or nothing when the number of drives does not fit.
preset_capacity() {
  local id=$1; shift
  [ $# -gt 0 ] || return 0
  local -a s=(); local n sum=0 x i par max small
  mapfile -t s < <(printf '%s\n' "$@" | sort -rn)
  n=${#s[@]}; max=$(preset_max "$id"); small=${s[$((n - 1))]}
  [ "$n" -ge "$(preset_min "$id")" ] || return 0
  [ "$max" -eq 0 ] || [ "$n" -le "$max" ] || return 0
  for x in "${s[@]}"; do sum=$((sum + x)); done
  case "$id" in
    pool|zfs-stripe|md-raid0) echo "$sum" ;;
    mirror) echo "${s[1]}" ;;
    zfs-mirror|md-raid1) echo "$small" ;;
    zfs-raidz1|md-raid5) echo $(( (n - 1) * small )) ;;
    zfs-raidz2|md-raid6) echo $(( (n - 2) * small )) ;;
    zfs-raidz3) echo $(( (n - 3) * small )) ;;
    md-raid10) echo $(( n * small / 2 )) ;;
    snapraid1|snapraid2)
      par=$(preset_parity_count "$id")
      for ((i = 0; i < par; i++)); do sum=$((sum - s[i])); done
      echo "$sum" ;;
  esac
}

disk_is_blank() { [ -z "$(parts_of "$1")" ] && [ -z "$(blkid -p -s TYPE -o value "$1" 2>/dev/null)" ]; }
blank_disks() { local d; for d in $(candidate_disks); do disk_is_blank "$d" && echo "$d"; done; }
disk_size_bytes() { lsblk -dnbo SIZE "$1" 2>/dev/null | head -1 | tr -d ' '; }

parity_mounts() { fstab_active | awk -v d="$DISKS_DIR/$PARITY_PREFIX" '$2 ~ "^" d "[0-9]+$" {print $2}' | sort -V; }
preset_current() { [ -r "$PRESET_FILE" ] && awk -F'|' 'NR == 1 {print $1}' "$PRESET_FILE"; return 0; }
preset_record() { printf '%s|%s|%s\n' "$1" "$(date +%F)" "$2" >"$PRESET_FILE"; }
snapraid_active() { case "$(preset_current)" in snapraid1|snapraid2) return 0 ;; *) return 1 ;; esac; }

# Write the SnapRAID settings: the protection drives, the content files and the data drives.
snapraid_conf_write() {
  local mp i=0 n=0
  mkdir -p "$(dirname "$SNAPRAID_CONF")" "$SNAPRAID_CONTENT_DIR" 2>/dev/null || true
  {
    echo "# Written by 'sudo drives preset'. It is written again whenever the drives of the Main pool change."
    for mp in $(parity_mounts); do
      i=$((i + 1))
      if [ "$i" -eq 1 ]; then echo "parity $mp/snapraid.parity"; else echo "$i-parity $mp/snapraid.$i-parity"; fi
    done
    echo "content $SNAPRAID_CONTENT_DIR/snapraid.content"
    for mp in $(branches_of main); do
      is_boot_section "$mp" && continue
      n=$((n + 1)); [ "$n" -le 2 ] && echo "content $mp/snapraid.content"
    done
    for mp in $(branches_of main); do
      is_boot_section "$mp" && continue
      echo "data $(basename "$mp" | tr 'A-Z' 'a-z') $mp"
    done
    echo "exclude /lost+found/"
    echo "exclude /tmp/"
    echo "exclude *.unrecoverable"
    echo "exclude .Trash-*/"
  } >"$SNAPRAID_CONF"
}

snapraid_cron_write() {
  mkdir -p "$(dirname "$SNAPRAID_CRON")" 2>/dev/null || true
  cat >"$SNAPRAID_CRON" <<EOF
# SnapRAID (written by 'sudo drives preset'): update the protection data every night at 04:00,
# and check a part of the files on the 1st of every month. The results are in $SNAPRAID_LOG
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 4 * * * root snapraid -c $SNAPRAID_CONF sync -q >>$SNAPRAID_LOG 2>&1
0 5 1 * * root snapraid -c $SNAPRAID_CONF scrub -p 5 -o 30 -q >>$SNAPRAID_LOG 2>&1
EOF
  chmod 644 "$SNAPRAID_CRON" 2>/dev/null || true
}

snapraid_forget() {
  rm -f "$SNAPRAID_CONF" "$SNAPRAID_CRON" "$PRESET_FILE"
}

snapraid_flow() {
  local what=${1:-status}
  case "$what" in
    status|diff|sync|scrub) ;;
    *) note "Unknown SnapRAID action: $what"; note "Use one of: status (is the parity up to date?), diff (what changed since the last sync), sync (update the parity now), scrub (check part of the files)."; return 1 ;;
  esac
  snapraid_active || { note "There is no SnapRAID setup. Build one with:  sudo drives preset snapraid1"; return 1; }
  command -v snapraid >/dev/null 2>&1 || { note "SnapRAID is not installed. Install it with:  sudo apt install -y snapraid"; return 1; }
  dry_gate "Run:  snapraid -c $SNAPRAID_CONF $what" && return 0
  snapraid -c "$SNAPRAID_CONF" "$what"
}

