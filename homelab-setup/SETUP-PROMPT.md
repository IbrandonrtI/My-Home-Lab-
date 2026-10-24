# Home lab one-command setup: master prompt and spec

This file does two jobs:

1. It is the **spec** for `homelab-setup`, the installer that turns a fresh Linux machine (Linux Mint or Ubuntu Server) into a copy of this home lab by pulling this GitHub repo.
2. It is a **master prompt** you can paste into a new AI chat (see "The master prompt" at the end) so that chat can change, extend or debug the installer without re-deriving anything.

Status: built and tested against a **simulated** machine (fake apt, Docker, Tailscale and fake web services for every app). It has **not** yet been run on a real VM. Section 12 lists exactly what the simulation could not prove.

---

## 1. What you get

On a blank machine:

```
sudo apt update && sudo apt install -y git
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git
cd My-Home-Lab-
sudo bash setup.sh install --dry-run     # shows what it would do, changes nothing
sudo bash setup.sh install               # asks a few questions, then builds the lab
```

The installer then:

1. Updates and upgrades the system.
2. Installs Docker, Tailscale and the helper programs.
3. Starts Portainer, creates its admin account and deploys the nine stacks **through the Portainer API** (so they stay editable in Portainer): AdGuard Home, Beszel, Netdata, Speedtest Tracker, FileBrowser, Immich, Nextcloud, Homepage, Beszel agent.
4. Fills in every machine-specific value (user, IP, Tailscale name, keys) and gives Homepage working widgets, each one **tested live** before its key is written.
5. Installs your scripts (`homelab`, `homelab-update`, `drives`, backup tools), their cron jobs and the login screen.
6. Prints a **checklist** of what is done and what only you can do. `sudo homelab-setup refresh` re-scans the machine and shows what is still left. The login screen shows one line, `Setup N of M steps done: run homelab-setup`, until everything is done.

It never formats or changes a drive, never stores the password you type, and never puts a secret in the repo or in chat.

## 2. Who the user is and how to work with them

- Brandon, computer-engineering-technology student, job-searching for IT help-desk roles. The repo is part of his portfolio, so it must be readable and honest.
- Plain language. One step at a time on server changes, then wait for pasted output.
- Name the terminal for every command (the server `pc`, a laptop, a VM).
- End each message with a short "Send me" list.
- Undo commands go in their own block, and only after the install is confirmed.
- Never ask him to paste a secret in chat. Never write a secret into a file in the repo.
- Do **not** change the DNS design (AdGuard Home on this machine; devices set DNS by hand) without asking.
- README and TROUBLESHOOTING are frozen until he says. README uses placeholders (`your-username`, `192.168.X.X`, `your-tailnet.ts.net`, `your-own-key`). TROUBLESHOOTING uses real values. The `Portainer-code` stack files keep real values on purpose.
- Commit and push only when asked.

## 3. Decisions already made (and the ones I defaulted)

| Topic | Decision | Source |
|---|---|---|
| Deploy method | Portainer API (stacks stay editable). Admin password typed once, never stored in a file | Brandon |
| Admin accounts and widget keys | Created by API where the app allows it, written into Homepage config and **tested**; the rest become guided checklist steps | Brandon |
| Config source | Always set up stack files and Homepage config from the repo; if a backup is found, restore saved configs (`homelab-restore-configs`) | Brandon |
| Photos and files (~62 GB) | Restored from a backup drive/folder if present, otherwise services start empty | Brandon |
| Storage | `/mnt/storage` is a plain folder on the boot drive at first. `sudo drives` is a checklist step. The installer never formats or touches a drive | Brandon |
| Secrets | Portainer stack variables plus ONE root-only 600 file (`/root/.homelab-setup/secrets.env`) shown once; never in the repo or chat | Brandon |
| Passwords | One password you type, used for every admin login (Brandon chose this over one-per-app). The installer shows a risk warning | Brandon |
| Port 53 | May be freed as the README does (stops `systemd-resolved`). It tells the user first. Refused over a Tailscale SSH session | Brandon |
| Testing | VM or spare PC. Simulation only here | Brandon |
| Login screen | One line "Setup N of M steps done: run homelab-setup" until complete | Brandon |
| Extras | Installs his scripts into `/usr/local`, the cron entries and the login hook. NOT AnyDesk, auto-login or VS Code | Brandon |
| Existing server | If 7 or more stacks already run and the installer never started, it is **read-only** (`--force-existing` to override) | me (safety) |
| Install source of truth | The repo clone the installer runs from; its path is saved so later runs use the same copy | me |
| Python | Python 3 standard library only (works on 3.7 and newer; Mint and Ubuntu Server ship it) | me |

Defaults I chose without an answer (change them if you disagree): the existing-machine read-only rule; the daily backup cron (06:00) is added only after `/mnt/storage` is a real mount point (the backup script refuses otherwise), and is dropped from the checklist when you skip the data drive; weather defaults to the repo value (New York) and is a "do it by hand" step.

## 4. Value substitution map

The repo files hold the original server's values or placeholders. The installer rewrites them for the new machine:

| In the repo | Becomes |
|---|---|
| `/home/brandon` | the new user's home |
| `192.168.1.198`, `192.168.X.X` | this machine's LAN address (asked, default detected) |
| `pc.griffin-luma.ts.net`, `pc.your-tailnet.ts.net` | this machine's Tailscale full name (`Self.DNSName`) |
| `griffin-luma.ts.net`, `your-tailnet.ts.net` | the tailnet name |
| `PUID` / `PGID` | the new user's ids |
| Speedtest `APP_KEY` | generated (`base64:` + 32 random bytes) |
| Beszel agent `KEY` / `TOKEN` | fetched from the new Beszel hub |
| Immich env | `UPLOAD_LOCATION`, `DB_DATA_LOCATION`, `TZ`, `IMMICH_VERSION`, `DB_PASSWORD` (generated), `DB_USERNAME=postgres`, `DB_DATABASE_NAME` |
| Nextcloud env | `NC_ADMIN_USER`, `NC_ADMIN_PASSWORD` (the typed password), `NC_DB_PASSWORD` (generated, or reused from a restored `config.php`) |
| Homepage widget placeholders (`your-own-key`, device id, etc.) | real values, but only after a live test passes |

## 5. Phases (what runs, in order)

The installer is a list of **steps**. Each step has a `probe()` that checks the live machine (done / todo / not applicable), so the checklist is always the truth and re-running never repeats work. Steps declare `needs` and run in dependency order. Steps are `auto` (the tool does it), `manual` (needs you, with a `fill` walk-through) or `ack` (you confirm with `done`).

1. **Questions** (once): admin name, email, time zone, LAN address, then the shared password (12+ letters and digits, typed twice, memory only), then the restore choice if a backup is found.
2. **System**: `apt update`/`upgrade`, helper packages, Docker (Docker's apt repo, deb822), docker group.
3. **Tailscale**: install from `pkgs.tailscale.com`, login with a link (or `TS_AUTHKEY`), then you turn on MagicDNS and HTTPS certificates in the Tailscale admin page, then `tailscale serve` maps HTTPS ports 1000 to 1008 to the LAN ports.
4. **Network**: free port 53 for AdGuard (explained, confirmed, refused over Tailscale SSH).
5. **Platform**: folders with correct owners, secrets file, Portainer, its admin account, an API token for this tool, the local Docker environment, optional restore of settings and data.
6. **Services**: the nine stacks, one image pulled at a time with retry on Docker Hub rate limits, deployed via the Portainer API, each waiting until its containers run.
7. **Logins and keys**: AdGuard first-run and upstream DNS; Immich admin; Nextcloud finished, trusted domains, optional database restore; Beszel hub account and agent key.
8. **Homepage**: config files for this machine, then each widget (see section 7).
9. **Scripts and schedule**: scripts, backup settings, cron lines, login hook.
10. **Your devices and drives**: data drive, save the secrets, set DNS on devices, Speedtest login, blocklists, weather, reboot test.

## 6. Checklist catalogue (57 steps; the ones that do not apply are hidden)

Group | id | kind | needs | what it checks
---|---|---|---|---
System | os | auto | | supported OS
System | apt-upgrade | auto | | system packages updated
System | packages | auto | os | curl, ca-certificates, gnupg, rsync, cron, smartmontools, hdparm, python3-yaml, mergerfs...
System | docker | auto | os, packages | `docker info`, compose, buildx
System | docker-group | auto | docker | user is in group docker
Tailscale | tailscale-install | auto | os, packages | `tailscale` installed
Tailscale | tailscale-login | manual | tailscale-install | `Self.DNSName` present
Tailscale | tailscale-https | manual | tailscale-login | `CertDomains` not empty
Tailscale | tailscale-serve | auto | tailscale-login, tailscale-https | nine serve mappings match
Network | port53 | auto | docker | nothing but AdGuard on port 53
Platform | folders | auto | os | `/mnt/storage/{immich,filebrowser,nextcloud}`, `~/nextcloud/{html,db}`, `~/immich/postgres`, `~/speedtest-tracker`, `~/homepage-config`, `~/750GB_HDD`, `/opt/adguard-docker/{conf,work}`
Platform | secrets | auto | os, restore-configs | secrets file has DB_PASSWORD, NC_DB_PASSWORD, APP_KEY (and matches a restored `config.php`)
Platform | portainer, portainer-admin, portainer-token, portainer-env | auto | chain | container, admin, API token, local endpoint
Platform | restore-configs, restore-data | auto | folders | only if you chose a restore
Services | stack-adguard, -beszel, -netdata, -speedtest-tracker, -filebrowser, -immich, -nextcloud, -homepage, -beszel-agent | auto | portainer-env and per-stack needs | containers running
Logins and keys | adguard-setup, adguard-dns, immich-admin, nextcloud-ready, nextcloud-config, nextcloud-restore-db, beszel-user, beszel-agent-key | auto | the stack | login or API answers
Homepage | homepage-files | auto | folders, tailscale-login, restore-configs | config files rendered for this machine
Homepage | w-adguard, w-beszel, w-netdata, w-speedtest, w-portainer, w-filebrowser, w-immich, w-nextcloud | auto | the app | widget works against the live app
Homepage | w-tailscale | manual | tailscale-login | needs an API token you create (no API to mint one)
Scripts | scripts, backup-conf, cron, cron-backup, login-hook | auto | scripts | installed copies match the repo; cron lines present; hook in `.bashrc`
Devices | data-drive | manual (optional) | | `/mnt/storage` is a mount point
Devices | secrets-saved, devices-dns, speedtest-login, reboot-test | ack | | you confirm with `done ID`
Devices | blocklists, weather | ack (optional) | | confirm or `skip ID`

Run `sudo homelab-setup` for the live version.

## 7. Homepage widgets and keys

Text edits keep the file's comments and order. Widgets that need a key are **stripped at first** and re-inserted from the repo template only after the key passes a live test. This avoids the Nextcloud 429 brute-force lockout we hit before.

| Widget | How the key is made | Live test |
|---|---|---|
| AdGuard Home | Basic auth with the admin account | status endpoint |
| Tailscale | device id from `tailscale status --json` (`Self.ID`); API token **by hand** | api.tailscale.com device endpoint |
| Beszel | superuser upserted with `docker exec beszel /beszel superuser upsert EMAIL PASSWORD` | PocketBase auth |
| Netdata | none | `/api/v1/info` |
| Speedtest Tracker | `artisan tinker` through stdin as user `abc`, token ability `results:read` | not 401/403 |
| Portainer | token named `homepage`, environment id from the endpoints list | stacks/endpoints call |
| FileBrowser | first-run password from the container log, then `PUT /api/users/1` to set yours | login |
| Immich | login, then API key with `server.statistics` | statistics call |
| Nextcloud | `occ config:app:set serverinfo token` | OCS call with `NC-Token` |

After a failed test the same check is not repeated for 10 minutes (state note `vf:ID`).

## 8. Secrets and safety rules

- The typed password lives only in memory. Tests assert it is absent from `state.json`, `secrets.env`, the log and everything under `/root` and `/var`. It is also masked in the log if it ever appears in a command line. The three Homepage logins in `services.yaml` keep it in plain text by design, as the working server does today.
- Known leak: while the Beszel superuser is created, the password is briefly visible in `ps` (the Beszel image has no shell to feed it through stdin).
- `/root/.homelab-setup/` is mode 700 and `secrets.env` is mode 600. State: `/var/lib/homelab-setup/state.json` (600). Log: `/var/log/homelab-setup.log`. Progress: `/var/lib/homelab/setup-progress`.
- The installer never runs `mkfs`, `wipefs`, `parted`, `fdisk`, `chattr` or `mount`. Drives are the person's job (`sudo drives`).
- Every changing command goes through `act()`, which `--dry-run` prints instead of running.
- Restore never overwrites: `restore-data` refuses if the Immich or Nextcloud folders already have files or if there is not enough free space; `restore-configs` is refused when the backup belongs to a different username; the Nextcloud database load needs you to type `RESTORE`.
- Port 53 is never freed over a Tailscale SSH session (it would cut you off).

## 9. Commands

```
sudo homelab-setup                 checklist
sudo homelab-setup install         set everything up (asks first, safe to re-run)
sudo homelab-setup install --dry-run
sudo homelab-setup refresh         re-scan and continue what is now possible
sudo homelab-setup fill            walk through keys and logins that need you
sudo homelab-setup done STEP       confirm a by-hand step    (skip STEP: not wanted)
sudo homelab-setup secrets         show the generated passwords
homelab-setup progress | version | help
Options: --yes  --backup FOLDER  --no-restore  --repo FOLDER  --all  --force-existing
```

`install` is also the right way to continue after a failure: it logs in to Tailscale and asks the questions that `refresh` leaves to `fill`.

## 10. Repo layout (what to add)

```
setup.sh                          starter: checks python3, then runs homelab-setup
.gitattributes                    keeps LF line endings
SECRETS-CHECKLIST.md
homelab-setup/homelab-setup       the installer (one file, Python 3 standard library)
homelab-setup/SETUP-PROMPT.md     this file
homelab-setup/VM-TEST-GUIDE.md
homelab-drives/homelab            version 1.6 (adds the setup progress line)
```

After adding, rebuild `SHA256SUMS`. README and TROUBLESHOOTING stay untouched until Brandon says.

## 11. Test plan

Simulated here (85 checks, all passing): full install on a blank Mint machine; second run changes nothing; dry-run changes nothing; password rules and no leak into files or logs; port 53 refused over Tailscale SSH and done from the LAN; Docker/Tailscale key download failure and recovery; `apt` failure; Portainer first-login window closed; Portainer with no local environment; Beszel account created three ways; Speedtest token failure; a wrong Tailscale key refused; Docker Hub throttle; restore of settings, photos and a Nextcloud dump; restore not confirmed; backup from another user; no backup and `--no-restore`; the existing server in read-only mode (43 of 43 steps, nothing written); the login screen line (71 checks).

Not provable without a real machine: see section 12 and `VM-TEST-GUIDE.md`.

## 12. Unverified assumptions (test these on a VM first)

1. Tailscale apt repository URLs and key location for `noble` and `jammy`.
2. Beszel `create-user` request body (the installer tries several shapes) and `superuser upsert`.
3. Portainer treats `env_file: stack.env` correctly when a stack is created through the API with variables.
4. Portainer auto-creates the local environment on first start.
5. Speedtest Tracker `artisan tinker` command and token ability name.
6. FileBrowser `PUT /api/users/1` payload.
7. AdGuard `dns_config` partial update keeps the other settings.
8. Nextcloud trusted domains (127 versus LAN address) after first install.
9. Immich restore from database dumps stays manual (a new admin would block it); Nextcloud database restore is untested against a real dump.
10. Image pull times and Docker Hub rate limits on a fresh network.
11. Real Mint and Ubuntu Server differences (package names, `ss` output, `resolv.conf` handling).

## 13. The master prompt

Paste everything below this line into a new chat, then attach `homelab-setup/homelab-setup` (and this file) or the repo link.

```
You are helping Brandon (computer-engineering-technology student, job-searching for IT help-desk roles) maintain "homelab-setup", a one-file Python 3 installer that rebuilds his home lab from this repo: https://github.com/IbrandonrtI/My-Home-Lab- (public). The target is a fresh Linux Mint or Ubuntu Server machine. The original server is "pc" (HP ProDesk 600 G3 Mini, Linux Mint 22.3, 16 Docker containers, Tailscale-only access).

Read homelab-setup/SETUP-PROMPT.md in the repo first. It is the spec: decisions, value substitution, steps, safety rules, unverified assumptions.

Working rules:
- Plain language. One server-changing step at a time; wait for my pasted output. Name the terminal for each command. End each message with a "Send me" list.
- Never ask me to paste a secret. Never write a secret into a repo file. The admin password I type is kept in memory only.
- Never format or modify a drive. Never change the DNS design (AdGuard Home on this machine, devices set DNS by hand) without asking.
- Do not edit README or TROUBLESHOOTING until I say. Commit or push only when I ask.
- Every step in the installer has probe() (live truth), needs, and a safe re-run. Anything that changes the machine goes through act() so --dry-run works.
- Test by simulation first (fake machine and fake web services), then tell me honestly what only a real VM can prove.
- Count only real problems.

My task now: <describe what you want changed or debugged>.
```
