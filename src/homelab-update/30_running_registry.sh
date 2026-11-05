# ---------- what is running ----------
CX=(); CN=(); CI=(); CD=(); CS=()      # container id, name, image name, image id, stack
load_containers() {
  CX=(); CN=(); CI=(); CD=(); CS=()
  local ids cid name img imgid stack
  ids=$(docker ps -q 2>/dev/null) || return 1
  [ -n "$ids" ] || return 0
  # shellcheck disable=SC2086
  while IFS='|' read -r cid name img imgid stack; do
    [ -n "$cid" ] || continue
    name=${name#/}
    [ "$stack" = "<no value>" ] && stack=""   # Docker prints this for a container that is not part of a Compose stack
    CX+=("$cid"); CN+=("$name"); CI+=("$img"); CD+=("$imgid"); CS+=("${stack:-$name}")
  done < <(docker inspect $ids --format '{{.Id}}|{{.Name}}|{{.Config.Image}}|{{.Image}}|{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null)
  return 0
}

is_held() {   # is_held NAME IMAGE
  local n=$1 img=$2 h
  [[ "$img" == *@sha256:* || "$img" == sha256:* ]] && return 0
  for h in "${HOLD[@]}"; do [ "$h" = "$n" ] && return 0; done
  return 1
}

IMG_LIST=(); declare -A IMG_STACKS=(); HELD_LIST=(); PINNED_LIST=()
build_images() {
  IMG_LIST=(); IMG_STACKS=(); HELD_LIST=(); PINNED_LIST=()
  local i img stack s found
  for i in "${!CN[@]}"; do
    img=${CI[$i]}; stack=${CS[$i]}
    if is_held "${CN[$i]}" "$img"; then HELD_LIST+=("${CN[$i]}"); continue; fi
    if [ -z "${IMG_STACKS[$img]+x}" ]; then IMG_LIST+=("$img"); IMG_STACKS[$img]="$stack"
    else
      found=0; for s in ${IMG_STACKS[$img]//,/ }; do [ "$s" = "$stack" ] && found=1; done
      [ "$found" -eq 1 ] || IMG_STACKS[$img]="${IMG_STACKS[$img]},$stack"
    fi
    if [[ "$img" =~ :v?[0-9]+(\.[0-9]+){2,}$ ]]; then PINNED_LIST+=("${CN[$i]} ($img)"); fi
  done
}

# ---------- asking the registry, and comparing ----------
remote_digest() {   # remote_digest IMAGE -> prints the fingerprint of the newest image online
  local out d
  out=$(timeout "$REGISTRY_TIMEOUT" docker buildx imagetools inspect "$1" 2>/dev/null) || return 1
  d=$(printf '%s\n' "$out" | awk '/^Digest:/ {print $2; exit}')
  [[ "$d" == sha256:* ]] || return 1
  printf '%s\n' "$d"
}

local_has() {   # local_has IMAGE DIGEST: is that exact version already downloaded?
  docker image inspect -f '{{range .RepoDigests}}{{println .}}{{end}}' "$1" 2>/dev/null | grep -qF -- "@$2"
}

pull_ref() {   # pull_ref IMAGE DIGEST -> what to download: the image itself, or the newer version tag found for it
  if [[ "$2" == tag=* ]]; then printf '%s:%s\n' "${1%:*}" "${2#tag=}"; else printf '%s\n' "$1"; fi
}

classify() {   # classify IMAGE DIGEST -> new (not downloaded) | downloaded (downloaded, container still old) | current
  local ref=$1 d=$2 tagid i running=0
  if [[ "$d" == tag=* ]]; then   # a newer version number was found (v2.6.0 -> v2.7.0)
    for i in "${!CI[@]}"; do [ "${CI[$i]}" = "$ref" ] && running=1; done
    [ "$running" -eq 1 ] || { echo current; return; }          # no container runs the old version any more
    if docker image inspect "$(pull_ref "$ref" "$d")" >/dev/null 2>&1; then echo downloaded; else echo new; fi
    return
  fi
  local_has "$ref" "$d" || { echo new; return; }
  tagid=$(docker image inspect -f '{{.Id}}' "$ref" 2>/dev/null)
  for i in "${!CI[@]}"; do
    [ "${CI[$i]}" = "$ref" ] || continue
    is_held "${CN[$i]}" "$ref" && continue
    [ "${CD[$i]}" = "$tagid" ] || { echo downloaded; return; }
  done
  echo current
}

