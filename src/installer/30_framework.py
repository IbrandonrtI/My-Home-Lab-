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
    tip = False              # an optional tip: shown at the end of the checklist, never counted, never "the next step"

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

    def tip_text(self):
        return self.help()


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
    """Check every step and return {step id: Result}, in dependency order.
    With HLS_TIMING=1 in the environment the slowest checks are listed afterwards (to see where the time goes)."""
    res = {}
    spent = {}
    for s in topo():
        t0 = time.monotonic()
        _check_one(s, res)
        spent[s.id] = time.monotonic() - t0
    if os.environ.get("HLS_TIMING") == "1":
        top = sorted(spent.items(), key=lambda kv: -kv[1])[:10]
        sys.stderr.write("slowest checks (seconds): total %.1f\n" % sum(spent.values()))
        for k, v in top:
            sys.stderr.write("  %5.2f  %s\n" % (v, k))
    return res


def _check_one(s, res):
    """Check one step and put its result into res."""
    if not s.applies():
        res[s.id] = Result("na")
        return
    if State.data["skip"].get(s.id):
        res[s.id] = Result("skip", "skipped")
        return
    if State.data["ack"].get(s.id):
        res[s.id] = Result("done", "confirmed")
        return
    waits = [BY_ID[n].title for n in s.needs if res[n].state not in ("done", "na", "skip")]
    if waits:
        res[s.id] = Result("blocked", "waits for: " + "; ".join(waits[:2]))
        return
    st = safe_probe(s)
    if st == "done":
        res[s.id] = Result("done", s.detail())
    elif st == "na":
        res[s.id] = Result("na", "")
    else:
        err = State.note("err:" + s.id)
        res[s.id] = Result("failed" if err else "todo", err)


def counts(res):
    """(steps done, steps that apply) from a set of results."""
    own = {k: r for k, r in res.items() if not (k in BY_ID and BY_ID[k].tip)}      # (tips are not part of "N of M")
    total = sum(1 for r in own.values() if r.state != "na")
    done = sum(1 for r in own.values() if r.state in ("done", "skip"))
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
    nodrive = not Opt.dry and main_storage_missing()
    later = deferred_ids() if not Opt.dry and finish_running() else set()
    for g in GROUPS:
        items = [s for s in STEPS if s.group == g and res[s.id].state != "na" and not s.tip]
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
            if s.id in later and r.state in ("todo", "blocked"):
                out("   %s%s %s   (finishing in the background)%s" % (D, S_WAIT, s.title, N))
                continue
            if r.state == "blocked":
                waiting = True
                out("   %s%s %s%s%s" % (D, S_WAIT, s.title, "   (waits for a Main drive)" if nodrive and waits_for_folders(s) else "", N))
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
    for s in STEPS:      # optional tips: never counted, never the next step
        if s.tip and res[s.id].state in ("todo", "failed", "blocked"):
            out("  %sOptional:%s %s" % (B, N, s.title))
            for l in wrap(s.tip_text(), 4):
                out(l)
            out("")
    if done >= total:
        out("  %s%s All steps are complete.%s" % (G, S_OK, N))
    elif not show_help:
        out("  %sInstructions for every open step: sudo homelab-setup --details%s" % (D, N))
    out("")


def pick_next(res):
    "The step to do next: the first one in dependency order that is not done."
    return next((s for s in topo() if res[s.id].state in ("todo", "failed") and not s.tip), None)


def unblock(res, dry=False):
    """Turn steps that were blocked into 'todo' once the steps they need are done."""
    for t in STEPS:
        if res[t.id].state == "blocked" and all(res[n].state in ("done", "na", "skip") for n in t.needs):
            if dry:
                res[t.id] = Result("todo", "")
                continue
            st = safe_probe(t)
            res[t.id] = Result("done", t.detail()) if st == "done" else Result("na") if st == "na" else Result("todo", "")


class Hook:
    """The background job listens to the steps here (to keep its status file up to date)."""
    step = None             # called as step(step_or_None, res) before a step starts (None: between steps) and after it ended


def run_step(s):
    """Run one step. Returns the exception it raised, or None."""
    try:
        s.run()
        return None
    except Exception as e:
        return e


def run_parallel(batch):
    """Run the steps of the batch at the same time (the stacks: each one only waits for Portainer and Docker). Returns {id: exception or None}."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(len(batch), 4)) as pool:
        futs = {s.id: pool.submit(run_step, s) for s in batch}
        return {sid: f.result() for sid, f in futs.items()}


def settle(s, exc, res, secs):
    """What a step's ending means: record success or the reason it failed. Returns 1 when the step became done."""
    if exc is None:
        State.note("err:" + s.id, "")
        Live.advance()
        if Opt.dry:
            res[s.id] = Result("done", "(dry run)")
            unblock(res, dry=True)
            return 0
        now = s.probe()
        if now in ("done", "na"):
            res[s.id] = Result("done", s.detail())
            good("%s%s" % (s.title, ("  %s(%s)%s" % (D, fmt_time(secs), N)) if secs >= 5 else ""))
            unblock(res)
            return 1
        State.note("err:" + s.id, "The step ran, but its check still reports it as not done")
        res[s.id] = Result("failed", "The step ran, but its check still reports it as not done")
        bad("%s: the step ran, but its check still reports it as not done." % s.title)
        unblock(res)
        return 0
    if isinstance(exc, NeedsPerson):
        if not Runtime.unattended:
            msg = str(exc)
            State.note("err:" + s.id, msg[:300])
            bad("%s: %s" % (s.title, msg))
            log("FAILED %s: %s" % (s.id, msg))
            res[s.id] = Result("failed", msg[:300])
        return 0      # (the quiet schedule leaves it open: the person finishes it with `sudo homelab-setup refresh`)
    if isinstance(exc, Abort):
        msg = str(exc)
        State.note("err:" + s.id, msg.splitlines()[0][:300] if msg else "failed")
        bad("%s: %s" % (s.title, msg))
        log("FAILED %s: %s" % (s.id, msg))
        res[s.id] = Result("failed", msg.splitlines()[0][:300])
        return 0
    State.note("err:" + s.id, "unexpected error: %r" % (exc,))
    bad("%s: unexpected error: %r" % (s.title, exc))
    log("CRASH %s: %r" % (s.id, exc))
    res[s.id] = Result("failed", "unexpected error")
    return 0


def ready(res, s, selected, skip):
    """True when the automatic step `s` can run in this pass."""
    return (res[s.id].state in ("todo", "failed") and s.kind == "auto" and not (selected and s.id not in selected) and not (skip and s.id in skip))


def run_pass(res, selected=None, skip=None):
    """Run every automatic step that is ready. Returns the number of steps that became done.
    `skip` holds the ids of steps that are left for later (the ones that finish in the background).
    The stacks (steps with `parallel` set) that are ready are started together: each one only waits for Portainer and Docker."""
    gained = 0
    for s in topo():
        if not ready(res, s, selected, skip):
            continue
        batch = [s]
        if getattr(s, "parallel", False) and not Opt.dry:
            batch += [t for t in STEPS if t is not s and getattr(t, "parallel", False) and ready(res, t, selected, skip)]
        for t in batch:
            if Hook.step:
                Hook.step(t, res)
        if Opt.dry or not Live.enabled:
            for t in batch:
                out("  %s %s%s" % (S_DOT, t.title, ("  %s(step %d of %d)%s" % (D, min(Live.done + 1, Live.total), Live.total, N)) if Live.total else ""))
        if not Opt.dry:
            Live.begin(s.title if len(batch) == 1 else "Starting %d stacks at the same time (%s)" % (len(batch), ", ".join(t.name for t in batch)))
        if len(batch) == 1:
            outcomes = {s.id: run_step(s)}
        else:
            outcomes = run_parallel(batch)
        secs = Live.end()
        for t in batch:
            gained += settle(t, outcomes[t.id], res, secs)
    if Hook.step:
        Hook.step(None, res)
    Live.close()
    return gained
