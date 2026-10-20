# Home Lab Troubleshooting Guide

Everything here comes from a real build and the problems that came up while building it. The first section is the storage setup that works. Everything after it is a list of problems, each with the symptom, the cause, the exact commands that fixed it, and how to check that it worked.

**Conventions**

- Server: a Lenovo Yoga 6 13ALC6 running Linux Mint, user `brandon`, LAN address `192.168.1.93`.
- Tailscale name: `home.griffin-luma.ts.net`.
- Anything secret (passwords, API keys, tokens) is written as `your-own-key`.
- Drive letters change. The main HDD has been `sda` and `sdb` on different days. Replace `sdX` or `sdb` with your drive's current letter, and rely on the label (`STORAGE`) or the UUID for anything permanent.

## Table of Contents

1. [Setup at a glance](#1-setup-at-a-glance)
1. [Storage setup that works](#2-storage-setup-that-works)
   - [Step 1: Reformat the HDD](#step-1-reformat-the-hdd)
   - [Step 2: Make the mount permanent](#step-2-make-the-mount-permanent)
   - [Step 3: Create a folder for each service](#step-3-create-a-folder-for-each-service)
   - [Step 4: Point each service at its folder](#step-4-point-each-service-at-its-folder)
   - [Step 5: hdparm and cron lines](#step-5-hdparm-and-cron-lines)
   - [Step 6: The hdd-recover script](#step-6-the-hdd-recover-script)
   - [Step 7: Verify it](#step-7-verify-it)
   - [How the widgets see the drive](#how-the-widgets-see-the-drive)
   - [Cleanup note: leftovers from the old setup](#cleanup-note-leftovers-from-the-old-setup)
1. [Troubleshooting](#3-troubleshooting)
   - [A. Drives and storage](#a-drives-and-storage)
   - [B. Docker and Portainer](#b-docker-and-portainer)
   - [C. FileBrowser](#c-filebrowser)
   - [D. Nextcloud](#d-nextcloud)
   - [E. Tailscale](#e-tailscale)
   - [F. AdGuard Home and DNS](#f-adguard-home-and-dns)
   - [G. Homepage](#g-homepage)
   - [H. Remote access](#h-remote-access)
1. [Diagnostic commands](#4-diagnostic-commands)
1. [Prevention checklist](#5-prevention-checklist)

---

## 1. Setup at a glance

| Service | Container name | Local port | Tailscale address | Where its data lives |
| :--- | :--- | :--- | :--- | :--- |
| FileBrowser | `filebrowser-filebrowser-1` | 8081 | `https://home.griffin-luma.ts.net` | HDD: `/mnt/storage/filebrowser` shown as `/srv/hdd`; SSD: `/home/brandon/256GB_SSD` shown as `/srv/ssd` |
| Nextcloud | `nextcloud`, `nextcloud_db`, `nextcloud_redis`, `nextcloud_cron` | 8082 | `https://home.griffin-luma.ts.net:8441` | Files on the HDD: `/mnt/storage/nextcloud`; app files and database on the SSD: `/home/brandon/nextcloud` |
| Speedtest Tracker | `speedtest-tracker` | 8088 | `https://home.griffin-luma.ts.net:8442` | Docker volume |
| AdGuard Home | `adguardhome` (host network) | 3000 web, 53 DNS | `https://home.griffin-luma.ts.net:8443` | `/opt/adguard-docker` |
| Beszel hub and agent | `beszel`, `beszel-agent` | 8090 | `https://home.griffin-luma.ts.net:8444` | Docker volume |
| Immich | `immich_server`, `immich_postgres`, `immich_machine_learning`, `immich_redis` | 2283 | `https://home.griffin-luma.ts.net:8445` | Photos on the HDD: `/mnt/storage/immich`; database on the SSD: `/home/brandon/immich/postgres` |
| Netdata | `netdata-netdata-1` | 19999 | `https://home.griffin-luma.ts.net:8446` | Docker volumes (no Homepage card yet) |
| Homepage | `homepage` | 3001 | `https://home.griffin-luma.ts.net:8447` | `/home/brandon/homepage-config` |
| Portainer | `portainer` | 9000 (HTTP), 9443 | `https://home.griffin-luma.ts.net:9444` | Docker volume `portainer_data` |

Two drives are used:

| Drive | Size | Used for |
| :--- | :--- | :--- |
| Internal SSD (`nvme0n1`) | 238G | The OS, Docker, databases, app files, config |
| External 1TB HDD (Toshiba MQ01ABD100) | 916G usable | Photos, Nextcloud files, FileBrowser files. ext4, label `STORAGE`, mounted at `/mnt/storage` |

---

## 2. Storage setup that works

Goal: the HDD keeps the same label, format and path after a reboot or a disconnect. Each service has its own folder on it, and Homepage, FileBrowser, Immich and Nextcloud all see the drive correctly.

**Why ext4:** it's a Linux filesystem, so Docker and databases get proper file permissions, and it isn't locked as "dirty" when the drive is unplugged the way NTFS can be.

### Step 1: Reformat the HDD

Unplug any other external drives first so you can't pick the wrong one. Find the drive and confirm it's the right one:

```
lsblk -o NAME,SIZE,MODEL,TRAN,FSTYPE,LABEL,MOUNTPOINTS
sudo smartctl -i -d sat /dev/sdX | grep -E "Device Model|Serial"
```

It should be about 931G and say `TOSHIBA MQ01ABD100`. Then wipe and format it. **This erases everything on the drive:**

```
sudo umount /dev/sdX1 /dev/sdX2 2>/dev/null
sudo wipefs -a /dev/sdX
sudo parted /dev/sdX --script mklabel gpt mkpart storage ext4 1MiB 100%
sudo partprobe /dev/sdX; sleep 2
sudo wipefs -a /dev/sdX1
sudo mkfs.ext4 -L STORAGE -m 0 /dev/sdX1
```

`-L STORAGE` sets the permanent label. `-m 0` turns off the 5% of space ext4 reserves by default.

### Step 2: Make the mount permanent

**1. Create the mount point and lock it.** Do this while the drive is not mounted:

```
sudo mkdir -p /mnt/storage
sudo chattr +i /mnt/storage
```

The lock means that if the drive is ever missing, nothing can write into the empty folder. Services fail with an error instead of silently filling the SSD.

**2. Replace the old fstab line and add the new one.** The old NTFS line used the UUID `527CF30D7CF2EA9D`:

```
sudo sed -i '/527CF30D7CF2EA9D/d' /etc/fstab
NEWUUID=$(sudo blkid -s UUID -o value /dev/sdX1)
echo "UUID=$NEWUUID  /mnt/storage  ext4  defaults,noatime,nofail,x-systemd.device-timeout=10  0  2" | sudo tee -a /etc/fstab
sudo umount /media/brandon/STORAGE 2>/dev/null
sudo systemctl daemon-reload
sudo mount -a
findmnt /mnt/storage
```

My current line in `/etc/fstab`:

```
UUID=0f029dec-c289-4d9a-b893-8ea5ef2817bc  /mnt/storage  ext4  defaults,noatime,nofail,x-systemd.device-timeout=10  0  2
```

`nofail` lets the computer boot even if the drive isn't plugged in.

**3. Make Docker wait for the drive at boot:**

```
sudo mkdir -p /etc/systemd/system/docker.service.d
printf '[Unit]\nWants=mnt-storage.mount\nAfter=mnt-storage.mount\n' | sudo tee /etc/systemd/system/docker.service.d/wait-for-hdd.conf
sudo systemctl daemon-reload
```

### Step 3: Create a folder for each service

```
sudo mkdir -p /mnt/storage/immich /mnt/storage/filebrowser
sudo chown -R brandon:brandon /mnt/storage
sudo mkdir -p /mnt/storage/nextcloud
sudo chown -R 33:33 /mnt/storage/nextcloud
mkdir -p /home/brandon/nextcloud/html /home/brandon/nextcloud/db
```

UID 33 is the user Nextcloud runs as inside its container (it shows up as `www-data` in `ls -la`). The Nextcloud database and app files stay on the SSD, only its files go on the HDD.

If the HDD was wiped and Immich should start fresh, Immich's database still lists the old photos. Stop the Immich stack in Portainer first. **This deletes the Immich accounts and database:**

```
sudo rm -rf /home/brandon/immich/postgres /home/brandon/immich-ssd-copy
mkdir -p /home/brandon/immich/postgres
```

### Step 4: Point each service at its folder

| Service | Where it points | Folder |
| :--- | :--- | :--- |
| Immich | Environment variable `UPLOAD_LOCATION` | `/mnt/storage/immich` |
| Immich database | Environment variable `DB_DATA_LOCATION` | `/home/brandon/immich/postgres` (SSD) |
| FileBrowser | Volume line, shown as `/srv/hdd` | `/mnt/storage/filebrowser` |
| Nextcloud | Volume line, shown as `/data` | `/mnt/storage/nextcloud` |
| Homepage | Volume line and the `widgets.yaml` disk list | `/mnt/storage` |

**Immich**: environment variables in the Portainer stack (your other Immich variables stay as they are):

```
UPLOAD_LOCATION=/mnt/storage/immich
DB_DATA_LOCATION=/home/brandon/immich/postgres
DB_PASSWORD=your-own-key
```

**FileBrowser**: the volumes in its stack:

```yaml
    volumes:
      - "/home/brandon/256GB_SSD:/srv/ssd"
      - "/mnt/storage/filebrowser:/srv/hdd"
      - filebrowser_data:/database
```

**Nextcloud**: the data folder and its volumes. The data folder is set once with `NEXTCLOUD_DATA_DIR: /data` and can't be changed after the first install:

```yaml
    environment:
      NEXTCLOUD_DATA_DIR: /data
    volumes:
      - /home/brandon/nextcloud/html:/var/www/html
      - /mnt/storage/nextcloud:/data
```

**Homepage**: the volumes in its stack, then the disk list in `widgets.yaml`:

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

### Step 5: hdparm and cron lines

The drive is a laptop drive that parks its heads aggressively at the default power setting. This changes it and keeps it that way after a reboot:

```
sudo hdparm -B 254 /dev/sdX
sudo hdparm -B /dev/sdX
sudo crontab -e
```

The second command should print `APM_level = 254`. My root crontab has these two lines. The first re-applies the setting after every reboot, and the second logs the head-parking count every morning:

```
@reboot sleep 60 && /usr/sbin/hdparm -S 0 -B 254 "/dev/$(lsblk -no pkname "$(readlink -f /dev/disk/by-label/STORAGE)")"
0 6 * * * echo "$(date +\%F) $(smartctl -A -d sat /dev/disk/by-label/STORAGE | awk '/Load_Cycle/ {print $10}')" >> /var/log/loadcycles.log
```

Both lines find the drive by its label, so they still work when its letter changes. `-S 0` means the drive never spins down. That's right for a drive that Immich and Nextcloud touch constantly.

### Step 6: The hdd-recover script

Containers keep the view of the drive they had when they started. If the drive is unplugged and plugged back in, they need a restart. This script stops them, remounts the drive, re-applies the power setting and starts them again.

My current script on the server stops and starts three containers:

```
#!/bin/bash
docker stop immich_server filebrowser-filebrowser-1 homepage
umount -l /mnt/storage 2>/dev/null; sleep 2
mount /mnt/storage || { echo "Drive not found. Check the cable."; exit 1; }
hdparm -S 0 -B 254 "/dev/$(lsblk -no pkname "$(readlink -f /dev/disk/by-label/STORAGE)")" 2>/dev/null
docker start immich_server filebrowser-filebrowser-1 homepage
echo "Recovered."
```

**Nextcloud also uses the HDD, so add its two containers** (`nextcloud` and `nextcloud_cron`) to both the `docker stop` line and the `docker start` line. Re-create the script with the longer lists:

```
sudo tee /usr/local/bin/hdd-recover >/dev/null <<'EOF'
#!/bin/bash
docker stop immich_server filebrowser-filebrowser-1 homepage nextcloud nextcloud_cron
umount -l /mnt/storage 2>/dev/null; sleep 2
mount /mnt/storage || { echo "Drive not found. Check the cable."; exit 1; }
hdparm -S 0 -B 254 "/dev/$(lsblk -no pkname "$(readlink -f /dev/disk/by-label/STORAGE)")" 2>/dev/null
docker start immich_server filebrowser-filebrowser-1 homepage nextcloud nextcloud_cron
echo "Recovered."
EOF
sudo chmod +x /usr/local/bin/hdd-recover
```

After you reconnect the drive at any time, run `sudo hdd-recover`.

### Step 7: Verify it

Start the Immich, FileBrowser, Nextcloud and Homepage stacks, then check that each container sees the HDD:

```
findmnt /mnt/storage
docker exec immich_server df -h /data
docker exec filebrowser-filebrowser-1 df -h /srv/hdd
docker exec nextcloud df -h /data
docker exec homepage df -h /mnt/storage
```

Every container should show your HDD (`/dev/sdb1`, about 916G). If one shows the SSD (`nvme0n1p2`), that container was started before the drive was mounted, so restart it.

Then run these tests:

- **Reboot:** run `sudo reboot`. After two minutes, run `findmnt /mnt/storage` and `docker ps`. The drive should be mounted and the containers running with no help from you.
- **Unplug:** unplug the drive, wait a few seconds, plug it back in and run `sudo hdd-recover`. You should see `Recovered.`
- **Optional lock test:** with the stacks stopped, run `sudo umount /mnt/storage`, then `touch /mnt/storage/test`. It should say `Operation not permitted`, which shows nothing can write to the empty folder. Then run `sudo mount /mnt/storage` and start the stacks again. `lsattr` can't show the lock while the drive is mounted, because the flag sits on the hidden folder underneath.

### How the widgets see the drive

- **Homepage drive pill:** it reads `/mnt/storage` inside the Homepage container through the `/mnt/storage:/mnt/storage:ro` volume. If it goes blank after a replug, restart Homepage.
- **Immich storage meter (bottom left of its web page):** it shows the disk that holds the photo folder (`/data`). It shows the HDD only while the drive is mounted.
- **Nextcloud card (`freespace`):** it reports the drive that holds the data folder, so it shows the HDD.
- **FileBrowser card:** FileBrowser reports the drive of the login's folder, and the admin login sees `/srv`, which is on the SSD. The card shows SSD numbers. To make a card show the HDD, see [C3](#c3-filebrowser-card-shows-ssd-numbers-optional-hdd-card).

### Cleanup note: leftovers from the old setup

These are left over from an earlier attempt and are not used. The `fstab` line points at a drive that doesn't exist (harmless because of `nofail`), the `/mnt/immich` folder is empty, and `/mnt/immich-photos` is a broken link to the old NTFS path. First check that nothing is using them:

```
findmnt /mnt/immich
ls -la /mnt/immich
```

The first command should print nothing and the folder should be empty. Then remove them (these commands are new, not from the earlier steps):

```
sudo sed -i '/a56b4cd1-8bd3-4e6a-b8d0-71d92462f2a9/d' /etc/fstab
sudo rm /mnt/immich-photos
sudo rmdir /mnt/immich
sudo systemctl daemon-reload
```

`rmdir` refuses to delete a folder that isn't empty, so it can't remove data by mistake. Check the result with `grep -v '^#' /etc/fstab`.

---

## 3. Troubleshooting

Each entry has the same four parts: Symptom, Cause, Fix and Verify.

### A. Drives and storage

#### A1. HDD comes back under a different path after a replug

**Symptom:** after unplugging and replugging the drive, FileBrowser can't see it and the Homepage drive pill is blank.

**Cause:** the desktop mounts external drives under `/media/brandon/<label>`. The label path (`1TB HDD`) was not the path the stacks used (`USB STICK`). Containers also keep the old view of the drive.

**Fix:** with the setup in section 2, run:

```
sudo hdd-recover
```

Before the fixed mount existed, this was the manual fix:

```
lsblk -f
ls /media/brandon/
sudo mount -t ntfs-3g -o uid=1000,gid=1000 /dev/sdb2 "/media/brandon/USB STICK"
docker restart filebrowser-filebrowser-1 homepage
```

**Verify:** `findmnt /mnt/storage` shows the drive, and the `df` checks from [Step 7](#step-7-verify-it) show the HDD in each container.

#### A2. sdb1 vs sdb2 and the wrong filesystem type error

**Symptom:** mounting fails with `wrong fs type, bad option, bad superblock on /dev/sdb1`.

**Cause:** the drive was formatted by Windows. Its first partition (`sdb1`) is a small one with no filesystem, and the data is on `sdb2`.

**Fix:** list the partitions and mount the one that shows a filesystem:

```
lsblk -f
sudo mount -t ntfs-3g -o uid=1000,gid=1000 /dev/sdb2 "/media/brandon/USB STICK"
```

If `ntfsfix` says `Refusing to operate on read-write mounted device`, ignore it. `ntfsfix` only works on an unmounted drive, and it's only needed if the mount itself fails with a "dirty" message.

**Verify:** `ls "/media/brandon/USB STICK"` lists your files.

#### A3. Mount refused because the NTFS volume is already exclusively opened

**Symptom:** `Mount is denied because the NTFS volume is already exclusively opened.`

**Cause:** the desktop had already mounted the drive at `/media/brandon/1TB HDD`, so mounting it a second time at another path is refused. The `USB STICK` folder was then an empty folder on the SSD, and anything written there went to the SSD.

**Fix:** unmount the desktop's copy and mount the drive from `/etc/fstab` at the fixed path:

```
findmnt "/media/brandon/USB STICK"
sudo umount "/media/brandon/1TB HDD"
sudo systemctl daemon-reload
sudo mount -a
findmnt "/media/brandon/USB STICK"
```

The first command should print nothing (the folder was not mounted). The last one should show `/dev/sdb2`. The ext4 setup in section 2 avoids this problem by mounting at `/mnt/storage`.

**Verify:** `findmnt` shows the drive at the fixed path.

#### A4. Immich database keeps restarting on an NTFS drive

**Symptom:** in Portainer, `immich_postgres` and `immich_server` keep restarting. The same stack worked when the folder was on the internal SSD.

**Cause:** the database folder was on the NTFS drive. Postgres needs a Linux filesystem so it can set file owners and permissions on its data.

**Fix:** keep the database on the SSD and only the photos on the HDD. In the stack's environment variables:

```
UPLOAD_LOCATION=/mnt/storage/immich
DB_DATA_LOCATION=/home/brandon/immich/postgres
```

```
mkdir -p /home/brandon/immich/postgres
```

If a half-built database was left on the HDD, delete only the folder you created for it. Don't delete anything else. The spin-down setting can also cause slow starts and failed health checks, so turn it off:

```
sudo hdparm -S 0 /dev/sdb
```

**Verify:**

```
docker ps
docker logs immich_postgres --tail 20
docker logs immich_server --tail 20
```

Both containers should show `healthy` or `Up`.

#### A5. Immich is writing to the SSD because the HDD was not mounted

**Symptom:** Immich's storage meter shows the SSD size, `docker exec immich_server df -h /data` shows `nvme0n1p2`, and `findmnt -T` on the photo folder shows `/`.

**Cause:** the folder was created, or the stack was started, while the HDD wasn't mounted. The folder was then created on the SSD.

**Fix:** stop the Immich stack in Portainer, mount the drive, copy the photos over and start the stack. These were the commands on the old NTFS setup:

```
sudo mv "/media/brandon/USB STICK/1TB HDD/immich" /home/brandon/immich-ssd-copy
mkdir -p "/media/brandon/USB STICK/1TB HDD/immich"
rsync -rt --no-perms --no-owner --no-group --info=progress2 /home/brandon/immich-ssd-copy/ "/media/brandon/USB STICK/1TB HDD/immich/"
du -sh /home/brandon/immich-ssd-copy "/media/brandon/USB STICK/1TB HDD/immich"
```

The two sizes should match. Once Immich shows your photos from the HDD, free the SSD space with `sudo rm -rf /home/brandon/immich-ssd-copy`. The lasting fix is the locked mount point and the Docker wait rule from [Step 2](#step-2-make-the-mount-permanent).

**Verify:**

```
docker exec immich_server df -h /data
findmnt -T /mnt/storage/immich
```

The first should show about 916G on the HDD, and the second should show the HDD as its source.

#### A6. Containers show an old or empty drive after an unplug

**Symptom:** the drive is mounted again, but Immich, FileBrowser, Nextcloud or Homepage still show an empty folder or no space.

**Cause:** a container keeps the mount it had when it started.

**Fix:**

```
sudo hdd-recover
```

To do it by hand: stop the stacks, run `sudo umount /mnt/storage`, plug the drive back in, run `sudo mount /mnt/storage` and start the stacks. Before you unplug the drive, always stop the stacks first and run `sudo umount /mnt/storage`.

**Verify:** the `df` commands in [Step 7](#step-7-verify-it) show the HDD in each container.

#### A7. Containers start before the drive is mounted after a reboot

**Symptom:** after a reboot, a container shows the SSD or an empty folder, or fails to start.

**Cause:** Docker started containers before the drive was mounted.

**Fix:** add the wait rule if it's missing (it's in [Step 2](#step-2-make-the-mount-permanent)):

```
sudo mkdir -p /etc/systemd/system/docker.service.d
printf '[Unit]\nWants=mnt-storage.mount\nAfter=mnt-storage.mount\n' | sudo tee /etc/systemd/system/docker.service.d/wait-for-hdd.conf
sudo systemctl daemon-reload
```

If the drive is missing at boot, the locked mount point makes the services fail with an error, and they don't write to the SSD. Plug the drive in and run `sudo hdd-recover`.

**Verify:** after `sudo reboot`, run `findmnt /mnt/storage` and `docker ps`.

#### A8. Head-parking count is high

**Symptom:** the SMART `Load_Cycle_Count` is high and climbing (mine was 105,642), and `hdparm -B` shows `APM_level = 128`.

**Cause:** at level 128, laptop drives park their heads after a few seconds of idle. Many are rated for about 300,000 parks.

**Fix:**

```
sudo smartctl -A -d sat /dev/sdb | grep -E "Power_On_Hours|Load_Cycle|Reallocated_Sector|Current_Pending"
sudo hdparm -B /dev/sdb
sudo hdparm -B 254 /dev/sdb
sudo hdparm -B /dev/sdb
```

The last command should print `APM_level = 254`. The `SG_IO: bad/missing sense data` messages are common with USB adapters and can be ignored. Keep the setting after reboots with the cron lines from [Step 5](#step-5-hdparm-and-cron-lines). If the count still climbs by hundreds a day, try `sudo hdparm -B 255 /dev/sdb`.

**Verify:** after a few days, check `cat /var/log/loadcycles.log`. A rise of under about 50 a day means the fix is working. Mine went from 105,644 to 105,744 in three days.

#### A9. Cron job logs a date with no number

**Symptom:** `/var/log/loadcycles.log` has a date but no count after it.

**Cause:** cron runs with a short search path that doesn't include `/usr/sbin`, where `smartctl` lives.

**Fix (only if the number is blank):** add this as the first line of root's crontab:

```
sudo crontab -e
```

```
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

**Verify:** `sudo crontab -l` shows the line, and `cat /var/log/loadcycles.log` has a number after tomorrow's date.

### B. Docker and Portainer

#### B1. Docker installs from the wrong repository on Mint

**Symptom:** the install stops with `containerd.io : Depends: libseccomp2 (>= 2.6.0)` and `E: Unable to correct problems, you have held broken packages`.

**Cause:** Docker's install script detected the system as Debian `trixie`. Mint is based on Ubuntu, and Docker's repository needs the Ubuntu name (`noble` for Mint 22).

**Fix:**

```
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

```
sudo usermod -aG docker $USER
sudo reboot
```

To test without rebooting, run `newgrp docker`.

**Verify:** `groups` lists `docker`, and `docker run hello-world` prints `Hello from Docker!`.

#### B3. Container names differ from the stack name

**Symptom:** `Error response from daemon: No such container: filebrowser`.

**Cause:** Portainer names containers from a stack as `<stack>-<service>-<number>`. Containers with a fixed `container_name` (like `immich_server` and `nextcloud`) keep that name.

**Fix:** find the real name and use it:

```
docker ps -a | grep -i filebrowser
docker logs filebrowser-filebrowser-1
```

**Verify:** the command prints the container's output instead of an error.

#### B4. Portainer asks for a setup token

**Symptom:** a new Portainer asks for a setup token before it lets you create an admin account.

**Cause:** Portainer protects a fresh install until you claim it.

**Fix:**

```
docker logs portainer
```

Look near the top for the token. Paste it into the page, then create your admin account.

**Verify:** you can log in and see the local environment.

### C. FileBrowser

#### C1. Login rejected

**Symptom:** `admin` / `admin` gives "wrong credentials."

**Cause:** newer FileBrowser images can generate a random password on first start, so the default may not apply. I don't remember which fix worked, so these are the steps used to diagnose it.

**Fix:**

```
docker ps
docker logs filebrowser-filebrowser-1
docker logs filebrowser-filebrowser-1 | grep -i password
```

Use the generated password if one is printed. If the container isn't running or healthy, the logs show why (a bad volume path is the usual cause). If it's still stuck, delete the stack in Portainer and deploy it again with the same YAML for a fresh database. After you log in, change the password right away.

**Verify:** you can log in at `http://192.168.1.93:8081`.

#### C2. HDD folder is empty because of a folder name mismatch

**Symptom:** FileBrowser shows an empty `hdd` folder.

**Cause:** the stack pointed at `1TB_HDD` (with an underscore) but the real folder was `1TB HDD` (with a space). Paths with spaces also need quotes in the YAML.

**Fix:** the volume line must match the real folder and be quoted:

```yaml
      - "/media/brandon/USB STICK/1TB HDD:/srv/hdd"
```

My current stack avoids spaces entirely:

```yaml
      - "/mnt/storage/filebrowser:/srv/hdd"
```

**Verify:**

```
ls "/mnt/storage/filebrowser"
docker exec filebrowser-filebrowser-1 df -h /srv/hdd
```

#### C3. FileBrowser card shows SSD numbers (optional HDD card)

**Symptom:** the FileBrowser card on Homepage shows the SSD's numbers.

**Cause:** the card reports the drive of the login's folder, and the admin login's folder is `/srv`, which is on the SSD.

**Fix (optional):** this is not part of my current setup, which shows the HDD's space in the drive pill. To get a card for the HDD, make a second FileBrowser login limited to the HDD folder. In FileBrowser, go to Settings, then User Management, and add a user named `homepage` with a password of at least 12 characters. Set **Scope** to `/hdd` and turn off all its permissions. Then add a card to `services.yaml`:

```yaml
    - FileBrowser (HDD):
        id: filebrowser-hdd-card
        href: https://home.griffin-luma.ts.net/files/hdd
        siteMonitor: http://192.168.1.93:8081
        icon: filebrowser.png
        description: 1TB storage drive
        widget:
          type: filebrowser
          url: http://192.168.1.93:8081
          username: homepage
          password: your-own-key
```

The card gets no colored accent until `#filebrowser-hdd-card` is added to the accent selectors in `custom.css`.

**Verify:** after `docker restart homepage`, the new card shows the HDD's available and total space.

### D. Nextcloud

#### D1. Access through untrusted domain

**Symptom:** Nextcloud says "Access through untrusted domain."

**Cause:** the address you're using isn't in Nextcloud's trusted domain list. The `NEXTCLOUD_TRUSTED_DOMAINS` variable is only read on the first install.

**Fix:** add the domain with `occ`. Use an index number that isn't used yet:

```
docker exec -u www-data nextcloud php occ config:system:get trusted_domains
docker exec -u www-data nextcloud php occ config:system:set trusted_domains 3 --value=home.griffin-luma.ts.net
```

Because the stack sets `OVERWRITEHOST` and `OVERWRITEPROTOCOL`, log in with the Tailscale address. The local `192.168.1.93:8082` address redirects to it.

**Verify:** the first command lists the new domain, and the Tailscale address loads the login page.

#### D2. Cannot write to the data directory

**Symptom:** the first start fails with a message that Nextcloud can't create or write to the data directory.

**Cause:** the data folder on the HDD isn't owned by the user Nextcloud runs as (UID 33, `www-data`).

**Fix:**

```
sudo chown -R 33:33 /mnt/storage/nextcloud
```

Then restart the stack.

**Verify:**

```
ls -la /mnt/storage/nextcloud
docker exec nextcloud df -h /data
```

The folder shows `www-data` as the owner, and `/data` shows the HDD.

#### D3. Homepage dot shows HTTP status 500

**Symptom:** the Nextcloud dot on Homepage is red and says status 500, even though you can log in. The Nextcloud logs show no errors (the monitor's `GET /` gets a `302`).

**Cause:** the monitor was checking `/`, which redirects to the login page.

**Fix:** monitor a page that answers directly. In `services.yaml`:

```yaml
        siteMonitor: http://192.168.1.93:8082/status.php
```

Check it, then restart Homepage:

```
curl -I http://192.168.1.93:8082/status.php
docker restart homepage
```

The first line should be `HTTP/1.1 200 OK`. If it says `400`, add the address as a trusted domain and try again:

```
docker exec -u www-data nextcloud php occ config:system:set trusted_domains 4 --value=192.168.1.93:8082
```

**Verify:** the dot turns green. If it doesn't, check what Homepage saw:

```
docker logs homepage --tail 40 | grep -i -E "nextcloud|8082|monitor|error"
```

#### D4. Immich integration says local IP blocked

**Symptom:** Nextcloud's Immich integration says `Connection failed: local IP blocked by Nextcloud`.

**Cause:** Nextcloud refuses requests to private addresses (like 192.168.x.x and Tailscale addresses) by default.

**Fix:**

```
docker exec -u www-data nextcloud php occ config:system:set allow_local_remote_servers --value=true --type=boolean
docker exec -u www-data nextcloud php occ config:system:get allow_local_remote_servers
```

In the integration settings, use the base address `http://192.168.1.93:2283`. Don't add `/photos` to the end, because that's a page in Immich's web app. Create the API key in Immich under Account Settings, then API Keys.

**Verify:** the second command prints `true`, and Test connection succeeds.

#### D5. 502 right after deploying

**Symptom:** the Tailscale address shows a 502 error after the stack was first deployed.

**Cause:** Nextcloud takes 2-5 minutes to install on its first start. Apache isn't ready yet.

**Fix:** watch it, then refresh the page:

```
docker logs -f nextcloud
```

Press `Ctrl+C` when the install finishes.

**Verify:** the login page loads.

### E. Tailscale

#### E1. 502 on Portainer through Tailscale Serve

**Symptom:** the Portainer address on Tailscale shows `HTTP ERROR 502`.

**Cause:** Portainer's HTTPS port (9443) uses a self-signed certificate that Tailscale won't proxy to. It also serves plain HTTP on port 9000, but that port wasn't published.

**Fix:** recreate the container with port 9000 published (your data stays in the `portainer_data` volume), then point Tailscale at it:

```
docker stop portainer
docker rm portainer
docker run -d -p 9443:9443 -p 9000:9000 --name portainer --restart=always -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer-ce:latest
sudo tailscale serve --https=9444 off
sudo tailscale serve --bg --https=9444 http://192.168.1.93:9000
```

**Verify:** `https://home.griffin-luma.ts.net:9444` loads.

#### E2. tailscale serve says the CLI has changed

**Symptom:** `Error: the CLI for serve and funnel has changed.`

**Cause:** newer Tailscale versions use a different command format.

**Fix:** use `--bg` and put the port in the `--https` option:

```
sudo tailscale serve --bg http://192.168.1.93:8081
sudo tailscale serve --bg --https=8445 http://192.168.1.93:2283
```

To remove one: `sudo tailscale serve --https=8445 off`.

**Verify:** `tailscale serve status` lists the address.

#### E3. Path-based serving breaks apps

**Symptom:** with addresses like `/files` and `/adguard` on one port, the apps load blank or with broken links.

**Cause:** these apps assume they live at the root of the address (`/`).

**Fix:** go back to one HTTPS port per service. This clears everything and sets the current list again:

```
sudo tailscale serve reset
sudo tailscale serve --bg http://192.168.1.93:8081
sudo tailscale serve --bg --https=8441 http://192.168.1.93:8082
sudo tailscale serve --bg --https=8442 http://192.168.1.93:8088
sudo tailscale serve --bg --https=8443 http://192.168.1.93:3000
sudo tailscale serve --bg --https=8444 http://192.168.1.93:8090
sudo tailscale serve --bg --https=8445 http://192.168.1.93:2283
sudo tailscale serve --bg --https=8446 http://192.168.1.93:19999
sudo tailscale serve --bg --https=8447 http://192.168.1.93:3001
sudo tailscale serve --bg --https=9444 http://192.168.1.93:9000
```

**Verify:** `tailscale serve status` lists nine entries, and each address loads.

#### E4. Tailnet name changed

**Symptom:** after the tailnet name changed from `tail30c3e5.ts.net` to `griffin-luma.ts.net`, links and logins stopped working.

**Cause:** the old name was written into several configs.

**Fix:** update the name in each place:

- Homepage's `services.yaml` (the `href:` links) and the `HOMEPAGE_ALLOWED_HOSTS` line in the Homepage stack.
- The Nextcloud stack's `OVERWRITEHOST` and `OVERWRITECLIURL` lines.
- Nextcloud's trusted domains:

```
docker exec -u www-data nextcloud php occ config:system:set trusted_domains 3 --value=home.griffin-luma.ts.net
```

- The server address in your phone and desktop apps.

**Verify:** `tailscale serve status` shows the new name, and every address loads.

#### E5. Name will not resolve from another computer

**Symptom:** `DNS_PROBE_POSSIBLE` or "DNS address could not be found" when opening a Tailscale address.

**Cause:** that computer isn't connected to Tailscale, so it can't look up the name.

**Fix:** open the Tailscale app on that computer and make sure it says **Connected**. If it shows signed in but not connected, quit and reopen the app, or log out and back in. Then test:

```
nslookup home.griffin-luma.ts.net
```

**Verify:** the lookup returns an address starting with `100.`.

#### E6. 502 when proxying a service on another machine

**Symptom:** a Tailscale address shows 502 even though the service works locally.

**Cause:** the Tailscale entry pointed at the wrong machine's address. At one point AdGuard was on a different computer.

**Fix:** check that the Lenovo can reach the address, then redo the entry with the right one:

```
curl -v http://192.168.1.93:3000
sudo tailscale serve --https=8443 off
sudo tailscale serve --bg --https=8443 http://192.168.1.93:3000
```

**Verify:** `tailscale serve status` shows the right target, and the address loads.

### F. AdGuard Home and DNS

AdGuard Home runs as a Docker container with `network_mode: host`, so it uses ports 53 and 3000 on the machine directly.

#### F1. Port 53 conflict with systemd-resolved

**Symptom:** AdGuard says port 53 is already in use, and `sudo ss -tulpn | grep :53` shows `systemd-resolve`.

**Cause:** `systemd-resolved` listens on port 53 by default. If you work around it by moving AdGuard to port 54, no device can use it, because devices only send DNS to port 53.

**Fix (what's in use now):** `systemd-resolved` is disabled. On the Lenovo, Tailscale writes `/etc/resolv.conf`, so the last two commands aren't needed there:

```
sudo systemctl disable systemd-resolved
sudo systemctl stop systemd-resolved
sudo rm /etc/resolv.conf
echo "nameserver 127.0.0.1" | sudo tee /etc/resolv.conf
```

**Fix (the other method, from the earlier native install):** keep `systemd-resolved` running and turn off only its port 53 listener:

```
sudo mkdir -p /etc/systemd/resolved.conf.d
sudo nano /etc/systemd/resolved.conf.d/adguardhome.conf
```

```
[Resolve]
DNS=127.0.0.1
DNSStubListener=no
```

```
sudo mv /etc/resolv.conf /etc/resolv.conf.backup
sudo ln -s /run/systemd/resolve/resolv.conf /etc/resolv.conf
sudo systemctl reload-or-restart systemd-resolved
```

**Verify:**

```
sudo ss -tulpn | grep :53
```

Only AdGuard Home should be listed.

#### F2. Blocklists block DNS-over-HTTPS providers

**Symptom:** AdGuard logs errors like `exchange failed upstream=https://dns10.quad9.net:443/dns-query`, and websites stop loading. `nslookup dns.cloudflare.com 127.0.0.1` returns `0.0.0.0`.

**Cause:** one of your blocklists blocks the domains of DNS providers, including the ones AdGuard uses as upstreams.

**Fix:** in AdGuard, open the Query Log and search for the machine's address or the blocked domain. Click an entry to see which list blocked it, then remove or disable that list. That's what fixed it here. Two options I didn't need: add allow rules such as `@@||dns.google^`, or switch the upstream servers to plain addresses (`1.1.1.1`, `8.8.8.8`, `9.9.9.9`). To see the errors:

```
docker logs adguardhome --tail 30
curl -v https://dns10.quad9.net:443
nslookup dns.google 127.0.0.1
```

**Verify:** `nslookup dns.google 127.0.0.1` returns a real address, not `0.0.0.0`, and the errors stop.

#### F3. Devices are not using AdGuard

**Symptom:** the AdGuard dashboard shows no clients or queries from other devices, though `nslookup` works on the server.

**Cause (check each):** devices still hold the old DNS from the router until it restarts. The address entered is the Wi-Fi address instead of the Ethernet one. AdGuard is on a different port than 53. Or the router's backup DNS is being used.

**Fix:**

```
nslookup google.com 192.168.1.93
ip addr
sudo ss -tulpn | grep :53
```

From a Windows computer, `ipconfig /all` shows which DNS server it was given (look for "DNS Servers"). The router is set to `192.168.1.93` as the primary DNS and `8.8.8.8` as the backup. A device that uses the backup skips AdGuard, so ads can come through. You can leave the backup blank if you'd rather not allow that. After changing the router, restart it (and the modem if needed) so the devices pick up the new setting. `ip addr` lists the Lenovo's address on each network card. Use the one for the connection that's actually in use (the Ethernet adapter), because the Wi-Fi card gets a different address.

**Verify:** the AdGuard Query Log shows queries from the other devices' addresses.

#### F4. NextDNS app and Tailscale on iPhone

**Symptom:** with the NextDNS app turned on, the iPhone can't reach the Tailscale addresses.

**Cause:** iOS only runs one VPN at a time. The NextDNS app and Tailscale each use a VPN slot, so they push each other out.

**Fix:** use one of them at a time. At home, AdGuard already blocks ads for the whole network. To use NextDNS with Tailscale, add it in Tailscale's DNS settings (Add nameserver, then NextDNS, with your endpoint ID) and delete the NextDNS app's profile. That setting applies to every device on the tailnet, and NextDNS's free plan has a monthly query limit. I removed this setting, and Tailscale's DNS is at its default.

**Verify:** the iPhone opens `https://home.griffin-luma.ts.net:8447` with Tailscale connected.

### G. Homepage

After you edit a Homepage file, run `docker restart homepage` and hard-refresh the browser with `Ctrl+Shift+R`.

#### G1. Host validation failed

**Symptom:** the page shows `{"error":"Host validation failed. See logs for more details."}`.

**Cause:** Homepage only answers requests for addresses it has been told about.

**Fix:** list every address you use in the Homepage stack's environment:

```yaml
    environment:
      HOMEPAGE_ALLOWED_HOSTS: 192.168.1.93:3001,home.griffin-luma.ts.net:8447,localhost:3001
```

**Verify:** `http://192.168.1.93:3001` loads.

#### G2. Port 3000 already in use

**Symptom:** the stack fails with `failed to bind host port 0.0.0.0:3000/tcp: address already in use`.

**Cause:** AdGuard Home's web page uses port 3000.

**Fix:** publish Homepage on a different port. The left number is the port on the Lenovo:

```yaml
    ports:
      - 3001:3000
```

Check what AdGuard is using with:

```
sudo ss -tulpn | grep AdGuardHome
```

**Verify:** `http://192.168.1.93:3001` loads.

#### G3. Beszel widget says No items returned

**Symptom:** `API Error: No items returned from beszel API`.

**Cause:** the widget needs the Beszel superuser login, which is separate from the regular hub login. It also needs `version: 2`.

**Fix:** reset the superuser login, test it, and make sure the widget has `version: 2`:

```
docker exec beszel /beszel superuser upsert your-email@example.com your-own-key
curl -X POST http://192.168.1.93:8090/api/collections/_superusers/auth-with-password -H "Content-Type: application/json" -d '{"identity":"your-email@example.com","password":"your-own-key"}'
docker restart homepage
```

**Verify:** the `curl` returns a token, and the widget shows your systems.

#### G4. Portainer widget says environment not found

**Symptom:** `Unable to find an environment with the specified identifier inside the database`.

**Cause:** the widget's `env:` number doesn't match your Portainer environment.

**Fix:** open Portainer, click your local environment, and read the number from the address, like `#!/endpoints/3`. Put it in `env:`. The API key comes from Portainer under your profile, then API access tokens.

```yaml
          type: portainer
          url: http://192.168.1.93:9000
          env: 3
          key: your-own-key
```

**Verify:** after `docker restart homepage`, the widget shows your container counts.

#### G5. Tailscale widget says API token invalid

**Symptom:** `API token invalid`.

**Cause:** the value pasted wasn't the whole access token. The real token starts with `tskey-api-` and has a second part after a dash. The short code ending in `CNTRL` in the list is only the token's ID. Auth keys (`tskey-auth-`) are a different thing.

**Fix:** create a new access token under API access tokens, and copy it with the copy button the moment it appears, because it's only shown once. Test it before putting it in Homepage:

```
curl -H "Authorization: Bearer your-own-key" https://api.tailscale.com/api/v2/tailnet/-/devices
```

Use the device ID that ends in `CNTRL` from the machine's page for `deviceid:`.

**Verify:** the `curl` lists your devices, and the card shows its fields.

#### G6. YAML indentation mistakes

**Symptom:** a widget doesn't appear, or a setting is ignored, with no error message.

**Cause:** YAML uses indentation for nesting. Keys that sit at the same level as `widget:` aren't part of it. Top-level settings nested under `background:` are ignored too.

**Fix:** everything inside `widget:` is indented two more spaces:

```yaml
        widget:
          type: filebrowser
          url: http://192.168.1.93:8081
          username: your-own-key
          password: your-own-key
```

In `settings.yaml`, keys like `maxGroupColumns` and `disableCollapse` go at the left edge, not under `background:`. Also, a service's `id:` must match the name used in `custom.css`, for example `id: filebrowser-card` for `#filebrowser-card`.

**Verify:** the widget shows data after a restart.

#### G7. Stat icons turn white

**Symptom:** the CPU, RAM, temperature and uptime icons (or the disk and network ones) lose their colors.

**Cause:** the old color rules counted the pill's position in the header ("the second box, then the first icon"). Adding or reordering a widget shifted the count.

**Fix:** `custom.css` now finds the pills as "the first stats pill" and "the second stats pill" with `:has()` rules, so it doesn't depend on position. The first rule looks like this:

```css
.widget-container:has(.information-widget-resource):not(.widget-container:has(.information-widget-resource) ~ .widget-container) .information-widget-resource:nth-of-type(1) svg { color: #4ade80 !important; } /* CPU */
```

Keep the order in `widgets.yaml` as the Lenovo stats first, then Drives.

**Verify:** the icons are colored after a hard refresh. The Home Lab logo pill isn't used now (the `logo` widget was removed and `custom.js` is empty), but its CSS stays in `custom.css`.

#### G8. Header wraps or overlaps at 1080p

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

#### G9. Mobile layout spacing

**Symptom:** on a phone, the pills are cramped or the search bar is too close to "Network."

**Cause:** the pills had no space between them, and the search bar has its own padding.

**Fix:** the spacing is set by variables at the top of `custom.css`. Change the numbers:

```css
:root {
  --d-search-top: 80px;
  --d-search-space: 90px;
  --m-gap: 12px;            /* space between every pill */
  --m-search-top: 12px;     /* space between the date/weather and the search*/
  --m-search-bottom: 8px;
  --m-search-pad: 10px;
}
```

The `--m-` numbers are for phones and small windows (1000px wide and under), and the `--d-` numbers are for the desktop layout.

**Verify:** after a hard refresh, the spacing between the pills is equal.

#### G10. Homepage cannot see the HDD

**Symptom:** the drive pill is blank or shows the SSD.

**Cause:** the Homepage container wasn't given the drive's folder, or it started before the drive was mounted.

**Fix:** the stack needs the volume line `- /mnt/storage:/mnt/storage:ro`, and `widgets.yaml` needs `/mnt/storage` in the `disk:` list (see [Step 4](#step-4-point-each-service-at-its-folder)). Then restart it:

```
docker restart homepage
```

**Verify:**

```
docker exec homepage df -h /mnt/storage
```

It should show the HDD at about 916G.

### H. Remote access

#### H1. SSH

**Symptom:** you can't connect with `ssh`.

**Cause:** the SSH server isn't installed or running.

**Fix:**

```
sudo apt update
sudo apt install openssh-server -y
sudo systemctl enable ssh
sudo systemctl start ssh
```

Connect from another computer:

```
ssh brandon@192.168.1.93
```

Over Tailscale, use the name instead:

```
ssh brandon@home
```

**Verify:** `sudo systemctl status ssh` shows `active (running)`.

#### H2. VS Code Remote-SSH cannot save files

**Symptom:** `Failed to save ... EACCES: permission denied`, or the folder won't open under `/var/lib/docker/volumes/`.

**Cause:** Docker's own volume folders are owned by root. Homepage's config lives in a regular folder (`/home/brandon/homepage-config`) that is shared into the container, and files copied out of a volume stay owned by root.

**Fix:** copy the config out once, share the regular folder in the stack, and take ownership of the files:

```
mkdir -p ~/homepage-config
docker run --rm -v homepage_homepage_config:/source -v ~/homepage-config:/dest alpine sh -c "cp -r /source/. /dest/"
sudo chown -R brandon:brandon ~/homepage-config
code -a ~/homepage-config/
```

The Homepage stack's volume line is then `/home/brandon/homepage-config:/app/config`.

**Verify:** you can save the files in VS Code.

#### H3. AnyDesk

**Symptom:** `anydesk` prints a GTK `cannot open display` warning, and `--set-password` doesn't ask for anything.

**Cause:** over SSH there's no screen, so the warning is harmless. Setting the password needs the AnyDesk service to be installed.

**Fix:**

```
anydesk --get-id
sudo anydesk --set-password
sudo systemctl enable anydesk
sudo systemctl start anydesk
```

Closing the lid shouldn't put the server to sleep. In `/etc/systemd/logind.conf`, set these three lines (no `#` in front of them), then restart the service. For a headless server, auto-login on boot is set under `[Seat:*]` in the lightdm config (`autologin-user=` followed by your username).

```
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
```

```
sudo systemctl restart systemd-logind
```

**Verify:** you can connect from another computer with the AnyDesk ID and password, with no one accepting on the server.

---

## 4. Diagnostic commands

```
lsblk -f                                       # drives, filesystems, labels, mount points
findmnt /mnt/storage                           # is the HDD mounted?
df -hT                                         # space used on each drive
docker ps -a                                   # all containers and their status
docker logs <container> --tail 30              # recent logs
docker exec <container> df -h /data            # which drive a container sees
tailscale serve status                         # every Tailscale address and where it points
sudo ss -tulpn | grep :53                      # who is using the DNS port
sudo smartctl -A -d sat /dev/sdb | grep -E "Power_On_Hours|Load_Cycle|Reallocated_Sector|Current_Pending"
sudo hdparm -B /dev/sdb                        # power setting (should be 254)
sudo crontab -l                                # root's scheduled jobs
cat /var/log/loadcycles.log                    # daily head-parking count
```

## 5. Prevention checklist

- [ ] Mount the HDD by UUID in `/etc/fstab` with `nofail`, at a fixed path (`/mnt/storage`).
- [ ] Lock the empty mount point with `chattr +i` before mounting.
- [ ] Keep the Docker wait-for-mount file in `/etc/systemd/system/docker.service.d/`.
- [ ] Keep databases (Immich, Nextcloud) on the SSD, and photos and files on the HDD.
- [ ] Stop the stacks and run `sudo umount /mnt/storage` before unplugging the drive.
- [ ] After any reconnect, run `sudo hdd-recover` (with the Nextcloud containers added).
- [ ] Check `cat /var/log/loadcycles.log` weekly: under about 50 a day is healthy.
- [ ] Save a copy of Nextcloud's database, since it lives on the SSD: `docker exec nextcloud_db pg_dump -U nextcloud nextcloud > /mnt/storage/nextcloud-db.sql`.
- [ ] After a Tailscale rename, check `tailscale serve status` and update Homepage's `HOMEPAGE_ALLOWED_HOSTS`, Nextcloud's overwrite settings and your apps.
- [ ] Copy API tokens and keys with the copy button when they're first shown, and never commit real ones. Use `your-own-key` in files you publish.
- [ ] After editing a Homepage file, restart it and hard-refresh the browser.



