

# ================================================================ your scripts, schedule and login screen
SCRIPTS = [("drives", "/usr/local/sbin"), ("homelab-backup", "/usr/local/sbin"), ("homelab-update", "/usr/local/sbin"),
           ("homelab-restore-configs", "/usr/local/sbin"), ("homelab-sample", "/usr/local/sbin"),
           ("homelab-selftest", "/usr/local/sbin"), ("hdd-recover", "/usr/local/bin"), ("homelab", "/usr/local/bin"), ("homelab-check", "/usr/local/bin")]


def render_script(name):
    """A script from scripts/ ready to install (the user name filled in)."""
    text = read_file(repo_file("scripts", name))
    # the scripts look the lab's user up by themselves (the first normal user); the installed copy names this machine's user
    return text.replace("$(getent passwd 1000 | cut -d: -f1)", Ctx.user)


def installed_copy(name, where):
    """Path of the installed copy of a script, or None when it is not installed."""
    p = P(where + "/" + name)
    if os.path.exists(p):
        return p
    found = shutil.which(name)
    return found if found else None


@step
class ScriptsInstalled(Step):
    id, group, title = "scripts", "Scripts and schedule", "Helper commands installed (homelab, homelab-update, drives, backup, ...)"
    needs = ("packages",)

    def _wanted(self):
        items = [(n, d, render_script(n)) for n, d in SCRIPTS]
        me = repo_file("installer", "homelab-setup")
        items.append(("homelab-setup", "/usr/local/sbin", read_file(me)))
        return items

    def probe(self):
        for n, d, body in self._wanted():
            if not body:
                return "todo"
            p = installed_copy(n, d)
            if not p or read_file(p) != body:
                return "todo"
        return "done"

    def run(self):
        for n, d, body in self._wanted():
            if not body:
                raise Abort("The repository copy of %s is missing (looked in %s)." % (n, Ctx.repo))
            dst = P(d + "/" + n)
            if os.path.exists(dst) and read_file(dst) == body:
                continue
            write_file(dst, body, 0o755)


@step
class BackupConf(Step):
    id, group, title = "backup-conf", "Scripts and schedule", "Backup settings file (/etc/homelab-backup.conf)"
    needs = ("scripts",)

    def probe(self):
        path = P("/etc/homelab-backup.conf")
        if not os.path.exists(path):
            return "todo"
        # a file left by an earlier install can name ~/750GB_HDD, a folder this machine does not have
        m = re.search(r'DEST_FALLBACK="([^"]*)"', read_file(path))
        if m and "/750GB_HDD/" in m.group(1) and not os.path.isdir(P(Ctx.home + "/750GB_HDD")):
            return "todo"
        return "done"

    def run(self):
        write_file(P("/etc/homelab-backup.conf"), 'DEST_FALLBACK="%s/backup-interim"\n' % boot_share_dir(), 0o644)


CRON_LINES = [
    ("homelab-sample", "*/15 * * * * /usr/local/sbin/homelab-sample >/dev/null 2>&1"),
    ("homelab-update", "17 * * * * /usr/local/sbin/homelab-update auto >/dev/null 2>&1"),
    ("drives power", "@reboot sleep 60 && /usr/local/sbin/drives power >/dev/null 2>&1"),
    ("hdparm -B 254", '@reboot sleep 60 && /usr/sbin/hdparm -B 254 "/dev/$(lsblk -no pkname "$(findmnt -no SOURCE /boot/efi)")" >/dev/null 2>&1'),
]
CRON_PROGRESS = ("homelab-setup progress", "*/10 * * * * /usr/local/sbin/homelab-setup progress >/dev/null 2>&1")
CRON_BACKUP = ("homelab-backup", "0 6 * * * /usr/local/sbin/homelab-backup")


def crontab_text():
    """Root's crontab as text ('' when there is none)."""
    rc, txt = run(["crontab", "-l"])
    return txt if rc == 0 else ""


def crontab_active(txt):
    """The crontab without comments and blank lines."""
    return "\n".join(l for l in txt.splitlines() if l.strip() and not l.strip().startswith("#"))


def crontab_add(lines):
    """Add lines to root's crontab unless the same line is already active; the old crontab is saved first."""
    cur = crontab_text()
    if Opt.dry:
        for _, l in lines:
            out("      would add to root's crontab: %s" % l)
        return
    os.makedirs(SECRET_DIR, exist_ok=True)
    if cur.strip():
        write_file("%s/crontab.before-%s" % (SECRET_DIR, time.strftime("%Y%m%d-%H%M%S")), cur, 0o600)
    act_lines = crontab_active(cur)
    new = cur.rstrip("\n") + ("\n" if cur.strip() else "")
    for key, l in lines:
        if key not in act_lines:
            new += l + "\n"
    rc, txt = run(["crontab", "-"], input_text=new)
    if rc != 0:
        raise Abort("Could not save root's crontab: %s" % txt.strip()[-200:])


@step
class CronLines(Step):
    id, group, title = "cron", "Scripts and schedule", "Scheduled jobs in root's crontab (readings, update check, drive power)"
    needs = ("scripts",)

    def _lines(self):
        return CRON_LINES + ([] if Mode.existing else [CRON_PROGRESS])

    def probe(self):
        # the progress line is not required: it removes itself once setup is finished
        act_lines = crontab_active(crontab_text())
        return "done" if all(k in act_lines for k, _ in CRON_LINES) else "todo"

    def run(self):
        crontab_add(self._lines())


@step
class DataDrive(Step):
    id, group, title = "data-drive", "Your devices and drives", "A data drive is mounted at /mnt/storage"
    kind = "manual"
    optional = True

    def probe(self):
        return "done" if os.path.ismount(P("/mnt/storage")) or os.environ.get("HLS_MOUNTED") == "1" else "todo"

    def help(self):
        return ("/mnt/storage is currently a plain folder on the boot drive, which is fine for testing. To use a dedicated drive, connect it and run the drive tool. It asks before changing anything, and the installer itself never formats a drive:\n$ sudo drives\nThen turn on the daily backup:\n$ sudo homelab-setup refresh\nTo skip this step:\n$ sudo homelab-setup skip data-drive")


@step
class CronBackup(Step):
    id, group, title = "cron-backup", "Scripts and schedule", "Daily backup scheduled at 6:00"
    needs = ("scripts", "data-drive")

    def applies(self):
        # homelab-backup refuses to run unless /mnt/storage is a real drive, so a skipped drive means no backup job
        return not State.data["skip"].get("data-drive")

    def probe(self):
        return "done" if CRON_BACKUP[0] in crontab_active(crontab_text()) else "todo"

    def run(self):
        crontab_add([CRON_BACKUP])


LOGIN_BLOCK = """
# >>> homelab login display >>>
if [[ $- == *i* ]] && [ -t 1 ] && command -v homelab >/dev/null 2>&1; then
  timeout 20 homelab login
fi
# <<< homelab login display <<<
"""


@step
class LoginHook(Step):
    id, group, title = "login-hook", "Scripts and schedule", "The homelab screen shows when you open a terminal"
    needs = ("scripts",)

    def probe(self):
        txt = read_file(P(Ctx.home + "/.bashrc"))
        # an older block (without "homelab login" on its command line) is replaced: the new one remembers the screen for 2 minutes
        if "# >>> homelab login display >>>" not in txt:
            return "todo"
        # a server built by hand is only looked at, so its older block counts too
        return "done" if Mode.existing or "timeout 20 homelab login" in txt else "todo"

    def run(self):
        path = P(Ctx.home + "/.bashrc")
        cur = read_file(path)
        if not Opt.dry and cur:
            bak = path + ".bak-homelab-setup"          # the first copy of the file, kept once
            if not os.path.exists(bak):
                write_file(bak, cur, 0o644, (Ctx.uid, Ctx.gid))
        if "# >>> homelab login display >>>" in cur:
            new = re.sub(r"\n?# >>> homelab login display >>>.*?# <<< homelab login display <<<\n", LOGIN_BLOCK, cur, flags=re.S)
        else:
            new = cur.rstrip("\n") + "\n" + LOGIN_BLOCK
        write_file(path, new, 0o644, (Ctx.uid, Ctx.gid))


# ================================================================ things only you can do
EXPECTED_CONTAINERS = 16
WEATHER_DEFAULT = (40.7128, -74.0060)


def boot_id():
    """An id that changes at every boot."""
    return os.environ.get("HLS_BOOT_ID") or read_file("/proc/sys/kernel/random/boot_id").strip()


def chk_weather():
    """True when the weather widget has coordinates."""
    if State.data.get("weather_set"):
        return True          # a city was chosen at install and written into widgets.yaml
    txt = read_file(P(Ctx.home + "/homepage-config/widgets.yaml"))
    m = re.search(r"openmeteo:(.*?)(?:\n- |\Z)", txt, re.S)
    if not m:
        return False
    lat = re.search(r"latitude:\s*(-?[0-9.]+)", m.group(1))
    lon = re.search(r"longitude:\s*(-?[0-9.]+)", m.group(1))
    if not (lat and lon):
        return False
    try:
        return (float(lat.group(1)), float(lon.group(1))) != WEATHER_DEFAULT
    except ValueError:
        return False


def chk_blocklists():
    """AdGuard Home starts with at most two lists on; three or more enabled means you added some."""
    on, inside = 0, False
    for line in adguard_yaml().split("\n"):
        if re.match(r"^filters:\s*$", line):
            inside = True
            continue
        if inside and re.match(r"^\S", line):
            break
        if inside and re.match(r"^\s+(-\s+)?enabled:\s*true\s*$", line):
            on += 1
    return on >= 3


def chk_devices_dns():
    """AdGuard Home has answered DNS questions from a device that is not this machine or a Docker network."""
    user, pw = hp_get("adguard-card", "username"), hp_get("adguard-card", "password")
    if is_placeholder(user) or is_placeholder(pw):
        return False
    st, js, _ = http("GET", url("adguard", "/control/stats"), headers=basic(user, pw), timeout=15)
    if st != 200 or not isinstance(js, dict):
        return False
    docker_net = ipaddress.ip_network("172.16.0.0/12")
    try:
        lan_in_docker = ipaddress.ip_address(Ctx.lan) in docker_net
    except ValueError:
        lan_in_docker = False
    for item in js.get("top_clients") or []:
        for ip in (item.keys() if isinstance(item, dict) else []):
            try:
                a = ipaddress.ip_address(ip)
            except ValueError:
                return True
            if a.is_loopback or a.is_link_local or ip == Ctx.lan:
                continue
            if a in docker_net and not lan_in_docker:
                continue
            return True
    return False


def chk_speedtest():
    """True when Speedtest Tracker's widget has a real key."""
    key = hp_get("speedtest-card", "key")
    if is_placeholder(key):
        return False
    st, _, _ = http("GET", url("speedtest", "/api/v1/results/latest"),
                    headers={"Authorization": "Bearer " + key, "Accept": "application/json"}, timeout=15)
    return st == 200


def chk_reboot():
    """All containers are up and the machine has restarted since the lab was first seen running."""
    n = len([l for l in run(["docker", "ps", "-q"])[1].split("\n") if l.strip()])
    if n < EXPECTED_CONTAINERS:
        return False
    seen, cur = State.data.get("boot_seen"), boot_id()
    if not seen:
        State.data["boot_seen"] = cur
        State.save()
        return False
    return seen != cur


class AckStep(Step):
    kind = "ack"
    group = "Your devices and drives"

    def __init__(self, sid, title, text, optional=False, needs=(), auto=None):
        self.id, self.title, self.text, self.optional, self.needs = sid, title, text, optional, tuple(needs)
        self.auto = auto

    def applies(self):
        return not Mode.existing

    def probe(self):
        if not self.auto:
            return "todo"
        if State.data.setdefault("autodone", {}).get(self.id):
            return "done"
        if self.auto():
            State.data["autodone"][self.id] = time.strftime("%F %T")
            State.save()
            return "done"
        return "todo"

    def detail(self):
        return "detected automatically" if self.auto else ""

    def help(self):
        if self.auto:
            tail = ("This step is detected automatically (a check runs about once an hour and each time "
                    "`sudo homelab-setup refresh` runs). To mark it as done manually:")
        else:
            tail = "When it is done, run:"
        text = "%s\n%s\n$ sudo homelab-setup done %s" % (self.text, tail, self.id)
        if self.optional:
            text += "\nTo skip it:\n$ sudo homelab-setup skip %s" % self.id
        return text


def _register_acks():
    """Create the checklist steps that only a person can confirm."""
    items = [
        AckStep("secrets-saved", "Generated passwords copied into your password manager",
                "Show the generated passwords and keys, copy them into your password manager, and store the admin password you chose there as well. They are kept in /root/.homelab-setup/secrets.env (root only). The step is marked done once this command has been run; the installer cannot check that the passwords were saved.\n$ sudo homelab-setup secrets",
                auto=lambda: bool(State.data.get("secrets_shown"))),
        AckStep("devices-dns", "Your devices use AdGuard Home as their DNS server",
                "On each device, set DNS manually: preferred = this machine's LAN address (shown by `homelab`), alternate = 8.8.8.8 (or leave it empty for strict filtering). Windows: Settings > Network > DNS. iPhone: Wi-Fi > (i) > Configure DNS.",
                needs=("adguard-setup",), auto=chk_devices_dns),
        AckStep("speedtest-first", "Speedtest Tracker has run its first speed test",
                "Open Speedtest Tracker (port 8088), log in with your email address and the admin password, and click Speedtest. The Homepage card fills in afterwards. If the login fails, the application's default login is admin@example.com / password: log in with it and change it immediately.",
                needs=("w-speedtest",), auto=chk_speedtest),
        AckStep("weather", "Homepage weather location set",
                "The weather city is asked during install. If it was not set (the city lookup was unavailable), edit ~/homepage-config/widgets.yaml and change latitude and longitude under openmeteo "
                "(the default is New York).\n$ nano ~/homepage-config/widgets.yaml",
                optional=True, needs=("homepage-files",), auto=chk_weather),
        AckStep("reboot-test", "Rebooted once and everything came back",
                "Reboot once and confirm that everything comes back: after about two minutes, log in again. The login screen should show all containers running, and `docker ps` should list them.\n$ sudo reboot", needs=("stack-homepage",), auto=chk_reboot),
    ]
    for s in items:
        register(s)


BLOCKLISTS = [
    ("HaGeZi's Pro Blocklist", "https://adguardteam.github.io/HostlistsRegistry/assets/filter_48.txt"),
    ("Peter Lowe's Blocklist", "https://adguardteam.github.io/HostlistsRegistry/assets/filter_3.txt"),
]


@step
class Blocklists(Step):
    id, group, title = "blocklists", "Logins and keys", "AdGuard Home blocklists added (HaGeZi Pro, Peter Lowe's)"
    needs = ("adguard-setup",)
    optional = True

    def applies(self):
        return not Mode.existing

    def probe(self):
        return "done" if chk_blocklists() else "todo"

    def detail(self):
        return "three or more lists on"

    def help(self):
        return ("In AdGuard Home go to Filters > DNS blocklists > Add blocklist > Choose from the list. Common choices: AdGuard DNS filter, AdAway, HaGeZi Pro, OISD Big, Peter Lowe's and Steven Black's. Then run:\n"
                "$ sudo homelab-setup done blocklists\nTo skip it:\n$ sudo homelab-setup skip blocklists")

    def run(self):
        if Opt.dry:
            out("      would add %s through AdGuard Home's API" % " and ".join(n for n, _ in BLOCKLISTS))
            return
        need_password("to add the blocklists in AdGuard Home")
        st, js, _ = http("GET", url("adguard", "/control/filtering/status"), headers=adguard_auth(), timeout=30)
        if st != 200 or not isinstance(js, dict):
            raise Abort("AdGuard Home did not return its blocklists (HTTP %s)." % st)
        have_lists = {f.get("url"): f for f in (js.get("filters") or []) if isinstance(f, dict)}
        for name, link in BLOCKLISTS:
            cur = have_lists.get(link)
            if cur is None:
                st, js2, _ = http("POST", url("adguard", "/control/filtering/add_url"), headers=adguard_auth(), timeout=180,
                                  body={"name": name, "url": link, "whitelist": False})
                if st != 200:
                    raise Abort("AdGuard Home refused the blocklist '%s' (HTTP %s): %s" % (name, st, str(js2)[:200]))
            elif not cur.get("enabled"):
                st, js2, _ = http("POST", url("adguard", "/control/filtering/set_url"), headers=adguard_auth(), timeout=180,
                                  body={"url": link, "whitelist": False, "data": {"name": name, "url": link, "enabled": True}})
                if st != 200:
                    raise Abort("AdGuard Home refused to turn on the blocklist '%s' (HTTP %s)." % (name, st))
        wait_for(chk_blocklists, "AdGuard Home to save the blocklists", 60)


_register_acks()
