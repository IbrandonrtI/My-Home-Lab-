# ================================================================ Downtify and MeTube (the music-downloader stack)
# On a new machine the two containers are started from a Portainer stack. On a machine where they were started by hand (docker compose in a
# terminal), Portainer shows them as "created outside of Portainer" with limited control. Then the same containers are moved into a Portainer
# stack: their settings are read from the machine, the old containers are removed (the folders and everything in them stay) and Portainer
# starts them again with those same settings.
MD_BACKUP = SECRET_DIR + "/music-downloader-before.yaml"       # the old settings, kept in case the move has to be undone
MD_NAMES = ("downtify", "metube")


def md_old_containers():
    """The Downtify and MeTube containers that exist right now (hand-made: the stack is not in Portainer yet), as {name: inspect data}."""
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
    """The settings of the old compose project, read with `docker compose config` from the file it was started from ('' when that is not possible)."""
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
            return re.sub(r"(?m)^name:.*\n", "", text, count=1)      # (Portainer gives the project its name: the stack's)
    return ""


def md_compose_from_inspect(old):
    """A compose file written from what the running containers were started with (image, ports, folders, settings, user)."""
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
    """Downtify (songs) and MeTube (videos) as one Portainer stack called music-downloader."""

    def applies(self):
        return not Mode.existing

    def detail(self):
        return "Downtify and MeTube run in the Portainer stack"

    def probe(self):
        if not stack_up(self.name):
            return "todo"
        if not Portainer.alive() or not Portainer.endpoint_id():
            return "done"      # Portainer cannot be asked right now: the running containers are left alone
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
        # Downtify or MeTube is running already, but not as a Portainer stack: move it, with its own settings.
        if Runtime.unattended:
            raise NeedsPerson("Moving the running Downtify and MeTube into Portainer restarts them, so it waits for `sudo homelab-setup refresh`.")
        text = md_compose_from_files(old) or md_compose_from_inspect(old)
        if not text:
            raise Abort("Downtify and MeTube were started by hand and their settings could not be read, so nothing was changed. "
                        "In Portainer, Stacks > Add stack, name it music-downloader and paste the compose file you used.")
        missing = [n for n in MD_NAMES if n not in old]
        if missing:       # only one of the two exists: the other one comes from the repository's file, with its default folders
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
            docker("compose", "-p", self.name, "-f", MD_BACKUP, "up", "-d", timeout=300)      # put them back the way they were
            raise Abort("Moving Downtify and MeTube into Portainer did not work (%s). They were started again the way they were." % str(e)[:200]) from None
        good("Downtify and MeTube are now a Portainer stack (their folders and settings are unchanged)")


register(MusicDownloaderStack("music-downloader", ("portainer-env", "folders"), "Downtify and MeTube stack (music and video downloads)"))
