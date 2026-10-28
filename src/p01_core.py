#!/usr/bin/env python3
# homelab-setup - build a Linux machine into the home lab from the GitHub repo.
#
#   sudo homelab-setup                 show the checklist (what is done, what is left)
#   sudo homelab-setup install         set the whole lab up (asks first, safe to run again)
#   sudo homelab-setup install --dry-run   show what it WOULD do, change nothing
#   sudo homelab-setup refresh         re-check everything, continue what is now possible
#   sudo homelab-setup fill            walk through the keys and logins that need you
#   sudo homelab-setup done STEP       mark a by-hand step as done   (skip STEP: not wanted)
#   sudo homelab-setup secrets         show the generated passwords (once, then keep them in a password manager)
#   homelab-setup progress | version | help
#
# It never formats or changes a drive. It never stores the password you type.
# Python 3 standard library only.

import atexit
import base64
import getpass
import hashlib
import json
import os
import pwd
import re
import secrets as pysecrets
import shutil
import socket
import string
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0"

# ---------------------------------------------------------------- paths
ROOT = os.environ.get("HLS_ROOT", "").rstrip("/")          # tests point this at a fake root
FAKE = os.environ.get("HLS_FAKE") == "1"                    # tests: no root check, no chown
HOST_OVERRIDE = os.environ.get("HLS_HOST", "")              # tests: where the services answer


def P(path):
    """Path of `path` inside the machine's root folder (the real root, or the fake one under test)."""
    return ROOT + path


STATE_DIR = P("/var/lib/homelab-setup")
STATE_FILE = STATE_DIR + "/state.json"
PROGRESS_DIR = P("/var/lib/homelab")
PROGRESS_FILE = PROGRESS_DIR + "/setup-progress"
BOOT_GRACE = 600      # seconds after a boot during which scheduled checks wait (apps are still starting)
SECRET_DIR = P("/root/.homelab-setup")
SECRET_FILE = SECRET_DIR + "/secrets.env"
LOG_FILE = P("/var/log/homelab-setup.log")

# ---------------------------------------------------------------- the nine stacks
# name -> (file in stacks/, containers that must run)
STACKS = {
    "adguard": ("adguard.yaml", ["adguardhome"]),
    "beszel": ("beszel.yaml", ["beszel"]),
    "netdata": ("netdata.yaml", ["netdata-netdata-1"]),
    "speedtest-tracker": ("speedtest-tracker.yaml", ["speedtest-tracker"]),
    "filebrowser": ("filebrowser.yaml", ["filebrowser-filebrowser-1"]),
    "immich": ("immich.yaml", ["immich_server", "immich_postgres", "immich_machine_learning", "immich_redis"]),
    "nextcloud": ("nextcloud.yaml", ["nextcloud", "nextcloud_db", "nextcloud_redis", "nextcloud_cron"]),
    "homepage": ("homepage.yaml", ["homepage"]),
    "beszel-agent": ("beszel-agent.yaml", ["beszel-agent"]),
}
STACK_ORDER = ["adguard", "beszel", "netdata", "speedtest-tracker", "filebrowser",
               "immich", "nextcloud", "homepage", "beszel-agent"]

# local port of each service, and the HTTPS port Tailscale Serve uses for it
PORTS = {"homepage": 3001, "portainer": 9000, "immich": 2283, "beszel": 8090, "adguard": 3000,
         "nextcloud": 8082, "filebrowser": 8081, "speedtest": 8088, "netdata": 19999}
SERVE = [(1000, "homepage"), (1001, "portainer"), (1002, "immich"), (1003, "beszel"), (1004, "adguard"),
         (1005, "nextcloud"), (1006, "filebrowser"), (1007, "speedtest"), (1008, "netdata")]

# The placeholders the repository files use, replaced by this machine's values (see subst).
PH_USER = "your-username"
PH_FQDN = "pc.your-tailnet.ts.net"
PH_LAN = "192.168.X.X"
PH_KEY = "your-own-key"
PH_MAIL = "your-email@example.com"

# Optional: the values of an EARLIER server, for restoring a backup made there. The repository itself holds none.
# Set HOMELAB_OLD_USER, HOMELAB_OLD_LAN and HOMELAB_OLD_FQDN (for example pc.example.ts.net) before running the installer.
OLD_USER = os.environ.get("HOMELAB_OLD_USER", "")
OLD_LAN = os.environ.get("HOMELAB_OLD_LAN", "")
OLD_FQDN = os.environ.get("HOMELAB_OLD_FQDN", "")
OLD_TAILNET = OLD_FQDN.split(".", 1)[1] if "." in OLD_FQDN else ""

# ---------------------------------------------------------------- look (same style as the homelab command)
_tty = ((sys.stdout.isatty() or os.environ.get("HLS_COLOR") == "1")          # HLS_COLOR=1 forces colour (tests)
        and not os.environ.get("NO_COLOR") and os.environ.get("TERM", "dumb") != "dumb")
if _tty:
    B, D, G, Y, R, N = "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"
    C, U = "\033[1;36m", "\033[4;36m"          # commands (bold cyan) and links (underlined cyan)
else:
    B = D = G = Y = R = N = C = U = ""
_loc = (os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE") or os.environ.get("LANG") or "")
_utf = bool(re.search(r"utf-?8", _loc, re.I))
S_OK, S_TODO, S_BAD, S_WAIT, S_NA, S_RULE, S_DOT = (
    ("✓", "○", "✗", "·", "–", "─", "·") if _utf else ("+", "o", "x", ".", "-", "-", "-"))


def window_cols():
    """The real width of the window. The terminal itself is asked first: the COLUMNS variable is only a copy made
    when the shell started (and `sudo` passes it on), so it goes stale as soon as the window is resized.
    HLS_COLS forces a width (tests)."""
    forced = os.environ.get("HLS_COLS", "")
    if forced.isdigit():
        return int(forced)
    for stream in (sys.__stdout__, sys.__stderr__, sys.__stdin__):
        try:
            if stream is not None and stream.isatty():
                return os.get_terminal_size(stream.fileno()).columns
        except (OSError, ValueError):
            pass
    try:
        return int(os.environ.get("COLUMNS", "") or 80)
    except ValueError:
        return 80


def window_rows():
    """The real height of the window (0 when it cannot be found). HLS_ROWS forces a height (tests)."""
    forced = os.environ.get("HLS_ROWS", "")
    if forced.isdigit():
        return int(forced)
    for stream in (sys.__stdout__, sys.__stderr__, sys.__stdin__):
        try:
            if stream is not None and stream.isatty():
                return os.get_terminal_size(stream.fileno()).lines
        except (OSError, ValueError):
            pass
    return 0


def term_cols():
    """Width of the terminal in columns, at least 40."""
    return max(window_cols(), 40)


def live_cols():
    """The window width with no minimum: the status line must never be longer than the window."""
    return max(window_cols(), 1)


def out(msg=""):
    """Print one line, keeping the pinned progress bar on the bottom row."""
    with Live.lock:
        Live.sync()
        print(msg, flush=True)


def rule(title):
    """Print a section heading."""
    w = min(term_cols(), 76)
    n = max(w - len(title) - 8, 3)
    out("")
    out("  %s%s%s%s %s%s%s %s%s%s" % (D, S_RULE, S_RULE, N, B, title, N, D, S_RULE * n, N))
    out("")


NBSP = "\u00a0"
_MARK = re.compile(r"`([^`]+)`|(https?://[^\s)`]*[^\s).,;:`])")


def _protect(text):
    """Keep a `command` on one line: its spaces become non-breaking until the line is drawn."""
    return re.sub(r"`([^`]+)`", lambda m: "`" + m.group(1).replace(" ", NBSP) + "`", text)


def wrap(text, indent, width=None):
    """Wrap `text` to the terminal width with `indent` spaces in front of every line."""
    width = (width or min(term_cols(), 100)) - indent
    lines = []
    for para in _protect(text).split("\n"):
        if not para.strip():
            lines.append("")
            continue
        cur = ""
        for word in para.split(" "):
            if cur and len(cur) + 1 + len(word) > width:
                lines.append(cur)
                cur = word
            else:
                cur = (cur + " " + word) if cur else word
        lines.append(cur)
    return [" " * indent + l if l else "" for l in lines]


def mark(line, base=""):
    """Highlight `commands` and links in a finished line. `base` is the colour to return to afterwards."""
    def sub(m):
        if m.group(1) is not None:
            txt = m.group(1)
            return (N + C + txt + N + base) if _tty else "`" + txt + "`"
        return (N + U + m.group(2) + N + base) if _tty else m.group(2)
    return _MARK.sub(sub, line).replace(NBSP, " ")


def styled(text, indent, base=""):
    """Wrap text and highlight commands and links. A paragraph that starts with "$ " is a command line,
    shown on its own line and never wrapped."""
    out_lines = []
    for para in text.split("\n"):
        if para.startswith("$ "):
            out_lines.append(" " * indent + "%s$%s %s%s%s" % (D, N, C, para[2:], N))
            continue
        for l in wrap(para, indent):
            out_lines.append((base + mark(l, base) + N) if base else mark(l))
    return out_lines


def say(msg, indent=2):
    """Print a plain message, wrapped and indented."""
    for l in styled(msg, indent):
        out(l)


def good(msg):
    """Print a message marked as done (green tick)."""
    out("  %s%s%s %s" % (G, S_OK, N, msg))


def warn(msg):
    """Print a message marked as a warning."""
    for i, l in enumerate(styled(msg, 4)):
        out(("  %s!%s " % (Y, N) + l[4:]) if i == 0 else l)


def bad(msg):
    """Print a message marked as a failure (red cross)."""
    for i, l in enumerate(styled(msg, 4)):
        out(("  %s%s%s " % (R, S_BAD, N) + l[4:]) if i == 0 else l)


def log(msg):
    """Append a line to the installer's log file, with the administrator password masked."""
    try:
        for word in [Runtime.password] + list(Runtime.hide):
            if word and len(word) >= 6:
                msg = msg.replace(word, "********")
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write("%s %s\n" % (time.strftime("%F %T"), msg))
    except OSError:
        pass


# ---------------------------------------------------------------- live progress line
def fmt_time(sec):
    """Seconds as a short text such as '45s' or '3m 10s'."""
    sec = int(sec)
    if sec < 60:
        return "%ds" % sec
    if sec < 3600:
        return "%dm %02ds" % (sec // 60, sec % 60)
    return "%dh %02dm" % (sec // 3600, (sec % 3600) // 60)


class Live:
    """The progress bar. On a real terminal the bottom row of the window is reserved for it (the way apt does it):
    a spinner, the step, a detail (for example which image is downloading), a bar for the whole install and the
    elapsed time. Everything else the installer prints scrolls above it, so the bar is always in the same place and
    never overlaps a message. The row is painted at an absolute position (cursor saved, row written, cursor put back,
    all in one write), so nothing depends on where the cursor is or on how the terminal re-wrapped earlier output.
    When the window changes size the reserved row is set up again for the new size.
    It is only used on a real terminal (HLS_LIVE=1 forces it for tests). When there is no terminal (a pipe, a log
    file) nothing is animated: each step prints a plain line instead."""
    lock = threading.RLock()
    MIN_ROWS = 8
    enabled = (((sys.stdout.isatty() and os.environ.get("TERM", "dumb") != "dumb") or os.environ.get("HLS_LIVE") == "1")
               and (os.environ.get("HLS_LIVE") == "1" or window_rows() >= MIN_ROWS))
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if _utf else "|/-\\"
    FULL, EMPTY = ("█", "░") if _utf else ("#", "-")
    active = False          # a step is running
    region = False          # the bottom row is reserved and the bar is painted there
    size = (0, 0)           # (rows, columns) the reserved row was set up for
    paused = 0              # >0 while a question or an external program owns the keyboard
    echo_saved = None       # terminal settings to put back (typing is not echoed while a step runs)
    title = ""
    note = ""
    t_step = 0.0
    t_all = None            # start of the whole run (for the total elapsed time)
    total = 0
    done = 0
    frame = 0
    thread = None
    stop = False
    own_clock = False       # show this step's own time, not the time of the whole run

    @classmethod
    def begin_run(cls, total):
        with cls.lock:
            cls.total, cls.done = total, 0
            cls.t_all = time.time()

    @classmethod
    def elapsed_total(cls):
        return time.time() - cls.t_all if cls.t_all else 0.0

    @classmethod
    def begin(cls, title, own_clock=False):
        with cls.lock:
            cls.title, cls.note, cls.t_step = title, "", time.time()
            cls.own_clock = own_clock
            if not cls.enabled:
                return
            cls.active = True
            cls.stop = False
            cls._echo(False)
            if cls.thread is None or not cls.thread.is_alive():
                cls.thread = threading.Thread(target=cls._loop, daemon=True)
                cls.thread.start()
            cls.sync()
            cls.paint()

    @classmethod
    def end(cls):
        """A step is over: return how many seconds it took. The bar stays where it is until the next step."""
        with cls.lock:
            cls.active = False
            cls.own_clock = False
            cls.note = ""
            secs = time.time() - cls.t_step
            cls.paint()
            return secs

    @classmethod
    def set_note(cls, text):
        with cls.lock:
            cls.note = text
            cls.paint()

    @classmethod
    def advance(cls):
        with cls.lock:
            cls.done += 1
            cls.paint()

    @classmethod
    def _loop(cls):
        while not cls.stop:
            time.sleep(0.12)
            with cls.lock:
                if cls.active:
                    cls.frame += 1
                    cls.sync()
                    cls.paint()

    @classmethod
    def _echo(cls, on):
        """While a step runs, keys the person types are not printed (they would only add blank lines); the echo is put
        back for a question and when the run ends."""
        try:
            import termios
            if not sys.stdin.isatty():
                return
            if on:
                if cls.echo_saved is not None:
                    termios.tcsetattr(0, termios.TCSANOW, cls.echo_saved)
                    cls.echo_saved = None
            elif cls.echo_saved is None:
                saved = termios.tcgetattr(0)
                new = list(saved)
                new[3] &= ~termios.ECHO
                termios.tcsetattr(0, termios.TCSANOW, new)
                cls.echo_saved = saved
        except Exception:
            pass

    @classmethod
    def _size(cls):
        rows, cols = window_rows(), window_cols()
        if os.environ.get("HLS_LIVE") == "1" and not rows:
            rows = 24
        return rows, cols

    @classmethod
    def sync(cls):
        """Set the reserved row up (first time) or again (the window changed size)."""
        if not cls.enabled or not cls.active and not cls.region:
            return
        rows, cols = cls._size()
        if cls.region and (rows, cols) == cls.size:
            return
        if rows < cls.MIN_ROWS:                 # too small to keep a bar
            cls.close()
            return
        if cls.region and not cls.paused:
            # the window was resized: the terminal has moved the old bar row somewhere below the text; wipe whatever
            # is under the cursor (nothing but that old row can be there)
            sys.stdout.write("\r\033[J")
        # one blank line makes room (the screen scrolls if the cursor is on the last row), the cursor goes back up to
        # where it was (now never on the last row), and the scrolling area is set to every row but the last
        sys.stdout.write("\n\033[1A\0337\033[1;%dr\0338" % (rows - 1))
        sys.stdout.flush()
        cls.region = True
        cls.size = (rows, cols)

    @classmethod
    def paint(cls):
        if not cls.region:
            return
        rows, cols = cls.size
        if cols < 46:                              # too narrow for a readable bar: leave the row empty
            sys.stdout.write("\0337\033[%d;1H\033[2K\0338" % rows)
            sys.stdout.flush()
            return
        text = cls.line(cols)
        sys.stdout.write("\0337\033[%d;1H\033[?7l%s\033[K\033[?7h\0338" % (rows, text))
        sys.stdout.flush()

    @classmethod
    def close(cls):
        """Give the last row back and put the typing echo back. Safe to call any number of times."""
        with cls.lock:
            try:
                if cls.region:
                    rows = cls.size[0]
                    sys.stdout.write("\0337\033[r\033[%d;1H\033[2K\0338" % rows)
                    sys.stdout.flush()
            except Exception:
                pass
            cls.region = False
            cls.active = False
            cls._echo(True)

    @classmethod
    def line(cls, cols):
        """The bar, never longer than cols - 1 characters."""
        spin = cls.FRAMES[cls.frame % len(cls.FRAMES)]
        clock = fmt_time(time.time() - (cls.t_step if cls.own_clock or not cls.t_all else cls.t_all))
        n = min(cls.total, max(cls.done, 0)) if cls.total else 0
        count = ("%d of %d" % (n, cls.total)) if cls.total else ""
        if cols >= 46:
            width = 10 if cols < 90 else 14
            bar = ""
            bar_plain = ""
            if cls.total:
                filled = int(round(width * n / float(cls.total)))
                bar = "%s%s%s%s%s  %s" % (G, cls.FULL * filled, D, cls.EMPTY * (width - filled), N, count)
                bar_plain = " " * (width + 2 + len(count))
            tail_plain = ("   " + bar_plain if bar_plain else "") + "   " + clock
            tail = ("   " + bar if bar else "") + "   " + D + clock + N
            room = cols - 1 - len("  x ") - len(tail_plain)
            title = cls.title
            text = cls.note
            avail = room - len(title) - 4                 # what is left for the detail after "  . "
            if text and len(text) > avail:
                text = (text[:avail - 3] + "...") if avail >= 15 else ""
            note = ("  " + D + S_DOT + " " + text + N) if text else ""
            note_plain = ("  " + S_DOT + " " + text) if text else ""
            if len(title) > room:
                title = title[:max(room - 3, 1)] + "..."
            pad = " " * max(room - len(title) - len(note_plain), 0)
            return "  %s%s%s %s%s%s%s" % (C, spin if cls.active else S_OK, N, title, note, pad, tail)
        # a very narrow window: spinner, counter and time only (or just the spinner)
        short = "  %s %s %s" % (spin, count.replace(" of ", "/"), clock) if count else "  %s %s" % (spin, clock)
        if len(short) > cols - 1:
            short = "  " + spin
        return short[:max(cols - 1, 1)]

    class _Paused:
        def __enter__(self):
            with Live.lock:
                Live.paused += 1
                if Live.echo_saved is not None:
                    try:                               # keys typed while a step ran are not answers
                        import termios
                        termios.tcflush(0, termios.TCIFLUSH)
                    except Exception:
                        pass
                Live._echo(True)

        def __exit__(self, *a):
            with Live.lock:
                Live.paused -= 1
                if Live.region and not Live.paused:
                    Live._echo(False)

    @classmethod
    def pause(cls):
        """A question or another program has the keyboard for a while (the bar keeps running)."""
        return cls._Paused()


atexit.register(Live.close)                 # never leave the terminal with the last row reserved or its echo switched off


class Abort(Exception):
    """A step that cannot continue. The message is shown to the person."""


# ---------------------------------------------------------------- global switches
class Opt:
    """Command-line options."""
    dry = False
    yes = False
    backup = None
    no_restore = False
    force_existing = False
    all = False
    details = False
    repo = None


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


def apt_install(pkgs):
    """Install packages with apt without asking questions (does nothing in a dry run)."""
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    act(["apt-get", "install", "-y", "-q"] + list(pkgs), env=env, check=True, timeout=1800)


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


def sha(path):
    """SHA-256 of a file as hex text, or '' when it cannot be read."""
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except OSError:
        return ""


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


def _ask(prompt, default=""):
    """Read one answer from the terminal (or from standard input when it is not a terminal)."""
    try:
        if interactive():
            v = input("  %s%s: " % (prompt, (" [%s]" % default) if default else ""))
        else:
            sys.stdout.write("  %s%s: " % (prompt, (" [%s]" % default) if default else ""))
            sys.stdout.flush()
            v = stdin_line()
            if v == "":
                raise EOFError
            v = v.rstrip("\n")
            out("")
    except EOFError:
        raise Abort("An answer is required for: %s (no input was available)." % prompt) from None
    return v.strip() or default


def ask_secret(prompt):
    """Ask for a secret without echoing it."""
    with Live.pause():
        return _ask_secret(prompt)


def _ask_secret(prompt):
    """Read one secret from the terminal without echo."""
    try:
        if interactive():
            return getpass.getpass("  %s: " % prompt)
        sys.stdout.write("  %s: " % prompt)
        sys.stdout.flush()
        v = stdin_line()
        if v == "":
            raise EOFError
        out("")
        return v.rstrip("\n")
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
