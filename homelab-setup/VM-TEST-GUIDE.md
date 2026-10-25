# Testing homelab-setup on a virtual machine

Goal: prove the installer on a real, disposable Linux machine before you trust it. Everything here is undone by reverting a snapshot, or by the "Start over" block at the end, so nothing needs undo commands.

Do **not** run this on the real server `pc`. (If you do, it detects the running lab and only shows a read-only checklist.)

## What to prepare (about 30 minutes, once)

| Item | Suggested value |
|---|---|
| VM program | VirtualBox or VMware Workstation Player on your PC (or a spare PC) |
| OS | Linux Mint 22 Cinnamon or Xfce, or Ubuntu Server 24.04 |
| Memory | 8 GB (Immich's machine-learning container needs about 4 GB) |
| Disk | 60 GB or more, dynamically allocated |
| Network | **Bridged** (so the VM gets its own address on your router) |
| Name of the machine | something that is not `pc`, for example `homelabtest` |
| Tailscale account | a **separate test account** is safest, so the VM never touches your real tailnet |

1. Install the OS, update nothing yet, and reboot once.
2. Take a snapshot called `clean` (power the VM off first if your program fails to restore snapshots taken while running).
3. In your router, note the VM's address. For a real test you can leave it as DHCP.

If you cannot restore a snapshot, use the "Start over" block at the end instead.

## Round 1: dry run (changes nothing)

Terminal: the VM.

```
sudo apt update && sudo apt install -y git
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git
cd My-Home-Lab-
sudo bash setup.sh install --dry-run
```

Use `sudo bash setup.sh`, not `./setup.sh`: files uploaded through the GitHub web page lose their "executable" mark.

Expected: it asks no questions, prints the list of what it would do and "would run ..." lines. Nothing is installed. The preview skips the steps that wait behind the Tailscale login, and it may print "Tailscale is not installed yet"; that is only because nothing was installed.

## Round 2: the real install

Terminal: the VM's own window (not SSH over Tailscale, because port 53 is freed during the install).

```
sudo bash setup.sh install
```

What to expect, in order:

1. Questions: name, email, time zone, LAN address, then the shared admin password (12 or more letters and digits, typed twice). Type the **email** carefully: it is the login for Immich, Beszel, Speedtest Tracker and Nextcloud.
2. "Type yes to start".
3. Updates, Docker, Tailscale.
4. **Tailscale shows a link.** Open it on your PC, log in, approve the machine.
5. **It asks you to turn on HTTPS certificates** in the Tailscale admin page (login.tailscale.com/admin/dns) if they are not on yet. Do that, then press Enter.
6. It asks before freeing port 53. Answer `y`.
7. Portainer, then the nine stacks. The first time this downloads about 10 GB of images; Nextcloud's first install can take up to 15 minutes.
8. A list of generated passwords. They are for the test VM only. On a real machine, copy them into your password manager and never paste them into a chat.
9. A checklist of what is left for you.

A fresh machine shows **55 steps**. After a clean install about 46 are done and the rest are the by-hand and self-checking items below.

Then:

```
sudo homelab-setup            # the checklist
sudo homelab-setup fill       # walks through the Tailscale API token and other by-hand keys
sudo homelab-setup refresh    # re-scans after you do a step
```

### Steps that tick themselves

You do the real thing; the next `sudo homelab-setup` or `refresh` notices and ticks it. You do not need to run `done`.

| Step | What makes it tick |
|---|---|
| Homepage weather location | change `latitude` / `longitude` under `openmeteo` in `~/homepage-config/widgets.yaml` |
| AdGuard Home blocklists | turn on three or more lists in AdGuard Home (Filters, DNS blocklists) |
| Your devices use AdGuard Home | set a device's DNS to the machine's address and browse a little |
| Speedtest Tracker has run its first test | log in on port 8088 and click Speedtest |
| Rebooted once and everything came back | `sudo reboot`, wait, and make sure all 16 containers are up |

Still by hand: the Tailscale widget API token (`sudo homelab-setup fill`), "passwords copied into your password manager" (`sudo homelab-setup done secrets-saved`), and the data drive (plug one in and run `sudo drives`, or `sudo homelab-setup skip data-drive`).

## Round 3: what to check

Quick list: Homepage, Portainer (all 9 stacks listed and editable), AdGuard Home, Beszel (the agent shows up), Netdata, Speedtest Tracker (log in with your email and the shared password; the Homepage card shows an error until the first test has run, that is normal), FileBrowser, Immich (log in, create a test upload), Nextcloud (log in, no "trusted domain" error).

On the VM:

```
docker ps --format '{{.Names}}'   # 16 containers
cat /etc/resolv.conf              # only your router (nameserver 192.168.x.1), never 100.100.100.100
homelab                           # the login screen, with the setup progress line
sudo homelab-setup install        # second run: should change nothing
sudo reboot                       # then run homelab, docker ps and cat /etc/resolv.conf again
```

With no data drive, the login screen shows a grey "no data drive set up yet" line, not a red error.

### Opening the Homepage and the Tailscale links

- **On the VM itself** use the LAN address: `http://<vm-address>:3001`. A machine cannot open its own Tailscale Serve addresses (`https://<vm-name>.<tailnet>.ts.net:1000` and so on); that is normal and not a bug. The installer also keeps Tailscale away from DNS on purpose (`--accept-dns=false`), so the VM does not look up `.ts.net` names at all.
- **To test the Tailscale links you need a second device on the same tailnet.** If you used a separate test account, share the VM with your real account: Tailscale admin page, the `...` next to the machine, Share, generate an invite link, open it in a browser logged in to your real account, accept it, and keep Tailscale running on that PC. Then open `https://<vm-name>.<tailnet>.ts.net:1000` there. The first page can take about 30 seconds while the HTTPS certificate is issued.
- When you are done, remove the shared machine from your real account.

## Round 4: restore test (optional)

Plug a copy of your backup (or a USB drive with a few photos laid out like the backup) into the VM, then start over (below) and run `sudo bash setup.sh install --backup /path/to/backup`. Use a user named `brandon` for this round, because settings from another user's backup are deliberately refused.

## If something fails

The installer never leaves you guessing: the step shows a red cross and the reason. You can always run `sudo homelab-setup install` again; finished steps are skipped. Use `install`, not `refresh`, to continue after a failure: `install` also shows the Tailscale login link when one is needed.

Send me:

1. The text of the failing step from `sudo homelab-setup` (not the secrets).
2. The last 60 lines of `/var/log/homelab-setup.log` (the typed password is masked there; check for anything else you consider private first).
3. The VM's OS and version.
4. For a widget that does not work: its name and what Homepage shows.

## Start over without a snapshot

Use this only on the test VM. It removes everything the installer made: containers, images, Docker data, the Tailscale login, the service folders, the scripts, the cron lines, the login-screen hook and the installer's own state. It leaves the cloned `My-Home-Lab-` folder, a few small tools the installer installed (curl, rsync, hdparm and similar) and your Mint updates.

Terminal: the VM. Check first that `hostname` is not `pc`.

```
sudo docker ps -aq | xargs -r sudo docker rm -f
sudo docker system prune -a --volumes -f
sudo tailscale logout
sudo crontab -r
sed -i '/# >>> homelab login display >>>/,/# <<< homelab login display <<</d' ~/.bashrc
sudo rm -rf ~/nextcloud ~/immich ~/speedtest-tracker ~/homepage-config ~/750GB_HDD /opt/adguard-docker /mnt/storage/immich /mnt/storage/filebrowser /mnt/storage/nextcloud
sudo rm -rf /root/.homelab-setup /var/lib/homelab-setup /var/lib/homelab /var/log/homelab-setup.log /etc/homelab-backup.conf
sudo rm -f /usr/local/sbin/{drives,homelab-backup,homelab-update,homelab-restore-configs,homelab-sample,homelab-setup} /usr/local/bin/{hdd-recover,homelab,homelab-check}
sudo apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin tailscale
sudo rm -rf /var/lib/docker /var/lib/containerd /var/lib/tailscale /etc/apt/keyrings/docker.asc /etc/apt/sources.list.d/docker.sources /etc/apt/sources.list.d/tailscale.list /usr/share/keyrings/tailscale-archive-keyring.gpg
sudo systemctl enable --now systemd-resolved
sudo ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
sudo apt-get autoremove -y
```

Then, in the Tailscale admin page, delete the old machine (otherwise the next one is named `homelabtest-1`), pull the newest files and test again:

```
cd ~/My-Home-Lab-
git pull
sudo bash setup.sh install --dry-run
```

## When you are done

- Delete the VM's entry in the Tailscale admin machines page, and remove any shared copy from your real account.
- Revert to the snapshot `clean`, or use the block above, to start over.
