# Home Lab Troubleshooting Guide

This guide covers my home lab on an HP ProDesk 600 G3 Mini: the storage setup that works, the full migration from my old server, every problem I ran into, and the commands that fixed each one. Each problem is written the same way: symptom, cause, fix and how to verify it.

**Conventions**

- Server: an HP ProDesk 600 G3 DM (hostname `pc`) running Linux Mint 22.3 XFCE. User `brandon`, LAN address `192.168.1.198`, Tailscale name `pc.griffin-luma.ts.net`.
- Old server: a Lenovo Yoga 6 13ALC6 (`192.168.1.93`), kept as a separate machine on the tailnet.
- Drives: a 750GB hard drive is the boot drive (`sdb` today) and a 1TB hard drive is the data drive (`sda` today, label `MAIN1`, the first drive of the main pool at `/mnt/storage`; its label was `STORAGE` until Phase 15). Drive letters change, so use the label or the UUID for anything permanent. Replace `sda`, `sdb` or `sdX` in commands with your drive's current letter.
- Storage tools: `sudo drives` (menu and status), `sudo hdd-recover` and `sudo homelab-backup`, plus `homelab`, which prints a cheat sheet and a live status when a terminal opens. Their source is in the repository's [`homelab-drives/`](homelab-drives/) folder, and the README explains them in [section 3](README.md#3-storage-drive-pools-and-backups).
- Anything secret (passwords, API keys, tokens) is written as `your-own-key`.
- The README has the clean build guide with placeholders. This file has the real values.

## Table of Contents

1. [Setup at a glance](#1-setup-at-a-glance)
1. [Storage setup that works](#2-storage-setup-that-works)
   - [Step 1: Install the tools and scripts](#step-1-install-the-tools-and-scripts)
   - [Step 2: Add the main drive](#step-2-add-the-main-drive)
   - [Step 3: Create a folder for each service](#step-3-create-a-folder-for-each-service)
   - [Step 4: Point each service at its folder](#step-4-point-each-service-at-its-folder)
   - [Step 5: Drive power settings and cron lines](#step-5-drive-power-settings-and-cron-lines)
   - [Step 6: The recovery command](#step-6-the-recovery-command)
   - [Step 7: The daily backup](#step-7-the-daily-backup)
   - [Step 8: Verify it](#step-8-verify-it)
   - [Step 9: The cheat sheet at login](#step-9-the-cheat-sheet-at-login)
   - [Step 10: Replace a dead drive](#step-10-replace-a-dead-drive)
   - [Step 11: Rebuild the server from GitHub and the backup](#step-11-rebuild-the-server-from-github-and-the-backup)
   - [How the widgets see the drives](#how-the-widgets-see-the-drives)
1. [Migration from the Lenovo to the ProDesk](#3-migration-from-the-lenovo-to-the-prodesk)
   - [Phase 0: Plan and decisions](#phase-0-plan-and-decisions)
   - [Phase 1: Check the ProDesk](#phase-1-check-the-prodesk)
   - [Phase 2: Make the data drive permanent](#phase-2-make-the-data-drive-permanent)
   - [Phase 3: Clear the old data and create the folders](#phase-3-clear-the-old-data-and-create-the-folders)
   - [Phase 4: Free port 53 and deploy AdGuard Home](#phase-4-free-port-53-and-deploy-adguard-home)
   - [Phase 5: Beszel and FileBrowser](#phase-5-beszel-and-filebrowser)
   - [Phase 6: Tailscale addresses](#phase-6-tailscale-addresses)
   - [Phase 7: Immich](#phase-7-immich)
   - [Phase 8: Nextcloud](#phase-8-nextcloud)
   - [Phase 9: Speedtest Tracker and Netdata](#phase-9-speedtest-tracker-and-netdata)
   - [Phase 10: Homepage](#phase-10-homepage)
   - [Phase 11: Point devices at AdGuard Home](#phase-11-point-devices-at-adguard-home)
   - [Phase 12: Recovery script, reboot test and final inventory](#phase-12-recovery-script-reboot-test-and-final-inventory)
   - [Phase 13: Nextcloud and Immich integration, and the phone](#phase-13-nextcloud-and-immich-integration-and-the-phone)
   - [Phase 14: The Lenovo](#phase-14-the-lenovo)
   - [Phase 15: Drive pools and the daily backup](#phase-15-drive-pools-and-the-daily-backup)
1. [Troubleshooting](#4-troubleshooting)
   - [A. Drives and storage](#a-drives-and-storage)
   - [B. Docker and Portainer](#b-docker-and-portainer)
   - [C. FileBrowser](#c-filebrowser)
   - [D. Nextcloud](#d-nextcloud)
   - [E. Tailscale](#e-tailscale)
   - [F. AdGuard Home and DNS](#f-adguard-home-and-dns)
   - [G. Homepage](#g-homepage)
   - [H. Remote access](#h-remote-access)
   - [I. Hardware and boot](#i-hardware-and-boot)
1. [Diagnostic commands](#5-diagnostic-commands)
1. [Prevention checklist](#6-prevention-checklist)
1. [Updating services](#7-updating-services)
   - [7.1 What can be updated](#71-what-can-be-updated)
   - [7.2 Before you update anything](#72-before-you-update-anything)
   - [7.3 Portainer](#73-portainer)
   - [7.4 Homepage](#74-homepage)
   - [7.5 Speedtest Tracker](#75-speedtest-tracker)
   - [7.6 Netdata](#76-netdata)
   - [7.7 Beszel hub and agent](#77-beszel-hub-and-agent)
   - [7.8 AdGuard Home](#78-adguard-home)
   - [7.9 FileBrowser](#79-filebrowser)
   - [7.10 Immich](#710-immich)
   - [7.11 Nextcloud](#711-nextcloud)
   - [7.12 Docker Engine](#712-docker-engine)
   - [7.13 Tailscale](#713-tailscale)
   - [7.14 Linux Mint packages](#714-linux-mint-packages)
   - [7.15 After updating](#715-after-updating)
   - [7.16 Sources](#716-sources)

---

## 1. Setup at a glance

| Service | Container name | Local port | Tailscale address | Where its data lives |
| :--- | :--- | :--- | :--- | :--- |
| Homepage | `homepage` | 3001 | `https://pc.griffin-luma.ts.net:1000` | `/home/brandon/homepage-config` (boot drive) |
| Portainer | `portainer` | 9000 (HTTP), 9443 | `https://pc.griffin-luma.ts.net:1001` | Docker volume `portainer_data` |
| Immich | `immich_server`, `immich_postgres`, `immich_machine_learning`, `immich_redis` | 2283 | `https://pc.griffin-luma.ts.net:1002` | Photos on the data drive: `/mnt/storage/immich`. Database on the boot drive: `/home/brandon/immich/postgres` |
| Beszel | `beszel`, `beszel-agent` | 8090 | `https://pc.griffin-luma.ts.net:1003` | Docker volume `beszel_beszel_data` |
| AdGuard Home | `adguardhome` (host network) | 3000 (web), 53 (DNS) | `https://pc.griffin-luma.ts.net:1004` | `/opt/adguard-docker` (boot drive) |
| Nextcloud | `nextcloud`, `nextcloud_db`, `nextcloud_redis`, `nextcloud_cron` | 8082 | `https://pc.griffin-luma.ts.net:1005` | Files on the data drive: `/mnt/storage/nextcloud`. Database and app files on the boot drive: `/home/brandon/nextcloud` |
| FileBrowser | `filebrowser-filebrowser-1` | 8081 | `https://pc.griffin-luma.ts.net:1006` | Data drive: `/mnt/storage/filebrowser` (shown as `/srv/hdd`). Boot drive: `/home/brandon/750GB_HDD` (shown as `/srv/750GB_HDD`) |
| Speedtest Tracker | `speedtest-tracker` | 8088 | `https://pc.griffin-luma.ts.net:1007` | `/home/brandon/speedtest-tracker` (boot drive), shown in the container as `/config`. It was an anonymous Docker volume until 2026-10-23: [B6](#b6-a-container-starts-empty-after-update-the-stack) |
| Netdata | `netdata-netdata-1` | 19999 | `https://pc.griffin-luma.ts.net:1008` | Docker volumes |

The nine Portainer stacks are named `adguard`, `beszel`, `beszel-agent`, `filebrowser`, `immich`, `nextcloud`, `speedtest-tracker`, `netdata` and `homepage`.

| Drive | Size | Used for |
| :--- | :--- | :--- |
| Boot drive: Hitachi Travelstar 5K750 (`sdb` today) | 698.6G | Linux Mint on LVM, Docker, databases, app files and config |
| Data drive: Toshiba MQ01ABD100 (`sda` today, label `MAIN1`) | 916G usable | Photos, Nextcloud files, FileBrowser share. ext4, mounted at `/mnt/disks/MAIN1` and joined into the main pool at `/mnt/storage` |
| Backup | no drive yet | The daily 6:00 backup goes to `/home/brandon/750GB_HDD/backup-interim` on the boot drive. A backup drive (label `BACKUP1`, pool `/mnt/backup`) comes later. |

**Drive letters change.** The letters `sda` and `sdb` are not fixed. On my machine they were `sda` for the Hitachi and `sdb` for the Toshiba at first, and they swapped later (the Toshiba is now `sda`, so the data drive's partition is `/dev/sda1`). The expected outputs in this guide show those current letters. If yours differ, read them as "the data drive's partition". Identify drives by model with `lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS`, by the label `MAIN1`, or by the partition mounted at `/boot/efi`. `sudo drives status` lists every pool drive with its current device name.

---

## 2. Storage setup that works

Goal: the data drives are joined into a pool at `/mnt/storage` and keep the same labels, formats and paths after a reboot or a disconnect. Each service has its own folder in the pool, Homepage, FileBrowser, Immich and Nextcloud all see the pool correctly, and a daily backup copies it to a separate place.

**How it is laid out today**

- The Toshiba is the first drive of the main pool: ext4, label `MAIN1`, mounted by UUID at `/mnt/disks/MAIN1`. The mergerfs pool on top of it is mounted at `/mnt/storage`, the same path the stacks always used.
- The backup pool `/mnt/backup` (drive label `BACKUP1`) does not exist yet, because there is no backup drive. Until there is one, the daily backup goes to `/home/brandon/750GB_HDD/backup-interim` on the boot drive.
- Three tools manage it: `sudo drives` (menu and status), `sudo hdd-recover` (remount and restart) and `sudo homelab-backup` (daily copy). A fourth, `homelab`, only reads information and shows a cheat sheet and the status at every login ([Step 9](#step-9-the-cheat-sheet-at-login)). Their source is in the repository's `homelab-drives/` folder, and the README explains each option in [section 3](README.md#3-storage-drive-pools-and-backups).

**Why ext4:** it's a Linux filesystem, so Docker and databases get proper file permissions, and it isn't locked as "dirty" when the drive is unplugged the way NTFS can be.

### Step 1: Install the tools and scripts

```bash
uname -r
timedatectl | grep "Time zone"
sudo apt update && sudo apt install -y mergerfs rsync parted hdparm smartmontools
mergerfs --version | head -1
```

On my machine the kernel was `7.0.0-38-generic` (6.6 or newer is best), the time zone was `America/New_York (EDT, -0400)`, and `apt` installed one new package, `mergerfs 2.33.5-1ubuntu2`, from Ubuntu's `noble/universe` repository. The version command printed `mergerfs version: 2.33.5`. The other four packages were already installed.

I first copied the scripts to the server from a zip file with VS Code (Remote-SSH). They are now in the repository's `homelab-drives/` folder. Check them and install two of them (the third comes in Step 6, and `homelab` in Step 9):

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

```
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

### Step 2: Add the main drive

**A new or blank drive:** run `sudo drives`, choose **2** (Connect a new drive), pick the drive, choose **Main storage**, then type the device name and `ERASE`. The script formats it as ext4 with the label `MAIN1`, locks the empty mount points, adds the `/etc/fstab` lines below, mounts the drive and the pool, and sets the power level. **This erases the drive.** Practise first in test mode (see Phase 15).

**My case: a drive already mounted at `/mnt/storage`** (the Toshiba, ext4, with its files in place). This keeps every file where it is:

```bash
sudo drives adopt
```

It printed what it was about to do, and I answered `y`:

```
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

```
# removed by drives 2026-10-22: UUID=0f029dec-c289-4d9a-b893-8ea5ef2817bc  /mnt/storage  ext4  defaults,noatime,nofail,x-systemd.device-timeout=10  0  2
UUID=0f029dec-c289-4d9a-b893-8ea5ef2817bc  /mnt/disks/MAIN1  ext4  defaults,noatime,nofail,x-systemd.device-timeout=10  0  2
/mnt/disks/MAIN1 /mnt/storage fuse.mergerfs allow_other,cache.files=off,category.create=mfs,moveonenospc=true,dropcacheonclose=true,nofail,fsname=mergerfs-main,x-systemd.requires-mounts-for=/mnt/disks/MAIN1 0 0
```

The pool type must be `fuse.mergerfs`. In my testing, plain `mergerfs` rejected `nofail`. The README explains each pool option in [section 3.4](README.md#34-add-the-first-main-drive). Check it, one command at a time (`findmnt` prints nothing if you give it two paths, see [A12](#a12-findmnt-prints-nothing-when-given-two-paths)):

```bash
findmnt /mnt/storage
findmnt /mnt/disks/MAIN1
sudo drives status
```

```
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

### Step 3: Create a folder for each service

```bash
sudo mkdir -p /mnt/storage/immich /mnt/storage/filebrowser
sudo chown -R brandon:brandon /mnt/storage
sudo mkdir -p /mnt/storage/nextcloud
sudo chown -R 33:33 /mnt/storage/nextcloud
mkdir -p /home/brandon/nextcloud/html /home/brandon/nextcloud/db
mkdir -p /home/brandon/immich/postgres
mkdir -p /home/brandon/homepage-config
mkdir -p /home/brandon/750GB_HDD
sudo mkdir -p /opt/adguard-docker/conf /opt/adguard-docker/work
```

UID 33 is the user Nextcloud runs as inside its container (it shows up as `www-data` in `ls -la`). Keep the folders separate, and don't point FileBrowser at `/mnt/storage` itself, or you could delete Immich's files by accident.

### Step 4: Point each service at its folder

| Service | Where it points | Folder |
| :--- | :--- | :--- |
| Immich | Environment variable `UPLOAD_LOCATION` | `/mnt/storage/immich` |
| Immich database | Environment variable `DB_DATA_LOCATION` | `/home/brandon/immich/postgres` (boot drive) |
| FileBrowser | Volume line, shown as `/srv/hdd` | `/mnt/storage/filebrowser` |
| Nextcloud | Volume line, shown as `/data` | `/mnt/storage/nextcloud` |
| Homepage | Volume line and the `widgets.yaml` disk list | `/mnt/storage` |

**Immich:** environment variables in the Portainer stack:

```
UPLOAD_LOCATION=/mnt/storage/immich
DB_DATA_LOCATION=/home/brandon/immich/postgres
TZ=America/New_York
IMMICH_VERSION=release
DB_PASSWORD=your-own-key
DB_USERNAME=postgres
DB_DATABASE_NAME=immich
```

**FileBrowser:** the volumes in its stack:

```yaml
    volumes:
      - "/home/brandon/750GB_HDD:/srv/750GB_HDD"
      - "/mnt/storage/filebrowser:/srv/hdd"
      - filebrowser_data:/database
```

**Nextcloud:** the data folder and its volumes. The data folder is set once with `NEXTCLOUD_DATA_DIR: /data` and can't be changed after the first install:

```yaml
    environment:
      NEXTCLOUD_DATA_DIR: /data
    volumes:
      - /home/brandon/nextcloud/html:/var/www/html
      - /mnt/storage/nextcloud:/data
```

**Homepage:** the volumes in its stack, then the disk list in `widgets.yaml`:

```yaml
    volumes:
      - /home/brandon/homepage-config:/app/config
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

### Step 5: Drive power settings and cron lines

Laptop drives park their heads aggressively at the default power setting. `drives power` changes it on every pool drive, and a cron line keeps it that way after a reboot:

```bash
sudo drives power
sudo hdparm -B /dev/sda
sudo hdparm -C /dev/sda
sudo crontab -e
```

`drives power` sets `hdparm -B 254 -S 0` on main drives (least head parking, never spin down) and `hdparm -B 254 -S 120` on backup drives (the same, and spin down after 10 minutes idle, since `120 x 5 seconds` is 10 minutes). It printed:

```
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

### Step 6: The recovery command

Containers keep the view of the drive they had when they started. After an unplug, they need a restart. `hdd-recover` is now a one-line wrapper that calls `drives recover`:

```bash
sudo install -m 755 ~/homelab-drives/hdd-recover /usr/local/bin/hdd-recover
sudo hdd-recover
```

`drives recover` looks at what each container has mounted under `/mnt/storage`, `/mnt/backup` and `/mnt/disks`, stops those containers, unmounts the pools and drives, mounts them again from `/etc/fstab`, re-applies the power settings and starts the containers. The old script had a fixed list of five container names. This one finds them by itself, so a new service is picked up with no edit. On my server it printed:

```
Stopping containers that use this storage: filebrowser-filebrowser-1 homepage immich_server nextcloud nextcloud_cron
Starting containers: filebrowser-filebrowser-1 homepage immich_server nextcloud nextcloud_cron
Recovered.
```

If a main drive isn't found, it prints `Drive not found. Check the cable.` with the drive's label and leaves the containers stopped on purpose. A missing backup drive only gives a warning. The old script is saved on the server as `/usr/local/bin/hdd-recover.old`, and its text is in Phase 15.

### Step 7: The daily backup

`homelab-backup` dumps the Nextcloud database, copies the main pool with `rsync` (a file you delete or replace is moved into `_deleted/<date>/` and kept for 30 days), copies the boot drive's config files, and deletes dumps and `_deleted` folders older than 30 days. It writes to `/mnt/backup` when that pool is mounted. Until then it uses the folder named in `DEST_FALLBACK`:

```bash
sudo tee /etc/homelab-backup.conf >/dev/null <<'EOF'
DEST_FALLBACK="/home/brandon/750GB_HDD/backup-interim"
EOF
df -h / /mnt/storage
sudo nohup /usr/local/sbin/homelab-backup >/dev/null 2>&1 &
sudo tail -f /var/log/homelab-backup.log
```

The boot drive had 606 GB free before the backup, and the pool holds 61 GB. The first run took 1420 seconds (about 24 minutes) and the log ended like this:

```
2026-10-22 19:04:46 start
2026-10-22 19:04:46 backup pool not mounted, using the fallback folder /home/brandon/750GB_HDD/backup-interim
2026-10-22 19:04:53 database dump saved: /home/brandon/750GB_HDD/backup-interim/db-dumps/nextcloud-2026-10-22.sql.gz
2026-10-22 19:27:04 main storage copied
2026-10-22 19:28:26 configs copied
2026-10-22 19:28:26 finished: OK in 1420s
```

While it ran, `du -sh` on the `main` folder grew from 8.2G to 17G to 21G, and in the end both folders showed `61G`. `sudo drives status` then showed `2026-10-22 19:28  result: OK  destination: /home/brandon/750GB_HDD/backup-interim  took: 1420s`. The folder holds `main`, `boot-configs` (1.1 GB, with `etc`, `home`, `opt`, `usr`, `var` and `root-crontab.txt`), `db-dumps` (the dump was 2.0 MB) and `_deleted`. To watch whether it is still running, use `pgrep -af homelab-backup` (see [A15](#a15-pgrep-shows-nothing-while-the-backup-is-running)). Then the schedule, added to root's crontab with `sudo crontab -e`:

```cron
0 6 * * * /usr/local/sbin/homelab-backup
```

**Guards.** The backup refuses to run, and logs why, if the main pool isn't mounted or looks empty (so a missing drive can't empty the backup), if the backup target isn't mounted and no fallback is set, or if the target has less than 20 GB free (or less than the pool's size plus 20 GB for the first run).

**The weakness for now.** The interim backup is on the boot drive. It protects against a failed data drive, but not against a failed boot drive or a lost machine, and it adds about 63 GB to the boot drive's root filesystem (107 GB used with it, 44 GB without). When a backup drive is connected (`sudo drives`, then **2**, **Backup storage**), delete the `DEST_FALLBACK` line, run `sudo homelab-backup`, and then remove the interim folder.

**Restore.** Copy files out of the backup, and never edit them there, because the next run overwrites a changed file. With the pool as the target, the paths start with `/mnt/backup` instead of the interim folder:

```bash
ls /home/brandon/750GB_HDD/backup-interim/_deleted/
sudo cp -a /home/brandon/750GB_HDD/backup-interim/main/nextcloud/some-folder /mnt/storage/nextcloud/
docker exec -u www-data nextcloud php occ files:scan --all
```

**Extra folders.** The list of boot-drive folders that the backup copies is `CONFIG_PATHS` at the top of `homelab-backup`. Speedtest Tracker's data folder is not in it, because the container used an anonymous volume when the list was written ([B6](#b6-a-container-starts-empty-after-update-the-stack)). I don't edit the script. I add the folder from the settings file, which is read after the defaults:

```bash
echo 'CONFIG_PATHS+=(/home/brandon/speedtest-tracker)' | sudo tee -a /etc/homelab-backup.conf
cat /etc/homelab-backup.conf
```

Use `+=`. A plain `=` would replace the whole list and the backup would stop copying Homepage, AdGuard, Nextcloud and the rest. **Verify** after the next backup (the 6:00 run, or `sudo homelab-backup` by hand):

```bash
sudo drives status
sudo ls /home/brandon/750GB_HDD/backup-interim/boot-configs/home/brandon/
```

The status should say `OK`, and the listing should include `speedtest-tracker`. I gave myself this command on 2026-10-23 and have not yet checked the result of a backup after it.

### Step 8: Verify it

Start the Immich, FileBrowser, Nextcloud and Homepage stacks, then check that each container sees the pool:

```bash
findmnt /mnt/storage
docker exec immich_server df -h /data
docker exec filebrowser-filebrowser-1 df -h /srv/hdd /srv/750GB_HDD
docker exec nextcloud df -h /data
docker exec homepage df -h /mnt/storage
```

Every container should show the filesystem `mergerfs-main` at about 916G (FileBrowser's `/srv/750GB_HDD` line shows the boot drive's `vgmint-root`). After the conversion mine showed:

```
Filesystem      Size  Used Avail Use% Mounted on
mergerfs-main   916G   61G  855G   7% /data
```

FileBrowser and Homepage, whose `df` prints a slightly different layout, showed `mergerfs-main 915.8G 60.9G 854.9G 7%`. If one shows the boot drive instead, that container was started before the pool was mounted, so restart it. Then run these tests:

- **Reboot:** run `sudo reboot`. After about three minutes, run `findmnt /mnt/storage`, `findmnt /mnt/disks/MAIN1` and `docker ps --format "table {{.Names}}\t{{.Status}}"`. The pool and the drive should be mounted and the containers up with no help from you. My result is in Phase 15.
- **Unplug:** unplug the drive, wait a few seconds, plug it back in and run `sudo hdd-recover`. You should see `Recovered.` I tested this with fake drives, but I have not repeated it on the real drive since it became a pool.
- **Lock test (optional):** with the stacks stopped, run `sudo umount /mnt/storage`, then `touch /mnt/storage/test`. It should say `Operation not permitted`, which shows nothing can write to the empty folder. Then run `sudo mount /mnt/storage` and start the stacks again. I ran this test on the single drive. The pool uses the same locked folders, but I haven't repeated it since. `lsattr` can't show the lock while the drive is mounted, because the flag sits on the hidden folder underneath.

### Step 9: The cheat sheet at login

`homelab` is a read-only script. It prints the commands from this guide, grouped by job, and a live status block, so I don't have to memorise them. I run it from `~/.bashrc`, so it shows in every new terminal: a plain SSH session and the terminal inside VS Code Remote-SSH. The README explains it in [section 3.14](README.md#314-the-cheat-sheet-at-login).

**1. Install it,** from inside the folder that holds the files. This is the step where I first made a mistake: I ran `install` from my home folder and got `install: cannot stat 'homelab'` ([A16](#a16-install-says-cannot-stat-when-installing-a-script)).

```bash
cd ~/homelab-drives
sha256sum -c SHA256SUMS
sudo install -m 755 homelab /usr/local/bin/homelab
homelab version
```

```
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

```
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
Docs  /home/brandon/My-Home-Lab-
  homelab docs                       sections of README.md and TROUBLESHOOTING.md
  git -C ~/My-Home-Lab- pull         refresh them from GitHub

Status
  Main pool       mounted, 61G used of 916G
  Backup pool     not connected (the backup goes to the boot drive)
  Last backup     2026-10-22 19:28  OK  (7 h ago)
  Containers      16 of 16 running
  Boot drive      18% used, 536G free
```

The first time, the Containers line was red because `portainer-old`, the spare container kept after the Portainer update ([7.3](#73-portainer)), was stopped on purpose. I changed the script to ignore a stopped container whose restart policy is `no`, so only containers that should be running count.

**3. Get the documents on the server,** so `homelab docs` has something to list. The first try failed with `Could not resolve host: github.com`, which turned out to be a DNS problem and not a mistake in the command ([F6](#f6-the-server-cannot-look-up-names-after-a-tailscale-update)). After F6 was fixed:

```bash
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git ~/My-Home-Lab-
homelab docs
```

`homelab docs` lists the `##` headings of the README and of this file with their line numbers.

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

**5. Test it in both places.** Open a new VS Code terminal (**Terminal**, then **New Terminal**) and a new SSH session from PowerShell. Both must show the cheat sheet. The first version of my block failed in VS Code ([H5](#h5-the-cheat-sheet-does-not-appear-in-the-vs-code-terminal)). The block above is the fixed one: it needs no variable.

**Undo,** if you want the old `.bashrc` back (only if you changed nothing else in it since):

```bash
cp ~/.bashrc.bak-2026-10-23 ~/.bashrc
```

### Step 10: Replace a dead drive

**Status: written and tested on fake drives, and rehearsed with a USB stick on 2026-10-23. Not yet used on my real drive.** This is the part that lets me recover when the Toshiba (`MAIN1`) dies. The README explains it in [section 3.15](README.md#315-replace-a-dead-drive). `drives` is version 1.1 from here on, and `homelab` was updated too (its Main pool line now mentions `sudo drives replace`, and the cheat sheet has a line for it).

**What I am relying on.** My main pool has one drive, so if it dies the whole pool is gone and every service stops. The only copy of my files is the daily backup in `/home/brandon/750GB_HDD/backup-interim` on the boot drive. `sudo drives replace` makes a new drive take the name `MAIN1`, shows what is missing, copies only the missing files from that backup, checks them, and then starts the containers. The new drive needs room for the 61 GB that are in the pool today, and it should be at least as big as I want the pool to be.

**1. Put the new version on the server.** Copy `drives`, `homelab` and `SHA256SUMS` into the folder (`~/homelab-drives`, or `~/My-Home-Lab-/homelab-drives` after a `git pull`), then, inside that folder:

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

**2. Rehearse it** with the USB stick and fake drives before a real drive dies. The numbered steps are in the README, [section 3.15](README.md#315-replace-a-dead-drive), under "Rehearse it with a USB stick". **Done on 2026-10-23, and it passed.** What I did and what I saw, step by step:

**2.1 Two fake drives, stick still unplugged.** `sudo DRIVES_TEST=1 drives test-setup 2 1G` made `/dev/loop0` (`disk1.img`) and `/dev/loop1` (`disk2.img`). Then I ran `sudo DRIVES_TEST=1 drives connect` twice. The list showed only the two fake drives, I chose **Main storage**, typed the drive name and `ERASE`, and it ended with `Done. TMAIN1 is connected to the main storage (/mnt/test-main).` and the same for `TMAIN2`. The status then showed:

```
main     /mnt/test-main mounted (fuse.mergerfs)  48KB used of 1.9GB
LABEL     ROLE     DEVICE       SIZE      USED      SMART     STATE
TMAIN1    main     /dev/loop0p1 972MB     24KB      skipped (test mode) connected
TMAIN2    main     /dev/loop1p1 972MB     24KB      skipped (test mode) connected
/dev/sda  931.5G  TOSHIBA MQ01ABD100  [usb]   not connected to a pool
```

The last line is only how test mode sees my real Toshiba: it knows nothing about my real pool. The real pool was not touched.

**2.2 Practice files and a practice backup.** Three 50 MB random files in `/mnt/test-main/photos`, copied with `rsync -a` to `/var/tmp/practice-backup/main`, checksums saved in `~/practice-sums.txt`. The pool put `file1.bin` on `TMAIN1` and `file2.bin` and `file3.bin` on `TMAIN2` (51 MB and 101 MB used), so losing `TMAIN2` would lose two of the three files.

**2.3 Pretend `TMAIN2` died.** `umount -l /mnt/test-main`, `umount -l /mnt/test-disks/TMAIN2`, `losetup -d /dev/loop1`. The status showed:

```
main     /mnt/test-main NOT MOUNTED
TMAIN1    main     /dev/loop0p1 972MB     51MB      skipped (test mode) connected
TMAIN2    main     -            -         -         -         MISSING (cable? then: sudo hdd-recover. Dead? sudo drives replace)
```

**2.4 Plug in the stick and find it.** `lsblk` listed a new `sdc`, 7.2G, `usb`, with one partition labelled `TMAIN1` (left over from an earlier practice). `dmesg` showed `USB DISK 2.0 ... Attached SCSI removable disk`. My Toshiba (`sda`, 931.5G) and the boot drive (`sdb`, 698.6G) were unmistakably different. I did not unplug the Toshiba.

**2.5 The replace.** `sudo DRIVES_TEST=1 DRIVES_RESTORE_SRC=/var/tmp/practice-backup drives replace`. I chose `TMAIN2`, answered `y` to the no-backup-record warning, chose the stick (the only real drive in the list), typed its name and `ERASE`, saw the preview and typed `RESTORE`. The desktop had auto-mounted the stick at `/media/brandon/TMAIN1`; the tool handled that. What it printed (the stick's serial number left out):

```
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
|---|---|
| The only main drive dies | The new drive gets the label `MAIN1` and a new UUID in `/etc/fstab` (the old line is kept as a comment). Every file is identical afterwards (`sha256sum`), including symlinks, names with spaces and accents, and nested folders. The containers are stopped first and started only after the check. |
| One of two main drives dies | Only the missing files come back. A file I had changed on the surviving drive after the backup was not overwritten, a file created after the backup was untouched, and a file I had deleted after the backup came back (documented behaviour). |
| I type something other than `RESTORE` | Nothing is copied, the containers stay stopped, and `sudo drives restore` finishes the job later. Running it again says `Nothing is missing`. |
| A backup drive dies | The new drive gets the label `BACKUP1`, the pool mounts, the main data is untouched, and the backup run is offered. |
| Refusals | No missing drive, no backup found, a failed last backup, a wrong device name, `ERASE` not typed, a drive that is too small, and not enough free space all stop with the fstab unchanged and (where it applies) the drive not formatted. |
| Two main drives die | The first replacement leaves the pool down and the containers stopped, the second brings it up and restores everything. |

**One limit I found while testing.** In my fake-drive test, two hard-linked files showed different inode numbers through the mergerfs pool, so `rsync -H` copied them into the backup as two separate files. A restored hard link would then be a normal copy. I have not checked whether any of my real files are hard-linked.

**Undo for the install,** if you want the old version back: install the old `drives` from the repository history, or from `/home/brandon/homelab-drives` if you still have it. The old version does not have the `replace` command and works as before.

### Step 11: Rebuild the server from GitHub and the backup

**Status: written on 2026-10-23 from the design and checked on a fake file tree. Not rehearsed on a real rebuild.** The README has the full procedure with explanations ([Rebuild the server after the boot drive dies](README.md#rebuild-the-server-after-the-boot-drive-dies)). This step is the same procedure with my real values, and the list of what I have to fix first.

**What I found when I checked it on paper**

1. **Until `BACKUP1` exists, the backup dies with the boot drive.** The backup sits in `/home/brandon/750GB_HDD/backup-interim`, on the same drive as the databases and the app folders. If that drive dies, I lose the Nextcloud database dump, the Nextcloud app folder (`config.php`), AdGuard Home's settings and the Beszel and FileBrowser data. Not lost: all photos and files (they are on `MAIN1`) and the Immich database, because Immich writes its own dumps to `/mnt/storage/immich/backups`. Until the backup drive is connected, I copy the `db-dumps` and `boot-configs` folders of the interim backup to another computer once a month.
2. **A full copy of the saved configs would break the new server.** The backup holds the old `/etc/fstab`. Copying it back makes the new install unbootable, which is why Step 6 of the README leaves it out (with the scripts and the Docker data). I tested the exclusions on a fake tree: the new `fstab` and the new `drives` stayed, the Homepage, Nextcloud and AdGuard files came back, the Homepage files kept their owner (1000), and `root-crontab.txt` did not land in `/`.
3. **The stack names matter.** The Beszel and FileBrowser data come back by their volume names, `beszel_beszel_data` and `filebrowser_filebrowser_data`. Before I need this, I run this once and keep the output:

```bash
docker ps --format '{{.Names}}   {{.Label "com.docker.compose.project"}}'
```

The second column is the stack name each container belongs to.

4. **The secrets are in no file.** Where each one comes from: the Nextcloud database password is also inside `/home/brandon/nextcloud/html/config/config.php` (`dbpassword`), so it can be read back after the restore of that folder; everything else (Nextcloud admin, Immich database user and password, the Homepage widget keys, the Speedtest Tracker `APP_KEY`) must be in my password manager. **To do: check that each of them is there.**
5. **The Tailscale name.** Delete the old `pc` in the admin console before the new server joins, or it becomes `pc-1` and `griffin-luma.ts.net` addresses stop matching (Nextcloud's `OVERWRITEHOST`, Homepage's allowed hosts, the phone).

**The procedure with my values**

| Step | What I do |
| :--- | :--- |
| 1 | Delete the dead `pc` in the Tailscale admin console. |
| 2 | Install Linux Mint with user `brandon` and host name `pc`. SSH, and the router reservation for 192.168.1.198 (new network card: update the reservation). |
| 3 | Docker and Tailscale (`tailscale up` only), and the `wait-for-hdd.conf` file. No stacks yet. |
| 4 | `git clone`, `sha256sum -c SHA256SUMS` (five `OK`), install `drives`, `homelab-backup`, `hdd-recover`, `homelab`. |
| 5 | `sudo drives` → 2 → the Toshiba → Main storage → **Keep the data and add the drive as it is**. Check `ls /mnt/storage`. Make the folders under `/home/brandon` and `/opt`, then the two cron lines and `/etc/homelab-backup.conf` (`DEST_FALLBACK` only while there is no `BACKUP1`, and `CONFIG_PATHS+=(/home/brandon/speedtest-tracker)`). |
| 6 | `BK=/home/brandon/750GB_HDD/backup-interim` (later `BK=/mnt/backup`), then the `rsync -aHn` preview, then the real `rsync -aH`, both with `--exclude=/etc/fstab --exclude=/usr/local/ --exclude=/root-crontab.txt --exclude=/var/lib/docker/`. Compare `root-crontab.txt` with `sudo crontab -l`. |
| 7 | Portainer (new admin account), then the stacks one at a time, with the same names. The files are in `Portainer-code/` on GitHub. Then the `tailscale serve` commands. |
| 8 | Beszel and FileBrowser: stop the container, `rsync` the volume from `$BK/boot-configs/var/lib/docker/volumes/...`, start it. Immich: **Restore from backup** on the welcome page, newest file in `/mnt/storage/immich/backups`. Nextcloud: stop `nextcloud` and `nextcloud_cron`, drop and create the `nextcloud` database in `nextcloud_db`, load the newest `db-dumps/nextcloud-DATE.sql.gz`, start them, then `occ maintenance:data-fingerprint` and `occ files:scan --all`. |
| 9 | AdGuard DNS rewrite and the devices, and the Immich address in the phone app. |
| 10 | `docker ps`, `sudo drives status`, `sudo homelab-backup` until `finished: OK`, then the reboot test. |

**When I rehearse this:** the safest way is a second computer or a virtual machine with a fresh Mint install, a copy of the interim backup, and a spare drive copy of `MAIN1`'s `immich/backups` and `nextcloud` folders. I will paste the result here when I have done it.

### How the widgets see the drives

- **Homepage drive pill:** it reads `/` (the boot drive) and `/mnt/storage` (the main pool) inside the Homepage container. The second works because of the `/mnt/storage:/mnt/storage:ro` volume. If it goes blank after a replug, restart Homepage.
- **Immich storage meter (bottom left of its web page):** it shows the disk that holds the photo folder (`/data`), so it shows the data drive while that is mounted.
- **Nextcloud card (`freespace`):** it reports the drive that holds the data folder, so it shows the data drive.
- **FileBrowser card:** FileBrowser reports the drive of the login's folder, and the admin login sees `/srv`, which is on the boot drive. That is why the card says "750GB HDD". To show the data drive on a card, see [C3](#c3-the-filebrowser-card-shows-the-boot-drive-numbers).

---

## 3. Migration from the Lenovo to the ProDesk

This is the full runbook for moving my home lab from a Lenovo laptop to the HP ProDesk, in the order I did it. Phases 0 to 14 were done with a single data drive, so their checks show `/dev/sda1` and the label `STORAGE`. Phase 15 turned that drive into a pool, after which the same checks show `mergerfs-main` and the label `MAIN1`. The steps are the clean, correct sequence. The problems I ran into along the way are written up as separate entries in [section 4](#4-troubleshooting), and each phase links to the ones that matter.

### Phase 0: Plan and decisions

| | Old server | New server |
| :--- | :--- | :--- |
| Machine | Lenovo Yoga 6 13ALC6 laptop | HP ProDesk 600 G3 Mini |
| System | Linux Mint Cinnamon | Linux Mint 22.3 XFCE (LVM, no encryption) |
| Address | `192.168.1.93` | `192.168.1.198` |
| Tailscale name | `home` | `pc` |
| Tailscale ports | 8441 to 8447, 9444 and 443 | 1000 to 1008 |
| Boot drive | 256GB SSD | 750GB hard drive |
| Data drive | 1TB hard drive on USB | The same 1TB drive, moved over |
| Services | The same nine | The same nine, rebuilt from scratch |

Decisions:

- **The ProDesk keeps its own address and name.** Instead of giving it the Lenovo's address, every `192.168.1.93` in the old files became `192.168.1.198` and every `home` became `pc`. Both servers can then exist on the network at the same time.
- **Fresh start.** No databases or settings were migrated. Every service starts empty with new accounts, so there are no stale references to the old setup.
- **Renumbered Tailscale ports.** The nine services are numbered 1000 to 1008 in a fixed order: Homepage 1000, Portainer 1001, Immich 1002, Beszel 1003, AdGuard Home 1004, Nextcloud 1005, FileBrowser 1006, Speedtest Tracker 1007, Netdata 1008.
- **Drives.** The 750GB drive is the boot drive. The 1TB drive moved over, keeping its ext4 filesystem and its `STORAGE` label. Its old test data was wiped.
- **DNS.** The router wouldn't let me change its DNS setting, so each device points at the ProDesk by hand (Phase 11).
- **The Lenovo stays,** as a separate machine on the tailnet (Phase 14).

**Before you start,** the ProDesk needs Linux Mint installed, Docker and Portainer installed, SSH working, Tailscale installed and signed in, and a fixed address reserved in the router. The README covers each of those.

### Phase 1: Check the ProDesk

Take an inventory and check both drives before you change anything. First, install the tools:

```bash
sudo apt update
sudo apt install smartmontools hdparm rsync -y
```

Check the health of both drives. These commands look the drives up so they work whichever letters you have:

```bash
sudo smartctl -H -A /dev/$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)") | grep -E "overall-health|Power_On_Hours|Reallocated_Sector|Current_Pending|Load_Cycle"
sudo smartctl -H -A -d sat /dev/disk/by-label/STORAGE | grep -E "overall-health|Power_On_Hours|Reallocated_Sector|Current_Pending|Load_Cycle"
```

You want `PASSED` and `0` for `Reallocated_Sector_Ct` and `Current_Pending_Sector` on both. Mine were:

| | Boot drive | Data drive |
| :--- | :--- | :--- |
| Health | PASSED | PASSED |
| Power-on hours | 1,945 | 8,950 |
| Reallocated and pending sectors | 0 and 0 | 0 and 0 |
| Load cycle count | 48,421 | 105,799 |

Get the wired adapter's hardware address, and reserve `192.168.1.198` for it in the router:

```bash
ip -br link show eno1
```

Run the inventory script from [section 5](#52-the-inventory-script) once now, so you have a record of the starting point.

### Phase 2: Make the data drive permanent

The 1TB drive was already ext4 with the label `STORAGE`, so it isn't reformatted. The desktop had mounted it under `/media/brandon/STORAGE`, which isn't permanent. First check that the data is there:

```bash
ls -la /media/brandon/STORAGE
```

You should see the old folders (`filebrowser`, `immich`, `nextcloud`). If the listing is empty or looks wrong, stop. If it's right, close any file manager window that shows the drive and run:

```bash
sudo umount /media/brandon/STORAGE
sudo mkdir -p /mnt/storage
sudo chattr +i /mnt/storage
sudo cp /etc/fstab /etc/fstab.bak
echo "UUID=0f029dec-c289-4d9a-b893-8ea5ef2817bc  /mnt/storage  ext4  defaults,noatime,nofail,x-systemd.device-timeout=10  0  2" | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
sudo mount -a
findmnt /mnt/storage
ls -la /mnt/storage
sudo dmesg | grep -i -E "sda|ext4" | tail -15
```

`findmnt` should show `/dev/sda1` at `/mnt/storage`. The `dmesg` lines may show `recovery complete` for the drive, which is normal after it was switched off without being unmounted, and there should be no errors. Then make Docker wait for the drive, and set the power level on both drives:

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
printf '[Unit]\nWants=mnt-storage.mount\nAfter=mnt-storage.mount\n' | sudo tee /etc/systemd/system/docker.service.d/wait-for-hdd.conf
sudo systemctl daemon-reload
DATA=$(lsblk -no pkname "$(readlink -f /dev/disk/by-label/STORAGE)")
BOOT=$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)")
sudo hdparm -B 254 /dev/$DATA
sudo hdparm -B /dev/$DATA
sudo hdparm -B 254 /dev/$BOOT
sudo hdparm -B /dev/$BOOT
sudo crontab -e
```

Both `hdparm -B` checks should print `APM_level = 254`. The boot drive needed this too: it had 48,421 head parks in under 2,000 hours, which is about 25 an hour. Add these lines to root's crontab:

```cron
@reboot sleep 60 && /usr/sbin/hdparm -S 0 -B 254 "/dev/$(lsblk -no pkname "$(readlink -f /dev/disk/by-label/STORAGE)")"
0 6 * * * echo "$(date +\%F) $(smartctl -A -d sat /dev/disk/by-label/STORAGE | awk '/Load_Cycle/ {print $10}')" >> /var/log/loadcycles.log
@reboot sleep 60 && /usr/sbin/hdparm -B 254 "/dev/$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)")"
```

Check that they saved with `sudo crontab -l`, then reboot to prove the mount comes back by itself:

```bash
sudo reboot
```

After a couple of minutes:

```bash
findmnt /mnt/storage
docker ps
```

The drive should be mounted and Portainer running. (This is the single-drive setup. Phase 15 later turned it into a pool, and the label `STORAGE` became `MAIN1`.) If a step went wrong, see [A1](#a1-the-data-drive-comes-back-under-a-different-path-after-a-replug) and [A7](#a7-containers-start-before-the-drive-is-mounted-after-a-reboot).

### Phase 3: Clear the old data and create the folders

The 61GB on the drive was test data from the Lenovo, so I wiped it. Check the drive is mounted first, because the next command deletes things:

```bash
findmnt /mnt/storage
ls -la /mnt/storage
```

The first command must show `/dev/sda1`. Then delete the old test data and check:

```bash
sudo rm -rf /mnt/storage/immich /mnt/storage/filebrowser /mnt/storage/nextcloud /mnt/storage/nextcloud-db.sql
ls -la /mnt/storage
df -h /mnt/storage
```

The listing should be empty and the used space under 1G. Then create the folders, with the same layout as the Lenovo:

```bash
sudo mkdir -p /mnt/storage/immich /mnt/storage/filebrowser
sudo chown -R brandon:brandon /mnt/storage
sudo mkdir -p /mnt/storage/nextcloud
sudo chown -R 33:33 /mnt/storage/nextcloud
mkdir -p /home/brandon/nextcloud/html /home/brandon/nextcloud/db
mkdir -p /home/brandon/immich/postgres
mkdir -p /home/brandon/homepage-config
sudo mkdir -p /opt/adguard-docker/conf /opt/adguard-docker/work
mkdir -p /home/brandon/750GB_HDD
ls -la /mnt/storage /home/brandon/nextcloud /opt/adguard-docker
```

Because the paths match the old stack files, the stacks need no edits for folders. The old share `256GB_SSD` became `750GB_HDD`, since it now lives on the 750GB boot drive.

### Phase 4: Free port 53 and deploy AdGuard Home

This is the first service, because port 53 changes how the machine looks up names.

**1. Reconnect over the local network, not Tailscale,** because step 3 restarts Tailscale and would cut off a session that goes through it:

```bash
ssh brandon@192.168.1.198
```

**2. Download the AdGuard image** while DNS still works:

```bash
docker pull adguard/adguardhome:v0.107.79
```

**3. Free port 53.** `systemd-resolved` is turned off, and Tailscale takes over `/etc/resolv.conf`, the same final state as on the Lenovo. The router's address goes into `resolv.conf` first so the machine keeps resolving names until AdGuard runs:

```bash
sudo systemctl disable systemd-resolved
sudo systemctl stop systemd-resolved
sudo rm /etc/resolv.conf
echo "nameserver 192.168.1.1" | sudo tee /etc/resolv.conf
sudo systemctl restart tailscaled
```

**4. Check it:**

```bash
sudo ss -tulpn | grep :53
cat /etc/resolv.conf
nslookup google.com
tailscale status | head -3
```

Port 53 should no longer be held by `systemd-resolve`. `resolv.conf` should start with `# resolv.conf(5) file generated by tailscale` and show `nameserver 100.100.100.100`. The lookup should return an address, and `tailscale status` should still show the machine connected. If the lookup fails, undo it with the rollback in [F1](#f1-port-53-conflict-with-systemd-resolved).

**A warning from later.** This worked for a month. On 2026-10-23, after Tailscale updated itself, the server could not look up any name while Tailscale owned `resolv.conf`. That is [F6](#f6-the-server-cannot-look-up-names-after-a-tailscale-update).

**5. Create the stack.** In Portainer (`http://192.168.1.198:9000`), go to **Stacks**, then **Add stack**, name it `adguard`:

```yaml
services:
  adguard:
    image: adguard/adguardhome:v0.107.79
    container_name: adguardhome
    restart: unless-stopped
    network_mode: host
    volumes:
      - /opt/adguard-docker/work:/opt/adguardhome/work
      - /opt/adguard-docker/conf:/opt/adguardhome/conf
```

**6. Run the setup wizard** at `http://192.168.1.198:3000`. Set the admin web interface to all interfaces on port **3000** (the wizard proposes 80, so change it) and the DNS server to all interfaces on port **53**. Create your admin account. If you leave the web port at 80, the Tailscale address will show a 502 error later, see [F5](#f5-the-adguard-web-page-shows-a-502-on-its-tailscale-address).

**7. Check that AdGuard answers:**

```bash
docker ps
sudo ss -tulpn | grep ':53 '
nslookup google.com 192.168.1.198
```

The container should be running, AdGuardHome should own port 53, and the lookup should return an address. Test the same lookup from another device. Then enable the twelve blocklists you want in AdGuard's **Filters** page. Mine are in the README.

### Phase 5: Beszel and FileBrowser

**Beszel hub.** Create a stack named `beszel`:

```yaml
services:
  beszel:
    image: henrygd/beszel:latest
    container_name: beszel
    restart: unless-stopped
    ports:
      - 8090:8090
    volumes:
      - beszel_data:/beszel_data

volumes:
  beszel_data:
```

Open `http://192.168.1.198:8090` and create your admin account. Click **Add System**, enter a name (`ProDesk`) and the host `192.168.1.198`, stay on the **Docker** tab and click **Copy docker compose**. Keep that window open.

**Beszel agent.** Create a stack named `beszel-agent` and paste what you copied. Check that `network_mode: host` is there and that `HUB_URL` is `http://192.168.1.198:8090`:

```yaml
services:
  beszel-agent:
    image: henrygd/beszel-agent
    container_name: beszel-agent
    restart: unless-stopped
    network_mode: host
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./beszel_agent_data:/var/lib/beszel-agent
    environment:
      LISTEN: 45876
      KEY: 'your-own-key'
      TOKEN: your-own-key
      HUB_URL: http://192.168.1.198:8090
```

Deploy it, then go back to the hub window and click **Add system** at the bottom to finish. Check it:

```bash
docker logs beszel-agent | tail -n 10
```

Look for `WebSocket connected host=192.168.1.198:8090`, and a green system in the hub.

**FileBrowser.** The old `256GB_SSD` share becomes `750GB_HDD`, created in Phase 3. Create a stack named `filebrowser`. The stack and service names must both be `filebrowser`:

```yaml
version: '3'
services:
  filebrowser:
    image: filebrowser/filebrowser
    restart: always
    ports:
      - "8081:80"
    volumes:
      - "/home/brandon/750GB_HDD:/srv/750GB_HDD"
      - "/mnt/storage/filebrowser:/srv/hdd"
      - filebrowser_data:/database

volumes:
  filebrowser_data:
```

Compose may warn that `version` is obsolete. That is harmless. Check it, and read the generated first password:

```bash
docker ps
docker exec filebrowser-filebrowser-1 df -h /srv/hdd /srv/750GB_HDD
docker logs filebrowser-filebrowser-1 | grep -i password
```

The container should be `healthy`. `/srv/hdd` should show `/dev/sda1` at 915.8G, and `/srv/750GB_HDD` the boot drive. Log in at `http://192.168.1.198:8081` as `admin` with the printed password, and change it straight away. See [C1](#c1-the-filebrowser-login-is-rejected).

### Phase 6: Tailscale addresses

Nextcloud needs its Tailscale address before you can log in, so set all nine now. Entries for services that aren't running yet show an error until those are deployed:

```bash
sudo tailscale serve reset
sudo tailscale serve --bg --https=1000 http://192.168.1.198:3001
sudo tailscale serve --bg --https=1001 http://192.168.1.198:9000
sudo tailscale serve --bg --https=1002 http://192.168.1.198:2283
sudo tailscale serve --bg --https=1003 http://192.168.1.198:8090
sudo tailscale serve --bg --https=1004 http://192.168.1.198:3000
sudo tailscale serve --bg --https=1005 http://192.168.1.198:8082
sudo tailscale serve --bg --https=1006 http://192.168.1.198:8081
sudo tailscale serve --bg --https=1007 http://192.168.1.198:8088
sudo tailscale serve --bg --https=1008 http://192.168.1.198:19999
tailscale serve status
```

| Port | Service | Address |
| :--- | :--- | :--- |
| 1000 | Homepage | `https://pc.griffin-luma.ts.net:1000` |
| 1001 | Portainer | `https://pc.griffin-luma.ts.net:1001` |
| 1002 | Immich | `https://pc.griffin-luma.ts.net:1002` |
| 1003 | Beszel | `https://pc.griffin-luma.ts.net:1003` |
| 1004 | AdGuard Home | `https://pc.griffin-luma.ts.net:1004` |
| 1005 | Nextcloud | `https://pc.griffin-luma.ts.net:1005` |
| 1006 | FileBrowser | `https://pc.griffin-luma.ts.net:1006` |
| 1007 | Speedtest Tracker | `https://pc.griffin-luma.ts.net:1007` |
| 1008 | Netdata | `https://pc.griffin-luma.ts.net:1008` |

`tailscale serve status` should list nine entries. If one is wrong, see [E3](#e3-path-based-addresses-break-apps).

### Phase 7: Immich

**1. Download the four images one at a time.** They come from GitHub's registry, which throttles parallel downloads with a `toomanyrequests` error ([B5](#b5-toomanyrequests-from-githubs-container-registry)). If one fails, wait a minute and run that line again:

```bash
docker pull ghcr.io/immich-app/immich-server:release
docker pull ghcr.io/immich-app/immich-machine-learning:release
docker pull ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:bcf63357191b76a916ae5eb93464d65c07511da41e3bf7a8416db519b40b1c23
docker pull docker.io/valkey/valkey:9@sha256:c123e3715db63d06d4ad6964884037aa0d5d4d703939b9929954112889708e1d
```

**2. Create a stack named `immich`:**

```yaml
name: immich

services:
  immich-server:
    container_name: immich_server
    image: ghcr.io/immich-app/immich-server:${IMMICH_VERSION:-release}
    volumes:
      - ${UPLOAD_LOCATION}:/data
      - /etc/localtime:/etc/localtime:ro
    env_file:
      - stack.env
    ports:
      - '2283:2283'
    depends_on:
      - redis
      - database
    restart: always
    healthcheck:
      disable: false

  immich-machine-learning:
    container_name: immich_machine_learning
    image: ghcr.io/immich-app/immich-machine-learning:${IMMICH_VERSION:-release}
    volumes:
      - model-cache:/cache
    env_file:
      - stack.env
    restart: always
    healthcheck:
      disable: false

  redis:
    container_name: immich_redis
    image: docker.io/valkey/valkey:9@sha256:c123e3715db63d06d4ad6964884037aa0d5d4d703939b9929954112889708e1d
    healthcheck:
      test: redis-cli ping | grep -q PONG || exit 1
    restart: always

  database:
    container_name: immich_postgres
    image: ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:bcf63357191b76a916ae5eb93464d65c07511da41e3bf7a8416db519b40b1c23
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_USER: ${DB_USERNAME}
      POSTGRES_DB: ${DB_DATABASE_NAME}
      POSTGRES_INITDB_ARGS: '--data-checksums'
      DB_STORAGE_TYPE: 'HDD'
    volumes:
      - ${DB_DATA_LOCATION}:/var/lib/postgresql/data
    shm_size: 128mb
    restart: always
    healthcheck:
      disable: false

volumes:
  model-cache:
```

`DB_STORAGE_TYPE: 'HDD'` is Immich's setting for a database that is not on an SSD, which is the case here. In **Environment variables**, in advanced mode:

```
UPLOAD_LOCATION=/mnt/storage/immich
DB_DATA_LOCATION=/home/brandon/immich/postgres
TZ=America/New_York
IMMICH_VERSION=release
DB_PASSWORD=your-own-key
DB_USERNAME=postgres
DB_DATABASE_NAME=immich
```

Use letters and numbers only for the password. Deploy it, then check:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
docker exec immich_server df -h /data
ls -a /mnt/storage/immich
```

All four containers should be `healthy` or `Up`, `/data` should show `/dev/sda1` at about 916G, and the folder should list `backups encoded-video library profile thumbs upload`. Open `http://192.168.1.198:2283` and create the admin account. Wait for Immich to settle before Phase 8 ([A10](#a10-immich-and-nextcloud-overload-the-machine-when-they-start-together)).

### Phase 8: Nextcloud

**1. Choose your values.** `NC_ADMIN_USER`, `NC_ADMIN_PASSWORD` and `NC_DB_PASSWORD`, using letters and numbers only. Nextcloud reads them once, at the first start. Changing them in Portainer afterwards does nothing.

**2. Create a stack named `nextcloud`.** The two addresses with `1005` must match the Tailscale port from Phase 6:

```yaml
services:
  db:
    image: postgres:16-alpine
    container_name: nextcloud_db
    restart: always
    environment:
      POSTGRES_DB: nextcloud
      POSTGRES_USER: nextcloud
      POSTGRES_PASSWORD: ${NC_DB_PASSWORD}
    volumes:
      - /home/brandon/nextcloud/db:/var/lib/postgresql/data

  redis:
    image: redis:alpine
    container_name: nextcloud_redis
    restart: always

  app:
    image: nextcloud:apache
    container_name: nextcloud
    restart: always
    depends_on:
      - db
      - redis
    ports:
      - "8082:80"
    environment:
      POSTGRES_HOST: db
      POSTGRES_DB: nextcloud
      POSTGRES_USER: nextcloud
      POSTGRES_PASSWORD: ${NC_DB_PASSWORD}
      REDIS_HOST: redis
      NEXTCLOUD_ADMIN_USER: ${NC_ADMIN_USER}
      NEXTCLOUD_ADMIN_PASSWORD: ${NC_ADMIN_PASSWORD}
      NEXTCLOUD_DATA_DIR: /data
      NEXTCLOUD_TRUSTED_DOMAINS: "192.168.1.198 pc.griffin-luma.ts.net"
      OVERWRITEPROTOCOL: https
      OVERWRITEHOST: pc.griffin-luma.ts.net:1005
      OVERWRITECLIURL: https://pc.griffin-luma.ts.net:1005
      TRUSTED_PROXIES: "172.16.0.0/12 192.168.1.198"
      PHP_UPLOAD_LIMIT: 10G
    volumes:
      - /home/brandon/nextcloud/html:/var/www/html
      - /mnt/storage/nextcloud:/data

  cron:
    image: nextcloud:apache
    container_name: nextcloud_cron
    restart: always
    entrypoint: /cron.sh
    depends_on:
      - db
      - redis
    volumes:
      - /home/brandon/nextcloud/html:/var/www/html
      - /mnt/storage/nextcloud:/data
```

Environment variables:

```
NC_ADMIN_USER=your-admin-name
NC_ADMIN_PASSWORD=your-own-key
NC_DB_PASSWORD=your-own-key
```

**3. Wait for the install.** It takes 2 to 15 minutes on this machine. Watch it, and press `Ctrl+C` when Apache is ready (that only stops the log view):

```bash
docker logs -f nextcloud
```

Then check:

```bash
docker exec nextcloud df -h /data
sudo ls -a /mnt/storage/nextcloud
```

`/data` should show `/dev/sda1`, and the folder should contain `.ncdata`, an `appdata_...` folder and a folder named for your login. Open `https://pc.griffin-luma.ts.net:1005` and log in with your admin name and password. Then change the admin password to a new one inside Nextcloud. See [D5](#d5-a-502-right-after-deploying-nextcloud) if the page shows a 502 at first.

### Phase 9: Speedtest Tracker and Netdata

**Speedtest Tracker.** Generate the app key and download the image:

```bash
echo "base64:$(openssl rand -base64 32 2>/dev/null)"
docker pull lscr.io/linuxserver/speedtest-tracker:latest
```

Copy the whole key including the `base64:` at the start. Create a stack named `speedtest-tracker` and put the key in the `APP_KEY` line:

```yaml
services:
  speedtest-tracker:
    image: lscr.io/linuxserver/speedtest-tracker:latest
    container_name: speedtest-tracker
    restart: unless-stopped
    ports:
      - "8088:80"
    environment:
      PUID: "1000"
      PGID: "1000"
      APP_KEY: "base64:your-own-key"
      APP_DEBUG: "false"
      APP_URL: "http://192.168.1.198:8088"
      DB_CONNECTION: sqlite
    volumes:
      - /home/brandon/speedtest-tracker:/config
```

Create the folder first with `mkdir -p ~/speedtest-tracker`. I deployed this stack without the `volumes:` lines in Phase 9, and that cost me the app's data on 2026-10-23, when I updated it ([B6](#b6-a-container-starts-empty-after-update-the-stack)). The lines are there now.

Open `http://192.168.1.198:8088` and log in with `admin@example.com` and `password`, then change both in your profile. Then create an API token at `http://192.168.1.198:8088/admin/api-tokens` with the **Read Results** ability, and run one speed test from the dashboard. Verify the token with:

```bash
curl -s -H "Accept: application/json" -H "Authorization: Bearer your-own-key" http://192.168.1.198:8088/api/v1/results/latest | head -c 300
```

You should see JSON with your speeds. If you get a 500 error on the first page, see [G6](#g6-the-speedtest-tracker-card-shows-an-error).

**Netdata.** Create a stack named `netdata`:

```yaml
version: '3'
services:
  netdata:
    image: netdata/netdata
    restart: always
    ports:
      - "19999:19999"
    cap_add:
      - SYS_PTRACE
    security_opt:
      - apparmor:unconfined
    volumes:
      - netdataconfig:/etc/netdata
      - netdatalib:/var/lib/netdata
      - netdatacache:/var/cache/netdata
      - /etc/passwd:/host/etc/passwd:ro
      - /etc/group:/host/etc/group:ro
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /etc/os-release:/host/etc/os-release:ro

volumes:
  netdataconfig:
  netdatalib:
  netdatacache:
```

Check it with `docker ps --format "table {{.Names}}\t{{.Status}}"` and `uptime`. The container is named `netdata-netdata-1`. Open `http://192.168.1.198:19999`. If it asks for a session ID, read it with `docker exec netdata-netdata-1 cat /var/lib/netdata/netdata_random_session_id`.

### Phase 10: Homepage

**1. Download the image:**

```bash
docker pull ghcr.io/gethomepage/homepage:latest
```

**2. Put the config files in `/home/brandon/homepage-config/`.** They are in the `homepage-config/` folder of the repository. The easiest way is to clone the repository on the server:

```bash
sudo apt install git -y
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git ~/My-Home-Lab-
cp ~/My-Home-Lab-/homepage-config/* ~/homepage-config/
cd ~/homepage-config
sed -i 's/192\.168\.X\.X/192.168.1.198/g; s/your-tailnet\.ts\.net/griffin-luma.ts.net/g' services.yaml
```

The `sed` line puts the real address and Tailscale name into the placeholders. You can also copy the files from Windows with `scp` in PowerShell, or drag them into the folder in VS Code Remote-SSH.

**3. Create a stack named `homepage`:**

```yaml
services:
  homepage:
    image: ghcr.io/gethomepage/homepage:latest
    container_name: homepage
    restart: unless-stopped
    ports:
      - 3001:3000
    environment:
      HOMEPAGE_ALLOWED_HOSTS: 192.168.1.198:3001,pc.griffin-luma.ts.net:1000,localhost:3001
    volumes:
      - /home/brandon/homepage-config:/app/config
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /:/host:ro
      - /mnt/storage:/mnt/storage:ro
```

Open `http://192.168.1.198:3001`. The cards and the styling should appear. Widgets show errors until you fill in their keys.

**4. Fill in the keys. Stop Homepage first,** so a widget with a wrong login doesn't retry every few seconds ([D7](#d7-nextcloud-returns-429-reached-maximum-delay)):

```bash
docker stop homepage
nano /home/brandon/homepage-config/services.yaml
```

Replace every `your-own-key`:

| Card | Value and where to get it |
| :--- | :--- |
| AdGuard Home | The login from the AdGuard setup wizard |
| Tailscale | `deviceid`: the `pc` machine's ID in the admin console (ends in `CNTRL`). `key`: an API access token from the admin console, the whole `tskey-api-...` text |
| Beszel | The superuser login: `docker exec beszel /beszel superuser upsert your-email@example.com your-own-key`, then the same email and password |
| Speedtest Tracker | The token from Phase 9 |
| Portainer | An access token (your name, **My account**, **Access tokens**) and the `env` number from the address bar. Mine is `3` |
| FileBrowser | `admin` and the password you set |
| Immich | An API key from Immich's account settings |
| Nextcloud | A token made with the commands below |

For Nextcloud, make a random token, store it, and print it:

```bash
TOKEN=$(openssl rand -hex 24)
docker exec -u www-data nextcloud php occ config:app:set serverinfo token --value=$TOKEN
echo $TOKEN
```

Then start Homepage:

```bash
docker start homepage
```

Wait a minute and reload the page with `Ctrl+Shift+R`. Check:

```bash
docker logs homepage --tail 30
docker exec homepage df -h /mnt/storage
```

Every card should show a green dot and a live widget. The second command should show `/dev/sda1`. For the individual widget errors I hit, see [G3](#g3-the-beszel-widget-says-no-items-returned) to [G8](#g8-yaml-indentation-mistakes).

### Phase 11: Point devices at AdGuard Home

My router wouldn't let me change its DNS setting, so I set the DNS server on each device by hand. Devices I don't change aren't filtered.

**Windows 11 (Ethernet):**

1. Open **Settings**, then **Network and internet**, then **Ethernet**.
1. Next to **DNS server assignment**, click **Edit**.
1. Choose **Manual**, switch **IPv4** on, and enter `192.168.1.198` as the preferred DNS and `8.8.8.8` as the alternate.
1. Click **Save**, then run `nslookup google.com` in a terminal. The server shown should be `192.168.1.198`.

**iPhone (Wi-Fi):**

1. Open **Settings**, then **Wi-Fi**, then tap the **i** next to the network.
1. Tap **Configure DNS**, then **Manual**.
1. Remove any existing servers, add `192.168.1.198` and `8.8.8.8`, and tap **Save**.

Check in AdGuard Home's dashboard: the **Top clients** list should show the devices, and the query count should rise as you browse. See [F3](#f3-devices-are-not-using-adguard-home) for what the alternate server means.

### Phase 12: Recovery script, reboot test and final inventory

Create the recovery script (this was the first version, with a fixed list of containers. Phase 15 replaced it with the version in [Step 6](#step-6-the-recovery-command)), then test it without unplugging anything. It stops the five containers, unmounts and remounts the drive, and starts them again. That takes about a minute:

```bash
sudo hdd-recover
```

You should end with `Recovered.`. Confirm everything is back:

```bash
findmnt /mnt/storage
docker ps --format "table {{.Names}}\t{{.Status}}"
docker exec immich_server df -h /data
docker exec nextcloud df -h /data
```

Then run the reboot test from [Step 8](#step-8-verify-it), and run the inventory script from [section 5](#52-the-inventory-script) again. It should show all nine stacks running, the data drive at `/mnt/storage`, and every container seeing `/dev/sda1`.

### Phase 13: Nextcloud and Immich integration, and the phone

The `integration_immich` app (version 1.5.1) shows the Immich photos through Nextcloud. The steps, in order:

```bash
docker exec -u www-data nextcloud php occ config:system:set allow_local_remote_servers --value=true --type=boolean
docker exec -u www-data nextcloud php occ config:system:get allow_local_remote_servers
docker exec -u www-data nextcloud php -r 'echo file_get_contents("http://192.168.1.198:2283/api/server/ping");'
docker exec -u www-data nextcloud php occ app:list | grep -i immich
```

1. In Immich, create an API key named `nextcloud` (profile picture, **Account Settings**, **API Keys**, **New API Key**, all permissions). Copy it, because it's shown once.
1. Run the first two commands. The second should print `true`.
1. Run the third command. It should print `{"res":"pong"}`.
1. In Nextcloud, click your avatar, then **Apps**, search for `Immich`, and click **Download and enable** on the Immich integration. The fourth command should then list `integration_immich` with its version.
1. Click your avatar, then **Personal settings**, then **Immich Integration**. Enter `http://192.168.1.198:2283` (no `/photos` and no `/api`) and the API key, click **Test connection**, then **Save**.

If the test fails, see [D4](#d4-the-immich-integration-says-local-ip-blocked) and [D9](#d9-the-immich-integration-test-fails-with-an-authentication-error).

**Phone.** The phone has Tailscale. In the Immich app, enter the server address `http://192.168.1.198:2283` at home, or `https://pc.griffin-luma.ts.net:1002` when away (with Tailscale on). Log in and turn on backup. Immich is the only phone app set up so far.

### Phase 14: The Lenovo

The Lenovo is kept as a separate machine, still on the tailnet. Nothing on the ProDesk depends on it. Its old Tailscale addresses (the ones on ports 8441 to 8447 and 9444) are no longer used by any device. If you want to clear them from the Lenovo, run this on the Lenovo:

```bash
sudo tailscale serve reset
```

If the Lenovo's AdGuard Home is still running, stop it, so no device gets answers from two different DNS servers. The ProDesk is the only DNS server for the devices configured in Phase 11.

### Phase 15: Drive pools and the daily backup

Done on 2026-10-22, after the migration was finished and every service was running. It turns the single data drive into a pool that more drives can join, adds a daily backup, and replaces `hdd-recover`. I did it one step at a time and checked each result before the next. Steps 0 to 4 didn't touch my real data.

**Decisions**

- **Two pools, both mergerfs.** Main storage is `/mnt/storage` (labels `MAIN1`, `MAIN2` and so on) and backup storage is `/mnt/backup` (`BACKUP1`...). Every drive is a normal ext4 drive mounted by UUID under `/mnt/disks/`.
- **mergerfs, not RAID.** If a drive fails, only the files on that drive are lost from its pool, instead of everything.
- **Backup with `rsync`, every day at 6:00.** Files I delete or replace go into a dated folder and are kept for 30 days. The Nextcloud database is dumped as part of the run. The backup drives sleep when idle (untested, see Step 5).
- **The backup can be browsed from FileBrowser in read and write mode** (planned for when the backup pool exists).
- **For now the backup lives on the boot drive**, in `/home/brandon/750GB_HDD/backup-interim`, until a backup drive is bought.
- **No change to any stack.** The pool takes over the path `/mnt/storage`.

**Step 0: put the files on the server and check them.** I unzipped `homelab-drives.zip` on the Windows PC and dragged the folder into `/home/brandon` with VS Code:

```bash
cd ~/homelab-drives && sha256sum -c SHA256SUMS
grep -c $'\r' ~/homelab-drives/drives ~/homelab-drives/hdd-recover ~/homelab-drives/homelab-backup
```

```
drives: OK
hdd-recover: OK
homelab-backup: OK
homelab-backup.conf.example: OK
GUIDE.md: OK
/home/brandon/homelab-drives/drives:0
/home/brandon/homelab-drives/hdd-recover:0
/home/brandon/homelab-drives/homelab-backup:0
```

That was the list at the time. Later the `GUIDE.md` line was dropped and `homelab` was added ([Step 9](#step-9-the-cheat-sheet-at-login)), so `SHA256SUMS` now lists five files: `drives`, `homelab-backup`, `hdd-recover`, `homelab-backup.conf.example` and `homelab`.

**Step 1: check the server and install the tools.** Details and versions are in [section 2, Step 1](#step-1-install-the-tools-and-scripts).

**Step 2: install `drives` and `homelab-backup`.** `hdd-recover` is not replaced yet:

```bash
cd ~/homelab-drives
sudo install -m 755 drives /usr/local/sbin/drives
sudo install -m 755 homelab-backup /usr/local/sbin/homelab-backup
sudo drives version
sudo drives status
```

`status` looked as shown in section 2, Step 1: `main /mnt/storage mounted (ext4)`, `backup /mnt/backup NOT MOUNTED`, the Toshiba as `current data drive (plain, not in a pool yet)` and the Hitachi as `boot/system drive (never touched)`.

**Step 3: practise with fake drives.** Test mode uses disk-image files and its own folders and fstab (`/mnt/test-main`, `/mnt/test-backup`, `/mnt/test-disks`), so my real drives, `/etc/fstab` and containers are not touched:

```bash
sudo DRIVES_TEST=1 drives test-setup 3 1G
sudo DRIVES_TEST=1 drives
```

I connected the fake drives as `TMAIN1` (main) and `TBACKUP1` (backup). The script asks for the device name and then `ERASE`, and it cancels with `Cancelled. Nothing was changed.` if either is wrong, which I saw twice when I pressed Enter without typing anything. The status then showed both pools mounted as `fuse.mergerfs` with `TMAIN1` and `TBACKUP1` connected, and the Toshiba as `not connected to a pool`. Trying to disconnect the only main drive was refused:

```
TMAIN1 is the only main drive. Removing it would take away the storage your services use.
Add another main drive first (menu option 2), then try again.
```

Removing the only backup drive asked me to type `REMOVE` first, and then said the data on the drive was not touched. A second practice run with two 4 GB fake drives tested the copy-before-removing step. I wrote two 200 MB random files into the pool, one landed on each drive, and disconnected `TMAIN1`, answering `y` to copy its files first:

```
Copying 201MB from TMAIN1 to TMAIN2 (pass 1, services keep running)...
Pass 2 (catching changes made during the first pass)...
Verified: every file from TMAIN1 is also on TMAIN2.
TMAIN1 is disconnected from the main storage. The data on the drive was not touched.
```

`sha256sum` of both files was identical before and after (`d81cd063...` and `b0e124b9...`). Then I removed the test setup and checked that `status` was back to how it looked in Step 2:

```bash
sudo DRIVES_TEST=1 drives test-cleanup
sudo drives status
```

**Step 4: practise with the 8 GB USB stick** (it gets erased). The stick showed up as `/dev/sdc`, exFAT, 7.2 GB, and was the only drive in the connect list, because the boot drive and the Toshiba are never offered. I connected it as `TMAIN1` in test mode, saw it as `connected` in `status`, and the script again refused to remove the only main drive. I closed the menu without running `test-cleanup`, which left the test pool mounted (see [A11](#a11-the-practice-pool-is-still-mounted-after-test-mode)). After running it, this printed nothing, which is correct:

```bash
sudo DRIVES_TEST=1 drives test-cleanup
findmnt -rn | grep -E 'test-main|test-disks'
```

`lsblk` then showed the stick's partition mounted at `/media/brandon/TMAIN1`. That is the desktop auto-mounting the freshly formatted stick, and is harmless.

**Step 5: replace `hdd-recover`.** I saved the old script first, installed the new one and ran it. The containers restarted for about a minute:

```bash
sudo cp /usr/local/bin/hdd-recover /usr/local/bin/hdd-recover.old
sudo install -m 755 ~/homelab-drives/hdd-recover /usr/local/bin/hdd-recover
sudo hdd-recover
docker ps --format "table {{.Names}}\t{{.Status}}"
```

It stopped and started exactly `filebrowser-filebrowser-1 homepage immich_server nextcloud nextcloud_cron`, printed `Recovered.`, and all 16 containers were up again a few minutes later. The old script, for reference (a fixed list of five names, no pools):

```bash
#!/bin/bash
docker stop immich_server filebrowser-filebrowser-1 homepage nextcloud nextcloud_cron
umount -l /mnt/storage 2>/dev/null; sleep 2
mount /mnt/storage || { echo "Drive not found. Check the cable."; exit 1; }
hdparm -S 0 -B 254 "/dev/$(lsblk -no pkname "$(readlink -f /dev/disk/by-label/STORAGE)")" 2>/dev/null
docker start immich_server filebrowser-filebrowser-1 homepage nextcloud nextcloud_cron
echo "Recovered."
```

**Step 6: start the daily backup, onto the boot drive.** Details, log lines and sizes are in [section 2, Step 7](#step-7-the-daily-backup). The first run started at 19:04 and finished at 19:28 with `finished: OK in 1420s`, and both `/mnt/storage` and the copy were `61G`. Then I added the schedule with `sudo crontab -e`:

```cron
0 6 * * * /usr/local/sbin/homelab-backup
```

**Step 7a: convert the Toshiba into the main pool.** I did this only after Step 6 had made a verified backup from the same day. `sudo drives adopt` is shown in [section 2, Step 2](#step-2-add-the-main-drive). The containers were stopped for about a minute. Each container then showed `mergerfs-main  916G  61G  855G  7%` for `/data`, and `status` listed `MAIN1` as `connected` with SMART `PASSED`. No stack needed an edit. The first check I tried, `findmnt /mnt/storage /mnt/disks/MAIN1`, printed nothing (see [A12](#a12-findmnt-prints-nothing-when-given-two-paths)).

**Step 7b: update root's crontab.** The old lines pointed at a drive labelled `STORAGE`, which no longer exists. I saved a copy, then applied the change with one `sed`. It replaces the old `hdparm` line with `drives power` and changes the label in the load-cycle line:

```bash
sudo crontab -l > ~/crontab-before-step7.txt
```

```bash
sudo crontab -l | sed -e 's|^@reboot sleep 60 && /usr/sbin/hdparm -S 0 -B 254 .*by-label/STORAGE.*$|@reboot sleep 60 \&\& /usr/local/sbin/drives power >/dev/null 2>\&1|' -e 's|by-label/STORAGE|by-label/MAIN1|' | sudo crontab -
```

```bash
sudo crontab -l | grep -v '^#'
```

```
@reboot sleep 60 && /usr/local/sbin/drives power >/dev/null 2>&1
0 6 * * * echo "$(date +\%F) $(smartctl -A -d sat /dev/disk/by-label/MAIN1 | awk '/Load_Cycle/ {print $10}')" >> /var/log/loadcycles.log
@reboot sleep 60 && /usr/sbin/hdparm -B 254 "/dev/$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)")"
0 6 * * * /usr/local/sbin/homelab-backup
```

The first time, the saved copy was restored by accident right after the change, because I ran the "undo" command in the same block (see [A14](#a14-the-crontab-went-back-to-the-old-lines)). I ran the `sed` again, which fixed it. Then `sudo drives power` printed the two power lines, and `sudo hdparm -B /dev/sda` printed `APM_level      = 254`. A first attempt to read the setting with `sudo hdparm -B -S /dev/sda` printed `-S: bad/missing standby-interval value (0..255)` (see [A13](#a13-hdparm--b--s-says-bad-or-missing-standby-interval)).

**Step 7c: reboot test.** After `sudo reboot` and about five minutes:

```
TARGET       SOURCE        FSTYPE        OPTIONS
/mnt/storage mergerfs-main fuse.mergerfs rw,relatime,user_id=0,group_id=0,default_permissions,allow_oth
TARGET           SOURCE    FSTYPE OPTIONS
/mnt/disks/MAIN1 /dev/sda1 ext4   rw,noatime
```

All 16 containers were up. Fourteen had been up for 5 minutes, while Homepage showed `Up 30 seconds` and Portainer `Up 23 seconds`, so those two had restarted once after the boot. I didn't investigate why. About two hours later every container showed `Up 2 hours`, so neither has restarted again. `sudo drives status` still showed `MAIN1` connected and the last backup as `OK`. `systemctl --failed` listed one unit, `casper-md5check.service` (it verifies the live installer ISO and has nothing to do with the drives). `/var/log/homelab-drives.log` recorded `adopted /dev/sda1 as MAIN1; pool at /mnt/storage` and the power settings being applied. The last entry, at 20:45, is the cron job running after the reboot.

The first scheduled 6:00 backup was the next morning, 2026-10-23.

---

## 4. Troubleshooting

Each entry has the same four parts: Symptom, Cause, Fix and Verify. Entries written before Phase 15 show the data drive as `/dev/sda1` in the `df` checks. Since the drive became a pool, the same checks show `mergerfs-main` instead, and everything else in them still applies.

### A. Drives and storage

#### A1. The data drive comes back under a different path after a replug

**Symptom:** after unplugging and replugging the drive, FileBrowser can't see it and the Homepage drive pill is blank.

**Cause:** the desktop mounts external drives under `/media/brandon/<label>`, not at the path the stacks use. Containers also keep the old view of the drive.

**Fix:** with the setup in [section 2](#2-storage-setup-that-works), run:

```bash
sudo hdd-recover
```

Before the fixed mount existed (on the Lenovo, with the old NTFS drive), this was the manual fix:

```bash
lsblk -f
ls /media/brandon/
sudo mount -t ntfs-3g -o uid=1000,gid=1000 /dev/sdb2 "/media/brandon/USB STICK"
docker restart filebrowser-filebrowser-1 homepage
```

**Verify:** `findmnt /mnt/storage` shows the drive, and the `df` checks from [Step 8](#step-8-verify-it) show the pool in each container.

#### A2. A Windows-formatted drive: sdb1 vs sdb2 and the wrong filesystem type error

**Symptom:** mounting fails with `wrong fs type, bad option, bad superblock on /dev/sdb1`.

**Cause:** a drive formatted by Windows has a small first partition (`sdb1`) with no filesystem, and the data is on `sdb2`.

**Fix:** list the partitions and mount the one that shows a filesystem:

```bash
lsblk -f
sudo mount -t ntfs-3g -o uid=1000,gid=1000 /dev/sdb2 "/media/brandon/USB STICK"
```

If `ntfsfix` says `Refusing to operate on read-write mounted device`, ignore it. `ntfsfix` only works on an unmounted drive, and it's only needed if the mount itself fails with a "dirty" message.

**Verify:** `ls "/media/brandon/USB STICK"` lists your files.

#### A3. The mount is refused because the NTFS volume is already exclusively opened

**Symptom:** `Mount is denied because the NTFS volume is already exclusively opened.`

**Cause:** the desktop had already mounted the drive at `/media/brandon/1TB HDD`, so a second mount at another path is refused. The folder you tried to mount onto was then just an empty folder on the boot drive, and anything written there went to the wrong drive.

**Fix:** unmount the desktop's copy and mount the drive from `/etc/fstab` at the fixed path:

```bash
findmnt "/media/brandon/USB STICK"
sudo umount "/media/brandon/1TB HDD"
sudo systemctl daemon-reload
sudo mount -a
findmnt "/media/brandon/USB STICK"
```

The first command should print nothing. The last should show `/dev/sdb2`. The ext4 setup in [section 2](#2-storage-setup-that-works) avoids this by mounting at `/mnt/storage`.

**Verify:** `findmnt` shows the drive at the fixed path.

#### A4. Immich's database keeps restarting on an NTFS drive

**Symptom:** in Portainer, `immich_postgres` and `immich_server` keep restarting. The same stack worked when the folder was on the internal drive.

**Cause:** the database folder was on the NTFS drive. Postgres needs a Linux filesystem so it can set file owners and permissions on its data.

**Fix:** keep the database on the boot drive and only the photos on the data drive. In the stack's environment variables:

```
UPLOAD_LOCATION=/mnt/storage/immich
DB_DATA_LOCATION=/home/brandon/immich/postgres
```

```bash
mkdir -p /home/brandon/immich/postgres
```

If a half-built database was left on the data drive, delete only the folder you created for it. Don't delete anything else. A spin-down setting can also cause slow starts and failed health checks, so turn it off:

```bash
sudo hdparm -S 0 /dev/sda
```

**Verify:**

```bash
docker ps
docker logs immich_postgres --tail 20
docker logs immich_server --tail 20
```

Both containers should show `healthy` or `Up`.

#### A5. Immich is writing to the boot drive because the data drive was not mounted

**Symptom:** Immich's storage meter shows the boot drive's size, `docker exec immich_server df -h /data` shows the boot drive's device, and `findmnt -T /mnt/storage/immich` shows `/`.

**Cause:** the folder was created, or the stack started, while the data drive wasn't mounted. The folder was then created on the boot drive.

**Fix:** stop the Immich stack in Portainer, mount the drive, copy the photos over and start the stack. These were the commands on the old NTFS setup:

```bash
sudo mv "/media/brandon/USB STICK/1TB HDD/immich" /home/brandon/immich-ssd-copy
mkdir -p "/media/brandon/USB STICK/1TB HDD/immich"
rsync -rt --no-perms --no-owner --no-group --info=progress2 /home/brandon/immich-ssd-copy/ "/media/brandon/USB STICK/1TB HDD/immich/"
du -sh /home/brandon/immich-ssd-copy "/media/brandon/USB STICK/1TB HDD/immich"
```

The two sizes should match. Once Immich shows your photos from the data drive, free the space with `sudo rm -rf /home/brandon/immich-ssd-copy`. The lasting fix is the locked mount point and the Docker wait rule from [Step 2](#step-2-add-the-main-drive), which make a missing drive stop the service with an error.

**Verify:**

```bash
docker exec immich_server df -h /data
findmnt -T /mnt/storage/immich
```

The first should show about 916G on `/dev/sda1`, and the second should show the data drive as its source.

#### A6. Containers show an old or empty drive after an unplug

**Symptom:** the drive is mounted again, but Immich, FileBrowser, Nextcloud or Homepage still show an empty folder or no space.

**Cause:** a container keeps the mount it had when it started.

**Fix:**

```bash
sudo hdd-recover
```

Before you unplug a drive on purpose, open `sudo drives` and choose **3** (Disconnect a drive). It stops the containers that use the pool and unmounts the drive for you. (Before the pool existed, the manual way was: stop the stacks, run `sudo umount /mnt/storage`, plug the drive back in, run `sudo mount /mnt/storage` and start the stacks.)

**Verify:** the `df` commands in [Step 8](#step-8-verify-it) show the pool in each container.

#### A7. Containers start before the drive is mounted after a reboot

**Symptom:** after a reboot, a container shows the boot drive or an empty folder, or fails to start.

**Cause:** Docker started containers before the drive was mounted.

**Fix:** add the wait rule if it's missing (it's in [Step 2](#step-2-add-the-main-drive)):

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
printf '[Unit]\nWants=mnt-storage.mount\nAfter=mnt-storage.mount\n' | sudo tee /etc/systemd/system/docker.service.d/wait-for-hdd.conf
sudo systemctl daemon-reload
```

If a drive of the pool is missing at boot, the pool does not mount, and the locked mount point makes the services fail with an error, so they don't write to the boot drive. Plug the drive in and run `sudo hdd-recover`. I tested the missing-drive case with fake drives, not on my real hardware.

**Verify:** after `sudo reboot`, run `findmnt /mnt/storage` and `docker ps`.

#### A8. The head-parking count is high

**Symptom:** the SMART `Load_Cycle_Count` is high and climbing (the data drive's was 105,642 and the boot drive's 48,421 after under 2,000 hours), and `hdparm -B` shows `APM_level = 128`.

**Cause:** at level 128, laptop drives park their heads after a few seconds of idle. Many are rated for about 300,000 parks.

**Fix:**

```bash
DATA=$(lsblk -no pkname "$(readlink -f /dev/disk/by-label/MAIN1)")
BOOT=$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)")
sudo smartctl -A -d sat /dev/disk/by-label/MAIN1 | grep -E "Power_On_Hours|Load_Cycle|Reallocated_Sector|Current_Pending"
sudo hdparm -B /dev/$DATA
sudo hdparm -B 254 /dev/$DATA
sudo hdparm -B /dev/$DATA
```

The last command should print `APM_level = 254`. Do the same for the boot drive with `/dev/$BOOT`. The `SG_IO: bad/missing sense data` messages are common with USB adapters and can be ignored. Keep the setting after reboots with the cron lines from [Step 5](#step-5-drive-power-settings-and-cron-lines). The `drives power` line there applies it to every pool drive. If the count still climbs by hundreds a day, try `sudo hdparm -B 255 /dev/$DATA`.

**Verify:** the boot drive's count stayed at 48,421 after the change, and the data drive's rose only from 105,799 to 105,835 over a few hours. With the logging line from Step 5, `cat /var/log/loadcycles.log` shows one number a day. Under about 50 a day is healthy.

#### A9. The cron job logs a date with no number

**Symptom:** `/var/log/loadcycles.log` has a date but no count after it.

**Cause:** cron runs with a short search path that doesn't include `/usr/sbin`, where `smartctl` lives.

**Fix (only if the number is blank):** add this as the first line of root's crontab:

```bash
sudo crontab -e
```

```
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

**Verify:** `sudo crontab -l` shows the line, and the log has a number after the next morning's date.

#### A10. Immich and Nextcloud overload the machine when they start together

**Symptom:** `immich_server` shows `(unhealthy)` for a long time, its log is full of `could not renew lock for job` and `Missing lock for job` errors, `uptime` shows a load average of about 7.8 on a 4-core machine, and the Nextcloud install looks stuck: the log stops at `Starting nextcloud installation` and the data folder holds only `nextcloud.log`.

**Cause:** the two stacks started at the same time on a single hard-drive boot disk. Immich's background-job queue stalls under the load, and the Nextcloud install is slow. It is not a real error.

**Fix:** wait, and don't deploy anything else. Check progress without following the log:

```bash
uptime
docker logs immich_server --tail 40
curl -s http://192.168.1.198:2283/api/server/ping
docker logs nextcloud --tail 15
sudo ls -a /mnt/storage/nextcloud
```

A healthy Immich answers the ping with `{"res":"pong"}`. The Nextcloud install is finished when the folder lists `.ncdata`, an `appdata_...` folder and your login folder. On my machine the load fell to about 0.05 after 10 to 15 minutes, and Immich turned healthy by itself.

**Verify:** `docker ps --format "table {{.Names}}\t{{.Status}}"` shows every Immich container `healthy`. To prevent it, deploy Immich, wait for it to turn healthy, and only then deploy Nextcloud.

#### A11. The practice pool is still mounted after test mode

**Symptom:** after practising with `DRIVES_TEST=1 drives` and closing the menu, the USB stick is still mounted in the practice pool (under `/mnt/test-disks` and `/mnt/test-main`). The normal `sudo drives status` doesn't show that: it lists the stick as `/dev/sdc   7.2G  USB DISK 2.0  [usb]   not connected to a pool`, so it looks as if nothing is left over.

**Cause:** test mode keeps its pools mounted until you run `test-cleanup`. I closed the menu after the USB stick practice and didn't run it.

**Fix:**

```bash
sudo DRIVES_TEST=1 drives test-cleanup
```

It unmounts the practice pools and drives, detaches the fake drives and deletes the image files and the test fstab.

**Verify:** this prints nothing:

```bash
findmnt -rn | grep -E 'test-main|test-disks'
```

A USB stick you practised with may still appear in `lsblk` under `/media/brandon/TMAIN1`. That is the desktop auto-mounting the freshly formatted stick. Unmount it from the file manager, or format it again if you want it back as a normal stick.

#### A12. findmnt prints nothing when given two paths

**Symptom:** right after `sudo drives adopt`, `findmnt /mnt/storage /mnt/disks/MAIN1` printed nothing at all, and it looked as if neither the pool nor the drive was mounted.

**Cause:** `findmnt` is meant to be given one mount point or device per command. With two, it printed nothing for me, even though both were mounted. The next commands showed both mounts correctly.

**Fix:** run one `findmnt` per command:

```bash
findmnt /mnt/storage
findmnt /mnt/disks/MAIN1
```

**Verify:** the first shows `mergerfs-main` with the type `fuse.mergerfs`, and the second shows `/dev/sda1` with the type `ext4`.

#### A13. hdparm -B -S says bad or missing standby interval

**Symptom:** `sudo hdparm -B -S /dev/sda` prints `-S: bad/missing standby-interval value (0..255)` and shows nothing else.

**Cause:** `-S` always needs a number right after it, because it sets the spin-down timeout. It can't be used to read the setting back, and as far as I know `hdparm` has no option that reads the spin-down timeout.

**Fix:** read the head-parking level with `-B` alone, and check the drive's current power state with `-C`:

```bash
sudo hdparm -B /dev/sda
sudo hdparm -C /dev/sda
```

**Verify:** the first prints `APM_level      = 254`, and the second prints `drive state is:  active/idle` for a main drive. A backup drive that has been idle for more than 10 minutes should print `standby` (I haven't been able to test that yet).

#### A14. The crontab went back to the old lines

**Symptom:** after running the `sed` command that changes root's crontab, `sudo crontab -l` shows the old lines again, with `by-label/STORAGE`, and no `drives power` line.

**Cause:** I ran the command that restores the saved copy (`sudo crontab ~/crontab-before-step7.txt`) in the same block as the change, so it replaced the new crontab with the old one.

**Fix:** run the `sed` command again. It only rewrites lines that still say `STORAGE`, so running it twice does no harm:

```bash
sudo crontab -l | sed -e 's|^@reboot sleep 60 && /usr/sbin/hdparm -S 0 -B 254 .*by-label/STORAGE.*$|@reboot sleep 60 \&\& /usr/local/sbin/drives power >/dev/null 2>\&1|' -e 's|by-label/STORAGE|by-label/MAIN1|' | sudo crontab -
```

**Verify:** `sudo crontab -l | grep -v '^#'` shows the `drives power` line and `by-label/MAIN1` in the load-cycle line. Keep an "undo" command in its own block, away from the commands that change something, so it can't be run by accident. To undo for real, use `sudo crontab ~/crontab-before-step7.txt`.

#### A15. pgrep shows nothing while the backup is running

**Symptom:** while the first backup was running (the backup folder kept growing), `pgrep -a homelab-backup` printed nothing, so it looked as if the backup had stopped.

**Cause:** the script starts with `#!/usr/bin/env bash`, so the running process is called `bash`, not `homelab-backup`. Without `-f`, `pgrep` matches only the process name.

**Fix:** search the full command line with `-f`, or follow the log until it says `finished`:

```bash
pgrep -af homelab-backup
sudo tail -f /var/log/homelab-backup.log
```

**Verify:** while the backup runs, `pgrep -af homelab-backup` should list the process. After the log says `finished: OK`, it prints nothing, which is what I saw, and `sudo drives status` shows the result.

#### A16. install says cannot stat when installing a script

**Symptom:** running `sudo install -m 755 homelab /usr/local/bin/homelab` prints `install: cannot stat 'homelab': No such file or directory`.

**Cause:** the command names the file without a path, so it looks in the folder the terminal is in. A new terminal starts in the home folder (`/home/brandon`), and the script is in `~/homelab-drives`. The same applies to `sha256sum -c SHA256SUMS`.

**Fix:** go into the folder that holds the files, and run the command again:

```bash
cd ~/homelab-drives
ls
sudo install -m 755 homelab /usr/local/bin/homelab
```

If you cloned the repository, the folder is `~/My-Home-Lab-/homelab-drives`.

**Verify:** `ls` lists `homelab`, `install` prints nothing, and `homelab version` prints `homelab 1.0`.

### B. Docker and Portainer

#### B1. Docker installs from the wrong repository on Mint

**Symptom:** the install stops with `containerd.io : Depends: libseccomp2 (>= 2.6.0)` and `E: Unable to correct problems, you have held broken packages`.

**Cause:** Docker's install script detected the system as Debian `trixie`. Mint is based on Ubuntu, and Docker's repository needs the Ubuntu name (`noble` for Mint 22).

**Fix:**

```bash
sudo rm /etc/apt/sources.list.d/docker.list
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-ce-rootless-extras docker-buildx-plugin
```

**Verify:** `docker --version` prints a version.

#### B2. Permission denied on the Docker socket

**Symptom:** `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`.

**Cause:** your user isn't in the `docker` group in the current session.

**Fix:**

```bash
sudo usermod -aG docker $USER
sudo reboot
```

To test without rebooting, run `newgrp docker`.

**Verify:** `groups` lists `docker`, and `docker run hello-world` prints `Hello from Docker!`.

#### B3. Container names differ from the stack name

**Symptom:** `Error response from daemon: No such container: filebrowser` (or `netdata`).

**Cause:** Portainer names containers from a stack as `<stack>-<service>-<number>`. Containers with a fixed `container_name` (like `immich_server` and `nextcloud`) keep that name.

**Fix:** find the real name and use it:

```bash
docker ps -a | grep -i filebrowser
docker logs filebrowser-filebrowser-1
docker exec netdata-netdata-1 cat /var/lib/netdata/netdata_random_session_id
```

**Verify:** the command prints the container's output instead of an error. This is also why the stack names in this guide matter: the recovery script expects `filebrowser-filebrowser-1`.

#### B4. Portainer asks for a setup token, or the setup page timed out

**Symptom:** a new Portainer asks for a setup token, or says its setup timed out.

**Cause:** Portainer protects a fresh install until you claim it, and closes the first-time setup after about five minutes.

**Fix:**

```bash
docker logs portainer
docker restart portainer
```

Read the token from the logs if it asks for one. If the setup timed out, restart the container and reload `http://192.168.1.198:9000` to create your admin account.

**Verify:** you can log in and see the local environment.

#### B5. toomanyrequests from GitHub's container registry

**Symptom:** a stack fails to deploy with `failed to deploy a stack: compose up operation failed: error from registry: retry-after: 530.302µs, allowed: 44000/minute`.

**Cause:** GitHub's registry (`ghcr.io`) throttles many downloads at once. Immich's, Homepage's and Speedtest Tracker's images all come from it. It is a throttle on GitHub's side, not a problem with your machine or your file.

**Fix:** download the images one at a time first, so Portainer finds them already on the machine. If a line prints `toomanyrequests`, wait a minute and run it again:

```bash
docker pull ghcr.io/immich-app/immich-server:release
docker pull ghcr.io/immich-app/immich-machine-learning:release
docker pull ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:bcf63357191b76a916ae5eb93464d65c07511da41e3bf7a8416db519b40b1c23
docker pull docker.io/valkey/valkey:9@sha256:c123e3715db63d06d4ad6964884037aa0d5d4d703939b9929954112889708e1d
docker pull lscr.io/linuxserver/speedtest-tracker:latest
docker pull ghcr.io/gethomepage/homepage:latest
```

Then, in Portainer, open the stack and click **Update the stack** (or add the stack again with the same YAML and variables).

**Verify:** `docker images | grep -E "immich|valkey|speedtest|homepage"` lists the images, and the stack deploys with nothing to download.

#### B6. A container starts empty after Update the stack

**Symptom:** I updated Speedtest Tracker in Portainer with **Update the stack**. The container started and was healthy, and `docker logs speedtest-tracker` ended with `generating self-signed keys`, but the app behaved like a new install: the old results and settings were gone.

**Cause:** the stack had no `volumes:` line for `/config`, so Docker created an **anonymous volume** (a volume with a 64-character name and no label). When Portainer recreated the container, the new one got a new empty anonymous volume, and the old one was left behind unused. Bind mounts (a folder on the host) and named volumes are kept. Anonymous volumes are not reliably kept.

**Fix (what I did, as steps).** I had copied `/config` out of the old container with `docker cp` before updating ([7.5](#75-speedtest-tracker)), so nothing was lost.

1. Stop the container and make a folder on the host. Copy the saved data into it:

   ```bash
   docker stop speedtest-tracker
   mkdir -p ~/speedtest-tracker
   cp -a ~/speedtest-config-backup-2026-10-23/. ~/speedtest-tracker/
   ls -la ~/speedtest-tracker
   ```

   If `cp` says `Permission denied`, the files belong to another user. Use `sudo cp -a` and then `sudo chown -R 1000:1000 ~/speedtest-tracker`. The container runs as user 1000 (`PUID`).

2. In Portainer, open the `speedtest-tracker` stack, click **Editor**, and add a `volumes:` block under the service, at the same level as `ports:` and `environment:`:

   ```yaml
       volumes:
         - /home/brandon/speedtest-tracker:/config
   ```

   Click **Update the stack**.

3. Check it:

   ```bash
   docker ps --filter name=speedtest-tracker --format "table {{.Names}}\t{{.Status}}"
   ls ~/speedtest-tracker
   ```

   Open `https://pc.griffin-luma.ts.net:1007`. The earlier results should be listed again, and the Speedtest card on Homepage should turn green. Mine did, and it stayed green after a second **Update the stack**, which is the real test.

4. Add the folder to the daily backup ([section 2, Step 7](#step-7-the-daily-backup), "Extra folders").

**Prevent it.** Before you update any stack, list which containers use anonymous volumes. A volume name made of 64 letters and digits is anonymous:

```bash
docker inspect $(docker ps -q) --format '{{.Name}}: {{range .Mounts}}{{if eq .Type "volume"}}{{.Name}} {{end}}{{end}}'
```

To list only the anonymous ones:

```bash
docker inspect $(docker ps -q) --format '{{.Name}}: {{range .Mounts}}{{if eq .Type "volume"}}{{.Name}} {{end}}{{end}}' | grep -E '[0-9a-f]{64}'
```

A container on the second list needs a bind mount or a named volume before you update it. Make a copy first with `docker cp <container>:<path> ~/some-folder`.

**Verify:** the second command prints nothing for the container you are about to update, or you have a `docker cp` copy of its data.

### C. FileBrowser

#### C1. The FileBrowser login is rejected

**Symptom:** `admin` / `admin` gives "wrong credentials."

**Cause:** this version creates the `admin` user with a random password the first time it starts. The password is printed once in the container's log.

**Fix:**

```bash
docker ps
docker logs filebrowser-filebrowser-1 | grep -i password
```

The log line looks like `User 'admin' initialized with randomly generated password: ...`. Log in with it, then change it right away in your profile. If the log has no password, the database already existed from an earlier start. In that case delete the stack in Portainer, remove its `filebrowser_filebrowser_data` volume, and deploy it again for a fresh database.

**Verify:** you can log in at `http://192.168.1.198:8081`.

#### C2. The FileBrowser data folder is empty because of a folder name mismatch

**Symptom:** FileBrowser shows an empty `hdd` folder.

**Cause:** the stack pointed at a folder that doesn't exist under that exact name. On the old setup, the stack said `1TB_HDD` (with an underscore) but the real folder was `1TB HDD` (with a space). Paths with spaces also need quotes in YAML.

**Fix:** the volume line must match the real folder, and be quoted if it has a space:

```yaml
      - "/media/brandon/USB STICK/1TB HDD:/srv/hdd"
```

The current stack avoids spaces entirely:

```yaml
      - "/mnt/storage/filebrowser:/srv/hdd"
```

**Verify:**

```bash
ls "/mnt/storage/filebrowser"
docker exec filebrowser-filebrowser-1 df -h /srv/hdd
```

#### C3. The FileBrowser card shows the boot drive numbers

**Symptom:** the FileBrowser card on Homepage shows the boot drive's numbers, not the 1TB data drive's.

**Cause:** the card reports the drive of the login's folder, and the admin login's folder is `/srv`, which is on the boot drive.

**Fix (optional):** this is not part of my current setup, where the card is labeled "750GB HDD" on purpose and the drive pill shows the data drive. To get a card for the data drive, make a second FileBrowser login limited to its folder. In FileBrowser, open Settings, then User Management, and add a user named `homepage` with a password of at least 12 characters. Set **Scope** to `/hdd` and turn off all its permissions. Then add a card to `services.yaml`:

```yaml
    - FileBrowser (HDD):
        id: filebrowser-hdd-card
        href: https://pc.griffin-luma.ts.net:1006/files/hdd
        siteMonitor: http://192.168.1.198:8081
        icon: filebrowser.svg
        description: 1TB storage drive
        widget:
          type: filebrowser
          url: http://192.168.1.198:8081
          username: homepage
          password: your-own-key
```

The new card has no colored accent until `#filebrowser-hdd-card` is added to the accent selectors in `custom.css`.

**Verify:** after `docker restart homepage`, the new card shows the data drive's available and total space.

### D. Nextcloud

#### D1. Access through untrusted domain

**Symptom:** Nextcloud says "Access through untrusted domain."

**Cause:** the address you're using isn't in Nextcloud's trusted domain list. The `NEXTCLOUD_TRUSTED_DOMAINS` variable is only read on the first install.

**Fix:** add the domain with `occ`, using an index number that isn't used yet:

```bash
docker exec -u www-data nextcloud php occ config:system:get trusted_domains
docker exec -u www-data nextcloud php occ config:system:set trusted_domains 3 --value=pc.griffin-luma.ts.net
```

Because the stack sets `OVERWRITEHOST` and `OVERWRITEPROTOCOL`, log in with the Tailscale address. The local `192.168.1.198:8082` address redirects to it.

**Verify:** the first command lists the new domain, and the Tailscale address loads the login page.

#### D2. Cannot write to the data directory

**Symptom:** the first start fails with a message that Nextcloud can't create or write to the data directory.

**Cause:** the data folder isn't owned by the user Nextcloud runs as (UID 33, shown as `www-data`).

**Fix:**

```bash
sudo chown -R 33:33 /mnt/storage/nextcloud
```

Then restart the stack.

**Verify:**

```bash
sudo ls -la /mnt/storage/nextcloud
docker exec nextcloud df -h /data
```

The folder shows `www-data` as the owner, and `/data` shows `/dev/sda1`.

#### D3. The Homepage dot shows HTTP status 500

**Symptom:** the Nextcloud dot on Homepage is red and says status 500, even though you can log in. Nextcloud's log shows the monitor's `GET /` getting a `302`.

**Cause:** the monitor was checking `/`, which redirects to the login page.

**Fix:** monitor a page that answers directly. In `services.yaml`:

```yaml
        siteMonitor: http://192.168.1.198:8082/status.php
```

Check it, then restart Homepage:

```bash
curl -I http://192.168.1.198:8082/status.php
docker restart homepage
```

The first line should be `HTTP/1.1 200 OK`. If it says `400`, add the address as a trusted domain and try again:

```bash
docker exec -u www-data nextcloud php occ config:system:set trusted_domains 4 --value=192.168.1.198:8082
```

**Verify:** the dot turns green. If it doesn't, check what Homepage saw:

```bash
docker logs homepage --tail 40 | grep -i -E "nextcloud|8082|monitor|error"
```

#### D4. The Immich integration says local IP blocked

**Symptom:** the integration says `Connection failed: local IP blocked by Nextcloud`.

**Cause:** Nextcloud refuses requests to private addresses (like `192.168.x.x` and Tailscale addresses) by default.

**Fix:**

```bash
docker exec -u www-data nextcloud php occ config:system:set allow_local_remote_servers --value=true --type=boolean
docker exec -u www-data nextcloud php occ config:system:get allow_local_remote_servers
```

In the integration settings, use the base address `http://192.168.1.198:2283`, with no `/photos` and no `/api`. Create the API key in Immich under Account Settings, then API Keys.

**Verify:** the second command prints `true`, and **Test connection** succeeds. Also confirm that Nextcloud can reach Immich: `docker exec -u www-data nextcloud php -r 'echo file_get_contents("http://192.168.1.198:2283/api/server/ping");'` should print `{"res":"pong"}`.

#### D5. A 502 right after deploying Nextcloud

**Symptom:** the Tailscale address shows a 502 error after the stack was first deployed.

**Cause:** Nextcloud takes 2 to 15 minutes to install on its first start on this machine. Apache isn't ready yet.

**Fix:** watch it, then refresh the page:

```bash
docker logs -f nextcloud
```

Press `Ctrl+C` when the install finishes and Apache is ready.

**Verify:** the login page loads.

#### D6. Nextcloud redirects to the wrong port

**Symptom:** clicking the Nextcloud link on its Tailscale port sends you to `https://pc.griffin-luma.ts.net:8441/login`, a port that no longer exists.

**Cause:** `OVERWRITEHOST` and `OVERWRITECLIURL` in the stack still had the old port (8441). They tell Nextcloud to build every link with that port. I had renumbered the Tailscale ports, so Nextcloud was now at 1005.

**Fix:** in Portainer, open the `nextcloud` stack, click **Editor** and change the two lines in the `app` service:

```yaml
      OVERWRITEHOST: pc.griffin-luma.ts.net:1005
      OVERWRITECLIURL: https://pc.griffin-luma.ts.net:1005
```

Click **Update the stack** with the re-pull option off. Your passwords stay saved, and the install isn't touched.

**Verify:**

```bash
docker exec -u www-data nextcloud php occ config:system:get overwritehost
```

It should print `pc.griffin-luma.ts.net:1005`. If it still prints the old port, set it directly:

```bash
docker exec -u www-data nextcloud php occ config:system:set overwritehost --value=pc.griffin-luma.ts.net:1005
docker exec -u www-data nextcloud php occ config:system:set overwrite.cli.url --value=https://pc.griffin-luma.ts.net:1005
```

#### D7. Nextcloud returns 429 Reached maximum delay

**Symptom:** the Nextcloud card on Homepage shows `API Error` with `statuscode: 429` and `Reached maximum delay`, even after you fix the key. Nextcloud's log has `Reached maximum delay` lines for `/ocs/v2.php/apps/serverinfo/api/v1/info`.

**Cause:** Nextcloud's brute-force protection. The widget was sending the placeholder `your-own-key` as its token and retrying every few seconds, so Nextcloud blocked the address it came from (the Docker network's gateway address, `172.21.0.1` on my machine). It stays blocked for a while, even for a valid token.

**Fix:** stop Homepage so it stops sending bad logins. Then create a real token, find the blocked address and reset it:

```bash
docker stop homepage
TOKEN=$(openssl rand -hex 24)
docker exec -u www-data nextcloud php occ config:app:set serverinfo token --value=$TOKEN
echo $TOKEN
sudo grep -i bruteforce /mnt/storage/nextcloud/nextcloud.log | tail -3
```

The log lines show the blocked address in `remoteAddr`. Use that address (not your server's address) here:

```bash
docker exec -u www-data nextcloud php occ security:bruteforce:attempts 172.21.0.1
docker exec -u www-data nextcloud php occ security:bruteforce:reset 172.21.0.1
docker exec -u www-data nextcloud php occ security:bruteforce:attempts 172.21.0.1
```

The last command should show `attempts: 0` and `delay: 0 ms`. Test the token before Homepage uses it:

```bash
curl -s -H "NC-Token: $TOKEN" "http://192.168.1.198:8082/ocs/v2.php/apps/serverinfo/api/v1/info?format=json" | head -c 300
```

A good answer starts with `{"ocs":{"meta":{"status":"ok"`. Put the token into `services.yaml` as the Nextcloud `key`, then `docker start homepage`. The `$TOKEN` variable only exists in the same terminal window.

**Verify:** the Nextcloud card shows its numbers, and Nextcloud's log stops filling with `Reached maximum delay`. To prevent it, always stop Homepage before you edit its keys.

#### D8. Permission denied when listing the Nextcloud data folder

**Symptom:** `ls /mnt/storage/nextcloud` says `Permission denied`.

**Cause:** once Nextcloud finishes installing, it makes its data folder private (`drwxrwx---`, owned by `www-data`). This is normal.

**Fix:**

```bash
sudo ls -a /mnt/storage/nextcloud
```

**Verify:** the listing shows `.ncdata`, an `appdata_...` folder and your login folder.

#### D9. The Immich integration test fails with an authentication error

**Symptom:** **Test connection** in the Immich Integration settings reports an authentication or permission error.

**Cause:** the API key was pasted wrongly, was revoked, or lacks the permissions the app needs.

**Fix:** create a new key in Immich (profile picture, **Account Settings**, **API Keys**, **New API Key**), choose all permissions, copy it as soon as it appears, and paste it into the integration settings. First confirm that Nextcloud can reach Immich:

```bash
docker exec -u www-data nextcloud php -r 'echo file_get_contents("http://192.168.1.198:2283/api/server/ping");'
```

It should print `{"res":"pong"}`. If it does, the problem is the key and not the network.

**Verify:** **Test connection** reports success, and **Save** keeps the settings.

---

### E. Tailscale

#### E1. 502 on Portainer through Tailscale Serve

**Symptom:** the Portainer address on Tailscale shows `HTTP ERROR 502`.

**Cause:** Portainer's HTTPS port (9443) uses a self-signed certificate that Tailscale won't proxy. It also serves plain HTTP on port 9000, but that port wasn't published.

**Fix:** recreate the container with port 9000 published (your data stays in the `portainer_data` volume), then point Tailscale at it:

```bash
docker stop portainer
docker rm portainer
docker run -d -p 9443:9443 -p 9000:9000 --name portainer --restart=always -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer-ce:latest
sudo tailscale serve --https=1001 off
sudo tailscale serve --bg --https=1001 http://192.168.1.198:9000
```

**Verify:** `https://pc.griffin-luma.ts.net:1001` loads.

#### E2. tailscale serve says the CLI has changed

**Symptom:** `Error: the CLI for serve and funnel has changed.`

**Cause:** newer Tailscale versions use a different command format.

**Fix:** use `--bg` and put the port in the `--https` option:

```bash
sudo tailscale serve --bg --https=1002 http://192.168.1.198:2283
```

To remove one: `sudo tailscale serve --https=1002 off`.

**Verify:** `tailscale serve status` lists the address.

#### E3. Path-based addresses break apps

**Symptom:** with addresses like `/files` and `/adguard` on one port, the apps load blank or with broken links.

**Cause:** these apps assume they live at the root of the address (`/`).

**Fix:** use one HTTPS port per service. This clears everything and sets the current list again. It is also how I renumbered the ports from the Lenovo's layout to 1000 to 1008:

```bash
sudo tailscale serve reset
sudo tailscale serve --bg --https=1000 http://192.168.1.198:3001
sudo tailscale serve --bg --https=1001 http://192.168.1.198:9000
sudo tailscale serve --bg --https=1002 http://192.168.1.198:2283
sudo tailscale serve --bg --https=1003 http://192.168.1.198:8090
sudo tailscale serve --bg --https=1004 http://192.168.1.198:3000
sudo tailscale serve --bg --https=1005 http://192.168.1.198:8082
sudo tailscale serve --bg --https=1006 http://192.168.1.198:8081
sudo tailscale serve --bg --https=1007 http://192.168.1.198:8088
sudo tailscale serve --bg --https=1008 http://192.168.1.198:19999
```

After renumbering, update every place that still has an old port: Nextcloud's `OVERWRITEHOST` and `OVERWRITECLIURL` ([D6](#d6-nextcloud-redirects-to-the-wrong-port)), Homepage's `href` links and its `HOMEPAGE_ALLOWED_HOSTS` line, and your phone app's server address.

**Verify:** `tailscale serve status` lists nine entries, and each address loads.

#### E4. The tailnet name changed

**Symptom:** after the Tailscale network name changed (mine went from `tail30c3e5.ts.net` to `griffin-luma.ts.net`), links and logins stopped working.

**Cause:** the old name was written into several configs.

**Fix:** update the name in each place:

- Homepage's `services.yaml` (the `href:` links) and the `HOMEPAGE_ALLOWED_HOSTS` line in the Homepage stack.
- The Nextcloud stack's `OVERWRITEHOST` and `OVERWRITECLIURL` lines, and Nextcloud's trusted domains:

```bash
docker exec -u www-data nextcloud php occ config:system:set trusted_domains 3 --value=pc.griffin-luma.ts.net
```

- The server address in your phone and desktop apps.

**Verify:** `tailscale serve status` shows the new name, and every address loads.

#### E5. The name will not resolve from another computer

**Symptom:** `DNS_PROBE_POSSIBLE` or "DNS address could not be found" when opening a Tailscale address.

**Cause:** that computer isn't connected to Tailscale, so it can't look up the name.

**Fix:** open the Tailscale app on that computer and make sure it says **Connected**. If it shows signed in but not connected, quit and reopen the app, or log out and back in. Then test:

```bash
nslookup pc.griffin-luma.ts.net
```

**Verify:** the lookup returns an address starting with `100.`.

#### E6. 502 when forwarding to the wrong address

**Symptom:** a Tailscale address shows 502 even though the service works locally.

**Cause:** the Tailscale entry points at the wrong machine's address, or the old server's address.

**Fix:** check that the server can reach the address, then redo the entry with the right one:

```bash
curl -v http://192.168.1.198:3000
sudo tailscale serve --https=1004 off
sudo tailscale serve --bg --https=1004 http://192.168.1.198:3000
```

**Verify:** `tailscale serve status` shows the right target, and the address loads.

#### E7. An SSH session over Tailscale drops when Tailscale restarts

**Symptom:** a command that restarts Tailscale freezes or ends your session, and the rest of the commands don't run.

**Cause:** the session itself travels through Tailscale.

**Fix:** use the local network address for any step that restarts Tailscale (like freeing port 53):

```bash
ssh brandon@192.168.1.198
```

**Verify:** the session survives `sudo systemctl restart tailscaled`.

### F. AdGuard Home and DNS

AdGuard Home runs as a Docker container with `network_mode: host`, so it uses ports 53 and 3000 on the machine directly.

#### F1. Port 53 conflict with systemd-resolved

**Symptom:** AdGuard says port 53 is already in use, and `sudo ss -tulpn | grep :53` shows `systemd-resolve`.

**Cause:** `systemd-resolved` listens on port 53 by default. If you work around it by moving AdGuard to port 54, no device can use it, because devices only send DNS to port 53.

**Fix (what is in use now):** `systemd-resolved` is disabled, and Tailscale writes `/etc/resolv.conf`. Do this over SSH on the local address ([E7](#e7-an-ssh-session-over-tailscale-drops-when-tailscale-restarts)):

```bash
sudo systemctl disable systemd-resolved
sudo systemctl stop systemd-resolved
sudo rm /etc/resolv.conf
echo "nameserver 192.168.1.1" | sudo tee /etc/resolv.conf
sudo systemctl restart tailscaled
```

The router's address in `resolv.conf` keeps the machine resolving names until AdGuard runs. Tailscale then replaces the file with its own, starting with `nameserver 100.100.100.100`. If the server later stops resolving names with this setup, see [F6](#f6-the-server-cannot-look-up-names-after-a-tailscale-update).

**Fix (the other method, from an earlier native install):** keep `systemd-resolved` running and turn off only its port 53 listener:

```bash
sudo mkdir -p /etc/systemd/resolved.conf.d
sudo nano /etc/systemd/resolved.conf.d/adguardhome.conf
```

```ini
[Resolve]
DNS=127.0.0.1
DNSStubListener=no
```

```bash
sudo mv /etc/resolv.conf /etc/resolv.conf.backup
sudo ln -s /run/systemd/resolve/resolv.conf /etc/resolv.conf
sudo systemctl reload-or-restart systemd-resolved
```

**Rollback,** if names stop resolving after the first method:

```bash
sudo systemctl enable --now systemd-resolved
sudo rm /etc/resolv.conf
sudo ln -s ../run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
sudo systemctl restart systemd-resolved tailscaled
```

**Verify:**

```bash
sudo ss -tulpn | grep :53
nslookup google.com
```

Only AdGuard Home should be listed on port 53 after it starts, and the lookup should return an address.

#### F2. Blocklists block DNS-over-HTTPS providers

**Symptom:** AdGuard logs errors like `exchange failed upstream=https://dns10.quad9.net:443/dns-query`, and websites stop loading. `nslookup dns.cloudflare.com 127.0.0.1` returns `0.0.0.0`.

**Cause:** one of your blocklists blocks the domains of DNS providers, including the ones AdGuard uses as upstream servers.

**Fix:** in AdGuard, open the **Query Log** and search for the machine's address or the blocked domain. Click an entry to see which list blocked it, then remove or disable that list. That is what fixed it here. Two options I didn't need: add allow rules such as `@@||dns.google^`, or switch the upstream servers to plain addresses (`1.1.1.1`, `8.8.8.8`, `9.9.9.9`). To see the errors:

```bash
docker logs adguardhome --tail 30
curl -v https://dns10.quad9.net:443
nslookup dns.google 127.0.0.1
```

**Verify:** `nslookup dns.google 127.0.0.1` returns a real address, not `0.0.0.0`, and the errors stop.

#### F3. Devices are not using AdGuard Home

**Symptom:** the AdGuard dashboard shows no clients or queries from other devices, though `nslookup` works on the server.

**Cause:** the router wouldn't let me change its DNS setting, so devices keep using the DNS server the router hands out until each one is set by hand. A device with an alternate DNS server of `8.8.8.8` can also use it and skip AdGuard's filtering.

**Fix:** set the DNS server on each device. On Windows 11 (Ethernet): **Settings**, **Network and internet**, **Ethernet**, **DNS server assignment**, **Edit**, **Manual**, **IPv4** on, preferred `192.168.1.198`, alternate `8.8.8.8`, **Save**. On the iPhone: **Settings**, **Wi-Fi**, the **i** next to the network, **Configure DNS**, **Manual**, add `192.168.1.198` and `8.8.8.8`, **Save**. Check from any device:

```bash
nslookup google.com 192.168.1.198
ipconfig /all
ip addr
sudo ss -tulpn | grep :53
```

`ipconfig /all` (Windows) shows which DNS servers the PC got. `ip addr` (on the server) shows the server's address on each network card, so use the wired one (`eno1`). The alternate server `8.8.8.8` keeps the internet working when the server is off. Leave it blank if you want strict filtering and don't mind losing internet while the server is down.

**Verify:** the AdGuard Query Log shows queries from the devices' addresses.

#### F4. The NextDNS app and Tailscale on the iPhone

**Symptom:** with the NextDNS app turned on, the iPhone can't reach the Tailscale addresses.

**Cause:** iOS only runs one VPN at a time. The NextDNS app and Tailscale each use the VPN slot, so they push each other out.

**Fix:** use one of them at a time. At home, AdGuard Home already blocks ads for configured devices. To use NextDNS with Tailscale, add it in Tailscale's DNS settings (Add nameserver, then NextDNS, with your endpoint ID) and delete the NextDNS app's profile. That setting applies to every device on the tailnet, and NextDNS's free plan has a monthly query limit. I removed this setting, and Tailscale's DNS is at its default.

**Verify:** the iPhone opens `https://pc.griffin-luma.ts.net:1000` with Tailscale connected.

#### F5. The AdGuard web page shows a 502 on its Tailscale address

**Symptom:** `https://pc.griffin-luma.ts.net:1004` shows `HTTP ERROR 502`, and the AdGuard card on Homepage has a red dot, but DNS lookups still work.

**Cause:** Tailscale forwards to `192.168.1.198:3000`, but AdGuard's web page isn't on port 3000. The setup wizard proposes port 80, and if you keep it, nothing answers on 3000.

**Fix:** check which port the web page is on:

```bash
docker ps | grep adguard
sudo ss -tulpn | grep AdGuardHome
sudo grep -n -B1 -A8 "^http:" /opt/adguard-docker/conf/AdGuardHome.yaml
```

If the config shows `address: 0.0.0.0:80`, move it to 3000. Stop the container first, because AdGuard rewrites its settings while it runs:

```bash
docker stop adguardhome
sudo sed -i 's/^  address: 0.0.0.0:80$/  address: 0.0.0.0:3000/' /opt/adguard-docker/conf/AdGuardHome.yaml
sudo grep -n "address:" /opt/adguard-docker/conf/AdGuardHome.yaml
docker start adguardhome
```

The best fix is to set 3000 in the setup wizard in the first place, which is what I did the second time.

**Verify:**

```bash
sudo ss -tulpn | grep AdGuardHome
curl -sI http://192.168.1.198:3000 | head -1
nslookup google.com 192.168.1.198
```

`ss` should show ports 3000 and 53, `curl` should return a line starting with `HTTP/1.1`, and the lookup should still answer.

#### F6. The server cannot look up names after a Tailscale update

**Status:** fixed on 2026-10-23 and working since. **Not yet checked after a reboot.** I don't know yet whether the setting and the file below survive one. The check is at the end of this entry.

**Symptom:**

- `git clone https://github.com/...` on the server fails with `fatal: unable to access ...: Could not resolve host: github.com`.
- `nslookup github.com` answers `** server can't find github.com: SERVFAIL` from `100.100.100.100`.
- The Tailscale card on Homepage turns red, and its log shows `getaddrinfo EAI_AGAIN api.tailscale.com`. The Speedtest Tracker card was red at the same time (it had a second problem of its own, see [B6](#b6-a-container-starts-empty-after-update-the-stack)).
- Everything that does not need a name still works: the web pages open by address and Docker keeps running.

**Cause:** on this server Tailscale owns `/etc/resolv.conf` ([F1](#f1-port-53-conflict-with-systemd-resolved)). The file said `nameserver 100.100.100.100`, which is Tailscale's own resolver, and that resolver had nothing to forward to. The message I found was `dns: resolver: forward: no upstream resolvers set, returning SERVFAIL`. The Machines page showed `pc` on 1.104.2, one version newer than the 1.104.1 I had installed, so Tailscale had updated itself (see [7.13](#713-tailscale)) and I believe that change is what broke it. That is my best explanation, not something I proved. Docker containers copy the host's DNS setting when they start, so Homepage had the broken setting too.

**Diagnose (read-only).** One command at a time:

```bash
cat /etc/resolv.conf
nslookup github.com
tailscale dns status
docker logs adguardhome --tail 30
```

On my server `resolv.conf` started with `# resolv.conf(5) file generated by tailscale` and showed `nameserver 100.100.100.100`. A copy of the file from before Tailscale took it over was still there: `cat /etc/resolv.pre-tailscale-backup.conf` showed `nameserver 192.168.1.1`, the router.

**What did not help.** `sudo systemctl restart tailscaled` changed nothing. `sudo tailscale set --accept-dns=false` stopped Tailscale from using its DNS, but it did not put the old file back, so `resolv.conf` still pointed at `100.100.100.100`.

**Fix.** Do this on the local address or at the machine, not over a session through Tailscale ([E7](#e7-an-ssh-session-over-tailscale-drops-when-tailscale-restarts)).

1. Tell Tailscale not to manage DNS on this machine:

   ```bash
   sudo tailscale set --accept-dns=false
   ```

2. Put back the file that Tailscale saved:

   ```bash
   sudo cp /etc/resolv.pre-tailscale-backup.conf /etc/resolv.conf
   cat /etc/resolv.conf
   ```

   It should show `nameserver 192.168.1.1`.

3. Check that names resolve:

   ```bash
   nslookup github.com
   ```

   It must return addresses.

4. Restart Homepage **after** step 3, so the container copies the working DNS setting. I restarted it once too early, before the file was fixed, and had to do it again:

   ```bash
   docker restart homepage
   ```

5. Reload the dashboard. The Tailscale card should be green again. Mine was. (The Speedtest card also needed its data restored: [B6](#b6-a-container-starts-empty-after-update-the-stack).)

**What this changes.** The server now sends its own lookups to the router (`192.168.1.1`), not through Tailscale. The server's own lookups do not pass through AdGuard Home, and names ending in `.ts.net` may not resolve on the server itself. Your other devices are not affected, and the Tailscale addresses on ports 1000 to 1008 still work for them.

**Undo,** to let Tailscale manage DNS again:

```bash
sudo tailscale set --accept-dns=true
```

Tailscale then rewrites `/etc/resolv.conf` by itself.

**Verify:**

```bash
cat /etc/resolv.conf
nslookup github.com
tailscale dns status
docker ps --filter name=homepage --format "table {{.Names}}\t{{.Status}}"
```

The file shows the router's address, the lookup returns addresses, and Homepage is `Up` with a green Tailscale card.

**Still to check after a reboot.** Run `sudo reboot`, wait about three minutes and run `cat /etc/resolv.conf` and `nslookup github.com` again. If the file is back to `100.100.100.100` and the lookup fails, repeat steps 1 to 4 and look at `tailscale debug prefs | grep -i dns` to see whether the setting was lost. I will replace this paragraph with the result.

### G. Homepage

After you edit a Homepage file, run `docker restart homepage` and hard-refresh the browser with `Ctrl+Shift+R`.

#### G1. Host validation failed

**Symptom:** the page shows `{"error":"Host validation failed. See logs for more details."}`.

**Cause:** Homepage only answers requests for addresses it has been told about.

**Fix:** list every address you use in the Homepage stack's environment:

```yaml
    environment:
      HOMEPAGE_ALLOWED_HOSTS: 192.168.1.198:3001,pc.griffin-luma.ts.net:1000,localhost:3001
```

**Verify:** `http://192.168.1.198:3001` loads.

#### G2. Port 3000 already in use

**Symptom:** the stack fails with `failed to bind host port 0.0.0.0:3000/tcp: address already in use`.

**Cause:** AdGuard Home's web page uses port 3000.

**Fix:** publish Homepage on a different port. The left number is the port on the server:

```yaml
    ports:
      - 3001:3000
```

Check what AdGuard is using with `sudo ss -tulpn | grep AdGuardHome`.

**Verify:** `http://192.168.1.198:3001` loads.

#### G3. The Beszel widget says No items returned

**Symptom:** `API Error: No items returned from beszel API`.

**Cause:** the widget needs the Beszel superuser login, which is separate from your hub login. It also needs `version: 2`.

**Fix:** reset the superuser login, test it, and make sure the widget has `version: 2`:

```bash
docker exec beszel /beszel superuser upsert your-email@example.com your-own-key
curl -X POST http://192.168.1.198:8090/api/collections/_superusers/auth-with-password -H "Content-Type: application/json" -d '{"identity":"your-email@example.com","password":"your-own-key"}'
docker restart homepage
```

**Verify:** the `curl` returns a token, and the widget shows your system.

#### G4. The Portainer widget shows an error

**Symptom:** the Portainer card shows either `Invalid JWT token` / `Unauthorized`, or `Unable to find an environment with the specified identifier inside the database (bucket=endpoints, key=1)`.

**Cause:** the first one means the `key` is wrong or still the placeholder. The second means the `env:` number doesn't match a Portainer environment. Mine is `3`. A guess like `1` fails.

**Fix:** create an access token in Portainer (your name, **My account**, **Access tokens**, **Add access token**) and copy it when it appears. Find the environment number: click the local environment on Portainer's home page and read the number in the address bar. It appears as `#!/endpoints/<number>` or `#!/<number>/docker/dashboard`. Put both in `services.yaml`:

```yaml
        widget:
          type: portainer
          url: http://192.168.1.198:9000
          env: 3
          key: your-own-key
```

Then `docker restart homepage`. To list the environments from the terminal, set `PT` to your token first. The `echo` line should print a number above 0, and it never prints the token:

```bash
echo ${#PT}
curl -s -H "X-API-Key: $PT" http://192.168.1.198:9000/api/endpoints | python3 -c "import sys,json; [print(e['Id'], e['Name']) for e in json.load(sys.stdin)]"
```

If Python prints `TypeError: string indices must be integers`, Portainer answered with an error message, which usually means `PT` isn't set in that terminal.

**Verify:** the widget shows your container counts.

#### G5. The Tailscale widget says the API token is invalid

**Symptom:** `API token invalid`.

**Cause:** the value pasted wasn't the whole access token. The real token starts with `tskey-api-` and has a second part after a dash. The short code ending in `CNTRL` in the list is only the token's ID, and `tskey-auth-` keys are a different thing.

**Fix:** create a new access token in the admin console and copy it with the copy button the moment it appears, because it's shown only once. Test it before putting it in Homepage:

```bash
curl -H "Authorization: Bearer your-own-key" https://api.tailscale.com/api/v2/tailnet/-/devices
```

Use the machine's ID that ends in `CNTRL` for `deviceid:`.

**Verify:** the `curl` lists your devices, and the card shows its fields.

#### G6. The Speedtest Tracker card shows an error

**Symptom:** the card shows `API Error` with a `Not Found` page, or Speedtest Tracker itself shows `500 | Server Error`. Calling its API by hand with a placeholder token answers `{"message":"Unauthenticated."}`.

**Cause:** for the card, the widget has no valid API token. Speedtest Tracker 1.2.1 and newer need `version: 2` plus a token with the **Read Results** ability. Until a speed test has finished, there is also no latest result to read. The 500 on the page itself is a problem with the app key: the stack's `APP_KEY` was missing the `base64:` prefix at the start.

**Fix:** open `http://192.168.1.198:8088/admin/api-tokens`, create a token with **Read Results**, and copy it. Run one speed test from the dashboard. Test the token (replace the placeholder with your real token):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Accept: application/json" -H "Authorization: Bearer your-own-key" http://192.168.1.198:8088/api/v1/results/latest
curl -s -H "Accept: application/json" -H "Authorization: Bearer your-own-key" http://192.168.1.198:8088/api/v1/results/latest | head -c 300
```

`200` and JSON with your speeds mean the token works. Put it into the card's `key:` line. If the page shows 500, fix the key line: it must start with `base64:` and be 51 characters long. Check without revealing it:

```bash
docker exec speedtest-tracker sh -c 'printf "%s" "$APP_KEY" | wc -c'
docker exec speedtest-tracker sh -c 'printf "%s" "$APP_KEY" | cut -c1-7'
```

They should print `51` and `base64:`. If not, generate a new key with `echo "base64:$(openssl rand -base64 32 2>/dev/null)"`, update the stack and run `docker restart speedtest-tracker`.

**Verify:** the card shows download, upload and ping.

#### G7. Widgets show errors until their keys are filled in

**Symptom:** after deploying Homepage, several cards show `API Error`, and Nextcloud may block the address.

**Cause:** the files in the repository use `your-own-key` as a placeholder, and a widget keeps sending it until you replace it.

**Fix:** stop Homepage, replace the keys one card at a time, and start it again:

```bash
docker stop homepage
nano /home/brandon/homepage-config/services.yaml
docker start homepage
```

The table in [Phase 10](#phase-10-homepage) lists where each value comes from. Don't put the real values anywhere that goes into Git.

**Verify:** `docker logs homepage --tail 30` shows no widget errors.

#### G8. YAML indentation mistakes

**Symptom:** a widget doesn't appear, a setting is ignored, or a whole file is skipped.

**Cause:** YAML uses indentation for nesting. Keys at the same level as `widget:` aren't part of it. A list item with a different indentation from its neighbors makes the file unreadable. The bookmarks file I tried to use had `- Newegg:` indented 5 spaces while its neighbors had 4, and Homepage couldn't parse it. Top-level settings nested under `background:` in `settings.yaml` are ignored too.

**Fix:** everything inside `widget:` is indented two more spaces:

```yaml
        widget:
          type: filebrowser
          url: http://192.168.1.198:8081
          username: your-own-key
          password: your-own-key
```

In `bookmarks.yaml`, every entry in a group must start at the same column:

```yaml
- Online Shopping:
    - Amazon:
        - abbr: AMZ
          href: https://amazon.com/
    - Newegg:
        - abbr: NEWEGG
          href: https://newegg.com/
```

In `settings.yaml`, keys like `maxGroupColumns` and `disableCollapse` go at the left edge, not under `background:`. A service's `id:` must match the name used in `custom.css`, for example `id: filebrowser-card` for `#filebrowser-card`. To check a file before copying it to the server, run it through a YAML parser:

```bash
python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1])); print('OK')" bookmarks.yaml
```

**Verify:** the parser prints `OK`, and after a restart the widget or bookmark group appears.

#### G9. Stat icons turn white

**Symptom:** the CPU, memory, temperature and uptime icons (or the disk and network ones) lose their colors.

**Cause:** the old color rules counted the pill's position in the header ("the second box, then the first icon"). Adding or reordering a widget shifted the count.

**Fix:** `custom.css` finds the pills as "the first stats pill" and "the second stats pill" with `:has()` rules, so it doesn't depend on position. The first rule looks like this:

```css
.widget-container:has(.information-widget-resource):not(.widget-container:has(.information-widget-resource) ~ .widget-container) .information-widget-resource:nth-of-type(1) svg { color: #4ade80 !important; } /* CPU */
```

Keep the order in `widgets.yaml` as the server stats first, then Drives.

**Verify:** the icons are colored after a hard refresh.

#### G10. The header wraps or overlaps on a smaller screen

**Symptom:** on a smaller screen, the date and weather drop under the other pills and the search bar overlaps them.

**Cause:** the header is about 2050px wide at full size and doesn't fit.

**Fix:** `custom.css` scales the header down in steps by browser width. These are my current rules. The comment names the screen they were written for:

```css
@media (min-width: 2040px) and (max-width: 2399px) { #information-widgets { zoom: 0.90; } }  /* 1440p at 125% (2048px) */
@media (min-width: 1800px) and (max-width: 2039px) { #information-widgets { zoom: 0.80; } }
@media (min-width: 1650px) and (max-width: 1799px) { #information-widgets { zoom: 0.70; } }
@media (min-width: 1530px) and (max-width: 1649px) { #information-widgets { zoom: 0.90; } }  /* 1080p at 125% (1536px) */
@media (min-width: 1490px) and (max-width: 1529px) { #information-widgets { zoom: 0.80; } }
```

If a rule has no effect, your browser's real width isn't inside its range. Windows display scaling changes it (a 1080p screen at 125% is about 1536 wide). Check yours: press `F12`, click Console, type `innerWidth` and press Enter, then move the `min-width` and `max-width` numbers so your width is inside one range. If the header wraps, lower the zoom number by 0.03 at a time. The rule needs a recent browser (it works in Firefox from version 126).

**Verify:** the pills stay on one row and the search bar sits under them.

#### G11. Mobile layout spacing

**Symptom:** on a phone, the pills are cramped or the search bar is too close to the first group.

**Cause:** the pills had no space between them, and the search bar has its own padding.

**Fix:** the spacing is set by variables at the top of `custom.css`. Change the numbers:

```css
:root {
  --d-search-top: 80px;
  --d-search-space: 90px;
  --m-gap: 12px;            /* space between every pill */
  --m-search-top: 12px;     /* space between the date/weather and the search */
  --m-search-bottom: 8px;
  --m-search-pad: 10px;
}
```

The `--m-` numbers are for phones and small windows (1000px wide and under), and the `--d-` numbers are for the desktop layout.

**Verify:** after a hard refresh, the spacing between the pills is equal.

#### G12. Homepage cannot see the data drive

**Symptom:** the drive pill is blank or shows the boot drive.

**Cause:** the Homepage container wasn't given the drive's folder, or it started before the drive was mounted.

**Fix:** the stack needs the volume line `- /mnt/storage:/mnt/storage:ro`, and `widgets.yaml` needs `/mnt/storage` in the `disk:` list (see [Step 4](#step-4-point-each-service-at-its-folder)). Then restart it:

```bash
docker restart homepage
```

**Verify:**

```bash
docker exec homepage df -h /mnt/storage
```

It should show the data drive at about 916G.

#### G13. The Netdata card is green, but Homepage's log shows a parse error

**Symptom:** `docker logs homepage` repeats `Error calling http://192.168.1.198:19999/...` followed by `Parse Error: Data after Connection: close` every 30 seconds, while the Netdata card shows a green dot and a working widget.

**Cause:** Netdata's built-in web server answers a HEAD request with `400 Bad Request`. You can see it with `curl -sI`. A normal request works fine.

**Fix:** none is needed. The card and widget work. If the log noise bothers you, check that Netdata itself is healthy with a normal request, and remove the `siteMonitor` line from the Netdata card (you lose the status dot, and the widget still shows its alerts):

```bash
curl -sI http://192.168.1.198:19999/ | head -8
curl -s -o /dev/null -w "%{http_code}\n" http://192.168.1.198:19999/api/v1/info
```

The first prints `HTTP/1.1 400 Bad Request`. The second should print `200`.

**Verify:** the second command prints `200`, and the card still shows live numbers.

### H. Remote access

#### H1. SSH

**Symptom:** you can't connect with `ssh`.

**Cause:** the SSH server isn't installed or running.

**Fix:**

```bash
sudo apt update
sudo apt install openssh-server -y
sudo systemctl enable ssh
sudo systemctl start ssh
```

Connect from another computer:

```bash
ssh brandon@192.168.1.198
```

Over Tailscale, use the name:

```bash
ssh brandon@pc
```

**Verify:** `sudo systemctl status ssh` shows `active (running)`.

#### H2. VS Code Remote-SSH cannot save files

**Symptom:** `Failed to save ... EACCES: permission denied`, or the folder won't open under `/var/lib/docker/volumes/`.

**Cause:** Docker's own volume folders are owned by root. Homepage's config lives in a regular folder (`/home/brandon/homepage-config`) that is shared into the container, and files copied out of a volume stay owned by root.

**Fix:** use a regular folder for the config, and take ownership of the files:

```bash
mkdir -p ~/homepage-config
sudo chown -R brandon:brandon ~/homepage-config
code -a ~/homepage-config/
```

The Homepage stack's volume line is then `/home/brandon/homepage-config:/app/config`.

**Verify:** you can save the files in VS Code.

#### H3. AnyDesk

**Symptom:** `anydesk` prints a GTK `cannot open display` warning, and `--set-password` doesn't ask for anything.

**Cause:** over SSH there's no screen, so the warning is harmless. Setting the password needs the AnyDesk service to be installed. `apt` may also print a warning that the AnyDesk key is stored in a legacy keyring. It still works.

**Fix:**

```bash
anydesk --get-id
sudo anydesk --set-password
sudo systemctl enable anydesk
sudo systemctl start anydesk
```

For auto-login on a headless machine, set it under `[Seat:*]` in the lightdm config:

```ini
[Seat:*]
autologin-guest=false
autologin-user=brandon
autologin-user-timeout=0
```

**Verify:** you can connect from another computer with the AnyDesk ID and password, with no one accepting on the server.

#### H4. The remote desktop is choppy on a machine with no monitor

**Symptom:** with no monitor attached, AnyDesk is slow or the screen resolution is unstable.

**Cause:** with no display connected, the graphics hardware has nothing to draw to.

**Fix:** plug a DisplayPort dummy plug (an EDID emulator) into the mini PC. It makes the machine believe a monitor is attached, which keeps the resolution stable, lets the integrated graphics work and makes the remote desktop smooth.

**Verify:** you connect with AnyDesk and the picture is smooth at a normal resolution.

#### H5. The cheat sheet does not appear in the VS Code terminal

**Symptom:** the cheat sheet from [Step 9](#step-9-the-cheat-sheet-at-login) appeared in an SSH session from PowerShell, but not in a new terminal in VS Code Remote-SSH, on the same server.

**Cause:** my first version of the `~/.bashrc` block used a guard variable, `export HOMELAB_SHOWN=1`, so the sheet showed once per terminal. VS Code Remote-SSH reads your environment by starting a shell on the server and copying its variables into every terminal it opens. That shell ran my block, which exported `HOMELAB_SHOWN=1`, so every VS Code terminal began with the variable already set and printed nothing. In a VS Code terminal, `echo "[$HOMELAB_SHOWN]"` printed `[1]`; in a fresh SSH session it printed `[]`.

**Fix:** remove the guard variable. The block does not need one, because it only runs in a shell that is interactive and attached to a terminal. The background shell VS Code uses has its output captured, so the `[ -t 1 ]` test skips it.

1. Look at what is in the file now:

   ```bash
   grep -n 'homelab\|HOMELAB' ~/.bashrc
   ```

2. Remove the old block, and add the new one. If your block used the same two marker lines as in Step 9, this removes it:

   ```bash
   sed -i '/# >>> homelab login display >>>/,/# <<< homelab login display <<</d' ~/.bashrc
   ```

   Then add the block from [Step 9, part 4](#step-9-the-cheat-sheet-at-login). If `grep` still shows a line with `HOMELAB_SHOWN`, open the file with `nano ~/.bashrc` and delete that line by hand.

3. Close the VS Code terminals and open a new one. If the old variable is still set, clear it in that terminal with `unset HOMELAB_SHOWN`. If a new terminal still shows `[1]`, run **Remote-SSH: Kill VS Code Server on Host** from the Command Palette and reconnect. I did not need that step.

**Verify:** a new VS Code terminal and a new SSH session both show the cheat sheet, `echo "[$HOMELAB_SHOWN]"` prints `[]`, and `ssh brandon@192.168.1.198 "echo ok"` from PowerShell prints only `ok`. All of that was true on my server.

### I. Hardware and boot

#### I1. The mini PC won't start, and the light by the power jack flickers

**Symptom:** with a third-party 65W adapter that connects through a converter tip, the LED next to the power jack flickers on and off, the fan doesn't spin and nothing starts when you press the power button. A multimeter reads about 19.9 volts at the plug, with the center positive, which is normal for a 19.5V adapter.

**Cause:** the voltage and polarity were correct, so the charger itself wasn't the problem. HP's adapters have a small ID pin in the middle of the plug, and my best guess is that the Mini didn't accept an adapter that went through a generic converter tip without it. I couldn't confirm this from HP's documentation.

**Fix:** use a genuine HP 65W adapter with the matching 7.4mm plug. That is what fixed it. Before you blame the board, rule out the adapter: reset the power (unplug, hold the power button for 20 seconds, plug in again) and test with a genuine adapter. If a genuine adapter gives the same flicker, the board has a fault.

**Verify:** the mini PC starts and the light stays on.

#### I2. The USB stick won't boot

**Symptom:** the Ventoy stick doesn't load, or the BIOS refuses to boot it.

**Cause:** Secure Boot was on. It blocks installers that aren't signed for it.

**Fix:** press **F10** at the HP logo to open the BIOS setup, turn **Secure Boot** off in the BIOS security settings, then open **Boot Options** and choose the USB stick. In the Ventoy menu, select the Linux Mint XFCE ISO and boot it in normal mode. This is the only BIOS change I made.

**Verify:** the Linux Mint live desktop appears.

---

## 5. Diagnostic commands

### 5.1 Quick commands

```bash
lsblk -f                                       # drives, filesystems, labels, mount points
sudo drives status                             # pools, pool drives with SMART health, and the last backup
homelab                                        # cheat sheet and live status (shown when a terminal opens)
sudo drives replace                            # a pool drive died: swap it and restore the missing files from the backup
sudo drives restore                            # only the restore part: preview, copy the missing files, check
findmnt /mnt/storage                           # is the main pool mounted?
findmnt /mnt/disks/MAIN1                       # is the drive itself mounted? (one path per findmnt)
df -hT                                         # space used on each drive
docker ps -a                                   # all containers and their status
docker logs <container> --tail 30              # recent logs
docker exec <container> df -h /data            # which drive a container sees
tailscale serve status                         # every Tailscale address and where it points
sudo ss -tulpn | grep :53                      # who is using the DNS port
cat /etc/resolv.conf                           # who owns DNS on the server (Tailscale's file says nameserver 100.100.100.100)
nslookup github.com                            # can the server look up names? SERVFAIL: see F6
tailscale dns status                           # what Tailscale does with DNS on this machine
docker inspect $(docker ps -q) --format '{{.Name}}: {{range .Mounts}}{{if eq .Type "volume"}}{{.Name}} {{end}}{{end}}'   # volumes per container (64 hex characters = anonymous, see B6)
sudo smartctl -A /dev/$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)") | grep -E "Power_On_Hours|Load_Cycle|Reallocated_Sector|Current_Pending"
sudo smartctl -A -d sat /dev/disk/by-label/MAIN1 | grep -E "Power_On_Hours|Load_Cycle|Reallocated_Sector|Current_Pending"
sudo hdparm -B "/dev/$(lsblk -no pkname "$(readlink -f /dev/disk/by-label/MAIN1)")"   # data drive power setting (should be 254)
sudo hdparm -C "/dev/$(lsblk -no pkname "$(readlink -f /dev/disk/by-label/MAIN1)")"   # power state (active/idle for a main drive)
sudo tail -20 /var/log/homelab-backup.log      # the daily backup log
sudo tail -20 /var/log/homelab-drives.log      # what the drives tool changed
sudo crontab -l                                # root's scheduled jobs
uptime                                         # load average
```

### 5.2 The inventory script

This script reads the whole setup and saves it to one file, with every secret masked. I ran it before and after the migration. It only reads settings and doesn't change anything. Create it, run it with `sudo`, skim the file for anything that looks like a real password, key or token, and then share it:

```bash
cat > ~/prodesk-full-report.sh <<'EOF'
#!/bin/bash
U=${SUDO_USER:-brandon}
OUT=/home/$U/prodesk-full-report.txt
HP=/home/$U/homepage-config
sec() { echo; echo "=================== $1 ==================="; }
mask() { sed -E '/^[[:space:]]*-?[[:space:]]*[A-Za-z0-9_.-]*(pass|secret|token|key|auth|user|deviceid)[A-Za-z0-9_.-]*[[:space:]]*[:=]/I s/([:=][[:space:]]*).*/\1***MASKED***/'; }
BOOT=$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)" 2>/dev/null)
{
sec "SYSTEM"; hostnamectl | head -8; grep PRETTY_NAME /etc/os-release; ls /usr/share/xsessions 2>&1; uptime -p; timedatectl | grep "Time zone"
sec "HARDWARE"; dmidecode -s system-product-name 2>&1; lscpu | grep -E "Model name|^CPU\(s\)"; free -h | head -2
dmidecode -t memory 2>/dev/null | grep -E "^\s+(Size|Speed|Locator):" | grep -v "No Module"
sec "DRIVES: layout"; lsblk -o NAME,SIZE,ROTA,MODEL,TRAN,FSTYPE,LABEL,UUID,MOUNTPOINTS
sec "DRIVES: space"; df -hT -x tmpfs -x devtmpfs -x squashfs -x efivarfs
sec "DRIVES: fstab"; grep -v '^#' /etc/fstab | grep -v '^$'
sec "DRIVES: mount points and folders"; lsattr -d /mnt/storage /mnt/disks/* 2>&1; ls -la /mnt /mnt/disks /mnt/storage 2>&1; ls -la /usr/local/bin /usr/local/sbin 2>&1
sec "DRIVES: health"
echo "-- boot drive /dev/$BOOT"; smartctl -i -H -A /dev/$BOOT 2>&1 | grep -E "Device Model|Model Family|User Capacity|Rotation|overall-health|Power_On_Hours|Load_Cycle|Reallocated_Sector|Current_Pending|Temperature"; hdparm -B /dev/$BOOT 2>&1 | tail -1
echo "-- main drive (label MAIN1)"; smartctl -i -H -A -d sat /dev/disk/by-label/MAIN1 2>&1 | grep -E "Device Model|User Capacity|Rotation|overall-health|Power_On_Hours|Load_Cycle|Reallocated_Sector|Current_Pending|Temperature"; hdparm -B "/dev/$(lsblk -no pkname "$(readlink -f /dev/disk/by-label/MAIN1)")" 2>&1 | tail -1
sec "SYSTEMD AND CRON"; cat /etc/systemd/system/docker.service.d/*.conf 2>&1; for s in docker tailscaled ssh anydesk lightdm; do echo "$s: $(systemctl is-active $s 2>&1)"; done; echo "systemd-resolved enabled: $(systemctl is-enabled systemd-resolved 2>&1)"
echo "-- root cron"; crontab -l 2>&1 | grep -v '^#'; echo "-- load cycle log"; tail -5 /var/log/loadcycles.log 2>&1; echo "-- hdd-recover"; cat /usr/local/bin/hdd-recover 2>&1
sec "STORAGE POOLS AND BACKUP"; /usr/local/sbin/drives version 2>&1; /usr/local/sbin/drives status 2>&1; echo "-- backup settings"; cat /etc/homelab-backup.conf 2>&1; echo "-- last lines of the backup log"; tail -5 /var/log/homelab-backup.log 2>&1
sec "NETWORK AND DNS"; ip -4 -br addr; cat /etc/resolv.conf; ss -tulpn | grep ':53 '; ufw status 2>&1 | head -2; nslookup google.com 192.168.1.198 2>&1 | tail -4
sec "REMOTE ACCESS SETTINGS"; grep -E "^Handle" /etc/systemd/logind.conf 2>&1; grep -h -E "^autologin" /etc/lightdm/lightdm.conf /etc/lightdm/lightdm.conf.d/* 2>&1; cat /etc/apt/sources.list.d/docker.list 2>&1
sec "DOCKER"; docker --version; docker compose version; docker info 2>/dev/null | grep -E "Docker Root Dir|Storage Driver"
echo; docker compose ls -a 2>&1; echo; docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
echo; docker image ls --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}'; echo; docker volume ls
sec "DOCKER: versions"; for c in $(docker ps -aq); do docker inspect -f '{{.Name}}  {{index .Config.Labels "org.opencontainers.image.version"}}' $c; done
sec "DOCKER: mounts and restart policy"
for c in $(docker ps -aq); do docker inspect "$c" --format '== {{.Name}} | restart: {{.HostConfig.RestartPolicy.Name}} | network: {{.HostConfig.NetworkMode}}{{println}}{{range .Mounts}}   {{.Source}} -> {{.Destination}} ({{if .RW}}rw{{else}}ro{{end}}){{println}}{{end}}'; done
sec "DOCKER: which drive each container sees"
for c in immich_server filebrowser-filebrowser-1 nextcloud homepage; do echo "-- $c"; docker exec "$c" df -h /data /srv/hdd /srv/750GB_HDD /mnt/storage 2>/dev/null; done
sec "PORTAINER STACK FILES (secrets masked)"
for f in $(find /var/lib/docker/volumes/portainer_data/_data/compose -maxdepth 2 -type f 2>/dev/null | sort); do echo "### $f"; mask < "$f"; echo; done
sec "TAILSCALE"; tailscale version | head -1; tailscale ip -4; tailscale status --peers=false 2>&1 | head -3; tailscale dns status 2>&1 | head -15; tailscale serve status 2>&1
sec "ADGUARD HOME CONFIG"; awk '/^http:/,/^users:/' /opt/adguard-docker/conf/AdGuardHome.yaml 2>&1; awk '/^dns:/,/^tls:/' /opt/adguard-docker/conf/AdGuardHome.yaml 2>&1 | head -60; awk '/^filters:/,/^whitelist_filters:/' /opt/adguard-docker/conf/AdGuardHome.yaml 2>&1 | head -80
sec "NEXTCLOUD SETTINGS"; docker exec -u www-data nextcloud php occ status 2>&1
for k in trusted_domains overwritehost overwriteprotocol overwrite.cli.url trusted_proxies datadirectory allow_local_remote_servers; do echo -n "$k: "; docker exec -u www-data nextcloud php occ config:system:get $k 2>&1 | tr '\n' ' '; echo; done
sec "FOLDER SIZES"; du -sh /home/$U/immich /home/$U/nextcloud /home/$U/750GB_HDD /mnt/storage/* 2>&1
sec "HOMEPAGE CONFIG (secrets masked)"; ls -la $HP
for f in services.yaml widgets.yaml settings.yaml bookmarks.yaml docker.yaml custom.js custom.css; do echo "### $f"; mask < "$HP/$f" 2>&1; echo; done
sec "HOMEPAGE RECENT ERRORS"; docker logs homepage --tail 80 2>&1 | grep -i -E "error|warn" | tail -12 | cut -c1-220
} > "$OUT" 2>&1
chown "$U":"$U" "$OUT"
echo "Saved: $OUT"
EOF
sudo bash ~/prodesk-full-report.sh
```

The `mask` function hides the value of any setting whose name contains `pass`, `secret`, `token`, `key`, `auth`, `user` or `deviceid`. It masks only settings, so paths and image names stay readable. Always read the file once before you share it. `bookmarks.yaml` is included in the report, so don't publish the report if your real bookmarks hold personal links.

---

## 6. Prevention checklist

**Storage**

- [ ] Add, remove and move drives with `sudo drives`, and don't edit the pool lines in `/etc/fstab` by hand. Every drive is mounted by UUID with `nofail` under `/mnt/disks/<label>`, and the pools are at `/mnt/storage` and `/mnt/backup`.
- [ ] Practise any new drive operation first in test mode (`sudo DRIVES_TEST=1 drives`), and run `test-cleanup` afterwards.
- [ ] Keep the empty mount points locked with `chattr +i` (`drives` does it before mounting).
- [ ] Keep the Docker wait-for-mount file in `/etc/systemd/system/docker.service.d/`.
- [ ] Keep databases (Immich, Nextcloud) on the boot drive, and photos and files in the main pool.
- [ ] Keep the power level at 254 on every drive (`sudo drives power`), and keep both `@reboot` cron lines.
- [ ] Before unplugging a drive on purpose, use `sudo drives` and choose **3** (Disconnect a drive). Don't just pull the cable.
- [ ] After any reconnect or power cut, run `sudo hdd-recover`.
- [ ] Check `sudo drives status` every few days: every pool drive `PASSED`, and the last backup `OK` with a recent date. Keep an eye on the numbers from `smartctl` too (zeros for reallocated and pending sectors).
- [ ] The daily backup dumps Nextcloud's database (30 days kept) and keeps deleted files for 30 days. Until a backup drive is connected, it sits on the boot drive, which doesn't protect against a failed boot drive.
- [ ] Run one command at a time when checking things, and keep any "undo" command in its own block.
- [ ] If the boot drive dies, follow [Step 11](#step-11-rebuild-the-server-from-github-and-the-backup). Until `BACKUP1` exists, copy the `db-dumps` and `boot-configs` folders of the interim backup to another computer once a month.
- [ ] If a pool drive dies for good, use `sudo drives replace` ([Step 10](#step-10-replace-a-dead-drive)). I rehearsed it once with the USB stick on 2026-10-23. Do not improvise on the live pool.
- [ ] Run `sudo install` and `sha256sum -c` from inside the folder that holds the files ([A16](#a16-install-says-cannot-stat-when-installing-a-script)). Keep `SHA256SUMS` in step with the files: five lines today.
- [ ] Keep the `homelab` login block in `~/.bashrc` free of exported variables, or VS Code copies them into every terminal ([H5](#h5-the-cheat-sheet-does-not-appear-in-the-vs-code-terminal)).

**Deploying**

- [ ] Download images with `docker pull` before deploying stacks from GitHub's registry, one at a time.
- [ ] Deploy Immich, wait for it to turn healthy, and only then deploy Nextcloud.
- [ ] Use the exact stack names from this guide, because container names are built from them.
- [ ] Choose passwords with letters and numbers only, and write them down before deploying. Nextcloud reads them only once.
- [ ] Put a `base64:` prefix on Speedtest Tracker's app key, and change the default `admin@example.com` login.
- [ ] Give every container's data a bind-mounted folder or a named volume, never an anonymous one ([B6](#b6-a-container-starts-empty-after-update-the-stack)). Check with the `docker inspect` line in section [5](#5-diagnostic-commands).

**Network**

- [ ] Reserve the server's address in the router.
- [ ] After a Tailscale rename or port change, check `tailscale serve status` and update Homepage's `HOMEPAGE_ALLOWED_HOSTS`, Nextcloud's overwrite settings and your apps.
- [ ] Use the local address (`192.168.1.198`), not the Tailscale one, for any step that restarts Tailscale.
- [ ] After a Tailscale update, run `nslookup github.com` on the server. If it says `SERVFAIL`, follow [F6](#f6-the-server-cannot-look-up-names-after-a-tailscale-update).
- [ ] Point each device's DNS at the server by hand if the router won't allow it, and check the AdGuard Query Log.

**Updating**

- [ ] Before any update, run `sudo homelab-backup`, wait for `finished: OK`, and update one service at a time (section [7](#7-updating-services)).
- [ ] Run `docker pull` first and update only what says `Downloaded newer image`. Update Immich and Nextcloud on their own, never together.
- [ ] Pin Nextcloud to its major version (`nextcloud:35-apache`) so a re-pull can't start a major upgrade by surprise, and never skip a major version.
- [ ] Update Tailscale from the local address (`192.168.1.198`), and expect every container to restart when Docker Engine is updated.
- [ ] FileBrowser is no longer maintained. Keep it off the internet and keep its command runner off.

**Homepage and secrets**

- [ ] Stop Homepage before editing its keys, then start it again.
- [ ] Copy API tokens and keys with the copy button when they're first shown, and never commit real ones. Use `your-own-key` in files you publish.
- [ ] Check a YAML file with a parser before you copy it to the server and before you upload it to GitHub: `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1])); print('OK')" Portainer-code/immich.yaml`. On 2026-10-23 I checked all nine stack files in the repository and found three that would not parse: a missing closing quote in the Speedtest Tracker file, and plain-text notes after the YAML in the Immich and Nextcloud files. They are comments now.
- [ ] Keep the `.gitattributes` file in the repository. The nine stack files had Windows line endings (CRLF) from the upload and are plain LF now; the file keeps them that way.
- [ ] After editing a Homepage file, restart it and hard-refresh the browser.

---

## 7. Updating services

How to keep each service, and the system under it, up to date. Written on 2026-10-23.

**How much of this has been tested.** I updated Portainer on 2026-10-22 ([7.3](#73-portainer)) and Speedtest Tracker on 2026-10-23 ([7.5](#75-speedtest-tracker)), and those two sections show what I ran and what happened, including what went wrong. Everything else was written from each project's own documentation and release page, and **I have not run those steps on this server yet**. Each service says so. When I run one, I will replace its "not yet run" line with the real output.

**How updates work here.** Most images use a moving tag (`latest`, `release` or no tag), so a container never updates by itself. An update is always the same two moves: download the newer image, then recreate the container from it. In Portainer, the second move is **Update the stack**. Settings and data that live in bind-mounted folders and in named Docker volumes survive the recreate. Data in an **anonymous** volume may not: it is how Speedtest Tracker lost its data ([B6](#b6-a-container-starts-empty-after-update-the-stack)). Check for them first (7.2, check 5).

### 7.1 What can be updated

Versions found on the projects' release pages on 2026-10-23. "Running" comes from my server report of 2026-10-20, except Portainer, Speedtest Tracker and Tailscale, which I looked at later. Check the live state with [7.2](#72-before-you-update-anything) before you act on this table.

| Service | Stack | Running | Newest found | What to do |
|---|---|---|---|---|
| Portainer | none (standalone container) | 2.45.2 | 2.45.3 | Updated on 2026-10-22: [7.3](#73-portainer) |
| Homepage | `homepage` | v2.6.0 | v2.6.0 | Nothing to do: [7.4](#74-homepage) |
| Speedtest Tracker | `speedtest-tracker` | v1.15.1-ls177 | v1.15.1 | Updated on 2026-10-23, and lost its data once: [7.5](#75-speedtest-tracker) |
| Netdata | `netdata` | nightly build | not versioned | Optional: [7.6](#76-netdata) |
| Beszel hub and agent | `beszel`, `beszel-agent` | 0.21.0 | 0.21.1 | Update, hub first: [7.7](#77-beszel-hub-and-agent) |
| AdGuard Home | `adguard` | v0.107.79 | v0.107.79 | Nothing to do (pinned tag): [7.8](#78-adguard-home) |
| FileBrowser | `filebrowser` | 2.63.23 | 2.63.23 | Nothing to do, and none will come: [7.9](#79-filebrowser) |
| Immich | `immich` | v3.3.3 | v3.3.5 | Update (security fixes): [7.10](#710-immich) |
| Nextcloud | `nextcloud` | 35.0.2 | 35.0.2 | Nothing to do now: [7.11](#711-nextcloud) |
| Docker Engine | system | 29.9.1 | 29.9.2 | Update: [7.12](#712-docker-engine) |
| Tailscale | system | 1.104.2 (updated itself) | 1.104.2 | Nothing to install, but check DNS: [7.13](#713-tailscale) |
| Linux Mint packages | system | not checked | not checked | Check and update: [7.14](#714-linux-mint-packages) |

Two notes on this table:

- **Immich v3.3.5** is a security release. Its release notes list no breaking changes and no manual steps, and say to update as soon as possible.
- **FileBrowser** is finished as a project. Its repository was archived on 2026-09-01, and its notice says there will be no further releases, bug fixes or security fixes. Version 2.63.23, which I run, is the last one. The notice suggests treating a copy that stays in use as unmaintained software.

### 7.2 Before you update anything

Do these five things every time. They take a few minutes and make every later step safer.

**1. Pick a quiet time.** Avoid 6:00 to 6:30, when the daily backup runs. Update one service at a time and wait until it is healthy before the next one. Never start Immich and Nextcloud together (see [A10](#a10-immich-and-nextcloud-overload-the-machine-when-they-start-together)).

**2. Make a fresh backup.** The first full run took 24 minutes. Later runs copy only what changed, so they should be shorter, but I haven't timed one yet. In the Linux server terminal:

```bash
sudo nohup /usr/local/sbin/homelab-backup >/dev/null 2>&1 &
sudo tail -f /var/log/homelab-backup.log
```

Press `Ctrl+C` when the log says `finished: OK`, then check the result:

```bash
sudo drives status
```

The "Last backup" line should show `result: OK` and today's time. Know what this backup covers:

| Covered by `homelab-backup` | Not covered |
|---|---|
| Everything in the main pool (`/mnt/storage`): Immich photos, Immich's own database dumps, Nextcloud files | The Immich database folder `/home/brandon/immich/postgres` (live files) |
| A fresh dump of the Nextcloud database | The Nextcloud database folder `/home/brandon/nextcloud/db` (the dump covers it) |
| Homepage config, AdGuard Home config, Nextcloud app files, and the Portainer, Beszel and FileBrowser volumes | The Netdata volumes. Speedtest Tracker's folder is covered only after you add it to `CONFIG_PATHS` ([Step 7](#step-7-the-daily-backup), "Extra folders") |

Also remember that the backup lives on the boot drive until a backup drive is connected, so it does not protect against that drive failing.

**3. See which images have a newer version.** Pulling only downloads an image. It does not touch a running container, so it is safe to run any time. Run the pulls one at a time, because the GitHub registry throttles parallel downloads ([B5](#b5-toomanyrequests-from-githubs-container-registry)). Each pull ends with either `Status: Downloaded newer image` (an update is available) or `Status: Image is up to date` (nothing to do):

```bash
docker pull ghcr.io/gethomepage/homepage:latest
docker pull lscr.io/linuxserver/speedtest-tracker:latest
docker pull netdata/netdata
docker pull henrygd/beszel:latest
docker pull henrygd/beszel-agent
docker pull filebrowser/filebrowser
docker pull ghcr.io/immich-app/immich-server:release
docker pull ghcr.io/immich-app/immich-machine-learning:release
docker pull nextcloud:apache
```

Pulling `nextcloud:apache` is harmless, but it can download a **new major version** of Nextcloud. Don't recreate Nextcloud until you have read section [7.11](#711-nextcloud). The Netdata image is large (about 1.3 GB), so give it time.

**4. Read the release notes** of anything you are about to update. The links are in [Sources](#716-sources).

**5. Check for anonymous volumes.** A container that keeps its data in an anonymous volume can come back empty after **Update the stack** ([B6](#b6-a-container-starts-empty-after-update-the-stack)). This only reads information:

```bash
docker inspect $(docker ps -q) --format '{{.Name}}: {{range .Mounts}}{{if eq .Type "volume"}}{{.Name}} {{end}}{{end}}' | grep -E '[0-9a-f]{64}'
```

Any container listed there needs a bind mount before you update it, or at least a `docker cp <container>:<path> ~/some-folder` copy of its data. If nothing is listed, you are fine.

**The same Portainer steps for every stack.** Each service section below refers to them:

1. Open Portainer and click **Stacks**, then the name of the stack.
2. Click the **Editor** tab. Leave the YAML and the environment variables alone. Passwords and keys stay saved.
3. If a switch called **Re-pull image and redeploy** is shown, switch it on. If it isn't shown, nothing is lost: the image was already downloaded in the terminal, and Docker Compose recreates a container when its image has changed.
4. Click **Update the stack**. The page says the request was accepted, and the containers restart in the background.
5. Back in the terminal, check the result with:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### 7.3 Portainer

**Status: done and tested on 2026-10-22** (2.45.2 to 2.45.3). Portainer is the one container here that is not a stack. It was started with `docker run`, so it is recreated from the terminal, not with **Update the stack**. Its settings, users, stack files and the token Homepage uses are in the `portainer_data` volume, so they survive.

**1. Record how it runs now.** This only reads information:

```bash
docker inspect portainer --format 'Image: {{.Config.Image}}{{"\n"}}Restart: {{.HostConfig.RestartPolicy.Name}}{{"\n"}}Ports: {{json .HostConfig.PortBindings}}{{"\n"}}Mounts:{{range .Mounts}}{{"\n"}}  {{.Type}} {{.Name}} {{.Source}} -> {{.Destination}}{{end}}'
```

Mine printed `portainer/portainer-ce:latest`, `Restart: always`, ports 9000 and 9443, the `portainer_data` volume at `/data` and the Docker socket. Every option in step 4 comes from this output.

**2. Stop Portainer and back up its data.** Stopping first means the database file is not being written to. Your other containers are not affected. The Portainer page and the Homepage Portainer card are down until step 4. The backup holds Portainer's private keys, so lock it down and never put it on GitHub:

```bash
docker stop portainer
sudo tar -czf ~/portainer_data-backup-$(date +%F).tar.gz -C /var/lib/docker/volumes/portainer_data/_data .
sudo chown brandon:brandon ~/portainer_data-backup-$(date +%F).tar.gz
chmod 600 ~/portainer_data-backup-$(date +%F).tar.gz
ls -lh ~/portainer_data-backup-$(date +%F).tar.gz
```

Mine was 77 KB and listed `portainer.db`, `portainer.key`, `tls/`, `chisel/` and `compose/` (the nine stack files).

**3. Download the new image.** The old container stays where it is:

```bash
docker pull portainer/portainer-ce:latest
docker images portainer/portainer-ce
```

The image ID changed from `03f94a406496` to `3609c307943b`.

**4. Keep the old container as a spare and start the new one.** The rename and the restart policy `no` mean the old one never starts by itself:

```bash
docker rename portainer portainer-old
docker update --restart=no portainer-old
```

```bash
docker run -d --name portainer --restart=always -p 9000:9000 -p 9443:9443 -v portainer_data:/data -v /var/run/docker.sock:/var/run/docker.sock portainer/portainer-ce:latest
```

**5. Check it:**

```bash
docker ps --filter name=portainer --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
docker logs --tail 15 portainer
```

The log showed `migrating database from version 2.45.2 to 2.45.3`, a safety copy at `/data/backups/portainer.db.bak`, and `starting Portainer ... version=2.45.3` with the web server listening on ports 9000 and 9443. Then log in and look at the version at the bottom of the left menu.

**6. Clean up** once everything has worked for a day or so:

```bash
docker rm portainer-old
docker image prune
```

`docker image prune` removes the old, unused image (about 200 MB). It asks for confirmation.

**Rollback (not tested).** The database was upgraded, so starting `portainer-old` against it is not safe. Go back by restoring the backup into the volume and running the old version:

```bash
docker stop portainer
docker rm portainer
sudo find /var/lib/docker/volumes/portainer_data/_data -mindepth 1 -delete
sudo tar -xzf ~/portainer_data-backup-2026-10-22.tar.gz -C /var/lib/docker/volumes/portainer_data/_data
docker run -d --name portainer --restart=always -p 9000:9000 -p 9443:9443 -v portainer_data:/data -v /var/run/docker.sock:/var/run/docker.sock portainer/portainer-ce:2.45.2
```

Use the date of your own backup file in the `tar` line.

### 7.4 Homepage

**Status: written from the documentation, not yet run on my server.** Homepage v2.6.0 is the newest release (published on 2026-10-17), so there is nothing to update now. When a newer one appears:

1. Do the four checks in [7.2](#72-before-you-update-anything). Homepage's settings are in `/home/brandon/homepage-config`, which the daily backup covers.
2. Read the release notes. The v2.6.0 notes mention changes to how `$` is handled in secrets, so check the notes when your keys contain a dollar sign.
3. Download the image:

   ```bash
   docker pull ghcr.io/gethomepage/homepage:latest
   ```

4. In Portainer, open the `homepage` stack and use **Update the stack** (the steps are in 7.2). The settings folder is a bind mount, and `HOMEPAGE_ALLOWED_HOSTS` is part of the stack, so both stay as they are.
5. Check it. The container should become `healthy`, the log should not show a "Host validation failed" line, and the page should load after a hard refresh (`Ctrl+Shift+R`):

   ```bash
   docker ps --filter name=homepage --format "table {{.Names}}\t{{.Status}}"
   docker logs --tail 20 homepage
   ```

   The Netdata line `Parse Error: Data after Connection: close` is known and harmless ([G13](#g13-the-netdata-card-is-green-but-homepages-log-shows-a-parse-error)).

**Rollback:** in the stack's **Editor**, change `homepage:latest` to the previous version's tag (for example `homepage:v2.6.0`) and click **Update the stack**. Your files in `/home/brandon/homepage-config` are not changed by an update.

### 7.5 Speedtest Tracker

**Status: done on 2026-10-23** (v1.15.0 to v1.15.1-ls177), **but it lost its data and I had to restore it.** The update itself is easy. The data loss was my own setup's fault, and it is fixed for good now. Version v1.15.1 was released on 2026-10-22. Its notes list a fix for a server filter that returned nothing with SQLite, and dependency updates. They list no breaking change.

**What happened.** My stack had no `volumes:` line, so Speedtest Tracker's `/config` folder (the database, the settings and the application key) was an anonymous Docker volume. I copied `/config` out by hand before updating, which saved the data. **Update the stack** then started a new container with a new empty volume. The old results and settings were gone until I restored them ([B6](#b6-a-container-starts-empty-after-update-the-stack)). My first version of this section said that the data survives a recreate. That was wrong for this container.

**The procedure to follow,** with what I learned. If your stack already has the bind mount from [Phase 9](#phase-9-speedtest-tracker-and-netdata), skip step 2.

1. Do the five checks in [7.2](#72-before-you-update-anything).
2. **Make sure `/config` is a folder on the host, not an anonymous volume.** Check:

   ```bash
   docker inspect speedtest-tracker --format '{{range .Mounts}}{{.Type}} {{.Source}} -> {{.Destination}}{{println}}{{end}}'
   ```

   You want a line that starts with `bind /home/brandon/speedtest-tracker -> /config`. A line that starts with `volume` and a long name means an anonymous volume. In that case, do the fix in [B6](#b6-a-container-starts-empty-after-update-the-stack) first (copy the data, add the `volumes:` lines), and only then update.
3. Make a copy by hand anyway. It is cheap, and it is what saved my data:

   ```bash
   docker cp speedtest-tracker:/config ~/speedtest-config-backup-$(date +%F)
   ls ~/speedtest-config-backup-$(date +%F)
   ```

   Keep this copy private. It contains the database and the application key.
4. Download the image:

   ```bash
   docker pull lscr.io/linuxserver/speedtest-tracker:latest
   ```

5. In Portainer, open the `speedtest-tracker` stack and use **Update the stack**. `APP_KEY` stays in the stack's variables, so don't retype it.
6. Check it:

   ```bash
   docker ps --filter name=speedtest-tracker --format "table {{.Names}}\t{{.Status}}"
   docker logs --tail 20 speedtest-tracker
   ```

   The log may say `generating self-signed keys` on the first start of a new `/config`. That is normal for an empty folder, and it is also what I saw when the data was lost, so don't use that line as proof either way. Open `https://pc.griffin-luma.ts.net:1007`, log in, and check that the past results are still listed. Then check that the Speedtest card on the Homepage dashboard shows numbers. Its API token lives in the database, so it should keep working.

**Result on my server:** after the restore and the bind mount, the card was green, and it was still green after another **Update the stack**.

**Rollback:** in the **Editor**, change `:latest` to the earlier version's tag (the report showed `v1.15.0-ls175`; check the exact spelling on the image's tag list) and click **Update the stack**. If the new version changed the database, stop the container and put the copy from step 3 back into the data folder:

```bash
docker stop speedtest-tracker
cp -a ~/speedtest-config-backup-DATE/. ~/speedtest-tracker/
docker start speedtest-tracker
```

### 7.6 Netdata

**Status: written from the documentation, not yet run on my server.** My stack uses `netdata/netdata` with no tag, which means `latest`. Netdata's documentation says `latest` may include nightly builds, and my report showed a nightly build. There is no fixed version to compare, so a pull simply tells you whether the image changed. The configuration, data and cache are in the volumes `netdataconfig`, `netdatalib` and `netdatacache` and survive an update.

1. Do the checks in [7.2](#72-before-you-update-anything). Nothing here needs special care.
2. Download the image (about 1.3 GB):

   ```bash
   docker pull netdata/netdata
   ```

3. If it printed `Downloaded newer image`, open the `netdata` stack in Portainer and use **Update the stack**.
4. Check it:

   ```bash
   docker ps --filter name=netdata --format "table {{.Names}}\t{{.Status}}"
   docker exec netdata-netdata-1 netdata -W buildinfo | head -5
   ```

   The container should become `healthy`. The Netdata card on Homepage should be green.

**Optional: follow stable releases only.** To avoid nightly builds, change the image line in the stack's **Editor** from `netdata/netdata` to `netdata/netdata:stable` and click **Update the stack**. Netdata's documentation describes `stable` as the most recently published stable build. I have not done this, so treat it as a choice to make, not a fix.

**Rollback:** change the image line to a version tag from the image's tag list on Docker Hub (for example `netdata/netdata:v2.0.0`, written here as a format example only) and update the stack.

### 7.7 Beszel hub and agent

**Status: written from the documentation, not yet run on my server.** Version 0.21.1 was released on 2026-10-22. The notes mention that some memory fields are being replaced by new fields that carry byte values, and that the new fields are filled in by a hub 0.21.1 or newer. Beszel's guides don't state an update order. My reasoning is that the hub should be updated first so it understands everything the newer agent sends. That is my inference, not a rule from the project.

1. Do the four checks in [7.2](#72-before-you-update-anything). The Beszel hub's data is in the `beszel_beszel_data` volume, which the daily backup covers. Beszel's guide also mentions the hub's own backup feature as an extra copy.
2. Download both images:

   ```bash
   docker pull henrygd/beszel:latest
   docker pull henrygd/beszel-agent
   ```

3. **Hub first.** In Portainer, open the `beszel` stack and use **Update the stack**. Check it:

   ```bash
   docker ps --filter name=beszel --format "table {{.Names}}\t{{.Status}}"
   docker logs --tail 15 beszel
   ```

   Open the Beszel page (`https://pc.griffin-luma.ts.net:1003`) and log in. The system `pc` should still be listed.
4. **Then the agent.** Open the `beszel-agent` stack and use **Update the stack**. The `KEY` and `TOKEN` variables stay saved, so don't retype them. The system `pc` should show as up again in the hub within a minute.
5. Check that the Beszel card on Homepage shows the numbers.

**Rollback:** change the image lines to `henrygd/beszel:0.21.0` and `henrygd/beszel-agent:0.21.0` in the two stacks' **Editor** and update them. If the hub's data looks wrong afterwards, restore the `beszel_beszel_data` folder from the backup (`/home/brandon/750GB_HDD/backup-interim/boot-configs/var/lib/docker/volumes/beszel_beszel_data`) with the hub stopped.

### 7.8 AdGuard Home

**Status: written from the documentation, not yet run on my server.** This stack pins its version in the image line (`adguard/adguardhome:v0.107.79`), so it never changes by itself. v0.107.79 is also the newest release found (published in August), so there is nothing to update now. When a newer version is out:

1. Read its release notes on the project's release page. The v0.107.79 notes say `strict_sni_check` is deprecated, so check whether my config uses it:

   ```bash
   sudo grep -n strict_sni_check /opt/adguard-docker/conf/AdGuardHome.yaml
   ```

   No output means it isn't set.
2. Do the checks in [7.2](#72-before-you-update-anything), then copy the AdGuard configuration. The copy holds a password hash, so keep it private:

   ```bash
   sudo cp -a /opt/adguard-docker/conf ~/adguard-conf-backup-$(date +%F)
   ```

3. Download the new version. Replace `vX.Y.Z` with the version you picked, for example the one in the release notes:

   ```bash
   docker pull adguard/adguardhome:vX.Y.Z
   ```

4. In Portainer, open the `adguard` stack, click **Editor**, change only the version at the end of the image line to `vX.Y.Z`, and click **Update the stack**. DNS is down for a few seconds. Devices that use 8.8.8.8 as their alternate keep working, without filtering.
5. Check it:

   ```bash
   docker ps --filter name=adguardhome --format "table {{.Names}}\t{{.Status}}"
   nslookup example.com 192.168.1.198
   ```

   The lookup should return an address. Open AdGuard Home (`https://pc.griffin-luma.ts.net:1004`) and check that the Query Log is filling and the version in the footer is the new one.

**Rollback:** change the image line back to the old tag (`v0.107.79`) in the **Editor** and update the stack. If the configuration file was changed by the newer version, stop the container, put the copy from step 2 back into `/opt/adguard-docker/conf`, and start it.

### 7.9 FileBrowser

**Status: nothing to update, and nothing will come.** The latest and last release is 2.63.23, which is what I run. The project's repository was archived on 2026-09-01, and its notice says there will be no further releases, bug fixes or security fixes. The Docker images stay available.

You can confirm that nothing changed with:

```bash
docker pull filebrowser/filebrowser
```

It should end with `Status: Image is up to date`. If it ever downloads something newer, update it like the others: open the `filebrowser` stack in Portainer and use **Update the stack**, then check `docker ps` for `filebrowser-filebrowser-1`.

What I do about it, following the project's own advice for unmaintained software:

- FileBrowser is reachable only through Tailscale. There is no port forwarding on the router, so it is not exposed to the internet.
- Keep its command runner turned off (the FileBrowser settings page has the switch).
- Replacing it with a maintained file manager is a decision for later. I have not chosen one.

### 7.10 Immich

**Status: written from the documentation, not yet run on my server.** v3.3.5 is a security release with no breaking changes and no manual steps listed. The stack uses `ghcr.io/immich-app/immich-server:release` and the matching machine-learning image, so a re-pull moves to the newest version.

Immich's own rules, from its upgrade page:

- Read the release notes first. Breaking changes are supposed to appear only in major releases.
- The server only works with its own major version. The mobile apps support the current and the previous major version, so update the iPhone app first when a major version changes.
- Downgrades are not supported, not even inside a minor version. Rolling back means restoring a backup.

Steps:

1. Do the four checks in [7.2](#72-before-you-update-anything), including the fresh backup.
2. Make a fresh database dump. Immich also writes its own dump every night at 2:00 into the `backups` folder of the photo folder and keeps the last 14. Create one now: in the Immich web page, open **Administration**, then **Job Queues**, click **Create job**, choose **Create Database Dump** and confirm. Then check that it appeared:

   ```bash
   ls -lh /mnt/storage/immich/backups | tail -3
   ```

   The newest file should have today's time.
3. Download the two images, one at a time (the GitHub registry throttles parallel pulls):

   ```bash
   docker pull ghcr.io/immich-app/immich-server:release
   docker pull ghcr.io/immich-app/immich-machine-learning:release
   ```

4. Leave the database image (`immich/postgres:14-vectorchord0.4.3-pgvectors0.2.0`) and the Valkey image exactly as they are. They are pinned on purpose, and Immich's release notes say when they change.
5. In Portainer, open the `immich` stack and use **Update the stack**.
6. Wait. A first start after an update can take from seconds to several minutes. Logs that seem stuck on `Reindexing clip_index` or `Reindexing face_index` are normal as long as no error appears. Don't touch Nextcloud meanwhile. Follow the log and the status until all four containers are `healthy`:

   ```bash
   docker logs -f --tail 30 immich_server
   ```

   Press `Ctrl+C` to leave the log, then:

   ```bash
   docker ps --format "table {{.Names}}\t{{.Status}}"
   ```

7. Check it. Open Immich (`https://pc.griffin-luma.ts.net:1002`), log in, and confirm that the server version is the new one and that your photos and the storage meter (bottom left) show as before. Open the Immich app on the iPhone and let it sync. Then check the Immich card on Homepage and the Nextcloud integration (Nextcloud's Immich page should still list your photos).
8. When everything is fine, free the disk space of the old images:

   ```bash
   docker image prune
   ```

**Rollback:** only for a small problem inside the same major version. In the stack's variables set `IMMICH_VERSION` to the previous version (for example `v3.3.3`) and click **Update the stack**. Immich does not support downgrades, so if the database was changed by the new version, restore the database from the dump made in step 2 following Immich's backup and restore page.

### 7.11 Nextcloud

**Status: written from the documentation, not yet run on my server.** 35.0.2 is the newest Nextcloud 35 release (published on 2026-10-15), which is what I run (`35.0.2.2`), so there is nothing to update now. My stack also has `postgres:16-alpine` (the database), `redis:alpine` (the cache) and a second container, `nextcloud_cron`, that uses the same Nextcloud image.

**The one rule that matters.** The Docker image docs say it is only possible to upgrade one major version at a time (for example 35 to 36, never 35 straight to 37). My image line is `nextcloud:apache`, which always points at the newest major. So the day Nextcloud 36 arrives, a re-pull followed by **Update the stack** would start that upgrade without asking. To stay in control, pin the major version once, in the `nextcloud` stack's **Editor**: change both `image: nextcloud:apache` lines (the `nextcloud` and the `nextcloud_cron` service) to `image: nextcloud:35-apache`, then click **Update the stack**. It's the same software, so nothing changes today. I have not done this yet.

**A normal update inside the same major version (for example 35.0.2 to 35.0.3):**

1. Do the four checks in [7.2](#72-before-you-update-anything). The backup includes a fresh dump of the Nextcloud database, and that is your safety net, because Nextcloud cannot go back to an older version.
2. Write down the current state:

   ```bash
   docker exec -u www-data nextcloud php occ status
   ```

   It should say `installed: true`, the version, and `maintenance: false`.
3. Download the image for your pinned tag:

   ```bash
   docker pull nextcloud:35-apache
   ```

4. In Portainer, open the `nextcloud` stack and use **Update the stack**. Both Nextcloud containers are recreated. On start, the image notices the new version and runs the upgrade by itself, so you don't run `occ upgrade`.
5. Watch the log until Apache is ready. The first start after an update can take several minutes, and the page shows an error until then ([D5](#d5-a-502-right-after-deploying-nextcloud)):

   ```bash
   docker logs -f --tail 30 nextcloud
   ```

   Press `Ctrl+C` when it says it is ready.
6. Check the result:

   ```bash
   docker exec -u www-data nextcloud php occ status
   docker ps --format "table {{.Names}}\t{{.Status}}"
   ```

   It should show the new version, `needsDbUpgrade: false` and `maintenance: false`.
7. Update the apps (such as `integration_immich`) from Nextcloud: sign in as admin, open the profile menu, click **Apps**, then **Updates**, and update what is listed. The command-line version, which I have not run, is:

   ```bash
   docker exec -u www-data nextcloud php occ app:update --all
   ```

8. Open **Administration settings**, then **Overview**, and read the list of warnings. Check the Homepage Nextcloud card too (it reads `/status.php` and the serverinfo token).

**A major upgrade (35 to 36).** Don't do it on the day it's released. Wait until the apps you use (including `integration_immich`) support it, read the Nextcloud release notes, make sure the backup is fresh, and then in the **Editor** change both image lines from `35-apache` to `36-apache` and update the stack. Do one major at a time.

**Rollback:** there is none inside Nextcloud. Restore the database dump from the backup (`db-dumps` folder in the backup) and the app files, which means you also need the matching older image. That's why the backup comes first.

### 7.12 Docker Engine

**Status: written from the documentation, not yet run on my server.** 29.9.2 is newer than the 29.9.1 I run. Docker came from Docker's Ubuntu `noble` repository ([B1](#b1-docker-installs-from-the-wrong-repository-on-mint)), so `apt` updates it.

**What to expect:** restarting Docker stops all containers. The `restart` settings in my stacks bring them back, but every service is down for a minute or two, and Immich and Nextcloud take longer to turn healthy. Pick a quiet time and update Docker on its own, not together with anything else.

1. Do the four checks in [7.2](#72-before-you-update-anything).
2. See what apt offers:

   ```bash
   sudo apt update
   apt list --upgradable 2>/dev/null | grep -E 'docker|containerd'
   ```

3. Upgrade only the Docker packages:

   ```bash
   sudo apt install --only-upgrade docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

4. Check it, after two or three minutes:

   ```bash
   docker version --format '{{.Server.Version}}'
   docker compose version
   systemctl show docker -p ActiveState
   docker ps --format "table {{.Names}}\t{{.Status}}"
   ```

   The version should be 29.9.2, and all 16 containers should come back up on their own. The wait-for-mount file in `/etc/systemd/system/docker.service.d/` is not touched by an update. If a container that needs the drive shows the wrong disk, run `sudo hdd-recover`.

**Rollback:** list the older versions with `apt list --all-versions docker-ce` and install one by naming its version, as Docker's install page describes. I wouldn't downgrade unless Docker itself stops working.

### 7.13 Tailscale

**Status: the machine is already on 1.104.2, and the update broke DNS on the server.** I had not run these steps. The Machines page in the Tailscale admin console showed `pc` on 1.104.2, so the machine had updated itself. Right after that, the server could not look up names (`SERVFAIL` from `100.100.100.100`) and the Tailscale card on Homepage turned red. The cause and the fix are in [F6](#f6-the-server-cannot-look-up-names-after-a-tailscale-update). The steps below are written from Tailscale's documentation, which says an update through a package manager is done by that manager and also names `tailscale update`. I have not run them.

**Important:** use the local address for this, not the Tailscale one. A restart of Tailscale drops a session that is running over Tailscale ([E7](#e7-an-ssh-session-over-tailscale-drops-when-tailscale-restarts)). From the Windows PC:

```powershell
ssh brandon@192.168.1.198
```

Then, in the Linux server terminal:

1. Check the current version and what is offered:

   ```bash
   tailscale version
   sudo apt update
   apt list --upgradable 2>/dev/null | grep tailscale
   ```

2. Upgrade only Tailscale:

   ```bash
   sudo apt install --only-upgrade tailscale
   ```

3. Check it:

   ```bash
   tailscale version
   tailscale status | head -5
   tailscale serve status
   ```

   The version should be 1.104.2, the status should show `pc` connected, and the Serve status should list all nine entries on ports 1000 to 1008. Open one address from your phone or the Windows PC to confirm, for example Homepage on port 1000.

4. **Check that the server can still look up names.** This is the step that would have caught the problem:

   ```bash
   cat /etc/resolv.conf
   nslookup github.com
   ```

   The lookup must return addresses. If it says `SERVFAIL`, follow [F6](#f6-the-server-cannot-look-up-names-after-a-tailscale-update), and restart Homepage afterwards.

If the Serve list is empty after an update, re-create the nine entries from the Tailscale phase of the migration ([Phase 6](#phase-6-tailscale-addresses)).

### 7.14 Linux Mint packages

**Status: written from general apt practice, not yet run for this purpose on my server.** This covers the operating system and everything installed with `apt`, such as `mergerfs`, `smartmontools` and the kernel.

1. Do the four checks in [7.2](#72-before-you-update-anything).
2. Update Docker and Tailscale first, on their own, by following [7.12](#712-docker-engine) and [7.13](#713-tailscale). That way their restarts don't hide in a large update.
3. See what is waiting:

   ```bash
   sudo apt update
   apt list --upgradable 2>/dev/null
   ```

   Read the list. Look for a new kernel (`linux-image-...`) and for packages you recognize, such as `mergerfs`.
4. Install the updates:

   ```bash
   sudo apt upgrade
   ```

   Answer the prompts after reading them. Don't remove old kernels afterwards. Keeping the previous one gives you something to boot if the new one has a problem.
5. See whether a restart is needed:

   ```bash
   ls /var/run/reboot-required 2>/dev/null && echo "restart needed"
   ```

6. If a restart is needed (a new kernel always needs one), stop and make sure the backup is not running. Then:

   ```bash
   sudo reboot
   ```

7. After about five minutes, run the same checks as after any restart (one `findmnt` per command, see [A12](#a12-findmnt-prints-nothing-when-given-two-paths)):

   ```bash
   findmnt /mnt/storage
   findmnt /mnt/disks/MAIN1
   docker ps --format "table {{.Names}}\t{{.Status}}"
   sudo drives status
   uname -r
   ```

   If the drive is missing or a container shows the wrong disk, run `sudo hdd-recover`.

**Rollback:** if a new kernel causes trouble, choose the older kernel from the GRUB menu's advanced options at boot. That menu appears before any remote access works, so it needs a monitor and keyboard connected to the machine. Connect them before you reboot into a new kernel if you want that option.

### 7.15 After updating

1. Run the inventory script from [section 5](#5-diagnostic-commands) so the report shows the new versions, and keep the new report.
2. Check `sudo drives status` again the next morning: the 6:00 backup should say `OK`.
3. Update the version numbers anywhere you keep them (the README's "Tested with" line, if a version there changed).
4. Remove the spare Portainer container and the unused images once everything has worked for a day (see [7.3](#73-portainer), step 6).
5. Run `homelab` ([Step 9](#step-9-the-cheat-sheet-at-login)). Every status line should be green, and `nslookup github.com` should still work ([F6](#f6-the-server-cannot-look-up-names-after-a-tailscale-update)).

### 7.16 Sources

The steps above come from these pages, which I read on 2026-10-23:

- Immich: [upgrading](https://docs.immich.app/install/upgrading), [backup and restore](https://docs.immich.app/administration/backup-and-restore), [releases](https://github.com/immich-app/immich/releases/latest)
- Nextcloud: [Docker image (updating)](https://github.com/nextcloud/docker), [changelog](https://nextcloud.com/changelog/). Nextcloud's own admin manual blocks automated reading, so the `occ app:update --all` command and the Apps page steps come from my general knowledge and are untested.
- Portainer: [editing a stack](https://docs.portainer.io/user/docker/stacks/edit)
- Beszel: [hub installation](https://www.beszel.dev/guide/hub-installation), [agent installation](https://www.beszel.dev/guide/agent-installation), [releases](https://github.com/henrygd/beszel/releases/latest)
- AdGuard Home: [releases](https://github.com/AdguardTeam/AdGuardHome/releases/latest)
- Homepage: [releases](https://github.com/gethomepage/homepage/releases/latest)
- FileBrowser: [repository](https://github.com/filebrowser/filebrowser), [releases](https://github.com/filebrowser/filebrowser/releases/latest)
- Speedtest Tracker: [releases](https://github.com/alexjustesen/speedtest-tracker/releases/latest)
- Netdata: [Docker installation and updating](https://learn.netdata.cloud/docs/netdata-agent/installation/docker)
- Docker Engine: [install and upgrade on Ubuntu](https://docs.docker.com/engine/install/ubuntu/), [release notes](https://docs.docker.com/engine/release-notes/)
- Tailscale: [updating](https://tailscale.com/kb/1067/update), [releases](https://github.com/tailscale/tailscale/releases/latest)
