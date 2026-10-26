# Storage setup notes (build log)

> **Historical record.** These are my notes from setting up the storage on the current server, with the real command output I saw (host names and addresses replaced). The up-to-date, step-by-step version is the [storage guide](../storage.md); use that to build, and this file to see what the commands printed and what went wrong along the way.

Goal: the data drives are joined into a pool at `/mnt/storage` and keep the same labels, formats and paths after a reboot or a disconnect. Each service has its own folder in the pool, Homepage, FileBrowser, Immich and Nextcloud all see the pool correctly, and a daily backup copies it to a separate place.

**How it is laid out today**

- The Toshiba is the first drive of the main pool: ext4, label `MAIN1`, mounted by UUID at `/mnt/disks/MAIN1`. The mergerfs pool on top of it is mounted at `/mnt/storage`, the same path the stacks always used.
- The backup pool `/mnt/backup` (drive label `BACKUP1`) does not exist yet, because there is no backup drive. Until there is one, the daily backup goes to `/home/your-username/750GB_HDD/backup-interim` on the boot drive.
- Three tools manage it: `sudo drives` (menu and status), `sudo hdd-recover` (remount and restart) and `sudo homelab-backup` (daily copy). A fourth, `homelab`, only reads information and shows a cheat sheet and the status at every login ([Step 9](#step-9-the-cheat-sheet-at-login)). Their source is in the repository's [`scripts/`](../../scripts/) folder, and the [storage guide](../storage.md) explains each option.

**Why ext4:** it's a Linux filesystem, so Docker and databases get proper file permissions, and it isn't locked as "dirty" when the drive is unplugged the way NTFS can be.

## Step 1: Install the tools and scripts

```bash
uname -r
timedatectl | grep "Time zone"
sudo apt update && sudo apt install -y mergerfs rsync parted hdparm smartmontools
mergerfs --version | head -1
```

On my machine the kernel was `7.0.0-38-generic` (6.6 or newer is best), the time zone was `America/New_York (EDT, -0400)`, and `apt` installed one new package, `mergerfs 2.33.5-1ubuntu2`, from Ubuntu's `noble/universe` repository. The version command printed `mergerfs version: 2.33.5`. The other four packages were already installed.

I first copied the scripts to the server from a zip file with VS Code (Remote-SSH). They are now in the repository's `scripts/` folder. Check them and install two of them (the third comes in Step 6, and `homelab` in Step 9):

```bash
cd ~/homelab-drives
sha256sum -c SHA256SUMS
grep -c $'\r' drives hdd-recover homelab-backup
sudo install -m 755 drives /usr/local/sbin/drives
sudo install -m 755 homelab-backup /usr/local/sbin/homelab-backup
sudo drives version
sudo drives status
```

Every checksum line printed `OK` (four lines then; `SHA256SUMS` has five now that `homelab` is in it, see Step 9), and the line-ending count was `0` for all three files (Windows line endings would stop a script from running). `drives version` printed `drives 1.0`. The first `status`, before anything was converted, looked like this:

```text
=== Pools ===
main     /mnt/storage   mounted (ext4)  61GB used of 916GB
backup   /mnt/backup    NOT MOUNTED
Note: main storage is still one plain drive. Menu option 5 converts it into a pool.

=== Pool drives ===
LABEL     ROLE     DEVICE       SIZE      USED      SMART     STATE
(no drives in a pool yet)

=== Other drives ===
/dev/sda  931.5G  TOSHIBA MQ01ABD100  [usb]   current data drive (plain, not in a pool yet)
/dev/sdb  698.6G  Hitachi HTS547575A9E384  [sata]   boot/system drive (never touched)

=== Last backup ===
no backup has run yet
```

## Step 2: Add the main drive

**A new or blank drive:** run `sudo drives`, choose **2** (Connect a new drive), pick the drive, choose **Main storage**, then type the device name and `ERASE`. The script formats it as ext4 with the label `MAIN1`, locks the empty mount points, adds the `/etc/fstab` lines below, mounts the drive and the pool, and sets the power level. **This erases the drive.** Practise first in test mode (see Phase 15).

**My case: a drive already mounted at `/mnt/storage`** (the Toshiba, ext4, with its files in place). This keeps every file where it is:

```bash
sudo drives adopt
```

It printed what it was about to do, and I answered `y`:

```text
This converts your current data drive into the first drive of the main pool.
  Drive:        /dev/sda  931.5G  TOSHIBA MQ01ABD100  [usb]
  Now:          mounted directly at /mnt/storage (label 'STORAGE')
  After:        mounted at /mnt/disks/MAIN1 (label MAIN1), and /mnt/storage becomes the pool
  Your files are not moved or copied. Containers using /mnt/storage will be stopped for a minute.
Continue? [y/N]: y
Stopping containers that use this storage: filebrowser-filebrowser-1 homepage immich_server nextcloud nextcloud_cron
Starting containers: filebrowser-filebrowser-1 homepage immich_server nextcloud nextcloud_cron

Done. /mnt/storage is now a pool containing MAIN1. Check: sudo drives status
```

It saved the old `/etc/fstab` as `/etc/fstab.bak-drives-<date>`, commented out the old `/mnt/storage` line and added the two new ones. My `/etc/fstab` now has:

```text
# removed by drives 2026-10-22: UUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee  /mnt/storage  ext4  defaults,noatime,nofail,x-systemd.device-timeout=10  0  2
UUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee  /mnt/disks/MAIN1  ext4  defaults,noatime,nofail,x-systemd.device-timeout=10  0  2
/mnt/disks/MAIN1 /mnt/storage fuse.mergerfs allow_other,cache.files=off,category.create=mfs,moveonenospc=true,dropcacheonclose=true,nofail,fsname=mergerfs-main,x-systemd.requires-mounts-for=/mnt/disks/MAIN1 0 0
```

The pool type must be `fuse.mergerfs`. In my testing, plain `mergerfs` rejected `nofail`. The storage guide explains each pool option in [storage guide, step 4](../storage.md#4-add-the-first-main-drive). Check it, one command at a time (`findmnt` prints nothing if you give it two paths, see [A12](../troubleshooting.md#a12-findmnt-prints-nothing-when-given-two-paths)):

```bash
findmnt /mnt/storage
findmnt /mnt/disks/MAIN1
sudo drives status
```

```text
TARGET       SOURCE        FSTYPE        OPTIONS
/mnt/storage mergerfs-main fuse.mergerfs rw,relatime,user_id=0,group_id=0,default_permissions,allow_other
TARGET           SOURCE    FSTYPE OPTIONS
/mnt/disks/MAIN1 /dev/sda1 ext4   rw,noatime
```

`status` showed `main /mnt/storage mounted (fuse.mergerfs) 61GB used of 916GB` and `MAIN1 main /dev/sda1 916GB 61GB PASSED connected`.

**Make Docker wait for the pool at boot.** This is the same file as before. `/mnt/storage` is still `mnt-storage.mount` to `systemd`, so it needed no change:

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
printf '[Unit]\nWants=mnt-storage.mount\nAfter=mnt-storage.mount\n' | sudo tee /etc/systemd/system/docker.service.d/wait-for-hdd.conf
sudo systemctl daemon-reload
```

Without this, containers can start before the pool is mounted.

## Step 3: Create a folder for each service

```bash
sudo mkdir -p /mnt/storage/immich /mnt/storage/filebrowser
sudo chown -R your-username:your-username /mnt/storage
sudo mkdir -p /mnt/storage/nextcloud
sudo chown -R 33:33 /mnt/storage/nextcloud
mkdir -p /home/your-username/nextcloud/html /home/your-username/nextcloud/db
mkdir -p /home/your-username/immich/postgres
mkdir -p /home/your-username/homepage-config
mkdir -p /home/your-username/750GB_HDD
sudo mkdir -p /opt/adguard-docker/conf /opt/adguard-docker/work
```

UID 33 is the user Nextcloud runs as inside its container (it shows up as `www-data` in `ls -la`). Keep the folders separate, and don't point FileBrowser at `/mnt/storage` itself, or you could delete Immich's files by accident.

## Step 4: Point each service at its folder

| Service | Where it points | Folder |
| :--- | :--- | :--- |
| Immich | Environment variable `UPLOAD_LOCATION` | `/mnt/storage/immich` |
| Immich database | Environment variable `DB_DATA_LOCATION` | `/home/your-username/immich/postgres` (boot drive) |
| FileBrowser | Volume line, shown as `/srv/hdd` | `/mnt/storage/filebrowser` |
| Nextcloud | Volume line, shown as `/data` | `/mnt/storage/nextcloud` |
| Homepage | Volume line and the `widgets.yaml` disk list | `/mnt/storage` |

**Immich:** environment variables in the Portainer stack:

```text
UPLOAD_LOCATION=/mnt/storage/immich
DB_DATA_LOCATION=/home/your-username/immich/postgres
TZ=America/New_York
IMMICH_VERSION=release
DB_PASSWORD=your-own-key
DB_USERNAME=postgres
DB_DATABASE_NAME=immich
```

**FileBrowser:** the volumes in its stack:

```yaml
    volumes:
      - "/home/your-username/750GB_HDD:/srv/750GB_HDD"
      - "/mnt/storage/filebrowser:/srv/hdd"
      - filebrowser_data:/database
```

**Nextcloud:** the data folder and its volumes. The data folder is set once with `NEXTCLOUD_DATA_DIR: /data` and can't be changed after the first install:

```yaml
    environment:
      NEXTCLOUD_DATA_DIR: /data
    volumes:
      - /home/your-username/nextcloud/html:/var/www/html
      - /mnt/storage/nextcloud:/data
```

**Homepage:** the volumes in its stack, then the disk list in `widgets.yaml`:

```yaml
    volumes:
      - /home/your-username/homepage-config:/app/config
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /:/host:ro
      - /mnt/storage:/mnt/storage:ro
```

```yaml
- resources:
    label: Drives
    disk:
      - /
      - /mnt/storage
    network: true
```

## Step 5: Drive power settings and cron lines

Laptop drives park their heads aggressively at the default power setting. `drives power` changes it on every pool drive, and a cron line keeps it that way after a reboot:

```bash
sudo drives power
sudo hdparm -B /dev/sda
sudo hdparm -C /dev/sda
sudo crontab -e
```

`drives power` sets `hdparm -B 254 -S 0` on main drives (least head parking, never spin down) and `hdparm -B 254 -S 120` on backup drives (the same, and spin down after 10 minutes idle, since `120 x 5 seconds` is 10 minutes). It printed:

```text
Power settings applied (main drives never sleep, backup drives sleep after 10 minutes idle).
Some USB adapters ignore these commands. That is harmless.
```

`hdparm -B` printed `APM_level      = 254`, and `hdparm -C` printed `drive state is:  active/idle`. The `-S` value can't be read back, so `-C` after a long idle period is the only way to see whether a drive sleeps. The drive was awake, which is what a main drive should be. I have not been able to test the backup drives' sleep setting, because there is no backup drive yet. Some USB adapters ignore it.

My root crontab now has these lines. The first re-applies the settings to every pool drive 60 seconds after every boot. The second logs the main drive's head-parking count each morning (optional). The third sets the boot drive, which it finds by the partition mounted at `/boot/efi`. The fourth is the daily backup from Step 7. Don't type a drive letter into these lines: on my machine the Toshiba became `sda` and the Hitachi `sdb` after a reboot, which broke an earlier version of the boot-drive line that said `/dev/sda`.

```cron
@reboot sleep 60 && /usr/local/sbin/drives power >/dev/null 2>&1
0 6 * * * echo "$(date +\%F) $(smartctl -A -d sat /dev/disk/by-label/MAIN1 | awk '/Load_Cycle/ {print $10}')" >> /var/log/loadcycles.log
@reboot sleep 60 && /usr/sbin/hdparm -B 254 "/dev/$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)")"
0 6 * * * /usr/local/sbin/homelab-backup
```

The old versions of the first two lines said `by-label/STORAGE`. Phase 15 shows the command that changed them.

## Step 6: The recovery command

Containers keep the view of the drive they had when they started. After an unplug, they need a restart. `hdd-recover` is now a one-line wrapper that calls `drives recover`:

```bash
sudo install -m 755 ~/homelab-drives/hdd-recover /usr/local/bin/hdd-recover
sudo hdd-recover
```

`drives recover` looks at what each container has mounted under `/mnt/storage`, `/mnt/backup` and `/mnt/disks`, stops those containers, unmounts the pools and drives, mounts them again from `/etc/fstab`, re-applies the power settings and starts the containers. The old script had a fixed list of five container names. This one finds them by itself, so a new service is picked up with no edit. On my server it printed:

```text
Stopping containers that use this storage: filebrowser-filebrowser-1 homepage immich_server nextcloud nextcloud_cron
Starting containers: filebrowser-filebrowser-1 homepage immich_server nextcloud nextcloud_cron
Recovered.
```

If a main drive isn't found, it prints `Drive not found. Check the cable.` with the drive's label and leaves the containers stopped on purpose. A missing backup drive only gives a warning. The old script is saved on the server as `/usr/local/bin/hdd-recover.old`, and its text is in Phase 15.

## Step 7: The daily backup

`homelab-backup` dumps the Nextcloud database, copies the main pool with `rsync` (a file you delete or replace is moved into `_deleted/<date>/` and kept for 30 days), copies the boot drive's config files, and deletes dumps and `_deleted` folders older than 30 days. It writes to `/mnt/backup` when that pool is mounted. Until then it uses the folder named in `DEST_FALLBACK`:

```bash
sudo tee /etc/homelab-backup.conf >/dev/null <<'EOF'
DEST_FALLBACK="/home/your-username/750GB_HDD/backup-interim"
EOF
df -h / /mnt/storage
sudo nohup /usr/local/sbin/homelab-backup >/dev/null 2>&1 &
sudo tail -f /var/log/homelab-backup.log
```

The boot drive had 606 GB free before the backup, and the pool holds 61 GB. The first run took 1420 seconds (about 24 minutes) and the log ended like this:

```text
2026-10-22 19:04:46 start
2026-10-22 19:04:46 backup pool not mounted, using the fallback folder /home/your-username/750GB_HDD/backup-interim
2026-10-22 19:04:53 database dump saved: /home/your-username/750GB_HDD/backup-interim/db-dumps/nextcloud-2026-10-22.sql.gz
2026-10-22 19:27:04 main storage copied
2026-10-22 19:28:26 configs copied
2026-10-22 19:28:26 finished: OK in 1420s
```

While it ran, `du -sh` on the `main` folder grew from 8.2G to 17G to 21G, and in the end both folders showed `61G`. `sudo drives status` then showed `2026-10-22 19:28  result: OK  destination: /home/your-username/750GB_HDD/backup-interim  took: 1420s`. The folder holds `main`, `boot-configs` (1.1 GB, with `etc`, `home`, `opt`, `usr`, `var` and `root-crontab.txt`), `db-dumps` (the dump was 2.0 MB) and `_deleted`. To watch whether it is still running, use `pgrep -af homelab-backup` (see [A15](../troubleshooting.md#a15-pgrep-shows-nothing-while-the-backup-is-running)). Then the schedule, added to root's crontab with `sudo crontab -e`:

```cron
0 6 * * * /usr/local/sbin/homelab-backup
```

**Guards.** The backup refuses to run, and logs why, if the main pool isn't mounted or looks empty (so a missing drive can't empty the backup), if the backup target isn't mounted and no fallback is set, or if the target has less than 20 GB free (or less than the pool's size plus 20 GB for the first run).

**The weakness for now.** The interim backup is on the boot drive. It protects against a failed data drive, but not against a failed boot drive or a lost machine, and it adds about 63 GB to the boot drive's root filesystem (107 GB used with it, 44 GB without). When a backup drive is connected (`sudo drives`, then **2**, **Backup storage**), delete the `DEST_FALLBACK` line, run `sudo homelab-backup`, and then remove the interim folder.

**Restore.** Copy files out of the backup, and never edit them there, because the next run overwrites a changed file. With the pool as the target, the paths start with `/mnt/backup` instead of the interim folder:

```bash
ls /home/your-username/750GB_HDD/backup-interim/_deleted/
sudo cp -a /home/your-username/750GB_HDD/backup-interim/main/nextcloud/some-folder /mnt/storage/nextcloud/
docker exec -u www-data nextcloud php occ files:scan --all
```

**Extra folders.** The list of boot-drive folders that the backup copies is `CONFIG_PATHS` at the top of `homelab-backup`. Speedtest Tracker's data folder is not in it, because the container used an anonymous volume when the list was written ([B6](../troubleshooting.md#b6-a-container-starts-empty-after-update-the-stack)). I don't edit the script. I add the folder from the settings file, which is read after the defaults:

```bash
echo 'CONFIG_PATHS+=(/home/your-username/speedtest-tracker)' | sudo tee -a /etc/homelab-backup.conf
cat /etc/homelab-backup.conf
```

Use `+=`. A plain `=` would replace the whole list and the backup would stop copying Homepage, AdGuard, Nextcloud and the rest. **Verify** after the next backup (the 6:00 run, or `sudo homelab-backup` by hand):

```bash
sudo drives status
sudo ls /home/your-username/750GB_HDD/backup-interim/boot-configs/home/your-username/
```

The status should say `OK`, and the listing should include `speedtest-tracker`. I gave myself this command on 2026-10-23 and have not yet checked the result of a backup after it.

## Step 8: Verify it

Start the Immich, FileBrowser, Nextcloud and Homepage stacks, then check that each container sees the pool:

```bash
findmnt /mnt/storage
docker exec immich_server df -h /data
docker exec filebrowser-filebrowser-1 df -h /srv/hdd /srv/750GB_HDD
docker exec nextcloud df -h /data
docker exec homepage df -h /mnt/storage
```

Every container should show the filesystem `mergerfs-main` at about 916G (FileBrowser's `/srv/750GB_HDD` line shows the boot drive's `vgmint-root`). After the conversion mine showed:

```text
Filesystem      Size  Used Avail Use% Mounted on
mergerfs-main   916G   61G  855G   7% /data
```

FileBrowser and Homepage, whose `df` prints a slightly different layout, showed `mergerfs-main 915.8G 60.9G 854.9G 7%`. If one shows the boot drive instead, that container was started before the pool was mounted, so restart it. Then run these tests:

- **Reboot:** run `sudo reboot`. After about three minutes, run `findmnt /mnt/storage`, `findmnt /mnt/disks/MAIN1` and `docker ps --format "table {{.Names}}\t{{.Status}}"`. The pool and the drive should be mounted and the containers up with no help from you. My result is in Phase 15.
- **Unplug:** unplug the drive, wait a few seconds, plug it back in and run `sudo hdd-recover`. You should see `Recovered.` I tested this with fake drives, but I have not repeated it on the real drive since it became a pool.
- **Lock test (optional):** with the stacks stopped, run `sudo umount /mnt/storage`, then `touch /mnt/storage/test`. It should say `Operation not permitted`, which shows nothing can write to the empty folder. Then run `sudo mount /mnt/storage` and start the stacks again. I ran this test on the single drive. The pool uses the same locked folders, but I haven't repeated it since. `lsattr` can't show the lock while the drive is mounted, because the flag sits on the hidden folder underneath.

## Step 9: The cheat sheet at login

`homelab` is a read-only script. It prints the commands from this guide, grouped by job, and a live status block, so I don't have to memorise them. I run it from `~/.bashrc`, so it shows in every new terminal: a plain SSH session and the terminal inside VS Code Remote-SSH. The storage guide explains it in [storage guide, step 14](../storage.md#14-the-cheat-sheet-at-login).

**1. Install it,** from inside the folder that holds the files. This is the step where I first made a mistake: I ran `install` from my home folder and got `install: cannot stat 'homelab'` ([A16](../troubleshooting.md#a16-install-says-cannot-stat-when-installing-a-script)).

```bash
cd ~/homelab-drives
sha256sum -c SHA256SUMS
sudo install -m 755 homelab /usr/local/bin/homelab
homelab version
```

```bash
drives: OK
homelab-backup: OK
hdd-recover: OK
homelab-backup.conf.example: OK
homelab: OK
homelab 1.0
```

`SHA256SUMS` has five lines now: the four from Phase 15 (the old fifth line, `GUIDE.md`, is gone) and `homelab`. If you change any of the files, make the list again from inside the folder with `sha256sum drives homelab-backup hdd-recover homelab-backup.conf.example homelab > SHA256SUMS`, and check it with `sha256sum -c SHA256SUMS`.

**2. Run it once by hand:**

```bash
homelab
```

```text
Home lab  pc  up 51 minutes

Storage
  sudo drives                        menu: connect, disconnect or check drives
  sudo drives status                 pools, drives, SMART health, last backup
  sudo hdd-recover                   after an unplug or power cut: remount, restart containers
  sudo drives power                  re-apply the drive power settings
Backup
  sudo homelab-backup                run the backup now (about 20 minutes)
  sudo tail -f /var/log/homelab-backup.log
                                     watch the backup (Ctrl+C to leave)
Checks
  docker ps                          what is running (add --format "table {{.Names}}\t{{.Status}}")
  findmnt /mnt/storage               is the pool mounted (one path per command)
Docs  /home/your-username/My-Home-Lab-
  homelab docs                       sections of the README and the guides in docs/
  git -C ~/My-Home-Lab- pull         refresh them from GitHub

Status
  Main pool       mounted, 61G used of 916G
  Backup pool     not connected (the backup goes to the boot drive)
  Last backup     2026-10-22 19:28  OK  (7 h ago)
  Containers      16 of 16 running
  Boot drive      18% used, 536G free
```

The first time, the Containers line was red because `portainer-old`, the spare container kept after the Portainer update ([Portainer](../updating.md#portainer)), was stopped on purpose. I changed the script to ignore a stopped container whose restart policy is `no`, so only containers that should be running count.

**3. Get the documents on the server,** so `homelab docs` has something to list. The first try failed with `Could not resolve host: github.com`, which turned out to be a DNS problem and not a mistake in the command ([F6](../troubleshooting.md#f6-the-server-cannot-look-up-names-after-a-tailscale-update)). After F6 was fixed:

```bash
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git ~/My-Home-Lab-
homelab docs
```

`homelab docs` lists the `##` headings of the README and of every guide in `docs/`, with their line numbers.

**4. Show it at login.** Back up `~/.bashrc`, then add the block at the end. The quotes around `'EOF'` stop the shell from changing the text:

```bash
cp ~/.bashrc ~/.bashrc.bak-2026-10-23
cat >> ~/.bashrc <<'EOF'

# >>> homelab login display >>>
if [[ $- == *i* ]] && [ -t 1 ] && command -v homelab >/dev/null 2>&1; then
  timeout 20 homelab
fi
# <<< homelab login display <<<
EOF
tail -8 ~/.bashrc
```

The `timeout 20` in front of `homelab` is a safety net: if Docker or a drive hangs, the sheet gives up after 20 seconds and the prompt still appears. The three conditions in the `if` are: an interactive shell, output going to a terminal, and the command existing. Together they keep `scp`, `sftp`, cron jobs and VS Code's background shell quiet.

**5. Test it in both places.** Open a new VS Code terminal (**Terminal**, then **New Terminal**) and a new SSH session from PowerShell. Both must show the cheat sheet. The first version of my block failed in VS Code ([H5](../troubleshooting.md#h5-the-cheat-sheet-does-not-appear-in-the-vs-code-terminal)). The block above is the fixed one: it needs no variable.

**Undo,** if you want the old `.bashrc` back (only if you changed nothing else in it since):

```bash
cp ~/.bashrc.bak-2026-10-23 ~/.bashrc
```

## Step 10: Replace a dead drive

**Status: written and tested on fake drives, and rehearsed with a USB stick on 2026-10-23. Not yet used on my real drive.** This is the part that lets me recover when the Toshiba (`MAIN1`) dies. The storage guide explains it in [storage guide, step 15](../storage.md#15-replace-a-dead-drive). `drives` is version 1.1 from here on, and `homelab` was updated too (its Main pool line now mentions `sudo drives replace`, and the cheat sheet has a line for it).

**What I am relying on.** My main pool has one drive, so if it dies the whole pool is gone and every service stops. The only copy of my files is the daily backup in `/home/your-username/750GB_HDD/backup-interim` on the boot drive. `sudo drives replace` makes a new drive take the name `MAIN1`, shows what is missing, copies only the missing files from that backup, checks them, and then starts the containers. The new drive needs room for the 61 GB that are in the pool today, and it should be at least as big as I want the pool to be.

**1. Put the new version on the server.** Copy `drives`, `homelab` and `SHA256SUMS` into the folder (`~/homelab-drives`, or `~/My-Home-Lab-/scripts` after a `git pull`), then, inside that folder:

```bash
cd ~/homelab-drives
sha256sum -c SHA256SUMS
grep -c $'\r' drives homelab
sudo install -m 755 drives /usr/local/sbin/drives
sudo install -m 755 homelab /usr/local/bin/homelab
sudo drives version
homelab version
```

All five checksum lines must say `OK`, both line-ending counts must be `0`, and the versions must be `drives 1.1` and `homelab 1.0`. Then check that nothing else changed:

```bash
sudo drives status
```

**2. Rehearse it** with the USB stick and fake drives before a real drive dies. The numbered steps are in [storage guide, step 15](../storage.md#15-replace-a-dead-drive), under "Rehearse it with a USB stick". **Done on 2026-10-23, and it passed.** What I did and what I saw, step by step:

**2.1 Two fake drives, stick still unplugged.** `sudo DRIVES_TEST=1 drives test-setup 2 1G` made `/dev/loop0` (`disk1.img`) and `/dev/loop1` (`disk2.img`). Then I ran `sudo DRIVES_TEST=1 drives connect` twice. The list showed only the two fake drives, I chose **Main storage**, typed the drive name and `ERASE`, and it ended with `Done. TMAIN1 is connected to the main storage (/mnt/test-main).` and the same for `TMAIN2`. The status then showed:

```text
main     /mnt/test-main mounted (fuse.mergerfs)  48KB used of 1.9GB
LABEL     ROLE     DEVICE       SIZE      USED      SMART     STATE
TMAIN1    main     /dev/loop0p1 972MB     24KB      skipped (test mode) connected
TMAIN2    main     /dev/loop1p1 972MB     24KB      skipped (test mode) connected
/dev/sda  931.5G  TOSHIBA MQ01ABD100  [usb]   not connected to a pool
```

The last line is only how test mode sees my real Toshiba: it knows nothing about my real pool. The real pool was not touched.

**2.2 Practice files and a practice backup.** Three 50 MB random files in `/mnt/test-main/photos`, copied with `rsync -a` to `/var/tmp/practice-backup/main`, checksums saved in `~/practice-sums.txt`. The pool put `file1.bin` on `TMAIN1` and `file2.bin` and `file3.bin` on `TMAIN2` (51 MB and 101 MB used), so losing `TMAIN2` would lose two of the three files.

**2.3 Pretend `TMAIN2` died.** `umount -l /mnt/test-main`, `umount -l /mnt/test-disks/TMAIN2`, `losetup -d /dev/loop1`. The status showed:

```text
main     /mnt/test-main NOT MOUNTED
TMAIN1    main     /dev/loop0p1 972MB     51MB      skipped (test mode) connected
TMAIN2    main     -            -         -         -         MISSING (cable? then: sudo hdd-recover. Dead? sudo drives replace)
```

**2.4 Plug in the stick and find it.** `lsblk` listed a new `sdc`, 7.2G, `usb`, with one partition labelled `TMAIN1` (left over from an earlier practice). `dmesg` showed `USB DISK 2.0 ... Attached SCSI removable disk`. My Toshiba (`sda`, 931.5G) and the boot drive (`sdb`, 698.6G) were unmistakably different. I did not unplug the Toshiba.

**2.5 The replace.** `sudo DRIVES_TEST=1 DRIVES_RESTORE_SRC=/var/tmp/practice-backup drives replace`. I chose `TMAIN2`, answered `y` to the no-backup-record warning, chose the stick (the only real drive in the list), typed its name and `ERASE`, saw the preview and typed `RESTORE`. The desktop had auto-mounted the stick at `/media/your-username/TMAIN1`; the tool handled that. What it printed (the stick's serial number left out):

```text
Pool drives that cannot be found:
  1) TMAIN2  (main)  not found
Which drive is dead? 1

TMAIN2 will be replaced by a new drive that gets the same name (TMAIN2).
The files that were on the dead drive are copied back from the backup. Only missing files are copied.
Backup copy to restore from: /var/tmp/practice-backup/main
WARNING: There is no record of a backup run. I cannot tell how old this copy is.
Use this copy anyway? [y/N]: y
Measuring the backup copy (this can take a minute)...
The backup holds about 100MB more than the remaining main drives. The new drive should be larger than that.
  1) /dev/sdc   7.2G  USB DISK 2.0  [usb]
!! ERASE WARNING !!
Everything on /dev/sdc will be permanently deleted.
TMAIN2 is in place and the main pool is mounted.

Missing from the pool but present in the backup: 2 files, 100MB
First 20:
  photos/file2.bin
  photos/file3.bin
Type RESTORE (capitals) to copy these 2 files: RESTORE
Copying (the services stay stopped)...
Checking that every file in the backup is now in the pool...
Verified: all 2 restored files, and every other file in the backup, are in the pool.
Done. If the old drive ever turns up again, do not plug it in next to the new one: both are called TMAIN2.
```

**2.6 Checked by hand.** `sha256sum -c ~/practice-sums.txt` printed `OK` for `file1.bin`, `file2.bin` and `file3.bin`. The status showed `TMAIN2` on `/dev/sdc1` (7.0GB, 101MB used) and the pool at 151MB used of 8.0GB. `ls` showed `file2.bin` and `file3.bin` on the stick, 52,428,800 bytes each.

**2.7 Cleanup.** `sudo DRIVES_TEST=1 drives test-cleanup` printed `Test setup removed.` The real `sudo drives status` was exactly as before (`MAIN1` connected, 61GB used of 916GB, last backup 06:00 OK). `findmnt /mnt/storage` showed the pool still mounted. All 16 containers were running, with the longest at 11 hours, so nothing restarted at any point. The stick stayed formatted as `TMAIN2` with no mount point; I unplugged it afterwards.

**What it showed.** The whole flow works on a real USB drive: it detects the dead drive, refuses to guess a backup without asking, only lists drives that are safe to erase, previews exactly what it will copy, verifies the copy, and the files match their checksums. Two small things, neither a bug: the stick's old label and the desktop auto-mount did not matter, and test mode's status lists my real Toshiba as "not connected to a pool". What is still untested is a real failed drive and the real backup folder on the boot drive as the source.

**3. What a real failure looks like, and what I will do.**

1. `homelab` shows `Main pool NOT MOUNTED` in red, the containers are down, and `sudo drives status` lists `MAIN1` as `MISSING`.
2. Check the cable and the adapter's power, plug it in again and run `sudo hdd-recover`. If it comes back, stop here.
3. If the drive is dead, plug in the new drive, check it with `lsblk -o NAME,SIZE,MODEL,TRAN`, and run `sudo drives replace`.
4. Answer the questions, read the preview and type `RESTORE`.
5. After the check says `Verified`, look at Immich, Nextcloud and FileBrowser, run `docker exec -u www-data nextcloud php occ files:scan --all`, and run `sudo homelab-backup`.

**The tests.** I ran 58 automatic checks against fake drives (loop devices over image files) with a fake `docker` command that records which containers were stopped and started:

| Scenario | What I checked |
| --- | --- |
| The only main drive dies | The new drive gets the label `MAIN1` and a new UUID in `/etc/fstab` (the old line is kept as a comment). Every file is identical afterwards (`sha256sum`), including symlinks, names with spaces and accents, and nested folders. The containers are stopped first and started only after the check. |
| One of two main drives dies | Only the missing files come back. A file I had changed on the surviving drive after the backup was not overwritten, a file created after the backup was untouched, and a file I had deleted after the backup came back (documented behaviour). |
| I type something other than `RESTORE` | Nothing is copied, the containers stay stopped, and `sudo drives restore` finishes the job later. Running it again says `Nothing is missing`. |
| A backup drive dies | The new drive gets the label `BACKUP1`, the pool mounts, the main data is untouched, and the backup run is offered. |
| Refusals | No missing drive, no backup found, a failed last backup, a wrong device name, `ERASE` not typed, a drive that is too small, and not enough free space all stop with the fstab unchanged and (where it applies) the drive not formatted. |
| Two main drives die | The first replacement leaves the pool down and the containers stopped, the second brings it up and restores everything. |

**One limit I found while testing.** In my fake-drive test, two hard-linked files showed different inode numbers through the mergerfs pool, so `rsync -H` copied them into the backup as two separate files. A restored hard link would then be a normal copy. I have not checked whether any of my real files are hard-linked.

**Undo for the install,** if you want the old version back: install the old `drives` from the repository history, or from `/home/your-username/homelab-drives` if you still have it. The old version does not have the `replace` command and works as before.

## Step 11: Rebuild the server from GitHub and the backup

**Status: written on 2026-10-23 from the design and checked on a fake file tree. Not rehearsed on a real rebuild.** The maintenance guide has the full procedure with explanations ([Rebuild the server after the boot drive dies](../maintenance.md#rebuild-the-server-after-the-boot-drive-dies)). This step is the same procedure with my real values, and the list of what I have to fix first.

**What I found when I checked it on paper**

1. **Until `BACKUP1` exists, the backup dies with the boot drive.** The backup sits in `/home/your-username/750GB_HDD/backup-interim`, on the same drive as the databases and the app folders. If that drive dies, I lose the Nextcloud database dump, the Nextcloud app folder (`config.php`), AdGuard Home's settings and the Beszel and FileBrowser data. Not lost: all photos and files (they are on `MAIN1`) and the Immich database, because Immich writes its own dumps to `/mnt/storage/immich/backups`. Until the backup drive is connected, I copy the `db-dumps` and `boot-configs` folders of the interim backup to another computer once a month.
2. **A full copy of the saved configs would break the new server.** The backup holds the old `/etc/fstab`. Copying it back makes the new install unbootable, which is why Step 6 of the maintenance guide leaves it out (with the scripts and the Docker data). I tested the exclusions on a fake tree: the new `fstab` and the new `drives` stayed, the Homepage, Nextcloud and AdGuard files came back, the Homepage files kept their owner (1000), and `root-crontab.txt` did not land in `/`.
3. **The stack names matter.** The Beszel and FileBrowser data come back by their volume names, `beszel_beszel_data` and `filebrowser_filebrowser_data`. Before I need this, I run this once and keep the output:

```bash
docker ps --format '{{.Names}}   {{.Label "com.docker.compose.project"}}'
```

The second column is the stack name each container belongs to.

<!-- markdownlint-disable-next-line MD029 -->
4. **The secrets are in no file.** Where each one comes from: the Nextcloud database password is also inside `/home/your-username/nextcloud/html/config/config.php` (`dbpassword`), so it can be read back after the restore of that folder; everything else (Nextcloud admin, Immich database user and password, the Homepage widget keys, the Speedtest Tracker `APP_KEY`) must be in my password manager. **To do: check that each of them is there.**
<!-- markdownlint-disable-next-line MD029 -->
5. **The Tailscale name.** Delete the old `pc` in the admin console before the new server joins, or it becomes `pc-1` and `your-tailnet.ts.net` addresses stop matching (Nextcloud's `OVERWRITEHOST`, Homepage's allowed hosts, the phone).

**The procedure with my values**

| Step | What I do |
| :--- | :--- |
| 1 | Delete the dead `pc` in the Tailscale admin console. |
| 2 | Install Linux Mint with user `your-username` and host name `pc`. SSH, and the router reservation for 192.168.X.X (new network card: update the reservation). |
| 3 | Docker and Tailscale (`tailscale up` only), and the `wait-for-hdd.conf` file. No stacks yet. |
| 4 | `git clone`, `sha256sum -c SHA256SUMS` (five `OK`), install `drives`, `homelab-backup`, `hdd-recover`, `homelab`. |
| 5 | `sudo drives` → 2 → the Toshiba → Main storage → **Keep the data and add the drive as it is**. Check `ls /mnt/storage`. Make the folders under `/home/your-username` and `/opt`, then the two cron lines and `/etc/homelab-backup.conf` (`DEST_FALLBACK` only while there is no `BACKUP1`, and `CONFIG_PATHS+=(/home/your-username/speedtest-tracker)`). |
| 6 | `BK=/home/your-username/750GB_HDD/backup-interim` (later `BK=/mnt/backup`), then the `rsync -aHn` preview, then the real `rsync -aH`, both with `--exclude=/etc/fstab --exclude=/usr/local/ --exclude=/root-crontab.txt --exclude=/var/lib/docker/`. Compare `root-crontab.txt` with `sudo crontab -l`. |
| 7 | Portainer (new admin account), then the stacks one at a time, with the same names. The files are in `stacks/` on GitHub. Then the `tailscale serve` commands. |
| 8 | Beszel and FileBrowser: stop the container, `rsync` the volume from `$BK/boot-configs/var/lib/docker/volumes/...`, start it. Immich: **Restore from backup** on the welcome page, newest file in `/mnt/storage/immich/backups`. Nextcloud: stop `nextcloud` and `nextcloud_cron`, drop and create the `nextcloud` database in `nextcloud_db`, load the newest `db-dumps/nextcloud-DATE.sql.gz`, start them, then `occ maintenance:data-fingerprint` and `occ files:scan --all`. |
| 9 | AdGuard DNS rewrite and the devices, and the Immich address in the phone app. |
| 10 | `docker ps`, `sudo drives status`, `sudo homelab-backup` until `finished: OK`, then the reboot test. |

**When I rehearse this:** the safest way is a second computer or a virtual machine with a fresh Mint install, a copy of the interim backup, and a spare drive copy of `MAIN1`'s `immich/backups` and `nextcloud` folders. I will paste the result here when I have done it.

## How the widgets see the drives

- **Homepage drive pill:** it reads `/` (the boot drive) and `/mnt/storage` (the main pool) inside the Homepage container. The second works because of the `/mnt/storage:/mnt/storage:ro` volume. If it goes blank after a replug, restart Homepage.
- **Immich storage meter (bottom left of its web page):** it shows the disk that holds the photo folder (`/data`), so it shows the data drive while that is mounted.
- **Nextcloud card (`freespace`):** it reports the drive that holds the data folder, so it shows the data drive.
- **FileBrowser card:** FileBrowser reports the drive of the login's folder, and the admin login sees `/srv`, which is on the boot drive. That is why the card says "750GB HDD". To show the data drive on a card, see [C3](../troubleshooting.md#c3-the-filebrowser-card-shows-the-boot-drive-numbers).
