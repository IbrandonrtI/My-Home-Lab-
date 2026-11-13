# ---------- FileBrowser ----------
# FileBrowser shows one folder for every connected drive. After a drive was connected, removed or moved, the installed
# helper updates those folders (FileBrowser restarts for a few seconds). Without homelab-setup (a hand-built server) nothing happens.
sync_filebrowser() {
  [ "$TEST_MODE" = 1 ] && return 0
  [ "$DRY_RUN" = 1 ] && return 0
  [ "${DRIVES_SKIP_SYNC:-}" = 1 ] && return 0      # the uninstall takes the pools apart and removes the dashboard itself
  # the Homepage drive pills ("Main Pool" / "Connect Backup Drive" ...) follow the pools
  command -v homelab-sample >/dev/null 2>&1 && { homelab-sample widgets 9>&- >/dev/null 2>&1 || true; }
  # the Stats tab and the drive temperatures are only redone every 15 minutes: after a change of the drives they are redone now (in the background, it takes a little while)
  if command -v homelab-stats >/dev/null 2>&1; then
    { homelab-sample 9>&-; homelab-stats 9>&-; } >/dev/null 2>&1 </dev/null &
    disown 2>/dev/null || true
  fi
  command -v homelab-setup >/dev/null 2>&1 || return 0
  # Homepage can only measure a pool that is mounted inside its own container: after a pool was mounted or changed it must see it
  # (the helper changes nothing when Homepage already sees the pools; otherwise it fixes the stack or restarts Homepage)
  homelab-setup homepage 9>&- || note "Homepage was not updated. Later, run:  sudo homelab-setup homepage"
  homelab-setup filebrowser 9>&- || note "FileBrowser's drive folders were not updated. Later, run:  sudo homelab-setup filebrowser"
}

# ---------- menu ----------
# The first screen has three groups so it stays short; each group opens its own small menu.
#   1) Show status
#   2) Add or remove drives      connect, disconnect, move, boot drive section, take all out
#   3) Fix a problem             remount after an unplug, replace a dead drive, copy back missing files
#   4) Settings and upgrades     power settings, fill order, convert the old single data drive
ask_choice() { ask "Type a number and press Enter: "; }

# After a menu choice: say what was chosen and what will happen, so it is clear before anything is asked or changed.
# intro_ask also asks whether to go on (Enter or n goes back to the menu without changing anything). The flows that ask their own
# "Continue?" later use intro, which only explains.
intro() {   # intro "Title" "line" ...
  local t=$1 l; shift
  say ""
  say "You chose: $t"
  for l in "$@"; do say "  $l"; done
  say ""
}
intro_ask() {   # intro_ask "Title" "line" ...  -> 0 to go on, 1 to go back
  intro "$@"
  yn "Do you want to go on?" || { say "Okay. Nothing was changed."; return 1; }
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
           "Next I list the drives that are plugged in and not used yet. You pick one," \
           "then you say if it is for the Main pool or the Backup pool." \
           "If the drive has files on it you can keep them. Nothing is erased without you typing ERASE." &&
         { connect_flow && sync_filebrowser; } ;;
      2) intro_ask "Disconnect a drive" \
           "Next I list the drives that are in the pools and you pick one." \
           "If it holds files, you are asked if they should be copied to another drive first." \
           "The files on the drive are not erased." &&
         { disconnect_flow && sync_filebrowser; } ;;
      3) intro_ask "Move a drive between main and backup" \
           "Next you pick a drive. Its files are copied to the other drives of its storage first," \
           "then the drive is erased and formatted for the other storage." &&
         { move_flow && sync_filebrowser; } ;;
      4) intro "Use part of the boot drive for a pool" \
           "Next you choose the Main or the Backup pool, read the warning and choose the size." \
           "You are asked again before anything is made. Cancel any time by pressing Enter." &&
         { bootsection_flow && sync_filebrowser; } ;;
      5) intro "Take all drives out of the pools" \
           "Next I list the drives and ask before anything is released." \
           "The files on the drives are not erased." &&
         { release_flow && sync_filebrowser; } ;;
      6) intro "Build a ready-made setup" \
           "Next you see the setups (a plain pool, a mirror with a nightly copy, SnapRAID protection) and what your empty drives would give." \
           "You pick a setup and the empty drives. The drives are formatted: you are asked twice before anything is erased." &&
         { preset_menu && sync_filebrowser; } ;;
      0|"") return 0 ;;
      *) say "Please type a number from the list." ;;
    esac
  done
}

problem_menu() {
  local c
  while :; do
    say ""
    say "Fix a problem"
    say "  1) Fix the drives after an unplug, a power cut or a lost drive"
    say "  2) Replace a dead drive (restores the missing files from the backup)"
    say "  3) Copy back only the files that are missing from the backup"
    say "  4) Copy files saved on the boot drive onto the Main pool"
    say "  0) Back"
    c=$(ask_choice)
    case "$c" in
      1) intro_ask "Fix the drives after an unplug, a power cut or a lost drive" \
           "The services that use the storage are stopped, the drives are mounted again and the services start again." \
           "Then Immich and Nextcloud are checked: if their files are missing you can copy them back from the backup." \
           "No files are changed unless you say so. It takes about a minute." &&
         { remount_flow && sync_filebrowser; } ;;
      2) intro "Replace a dead drive" \
           "Next I list the pool drives that cannot be found and you pick the dead one." \
           "Then you pick the new drive. The missing files are copied back from the backup." \
           "You are asked again before anything is erased." &&
         { replace_flow && sync_filebrowser; } ;;
      3) intro "Copy back only the files that are missing from the backup" \
           "Next I look for the backup copy and show what it holds." \
           "Only files that are missing in the main pool are copied back. Nothing is overwritten." &&
         { restore_flow && sync_filebrowser; } ;;
      4) intro "Copy files saved on the boot drive onto the Main pool" \
           "While the Main pool had no drive, the services saved their files on the boot drive." \
           "They are copied to the pool, checked, and you are asked before the old copies are removed." &&
         { moveboot_flow && sync_filebrowser; } ;;
      0|"") return 0 ;;
      *) say "Please type a number from the list." ;;
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
           "Main drives never go to sleep. Backup drives sleep after 10 minutes without use." \
           "No files are touched." &&
         power_all ;;
      2) intro "Fill order" \
           "Next you pick a storage and see how it picks a drive for a new file. A pool uses its first drive until only" \
           "${POOL_FREE_PERCENT}% of it is free, then the next one, or it can spread by free space. No files are moved." &&
         fillorder_flow ;;
      3) intro "Convert the current single data drive into the main pool" \
           "Only for older setups where one drive is mounted directly as the main pool." \
           "Next you see what changes and are asked before anything is done." &&
         { adopt_flow && sync_filebrowser; } ;;
      4) intro "Even out the used space (balance)" \
           "Next you pick a storage and see a plan: which files move from the fullest drive to the emptiest." \
           "Files are copied and checked before they are removed. You are asked before anything moves." &&
         { balance_flow && sync_filebrowser; } ;;
      5) intro "Free space a drive keeps" \
           "Next you pick a drive and type how much free space it keeps (for example 50GB or 8%)." \
           "No files are moved." &&
         limit_flow ;;
      6) intro "Make a boot drive section bigger or smaller" \
           "Next you pick a section and its new size. The containers of that pool stop for a while." \
           "You are asked again before anything changes." &&
         { resize_flow && sync_filebrowser; } ;;
      0|"") return 0 ;;
      *) say "Please type a number from the list." ;;
    esac
  done
}

menu() {
  local c
  while :; do
    say ""
    [ "$TEST_MODE" = 1 ] && say "*** TEST MODE: test folders and a test fstab, real pools are not touched ***"
    say "Home lab drives"
    say "  1) Look at the drives (status, list, space, health, checks)"
    say "  2) Add or remove drives"
    say "  3) Fix a problem"
    say "  4) Settings and upgrades"
    say "  5) Actions on one drive (rename, sleep, wake, unplug, erase a spare)"
    say "  0) Quit"
    c=$(ask_choice)
    case "$c" in
      1) look_menu ;;
      2) drives_menu ;;
      3) problem_menu ;;
      4) settings_menu ;;
      5) actions_menu ;;
      0|"") return 0 ;;
      *) say "Please type a number from the list." ;;
    esac
  done
}

