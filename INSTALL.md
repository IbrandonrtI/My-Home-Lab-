# Installing the home lab on a fresh machine

This is the short version. One program, `homelab-setup`, builds the whole lab on a fresh Linux Mint or Ubuntu machine: Docker, Tailscale, Portainer, Homepage, AdGuard Home, Beszel, Netdata, Speedtest Tracker, FileBrowser, Immich and Nextcloud. The [README](README.md) explains what each piece does, and the [build guide](docs/build-guide.md) does the same thing by hand.

It takes about 30 to 60 minutes, mostly downloads (around 10 GB). It asks a few questions at the start and when it needs you. The rest runs on its own.

## What you need

| Item | Notes |
| --- | --- |
| A machine | Linux Mint 22 or Ubuntu 24.04 with internet and about 20 GB free (more once you add photos and files). 8 GB of memory is a good idea. |
| A free Tailscale account | <https://tailscale.com>. You sign in once, in a browser on any device. |
| A password manager | The installer makes several passwords and shows them once. |
| The machine's own screen and keyboard | Run the installer there, not over SSH through Tailscale. It frees port 53 for AdGuard Home, and that cuts a Tailscale SSH session. SSH on your home network is fine. |

A drive for photos and backups is optional and can be added later. The installer never formats or changes a drive.

## Install

Open a terminal on the machine and run these three blocks one after the other.

Get the files:

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git
cd My-Home-Lab-
```

Look at what would happen first (changes nothing, asks nothing):

```bash
sudo bash setup.sh install --dry-run
```

Then do it:

```bash
sudo bash setup.sh install
```

Use `sudo bash setup.sh`, not `./setup.sh`. Files downloaded from GitHub's web page lose their "executable" mark, so it needs `bash`.

## What you'll see

1. **Welcome screen.** What gets installed, how long it takes, what to have ready.
2. **Questions.** Your name, an email address (it becomes the login for Immich, Beszel and Speedtest Tracker, so type it carefully), time zone, a city for the weather card, the machine's address on your network, and then **one admin password** (12 or more letters and digits, typed twice). That one password is used for every admin login. The installer never saves it.
3. **The plan.** A short list of what will run and which steps need you. Type `yes` to start.
4. **Installing.** A status line at the bottom shows the current step, a bar for the whole install and the time so far. Finished steps stay above it with a tick.
5. **Tailscale login.** A link appears. Open it in a browser on any device, sign in and approve the machine. The installer carries on by itself.
6. **Tailscale HTTPS.** If HTTPS certificates aren't on in your Tailscale account yet, it shows where to switch them on (<https://login.tailscale.com/admin/dns>) and waits for Enter.
7. **Port 53.** It explains that it will stop the built-in DNS resolver so AdGuard Home can use port 53, and asks first. Answer `y`.
8. **Install finished.** The time it took, how many steps are done, and the address of Homepage, the dashboard.
9. **Generated passwords and keys.** Shown once. Copy them into your password manager, then press Enter. They stay in a root-only file on the machine, and `sudo homelab-setup secrets` shows them again.
10. **Checklist and Next step.** A short list of what's done and what's left, then the one step to do next, with its command.

## After the install

Keep running the command the **Next step** section shows (usually `sudo homelab-setup refresh`). It checks the machine again, finishes whatever is now possible and names the next step. When everything is done, it turns into a **System check** that confirms every container and service answers.

The steps that need you are few:

| Step | What to do |
| --- | --- |
| Tailscale widget | `sudo homelab-setup fill` walks you through making an API token and tests it before saving it. |
| Data drive | Optional. Connect a drive and run `sudo drives`, or skip it with `sudo homelab-setup skip data-drive`. |
| Devices use AdGuard Home | Set a device's DNS server (or your router's) to the machine's address. The installer notices on its own. |
| First speed test | Log in to Speedtest Tracker and start a test. The installer notices on its own. |
| Reboot once | `sudo reboot`. The installer notices that everything came back. |

Handy commands:

```bash
sudo homelab-setup                # the checklist
sudo homelab-setup --details      # the checklist with full instructions for every open step
sudo homelab-setup refresh        # check again and continue
sudo homelab-setup verify         # check that every container and service is up
sudo homelab-setup secrets        # show the generated passwords again
sudo homelab-setup help
```

## If something goes wrong

- A failed step shows a red cross and the reason. Run `sudo bash setup.sh install` again. Finished steps are skipped and the failed one is retried.
- The log is `/var/log/homelab-setup.log` (the admin password is masked in it).
- The [troubleshooting guide](docs/troubleshooting.md) covers problems with the running lab. The [VM test guide](docs/vm-test-guide.md) shows how to try the installer on a throw-away virtual machine and how to start over.

## Restoring from a backup (optional)

If you have a backup of an earlier copy of this lab, connect it before the first install, or point the installer at it with `sudo bash setup.sh install --backup /path/to/backup`. Saved settings come back from it. Photos and files are copied back only when nothing is there yet. Nothing gets overwritten.

## How it works

The installer is one Python file with no dependencies, so it also works on a machine that has nothing installed yet. I build it from the pieces in `src/` with `bash tools/build.sh` (edit the pieces, not the built file).

**It's a checklist, not a script.** Every step has a check that looks at the real machine ("is Docker installed?", "is port 53 free?"). The checklist is always worked out from those checks, never from a record of what ran. So running it again is safe, and it only does what's still missing.

**Steps run in this order:**

1. Questions (once).
2. System: updates, helper packages, Docker.
3. Tailscale: install, login, HTTPS, and a mapping from HTTPS ports 1000 to 1008 to the services.
4. Network: free port 53 for AdGuard Home and stop Tailscale from taking over DNS.
5. Platform: folders with the right owners, the secrets file, Portainer and its API token.
6. The nine stacks, deployed through the Portainer API so they stay editable in Portainer.
7. Logins and keys for AdGuard Home, Immich, Nextcloud and Beszel.
8. Homepage: the config files, then each widget.
9. My helper scripts, their cron jobs and the login screen.
10. The things only a person can do: data drive, DNS on your devices, a first speed test and a reboot.

**What it fills in.** The files in this repo hold placeholders. The installer swaps in the real user and home folder (`/home/your-username`), the machine's address (`192.168.X.X`), the Tailscale name (`pc.your-tailnet.ts.net`), and the passwords and keys it generates.

**Rules it follows.**

- A Homepage widget key is written only after a live request with that key works. That avoids lockouts from repeated wrong logins.
- It never formats or changes a drive. `sudo drives` does that, separately, and asks you to type `ERASE`.
- It never saves the admin password. The generated passwords live in `/root/.homelab-setup/secrets.env` (readable only by root) and are shown once.
- Every command that changes the machine goes through one function, so `--dry-run` can print it instead of running it.
- Restoring never overwrites existing data, and the Nextcloud database restore needs you to type `RESTORE`.
- It won't free port 53 over a Tailscale SSH session.

**Tests.** `bash tests/run_all.sh` runs the installer against a fake machine (fake `apt`, Docker, Tailscale and fake web services for every app). The full run takes about 10 minutes, and `bash tests/run_all.sh quick` takes about one. The tests are listed in [tests/README.md](tests/README.md).

**What I've verified on a real machine.** Two clean installs on a Linux Mint 22.3 virtual machine: system and Docker, Tailscale login and HTTPS, the nine stacks, the Beszel and Speedtest Tracker keys, the Nextcloud first install, every Homepage widget, DNS after a reboot and the login screen.

**What I haven't verified yet.**

- Ubuntu Server. Only Linux Mint has been run.
- Restoring from a real backup (settings, photos and a Nextcloud database dump).
- The daily backup onto a real drive.
- The self-checking steps against real AdGuard Home and Speedtest Tracker responses. They've only run against fake ones.
- Image download times on a fresh network.
- The pinned progress bar in terminals that don't re-wrap on resize (xterm).
