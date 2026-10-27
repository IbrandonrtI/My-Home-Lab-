# Storage: drive pools and backups

The big files live on hard drives grouped into **pools**. Immich photos, Nextcloud files and the FileBrowser share all sit in the **main pool**, which shows up as `/mnt/storage`. A second pool, `/mnt/backup`, holds the daily backup. Three small tools handle all of it, so adding, removing, moving or recovering a drive is a menu choice instead of a pile of `fstab` edits. A fourth one, `homelab`, prints the commands and current status whenever I open a terminal, so I don't have to remember any of them.

| Command | What it does |
| :--- | :--- |
| `sudo drives` | A menu to see drive health, connect a new drive, disconnect a drive, move a drive between the main and backup pools, recover after an unplug, and replace a dead drive. |
| `sudo hdd-recover` | Run it after an unplug or a power cut. It finds the containers that use the storage, stops them, remounts every drive and pool, re-applies the power settings and starts the containers again. |
| `sudo homelab-backup` | Copies the main pool and the boot drive's config files to the backup. It runs by itself from `cron` at 6:00 every day. |
| `homelab` | Prints a cheat sheet of these commands, a few **Suggested Commands** based on what needs attention now, and a live status (pools, last backup, containers, free space). It runs when a terminal opens ([step 14](#14-the-cheat-sheet-at-login)). Apart from `homelab theme` and `homelab bookmark`, which change only the Homepage files in your home folder, it only reads. |

**How the storage is organised**

- Every real drive is an ordinary ext4 drive, mounted by its UUID under `/mnt/disks/` with a label: `MAIN1`, `MAIN2`, `BACKUP1` and so on. Any Linux computer can read one of them on its own.
- A pool joins all the drives of one role into a single folder using **mergerfs**. `/mnt/storage` is the main pool and `/mnt/backup` is the backup pool. The paths in the Docker stacks (`/mnt/storage/...`) never change, so adding a drive needs no edits in Immich, Nextcloud, FileBrowser or Homepage.
- New files go to the drive with the most free space, so two drives fill evenly. Files already on a drive stay where they are.
- **A pool isn't RAID and it isn't a backup.** If a drive dies, only the files stored on that drive disappear from the pool. That is why the backup is a separate pool on separate drives.
- **It fails closed.** If a drive is missing, the pool doesn't mount at all, instead of mounting half-empty. The empty mount point is locked, so the services stop with an error and can't quietly write to the boot drive. After you reconnect the drive, `sudo hdd-recover` fixes it.

**Why ext4:** it's a Linux filesystem, so Docker and databases get proper file permissions, and it isn't locked as "dirty" when the drive is unplugged the way NTFS can be.

## 1. Install the tools

```bash
timedatectl | grep "Time zone"
uname -r
sudo apt update && sudo apt install -y mergerfs rsync parted hdparm smartmontools
mergerfs --version | head -1
```

The time zone should be yours, because the 6:00 backup runs on the server's clock. Kernel 6.6 or newer is best. On an older kernel the script switches one mergerfs cache option by itself. `mergerfs` prints its version (2.33.5 from Ubuntu 24.04's repository on my machine).

## 2. Install the scripts

The scripts are in the [`scripts/`](../scripts/) folder of this repository. The folder holds the commands `drives`, `homelab-backup`, `hdd-recover` and `homelab`, a few helpers (`homelab-sample`, `homelab-update`, `homelab-restore-configs` and `homelab-check`), and the example settings file `homelab-backup.conf.example`. (If you used the installer, these are already on the server. This part is for setting it up yourself.) Clone the repository on the server and install two of the commands now (`hdd-recover` comes in [step 8](#8-the-recovery-command) and `homelab` in [step 14](#14-the-cheat-sheet-at-login)):

```bash
sudo apt install -y git
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git ~/My-Home-Lab-
cd ~/My-Home-Lab-/scripts
sudo install -m 755 drives /usr/local/sbin/drives
sudo install -m 755 homelab-backup /usr/local/sbin/homelab-backup
sudo drives version
sudo drives status
```

`drives` is version 1.2 (1.1 added `drives replace`, see [step 15](#15-replace-a-dead-drive)).

If you copy the files from a Windows PC instead, run `grep -c $'\r' drives hdd-recover homelab-backup homelab` as well. All four numbers must be `0`, because Windows line endings stop a script from running.

Every `install` command here has to run **inside** the `scripts` folder, because it names the files without a path. If `install` answers `cannot stat 'homelab'` (or another file name), you are in the wrong folder. Run `cd ~/My-Home-Lab-/scripts` and repeat the command.

On a server with no pools yet, `status` looks like this:

```text
=== Pools ===
main     /mnt/storage   NOT MOUNTED
backup   /mnt/backup    NOT MOUNTED

=== Pool drives ===
LABEL     ROLE     DEVICE       SIZE      USED      SMART     STATE
(no drives in a pool yet)

=== Other drives ===
/dev/sdb  698.6G  Hitachi HTS547575A9E384  [sata]   boot/system drive (never touched)

=== Last backup ===
no backup has run yet
```

> **Your user name.** The scripts look up the user name themselves: `drives` uses the user who ran `sudo` (the owner of a new main drive), and `homelab-backup` uses the first normal user (the owner of the folders it copies). If your account is different, run `sudo DRIVES_OWNER=your-username drives`, set `HOMELAB_USER=your-username` in `/etc/homelab-backup.conf`, and put your own `CONFIG_PATHS` list there ([step 9](#9-the-daily-backup)). The settings file is read after the defaults, so it overrides them.

## 3. Practice with fake drives

Test mode uses disk-image files and its own folders (`/mnt/test-main`, `/mnt/test-backup`, `/mnt/test-disks`) and its own test `fstab`. Your real drives, `/etc/fstab` and containers aren't touched, so you can learn the menu safely.

```bash
sudo DRIVES_TEST=1 drives test-setup 3 1G
sudo DRIVES_TEST=1 drives
```

`test-setup 3 1G` creates three 1 GB image files and attaches them as fake drives. In the menu:

1. Choose **2** (Connect a new drive), pick the first fake drive and choose **Main storage**. The script asks you to type the drive name, then `ERASE`. Nothing is erased until both match.
2. Connect a second fake drive as **Main storage** and a third as **Backup storage**.
3. Choose **1** to see the status: two main drives and one backup drive.
4. Choose **3** and try to remove a drive. With two main drives, it offers to copy that drive's files to the other one first, then checks that every file arrived before it lets go of the drive. With only one main drive, it refuses: removing the last one would take the storage away from your services.
5. Choose **0** to quit, then remove the test setup:

```bash
sudo DRIVES_TEST=1 drives test-cleanup
sudo drives status
```

**Don't skip `test-cleanup`.** If you do, the practice pool stays mounted. The last command should look exactly like it did in [step 2](#2-install-the-scripts).

Here's what a good result looks like. I put two 200 MB files of random data in a practice pool of two fake drives (one file landed on each). I disconnected `TMAIN1`, which held one of them, and chose to copy its files first. The script printed `Verified: every file from TMAIN1 is also on TMAIN2.`, and `sha256sum` gave identical checksums for both files before and after.

You can repeat the practice with a real, spare USB stick (**it will be erased**). Test mode lists only unused drives, and the boot drive and your data drive never appear in the list.

## 4. Add the first main drive

There are two cases. Use the first for a new or blank drive, and the second if you already have an ext4 data drive mounted at `/mnt/storage`, as I did.

**A. A new drive.** Connect it and open the menu:

```bash
lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS
sudo drives
```

Choose **2** (Connect a new drive), pick the drive, check the size and model on screen, choose **Main storage**, then type the drive name and `ERASE`. **This erases the whole drive.** The script then:

1. wipes the drive and creates one GPT partition, formatted as ext4 with the label `MAIN1` and no 5% reserve (`mkfs.ext4 -m 0`);
2. creates `/mnt/disks/MAIN1` and `/mnt/storage`, and locks both empty folders with `chattr +i`, so nothing can write into them while no drive is mounted;
3. saves a copy of `/etc/fstab` (as `/etc/fstab.bak-drives-<date>`) and adds the lines below;
4. mounts the drive, mounts the pool, gives your user the top folder of the new drive and applies the power settings ([step 7](#7-drive-power-settings)).

If the pool doesn't mount, the script restores `/etc/fstab` by itself and says so.

**B. A drive that is already mounted at `/mnt/storage`.** This keeps every file in place:

```bash
sudo drives adopt
```

The script shows what will change and asks `Continue? [y/N]`. Answer `y`. It stops the containers that use the storage, unmounts the drive, relabels it `MAIN1`, mounts it at `/mnt/disks/MAIN1`, builds the pool at `/mnt/storage` and starts the containers again. No file is moved or copied. If the pool shows a different number of items than the drive did, it rolls everything back.

**The `/etc/fstab` lines it writes** (the UUID is your drive's own):

```text
UUID=<uuid-of-the-drive>  /mnt/disks/MAIN1  ext4  defaults,noatime,nofail,x-systemd.device-timeout=10  0  2
/mnt/disks/MAIN1 /mnt/storage fuse.mergerfs allow_other,cache.files=off,category.create=mfs,moveonenospc=true,dropcacheonclose=true,nofail,fsname=mergerfs-main,x-systemd.requires-mounts-for=/mnt/disks/MAIN1 0 0
```

| Pool option | Meaning |
| :--- | :--- |
| `allow_other` | Docker and the other users on the server can use the pool, not only root. |
| `cache.files=off` | No kernel file cache, so containers see changes straight away. (Kernels older than 6.6 use `auto-full` instead.) |
| `category.create=mfs` | New files go to the drive with the most free space. |
| `moveonenospc=true` | If a drive fills up while a file is being written, the file moves to a drive with room. |
| `dropcacheonclose=true` | Frees cached data when a file is closed. |
| `nofail` | The server still boots if the pool can't mount. |
| `fsname=mergerfs-main` | The name that `df` and `findmnt` show for the pool. |
| `x-systemd.requires-mounts-for=...` | One entry per drive. `systemd` mounts the pool only after all its drives are mounted. |

The type must be `fuse.mergerfs`, not `mergerfs`. In my testing, the plain `mergerfs` type rejected the `nofail` option.

**Check it worked.** Run the two `findmnt` commands one at a time, because `findmnt` prints nothing when it gets two paths:

```bash
findmnt /mnt/storage
findmnt /mnt/disks/MAIN1
sudo drives status
```

`/mnt/storage` should show the source `mergerfs-main` with the type `fuse.mergerfs`, and `/mnt/disks/MAIN1` should show your drive (`/dev/sda1` on my machine) as `ext4`. `status` should list `MAIN1` as `connected` with SMART `PASSED`:

```text
=== Pools ===
main     /mnt/storage   mounted (fuse.mergerfs)  61GB used of 916GB
backup   /mnt/backup    NOT MOUNTED

=== Pool drives ===
LABEL     ROLE     DEVICE       SIZE      USED      SMART     STATE
MAIN1     main     /dev/sda1    916GB     61GB      PASSED    connected
```

Once the services exist (sections 10 to 12 and 15), each container should see the pool, not the boot drive:

```bash
docker exec immich_server df -h /data
docker exec nextcloud df -h /data
docker exec filebrowser-filebrowser-1 df -h /srv/hdd
docker exec homepage df -h /mnt/storage
```

Every line should show the filesystem `mergerfs-main` at about 916G. On my machine the same four commands worked unchanged after the conversion, which shows the stacks didn't need any edit.

## 5. Create a folder for each service

```bash
sudo mkdir -p /mnt/storage/immich /mnt/storage/filebrowser
sudo chown -R your-username:your-username /mnt/storage
sudo mkdir -p /mnt/storage/nextcloud
sudo chown -R 33:33 /mnt/storage/nextcloud
mkdir -p /home/your-username/nextcloud/html /home/your-username/nextcloud/db
mkdir -p /home/your-username/immich/postgres
mkdir -p /home/your-username/homepage-config
mkdir -p /home/your-username/boot-drive-files
sudo mkdir -p /opt/adguard-docker/conf /opt/adguard-docker/work
```

UID 33 is the user Nextcloud runs as inside its container (it shows as `www-data` in `ls -la`). The databases and app files stay on the boot drive. Only the photos and files go in the pool.

| Folder | Used by | Where |
| :--- | :--- | :--- |
| `/mnt/storage/immich` | Immich photos and videos | Main pool |
| `/mnt/storage/nextcloud` | Nextcloud files | Main pool |
| `/mnt/storage/filebrowser` | FileBrowser share | Main pool |
| `/home/your-username/immich/postgres` | Immich database | Boot |
| `/home/your-username/nextcloud/db` and `html` | Nextcloud database and app files | Boot |
| `/home/your-username/boot-drive-files` | FileBrowser share on the boot drive | Boot |
| `/home/your-username/homepage-config` | Homepage config files | Boot |
| `/opt/adguard-docker` | AdGuard Home settings | Boot |

## 6. Make Docker wait for the pool

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
printf '[Unit]\nWants=mnt-storage.mount\nAfter=mnt-storage.mount\n' | sudo tee /etc/systemd/system/docker.service.d/wait-for-hdd.conf
sudo systemctl daemon-reload
```

`/mnt/storage` is still a mount point that `systemd` knows as `mnt-storage.mount`, now with the pool on it. So this file is the same one I used with a single drive, and it needs no change. (Docker is installed in [build guide, section 3](build-guide.md#3-docker). If it isn't installed yet, create this file after installing it.)

## 7. Drive power settings

Laptop-style drives park their heads aggressively at the default power setting, which wears them out when a server never sleeps. One command sets safer levels on every pool drive:

```bash
sudo drives power
```

- **Main drives:** `hdparm -B 254 -S 0`. The first value is the least aggressive head parking. The second means the drive never spins down, which suits drives that Immich and Nextcloud use all day.
- **Backup drives:** `hdparm -B 254 -S 120`. The same head setting, and the drive spins down after 10 minutes without use (`120 x 5 seconds`), since it is only busy once a day.

The settings reset at every reboot, so add these two lines to root's crontab. The first re-applies the settings to every pool drive 60 seconds after boot. The second sets the boot drive, which it finds by the partition mounted at `/boot/efi`:

```bash
sudo crontab -e
```

```cron
@reboot sleep 60 && /usr/local/sbin/drives power >/dev/null 2>&1
@reboot sleep 60 && /usr/sbin/hdparm -B 254 "/dev/$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)")"
```

Don't type a drive letter such as `/dev/sdb` into cron lines. If the letters swap after a reboot, the setting would land on the wrong drive. Both lines look the drive up instead.

Optional: log the head-parking count every morning so you can watch it:

```cron
0 6 * * * echo "$(date +\%F) $(smartctl -A -d sat /dev/disk/by-label/MAIN1 | awk '/Load_Cycle/ {print $10}')" >> /var/log/loadcycles.log
```

Check a drive (replace `sda` with its letter from `lsblk`):

```bash
sudo hdparm -B /dev/sda
sudo hdparm -C /dev/sda
```

The first should print `APM_level = 254`. The second prints the drive state, which is `active/idle` for a main drive. Some USB adapters ignore these commands and print `SG_IO: bad/missing sense data`. That message is harmless. The backup drives' sleep setting is the one part I haven't been able to test yet, because I don't have a backup drive. After you add one, wait 15 idle minutes and run `sudo hdparm -C` on it. It should say `standby`.

## 8. The recovery command

Containers keep the view of the drive they had when they started. If a drive is unplugged and plugged back in, the containers need a restart. `hdd-recover` is a one-line command that calls `drives recover`, which does the whole job:

```bash
cd ~/My-Home-Lab-/scripts
sudo install -m 755 hdd-recover /usr/local/bin/hdd-recover
sudo hdd-recover
```

It looks at what each container has mounted under `/mnt/storage`, `/mnt/backup` and `/mnt/disks`. That means a new service that uses the pool is picked up automatically, with no list of container names to maintain. Then it stops those containers, unmounts the pools and drives, mounts them again from `/etc/fstab`, re-applies the power settings and starts the containers. On my server it printed:

```text
Stopping containers that use this storage: filebrowser-filebrowser-1 homepage immich_server nextcloud nextcloud_cron
Starting containers: filebrowser-filebrowser-1 homepage immich_server nextcloud nextcloud_cron
Recovered.
```

If a main drive isn't found, it prints `Drive not found. Check the cable.` with the drive's label and leaves the containers stopped on purpose, so nothing writes to the wrong place. A missing backup drive only produces a warning.

## 9. The daily backup

`homelab-backup` runs these steps in order:

1. dumps the Nextcloud database (the database lives on the boot drive, so a copy of the pool alone wouldn't contain it);
2. copies the main pool to the backup with `rsync`. A file you delete or replace is moved into a dated folder, `_deleted/<date>/`, and not destroyed;
3. copies the boot drive's config files: the Homepage config, the Nextcloud app files, AdGuard Home's settings, the Portainer, Beszel and FileBrowser data, `/etc/fstab`, the Docker wait file, the `drives`, `hdd-recover` and `homelab-backup` scripts and root's crontab, plus any extra folders you add (see below);
4. removes dumps and `_deleted` folders older than 30 days.

Immich also writes its own database backups into `/mnt/storage/immich/backups`, so they are included in the copy of the pool.

**Where it writes.** The target is the backup pool, `/mnt/backup`. Until you have a backup drive, point it at a folder on the boot drive. That protects you if the data drive fails, but not if the boot drive fails or the machine is lost. Create the settings file:

```bash
sudo tee /etc/homelab-backup.conf >/dev/null <<'EOF'
DEST_FALLBACK="/home/your-username/boot-drive-files/backup-interim"
EOF
cat /etc/homelab-backup.conf
```

Check there is room first (`df -h / /mnt/storage`). The first backup needs about as much space as the pool uses. Then run the first one in the background and watch the log (press `Ctrl+C` to stop watching; the backup keeps running):

```bash
sudo nohup /usr/local/sbin/homelab-backup >/dev/null 2>&1 &
sudo tail -f /var/log/homelab-backup.log
```

My first run copied 61 GB over the USB adapter in 1420 seconds (about 24 minutes) and ended with these lines:

```text
2026-10-22 19:04:46 start
2026-10-22 19:04:46 backup pool not mounted, using the fallback folder /home/your-username/boot-drive-files/backup-interim
2026-10-22 19:04:53 database dump saved: /home/your-username/boot-drive-files/backup-interim/db-dumps/nextcloud-2026-10-22.sql.gz
2026-10-22 19:27:04 main storage copied
2026-10-22 19:28:26 configs copied
2026-10-22 19:28:26 finished: OK in 1420s
```

To check whether it is still running, use `pgrep -af homelab-backup`. The `f` matters, because the script runs under the name `bash`. When the log says `finished: OK`, check the result and compare the sizes:

```bash
sudo drives status
sudo du -sh /mnt/storage /home/your-username/boot-drive-files/backup-interim/main
```

The status should show `result: OK` with the destination, and the two sizes should be close (mine were both 61G). Then schedule it for 6:00 every day:

```bash
sudo crontab -e
```

```cron
0 6 * * * /usr/local/sbin/homelab-backup
```

**What the backup folder contains**

| Folder | What is in it |
| :--- | :--- |
| `main/` | A copy of the main pool |
| `boot-configs/` | The boot drive's config files listed above, plus `root-crontab.txt` |
| `db-dumps/` | One Nextcloud database dump per day (30 days kept) |
| `_deleted/<date>/` | Files you deleted or replaced that day (30 days kept, then removed) |

**Safety rules built in.** The backup refuses to run, and logs why, if main storage isn't mounted, if main storage looks empty (so a missing drive can never empty the backup), if the backup target isn't mounted and no fallback is set, or if the target has too little free space (less than 20 GB, or less than the pool's size plus 20 GB for the first run). `drives status` shows the result of the last run, and the log is `/var/log/homelab-backup.log`.

**Backing up another folder.** The list of boot-drive folders is `CONFIG_PATHS` at the top of `homelab-backup`. Don't edit the script. Add to the list from the settings file instead, which is read after the defaults. For example, Speedtest Tracker keeps its database in `/home/your-username/speedtest-tracker` ([build guide, section 13](build-guide.md#13-speedtest-tracker)), and the default list doesn't include it:

```bash
echo 'CONFIG_PATHS+=(/home/your-username/speedtest-tracker)' | sudo tee -a /etc/homelab-backup.conf
cat /etc/homelab-backup.conf
```

Use `+=`, which adds to the list. A plain `=` would replace the list, and the backup would stop copying everything else. A folder that doesn't exist is skipped, with a line in the log. After the next backup, the folder appears under `boot-configs/`, with its full path:

```bash
sudo ls /home/your-username/boot-drive-files/backup-interim/boot-configs/home/your-username/
```

**Restore a file or folder.** Copy it out of the backup, and don't edit it there, because the next backup overwrites a changed file. Replace the backup path with your fallback folder while you still use one:

```bash
ls /mnt/backup/_deleted/
sudo cp -a /mnt/backup/_deleted/2026-10-22/main/immich/some-file.jpg /mnt/storage/immich/
sudo cp -a /mnt/backup/main/nextcloud/some-folder /mnt/storage/nextcloud/
```

The first line lists one folder per day. The second restores something you deleted or replaced that day. The third restores a file that is still in the latest copy. If you restore Nextcloud files this way, run `docker exec -u www-data nextcloud php occ files:scan --all` afterwards so Nextcloud notices them.

## 10. Verify the storage setup

Run the four `docker exec ... df` checks from [step 4](#4-add-the-first-main-drive). Then run two tests:

- **Reboot:** run `sudo reboot`. After about three minutes, run these one at a time. The pool and the drive should be mounted and the containers up without any help from you:

```bash
findmnt /mnt/storage
findmnt /mnt/disks/MAIN1
docker ps --format "table {{.Names}}\t{{.Status}}"
sudo drives status
```

- **Unplug:** with the stacks running, unplug the drive for ten seconds, plug it in, and run `sudo hdd-recover`. You should see `Recovered.` I tested this with fake drives, including the cases of a missing drive and a drive plugged back in. I haven't repeated it on my real drive since converting it to a pool, so treat your first run as the real test.

> The weekly health check for the drives is in [Maintenance and recovery](maintenance.md#maintenance-and-recovery).

## 11. Everyday use

| What you want | Command |
| :--- | :--- |
| See pools, drives, SMART health and the last backup | `sudo drives status` |
| Connect, disconnect or move a drive | `sudo drives` |
| After an unplug or a power cut | `sudo hdd-recover` |
| A drive died and you have a new one | `sudo drives replace` ([step 15](#15-replace-a-dead-drive)) |
| Copy back only the missing files from the backup | `sudo drives restore` ([step 15](#15-replace-a-dead-drive)) |
| Run the backup now | `sudo homelab-backup` |
| Read the backup log | `sudo tail -50 /var/log/homelab-backup.log` |
| Read the drives log | `sudo tail -50 /var/log/scripts.log` |
| See the commands and the status again | `homelab` |
| List the sections of the README and the guides | `homelab docs` |

**Before you unplug a drive on purpose,** open `sudo drives` and choose **3** (Disconnect a drive), then unplug when it says it's safe. Don't just pull the cable.

**Adding a second main drive:** choose **2** and **Main storage**. The new drive is labelled `MAIN2`. New files go to whichever drive has more free space, and existing files stay where they are.

**Moving a drive between the pools:** choose **4**. The script offers to copy the drive's files to another drive of the same pool and verifies them. Then it erases the drive (after the same device-name and `ERASE` checks) and adds it to the other pool.

What the script refuses or double-checks:

- The boot drive and anything with a filesystem mounted outside the desktop's `/media` folder are never offered and never erased.
- Erasing needs the exact device name and then the word `ERASE`.
- It won't remove the last main drive. Removing the last backup drive needs the word `REMOVE`.
- Before removing a drive that holds files, it offers to copy them to another drive of the same pool first, and it checks that every file arrived.
- Before every change it saves a copy of `/etc/fstab`, and it puts that copy back if a mount fails. If something goes wrong half way, the containers it stopped stay stopped, and it tells you to run `sudo hdd-recover`.

## 12. Adding the backup drive

I haven't done this on my own server yet, because I don't have the drive. I tested it with fake drives and a USB stick. Connect the drive, then:

```bash
sudo drives
```

Choose **2** (Connect a new drive), pick the drive and choose **Backup storage**. It becomes `BACKUP1`, mounted at `/mnt/disks/BACKUP1`, and `/mnt/backup` becomes the backup pool. A second backup drive becomes `BACKUP2` and joins the same pool.

Then delete the `DEST_FALLBACK` line from `/etc/homelab-backup.conf` and run `sudo homelab-backup`. `sudo drives status` should now show the destination `/mnt/backup`. After one good run on the new drive, free the space on the boot drive by deleting the interim folder (`sudo rm -rf /home/your-username/boot-drive-files/backup-interim`). Check the path before you press Enter.

To browse the backup from FileBrowser on a machine set up with the installer, nothing needs adding: run `sudo homelab-setup filebrowser` (it also runs by itself after `sudo drives` connects or disconnects a drive) and the backup drive appears as a folder inside `backup-storage`. On the original server, add `- /mnt/backup:/srv/backup` to the volumes in the stack by hand. The container name stays the same, so `hdd-recover` finds it by itself.

**FileBrowser folders and drive names.** On an installer-built machine FileBrowser shows one folder per drive: the system drive, then `main-storage/<drive>` and `backup-storage/<drive>`. A folder shows the whole drive. The installer scans each drive and names the folder after its size, brand and type, for example `1 TB Toshiba HDD` or `250 GB Samsung SSD`. The size comes from the drive itself, the brand is picked out of its model name, and HDD or SSD comes from whether the drive spins. If it can't recognise the brand it uses the model text instead (`1 TB ST1000DM010`), and if two drives end up with the same name the mount name is added in brackets (`1 TB Toshiba HDD (MAIN2)`). Some USB adapters hide what kind of drive is inside, so the HDD or SSD part may be missing. The drive labels `MAIN1` and `BACKUP1` don't change, only the folder names in FileBrowser. To choose your own, create `/etc/homelab-drive-names` with one `LABEL=Name` per line (for example `MAIN1=Photos drive`, and `boot=My Mint` for the system drive), then run `sudo homelab-setup filebrowser`. A file saved straight into a drive's folder skips the pool's copy rules and sits on that one drive only, so put new files in the pool paths the apps use unless you mean it.

## 13. When a drive goes missing

- **A main drive is unplugged or dead:** the main pool doesn't mount, the empty locked `/mnt/storage` makes Immich, Nextcloud and FileBrowser fail with errors, and `sudo drives status` shows the drive as `MISSING`. Reconnect it and run `sudo hdd-recover`. I tested this with fake drives, not on my real hardware.
- **A backup drive is missing:** the main pool and the services aren't affected, and the backup run fails and says why. `drives status` shows `FAILED` in the last-backup line.
- **A drive is gone for good:** the files that were stored on it are in the backup, up to a day old. `sudo drives replace` swaps in a new drive and copies back only the files that are missing ([step 15](#15-replace-a-dead-drive)). I have tested it with fake drives and rehearsed it once on my server with a USB stick, but not yet on a real failed drive. Rehearse it first.

## 14. The cheat sheet at login

`homelab` is a small script. It prints the commands from this section (and, when the installer is present, its setup commands such as `sudo homelab-setup refresh`), grouped by job, a short **Suggested Commands** list (what is worth running now: a setup step that is waiting, an old backup, updates, and so on) and a live status block. I run it from `~/.bashrc`, so every new terminal shows it, both in a plain SSH session and in the terminal of VS Code Remote-SSH. Showing the cheat sheet never changes anything and needs no `sudo`. The only commands in it that change files are `homelab theme` and `homelab bookmark`, which edit the Homepage dashboard's own files ([build guide, section 14.5](build-guide.md#145-change-the-look-and-add-bookmarks)). `HOMELAB_SUGGEST_MAX` sets how many suggestions are shown (default 4).

**1. Install it.** Run this on the server. Like in [step 2](#2-install-the-scripts), the commands must run inside the `scripts` folder:

```bash
cd ~/My-Home-Lab-/scripts
sudo install -m 755 homelab /usr/local/bin/homelab
homelab version
```

`homelab version` prints the installed version (for example `homelab 1.8`). Then run `homelab` once by hand. Mine printed this (the host name is replaced here, and the paths with `your-username`):

```text
Home lab  your-server  up 51 minutes

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

On a terminal that supports colour, a good line is green, a warning is yellow and a problem is red. What each status line means:

| Line | Meaning |
| :--- | :--- |
| Main pool | Green when `/mnt/storage` is mounted. Red with `NOT MOUNTED` when it isn't: plug the drive in and run `sudo hdd-recover`. |
| Backup pool | Yellow with `not connected` until a backup drive exists. That is normal for now. |
| Last backup | Green when the last run was `OK` and less than 36 hours old. Yellow when it is older. Red when the last run failed, with the command that shows why. |
| Containers | The number running out of the number that should run. A container that was stopped on purpose (restart policy `no`) isn't counted. Red lists the ones that are down. |
| Boot drive | Space used and free on `/`. |

**2. Show it at login.** Make a copy of `~/.bashrc` first, then add a short block at the end. The `'EOF'` in quotes matters: it stops the shell from changing the text while it is written.

```bash
cp ~/.bashrc ~/.bashrc.bak
cat >> ~/.bashrc <<'EOF'

# >>> homelab login display >>>
if [[ $- == *i* ]] && [ -t 1 ] && command -v homelab >/dev/null 2>&1; then
  timeout 20 homelab
fi
# <<< homelab login display <<<
EOF
tail -8 ~/.bashrc
```

The `if` has three conditions. `$- == *i*` means an interactive shell, `-t 1` means the output goes to a terminal and not to a file or a pipe, and `command -v homelab` means the command exists. Because of them, `scp`, `sftp`, cron jobs and the shell that VS Code starts in the background to read your environment print nothing extra. The `timeout 20` in front of `homelab` is a safety net: if Docker or a drive hangs, the cheat sheet gives up after 20 seconds and your prompt still appears.

**3. Test it.** Open a new terminal in each place you use and check that the cheat sheet appears:

1. In VS Code, open **Terminal**, then **New Terminal**.
2. From the Windows PC, open a new PowerShell window and connect with `ssh your-username@192.168.X.X`.
3. To confirm that scripts aren't disturbed, run this from the Windows PC. It should print only the word `ok`:

```powershell
ssh your-username@192.168.X.X "echo ok"
```

**Don't** keep a variable such as `export HOMELAB_SHOWN=1` to show the sheet only once. VS Code reads your environment by starting a shell, so the exported variable ends up in every VS Code terminal and the sheet never appears there. The `if` above needs no variable. See [H5 in the troubleshooting guide](troubleshooting.md#h5-the-cheat-sheet-does-not-appear-in-the-vs-code-terminal).

**4. Open the documents from the terminal.** `homelab docs` lists the `##` headings of the README and of every guide in `docs/`, with their line numbers, read from the clone you made in [step 2](#2-install-the-scripts):

```bash
homelab docs
less +LINE ~/My-Home-Lab-/docs/build-guide.md
git -C ~/My-Home-Lab- pull
```

The second command opens a guide at a line from that list (replace `LINE` with the number and the file name with the one `homelab docs` shows, and press `q` to leave). The third refreshes the clone from GitHub. If the clone is missing, `homelab docs` prints the `git clone` command to run.

**5. Update it later.** After a `git pull` that changes the script, repeat the `install` line from step 1.

**Undo.** Remove the block, or put the old file back (only if you changed nothing else in `~/.bashrc` since):

```bash
sed -i '/# >>> homelab login display >>>/,/# <<< homelab login display <<</d' ~/.bashrc
```

```bash
cp ~/.bashrc.bak ~/.bashrc
```

Settings, for the rare case you need them, are environment variables: `HOMELAB_MAIN_POOL`, `HOMELAB_BACKUP_POOL`, `HOMELAB_LAST_RUN_FILE`, `HOMELAB_DOCS_DIR` and `HOMELAB_STALE_HOURS` (the age in hours after which a backup shows yellow, 36 by default).

## 15. Replace a dead drive

Use this when a pool drive is gone for good: it won't spin up, it isn't found any more, and `sudo hdd-recover` can't bring it back. The command is `sudo drives replace` (or choose **8** in the `sudo drives` menu). It needs two things: a **new drive** (it will be erased) and a **backup copy** (the daily backup, [step 9](#9-the-daily-backup)).

> **Tested with fake drives and one USB-stick rehearsal.** I ran 58 automatic checks on practice drives (one drive dying, one of two dying, refusing to continue, a dead backup drive, two dead drives). I also rehearsed it on my server: one of two practice drives "died", a real 8 GB USB stick took its place, the 2 missing files (100 MB) came back, and their SHA-256 checksums matched the ones I saved before. I haven't yet used it on a real failed drive. Do the rehearsal at the end of this section once before you depend on it. Version 1.1 of `drives` is the first one that has this command: `sudo drives version` should print `drives 1.1`.

**What it does, in order**

1. Finds the pool drives that can't be found, and asks which one is dead. If none is missing, it says so and stops. (A drive that was only unplugged needs `sudo hdd-recover`, not this.)
2. For a main drive, finds the backup copy and shows its date and result. It stops if there is no backup. Nothing has been changed so far.
3. Asks you to pick the new drive, and to type its name and `ERASE`. Nothing is erased before both match, and the boot drive and your working pool drives are never offered.
4. Stops the containers that use the storage, formats the new drive with **the same label as the dead one** (for example `MAIN1`), swaps the line in `/etc/fstab` (the old line stays in the file as a comment) and mounts the pool again.
5. For a main drive: compares the backup with the pool and shows a **preview** with the number of missing files, their total size and the first 20 names. Nothing is copied until you type `RESTORE`.
6. Copies only the missing files. Files that are already in the pool are never overwritten.
7. Checks that every file in the backup is now in the pool. **Only if that check passes, the containers start again.** If anything fails, they stay stopped and the tool tells you what to run next.

**Step by step**

1. See what is wrong, and make sure it isn't just a cable:

   ```bash
   homelab
   sudo drives status
   ```

   The dead drive shows as `MISSING` in the status. Check the cable and the power of the adapter, plug it in again and run `sudo hdd-recover`. Only go on if the drive is really dead.

2. Look at the last backup. It should say `OK`, with a recent date:

   ```bash
   sudo drives status
   ```

   The files that were created after that backup aren't in it and can't come back.

3. Plug in the new drive. Check that the system sees it, and note the device name:

   ```bash
   lsblk -o NAME,SIZE,MODEL,TRAN
   ```

4. Run the command and follow the questions:

   ```bash
   sudo drives replace
   ```

   Here's the middle of a run from my practice drives (practice labels start with a `T`, so the dead drive is `TMAIN1`; on the real server it is `MAIN1`):

   ```text
   Pool drives that cannot be found:
     1) TMAIN1  (main)  not found
   Which drive is dead? 1

   TMAIN1 will be replaced by a new drive that gets the same name (TMAIN1).
   Backup copy to restore from: /path/to/backup/main
   Last backup run: 2026-10-23 06:00  result: OK  destination: /path/to/backup
   ...
   !! ERASE WARNING !!
   Everything on /dev/loop1 will be permanently deleted.
   Type the drive name exactly (/dev/loop1) to continue: /dev/loop1
   Type ERASE (capitals) to confirm: ERASE
   Stopping containers that use this storage: immich_server nextcloud

   TMAIN1 is in place and the main pool is mounted.

   Missing from the pool but present in the backup: 23 files, 31MB
   First 20:
     immich/photo-1.jpg
     ...
   What this will and will not do:
     - Files that are already in the pool are never overwritten.
     - Files you deleted since the last backup come back too (the backup still has them).
     - Files created or changed since the last backup are not in the backup, so they cannot come back.
   Type RESTORE (capitals) to copy these 23 files: RESTORE
   ...
   Verified: all 23 restored files, and every other file in the backup, are in the pool.
   Starting containers: immich_server nextcloud
   ```

5. When it finishes, check the services in Immich, Nextcloud and FileBrowser. If you restored Nextcloud files, tell Nextcloud about them, then run a fresh backup:

   ```bash
   docker exec -u www-data nextcloud php occ files:scan --all
   sudo homelab-backup
   ```

**If you type something other than `RESTORE`,** nothing is copied and the containers stay stopped. Come back to it later with `sudo drives restore`. It does the preview, the question, the copy and the check again, and then starts the containers. It's safe to run several times: once everything is back it says `Nothing is missing`.

**If two main drives are dead,** replace them one at a time. After the first one, the pool can't start until the second is replaced too, so the tool tells you to run `sudo drives replace` again. The files are restored after the last one.

**If the dead drive is a backup drive,** there is nothing to restore. The new drive gets the same label (`BACKUP1`) and starts empty, and the tool offers to run the backup now. The older versions of deleted files (`_deleted/`) that were on the dead drive are gone.

**What it can't do**

- It can't bring back files that were created after the last backup and lived on the dead drive. A file that was changed after the last backup comes back in its older, backed-up version.
- It also brings back files you deleted after the last backup, because they are still in the backup.
- If the drive is still connected but failing (SMART says `FAILED`, but it still mounts), don't use this. Copy the files off it first with option **3** (Disconnect a drive).
- If the old drive ever turns up again, don't plug it in next to the new one, because both are called `MAIN1`.
- Until a backup drive exists, the backup is a folder on the boot drive ([step 9](#9-the-daily-backup)). `replace` finds it by itself from the record of the last run.

**Rehearse it with a USB stick (it will be erased).** Do this once, while nothing is broken, so you know what the screens look like before you need them. It takes about 15 minutes. It uses test mode, so your real pools, `/etc/fstab` and containers aren't touched: test mode has its own folders (`/mnt/test-main`, `/mnt/test-disks`) and its own test `fstab`. You need one spare USB stick of 2 GB or more. Everything on it is erased.

The idea: make two fake drives, put three files on them, pretend one fake drive died, and let a real USB stick take its place. Then check that the files came back unchanged. Run one command at a time in the terminal on the server, and check each result before going on.

**Step 1: Make two fake drives. Don't plug in the USB stick yet.** If the stick is already in, the connect menu in Step 2 would list it too, and you could pick it by mistake.

```bash
sudo DRIVES_TEST=1 drives test-setup 2 1G
```

You should see two lines like `/dev/loop0 /var/tmp/scripts-test/disk1.img` and `/dev/loop1 ... disk2.img`. Those are two 1 GB image files acting as drives.

**Step 2: Connect both fake drives as Main storage.** Run this twice, one drive each time.

```bash
sudo DRIVES_TEST=1 drives connect
```

1. Choose the drive in the list. Only the fake ones (`loop0`, `loop1`) should be there. Your real drives are never listed.
2. Choose **Main storage**.
3. Type the drive name exactly as shown (for example `/dev/loop0`), then type `ERASE`. This only erases the fake image file.

Each run ends with `Done. TMAIN1 is connected to the main storage` (then `TMAIN2` the second time). Check the result:

```bash
sudo DRIVES_TEST=1 drives status
```

You should see two main drives, `TMAIN1` and `TMAIN2`, both `connected`, and the practice pool `/mnt/test-main` mounted with about 1.9 GB. In test mode, the "Other drives" part may list your real data drive as "not connected to a pool". That is only because test mode knows nothing about your real pool. Your real pool isn't affected.

**Step 3: Put practice files in the practice pool, and make a practice backup.** This writes 150 MB of random data into the fake pool only.

```bash
sudo mkdir -p /mnt/test-main/photos
for i in 1 2 3; do sudo sh -c "head -c 50M /dev/urandom > /mnt/test-main/photos/file$i.bin"; done
sudo mkdir -p /var/tmp/practice-backup/main
sudo rsync -a /mnt/test-main/ /var/tmp/practice-backup/main/
(cd /mnt/test-main && sha256sum photos/*.bin) | tee ~/practice-sums.txt
ls -la /mnt/test-disks/TMAIN1/photos /mnt/test-disks/TMAIN2/photos
```

You should see three `sha256sum` lines, which are the fingerprints of the files before the "crash". The `ls` shows which fake drive holds which file. The pool puts new files on the drive with the most free space, so in my run `TMAIN1` held `file1.bin` and `TMAIN2` held `file2.bin` and `file3.bin`. The next steps use `TMAIN2` as the drive that dies. If your split is different, use the drive that holds at least one file, and swap the names (and `disk2.img`) below.

**Step 4: Pretend `TMAIN2` died.** This unmounts the pool and takes the fake drive away.

```bash
sudo umount -l /mnt/test-main
sudo umount -l /mnt/test-disks/TMAIN2
sudo losetup -d "$(losetup -j /var/tmp/scripts-test/disk2.img | cut -d: -f1)"
sudo DRIVES_TEST=1 drives status
```

You should see `TMAIN2` as `MISSING (cable? then: sudo hdd-recover. Dead? sudo drives replace)` and the practice main pool as `NOT MOUNTED`. The pool refuses to mount with a drive missing, which is on purpose: a half-empty pool would look healthy while it hid files.

**Step 5: Plug in the USB stick and find it.** This only reads; nothing is erased yet.

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINTS,TRAN
sudo dmesg | tail -15
```

The stick is the new line with `usb` in the last column and a size that matches the stick (an 8 GB stick shows about 7.2G), usually `sdc`. `dmesg` should mention a new USB device. Your real data drive (also `usb`, hundreds of GB) and your boot drive are much bigger, so they are easy to tell apart. If the stick has an old label, or the desktop mounted it under `/media/...`, that is fine: the tool unmounts it before it erases it. If the stick doesn't show up, wait 10 seconds, try another USB port and run the two commands again.

**Step 6: Run the replace with the stick as the new drive.** `DRIVES_RESTORE_SRC` tells the tool where the practice backup is, because there is no real backup record in test mode.

```bash
sudo DRIVES_TEST=1 DRIVES_RESTORE_SRC=/var/tmp/practice-backup drives replace
```

Answer the questions as they come:

1. **Which drive is dead?** Choose `TMAIN2`.
2. **WARNING: There is no record of a backup run. Use this copy anyway? [y/N]:** type `y`. This is your hand-made practice backup, so the warning is expected.
3. **Which drive do you want to connect?** Choose the stick. It must be the only real drive in the list. If your data drive or boot drive is listed, press `0` and stop.
4. **Type the drive name exactly:** type the stick's name (for example `/dev/sdc`), then type `ERASE`.
5. The tool formats the stick, names it `TMAIN2`, mounts it and rebuilds the pool. Then it prints a preview: `Missing from the pool but present in the backup: 2 files, 100MB`, followed by the names (`photos/file2.bin` and `photos/file3.bin`). Check that these are the files that were on the dead drive.
6. **Type RESTORE (capitals) to copy these 2 files:** type `RESTORE`.

It copies the files and then checks them: `Verified: all 2 restored files, and every other file in the backup, are in the pool.` It ends with `Done.` and a reminder not to plug the old drive in next to the new one, because both are called `TMAIN2`.

**Step 7: Check the files yourself.** The script's own check says the files are there; this check says they are unchanged.

```bash
(cd /mnt/test-main && sha256sum -c ~/practice-sums.txt)
sudo DRIVES_TEST=1 drives status
ls -la /mnt/test-disks/TMAIN2/photos
```

All three `sha256sum` lines must end in `OK`. The status should show `TMAIN1` and `TMAIN2` both `connected`, with `TMAIN2` now on the stick (about 7 GB), and the pool mounted with about 151 MB used. The `ls` shows `file2.bin` and `file3.bin` on the stick.

**Step 8: Clean up, and check your real system is as it was.**

```bash
sudo DRIVES_TEST=1 drives test-cleanup
sudo rm -rf /var/tmp/practice-backup ~/practice-sums.txt
sudo drives status
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS,TRAN
docker ps --format "table {{.Names}}\t{{.Status}}"
```

You should see `Test setup removed.`, then your real `drives status` looking exactly as before the practice (your data drive connected, the same amount used). In `lsblk` there is no `loop0` and nothing is mounted under `/mnt/test-*`. The stick may still show the label `TMAIN2` with no mount point; cleanup doesn't wipe it. All your containers are still running. Now you can unplug the stick. It still holds the practice files, so wipe it before you use it for anything else.

**Don't skip Step 8.** If you do, the practice pool stays mounted. If a step goes wrong and you want to stop, run the first two commands of Step 8. They remove the practice setup whatever state it is in.
