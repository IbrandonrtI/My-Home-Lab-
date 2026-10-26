

# ================================================================ state, answers, secrets
class State:
    """Non-secret facts: the answers given, which one-time actions ran, and what was acknowledged."""
    data = {}

    @classmethod
    def load(cls):
        try:
            cls.data = json.loads(read_file(STATE_FILE, "{}") or "{}")
        except ValueError:
            cls.data = {}
        cls.data.setdefault("answers", {})
        cls.data.setdefault("ran", {})
        cls.data.setdefault("ack", {})
        cls.data.setdefault("skip", {})
        cls.data.setdefault("notes", {})

    readonly = False

    @classmethod
    def save(cls):
        if Opt.dry or cls.readonly:
            return
        os.makedirs(STATE_DIR, exist_ok=True)
        write_file(STATE_FILE, json.dumps(cls.data, indent=1, sort_keys=True) + "\n", 0o600)

    @classmethod
    def exists(cls):
        return os.path.exists(STATE_FILE)

    @classmethod
    def ran(cls, key):
        return key in cls.data["ran"]

    @classmethod
    def mark(cls, key):
        cls.data["ran"][key] = time.strftime("%F %T")
        cls.save()

    @classmethod
    def note(cls, key, text=None):
        if text is None:
            return cls.data["notes"].get(key, "")
        if text:
            cls.data["notes"][key] = text
        else:
            cls.data["notes"].pop(key, None)
        cls.save()


class Secrets:
    """The one root-only file (mode 600). Generated passwords and keys. Never the password you type."""
    vals = {}

    @classmethod
    def load(cls):
        cls.vals = {}
        for line in read_file(SECRET_FILE).splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                cls.vals[k.strip()] = v.strip()

    @classmethod
    def get(cls, key, default=""):
        return cls.vals.get(key, default)

    @classmethod
    def set(cls, key, value):
        cls.vals[key] = value
        cls.save()

    @classmethod
    def save(cls):
        if Opt.dry:
            return
        os.makedirs(SECRET_DIR, exist_ok=True)
        os.chmod(SECRET_DIR, 0o700)
        body = ["# homelab-setup secrets (root only, mode 600). Copy these into a password manager.",
                "# Never commit this file to a repository and never share it."]
        body += ["%s=%s" % (k, cls.vals[k]) for k in sorted(cls.vals)]
        write_file(SECRET_FILE, "\n".join(body) + "\n", 0o600)


class Runtime:
    """Lives only in memory while the program runs. The typed password is never written to a file by the installer."""
    password = None
    hide = []          # other secret words that must never reach the log file


def need_password(why):
    """Ask for the shared password once per run, when a step really needs it.
    Every typed password is checked: against the Portainer admin when that account exists, otherwise by typing it twice.
    (A typo here would quietly give some apps a different password than the others.)"""
    if Runtime.password:
        return Runtime.password
    out("")
    say("This step needs the admin password (%s). It is used for this run only and is not saved." % why)
    for _ in range(3):
        pw = ask_secret("Admin password")
        problem = password_problem(pw)
        if problem:
            warn(problem)
            continue
        if Portainer.admin_state() == 204:
            if not Portainer.login(pw):
                warn("That is not the password of the Portainer admin account (%s). Enter the password chosen at the start of the installation." % Ctx.admin)
                continue
        elif ask_secret("Type it again") != pw:
            warn("The two entries did not match.")
            continue
        Runtime.password = pw
        return pw
    raise Abort("No matching admin password was entered. Setup stopped before configuring any further logins. Run `sudo homelab-setup refresh` to try again.")


def password_problem(pw):
    """Why `pw` is not acceptable as the administrator password, or an empty text when it is fine."""
    if len(pw) < 12:
        return "The password must be at least 12 characters (Portainer requires it)."
    if not re.fullmatch(r"[A-Za-z0-9]+", pw):
        return "Use letters and digits only. Other characters can break the stack files and the Homepage configuration."
    return ""


# ================================================================ the machine
class Ctx:
    """Facts about THIS machine and the answers given at the start."""
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
        cls.os_like = info.get("ID_LIKE", "")
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
    """The normal user who ran sudo (the owner of the lab folders)."""
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
    """This machine's address on the home network."""
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
    """The router's address."""
    if os.environ.get("HLS_GATEWAY"):
        return os.environ["HLS_GATEWAY"]
    rc, txt = run(["ip", "-4", "route", "show", "default"])
    m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", txt)
    return m.group(1) if m else ""


def detect_tz():
    """The machine's time zone name."""
    rc, txt = run(["timedatectl", "show", "-p", "Timezone", "--value"])
    if rc == 0 and txt.strip():
        return txt.strip()
    return read_file(P("/etc/timezone")).strip() or "UTC"


WEATHER_CITY_DEFAULT = "New York"


def geocode_city(query):
    """Look a city up with Open-Meteo's free geocoding service (no key needed).
    Returns a list of {name, region, country, lat, lon} (empty = no such city), or None when the service cannot be reached."""
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


def weather_apply(text, w):
    """Put a chosen city (name, lat, lon) into the openmeteo block of widgets.yaml. Returns the new text, or None if the block is missing."""
    m = re.search(r"(openmeteo:)(.*?)(\n- |\Z)", text, re.S)
    if not m:
        return None
    block = m.group(2)
    label = w["name"].replace("\\", "").replace('"', "")
    block = re.sub(r"(\n\s+label:).*", lambda x: '%s "%s"' % (x.group(1), label), block, count=1)
    block = re.sub(r"(\n\s+latitude:).*", lambda x: "%s %.4f" % (x.group(1), w["lat"]), block, count=1)
    block = re.sub(r"(\n\s+longitude:).*", lambda x: "%s %.4f" % (x.group(1), w["lon"]), block, count=1)
    return text[:m.start(2)] + block + text[m.end(2):]


def ts_status():
    """Tailscale's status as a dict, or None when Tailscale is not installed or does not answer."""
    if not have("tailscale"):
        return None
    rc, txt = run(["tailscale", "status", "--json"], timeout=15)
    if rc != 0:
        return None
    try:
        return json.loads(txt)
    except ValueError:
        return None


# ================================================================ docker facts
def containers_running():
    """Names of the containers that are running."""
    rc, txt = docker("ps", "--format", "{{.Names}}", timeout=30)
    return set(txt.split()) if rc == 0 else set()


def containers_all():
    """Names of all containers, running or not."""
    rc, txt = docker("ps", "-a", "--format", "{{.Names}}", timeout=30)
    return set(txt.split()) if rc == 0 else set()


def stack_up(name):
    """True when every container of the stack is running."""
    need = STACKS[name][1]
    run_now = containers_running()
    return all(c in run_now for c in need)


def is_existing():
    """A machine that already runs the lab (set up by hand, not by the installer)."""
    if State.exists() and State.ran("install-started"):
        return False
    run_now = containers_running()
    n = sum(1 for s in STACKS if all(c in run_now for c in STACKS[s][1]))
    return n >= 7


def svc_host():
    """Address used to reach the services from this machine."""
    return HOST_OVERRIDE or Ctx.lan or "127.0.0.1"


def url(service, path=""):
    """Local web address of a service, with an optional path."""
    return "http://%s:%d%s" % (svc_host(), PORTS[service], path)


# ================================================================ rendering the repo's files for THIS machine
def subst(text):
    """Replace the original server's values (and the placeholders) with this machine's."""
    pairs = []
    if Ctx.fqdn:
        pairs += [(OLD_FQDN, Ctx.fqdn), (PH_FQDN, Ctx.fqdn)]
    if Ctx.tailnet:
        pairs += [(OLD_TAILNET, Ctx.tailnet)]
    if Ctx.lan:
        pairs += [(OLD_LAN, Ctx.lan), (PH_LAN, Ctx.lan)]
    pairs += [("/home/" + OLD_USER, Ctx.home), ("/home/" + PH_USER, Ctx.home)]
    for a, b in pairs:
        if a and a != "/home/":          # an empty old value (none set) must never match
            text = text.replace(a, b)
    text = re.sub(r'(PUID:\s*)"\d+"', r'\g<1>"%s"' % Ctx.uid, text)
    text = re.sub(r'(PGID:\s*)"\d+"', r'\g<1>"%s"' % Ctx.gid, text)
    return text


def repo_file(*parts):
    """Path of a file inside the repository the installer was started from."""
    return os.path.join(Ctx.repo, *parts)


def backup_mounted():
    """The backup pool (/mnt/backup) is a real mount point (a backup drive has been connected with `sudo drives`)."""
    return os.path.ismount(P("/mnt/backup")) or os.environ.get("HLS_MOUNTED_BACKUP") == "1"


DRIVE_NAMES_FILE = "/etc/homelab-drive-names"


def is_mount(path):
    """A real mount point (tests can mark folders as mounted with HLS_MOUNTED_DISKS="MAIN1 BACKUP1")."""
    return os.path.ismount(P(path)) or os.path.basename(path) in os.environ.get("HLS_MOUNTED_DISKS", "").split()


def pretty_size(nbytes):
    """Size as a drive is sold: 1 TB, 750 GB, 256 GB."""
    if nbytes >= 0.95e12:
        return "%g TB" % round(nbytes / 1e12, 1)
    return "%d GB" % round(nbytes / 1e9)


def clean_folder_name(text):
    """A name that is safe as a FileBrowser folder and inside a Docker volume line."""
    text = re.sub(r"[^\w .()+,-]", " ", text.replace("_", " "))
    return re.sub(r"\s+", " ", text).strip(" .-")


def drive_name_overrides():
    """Drive names chosen in /etc/homelab-drive-names ('LABEL=Name' per line)."""
    names = {}
    for line in read_file(P(DRIVE_NAMES_FILE)).splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if clean_folder_name(v):
                names[k.strip()] = clean_folder_name(v)
    return names


def disk_facts(mountpoint):
    """(model, size in bytes, file system label) of the physical drive behind a mount point; empty when unknown."""
    rc, src = run(["findmnt", "-n", "-o", "SOURCE", "--target", mountpoint], timeout=15)
    src = src.strip().splitlines()[0].strip() if rc == 0 and src.strip() else ""
    if not src.startswith("/dev/"):
        return "", 0, ""
    label = run(["lsblk", "-no", "LABEL", src], timeout=15)[1].strip().splitlines()
    label = label[0].strip() if label else ""
    disk = ""
    rc, txt = run(["lsblk", "-nslo", "NAME,TYPE", src], timeout=15)
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "disk":
            disk = "/dev/" + parts[0]
            break
    model, size = "", 0
    if disk:
        rc, txt = run(["lsblk", "-dnbo", "MODEL,SIZE", disk], timeout=15)
        line = txt.strip().splitlines()[0].strip() if rc == 0 and txt.strip() else ""
        m = re.match(r"^(.*?)\s*(\d+)$", line)
        if m:
            model, size = m.group(1).strip(), int(m.group(2))
    return model, size, label


def drive_name(mountpoint, fallback, prefer_label=False):
    """The folder name for a drive: a name you chose (/etc/homelab-drive-names), else the drive's own name
    (its file system label for the boot drive, else the model and size), else the fallback."""
    base = os.path.basename(mountpoint.rstrip("/")) or "boot"
    over = drive_name_overrides()
    if base in over:
        return over[base]
    model, size, label = disk_facts(mountpoint)
    generic = re.fullmatch(r"(MAIN|BACKUP)\d*", label or "")
    if prefer_label and label and not generic and clean_folder_name(label):
        return clean_folder_name(label)
    if model:
        name = clean_folder_name("%s %s" % (model, pretty_size(size)) if size else model)
        if name:
            return name
    if label and not generic and clean_folder_name(label):
        return clean_folder_name(label)
    return fallback


def pool_drives(role):
    """Mount points of the drives that are connected for a role (main or backup), as /mnt/disks/MAIN1 ..."""
    import glob
    prefix = "MAIN" if role == "main" else "BACKUP"
    found = sorted(d[len(ROOT):] if ROOT and d.startswith(ROOT) else d for d in glob.glob(P("/mnt/disks/" + prefix + "[0-9]*")))
    found = [d for d in found if is_mount(d)]
    if found:
        return found
    # one plain drive mounted at the pool path (before it is converted into a pool), or the old single backup mount
    if role == "main":
        return ["/mnt/storage"] if os.path.ismount(P("/mnt/storage")) or os.environ.get("HLS_MOUNTED") == "1" else []
    return ["/mnt/backup"] if backup_mounted() else []


def unique_names(items):
    """items: [(mount point, name)] -> the same list, a duplicate name made different by adding the mount point's own name."""
    seen = {}
    for _, n in items:
        seen[n] = seen.get(n, 0) + 1
    return [(mp, n if seen[n] == 1 else "%s (%s)" % (n, os.path.basename(mp))) for mp, n in items]


def filebrowser_mounts():
    """(host folder, folder name inside FileBrowser) for this machine's drives, named after the drives themselves:
    the drive that holds the system, then main-storage/<drive> and backup-storage/<drive> for every connected drive."""
    boot = drive_name("/", "boot-drive", prefer_label=True)
    if boot in ("main-storage", "backup-storage"):
        boot += " (system)"
    m = [(Ctx.home + "/750GB_HDD", "/srv/" + boot)]
    for role, folder in (("main", "main-storage"), ("backup", "backup-storage")):
        drives = unique_names([(mp, drive_name(mp, os.path.basename(mp))) for mp in pool_drives(role)])
        if not drives and role == "main":
            m.append(("/mnt/storage/filebrowser", "/srv/main-storage"))   # no data drive yet: a share on the boot drive
        for mp, name in drives:
            m.append((mp, "/srv/%s/%s" % (folder, name)))
    return m


def filebrowser_volumes(text):
    """Replace the two drive folders of the original server's FileBrowser stack with this machine's drives."""
    m = re.search(r"(\n    volumes:\n)((?:      - .*(?:\n|$))+)", text)
    if not m or "/srv/hdd" not in m.group(2):
        return text          # the stack file was changed: leave it as it is
    keep = [l for l in m.group(2).splitlines() if "/srv/hdd" not in l and "/srv/750GB_HDD" not in l]
    new = ['      - "%s:%s"' % d for d in filebrowser_mounts()] + keep
    return text[:m.start(2)] + "\n".join(new) + "\n" + text[m.end(2):]


def stack_text(name):
    """The stack file for `name` with this machine's values filled in."""
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
    if name == "beszel-agent":
        text = re.sub(r"(\n\s*KEY:\s*)'[^']*'", lambda m: "%s'%s'" % (m.group(1), Secrets.get("BESZEL_KEY")), text)
        text = re.sub(r"(\n\s*TOKEN:\s*)\S+", lambda m: "%s%s" % (m.group(1), Secrets.get("BESZEL_TOKEN")), text)
    return text


def stack_env(name):
    """The variables Portainer needs for the stack, as (name, value) pairs."""
    if name == "immich":
        return [("UPLOAD_LOCATION", "/mnt/storage/immich"), ("DB_DATA_LOCATION", Ctx.home + "/immich/postgres"),
                ("TZ", Ctx.tz), ("IMMICH_VERSION", "release"), ("DB_PASSWORD", Secrets.get("DB_PASSWORD")),
                ("DB_USERNAME", "postgres"), ("DB_DATABASE_NAME", "immich")]
    if name == "nextcloud":
        return [("NC_ADMIN_USER", Ctx.admin), ("NC_ADMIN_PASSWORD", Runtime.password or ""),
                ("NC_DB_PASSWORD", Secrets.get("NC_DB_PASSWORD"))]
    return []


def images_in(text):
    """The image names used in a stack file."""
    imgs = []
    for m in re.finditer(r"^\s*image:\s*(\S+)", text, re.M):
        img = m.group(1).replace("${IMMICH_VERSION:-release}", "release")
        if img not in imgs:
            imgs.append(img)
    return imgs
