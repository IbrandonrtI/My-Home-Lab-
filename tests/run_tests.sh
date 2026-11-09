#!/bin/bash
# shellcheck disable=SC2034  # many variables are only used inside the quoted test commands that ok() and check() evaluate
# Simulation tests for homelab-setup. Everything runs against a FAKE machine (fake apt, docker, Tailscale and web services).
SIMDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HLS_BOOT_ID=boot-A; ORIG_PATH="$PATH"; PASS=0; FAIL=0; ONLY="${1:-}"
ok(){ if ( eval "$2" ) >/dev/null 2>${OKERR:-/dev/null}; then echo "PASS  $1"; PASS=$((PASS+1)); else echo "FAIL  $1"; FAIL=$((FAIL+1)); fi; }
wj(){ python3 -c "import json;w=json.load(open('$SIM_DIR/world.json'));print($1)"; }
scen(){ [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }
PW=CorrectHorse1234
approve_in(){ ( sleep "$1"; setw ts.approved true ) & }
fresh(){ export PATH="$ORIG_PATH"; unset SIM_KEEP; source $SIMDIR/start.sh mint; }
keep(){ export PATH="$ORIG_PATH"; export SIM_KEEP=1; source $SIMDIR/start.sh; }
install_in(){ # install_in "https-enter" "port53-answer"
  printf '%s\n' Tester tester@example.com "" "" "" "" $PW $PW yes "${1:-}" "${2:-y}" ; }

# ------------------------------------------------------------------ S1: a full install on a blank machine
if scen S1; then
echo "### S1 full install on a blank Mint machine"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s1.out 2>&1; RC=$?
ok "S1 install exits 0" '[ $RC -eq 0 ]'
ok "S1 all 16 containers run" '[ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
ok "S1 no host folder was left for Docker to create root-owned" '[ "$(wj "len(w[\"warnings\"])")" = 0 ]'
ok "S1 systemd-resolved stopped and disabled" '[ "$(wj "w[\"units\"][\"systemd-resolved\"]")" = inactive ] && [ "$(wj "w[\"enabled\"][\"systemd-resolved\"]")" = False ]'
ok "S1 resolv.conf points at the router" 'grep -q "nameserver 192.168.50.1" $HLS_ROOT/etc/resolv.conf'
ok "S1 resolv.conf is free of Tailscale's 100.100.100.100" '! grep -q 100.100.100.100 $HLS_ROOT/etc/resolv.conf && grep -q "^nameserver" $HLS_ROOT/etc/resolv.conf'
ok "S1 Tailscale told not to manage DNS" '[ "$(wj "w[\"ts\"].get(\"accept_dns\", True)")" = False ]'
ok "S1 dns-stable step shows done" 'hls 2>&1 | grep -q "✓ Network (2 of 2)"'
# the machine is removed from the Tailscale admin page, then logs in again: must work with accept-dns=false already set
setw ts.logged_in false; setw ts.approved true
printf 'y\nn\nn\n' | hls fill > $SIM_DIR/s1relogin.out 2>&1
ok "S1 logging in to Tailscale again works after accept-dns=false was set" '[ "$(wj "w[\"ts\"][\"logged_in\"]")" = True ] && ! grep -q "requires mentioning" $SIM_DIR/s1relogin.out'
ok "S1 commands in the checklist are highlighted (bold cyan) when colour is on" 'HLS_COLOR=1 hls 2>&1 | grep -q $'"'"'\033\[1;36msudo homelab-setup'"'"''
ok "S1 links in the checklist are underlined when colour is on" 'HLS_COLOR=1 hls 2>&1 | grep -q $'"'"'\033\[4;36mhttps://'"'"''
ok "S1 plain output (no colour) shows commands as plain \$ lines" 'hls 2>&1 | grep -q "^ *\$ sudo homelab-setup"'
ok "S1 login screen is told there is no data drive yet (marker written)" '[ -s $HLS_ROOT/var/lib/homelab/no-data-drive ]'
ok "S1 the boot drive share is ~/boot-drive-files (no 750GB_HDD), and the stand-in backup points into it" '[ -d $HLS_ROOT/home/testuser/boot-drive-files ] && [ ! -e $HLS_ROOT/home/testuser/750GB_HDD ] && grep -q "boot-drive-files/backup-interim" $HLS_ROOT/etc/homelab-backup.conf'
ok "S1 user was added to the docker group" 'wj "w[\"usermod\"]" | grep -q "docker testuser"'
ok "S1 serve waits for HTTPS (not set yet)" '[ "$(wj "len(w[\"ts\"][\"serve\"])")" = 0 ]'
ok "S1 Tailscale widget is the only missing key" 'grep -q "Tailscale widget" $SIM_DIR/s1.out'
ok "S1 secrets file mode 600 and dir 700" '[ "$(stat -c %a $HLS_ROOT/root/.homelab-setup/secrets.env)" = 600 ] && [ "$(stat -c %a $HLS_ROOT/root/.homelab-setup)" = 700 ]'
ok "S1 typed password NOT in secrets.env" '! grep -q $PW $HLS_ROOT/root/.homelab-setup/secrets.env'
ok "S1 typed password NOT in state.json" '! grep -q $PW $HLS_ROOT/var/lib/homelab-setup/state.json'
ok "S1 typed password NOT in the install log" '! grep -q $PW $HLS_ROOT/var/log/homelab-setup.log'
ok "S1 typed password only in the three Homepage logins" '[ "$(grep -rl $PW $HLS_ROOT | grep -v "/proc" | sort | tr "\n" " ")" = "$HLS_ROOT/home/testuser/homepage-config/services.yaml " ]'
ok "S1 services.yaml has no placeholders left" '! grep -q "your-own-key\|192.168.X.X\|your-tailnet\|your-email" $HLS_ROOT/home/testuser/homepage-config/services.yaml || grep -B3 -A3 "your-own-key" $HLS_ROOT/home/testuser/homepage-config/services.yaml | grep -q tailscale'
ok "S1 progress file written" '[ -s $HLS_ROOT/var/lib/homelab/setup-progress ]'
ok "S1 cron has 9 lines (with the service cards, the stats and the calendar with its daily sync), no backup line (no data drive)" '[ "$(grep -c . $SIM_DIR/crontab)" = 9 ] && grep -q "homelab-stats" $SIM_DIR/crontab && grep -q "homelab-calendar build" $SIM_DIR/crontab && grep -q "homelab-calendar sync" $SIM_DIR/crontab && ! grep -q homelab-backup $SIM_DIR/crontab'
ok "S1 login hook added to .bashrc once" '[ "$(grep -c "homelab login display >>>" $HLS_ROOT/home/testuser/.bashrc)" = 1 ]'
ok "S1 a clean machine gets no notice about drives left by an earlier install" '! grep -q "sudo drives release" $SIM_DIR/s1.out'
ok "S1 scripts installed with this machine's user pinned in them (no lookup left, nobody else's name)" 'grep -q "HOMELAB_USER:-testuser" $HLS_ROOT/usr/local/sbin/homelab-backup && grep -q "SUDO_USER:-testuser" $HLS_ROOT/usr/local/sbin/drives && ! grep -q "getent passwd 1000" $HLS_ROOT/usr/local/sbin/homelab-backup $HLS_ROOT/usr/local/sbin/drives && ! grep -rq "otheruser" $HLS_ROOT/usr/local'
ok "S1 drives owner rewritten" 'grep -q "DRIVES_OWNER:-\${SUDO_USER:-testuser}" $HLS_ROOT/usr/local/sbin/drives'
ok "S1 never touched a drive tool" '! wj "w[\"events\"]" | grep -v "apt install" | grep -qi "mkfs\|wipefs\|parted\|fdisk\|chattr\|mount"'
# the person turns on HTTPS, then refreshes
setw ts.https true
HLS_LIVE=1 hls refresh > $SIM_DIR/s1b.out 2>&1
ok "S1 live mode reserves the bottom row and paints the n of m bar there and still prints the result" 'grep -q $'"'"'\033\[1;[0-9]*r'"'"' $SIM_DIR/s1b.out && grep -qE "[0-9]+ of [0-9]+  " $SIM_DIR/s1b.out && grep -q "✓" $SIM_DIR/s1b.out'
ok "S1 refresh sets the 10 Tailscale Serve addresses (the panel on 1100 included)" '[ "$(wj "len(w[\"ts\"][\"serve\"])")" = 10 ]'
ok "S1 the control panel: page files and the unit are installed" 'for f in index.html app.js app.css icon.svg; do [ -s $HLS_ROOT/usr/local/share/homelab-panel/ui/$f ] || exit 1; done; grep -q "HLP_PORT=8300" $HLS_ROOT/etc/systemd/system/homelab-panel.service && grep -q "^User=testuser" $HLS_ROOT/etc/systemd/system/homelab-panel.service'
ok "S1 the Drives tab: a narrow sudo rule lets only the panel's user run the exact drives panel commands, and the file is private" 'F=$HLS_ROOT/etc/sudoers.d/homelab-panel; [ -s $F ] && [ "$(stat -c %a $F)" = 440 ] && grep -q "^testuser ALL=(root) NOPASSWD: HOMELAB_PANEL_DRIVES$" $F && for w in status health check actions remount abort setups "rename \*" "sleep \*" "wake \*" "add \*" "wipe \*" "disconnect \*" "move \*" "setup \*" "bootadd \*"; do grep -q "/usr/local/sbin/drives panel $w" $F || exit 1; done; [ "$(grep -c "/usr/local/sbin/drives" $F)" = 16 ] && ! grep -q "ALL$" $F && ! grep -qE "eject|release|replace|restore|preset|wizard|bootsection|adopt|--" $F'
ok "S1 the panel's service can use sudo (no NoNewPrivileges, PrivateTmp or ProtectSystem, which would stop a mount from reaching the machine)" '! grep -qE "NoNewPrivileges|PrivateTmp|ProtectSystem" $HLS_ROOT/etc/systemd/system/homelab-panel.service'
ok "S1 the panel's service stops only itself on a restart (KillMode=process), so a pool it mounted stays mounted" 'grep -q "^KillMode=process" $HLS_ROOT/etc/systemd/system/homelab-panel.service'
ok "S1 the web terminal: ttyd is installed and its unit runs as the lab user on a socket file (no network port)" 'wj "\"ttyd\" in w[\"pkgs\"]" | grep -q True && U=$HLS_ROOT/etc/systemd/system/homelab-terminal.service && grep -q "^User=testuser" $U && grep -q "ttyd --writable --interface /run/homelab-terminal/ttyd.sock --base-path /terminal" $U && grep -q "^RuntimeDirectoryMode=0700" $U && ! grep -q -- "--port\|--interface 0\|NoNewPrivileges" $U'
ok "S1 the Terminal card is the last card of the Customize tab, after the Customize card" 'grep -q "terminal-card" $HLS_ROOT/home/testuser/homepage-config/services.yaml && ST=$HLS_ROOT/home/testuser/homepage-config/settings.yaml && C=$(grep -n "^  Customize:" $ST | cut -d: -f1) && T=$(grep -n "^  Terminal:" $ST | cut -d: -f1) && [ -n "$C" ] && [ -n "$T" ] && [ "$T" -gt "$C" ] && sed -n "$((T+1))p" $ST | grep -q "tab: Customize"'
ok "S1 the control panel has its Tailscale address 1100, pointing at 127.0.0.1:8300" 'wj "w[\"ts\"][\"serve\"][\"1100\"]" | grep -q "http://127.0.0.1:8300"'
ok "S1 the Customize tab and its card are on the dashboard" 'grep -q "customize-card" $HLS_ROOT/home/testuser/homepage-config/services.yaml && grep -q "Customize" $HLS_ROOT/home/testuser/homepage-config/settings.yaml'
ok "S1 serve targets use the LAN address" 'wj "w[\"ts\"][\"serve\"][\"1005\"]" | grep -q "http://192.168.50.23:8082"'
# the Tailscale widget key
printf '%s\n' y tskey-api-VALID123 | hls fill > $SIM_DIR/s1c.out 2>&1
ok "S1 fill writes the tested Tailscale key" 'grep -q "tskey-api-VALID123" $HLS_ROOT/home/testuser/homepage-config/services.yaml && grep -q "deviceid: nTESTCNTRL" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
# a wrong key must NOT be written
H0=$(sha256sum $HLS_ROOT/home/testuser/homepage-config/services.yaml | cut -d' ' -f1)
# (re-run fill on a done step does nothing; tested in S5)
ok "S1 fill does not tell the user to start the walk-through while inside it" '! grep -q "start the walk-through" $SIM_DIR/s1c.out && grep -q "then paste it below" $SIM_DIR/s1c.out'
ok "S1 with no backup drive FileBrowser shows no drive folder (no boot drive, no main pool)" '! wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]" | grep -q "/srv"'
ok "S1 the FileBrowser card on Homepage no longer names a 750GB drive" '! grep -q "750GB HDD" $HLS_ROOT/home/testuser/homepage-config/services.yaml && grep -q "Browse and Edit Files" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
ok "S1 the first Homepage resources pill is the shipped HomeLab label, not the original server" '! grep -q "label: Server" $HLS_ROOT/home/testuser/homepage-config/widgets.yaml && grep -q "label: HomeLab" $HLS_ROOT/home/testuser/homepage-config/widgets.yaml'
ok "S1 the Next step section is the last thing printed after the passwords" '[ "$(grep -n "── Next step" $SIM_DIR/s1.out | tail -1 | cut -d: -f1)" -gt "$(grep -n "Generated passwords and keys" $SIM_DIR/s1.out | head -1 | cut -d: -f1)" ] && tail -8 $SIM_DIR/s1.out | grep -q "sudo homelab-setup"'
ok "S1 the Next step section names the HTTPS step (the first thing that waits for a person)" 'sed -n "/── Next step/,\$p" $SIM_DIR/s1.out | grep -q "MagicDNS and HTTPS" && sed -n "/── Next step/,\$p" $SIM_DIR/s1.out | grep -q "sudo homelab-setup refresh"'
ok "S1 a plain checklist run ends with the Next step section too" 'hls 2>&1 | tail -12 | grep -q "Next step\|After each step"'
ok "S1 end of install order: finished, passwords, checklist, next step" 'a=$(grep -n "── Install finished" $SIM_DIR/s1.out | tail -1 | cut -d: -f1); b=$(grep -n "── Generated passwords and keys" $SIM_DIR/s1.out | tail -1 | cut -d: -f1); c=$(grep -n "── Setup" $SIM_DIR/s1.out | tail -1 | cut -d: -f1); d=$(grep -n "── Next step" $SIM_DIR/s1.out | tail -1 | cut -d: -f1); [ "$a" -lt "$b" ] && [ "$b" -lt "$c" ] && [ "$c" -lt "$d" ]'
ok "S1 the finished box shows the time taken and the Homepage address" 'grep -q "Finished in .*steps are done" $SIM_DIR/s1.out && grep -q "Your lab is running. Open Homepage: http" $SIM_DIR/s1.out'
ok "S1 the welcome screen lists what to have ready" 'grep -q "Have ready:" $SIM_DIR/s1.out && grep -q "30 to 60 minutes" $SIM_DIR/s1.out'
ok "S1 the plan is grouped, with a line for each group and the by-hand list" 'grep -qE "^   System +[0-9]+  " $SIM_DIR/s1.out && grep -q "steps need you:" $SIM_DIR/s1.out && grep -q "(during the install)" $SIM_DIR/s1.out'
ok "S1 without a terminal every step prints its number and then its result" 'grep -qE "· .*\(step 1 of [0-9]+\)" $SIM_DIR/s1.out && ! grep -q $'"'"'\r'"'"' $SIM_DIR/s1.out'
ok "S1 the checklist is compact: the open-step instructions appear only in Next step" '! sed -n "/── Setup/,/── Next step/p" $SIM_DIR/s1.out | grep -q "scroll to HTTPS" && sed -n "/── Next step/,\$p" $SIM_DIR/s1.out | grep -q "scroll to HTTPS"'
ok "S1 the checklist tags what needs the person" 'sed -n "/── Setup/,/── Next step/p" $SIM_DIR/s1.out | grep -q "you do this" && sed -n "/── Setup/,/── Next step/p" $SIM_DIR/s1.out | grep -q "detected automatically"'
ok "S1 --details brings the full instructions back" 'hls --details 2>&1 | grep -q "sudo drives"'
ok "S1 hls without --details does not repeat the instructions in the checklist" '! hls 2>&1 | sed -n "/steps done/,/── Next step/p" | grep -q "sudo drives"'
ok "S1 checklist now lists only the by-hand items (the panel password among them)" '[ "$(hls 2>&1 | grep -c "^   ○")" = 6 ]'
# ---- weather: the city chosen at install is written into widgets.yaml and the step ticks itself
ok "S1 weather: the city's coordinates are in widgets.yaml" 'grep -q "latitude: 40.7143" $HLS_ROOT/home/testuser/homepage-config/widgets.yaml && grep -q "longitude: -74.0060" $HLS_ROOT/home/testuser/homepage-config/widgets.yaml && grep -q "label: \"New York\"" $HLS_ROOT/home/testuser/homepage-config/widgets.yaml'
ok "S1 weather: the step is done without any manual action" '! hls 2>&1 | grep -q "○ Homepage weather location"'
# ---- blocklists: added through AdGuard Home's API during install
ok "S1 blocklists: HaGeZi Pro and Peter Lowe's were added and are on" 'grep -q "HaGeZi" $HLS_ROOT/opt/adguard-docker/conf/AdGuardHome.yaml && grep -q "Peter Lowe" $HLS_ROOT/opt/adguard-docker/conf/AdGuardHome.yaml && [ "$(grep -c "enabled: true" $HLS_ROOT/opt/adguard-docker/conf/AdGuardHome.yaml)" -ge 3 ]'
ok "S1 blocklists: the step is done without any manual action" '! hls 2>&1 | grep -q "○ AdGuard Home blocklists"'
# ---- the steps that tick themselves (each one: not yet -> done)
hls refresh > $SIM_DIR/s1d.out 2>&1
for id in "Your devices use AdGuard" "Speedtest Tracker has run" "Rebooted once" "Generated passwords copied"; do
  ok "S1 auto: '$id' is still open before anything is done" 'hls 2>&1 | grep -q "○ $id"'
done
setw adguard.clients '[{"127.0.0.1": 3}, {"172.18.0.4": 9}]'
ok "S1 auto: only this machine and Docker asking DNS does not count as a device" 'hls 2>&1 | grep -q "○ Your devices use AdGuard"'
setw adguard.clients '[{"127.0.0.1": 3}, {"172.18.0.4": 9}, {"192.168.50.77": 5}]'
ok "S1 auto: a real device asking DNS ticks the step" '[ "$(hls 2>&1 | grep -c "○ Your devices use AdGuard")" = 0 ]'
ok "S1 auto: speed test step waits for a first result" 'hls 2>&1 | grep -q "○ Speedtest Tracker has run"'
setw speedtest.results 1
ok "S1 auto: speed test step ticks itself after a result exists" '[ "$(hls 2>&1 | grep -c "○ Speedtest Tracker has run")" = 0 ]'
ok "S1 auto: reboot step waits while the boot id is the same" 'hls 2>&1 | grep -q "○ Rebooted once"'
export HLS_BOOT_ID=boot-B
ok "S1 auto: reboot step ticks itself after a restart with every container up" '[ "$(hls 2>&1 | grep -c "○ Rebooted once")" = 0 ]'
ok "S1 auto: the password-manager step, the panel password and the data drive are left" '[ "$(hls 2>&1 | grep -c "^   ○")" = 3 ]'
export HLS_BOOT_ID=boot-A
hls secrets > $SIM_DIR/s1sec.out 2>&1
ok "S1 auto: showing the passwords with the secrets command ticks the password step" '[ "$(hls 2>&1 | grep -c "○ Generated passwords copied")" = 0 ]'
hls skip data-drive >/dev/null 2>&1
hls skip panel-password >/dev/null 2>&1
ok "S1 when complete, the checklist ends with a System check that says everything is up" 'hls 2>&1 | grep -q "System check" && hls 2>&1 | grep -q "Containers: 16 of 16 running" && hls 2>&1 | grep -q "Everything is up and running"'
# services added after the install (cards made by homelab-cards) show up in the System check; a silent one is a warning, not a problem
mkdir -p $HLS_ROOT/var/lib/homelab
cat > $HLS_ROOT/var/lib/homelab/cards.json <<'JSON'
{"managed": {"metube": {"card": "metube-card", "name": "MeTube", "hostport": 8081, "serve": 1010},
             "ghostapp": {"card": "ghostapp-card", "name": "Ghost App", "hostport": 7777, "serve": 0}}, "ignore": []}
JSON
hls > $SIM_DIR/s1extra.out 2>&1
ok "S1 the System check lists a service added later, with its local and Tailscale address" 'grep -q "Other services" $SIM_DIR/s1extra.out && grep -Eq "MeTube +http://[^ ]+:8081" $SIM_DIR/s1extra.out && grep -Eq "MeTube +https://[^ ]+:1010" $SIM_DIR/s1extra.out'
ok "S1 an added service that does not answer is a warning and not a problem" 'grep -q "Ghost App.*no answer: is the container running" $SIM_DIR/s1extra.out && grep -q "Everything is up and running" $SIM_DIR/s1extra.out'
rm -f $HLS_ROOT/var/lib/homelab/cards.json
ok "S1 after done/skip: everything on the list is done" 'hls 2>&1 | grep -q "All steps are complete"'
ok "S1 progress file removed when complete" '[ ! -e $HLS_ROOT/var/lib/homelab/setup-progress ]'
# ---- S2: running install again changes nothing
EV=$(wj "len(w[\"events\"])"); HASH=$(find $HLS_ROOT/home -type f | sort | xargs sha256sum | sha256sum)
printf 'yes\n' | hls install > $SIM_DIR/s2.out 2>&1
ok "S2 second install: says there is nothing to do and asks nothing" 'grep -q "Nothing to do: all steps are complete" $SIM_DIR/s2.out && ! grep -q "Type yes to start" $SIM_DIR/s2.out'
ok "S2 second install: does not print the generated passwords again" '! grep -q "Generated passwords and keys" $SIM_DIR/s2.out && grep -q "Generated passwords and keys" $SIM_DIR/s1.out'
ok "S2 second install: no new actions" '[ "$(wj "len(w[\"events\"])")" = "$EV" ]'
ok "S2 second install: files under /home unchanged" '[ "$(find $HLS_ROOT/home -type f | sort | xargs sha256sum | sha256sum)" = "$HASH" ]'
PF=$HLS_ROOT/var/lib/homelab/setup-progress
printf '1|2|0\n' >$PF
HLS_UPTIME=100 hls progress --quiet >/dev/null 2>&1
ok "S1 scheduled progress check does nothing in the first 10 minutes after a boot" '[ "$(cat $PF)" = "1|2|0" ] && grep -q "homelab-setup progress" $SIM_DIR/crontab'
HLS_UPTIME=100000 hls progress >/dev/null 2>&1
ok "S1 scheduled progress check (output to /dev/null) does nothing while the saved counts are young" '[ "$(cat $PF)" = "1|2|0" ] && grep -q "homelab-setup progress" $SIM_DIR/crontab'
rm -f $PF
HLS_UPTIME=100 hls progress --quiet >/dev/null 2>&1
ok "S1 a boot-time scheduled run leaves the schedule line alone" 'grep -q "homelab-setup progress" $SIM_DIR/crontab'
HLS_UPTIME=100000 hls progress --quiet >/dev/null 2>&1
ok "S1 progress cron line removes itself when complete" '! grep -q "homelab-setup progress" $SIM_DIR/crontab'
ok "S1 the cron step stays done after the progress line is gone" '! hls 2>&1 | grep -q "○ Scheduled jobs"'
fi

# ------------------------------------------------------------------ S3: dry run changes nothing
if scen S3; then
echo "### S3 dry-run on a blank machine"
fresh
HASH0=$(find $HLS_ROOT -type f ! -name homelab-setup.log | sort | xargs sha256sum | sha256sum)
install_in "" y | hls install --dry-run > $SIM_DIR/s3.out 2>&1; RC=$?
ok "S3 dry-run exits 0" '[ $RC -eq 0 ]'
ok "S3 plain mode (no terminal) has no escape codes for the progress bar" '! grep -q $'"'"'\033\[1;[0-9]*r'"'"' $SIM_DIR/s3.out && ! grep -q $'"'"'\033\[?7l'"'"' $SIM_DIR/s3.out'
ok "S3 dry-run shows no failure mark, no placeholder email and no setup token" '! grep -q "✗" $SIM_DIR/s3.out && ! grep -q "you@example.com" $SIM_DIR/s3.out && ! grep -qE "setup-token [A-Za-z0-9]{32}" $SIM_DIR/s3.out'
ok "S3 dry-run does not stop to ask anything about the Tailscale admin page" '! grep -q "Press Enter when it is done" $SIM_DIR/s3.out && grep -q "would ask for MagicDNS and HTTPS" $SIM_DIR/s3.out'
ok "S3 dry-run says it would show a Tailscale login link" 'grep -q "would run: sudo tailscale up" $SIM_DIR/s3.out'
ok "S3 the plan counts exactly the steps the install then runs, and lists a waiting step apart" 'N=$(grep -oE "^  [0-9]+ steps run automatically" $SIM_DIR/s3.out | grep -oE "[0-9]+"); C=$(grep -cE "^  · .*\(step [0-9]+ of" $SIM_DIR/s3.out); [ -n "$N" ] && [ "$N" = "$C" ] && grep -q "more step runs by itself once the steps that need you are done" $SIM_DIR/s3.out'
ok "S3 dry-run mentions the blocklists" 'grep -q "would add HaGeZi" $SIM_DIR/s3.out'
ok "S3 dry-run did not change any file" '[ "$(find $HLS_ROOT -type f ! -name homelab-setup.log | sort | xargs sha256sum | sha256sum)" = "$HASH0" ]'
ok "S3 dry-run started no container, installed no package" '[ "$(wj "len(w[\"containers\"])")" = 0 ] && ! wj "w[\"events\"]" | grep -q "apt install\|apt update\|apt upgrade\|docker pull"'
ok "S3 dry-run left systemd-resolved alone" '[ "$(wj "w[\"units\"][\"systemd-resolved\"]")" = active ]'
ok "S3 dry-run created no state or secrets" '[ ! -e $HLS_ROOT/var/lib/homelab-setup ] && [ ! -e $HLS_ROOT/root/.homelab-setup ]'
ok "S3 dry-run printed what it would do" 'grep -q "would" $SIM_DIR/s3.out'
ok "S3 dry-run left crontab empty" '[ ! -s $SIM_DIR/crontab ]'
fi

# ------------------------------------------------------------------ S4: port 53 is refused over a Tailscale SSH session
if scen S4; then
echo "### S4 port 53 over a Tailscale SSH session"
fresh; approve_in 3
export SIM_SSH_PEER=100.101.102.103
install_in "" y | hls install > $SIM_DIR/s4.out 2>&1
unset SIM_SSH_PEER
ok "S4 systemd-resolved left running (would cut the session)" '[ "$(wj "w[\"units\"][\"systemd-resolved\"]")" = active ]'
ok "S4 resolv.conf unchanged" 'grep -q 127.0.0.53 $HLS_ROOT/etc/resolv.conf'
ok "S4 AdGuard not started" '! wj "list(w[\"containers\"])" | grep -q adguard'
ok "S4 explained why in plain words" 'grep -qi "tailscale" $SIM_DIR/s4.out && grep -qi "port 53\|DNS" $SIM_DIR/s4.out'
ok "S4 other stacks still installed" 'wj "list(w[\"containers\"])" | grep -q portainer && wj "list(w[\"containers\"])" | grep -q netdata'
ok "S4 checklist shows the port 53 step as undone" 'hls 2>&1 | grep -qi "port 53"'
# later, from the LAN, it works
printf 'y\n' | hls refresh > $SIM_DIR/s4b.out 2>&1
ok "S4 from the LAN a refresh frees port 53 and starts AdGuard" '[ "$(wj "w[\"units\"][\"systemd-resolved\"]")" = inactive ] && wj "list(w[\"containers\"])" | grep -q adguard'
fi

# ------------------------------------------------------------------ S5: password rules
if scen S5; then
echo "### S5 weak / mismatched passwords"
fresh
printf '%s\n' Tester tester@example.com "" "" "" "" short Abc12345 "Pass word!12345" | hls install > $SIM_DIR/s5.out 2>&1; RC=$?
ok "S5 three bad passwords stop the install" '[ $RC -ne 0 ] && grep -q "No valid password" $SIM_DIR/s5.out'
ok "S5 too-short password gives the 12 character message" 'grep -q "at least 12" $SIM_DIR/s5.out'
ok "S5 symbols give the letters-and-numbers message" 'grep -q "letters and digits only" $SIM_DIR/s5.out'
ok "S5 nothing was changed on the machine" 'wj "w[\"events\"]" | tee $SIM_DIR/s5.ev | grep -q . ; ! grep -q "apt\|systemctl\|docker" $SIM_DIR/s5.ev'
fresh; approve_in 3
printf '%s\n' Tester tester@example.com "" "" "" "" CorrectHorse1234 Different12345 CorrectHorse1234 CorrectHorse1234 yes "" y | hls install > $SIM_DIR/s5b.out 2>&1
ok "S5 mismatched confirmation is caught and asked again" 'grep -q "did not match" $SIM_DIR/s5b.out && [ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
fi

# ------------------------------------------------------------------ S6: downloads and apt fail
if scen S6; then
echo "### S6 repository key download fails"
fresh; approve_in 3
export HLS_FETCH_FAIL=1
install_in "" y | hls install > $SIM_DIR/s6.out 2>&1
unset HLS_FETCH_FAIL
ok "S6 Docker step is reported failed with the reason" 'hls 2>&1 | grep -q "✗ Docker installed" && hls 2>&1 | grep -q "signing key"'
ok "S6 Tailscale install failure is reported with the manual fallback" 'hls 2>&1 | grep -q "Install Tailscale manually"'
ok "S6 nothing that needs Docker was attempted" '[ "$(wj "len(w[\"containers\"])")" = 0 ]'
ok "S6 the steps that do not need Docker finished (9 of 60)" 'hls 2>&1 | grep -q "9 of 60"'
ok "S6 retry after the network is back finishes the job" '(printf "yes\n\ny\n$PW\n$PW\n" | hls install >/dev/null 2>&1; [ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ])'
echo "### S6b apt update fails"
fresh
export SIM_APT_FAIL=update
install_in "" y | hls install > $SIM_DIR/s6b.out 2>&1
unset SIM_APT_FAIL
ok "S6b apt failure is explained" 'grep -qi "lock\|apt" $SIM_DIR/s6b.out'
ok "S6b no containers started after apt failure" '[ "$(wj "len(w[\"containers\"])")" = 0 ]'
fi

# ------------------------------------------------------------------ S7: Portainer problems
if scen S7; then
echo "### S7 Portainer first-login window already closed"
fresh; approve_in 3; setw portainer.window_closed true
install_in "" y | hls install > $SIM_DIR/s7.out 2>&1
ok "S7 installer restarts Portainer and still creates the admin" '[ "$(wj "w[\"portainer\"][\"admin\"] is not None")" = True ] && [ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
ok "S7 it said why it restarted Portainer" 'grep -qi "restart" $SIM_DIR/s7.out'
echo "### S7b Portainer has no local environment"
export SIM_PORTAINER_NO_LOCAL=1; fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s7b.out 2>&1
unset SIM_PORTAINER_NO_LOCAL
ok "S7b local environment is created by the installer" '[ "$(wj "len(w[\"portainer\"][\"endpoints\"])")" -ge 1 ] && [ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
fi

# ------------------------------------------------------------------ S8: Beszel create-user variants
if scen S8; then
for mode in plain never; do
echo "### S8 Beszel create-user mode: $mode"
export SIM_BESZEL_CREATE=$mode; fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s8$mode.out 2>&1
unset SIM_BESZEL_CREATE
if [ $mode = plain ]; then
ok "S8 plain mode: hub account created" 'hls 2>&1 | grep -q "✓ Logins and keys"'
else
ok "S8 never mode: step fails with a human message, not a crash" 'hls 2>&1 | grep -q "✗ Beszel hub account" && ! grep -q Traceback $SIM_DIR/s8never.out'
ok "S8 never mode: steps that depend on it wait, others finish" 'hls 2>&1 | grep -q "✓ Services" || hls 2>&1 | grep -q "Services  (9 of 10)"'
ok "S8 never mode: the guided step tells the person what to do in the Beszel web page" 'grep -qi "beszel" $SIM_DIR/s8never.out && hls 2>&1 | grep -qi "create\|open"'
fi
done
fi

# ------------------------------------------------------------------ S9: Speedtest token step fails, then fill
if scen S9; then
echo "### S9 speedtest tinker fails"
export SIM_TINKER_FAIL=1; fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s9.out 2>&1
unset SIM_TINKER_FAIL
ok "S9 speedtest widget is reported undone, not crashed" 'hls 2>&1 | grep -q "Speedtest Tracker widget key" && ! grep -q Traceback $SIM_DIR/s9.out'
ok "S9 no half-written key left in services.yaml for speedtest" '! grep -q "st|" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
ok "S9 other widgets unaffected" 'grep -q "Portainer" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
echo "### S9b a WRONG Tailscale API key is refused, a right one accepted"
H0=$(sha256sum $HLS_ROOT/home/testuser/homepage-config/services.yaml | cut -d' ' -f1)
setw ts.https true
printf '%s\n' y tskey-api-WRONG y "" | hls fill > $SIM_DIR/s9b.out 2>&1
H1=$(sha256sum $HLS_ROOT/home/testuser/homepage-config/services.yaml | cut -d' ' -f1)
ok "S9b wrong key leaves services.yaml untouched" '! grep -q "tskey-api-WRONG" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
ok "S9b person is told the key did not work" 'grep -qi "did not work\|rejected\|not accepted\|invalid" $SIM_DIR/s9b.out'
fi

# ------------------------------------------------------------------ S10: Docker Hub rate limit while pulling
if scen S10; then
echo "### S10 image pull throttled once"
export SIM_PULL_THROTTLE=1; fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s10.out 2>&1
unset SIM_PULL_THROTTLE
ok "S10 pull retried and install finished" '[ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
ok "S10 no Traceback" '! grep -q Traceback $SIM_DIR/s10.out'
fi

# ------------------------------------------------------------------ S11: restore from a backup
if scen S11; then
echo "### S11 restore from a backup of the same user"
fresh; approve_in 3; bash $SIMDIR/mkbackup.sh $SIM_DIR/bk testuser
printf '%s\n' Tester tester@example.com "" "" "" "" $PW $PW y y yes "" y RESTORE RESTORE | hls install --backup $SIM_DIR/bk > $SIM_DIR/s11.out 2>&1
ok "S11 install finished all 16 containers" '[ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
ok "S11 photos copied back before Immich started" '[ -f $HLS_ROOT/mnt/storage/immich/library/photo2.jpg ] && [ -f $HLS_ROOT/mnt/storage/nextcloud/data/doc.txt ] && [ -f $HLS_ROOT/mnt/storage/filebrowser/file.txt ]'
ok "S11 saved Homepage settings restored" 'grep -q from_backup $HLS_ROOT/home/testuser/homepage-config/bookmarks.yaml'
ok "S11 Nextcloud config.php restored and its DB password reused" 'grep -q "NC_DB_PASSWORD=OldNcDbPass123456" $HLS_ROOT/root/.homelab-setup/secrets.env'
ok "S11 Nextcloud dump was loaded into the new database" '[ "$(wj "len(w.get(\"psql\", []))")" -ge 3 ]'
ok "S11 backup folder itself was not modified" '[ "$(cat $SIM_DIR/bk/main/immich/library/photo1.jpg)" = photo-bytes-1 ]'
ok "S11 restore asked for the typed word RESTORE" 'grep -q "Type RESTORE" $SIM_DIR/s11.out'
ok "S11 the typed password still never appears in files or logs" '[ -z "$(grep -rl $PW $HLS_ROOT/root $HLS_ROOT/var 2>/dev/null)" ]'
echo "### S11b the person does not type RESTORE"
fresh; approve_in 3; bash $SIMDIR/mkbackup.sh $SIM_DIR/bk testuser
printf '%s\n' Tester tester@example.com "" "" "" "" $PW $PW y y yes "" y no no | hls install --backup $SIM_DIR/bk > $SIM_DIR/s11b.out 2>&1
ok "S11b nothing was copied into /mnt/storage" '[ ! -e $HLS_ROOT/mnt/storage/immich/library/photo1.jpg ]'
ok "S11b the restore step is reported failed, not a crash" 'hls 2>&1 | grep -q "Saved settings restored" && ! grep -q Traceback $SIM_DIR/s11b.out'
ok "S11b steps that must follow the restore did not run (Nextcloud stack waits)" '! wj "list(w[\"containers\"])" | grep -q "^nextcloud$\|nextcloud_db"'
ok "S11b other services still installed" 'wj "list(w[\"containers\"])" | grep -q portainer'
echo "### S12 the backup belongs to another user (otheruser)"
fresh; approve_in 3; bash $SIMDIR/mkbackup.sh $SIM_DIR/bk otheruser
printf '%s\n' Tester tester@example.com "" "" "" "" $PW $PW y yes "" y RESTORE | hls install --backup $SIM_DIR/bk > $SIM_DIR/s12.out 2>&1
ok "S12 warned that the backup is another user's" 'grep -qi "belongs to the user otheruser" $SIM_DIR/s12.out'
ok "S12 saved settings NOT restored, nothing written to /home/otheruser" '[ ! -e $HLS_ROOT/home/otheruser ] && [ ! -e $HLS_ROOT/home/testuser/nextcloud/html/config/config.php ]'
echo "### S13 no backup, and --no-restore"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s13.out 2>&1
ok "S13 says no backup was found" 'grep -qi "No backup found" $SIM_DIR/s13.out'
fresh; approve_in 3; bash $SIMDIR/mkbackup.sh $SIM_DIR/bk testuser
install_in "" y | hls install --backup $SIM_DIR/bk --no-restore > $SIM_DIR/s13b.out 2>&1
ok "S13b --no-restore never reads the backup" '[ ! -e $HLS_ROOT/mnt/storage/immich/library/photo1.jpg ] && ! grep -q "I found a backup" $SIM_DIR/s13b.out'
fi

# ------------------------------------------------------------------ S14: Portainer setup token (new Portainer versions)
if scen S14; then
echo "### S14a installer passes its own setup token to a new Portainer"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s14.out 2>&1
ok "S14a Portainer was started with --setup-token" 'wj "w[\"events\"]" | grep -q "docker run portainer --setup-token"'
ok "S14a admin created and install finished" '[ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
ok "S14a setup token not left in state.json or secrets after use" '! grep -q ptoken $HLS_ROOT/var/lib/homelab-setup/state.json && ! grep -qi setup_token $HLS_ROOT/root/.homelab-setup/secrets.env'
echo "### S14b Portainer was started earlier by hand (no flag): token comes from its log"
fresh; approve_in 3
# a machine that already has Docker and a plain Portainer container
python3 - <<PY
import sys; sys.path.insert(0,"$SIMDIR")
from simlib import World
with World() as w:
    w["bin"].append("docker"); w["units"]["docker"]="active"
PY
mkdir -p $SIM_DIR/bin-installed; ln -sf $SIMDIR/fakecmd.py $SIM_DIR/bin-installed/docker
docker run -d --name portainer -p 9000:9000 portainer/portainer-ce:latest >/dev/null 2>&1
ok "S14b precondition: Portainer runs and has no tool-chosen token" '[ "$(wj "w[\"portainer\"][\"token_in_log\"]")" = True ]'
install_in "" y | hls install > $SIM_DIR/s14b.out 2>&1
ok "S14b token read from the log (ANSI colours stripped); admin created" '[ "$(wj "w[\"portainer\"][\"admin\"] is not None")" = True ]'
ok "S14b install finished" '[ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
echo "### S14c token unknown and not in the log"
fresh; approve_in 3
setw portainer.setup_token '"unknowable-token-123"'
python3 - <<PY
import sys; sys.path.insert(0,"$SIMDIR")
from simlib import World
with World() as w:
    w["bin"].append("docker"); w["units"]["docker"]="active"
    w["containers"]["portainer"]={"image":"x","stack":"","running":True}
    w["portainer"]["token_in_log"]=False
PY
ln -sf $SIMDIR/fakecmd.py $SIM_DIR/bin-installed/docker
install_in "" y | hls install > $SIM_DIR/s14c.out 2>&1
ok "S14c clear refusal, no crash" 'hls 2>&1 | grep -q "✗ Portainer admin account" && ! grep -q Traceback $SIM_DIR/s14c.out'
ok "S14c nothing deployed after the failure" '[ "$(wj "len([c for c in w[\"containers\"] if c != \"portainer\"])")" = 0 ]'
fi

# ------------------------------------------------------------------ S15: Nextcloud's own database user must not replace our password
if scen S15; then
echo "### S15 Nextcloud writes its own oc_ database user into config.php"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s15.out 2>&1
B=$(grep NC_DB_PASSWORD $HLS_ROOT/root/.homelab-setup/secrets.env)
mkdir -p $HLS_ROOT/home/testuser/nextcloud/html/config
printf "<?php\n\$CONFIG = array (\n  'dbuser' => 'oc_Tester',\n  'dbpassword' => '_B?VKNf!_aMh1xLrnrpJX#]-:@!a6u',\n);\n" > $HLS_ROOT/home/testuser/nextcloud/html/config/config.php
printf 'y\n%s\n' $PW | hls refresh > $SIM_DIR/s15b.out 2>&1
ok "S15 secrets file keeps our NC_DB_PASSWORD" '[ "$(grep NC_DB_PASSWORD $HLS_ROOT/root/.homelab-setup/secrets.env)" = "$B" ]'
ok "S15 the secrets step stays done" 'hls 2>&1 | grep -q "✓ Platform"'
ok "S15 FileBrowser login set with the current_password rule enforced" 'hls 2>&1 | grep -qv "✗ FileBrowser" && grep -q "filebrowser" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
fi

# ------------------------------------------------------------------ S16: a service is still starting when first tested (throttle must not hide success)
if scen S16; then
echo "### S16 Netdata answers 503 for its first requests; failed-test throttle is ON"
fresh; approve_in 3; setw netdata_fail 2
unset HLS_NO_THROTTLE
install_in "" y | hls install > $SIM_DIR/s16.out 2>&1
export HLS_NO_THROTTLE=1
ok "S16 Netdata widget ends up done in the same run" '! hls 2>&1 | grep -q "✗ Netdata widget" && grep -q "type: netdata" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
ok "S16 Speedtest token made without tinker (PHP bootstrap) and written" 'grep -q "st|" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
fi

# ------------------------------------------------------------------ S17: a typo on a later run must not create a second password
if scen S17; then
echo "### S17 later run: typo caught by checking the Portainer admin; right password then accepted"
fresh; approve_in 3
# stop after the Portainer admin exists but before the widgets: make the Speedtest widget wait by stopping its container
install_in "" y | hls install > $SIM_DIR/s17.out 2>&1
# a new password-needing step on a later run: remove the Speedtest login from Homepage and re-run it
python3 - <<PY
import re,os
p=os.environ["HLS_ROOT"]+"/home/testuser/homepage-config/services.yaml"
t=open(p).read()
t=re.sub(r"(speedtest-card[\s\S]*?)key:\s*\S+", r"\1key: your-own-key", t, count=1)
open(p,"w").write(t)
PY
printf '%s\n' WrongPassword9999 WrongPassword8888 $PW | hls refresh > $SIM_DIR/s17b.out 2>&1
ok "S17 two wrong passwords were refused with a plain message" '[ "$(grep -c "not the password of the Portainer admin" $SIM_DIR/s17b.out)" = 2 ]'
ok "S17 the right password was then accepted and the step finished" '! hls 2>&1 | grep -q "✗ Speedtest" && ! grep -q "your-own-key" <(grep -A12 speedtest-card $HLS_ROOT/home/testuser/homepage-config/services.yaml)'
ok "S17 the wrong password was never used (Speedtest user still has the real one)" '[ "$(wj "w[\"speedtest\"][\"user\"][\"pw\"]")" = "$PW" ]'
echo "### S17b Portainer admin does not exist yet: the prompt asks twice"
fresh; approve_in 3
printf '%s\n' Tester tester@example.com "" "" "" "" $PW $PW yes "" y | hls install > $SIM_DIR/s17c.out 2>&1
ok "S17b normal install still asks twice at the start and finishes" '[ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
fi

# ------------------------------------------------------------------ S18: the city lookup is unreachable
if scen S18; then
echo "### S18 weather city lookup unreachable: install continues, weather step stays, manual edit still ticks it"
fresh; approve_in 3
HLS_GEOCODE_API=http://127.0.0.1:9 bash -c "$(declare -f install_in hls); PW=$PW; install_in '' y" 2>/dev/null | HLS_GEOCODE_API=http://127.0.0.1:9 hls install > $SIM_DIR/s18.out 2>&1
ok "S18 install finished with a plain warning about the lookup" 'grep -q "city lookup" $SIM_DIR/s18.out && [ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
ok "S18 widgets.yaml keeps the default coordinates" 'grep -q "latitude: 40.7143" $HLS_ROOT/home/testuser/homepage-config/widgets.yaml'
ok "S18 the weather step is still on the list" 'hls 2>&1 | grep -q "○ Homepage weather location"'
sed -i 's/latitude: 40.7143/latitude: 40.67/; s/longitude: -74.0060/longitude: -73.80/' $HLS_ROOT/home/testuser/homepage-config/widgets.yaml
ok "S18 editing the coordinates by hand ticks the step" '[ "$(hls 2>&1 | grep -c "○ Homepage weather location")" = 0 ]'
fi

# ------------------------------------------------------------------ S19: choosing a city
if scen S19; then
echo "### S19 city question: unknown name, then a name with two matches"
fresh; approve_in 3
printf '%s\n' Tester tester@example.com "" Nowhereville Springfield 2 "" "" $PW $PW yes "" y | hls install > $SIM_DIR/s19.out 2>&1
ok "S19 an unknown city gets a plain message and the question is asked again" 'grep -q "No city named .Nowhereville. was found" $SIM_DIR/s19.out'
ok "S19 the second Springfield (Massachusetts) was chosen" 'grep -q "latitude: 42.1015" $HLS_ROOT/home/testuser/homepage-config/widgets.yaml && grep -q "label: \"Springfield\"" $HLS_ROOT/home/testuser/homepage-config/widgets.yaml'
ok "S19 the weather step is done" '! hls 2>&1 | grep -q "○ Homepage weather location"'
fi

# ------------------------------------------------------------------ S20: AdGuard refuses a blocklist
if scen S20; then
echo "### S20 AdGuard Home cannot download a blocklist; later it works; a disabled list is switched on, not duplicated"
fresh; approve_in 3; setw adguard.filter_fail true
install_in "" y | hls install > $SIM_DIR/s20.out 2>&1
ok "S20 the blocklist step failed with a plain message and the install went on" 'grep -q "refused the blocklist" $SIM_DIR/s20.out && [ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
setw adguard.filter_fail false
python3 - <<'PY'
import os
p=os.environ["HLS_ROOT"]+"/opt/adguard-docker/conf/AdGuardHome.yaml"
t=open(p).read()
e="  - enabled: false\n    url: https://adguardteam.github.io/HostlistsRegistry/assets/filter_3.txt\n    name: Peter Lowe's Blocklist\n    id: 7\n"
open(p,"w").write(t.replace("whitelist_filters:", e+"whitelist_filters:",1))
PY
printf '%s\n' $PW | hls refresh > $SIM_DIR/s20b.out 2>&1
ok "S20 refresh turned the disabled list on and added the other one" '[ "$(grep -c "enabled: true" $HLS_ROOT/opt/adguard-docker/conf/AdGuardHome.yaml)" -ge 3 ] && [ "$(grep -c "filter_3.txt" $HLS_ROOT/opt/adguard-docker/conf/AdGuardHome.yaml)" = 1 ]'
ok "S20 the blocklist step is now done" '! hls 2>&1 | grep -q "✗ AdGuard Home blocklists" && ! hls 2>&1 | grep -q "○ AdGuard Home blocklists"'
fi

# ------------------------------------------------------------------ S21: the system check notices a stopped service
if scen S21; then
echo "### S21 verify: a stopped container is reported"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s21.out 2>&1
hls verify > $SIM_DIR/s21a.out 2>&1
ok "S21 verify on a healthy machine reports everything up" 'grep -q "Everything is up and running" $SIM_DIR/s21a.out'
ok "S21 verify lists both the local and the Tailscale addresses" 'grep -q "Services on the local network" $SIM_DIR/s21a.out && grep -q "Services over Tailscale" $SIM_DIR/s21a.out'
setw containers.netdata-netdata-1.running false
hls verify > $SIM_DIR/s21b.out 2>&1
ok "S21 verify reports the stopped container and the service that does not answer" 'grep -q "Containers: 15 of 16 running" $SIM_DIR/s21b.out && grep -q "netdata-netdata-1" $SIM_DIR/s21b.out && grep -q "(no answer)" $SIM_DIR/s21b.out && ! grep -q "Everything is up and running" $SIM_DIR/s21b.out'
fi

# ------------------------------------------------------------------ S22: FileBrowser follows the drives
if scen S22; then
echo "### S22 a backup drive appears and disappears: FileBrowser follows on refresh"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s22.out 2>&1
mkdir -p $HLS_ROOT/mnt/backup
HLS_MOUNTED_BACKUP=1 hls > $SIM_DIR/s22a.out 2>&1
ok "S22 a connected backup pool puts the FileBrowser step back on the list" 'grep -q "○ FileBrowser shows the backup" $SIM_DIR/s22a.out'
HLS_MOUNTED_BACKUP=1 hls refresh > $SIM_DIR/s22b.out 2>&1
ok "S22 refresh redeploys FileBrowser with the backup folder" 'wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]" | grep -q "/srv/Backup-Pool" && ! HLS_MOUNTED_BACKUP=1 hls 2>&1 | grep -q "○ FileBrowser shows this machine"'
ok "S22 nothing but Backup-Pool is shown" '! wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]" | grep -qE "/srv/(main-storage|boot-drive|backup-storage|hdd)"'
hls refresh > $SIM_DIR/s22c.out 2>&1
ok "S22 when the backup pool is gone, refresh removes the backup folder again" '! wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]" | grep -q "/srv/Backup-Pool"'
fi

# ------------------------------------------------------------------ S24: a machine that already runs the lab (read-only)
if scen S24; then
echo "### S24 a server built by hand: the installer only reads it"
export HLS_MOUNTED=1; PATH="$ORIG_PATH"; unset SIM_KEEP; source $SIMDIR/start.sh existing
hls > $SIM_DIR/s24a.out 2>&1
hls install </dev/null > $SIM_DIR/s24b.out 2>&1
ok "S24 the checklist is read-only and counts every step done" 'grep -q "already runs the lab" $SIM_DIR/s24a.out && grep -q "43 of 43 steps done" $SIM_DIR/s24a.out'
ok "S24 install refuses and points at --force-existing" 'grep -q "nothing is installed" $SIM_DIR/s24b.out && grep -q -- "--force-existing" $SIM_DIR/s24b.out'
ok "S24 nothing was run on the machine (no package, container, service or file event)" '[ "$(wj "len(w[\"events\"])")" = 0 ]'
ok "S24 the old ~/750GB_HDD is left alone and no boot-drive-files folder is created" '[ -d $HLS_ROOT/home/testuser/750GB_HDD ] && [ ! -e $HLS_ROOT/home/testuser/boot-drive-files ]'
ok "S24 no installer state or secrets were created" '[ ! -e $HLS_ROOT/var/lib/homelab-setup ] && [ ! -e $HLS_ROOT/root/.homelab-setup ]'
unset HLS_MOUNTED
fi

# ------------------------------------------------------------------ S25: placeholders and the earlier server's values
if scen S25; then
echo "### S25 subst(): placeholders become this machine's values; HOMELAB_OLD_* are optional and empty values match nothing"
ok "S25 placeholders, the earlier server's values (when given) and the empty case" 'python3 $SIMDIR/t_subst.py | tail -1 | grep -q "^OK"'
fi

# ------------------------------------------------------------------ S26: Nextcloud answers on the local address too
if scen S26; then
echo "### S26 Nextcloud is not forced to the Tailscale address; a forced address saved earlier is removed"
ok "S26 the stack has no OVERWRITEHOST or OVERWRITEPROTOCOL, and keeps the proxy list and the command-line address" 'python3 - <<PY
import yaml
e = yaml.safe_load(open("$SIMDIR/../stacks/nextcloud.yaml"))["services"]["app"]["environment"]
assert "OVERWRITEHOST" not in e and "OVERWRITEPROTOCOL" not in e, e
assert "TRUSTED_PROXIES" in e and "OVERWRITECLIURL" in e and "NEXTCLOUD_TRUSTED_DOMAINS" in e
PY'
fresh; approve_in 3; setw nc.conf.overwritehost '"pc.your-tailnet.ts.net:1005"'; setw nc.conf.overwriteprotocol '"https"'
install_in "" y | hls install > $SIM_DIR/s26.out 2>&1
ok "S26 install finished" '[ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
ok "S26 the forced host and protocol saved earlier were removed" '[ "$(wj "\"overwritehost\" in w[\"nc\"][\"conf\"] or \"overwriteprotocol\" in w[\"nc\"][\"conf\"]")" = False ]'
ok "S26 the trusted domains still hold this machine's address and its Tailscale name" 'wj "list(w[\"nc\"][\"domains\"].values())" | grep -q 192.168.50.23'
fi

# ------------------------------------------------------------------ S27: FileBrowser shows Backup-Pool with one folder per backup drive
if scen S27; then
echo "### S27 FileBrowser: only Backup-Pool, with a folder named after each backup drive"
fresh; approve_in 3
mkdir -p $HLS_ROOT/mnt/disks/MAIN1 $HLS_ROOT/mnt/disks/MAIN2 $HLS_ROOT/mnt/disks/BACKUP1 $HLS_ROOT/mnt/disks/BACKUP2 $HLS_ROOT/mnt/disks/BACKUP3 $HLS_ROOT/etc
cat > $SIM_DIR/disks.txt <<DISKS
/|/dev/sda2|sda|Samsung_SSD_860|250059350016||0|sata
/mnt/disks/MAIN1|/dev/sdb1|sdb|TOSHIBA_DT01ACA100|1000204886016|MAIN1|1|sata
/mnt/disks/MAIN2|/dev/sdc1|sdc|ST2000DM008-2FR102|2000398934016|MAIN2|1|usb
/mnt/disks/BACKUP1|/dev/sdd1|sdd|TOSHIBA_DT01ACA100|1000204886016|BACKUP1|1|sata
/mnt/disks/BACKUP2|/dev/sde1|sde|WDC_WD10EZEX|1000204886016|BACKUP2|1|sata
/mnt/disks/BACKUP3|/dev/sdf1|sdf|WDC_WD10EZEX|1000204886016|BACKUP3|1|sata
DISKS
export HLS_MOUNTED_DISKS="MAIN1 MAIN2 BACKUP1 BACKUP2 BACKUP3"
install_in "" y | hls install > $SIM_DIR/s27.out 2>&1
M='wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]"'
ok "S27 install finished with 16 containers" '[ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
ok "S27 every backup drive has a folder inside Backup-Pool, named by size, maker and HDD" 'eval "$M" | grep -q "/srv/Backup-Pool/1 TB Western Digital HDD 1" && eval "$M" | grep -q "/srv/Backup-Pool/1 TB Western Digital HDD 2"'
ok "S27 a backup drive that looks like a main drive is numbered after it (the main one is 1)" 'eval "$M" | grep -q "/srv/Backup-Pool/1 TB Toshiba HDD 2"'
ok "S27 main drives and the system drive are not shown, and nothing sits outside Backup-Pool" '! eval "$M" | grep -q "Seagate" && [ "$(eval "$M" | tr "|" "\n" | grep -c "^/srv/")" = "$(eval "$M" | tr "|" "\n" | grep -c "^/srv/Backup-Pool/")" ] && ! eval "$M" | grep -qE "/srv/(main-storage|backup-storage|boot-drive|hdd|750GB_HDD)"'
ok "S27 the checklist counts the FileBrowser step as done" '! hls 2>&1 | grep -q "○ FileBrowser shows the backup"'
echo "mix: a name you chose wins, and a drive that goes away loses its folder"
printf '# my names\nBACKUP1= Backup: drive/one \n' > $HLS_ROOT/etc/homelab-drive-names
ok "S27 after naming a drive, the checklist says FileBrowser is out of date" 'hls 2>&1 | grep -q "○ FileBrowser shows the backup"'
export HLS_MOUNTED_DISKS="MAIN1 BACKUP1 BACKUP2"
hls filebrowser > $SIM_DIR/s27b.out 2>&1
ok "S27 homelab-setup filebrowser applied the chosen name (unsafe characters removed)" 'eval "$M" | grep -q "/srv/Backup-Pool/Backup drive one"'
ok "S27 the drive that went away has no folder, and the one left alone loses its number" '! eval "$M" | grep -q "Western Digital HDD [12]" && eval "$M" | grep -q "Western Digital HDD"'
hls filebrowser > $SIM_DIR/s27c.out 2>&1
ok "S27 a second run says nothing is to do" 'grep -q "already shows" $SIM_DIR/s27c.out'
export HLS_MOUNTED_DISKS="MAIN1 MAIN2"
hls filebrowser > $SIM_DIR/s27d.out 2>&1
ok "S27 with no backup drive FileBrowser shows no drive folder at all" '! eval "$M" | tr "|" "\n" | grep -q "^/srv/"'
unset HLS_MOUNTED_DISKS
rm -rf $HLS_ROOT/mnt/disks; rm -f $SIM_DIR/disks.txt
fi

# ------------------------------------------------------------------ S28: drives left by an earlier install are pointed out, not touched
if scen S28; then
echo "### S28 a machine whose /etc/fstab still has pool drives from an earlier install"
fresh; approve_in 3
printf 'UUID=abc /mnt/disks/MAIN1 ext4 defaults 0 2\n/mnt/disks/MAIN1 /mnt/storage fuse.mergerfs allow_other 0 0\n' > $HLS_ROOT/etc/fstab
install_in "" y | hls install > $SIM_DIR/s28.out 2>&1
ok "S28 the install says drives from an earlier install are still set up, and how to release them" 'grep -q "/mnt/disks/MAIN1" $SIM_DIR/s28.out && grep -q "sudo drives release" $SIM_DIR/s28.out'
ok "S28 the fstab was not changed" '[ "$(grep -c . $HLS_ROOT/etc/fstab)" = 2 ]'
fi

# ------------------------------------------------------------------ S29: Docker does not answer -> refresh says so at once
if scen S29; then
echo "### S29 refresh stops with a clear message when Docker does not answer"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s29a.out 2>&1
FAKE_DOCKER_DOWN=1 hls refresh </dev/null > $SIM_DIR/s29b.out 2>&1
ok "S29 refresh says Docker is not answering and what to look at" 'grep -q "Docker is not answering" $SIM_DIR/s29b.out && grep -q "systemctl status docker" $SIM_DIR/s29b.out'
hls refresh </dev/null > $SIM_DIR/s29c.out 2>&1
ok "S29 with Docker answering again, refresh runs normally" '! grep -q "Docker is not answering" $SIM_DIR/s29c.out && grep -q "steps done" $SIM_DIR/s29c.out'
fi

# ------------------------------------------------------------------ S30: Immich is still starting after a reboot -> no password question
if scen S30; then
echo "### S30 after a reboot Immich answers late: the admin account is not asked for again"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s30a.out 2>&1
ok "S30 the install created the Immich admin account" '[ "$(wj "w[\"immich\"][\"user\"] is not None")" = True ]'
setw immich.down_config 1
hls refresh </dev/null > $SIM_DIR/s30b.out 2>&1
ok "S30 refresh did not ask for the admin password" '! grep -q "needs the admin password" $SIM_DIR/s30b.out && ! grep -q "answer is required" $SIM_DIR/s30b.out'
ok "S30 the Immich step finished without a question" 'grep -q "✓ Immich admin account created" $SIM_DIR/s30b.out'
fi

# ------------------------------------------------------------------ S31: a backup settings file left by an earlier install names a folder this machine does not have
if scen S31; then
echo "### S31 a stale backup settings file (~/750GB_HDD) is replaced on a machine without that folder"
fresh; approve_in 3
mkdir -p $HLS_ROOT/etc
printf 'DEST_FALLBACK="/home/testuser/750GB_HDD/backup-interim"\n' > $HLS_ROOT/etc/homelab-backup.conf
install_in "" y | hls install > $SIM_DIR/s31.out 2>&1
ok "S31 the settings file now names boot-drive-files" 'grep -q "boot-drive-files/backup-interim" $HLS_ROOT/etc/homelab-backup.conf && ! grep -q 750GB_HDD $HLS_ROOT/etc/homelab-backup.conf'
fi

# ------------------------------------------------------------------ S32: a service does not answer for a minute when the repository is pulled and the installer runs again
if scen S32; then
echo "### S32 Speedtest Tracker does not answer: finished widgets stay done, nothing is redone, no password is asked"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s32a.out 2>&1
SY=$HLS_ROOT/home/testuser/homepage-config/services.yaml
H32=$(sha256sum $SY | cut -d' ' -f1)
setw speedtest.down 1
hls refresh </dev/null > $SIM_DIR/s32b.out 2>&1
ok "S32 no password question while the service is silent" '! grep -q "needs the admin password" $SIM_DIR/s32b.out && ! grep -q "answer is required" $SIM_DIR/s32b.out'
ok "S32 the Homepage config was not touched" '[ "$(sha256sum $SY | cut -d" " -f1)" = "$H32" ]'
ok "S32 the Speedtest widget still counts as done" '! grep -q "✗ Speedtest" $SIM_DIR/s32b.out && ! hls 2>&1 | grep -q "✗ Speedtest"'
ok "S32 no new Speedtest token was made" '[ "$(wj "len(w[\"speedtest\"][\"tokens\"])")" = 1 ]'
echo "### S32b the key is missing AND the service is silent: it waits, then stops before asking for anything"
python3 - <<PY
import re,os
p=os.environ["HLS_ROOT"]+"/home/testuser/homepage-config/services.yaml"
t=open(p).read()
t=re.sub(r"(speedtest-card[\s\S]*?)key:\s*\S+", r"\1key: your-own-key", t, count=1)
open(p,"w").write(t)
PY
hls refresh </dev/null > $SIM_DIR/s32c.out 2>&1
ok "S32b it says the service is not answering and that nothing was asked" 'grep -q "not answering" $SIM_DIR/s32c.out && ! grep -q "needs the admin password" $SIM_DIR/s32c.out'
setw speedtest.down 0
printf '%s\n' $PW $PW | hls refresh > $SIM_DIR/s32d.out 2>&1
ok "S32b when the service answers again the step finishes" '! grep -q "your-own-key" <(grep -A12 speedtest-card $SY)'
fi

# ------------------------------------------------------------------ S33: Homepage must see a pool that is mounted after it started (the Backup pool pill said "API Error")
if scen S33; then
echo "### S33 homelab-setup homepage: the saved Homepage stack gets the whole /mnt folder (rslave) and keeps everything else"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s33a.out 2>&1
ok "S33 a fresh install already uses the /mnt line" 'wj "[s[\"Text\"] for s in w[\"portainer\"][\"stacks\"] if s[\"Name\"]==\"homepage\"][0]" | grep -q "/mnt:/mnt:ro,rslave"'
hls homepage > $SIM_DIR/s33b.out 2>&1
ok "S33 nothing to change: it says Homepage already sees the pools" 'grep -q "already sees the pools" $SIM_DIR/s33b.out'
python3 - <<PY
import json,os
p=os.environ["SIM_DIR"]+"/world.json"
w=json.load(open(p))
for s in w["portainer"]["stacks"]:
    if s["Name"]=="homepage":
        s["Text"]=s["Text"].replace("      - /mnt:/mnt:ro,rslave","      - /mnt/storage:/mnt/storage:ro")
        s["Text"]=s["Text"].replace("image: ghcr.io/gethomepage/homepage:v2.6.0","image: ghcr.io/gethomepage/homepage:v2.7.0")
json.dump(w,open(p,"w"))
PY
hls homepage > $SIM_DIR/s33c.out 2>&1
ok "S33 an older saved stack is changed" 'grep -q "Letting Homepage see the pools" $SIM_DIR/s33c.out && grep -q "Homepage can see the Main and Backup pool" $SIM_DIR/s33c.out'
T33='wj "[s[\"Text\"] for s in w[\"portainer\"][\"stacks\"] if s[\"Name\"]==\"homepage\"][0]"'
ok "S33 the stack now has the /mnt line and not the single line" 'eval "$T33" | grep -q "/mnt:/mnt:ro,rslave" && ! eval "$T33" | grep -q "/mnt/storage:/mnt/storage"'
ok "S33 the newer Homepage version in the saved stack was kept (not downgraded to the repository file)" 'eval "$T33" | grep -q "homepage:v2.7.0"'
CSS33=$HLS_ROOT/home/testuser/homepage-config/custom.css
ok "S33 a fresh install has the new custom.css layout" 'grep -q "How this file is organised" $CSS33 && [ "$(grep -c "^:root" $CSS33)" = 1 ]'
# an older custom.css of this machine: one changed card colour, one changed number, the homelab theme block, a first-generation file
export SIMDIR
python3 - <<PY
import os
p=os.environ["HLS_ROOT"]+"/home/testuser/homepage-config/custom.css"
t=open(os.environ["SIMDIR"]+"/old-custom.css").read()
t=t.replace("#immich-card      { --accent: 209, 18,  18;   }   /* Immich red */","#immich-card      { --accent: 1, 2, 3;   }   /* Immich my own */").replace("--m-gap: 12px;","--m-gap: 20px;")
t+="\n/* >>> homelab theme >>> written by: homelab theme. Remove it with: homelab theme reset */\n.service-card { background: rgba(10, 10, 10, 0.9) !important; }\n/* <<< homelab theme <<< */\n"
open(p,"w").write(t)
PY
ok "S33 (set up) an older custom.css is in place" '! grep -q "How this file is organised" $CSS33 && grep -q "Immich my own" $CSS33'
hls homepage > $SIM_DIR/s33d.out 2>&1
ok "S33 homelab-setup homepage moves the old custom.css to the new layout and says so" 'grep -q "How this file is organised" $CSS33 && grep -q "tidier layout" $SIM_DIR/s33d.out && grep -q "before-layout2" $SIM_DIR/s33d.out'
ok "S33 the old file was saved first, unchanged" '[ -f $CSS33.before-layout2 ] && grep -q "Immich my own" $CSS33.before-layout2 && ! grep -q "How this file is organised" $CSS33.before-layout2'
ok "S33 the changed card colour, the changed number and the theme block were kept" 'grep -q "Immich my own" $CSS33 && grep -q "\-\-m-gap: 20px" $CSS33 && grep -q "rgba(10, 10, 10, 0.9)" $CSS33'
hls homepage > $SIM_DIR/s33e.out 2>&1
ok "S33 a second run does not touch custom.css again" '! grep -q "tidier layout" $SIM_DIR/s33e.out'
fi

# ------------------------------------------------------------------ S34: Nextcloud refuses a token that was only just set (its web side still has the old one cached)
if scen S34; then
echo "### S34 the Nextcloud widget key waits until Nextcloud accepts the new token"
export SIM_NC_TOKEN_LAG=4; fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s34.out 2>&1; RC=$?
unset SIM_NC_TOKEN_LAG
ok "S34 the install finished" '[ $RC -eq 0 ]'
ok "S34 the Nextcloud widget key step passed in spite of the delay" 'grep -q "✓ Nextcloud widget key" $SIM_DIR/s34.out && ! grep -q "✗ Nextcloud widget key" $SIM_DIR/s34.out'
T34=$(grep '^NC_SERVERINFO_TOKEN=' $HLS_ROOT/root/.homelab-setup/secrets.env)
hls refresh > $SIM_DIR/s34b.out 2>&1
ok "S34 a retry keeps the token that works instead of making a new one" '[ "$(grep "^NC_SERVERINFO_TOKEN=" $HLS_ROOT/root/.homelab-setup/secrets.env)" = "$T34" ] && [ -n "$T34" ]'
fi

# ------------------------------------------------------------------ S35: AdGuard Home is optional (the question, the skipped steps, the command that adds it later)
if scen S35; then
echo "### S35 install without AdGuard Home, then add it with: homelab-setup adguard"
fresh; approve_in 3
printf '%s\n' Tester tester@example.com "" "" "" n $PW $PW yes "" y | hls install > $SIM_DIR/s35.out 2>&1; RC=$?
ok "S35 the question is asked and the install finishes" 'grep -q "Install AdGuard Home?" $SIM_DIR/s35.out && [ $RC -eq 0 ]'
ok "S35 no AdGuard container, the other 15 run" '! wj "list(w[\"containers\"])" | grep -q adguard && [ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 15 ]'
ok "S35 port 53 was not touched: systemd-resolved still runs and the question about it was not asked" '[ "$(wj "w[\"units\"][\"systemd-resolved\"]")" = active ] && ! grep -q "Free port 53 now" $SIM_DIR/s35.out'
setw ts.https true
hls refresh > $SIM_DIR/s35r.out 2>&1
ok "S35 nine Tailscale Serve addresses (the panel included), none for AdGuard Home (1004)" '[ "$(wj "len(w[\"ts\"][\"serve\"])")" = 9 ] && ! wj "list(w[\"ts\"][\"serve\"])" | grep -q 1004'
ok "S35 the Homepage dashboard has no AdGuard card but keeps Tailscale and the others" '! grep -q "adguard-card" $HLS_ROOT/home/testuser/homepage-config/services.yaml && grep -q "tailscale-card" $HLS_ROOT/home/testuser/homepage-config/services.yaml && grep -q "beszel-card" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
ok "S35 services.yaml is still valid YAML" 'python3 -c "import yaml,sys; yaml.safe_load(open(\"$HLS_ROOT/home/testuser/homepage-config/services.yaml\"))"'
ok "S35 no AdGuard step is on the checklist, and nothing failed" '! hls 2>&1 | grep -qi "adguard" && ! grep -q "✗" $SIM_DIR/s35.out'
ok "S35 the final check does not list AdGuard Home" '! grep -qi "adguard" <(hls verify 2>&1)'
# add it later
approve_in 3
printf '%s\n' $PW | hls adguard --yes > $SIM_DIR/s35b.out 2>&1; RC=$?
ok "S35 homelab-setup adguard finishes" '[ $RC -eq 0 ]'
ok "S35 AdGuard Home runs now, port 53 is free for it" 'wj "list(w[\"containers\"])" | grep -q adguard && [ "$(wj "w[\"units\"][\"systemd-resolved\"]")" = inactive ]'
ok "S35 the card is back on the dashboard, with its widget filled in" 'grep -q "adguard-card" $HLS_ROOT/home/testuser/homepage-config/services.yaml && python3 -c "import yaml; yaml.safe_load(open(\"$HLS_ROOT/home/testuser/homepage-config/services.yaml\"))" && grep -A12 "adguard-card" $HLS_ROOT/home/testuser/homepage-config/services.yaml | grep -q "type: adguard"'
ok "S35 the Tailscale address for AdGuard Home (1004) is set, ten in all" '[ "$(wj "len(w[\"ts\"][\"serve\"])")" = 10 ] && wj "list(w[\"ts\"][\"serve\"])" | grep -q 1004'
ok "S35 running it again changes nothing and does not ask again" 'printf "%s\n" $PW | hls adguard --yes 2>&1 | grep -q "already part of this machine"'
fi

# ------------------------------------------------------------------ S36: the default answer is yes (pressing Enter installs AdGuard Home)
if scen S36; then
echo "### S36 pressing Enter at the AdGuard Home question installs it"
fresh; approve_in 3
printf '%s\n' Tester tester@example.com "" "" "" "" $PW $PW yes "" y | hls install > $SIM_DIR/s36.out 2>&1; RC=$?
ok "S36 install finishes with all 16 containers" '[ $RC -eq 0 ] && [ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
ok "S36 the dashboard has the AdGuard card" 'grep -q "adguard-card" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
fi

# ------------------------------------------------------------------ S37: `homelab-setup upgrade` (git pull, then the NEW installer's refresh)
if scen S37; then
echo "### S37 upgrade downloads the newest files and runs the new installer"
fresh
ln -sf /usr/bin/git $SIM_DIR/sys-bin/git
git() { /usr/bin/git "$@"; }
U=$SIM_DIR/up; rm -rf $U; mkdir -p $U; git init -q --bare $U/remote.git
git clone -q $U/remote.git $U/work 2>/dev/null; git -C $U/work config user.email t@example.com; git -C $U/work config user.name T
mkdir -p $U/work/installer
printf '#!/usr/bin/env python3\nimport sys\nprint("STUB-REFRESH " + " ".join(sys.argv[1:]))\n' > $U/work/installer/homelab-setup
git -C $U/work add -A; git -C $U/work commit -q -m "first"; git -C $U/work push -q origin HEAD 2>/dev/null
git clone -q $U/remote.git $U/machine 2>/dev/null
echo two > $U/work/two.txt; git -C $U/work add -A; git -C $U/work commit -q -m "second change"; git -C $U/work push -q origin HEAD 2>/dev/null
hls upgrade --dry-run --repo $U/machine > $SIM_DIR/s37a.out 2>&1; RC=$?
ok "S37 --dry-run changes nothing and says what it would do" '[ $RC -eq 0 ] && [ ! -e $U/machine/two.txt ] && grep -q "Would download" $SIM_DIR/s37a.out'
hls upgrade --repo $U/machine > $SIM_DIR/s37b.out 2>&1; RC=$?
ok "S37 upgrade exits 0" '[ $RC -eq 0 ]'
ok "S37 the new file arrived" '[ -e $U/machine/two.txt ]'
ok "S37 it lists what is new" 'grep -q "second change" $SIM_DIR/s37b.out'
ok "S37 the installer from the downloaded files is run with refresh" 'grep -q "^STUB-REFRESH refresh" $SIM_DIR/s37b.out'
hls upgrade --repo $U/machine > $SIM_DIR/s37c.out 2>&1; RC=$?
ok "S37 a second upgrade says it is already the newest" '[ $RC -eq 0 ] && grep -q "Already the newest" $SIM_DIR/s37c.out'
echo three > $U/machine/local.txt; git -C $U/machine add -A; git -C $U/machine -c user.email=a@b -c user.name=A commit -q -m "local only"
echo four > $U/work/four.txt; git -C $U/work add -A; git -C $U/work commit -q -m "third change"; git -C $U/work push -q origin HEAD 2>/dev/null
hls upgrade --repo $U/machine > $SIM_DIR/s37d.out 2>&1; RC=$?
ok "S37 a download that cannot be applied stops with a plain message and no refresh" '[ $RC -ne 0 ] && grep -q "download from GitHub failed" $SIM_DIR/s37d.out && ! grep -q STUB-REFRESH $SIM_DIR/s37d.out'
mkdir -p $U/plain; hls upgrade --repo $U/plain > $SIM_DIR/s37e.out 2>&1; RC=$?
ok "S37 a folder that is not a git copy is explained" '[ $RC -ne 0 ] && grep -q "not a copy downloaded with git" $SIM_DIR/s37e.out'
fi

# ------------------------------------------------------------------ S38: an LVM system volume with unused space is grown (asked first)
if scen S38; then
echo "### S38 the installer offers to use the unused space of an LVM system volume"
fresh
B=$SIM_DIR/bin-always
cat > $B/lvs <<'X'
#!/bin/sh
[ -f "$SIM_DIR/lv.fail" ] && exit 5
IFS='|' read -r size free < "$SIM_DIR/lv.state"
echo "  $size|$free"
X
cat > $B/lvextend <<'X'
#!/bin/sh
echo "$*" >> "$SIM_DIR/lvextend.log"
[ -f "$SIM_DIR/lvextend.fail" ] && { echo "  Insufficient free space"; exit 5; }
IFS='|' read -r size free < "$SIM_DIR/lv.state"
echo "$((size + free))|0" > "$SIM_DIR/lv.state"
X
cat > $B/findmnt.new <<X
#!/bin/sh
case "\$*" in *SOURCE,FSTYPE*) echo "/dev/mapper/ubuntu--vg-ubuntu--lv ext4"; exit 0 ;; esac
exec -a findmnt bash $SIMDIR/fakedisks.sh "\$@"
X
rm -f $B/findmnt; mv $B/findmnt.new $B/findmnt; chmod +x $B/lvs $B/lvextend $B/findmnt
echo "107374182400|639000000000" > $SIM_DIR/lv.state
printf 'n\n' | hls growdisk > $SIM_DIR/s38a.out 2>&1
ok "S38 growdisk says what it found" 'grep -q "has another" $SIM_DIR/s38a.out && grep -q "Nothing is erased" $SIM_DIR/s38a.out'
ok "S38 answering no changes nothing" '[ ! -e $SIM_DIR/lvextend.log ] && grep -q "nothing was changed" $SIM_DIR/s38a.out'
printf 'y\n' | hls growdisk > $SIM_DIR/s38b.out 2>&1
ok "S38 answering yes grows the volume into all the unused space (and the file system with it)" 'grep -q "^-r -l +100%FREE /dev/mapper/ubuntu--vg-ubuntu--lv$" $SIM_DIR/lvextend.log && grep -q "now bigger" $SIM_DIR/s38b.out'
hls growdisk > $SIM_DIR/s38c.out 2>&1
ok "S38 with nothing left to grow it says so and asks nothing" 'grep -q "Nothing to do" $SIM_DIR/s38c.out'
echo "107374182400|10000000000" > $SIM_DIR/lv.state
hls growdisk > $SIM_DIR/s38d.out 2>&1
ok "S38 a small leftover (under 20 GB) is not worth a question" 'grep -q "Nothing to do" $SIM_DIR/s38d.out'
echo "107374182400|639000000000" > $SIM_DIR/lv.state; touch $SIM_DIR/lvextend.fail; rm -f $SIM_DIR/lvextend.log
printf 'y\n' | hls growdisk > $SIM_DIR/s38e.out 2>&1
ok "S38 a failure is explained, says nothing was changed and how to retry" 'grep -q "could not be made bigger" $SIM_DIR/s38e.out && grep -q "Insufficient free space" $SIM_DIR/s38e.out && grep -q "growdisk" $SIM_DIR/s38e.out'
rm -f $SIM_DIR/lvextend.fail $SIM_DIR/lvextend.log
hls install --dry-run > $SIM_DIR/s38f.out 2>&1
ok "S38 a dry run only says what it would offer" 'grep -q "Would offer" $SIM_DIR/s38f.out && [ ! -e $SIM_DIR/lvextend.log ]'
approve_in 3
printf '%s\n' Tester tester@example.com "" "" "" "" $PW $PW y yes "" y | hls install > $SIM_DIR/s38g.out 2>&1; RC=$?
ok "S38 the install asks the question after the password and grows the volume" '[ $RC -eq 0 ] && grep -q "Give the unused space to the system volume" $SIM_DIR/s38g.out && grep -q "^-r -l +100%FREE" $SIM_DIR/lvextend.log'
ok "S38 the answer is kept so a second install does not ask again" 'grep -q "\"lvm_grow\": \"done\"" $HLS_ROOT/var/lib/homelab-setup/state.json'
ok "S38 the install still finishes with all 16 containers" '[ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
fi

# ------------------------------------------------------------------ S39: Homepage tabs reach an older machine once, and taking them out is respected
if scen S39; then
echo "### S39 an older machine gets the Homepage tabs (HOME, LINKS), group icons and tab styles with one refresh, once"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s39a.out 2>&1
HP39=$HLS_ROOT/home/testuser/homepage-config
ok "S39 a fresh install already has the layout, the small settings and the tab styles" 'grep -q "^layout:" $HP39/settings.yaml && grep -q "^hideVersion: true" $HP39/settings.yaml && grep -q "homelab tabs >>>" $HP39/custom.css'
ok "S39 a fresh install has custom.js with the group tags, the music player block and the extras block" 'grep -q "homelab groups >>>" $HP39/custom.js && grep -q "homelab player >>>" $HP39/custom.js && grep -q "homelab extras >>>" $HP39/custom.js'
ok "S39 a fresh install did not make any backup copy" '[ ! -e $HP39/settings.yaml.before-tabs ] && [ ! -e $HP39/custom.css.before-tabs ] && [ ! -e $HP39/services.yaml.before-tabs ]'
ok "S39 a fresh install has the STATS cards (with this machine's address) and the STATS tab" 'grep -q "homelab stats >>>" $HP39/services.yaml && grep -q "id: stat-folders" $HP39/services.yaml && ! grep -q "192.168.X.X:3001/images/stats.json" $HP39/services.yaml && grep -q "/images/stats.json" $HP39/services.yaml && grep -q "tab: Stats" $HP39/settings.yaml && grep -q "^  Folder Sizes:" $HP39/settings.yaml'
ok "S39 a fresh install has the Calendar (its three files exist, the cards read them) and its layout entry" '[ -x $HLS_ROOT/usr/local/bin/homelab-calendar ] && grep -q "homelab calendar >>>" $HP39/services.yaml && ! grep -q "192.168.X.X:3001/images/holidays.ics" $HP39/services.yaml && grep -q "/images/holidays.ics" $HP39/services.yaml && grep -q "^  Calendar:" $HP39/settings.yaml && [ -s $HP39/images/holidays.ics ] && [ -s $HP39/images/observances.ics ] && [ -s $HP39/images/events.ics ] && [ -s $HP39/images/mycalendars.ics ]'
ok "S39 the stats command is installed and scheduled every 15 minutes" '[ -x $HLS_ROOT/usr/local/sbin/homelab-stats ] && grep -q "^5,20,35,50 \* \* \* \* /usr/local/sbin/homelab-stats" $SIM_DIR/crontab'
export HP39
python3 - <<PY
import os,re,json
hp=os.environ["HP39"]
s=open(hp+"/settings.yaml").read()
s=s[:s.index("# Tabs and group icons")].replace("hideVersion: true\n","").replace("language: en\n","")
s=s.replace("title: Home Lab","title: My Own Title")
open(hp+"/settings.yaml","w").write(s)
c=open(hp+"/custom.css").read()
c=c[:c.index("/* >>> homelab tabs >>>")]+"/* mine */\n"
open(hp+"/custom.css","w").write(c)
os.remove(hp+"/custom.js")
v=open(hp+"/services.yaml").read()
open(hp+"/services.yaml","w").write(v[:v.index("# >>> homelab stats >>>")].rstrip("\n")+"\n")
sp=os.environ["HLS_ROOT"]+"/var/lib/homelab-setup/state.json"
st=json.load(open(sp)); st["ran"].pop("homepage-tabs",None); st["ran"].pop("homepage-stats",None); st["ran"].pop("homepage-calendar",None); json.dump(st,open(sp,"w"))
PY
ok "S39 (set up) an older machine: no layout, no tab styles" '! grep -q "^layout:" $HP39/settings.yaml && ! grep -q "homelab tabs" $HP39/custom.css'
hls refresh > $SIM_DIR/s39b.out 2>&1
ok "S39 refresh adds the layout with both tabs and the small settings" 'grep -q "^layout:" $HP39/settings.yaml && grep -q "tab: Links" $HP39/settings.yaml && grep -q "tab: Home" $HP39/settings.yaml && grep -q "^hideVersion: true" $HP39/settings.yaml && grep -q "^language: en" $HP39/settings.yaml'
ok "S39 it keeps this machine's own title and own css rule" 'grep -q "title: My Own Title" $HP39/settings.yaml && grep -q "/\* mine \*/" $HP39/custom.css && grep -q "homelab tabs >>>" $HP39/custom.css'
ok "S39 the old files were saved first" '[ -f $HP39/settings.yaml.before-tabs ] && ! grep -q "^layout:" $HP39/settings.yaml.before-tabs && [ -f $HP39/custom.css.before-tabs ] && ! grep -q "homelab tabs" $HP39/custom.css.before-tabs'
ok "S39 custom.js is back, and the bookmark card styles are in custom.css" 'grep -q "homelab groups >>>" $HP39/custom.js && grep -q "bookmark > a::before" $HP39/custom.css'
ok "S39 it says to reload the dashboard" 'grep -q "Ctrl+Shift+R" $SIM_DIR/s39b.out'
ok "S39 refresh adds the STATS cards at the end of services.yaml and the five groups to the STATS tab" 'grep -q "homelab stats >>>" $HP39/services.yaml && grep -q "id: immich-card" $HP39/services.yaml && python3 - <<PY
import re,os
t=open(os.environ["HP39"]+"/settings.yaml").read()
for g,c in (("At a Glance",4),("Music Library",2),("Library Totals",2),("Storage",3),("Backup & Updates",2),("Folder Sizes",1)):
    assert re.search(r"(?m)^  %s:\n    tab: Stats\n    icon: mdi-[a-z-]+\n    style: row\n    columns: %d\n" % (re.escape(g),c), t), (g, t)
assert "tab: Home\n    icon: mdi-apps" not in t.split("At a Glance:")[1].split("Folder Sizes:")[0]
PY'
ok "S39 the old services.yaml was saved without the STATS cards" '[ -f $HP39/services.yaml.before-tabs ] && ! grep -q "homelab stats" $HP39/services.yaml.before-tabs && grep -q "id: immich-card" $HP39/services.yaml.before-tabs'
ok "S39 it tells how to fill the STATS tab in now" 'grep -q "sudo homelab-stats" $SIM_DIR/s39b.out'
ok "S39 refresh also adds the Calendar (block, layout entry on Home, calendar files) and says how to add an event" 'grep -q "homelab calendar >>>" $HP39/services.yaml && grep -q "^  Calendar:" $HP39/settings.yaml && [ -s $HP39/images/events.ics ] && grep -q "homelab event add" $SIM_DIR/s39b.out && python3 - <<PY
import re,os
t=open(os.environ["HP39"]+"/settings.yaml").read()
assert re.search(r"(?m)^  Calendar:\n    tab: Home\n    icon: mdi-calendar-month\n    style: row\n    columns: 2\n", t), t
PY'
cp $HP39/settings.yaml $SIM_DIR/s39.keep
cp $HP39/services.yaml $SIM_DIR/s39svc.keep
hls refresh > $SIM_DIR/s39c.out 2>&1
ok "S39 a second refresh changes nothing" 'cmp -s $HP39/settings.yaml $SIM_DIR/s39.keep && cmp -s $HP39/services.yaml $SIM_DIR/s39svc.keep && ! grep -q "Ctrl+Shift+R" $SIM_DIR/s39c.out'
printf '\n- Others:\n    - Indeed:\n        - abbr: IN\n          href: https://www.indeed.com/\n' >> $HP39/bookmarks.yaml
hls refresh > $SIM_DIR/s39f.out 2>&1
ok "S39 a bookmark group of this machine that no tab knew is put on LINKS (so it does not show on every tab)" 'python3 - <<PY
import re,os
t=open(os.environ["HP39"]+"/settings.yaml").read()
assert re.search(r"(?m)^  Others:\n    tab: Links\n    icon: mdi-dots-horizontal-circle", t), t
PY'
ok "S39 the first backup copy was kept as it was" '! grep -q "Others" $HP39/settings.yaml.before-tabs && ! grep -q "^layout:" $HP39/settings.yaml.before-tabs'
python3 - <<PY
import os
hp=os.environ["HP39"]
t=open(hp+"/settings.yaml").read()
open(hp+"/settings.yaml","w").write(t.replace("  Others:\n    tab: Links\n    icon: mdi-dots-horizontal-circle\n",""))
PY
hls refresh > $SIM_DIR/s39g.out 2>&1
ok "S39 an entry taken out by hand is not put back" '! grep -q "^  Others:" $HP39/settings.yaml'
python3 - <<PY
import os,re
hp=os.environ["HP39"]
t=open(hp+"/settings.yaml").read()
for a,b in (("Home","HOME"),("Links","LINKS"),("Stats","STATS")):
    t=t.replace("tab: "+a+"\n","tab: "+b+"\n")
for a,b in (("At a Glance","At a glance"),("Library Totals","Library totals"),("Backup & Updates","Backup & updates"),("Folder Sizes","Folder sizes")):
    t=t.replace("  "+a+":\n","  "+b+":\n")
open(hp+"/settings.yaml","w").write(t)
v=open(hp+"/services.yaml").read()
for a,b in (("At a Glance","At a glance"),("Library Totals","Library totals"),("Backup & Updates","Backup & updates"),("Folder Sizes","Folder sizes")):
    v=v.replace("- "+a+":","- "+b+":")
open(hp+"/services.yaml","w").write(v)
PY
hls refresh > $SIM_DIR/s39i.out 2>&1
ok "S39 a machine with the earlier capital tab names and group names is renamed in place (Home, Links, Stats, At a Glance ...)" '! grep -q "tab: HOME\|tab: LINKS\|tab: STATS\|At a glance\|Folder sizes" $HP39/settings.yaml && grep -q "tab: Home" $HP39/settings.yaml && grep -q "tab: Links" $HP39/settings.yaml && grep -q "^  At a Glance:" $HP39/settings.yaml && [ "$(grep -c "^  Folder Sizes:" $HP39/settings.yaml)" = 1 ] && grep -q "^- At a Glance:" $HP39/services.yaml && ! grep -q "^- At a glance:" $HP39/services.yaml'
# a machine from the time before the Music Library and the drive temperatures: Storage had two columns, there was no Music Library entry
python3 - <<PY
import os,re,json
hp=os.environ["HP39"]
t=open(hp+"/settings.yaml").read()
t=t.replace("  Music Library:\n    tab: Stats\n    icon: mdi-music\n    style: row\n    columns: 1\n","")
t=re.sub(r"(  Storage:\n(?:    .*\n)*?    columns: )3", r"\g<1>2", t)
open(hp+"/settings.yaml","w").write(t)
sf=os.environ["HLS_ROOT"]+"/var/lib/homelab-setup/state.json"
st=json.load(open(sf))
st["layout_seen"]=[g for g in st.get("layout_seen",[]) if g!="Music Library" and not g.startswith("~")]
json.dump(st,open(sf,"w"))
PY
hls refresh > $SIM_DIR/s39m.out 2>&1
ok "S39 a machine from before the Music Library gets it right under At a Glance, and the Storage row gets three columns" 'python3 - <<PY
import re,os
t=open(os.environ["HP39"]+"/settings.yaml").read()
assert re.search(r"(?m)^  At a Glance:\n(?:    .*\n)+  Music Library:\n    tab: Stats\n    icon: mdi-music\n    style: row\n    columns: 2\n  Library Totals:", t), t
assert re.search(r"(?m)^  Storage:\n(?:    .*\n)*?    columns: 3\n", t), t
PY'
cp $HP39/settings.yaml $SIM_DIR/s39mk.keep
hls refresh > $SIM_DIR/s39n.out 2>&1
ok "S39 and a later refresh changes nothing more" 'cmp -s $HP39/settings.yaml $SIM_DIR/s39mk.keep'
cp $HP39/settings.yaml $SIM_DIR/s39.keep
python3 - <<PY
import os
hp=os.environ["HP39"]
s=open(hp+"/settings.yaml").read()
open(hp+"/settings.yaml","w").write(s[:s.index("# Tabs and group icons")])
PY
hls refresh > $SIM_DIR/s39d.out 2>&1
ok "S39 taking the layout out is respected (it is not put back)" '! grep -q "^layout:" $HP39/settings.yaml'
hls refresh --dry-run > $SIM_DIR/s39e.out 2>&1
ok "S39 a dry run changes no file" '! grep -q "^layout:" $HP39/settings.yaml'
python3 - <<PY
import os
hp=os.environ["HP39"]
v=open(hp+"/services.yaml").read()
open(hp+"/services.yaml","w").write(v[:v.index("# >>> homelab stats >>>")].rstrip("\n")+"\n")
PY
hls refresh > $SIM_DIR/s39h.out 2>&1
ok "S39 taking the STATS cards out is respected (they are not put back)" '! grep -q "homelab stats" $HP39/services.yaml'
python3 - <<PY
import os
hp=os.environ["HP39"]
v=open(hp+"/services.yaml").read()
open(hp+"/services.yaml","w").write(v[:v.index("# >>> homelab calendar >>>")].rstrip("\n")+"\n")
PY
hls refresh > $SIM_DIR/s39i.out 2>&1
ok "S39 taking the Calendar out is respected too" '! grep -q "homelab calendar" $HP39/services.yaml'
fi

# ------------------------------------------------------------------ S40: Quick Launch, the saved background picture, Navidrome
if scen S40; then
echo "### S40 Quick Launch, the background picture saved on the server, and Navidrome (only with a music folder)"
fresh; approve_in 3
install_in "" y | hls install > $SIM_DIR/s40a.out 2>&1
HP40=$HLS_ROOT/home/testuser/homepage-config
export HP40
ok "S40 a fresh install has Quick Launch in settings.yaml" 'grep -q "^quicklaunch:" $HP40/settings.yaml'
ok "S40 without a music folder there is no Navidrome (no container, no step)" '[ "$(wj "len([c for c in w[\"containers\"] if c == \"navidrome\"])")" = 0 ] && ! grep -q "navidrome" $HP40/services.yaml'
ok "S40 the picture could not be downloaded (no network here): the address stays and the install went on" 'grep -q "image: https://" $HP40/settings.yaml && grep -q "Could not download the background picture" $SIM_DIR/s40a.out'
printf '\x89PNG\r\n\x1a\n0000000000000000' > $SIM_DIR/bg.png
hls refresh > $SIM_DIR/s40b0.out 2>&1
ok "S40 a failed download is not tried again on every run (the next try is a week later)" '! grep -q "Could not download" $SIM_DIR/s40b0.out && grep -q "image: https://" $HP40/settings.yaml'
python3 - <<PY
import json,os
sp=os.environ["HLS_ROOT"]+"/var/lib/homelab-setup/state.json"
st=json.load(open(sp)); st.pop("background_tried",None); json.dump(st,open(sp,"w"))
PY
HLS_FAKE_BG_FILE=$SIM_DIR/bg.png hls refresh > $SIM_DIR/s40b.out 2>&1
ok "S40 with the picture available: it is saved in the images folder and settings.yaml points to it" '[ -s $HP40/images/background.png ] && grep -q "^  image: /images/background.png$" $HP40/settings.yaml && [ -f $HP40/settings.yaml.before-background ] && grep -q "brightness: 42" $HP40/settings.yaml'
cp $HP40/settings.yaml $SIM_DIR/s40.keep
hls refresh > $SIM_DIR/s40c.out 2>&1
ok "S40 a second refresh changes nothing and does not look for the picture again" 'cmp -s $HP40/settings.yaml $SIM_DIR/s40.keep && ! grep -q "Could not download" $SIM_DIR/s40c.out'
python3 - <<PY
import os
p=os.environ["HP40"]+"/settings.yaml"
t=open(p).read().replace("image: /images/background.png","image: https://example.com/mine.jpg")
open(p,"w").write(t)
PY
hls refresh > $SIM_DIR/s40d.out 2>&1
ok "S40 a web address set later on purpose is respected (offered once)" 'grep -q "image: https://example.com/mine.jpg" $HP40/settings.yaml'
python3 - <<PY
import os
p=os.environ["HP40"]+"/settings.yaml"
t=open(p).read()
i=t.index("# Quick Launch:"); j=t.index("# Tabs and group icons")
open(p,"w").write(t[:i]+t[j:])
PY
hls refresh > $SIM_DIR/s40e.out 2>&1
ok "S40 a Quick Launch that was taken out is not put back" '! grep -q "^quicklaunch:" $HP40/settings.yaml'
mkdir -p $HLS_ROOT/mnt/storage/music; echo song > "$HLS_ROOT/mnt/storage/music/Artist - Song.mp3"
printf '\n- Media & Entertainment:\n    - Metube:\n        id: metube-card\n        href: http://192.168.50.23:8086\n        icon: metube.svg\n        description: Video downloader\n\n    - navidrome:\n        id: navidrome-card\n        href: https://pc.example.ts.net:1011\n        siteMonitor: http://192.168.50.23:4533\n        icon: navidrome.svg\n        description: Music streaming server\n' >> $HP40/services.yaml
printf 'y\n%s\n' $PW | hls refresh > $SIM_DIR/s40f.out 2>&1
ok "S40 with a music folder Navidrome is installed and running, with its music folder mounted read-only" '[ "$(wj "w[\"containers\"][\"navidrome\"][\"running\"]")" = True ] && [ -d $HLS_ROOT/home/testuser/navidrome ]'
ok "S40 its login was made with the admin name and the shared password" '[ "$(wj "w[\"navidrome\"][\"user\"]")" = Tester ] && [ "$(wj "w[\"navidrome\"][\"pw\"]")" = $PW ]'
ok "S40 its card shows the Navidrome player (an iframe of this machine address), no password in it, and there is only one card" 'python3 - <<PY
import os,re
t=open(os.environ["HP40"]+"/services.yaml").read()
g=t[t.index("- Media & Entertainment:"):]
names=re.findall(r"(?m)^    - (.+):$", g)
assert names[:2]==["Navidrome","Metube"], names
assert "navidrome-player" not in g.replace("name: navidrome-player",""), g
card=g[g.index("id: navidrome-card"):g.index("id: metube-card")]
assert "description: Music Streaming Server\n" in card and "Music streaming server" not in card, card
assert "widget:\n          type: iframe\n" in card and "src: http://192.168.50.23:4533" in card and "href: https://pc.example.ts.net:1011" in card, card
assert "CorrectHorse1234" not in card and "token:" not in card
PY'
ok "S40 Navidrome's stack file has the Spotify-ish theme and the frame setting, and the installer remembers it deployed it" 'grep -q "ND_DEFAULTTHEME: \"Spotify-ish\"" $SIMDIR/../stacks/navidrome.yaml && grep -q "ND_HTTPHEADERS_FRAMEOPTIONS" $SIMDIR/../stacks/navidrome.yaml && grep -q navidrome_stack $HLS_ROOT/var/lib/homelab-setup/state.json'
ok "S40 the old services.yaml was kept" '[ -f $HP40/services.yaml.before-navidrome ] && ! grep -q "type: navidrome" $HP40/services.yaml.before-navidrome'
cp $HP40/services.yaml $SIM_DIR/s40svc.keep
hls refresh > $SIM_DIR/s40g.out 2>&1
ok "S40 a second refresh changes nothing and asks for no password" 'cmp -s $HP40/services.yaml $SIM_DIR/s40svc.keep && ! grep -qi "admin password" $SIM_DIR/s40g.out'
python3 - <<PY
import os,re
p=os.environ["HP40"]+"/services.yaml"
t=open(p).read()
# the dashboard of zip 33: live numbers in the Navidrome card and a second card for the player
t=re.sub(r"(id: navidrome-card.*?description: Music Streaming Server\n)        widget:\n(?:          [^\n]*\n)+", r"\1        widget:\n          type: navidrome\n          url: http://192.168.50.23:4533\n          user: Tester\n          token: abc\n          salt: xyz\n", t, count=1, flags=re.S)
t=t.rstrip("\n")+"\n\n    - Navidrome Player:\n        id: navidrome-player\n        icon: navidrome.svg\n        widget:\n          type: iframe\n          name: navidrome-player\n          src: http://192.168.50.23:4533\n"
open(p,"w").write(t)
PY
hls refresh > $SIM_DIR/s40h.out 2>&1
ok "S40 a dashboard of the first version (live numbers + a second player card) becomes one card with the player, and asks for no password" 'python3 - <<PY
import os,re
t=open(os.environ["HP40"]+"/services.yaml").read()
assert t.count("id: navidrome-player")==0 and t.count("id: navidrome-card")==1, t
card=t[t.index("id: navidrome-card"):t.index("id: metube-card")]
assert "type: iframe" in card and "type: navidrome" not in card and "token:" not in card, card
PY
[ $? = 0 ] && ! grep -qi "admin password" $SIM_DIR/s40h.out'
python3 - <<PY
import os,re,json
hp=os.environ["HP40"]; p=hp+"/settings.yaml"
t=open(p).read()
i=t.index("layout:\n"); head,body=t[:i+8],t[i+8:]
ents=[]
for l in body.split("\n"):
    if re.match(r"^  \S",l): ents.append([l])
    elif ents and l: ents[-1].append(l)
nm=lambda e:e[0].strip().rstrip(":")
tb=lambda e:next(re.match(r"\s+tab: (\S+)",l).group(1) for l in e if "tab:" in l)
home=[e for e in ents if tb(e)=="Home" and nm(e)!="Calendar"]; links=[e for e in ents if tb(e)=="Links"]; stats=[e for e in ents if tb(e)=="Stats" and nm(e)!="Calendar"]
cal=[e for e in ents if nm(e)=="Calendar"][0]; cal[[k for k,l in enumerate(cal) if "tab:" in l][0]]="    tab: Home"
old=home[:4]+[cal]+home[4:]+links+stats           # the order of zips 29 to 35: Calendar on Home, Links before Stats
open(p,"w").write(head+"\n".join(l for e in old for l in e)+"\n")
sp=os.environ["HLS_ROOT"]+"/var/lib/homelab-setup/state.json"
st=json.load(open(sp)); st["layout_seen"]=[g for g in st.get("layout_seen",[]) if not g.startswith("~stats-before") and not g.startswith("~calendar-on")]
json.dump(st,open(sp,"w"))
PY
hls refresh > $SIM_DIR/s40i.out 2>&1
ok "S40 an older dashboard (Calendar on Home, Links tab before Stats) gets the tabs Home, Stats, Links and the Calendar at the end of Home" 'python3 - <<PY
import os,re
t=open(os.environ["HP40"]+"/settings.yaml").read()
names=re.findall(r"(?m)^  (\S[^:]*):\n    tab: (\S+)", t)
tabs=[]
for n,tb in names:
    if tb not in tabs: tabs.append(tb)
assert tabs==["Home","Stats","Links"], names
order=[n for n,_ in names]
assert order[order.index("Calendar")-1]=="Media & Entertainment" and order[order.index("Calendar")+1]=="At a Glance", order
assert "  Calendar:\n    tab: Home\n" in t, t
PY'
cp $HP40/settings.yaml $SIM_DIR/s40set.keep
hls refresh > $SIM_DIR/s40j.out 2>&1
ok "S40 a second refresh leaves the tab order alone" 'cmp -s $HP40/settings.yaml $SIM_DIR/s40set.keep'
hls verify > $SIM_DIR/s40sys.out 2>&1
ok "S40 the System check counts Navidrome as a container and lists it under the other services" 'grep -Eq "Containers: ([0-9]+) of \1 running" $SIM_DIR/s40sys.out && grep -q "Other services" $SIM_DIR/s40sys.out && grep -Eq "Navidrome +http://[^ ]+:4533" $SIM_DIR/s40sys.out'
# Last.fm key: `homelab-setup lastfm` saves it root-only and deploys Navidrome again with it; a wrong key saves nothing; `lastfm remove` takes it out
LFK=0123456789abcdef0123456789abcdef; LFS=fedcba9876543210fedcba9876543210
printf '%s\n' "not-a-key" "also-not" | hls lastfm > $SIM_DIR/s40lf1.out 2>&1
ok "S40 a wrong Last.fm key is refused and nothing is saved" 'grep -q "does not look like a Last.fm key" $SIM_DIR/s40lf1.out && ! grep -q LASTFM $HLS_ROOT/root/.homelab-setup/secrets.env'
printf '%s\n' "$LFK" "$LFS" | hls lastfm > $SIM_DIR/s40lf2.out 2>&1
ok "S40 the Last.fm key is saved in the root-only secrets file" 'grep -q "^LASTFM_APIKEY=$LFK" $HLS_ROOT/root/.homelab-setup/secrets.env && grep -q "^LASTFM_SECRET=$LFS" $HLS_ROOT/root/.homelab-setup/secrets.env && [ "$(stat -c %a $HLS_ROOT/root/.homelab-setup/secrets.env)" = 600 ]'
ok "S40 Navidrome was deployed again with the key, and the secret is not printed" '[ "$(wj "w[\"stack_env\"][\"navidrome\"][\"LASTFM_APIKEY\"]")" = "$LFK" ] && [ "$(wj "w[\"stack_env\"][\"navidrome\"][\"LASTFM_SECRET\"]")" = "$LFS" ] && ! grep -q "$LFS" $SIM_DIR/s40lf2.out'
ok "S40 the Navidrome stack file passes the two Last.fm settings on" 'grep -q "ND_LASTFM_APIKEY: \"\${LASTFM_APIKEY:-}\"" $SIMDIR/../stacks/navidrome.yaml && grep -q "ND_LASTFM_SECRET" $SIMDIR/../stacks/navidrome.yaml'
hls lastfm remove > $SIM_DIR/s40lf3.out 2>&1
ok "S40 lastfm remove takes the key out and deploys Navidrome without it" '! grep -q LASTFM $HLS_ROOT/root/.homelab-setup/secrets.env && [ -z "$(wj "w[\"stack_env\"][\"navidrome\"][\"LASTFM_APIKEY\"]")" ]'
# renamed commands: copies of the old names left by an earlier install are removed, the new names are installed
ok "S40 the repository check is installed as homelab-repocheck and no retired command is on the machine" '[ -x $HLS_ROOT/usr/local/bin/homelab-repocheck ] && [ ! -e $HLS_ROOT/usr/local/bin/homelab-check ] && [ ! -e $HLS_ROOT/usr/local/bin/hdd-recover ]'
printf '#!/bin/sh\n' > $HLS_ROOT/usr/local/bin/hdd-recover; printf '#!/bin/sh\n' > $HLS_ROOT/usr/local/bin/homelab-check
hls refresh > $SIM_DIR/s40k.out 2>&1
ok "S40 a refresh removes the retired hdd-recover and homelab-check" '[ ! -e $HLS_ROOT/usr/local/bin/hdd-recover ] && [ ! -e $HLS_ROOT/usr/local/bin/homelab-check ] && [ -x $HLS_ROOT/usr/local/bin/homelab-repocheck ]'
# AudioMuse-AI: asked for with `homelab-setup audiomuse`; its own Navidrome login, the plugin, a memory cap you can change, pause and remove
export HLS_RAM_KB=7400000 HLS_CPUS=4                       # this machine has 7.1 GB and 4 cores, like Brandon's
AMEV(){ wj "len([e for e in w[\"events\"] if \"stack updated: audiomuse\" in e or \"stack created: audiomuse\" in e])"; }
hls audiomuse --dry-run > $SIM_DIR/s40am0.out 2>&1
ok "S40 audiomuse --dry-run changes nothing" '[ "$(wj "len([c for c in w[\"containers\"] if c.startswith(\"audiomuse\")])")" = 0 ] && ! grep -q audiomuse $HLS_ROOT/var/lib/homelab-setup/state.json && grep -q "dry run" $SIM_DIR/s40am0.out'
HLS_NO_AVX2=1 hls audiomuse > $SIM_DIR/s40am1.out 2>&1
ok "S40 a processor without AVX2 is refused and nothing is changed" 'grep -q "no AVX2" $SIM_DIR/s40am1.out && [ "$(wj "len([c for c in w[\"containers\"] if c.startswith(\"audiomuse\")])")" = 0 ]'
( export SIM_PORT_BUSY=8100:downtify; printf '%s\n' y | hls audiomuse ) > $SIM_DIR/s40am1b.out 2>&1
ok "S40 a port that another container already uses is refused with that container's name and nothing is changed" 'grep -q "Port 8100 is already used by the container downtify" $SIM_DIR/s40am1b.out && [ "$(wj "len([c for c in w[\"containers\"] if c.startswith(\"audiomuse\")])")" = 0 ]'
printf '%s\n' n | hls audiomuse > $SIM_DIR/s40am2.out 2>&1
ok "S40 answering no to the question changes nothing" '[ "$(wj "len([c for c in w[\"containers\"] if c.startswith(\"audiomuse\")])")" = 0 ] && ! grep -q audiomuse $HLS_ROOT/var/lib/homelab-setup/state.json'
ok "S40 the question explains the memory limit and the first analysis in plain words" 'grep -q "3 GB of memory" $SIM_DIR/s40am2.out && grep -q "a little under the 8 GB" $SIM_DIR/s40am2.out && grep -q "takes hours" $SIM_DIR/s40am2.out'
printf '%s\n' y $PW | hls audiomuse > $SIM_DIR/s40am3.out 2>&1
ok "S40 AudioMuse-AI runs: database, web page and worker" '[ "$(wj "len([c for c in w[\"containers\"] if c.startswith(\"audiomuse\") and w[\"containers\"][c][\"running\"]])")" = 3 ]'
ok "S40 its five generated secrets are saved root-only and none is printed" 'for k in AUDIOMUSE_DB_PASSWORD AUDIOMUSE_ND_PASSWORD AUDIOMUSE_PASSWORD AUDIOMUSE_TOKEN AUDIOMUSE_JWT_SECRET; do v=$(grep "^$k=" $HLS_ROOT/root/.homelab-setup/secrets.env | cut -d= -f2); [ -n "$v" ] && ! grep -q "$v" $SIM_DIR/s40am3.out || exit 1; done; [ "$(stat -c %a $HLS_ROOT/root/.homelab-setup/secrets.env)" = 600 ]'
ok "S40 AudioMuse-AI has its own small Navidrome login and the admin password is not in its stack" '[ "$(wj "len(w[\"navidrome\"][\"users\"])")" = 1 ] && wj "list(w[\"navidrome\"][\"users\"])" | grep -q audiomuse && [ "$(wj "w[\"stack_env\"][\"audiomuse\"][\"AUDIOMUSE_NAVIDROME_USER\"]")" = audiomuse ] && [ "$(wj "w[\"stack_env\"][\"audiomuse\"][\"AUDIOMUSE_NAVIDROME_PASSWORD\"]")" = "$(wj "w[\"navidrome\"][\"users\"][\"audiomuse\"]")" ] && ! wj "w[\"stack_env\"][\"audiomuse\"]" | grep -q "$PW"'
ok "S40 the worker is limited to 3g and 3 of the 4 cores" '[ "$(wj "w[\"stack_env\"][\"audiomuse\"][\"AUDIOMUSE_MEM\"]")" = 3g ] && [ "$(wj "w[\"stack_env\"][\"audiomuse\"][\"AUDIOMUSE_CPUS\"]")" = 3 ]'
ok "S40 the plugin file is in the Navidrome plugins folder and the plugin is on, pointed at AudioMuse-AI with the saved token" '[ -s $HLS_ROOT/home/testuser/navidrome/plugins/audiomuseai.ndp ] && [ "$(wj "w[\"nd_plugins\"][\"audiomuseai\"][\"enabled\"]")" = True ] && [ "$(wj "w[\"nd_plugins\"][\"audiomuseai\"][\"config\"][\"apiToken\"]")" = "$(grep ^AUDIOMUSE_TOKEN= $HLS_ROOT/root/.homelab-setup/secrets.env | cut -d= -f2)" ] && wj "w[\"nd_plugins\"][\"audiomuseai\"][\"config\"][\"apiUrl\"]" | grep -Eq "^http://[0-9.]+:8100$"'
ok "S40 Navidrome was deployed again with audiomuseai first in its agents" '[ "$(wj "w[\"stack_env\"][\"navidrome\"][\"NAVIDROME_AGENTS\"]")" = "audiomuseai,deezer,lastfm,listenbrainz" ]'
ok "S40 the setup tells how to start the analysis" 'grep -q "Start Analysis" $SIM_DIR/s40am3.out && grep -q "AUDIOMUSE_PASSWORD" $SIM_DIR/s40am3.out'
ok "S40 the AudioMuse stack file has no database port on the host and caps the worker with the variables" '! grep -q "5432:5432" $SIMDIR/../stacks/audiomuse.yaml && grep -q "AUDIOMUSE_MEM:-3g" $SIMDIR/../stacks/audiomuse.yaml && grep -q "AUDIOMUSE_CPUS" $SIMDIR/../stacks/audiomuse.yaml'
N0=$(AMEV); hls refresh > $SIM_DIR/s40am4.out 2>&1
ok "S40 a refresh leaves a finished AudioMuse-AI alone (no new deploy)" '[ "$(AMEV)" = "$N0" ]'
hls verify > $SIM_DIR/s40am5.out 2>&1
ok "S40 the System check counts the three AudioMuse containers and lists AudioMuse-AI" 'grep -Eq "Containers: ([0-9]+) of \1 running" $SIM_DIR/s40am5.out && grep -Eq "AudioMuse-AI +http://[^ ]+:8100" $SIM_DIR/s40am5.out'
hls audiomuse memory > $SIM_DIR/s40am6.out 2>&1 < /dev/null
ok "S40 audiomuse memory shows the suggestions for 8 GB and 16 GB machines and what it uses now" 'grep -q "8 GB machine   3 GB" $SIM_DIR/s40am6.out && grep -q "16 GB machine   6 GB" $SIM_DIR/s40am6.out && grep -q "right now: audiomuse-worker" $SIM_DIR/s40am6.out'
hls audiomuse memory 4g > $SIM_DIR/s40am7.out 2>&1
ok "S40 audiomuse memory 4g deploys again with a 4 GB cap" '[ "$(wj "w[\"stack_env\"][\"audiomuse\"][\"AUDIOMUSE_MEM\"]")" = 4096m ] && grep -q "now 4 GB" $SIM_DIR/s40am7.out'
for bad in banana 512m 20g; do hls audiomuse memory $bad > $SIM_DIR/s40am8.out 2>&1; done
ok "S40 a word, a size under 1g or one the machine cannot spare is refused and the cap stays" '[ "$(wj "w[\"stack_env\"][\"audiomuse\"][\"AUDIOMUSE_MEM\"]")" = 4096m ] && grep -q "more than this machine can spare" $SIM_DIR/s40am8.out'
hls audiomuse memory auto > $SIM_DIR/s40am9.out 2>&1
ok "S40 audiomuse memory auto goes back to the suggestion for this machine" '[ "$(wj "w[\"stack_env\"][\"audiomuse\"][\"AUDIOMUSE_MEM\"]")" = 3g ]'
HLS_RAM_KB=16000000 hls audiomuse memory auto > $SIM_DIR/s40am10.out 2>&1
ok "S40 on a 16 GB machine the suggestion is 6g" '[ "$(wj "w[\"stack_env\"][\"audiomuse\"][\"AUDIOMUSE_MEM\"]")" = 6g ]'
hls audiomuse memory auto > /dev/null 2>&1
hls audiomuse pause > $SIM_DIR/s40am11.out 2>&1
ok "S40 pause stops only the worker" '[ "$(wj "w[\"containers\"][\"audiomuse-worker\"][\"running\"]")" = False ] && [ "$(wj "w[\"containers\"][\"audiomuse-flask\"][\"running\"]")" = True ]'
N1=$(AMEV); hls refresh > $SIM_DIR/s40am12.out 2>&1; hls verify > $SIM_DIR/s40am13.out 2>&1
ok "S40 a paused worker is wanted: refresh does not start it and the System check does not call it a fault" '[ "$(AMEV)" = "$N1" ] && [ "$(wj "w[\"containers\"][\"audiomuse-worker\"][\"running\"]")" = False ] && grep -Eq "Containers: ([0-9]+) of \1 running" $SIM_DIR/s40am13.out'
hls audiomuse status > $SIM_DIR/s40am14.out 2>&1
ok "S40 status says the worker is paused on purpose" 'grep -q "paused on purpose" $SIM_DIR/s40am14.out'
hls audiomuse resume > $SIM_DIR/s40am15.out 2>&1
ok "S40 resume starts the worker again" '[ "$(wj "w[\"containers\"][\"audiomuse-worker\"][\"running\"]")" = True ]'
printf '%s\n' y | hls audiomuse remove > $SIM_DIR/s40am16.out 2>&1
ok "S40 remove takes the three containers and the plugin out and puts Navidrome back to its own agents" '[ "$(wj "len([c for c in w[\"containers\"] if c.startswith(\"audiomuse\")])")" = 0 ] && [ ! -e $HLS_ROOT/home/testuser/navidrome/plugins/audiomuseai.ndp ] && [ "$(wj "w[\"nd_plugins\"][\"audiomuseai\"][\"enabled\"]")" = False ] && [ -z "$(wj "w[\"stack_env\"][\"navidrome\"][\"NAVIDROME_AGENTS\"]")" ] && ! grep -q "\"audiomuse\": true" $HLS_ROOT/var/lib/homelab-setup/state.json'
ok "S40 remove keeps the analysis data and the secrets, and says how to free the space" '[ -d $HLS_ROOT/home/testuser/audiomuse/postgres ] && grep -q "^AUDIOMUSE_DB_PASSWORD=" $HLS_ROOT/root/.homelab-setup/secrets.env && grep -q "To free the space" $SIM_DIR/s40am16.out'
( export SIM_PLUGIN_FAIL=1; printf '%s\n' y | hls audiomuse ) > $SIM_DIR/s40am17.out 2>&1
ok "S40 a Navidrome that refuses the plugin gives a plain message and the setup stays unfinished" 'grep -q "could not switch it on" $SIM_DIR/s40am17.out && grep -q "do not fit each other" $SIM_DIR/s40am17.out && ! grep -q "\"audiomuse_plugin\"" $HLS_ROOT/var/lib/homelab-setup/state.json'
hls refresh > $SIM_DIR/s40am18.out 2>&1
ok "S40 the next refresh finishes it, with the same database password as before" '[ "$(wj "w[\"nd_plugins\"][\"audiomuseai\"][\"enabled\"]")" = True ] && [ "$(wj "len([c for c in w[\"containers\"] if c.startswith(\"audiomuse\") and w[\"containers\"][c][\"running\"]])")" = 3 ] && [ "$(wj "w[\"stack_env\"][\"audiomuse\"][\"AUDIOMUSE_DB_PASSWORD\"]")" = "$(grep ^AUDIOMUSE_DB_PASSWORD= $HLS_ROOT/root/.homelab-setup/secrets.env | cut -d= -f2)" ]'
# naviList: asked for with `homelab-setup navilist`; its own Navidrome login, the ListenBrainz token, the playlists subscribed once ListenBrainz has made them
LBT=1b2c3d4e-0000-1111-2222-333344445555
NLEV(){ wj "len([e for e in w[\"events\"] if \"stack updated: navilist\" in e or \"stack created: navilist\" in e])"; }
NLCN(){ wj "len([c for c in w[\"containers\"] if c == \"navilist\"])"; }
hls navilist --dry-run > $SIM_DIR/s40nl0.out 2>&1
ok "S40 navilist --dry-run changes nothing" '[ "$(NLCN)" = 0 ] && ! grep -q navilist $HLS_ROOT/var/lib/homelab-setup/state.json && grep -q "dry run" $SIM_DIR/s40nl0.out'
( export SIM_PORT_BUSY=8200:downtify; printf '%s\n' y | hls navilist ) > $SIM_DIR/s40nl1.out 2>&1
ok "S40 naviList: a port that another container already uses is refused with that container's name" 'grep -q "Port 8200 is already used by the container downtify" $SIM_DIR/s40nl1.out && [ "$(NLCN)" = 0 ]'
printf '%s\n' n | hls navilist > $SIM_DIR/s40nl2.out 2>&1
ok "S40 naviList: answering no changes nothing, and the question says what it does in plain words" '[ "$(NLCN)" = 0 ] && ! grep -q navilist $HLS_ROOT/var/lib/homelab-setup/state.json && grep -q "never downloads anything" $SIM_DIR/s40nl2.out && grep -q "a few days" $SIM_DIR/s40nl2.out'
printf '%s\n' y tester_lb not-a-token | hls navilist > $SIM_DIR/s40nl3.out 2>&1
ok "S40 naviList: a token that is not a ListenBrainz token is refused and nothing is saved" 'grep -q "does not look like a ListenBrainz token" $SIM_DIR/s40nl3.out && ! grep -q NAVILIST $HLS_ROOT/root/.homelab-setup/secrets.env && [ "$(NLCN)" = 0 ]'
printf '%s\n' y tester_lb "" | hls navilist > $SIM_DIR/s40nl4.out 2>&1
ok "S40 naviList: a user name without a token is refused" 'grep -q "needs both the user name and the token" $SIM_DIR/s40nl4.out && [ "$(NLCN)" = 0 ]'
printf '%s\n' y "" "" | hls navilist > $SIM_DIR/s40nl5.out 2>&1
ok "S40 naviList: with no Last.fm key and no ListenBrainz account there is nothing to make playlists from" 'grep -q "needs at least ListenBrainz or Last.fm" $SIM_DIR/s40nl5.out && [ "$(NLCN)" = 0 ]'
printf '%s\n' y tester_lb $LBT $PW | hls navilist > $SIM_DIR/s40nl6.out 2>&1
ok "S40 naviList runs, and says plainly that no Last.fm key is saved" '[ "$(wj "w[\"containers\"][\"navilist\"][\"running\"]")" = True ] && grep -q "No Last.fm key is saved" $SIM_DIR/s40nl6.out'
ok "S40 naviList has its own small Navidrome login, and the admin password is not in its stack" 'wj "list(w[\"navidrome\"][\"users\"])" | grep -q navilist && [ "$(wj "w[\"stack_env\"][\"navilist\"][\"NAVILIST_NAVIDROME_USER\"]")" = navilist ] && [ "$(wj "w[\"stack_env\"][\"navilist\"][\"NAVILIST_NAVIDROME_PASSWORD\"]")" = "$(wj "w[\"navidrome\"][\"users\"][\"navilist\"]")" ] && ! wj "w[\"stack_env\"][\"navilist\"]" | grep -q "$PW"'
ok "S40 the ListenBrainz token and the generated password are saved root-only and not printed" 'grep -q "^NAVILIST_LB_TOKEN=$LBT" $HLS_ROOT/root/.homelab-setup/secrets.env && grep -q "^NAVILIST_LB_USER=tester_lb" $HLS_ROOT/root/.homelab-setup/secrets.env && v=$(grep "^NAVILIST_ND_PASSWORD=" $HLS_ROOT/root/.homelab-setup/secrets.env | cut -d= -f2) && [ -n "$v" ] && ! grep -q "$v" $SIM_DIR/s40nl6.out && ! grep -q "$LBT" $SIM_DIR/s40nl6.out && [ "$(stat -c %a $HLS_ROOT/root/.homelab-setup/secrets.env)" = 600 ]'
ok "S40 the running naviList got the Navidrome login and the ListenBrainz token on its settings page, and read the library" '[ "$(wj "w[\"navilist_app\"][\"settings\"][\"navidrome_user\"]")" = navilist ] && [ "$(wj "w[\"navilist_app\"][\"settings\"][\"listenbrainz_token\"]")" = "$LBT" ] && [ "$(wj "w[\"navilist_app\"][\"settings\"][\"listenbrainz_username\"]")" = tester_lb ] && [ "$(wj "w[\"navilist_app\"][\"library_syncs\"]")" -ge 1 ]'
ok "S40 naviList's data folder is under the home folder, and its stack file uses port 8200 for its own port 3000" '[ -d $HLS_ROOT/home/testuser/navilist/data ] && grep -q "\"8200:3000\"" $SIMDIR/../stacks/navilist.yaml && grep -q "ghcr.io/ofernander/navilist:v" $SIMDIR/../stacks/navilist.yaml'
ok "S40 with ListenBrainz still empty it says the playlists are not there yet and subscribes to nothing" 'grep -q "Not there yet" $SIM_DIR/s40nl6.out && grep -q "a few days" $SIM_DIR/s40nl6.out && [ "$(wj "len(w[\"navilist_app\"][\"lb_subs\"])")" = 0 ] && grep -q "Scrobble to ListenBrainz" $SIM_DIR/s40nl6.out'
touch $SIM_DIR/navilist.lb
hls navilist subscribe > $SIM_DIR/s40nl7.out 2>&1
ok "S40 once ListenBrainz has made the playlists, subscribe takes Weekly Jams and Weekly Exploration and leaves the person's own playlist alone" '[ "$(wj "sorted(w[\"navilist_app\"][\"lb_subs\"])==[\"mbid-we\",\"mbid-wj\"]")" = True ] && grep -q "Subscribed: Weekly Jams" $SIM_DIR/s40nl7.out && grep -q "Subscribed: Weekly Exploration" $SIM_DIR/s40nl7.out'
hls navilist subscribe > $SIM_DIR/s40nl8.out 2>&1
ok "S40 subscribing again changes nothing" 'grep -q "Everything is subscribed already" $SIM_DIR/s40nl8.out && [ "$(wj "len(w[\"navilist_app\"][\"lb_subs\"])")" = 2 ]'
EVN=$(NLEV)
hls refresh > $SIM_DIR/s40nl9.out 2>&1
ok "S40 a second refresh does not deploy naviList again and asks for no password" '[ "$(NLEV)" = "$EVN" ] && ! grep -qi "admin password" $SIM_DIR/s40nl9.out'
printf '%s\n' "$LFK" "$LFS" | hls lastfm > $SIM_DIR/s40nl10.out 2>&1
printf '%s\n' "" "" tester_fm | hls navilist > $SIM_DIR/s40nl11.out 2>&1
ok "S40 with a Last.fm key saved, naviList asks for the Last.fm user name and keeps the ListenBrainz details when Enter is pressed" 'grep -q "^NAVILIST_LASTFM_USER=tester_fm" $HLS_ROOT/root/.homelab-setup/secrets.env && grep -q "^NAVILIST_LB_TOKEN=$LBT" $HLS_ROOT/root/.homelab-setup/secrets.env && [ "$(wj "w[\"stack_env\"][\"navilist\"][\"NAVILIST_LASTFM_KEY\"]")" = "$LFK" ]'
ok "S40 the new Last.fm details reach the running naviList's settings and the two Last.fm charts are subscribed" '[ "$(wj "w[\"navilist_app\"][\"settings\"][\"lastfm_username\"]")" = tester_fm ] && [ "$(wj "w[\"navilist_app\"][\"settings\"][\"lastfm_api_key\"]")" = "$LFK" ] && [ "$(wj "sorted(w[\"navilist_app\"][\"lfm_subs\"])==[\"top_1month\",\"weekly\"]")" = True ]'
hls navilist status > $SIM_DIR/s40nl12.out 2>&1
ok "S40 navilist status shows the web page, the container, the names and what is subscribed" 'grep -Eq "http://[0-9.]+:8200" $SIM_DIR/s40nl12.out && grep -q "navilist  *running" $SIM_DIR/s40nl12.out && grep -q "tester_lb" $SIM_DIR/s40nl12.out && grep -q "tester_fm" $SIM_DIR/s40nl12.out && grep -q "subscribed: Weekly Jams" $SIM_DIR/s40nl12.out'
hls verify > $SIM_DIR/s40nl13.out 2>&1
ok "S40 the System check counts the naviList container and lists it under the other services" 'grep -Eq "Containers: ([0-9]+) of \1 running" $SIM_DIR/s40nl13.out && grep -Eq "naviList +http://[^ ]+:8200" $SIM_DIR/s40nl13.out'
printf '%s\n' y | hls navilist remove > $SIM_DIR/s40nl14.out 2>&1
ok "S40 navilist remove takes the container out and forgets the personal names and token" '[ "$(NLCN)" = 0 ] && ! grep -q "^NAVILIST_LB_TOKEN=" $HLS_ROOT/root/.homelab-setup/secrets.env && ! grep -q "^NAVILIST_LB_USER=" $HLS_ROOT/root/.homelab-setup/secrets.env && ! grep -q "\"navilist\": true" $HLS_ROOT/var/lib/homelab-setup/state.json'
ok "S40 remove keeps the data folder and the Navidrome login, and says the playlists stay" '[ -d $HLS_ROOT/home/testuser/navilist/data ] && wj "list(w[\"navidrome\"][\"users\"])" | grep -q navilist && grep -q "playlists it made are still in Navidrome" $SIM_DIR/s40nl14.out'
printf '%s\n' y tester_lb $LBT tester_fm | hls navilist > $SIM_DIR/s40nl15.out 2>&1
ok "S40 setting it up again reuses the Navidrome login and asks for no admin password" '[ "$(wj "w[\"containers\"][\"navilist\"][\"running\"]")" = True ] && [ "$(wj "len(w[\"navidrome\"][\"users\"])")" = 2 ] && ! grep -qi "admin password" $SIM_DIR/s40nl15.out'
unset HLS_RAM_KB HLS_CPUS
fi

echo; echo "TOTAL pass=$PASS fail=$FAIL"
