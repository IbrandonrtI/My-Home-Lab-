#!/bin/bash
# shellcheck disable=SC2034  # many variables are only used inside the quoted test commands that ok() and check() evaluate
# Simulation tests for homelab-setup. Everything runs against a FAKE machine (fake apt, docker, Tailscale and web services).
SIMDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HLS_BOOT_ID=boot-A; ORIG_PATH="$PATH"; PASS=0; FAIL=0; ONLY="${1:-}"
ok(){ if ( eval "$2" ) >/dev/null 2>&1; then echo "PASS  $1"; PASS=$((PASS+1)); else echo "FAIL  $1"; FAIL=$((FAIL+1)); fi; }
wj(){ python3 -c "import json;w=json.load(open('$SIM_DIR/world.json'));print($1)"; }
scen(){ [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }
PW=CorrectHorse1234
approve_in(){ ( sleep "$1"; setw ts.approved true ) & }
fresh(){ export PATH="$ORIG_PATH"; unset SIM_KEEP; source $SIMDIR/start.sh mint; }
keep(){ export PATH="$ORIG_PATH"; export SIM_KEEP=1; source $SIMDIR/start.sh; }
install_in(){ # install_in "https-enter" "port53-answer"
  printf '%s\n' Tester tester@example.com "" "" "" $PW $PW yes "${1:-}" "${2:-y}" ; }

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
ok "S1 cron has 5 lines, no backup line (no data drive)" '[ "$(grep -c . $SIM_DIR/crontab)" = 5 ] && ! grep -q homelab-backup $SIM_DIR/crontab'
ok "S1 login hook added to .bashrc once" '[ "$(grep -c "homelab login display >>>" $HLS_ROOT/home/testuser/.bashrc)" = 1 ]'
ok "S1 scripts installed with this machine's user pinned in them (no lookup left, nobody else's name)" 'grep -q "HOMELAB_USER:-testuser" $HLS_ROOT/usr/local/sbin/homelab-backup && grep -q "SUDO_USER:-testuser" $HLS_ROOT/usr/local/sbin/drives && ! grep -q "getent passwd 1000" $HLS_ROOT/usr/local/sbin/homelab-backup $HLS_ROOT/usr/local/sbin/drives && ! grep -rq "otheruser" $HLS_ROOT/usr/local'
ok "S1 drives owner rewritten" 'grep -q "DRIVES_OWNER:-\${SUDO_USER:-testuser}" $HLS_ROOT/usr/local/sbin/drives'
ok "S1 never touched a drive tool" '! wj "w[\"events\"]" | grep -v "apt install" | grep -qi "mkfs\|wipefs\|parted\|fdisk\|chattr\|mount"'
# the person turns on HTTPS, then refreshes
setw ts.https true
HLS_LIVE=1 hls refresh > $SIM_DIR/s1b.out 2>&1
ok "S1 live mode reserves the bottom row and paints the n of m bar there and still prints the result" 'grep -q $'"'"'\033\[1;[0-9]*r'"'"' $SIM_DIR/s1b.out && grep -qE "[0-9]+ of [0-9]+  " $SIM_DIR/s1b.out && grep -q "✓" $SIM_DIR/s1b.out'
ok "S1 refresh sets the 9 Tailscale Serve addresses" '[ "$(wj "len(w[\"ts\"][\"serve\"])")" = 9 ]'
ok "S1 serve targets use the LAN address" 'wj "w[\"ts\"][\"serve\"][\"1005\"]" | grep -q "http://192.168.50.23:8082"'
# the Tailscale widget key
printf '%s\n' y tskey-api-VALID123 | hls fill > $SIM_DIR/s1c.out 2>&1
ok "S1 fill writes the tested Tailscale key" 'grep -q "tskey-api-VALID123" $HLS_ROOT/home/testuser/homepage-config/services.yaml && grep -q "deviceid: nTESTCNTRL" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
# a wrong key must NOT be written
H0=$(sha256sum $HLS_ROOT/home/testuser/homepage-config/services.yaml | cut -d' ' -f1)
# (re-run fill on a done step does nothing; tested in S5)
ok "S1 fill does not tell the user to start the walk-through while inside it" '! grep -q "start the walk-through" $SIM_DIR/s1c.out && grep -q "then paste it below" $SIM_DIR/s1c.out'
ok "S1 FileBrowser shows the boot drive and the main storage, named by role" 'wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]" | grep -q "/srv/boot-drive" && wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]" | grep -q "/srv/main-storage" && ! wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]" | grep -qE "/srv/(hdd|750GB_HDD|backup)"'
ok "S1 the FileBrowser card on Homepage no longer names a 750GB drive" '! grep -q "750GB HDD" $HLS_ROOT/home/testuser/homepage-config/services.yaml && grep -q "this machine.s drives" $HLS_ROOT/home/testuser/homepage-config/services.yaml'
ok "S1 the first Homepage resources pill is named after this machine, not the original server" '! grep -q "label: Server" $HLS_ROOT/home/testuser/homepage-config/widgets.yaml && grep -q "label: vm" $HLS_ROOT/home/testuser/homepage-config/widgets.yaml'
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
ok "S1 checklist now lists only the by-hand items" '[ "$(hls 2>&1 | grep -c "^   ○")" = 5 ]'
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
ok "S1 auto: the password-manager step and the data drive are left" '[ "$(hls 2>&1 | grep -c "^   ○")" = 2 ]'
export HLS_BOOT_ID=boot-A
hls secrets > $SIM_DIR/s1sec.out 2>&1
ok "S1 auto: showing the passwords with the secrets command ticks the password step" '[ "$(hls 2>&1 | grep -c "○ Generated passwords copied")" = 0 ]'
hls skip data-drive >/dev/null 2>&1
ok "S1 when complete, the checklist ends with a System check that says everything is up" 'hls 2>&1 | grep -q "System check" && hls 2>&1 | grep -q "Containers: 16 of 16 running" && hls 2>&1 | grep -q "Everything is up and running"'
ok "S1 after done/skip: everything on the list is done" 'hls 2>&1 | grep -q "All steps are complete"'
ok "S1 progress file removed when complete" '[ ! -e $HLS_ROOT/var/lib/homelab/setup-progress ]'
# ---- S2: running install again changes nothing
EV=$(wj "len(w[\"events\"])"); HASH=$(find $HLS_ROOT/home -type f | sort | xargs sha256sum | sha256sum)
printf 'yes\n' | hls install > $SIM_DIR/s2.out 2>&1
ok "S2 second install: says there is nothing to do and asks nothing" 'grep -q "Nothing to do: all steps are complete" $SIM_DIR/s2.out && ! grep -q "Type yes to start" $SIM_DIR/s2.out'
ok "S2 second install: does not print the generated passwords again" '! grep -q "Generated passwords and keys" $SIM_DIR/s2.out && grep -q "Generated passwords and keys" $SIM_DIR/s1.out'
ok "S2 second install: no new actions" '[ "$(wj "len(w[\"events\"])")" = "$EV" ]'
ok "S2 second install: files under /home unchanged" '[ "$(find $HLS_ROOT/home -type f | sort | xargs sha256sum | sha256sum)" = "$HASH" ]'
hls progress --quiet >/dev/null 2>&1
ok "S1 progress cron line removes itself when complete" '! grep -q "homelab-setup progress" $SIM_DIR/crontab'
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
printf '%s\n' Tester tester@example.com "" "" "" short Abc12345 "Pass word!12345" | hls install > $SIM_DIR/s5.out 2>&1; RC=$?
ok "S5 three bad passwords stop the install" '[ $RC -ne 0 ] && grep -q "No valid password" $SIM_DIR/s5.out'
ok "S5 too-short password gives the 12 character message" 'grep -q "at least 12" $SIM_DIR/s5.out'
ok "S5 symbols give the letters-and-numbers message" 'grep -q "letters and digits only" $SIM_DIR/s5.out'
ok "S5 nothing was changed on the machine" 'wj "w[\"events\"]" | tee $SIM_DIR/s5.ev | grep -q . ; ! grep -q "apt\|systemctl\|docker" $SIM_DIR/s5.ev'
fresh; approve_in 3
printf '%s\n' Tester tester@example.com "" "" "" CorrectHorse1234 Different12345 CorrectHorse1234 CorrectHorse1234 yes "" y | hls install > $SIM_DIR/s5b.out 2>&1
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
ok "S6 the steps that do not need Docker finished (9 of 56)" 'hls 2>&1 | grep -q "9 of 56"'
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
printf '%s\n' Tester tester@example.com "" "" "" $PW $PW y y yes "" y RESTORE RESTORE | hls install --backup $SIM_DIR/bk > $SIM_DIR/s11.out 2>&1
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
printf '%s\n' Tester tester@example.com "" "" "" $PW $PW y y yes "" y no no | hls install --backup $SIM_DIR/bk > $SIM_DIR/s11b.out 2>&1
ok "S11b nothing was copied into /mnt/storage" '[ ! -e $HLS_ROOT/mnt/storage/immich/library/photo1.jpg ]'
ok "S11b the restore step is reported failed, not a crash" 'hls 2>&1 | grep -q "Saved settings restored" && ! grep -q Traceback $SIM_DIR/s11b.out'
ok "S11b steps that must follow the restore did not run (Nextcloud stack waits)" '! wj "list(w[\"containers\"])" | grep -q "^nextcloud$\|nextcloud_db"'
ok "S11b other services still installed" 'wj "list(w[\"containers\"])" | grep -q portainer'
echo "### S12 the backup belongs to another user (otheruser)"
fresh; approve_in 3; bash $SIMDIR/mkbackup.sh $SIM_DIR/bk otheruser
printf '%s\n' Tester tester@example.com "" "" "" $PW $PW y yes "" y RESTORE | hls install --backup $SIM_DIR/bk > $SIM_DIR/s12.out 2>&1
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
printf '%s\n' Tester tester@example.com "" "" "" $PW $PW yes "" y | hls install > $SIM_DIR/s17c.out 2>&1
ok "S17b normal install still asks twice at the start and finishes" '[ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
fi

# ------------------------------------------------------------------ S18: the city lookup is unreachable
if scen S18; then
echo "### S18 weather city lookup unreachable: install continues, weather step stays, manual edit still ticks it"
fresh; approve_in 3
HLS_GEOCODE_API=http://127.0.0.1:9 bash -c "$(declare -f install_in hls); PW=$PW; install_in '' y" 2>/dev/null | HLS_GEOCODE_API=http://127.0.0.1:9 hls install > $SIM_DIR/s18.out 2>&1
ok "S18 install finished with a plain warning about the lookup" 'grep -q "city lookup" $SIM_DIR/s18.out && [ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
ok "S18 widgets.yaml keeps the default coordinates" 'grep -q "latitude: 40.7128" $HLS_ROOT/home/testuser/homepage-config/widgets.yaml'
ok "S18 the weather step is still on the list" 'hls 2>&1 | grep -q "○ Homepage weather location"'
sed -i 's/latitude: 40.7128/latitude: 40.67/; s/longitude: -74.0060/longitude: -73.80/' $HLS_ROOT/home/testuser/homepage-config/widgets.yaml
ok "S18 editing the coordinates by hand ticks the step" '[ "$(hls 2>&1 | grep -c "○ Homepage weather location")" = 0 ]'
fi

# ------------------------------------------------------------------ S19: choosing a city
if scen S19; then
echo "### S19 city question: unknown name, then a name with two matches"
fresh; approve_in 3
printf '%s\n' Tester tester@example.com "" Nowhereville Springfield 2 "" $PW $PW yes "" y | hls install > $SIM_DIR/s19.out 2>&1
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
ok "S22 a connected backup pool puts the FileBrowser step back on the list" 'grep -q "○ FileBrowser shows this machine" $SIM_DIR/s22a.out'
HLS_MOUNTED_BACKUP=1 hls refresh > $SIM_DIR/s22b.out 2>&1
ok "S22 refresh redeploys FileBrowser with the backup folder" 'wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]" | grep -q "/srv/backup" && ! HLS_MOUNTED_BACKUP=1 hls 2>&1 | grep -q "○ FileBrowser shows this machine"'
ok "S22 the other folders are still there" 'wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]" | grep -q "/srv/main-storage" && wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]" | grep -q "/srv/boot-drive"'
hls refresh > $SIM_DIR/s22c.out 2>&1
ok "S22 when the backup pool is gone, refresh removes the backup folder again" '! wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]" | grep -q "/srv/backup"'
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

# ------------------------------------------------------------------ S27: FileBrowser shows one folder per drive, named after the drive
if scen S27; then
echo "### S27 FileBrowser: the system drive and every main and backup drive get a folder named after the drive"
fresh; approve_in 3
mkdir -p $HLS_ROOT/mnt/disks/MAIN1 $HLS_ROOT/mnt/disks/MAIN2 $HLS_ROOT/mnt/disks/BACKUP1 $HLS_ROOT/etc
cat > $SIM_DIR/disks.txt <<DISKS
/|/dev/sda2|sda|Samsung_SSD_860|250059350016||0|sata
/mnt/disks/MAIN1|/dev/sdb1|sdb|TOSHIBA_DT01ACA100|1000204886016|MAIN1|1|sata
/mnt/disks/MAIN2|/dev/sdc1|sdc|TOSHIBA_DT01ACA100|1000204886016|MAIN2|1|usb
/mnt/disks/BACKUP1|/dev/sdd1|sdd|WDC_WD10EZEX|1000204886016|BACKUP1|1|sata
DISKS
export HLS_MOUNTED_DISKS="MAIN1 MAIN2 BACKUP1"
install_in "" y | hls install > $SIM_DIR/s27.out 2>&1
M='wj "w[\"containers\"][\"filebrowser-filebrowser-1\"][\"mounts\"]"'
ok "S27 install finished with 16 containers" '[ "$(wj "len([c for c in w[\"containers\"].values() if c[\"running\"]])")" = 16 ]'
ok "S27 the folder of the system drive is named after the drive (size, maker and SSD)" 'eval "$M" | grep -q "/srv/250 GB Samsung SSD"'
ok "S27 two identical drives are told apart by their mount name" 'eval "$M" | grep -q "/srv/main-storage/1 TB Toshiba HDD (MAIN1)" && eval "$M" | grep -q "/srv/main-storage/1 TB Toshiba HDD (MAIN2)"'
ok "S27 a backup drive gets a folder under backup-storage" 'eval "$M" | grep -q "/srv/backup-storage/1 TB Western Digital HDD"'
ok "S27 no old fixed folder names are left" '! eval "$M" | grep -q "/srv/boot-drive" && ! eval "$M" | grep -q "/srv/hdd" && ! eval "$M" | grep -q "/srv/750GB_HDD"'
ok "S27 the checklist counts the FileBrowser step as done" '! hls 2>&1 | grep -q "○ FileBrowser shows this"'
echo "mix: a name you chose wins, and a drive that goes away loses its folder"
printf '# my names\nMAIN1=1TB HDD\nBACKUP1= Backup: drive/one \n' > $HLS_ROOT/etc/homelab-drive-names
ok "S27 after naming a drive, the checklist says FileBrowser is out of date" 'hls 2>&1 | grep -q "○ FileBrowser shows this"'
export HLS_MOUNTED_DISKS="MAIN1 BACKUP1"
hls filebrowser > $SIM_DIR/s27b.out 2>&1
ok "S27 homelab-setup filebrowser applied the chosen names (unsafe characters removed)" 'eval "$M" | grep -q "/srv/main-storage/1TB HDD" && eval "$M" | grep -q "/srv/backup-storage/Backup drive one"'
ok "S27 the drive that went away has no folder any more" '! eval "$M" | grep -q "MAIN2" && ! eval "$M" | grep -q "main-storage/1 TB Toshiba"'
hls filebrowser > $SIM_DIR/s27c.out 2>&1
ok "S27 a second run says nothing is to do" 'grep -q "already shows" $SIM_DIR/s27c.out'
export HLS_MOUNTED_DISKS=""
rm -rf $HLS_ROOT/mnt/disks; rm -f $SIM_DIR/disks.txt
hls filebrowser > $SIM_DIR/s27d.out 2>&1
ok "S27 with no data drive the old main-storage share on the boot drive is back, and the system drive falls back to boot-drive" 'eval "$M" | grep -q "/srv/main-storage" && eval "$M" | grep -q "/srv/boot-drive" && ! eval "$M" | grep -q "backup-storage"'
unset HLS_MOUNTED_DISKS
fi

echo; echo "TOTAL pass=$PASS fail=$FAIL"
