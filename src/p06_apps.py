

# ================================================================ restore from a backup (only when one is found and you said yes)
def need_email():
    """The email address given at the start, or a message saying how to give it (Immich and Beszel need one)."""
    if not Ctx.email:
        raise Abort("An email address is required. Run `sudo homelab-setup install` and answer the questions.")


def restore_choice():
    """What the person chose to restore from a backup (saved in the state file)."""
    return State.data.get("restore", {})


def find_backups():
    """Folders that look like a backup of an earlier lab (they hold main/ and boot-configs/)."""
    cands = []
    if Opt.backup:
        cands.append(Opt.backup)
    else:
        cands += [P("/mnt/backup"), P(Ctx.home + "/boot-drive-files/backup-interim"), P(Ctx.home + "/750GB_HDD/backup-interim")]
        for pat in ("/media/*/*", "/media/*/*/*", "/mnt/*", "/mnt/*/*", "/mnt/disks/*"):
            cands += glob.glob(P(pat))
    found = []
    for c in cands:
        if os.path.isdir(c + "/main") and os.path.isdir(c + "/boot-configs") and c not in found:
            found.append(c)
    return found


def dir_size_gb(path):
    """Size of a folder in gigabytes."""
    rc, txt = run(["du", "-sb", path], timeout=300)
    try:
        return int(txt.split()[0]) / 1073741824.0
    except (ValueError, IndexError):
        return 0.0


def ask_restore_plan():
    """Install-time question: restore from a backup? Returns nothing; saves the choice."""
    if "restore" in State.data:
        return
    old = fstab_pool_drives()
    if old:
        out("")
        warn("This machine already has drive(s) set up for the pools, left by an earlier install (%s). The installer never changes drives, "
             "so they stay in the pool and mount at every boot. To start with no drive in a pool, run `sudo drives release` once the install is done "
             "(the files on the drives are not touched), then choose the drives you want with `sudo drives`." % ", ".join(sorted(old)))
    State.data["restore"] = {"path": "", "configs": False, "data": False}
    if Opt.no_restore:
        State.save()
        return
    found = find_backups()
    if not found:
        out("")
        say("No backup found: every service will start empty. To restore from a backup, connect it (or pass `--backup FOLDER`) and run `sudo homelab-setup install` again before the services are deployed.")
        State.save()
        return
    path = found[0]
    out("")
    say("Backup found: %s" % path.replace(ROOT, ""))
    if len(found) > 1:
        say("(Other candidates: %s)" % ", ".join(f.replace(ROOT, "") for f in found[1:]))
    users = os.listdir(path + "/boot-configs/home") if os.path.isdir(path + "/boot-configs/home") else []
    if users and Ctx.user not in users:
        warn("The backup belongs to the user %s, but this machine's user is %s. Restoring would write into /home/%s, so the saved settings are not restored. Create a user named %s to restore them."
             % (", ".join(users), Ctx.user, users[0], users[0]))
        cfg = False
    else:
        cfg = yesno("Restore the saved settings from it (Homepage, Nextcloud app files, AdGuard Home)?", True)
    size = dir_size_gb(path + "/main")
    data = yesno("Copy your photos and files back (about %.0f GB) before the services start?" % size, True)
    State.data["restore"] = {"path": path, "configs": cfg, "data": data}
    State.save()


@step
class RestoreConfigs(Step):
    id, group, title = "restore-configs", "Platform", "Saved settings restored from your backup"
    needs = ("folders",)

    def applies(self):
        return bool(restore_choice().get("configs"))

    def probe(self):
        return "done" if State.ran("restore-configs") else "todo"

    def run(self):
        path = restore_choice()["path"]
        tool = repo_file("scripts", "homelab-restore-configs")
        if not os.path.exists(tool):
            raise Abort("homelab-restore-configs is missing from the repository copy.")
        if Opt.dry:
            out("      would run the safe restore tool on %s (it shows a preview and asks you to type RESTORE)" % path)
            return
        env = dict(os.environ)
        if ROOT:
            env["HRC_ROOT"] = ROOT                      # tests only: restore into the fake root
        with Live.pause():
            rc = subprocess.run(["bash", tool, path], env=env).returncode
        if rc != 0:
            raise Abort("The restore tool stopped (code %s). Nothing was deleted. Run `sudo homelab-setup refresh` to try again." % rc)
        State.mark("restore-configs")


@step
class RestoreData(Step):
    id, group, title = "restore-data", "Platform", "Photos and files copied back from your backup"
    needs = ("folders", "restore-configs")

    def applies(self):
        return bool(restore_choice().get("data"))

    def probe(self):
        return "done" if State.ran("restore-data") else "todo"

    def run(self):
        path = restore_choice()["path"] + "/main/"
        dest = P("/mnt/storage/")
        for sub in ("immich", "nextcloud"):
            d = dest + sub
            if os.path.isdir(d) and any(os.scandir(d)):
                raise Abort("%s already contains files and will not be overwritten. Move them away or skip the restore." % d.replace(ROOT, ""))
        size = dir_size_gb(path)
        free = shutil.disk_usage(dest).free / 1073741824.0
        if free < size + 5:
            raise Abort("Not enough space: the backup is %.0f GB and only %.0f GB is free at /mnt/storage." % (size, free))
        if Opt.dry:
            out("      would copy %.0f GB from %s to /mnt/storage with rsync" % (size, path))
            return
        out("      copying %.0f GB (this can take a long time; you can leave it running) ..." % size)
        with Live.pause():
            rc = subprocess.run(["rsync", "-aH", "--numeric-ids", "--info=progress2", "--exclude=/lost+found", path, dest]).returncode
        if rc not in (0, 24):
            raise Abort("rsync stopped with code %s. Run `sudo homelab-setup refresh` to continue where it stopped." % rc)
        State.mark("restore-data")


def immich_restored():
    """True when data was restored from a backup and Immich's own database dumps are present."""
    return bool(restore_choice().get("data")) and bool(glob.glob(P("/mnt/storage/immich/backups/*")))


# ================================================================ Homepage config files
HP_FILES = ["services.yaml", "settings.yaml", "widgets.yaml", "bookmarks.yaml", "custom.css"]


def widgets_for_machine(body):
    """widgets.yaml for a new machine: its first resources pill carries this machine's name (the repository file calls it
    "Server"), and the weather city chosen at the start is put in."""
    body = re.sub(r"(- resources:\n\s+label:) Server\b", lambda m: "%s %s" % (m.group(1), Ctx.hostname), body, count=1)
    w = State.data["answers"].get("weather")
    if w:
        new = weather_apply(body, w)
        if new is not None:
            body = new
            State.data["weather_set"] = w["name"]
            State.save()
    return body


@step
class HomepageFiles(Step):
    id, group, title = "homepage-files", "Homepage", "Homepage config files in place for this machine"
    needs = ("folders", "tailscale-login", "restore-configs")

    def probe(self):
        if not all(os.path.exists(hp_path(f)) for f in HP_FILES):
            return "todo"
        txt = read_file(hp_path())
        if PH_LAN in txt or PH_FQDN in txt:
            return "todo"
        if OLD_LAN and OLD_LAN in txt and OLD_LAN != Ctx.lan:
            return "todo"
        if OLD_FQDN and OLD_FQDN in txt and OLD_FQDN != Ctx.fqdn:
            return "todo"
        return "done"

    def run(self):
        for f in HP_FILES:
            dst = hp_path(f)
            if not os.path.exists(dst):
                body = subst(read_file(repo_file("homepage-config", f)))
                if not body:
                    raise Abort("The repository file homepage-config/%s is missing." % f)
                if f == "services.yaml":
                    body = hp_strip_widgets(body)
                    if not adguard_wanted():
                        body = hp_remove_card(body, "adguard-card")
                if f == "widgets.yaml":
                    body = widgets_for_machine(body)
                write_file(dst, body, 0o644, (Ctx.uid, Ctx.gid))
            elif f in ("services.yaml", "bookmarks.yaml"):
                old = read_file(dst)
                new = subst(old)
                if new != old:
                    write_file(dst, new, 0o644, (Ctx.uid, Ctx.gid))


@step
class HomepageTabs(Step):
    id, group, title = "homepage-tabs", "Homepage", "Homepage tabs (Home, Links, Stats), group icons, bookmark cards, the STATS cards and their styles"
    needs = ("homepage-files", "scripts")

    def applies(self):
        return not Mode.existing and os.path.exists(hp_path("settings.yaml")) and os.path.exists(hp_path("custom.css")) and bool(read_file(repo_file("homepage-config", "settings.yaml")))

    def wanted(self):
        """(new settings.yaml, new custom.css, groups now known, new custom.js, new services.yaml) for this machine. The tabs are offered
        once: after that, taking the layout: block out of settings.yaml is respected. A group of this machine that no tab knows yet is put
        on one. The STATS groups are added to services.yaml (also offered once) when the tabs are on."""
        sett, css = read_file(hp_path("settings.yaml")), read_file(hp_path("custom.css"))
        if not State.ran("homepage-tabs"):
            sett = settings_with_layout(sett, read_file(repo_file("homepage-config", "settings.yaml")))
        svc = read_file(hp_path("services.yaml"))
        if re.search(r"(?m)^layout:", sett):
            shipped_svc = subst(read_file(repo_file("homepage-config", "services.yaml")))
            if not State.ran("homepage-stats") or STATS_BEGIN in svc:
                svc = services_stats_block(svc, shipped_svc)
            if not State.ran("homepage-calendar") or CAL_BEGIN in svc:
                svc = services_calendar_block(svc, shipped_svc)
        sett = layout_renamed(sett)
        sett, seen = layout_complete(sett, group_names(svc), group_names(read_file(hp_path("bookmarks.yaml"))), State.data.get("layout_seen", []))
        if re.search(r"(?m)^layout:", sett):
            sett, seen = layout_storage_wide(sett, seen)
            sett, seen = layout_music_wide(sett, seen)
        sett, seen = settings_quicklaunch(sett, seen)
        new_css = css_tabs_block(css, read_file(repo_file("homepage-config", "custom.css")))
        new_js = js_groups_block(read_file(hp_path("custom.js")), read_file(repo_file("homepage-config", "custom.js")))
        return sett, new_css, seen, new_js, svc

    def remember(self, seen):
        if seen != State.data.get("layout_seen", []):
            State.data["layout_seen"] = seen
            State.save()

    def probe(self):
        sett, css, seen, js, svc = self.wanted()
        if (sett != read_file(hp_path("settings.yaml")) or css != read_file(hp_path("custom.css")) or js != read_file(hp_path("custom.js"))
                or svc != read_file(hp_path("services.yaml"))):
            return "todo"
        if not Opt.dry:
            self.remember(seen)                  # already in place (a new machine): a later removal of a group or of the tabs is respected
            for k in ("homepage-tabs", "homepage-stats", "homepage-calendar"):
                if not State.ran(k):
                    State.mark(k)
        return "done"

    def run(self):
        old_sett, old_css, old_js, old_svc = (read_file(hp_path(n)) for n in ("settings.yaml", "custom.css", "custom.js", "services.yaml"))
        sett, css, seen, js, svc = self.wanted()
        own = (Ctx.uid, Ctx.gid)
        if Opt.dry:
            out("      would add the tabs (Home, Links, Stats), the group icons, the bookmark cards, the STATS cards and their styles to the Homepage files")
            return
        for name, old, new in (("settings.yaml", old_sett, sett), ("custom.css", old_css, css), ("custom.js", old_js, js), ("services.yaml", old_svc, svc)):
            if new == old:
                continue
            if old and not os.path.exists(hp_path(name) + ".before-tabs"):          # the first copy is the one worth keeping
                write_file(hp_path(name) + ".before-tabs", old, 0o644, own)
            write_file(hp_path(name), new, 0o644, own)
        self.remember(seen)
        State.mark("homepage-tabs")
        State.mark("homepage-stats")
        State.mark("homepage-calendar")
        stats_file = hp_path("images/stats.json")
        if not FAKE and not os.path.exists(stats_file) and os.path.exists(P("/usr/local/sbin/homelab-stats")):
            # Homepage only serves a file that was there when it started, so the first stats.json is made now, before the restart below
            os.makedirs(os.path.dirname(stats_file), exist_ok=True)
            run_as_root_stats(stats_file)
        if CAL_BEGIN in svc and os.path.exists(P("/usr/local/bin/homelab-calendar")):
            # the same for the calendar files: they must exist before Homepage starts
            os.makedirs(hp_path("images"), exist_ok=True)
            run_calendar_build()
        if not FAKE and "homepage" in containers_all():
            act(["docker", "restart", "homepage"], timeout=120)
        out("      Reload the dashboard (Ctrl+Shift+R). The old files are saved as settings.yaml.before-tabs, custom.css.before-tabs, custom.js.before-tabs and services.yaml.before-tabs")
        if STATS_BEGIN in svc:
            out("      The Stats tab fills in within 15 minutes (the folder sizes take a little longer). To fill it in now:  sudo homelab-stats")
        if CAL_BEGIN in svc:
            out("      The Calendar is at the bottom of the Home tab. Add your own events with:  homelab event add 2026-12-25 \"Family dinner\"")


def fetch_picture(addr):
    """The bytes of a picture from the web (None when it cannot be had or is not a picture). FAKE mode: the file named in HLS_FAKE_BG_FILE."""
    if FAKE:
        f = os.environ.get("HLS_FAKE_BG_FILE", "")
        data = open(f, "rb").read() if f and os.path.isfile(f) else None
    else:
        try:
            req = urllib.request.Request(addr, headers={"User-Agent": "homelab-setup"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read(30 * 1024 * 1024)
        except (urllib.error.URLError, OSError, ValueError):
            return None
    return data if data and (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")) else None


@step
class HomepageBackground(Step):
    id, group, title = "homepage-background", "Homepage", "The dashboard's background picture is saved on this server (loads fast, works offline)"
    needs = ("homepage-tabs",)

    def applies(self):
        return not Mode.existing and os.path.exists(hp_path("settings.yaml"))

    def probe(self):
        cur = background_image(read_file(hp_path("settings.yaml")))
        tried = time.time() - State.data.get("background_tried", 0) < 7 * 86400          # a failed attempt is repeated a week later, not on every run
        return "done" if State.ran(self.id) or tried or not re.match(r"https?://", cur) else "todo"

    def detail(self):
        return background_image(read_file(hp_path("settings.yaml")))[:60]

    def run(self):
        sett = read_file(hp_path("settings.yaml"))
        cur = background_image(sett)
        if Opt.dry:
            out("      would download the background picture into %s and use it from there" % hp_path("images"))
            return
        data = fetch_picture(cur)
        if data is None:
            warn("Could not download the background picture (%s). It stays as it is; an upgrade a week from now tries again." % cur[:70])
            State.data["background_tried"] = int(time.time())
            State.save()
            return
        ext = ".png" if data[:4] == b"\x89PNG" else ".webp" if data[:4] == b"RIFF" else ".jpg"
        name = "background" + ext
        os.makedirs(hp_path("images"), exist_ok=True)
        path = hp_path("images/" + name)
        with open(path, "wb") as f:
            f.write(data)
        os.chmod(path, 0o644)
        chown(path, Ctx.uid, Ctx.gid)
        if not os.path.exists(hp_path("settings.yaml") + ".before-background"):
            write_file(hp_path("settings.yaml") + ".before-background", sett, 0o644, (Ctx.uid, Ctx.gid))
        write_file(hp_path("settings.yaml"), settings_with_background(sett, "/images/" + name), 0o644, (Ctx.uid, Ctx.gid))
        State.mark(self.id)
        if not FAKE and "homepage" in containers_all():
            act(["docker", "restart", "homepage"], timeout=120)       # Homepage only serves a new picture after a restart
        out("      The background is now %s in the images folder (the old settings.yaml is kept as settings.yaml.before-background). "
            "To use another picture later:  homelab theme background URL-or-FILE" % name)


# ================================================================ Navidrome (plays the songs Downtify saved)
class NavidromeStack(StackStep):
    """Only on a machine that has a music folder (the folder Downtify saves into). A hand-built server is only looked at."""

    def applies(self):
        return not Mode.existing and bool(music_folder())

    def detail(self):
        return "music folder %s" % music_folder()

    def run(self):
        folder = Ctx.home + "/navidrome"
        if not Opt.dry:
            os.makedirs(P(folder), exist_ok=True)
            chown(P(folder), Ctx.uid, Ctx.gid)
        StackStep.run(self)


register(NavidromeStack("navidrome", ("portainer-env", "folders"), "Navidrome music server (plays the songs Downtify saved)"))


@step
class NavidromeCard(Step):
    id, group = "navidrome-card", "Homepage"
    title = "Navidrome login and its dashboard card with live numbers (songs, albums, artists)"
    needs = ("stack-navidrome", "homepage-files")

    def applies(self):
        return BY_ID["stack-navidrome"].applies()

    def probe(self):
        return "done" if card_widget_type(read_file(hp_path("services.yaml")), "navidrome-card") == "navidrome" else "todo"

    def run(self):
        if Opt.dry:
            out("      would create the Navidrome login (%s), then add its card and the live numbers to the dashboard" % Ctx.admin)
            return
        pw = need_password("to create the Navidrome login")
        if not wait_for(lambda: http("GET", url("navidrome", "/"), raw=True, timeout=10)[0] == 200, "Navidrome to answer", 120):
            raise Abort("Navidrome does not answer on port %d. Look at its log:  docker logs navidrome" % PORTS["navidrome"])
        creds = {"username": Ctx.admin, "password": pw}
        st, _, _ = http("POST", url("navidrome", "/auth/createAdmin"), body=creds, timeout=30)
        if st != 200:                                    # 403: it has a login already. Is it ours?
            st, _, _ = http("POST", url("navidrome", "/auth/login"), body=creds, timeout=30)
            if st != 200:
                warn("Navidrome already has a login that is not %s with the shared admin password, so the dashboard cannot show its numbers. "
                     "Open it, add that user or change its password, then run:  sudo homelab-setup upgrade" % Ctx.admin)
                return
        if not FAKE and os.path.exists(P("/usr/local/sbin/homelab-cards")):
            run([P("/usr/local/sbin/homelab-cards"), "sync"], timeout=120)            # makes the card (and its Tailscale address) now
        old = read_file(hp_path("services.yaml"))
        new = services_with_widget(old, "navidrome-card", navidrome_widget(Ctx.lan or svc_host(), Ctx.admin, pw, rand_alnum(12)))
        if new == old:
            warn("The dashboard has no Navidrome card yet. homelab-cards makes it within 5 minutes; run `sudo homelab-setup upgrade` after that "
                 "to add its live numbers.")
            return
        if not os.path.exists(hp_path("services.yaml") + ".before-navidrome"):
            write_file(hp_path("services.yaml") + ".before-navidrome", old, 0o644, (Ctx.uid, Ctx.gid))
        write_file(hp_path("services.yaml"), new, 0o644, (Ctx.uid, Ctx.gid))
        out("      Navidrome is at %s. Log in as %s with the shared admin password; the dashboard card shows its numbers." % (url("navidrome"), Ctx.admin))


def run_calendar_build():
    """Make the calendar files (holidays, observances, your events) in the images folder of Homepage."""
    run([P("/usr/local/bin/homelab-calendar"), "build"], env=dict(os.environ, HP_DIR=P(hp_dir())), timeout=60)


def run_as_root_stats(stats_file):
    """Make the first stats.json (without counting folder sizes, which takes minutes)."""
    run([P("/usr/local/sbin/homelab-stats"), "quick"], env=dict(os.environ, HOMELAB_STATS_OUT=stats_file), timeout=180)


# ================================================================ AdGuard Home
def adguard_yaml():
    """Contents of AdGuard Home's settings file."""
    return read_file(P("/opt/adguard-docker/conf/AdGuardHome.yaml"))


def adguard_auth():
    """Basic-authentication header for AdGuard Home's API."""
    pw = Runtime.password or ""
    tok = base64.b64encode(("%s:%s" % (Ctx.admin, pw)).encode()).decode()
    return {"Authorization": "Basic " + tok}


@step
class AdGuardSetup(Step):
    id, group, title = "adguard-setup", "Logins and keys", "AdGuard Home first-run setup done (admin account, web port 3000, DNS port 53)"
    needs = ("stack-adguard",)

    def applies(self):
        return adguard_wanted()

    def probe(self):
        return "done" if re.search(r"^users:\s*\n\s*-\s*name:", adguard_yaml(), re.M) else "todo"

    def run(self):
        pw = need_password("to create the AdGuard Home admin account") if not Opt.dry else None
        if Opt.dry:
            out("      would send the AdGuard Home install settings (web 3000, DNS 53, user %s)" % Ctx.admin)
            return
        st, js, _ = http("POST", url("adguard", "/control/install/configure"),
                         body={"web": {"ip": "0.0.0.0", "port": 3000}, "dns": {"ip": "0.0.0.0", "port": 53},
                               "username": Ctx.admin, "password": pw, "language": "en"}, timeout=60)
        if st == 422:
            raise Abort("AdGuard Home rejected the password as too weak. Use a longer one.")
        if st not in (200, 201):
            raise Abort("AdGuard Home refused the setup (HTTP %s): %s" % (st, str(js)[:200]))
        wait_for(lambda: http("GET", url("adguard", "/control/status"), headers=adguard_auth(), timeout=10)[0] == 200,
                 "AdGuard Home to restart with the new settings", 90)


DNS_UP = ["https://dns.quad9.net/dns-query", "https://cloudflare-dns.com/dns-query", "https://dns.google/dns-query"]
DNS_BOOT = ["9.9.9.10", "149.112.112.10", "2620:fe::10", "2620:fe::fe:10"]


@step
class AdGuardDns(Step):
    id, group, title = "adguard-dns", "Logins and keys", "AdGuard Home upstream DNS set (Quad9, Cloudflare, Google over HTTPS)"
    needs = ("adguard-setup",)
    optional = True

    def applies(self):
        return adguard_wanted()

    def probe(self):
        return "done" if "dns.quad9.net" in adguard_yaml() else "todo"

    def help(self):
        return ("In AdGuard Home go to Settings > DNS settings. Upstream DNS servers: %s. Bootstrap: %s. Enable parallel requests and DNSSEC. Then run:\n$ sudo homelab-setup done adguard-dns" % (", ".join(DNS_UP), ", ".join(DNS_BOOT)))

    def run(self):
        if Opt.dry:
            out("      would set AdGuard Home's upstream and bootstrap DNS")
            return
        need_password("to change AdGuard Home's DNS settings")
        st, js, _ = http("POST", url("adguard", "/control/dns_config"), headers=adguard_auth(), timeout=30,
                         body={"upstream_dns": DNS_UP, "bootstrap_dns": DNS_BOOT, "upstream_mode": "load_balance",
                               "dnssec_enabled": True, "cache_enabled": True, "cache_size": 4194304, "ratelimit": 20})
        if st != 200:
            raise Abort("AdGuard Home refused the DNS settings (HTTP %s)." % st)


# ================================================================ Immich
def immich_initialized():
    """True when Immich has finished its first-run setup."""
    st, js, _ = http("GET", url("immich", "/api/server/config"), timeout=10)
    return st == 200 and isinstance(js, dict) and bool(js.get("isInitialized"))


@step
class ImmichAdmin(Step):
    id, group, title = "immich-admin", "Logins and keys", "Immich admin account created"
    needs = ("stack-immich",)

    def probe(self):
        return "done" if immich_initialized() else "todo"

    def run(self):
        if immich_restored():
            raise Abort("The backup contains Immich database dumps, so no new admin account is created (it would block the restore). Open %s, choose 'Restore from backup' on the first screen and pick the newest dump. Then run `sudo homelab-setup refresh`." % url("immich"))
        need_email()
        if Opt.dry:
            out("      would create the Immich admin %s with the email address entered at install" % Ctx.admin)
            return
        if not docker_answers():
            raise Abort(DOCKER_DOWN)
        # Right after a reboot Immich needs a few minutes to start. Until it answers, the check above says "not set up"
        # even when the account exists, so wait first and look again before asking for a password.
        wait_for(lambda: http("GET", url("immich", "/api/server/ping"), timeout=8)[0] == 200, "Immich to answer", 300)
        if immich_initialized():
            return
        pw = need_password("to create the Immich admin account")
        st, js, _ = http("POST", url("immich", "/api/auth/admin-sign-up"),
                         body={"email": Ctx.email, "name": Ctx.admin, "password": pw}, timeout=60)
        if st not in (200, 201):
            raise Abort("Immich refused the admin account (HTTP %s): %s" % (st, str(js)[:200]))


# ================================================================ Nextcloud
def nc_installed():
    """True when Nextcloud has finished installing itself."""
    st, js, _ = http("GET", url("nextcloud", "/status.php"), timeout=10)
    return st == 200 and isinstance(js, dict) and js.get("installed") is True


FORCED_NC_KEYS = ("overwritehost", "overwriteprotocol")


def occ(*args):
    """Run Nextcloud's `occ` command inside its container."""
    return docker("exec", "-u", "www-data", "nextcloud", "php", "occ", *args, timeout=300)


def nc_system_config():
    """Nextcloud's whole system config as a dict, from one call (secret values are hidden by occ itself), or None when it cannot be read."""
    rc, txt = occ("config:list", "system")
    if rc != 0:
        return None
    try:
        data = json.loads(txt[txt.index("{"):])
        cfg = data.get("system")
        return cfg if isinstance(cfg, dict) else None
    except ValueError:
        return None


@step
class NextcloudReady(Step):
    id, group, title = "nextcloud-ready", "Logins and keys", "Nextcloud finished its first install"
    needs = ("stack-nextcloud",)

    def probe(self):
        return "done" if nc_installed() else "todo"

    def run(self):
        if Opt.dry:
            out("      would wait (2 to 15 minutes) for Nextcloud's first install to finish")
            return
        wait_for(nc_installed, "Nextcloud's first install (2 to 15 minutes)", 1500, every=10)


@step
class NextcloudConfig(Step):
    id, group, title = "nextcloud-config", "Logins and keys", "Nextcloud trusts this address and local servers (for Immich)"
    needs = ("nextcloud-ready",)

    def probe(self):
        cfg = nc_system_config()
        if cfg is not None:   # one call to Nextcloud answers all of it (each call into the container takes about 0.4 s)
            allow = str(cfg.get("allow_local_remote_servers", "")).lower()
            doms = "\n".join(str(d) for d in (cfg.get("trusted_domains") or []))
            forced = [k for k in FORCED_NC_KEYS if k in cfg]
            return "done" if "true" in allow and Ctx.fqdn in doms and Ctx.lan in doms and not forced else "todo"
        rc, txt = occ("config:system:get", "allow_local_remote_servers")
        rc2, doms = occ("config:system:get", "trusted_domains")
        forced = [k for k in FORCED_NC_KEYS if occ("config:system:get", k)[0] == 0]
        return "done" if rc == 0 and "true" in txt.lower() and Ctx.fqdn in doms and Ctx.lan in doms and not forced else "todo"

    def run(self):
        if Opt.dry:
            out("      would set trusted domains and allow_local_remote_servers in Nextcloud, and remove a forced address if one is saved")
            return
        for k in FORCED_NC_KEYS:   # a forced address would send every local request to the Tailscale address
            if occ("config:system:get", k)[0] == 0:
                occ("config:system:delete", k)
        for args in (["config:system:set", "allow_local_remote_servers", "--value=true", "--type=boolean"],
                     ["config:system:set", "trusted_domains", "1", "--value=" + Ctx.lan],
                     ["config:system:set", "trusted_domains", "2", "--value=" + Ctx.fqdn]):
            rc, txt = occ(*args)
            if rc != 0:
                raise Abort("occ %s failed: %s" % (args[0], txt.strip()[-200:]))


@step
class NextcloudRestoreDb(Step):
    id, group, title = "nextcloud-restore-db", "Logins and keys", "Nextcloud database loaded from your backup"
    needs = ("stack-nextcloud",)

    def applies(self):
        return bool(restore_choice().get("data"))

    def probe(self):
        return "done" if State.ran("nextcloud-restore-db") else "todo"

    def run(self):
        dumps = sorted(glob.glob(restore_choice()["path"] + "/db-dumps/nextcloud-*.sql.gz"))
        if not dumps:
            State.mark("nextcloud-restore-db")
            return
        dump = dumps[-1]
        if Opt.dry:
            out("      would load %s into the new Nextcloud database" % dump)
            return
        if not typed("RESTORE", "Type RESTORE to replace the new, empty Nextcloud database with %s" % os.path.basename(dump)):
            raise Abort("Not confirmed. Run `sudo homelab-setup refresh` when you want to load the dump.")
        docker("stop", "nextcloud", "nextcloud_cron")
        psql = ["exec", "-i", "nextcloud_db", "psql", "-U", "nextcloud", "-v", "ON_ERROR_STOP=1"]
        run(["docker"] + psql + ["-d", "postgres", "-c", "DROP DATABASE IF EXISTS nextcloud"], check=True)
        run(["docker"] + psql + ["-d", "postgres", "-c", "CREATE DATABASE nextcloud OWNER nextcloud"], check=True)
        with gzip.open(dump, "rt") as f:
            rc, txt = run(["docker"] + psql + ["-d", "nextcloud"], input_text=f.read(), timeout=1800)
        if rc != 0:
            raise Abort("Loading the dump failed: %s" % txt.strip()[-300:])
        docker("start", "nextcloud", "nextcloud_cron")
        State.mark("nextcloud-restore-db")


# ================================================================ Beszel
def beszel_first_run():
    """True while Beszel has no user yet."""
    st, js, _ = http("GET", url("beszel", "/api/beszel/first-run"), timeout=10)
    if st == 200 and isinstance(js, dict):
        return bool(js.get("firstRun"))
    return None


def beszel_login(email, pw):
    """Log in to Beszel and return its answer."""
    st, js, _ = http("POST", url("beszel", "/api/collections/users/auth-with-password"),
                     body={"identity": email, "password": pw}, timeout=20)
    return js.get("token") if st == 200 and isinstance(js, dict) else None


@step
class BeszelUser(Step):
    id, group, title = "beszel-user", "Logins and keys", "Beszel hub account created"
    needs = ("stack-beszel",)

    def probe(self):
        return "done" if beszel_first_run() is False else "todo"

    def help(self):
        return "Open %s and create the account with your email address and the admin password. Then run `sudo homelab-setup refresh`." % url("beszel")

    def run(self):
        need_email()
        if Opt.dry:
            out("      would create the Beszel hub account for the email address entered at install")
            return
        pw = need_password("to create the Beszel hub account")
        wait_for(lambda: beszel_first_run() is not None, "Beszel to answer", 120)
        bodies = [{"email": Ctx.email, "password": pw},
                  {"email": Ctx.email, "password": pw, "passwordConfirm": pw},
                  {"email": Ctx.email, "password": pw, "passwordConfirm": pw, "username": Ctx.admin.lower()}]
        for b in bodies:
            st, js, _ = http("POST", url("beszel", "/api/beszel/create-user"), body=b, timeout=30)
            if st in (200, 201, 204) and beszel_first_run() is False:
                return
        raise Abort("The Beszel account could not be created automatically. %s" % self.help())


@step
class BeszelAgentKey(Step):
    id, group, title = "beszel-agent-key", "Logins and keys", "Beszel agent key and token fetched from the hub"
    needs = ("beszel-user",)

    def probe(self):
        Secrets.load()
        if Secrets.get("BESZEL_KEY") and Secrets.get("BESZEL_TOKEN"):
            return "done"
        return "na" if Mode.existing else "todo"

    def run(self):
        if Opt.dry:
            out("      would ask the Beszel hub for its public key and a permanent agent token")
            return
        pw = need_password("to log in to the Beszel hub")
        tok = beszel_login(Ctx.email, pw)
        if not tok:
            raise Abort("The Beszel hub rejected the login for %s. Run `sudo homelab-setup fill`." % Ctx.email)
        hdr = {"Authorization": tok}
        st, js, _ = http("GET", url("beszel", "/api/beszel/info"), headers=hdr, timeout=20)
        if st != 200:
            st, js, _ = http("GET", url("beszel", "/api/beszel/getkey"), headers=hdr, timeout=20)
        key = js.get("key") if st == 200 and isinstance(js, dict) else None
        if not key:
            raise Abort("The Beszel hub did not give its public key (HTTP %s)." % st)
        want = rand_hex(16)
        st, js, _ = http("GET", url("beszel", "/api/beszel/universal-token?enable=1&permanent=1&token=" + want),
                         headers=hdr, timeout=20)
        token = js.get("token") if st == 200 and isinstance(js, dict) else None
        if not token:
            raise Abort("The Beszel hub did not give an agent token (HTTP %s)." % st)
        Secrets.set("BESZEL_KEY", key)
        Secrets.set("BESZEL_TOKEN", token)
