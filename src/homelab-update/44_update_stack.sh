# ---------- updating one stack ----------
wait_stack() {   # wait_stack STACK: wait until every container of the stack runs again (and is healthy). 0 = yes
  local s=$1 i c st h deadline ok bad_names
  deadline=$(( $(date +%s) + ${HLU_WAIT:-300} ))
  while :; do
    ok=1; bad_names=""
    while IFS= read -r c; do
      [ -n "$c" ] || continue
      read -r st h < <(docker inspect "$c" --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null)
      if [ "$st" != running ] || { [ "$h" != none ] && [ "$h" != healthy ]; }; then ok=0; bad_names="$bad_names$c "; fi
    done < <(docker ps -a --filter "label=com.docker.compose.project=$s" --format '{{.Names}}' 2>/dev/null)
    [ "$ok" -eq 1 ] && return 0
    [ "$(date +%s)" -ge "$deadline" ] && { WAIT_BAD=${bad_names% }; return 1; }
    sleep "${HLU_WAIT_EVERY:-5}"
  done
}

manual_steps() {   # manual_steps STACK WHY
  line_warn "$2"
  echo "      Do it by hand in Portainer: Stacks ${S_ARR} $1 ${S_ARR} Editor ${S_ARR} (change the version on the image: line if one is listed above)"
  echo "      ${S_ARR} Update the stack. Then check:  docker ps --format \"table {{.Names}}\\t{{.Status}}\""
}

update_portainer() {   # recreate the Portainer container itself from the terminal (it is not a stack)
  local img="" i restart ports mounts args old="portainer-before-update"
  for i in "${!CN[@]}"; do [ "${CN[$i]}" = portainer ] && img=${CI[$i]}; done
  [ -n "$img" ] || { line_bad "No container named portainer is running."; return 1; }
  restart=$(docker inspect portainer --format '{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null); restart=${restart:-always}
  ports=$(docker inspect portainer --format '{{range $p, $b := .HostConfig.PortBindings}}{{range $b}}-p {{.HostPort}}:{{$p}} {{end}}{{end}}' 2>/dev/null)
  mounts=$(docker inspect portainer --format '{{range .Mounts}}{{if eq .Type "volume"}}-v {{.Name}}:{{.Destination}} {{else if eq .Type "bind"}}-v {{.Source}}:{{.Destination}}{{if not .RW}}:ro{{end}} {{end}}{{end}}' 2>/dev/null)
  args=$(docker inspect portainer --format '{{range .Args}}{{.}} {{end}}' 2>/dev/null)
  docker rm -f "$old" >/dev/null 2>&1
  docker stop portainer >/dev/null 2>&1 || { line_bad "Could not stop Portainer."; return 1; }
  docker rename portainer "$old" >/dev/null 2>&1
  # shellcheck disable=SC2086
  if docker run -d --name portainer --restart="$restart" $ports $mounts "$img" ${args:-} >/dev/null 2>&1 \
     && wait_http "${HLU_PORTAINER:-http://127.0.0.1:9000}/api/status" "${HLU_WAIT:-120}"; then
    docker rm "$old" >/dev/null 2>&1
    return 0
  fi
  line_bad "The new Portainer did not start. Putting the old one back."
  docker rm -f portainer >/dev/null 2>&1
  docker rename "$old" portainer >/dev/null 2>&1
  docker start portainer >/dev/null 2>&1
  return 1
}

wait_http() {   # wait_http URL SECONDS: wait until the address answers 200
  local url=$1 deadline=$(( $(date +%s) + $2 ))
  until curl -fsS -m 5 -o /dev/null "$url" 2>/dev/null; do
    [ "$(date +%s)" -ge "$deadline" ] && return 1
    sleep "${HLU_WAIT_EVERY:-5}"
  done
}

update_stack() {   # update_stack STACK YES(0/1) -> 0 updated, 1 failed (stop here), 2 left for you (nothing was changed)
  local s=$1 yes=$2 img nt pairs=() old_ids="" i c v old new
  for img in ${SIMG[$s]}; do
    if [ "${SST["$s|$img"]}" = new ]; then manual_steps "$s" "$s was not downloaded yet: run  sudo homelab-update  again first."; return 2; fi
    nt=${SNT["$s|$img"]:-}
    [ -n "$nt" ] && pairs+=("$img" "${img%:*}:$nt")
  done
  # data in an anonymous volume can be lost when the container is recreated
  for i in "${!CN[@]}"; do
    [ "${CS[$i]}" = "$s" ] || continue
    v=$(anon_volumes_of "${CX[$i]}")
    if [ -n "$v" ]; then manual_steps "$s" "${CN[$i]} keeps data in an anonymous volume, so it is not updated here (B6 in docs/troubleshooting.md). Copy that data out first."; return 2; fi
  done
  case "${s,,}" in
    nextcloud*)
      if read -r old new < <(nc_versions "$s") && [ -n "${new:-}" ]; then
        case "$(nc_jump "$old" "$new")" in
          skip) line_bad "Nextcloud would skip a major version ($old $S_ARR $new). Not updated. Read docs/updating.md."; return 2 ;;
          major)
            if [ "$yes" -eq 1 ]; then line_warn "Nextcloud $old $S_ARR $new is a MAJOR upgrade. It is left for you: run  sudo homelab-update  without --yes."; return 2; fi
            confirm "This is a MAJOR Nextcloud upgrade ($old $S_ARR $new). Did you read the release notes and check your apps? Continue?" 0 || { line_note "Nextcloud left as it is."; return 2; } ;;
        esac
      fi ;;
  esac
  case "${s,,}" in
    nextcloud*|immich*) echo "      Quick database dump first..."; dump_stack_db "$s" || return 1 ;;
  esac
  for i in "${!CN[@]}"; do [ "${CS[$i]}" = "$s" ] && old_ids="$old_ids${CN[$i]}=${CD[$i]} "; done
  if [ "${s,,}" = portainer ]; then
    echo "      Recreating Portainer..."
    update_portainer || return 1
  else
    local why
    if ! why=$(pylib pt-has "$s" 2>&1); then manual_steps "$s" "Portainer could not be asked ($why)."; return 2; fi
    if [ "$why" != yes ]; then manual_steps "$s" "Portainer has no stack named '$s' (it was not made with Portainer)."; return 2; fi
    echo "      Updating the stack through Portainer..."
    if ! why=$(pylib pt-update "$s" "${pairs[@]}" 2>&1); then
      line_bad "Portainer did not update '$s': $why"
      echo "      Nothing else was changed. You can do it by hand in Portainer (Stacks ${S_ARR} $s ${S_ARR} Update the stack)."
      return 1
    fi
  fi
  WAIT_BAD=""
  echo "      Waiting for the containers to come back (up to 5 minutes)..."
  if ! wait_stack "$s"; then
    line_bad "$s is not healthy yet: ${WAIT_BAD:-unknown}. Look:  docker ps -a   and   docker logs --tail 50 NAME"
    echo "      Going back: the old version of each image is saved as homelab-rollback:<name>-<date> (docs/updating.md)."
    return 1
  fi
  # did the containers really change? Portainer can answer before Docker has recreated them, so give it a little time.
  # Only a container whose image tag now points to a NEWER image is expected to change (a database that did not get a new version stays as it is).
  local settle_end waiting name oldid cur
  settle_end=$(( $(date +%s) + ${HLU_SETTLE:-90} ))
  while :; do
    load_containers
    waiting=""
    for c in $old_ids; do
      name=${c%%=*}; oldid=${c#*=}
      for i in "${!CN[@]}"; do
        [ "${CN[$i]}" = "$name" ] && [ "${CD[$i]}" = "$oldid" ] || continue
        cur=$(docker image inspect -f '{{.Id}}' "${CI[$i]}" 2>/dev/null)
        if [ -n "$cur" ] && [ "$cur" != "$oldid" ]; then waiting="$waiting$name "; fi
      done
    done
    [ -z "$waiting" ] && break
    [ "$(date +%s)" -ge "$settle_end" ] && break
    sleep "${HLU_WAIT_EVERY:-5}"
  done
  for name in $waiting; do line_warn "$name still runs the old image (Docker found nothing to change)."; done
  line_ok "$s is updated and running."
  return 0
}

