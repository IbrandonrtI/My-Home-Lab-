

class Mode:
    """How the machine was classified: new, or an existing lab."""
    existing = False          # this machine already runs the lab (built by hand)


def fetch_bytes(u, timeout=60):
    """Download a file and return its bytes."""
    if FAKE:
        if os.environ.get("HLS_FETCH_FAIL"):
            raise OSError("simulated download failure")
        return b"FAKE-DOWNLOAD " + u.encode()
    req = urllib.request.Request(u, headers={"User-Agent": "homelab-setup/" + VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def pkg_installed(name):
    """True when the apt package is installed."""
    rc, txt = run(["dpkg-query", "-W", "-f=${Status}", name])
    return rc == 0 and "install ok installed" in txt


def ssh_peers_over_tailscale():
    """True if someone is connected to this machine's SSH through Tailscale (a step that restarts Tailscale would drop them)."""
    rc, txt = run(["ss", "-H", "-tn", "state", "established", "( sport = :22 )"])
    for line in txt.splitlines():
        for tok in line.split():
            m = re.match(r"^(\d+)\.(\d+)\.\d+\.\d+:\d+$", tok)
            if m and int(m.group(1)) == 100 and 64 <= int(m.group(2)) <= 127:
                return True
    return False


# ---------------------------------------------------------------- System
@step
class OsSupported(Step):
    id, group, title = "os", "System", "Operating system is supported"

    def probe(self):
        ok = (Ctx.os_id == "ubuntu" and Ctx.os_version in ("22.04", "24.04", "26.04")) or \
             (Ctx.os_id == "linuxmint" and Ctx.os_version.split(".")[0] in ("21", "22", "23")) or \
             (Ctx.os_id == "debian" and Ctx.os_version in ("12", "13"))
        return "done" if ok else "todo"

    def detail(self):
        return Ctx.os_name

    def help(self):
        return ("homelab-setup supports Ubuntu 22.04/24.04, Linux Mint 21/22 and Debian 12/13. Detected: %s." % Ctx.os_name)


@step
class AptUpgrade(Step):
    id, group, title = "apt-upgrade", "System", "System packages updated and upgraded"

    def probe(self):
        if State.ran("apt-upgrade"):
            return "done"
        return "na" if Mode.existing else "todo"

    def detail(self):
        return State.data["ran"].get("apt-upgrade", "")

    def run(self):
        env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
        act(["apt-get", "update", "-q"], env=env, check=True, timeout=900)
        act(["apt-get", "upgrade", "-y", "-q", "-o", "Dpkg::Options::=--force-confold"], env=env, check=True, timeout=3600)
        if not Opt.dry:
            State.mark("apt-upgrade")


REQUIRED_PKGS = ["curl", "ca-certificates", "gnupg", "rsync", "cron", "python3-yaml", "smartmontools", "hdparm"]
OPTIONAL_PKGS = ["mergerfs", "parted"]


@step
class Packages(Step):
    id, group, title = "packages", "System", "Helper programs installed (rsync, cron, smartmontools, mergerfs, ...)"

    def probe(self):
        missing = [p for p in REQUIRED_PKGS if not pkg_installed(p)]
        return "done" if not missing else "todo"

    def run(self):
        need = [p for p in REQUIRED_PKGS if not pkg_installed(p)]
        if need:
            apt_install(need)
        for p in OPTIONAL_PKGS:
            if not pkg_installed(p):
                rc, txt = act(["apt-get", "install", "-y", "-q", p], env=dict(os.environ, DEBIAN_FRONTEND="noninteractive"))
                if rc != 0 and not Opt.dry:
                    warn("Optional package %s could not be installed (%s). The drives tool needs it later." % (p, txt.strip()[-120:]))


@step
class DockerInstalled(Step):
    id, group, title = "docker", "System", "Docker installed (with Compose and Buildx)"
    needs = ("os", "packages")

    def probe(self):
        rc, _ = docker("info", timeout=30)
        rc2, _ = docker("compose", "version")
        rc3, _ = docker("buildx", "version")
        return "done" if rc == 0 and rc2 == 0 and rc3 == 0 else "todo"

    def run(self):
        distro = "debian" if Ctx.os_id == "debian" else "ubuntu"
        suite = Ctx.os_codename
        if not suite:
            raise Abort("Could not read the release name from /etc/os-release.")
        if pkg_installed("docker.io") or pkg_installed("docker-compose") or pkg_installed("podman-docker"):
            if containers_all():
                raise Abort("Another Docker package is installed and has containers. The installer does not remove it. Remove it manually first.")
            act(["apt-get", "remove", "-y", "-q", "docker.io", "docker-compose", "podman-docker", "containerd", "runc"],
                env=dict(os.environ, DEBIAN_FRONTEND="noninteractive"))
        if Opt.dry:
            out("      would add Docker's apt repository for %s %s and install docker-ce" % (distro, suite))
            return
        os.makedirs(P("/etc/apt/keyrings"), exist_ok=True)
        try:
            key = fetch_bytes("https://download.docker.com/linux/%s/gpg" % distro)
        except Exception as e:
            raise Abort("Could not download Docker's signing key (%s). Check the internet connection." % e) from None
        with open(P("/etc/apt/keyrings/docker.asc"), "wb") as f:
            f.write(key)
        os.chmod(P("/etc/apt/keyrings/docker.asc"), 0o644)
        arch = run(["dpkg", "--print-architecture"])[1].strip() or "amd64"
        write_file(P("/etc/apt/sources.list.d/docker.sources"),
                   "Types: deb\nURIs: https://download.docker.com/linux/%s\nSuites: %s\nComponents: stable\n"
                   "Architectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n" % (distro, suite, arch), 0o644)
        run(["apt-get", "update", "-q"], env=dict(os.environ, DEBIAN_FRONTEND="noninteractive"), check=True, timeout=600)
        apt_install(["docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin", "docker-compose-plugin"])
        act(["systemctl", "enable", "--now", "docker"])


@step
class DockerGroup(Step):
    id, group, title = "docker-group", "System", "Your user can run Docker without sudo"
    needs = ("docker",)

    def probe(self):
        rc, txt = run(["id", "-nG", Ctx.user])
        return "done" if rc == 0 and "docker" in txt.split() else "todo"

    def run(self):
        act(["usermod", "-aG", "docker", Ctx.user], check=True)


# ---------------------------------------------------------------- Tailscale
@step
class TailscaleInstalled(Step):
    id, group, title = "tailscale-install", "Tailscale", "Tailscale installed"
    needs = ("os", "packages")

    def probe(self):
        return "done" if have("tailscale") and have("tailscaled") else "todo"

    def run(self):
        distro = "debian" if Ctx.os_id == "debian" else "ubuntu"
        suite = Ctx.os_codename
        if Opt.dry:
            out("      would add Tailscale's apt repository for %s %s and install tailscale" % (distro, suite))
            return
        base = "https://pkgs.tailscale.com/stable/%s/%s" % (distro, suite)
        try:
            os.makedirs(P("/usr/share/keyrings"), exist_ok=True)
            os.makedirs(P("/etc/apt/sources.list.d"), exist_ok=True)
            with open(P("/usr/share/keyrings/tailscale-archive-keyring.gpg"), "wb") as f:
                f.write(fetch_bytes(base + ".noarmor.gpg"))
            with open(P("/etc/apt/sources.list.d/tailscale.list"), "wb") as f:
                f.write(fetch_bytes(base + ".tailscale-keyring.list"))
            env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
            run(["apt-get", "update", "-q"], env=env, check=True, timeout=600)
            apt_install(["tailscale"])
        except Abort:
            raise
        except Exception as e:
            raise Abort("Tailscale's package repository did not work (%s). Install Tailscale manually (https://tailscale.com/download), then run `sudo homelab-setup install` again." % e) from None
        act(["systemctl", "enable", "--now", "tailscaled"])


def do_tailscale_login():
    """Interactive: show the login link and wait. Uses TS_AUTHKEY if it is set in the environment."""
    Ctx.refresh_tailscale()
    if Ctx.fqdn:
        return True
    if Opt.dry:
        out("      would run: sudo tailscale up   (shows a login link; open it in a browser and approve this machine)")
        return True
    if not have("tailscale"):
        raise Abort("Tailscale is not installed yet.")
    key = os.environ.get("TS_AUTHKEY", "")
    # --accept-dns=false is repeated on purpose: once it is set, `tailscale up` refuses to run (and a login after the
    # machine was removed from the admin page or its key expired would fail) unless every non-default setting is named.
    args = ["tailscale", "up", "--hostname=" + Ctx.hostname.lower(), "--accept-dns=false"]
    if key:
        args.append("--auth-key=" + key)
    out("")
    say("Tailscale needs a login. Open the link below in any browser, sign in and approve this machine.")
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    shown = False
    end = time.time() + float(os.environ.get("HLS_TS_WAIT", "900"))
    import threading
    lines = []

    def reader():
        for line in proc.stdout:
            lines.append(line.rstrip())
    th = threading.Thread(target=reader, daemon=True)
    th.start()
    Live.begin("Waiting for you to approve this machine in Tailscale (open the link above)", own_clock=True)
    try:
        while time.time() < end:
            if not shown:
                for l in lines:
                    m = re.search(r"https://\S+", l)
                    if m and "login" in m.group(0) or (m and "/a/" in m.group(0)):
                        out("")
                        out("      %s%s%s" % (U, m.group(0), N))
                        out("")
                        shown = True
                        break
            Ctx.refresh_tailscale()
            if Ctx.fqdn:
                good("Tailscale is connected as %s" % Ctx.fqdn)
                try:
                    proc.terminate()
                except OSError:
                    pass
                return True
            if proc.poll() is not None and not Ctx.fqdn:
                time.sleep(0.5 if not FAKE else 0.05)
                Ctx.refresh_tailscale()
                if Ctx.fqdn:
                    return True
                raise Abort("Tailscale stopped without logging in:\n" + "\n".join(lines[-5:]))
            time.sleep(2 if not FAKE else 0.05)
        try:
            proc.terminate()
        except OSError:
            pass
    finally:
        Live.end()
    raise Abort("The Tailscale login was not completed within 15 minutes. Run `sudo homelab-setup fill` to try again.")


@step
class TailscaleLogin(Step):
    id, group, title = "tailscale-login", "Tailscale", "Logged in to Tailscale"
    kind = "manual"
    needs = ("tailscale-install",)

    def probe(self):
        Ctx.refresh_tailscale()
        return "done" if Ctx.fqdn else "todo"

    def detail(self):
        return Ctx.fqdn

    def help(self):
        return ("Start the walk-through, open the login link it shows and approve this machine:\n$ sudo homelab-setup fill")

    def fill_help(self):
        return "A login link is shown below. Open it in a browser, sign in and approve this machine."

    def fill(self):
        return do_tailscale_login()


@step
class TailscaleHttps(Step):
    id, group, title = "tailscale-https", "Tailscale", "MagicDNS and HTTPS certificates are on in your Tailscale account"
    kind = "manual"
    needs = ("tailscale-login",)

    def probe(self):
        js = ts_status() or {}
        return "done" if js.get("CertDomains") else "todo"

    def help(self):
        return ("Open https://login.tailscale.com/admin/dns, make sure MagicDNS is on, then scroll to HTTPS Certificates and choose Enable HTTPS. The installer detects the change on the next `sudo homelab-setup refresh`.")

    def fill(self):
        if Opt.dry:
            out("      would ask for MagicDNS and HTTPS certificates to be turned on in the Tailscale admin page")
            return True
        say(self.help())
        ask("Press Enter when it is done")
        return self.probe() == "done"


@step
class ServeMappings(Step):
    id, group, title = "tailscale-serve", "Tailscale", "Tailscale Serve addresses (ports 1000-1008) set"
    needs = ("tailscale-login", "tailscale-https")

    def _current(self):
        rc, txt = run(["tailscale", "serve", "status", "--json"], timeout=20)
        try:
            js = json.loads(txt) if rc == 0 else {}
        except ValueError:
            js = {}
        found = {}
        for k, v in (js.get("Web") or {}).items():
            m = re.search(r":(\d+)$", k)
            if m:
                prox = ((v.get("Handlers") or {}).get("/") or {}).get("Proxy", "")
                found[int(m.group(1))] = prox
        return found

    def probe(self):
        cur = self._current()
        return "done" if all(cur.get(p, "").rstrip("/") == "http://%s:%d" % (Ctx.lan, PORTS[s]) for p, s in SERVE) else "todo"

    def run(self):
        cur = self._current()
        for p, s in SERVE:
            want = "http://%s:%d" % (Ctx.lan, PORTS[s])
            if cur.get(p, "").rstrip("/") != want:
                rc, txt = act(["tailscale", "serve", "--bg", "--https=%d" % p, want], timeout=60)
                if rc != 0:
                    raise Abort("tailscale serve for port %d failed: %s" % (p, txt.strip()[-300:]))


# ---------------------------------------------------------------- Network: port 53
def port53_listeners():
    """Names of the processes that listen on port 53."""
    rc, txt = run(["ss", "-H", "-tulpn", "sport = :53"])
    procs = []
    for line in txt.splitlines():
        m = re.search(r'users:\(\("([^"]+)"', line)
        procs.append(m.group(1) if m else "unknown")
    return procs


@step
class Port53(Step):
    id, group, title = "port53", "Network", "Port 53 is free for AdGuard Home"
    needs = ("docker",)

    def probe(self):
        procs = port53_listeners()
        return "done" if all(p.lower().startswith("adguard") for p in procs) else "todo"

    def run(self):
        if ssh_peers_over_tailscale():
            raise Abort("This session is connected through Tailscale, and this step restarts Tailscale, which would end the session. Connect over the local network instead (`ssh %s@%s`) and run `sudo homelab-setup refresh` again." %
                        (Ctx.user, Ctx.lan))
        gw = Ctx.gateway or "1.1.1.1"
        out("")
        say("AdGuard Home needs port 53, which the built-in DNS resolver (systemd-resolved) currently holds. The resolver will be stopped and disabled. This machine will then ask your router (%s) for names. AdGuard Home runs on this machine, and you point each device at it by hand." % gw)
        if not Opt.dry and not Opt.yes and not yesno("Free port 53 now?", False):
            raise Abort("Port 53 was left unchanged. Run `sudo homelab-setup refresh` when you are ready.")
        # pull the image first, while DNS still works
        act(["docker", "pull", "adguard/adguardhome:v0.107.79"], timeout=900)
        act(["systemctl", "disable", "systemd-resolved"])
        act(["systemctl", "stop", "systemd-resolved"])
        if have("tailscale"):
            # Tailscale must not take /etc/resolv.conf over: with systemd-resolved off, its own resolver (100.100.100.100)
            # can lose its upstream servers after a reboot or an update, and the machine then cannot look up names.
            act(["tailscale", "set", "--accept-dns=false"])
        if not Opt.dry:
            try:
                os.remove(P("/etc/resolv.conf"))
            except OSError:
                pass
            write_file(P("/etc/resolv.conf"), "nameserver %s\n" % gw, 0o644)
        if run(["systemctl", "is-active", "tailscaled"])[1].strip() == "active":
            act(["systemctl", "restart", "tailscaled"])
        if not Opt.dry:
            time.sleep(2 if not FAKE else 0)
            others = [p for p in port53_listeners() if not p.lower().startswith("adguard")]
            if others:
                raise Abort("Something still uses port 53: %s" % ", ".join(sorted(set(others))))


@step
class DnsStable(Step):
    id, group, title = "dns-stable", "Network", "DNS keeps working after a reboot (Tailscale does not manage DNS)"
    needs = ("tailscale-install", "port53")

    def applies(self):
        return not Mode.existing

    def probe(self):
        txt = read_file(P("/etc/resolv.conf"))
        return "done" if "nameserver" in txt and "100.100.100.100" not in txt else "todo"

    def run(self):
        act(["tailscale", "set", "--accept-dns=false"])
        if Opt.dry:
            return
        if "100.100.100.100" in read_file(P("/etc/resolv.conf")):
            backup = P("/etc/resolv.pre-tailscale-backup.conf")
            old = read_file(backup)
            if "nameserver" not in old or "100.100.100.100" in old:
                old = "nameserver %s\n" % (Ctx.gateway or "1.1.1.1")
            try:
                os.remove(P("/etc/resolv.conf"))
            except OSError:
                pass
            write_file(P("/etc/resolv.conf"), old, 0o644)
        if not FAKE:
            try:
                socket.gethostbyname("github.com")
            except OSError:
                raise Abort("Name resolution still fails. Check `cat /etc/resolv.conf` (it should list your router) and the network connection.") from None


# ---------------------------------------------------------------- Platform
def folder_plan():
    """The folders the lab needs, as (path, owner id, group id) tuples."""
    h = Ctx.home
    u, g = Ctx.uid, Ctx.gid
    return [
        ("/mnt/storage", 0, 0), ("/mnt/storage/immich", u, g), ("/mnt/storage/filebrowser", u, g),
        ("/mnt/storage/nextcloud", 33, 33),
        (h + "/nextcloud", u, g), (h + "/nextcloud/html", 33, 33), (h + "/nextcloud/db", 0, 0),
        (h + "/immich", u, g), (h + "/immich/postgres", 0, 0),
        (h + "/speedtest-tracker", u, g), (h + "/homepage-config", u, g), (h + "/750GB_HDD", u, g),
        ("/opt/adguard-docker", 0, 0), ("/opt/adguard-docker/conf", 0, 0), ("/opt/adguard-docker/work", 0, 0),
    ]


@step
class Folders(Step):
    id, group, title = "folders", "Platform", "Folders for the services exist"
    needs = ("os",)

    def probe(self):
        return "done" if all(os.path.isdir(P(p)) for p, _, _ in folder_plan()) else "todo"

    def run(self):
        for p, u, g in folder_plan():
            mkdirs(P(p), u, g)


def restored_nc_password():
    """The database password from a restored Nextcloud config.php, but only if it belongs to the database user our stack
    creates ('nextcloud'). Nextcloud makes its own extra database user (oc_...) with a random password on a first install;
    that one is not ours to reuse."""
    cfg = read_file(P(Ctx.home + "/nextcloud/html/config/config.php"))
    user = re.search(r"'dbuser'\s*=>\s*'([^']*)'", cfg)
    pw = re.search(r"'dbpassword'\s*=>\s*'([^']*)'", cfg)
    if user and pw and user.group(1) == "nextcloud":
        return pw.group(1)
    return None


@step
class SecretsFile(Step):
    id, group, title = "secrets", "Platform", "Passwords and keys generated and saved in one root-only file"
    needs = ("os", "restore-configs")

    def probe(self):
        Secrets.load()
        if not all(Secrets.get(k) for k in ("DB_PASSWORD", "NC_DB_PASSWORD", "APP_KEY")):
            return "na" if Mode.existing else "todo"
        old = restored_nc_password()
        if old and old != Secrets.get("NC_DB_PASSWORD") and not Mode.existing:
            return "todo"            # a restored Nextcloud brought its own database password
        return "done"

    def detail(self):
        return SECRET_FILE.replace(ROOT, "")

    def run(self):
        Secrets.load()
        for k, f in (("DB_PASSWORD", lambda: rand_alnum(28)), ("NC_DB_PASSWORD", lambda: rand_alnum(28)),
                     ("APP_KEY", rand_app_key)):
            if not Secrets.get(k):
                Secrets.vals[k] = f()
        # a restored Nextcloud keeps its old database password
        old = restored_nc_password()
        if old:
            Secrets.vals["NC_DB_PASSWORD"] = old
        Secrets.save()
