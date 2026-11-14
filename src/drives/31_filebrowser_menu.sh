sync_filebrowser() {
  [ "$TEST_MODE" = 1 ] && return 0
  [ "$DRY_RUN" = 1 ] && return 0
  [ "${DRIVES_SKIP_SYNC:-}" = 1 ] && return 0
  command -v homelab-sample >/dev/null 2>&1 && { homelab-sample widgets 9>&- >/dev/null 2>&1 || true; }
  if command -v homelab-stats >/dev/null 2>&1; then
    { homelab-sample 9>&-; homelab-stats 9>&-; } >/dev/null 2>&1 </dev/null &
    disown 2>/dev/null || true
  fi
  command -v homelab-setup >/dev/null 2>&1 || return 0
  homelab-setup homepage 9>&- || note "Homepage was not updated. Later, run:  sudo homelab-setup homepage"
  homelab-setup filebrowser 9>&- || note "FileBrowser's drive folders were not updated. Later, run:  sudo homelab-setup filebrowser"
}

ask_choice() { ask "Type a number and press Enter: "; }

intro() {
  local t=$1 l; shift
  say ""
  say "You chose: $t"
  for l in "$@"; do say "  $l"; done
  say ""
}
intro_ask() {
  intro "$@"
  yn "Do you want to continue?" || { say "Nothing was changed."; return 1; }
}

drives_menu() {
  local c
  while :; do
    say ""
    say "Add or remove drives"
    say "  1) Connect a new drive"
    say "  2) Disconnect a drive"
    say "  3) Move a drive between main and backup"
    say "  4) Use part of the boot drive for a pool (with a size limit)"
    say "  5) Take all drives out of the pools (the files stay on the drives)"
    say "  6) Build a ready-made setup on empty drives (pool, mirror, SnapRAID)"
    say "  0) Back"
    c=$(ask_choice)
    case "$c" in
      1) intro_ask "Connect a new drive" \
           "Next, the connected drives that are not in use are listed. Choose one," \
           "then choose whether it is for the Main pool or the Backup pool." \
           "If the drive has files on it, they can be kept. Nothing is erased unless ERASE is typed." &&
         { connect_flow && sync_filebrowser; } ;;
      2) intro_ask "Disconnect a drive" \
           "Next, the drives in the pools are listed. Choose one." \
           "If it holds files, you are asked whether to copy them to another drive first." \
           "The files on the drive are not erased." &&
         { disconnect_flow && sync_filebrowser; } ;;
      3) intro_ask "Move a drive between main and backup" \
           "Next, choose a drive. Its files are first copied to the other drives of its storage," \
           "then the drive is erased and formatted for the other storage." &&
         { move_flow && sync_filebrowser; } ;;
      4) intro "Use part of the boot drive for a pool" \
           "Next, choose the Main or Backup pool, read the warning and choose the size." \
           "You are asked to confirm before anything is created. Press Enter to cancel at any time." &&
         { bootsection_flow && sync_filebrowser; } ;;
      5) intro "Take all drives out of the pools" \
           "Next, the drives are listed and you are asked to confirm before anything is released." \
           "The files on the drives are not erased." &&
         { release_flow && sync_filebrowser; } ;;
      6) intro "Build a ready-made setup" \
           "Next, the available setups (a plain pool, a mirror with a nightly copy, SnapRAID parity) are shown with what the empty drives would provide." \
           "Choose a setup and the empty drives. The drives are formatted, and you are asked twice before anything is erased." &&
         { preset_menu && sync_filebrowser; } ;;
      0|"") return 0 ;;
      *) say "Enter a number from the list." ;;
    esac
  done
}

problem_menu() {
  local c
  while :; do
    say ""
    say "Fix a problem"
    say "  1) Repair the drives after a disconnection, a power loss or a missing drive"
    say "  2) Replace a failed drive (restores the missing files from the backup)"
    say "  3) Restore only the missing files from the backup"
    say "  4) Copy files saved on the boot drive to the Main pool"
    say "  0) Back"
    c=$(ask_choice)
    case "$c" in
      1) intro_ask "Repair the drives after a disconnection, a power loss or a missing drive" \
           "The services that use the storage are stopped, the drives are mounted again and the services start again." \
           "Then Immich and Nextcloud are checked. If their files are missing, they can be copied back from the backup." \
           "No files are changed without confirmation. It takes about a minute." &&
         { remount_flow && sync_filebrowser; } ;;
      2) intro "Replace a failed drive" \
           "Next, the pool drives that cannot be found are listed. Choose the failed drive." \
           "Then choose the new drive. The missing files are copied back from the backup." \
           "You are asked to confirm before anything is erased." &&
         { replace_flow && sync_filebrowser; } ;;
      3) intro "Restore only the missing files from the backup" \
           "Next, the backup copy is located and its contents are shown." \
           "Only files that are missing in the Main pool are copied back. Nothing is overwritten." &&
         { restore_flow && sync_filebrowser; } ;;
      4) intro "Copy files saved on the boot drive to the Main pool" \
           "While the Main pool had no drive, the services saved their files on the boot drive." \
           "They are copied to the pool and checked. You are asked before the old copies are removed." &&
         { moveboot_flow && sync_filebrowser; } ;;
      0|"") return 0 ;;
      *) say "Enter a number from the list." ;;
    esac
  done
}

settings_menu() {
  local c
  while :; do
    say ""
    say "Settings and upgrades"
    say "  1) Apply the drive power settings"
    say "  2) Fill order: one drive at a time or spread, and which drive goes first"
    say "  3) Convert the current single data drive into the main pool (one time, older setups)"
    say "  4) Even out the used space between the drives of a storage (balance)"
    say "  5) Set how much free space a drive keeps"
    say "  6) Make a boot drive section bigger or smaller"
    say "  0) Back"
    c=$(ask_choice)
    case "$c" in
      1) intro_ask "Apply the drive power settings" \
           "Main drives never sleep. Backup drives sleep after 10 minutes without use." \
           "No files are touched." &&
         power_all ;;
      2) intro "Fill order" \
           "Next you pick a storage and see how it picks a drive for a new file. A pool uses its first drive until only" \
           "${POOL_FREE_PERCENT}% of it is free, then the next one, or it can spread by free space. No files are moved." &&
         fillorder_flow ;;
      3) intro "Convert the current single data drive into the main pool" \
           "Only for older setups where one drive is mounted directly as the main pool." \
           "Next, the changes are shown and you are asked to confirm before anything is done." &&
         { adopt_flow && sync_filebrowser; } ;;
      4) intro "Even out the used space (balance)" \
           "Next, choose a storage. A plan shows which files move from the fullest drive to the emptiest." \
           "Files are copied and checked before they are removed. You are asked to confirm before anything moves." &&
         { balance_flow && sync_filebrowser; } ;;
      5) intro "Free space a drive keeps" \
           "Next, choose a drive and enter how much free space it keeps (for example 50GB or 8%)." \
           "No files are moved." &&
         limit_flow ;;
      6) intro "Make a boot drive section bigger or smaller" \
           "Next, choose a section and its new size. The containers of that pool stop during the change." \
           "You are asked to confirm before anything changes." &&
         { resize_flow && sync_filebrowser; } ;;
      0|"") return 0 ;;
      *) say "Enter a number from the list." ;;
    esac
  done
}

menu() {
  local c
  while :; do
    say ""
    [ "$TEST_MODE" = 1 ] && say "Test mode: test folders and a test fstab are used. The real pools are not changed."
    say "Home lab drives"
    say "  1) Look at the drives (status, list, space, health, checks)"
    say "  2) Add or remove drives"
    say "  3) Fix a problem"
    say "  4) Settings and upgrades"
    say "  5) Actions on one drive (rename, sleep, wake, safe removal, erase a spare)"
    say "  0) Quit"
    c=$(ask_choice)
    case "$c" in
      1) look_menu ;;
      2) drives_menu ;;
      3) problem_menu ;;
      4) settings_menu ;;
      5) actions_menu ;;
      0|"") return 0 ;;
      *) say "Enter a number from the list." ;;
    esac
  done
}

