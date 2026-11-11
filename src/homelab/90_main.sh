screen() {   # the full login screen, checked live
  BUFFERING=1; status; BUFFERING=0
  header; summary_line; setup_line
  rule "Status"; printf '%s\n' "$STATUS_BUF"
  open_section
  suggestions
  hint_line
}

uptime_secs() {
  local u=${HOMELAB_UPTIME:-$(cut -d. -f1 /proc/uptime 2>/dev/null)}
  [[ "$u" =~ ^[0-9]+$ ]] || u=999999
  echo "$u"
}

# alerts_read ALERTS-FILE STATS-FILE: reads what the bell keeps (alerts.json) with python3. Prints nothing when the file cannot be read, otherwise
#   A|AGE-IN-SECONDS|EXTRA-TEXT      one line; the extra text is the last backup and the pool fullness, for the "all good" line
#   I|LEVEL|TITLE                    one line for every item (worst first)
alerts_read() {
  command -v python3 >/dev/null 2>&1 || return 0
  python3 - "$1" "$2" 2>/dev/null <<'PY'
import json, sys, time
try:
    a = json.load(open(sys.argv[1]))
    age = int(time.time() - float(a["updated"]))
    items = [i for i in a.get("items", []) if i.get("level") in ("bad", "warn", "info") and i.get("title")]
except Exception:
    sys.exit(0)
extra = []
try:
    s = json.load(open(sys.argv[2]))
    lb = s.get("last_backup") or {}
    if str(lb.get("result", "")).upper() == "OK" and lb.get("when") not in (None, "", "-", "Never"):
        extra.append("last backup " + str(lb["when"]).lower())
    pct = str((s.get("main") or {}).get("percent", ""))
    if pct.endswith("%"):
        extra.append("main pool " + pct + " full")
except Exception:
    pass
print("A|%d|%s" % (age, ", ".join(extra)))
for i in items:
    print("I|%s|%s" % (i["level"], str(i["title"]).replace("|", "/").replace("\n", " ")))
PY
}

# The two dashboard addresses are looked up through Docker and Tailscale, which takes a moment, so a login keeps them for an hour.
cached_dashboard_urls() {
  local dir="${HOMELAB_CACHE_DIR:-${XDG_RUNTIME_DIR:-$HOME/.cache}}/homelab-login" file mt now
  file="$dir/urls"; now=$(date +%s); mt=$(stat -c %Y "$file" 2>/dev/null || echo 0)
  DASH_HOME=""; DASH_TS=""
  if [ -r "$file" ] && [ $(( now - mt )) -ge 0 ] && [ $(( now - mt )) -lt "$URL_CACHE_SECS" ]; then
    IFS='|' read -r DASH_HOME DASH_TS <"$file"
    return 0
  fi
  dashboard_urls
  if [ -n "$DASH_HOME" ] && mkdir -p "$dir" 2>/dev/null && chmod 700 "$dir" 2>/dev/null; then
    printf '%s|%s\n' "$DASH_HOME" "$DASH_TS" >"$file.$$" 2>/dev/null && mv -f "$file.$$" "$file" 2>/dev/null || rm -f "$file.$$"
  fi
}

# login_screen: what ~/.bashrc runs when a terminal opens. A few lines, shown at once:
#   - It reads the file the bell keeps (alerts.json, rewritten every 5 minutes), so nothing has to be checked while you wait.
#   - If that file is missing or old, it falls back to a live check (the same one as "homelab status") and lists what is wrong.
#   - In the first 10 minutes after a boot the apps are still starting, so it says so and checks nothing.
#   "homelab" shows the whole screen and "homelab status" the whole status, always live.
login_screen() {
  local hp="${HOMELAB_HOMEPAGE_DIR:-$HOME/homepage-config}" up cols max=3 shown=0 total=0 nbad=0 nwarn=0 age="" extra="" kind lvl title rest line
  local -a items=()
  up=$(uptime_secs); cols=$(term_cols)
  header
  echo
  if [ "$up" -lt "$BOOT_GRACE_SECS" ]; then
    printf '   %s%s%s  Just started and the apps are still starting. Check again in a few minutes.\n' "$Y" "$S_WARN" "$N"
  else
    while IFS='|' read -r kind lvl title; do
      case "$kind" in
        A) age=$lvl; extra=$title ;;
        I) items+=("$lvl|$title") ;;
      esac
    done < <(alerts_read "$hp/images/alerts.json" "$hp/images/stats.json")
    if [[ "$age" =~ ^-?[0-9]+$ ]] && [ "$age" -le "$ALERTS_MAX_AGE" ] && [ "$age" -ge -300 ]; then
      :   # the bell's file is fresh: use it
    else
      items=(); extra=""; age=""
      BUFFERING=1; status; BUFFERING=0
      while IFS='|' read -r lvl title rest; do
        [ -n "$lvl" ] && items+=("$lvl|$title: $rest")
      done <<<"$ISSUES_BUF"
    fi
    # while setup still has steps left (it removes this file when all are done), say so first
    if [ -r "$STATE_DIR/setup-progress" ]; then
      local sd st _se; IFS='|' read -r sd st _se <"$STATE_DIR/setup-progress"
      if [[ "$sd" =~ ^[0-9]+$ && "$st" =~ ^[0-9]+$ ]] && [ "$sd" -lt "$st" ]; then
        printf '   %s%s%s  Setup is not finished (%d of %d steps). Next: %ssudo homelab-setup%s\n' "$Y" "$S_WARN" "$N" "$sd" "$st" "$B" "$N"
      fi
    fi
    total=${#items[@]}
    for line in "${items[@]}"; do case "${line%%|*}" in bad) nbad=$((nbad + 1)) ;; warn) nwarn=$((nwarn + 1)) ;; esac; done
    if [ "$nbad" -eq 0 ] && [ "$nwarn" -eq 0 ] && [ "$total" -eq 0 ]; then
      printf '   %s%s%s  All good%s%s\n' "$G" "$S_OK" "$N" "${extra:+  $S_DOT  }" "$D$extra$N"
    else
      for line in "${items[@]}"; do
        [ "$shown" -ge "$max" ] && break
        lvl=${line%%|*}; title=${line#*|}
        [ "${#title}" -gt $(( cols - 8 )) ] && title="${title:0:$(( cols - 11 ))}..."
        case "$lvl" in
          bad)  printf '   %s%s%s  %s%s%s\n' "$R" "$S_BAD" "$N" "$R" "$title" "$N" ;;
          warn) printf '   %s%s%s  %s%s%s\n' "$Y" "$S_WARN" "$N" "$Y" "$title" "$N" ;;
          *)    printf '   %s%s%s  %s\n' "$D" "$S_DOT" "$N" "$title" ;;
        esac
        shown=$((shown + 1))
      done
      [ "$total" -gt "$shown" ] && printf '      %s+%d more (homelab status)%s\n' "$D" $(( total - shown )) "$N"
    fi
  fi
  if [ -d "$hp" ]; then
    cached_dashboard_urls
    if [ -n "$DASH_HOME" ]; then
      echo
      if [ -n "$DASH_TS" ] && [ $(( 13 + ${#DASH_HOME} + 4 + ${#DASH_TS} )) -lt "$cols" ]; then
        printf '   %sDashboard%s  %s%s%s   %s%s%s\n' "$D" "$N" "$B" "$DASH_HOME" "$N" "$B" "$DASH_TS" "$N"
      else
        printf '   %sDashboard%s  %s%s%s\n' "$D" "$N" "$B" "$DASH_HOME" "$N"
      fi
    fi
  fi
  echo
  if [ "$cols" -ge 62 ]; then
    printf '  %sType%s %shomelab%s %sfor the full status, or%s %shomelab commands%s%s.%s\n\n' "$D" "$N" "$B" "$N" "$D" "$N" "$B" "$N" "$D" "$N"
  else
    printf '  %sType%s %shomelab%s %sfor the full status.%s\n\n' "$D" "$N" "$B" "$N" "$D" "$N"
  fi
}

forward() {   # short forms: "homelab backup" runs "sudo homelab-backup" (it says so, so the real name is learned)
  local word="$1"; shift
  local -a real
  case "$word" in
    backup)          real=(homelab-backup) ;;
    update)          real=(homelab-update) ;;
    upgrade)         real=(homelab-setup upgrade) ;;
    setup)           real=(homelab-setup) ;;
    drives|drive)    real=(drives) ;;
    cards)           real=(homelab-cards) ;;
    selftest)        real=(homelab-selftest) ;;
  esac
  printf '  %sRunning:  sudo %s%s\n' "$D" "${real[*]}${*:+ $*}" "$N" >&2
  if [ "$(id -u)" = 0 ]; then exec "${real[@]}" "$@"; fi
  exec sudo "${real[@]}" "$@"
}

did_you_mean() {   # a word that is not a homelab option: point to the command the person most likely meant
  local w="${1:-}" c="" why=""
  case "$w" in
    disk|disks|storage|pool|pools)     c="homelab drives";                     why="the drive menu: look at, connect, remove or fix drives" ;;
    pull|install)                      c="homelab upgrade";                    why="download the newest lab files from GitHub and put them on this server" ;;
    check|test|health|verify)          c="sudo homelab-selftest";              why="the big check of the whole lab. Which check fits? see: homelab commands" ;;
    restore)                           c="sudo homelab-restore-configs check"; why="preview restoring the saved settings after a rebuild" ;;
    recover|remount|mount)             c="sudo drives remount";                why="after an unplug or power cut: remount the drives and start the containers" ;;
    logs|log)                          c="docker logs --tail 50 NAME";         why="the last lines a container printed" ;;
    help-me|-?|\?)                    c="homelab help";                       why="what this command can do" ;;
  esac
  echo "homelab does not have an option called '$w'."
  [ -z "$c" ] || printf 'Did you mean:  %s\n    (%s)\n' "$c" "$why"
  echo "Options of this command:  homelab help      Every command, in groups:  homelab commands"
}

case "${1:-}" in
  backup|update|upgrade|setup|drives|drive|cards|selftest) forward "$@" ;;
  panel)  panel_cmd "${@:2}" ;;
  theme)  homepage_edit theme "${@:2}" ;;
  simple) homepage_edit simple "${@:2}" ;;
  bookmark|bookmarks) homepage_edit bookmark "${@:2}" ;;
  event|events) calendar_cmd "${@:2}" ;;
  calendar|calendars) calendar_cmd feed "${@:2}" ;;
  docs)   show_docs ;;
  secrets) secrets ;;
  -h|--help|help)
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0" ;;
  version|--version) echo "homelab $VERSION" ;;
  status) BUFFERING=1; status; BUFFERING=0; rule "Status"; printf '%s\n' "$STATUS_BUF" ;;
  commands|command)
          header; commands
          echo; printf '  %sType%s %shomelab%s %sto see the status.%s\n\n' "$D" "$N" "$B" "$N" "$D" "$N" ;;
  login)  login_screen ;;
  "")     screen ;;
  *)      did_you_mean "$1" >&2; exit 1 ;;
esac

