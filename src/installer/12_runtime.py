# ---------------------------------------------------------------- running commands
def run(args, input_text=None, timeout=None, check=False, env=None, quiet=False, shell=False):
    """Run a command. Returns (returncode, stdout+stderr). In dry-run mode, changing commands are not run."""
    shown = args if isinstance(args, str) else " ".join(args)
    log("RUN " + shown[:200])
    try:
        p = subprocess.run(args, input=input_text, capture_output=True, text=True, timeout=timeout,
                           env=env, shell=shell)
        text = (p.stdout or "") + (p.stderr or "")
        rc = p.returncode
    except FileNotFoundError:
        rc, text = 127, "command not found: %s" % (args if isinstance(args, str) else args[0])
    except subprocess.TimeoutExpired:
        rc, text = 124, "timed out after %ss: %s" % (timeout, shown[:80])
    if check and rc != 0:
        raise Abort("Command failed (%s): %s\n%s" % (rc, shown[:120], text.strip()[-600:]))
    return rc, text


def act(args, **kw):
    """Run a command that CHANGES the machine. Dry-run prints it instead."""
    if Opt.dry:
        out("      would run: %s" % (args if isinstance(args, str) else " ".join(args)))
        return 0, ""
    return run(args, **kw)


def have(cmd):
    """True when the command exists on this machine."""
    return shutil.which(cmd) is not None


def docker(*args, **kw):
    """Run a docker command and return (exit code, output). A docker command that hangs (a stuck Docker service)
    is stopped after 3 minutes instead of freezing the installer for ever."""
    kw.setdefault("timeout", 180)
    return run(["docker"] + list(args), **kw)


def docker_answers():
    """True when the Docker service answers a plain question within 30 seconds."""
    return docker("info", "--format", "{{.ServerVersion}}", timeout=30)[0] == 0


DOCKER_DOWN = ("Docker is not answering, so the apps cannot be reached or checked. Look at it with:\n"
               "      $ sudo systemctl status docker\n"
               "      $ sudo journalctl -u docker -n 40 --no-pager\n"
               "      Then run `sudo homelab-setup refresh` again.")


def apt_env():
    """The environment for apt commands: they must never stop to ask a question."""
    return dict(os.environ, DEBIAN_FRONTEND="noninteractive")


def apt_distro():
    """The name of this system's family in the Docker and Tailscale package addresses: debian or ubuntu (Mint counts as ubuntu)."""
    return "debian" if Ctx.os_id == "debian" else "ubuntu"


def apt_install(pkgs):
    """Install packages with apt without asking questions (does nothing in a dry run)."""
    act(["apt-get", "install", "-y", "-q"] + list(pkgs), env=apt_env(), check=True, timeout=1800)


# ---------------------------------------------------------------- files
def read_file(path, default=""):
    """Contents of a text file, or `default` when it cannot be read."""
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return default


def write_file(path, text, mode=None, owner=None):
    """Write a text file (atomically, with the given mode and owner); a dry run only says what would be written."""
    if Opt.dry:
        out("      would write: %s" % path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-hls"
    with open(tmp, "w") as f:
        f.write(text)
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, path)
    if owner:
        chown(path, *owner)


def write_bytes(path, data, mode=None, owner=None):
    """Write a binary file (atomically, with the given mode and owner); a dry run only says what would be written."""
    if Opt.dry:
        out("      would write: %s" % path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-hls"
    with open(tmp, "wb") as f:
        f.write(data)
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, path)
    if owner:
        chown(path, *owner)


def chown(path, uid, gid, recursive=False):
    """Change the owner of a path, and of everything under it when `recursive` is set."""
    if FAKE or Opt.dry:
        return
    try:
        if recursive and os.path.isdir(path):
            for dp, _dirs, fn in os.walk(path):
                os.chown(dp, uid, gid)
                for n in fn:
                    try:
                        os.chown(os.path.join(dp, n), uid, gid)
                    except OSError:
                        pass
        os.chown(path, uid, gid)
    except OSError:
        pass


def mkdirs(path, uid=None, gid=None, mode=0o755):
    """Create a folder and its parents with the given owner and mode."""
    if Opt.dry:
        if not os.path.isdir(path):
            out("      would create folder: %s" % path)
        return
    os.makedirs(path, exist_ok=True)
    try:
        os.chmod(path, mode)
    except OSError:
        pass
    if uid is not None:
        chown(path, uid, gid)


# ---------------------------------------------------------------- random values
ALNUM = string.ascii_letters + string.digits


def rand_alnum(n=24):
    """A random password of letters and digits."""
    return "".join(pysecrets.choice(ALNUM) for _ in range(n))


def rand_hex(n=24):
    """A random hex string of 2*n characters."""
    return pysecrets.token_hex(n)


def rand_app_key():
    """A random 32-byte application key in the 'base64:...' form Laravel apps expect."""
    return "base64:" + base64.b64encode(pysecrets.token_bytes(32)).decode()


# ---------------------------------------------------------------- HTTP
def http(method, url, body=None, headers=None, timeout=20, form=None, raw=False):
    """Returns (status, data, headers). status 0 = could not connect. data = parsed JSON, else text."""
    hdr = dict(headers or {})
    data = None
    if form is not None:
        boundary = "----hls" + rand_alnum(16)
        parts = []
        for k, v in form.items():
            parts.append("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v))
        parts.append("--%s--\r\n" % boundary)
        data = "".join(parts).encode()
        hdr["Content-Type"] = "multipart/form-data; boundary=%s" % boundary
    elif body is not None:
        data = json.dumps(body).encode()
        hdr.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", "replace")
            st, hd = r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace") if e.fp else ""
        st, hd = e.code, dict(e.headers or {})
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        return 0, str(e), {}
    if raw:
        return st, txt, hd
    try:
        return st, json.loads(txt), hd
    except ValueError:
        return st, txt, hd


def wait_for(fn, what, timeout=300, every=3, quiet=False):
    """Poll fn() until it returns something true."""
    end = time.time() + timeout
    n = 0
    while True:
        try:
            v = fn()
        except Abort:
            raise
        except Exception:
            v = None
        if v:
            if n and Live.active:
                Live.set_note("")
            return v
        if time.time() > end:
            raise Abort("Timed out after %d seconds waiting for %s." % (timeout, what))
        if not quiet and n == 0:
            if Live.active:
                Live.set_note("waiting for %s" % what)
            else:
                out("      waiting for %s ..." % what)
        n += 1
        time.sleep(every if not FAKE else 0.05)


# ---------------------------------------------------------------- questions
def interactive():
    """True when a person is typing at a terminal."""
    return sys.stdin.isatty()


def stdin_line():
    """Read one line from a pipe WITHOUT reading ahead, so a program we start (the restore tool) can read the rest."""
    buf = b""
    while True:
        ch = os.read(0, 1)
        if not ch:
            break
        buf += ch
        if ch == b"\n":
            break
    return buf.decode("utf-8", "replace")


def ask(prompt, default=""):
    """Ask a question; with --yes the default is used without asking."""
    if Opt.yes and default != "":
        return default
    with Live.pause():
        return _ask(prompt, default)


def _read_piped(label):
    """Show `label`, then read one answer from standard input when it is not a terminal (EOFError when there is none)."""
    sys.stdout.write(label)
    sys.stdout.flush()
    v = stdin_line()
    if v == "":
        raise EOFError
    out("")
    return v.rstrip("\n")


def _ask(prompt, default=""):
    """Read one answer from the terminal (or from standard input when it is not a terminal)."""
    label = "  %s%s: " % (prompt, (" [%s]" % default) if default else "")
    try:
        v = input(label) if interactive() else _read_piped(label)
    except EOFError:
        raise Abort("An answer is required for: %s (no input was available)." % prompt) from None
    return v.strip() or default


def ask_secret(prompt):
    """Ask for a secret without echoing it."""
    with Live.pause():
        return _ask_secret(prompt)


def _ask_secret(prompt):
    """Read one secret from the terminal without echo."""
    label = "  %s: " % prompt
    try:
        return getpass.getpass(label) if interactive() else _read_piped(label)
    except EOFError:
        raise Abort("An answer is required for: %s (no input was available)." % prompt) from None


def yesno(prompt, default=False):
    """Ask a yes/no question; --yes answers yes."""
    if Opt.yes:
        return True
    v = ask(prompt + (" [Y/n]" if default else " [y/N]"), "").lower()
    if v == "":
        return default
    return v in ("y", "yes")


def typed(word, prompt):
    """True when the person typed exactly `word` (used for the confirmations that cannot be undone)."""
    if Opt.yes:
        return True
    return ask(prompt).strip() == word
