# ---- homelab theme / homelab bookmark: edit the Homepage files in your own home folder (never needs sudo) ----
HOMEPAGE_DIR="${HOMELAB_HOMEPAGE_DIR:-$HOME/homepage-config}"
calendar_cmd() {   # homelab event add|list|remove|holidays: the holidays and your own events in the dashboard calendar
  if ! command -v homelab-calendar >/dev/null 2>&1; then
    echo "homelab-calendar is not installed yet. Run:  homelab upgrade" >&2
    return 1
  fi
  HP_DIR="$HOMEPAGE_DIR" homelab-calendar "$@"
}

panel_cmd() {   # homelab panel password|status: the password of the control panel (the Customize tab), saved in your own folder
  if ! command -v homelab-panel >/dev/null 2>&1; then
    echo "The control panel is not installed yet. Run:  homelab upgrade" >&2
    return 1
  fi
  if [ "$(id -u)" -eq 0 ] && [ -z "${HOMELAB_ALLOW_ROOT:-}" ]; then
    echo "Run this without sudo, as yourself: the password is saved in your own folder." >&2
    return 1
  fi
  case "${1:-}" in
    password|passwd) homelab-panel set-password ;;
    status|"")       homelab-panel status ;;
    *) echo "Use:  homelab panel password   (choose the password)   or   homelab panel status" >&2; return 1 ;;
  esac
}

homepage_edit() {
  if [ "$(id -u)" -eq 0 ] && [ -z "${HOMELAB_ALLOW_ROOT:-}" ]; then
    echo "Run this without sudo, as the user who owns $HOMEPAGE_DIR (sudo would make the files belong to root)." >&2
    return 1
  fi
  command -v python3 >/dev/null 2>&1 || { echo "python3 is needed for this command (sudo apt install python3)." >&2; return 1; }
  HP_DIR="$HOMEPAGE_DIR" HP_DOCS_DIR="$DOCS_DIR" python3 - "$@" <<'PY'
@@include homepage_edit.py@@
PY
}

