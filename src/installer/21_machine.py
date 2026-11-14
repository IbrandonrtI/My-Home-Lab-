class Ctx:
    """Facts about this machine and the answers given at the start of the install."""
    user = uid = gid = home = ""
    lan = gateway = tz = hostname = ""
    admin = email = ""
    fqdn = tailnet = ts_id = ""
    repo = ""
    os_id = os_name = os_codename = os_version = ""

    @classmethod
    def detect(cls):
        a = State.data["answers"]
        cls.user = a.get("user") or detect_user()
        try:
            pw = pwd.getpwnam(cls.user)
            cls.uid, cls.gid, cls.home = pw.pw_uid, pw.pw_gid, pw.pw_dir
        except KeyError:
            cls.uid = cls.gid = 1000
            cls.home = "/home/" + cls.user
        if ROOT and not os.path.isabs(cls.home):
            cls.home = "/home/" + cls.user
        if FAKE:
            cls.uid, cls.gid, cls.home = 1000, 1000, "/home/" + cls.user
        cls.lan = a.get("lan") or detect_lan()
        cls.gateway = detect_gateway()
        cls.tz = a.get("tz") or detect_tz()
        cls.hostname = socket.gethostname()
        cls.admin = a.get("admin", "")
        cls.email = a.get("email", "")
        cls.repo = Opt.repo or State.data.get("repo") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.refresh_tailscale()
        cls.read_os()

    @classmethod
    def read_os(cls):
        info = {}
        for line in read_file(P("/etc/os-release")).splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                info[k] = v.strip().strip('"')
        cls.os_id = info.get("ID", "")
        cls.os_name = info.get("PRETTY_NAME", cls.os_id)
        cls.os_version = info.get("VERSION_ID", "")
        cls.os_codename = info.get("UBUNTU_CODENAME") or info.get("VERSION_CODENAME", "")

    @classmethod
    def refresh_tailscale(cls):
        js = ts_status()
        cls.fqdn = cls.tailnet = cls.ts_id = ""
        if js and js.get("BackendState") == "Running":
            me = js.get("Self") or {}
            cls.fqdn = (me.get("DNSName") or "").rstrip(".")
            cls.ts_id = me.get("ID", "")
            if cls.fqdn.count(".") >= 2:
                cls.tailnet = cls.fqdn.split(".", 1)[1]


def detect_user():
    if os.environ.get("HLS_USER"):
        return os.environ["HLS_USER"]
    u = os.environ.get("SUDO_USER")
    if u and u != "root":
        return u
    try:
        names = [p.pw_name for p in pwd.getpwall() if 1000 <= p.pw_uid < 60000 and os.path.isdir(p.pw_dir)]
    except Exception:
        names = []
    return names[0] if names else (os.environ.get("USER") or "root")


def detect_lan():
    if os.environ.get("HLS_LAN"):
        return os.environ["HLS_LAN"]
    rc, txt = run(["ip", "-4", "route", "get", "1.1.1.1"])
    m = re.search(r"\bsrc (\d+\.\d+\.\d+\.\d+)", txt)
    if m:
        return m.group(1)
    rc, txt = run(["hostname", "-I"])
    for tok in txt.split():
        if re.match(r"^(10|192\.168|172\.(1[6-9]|2\d|3[01]))\.", tok):
            return tok
    return ""


def detect_gateway():
    if os.environ.get("HLS_GATEWAY"):
        return os.environ["HLS_GATEWAY"]
    rc, txt = run(["ip", "-4", "route", "show", "default"])
    m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", txt)
    return m.group(1) if m else ""


def detect_tz():
    rc, txt = run(["timedatectl", "show", "-p", "Timezone", "--value"])
    if rc == 0 and txt.strip():
        return txt.strip()
    return read_file(P("/etc/timezone")).strip() or "UTC"


def geocode_city(query):
    base = os.environ.get("HLS_GEOCODE_API", "https://geocoding-api.open-meteo.com")
    st, js, _ = http("GET", base + "/v1/search?count=5&language=en&format=json&name=" + urllib.parse.quote(query), timeout=15)
    if st != 200 or not isinstance(js, dict):
        return None
    found = []
    for r in js.get("results") or []:
        try:
            found.append({"name": str(r["name"]), "region": str(r.get("admin1") or ""), "country": str(r.get("country") or ""),
                          "lat": float(r["latitude"]), "lon": float(r["longitude"])})
        except (KeyError, TypeError, ValueError):
            continue
    return found


def ip_location():
    """Find the time zone and city from the public IP address using a free lookup service; None when no service answers."""
    override = os.environ.get("HLS_IP_API")
    for base, kind in ([(override, "ipwho")] if override else [("https://ipwho.is", "ipwho"), ("https://ipapi.co", "ipapi")]):
        st, js, _ = http("GET", base + ("/" if kind == "ipwho" else "/json/"), timeout=8)
        if st != 200 or not isinstance(js, dict) or js.get("success") is False or js.get("error"):
            continue
        try:
            tz = js["timezone"]["id"] if isinstance(js.get("timezone"), dict) else str(js.get("timezone") or "")
            return {"tz": tz, "name": str(js["city"]), "region": str(js.get("region") or ""), "country": str(js.get("country") or js.get("country_name") or ""),
                    "lat": float(js["latitude"]), "lon": float(js["longitude"])}
        except (KeyError, TypeError, ValueError):
            continue
    return None


def weather_apply(text, w):
    m = re.search(r"(openmeteo:)(.*?)(\n- |\Z)", text, re.S)
    if not m:
        return None
    block = m.group(2)
    label = w["name"].replace("\\", "").replace('"', "")
    block = re.sub(r"(\n\s+label:).*", lambda x: '%s "%s"' % (x.group(1), label), block, count=1)
    block = re.sub(r"(\n\s+latitude:).*", lambda x: "%s %.4f" % (x.group(1), w["lat"]), block, count=1)
    block = re.sub(r"(\n\s+longitude:).*", lambda x: "%s %.4f" % (x.group(1), w["lon"]), block, count=1)
    return text[:m.start(2)] + block + text[m.end(2):]


def clock_apply(text, tz):
    m = re.search(r"(- datetime:)(.*?)(\n- |\Z)", text, re.S)
    if not m or not re.fullmatch(r"[A-Za-z0-9_+/-]{1,60}", tz or ""):
        return None
    block = m.group(2)
    if re.search(r"\n\s+timeZone:", block):
        block = re.sub(r"(\n\s+timeZone:).*", lambda x: "%s %s" % (x.group(1), tz), block, count=1)
    else:
        f = re.search(r"\n(\s+)format:[^\n]*", block)
        if f:
            block = block[:f.end()] + "\n%s  timeZone: %s" % (f.group(1), tz) + block[f.end():]
        else:
            block = block.rstrip("\n") + "\n    format:\n      timeZone: %s\n" % tz
    return text[:m.start(2)] + block + text[m.end(2):]


def ts_status():
    if not have("tailscale"):
        return None
    rc, txt = run(["tailscale", "status", "--json"], timeout=15)
    if rc != 0:
        return None
    try:
        return json.loads(txt)
    except ValueError:
        return None


def _container_names(*flags):
    rc, txt = docker("ps", *flags, "--format", "{{.Names}}", timeout=30)
    return set(txt.split()) if rc == 0 else set()


def containers_running():
    return _container_names()


def containers_starting():
    rc, txt = docker("ps", "--format", "{{.Names}}|{{.Status}}", timeout=30)
    if rc != 0:
        return set()
    return {line.split("|")[0] for line in txt.splitlines() if "|" in line and ("starting" in line.lower() or "restarting" in line.lower())}


def containers_all():
    return _container_names("-a")


def stack_up(name):
    need = STACKS[name][1]
    run_now = containers_running()
    return all(c in run_now for c in need)


def is_existing():
    if State.exists() and State.ran("install-started"):
        return False
    run_now = containers_running()
    n = sum(1 for s in STACKS if all(c in run_now for c in STACKS[s][1]))
    return n >= 7


def svc_host():
    return HOST_OVERRIDE or Ctx.lan or "127.0.0.1"


def url(service, path=""):
    return "http://%s:%d%s" % (svc_host(), PORTS[service], path)


def subst(text):
    """Replace the original server's values and the placeholders with this machine's values."""
    pairs = []
    if Ctx.fqdn:
        pairs += [(OLD_FQDN, Ctx.fqdn), (PH_FQDN, Ctx.fqdn)]
    if Ctx.tailnet:
        pairs += [(OLD_TAILNET, Ctx.tailnet)]
    if Ctx.lan:
        pairs += [(OLD_LAN, Ctx.lan), (PH_LAN, Ctx.lan)]
    pairs += [("/home/" + OLD_USER, Ctx.home), ("/home/" + PH_USER, Ctx.home)]
    for a, b in pairs:
        if a and a != "/home/":
            text = text.replace(a, b)
    text = re.sub(r'(PUID:\s*)"\d+"', r'\g<1>"%s"' % Ctx.uid, text)
    text = re.sub(r'(PGID:\s*)"\d+"', r'\g<1>"%s"' % Ctx.gid, text)
    return text


def repo_file(*parts):
    return os.path.join(Ctx.repo, *parts)


def stack_text(name):
    """The Compose file of a stack with this machine's values filled in."""
    fn = STACKS[name][0]
    text = read_file(repo_file("stacks", fn))
    if not text:
        raise Abort("The repository file stacks/%s is missing (looked in %s)." % (fn, Ctx.repo))
    text = subst(text)
    if name == "filebrowser":
        text = filebrowser_volumes(text)
    if name == "speedtest-tracker":
        key = Secrets.get("APP_KEY")
        text = re.sub(r'(APP_KEY:\s*)"[^"]*"', lambda m: '%s"%s"' % (m.group(1), key), text)
    if name == "navidrome":
        text = text.replace("/mnt/storage/music:/music:ro", "%s:/music:ro" % (music_folder() or "/mnt/storage/music"))
        text = text.replace('user: "1000:1000"', 'user: "%d:%d"' % (Ctx.uid, Ctx.gid))
    if name == "beszel-agent":
        text = re.sub(r"(\n\s*KEY:\s*)'[^']*'", lambda m: "%s'%s'" % (m.group(1), Secrets.get("BESZEL_KEY")), text)
        text = re.sub(r"(\n\s*TOKEN:\s*)\S+", lambda m: "%s%s" % (m.group(1), Secrets.get("BESZEL_TOKEN")), text)
    return text


MUSIC_FOLDER_NAMES = ("music", "Music", "downtify", "Downtify", "Downtify/music", "downtify/music", "media/music", "Media/Music", "downloads/music")


def music_folder():
    """Find the folder that holds the songs: the saved setting, the Downtify container's mount, then common names under the main storage."""
    forced = os.environ.get("HOMELAB_MUSIC_DIR") or read_file(P("/var/lib/homelab/music-dir")).strip()
    if forced:
        return forced if os.path.isdir(P(forced)) else ""
    rc, ps = run(["docker", "ps", "-a", "--format", "{{.Names}}|{{.Image}}"], timeout=20)
    for line in ps.splitlines():
        f = line.split("|")
        if rc == 0 and len(f) == 2 and "downtify" in line.lower():
            rc2, mounts = run(["docker", "inspect", f[0], "--format", "{{range .Mounts}}{{.Destination}}|{{.Source}}{{println}}{{end}}"], timeout=10)
            for m in mounts.splitlines():
                d = m.split("|", 1)
                if len(d) == 2 and re.search(r"music|download", d[0], re.I) and os.path.isdir(P(d[1])):
                    return d[1]
    for name in MUSIC_FOLDER_NAMES:
        if os.path.isdir(P("/mnt/storage/" + name)):
            return "/mnt/storage/" + name
    return ""


def stack_env(name):
    """The variables Portainer needs for a stack, as (name, value) pairs."""
    if name == "immich":
        return [("UPLOAD_LOCATION", "/mnt/storage/immich"), ("DB_DATA_LOCATION", Ctx.home + "/immich/postgres"),
                ("TZ", Ctx.tz), ("IMMICH_VERSION", "release"), ("DB_PASSWORD", Secrets.get("DB_PASSWORD")),
                ("DB_USERNAME", "postgres"), ("DB_DATABASE_NAME", "immich")]
    if name == "nextcloud":
        return [("NC_ADMIN_USER", Ctx.admin), ("NC_ADMIN_PASSWORD", Runtime.password or ""),
                ("NC_DB_PASSWORD", Secrets.get("NC_DB_PASSWORD"))]
    if name == "navidrome":
        return [("LASTFM_APIKEY", Secrets.get("LASTFM_APIKEY")), ("LASTFM_SECRET", Secrets.get("LASTFM_SECRET")),
                ("NAVIDROME_AGENTS", NAVIDROME_AGENTS_WITH if audiomuse_wanted() else "")]
    if name == "audiomuse":
        return [("TZ", Ctx.tz), ("AUDIOMUSE_DB_PASSWORD", Secrets.get("AUDIOMUSE_DB_PASSWORD")),
                ("AUDIOMUSE_NAVIDROME_URL", "http://%s:%d" % (svc_host(), PORTS["navidrome"])),
                ("AUDIOMUSE_NAVIDROME_USER", AUDIOMUSE_ND_USER), ("AUDIOMUSE_NAVIDROME_PASSWORD", Secrets.get("AUDIOMUSE_ND_PASSWORD")),
                ("AUDIOMUSE_USER", Ctx.admin), ("AUDIOMUSE_PASSWORD", Secrets.get("AUDIOMUSE_PASSWORD")),
                ("AUDIOMUSE_TOKEN", Secrets.get("AUDIOMUSE_TOKEN")), ("AUDIOMUSE_JWT_SECRET", Secrets.get("AUDIOMUSE_JWT_SECRET")),
                ("AUDIOMUSE_MEM", audiomuse_mem()), ("AUDIOMUSE_CPUS", str(audiomuse_cpus()))]
    if name == "navilist":
        return [("TZ", Ctx.tz), ("NAVILIST_NAVIDROME_URL", "http://%s:%d" % (svc_host(), PORTS["navidrome"])),
                ("NAVILIST_NAVIDROME_USER", NAVILIST_ND_USER), ("NAVILIST_NAVIDROME_PASSWORD", Secrets.get("NAVILIST_ND_PASSWORD")),
                ("NAVILIST_LASTFM_KEY", Secrets.get("LASTFM_APIKEY")), ("NAVILIST_LASTFM_USER", Secrets.get("NAVILIST_LASTFM_USER")),
                ("NAVILIST_LB_TOKEN", Secrets.get("NAVILIST_LB_TOKEN")), ("NAVILIST_LB_USER", Secrets.get("NAVILIST_LB_USER"))]
    return []


AUDIOMUSE_ND_USER = "audiomuse"
AUDIOMUSE_SECRETS = {"AUDIOMUSE_DB_PASSWORD": lambda: rand_alnum(28), "AUDIOMUSE_ND_PASSWORD": lambda: rand_alnum(28),
                     "AUDIOMUSE_PASSWORD": lambda: rand_alnum(20), "AUDIOMUSE_TOKEN": lambda: rand_hex(24),
                     "AUDIOMUSE_JWT_SECRET": lambda: rand_hex(32)}
NAVIDROME_AGENTS_WITH = "audiomuseai,deezer,lastfm,listenbrainz"


NAVILIST_ND_USER = "navilist"


def navilist_wanted():
    return bool(State.data.get("navilist")) and not Mode.existing


def audiomuse_wanted():
    return bool(State.data.get("audiomuse")) and not Mode.existing


def ram_gb():
    try:
        kb = int(os.environ.get("HLS_RAM_KB") or [l for l in open("/proc/meminfo") if l.startswith("MemTotal:")][0].split()[1])
    except (OSError, IndexError, ValueError):
        return 0.0
    return kb / 1024 / 1024


def audiomuse_mem_suggest(total=None):
    total = ram_gb() if total is None else total
    return "2g" if total < 5.5 else "3g" if total < 11 else "6g" if total < 24 else "8g"


def audiomuse_mem():
    return State.data.get("audiomuse_mem") or audiomuse_mem_suggest()


def audiomuse_cpus():
    return max(1, int(os.environ.get("HLS_CPUS") or os.cpu_count() or 2) - 1)


def images_in(text):
    imgs = []
    for m in re.finditer(r"^\s*image:\s*(\S+)", text, re.M):
        img = m.group(1).replace("${IMMICH_VERSION:-release}", "release")
        if img not in imgs:
            imgs.append(img)
    return imgs
