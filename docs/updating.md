# Updating services

How to keep each service, and the system under it, up to date. The version numbers in the examples are the ones from the day I wrote each section; always look up the current ones on the release pages listed in [Sources](#sources).

**How much of this has been tested.** I updated Portainer on 2026-10-22 ([Portainer](#portainer)) and Speedtest Tracker on 2026-10-23 ([Speedtest Tracker](#speedtest-tracker)), and those two sections show what I ran and what happened, including what went wrong. Everything else was written from each project's own documentation and release page, and **I have not run those steps on this server yet**. Each service says so.

**How updates work here.** The stack files in [`stacks/`](../stacks/) pin each image to a version (or, for Immich and Netdata, to a release channel), so a container never updates by itself. An update is always three moves: choose the new version and change the tag on the `image:` line, download the image, then recreate the container from it. In Portainer, the last move is **Update the stack**. Settings and data that live in bind-mounted folders and in named Docker volumes survive the recreate. Data in an **anonymous** volume may not: it is how Speedtest Tracker lost its data ([B6](troubleshooting.md#b6-a-container-starts-empty-after-update-the-stack)). Check for them first ([check 5](#before-you-update-anything)). After an update, change the same tag in your copy of the stack file in this repository, so that the next rebuild gets the version you run. `sudo homelab-update` finds newer builds of the tag a container runs (the `release`, `stable` and `35-apache` channels move; a tag such as `v2.6.0` hardly ever does), so for pinned versions also look at the release pages.

## What can be updated

| Service | Stack | How it is versioned | Where to look for the newest version |
| --- | --- | --- | --- |
| Portainer | none (standalone container) | `latest` tag, on purpose | [Portainer](#portainer) |
| Homepage | `homepage` | pinned tag (`vX.Y.Z`) | [Homepage](#homepage) |
| Speedtest Tracker | `speedtest-tracker` | pinned tag | [Speedtest Tracker](#speedtest-tracker) |
| Netdata | `netdata` | `stable` channel | [Netdata](#netdata) |
| Beszel hub and agent | `beszel`, `beszel-agent` | pinned minor version (`0.21`) | [Beszel hub and agent](#beszel-hub-and-agent) |
| AdGuard Home | `adguard` | pinned tag | [AdGuard Home](#adguard-home) |
| FileBrowser | `filebrowser` | pinned tag | [FileBrowser](#filebrowser) |
| Immich | `immich` | `release` channel (the version is in `IMMICH_VERSION`) | [Immich](#immich) |
| Nextcloud | `nextcloud` | pinned major version (`35-apache`) | [Nextcloud](#nextcloud) |
| Docker Engine | system | `apt` | [Docker Engine](#docker-engine) |
| Tailscale | system | `apt` | [Tailscale](#tailscale) |
| Linux Mint packages | system | `apt` | [Linux Mint packages](#linux-mint-packages) |

Two things I found when I last checked (2026-10-23), which are still worth knowing:

- **Immich v3.3.5** was a security release. Its release notes listed no breaking changes and no manual steps, and said to update as soon as possible. Read the notes of the version you move to.
- **FileBrowser** is finished as a project. Its repository was archived on 2026-09-01, and its notice says there will be no further releases, bug fixes or security fixes. Version 2.63.23, the last one, is what the stack pins. The notice suggests treating a copy that stays in use as unmaintained software.

## Before you update anything

Do these five things every time. They take a few minutes and make every later step safer.

**1. Pick a quiet time.** Avoid 6:00 to 6:30, when the daily backup runs. Update one service at a time and wait until it is healthy before the next one. Never start Immich and Nextcloud together (see [A10](troubleshooting.md#a10-immich-and-nextcloud-overload-the-machine-when-they-start-together)).

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
| --- | --- |
| Everything in the main pool (`/mnt/storage`): Immich photos, Immich's own database dumps, Nextcloud files | The Immich database folder `/home/your-username/immich/postgres` (live files) |
| A fresh dump of the Nextcloud database | The Nextcloud database folder `/home/your-username/nextcloud/db` (the dump covers it) |
| Homepage config, AdGuard Home config, Nextcloud app files, and the Portainer, Beszel and FileBrowser volumes | The Netdata volumes. Speedtest Tracker's folder is covered only after you add it to `CONFIG_PATHS` ([Step 7](history/storage-setup-notes.md#step-7-the-daily-backup), "Extra folders") |

Also remember that the backup lives on the boot drive until a backup drive is connected, so it does not protect against that drive failing.

**3. Find out which version you are on and which is newest.** The version you run is the tag on the `image:` line of the stack (Portainer, **Stacks**, the stack, **Editor**) or in `stacks/` in this repository. The newest one is on the project's release page ([Sources](#sources)). Pulling only downloads an image and never touches a running container, so you can safely download the new image first. Run the pulls one at a time, because the GitHub registry throttles parallel downloads ([B5](troubleshooting.md#b5-toomanyrequests-from-githubs-container-registry)). Each service section below shows its own pull command with the tag to use. The Netdata image is large (about 1.3 GB), so give it time.

**4. Read the release notes** of anything you are about to update. The links are in [Sources](#sources).

**5. Check for anonymous volumes.** A container that keeps its data in an anonymous volume can come back empty after **Update the stack** ([B6](troubleshooting.md#b6-a-container-starts-empty-after-update-the-stack)). This only reads information:

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

## Portainer

**Status: done and tested on 2026-10-22** (2.45.2 to 2.45.3). Portainer is the one container here that is not a stack. It was started with `docker run`, so it is recreated from the terminal, not with **Update the stack**. Its settings, users, stack files and the token Homepage uses are in the `portainer_data` volume, so they survive.

**1. Record how it runs now.** This only reads information:

```bash
docker inspect portainer --format 'Image: {{.Config.Image}}{{"\n"}}Restart: {{.HostConfig.RestartPolicy.Name}}{{"\n"}}Ports: {{json .HostConfig.PortBindings}}{{"\n"}}Mounts:{{range .Mounts}}{{"\n"}}  {{.Type}} {{.Name}} {{.Source}} -> {{.Destination}}{{end}}'
```

Mine printed `portainer/portainer-ce:latest` (Portainer is the one container that runs from the `latest` tag, so that its security fixes reach it), `Restart: always`, ports 9000 and 9443, the `portainer_data` volume at `/data` and the Docker socket. Every option in step 4 comes from this output.

**2. Stop Portainer and back up its data.** Stopping first means the database file is not being written to. Your other containers are not affected. The Portainer page and the Homepage Portainer card are down until step 4. The backup holds Portainer's private keys, so lock it down and never put it on GitHub:

```bash
docker stop portainer
sudo tar -czf ~/portainer_data-backup-$(date +%F).tar.gz -C /var/lib/docker/volumes/portainer_data/_data .
sudo chown your-username:your-username ~/portainer_data-backup-$(date +%F).tar.gz
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

## Homepage

**Status: written from the documentation, not yet run on my server.** The stack pins Homepage to a version tag, for example `ghcr.io/gethomepage/homepage:v2.6.0`. When a newer one appears:

1. Do the four checks in [Before you update anything](#before-you-update-anything). Homepage's settings are in `/home/your-username/homepage-config`, which the daily backup covers.
2. Read the release notes. The v2.6.0 notes mention changes to how `$` is handled in secrets, so check the notes when your keys contain a dollar sign.
3. Download the image of the new version (replace `vX.Y.Z` with it):

   ```bash
   docker pull ghcr.io/gethomepage/homepage:vX.Y.Z
   ```

4. In Portainer, open the `homepage` stack, change the version at the end of the `image:` line to `vX.Y.Z` and use **Update the stack** (the steps are in [Before you update anything](#before-you-update-anything)). The settings folder is a bind mount, and `HOMEPAGE_ALLOWED_HOSTS` is part of the stack, so both stay as they are.
5. Check it. The container should become `healthy`, the log should not show a "Host validation failed" line, and the page should load after a hard refresh (`Ctrl+Shift+R`):

   ```bash
   docker ps --filter name=homepage --format "table {{.Names}}\t{{.Status}}"
   docker logs --tail 20 homepage
   ```

   The Netdata line `Parse Error: Data after Connection: close` is known and harmless ([G13](troubleshooting.md#g13-the-netdata-card-is-green-but-homepages-log-shows-a-parse-error)).

**Rollback:** in the stack's **Editor**, change the tag back to the previous version (for example `homepage:v2.6.0`) and click **Update the stack**. Your files in `/home/your-username/homepage-config` are not changed by an update.

## Speedtest Tracker

**Status: done on 2026-10-23** (v1.15.0 to v1.15.1-ls177), **but it lost its data and I had to restore it.** The update itself is easy. The data loss was my own setup's fault, and it is fixed for good now. Version v1.15.1 was released on 2026-10-22. Its notes list a fix for a server filter that returned nothing with SQLite, and dependency updates. They list no breaking change.

**What happened.** My stack had no `volumes:` line, so Speedtest Tracker's `/config` folder (the database, the settings and the application key) was an anonymous Docker volume. I copied `/config` out by hand before updating, which saved the data. **Update the stack** then started a new container with a new empty volume. The old results and settings were gone until I restored them ([B6](troubleshooting.md#b6-a-container-starts-empty-after-update-the-stack)). My first version of this section said that the data survives a recreate. That was wrong for this container.

**The procedure to follow,** with what I learned. If your stack already has the bind mount from [Phase 9](history/lenovo-migration.md#phase-9-speedtest-tracker-and-netdata), skip step 2.

1. Do the five checks in [Before you update anything](#before-you-update-anything).
2. **Make sure `/config` is a folder on the host, not an anonymous volume.** Check:

   ```bash
   docker inspect speedtest-tracker --format '{{range .Mounts}}{{.Type}} {{.Source}} -> {{.Destination}}{{println}}{{end}}'
   ```

   You want a line that starts with `bind /home/your-username/speedtest-tracker -> /config`. A line that starts with `volume` and a long name means an anonymous volume. In that case, do the fix in [B6](troubleshooting.md#b6-a-container-starts-empty-after-update-the-stack) first (copy the data, add the `volumes:` lines), and only then update.
3. Make a copy by hand anyway. It is cheap, and it is what saved my data:

   ```bash
   docker cp speedtest-tracker:/config ~/speedtest-config-backup-$(date +%F)
   ls ~/speedtest-config-backup-$(date +%F)
   ```

   Keep this copy private. It contains the database and the application key.
4. Download the image of the new version (replace `X.Y.Z` with it; the linuxserver.io images are tagged like `1.15.1`):

   ```bash
   docker pull lscr.io/linuxserver/speedtest-tracker:X.Y.Z
   ```

5. In Portainer, open the `speedtest-tracker` stack, change the tag on the `image:` line to `X.Y.Z` and use **Update the stack**. `APP_KEY` stays in the stack's variables, so don't retype it.
6. Check it:

   ```bash
   docker ps --filter name=speedtest-tracker --format "table {{.Names}}\t{{.Status}}"
   docker logs --tail 20 speedtest-tracker
   ```

   The log may say `generating self-signed keys` on the first start of a new `/config`. That is normal for an empty folder, and it is also what I saw when the data was lost, so don't use that line as proof either way. Open `https://pc.your-tailnet.ts.net:1007`, log in, and check that the past results are still listed. Then check that the Speedtest card on the Homepage dashboard shows numbers. Its API token lives in the database, so it should keep working.

**Result on my server:** after the restore and the bind mount, the card was green, and it was still green after another **Update the stack**.

**Rollback:** in the **Editor**, change the tag back to the earlier version (check the exact spelling on the image's tag list on GitHub's package page) and click **Update the stack**. If the new version changed the database, stop the container and put the copy from step 3 back into the data folder:

```bash
docker stop speedtest-tracker
cp -a ~/speedtest-config-backup-DATE/. ~/speedtest-tracker/
docker start speedtest-tracker
```

## Netdata

**Status: written from the documentation, not yet run on my server.** The stack uses `netdata/netdata:stable`, which follows Netdata's stable releases. (An older version of this lab used no tag, which means `latest` and can include nightly builds.) The configuration, data and cache are in the volumes `netdataconfig`, `netdatalib` and `netdatacache` and survive an update.

1. Do the checks in [Before you update anything](#before-you-update-anything). Nothing here needs special care.
2. Download the image (about 1.3 GB):

   ```bash
   docker pull netdata/netdata:stable
   ```

3. If it printed `Downloaded newer image`, open the `netdata` stack in Portainer and use **Update the stack**.
4. Check it:

   ```bash
   docker ps --filter name=netdata --format "table {{.Names}}\t{{.Status}}"
   docker exec netdata-netdata-1 netdata -W buildinfo | head -5
   ```

   The container should become `healthy`. The Netdata card on Homepage should be green.

**Rollback:** change the image line to a version tag from the image's tag list on Docker Hub (written as `netdata/netdata:vX.Y.Z`; the exact tag names are on the image's tag list) and update the stack.

## Beszel hub and agent

**Status: written from the documentation, not yet run on my server.** Version 0.21.1 was released on 2026-10-22. The notes mention that some memory fields are being replaced by new fields that carry byte values, and that the new fields are filled in by a hub 0.21.1 or newer. Beszel's guides don't state an update order. My reasoning is that the hub should be updated first so it understands everything the newer agent sends. That is my inference, not a rule from the project.

1. Do the four checks in [Before you update anything](#before-you-update-anything). The Beszel hub's data is in the `beszel_beszel_data` volume, which the daily backup covers. Beszel's guide also mentions the hub's own backup feature as an extra copy.
2. Download both images of the new version (replace `X.Y` with it, for example the next minor version after the one in the stack files):

   ```bash
   docker pull henrygd/beszel:X.Y
   docker pull henrygd/beszel-agent:X.Y
   ```

3. **Hub first.** In Portainer, open the `beszel` stack, change the tag on the `image:` line to `X.Y` and use **Update the stack**. Check it:

   ```bash
   docker ps --filter name=beszel --format "table {{.Names}}\t{{.Status}}"
   docker logs --tail 15 beszel
   ```

   Open the Beszel page (`https://pc.your-tailnet.ts.net:1003`) and log in. The system `pc` should still be listed.
4. **Then the agent.** Open the `beszel-agent` stack, change its tag to `X.Y` as well and use **Update the stack**. The `KEY` and `TOKEN` variables stay saved, so don't retype them. The system `pc` should show as up again in the hub within a minute.
5. Check that the Beszel card on Homepage shows the numbers.

**Rollback:** change the tags back to the version you ran before in the two stacks' **Editor** and update them. If the hub's data looks wrong afterwards, restore the `beszel_beszel_data` folder from the backup (`/home/your-username/750GB_HDD/backup-interim/boot-configs/var/lib/docker/volumes/beszel_beszel_data`) with the hub stopped.

## AdGuard Home

**Status: written from the documentation, not yet run on my server.** This stack pins its version in the image line (`adguard/adguardhome:v0.107.79`), so it never changes by itself. v0.107.79 is also the newest release found (published in August), so there is nothing to update now. When a newer version is out:

1. Read its release notes on the project's release page. The v0.107.79 notes say `strict_sni_check` is deprecated, so check whether my config uses it:

   ```bash
   sudo grep -n strict_sni_check /opt/adguard-docker/conf/AdGuardHome.yaml
   ```

   No output means it isn't set.
2. Do the checks in [Before you update anything](#before-you-update-anything), then copy the AdGuard configuration. The copy holds a password hash, so keep it private:

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
   nslookup example.com 192.168.X.X
   ```

   The lookup should return an address. Open AdGuard Home (`https://pc.your-tailnet.ts.net:1004`) and check that the Query Log is filling and the version in the footer is the new one.

**Rollback:** change the image line back to the old tag (`v0.107.79`) in the **Editor** and update the stack. If the configuration file was changed by the newer version, stop the container, put the copy from step 2 back into `/opt/adguard-docker/conf`, and start it.

## FileBrowser

**Status: nothing to update, and nothing will come.** The latest and last release is 2.63.23, which is what I run. The project's repository was archived on 2026-09-01, and its notice says there will be no further releases, bug fixes or security fixes. The Docker images stay available.

You can confirm that nothing changed with:

```bash
docker pull filebrowser/filebrowser:v2.63.23
```

It should end with `Status: Image is up to date`. A newer version will not come. If one ever does, update it like the others (change the tag on the `image:` line): open the `filebrowser` stack in Portainer and use **Update the stack**, then check `docker ps` for `filebrowser-filebrowser-1`.

What I do about it, following the project's own advice for unmaintained software:

- FileBrowser is reachable only through Tailscale. There is no port forwarding on the router, so it is not exposed to the internet.
- Keep its command runner turned off (the FileBrowser settings page has the switch).
- Replacing it with a maintained file manager is a decision for later. I have not chosen one.

## Immich

**Status: written from the documentation, not yet run on my server.** v3.3.5 is a security release with no breaking changes and no manual steps listed. The stack uses `ghcr.io/immich-app/immich-server:release` and the matching machine-learning image (the tag comes from the `IMMICH_VERSION` variable, which is `release` by default), so a re-pull moves to the newest version.

Immich's own rules, from its upgrade page:

- Read the release notes first. Breaking changes are supposed to appear only in major releases.
- The server only works with its own major version. The mobile apps support the current and the previous major version, so update the iPhone app first when a major version changes.
- Downgrades are not supported, not even inside a minor version. Rolling back means restoring a backup.

Steps:

1. Do the four checks in [Before you update anything](#before-you-update-anything), including the fresh backup.
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

7. Check it. Open Immich (`https://pc.your-tailnet.ts.net:1002`), log in, and confirm that the server version is the new one and that your photos and the storage meter (bottom left) show as before. Open the Immich app on the iPhone and let it sync. Then check the Immich card on Homepage and the Nextcloud integration (Nextcloud's Immich page should still list your photos).
8. When everything is fine, free the disk space of the old images:

   ```bash
   docker image prune
   ```

**Rollback:** only for a small problem inside the same major version. In the stack's variables set `IMMICH_VERSION` to the previous version (for example `v3.3.3`) and click **Update the stack**. Immich does not support downgrades, so if the database was changed by the new version, restore the database from the dump made in step 2 following Immich's backup and restore page.

## Nextcloud

**Status: written from the documentation, not yet run on my server.** The stack runs the Nextcloud 35 line. It also has `postgres:16-alpine` (the database), `redis:alpine` (the cache) and a second container, `nextcloud_cron`, that uses the same Nextcloud image.

**The one rule that matters.** The Docker image docs say it is only possible to upgrade one major version at a time (for example 35 to 36, never 35 straight to 37). The stack therefore pins the major version in both image lines (`nextcloud:35-apache`, for the `nextcloud` and the `nextcloud_cron` service), so a re-pull never starts a major upgrade by itself. (An older version of this lab used `nextcloud:apache`, which always points at the newest major version.)

**A normal update inside the same major version (for example 35.0.2 to 35.0.3):**

1. Do the four checks in [Before you update anything](#before-you-update-anything). The backup includes a fresh dump of the Nextcloud database, and that is your safety net, because Nextcloud cannot go back to an older version.
2. Write down the current state:

   ```bash
   docker exec -u www-data nextcloud php occ status
   ```

   It should say `installed: true`, the version, and `maintenance: false`.
3. Download the newest image for your pinned major version (this only fetches 35.x updates):

   ```bash
   docker pull nextcloud:35-apache
   ```

4. In Portainer, open the `nextcloud` stack and use **Update the stack**. Both Nextcloud containers are recreated. On start, the image notices the new version and runs the upgrade by itself, so you don't run `occ upgrade`.
5. Watch the log until Apache is ready. The first start after an update can take several minutes, and the page shows an error until then ([D5](troubleshooting.md#d5-a-502-right-after-deploying-nextcloud)):

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

## Docker Engine

**Status: written from the documentation, not yet run on my server.** Docker came from Docker's Ubuntu `noble` repository ([B1](troubleshooting.md#b1-docker-installs-from-the-wrong-repository-on-mint)), so `apt` updates it.

**What to expect:** restarting Docker stops all containers. The `restart` settings in my stacks bring them back, but every service is down for a minute or two, and Immich and Nextcloud take longer to turn healthy. Pick a quiet time and update Docker on its own, not together with anything else.

1. Do the four checks in [Before you update anything](#before-you-update-anything).
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

   The version should be the new one, and all 16 containers should come back up on their own. The wait-for-mount file in `/etc/systemd/system/docker.service.d/` is not touched by an update. If a container that needs the drive shows the wrong disk, run `sudo hdd-recover`.

**Rollback:** list the older versions with `apt list --all-versions docker-ce` and install one by naming its version, as Docker's install page describes. I wouldn't downgrade unless Docker itself stops working.

## Tailscale

**Status: an automatic Tailscale update broke DNS on my server once.** The Machines page in the Tailscale admin console showed `pc` on a newer version, so the machine had updated itself. Right after that, the server could not look up names (`SERVFAIL` from `100.100.100.100`) and the Tailscale card on Homepage turned red. The cause and the fix are in [F6](troubleshooting.md#f6-the-server-cannot-look-up-names-after-a-tailscale-update). The steps below are written from Tailscale's documentation, which says an update through a package manager is done by that manager and also names `tailscale update`. I have not run them.

**Important:** use the local address for this, not the Tailscale one. A restart of Tailscale drops a session that is running over Tailscale ([E7](troubleshooting.md#e7-an-ssh-session-over-tailscale-drops-when-tailscale-restarts)). From the Windows PC:

```powershell
ssh your-username@192.168.X.X
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

   The version should be the new one, the status should show `pc` connected, and the Serve status should list all nine entries on ports 1000 to 1008. Open one address from your phone or the Windows PC to confirm, for example Homepage on port 1000.

4. **Check that the server can still look up names.** This is the step that would have caught the problem:

   ```bash
   cat /etc/resolv.conf
   nslookup github.com
   ```

   The lookup must return addresses. If it says `SERVFAIL`, follow [F6](troubleshooting.md#f6-the-server-cannot-look-up-names-after-a-tailscale-update), and restart Homepage afterwards.

If the Serve list is empty after an update, re-create the nine entries from the Tailscale phase of the migration ([Phase 6](history/lenovo-migration.md#phase-6-tailscale-addresses)).

## Linux Mint packages

**Status: written from general apt practice, not yet run for this purpose on my server.** This covers the operating system and everything installed with `apt`, such as `mergerfs`, `smartmontools` and the kernel.

1. Do the four checks in [Before you update anything](#before-you-update-anything).
2. Update Docker and Tailscale first, on their own, by following [Docker Engine](#docker-engine) and [Tailscale](#tailscale). That way their restarts don't hide in a large update.
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

7. After about five minutes, run the same checks as after any restart (one `findmnt` per command, see [A12](troubleshooting.md#a12-findmnt-prints-nothing-when-given-two-paths)):

   ```bash
   findmnt /mnt/storage
   findmnt /mnt/disks/MAIN1
   docker ps --format "table {{.Names}}\t{{.Status}}"
   sudo drives status
   uname -r
   ```

   If the drive is missing or a container shows the wrong disk, run `sudo hdd-recover`.

**Rollback:** if a new kernel causes trouble, choose the older kernel from the GRUB menu's advanced options at boot. That menu appears before any remote access works, so it needs a monitor and keyboard connected to the machine. Connect them before you reboot into a new kernel if you want that option.

## After updating

1. Run the inventory script from [Diagnostic commands](troubleshooting.md#diagnostic-commands) so the report shows the new versions, and keep the new report.
2. Check `sudo drives status` again the next morning: the 6:00 backup should say `OK`.
3. Update the version numbers anywhere you keep them: the tag in the matching file in `stacks/`, the README's "Tested with" line, and the [changelog](../CHANGELOG.md).
4. Remove the spare Portainer container and the unused images once everything has worked for a day (see [Portainer](#portainer), step 6).
5. Run `homelab` ([Step 9](history/storage-setup-notes.md#step-9-the-cheat-sheet-at-login)). Every status line should be green, and `nslookup github.com` should still work ([F6](troubleshooting.md#f6-the-server-cannot-look-up-names-after-a-tailscale-update)).

## Sources

The steps above come from these pages (read on 2026-10-23; they may have moved since):

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
