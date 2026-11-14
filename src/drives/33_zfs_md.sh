array_active() { preset_is_array "$(preset_current)"; }
array_tokens() { [ -r "$PRESET_FILE" ] && awk -F'|' 'NR == 1 {print $3}' "$PRESET_FILE" | tr ' ' '\n' | grep .; return 0; }
array_members() { array_tokens | sed 's/^[a-z]*=//' | grep '^/'; return 0; }
array_encrypted() { array_tokens | grep -qx encrypted; }
array_disk_kinds() {
  local t kind path r d
  array_active || return 0
  for t in $(array_tokens); do
    kind=data; path=$t
    case "$t" in spare=*|cache=*) kind=${t%%=*}; path=${t#*=} ;; esac
    case "$path" in /*) ;; *) continue ;; esac
    r=$(readlink -f "$path" 2>/dev/null)
    if [ -b "$r" ]; then d=$(disk_of_part "$r"); echo "$d $kind"; else echo "- $kind $path"; fi
  done
}
array_disks() { array_disk_kinds | awk '$1 != "-" {print $1}' | sort -u; }
array_kind_text() {
  case "$1" in spare) echo "connected (hot spare)" ;; cache) echo "connected (SSD read cache)" ;; *) echo "connected (in the $(preset_title "$(preset_current)") array)" ;; esac
}
disk_stable_name() {
  local l
  for l in /dev/disk/by-id/*; do
    [ -L "$l" ] || continue
    case "$(basename "$l")" in *-part[0-9]*|wwn-*|nvme-eui.*|nvme-nvme.*|md-*|dm-*|lvm-*|scsi-*) continue ;; esac
    [ "$(readlink -f "$l")" = "$1" ] && { echo "$l"; return 0; }
  done
  echo "$1"
}
array_guard() {
  array_active || return 0
  note "The Main pool is a $(preset_title "$(preset_current)") array (built with  sudo drives preset)."
  note "This command is for pools of separate drives, so it does not apply to an array."
  note "To view the array, run  sudo drives status.  To remove it (this deletes its files), run  sudo drives release."
  return 1
}
array_health_text() {
  local h st
  case "$(preset_kind "$(preset_current)")" in
    zfs) h=$(zpool list -H -o health "$ZFS_POOL_NAME" 2>/dev/null)
         echo "${h:-unknown}   (details:  zpool status $ZFS_POOL_NAME)" ;;
    md)  st=$(mdadm --detail "$MD_DEVICE" 2>/dev/null | awk -F' : ' '/^ *State :/ {gsub(/^ +| +$/, "", $2); print $2; exit}')
         h=$(grep -E '(resync|recovery|reshape) *=' /proc/mdstat 2>/dev/null | head -1 | sed 's/^ *//')
         echo "${st:-unknown}${h:+   (building: $h)}   (details:  mdadm --detail $MD_DEVICE)" ;;
  esac
}

zfs_scrub_cron_write() {
  [ -e "$ZFS_SYSTEM_SCRUB" ] && return 0
  mkdir -p "$(dirname "$ZFS_SCRUB_CRON")" 2>/dev/null || true
  printf '# ZFS (written by '"'"'sudo drives preset'"'"'): check all the data of the pool on the 1st of every month at 03:00.\n0 3 1 * * root zpool scrub %s\n' "$ZFS_POOL_NAME" >"$ZFS_SCRUB_CRON"
  chmod 644 "$ZFS_SCRUB_CRON" 2>/dev/null || true
}

array_service_folders() {
  mkdir -p "$MAIN_POOL/immich" "$MAIN_POOL/nextcloud"
  give_to_owner "$MAIN_POOL"
  give_to_owner "$MAIN_POOL/immich"
  chown 33:33 "$MAIN_POOL/nextcloud" 2>/dev/null || true
}

key_make() {
  local f="$KEY_DIR/$1.key"
  mkdir -p "$KEY_DIR" && chmod 700 "$KEY_DIR" 2>/dev/null || true
  if [ -e "$f" ]; then warn "The key file $f already exists. Move it elsewhere first. It may be the only key to an older array."; return 1; fi
  ( umask 077; head -c "${2:-32}" /dev/urandom >"$f" ) || { warn "Could not create the key file $f."; return 1; }
  chmod 400 "$f"
  echo "$f"
}
# Write the unit that loads the ZFS key at boot, before the pool is mounted. The key file is on the boot drive.
zfs_key_unit_write() {
  local zbin; zbin=$(command -v zfs || echo /usr/sbin/zfs)
  mkdir -p "$(dirname "$ZFS_KEY_UNIT")" 2>/dev/null || true
  cat >"$ZFS_KEY_UNIT" <<UNIT
# Written by 'sudo drives preset': unlock the encrypted ZFS pool with its key file before it is mounted.
[Unit]
Description=Unlock the encrypted ZFS pool $ZFS_POOL_NAME
DefaultDependencies=no
After=zfs-import.target
Before=zfs-mount.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=-$zbin load-key -r $ZFS_POOL_NAME

[Install]
WantedBy=zfs-mount.service
UNIT
  if [ "$TEST_MODE" != 1 ]; then
    systemctl daemon-reload
    systemctl enable homelab-zfs-key.service >/dev/null 2>&1 || warn "Could not enable the unlock service. Run:  sudo systemctl enable homelab-zfs-key.service"
  fi
}

zfs_build() {
  local id=$1 enc=$2 key="" mnt="${ARRAY_MOUNT:-$MAIN_POOL}"; shift 2
  local -a vdev=() eopts=()
  case "$id" in zfs-mirror) vdev=(mirror) ;; zfs-raidz1) vdev=(raidz1) ;; zfs-raidz2) vdev=(raidz2) ;; zfs-raidz3) vdev=(raidz3) ;; esac
  if [ "$enc" = 1 ]; then
    key=$(key_make "$ZFS_POOL_NAME" 32) || return 1
    eopts=(-O encryption=aes-256-gcm -O keyformat=raw -O "keylocation=file://$key")
  fi
  mkdir -p "$mnt"
  if ! zpool create -f -o ashift=12 -O compression=lz4 -O atime=off -O xattr=sa -O acltype=posixacl ${eopts[@]+"${eopts[@]}"} \
       -O mountpoint="$mnt" "$ZFS_POOL_NAME" ${vdev[@]+"${vdev[@]}"} "$@" 9>&- >&2; then
    [ -z "$key" ] || rm -f "$key"
    return 1
  fi
  [ "$enc" = 1 ] && zfs_key_unit_write
  zfs_scrub_cron_write
  mountpoint -q "$mnt" || { warn "The ZFS pool was created but is not mounted at $mnt."; return 1; }
}

md_conf_forget() {
  [ -w "$MDADM_CONF" ] && sed -i "/^ARRAY .*$MD_NAME/d" "$MDADM_CONF"
  return 0
}
md_conf_write() {
  mkdir -p "$(dirname "$MDADM_CONF")"; touch "$MDADM_CONF"
  md_conf_forget
  mdadm --detail --scan "$MD_DEVICE" >>"$MDADM_CONF" 2>/dev/null || true
}
crypttab_forget() { [ -w "$CRYPTTAB" ] && sed -i "/^$MD_CRYPT /d" "$CRYPTTAB"; return 0; }
md_undo() {
  local m
  if command -v cryptsetup >/dev/null 2>&1; then cryptsetup close "$MD_CRYPT" >/dev/null 2>&1 || true; fi
  crypttab_forget
  mdadm --stop "$MD_DEVICE" >/dev/null 2>&1 || true
  for m in "$@"; do mdadm --zero-superblock "$m" >/dev/null 2>&1 || true; wipefs -a "$m" >/dev/null 2>&1 || true; done
  rm -f "$KEY_DIR/$MD_NAME.key"
}
# md_build ID ENCRYPT(0|1) NAME...: build one RAID array on whole drives, format it and mount it at the Main pool path.
md_build() {
  local id=$1 enc=$2 level uuid i key="" target="$MD_DEVICE" luks="" opts="$BRANCH_OPTS" mnt="${ARRAY_MOUNT:-$MAIN_POOL}"; shift 2
  level=${id#md-raid}
  mkdir -p "$(dirname "$MD_DEVICE")" "$mnt"
  mdadm --create "$MD_DEVICE" --run --level="$level" --raid-devices="$#" --metadata=1.2 --name="$MD_NAME" "$@" 9>&- </dev/null >&2 || return 1
  udevadm settle 2>/dev/null || true
  for i in 1 2 3 4 5 6 7 8 9 10; do [ -b "$(readlink -f "$MD_DEVICE")" ] && break; sleep 1; done
  if [ "$enc" = 1 ]; then
    key=$(key_make "$MD_NAME" 64) || { md_undo "$@"; return 1; }
    cryptsetup luksFormat --batch-mode --type luks2 --key-file "$key" "$MD_DEVICE" 9>&- >&2 || { md_undo "$@"; return 1; }
    cryptsetup open --key-file "$key" "$MD_DEVICE" "$MD_CRYPT" 9>&- >&2 || { md_undo "$@"; return 1; }
    target="$MAPPER_DIR/$MD_CRYPT"
    luks=$(blkid -s UUID -o value "$MD_DEVICE") || true
    opts="defaults,noatime,nofail,x-systemd.device-timeout=60"
  fi
  if ! mkfs.ext4 -F -q -L "$MD_NAME" -m 0 "$target" >&2; then md_undo "$@"; return 1; fi
  udevadm settle 2>/dev/null || true
  uuid=$(blkid -s UUID -o value "$target") || true
  if [ -z "$uuid" ]; then md_undo "$@"; warn "Could not read the UUID of the new array."; return 1; fi
  if [ "$enc" = 1 ]; then
    [ -n "$luks" ] || { md_undo "$@"; warn "Could not read the UUID of the encrypted array."; return 1; }
    mkdir -p "$(dirname "$CRYPTTAB")"; touch "$CRYPTTAB"; crypttab_forget
    printf '%s UUID=%s %s luks,nofail\n' "$MD_CRYPT" "$luks" "$key" >>"$CRYPTTAB"
  fi
  fstab_snapshot
  fstab_add "UUID=$uuid  $mnt  ext4  $opts  0  2"
  sd_reload
  if ! mount_fstab "$mnt"; then fstab_rollback; md_undo "$@"; warn "Could not mount the new array at $mnt. fstab was restored."; return 1; fi
  md_conf_write
  if command -v update-initramfs >/dev/null 2>&1; then update-initramfs -u >/dev/null 2>&1 || warn "update-initramfs failed. Run it again later:  sudo update-initramfs -u"; fi
  return 0
}

preset_record_add() {
  local tmp; tmp=$(mktemp)
  awk -F'|' -v OFS='|' -v t="$1" 'NR == 1 {$3 = $3 " " t} {print}' "$PRESET_FILE" >"$tmp" && cat "$tmp" >"$PRESET_FILE"
  rm -f "$tmp"
}
array_can_spare() { case "$1" in zfs-mirror|zfs-raidz1|zfs-raidz2|zfs-raidz3|md-raid1|md-raid5|md-raid6|md-raid10) return 0 ;; *) return 1 ;; esac; }
array_can_cache() { case "$1" in zfs-*) return 0 ;; *) return 1 ;; esac; }
array_add_spare() {
  case "$(preset_kind "$(preset_current)")" in
    zfs) zpool add -f "$ZFS_POOL_NAME" spare "$1" 9>&- >&2 || return 1
         zpool set autoreplace=on "$ZFS_POOL_NAME" 9>&- >&2 || warn "Could not turn on automatic replacement. Run:  sudo zpool set autoreplace=on $ZFS_POOL_NAME" ;;
    md)  mdadm "$MD_DEVICE" --add "$1" 9>&- >&2 || return 1
         md_conf_write ;;
  esac
}
array_add_cache() { zpool add -f "$ZFS_POOL_NAME" cache "$1" 9>&- >&2; }

# Release when Main is a ZFS or RAID array: the array and everything on it is deleted.
array_release_flow() {
  local id d m
  local -a disks=()
  id=$(preset_current)
  mapfile -t disks < <(array_disks)
  say "The Main pool ($MAIN_POOL) is a $(preset_title "$id") array on these drives:"
  for d in ${disks[@]+"${disks[@]}"}; do say "  - $(disk_base_name "$d")  ($d)"; done
  [ ${#disks[@]} -gt 0 ] || say "  (the drives could not be found right now)"
  say ""
  say "Warning: releasing an array deletes the array and everything stored on it. This cannot be undone."
  say "The drives are emptied and can be used again, for a new ready-made setup or with  sudo drives connect."
  say "The Backup pool ($BACKUP_POOL) is not changed. Make sure it holds a recent copy of the files that must be kept."
  yn "Delete the array and all its files?" || { say "Cancelled. Nothing was changed."; return 1; }
  typed DESTROY "Type DESTROY in capital letters to confirm: " || { say "Cancelled. Nothing was changed."; return 1; }
  pre_change "Stop the containers that use the storage." \
             "Delete the array, and erase its ${#disks[@]} drives." \
             "Make $MAIN_POOL a plain folder on the boot drive, then start the containers." && return 0
  PRESET_TOUCHED=1
  stop_containers "$MAIN_POOL" "$DISKS_DIR"
  sync_fs "$MAIN_POOL"
  case "$(preset_kind "$id")" in
    zfs)
      zpool destroy -f "$ZFS_POOL_NAME" 9>&- || { start_containers; die "Could not delete the ZFS pool (is something using $MAIN_POOL?). Nothing was changed."; }
      for d in ${disks[@]+"${disks[@]}"}; do
        for m in $(parts_of "$d"); do zpool labelclear -f "$m" >/dev/null 2>&1 || true; done
      done
      rm -f "$ZFS_SCRUB_CRON"
      if array_encrypted; then
        if [ "$TEST_MODE" != 1 ]; then systemctl disable homelab-zfs-key.service >/dev/null 2>&1 || true; fi
        rm -f "$ZFS_KEY_UNIT" "$KEY_DIR/$ZFS_POOL_NAME.key"
        sd_reload
      fi ;;
    md)
      if mountpoint -q "$MAIN_POOL" && ! pool_umount "$MAIN_POOL"; then start_containers; die "Could not unmount $MAIN_POOL (something is using it). Nothing was changed."; fi
      fstab_snapshot
      fstab_remove_mp "$MAIN_POOL"
      if array_encrypted; then
        cryptsetup close "$MD_CRYPT" 9>&- >&2 || warn "The encrypted layer did not close cleanly."
        crypttab_forget
        rm -f "$KEY_DIR/$MD_NAME.key"
      fi
      sd_reload
      mdadm --stop "$MD_DEVICE" 9>&- >&2 || warn "The array did not stop cleanly."
      for m in $(array_members); do
        d=$(readlink -f "$m" 2>/dev/null); [ -b "$d" ] && mdadm --zero-superblock "$d" >/dev/null 2>&1 || true
      done
      md_conf_forget
      command -v update-initramfs >/dev/null 2>&1 && { update-initramfs -u >/dev/null 2>&1 || true; } ;;
  esac
  for d in ${disks[@]+"${disks[@]}"}; do wipefs -a "$d" >/dev/null 2>&1 || true; done
  rm -f "$PRESET_FILE"
  chattr -i "$MAIN_POOL" 2>/dev/null || true
  mkdir -p "$MAIN_POOL"
  array_service_folders
  start_containers
  log "released the $id array (${#disks[@]} drives erased)"
  say ""
  say "Done. The array was deleted and its drives are empty again."
  say "Choose the drives you want with:  sudo drives preset     or     sudo drives"
}

# `preset`: list the setups that can be built and what the empty drives plugged in now would give.
preset_list_flow() {
  local id d s sizes_text="" total=0 n=0 kind lastkind=""
  local -a bsizes=() disks=() use=()
  mapfile -t disks < <(blank_disks)
  for d in "${disks[@]}"; do s=$(disk_size_bytes "$d"); [ -n "$s" ] || continue; bsizes+=("$s"); total=$((total + s)); n=$((n + 1)); done
  say ""
  say "Ready-made setups. Each one is built on empty drives, which are formatted."
  if [ "$n" -eq 0 ]; then
    say "Empty drives connected: none. (A drive with files can be used only through  sudo drives wizard,  which asks whether to keep or erase its files.)"
  else
    for s in "${bsizes[@]}"; do sizes_text="$sizes_text, $(pretty_size "$s")"; done
    say "Empty drives connected: $n (${sizes_text#, })"
  fi
  say ""
  for id in $PRESET_IDS; do
    kind=$(preset_kind "$id")
    if [ "$kind" != "$lastkind" ]; then
      lastkind=$kind
      case "$kind" in
        pool) say "== Pools of separate drives (each drive keeps its own files; easy to expand later) ==" ;;
        zfs)  say "== ZFS, a RAID file system (needs the program:  sudo apt install -y zfsutils-linux) ==" ;;
        md)   say "== Linux RAID with mdadm (needs the program:  sudo apt install -y mdadm) ==" ;;
      esac
      say ""
    fi
    printf '  %-10s %s   needs %s drives\n' "$id" "$(preset_title "$id")" "$(preset_drives_text "$id")"
    printf '             %s\n' "$(preset_blurb "$id")"
    if [ "$n" -lt "$(preset_min "$id")" ]; then
      printf '             With your drives: need %s more empty drive(s)\n' "$(( $(preset_min "$id") - n ))"
    else
      use=("${bsizes[@]}")
      if [ "$id" = mirror ]; then mapfile -t use < <(printf '%s\n' "${bsizes[@]}" | sort -rn | head -2); fi
      printf '             With your drives: %s usable (of %s in the %d drives used)\n' "$(pretty_size "$(preset_capacity "$id" "${use[@]}")")" \
        "$(pretty_size "$(printf '%s\n' "${use[@]}" | awk '{t += $1} END {print t}')")" "${#use[@]}"
    fi
    say ""
  done
  say "Build one with:  sudo drives preset NAME      (for example  sudo drives preset snapraid1  or  sudo drives preset raidz1;  add --dry-run to show the plan first)"
  say "A ZFS or RAID setup becomes the Main pool. If Main already has drives, its files are copied into the new setup first, and the old Main drives are released afterwards. Their files are not erased."
  if [ -n "$(preset_current)" ]; then say "Built on this machine: $(preset_title "$(preset_current)")"; fi
}

# preset_pick_drives ID: print the chosen devices, one per line. Only empty drives are offered.
preset_pick_drives() {
  local id=$1 min max d n=0 left
  local -a pool=() chosen=()
  mapfile -t pool < <({ blank_disks; printf '%s\n' "$WIZARD_DEVS"; } | grep . | sort -u)
  min=$(preset_min "$id"); max=$(preset_max "$id")
  if [ ${#pool[@]} -lt "$min" ]; then
    note "$(preset_title "$id") needs $(preset_drives_text "$id") empty drives; ${#pool[@]} found."
    note "This list contains only empty or new drives. A drive with files can be added with  sudo drives wizard  (keep or erase its files) or erased first with  sudo drives wipe"
    return 1
  fi
  if [ -n "$WIZARD_DEVS" ]; then
    mapfile -t chosen < <(printf '%s\n' "$WIZARD_DEVS" | grep .)
    if [ ${#chosen[@]} -ge "$min" ] && { [ "$max" -le 0 ] || [ ${#chosen[@]} -le "$max" ]; }; then
      note "Using the ${#chosen[@]} drives chosen in the scan:"
      for d in "${chosen[@]}"; do note "  $(disk_summary "$d")"; done
      printf '%s\n' "${chosen[@]}"; return 0
    fi
    chosen=()
  fi
  note "Empty drives that can be used (the boot drive and your pool drives are never listed):"
  while :; do
    d=$(pick_disk_list "Which drive do you want to use? " "${pool[@]}") || return 1
    chosen+=("$d"); n=$((n + 1))
    mapfile -t pool < <(printf '%s\n' "${pool[@]}" | grep -vx "$d" | grep .)
    [ "$max" -gt 0 ] && [ "$n" -ge "$max" ] && break
    [ ${#pool[@]} -eq 0 ] && break
    if [ "$n" -ge "$min" ]; then
      yn "Use another drive?" || break
    else
      left=$((min - n)); note "(this setup needs at least $min drives: $left more)"
    fi
  done
  printf '%s\n' "${chosen[@]}"
}

preset_parity_drive() {
  local dev=$1 n=$2 label part uuid mp base
  label="$PARITY_PREFIX$n"; mp="$DISKS_DIR/$label"
  refuse_unsafe_disk "$dev"
  base=$(disk_base_name "$dev")
  part=$(format_disk "$dev" "$label") || return 1
  uuid=$(blkid -s UUID -o value "$part") || true
  [ -n "$uuid" ] || die "Could not read the UUID of $part"
  name_store_put "$label" "$base"
  fstab_snapshot
  ensure_mp "$mp"
  fstab_add "UUID=$uuid  $mp  ext4  $BRANCH_OPTS  0  2"
  sd_reload
  if ! mount_fstab "$mp"; then fstab_rollback; die "Could not mount $part at $mp. fstab was restored."; fi
  power_apply "$mp" backup
  say "Done. $base is now a parity drive ($mp)."
  log "preset: $label ($part, $base) is a SnapRAID parity drive"
}

extra_wanted() {
  [ "$1" = 1 ] && return 0
  [ "$ASSUME_YES" = 1 ] && return 1
  yn "$2"
}
rest_drives() {
  local d
  for d in $(blank_disks); do
    case " $* " in *" $d "*) ;; *) echo "$d" ;; esac
  done
}

# preset_flow ID: build a ready-made setup (single, mirror, RAID, ZFS or SnapRAID) on empty drives.
preset_flow() {
  local id d i n=0 usable total=0 mp label par s hint smallest biggest enc=0 spare_dev="" cache_dev="" key_path="" bk_dev="" used_b kept_n=0 force migrate=0 main_used=0 main_need=0
  local -a devs=() sizes=() order=() main_devs=() par_devs=() ids=() rest=() erase_list=()
  id=$(preset_alias "${1:-}")
  if ! preset_known "$id"; then
    note "There is no setup called '${1:-}'. The setups are: $PRESET_IDS"
    note "See what each one needs and gives:  sudo drives preset"
    return 1
  fi
  if [ -n "$WIZARD_KEEP" ]; then
    case "$id" in
      pool|mirror|snapraid1|snapraid2) ;;
      *) note "$(preset_title "$id") erases every drive, so it cannot keep the files you chose to keep. Choose the plain pool, the mirror or SnapRAID, or erase that drive first."; return 1 ;;
    esac
  fi
  if preset_is_array "$id"; then need_cmds wipefs blkid mkfs.ext4 || return 1; else need_tools || return 1; fi
  hint=$(preset_tool_hint "$id")
  if [ -n "$hint" ]; then note "$(preset_title "$id") needs a program that is not installed yet. Install it with:  $hint"; return 1; fi
  if array_active; then
    note "The Main pool is already a $(preset_title "$(preset_current)") array."
    note "To start over, take it apart first:  sudo drives release   (this DELETES the array and its files)."
    return 1
  fi
  if preset_is_array "$id" && [ -n "$(branches_of main)" ] && [ -z "$(parity_mounts)" ]; then
    migrate=1
    if ! main_is_pool; then
      note "The Main pool is not mounted, so its files cannot be copied into a new setup. Mount it first:  sudo drives remount"
      return 1
    fi
    need_cmds rsync || return 1
    if mountpoint -q "$MIGRATE_DIR" || [ -n "$(find "$MIGRATE_DIR" -mindepth 1 -print -quit 2>/dev/null)" ]; then
      note "The folder $MIGRATE_DIR (where the new setup is built) is not empty. Check its contents, move it elsewhere, then try again."
      return 1
    fi
  elif [ -n "$(branches_of main)" ] || { [ "$id" = mirror ] && [ -n "$(branches_of backup)" ]; } || [ -n "$(parity_mounts)" ]; then
    note "A ready-made setup creates a new setup, but some drives are already in a storage."
    note "View them with  sudo drives list.  To add another drive to the existing storage, use  sudo drives connect."
    note "To start over with every drive, remove them from the pools first with  sudo drives release  (the files stay on the drives)."
    return 1
  fi
  if preset_is_array "$id"; then
    if [ "$migrate" != 1 ] && mountpoint -q "$MAIN_POOL"; then
      note "$MAIN_POOL is already used by something else (check: findmnt $MAIN_POOL). A RAID setup needs it to be an ordinary empty folder."
      return 1
    fi
    if [ "$migrate" != 1 ] && boot_has_files "$MAIN_POOL"; then
      note "The folder $MAIN_POOL (on the boot drive) contains files. The new storage would hide them."
      note "Move them elsewhere first, then try again."
      return 1
    fi
    if [ "$(preset_kind "$id")" = zfs ] && zpool list -H -o name 2>/dev/null | grep -qx "$ZFS_POOL_NAME"; then
      note "A ZFS pool called '$ZFS_POOL_NAME' already exists on this computer. Look at it with:  zpool status $ZFS_POOL_NAME"
      return 1
    fi
  else
    pool_can_grow main "these drives" || return 1
    [ "$id" = mirror ] && { pool_can_grow backup "these drives" || return 1; }
  fi

  mapfile -t devs < <(preset_pick_drives "$id") || return 1
  [ ${#devs[@]} -gt 0 ] || return 1
  for d in "${devs[@]}"; do
    refuse_unsafe_disk "$d"
    if in_list "$d" "$WIZARD_KEEP"; then keepable_disk "$d" || die "$d does not have one ext4 partition, so its files cannot be kept."
    elif in_list "$d" "$WIZARD_ERASE"; then :
    else disk_is_blank "$d" || die "$d is not empty. Refusing."; fi
    sizes+=("$(disk_size_bytes "$d")")
  done
  mapfile -t order < <(for i in "${!devs[@]}"; do printf '%s %s\n' "${sizes[$i]}" "${devs[$i]}"; done | sort -rn -s -k1,1 | awk '{print $2}')
  case "$id" in
    pool|zfs-*|md-*) main_devs=("${devs[@]}") ;;
    mirror)
      par_devs=(); bk_dev=${order[0]}
      if [ -n "$WIZARD_KEEP" ]; then
        for d in "${devs[@]}"; do if in_list "$d" "$WIZARD_KEEP"; then main_devs+=("$d"); else bk_dev=$d; fi; done
        [ ${#main_devs[@]} -eq 1 ] || { note "A mirror can keep the files of only one drive. The other drive becomes the copy."; return 1; }
      else
        main_devs=("${order[1]}")
      fi ;;
    snapraid1|snapraid2)
      par=$(preset_parity_count "$id")
      if [ -n "$WIZARD_KEEP" ]; then
        local -a cand=()
        for d in "${order[@]}"; do in_list "$d" "$WIZARD_KEEP" || cand+=("$d"); done
        if [ ${#cand[@]} -lt "$par" ]; then
          note "$(preset_title "$id") needs $par drive(s) for parity data, and those are erased. Every chosen drive keeps its files, so none is left for that."
          note "Nothing was changed. Choose a drive to erase for parity, or remove one from the keep list."
          return 1
        fi
        par_devs=("${cand[@]:0:par}")
        for d in "${devs[@]}"; do in_list "$d" "$(printf '%s\n' "${par_devs[@]}")" || main_devs+=("$d"); done
        biggest=0
        for d in "${main_devs[@]}"; do s=$(disk_size_bytes "$d"); [ "$s" -gt "$biggest" ] && biggest=$s; done
        for d in "${par_devs[@]}"; do
          if [ "$(disk_size_bytes "$d")" -lt "$biggest" ]; then
            note "The parity drive $d ($(pretty_size "$(disk_size_bytes "$d")")) is smaller than the biggest data drive ($(pretty_size "$biggest")). SnapRAID requires it to be at least as large."
            note "Nothing was changed. Use a larger drive for parity, or leave the largest drive out."
            return 1
          fi
        done
      else
        par_devs=("${order[@]:0:par}"); main_devs=("${order[@]:par}")
      fi ;;
  esac
  usable=$(preset_capacity "$id" "${sizes[@]}")
  if [ -n "$WIZARD_KEEP" ]; then case "$id" in snapraid1|snapraid2)
    usable=0; for d in "${main_devs[@]}"; do usable=$((usable + $(disk_size_bytes "$d"))); done ;; esac; fi
  for s in "${sizes[@]}"; do total=$((total + s)); done
  if [ "$migrate" = 1 ]; then
    main_used=$(pool_used_bytes); main_need=$(migrate_need_bytes "$main_used")
    if [ "$usable" -lt "$main_need" ]; then
      note "The new setup is too small. $(preset_title "$id") on these drives holds about $(pretty_size "$usable"), but the Main pool has $(pretty_size "$main_used") of files (about $(pretty_size "$main_need") are needed for the copy)."
      note "Nothing was changed. Choose more or larger drives, or a setup that provides more space."
      return 1
    fi
  fi

  if preset_is_array "$id"; then
    mapfile -t rest < <(rest_drives "${devs[@]}")
    if [ "$WANT_SPARE" = 1 ] && ! array_can_spare "$id"; then note "$(preset_title "$id") has no redundancy for a spare to take over, so a hot spare would have no effect. Leave out --spare."; return 1; fi
    if [ "$WANT_CACHE" = 1 ] && ! array_can_cache "$id"; then note "An SSD read cache is for the ZFS setups only. Leave out --cache."; return 1; fi
    if array_can_spare "$id" && { [ "$WANT_SPARE" = 1 ] || [ ${#rest[@]} -gt 0 ]; }; then
      if [ ${#rest[@]} -eq 0 ]; then note "No empty drive is left for a hot spare."; return 1; fi
      if extra_wanted "$WANT_SPARE" "Add a hot spare? (one more empty drive that takes over automatically when a drive fails)"; then
        spare_dev=$(pick_disk_list "Which drive is the hot spare? " "${rest[@]}") || return 1
        mapfile -t rest < <(rest_drives "${devs[@]}" "$spare_dev")
      fi
    fi
    if array_can_cache "$id" && { [ "$WANT_CACHE" = 1 ] || [ ${#rest[@]} -gt 0 ]; }; then
      if [ ${#rest[@]} -eq 0 ]; then note "No empty drive is left for the SSD read cache."; return 1; fi
      if extra_wanted "$WANT_CACHE" "Add an SSD as a read cache? (speeds up reading; if the SSD fails, no data is lost)"; then
        cache_dev=$(pick_disk_list "Which drive is the SSD read cache? " "${rest[@]}") || return 1
        if [ "$(drive_kind "$cache_dev" "$(lsblk -dno MODEL "$cache_dev" 2>/dev/null)")" != SSD ]; then
          note "$cache_dev does not say it is an SSD. A cache on a spinning drive does not make anything faster."
          yn "Use it as the read cache anyway?" || return 1
        fi
      fi
    fi
    if extra_wanted "$WANT_ENCRYPT" "Encrypt the drives? (a stolen drive cannot be read; the key file stays on the boot drive)"; then
      enc=1
      if [ "$(preset_kind "$id")" = md ] && ! command -v cryptsetup >/dev/null 2>&1; then
        note "Encrypting a RAID setup needs a program that is not installed. Install it with:  sudo apt install -y cryptsetup"
        return 1
      fi
      key_path="$KEY_DIR/$([ "$(preset_kind "$id")" = zfs ] && echo "$ZFS_POOL_NAME" || echo "$MD_NAME").key"
      if [ -e "$key_path" ]; then note "The key file $key_path already exists (possibly from an older array). Move it elsewhere first."; return 1; fi
    fi
  fi
  erase_list=()
  for d in "${devs[@]}"; do in_list "$d" "$WIZARD_KEEP" && kept_n=$((kept_n + 1)) || erase_list+=("$d"); done
  [ -z "$spare_dev" ] || erase_list+=("$spare_dev")
  [ -z "$cache_dev" ] || erase_list+=("$cache_dev")
  [ -z "$spare_dev" ] || refuse_unsafe_disk "$spare_dev"
  [ -z "$cache_dev" ] || refuse_unsafe_disk "$cache_dev"

  say ""
  say "Setup: $(preset_title "$id")"
  say "$(preset_blurb "$id")"
  say ""
  printf '  %-28s %-12s %-9s %s\n' DRIVE DEVICE SIZE "WILL BE"
  i=0
  for d in "${main_devs[@]}"; do
    i=$((i + 1))
    printf '  %-28s %-12s %-9s %s\n' "$(disk_base_name "$d")" "$d" "$(pretty_size "$(disk_size_bytes "$d")")" \
      "$(if preset_is_array "$id"; then echo "Main pool, array member $i"; else echo "Main pool, drive $i"; fi)$(in_list "$d" "$WIZARD_KEEP" && echo "  [its files are KEPT]")"
  done
  if [ "$id" = mirror ]; then
    printf '  %-28s %-12s %-9s %s\n' "$(disk_base_name "$bk_dev")" "$bk_dev" "$(pretty_size "$(disk_size_bytes "$bk_dev")")" "Backup pool (the nightly copy)$(in_list "$bk_dev" "$WIZARD_ERASE" && echo "  [ERASED: it has files]")"
    if [ -n "$WIZARD_KEEP" ]; then
      used_b=$(disk_used_bytes "${main_devs[0]}")
      if [ -n "$used_b" ] && [ "$(disk_size_bytes "$bk_dev")" -lt "$used_b" ]; then
        note "The Backup drive ($(pretty_size "$(disk_size_bytes "$bk_dev")")) is smaller than the files on the Main drive ($(pretty_size "$used_b")), so the nightly copy would not fit."
        note "Nothing was changed. Choose the plain pool, or a larger drive for the copy."
        return 1
      fi
    fi
  fi
  i=0
  for d in ${par_devs[@]+"${par_devs[@]}"}; do i=$((i + 1)); printf '  %-28s %-12s %-9s %s\n' "$(disk_base_name "$d")" "$d" "$(pretty_size "$(disk_size_bytes "$d")")" "SnapRAID parity drive $i"; done
  [ -z "$spare_dev" ] || printf '  %-28s %-12s %-9s %s\n' "$(disk_base_name "$spare_dev")" "$spare_dev" "$(pretty_size "$(disk_size_bytes "$spare_dev")")" "Hot spare (waits and takes over automatically)"
  [ -z "$cache_dev" ] || printf '  %-28s %-12s %-9s %s\n' "$(disk_base_name "$cache_dev")" "$cache_dev" "$(pretty_size "$(disk_size_bytes "$cache_dev")")" "SSD read cache"
  say ""
  say "Usable space: $(pretty_size "$usable") of the $(pretty_size "$total") on the ${#devs[@]} drives of the setup."
  if [ "$migrate" = 1 ]; then
    say "Size check: the Main pool has $(pretty_size "$main_used") of files and the new setup holds $(pretty_size "$usable"). Everything fits."
    say "The Main pool is not erased. Its files are copied into the new setup first, and the new setup takes over only after the copy is checked."
    say "Then the old Main drives are released. Their files stay on them and they appear as spare drives."
    say "The containers that use the Main pool are stopped while the files are copied. This can take hours for large amounts of data."
    for mp in $(branches_of main); do say "  - old Main drive: $(branch_name "$mp")  (released afterwards, not erased)"; done
  fi
  if [ "$enc" = 1 ]; then
    say "Encrypted. The key file is $key_path (on the boot drive; the server unlocks the array automatically at boot)."
    say "Copy the key file to a safe place (for example a USB stick) after the build. If the boot drive fails and there is no copy, the files are permanently lost."
  fi
  case "$id" in
    mirror) say "The Backup drive receives a copy of the Main drive every day (the schedule is shown by  sudo homelab status). A file added today is on the Backup drive tomorrow." ;;
    snapraid*) say "Parity data is updated every night at 04:00, not immediately. Files added today are protected from tonight." ;;
    zfs-*|md-*)
      say "The array becomes the Main pool ($MAIN_POOL). The containers keep using the same path. The Backup pool is unchanged."
      smallest=$(printf '%s\n' "${sizes[@]}" | sort -n | head -1); biggest=$(printf '%s\n' "${sizes[@]}" | sort -n | tail -1)
      case "$id" in
        zfs-stripe|md-raid0) say "Warning: there is no redundancy. If any one drive fails, all files are lost. Keep a good backup (the Backup pool does this every night)." ;;
        *) [ $((biggest - smallest)) -gt $((smallest / 10)) ] && say "Note: the drives are not the same size. A RAID setup uses only as much of each drive as the smallest one provides ($(pretty_size "$smallest")), so part of the larger drives stays unused." ;;
      esac
      case "$id" in
        md-*) say "The array builds its redundancy in the background. This takes hours on large drives (see  cat /proc/mdstat). The array can be used immediately, but it is not fully protected until this finishes." ;;
        zfs-*) say "ZFS also checks all data for silent damage once a month and repairs what it can." ;;
      esac ;;
  esac
  say ""
  if [ ${#erase_list[@]} -gt 0 ]; then
    say "Warning: data will be erased"
    if [ ${#erase_list[@]} -eq 1 ]; then say "Everything on this drive will be permanently deleted:"; else say "Everything on these ${#erase_list[@]} drives will be permanently deleted:"; fi
    for d in "${erase_list[@]}"; do say "  - $d  ($(disk_base_name "$d"))$(in_list "$d" "$WIZARD_ERASE" && echo "   <- it has files: $(disk_files_text "$d")")"; done
  fi
  if [ "$kept_n" -gt 0 ]; then
    if [ "$kept_n" -eq 1 ]; then say "The files on this drive are kept as they are. Nothing on it is deleted:"; else say "The files on these $kept_n drives are kept as they are. Nothing on them is deleted:"; fi
    for d in "${devs[@]}"; do in_list "$d" "$WIZARD_KEEP" && say "  - $d  ($(disk_base_name "$d"))   $(disk_files_text "$d")"; done
  fi
  typed_enter "$id" "Press Enter to continue with this setup, or type another setup name" || { say "Cancelled. Nothing was changed."; return 1; }
  [ ${#erase_list[@]} -eq 0 ] || typed "ERASE" "Type ERASE in capital letters to confirm: " || { say "Cancelled. Nothing was changed."; return 1; }
  if preset_is_array "$id"; then
    pre_change "Erase the ${#erase_list[@]} drives and build the $(preset_title "$id") array on them." \
               "$([ "$migrate" = 1 ] && echo "Stop the containers that use the Main pool while its files are copied into the new array, check the copy, then let the array take over $MAIN_POOL and release the old Main drives (their files stay)." || echo "Stop the containers that use the Main pool for a minute.")" \
               "$([ "$(preset_kind "$id")" = zfs ] && echo "Create the ZFS pool '$ZFS_POOL_NAME'$([ "$enc" = 1 ] && echo ", encrypted with a new key file,") and mount it at $MAIN_POOL." || echo "Create the RAID array$([ "$enc" = 1 ] && echo ", encrypt it with a new key file,"), format it and mount it at $MAIN_POOL (and write it into fstab and mdadm.conf).")" \
               "$([ -n "$spare_dev$cache_dev" ] && echo "Add the $([ -n "$spare_dev" ] && echo "hot spare")$([ -n "$spare_dev" ] && [ -n "$cache_dev" ] && echo " and the ")$([ -n "$cache_dev" ] && echo "read cache").")" \
               "Start the containers again." && return 0
    PRESET_TOUCHED=1
    PROG_ALL=(); for d in "${devs[@]}"; do PROG_ALL+=("$(basename "$d")"); done
    progress 3 "Getting ready"
    for d in "${devs[@]}"; do refuse_unsafe_disk "$d"; ids+=("$(disk_stable_name "$d")"); done
    stop_containers "$MAIN_POOL"
    progress 8 "Building the new setup"
    [ "$migrate" != 1 ] || ARRAY_MOUNT=$MIGRATE_DIR
    if [ "$(preset_kind "$id")" = zfs ]; then
      zfs_build "$id" "$enc" "${ids[@]}" || { ARRAY_MOUNT=""; start_containers; warn "The ZFS pool could not be created. Look at the messages above.$(hint " See: sudo drives status" "")"; return 1; }
    else
      md_build "$id" "$enc" "${ids[@]}" || { ARRAY_MOUNT=""; start_containers; warn "The RAID array could not be built. Look at the messages above.$(hint " See: sudo drives status" "")"; return 1; }
    fi
    ARRAY_MOUNT=""
    progress 18 "New setup is ready"
    if [ "$migrate" = 1 ]; then
      local mig_ok=0
      MIGRATE_STOPPED=0
      if abort_requested; then MIGRATE_STOPPED=1
      elif migrate_copy; then progress 95 "Switching over"; migrate_switch "$id" && mig_ok=1
      fi
      if [ "$mig_ok" != 1 ]; then
        migrate_discard "$id" "${ids[@]}"
        PROG_ALL=()
        start_containers
        if [ "$MIGRATE_STOPPED" = 1 ]; then
          ABORTED=1
          say "Stopped. Nothing was changed: the Main pool is as it was and its files are untouched. The new setup was removed again and its drives are empty."
          return 4
        fi
        warn "The move to the new setup did not finish. The Main pool is as it was and its files are untouched. The new setup was removed again and its drives are empty."
        return 1
      fi
    fi
    PROG_ALL=()
    preset_record "$id" "${ids[*]}$([ "$enc" = 1 ] && echo " encrypted")"
    if [ -n "$spare_dev" ]; then
      d=$(disk_stable_name "$spare_dev")
      if array_add_spare "$d"; then preset_record_add "spare=$d"; say "Hot spare added: $(disk_base_name "$spare_dev")."
      else warn "The hot spare could not be added. The array works without it. Add it later with:  sudo drives spare"; fi
    fi
    if [ -n "$cache_dev" ]; then
      d=$(disk_stable_name "$cache_dev")
      if array_add_cache "$d"; then preset_record_add "cache=$d"; say "Read cache added: $(disk_base_name "$cache_dev")."
      else warn "The read cache could not be added. The array works without it. Add it later with:  sudo drives cache"; fi
    fi
    array_service_folders
    start_containers
    log "preset $id built on ${#devs[@]} drives: ${ids[*]}"
    say ""
    say "Done. $(preset_title "$id") is ready at $MAIN_POOL: about $(pretty_size "$usable") usable."
    [ "$migrate" != 1 ] || say "The files of the old Main pool were copied over. Its drives are now spare drives. Their files remain on them until they are used or erased."
    [ "$enc" != 1 ] || say "Important: copy the key file $key_path to a safe place now (for example a USB stick). Without it, the files cannot be read."
    case "$id" in
      md-*) say "Background build progress:  cat /proc/mdstat      Health:  sudo drives status" ;;
      zfs-*) say "Health:  sudo drives status      Details:  zpool status $ZFS_POOL_NAME" ;;
    esac
    return 0
  fi
  PRESET_TOUCHED=1
  pre_change "$([ "$kept_n" -gt 0 ] && echo "Format ${#erase_list[@]} drive(s) and keep the files on the other $kept_n." || echo "Format the ${#devs[@]} drives.")" \
             "Stop the containers that use the storage while each drive is added (once per drive), then start them again." \
             "Make the Main pool from the data drives$([ "$id" = mirror ] && echo ", and the Backup pool from the other drive")." \
             "$([ -n "${par_devs[*]:-}" ] && echo "Make the protection drives, write the SnapRAID settings and the 04:00 schedule." || echo "Write down what was built.")" && return 0

  for d in "${main_devs[@]}"; do
    force=1; in_list "$d" "$WIZARD_KEEP" && force=2
    connect_flow "$d" main "$force" 1 || { warn "Stopped at $d. The drives before it are already in the Main pool. The remaining drives were not changed. See: sudo drives list"; return 1; }
    n=$((n + 1))
  done
  if [ "$id" = mirror ]; then
    connect_flow "$bk_dev" backup 1 1 || { warn "Stopped at $bk_dev. The Main drive is ready. The Backup drive was not added. See: sudo drives list"; return 1; }
  fi
  i=0
  for d in ${par_devs[@]+"${par_devs[@]}"}; do
    i=$((i + 1))
    preset_parity_drive "$d" "$i" || { warn "Stopped at $d. See: sudo drives list"; return 1; }
  done
  label=""
  for mp in $(branches_of main) $(branches_of backup) $(parity_mounts); do label="$label $(basename "$mp")"; done
  preset_record "$id" "${label# }"
  if [ -n "${par_devs[*]:-}" ]; then
    snapraid_conf_write
    snapraid_cron_write
    say "Setting up SnapRAID (first parity run; nothing to protect yet)..."
    snapraid -c "$SNAPRAID_CONF" sync || warn "The first SnapRAID run did not finish. Run it again later with:  sudo drives snapraid sync"
  fi
  log "preset $id built on ${#devs[@]} drives: ${label# }"
  say ""
  say "Done. $(preset_title "$id") is ready: $(pretty_size "$usable") usable."
  case "$id" in
    snapraid*) say "Check status:  sudo drives snapraid status      Update parity now:  sudo drives snapraid sync" ;;
    mirror) say "To run the copy now:  sudo homelab-backup" ;;
  esac
  return 0
}

# extra_drive_flow spare|cache: add one more empty drive to the existing ZFS or RAID array.
extra_drive_flow() {
  local what=$1 id dev name hint
  local -a rest=()
  id=$(preset_current)
  if ! array_active; then
    note "There is no ZFS or RAID array to add a $what to. Build one first with  sudo drives preset"
    return 1
  fi
  if [ "$what" = spare ] && ! array_can_spare "$id"; then note "$(preset_title "$id") has no redundancy for a spare to take over, so a hot spare would have no effect."; return 1; fi
  if [ "$what" = cache ] && ! array_can_cache "$id"; then note "An SSD read cache is for ZFS arrays only."; return 1; fi
  hint=$(preset_tool_hint "$id")
  if [ -n "$hint" ]; then note "The program of the array is not installed:  $hint"; return 1; fi
  mapfile -t rest < <(blank_disks)
  if [ ${#rest[@]} -eq 0 ]; then note "No empty drive is connected. (A drive with files must be erased first with  sudo drives wipe.)"; return 1; fi
  dev=$(pick_disk_list "Which drive do you want to use as the $([ "$what" = spare ] && echo "hot spare" || echo "SSD read cache")? " "${rest[@]}") || return 1
  refuse_unsafe_disk "$dev"
  disk_is_blank "$dev" || die "$dev is not empty. Refusing."
  if [ "$what" = cache ] && [ "$(drive_kind "$dev" "$(lsblk -dno MODEL "$dev" 2>/dev/null)")" != SSD ]; then
    note "$dev does not say it is an SSD. A cache on a spinning drive does not make anything faster."
    yn "Use it as the read cache anyway?" || return 1
  fi
  say ""
  say "Warning: data will be erased"
  say "Everything on this drive will be permanently deleted:"
  say "  - $dev  ($(disk_base_name "$dev"))"
  typed "ERASE" "Type ERASE in capital letters to confirm: " || { say "Cancelled. Nothing was changed."; return 1; }
  pre_change "Erase $dev." "Add it to the $(preset_title "$id") array as the $([ "$what" = spare ] && echo "hot spare" || echo "read cache")." && return 0
  PRESET_TOUCHED=1
  name=$(disk_stable_name "$dev")
  if [ "$what" = spare ]; then array_add_spare "$name" || die "The hot spare could not be added. See the messages above."
  else array_add_cache "$name" || die "The read cache could not be added. See the messages above."; fi
  preset_record_add "$what=$name"
  log "array: $what added ($dev)"
  say ""
  say "Done. $(disk_base_name "$dev") is the $([ "$what" = spare ] && echo "hot spare of" || echo "SSD read cache of") the array."
}
spare_flow() { extra_drive_flow spare; }
cache_flow() { extra_drive_flow cache; }

preset_menu() {
  local id choice
  local -a ids=() items=()
  preset_list_flow
  for id in $PRESET_IDS; do ids+=("$id"); items+=("$(preset_title "$id")  ($id)"); done
  choice=$(choose "Which setup do you want to build? " "${items[@]}") || return 1
  preset_flow "${ids[$choice]}"
}

