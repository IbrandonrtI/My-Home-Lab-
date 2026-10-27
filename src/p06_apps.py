

# ================================================================ restore from a backup (only when one is found and you said yes)
def restore_choice():
    """What the person chose to restore from a backup (saved in the state file)."""
    return State.data.get("restore", {})


def find_backups():
    """Folders that look like a backup of an earlier lab (they hold main/ and boot-configs/)."""
    import glob
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
    users = os.listdir((path + "/boot-configs/home")) if os.path.isdir((path + "/boot-configs/home")) else []
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
    import glob
    return bool(restore_choice().get("data")) and bool(glob.glob(P("/mnt/storage/immich/backups/*")))


# ================================================================ Homepage config files
HP_FILES = ["services.yaml", "settings.yaml", "widgets.yaml", "bookmarks.yaml", "custom.css"]


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
                if f == "widgets.yaml":
                    # the first resources pill is named "Server" in the repository file; use this machine's name
                    body = re.sub(r"(- resources:\n\s+label:) Server\b", lambda m: "%s %s" % (m.group(1), Ctx.hostname), body, count=1)
                if f == "widgets.yaml" and State.data["answers"].get("weather"):
                    w = State.data["answers"]["weather"]
                    new = weather_apply(body, w)
                    if new is not None:
                        body = new
                        State.data["weather_set"] = w["name"]
                        State.save()
                write_file(dst, body, 0o644, (Ctx.uid, Ctx.gid))
            elif f in ("services.yaml", "bookmarks.yaml"):
                old = read_file(dst)
                new = subst(old)
                if new != old:
                    write_file(dst, new, 0o644, (Ctx.uid, Ctx.gid))


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
        if not Ctx.email:
            raise Abort("An email address is required. Run `sudo homelab-setup install` and answer the questions.")
        if Opt.dry:
            out("      would create the Immich admin %s with the email address entered at install" % Ctx.admin)
            return
        pw = need_password("to create the Immich admin account")
        wait_for(lambda: http("GET", url("immich", "/api/server/ping"), timeout=8)[0] == 200, "Immich to answer", 300)
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


def occ(*args, stdin=None):
    """Run Nextcloud's `occ` command inside its container."""
    return docker("exec", "-u", "www-data", "nextcloud", "php", "occ", *args, timeout=300)


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
        import glob
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
        import gzip
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
        if not Ctx.email:
            raise Abort("An email address is required. Run `sudo homelab-setup install` and answer the questions.")
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
