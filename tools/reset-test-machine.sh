#!/usr/bin/env bash
# Takes everything the home lab installer put on THIS machine off again, so the install can be tested from the beginning.
#
#   sudo bash tools/reset-test-machine.sh --dry-run     show what would be removed, change nothing
#   sudo bash tools/reset-test-machine.sh               remove it (you must type this machine's name first)
#
# FOR A TEST MACHINE ONLY. It deletes the containers, their data (photos, files, databases), the generated passwords and the
# helper commands. It does not touch your own files, the git copy of this repository, or drives set up with `sudo drives`
# (it refuses to run while a pool or a drive is set up: take them out first with `sudo drives release`).
# After it, the machine is ready for: sudo bash setup.sh install

set -u
DRY=0
case "${1:-}" in
  --dry-run|-n) DRY=1 ;;
  "") ;;
  *) echo "Usage: sudo bash tools/reset-test-machine.sh [--dry-run]"; exit 1 ;;
esac
[ "$(id -u)" = 0 ] || { echo "Run this with sudo."; exit 1; }

REAL_USER="${SUDO_USER:-}"
[ -n "$REAL_USER" ] && [ "$REAL_USER" != root ] || REAL_USER=$(getent passwd 1000 | cut -d: -f1)
[ -n "$REAL_USER" ] || { echo "Could not find the normal user of this machine."; exit 1; }
HOME_DIR=$(getent passwd "$REAL_USER" | cut -d: -f6)
HOST=$(hostname)

say() { printf '%s\n' "$*"; }
step() { say ""; say "== $* =="; }
do_() {   # do_ COMMAND...: run it, or only show it in a dry run
  if [ "$DRY" = 1 ]; then say "   would run: $*"; else "$@" >/dev/null 2>&1 || true; fi
}
rm_() {   # rm_ PATH...: remove files or folders (only those that exist)
  local p
  for p in "$@"; do
    [ -e "$p" ] || [ -L "$p" ] || continue
    if [ "$DRY" = 1 ]; then say "   would remove: $p"; else rm -rf --one-file-system -- "$p" && say "   removed: $p"; fi
  done
}

# ---- refuse when real drives are in use
if grep -v '^[[:space:]]*#' /etc/fstab 2>/dev/null | awk '$2 ~ "^/mnt/disks/" || $3 ~ "mergerfs"' | grep -q . \
   || mountpoint -q /mnt/storage || mountpoint -q /mnt/backup; then
  say "STOP: this machine has drives or a pool set up (/etc/fstab mentions /mnt/disks or mergerfs, or /mnt/storage / /mnt/backup is mounted)."
  say "Take them out first:  sudo drives release   (the files on the drives are not touched). Nothing was changed."
  exit 1
fi

say "This machine is called: $HOST   (user: $REAL_USER, home: $HOME_DIR)"
say "It will remove: all containers and their data, Docker, Tailscale (and log this machine out of it), the folders the installer"
say "made in $HOME_DIR (nextcloud, immich, speedtest-tracker, homepage-config, boot-drive-files), /opt/adguard-docker, the generated"
say "passwords, the homelab commands and their schedule, and it turns the built-in DNS resolver back on."
if [ "$DRY" = 1 ]; then
  say ""; say "(dry run: nothing is changed below, it only lists what would happen)"
else
  say ""
  printf 'To go on, type this machine name (%s) and press Enter: ' "$HOST"
  read -r answer
  [ "$answer" = "$HOST" ] || { say "Not confirmed. Nothing was changed."; exit 1; }
fi

step "1. Containers, images and volumes"
if command -v docker >/dev/null 2>&1; then
  if [ "$DRY" = 1 ]; then
    say "   would remove all containers, images, networks and volumes ($(docker ps -aq 2>/dev/null | wc -l) containers now)"
  else
    say "   removing $(docker ps -aq 2>/dev/null | wc -l) containers, then all images, networks and volumes ..."
    docker ps -aq 2>/dev/null | xargs -r docker rm -f >/dev/null 2>&1
    docker system prune -af --volumes >/dev/null 2>&1
    say "   done: $(docker ps -aq 2>/dev/null | wc -l) containers left"
  fi
else
  say "   Docker is not installed."
fi

step "2. Tailscale"
if command -v tailscale >/dev/null 2>&1; then
  do_ tailscale serve reset
  do_ tailscale logout
  [ "$DRY" = 1 ] || say "   logged out of Tailscale"
fi
do_ systemctl disable --now tailscaled

step "3. Docker and Tailscale programs and their package sources"
do_ systemctl disable --now docker.service docker.socket containerd.service
do_ gpasswd -d "$REAL_USER" docker
if [ "$DRY" = 1 ]; then
  say "   would purge: docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin tailscale"
else
  DEBIAN_FRONTEND=noninteractive apt-get purge -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin tailscale >/dev/null 2>&1 || true
  DEBIAN_FRONTEND=noninteractive apt-get autoremove -y -q >/dev/null 2>&1 || true
  say "   purged the Docker and Tailscale packages"
fi
rm_ /etc/apt/sources.list.d/docker.sources /etc/apt/keyrings/docker.asc /etc/apt/sources.list.d/tailscale.list \
    /usr/share/keyrings/tailscale-archive-keyring.gpg /var/lib/docker /var/lib/containerd /var/lib/tailscale
[ "$DRY" = 1 ] || apt-get update -q >/dev/null 2>&1 || true

step "4. The folders of the services"
for d in nextcloud immich speedtest-tracker homepage-config boot-drive-files 750GB_HDD; do rm_ "$HOME_DIR/$d"; done
rm_ /opt/adguard-docker /mnt/storage/immich /mnt/storage/nextcloud
if [ "$DRY" = 1 ]; then
  say "   would remove /mnt/storage and /mnt/backup if they are empty folders"
else
  rmdir /mnt/storage /mnt/backup 2>/dev/null || true
fi

step "5. Passwords, settings, records and logs of the installer"
rm_ /root/.homelab-setup /var/lib/homelab-setup /var/lib/homelab /var/lib/homelab-drives /var/lib/homelab-backup /var/lib/homelab-boot-sections \
    /etc/homelab-backup.conf /etc/homelab-drive-names /var/log/homelab-setup.log /var/log/homelab-drives.log /var/lock/homelab-drives.lock \
    /var/log/homelab-backup.log /var/log/homelab-update.log /var/log/homelab-snapraid.log

step "6. The homelab commands"
for f in drives homelab-backup homelab-update homelab-restore-configs homelab-sample homelab-selftest homelab-setup; do rm_ "/usr/local/sbin/$f"; done
for f in hdd-recover homelab homelab-check; do rm_ "/usr/local/bin/$f"; done

step "7. The schedule (root's crontab) and the login screen"
if crontab -l >/dev/null 2>&1; then
  if [ "$DRY" = 1 ]; then
    say "   would remove these lines from root's crontab:"
    crontab -l | grep -E 'homelab-(sample|update|backup|setup)|drives power' | sed 's/^/     /'
  else
    crontab -l | grep -vE 'homelab-(sample|update|backup|setup)|drives power' | crontab - 2>/dev/null || true
    say "   removed the lab's lines from root's crontab"
  fi
fi
if [ -f "$HOME_DIR/.bashrc" ] && grep -q '# >>> homelab login display >>>' "$HOME_DIR/.bashrc"; then
  if [ "$DRY" = 1 ]; then say "   would remove the homelab login block from $HOME_DIR/.bashrc"
  else sed -i '/# >>> homelab login display >>>/,/# <<< homelab login display <<</d' "$HOME_DIR/.bashrc"; say "   removed the login screen block from $HOME_DIR/.bashrc"; fi
fi
rm_ "$HOME_DIR/.bashrc.bak-homelab-setup"

step "8. The built-in DNS resolver"
if [ "$DRY" = 1 ]; then
  say "   would turn systemd-resolved back on and point /etc/resolv.conf at it"
else
  systemctl enable --now systemd-resolved >/dev/null 2>&1 || true
  if [ -e /run/systemd/resolve/stub-resolv.conf ]; then ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf; fi
  say "   systemd-resolved is $(systemctl is-active systemd-resolved 2>/dev/null)"
fi

say ""
if [ "$DRY" = 1 ]; then
  say "Dry run finished. Nothing was changed."
else
  say "Done. This machine is back to before the install."
  say "Next:"
  say "  1. Remove this machine from your Tailscale admin page (https://login.tailscale.com/admin/machines), or the next install gets a name like $HOST-1."
  say "  2. Reboot:  sudo reboot      (also gives you a clean terminal; the Docker group change needs it)"
  say "  3. Install again:  cd ~/My-Home-Lab- && git pull && sudo bash setup.sh install"
fi
