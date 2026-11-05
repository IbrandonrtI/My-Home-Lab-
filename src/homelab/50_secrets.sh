# ---------- secrets ----------
# Shows which secrets a rebuild needs and checks what the server can confirm.
# It NEVER prints a value: only "set", a length, or a yes/no.
real_home() {   # home folder of the person who runs it (also under sudo)
  if [ -n "${HOMELAB_HOME:-}" ]; then echo "$HOMELAB_HOME"; return; fi
  if [ -n "${SUDO_USER:-}" ]; then getent passwd "$SUDO_USER" | cut -d: -f6; else echo "$HOME"; fi
}

dk() { timeout 10 docker "$@" 2>/dev/null; }
container_running() { dk ps --format '{{.Names}}' | grep -qx "$1"; }

dump_age_line() {   # dump_age_line LABEL DIR PATTERN MISSING-TEXT: how old the newest database dump is
  local label=$1 days
  days=$(age_days "$2" "$3") || days=""
  if [ -z "$days" ]; then bad "$label" "$4"
  elif [ "$days" -ge 2 ]; then warn "$label" "the newest dump is $days days old"
  else ok "$label" "newest dump is $days day(s) old"; fi
}

env_info() {   # env_info CONTAINER VAR -> "LENGTH STARTS_WITH_base64 LOOKS_LIKE_PLACEHOLDER", or nothing
  dk inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$1" | awk -F= -v v="$2" '
    $1 == v { sub(/^[^=]*=/, ""); print length($0), ($0 ~ /^base64:/ ? 1 : 0), ($0 ~ /your-own-key|^changeme$|^yours?$|^your-password$/ ? 1 : 0); found = 1 }
    END { if (!found) exit 1 }'
}

age_days() {   # age_days DIR PATTERN -> whole days since the newest matching file, or nothing
  local newest
  newest=$(find "$1" -maxdepth 1 -type f -name "$2" -printf '%T@\n' 2>/dev/null | sort -n | tail -1)
  [ -n "$newest" ] || return 1
  echo $(( ( $(date +%s) - ${newest%.*} ) / 86400 ))
}

secrets() {
  local uh dest line len b64 ph n_key n_ph d f missing got
  uh=$(real_home)
  rule "Secrets and rebuild essentials"
  echo "   Values are never shown."
  echo
  printf '   %sKeep these in your password manager%s (the server cannot check them)\n\n' "$B" "$N"
  sed 's/^  /   /' <<'LIST'
  [ ] Linux user login (sudo, SSH, the console)
  [ ] Nextcloud admin login, and the Nextcloud database password
  [ ] Immich admin login, and the Immich database user and password
  [ ] Portainer, AdGuard Home, Beszel and FileBrowser admin logins
  [ ] Speedtest Tracker login and its APP_KEY
  [ ] Homepage widget keys (Tailscale token, Immich key, Nextcloud token, logins)
  [ ] Tailscale account, AnyDesk unattended password, GitHub account and its recovery codes
  [ ] Router admin login and the Wi-Fi password
LIST
  rule "What this server can confirm"

  dest=""
  if [ -r "$LAST_RUN_FILE" ]; then dest=$(awk -F'|' 'END {print $3}' "$LAST_RUN_FILE"); fi
  [ "$dest" = none ] && dest=""

  # Docker needed for the next checks
  if ! { command -v docker >/dev/null 2>&1 && timeout 5 docker info >/dev/null 2>&1; }; then
    warn "Containers" "cannot read Docker, so the keys inside the containers were not checked"
  else
    # Nextcloud database password
    if container_running nextcloud; then
      n_key=$(dk exec nextcloud grep -c "'dbpassword'" /var/www/html/config/config.php || true)
      if [ "${n_key:-0}" -ge 1 ] 2>/dev/null; then ok "Nextcloud DB" "password is set in config.php (a rebuild must reuse this same password)"
      else bad "Nextcloud DB" "no dbpassword found in config.php"; fi
    else
      warn "Nextcloud DB" "the nextcloud container is not running, not checked"
    fi
    # Immich database password
    if container_running immich_postgres; then
      line=$(env_info immich_postgres POSTGRES_PASSWORD) || line=""
      read -r len _ ph <<<"$line"
      if [ -z "$line" ] || [ "${len:-0}" -eq 0 ]; then bad "Immich DB" "no database password is set in the container"
      elif [ "${ph:-0}" -eq 1 ]; then bad "Immich DB" "the password looks like a placeholder"
      else ok "Immich DB" "password is set (${len} characters)"; fi
    else
      warn "Immich DB" "the immich_postgres container is not running, not checked"
    fi
    # Speedtest Tracker key
    if container_running speedtest-tracker; then
      line=$(env_info speedtest-tracker APP_KEY) || line=""
      read -r len b64 ph <<<"$line"
      if [ -z "$line" ]; then bad "Speedtest key" "no APP_KEY is set in the container"
      elif [ "${ph:-0}" -eq 1 ]; then bad "Speedtest key" "APP_KEY is still the placeholder (replace it in the stack, with a base64: key of your own)"
      elif [ "${b64:-0}" -ne 1 ]; then warn "Speedtest key" "APP_KEY does not start with base64: (the app needs that prefix)"
      else ok "Speedtest key" "APP_KEY is set (${len} characters) and is not the placeholder"; fi
    else
      warn "Speedtest key" "the speedtest-tracker container is not running, not checked"
    fi
  fi

  # Homepage keys
  f="$uh/homepage-config/services.yaml"
  if [ -r "$f" ]; then
    n_key=$(grep -c -E '^[[:space:]]+(key|password|token|apikey|deviceid):[[:space:]]*[^[:space:]]' "$f")
    n_ph=$(grep -c -E '^[[:space:]]+(key|password|token|apikey|deviceid):[[:space:]]*(your-own-key|your-password|TOKEN|changeme)[[:space:]]*$' "$f")
    if [ "$n_ph" -gt 0 ]; then warn "Homepage keys" "$((n_key - n_ph)) filled in, $n_ph still placeholders in services.yaml"
    else ok "Homepage keys" "$n_key key/password fields are filled in"; fi
  else
    warn "Homepage keys" "cannot read $f"
  fi

  # Tailscale
  if command -v tailscale >/dev/null 2>&1; then
    if timeout 5 tailscale status >/dev/null 2>&1; then ok "Tailscale" "this machine is logged in"
    else warn "Tailscale" "not logged in, or cannot be read without sudo"; fi
  fi

  # The backup
  if [ -z "$dest" ]; then
    warn "Backup" "no backup location is known yet (no backup has run)"
  elif [ ! -d "$dest" ]; then
    bad "Backup" "the backup folder $dest is not there"
  else
    if [ "$(stat -c %d "$dest" 2>/dev/null)" = "$(stat -c %d "$BOOT_PATH" 2>/dev/null)" ]; then
      warn "Backup place" "$dest is on the boot drive: it is lost if that drive dies (connect a backup drive)"
    elif only_boot_section BACKUP; then
      warn "Backup place" "$dest is a section of the boot drive: it is lost if that drive dies (connect a backup drive)"
    else
      ok "Backup place" "$dest is on its own drive"
    fi
    if [ -r "$dest/boot-configs" ] && [ -x "$dest/boot-configs" ]; then
      missing=""; got=0
      for d in "home/*/homepage-config/services.yaml" "home/*/nextcloud/html/config/config.php" "opt/adguard-docker/conf/AdGuardHome.yaml"; do
        # shellcheck disable=SC2086
        if compgen -G "$dest/boot-configs/"$d >/dev/null 2>&1; then got=$((got + 1)); else missing="$missing ${d##*/}"; fi
      done
      if [ -z "$missing" ]; then ok "Saved configs" "Homepage, Nextcloud and AdGuard files are in the backup"
      elif [ "$got" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then warn "Saved configs" "cannot look inside the backup (run: sudo homelab secrets)"
      else bad "Saved configs" "missing from the backup:$missing"; fi
    else
      warn "Saved configs" "cannot read $dest/boot-configs (run: sudo homelab secrets)"
    fi
    dump_age_line "Nextcloud dump" "$dest/db-dumps" 'nextcloud-*.sql.gz' "no database dump found in $dest/db-dumps"
  fi

  # Immich's own database dumps (in the main pool)
  d="$MAIN_POOL/immich/backups"
  if [ -d "$d" ]; then
    dump_age_line "Immich dump" "$d" '*.sql.gz' "no Immich database dump in $d (Immich > Administration > Job Queues > Create job > Create Database Dump)"
  else
    warn "Immich dump" "$d is not there (is the main pool mounted?)"
  fi
  echo
  echo "   The full list, with where each secret is used and how to get it back, is in SECRETS-CHECKLIST.md in the repository."
  echo
}

