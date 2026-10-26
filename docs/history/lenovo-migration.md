# Migration from the Lenovo to the ProDesk

> **Old notes.** This is the log from when I moved the lab from an old laptop to the current server, written at the time. Folder names, paths and image tags are from that day, so for a new build use the [build guide](../build-guide.md) or the installer. The problems I hit are in the [troubleshooting guide](../troubleshooting.md). `192.168.X.Y` is the old server's address; everything else is a placeholder.

This is how I moved my home lab from a Lenovo laptop to the HP ProDesk, in the order I did it. Phases 0 to 14 used a single data drive, so their checks show `/dev/sda1` and the label `STORAGE`. Phase 15 turned that drive into a pool, and after that the same checks show `mergerfs-main` and the label `MAIN1`. The steps here are the clean version. The problems I ran into are written up separately in [Problems and fixes](../troubleshooting.md#problems-and-fixes), and each phase links to the ones that matter.

## Phase 0: Plan and decisions

| | Old server | New server |
| :--- | :--- | :--- |
| Machine | Lenovo Yoga 6 13ALC6 laptop | HP ProDesk 600 G3 Mini |
| System | Linux Mint Cinnamon | Linux Mint 22.3 XFCE (LVM, no encryption) |
| Address | `192.168.X.Y` | `192.168.X.X` |
| Tailscale name | `home` | `pc` |
| Tailscale ports | 8441 to 8447, 9444 and 443 | 1000 to 1008 |
| Boot drive | 256GB SSD | 750GB hard drive |
| Data drive | 1TB hard drive on USB | The same 1TB drive, moved over |
| Services | The same nine | The same nine, rebuilt from scratch |

Decisions:

- **The ProDesk keeps its own address and name.** Instead of giving it the Lenovo's address, every `192.168.X.Y` in the old files became `192.168.X.X` and every `home` became `pc`. Both servers can then exist on the network at the same time.
- **Fresh start.** No databases or settings were migrated. Every service starts empty with new accounts, so there are no stale references to the old setup.
- **Renumbered Tailscale ports.** The nine services are numbered 1000 to 1008 in a fixed order: Homepage 1000, Portainer 1001, Immich 1002, Beszel 1003, AdGuard Home 1004, Nextcloud 1005, FileBrowser 1006, Speedtest Tracker 1007, Netdata 1008.
- **Drives.** The 750GB drive is the boot drive. The 1TB drive moved over, keeping its ext4 filesystem and its `STORAGE` label. Its old test data was wiped.
- **DNS.** The router wouldn't let me change its DNS setting, so each device points at the ProDesk by hand (Phase 11).
- **The Lenovo stays,** as a separate machine on the tailnet (Phase 14).

**Before you start,** the ProDesk needs Linux Mint installed, Docker and Portainer installed, SSH working, Tailscale installed and signed in, and a fixed address reserved in the router. The [build guide](../build-guide.md) covers each of those.

## Phase 1: Check the ProDesk

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

Get the wired adapter's hardware address, and reserve `192.168.X.X` for it in the router:

```bash
ip -br link show eno1
```

Run the inventory script from [The inventory script](../troubleshooting.md#the-inventory-script) once now, so you have a record of the starting point.

## Phase 2: Make the data drive permanent

The 1TB drive was already ext4 with the label `STORAGE`, so it isn't reformatted. The desktop had mounted it under `/media/your-username/STORAGE`, which isn't permanent. First check that the data is there:

```bash
ls -la /media/your-username/STORAGE
```

You should see the old folders (`filebrowser`, `immich`, `nextcloud`). If the listing is empty or looks wrong, stop. If it's right, close any file manager window that shows the drive and run:

```bash
sudo umount /media/your-username/STORAGE
sudo mkdir -p /mnt/storage
sudo chattr +i /mnt/storage
sudo cp /etc/fstab /etc/fstab.bak
echo "UUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee  /mnt/storage  ext4  defaults,noatime,nofail,x-systemd.device-timeout=10  0  2" | sudo tee -a /etc/fstab
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

The drive should be mounted and Portainer running. (This is the single-drive setup. Phase 15 later turned it into a pool, and the label `STORAGE` became `MAIN1`.) If a step went wrong, see [A1](../troubleshooting.md#a1-the-data-drive-comes-back-under-a-different-path-after-a-replug) and [A7](../troubleshooting.md#a7-containers-start-before-the-drive-is-mounted-after-a-reboot).

## Phase 3: Clear the old data and create the folders

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
sudo chown -R your-username:your-username /mnt/storage
sudo mkdir -p /mnt/storage/nextcloud
sudo chown -R 33:33 /mnt/storage/nextcloud
mkdir -p /home/your-username/nextcloud/html /home/your-username/nextcloud/db
mkdir -p /home/your-username/immich/postgres
mkdir -p /home/your-username/homepage-config
sudo mkdir -p /opt/adguard-docker/conf /opt/adguard-docker/work
mkdir -p /home/your-username/750GB_HDD
ls -la /mnt/storage /home/your-username/nextcloud /opt/adguard-docker
```

Because the paths match the old stack files, the stacks need no edits for folders. The old share `256GB_SSD` became `750GB_HDD`, since it now lives on the 750GB boot drive.

## Phase 4: Free port 53 and deploy AdGuard Home

This is the first service, because port 53 changes how the machine looks up names.

**1. Reconnect over the local network, not Tailscale,** because step 3 restarts Tailscale and would cut off a session that goes through it:

```bash
ssh your-username@192.168.X.X
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
echo "nameserver 192.168.X.1" | sudo tee /etc/resolv.conf
sudo systemctl restart tailscaled
```

**4. Check it:**

```bash
sudo ss -tulpn | grep :53
cat /etc/resolv.conf
nslookup google.com
tailscale status | head -3
```

Port 53 should no longer be held by `systemd-resolve`. `resolv.conf` should start with `# resolv.conf(5) file generated by tailscale` and show `nameserver 100.100.100.100`. The lookup should return an address, and `tailscale status` should still show the machine connected. If the lookup fails, undo it with the rollback in [F1](../troubleshooting.md#f1-port-53-conflict-with-systemd-resolved).

**A warning from later.** This worked for a month. On 2026-10-23, after Tailscale updated itself, the server couldn't look up any name while Tailscale owned `resolv.conf`. That is [F6](../troubleshooting.md#f6-the-server-cannot-look-up-names-after-a-tailscale-update).

**5. Create the stack.** In Portainer (`http://192.168.X.X:9000`), go to **Stacks**, then **Add stack**, name it `adguard`:

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

**6. Run the setup wizard** at `http://192.168.X.X:3000`. Set the admin web interface to all interfaces on port **3000** (the wizard proposes 80, so change it) and the DNS server to all interfaces on port **53**. Create your admin account. If you leave the web port at 80, the Tailscale address will show a 502 error later, see [F5](../troubleshooting.md#f5-the-adguard-web-page-shows-a-502-on-its-tailscale-address).

**7. Check that AdGuard answers:**

```bash
docker ps
sudo ss -tulpn | grep ':53 '
nslookup google.com 192.168.X.X
```

The container should be running, AdGuardHome should own port 53, and the lookup should return an address. Test the same lookup from another device. Then enable the twelve blocklists you want in AdGuard's **Filters** page. Mine are in the [build guide](../build-guide.md#63-setup-wizard).

## Phase 5: Beszel and FileBrowser

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

Open `http://192.168.X.X:8090` and create your admin account. Click **Add System**, enter a name (`ProDesk`) and the host `192.168.X.X`, stay on the **Docker** tab and click **Copy docker compose**. Keep that window open.

**Beszel agent.** Create a stack named `beszel-agent` and paste what you copied. Check that `network_mode: host` is there and that `HUB_URL` is `http://192.168.X.X:8090`:

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
      HUB_URL: http://192.168.X.X:8090
```

Deploy it, then go back to the hub window and click **Add system** at the bottom to finish. Check it:

```bash
docker logs beszel-agent | tail -n 10
```

Look for `WebSocket connected host=192.168.X.X:8090`, and a green system in the hub.

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
      - "/home/your-username/750GB_HDD:/srv/750GB_HDD"
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

The container should be `healthy`. `/srv/hdd` should show `/dev/sda1` at 915.8G, and `/srv/750GB_HDD` the boot drive. Log in at `http://192.168.X.X:8081` as `admin` with the printed password, and change it straight away. See [C1](../troubleshooting.md#c1-the-filebrowser-login-is-rejected).

## Phase 6: Tailscale addresses

Nextcloud needs its Tailscale address before you can log in, so set all nine now. Entries for services that aren't running yet show an error until those are deployed:

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
tailscale serve status
```

| Port | Service | Address |
| :--- | :--- | :--- |
| 1000 | Homepage | `https://pc.your-tailnet.ts.net:1000` |
| 1001 | Portainer | `https://pc.your-tailnet.ts.net:1001` |
| 1002 | Immich | `https://pc.your-tailnet.ts.net:1002` |
| 1003 | Beszel | `https://pc.your-tailnet.ts.net:1003` |
| 1004 | AdGuard Home | `https://pc.your-tailnet.ts.net:1004` |
| 1005 | Nextcloud | `https://pc.your-tailnet.ts.net:1005` |
| 1006 | FileBrowser | `https://pc.your-tailnet.ts.net:1006` |
| 1007 | Speedtest Tracker | `https://pc.your-tailnet.ts.net:1007` |
| 1008 | Netdata | `https://pc.your-tailnet.ts.net:1008` |

`tailscale serve status` should list nine entries. If one is wrong, see [E3](../troubleshooting.md#e3-path-based-addresses-break-apps).

## Phase 7: Immich

**1. Download the four images one at a time.** They come from GitHub's registry, which throttles parallel downloads with a `toomanyrequests` error ([B5](../troubleshooting.md#b5-toomanyrequests-from-githubs-container-registry)). If one fails, wait a minute and run that line again:

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

`DB_STORAGE_TYPE: 'HDD'` is Immich's setting for a database that isn't on an SSD, which is the case here. In **Environment variables**, in advanced mode:

```text
UPLOAD_LOCATION=/mnt/storage/immich
DB_DATA_LOCATION=/home/your-username/immich/postgres
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

All four containers should be `healthy` or `Up`, `/data` should show `/dev/sda1` at about 916G, and the folder should list `backups encoded-video library profile thumbs upload`. Open `http://192.168.X.X:2283` and create the admin account. Wait for Immich to settle before Phase 8 ([A10](../troubleshooting.md#a10-immich-and-nextcloud-overload-the-machine-when-they-start-together)).

## Phase 8: Nextcloud

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
      - /home/your-username/nextcloud/db:/var/lib/postgresql/data

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
      NEXTCLOUD_TRUSTED_DOMAINS: "192.168.X.X pc.your-tailnet.ts.net"
      OVERWRITEPROTOCOL: https
      OVERWRITEHOST: pc.your-tailnet.ts.net:1005
      OVERWRITECLIURL: https://pc.your-tailnet.ts.net:1005
      TRUSTED_PROXIES: "172.16.0.0/12 192.168.X.X"
      PHP_UPLOAD_LIMIT: 10G
    volumes:
      - /home/your-username/nextcloud/html:/var/www/html
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
      - /home/your-username/nextcloud/html:/var/www/html
      - /mnt/storage/nextcloud:/data
```

Environment variables:

```text
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

`/data` should show `/dev/sda1`, and the folder should contain `.ncdata`, an `appdata_...` folder and a folder named for your login. Open `https://pc.your-tailnet.ts.net:1005` and log in with your admin name and password. Then change the admin password to a new one inside Nextcloud. See [D5](../troubleshooting.md#d5-a-502-right-after-deploying-nextcloud) if the page shows a 502 at first.

## Phase 9: Speedtest Tracker and Netdata

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
      APP_URL: "http://192.168.X.X:8088"
      DB_CONNECTION: sqlite
    volumes:
      - /home/your-username/speedtest-tracker:/config
```

Create the folder first with `mkdir -p ~/speedtest-tracker`. I deployed this stack without the `volumes:` lines in Phase 9, and that cost me the app's data on 2026-10-23, when I updated it ([B6](../troubleshooting.md#b6-a-container-starts-empty-after-update-the-stack)). The lines are there now.

Open `http://192.168.X.X:8088` and log in with `admin@example.com` and `password`, then change both in your profile. Then create an API token at `http://192.168.X.X:8088/admin/api-tokens` with the **Read Results** ability, and run one speed test from the dashboard. Verify the token with:

```bash
curl -s -H "Accept: application/json" -H "Authorization: Bearer your-own-key" http://192.168.X.X:8088/api/v1/results/latest | head -c 300
```

You should see JSON with your speeds. If you get a 500 error on the first page, see [G6](../troubleshooting.md#g6-the-speedtest-tracker-card-shows-an-error).

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

Check it with `docker ps --format "table {{.Names}}\t{{.Status}}"` and `uptime`. The container is named `netdata-netdata-1`. Open `http://192.168.X.X:19999`. If it asks for a session ID, read it with `docker exec netdata-netdata-1 cat /var/lib/netdata/netdata_random_session_id`.

## Phase 10: Homepage

**1. Download the image:**

```bash
docker pull ghcr.io/gethomepage/homepage:latest
```

**2. Put the config files in `/home/your-username/homepage-config/`.** They are in the `homepage-config/` folder of the repository. The easiest way is to clone the repository on the server:

```bash
sudo apt install git -y
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git ~/My-Home-Lab-
cp ~/My-Home-Lab-/homepage-config/* ~/homepage-config/
cd ~/homepage-config
sed -i 's/192\.168\.X\.X/192.168.X.X/g; s/your-tailnet\.ts\.net/your-tailnet.ts.net/g' services.yaml
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
      HOMEPAGE_ALLOWED_HOSTS: 192.168.X.X:3001,pc.your-tailnet.ts.net:1000,localhost:3001
    volumes:
      - /home/your-username/homepage-config:/app/config
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /:/host:ro
      - /mnt/storage:/mnt/storage:ro
```

Open `http://192.168.X.X:3001`. The cards and the styling should appear. Widgets show errors until you fill in their keys.

**4. Fill in the keys. Stop Homepage first,** so a widget with a wrong login doesn't retry every few seconds ([D7](../troubleshooting.md#d7-nextcloud-returns-429-reached-maximum-delay)):

```bash
docker stop homepage
nano /home/your-username/homepage-config/services.yaml
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

Every card should show a green dot and a live widget. The second command should show `/dev/sda1`. For the individual widget errors I hit, see [G3](../troubleshooting.md#g3-the-beszel-widget-says-no-items-returned) to [G8](../troubleshooting.md#g8-yaml-indentation-mistakes).

## Phase 11: Point devices at AdGuard Home

My router wouldn't let me change its DNS setting, so I set the DNS server on each device by hand. Devices I don't change aren't filtered.

**Windows 11 (Ethernet):**

1. Open **Settings**, then **Network and internet**, then **Ethernet**.
1. Next to **DNS server assignment**, click **Edit**.
1. Choose **Manual**, switch **IPv4** on, and enter `192.168.X.X` as the preferred DNS and `8.8.8.8` as the alternate.
1. Click **Save**, then run `nslookup google.com` in a terminal. The server shown should be `192.168.X.X`.

**iPhone (Wi-Fi):**

1. Open **Settings**, then **Wi-Fi**, then tap the **i** next to the network.
1. Tap **Configure DNS**, then **Manual**.
1. Remove any existing servers, add `192.168.X.X` and `8.8.8.8`, and tap **Save**.

Check in AdGuard Home's dashboard: the **Top clients** list should show the devices, and the query count should rise as you browse. See [F3](../troubleshooting.md#f3-devices-are-not-using-adguard-home) for what the alternate server means.

## Phase 12: Recovery script, reboot test and final inventory

Create the recovery script (this was the first version, with a fixed list of containers. Phase 15 replaced it with the version in [Step 6](storage-setup-notes.md#step-6-the-recovery-command)), then test it without unplugging anything. It stops the five containers, unmounts and remounts the drive, and starts them again. That takes about a minute:

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

Then run the reboot test from [Step 8](storage-setup-notes.md#step-8-verify-it), and run the inventory script from [The inventory script](../troubleshooting.md#the-inventory-script) again. It should show all nine stacks running, the data drive at `/mnt/storage`, and every container seeing `/dev/sda1`.

## Phase 13: Nextcloud and Immich integration, and the phone

The `integration_immich` app (version 1.5.1) shows the Immich photos through Nextcloud. The steps, in order:

```bash
docker exec -u www-data nextcloud php occ config:system:set allow_local_remote_servers --value=true --type=boolean
docker exec -u www-data nextcloud php occ config:system:get allow_local_remote_servers
docker exec -u www-data nextcloud php -r 'echo file_get_contents("http://192.168.X.X:2283/api/server/ping");'
docker exec -u www-data nextcloud php occ app:list | grep -i immich
```

1. In Immich, create an API key named `nextcloud` (profile picture, **Account Settings**, **API Keys**, **New API Key**, all permissions). Copy it, because it's shown once.
1. Run the first two commands. The second should print `true`.
1. Run the third command. It should print `{"res":"pong"}`.
1. In Nextcloud, click your avatar, then **Apps**, search for `Immich`, and click **Download and enable** on the Immich integration. The fourth command should then list `integration_immich` with its version.
1. Click your avatar, then **Personal settings**, then **Immich Integration**. Enter `http://192.168.X.X:2283` (no `/photos` and no `/api`) and the API key, click **Test connection**, then **Save**.

If the test fails, see [D4](../troubleshooting.md#d4-the-immich-integration-says-local-ip-blocked) and [D9](../troubleshooting.md#d9-the-immich-integration-test-fails-with-an-authentication-error).

**Phone.** The phone has Tailscale. In the Immich app, enter the server address `http://192.168.X.X:2283` at home, or `https://pc.your-tailnet.ts.net:1002` when away (with Tailscale on). Log in and turn on backup. Immich is the only phone app set up so far.

## Phase 14: The Lenovo

The Lenovo is kept as a separate machine, still on the tailnet. Nothing on the ProDesk depends on it. Its old Tailscale addresses (the ones on ports 8441 to 8447 and 9444) are no longer used by any device. If you want to clear them from the Lenovo, run this on the Lenovo:

```bash
sudo tailscale serve reset
```

If the Lenovo's AdGuard Home is still running, stop it, so no device gets answers from two different DNS servers. The ProDesk is the only DNS server for the devices configured in Phase 11.

## Phase 15: Drive pools and the daily backup

Done on 2026-10-22, after the migration was finished and every service was running. It turns the single data drive into a pool that more drives can join, adds a daily backup, and replaces `hdd-recover`. I did it one step at a time and checked each result before the next. Steps 0 to 4 didn't touch my real data.

**Decisions**

- **Two pools, both mergerfs.** Main storage is `/mnt/storage` (labels `MAIN1`, `MAIN2` and so on) and backup storage is `/mnt/backup` (`BACKUP1`...). Every drive is a normal ext4 drive mounted by UUID under `/mnt/disks/`.
- **mergerfs, not RAID.** If a drive fails, only the files on that drive are lost from its pool, instead of everything.
- **Backup with `rsync`, every day at 6:00.** Files I delete or replace go into a dated folder and are kept for 30 days. The Nextcloud database is dumped as part of the run. The backup drives sleep when idle (untested, see Step 5).
- **The backup can be browsed from FileBrowser in read and write mode** (planned for when the backup pool exists).
- **For now the backup lives on the boot drive**, in `/home/your-username/750GB_HDD/backup-interim`, until a backup drive is bought.
- **No change to any stack.** The pool takes over the path `/mnt/storage`.

**Step 0: put the files on the server and check them.** I unzipped `homelab-drives.zip` on the Windows PC and dragged the folder into `/home/your-username` with VS Code:

```bash
cd ~/homelab-drives && sha256sum -c SHA256SUMS
grep -c $'\r' ~/homelab-drives/drives ~/homelab-drives/hdd-recover ~/homelab-drives/homelab-backup
```

```bash
drives: OK
hdd-recover: OK
homelab-backup: OK
homelab-backup.conf.example: OK
GUIDE.md: OK
/home/your-username/homelab-drives/drives:0
/home/your-username/homelab-drives/hdd-recover:0
/home/your-username/homelab-drives/homelab-backup:0
```

That was the list at the time. Later the `GUIDE.md` line was dropped and `homelab` was added ([Step 9](storage-setup-notes.md#step-9-the-cheat-sheet-at-login)), so `SHA256SUMS` now lists five files: `drives`, `homelab-backup`, `hdd-recover`, `homelab-backup.conf.example` and `homelab`.

**Step 1: check the server and install the tools.** Details and versions are in [section 2, Step 1](storage-setup-notes.md#step-1-install-the-tools-and-scripts).

**Step 2: install `drives` and `homelab-backup`.** `hdd-recover` isn't replaced yet:

```bash
cd ~/homelab-drives
sudo install -m 755 drives /usr/local/sbin/drives
sudo install -m 755 homelab-backup /usr/local/sbin/homelab-backup
sudo drives version
sudo drives status
```

`status` looked as shown in [Storage setup notes (build log)](storage-setup-notes.md#storage-setup-notes-build-log), Step 1: `main /mnt/storage mounted (ext4)`, `backup /mnt/backup NOT MOUNTED`, the Toshiba as `current data drive (plain, not in a pool yet)` and the Hitachi as `boot/system drive (never touched)`.

**Step 3: practise with fake drives.** Test mode uses disk-image files and its own folders and fstab (`/mnt/test-main`, `/mnt/test-backup`, `/mnt/test-disks`), so my real drives, `/etc/fstab` and containers aren't touched:

```bash
sudo DRIVES_TEST=1 drives test-setup 3 1G
sudo DRIVES_TEST=1 drives
```

I connected the fake drives as `TMAIN1` (main) and `TBACKUP1` (backup). The script asks for the device name and then `ERASE`, and it cancels with `Cancelled. Nothing was changed.` if either is wrong, which I saw twice when I pressed Enter without typing anything. The status then showed both pools mounted as `fuse.mergerfs` with `TMAIN1` and `TBACKUP1` connected, and the Toshiba as `not connected to a pool`. Trying to disconnect the only main drive was refused:

```text
TMAIN1 is the only main drive. Removing it would take away the storage your services use.
Add another main drive first (menu option 2), then try again.
```

Removing the only backup drive asked me to type `REMOVE` first, and then said the data on the drive wasn't touched. A second practice run with two 4 GB fake drives tested the copy-before-removing step. I wrote two 200 MB random files into the pool, one landed on each drive, and disconnected `TMAIN1`, answering `y` to copy its files first:

```text
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

**Step 4: practise with the 8 GB USB stick** (it gets erased). The stick showed up as `/dev/sdc`, exFAT, 7.2 GB, and was the only drive in the connect list, because the boot drive and the Toshiba are never offered. I connected it as `TMAIN1` in test mode, saw it as `connected` in `status`, and the script again refused to remove the only main drive. I closed the menu without running `test-cleanup`, which left the test pool mounted (see [A11](../troubleshooting.md#a11-the-practice-pool-is-still-mounted-after-test-mode)). After running it, this printed nothing, which is correct:

```bash
sudo DRIVES_TEST=1 drives test-cleanup
findmnt -rn | grep -E 'test-main|test-disks'
```

`lsblk` then showed the stick's partition mounted at `/media/your-username/TMAIN1`. That is the desktop auto-mounting the freshly formatted stick, and is harmless.

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

**Step 6: start the daily backup, onto the boot drive.** Details, log lines and sizes are in [section 2, Step 7](storage-setup-notes.md#step-7-the-daily-backup). The first run started at 19:04 and finished at 19:28 with `finished: OK in 1420s`, and both `/mnt/storage` and the copy were `61G`. Then I added the schedule with `sudo crontab -e`:

```cron
0 6 * * * /usr/local/sbin/homelab-backup
```

**Step 7a: convert the Toshiba into the main pool.** I did this only after Step 6 had made a verified backup from the same day. `sudo drives adopt` is shown in [section 2, Step 2](storage-setup-notes.md#step-2-add-the-main-drive). The containers were stopped for about a minute. Each container then showed `mergerfs-main  916G  61G  855G  7%` for `/data`, and `status` listed `MAIN1` as `connected` with SMART `PASSED`. No stack needed an edit. The first check I tried, `findmnt /mnt/storage /mnt/disks/MAIN1`, printed nothing (see [A12](../troubleshooting.md#a12-findmnt-prints-nothing-when-given-two-paths)).

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

```text
@reboot sleep 60 && /usr/local/sbin/drives power >/dev/null 2>&1
0 6 * * * echo "$(date +\%F) $(smartctl -A -d sat /dev/disk/by-label/MAIN1 | awk '/Load_Cycle/ {print $10}')" >> /var/log/loadcycles.log
@reboot sleep 60 && /usr/sbin/hdparm -B 254 "/dev/$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)")"
0 6 * * * /usr/local/sbin/homelab-backup
```

The first time, the saved copy was restored by accident right after the change, because I ran the "undo" command in the same block (see [A14](../troubleshooting.md#a14-the-crontab-went-back-to-the-old-lines)). I ran the `sed` again, which fixed it. Then `sudo drives power` printed the two power lines, and `sudo hdparm -B /dev/sda` printed `APM_level      = 254`. A first attempt to read the setting with `sudo hdparm -B -S /dev/sda` printed `-S: bad/missing standby-interval value (0..255)` (see [A13](../troubleshooting.md#a13-hdparm--b--s-says-bad-or-missing-standby-interval)).

**Step 7c: reboot test.** After `sudo reboot` and about five minutes:

```text
TARGET       SOURCE        FSTYPE        OPTIONS
/mnt/storage mergerfs-main fuse.mergerfs rw,relatime,user_id=0,group_id=0,default_permissions,allow_oth
TARGET           SOURCE    FSTYPE OPTIONS
/mnt/disks/MAIN1 /dev/sda1 ext4   rw,noatime
```

All 16 containers were up. Fourteen had been up for 5 minutes, while Homepage showed `Up 30 seconds` and Portainer `Up 23 seconds`, so those two had restarted once after the boot. I didn't investigate why. About two hours later every container showed `Up 2 hours`, so neither has restarted again. `sudo drives status` still showed `MAIN1` connected and the last backup as `OK`. `systemctl --failed` listed one unit, `casper-md5check.service` (it verifies the live installer ISO and has nothing to do with the drives). `/var/log/homelab-drives.log` recorded `adopted /dev/sda1 as MAIN1; pool at /mnt/storage` and the power settings being applied. The last entry, at 20:45, is the cron job running after the reboot.

The first scheduled 6:00 backup was the next morning, 2026-10-23.
