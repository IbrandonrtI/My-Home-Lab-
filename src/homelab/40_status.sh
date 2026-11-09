human_bytes() { numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "$1 B"; }

# "in 11 h" / "in 40 min" for a number of seconds
in_words() {
  local s=$1
  if [ "$s" -ge 7200 ]; then echo "in $(( s / 3600 )) h"
  elif [ "$s" -ge 60 ]; then echo "in $(( s / 60 )) min"
  else echo "soon"; fi
}

# next_run MINUTE HOUR DAY MONTH WEEKDAY -> "06:00 (in 11 h)" for a daily line, or "see root's crontab"
next_run() {
  local m=$1 h=$2 dom=$3 mon=$4 dow=$5 t now hhmm
  if [[ "$m" =~ ^[0-9]+$ ]] && [[ "$h" =~ ^[0-9]+$ ]] && [ "$dom" = "*" ] && [ "$mon" = "*" ] && [ "$dow" = "*" ]; then
    now=$(date +%s); hhmm=$(printf '%02d:%02d' "$h" "$m")
    t=$(date -d "$hhmm" +%s 2>/dev/null) || { echo "see root's crontab"; return; }
    [ "$t" -gt "$now" ] || t=$(date -d "tomorrow $hhmm" +%s)
    printf '%s (%s)' "$hhmm" "$(in_words $(( t - now )))"
  else
    echo "see root's crontab"
  fi
}

# the file written by homelab-sample is "fresh" if its time stamp is recent
sample_age_min() {   # sample_age_min EPOCH -> minutes
  echo $(( ( $(date +%s) - $1 ) / 60 ))
}

backup_size_line() {
  local stamp result dest _s bytes m h dom mon dow _e text next=""
  [ -r "$LAST_RUN_FILE" ] || return 0
  IFS="|" read -r stamp result dest _s bytes <"$LAST_RUN_FILE"
  if [ -r "$STATE_DIR/schedule" ] && [ -s "$STATE_DIR/schedule" ]; then
    IFS='|' read -r m h dom mon dow _e <"$STATE_DIR/schedule"
    next="next run $(next_run "$m" "$h" "$dom" "$mon" "$dow")"
  fi
  if [[ "${bytes:-}" =~ ^[0-9]+$ ]]; then
    text="$(human_bytes "$bytes") in the backup"
  else
    text="size shows after the next backup run"
  fi
  [ -n "$next" ] && text="$text, $next"
  ok "Backup size" "$text"
}

# The name of a pool drive as "sudo drives status" shows it ("1 TB Samsung HDD"), not the label on the drive (MAIN2).
# The name you chose in /etc/homelab-drive-names wins, then the name "drives" saved. A name two drives share keeps the label too.
drive_shown_name() {   # drive_shown_name LABEL TEMPS-FILE
  local lab=$1 file=$2 name="" other n=0 names_file="${HOMELAB_NAMES_FILE:-/etc/homelab-drive-names}"
  case "$lab" in MAIN[0-9]*|BACKUP[0-9]*) ;; *) printf '%s' "$lab"; return 0 ;; esac
  [ -r "$names_file" ] && name=$(awk -F= -v k="$lab" '{ gsub(/^[ \t]+|[ \t]+$/, "", $1) } $1 == k && !/^[ \t]*#/ { sub(/^[^=]*=/, ""); print; exit }' "$names_file")
  [ -n "$name" ] || name=$(saved_drive_name "$lab")
  [ -n "$name" ] || { printf '%s' "$lab"; return 0; }
  while IFS='|' read -r other _; do
    [ "$other" = "$lab" ] && continue
    case "$other" in MAIN[0-9]*|BACKUP[0-9]*) [ "$(saved_drive_name "$other")" = "$name" ] && n=1 ;; esac
  done <"$file"
  if [ "$n" -eq 1 ]; then printf '%s (%s)' "$name" "$lab"; else printf '%s' "$name"; fi
}

saved_drive_name() {   # saved_drive_name LABEL -> the name "drives" saved for that drive, or nothing
  [ -r "$STATE_DIR/drive-names" ] && awk -F'|' -v k="$1" '$1 == k {print $2; exit}' "$STATE_DIR/drive-names"
  return 0
}

temps_line() {
  local f="$STATE_DIR/temps" label _d t ep parts="" max=0 oldest="" age
  if [ ! -e "$f" ]; then
    warn "Drive temps" "no readings yet (run: sudo homelab-sample, and add its cron line, see docs/maintenance.md)"
    return 0
  fi
  if [ ! -s "$f" ]; then
    warn "Drive temps" "no readings (is smartmontools installed? try: sudo homelab-sample)"
    suggest 6 "sudo homelab-sample" "take a drive temperature reading now"
    return 0
  fi
  while IFS="|" read -r label _d t ep; do
    [ -n "$label" ] || continue
    label=$(drive_shown_name "$label" "$f")
    if [ "$t" = "standby" ]; then parts="$parts$label asleep, "
    elif [[ "$t" =~ ^[0-9]+$ ]]; then
      parts="$parts$label ${t}°C, "
      [ "$t" -gt "$max" ] && max=$t
    fi
    if [[ "$ep" =~ ^[0-9]+$ ]] && { [ -z "$oldest" ] || [ "$ep" -lt "$oldest" ]; }; then oldest=$ep; fi
  done <"$f"
  parts=${parts%, }
  age=""
  [ -n "$oldest" ] && age=$(sample_age_min "$oldest")
  if [ "$max" -ge "$TEMP_BAD" ]; then bad "Drive temps" "$parts -> too hot, check the airflow"
  elif [ "$max" -ge "$TEMP_WARN" ]; then warn "Drive temps" "$parts -> getting warm"
  elif [ -n "$age" ] && [ "$age" -ge "$SAMPLE_STALE_MIN" ]; then warn "Drive temps" "$parts (readings are $age min old; take new ones: sudo homelab-sample)"
  else ok "Drive temps" "$parts"; fi
}

updates_line() {
  local n="" ep names="" img_n=0 text="" line
  [ -r "$STATE_DIR/apt" ] && IFS='|' read -r n ep <"$STATE_DIR/apt"
  if [ -r "$STATE_DIR/image-updates" ]; then
    names=$(tail -n +2 "$STATE_DIR/image-updates" | awk 'NF {printf "%s%s", (c++ ? ", " : ""), $1}')
    img_n=$(tail -n +2 "$STATE_DIR/image-updates" | awk 'NF' | wc -l)
  fi
  # the saved count is from the last reading (up to 6 hours ago). When apt ran since then (an upgrade, or an apt update that
  # found new lists) it is out of date, so count again now: a simulation that changes nothing and needs no sudo.
  if [[ "$n" =~ ^[0-9]+$ && "$ep" =~ ^[0-9]+$ ]] && [ "$JUST_BOOTED" != 1 ] && command -v apt-get >/dev/null 2>&1; then
    local m1 m2
    m1=$(stat -c %Y "${HOMELAB_DPKG_STATUS:-/var/lib/dpkg/status}" 2>/dev/null || echo 0)
    m2=$(stat -c %Y "${HOMELAB_APT_LISTS:-/var/lib/apt/lists}" 2>/dev/null || echo 0)
    if [ "$m1" -gt "$ep" ] || [ "$m2" -gt "$ep" ]; then n=$(timeout 8 apt-get -s upgrade 2>/dev/null | grep -c '^Inst ' || true); fi
  fi
  [[ "$n" =~ ^[0-9]+$ ]] || n=""
  [ -n "$n" ] || [ -r "$STATE_DIR/image-updates" ] || return 0
  if [ -n "$n" ]; then
    if [ "$n" -gt 0 ]; then text="$n system update(s)"; else text="system is up to date"; fi
  fi
  if [ -r "$STATE_DIR/image-updates" ]; then
    line=$(head -1 "$STATE_DIR/image-updates")
    if [ "$img_n" -gt 0 ]; then text="${text:+$text; }newer images: $names"
    else text="${text:+$text; }container images up to date"; fi
    [[ "$line" =~ ^[0-9]+$ ]] && text="$text (checked $(( ( $(date +%s) - line ) / 86400 )) d ago)"
  fi
  if [ "${n:-0}" -gt 0 ] || [ "$img_n" -gt 0 ]; then
    local fix=""
    [ "${n:-0}" -gt 0 ] && fix="install the system ones: sudo apt upgrade"
    [ "$img_n" -gt 0 ] && fix="${fix:+$fix; }update the containers: sudo homelab-update"
    warn "Updates" "$text -> $fix"
    [ "$img_n" -gt 0 ] && suggest 4 "sudo homelab-update" "newer container versions are waiting: it downloads and updates them"
    [ "${n:-0}" -gt 0 ] && suggest 5 "sudo apt update && sudo apt upgrade" "install the waiting system updates"
  else ok "Updates" "$text"; fi
}

pool_mounted() { command -v findmnt >/dev/null 2>&1 && findmnt -n "$1" >/dev/null 2>&1; }

pool_lines() {
  local used size
  # main pool
  if pool_mounted "$MAIN_POOL"; then
    read -r used size < <(df -h --output=used,size "$MAIN_POOL" 2>/dev/null | awk 'NR==2 {print $1, $2}')
    if only_boot_section MAIN; then
      warn "Main Pool" "mounted, ${used:-?} used of ${size:-?}, but only on a section of the boot drive (no separate drive: sudo drives)"
      suggest 3 "sudo drives" "the main pool is only a section of the boot drive: connect a real drive"
    else
      ok "Main Pool" "mounted, ${used:-?} used of ${size:-?}"
    fi
  elif [ -e "$STATE_DIR/no-data-drive" ]; then
    # written by homelab-setup while no data drive has been set up (or when you skipped that step): not a failure
    warn "Main Pool" "no data drive set up yet (when you have one: sudo drives)"
    suggest 5 "sudo drives" "connect a data drive (a menu; it asks before erasing anything)"
  else
    bad "Main Pool" "NOT MOUNTED -> plug the drive in, then run: sudo drives remount (drive dead? sudo drives replace)"
    suggest 1 "sudo drives remount" "the data drive is not mounted: remount it and restart the containers"
  fi

  # backup pool
  if pool_mounted "$BACKUP_POOL"; then
    if only_boot_section BACKUP; then
      warn "Backup Pool" "mounted, but only on a section of the boot drive (lost if that drive dies; fix: sudo drives connect)"
      suggest 4 "sudo drives" "connect a real backup drive: the backup is on the boot drive now"
    else
      ok "Backup Pool" "mounted"
    fi
  else
    warn "Backup Pool" "not connected, so the backup goes to the boot drive (connect a drive: sudo drives connect)"
    suggest 5 "sudo drives" "connect a backup drive (or use part of the boot drive: sudo drives bootsection)"
  fi
}

last_backup_line() {
  local stamp result age_h ts line
  if [ -r "$LAST_RUN_FILE" ]; then
    IFS='|' read -r stamp result _ _ <"$LAST_RUN_FILE"
    ts=$(date -d "$stamp" +%s 2>/dev/null || echo "")
    age_h=""
    [ -n "$ts" ] && age_h=$(( ($(date +%s) - ts) / 3600 ))
    line="$stamp  $result"
    [ -n "$age_h" ] && line="$line  (${age_h} h ago)"
    if [ "$result" != "OK" ]; then
      bad "Last backup" "$line -> read: sudo tail -20 /var/log/homelab-backup.log"
      suggest 1 "sudo tail -20 /var/log/homelab-backup.log" "the last backup failed: read why"
    elif [ -n "$age_h" ] && [ "$age_h" -ge "$STALE_HOURS" ]; then
      warn "Last backup" "$line -> older than ${STALE_HOURS} h (run one now: sudo homelab-backup)"
      suggest 3 "sudo homelab-backup" "the last backup is old: run one now"
    else
      ok "Last backup" "$line"
    fi
  elif [ -e "$(dirname "$LAST_RUN_FILE")" ]; then
    warn "Last backup" "no result found (check: sudo drives status)"
    suggest 3 "sudo drives status" "no backup result was found: check the backup"
  else
    warn "Last backup" "no backup has run yet (run the first one: sudo homelab-backup)"
    suggest 4 "sudo homelab-backup" "no backup has run yet: run the first one now"
  fi
}

# containers (a stopped container whose restart policy is "no" was stopped on purpose, so it is ignored)
containers_line() {
  local n_run=0 n_all=0 down="" unhealthy cname cstate cpol crc cstart restarted="" st_ts now
  if [ "$JUST_BOOTED" -eq 1 ]; then
    # first minutes after a boot: Docker is busy starting the apps, so the login screen leaves it alone
    warn "Containers" "the server just started and the apps are still starting (live check in a few minutes: homelab status)"
  elif command -v docker >/dev/null 2>&1 && timeout 5 docker info >/dev/null 2>&1; then
    now=$(date +%s)
    while read -r cname cstate cpol crc cstart; do
      [ -n "$cname" ] || continue
      cname=${cname#/}
      if [[ "${crc:-0}" =~ ^[0-9]+$ ]] && [ "${crc:-0}" -gt 0 ] && [ "$cstate" = "running" ]; then
        st_ts=$(date -d "$cstart" +%s 2>/dev/null || echo 0)
        [ $(( now - st_ts )) -lt 86400 ] && restarted="$restarted$cname (${crc}x), "
      fi
      if [ "$cstate" = "running" ]; then
        n_run=$((n_run + 1)); n_all=$((n_all + 1))
      elif [ -n "$cpol" ] && [ "$cpol" != "no" ]; then
        n_all=$((n_all + 1)); down="$down$cname "
      fi
    done < <(timeout 10 docker ps -aq 2>/dev/null | xargs -r timeout 10 docker inspect --format '{{.Name}} {{.State.Status}} {{.HostConfig.RestartPolicy.Name}} {{.RestartCount}} {{.State.StartedAt}}' 2>/dev/null)
    unhealthy=$(timeout 5 docker ps --filter health=unhealthy --format '{{.Names}}' 2>/dev/null | tr '\n' ' ')
    if [ -n "$down" ]; then
      bad "Containers" "${n_run} of ${n_all} running; not running: ${down% } (see: docker ps -a)"
      suggest 1 "docker ps -a" "a container is not running: see which one"
    elif [ -n "$unhealthy" ]; then
      warn "Containers" "${n_run} of ${n_all} running; unhealthy: ${unhealthy% } (read: docker logs --tail 50 NAME)"
      suggest 2 "docker logs --tail 50 NAME" "a container is unhealthy: read what it printed"
    else
      ok "Containers" "${n_run} of ${n_all} running"
    fi
    [ -n "$restarted" ] && warn "Restarts" "Docker restarted in the last 24 h: ${restarted%, } (why: docker logs --tail 50 NAME)"
  else
    case "$(systemctl is-active docker 2>/dev/null)" in
      activating) warn "Containers" "Docker is still starting after the restart. Wait a minute, then run  homelab  again" ;;
      inactive|failed) warn "Containers" "Docker is not running. Start it with:  sudo systemctl start docker" ;;
      *) if [ "$(id -u)" != 0 ] && getent group docker 2>/dev/null | cut -d: -f4 | tr ',' '\n' | grep -qx "$(id -un)" && ! id -nG | tr ' ' '\n' | grep -qx docker; then
           warn "Containers" "this terminal has not picked up your Docker access yet. Log out and back in (or run: newgrp docker), or use: sudo homelab"
         else
           warn "Containers" "cannot read Docker (is Docker running, and are you in the docker group?)"
         fi ;;
    esac
  fi
}

boot_drive_line() {
  local line sec_dir="${HOMELAB_BOOT_SECTION_DIR:-/var/lib/homelab-boot-sections}" sec_gb="" f free_b
  line=$(df -h --output=pcent,avail / 2>/dev/null | awk 'NR==2 {print $1 " used, " $2 " free"}')
  for f in "$sec_dir"/*.img; do [ -f "$f" ] && sec_gb="$sec_gb $(( $(stat -c %s "$f") / 1000000000 ))"; done
  if [ -n "$sec_gb" ]; then
    line="$line; sections for pools:$(printf '%s' "$sec_gb" | sed 's/ \([0-9]*\)/ \1 GB,/g; s/,$//')"
    free_b=$(df -B1 --output=avail / 2>/dev/null | awk 'NR==2 {print $1}')
    if [ -n "$free_b" ] && [ "$free_b" -lt 128000000000 ]; then
      warn "Boot drive" "$line -> under 128 GB free; free some space (sudo drives status)"
      suggest 2 "sudo drives status" "the boot drive is getting full and a pool uses part of it"
      return 0
    fi
  fi
  [ -n "$line" ] && ok "Boot drive" "$line"
  return 0
}

cards_line() {   # the cards homelab-cards made for new services (it writes the summary; a section it was unsure about is asked for)
  local f="$STATE_DIR/cards-summary" names="" unsure="" kind name _c _s uns _a n=0
  [ -r "$f" ] || return 0
  while IFS='|' read -r kind name _c _s uns _a; do
    [ "$kind" = managed ] || continue
    n=$((n + 1)); names="$names$name, "
    [ "$uns" = 1 ] && unsure="$unsure$name "
  done <"$f"
  [ "$n" -gt 0 ] || return 0
  if [ -n "$unsure" ]; then
    warn "Service cards" "$n added by themselves (${names%, }); not sure of the section for: ${unsure% }"
    suggest 3 "sudo homelab-cards move ${unsure%% *} SECTION" "put its dashboard card in the right section"
  else
    ok "Service cards" "$n added by themselves: ${names%, }"
  fi
}

status() {
  pool_lines
  last_backup_line
  backup_size_line
  temps_line
  updates_line
  containers_line
  cards_line
  boot_drive_line
}

