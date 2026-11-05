# ---------- status ----------
last_backup_line() {
  if [ -f "$BACKUP_STATUS_FILE" ]; then
    awk -F'|' '{printf "%s  result: %s  destination: %s  took: %ss\n", $1, $2, $3, $4}' "$BACKUP_STATUS_FILE"
  else
    echo "no backup has run yet"
  fi
}

status_flow() {
  local role mp pool fst p
  say ""
  say "=== Pools ==="
  for role in main backup; do
    pool=$(role_pool "$role")
    if mountpoint -q "$pool"; then
      fst=$(findmnt -no FSTYPE "$pool")
      printf '%-8s %-14s mounted (%s)  %s used of %s\n' "$role" "$pool" "$fst" \
        "$(human "$(used_bytes "$pool")")" "$(human "$(total_bytes "$pool")")"
    else
      printf '%-8s %-14s NOT MOUNTED\n' "$role" "$pool"
    fi
  done
  for role in main backup; do
    if [ -n "$(branches_of "$role")" ] && ! pool_has_limits "$(role_pool "$role")"; then
      say "Note: the $role pool uses an older setting. Run  sudo drives fillorder  (menu: Settings and upgrades) to update it: it then keeps ${POOL_FREE_PERCENT}% of each drive free."
    fi
  done
  if [ -z "$(branches_of main)" ] && mountpoint -q "$MAIN_POOL" && [ "$TEST_MODE" != 1 ] && ! array_active; then
    say "Note: main storage is still one plain drive. Run  sudo drives  and choose Settings and upgrades > Convert to turn it into a pool."
  fi
  for role in main backup; do
    [ -n "$(branches_of "$role")" ] || continue
    say "$([ "$role" = main ] && echo Main || echo Backup) storage: new files go to $(policy_text "$(pool_policy_now "$(role_pool "$role")")"). Drive order: $(order_text "$role")"
  done
  say ""
  say "=== Pool drives ==="
  printf '%-26s %-8s %-12s %-9s %-9s %-9s %s\n' DRIVE ROLE DEVICE SIZE USED SMART STATE
  for mp in $(all_branches); do
    p=$(branch_part "$mp")
    if is_boot_section "$mp"; then
      if mountpoint -q "$mp"; then
        printf '%-26s %-8s %-12s %-9s %-9s %-9s %s\n' "$(branch_name "$mp")" "$(branch_role "$mp")" "boot drive" \
          "$(human "$(total_bytes "$mp")")" "$(human "$(used_bytes "$mp")")" "-" "connected (used last)"
      else
        printf '%-26s %-8s %-12s %-9s %-9s %-9s %s\n' "$(branch_name "$mp")" "$(branch_role "$mp")" "boot drive" "-" "-" "-" "NOT MOUNTED (try: sudo drives remount)"
      fi
    elif [ -n "$p" ] && mountpoint -q "$mp"; then
      printf '%-26s %-8s %-12s %-9s %-9s %-9s %s\n' "$(branch_name "$mp")" "$(branch_role "$mp")" "$p" \
        "$(human "$(total_bytes "$mp")")" "$(human "$(used_bytes "$mp")")" \
        "$(smart_health "$(disk_of_part "$p")")" "connected"
    else
      printf '%-26s %-8s %-12s %-9s %-9s %-9s %s\n' "$(branch_name "$mp")" "$(branch_role "$mp")" "-" "-" "-" "-" "MISSING (cable? then: sudo drives remount. Dead? sudo drives replace)"
    fi
  done
  for mp in $(parity_mounts); do
    p=$(branch_part "$mp")
    if [ -n "$p" ] && mountpoint -q "$mp"; then
      printf '%-26s %-8s %-12s %-9s %-9s %-9s %s\n' "$(branch_base_name "$mp")" "parity" "$p" \
        "$(human "$(total_bytes "$mp")")" "$(human "$(used_bytes "$mp")")" "$(smart_health "$(disk_of_part "$p")")" "connected (SnapRAID protection)"
    else
      printf '%-26s %-8s %-12s %-9s %-9s %-9s %s\n' "$(branch_base_name "$mp")" "parity" "-" "-" "-" "-" "MISSING (cable? then: sudo drives remount)"
    fi
  done
  if array_active; then
    local ad akind apath
    while read -r ad akind apath; do
      if [ "$ad" != "-" ]; then
        printf '%-26s %-8s %-12s %-9s %-9s %-9s %s\n' "$(disk_base_name "$ad")" "array" "$ad" "$(pretty_size "$(disk_size_bytes "$ad")")" "-" "$(smart_health "$ad")" "$(array_kind_text "$akind")"
      else
        printf '%-26s %-8s %-12s %-9s %-9s %-9s %s\n' "$(basename "$apath")" "array" "-" "-" "-" "-" "MISSING (cable? or dead: see  zpool status / mdadm --detail)"
      fi
    done < <(array_disk_kinds)
  fi
  [ -n "$(all_branches)" ] || array_active || say "(no drives in a pool yet)"
  [ -z "$(preset_current)" ] || say "Setup built with  sudo drives preset:  $(preset_title "$(preset_current)")"
  ! array_active || say "Array health: $(array_health_text)"
  if array_active && array_encrypted; then say "Encrypted: yes. The server unlocks it by itself at boot with the key file in $KEY_DIR (keep a copy of that file somewhere else)."; fi
  say ""
  say "=== Boot drive ==="
  say "Free now: $(pretty_size "$(boot_free_bytes)"). The boot drive always keeps at least $(pretty_size "$BOOT_KEEP_FREE_BYTES") free for the system and your other services; a boot drive section cannot take that away."
  local bs
  for bs in $(boot_section_of main) $(boot_section_of backup); do
    say "Section in the $(branch_role "$bs") storage: $(branch_name "$bs")"
  done
  say "Add one with  sudo drives bootsection  (menu: Add or remove drives). It is the last place the pool puts files."
  local tw; tw=$(timeshift_warn_text)
  [ -z "$tw" ] || say "!! $tw"
  say ""
  say "=== Other drives ==="
  local prot legacy managed d
  prot=$(protected_disks); legacy=$(legacy_disks); managed=$(managed_disks)
  for d in $(all_disks | sort -u); do
    if grep -qx "$d" <<<"$prot"; then
      say "$(disk_summary "$d")   boot/system drive (never touched)"
    elif grep -qx "$d" <<<"$managed"; then
      :
    elif grep -qx "$d" <<<"$legacy"; then
      say "$(disk_summary "$d")   current data drive (plain, not in a pool yet)"
    else
      say "$(disk_summary "$d")   not connected to a pool"
    fi
  done
  say ""
  say "=== Last backup ==="
  say "$(last_backup_line)"
  say ""
}

