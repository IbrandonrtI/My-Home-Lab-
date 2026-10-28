

# ================================================================ commands
def ensure_root():
    """Start the installer again under sudo when it was not started as root."""
    if FAKE or os.geteuid() == 0:
        return
    if not have("sudo"):
        raise SystemExit("homelab-setup must run as root, and sudo is not installed.")
    os.execvp("sudo", ["sudo", "-E", sys.executable] + sys.argv)


def load_all():
    """Load the state file, the saved secrets and this machine's facts."""
    State.load()
    Secrets.load()
    Ctx.detect()
    Mode.existing = is_existing()
    State.readonly = Mode.existing and not Opt.force_existing


def password_warning():
    """Explain that one password is used for every login."""
    out("")
    warn("One password is used for every admin login (Portainer, AdGuard Home, Beszel, Immich, Nextcloud, FileBrowser, "
         "Speedtest Tracker). If one service leaks it, all of them are exposed. Homepage's configuration file also stores "
         "some of these logins in plain text. Use a long password that you use nowhere else and keep it in a password "
         "manager.")


def ask_weather(a):
    """Ask for a city, look up its coordinates and keep them for the Homepage weather card.
    If the lookup is not possible the card keeps the repository default and the weather step stays on the list."""
    if a.get("weather"):
        return
    default = WEATHER_CITY_DEFAULT
    for _ in range(3):
        q = ask("City for the Homepage weather card", default)
        found = geocode_city(q)
        if found is None:
            warn("The city lookup (geocoding-api.open-meteo.com) did not answer. The weather card keeps its default "
                 "location (New York). It can be changed later in ~/homepage-config/widgets.yaml.")
            return
        if not found:
            warn("No city named '%s' was found. Try the name alone, without a state or country." % q)
            continue
        pick = found[0]
        if len(found) > 1:
            out("")
            for i, f in enumerate(found, 1):
                out("   %d  %s" % (i, ", ".join(x for x in (f["name"], f["region"], f["country"]) if x)))
            n = ask("Which one? Enter its number", "1")
            pick = found[int(n) - 1] if n.isdigit() and 1 <= int(n) <= len(found) else found[0]
        a["weather"] = pick
        good("Weather location: %s" % ", ".join(x for x in (pick["name"], pick["region"], pick["country"]) if x))
        return
    warn("No weather city was chosen. The card keeps its default location (New York).")


def is_ipv4(text):
    """Four numbers from 0 to 255 with dots, like 192.168.1.20."""
    return bool(re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", text)) and all(int(x) <= 255 for x in text.split("."))


def ask_answers():
    """Ask the first questions of an install: admin name, email, time zone, city, LAN address and the password."""
    a = State.data["answers"]
    out("")
    say("A few answers are needed first. They stay on this machine and only fill in its configuration files.")
    out("")
    a["admin"] = ask("Admin name for every service", a.get("admin") or Ctx.user.capitalize())
    a["email"] = ask("Email address (login for Immich, Beszel and Speedtest Tracker)", a.get("email", ""))
    while not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", a["email"]):
        a["email"] = ask("That is not a valid email address. Enter it again", "")
    a["tz"] = ask("Time zone", a.get("tz") or Ctx.tz)
    ask_weather(a)
    a["lan"] = ask("This machine's LAN address (reserve it in your router so it does not change)", a.get("lan") or Ctx.lan)
    while not is_ipv4(a["lan"].strip()):
        a["lan"] = ask("That is not an address like 192.168.1.20. Enter it again", "")
    a["lan"] = a["lan"].strip()
    State.save()
    Ctx.detect()
    if not Runtime.password:
        password_warning()
        out("")
        for _ in range(3):
            p1 = ask_secret("Choose the admin password (12 or more letters and digits; it is not saved)")
            problem = password_problem(p1)
            if problem:
                warn(problem)
                continue
            if ask_secret("Type it again") != p1:
                warn("The two entries did not match.")
                continue
            Runtime.password = p1
            break
        else:
            raise Abort("No valid password was entered.")


def preflight():
    """Check that the machine can run the install."""
    out("")
    if OsSupported().probe() != "done":
        raise Abort(OsSupported().help())
    good("Operating system: %s" % Ctx.os_name)
    if not Ctx.lan:
        raise Abort("Could not detect this machine's network address. Connect it to the network and try again.")
    good("Network address: %s" % Ctx.lan)
    try:
        socket.getaddrinfo("download.docker.com", 443)
        good("Internet reachable")
    except OSError:
        if not FAKE:
            raise Abort("No internet access (download.docker.com did not resolve). Check the network and try again.") from None
    free = shutil.disk_usage(P("/") if os.path.isdir(P("/")) else "/").free / 1073741824.0
    if free < 20:
        warn("Only %.0f GB free on the boot drive. The services need about 20 GB (more with photos)." % free)
    else:
        good("Free space on the boot drive: %.0f GB" % free)


def final_report(res):
    """End of install: how it went, the generated passwords (then wait for Enter), the checklist, the next step."""
    Live.close()
    done, total = counts(res)
    failed = [s for s in STEPS if res[s.id].state == "failed"]
    rule("Install finished")
    good("Finished in %s. %d of %d steps are done." % (fmt_time(Live.elapsed_total()), done, total))
    if failed:
        bad("%d step(s) failed: %s. `sudo homelab-setup refresh` tries them again." % (
            len(failed), "; ".join(s.title for s in failed[:3]) + (" ..." if len(failed) > 3 else "")))
    if 0 < http("GET", url("homepage"), timeout=10)[0] < 500:
        good("Your lab is running. Open Homepage: %s" % mark(url("homepage")))
    Secrets.load()
    keys = list(Secrets.vals)
    if keys and not State.data.get("secrets_announced"):
        State.data["secrets_announced"] = time.strftime("%F %T")
        State.save()
        rule("Generated passwords and keys")
        say("Stored in %s (root only). Copy them into your password manager now. "
            "This file stays on this machine and is never part of the repository." % SECRET_FILE.replace(ROOT, ""))
        out("")
        for k in sorted(Secrets.vals):
            out("   %-28s %s" % (k, Secrets.vals[k]))
        out("")
        say("Show them again at any time:\n$ sudo homelab-setup secrets")
        say("The admin password you chose is not stored anywhere. Keep it in your password manager.")
        out("")
        if interactive() and not Opt.yes:
            ask("Press Enter when they are saved to see what is left")
            State.data["secrets_shown"] = time.strftime("%F %T")        # ticks "passwords copied into your password manager"
            State.save()
            res = evaluate()
            write_progress(res)
    show_checklist(res, "Setup")
    next_step_section(res)


SERVICE_LABELS = [("homepage", "Homepage"), ("portainer", "Portainer"), ("adguard", "AdGuard Home"), ("beszel", "Beszel"),
                  ("netdata", "Netdata"), ("speedtest", "Speedtest Tracker"), ("filebrowser", "FileBrowser"),
                  ("immich", "Immich"), ("nextcloud", "Nextcloud")]


def system_check():
    """Look at the running system and report whether everything is up. Returns the number of problems."""
    rule("System check")
    problems = []
    names = ["portainer"] + [c for n in STACK_ORDER for c in STACKS[n][1]]
    up = containers_running()
    missing = [c for c in names if c not in up]
    if missing:
        bad("Containers: %d of %d running. Not running: %s" % (len(names) - len(missing), len(names), ", ".join(missing)))
        problems.append("containers")
    else:
        good("Containers: %d of %d running" % (len(names), len(names)))
    Ctx.refresh_tailscale()
    if Ctx.fqdn:
        good("Tailscale: connected as %s" % Ctx.fqdn)
    else:
        bad("Tailscale: not connected")
        problems.append("tailscale")
    resolv = read_file(P("/etc/resolv.conf"))
    if "nameserver" in resolv and "100.100.100.100" not in resolv:
        good("DNS: this machine uses its router (Tailscale does not manage DNS)")
    else:
        bad("DNS: /etc/resolv.conf is empty or points at Tailscale (100.100.100.100). Run `sudo homelab-setup refresh`.")
        problems.append("dns")
    out("")
    out("  %sServices on the local network%s" % (B, N))
    for key, label in SERVICE_LABELS:
        st = http("GET", url(key), timeout=10)[0]
        if 0 < st < 500:
            out("  %s%s%s %-18s %s" % (G, S_OK, N, label, mark(url(key))))
        else:
            out("  %s%s%s %-18s %s  (no answer)" % (R, S_BAD, N, label, mark(url(key))))
            problems.append(key)
    if Ctx.fqdn:
        out("")
        out("  %sServices over Tailscale%s %s(use these from your other devices; a machine cannot open its own Tailscale addresses)%s" % (B, N, D, N))
        for port, key in SERVE:
            label = dict(SERVICE_LABELS)[key]
            out("    %-18s %s" % (label, mark("https://%s:%d" % (Ctx.fqdn, port))))
    out("")
    if problems:
        say("%d problem(s) found. Run:\n$ sudo homelab-setup refresh" % len(problems))
    else:
        good("Everything is up and running. Open Homepage: %s" % mark(url("homepage")))
    out("")
    return len(problems)


def next_step_section(res):
    """The last thing on screen: the one command to run next, or the system check when everything is done."""
    if Mode.existing:
        return
    done, total = counts(res)
    if done >= total:
        system_check()
        return
    rule("Next step")
    nxt = pick_next(res)
    if nxt is None:
        say("The remaining steps are waiting for earlier ones. Run:\n$ sudo homelab-setup refresh")
        out("")
        return
    out("  %s%s%s" % (B, nxt.title, N))
    r = res[nxt.id]
    if r.state == "failed" and r.detail:
        for l in wrap("Last attempt failed: " + r.detail, 4):
            out("%s%s%s" % (R, l, N))
    if nxt.kind == "auto":
        say("This step runs automatically. Run:\n$ sudo homelab-setup refresh", 4)
    else:
        say(nxt.help(), 4)
        out("")
        say("%d of %d steps are done. After each step, check progress with:\n$ sudo homelab-setup refresh" % (done, total))
    out("")


def cmd_verify():
    """`verify`: run the system check."""
    load_all()
    if Mode.existing and not Opt.force_existing:
        say("This machine already runs the lab. The system check is for machines set up by the installer.")
        return
    system_check()


def cmd_checklist():
    """Show the checklist."""
    load_all()
    res = evaluate()
    if Mode.existing:
        say("This machine already runs the lab (set up by hand). The installer only reads it and changes nothing.")
    show_checklist(res, show_all=Opt.all)
    write_progress(res)
    next_step_section(res)


DURING_INSTALL = ("tailscale-login", "tailscale-https")

GROUP_BLURB = {
    "System": "updates, helper programs and Docker",
    "Tailscale": "the private network that reaches the lab from anywhere",
    "Network": "keeps DNS working and frees port 53 for AdGuard Home",
    "Platform": "folders, generated passwords and Portainer, which deploys the apps",
    "Services": "downloads and starts the apps (the longest part)",
    "Logins and keys": "creates the admin accounts and API keys inside the apps",
    "Homepage": "connects the dashboard widgets to the apps",
    "Scripts and schedule": "helper commands, scheduled jobs and the login screen",
    "Your devices and drives": "things only you can do",
}


def welcome():
    """Print the welcome screen."""
    say("This turns this machine into a home lab: Docker, Tailscale and nine apps (Homepage, Portainer, AdGuard Home, "
        "Beszel, Netdata, Speedtest Tracker, FileBrowser, Immich and Nextcloud), with their logins and dashboard widgets.")
    out("")
    say("It takes roughly 30 to 60 minutes and downloads about 10 GB. You can leave it running; it only asks when it needs you. "
        "If it stops, run the same command again: finished steps are skipped.")
    out("")
    say("Have ready:")
    for item in ("a password manager, to save the passwords the installer generates",
                 "a free Tailscale account (tailscale.com), to sign in once in a browser",
                 "about 20 GB of free space on this machine"):
        lines = styled(item, 6)
        out("    %s %s" % (S_DOT, lines[0][6:]))          # bullet, then the text lines up under itself
        for l in lines[1:]:
            out(l)


def cmd_install():
    """`install`: plan, ask, then build the lab."""
    load_all()
    if Mode.existing and not Opt.force_existing:
        out("")
        say("This machine already runs the lab, so nothing is installed. Its checklist is shown read-only. "
            "To run the installer on it anyway, add `--force-existing`.")
        res = evaluate()
        show_checklist(res)
        return
    rule("Home lab installer %s %s" % (S_DOT, "dry run - nothing will be changed" if Opt.dry else "v" + VERSION))
    if not State.ran("install-started"):
        welcome()
    else:
        say("An earlier install was started on this machine. It continues where it stopped; finished steps are skipped.")
    preflight()
    if not Opt.dry:
        if not (State.data["answers"].get("admin") and State.data["answers"].get("email")):
            ask_answers()
        else:
            Ctx.detect()
        State.data["repo"] = Ctx.repo
        State.save()
        ask_restore_plan()
    else:
        if not Ctx.admin:
            Ctx.admin = Ctx.user.capitalize()
        if not Ctx.email:
            Ctx.email = "you@example.com"
    if State.ran("install-started"):
        wait_for_apps()
    res = evaluate()
    open_auto = [s for s in STEPS if res[s.id].state in ("todo", "failed", "blocked") and s.kind == "auto"]

    def runs_now(s, seen=()):
        """True when everything this step needs is done or will be done by the installer itself in this run."""
        for n in s.needs:
            if res[n].state in ("done", "na", "skip"):
                continue
            d = BY_ID[n]
            if n in seen or not (d.kind == "auto" or n in DURING_INSTALL) or not runs_now(d, seen + (s.id,)):
                return False
        return True
    todo = [s for s in open_auto if runs_now(s)]
    later = [s for s in open_auto if s not in todo]          # wait for a step that only the person can do
    by_hand = [s for s in STEPS if res[s.id].state in ("todo", "failed", "blocked") and s.kind != "auto"
               and not (s.id == "weather" and (Opt.dry or State.data["answers"].get("weather")))]   # set from the city answer
    if not todo and not by_hand and not later:
        out("")
        say("Nothing to do: all steps are complete.")
        show_checklist(res, "Setup")
        next_step_section(res)
        return
    rule("Planned steps")
    during = [s for s in by_hand if s.id in DURING_INSTALL]
    say("%d steps run automatically, in this order:" % len(todo))
    out("")
    for g in GROUPS:
        n = len([s for s in todo if s.group == g])
        if n:
            out("   %s%-22s%s %2d  %s%s%s" % (B, g, N, n, D, GROUP_BLURB.get(g, ""), N))
    if later:
        out("")
        say("%d more %s by itself once the steps that need you are done: %s" % (
            len(later), "step runs" if len(later) == 1 else "steps run", "; ".join(s.title for s in later)))
    if by_hand:
        out("")
        say("%d steps need you:" % len(by_hand))
        out("")
        for s in by_hand:
            if s.id in DURING_INSTALL:
                tag = "during the install"
            elif s.id == "secrets-saved":
                tag = "at the end of the install, when you press Enter after copying them"
            elif getattr(s, "auto", None):
                tag = "afterwards, detected automatically once done"
            else:
                tag = "afterwards"
            out("   %s%s%s %s  %s(%s)%s" % (Y, S_TODO, N, s.title, D, tag, N))
    out("")
    if not Opt.dry and not Opt.yes:
        if not typed("yes", "Type yes to start (nothing has been changed yet)"):
            raise Abort("Stopped. Nothing was changed.")
    if not Opt.dry:
        State.mark("install-started")
    Live.begin_run(len(todo) + len(during))
    run_install(res)
    res = evaluate()
    write_progress(res)
    if not Opt.dry:
        final_report(res)
    else:
        out("")
        say("This was a dry run. Nothing was changed.")


def run_install(res):
    """Run the install: the early system steps, then the two steps a person must do, then up to four more passes."""
    early = {"os", "apt-upgrade", "packages", "docker", "docker-group", "tailscale-install"}
    rule("Installing")
    run_pass(res, early)
    # the two things only a person can do: log in to Tailscale and switch HTTPS on
    for sid in ("tailscale-login", "tailscale-https"):
        s = BY_ID[sid]
        if res[s.id].state == "todo":
            out("")
            out("  %s %s" % (S_DOT, s.title))
            try:
                if s.fill():
                    res[s.id] = Result("done", s.detail())
                    Live.advance()
                    unblock(res, dry=Opt.dry)
            except Abort as e:
                bad(str(e))
    for _ in range(4):
        gained = run_pass(res)
        res.update(evaluate()) if not Opt.dry else None
        if not gained:
            break


def wait_for_apps():
    """Before the steps are checked: give Docker and the apps a moment if they are busy or still starting (after a reboot or an update),
    so that a slow answer is not mistaken for something that is missing."""
    if not have("docker") or Opt.dry:
        return
    if not docker_answers():
        try:
            wait_for(docker_answers, "Docker to answer (up to 2 minutes)", 3 if FAKE else 120, every=5)
        except Abort:
            raise Abort(DOCKER_DOWN) from None
    if containers_starting():
        try:
            wait_for(lambda: not containers_starting(), "the apps to finish starting (up to 5 minutes)", 300, every=5)
        except Abort as e:
            warn(str(e) + " Going on anyway.")


def cmd_refresh():
    """`refresh`: check every step again and do what is now possible."""
    load_all()
    if Mode.existing:
        say("This machine already runs the lab. Its checklist is shown read-only.")
        res = evaluate()
        show_checklist(res)
        write_progress(res)
        return
    if not State.exists():
        raise Abort("The installer has not run on this machine yet. Run `sudo homelab-setup install`.")
    wait_for_apps()
    res = evaluate()
    Live.begin_run(len([s for s in STEPS if s.kind == "auto" and res[s.id].state in ("todo", "failed", "blocked")]))
    rule("Checking and continuing")
    for _ in range(4):
        gained = run_pass(res)
        res = evaluate()
        if not gained:
            break
    write_progress(res)
    show_checklist(res)
    next_step_section(res)


def cmd_filebrowser():
    """Update FileBrowser's drive folders after a drive was connected or removed (sudo drives calls this by itself)."""
    load_all()
    if Mode.existing:
        say("This machine already runs the lab. The installer does not change it.")
        return
    if not State.exists():
        raise Abort("The installer has not run on this machine yet. Run `sudo homelab-setup install`.")
    s = BY_ID["filebrowser-drives"]
    if BY_ID["stack-filebrowser"].probe() != "done":
        raise Abort("FileBrowser is not running yet. Run `sudo homelab-setup install` first.")
    if s.probe() == "done":
        say("FileBrowser already shows the drives that are connected: %s." % (s.detail() or "no backup drive yet"))
        return
    rule("FileBrowser")
    out("  Updating FileBrowser's drive folders: %s" % (s.detail() or "no backup drive yet"))
    s.run()
    good("FileBrowser now shows: %s" % s.detail())


def host_mount_types():
    try:
        return mount_types(open("/proc/self/mountinfo").read())
    except OSError:
        return {}


def homepage_sees_pools():
    """True when Homepage shows each pool the way the host has it (a mounted pool as a mounted pool, no pool as no pool).
    Homepage can only measure a pool that is a mount point inside its own container."""
    rc, txt = docker("exec", "homepage", "cat", "/proc/self/mountinfo", timeout=30)
    if rc != 0:
        return True          # cannot look inside: do not restart for nothing
    inside, host = mount_types(txt), host_mount_types()
    for pool in ("/mnt/storage", "/mnt/backup"):
        h = host.get(pool, "").startswith("fuse")
        c = inside.get(pool, "").startswith("fuse")
        if h != c:
            return False
    return True


def apply_pill_layout():
    """Put the shipped 'pill layout' block (taller top pills, search bar lower) into this machine's custom.css."""
    dst = hp_path("custom.css")
    shipped = css_block(read_file(repo_file("homepage-config", "custom.css")))
    cur = read_file(dst)
    if not shipped or not cur:
        return
    new = css_with_block(cur, shipped)
    if new == cur:
        return
    rule("Homepage")
    out("  Updating the look of the top pills in custom.css (taller pills, search bar a little lower). Reload the page to see it")
    write_file(dst, new, 0o644, (Ctx.uid, Ctx.gid))


def cmd_homepage():
    """Make Homepage see the Main and Backup pool (the two drive pills). sudo drives calls this by itself."""
    load_all()
    if "homepage" not in containers_all():
        say("Homepage is not installed on this machine.")
        return
    apply_pill_layout()
    changed = False
    manual = ("In Portainer open the stack 'homepage' > Editor. Replace the lines that mount /mnt/storage and /mnt/backup with this one line "
              "under volumes, then click Update the stack:\n      - %s" % HOMEPAGE_PARENT_LINE)
    if not Secrets.get("PORTAINER_TOKEN") or not Portainer.alive():
        warn("Portainer cannot be reached with a saved key, so the Homepage stack is not changed here. " + manual)
    else:
        s = next((x for x in Portainer.stacks() if x.get("Name") == "homepage"), None)
        if not s:
            warn("Portainer has no stack named 'homepage'. " + manual)
        else:
            eid = s.get("EndpointId") or Portainer.endpoint_id()
            st, js, _ = Portainer.call("GET", "/api/stacks/%s/file?endpointId=%s" % (s["Id"], eid), timeout=30)
            text = js.get("StackFileContent", "") if st == 200 and isinstance(js, dict) else ""
            if not text:
                warn("Could not read the Homepage stack from Portainer. " + manual)
            else:
                new = homepage_volumes(text)
                if new != text:
                    rule("Homepage")
                    out("  Letting Homepage see the pools: its stack mounts the whole /mnt folder now (Homepage restarts for a few seconds)")
                    if Opt.dry:
                        out("      would update the Homepage stack in Portainer")
                        return
                    env = [{"name": e["name"], "value": e["value"]} for e in (s.get("Env") or [])]
                    st, js, _ = Portainer.call("PUT", "/api/stacks/%s?endpointId=%s" % (s["Id"], eid),
                                               body={"stackFileContent": new, "env": env, "prune": False,
                                                     "pullImage": False, "repullImageAndRedeploy": False}, timeout=900)
                    if st not in (200, 201):
                        msg = js.get("details") or js.get("message") if isinstance(js, dict) else str(js)
                        raise Abort("Portainer refused to change the Homepage stack (HTTP %s): %s" % (st, str(msg)[:300]))
                    wait_for(lambda: stack_up("homepage"), "Homepage to restart", 120)
                    changed = True
    if not changed and "homepage" in containers_running() and not homepage_sees_pools():
        rule("Homepage")
        out("  Homepage does not see the pools the way they are mounted now. Restarting Homepage")
        if Opt.dry:
            out("      would restart Homepage")
            return
        act(["docker", "restart", "homepage"], timeout=120)
        wait_for(lambda: stack_up("homepage"), "Homepage to restart", 120)
        changed = True
    if changed:
        good("Homepage can see the Main and Backup pool")
    else:
        say("Homepage already sees the pools.")


def cmd_fill():
    """`fill`: enter the keys that cannot be created automatically."""
    load_all()
    res = evaluate()
    did = False
    rule("Walk-through")
    for s in topo():
        if res[s.id].state not in ("todo", "failed"):
            continue
        if s.kind == "ack":
            continue
        if type(s).fill is Step.fill:
            continue
        out("  %s%s%s" % (B, s.title, N))
        h = s.fill_help()
        if h:
            say(h, 4)
        if not yesno("Do this one now?", True):
            continue
        try:
            if s.fill():
                did = True
                good("Done: %s" % s.title)
                res = evaluate()
        except Abort as e:
            bad(str(e))
    if not did:
        say("No manual steps are waiting. Run `sudo homelab-setup refresh` to continue the automatic steps.")
    else:
        say("Run `sudo homelab-setup refresh` to continue.")


def cmd_mark(kind, sid):
    """`done` or `skip`: mark a step by hand."""
    load_all()
    if sid not in BY_ID:
        raise Abort("There is no step called '%s'. Names: %s" % (sid, ", ".join(s.id for s in STEPS if s.kind == "ack" or s.optional)))
    State.data[kind][sid] = time.strftime("%F %T")
    State.save()
    good("%s: %s" % ("Marked done" if kind == "ack" else "Skipped", BY_ID[sid].title))
    write_progress(evaluate())


def cmd_secrets():
    """`secrets`: show the generated passwords and keys."""
    load_all()
    if not Secrets.vals:
        say("No generated passwords or keys are stored on this machine.")
        return
    say("Saved in %s (root only):" % SECRET_FILE.replace(ROOT, ""))
    out("")
    for k in sorted(Secrets.vals):
        out("   %-28s %s" % (k, Secrets.vals[k]))
    out("")
    say("The admin password you chose is not stored. Keep it in your password manager.")
    if not State.readonly:
        State.data["secrets_shown"] = State.data.get("secrets_shown") or time.strftime("%F %T")
        State.save()
        write_progress(evaluate())


def uptime_seconds():
    """Seconds since the machine booted (HLS_UPTIME overrides it, for tests)."""
    try:
        return float(os.environ.get("HLS_UPTIME") or open("/proc/uptime").read().split()[0])
    except (OSError, ValueError, IndexError):
        return 1e9


def started_by_cron():
    """True when the output goes to /dev/null: the schedule started this, nobody is reading."""
    try:
        return os.stat("/dev/null").st_rdev == os.fstat(1).st_rdev and not os.isatty(1)
    except OSError:
        return False


def drop_progress_line():
    """Take the progress line out of root's crontab, so nothing keeps running for no reason."""
    if Opt.dry:
        return
    cur = crontab_text()
    kept = [l for l in cur.splitlines() if CRON_PROGRESS[0] not in l]
    if len(kept) != len(cur.splitlines()):
        run(["crontab", "-"], input_text="\n".join(kept) + "\n")


def cmd_progress():
    """`progress`: write the progress counts for the login screen.

    Run by the schedule it stays light: nothing in the first 10 minutes after a boot (apps are still
    starting, and a full check of every step would only slow the machine down), nothing while the saved
    counts are less than 50 minutes old, and once setup is finished the schedule line removes itself.
    """
    quiet = len(sys.argv) > 2 and sys.argv[2] == "--quiet"
    if quiet or started_by_cron():
        if uptime_seconds() < BOOT_GRACE:
            return
        try:
            if time.time() - os.path.getmtime(PROGRESS_FILE) < 50 * 60:
                return
        except OSError:
            pass            # no counts saved: either never written, or setup is finished; one check tells which
        try:
            os.nice(19)
        except OSError:
            pass
        quiet = True
    load_all()
    res = evaluate()
    write_progress(res)
    done, total = counts(res)
    if quiet:
        if done >= total:
            drop_progress_line()
        return
    out("%d of %d steps done" % (done, total))


HELP = """homelab-setup %s: set up this machine as a home lab from the GitHub repository.

Usage: sudo homelab-setup [command]

Commands:
  (none)                   show the checklist: what is done and what is left (add --details for full instructions)
  install                  set everything up (asks first; safe to run again)
  install --dry-run        show the plan and change nothing
  refresh                  re-check and continue every step that is now possible
  verify                   check that every container and service is up (also shown when all steps are done)
  fill                     walk through the logins and keys that need you
  filebrowser              update FileBrowser's drive folders after a drive was connected or removed
  homepage                 let Homepage see the Main and Backup pool, and update the look of the top pills
  done STEP | skip STEP    mark a manual step as done, or as not wanted
  secrets                  show the generated passwords and keys
  progress | version | help

Options for install:  --yes  --backup FOLDER  --no-restore  --repo FOLDER  --force-existing
The installer never formats or modifies a drive and never saves the admin password.
"""


def main(argv):
    """Read the command line and run the command."""
    import signal
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass
    args = list(argv[1:])
    i = 0
    cmd = None
    pos = []
    while i < len(args):
        a = args[i]
        if a in ("--dry-run", "-n"):
            Opt.dry = True
        elif a in ("--yes", "-y"):
            Opt.yes = True
        elif a == "--no-restore":
            Opt.no_restore = True
        elif a == "--force-existing":
            Opt.force_existing = True
        elif a == "--backup" and i + 1 < len(args):
            i += 1
            Opt.backup = args[i]
        elif a == "--repo" and i + 1 < len(args):
            i += 1
            Opt.repo = args[i]
        elif a in ("-h", "--help", "help"):
            out(HELP % VERSION)
            return 0
        elif a in ("--version", "version"):
            out("homelab-setup " + VERSION)
            return 0
        elif a == "--quiet":
            pass
        elif a in ("--all", "-a"):
            Opt.all = True
        elif a in ("--details", "-d"):
            Opt.details = True
        elif a.startswith("-"):
            out("Unknown option %s. Try: homelab-setup help" % a)
            return 1
        else:
            pos.append(a)
        i += 1
    cmd = pos[0] if pos else "checklist"
    if cmd not in ("checklist", "check", "install", "refresh", "fill", "done", "skip", "secrets", "progress", "verify", "filebrowser", "homepage"):
        out("Unknown command '%s'. Try: homelab-setup help" % cmd)
        return 1
    ensure_root()
    try:
        if cmd in ("checklist", "check"):
            cmd_checklist()
        elif cmd == "install":
            cmd_install()
        elif cmd == "refresh":
            cmd_refresh()
        elif cmd == "fill":
            cmd_fill()
        elif cmd in ("done", "skip"):
            if len(pos) < 2:
                out("Which step? Example: homelab-setup %s reboot-test" % cmd)
                return 1
            cmd_mark("ack" if cmd == "done" else "skip", pos[1])
        elif cmd == "secrets":
            cmd_secrets()
        elif cmd == "progress":
            cmd_progress()
        elif cmd == "verify":
            cmd_verify()
        elif cmd == "filebrowser":
            cmd_filebrowser()
        elif cmd == "homepage":
            cmd_homepage()
    except Abort as e:
        Live.close()
        out("")
        bad(str(e))
        return 1
    except KeyboardInterrupt:
        Live.close()
        out("")
        say("Stopped. Finished steps stay finished; run the same command again to continue.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
