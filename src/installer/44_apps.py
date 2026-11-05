# ================================================================ Navidrome (plays the songs Downtify saved)
class NavidromeStack(StackStep):
    """Only on a machine that has a music folder (the folder Downtify saves into). A hand-built server is only looked at."""

    def applies(self):
        return not Mode.existing and bool(music_folder())

    def detail(self):
        return "music folder %s" % music_folder()

    def stamp(self):
        env = "".join(v for _, v in stack_env("navidrome"))        # new Last.fm keys, or AudioMuse-AI first in the agents, deploy Navidrome once more
        return hashlib.md5((stack_text("navidrome") + env).encode()).hexdigest()

    def probe(self):
        # a Navidrome from an earlier version of the installer is deployed once more, so it gets the Spotify-ish theme and the frame setting
        return "done" if stack_up(self.name) and State.data.get("navidrome_stack") == self.stamp() else "todo"

    def run(self):
        folder = Ctx.home + "/navidrome"
        if not Opt.dry:
            os.makedirs(P(folder), exist_ok=True)
            chown(P(folder), Ctx.uid, Ctx.gid)
        StackStep.run(self)
        if not Opt.dry:
            State.data["navidrome_stack"] = self.stamp()
            State.save()


register(NavidromeStack("navidrome", ("portainer-env", "folders"), "Navidrome music server (plays the songs Downtify saved)"))


@step
class NavidromeCard(Step):
    id, group = "navidrome-card", "Homepage"
    title = "Navidrome login and its dashboard card (first in its group) with Navidrome's own player inside"
    needs = ("stack-navidrome", "homepage-files")

    def applies(self):
        return BY_ID["stack-navidrome"].applies()

    def probe(self):
        svc = read_file(hp_path("services.yaml"))
        if card_widget_type(svc, "navidrome-card") != "iframe":
            return "todo"
        return "done" if card_range(svc.split("\n"), PLAYER_ID) is None and navidrome_card_first(svc) and navidrome_card_named(svc) == svc else "todo"

    def run(self):
        if Opt.dry:
            out("      would create the Navidrome login (%s), then put Navidrome's player inside its dashboard card, first in its group" % Ctx.admin)
            return
        old = read_file(hp_path("services.yaml"))
        new = old
        if card_widget_type(old, "navidrome-card") not in ("navidrome", "iframe"):          # first time: the login
            pw = need_password("to create the Navidrome login")
            if not wait_for(lambda: http("GET", url("navidrome", "/"), raw=True, timeout=10)[0] == 200, "Navidrome to answer", 120):
                raise Abort("Navidrome does not answer on port %d. Look at its log:  docker logs navidrome" % PORTS["navidrome"])
            creds = {"username": Ctx.admin, "password": pw}
            st, _, _ = http("POST", url("navidrome", "/auth/createAdmin"), body=creds, timeout=30)
            if st != 200:                                    # 403: it has a login already. Is it ours?
                st, _, _ = http("POST", url("navidrome", "/auth/login"), body=creds, timeout=30)
                if st != 200:
                    warn("Navidrome already has a login that is not %s with the shared admin password. Open it and log in with the login it has. "
                         "(The player card of the dashboard works with any login.)" % Ctx.admin)
            else:
                out("      Navidrome is at %s. Log in as %s with the shared admin password." % (url("navidrome"), Ctx.admin))
            if not FAKE and os.path.exists(P("/usr/local/sbin/homelab-cards")):
                run([P("/usr/local/sbin/homelab-cards"), "sync"], timeout=120)        # makes the card (and its Tailscale address) now
            old = read_file(hp_path("services.yaml"))
            if card_widget_type(old, "navidrome-card") is None:
                warn("The dashboard has no Navidrome card yet. homelab-cards makes it within 5 minutes; run `sudo homelab-setup upgrade` after that "
                     "to put the player in it.")
                return
        new = services_without_card(old, PLAYER_ID)                    # zip 33 had a second card for the player: it is one card now
        new = services_with_iframe_widget(new, "navidrome-card", Ctx.lan or svc_host())
        new = card_to_top(new, "navidrome-card")
        new = navidrome_card_named(new)
        if new != old:
            if not os.path.exists(hp_path("services.yaml") + ".before-navidrome"):
                write_file(hp_path("services.yaml") + ".before-navidrome", old, 0o644, (Ctx.uid, Ctx.gid))
            write_file(hp_path("services.yaml"), new, 0o644, (Ctx.uid, Ctx.gid))
            out("      The Navidrome card is first in its group, called Navidrome (\"Spotify Music Player\"), and has Navidrome's own player inside "
                "(previous, next, shuffle, repeat). Clicking its title opens the full Navidrome page.")


# ================================================================ AudioMuse-AI (similar songs for Navidrome; only after `homelab-setup audiomuse`)
AUDIOMUSE_PLUGIN_URL = "https://github.com/NeptuneHub/AudioMuse-AI-NV-plugin/releases/download/v11/audiomuseai.ndp"
AUDIOMUSE_PLUGIN_ID = "audiomuseai"


def audiomuse_applies():
    return audiomuse_wanted() and BY_ID["stack-navidrome"].applies()


def audiomuse_plugin_file():
    return P(Ctx.home + "/navidrome/plugins/%s.ndp" % AUDIOMUSE_PLUGIN_ID)


def navidrome_cli(*args, **kw):
    """Run Navidrome's own program inside its container (plugin rescan, edit, enable ...). Returns (exit code, output)."""
    return docker("exec", "-i", "navidrome", "/app/navidrome", *args, **kw)


@step
class AudioMuseUser(Step):
    id, group = "audiomuse-user", "Services"
    title = "AudioMuse-AI has its own small Navidrome login (a normal login with a generated password)"
    needs = ("stack-navidrome", "navidrome-card")

    def applies(self):
        return audiomuse_applies()

    def probe(self):
        return "done" if State.data.get("audiomuse_user") and Secrets.get("AUDIOMUSE_ND_PASSWORD") else "todo"

    def run(self):
        if Opt.dry:
            out("      would make the Navidrome login '%s' for AudioMuse-AI (a normal login, not an admin)" % AUDIOMUSE_ND_USER)
            return
        for key, make in AUDIOMUSE_SECRETS.items():
            if not Secrets.get(key):
                Secrets.vals[key] = make()
        Secrets.save()
        mine = {"username": AUDIOMUSE_ND_USER, "password": Secrets.get("AUDIOMUSE_ND_PASSWORD")}
        if http("POST", url("navidrome", "/auth/login"), body=mine, timeout=30)[0] != 200:       # not made yet (or by an earlier try)
            pw = need_password("to make the AudioMuse-AI login in Navidrome")
            st, js, _ = http("POST", url("navidrome", "/auth/login"), body={"username": Ctx.admin, "password": pw}, timeout=30)
            if st != 200 or not isinstance(js, dict) or not js.get("token"):
                raise Abort("Navidrome did not accept the login %s with the shared admin password, so the AudioMuse-AI login could not be made. "
                            "Open Navidrome and check the login, then run `sudo homelab-setup refresh`." % Ctx.admin)
            st, js, _ = http("POST", url("navidrome", "/api/user"), headers={"X-ND-Authorization": "Bearer " + js["token"]}, timeout=30,
                             body={"userName": AUDIOMUSE_ND_USER, "name": "AudioMuse-AI", "password": mine["password"], "isAdmin": False})
            if st not in (200, 201):
                raise Abort("Navidrome refused to make the login '%s' (HTTP %s). If a login with that name is already there, delete it in Navidrome "
                            "(Users page), then run `sudo homelab-setup refresh`. Navidrome said: %s" % (AUDIOMUSE_ND_USER, st, str(js)[:200]))
            out("      Made the Navidrome login '%s' for AudioMuse-AI. Its password is saved in the root-only file (sudo homelab-setup secrets)." % AUDIOMUSE_ND_USER)
        State.data["audiomuse_user"] = True
        State.save()


class AudioMuseStack(StackStep):
    """AudioMuse-AI's three containers: database, web page and worker. Only after `homelab-setup audiomuse`."""

    def applies(self):
        return audiomuse_applies()

    def detail(self):
        return "port %d, the worker may use %s of memory" % (PORTS["audiomuse"], audiomuse_mem())

    def stamp(self):
        env = "|".join("%s=%s" % kv for kv in stack_env("audiomuse"))          # a new memory limit deploys the stack once more
        return hashlib.md5((stack_text("audiomuse") + env).encode()).hexdigest()

    def probe(self):
        need = {"audiomuse-postgres", "audiomuse-flask"}
        if not State.data.get("audiomuse_paused"):
            need.add("audiomuse-worker")                     # a paused worker (`audiomuse pause`) is wanted, not a fault
        return "done" if need <= containers_running() and State.data.get("audiomuse_stack") == self.stamp() else "todo"

    def run(self):
        if not Opt.dry:
            for folder in (Ctx.home + "/audiomuse", Ctx.home + "/audiomuse/postgres"):
                os.makedirs(P(folder), exist_ok=True)
                chown(P(folder), Ctx.uid, Ctx.gid)
        StackStep.run(self)
        if Opt.dry:
            return
        State.data.pop("audiomuse_paused", None)             # a new deploy starts the worker again
        State.data["audiomuse_stack"] = self.stamp()
        State.save()
        if not wait_for(lambda: http("GET", url("audiomuse", "/api/health"), timeout=10)[0] == 200, "AudioMuse-AI to answer", 240):
            raise Abort("AudioMuse-AI does not answer on port %d. Look at its log:  docker logs audiomuse-flask" % PORTS["audiomuse"])
        head = {"Authorization": "Bearer " + Secrets.get("AUDIOMUSE_TOKEN")}
        if http("GET", url("audiomuse", "/api/last_task"), headers=head, timeout=20)[0] != 200:
            warn("AudioMuse-AI did not accept its saved token. Open %s, go to Administration > Setup Wizard and enter the API token shown by "
                 "`sudo homelab-setup secrets` (AUDIOMUSE_TOKEN)." % url("audiomuse"))


register(AudioMuseStack("audiomuse", ("portainer-env", "folders", "stack-navidrome", "audiomuse-user"),
                        "AudioMuse-AI stack (listens to your songs so Navidrome can suggest similar ones)", 600))


@step
class AudioMusePlugin(Step):
    id, group = "audiomuse-plugin", "Services"
    title = "The AudioMuse-AI plugin is in Navidrome, switched on and pointed at AudioMuse-AI"
    needs = ("stack-navidrome", "stack-audiomuse")

    def applies(self):
        return audiomuse_applies()

    def config(self):
        return {"apiUrl": "http://%s:%d" % (svc_host(), PORTS["audiomuse"]), "apiToken": Secrets.get("AUDIOMUSE_TOKEN")}

    def stamp(self):
        return hashlib.md5((AUDIOMUSE_PLUGIN_URL + json.dumps(self.config(), sort_keys=True)).encode()).hexdigest()

    def probe(self):
        return "done" if os.path.isfile(audiomuse_plugin_file()) and State.data.get("audiomuse_plugin") == self.stamp() else "todo"

    def run(self):
        if Opt.dry:
            out("      would download the AudioMuse-AI plugin, put it in Navidrome's plugins folder, point it at AudioMuse-AI and switch it on")
            return
        try:
            data = fetch_bytes(AUDIOMUSE_PLUGIN_URL, timeout=120)
        except (OSError, ValueError) as e:
            raise Abort("The AudioMuse-AI plugin could not be downloaded from GitHub (%s). Check the internet connection, then run "
                        "`sudo homelab-setup refresh`." % e) from None
        if not FAKE and data[:2] != b"PK":
            raise Abort("The file from %s is not a plugin file. Nothing was changed." % AUDIOMUSE_PLUGIN_URL)
        folder = os.path.dirname(audiomuse_plugin_file())
        os.makedirs(folder, exist_ok=True)
        chown(folder, Ctx.uid, Ctx.gid)
        write_bytes(audiomuse_plugin_file(), data, 0o644, (Ctx.uid, Ctx.gid))
        for what, args, extra in (("find the plugin", ("plugin", "rescan"), {}),
                                  ("take its settings", ("plugin", "edit", AUDIOMUSE_PLUGIN_ID, "--config-file", "-"),
                                   {"input_text": json.dumps(self.config())}),
                                  ("switch it on", ("plugin", "enable", AUDIOMUSE_PLUGIN_ID), {})):
            rc, txt = navidrome_cli(*args, timeout=120, **extra)
            if rc != 0:
                raise Abort("Navidrome could not %s: %s\nThis plugin is made for a newer Navidrome than the one this lab runs. "
                            "`sudo homelab-setup audiomuse remove` takes it out again." % (what, txt.strip()[-300:]))
        docker("restart", "navidrome", timeout=120)
        wait_for(lambda: http("GET", url("navidrome", "/"), raw=True, timeout=10)[0] == 200, "Navidrome to answer", 120)
        State.data["audiomuse_plugin"] = self.stamp()
        State.save()
        if not FAKE and os.path.exists(P("/usr/local/sbin/homelab-cards")):
            run([P("/usr/local/sbin/homelab-cards"), "sync"], timeout=120)        # the dashboard card of AudioMuse-AI, now
        out("      The plugin is on. Now let AudioMuse-AI listen to your songs once: open %s, log in as %s and press Start Analysis." % (
            url("audiomuse"), Ctx.admin))


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
