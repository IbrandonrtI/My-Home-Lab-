# ---------- ready-made setups (drives preset): a whole drive setup built from empty drives in one go ----------
# What was built is kept in PRESET_FILE (one line: ID|date|labels). A setup uses EMPTY drives only: they are formatted.
PRESET_IDS="pool mirror snapraid1 snapraid2 zfs-stripe zfs-mirror zfs-raidz1 zfs-raidz2 zfs-raidz3 md-raid0 md-raid1 md-raid5 md-raid6 md-raid10"

preset_alias() {   # the short names people type -> the full name of the setup
  case "$1" in
    raidz1|raidz2|raidz3) echo "zfs-$1" ;;
    raid0|raid1|raid5|raid6|raid10) echo "md-$1" ;;
    *) echo "$1" ;;
  esac
}
preset_known() { case " $PRESET_IDS " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
preset_kind() { case "$1" in zfs-*) echo zfs ;; md-*) echo md ;; *) echo pool ;; esac; }   # pool = separate drives joined by mergerfs; zfs / md = a real RAID array
preset_is_array() { case "$1" in zfs-*|md-*) return 0 ;; *) return 1 ;; esac; }
preset_title() {
  case "$1" in
    pool)       echo "Plain pool" ;;
    mirror)     echo "Mirror (nightly copy)" ;;
    snapraid1)  echo "SnapRAID, 1 protection drive" ;;
    snapraid2)  echo "SnapRAID, 2 protection drives" ;;
    zfs-stripe) echo "ZFS, striped (fast, NO protection)" ;;
    zfs-mirror) echo "ZFS, mirror" ;;
    zfs-raidz1) echo "ZFS, RAIDZ1 (1 drive can die)" ;;
    zfs-raidz2) echo "ZFS, RAIDZ2 (2 drives can die)" ;;
    zfs-raidz3) echo "ZFS, RAIDZ3 (3 drives can die)" ;;
    md-raid0)   echo "RAID 0, striped (fast, NO protection)" ;;
    md-raid1)   echo "RAID 1, mirror" ;;
    md-raid5)   echo "RAID 5 (1 drive can die)" ;;
    md-raid6)   echo "RAID 6 (2 drives can die)" ;;
    md-raid10)  echo "RAID 10, mirrored stripes" ;;
  esac
}
preset_blurb() {
  case "$1" in
    pool)       echo "All the drives in one big pool. New files fill one drive after the other. No protection: a dead drive loses its files." ;;
    mirror)     echo "One Main drive and one Backup drive. Every night the Backup gets a copy of the Main (not instant)." ;;
    snapraid1)  echo "The biggest drive only holds protection data, so one dead drive can be rebuilt. Updated every night at 04:00, not instant." ;;
    snapraid2)  echo "The two biggest drives hold protection data, so two dead drives can be rebuilt. Updated every night at 04:00, not instant." ;;
    zfs-stripe) echo "ZFS spreads every file over all the drives: fast and all the space, but ONE dead drive loses EVERYTHING. Only for files you can get back." ;;
    zfs-mirror) echo "ZFS keeps the same data on every drive. You only get the space of one drive; the data survives while one drive is alive." ;;
    zfs-raidz1) echo "ZFS with the space of one drive used for protection: one dead drive can be replaced without losing anything." ;;
    zfs-raidz2) echo "ZFS with the space of two drives used for protection: two drives can die at the same time." ;;
    zfs-raidz3) echo "ZFS with the space of three drives used for protection: three drives can die at the same time." ;;
    md-raid0)   echo "Linux RAID that spreads every file over all the drives: fast and all the space, but ONE dead drive loses EVERYTHING." ;;
    md-raid1)   echo "Linux RAID that keeps the same data on every drive. You only get the space of one drive; the data survives while one drive is alive." ;;
    md-raid5)   echo "Linux RAID with the space of one drive used for protection: one dead drive can be replaced without losing anything." ;;
    md-raid6)   echo "Linux RAID with the space of two drives used for protection: two drives can die at the same time." ;;
    md-raid10)  echo "Linux RAID that mirrors pairs of drives and spreads files over the pairs: fast, half the space, and a dead drive is covered by its twin." ;;
  esac
}
preset_min()  { case "$1" in pool) echo 1 ;; mirror|zfs-stripe|zfs-mirror|md-raid0|md-raid1) echo 2 ;; snapraid1|zfs-raidz1|md-raid5) echo 3 ;; snapraid2|zfs-raidz2|md-raid6|md-raid10) echo 4 ;; zfs-raidz3) echo 5 ;; esac; }
preset_max()  { case "$1" in mirror) echo 2 ;; *) echo 0 ;; esac; }                     # 0 = as many as you like
preset_parity_count() { case "$1" in snapraid1) echo 1 ;; snapraid2) echo 2 ;; *) echo 0 ;; esac; }
preset_drives_text() {
  local min max; min=$(preset_min "$1"); max=$(preset_max "$1")
  if [ "$max" -eq "$min" ]; then echo "exactly $min"; elif [ "$min" -eq 1 ]; then echo "1 or more"; else echo "$min or more"; fi
}
preset_tool_hint() {   # preset_tool_hint ID: nothing when the programs the setup needs are installed, else the command that installs them
  case "$(preset_kind "$1")" in
    zfs) command -v zpool >/dev/null 2>&1 && command -v zfs >/dev/null 2>&1 || echo "sudo apt install -y zfsutils-linux" ;;
    md)  command -v mdadm >/dev/null 2>&1 || echo "sudo apt install -y mdadm" ;;
    *)   case "$1" in snapraid*) command -v snapraid >/dev/null 2>&1 || echo "sudo apt install -y snapraid" ;; esac ;;
  esac
  return 0
}

preset_capacity() {   # preset_capacity ID SIZE... -> the space you can use, in bytes (nothing when the number of drives does not fit)
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
    mirror) echo "${s[1]}" ;;                      # the smaller of the two
    zfs-mirror|md-raid1) echo "$small" ;;          # every drive holds everything: the smallest drive decides
    zfs-raidz1|md-raid5) echo $(( (n - 1) * small )) ;;     # RAID uses only as much of each drive as the smallest one has
    zfs-raidz2|md-raid6) echo $(( (n - 2) * small )) ;;
    zfs-raidz3) echo $(( (n - 3) * small )) ;;
    md-raid10) echo $(( n * small / 2 )) ;;
    snapraid1|snapraid2)                           # the biggest drives only hold protection data
      par=$(preset_parity_count "$id")
      for ((i = 0; i < par; i++)); do sum=$((sum - s[i])); done
      echo "$sum" ;;
  esac
}

disk_is_blank() { [ -z "$(parts_of "$1")" ] && [ -z "$(blkid -p -s TYPE -o value "$1" 2>/dev/null)" ]; }   # no partition and no file system: empty or new
blank_disks() { local d; for d in $(candidate_disks); do disk_is_blank "$d" && echo "$d"; done; }
disk_size_bytes() { lsblk -dnbo SIZE "$1" 2>/dev/null | head -1 | tr -d ' '; }

parity_mounts() { fstab_active | awk -v d="$DISKS_DIR/$PARITY_PREFIX" '$2 ~ "^" d "[0-9]+$" {print $2}' | sort -V; }   # the SnapRAID protection drives
preset_current() { [ -r "$PRESET_FILE" ] && awk -F'|' 'NR == 1 {print $1}' "$PRESET_FILE"; return 0; }
preset_record() { printf '%s|%s|%s\n' "$1" "$(date +%F)" "$2" >"$PRESET_FILE"; }
snapraid_active() { case "$(preset_current)" in snapraid1|snapraid2) return 0 ;; *) return 1 ;; esac; }

snapraid_conf_write() {   # the SnapRAID settings: the protection drives, a list of the files that say what is where, the data drives
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

snapraid_forget() {   # the SnapRAID setup is taken apart: its settings, its schedule and the record of it go away (the drives are handled by the caller)
  rm -f "$SNAPRAID_CONF" "$SNAPRAID_CRON" "$PRESET_FILE"
}

snapraid_flow() {   # snapraid status|diff|sync|scrub: SnapRAID by hand, with this setup's settings
  local what=${1:-status}
  case "$what" in
    status|diff|sync|scrub) ;;
    *) note "Unknown SnapRAID action: $what"; note "Use one of: status (is the protection up to date?), diff (what changed since the last update), sync (update it now), scrub (check part of the files)."; return 1 ;;
  esac
  snapraid_active || { note "There is no SnapRAID setup. Build one with:  sudo drives preset snapraid1"; return 1; }
  command -v snapraid >/dev/null 2>&1 || { note "SnapRAID is not installed. Install it with:  sudo apt install -y snapraid"; return 1; }
  dry_gate "Run:  snapraid -c $SNAPRAID_CONF $what" && return 0
  snapraid -c "$SNAPRAID_CONF" "$what"
}

