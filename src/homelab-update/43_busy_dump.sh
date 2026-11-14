pool_devices() {
  if [ -n "${HLU_POOL_DEVS:-}" ]; then printf '%s\n' $HLU_POOL_DEVS; return; fi
  local src dsk
  while read -r src; do
    [[ "$src" == /dev/* ]] || continue
    dsk=$(lsblk -no pkname "$src" 2>/dev/null | head -n 1)
    [ -n "$dsk" ] && printf '%s\n' "$dsk"
  done < <(findmnt -rn -o SOURCE,TARGET 2>/dev/null | awk '$2 ~ "^/mnt/(disks/|storage$|backup$)" {print $1}') | sort -u
}

sectors_written() {
  local d t=0 w
  while read -r d; do
    [ -n "$d" ] || continue
    w=$(awk '{print $7}' "${HLU_SYS_BLOCK:-/sys/block}/$d/stat" 2>/dev/null)
    [[ "$w" =~ ^[0-9]+$ ]] && t=$((t + w))
  done < <(pool_devices)
  echo "$t"
}

busy_reason() {
  if [ -n "${HLU_BUSY:-}" ]; then [ "$HLU_BUSY" = none ] || echo "$HLU_BUSY"; return 0; fi
  if ! ( exec 7>"${HLU_BACKUP_LOCK:-/var/lock/homelab-backup.lock}" && flock -n 7 ) 2>/dev/null; then
    echo "a backup is running"; return 0
  fi
  local a b secs=${HLU_SAMPLE_SECS:-5}
  a=$(sectors_written); sleep "$secs"; b=$(sectors_written)
  if [ $(( (b - a) * 512 / secs )) -gt 300000 ]; then echo "files are being written to a storage pool (for example an upload)"; fi
  return 0
}

dump_dir() {
  if mountpoint -q /mnt/backup 2>/dev/null; then echo "${HLU_DUMP_DIR:-/mnt/backup/db-dumps/pre-update}"; else echo "${HLU_DUMP_DIR:-$STATE_DIR/pre-update-dumps}"; fi
}

# dump_stack_db STACK: dump every PostgreSQL database in the stack. Returns 0 when all are saved or there is nothing to dump.
dump_stack_db() {
  local s=$1 i c img dir stamp user db f n=0 free
  stamp=$(date +%Y%m%d-%H%M%S); dir=$(dump_dir)
  for i in "${!CN[@]}"; do
    [ "${CS[$i]}" = "$s" ] || continue
    c=${CN[$i]}; img=${CI[$i]}
    [[ "${img,,}" == *postgres* ]] || continue
    user=$(docker exec "$c" printenv POSTGRES_USER 2>/dev/null); user=${user:-postgres}
    db=$(docker exec "$c" printenv POSTGRES_DB 2>/dev/null); db=${db:-$user}
    mkdir -p "$dir" 2>/dev/null || { line_bad "Cannot create $dir for the database dump."; return 1; }
    free=$(avail_of 1G "$dir")
    if [ -n "$free" ] && [ "$free" -lt "$MIN_FREE_GB" ]; then line_bad "Only ${free} GB free at $dir; need at least $MIN_FREE_GB for the dump."; return 1; fi
    f="$dir/$c-$stamp.sql.gz"
    if nice -n 19 docker exec "$c" pg_dump -U "$user" "$db" 2>/dev/null | gzip -c >"$f.tmp" && gzip -t "$f.tmp" 2>/dev/null \
       && [ "$(stat -c %s "$f.tmp")" -gt "${HLU_DUMP_MIN:-200}" ]; then
      mv "$f.tmp" "$f"; chmod 600 "$f"
      line_ok "Database dump saved: $f ($(hb "$(stat -c %s "$f")"))"
      # shellcheck disable=SC2012
      ls -1t "$dir/$c"-*.sql.gz 2>/dev/null | tail -n +4 | xargs -r rm -f
      n=$((n + 1))
    else
      rm -f "$f.tmp"; line_bad "The dump of the $c database failed, so $s is not updated."; return 1
    fi
  done
  return 0
}

