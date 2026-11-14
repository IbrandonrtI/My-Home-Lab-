FINISH_UNIT = "homelab-finish"
FINISH_STATUS = PROGRESS_DIR + "/finish-status"
FINISH_LOCK = STATE_DIR + "/finish.lock"
DASHBOARD_STATUS = "images/install-status.json"
FINISH_PW = P("/run/homelab-finish.pw")
FINISH_SEEDS = ("stack-immich", "stack-nextcloud", "nextcloud-ready", "nextcloud-restore-db", "immich-admin", "beszel-user", "beszel-agent-key", "apt-upgrade")


def background_mode():
    if Opt.dry or Opt.no_background:
        return False
    if FAKE:
        return os.environ.get("HLS_BG") == "1"
    return have("systemd-run")


def deferred_ids():
    ids = set(FINISH_SEEDS) | {s.id for s in STEPS if isinstance(s, WidgetStep) and s.kind == "auto"}
    grew = True
    while grew:
        grew = False
        for s in STEPS:
            if s.kind == "auto" and s.id not in ids and any(n in ids for n in s.needs):
                ids.add(s.id)
                grew = True
    return ids & {s.id for s in STEPS}


def finish_running():
    try:
        fd = os.open(FINISH_LOCK, os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        os.close(fd)


class Finish:
    """Status and lock of the background job that finishes the deferred steps. The lock lets only one run at a time."""
    lock_fd = None
    data = {}
    active = set()

    @classmethod
    def take_lock(cls):
        os.makedirs(STATE_DIR, exist_ok=True)
        cls.lock_fd = os.open(FINISH_LOCK, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(cls.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(cls.lock_fd)
            cls.lock_fd = None
            return False
        return True

    @classmethod
    def save(cls):
        cls.data["updated"] = int(time.time())
        try:
            os.makedirs(PROGRESS_DIR, exist_ok=True)
            write_file(FINISH_STATUS, json.dumps(cls.data), 0o644)
            if os.path.isdir(hp_path("images")):
                keep = ("state", "started", "updated", "finished", "total", "done", "now", "steps")
                write_file(hp_path(DASHBOARD_STATUS), json.dumps({k: cls.data[k] for k in keep if k in cls.data}), 0o644, (Ctx.uid, Ctx.gid))
        except OSError:
            pass

    @classmethod
    def begin(cls, res, ids):
        mine = [s for s in STEPS if s.id in ids and res[s.id].state != "na"]
        cls.data = {"state": "running", "started": int(time.time()), "total": len(mine), "done": 0, "now": "", "failed": [], "waiting": []}
        cls.update(None, res, ids)

    @classmethod
    def step_state(cls, x, res):
        """One word for the dashboard list: done, failed, now (running) or wait."""
        st = res[x.id].state
        return "done" if st in ("done", "skip") else "failed" if st == "failed" else "now" if x.id in cls.active else "wait"

    @classmethod
    def update(cls, s, res, ids):
        mine = [x for x in STEPS if x.id in ids and res[x.id].state != "na"]
        cls.data["total"] = len(mine)
        cls.data["done"] = sum(1 for x in mine if res[x.id].state in ("done", "skip"))
        cls.data["now"] = s.title if s is not None else ""
        cls.active = cls.active | {s.id} if s is not None else set()
        cls.data["steps"] = [{"t": x.title.split(" (")[0], "s": cls.step_state(x, res)} for x in mine]
        cls.data["failed"] = [{"id": x.id, "title": x.title, "why": res[x.id].detail} for x in mine if res[x.id].state == "failed"]
        cls.save()

    @classmethod
    def end(cls, res, ids):
        mine = [x for x in STEPS if x.id in ids and res[x.id].state != "na"]
        cls.update(None, res, ids)
        cls.data["waiting"] = [{"id": x.id, "title": x.title} for x in mine if res[x.id].state in ("todo", "blocked")]
        cls.data["state"] = "failed" if cls.data["failed"] else "waiting" if cls.data["waiting"] else "done"
        cls.data["finished"] = int(time.time())
        cls.save()


def sync_dashboard_status(res):
    """After a manual refresh or fill, bring the dashboard's install status in line with the real steps (so a fixed step clears the warning)."""
    if Opt.dry or State.readonly or finish_running():
        return
    try:
        d = json.loads(read_file(FINISH_STATUS) or "{}")
    except (OSError, ValueError):
        return
    if not d:
        return
    was = (d.get("state"), d.get("done"), d.get("finished"))
    Finish.data, Finish.active = d, set()
    Finish.end(res, deferred_ids())
    if was[2] and (Finish.data.get("state"), Finish.data.get("done")) == was[:2]:
        Finish.data["finished"] = was[2]
        Finish.save()


def finish_passes(res, ids):
    Hook.step = lambda s, r: Finish.update(s, r, ids)
    try:
        for _ in range(4):
            gained = run_pass(res, selected=ids, skip={"apt-upgrade"})
            res = evaluate()
            if not gained:
                break
        if "apt-upgrade" in ids and res["apt-upgrade"].state in ("todo", "failed"):
            run_pass(res, selected={"apt-upgrade"})
            res = evaluate()
    finally:
        Hook.step = None
    return res


def finish_pending(res):
    ids = deferred_ids()
    return [s for s in STEPS if s.id in ids and res[s.id].state in ("todo", "failed", "blocked")]


def hand_over_password():
    if not Runtime.password:
        return False
    os.makedirs(os.path.dirname(FINISH_PW), exist_ok=True)
    fd = os.open(FINISH_PW, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(Runtime.password)
    return True


def start_finish_job(res):
    pending = [s for s in finish_pending(res) if res[s.id].state in ("todo", "failed", "blocked")]
    if not pending or not background_mode():
        return False
    if not Runtime.password and interactive():
        try:
            need_password("the last steps run in the background and cannot ask for it later")
        except Abort as e:
            warn(str(e))
            return False
    me = os.path.realpath(sys.argv[0])
    # The dashboard's progress ring reads this file, so it is written now, before the dashboard link is shown.
    Finish.data = {}
    Finish.begin(res, deferred_ids())
    handed = False
    try:
        handed = hand_over_password()
    except OSError:
        pass
    cmd = ["systemd-run", "--unit=" + FINISH_UNIT, "--collect", "--quiet", "--description=Home lab: finishing the install",
           "--property=Nice=5", "--setenv=SUDO_USER=" + (Ctx.user or "")]
    for k in ("HLS_ROOT", "HLS_FAKE", "HLS_USER", "HLS_HOST", "HLS_LAN", "HLS_NO_THROTTLE", "HLS_BG", "HLS_PREFETCH", "PATH", "HOMELAB_EXTRA_PATH"):
        if os.environ.get(k) is not None:
            cmd.append("--setenv=%s=%s" % (k, os.environ[k]))
    cmd += [sys.executable, me, "finish", "--background"]
    rc, txt = run(cmd)
    if rc != 0:
        for f in (FINISH_STATUS, hp_path(DASHBOARD_STATUS)):
            try:
                os.remove(f)
            except OSError:
                pass
        if handed:
            try:
                os.remove(FINISH_PW)
            except OSError:
                pass
        warn("The background job could not be started (%s). The last steps run with:  sudo homelab-setup finish" % txt.strip()[-200:])
        return False
    log("background job started for %d step(s)" % len(pending))
    return True


def say_background_start(res):
    """Tell the user which last steps continue in the background and how to check progress."""
    pending = finish_pending(res)
    rule("Finishing in the background")
    say("%d last step%s continue%s automatically, so you can close this window:" % (len(pending), "" if len(pending) == 1 else "s", "s" if len(pending) == 1 else ""))
    names = []
    for s in pending:
        t = s.title.split(" (")[0]
        if t not in names:
            names.append(t)
    for l in wrap("; ".join(names[:8]) + (" ..." if len(names) > 8 else ""), 4):
        out(l)
    out("")
    say("See how far it is at any time:\n$ sudo homelab-setup status")
    say("Nextcloud and Immich can need a few more minutes before their first login works.")
    out("")


def refuse_while_finishing():
    if finish_running():
        raise Abort("The last steps of the install are still finishing in the background. See how far it is with `sudo homelab-setup status`, "
                    "and run this again when it says it is done.")


def cmd_finish():
    background = "--background" in sys.argv
    Runtime.background = background
    if background:
        try:
            Runtime.password = read_file(FINISH_PW).strip() or None
            os.remove(FINISH_PW)
        except OSError:
            pass
    load_all()
    if Mode.existing:
        raise Abort("This machine already runs the lab; there is nothing to finish.")
    if not State.exists():
        raise Abort("The installer has not run on this machine yet. Run `sudo homelab-setup install`.")
    if not Finish.take_lock():
        raise Abort("The last steps are already finishing in the background. See `sudo homelab-setup status`.")
    ids = deferred_ids()
    wait_for_apps()
    res = evaluate()
    todo = [s for s in finish_pending(res) if res[s.id].state in ("todo", "failed", "blocked")]
    if not todo:
        say("Nothing is left to finish.")
        Finish.begin(res, ids)
        Finish.end(res, ids)
        return
    Live.begin_run(len(todo))
    Finish.begin(res, ids)
    Prefetch.start()
    rule("Finishing the install")
    try:
        res = finish_passes(res, ids)
    finally:
        Finish.end(res, ids)
    write_progress(res)
    done, total = Finish.data["done"], Finish.data["total"]
    if Finish.data["failed"]:
        bad("%d last step(s) failed: %s. `sudo homelab-setup finish` tries them again." % (
            len(Finish.data["failed"]), "; ".join(f["title"] for f in Finish.data["failed"][:3])))
    else:
        good("%d of %d last steps are done." % (done, total))
        show_dashboard_links()


def cmd_status():
    try:
        d = json.loads(read_file(FINISH_STATUS) or "{}")
    except ValueError:
        d = {}
    if not d:
        say("No background job has run on this machine. `sudo homelab-setup` shows the checklist.")
        return
    running = finish_running()
    el = fmt_time(max(0, (int(time.time()) if running else d.get("finished", d.get("updated", 0))) - d.get("started", 0)))
    if running:
        say("Finishing the install in the background: %d of %d steps done (running for %s)." % (d.get("done", 0), d.get("total", 0), el))
        if d.get("now"):
            say("Now: %s" % d["now"])
    elif d.get("state") == "running":
        warn("The background job stopped before it was done (%d of %d steps), for example because the machine was restarted." % (d.get("done", 0), d.get("total", 0)))
        say("Continue with:\n$ sudo homelab-setup finish")
    elif d.get("state") == "done":
        good("The last steps are done (%d of %d, took %s)." % (d.get("done", 0), d.get("total", 0), el))
        show_dashboard_links()
    else:
        say("The background job ended after %s: %d of %d steps done." % (el, d.get("done", 0), d.get("total", 0)))
    for f in d.get("failed", []):
        bad("%s: %s" % (f["title"], f.get("why") or "failed"))
    if d.get("failed") and not running:
        say("Try them again:\n$ sudo homelab-setup finish")
    if d.get("waiting") and not running:
        say("These wait for a step that needs you: %s. `sudo homelab-setup` shows what to do." % "; ".join(w["title"] for w in d["waiting"][:4]))
    if running:
        say("Details:  journalctl -u %s" % FINISH_UNIT)
