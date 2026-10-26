# Testing homelab-setup on a virtual machine

This is how I check the installer on a real, throw-away Linux machine before I trust it with anything that matters. Everything here can be undone by reverting a snapshot or by running the "Start over" block at the end.

**Don't run this on your real server.** (If the installer runs on a machine that already has the lab, it notices and only shows a read-only checklist. The "Start over" block at the end deletes data and has no such protection.) The fake-machine tests in [`tests/`](../tests/README.md) need no VM. This guide is for what only a real machine can prove.

## Preparation (about 30 minutes, once)

| Item | What I use |
| --- | --- |
| VM program | VirtualBox or VMware Workstation Player on a PC (or a spare PC) |
| OS | Linux Mint 22 Cinnamon or Xfce, or Ubuntu Server 24.04 |
| Memory | 8 GB (Immich's machine-learning container needs about 4 GB) |
| Disk | 60 GB or more, dynamically allocated |
| Network | **Bridged**, so the VM gets its own address on the router |
| Machine name | Anything but `pc`, for example `homelabtest` |
| Tailscale account | A **separate test account**, so the VM never touches your real tailnet |

1. Install the OS, don't update anything yet, and reboot once.
2. Take a snapshot called `clean`. Power the VM off first if your VM program can't restore snapshots taken while running.
3. Note the VM's address in the router. DHCP is fine for a test.

If snapshots can't be restored, use the "Start over without a snapshot" block at the end.

## Round 1: dry run (changes nothing)

In the VM:

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/IbrandonrtI/My-Home-Lab-.git
cd My-Home-Lab-
sudo bash setup.sh install --dry-run
```

Use `sudo bash setup.sh`, not `./setup.sh`, because files uploaded through GitHub's web page lose their "executable" mark.

What should happen: no questions. It prints a welcome screen, then the planned steps in groups (how many run automatically in each, and the steps that need a person) and "would run ..." lines. Nothing gets installed. The preview leaves out the steps that wait behind the Tailscale login, and it may say "Tailscale is not installed yet". That's only because nothing has been installed.

## Round 2: the real install

Do this in the VM's own window, not over SSH through Tailscale, because port 53 gets freed during the install.

```bash
sudo bash setup.sh install
```

What you should see, in order:

1. A welcome screen (what gets installed, 30 to 60 minutes, about 10 GB, what to have ready).
2. Questions: name, email address, time zone, a city for the weather card (it shows a list if several cities match), LAN address, then the shared admin password (12 or more letters and digits, typed twice). Type the **email address** carefully, because it's the login for Immich, Beszel and Speedtest Tracker.
3. The planned steps in groups, then "Type yes to start".
4. Updates, Docker, Tailscale. While a step runs, a status line at the bottom shows a spinner, the step, the image being downloaded, a bar for the whole install (`n of m`) and the time so far. Finished steps stay above it as `✓` lines.
5. **Tailscale shows a login link.** Open it in a browser on another device, log in and approve the machine. The status line shows how long it has been waiting.
6. **It asks you to turn on HTTPS certificates** in the Tailscale admin page (<https://login.tailscale.com/admin/dns>) if they're not on yet. Turn them on, then press Enter.
7. It asks before freeing port 53. Answer `y`.
8. Portainer, then the nine stacks. The first time, this downloads about 10 GB of images, and Nextcloud's first install can take up to 15 minutes.
9. **Install finished**: the time it took, steps done and the Homepage address.
10. **Generated passwords and keys**, shown once. On a test VM they're disposable. On a real machine, copy them into a password manager and never paste them into a chat or an issue. It waits for Enter, and pressing it ticks the "passwords copied" step.
11. A compact checklist (one line per step, with `you do this` or `detected automatically` on the open ones), then a **Next step** section with the one step to do next, its instructions and its command. After each step run `sudo homelab-setup refresh`. The Next step section moves on until everything is done, and then it turns into a **System check** that confirms every container and service is up. `sudo homelab-setup --details` shows the full instructions for every open step.

A fresh machine shows **56 steps**. After a clean install about 49 are done, and the rest are the manual and self-checking items below. Commands and links in the remaining-steps list are highlighted (bold cyan for commands, underlined cyan for links) when the terminal supports colour.

Then:

```bash
sudo homelab-setup            # the checklist
sudo homelab-setup fill       # walks through the Tailscale API token and other manual keys
sudo homelab-setup refresh    # checks again after you finish a step
```

### The "Devices use AdGuard Home" test

This is the one self-checking step I haven't proven on a real machine yet. Do it exactly like this, on **one other device** (not the VM itself, because the check ignores the machine's own address):

1. On that device, set the DNS server by hand to the VM's address (`<vm-address>`, shown by `homelab`). Windows: Settings > Network > DNS. iPhone: Wi-Fi > (i) > Configure DNS.
2. Browse a few pages for a minute, so AdGuard Home sees queries from the device.
3. On the VM, run `sudo homelab-setup refresh`. Do **not** run `done`.
4. What should happen: the step "Your devices use AdGuard Home as their DNS server" changes to done by itself, and the line says "detected automatically". If it stays open, look at AdGuard Home's dashboard: the device should be listed under Top clients. Write down which of the two is missing.
5. Set the device's DNS back to automatic afterwards, so it doesn't point at a test machine.

### Steps that tick themselves

Do the thing itself, and the next `sudo homelab-setup` or `refresh` notices and marks the step done. You don't need `done`.

| Step | What makes it tick |
| --- | --- |
| Devices use AdGuard Home | Set a device's DNS server to the machine's address and browse for a bit |
| Speedtest Tracker has run its first test | Log in on port 8088 and start a test |
| Passwords copied | Press Enter at the end of the install, after the passwords are shown (or run `sudo homelab-setup secrets` later). The installer can't check that you actually saved them |
| Rebooted once and everything came back | `sudo reboot`, wait, and make sure all 16 containers are up |

The installer does these during the install: the weather city (it asks in the questions) and the AdGuard Home blocklists (HaGeZi Pro and Peter Lowe's).

Still manual: the Tailscale widget API token (`sudo homelab-setup fill`) and the data drive (connect one and run `sudo drives`, or run `sudo homelab-setup skip data-drive`).

A background check runs every 10 minutes, so the self-checking steps tick without you running anything. `sudo homelab-setup refresh` runs the same check on demand. Don't use `done` on a self-checking step while testing, because that skips the real detection this round is meant to check.

## Round 3: check everything

FileBrowser shows one folder named after the system drive and, once drives are connected, `main-storage` and `backup-storage` with one folder per drive inside (the names come from the drive's model and size, or from `/etc/homelab-drive-names`). Check each of these: Homepage; Portainer (all 9 stacks listed and editable); AdGuard Home; Beszel (the agent is listed); Netdata; Speedtest Tracker (log in with the email address and the shared password; the Homepage card shows an error until the first test has run, which is normal); FileBrowser; Immich (log in, upload a test photo); Nextcloud (log in, no "trusted domain" error).

On the VM:

```bash
docker ps --format '{{.Names}}'   # 16 containers
cat /etc/resolv.conf              # only the router (nameserver 192.168.x.1), never 100.100.100.100
homelab                           # the login screen, with the setup progress line
sudo homelab-setup verify         # system check: containers, Tailscale, DNS and every service address
sudo homelab-setup install        # second run: prints "Nothing to do: all steps are complete"
sudo reboot                       # then run homelab, docker ps and cat /etc/resolv.conf again
```

With no data drive, the login screen shows a grey "no data drive set up yet" line instead of a red error.

### Opening Homepage and the Tailscale links

- **On the VM itself** use the LAN address: `http://<vm-address>:3001`. A machine can't open its own Tailscale Serve addresses (`https://<vm-name>.<tailnet>.ts.net:1000` and so on). That's normal, not a bug. The installer also keeps Tailscale away from DNS on purpose (`--accept-dns=false`), so the VM doesn't look up `.ts.net` names at all.
- **To test the Tailscale links you need a second device on the same tailnet.** With a separate test account, share the VM with your real account: in the Tailscale admin page open the `...` menu next to the machine, choose Share, make an invite link, open it in a browser signed in to your real account, accept it, and keep Tailscale running on that PC. Then open `https://<vm-name>.<tailnet>.ts.net:1000` there. The first page can take about 30 seconds while the HTTPS certificate is issued.
- When you're done testing, remove the shared machine from your real account.

## Round 3b: the newer changes

These need a real machine, because the fake one can't prove them. Do them after Round 3, with the two extra virtual disks added in the VM settings (any size, for example 20 GB and 10 GB).

1. **Nextcloud on both addresses.** Run `sudo homelab-setup refresh` first (it removes the forced address that an older install saved). Then open `http://192.168.X.X:8082` (plain http) and log in. After that, open the Tailscale address (`https://<machine>.<tailnet>.ts.net:1005`) from a second device and log in. Both should open the login page without a "trusted domain" error, and the local address should **stay** on `192.168.X.X:8082` instead of jumping to the Tailscale name. If the Tailscale address shows a wrong link or a redirect loop, write down the exact address in the browser and the output of `docker exec -u www-data nextcloud php occ config:system:get overwritehost`.
2. **FileBrowser, one folder per drive.** Log in to FileBrowser (`:8081`). You should see a folder named after the system drive. Connect the first extra disk with `sudo drives` (it becomes `MAIN1`) and open FileBrowser again: `main-storage` should contain one folder named after the disk (model and size, for example `QEMU HARDDISK 20 GB`), with the disk's contents in it. Connect the second disk as a backup drive and `backup-storage` appears with its own folder. FileBrowser restarts for a few seconds after each change, and that's normal. Then put `MAIN1=1TB HDD` into `/etc/homelab-drive-names` (as root), run `sudo homelab-setup filebrowser`, and check that the folder is now called `1TB HDD`.
3. **Suggested Commands.** Open a new terminal. A "Suggested Commands" block should appear above "Type homelab commands to see every command." Run `homelab commands` and check that `sudo homelab-setup refresh` is in the list.
4. **Dashboard look.** As the normal user (no `sudo`): `homelab theme cards blue 40`, then refresh Homepage with `Ctrl+Shift+R`, and the cards change colour. `homelab theme reset` puts it back. `homelab theme background <a picture address>` changes the picture.
5. **Bookmarks.** Make a free Brandfetch client ID, run `homelab bookmark brandfetch YOUR-ID`, then `homelab bookmark add Proton https://proton.me`. After a hard refresh the bookmark shows up with its logo. `homelab bookmark remove Proton` removes it.

## Round 4: a real backup drive and the daily backup

This round proves what the fake machine can't: that `drives` and `homelab-backup` work on a real (virtual) disk. A virtual disk counts as a real drive here, so you don't need spare hardware.

**Add the disks.** Power the VM off and add **two extra virtual disks of 30 GB** (VirtualBox: Settings > Storage > add a hard disk). Start the VM again.

In the VM:

```bash
lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS     # the two new disks have no partitions and no mount point
sudo drives
```

1. Choose **2** (Connect a new drive), pick the first new disk, choose **Main storage**, type the name and `ERASE`. It becomes `MAIN1` at `/mnt/storage`.
2. Choose **2** again, pick the second new disk, choose **Backup storage**. It becomes `BACKUP1` at `/mnt/backup`.
3. `sudo drives status` should show both pools without a red line.

**Put something in it that's worth restoring.** Upload one photo in Immich, one file in Nextcloud, and put one text file in `/mnt/storage/filebrowser`. Write down what you put where, because Round 5 checks each of them.

**Run the backup once by hand,** then look at the result:

```bash
sudo homelab-backup
sudo drives status                 # result: OK, destination /mnt/backup
sudo ls /mnt/backup                # main  boot-configs  db-dumps
sudo ls /mnt/backup/db-dumps       # one Nextcloud dump with today's date
sudo tail -5 /var/log/homelab-backup.log
```

**Prove the daily run.** The installer should already have put the 6:00 line in root's crontab:

```bash
sudo crontab -l | grep homelab-backup      # 0 6 * * * /usr/local/sbin/homelab-backup
```

Leave the VM running overnight (or set its clock past 06:00). The next day, `sudo grep -E 'start|finished' /var/log/homelab-backup.log | tail` should show a run at 06:00 that ended `finished: OK`, and a second dump in `db-dumps`.

Write down anything that didn't match. A mismatch is a finding, not a failed test.

## Round 5: restore from that backup

The goal is a brand-new machine that gets the lab back from the backup drive. Use a **new VM**, so the backup disk is the only thing it shares with the old one.

1. Power the old VM off. In the VM program, clone the `clean` snapshot into a new VM (for example `homelabtest2`) with a different name from the old one.
2. Detach the backup disk from the old VM and attach it to the new one (VirtualBox: Settings > Storage > choose an existing disk). Don't attach the main disk, because a lost main drive is exactly what this tests.
3. Start the new VM. Make the user with **the same user name** as on the first VM, because settings from another user's backup are refused on purpose.
4. Mount the backup disk where the installer looks (Mint's file manager does it on a click and puts it under `/media/<user>/BACKUP1`). Check:

```bash
ls /media/*/BACKUP1                 # main  boot-configs  db-dumps
```

<!-- markdownlint-disable-next-line MD029 -->
5. Run the installer. It lists the backup it found and asks two questions: restore the saved settings, and copy the photos and files back. Answer yes to both:

```bash
sudo bash setup.sh install
```

<!-- markdownlint-disable-next-line MD029 -->
6. When it's finished, check each item you wrote down in Round 4: the Immich photo, the Nextcloud file, the FileBrowser text file, the AdGuard Home settings, the Homepage config. The Nextcloud database should be the same one as before (log in with the same account).
<!-- markdownlint-disable-next-line MD029 -->
7. If you meant a different backup, or it didn't find one on its own, point the installer at it: `sudo bash setup.sh install --backup /path/to/backup-folder`.

If something doesn't come back, write down what it was. The manual restore steps in [`maintenance.md`](maintenance.md) are the fallback.

## If something fails

A failed step shows a red cross and the reason. You can always run `sudo homelab-setup install` again, and finished steps are skipped. Use `install`, not `refresh`, to carry on after a failure, because `install` also shows the Tailscale login link when one is needed.

What to write down for a bug report:

1. The text of the failing step from `sudo homelab-setup` (never the secrets).
2. The last 60 lines of `/var/log/homelab-setup.log` (the typed password is masked there, but read the lines for anything else private before sharing).
3. The VM's operating system and version.
4. For a widget that doesn't work: its name and what Homepage shows.

## Start over without a snapshot

> **Warning: this deletes data.** Only run it on the disposable test VM, never on a machine with data you want to keep. It removes Docker with all containers, images and volumes, and the service folders.

This removes everything the installer made: containers, images, Docker data, the Tailscale login, the service folders, the scripts, the cron lines, the login-screen hook and the installer's own state. It leaves the cloned `My-Home-Lab-` folder, a few small tools the installer installed (curl, rsync, hdparm and similar) and the system updates.

In the VM, first confirm that `hostname` prints the name of the test VM and not your real server's name. The first line below stops you if the name is `pc`, the name these guides use for the real server.

```text
[ "$(hostname)" != pc ] || { echo 'STOP: this is the real server'; false; }
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

Then delete the old machine in the Tailscale admin page (otherwise the next one is called `homelabtest-1`), pull the newest files and test again:

```bash
cd ~/My-Home-Lab-
git pull
sudo bash setup.sh install --dry-run
```

## When you're done

- Delete the VM from the Tailscale admin machines page, and remove any shared copy from your real account.
- Revert to the `clean` snapshot, or use the block above, to start over.
