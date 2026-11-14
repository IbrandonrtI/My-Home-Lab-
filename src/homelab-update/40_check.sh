CHECK_NEW=(); CHECK_DL=(); CHECK_FAILED=(); CHECK_OK=0
declare -A NEWTAG=()
TAG_UNSURE=()
# do_check show(0/1): look online for newer images of every running container and save the result.
do_check() {
  local show=$1 img d st n=0 now line stacks i nt
  CHECK_NEW=(); CHECK_DL=(); CHECK_FAILED=(); CHECK_OK=0; NEWTAG=(); TAG_UNSURE=()
  now=$(date +%s)
  mkdir -p "$STATE_DIR" && echo "$now" | put image-check-attempt
  load_containers || die "Cannot talk to Docker. Is it running? (docker ps)"
  build_images
  read_state
  local -A STAT=()
  local new_lines=""
  for img in "${IMG_LIST[@]}"; do
    n=$((n + 1))
    if d=$(remote_digest "$img"); then
      if [[ "$img" =~ :v?[0-9]+(\.[0-9]+)+$ ]]; then
        if nt=$(pylib tags "$img" 2>/dev/null); then
          if [ -n "$nt" ]; then d="tag=$nt"; NEWTAG[$img]=$nt; fi
        else
          TAG_UNSURE+=("$img")
        fi
      fi
      st=$(classify "$img" "$d"); STAT[$img]=$st
      case "$st" in
        new) CHECK_NEW+=("$img") ;;
        downloaded) CHECK_DL+=("$img") ;;
      esac
      [ "$st" = current ] || new_lines+="${IMG_STACKS[$img]}|$img|$d|$now|$st"$'\n'
    else
      CHECK_FAILED+=("$img"); STAT[$img]=failed
      for line in "${OLD_STATE[@]}"; do
        IFS='|' read -r stacks i d _ <<<"$line"
        if [ "$i" = "$img" ]; then
          st=$(classify "$img" "$d")
          [ "$st" = current ] || new_lines+="${IMG_STACKS[$img]}|$img|$d|$(echo "$line" | cut -d'|' -f4)|$st"$'\n'
        fi
      done
    fi
  done
  CHECK_OK=$((n - ${#CHECK_FAILED[@]}))

  if [ "$show" -eq 1 ]; then
    local prev=""
    for img in "${IMG_LIST[@]}"; do
      local who=${IMG_STACKS[$img]//,/+} short=${img##*/}
      if [ "$who" = "$prev" ]; then who=""; else prev=$who; fi
      case "${STAT[$img]}" in
        new)        img_row "$Y" "$S_UP"   "$who" "$short" "newer ${NEWTAG[$img]:+version ${NEWTAG[$img]} }online" ;;
        downloaded) img_row "$C" "$S_PEND" "$who" "$short" "${NEWTAG[$img]:+${NEWTAG[$img]} }downloaded, not updated yet" ;;
        failed)     img_row "$R" "$S_BAD"  "$who" "$short" "could not check" ;;
        *)          img_row "$G" "$S_OK"   "$who" "$short" "up to date" ;;
      esac
    done
    echo
    [ "${#HELD_LIST[@]}" -eq 0 ] || line_note "Left alone on purpose (locked to an exact version): ${HELD_LIST[*]}"
    [ "${#TAG_UNSURE[@]}" -eq 0 ] || line_note "Pinned to an exact version, and its newer versions could not be looked up (check by hand): ${TAG_UNSURE[*]##*/}"
  fi

  if [ "${#CHECK_FAILED[@]}" -eq 0 ]; then
    printf '%s' "$new_lines" | write_outputs "$now" || die "Cannot write to $STATE_DIR"
    return 0
  fi
  [ "$show" -eq 1 ] && line_bad "Could not reach the registry for ${#CHECK_FAILED[@]} image(s). Is the internet working? The saved result was only partly updated."
  local ep; ep=$(summary_epoch) || ep=""
  if [ -n "$ep" ] && [ "$CHECK_OK" -gt 0 ]; then printf '%s' "$new_lines" | write_outputs "$ep" || true; fi
  return 2
}

