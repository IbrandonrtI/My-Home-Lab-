#!/usr/bin/env bash
# Test: the Homepage drive pills ("Main Pool", "Backup Pool", "Connect ... Drive") kept by homelab-sample.
# Fake docker/mountpoint tell where Homepage's folder is and which pools are mounted. Nothing real is touched.
# Last line: OK or FAIL.
# shellcheck disable=SC2034  # test code: the checks read these variables as strings, and the file names are plain
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HERE/.."
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
bad=0
check() { if ( eval "$2" ); then echo "ok   $1"; else echo "FAIL $1"; bad=$((bad + 1)); fi; }
if [ "$(id -u)" != 0 ]; then echo "skipped: needs root (the script insists on it)"; echo OK; exit 0; fi
mkdir -p "$T/bin" "$T/hp" "$T/st"
printf '#!/bin/sh\necho "%s"\n' "$T/hp" >"$T/bin/docker"
cat >"$T/bin/mountpoint" <<'X'
#!/bin/sh
case "$2" in
  */main) [ -e "$FAKE_STATE/main" ] ;;
  */backup) [ -e "$FAKE_STATE/backup" ] ;;
  *) exit 1 ;;
esac
X
chmod +x "$T/bin/"*
export FAKE_STATE="$T/fs"; mkdir -p "$FAKE_STATE"
export HOMELAB_STATE_DIR="$T/st" HOMELAB_EXTRA_PATH="$T/bin" HOMELAB_MAIN_POOL="$T/main" HOMELAB_BACKUP_POOL="$T/backup"
run() { PATH="$T/bin:$PATH" bash "$REPO/scripts/homelab-sample" widgets; }
W="$T/hp/widgets.yaml"

# an older file: one "Drives" pill with the boot drive, the main pool and the network
cat >"$W" <<'Y'
- resources:
    label: pc
    cpu: true
    memory: true

- resources:
    label: Drives
    disk:
      - /
      - /mnt/storage
    network: true

- datetime:
    text_size: md

- openmeteo:
    label: City
    latitude: 40.7
    longitude: -74.0
Y
touch "$FAKE_STATE/main"
run
check "an older Drives pill becomes a Main Pool pill, a Backup Pool pill and a Network pill" 'grep -q "label: Main Pool" $W && grep -q "disk: /mnt/storage" $W && grep -q "disk: /mnt/backup" $W && grep -q "label: Network" $W && ! grep -q "label: Drives" $W'
check "the pool pills use the expanded view" '[ "$(grep -c "expanded: true" $W)" = 2 ]'
check "the other widgets are untouched" 'grep -q "label: pc" $W && grep -q "latitude: 40.7" $W && grep -q "text_size: md" $W'
check "the main pool is connected, the backup pool is not: the label asks for it" 'grep -q "label: Main Pool" $W && grep -q "label: Connect Backup Drive" $W'
touch "$FAKE_STATE/backup"; run
check "with both pools mounted the labels are the pool names" 'grep -q "label: Main Pool" $W && grep -q "label: Backup Pool" $W && ! grep -q "label: Connect" $W'
rm -f "$FAKE_STATE/main" "$FAKE_STATE/backup"; run
check "with neither mounted both pills ask for a drive" 'grep -q "label: Connect Main Drive" $W && grep -q "label: Connect Backup Drive" $W'
touch "$FAKE_STATE/main" "$FAKE_STATE/backup"; run
H1=$(sha256sum <"$W"); run; H2=$(sha256sum <"$W")
check "running again changes nothing" '[ "$H1" = "$H2" ]'
check "the file still has exactly four resources pills" '[ "$(grep -c "^- resources:" $W)" = 4 ]'

# the file shipped in the repository works the same way
cp "$REPO/homepage-config/widgets.yaml" "$W"; rm -f "$FAKE_STATE/backup"; run
check "the shipped file: the missing backup pool asks for a drive" 'grep -q "label: Connect Backup Drive" $W && grep -q "label: Main Pool" $W'
touch "$FAKE_STATE/backup"; run
check "the shipped file: back to Backup Pool when it is mounted" 'grep -q "label: Backup Pool" $W && ! grep -q "label: Connect" $W'
check "the shipped file has the two pools and the network, each in its own pill" '[ "$(grep -c "^- resources:" $REPO/homepage-config/widgets.yaml)" = 4 ] && grep -q "label: Network" $REPO/homepage-config/widgets.yaml'
check "the stack file shares /mnt (both pools) with Homepage, with rslave" 'grep -q "^      - /mnt:/mnt:ro,rslave" $REPO/stacks/homepage.yaml'
echo "$([ "$bad" -eq 0 ] && echo OK || echo FAIL)"
exit "$bad"
