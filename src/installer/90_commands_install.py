# ================================================================ commands: install, refresh, verify, checklist, growdisk
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
    warn("One password is used for every admin login (Portainer, %sBeszel, Immich, Nextcloud, FileBrowser, "
         "Speedtest Tracker). If one service leaks it, all of them are exposed. Homepage's configuration file also stores "
         "some of these logins in plain text. Use a long password that you use nowhere else and keep it in a password "
         "manager." % ("AdGuard Home, " if adguard_wanted() else ""))


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


LVM_EXPLAIN = ("Ubuntu Server's installer makes the system volume small (about 100 GB) and leaves the rest of the drive unused. "
               "Using that space makes the system volume bigger. Nothing is erased and nothing moves: your files stay as they "
               "are, and it is done while the machine runs. It is needed if you want to use part of this drive as a storage "
               "pool later (sudo drives bootsection). A volume grows easily but only shrinks with effort.")


def lvm_question(info):
    """The question about unused space in the system volume's drive."""
    out("")
    say("This machine's system volume is %s, but its drive has another %s that nothing uses." %
        (pretty_size(info["size"]), pretty_size(info["free"])))
    say(LVM_EXPLAIN)
    return yesno("Give the unused space to the system volume?", True)


def ask_grow_boot_volume(a):
    """Install question: offer to use the unused space of an LVM system volume (asked once; the answer is kept)."""
    if "lvm_grow" in a:
        return
    info = root_lvm_info()
    if not info or info["free"] < LVM_MIN_FREE:
        return
    a["lvm_grow"] = "yes" if lvm_question(info) else "no"
    State.save()


def grow_boot_volume():
    """Make the system volume use all the unused space of its volume group. Returns True when it grew."""
    info = root_lvm_info()
    if not info or info["free"] < LVM_MIN_FREE:
        return False
    out("")
    rule("Using the unused space of the drive")
    say("Growing the system volume from %s by %s ..." % (pretty_size(info["size"]), pretty_size(info["free"])))
    rc, text = act(["lvextend", "-r", "-l", "+100%FREE", info["src"]], timeout=900)
    if rc != 0:
        warn("The system volume could not be made bigger, so nothing was changed. The reason:\n      %s\n"
             "      You can try again later:  sudo homelab-setup growdisk" % "\n      ".join(text.strip().splitlines()[-4:]))
        return False
    if not Opt.dry:
        good("The system volume is now bigger.")
        State.data["answers"]["lvm_grow"] = "done"
        State.save()
    return True


def cmd_growdisk():
    """`growdisk`: give the unused space of the drive to the system volume (LVM only), after asking."""
    info = root_lvm_info()
    if not info or info["free"] < LVM_MIN_FREE:
        out("")
        say("Nothing to do: the system volume already uses its whole drive, or it is not an LVM volume with room to grow.")
        return
    if not lvm_question(info):
        say("Okay, nothing was changed.")
        return
    grow_boot_volume()


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
    if "adguard" not in a:
        out("")
        say("AdGuard Home blocks ads and trackers for every device on your network by acting as the network's DNS server. To do "
            "that it takes port 53 from this machine's built-in DNS resolver, and you then point each device at it. You can "
            "skip it now and add it later with:  sudo homelab-setup adguard")
        a["adguard"] = "yes" if yesno("Install AdGuard Home?", True) else "no"
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


def show_secret_values():
    """The generated passwords and keys, one per line."""
    out("")
    for k in sorted(Secrets.vals):
        out("   %-28s %s" % (k, Secrets.vals[k]))
    out("")


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
        show_secret_values()
        say("Show them again at any time:\n$ sudo homelab-setup secrets")
        say("The admin password you chose is not stored anywhere. Keep it in your password manager.")
        out("")
        if interactive() and not Opt.yes:
            ask("Press Enter when they are saved to see what is left")
            State.data["secrets_shown"] = time.strftime("%F %T")        # ticks "passwords copied into your password manager"
            State.save()
            res = evaluate()
            write_progress(res)
    offer_drive_wizard()
    show_checklist(res, "Setup")
    next_step_section(res)


def offer_drive_wizard():
    """End of the first install: when no storage exists yet, let `sudo drives wizard` look at the drives and offer a setup (once).
    The wizard itself stays silent when storage is already set up, and it formats nothing before the person has read the plan and typed ERASE."""
    if FAKE or Opt.yes or Opt.dry or not interactive() or State.data.get("wizard_offered"):
        return
    drives = P("/usr/local/sbin/drives")
    if not os.path.exists(drives) or os.path.ismount(P("/mnt/storage")):
        return
    State.data["wizard_offered"] = time.strftime("%F %T")
    State.save()
    rule("Your drives")
    say("Next the drive wizard looks at the drives that are plugged in and can suggest a ready-made setup. "
        "Nothing is changed unless you pick one, read its plan and type ERASE. Run it again any time:\n$ sudo drives wizard")
    try:
        subprocess.call([drives, "wizard", "--first-run"])
    except OSError as e:
        warn("Could not start the drive wizard (%s). Run it later:  sudo drives wizard" % e)


SERVICE_LABELS = [("homepage", "Homepage"), ("portainer", "Portainer"), ("adguard", "AdGuard Home"), ("beszel", "Beszel"),
                  ("netdata", "Netdata"), ("speedtest", "Speedtest Tracker"), ("filebrowser", "FileBrowser"),
                  ("immich", "Immich"), ("nextcloud", "Nextcloud")]


def navidrome_wanted():
    """True when this machine is meant to run Navidrome (it has a music folder)."""
    return BY_ID["stack-navidrome"].applies()


def added_services():
    """Services added after the install: Navidrome (when set up) and every card that `homelab-cards` made.
    Returns [(label, container, local port, Tailscale port or 0)], sorted by label."""
    found = {}
    try:
        managed = json.loads(read_file(PROGRESS_DIR + "/cards.json") or "{}").get("managed", {})
        for container, m in managed.items():
            if m.get("hostport"):
                found[container] = (m.get("name") or container, container, int(m["hostport"]), int(m.get("serve") or 0))
    except (ValueError, AttributeError, TypeError):
        pass                                                  # an unreadable list only means "nothing added"
    if navidrome_wanted() and "navidrome" not in found:
        found["navidrome"] = ("Navidrome", "navidrome", PORTS["navidrome"], 0)
    return sorted(found.values(), key=lambda x: x[0].lower())


def system_check():
    """Look at the running system and report whether everything is up. Returns the number of problems."""
    rule("System check")
    problems = []
    names = ["portainer"] + [c for n in STACK_ORDER for c in STACKS[n][1] if n != "adguard" or adguard_wanted()]
    if navidrome_wanted():
        names.append("navidrome")
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
        if key == "adguard" and not adguard_wanted():
            continue
        st = http("GET", url(key), timeout=10)[0]
        if 0 < st < 500:
            out("  %s%s%s %-18s %s" % (G, S_OK, N, label, mark(url(key))))
        else:
            out("  %s%s%s %-18s %s  (no answer)" % (R, S_BAD, N, label, mark(url(key))))
            problems.append(key)
    extras = added_services()
    if extras:
        out("")
        out("  %sOther services%s" % (B, N))
        for label, container, port, _ in extras:
            link = "http://%s:%d" % (svc_host(), port)
            st = http("GET", link, timeout=10)[0]
            if 0 < st < 500:
                out("  %s%s%s %-18s %s" % (G, S_OK, N, label, mark(link)))
            elif container == "navidrome":                    # the installer owns Navidrome, so a silent one is a problem
                out("  %s%s%s %-18s %s  (no answer)" % (R, S_BAD, N, label, mark(link)))
                problems.append(container)
            else:                                             # a service the person added: stopping it can be on purpose
                out("  %s%s%s %-18s %s  (no answer: is the container running?)" % (Y, S_WAIT, N, label, mark(link)))
    if Ctx.fqdn:
        out("")
        out("  %sServices over Tailscale%s %s(use these from your other devices; a machine cannot open its own Tailscale addresses)%s" % (B, N, D, N))
        for port, key in serve_items():
            label = dict(SERVICE_LABELS)[key]
            out("    %-18s %s" % (label, mark("https://%s:%d" % (Ctx.fqdn, port))))
        for label, _, _, port in extras:
            if port:
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
    "Network": "keeps DNS working and frees port 53 for AdGuard Home (if you chose it)",
    "Platform": "folders, generated passwords and Portainer, which deploys the apps",
    "Services": "downloads and starts the apps (the longest part)",
    "Logins and keys": "creates the admin accounts and API keys inside the apps",
    "Homepage": "connects the dashboard widgets to the apps",
    "Scripts and schedule": "helper commands, scheduled jobs and the login screen",
    "Your devices and drives": "things only you can do",
}


def welcome():
    """Print the welcome screen."""
    say("This turns this machine into a home lab: Docker, Tailscale and up to nine apps (Homepage, Portainer, AdGuard Home "
        "(optional, you are asked), Beszel, Netdata, Speedtest Tracker, FileBrowser, Immich and Nextcloud), with their logins "
        "and dashboard widgets.")
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


def plan_install(res):
    """Sort the open steps into (todo, later, by_hand): the ones the installer runs now, the ones it runs by itself once
    a step that needs the person is done, and the ones only the person can do."""
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
    return todo, later, by_hand


def by_hand_tag(s):
    """When the person will be asked to do this step."""
    if s.id in DURING_INSTALL:
        return "during the install"
    if s.id == "secrets-saved":
        return "at the end of the install, when you press Enter after copying them"
    if getattr(s, "auto", None):
        return "afterwards, detected automatically once done"
    return "afterwards"


def show_plan(todo, later, by_hand):
    """Print what the install will do, and what needs the person."""
    rule("Planned steps")
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
            out("   %s%s%s %s  %s(%s)%s" % (Y, S_TODO, N, s.title, D, by_hand_tag(s), N))


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
        ask_grow_boot_volume(State.data["answers"])
        ask_restore_plan()
    else:
        if not Ctx.admin:
            Ctx.admin = Ctx.user.capitalize()
        if not Ctx.email:
            Ctx.email = "you@example.com"
        info = root_lvm_info()
        if info and info["free"] >= LVM_MIN_FREE:
            say("Would offer: give the %s the drive has left over to the system volume (now %s). It only grows the volume; nothing is erased." %
                (pretty_size(info["free"]), pretty_size(info["size"])))
    if State.ran("install-started"):
        wait_for_apps()
    res = evaluate()
    todo, later, by_hand = plan_install(res)
    if not todo and not by_hand and not later:
        out("")
        say("Nothing to do: all steps are complete.")
        show_checklist(res, "Setup")
        next_step_section(res)
        return
    show_plan(todo, later, by_hand)
    during = [s for s in by_hand if s.id in DURING_INSTALL]
    out("")
    if not Opt.dry and not Opt.yes:
        if not typed("yes", "Type yes to start (nothing has been changed yet)"):
            raise Abort("Stopped. Nothing was changed.")
    if not Opt.dry:
        State.mark("install-started")
        if State.data["answers"].get("lvm_grow") == "yes":
            grow_boot_volume()
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
        if not Opt.dry:
            res.update(evaluate())
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
