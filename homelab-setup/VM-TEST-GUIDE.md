# Testing homelab-setup on a virtual machine

Goal: prove the installer on a real, disposable Linux machine before you trust it. Everything here is undone by reverting a snapshot, so nothing needs undo commands.

Do **not** run this on the real server `pc`. (If you do, it detects the running lab and only shows a read-only checklist.)

## What to prepare (about 30 minutes, once)

| Item | Suggested value |
|---|---|
| VM program | VirtualBox or VMware Workstation Player on your PC (or a spare PC) |
| OS | Linux Mint 22 Cinnamon, or Ubuntu Server 24.04 |
| Memory | 8 GB (Immich's machine-learning container needs about 4 GB) |
| Disk | 60 GB or more, dynamically allocated |
| Network | **Bridged** (so the VM gets its own address on your router) |
| Name of the machine | something that is not `pc`, for example `labtest` |
| User | create a user with a name that is **not** `brandon` (for example `tester`), so the substitution is really tested |

1. Install the OS, update nothing yet, and reboot once.
2. Take a snapshot called `clean`.
3. In your router, note the VM's address. For a real test you can leave it as DHCP.

## Round 1: dry run (changes nothing)

Terminal: the VM.

```
sudo apt update && sudo apt install -y git
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git
cd My-Home-Lab-
sudo bash setup.sh install --dry-run
```

If you have not pushed the installer to GitHub yet, copy the folder over from your PC (USB stick, or `scp`) instead of cloning.

Expected: it asks no questions, prints the list of what it would do and "would run ..." lines. Nothing is installed.

## Round 2: the real install

Terminal: the VM.

```
sudo bash setup.sh install
```

What to expect, in order:

1. Questions: name, email, time zone, LAN address, then the shared admin password (12 or more letters and digits). It warns that one password for everything is a risk.
2. "Type yes to start".
3. Updates, Docker, Tailscale.
4. **Tailscale shows a link.** Open it on your PC, log in, approve the machine.
5. **It asks you to turn on HTTPS certificates** in the Tailscale admin page (login.tailscale.com/admin/dns). Do that, then press Enter.
6. It asks before freeing port 53. Answer `y`. Do this from the VM's own console or the LAN, not over Tailscale SSH.
7. Portainer, then the nine stacks. This takes a while the first time (many gigabytes of images).
8. A list of generated passwords. Copy them into your password manager now.
9. A checklist of what is left for you.

Then:

```
sudo homelab-setup            # the checklist
sudo homelab-setup fill       # walks through the Tailscale API token and other by-hand keys
sudo homelab-setup refresh    # re-scans after you do a step
```

## Round 3: what to check

On your PC, open `https://<vm-name>.<your-tailnet>.ts.net:1000` (Homepage) and look at each widget. Every widget should show numbers, not an error.

Quick list: Homepage, Portainer (all 9 stacks listed and editable), AdGuard Home, Beszel (the agent shows up), Netdata, Speedtest Tracker (log in with your email and the shared password), FileBrowser, Immich (log in, create a test upload), Nextcloud (log in, no "trusted domain" error).

On the VM:

```
docker ps                      # 16 containers running
homelab                        # the login screen, with the setup progress line
sudo homelab-setup install     # second run: should change nothing
sudo reboot                    # then run homelab and docker ps again
```

## Round 4: restore test (optional)

Plug a copy of your backup (or a USB drive with a few photos laid out like the backup) into the VM, then revert to `clean` and run `sudo bash setup.sh install --backup /path/to/backup`. Use a user named `brandon` for this round, because settings from another user's backup are deliberately refused.

## If something fails

The installer never leaves you guessing: the step shows a red cross and the reason. You can always run `sudo homelab-setup install` again; finished steps are skipped.

Send me:

1. The text of the failing step from `sudo homelab-setup` (not the secrets).
2. The last 60 lines of `/var/log/homelab-setup.log` (the typed password is masked there; check for anything else you consider private first).
3. The VM's OS and version.
4. For a widget that does not work: its name and what Homepage shows.

## When you are done

- Delete the VM's entry in the Tailscale admin machines page, or revert the snapshot and keep the VM for the next round.
- Revert to the snapshot `clean` to start over.
