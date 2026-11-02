#!/usr/bin/env bash
# The drive-name helpers in scripts/drives were rewritten to start no programs (tr, sed, grep, awk). This test runs the OLD versions
# (copied below) and the new ones on the same inputs and demands the same answer: model names of every maker in the table, odd
# characters, many sizes around the TB / GB / MB limits.
# Run: bash tests/t_namefast.sh   (last line is OK or FAIL; nothing outside a temp folder is touched)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bad=0; n=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
export DRIVES_TEST=1 DRIVES_STATE_DIR="$TMP/state" FSTAB="$TMP/fstab"; : >"$FSTAB"
# shellcheck disable=SC1091
source "$HERE/../scripts/drives"
set +e

old_drive_brand() {
  local text pat name
  text=$(printf '%s' "$1" | tr 'a-z_' 'A-Z ' | tr -s ' ' | sed 's/^ //; s/ $//')
  while IFS=$'\t' read -r pat name; do
    if printf '%s' "$text" | grep -Eq -- "$pat"; then printf '%s' "$name"; return 0; fi
  done <<<"$BRAND_TABLE"
  return 0
}
old_pretty_size() {
  awk -v b="$1" 'BEGIN { if (b >= 0.95e12) { v = int(b / 1e11 + 0.5) / 10; printf "%g TB", v } else if (b >= 1e9) printf "%d GB", int(b / 1e9 + 0.5); else printf "%d MB", int(b / 1e6 + 0.5) }'
}
old_clean_name() { printf '%s' "$1" | tr '_' ' ' | sed 's/[^A-Za-z0-9 .()+,-]/ /g' | tr -s ' ' | sed 's/^[ .-]*//; s/[ .-]*$//'; }
old_ssd_text() { printf '%s' "$1" | tr 'a-z_' 'A-Z ' | grep -Eq '(^|[^A-Z0-9])SSD([^A-Z0-9]|$)|NVME' && echo SSD; }
new_ssd_text() { lsblk() { return 1; }; [ "$(drive_kind /dev/none "$1")" = SSD ] && echo SSD; }

python3 - >"$TMP/models" <<'PY'
import random
random.seed(11)
base = ["TOSHIBA MQ01ABD100", "Samsung SSD 860 EVO", "SAMSUNG MZ7LN256", "HM161HI", "WDC WD10EZEX-00BN5A0", "WD20 EARX", "WDS500G2B0A", "HGST HUS724040ALE640",
        "Hitachi HDS721010", "ST1000DM010-2EP102", "ST500LM030-1RK17", "CT500MX500SSD1", "KINGSTON SA400S37480G", "SanDisk SDSSDA120G", "SDSSDH3 250G",
        "INTEL SSDSC2BW120A4", "Micron MTFDDAK", "ADATA SU800", "Lexar 128GB", "CORSAIR Force", "PNY CS900", "A PNY X", "TeamGroup T-FORCE", "TEAM T253X2",
        "LITEON CV3", "Lite-On", "SK hynix SC311", "SKHYNIX", "MAXTOR 6L080", "FUJITSU MHZ2", "Transcend TS", "Plextor PX", "Patriot Burst", "Sabrent Rocket", "KIOXIA EXCERIA",
        "USB_DISK_3.0", "", " ", "   leading and trailing   ", "a__b", "Some Drive (v2) +x, y-z", "NVMe SSD", "nvme0", "SSD", "mySSDx", "my SSD x", "My-SSD-1", "x_SSD_y",
        "tab\there", "ünïcödé drive", "weird/chars:*?<>|" + chr(34) + chr(39), "dots...and---dashes", "...lead", "trail...", "-.- both -.-", "A  B   C"]
out = list(base)
chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-.()+,/:;*?éü" + chr(9)
for _ in range(400):
    out.append("".join(random.choice(chars) for _ in range(random.randint(0, 24))))
for b in base[:30]:
    out.append(b.lower()); out.append("  " + b + "  "); out.append(b.replace(" ", "_"))
for x in out:
    print(x.replace("\\\\t", "\\t").replace("\\n", " "))
PY
while IFS= read -r m; do
  n=$((n + 1))
  a=$(old_drive_brand "$m"); b=$(drive_brand "$m"); [ "$a" = "$b" ] || { echo "FAIL drive_brand [$m] old '$a' new '$b'"; bad=$((bad + 1)); }
  a=$(old_clean_name "$m"); b=$(clean_name "$m"); [ "$a" = "$b" ] || { echo "FAIL clean_name [$m] old '$a' new '$b'"; bad=$((bad + 1)); }
  a=$(old_ssd_text "$m"); b=$(new_ssd_text "$m"); [ "$a" = "$b" ] || { echo "FAIL ssd text [$m] old '$a' new '$b'"; bad=$((bad + 1)); }
done <"$TMP/models"

python3 - >"$TMP/sizes" <<'PY'
import random
random.seed(5)
v = [0, 1, 999999, 1000000, 1499999, 1500000, 999499999, 999500000, 1000000000, 1499999999, 1500000000, 949999999999, 950000000000, 950000000001, 999999999999,
     1000000000000, 1000204886016, 1500301910016, 2000398934016, 4000787030016, 8001563222016, 16000900661248, 100000000000000, 24 * 10**12 + 5 * 10**10, 12 * 10**11 + 49999999999,
     12 * 10**11 + 50000000000]
for _ in range(3000):
    v.append(random.randint(0, 3 * 10**13))
for _ in range(2000):
    v.append(random.randint(900 * 10**9, 1100 * 10**9))
for _ in range(1000):
    v.append(random.randint(0, 3 * 10**9))
for x in v:
    print(x)
PY
while IFS= read -r z; do
  n=$((n + 1))
  a=$(old_pretty_size "$z"); b=$(pretty_size "$z"); [ "$a" = "$b" ] || { echo "FAIL pretty_size $z old '$a' new '$b'"; bad=$((bad + 1)); }
done <"$TMP/sizes"
for z in "" abc "12abc" "007" "-5" "1e9" "12.5"; do
  n=$((n + 1)); a=$(old_pretty_size "$z"); b=$(pretty_size "$z")
  [ "$a" = "$b" ] || echo "note pretty_size [$z]: old '$a' new '$b' (an input that never comes from lsblk)"
done

# the name cache: while a look-only command runs, each drive's name is worked out once; afterwards the cache folder is gone
CALLS="$TMP/calls"; : >"$CALLS"
branch_name_calc() { echo x >>"$CALLS"; printf 'name-of-%s' "$(basename "$1")"; }
seen_cache=""
probe() { seen_cache=$NAME_CACHE; a=$(branch_name /m/D1); b=$(branch_name /m/D1); c=$(branch_name /m/D2); [ "$a" = "name-of-D1" ] && [ "$b" = "$a" ] && [ "$c" = "name-of-D2" ]; }
n=$((n + 1)); with_name_cache probe || { echo "FAIL name cache gave wrong names"; bad=$((bad + 1)); }
n=$((n + 1)); [ "$(wc -l <"$CALLS")" -eq 2 ] || { echo "FAIL name cache: $(wc -l <"$CALLS") lookups for 2 drives (want 2)"; bad=$((bad + 1)); }
n=$((n + 1)); { [ -n "$seen_cache" ] && [ ! -e "$seen_cache" ] && [ -z "$NAME_CACHE" ]; } || { echo "FAIL name cache folder was not removed"; bad=$((bad + 1)); }
: >"$CALLS"; branch_name /m/D1 >/dev/null; branch_name /m/D1 >/dev/null
n=$((n + 1)); [ "$(wc -l <"$CALLS")" -eq 2 ] || { echo "FAIL without the cache every call must look again"; bad=$((bad + 1)); }
[ "$bad" -eq 0 ] && echo "ok   $n comparisons, old and new give the same answers"
echo "$([ "$bad" -eq 0 ] && echo OK || echo FAIL)"
exit "$bad"
