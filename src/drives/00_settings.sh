#!/usr/bin/env bash
# drives - menu for the home lab storage pools.
#
# Main pool   = mergerfs pool at /mnt/storage (services already use this path)
# Backup pool = mergerfs pool at /mnt/backup
# Every drive is mounted by UUID under /mnt/disks/ with a label (MAIN1, BACKUP1, ...).
# A pool can also get one "boot drive section": a file of a fixed size on the boot drive, mounted as MAINBOOT / BACKUPBOOT.
# It is always the LAST branch of its pool, so it is used only when the real drives are full.
#
# Run:  sudo drives
# Test: sudo DRIVES_TEST=1 drives     (uses separate test folders and a test fstab,
#                                       never touches the real pools or /etc/fstab)

set -u
set -o pipefail
export PATH="${HOMELAB_EXTRA_PATH:+$HOMELAB_EXTRA_PATH:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

VERSION="1.9"
TEST_MODE="${DRIVES_TEST:-0}"
# Owner of the top folder of a new main drive: DRIVES_OWNER, else the user who ran sudo, else the first normal user (uid 1000).
OWNER="${DRIVES_OWNER:-${SUDO_USER:-$(getent passwd 1000 | cut -d: -f1)}}"

if [ "$TEST_MODE" = 1 ]; then
  STATE_DIR="${DRIVES_STATE_DIR:-/var/tmp/homelab-drives-test}"
  FSTAB="${FSTAB:-$STATE_DIR/fstab}"
  DISKS_DIR="${DISKS_DIR:-/mnt/test-disks}"
  MAIN_POOL="${MAIN_POOL:-/mnt/test-main}"
  BACKUP_POOL="${BACKUP_POOL:-/mnt/test-backup}"
  MAIN_PREFIX="${MAIN_PREFIX:-TMAIN}"
  BACKUP_PREFIX="${BACKUP_PREFIX:-TBACKUP}"
  LOGFILE="${LOGFILE:-$STATE_DIR/drives.log}"
  mkdir -p "$STATE_DIR"
  [ -f "$FSTAB" ] || : >"$FSTAB"
  POOL_MINFREE="${POOL_MINFREE:-${DRIVES_MINFREE:-10M}}"   # the test disks are tiny
  BACKUP_STATUS_FILE="${BACKUP_STATUS_FILE:-$STATE_DIR/last-run}"   # test mode never reads the real backup record
  BOOT_SECTION_DIR="${BOOT_SECTION_DIR:-$STATE_DIR/boot-sections}"
  TIMESHIFT_CONF="${TIMESHIFT_CONF:-$STATE_DIR/timeshift.json}"      # test mode never touches the real Timeshift settings
  BOOT_KEEP_FREE_BYTES="${DRIVES_BOOT_KEEP:-100000000}"     # the test machine is small: keep 100 MB, smallest section 16 MB
  BOOT_MIN_BYTES="${DRIVES_BOOT_MIN:-16000000}"
  BOOT_SMALL_BYTES="${DRIVES_BOOT_SMALL:-0}"                # a boot drive this small (or smaller) cannot lend a section (0 = never, for the tests)
  BOOT_UNIT_BYTES=1000000; BOOT_UNIT_NAME=MB               # sizes are typed in MB in test mode
  PARITY_PREFIX="${PARITY_PREFIX:-TPARITY}"
  SNAPRAID_CONF="${SNAPRAID_CONF:-$STATE_DIR/snapraid.conf}"
  SNAPRAID_CRON="${SNAPRAID_CRON:-$STATE_DIR/snapraid-cron}"
  SNAPRAID_CONTENT_DIR="${SNAPRAID_CONTENT_DIR:-$STATE_DIR/snapraid-content}"
  SNAPRAID_LOG="${SNAPRAID_LOG:-$STATE_DIR/snapraid.log}"
  MDADM_CONF="${MDADM_CONF:-$STATE_DIR/mdadm.conf}"
  ZFS_SCRUB_CRON="${ZFS_SCRUB_CRON:-$STATE_DIR/zfs-scrub-cron}"
  ZFS_SYSTEM_SCRUB="${ZFS_SYSTEM_SCRUB:-$STATE_DIR/zfsutils-linux-cron}"
  KEY_DIR="${KEY_DIR:-$STATE_DIR/keys}"
  CRYPTTAB="${CRYPTTAB:-$STATE_DIR/crypttab}"
  MAPPER_DIR="${MAPPER_DIR:-$STATE_DIR/mapper}"
  ZFS_KEY_UNIT="${ZFS_KEY_UNIT:-$STATE_DIR/homelab-zfs-key.service}"
  MIGRATE_DIR="${MIGRATE_DIR:-/mnt/test-newmain}"
else
  STATE_DIR="${DRIVES_STATE_DIR:-/var/lib/homelab-drives}"
  FSTAB="${FSTAB:-/etc/fstab}"
  DISKS_DIR="${DISKS_DIR:-/mnt/disks}"
  MAIN_POOL="${MAIN_POOL:-/mnt/storage}"
  MIGRATE_DIR="${MIGRATE_DIR:-/mnt/storage-new}"                    # where a new ZFS / RAID setup is built and filled while the old Main pool is still in use
  BACKUP_POOL="${BACKUP_POOL:-/mnt/backup}"
  MAIN_PREFIX="${MAIN_PREFIX:-MAIN}"
  BACKUP_PREFIX="${BACKUP_PREFIX:-BACKUP}"
  LOGFILE="${LOGFILE:-/var/log/homelab-drives.log}"
  BOOT_SECTION_DIR="${BOOT_SECTION_DIR:-/var/lib/homelab-boot-sections}"
  TIMESHIFT_CONF="${TIMESHIFT_CONF:-/etc/timeshift/timeshift.json}"
  BOOT_KEEP_FREE_BYTES="${HOMELAB_BOOT_KEEP_BYTES:-128000000000}"   # the boot drive always keeps 128 GB free for the system and the apps
  BOOT_SMALL_BYTES="${HOMELAB_BOOT_SMALL_BYTES:-130000000000}"      # a "128 GB" boot drive (or smaller) cannot lend any space: the system needs all of it
  BOOT_MIN_BYTES="${HOMELAB_BOOT_MIN_BYTES:-30000000000}"          # a section smaller than 30 GB is refused
  PARITY_PREFIX="${PARITY_PREFIX:-PARITY}"                          # the SnapRAID protection drives: PARITY1, PARITY2
  SNAPRAID_CONF="${SNAPRAID_CONF:-/etc/snapraid.conf}"
  SNAPRAID_CRON="${SNAPRAID_CRON:-/etc/cron.d/homelab-snapraid}"
  SNAPRAID_CONTENT_DIR="${SNAPRAID_CONTENT_DIR:-/var/lib/snapraid}"
  SNAPRAID_LOG="${SNAPRAID_LOG:-/var/log/homelab-snapraid.log}"
  MDADM_CONF="${MDADM_CONF:-/etc/mdadm/mdadm.conf}"
  ZFS_SCRUB_CRON="${ZFS_SCRUB_CRON:-/etc/cron.d/homelab-zfs-scrub}"
  ZFS_SYSTEM_SCRUB="${ZFS_SYSTEM_SCRUB:-/etc/cron.d/zfsutils-linux}"      # Ubuntu / Mint already check ZFS pools once a month with this file
  KEY_DIR="${KEY_DIR:-/etc/homelab-drives/keys}"                           # the key files of encrypted arrays (root only)
  CRYPTTAB="${CRYPTTAB:-/etc/crypttab}"
  MAPPER_DIR="${MAPPER_DIR:-/dev/mapper}"
  ZFS_KEY_UNIT="${ZFS_KEY_UNIT:-/etc/systemd/system/homelab-zfs-key.service}"
fi
ZFS_POOL_NAME="${ZFS_POOL_NAME:-tank}"                              # the name of the ZFS pool a ready-made ZFS setup creates
MD_NAME="${MD_NAME:-homelab}"                                       # the name of the mdadm array a ready-made RAID setup creates
MD_DEVICE="${DRIVES_MD_DEVICE:-/dev/md/$MD_NAME}"
MD_CRYPT="$MD_NAME-crypt"                                           # the name of the unlocked (decrypted) RAID device
PRESET_FILE="${PRESET_FILE:-$STATE_DIR/preset}"                     # what `drives preset` built: ID|date|labels
WIZARD_FILE="${WIZARD_FILE:-$STATE_DIR/wizard}"                     # DATE|answer: the drive wizard was asked once (the first-run offer is not repeated)
BOOT_OPTS="loop,noatime,nofail"
BOOT_UNIT_BYTES="${BOOT_UNIT_BYTES:-1000000000}"; BOOT_UNIT_NAME="${BOOT_UNIT_NAME:-GB}"

# category.create=ff: a new file goes to the first drive (MAIN1, then MAIN2, ...) that still has room, so the drives fill up
# one after the other. Every file sits whole on one drive. A drive keeps 5% of its own size free before the next one is used
# (set per drive in the pool line: /mnt/disks/MAIN1=RW,<size>). POOL_MINFREE is only the fallback for a drive whose size is unknown.
POOL_MINFREE="${POOL_MINFREE:-20G}"
POOL_FREE_PERCENT="${POOL_FREE_PERCENT:-5}"
POOL_OPTS_BASE="allow_other,cache.files=off,category.create=ff,moveonenospc=true,dropcacheonclose=true,minfreespace=$POOL_MINFREE,nofail"
# A drive is shown by what it is, e.g. "1 TB Samsung HDD", never by its internal label (MAIN1, BACKUP1). The names you chose
# yourself are in DRIVE_NAMES_FILE (LABEL=Name per line); the name scanned when a drive was connected is kept in NAME_STORE,
# so a drive that is unplugged or dead still shows its name.
DRIVE_NAMES_FILE="${DRIVE_NAMES_FILE:-/etc/homelab-drive-names}"
[ "$TEST_MODE" = 1 ] && DRIVE_NAMES_FILE="${DRIVE_NAMES_FILE_TEST:-$STATE_DIR/drive-names-chosen}"
NAME_STORE="${NAME_STORE:-$STATE_DIR/drive-names}"
# What you changed with `drives fillorder` and `drives limit`: how a pool picks a drive for a new file (policy), which drive goes
# first (order) and how much free space a drive keeps (limit). One line per setting: KIND|KEY|VALUE.
SETTINGS_FILE="${SETTINGS_FILE:-$STATE_DIR/pool-settings}"
BALANCE_TOLERANCE="${BALANCE_TOLERANCE:-5}"   # balance does nothing when the fullest and the emptiest drive are this many percentage points apart or less
BRANCH_OPTS="defaults,noatime,nofail,x-systemd.device-timeout=10"
BACKUP_STATUS_FILE="${BACKUP_STATUS_FILE:-/var/lib/homelab-backup/last-run}"
DRAIN_SPARE_BYTES="${DRAIN_SPARE_BYTES:-2147483648}"   # free space to keep on the target drive when copying a drive off

DRY_RUN=0            # --dry-run: show what would happen, change nothing
ASSUME_YES=0         # --yes: answer the yes/no questions with yes
CONFIRM_ERASE=0      # --confirm-erase: also type the confirmations for erasing or removing a drive (ERASE, REMOVE, CONTINUE, the drive name)
NOW=0                # --now: do not wait for a running backup or upload
PANEL_MODE=0          # 1 only inside `drives panel ...`: typed confirmations come from PANEL_TYPED, nothing is ever asked, no question is answered with yes
PANEL_TYPED=()       # the words the person typed in the panel (checked by typed(), never trusted without a match)
PANEL_ARG=""         # the extra choice of the panel command: empty|format (wipe), yes|no (copy first), keep|erase ...
PANEL_KEEP=""        # move: yes = the drive keeps its files and joins the other pool as it is, no = it is erased and formatted
PANEL_COPY=""        # disconnect and move: yes = copy the drive's files to the other drives of its pool first, no = do not
PANEL_IDS=()         # the drives of a panel add, move or disconnect (one or several), and for each the choice "keep" or "erase" when the panel sends them one by one
PANEL_MODES=()
PANEL_ROLE=""        # add: the pool they join
PANEL_UNITS=""       # bootadd: the size of the boot drive section, in GB
PANEL_ALL=""         # add and move: the one choice (keep or erase) for every drive
PANEL_NOW=0          # the panel's "Go Ahead Anyway": do not wait for a running backup or upload (it sends the word NOW)
PROG_ITEM=""         # the drive the progress lines are about (panel only)
PROG_LO=0; PROG_HI=100   # the part of the bar a step may use (a move is two steps: leaving a pool, then joining the other)
PANEL_LEAVING=()     # the pool folders of the drives that leave their pools in this batch (a copy never goes to one of them)
PANEL_RESERVE_DIR="" # the folder of a batch with several drives: reserved drive names and reserved space
PANEL_JOBS=3         # how many drives of one batch are worked on at the same time
CRIT_DEPTH=0         # >0 while this process holds the pool lock (the short steps that change a pool run one at a time)
ABORTED=0            # 1 when the person pressed Stop and this drive was stopped because of it
HOLDER_STOPPED=""
KEEP_IMG=0           # 1 while a boot drive section moves to the other pool with its file (the file is not deleted when it leaves)
PANEL_HOLD=0         # 1 while a batch of several drives runs: the containers are stopped once (at the first pool change) and started once (when every drive is done)
PANEL_BARRIER=0      # 1 while a batch of several drives runs: the pool changes start only when every drive has finished its slow work (copying, formatting)
PUTBACK=0            # 1 when a half-moved drive was put back into the pool it came from
NOROOM=0            # 1 when a drive was left where it is because the drives that stay have no room for its files
PANEL_UNDO=0         # 1 while drives are put back after Stop (typed words are not asked for)
ABORT_IGNORE=0       # 1 while putting a drive back (the Stop request is then not looked at)
POOL_LOCK="${POOL_LOCK:-$STATE_DIR/pool-change.lock}"
ABORT_FILE="${ABORT_FILE:-$STATE_DIR/panel-abort}"           # the Stop button: this file exists = stop as soon as it is safe
BATCH_PID_FILE="${BATCH_PID_FILE:-$STATE_DIR/panel-batch.pid}"
PANEL_ID=""          # set only by `drives panel ...`: the drive (a pool label, or sda) the control panel chose, so the flow does not ask
PANEL_NAME=""        # ... and the new name for rename
WANT_SPARE=0         # --spare: a ready-made array setup also gets a hot spare drive
WANT_CACHE=0         # --cache: a ready-made ZFS setup also gets an SSD read cache
WANT_ENCRYPT=0       # --encrypt: a ready-made array setup is encrypted (key file on the boot drive)
WANT_FIRST=0         # --first-run: the wizard was started by the installer (silent when there is nothing to offer; asks only once)
WIZARD_DEVS=""       # the empty drives the wizard found, one per line: preset_pick_drives uses them instead of asking again
BACKUP_LOCK="${BACKUP_LOCK:-/var/lock/homelab-backup.lock}"
[ "$TEST_MODE" = 1 ] && BACKUP_LOCK="${BACKUP_LOCK_TEST:-$STATE_DIR/backup.lock}"
BUSY_POLL_SECS="${BUSY_POLL_SECS:-30}"
BUSY_MAX_WAIT_SECS="${BUSY_MAX_WAIT_SECS:-21600}"   # wait at most 6 hours for a backup or upload to end

PRESET_TOUCHED=0     # 1 once a ready-made setup has changed anything (a refused one leaves Homepage alone)
STOPPED=""
START_FAILED=""      # containers that would not start again after a change
ROLLED_BACK=0        # 1 once fstab was put back to what it was before the step
NAME_CACHE=""        # a temporary folder of drive names while a look-only command runs (see with_name_cache)
PENDING_NOTE=""      # a sentence for the end when the command stops halfway (for example a drive that left its pool)
FSTAB_SNAP=""
HOLD_HINT=""

