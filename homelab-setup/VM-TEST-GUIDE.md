# Testing homelab-setup on a virtual machine

Purpose: verify the installer on a real, disposable Linux machine before it is used for anything that matters. Everything in this guide can be undone by reverting a snapshot or by running the "Start over" block at the end.

Do **not** run this on the production server `pc`. (If it is run there by mistake, the installer detects the running lab and shows a read-only checklist only.)

## Preparation (about 30 minutes, once)

| Item | Suggested value |
|---|---|
| VM program | VirtualBox or VMware Workstation Player on a PC (or a spare PC) |
| OS | Linux Mint 22 Cinnamon or Xfce, or Ubuntu Server 24.04 |
| Memory | 8 GB (Immich's machine-learning container needs about 4 GB) |
| Disk | 60 GB or more, dynamically allocated |
| Network | **Bridged** (so the VM gets its own address on the router) |
| Name of the machine | something that is not `pc`, for example `homelabtest` |
| Tailscale account | a **separate test account** is recommended, so the VM never touches the production tailnet |

1. Install the OS, update nothing yet, and reboot once.
2. Take a snapshot called `clean` (power the VM off first if the VM program fails to restore snapshots taken while running).
3. Note the VM's address in the router. For a test, DHCP is sufficient.

If snapshots cannot be restored, use the "Start over without a snapshot" block at the end instead.

## Round 1: dry run (changes nothing)

Terminal: the VM.

```
sudo apt update && sudo apt install -y git
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git
cd My-Home-Lab-
sudo bash setup.sh install --dry-run
```

Use `sudo bash setup.sh`, not `./setup.sh`: files uploaded through the GitHub web page lose their "executable" mark.

Expected result: no questions are asked. The installer prints the planned steps (how many run automatically and how many need a person) and "would run ..." lines. Nothing is installed. The preview omits the steps that wait behind the Tailscale login, and it may print "Tailscale is not installed yet"; this only reflects that nothing has been installed.

## Round 2: the real install

Terminal: the VM's own window (not SSH over Tailscale, because port 53 is freed during the install).

```
sudo bash setup.sh install
```

What to expect, in order:

1. Questions: name, email address, time zone, LAN address, then the shared administrator password (12 or more letters and digits, typed twice). Enter the **email address** carefully: it is the login for Immich, Beszel and Speedtest Tracker.
2. "Type yes to start".
3. Updates, Docker, Tailscale.
4. **Tailscale shows a login link.** Open it in a browser on another device, log in and approve the machine.
5. **The installer asks for HTTPS certificates to be enabled** in the Tailscale admin page (https://login.tailscale.com/admin/dns) if they are not on yet. Enable them, then press Enter.
6. The installer asks before freeing port 53. Answer `y`.
7. Portainer, then the nine stacks. The first time this downloads about 10 GB of images; Nextcloud's first install can take up to 15 minutes.
8. A list of generated passwords. On a test VM they are disposable. On a real machine, copy them into a password manager and never paste them into a chat or an issue.
9. A checklist of the remaining steps.

A fresh machine shows **55 steps**. After a clean install about 46 are done; the rest are the manual and self-checking items below. Every command and link in the remaining-steps list is highlighted (bold cyan for commands, underlined cyan for links) when the terminal supports colour.

Then:

```
sudo homelab-setup            # the checklist
sudo homelab-setup fill       # walks through the Tailscale API token and other manual keys
sudo homelab-setup refresh    # re-scans after a step has been completed
```

### Steps that tick themselves

Perform the action itself; the next `sudo homelab-setup` or `refresh` detects it and marks the step done. Running `done` is not required.

| Step | What makes it tick |
|---|---|
| Homepage weather location | change `latitude` / `longitude` under `openmeteo` in `~/homepage-config/widgets.yaml` |
| AdGuard Home blocklists | turn on three or more lists in AdGuard Home (Filters, DNS blocklists) |
| Devices use AdGuard Home | set a device's DNS server to the machine's address and browse for a short while |
| Speedtest Tracker has run its first test | log in on port 8088 and start a test |
| Rebooted once and everything came back | `sudo reboot`, wait, and confirm all 16 containers are up |

Still manual: the Tailscale widget API token (`sudo homelab-setup fill`), the confirmation that the passwords are stored in a password manager (`sudo homelab-setup done secrets-saved`), and the data drive (connect one and run `sudo drives`, or run `sudo homelab-setup skip data-drive`).

## Round 3: verification

Check each of the following: Homepage; Portainer (all 9 stacks listed and editable); AdGuard Home; Beszel (the agent is listed); Netdata; Speedtest Tracker (log in with the email address and the shared password; the Homepage card shows an error until the first test has run, which is expected); FileBrowser; Immich (log in, create a test upload); Nextcloud (log in, no "trusted domain" error).

On the VM:

```
docker ps --format '{{.Names}}'   # 16 containers
cat /etc/resolv.conf              # only the router (nameserver 192.168.x.1), never 100.100.100.100
homelab                           # the login screen, with the setup progress line
sudo homelab-setup install        # second run: changes nothing
sudo reboot                       # then run homelab, docker ps and cat /etc/resolv.conf again
```

With no data drive, the login screen shows a grey "no data drive set up yet" line, not a red error.

### Opening the Homepage and the Tailscale links

- **On the VM itself** use the LAN address: `http://<vm-address>:3001`. A machine cannot open its own Tailscale Serve addresses (`https://<vm-name>.<tailnet>.ts.net:1000` and so on); that is normal and not a bug. The installer also keeps Tailscale away from DNS on purpose (`--accept-dns=false`), so the VM does not look up `.ts.net` names at all.
- **Testing the Tailscale links requires a second device on the same tailnet.** With a separate test account, share the VM with the production account: in the Tailscale admin page open the `...` menu next to the machine, choose Share, generate an invite link, open it in a browser signed in to the production account, accept it, and keep Tailscale running on that PC. Then open `https://<vm-name>.<tailnet>.ts.net:1000` there. The first page can take about 30 seconds while the HTTPS certificate is issued.
- When testing is finished, remove the shared machine from the production account.

## Round 4: restore test (optional)

Connect a copy of a backup (or a USB drive with a few photos laid out like the backup) to the VM, start over (below) and run `sudo bash setup.sh install --backup /path/to/backup`. Use a user named `brandon` for this round, because settings from another user's backup are deliberately refused.

## If something fails

A failed step shows a red cross and the reason. `sudo homelab-setup install` can always be run again; finished steps are skipped. Use `install`, not `refresh`, to continue after a failure: `install` also shows the Tailscale login link when one is needed.

Information to include in a bug report:

1. The text of the failing step from `sudo homelab-setup` (never the secrets).
2. The last 60 lines of `/var/log/homelab-setup.log` (the typed password is masked there; review the lines for anything else private before sharing).
3. The VM's operating system and version.
4. For a widget that does not work: its name and what Homepage shows.

## Start over without a snapshot

Use this only on the test VM. It removes everything the installer created: containers, images, Docker data, the Tailscale login, the service folders, the scripts, the cron lines, the login-screen hook and the installer's own state. It leaves the cloned `My-Home-Lab-` folder, a few small tools the installer installed (curl, rsync, hdparm and similar) and the system updates.

Terminal: the VM. First confirm that `hostname` does not print `pc`.

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

Then delete the old machine in the Tailscale admin page (otherwise the next one is named `homelabtest-1`), pull the newest files and test again:

```
cd ~/My-Home-Lab-
git pull
sudo bash setup.sh install --dry-run
```

## When you are done

- Delete the VM's entry in the Tailscale admin machines page, and remove any shared copy from the production account.
- Revert to the snapshot `clean`, or use the block above, to start over.
