#!/usr/bin/env bash
# build.sh - join the pieces in src/ into the files that are installed on the server (see tools/build.py).
#
#   bash tools/build.sh          build every file (and check that it compiles)
#   bash tools/build.sh --check  compare with the files in the repository (exit 1 if they differ)
set -euo pipefail
exec python3 "$(dirname "${BASH_SOURCE[0]}")/build.py" "$@"
