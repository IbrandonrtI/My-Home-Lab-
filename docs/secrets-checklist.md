# Secrets checklist

Every password and key the lab needs. There are **no values** on this page, only where each one is used, where a copy sits on the server, and what to do if I lose it. The values go in a password manager. A rebuild ([Rebuild the server after the boot drive dies](maintenance.md#rebuild-the-server-after-the-boot-drive-dies)) can't start without them.

On the server, `homelab secrets` prints a short version of this list and checks what it can (a key is set, a database dump is recent, the backup has the saved configs). It never shows a value.

To use this page, copy it into your password manager's notes, tick each line once the item is stored, and look at it again after any password change.

## What to store

| Done | Secret | Used by | Where a copy sits on the server | If it's lost |
| :--- | :--- | :--- | :--- | :--- |
| [ ] | Linux user login | `sudo`, SSH, the console | Nowhere | Boot into recovery mode (hold Shift at start-up), open a root shell and run `passwd your-username` |
| [ ] | Nextcloud admin login | Nextcloud web page and apps | In Nextcloud's database | `docker exec -it -u www-data nextcloud php occ user:resetpassword your-nextcloud-user` |
| [ ] | Nextcloud database password (`NC_DB_PASSWORD`) | The Nextcloud stack, and `config.php` | `dbpassword` in `config.php` (also in the backup's `boot-configs`) | Read it back from `config.php`. A rebuild has to reuse the **same** password, because `config.php` contains it |
| [ ] | Immich admin login | Immich web page and phone app | In Immich's database (restored from its own dumps) | `docker exec -it immich_server immich-admin reset-admin-password` |
| [ ] | Immich database user and password (`DB_USERNAME`, `DB_PASSWORD`) | The Immich stack | Portainer stack variables | Pick new ones for a rebuild. Immich restores its data from a dump, so the old password isn't needed |
| [ ] | Portainer admin login | Portainer web page | In Portainer's data volume | Stop Portainer and run its reset helper: `docker stop portainer && docker run --rm -v portainer_data:/data portainer/helper-reset-password`. It prints a new password. Then `docker start portainer` |
| [ ] | AdGuard Home admin login | AdGuard Home web page | A password hash in `AdGuardHome.yaml` | Stop the container, make a new bcrypt hash (`htpasswd -B -n -b admin 'new-password'` from the `apache2-utils` package), paste it as the `password:` of the user in `/opt/adguard-docker/conf/AdGuardHome.yaml`, then start the container |
| [ ] | Beszel admin login, and the agent `KEY` and `TOKEN` | Beszel hub and agent | The hub's data volume | The hub shows a new `KEY` and `TOKEN` when you add the system again. For the login: `docker exec beszel /beszel superuser upsert you@example.com new-password` |
| [ ] | FileBrowser admin login | FileBrowser web page | In FileBrowser's data volume | Set a new password with FileBrowser's command line, or start with an empty database |
| [ ] | Speedtest Tracker login | Speedtest Tracker web page | Its folder in `/home/your-username/speedtest-tracker` | Use the app's own reset (see its docs) |
| [ ] | Speedtest Tracker `APP_KEY` | The Speedtest Tracker stack | Stack variable | Make a new one with `echo "base64:$(openssl rand -base64 32)"`. Everyone gets logged out, and saved settings encrypted with the old key can't be read any more |
| [ ] | Homepage widget keys | Homepage `services.yaml` | `services.yaml` (also in the backup's `boot-configs`) | Make new ones: a Tailscale API token in the admin console, an Immich API key in your Immich account, a Nextcloud token with `occ` ([build guide, section 14.3](build-guide.md#143-fill-in-the-widget-keys)) |
| [ ] | Tailscale account login | Every Tailscale address | With your account provider | Recover it through the sign-in provider you picked |
| [ ] | AnyDesk unattended password | Remote desktop | AnyDesk's settings | `sudo anydesk --set-password` |
| [ ] | GitHub account and its recovery codes | This repository | Nowhere | Use the recovery codes. Without them, GitHub support is the only way back in |
| [ ] | Router admin login and the Wi-Fi password | The router | Nowhere | Factory-reset the router, which also clears the fixed address for the server |

## The rule behind this page

- No real value goes into a file in this repo. The stack files and `services.yaml` carry placeholders like `your-own-key`.
- `homelab-check` scans the repo for anything that looks like a real key before I upload.
- If a real secret gets committed by mistake, change it at its source (the service) first. Deleting it from the repo doesn't remove it from the history.

## Keys I replace now and then

| Key | When | How |
| :--- | :--- | :--- |
| Tailscale API token (Homepage widget) | It expires on its own (90 days by default) and the Tailscale card turns red | Make a new token in the admin console under **Settings**, then **Keys**, and run `sudo homelab-setup fill` (or edit `services.yaml`) |
| Immich API key | If it may have leaked | Make a new one in your Immich account settings, put it in `services.yaml`, then delete the old one |
| Nextcloud token for the Homepage card | If it may have leaked | `docker exec -u www-data nextcloud php occ config:app:set serverinfo token --value=$(openssl rand -hex 24)`, then put the new value in `services.yaml` |
| Speedtest Tracker `APP_KEY` | Only if it leaked. Replacing it logs everyone out and makes encrypted settings unreadable | See the table above. Stop Homepage while you change keys, so a wrong key doesn't cause a lockout |
| Shared admin password | If it was ever pasted into a chat, an issue or a screen share | Change it in each service (Portainer, AdGuard Home, Beszel, FileBrowser, Immich, Nextcloud, Speedtest Tracker), one at a time |

Last looked at: October 2026.
