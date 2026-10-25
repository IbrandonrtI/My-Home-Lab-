# Secrets checklist

This page lists every password and key the home lab needs. It holds **no values**, only where each one is used, where a copy can be found on the server, and what to do if it is lost. The values belong in a password manager. A rebuild ([README, "Rebuild the server after the boot drive dies"](README.md#rebuild-the-server-after-the-boot-drive-dies)) cannot start without them.

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
| [ ] | Portainer admin login | Portainer web page | In Portainer's data volume | Use Portainer's password-reset helper (see Portainer's documentation) |
| [ ] | AdGuard Home admin login | AdGuard Home web page | A password hash in `AdGuardHome.yaml` | Replace the hash in `AdGuardHome.yaml` (see AdGuard Home's documentation, "Configuration") |
| [ ] | Beszel admin login, and the agent `KEY` and `TOKEN` | Beszel hub and agent | The hub's data volume | The hub shows a new `KEY` and `TOKEN` when you add the system again. Use Beszel's superuser command for the login (see its documentation) |
| [ ] | FileBrowser admin login | FileBrowser web page | In FileBrowser's data volume | Use FileBrowser's command line to set a new password, or start with an empty database |
| [ ] | Speedtest Tracker login | Speedtest Tracker web page | Its folder in `/home/your-username/speedtest-tracker` | Use the app's own reset (see its documentation) |
| [ ] | Speedtest Tracker `APP_KEY` | The Speedtest Tracker stack | Stack variable | Make a new one with `echo "base64:$(openssl rand -base64 32)"`. Everyone is logged out, and saved settings that were encrypted with the old key can no longer be read |
| [ ] | Homepage widget keys | Homepage `services.yaml` | `services.yaml` (also in the backup's `boot-configs`) | Make new ones: a Tailscale API token in the admin console, an Immich API key in your Immich account, a Nextcloud token with `occ` (README, section 15.3) |
| [ ] | Tailscale account login | Every Tailscale address | In your account provider | Recover through the sign-in provider you chose |
| [ ] | AnyDesk unattended password | Remote desktop | AnyDesk's settings | `sudo anydesk --set-password` |
| [ ] | GitHub account, and its recovery codes | This repository | Nowhere | Use the recovery codes. Without them GitHub's support is the only way back in |
| [ ] | Router admin login and the Wi-Fi password | The router | Nowhere | A factory reset of the router, which also clears the fixed address for the server |

## The rule behind this page

- No value is ever written into a file in this repository. The stack files and `services.yaml` carry placeholders such as `your-own-key`.
- `homelab-check` scans the repository for anything that looks like a real key before an upload.
- If a real secret is committed by mistake, change it at its source (the service) first. Deleting it from the repository does not remove it from the repository's history.
