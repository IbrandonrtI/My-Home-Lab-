_tty = ((sys.stdout.isatty() or os.environ.get("HLS_COLOR") == "1")
        and not os.environ.get("NO_COLOR") and os.environ.get("TERM", "dumb") != "dumb")
if _tty:
    B, D, G, Y, R, N = "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"
    C, U = "\033[1;36m", "\033[4;36m"
else:
    B = D = G = Y = R = N = C = U = ""
_loc = (os.environ.get("LC_ALL") or os.environ.get("LC_CTYPE") or os.environ.get("LANG") or "")
_utf = bool(re.search(r"utf-?8", _loc, re.I))
S_OK, S_TODO, S_BAD, S_WAIT, S_RULE, S_DOT = (
    ("✓", "○", "✗", "·", "─", "·") if _utf else ("+", "o", "x", ".", "-", "-"))


def _terminal_size():
    for stream in (sys.__stdout__, sys.__stderr__, sys.__stdin__):
        try:
            if stream is not None and stream.isatty():
                return os.get_terminal_size(stream.fileno())
        except (OSError, ValueError):
            pass
    return None


def window_cols():
    """Width of the terminal window, read from the terminal itself because the COLUMNS variable is stale after a resize."""
    forced = os.environ.get("HLS_COLS", "")
    if forced.isdigit():
        return int(forced)
    size = _terminal_size()
    if size:
        return size.columns
    try:
        return int(os.environ.get("COLUMNS", "") or 80)
    except ValueError:
        return 80


def window_rows():
    forced = os.environ.get("HLS_ROWS", "")
    if forced.isdigit():
        return int(forced)
    size = _terminal_size()
    return size.lines if size else 0


def term_cols():
    return max(window_cols(), 40)


def out(msg=""):
    with Live.lock:
        Live.sync()
        print(msg, flush=True)


def rule(title):
    w = min(term_cols(), 76)
    n = max(w - len(title) - 8, 3)
    out("")
    out("  %s%s%s%s %s%s%s %s%s%s" % (D, S_RULE, S_RULE, N, B, title, N, D, S_RULE * n, N))
    out("")


NBSP = "\u00a0"
_MARK = re.compile(r"`([^`]+)`|(https?://[^\s)`]*[^\s).,;:`])")


def _protect(text):
    return re.sub(r"`([^`]+)`", lambda m: "`" + m.group(1).replace(" ", NBSP) + "`", text)


def wrap(text, indent, width=None):
    """Wrap text to the terminal width, indenting every line."""
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
    def sub(m):
        if m.group(1) is not None:
            txt = m.group(1)
            return (N + C + txt + N + base) if _tty else "`" + txt + "`"
        return (N + U + m.group(2) + N + base) if _tty else m.group(2)
    return _MARK.sub(sub, line).replace(NBSP, " ")


def styled(text, indent, base=""):
    out_lines = []
    for para in text.split("\n"):
        if para.startswith("$ "):
            out_lines.append(" " * indent + "%s$%s %s%s%s" % (D, N, C, para[2:], N))
            continue
        for l in wrap(para, indent):
            out_lines.append((base + mark(l, base) + N) if base else mark(l))
    return out_lines


def say(msg, indent=2):
    for l in styled(msg, indent):
        out(l)


def good(msg):
    out("  %s%s%s %s" % (G, S_OK, N, msg))


def _flagged(flag, msg):
    for i, l in enumerate(styled(msg, 4)):
        out(("  %s " % flag + l[4:]) if i == 0 else l)


def warn(msg):
    _flagged("%s!%s" % (Y, N), msg)


def bad(msg):
    _flagged("%s%s%s" % (R, S_BAD, N), msg)


def log(msg):
    """Append a line to the installer log with the admin password masked."""
    try:
        for word in [Runtime.password] + list(Runtime.hide):
            if word and len(word) >= 6:
                msg = msg.replace(word, "********")
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write("%s %s\n" % (time.strftime("%F %T"), msg))
    except OSError:
        pass


def fmt_time(sec):
    sec = int(sec)
    if sec < 60:
        return "%ds" % sec
    if sec < 3600:
        return "%dm %02ds" % (sec // 60, sec % 60)
    return "%dh %02dm" % (sec // 3600, (sec % 3600) // 60)


class Live:
    """Progress display: reserves the bottom row of the terminal for the current step, a bar for the whole install and the elapsed time."""
    lock = threading.RLock()
    MIN_ROWS = 8
    enabled = (((sys.stdout.isatty() and os.environ.get("TERM", "dumb") != "dumb") or os.environ.get("HLS_LIVE") == "1")
               and (os.environ.get("HLS_LIVE") == "1" or window_rows() >= MIN_ROWS))
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if _utf else "|/-\\"
    FULL, EMPTY = ("█", "░") if _utf else ("#", "-")
    active = False
    region = False
    size = (0, 0)
    paused = 0
    echo_saved = None
    title = ""
    note = ""
    t_step = 0.0
    t_all = None
    total = 0
    done = 0
    frame = 0
    thread = None
    stop = False
    own_clock = False

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
        """Turn keyboard echo off while a step runs and back on for questions and at the end."""
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
        if not cls.enabled or not cls.active and not cls.region:
            return
        rows, cols = cls._size()
        if cls.region and (rows, cols) == cls.size:
            return
        if rows < cls.MIN_ROWS:
            cls.close()
            return
        if cls.region and not cls.paused:
            sys.stdout.write("\r\033[J")
        sys.stdout.write("\n\033[1A\0337\033[1;%dr\0338" % (rows - 1))
        sys.stdout.flush()
        cls.region = True
        cls.size = (rows, cols)

    @classmethod
    def paint(cls):
        if not cls.region:
            return
        rows, cols = cls.size
        if cols < 46:
            sys.stdout.write("\0337\033[%d;1H\033[2K\0338" % rows)
            sys.stdout.flush()
            return
        text = cls.line(cols)
        sys.stdout.write("\0337\033[%d;1H\033[?7l%s\033[K\033[?7h\0338" % (rows, text))
        sys.stdout.flush()

    @classmethod
    def close(cls):
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
            avail = room - len(title) - 4
            if text and len(text) > avail:
                text = (text[:avail - 3] + "...") if avail >= 15 else ""
            note = ("  " + D + S_DOT + " " + text + N) if text else ""
            note_plain = ("  " + S_DOT + " " + text) if text else ""
            if len(title) > room:
                title = title[:max(room - 3, 1)] + "..."
            pad = " " * max(room - len(title) - len(note_plain), 0)
            return "  %s%s%s %s%s%s%s" % (C, spin if cls.active else S_OK, N, title, note, pad, tail)
        short = "  %s %s %s" % (spin, count.replace(" of ", "/"), clock) if count else "  %s %s" % (spin, clock)
        if len(short) > cols - 1:
            short = "  " + spin
        return short[:max(cols - 1, 1)]

    class _Paused:
        def __enter__(self):
            with Live.lock:
                Live.paused += 1
                if Live.echo_saved is not None:
                    try:
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
        return cls._Paused()


atexit.register(Live.close)
