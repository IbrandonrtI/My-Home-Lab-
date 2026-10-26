#!/usr/bin/env bash
# setup.sh - starts the home lab installer from a fresh clone of this repository.
#
#   git clone https://github.com/IbrandonrtI/My-Home-Lab-.git
#   cd My-Home-Lab-
#   sudo bash setup.sh install --dry-run     # show what would be done, change nothing
#   sudo bash setup.sh install               # set everything up (asks first)
#   sudo bash setup.sh                       # show the checklist
#   bash setup.sh --help                     # this text, then the installer's own commands
#
# This script only checks that Python 3 is installed (on a machine with apt) and then runs
# installer/homelab-setup with the same arguments. Run it with `bash`: files uploaded through
# GitHub's web page do not keep their "executable" mark.
set -euo pipefail

SELF="${BASH_SOURCE[0]:-}"
if [ -z "$SELF" ] || [ ! -f "$SELF" ]; then
  echo "setup.sh: run it from a clone of the repository (git clone ... && cd My-Home-Lab- && sudo bash setup.sh)," >&2
  echo "          not through a pipe or process substitution." >&2
  exit 1
fi
HERE="$(cd "$(dirname "$SELF")" && pwd)"
PROG="$HERE/installer/homelab-setup"

case "${1:-}" in
  -h | --help | help)
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$SELF"
    echo
    if [ -f "$PROG" ] && command -v python3 >/dev/null 2>&1; then
      python3 "$PROG" help
    fi
    exit 0
    ;;
esac

if [ ! -f "$PROG" ]; then
  echo "setup.sh: $PROG not found. Run this script from the root of the cloned repository." >&2
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  if ! command -v sudo >/dev/null 2>&1; then
    echo "setup.sh: this needs root. Run it as root, or install sudo." >&2
    exit 1
  fi
  exec sudo -E bash "$SELF" "$@"
fi

if ! command -v python3 >/dev/null 2>&1; then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "setup.sh: Python 3 is missing and this machine has no apt-get. The installer supports Linux Mint and Ubuntu." >&2
    exit 1
  fi
  echo "setup.sh: Python 3 is not installed. Installing it first ..."
  DEBIAN_FRONTEND=noninteractive apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3
fi

exec python3 "$PROG" "$@"
