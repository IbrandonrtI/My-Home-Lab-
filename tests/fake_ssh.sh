#!/bin/bash
# Stand-in for ssh in tests: runs the remote command on this machine (so rsync -e and the engine's remote helpers work without a server).
# Skips ssh's options (-i X, -o X, -p X) and the user@host word, then runs the rest the way a remote shell would.
while [ $# -gt 0 ]; do
  case "$1" in
    -i|-o|-p|-l) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
shift
printf '%s\n' "$*" >> "${FAKE_SSH_LOG:-/dev/null}"
exec sh -c "$*"
