# ---------- small helpers ----------
log()  { printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$LOGFILE" 2>/dev/null || true; }
say()  { printf '%s\n' "$*"; }
note() { printf '%s\n' "$*" >&2; }
warn() { printf 'WARNING: %s\n' "$*" >&2; log "WARN $*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; log "ERROR $*"; restore_services; exit 1; }

ask()  { local v=""; printf '%s' "$1" >&2; IFS= read -r v || true; printf '%s' "$v"; }
yn()   {
  if [ "$ASSUME_YES" = 1 ]; then note "$1 [y/N]: y   (--yes)"; return 0; fi
  case "$(ask "$1 [y/N]: ")" in y|Y|yes|YES|Yes) return 0 ;; *) return 1 ;; esac
}
typed() {   # typed WORD "Prompt: ": the person must type WORD. --confirm-erase types it for a script; a dry run changes nothing, so it needs no typing
  if [ "$PANEL_MODE" = 1 ]; then      # the control panel passes what the person typed; it counts only when it is exactly the word asked for
    local w
    for w in "${PANEL_TYPED[@]}"; do [ "$w" = "$1" ] && { note "${2}$1   (typed in the panel)"; return 0; }; done
    note "${2}(not typed)"
    return 1
  fi
  if [ "$CONFIRM_ERASE" = 1 ]; then note "${2}$1   (--confirm-erase)"; return 0; fi
  if [ "$DRY_RUN" = 1 ]; then note "${2}(not needed for a dry run)"; return 0; fi
  [ "$(ask "$2")" = "$1" ]
}

choose() {   # choose "Prompt: " item1 item2 ... -> prints 0-based index
  local prompt=$1; shift
  local n=$# i=1 a
  for a in "$@"; do printf '  %d) %s\n' "$i" "$a" >&2; i=$((i + 1)); done
  printf '  0) Cancel\n' >&2
  while :; do
    a=$(ask "$prompt")
    case "$a" in 0|"") note "Cancelled."; return 1 ;; esac
    if [[ "$a" =~ ^[0-9]+$ ]] && [ "$a" -ge 1 ] && [ "$a" -le "$n" ]; then
      echo $((a - 1)); return 0
    fi
    note "Please type a number from the list."
  done
}

human() { numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "$1 B"; }

role_prefix() { if [ "$1" = main ]; then echo "$MAIN_PREFIX"; else echo "$BACKUP_PREFIX"; fi; }
role_pool()   { if [ "$1" = main ]; then echo "$MAIN_POOL";   else echo "$BACKUP_POOL";   fi; }
other_role()  { if [ "$1" = main ]; then echo backup; else echo main; fi; }

sd_reload() { [ "$TEST_MODE" = 1 ] || systemctl daemon-reload; }


progress() {   # progress PERCENT "Text": the control panel shows a bar on the drive that is being changed (only inside `drives panel`; PERCENT is the drive's own 0-100)
  [ "$PANEL_MODE" = 1 ] || return 0
  printf 'PROGRESS %s %s %s\n' "${PROG_ITEM:--}" "$(( PROG_LO + $1 * (PROG_HI - PROG_LO) / 100 ))" "$2"
}

rsync_run() {   # rsync_run FROM TO "Text" RSYNC-ARGS...: like rsync; in the panel its percent moves the bar from FROM to TO
  local from=$1 to=$2 text=$3 rc=0 rcfile; shift 3
  if [ "$PANEL_MODE" != 1 ]; then rsync "$@"; return $?; fi
  rcfile=$(mktemp) || { rsync "$@"; return $?; }
  local line pct last=-1
  { rsync --info=progress2 --no-inc-recursive "$@" 2>&1; echo "RSYNC_RC=$?"; } | tr '\r' '\n' | while IFS= read -r line; do
    case "$line" in
      RSYNC_RC=*) echo "${line#RSYNC_RC=}" >"$rcfile" ;;
      *%*) if [[ "$line" =~ ([0-9]+)% ]]; then
             pct=${BASH_REMATCH[1]}
             if [ "$pct" != "$last" ]; then last=$pct; progress $(( from + pct * (to - from) / 100 )) "$text $pct%"; fi
           fi ;;
    esac
  done
  rc=$(cat "$rcfile" 2>/dev/null || echo 1); rm -f "$rcfile"
  return "${rc:-1}"
}
