pool_has_limits() {
  fstab_active | awk -v m="$1" '$2 == m && /=RW,[0-9]+K/ {f = 1} END {exit !f}'
}

pool_policy_now() {
  fstab_active | awk -v m="$1" '$2 == m { if (match($0, /category\.create=[a-z]+/)) print substr($0, RSTART + 16, RLENGTH - 16); exit }'
}

policy_text() {
  case "$1" in
    ff)  printf '%s' "one drive at a time (a new file goes to the first drive that has room)" ;;
    mfs) printf '%s' "spread (a new file goes to the drive with the most free space)" ;;
    *)   printf '%s' "spread over the drives (older setting)" ;;
  esac
}

pool_live_apply() {
  local role=$1 pool
  pool=$(role_pool "$role")
  mountpoint -q "$pool" && command -v setfattr >/dev/null 2>&1 || return 1
  setfattr -n user.mergerfs.category.create -v "$(pool_policy "$role")" "$pool/.mergerfs" 2>/dev/null \
    && setfattr -n user.mergerfs.minfreespace -v "$POOL_MINFREE" "$pool/.mergerfs" 2>/dev/null \
    && setfattr -n user.mergerfs.branches -v "$(branches_string "$role")" "$pool/.mergerfs" 2>/dev/null
}

# pool_reconfigure main|backup: apply the saved policy, order or limits to the running pool and write them to fstab.
pool_reconfigure() {
  local role=$1 pool
  pool=$(role_pool "$role")
  fstab_snapshot
  if pool_live_apply "$role"; then
    fstab_set_pool "$role"; sd_reload
    say "It is in use; nothing had to stop."
    return 0
  fi
  if mountpoint -q "$pool" && yn "The $role pool cannot apply the change while it is running. Apply it now? Its containers stop briefly while the pool is mounted again."; then
    if ! ( busy_gate ); then settings_rollback; return 1; fi
    stop_containers "$pool"
    if apply_pool "$role"; then
      start_containers
      return 0
    fi
    fstab_rollback; mount_fstab "$pool" 2>/dev/null; start_containers
    warn "The $role pool did not mount with the new setting. fstab was restored."
    return 1
  fi
  fstab_set_pool "$role"; sd_reload
  say "The change is saved. It takes effect after the next restart, or after  sudo drives remount."
  return 0
}

pick_pool_role() {
  local min=${1:-1} role mp n
  local -a roles=() items=()
  for role in main backup; do
    n=0; for mp in $(branches_of "$role"); do is_boot_section "$mp" || n=$((n + 1)); done
    if [ "$min" -le 1 ]; then [ -n "$(branches_of "$role")" ] || continue; else [ "$n" -ge "$min" ] || continue; fi
    roles+=("$role")
    items+=("$([ "$role" = main ] && echo Main || echo Backup) storage ($(role_pool "$role"))")
  done
  if [ ${#roles[@]} -eq 0 ]; then
    if [ "$min" -le 1 ]; then note "No drives are connected to a pool yet."; else note "This needs a storage with at least $min drives (the boot drive section does not count). Nothing was changed."; fi
    return 1
  fi
  if [ ${#roles[@]} -eq 1 ]; then echo "${roles[0]}"; return 0; fi
  local idx; idx=$(choose "Which storage? " "${items[@]}") || return 1
  echo "${roles[$idx]}"
}

order_text() {
  local mp out="" n own=""
  if [ -z "${NAME_CACHE:-}" ]; then NAME_CACHE=$(mktemp -d 2>/dev/null) && own=1 || NAME_CACHE=""; fi
  for mp in $(branches_of "$1"); do n=$(branch_name "$mp"); out="${out:+$out, }$n"; done
  if [ -n "$own" ]; then rm -rf "$NAME_CACHE"; NAME_CACHE=""; fi
  printf '%s' "$out"
}

# `fillorder`: choose how a pool picks a drive for a new file and which drive is used first.
fillorder_flow() {
  array_guard || return 1
  local role pool now act idx mp first cur
  local -a real=() items=() mps=()
  role=$(pick_pool_role 1) || return 1
  pool=$(role_pool "$role")
  now=$(pool_policy_now "$pool")
  for mp in $(branches_of "$role"); do is_boot_section "$mp" || real+=("$mp"); done
  say ""
  say "$([ "$role" = main ] && echo Main || echo Backup) storage: new files go to $(policy_text "$now")."
  say "Order of the drives: $(order_text "$role")"
  pool_has_limits "$pool" || say "(This pool still has an older setting without a free-space limit per drive. Choosing the first or second option updates it.)"
  act=$(choose "What do you want to do? " \
        "Fill one drive at a time, the first drive first$([ "$now" = ff ] && pool_has_limits "$pool" && echo "   [now]")" \
        "Spread: put a new file on the drive with the most free space$([ "$now" = mfs ] && pool_has_limits "$pool" && echo "   [now]")" \
        "Choose which drive is used first") || return 1
  settings_snapshot
  case "$act" in
    0|1)
      local want=ff; [ "$act" = 1 ] && want=mfs
      if [ "$now" = "$want" ] && pool_has_limits "$pool"; then
        settings_discard; say "The $role pool already works like that. Nothing was changed."; return 0
      fi
      dry_gate "Save the setting '$(policy_text "$want")' for the $role pool." \
               "Apply it to the running pool if possible (nothing stops). Otherwise you are asked before the pool is mounted again." && { settings_discard; return 0; }
      if [ "$want" = ff ]; then setting_del policy "$role"; else setting_put policy "$role" mfs; fi
      pool_reconfigure "$role" || { settings_rollback; return 1; }
      settings_discard
      say ""; say "Done. The $role pool now puts a new file on $(policy_text "$want" | sed 's/^[^(]*(a new file goes to //; s/)$//')."
      log "pool $role policy $want"
      ;;
    2)
      if [ ${#real[@]} -lt 2 ]; then settings_discard; note "The $role pool has only one drive, so there is no order to change. Nothing was changed."; return 1; fi
      for mp in "${real[@]}"; do
        mps+=("$mp")
        items+=("$(branch_name "$mp")   [position $(( ${#mps[@]} ))]")
      done
      idx=$(choose "Which drive should be used first? " "${items[@]}") || { settings_discard; return 1; }
      first=${mps[$idx]}
      if [ "$idx" = 0 ]; then settings_discard; say "$(branch_name "$first") is already the first drive. Nothing was changed."; return 0; fi
      [ "$now" = mfs ] && say "Note: this pool spreads files by free space, so the order has little effect. It is still saved."
      dry_gate "Save the order: $(branch_name "$first") first, then the others in their current order." \
               "Apply it to the running pool if possible (nothing stops)." && { settings_discard; return 0; }
      cur="$(basename "$first")"
      for mp in "${real[@]}"; do [ "$mp" = "$first" ] || cur="$cur $(basename "$mp")"; done
      setting_put order "$role" "$cur"
      pool_reconfigure "$role" || { settings_rollback; return 1; }
      settings_discard
      say ""; say "Done. Order of the drives in the $role pool: $(order_text "$role")"
      log "pool $role order $cur"
      ;;
  esac
  return 0
}

parse_limit() {
  local t=${1// /} size=$2 n bytes
  t=${t,,}
  if [[ "$t" =~ ^([0-9]+)%$ ]]; then
    n=${BASH_REMATCH[1]}
    if [ "$n" -lt 1 ] || [ "$n" -gt 50 ]; then note "A percentage must be from 1% to 50%."; return 1; fi
    echo "pct $n"; return 0
  fi
  if [[ "$t" =~ ^([0-9]+(\.[0-9]+)?)(kb|mb|gb|tb|k|m|g|t)$ ]]; then
    n=${BASH_REMATCH[1]}
    case "${BASH_REMATCH[3]}" in k|kb) bytes=1000 ;; m|mb) bytes=1000000 ;; g|gb) bytes=1000000000 ;; *) bytes=1000000000000 ;; esac
    bytes=$(awk -v n="$n" -v u="$bytes" 'BEGIN { printf "%.0f", n * u }')
    if [ "$bytes" -lt $(( size / 100 )) ] || [ $(( bytes * 2 )) -gt "$size" ]; then
      note "The limit must be from 1% to 50% of the drive ($(human $(( size / 100 ))) to $(human $(( size / 2 ))))."; return 1
    fi
    echo "bytes $bytes"; return 0
  fi
  note "Type the free space to keep as a size such as 50GB or as a percentage such as 8%."
  return 1
}

limit_text() {
  local k lim
  k=$(branch_minfree "$1"); lim=$(setting_get limit "$(basename "$1")")
  [ -n "$k" ] || { printf '%s' "unknown (the drive is not mounted)"; return 0; }
  if [ -n "$lim" ] && [ "$k" != "$(( $(df -B1 --output=size "$1" | awk 'NR==2 {print $1}') * POOL_FREE_PERCENT / 100 / 1024 ))K" ]; then
    printf '%s (your setting)' "$(human $(( ${k%K} * 1024 )))"
  else
    printf '%s%% = %s (automatic)' "$POOL_FREE_PERCENT" "$(human $(( ${k%K} * 1024 )))"
  fi
}

# `limit`: set how much free space a pool drive keeps before the pool uses the next drive.
limit_flow() {
  array_guard || return 1
  local mp role label size cur new parsed
  mp=$(pick_branch "Which drive do you want to set the free-space limit for? ") || return 1
  role=$(branch_role "$mp"); label=$(basename "$mp")
  if ! mountpoint -q "$mp"; then note "$(branch_name "$mp") is not connected. Reconnect it first (sudo drives remount). Nothing was changed."; return 1; fi
  size=$(total_bytes "$mp")
  say ""
  say "$(branch_name "$mp") is $(human "$size"). It keeps this much free before the $role pool uses the next drive: $(limit_text "$mp")"
  say "(A nearly full drive performs poorly. A limit from 1% to 50% of the drive is accepted. Type  auto  for the automatic ${POOL_FREE_PERCENT}%.)"
  new=$(ask "New free-space limit (for example 50GB or 8%; Enter cancels): ")
  [ -n "$new" ] || { say "Cancelled. Nothing was changed."; return 1; }
  settings_snapshot
  if [ "$new" = auto ]; then
    if [ -z "$(setting_get limit "$label")" ]; then settings_discard; say "The limit is already automatic. Nothing was changed."; return 0; fi
    dry_gate "Go back to the automatic limit (${POOL_FREE_PERCENT}%) for $(branch_name "$mp")." "Apply it to the running pool if possible (nothing stops)." && { settings_discard; return 0; }
    setting_del limit "$label"
  else
    parsed=$(parse_limit "$new" "$size") || { settings_discard; note "Nothing was changed."; return 1; }
    if [ "$(setting_get limit "$label")" = "$parsed" ]; then settings_discard; say "That is already the limit. Nothing was changed."; return 0; fi
    dry_gate "Keep $new free on $(branch_name "$mp") before the $role pool uses the next drive." "Apply it to the running pool if possible (nothing stops)." && { settings_discard; return 0; }
    setting_put limit "$label" "$parsed"
  fi
  pool_reconfigure "$role" || { settings_rollback; return 1; }
  settings_discard
  say ""; say "Done. $(branch_name "$mp") keeps this much free: $(limit_text "$mp")"
  log "limit $label: ${parsed:-auto}"
  return 0
}

