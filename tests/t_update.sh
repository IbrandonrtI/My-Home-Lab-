#!/usr/bin/env bash
# Test: homelab-update with a fake Docker, a fake registry and a fake Portainer (tests/fakeupd.py).
# Checks the version lookup (v2.6.0 -> v2.7.0), the upload check, the database dump, the update through Portainer
# and the guards. Nothing on this machine is touched. Last line: OK or FAIL.
# shellcheck disable=SC2034  # test code: the checks read these variables as strings, and the file names are plain
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPD="$HERE/../scripts/homelab-update"
T="$(mktemp -d)"; PASS=0; FAIL=0
trap 'kill $PT $RG 2>/dev/null; rm -rf "$T"' EXIT
check() { if ( eval "$2" ); then PASS=$((PASS+1)); else echo "FAIL  $1"; FAIL=$((FAIL+1)); [ -n "${3:-}" ] && echo "$3" | head -30; fi; }
if [ "$(id -u)" != 0 ]; then echo "skipped: needs root (the script insists on it)"; echo OK; exit 0; fi

mkdir -p "$T/bin" "$T/st" "$T/dumps"
export FAKE_DIR="$T"
printf '#!/bin/sh\nexec python3 %s docker "$@"\n' "$HERE/fakeupd.py" >"$T/bin/docker"; chmod +x "$T/bin/docker"
free_port() { python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])'; }
PP=$(free_port); RP=$(free_port)
newstate() {
python3 - "$T/state.json" <<'PY'
import json, sys
H, A, N, P = "ghcr.io/gethomepage/homepage:v2.6.0", "adguard/adguardhome:v0.107.79", "nextcloud:35-apache", "postgres:16-alpine"
st = {
 "images": {H: {"id": "sha256:h260", "digests": ["x@sha256:hp260"]}, A: {"id": "sha256:ag1", "digests": ["x@sha256:ag"]},
            N: {"id": "sha256:nc1", "digests": ["x@sha256:nc-old"]}, P: {"id": "sha256:pg1", "digests": ["x@sha256:pg"]}},
 "remote": {H: "sha256:hp260", A: "sha256:ag", N: "sha256:nc-new", P: "sha256:pg"},
 "remote_tags": {"ghcr.io/gethomepage/homepage:v2.7.0": "sha256:hp270"},
 "tags": {"gethomepage/homepage": ["v2.5.0", "v2.6.0", "v2.7.0", "v2.7.0-rc1", "latest", "v2.4.0"], "adguard/adguardhome": ["v0.107.79", "latest"]},
 "containers": {
   "homepage": {"id": "c1", "image": H, "stack": "homepage"}, "adguardhome": {"id": "c2", "image": A, "stack": "adguard"},
   "nextcloud": {"id": "c3", "image": N, "stack": "nextcloud"}, "nextcloud_db": {"id": "c4", "image": P, "stack": "nextcloud"}},
 "stacks": {"homepage": {"file": "services:\n  homepage:\n    image: %s\n" % H, "env": [{"name": "HOMEPAGE_ALLOWED_HOSTS", "value": "a:1"}]},
            "adguard": {"file": "services:\n  a:\n    image: %s\n" % A, "env": []},
            "nextcloud": {"file": "services:\n  nextcloud:\n    image: %s\n  db:\n    image: %s\n" % (N, P), "env": [{"name": "K", "value": "secret"}]}},
 "nc_old": "35.0.1", "nc_new": "35.0.2"}
for c in st["containers"].values():
    c["imgid"] = st["images"][c["image"]]["id"]       # a running container keeps the image it was started from
json.dump(st, open(sys.argv[1], "w"))
PY
}
newstate
python3 "$HERE/fakeupd.py" portainer "$PP" & PT=$!
python3 "$HERE/fakeupd.py" registry "$RP" & RG=$!
for _ in $(seq 1 50); do python3 -c "import socket;socket.create_connection(('127.0.0.1',$PP),0.2);socket.create_connection(('127.0.0.1',$RP),0.2)" 2>/dev/null && break; sleep 0.1; done
printf 'PORTAINER_TOKEN=good-key\n' >"$T/secrets.env"

export HOMELAB_STATE_DIR="$T/st" HOMELAB_EXTRA_PATH="$T/bin" HLU_LOCKFILE="$T/lock" HLU_FREE_GB=100 HLU_PULL_PAUSE=0 HLU_WAIT=10 HLU_SETTLE=3 HLU_WAIT_EVERY=1 \
       HLU_DUMP_DIR="$T/dumps" HLU_SECRETS="$T/secrets.env" HLU_PORTAINER="http://127.0.0.1:$PP" HLU_REGISTRY_BASE="http://127.0.0.1:$RP" \
       HLU_CONF="$T/none" HLU_DUMP_MIN=20 NO_COLOR=1 TERM=dumb
up() { timeout 60 bash "$UPD" "$@" 2>&1 </dev/null; }
js() { python3 -c "import json;s=json.load(open('$T/state.json'));print($1)"; }

# ---- looking online
out=$(up check)
check "check: a pinned version sees the newer number online (v2.6.0 -> v2.7.0)" 'echo "$out" | grep -q "homepage:v2.6.0.*newer version v2.7.0 online"' "$out"
check "check: a moved tag still shows as newer online" 'echo "$out" | grep -q "nextcloud:35-apache.*newer online"' "$out"
check "check: a pinned version with nothing newer is up to date (a release candidate is not offered)" 'echo "$out" | grep -q "adguardhome:v0.107.79.*up to date"' "$out"
check "check: it no longer says new releases are not seen" '! echo "$out" | grep -q "NOT seen"' "$out"
check "list: tells to run homelab-update, no Portainer clicking" 'up list | grep -q "sudo homelab-update" && ! up list | grep -q "Re-pull"'

# ---- the upload / backup check
newstate
out=$(HLU_BUSY="files are being written to a storage pool (an upload?)" up --yes)
check "busy: it stops before touching any container and says to wait" 'echo "$out" | grep -q "Not now: files are being written" && echo "$out" | grep -q "run  sudo homelab-update  again" && [ "$(js "len(s.get(\"puts\",[]))")" = 0 ]' "$out"
check "busy: nothing was downloaded to the containers (they still run the old images)" '[ "$(js "s[\"containers\"][\"homepage\"][\"image\"]")" = "ghcr.io/gethomepage/homepage:v2.6.0" ]'
out=$(HLU_BUSY="a backup is running right now" up --yes); check "a running backup also stops it" 'echo "$out" | grep -q "Not now: a backup is running right now"' "$out"

# ---- the real sampling: an idle drive is not busy, a writing drive is
mkdir -p "$T/sys/sdz"; echo "1 0 1 0 1 0 1000 0 0 0 0" >"$T/sys/sdz/stat"
check "idle pool drives are not busy" '[ -z "$(HLU_POOL_DEVS=sdz HLU_SYS_BLOCK=$T/sys HLU_SAMPLE_SECS=1 HLU_SOURCE_ONLY=1 bash -c ". $UPD; busy_reason")" ]'
( sleep 0.3; echo "1 0 1 0 1 0 9999999 0 0 0 0" >"$T/sys/sdz/stat" ) & W=$!
check "a pool drive that is being written to is busy" 'HLU_POOL_DEVS=sdz HLU_SYS_BLOCK=$T/sys HLU_SAMPLE_SECS=1 HLU_SOURCE_ONLY=1 bash -c ". $UPD; busy_reason" | grep -q "being written"'
wait $W

# ---- the full run: no full backup, database dump, update through Portainer
newstate
out=$(up --yes --now); r=$?
check "run: it succeeds" '[ $r -eq 0 ]' "$out"
check "run: the newer version is downloaded by its version tag" 'echo "$out" | grep -q "homepage:v2.7.0"' "$out"
check "run: no full backup is made (no backup step)" '! echo "$out" | grep -qi "Back up everything first" && ! grep -q homelab-backup "$T/docker.log"' "$out"
check "run: Homepage's saved stack file now says v2.7.0 and nothing else changed" '[ "$(js "s[\"stacks\"][\"homepage\"][\"file\"]")" = "$(printf "services:\n  homepage:\n    image: ghcr.io/gethomepage/homepage:v2.7.0")" ]'
check "run: the stack's variables are sent back unchanged" '[ "$(js "s[\"stacks\"][\"homepage\"][\"env_sent\"][0][\"value\"]")" = "a:1" ] && [ "$(js "s[\"stacks\"][\"nextcloud\"][\"env_sent\"][0][\"value\"]")" = "secret" ]'
check "run: the Homepage container now runs v2.7.0" '[ "$(js "s[\"containers\"][\"homepage\"][\"image\"]")" = "ghcr.io/gethomepage/homepage:v2.7.0" ]'
check "run: the moved Nextcloud tag was recreated too" '[ "$(js "s[\"containers\"][\"nextcloud\"].get(\"recreated\",0)")" = 1 ]'
check "run: AdGuard had nothing to do and was not touched" '[ "$(js "\"adguard\" in s.get(\"puts\",[])")" = False ]'
check "run: a database dump of Nextcloud was saved before updating it" '[ "$(ls $T/dumps/nextcloud_db-*.sql.gz | wc -l)" = 1 ] && gzip -t $T/dumps/nextcloud_db-*.sql.gz' "$out"
check "run: no false 'still runs the old image' (the database kept its version on purpose)" '! echo "$out" | grep -q "still runs the old image"' "$out"
check "run: the order is safe (Homepage before Nextcloud) and it reports both" 'echo "$out" | grep -q "homepage is updated" && echo "$out" | grep -q "nextcloud is updated"' "$out"
check "run: the saved list is cleaned up (the login screen shows nothing waiting)" '[ "$(tail -n +2 $T/st/image-updates | wc -l)" = 0 ]' "$(cat $T/st/image-updates)"
out=$(up check); check "run: afterwards the check finds nothing new for the updated stacks" 'echo "$out" | grep -q "homepage:v2.7.0" ' "$out"

# ---- guards
newstate; python3 - "$T/state.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1])); s["nc_new"] = "37.0.0"; s["nc_old"] = "35.0.1"; json.dump(s, open(sys.argv[1], "w"))
PY
out=$(up --yes --now)
check "guard: a Nextcloud jump over a major version is refused" 'echo "$out" | grep -q "skip a major version" && [ "$(js "s[\"containers\"][\"nextcloud\"].get(\"recreated\",0)")" = 0 ]' "$out"
check "guard: the other stacks were still updated" '[ "$(js "s[\"containers\"][\"homepage\"][\"image\"]")" = "ghcr.io/gethomepage/homepage:v2.7.0" ]'
newstate; python3 - "$T/state.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1])); s["nc_new"] = "36.0.0"; s["nc_old"] = "35.0.1"; json.dump(s, open(sys.argv[1], "w"))
PY
out=$(up --yes --now)
check "guard: a Nextcloud major upgrade is left for you when --yes is used" 'echo "$out" | grep -q "MAJOR upgrade" && [ "$(js "s[\"containers\"][\"nextcloud\"].get(\"recreated\",0)")" = 0 ]' "$out"
newstate; python3 - "$T/state.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1])); s["dump_fails"] = True; json.dump(s, open(sys.argv[1], "w"))
PY
out=$(up --yes --now)
check "guard: if the database dump fails, that stack is not updated and it stops" 'echo "$out" | grep -q "dump of the nextcloud_db database failed" && [ "$(js "s[\"containers\"][\"nextcloud\"].get(\"recreated\",0)")" = 0 ]' "$out"
newstate; python3 - "$T/state.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1])); s["containers"]["homepage"]["anon"] = ["/data"]; json.dump(s, open(sys.argv[1], "w"))
PY
out=$(up --yes --now)
check "guard: a container with data in an anonymous volume is not updated" 'echo "$out" | grep -q "anonymous volume" && [ "$(js "s[\"containers\"][\"homepage\"].get(\"recreated\",0)")" = 0 ]' "$out"
newstate
out=$(HLU_SECRETS="$T/none" up --yes --now)
check "no Portainer key: it explains and gives the manual steps, nothing is changed" 'echo "$out" | grep -q "Do it by hand in Portainer" && [ "$(js "len(s.get(\"puts\",[]))")" = 0 ]' "$out"
newstate
out=$(printf 'y\nn\nn\nn\n' | HLU_TEST_STDIN=1 bash "$UPD" --now 2>&1)
check "asking: each stack is asked about, and a no leaves it alone" 'echo "$out" | grep -q "homepage left as it is" && [ "$(js "len(s.get(\"puts\",[]))")" = 0 ]' "$out"
out=$(bash "$UPD" --yes --now --backup 2>&1 </dev/null)
check "--backup: asks for the full backup first (it fails here: no backup tool, and nothing is updated)" 'echo "$out" | grep -q "STOPPED: the backup" || echo "$out" | grep -q "Running the full backup"' "$out"

# ---- Portainer itself is recreated from the terminal (it is not a stack)
newstate; python3 - "$T/state.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
I = "portainer/portainer-ce:latest"
s["images"][I] = {"id": "sha256:pt1", "digests": ["x@sha256:pt-old"]}
s["remote"][I] = "sha256:pt-new"
s["containers"] = {"portainer": {"id": "c9", "image": I, "stack": "<no value>", "imgid": "sha256:pt1", "run": "always"}}
s["stacks"] = {}
json.dump(s, open(sys.argv[1], "w"))
PY
: >"$T/docker.log"
out=$(up --yes --now)
check "portainer: it is stopped, renamed, started again from the new image and the old copy removed" 'grep -q "^stop portainer" $T/docker.log && grep -q "^rename portainer portainer-before-update" $T/docker.log && grep -q "^run -d --name portainer --restart=always" $T/docker.log && grep -q "^rm portainer-before-update" $T/docker.log' "$out"
check "portainer: the result says it is updated" 'echo "$out" | grep -q "portainer is updated"' "$out"

echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && echo OK || echo FAIL
