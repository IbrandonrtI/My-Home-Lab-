#!/bin/bash
# setup.sh - start the home lab installer from a fresh clone of the repo.
#
#   git clone https://github.com/your-username/My-Home-Lab-.git
#   cd My-Home-Lab-
#   sudo bash setup.sh install --dry-run     # show what it would do, change nothing
#   sudo bash setup.sh install               # do it (asks first)
#   sudo bash setup.sh                       # show the checklist
#
# All it does is check that Python 3 is there and hand over to homelab-setup/homelab-setup.
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROG="$HERE/homelab-setup/homelab-setup"
if [ ! -f "$PROG" ]; then
  echo "I cannot find $PROG - run this from the folder you cloned from GitHub." >&2
  exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
  exec sudo -E bash "$0" "$@"
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is missing. Installing it first ..."
  apt-get update -y && apt-get install -y python3
fi
exec python3 "$PROG" "$@"
