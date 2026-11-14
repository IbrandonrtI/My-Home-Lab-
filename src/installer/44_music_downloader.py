MD_BACKUP = SECRET_DIR + "/music-downloader-before.yaml"
MD_NAMES = ("downtify", "metube")


def md_old_containers():
    found = {}
    for n in MD_NAMES:
        rc, txt = docker("inspect", n, timeout=30)
        if rc != 0:
            continue
        try:
            data = json.loads(txt)
        except ValueError:
            continue
        if isinstance(data, list) and data and isinstance(data[0], dict):
            found[n] = data[0]
    return found


def md_compose_from_files(old):
    for c in old.values():
        lab = (c.get("Config") or {}).get("Labels") or {}
        project = lab.get("com.docker.compose.project", "")
        files = [f for f in (lab.get("com.docker.compose.project.config_files", "")).split(",") if f and os.path.isfile(P(f))]
        if not project or not files:
            continue
        args = ["compose", "-p", project]
        if lab.get("com.docker.compose.project.working_dir"):
            args += ["--project-directory", lab["com.docker.compose.project.working_dir"]]
        for f in files:
            args += ["-f", f]
        rc, txt = docker(*args, "config", timeout=60)
        text = txt if rc == 0 else ""
        if "services:" in text and "build:" not in text and all(("container_name: " + n) in text for n in old):
            return re.sub(r"(?m)^name:.*\n", "", text, count=1)
    return ""


def md_compose_from_inspect(old):
    """Build a Compose file from the settings a running container was started with (image, ports, folders, environment, user)."""
    lines = ["services:"]
    for n, c in old.items():
        cfg, host = c.get("Config") or {}, c.get("HostConfig") or {}
        image = cfg.get("Image") or ""
        if not image:
            return ""
        lines += ["  %s:" % n, "    image: %s" % image, "    container_name: %s" % n]
        policy = (host.get("RestartPolicy") or {}).get("Name") or ""
        lines.append("    restart: %s" % (policy if policy and policy != "no" else "unless-stopped"))
        if cfg.get("User"):
            lines.append("    user: \"%s\"" % cfg["User"])
        ports = []
        for cport, binds in (host.get("PortBindings") or {}).items():
            for b in binds or []:
                ports.append("%s:%s" % (b.get("HostPort", ""), cport.split("/")[0]) + ("/udp" if cport.endswith("/udp") else ""))
        if ports:
            lines.append("    ports:")
            lines += ['      - "%s"' % p for p in ports]
        binds = [b for b in (host.get("Binds") or []) if b]
        if binds:
            lines.append("    volumes:")
            lines += ["      - %s" % b for b in binds]
        rc, imgenv = docker("image", "inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", image, timeout=30)
        default = set(imgenv.splitlines()) if rc == 0 else set()
        env = [e for e in (cfg.get("Env") or []) if "=" in e and e not in default]
        if env:
            lines.append("    environment:")
            for e in env:
                k, v = e.split("=", 1)
                lines.append("      %s: %s" % (k, json.dumps(v)))
    return "\n".join(lines) + "\n"


class MusicDownloaderStack(StackStep):
    """Downtify (songs) and MeTube (videos) as one Portainer stack called music-downloader. Containers started by hand are moved into it with their settings."""
    parallel = False

    def applies(self):
        return not Mode.existing

    def detail(self):
        return "Downtify and MeTube run in the Portainer stack"

    def probe(self):
        if not stack_up(self.name):
            return "todo"
        if not Portainer.alive() or not Portainer.endpoint_id():
            return "done"
        return "done" if Portainer.stack_named(self.name) else "todo"

    def run(self):
        if not Opt.dry:
            unlock_storage_folders()
            for p in ("/mnt/storage/music", "/mnt/storage/videos"):
                if not os.path.isdir(P(p)):
                    os.makedirs(P(p), exist_ok=True)
                    chown(P(p), Ctx.uid, Ctx.gid)
        old = {} if Opt.dry else md_old_containers()
        if not old:
            return StackStep.run(self)
        if Runtime.unattended:
            raise NeedsPerson("Moving the running Downtify and MeTube into Portainer restarts them, so it waits for `sudo homelab-setup refresh`.")
        text = md_compose_from_files(old) or md_compose_from_inspect(old)
        if not text:
            raise Abort("Downtify and MeTube were started by hand and their settings could not be read, so nothing was changed. "
                        "In Portainer, Stacks > Add stack, name it music-downloader and paste the compose file you used.")
        missing = [n for n in MD_NAMES if n not in old]
        if missing:
            ours = stack_text(self.name)
            part = re.search(r"(?ms)^  %s:\n.*?(?=^  \w|\Z)" % missing[0], ours)
            if part:
                text = text.rstrip("\n") + "\n" + part.group(0).rstrip("\n") + "\n"
        prepull(images_in(text))
        os.makedirs(SECRET_DIR, exist_ok=True)
        write_file(MD_BACKUP, text, 0o600)
        log("music-downloader: moving %s into a Portainer stack" % ", ".join(old))
        rc, txt = docker("rm", "-f", *old.keys(), timeout=120)
        if rc != 0:
            raise Abort("The old containers could not be removed (%s), so nothing was changed." % txt.strip()[-160:])
        try:
            Portainer.deploy(self.name, text, [])
            wait_for(lambda: stack_up(self.name), "the music-downloader containers to start", self.wait)
        except Abort as e:
            docker("compose", "-p", self.name, "-f", MD_BACKUP, "up", "-d", timeout=300)
            raise Abort("Moving Downtify and MeTube into Portainer did not work (%s). They were started again the way they were." % str(e)[:200]) from None
        good("Downtify and MeTube are now a Portainer stack (their folders and settings are unchanged)")


register(MusicDownloaderStack("music-downloader", ("portainer-env", "folders"), "Downtify and MeTube stack (music and video downloads)"))


DT_DEFAULT_USER, DT_DEFAULT_PASS = "admin", "downtify"


def dt_username():
    """The install name as a Downtify username (3 to 32 letters, digits, dots, dashes or underscores); `admin` when nothing usable is left."""
    name = re.sub(r"[^A-Za-z0-9._-]", "", Ctx.admin or "")[:32]
    return name if len(name) >= 3 else DT_DEFAULT_USER


def dt_login(user, password):
    """Sign in to Downtify. Returns (status, user record, cookie header). Status 0 means no answer."""
    st, js, hd = http("POST", url("downtify", "/api/auth/login"), body={"username": user, "password": password}, timeout=20)
    m = re.search(r"downtify_session=([^;,\s]+)", str(hd.get("Set-Cookie", ""))) if st == 200 else None
    rec = js.get("user") if st == 200 and isinstance(js, dict) else None
    return st, rec, ("downtify_session=" + m.group(1)) if m else ""


def dt_state():
    """Where Downtify's sign-in stands: `none` (not running or no accounts), `default` (still the first admin and password), `set` (changed) or `off` (sign-in turned off)."""
    st, js, _ = http("GET", url("downtify", "/api/auth/status"), timeout=10)
    if st != 200 or not isinstance(js, dict):
        return "none"
    if js.get("auth_disabled") or js.get("require_sign_in") is False:
        return "off"
    st, _, _ = dt_login(DT_DEFAULT_USER, DT_DEFAULT_PASS)
    return "default" if st == 200 else "set"


@step
class DowntifyLogin(Step):
    """Give Downtify the name and password chosen at install. A new Downtify only has the account admin with the password downtify, so its first admin account is renamed and given the install password."""
    id, group, title = "downtify-login", "Logins and keys", "Downtify sign-in set to your name and the admin password"
    needs = ("stack-music-downloader",)
    optional = True

    def applies(self):
        return not Mode.existing

    def probe(self):
        if not stack_up("music-downloader"):
            return "todo"
        return "todo" if dt_state() == "default" else "done"

    def help(self):
        return ("Open %s and sign in as admin with the password downtify. Then change the name and password in Settings, Users and General, Account. "
                "If the password was changed and forgotten, run:  docker exec downtify python main.py auth-reset" % url("downtify"))

    def run(self):
        if Opt.dry:
            out("      would rename Downtify's first account (admin) to %s and give it the admin password" % dt_username())
            return
        wait_for(lambda: dt_state() != "none", "Downtify to answer", 120)
        pw = need_password("to set the Downtify sign-in")
        user = dt_username()
        if dt_login(user, pw)[0] == 200:
            return
        st, rec, cookie = dt_login(DT_DEFAULT_USER, DT_DEFAULT_PASS)
        if st != 200 or not rec or not cookie:
            raise Abort("Downtify's sign-in was changed by hand, so it was left alone. %s" % self.help())
        body = {"username": user, "password": pw}
        st, js, _ = http("PATCH", url("downtify", "/api/users/%s" % rec["id"]), body=body, headers={"Cookie": cookie}, timeout=30)
        if st == 400 and user != DT_DEFAULT_USER:
            st, js, _ = http("PATCH", url("downtify", "/api/users/%s" % rec["id"]), body={"password": pw}, headers={"Cookie": cookie}, timeout=30)
            if st == 200:
                warn("Downtify already has an account called %s, so the first account keeps the name admin and now has the admin password." % user)
        if st != 200:
            raise Abort("Downtify refused the new sign-in (HTTP %s): %s" % (st, str(js)[:200]))
