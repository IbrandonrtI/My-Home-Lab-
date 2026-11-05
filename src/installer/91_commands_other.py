# ================================================================ more commands: adguard, cards, upgrade, filebrowser, homepage, fill, secrets, progress
def cmd_adguard():
    """`adguard`: add AdGuard Home to a machine that was installed without it."""
    load_all()
    if Mode.existing:
        say("This machine already runs AdGuard Home (the lab was built by hand). Nothing to add.")
        return
    if not State.exists():
        raise Abort("The installer has not run on this machine yet. Run `sudo homelab-setup install`.")
    if State.data["answers"].get("adguard") != "no":
        say("AdGuard Home is already part of this machine's setup. Continuing with whatever is left of it.")
        return cmd_refresh()
    out("")
    say("AdGuard Home blocks ads and trackers for every device on your network by acting as the network's DNS server. To do "
        "that it takes port 53 from this machine's built-in DNS resolver (which is stopped and disabled), and you then point "
        "each device at it.")
    if Opt.dry:
        say("This is a dry run: it would add AdGuard Home to the setup, put its card back on the Homepage dashboard and run "
            "the steps for it. Nothing was changed.")
        return
    if not Opt.yes and not yesno("Install AdGuard Home now?", True):
        say("Nothing was changed.")
        return
    State.data["answers"]["adguard"] = "yes"
    State.save()
    if os.path.exists(hp_path()) and hp_add_card("adguard-card"):
        good("The AdGuard Home card is back on the Homepage dashboard.")
    cmd_refresh()


LASTFM_KEY = re.compile(r"^[0-9a-fA-F]{32}$")


def cmd_lastfm(rest):
    """`lastfm`: save your own Last.fm API key and secret so Navidrome can suggest similar songs and artists (`lastfm remove` takes them out)."""
    load_all()
    if Mode.existing:
        say("This machine was built by hand, so the installer only reads it. Put the two Last.fm keys into the Navidrome stack in Portainer yourself.")
        return
    if not State.exists():
        raise Abort("The installer has not run on this machine yet. Run `sudo homelab-setup install`.")
    have = bool(Secrets.get("LASTFM_APIKEY"))
    if rest[:1] == ["remove"]:
        if not have:
            say("No Last.fm key is saved. Nothing to remove.")
            return
        if Opt.dry:
            say("This is a dry run: it would remove the saved Last.fm key and deploy Navidrome again. Nothing was changed.")
            return
        for k in ("LASTFM_APIKEY", "LASTFM_SECRET"):
            Secrets.vals.pop(k, None)
        Secrets.save()
        good("The Last.fm key was removed. Navidrome is deployed again without it.")
        return cmd_refresh()
    if rest:
        raise Abort("Unknown word '%s'. Use: homelab-setup lastfm   or   homelab-setup lastfm remove" % rest[0])
    out("")
    say("Navidrome can use Last.fm to suggest similar songs and artists (the Instant Mix of a song). You make a free key once:")
    say("  1. Sign in (or sign up) at https://www.last.fm\n"
        "  2. Open https://www.last.fm/api/account/create and fill in an application name (for example Home Lab) and a short description.\n"
        "  3. The page that follows shows an API key and a Shared secret. Copy both.")
    if have:
        warn("A Last.fm key is already saved. Typing a new one replaces it.")
    if Opt.dry:
        say("This is a dry run: it would ask for the two keys, save them (root only) and deploy Navidrome again. Nothing was changed.")
        return
    key = ask("API key").strip()
    secret = ask_secret("Shared secret").strip()
    if not LASTFM_KEY.match(key) or not LASTFM_KEY.match(secret):
        raise Abort("That does not look like a Last.fm key: the API key and the Shared secret are each 32 letters and digits. Nothing was saved.")
    Secrets.set("LASTFM_APIKEY", key.lower())
    Secrets.set("LASTFM_SECRET", secret.lower())
    good("The keys are saved in %s (root only). Deploying Navidrome with them ..." % SECRET_FILE.replace(ROOT, ""))
    cmd_refresh()
    say("Done. In Navidrome open a song's menu and choose Instant Mix. Optional: to also send what you play to Last.fm, click your name in Navidrome, "
        "then Personal, and link your Last.fm account there.")


def cmd_cards(rest):
    """`cards`: look for new services (containers with a web page) and give each its Homepage card; also move, ignore, list."""
    prog = installed_copy("homelab-cards", "/usr/local/sbin")
    if not prog:
        raise Abort("The helper homelab-cards is not installed yet. Run `sudo homelab-setup refresh` first.")
    if FAKE:
        say("(simulation) would run: homelab-cards %s" % " ".join(rest))
        return 0
    return subprocess.call([prog] + list(rest) + (["--dry-run"] if Opt.dry else []))


def cmd_upgrade():
    """`upgrade`: download the newest files from GitHub, then run the NEW installer's refresh, so every changed script,
    the installer itself and every new step are put on this machine in one go (no `sudo install` by hand)."""
    load_all()
    repo = Ctx.repo
    if not os.path.isdir(os.path.join(repo, ".git")):
        raise Abort("%s is not a copy downloaded with git, so it cannot be updated from GitHub.\n"
                    "Download the lab again:  git clone https://github.com/IbrandonrtI/My-Home-Lab-.git  and run  sudo bash setup.sh refresh  inside it." % repo)
    prefix = []
    if not FAKE and os.geteuid() == 0 and have("sudo"):
        try:     # git must run as the folder's owner: a root-owned .git folder would block your own git pull later
            owner = pwd.getpwuid(os.stat(repo).st_uid).pw_name
        except (KeyError, OSError):
            owner = ""
        if owner and owner != "root":
            prefix = ["sudo", "-u", owner]
    new_installer = repo_file("installer", "homelab-setup")
    if Opt.dry:
        say("Would download the newest files:  git -C %s pull --ff-only" % repo)
        say("Then would run the new installer:  homelab-setup refresh")
        return 0
    rule("Downloading the newest files from GitHub")
    rc, before = run(prefix + ["git", "-C", repo, "rev-parse", "HEAD"], timeout=30)
    before = before.strip() if rc == 0 else ""
    rc, text = run(prefix + ["git", "-C", repo, "pull", "--ff-only"], timeout=180)
    if rc != 0:
        tail = "\n".join(text.strip().splitlines()[-6:])
        raise Abort("The download from GitHub failed:\n%s\n"
                    "Is the machine online? Did you change files in %s by hand? (look:  git -C %s status)" % (tail, repo, repo))
    rc, after = run(prefix + ["git", "-C", repo, "rev-parse", "HEAD"], timeout=30)
    after = after.strip() if rc == 0 else ""
    if before and after and before == after:
        good("Already the newest version of the files.")
    elif before and after:
        rc, log_text = run(prefix + ["git", "-C", repo, "log", "--oneline", "-n", "8", "%s..%s" % (before, after)], timeout=30)
        good("New files downloaded:")
        for line in (log_text.strip().splitlines() if rc == 0 else []):
            out("      " + line)
    else:
        good("Files downloaded.")
    if not os.path.exists(new_installer):
        raise Abort("The downloaded files have no installer/homelab-setup. Look in %s." % repo)
    out("")
    say("Now putting the new scripts on this machine (with the new installer):")
    return subprocess.call([sys.executable, new_installer, "refresh"] + (["--repo", Opt.repo] if Opt.repo else []))


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
    """{mount point: file system type} as the host sees its own mounts."""
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


def apply_custom_css():
    """Move this machine's custom.css to the shipped, tidier layout (the old file is saved first)."""
    dst = hp_path("custom.css")
    cur = read_file(dst)
    new = css_new_layout(cur, read_file(repo_file("homepage-config", "custom.css"))) if cur else cur
    if new == cur:
        return
    rule("Homepage")
    out("  Moving custom.css to the new, tidier layout. Your accent colours, the numbers you changed and the homelab theme block are kept.")
    out("  The old file is saved as custom.css.before-layout2. Reload the page to see it (Ctrl+Shift+R)")
    write_file(dst + ".before-layout2", cur, 0o644, (Ctx.uid, Ctx.gid))
    write_file(dst, new, 0o644, (Ctx.uid, Ctx.gid))


def update_homepage_stack():
    """Make the Homepage stack in Portainer mount the whole /mnt folder (see homepage_volumes).
    Returns "changed", "unchanged", or "dry" (a dry run only said what it would do)."""
    manual = ("In Portainer open the stack 'homepage' > Editor. Replace the lines that mount /mnt/storage and /mnt/backup with this one line "
              "under volumes, then click Update the stack:\n      - %s" % HOMEPAGE_PARENT_LINE)
    if not Secrets.get("PORTAINER_TOKEN") or not Portainer.alive():
        warn("Portainer cannot be reached with a saved key, so the Homepage stack is not changed here. " + manual)
        return "unchanged"
    stack = Portainer.stack_named("homepage")
    if not stack:
        warn("Portainer has no stack named 'homepage'. " + manual)
        return "unchanged"
    text = Portainer.stack_file(stack)
    if not text:
        warn("Could not read the Homepage stack from Portainer. " + manual)
        return "unchanged"
    new = homepage_volumes(text)
    if new == text:
        return "unchanged"
    rule("Homepage")
    out("  Letting Homepage see the pools: its stack mounts the whole /mnt folder now (Homepage restarts for a few seconds)")
    if Opt.dry:
        out("      would update the Homepage stack in Portainer")
        return "dry"
    env = [{"name": e["name"], "value": e["value"]} for e in (stack.get("Env") or [])]
    st, js = Portainer.redeploy(stack, new, env)
    if st not in (200, 201):
        raise Abort("Portainer refused to change the Homepage stack (HTTP %s): %s" % (st, Portainer.error_text(js)[:300]))
    wait_for(lambda: stack_up("homepage"), "Homepage to restart", 120)
    return "changed"


def restart_homepage_if_blind():
    """Restart Homepage when it does not see the pools the way the host has them mounted.
    Returns "changed", "unchanged", or "dry"."""
    if "homepage" not in containers_running() or homepage_sees_pools():
        return "unchanged"
    rule("Homepage")
    out("  Homepage does not see the pools the way they are mounted now. Restarting Homepage")
    if Opt.dry:
        out("      would restart Homepage")
        return "dry"
    act(["docker", "restart", "homepage"], timeout=120)
    wait_for(lambda: stack_up("homepage"), "Homepage to restart", 120)
    return "changed"


def cmd_homepage():
    """Make Homepage see the Main and Backup pool (the two drive pills). sudo drives calls this by itself."""
    load_all()
    if "homepage" not in containers_all():
        say("Homepage is not installed on this machine.")
        return
    apply_custom_css()
    result = update_homepage_stack()
    if result == "unchanged":                 # the stack was fine; the container may still be looking at an old mount
        result = restart_homepage_if_blind()
    if result == "dry":
        return
    if result == "changed":
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
    show_secret_values()
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
  upgrade                  download the newest files from GitHub and put the new scripts on this machine (one step)
  growdisk                 give the unused space of the drive to the system volume (LVM, Ubuntu Server); it asks first
  verify                   check that every container and service is up (also shown when all steps are done)
  fill                     walk through the logins and keys that need you
  filebrowser              update FileBrowser's drive folders after a drive was connected or removed
  homepage                 let Homepage see the Main and Backup pool, and move custom.css to the current layout
  adguard                  add AdGuard Home, if you skipped it during the install
  cards                    give every new service (a container with a web page) its Homepage card; also: cards list | move | ignore
  lastfm                   save your free Last.fm key so Navidrome can suggest similar songs; also: lastfm remove
  done STEP | skip STEP    mark a manual step as done, or as not wanted
  secrets                  show the generated passwords and keys
  progress | version | help

Options for install:  --yes  --backup FOLDER  --no-restore  --repo FOLDER  --force-existing
The installer never formats or erases a drive and never saves the admin password. The one change it can make to the drive layout
is growing an LVM system volume into unused space of its drive, and only after you say yes.
"""


# every command that needs no more than its name (done STEP and skip STEP also take the step)
COMMANDS = {"checklist": cmd_checklist, "check": cmd_checklist, "install": cmd_install, "refresh": cmd_refresh, "fill": cmd_fill,
            "secrets": cmd_secrets, "progress": cmd_progress, "verify": cmd_verify, "filebrowser": cmd_filebrowser,
            "homepage": cmd_homepage, "adguard": cmd_adguard, "upgrade": cmd_upgrade, "growdisk": cmd_growdisk}
