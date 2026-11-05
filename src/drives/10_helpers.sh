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

