# ---------- look-only commands: list, usage, health, check (they change nothing; check --full takes one drive offline for a while) ----------
JSON=0               # --json: print machine-readable JSON (the messages go to stderr)
FULL=0               # check --full
FOLDERS=0            # usage --folders
US=$'\037'           # separates the fields of an internal row (a tab would swallow empty fields)

json_str() {
  local s=$1
  s=${s//\\/\\\\}; s=${s//\"/\\\"}; s=${s//$'\n'/\\n}; s=${s//$'\t'/\\t}
  s=$(printf '%s' "$s" | tr -d '\000-\010\013\014\015\016-\037')
  printf '"%s"' "$s"
}
json_num() { if [[ "${1:-}" =~ ^[0-9]+$ ]]; then printf '%s' "$1"; else printf 'null'; fi; }
hs() { if [[ "${1:-}" =~ ^[0-9]+$ ]]; then human "$1"; else printf '%s' "-"; fi; }   # a size for people, or "-"
pct() { if [[ "${1:-}" =~ ^[0-9]+$ ]] && [[ "${2:-}" =~ ^[0-9]+$ ]] && [ "$2" -gt 0 ]; then printf '%s%%' $(( $1 * 100 / $2 )); else printf '%s' "-"; fi; }

drive_rows() {   # one row per drive: name US role US device US size US used US free US state US mount
  local mp p name role d m size prot legacy managed state
  prot=$(protected_disks); legacy=$(legacy_disks); managed=$(managed_disks)
  for mp in $(all_branches); do
    name=$(branch_name "$mp"); role=$(branch_role "$mp"); p=$(branch_part "$mp")
    if is_boot_section "$mp"; then
      if mountpoint -q "$mp"; then
        printf '%s\n' "$name$US$role${US}boot drive$US$(total_bytes "$mp")$US$(used_bytes "$mp")$US$(avail_bytes "$mp")${US}connected (used last)$US$mp"
      else
        printf '%s\n' "$name$US$role${US}boot drive$US$US$US${US}NOT MOUNTED$US$mp"
      fi
    elif [ -n "$p" ] && mountpoint -q "$mp"; then
      printf '%s\n' "$name$US$role$US$p$US$(total_bytes "$mp")$US$(used_bytes "$mp")$US$(avail_bytes "$mp")${US}connected$US$mp"
    else
      printf '%s\n' "$name$US$role$US-$US$US$US${US}MISSING$US$mp"
    fi
  done
  for mp in $(parity_mounts); do
    name=$(branch_base_name "$mp"); p=$(branch_part "$mp")
    if [ -n "$p" ] && mountpoint -q "$mp"; then
      printf '%s\n' "$name${US}parity$US$p$US$(total_bytes "$mp")$US$(used_bytes "$mp")$US$(avail_bytes "$mp")${US}connected$US$mp"
    else
      printf '%s\n' "$name${US}parity$US-$US$US$US${US}MISSING$US$mp"
    fi
  done
  while read -r d kind m; do
    if [ "$d" != "-" ]; then
      printf '%s\n' "$(disk_base_name "$d")${US}array$US$d$US$(disk_size_bytes "$d")$US$US$US$(array_kind_text "$kind")$US"
    else
      printf '%s\n' "$(basename "$m")${US}array${US}-$US$US$US${US}MISSING (cable? replace it with the tools of the array)$US"
    fi
  done < <(array_disk_kinds)
  for d in $(all_disks | sort -u); do
    grep -qx "$d" <<<"$managed" && continue
    size=$(lsblk -dnbo SIZE "$d" 2>/dev/null | head -1 | tr -d ' ')
    if grep -qx "$d" <<<"$prot"; then role=system; state="boot/system drive (never touched)"
    elif grep -qx "$d" <<<"$legacy"; then role=plain-data; state="current data drive, not in a pool yet"
    else role=spare; state="not connected to a pool"; fi
    printf '%s\n' "$(disk_base_name "$d")$US$role$US$d$US$size$US$US$US$state$US"
  done
}

pool_rows() {   # one row per pool: role US path US mounted(1/0) US fstype US size US used US free
  local role pool
  for role in main backup; do
    pool=$(role_pool "$role")
    if mountpoint -q "$pool"; then
      printf '%s\n' "$role$US$pool${US}1$US$(findmnt -no FSTYPE "$pool")$US$(total_bytes "$pool")$US$(used_bytes "$pool")$US$(avail_bytes "$pool")"
    else
      printf '%s\n' "$role$US$pool${US}0$US$US$US$US"
    fi
  done
}

folder_rows() {   # the biggest folders of a pool: bytes US path
  du -x -B1 --max-depth=1 "$1" 2>/dev/null | sort -rn | awk 'NR > 1' | head -10 | while read -r b d; do printf '%s\n' "$b$US$d"; done
}

json_drives() {   # {"pools":[...],"drives":[...]} (usage, list and status all use it)
  local first=1 role pool mounted fst size used free name dev state mount
  printf '{"pools":['
  while IFS=$US read -r role pool mounted fst size used free; do
    [ "$first" = 1 ] || printf ','
    first=0
    printf '{"role":%s,"path":%s,"mounted":%s,"filesystem":%s,"size_bytes":%s,"used_bytes":%s,"free_bytes":%s' \
      "$(json_str "$role")" "$(json_str "$pool")" "$([ "$mounted" = 1 ] && echo true || echo false)" "$(json_str "$fst")" \
      "$(json_num "$size")" "$(json_num "$used")" "$(json_num "$free")"
    if [ "$FOLDERS" = 1 ] && [ "$mounted" = 1 ]; then
      local f2=1 fb fp
      printf ',"folders":['
      while IFS=$US read -r fb fp; do
        [ "$f2" = 1 ] || printf ','
        f2=0
        printf '{"path":%s,"bytes":%s}' "$(json_str "$fp")" "$(json_num "$fb")"
      done < <(folder_rows "$pool")
      printf ']'
    fi
    printf '}'
  done < <(pool_rows)
  printf '],"drives":['
  first=1
  while IFS=$US read -r name role dev size used free state mount; do
    [ "$first" = 1 ] || printf ','
    first=0
    printf '{"name":%s,"role":%s,"device":%s,"size_bytes":%s,"used_bytes":%s,"free_bytes":%s,"state":%s,"mount":%s}' \
      "$(json_str "$name")" "$(json_str "$role")" "$(json_str "$dev")" "$(json_num "$size")" "$(json_num "$used")" "$(json_num "$free")" \
      "$(json_str "$state")" "$(json_str "$mount")"
  done < <(drive_rows)
  printf ']'
  # Main has no drive (and is not a ZFS / RAID setup): the services that keep their files there wait; the panel shows a warning
  local empty=false held n hf=1
  if [ -z "$(branches_of main)" ] && ! array_active; then empty=true; fi
  printf ',"main_empty":%s,"main_held":[' "$empty"
  held=$(sort -u "$(main_hold_file)" 2>/dev/null)
  for n in $held; do [ "$hf" = 1 ] || printf ','; hf=0; printf '%s' "$(json_str "$n")"; done
  printf ']'
  # a RAID or ZFS setup: its name and health (the panel shows it as one tile inside Main, with its drives)
  if array_active; then
    local ah; ah=$(array_health_text); ah=${ah%%   (*}
    printf ',"array":{"title":%s,"health":%s}' "$(json_str "$(preset_title "$(preset_current)")")" "$(json_str "$ah")"
  else printf ',"array":null'; fi
}

list_flow() {
  local name role dev size used free state mount
  if [ "$JSON" = 1 ]; then with_name_cache json_drives; printf '}\n'; return 0; fi
  say ""
  printf '%-26s %-10s %-12s %-9s %s\n' DRIVE ROLE DEVICE SIZE STATE
  while IFS=$US read -r name role dev size used free state mount; do
    printf '%-26s %-10s %-12s %-9s %s\n' "$name" "$role" "${dev:--}" "$(hs "$size")" "$state"
  done < <(drive_rows)
  say ""
  say "Roles: main and backup are pool drives; parity holds SnapRAID protection data; array is part of a ZFS or RAID array. spare = plugged in, not used. system = the boot drive (never touched)."
  say "More: sudo drives usage (space)   sudo drives health (SMART)   sudo drives check (file system errors)"
  say ""
}

usage_flow() {
  local role pool mounted fst size used free name dev state mount fb fp
  if [ "$JSON" = 1 ]; then with_name_cache json_drives; printf '}\n'; return 0; fi
  say ""
  printf '%-26s %-14s %-9s %-9s %-9s %s\n' POOL PATH SIZE USED FREE USED%
  while IFS=$US read -r role pool mounted fst size used free; do
    if [ "$mounted" = 1 ]; then
      printf '%-26s %-14s %-9s %-9s %-9s %s\n' "$role" "$pool" "$(hs "$size")" "$(hs "$used")" "$(hs "$free")" "$(pct "$used" "$size")"
    else
      printf '%-26s %-14s %s\n' "$role" "$pool" "NOT MOUNTED"
    fi
  done < <(pool_rows)
  say ""
  printf '%-26s %-10s %-9s %-9s %-9s %s\n' DRIVE ROLE SIZE USED FREE USED%
  while IFS=$US read -r name role dev size used free state mount; do
    [ -n "$used" ] || continue
    printf '%-26s %-10s %-9s %-9s %-9s %s\n' "$name" "$role" "$(hs "$size")" "$(hs "$used")" "$(hs "$free")" "$(pct "$used" "$size")"
  done < <(drive_rows)
  say ""
  say "The pool stops putting files on a drive when only its free-space limit is left (${POOL_FREE_PERCENT}% unless you set another with: sudo drives limit), so a drive shows as full a little before 100%."
  if [ "$FOLDERS" = 1 ]; then
    while IFS=$US read -r role pool mounted fst size used free; do
      [ "$mounted" = 1 ] || continue
      say ""
      say "Biggest folders in the $role pool ($pool). This can take a while on a big drive."
      while IFS=$US read -r fb fp; do printf '  %-9s %s\n' "$(hs "$fb")" "$fp"; done < <(folder_rows "$pool")
    done < <(pool_rows)
  else
    say "Add --folders to also list the biggest folders (slow on a big drive)."
  fi
  say ""
}

smart_detail() {   # smart_detail /dev/sdX -> health US temperature(C) US power-on hours US reallocated US pending US note
  local dev=$1 sc=smartctl o="" opt h t hrs re pe note=""
  if [ "$TEST_MODE" = 1 ]; then
    if [ -n "${DRIVES_SMARTCTL:-}" ]; then sc=$DRIVES_SMARTCTL; else printf '%s\n' "skipped (test mode)$US$US$US$US$US"; return 0; fi
  fi
  if ! command -v "$sc" >/dev/null 2>&1; then printf '%s\n' "smartctl not installed$US$US$US$US${US}install it with: sudo apt install smartmontools"; return 0; fi
  for opt in "" "-d sat"; do
    # -n standby: a sleeping drive is not woken up just to read its health
    # shellcheck disable=SC2086
    o=$("$sc" -H -A -n standby $opt "$dev" 2>&1)
    if grep -Eqi 'in (STANDBY|SLEEP)' <<<"$o"; then printf '%s\n' "asleep$US$US$US$US${US}not woken up for this; it checks again when the drive is awake"; return 0; fi
    grep -Eq 'overall-health|SMART Health Status|Attribute' <<<"$o" && break
  done
  h=unknown
  if grep -E 'overall-health|SMART Health Status' <<<"$o" | grep -Eq 'PASSED|: OK'; then h=PASSED; fi
  if grep -E 'overall-health|SMART Health Status' <<<"$o" | grep -q 'FAILED'; then h=FAILED; fi
  t=$(awk '$1 == 194 && $10 ~ /^[0-9]/ {sub(/[^0-9].*/, "", $10); print $10; f = 1; exit} $1 == 190 && $10 ~ /^[0-9]/ {sub(/[^0-9].*/, "", $10); a = $10} END {if (!f && a != "") print a}' <<<"$o")
  [ -n "$t" ] || t=$(sed -n 's/^Temperature:[[:space:]]*\([0-9][0-9]*\).*/\1/p; s/^Current Drive Temperature:[[:space:]]*\([0-9][0-9]*\).*/\1/p' <<<"$o" | head -1)
  hrs=$(awk '$1 == 9 && $10 ~ /^[0-9]/ {sub(/[^0-9].*/, "", $10); print $10; exit}' <<<"$o")
  [ -n "$hrs" ] || hrs=$(sed -n 's/^Power On Hours:[[:space:]]*\([0-9,][0-9,]*\).*/\1/p' <<<"$o" | head -1 | tr -d ,)
  re=$(awk '$1 == 5 && $10 ~ /^[0-9]/ {sub(/[^0-9].*/, "", $10); print $10; exit}' <<<"$o")
  pe=$(awk '$1 == 197 && $10 ~ /^[0-9]/ {sub(/[^0-9].*/, "", $10); print $10; exit}' <<<"$o")
  [ "$h" = FAILED ] && note="the drive says it is failing: back up its files now"
  if [ -n "$pe" ] && [ "$pe" -gt 0 ]; then note="${note:+$note; }$pe sector(s) are waiting to be remapped (a bad sign)"; fi
  if [ -n "$re" ] && [ "$re" -gt 0 ]; then note="${note:+$note; }$re sector(s) were already remapped: keep an eye on it"; fi
  if [ -n "$t" ] && [ "$t" -ge 55 ]; then note="${note:+$note; }it is hot (${t} C)"; fi
  printf '%s\n' "$h$US$t$US$hrs$US$re$US$pe$US$note"
}

health_rows() {   # one row per physical drive: name US device US health US temp US hours US reallocated US pending US note
  local d mp p managed
  managed=$(managed_disks)
  for mp in $(all_branches); do
    is_boot_section "$mp" && continue
    p=$(branch_part "$mp"); [ -n "$p" ] || continue
    d=$(disk_of_part "$p"); [ -n "$d" ] || continue
    printf '%s\n' "$(branch_name "$mp")$US$d$US$(smart_detail "$d")"
  done
  for mp in $(parity_mounts); do
    p=$(branch_part "$mp"); [ -n "$p" ] || continue
    d=$(disk_of_part "$p"); [ -n "$d" ] || continue
    printf '%s\n' "$(branch_base_name "$mp")$US$d$US$(smart_detail "$d")"
  done
  for d in $(array_disks); do
    printf '%s\n' "$(disk_base_name "$d")$US$d$US$(smart_detail "$d")"
  done
  for d in $(all_disks | sort -u); do
    grep -qx "$d" <<<"$managed" && continue
    grep -qx "$d" <<<"$(array_disks)" && continue
    printf '%s\n' "$(disk_base_name "$d")$US$d$US$(smart_detail "$d")"
  done
}

disk_ident() {   # disk_ident sdb -> "MODEL US SERIAL" as the drive reports them (read from the system, the drive is not woken up)
  local d=${1#/dev/} m s
  m=$(lsblk -dno MODEL "/dev/$d" 2>/dev/null | sed 's/^ *//; s/ *$//' | head -1)
  s=$(lsblk -dno SERIAL "/dev/$d" 2>/dev/null | sed 's/^ *//; s/ *$//' | head -1)
  printf '%s\n' "$m$US$s"
}

health_flow() {
  local name dev h t hrs re pe note bad=0 first=1 n=0 ident model serial
  if [ "$JSON" = 1 ]; then printf '{"drives":['; fi
  [ "$JSON" = 1 ] || { say ""; printf '%-26s %-10s %-9s %-6s %-8s %-9s %-8s %s\n' DRIVE DEVICE HEALTH TEMP HOURS REALLOC PENDING NOTE; }
  while IFS=$US read -r name dev h t hrs re pe note; do
    n=$((n + 1))
    if [ "$h" = FAILED ] || { [[ "$pe" =~ ^[0-9]+$ ]] && [ "$pe" -gt 0 ]; }; then bad=1; fi
    if [ "$JSON" = 1 ]; then
      [ "$first" = 1 ] || printf ','
      first=0
      ident=$(disk_ident "$dev"); model=${ident%%"$US"*}; serial=${ident#*"$US"}
      printf '{"name":%s,"device":%s,"model":%s,"serial":%s,"health":%s,"temperature_c":%s,"power_on_hours":%s,"reallocated_sectors":%s,"pending_sectors":%s,"note":%s}' \
        "$(json_str "$name")" "$(json_str "$dev")" "$(json_str "$model")" "$(json_str "$serial")" "$(json_str "$h")" "$(json_num "$t")" "$(json_num "$hrs")" "$(json_num "$re")" "$(json_num "$pe")" "$(json_str "$note")"
    else
      printf '%-26s %-10s %-9s %-6s %-8s %-9s %-8s %s\n' "$name" "$dev" "$h" "${t:+${t} C}" "${hrs:--}" "${re:--}" "${pe:--}" "$note"
    fi
  done < <(health_rows)
  if [ "$JSON" = 1 ]; then printf '],"ok":%s}\n' "$([ "$bad" = 0 ] && echo true || echo false)"; return "$bad"; fi
  [ "$n" -gt 0 ] || say "(no drives found)"
  say ""
  if [ "$bad" = 1 ]; then
    say "PROBLEM: at least one drive reports it is failing or has bad sectors. Copy its files to another drive soon."
  else
    say "No drive reports a failure. (A sleeping drive is not woken up just to read its health.)"
  fi
  say ""
  return "$bad"
}

check_findings() {   # check_findings MOUNTPOINT -> lines "LEVEL US text" (OK, WARN or PROBLEM) about one pool drive
  local mp=$1 part dev opts info st errs first sd h pe re base n total used
  if ! mountpoint -q "$mp"; then printf '%s\n' "PROBLEM${US}it is not connected or not mounted (check the cable, then: sudo drives remount)"; return 0; fi
  part=$(branch_part "$mp")
  opts=$(findmnt -no OPTIONS "$mp" 2>/dev/null)
  if [[ ",$opts," == *,ro,* ]]; then printf '%s\n' "PROBLEM${US}it is mounted read-only: it hit an error and the system stopped writing to it"; fi
  if [ -n "$part" ] && command -v tune2fs >/dev/null 2>&1; then
    info=$(tune2fs -l "$part" 2>/dev/null)
    st=$(sed -n 's/^Filesystem state:[[:space:]]*//p' <<<"$info" | head -1)
    errs=$(sed -n 's/^FS Error count:[[:space:]]*//p' <<<"$info" | head -1)
    first=$(sed -n 's/^First error time:[[:space:]]*//p' <<<"$info" | head -1)
    if [ -n "$st" ] && [ "$st" != clean ]; then printf '%s\n' "WARN${US}the file system says it is '$st'"; fi
    if [[ "$errs" =~ ^[0-9]+$ ]] && [ "$errs" -gt 0 ]; then
      printf '%s\n' "PROBLEM${US}the file system has recorded $errs error(s)${first:+, the first on $first}. Run  sudo drives check --full"
    fi
  fi
  if ! is_boot_section "$mp" && [ -n "$part" ]; then
    dev=$(disk_of_part "$part")
    if [ -n "$dev" ]; then
      sd=$(smart_detail "$dev")
      IFS=$US read -r h _ _ re pe _ <<<"$sd"
      [ "$h" = FAILED ] && printf '%s\n' "PROBLEM${US}SMART says the drive is failing"
      if [[ "$pe" =~ ^[0-9]+$ ]] && [ "$pe" -gt 0 ]; then printf '%s\n' "PROBLEM${US}$pe sector(s) are waiting to be remapped"; fi
      if [[ "$re" =~ ^[0-9]+$ ]] && [ "$re" -gt 0 ]; then printf '%s\n' "WARN${US}$re sector(s) were remapped"; fi
    fi
    base=$(basename "$part")
    if [ "$TEST_MODE" = 1 ]; then
      [ -n "${DRIVES_DMESG:-}" ] && n=$(grep -c "EXT4-fs error.*$base" "$DRIVES_DMESG" 2>/dev/null)
    else
      n=$(dmesg 2>/dev/null | grep -c "EXT4-fs error.*$base")
    fi
    if [[ "${n:-0}" =~ ^[0-9]+$ ]] && [ "${n:-0}" -gt 0 ]; then printf '%s\n' "PROBLEM${US}the system log has $n file system error(s) for this drive since the last start"; fi
  fi
  total=$(total_bytes "$mp"); used=$(used_bytes "$mp")
  if [ "$total" -gt 0 ] && [ $(( used * 100 / total )) -ge 95 ]; then printf '%s\n' "WARN${US}it is almost full ($(pct "$used" "$total") used)"; fi
  return 0
}

check_flow() {
  local mp name part f f2 level worst nprob=0 nwarn=0 nok=0 first=1 n=0
  local -a lines=()
  if [ "$FULL" = 1 ]; then run_changing check_full_flow; return $?; fi
  if [ "$JSON" = 1 ]; then printf '{"drives":['; else say ""; fi
  for mp in $(all_branches); do
    n=$((n + 1))
    name=$(branch_name "$mp"); part=$(branch_part "$mp")
    mapfile -t lines < <(check_findings "$mp")
    worst=OK
    for f in "${lines[@]}"; do
      level=${f%%"$US"*}
      [ "$level" = PROBLEM ] && worst=PROBLEM
      [ "$level" = WARN ] && [ "$worst" = OK ] && worst=WARN
    done
    case "$worst" in PROBLEM) nprob=$((nprob + 1)) ;; WARN) nwarn=$((nwarn + 1)) ;; *) nok=$((nok + 1)) ;; esac
    if [ "$JSON" = 1 ]; then
      [ "$first" = 1 ] || printf ','
      first=0
      printf '{"name":%s,"device":%s,"result":%s,"findings":[' "$(json_str "$name")" "$(json_str "${part:--}")" "$(json_str "${worst,,}")"
      f2=1
      for f in "${lines[@]}"; do
        [ -n "$f" ] || continue
        [ "$f2" = 1 ] || printf ','
        f2=0
        printf '{"level":%s,"text":%s}' "$(json_str "${f%%"$US"*}" | tr '[:upper:]' '[:lower:]')" "$(json_str "${f#*"$US"}")"
      done
      printf ']}'
    else
      printf '%s (%s): %s\n' "$name" "${part:--}" "$worst"
      for f in "${lines[@]}"; do [ -n "$f" ] && printf '   - %s: %s\n' "${f%%"$US"*}" "${f#*"$US"}"; done
      [ "$worst" = OK ] && say "   - the file system is clean, no errors are recorded and the drive reports no problem"
    fi
  done
  if [ "$JSON" = 1 ]; then printf '],"ok":%s}\n' "$([ "$nprob" = 0 ] && echo true || echo false)"; [ "$nprob" = 0 ]; return; fi
  if [ "$n" = 0 ] && array_active; then say "The Main pool is a $(preset_title "$(preset_current)") array. Array health: $(array_health_text)"; say "(The health of every plugged-in drive:  sudo drives health)"; say ""; return 0; fi
  if [ "$n" = 0 ]; then say "No drives are connected to a pool yet, so there is nothing to check."; say "(The health of every plugged-in drive, pooled or not:  sudo drives health)"; say ""; return 0; fi
  say ""
  say "Checked $n drive(s): $nok ok, $nwarn with a warning, $nprob with a problem. Nothing was changed."
  say "This quick check reads what the file system and the drive recorded. For a full scan of one drive: sudo drives check --full"
  say ""
  [ "$nprob" = 0 ]
}

check_full_flow() {   # a full read-only scan of one drive: it is taken offline for the scan (the containers stop), then put back
  command -v e2fsck >/dev/null 2>&1 || { note "The tool 'e2fsck' is missing (package e2fsprogs)."; return 1; }
  local mp name role pool part rc=0
  mp=$(pick_branch "Which drive do you want to scan? ") || return 1
  name=$(branch_name "$mp"); role=$(branch_role "$mp"); pool=$(role_pool "$role")
  part=$(branch_part "$mp")
  if [ -z "$part" ] || ! mountpoint -q "$mp"; then note "$name is not connected, so it cannot be scanned."; return 1; fi
  say "$name will be scanned from start to finish. The scan is read-only: nothing on the drive is changed."
  say "For the scan the drive is taken offline, so the containers that use the $role pool stop until it is done."
  say "A big drive can take an hour or more."
  yn "Continue?" || { say "Cancelled. Nothing was changed."; return 1; }
  pre_change "Stop the containers that use the $role pool." \
             "Unmount the $role pool and $name." \
             "Scan $part (read-only)." \
             "Mount $name and the $role pool again, then start the containers." && return 0
  stop_containers "$pool"
  ROLLED_BACK=1    # nothing in fstab changes, so if a step fails the old mounts can simply be restored
  pool_umount "$pool" || { start_containers; die "Could not unmount $pool (something is using it). Nothing was changed."; }
  if mountpoint -q "$mp" && ! umount "$mp" 2>/dev/null; then
    mount_fstab "$pool" 2>/dev/null
    start_containers
    die "Could not take $name offline (something is using it). Nothing was changed."
  fi
  say "Scanning $part (read-only)..."
  e2fsck -fn "$part" || rc=$?
  mount_fstab "$mp" || die "Could not mount $name again. Run  sudo drives remount"
  mount_fstab "$pool" || die "Could not mount the $role pool again. Run  sudo drives remount"
  start_containers
  say ""
  if [ "$rc" = 0 ]; then
    say "The scan found no errors on $name. Nothing was changed."
    return 0
  fi
  say "The scan reported problems on $name (code $rc). Read the lines above. Nothing was changed."
  say "To repair it, copy the files to another drive first (sudo drives disconnect), then repair the drive with e2fsck while it is not in use."
  return 1
}

look_menu() {
  local c
  while :; do
    say ""
    say "Look at the drives (nothing is changed, except in the last choice)"
    say "  1) Status: pools, drives and the last backup"
    say "  2) List of all drives"
    say "  3) Space used and free"
    say "  4) Health (SMART)"
    say "  5) Quick check for file system errors"
    say "  6) Full scan of one drive (stops the containers for a while)"
    say "  0) Back"
    c=$(ask_choice)
    case "$c" in
      1) with_name_cache status_flow ;;
      2) with_name_cache list_flow ;;
      3) with_name_cache usage_flow ;;
      4) with_name_cache health_flow ;;
      5) check_flow ;;
      6) FULL=1 check_flow ;;
      0|"") return 0 ;;
      *) say "Please type a number from the list." ;;
    esac
  done
}

