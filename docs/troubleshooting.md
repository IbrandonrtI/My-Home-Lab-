# Troubleshooting

Problems I ran into while building and running this lab, and how I fixed them. Every entry has the same four parts: **Symptom**, **Cause**, **Fix** and **Check it**. Find your symptom in the list below, or search the page for the error message.

**Notes before you start**

- The server is a small PC with the host name `pc`, running Linux Mint 22.3. Addresses and names are placeholders: `your-username` (the Linux user), `192.168.X.X` (the server's address) and `your-tailnet.ts.net` (your Tailscale network). `192.168.X.Y` stands for the address of the old server in the migration notes. Passwords, keys and tokens are written as `your-own-key`.
- Drive letters change (`sda` and `sdb` can swap after a reboot). Use the label or the UUID for anything permanent, and replace `sda`, `sdb` or `sdX` in a command with your drive's current letter. See [Setup at a glance](#setup-at-a-glance).
- The tools: `sudo drives` (menu and status), `sudo hdd-recover`, `sudo homelab-backup` and `homelab` (a cheat sheet and live status when a terminal opens). They are explained in the [storage guide](storage.md).
- Entries marked **Old setup** are from my first server, which used an NTFS drive. I kept them because the same problems can come back if you reuse a Windows-formatted drive.

**Contents**

- [Setup at a glance](#setup-at-a-glance): what runs where
- [A. Drives and storage](#a-drives-and-storage) (A1 to A16)
- [B. Docker and Portainer](#b-docker-and-portainer) (B1 to B6)
- [C. FileBrowser](#c-filebrowser) (C1 to C3)
- [D. Nextcloud](#d-nextcloud) (D1 to D9)
- [E. Tailscale](#e-tailscale) (E1 to E7)
- [F. AdGuard Home and DNS](#f-adguard-home-and-dns) (F1 to F6)
- [G. Homepage](#g-homepage) (G1 to G13)
- [H. Remote access](#h-remote-access) (H1 to H5)
- [I. Hardware and boot](#i-hardware-and-boot) (I1 to I2)
- [Diagnostic commands](#diagnostic-commands)
- [Prevention checklist](#prevention-checklist)

Updating a service is covered in the [updating guide](updating.md). How the lab was first built is in [history](history/lenovo-migration.md).

## Setup at a glance

| Service | Container name | Local port | Tailscale address | Where its data lives |
| :--- | :--- | :--- | :--- | :--- |
| Homepage | `homepage` | 3001 | `https://pc.your-tailnet.ts.net:1000` | `/home/your-username/homepage-config` (boot drive) |
| Portainer | `portainer` | 9000 (HTTP), 9443 | `https://pc.your-tailnet.ts.net:1001` | Docker volume `portainer_data` |
| Immich | `immich_server`, `immich_postgres`, `immich_machine_learning`, `immich_redis` | 2283 | `https://pc.your-tailnet.ts.net:1002` | Photos on the data drive: `/mnt/storage/immich`. Database on the boot drive: `/home/your-username/immich/postgres` |
| Beszel | `beszel`, `beszel-agent` | 8090 | `https://pc.your-tailnet.ts.net:1003` | Docker volume `beszel_beszel_data` |
| AdGuard Home | `adguardhome` (host network) | 3000 (web), 53 (DNS) | `https://pc.your-tailnet.ts.net:1004` | `/opt/adguard-docker` (boot drive) |
| Nextcloud | `nextcloud`, `nextcloud_db`, `nextcloud_redis`, `nextcloud_cron` | 8082 | `https://pc.your-tailnet.ts.net:1005` | Files on the data drive: `/mnt/storage/nextcloud`. Database and app files on the boot drive: `/home/your-username/nextcloud` |
| FileBrowser | `filebrowser-filebrowser-1` | 8081 | `https://pc.your-tailnet.ts.net:1006` | Data drive: `/mnt/storage/filebrowser` (shown as `/srv/hdd`). Boot drive: `/home/your-username/750GB_HDD` (shown as `/srv/750GB_HDD`) |
| Speedtest Tracker | `speedtest-tracker` | 8088 | `https://pc.your-tailnet.ts.net:1007` | `/home/your-username/speedtest-tracker` (boot drive), shown in the container as `/config`. It was an anonymous Docker volume until 2026-10-23: [B6](#b6-a-container-starts-empty-after-update-the-stack) |
| Netdata | `netdata-netdata-1` | 19999 | `https://pc.your-tailnet.ts.net:1008` | Docker volumes |

The nine Portainer stacks are named `adguard`, `beszel`, `beszel-agent`, `filebrowser`, `immich`, `nextcloud`, `speedtest-tracker`, `netdata` and `homepage`.

| Drive | Size | Used for |
| :--- | :--- | :--- |
| Boot drive: Hitachi Travelstar 5K750 (`sdb` today) | 698.6G | Linux Mint on LVM, Docker, databases, app files and config |
| Data drive: Toshiba MQ01ABD100 (`sda` today, label `MAIN1`) | 916G usable | Photos, Nextcloud files, FileBrowser share. ext4, mounted at `/mnt/disks/MAIN1` and joined into the main pool at `/mnt/storage` |
| Backup | no drive yet | The daily 6:00 backup goes to `/home/your-username/750GB_HDD/backup-interim` on the boot drive. A backup drive (label `BACKUP1`, pool `/mnt/backup`) comes later. |

**Drive letters change.** The letters `sda` and `sdb` aren't fixed. On my machine they were `sda` for the Hitachi and `sdb` for the Toshiba at first, and they swapped later (the Toshiba is now `sda`, so the data drive's partition is `/dev/sda1`). The expected outputs in this guide show those current letters. If yours differ, read them as "the data drive's partition". Identify drives by model with `lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS`, by the label `MAIN1`, or by the partition mounted at `/boot/efi`. `sudo drives status` lists every pool drive with its current device name.

## Problems and fixes

Each entry has the same four parts: Symptom, Cause, Fix and Check it. Entries written before the data drive became a pool show it as `/dev/sda1` in the `df` checks. Now that it's a pool, the same checks show `mergerfs-main` instead, and everything else still applies.

### A. Drives and storage

#### A1. The data drive comes back under a different path after a replug

**Symptom:** after unplugging and replugging the drive, FileBrowser can't see it and the Homepage drive pill is blank.

**Cause:** the desktop mounts external drives under `/media/your-username/<label>`, not at the path the stacks use. Containers also keep the old view of the drive.

**Fix:** with the setup in [Storage setup notes (build log)](history/storage-setup-notes.md#storage-setup-notes-build-log), run:

```bash
sudo hdd-recover
```

Before the fixed mount existed (on the Lenovo, with the old NTFS drive), this was the manual fix:

```bash
lsblk -f
ls /media/your-username/
sudo mount -t ntfs-3g -o uid=1000,gid=1000 /dev/sdb2 "/media/your-username/USB STICK"
docker restart filebrowser-filebrowser-1 homepage
```

**Check it:** `findmnt /mnt/storage` shows the drive, and the `df` checks from [Step 8](history/storage-setup-notes.md#step-8-verify-it) show the pool in each container.

#### A2. A Windows-formatted drive: sdb1 vs sdb2 and the wrong filesystem type error

> **Old setup.** This entry is from the first server, whose data drive was formatted as NTFS (Windows). The lab now uses ext4 drives, where this can't happen. It is kept for anyone who reuses a Windows-formatted drive.

**Symptom:** mounting fails with `wrong fs type, bad option, bad superblock on /dev/sdb1`.

**Cause:** a drive formatted by Windows has a small first partition (`sdb1`) with no filesystem, and the data is on `sdb2`.

**Fix:** list the partitions and mount the one that shows a filesystem:

```bash
lsblk -f
sudo mount -t ntfs-3g -o uid=1000,gid=1000 /dev/sdb2 "/media/your-username/USB STICK"
```

If `ntfsfix` says `Refusing to operate on read-write mounted device`, ignore it. `ntfsfix` only works on an unmounted drive, and it's only needed if the mount itself fails with a "dirty" message.

**Check it:** `ls "/media/your-username/USB STICK"` lists your files.

#### A3. The mount is refused because the NTFS volume is already exclusively opened

> **Old setup.** This entry is from the first server, whose data drive was formatted as NTFS (Windows). The lab now uses ext4 drives, where this can't happen. It is kept for anyone who reuses a Windows-formatted drive.

**Symptom:** `Mount is denied because the NTFS volume is already exclusively opened.`

**Cause:** the desktop had already mounted the drive at `/media/your-username/1TB HDD`, so a second mount at another path is refused. The folder you tried to mount onto was then just an empty folder on the boot drive, and anything written there went to the wrong drive.

**Fix:** unmount the desktop's copy and mount the drive from `/etc/fstab` at the fixed path:

```bash
findmnt "/media/your-username/USB STICK"
sudo umount "/media/your-username/1TB HDD"
sudo systemctl daemon-reload
sudo mount -a
findmnt "/media/your-username/USB STICK"
```

The first command should print nothing. The last should show `/dev/sdb2`. The ext4 setup in [Storage setup notes (build log)](history/storage-setup-notes.md#storage-setup-notes-build-log) avoids this by mounting at `/mnt/storage`.

**Check it:** `findmnt` shows the drive at the fixed path.

#### A4. Immich's database keeps restarting on an NTFS drive

> **Old setup.** This entry is from the first server, whose data drive was formatted as NTFS (Windows). The lab now uses ext4 drives, where this can't happen. It is kept for anyone who reuses a Windows-formatted drive.

**Symptom:** in Portainer, `immich_postgres` and `immich_server` keep restarting. The same stack worked when the folder was on the internal drive.

**Cause:** the database folder was on the NTFS drive. Postgres needs a Linux filesystem so it can set file owners and permissions on its data.

**Fix:** keep the database on the boot drive and only the photos on the data drive. In the stack's environment variables:

```text
UPLOAD_LOCATION=/mnt/storage/immich
DB_DATA_LOCATION=/home/your-username/immich/postgres
```

```bash
mkdir -p /home/your-username/immich/postgres
```

If a half-built database was left on the data drive, delete only the folder you created for it. Don't delete anything else. A spin-down setting can also cause slow starts and failed health checks, so turn it off:

```bash
sudo hdparm -S 0 /dev/sda
```

**Check it:**

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
sudo mv "/media/your-username/USB STICK/1TB HDD/immich" /home/your-username/immich-ssd-copy
mkdir -p "/media/your-username/USB STICK/1TB HDD/immich"
rsync -rt --no-perms --no-owner --no-group --info=progress2 /home/your-username/immich-ssd-copy/ "/media/your-username/USB STICK/1TB HDD/immich/"
du -sh /home/your-username/immich-ssd-copy "/media/your-username/USB STICK/1TB HDD/immich"
```

The two sizes should match. Once Immich shows your photos from the data drive, free the space with `sudo rm -rf /home/your-username/immich-ssd-copy`. The lasting fix is the locked mount point and the Docker wait rule from [Step 2](history/storage-setup-notes.md#step-2-add-the-main-drive), which make a missing drive stop the service with an error.

**Check it:**

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

**Check it:** the `df` commands in [Step 8](history/storage-setup-notes.md#step-8-verify-it) show the pool in each container.

#### A7. Containers start before the drive is mounted after a reboot

**Symptom:** after a reboot, a container shows the boot drive or an empty folder, or fails to start.

**Cause:** Docker started containers before the drive was mounted.

**Fix:** add the wait rule if it's missing (it's in [Step 2](history/storage-setup-notes.md#step-2-add-the-main-drive)):

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
printf '[Unit]\nWants=mnt-storage.mount\nAfter=mnt-storage.mount\n' | sudo tee /etc/systemd/system/docker.service.d/wait-for-hdd.conf
sudo systemctl daemon-reload
```

If a drive of the pool is missing at boot, the pool doesn't mount, and the locked mount point makes the services fail with an error, so they don't write to the boot drive. Plug the drive in and run `sudo hdd-recover`. I tested the missing-drive case with fake drives, not on my real hardware.

**Check it:** after `sudo reboot`, run `findmnt /mnt/storage` and `docker ps`.

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

The last command should print `APM_level = 254`. Do the same for the boot drive with `/dev/$BOOT`. The `SG_IO: bad/missing sense data` messages are common with USB adapters and can be ignored. Keep the setting after reboots with the cron lines from [Step 5](history/storage-setup-notes.md#step-5-drive-power-settings-and-cron-lines). The `drives power` line there applies it to every pool drive. If the count still climbs by hundreds a day, try `sudo hdparm -B 255 /dev/$DATA`.

**Check it:** the boot drive's count stayed at 48,421 after the change, and the data drive's rose only from 105,799 to 105,835 over a few hours. With the logging line from Step 5, `cat /var/log/loadcycles.log` shows one number a day. Under about 50 a day is healthy.

#### A9. The cron job logs a date with no number

**Symptom:** `/var/log/loadcycles.log` has a date but no count after it.

**Cause:** cron runs with a short search path that doesn't include `/usr/sbin`, where `smartctl` lives.

**Fix (only if the number is blank):** add this as the first line of root's crontab:

```bash
sudo crontab -e
```

```text
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

**Check it:** `sudo crontab -l` shows the line, and the log has a number after the next morning's date.

#### A10. Immich and Nextcloud overload the machine when they start together

**Symptom:** `immich_server` shows `(unhealthy)` for a long time, its log is full of `could not renew lock for job` and `Missing lock for job` errors, `uptime` shows a load average of about 7.8 on a 4-core machine, and the Nextcloud install looks stuck: the log stops at `Starting nextcloud installation` and the data folder holds only `nextcloud.log`.

**Cause:** the two stacks started at the same time on a single hard-drive boot disk. Immich's background-job queue stalls under the load, and the Nextcloud install is slow. It isn't a real error.

**Fix:** wait, and don't deploy anything else. Check progress without following the log:

```bash
uptime
docker logs immich_server --tail 40
curl -s http://192.168.X.X:2283/api/server/ping
docker logs nextcloud --tail 15
sudo ls -a /mnt/storage/nextcloud
```

A healthy Immich answers the ping with `{"res":"pong"}`. The Nextcloud install is finished when the folder lists `.ncdata`, an `appdata_...` folder and your login folder. On my machine the load fell to about 0.05 after 10 to 15 minutes, and Immich turned healthy by itself.

**Check it:** `docker ps --format "table {{.Names}}\t{{.Status}}"` shows every Immich container `healthy`. To prevent it, deploy Immich, wait for it to turn healthy, and only then deploy Nextcloud.

#### A11. The practice pool is still mounted after test mode

**Symptom:** after practising with `DRIVES_TEST=1 drives` and closing the menu, the USB stick is still mounted in the practice pool (under `/mnt/test-disks` and `/mnt/test-main`). The normal `sudo drives status` doesn't show that: it lists the stick as `/dev/sdc   7.2G  USB DISK 2.0  [usb]   not connected to a pool`, so it looks as if nothing is left over.

**Cause:** test mode keeps its pools mounted until you run `test-cleanup`. I closed the menu after the USB stick practice and didn't run it.

**Fix:**

```bash
sudo DRIVES_TEST=1 drives test-cleanup
```

It unmounts the practice pools and drives, detaches the fake drives and deletes the image files and the test fstab.

**Check it:** this prints nothing:

```bash
findmnt -rn | grep -E 'test-main|test-disks'
```

A USB stick you practised with may still appear in `lsblk` under `/media/your-username/TMAIN1`. That is the desktop auto-mounting the freshly formatted stick. Unmount it from the file manager, or format it again if you want it back as a normal stick.

#### A12. findmnt prints nothing when given two paths

**Symptom:** right after `sudo drives adopt`, `findmnt /mnt/storage /mnt/disks/MAIN1` printed nothing at all, and it looked as if neither the pool nor the drive was mounted.

**Cause:** `findmnt` is meant to be given one mount point or device per command. With two, it printed nothing for me, even though both were mounted. The next commands showed both mounts correctly.

**Fix:** run one `findmnt` per command:

```bash
findmnt /mnt/storage
findmnt /mnt/disks/MAIN1
```

**Check it:** the first shows `mergerfs-main` with the type `fuse.mergerfs`, and the second shows `/dev/sda1` with the type `ext4`.

#### A13. hdparm -B -S says bad or missing standby interval

**Symptom:** `sudo hdparm -B -S /dev/sda` prints `-S: bad/missing standby-interval value (0..255)` and shows nothing else.

**Cause:** `-S` always needs a number right after it, because it sets the spin-down timeout. It can't be used to read the setting back, and as far as I know `hdparm` has no option that reads the spin-down timeout.

**Fix:** read the head-parking level with `-B` alone, and check the drive's current power state with `-C`:

```bash
sudo hdparm -B /dev/sda
sudo hdparm -C /dev/sda
```

**Check it:** the first prints `APM_level      = 254`, and the second prints `drive state is:  active/idle` for a main drive. A backup drive that has been idle for more than 10 minutes should print `standby` (I haven't been able to test that yet).

#### A14. The crontab went back to the old lines

**Symptom:** after running the `sed` command that changes root's crontab, `sudo crontab -l` shows the old lines again, with `by-label/STORAGE`, and no `drives power` line.

**Cause:** I ran the command that restores the saved copy (`sudo crontab ~/crontab-before-step7.txt`) in the same block as the change, so it replaced the new crontab with the old one.

**Fix:** run the `sed` command again. It only rewrites lines that still say `STORAGE`, so running it twice does no harm:

```bash
sudo crontab -l | sed -e 's|^@reboot sleep 60 && /usr/sbin/hdparm -S 0 -B 254 .*by-label/STORAGE.*$|@reboot sleep 60 \&\& /usr/local/sbin/drives power >/dev/null 2>\&1|' -e 's|by-label/STORAGE|by-label/MAIN1|' | sudo crontab -
```

**Check it:** `sudo crontab -l | grep -v '^#'` shows the `drives power` line and `by-label/MAIN1` in the load-cycle line. Keep an "undo" command in its own block, away from the commands that change something, so it can't be run by accident. To undo for real, use `sudo crontab ~/crontab-before-step7.txt`.

#### A15. pgrep shows nothing while the backup is running

**Symptom:** while the first backup was running (the backup folder kept growing), `pgrep -a homelab-backup` printed nothing, so it looked as if the backup had stopped.

**Cause:** the script starts with `#!/usr/bin/env bash`, so the running process is called `bash`, not `homelab-backup`. Without `-f`, `pgrep` matches only the process name.

**Fix:** search the full command line with `-f`, or follow the log until it says `finished`:

```bash
pgrep -af homelab-backup
sudo tail -f /var/log/homelab-backup.log
```

**Check it:** while the backup runs, `pgrep -af homelab-backup` should list the process. After the log says `finished: OK`, it prints nothing, which is what I saw, and `sudo drives status` shows the result.

#### A16. install says cannot stat when installing a script

**Symptom:** running `sudo install -m 755 homelab /usr/local/bin/homelab` prints `install: cannot stat 'homelab': No such file or directory`.

**Cause:** the command names the file without a path, so it looks in the folder the terminal is in. A new terminal starts in the home folder (`/home/your-username`), and the script is in `~/My-Home-Lab-/scripts`.

**Fix:** go into the folder that holds the files, and run the command again:

```bash
cd ~/My-Home-Lab-/scripts
ls
sudo install -m 755 homelab /usr/local/bin/homelab
```

If you copied the files by hand instead of cloning the repository, go to the folder you copied them to.

**Check it:** `ls` lists `homelab`, `install` prints nothing, and `homelab version` prints `homelab 1.0`.

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

**Check it:** `docker --version` prints a version.

#### B2. Permission denied on the Docker socket

**Symptom:** `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`.

**Cause:** your user isn't in the `docker` group in the current session.

**Fix:**

```bash
sudo usermod -aG docker $USER
sudo reboot
```

To test without rebooting, run `newgrp docker`.

**Check it:** `groups` lists `docker`, and `docker run hello-world` prints `Hello from Docker!`.

#### B3. Container names differ from the stack name

**Symptom:** `Error response from daemon: No such container: filebrowser` (or `netdata`).

**Cause:** Portainer names containers from a stack as `<stack>-<service>-<number>`. Containers with a fixed `container_name` (like `immich_server` and `nextcloud`) keep that name.

**Fix:** find the real name and use it:

```bash
docker ps -a | grep -i filebrowser
docker logs filebrowser-filebrowser-1
docker exec netdata-netdata-1 cat /var/lib/netdata/netdata_random_session_id
```

**Check it:** the command prints the container's output instead of an error. This is also why the stack names in this guide matter: the recovery script expects `filebrowser-filebrowser-1`.

#### B4. Portainer asks for a setup token, or the setup page timed out

**Symptom:** a new Portainer asks for a setup token, or says its setup timed out.

**Cause:** Portainer protects a fresh install until you claim it, and closes the first-time setup after about five minutes.

**Fix:**

```bash
docker logs portainer
docker restart portainer
```

Read the token from the logs if it asks for one. If the setup timed out, restart the container and reload `http://192.168.X.X:9000` to create your admin account.

**Check it:** you can log in and see the local environment.

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

**Check it:** `docker images | grep -E "immich|valkey|speedtest|homepage"` lists the images, and the stack deploys with nothing to download.

#### B6. A container starts empty after Update the stack

**Symptom:** I updated Speedtest Tracker in Portainer with **Update the stack**. The container started and was healthy, and `docker logs speedtest-tracker` ended with `generating self-signed keys`, but the app behaved like a new install: the old results and settings were gone.

**Cause:** the stack had no `volumes:` line for `/config`, so Docker created an **anonymous volume** (a volume with a 64-character name and no label). When Portainer recreated the container, the new one got a new empty anonymous volume, and the old one was left behind unused. Bind mounts (a folder on the host) and named volumes are kept. Anonymous volumes aren't reliably kept.

**Fix (what I did, as steps).** I had copied `/config` out of the old container with `docker cp` before updating ([Speedtest Tracker](updating.md#speedtest-tracker)), so nothing was lost.

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
         - /home/your-username/speedtest-tracker:/config
   ```

   Click **Update the stack**.

3. Check it:

   ```bash
   docker ps --filter name=speedtest-tracker --format "table {{.Names}}\t{{.Status}}"
   ls ~/speedtest-tracker
   ```

   Open `https://pc.your-tailnet.ts.net:1007`. The earlier results should be listed again, and the Speedtest card on Homepage should turn green. Mine did, and it stayed green after a second **Update the stack**, which is the real test.

4. Add the folder to the daily backup ([section 2, Step 7](history/storage-setup-notes.md#step-7-the-daily-backup), "Extra folders").

**Prevent it.** Before you update any stack, list which containers use anonymous volumes. A volume name made of 64 letters and digits is anonymous:

```bash
docker inspect $(docker ps -q) --format '{{.Name}}: {{range .Mounts}}{{if eq .Type "volume"}}{{.Name}} {{end}}{{end}}'
```

To list only the anonymous ones:

```bash
docker inspect $(docker ps -q) --format '{{.Name}}: {{range .Mounts}}{{if eq .Type "volume"}}{{.Name}} {{end}}{{end}}' | grep -E '[0-9a-f]{64}'
```

A container on the second list needs a bind mount or a named volume before you update it. Make a copy first with `docker cp <container>:<path> ~/some-folder`.

**Check it:** the second command prints nothing for the container you are about to update, or you have a `docker cp` copy of its data.

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

**Check it:** you can log in at `http://192.168.X.X:8081`.

#### C2. The FileBrowser data folder is empty because of a folder name mismatch

**Symptom:** FileBrowser shows an empty `hdd` folder.

**Cause:** the stack pointed at a folder that doesn't exist under that exact name. On the old setup, the stack said `1TB_HDD` (with an underscore) but the real folder was `1TB HDD` (with a space). Paths with spaces also need quotes in YAML.

**Fix:** the volume line must match the real folder, and be quoted if it has a space:

```yaml
      - "/media/your-username/USB STICK/1TB HDD:/srv/hdd"
```

The current stack avoids spaces entirely:

```yaml
      - "/mnt/storage/filebrowser:/srv/hdd"
```

**Check it:**

```bash
ls "/mnt/storage/filebrowser"
docker exec filebrowser-filebrowser-1 df -h /srv/hdd
```

#### C3. The FileBrowser card shows the boot drive numbers

**Symptom:** the FileBrowser card on Homepage shows the boot drive's numbers, not the 1TB data drive's.

**Cause:** the card reports the drive of the login's folder, and the admin login's folder is `/srv`, which is on the boot drive.

**Fix (optional):** this isn't part of my current setup, where the card is labeled "750GB HDD" on purpose and the drive pill shows the data drive. To get a card for the data drive, make a second FileBrowser login limited to its folder. In FileBrowser, open Settings, then User Management, and add a user named `homepage` with a password of at least 12 characters. Set **Scope** to `/hdd` and turn off all its permissions. Then add a card to `services.yaml`:

```yaml
    - FileBrowser (HDD):
        id: filebrowser-hdd-card
        href: https://pc.your-tailnet.ts.net:1006/files/hdd
        siteMonitor: http://192.168.X.X:8081
        icon: filebrowser.svg
        description: 1TB storage drive
        widget:
          type: filebrowser
          url: http://192.168.X.X:8081
          username: homepage
          password: your-own-key
```

The new card has no colored accent until `#filebrowser-hdd-card` is added to the accent selectors in `custom.css`.

**Check it:** after `docker restart homepage`, the new card shows the data drive's available and total space.

### D. Nextcloud

#### D1. Access through untrusted domain

**Symptom:** Nextcloud says "Access through untrusted domain."

**Cause:** the address you're using isn't in Nextcloud's trusted domain list. The `NEXTCLOUD_TRUSTED_DOMAINS` variable is only read on the first install.

**Fix:** add the domain with `occ`, using an index number that isn't used yet:

```bash
docker exec -u www-data nextcloud php occ config:system:get trusted_domains
docker exec -u www-data nextcloud php occ config:system:set trusted_domains 3 --value=pc.your-tailnet.ts.net
```

Both `https://pc.your-tailnet.ts.net:1005` and `http://192.168.X.X:8082` work. If the local address still redirects to the Tailscale one, an older install saved a forced address in Nextcloud's own settings. Check and remove it:

```bash
docker exec -u www-data nextcloud php occ config:system:get overwritehost
docker exec -u www-data nextcloud php occ config:system:delete overwritehost
docker exec -u www-data nextcloud php occ config:system:delete overwriteprotocol
```

Also remove `OVERWRITEHOST` and `OVERWRITEPROTOCOL` from the stack's environment in Portainer, and redeploy.

**Check it:** the first command lists the new domain, and the Tailscale address loads the login page.

#### D2. Cannot write to the data directory

**Symptom:** the first start fails with a message that Nextcloud can't create or write to the data directory.

**Cause:** the data folder isn't owned by the user Nextcloud runs as (UID 33, shown as `www-data`).

**Fix:**

```bash
sudo chown -R 33:33 /mnt/storage/nextcloud
```

Then restart the stack.

**Check it:**

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
        siteMonitor: http://192.168.X.X:8082/status.php
```

Check it, then restart Homepage:

```bash
curl -I http://192.168.X.X:8082/status.php
docker restart homepage
```

The first line should be `HTTP/1.1 200 OK`. If it says `400`, add the address as a trusted domain and try again:

```bash
docker exec -u www-data nextcloud php occ config:system:set trusted_domains 4 --value=192.168.X.X:8082
```

**Check it:** the dot turns green. If it doesn't, check what Homepage saw:

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

In the integration settings, use the base address `http://192.168.X.X:2283`, with no `/photos` and no `/api`. Create the API key in Immich under Account Settings, then API Keys.

**Check it:** the second command prints `true`, and **Test connection** succeeds. Also confirm that Nextcloud can reach Immich: `docker exec -u www-data nextcloud php -r 'echo file_get_contents("http://192.168.X.X:2283/api/server/ping");'` should print `{"res":"pong"}`.

#### D5. A 502 right after deploying Nextcloud

**Symptom:** the Tailscale address shows a 502 error after the stack was first deployed.

**Cause:** Nextcloud takes 2 to 15 minutes to install on its first start on this machine. Apache isn't ready yet.

**Fix:** watch it, then refresh the page:

```bash
docker logs -f nextcloud
```

Press `Ctrl+C` when the install finishes and Apache is ready.

**Check it:** the login page loads.

#### D6. Nextcloud redirects to the wrong port

**Symptom:** clicking the Nextcloud link on its Tailscale port sends you to `https://pc.your-tailnet.ts.net:8441/login`, a port that no longer exists.

**Cause:** `OVERWRITEHOST` and `OVERWRITECLIURL` in the stack still had the old port (8441). They tell Nextcloud to build every link with that port. I had renumbered the Tailscale ports, so Nextcloud was now at 1005.

**Note:** the stack file in this repository no longer has `OVERWRITEHOST` or `OVERWRITEPROTOCOL` (see [D1](#d1-access-through-untrusted-domain)), so a new install doesn't have this problem. Keep reading only if your stack still has them.

**Fix:** in Portainer, open the `nextcloud` stack, click **Editor** and change the two lines in the `app` service:

```yaml
      OVERWRITEHOST: pc.your-tailnet.ts.net:1005
      OVERWRITECLIURL: https://pc.your-tailnet.ts.net:1005
```

Click **Update the stack** with the re-pull option off. Your passwords stay saved, and the install isn't touched.

**Check it:**

```bash
docker exec -u www-data nextcloud php occ config:system:get overwritehost
```

It should print `pc.your-tailnet.ts.net:1005`. If it still prints the old port, set it directly:

```bash
docker exec -u www-data nextcloud php occ config:system:set overwritehost --value=pc.your-tailnet.ts.net:1005
docker exec -u www-data nextcloud php occ config:system:set overwrite.cli.url --value=https://pc.your-tailnet.ts.net:1005
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
curl -s -H "NC-Token: $TOKEN" "http://192.168.X.X:8082/ocs/v2.php/apps/serverinfo/api/v1/info?format=json" | head -c 300
```

A good answer starts with `{"ocs":{"meta":{"status":"ok"`. Put the token into `services.yaml` as the Nextcloud `key`, then `docker start homepage`. The `$TOKEN` variable only exists in the same terminal window.

**Check it:** the Nextcloud card shows its numbers, and Nextcloud's log stops filling with `Reached maximum delay`. To prevent it, always stop Homepage before you edit its keys.

#### D8. Permission denied when listing the Nextcloud data folder

**Symptom:** `ls /mnt/storage/nextcloud` says `Permission denied`.

**Cause:** once Nextcloud finishes installing, it makes its data folder private (`drwxrwx---`, owned by `www-data`). This is normal.

**Fix:**

```bash
sudo ls -a /mnt/storage/nextcloud
```

**Check it:** the listing shows `.ncdata`, an `appdata_...` folder and your login folder.

#### D9. The Immich integration test fails with an authentication error

**Symptom:** **Test connection** in the Immich Integration settings reports an authentication or permission error.

**Cause:** the API key was pasted wrongly, was revoked, or lacks the permissions the app needs.

**Fix:** create a new key in Immich (profile picture, **Account Settings**, **API Keys**, **New API Key**), choose all permissions, copy it as soon as it appears, and paste it into the integration settings. First confirm that Nextcloud can reach Immich:

```bash
docker exec -u www-data nextcloud php -r 'echo file_get_contents("http://192.168.X.X:2283/api/server/ping");'
```

It should print `{"res":"pong"}`. If it does, the problem is the key and not the network.

**Check it:** **Test connection** reports success, and **Save** keeps the settings.

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
sudo tailscale serve --bg --https=1001 http://192.168.X.X:9000
```

**Check it:** `https://pc.your-tailnet.ts.net:1001` loads.

#### E2. tailscale serve says the CLI has changed

**Symptom:** `Error: the CLI for serve and funnel has changed.`

**Cause:** newer Tailscale versions use a different command format.

**Fix:** use `--bg` and put the port in the `--https` option:

```bash
sudo tailscale serve --bg --https=1002 http://192.168.X.X:2283
```

To remove one: `sudo tailscale serve --https=1002 off`.

**Check it:** `tailscale serve status` lists the address.

#### E3. Path-based addresses break apps

**Symptom:** with addresses like `/files` and `/adguard` on one port, the apps load blank or with broken links.

**Cause:** these apps assume they live at the root of the address (`/`).

**Fix:** use one HTTPS port per service. This clears everything and sets the current list again. It is also how I renumbered the ports from the Lenovo's layout to 1000 to 1008:

```bash
sudo tailscale serve reset
sudo tailscale serve --bg --https=1000 http://192.168.X.X:3001
sudo tailscale serve --bg --https=1001 http://192.168.X.X:9000
sudo tailscale serve --bg --https=1002 http://192.168.X.X:2283
sudo tailscale serve --bg --https=1003 http://192.168.X.X:8090
sudo tailscale serve --bg --https=1004 http://192.168.X.X:3000
sudo tailscale serve --bg --https=1005 http://192.168.X.X:8082
sudo tailscale serve --bg --https=1006 http://192.168.X.X:8081
sudo tailscale serve --bg --https=1007 http://192.168.X.X:8088
sudo tailscale serve --bg --https=1008 http://192.168.X.X:19999
```

After renumbering, update every place that still has an old port: Nextcloud's `OVERWRITEHOST` and `OVERWRITECLIURL` ([D6](#d6-nextcloud-redirects-to-the-wrong-port)), Homepage's `href` links and its `HOMEPAGE_ALLOWED_HOSTS` line, and your phone app's server address.

**Check it:** `tailscale serve status` lists nine entries, and each address loads.

#### E4. The tailnet name changed

**Symptom:** after the Tailscale network name changed (mine went from `tail30c3e5.ts.net` to `your-tailnet.ts.net`), links and logins stopped working.

**Cause:** the old name was written into several configs.

**Fix:** update the name in each place:

- Homepage's `services.yaml` (the `href:` links) and the `HOMEPAGE_ALLOWED_HOSTS` line in the Homepage stack.
- The Nextcloud stack's `OVERWRITEHOST` and `OVERWRITECLIURL` lines, and Nextcloud's trusted domains:

```bash
docker exec -u www-data nextcloud php occ config:system:set trusted_domains 3 --value=pc.your-tailnet.ts.net
```

- The server address in your phone and desktop apps.

**Check it:** `tailscale serve status` shows the new name, and every address loads.

#### E5. The name will not resolve from another computer

**Symptom:** `DNS_PROBE_POSSIBLE` or "DNS address could not be found" when opening a Tailscale address.

**Cause:** that computer isn't connected to Tailscale, so it can't look up the name.

**Fix:** open the Tailscale app on that computer and make sure it says **Connected**. If it shows signed in but not connected, quit and reopen the app, or log out and back in. Then test:

```bash
nslookup pc.your-tailnet.ts.net
```

**Check it:** the lookup returns an address starting with `100.`.

#### E6. 502 when forwarding to the wrong address

**Symptom:** a Tailscale address shows 502 even though the service works locally.

**Cause:** the Tailscale entry points at the wrong machine's address, or the old server's address.

**Fix:** check that the server can reach the address, then redo the entry with the right one:

```bash
curl -v http://192.168.X.X:3000
sudo tailscale serve --https=1004 off
sudo tailscale serve --bg --https=1004 http://192.168.X.X:3000
```

**Check it:** `tailscale serve status` shows the right target, and the address loads.

#### E7. An SSH session over Tailscale drops when Tailscale restarts

**Symptom:** a command that restarts Tailscale freezes or ends your session, and the rest of the commands don't run.

**Cause:** the session itself travels through Tailscale.

**Fix:** use the local network address for any step that restarts Tailscale (like freeing port 53):

```bash
ssh your-username@192.168.X.X
```

**Check it:** the session survives `sudo systemctl restart tailscaled`.

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
echo "nameserver 192.168.X.1" | sudo tee /etc/resolv.conf
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

**Check it:**

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

**Check it:** `nslookup dns.google 127.0.0.1` returns a real address, not `0.0.0.0`, and the errors stop.

#### F3. Devices are not using AdGuard Home

**Symptom:** the AdGuard dashboard shows no clients or queries from other devices, though `nslookup` works on the server.

**Cause:** the router wouldn't let me change its DNS setting, so devices keep using the DNS server the router hands out until each one is set by hand. A device with an alternate DNS server of `8.8.8.8` can also use it and skip AdGuard's filtering.

**Fix:** set the DNS server on each device. On Windows 11 (Ethernet): **Settings**, **Network and internet**, **Ethernet**, **DNS server assignment**, **Edit**, **Manual**, **IPv4** on, preferred `192.168.X.X`, alternate `8.8.8.8`, **Save**. On the iPhone: **Settings**, **Wi-Fi**, the **i** next to the network, **Configure DNS**, **Manual**, add `192.168.X.X` and `8.8.8.8`, **Save**. Check from any device:

```bash
nslookup google.com 192.168.X.X
ipconfig /all
ip addr
sudo ss -tulpn | grep :53
```

`ipconfig /all` (Windows) shows which DNS servers the PC got. `ip addr` (on the server) shows the server's address on each network card, so use the wired one (`eno1`). The alternate server `8.8.8.8` keeps the internet working when the server is off. Leave it blank if you want strict filtering and don't mind losing internet while the server is down.

**Check it:** the AdGuard Query Log shows queries from the devices' addresses.

#### F4. The NextDNS app and Tailscale on the iPhone

**Symptom:** with the NextDNS app turned on, the iPhone can't reach the Tailscale addresses.

**Cause:** iOS only runs one VPN at a time. The NextDNS app and Tailscale each use the VPN slot, so they push each other out.

**Fix:** use one of them at a time. At home, AdGuard Home already blocks ads for configured devices. To use NextDNS with Tailscale, add it in Tailscale's DNS settings (Add nameserver, then NextDNS, with your endpoint ID) and delete the NextDNS app's profile. That setting applies to every device on the tailnet, and NextDNS's free plan has a monthly query limit. I removed this setting, and Tailscale's DNS is at its default.

**Check it:** the iPhone opens `https://pc.your-tailnet.ts.net:1000` with Tailscale connected.

#### F5. The AdGuard web page shows a 502 on its Tailscale address

**Symptom:** `https://pc.your-tailnet.ts.net:1004` shows `HTTP ERROR 502`, and the AdGuard card on Homepage has a red dot, but DNS lookups still work.

**Cause:** Tailscale forwards to `192.168.X.X:3000`, but AdGuard's web page isn't on port 3000. The setup wizard proposes port 80, and if you keep it, nothing answers on 3000.

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

**Check it:**

```bash
sudo ss -tulpn | grep AdGuardHome
curl -sI http://192.168.X.X:3000 | head -1
nslookup google.com 192.168.X.X
```

`ss` should show ports 3000 and 53, `curl` should return a line starting with `HTTP/1.1`, and the lookup should still answer.

#### F6. The server cannot look up names after a Tailscale update

**Status:** fixed on 2026-10-23 and working since. **Not yet checked after a reboot.** I don't know yet whether the setting and the file below survive one. The check is at the end of this entry.

**Symptom:**

- `git clone https://github.com/...` on the server fails with `fatal: unable to access ...: Could not resolve host: github.com`.
- `nslookup github.com` answers `** server can't find github.com: SERVFAIL` from `100.100.100.100`.
- The Tailscale card on Homepage turns red, and its log shows `getaddrinfo EAI_AGAIN api.tailscale.com`. The Speedtest Tracker card was red at the same time (it had a second problem of its own, see [B6](#b6-a-container-starts-empty-after-update-the-stack)).
- Everything that doesn't need a name still works: the web pages open by address and Docker keeps running.

**Cause:** on this server Tailscale owns `/etc/resolv.conf` ([F1](#f1-port-53-conflict-with-systemd-resolved)). The file said `nameserver 100.100.100.100`, which is Tailscale's own resolver, and that resolver had nothing to forward to. The message I found was `dns: resolver: forward: no upstream resolvers set, returning SERVFAIL`. The Machines page showed `pc` on 1.104.2, one version newer than the 1.104.1 I had installed, so Tailscale had updated itself (see [Tailscale](updating.md#tailscale)) and I believe that change is what broke it. That is my best explanation, not something I proved. Docker containers copy the host's DNS setting when they start, so Homepage had the broken setting too.

**Diagnose (read-only).** One command at a time:

```bash
cat /etc/resolv.conf
nslookup github.com
tailscale dns status
docker logs adguardhome --tail 30
```

On my server `resolv.conf` started with `# resolv.conf(5) file generated by tailscale` and showed `nameserver 100.100.100.100`. A copy of the file from before Tailscale took it over was still there: `cat /etc/resolv.pre-tailscale-backup.conf` showed `nameserver 192.168.X.1`, the router.

**What didn't help.** `sudo systemctl restart tailscaled` changed nothing. `sudo tailscale set --accept-dns=false` stopped Tailscale from using its DNS, but it didn't put the old file back, so `resolv.conf` still pointed at `100.100.100.100`.

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

   It should show `nameserver 192.168.X.1`.

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

**What this changes.** The server now sends its own lookups to the router (`192.168.X.1`), not through Tailscale. The server's own lookups don't pass through AdGuard Home, and names ending in `.ts.net` may not resolve on the server itself. Your other devices aren't affected, and the Tailscale addresses on ports 1000 to 1008 still work for them.

**Undo,** to let Tailscale manage DNS again:

```bash
sudo tailscale set --accept-dns=true
```

Tailscale then rewrites `/etc/resolv.conf` by itself.

**Check it:**

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
      HOMEPAGE_ALLOWED_HOSTS: 192.168.X.X:3001,pc.your-tailnet.ts.net:1000,localhost:3001
```

**Check it:** `http://192.168.X.X:3001` loads.

#### G2. Port 3000 already in use

**Symptom:** the stack fails with `failed to bind host port 0.0.0.0:3000/tcp: address already in use`.

**Cause:** AdGuard Home's web page uses port 3000.

**Fix:** publish Homepage on a different port. The left number is the port on the server:

```yaml
    ports:
      - 3001:3000
```

Check what AdGuard is using with `sudo ss -tulpn | grep AdGuardHome`.

**Check it:** `http://192.168.X.X:3001` loads.

#### G3. The Beszel widget says No items returned

**Symptom:** `API Error: No items returned from beszel API`.

**Cause:** the widget needs the Beszel superuser login, which is separate from your hub login. It also needs `version: 2`.

**Fix:** reset the superuser login, test it, and make sure the widget has `version: 2`:

```bash
docker exec beszel /beszel superuser upsert your-email@example.com your-own-key
curl -X POST http://192.168.X.X:8090/api/collections/_superusers/auth-with-password -H "Content-Type: application/json" -d '{"identity":"your-email@example.com","password":"your-own-key"}'
docker restart homepage
```

**Check it:** the `curl` returns a token, and the widget shows your system.

#### G4. The Portainer widget shows an error

**Symptom:** the Portainer card shows either `Invalid JWT token` / `Unauthorized`, or `Unable to find an environment with the specified identifier inside the database (bucket=endpoints, key=1)`.

**Cause:** the first one means the `key` is wrong or still the placeholder. The second means the `env:` number doesn't match a Portainer environment. Mine is `3`. A guess like `1` fails.

**Fix:** create an access token in Portainer (your name, **My account**, **Access tokens**, **Add access token**) and copy it when it appears. Find the environment number: click the local environment on Portainer's home page and read the number in the address bar. It appears as `#!/endpoints/<number>` or `#!/<number>/docker/dashboard`. Put both in `services.yaml`:

```yaml
        widget:
          type: portainer
          url: http://192.168.X.X:9000
          env: 3
          key: your-own-key
```

Then `docker restart homepage`. To list the environments from the terminal, set `PT` to your token first. The `echo` line should print a number above 0, and it never prints the token:

```bash
echo ${#PT}
curl -s -H "X-API-Key: $PT" http://192.168.X.X:9000/api/endpoints | python3 -c "import sys,json; [print(e['Id'], e['Name']) for e in json.load(sys.stdin)]"
```

If Python prints `TypeError: string indices must be integers`, Portainer answered with an error message, which usually means `PT` isn't set in that terminal.

**Check it:** the widget shows your container counts.

#### G5. The Tailscale widget says the API token is invalid

**Symptom:** `API token invalid`.

**Cause:** the value pasted wasn't the whole access token. The real token starts with `tskey-api-` and has a second part after a dash. The short code ending in `CNTRL` in the list is only the token's ID, and `tskey-auth-` keys are a different thing.

**Fix:** create a new access token in the admin console and copy it with the copy button the moment it appears, because it's shown only once. Test it before putting it in Homepage:

```bash
curl -H "Authorization: Bearer your-own-key" https://api.tailscale.com/api/v2/tailnet/-/devices
```

Use the machine's ID that ends in `CNTRL` for `deviceid:`.

**Check it:** the `curl` lists your devices, and the card shows its fields.

#### G6. The Speedtest Tracker card shows an error

**Symptom:** the card shows `API Error` with a `Not Found` page, or Speedtest Tracker itself shows `500 | Server Error`. Calling its API by hand with a placeholder token answers `{"message":"Unauthenticated."}`.

**Cause:** for the card, the widget has no valid API token. Speedtest Tracker 1.2.1 and newer need `version: 2` plus a token with the **Read Results** ability. Until a speed test has finished, there is also no latest result to read. The 500 on the page itself is a problem with the app key: the stack's `APP_KEY` was missing the `base64:` prefix at the start.

**Fix:** open `http://192.168.X.X:8088/admin/api-tokens`, create a token with **Read Results**, and copy it. Run one speed test from the dashboard. Test the token (replace the placeholder with your real token):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Accept: application/json" -H "Authorization: Bearer your-own-key" http://192.168.X.X:8088/api/v1/results/latest
curl -s -H "Accept: application/json" -H "Authorization: Bearer your-own-key" http://192.168.X.X:8088/api/v1/results/latest | head -c 300
```

`200` and JSON with your speeds mean the token works. Put it into the card's `key:` line. If the page shows 500, fix the key line: it must start with `base64:` and be 51 characters long. Check without revealing it:

```bash
docker exec speedtest-tracker sh -c 'printf "%s" "$APP_KEY" | wc -c'
docker exec speedtest-tracker sh -c 'printf "%s" "$APP_KEY" | cut -c1-7'
```

They should print `51` and `base64:`. If not, generate a new key with `echo "base64:$(openssl rand -base64 32 2>/dev/null)"`, update the stack and run `docker restart speedtest-tracker`.

**Check it:** the card shows download, upload and ping.

#### G7. Widgets show errors until their keys are filled in

**Symptom:** after deploying Homepage, several cards show `API Error`, and Nextcloud may block the address.

**Cause:** the files in the repository use `your-own-key` as a placeholder, and a widget keeps sending it until you replace it.

**Fix:** stop Homepage, replace the keys one card at a time, and start it again:

```bash
docker stop homepage
nano /home/your-username/homepage-config/services.yaml
docker start homepage
```

The table in [Phase 10](history/lenovo-migration.md#phase-10-homepage) lists where each value comes from. Don't put the real values anywhere that goes into Git.

**Check it:** `docker logs homepage --tail 30` shows no widget errors.

#### G8. YAML indentation mistakes

**Symptom:** a widget doesn't appear, a setting is ignored, or a whole file is skipped.

**Cause:** YAML uses indentation for nesting. Keys at the same level as `widget:` aren't part of it. A list item with a different indentation from its neighbors makes the file unreadable. The bookmarks file I tried to use had `- Newegg:` indented 5 spaces while its neighbors had 4, and Homepage couldn't parse it. Top-level settings nested under `background:` in `settings.yaml` are ignored too.

**Fix:** everything inside `widget:` is indented two more spaces:

```yaml
        widget:
          type: filebrowser
          url: http://192.168.X.X:8081
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

**Check it:** the parser prints `OK`, and after a restart the widget or bookmark group appears.

#### G9. Stat icons turn white

**Symptom:** the CPU, memory, temperature and uptime icons (or the disk and network ones) lose their colors.

**Cause:** the old color rules counted the pill's position in the header ("the second box, then the first icon"). Adding or reordering a widget shifted the count.

**Fix:** `custom.css` finds the pills as "the first stats pill" and "the second stats pill" with `:has()` rules, so it doesn't depend on position. The first rule looks like this:

```css
.widget-container:has(.information-widget-resource):not(.widget-container:has(.information-widget-resource) ~ .widget-container) .information-widget-resource:nth-of-type(1) svg { color: #4ade80 !important; } /* CPU */
```

Keep the order in `widgets.yaml` as the server stats first, then Drives.

**Check it:** the icons are colored after a hard refresh.

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

**Check it:** the pills stay on one row and the search bar sits under them.

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

**Check it:** after a hard refresh, the spacing between the pills is equal.

#### G12. Homepage cannot see the data drive

**Symptom:** the drive pill is blank or shows the boot drive.

**Cause:** the Homepage container wasn't given the drive's folder, or it started before the drive was mounted.

**Fix:** the stack needs the volume line `- /mnt/storage:/mnt/storage:ro`, and `widgets.yaml` needs `/mnt/storage` in the `disk:` list (see [Step 4](history/storage-setup-notes.md#step-4-point-each-service-at-its-folder)). Then restart it:

```bash
docker restart homepage
```

**Check it:**

```bash
docker exec homepage df -h /mnt/storage
```

It should show the data drive at about 916G.

#### G13. The Netdata card is green, but Homepage's log shows a parse error

**Symptom:** `docker logs homepage` repeats `Error calling http://192.168.X.X:19999/...` followed by `Parse Error: Data after Connection: close` every 30 seconds, while the Netdata card shows a green dot and a working widget.

**Cause:** Netdata's built-in web server answers a HEAD request with `400 Bad Request`. You can see it with `curl -sI`. A normal request works fine.

**Fix:** none is needed. The card and widget work. If the log noise bothers you, check that Netdata itself is healthy with a normal request, and remove the `siteMonitor` line from the Netdata card (you lose the status dot, and the widget still shows its alerts):

```bash
curl -sI http://192.168.X.X:19999/ | head -8
curl -s -o /dev/null -w "%{http_code}\n" http://192.168.X.X:19999/api/v1/info
```

The first prints `HTTP/1.1 400 Bad Request`. The second should print `200`.

**Check it:** the second command prints `200`, and the card still shows live numbers.

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
ssh your-username@192.168.X.X
```

Over Tailscale, use the name:

```bash
ssh your-username@pc
```

**Check it:** `sudo systemctl status ssh` shows `active (running)`.

#### H2. VS Code Remote-SSH cannot save files

**Symptom:** `Failed to save ... EACCES: permission denied`, or the folder won't open under `/var/lib/docker/volumes/`.

**Cause:** Docker's own volume folders are owned by root. Homepage's config lives in a regular folder (`/home/your-username/homepage-config`) that is shared into the container, and files copied out of a volume stay owned by root.

**Fix:** use a regular folder for the config, and take ownership of the files:

```bash
mkdir -p ~/homepage-config
sudo chown -R your-username:your-username ~/homepage-config
code -a ~/homepage-config/
```

The Homepage stack's volume line is then `/home/your-username/homepage-config:/app/config`.

**Check it:** you can save the files in VS Code.

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
autologin-user=your-username
autologin-user-timeout=0
```

**Check it:** you can connect from another computer with the AnyDesk ID and password, with no one accepting on the server.

#### H4. The remote desktop is choppy on a machine with no monitor

**Symptom:** with no monitor attached, AnyDesk is slow or the screen resolution is unstable.

**Cause:** with no display connected, the graphics hardware has nothing to draw to.

**Fix:** plug a DisplayPort dummy plug (an EDID emulator) into the mini PC. It makes the machine believe a monitor is attached, which keeps the resolution stable, lets the integrated graphics work and makes the remote desktop smooth.

**Check it:** you connect with AnyDesk and the picture is smooth at a normal resolution.

#### H5. The cheat sheet does not appear in the VS Code terminal

**Symptom:** the cheat sheet from [Step 9](history/storage-setup-notes.md#step-9-the-cheat-sheet-at-login) appeared in an SSH session from PowerShell, but not in a new terminal in VS Code Remote-SSH, on the same server.

**Cause:** my first version of the `~/.bashrc` block used a guard variable, `export HOMELAB_SHOWN=1`, so the sheet showed once per terminal. VS Code Remote-SSH reads your environment by starting a shell on the server and copying its variables into every terminal it opens. That shell ran my block, which exported `HOMELAB_SHOWN=1`, so every VS Code terminal began with the variable already set and printed nothing. In a VS Code terminal, `echo "[$HOMELAB_SHOWN]"` printed `[1]`; in a fresh SSH session it printed `[]`.

**Fix:** remove the guard variable. The block doesn't need one, because it only runs in a shell that is interactive and attached to a terminal. The background shell VS Code uses has its output captured, so the `[ -t 1 ]` test skips it.

1. Look at what is in the file now:

   ```bash
   grep -n 'homelab\|HOMELAB' ~/.bashrc
   ```

2. Remove the old block, and add the new one. If your block used the same two marker lines as in Step 9, this removes it:

   ```bash
   sed -i '/# >>> homelab login display >>>/,/# <<< homelab login display <<</d' ~/.bashrc
   ```

   Then add the block from [Step 9, part 4](history/storage-setup-notes.md#step-9-the-cheat-sheet-at-login). If `grep` still shows a line with `HOMELAB_SHOWN`, open the file with `nano ~/.bashrc` and delete that line by hand.

3. Close the VS Code terminals and open a new one. If the old variable is still set, clear it in that terminal with `unset HOMELAB_SHOWN`. If a new terminal still shows `[1]`, run **Remote-SSH: Kill VS Code Server on Host** from the Command Palette and reconnect. I didn't need that step.

**Check it:** a new VS Code terminal and a new SSH session both show the cheat sheet, `echo "[$HOMELAB_SHOWN]"` prints `[]`, and `ssh your-username@192.168.X.X "echo ok"` from PowerShell prints only `ok`. All of that was true on my server.

### I. Hardware and boot

#### I1. The mini PC won't start, and the light by the power jack flickers

**Symptom:** with a third-party 65W adapter that connects through a converter tip, the LED next to the power jack flickers on and off, the fan doesn't spin and nothing starts when you press the power button. A multimeter reads about 19.9 volts at the plug, with the center positive, which is normal for a 19.5V adapter.

**Cause:** the voltage and polarity were correct, so the charger itself wasn't the problem. HP's adapters have a small ID pin in the middle of the plug, and my best guess is that the Mini didn't accept an adapter that went through a generic converter tip without it. I couldn't confirm this from HP's documentation.

**Fix:** use a genuine HP 65W adapter with the matching 7.4mm plug. That is what fixed it. Before you blame the board, rule out the adapter: reset the power (unplug, hold the power button for 20 seconds, plug in again) and test with a genuine adapter. If a genuine adapter gives the same flicker, the board has a fault.

**Check it:** the mini PC starts and the light stays on.

#### I2. The USB stick won't boot

**Symptom:** the Ventoy stick doesn't load, or the BIOS refuses to boot it.

**Cause:** Secure Boot was on. It blocks installers that aren't signed for it.

**Fix:** press **F10** at the HP logo to open the BIOS setup, turn **Secure Boot** off in the BIOS security settings, then open **Boot Options** and choose the USB stick. In the Ventoy menu, select the Linux Mint XFCE ISO and boot it in normal mode. This is the only BIOS change I made.

**Check it:** the Linux Mint live desktop appears.

---

## Diagnostic commands

### Quick commands

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

### The inventory script

This script reads the whole setup and saves it to one file, with every secret masked. I ran it before and after the migration. It only reads settings and doesn't change anything. Create it, run it with `sudo`, skim the file for anything that looks like a real password, key or token, and then share it:

```bash
cat > ~/prodesk-full-report.sh <<'EOF'
#!/bin/bash
U=${SUDO_USER:-your-username}
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
sec "NETWORK AND DNS"; ip -4 -br addr; cat /etc/resolv.conf; ss -tulpn | grep ':53 '; ufw status 2>&1 | head -2; nslookup google.com 192.168.X.X 2>&1 | tail -4
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

## Prevention checklist

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
- [ ] If the boot drive dies, follow [Step 11](history/storage-setup-notes.md#step-11-rebuild-the-server-from-github-and-the-backup). Until `BACKUP1` exists, copy the `db-dumps` and `boot-configs` folders of the interim backup to another computer once a month.
- [ ] If a pool drive dies for good, use `sudo drives replace` ([Step 10](history/storage-setup-notes.md#step-10-replace-a-dead-drive)). I rehearsed it once with the USB stick on 2026-10-23. Don't improvise on the live pool.
- [ ] Run `sudo install` from inside the folder that holds the files ([A16](#a16-install-says-cannot-stat-when-installing-a-script)).
- [ ] Keep the `homelab` login block in `~/.bashrc` free of exported variables, or VS Code copies them into every terminal ([H5](#h5-the-cheat-sheet-does-not-appear-in-the-vs-code-terminal)).

**Deploying**

- [ ] Download images with `docker pull` before deploying stacks from GitHub's registry, one at a time.
- [ ] Deploy Immich, wait for it to turn healthy, and only then deploy Nextcloud.
- [ ] Use the exact stack names from this guide, because container names are built from them.
- [ ] Choose passwords with letters and numbers only, and write them down before deploying. Nextcloud reads them only once.
- [ ] Put a `base64:` prefix on Speedtest Tracker's app key, and change the default `admin@example.com` login.
- [ ] Give every container's data a bind-mounted folder or a named volume, never an anonymous one ([B6](#b6-a-container-starts-empty-after-update-the-stack)). Check with the `docker inspect` line in section [Diagnostic commands](#diagnostic-commands).

**Network**

- [ ] Reserve the server's address in the router.
- [ ] After a Tailscale rename or port change, check `tailscale serve status` and update Homepage's `HOMEPAGE_ALLOWED_HOSTS`, Nextcloud's overwrite settings and your apps.
- [ ] Use the local address (`192.168.X.X`), not the Tailscale one, for any step that restarts Tailscale.
- [ ] After a Tailscale update, run `nslookup github.com` on the server. If it says `SERVFAIL`, follow [F6](#f6-the-server-cannot-look-up-names-after-a-tailscale-update).
- [ ] Point each device's DNS at the server by hand if the router won't allow it, and check the AdGuard Query Log.

**Updating**

- [ ] Before any update, run `sudo homelab-backup`, wait for `finished: OK`, and update one service at a time (section [Updating services](updating.md#updating-services)).
- [ ] Run `docker pull` first and update only what says `Downloaded newer image`. Update Immich and Nextcloud on their own, never together.
- [ ] Pin Nextcloud to its major version (`nextcloud:35-apache`) so a re-pull can't start a major upgrade by surprise, and never skip a major version.
- [ ] Update Tailscale from the local address (`192.168.X.X`), and expect every container to restart when Docker Engine is updated.
- [ ] FileBrowser is no longer maintained. Keep it off the internet and keep its command runner off.

**Homepage and secrets**

- [ ] Stop Homepage before editing its keys, then start it again.
- [ ] Copy API tokens and keys with the copy button when they're first shown, and never commit real ones. Use `your-own-key` in files you publish.
- [ ] Check a YAML file with a parser before you copy it to the server and before you upload it to GitHub: `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1])); print('OK')" stacks/immich.yaml`. On 2026-10-23 I checked all nine stack files in the repository and found three that wouldn't parse: a missing closing quote in the Speedtest Tracker file, and plain-text notes after the YAML in the Immich and Nextcloud files. They are comments now.
- [ ] Keep the `.gitattributes` file in the repository. The nine stack files had Windows line endings (CRLF) from the upload and are plain LF now; the file keeps them that way.
- [ ] After editing a Homepage file, restart it and hard-refresh the browser.
