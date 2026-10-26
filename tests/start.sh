#!/bin/bash
# Build a fresh fake machine in $SIM_DIR and start the fake web services.
#   source start.sh [mint|existing]
SIMSRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SIMSRC/.." && pwd)"
export SIM_DIR="${SIM_DIR:-${TMPDIR:-/tmp}/homelab-sim}"
[ -f "$SIM_DIR/server.pid" ] && kill "$(cat "$SIM_DIR/server.pid")" 2>/dev/null; sleep 0.3
if [ -z "$SIM_KEEP" ]; then
OLDPID=$(cat "$SIM_DIR/server.pid" 2>/dev/null); [ -n "$OLDPID" ] && kill "$OLDPID" 2>/dev/null
rm -rf "$SIM_DIR"; mkdir -p "$SIM_DIR"/{root,bin-always,bin-installed,sys-bin}
fi
export HLS_ROOT="$SIM_DIR/root"
R="$HLS_ROOT"
if [ -z "$SIM_KEEP" ]; then
mkdir -p "$R"/{etc,home/testuser,mnt/storage,opt,var/lib,var/log,usr/local/sbin,usr/local/bin,root}
cat > "$R/etc/os-release" <<'EOF'
PRETTY_NAME="Linux Mint 22.3"
NAME="Linux Mint"
VERSION_ID="22.3"
ID=linuxmint
ID_LIKE="ubuntu debian"
VERSION_CODENAME=zena
UBUNTU_CODENAME=noble
EOF
echo 'nameserver 127.0.0.53' > "$R/etc/resolv.conf"
for c in apt-get dpkg-query dpkg systemctl ss ip timedatectl crontab usermod id; do ln -sf "$SIMSRC/fakecmd.py" "$SIM_DIR/bin-always/$c"; done
for t in python3 bash sh env cat ls rsync du df gzip gunzip zcat mkdir rm cp mv chmod chown sleep date head tail grep sed awk hostname stat find tr sort uniq wc dirname basename readlink ln touch tee diff cmp expr true false test timeout xargs cut od base64 seq sha256sum md5sum; do
  p=$(command -v $t 2>/dev/null); [ -n "$p" ] && ln -sf "$p" "$SIM_DIR/sys-bin/$t"
done
fi
export PATH="$SIM_DIR/bin-always:$SIM_DIR/bin-installed:$SIM_DIR/sys-bin"
export HLS_FAKE=1 HLS_USER=testuser HLS_LAN=192.168.50.23 HLS_GATEWAY=192.168.50.1 HLS_TS_API=http://127.0.0.1:9999 HLS_GEOCODE_API=http://127.0.0.1:9999 HLS_HOST=127.0.0.1
export HLS_NO_THROTTLE=1
# the repo the installer reads: a copy of this repository's working tree (HLS_PROG overrides the installer file)
REPO="$SIM_DIR/repo"
if [ -z "$SIM_KEEP" ]; then
mkdir -p "$REPO"
for d in installer scripts stacks homepage-config; do cp -r "$REPO_ROOT/$d" "$REPO/"; done
[ -n "${HLS_PROG:-}" ] && cp "$HLS_PROG" "$REPO/installer/homelab-setup"
fi
export REPO
if [ -z "$SIM_KEEP" ]; then
case "${1:-mint}" in
  existing) python3 "$SIMSRC/mkexisting.py" ;;
esac
fi
if ! kill -0 "$(cat "$SIM_DIR/server.pid" 2>/dev/null)" 2>/dev/null; then
rm -f "$SIM_DIR/server.ready"
/usr/bin/python3 "$SIMSRC/server.py" >"$SIM_DIR/server.log" 2>&1 &
echo $! > "$SIM_DIR/server.pid"
for i in $(seq 1 50); do [ -f "$SIM_DIR/server.ready" ] && break; sleep 0.1; done
fi
setw() { SIMSRC="$SIMSRC" python3 - "$@" <<'PY'
import sys,json,os; sys.path.insert(0,os.environ["SIMSRC"])
from simlib import World
path,val=sys.argv[1],json.loads(sys.argv[2])
with World() as w:
    d=w
    keys=path.split(".")
    for k in keys[:-1]: d=d[k]
    d[keys[-1]]=val
PY
}
hls() { /usr/bin/python3 "$REPO/installer/homelab-setup" "$@"; }
world() { python3 -c "import json;w=json.load(open('$SIM_DIR/world.json'));print(json.dumps(w$1,indent=1))"; }
