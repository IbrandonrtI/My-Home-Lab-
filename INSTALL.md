# Install the home lab on a fresh machine

This is the short guide for a first install. It builds the whole lab (Docker, Tailscale, Portainer, Homepage, AdGuard Home, Beszel, Netdata, Speedtest Tracker, FileBrowser, Immich and Nextcloud) on a fresh Linux Mint or Ubuntu machine with one program, `homelab-setup`. The README explains what each part does; this page only covers getting it running.

Time: roughly 30 to 60 minutes, mostly downloads. Download size: about 10 GB. The installer asks questions at the start and when it needs you; the rest runs by itself.

## What you need

| Item | Notes |
|---|---|
| A machine | Linux Mint 22 or Ubuntu 24.04, with internet access and about 20 GB free (more once photos and files are added). 8 GB of memory is recommended. |
| A free Tailscale account | https://tailscale.com. You sign in once, in a browser on any device. |
| A password manager | The installer generates several passwords and shows them once. |
| The machine's own screen and keyboard | Run the installer there, not over an SSH session through Tailscale, because the installer frees port 53 for AdGuard Home and that interrupts such a session. A plain SSH session on the local network is fine. |

A drive for photos and backups is **optional** and can be added later. The installer never formats or changes a drive.

## Install

Open a terminal on the machine and run these three blocks, one after the other.

Get the files:

```
sudo apt update && sudo apt install -y git
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git
cd My-Home-Lab-
```

Look at what would happen (changes nothing, asks nothing):

```
sudo bash setup.sh install --dry-run
```

Do it:

```
sudo bash setup.sh install
```

Use `sudo bash setup.sh`, not `./setup.sh`. Files downloaded from GitHub's web page lose their "executable" mark, so `bash` is needed.

## What you will see

1. **Welcome screen.** What is installed, how long it takes, what to have ready.
2. **Questions.** Name, email address (it becomes the login for Immich, Beszel and Speedtest Tracker, so type it carefully), time zone, a city for the weather card, the machine's address on your network, then **one admin password** (12 or more letters and digits, typed twice). That password is used for every admin login and is never saved by the installer.
3. **Planned steps.** A short, grouped list of what will run, and which steps need you. Type `yes` to start.
4. **Installing.** A status line at the bottom shows the current step, the bar for the whole install and the elapsed time. Finished steps stay above it with a tick.
5. **Tailscale login.** A link appears. Open it in a browser on any device, sign in and approve the machine. The installer carries on by itself.
6. **Tailscale HTTPS.** If HTTPS certificates are not on in your Tailscale account yet, the installer shows where to switch them on (https://login.tailscale.com/admin/dns), then waits for Enter.
7. **Port 53.** The installer explains that it will stop the built-in DNS resolver so AdGuard Home can use port 53, and asks first. Answer `y`.
8. **Install finished.** The time taken, how many steps are done and the address of Homepage, your dashboard.
9. **Generated passwords and keys.** Shown once. Copy them into your password manager, then press Enter. They stay in a root-only file on the machine; `sudo homelab-setup secrets` shows them again.
10. **Checklist and Next step.** A short list of what is done and what is left, then the one step to do next with its command.

## After the install

Keep running the command the **Next step** section shows (usually `sudo homelab-setup refresh`). It re-checks the machine, finishes whatever is now possible and names the next step. When everything is done it is replaced by a **System check** that confirms every container and service answers.

The steps that need you are few:

| Step | What to do |
|---|---|
| Tailscale widget | `sudo homelab-setup fill` walks you through creating an API token and tests it before saving it. |
| Data drive | Optional. Connect a drive and run `sudo drives`, or skip: `sudo homelab-setup skip data-drive`. |
| Devices use AdGuard Home | Set a device's DNS server (or your router's) to the machine's address. The installer notices on its own. |
| First speed test | Log in to Speedtest Tracker and start a test. The installer notices on its own. |
| Reboot once | `sudo reboot`. The installer notices that everything came back. |

Useful commands:

```
sudo homelab-setup                # the checklist
sudo homelab-setup --details      # the checklist with full instructions for every open step
sudo homelab-setup refresh        # re-check and continue
sudo homelab-setup verify         # check that every container and service is up
sudo homelab-setup secrets        # show the generated passwords again
sudo homelab-setup help
```

## If something goes wrong

- A failed step shows a red cross and the reason. Run `sudo bash setup.sh install` again: finished steps are skipped and the failed one is retried.
- The log is `/var/log/homelab-setup.log` (the admin password is masked there).
- `TROUBLESHOOTING.md` covers problems with the running lab. `homelab-setup/VM-TEST-GUIDE.md` shows how to test the installer on a throw-away virtual machine and how to start over.

## Restoring from a backup (optional)

If you have a backup of an earlier copy of this lab, connect it before the first install, or pass its folder: `sudo bash setup.sh install --backup /path/to/backup`. Saved settings are restored from it; photos and files are copied back only when nothing is there yet. Nothing is overwritten.

## For maintainers

`homelab-setup/DESIGN.md` records how the installer works and why: the steps, the safety rules, the tests and what has not been verified yet.
