#!/bin/bash
# setup.sh - starts the home lab installer from a fresh clone of the repository.
#
#   git clone https://github.com/your-username/My-Home-Lab-.git
#   cd My-Home-Lab-
#   sudo bash setup.sh install --dry-run     # show what would be done, change nothing
#   sudo bash setup.sh install               # set everything up (asks first)
#   sudo bash setup.sh                       # show the checklist
#
# This script only checks that Python 3 is installed and then runs homelab-setup/homelab-setup.
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROG="$HERE/homelab-setup/homelab-setup"
if [ ! -f "$PROG" ]; then
  echo "setup.sh: $PROG not found. Run this script from the root of the cloned repository." >&2
  exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "setup.sh: Python 3 is not installed. Installing it first ..."
  apt-get update -y && apt-get install -y python3
fi
exec python3 "$PROG" "$@"
