# ---------- commands ----------
cmd_check() {
  need_root check; take_lock loud
  rule "Look online for newer images"
  local rc=0; do_check 1 || rc=$?
  if [ "$rc" -eq 0 ]; then
    if [ "${#CHECK_NEW[@]}" -eq 0 ] && [ "${#CHECK_DL[@]}" -eq 0 ]; then line_ok "Everything is up to date."
    else line_warn "${#CHECK_NEW[@]} to download, ${#CHECK_DL[@]} downloaded and waiting for you.  Run:  sudo homelab-update"; fi
  fi
  echo
  return "$rc"
}

cmd_refresh() {
  need_root refresh; take_lock quiet
  local ep; ep=$(summary_epoch) || return 0
  load_containers || return 0
  read_state
  evaluate_state | write_outputs "$ep"
}

cmd_auto() {
  need_root auto
  # the first 10 minutes after a boot: the apps are still starting, so this waits for the next hourly run
  local up=${HOMELAB_UPTIME:-$(cut -d. -f1 /proc/uptime 2>/dev/null)}
  if [[ "${up:-}" =~ ^[0-9]+$ ]] && [ "$up" -lt 600 ]; then return 0; fi
  renice -n 19 -p $$ >/dev/null 2>&1 || true
  ionice -c3 -p $$ >/dev/null 2>&1 || true
  take_lock quiet
  local ep att now; now=$(date +%s)
  if ep=$(summary_epoch); then
    load_containers || exit 0
    read_state
    evaluate_state | write_outputs "$ep"
  fi
  ep=$(summary_epoch) || ep=0
  att=$(cat "$ATTEMPT_FILE" 2>/dev/null); [[ "$att" =~ ^[0-9]+$ ]] || att=0
  if [ $((now - ep)) -ge $((CHECK_EVERY_DAYS * 86400)) ] && [ $((now - att)) -ge $((RETRY_HOURS * 3600)) ]; then
    do_check 0 || true
  fi
  return 0
}

cmd_list() {
  local ep; ep=$(summary_epoch) || ep=""
  rule "Container updates"
  if [ -n "$ep" ]; then echo "  Last check online: $(date -d "@$ep" '+%F %H:%M') ($(( ($(date +%s) - ep) / 86400 )) day(s) ago)"
  else echo "  No check has been saved yet. Run: sudo homelab-update check"; fi
  echo
  load_containers || die "Cannot talk to Docker (is your user in the docker group?)."
  build_images
  read_state
  print_plan
  echo
  [ "${#HELD_LIST[@]}" -eq 0 ] || line_note "Left alone on purpose: ${HELD_LIST[*]}"
  [ "${#PINNED_LIST[@]}" -eq 0 ] || line_note "Pinned to an exact version (newer version numbers are looked up at each check): ${PINNED_LIST[*]}"
  echo
}

confirm() {   # confirm TEXT yes(0/1)
  [ "$2" -eq 1 ] && return 0
  [ -t 0 ] || [ "${HLU_TEST_STDIN:-}" = 1 ] || die "Not a terminal. Add --yes to go on without asking."
  local a; read -r -p "  $1 [y/N] " a
  [[ "$a" == [yY]* ]]
}

cmd_run() {
  local yes=$1 rc=0 img free
  need_root ""; take_lock loud
  printf '\n  %shomelab-update%s %s\n' "$B" "$N" "$VERSION"
  rule "Step 1 of 4 ${S_DOT} Look online (nothing is downloaded yet)"
  do_check 1 || rc=$?
  if [ "$rc" -ne 0 ]; then
    [ "$CHECK_OK" -gt 0 ] || die "No answer from any registry. Check the internet (ping 1.1.1.1), then try again."
    line_warn "Some images could not be checked. Going on with the ones that could."
  fi
  if [ "${#CHECK_NEW[@]}" -eq 0 ] && [ "${#CHECK_DL[@]}" -eq 0 ]; then
    line_ok "Nothing to do: every checked container runs the newest image."; echo; return 0
  fi
  confirm "Download ${#CHECK_NEW[@]} image(s)? No running container is changed yet. Continue?" "$yes" || { echo; echo "  Stopped. Nothing was downloaded."; return 0; }

  rule "Step 2 of 4 ${S_DOT} Download"
  if [ "${#CHECK_NEW[@]}" -eq 0 ]; then line_ok "Nothing new to download (the newer images are already here)."; else
    free=$(free_gb); free=${free:-0}
    if [ "$free" -lt "$MIN_FREE_GB" ]; then die "Only ${free} GB free where Docker keeps its images; need at least $MIN_FREE_GB. Free some space (sudo homelab-update clean) and try again."; fi
    echo "  One at a time. Big images take a few minutes."
    echo
    local out prc msg pr failed_pull=()
    for img in "${CHECK_NEW[@]}"; do
      pr=$img; [ -n "${NEWTAG[$img]:-}" ] && pr="${img%:*}:${NEWTAG[$img]}"
      printf '   %s%s%s  %s\n' "$C" "$S_DL" "$N" "$pr"
      rollback_tag "$img"
      out=$(docker pull "$pr" 2>&1); prc=$?
      if [ "$prc" -ne 0 ]; then
        failed_pull+=("$img")
        printf '      %s%s FAILED:%s %s\n' "$R" "$S_BAD" "$N" "$(printf '%s\n' "$out" | tail -n 1)"
        printf '%s\n' "$out" | grep -qi 'toomanyrequests' && echo "      The registry is throttling downloads. Wait a few minutes and run homelab-update again."
      else
        msg=$(printf '%s\n' "$out" | grep -E '^Status:' | tail -n 1)
        case "$msg" in *"Downloaded newer"*) msg="downloaded" ;; *"up to date"*) msg="already up to date" ;; esac
        printf '      %s%s %s%s\n' "$G" "$S_OK" "${msg:-done}" "$N"
      fi
      sleep "${HLU_PULL_PAUSE:-2}"
    done
    [ "${#failed_pull[@]}" -eq 0 ] || { echo; line_warn "${#failed_pull[@]} download(s) failed; they are marked [not downloaded yet] below. Run homelab-update again later."; }
  fi

  # save what we know now (so the login screen shows the new state even if something stops later)
  refresh_state

  rule "Step 3 of 4 ${S_DOT} Is anything being uploaded?"
  local why
  if [ "$NOW" -eq 1 ]; then
    line_note "Skipped (--now)."
  else
    echo "  Looking at the storage drives for a few seconds..."
    why=$(busy_reason)
    if [ -n "$why" ]; then
      echo
      line_warn "Not now: $why."
      echo "      Wait for it to finish, then run  sudo homelab-update  again. The downloads are done, so it goes quickly."
      echo "      (Running it anyway: sudo homelab-update --now)"
      echo
      return 0
    fi
    line_ok "Nothing is being written to the storage pools."
  fi
  if [ "$FULL_BACKUP" -eq 1 ]; then
    echo
    echo "  Running the full backup first (--backup)..."
    BACKUP_WHEN=""
    if ! run_backup; then
      echo; line_bad "STOPPED: the backup did not finish OK, so nothing was updated."; echo; return 1
    fi
    line_ok "Backup finished OK at $BACKUP_WHEN."
  fi

  rule "Step 4 of 4 ${S_DOT} Update, one stack at a time"
  load_containers; build_images
  build_plan
  if [ "${#PLAN_STACKS[@]}" -eq 0 ]; then line_ok "Nothing is waiting any more."; echo; return 0; fi
  local n=0 s r updated=0 left=0
  for s in "${PLAN_STACKS[@]}"; do
    n=$((n + 1)); [ "$n" -gt 1 ] && echo
    print_stack "$n" "$s"
    echo
    if ! confirm "Update $s now?" "$yes"; then line_note "$s left as it is."; left=$((left + 1)); continue; fi
    if [ "$NOW" -eq 0 ] && [ "$n" -gt 1 ]; then
      why=$(busy_reason)
      if [ -n "$why" ]; then
        line_warn "Not now: $why. Stopped before $s. Run  sudo homelab-update  again when it is done."
        return 0
      fi
    fi
    r=0; update_stack "$s" "$yes" || r=$?
    case "$r" in
      0) updated=$((updated + 1)) ;;
      2) left=$((left + 1)) ;;
      *) echo; line_bad "Stopped at $s. The stacks after it were not touched."; echo; refresh_state; return 1 ;;
    esac
    # the containers changed: read them again so the next stack and the login screen see the truth
    refresh_state
  done
  echo
  line_ok "$updated stack(s) updated${left:+, $left left as they were}."
  echo "  ${D}When everything runs fine for a few days, free the disk space with:${N}  sudo homelab-update clean"
  echo
  return 0
}

refresh_state() {   # re-read the containers and save what is still waiting
  load_containers; build_images; read_state
  evaluate_state | write_outputs "$(summary_epoch || date +%s)"
}

held_note() {   # held_note COUNT: says how many leftover images stay because a container uses them
  [ "$1" -eq 0 ] || line_note "$1 leftover image(s) are kept because a container still uses them (a stopped one counts)."
}

cmd_clean() {   # cmd_clean YES OLD_ONLY
  need_root clean; take_lock loud
  local yes=$1 old_only=$2 tag size age d t now iid in_use i before after since lab all_ids held=0
  local -a tags=() tsizes=() tuse=() dids=() dsizes=() dinfo=()
  load_containers || die "Cannot talk to Docker. Is it running? (docker ps)"
  # every image that ANY container uses, stopped ones too (for example a spare kept from an old Portainer update)
  all_ids=" "
  local cids; cids=$(docker ps -aq 2>/dev/null)
  # shellcheck disable=SC2086
  [ -z "$cids" ] || all_ids+=$(docker inspect $cids --format '{{.Image}}' 2>/dev/null | tr '\n' ' ')
  now=$(date +%s)
  while read -r tag size; do
    [ -n "$tag" ] || continue
    if [ "$old_only" -eq 1 ]; then
      d=${tag##*-}
      [[ "$d" =~ ^[0-9]{8}$ ]] || continue
      t=$(date -d "$d" +%s 2>/dev/null) || continue
      age=$(( (now - t) / 86400 )); [ "$age" -ge "$ROLLBACK_KEEP_DAYS" ] || continue
    fi
    iid=$(docker image inspect -f '{{.Id}}' "homelab-rollback:$tag" 2>/dev/null)
    in_use=""; for i in "${!CD[@]}"; do [ "${CD[$i]}" = "$iid" ] && { in_use=${CN[$i]}; break; }; done
    tags+=("$tag"); tsizes+=("$size"); tuse+=("$in_use")
  done < <(docker image ls homelab-rollback --format '{{.Tag}} {{.Size}}' 2>/dev/null)
  if [ "$old_only" -eq 0 ]; then
    while IFS='|' read -r iid size since; do
      [ -n "$iid" ] || continue
      if [[ "$all_ids" == *" $iid "* ]]; then held=$((held + 1)); continue; fi
      lab=$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.title"}} {{index .Config.Labels "org.opencontainers.image.version"}}' "$iid" 2>/dev/null | sed 's/<no value>//g; s/^ *//; s/ *$//')
      dids+=("$iid"); dsizes+=("$size"); dinfo+=("$since${lab:+, $lab}")
    done < <(docker image ls --filter dangling=true --no-trunc --format '{{.ID}}|{{.Size}}|{{.CreatedSince}}' 2>/dev/null)
  fi

  if [ "$old_only" -eq 1 ]; then rule "Clean up saved copies older than $ROLLBACK_KEEP_DAYS days"; else rule "Clean up old versions"; fi
  if [ "${#tags[@]}" -eq 0 ] && [ "${#dids[@]}" -eq 0 ]; then
    line_ok "Nothing to clean."
    held_note "$held"
    echo; return 0
  fi

  if [ "${#tags[@]}" -gt 0 ]; then
    echo "  Saved copies of older versions (${#tags[@]})"
    for i in "${!tags[@]}"; do
      printf '   %s%s%s  homelab-rollback:%-34s %s\n' "$D" "$S_DOT" "$N" "${tags[$i]}" "${tsizes[$i]}"
      [ -z "${tuse[$i]}" ] || printf '      %sstill used by %s: only the saved name goes, the running program stays%s\n' "$D" "${tuse[$i]}" "$N"
    done
    echo
  fi
  if [ "${#dids[@]}" -gt 0 ]; then
    echo "  Leftover old images that no container uses (${#dids[@]})"
    for i in "${!dids[@]}"; do
      iid=${dids[$i]#sha256:}
      printf '   %s%s%s  %s  %8s  %s\n' "$D" "$S_DOT" "$N" "${iid:0:12}" "${dsizes[$i]}" "${dinfo[$i]}"
    done
    echo
  fi
  if [ "$held" -ne 0 ]; then held_note "$held"; echo; fi
  before=$(free_bytes)
  [ -z "$before" ] || echo "  Free space on the boot drive now: $(hb "$before")"
  echo "  A running container's image is never removed. After this you cannot go back to the old programs"
  echo "  without downloading them again."
  echo
  confirm "Delete these?" "$yes" || { echo; echo "  Nothing deleted."; echo; return 0; }
  local removed=0 in_use=0 other=0 msg first_err="" progress
  for tag in "${tags[@]}"; do
    if docker rmi "homelab-rollback:$tag" >/dev/null 2>&1; then removed=$((removed + 1)); else line_warn "could not remove homelab-rollback:$tag"; fi
  done
  # An image that other images are built on cannot go before them, so go in passes until nothing more can be removed.
  local -a pending=("${dids[@]}") nxt=()
  local -A errs=()
  while [ "${#pending[@]}" -gt 0 ]; do
    nxt=(); progress=0
    for iid in "${pending[@]}"; do
      if msg=$(docker image rm "$iid" 2>&1); then removed=$((removed + 1)); progress=1
      elif [[ "$msg" == *"No such image"* ]]; then removed=$((removed + 1)); progress=1   # Docker already removed it together with its child
      else nxt+=("$iid"); errs[$iid]=$msg; fi
    done
    pending=("${nxt[@]}")
    [ "$progress" -eq 1 ] || break
  done
  for iid in "${pending[@]}"; do
    case "${errs[$iid]}" in
      *"being used"*|*"in use"*) in_use=$((in_use + 1)) ;;
      *) other=$((other + 1)); [ -n "$first_err" ] || first_err=$(printf '%s' "${errs[$iid]}" | tail -n 1) ;;
    esac
  done
  line_ok "Removed $removed item(s)."
  [ "$in_use" -eq 0 ] || line_note "$in_use image(s) kept because a container uses them."
  [ "$other" -eq 0 ] || line_warn "$other image(s) could not be removed. Docker said: $first_err"
  after=$(free_bytes)
  [ -z "$before" ] || [ -z "$after" ] || line_ok "Free space on the boot drive: $(hb "$before") $S_ARR $(hb "$after")"
  echo
}

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; }

[ "${HLU_SOURCE_ONLY:-}" = 1 ] && return 0   # tests load the functions only
YES=0; OLD=0; NOW=0; FULL_BACKUP=0; ARGS=()
for a in "$@"; do case "$a" in --yes|-y) YES=1 ;; --old) OLD=1 ;; --now) NOW=1 ;; --backup) FULL_BACKUP=1 ;; *) ARGS+=("$a") ;; esac; done
case "${ARGS[0]:-run}" in
  version|--version) echo "homelab-update $VERSION" ;;
  help|--help|-h) usage ;;
  run) cmd_run "$YES" ;;
  check) cmd_check ;;
  list) cmd_list ;;
  clean) cmd_clean "$YES" "$OLD" ;;
  auto) cmd_auto ;;
  refresh) cmd_refresh ;;
  *) echo "Unknown option: ${ARGS[0]}" >&2; usage >&2; exit 1 ;;
esac
