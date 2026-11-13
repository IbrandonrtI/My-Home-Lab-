# ---------- small helpers ----------
log()  { printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$LOGFILE" 2>/dev/null || true; }
say()  { printf '%s\n' "$*"; }
note() { printf '%s\n' "$*" >&2; }
why() { [ -n "${PANEL_RESERVE_DIR:-}" ] && [ -d "$PANEL_RESERVE_DIR" ] && printf '%s\n' "$2" >"$PANEL_RESERVE_DIR/${PROG_ITEM:-none}.$1" 2>/dev/null; return 0; }      # why KIND TEXT: in a batch, what this drive's process complained about last (the batch tells it in its report)
warn() { printf 'WARNING: %s\n' "$*" >&2; log "WARN $*"; why warn "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; log "ERROR $*"; why err "$*"; restore_services; exit 1; }

hint() { if [ "$PANEL_MODE" = 1 ]; then printf '%s' "$2"; else printf '%s' "$1"; fi; }      # hint "terminal wording" "panel wording": the control panel has no terminal, so it points to its own buttons
ask()  { local v=""; printf '%s' "$1" >&2; IFS= read -r v || true; printf '%s' "$v"; }
yn()   {
  if [ "$ASSUME_YES" = 1 ]; then note "$1 [y/N]: y   (--yes)"; return 0; fi
  case "$(ask "$1 [y/N]: ")" in y|Y|yes|YES|Yes) return 0 ;; *) return 1 ;; esac
}
yn_yes() {   # a yes/no question where Enter means yes (only for questions whose answer is safe, for example removing copies that were just checked)
  if [ "$ASSUME_YES" = 1 ]; then note "$1 [Y/n]: y   (--yes)"; return 0; fi
  case "$(ask "$1 [Y/n]: ")" in n|N|no|NO|No) return 1 ;; *) return 0 ;; esac
}
typed_enter() {   # typed_enter WORD "Prompt": like `typed`, but Enter alone also counts (the word is shown as the default). Never for erasing: that stays `typed ERASE`.
  if [ "$PANEL_MODE" = 1 ] || [ "$CONFIRM_ERASE" = 1 ] || [ "$DRY_RUN" = 1 ]; then typed "$1" "$2: "; return; fi
  local v; v=$(ask "$2 [$1]: ")
  [ -z "$v" ] || [ "$v" = "$1" ]
}
typed() {   # typed WORD "Prompt: ": the person must type WORD. --confirm-erase types it for a script; a dry run changes nothing, so it needs no typing
  if [ "$PANEL_MODE" = 1 ]; then      # the control panel passes what the person typed; it counts only when it is exactly the word asked for
    local w
    [ "${PANEL_UNDO:-0}" = 1 ] && return 0      # (putting a drive back after Stop: nothing is lost, so nothing has to be confirmed)
    for w in "${PANEL_TYPED[@]}"; do [ "$w" = "$1" ] && { note "${2}$1   (typed in the panel)"; return 0; }; done
    note "${2}(not typed)"
    return 1
  fi
  if [ "$CONFIRM_ERASE" = 1 ]; then note "${2}$1   (--confirm-erase)"; return 0; fi
  if [ "$DRY_RUN" = 1 ]; then note "${2}(not needed for a dry run)"; return 0; fi
  [ "$(ask "$2")" = "$1" ]
}

choose() {   # choose "Prompt: " item1 item2 ... -> prints 0-based index. CHOOSE_DEFAULT=N makes Enter pick item N (only set for choices that are safe)
  local prompt=$1; shift
  local n=$# i=1 a def=${CHOOSE_DEFAULT:-}
  for a in "$@"; do printf '  %d) %s\n' "$i" "$a" >&2; i=$((i + 1)); done
  printf '  0) Cancel\n' >&2
  [ -z "$def" ] || prompt="${prompt%: }  [$def]: "
  while :; do
    a=$(ask "$prompt")
    [ -n "$a" ] || a=$def
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
  local it pct=$(( PROG_LO + $1 * (PROG_HI - PROG_LO) / 100 ))
  if [ "${#PROG_ALL[@]}" -gt 0 ]; then for it in "${PROG_ALL[@]}"; do printf 'PROGRESS %s %s %s\n' "$it" "$pct" "$2"; done; return 0; fi
  printf 'PROGRESS %s %s %s\n' "${PROG_ITEM:--}" "$pct" "$2"
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

gb2() {   # gb2 BYTES -> "5.00 GB" (as drives are sold: 1 GB = 1000 MB)
  awk -v b="${1:-0}" 'BEGIN { if (b >= 1e12) printf "%.2f TB", b / 1e12; else printf "%.2f GB", b / 1e9 }'
}

rsync_bytes_run() {   # rsync_bytes_run TOTAL_BYTES "Text" RSYNC-ARGS...: like rsync; in the panel the bar shows "Text 5.00 GB / 11.00 GB" (TOTAL_BYTES is what the preview found)
  local total=$1 text=$2 rc=0 rcfile; shift 2
  if [ "$PANEL_MODE" != 1 ]; then rsync "$@"; return $?; fi
  rcfile=$(mktemp) || { rsync "$@"; return $?; }
  local line done_b pct last=-1 lastb=0
  [ "${total:-0}" -gt 0 ] 2>/dev/null || total=1
  { rsync --info=progress2 --no-inc-recursive "$@" 2>&1; echo "RSYNC_RC=$?"; } | tr '\r' '\n' | while IFS= read -r line; do
    case "$line" in
      RSYNC_RC=*) echo "${line#RSYNC_RC=}" >"$rcfile" ;;
      *%*) if [[ "$line" =~ ^[[:space:]]*([0-9,]+)[[:space:]]+([0-9]+)% ]]; then
             done_b=${BASH_REMATCH[1]//,/}
             [ "$done_b" -gt "$total" ] && done_b=$total
             pct=$(( done_b * 100 / total ))
             # a new line when the percent moved, or about every 50 MB (a few big files move the number long before the percent changes)
             if [ "$pct" != "$last" ] || [ $(( done_b - lastb )) -ge 50000000 ]; then last=$pct; lastb=$done_b; progress "$pct" "$text $(gb2 "$done_b") / $(gb2 "$total")"; fi
           fi ;;
    esac
  done
  rc=$(cat "$rcfile" 2>/dev/null || echo 1); rm -f "$rcfile"
  return "${rc:-1}"
}

# ---------- several drives at once, and the Stop button (the control panel only) ----------
abort_requested() {   # 0 when the person pressed Stop (not while a drive is being put back)
  [ "$ABORT_IGNORE" = 1 ] && return 1
  [ -e "$ABORT_FILE" ]
}

batch_all_ready() {   # 0 when every drive of the batch has finished its slow work or has ended
  local id
  for id in "${PANEL_IDS[@]}"; do
    [ -e "$PANEL_RESERVE_DIR/ready-$id" ] || [ -e "$PANEL_RESERVE_DIR/$id.state" ] || return 1
  done
  return 0
}
batch_barrier() {   # a drive whose slow work (copying, formatting) is done waits here until every drive of the batch is done with it: then the pool changes follow one after the other, with the containers stopped only once. 1 when Stop was pressed while waiting
  [ "$PANEL_BARRIER" = 1 ] && [ -n "$PANEL_RESERVE_DIR" ] || return 0
  local f="$PANEL_RESERVE_DIR/ready-$PROG_ITEM"
  [ -e "$f" ] && return 0
  : >"$f"
  progress 60 "Waiting for the other drives"
  until [ -e "$PANEL_RESERVE_DIR/launched-all" ] && batch_all_ready; do
    abort_requested && return 1
    sleep 0.5
  done
  return 0
}
batch_copying() {   # how many drives of the batch are in their slow part right now
  local id n=0
  for id in "$@"; do
    [ -e "$PANEL_RESERVE_DIR/ready-$id" ] || [ -e "$PANEL_RESERVE_DIR/$id.state" ] || n=$((n + 1))
  done
  echo "$n"
}

crit_enter() {   # crit_enter [abortable]: only one drive at a time may change a pool (stop containers, edit fstab, mount, start containers). Waits for its turn; 1 only when "abortable" and Stop was pressed while waiting
  if [ "$CRIT_DEPTH" -gt 0 ]; then CRIT_DEPTH=$((CRIT_DEPTH + 1)); return 0; fi
  mkdir -p "$(dirname "$POOL_LOCK")" 2>/dev/null || true
  { exec 8>"$POOL_LOCK"; } 2>/dev/null || return 0      # (no lock file: one drive at a time anyway)
  until flock -w 1 8; do
    if [ "${1:-}" = abortable ] && abort_requested; then { exec 8>&-; } 2>/dev/null; return 1; fi
  done
  CRIT_DEPTH=1
  return 0
}
crit_leave() {
  [ "$CRIT_DEPTH" -gt 0 ] || return 0
  CRIT_DEPTH=$((CRIT_DEPTH - 1))
  if [ "$CRIT_DEPTH" -eq 0 ]; then { exec 8>&-; } 2>/dev/null; fi
  return 0
}
crit_release() {   # leave however deep this process is in
  if [ "$CRIT_DEPTH" -gt 0 ]; then CRIT_DEPTH=0; { exec 8>&-; } 2>/dev/null; fi
  return 0
}

take_label() {   # take_label main|backup -> the next free drive name; in a batch with several drives the name is also reserved, so two drives never get the same one
  local l
  if [ -z "$PANEL_RESERVE_DIR" ]; then next_label "$1"; return 0; fi
  crit_enter || true
  l=$(next_label "$1")
  : >"$PANEL_RESERVE_DIR/label-$l"
  crit_leave
  echo "$l"
}

target_lock() {   # target_lock TARGET-MOUNT: only one drive of a batch copies to the same drive at a time (two drives can hold different versions of the same file, and a copy must not be overwritten while it is being checked). Waits for its turn; 1 only when Stop was pressed while waiting
  local f
  f="$STATE_DIR/target-$(basename "$1").lock"
  { exec 6>"$f"; } 2>/dev/null || return 0
  until flock -w 1 6; do
    if abort_requested; then { exec 6>&-; } 2>/dev/null; return 1; fi
  done
  return 0
}
target_unlock() { { exec 6>&-; } 2>/dev/null; return 0; }

space_pick() {   # space_pick SOURCE-MOUNT BYTES TARGET...: the emptiest of the target drives that still has BYTES (and the spare margin) free after what other copies of this batch have reserved; reserves it
  local src=$1 need=$2 o free res best="" bestfree=0; shift 2
  crit_enter || true
  for o in "$@"; do
    mountpoint -q "$o" || continue
    free=$(avail_bytes "$o")
    res=0
    [ -n "$PANEL_RESERVE_DIR" ] && res=$(awk -v t="$o" '$2 == t {s += $3} END {print s + 0}' "$PANEL_RESERVE_DIR/space" 2>/dev/null)
    free=$((free - ${res:-0}))
    if [ "$free" -gt "$bestfree" ]; then best=$o; bestfree=$free; fi
  done
  if [ -n "$best" ] && [ "$bestfree" -ge $((need + DRAIN_SPARE_BYTES)) ]; then
    [ -n "$PANEL_RESERVE_DIR" ] && printf '%s %s %s\n' "$src" "$best" "$need" >>"$PANEL_RESERVE_DIR/space"
    crit_leave
    echo "$best"
    return 0
  fi
  crit_leave
  return 1
}

space_release() {   # space_release SOURCE-MOUNT: the copy is over (the files are on the target now, so the drive's own numbers show them)
  [ -n "$PANEL_RESERVE_DIR" ] && [ -f "$PANEL_RESERVE_DIR/space" ] || return 0
  crit_enter || true
  grep -v "^$1 " "$PANEL_RESERVE_DIR/space" >"$PANEL_RESERVE_DIR/space.new" 2>/dev/null
  mv -f "$PANEL_RESERVE_DIR/space.new" "$PANEL_RESERVE_DIR/space"
  crit_leave
  return 0
}
