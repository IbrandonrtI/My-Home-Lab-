boot_free_bytes() { mkdir -p "$BOOT_SECTION_DIR" 2>/dev/null; avail_bytes "$BOOT_SECTION_DIR"; }
boot_total_bytes() { mkdir -p "$BOOT_SECTION_DIR" 2>/dev/null; df -B1 --output=size "$BOOT_SECTION_DIR" 2>/dev/null | awk 'NR==2 {gsub(/[^0-9]/, "", $1); print $1}'; }

timeshift_pattern() { printf '%s/**' "$BOOT_SECTION_DIR"; }
timeshift_state() {
  [ -f "$TIMESHIFT_CONF" ] || { echo none; return 0; }
  python3 - "$TIMESHIFT_CONF" "$(timeshift_pattern)" <<'PY' 2>/dev/null || echo unreadable
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    print("unreadable"); sys.exit(0)
ex = cfg.get("exclude", [])
print("ok" if isinstance(ex, list) and sys.argv[2] in ex else "missing")
PY
}
# Add the pattern to the Timeshift settings (the old file is kept next to it). Returns 0 when it is in place.
timeshift_exclude_add() {
  local pat bak; pat=$(timeshift_pattern)
  bak="$TIMESHIFT_CONF.bak-homelab-$(date +%Y%m%d-%H%M%S)"
  cp -p "$TIMESHIFT_CONF" "$bak" || return 1
  if ! python3 - "$TIMESHIFT_CONF" "$pat" <<'PY' >&2
import json, os, sys
path, pat = sys.argv[1], sys.argv[2]
cfg = json.load(open(path))
ex = cfg.get("exclude")
if not isinstance(ex, list):
    ex = []
if pat not in ex:
    ex.append(pat)
cfg["exclude"] = ex
tmp = path + ".new"
with open(tmp, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
os.chmod(tmp, os.stat(path).st_mode & 0o777)
os.replace(tmp, path)
PY
  then cp -p "$bak" "$TIMESHIFT_CONF"; return 1; fi
  [ "$(timeshift_state)" = ok ] || { cp -p "$bak" "$TIMESHIFT_CONF"; return 1; }
  log "added $pat to the Timeshift exclude list (old settings: $bak)"
  return 0
}
timeshift_protect() {
  local st; st=$(timeshift_state)
  case "$st" in
    ok|none) return 0 ;;
    missing) if timeshift_exclude_add; then
               say "Timeshift is set up on this machine and now skips $BOOT_SECTION_DIR, so its snapshots do not include the section."
             else
               note "Timeshift is set up, but the exclusion for $BOOT_SECTION_DIR could not be added to $TIMESHIFT_CONF. Run:  sudo drives timeshift"
             fi ;;
    *) note "Timeshift's settings ($TIMESHIFT_CONF) could not be read. Make sure its exclude list has: $(timeshift_pattern)" ;;
  esac
  return 0
}
timeshift_warn_text() {
  ls "$BOOT_SECTION_DIR"/*.img >/dev/null 2>&1 || return 0
  case "$(timeshift_state)" in
    missing) echo "Timeshift would copy the boot drive section into every snapshot and fill the boot drive. To fix this, run:  sudo drives timeshift" ;;
    unreadable) echo "Timeshift's settings ($TIMESHIFT_CONF) could not be read; make sure its exclude list has $(timeshift_pattern)" ;;
  esac
  return 0
}
# `timeshift`: keep the pools out of Timeshift snapshots.
timeshift_flow() {
  local st; st=$(timeshift_state)
  case "$st" in
    none)
      say "Timeshift is not set up on this machine ($TIMESHIFT_CONF does not exist), so nothing needs to change."
      say "If Timeshift is installed later, run  sudo drives timeshift  again so that it skips $BOOT_SECTION_DIR."
      return 0 ;;
    ok)
      say "Timeshift already skips $BOOT_SECTION_DIR. Nothing was changed."
      return 0 ;;
    unreadable)
      note "Timeshift's settings ($TIMESHIFT_CONF) could not be read, so nothing was changed."
      note "Open Timeshift > Settings > Filters and add:  $(timeshift_pattern)"
      return 1 ;;
  esac
  say "Timeshift copies the whole boot drive. The boot drive sections ($BOOT_SECTION_DIR) are large files that change every day,"
  say "so each snapshot would contain a full extra copy of them and fill the boot drive."
  say "This can be fixed by adding  $(timeshift_pattern)  to the exclude list in $TIMESHIFT_CONF. The previous file is kept next to it."
  if [ "$DRY_RUN" = 1 ]; then say "(dry run: nothing was changed)"; return 0; fi
  yn "Add it now?" || { say "Nothing was changed."; return 0; }
  if timeshift_exclude_add; then
    say "Done. New snapshots skip the boot drive sections. Earlier snapshots still contain the copies and can be deleted with  sudo timeshift --delete"
  else
    note "Could not change $TIMESHIFT_CONF. Nothing was changed."; return 1
  fi
}

lvm_unused_bytes() {
  command -v lvs >/dev/null 2>&1 || return 0
  local src; src=$(findmnt -no SOURCE / 2>/dev/null) || return 0
  [ -n "$src" ] || return 0
  lvs --noheadings --nosuffix --units b -o vg_free "$src" 2>/dev/null | awk 'NF {printf "%d", $1; exit}'
}

# bootsection_attach ROLE REUSE: make the section file of that pool (new or saved) the last drive of the pool.
bootsection_attach() {
  local role=$1 reuse=$2 label mp img
  label="$(role_prefix "$role")BOOT"; mp="$DISKS_DIR/$label"; img="$BOOT_SECTION_DIR/$role.img"
  crit_enter || true
  stop_containers "$(role_pool "$role")"
  fstab_snapshot
  ensure_mp "$mp"
  fstab_add "$img  $mp  ext4  $BOOT_OPTS  0  0"
  sd_reload
  if ! mount_fstab "$mp"; then
    fstab_rollback
    [ "$reuse" = 1 ] || rm -f "$img"
    start_containers
    die "Could not mount the section at $mp. fstab was restored."
  fi
  if ! absorb_plain_pool "$role" "$mp"; then
    fstab_rollback; pool_umount "$mp"; [ "$reuse" = 1 ] || rm -f "$img"; start_containers
    die "The files in $(role_pool "$role") could not be moved into the section. fstab was restored."
  fi
  if [ "$reuse" = 0 ] && [ "$role" = main ]; then give_to_owner "$mp"; fi
  if ! apply_pool "$role"; then
    fstab_rollback; pool_umount "$mp"; [ "$reuse" = 1 ] || rm -f "$img"; start_containers
    die "The $role pool did not mount. fstab was restored. Check: sudo drives status"
  fi
  start_containers
  name_store_put "$label" "$(pretty_size "$(stat -c %s "$img")") boot drive section"
  timeshift_protect
  say ""
  say "Done. $(branch_name "$mp") is part of the $role pool ($(role_pool "$role")). The pool uses it last."
  log "connected $label ($img) to $role"
  crit_release
  return 0
}

# `bootsection`: use part of the boot drive as a drive of Main or Backup.
bootsection_flow() {
  array_guard || return 1
  need_tools || return 1
  command -v fallocate >/dev/null 2>&1 || { note "The tool 'fallocate' is missing (package util-linux)."; return 1; }
  local role idx label mp img free old=0 max min keep gb bytes reuse=0 other prompt total
  total=$(boot_total_bytes)
  if [ -n "$total" ] && [ "$total" -le "$BOOT_SMALL_BYTES" ]; then
    note "The boot drive is only $(pretty_size "$total"). The system and the apps need $(pretty_size "$BOOT_KEEP_FREE_BYTES") of it, so no part of it can be used for a storage pool."
    local lvm; lvm=$(lvm_unused_bytes)
    if [[ "${lvm:-0}" =~ ^[0-9]+$ ]] && [ "${lvm:-0}" -ge 21474836480 ]; then
      note "But the system volume is LVM and the drive has $(pretty_size "$lvm") that is not used (the installer created a small volume)."
      note "Give it to the system first with  sudo homelab-setup growdisk  (it asks first and erases nothing). Then run this again."
    else
      note "Connect a separate drive instead (sudo drives). Nothing was changed."
    fi
    return 1
  fi
  idx=$(choose "Add a boot drive section to which storage? " "Main pool (photos and files used by your services)" "Backup pool (daily copy of the Main pool)") || return 1
  if [ "$idx" = 0 ]; then role=main; else role=backup; fi
  other=$(other_role "$role")
  if [ -n "$(boot_section_of "$role")" ]; then
    say "The $role pool already has a boot drive section: $(branch_name "$(boot_section_of "$role")")."
    say "To change its size, remove it (sudo drives > Add or remove drives > Disconnect) and add it again."
    return 1
  fi
  pool_can_grow "$role" "a section" || return 1
  label="$(role_prefix "$role")BOOT"; mp="$DISKS_DIR/$label"; img="$BOOT_SECTION_DIR/$role.img"
  mkdir -p "$BOOT_SECTION_DIR"; chmod 700 "$BOOT_SECTION_DIR" 2>/dev/null || true

  if [ -f "$img" ]; then
    old=$(stat -c %s "$img")
    say "A boot drive section of $(pretty_size "$old") that was used for the $role pool before is still saved."
    idx=$(choose "Choose an action: " "Use it again, with its files" "Delete it and make a new one") || return 1
    [ "$idx" = 0 ] && reuse=1
  fi

  if [ "$reuse" = 0 ]; then
    say ""
    say "Warning: this uses part of the boot drive."
    say "  - The boot drive also holds the operating system and the apps. If it fails, everything in this section is lost too."
    say "  - The space is taken from the boot drive immediately and stays reserved, even while the section is empty."
    say "  - The section is the last drive the $role pool uses. It receives files only when the other $role drives are full."
    if [ "$role" = backup ]; then
      say "  - A backup on the boot drive helps if a Main drive fails, but not if the boot drive fails, because the backup is lost with it."
    fi
    if [ -n "$(boot_section_of "$other")" ]; then
      say "  - The $other storage also has a section on the boot drive. Files kept only in those sections have no safe copy."
    fi
    keep=$BOOT_KEEP_FREE_BYTES; min=$BOOT_MIN_BYTES
    free=$(( $(boot_free_bytes) + old ))
    max=$(( free - keep ))
    max=$(( max / BOOT_UNIT_BYTES * BOOT_UNIT_BYTES ))
    say ""
    say "Free space on the boot drive now: $(pretty_size "$free"). It always keeps at least $(pretty_size "$keep") free for the system and other services."
    if [ "$max" -lt "$min" ]; then
      note "A section would have to be at least $(pretty_size "$min"), but at most $(pretty_size "$(( max > 0 ? max : 0 ))") can be used. Nothing was changed."
      return 1
    fi
    say "A section can be from $(( min / BOOT_UNIT_BYTES )) $BOOT_UNIT_NAME to $(( max / BOOT_UNIT_BYTES )) $BOOT_UNIT_NAME."
    say "The pool stops placing files in the section when only ${POOL_FREE_PERCENT}% of it is left, as on every other drive."
    typed "CONTINUE" "Type CONTINUE to continue, or press Enter to cancel: " || { say "Cancelled. Nothing was changed."; return 1; }
    while :; do
      prompt="How many $BOOT_UNIT_NAME should the section have? [$(( min / BOOT_UNIT_BYTES )) to $(( max / BOOT_UNIT_BYTES )) $BOOT_UNIT_NAME, Enter to cancel]: "
      gb=$(ask "$prompt"); gb=${gb//[GgMm][Bb]/}; gb=${gb//[GgMm]/}; gb=${gb// /}
      [ -n "$gb" ] || { say "Cancelled. Nothing was changed."; return 1; }
      if [[ "$gb" =~ ^[0-9]+$ ]]; then
        bytes=$(( gb * BOOT_UNIT_BYTES ))
        [ "$bytes" -lt "$min" ] && { note "The size is too small. The smallest section is $(pretty_size "$min")."; continue; }
        [ "$bytes" -gt "$max" ] && { note "The size is too large. The boot drive must keep $(pretty_size "$keep") free, so the most is $(( max / BOOT_UNIT_BYTES )) $BOOT_UNIT_NAME."; continue; }
        break
      fi
      note "Enter a number of $BOOT_UNIT_NAME, for example 100."
    done
    say "The section will have $(pretty_size "$bytes") ($(role_pool "$role"), last in line)."
    yn "Make it now?" || { say "Cancelled. Nothing was changed."; return 1; }
    pre_change "Reserve $(pretty_size "$bytes") on the boot drive and format it as a new drive section." \
               "Stop the containers that use the $role pool briefly." \
               "Add the section to the $role pool as its last drive, then start the containers again." && return 0
    [ "$old" -gt 0 ] && rm -f "$img"
    if ! fallocate -l "$bytes" "$img" 2>/dev/null; then rm -f "$img"; die "Could not reserve $(pretty_size "$bytes") on the boot drive."; fi
    if ! mkfs.ext4 -F -q -L "$label" -m 0 "$img" >&2; then rm -f "$img"; die "Could not format the section."; fi
    log "made the boot drive section $img ($bytes bytes) for $role"
  fi

  if [ "$reuse" = 1 ]; then
    pre_change "Use the saved boot drive section again, with its files." \
               "Stop the containers that use the $role pool briefly." \
               "Add the section to the $role pool as its last drive, then start the containers again." && return 0
  fi
  bootsection_attach "$role" "$reuse"
}


bootsection_limits() {
  local total free max small=0
  total=$(boot_total_bytes); free=$(boot_free_bytes)
  [[ "${free:-}" =~ ^[0-9]+$ ]] || free=0
  if [[ "${total:-}" =~ ^[0-9]+$ ]] && [ "$total" -le "$BOOT_SMALL_BYTES" ]; then small=1; fi
  max=$(( free - BOOT_KEEP_FREE_BYTES ))
  [ "$max" -gt 0 ] || max=0
  max=$(( max / BOOT_UNIT_BYTES * BOOT_UNIT_BYTES ))
  echo "$BOOT_MIN_BYTES $max $BOOT_UNIT_BYTES $small"
}
bootsection_limits_json() {
  local lim min max unit small
  lim=$(bootsection_limits); read -r min max unit small <<<"$lim"
  printf '{"min_bytes":%s,"max_bytes":%s,"unit_bytes":%s,"unit":%s,"small":%s,"main":%s,"backup":%s}' "$(json_num "$min")" "$(json_num "$max")" "$(json_num "$unit")" "$(json_str "$BOOT_UNIT_NAME")" \
    "$([ "$small" = 1 ] && echo true || echo false)" "$([ -n "$(boot_section_of main)" ] && echo true || echo false)" "$([ -n "$(boot_section_of backup)" ] && echo true || echo false)"
}

# Control panel: make part of the boot drive a drive of Main or Backup (PANEL_ROLE, PANEL_UNITS = size in GB).
panel_bootadd_flow() {
  local role=$PANEL_ROLE units=$PANEL_UNITS label mp img min max unit small bytes lim
  array_guard || return 1
  need_tools || return 1
  command -v fallocate >/dev/null 2>&1 || { note "The tool 'fallocate' is missing (package util-linux)."; return 1; }
  lim=$(bootsection_limits); read -r min max unit small <<<"$lim"
  if [ "$small" = 1 ]; then note "The boot drive is too small to provide a section for a storage pool. Nothing was changed."; return 1; fi
  if [ -n "$(boot_section_of "$role")" ]; then note "The $role pool already has a boot drive section. Remove it first to create one of a different size. Nothing was changed."; return 1; fi
  label="$(role_prefix "$role")BOOT"; mp="$DISKS_DIR/$label"; img="$BOOT_SECTION_DIR/$role.img"
  if [ -f "$img" ]; then note "A boot drive section that was used for the $role pool earlier is still saved. Use it or delete it with  sudo drives  on the server. Nothing was changed."; return 1; fi
  pool_can_grow "$role" "a section" || return 1
  [[ "$units" =~ ^[0-9]{1,6}$ ]] || { note "Choose a size in $BOOT_UNIT_NAME. Nothing was changed."; return 1; }
  bytes=$(( units * unit ))
  if [ "$bytes" -lt "$min" ]; then note "The size is too small. The smallest section is $(pretty_size "$min"). Nothing was changed."; return 1; fi
  if [ "$bytes" -gt "$max" ]; then note "The size is too large. The boot drive must keep $(pretty_size "$BOOT_KEEP_FREE_BYTES") free, so the most is $(( max / unit )) $BOOT_UNIT_NAME. Nothing was changed."; return 1; fi
  typed "CONTINUE" "Type CONTINUE to continue: " || { say "Cancelled. Nothing was changed."; return 1; }
  mkdir -p "$BOOT_SECTION_DIR"; chmod 700 "$BOOT_SECTION_DIR" 2>/dev/null || true
  pre_change "Reserve $(pretty_size "$bytes") on the boot drive and format it as a new drive section." \
             "Stop the containers that use the $role pool briefly." \
             "Add the section to the $role pool as its last drive, then start the containers again." && return 0
  progress_for "$PROG_ITEM" 10 "Reserving the space"
  if ! fallocate -l "$bytes" "$img" 2>/dev/null; then rm -f "$img"; die "Could not reserve $(pretty_size "$bytes") on the boot drive."; fi
  if ! mkfs.ext4 -F -q -L "$label" -m 0 "$img" >&2; then rm -f "$img"; die "Could not format the section."; fi
  log "made the boot drive section $img ($bytes bytes) for $role"
  bootsection_attach "$role" 0
}

# Control panel: move a boot drive section to the other pool. keep = move the section with its files; erase = create a new, empty section of the same size.
bootmove_flow() {
  local mp=$1 role newrole oldname img size newlabel newimg keep=$PANEL_KEEP lim min max unit small
  role=$(branch_role "$mp"); newrole=$(other_role "$role"); oldname=$(branch_name "$mp"); img=$(boot_image_of "$mp")
  [ "$PANEL_MODE" = 1 ] || { note "A boot drive section is moved in the Drives tab of the dashboard. Here, remove it (sudo drives > Add or remove drives > Disconnect) and add one to the other pool (Use part of the boot drive)."; return 1; }
  [ -f "$img" ] || die "The file behind $oldname is not there. Nothing was changed."
  size=$(stat -c %s "$img")
  if [ -n "$(boot_section_of "$newrole")" ]; then note "The $newrole pool already has a boot drive section. Nothing was changed."; return 1; fi
  pool_can_grow "$newrole" "a section" || return 1
  newlabel="$(role_prefix "$newrole")BOOT"; newimg="$BOOT_SECTION_DIR/$newrole.img"
  [ ! -e "$newimg" ] || { note "A saved boot drive section for the $newrole pool already exists ($newimg). Nothing was changed."; return 1; }
  if [ "$keep" = yes ]; then
    typed KEEP "Type KEEP to move the section with its files: " || { say "Cancelled. Nothing was changed."; return 1; }
    KEEP_IMG=1
  else
    typed ERASE "Type ERASE to move the section as a new, empty one: " || { say "Cancelled. Nothing was changed."; return 1; }
    KEEP_IMG=0
  fi
  say "$oldname moves from the $role pool to the $newrole pool."
  PROG_LO=0; PROG_HI=55
  detach_branch "$mp" "Then put the section into the $newrole pool." || { PROG_HI=100; KEEP_IMG=0; return 1; }
  [ "$DRY_RUN" = 1 ] && { PROG_HI=100; KEEP_IMG=0; return 0; }
  KEEP_IMG=0
  PENDING_NOTE="$oldname already left the $role pool and was not added to the $newrole pool."
  PROG_LO=55; PROG_HI=100
  if [ "$keep" = yes ]; then
    mv "$img" "$newimg" || die "Could not move the section file. It is at $img."
    e2label "$newimg" "$newlabel" || die "Could not rename the section. It is at $newimg."
  else
    if ! fallocate -l "$size" "$newimg" 2>/dev/null; then rm -f "$newimg"; die "Could not reserve $(pretty_size "$size") on the boot drive."; fi
    if ! mkfs.ext4 -F -q -L "$newlabel" -m 0 "$newimg" >&2; then rm -f "$newimg"; die "Could not format the section."; fi
  fi
  bootsection_attach "$newrole" "$([ "$keep" = yes ] && echo 1 || echo 0)" || return 1
  PROG_LO=0; PENDING_NOTE=""
  return 0
}
