# ---------- fstab ----------
fstab_active() { awk '!/^[[:space:]]*(#|$)/' "$FSTAB"; }
pool_in_fstab() { fstab_active | awk -v m="$1" '$2 == m {f = 1} END {exit !f}'; }   # is there an active fstab line for this mount point

setting_get() {   # setting_get KIND KEY -> the value, or nothing
  [ -r "$SETTINGS_FILE" ] || return 0
  awk -F'|' -v k="$1" -v n="$2" '$1 == k && $2 == n { sub(/^[^|]*\|[^|]*\|/, ""); print; exit }' "$SETTINGS_FILE"
}

setting_put() {   # setting_put KIND KEY VALUE
  local tmp
  mkdir -p "$(dirname "$SETTINGS_FILE")" 2>/dev/null || die "Could not write $SETTINGS_FILE"
  tmp=$(mktemp) || die "Could not make a temporary file"
  { [ -r "$SETTINGS_FILE" ] && awk -F'|' -v k="$1" -v n="$2" '!($1 == k && $2 == n)' "$SETTINGS_FILE"; printf '%s|%s|%s\n' "$1" "$2" "$3"; } >"$tmp"
  cat "$tmp" >"$SETTINGS_FILE" || { rm -f "$tmp"; die "Could not write $SETTINGS_FILE"; }
  rm -f "$tmp"
}

setting_del() {   # setting_del KIND KEY
  [ -r "$SETTINGS_FILE" ] || return 0
  local tmp; tmp=$(mktemp) || return 0
  awk -F'|' -v k="$1" -v n="$2" '!($1 == k && $2 == n)' "$SETTINGS_FILE" >"$tmp"
  cat "$tmp" >"$SETTINGS_FILE" || true
  rm -f "$tmp"
}

SETTINGS_SNAP=""
settings_snapshot() { SETTINGS_SNAP=$(mktemp); SETTINGS_WAS_MISSING=0; if [ -r "$SETTINGS_FILE" ]; then cat "$SETTINGS_FILE" >"$SETTINGS_SNAP"; else : >"$SETTINGS_SNAP"; SETTINGS_WAS_MISSING=1; fi; }
settings_rollback() {   # puts the settings back as they were; a file that did not exist before is removed again
  if [ -n "$SETTINGS_SNAP" ] && [ -f "$SETTINGS_SNAP" ]; then
    if [ "$SETTINGS_WAS_MISSING" = 1 ]; then rm -f "$SETTINGS_FILE"; else cat "$SETTINGS_SNAP" >"$SETTINGS_FILE"; fi
  fi
  rm -f "$SETTINGS_SNAP"; SETTINGS_SNAP=""; return 0
}
settings_discard() { rm -f "$SETTINGS_SNAP"; SETTINGS_SNAP=""; }

settings_prune() {   # forget the limits of drives that are not in any pool any more (a new drive with the same label must not inherit them)
  [ -r "$SETTINGS_FILE" ] || return 0
  local labels tmp mp
  labels=""; for mp in $(all_branches); do labels="$labels$(basename "$mp")"$'\n'; done
  tmp=$(mktemp) || return 0
  awk -F'|' -v L="$labels" 'BEGIN { n = split(L, a, "\n"); for (i = 1; i <= n; i++) have[a[i]] = 1 } $1 == "limit" && !($2 in have) { next } { print }' "$SETTINGS_FILE" >"$tmp"
  cat "$tmp" >"$SETTINGS_FILE" || true
  rm -f "$tmp"
}

branches_of() {   # branches_of main|backup -> mount points, in the order the pool uses them
  local p all ord l ordered
  p=$(role_prefix "$1")
  all=$(fstab_active | awk -v d="$DISKS_DIR/$p" '$2 ~ "^" d "([0-9]+|BOOT)$" {print $2}' | sort -V)
  [ -n "$all" ] || return 0
  # the order you chose with `drives fillorder` (drives not in it follow, sorted), else MAIN1, MAIN2, ...; the boot drive section (MAINBOOT) is always last
  ord=$(setting_get order "$1")
  ordered=$({ for l in $ord; do printf '%s\n' "$DISKS_DIR/$l"; done; printf '%s\n' "$all"; } | awk 'NF && !seen[$0]++' | grep -Fx -f <(printf '%s\n' "$all"))
  { printf '%s\n' "$ordered" | grep -v 'BOOT$'; printf '%s\n' "$ordered" | grep 'BOOT$'; } | grep .
  return 0
}

is_boot_section() { case "$(basename "$1")" in *BOOT) return 0 ;; *) return 1 ;; esac; }   # a mount point such as /mnt/disks/MAINBOOT
boot_image_of() { fstab_active | awk -v m="$1" '$2 == m {print $1; exit}'; }               # the file behind a boot drive section
boot_section_of() { branches_of "$1" | grep 'BOOT$' | head -1; }                           # boot_section_of main|backup

all_branches() { branches_of main; branches_of backup; }

branch_role() {
  case "$(basename "$1")" in
    "$MAIN_PREFIX"[0-9]*|"$MAIN_PREFIX"BOOT) echo main ;;
    *) echo backup ;;
  esac
}

branch_uuid() { fstab_active | awk -v m="$1" '$2 == m {sub(/^UUID=/, "", $1); print $1; exit}'; }
branch_part() {   # the partition of a drive; for a boot drive section, the file it lives in
  local u f
  if is_boot_section "$1"; then f=$(boot_image_of "$1"); [ -f "$f" ] && echo "$f"; return 0; fi
  u=$(branch_uuid "$1"); [ -n "$u" ] && blkid -U "$u" 2>/dev/null
}

fstab_snapshot() {
  FSTAB_SNAP="$FSTAB.bak-drives-$(date +%Y%m%d-%H%M%S)"
  cp -a "$FSTAB" "$FSTAB_SNAP" && log "fstab backup: $FSTAB_SNAP"
}

fstab_rollback() {
  if [ -n "$FSTAB_SNAP" ] && [ -f "$FSTAB_SNAP" ]; then
    cat "$FSTAB_SNAP" >"$FSTAB" && warn "fstab restored from $FSTAB_SNAP"
    ROLLED_BACK=1
    sd_reload
  fi
}

fstab_add() { printf '%s\n' "$1" >>"$FSTAB"; log "fstab add: $1"; }

fstab_remove_mp() {   # comment out active lines whose mount point is $1
  local tmp; tmp=$(mktemp)
  awk -v m="$1" -v d="$(date +%F)" '
    !/^[[:space:]]*#/ && $2 == m { print "# removed by drives " d ": " $0; next }
    { print }' "$FSTAB" >"$tmp" && cat "$tmp" >"$FSTAB"
  rm -f "$tmp"
  settings_prune
  log "fstab remove mount point: $1"
}

cache_opt() {   # mergerfs docs: kernel 6.6 or newer uses cache.files=off, older kernels need auto-full
  local k; k=$(uname -r | sed 's/[^0-9.].*//')
  if [ "$(printf '%s\n6.6\n' "$k" | sort -V | head -1)" = "6.6" ]; then echo off; else echo auto-full; fi
}

branch_minfree() {   # branch_minfree MOUNTPOINT -> the space to keep free on that drive (the limit you set, else 5% of its size), e.g. 48828125K; nothing if unknown
  local sz lim kind num
  mountpoint -q "$1" 2>/dev/null || return 0
  sz=$(df -B1 --output=size "$1" 2>/dev/null | awk 'NR==2 {gsub(/[^0-9]/, "", $1); print $1}')
  [[ "$sz" =~ ^[0-9]+$ ]] && [ "$sz" -gt 0 ] || return 0
  lim=$(setting_get limit "$(basename "$1")"); kind=${lim%% *}; num=${lim#* }
  case "$kind" in   # a limit that does not fit the drive (for example after a smaller drive took its place) is ignored
    pct)   if [[ "$num" =~ ^[0-9]+$ ]] && [ "$num" -ge 1 ] && [ "$num" -le 50 ]; then echo "$(( sz * num / 100 / 1024 ))K"; return 0; fi ;;
    bytes) if [[ "$num" =~ ^[0-9]+$ ]] && [ "$num" -ge 1048576 ] && [ $(( num * 2 )) -le "$sz" ]; then echo "$(( num / 1024 ))K"; return 0; fi ;;
  esac
  echo "$(( sz * POOL_FREE_PERCENT / 100 / 1024 ))K"
}

branch_spec() {   # branch_spec MOUNTPOINT -> "/mnt/disks/MAIN1=RW,48828125K" (the drive with its own free-space limit)
  local f; f=$(branch_minfree "$1")
  if [ -n "$f" ]; then printf '%s=RW,%s' "$1" "$f"; else printf '%s' "$1"; fi
}

branches_string() {   # branches_string main|backup -> the drives of a pool, in order, each with its limit
  local b joined=""
  for b in $(branches_of "$1"); do joined="${joined:+$joined:}$(branch_spec "$b")"; done
  printf '%s' "$joined"
}

pool_policy() {   # pool_policy main|backup -> ff (one drive at a time, the default) or mfs (the drive with the most free space)
  case "$(setting_get policy "$1")" in mfs) echo mfs ;; *) echo ff ;; esac
}

pool_line() {   # pool_line main|backup
  local role=$1 mp b joined req="" opts
  opts=${POOL_OPTS_BASE/cache.files=off/cache.files=$(cache_opt)}
  opts=${opts/category.create=ff/category.create=$(pool_policy "$role")}
  mp=$(role_pool "$role")
  joined=$(branches_string "$role")
  [ -n "$joined" ] || return 1
  for b in $(branches_of "$role"); do req="$req,x-systemd.requires-mounts-for=$b"; done
  printf '%s %s fuse.mergerfs %s,fsname=mergerfs-%s%s 0 0' "$joined" "$mp" "$opts" "$role" "$req"
}

fstab_set_pool() {
  local role=$1 mp line
  mp=$(role_pool "$role")
  fstab_remove_mp "$mp"
  if line=$(pool_line "$role"); then fstab_add "$line"; fi
}

