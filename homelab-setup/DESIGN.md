# homelab-setup: design document

This document describes the design of `homelab-setup`, the installer that turns a fresh Linux machine (Linux Mint or Ubuntu Server) into a copy of this home lab by using the files in this repository. It records the decisions behind the installer, the checklist it maintains, its safety rules and what has and has not been verified, in enough detail to maintain it or to rebuild it from scratch.

Related files:

- `INSTALL.md` (repository root): the short guide for a first-time installer.
- `homelab-setup/homelab-setup`: the installer (one file, Python 3 standard library only).
- `homelab-setup/VM-TEST-GUIDE.md`: how to test the installer on a disposable virtual machine.
- `setup.sh`: starter script that checks for Python 3 and runs the installer.
- `SECRETS-CHECKLIST.md`: every password and key the lab needs, and where each one lives.

Status: tested against a simulated machine (fake `apt`, Docker, Tailscale and web services for every application) and on a real Linux Mint 22.3 virtual machine (two clean installs). Section 13 lists what is still unverified.

---

## 1. Overview

On a blank machine:

```
sudo apt update && sudo apt install -y git
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git
cd My-Home-Lab-
sudo bash setup.sh install --dry-run     # shows what would be done, changes nothing
sudo bash setup.sh install               # asks a few questions, then builds the lab
```

The installer:

1. Updates and upgrades the system.
2. Installs Docker, Tailscale and the helper programs.
3. Starts Portainer, creates its admin account and deploys nine stacks **through the Portainer API**, so the stacks stay editable in Portainer: AdGuard Home, Beszel, Netdata, Speedtest Tracker, FileBrowser, Immich, Nextcloud, Homepage and the Beszel agent.
4. Fills in every machine-specific value (user, IP address, Tailscale name, keys) and enables the Homepage widgets, each one **tested against the live application** before its key is written.
5. Installs the helper scripts (`homelab`, `homelab-update`, `drives` and the backup tools), their cron jobs and the login-screen summary.
6. Prints a **checklist** of what is done and what remains. `sudo homelab-setup refresh` scans the machine again and shows what is left. Until every step is complete, the login screen shows one line: `Setup N of M steps done: run homelab-setup`.

The installer never formats or changes a drive, never stores the administrator password it asks for, and never writes a secret into the repository or a log.

## 2. Design principles

- **The machine is the source of truth.** Every step has a `probe()` that inspects the live machine. The checklist is always computed from probes, never from a record of what was run, so re-running is safe and never repeats finished work.
- **Automate what can be verified.** A step is automatic only when the installer can confirm the result. Anything that needs a person (a Tailscale login, a drive, an API token that cannot be created through an API) is a guided manual step.
- **Test before writing.** A Homepage widget key is written only after a live request with that key succeeds.
- **Explain before changing anything sensitive.** Freeing port 53, restoring data and similar actions are described first and, where relevant, confirmed.
- **Secrets stay out of the repository.** The repository holds placeholders or the original server's values; generated secrets live in Portainer stack variables and in one root-only file.
- **Readable output.** Messages are written in the third person or the imperative, describe the machine's state, and show every command to run on its own highlighted line (section 8).

## 3. Design decisions

| Topic | Decision | Rationale |
|---|---|---|
| Deploy method | Portainer API; the stacks stay editable in Portainer | Matches how the original server is managed. The administrator password is entered once and never written to a file |
| Admin accounts and widget keys | Created through each application's API where one exists, written to the Homepage configuration and **tested**; the rest become guided checklist steps | Reduces manual work without trusting an untested key |
| Configuration source | Stack files and the Homepage configuration always come from the repository. If a backup is found, saved settings are restored with `homelab-restore-configs` | One source of truth, plus a path back to a previous state |
| Photos and files (roughly 60 GB) | Restored from a backup drive or folder when one is present; otherwise the services start empty | Restoring is optional and never overwrites existing data |
| Storage | `/mnt/storage` starts as a plain folder on the boot drive. `sudo drives` is a checklist step. The installer never formats or touches a drive | Destroying a disk by mistake is the worst failure this tool could cause |
| Secrets | Portainer stack variables plus one root-only file (`/root/.homelab-setup/secrets.env`, mode 600) displayed once. Nothing in the repository | Keeps the repository public-safe |
| Passwords | One administrator password, entered by the person running the installer and reused for every application login. A risk warning is displayed | One password to remember during a rebuild; the trade-off is shown explicitly |
| Port 53 | May be freed by stopping `systemd-resolved`, as the README describes. The installer explains first and refuses to do it over a Tailscale SSH session | AdGuard Home needs port 53; losing the SSH session mid-change would strand the machine |
| DNS on the machine itself | `/etc/resolv.conf` lists the router; Tailscale runs with `--accept-dns=false` | With `systemd-resolved` stopped, Tailscale rewrites `resolv.conf` to 100.100.100.100 and can lose its upstream servers, so name lookups fail after a reboot or update. Every `tailscale up` run by the installer repeats `--accept-dns=false`, because Tailscale refuses a login that does not restate all non-default settings. Side effect: the machine itself cannot resolve `*.ts.net` names (other devices can), so on the machine use its LAN address |
| DNS design | AdGuard Home runs on this machine; client devices set their DNS server by hand | Documented in the README; not changed by the installer |
| Testing | Virtual machine or spare PC; simulation for everything else | The installer is destructive by design and must not be tried on the production server |
| Login screen | One line, `Setup N of M steps done: run homelab-setup`, until the checklist is complete | A visible reminder without noise |
| Installed extras | The helper scripts in `/usr/local`, the cron entries and the login hook. AnyDesk, automatic login and VS Code are not installed | Keeps the installer to what the lab needs |
| Existing server | If seven or more stacks already run and the installer has never run, it works read-only (`--force-existing` overrides) | Protects the production server from an accidental install |
| Install source | The repository clone the installer was started from; the path is saved so later runs use the same copy | Avoids two diverging copies |
| Python | Python 3 standard library only, 3.7 or newer | Present on Linux Mint and Ubuntu Server without extra packages |
| Backup schedule | The daily backup cron entry (06:00) is added only once `/mnt/storage` is a real mount point; it is dropped from the checklist when the data drive is skipped | The backup script refuses to run onto the boot drive |
| Weather | A city is asked at install and looked up with Open-Meteo's free geocoding service (no key). The coordinates are written into `widgets.yaml`. If the service cannot be reached, the repository default (New York) stays and the weather step remains on the list until the coordinates are changed by hand | The location is personal, and typing a city is easier than editing coordinates |
| AdGuard Home blocklists | Added by the installer through AdGuard Home's API: HaGeZi's Pro Blocklist and Peter Lowe's Blocklist, on top of the defaults. A list that is already present is not duplicated; a disabled one is switched on | Removes a manual step; the lists can be changed in AdGuard Home at any time |
| FileBrowser folders | Named by the role of the drive: `boot-drive` (the `~/750GB_HDD` folder on the boot drive), `main-storage` (`/mnt/storage/filebrowser`) and, when a backup drive is connected, `backup` (`/mnt/backup`, read and write). The installer rewrites the stack file when it deploys FileBrowser on a new machine; the repository file `Portainer-code/filebrowser.yaml` (the production server's `hdd` and `750GB_HDD` names) is not changed. The `filebrowser-drives` step compares the folders FileBrowser has mounted with the drives present and redeploys the stack through Portainer on `refresh` when a drive is connected or removed | The original names describe the original hardware; backup access from FileBrowser was already part of the design |
| Final screen | Every `install`, `refresh` and checklist run ends with a **Next step** section (the one step to do next, with its command). When all steps are complete it becomes a **System check** (containers, Tailscale, DNS, every service address). `sudo homelab-setup verify` runs the system check at any time | The next command is always the last thing on the screen |
| Passwords step | `secrets-saved` is marked when `sudo homelab-setup secrets` has been run. The installer cannot verify that the passwords were saved elsewhere | A manual-only step could not be checked at all |
| Secrets display | The generated-passwords block is printed once at the end of the first install (`secrets_announced` in the state file); later runs do not print it again | Avoids repeating secrets on screen |

## 4. Value substitution

The repository files hold the original server's values or placeholders. The installer rewrites them for the new machine:

| In the repository | Becomes |
|---|---|
| `/home/brandon` | the new user's home directory |
| `192.168.1.198`, `192.168.X.X` | this machine's LAN address (detected, confirmed by the user) |
| `pc.griffin-luma.ts.net`, `pc.your-tailnet.ts.net` | this machine's full Tailscale name (`Self.DNSName`) |
| `griffin-luma.ts.net`, `your-tailnet.ts.net` | the tailnet name |
| `PUID` / `PGID` | the new user's ids |
| Speedtest Tracker `APP_KEY` | generated (`base64:` followed by 32 random bytes) |
| Beszel agent `KEY` / `TOKEN` | fetched from the new Beszel hub |
| Immich environment | `UPLOAD_LOCATION`, `DB_DATA_LOCATION`, `TZ`, `IMMICH_VERSION`, `DB_PASSWORD` (generated), `DB_USERNAME=postgres`, `DB_DATABASE_NAME` |
| Nextcloud environment | `NC_ADMIN_USER`, `NC_ADMIN_PASSWORD` (the administrator password entered), `NC_DB_PASSWORD` (generated, or reused from a restored `config.php`) |
| Homepage widget placeholders (`your-own-key`, device id and so on) | real values, written only after a live test passes |

## 5. Phases

The installer is a list of **steps**. Each step has a `probe()` that reports `done`, `todo` or `na` (not applicable), declares the steps it `needs`, and runs in dependency order. A step is one of three kinds:

- `auto`: the installer performs it.
- `manual`: a person performs it, with a guided walk-through (`fill`).
- `ack`: a person confirms it with `done`, or the installer detects it automatically (self-checking steps, section 6).

Phases, in order:

1. **Questions** (once): administrator name, email address, time zone, a city for the weather card (looked up online; several matches are listed for a choice), LAN address, then the shared password (12 or more letters and digits, typed twice, kept in memory only), then the restore choice if a backup is found.
2. **System**: `apt update` and `upgrade`, helper packages, Docker (from Docker's apt repository, deb822 format), docker group membership.
3. **Tailscale**: installation from `pkgs.tailscale.com`, login through a link (or `TS_AUTHKEY`), MagicDNS and HTTPS certificates enabled in the Tailscale admin page, then `tailscale serve` maps HTTPS ports 1000 to 1008 to the LAN ports.
4. **Network**: free port 53 for AdGuard Home (explained, confirmed, refused over Tailscale SSH); keep Tailscale from managing DNS.
5. **Platform**: folders with the correct owners, the secrets file, Portainer, its admin account, an API token for the installer, the local Docker environment, optional restore of settings and data.
6. **Services**: the nine stacks. Images are pulled one at a time with retries on Docker Hub rate limits; stacks are deployed through the Portainer API; each is checked until its containers run.
7. **Logins and keys**: AdGuard Home first run, upstream DNS and blocklists; Immich administrator; Nextcloud installation, trusted domains and optional database restore; Beszel hub account and agent key.
8. **Homepage**: configuration files for this machine, then each widget (section 9).
9. **Scripts and schedule**: scripts, backup settings, cron lines, login hook.
10. **Devices and drives**: data drive, saved secrets, client DNS, first Speedtest run, blocklists, weather, reboot test.

## 6. Checklist catalogue

59 steps are defined. Steps that do not apply to a machine are hidden, so a fresh machine shows 56 and the existing server shows 43.

Group | id | kind | needs | what the probe checks
---|---|---|---|---
System | os | auto | | supported operating system
System | apt-upgrade | auto | | system packages are up to date
System | packages | auto | os | curl, ca-certificates, gnupg, rsync, cron, smartmontools, hdparm, python3-yaml, mergerfs and similar
System | docker | auto | os, packages | `docker info`, Compose and Buildx work
System | docker-group | auto | docker | the user is in the group `docker`
Tailscale | tailscale-install | auto | os, packages | `tailscale` is installed
Tailscale | tailscale-login | manual | tailscale-install | `Self.DNSName` is present
Tailscale | tailscale-https | manual | tailscale-login | `CertDomains` is not empty
Tailscale | tailscale-serve | auto | tailscale-login, tailscale-https | the nine serve mappings match
Network | port53 | auto | docker | only AdGuard Home listens on port 53
Network | dns-stable | auto | tailscale-install, port53 | `/etc/resolv.conf` has a nameserver and no `100.100.100.100` (Tailscale set to `--accept-dns=false`); not shown on the existing server
Platform | folders | auto | os | `/mnt/storage/{immich,filebrowser,nextcloud}`, `~/nextcloud/{html,db}`, `~/immich/postgres`, `~/speedtest-tracker`, `~/homepage-config`, `~/750GB_HDD`, `/opt/adguard-docker/{conf,work}`
Platform | secrets | auto | os, restore-configs | the secrets file has `DB_PASSWORD`, `NC_DB_PASSWORD` and `APP_KEY` (and matches a restored `config.php`)
Platform | portainer, portainer-admin, portainer-token, portainer-env | auto | chain | container, admin account, API token, local environment
Platform | restore-configs, restore-data | auto | folders | only when a restore was chosen
Services | filebrowser-drives | auto | stack-filebrowser | the folders mounted in the FileBrowser container (`docker inspect`) are exactly `/srv/boot-drive`, `/srv/main-storage` and, when `/mnt/backup` is a mount point, `/srv/backup`. Not shown on the existing server
Services | stack-adguard, -beszel, -netdata, -speedtest-tracker, -filebrowser, -immich, -nextcloud, -homepage, -beszel-agent | auto | portainer-env and per-stack needs | containers are running
Logins and keys | blocklists | auto (optional) | adguard-setup | three or more `enabled: true` entries under `filters:` in `AdGuardHome.yaml`; the step adds HaGeZi Pro and Peter Lowe's through `/control/filtering/add_url` (or switches a disabled copy on with `set_url`). Not shown on the existing server
Logins and keys | adguard-setup, adguard-dns, immich-admin, nextcloud-ready, nextcloud-config, nextcloud-restore-db, beszel-user, beszel-agent-key | auto | the stack | login or API answers
Homepage | homepage-files | auto | folders, tailscale-login, restore-configs | configuration files rendered for this machine
Homepage | w-adguard, w-beszel, w-netdata, w-speedtest, w-portainer, w-filebrowser, w-immich, w-nextcloud | auto | the application | the widget works against the live application
Homepage | w-tailscale | manual | tailscale-login | needs an API token created by hand (no API can create one)
Scripts and schedule | scripts, backup-conf, cron, cron-backup, login-hook | auto | scripts | installed copies match the repository; cron lines present; hook in `.bashrc`
Your devices and drives | data-drive | manual (optional) | | `/mnt/storage` is a mount point
Your devices and drives | secrets-saved | ack, self-checking | | `sudo homelab-setup secrets` has been run (`secrets_shown` in the state file). The installer cannot confirm that the passwords were saved
Your devices and drives | devices-dns | ack, self-checking | adguard-setup | AdGuard Home's `/control/stats` `top_clients` contains an address that is not loopback, link-local, this machine or a Docker network (172.16.0.0/12, unless the LAN itself is in that range). Uses the AdGuard login saved in the Homepage widget
Your devices and drives | speedtest-first | ack, self-checking | w-speedtest | `GET /api/v1/results/latest` with the widget token answers 200 (a first test has run). Replaces a manual "log in" step, because the installer already sets that login
Your devices and drives | reboot-test | ack, self-checking | stack-homepage | 16 containers are running and `/proc/sys/kernel/random/boot_id` differs from the value recorded the first time the lab was seen running (`boot_seen` in the state file)
Your devices and drives | weather | ack (optional), self-checking | homepage-files | a city was written into `widgets.yaml` at install (`weather_set` in the state file), or the `openmeteo` latitude and longitude differ from the repository default (40.7128, -74.0060)

Self-checking steps are evaluated on every checklist run. Once one is seen to be true it is remembered (`autodone` in the state file) and does not revert. A cron job runs `homelab-setup progress` every 10 minutes, which evaluates every probe, so these steps tick by themselves without `refresh`. `done ID` and `skip ID` also work for every one of them.

`sudo homelab-setup` displays the live checklist.

## 7. Checklist behaviour

- `evaluate()` assigns each step a state in this order: not applicable, skipped, confirmed, blocked (a required step is not done), then the result of `probe()`.
- A step that failed shows the last error beneath it until it succeeds.
- The checklist is compact: one line per step, tagged `you do this` (a step that only a person can do) or `detected automatically` (a self-checking step), and details for open steps only in the **Next step** section. `sudo homelab-setup --details` prints the full instructions of every open step.
- Each run ends with a **Next step** section: the title of the first step that is not done, its instructions and its command, then `sudo homelab-setup refresh` to check progress. When every step is complete the section is replaced by a **System check**: containers (16 expected, including Portainer), Tailscale, DNS, and a live request to every service on its local address, followed by the Tailscale addresses. `sudo homelab-setup verify` shows it on demand.
- `install` on a machine whose steps are all complete prints "Nothing to do: all steps are complete" and asks nothing.
- The summary line (`N of M steps done`) is written to `/var/lib/homelab/setup-progress` for the login screen, and removed when everything is done.
- When the data-drive step is not done or is skipped, the installer writes `/var/lib/homelab/no-data-drive`. The `homelab` login script then shows a grey "no data drive set up yet" line in place of a red "NOT MOUNTED" error. The marker is never written in read-only mode.
- `refresh` runs the installed copy at `/usr/local/sbin/homelab-setup`, which replaces itself during the run; a new build therefore takes effect on the following run.

## 8. Output conventions

**Screens of an install.** In order: a welcome screen (what is installed, 30 to 60 minutes, about 10 GB, what to have ready); the preflight checks; the questions; the planned steps, grouped (one line per group with the number of steps and a short description, then the steps that need a person, each tagged `during the install` or `afterwards`); `Type yes to start`; the installation; **Install finished** (time taken, steps done, the Homepage address when it answers); **Generated passwords and keys** (shown once; on a terminal the installer waits for Enter, which also ticks the passwords step); the compact checklist; **Next step** (or the **System check** when everything is done).

**Run the next command with Enter.** A terminal cannot make text clickable in a way that runs it (a security rule of terminals), so at a real terminal the Next step ends with `Press Enter to run ... now, or type n to stop`. Enter runs the walk-through (`fill`) for a step that has one, otherwise the re-check (`refresh`); `skip` is offered for an optional step; `n` stops. After each action the installer re-checks and shows the next step, so Enter can be pressed through the steps. Only these commands are ever offered: never a drive tool, `done` (the self-checking steps must tick on their own) or a reboot. Nothing is asked when the output is not a terminal, with `--yes`, with `--dry-run` or on a machine that already runs the lab.

**Progress.** On a terminal, the bottom row of the window is reserved for one progress bar, the way `apt` does it: a spinner, the step, a detail (for example `downloading 3 of 9: immich-server`), a bar for the whole run (`n of m`) and the elapsed time. Everything else the installer prints scrolls above it. The row is reserved by setting the terminal's scrolling area to every row but the last (`ESC[1;<rows-1>r`) and the bar is painted at an absolute position in one write (save the cursor, go to the last row, write the bar with automatic wrapping off, put the cursor back), so it never depends on where the cursor is or on how the terminal re-wrapped earlier output. Two earlier designs drew the bar on the cursor's own row and erased it by counting wrapped rows (upload 21) or by keeping the cursor at the start of the row (upload 22); both left frames strung together on the test VM even though a real xfce4-terminal in a virtual screen stayed clean, so that approach was dropped. The rows and width come from the terminal itself (`os.get_terminal_size`), never from the `COLUMNS` variable (a stale copy that `sudo` passes on). When the window changes size the reserved row is set up again for the new size (the old bar row is wiped from the cursor down first). Narrower than 46 columns the row is left empty, and shorter than 8 rows the bar is not used. While a step runs the typing echo is switched off (keys pressed during a long download would only add blank lines); keys typed meanwhile are discarded when the next question appears. `Live.close()` gives the row back at the end of a pass, before the final report, on an error and (through `atexit`) on any exit. `sim/t_pinned.py` runs the bar against a terminal emulator (`pyte`): messages above, bar once on the last row, nothing lost or repeated, repair after resizes, a blank row after closing; `sim/vte_resize_test.sh` drags a real xfce4-terminal window narrow and wide in a virtual screen. A resize can still leave one stray line in the text on a terminal that re-wraps (an old copy of the bar that the terminal moved before the program noticed). `HLS_LIVE=1` forces the bar for tests.

All installer text follows these rules.

**Voice.** Impersonal or imperative: "Docker is not installed yet", "Run `sudo homelab-setup fill`". No first person ("I will ..."), no references to a chat or conversation, no references to individual people.

**Commands and links.** Output that tells the reader to run something is written in one of two forms inside the step text:

- inline: wrap the command in backticks, for example `` `sudo homelab-setup refresh` ``;
- block: a paragraph that starts with `$ ` is printed on its own line, never wrapped, so it can be copied whole.

On a terminal, commands are drawn in bold cyan and URLs in underlined cyan; the surrounding text is dim, and normal formatting resumes after each highlighted item. When output is piped, when `NO_COLOR` is set or when `TERM=dumb`, the backticks are kept and block commands print as plain `$ command` lines. `HLS_COLOR=1` forces colour for testing. The markup engine lives in the first section of the installer (`mark()`, `styled()`, `wrap()`).

**Messages.** State what happened and what to do next. Errors name the step and the reason. Prompts that need an answer print a clear label and no trailing punctuation clutter.

## 9. Homepage widgets and keys

Text edits preserve the file's comments and order. Widgets that need a key are **removed at first** and re-inserted from the repository template only after the key passes a live test. This avoids Nextcloud's brute-force lockout (HTTP 429), which repeated failed logins trigger.

| Widget | How the key is made | Live test |
|---|---|---|
| AdGuard Home | Basic authentication with the administrator account | status endpoint |
| Tailscale | device id from `tailscale status --json` (`Self.ID`); the API token is created **by hand** | api.tailscale.com device endpoint |
| Beszel | superuser created with `docker exec beszel /beszel superuser upsert EMAIL PASSWORD` | PocketBase authentication |
| Netdata | none | `/api/v1/info` |
| Speedtest Tracker | a PHP script passed on stdin as user `abc` (the image has no `tinker`) boots Laravel, sets the login and calls `createToken('homepage', ['results:read'])` | response is not 401 or 403 |
| Portainer | token named `homepage`; environment id from the endpoints list | stacks or endpoints call |
| FileBrowser | first-run password from the container log, then `PUT /api/users/1` (with `current_password`) to set the chosen login | login |
| Immich | login, then an API key with `server.statistics` | statistics call |
| Nextcloud | `occ config:app:set serverinfo token` | OCS call with `NC-Token` |

On a new machine the first resources pill (labelled `ProDesk` in the repository file, the original server's name) is renamed to the machine's host name, and the weather card gets the chosen city.

After a failed test, the same check is not repeated for 10 minutes (state note `vf:ID`), unless a key was just written and passed its test, which clears the note. The Speedtest Tracker widget reports an error until the first speed test has produced a result.

## 10. Secrets and safety rules

- The administrator password lives only in memory. Tests assert that it is absent from `state.json`, `secrets.env`, the log and everything under `/root` and `/var`. It is also masked in the log if it appears in a command line. The three Homepage logins in `services.yaml` keep it in plain text by design, as the production server does.
- The password is verified every time it is entered. At the start it is typed twice. On later runs it is checked against the Portainer admin account (or typed twice if that account does not exist yet), because a typo would otherwise give some applications a different password from the others.
- Known exposure: while the Beszel superuser is created, the password is briefly visible in the process list (the Beszel image has no shell to feed it through stdin).
- `/root/.homelab-setup/` is mode 700 and `secrets.env` is mode 600. State: `/var/lib/homelab-setup/state.json` (mode 600). Log: `/var/log/homelab-setup.log`. Progress: `/var/lib/homelab/setup-progress`.
- The installer never runs `mkfs`, `wipefs`, `parted`, `fdisk`, `chattr` or `mount`. Drive preparation is a manual step (`sudo drives`).
- Every command that changes the machine goes through `act()`, which `--dry-run` prints instead of running.
- Restore never overwrites. `restore-data` refuses if the Immich or Nextcloud folders already contain files or there is not enough free space. `restore-configs` is refused when the backup belongs to a different username. The Nextcloud database load requires typing `RESTORE`.
- Port 53 is never freed over a Tailscale SSH session.

## 11. Commands

```
sudo homelab-setup                 show the checklist
sudo homelab-setup install         set everything up (asks first, safe to re-run)
sudo homelab-setup install --dry-run
sudo homelab-setup refresh         re-scan and continue whatever is now possible
sudo homelab-setup verify          system check: every container and service answering
sudo homelab-setup fill            walk through the keys and logins that need a person
sudo homelab-setup done STEP       confirm a manual step       (skip STEP: not wanted)
sudo homelab-setup secrets         show the generated passwords
homelab-setup progress | version | help
Options: --yes  --backup FOLDER  --no-restore  --repo FOLDER  --all  --details  --force-existing
```

`install` is also the way to continue after a failure: it shows the Tailscale login link when one is needed and asks the questions that `refresh` leaves to `fill`.

## 12. Repository layout and tests

```
INSTALL.md                        quick start for a first-time installer
setup.sh                          starter: checks for python3, then runs homelab-setup
.gitattributes                    keeps LF line endings
SECRETS-CHECKLIST.md
homelab-setup/homelab-setup       the installer
homelab-setup/DESIGN.md            this document
homelab-setup/VM-TEST-GUIDE.md
homelab-drives/homelab            login screen script, version 1.7 (shows the setup progress line)
homelab-drives/SHA256SUMS
```

`SHA256SUMS` must be regenerated whenever a script it lists changes. Files uploaded through the GitHub web interface lose the executable bit, so the documentation always runs `sudo bash setup.sh`.

Simulation tests (run against a fake machine; environment hooks `HLS_ROOT`, `HLS_FAKE`, `HLS_USER`, `HLS_LAN`, `HLS_GATEWAY`, `HLS_HOST`, `HLS_TS_API`, `HLS_TS_WAIT`, `HLS_NO_THROTTLE`, `HLS_FETCH_FAIL`, `HLS_BOOT_ID`, `HLS_COLOR`, `HLS_LIVE`, `HLS_MOUNTED`, `HLS_MOUNTED_BACKUP`, `HLS_GEOCODE_API`):

- **Installer suite (177 checks):** full install on a blank Mint machine; second run changes nothing; dry run changes nothing; password rules and no leak into files or logs; port 53 refused over Tailscale SSH and freed from the LAN; DNS stays stable and Tailscale login works again after `--accept-dns=false`; Docker and Tailscale key download failure and recovery; `apt` failure; Portainer first-login window closed; Portainer with no local environment; Beszel account created three ways; Speedtest token failure; a wrong Tailscale key refused; Docker Hub throttle; restore of settings, photos and a Nextcloud dump; restore not confirmed; backup from another user; no backup and `--no-restore`; the weather city question (lookup unreachable, unknown name, several matches); blocklists added through the API, refused by AdGuard Home and a disabled list switched on; the self-checking steps; the passwords step; a second run that has nothing to do; dry-run output; FileBrowser folders following a backup drive that appears and disappears; the Next step section and the System check (including a stopped container); highlighted commands and links; the order of the end-of-install screens, the grouped plan, the compact checklist, the pinned progress bar and its repair after a resize, a full install on a pseudo-terminal (the Enter pause ticks the passwords step) and the Homepage pill named after the machine.
- **Login screen suite (74 checks):** the `homelab` script's setup line and the no-data-drive note.
- **Existing server:** read-only run on a simulated production server (43 of 43 steps, nothing written).

## 13. Verification status

Verified on a real Linux Mint 22.3 virtual machine (two clean installs): system and Docker installation; Tailscale installation, login and re-login; HTTPS serve mappings (opened from a second device on the tailnet); Portainer first-run setup token; nine stacks deployed through the API; Beszel hub account and agent key; Speedtest Tracker token creation; FileBrowser login change; Nextcloud first install and trusted domains; all Homepage widgets; DNS after a reboot; the login screen line and the no-data-drive note.

Not yet verified on a real machine:

1. Ubuntu Server (package names, `ss` output, `resolv.conf` handling); only Linux Mint has been run.
2. Restore of saved settings, photos and a Nextcloud database dump from a real backup. A restored Nextcloud `config.php` may name an `oc_...` database user (Nextcloud creates one itself on a first install); only the password of a user named `nextcloud` is reused. Restoring a dump that belongs to an `oc_` user is untested.
3. Immich restore from database dumps remains manual (a new administrator would block it).
4. The daily backup schedule onto a real mounted drive.
5. The self-checking steps (devices using AdGuard Home, first speed test, reboot) against real AdGuard Home and Speedtest Tracker responses (verified only against simulated services).
6. AdGuard Home's `/control/filtering/add_url` and `set_url` calls and Open-Meteo's geocoding response format against the real services (verified only against simulated services).
7. Image pull times and Docker Hub rate limits on a fresh network.
8. The progress bar was drawn in a terminal emulator (`pyte`) and in a real xfce4-terminal in a virtual screen, also through `sudo`. On the real VM, uploads 19 to 22 left stray or repeated frames when the window was resized, which a virtual screen never reproduced; upload 23 pins the bar to the last row instead (not yet seen on the VM). Terminals that do not re-wrap on resize (xterm) have not been checked.

## 14. Maintenance guide

Conventions for changing the installer:

- Every step has a `probe()` that reads the live machine, a `needs` list and a safe re-run. Anything that changes the machine goes through `act()` so `--dry-run` works.
- Follow the output conventions in section 8. Put commands in backticks or on `$ ` lines; do not write instructions as prose that hides the command.
- Never write a secret into a repository file, a log or the state file, and never format or modify a drive.
- Do not change the DNS design (section 3) without a deliberate decision.
- Add or update a simulation check for every behaviour change, then run the full suites. Record anything that only a real machine can prove in section 13.
- The README and TROUBLESHOOTING documents are maintained separately. The README uses placeholders (`your-username`, `192.168.X.X`, `your-tailnet.ts.net`, `your-own-key`); TROUBLESHOOTING and the `Portainer-code` stack files keep the original server's real values on purpose.

Context block for an assistant or new maintainer:

```
Project: "homelab-setup", a one-file Python 3 installer that rebuilds a Docker home lab from the repository
https://github.com/IbrandonrtI/My-Home-Lab- on a fresh Linux Mint or Ubuntu Server machine. The original
server ("pc", Linux Mint 22.3, 16 Docker containers, Tailscale-only access) is the reference.

Read homelab-setup/DESIGN.md first: it records the decisions, the value substitution, the step
catalogue, the safety rules and the unverified assumptions.

Rules: keep secrets out of the repository; never format or modify a drive; route every changing command
through act(); give every step a probe(); keep output impersonal with commands on their own highlighted
lines; test in simulation first and state plainly what only a real machine can prove.
```
