# Security and credentials

This page lists how the lab is protected, what it trusts, and where the weak spots are. It describes this design; it is not a security audit.

## How it is protected

- **No public exposure.** There is no port forwarding on the router. Every service is reached through Tailscale, and only devices signed in to the owner's Tailscale account can open the HTTPS addresses. The lab uses Tailscale Serve, which stays inside the tailnet; Tailscale Funnel, which publishes to the internet, is never turned on.
- **Secrets stay local.** Passwords, API keys and tokens live in Portainer's environment variables and in the local `homepage-config` files on the server. Every `your-own-key` in this repository is a placeholder. Never commit the real values. [The secrets checklist](secrets-checklist.md) lists every secret and what to do if one is lost.
- **Change every default.** FileBrowser creates a random first password, and Speedtest Tracker ships with `admin@example.com` and `password`. Change both on the first login. The installer does this for you.
- **Least privilege.** Each integration gets its own API key (one for Homepage, one for Nextcloud), so any of them can be revoked without affecting the others.
- **Throttling is a feature.** Nextcloud blocks an address after repeated failed logins. Stop Homepage while you edit its keys so a typo doesn't lock the server out.
- **Per-device DNS.** Only devices configured to use AdGuard Home are filtered, so a guest's phone isn't touched.
- **Pinned images.** The stack files pin each image to a version, so a container does not change without you choosing it. [Updating services](updating.md) explains how to move on, and the security releases are the reason to do it.

## What the lab trusts, and the weak spots

| Item | Why it matters | What to do |
| :--- | :--- | :--- |
| The `docker` group | A user in the `docker` group can start a container that mounts the whole disk, so it is the same as being root. | Add only accounts you trust. Protect SSH with a strong password or keys. |
| The Docker socket in Portainer and Homepage | Both containers mount `/var/run/docker.sock`. Whoever controls them controls Docker, and so the machine. Homepage mounts it read-only, which still lets it read container details. | Keep both behind Tailscale only, and use strong admin passwords. |
| Homepage mounts `/` read-only | The drive widget needs it, but the container can read every file on the boot drive, including the backups of other services' config. | Keep Homepage's address private. Remove the `/:/host:ro` line if you do not use the resources widget. |
| The backups are not encrypted | They contain the Nextcloud `config.php` (with its database password), the Homepage config (with its API keys) and the Nextcloud database dump. | Keep the backup drive somewhere safe. Do not copy the backup to a cloud service you do not trust. |
| No disk encryption | The boot drive is not encrypted, so anyone with the machine in their hands can read it. | Acceptable for a machine at home. Encrypt the drives if the machine could be stolen. |
| FileBrowser is unmaintained | Its repository was archived and no more security fixes will come. | Keep it reachable only through Tailscale and keep its command runner turned off. See [FileBrowser](updating.md#filebrowser). |
| Unattended AnyDesk access | The password you set lets anyone who has it control the desktop. | Use a long random password, and remove AnyDesk if you do not need it. |
| Public documentation | The guides describe the whole setup. | They contain only placeholders, never real addresses or keys. Run `homelab-check` before you upload changes. |

## If you think a secret has leaked

1. Change it where it is used (see [the secrets checklist](secrets-checklist.md)), then in Portainer's environment variables, and redeploy the stack.
1. If it was committed to Git, deleting the line is not enough: the old commit still holds it. Treat the secret as public and replace it.
1. Revoke Tailscale and Immich API keys in their admin pages and make new ones.

If something doesn't work, start with the [troubleshooting guide](troubleshooting.md). It lists the problems I hit, with the symptom, cause, fix and a way to check each fix.
