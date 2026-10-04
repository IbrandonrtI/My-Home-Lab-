# My Home Lab

A self-hosted home lab running on a repurposed laptop: DNS-level ad blocking, container management, system monitoring, file access, and a unified dashboard, all accessible remotely over a private Tailscale network.
![image alt](https://github.com/IbrandonrtI/My-Home-Lab-/blob/af5bb2855b9ba8d767b95a5a87b099b8eaaa430c/Homepage.jpg)

## Table of Contents

1. [Base System](#1-base-system)
1. [VS Code + Remote-SSH](#2-vs-code--remote-ssh)
1. [AnyDesk (Remote Desktop)](#3-anydesk-remote-desktop)
1. [SSH Server](#4-ssh-server)
1. [Docker](#5-docker)
1. [Portainer](#6-portainer)
1. [AdGuard Home](#7-adguard-home)
1. [Beszel (System Monitoring)](#8-beszel-system-monitoring)
1. [FileBrowser](#9-filebrowser)
1. [Tailscale](#10-tailscale)
1. [Homepage Dashboard](#11-homepage-dashboard)

## 1. Base System

**OS:** Linux Mint Cinnamon, installed on a repurposed laptop acting as the always-on home lab server.

The laptop stays powered on 24/7, so two power-related settings were configured first:

**Ignore lid close** (so closing the lid doesn't suspend the system):

```bash
sudo nano /etc/systemd/logind.conf
```

Set the following (uncomment and edit, no `#` in front):

```ini
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
```

Apply the change:

```bash
sudo systemctl restart systemd-logind
```

**Auto-login on boot** (so the desktop session starts without anyone physically logging in, needed for remote desktop access later). In `/etc/lightdm/lightdm.conf`, under `[Seat:*]`:

```ini
[Seat:*]
autologin-guest=false
autologin-user=your-username
autologin-user-timeout=0
```

---

## 2. VS Code + Remote-SSH

Used for editing config files on the server directly from a Windows desktop, with full syntax highlighting instead of editing blind over `nano`.

1. Install [VS Code](https://code.visualstudio.com/) on the Windows machine.
1. Install the **Remote - SSH** extension from the Extensions panel.
1. Connect: `Ctrl+Shift+P` → **Remote-SSH: Connect to Host** → enter `your-username@192.168.X.X`.
1. Enter the SSH password when prompted.
1. Open a folder or file directly from the integrated terminal:

```bash
code -a ~/homepage-config/
```

> 
> “
> Note: editing files that live inside a Docker **named volume** (e.g. `/var/lib/docker/volumes/...`) runs into permission errors, since those paths are root-owned. The working approach is to use a **bind mount** instead, a normal folder in the home directory, mounted into the container. See [Section 11](#11-homepage-dashboard) for how this was done for Homepage's config.
> ”
> 
> 

---

## 3. AnyDesk (Remote Desktop)

Used for full remote desktop / screen mirroring access to the headless laptop, functioning like a self-hosted TeamViewer.

**Install via AnyDesk's official apt repository:**

```bash
sudo apt install gnupg2 -y
wget -qO - https://keys.anydesk.com/repos/DEB-GPG-KEY | sudo apt-key add -
echo "deb http://deb.anydesk.com/ all main" | sudo tee /etc/apt/sources.list.d/anydesk-stable.list
sudo apt update
sudo apt install anydesk -y
```

**Get the device's AnyDesk ID** (needed to connect from another device):

```bash
anydesk --get-id
```

**Set a password for unattended access** (so a connection doesn't require someone physically clicking "Accept" on the laptop):

```bash
sudo anydesk --set-password
```

**Enable the AnyDesk service to start on boot:**

```bash
sudo systemctl enable anydesk
sudo systemctl start anydesk
```

**Auto-start AnyDesk's GUI after login** (so it's ready as soon as the desktop session starts, via auto-login from Section 1):

```bash
mkdir -p ~/.config/autostart
cp /usr/share/applications/anydesk.desktop ~/.config/autostart/
```

From another device, install the AnyDesk app and connect using the ID from `anydesk --get-id` and the password set above.

---

## 4. SSH Server

Enables remote terminal access from any other device on the network (or, later, over Tailscale).

```bash
sudo apt update
sudo apt install openssh-server -y
sudo systemctl enable ssh
sudo systemctl start ssh
```

Connect from another machine:

```bash
ssh your-username@192.168.X.X
```

---

## 5. Docker

Installed using Docker's official apt repository. (The host is Linux Mint, which doesn't have its own entry in Docker's repo list, Mint's underlying Ubuntu base codename — here `noble`, Ubuntu 24.04 — is used instead.)

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-ce-rootless-extras docker-buildx-plugin
```

Allow running `docker` without `sudo`:

```bash
sudo usermod -aG docker $USER
sudo reboot
```

Confirm it works:

```bash
docker run hello-world
```

---

## 6. Portainer

A web dashboard for managing Docker containers without hand-writing `docker run` commands for everything.

```bash
docker volume create portainer_data

docker run -d \
  -p 9443:9443 \
  -p 9000:9000 \
  --name portainer \
  --restart=always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data \
  portainer/portainer-ce:latest
```

Access the dashboard at `https://192.168.X.X:9443`, retrieve the one-time setup token from the container logs if prompted:

```bash
docker logs portainer
```

Create an admin account on first load. From here on, containers are deployed as **Stacks** in Portainer using the compose files below.
The code for the creation of each stacks for the current services used is listed below.

### `Adguard Home`
```bash
services:
  adguard:
    image: adguard/adguardhome:v0.107.79
    container_name: adguardhome
    restart: unless-stopped
    network_mode: host
    volumes:
      - /opt/adguard-docker/work:/opt/adguardhome/work
      - /opt/adguard-docker/conf:/opt/adguardhome/conf
```

### 'Beszel'
```bash
services:
  beszel:
    image: henrygd/beszel:latest
    container_name: beszel
    restart: unless-stopped
    ports:
      - 8090:8090
    volumes:
      - beszel_data:/beszel_data

volumes:
  beszel_data:
```
### 'Beszel-agent'
```bash
services:
  beszel-agent:
    image: henrygd/beszel-agent
    container_name: beszel-agent
    restart: unless-stopped
    network_mode: host
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./beszel_agent_data:/var/lib/beszel-agent
    environment:
      LISTEN: 45876
      KEY: 'your-own'
      TOKEN: 'your-own'
      HUB_URL: http://192.168.X.X:8090
```
### 'Filebrowser'
```bash
version: '3'
services:
  filebrowser:
    image: filebrowser/filebrowser
    restart: always
    ports:
      - "8081:80"
    volumes:
      - "/home/brandon/256GB_SSD:/srv/ssd"
      - "/media/brandon/USB STICK/1TB_HDD:/srv/hdd"
      - filebrowser_data:/database

volumes:
  filebrowser_data:
```
### 'Homepage'
```bash
services:
  homepage:
    image: ghcr.io/gethomepage/homepage:latest
    container_name: homepage
    restart: unless-stopped
    ports:
      - 3001:3000
    environment:
      HOMEPAGE_ALLOWED_HOSTS: 192.168.X.X:3001,home.tail30c3e5.ts.net:8447,localhost:3001
    volumes:
      - /home/brandon/homepage-config:/app/config
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /:/host:ro
      - "/media/brandon/USB STICK:/media/brandon/USB STICK:ro"
```

---

## 7. AdGuard Home

Network-wide DNS ad/tracker blocking.

**Prerequisite: free up port 53.** `systemd-resolved`'s local DNS stub listener occupies port 53 by default, which conflicts with AdGuard Home.

```bash
sudo mkdir -p /etc/systemd/resolved.conf.d
```

Create `/etc/systemd/resolved.conf.d/adguardhome.conf`:

```ini
[Resolve]
DNS=127.0.0.1
DNSStubListener=no
```

```bash
sudo mv /etc/resolv.conf /etc/resolv.conf.backup
sudo ln -s /run/systemd/resolve/resolv.conf /etc/resolv.conf
sudo systemctl reload-or-restart systemd-resolved
```

**Install AdGuard Home:**

```bash
curl -s -S -L https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh | sh -s -- -v
```

Complete the setup wizard at `http://192.168.X.X:3000`:

- Set the web interface port and the DNS port to **53**
- Create an admin account
- Set upstream DNS servers (plain IPs, e.g. `1.1.1.1`, `8.8.8.8`, `9.9.9.9`, rather than DNS-over-HTTPS URLs, to avoid blocklists accidentally blocking the DoH provider domains themselves)

**Point the network at it:** a static IP reservation for the server (`192.168.X.X`) was set in the router's DHCP settings, and the router's primary DNS was set to that same address.

---

## 8. Beszel (System Monitoring)

Real-time CPU, RAM, disk, and network monitoring. Runs as two separate pieces: a **Hub** (the dashboard) and an **Agent** (reports stats to the hub).

**Hub**, deployed as a Portainer stack:

```yaml
services:
  beszel:
    image: henrygd/beszel:latest
    container_name: beszel
    restart: unless-stopped
    ports:
      - 8090:8090
    volumes:
      - beszel_data:/beszel_data

volumes:
  beszel_data:
```

Access `http://192.168.X.X:8090`, create an admin account, then click **Add System** to generate a key and token for the agent.

**Agent**, deployed as a second Portainer stack using the key/token from the hub:

```yaml
services:
  beszel-agent:
    image: henrygd/beszel-agent
    container_name: beszel-agent
    restart: unless-stopped
    network_mode: host
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./beszel_agent_data:/var/lib/beszel-agent
    environment:
      LISTEN: 45876
      KEY: 'your-own'
      TOKEN: your-own
      HUB_URL: http://192.168.X.X:8090
```

**Note on the Homepage widget integration:** Homepage's Beszel widget requires Beszel's underlying **PocketBase superuser** credentials specifically, not the regular hub login. If these drift out of sync, reset them directly:

```bash
docker exec beszel /beszel superuser upsert your-email@example.com YourPassword
```

---

## 9. FileBrowser

Web-based file manager for drag-and-drop access to the server's storage, deployed as a Portainer stack.

Create dedicated shared folders first, rather than exposing entire drives:

```bash
mkdir -p /home/your-username/256GB_SSD
mkdir -p "/media/your-username/USB STICK/1TB_HDD"
```

```yaml
version: '3'
services:
  filebrowser:
    image: filebrowser/filebrowser
    restart: always
    ports:
      - "8081:80"
    volumes:
      - "/home/your-username/256GB_SSD:/srv/ssd"
      - "/media/your-username/USB STICK/1TB_HDD:/srv/hdd"
      - filebrowser_data:/database

volumes:
  filebrowser_data:
```

Access `http://192.168.X.X:8081`, log in with the default `admin` / `admin`, and change the password immediately.

---

## 10. Tailscale

Provides secure, private remote access to every service above from anywhere, with real trusted HTTPS certificates and no port forwarding or public exposure.

**Install:**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Authenticate via the URL it prints, using a browser signed into the Tailscale account.

**Rename the device** to something short and memorable via the [Tailscale admin console](https://login.tailscale.com/admin/machines) → select the device → **Edit machine name** → `home`.

**Expose each service over HTTPS with Tailscale Serve:**

```bash
sudo tailscale serve --bg http://192.168.X.X::8081
sudo tailscale serve --bg --https=8443 http://192.168.X.X:3000
sudo tailscale serve --bg --https=8444 http://192.168.X.X:8090
sudo tailscale serve --bg --https=8447 http://192.168.X.X:3001
sudo tailscale serve --bg --https=9444 http://192.168.X.X:9000
```

Resulting in:

| Service | URL |
| --- | --- |
| FileBrowser | `https://home.tail30c3e5.ts.net` |
| AdGuard Home | `https://home.tail30c3e5.ts.net:8443` |
| Beszel | `https://home.tail30c3e5.ts.net:8444` |
| Homepage | `https://home.tail30c3e5.ts.net:8447` |
| Portainer | `https://home.tail30c3e5.ts.net:9444` |

Check the live config at any time:

```bash
tailscale serve status
```

---

## 11. Homepage Dashboard

A single landing page linking to every service, with live widgets for system resources, container counts, DNS stats, and more.

**Use a bind-mounted folder for config** (not a Docker named volume, to avoid permission issues when editing via VS Code):

```bash
mkdir -p ~/homepage-config
sudo chown -R your-username:your-username ~/homepage-config
```

**Deploy as a Portainer stack:**

```yaml
services:
  homepage:
    image: ghcr.io/gethomepage/homepage:latest
    container_name: homepage
    restart: unless-stopped
    ports:
      - 3001:3000
    environment:
      HOMEPAGE_ALLOWED_HOSTS: 192.168.X.X:3001,home.tail30c3e5.ts.net:8447,localhost:3001
    volumes:
      - /home/your-username/homepage-config:/app/config
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /:/host:ro
      - "/media/your-username/USB STICK:/media/your-username/USB STICK:ro"
```

### `services.yaml`

```yaml
- Network:
    - AdGuard Home:
        id: adguard-card
        href: https://home.tail30c3e5.ts.net:8443
        siteMonitor: http://192.168.X.X:3000
        icon: adguard-home.png
        description: DNS ad blocking
        widget:
          type: adguard
          url: http://192.168.X.X:3000
          username: your-own
          password: your-own

    - Tailscale:
        id: tailscale-card
        href: https://console.tailscale.com/admin/machines
        siteMonitor: https://console.tailscale.com/admin/machines
        icon: tailscale.png
        description: Connected to Tailscale
        widget:
          type: tailscale
          deviceid: your-own
          key: your-own

- System Monitor:
    - Beszel:
        id: beszel-card
        href: https://home.tail30c3e5.ts.net:8444
        siteMonitor: http://192.168.X.X:8090
        icon: beszel.png
        description: Real-Time Server Stats
        widget:
          type: beszel
          url: http://192.168.X.X:8090
          username: your-own
          password: your-own
          version: 2

- Infrastructure:
    - Portainer:
        id: portainer-card
        href: https://home.tail30c3e5.ts.net:9444
        siteMonitor: http://192.168.X.X:9000
        icon: portainer.png
        description: Docker container management
        widget:
          type: portainer
          url: http://192.168.X.X:9000
          username: your-own
          password: your-own
          env: 3
          key: your-own

- Services:
    - FileBrowser (SSD):
        id: filebrowser
        href: https://home.tail30c3e5.ts.net/files/ssd
        siteMonitor: http://192.168.X.X:8081
        icon: filebrowser.png
        description: 256GB SSD
        widget:
          type: filebrowser
          url: http://192.168.X.X:8081
          username: your-own
          password: your-own
```

### `widgets.yaml`

```yaml
- logo:
    icon: https://cdn.iconscout.com/icon/premium/png-512-thumb/server-icon-svg-download-png-6628653.png?f=webp&w=512

- resources:
    cpu: true
    memory: true
    cputemp: true
    uptime: true

- resources:
    disk:
      - /
      - /media/your-username/USB STICK
    network: true

- datetime:
    text_size: xl
    format:
      dateStyle: short
      timeStyle: short
      hour12: true

- openmeteo:
    label: City
    latitude: x
    longitude: x
    units: imperial or metic
    cache: 5
```

### `settings.yaml`

```yaml
title: Home Lab
headerStyle: boxedWidgets
theme: dark
color: neutral
background:
  image: https://images.unsplash.com/photo-1548679847-1d4ff48016c7?q=80&w=2671&auto=format&fit=crop
  blur: md
  saturate: 50
  brightness: 50
  opacity: 80
  maxGroupColumns: 4
  disableCollapse: true
  iconStyle: theme
providers:
  openweathermap: your-own
```

### `bookmarks.yaml`

```yaml
- Entertainment:
    - YouTube:
        - abbr: YT
          href: https://youtube.com/
          icon: https://cdn.iconscout.com/icon/free/png-512/free-youtube-logo-icon-svg-download-png-498416.png?f=webp&w=512

    - Twitch:
        - abbr: TW
          href: https://twitch.tv/
          icon: https://cdn.iconscout.com/icon/free/png-512/free-twitch-logo-icon-svg-download-png-9343759.png?f=webp&w=512

    - Spotify:
        - abbr: SPOT
          href: https://spotify.com/
          icon: https://cdn.iconscout.com/icon/free/png-512/free-spotify-logo-icon-svg-download-png-9343751.png?f=webp&w=512

- Online Shopping:
    - Amazon:
        - abbr: AMZ
          href: https://amazon.com/
          icon: https://cdn.iconscout.com/icon/free/png-512/free-amazon-logo-icon-svg-download-png-2285069.png?f=webp&w=512

    - eBay:
        - abbr: EBAY
          href: https://ebay.com/
          icon: https://cdn.brandfetch.io/idC0T6HUjp/w/400/h/400/theme/dark/icon.jpeg?c=1dxbfHSJFAPEGdCLU4o5B

- Productivity:
    - Claude:
        - abbr: CL
          href: https://claude.ai/
          icon: https://cdn.iconscout.com/icon/free/png-512/free-claude-icon-svg-download-png-14426777.png?f=webp&w=512

    - ChatGPT:
        - abbr: CGPT
          href: https://chat.openai.com/
          icon: https://cdn.iconscout.com/icon/free/png-512/free-gpt-icon-svg-download-png-14426781.png?f=webp&w=512
```

### `custom.css`

```css
::-webkit-scrollbar { display: none; }
body { -ms-overflow-style: none; scrollbar-width: none; }

.service-card, .group-header, div[id$="-card"], div[id$="-card"] > div {
  border-radius:20px !important;
  overflow: hidden !important;
  isolation: isolate !important;
}

#adguard-card, #beszel-card, #portainer-card, #filebrowser-card, #tailscale-card{
  position: relative !important;
  background-color: transparent !important;
}

#adguard-card::before, #beszel-card::before,
#portainer-card::before, #filebrowser-card::before, #tailscale-card::before {
  content: "";
  position: absolute;
  top: 2px; left: 2px; right: 2px; bottom: 6px;
  z-index: 0;
  border-radius: 18px !important;
  opacity: 0.35;
}

#adguard-card::before    { background-color: #5eba00 !important; }
#beszel-card::before     { background-color: #747bff !important; }
#portainer-card::before  { background-color: #09090a !important; }
#filebrowser-card::before { background-color: #69d0ff !important; }
#tailscale-card::before { background-color: #131212 !important; }

/* --- Colored resource bars (CPU/RAM/disk/network) --- */
.information-widget-resource div[style*="width"] {
  background: linear-gradient(90deg, #4ade80 0%, #2dd4bf 40%, #3b82f6 75%, #b80fde 100%) !important;
  opacity: 0.55 !important;
  border-radius: 10px !important;
}

/* First resources pill: CPU / RAM / Temp / Uptime */  Disk / Disk / Network 
.widget-container:nth-of-type(2) .information-widget-resource:nth-of-type(1) svg { color: #4ade80 !important; } /* CPU */
.widget-container:nth-of-type(2) .information-widget-resource:nth-of-type(2) svg { color: #22d3ee !important; } /* RAM */
.widget-container:nth-of-type(2) .information-widget-resource:nth-of-type(3) svg { color: #ef4444 !important; } /* Temp */
.widget-container:nth-of-type(2) .information-widget-resource:nth-of-type(4) svg { color: #3b82f6 !important; } /* Uptime */
.widget-container:nth-of-type(3) .information-widget-resource:nth-of-type(1) svg { color: #4ade80 !important; } /* Disk 1 */
.widget-container:nth-of-type(3) .information-widget-resource:nth-of-type(2) svg { color: #4ade80 !important; } /* Disk 2 */
.widget-container:nth-of-type(3) .information-widget-resource:nth-of-type(3) svg { color: #3b82f6 !important; } /* Network */
.information-widget-logo {
  display: flex !important;
  flex-direction: row !important;
  align-items: center !important;
  justify-content: center !important;
  width: auto !important;
  height: 42px !important;
  white-space: nowrap !important;
  gap: 8px !important;
  padding: 0 18px !important;
  background-color: rgba(30, 30, 40, 0.55) !important;
  border-radius: 50px !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
}

.information-widget-logo img {
  max-height: 24px !important;
  max-width: 24px !important;
  width: auto !important;
  height: auto !important;
  object-fit: contain !important;
  margin: 0 !important;
  flex-shrink: 0 !important;
}

/* Dividers between stats inside the same pill (e.g. CPU | RAM | TEMP | UP) */
.information-widget-resource:not(:last-child) {
  border-right: 1px solid rgba(255, 255, 255, 0.12) !important;
  padding-right: 14px !important;
  margin-right: 14px !important;
}

.information-widget-logo {
  width: auto !important;
  white-space: nowrap !important;
  gap: 8px !important;
}

.logo-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-main, #e8e8ee);
  letter-spacing: 0.03em;
  line-height: 1;
}

.service-card > div { position: relative; z-index: 1; }

.service-name, .service-description {
  color: #f5f5f5d9 !important;
}

.service-group-name {
  color: #cfcfcf !important;
  font-weight: 700 !important;
}

@media (min-width: 768px) {

  .widget-container {
    height: 62px !important;

    display: flex !important;
    align-items: center !important;
    border-radius: 50px !important;
    background-color: rgba(58, 58, 58, 0.2) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    padding: 5px 16px !important;
    margin-top: 10px !important;
  }
  .widget-container .information-widget-resource {
    align-items: center !important;
  }
  .widget-container > div:last-child {
    text-align: center !important;
    margin-left: 0 !important;
  }
}
```

### `custom.js`

Injects a text label next to the logo icon, since Homepage's logo widget is icon-only by default:

```javascript
function addLogoText() {
  const logoEl = document.querySelector('.information-widget-logo');
  if (logoEl && !logoEl.querySelector('.logo-text')) {
    const span = document.createElement('span');
    span.className = 'logo-text';
    span.textContent = 'Home Lab';
    logoEl.insertBefore(span, logoEl.firstChild);
  }
}

addLogoText();
const observer = new MutationObserver(addLogoText);
observer.observe(document.body, { childList: true, subtree: true });
```

Access the finished dashboard at `http://192.168.X.X:3001` locally, or `https://home.tail30c3e5.ts.net:8447` remotely via Tailscale.

---

## Credentials

Every `your-own` placeholder above should be replaced with real values **locally only**, never committed to the repository.
