term_cols() { local c; c=$(stty size 2>/dev/null </dev/tty | cut -d" " -f2); [[ "$c" =~ ^[0-9]+$ ]] || c=$(tput cols 2>/dev/null); [[ "$c" =~ ^[0-9]+$ ]] || c=${COLUMNS:-80}; [[ "$c" =~ ^[0-9]+$ ]] || c=80; [ "$c" -lt 40 ] && c=40; echo "$c"; }

rule() {   # rule "Title": a spaced section heading with a thin line
  local cols w t="$1" n pad
  cols=$(term_cols); w=$cols; [ "$w" -gt 76 ] && w=76
  n=$(( w - ${#t} - 8 )); [ "$n" -lt 3 ] && n=3
  pad=$(printf '%*s' "$n" '' | sed "s/ /$S_RULE/g")
  printf '\n  %s%s%s%s %s%s%s %s%s%s\n\n' "$D" "$S_RULE" "$S_RULE" "$N" "$B" "$t" "$N" "$D" "$pad" "$N"
}

# status rows. While BUFFERING=1 they are collected (so the top summary can count them), otherwise printed.
OKN=0; WARNN=0; BADN=0; STATUS_BUF=""; BUFFERING=0
row() {   # row COLOUR SYMBOL LABEL TEXT TEXTCOLOUR
  local out
  printf -v out '   %s%s%s  %-16s %s%s%s\n' "$1" "$2" "$N" "$3" "$5" "$4" "$N"
  if [ "$BUFFERING" -eq 1 ]; then STATUS_BUF+="$out"; else printf '%s' "$out"; fi
}
ok()   { OKN=$((OKN + 1));     row "$G" "$S_OK"   "$1" "$2" ""; }
warn() { WARNN=$((WARNN + 1)); row "$Y" "$S_WARN" "$1" "$2" "$Y"; }
bad()  { BADN=$((BADN + 1));   row "$R" "$S_BAD"  "$1" "$2" "$R"; }

# command lists: collected per section, so the whole section is a table (if it fits the window) or stacked
CMDS_C=(); CMDS_D=()
cmd() { CMDS_C+=("$1"); CMDS_D+=("$2"); }
flush_cmds() {
  local i w=0 cols fits=1
  cols=$(term_cols)
  for i in "${!CMDS_C[@]}"; do [ "${#CMDS_C[$i]}" -gt "$w" ] && w=${#CMDS_C[$i]}; done
  w=$((w + 3))
  for i in "${!CMDS_C[@]}"; do [ $(( 3 + w + ${#CMDS_D[$i]} )) -ge "$cols" ] && fits=0; done
  for i in "${!CMDS_C[@]}"; do
    if [ "$fits" -eq 1 ]; then printf '   %s%-*s%s%s\n' "$B" "$w" "${CMDS_C[$i]}" "$N" "${CMDS_D[$i]}"
    else printf '   %s%s%s\n       %s\n' "$B" "${CMDS_C[$i]}" "$N" "${CMDS_D[$i]}"; fi
  done
  CMDS_C=(); CMDS_D=()
}
section() { flush_cmds; rule "$1"; }

# Suggested commands: status() and setup_line() add entries (priority 1 = most urgent), suggestions() prints the best few.
SUGG=()
suggest() {   # suggest PRIORITY COMMAND WHY  (the same command is kept only once)
  local e
  for e in "${SUGG[@]}"; do [[ "$e" == *"|$2|"* ]] && return 0; done
  SUGG+=("$1|$2|$3")
}
only_boot_section() {   # only_boot_section MAIN|BACKUP: this pool is made of a boot drive section and no real drive
  local pfx=$1 d dir="${HOMELAB_DISKS_DIR:-/mnt/disks}"
  for d in "$dir/$pfx"[0-9]*; do [ -e "$d" ] && findmnt -n "$d" >/dev/null 2>&1 && return 1; done
  findmnt -n "$dir/${pfx}BOOT" >/dev/null 2>&1
}

suggestions() {
  local max="${HOMELAB_SUGGEST_MAX:-6}" n=0 c why
  # when little needs doing, fill up with the commands used most often (the ones that matter now come first)
  suggest 6 "sudo drives status" "pools, drives, temperatures and the last backup"
  suggest 6 "sudo homelab-backup" "run a backup now"
  suggest 7 "sudo homelab-update check" "look online for newer container images"
  suggest 7 "docker ps" "what is running right now"
  suggest 7 "sudo homelab-selftest" "check everything and look for problems or leftovers"
  suggest 8 "sudo drives" "menu: connect or remove drives, or use part of the boot drive for a pool"
  if [ -d "$HOMEPAGE_DIR" ]; then
    suggest 8 "homelab theme" "change the dashboard's background and card colours"
    suggest 8 "homelab bookmark add NAME URL" "add a bookmark to the dashboard, with its logo"
  fi
  suggest 9 "homelab commands" "every command, in groups"
  suggest 9 "homelab docs" "list the sections of the guides"
  rule "Suggested Commands"
  while IFS='|' read -r _p c why; do
    [ -n "$c" ] || continue
    [ "$n" -ge "$max" ] && break
    cmd "$c" "$why"; n=$((n + 1))
  done < <(printf '%s\n' "${SUGG[@]}" | sort -t'|' -k1,1n -s)
  flush_cmds
  echo
}

lan_address() {   # this machine's address on the home network
  local ip="${HOMELAB_LAN_IP:-}"
  [ -n "$ip" ] || ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") {print $(i + 1); exit}}')
  [ -n "$ip" ] || ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  echo "$ip"
}

open_section() {   # where to click: the dashboard on the home network, and from anywhere through Tailscale
  [ -d "$HOMEPAGE_DIR" ] || return 0
  local ip ts="" port=""
  ip=$(lan_address)
  [ -n "$ip" ] || return 0
  # the port Homepage listens on: ask Docker (the installer's default is 3001; 3000 belongs to AdGuard Home)
  command -v docker >/dev/null 2>&1 && port=$(timeout 3 docker port homepage 2>/dev/null | awk -F: 'NR == 1 {print $NF}')
  [[ "$port" =~ ^[0-9]+$ ]] || port="${HOMELAB_HOMEPAGE_PORT:-3001}"
  if command -v tailscale >/dev/null 2>&1; then
    ts=$(timeout 3 tailscale serve status 2>/dev/null | awk -v p=":$port" '/^https:\/\// {u = $1} $0 ~ "proxy .*" p "[[:space:]]*$" && u {print u; exit}')
  fi
  rule "Open in your browser"
  printf '   %-30s %s%s%s\n' "Dashboard, at home" "$B" "http://$ip:$port" "$N"
  [ -z "$ts" ] || printf '   %-30s %s%s%s\n' "Dashboard, from anywhere" "$B" "$ts" "$N"
  [ -z "$ts" ] || printf '   %s%-30s needs the Tailscale app on that device, signed in to your account%s\n' "$D" "" "$N"
}

show_docs() {
  local f
  if [ ! -d "$DOCS_DIR" ]; then
    echo "The documents are not on this server yet. Clone them once:"
    echo "  git clone $REPO_URL \"$DOCS_DIR\""
    return 1
  fi
  for f in README.md $(cd "$DOCS_DIR" 2>/dev/null && ls docs/*.md 2>/dev/null); do
    [ -f "$DOCS_DIR/$f" ] || continue
    rule "$f"
    echo "   open a section with:  less +LINE $DOCS_DIR/$f"
    echo
    grep -n '^## ' "$DOCS_DIR/$f" | sed 's/^\([0-9]*\):## /   \1\t/'
  done
  echo
}

header() {
  printf '\n  %sHome lab%s  %s%s%s  %s  %s%s%s  %s\n' "$B" "$N" "$D" "$S_DOT" "$N" "$(hostname)" "$D" "$S_DOT" "$N" "$(uptime -p 2>/dev/null)"
}

summary_line() {
  echo
  if [ "$BADN" -gt 0 ]; then
    local w="need"; [ "$BADN" -eq 1 ] && w="needs"
    local p="problems"; [ "$BADN" -eq 1 ] && p="problem"
    printf '   %s%s%s  %s%d %s %s you.%s  Details in Status below.\n' "$R" "$S_BAD" "$N" "$R" "$BADN" "$p" "$w" "$N"
  elif [ "$WARNN" -gt 0 ]; then
    local t="things"; [ "$WARNN" -eq 1 ] && t="thing"
    printf '   %s%s%s  %d %s to look at.  Details in Status below.\n' "$Y" "$S_WARN" "$N" "$WARNN" "$t"
  else
    printf '   %s%s%s  Everything looks fine.\n' "$G" "$S_OK" "$N"
  fi
}

setup_line() {   # shown only while homelab-setup still has steps left (it removes the file when all are done)
  local f="$STATE_DIR/setup-progress" d t _e
  [ -r "$f" ] || return 0
  IFS='|' read -r d t _e <"$f"
  [[ "$d" =~ ^[0-9]+$ && "$t" =~ ^[0-9]+$ ]] || return 0
  [ "$d" -lt "$t" ] || return 0
  printf '   %s%s%s  Setup is not finished: %d of %d steps done. Some warnings below are normal until it is.\n' "$Y" "$S_WARN" "$N" "$d" "$t"
  printf '       Next: run  %ssudo homelab-setup%s  to see what is left.\n' "$B" "$N"
  suggest 2 "sudo homelab-setup refresh" "carry on with setup ($(( t - d )) steps left)"
  suggest 2 "sudo homelab-setup" "see the checklist and the next step"
}

hint_line() {
  printf '  %sType%s %shomelab commands%s %sto see every command.%s\n\n' "$D" "$N" "$B" "$N" "$D" "$N"
}

