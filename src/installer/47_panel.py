# ================================================================ the control panel (the Customize tab of the dashboard)
# A small web program (scripts/homelab-panel) that changes the look, the layout, the cards and the links of the dashboard by pointing and
# clicking. It runs as the lab's own user and listens only on this machine; Tailscale Serve gives it an HTTPS address that only your own
# devices can reach, and it has its own password. See the top of scripts/homelab-panel.
PANEL_PORT = 8300                       # on this machine only (127.0.0.1)
PANEL_HTTPS = 1100                      # the Tailscale Serve port (https://NAME.ts.net:1100)
PANEL_SHARE = "/usr/local/share/homelab-panel"
PANEL_UNIT = "/etc/systemd/system/homelab-panel.service"
PANEL_UI_FILES = ["index.html", "app.js", "app.css", "icon.svg"]


def panel_applies():
    """The panel is part of a machine the installer built (a server built by hand is only looked at)."""
    return not Mode.existing


def panel_password_file():
    return P(Ctx.home + "/.config/homelab-panel/password")


def panel_unit_text():
    """The systemd unit: the panel runs as the lab's user (no sudo needed for what it does), only on 127.0.0.1."""
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
        "Restart=on-failure",
        "RestartSec=3",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectSystem=full",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        ""])


def panel_files_wanted():
    """[(path, text)] of everything the panel needs on disk: its page files and the unit."""
    items = [(P(PANEL_SHARE + "/ui/" + fn), read_file(repo_file("panel", "ui", fn))) for fn in PANEL_UI_FILES]
    return items + [(P(PANEL_UNIT), panel_unit_text())]


def panel_set_password(pw):
    """Save the panel's password (hashed, in the lab user's own folder) by running the panel's own program as that user."""
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


def panel_ask_password():
    """Ask for the panel's password (twice). Returns True when it was saved."""
    if Opt.dry:
        out("      would ask for a password for the control panel and save it (hashed) in %s" % panel_password_file().replace(ROOT, ""))
        return True
    say("Choose a password for the control panel (the Customize tab). It is only for the panel: your other logins stay as they are.")
    for _ in range(3):
        pw = ask_secret("Panel password (at least 10 characters)")
        if len(pw) < 10:
            warn("The password needs at least 10 characters.")
            continue
        if pw != pw.strip():
            warn("The password cannot start or end with a space.")
            continue
        if ask_secret("Type it again") != pw:
            warn("The two entries did not match.")
            continue
        panel_set_password(pw)
        good("The control panel password is saved.")
        return True
    warn("No password was saved. Choose one later with:  homelab panel password")
    return False


@step
class PanelFiles(Step):
    id, group = "panel-files", "Homepage"
    title = "The control panel (Customize tab): its page files installed and the service running"
    needs = ("scripts", "homepage-files", "tailscale-login")

    def applies(self):
        return panel_applies()

    def probe(self):
        for path, body in panel_files_wanted():
            if not body or read_file(path) != body:
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
        act(["systemctl", "daemon-reload"])
        act(["systemctl", "enable", "--now", "homelab-panel"])
        if changed and not Opt.dry and run(["systemctl", "is-active", "homelab-panel"])[1].strip() == "active":
            act(["systemctl", "restart", "homelab-panel"])         # new page files or a new unit: start the service again
        if interactive() and not Opt.yes and not os.path.exists(panel_password_file()):
            out("")
            panel_ask_password()


@step
class PanelServe(Step):
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
    title = "The control panel has its own password"
    kind = "manual"
    optional = True
    needs = ("panel-files",)

    def applies(self):
        return panel_applies()

    def probe(self):
        return "done" if os.path.exists(panel_password_file()) else "todo"

    def help(self):
        return ("Choose the password for the Customize tab (it is only for the panel). Run this as yourself, without sudo:\n$ homelab panel password\n"
                "or let the walk-through ask you:\n$ sudo homelab-setup fill")

    def fill_help(self):
        return "Choose a password for the control panel. It is saved hashed, in your own folder, and used only by the Customize tab."

    def fill(self):
        return panel_ask_password()


# ================================================================ the web terminal (the Terminal card of the Links tab)
# ttyd runs a shell in the browser. It is its own service, as the lab's own user, and listens on a socket FILE (not a network port) that only
# that user can open. The only thing that talks to it is the control panel, which checks the login first and then passes the terminal
# through on the panel's own Tailscale address (port 1100). So the terminal is exactly as private as the panel: your tailnet only.
TERMINAL_UNIT = "/etc/systemd/system/homelab-terminal.service"
TERMINAL_SOCK = "/run/homelab-terminal/ttyd.sock"


def terminal_unit_text():
    """The systemd unit. It cannot be locked down like the panel's unit: a shell needs sudo to work, and sudo needs what a lock-down takes away."""
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
            rc, txt = act(["apt-get", "install", "-y", "-q", "ttyd"], env=apt_env(), timeout=900)
            if rc != 0 and not Opt.dry:
                raise Abort("The terminal program (ttyd) could not be installed: %s\n      Try it by hand: sudo apt-get install ttyd" % txt.strip()[-200:])
        changed = read_file(P(TERMINAL_UNIT)) != terminal_unit_text()
        if changed:
            write_file(P(TERMINAL_UNIT), terminal_unit_text(), 0o644)
        act(["systemctl", "daemon-reload"])
        act(["systemctl", "enable", "--now", "homelab-terminal"])
        if changed and not Opt.dry and run(["systemctl", "is-active", "homelab-terminal"])[1].strip() == "active":
            act(["systemctl", "restart", "homelab-terminal"])
