

# ================================================================ Portainer
class Portainer:
    """Portainer's web API (login, token, stacks)."""
    jwt = None
    _env_id = None

    @staticmethod
    def base():
        return url("portainer")

    @classmethod
    def call(cls, method, path, body=None, form=None, timeout=60, auth="key"):
        hdr = {}
        key = Secrets.get("PORTAINER_TOKEN")
        if auth == "jwt" and cls.jwt:
            hdr["Authorization"] = "Bearer " + cls.jwt
        elif key:
            hdr["X-API-Key"] = key
        elif cls.jwt:
            hdr["Authorization"] = "Bearer " + cls.jwt
        return http(method, cls.base() + path, body=body, form=form, headers=hdr, timeout=timeout)

    @classmethod
    def alive(cls):
        st, _, _ = http("GET", cls.base() + "/api/status", timeout=8)
        return st == 200

    @classmethod
    def admin_state(cls):
        st, _, _ = http("GET", cls.base() + "/api/users/admin/check", timeout=8)
        return st      # 204 ready, 404 needs first admin, 303 setup window closed, 0 not reachable

    @classmethod
    def login(cls, password):
        st, js, _ = http("POST", cls.base() + "/api/auth", body={"Username": Ctx.admin, "Password": password}, timeout=20)
        if st != 200 or not isinstance(js, dict) or "jwt" not in js:
            return False
        cls.jwt = js["jwt"]
        return True

    @classmethod
    def endpoint_id(cls):
        if cls._env_id:
            return cls._env_id
        if not Secrets.get("PORTAINER_TOKEN"):
            return None
        st, js, _ = cls.call("GET", "/api/endpoints", timeout=20)
        if st == 200 and isinstance(js, list) and js:
            pick = next((e for e in js if e.get("Name") == "local"), js[0])
            cls._env_id = pick.get("Id")
        return cls._env_id

    @classmethod
    def stacks(cls):
        st, js, _ = cls.call("GET", "/api/stacks", timeout=30)
        return js if st == 200 and isinstance(js, list) else []

    @classmethod
    def stack_named(cls, name):
        """The stack called `name` as Portainer lists it, or None."""
        return next((s for s in cls.stacks() if s.get("Name") == name), None)

    @classmethod
    def stack_file(cls, stack):
        """The saved file of a stack, as text ('' when it cannot be read)."""
        eid = stack.get("EndpointId") or cls.endpoint_id()
        st, js, _ = cls.call("GET", "/api/stacks/%s/file?endpointId=%s" % (stack["Id"], eid), timeout=30)
        return js.get("StackFileContent", "") if st == 200 and isinstance(js, dict) else ""

    @classmethod
    def redeploy(cls, stack, text, env):
        """Give an existing stack a new file and redeploy it. `env` is a list of {"name", "value"}. Returns (status, answer)."""
        eid = stack.get("EndpointId") or cls.endpoint_id()
        st, js, _ = cls.call("PUT", "/api/stacks/%s?endpointId=%s" % (stack["Id"], eid),
                             body={"stackFileContent": text, "env": env, "prune": False,
                                   "pullImage": False, "repullImageAndRedeploy": False}, timeout=900)
        return st, js

    @staticmethod
    def error_text(js):
        """What Portainer said when it refused something."""
        return str(js.get("details") or js.get("message") if isinstance(js, dict) else js)

    @classmethod
    def deploy(cls, name, text, env):
        eid = cls.endpoint_id()
        if not eid:
            raise Abort("Portainer has no Docker environment yet.")
        envl = [{"name": k, "value": v} for k, v in env]
        existing = cls.stack_named(name)
        if existing:
            st, js = cls.redeploy(existing, text, envl)
        else:
            st, js, _ = cls.call("POST", "/api/stacks/create/standalone/string?endpointId=%s" % eid,
                                 body={"name": name, "stackFileContent": text, "env": envl}, timeout=900)
        if st not in (200, 201):
            raise Abort("Portainer refused to deploy stack '%s' (HTTP %s): %s" % (name, st, cls.error_text(js)[:400]))


def setup_tokens():
    """Portainer 2.39.4 / 2.43 and newer refuse the first admin without a setup token. Candidates, best first:
    the one the installer gave Portainer at creation, then the one Portainer printed in its log."""
    found = []
    mine = State.data.get("ptoken")
    if mine:
        found.append(mine)
    rc, txt = run(["docker", "logs", "portainer"])
    txt = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", txt or "")
    for m in re.finditer(r"setup_token[=:]\s*[\"']?([A-Za-z0-9_\-+/=.]{8,})", txt):
        if m.group(1) not in found:
            found.insert(1 if mine else 0, m.group(1))
    return found


@step
class PortainerRunning(Step):
    id, group, title = "portainer", "Platform", "Portainer is running"
    needs = ("docker",)

    def probe(self):
        return "done" if "portainer" in containers_running() and Portainer.alive() else "todo"

    def run(self):
        if "portainer" in containers_all() and "portainer" not in containers_running():
            act(["docker", "start", "portainer"], check=True)
        elif "portainer" not in containers_all():
            act(["docker", "pull", "portainer/portainer-ce:latest"], timeout=900)
            # our own setup token (new Portainer versions require one for the first admin); used once, then useless
            tok = State.data.get("ptoken") or rand_alnum(32)
            if not Opt.dry:
                State.data["ptoken"] = tok
                State.save()
            act(["docker", "run", "-d", "--name", "portainer", "--restart=always",
                 "-p", "9000:9000", "-p", "9443:9443",
                 "-v", "/var/run/docker.sock:/var/run/docker.sock", "-v", "portainer_data:/data",
                 "portainer/portainer-ce:latest", "--setup-token", "<random token>" if Opt.dry else tok], check=True, timeout=300)
        if not Opt.dry:
            wait_for(Portainer.alive, "Portainer to start", 120)


def restart_portainer():
    """Restart Portainer and wait until it answers again (its first-setup window then opens afresh)."""
    docker("restart", "portainer")
    wait_for(Portainer.alive, "Portainer to restart", 120)
    time.sleep(2 if not FAKE else 0)


@step
class PortainerAdmin(Step):
    id, group, title = "portainer-admin", "Platform", "Portainer admin account created"
    needs = ("portainer",)

    def probe(self):
        return "done" if Portainer.admin_state() == 204 else "todo"

    def run(self):
        pw = need_password("to create the Portainer admin account") if not Opt.dry else None
        if Opt.dry:
            out("      would create the Portainer admin '%s' with the password entered at install" % (Ctx.admin or "admin"))
            return
        last = (0, "")
        for attempt in (1, 2, 3):
            state = Portainer.admin_state()
            if state == 204:
                return
            if state == 303:
                out("      the first-setup window closed; restarting Portainer to reopen it")
                restart_portainer()
            for tok in (setup_tokens() or [None]):
                hdr = {"X-Setup-Token": tok} if tok else {}
                st, js, _ = http("POST", Portainer.base() + "/api/users/admin/init", headers=hdr,
                                 body={"Username": Ctx.admin, "Password": pw}, timeout=30)
                if st in (200, 201):
                    State.data.pop("ptoken", None)
                    State.save()
                    return
                last = (st, js)
                if st != 403:
                    break
            if attempt < 3:
                out("      Portainer refused (HTTP %s); restarting it to open a fresh setup window" % last[0])
                restart_portainer()
        raise Abort("Portainer refused the admin account (HTTP %s): %s" % (last[0], str(last[1])[:200]))


@step
class PortainerToken(Step):
    id, group, title = "portainer-token", "Platform", "Portainer access token for the installer saved (used to deploy stacks)"
    needs = ("portainer-admin",)

    def probe(self):
        Secrets.load()
        if not Secrets.get("PORTAINER_TOKEN"):
            return "na" if Mode.existing else "todo"
        st, _, _ = Portainer.call("GET", "/api/users/me", timeout=10)
        return "done" if st == 200 else "todo"

    def run(self):
        if Opt.dry:
            out("      would create a Portainer access token named homelab-setup and keep it in the secrets file")
            return
        pw = need_password("to create the Portainer access token")
        if not Portainer.login(pw):
            raise Abort("Portainer rejected the login for '%s'. If the account already exists with a different password, run `sudo homelab-setup fill`." % Ctx.admin)
        st, me, _ = Portainer.call("GET", "/api/users/me", auth="jwt")
        if st != 200:
            raise Abort("Portainer did not return the account details (HTTP %s)." % st)
        st, js, _ = Portainer.call("POST", "/api/users/%s/tokens" % me["Id"], auth="jwt",
                                   body={"description": "homelab-setup", "password": pw})
        if st not in (200, 201) or not isinstance(js, dict) or not js.get("rawAPIKey"):
            raise Abort("Portainer refused to create an access token (HTTP %s)." % st)
        Secrets.set("PORTAINER_TOKEN", js["rawAPIKey"])


@step
class PortainerEnv(Step):
    id, group, title = "portainer-env", "Platform", "Portainer manages this machine's Docker"
    needs = ("portainer-token",)

    def probe(self):
        if not Secrets.get("PORTAINER_TOKEN"):
            return "na" if Mode.existing else "todo"
        return "done" if Portainer.endpoint_id() else "todo"

    def detail(self):
        return "environment %s" % Portainer.endpoint_id()

    def run(self):
        if Opt.dry:
            return
        try:
            wait_for(Portainer.endpoint_id, "Portainer to add the local Docker environment", 40, every=2, quiet=True)
            return
        except Abort:
            pass
        st, js, _ = Portainer.call("POST", "/api/endpoints",
                                   form={"Name": "local", "EndpointCreationType": "1"}, timeout=60)
        Portainer._env_id = None
        if st not in (200, 201) or not Portainer.endpoint_id():
            raise Abort("Portainer refused to add the local Docker environment (HTTP %s): %s" % (st, str(js)[:200]))


# ================================================================ the nine stacks
def prepull(images):
    """Pull the images one at a time (ghcr.io throttles parallel pulls)."""
    todo = [i for i in images if docker("image", "inspect", i)[0] != 0]
    for n, img in enumerate(todo, 1):
        Live.set_note("downloading %d of %d: %s" % (n, len(todo), img.split("/")[-1].split(":")[0]))
        for attempt in range(1, 5):
            rc, txt = act(["docker", "pull", img], timeout=1800)
            if rc == 0 or Opt.dry:
                break
            if "toomanyrequests" in txt or "rate limit" in txt.lower():
                out("      the registry is throttling; waiting a minute (try %d of 4)" % attempt)
                time.sleep(60 if not FAKE else 0)
                continue
            if attempt == 4:
                raise Abort("Could not download image %s: %s" % (img, txt.strip()[-300:]))
            time.sleep(5 if not FAKE else 0)


class StackStep(Step):
    group = "Services"

    def __init__(self, name, needs, title, wait=300):
        self.name, self.needs, self.title, self.wait = name, tuple(needs), title, wait
        self.id = "stack-" + name

    def probe(self):
        return "done" if stack_up(self.name) else "todo"

    def detail(self):
        return "%d container(s) running" % len(STACKS[self.name][1])

    def run(self):
        text = stack_text(self.name)
        env = stack_env(self.name)
        prepull(images_in(text))
        if Opt.dry:
            out("      would deploy stack '%s' through Portainer (%d container(s))" % (self.name, len(STACKS[self.name][1])))
            return
        Portainer.deploy(self.name, text, env)
        wait_for(lambda: stack_up(self.name), "the %s containers to start" % self.name, self.wait)
        if self.name == "immich":
            wait_for(lambda: docker("inspect", "-f", "{{.State.Health.Status}}", "immich_server")[1].strip() == "healthy",
                     "Immich to become healthy", 900, every=5)


def _register_stacks():
    """Create one checklist step per Portainer stack."""
    base = ("portainer-env", "folders")
    spec = [
        ("adguard", base + ("port53", "restore-configs"), "AdGuard Home stack (DNS ad blocking)"),
        ("beszel", base, "Beszel stack (server health)"),
        ("netdata", base, "Netdata stack (live metrics)"),
        ("speedtest-tracker", base + ("secrets",), "Speedtest Tracker stack"),
        ("filebrowser", base, "FileBrowser stack"),
        ("immich", base + ("secrets", "restore-data"), "Immich stack (photos)"),
        ("nextcloud", base + ("secrets", "tailscale-login", "restore-configs", "restore-data"), "Nextcloud stack (files)"),
        ("homepage", base + ("tailscale-login", "homepage-files"), "Homepage stack (the dashboard)"),
        ("beszel-agent", base + ("beszel-agent-key",), "Beszel agent stack"),
    ]
    for name, needs, title in spec:
        register(StackStep(name, needs, title, 900 if name == "nextcloud" else 300))


_register_stacks()


def filebrowser_destinations():
    """The folders FileBrowser has mounted right now (read from the running container)."""
    rc, txt = docker("inspect", "-f", "{{range .Mounts}}{{.Destination}}|{{end}}", "filebrowser-filebrowser-1", timeout=30)
    return {d.strip() for d in txt.split("|") if d.strip()} if rc == 0 else set()


@step
class FileBrowserDrives(Step):
    id, group, title = "filebrowser-drives", "Services", "FileBrowser shows the backup drives in a Backup-Pool folder, each in a folder named after the drive"
    needs = ("stack-filebrowser",)

    def applies(self):
        return not Mode.existing

    def probe(self):
        want = {d for _, d in filebrowser_mounts()}
        have = {d for d in filebrowser_destinations() if d.startswith("/srv/")}
        return "done" if have == want else "todo"

    def detail(self):
        return ", ".join(d.replace("/srv/", "") for _, d in filebrowser_mounts())

    def help(self):
        return ("FileBrowser lists the backup drives that are connected now. After connecting or removing a drive with `sudo drives`, "
                "run this to update it (FileBrowser restarts for a few seconds):\n$ sudo homelab-setup refresh")

    def run(self):
        text = stack_text("filebrowser")
        if Opt.dry:
            out("      would redeploy FileBrowser with: %s" % self.detail())
            return
        Portainer.deploy("filebrowser", text, stack_env("filebrowser"))
        wait_for(lambda: stack_up("filebrowser"), "FileBrowser to restart", 120)
        wait_for(lambda: self.probe() == "done", "FileBrowser to show the drives", 60)

