running_id_of() {
  local i
  for i in "${!CI[@]}"; do [ "${CI[$i]}" = "$1" ] && { echo "${CD[$i]}"; return; }; done
}

rollback_tag() {
  local ref=$1 id safe
  id=$(running_id_of "$ref")
  [ -n "$id" ] || return 0
  safe=$(printf '%s' "${ref##*/}" | sed 's/[^A-Za-z0-9_.-]/-/g')
  docker tag "$id" "homelab-rollback:${safe}-$(date +%Y%m%d)" >/dev/null 2>&1 || true
}

docker_root() { local r; r=$(docker info -f '{{.DockerRootDir}}' 2>/dev/null); echo "${r:-/var/lib/docker}"; }
avail_of() {
  df -B"$1" --output=avail "$2" 2>/dev/null | awk 'NR==2 {gsub(/[^0-9]/, "", $1); print $1}'
}
free_gb() {
  [ -n "${HLU_FREE_GB:-}" ] && { echo "$HLU_FREE_GB"; return; }
  avail_of 1G "$(docker_root)"
}
free_bytes() { avail_of 1 "$(docker_root)"; }

run_backup() {
  local start start_min last ts res
  start=$(date +%s); start_min=$(date -d "@$start" '+%F %H:%M')
  "$BACKUP_CMD"; local rc=$?
  last=$(cat "$BACKUP_STATUS" 2>/dev/null)
  IFS='|' read -r ts res _ <<<"$last"
  if [ "$rc" -ne 0 ]; then line_bad "The backup reported a problem ($res)."; return 1; fi
  if [[ -z "$ts" || ( "$ts" < "$start_min" ) ]]; then
    line_bad "The backup did not run: probably another backup was already running (the 6:00 one?)."
    echo "      Wait for it (sudo tail -f /var/log/homelab-backup.log shows 'finished'), then run homelab-update again."
    return 1
  fi
  [[ "$res" == OK* ]] || { line_bad "The backup finished with a problem: $res"; return 1; }
  BACKUP_WHEN=$ts
  return 0
}

