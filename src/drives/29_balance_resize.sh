BALANCE_TMP=""

PICK_COUNT=0; PICK_BYTES=0
balance_pick_files() {
  local giver=$1 recv=$2 want=$3 list=$4 sz rel remaining=$3 count=0 got=0 stop
  stop=$(( want / 50 )); [ "$stop" -ge 1 ] || stop=1
  : >"$list"
  while IFS=$'\t' read -r -d '' sz rel; do
    [ "$sz" -le "$remaining" ] || continue
    [ -e "$recv/$rel" ] && continue
    [ -n "${BALANCE_TAKEN[$giver/$rel]:-}" ] && continue
    BALANCE_TAKEN[$giver/$rel]=1
    printf '%s\0' "$rel" >>"$list"
    count=$((count + 1)); got=$((got + sz)); remaining=$((remaining - sz))
    [ "$remaining" -ge "$stop" ] || break
  done < <(find "$giver" -xdev -type f ! -path "$giver/lost+found/*" -printf '%s\t%P\0' 2>/dev/null | sort -z -t$'\t' -k1,1nr)
  PICK_COUNT=$count; PICK_BYTES=$got
}

balance_undo() {
  local recv=$1 list=$2 rel
  while IFS= read -r -d '' rel; do rm -f -- "${recv:?}/$rel"; done <"$list"
}

balance_table() {
  local mp
  for mp in "$@"; do
    printf '  %-28s %9s of %-9s %s\n' "$(branch_name "$mp")" "$(human "$(used_bytes "$mp")")" "$(human "$(total_bytes "$mp")")" "$(pct "$(used_bytes "$mp")" "$(total_bytes "$mp")")"
  done
}

# `balance`: spread the files in the Main pool evenly across its drives.
balance_main() {
  local role pool mp i n it pg lo hi g r b lim
  local -a mps=() rows=() steps=() lists=() gs=() rs=() cnt=() nbytes=()
  declare -gA BALANCE_TAKEN=()
  role=$(pick_pool_role 2) || return 1
  pool=$(role_pool "$role")
  for mp in $(branches_of "$role"); do
    is_boot_section "$mp" && continue
    if ! mountpoint -q "$mp"; then note "$(branch_name "$mp") is not connected. Reconnect it first (sudo drives remount). Nothing was changed."; return 1; fi
    mps+=("$mp")
  done
  say ""
  say "Used space in the $role pool now (the boot drive section is left out: it is only used when the others are full):"
  balance_table "${mps[@]}"
  lo=100; hi=0
  for mp in "${mps[@]}"; do
    pg=$(( $(used_bytes "$mp") * 100 / $(total_bytes "$mp") ))
    [ "$pg" -lt "$lo" ] && lo=$pg
    [ "$pg" -gt "$hi" ] && hi=$pg
  done
  if [ $(( hi - lo )) -le "$BALANCE_TOLERANCE" ]; then
    say ""; say "The drives are already within $BALANCE_TOLERANCE percentage points of each other. Nothing needs to be moved."; return 0
  fi
  for mp in "${mps[@]}"; do
    lim=$(branch_minfree "$mp" | tr -d K); lim=${lim:-0}
    rows+=("$(total_bytes "$mp") $(used_bytes "$mp") $(avail_bytes "$mp") $(( lim * 1024 ))")
  done
  mapfile -t steps < <(printf '%s\n' "${rows[@]}" | awk -v tol="$BALANCE_TOLERANCE" '
    { size[NR] = $1; used[NR] = $2; free[NR] = $3; lim[NR] = $4; n = NR; tu += $2; ts += $1 }
    END {
      for (it = 0; it < 20; it++) {
        g = 0; r = 0; sg = -1e30; sr = 1e30
        for (i = 1; i <= n; i++) {
          s = used[i] - tu * size[i] / ts
          if (s > sg) { sg = s; g = i }
          if (free[i] - lim[i] > 0 && s < sr) { sr = s; r = i }
        }
        if (g == 0 || r == 0 || g == r) break
        if (used[g] * 100 / size[g] - used[r] * 100 / size[r] <= tol) break
        amt = sg; if (-sr < amt) amt = -sr; h = free[r] - lim[r]; if (h < amt) amt = h
        if (amt < size[g] / 100) break
        printf "%d %d %.0f\n", g - 1, r - 1, amt
        used[g] -= amt; used[r] += amt; free[g] += amt; free[r] -= amt
      }
    }')
  if [ ${#steps[@]} -eq 0 ]; then say ""; say "No move would help (the emptier drives have no room above their free-space limit). Nothing was changed."; return 0; fi
  BALANCE_TMP=$(mktemp -d)
  local total=0 files=0
  for i in "${!steps[@]}"; do
    read -r g r b <<<"${steps[$i]}"
    lists+=("$BALANCE_TMP/list$i"); gs+=("$g"); rs+=("$r")
    balance_pick_files "${mps[$g]}" "${mps[$r]}" "$b" "$BALANCE_TMP/list$i"
    cnt+=("$PICK_COUNT"); nbytes+=("$PICK_BYTES"); total=$((total + PICK_BYTES)); files=$((files + PICK_COUNT))
  done
  if [ "$files" -eq 0 ]; then say ""; say "No suitable files were found to move. Nothing was changed."; return 0; fi
  say ""
  say "The plan: move $(human "$total") ($files files) so the drives end up about equally full:"
  for i in "${!steps[@]}"; do
    [ "${cnt[$i]}" -gt 0 ] && say "  - $(human "${nbytes[$i]}") (${cnt[$i]} files) from $(branch_name "${mps[${gs[$i]}]}") to $(branch_name "${mps[${rs[$i]}]}")"
  done
  say "Each file is copied and checked first, then removed from the old drive. The files keep their place in the pool."
  say "The services keep running while the files are copied. They stop for a short time at the end to copy the last changes."
  say "A large move can take hours. New files still go where the fill order says (see: sudo drives fillorder)."
  yn "Move the files now?" || { say "Cancelled. Nothing was changed."; return 1; }
  pre_change "Copy the chosen files ($(human "$total")) between the drives of the $role pool, while the services run." \
             "Stop the containers that use the $role pool for a short time and copy the last changes." \
             "Check every copied file, then remove the old copies, and start the containers again." && return 0
  for i in "${!steps[@]}"; do
    [ "${cnt[$i]}" -gt 0 ] || continue
    say "Copying $(human "${nbytes[$i]}") from $(branch_name "${mps[${gs[$i]}]}") to $(branch_name "${mps[${rs[$i]}]}") (pass 1, services keep running)..."
    rsync -aH --numeric-ids --from0 --files-from="${lists[$i]}" --ignore-missing-args "${mps[${gs[$i]}]}/" "${mps[${rs[$i]}]}/"
    n=$?
    if [ "$n" -ne 0 ] && [ "$n" -ne 24 ]; then
      warn "Copy failed (code $n). The old copies were not removed."
      for it in "${!steps[@]}"; do balance_undo "${mps[${rs[$it]}]}" "${lists[$it]}"; done
      return 1
    fi
  done
  stop_containers "$pool"
  say "Pass 2 (catching changes made during the first pass)..."
  local rel bad=0
  for i in "${!steps[@]}"; do
    [ "${cnt[$i]}" -gt 0 ] || continue
    while IFS= read -r -d '' rel; do
      [ -e "${mps[${gs[$i]}]}/$rel" ] || rm -f -- "${mps[${rs[$i]}]:?}/$rel"
    done <"${lists[$i]}"
    rsync -aH --numeric-ids --from0 --files-from="${lists[$i]}" --ignore-missing-args "${mps[${gs[$i]}]}/" "${mps[${rs[$i]}]}/"
    n=$?
    if [ "$n" -ne 0 ] && [ "$n" -ne 24 ]; then bad=1; break; fi
    if rsync -aHn --numeric-ids --itemize-changes --from0 --files-from="${lists[$i]}" --ignore-missing-args "${mps[${gs[$i]}]}/" "${mps[${rs[$i]}]}/" | grep -q '^>f'; then bad=1; break; fi
  done
  if [ "$bad" = 1 ]; then
    warn "The check found files that are not copied correctly. Nothing was removed from the old drives."
    for it in "${!steps[@]}"; do balance_undo "${mps[${rs[$it]}]}" "${lists[$it]}"; done
    start_containers
    return 1
  fi
  say "Verified: every moved file is on its new drive. Removing the old copies..."
  for i in "${!steps[@]}"; do
    [ "${cnt[$i]}" -gt 0 ] || continue
    while IFS= read -r -d '' rel; do rm -f -- "${mps[${gs[$i]}]:?}/$rel"; done <"${lists[$i]}"
  done
  sync_fs "${mps[@]}"
  start_containers
  log "balanced $role: moved $total bytes ($files files)"
  say ""
  say "Done. Used space in the $role pool now:"
  balance_table "${mps[@]}"
  return 0
}

balance_flow() {
  array_guard || return 1
  local rc=0
  balance_main || rc=$?
  [ -n "$BALANCE_TMP" ] && rm -rf "$BALANCE_TMP"
  BALANCE_TMP=""
  return "$rc"
}

# `resize`: make a boot drive section bigger or smaller.
resize_flow() {
  array_guard || return 1
  need_cmds fallocate resize2fs e2fsck truncate || return 1
  local role idx mp img pool cur used free max lower min keep gb bytes new_gb prompt shrink=0 fs_min before_files after_files before_used
  local -a roles=() items=()
  for role in main backup; do
    [ -n "$(boot_section_of "$role")" ] || continue
    roles+=("$role"); items+=("$([ "$role" = main ] && echo Main || echo Backup) storage: $(branch_name "$(boot_section_of "$role")")")
  done
  if [ ${#roles[@]} -eq 0 ]; then
    note "There is no boot drive section to resize. Make one with:  sudo drives bootsection"
    return 1
  fi
  if [ ${#roles[@]} -eq 1 ]; then role=${roles[0]}; else idx=$(choose "Which boot drive section? " "${items[@]}") || return 1; role=${roles[$idx]}; fi
  mp=$(boot_section_of "$role"); img=$(boot_image_of "$mp"); pool=$(role_pool "$role")
  if [ ! -f "$img" ] || ! mountpoint -q "$mp"; then note "$(branch_name "$mp") is not mounted. Run  sudo drives remount  first. Nothing was changed."; return 1; fi
  cur=$(stat -c %s "$img"); used=$(used_bytes "$mp")
  keep=$BOOT_KEEP_FREE_BYTES; min=$BOOT_MIN_BYTES
  free=$(( $(boot_free_bytes) + cur ))
  max=$(( (free - keep) / BOOT_UNIT_BYTES * BOOT_UNIT_BYTES ))
  lower=$(( (used * 100 / 90 + BOOT_UNIT_BYTES - 1) / BOOT_UNIT_BYTES * BOOT_UNIT_BYTES ))
  [ "$lower" -ge "$min" ] || lower=$min
  say ""
  say "$(branch_name "$mp") is $(pretty_size "$cur") now and holds $(human "$used") ($(pct "$used" "$cur"))."
  say "Free space on the boot drive: $(pretty_size "$(( free - cur ))"). It always keeps at least $(pretty_size "$keep") free."
  if [ "$max" -lt "$lower" ]; then
    note "It cannot change: it would have to be at least $(pretty_size "$lower") but at most $(pretty_size "$(( max > 0 ? max : 0 ))") fits. Nothing was changed."
    return 1
  fi
  say "The new size can be from $(( lower / BOOT_UNIT_BYTES )) $BOOT_UNIT_NAME to $(( max / BOOT_UNIT_BYTES )) $BOOT_UNIT_NAME (the files may fill at most 90% of it)."
  while :; do
    prompt="New size in $BOOT_UNIT_NAME [$(( lower / BOOT_UNIT_BYTES )) to $(( max / BOOT_UNIT_BYTES )) $BOOT_UNIT_NAME, Enter to cancel]: "
    gb=$(ask "$prompt"); gb=${gb//[GgMm][Bb]/}; gb=${gb//[GgMm]/}; gb=${gb// /}
    [ -n "$gb" ] || { say "Cancelled. Nothing was changed."; return 1; }
    if [[ "$gb" =~ ^[0-9]+$ ]]; then
      bytes=$(( gb * BOOT_UNIT_BYTES ))
      [ "$bytes" -lt "$lower" ] && { note "That is too small. The files in it would fill more than 90% of it: the smallest is $(pretty_size "$lower")."; continue; }
      [ "$bytes" -gt "$max" ] && { note "The size is too large. The boot drive must keep $(pretty_size "$keep") free: the most is $(( max / BOOT_UNIT_BYTES )) $BOOT_UNIT_NAME."; continue; }
      break
    fi
    note "Enter a number of $BOOT_UNIT_NAME, for example 100."
  done
  new_gb=$bytes
  if [ "$bytes" -eq "$cur" ]; then say "It already has that size. Nothing was changed."; return 0; fi
  [ "$bytes" -lt "$cur" ] && shrink=1
  if [ "$shrink" = 1 ]; then
    say ""
    say "Making the section smaller rewrites its file system. If the power fails during this, the section can be damaged."
    say "The files in it are in the backup only if the Main pool is backed up. A section of the Backup pool has no second copy."
    typed "CONTINUE" "Type CONTINUE to continue, or press Enter to cancel: " || { say "Cancelled. Nothing was changed."; return 1; }
  fi
  yn "Change the section from $(pretty_size "$cur") to $(pretty_size "$new_gb") now? The $role containers stop for at least a minute." || { say "Cancelled. Nothing was changed."; return 1; }
  pre_change "Stop the containers that use the $role pool." \
             "Unmount the $role pool and $(branch_name "$mp"), check its file system." \
             "$([ "$shrink" = 1 ] && echo "Shrink the file system, then the file, to $(pretty_size "$new_gb")." || echo "Make the file $(pretty_size "$new_gb") big and grow the file system into it.")" \
             "Mount everything again, compare the files, and start the containers." && return 0
  before_files=$(find "$mp" -xdev -type f 2>/dev/null | wc -l); before_used=$used
  stop_containers "$pool"
  ROLLED_BACK=1
  pool_umount "$pool" || { start_containers; die "Could not unmount $pool (something is using it). Nothing was changed."; }
  if ! umount "$mp" 2>/dev/null; then mount_fstab "$pool" 2>/dev/null; start_containers; die "Could not take $(branch_name "$mp") offline (something is using it). Nothing was changed."; fi
  back() { mount_fstab "$mp" 2>/dev/null; mount_fstab "$pool" 2>/dev/null; start_containers; }
  if ! e2fsck -fn "$img" >/dev/null 2>&1; then back; die "The file system of the section has errors, so it was not resized. Nothing was changed. Check it with: sudo drives check"; fi
  e2fsck -fp "$img" >/dev/null 2>&1 || true
  if [ "$shrink" = 1 ]; then
    fs_min=$(resize2fs -P "$img" 2>/dev/null | awk -F: '/minimum size/ {gsub(/ /, "", $2); print $2}')
    if [[ "$fs_min" =~ ^[0-9]+$ ]] && [ $(( fs_min * $(dumpe2fs -h "$img" 2>/dev/null | awk -F: '/^Block size/ {gsub(/ /, "", $2); print $2}') )) -gt "$new_gb" ]; then
      back; die "The files do not fit into $(pretty_size "$new_gb"). Nothing was changed."
    fi
    if ! resize2fs "$img" "$(( new_gb / 1024 ))K" >/dev/null 2>&1; then
      back; die "Shrinking the file system failed. Check it with: sudo drives check --full"
    fi
    truncate -s "$new_gb" "$img"
  else
    if ! fallocate -l "$new_gb" "$img" 2>/dev/null; then back; die "Could not reserve $(pretty_size "$new_gb") on the boot drive. Nothing was changed."; fi
    if ! resize2fs "$img" >/dev/null 2>&1; then truncate -s "$cur" "$img"; back; die "Growing the file system failed. The section has its old size again."; fi
  fi
  e2fsck -fn "$img" >/dev/null 2>&1 || warn "The check after the change reports problems. Run: sudo drives check --full"
  if ! mount_fstab "$mp"; then mount_fstab "$pool" 2>/dev/null; start_containers; die "Could not mount the section again. Run  sudo drives remount"; fi
  if ! mount_fstab "$pool"; then start_containers; die "Could not mount the $role pool again. Run  sudo drives remount"; fi
  after_files=$(find "$mp" -xdev -type f 2>/dev/null | wc -l)
  start_containers
  name_store_put "$(basename "$mp")" "$(pretty_size "$(stat -c %s "$img")") boot drive section"
  log "resized $img: $cur -> $new_gb bytes (files $before_files -> $after_files)"
  say ""
  if [ "$before_files" != "$after_files" ]; then
    warn "The number of files changed ($before_files before, $after_files after). Check the section: sudo drives check --full"
    return 1
  fi
  say "Done. $(branch_name "$mp") is now $(pretty_size "$(stat -c %s "$img")") and holds $(human "$(used_bytes "$mp")") ($after_files files, all there; before: $(human "$before_used"))."
  return 0
}

