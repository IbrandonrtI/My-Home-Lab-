# Secrets checklist

This page lists every password and key the home lab needs. It holds **no values**, only where each one is used, where a copy can be found on the server, and what to do if it is lost. The values belong in a password manager. A rebuild ([Rebuild the server after the boot drive dies](maintenance.md#rebuild-the-server-after-the-boot-drive-dies)) cannot start without them.

On the server, `homelab secrets` prints the short version of this list and checks what it can confirm (a key is set, a database dump is recent, the backup holds the saved configs). It never shows a value.

How to use this page: copy it into the password manager's notes, tick each line when the item is stored there, and review the list again after any password change.

## Items to store in a password manager

| Done | Secret | Used by | Where a copy lives on the server | If it is lost |
| :--- | :--- | :--- | :--- | :--- |
| [ ] | Linux user login | `sudo`, SSH, the console | Nowhere | Boot into recovery mode (hold Shift at start-up), open a root shell and run `passwd your-username` |
| [ ] | Nextcloud admin login | Nextcloud web page and apps | In Nextcloud's database | `docker exec -it -u www-data nextcloud php occ user:resetpassword your-nextcloud-user` |
| [ ] | Nextcloud database password (`NC_DB_PASSWORD`) | The Nextcloud stack, and `config.php` | `dbpassword` in `config.php` (also in the backup's `boot-configs`) | Read it back from `config.php`. A rebuild must reuse the **same** password, because `config.php` contains it |
| [ ] | Immich admin login | Immich web page and phone app | In Immich's database (restored from its own dumps) | `docker exec -it immich_server immich-admin reset-admin-password` |
| [ ] | Immich database user and password (`DB_USERNAME`, `DB_PASSWORD`) | The Immich stack | Portainer stack variables | Choose new ones for a rebuild. Immich restores its data from a dump, so the old password is not needed |
| [ ] | Portainer admin login | Portainer web page | In Portainer's data volume | Stop Portainer and run Portainer's reset helper: `docker stop portainer && docker run --rm -v portainer_data:/data portainer/helper-reset-password`. It prints a new password; start Portainer again with `docker start portainer` |
| [ ] | AdGuard Home admin login | AdGuard Home web page | A password hash in `AdGuardHome.yaml` | Stop the container, make a new bcrypt hash (`htpasswd -B -n -b admin 'new-password'` from the `apache2-utils` package) and paste it as the `password:` of the user in `/opt/adguard-docker/conf/AdGuardHome.yaml`, then start the container |
| [ ] | Beszel admin login, and the agent `KEY` and `TOKEN` | Beszel hub and agent | The hub's data volume | The hub shows a new `KEY` and `TOKEN` when you add the system again. For the login: `docker exec beszel /beszel superuser upsert you@example.com new-password` |
| [ ] | FileBrowser admin login | FileBrowser web page | In FileBrowser's data volume | Use FileBrowser's command line to set a new password, or start with an empty database |
| [ ] | Speedtest Tracker login | Speedtest Tracker web page | Its folder in `/home/your-username/speedtest-tracker` | Use the app's own reset (see its documentation) |
| [ ] | Speedtest Tracker `APP_KEY` | The Speedtest Tracker stack | Stack variable | Make a new one with `echo "base64:$(openssl rand -base64 32)"`. Everyone is logged out, and saved settings that were encrypted with the old key can no longer be read |
| [ ] | Homepage widget keys | Homepage `services.yaml` | `services.yaml` (also in the backup's `boot-configs`) | Make new ones: a Tailscale API token in the admin console, an Immich API key in your Immich account, a Nextcloud token with `occ` ([build guide, section 14.3](build-guide.md#143-fill-in-the-widget-keys)) |
| [ ] | Tailscale account login | Every Tailscale address | In your account provider | Recover through the sign-in provider you chose |
| [ ] | AnyDesk unattended password | Remote desktop | AnyDesk's settings | `sudo anydesk --set-password` |
| [ ] | GitHub account, and its recovery codes | This repository | Nowhere | Use the recovery codes. Without them GitHub's support is the only way back in |
| [ ] | Router admin login and the Wi-Fi password | The router | Nowhere | A factory reset of the router, which also clears the fixed address for the server |

## The rule behind this page

- No value is ever written into a file in this repository. The stack files and `services.yaml` carry placeholders such as `your-own-key`.
- `homelab-check` scans the repository for anything that looks like a real key before an upload.
- If a real secret is committed by mistake, change it at its source (the service) first. Deleting it from the repository does not remove it from the repository's history.

## Keys worth replacing from time to time

| Key | When | How |
| :--- | :--- | :--- |
| Tailscale API token (Homepage widget) | It expires on its own (90 days by default), and the Tailscale card turns red | Make a new token in the admin console under **Settings**, then **Keys**, and run `sudo homelab-setup fill` (or edit `services.yaml`) |
| Immich API key | If it may have leaked | Make a new one in your Immich account settings, put it into `services.yaml`, then delete the old one |
| Nextcloud token for the Homepage card | If it may have leaked | `docker exec -u www-data nextcloud php occ config:app:set serverinfo token --value=$(openssl rand -hex 24)`, then put the new value into `services.yaml` |
| Speedtest Tracker `APP_KEY` | Only if it leaked: replacing it logs everyone out and makes encrypted settings unreadable | See the table above. Stop Homepage while you change keys, so a wrong key does not trigger a lock-out |
| Shared admin password | If it was ever pasted into a chat, an issue or a screen share | Change it in each service (Portainer, AdGuard Home, Beszel, FileBrowser, Immich, Nextcloud, Speedtest Tracker), one at a time |

Last reviewed: October 2026.
