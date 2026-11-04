#!/usr/bin/env bash
# Test: the newcomer-friendly parts: help and refused options on homelab-backup and hdd-recover, "Did you mean" in homelab,
# the "Open in your browser" block, a fix command on every warning, and the calmer message while setup is not finished.
# Nothing real is touched (fake state folder, fake tailscale). Last line: OK or FAIL.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$HERE/.."
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
bad=0
has() { case "$2" in *"$3"*) echo "ok   $1" ;; *) echo "FAIL $1   (missing: $3)"; bad=$((bad + 1)) ;; esac; }
hasnt() { case "$2" in *"$3"*) echo "FAIL $1   (should not be there: $3)"; bad=$((bad + 1)) ;; *) echo "ok   $1" ;; esac; }
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1   got '$2', wanted '$3'"; bad=$((bad + 1)); fi; }

# homelab-backup: help and refused options never start a backup (the script would stop with "Run as root" or lock a file if it started)
OUT=$(bash "$REPO/scripts/homelab-backup" --help 2>&1); RC=$?
has "backup --help prints the help" "$OUT" "Usage:"; check "backup --help exits 0" "$RC" "0"
OUT=$(bash "$REPO/scripts/homelab-backup" help 2>&1); has "backup help prints the help" "$OUT" "run the backup now"
OUT=$(bash "$REPO/scripts/homelab-backup" version 2>&1); has "backup version" "$OUT" "homelab-backup 1."
OUT=$(bash "$REPO/scripts/homelab-backup" --dry-run 2>&1); RC=$?
has "an unknown option is refused with a plain message" "$OUT" "Nothing was started"; check "an unknown option exits 2" "$RC" "2"
hasnt "a refused option does not start a backup" "$OUT" "Run as root"

# hdd-recover: help does not run the recovery
OUT=$(bash "$REPO/scripts/hdd-recover" --help 2>&1); RC=$?
has "hdd-recover --help explains itself" "$OUT" "remount the drives"; check "hdd-recover --help exits 0" "$RC" "0"
hasnt "hdd-recover --help does not call drives" "$OUT" "No such file"

# homelab: short forms run the real command (with sudo when not root) and say which one; other wrong guesses get "Did you mean"
export HOMELAB_COLOR=0 HOMELAB_STATE_DIR="$T/st" HOMELAB_HOMEPAGE_DIR="$T/hp" HOMELAB_LAN_IP=192.168.1.50 HOMELAB_MAIN_POOL="$T/main" HOMELAB_BACKUP_POOL="$T/backup"
export HOMELAB_LAST_RUN_FILE="$T/nolog/last-run" HOME="$T/home"; mkdir -p "$T/st" "$T/hp" "$T/home" "$T/bin"
for c in homelab-backup homelab-update homelab-setup drives homelab-cards homelab-selftest; do
  printf '#!/bin/sh\necho "REAL-RUN %s $*"\n' "$c" >"$T/bin/$c"; chmod +x "$T/bin/$c"
done
printf '#!/bin/sh\nexec "$@"\n' >"$T/bin/sudo"; chmod +x "$T/bin/sudo"
H="bash $REPO/scripts/homelab"
P="env PATH=$T/bin:$PATH"
has "homelab backup runs the backup command" "$($P $H backup 2>&1)" "REAL-RUN homelab-backup"
has "it says which real command it runs" "$($P $H backup 2>&1)" "Running:  sudo homelab-backup"
has "homelab update runs the update command with its options" "$($P $H update check 2>&1)" "REAL-RUN homelab-update check"
has "homelab upgrade runs the one-step update" "$($P $H upgrade 2>&1)" "REAL-RUN homelab-setup upgrade"
has "homelab drives runs the drive menu command with its options" "$($P $H drives health 2>&1)" "REAL-RUN drives health"
has "homelab cards runs the cards command" "$($P $H cards list 2>&1)" "REAL-RUN homelab-cards list"
has "homelab selftest runs the self-test" "$($P $H selftest 2>&1)" "REAL-RUN homelab-selftest"
OUT=$($H check 2>&1); RC=$?
has "homelab check points to the self-test" "$OUT" "sudo homelab-selftest"; check "a wrong guess exits 1" "$RC" "1"
has "homelab restore points to the restore preview" "$($H restore 2>&1)" "homelab-restore-configs check"
has "an unknown word still points to the help" "$($H banana 2>&1)" "homelab commands"
hasnt "an unknown word does not invent a suggestion" "$($H banana 2>&1)" "Did you mean"

# the login screen
printf '1|56|\n' >"$T/st/setup-progress"; printf '26|%s\n' "$(date +%s)" >"$T/st/apt"
printf '%s\n' '#!/bin/sh' 'case "$1" in serve) printf "https://lab.example.ts.net:1004 (tailnet only)\n|-- / proxy http://192.168.1.50:3001\n" ;; esac' >"$T/bin/tailscale"; chmod +x "$T/bin/tailscale"
SCREEN=$(PATH="$T/bin:$PATH" HOMELAB_CACHE_DIR="$T/cache" $H 2>&1)
has "the screen has an Open in your browser block" "$SCREEN" "Open in your browser"
has "it shows the dashboard address at home" "$SCREEN" "http://192.168.1.50:3001"
hasnt "it does not show AdGuard Home's port as the dashboard" "$SCREEN" ":3000"
has "it shows the Tailscale address when there is one" "$SCREEN" "https://lab.example.ts.net:1004"
has "it says what the Tailscale address needs" "$SCREEN" "needs the Tailscale app"
has "an unfinished setup is explained as the reason for warnings" "$SCREEN" "Some warnings below are normal until it is"
has "the next step is named" "$SCREEN" "sudo homelab-setup"
has "system updates say how to install them" "$SCREEN" "sudo apt upgrade"
has "a missing backup says how to run it" "$SCREEN" "sudo homelab-backup"
has "an unconnected backup pool says how to connect one" "$SCREEN" "sudo drives connect"
printf '#!/bin/sh\n[ "$1" = port ] && echo "0.0.0.0:3009" && exit 0\nexit 1\n' >"$T/bin/docker"; chmod +x "$T/bin/docker"
SCREEN5=$(PATH="$T/bin:$PATH" HOMELAB_CACHE_DIR="$T/cache5" $H 2>&1)
has "the dashboard port is read from Docker when it can be" "$SCREEN5" "http://192.168.1.50:3009"
hasnt "no Tailscale address is guessed for another port" "$SCREEN5" "ts.net:1004"
rm -f "$T/bin/docker"
SCREEN2=$(PATH="$T/bin:$PATH" $H status 2>&1)
hasnt "homelab status alone has no browser block" "$SCREEN2" "Open in your browser"
rm -rf "$T/hp"
SCREEN3=$(PATH="$T/bin:$PATH" $H 2>&1)
hasnt "without the Homepage folder there is no browser block" "$SCREEN3" "Open in your browser"
rm -f "$T/st/setup-progress"; mkdir -p "$T/hp"
SCREEN4=$(PATH="$T/bin:$PATH" $H 2>&1)
hasnt "when setup is finished the unfinished message is gone" "$SCREEN4" "Setup is not finished"
OUT=$($H commands 2>&1)
has "the command list offers the one-step update" "$OUT" "sudo homelab-setup upgrade"
has "the command list starts with a short Start here section" "$OUT" "Start here"
has "the command list explains which check to run" "$OUT" "Which check do I run?"
has "the command list has a glossary" "$OUT" "Words used here"
has "the command list explains the word pool" "$OUT" "several drives shown as one folder"
has "the command list shows the short forms" "$OUT" "homelab backup"
# every section is in alphabetical order (not counting "sudo")
BADSORT=$(HOMELAB_COLOR=0 COLUMNS=140 $H commands | awk '/^  -- /{prev=""; next} /^   [^ ]/ {c=substr($0,4); sub(/   .*/,"",c); sub(/^sudo /,"",c); c=tolower(c); if (prev != "" && c < prev) print prev " > " c; prev=c}')
check "each section of the command list is in alphabetical order" "$BADSORT" ""

if [ "$bad" -eq 0 ]; then echo OK; else echo "FAIL ($bad)"; exit 1; fi
