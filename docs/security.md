# Security

How the lab is protected, what it trusts, and where the weak spots are. This is how I set mine up, not a security audit.

## What protects it

- **Nothing is open to the internet.** There's no port forwarding on the router. Every service is reached through Tailscale, and only devices signed in to my Tailscale account can open the HTTPS addresses. I use Tailscale Serve, which stays inside the tailnet. Tailscale Funnel, which publishes to the internet, is never turned on.
- **Secrets stay on the machine.** Passwords, API keys and tokens live in Portainer's environment variables and in the `homepage-config` files on the server. Every `your-own-key` in this repo is a placeholder. The [secrets checklist](secrets-checklist.md) lists every secret and what to do if one is lost.
- **Defaults get changed.** FileBrowser makes a random first password, and Speedtest Tracker ships with `admin@example.com` and `password`. Change both on the first login (the installer does it for you).
- **One key per integration.** Homepage, Nextcloud and the others each get their own API key, so I can revoke one without breaking the rest.
- **Lockouts are on purpose.** Nextcloud blocks an address after repeated failed logins. Stop Homepage while you edit its keys, so a typo doesn't lock the server out.
- **DNS filtering is per device.** Only devices that use AdGuard Home are filtered, so a guest's phone isn't touched.
- **Pinned images.** Each stack file pins its image to a version, so a container doesn't change unless I choose to. [Updating](updating.md) explains how I move to a newer one.

## Weak spots

| Item | Why it matters | What I do about it |
| --- | --- | --- |
| The `docker` group | A user in the `docker` group can start a container that mounts the whole disk, which is the same as being root. | Only trusted accounts go in it, and SSH has a strong password or keys. |
| The Docker socket in Portainer and Homepage | Both mount `/var/run/docker.sock`, so whoever controls them controls Docker, and so the machine. Homepage mounts it read-only, which still lets it read container details. | Both stay behind Tailscale, with strong admin passwords. |
| Homepage mounts `/` read-only | The drive widget needs it, but the container can read every file on the boot drive, including the backups of other services' config. | Keep Homepage private. Remove the `/:/host:ro` line if you don't use the resources widget. |
| Backups aren't encrypted | They hold the Nextcloud `config.php` (with its database password), the Homepage config (with its API keys) and the Nextcloud database dump. | The backup drive stays somewhere safe, and I don't copy it to a cloud service I don't trust. |
| No disk encryption | Anyone holding the machine can read the boot drive. | Fine for a machine at home. Encrypt the drives if it could be stolen. |
| FileBrowser is abandoned | Its repository was archived, so there won't be more security fixes. | Only reachable through Tailscale, with its command runner turned off. See [FileBrowser](updating.md#filebrowser). |
| Unattended AnyDesk access | The password I set lets anyone who has it control the desktop. | A long random password. Remove AnyDesk if you don't need it. |
| Public docs | The guides describe the whole setup. | They only contain placeholders. Run `homelab-check` before uploading changes. |

## If a secret leaks

1. Change it where it's used (see the [secrets checklist](secrets-checklist.md)), then in Portainer's environment variables, and redeploy the stack.
1. If it was committed to Git, deleting the line isn't enough, because the old commit still has it. Treat it as public and replace it.
1. Revoke the Tailscale and Immich API keys in their admin pages and make new ones.

If something doesn't work, start with the [troubleshooting guide](troubleshooting.md).
