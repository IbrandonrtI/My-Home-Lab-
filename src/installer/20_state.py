# ================================================================ state, answers, secrets
class State:
    """Non-secret facts: the answers given, which one-time actions ran, and what was acknowledged."""
    data = {}
    readonly = False

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

    lock = threading.RLock()        # (stacks are deployed at the same time, and each one may save its note)

    @classmethod
    def save(cls):
        if Opt.dry or cls.readonly:
            return
        with cls.lock:
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
    background = False      # True in the job that finishes the install by itself: nobody is there to type
    unattended = False      # True in the quiet scheduled run: a step that needs the password stays open, without a failure message
    hide = []          # other secret words that must never reach the log file


def need_password(why):
    """Ask for the shared password once per run, when a step really needs it.
    Every typed password is checked: against the Portainer admin when that account exists, otherwise by typing it twice.
    (A typo here would quietly give some apps a different password than the others.)"""
    if Runtime.password:
        return Runtime.password
    if Runtime.background or Runtime.unattended:
        raise NeedsPassword("This step needs the admin password, and the background job does not have it. Run `sudo homelab-setup finish` and type it there.")
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
