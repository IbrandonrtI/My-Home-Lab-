#!/usr/bin/env bash
# Tests of `drives preset`: the capacity arithmetic against an independent Python version, the rules about the number of drives,
# and the words people type. (The building itself runs on fake drives in tools/drive-bench.)
# Run: bash tests/t_preset.sh   (last line is OK or FAIL)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVES="$HERE/../scripts/drives"
bad=0; n=0
check() { n=$((n + 1)); if [ "$2" = "$3" ]; then :; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }
ST=$(mktemp -d); trap 'rm -rf "$ST"' EXIT
export DRIVES_TEST=1 DRIVES_STATE_DIR="$ST"
# shellcheck disable=SC1090
source "$DRIVES"
set +e

# --- capacity: every setup, many sets of drive sizes, against the Python reference
python3 - >"$ST/cases" <<'PY'
import random
random.seed(7)
# id: (fewest drives, most drives or None)
need = {"pool": (1, None), "mirror": (2, 2), "snapraid1": (3, None), "snapraid2": (4, None),
        "zfs-stripe": (2, None), "zfs-mirror": (2, None), "zfs-raidz1": (3, None), "zfs-raidz2": (4, None), "zfs-raidz3": (5, None),
        "md-raid0": (2, None), "md-raid1": (2, None), "md-raid5": (3, None), "md-raid6": (4, None), "md-raid10": (4, None)}
def ref(i, s):
    s = sorted(s, reverse=True); lo, hi = need[i]; n = len(s); small = s[-1]
    if n < lo or (hi and n > hi): return ""
    if i in ("pool", "zfs-stripe", "md-raid0"): return sum(s)
    if i == "mirror": return s[1]
    if i in ("zfs-mirror", "md-raid1"): return small
    if i in ("zfs-raidz1", "md-raid5"): return (n - 1) * small
    if i in ("zfs-raidz2", "md-raid6"): return (n - 2) * small
    if i == "zfs-raidz3": return (n - 3) * small
    if i == "md-raid10": return n * small // 2
    k = 1 if i == "snapraid1" else 2
    return sum(s) - sum(s[:k])
GB = 10 ** 9
sets = [[1000 * GB], [1000 * GB, 1000 * GB], [4000 * GB, 2000 * GB, 2000 * GB], [750 * GB, 1000 * GB, 484 * GB],
        [8000 * GB] * 6, [1000 * GB, 2000 * GB, 3000 * GB, 4000 * GB], [100] * 5, [5, 4, 3, 2, 1, 1, 1],
        [4000 * GB, 4000 * GB, 4000 * GB, 4000 * GB, 1000 * GB], [3, 3, 3, 3, 3, 3]]
for _ in range(60): sets.append([random.randint(1, 20) * 250 * GB for _ in range(random.randint(1, 9))])
for s in sets:
    for i in need: print(i, " ".join(map(str, s)), "=", ref(i, s))
PY
cases=0
while IFS= read -r line; do
  want=${line##*= }; head=${line% =*}; id=${head%% *}; sizes=${head#* }
  # shellcheck disable=SC2086
  got=$(preset_capacity "$id" $sizes)
  check "capacity $id $sizes" "$got" "$want"; cases=$((cases + 1))
done <"$ST/cases"
check "no capacity without drives" "$(preset_capacity pool)" ""

# --- the catalog
for id in $PRESET_IDS; do
  check "$id has a title" "$([ -n "$(preset_title "$id")" ] && echo yes)" yes
  check "$id has a text" "$([ -n "$(preset_blurb "$id")" ] && echo yes)" yes
  check "$id: the minimum is at least the protection drives + 1" "$([ "$(preset_min "$id")" -gt "$(preset_parity_count "$id")" ] && echo yes)" yes
done
check "an unknown setup is not known" "$(preset_known nonsense && echo known || echo unknown)" unknown
check "drive counts are written for people" "$(preset_drives_text pool) / $(preset_drives_text mirror) / $(preset_drives_text snapraid1)" "1 or more / exactly 2 / 3 or more"

# --- short names, kinds and the programs a setup needs
check "raidz2 means zfs-raidz2" "$(preset_alias raidz2)" zfs-raidz2
check "raid10 means md-raid10" "$(preset_alias raid10)" md-raid10
check "a full name stays" "$(preset_alias snapraid1)" snapraid1
check "every short name is a known setup" "$(for a in raidz1 raidz2 raidz3 raid0 raid1 raid5 raid6 raid10; do preset_known "$(preset_alias "$a")" && printf y; done)" yyyyyyyy
check "pool is made of separate drives" "$(preset_kind pool)/$(preset_kind mirror)/$(preset_kind snapraid2)" "pool/pool/pool"
check "zfs-raidz1 is a ZFS array" "$(preset_kind zfs-raidz1)" zfs
check "md-raid5 is a RAID array" "$(preset_kind md-raid5)" md
check "arrays are arrays" "$(for id in $PRESET_IDS; do preset_is_array "$id" && printf y; done)" yyyyyyyyyy
check "zfs needs zfsutils-linux when zpool is missing" "$(PATH=/nonexistent preset_tool_hint zfs-raidz1)" "sudo apt install -y zfsutils-linux"
check "raid needs mdadm when it is missing" "$(PATH=/nonexistent preset_tool_hint md-raid5)" "sudo apt install -y mdadm"
check "snapraid needs snapraid when it is missing" "$(PATH=/nonexistent preset_tool_hint snapraid1)" "sudo apt install -y snapraid"
check "a plain pool needs no extra program" "$(PATH=/nonexistent preset_tool_hint pool)" ""
check "every setup has a minimum above its protection" "$(for id in $PRESET_IDS; do [ "$(preset_min "$id")" -ge 1 ] && printf y; done)" yyyyyyyyyyyyyy

# --- the array bookkeeping: the record keeps the drives, the guard refuses the pool commands
echo "zfs-raidz1|2026-11-01|/dev/null /dev/zero" >"$PRESET_FILE"
check "the record says an array exists" "$(array_active && echo yes || echo no)" yes
check "the recorded drives are listed" "$(array_members | wc -l)" 2
check "the guard refuses connect on an array" "$(array_guard 2>/dev/null && echo allowed || echo refused)" refused
check "the guard explains itself" "$(array_guard 2>&1 | grep -c 'does not apply to an array')" 1
rm -f "$PRESET_FILE"
check "no record, no array" "$(array_active && echo yes || echo no)" no
check "the guard allows commands without an array" "$(array_guard && echo allowed || echo refused)" allowed
check "a snapraid record is not an array" "$(echo 'snapraid1|2026-11-01|TMAIN1' >"$PRESET_FILE"; array_active && echo yes || echo no; rm -f "$PRESET_FILE")" no

# --- the extras: which setups can have a hot spare / an SSD cache, and what the record keeps
check "hot spare: only setups that survive a dead drive" "$(for id in $PRESET_IDS; do array_can_spare "$id" && printf '%s ' "$id"; done)" "zfs-mirror zfs-raidz1 zfs-raidz2 zfs-raidz3 md-raid1 md-raid5 md-raid6 md-raid10 "
check "SSD cache: ZFS only" "$(for id in $PRESET_IDS; do array_can_cache "$id" && printf '%s ' "$id"; done)" "zfs-stripe zfs-mirror zfs-raidz1 zfs-raidz2 zfs-raidz3 "
echo "zfs-raidz1|2026-11-01|/dev/null /dev/zero spare=/dev/full cache=/dev/tty encrypted" >"$PRESET_FILE"
check "the record keeps every token" "$(array_tokens | wc -l)" 5
check "members include spare and cache drives" "$(array_members | tr '\n' ' ')" "/dev/null /dev/zero /dev/full /dev/tty "
check "encrypted is read from the record" "$(array_encrypted && echo yes || echo no)" yes
check "a record without encrypted is not encrypted" "$(echo 'zfs-raidz1|2026-11-01|/dev/null' >"$PRESET_FILE"; array_encrypted && echo yes || echo no)" no
echo "zfs-raidz1|2026-11-01|/dev/null /dev/zero" >"$PRESET_FILE"
preset_record_add spare=/dev/full
check "a spare is added to the record" "$(array_tokens | tr '\n' ' ')" "/dev/null /dev/zero spare=/dev/full "
check "the record keeps its first fields" "$(cut -d'|' -f1,2 "$PRESET_FILE")" "zfs-raidz1|2026-11-01"
check "the state words tell spare from cache" "$(array_kind_text spare) / $(array_kind_text cache)" "connected (hot spare) / connected (SSD read cache)"
rm -f "$PRESET_FILE"
check "--spare alone is a yes" "$(extra_wanted 1 "q" </dev/null && echo yes || echo no)" yes
check "--yes alone does not add an extra" "$(ASSUME_YES=1 extra_wanted 0 "q" </dev/null && echo yes || echo no)" no
KEY_DIR="$ST/keys"
key=$(key_make tank 32); check "a key file has the right size" "$(wc -c <"$key" | tr -d ' ')" 32
check "only root can read the key file" "$(stat -c %a "$key")" 400
check "a key is never overwritten" "$(key_make tank 32 >/dev/null 2>&1 && echo overwritten || echo refused)" refused
rm -rf "$KEY_DIR"

# --- the command line: words, refusals and help
out=$(bash "$DRIVES" preset nonsense 2>&1); rc=$?
check "an unknown setup is refused with exit 1" "$rc" 1
case "$out" in *"There is no setup called 'nonsense'"*) check "it names the setups" yes yes ;; *) check "it names the setups" "$out" "a message" ;; esac
out=$(bash "$DRIVES" preset pool extra 2>&1); rc=$?
check "an extra word after the setup is refused" "$rc" 1
check "snapraid with no setup built says so" "$(bash "$DRIVES" snapraid status 2>&1 | grep -c 'There is no SnapRAID setup')" 1
check "snapraid with a wrong word is refused" "$(bash "$DRIVES" snapraid explode >/dev/null 2>&1; echo $?)" 1
out=$(bash "$DRIVES" help preset 2>&1); want=$(for id in $PRESET_IDS; do printf y; done)
check "help preset names every setup" "$(for id in $PRESET_IDS; do case "$out" in *"$id"*) printf y ;; esac; done)" "$want"
check "there are fourteen setups" "$(echo $PRESET_IDS | wc -w)" 14
check "help raid words work through the short names" "$(bash "$DRIVES" help preset 2>&1 | grep -c 'raidz1')" 2
check "help presets (the other word) shows the same text" "$(bash "$DRIVES" help presets 2>&1 | head -1)" "sudo drives preset [NAME] [--dry-run] [--yes] [--confirm-erase] [--spare] [--cache] [--encrypt]"
check "help snapraid exists" "$(bash "$DRIVES" help snapraid 2>&1 | head -1)" "sudo drives snapraid [status|diff|sync|scrub] [--dry-run]"
check "help spare exists" "$(bash "$DRIVES" help spare 2>&1 | head -1)" "sudo drives spare [--dry-run]"
check "help cache exists" "$(bash "$DRIVES" help cache 2>&1 | head -1)" "sudo drives cache [--dry-run]"
hp=$(bash "$DRIVES" help preset 2>&1)
check "help preset explains every option" "$(for o in --spare --cache --encrypt; do case "$hp" in *"    $o "*) printf y ;; esac; done)" yyy
check "--spare outside preset is refused" "$(bash "$DRIVES" status --spare >/dev/null 2>&1; echo $?)" 1
check "--encrypt outside preset is refused" "$(bash "$DRIVES" list --encrypt 2>&1 | grep -c 'work with: preset')" 1
check "spare without an array says so" "$(bash "$DRIVES" spare 2>&1 | grep -c -i 'array')" 1
usage=$(bash "$DRIVES" help 2>&1)
case "$usage" in *"preset        build a whole setup"*) check "the command list shows preset" yes yes ;; *) check "the command list shows preset" no yes ;; esac

# --- the SnapRAID files
mkdir -p "$ST/snap"; SNAPRAID_CONF="$ST/snap/conf"; SNAPRAID_CRON="$ST/snap/cron"; SNAPRAID_CONTENT_DIR="$ST/snap/content"; SNAPRAID_LOG="$ST/snap/log"
snapraid_cron_write
check "the schedule updates at 04:00 every night" "$(grep -c '^0 4 \* \* \* root snapraid -c .* sync' "$SNAPRAID_CRON")" 1
check "the schedule checks part of the files on the 1st" "$(grep -c '^0 5 1 \* \* root snapraid -c .* scrub' "$SNAPRAID_CRON")" 1
check "the schedule file ends with a new line" "$(tail -c1 "$SNAPRAID_CRON" | od -An -c | tr -d ' ')" '\n'
snapraid_forget
check "taking it apart removes the schedule and the settings" "$([ ! -e "$SNAPRAID_CRON" ] && [ ! -e "$SNAPRAID_CONF" ] && echo yes)" yes

[ "$bad" -eq 0 ] && echo "ok   $n checks ($cases capacity cases)"
echo "$([ "$bad" -eq 0 ] && echo OK || echo FAIL)"
exit "$bad"
