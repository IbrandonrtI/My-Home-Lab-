usage_text() {
  cat <<'EOF'
Usage:  sudo drives [command] [options]

Look at the drives (these change nothing):
  status        pools, drives, free space and the last backup
  list          every drive: its name, role, device, size and state
  usage         space used and free for every drive and both pools
  health        SMART health, temperature and bad sectors of every drive
  check         quick check of every pool drive for file system errors

Change the drives:
  connect       connect a new drive to the Main or the Backup pool
  disconnect    take a drive out of its pool (its files can be copied to the other drives first)
  move          move a drive between Main and Backup (its files are copied away first)
  bootsection   use part of the boot drive as a pool drive, with a size limit
  timeshift     make Timeshift skip the boot drive sections (otherwise its snapshots fill the boot drive)
  adopt         turn the old single data drive into a pool
  wizard        look at the drives, suggest a setup for them and build it if you say yes (also offered after the first install)
  preset        build a whole setup on empty drives: a plain pool, a mirror with a nightly copy, SnapRAID, ZFS or RAID
  snapraid      look at or update the SnapRAID protection (status, diff, sync, scrub)
  spare         add a hot spare drive to a ZFS or RAID array (it takes over by itself when a drive dies)
  cache         add an SSD read cache to a ZFS array
  release       take every drive out of the pools (the files stay on the drives)
  remount       after an unplug or a power cut: mount the drives and start the containers again
  replace       a drive died: put a new one in its place and copy the files back from the backup
  restore       copy only the missing files back from the backup
  fillorder     how a pool picks a drive for a new file (one at a time or spread) and which drive goes first
  balance       move files so the drives of one storage are about equally full
  limit         how much free space one drive keeps before the pool uses the next drive
  resize        make a boot drive section bigger or smaller
  power         apply the drive power settings

Actions on one drive:
  rename        give a pool drive a name of your own (shown in the menus, FileBrowser and the dashboard)
  sleep         put a spinning hard drive to sleep now (it wakes up by itself when something reads it)
  wake          wake a spinning hard drive up now
  eject         get a spare drive ready to unplug: unmount it, write out its data, power a USB drive off
  wipe          erase a spare drive (never a pool drive or the boot drive), leave it empty or format it

Other:
  (no command)  open the menu
  version       show the version
  help [command]  this text, or the details of one command:  sudo drives help release

Options (before or after the command):
  --dry-run, -n    show what would happen and change nothing (the questions are still asked)
  --yes, -y        answer the yes/no questions with yes (which drive to use is still asked)
  --confirm-erase  also type the confirmations for erasing or removing a drive (ERASE, REMOVE, CONTINUE, the drive name)
  --now            do not wait for a running backup or upload
  --json           status, list, usage, health, check: print JSON for a script (messages go to stderr)
  --folders        usage: also list the biggest folders (slow on a big drive)
  --full           check: scan one drive from start to finish (read-only; its containers stop meanwhile)
  --help, -h       show this text; after a command, the details of that command

Before a change that stops the containers, drives looks at the backup and at what is being written to the drives.
If a backup or an upload is running it says so and waits for it to finish (up to 6 hours), unless you use --now.

Exit code: 0 = the command did what was asked. 1 = it was refused, cancelled or failed.
health and check also exit 1 when they find a failing drive or an error, so a script can alert on it.
EOF
}

help_for() {   # help_for COMMAND: what it does, what it asks, what it changes
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
  Size, used, free and percent for both pools and every drive. --folders adds the ten biggest folders of each pool
  (slow on a big drive). Changes nothing.
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
  --full: scans ONE drive from start to finish (read-only e2fsck). The drive is taken offline for the scan, so the
  containers that use its storage stop until it is done (a big drive can take an hour or more). It asks first, waits for a
  running backup, and --dry-run shows the steps. Nothing on the drive is changed or repaired.
EOF
    ;;
    connect) cat <<'EOF'
sudo drives connect [--dry-run] [--yes] [--confirm-erase] [--now]
  Lists the drives that are plugged in and not used, asks which one and for which storage (Main or Backup). A drive that
  already has files can be kept as it is. Erasing needs the drive name and ERASE typed. The containers of that storage
  stop for about a minute while the pool mounts again.
EOF
    ;;
    disconnect) cat <<'EOF'
sudo drives disconnect [--dry-run] [--yes] [--confirm-erase] [--now]
  Takes one drive out of its pool. Its files can be copied to the other drives of the same storage first (checked file by
  file). The data on the drive is not erased. The last main drive cannot be removed. The containers stop for a minute.
EOF
    ;;
    move) cat <<'EOF'
sudo drives move [--dry-run] [--yes] [--confirm-erase] [--now]
  Moves a drive from Main to Backup or back: its files are copied to another drive of its storage, then the drive is
  ERASED and formatted for the other storage. Everything is checked and confirmed before the drive leaves its pool.
EOF
    ;;
    bootsection) cat <<'EOF'
sudo drives bootsection [--dry-run] [--yes] [--now]
  Uses part of the boot drive as a pool drive: a file of the size you choose, always the last drive of its pool. The boot
  drive keeps at least the reserved free space. A section saved by an earlier release can be used again with its files.
EOF
    ;;
    timeshift) cat <<'EOF'
sudo drives timeshift [--dry-run] [--yes]
  Timeshift (system snapshots) copies the whole boot drive. A boot drive section is one big file that changes every day, so
  each snapshot would hold a full extra copy of it. This adds the section folder to Timeshift's exclude list
  (/etc/timeshift/timeshift.json; the old file is kept next to it). It is also done by itself when a section is made.
  Does nothing when Timeshift is not set up or the exclusion is already there.
EOF
    ;;
    adopt) cat <<'EOF'
sudo drives adopt [--dry-run] [--yes] [--now]
  Turns the old single data drive (mounted directly at the main pool path) into the first drive of a pool. Its files
  are not moved or copied. The containers stop for a minute.
EOF
    ;;
    release) cat <<'EOF'
sudo drives release [--dry-run] [--yes] [--now]
  Takes EVERY drive out of both pools. The files on the drives are not touched and nothing is erased. Afterwards the pool
  paths are plain folders on the boot drive until you connect drives again. The containers stop for a minute.
  Try it first with --dry-run.
EOF
    ;;
    remount) cat <<'EOF'
sudo drives remount [--dry-run] [--now]
  After an unplug or a power cut: stops the containers, mounts every drive and pool again, applies the power settings
  and starts the containers. When a main drive is missing the containers stay stopped on purpose.
EOF
    ;;
    replace) cat <<'EOF'
sudo drives replace [--dry-run] [--yes] [--confirm-erase] [--now]
  For a dead drive: you pick the missing drive and a new one, which is erased and takes its place. For a main drive the
  missing files are copied back from the backup.
EOF
    ;;
    restore) cat <<'EOF'
sudo drives restore [--dry-run] [--yes] [--confirm-erase] [--now]
  Copies back only the files that are in the backup but missing from the main pool. Files that are already there are
  never overwritten. Shows the list first and asks you to type RESTORE.
EOF
    ;;
    fillorder) cat <<'EOF'
sudo drives fillorder [--dry-run] [--yes] [--now]
  Shows how a storage picks a drive for a new file and in which order, and lets you change it: fill one drive at a time (the
  first drive first, the default), spread (the drive with the most free space), or choose which drive is used first. The
  change is used right away by the running pool when possible; otherwise you are asked before the pool is mounted again.
  A pool of an older version is updated too. No files are moved (for that see: sudo drives balance).
EOF
    ;;
    balance) cat <<'EOF'
sudo drives balance [--dry-run] [--yes] [--now]
  Moves files between the drives of one storage until they are about equally full (in percent). It shows the plan first.
  Every file is copied and checked, then removed from the old drive; the files keep their place in the pool. The services keep
  running during the long copy and stop for a short time at the end. The boot drive section is left out. If the drives are
  within 5 percentage points of each other nothing is moved. New files still follow the fill order (sudo drives fillorder).
EOF
    ;;
    limit) cat <<'EOF'
sudo drives limit [--dry-run] [--yes] [--now]
  Sets how much free space one drive keeps before the pool uses the next drive (the automatic value is 5% of the drive).
  Type it as a size (50GB) or a percentage (8%), from 1% to 50% of the drive, or  auto  to go back to the automatic value.
  It is used right away by the running pool when possible. No files are moved.
EOF
    ;;
    resize) cat <<'EOF'
sudo drives resize [--dry-run] [--yes] [--confirm-erase] [--now]
  Makes a boot drive section bigger or smaller. The containers of that storage stop, the file system is checked, resized
  and checked again, and the files are counted before and after. Shrinking is refused when the files would fill more than 90%
  of the new size, and you must type CONTINUE. Growing needs free space on the boot drive (it always keeps its reserve).
EOF
    ;;
    power) cat <<'EOF'
sudo drives power [--dry-run]
  Applies the drive power settings: main drives never sleep, backup drives sleep after 10 minutes without use.
EOF
    ;;
    rename) cat <<'EOF'
sudo drives rename [--dry-run]
  Gives a pool drive a name of your own, for example "Photos drive". The name is kept in /etc/homelab-drive-names under the
  drive's internal label (MAIN1, BACKUP1, ...), so it stays when the drive is plugged in again. FileBrowser's folder and
  the dashboard follow the new name. Type  auto  as the new name to go back to the automatic one. Nothing is erased or moved.
EOF
    ;;
    sleep) cat <<'EOF'
sudo drives sleep [--dry-run]
  Lists the spinning hard drives (not SSDs and not the boot drive) with their state and sends the one you pick to sleep now.
  It wakes by itself when something reads it; main drives are set to never sleep on their own. Many USB adapters ignore the
  command: then it says so and exits with 1. No files are touched.
EOF
    ;;
    wake) cat <<'EOF'
sudo drives wake [--dry-run]
  Wakes a spinning hard drive up now by reading one sector from it. No files are touched.
EOF
    ;;
    eject) cat <<'EOF'
sudo drives eject [--dry-run]
  Lists the spare drives (a drive in a pool, the boot drive and a drive in use are never listed), unmounts the one you pick,
  writes out its data and powers a USB drive off. Afterwards it is safe to unplug. To unplug a pool drive use
  sudo drives disconnect first. Nothing is erased.
EOF
    ;;
    wizard) cat <<'EOF'
sudo drives wizard [--dry-run] [--yes] [--confirm-erase]
  Looks at the drives (the boot drive and drives that are already in a pool are never touched), counts the EMPTY ones and suggests
  a ready-made setup for that number: 1 drive a plain pool, 2 a mirror with a nightly copy, 3 SnapRAID with one protection drive,
  4 or more SnapRAID with two. A real ZFS setup of the same strength is shown beside it. You pick one (or ask for the full list),
  then the normal  sudo drives preset  steps run: the plan, then the setup name and ERASE before anything is erased.
  A drive that already HOLDS FILES can be used too. For each such drive you choose: keep its files and use it as it is, erase it
  and use it like an empty drive, or leave it alone. Files can be kept only on a drive with one ext4 partition (another kind of
  drive can be erased or left alone). When a drive keeps its files, only the plain pool and the mirror (the kept drive is the Main
  drive) are suggested, because ZFS, RAID and SnapRAID format every drive they use. The plan says which drives are erased and
  which keep their files; ERASE is only asked when a drive is really erased.
  It is only for a fresh start: when storage is already set up it says so and does nothing.
  The installer offers it once at the end of the first install; run it again any time with  sudo drives wizard.
  --dry-run shows the scan, the suggestion and the plan only. --yes takes the first suggestion without asking (the typing of
  the setup name and ERASE is still needed, unless you add --confirm-erase). With --yes, drives that hold files are left alone.
EOF
    ;;
    preset) cat <<'EOF'
sudo drives preset [NAME] [--dry-run] [--yes] [--confirm-erase] [--spare] [--cache] [--encrypt]
  Without a name: lists the ready-made setups and shows what the empty drives that are plugged in now would give.
  With a name: builds it. You pick the drives, see the plan and what you can use, and type the setup name and ERASE
  before anything is erased. Only EMPTY or new drives are used (a drive with files: use  sudo drives wizard  to keep or erase its files,
  or erase it first with  sudo drives wipe).
  The Main pool must not have drives yet (to add to it use connect).
    pool        all the drives in one pool (no protection)
    mirror      exactly 2 drives: the smaller one is Main, the bigger one is Backup; the backup copies Main to it every day
    snapraid1   3 or more drives: the biggest holds protection data (updated every night at 04:00, not at once)
    snapraid2   4 or more drives: the two biggest hold protection data
  Real RAID arrays (they become the Main pool at /mnt/storage; the drives must all be empty):
    zfs-stripe  2 or more drives, ZFS, all the space, NO protection        zfs-mirror  2 or more drives, same data on each
    zfs-raidz1  3 or more drives, ZFS, 1 drive can die                     zfs-raidz2  4 or more, 2 can die    zfs-raidz3  5 or more, 3 can die
    md-raid0    2 or more drives, Linux RAID, NO protection                md-raid1    2 or more, same data on each
    md-raid5    3 or more drives, 1 can die                                md-raid6    4 or more, 2 can die    md-raid10  4 or more, mirrored pairs
  The short names raidz1, raidz2, raidz3 and raid0, raid1, raid5, raid6, raid10 work too.
  ZFS needs  sudo apt install -y zfsutils-linux  and RAID needs  sudo apt install -y mdadm  first.
  Extras for ZFS and RAID setups (without the options it asks; --yes alone never turns an extra on):
    --spare    one more empty drive waits as a hot spare and takes over by itself (all but the stripe / RAID 0 setups)
    --cache    one more drive, an SSD, becomes a read cache (ZFS only; if the SSD dies no data is lost)
    --encrypt  the drives are encrypted; the key file stays on the boot drive (/etc/homelab-drives/keys), so the server unlocks
               itself at boot. KEEP A COPY OF THE KEY FILE somewhere else: without it the files cannot be read again.
  Later: sudo drives spare  and  sudo drives cache  add a hot spare or a cache to an array that is already there.
  The setup is kept in the state folder; sudo drives status shows it. sudo drives release takes it apart again
  (for a ZFS / RAID array that DELETES the array and its files: it asks you to type DESTROY).
EOF
    ;;
    spare) cat <<'EOF'
sudo drives spare [--dry-run]
  Adds one empty drive to a ZFS or RAID array (built with  sudo drives preset) as a hot spare: it waits and takes over by
  itself when a drive of the array dies. It does not work for the striped setups (nothing to take over). You pick the
  drive, type ERASE, and it is erased. ZFS also turns on automatic replacement.
EOF
    ;;
    cache) cat <<'EOF'
sudo drives cache [--dry-run]
  Adds one empty drive, an SSD, to a ZFS array as a read cache (L2ARC): often-read files come from the SSD. If the SSD
  dies nothing is lost. You pick the drive, type ERASE, and it is erased. ZFS arrays only.
EOF
    ;;
    snapraid) cat <<'EOF'
sudo drives snapraid [status|diff|sync|scrub] [--dry-run]
  SnapRAID by hand, for a setup built with  sudo drives preset snapraid1  (or snapraid2).
    status  is the protection up to date?     diff   what changed since the last update
    sync    update the protection now         scrub  check part of the files against it
  The same sync runs by itself every night at 04:00 (and a scrub on the 1st of the month). Without a word it shows the status.
EOF
    ;;
    wipe) cat <<'EOF'
sudo drives wipe [--dry-run] [--yes] [--confirm-erase]
  ERASES a spare drive (a drive in a pool, the boot drive and a drive in use are never listed). You choose to leave it empty
  or to format it as a new empty ext4 drive. You must type the drive name and ERASE (or use --confirm-erase).
  A quick erase: the file systems and the partition table are removed; the old data is not overwritten.
EOF
    ;;
    version) echo "sudo drives version: shows the version of this command." ;;
    help|"") usage_text ;;
    *) note "There is no command called '$1'. These exist:"; note ""; usage_text >&2; return 1 ;;
  esac
}

