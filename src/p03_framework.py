

# ================================================================ Homepage config (text edits that keep your comments and order)
HP_CARDS = {   # card id -> (widget type, the fields that hold secrets)
    "adguard-card": ("adguard", ["username", "password"]),
    "tailscale-card": ("tailscale", ["deviceid", "key"]),
    "beszel-card": ("beszel", ["username", "password"]),
    "speedtest-card": ("speedtest", ["key"]),
    "portainer-card": ("portainer", ["env", "key"]),
    "filebrowser-card": ("filebrowser", ["username", "password"]),
    "immich-card": ("immich", ["key"]),
    "nextcloud-card": ("nextcloud", ["key"]),
}


def hp_dir():
    """The Homepage configuration folder."""
    return Ctx.home + "/homepage-config"


def hp_path(name="services.yaml"):
    """Path of one Homepage configuration file."""
    return P(hp_dir() + "/" + name)


def _indent(line):
    """Number of leading spaces of a line."""
    return len(line) - len(line.lstrip(" "))


def hp_ranges(lines, card_id):
    """Find a card in a services.yaml. Returns (card_start, card_end, widget_start, widget_end); widget_* may be None."""
    idx = None
    for i, l in enumerate(lines):
        if re.match(r"^\s*id:\s*%s\s*$" % re.escape(card_id), l):
            idx = i
            break
    if idx is None:
        return None
    id_ind = _indent(lines[idx])
    start = idx
    while start > 0 and not (re.match(r"^\s*- .+:\s*$", lines[start]) and _indent(lines[start]) < id_ind):
        start -= 1
    hind = _indent(lines[start])
    end = idx + 1
    while end < len(lines) and (not lines[end].strip() or _indent(lines[end]) > hind):
        end += 1
    while end > idx + 1 and not lines[end - 1].strip():
        end -= 1
    ws = we = None
    for i in range(start, end):
        if re.match(r"^\s*widget:\s*$", lines[i]):
            ws = i
            wi = _indent(lines[i])
            we = i + 1
            while we < end and (not lines[we].strip() or _indent(lines[we]) > wi):
                we += 1
            while we > ws + 1 and not lines[we - 1].strip():
                we -= 1
            break
    return start, end, ws, we


def hp_template_widget(card_id):
    "The widget block for a card, as the repository has it, adapted to this machine."
    text = subst(read_file(repo_file("homepage-config", "services.yaml")))
    lines = text.split("\n")
    r = hp_ranges(lines, card_id)
    if not r or r[2] is None:
        return []
    return lines[r[2]:r[3]]


def hp_get(card_id, field, path=None):
    """Value of a field of one Homepage card, or None when it is not there."""
    lines = read_file(path or hp_path()).split("\n")
    r = hp_ranges(lines, card_id)
    if not r or r[2] is None:
        return None
    for i in range(r[2], r[3]):
        m = re.match(r"^\s+%s:\s*(.*?)\s*$" % re.escape(field), lines[i])
        if m:
            return m.group(1).strip("\"'")
    return None


def hp_has_widget(card_id):
    """True when the card has a widget block."""
    lines = read_file(hp_path()).split("\n")
    r = hp_ranges(lines, card_id)
    return bool(r and r[2] is not None)


def is_placeholder(v):
    """True when a Homepage value is still a placeholder (empty, your-own-key, X.X ...)."""
    return v is None or v == "" or PH_KEY in v or PH_MAIL in v or "X.X" in v or v in ("yours",)


def hp_set_widget(card_id, values):
    """Write the widget block of a card: the repo's block, with `values` filled in."""
    path = hp_path()
    lines = read_file(path).split("\n")
    r = hp_ranges(lines, card_id)
    if not r:
        raise Abort("Card %s is not in %s." % (card_id, path))
    block = hp_template_widget(card_id)
    if not block:
        raise Abort("The repository has no widget block for %s." % card_id)
    new = []
    for l in block:
        m = re.match(r"^(\s+)([A-Za-z]+):\s*(.*)$", l)
        if m and m.group(2) in values:
            l = "%s%s: %s" % (m.group(1), m.group(2), values[m.group(2)])
        new.append(l)
    start, end, ws, we = r
    ind = " " * (_indent(lines[ws]) if ws is not None else _indent(lines[start]) + 4)
    new = [ind + l.lstrip(" ") if i == 0 else l for i, l in enumerate(new)]
    if ws is not None:
        lines[ws:we] = new
    else:
        lines[end:end] = new
    write_file(path, "\n".join(lines), owner=(Ctx.uid, Ctx.gid))


def hp_strip_widgets(text):
    """Remove the widget blocks that need keys. They come back one by one, after each key is tested."""
    lines = text.split("\n")
    for cid in HP_CARDS:
        r = hp_ranges(lines, cid)
        if r and r[2] is not None:
            del lines[r[2]:r[3]]
    return "\n".join(lines)


# ================================================================ steps and the checklist
class Result:
    """The state of one step: done, todo, blocked, skip or na, with a detail text."""
    def __init__(self, state, detail=""):
        self.state = state       # done | todo | blocked | failed | na | skip
        self.detail = detail


class Step:
    """One checklist step: `probe()` says whether it is done, `run()` does it."""
    id = ""
    group = ""
    title = ""
    kind = "auto"            # auto: the installer does it.  manual: you do it.  ack: you confirm it, or it is detected
    needs = ()
    optional = False

    def applies(self):       # False = not part of this machine's list at all
        return True

    def probe(self):         # -> "done" | "todo" | "na"
        return "todo"

    def detail(self):
        return ""

    def run(self):
        raise Abort("This step must be completed manually.")

    def help(self):
        return ""

    def fill_help(self):
        return self.help()   # the text shown at the start of this step inside `sudo homelab-setup fill`

    def fill(self):
        return False         # interactive walk-through; True when something was done


STEPS = []
BY_ID = {}


def register(inst):
    """Add a step (an instance) to the checklist."""
    STEPS.append(inst)
    BY_ID[inst.id] = inst


def step(cls):
    """Class decorator: register a checklist step."""
    register(cls())
    return cls


GROUPS = ["System", "Tailscale", "Network", "Platform", "Services", "Logins and keys", "Homepage",
          "Scripts and schedule", "Your devices and drives"]


def topo():
    """Steps in an order where every step comes after the steps it needs."""
    order, seen = [], set()

    def visit(s):
        if s.id in seen:
            return
        seen.add(s.id)
        for n in s.needs:
            visit(BY_ID[n])
        order.append(s)
    for s in STEPS:
        visit(s)
    return order


def safe_probe(s):
    """What a step's check says ("done", "todo" or "na"). A check must never crash the checklist: an error means "todo"."""
    try:
        return s.probe()
    except Abort:
        return "todo"
    except Exception as e:
        log("probe %s failed: %r" % (s.id, e))
        return "todo"


def evaluate():
    """Check every step and return {step id: Result}, in dependency order."""
    res = {}
    for s in topo():
        if not s.applies():
            res[s.id] = Result("na")
            continue
        if State.data["skip"].get(s.id):
            res[s.id] = Result("skip", "skipped")
            continue
        if State.data["ack"].get(s.id):
            res[s.id] = Result("done", "confirmed")
            continue
        waits = [BY_ID[n].title for n in s.needs if res[n].state not in ("done", "na", "skip")]
        if waits:
            res[s.id] = Result("blocked", "waits for: " + "; ".join(waits[:2]))
            continue
        st = safe_probe(s)
        if st == "done":
            res[s.id] = Result("done", s.detail())
        elif st == "na":
            res[s.id] = Result("na", "")
        else:
            err = State.note("err:" + s.id)
            res[s.id] = Result("failed" if err else "todo", err)
    return res


def counts(res):
    """(steps done, steps that apply) from a set of results."""
    total = sum(1 for r in res.values() if r.state != "na")
    done = sum(1 for r in res.values() if r.state in ("done", "skip"))
    return done, total


def write_progress(res):
    """Save the progress counts for the login screen (does nothing in a dry run)."""
    if Opt.dry:
        return
    done, total = counts(res)
    try:
        os.makedirs(PROGRESS_DIR, exist_ok=True)
        if done >= total:
            if os.path.exists(PROGRESS_FILE):
                os.remove(PROGRESS_FILE)
        else:
            write_file(PROGRESS_FILE, "%d|%d|%d\n" % (done, total, int(time.time())), 0o644)
        # tells the login screen that having no data drive is expected here (it then shows a grey note, not a red error)
        marker = PROGRESS_DIR + "/no-data-drive"
        dd = res.get("data-drive")
        if State.readonly:
            pass        # the existing server is only looked at, never changed
        elif dd is not None and dd.state in ("todo", "skip"):
            write_file(marker, "no data drive set up\n", 0o644)
        elif os.path.exists(marker):
            os.remove(marker)
    except OSError:
        pass


def show_checklist(res, title="Home lab setup", show_help=None, show_all=False):
    """Compact by default: one line per step. `--details` adds the full instructions of every open step."""
    if show_help is None:
        show_help = Opt.details
    done, total = counts(res)
    rule("%s %s %s %s %d of %d steps done" % (title, S_DOT, Ctx.hostname, S_DOT, done, total))
    waiting = False
    for g in GROUPS:
        items = [s for s in STEPS if s.group == g and res[s.id].state != "na"]
        if not items:
            continue
        gd = sum(1 for s in items if res[s.id].state in ("done", "skip"))
        if gd == len(items) and not show_all:
            out("  %s%s%s %s%s (%d of %d)%s" % (G, S_OK, N, B, g, gd, len(items), N))
            continue
        out("  %s%s%s  %s(%d of %d)%s" % (B, g, N, D, gd, len(items), N))
        for s in items:
            r = res[s.id]
            if r.state in ("done", "skip"):
                if not show_all:
                    continue
                line = "   %s%s%s %s" % (G, S_OK, N, s.title)
                if r.detail:
                    line += "  %s%s%s" % (D, r.detail, N)
                out(line)
                continue
            if r.state == "blocked":
                waiting = True
                out("   %s%s %s%s" % (D, S_WAIT, s.title, N))
                continue
            col, sym = (R, S_BAD) if r.state == "failed" else (Y, S_TODO)
            tag = ""
            if s.kind == "manual":
                tag = "  %syou do this%s" % (D, N)
            elif s.kind == "ack":
                tag = "  %sdetected automatically%s" % (D, N)
            out("   %s%s%s %s%s" % (col, sym, N, s.title, tag))
            if r.state == "failed" and r.detail:
                for l in wrap("Last attempt failed: " + r.detail, 9):
                    out("%s%s%s" % (R, l, N))
            if show_help:
                h = s.help()
                if h:
                    for l in styled(h, 9):
                        out(l)
        out("")
    if waiting:
        out("  %sDimmed steps wait for the steps above them.%s" % (D, N))
        out("")
    if done >= total:
        out("  %s%s All steps are complete.%s" % (G, S_OK, N))
    elif not show_help:
        out("  %sInstructions for every open step: sudo homelab-setup --details%s" % (D, N))
    out("")


def pick_next(res):
    "The step to do next: the first one in dependency order that is not done."
    return next((s for s in topo() if res[s.id].state in ("todo", "failed")), None)


def unblock(res, dry=False):
    """Turn steps that were blocked into 'todo' once the steps they need are done."""
    for t in STEPS:
        if res[t.id].state == "blocked" and all(res[n].state in ("done", "na", "skip") for n in t.needs):
            if dry:
                res[t.id] = Result("todo", "")
                continue
            st = safe_probe(t)
            res[t.id] = Result("done", t.detail()) if st == "done" else Result("na") if st == "na" else Result("todo", "")


def run_pass(res, selected=None):
    """Run every automatic step that is ready. Returns the number of steps that became done."""
    gained = 0
    for s in topo():
        r = res[s.id]
        if r.state not in ("todo", "failed") or s.kind != "auto":
            continue
        if selected and s.id not in selected:
            continue
        if Opt.dry or not Live.enabled:
            out("  %s %s%s" % (S_DOT, s.title, ("  %s(step %d of %d)%s" % (D, min(Live.done + 1, Live.total), Live.total, N)) if Live.total else ""))
        if not Opt.dry:
            Live.begin(s.title)
        try:
            s.run()
            State.note("err:" + s.id, "")
            now = "done" if Opt.dry else s.probe()
        except Abort as e:
            Live.end()
            msg = str(e)
            State.note("err:" + s.id, msg.splitlines()[0][:300] if msg else "failed")
            bad("%s: %s" % (s.title, msg))
            log("FAILED %s: %s" % (s.id, msg))
            res[s.id] = Result("failed", msg.splitlines()[0][:300])
            continue
        except Exception as e:
            Live.end()
            State.note("err:" + s.id, "unexpected error: %r" % (e,))
            bad("%s: unexpected error: %r" % (s.title, e))
            log("CRASH %s: %r" % (s.id, e))
            res[s.id] = Result("failed", "unexpected error")
            continue
        secs = Live.end()
        Live.advance()
        if Opt.dry:
            res[s.id] = Result("done", "(dry run)")
            unblock(res, dry=True)
            continue
        if now in ("done", "na"):
            res[s.id] = Result("done", s.detail())
            gained += 1
            good("%s%s" % (s.title, ("  %s(%s)%s" % (D, fmt_time(secs), N)) if secs >= 5 else ""))
        else:
            State.note("err:" + s.id, "The step ran, but its check still reports it as not done")
            res[s.id] = Result("failed", "The step ran, but its check still reports it as not done")
            bad("%s: the step ran, but its check still reports it as not done." % s.title)
        # steps that were waiting may be ready now
        unblock(res)
    Live.close()
    return gained
