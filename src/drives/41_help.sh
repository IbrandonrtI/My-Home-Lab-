usage_text() {
  cat <<'EOF'
Usage:  sudo drives [command] [options]

View the drives (these commands change nothing):
  status        pools, drives, free space and the last backup
  list          every drive: its name, role, device, size and state
  usage         space used and free for every drive and both pools
  health        SMART health, temperature and bad sectors of every drive
  check         quick check of every pool drive for file system errors

Change the drives:
  connect       connect a new drive to the Main or Backup pool
  disconnect    remove a drive from its pool (its files can be copied to the other drives first)
  move          move a drive between Main and Backup (its files are copied away first)
  bootsection   use part of the boot drive as a pool drive, with a size limit
  timeshift     exclude the boot drive sections from Timeshift snapshots (otherwise the snapshots fill the boot drive)
  adopt         convert the existing single data drive into a pool
  wizard        inspect the drives, suggest a setup and build it after confirmation (also offered after the first install)
  preset        build a complete setup on empty drives: a plain pool, a mirror with a nightly copy, SnapRAID, ZFS or RAID
  snapraid      show or update the SnapRAID parity (status, diff, sync, scrub)
  spare         add a hot spare drive to a ZFS or RAID array (it takes over automatically when a drive fails)
  cache         add an SSD read cache to a ZFS array
  release       remove every drive from the pools (the files stay on the drives)
  remount       Fix Drives: after a disconnection, a power loss or a missing drive, mount the drives, check Immich and Nextcloud and start the containers
  moveboot      copy the files saved on the boot drive while Main had no drive to the Main pool (asks before removing the old ones)
  replace       a drive failed: add a new one in its place and copy the files back from the backup
  restore       copy only the missing files back from the backup
  fillorder     how a pool chooses a drive for a new file (one at a time or spread) and which drive is used first
  balance       move files so that the drives of one storage are about equally full
  limit         how much free space a drive keeps before the pool uses the next drive
  resize        make a boot drive section bigger or smaller
  power         apply the drive power settings

Actions on one drive:
  rename        give a pool drive a custom name (shown in the menus, FileBrowser and the dashboard)
  sleep         put a spinning hard drive to sleep now (it wakes automatically when something reads it)
  wake          wake a spinning hard drive now
  eject         prepare a spare drive for removal: unmount it, write out its data and power a USB drive off
  wipe          erase a spare drive (never a pool drive or the boot drive) and leave it empty or format it

Other:
  (no command)  open the menu
  version       show the version
  help [command]  this text, or the details of one command:  sudo drives help release

Options (before or after the command):
  --dry-run, -n    show what would happen and change nothing (the questions are still asked)
  --yes, -y        answer yes to the yes/no questions (the choice of drive is still asked)
  --confirm-erase  also supply the typed confirmations for erasing or removing a drive (ERASE, REMOVE, CONTINUE, the drive name)
  --now            do not wait for a running backup or upload
  --json           status, list, usage, health, check: print JSON for a script (messages go to stderr)
  --folders        usage: also list the largest folders (slow on a large drive)
  --full           check: scan one drive from start to finish (read-only; its containers stop during the scan)
  --help, -h       show this text; after a command, the details of that command

Before a change that stops the containers, drives checks for a running backup and for files being written to the drives.
If a backup or an upload is running, drives says so and waits for it to finish (up to 6 hours), unless --now is used.

Exit code: 0 = the command completed. 1 = it was refused, cancelled or failed.
health and check also exit 1 when they find a failing drive or an error, so that a script can raise an alert.
EOF
}

help_for() {
  case "${1:-}" in
    status) cat <<'EOF'
sudo drives status [--json]
  Shows both pools (mounted or not, used and size), every pool drive with its SMART result and state, the boot drive,
  the other drives and the last backup. Changes nothing. With --json the same facts are printed as JSON.
EOF
    ;;
    list) cat <<'EOF'
sudo drives list [--json]
  One line per drive: name, role (main, backup, spare, system, plain-data), device, size and state. Changes nothing.
EOF
    ;;
    usage) cat <<'EOF'
sudo drives usage [--folders] [--json]
  Size, used, free and percent for both pools and every drive. --folders adds the ten largest folders of each pool
  (slow on a large drive). Changes nothing.
EOF
    ;;
    health) cat <<'EOF'
sudo drives health [--json]
  Reads each drive's SMART data: overall result, temperature, power-on hours, remapped and pending sectors.
  A sleeping drive is not woken up for this; it is shown as asleep.
  Exit code 1 when a drive reports FAILED or has sectors waiting to be remapped. Changes nothing.
EOF
    ;;
    check) cat <<'EOF'
sudo drives check [--full] [--dry-run] [--json]
  Quick check (default): for every pool drive it reads what the file system and the drive recorded: mounted read-only,
  file system state and error count, SMART, errors in the system log, and how full it is. Nothing stops and nothing changes.
  Exit code 1 when a problem is found.
  --full: scans one drive from start to finish (read-only e2fsck). The drive is taken offline for the scan, so the
  containers that use its storage stop until it is done (a large drive can take an hour or more). It asks first, waits for a
  running backup, and --dry-run shows the steps. Nothing on the drive is changed or repaired.
EOF
    ;;
    connect) cat <<'EOF'
sudo drives connect [--dry-run] [--yes] [--confirm-erase] [--now]
  Lists the connected drives that are not in use, and asks which one to use and for which storage (Main or Backup). A drive that
  already has files can be kept as it is. Erasing requires the drive name and ERASE to be typed. The containers of that pool
  stop for about a minute while the pool is mounted again.
EOF
    ;;
    disconnect) cat <<'EOF'
sudo drives disconnect [--dry-run] [--yes] [--confirm-erase] [--now]
  Removes one drive from its pool. Its files can be copied to the other drives of the same storage first (checked file by
  file). The data on the drive is not erased. The last Main drive cannot be removed. The containers stop briefly.
EOF
    ;;
    move) cat <<'EOF'
sudo drives move [--dry-run] [--yes] [--confirm-erase] [--now]
  Moves a drive from Main to Backup or back. Its files are copied to another drive of its storage, then the drive is
  erased and formatted for the other storage. Everything is checked and confirmed before the drive leaves its pool.
EOF
    ;;
    bootsection) cat <<'EOF'
sudo drives bootsection [--dry-run] [--yes] [--now]
  Uses part of the boot drive as a pool drive: a file of the chosen size, always the last drive of its pool. The boot
  drive keeps at least the reserved free space. A section saved by an earlier version can be used again with its files.
EOF
    ;;
    timeshift) cat <<'EOF'
sudo drives timeshift [--dry-run] [--yes]
  Timeshift (system snapshots) copies the whole boot drive. A boot drive section is one large file that changes every day, so
  each snapshot would contain a full extra copy of it. This adds the section folder to Timeshift's exclude list
  (/etc/timeshift/timeshift.json; the previous file is kept next to it). It is also done automatically when a section is created.
  Does nothing when Timeshift is not set up or the exclusion is already there.
EOF
    ;;
    adopt) cat <<'EOF'
sudo drives adopt [--dry-run] [--yes] [--now]
  Converts the existing single data drive (mounted directly at the Main pool path) into the first drive of a pool. Its files
  are not moved or copied. The containers stop briefly.
EOF
    ;;
    release) cat <<'EOF'
sudo drives release [--dry-run] [--yes] [--now]
  Removes every drive from both pools. The files on the drives are not changed and nothing is erased. Afterwards the pool
  paths are plain folders on the boot drive until drives are connected again. The containers stop briefly.
  Use --dry-run first to see the plan.
EOF
    ;;
    remount) cat <<'EOF'
sudo drives remount [--dry-run] [--now]
  Fix Drives. After a disconnection, a power loss or a missing drive: stops the containers, mounts every drive and pool again, applies the
  power settings and starts the containers. When a Main drive is missing, the services use the boot drive
  (files on the missing drive are not available until it is back). When the drive is back, files saved on the boot drive
  in the meantime are offered for copying to the pool.
  Then it checks that Immich and Nextcloud find their files. If not (the drive that held them is gone), they stay stopped and
  the choice is: copy the files back from the backup (type RESTORE), or start them on empty folders (type START). Their
  accounts and settings are unchanged either way.
EOF
    ;;
    moveboot) cat <<'EOF'
sudo drives moveboot [--dry-run] [--yes] [--now]
  With no drive in Main (or with its drive missing), the services keep running and save their files on the boot drive. When a
  Main drive is back, those files are hidden under the mounted pool. This copies them to the pool (nothing in the pool is
  replaced), checks every file, and only then asks whether to remove the old copies from the boot drive.
EOF
    ;;
    guard) cat <<'EOF'
sudo drives guard
  Runs automatically at start-up, before Docker. If the Main drive is not present, the boot drive becomes the storage so that the services
  still start. It does not need to be run manually.
EOF
    ;;
    replace) cat <<'EOF'
sudo drives replace [--dry-run] [--yes] [--confirm-erase] [--now]
  For a failed drive: choose the missing drive and a new one, which is erased and takes its place. For a Main drive, the
  missing files are copied back from the backup.
EOF
    ;;
    restore) cat <<'EOF'
sudo drives restore [--dry-run] [--yes] [--confirm-erase] [--now]
  Copies back only the files that are in the backup but missing from the main pool. Files that are already there are
  never overwritten. Shows the list first and asks for RESTORE to be typed.
EOF
    ;;
    fillorder) cat <<'EOF'
sudo drives fillorder [--dry-run] [--yes] [--now]
  Shows how a storage chooses a drive for a new file and in which order, and allows changing it: fill one drive at a time (the
  first drive first, the default), spread (the drive with the most free space), or choose which drive is used first. The
  change is applied to the running pool when possible; otherwise you are asked before the pool is mounted again.
  A pool created by an older version is updated too. No files are moved (for that, see: sudo drives balance).
EOF
    ;;
    balance) cat <<'EOF'
sudo drives balance [--dry-run] [--yes] [--now]
  Moves files between the drives of one storage until they are about equally full (in percent). It shows the plan first.
  Every file is copied and checked, then removed from the old drive. The files keep their place in the pool. The services keep
  running during the long copy and stop for a short time at the end. The boot drive section is excluded. If the drives are
  within 5 percentage points of each other nothing is moved. New files still follow the fill order (sudo drives fillorder).
EOF
    ;;
    limit) cat <<'EOF'
sudo drives limit [--dry-run] [--yes] [--now]
  Sets how much free space one drive keeps before the pool uses the next drive (the automatic value is 5% of the drive).
  Enter it as a size (50GB) or a percentage (8%), from 1% to 50% of the drive, or  auto  to return to the automatic value.
  It is applied to the running pool when possible. No files are moved.
EOF
    ;;
    resize) cat <<'EOF'
sudo drives resize [--dry-run] [--yes] [--confirm-erase] [--now]
  Makes a boot drive section larger or smaller. The containers of that pool stop, the file system is checked, resized
  and checked again, and the files are counted before and after. Shrinking is refused when the files would fill more than 90%
  of the new size, and CONTINUE must be typed. Growing needs free space on the boot drive (it always keeps its reserve).
EOF
    ;;
    power) cat <<'EOF'
sudo drives power [--dry-run]
  Applies the drive power settings: main drives never sleep, backup drives sleep after 10 minutes without use.
EOF
    ;;
    rename) cat <<'EOF'
sudo drives rename [--dry-run]
  Gives a pool drive a custom name, for example "Photos drive". The name is kept in /etc/homelab-drive-names under the
  drive's internal label (MAIN1, BACKUP1, ...), so it stays when the drive is connected again. FileBrowser's folder and
  the dashboard follow the new name. Type  auto  as the new name to return to the automatic one. Nothing is erased or moved.
EOF
    ;;
    sleep) cat <<'EOF'
sudo drives sleep [--dry-run]
  Lists the spinning hard drives (not SSDs and not the boot drive) with their state and puts the chosen one to sleep now.
  It wakes automatically when something reads it. Main drives are set never to sleep on their own. Many USB adapters ignore the
  command; in that case a message says so and the exit code is 1. No files are changed.
EOF
    ;;
    wake) cat <<'EOF'
sudo drives wake [--dry-run]
  Wakes a spinning hard drive now by reading one sector from it. No files are changed.
EOF
    ;;
    eject) cat <<'EOF'
sudo drives eject [--dry-run]
  Lists the spare drives (a drive in a pool, the boot drive and a drive in use are never listed), unmounts the chosen one,
  writes out its data and powers a USB drive off. Afterwards it can be removed safely. To remove a pool drive, use
  sudo drives disconnect first. Nothing is erased.
EOF
    ;;
    wizard) cat <<'EOF'
sudo drives wizard [--dry-run] [--yes] [--confirm-erase]
  Inspects the drives (the boot drive and drives that are already in a pool are never changed), counts the empty ones and suggests
  a ready-made setup for that number: 1 drive a plain pool, 2 a mirror with a nightly copy, 3 SnapRAID with one parity drive,
  4 or more SnapRAID with two. A ZFS setup of the same strength is shown beside it. Choose one (or ask for the full list),
  then the normal  sudo drives preset  steps run: the plan, then the setup name and ERASE before anything is erased.
  A drive that already holds files can be used too. For each such drive, choose: keep its files and use it as it is, erase it
  and use it like an empty drive, or skip it. Files can be kept only on a drive with one ext4 partition (another kind of
  drive can be erased or skipped). When a drive keeps its files, only the plain pool and the mirror (the kept drive is the Main
  drive) are suggested, because ZFS, RAID and SnapRAID format every drive they use. The plan says which drives are erased and
  which keep their files. ERASE is requested only when a drive is actually erased.
  It is only for a first setup: when storage is already set up, it says so and does nothing.
  The installer offers it once at the end of the first install. It can be run again at any time with  sudo drives wizard.
  --dry-run shows only the scan, the suggestion and the plan. --yes takes the first suggestion without asking (typing the
  setup name and ERASE is still required, unless --confirm-erase is added). With --yes, drives that hold files are skipped.
EOF
    ;;
    preset) cat <<'EOF'
sudo drives preset [NAME] [--dry-run] [--yes] [--confirm-erase] [--spare] [--cache] [--encrypt]
  Without a name: lists the ready-made setups and shows what the connected empty drives would provide.
  With a name: builds it. Choose the drives, review the plan and the usable space, then type the setup name and ERASE
  before anything is erased. Only empty or new drives are used (for a drive with files, use  sudo drives wizard  to keep or erase its files,
  or erase it first with  sudo drives wipe).
  The Main pool must not have drives yet (to add to it use connect).
    pool        all drives in one pool (no redundancy)
    mirror      exactly 2 drives: the smaller one is Main, the larger one is Backup; Main is copied to Backup every day
    snapraid1   3 or more drives: the largest holds parity data (updated every night at 04:00, not immediately)
    snapraid2   4 or more drives: the two largest hold parity data
  RAID arrays (they become the Main pool at /mnt/storage; all drives must be empty):
    zfs-stripe  2 or more drives, ZFS, all the space, no redundancy        zfs-mirror  2 or more drives, same data on each
    zfs-raidz1  3 or more drives, ZFS, tolerates 1 failed drive            zfs-raidz2  4 or more, tolerates 2    zfs-raidz3  5 or more, tolerates 3
    md-raid0    2 or more drives, Linux RAID, no redundancy                md-raid1    2 or more, same data on each
    md-raid5    3 or more drives, tolerates 1 failed drive                 md-raid6    4 or more, tolerates 2    md-raid10  4 or more, mirrored pairs
  The short names raidz1, raidz2, raidz3 and raid0, raid1, raid5, raid6, raid10 work too.
  ZFS needs  sudo apt install -y zfsutils-linux  and RAID needs  sudo apt install -y mdadm  first.
  Extras for ZFS and RAID setups (without the options, they are asked about; --yes alone never turns an extra on):
    --spare    one more empty drive waits as a hot spare and takes over automatically (all setups except stripe / RAID 0)
    --cache    one more drive, an SSD, becomes a read cache (ZFS only; if the SSD fails, no data is lost)
    --encrypt  the drives are encrypted; the key file stays on the boot drive (/etc/homelab-drives/keys), so the server unlocks
              the array automatically at boot. Keep a copy of the key file elsewhere: without it, the files cannot be read.
  Later,  sudo drives spare  and  sudo drives cache  add a hot spare or a cache to an existing array.
  The setup is recorded in the state folder, and  sudo drives status  shows it.  sudo drives release  removes it again
  (for a ZFS or RAID array this deletes the array and its files, and DESTROY must be typed).
EOF
    ;;
    spare) cat <<'EOF'
sudo drives spare [--dry-run]
  Adds one empty drive to a ZFS or RAID array (built with  sudo drives preset) as a hot spare: it waits and takes over automatically
  when a drive of the array fails. It does not apply to striped setups (there is nothing to take over). Choose the
  drive and type ERASE; the drive is erased. ZFS also turns on automatic replacement.
EOF
    ;;
    cache) cat <<'EOF'
sudo drives cache [--dry-run]
  Adds one empty drive, an SSD, to a ZFS array as a read cache (L2ARC): frequently read files are served from the SSD. If the SSD
  fails, nothing is lost. Choose the drive and type ERASE; the drive is erased. ZFS arrays only.
EOF
    ;;
    snapraid) cat <<'EOF'
sudo drives snapraid [status|diff|sync|scrub] [--dry-run]
  Manual SnapRAID commands, for a setup built with  sudo drives preset snapraid1  (or snapraid2).
    status  is the parity up to date?        diff   what changed since the last sync
    sync    update the parity now             scrub  check part of the files against it
  The same sync runs automatically every night at 04:00, and a scrub on the 1st of the month. Without an argument, the status is shown.
EOF
    ;;
    wipe) cat <<'EOF'
sudo drives wipe [--dry-run] [--yes] [--confirm-erase]
  Erases a spare drive (a drive in a pool, the boot drive and a drive in use are never listed). Choose whether to leave it empty
  or format it as a new empty ext4 drive. The drive name and ERASE must be typed (or --confirm-erase used).
  A quick erase: the file systems and the partition table are removed; the old data is not overwritten.
EOF
    ;;
    version) echo "sudo drives version: shows the version of this command." ;;
    help|"") usage_text ;;
    *) note "There is no command called '$1'. These exist:"; note ""; usage_text >&2; return 1 ;;
  esac
}

