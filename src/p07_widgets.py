

# ================================================================ Homepage widgets: create the key, TEST it, then write it
def basic(user, pw):
    """Basic-authentication header for a user name and password."""
    return {"Authorization": "Basic " + base64.b64encode(("%s:%s" % (user, pw)).encode()).decode()}


def judge(st):
    """For an answer that was not a success: None when the service did not really answer (no connection, too slow, or an error
    of its own: it may be busy or restarting, so nothing can be said about the key), False when it answered and said no."""
    return None if st == 0 or st >= 500 else False


def verdict(st):
    """The result of a test whose success is HTTP 200: True, or what judge() says about any other answer."""
    return True if st == 200 else judge(st)


def v_adguard(v):
    """Test the AdGuard Home login with a live request. True, False (rejected) or None (no answer)."""
    st, _, _ = http("GET", url("adguard", "/control/status"), headers=basic(v["username"], v["password"]), timeout=10)
    return verdict(st)


def v_tailscale(v):
    """Test the Tailscale API key with a live request."""
    base = os.environ.get("HLS_TS_API", "https://api.tailscale.com")
    st, _, _ = http("GET", "%s/api/v2/device/%s" % (base, v["deviceid"]), headers=basic(v["key"], ""), timeout=20)
    return verdict(st)


def v_beszel(v):
    """Test the Beszel login with a live request."""
    silent = False
    for path in ("/api/collections/_superusers/auth-with-password", "/api/admins/auth-with-password"):
        st, js, _ = http("POST", url("beszel", path), body={"identity": v["username"], "password": v["password"]}, timeout=15)
        if st == 200 and isinstance(js, dict) and js.get("token"):
            return True
        silent = silent or judge(st) is None
    return None if silent else False


def v_netdata(v):
    """Test that Netdata answers."""
    st = http("GET", url("netdata", "/api/v1/info"), timeout=10)[0]
    return verdict(st)


def v_speedtest(v):
    """Test the Speedtest Tracker token with a live request."""
    st, _, _ = http("GET", url("speedtest", "/api/v1/results/latest"),
                    headers={"Authorization": "Bearer " + v["key"], "Accept": "application/json"}, timeout=30)
    if st in (401, 403):
        return False
    return None if st == 0 or st >= 500 else True


def v_portainer(v):
    """Test the Portainer key with a live request."""
    st, _, _ = http("GET", url("portainer", "/api/users/me"), headers={"X-API-Key": v["key"]}, timeout=10)
    if st != 200:
        return judge(st)
    st, _, _ = http("GET", url("portainer", "/api/endpoints/%s" % v["env"]), headers={"X-API-Key": v["key"]}, timeout=10)
    return verdict(st)


def v_filebrowser(v):
    """Test the FileBrowser login with a live request."""
    st, _, _ = http("POST", url("filebrowser", "/api/login"), body={"username": v["username"], "password": v["password"]}, timeout=10)
    return verdict(st)


def v_immich(v):
    """Test the Immich key with a live request."""
    st, _, _ = http("GET", url("immich", "/api/server/statistics"), headers={"x-api-key": v["key"]}, timeout=15)
    return verdict(st)


def v_nextcloud(v):
    """Test the Nextcloud token with a live request."""
    st, js, _ = http("GET", url("nextcloud", "/ocs/v2.php/apps/serverinfo/api/v1/info?format=json"),
                     headers={"NC-Token": v["key"], "OCS-APIRequest": "true", "Accept": "application/json"}, timeout=30)
    if st == 200:
        return isinstance(js, dict) and (js.get("ocs") or {}).get("meta", {}).get("statuscode") == 200
    return judge(st)


class WidgetStep(Step):
    group = "Homepage"
    unsure = False          # the last test got no answer from the service (the saved key was kept)

    def __init__(self, sid, card, title, needs, fields, verify, auto=None, prompts=None, kind="auto", help_text="", pre=None, fill_text=""):
        self.id, self.card, self.title = sid, card, title
        self.needs = tuple(needs) + ("homepage-files",)
        self.fields, self.verify, self.auto = fields, verify, auto
        self.prompts = prompts or []
        self.kind = kind
        self.help_text = help_text
        self.fill_text = fill_text
        self.pre = pre or {}

    def values(self):
        v = {f: hp_get(self.card, f) for f in self.fields}
        for k, val in self.pre.items():
            v.setdefault(k, val)
        return v

    def probe(self):
        if not os.path.exists(hp_path()) or not hp_has_widget(self.card):
            return "todo"
        v = self.values()
        if any(is_placeholder(x) for x in v.values()):
            return "todo"
        key = "vf:" + self.id
        last = State.note(key)
        if last and time.time() - float(last) < 600 and not os.environ.get("HLS_NO_THROTTLE"):
            return "todo"           # tested and failed a few minutes ago: do not hammer the service
        ok = self.verify(v)
        if ok is None:
            # The service did not answer (busy, restarting). That says nothing about the key, so the step is NOT redone:
            # a login or key that is in the Homepage config stays as it is, and it is tested again next time.
            self.unsure = True
            return "done"
        self.unsure = False
        if not ok:
            State.note(key, str(time.time()))
            return "todo"
        if last:
            State.note(key, "")
        return "done"

    def detail(self):
        return "kept, the service did not answer just now" if self.unsure else "tested"

    @property
    def service_name(self):
        """The title without the part in brackets: 'AdGuard Home widget login'."""
        return self.title.split(" (")[0]

    def tested(self, v, patient=True):
        """True or False from the service. If it does not answer, wait for it (up to 2 minutes); if it still does not, stop."""
        ok = self.verify(v)
        if ok is None and patient and not Opt.dry:
            def answer():
                nonlocal ok
                ok = self.verify(v)
                return ok is not None
            try:
                wait_for(answer, "%s to answer" % self.service_name, 3 if FAKE else 120, every=5)
            except Abort:
                pass
        if ok is None:
            raise Abort("%s did not answer, so nothing was tested or written. It may be busy or still starting: wait a minute, then run `sudo homelab-setup refresh` again." % self.service_name)
        return ok

    def wait_alive(self):
        """Before asking for a password or changing anything: wait until the service answers at all (up to 2 minutes)."""
        svc = self.card[:-5]
        if svc not in PORTS or Opt.dry:
            return
        def alive():
            st = http("GET", url(svc, "/"), timeout=10)[0]
            return st != 0 and st < 500
        try:
            wait_for(alive, "%s to answer" % svc, 3 if FAKE else 120, every=5)
        except Abort:
            raise Abort("%s is not answering at %s right now. Nothing was changed and no password was asked. Wait a minute, then run `sudo homelab-setup refresh` again." % (self.service_name, url(svc))) from None

    def help(self):
        if self.help_text:
            return self.help_text
        return "This could not be created automatically. Run `sudo homelab-setup fill`."

    def fill_help(self):
        return self.fill_text or self.help()

    def prefill(self):
        """Values the person is not asked for in `fill` (a widget with such values overrides this)."""
        return {}

    def _write(self, v):
        if not self.tested(v):
            raise Abort("The new login or key failed its test against the service, so it was not written to the Homepage configuration.")
        hp_set_widget(self.card, v)
        State.note("vf:" + self.id, "")        # it just passed: never let an older failed test hide that

    def run(self):
        if self.auto is None:
            raise Abort(self.help())
        if Opt.dry:
            out("      would create and test the key for %s, then write it into the Homepage config" % self.card)
            return
        self.wait_alive()
        self._write(self.auto())

    def fill(self):
        cur = {}
        for f, label, hidden in self.prompts:
            cur[f] = ask_secret(label) if hidden else ask(label, hp_get(self.card, f) or "")
        for k, val in self.pre.items():
            cur.setdefault(k, val)
        cur.update(self.prefill())
        try:
            ok = self.tested(cur)
        except Abort as e:
            bad(str(e))
            return False
        if not ok:
            bad("The service rejected it during the test. Nothing was written. Check the value and try again.")
            return False
        hp_set_widget(self.card, cur)
        good("%s tested and saved in the Homepage config." % self.title)
        return True


def auto_adguard():
    """Values for the AdGuard Home widget."""
    return {"username": Ctx.admin, "password": need_password("for the AdGuard Home widget")}


def auto_beszel():
    """Create the Beszel superuser and return the values for its widget."""
    pw = need_password("to create the Beszel superuser (the Homepage widget needs one)")
    rc, txt = docker("exec", "beszel", "/beszel", "superuser", "upsert", Ctx.email, pw, timeout=60)
    if rc != 0:
        raise Abort("Could not create the Beszel superuser: %s" % txt.strip()[-200:])
    return {"username": Ctx.email, "password": pw}


def auto_speedtest():
    """Create the Speedtest Tracker login and token and return the values for its widget."""
    pw = need_password("to set the Speedtest Tracker login")
    esc = lambda s: s.replace("\\", "\\\\").replace("'", "\\'")
    # The container has no "tinker" command, so start the Laravel app from a small PHP script read from stdin.
    code = ("<?php\nchdir('/app/www');\nrequire '/app/www/vendor/autoload.php';\n"
            "$app = require '/app/www/bootstrap/app.php';\n"
            "$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();\n"
            "$u = App\\Models\\User::first();\n"
            "if (!$u) { echo \"HLS_ERROR no user exists yet\\n\"; exit(1); }\n"
            "$u->name = '%s';\n$u->email = '%s';\n"
            "$u->password = Illuminate\\Support\\Facades\\Hash::make('%s');\n$u->save();\n"
            "echo 'HLS_TOKEN=' . $u->createToken('homepage', ['results:read'])->plainTextToken . \"\\n\";\n"
            % (esc(Ctx.admin), esc(Ctx.email), esc(pw)))
    rc, txt = run(["docker", "exec", "-u", "abc", "-i", "speedtest-tracker", "php"], input_text=code, timeout=180)
    m = re.search(r"HLS_TOKEN=(\S+)", txt)
    if not m:
        why = next((l.strip() for l in txt.splitlines() if re.search(r"rror|xception|HLS_ERROR", l)), txt.strip()[:200])
        raise Abort("The Speedtest Tracker token could not be created (%s). Create one manually at %s/admin/api-tokens (enable 'Read Results'), then run `sudo homelab-setup fill`." % (why[:200], url("speedtest")))
    Secrets.set("SPEEDTEST_TOKEN", m.group(1))
    return {"key": m.group(1)}


def auto_portainer():
    """Create a Portainer token and return the values for its widget."""
    pw = need_password("to create the Portainer token for Homepage")
    if not Portainer.login(pw):
        raise Abort("Portainer rejected the login for %s." % Ctx.admin)
    st, me, _ = Portainer.call("GET", "/api/users/me", auth="jwt")
    st, js, _ = Portainer.call("POST", "/api/users/%s/tokens" % me["Id"], auth="jwt",
                               body={"description": "homepage", "password": pw})
    if st not in (200, 201) or not js.get("rawAPIKey"):
        raise Abort("Portainer refused to create the Homepage token (HTTP %s)." % st)
    Secrets.set("PORTAINER_HOMEPAGE_TOKEN", js["rawAPIKey"])
    return {"key": js["rawAPIKey"], "env": str(Portainer.endpoint_id() or 1)}


def auto_filebrowser():
    """Set the FileBrowser login and return the values for its widget."""
    pw = need_password("to set the FileBrowser login")
    api = lambda p: url("filebrowser", p)
    st, tok, _ = http("POST", api("/api/login"), body={"username": Ctx.admin, "password": pw}, timeout=10)
    if st == 200:
        return {"username": Ctx.admin, "password": pw}          # already set
    rc, logs = docker("logs", "filebrowser-filebrowser-1")
    m = re.findall(r"randomly generated password:\s*(\S+)", logs) or re.findall(r"password:\s*(\S+)", logs)
    if not m:
        raise Abort("FileBrowser's initial password is no longer in its log. Open %s, log in as admin, then run `sudo homelab-setup fill`." % url("filebrowser"))
    st, tok, _ = http("POST", api("/api/login"), body={"username": "admin", "password": m[-1]}, timeout=10)
    if st != 200 or not isinstance(tok, str):
        raise Abort("FileBrowser rejected the password found in its log. Run `sudo homelab-setup fill`.")
    hdr = {"X-Auth": tok.strip()}
    st, user, _ = http("GET", api("/api/users/1"), headers=hdr, timeout=10)
    if st != 200 or not isinstance(user, dict):
        raise Abort("FileBrowser did not return its admin account (HTTP %s)." % st)
    user["username"], user["password"] = Ctx.admin, pw
    st, js, _ = http("PUT", api("/api/users/1"), headers=hdr, body={"what": "user", "which": ["all"], "data": user,
                                                                    "current_password": m[-1]}, timeout=20)
    if st not in (200, 201, 204):
        raise Abort("FileBrowser refused to change the admin login (HTTP %s)." % st)
    return {"username": Ctx.admin, "password": pw}


def auto_immich():
    """Create an Immich API key and return the values for its widget."""
    if immich_restored():
        raise Abort("Immich was restored from a backup, so the key must be created manually: Immich > Account Settings > API Keys (permission server.statistics). Then run `sudo homelab-setup fill`.")
    pw = need_password("to log in to Immich and create the Homepage key")
    st, js, _ = http("POST", url("immich", "/api/auth/login"), body={"email": Ctx.email, "password": pw}, timeout=30)
    if st not in (200, 201) or not isinstance(js, dict) or not js.get("accessToken"):
        raise Abort("Immich rejected the login for %s. Run `sudo homelab-setup fill`." % Ctx.email)
    st, js, _ = http("POST", url("immich", "/api/api-keys"), headers={"Authorization": "Bearer " + js["accessToken"]},
                     body={"name": "homepage", "permissions": ["server.statistics"]}, timeout=30)
    if st not in (200, 201) or not isinstance(js, dict) or not js.get("secret"):
        raise Abort("Immich refused to create the API key (HTTP %s)." % st)
    Secrets.set("IMMICH_HOMEPAGE_KEY", js["secret"])
    return {"key": js["secret"]}


def auto_nextcloud():
    """Create a Nextcloud token and return the values for its widget."""
    tok = rand_hex(24)
    rc, txt = occ("config:app:set", "serverinfo", "token", "--value=" + tok)
    if rc != 0:
        raise Abort("occ could not set the serverinfo token: %s" % txt.strip()[-200:])
    Secrets.set("NC_SERVERINFO_TOKEN", tok)
    return {"key": tok}


class TailscaleWidget(WidgetStep):
    """The Homepage Tailscale widget, which needs a key made by hand."""
    def prefill(self):
        Ctx.refresh_tailscale()
        return {"deviceid": Ctx.ts_id}


def _register_widgets():
    """Create one checklist step per Homepage widget."""
    mk = WidgetStep
    items = [
        mk("w-adguard", "adguard-card", "AdGuard Home widget login", ("adguard-setup",), ["username", "password"],
           v_adguard, auto_adguard, [("username", "AdGuard username", False), ("password", "AdGuard password", True)]),
        TailscaleWidget("w-tailscale", "tailscale-card", "Tailscale widget (machine ID and API access token)",
                        ("tailscale-login",), ["deviceid", "key"], v_tailscale, None,
                        [("key", "Tailscale API access token (starts with tskey-api-)", True)], kind="manual",
                        help_text="Create an API access token at https://login.tailscale.com/admin/settings/keys (Generate access token), then start the walk-through and paste it:\n$ sudo homelab-setup fill\nThe machine ID is filled in automatically.",
                        fill_text="Create an API access token at https://login.tailscale.com/admin/settings/keys (Generate access token), then paste it below. The machine ID is filled in automatically."),
        mk("w-beszel", "beszel-card", "Beszel widget login (a Beszel superuser)", ("beszel-user",), ["username", "password"],
           v_beszel, auto_beszel, [("username", "Beszel superuser email", False), ("password", "Beszel superuser password", True)]),
        mk("w-netdata", "netdata-card", "Netdata widget", ("stack-netdata",), [], v_netdata, lambda: {}),
        mk("w-speedtest", "speedtest-card", "Speedtest Tracker widget key (API token, Read Results)",
           ("stack-speedtest-tracker",), ["key"], v_speedtest, auto_speedtest, [("key", "Speedtest Tracker API token", True)]),
        mk("w-portainer", "portainer-card", "Portainer widget key", ("portainer-env",), ["env", "key"], v_portainer,
           auto_portainer, [("key", "Portainer access token (ptr_...)", True)], pre={"env": "1"}),
        mk("w-filebrowser", "filebrowser-card", "FileBrowser widget login", ("stack-filebrowser",), ["username", "password"],
           v_filebrowser, auto_filebrowser, [("username", "FileBrowser username", False), ("password", "FileBrowser password", True)]),
        mk("w-immich", "immich-card", "Immich widget key (API key, server.statistics)", ("immich-admin",), ["key"],
           v_immich, auto_immich, [("key", "Immich API key", True)]),
        mk("w-nextcloud", "nextcloud-card", "Nextcloud widget key (serverinfo token)", ("nextcloud-config",), ["key"],
           v_nextcloud, auto_nextcloud, [("key", "Nextcloud NC-Token", True)]),
    ]
    for s in items:
        register(s)


_register_widgets()
