#!/usr/bin/env bash
# Timeshift must skip the boot drive sections: sudo drives timeshift, the automatic fix, the warning in status and in the self-test.
# Needs root only because scripts/drives insists on it; no drives are touched. Run: bash tests/t_timeshift.sh   (last line is OK or FAIL)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVES="$HERE/../scripts/drives"
SELFTEST="$HERE/../scripts/homelab-selftest"
bad=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
if [ "$(id -u)" != 0 ] || ! command -v python3 >/dev/null; then echo "skipped: needs root and python3"; echo OK; exit 0; fi

S=$(mktemp -d); trap 'rm -rf "$S"' EXIT
export DRIVES_TEST=1 DRIVES_STATE_DIR="$S" TIMESHIFT_CONF="$S/timeshift.json"
SEC="$S/boot-sections"
PAT="$SEC/**"
D="bash $DRIVES"
excl() { python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1])).get("exclude", [])))' "$TIMESHIFT_CONF"; }

# 1. no Timeshift here: nothing to do, no file is made
OUT=$($D timeshift 2>&1); rc=$?
check "no Timeshift: exit 0" "$rc" "0"
case "$OUT" in *"not set up"*) r=yes ;; *) r=no ;; esac; check "no Timeshift: says so" "$r" "yes"
[ ! -e "$TIMESHIFT_CONF" ] && r=yes || r=no; check "no Timeshift: no settings file is made" "$r" "yes"

# 2. Timeshift with its own exclusions and other settings: the pattern is added, nothing else changes
cat >"$TIMESHIFT_CONF" <<'EOF'
{
  "backup_device_uuid" : "abc-123",
  "schedule_daily" : "true",
  "count_daily" : "5",
  "exclude" : [
    "/home/brandon/**"
  ],
  "exclude-apps" : [
  ]
}
EOF
chmod 640 "$TIMESHIFT_CONF"
mkdir -p "$SEC"; : >"$SEC/main.img"
OUT=$($D status 2>&1)
case "$OUT" in *"Timeshift would copy the boot drive section"*) r=yes ;; *) r=no ;; esac; check "status warns when a section exists and Timeshift does not skip it" "$r" "yes"
OUT=$($D timeshift --dry-run 2>&1)
case "$OUT" in *"dry run: nothing was changed"*) r=yes ;; *) r=no ;; esac; check "dry run says it changes nothing" "$r" "yes"
check "dry run: the exclude list is unchanged" "$(excl)" "/home/brandon/**"
OUT=$(printf 'n\n' | $D timeshift 2>&1)
check "answering no: the exclude list is unchanged" "$(excl)" "/home/brandon/**"
OUT=$(printf 'y\n' | $D timeshift 2>&1); rc=$?
check "answering yes: exit 0" "$rc" "0"
check "the pattern is added and the user's own one stays" "$(excl)" "/home/brandon/** $PAT"
check "other settings are kept" "$(python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); print(c["backup_device_uuid"], c["count_daily"], c["schedule_daily"])' "$TIMESHIFT_CONF")" "abc-123 5 true"
check "the file permissions are kept" "$(stat -c %a "$TIMESHIFT_CONF")" "640"
check "the old settings are saved next to it" "$(ls "$TIMESHIFT_CONF".bak-homelab-* 2>/dev/null | wc -l)" "1"
check "the saved copy is the old file" "$(python3 -c 'import json,glob,sys; print(" ".join(json.load(open(glob.glob(sys.argv[1]+".bak-homelab-*")[0]))["exclude"]))' "$TIMESHIFT_CONF")" "/home/brandon/**"
OUT=$($D status 2>&1)
case "$OUT" in *"Timeshift would copy"*) r=no ;; *) r=yes ;; esac; check "status no longer warns" "$r" "yes"

# 3. running it again changes nothing
before=$(md5sum <"$TIMESHIFT_CONF")
OUT=$($D timeshift 2>&1)
case "$OUT" in *"already skips"*) r=yes ;; *) r=no ;; esac; check "second run: says it is already fine" "$r" "yes"
check "second run: the file is the same" "$(md5sum <"$TIMESHIFT_CONF")" "$before"
check "second run: no second saved copy" "$(ls "$TIMESHIFT_CONF".bak-homelab-* | wc -l)" "1"

# 4. no "exclude" key at all, and --yes
echo '{ "schedule_daily" : "true" }' >"$TIMESHIFT_CONF"
OUT=$($D timeshift --yes 2>&1)
check "a file without an exclude list gets one" "$(excl)" "$PAT"

# 5. a settings file that is not valid JSON is never touched
echo 'this is not json' >"$TIMESHIFT_CONF"
OUT=$($D timeshift --yes 2>&1); rc=$?
check "broken settings: exit 1" "$rc" "1"
check "broken settings: the file is untouched" "$(cat "$TIMESHIFT_CONF")" "this is not json"
case "$OUT" in *"Settings > Filters"*|*"Timeshift > Settings"*) r=yes ;; *) r=no ;; esac; check "broken settings: tells him what to do by hand" "$r" "yes"

# 6. no section file and no Timeshift exclusion: status stays quiet (nothing to protect yet)
rm -f "$SEC"/*.img
echo '{ "exclude" : [] }' >"$TIMESHIFT_CONF"
OUT=$($D status 2>&1)
case "$OUT" in *"Timeshift would copy"*) r=no ;; *) r=yes ;; esac; check "status is quiet when there is no section" "$r" "yes"

# 7. the help and the command list know the command
case "$($D help timeshift 2>&1)" in *"exclude list"*) r=yes ;; *) r=no ;; esac; check "help timeshift explains it" "$r" "yes"
case "$($D help 2>&1)" in *"timeshift "*"skip the boot drive sections"*) r=yes ;; *) r=no ;; esac; check "the command is in the list" "$r" "yes"

# 8. the self-test (part 2) checks it as well
if [ -x "$SELFTEST" ] || [ -f "$SELFTEST" ]; then
  # run only part 2 of the self-test, pointed at the temporary folder (HOMELAB_USER=root keeps the report out of real homes)
  ST="$S/selftest"; sed -e "s#^BOOT_SECTIONS=.*#BOOT_SECTIONS=$SEC#" -e "s#^REPORT=.*#REPORT=$S/report.txt#" -e '/^# -* run it$/,$d' "$SELFTEST" >"$ST"
  printf 'emit "x"\npart_state\n' >>"$ST"
  : >"$SEC/main.img"
  echo '{ "exclude" : [] }' >"$TIMESHIFT_CONF"
  OUT=$(HOMELAB_USER=root bash "$ST" 2>&1 </dev/null)
  case "$OUT" in *"Timeshift does not skip"*"sudo drives timeshift"*) r=yes ;; *) r=no ;; esac; check "self-test warns when Timeshift does not skip the section" "$r" "yes"
  printf '{ "exclude" : ["%s"] }\n' "$PAT" >"$TIMESHIFT_CONF"
  OUT=$(HOMELAB_USER=root bash "$ST" 2>&1 </dev/null)
  case "$OUT" in *"Timeshift skips the boot drive sections"*) r=yes ;; *) r=no ;; esac; check "self-test is happy when it does" "$r" "yes"
fi

echo "$([ "$bad" -eq 0 ] && echo OK || echo FAIL)"
exit "$bad"
