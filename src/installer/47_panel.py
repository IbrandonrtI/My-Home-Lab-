PANEL_PORT = 8300
PANEL_HTTPS = 1100
PANEL_SHARE = "/usr/local/share/homelab-panel"
PANEL_UNIT = "/etc/systemd/system/homelab-panel.service"
PANEL_UI_FILES = ["index.html", "app.js", "app.css", "icon.svg"]
PANEL_SHIPPED_FILES = [("shipped-services.yaml", "services.yaml"), ("shipped-stat-extras.yaml", "stat-extras.yaml")]
PANEL_SUDOERS = "/etc/sudoers.d/homelab-panel"
PANEL_SUDO_EXACT = ["status", "health", "check", "actions", "remount", "abort", "setups", "apps", "moveboot"]
PANEL_SUDO_WITH_WORDS = ["setups", "rename", "sleep", "wake", "add", "wipe", "disconnect", "move", "setup", "bootadd", "appsfix"]
PANEL_SUDO_BACKUP_EXACT = ["state", "save", "sshkey", "cloud-add"]
PANEL_SUDO_BACKUP_WORDS = ["versions", "browse", "run", "dry", "restore", "delete", "toggle", "sshtest", "stream"]
PANEL_SUDO_UPDATE = ["/usr/local/sbin/homelab-update check", "/usr/local/sbin/homelab-update --yes", "/usr/bin/apt-get update", "/usr/bin/apt-get -y upgrade",
                     "/usr/bin/systemctl reboot"]


def panel_applies():
    return not Mode.existing


def panel_password_file():
    return P(Ctx.home + "/.config/homelab-panel/password")


def panel_unit_text():
    hosts = "%s:%d" % (Ctx.fqdn, PANEL_HTTPS)
    frame = ["https://%s:%d" % (Ctx.fqdn, SERVE[0][0])] + (["http://%s:%d" % (Ctx.lan, PORTS["homepage"])] if Ctx.lan else [])
    return "\n".join([
        "# Written by homelab-setup. The control panel of the dashboard (the Customize tab). Change nothing here: an upgrade puts it back.",
        "[Unit]",
        "Description=Homelab control panel (the Customize tab)",
        "After=network.target docker.service",
        "",
        "[Service]",
        "Type=simple",
        "User=%s" % Ctx.user,
        "Environment=HLP_HOME=%s" % Ctx.home,
        "Environment=HLP_PORT=%d" % PANEL_PORT,
        "Environment=HLP_HOSTS=%s" % hosts,
        "Environment=HLP_FRAME=%s" % ",".join(frame),
        "Environment=HLP_HOMEPAGE_URL=https://%s:%d" % (Ctx.fqdn, SERVE[0][0]),
        "ExecStart=/usr/bin/python3 /usr/local/sbin/homelab-panel serve",
        "KillMode=process",
        "Restart=on-failure",
        "RestartSec=3",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        ""])


def panel_sudoers_text():
    user = Ctx.user or ""
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
        return ""
    drives = "/usr/local/sbin/drives panel "
    cmds = [drives + w for w in PANEL_SUDO_EXACT] + [drives + w + " *" for w in PANEL_SUDO_WITH_WORDS]
    backup = "/usr/local/sbin/homelab-backup-tasks panel "
    bcmds = [backup + w for w in PANEL_SUDO_BACKUP_EXACT] + [backup + w + " *" for w in PANEL_SUDO_BACKUP_WORDS]
    return "\n".join([
        "# Written by homelab-setup. Lets the control panel (the Drives and Updates tabs) run exactly these drive, backup and update commands as root, without a password.",
        "# Anything else still asks for your password. Each command checks its own words again. Change nothing here: an upgrade puts it back.",
        "Cmnd_Alias HOMELAB_PANEL_DRIVES = " + ", \\\n    ".join(cmds),
        "Cmnd_Alias HOMELAB_PANEL_BACKUP = " + ", \\\n    ".join(bcmds),
        "Cmnd_Alias HOMELAB_PANEL_UPDATE = " + ", \\\n    ".join(PANEL_SUDO_UPDATE),
        "%s ALL=(root) NOPASSWD: HOMELAB_PANEL_DRIVES" % user,  # homelab-repocheck: ignore
        "%s ALL=(root) NOPASSWD: HOMELAB_PANEL_BACKUP" % user,  # homelab-repocheck: ignore
        "%s ALL=(root) NOPASSWD: HOMELAB_PANEL_UPDATE" % user,  # homelab-repocheck: ignore
        ""])


def panel_sudoers_install():
    text = panel_sudoers_text()
    if not text or read_file(P(PANEL_SUDOERS)) == text:
        return False
    if not Opt.dry and have("visudo"):
        tmp = P("/run/homelab-panel-sudoers.check")
        write_file(tmp, text, 0o600)
        rc, txt = run(["visudo", "-cf", tmp])
        try:
            os.unlink(tmp)
        except OSError:
            pass
        if rc != 0:
            warn("The sudo rule for the Drives tab was not installed because sudo did not accept it (%s). The rest of the panel works." % txt.strip()[-160:])
            return False
    write_file(P(PANEL_SUDOERS), text, 0o440)
    return True


def panel_files_wanted():
    items = [(P(PANEL_SHARE + "/ui/" + fn), read_file(repo_file("panel", "ui", fn))) for fn in PANEL_UI_FILES]
    items += [(P(PANEL_SHARE + "/" + dst), subst(read_file(repo_file("homepage-config", src)))) for dst, src in PANEL_SHIPPED_FILES]
    return items + [(P(PANEL_UNIT), panel_unit_text())]


def panel_set_password(pw):
    script = P("/usr/local/sbin/homelab-panel")
    env = dict(os.environ, HLP_HOME=P(Ctx.home), HLP_STATE=P(Ctx.home + "/.config/homelab-panel"))
    if FAKE or os.geteuid() != 0:
        args = [sys.executable, script, "set-password", "--stdin"]
    else:
        args = ["sudo", "-u", Ctx.user, "env", "HLP_HOME=" + Ctx.home, "python3", script, "set-password", "--stdin"]
    rc, txt = run(args, input_text=pw + "\n", env=env, timeout=60)
    if rc != 0:
        raise Abort("The panel password could not be saved: %s" % txt.strip()[-200:])
    if os.geteuid() == 0:
        d = P(Ctx.home + "/.config/homelab-panel")
        for p in (P(Ctx.home + "/.config"), d, d + "/password"):
            if os.path.exists(p):
                chown(p, Ctx.uid, Ctx.gid)


@step
class PanelFiles(Step):
    """Install the control panel's page files and sudo rule, and start its service."""
    id, group = "panel-files", "Homepage"
    title = "The control panel (Customize tab): its page files installed and the service running"
    needs = ("scripts", "homepage-files", "tailscale-login")

    def applies(self):
        return panel_applies()

    def probe(self):
        for path, body in panel_files_wanted():
            if not body or read_file(path) != body:
                return "todo"
        if panel_sudoers_text() and read_file(P(PANEL_SUDOERS)) != panel_sudoers_text():
            return "todo"
        return "done" if run(["systemctl", "is-active", "homelab-panel"])[1].strip() == "active" else "todo"

    def run(self):
        changed = False
        for path, body in panel_files_wanted():
            if not body:
                raise Abort("A file of the control panel is missing in the repository (looked for it in %s/panel/ui)." % Ctx.repo)
            if read_file(path) != body:
                write_file(path, body, 0o644)
                changed = True
        if panel_sudoers_install():
            changed = True
        act(["systemctl", "daemon-reload"])
        act(["systemctl", "enable", "--now", "homelab-panel"])
        if changed and not Opt.dry and run(["systemctl", "is-active", "homelab-panel"])[1].strip() == "active":
            act(["systemctl", "restart", "homelab-panel"])


@step
class PanelServe(Step):
    """Publish the control panel on a Tailscale HTTPS address (port 1100) that only the user's own devices can reach."""
    id, group = "panel-serve", "Homepage"
    title = "The control panel has a Tailscale HTTPS address (port 1100), reachable only from your own devices"
    needs = ("panel-files", "tailscale-https")

    def applies(self):
        return panel_applies()

    def probe(self):
        cur = BY_ID["tailscale-serve"]._current()
        return "done" if cur.get(PANEL_HTTPS, "").rstrip("/") == "http://127.0.0.1:%d" % PANEL_PORT else "todo"

    def run(self):
        rc, txt = act(["tailscale", "serve", "--bg", "--https=%d" % PANEL_HTTPS, "http://127.0.0.1:%d" % PANEL_PORT], timeout=60)
        if rc != 0:
            raise Abort("tailscale serve for the control panel failed: %s" % txt.strip()[-300:])


@step
class PanelPassword(Step):
    id, group = "panel-password", "Homepage"
    title = "The control panel uses the admin password"
    needs = ("panel-files",)

    def applies(self):
        return panel_applies()

    def probe(self):
        return "done" if os.path.exists(panel_password_file()) else "todo"

    def run(self):
        if Opt.dry:
            out("      would save the admin password (hashed) as the control panel's password in %s" % panel_password_file().replace(ROOT, ""))
            return
        panel_set_password(need_password("it is also the control panel's password"))
        good("The control panel uses the admin password (change it later with:  homelab panel password)")


TERMINAL_UNIT = "/etc/systemd/system/homelab-terminal.service"
TERMINAL_SOCK = "/run/homelab-terminal/ttyd.sock"


def terminal_unit_text():
    theme = '{"background":"#0a0f19","foreground":"#dbe4f5","cursor":"#8ab4ff"}'
    return "\n".join([
        "# Written by homelab-setup. The web terminal of the dashboard (the Terminal card on the Links tab). Change nothing here: an upgrade puts it back.",
        "[Unit]",
        "Description=Homelab web terminal (the Terminal card of the Links tab)",
        "After=network.target",
        "",
        "[Service]",
        "Type=simple",
        "User=%s" % Ctx.user,
        "WorkingDirectory=%s" % Ctx.home,
        "Environment=HOME=%s" % Ctx.home,
        "RuntimeDirectory=homelab-terminal",
        "RuntimeDirectoryMode=0700",
        "ExecStart=/usr/bin/ttyd --writable --interface %s --base-path /terminal --ping-interval 30 -t fontSize=15 -t cursorBlink=true -t 'theme=%s' /bin/bash -l" % (TERMINAL_SOCK, theme),
        "Restart=on-failure",
        "RestartSec=3",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        ""])


@step
class TerminalFiles(Step):
    """Install ttyd and start the web terminal service used by the Terminal card."""
    id, group = "terminal", "Homepage"
    title = "The web terminal (Terminal card, Links tab): ttyd installed and the service running"
    needs = ("panel-files",)

    def applies(self):
        return panel_applies()

    def probe(self):
        if not pkg_installed("ttyd") or read_file(P(TERMINAL_UNIT)) != terminal_unit_text():
            return "todo"
        return "done" if run(["systemctl", "is-active", "homelab-terminal"])[1].strip() == "active" else "todo"

    def run(self):
        if not pkg_installed("ttyd"):
            rc, txt = act(["apt-get", "-oDPkg::Lock::Timeout=600", "install", "-y", "-q", "ttyd"], env=apt_env(), timeout=900)
            if rc != 0 and not Opt.dry:
                raise Abort("The terminal program (ttyd) could not be installed: %s\n      Try it by hand: sudo apt-get install ttyd" % txt.strip()[-200:])
        changed = read_file(P(TERMINAL_UNIT)) != terminal_unit_text()
        if changed:
            write_file(P(TERMINAL_UNIT), terminal_unit_text(), 0o644)
        act(["systemctl", "daemon-reload"])
        act(["systemctl", "enable", "--now", "homelab-terminal"])
        if changed and not Opt.dry and run(["systemctl", "is-active", "homelab-terminal"])[1].strip() == "active":
            act(["systemctl", "restart", "homelab-terminal"])


def music_writable():
    rc, _ = run(["runuser", "-u", Ctx.user, "--", "test", "-w", P(music_folder())])
    return rc == 0


@step
class MusicFolderAccess(Step):
    """Give the lab's user write access to the music folder so the Upload card can add songs."""
    id, group = "music-access", "Services"
    title = "The lab's user may add songs to the music folder (the Upload card)"
    needs = ("folders",)

    def applies(self):
        return panel_applies() and bool(music_folder())

    def detail(self):
        return music_folder()

    def probe(self):
        return "done" if music_writable() else "todo"

    def run(self):
        folder = P(music_folder())
        if not have("setfacl"):
            act(["apt-get", "-oDPkg::Lock::Timeout=600", "install", "-y", "-q", "acl"], env=apt_env())
        if have("setfacl"):
            act(["setfacl", "-m", "u:%s:rwx" % Ctx.user, folder])
        if not Opt.dry and not music_writable():
            act(["chmod", "o+rwx", folder])
        if not Opt.dry and not music_writable():
            warn("The music folder %s still cannot be written by %s. The Upload card cannot add songs until it can." % (folder, Ctx.user))
