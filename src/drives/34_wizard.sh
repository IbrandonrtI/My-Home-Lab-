WIZARD_KEEP=""
WIZARD_ERASE=""
in_list() { [ -n "${2:-}" ] && grep -qxF -- "$1" <<<"$2"; }
keepable_disk() {
  local -a p; mapfile -t p < <(parts_of "$1")
  [ ${#p[@]} -eq 1 ] && [ "$(fs_type "${p[0]}")" = ext4 ]
}
disk_files_text() {
  local d=$1 fs label used total n
  local -a p; mapfile -t p < <(parts_of "$d")
  n=${#p[@]}
  if [ "$n" -eq 0 ]; then fs=$(blkid -p -s TYPE -o value "$d" 2>/dev/null); echo "${fs:-unknown} file system on the whole drive"; return 0; fi
  fs=$(fs_type "${p[0]}"); label=$(fs_label "${p[0]}")
  if [ "$n" -eq 1 ] && [ "$fs" = ext4 ]; then
    used=$(disk_used_bytes "$d")
    total=$(disk_size_bytes "$d")
    echo "ext4${label:+, label '$label'}, ${used:+about $(pretty_size "$used") of }$(pretty_size "${total:-0}")${used:+ used}"
  else
    echo "$n partition(s)${fs:+, the first is $fs}${label:+ '$label'}"
  fi
}
disk_used_bytes() {
  local -a p; mapfile -t p < <(parts_of "$1")
  [ ${#p[@]} -eq 1 ] || return 0
  dumpe2fs -h "${p[0]}" 2>/dev/null | awk -F: '/^Block count/ {bc=$2+0} /^Free blocks/ {fb=$2+0} /^Block size/ {bs=$2+0} END {if (bs > 0) print (bc - fb) * bs}'
}
wizard_suggest_keep() {
  if [ "$1" -eq 2 ] && [ "$2" -eq 1 ]; then echo "mirror pool"; else echo "pool -"; fi
}
wizard_storage_exists() { array_active || [ -n "$(branches_of main)" ] || [ -n "$(branches_of backup)" ] || [ -n "$(parity_mounts)" ] || [ -n "$(legacy_disks)" ]; }
wizard_suggest() {
  case "$1" in
    1) echo "pool -" ;;
    2) echo "mirror zfs-mirror" ;;
    3) echo "snapraid1 zfs-raidz1" ;;
    *) echo "snapraid2 zfs-raidz2" ;;
  esac
}
# The guided setup that runs first on a new machine: asks which drives to use and sets up the pools.
wizard_flow() {
  local d s n=0 total=0 first second id other_n=0 idx hint kept_n=0 erased_n=0 left_n=0 other_size
  local -a blank=() others=() sizes=() ids=() items=() all=() acts=()
  if [ "$WANT_FIRST" = 1 ]; then
    [ -e "$WIZARD_FILE" ] && return 0
    wizard_storage_exists && return 0
    if [ "$TEST_MODE" != 1 ] && [ ! -t 0 ]; then
      mapfile -t blank < <(blank_disks)
      [ ${#blank[@]} -gt 0 ] && note "${#blank[@]} empty drive(s) found. To set up storage on them, run:  sudo drives wizard"
      return 0
    fi
  elif wizard_storage_exists; then
    say ""
    say "The storage is already set up, so the wizard is not needed. It is only for a first setup."
    say "  See it:  sudo drives status      Add a drive to it:  sudo drives connect      Start over:  sudo drives release"
    return 0
  fi

  mapfile -t blank < <(blank_disks)
  for d in $(candidate_disks); do
    case " ${blank[*]:-} " in *" $d "*) ;; *) others+=("$d"); other_n=$((other_n + 1)) ;; esac
  done
  WIZARD_KEEP=""; WIZARD_ERASE=""; WIZARD_DEVS=""
  say ""
  say "Drive scan"
  say "  Not used: the boot drive and drives that are already in a pool."
  if [ ${#blank[@]} -eq 0 ]; then say "  Empty drives found: none."; else
    say "  Empty drives found: ${#blank[@]}"
    for d in "${blank[@]}"; do say "    $(disk_summary "$d")"; done
  fi

  if [ "$other_n" -gt 0 ]; then
    say "  Drives that hold files: $other_n"
    for d in "${others[@]}"; do say "    $(disk_summary "$d")"; say "       on it: $(disk_files_text "$d")"; done
    if [ "$ASSUME_YES" = 1 ]; then
      note "(--yes) Drives that hold files are skipped. Erasing or keeping a drive always requires an explicit answer."
      left_n=$other_n
    else
      say ""
      say "A drive that holds files can still be used. For each one, choose what happens to its files."
      for d in "${others[@]}"; do
        say ""
        say "Drive $(disk_summary "$d")"
        say "  on it: $(disk_files_text "$d")"
        if keepable_disk "$d"; then
          idx=$(CHOOSE_DEFAULT=1 choose "What should be done with this drive? " \
            "Keep its files and use the drive as it is (nothing on it is deleted)" \
            "Erase everything on it and use it as a new, empty drive" \
            "Skip it (do not use it)") || idx=2
        else
          note "Its files cannot be kept: only a drive with one ext4 partition can be added with its files. It can be erased or skipped."
          idx=$(choose "What should be done with this drive? " \
            "Erase everything on it and use it as a new, empty drive" \
            "Skip it (do not use it)") || idx=1
          idx=$((idx + 1))
        fi
        case "$idx" in
          0) WIZARD_KEEP="${WIZARD_KEEP:+$WIZARD_KEEP$'\n'}$d"; kept_n=$((kept_n + 1)); acts+=("$d") ;;
          1) WIZARD_ERASE="${WIZARD_ERASE:+$WIZARD_ERASE$'\n'}$d"; erased_n=$((erased_n + 1)); acts+=("$d") ;;
          *) left_n=$((left_n + 1)) ;;
        esac
      done
    fi
  fi
  all=("${blank[@]}" ${acts[@]+"${acts[@]}"})
  if [ ${#all[@]} -eq 0 ]; then
    if [ "$left_n" -gt 0 ]; then say "No drive is left to use. Run  sudo drives wizard  again to choose differently."
    else say "Connect the drives to use, wait about 10 seconds, then run  sudo drives wizard  again."; fi
    return 0
  fi
  [ "$left_n" -gt 0 ] && say "  Skipped: $left_n drive(s) with files."
  [ "$kept_n" -gt 0 ] && say "  Files kept: $kept_n drive(s). Erased: $erased_n drive(s) with files."
  for d in "${all[@]}"; do
    s=$(disk_size_bytes "$d"); [ -n "$s" ] || s=0
    sizes+=("$s"); total=$((total + s)); n=$((n + 1))
  done

  if [ "$WANT_FIRST" = 1 ] && [ "$ASSUME_YES" != 1 ] && [ ${#acts[@]} -eq 0 ]; then
    local qcap; qcap=$(preset_capacity pool "${sizes[@]}")
    say ""
    say "Suggested setup: $(preset_title pool)"
    say "$(preset_blurb pool)"
    say "Usable space: $(pretty_size "${qcap:-0}")."
    say "$([ "$n" -eq 1 ] && echo "This drive is empty" || echo "These drives are empty"), so nothing on $([ "$n" -eq 1 ] && echo it || echo them) is lost. Other setups (mirror, RAID) are available later with:  sudo drives wizard"
    if yn_yes "Format $([ "$n" -eq 1 ] && echo "this drive" || echo "these $n drives") and set up the plain pool now?"; then
      [ "$DRY_RUN" = 1 ] || { mkdir -p "$STATE_DIR" && printf '%s|pool\n' "$(date +%F)" >"$WIZARD_FILE"; }
      WIZARD_DEVS=$(printf '%s\n' "${all[@]}"); WIZARD_QUICK=1
      preset_flow pool; local qrc=$?
      WIZARD_DEVS=""; WIZARD_KEEP=""; WIZARD_ERASE=""; WIZARD_QUICK=0
      return $qrc
    fi
    [ "$DRY_RUN" = 1 ] || { mkdir -p "$STATE_DIR" && printf '%s|not-now\n' "$(date +%F)" >"$WIZARD_FILE"; }
    say "Nothing was changed. The install continues without a data drive. To set up the drives later, run:  sudo drives wizard"
    return 0
  fi
  if [ "$kept_n" -gt 0 ]; then
    read -r first second < <(wizard_suggest_keep "$n" "$kept_n")
    if [ "$first" = mirror ]; then
      local kd="" od="" used_b
      for d in "${all[@]}"; do if in_list "$d" "$WIZARD_KEEP"; then kd=$d; else od=$d; fi; done
      used_b=$(disk_used_bytes "$kd"); other_size=$(disk_size_bytes "$od")
      if [ -n "$used_b" ] && [ -n "$other_size" ] && [ "$other_size" -lt "$used_b" ]; then first=pool; second="-"; fi
    fi
  else
    read -r first second < <(wizard_suggest "$n")
  fi
  ids=("$first"); [ "$second" != "-" ] && ids+=("$second")
  say ""
  say "Suggested setups for these $n drive(s):"
  [ "$kept_n" -gt 0 ] && say "(Because the files of $kept_n drive(s) are kept, only setups that do not format those drives are offered: the plain pool and the mirror. ZFS, RAID and SnapRAID need erased drives.)"
  for id in "${ids[@]}"; do
    s=$(preset_capacity "$id" "${sizes[@]}")
    if [ "$id" = "$first" ]; then items+=("$(preset_title "$id")  (simple, recommended)")
    elif [ "$(preset_kind "$id")" = pool ]; then items+=("$(preset_title "$id")  (simple alternative)")
    else items+=("$(preset_title "$id")  (RAID, more advanced)"); fi
    say ""
    say "  ${#items[@]}) $(preset_title "$id")   [$id]"
    say "       $(preset_blurb "$id")"
    say "       Usable space: $(pretty_size "${s:-0}") of $(pretty_size "$total") in the $n drives."
    [ "$(preset_kind "$id")" = pool ] || { hint=$(preset_tool_hint "$id"); [ -z "$hint" ] || say "       It needs a program that is not installed:  $hint"; }
  done
  say ""
  if [ "$kept_n" -gt 0 ] || [ "$erased_n" -gt 0 ]; then
    say "Nothing is changed until a setup is chosen and its plan is confirmed. The plan lists which drives are erased and which keep their files."
  else
    say "The drives are formatted only after a setup is chosen, its plan is shown and ERASE is typed. Nothing is changed before that."
  fi
  items+=("Show every setup and choose one manually")
  if [ "$ASSUME_YES" = 1 ]; then idx=0; note "(--yes) taking the first suggestion: $(preset_title "$first")"
  else
    idx=$(CHOOSE_DEFAULT=1 choose "Which one do you want? " "${items[@]}") || {
      [ "$DRY_RUN" = 1 ] || { mkdir -p "$STATE_DIR" && printf '%s|not-now\n' "$(date +%F)" >"$WIZARD_FILE"; }
      say "Nothing was changed. This can be done at any time with:  sudo drives wizard"
      return 0
    }
  fi
  [ "$DRY_RUN" = 1 ] || { mkdir -p "$STATE_DIR" && printf '%s|%s\n' "$(date +%F)" "$([ "$idx" -lt "${#ids[@]}" ] && echo "${ids[$idx]}" || echo list)" >"$WIZARD_FILE"; }
  if [ "$idx" -ge "${#ids[@]}" ]; then
    if [ "$kept_n" -gt 0 ] || [ "$erased_n" -gt 0 ]; then WIZARD_DEVS=$(printf '%s\n' "${all[@]}"); fi
    preset_menu; local rc=$?
    WIZARD_DEVS=""; WIZARD_KEEP=""; WIZARD_ERASE=""
    return $rc
  fi
  WIZARD_DEVS=$(printf '%s\n' "${all[@]}")
  preset_flow "${ids[$idx]}"; local rc=$?
  WIZARD_DEVS=""; WIZARD_KEEP=""; WIZARD_ERASE=""
  return $rc
}

