#!/usr/bin/env bash
# Runs every test in this folder and prints one summary line. Nothing on this machine is changed:
# the installer tests use a fake machine.
#
#   bash tests/run_all.sh           # everything (about 10 minutes)
#   bash tests/run_all.sh quick     # skips the long install scenarios (about 1 minute)
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="${TMPDIR:-/tmp}/homelab-tests"
mkdir -p "$LOG"
bad=0

run() {   # run <name> <command...>
  name="$1"; shift
  if "$@" >"$LOG/$name.log" 2>&1; then
    printf 'ok    %s\n' "$name"
  else
    printf 'FAIL  %s   (see %s/%s.log)\n' "$name" "$LOG" "$name"; bad=$((bad + 1))
  fi
}
count() {  # count <name> : fail if the log ends with a non-zero fail count
  grep -q 'fail=0$' "$LOG/$1.log" || { printf 'FAIL  %s   (see %s/%s.log)\n' "$1" "$LOG" "$1"; bad=$((bad + 1)); return 1; }
  printf 'ok    %s   (%s)\n' "$1" "$(grep -o 'pass=[0-9]*' "$LOG/$1.log" | tail -1)"
}

run substitution bash -c "python3 '$HERE/t_subst.py' | tail -1 | grep -q '^OK'"
run homepage-cmds bash -c "bash '$HERE/t_homepage.sh' | tail -1 | grep -q '^OK'"
run drive-names bash -c "python3 '$HERE/t_names.py' | tail -1 | grep -q '^OK'"
run home-volumes bash -c "python3 '$HERE/t_homevol.py' | tail -1 | grep -q '^OK'"
run homepage-tabs bash -c "python3 '$HERE/t_tabs.py' | tail -1 | grep -q '^OK'"
run music-player bash -c "python3 '$HERE/t_player.py' | tail -1 | grep -q '^OK'"
run dashboard-extras bash -c "python3 '$HERE/t_extras.py' | tail -1 | grep -q '^OK'"
run stats-tab bash -c "python3 '$HERE/t_stats.py' | tail -1 | grep -q '^OK'"
run panel-server bash -c "python3 '$HERE/t_panel.py' | tail -1 | grep -q '^OK'"
run panel-ui bash -c "python3 '$HERE/t_panel_ui.py' | tail -1 | grep -q '^OK'"
run drives-tab-server bash -c "python3 '$HERE/t_drives_tab.py' | tail -1 | grep -q '^OK'"
run drives-tab-ui bash -c "python3 '$HERE/t_drives_ui.py' | tail -1 | grep -q '^OK'"
run screen-zoom bash -c "python3 '$HERE/t_zoom.py' | tail -1 | grep -q '^OK'"
run folders-message bash -c "python3 '$HERE/t_folders.py' | tail -1 | grep -q '^OK'"
run calendar bash -c "python3 '$HERE/t_calendar.py' | tail -1 | grep -q '^OK'"
run drive-script-names bash -c "bash '$HERE/t_drivenames.sh' | tail -1 | grep -q '^OK'"
run boot-sections bash -c "bash '$HERE/t_bootsection.sh' | tail -1 | grep -q '^OK'"
run timeshift-exclusion bash -c "bash '$HERE/t_timeshift.sh' | tail -1 | grep -q '^OK'"
run presets bash -c "bash '$HERE/t_preset.sh' | tail -1 | grep -q '^OK'"
run wizard-keep bash -c "bash '$HERE/t_wizard_keep.sh' | tail -1 | grep -q '^OK'"
run drive-power bash -c "bash '$HERE/t_power.sh' | tail -1 | grep -q '^OK'"
run drive-panel-door bash -c "bash '$HERE/t_drivepanel.sh' | tail -1 | grep -q '^OK'"
run drive-panel-stage4 bash -c "bash '$HERE/t_drivepanel4.sh' | tail -1 | grep -q '^OK'"
run mount-scope bash -c "bash '$HERE/t_mountscope.sh' | tail -1 | grep -q '^OK'"
run drive-batch bash -c "bash '$HERE/t_drivebatch.sh' | tail -1 | grep -q '^OK'"
run docker-together bash -c "bash '$HERE/t_dockereach.sh' | tail -1 | grep -q '^OK'"
run drive-pills bash -c "bash '$HERE/t_widgets.sh' | tail -1 | grep -q '^OK'"
run update-command bash -c "bash '$HERE/t_update.sh' | tail -1 | grep -q '^OK'"
run secret-scan bash -c "python3 '$HERE/t_check.py' | tail -1 | grep -q '^OK'"
run wizard-offer bash -c "python3 '$HERE/t_wizard_offer.py' | tail -1 | grep -q '^OK'"
run login-hook bash -c "python3 '$HERE/t_loginhook.py' | tail -1 | grep -q '^OK'"
run service-cards bash -c "python3 '$HERE/t_cards.py' | tail -1 | grep -q '^OK'"
run friendly-commands bash -c "bash '$HERE/t_friendly.sh' | tail -1 | grep -q '^OK'"
run name-helpers bash -c "bash '$HERE/t_namefast.sh' | tail -1 | grep -q '^OK'"
run speedcheck bash -c "python3 '$HERE/t_speedcheck.py' | tail -1 | grep -q '^OK'"
run drive-bench bash -c "python3 '$HERE/t_bench.py' | tail -1 | grep -q '^OK'"
if [ "${1:-}" = quick ]; then
  for s in S3 S24 S25; do bash "$HERE/run_tests.sh" "$s" >"$LOG/$s.log" 2>&1; count "$s"; done
else
  bash "$HERE/run_tests.sh" >"$LOG/installer.log" 2>&1; count installer
fi
[ "$bad" -eq 0 ] && echo "all tests passed" || { echo "$bad test group(s) failed"; exit 1; }
