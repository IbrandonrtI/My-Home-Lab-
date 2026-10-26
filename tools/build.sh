#!/usr/bin/env bash
# build.sh - join the pieces in src/ into the single installer file installer/homelab-setup.
#
#   bash tools/build.sh          build the installer (and check that it compiles)
#   bash tools/build.sh --check  build into a temporary file and compare it with installer/homelab-setup
#                                (exit 1 if they differ: someone edited one side only)
#
# The installer is one Python 3 file with no dependencies, so it can be copied to a fresh machine on its own.
# The pieces are joined in file-name order (p01 ... p09); edit the pieces in src/, never the built file.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT=installer/homelab-setup
if [ "${1:-}" = "--check" ]; then
  TMP="$(mktemp)"
  trap 'rm -f "$TMP"' EXIT
  cat src/p0*.py > "$TMP"
  if cmp -s "$TMP" "$OUT"; then
    echo "installer/homelab-setup matches src/"
    exit 0
  fi
  echo "installer/homelab-setup does NOT match src/. Run: bash tools/build.sh" >&2
  exit 1
fi

cat src/p0*.py > "$OUT"
chmod +x "$OUT"
python3 -m py_compile "$OUT"
rm -rf installer/__pycache__
echo "built $OUT: $(wc -l < "$OUT") lines"
