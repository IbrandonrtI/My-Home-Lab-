#!/bin/bash
# shellcheck disable=SC2034  # many variables are only used inside the quoted test commands that ok() and check() evaluate
# Tests for the login screen (scripts/homelab) against fake state files; nothing on this machine is touched.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
H="${H:-$HERE/../scripts/homelab}"; T="${TMPDIR:-/tmp}/homelab-login-test"; PASS=0; FAIL=0
check(){ if ( eval "$2" ); then echo "PASS  $1"; PASS=$((PASS+1)); else echo "FAIL  $1"; FAIL=$((FAIL+1)); fi; }
NOW=$(date +%s)
reset(){
  rm -rf $T; mkdir -p $T/bin $T/state $T/fd
  printf '%s|OK|/bk|55|65432198765\n' "$(date '+%F %H:%M')" >$T/last-run
  printf 'boot|/dev/sdb|41|%s\nMAIN1|/dev/sda|38|%s\n' $NOW $NOW >$T/state/temps
  printf '12|%s\n' $NOW >$T/state/apt
  printf '0|6|*|*|*|%s\n' $NOW >$T/state/schedule
  S=$(date -d '30 minutes ago' +%Y-%m-%dT%H:%M:%S.123456789Z -u)
  printf '/immich_server running always 0 %s\n/homepage running always 0 %s\n/portainer running always 1 %s\n' $S $S $S >$T/fd/inspect
  cat >$T/bin/docker <<'D'
#!/bin/bash
FD="$LOGIN_TEST_FD"
case "$1" in
 info) exit 0;;
 ps) if [ "$2" = "-aq" ]; then echo abc; else :; fi;;
 inspect) cat $FD/inspect;;
esac
D
  printf '#!/bin/bash\ncat >/dev/null\n' >$T/bin/xargs_unused
  chmod +x $T/bin/docker
  export LOGIN_TEST_FD=$T/fd
  export HOMELAB_LAST_RUN_FILE=$T/last-run HOMELAB_STATE_DIR=$T/state PATH=$T/bin:$PATH NO_COLOR=1 COLUMNS=120 LC_ALL=C.UTF-8 HOMELAB_MAIN_POOL=/nonexistent-pool
}
runh(){ bash "$H" "$@" 2>&1; }
reset; out=$(runh)
check "version 2.0" '[ "$(runh version)" = "homelab 2.0" ]'
check "backup size shown in GB" 'echo "$out" | grep -q "Backup size .*61GB in the backup, next run 06:00 (in "'
check "temps shown" 'echo "$out" | grep -q "Drive temps .*boot 41°C, MAIN1 38°C"'
check "updates shown" 'echo "$out" | grep -q "Updates .*12 system update(s)"'
check "restart shown with count" 'echo "$out" | grep -q "Restarts .*portainer (1x)"'
check "restart not shown for count 0" '! echo "$out" | grep "Restarts" | grep -q "homepage"'
check "existing lines remain" 'echo "$out" | grep -q "Last backup" && echo "$out" | grep -q "Containers" && echo "$out" | grep -q "Boot drive"'
reset; printf 'boot|/dev/sdb|41|%s\nMAIN1|/dev/sda|standby|%s\n' $NOW $NOW >$T/state/temps; out=$(runh); check "standby shown as asleep" 'echo "$out" | grep -q "MAIN1 asleep"'
reset; printf 'boot|/dev/sdb|52|%s\n' $NOW >$T/state/temps; out=$(runh); check "52C -> getting warm" 'echo "$out" | grep -q "Drive temps .*52°C -> getting warm"'
reset; printf 'boot|/dev/sdb|61|%s\n' $NOW >$T/state/temps; out=$(runh); check "61C -> too hot" 'echo "$out" | grep -q "61°C -> too hot"'
reset; printf 'boot|/dev/sdb|41|%s\n' $((NOW-7200)) >$T/state/temps; out=$(runh); check "old readings flagged" 'echo "$out" | grep -q "readings are 120 min old"'
reset; rm $T/state/temps; out=$(runh); check "no temps file -> hint" 'echo "$out" | grep -q "no readings yet (run: sudo homelab-sample"'
reset; : >$T/state/temps; out=$(runh); check "empty temps -> smartmontools hint" 'echo "$out" | grep -q "no readings (is smartmontools installed"'
reset; printf '0|%s\n' $NOW >$T/state/apt; out=$(runh); check "no updates -> up to date" 'echo "$out" | grep -q "Updates .*system is up to date"'
reset; rm $T/state/apt; out=$(runh); check "no apt file and no image file -> no Updates line" '! echo "$out" | grep -q "  Updates  "'
reset; printf '%s\nimmich\nnextcloud_app extra words\n' $((NOW-86400*2)) >$T/state/image-updates; out=$(runh); check "image updates listed" 'echo "$out" | grep -q "Updates .*12 system update(s); newer images: immich, nextcloud_app (checked 2 d ago)"'
reset; printf '%s\n' $NOW >$T/state/image-updates; printf '0|%s\n' $NOW >$T/state/apt; out=$(runh); check "image check found nothing" 'echo "$out" | grep -q "Updates .*system is up to date; container images up to date"'
reset; printf '%s|OK|/bk|55\n' "$(date '+%F %H:%M')" >$T/last-run; out=$(runh); check "old 4-field status file: size placeholder" 'echo "$out" | grep -q "size shows after the next backup run, next run 06:00"'
reset; : >$T/state/schedule; out=$(runh); check "empty schedule -> size without next run" 'echo "$out" | grep -q "61GB in the backup$"'
reset; printf '30|2|*|*|0|%s\n' $NOW >$T/state/schedule; out=$(runh); check "weekly schedule -> see crontab" "echo \"\$out\" | grep -q \"next run see root's crontab\""
reset; rm $T/last-run; out=$(runh); check "no last-run file: no crash, no Backup size line" '! echo "$out" | grep -q "  Backup size  "'
reset; S2=$(date -d '3 days ago' +%Y-%m-%dT%H:%M:%S.0Z -u); printf '/portainer running always 5 %s\n' $S2 >$T/fd/inspect; out=$(runh); check "old restart (3 days ago) not shown" '! echo "$out" | grep -q "  Restarts  "'
reset; printf '/dead exited always 0 2026-01-01T00:00:00Z\n/ok running always 0 2026-01-01T00:00:00Z\n' >$T/fd/inspect; out=$(runh); check "down container still reported" 'echo "$out" | grep -q "Containers .*not running: dead"'
reset; out=$(HOMELAB_TEMP_WARN=40 runh); check "temperature threshold can be changed" 'echo "$out" | grep -q "getting warm"'
out=$(runh secrets | head -3); check "secrets command still works" 'echo "$out" | grep -q "Secrets and rebuild essentials"'
out=$(runh help); check "help ok" 'echo "$out" | grep -q "homelab secrets"'
start=$(date +%s%N); runh >/dev/null; el=$(( ($(date +%s%N)-start)/1000000 )); check "fast (under 3 s here): ${el} ms" '[ $el -lt 3000 ]'

# ---------- the 1.5 screens: short login screen, full list on demand ----------
reset; out=$(runh); outc=$(runh commands)
check "login screen: header line" 'echo "$out" | head -3 | grep -q "Home lab  ·  .*  ·  up"'
check "login screen: summary line (problem, pool not mounted)" 'echo "$out" | grep -q "✗  1 problem needs you.  Details in Status below."'
check "login screen: Status section present" 'echo "$out" | grep -q "── Status ──" && echo "$out" | grep -q "Main pool"'
check "login screen: hint to type homelab commands, after the status" '[ "$(echo "$out" | grep -n "homelab commands" | cut -d: -f1)" -gt "$(echo "$out" | grep -n "Boot drive" | cut -d: -f1)" ] && echo "$out" | grep -q "Type homelab commands to see every command."'
check "login screen: the long command list is NOT shown" '! echo "$out" | grep -q "── Storage" && ! echo "$out" | grep -q "── Docker, everyday" && ! echo "$out" | grep -q "menu: connect"'
check "login screen is short (under 32 lines, with the suggestions)" '[ "$(echo "$out" | wc -l)" -lt 32 ]'
check "commands screen: header line, no status block" 'echo "$outc" | head -3 | grep -q "Home lab  ·  .*  ·  up" && ! echo "$outc" | grep -q "── Status ──" && ! echo "$outc" | grep -q "Main pool"'
check "commands screen: every section heading" 'for t in Storage Backup "Container updates" "Rebuild and safety" "Docker, everyday" "Network and system" "This screen and the guides"; do echo "$outc" | grep -q "── $t ──" || exit 1; done'
check "commands screen: container update commands" 'for c in "sudo homelab-update " "sudo homelab-update check" "homelab-update list" "sudo homelab-update clean"; do echo "$outc" | grep -q "$c" || exit 1; done'
check "commands screen: rebuild and safety commands" 'for c in "homelab secrets" "sudo homelab-restore-configs check" "homelab-check"; do echo "$outc" | grep -q "$c" || exit 1; done'
check "commands screen: docker commands" 'for c in "docker ps --format" "docker logs --tail 50 NAME" "docker restart NAME" "docker stats --no-stream"; do echo "$outc" | grep -q "$c" || exit 1; done'
check "commands screen: network and system commands" 'for c in "tailscale status" "findmnt /mnt/storage" "df -h /" "sudo apt update && sudo apt upgrade" "sudo reboot"; do echo "$outc" | grep -q "$c" || exit 1; done'
check "commands screen: storage and backup commands" 'for c in "sudo drives status" "sudo drives replace" "sudo hdd-recover" "sudo homelab-backup" "homelab docs"; do echo "$outc" | grep -q "$c" || exit 1; done'
check "commands screen lists the homelab commands themselves" 'for c in "homelab commands" "homelab status" "homelab secrets" "homelab docs"; do echo "$outc" | grep -q "$c" || exit 1; done && echo "$outc" | grep -Eq "^   homelab  +login screen"'
check "commands screen: backup line no longer says 20 minutes" '! echo "$outc" | grep -q "about 20 minutes"'
check "commands screen: points back to the status screen" 'echo "$outc" | grep -q "Type homelab to see the status."'
check "homelab command (singular) works too" '[ "$(runh command)" = "$outc" ]'
check "table: command and description on one line (wide window)" 'echo "$outc" | grep -Eq "sudo drives status +pools, drives, SMART health"'
check "at least 3 spaces between command and description" 'echo "$outc" | grep -Eq "sudo drives status {3,}pools"'
reset; export HOMELAB_MAIN_POOL=/ HOMELAB_BACKUP_POOL=/; printf '0|%s\n' $NOW >$T/state/apt; printf '/immich_server running always 0 %s\n' "$(date -d '3 days ago' +%Y-%m-%dT%H:%M:%S.0Z -u)" >$T/fd/inspect; out=$(runh)
check "all good -> 'Everything looks fine'" 'echo "$out" | grep -q "✓  Everything looks fine"'
printf '12|%s\n' $NOW >$T/state/apt; out=$(runh)
check "one warning -> '1 thing to look at' (singular)" 'echo "$out" | grep -q "!  1 thing to look at.  Details in Status below."'
printf '12|%s\n' $NOW >$T/state/apt; rm -f $T/last-run; out=$(runh)
check "two warnings -> '2 things to look at' (plural)" 'echo "$out" | grep -Eq "!  2 things to look at."'
export HOMELAB_MAIN_POOL=/nonexistent-pool; unset HOMELAB_BACKUP_POOL
reset; export HOMELAB_MAIN_POOL=/nonexistent-pool; printf '/dead exited always 0 2026-01-01T00:00:00Z\n/ok running always 0 2026-01-01T00:00:00Z\n' >$T/fd/inspect; out=$(runh)
check "two problems -> '2 problems need you' (plural)" 'echo "$out" | grep -q "✗  2 problems need you."'
reset; out=$(runh status)
check "homelab status prints only the status block" 'echo "$out" | grep -q "── Status ──" && echo "$out" | grep -q "Main pool" && ! echo "$out" | grep -q "── Storage" && ! echo "$out" | grep -q "menu: connect" && ! echo "$out" | grep -q "Home lab  ·"'
out=$(COLUMNS=60 runh commands)
check "narrow window: command, then its description on the next line" 'echo "$out" | grep -A1 "^   sudo drives status$" | tail -1 | grep -q "^       pools, drives, SMART health"'
check "narrow window: a whole section is stacked, not mixed" 'echo "$out" | grep -A1 "^   sudo drives$" | tail -1 | grep -q "^       menu:" && echo "$out" | grep -A1 "^   sudo drives power$" | tail -1 | grep -q "^       re-apply"'
check "rule lines never wider than the window (60)" '[ "$(echo "$out" | grep "── " | python3 -c "import sys;print(max(len(l.rstrip(chr(10))) for l in sys.stdin))")" -le 60 ]'
out=$(COLUMNS=60 runh)
check "narrow window: login rules also fit, hint still shown" '[ "$(echo "$out" | grep "── " | python3 -c "import sys;print(max(len(l.rstrip(chr(10))) for l in sys.stdin))")" -le 60 ] && echo "$out" | grep -q "homelab commands"'
out=$(LC_ALL=C runh); outc=$(LC_ALL=C runh commands)
check "plain symbols when the terminal is not UTF-8" '! echo "$out$outc" | grep -q "[✓✗·─]" && echo "$outc" | grep -q "  -- Storage --" && echo "$out" | grep -Eq "^   [+!x]  Main pool"'
col=$(env -u NO_COLOR TERM=xterm script -qec "bash $H" /dev/null </dev/null 2>&1 | cat -v)
check "colours on a terminal" 'echo "$col" | grep -qF "^[[1m" && echo "$col" | grep -qF "^[[33m"'
check "no colour codes when the output is captured" '! runh | grep -q $'"'"'\033'"'"''
out=$(runh help)
check "help lists homelab commands and status" 'echo "$out" | grep -q "homelab commands" && echo "$out" | grep -q "homelab status"'
out=$(runh nonsense); check "unknown option names the options" 'echo "$out" | grep -q "homelab, homelab commands, homelab status, homelab docs, homelab secrets"'
reset; mkdir -p $T/docs; printf '# T\n## 1. Intro\ntext\n## 2. More\n' >$T/docs/README.md; mkdir -p $T/docs/docs; printf '## A. Fix\n' >$T/docs/docs/troubleshooting.md
out=$(HOMELAB_DOCS_DIR=$T/docs runh docs)
check "homelab docs: headings per file, numbered sections" 'echo "$out" | grep -q "── README.md ──" && echo "$out" | grep -q "── docs/troubleshooting.md ──" && echo "$out" | grep -Eq "^   2[[:space:]]+1. Intro" && echo "$out" | grep -q "less +LINE"'
out=$(HOMELAB_DOCS_DIR=$T/nodocs runh docs); check "homelab docs: missing folder gives clone hint" 'echo "$out" | grep -q "git clone"'
out=$(runh secrets | head -12)
check "secrets screen: spaced heading, checklist" 'echo "$out" | grep -q "── Secrets and rebuild essentials ──" && echo "$out" | grep -q "Values are never shown" && echo "$out" | grep -q "\[ \] Linux user login"'
check "login screen needs no sudo and no docs folder" 'HOMELAB_DOCS_DIR=/nonexistent runh | grep -q "Type homelab commands"'
echo; echo "PASS=$PASS FAIL=$FAIL"
# ---- setup progress line (new in 1.6)
reset; out=$(runh); check "no progress file -> no setup line" '! echo "$out" | grep -q "Setup:"'
reset; printf '9|23|%s\n' $NOW >$T/state/setup-progress; out=$(runh); check "progress file -> one-line setup progress" 'echo "$out" | grep -q "Setup: 9 of 23 steps done.  Run  sudo homelab-setup  to see what is left."'
reset; printf '23|23|%s\n' $NOW >$T/state/setup-progress; out=$(runh); check "complete -> line hidden" '! echo "$out" | grep -q "Setup:"'
reset; printf 'junk\n' >$T/state/setup-progress; out=$(runh); check "garbage file -> hidden, no error" '! echo "$out" | grep -q "Setup:" && ! echo "$out" | grep -qi "error\|syntax"'
reset; printf '9|23|%s\n' $NOW >$T/state/setup-progress; out=$(runh status); check "status screen does not carry the setup line" '! echo "$out" | grep -q "Setup:"'
reset; printf '#!/bin/bash\n' >$T/bin/homelab-setup; chmod +x $T/bin/homelab-setup; out=$(runh commands); check "commands list shows homelab-setup when installed" 'echo "$out" | grep -q "sudo homelab-setup"'
reset; out=$(runh commands); check "commands list hides it when not installed" '! echo "$out" | grep -q "homelab-setup"'
# ---- no data drive set up (new in 1.7)
reset; out=$(runh status); check "pool missing, no marker -> red NOT MOUNTED (real failures stay loud)" 'echo "$out" | grep -q "NOT MOUNTED"'
reset; printf 'no data drive set up\n' >$T/state/no-data-drive; out=$(runh status); check "pool missing + marker -> grey note, no NOT MOUNTED" '! echo "$out" | grep -q "NOT MOUNTED" && echo "$out" | grep -q "no data drive set up yet"'
reset; printf 'no data drive set up\n' >$T/state/no-data-drive; out=$(runh); check "login screen with marker is not red because of the pool" '! echo "$out" | grep -q "problem needs you" '
# ---- Suggested Commands (new in 1.9)
reset; out=$(runh)
check "Suggested Commands block is on the login screen" 'echo "$out" | grep -q "── Suggested Commands ──"'
check "Suggested Commands sits above the hint line and below Status" '[ "$(echo "$out" | grep -n "── Status ──" | cut -d: -f1)" -lt "$(echo "$out" | grep -n "── Suggested Commands ──" | cut -d: -f1)" ] && [ "$(echo "$out" | grep -n "── Suggested Commands ──" | cut -d: -f1)" -lt "$(echo "$out" | grep -n "Type homelab commands" | cut -d: -f1)" ]'
check "at most four suggestions" '[ "$(echo "$out" | sed -n "/── Suggested Commands ──/,/Type homelab commands/p" | grep -c "^   [a-z]")" -le 4 ]'
check "pending system updates suggest apt" 'echo "$out" | sed -n "/── Suggested Commands ──/,$ p" | grep -q "sudo apt update"'
reset; printf 'no data drive set up\n' >$T/state/no-data-drive; printf '9|23|%s\n' $NOW >$T/state/setup-progress; out=$(runh)
check "open setup steps suggest refresh first" 'echo "$out" | sed -n "/── Suggested Commands ──/,$ p" | grep -m1 "^   " | grep -q "sudo homelab-setup refresh"'
check "the refresh suggestion says how many steps are left" 'echo "$out" | grep -q "sudo homelab-setup refresh .*14 steps left"'
reset; printf 'no data drive set up\n' >$T/state/no-data-drive; out=$(runh)
check "no data drive suggests sudo drives" 'echo "$out" | sed -n "/── Suggested Commands ──/,$ p" | grep -q "^   sudo drives  "'
reset; printf 'no data drive set up\n' >$T/state/no-data-drive; printf '%s|OK|/bk|55|1\n' "$(date -d '3 days ago' '+%F %H:%M')" >$T/last-run; out=$(runh)
check "an old backup suggests running one" 'echo "$out" | sed -n "/── Suggested Commands ──/,$ p" | grep -q "sudo homelab-backup"'
reset; printf 'no data drive set up\n' >$T/state/no-data-drive; printf '/dead exited always 0 2026-01-01T00:00:00Z\n' >$T/fd/inspect; out=$(runh)
check "a stopped container is the first suggestion" 'echo "$out" | sed -n "/── Suggested Commands ──/,$ p" | grep -m1 "^   " | grep -q "docker ps -a"'
reset; printf 'no data drive set up\n' >$T/state/no-data-drive; printf '0|%s\n' $NOW >$T/state/apt; printf '%s\n' $NOW >$T/state/image-updates; out=$(runh)
check "when all is fine, everyday commands fill the list" 'echo "$out" | sed -n "/── Suggested Commands ──/,$ p" | grep -q "homelab commands"'
reset; out=$(HOMELAB_SUGGEST_MAX=2 runh)
check "the number of suggestions can be changed" '[ "$(echo "$out" | sed -n "/── Suggested Commands ──/,/Type homelab commands/p" | grep -c "^   [a-z]")" -le 2 ]'
reset; out=$(runh status)
check "the status screen has no suggestions" '! echo "$out" | grep -q "Suggested Commands"'
reset; printf '#!/bin/bash\n' >$T/bin/homelab-setup; chmod +x $T/bin/homelab-setup; out=$(runh commands)
check "commands list: refresh, details and verify when homelab-setup is installed" 'echo "$out" | grep -q "sudo homelab-setup refresh" && echo "$out" | grep -q "sudo homelab-setup --details" && echo "$out" | grep -q "sudo homelab-setup verify" && echo "$out" | grep -q "sudo homelab-setup done STEP"'
out=$(COLUMNS=60 runh)
check "narrow window: suggestions still fit" '[ "$(echo "$out" | grep "── " | python3 -c "import sys;print(max(len(l.rstrip(chr(10))) for l in sys.stdin))")" -le 60 ]'
reset; printf 'no data drive set up\n' >$T/state/no-data-drive; printf '0|%s\n' $NOW >$T/state/apt; printf '%s\n' $NOW >$T/state/image-updates; mkdir -p $T/hp; out=$(HOMELAB_HOMEPAGE_DIR=$T/hp runh)
check "with a Homepage folder, theme and bookmark are suggested when little else is" 'echo "$out" | sed -n "/── Suggested Commands ──/,$ p" | grep -q "homelab theme" && echo "$out" | grep -q "homelab bookmark add NAME URL"'
reset; out=$(HOMELAB_HOMEPAGE_DIR=$T/none runh)
check "without a Homepage folder they are not suggested" '! echo "$out" | grep -q "homelab bookmark add"'
reset; out=$(runh commands); check "the commands list has the Homepage dashboard group" 'echo "$out" | grep -q "── Homepage dashboard" && echo "$out" | grep -q "homelab bookmark add NAME URL" && echo "$out" | grep -q "homelab theme background URL"'
echo "TOTAL pass=$PASS fail=$FAIL"
