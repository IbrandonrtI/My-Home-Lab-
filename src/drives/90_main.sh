run_changing() {
  local rc=0
  "$@" || rc=$?
  if [ "$1" = wizard_flow ] && [ "$PRESET_TOUCHED" != 1 ]; then return "$rc"; fi
  if [ "$rc" -ne 0 ] && [ "$PRESET_TOUCHED" != 1 ]; then case "$1" in preset_flow|spare_flow|cache_flow) return "$rc" ;; esac; fi
  [ -n "${STOPPED// /}" ] || sync_filebrowser
  if [ -n "${START_FAILED// /}" ] && [ "$rc" -eq 0 ]; then rc=1; fi
  return "$rc"
}

take_lock() {
  mkdir -p "$(dirname "$LOGFILE")" 2>/dev/null || true
  { exec 9>"/var/lock/homelab-drives.lock"; } 2>/dev/null || exec 9>"/tmp/homelab-drives.lock"
  flock -n 9 || die "Another drives command is running."
}

# Read the command line and run the requested command.
main() {
  if [ "${1:-}" = panel ]; then shift; panel_main "$@"; return $?; fi
  local -a args=()
  local a WANT_HELP=0
  while [ $# -gt 0 ]; do
    a=$1; shift
    case "$a" in
      --dry-run|-n)  DRY_RUN=1 ;;
      --yes|-y)      ASSUME_YES=1 ;;
      --confirm-erase) CONFIRM_ERASE=1 ;;
      --now)         NOW=1 ;;
      --spare)       WANT_SPARE=1 ;;
      --cache)       WANT_CACHE=1 ;;
      --encrypt)     WANT_ENCRYPT=1 ;;
      --first-run)   WANT_FIRST=1 ;;
      --json)        JSON=1 ;;
      --full)        FULL=1 ;;
      --folders)     FOLDERS=1 ;;
      -h|--help)     WANT_HELP=1 ;;
      --version)     args+=("version") ;;
      -*)            note "Unknown option: $a"; note ""; usage_text >&2; exit 1 ;;
      test-setup|test-cleanup) args+=("$a" "$@"); break ;;
      *)             args+=("$a") ;;
    esac
  done
  set -- ${args[@]+"${args[@]}"}
  case "${1:-}" in
    name) set -- rename "${@:2}" ;;                    smart) set -- health "${@:2}" ;;
    spindown|standby) set -- sleep "${@:2}" ;;         fsck|verify) set -- check "${@:2}" ;;
    add) set -- connect "${@:2}" ;;                    remove) set -- disconnect "${@:2}" ;;
    df) set -- usage "${@:2}" ;;                       erase|format) set -- wipe "${@:2}" ;;
    presets|setups) set -- preset "${@:2}" ;;
    firstrun|first-run|scan-drives) set -- wizard "${@:2}" ;;
    help) case "${2:-}" in
            name) set -- help rename "${@:3}" ;;       smart) set -- help health "${@:3}" ;;
            spindown|standby) set -- help sleep "${@:3}" ;;   fsck|verify) set -- help check "${@:3}" ;;
            add) set -- help connect "${@:3}" ;;       remove) set -- help disconnect "${@:3}" ;;
            df) set -- help usage "${@:3}" ;;          erase|format) set -- help wipe "${@:3}" ;;
            presets|setups) set -- help preset "${@:3}" ;;
          esac ;;
  esac
  if [ "$WANT_HELP" = 1 ]; then set -- help "$@"; fi
  [ "${1:-}" = help ] && { [ "$#" -le 2 ] || { note "help takes one command name, for example:  sudo drives help release"; exit 1; }; help_for "${2:-}"; exit $?; }
  local cmd=${1:-menu}
  if [ "$JSON" = 1 ]; then case "$cmd" in status|list|usage|health|check) ;; *) note "--json works with: status, list, usage, health, check (not with '$cmd')."; exit 1 ;; esac; fi
  if [ "$FULL" = 1 ] && [ "$cmd" != check ]; then note "--full works with: check (not with '$cmd')."; exit 1; fi
  if { [ "$WANT_SPARE" = 1 ] || [ "$WANT_CACHE" = 1 ] || [ "$WANT_ENCRYPT" = 1 ]; } && [ "$cmd" != preset ]; then note "--spare, --cache and --encrypt work with: preset (not with '$cmd')."; exit 1; fi
  if [ "$WANT_FIRST" = 1 ] && [ "$cmd" != wizard ]; then note "--first-run works with: wizard (not with '$cmd')."; exit 1; fi
  if [ "$FOLDERS" = 1 ] && [ "$cmd" != usage ]; then note "--folders works with: usage (not with '$cmd')."; exit 1; fi
  case "${1:-}" in
    test-setup|test-cleanup) ;;
    preset|snapraid) if [ $# -gt 2 ]; then note "Unexpected word: ${*:3}"; note "Nothing was done."; note ""; usage_text >&2; exit 1; fi ;;
    *) if [ $# -gt 1 ]; then note "Unexpected word: ${*:2}"; note "Nothing was done."; note ""; usage_text >&2; exit 1; fi ;;
  esac
  [ "$(id -u)" = 0 ] || die "Run this with sudo:  sudo drives"
  take_lock
  case "${1:-menu}" in
    menu)         menu ;;
    status)       if [ "$JSON" = 1 ]; then with_name_cache json_drives; printf ',"last_backup":%s,"boot_free_bytes":%s}\n' "$(json_str "$(last_backup_line)")" "$(json_num "$(boot_free_bytes)")"; else with_name_cache status_flow; fi ;;
    list)         with_name_cache list_flow ;;
    usage)        with_name_cache usage_flow ;;
    health)       with_name_cache health_flow ;;
    check)        check_flow ;;
    connect)      run_changing connect_flow ;;
    disconnect)   run_changing disconnect_flow ;;
    move)         run_changing move_flow ;;
    adopt)        run_changing adopt_flow ;;
    power)        power_all ;;
    remount)      run_changing remount_flow ;;
    moveboot)     run_changing moveboot_flow ;;
    guard)        guard_flow ;;
    replace)      run_changing replace_flow ;;
    fillorder|reorder|priority) fillorder_flow ;;
    balance|rebalance) run_changing balance_flow ;;
    limit)        limit_flow ;;
    resize)       run_changing resize_flow ;;
    preset)       if [ -n "${2:-}" ]; then run_changing preset_flow "$2"; else preset_list_flow; fi ;;
    snapraid)     snapraid_flow "${2:-status}" ;;
    wizard)       run_changing wizard_flow ;;
    spare)        run_changing spare_flow ;;
    cache)        run_changing cache_flow ;;
    release)      run_changing release_flow ;;
    bootsection)  run_changing bootsection_flow ;;
    timeshift)    timeshift_flow ;;
    restore)      run_changing restore_flow ;;
    rename)       run_changing rename_flow ;;
    sleep)        sleep_flow ;;
    wake)         wake_flow ;;
    eject)        eject_flow ;;
    wipe)         wipe_flow ;;
    test-setup)   shift; test_setup "$@" ;;
    test-cleanup) test_cleanup ;;
    version)      echo "drives $VERSION" ;;
    recover) note "'recover' is now called:  sudo drives remount"; exit 1 ;;
    *) note "Unknown command: $1"; note ""; usage_text >&2; exit 1 ;;
  esac
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
