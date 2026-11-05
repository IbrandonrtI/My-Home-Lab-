# ---------- the plan ----------
rank_of() {
  case "${1,,}" in
    adguard*) echo 2 ;; immich*) echo 3 ;; nextcloud*) echo 4 ;; portainer*) echo 5 ;; *) echo 1 ;;
  esac
}

img_version() {
  local v
  v=$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' "$1" 2>/dev/null)
  [ "$v" = "<no value>" ] && v=""   # Docker prints this when the image has no version label
  printf '%s' "$v"
}

nc_version_of() { sed -n "s/.*OC_VersionString *= *'\([^']*\)'.*/\1/p" | head -1; }

warn_block() {   # warn_block "text..." : a yellow ! line that wraps under itself
  local first=1 l w text="$*"
  w=$(( $(term_cols) - 14 )); [ "$w" -gt 90 ] && w=90
  while IFS= read -r l; do
    if [ "$first" -eq 1 ]; then printf '      %s%s%s  %s\n' "$Y" "$S_WARN" "$N" "$l"; first=0
    else printf '         %s\n' "$l"; fi
  done < <(printf '%s\n' "$text" | fold -s -w "$w")
}

PLAN_STACKS=(); declare -A SIMG=() SST=() SNT=()      # the stacks waiting, their images, each image's status, each image's newer version
build_plan() {   # reads the saved state and fills PLAN_STACKS (in the order to update) / SIMG / SST / SNT
  local line stacks img dig at st s
  PLAN_STACKS=(); SIMG=(); SST=(); SNT=()
  read_state
  local -a seen=()
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    IFS='|' read -r stacks img dig at st <<<"$line"
    for s in ${stacks//,/ }; do
      if [ -z "${SIMG[$s]+x}" ]; then seen+=("$s"); SIMG[$s]="$img"; else SIMG[$s]+=" $img"; fi
      SST["$s|$img"]=$st
      [[ "$dig" == tag=* ]] && SNT["$s|$img"]=${dig#tag=}
    done
  done < <(evaluate_state)
  [ "${#seen[@]}" -eq 0 ] && return 0
  local sorted
  sorted=$(for s in "${seen[@]}"; do printf '%s %s\n' "$(rank_of "$s")" "$s"; done | sort -k1,1n -k2,2 | awk '{print $2}')
  while IFS= read -r s; do [ -n "$s" ] && PLAN_STACKS+=("$s"); done <<<"$sorted"
}

print_stack() {   # print_stack N STACK: what is waiting in one stack, with the notes that matter
  local n=$1 s=$2 img any_new=0 oldid newv oldv m i
  for img in ${SIMG[$s]}; do [ "${SST["$s|$img"]}" = new ] && any_new=1; done
  if [ "$any_new" -eq 1 ]; then
    printf '   %s%d%s  %s%s%s   %s[not downloaded yet]%s\n' "$C" "$n" "$N" "$B" "$s" "$N" "$Y" "$N"
  else
    printf '   %s%d%s  %s%s%s\n' "$C" "$n" "$N" "$B" "$s" "$N"
  fi
  for img in ${SIMG[$s]}; do
    kv image "$img"
    if [ -n "${SNT["$s|$img"]:-}" ]; then
      kv version "${img##*:} $S_ARR ${SNT["$s|$img"]}"
      continue
    fi
    [ "${SST["$s|$img"]}" = new ] && continue
    oldid=$(running_id_of "$img")
    newv=$(img_version "$img"); oldv=""; [ -n "$oldid" ] && oldv=$(img_version "$oldid")
    if [ -n "$newv" ] && [ -n "$oldv" ] && [ "$newv" != "$oldv" ]; then kv version "$oldv $S_ARR $newv"; fi
  done
  for i in "${!CN[@]}"; do
    [ "${CS[$i]}" = "$s" ] || continue
    m=$(anon_volumes_of "${CX[$i]}")
    if [ -n "$m" ]; then
      warn_block "WARNING: ${CN[$i]} keeps data in an anonymous volume ($(echo "$m" | paste -sd, -))." \
        "Updating can leave it EMPTY (see B6 in docs/troubleshooting.md), so it is NOT updated here. Copy that data out first."
    fi
  done
  case "${s,,}" in
    adguard*) kv note "This is your DNS server. DNS is down for a few seconds while it restarts, so pick a quiet moment." ;;
    immich*)
      kv note "Read the release notes first: https://github.com/immich-app/immich/releases"
      kv "" "A quick dump of its database is made right before. Do it alone, not together with Nextcloud." ;;
    nextcloud*) nextcloud_notes "$s" ;;
    portainer*)
      kv note "Portainer is recreated from the terminal (it is not a stack). Its page and the Homepage card are down for a minute." ;;
  esac
}

anon_volumes_of() {   # anon_volumes_of CONTAINER: the paths kept in anonymous volumes (a 64-character name)
  docker inspect "$1" --format '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}} {{.Destination}}{{println}}{{end}}{{end}}' 2>/dev/null | awk '$1 ~ /^[0-9a-f]{64}$/ {print $2}'
}

print_plan() {   # for "list": every waiting stack, in order
  build_plan
  if [ "${#PLAN_STACKS[@]}" -eq 0 ]; then line_ok "Nothing is waiting: every container runs the newest image."; return 0; fi
  local n=0 todl=0 s img
  echo "  Update these one at a time, in this order. The riskier ones are last."
  echo
  for s in "${PLAN_STACKS[@]}"; do
    n=$((n + 1)); [ "$n" -gt 1 ] && echo
    for img in ${SIMG[$s]}; do [ "${SST["$s|$img"]}" = new ] && { todl=$((todl + 1)); break; }; done
    print_stack "$n" "$s"
  done
  [ "$todl" -eq 0 ] || { echo; line_warn "Stacks marked [not downloaded yet]: run  sudo homelab-update  first."; }
  echo
  echo "  ${D}To update them, run:${N}  sudo homelab-update   ${D}(it downloads, then asks before each stack)${N}"
  echo "  ${D}Going back:${N} the old version of each image is saved as homelab-rollback:<name>-<date>."
  echo "  ${D}When everything runs fine, free the disk space with:${N}  sudo homelab-update clean"
}

nc_versions() {   # nc_versions STACK -> "OLD NEW" Nextcloud version numbers (the running one and the downloaded one), or nothing
  local s=$1 i name="" ref="" old new
  for i in "${!CS[@]}"; do
    if [ "${CS[$i]}" = "$s" ] && [[ "${CI[$i]}" == nextcloud:* || "${CI[$i]}" == nextcloud ]]; then
      if [ -z "$name" ] || [ "${CN[$i]}" = nextcloud ]; then name=${CN[$i]}; ref=${CI[$i]}; fi
    fi
  done
  [ -n "$name" ] || return 0
  [ "${SST["$s|$ref"]:-}" = downloaded ] || return 0
  old=$(docker exec "$name" cat /var/www/html/version.php 2>/dev/null | nc_version_of)
  new=$(docker run --rm --network none --entrypoint cat "$ref" /usr/src/nextcloud/version.php 2>/dev/null | nc_version_of)
  [ -n "$old" ] && [ -n "$new" ] && printf '%s %s\n' "$old" "$new"
  return 0
}

nc_jump() {   # nc_jump OLD NEW -> skip (more than one major version) | major | same | minor
  local om=${1%%.*} nm=${2%%.*}
  [[ "$om" =~ ^[0-9]+$ && "$nm" =~ ^[0-9]+$ ]] || { echo minor; return; }
  if [ "$nm" -gt $((om + 1)) ]; then echo skip
  elif [ "$nm" -gt "$om" ]; then echo major
  elif [ "$1" = "$2" ]; then echo same
  else echo minor; fi
}

nextcloud_notes() {   # nextcloud_notes STACK   (uses SST from build_plan)
  local s=$1 old new
  if read -r old new < <(nc_versions "$s") && [ -n "${new:-}" ]; then
    case "$(nc_jump "$old" "$new")" in
      skip) warn_block "STOP: Nextcloud would jump from $old to $new and skip a major version. It is NOT updated here." \
              "Nextcloud can only go up one major version at a time. Read the Nextcloud section of docs/updating.md first." ;;
      major) warn_block "MAJOR upgrade: $old $S_ARR $new. Read the release notes and the Nextcloud section of docs/updating.md first;" \
              "check that your apps support it. It is only done when you type yes yourself (not with --yes)." ;;
      same) kv version "$old (same number, rebuilt image)" ;;
      *) kv version "$old $S_ARR $new" ;;
    esac
  else
    local img
    for img in ${SIMG[$s]}; do
      [ "${SST["$s|$img"]:-}" = new ] && { kv note "The version change is shown after the image is downloaded."; break; }
    done
  fi
  kv note "A quick dump of its database is made right before. Do it alone, not together with Immich. Never skip a major version."
}

