# Maintenance and recovery

Routine checks, what to do after a power cut, and the plan for rebuilding the server when the boot drive dies. The commands assume the storage tools from the [storage guide](storage.md) are installed (the installer does this).

## Quick health check

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
df -h / /mnt/storage
free -h
uptime
sudo drives status
```

Every container should be `Up` or `healthy`, neither the boot drive nor the pool should be near full, and the load average should be low when the machine is idle. `drives status` lists every pool drive with its SMART health and shows the result of the last backup. After 6:00 it should say `result: OK` with today's date.

The short version of this check is the status block that `homelab` prints whenever you open a terminal ([storage guide, step 14](storage.md#14-the-cheat-sheet-at-login)). Green lines are fine. Yellow or red lines tell you what to look at.

## Drive health

`sudo drives status` shows `PASSED` or `FAILED` for each pool drive. For the details, read the SMART numbers:

```bash
sudo smartctl -H -A /dev/sdb | grep -E "overall-health|Reallocated_Sector|Current_Pending|Load_Cycle"
sudo smartctl -H -A -d sat /dev/disk/by-label/MAIN1 | grep -E "overall-health|Reallocated_Sector|Current_Pending|Load_Cycle"
```

The first line is the boot drive (`sdb` on my machine). Check the letters with `lsblk` first, because they can swap after a reboot. The second line finds the first main drive by its label, so it always reads the right drive. Use `MAIN2`, `BACKUP1` and so on for the others.

`PASSED` and zeros for `Reallocated_Sector_Ct` and `Current_Pending_Sector` mean the drive is healthy. If either number starts to rise, replace the drive. The `Load_Cycle_Count` should climb slowly. Hundreds a day means the power setting from [storage guide, step 7](storage.md#7-drive-power-settings) isn't applied.

## Backups

`homelab-backup` runs from root's crontab at 6:00 every day (set up in [storage guide, step 9](storage.md#9-the-daily-backup)). Check it with:

```bash
sudo drives status
sudo tail -20 /var/log/homelab-backup.log
```

The last line of `status` shows the date, the result and where the backup went. If it says `FAILED`, the log says why: the main pool wasn't mounted, the backup target wasn't mounted, there wasn't enough free space, or the Nextcloud database container wasn't running. To get a deleted or changed file back, copy it out of `_deleted/<date>/` or `main/` as shown in [storage guide, step 9](storage.md#9-the-daily-backup).

The Nextcloud database is dumped as part of every run, so you no longer need to dump it by hand. Immich writes its own database backups into `/mnt/storage/immich/backups`, which the backup copies with the rest of the pool. Until a backup drive is connected, the backup sits in a folder on the boot drive, which does not protect against a failed boot drive.

## After a disconnect or power cut

```bash
sudo hdd-recover
```

If you unplug a drive on purpose, don't just pull the cable. Open `sudo drives`, choose **3** (Disconnect a drive) and wait for the message that it is safe to unplug.

## Rebuild the server after the boot drive dies

This is the plan for the day the boot drive (the one with Linux on it) fails or you want to start over on a clean install. The idea: **GitHub gives you the tools, the backup gives you the data, and your password manager gives you the secrets.** Nothing is typed from memory.

> **Status: written from the design and checked on a fake file tree, not yet rehearsed on a real rebuild.** The parts that touch my real services (the two database restores) follow the official [Immich](https://docs.immich.app/administration/backup-and-restore) and [Nextcloud](https://docs.nextcloud.com/server/stable/admin_manual/maintenance/restore.html) restore guides. Treat the first real run as a rehearsal: go slowly, one step at a time, and keep the old drives untouched until the end.

**What survives a dead boot drive**

| Where it lives | What is in it | After the boot drive dies |
| :--- | :--- | :--- |
| GitHub (this repository) | The scripts, the stack files, the Homepage config, these guides | Safe |
| The main drive (`MAIN1`) | Immich photos, Nextcloud files, FileBrowser share, Immich's own nightly database dumps in `/mnt/storage/immich/backups` | Safe, it is a separate drive |
| A backup drive (`BACKUP1`) | The daily copy of the main pool, `boot-configs/` (Homepage, Nextcloud app files, AdGuard settings, Beszel and FileBrowser data), `db-dumps/` (Nextcloud database) | Safe, if you have one |
| The interim backup folder on the boot drive | The same as above | **Lost with the boot drive.** Without a backup drive, you lose the Nextcloud database dump and the saved configs. The photos and files are still safe, and Immich can still be restored from its own dumps |
| Your password manager | The passwords and keys the stacks need | Safe, if you really keep them there |

**Have these ready before you start:** the Linux Mint installer stick ([build guide, section 1.2](build-guide.md#12-make-the-installer-usb-stick)), the main drive and the backup drive, your Tailscale login, and from your password manager: the Nextcloud database password, the Nextcloud admin login, the Immich database user name and password, the Speedtest Tracker `APP_KEY`, and the Homepage widget keys ([build guide, section 14.3](build-guide.md#143-fill-in-the-widget-keys)). The Nextcloud database password must be the same one as before, because it is also written inside Nextcloud's `config.php`.

**Step 1: Free the old name in Tailscale.** In the [admin console](https://login.tailscale.com/admin/machines), delete the dead machine. If you skip this, the new server joins as `your-hostname-1` and every address that contains the old name stops matching (Nextcloud's `OVERWRITEHOST`, the Homepage allowed hosts, your phone's Immich address).

**Step 2: Install Linux and the base system.** Use the **same user name and the same host name** as before, because the scripts and the stack files contain `/home/your-username/...`. Follow [1.3 to 1.5](build-guide.md#13-bios-setting-and-booting-the-stick), then [build guide, section 2.1](build-guide.md#21-reserve-a-fixed-address-for-the-server) and [build guide, section 2.2](build-guide.md#22-ssh-server). If the computer is new, its network card has a new address, so update the reservation in your router so the server gets the same fixed address.

**Step 3: Install Docker, but do not start any stack yet.** Follow [build guide, section 3](build-guide.md#3-docker), then the "wait for the pool" file from [storage guide, step 6](storage.md#6-make-docker-wait-for-the-pool). Install Tailscale ([build guide, section 5](build-guide.md#5-tailscale)) and run `sudo tailscale up`, but leave the `tailscale serve` commands for later.

**Step 4: Get the tools from GitHub.** Follow [storage guide, step 1](storage.md#1-install-the-tools) and [storage guide, step 2](storage.md#2-install-the-scripts): install the tools, clone the repository, check `SHA256SUMS` (all five lines `OK`), then install `drives`, `homelab-backup`, `hdd-recover` ([storage guide, step 8](storage.md#8-the-recovery-command)) and `homelab` ([storage guide, step 14](storage.md#14-the-cheat-sheet-at-login)).

**Step 5: Reconnect the drives without erasing them.** Plug in the main drive and run `sudo drives`. Choose **2** (Connect a new drive), pick the main drive, choose **Main storage**, and when it says the drive already has an ext4 partition with data, choose **Keep the data and add the drive as it is**. **Never choose "Erase everything" here.** Repeat for the backup drive with **Backup storage**. Then check:

```bash
sudo drives status
ls /mnt/storage
ls /mnt/backup
```

`ls /mnt/storage` must show your folders (`immich`, `nextcloud`, `filebrowser`). Now create the folders on the boot drive, the same as [storage guide, step 5](storage.md#5-create-a-folder-for-each-service) but **only the lines that create folders under `/home/your-username/` and `/opt/`**. Skip the two `chown -R` lines for the pool: its folders already exist with the right owners. Finally set the drive power cron line ([storage guide, step 7](storage.md#7-drive-power-settings)) and the backup settings and cron line ([storage guide, step 9](storage.md#9-the-daily-backup)).

**Step 6: Restore the saved config files, the safe way.** The backup keeps the boot drive's config files under their full paths in `boot-configs/`, so one `rsync` can put them back. **Do not copy everything.** The backup contains the old `/etc/fstab`, which holds the old boot drive's identifiers, and restoring it makes the new server unbootable. The command below leaves out that file, the scripts (the ones from GitHub are newer), the crontab record, and the Docker data (those are restored service by service in Step 8). Set `BK` to your backup first:

```bash
BK=/mnt/backup
sudo ls "$BK/boot-configs"
sudo rsync -aHn --numeric-ids --itemize-changes --exclude=/etc/fstab --exclude=/usr/local/ --exclude=/root-crontab.txt --exclude=/var/lib/docker/ "$BK/boot-configs/" / | head -40
```

The first `ls` should list `etc`, `home`, `opt`, `usr`, `var` and `root-crontab.txt`. The `rsync` with `-n` only **prints** what it would copy. Read it: you should see the Homepage config, the Nextcloud app folder and AdGuard Home's settings, and nothing under `/etc/fstab` or `/usr/local`. If it looks right, run it for real, and compare the saved crontab with the one you set up in Step 5:

```bash
sudo rsync -aH --numeric-ids --exclude=/etc/fstab --exclude=/usr/local/ --exclude=/root-crontab.txt --exclude=/var/lib/docker/ "$BK/boot-configs/" /
sudo systemctl daemon-reload
sudo cat "$BK/boot-configs/root-crontab.txt"
sudo crontab -l
```

**Step 7: Portainer and the stacks.** Install Portainer fresh ([build guide, section 4](build-guide.md#4-portainer)) and create a new admin account. (The saved Portainer data is not restored on purpose: it is a live database file, and your stacks are all in this repository.) Create each stack with **the same name as before**. It matters most for Beszel (`beszel`) and FileBrowser (`filebrowser`), because the stack name is the start of their Docker volume names (`beszel_beszel_data`, `filebrowser_filebrowser_data`), and Step 8 needs those exact names. Use the YAML from the sections below or from the [`stacks/`](../stacks/) folder, and put the passwords from your password manager into the "Environment variables" box. Deploy them one at a time and wait for each to be healthy. Then run the `tailscale serve` commands from [build guide, section 5](build-guide.md#5-tailscale).

**Step 8: Put each service's data back.**

| Service | What to do |
| :--- | :--- |
| AdGuard Home ([build guide, section 6](build-guide.md#6-adguard-home)) | Nothing more. Its settings came back in Step 6, so it starts with your filters and DNS rewrites. |
| Homepage ([build guide, section 14](build-guide.md#14-homepage-dashboard)) | Nothing more. Its config came back in Step 6. |
| Speedtest Tracker ([build guide, section 13](build-guide.md#13-speedtest-tracker)) | Nothing more if its folder was in your `CONFIG_PATHS` ([storage guide, step 9](storage.md#9-the-daily-backup)). Use the same `APP_KEY` as before, or its saved settings can't be read. |
| Beszel ([build guide, section 7](build-guide.md#7-beszel)) and FileBrowser ([build guide, section 9](build-guide.md#9-filebrowser)) | Deploy the stack, then `docker stop beszel` (or `filebrowser-filebrowser-1`), run `sudo rsync -aH --numeric-ids "$BK/boot-configs/var/lib/docker/volumes/beszel_beszel_data/" /var/lib/docker/volumes/beszel_beszel_data/` (FileBrowser: `filebrowser_filebrowser_data`), then `docker start` it again. If the Beszel agent can't connect, copy a fresh `KEY` and `TOKEN` from the hub ([build guide, section 7.2](build-guide.md#72-agent)). |
| Netdata ([build guide, section 8](build-guide.md#8-netdata)) | Nothing to restore. |
| Immich ([build guide, section 10](build-guide.md#10-immich)) | Deploy with the same `UPLOAD_LOCATION`. The photos are already there, but the database on the boot drive is gone. On the welcome page click **Restore from backup**, choose the newest file from `/mnt/storage/immich/backups` and restore. Don't create a new account first. |
| Nextcloud ([build guide, section 11](build-guide.md#11-nextcloud)) | Step 6 already brought back the app folder with `config.php`. Use the **same** database password as in that file. Deploy the stack, immediately stop the app containers (`docker stop nextcloud nextcloud_cron`), empty the new database and load the newest dump. Details below. |

**Nextcloud database restore.** Replace `DATE` with the date of the newest file in `$BK/db-dumps`. The user and database are both called `nextcloud`:

```bash
ls -lh "$BK/db-dumps" | tail -3
docker exec nextcloud_db psql -U nextcloud -d template1 -c 'DROP DATABASE nextcloud;'
docker exec nextcloud_db psql -U nextcloud -d template1 -c 'CREATE DATABASE nextcloud;'
gunzip -c "$BK/db-dumps/nextcloud-DATE.sql.gz" | docker exec -i nextcloud_db psql -U nextcloud -d nextcloud >/dev/null
docker start nextcloud nextcloud_cron
docker exec -u www-data nextcloud php occ maintenance:data-fingerprint
docker exec -u www-data nextcloud php occ files:scan --all
```

The `gunzip` line prints a lot unless you silence it, which is why it ends with `>/dev/null`. Errors still show. If `DROP DATABASE` complains that the database is in use, the app containers are still running: stop them and try again. `data-fingerprint` makes your synced devices check their files against the restored server, and `files:scan` makes Nextcloud look at the files in the pool.

**Step 9: Point everything at the server again.** If the server's address or Tailscale name changed, update AdGuard's DNS rewrite and the devices that use it ([build guide, section 6.4](build-guide.md#64-point-your-devices-at-it)), and the Immich address in the phone app.

**Step 10: Check it, then make a backup.**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
sudo drives status
sudo homelab-backup
```

Every container should be `Up` or `healthy`. Log in to Immich and Nextcloud and open a few old photos and files. When `homelab-backup` finishes with `finished: OK` (watch it with `sudo tail -f /var/log/homelab-backup.log`), do the reboot test from [storage guide, step 10](storage.md#10-verify-the-storage-setup). Only now is it safe to wipe or throw away anything from the old setup.

**If the backup was lost too** (the interim backup on the dead boot drive), skip the parts of Step 6 and Step 8 that need it. Immich still restores from its own dumps on the main drive. Homepage comes from the repository, and AdGuard Home needs a new setup ([build guide, section 6](build-guide.md#6-adguard-home)). Nextcloud's files are safe on the main drive, but its accounts, shares and settings are gone: the realistic way is to deploy it as a new install, create the same user names, and run `occ files:scan --all`. I have not tried this, so ask for help and don't delete anything on the main drive while you work on it.

**If the main drive died too,** do Step 5 with the new drive as **Main storage**, then use the replace tool ([storage guide, step 15](storage.md#15-replace-a-dead-drive)) to copy the files back from the backup before you continue with Step 6.

## Updating

Every service here has its own written update procedure in [the updating guide](updating.md). It lists what can be updated, what to check first and how to undo each update. In short:

- **Containers:** make a fresh backup first (`sudo homelab-backup`, wait for `finished: OK`). Change the version on the stack's `image:` line, pull the new image in the terminal, then in Portainer open the stack and click **Update the stack**. Update one service at a time, and Immich and Nextcloud only on their own. Don't skip major versions of Nextcloud: update one major version at a time.
- **Before you click Update the stack,** check the container has no anonymous volume. Its data can be lost on the update ([B6](troubleshooting.md#b6-a-container-starts-empty-after-update-the-stack)).
- **Portainer itself** is not a stack. It is recreated from the terminal, as described in [Portainer](updating.md#portainer).
- **Docker Engine** restarts every container when it updates. **Tailscale** can disturb the server's DNS when it updates ([F6](troubleshooting.md#f6-the-server-cannot-look-up-names-after-a-tailscale-update)).
- **System:** `sudo apt update && sudo apt upgrade -y`, then reboot and run the reboot test from [storage guide, step 10](storage.md#10-verify-the-storage-setup).
