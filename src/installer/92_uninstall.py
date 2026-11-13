# ================================================================ uninstall: take the lab off this machine again
# `sudo homelab-setup uninstall` removes what this repository put on the machine (the containers, the scripts, the schedule, the control panel,
# the Tailscale addresses, the pool settings) and leaves what other things may use: Tailscale itself (still logged in), Docker, and the drive and
# helper programs (mergerfs, SnapRAID, mdadm, ZFS, smartmontools ...). Two questions decide what happens to your things:
#   1. the apps' own data (photos, Nextcloud files, databases, settings): keep it, or wipe it
#   2. the drives of the pools: keep every file on them (the pools are only taken apart), or erase them (each one needs typed words)
# Nothing is changed before a last "UNINSTALL" is typed. `--dry-run` shows everything and changes nothing.

UN_UNITS = [("homelab-terminal", TERMINAL_UNIT), ("homelab-panel", PANEL_UNIT), ("homelab-storage-guard", GUARD_UNIT)]


def un_drives_tool():
    """The drives tool to run. In the test machine only a stand-in named in HLS_DRIVES is ever run (the real one would touch the test computer)."""
    forced = os.environ.get("HLS_DRIVES")
    if forced:
        return forced
    return None if FAKE else "/usr/local/sbin/drives"


def un_container_names():
    """The HomeLab containers that exist on this machine (running or not)."""
    names = ["portainer"]
    for _, cs in STACKS.values():
        names += cs
    present = containers_all()
    return [n for n in dict.fromkeys(names) if n in present]


def un_serve_ports():
    """The Tailscale Serve ports that point at HomeLab's own services (a port that points somewhere else is not ours and stays)."""
    if not have("tailscale"):
        return []
    rc, txt = run(["tailscale", "serve", "status", "--json"], timeout=20)
    try:
        js = json.loads(txt) if rc == 0 else {}
    except ValueError:
        js = {}
    ours = {p: PORTS[s] for p, s in SERVE}
    ours[PANEL_HTTPS] = PANEL_PORT
    # the addresses homelab-cards gave to the containers you added yourself (1009 and up) are written down in its list
    try:
        cards = json.loads(read_file(P("/var/lib/homelab/cards.json")) or "{}").get("managed") or {}
    except ValueError:
        cards = {}
    extra = {int(m["serve"]) for m in cards.values() if isinstance(m, dict) and str(m.get("serve") or "").isdigit()}
    found = []
    for k, v in (js.get("Web") or {}).items():
        m = re.search(r":(\d+)$", k)
        if not m:
            continue
        port = int(m.group(1))
        prox = ((v.get("Handlers") or {}).get("/") or {}).get("Proxy", "")
        if port in extra or (port in ours and re.search(r":%d/?$" % ours[port], prox)):
            found.append(port)
    return sorted(found)


def un_data_dirs():
    """The folders that hold the apps' own data and settings (the music library is NOT in this list: those are your songs)."""
    h = Ctx.home
    dirs = [h + "/nextcloud", h + "/immich", h + "/speedtest-tracker", h + "/homepage-config", h + "/audiomuse", h + "/navidrome", h + "/navilist",
            "/opt/adguard-docker", "/mnt/storage/immich", "/mnt/storage/nextcloud", boot_share_dir()]
    return [d for d in dirs if os.path.isdir(P(d))]


def un_dir_size(path):
    """A short size of a folder ('' when it takes too long to add up)."""
    rc, txt = run(["du", "-sb", P(path)], timeout=10)
    if rc != 0 or not txt.split():
        return ""
    try:
        return pretty_size(int(txt.split()[0]))
    except ValueError:
        return ""


def un_array_kind():
    """'zfs' or 'md' when the Main pool is a real RAID / ZFS array (it cannot be taken apart without erasing it), else ''."""
    first = read_file(P("/var/lib/homelab-drives/preset")).split("|")[0].strip()
    return first.split("-")[0] if first.startswith(("zfs-", "md-")) else ""


def un_run_drives(*args, quiet=False):
    """Run the drives tool. Returns (exit code, output)."""
    tool = un_drives_tool()
    if not tool:
        return 127, ""
    if quiet:
        return run([tool] + list(args), timeout=120)
    return subprocess.call([tool] + list(args)), ""


def un_disk_of(dev):
    """The whole drive a device path belongs to (/dev/sdb1 -> /dev/sdb)."""
    rc, txt = run(["lsblk", "-no", "pkname", dev], timeout=20)
    parent = txt.split()[0] if rc == 0 and txt.split() else ""
    if parent:
        return "/dev/" + parent
    m = re.match(r"^(/dev/(?:nvme\d+n\d+|mmcblk\d+|loop\d+))p\d+$", dev) or re.match(r"^(/dev/(?:[sv]d[a-z]+|xvd[a-z]+))\d+$", dev)
    return m.group(1) if m else dev


def un_pool_drives():
    """(how many entries the pools have, [(name, /dev/xxx of the whole drive, size in bytes)]) for the drives in the pools right now. The sections of the
    boot drive count as entries but are not listed as drives. None when the drives tool cannot be asked."""
    tool = un_drives_tool()
    if not tool or not os.path.exists(tool):
        return None
    rc, txt = un_run_drives("status", "--json", quiet=True)
    try:
        js = json.loads(txt) if rc == 0 else None
    except ValueError:
        js = None
    if js is None:
        return None
    found = []
    # `status` lists every drive of the machine: only the ones with a pool role are the pools' (spare, system and plain-data drives are not)
    rows = [d for d in js.get("drives") or [] if d.get("role") in ("main", "backup", "parity")]
    for d in rows:
        dev = d.get("device") or ""
        if not dev.startswith("/dev/"):      # a section of the boot drive has "boot drive" there, a drive that is not plugged in "-"
            continue
        disk = un_disk_of(dev)
        if disk not in [x[1] for x in found]:
            found.append((d.get("name") or disk, disk, d.get("size_bytes") or 0))
    return len(rows), found


def un_spare_disks():
    """The drives `sudo drives` would let you erase right now (a drive in a pool or the boot drive is never in this list)."""
    rc, txt = un_run_drives("panel", "actions", quiet=True)
    try:
        js = json.loads(txt) if rc == 0 else {}
    except ValueError:
        js = {}
    return {s.get("device"): s for s in js.get("spare") or [] if s.get("device")}


def un_facts():
    """Everything the uninstall would touch, looked up once."""
    f = {}
    f["containers"] = un_container_names()
    f["serve"] = un_serve_ports()
    f["units"] = [u for u, path in UN_UNITS if os.path.exists(P(path))]
    f["scripts"] = [w + "/" + n for n, w in SCRIPTS if os.path.exists(P(w + "/" + n))]
    f["scripts"] += [p for p in RETIRED_SCRIPTS if os.path.exists(P(p))]
    f["cron"] = [l for l in crontab_text().splitlines() if un_cron_match(l)]
    f["data"] = [(d, un_dir_size(d)) for d in un_data_dirs()]
    f["array"] = un_array_kind()
    pools = None if f["array"] else un_pool_drives()
    f["pools"] = pools[0] if pools else 0
    f["drives"] = pools[1] if pools else []
    f["pools_known"] = pools is not None
    f["boot_sections"] = sorted(glob.glob(P("/var/lib/homelab-boot-sections") + "/*.img"))
    f["music"] = music_folder()
    f["adguard"] = "adguardhome" in f["containers"]
    return f


def un_cron_match(line):
    """True for a line of root's crontab that HomeLab put there (lines you added yourself never match)."""
    s = line.strip()
    if not s or s.startswith("#"):
        return False
    return (s in [l for _, l in CRON_LINES] or s == CRON_PROGRESS[1] or "/usr/local/sbin/homelab" in s or "/usr/local/bin/homelab" in s
            or "/usr/local/sbin/drives " in s or bool(OLD_BACKUP_LINE.match(line)))


def un_menu(question, options, default="1"):
    """Ask for one of the numbered options; returns its number as text."""
    out("")
    say(question)
    for i, text in enumerate(options, 1):
        for j, l in enumerate(styled(text, 8)):
            out(("     %d) " % i + l[8:]) if j == 0 else l)
    while True:
        a = ask("Type %s" % " or ".join(str(i) for i in range(1, len(options) + 1)), default)
        if a in [str(i) for i in range(1, len(options) + 1)]:
            return a
        say("Please type one of the numbers.")


def un_show_plan(f):
    """The list of what goes and what stays."""
    rule("What the uninstall will do")
    say("These parts of HomeLab will be REMOVED:")
    if f["containers"]:
        say("  - %d containers (%s) and their images; Portainer, the dashboard and every service" % (len(f["containers"]), ", ".join(f["containers"][:6]) + (", ..." if len(f["containers"]) > 6 else "")))
    if f["serve"]:
        say("  - the %d Tailscale addresses HomeLab set up, also the ones it gave to apps you added yourself (ports %s)" % (len(f["serve"]), ", ".join(str(p) for p in f["serve"])))
    if f["units"]:
        say("  - the control panel and the web terminal (services %s)" % ", ".join(f["units"]))
    if f["cron"]:
        say("  - %d scheduled jobs in root's crontab (your own lines stay)" % len(f["cron"]))
    if f["scripts"]:
        say("  - %d programs HomeLab installed (%s ...)" % (len(f["scripts"]), ", ".join(os.path.basename(s) for s in f["scripts"][:4])))
    say("  - HomeLab's settings files, the login screen in %s/.bashrc, and the record of what was installed" % Ctx.home)
    if f["pools"]:
        say("  - the drive pools (Main and Backup): taken apart%s" % ((". The drives are " + ", ".join("%s (%s)" % (n, pretty_size(int(s))) if s else n for n, _, s in f["drives"])) if f["drives"] else ""))
    out("")
    say("These STAY on the machine:")
    say("  - Tailscale (still logged in; only HomeLab's addresses are removed)")
    say("  - Docker (only HomeLab's containers, images and networks go; any container of your own stays)")
    say("  - mergerfs, SnapRAID, mdadm, ZFS, smartmontools and the other helper programs")
    say("  - your music files%s" % (" in %s" % f["music"] if f["music"] else ""))
    say("  - the downloaded copy of this repository (%s)" % Ctx.repo)
    if f["array"]:
        out("")
        warn("The Main pool is a %s array. An array cannot be taken apart without erasing it, so it is LEFT AS IT IS, with all its files. "
             "The drives tool stays installed so you can still manage it with `sudo drives`." % {"zfs": "ZFS", "md": "RAID"}[f["array"]])
    if f["adguard"]:
        out("")
        warn("AdGuard Home is your DNS ad blocker. If your router or your devices use this machine as their DNS server, point them back to "
             "your router (or another DNS server) now, or they will not find any website once AdGuard Home is gone.")


def un_ask_choices(f):
    """The two questions. Returns (wipe_data, wipe_drives)."""
    wipe_data = wipe_drives = False
    if f["data"] or f["containers"]:
        if Opt.yes:
            wipe_data = Opt.wipe_data
        else:
            lines = ["  %s%s" % (d, ("  (%s)" % s) if s else "") for d, s in f["data"]]
            out("")
            say("The apps keep their own data in these folders (and in Docker volumes):\n" + "\n".join(lines))
            a = un_menu("What should happen to the data of the apps (photos, Nextcloud files, Navidrome playlists, AdGuard settings, Beszel history, dashboard settings, passwords)?",
                        ["KEEP it. The apps are removed, the data stays where it is. Installing again later finds it and goes on where you stopped. (Recommended)",
                         "WIPE it. Everything the apps stored is deleted for good. Your music files are never deleted by this."])
            wipe_data = a == "2"
    if f["drives"] or f["boot_sections"] or f["pools"]:
        if Opt.yes:
            wipe_drives = Opt.wipe_drives
        else:
            a = un_menu("What should happen to the drives of the pools?",
                        ["KEEP the files. The pools are taken apart (HomeLab's mount settings are removed) but every file stays on the drives, and each drive can be read normally. (Recommended)",
                         "WIPE the drives. Every drive is erased after the pools are taken apart. You will be asked to type the name of each drive and ERASE before it is erased."])
            wipe_drives = a == "2"
        if wipe_drives and not wipe_data and not Opt.yes and (f["data"] or f["containers"]):
            out("")
            warn("You chose to keep the app data but to erase the drives. The photos and files the apps keep on those drives will be gone too. "
                 "Only the settings in your home folder and the Docker volumes would be kept.")
            if not yesno("Go on with this choice?", False):
                return un_ask_choices(f)
    return wipe_data, wipe_drives


def un_confirm(wipe_data, wipe_drives):
    """The last stop. Nothing has been changed before this."""
    out("")
    if wipe_data:
        warn("The data of the apps will be DELETED and cannot be brought back.")
    if wipe_drives:
        warn("The drives of the pools will be ERASED (each one asks for its own typed words first).")
    if Opt.yes or Opt.dry:
        return True
    if ask("Type UNINSTALL (capitals) to start, or press Enter to cancel").strip() != "UNINSTALL":
        return False
    if wipe_data and ask("The data of the apps will be deleted for good. Type DELETE (capitals) to confirm, or press Enter to cancel").strip() != "DELETE":
        return False
    return True


# ---------------------------------------------------------------- the removal steps
def un_rm(path):
    """Delete a file, a link or a folder (a dry run only says so). True when something was there."""
    p = P(path)      # `path` is the path on the machine (the test machine puts it under its fake root)
    if not os.path.lexists(p):
        return False
    if Opt.dry:
        out("      would delete: %s" % path)
        return True
    if os.path.isdir(p) and not os.path.islink(p):
        shutil.rmtree(p)
    else:
        os.remove(p)
    return True


def un_remove_cron():
    n = crontab_remove(un_cron_match)
    if n:
        good("%d scheduled job(s) removed from root's crontab (a copy of the old crontab is in %s)" % (n, SECRET_DIR))
    return True


def un_stop_services():
    if run(["systemctl", "is-active", FINISH_UNIT])[1].strip() in ("active", "activating"):
        act(["systemctl", "stop", FINISH_UNIT])         # the job that finishes the install (its status and lock files go with the folders below)
    for unit, path in UN_UNITS:
        if os.path.exists(P(path)) or run(["systemctl", "is-active", unit])[1].strip() == "active":
            act(["systemctl", "stop", unit])
            act(["systemctl", "disable", unit])
            un_rm(path)
    act(["systemctl", "daemon-reload"])
    un_rm(PANEL_SUDOERS)
    un_rm(PANEL_SHARE)
    un_rm(Ctx.home + "/.config/homelab-panel")
    good("The control panel and the web terminal are stopped and removed")
    return True


def un_remove_serve(ports):
    for p in ports:
        rc, txt = act(["tailscale", "serve", "--https=%d" % p, "off"], timeout=60)
        if rc != 0 and not Opt.dry:
            warn("Tailscale would not remove port %d: %s" % (p, txt.strip()[-150:]))
    if ports:
        good("%d Tailscale address(es) removed (Tailscale itself stays logged in)" % len(ports))
    return True


def un_remove_containers(names, wipe_data):
    """Remove the containers, their networks and images; the Docker volumes only when the data is wiped (Portainer's own volume always)."""
    if not names:
        return True
    images, projects = [], set()
    for n in names:
        rc, txt = docker("inspect", "-f", '{{.Config.Image}}|{{index .Config.Labels "com.docker.compose.project"}}', n, timeout=30)
        if rc == 0 and "|" in txt:
            img, proj = txt.strip().split("|", 1)
            if img and img not in images:
                images.append(img)
            if proj and proj != "<no value>":
                projects.add(proj)
    rc, txt = act(["docker", "rm", "-f"] + names, timeout=600)
    if rc != 0 and not Opt.dry:
        warn("Docker could not remove every container: %s" % txt.strip()[-200:])
    good("%d container(s) removed" % len(names))
    for proj in sorted(projects):
        for kind, flag in (("network", True), ("volume", wipe_data)):
            rc, ids = docker(kind, "ls", "-q", "--filter", "label=com.docker.compose.project=%s" % proj, timeout=30)
            ids = ids.split() if rc == 0 else []
            if ids and flag:
                act(["docker", kind, "rm"] + ids, timeout=120)
    if "portainer" in names:
        act(["docker", "volume", "rm", "portainer_data"], timeout=60)
    for img in images:
        act(["docker", "image", "rm", img], timeout=180)
    good("The networks and the images of the lab are removed%s" % (" and so are the volumes with the apps' data" if wipe_data else "; the Docker volumes with the apps' data are kept"))
    return True


def un_on_pool(path):
    """True when the folder is on a mounted pool (/mnt/storage or /mnt/backup)."""
    return any(path == m or path.startswith(m + "/") for m in ("/mnt/storage", "/mnt/backup")) and any(os.path.ismount(P(m)) for m in ("/mnt/storage", "/mnt/backup"))


def un_wipe_data(skip_pools, announce=True):
    """Delete the apps' folders. With skip_pools the folders on the pools stay (the drives are erased anyway, and deleting terabytes first takes hours)."""
    for d in un_data_dirs():
        if skip_pools and un_on_pool(d):
            continue
        if os.path.ismount(P(d)):
            warn("%s is a drive of its own and was left alone." % d)
            continue
        un_rm(d)
    if announce:
        good("The data of the apps is deleted")
    return True


def un_release_drives(f, wipe_drives):
    """Take the pools apart (every file stays on the drives), then erase the drives when asked to."""
    if not un_drives_tool():
        say("(simulation) the drives tool would run here")
        return True
    if f["pools_known"] and not f["pools"]:
        return True      # no drive is in a pool: nothing to take apart
    args = ["release", "--yes", "--now"] + (["--dry-run"] if Opt.dry else [])
    out("")
    say("Taking the pools apart (the drives tool does this and says what it does):")
    rc, _ = un_run_drives(*args)
    if rc != 0:
        warn("The drives tool did not finish (exit code %d). The drives were NOT erased. Look at the messages above, then run `sudo drives release`." % rc)
        return False
    good("The pools are taken apart; every file is still on its drive")
    if not wipe_drives or Opt.dry:
        if wipe_drives and Opt.dry:
            for n, dev, _ in f["drives"]:
                say("Would erase %s (%s) after you type its name and ERASE." % (n, dev))
        return True
    spare = un_spare_disks()
    ok = True
    for name, dev, size in f["drives"]:
        info = spare.get(dev)
        if not info:
            warn("%s (%s) is not ready to be erased (it is in use, not plugged in, or it holds the operating system). It was left alone." % (name, dev))
            ok = False
            continue
        out("")
        warn("ERASE %s (%s, %s). Everything on this drive will be deleted for good." % (name, dev, pretty_size(int(size)) if size else "?"))
        if ask("Type the drive name (%s) to erase it, or press Enter to keep it" % dev).strip() != dev:
            say("%s was kept." % name)
            continue
        if ask("Type ERASE (capitals) to confirm").strip() != "ERASE":
            say("%s was kept." % name)
            continue
        rc, txt = un_run_drives("panel", "wipe", info["id"], "empty", dev, "ERASE", quiet=True)
        if rc == 0:
            good("%s is erased" % name)
        else:
            warn("%s could not be erased: %s" % (name, txt.strip()[-200:]))
            ok = False
    for img in f["boot_sections"]:
        un_rm(img)
    if f["boot_sections"]:
        good("The files of the boot drive sections are deleted")
    return ok


def un_remove_login_block():
    path = P(Ctx.home + "/.bashrc")
    cur = read_file(path)
    if "# >>> homelab login display >>>" not in cur:
        return True
    new = re.sub(r"\n?# >>> homelab login display >>>.*?# <<< homelab login display <<<\n", "\n", cur, flags=re.S)
    if Opt.dry:
        out("      would take the HomeLab login screen out of %s" % path)
        return True
    write_file(path + ".before-uninstall", cur, 0o644, (Ctx.uid, Ctx.gid))
    write_file(path, new, 0o644, (Ctx.uid, Ctx.gid))
    good("The HomeLab login screen is taken out of ~/.bashrc (a copy is ~/.bashrc.before-uninstall)")
    return True


def un_restore_dns(f):
    """HomeLab turned the system's own DNS resolver off so AdGuard Home could use port 53. Turn it on again.
    Tailscale is NOT told to manage DNS again: HomeLab set it to leave /etc/resolv.conf alone because Tailscale's own resolver (100.100.100.100) can lose
    its upstream servers while systemd-resolved is off, and then the machine cannot look up any name. That setting stays, it is Tailscale's safe one."""
    if not f["adguard"]:
        return True
    if run(["systemctl", "is-active", "systemd-resolved"])[1].strip() == "active":
        return True
    if not FAKE and not os.path.exists(P("/lib/systemd/system/systemd-resolved.service")) and not os.path.exists(P("/usr/lib/systemd/system/systemd-resolved.service")):
        return True
    old = read_file(P("/etc/resolv.conf"))
    act(["systemctl", "enable", "--now", "systemd-resolved"])
    if Opt.dry:
        out("      would point /etc/resolv.conf at the system resolver again")
        return True
    if FAKE:
        set_resolv_conf("nameserver 127.0.0.53\n")
        good("The system's own DNS resolver (systemd-resolved) is on again")
        return True
    try:
        os.remove(P("/etc/resolv.conf"))
        os.symlink("../run/systemd/resolve/stub-resolv.conf", P("/etc/resolv.conf"))
        time.sleep(3)
        socket.gethostbyname("github.com")
    except OSError:
        # keep the machine able to look up names: the plain file with the router and a public server, like the installer sets it
        set_resolv_conf("nameserver %s\nnameserver 1.1.1.1\n" % (Ctx.gateway or "1.1.1.1") if "nameserver" not in old or "100.100.100.100" in old else old)
        act(["systemctl", "disable", "--now", "systemd-resolved"])
        warn("The system's DNS resolver did not work, so the machine keeps asking your router for names (as before).")
        return True
    good("The system's own DNS resolver (systemd-resolved) is on again")
    return True


def un_remove_files(f, wipe_data, keep_drives_tool):
    """HomeLab's own files, settings and records. The installer itself is deleted last, and only when everything before it worked."""
    for n, w in SCRIPTS:
        if n == "drives" and keep_drives_tool:
            continue
        un_rm(w + "/" + n)
    for p in RETIRED_SCRIPTS:
        un_rm(p)
    files = ["/etc/homelab-backup.conf", "/etc/homelab-backup-tasks.json", "/etc/homelab-update.conf", "/var/lib/homelab", "/var/lib/homelab-backup",
             "/etc/homelab-drive-names", "/var/log/homelab-backup.log", "/var/log/homelab-backup-tasks.log", "/var/log/homelab-cards.log",
             "/var/log/homelab-restore-configs.log", "/run/homelab-terminal", "/run/homelab-stats", "/run/homelab-update"]
    if not keep_drives_tool:
        files += ["/var/lib/homelab-drives", "/var/log/homelab-drives.log", "/etc/homelab-drives"]
    for p in files:
        un_rm(p)
    good("HomeLab's programs, settings files and records are removed")
    if wipe_data:
        un_rm(SECRET_DIR[len(ROOT):])
        good("The saved passwords (%s) are deleted" % SECRET_DIR)
    return True


def un_inside_web_terminal():
    """True when this command runs inside the dashboard's web terminal: stopping that service would close the window in the middle of the removal."""
    if FAKE:
        return bool(os.environ.get("HLS_IN_TERMINAL"))
    pid = os.getpid()
    for _ in range(40):
        try:
            with open("/proc/%d/stat" % pid) as fh:
                st = fh.read()
            ppid = int(st.rsplit(")", 1)[1].split()[1])
            with open("/proc/%d/comm" % ppid) as fh:
                if fh.read().strip() == "ttyd":
                    return True
        except (OSError, ValueError, IndexError):
            return False
        if ppid <= 1:
            return False
        pid = ppid
    return False


def cmd_uninstall():
    """`uninstall`: take HomeLab off this machine. Asks what to do with the apps' data and with the drives, then a last confirmation."""
    load_all()
    if Mode.existing and not Opt.force_existing:
        raise Abort("This machine was built by hand, and HomeLab only looks at it: it never installed anything here, so it cannot take anything off. "
                    "If you really want the containers and scripts of the lab removed, run it again with --force-existing.")
    if un_inside_web_terminal():
        raise Abort("This window is the web terminal of the dashboard, and the uninstall removes the web terminal, which would close this window in the middle of the work. "
                    "Open a normal terminal instead (for example `ssh %s@%s`) and run `sudo homelab-setup uninstall` there." % (Ctx.user, Ctx.lan or "this-machine"))
    f = un_facts()
    nothing = not (f["containers"] or f["serve"] or f["units"] or f["scripts"] or f["cron"] or f["pools"] or State.exists())
    if nothing:
        say("Nothing from HomeLab is installed on this machine.")
        return 0
    un_show_plan(f)
    wipe_data, wipe_drives = un_ask_choices(f)
    out("")
    say("Your choices:  app data = %s;  drives = %s." % ("WIPE" if wipe_data else "keep", "ERASE" if wipe_drives else "keep every file"))
    if not un_confirm(wipe_data, wipe_drives):
        say("Cancelled. Nothing was changed.")
        return 0
    if Opt.dry:
        rule("Dry run: this is what would happen (nothing is changed)")
    failed = []

    def stage(title, fn, *a):
        rule(title)
        try:
            if fn(*a) is False:
                failed.append(title)
        except (Abort, OSError, subprocess.SubprocessError) as e:
            bad("%s: %s" % (title, e))
            failed.append(title)

    keep_drives_tool = bool(f["array"])
    stage("Stopping the scheduled jobs", un_remove_cron)
    stage("Removing the control panel and the web terminal", un_stop_services)
    stage("Removing the Tailscale addresses", un_remove_serve, f["serve"])
    stage("Removing the containers", un_remove_containers, f["containers"], wipe_data)
    if wipe_data:
        stage("Deleting the data of the apps", un_wipe_data, wipe_drives)
    if not f["array"]:
        stage("Taking the drive pools apart" + (" and erasing the drives" if wipe_drives else ""), un_release_drives, f, wipe_drives)
        if wipe_data:
            stage("Deleting what is left of the apps' folders", un_wipe_data, False, False)
    stage("Giving the machine's DNS back", un_restore_dns, f)
    stage("Taking the login screen out of ~/.bashrc", un_remove_login_block)
    stage("Removing HomeLab's own files", un_remove_files, f, wipe_data, keep_drives_tool)
    out("")
    if Opt.dry:
        say("This was a dry run. Nothing was changed. Run `sudo homelab-setup uninstall` to do it.")
        return 0
    if failed:
        warn("Some parts could not be removed: %s. Read the messages above, fix the cause, and run `sudo homelab-setup uninstall` again. "
             "The installer and its record were left in place so you can." % "; ".join(failed))
        return 1
    # last of all: the record of what was installed and the installer itself (nothing can be repeated without them)
    un_rm("/var/lib/homelab-setup")
    un_rm("/usr/local/sbin/homelab-setup")
    un_rm(LOG_FILE[len(ROOT):])
    rule("HomeLab is uninstalled")
    good("Everything HomeLab installed is removed.")
    say("Still here: Tailscale, Docker and the drive programs. The downloaded copy of the repository is in %s; delete that folder yourself if you do not need it." % Ctx.repo)
    if not wipe_data:
        say("The data of the apps was kept (folders %s and the Docker volumes). The saved passwords are in %s; keep that folder if you want to install again and open the old data." %
            (", ".join(d for d, _ in f["data"][:4]) + (" ..." if len(f["data"]) > 4 else ""), SECRET_DIR))
    if f["array"]:
        say("The %s array was left as it is. Manage it with `sudo drives`." % {"zfs": "ZFS", "md": "RAID"}[f["array"]])
    say("To install the lab again later:  git clone https://github.com/IbrandonrtI/My-Home-Lab-.git  and  sudo bash setup.sh install  inside it.")
    return 0


COMMANDS["uninstall"] = cmd_uninstall
