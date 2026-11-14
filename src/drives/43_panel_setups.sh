
setup_tolerates() {
  case "$1" in
    zfs-mirror|md-raid1) echo $(( $2 - 1 )) ;;
    mirror|snapraid1|zfs-raidz1|md-raid5|md-raid10) echo 1 ;;
    snapraid2|zfs-raidz2|md-raid6) echo 2 ;;
    zfs-raidz3) echo 3 ;;
    *) echo 0 ;;
  esac
}
setup_soft() { case "$1" in mirror|snapraid1|snapraid2) return 0 ;; *) return 1 ;; esac; }

setup_score() {
  local id=$1 t=$2 cap=$3 total=$4 prot space s
  case "$t" in 0) prot=0 ;; 1) prot=60 ;; 2) prot=85 ;; *) prot=95 ;; esac
  if [ "$t" -gt 0 ] && setup_soft "$id"; then prot=$((prot - 10)); fi
  space=0; [ "$total" -gt 0 ] && space=$(( cap * 100 / total ))
  s=$(( (prot + space) * 5 ))
  case "$id" in zfs-*) [ "$t" -gt 0 ] && s=$((s + 5)) ;; esac
  echo "$s"
}

setup_choose() {
  local id=$1; shift
  local -a s=("$@"); local n=${#s[@]} min max k best=0 bestcap=0 cap
  min=$(preset_min "$id"); max=$(preset_max "$id")
  [ "$n" -ge "$min" ] || return 1
  if [ "$max" -gt 0 ] && [ "$n" -gt "$max" ]; then n=$max; fi
  for ((k = min; k <= n; k++)); do
    cap=$(preset_capacity "$id" "${s[@]:0:k}")
    [ -n "$cap" ] || continue
    if [ "$cap" -gt "$bestcap" ]; then best=$k; bestcap=$cap; fi
  done
  [ "$best" -gt 0 ] || return 1
  echo "$best $bestcap"
}

setup_blocker() {
  local id=$1
  if array_active; then echo "The Main pool is already a $(preset_title "$(preset_current)") setup. It must be removed first (sudo drives release)."; return 0; fi
  if [ -n "$(parity_mounts)" ]; then echo "The Main pool uses SnapRAID parity drives. A new setup creates a new Main pool, so remove the drives from Main first."; return 0; fi
  if [ -n "$(branches_of main)" ]; then
    if ! preset_is_array "$id"; then echo "The Main pool still has drives in it. A new setup creates a new Main pool, so remove the drives from Main first."; return 0; fi
    main_is_pool || { echo "The Main pool is not mounted, so its files cannot be copied into a new setup. Mount it first (sudo drives remount)."; return 0; }
  fi
  if [ "$id" = mirror ] && [ -n "$(branches_of backup)" ]; then echo "The Backup pool still has drives in it. The mirror creates a new Backup pool, so remove its drives first."; return 0; fi
  if preset_is_array "$id" && [ -z "$(branches_of main)" ] && mountpoint -q "$MAIN_POOL"; then echo "$MAIN_POOL is already in use by something else."; return 0; fi
  if [ -n "$(preset_tool_hint "$id")" ]; then echo "The program for this setup is not installed. Run  sudo homelab-setup upgrade  on the server to install it."; return 0; fi
  return 0
}

panel_setups_json() {
  local d s id first=1 i k cap total=0 n tol score why ids_json used hint blank keep skipped main_used=0 main_need=0 migrate
  [ -n "$(branches_of main)" ] && main_is_pool && { main_used=$(pool_used_bytes); main_used=${main_used:-0}; main_need=$(migrate_need_bytes "$main_used"); }
  local -a devs=() sizes=() rows=() chosen=() alld=() alls=()
  local line skipcsv=",${PANEL_SKIP:-},"
  while read -r s d; do
    alld+=("$d"); alls+=("$s")
    case "$skipcsv" in *",$(basename "$d"),"*) continue ;; esac
    devs+=("$d"); sizes+=("$s"); total=$((total + s))
  done < <(for d in $(candidate_disks); do s=$(disk_size_bytes "$d"); [[ "$s" =~ ^[0-9]+$ ]] && echo "$s $d"; done | sort -rn -k1,1)
  n=${#devs[@]}
  printf '{"spare":['
  for i in "${!alld[@]}"; do
    d=${alld[$i]}; blank=false; disk_is_blank "$d" && blank=true
    keep=false; [ "$blank" = false ] && keepable_disk "$d" && keep=true
    skipped=false; case "$skipcsv" in *",$(basename "$d"),"*) skipped=true ;; esac
    [ "$i" = 0 ] || printf ','
    printf '{"id":%s,"device":%s,"name":%s,"size_bytes":%s,"blank":%s,"keep_ok":%s,"skipped":%s}' "$(json_str "$(basename "$d")")" "$(json_str "$d")" "$(json_str "$(disk_base_name "$d")")" "$(json_num "${alls[$i]}")" "$blank" "$keep" "$skipped"
  done
  local svc="" sn sfirst=1
  if [ -n "$(branches_of main)" ]; then
    for sn in $(containers_using "$MAIN_POOL"); do
      [ "$sfirst" = 1 ] || svc="$svc,"; sfirst=0; svc="$svc$(json_str "$sn")"
    done
  fi
  printf '],"total_bytes":%s,"main_used_bytes":%s,"main_has_drives":%s,"main_services":[%s],"options":[' "$(json_num "$total")" "$(json_num "$main_used")" "$([ -n "$(branches_of main)" ] && echo true || echo false)" "$svc"
  for id in $PRESET_IDS; do
    local fits=false k=0 cap=0 used=0 why="" tol=0 score
    migrate=false; preset_is_array "$id" && [ -n "$(branches_of main)" ] && [ -z "$(parity_mounts)" ] && migrate=true
    score=$(( -10 * $(preset_min "$id") ))
    if [ "$n" -ge "$(preset_min "$id")" ] && line=$(setup_choose "$id" "${sizes[@]}"); then
      fits=true; k=${line% *}; cap=${line#* }
      tol=$(setup_tolerates "$id" "$k"); score=$(setup_score "$id" "$tol" "$cap" "$total")
      used=0; for ((i = 0; i < k; i++)); do used=$((used + sizes[i])); done
      why=$(setup_blocker "$id")
      if [ "$migrate" = true ] && [ -z "$why" ] && [ "$cap" -lt "$main_need" ]; then
        why="Too small to hold the contents of Main: this setup holds about $(pretty_size "$cap") and Main has $(pretty_size "$main_used") of files. Add more or larger drives."
      fi
    else
      why="Needs $(preset_drives_text "$id") empty drives; $n found."
    fi
    ids_json=""
    if [ "$fits" = true ]; then for ((i = 0; i < k; i++)); do ids_json="${ids_json:+$ids_json,}$(json_str "$(basename "${devs[$i]}")")"; done; fi
    hint=false; [ -n "$(preset_tool_hint "$id")" ] && hint=true
    rows+=("$score|$(printf '{"id":%s,"title":%s,"blurb":%s,"kind":%s,"fits":%s,"min":%s,"drives":[%s],"usable_bytes":%s,"used_bytes":%s,"tolerates":%s,"nightly":%s,"score":%s,"can_build":%s,"why":%s,"needs_tool":%s,"can_keep":%s,"migrate":%s}' \
      "$(json_str "$id")" "$(json_str "$(preset_title "$id")")" "$(json_str "$(preset_blurb "$id")")" "$(json_str "$(preset_kind "$id")")" "$fits" "$(json_num "$(preset_min "$id")")" "$ids_json" \
      "$(json_num "$cap")" "$(json_num "$used")" "$(json_num "$tol")" "$(setup_soft "$id" && echo true || echo false)" "$score" \
      "$([ "$fits" = true ] && [ -z "$why" ] && echo true || echo false)" "$(json_str "$why")" "$hint" "$(case "$id" in pool|mirror|snapraid1|snapraid2) echo true ;; *) echo false ;; esac)" "$migrate")")
  done
  local sorted rec="" r
  sorted=$(printf '%s\n' "${rows[@]}" | sort -t'|' -k1,1nr -s)
  first=1
  while IFS= read -r r; do
    [ "$first" = 1 ] || printf ','
    first=0
    printf '%s' "${r#*|}"
    [ -z "$rec" ] && case "${r#*|}" in *'"fits":true'*) rec=$(printf '%s' "${r#*|}" | sed 's/^{"id":"\([^"]*\)".*/\1/') ;; esac
  done <<<"$sorted"
  printf '],"recommended":%s,"current":%s}\n' "$(json_str "$rec")" "$(json_str "$(preset_current)")"
}

# panel_setup_run ID DISK,DISK,...: build a ready-made setup on the spare drives the person chose. The flow has already checked the confirmation words.
panel_setup_run() {
  local id=$1 idlist=$2 t d spare
  local -a toks=()
  id=$(preset_alias "$id")
  preset_known "$id" || { panel_refuse "That setup does not exist."; return 1; }
  IFS=, read -ra toks <<<"$idlist"
  [ "${#toks[@]}" -ge 1 ] && [ "${#toks[@]}" -le 16 ] || { panel_refuse "Choose the drives for the setup."; return 1; }
  WIZARD_DEVS=""; WIZARD_ERASE=""; WIZARD_KEEP=""
  spare=$(candidate_disks)
  for t in "${toks[@]}"; do
    local want=""
    case "$t" in *:keep) want=keep; t=${t%:keep} ;; *:erase) want=erase; t=${t%:erase} ;; esac
    [[ "$t" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || { panel_refuse "That drive id is not allowed."; return 1; }
    d="/dev/$t"
    grep -qx "$d" <<<"$spare" || { panel_refuse "$t is not a spare drive that can be used."; return 1; }
    WIZARD_DEVS="${WIZARD_DEVS:+$WIZARD_DEVS$'\n'}$d"
    if [ "$want" = keep ] && ! disk_is_blank "$d"; then
      keepable_disk "$d" || { panel_refuse "The files on $t cannot be kept: it needs exactly one ext4 partition."; return 1; }
      WIZARD_KEEP="${WIZARD_KEEP:+$WIZARD_KEEP$'\n'}$d"
    else
      disk_is_blank "$d" || WIZARD_ERASE="${WIZARD_ERASE:+$WIZARD_ERASE$'\n'}$d"
    fi
  done
  local rc=0
  rm -f "$ABORT_FILE"; echo $$ >"$BATCH_PID_FILE"
  preset_flow "$id" || rc=$?
  rm -f "$BATCH_PID_FILE" "$ABORT_FILE"
  return "$rc"
}
