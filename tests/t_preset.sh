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
need = {"pool": (1, None), "mirror": (2, 2), "snapraid1": (3, None), "snapraid2": (4, None)}
def ref(i, s):
    s = sorted(s, reverse=True); lo, hi = need[i]
    if len(s) < lo or (hi and len(s) > hi): return ""
    if i == "pool": return sum(s)
    if i == "mirror": return s[1]
    k = 1 if i == "snapraid1" else 2
    return sum(s) - sum(s[:k])
GB = 10 ** 9
sets = [[1000 * GB], [1000 * GB, 1000 * GB], [4000 * GB, 2000 * GB, 2000 * GB], [750 * GB, 1000 * GB, 484 * GB],
        [8000 * GB] * 6, [1000 * GB, 2000 * GB, 3000 * GB, 4000 * GB], [100] * 5, [5, 4, 3, 2, 1, 1, 1]]
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

# --- the command line: words, refusals and help
out=$(bash "$DRIVES" preset nonsense 2>&1); rc=$?
check "an unknown setup is refused with exit 1" "$rc" 1
case "$out" in *"There is no setup called 'nonsense'"*) check "it names the setups" yes yes ;; *) check "it names the setups" "$out" "a message" ;; esac
out=$(bash "$DRIVES" preset pool extra 2>&1); rc=$?
check "an extra word after the setup is refused" "$rc" 1
check "snapraid with no setup built says so" "$(bash "$DRIVES" snapraid status 2>&1 | grep -c 'There is no SnapRAID setup')" 1
check "snapraid with a wrong word is refused" "$(bash "$DRIVES" snapraid explode >/dev/null 2>&1; echo $?)" 1
out=$(bash "$DRIVES" help preset 2>&1); check "help preset names every setup" "$(for id in $PRESET_IDS; do case "$out" in *"$id"*) printf y ;; esac; done)" "yyyy"
check "help presets (the other word) shows the same text" "$(bash "$DRIVES" help presets 2>&1 | head -1)" "sudo drives preset [NAME] [--dry-run] [--yes] [--confirm-erase]"
check "help snapraid exists" "$(bash "$DRIVES" help snapraid 2>&1 | head -1)" "sudo drives snapraid [status|diff|sync|scrub] [--dry-run]"
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
