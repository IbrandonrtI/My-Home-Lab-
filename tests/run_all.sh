#!/usr/bin/env bash
# Runs every test in this folder and prints one summary line. Nothing on this machine is changed:
# the installer tests use a fake machine, the login-screen tests use fake state files.
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
run pinned-bar bash -c "python3 '$HERE/t_pinned.py' | tail -1 | grep -q '^OK'"
run secret-scan bash -c "python3 '$HERE/t_check.py' | tail -1 | grep -q '^OK'"
bash "$HERE/run_login_tests.sh" >"$LOG/login.log" 2>&1; count login
if [ "${1:-}" = quick ]; then
  for s in S3 S24 S25; do bash "$HERE/run_tests.sh" "$s" >"$LOG/$s.log" 2>&1; count "$s"; done
else
  bash "$HERE/run_tests.sh" >"$LOG/installer.log" 2>&1; count installer
fi
[ "$bad" -eq 0 ] && echo "all tests passed" || { echo "$bad test group(s) failed"; exit 1; }
