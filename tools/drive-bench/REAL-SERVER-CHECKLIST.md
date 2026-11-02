# Real-server checklist for the ready-made setups

The fake-drive tests prove that the script does what it should: the right commands, in the right order, with the right
checks. They cannot prove that ZFS, mdadm and SnapRAID behave on real drives. This list does that. It is meant for **spare
drives** (old drives or USB sticks of any size), never for the drives that hold your photos and files.

Each step says what to type, what you should see, and what to do if you do not see it. Work through one setup at a time.
Tick the boxes as you go and send me anything that did not match.

## 0. Before you start (once)

- [ ] You have a machine **without any pool**: a second computer, or your server after `sudo drives release`
      (do NOT release the pools of your real server just for this test).
- [ ] The Backup storage is not needed for this test. If it is connected it stays untouched.
- [ ] You have at least 5 spare drives for the biggest tests (3 for RAIDZ1 / RAID 5 and 2 for the small ones are enough to start).
      USB sticks work for a first try, but they are slow.
- [ ] The scripts are installed: `sudo drives version` prints a version, `sudo drives preset` lists 14 setups.
- [ ] Programs: `sudo apt install -y zfsutils-linux mdadm snapraid` (each setup tells you what it is missing).
- [ ] Drives are empty. If one holds old files: `sudo drives wipe`. `sudo drives preset` shows how many empty drives it sees.

## 1. For EVERY setup you try

1. [ ] `sudo drives preset NAME --dry-run` shows the plan (drives, space you can use) and says **DRY RUN**. Nothing changes:
       `sudo drives status` looks the same as before.
2. [ ] `sudo drives preset NAME`: pick the drives, read the plan, type the name, type `ERASE`. It ends with **Done**.
3. [ ] `sudo drives status` shows the drives with the role `array` (ZFS / RAID) or `main`, `backup`, `parity` (pool setups),
       a line `Setup built with sudo drives preset: ...` and, for ZFS and RAID, `Array health:`.
4. [ ] `df -h /mnt/storage` shows about the space the plan promised (a few percent less is normal).
5. [ ] Write a file: `echo hello | sudo tee /mnt/storage/test.txt` and read it back with `cat /mnt/storage/test.txt`.
6. [ ] Copy something big (a few GB) into `/mnt/storage` and check that it finishes without errors.
7. [ ] `sudo drives health` lists every drive of the setup.
8. [ ] **Reboot** (`sudo reboot`). Afterwards `sudo drives status` shows the same setup, healthy, and `/mnt/storage` still has
       your test file. (This is the most important check: it proves the setup starts by itself.)
9. [ ] Pool commands are refused on an array: `sudo drives connect` says it does not apply to an array (ZFS and RAID only).
10. [ ] Take it apart: `sudo drives release` (for ZFS / RAID: type `DESTROY`). `sudo drives preset` then shows all drives as
        empty again, and `findmnt /mnt/storage` prints nothing.

## 2. Extra checks, per kind

### Plain pool, mirror, SnapRAID (`pool`, `mirror`, `snapraid1`, `snapraid2`)
- [ ] `mirror`: after the first night (or run `sudo homelab-backup`) the Backup drive holds a copy of the files.
- [ ] SnapRAID: `sudo drives snapraid status` works, `sudo drives snapraid sync` finishes, and `cat /etc/cron.d/homelab-snapraid`
      shows the 04:00 line.
- [ ] SnapRAID: add a file, run `sudo drives snapraid diff` (it should list the new file), then `sudo drives snapraid sync`.
- [ ] Optional, by hand: SnapRAID can rebuild a lost file with `sudo snapraid -c /etc/snapraid.conf fix -f FILE` (after
      deleting a test file on purpose, following a sync). Replacing a whole dead drive is not automated yet: tell me if you
      want that built.

### ZFS (`zfs-stripe`, `zfs-mirror`, `zfs-raidz1/2/3`)
- [ ] `zpool status tank` says `ONLINE` for the pool and for every drive.
- [ ] `zfs get compression,atime tank` shows `lz4` and `off`.
- [ ] `ls /etc/cron.d/` has `zfsutils-linux` (Ubuntu / Mint do the monthly check) or `homelab-zfs-scrub`.
- [ ] `sudo zpool scrub tank`, then `zpool status tank` ends with `scrub repaired 0B ... with 0 errors`.
- [ ] Not for stripe: **pretend a drive died.** Power off, unplug one drive, power on. `sudo drives status` shows the
      drive as MISSING and the pool as `DEGRADED`, and `/mnt/storage` still works. Plug it back: `sudo zpool online tank DRIVE`.
- [ ] Replacing a dead drive is done by hand for now: `sudo zpool replace tank OLD NEW` (look up the names in `zpool status`).

### RAID with mdadm (`md-raid0/1/5/6/10`)
- [ ] `cat /proc/mdstat` shows the array (`active`) and, at first, a progress bar: it builds in the background. You can
      already use it.
- [ ] `sudo mdadm --detail /dev/md/homelab` shows the level, the drives and the state (`clean` or `active, resyncing`).
- [ ] `grep homelab /etc/mdadm/mdadm.conf` shows the ARRAY line, and `grep /mnt/storage /etc/fstab` shows one ext4 line.
- [ ] Wait for the build to finish (`cat /proc/mdstat`), then reboot as in step 8.
- [ ] Not for RAID 0: **pretend a drive died.** `sudo mdadm /dev/md/homelab --fail /dev/sdX --remove /dev/sdX`; the array stays
      usable (`degraded`). Add it back with `sudo mdadm /dev/md/homelab --add /dev/sdX` and watch it rebuild.

## 3. What to send me

For every step that did not match: the exact command, what you expected, and what you got. For a failed build also send
`sudo tail -50 /var/log/homelab-drives.log`.

## 4. Known limits (on purpose, for now)

- `drives replace`, `recover`, `connect`, `disconnect` and the other pool commands are refused on a ZFS / RAID array. Use the
  tools of the array (`zpool`, `mdadm`) to replace a drive; `sudo drives status` shows what is wrong.
- A ZFS / RAID setup becomes the Main storage. It cannot be built while the Main storage already has drives.
- All drives of a RAID setup should be the same size: a bigger drive only uses as much space as the smallest one.
- `sudo drives release` on an array deletes the array **and its files**. The Backup storage is not touched.
