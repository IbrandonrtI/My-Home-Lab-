screen() {   # the whole screen, checked live. "login" leaves out the suggested commands and puts the hint under the browser addresses
  local login="${1:-}"
  BUFFERING=1; status; BUFFERING=0
  header; summary_line; setup_line; finish_line
  rule "Status"; printf '%s\n' "$STATUS_BUF"
  open_section "$login"
  if [ -n "$login" ]; then login_hint; else suggestions; hint_line; fi
}

login_hint() {
  printf '\n  %sType%s %shomelab%s %sfor the full status, or%s %shomelab commands%s%s.%s\n' "$D" "$N" "$B" "$N" "$D" "$N" "$B" "$N" "$D" "$N"
  secrets_hint
}

uptime_secs() {
  local u=${HOMELAB_UPTIME:-$(cut -d. -f1 /proc/uptime 2>/dev/null)}
  [[ "$u" =~ ^[0-9]+$ ]] || u=999999
  echo "$u"
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

# login_screen: what ~/.bashrc runs when a terminal opens: the summary, the status and the browser addresses, without the suggested commands.
#  - A screen made less than 2 minutes ago (for the same window width) is shown again as it was, so opening several terminals in a row
#    does the checks once. "homelab" and "homelab status" are always live.
#  - In the first 10 minutes after a boot the apps are still starting: only light checks run, so SSH stays quick.
login_screen() {
  local dir="${HOMELAB_CACHE_DIR:-${XDG_RUNTIME_DIR:-$HOME/.cache}}/homelab-login" file cols now mt age up text
  file="$dir/screen"; cols=$(term_cols); now=$(date +%s); up=$(uptime_secs)
  mt=$(stat -c %Y "$file" 2>/dev/null || echo 0); age=$(( now - mt ))
  if [ -r "$file" ] && [ "$age" -ge 0 ] && [ "$age" -lt "$LOGIN_CACHE_SECS" ] && [ "$age" -lt "$up" ] \
     && [ "$(head -n 1 "$file")" = "$cols|$B" ]; then
    tail -n +2 "$file"
    return 0
  fi
  [ "$up" -lt "$BOOT_GRACE_SECS" ] && JUST_BOOTED=1
  text=$(screen login)
  printf '%s\n' "$text"
  if mkdir -p "$dir" 2>/dev/null && chmod 700 "$dir" 2>/dev/null; then
    { printf '%s|%s\n' "$cols" "$B"; printf '%s\n' "$text"; } >"$file.$$" 2>/dev/null && mv -f "$file.$$" "$file" 2>/dev/null || rm -f "$file.$$"
  fi
}

forward() {   # short forms: "homelab backup" runs "sudo homelab-backup" (it says so, so the real name is learned)
  local word="$1"; shift
  local -a real
  case "$word" in
    backup)          real=(homelab-backup) ;;
    update)          real=(homelab-update) ;;
    upgrade)         real=(homelab-setup upgrade) ;;
    uninstall)       real=(homelab-setup uninstall) ;;
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
  backup|update|upgrade|uninstall|setup|drives|drive|cards|selftest) forward "$@" ;;
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

