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


MEM_SIZE = re.compile(r"^(\d+(?:\.\d+)?)\s*([mMgG])[bB]?$")


def cpu_has_avx2():
    """True when the processor has AVX2 (AudioMuse-AI will not start without it). True too when it cannot be read."""
    if os.environ.get("HLS_NO_AVX2"):
        return False
    try:
        return any("avx2" in line.split() for line in open("/proc/cpuinfo") if line.startswith("flags"))
    except OSError:
        return True


def mem_mb(text):
    """'3g' or '3072m' as megabytes (3072)."""
    m = MEM_SIZE.match(str(text))
    return int(float(m.group(1)) * (1024 if m.group(2).lower() == "g" else 1)) if m else 3072


def gb_text(mb):
    """'3072' (megabytes) as '3 GB'."""
    return "%g GB" % round(int(mb) / 1024, 1)


def audiomuse_limit_mb(text):
    """The worker's memory cap in whole megabytes, from what was typed (3g, 4096m, 2.5g). Raises Abort for a number that does not work."""
    m = MEM_SIZE.match(text.strip())
    if not m:
        raise Abort("'%s' is not a size. Write it like 3g (gigabytes) or 3072m (megabytes), or write auto." % text)
    mb = mem_mb(text.strip())
    total = ram_gb()
    if mb < 1024:
        raise Abort("%s is too little: the worker needs at least 1g to listen to a song." % text)
    if total and mb > total * 1024 * 0.8:
        raise Abort("%s is more than this machine can spare: it has %.1f GB in all and the other apps need some. Nothing was changed." % (text, total))
    return mb


def port_taken_by(port, mine=("audiomuse-flask",)):
    """The name of another container that already publishes this port on the machine ('' when none does)."""
    rc, txt = docker("ps", "--format", "{{.Names}}|{{.Ports}}", timeout=30)
    for line in txt.splitlines():
        name, _, ports = line.partition("|")
        if name not in mine and re.search(r":%d->" % port, ports):
            return name
    return ""


def audiomuse_memory_help():
    total = ram_gb()
    cur = audiomuse_mem()
    rows = [(4, "a small machine"), (8, "what most small servers have"), (16, "a roomy machine"), (32, "a big machine")]
    out("")
    say("The AudioMuse-AI worker (the part that listens to your songs) may use up to %s of memory." % (
        gb_text(mem_mb(cur))) + (" This machine has %.1f GB in all." % total if total else ""))
    say("What I suggest, by the memory of the machine (my estimates for a library of a few thousand songs, not measurements):")
    for gb, note in rows:
        out("      %2d GB machine   %-5s  %s%s" % (gb, audiomuse_mem_suggest(gb * 0.93).replace("g", " GB"), note,
                                                  "   <- this machine" if total and abs(total - gb * 0.93) < gb * 0.2 else ""))
    say("Too low: a long song can make the worker run out, and AudioMuse-AI then tries it again later. Too high: the other apps can run short "
        "while it works. More memory does not make it much faster; the processor does that.")


def audiomuse_usage():
    """What the three containers use right now, as lines of text ([] when Docker cannot say)."""
    rc, txt = docker("stats", "--no-stream", "--format", "{{.Name}}|{{.MemUsage}}", *STACKS["audiomuse"][1], timeout=60)
    return ["%-20s %s" % tuple(l.split("|", 1)) for l in txt.splitlines() if "|" in l] if rc == 0 else []


def audiomuse_set_memory(rest):
    """`audiomuse memory [SIZE | auto]`: show the worker's memory cap with suggestions, and change it."""
    audiomuse_memory_help()
    if audiomuse_wanted():
        for line in audiomuse_usage():
            out("      right now: " + line)
    if rest:
        word = rest[0]
    elif Opt.dry:
        say("This is a dry run: nothing was changed.")
        return
    else:
        word = ask("New limit (for example 4g), auto for the suggestion for this machine, or Enter to keep it", "")
    if not word:
        say("Kept at %s." % gb_text(mem_mb(audiomuse_mem())))
        return
    new = None if word == "auto" else "%dm" % audiomuse_limit_mb(word)
    if Opt.dry:
        say("This is a dry run: the limit would become %s. Nothing was changed." % gb_text(mem_mb(new or audiomuse_mem_suggest())))
        return
    if new:
        State.data["audiomuse_mem"] = new
    else:
        State.data.pop("audiomuse_mem", None)
    State.save()
    good("The worker's memory limit is now %s." % gb_text(mem_mb(audiomuse_mem())))
    if audiomuse_wanted():
        say("AudioMuse-AI is deployed again with it (it restarts; an analysis that was running carries on afterwards).")
        cmd_refresh()
    else:
        say("It takes effect when AudioMuse-AI is set up (sudo homelab-setup audiomuse).")


def audiomuse_worker(stop):
    """`audiomuse pause` / `audiomuse resume`: stop the worker to free its memory, or start it again."""
    if not audiomuse_wanted():
        raise Abort("AudioMuse-AI is not set up on this machine. Run `sudo homelab-setup audiomuse`.")
    if Opt.dry:
        say("This is a dry run: the worker would be %s. Nothing was changed." % ("paused" if stop else "started"))
        return
    rc, txt = docker("stop" if stop else "start", "audiomuse-worker", timeout=120)
    if rc != 0:
        raise Abort("Docker could not %s the worker: %s" % ("stop" if stop else "start", txt.strip()[-200:]))
    if stop:
        State.data["audiomuse_paused"] = True
    else:
        State.data.pop("audiomuse_paused", None)
    State.save()
    if stop:
        good("The worker is paused and its memory is free. Songs are not analysed until you run:  sudo homelab-setup audiomuse resume")
    else:
        good("The worker is running again. An analysis you started carries on.")


def audiomuse_status():
    out("")
    if not audiomuse_wanted():
        say("AudioMuse-AI is not set up on this machine. `sudo homelab-setup audiomuse` sets it up.")
        return
    up = containers_running()
    say("Web page: %s   (log in as %s; the password is AUDIOMUSE_PASSWORD in `sudo homelab-setup secrets`)" % (url("audiomuse"), Ctx.admin))
    for c in STACKS["audiomuse"][1]:
        paused = c == "audiomuse-worker" and State.data.get("audiomuse_paused")
        out("      %-20s %s" % (c, "paused on purpose" if paused and c not in up else "running" if c in up else "NOT running"))
    say("The worker may use up to %s of memory (change it: sudo homelab-setup audiomuse memory)." % gb_text(mem_mb(audiomuse_mem())))
    for line in audiomuse_usage():
        out("      right now: " + line)


def audiomuse_remove():
    """`audiomuse remove`: take the plugin out of Navidrome and remove the three containers (the analysis data stays)."""
    if not audiomuse_wanted():
        say("AudioMuse-AI is not set up. Nothing to remove.")
        return
    if Opt.dry:
        say("This is a dry run: it would switch the plugin off, remove the three AudioMuse-AI containers and deploy Navidrome again. Nothing was changed.")
        return
    if not yesno("Remove AudioMuse-AI (its analysis data stays on the drive)?", False):
        say("Nothing was changed.")
        return
    navidrome_cli("plugin", "disable", AUDIOMUSE_PLUGIN_ID, timeout=120)
    try:
        os.remove(audiomuse_plugin_file())
    except OSError:
        pass
    if not Portainer.delete("audiomuse"):
        raise Abort("Portainer could not remove the stack 'audiomuse'. Remove it in Portainer (Stacks), then run this again.")
    for k in ("audiomuse", "audiomuse_stack", "audiomuse_plugin", "audiomuse_paused"):
        State.data.pop(k, None)
    State.save()
    good("AudioMuse-AI is removed. Navidrome is deployed again without it.")
    say("Its analysis data is still in %s/audiomuse (it took hours to make, so a later setup reuses it). To free the space: sudo rm -rf %s/audiomuse\n"
        "The Navidrome login called %s stays too; you can delete it on Navidrome's Users page." % (Ctx.home, Ctx.home, AUDIOMUSE_ND_USER))
    cmd_refresh()


def cmd_audiomuse(rest):
    """`audiomuse`: set up AudioMuse-AI (Navidrome suggests similar songs by how they sound); also memory, pause, resume, status, remove."""
    load_all()
    if Mode.existing:
        say("This machine was built by hand, so the installer only reads it. AudioMuse-AI is set up with its own compose file; see its page on GitHub.")
        return
    if not State.exists():
        raise Abort("The installer has not run on this machine yet. Run `sudo homelab-setup install`.")
    word = rest[0] if rest else ""
    if word == "memory":
        return audiomuse_set_memory(rest[1:])
    if word in ("pause", "resume"):
        return audiomuse_worker(word == "pause")
    if word == "status":
        return audiomuse_status()
    if word == "remove":
        return audiomuse_remove()
    if rest:
        raise Abort("Unknown word '%s'. Use: homelab-setup audiomuse   or   audiomuse memory | pause | resume | status | remove" % word)
    if not navidrome_wanted():
        raise Abort("AudioMuse-AI works together with Navidrome, and this machine has no Navidrome yet (it is installed with the lab; run `sudo homelab-setup refresh`). Nothing was changed.")
    other = "" if State.data.get("audiomuse") else port_taken_by(PORTS["audiomuse"])
    if other:
        raise Abort("Port %d is already used by the container %s, and AudioMuse-AI needs it for its web page. Nothing was changed." % (PORTS["audiomuse"], other))
    if not cpu_has_avx2():
        raise Abort("The processor of this machine has no AVX2, and AudioMuse-AI will not start without it. Nothing was changed.")
    out("")
    say("AudioMuse-AI listens to every song in Navidrome once and works out which songs sound alike. After that, Instant Mix in Navidrome "
        "builds its queue from songs that sound like the one you picked (it also works for songs nobody has tagged).")
    say("What this does:\n"
        "  - adds three containers (a database, a web page and a worker); the first download is a few GB\n"
        "  - makes a small Navidrome login for it and puts its plugin into Navidrome (Navidrome restarts once)\n"
        "  - limits the worker to %s of memory and all processor cores but one, so your other apps keep running\n"
        "  - the first analysis is started by you, takes hours for a few thousand songs, and keeps your processor busy meanwhile" % gb_text(mem_mb(audiomuse_mem())))
    total = ram_gb()
    if total and total < 5.5:
        warn("This machine has only %.1f GB of memory. AudioMuse-AI recommends 8 GB; it will be slow and may stop other apps." % total)
    elif total and total < 9:
        say("This machine has %.1f GB of memory, a little under the 8 GB AudioMuse-AI recommends. The limits above are there for that; "
            "`sudo homelab-setup audiomuse memory` shows how to change them, and `audiomuse pause` frees the worker's memory." % total)
    if State.data.get("audiomuse"):
        say("AudioMuse-AI is already set up; this checks it again.")
    elif Opt.dry:
        say("This is a dry run: nothing was changed.")
        return
    elif not yesno("Set up AudioMuse-AI now?", True):
        say("Nothing was changed.")
        return
    State.data["audiomuse"] = True
    State.save()
    cmd_refresh()
    if State.data.get("audiomuse_plugin"):
        good("AudioMuse-AI is set up.")
        say("Next, let it listen to your songs (once):\n"
            "  1. Open %s and log in as %s. The password is AUDIOMUSE_PASSWORD in `sudo homelab-setup secrets`.\n"
            "  2. On the main page (Analysis and Clustering) press Start Analysis. You can close the page; it keeps going.\n"
            "  3. When it has finished, open a song's menu in Navidrome and choose Instant Mix.\n"
            "Check on it with `sudo homelab-setup audiomuse status`." % (url("audiomuse"), Ctx.admin))
    else:
        warn("The setup did not finish. Read the message above, then run `sudo homelab-setup refresh` to continue.")


LB_TOKEN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SERVICE_USER = re.compile(r"^[^\s/?#&:@]{1,64}$")               # a Last.fm or ListenBrainz user name: no spaces, slashes or other address characters
NAVILIST_SECRETS = ("NAVILIST_LASTFM_USER", "NAVILIST_LB_USER", "NAVILIST_LB_TOKEN")


def cmd_navilist(rest):
    """`navilist`: set up naviList (Navidrome playlists from your ListenBrainz and Last.fm listening); also subscribe, status, remove."""
    load_all()
    if Mode.existing:
        say("This machine was built by hand, so the installer only reads it. naviList is set up with its own compose file; see its page on GitHub.")
        return
    if not State.exists():
        raise Abort("The installer has not run on this machine yet. Run `sudo homelab-setup install`.")
    word = rest[0] if rest else ""
    if word == "subscribe":
        return navilist_subscribe_now()
    if word == "status":
        return navilist_status()
    if word == "remove":
        return navilist_remove()
    if rest:
        raise Abort("Unknown word '%s'. Use: homelab-setup navilist   or   navilist subscribe | status | remove" % word)
    if not navidrome_wanted():
        raise Abort("naviList works together with Navidrome, and this machine has no Navidrome yet (it is installed with the lab; run `sudo homelab-setup refresh`). Nothing was changed.")
    other = "" if State.data.get("navilist") else port_taken_by(PORTS["navilist"], mine=("navilist",))
    if other:
        raise Abort("Port %d is already used by the container %s, and naviList needs it for its web page. Nothing was changed." % (PORTS["navilist"], other))
    out("")
    say("naviList makes playlists in Navidrome from what you listen to. ListenBrainz makes Weekly Jams, Weekly Exploration and Daily Jams for you, "
        "and Last.fm has your charts. naviList turns them into Navidrome playlists, using only songs you already have.")
    say("What this does:\n"
        "  - adds one small container (its web page is on port %d) and makes a small Navidrome login for it\n"
        "  - asks for your ListenBrainz user name and token (and your Last.fm user name if you saved a Last.fm key)\n"
        "  - refreshes by itself: Navidrome every 5 minutes, ListenBrainz and Last.fm every 30 minutes\n"
        "  - never downloads anything\n"
        "  - ListenBrainz makes your playlists only after it has some of your listens, so the first ones can take a few days" % PORTS["navilist"])
    if State.data.get("navilist"):
        say("naviList is already set up; this changes the saved names and token, or checks it again. Press Enter to keep what is saved.")
    elif Opt.dry:
        say("This is a dry run: nothing was changed.")
        return
    elif not yesno("Set up naviList now?", True):
        say("Nothing was changed.")
        return
    if Opt.dry:
        say("This is a dry run: nothing was changed.")
        return
    say("Your ListenBrainz token is on https://listenbrainz.org/settings/ (sign in, then copy the User token). Your user name is the name you sign in with.")
    lb_user = ask("ListenBrainz user name", Secrets.get("NAVILIST_LB_USER")).strip()
    lb_token = ask_secret("ListenBrainz token (Enter keeps the saved one)").strip() or Secrets.get("NAVILIST_LB_TOKEN")
    if lb_user and not SERVICE_USER.match(lb_user):
        raise Abort("'%s' does not look like a ListenBrainz user name. Nothing was saved." % lb_user)
    if bool(lb_user) != bool(lb_token):
        raise Abort("ListenBrainz needs both the user name and the token. Nothing was saved.")
    if lb_token and not LB_TOKEN.match(lb_token):
        raise Abort("That does not look like a ListenBrainz token: it is 36 characters with dashes, like 1b2c3d4e-0000-1111-2222-333344445555. Nothing was saved.")
    fm_user = ""
    if Secrets.get("LASTFM_APIKEY"):
        fm_user = ask("Last.fm user name (Enter to skip the Last.fm charts)", Secrets.get("NAVILIST_LASTFM_USER")).strip()
        if fm_user and not SERVICE_USER.match(fm_user):
            raise Abort("'%s' does not look like a Last.fm user name. Nothing was saved." % fm_user)
    else:
        say("No Last.fm key is saved, so the Last.fm charts are left out. (`sudo homelab-setup lastfm` saves the key; run this again afterwards.)")
    if not lb_user and not fm_user:
        raise Abort("naviList needs at least ListenBrainz or Last.fm to make playlists from. Nothing was saved.")
    for key, val in (("NAVILIST_LB_USER", lb_user), ("NAVILIST_LB_TOKEN", lb_token), ("NAVILIST_LASTFM_USER", fm_user)):
        if val:
            Secrets.set(key, val)
        else:
            Secrets.vals.pop(key, None)
    Secrets.save()
    State.data["navilist"] = True
    State.save()
    cmd_refresh()
    if not State.data.get("navilist_stack"):
        warn("The setup did not finish. Read the message above, then run `sudo homelab-setup refresh` to continue.")
        return
    good("naviList is set up.")
    navilist_report_subscribe()
    say("Last step, once: Navidrome has to tell ListenBrainz (and Last.fm) what you play, or they have nothing to recommend from.\n"
        "  1. Open Navidrome, click your name at the top right, then Personal.\n"
        "  2. Switch on Scrobble to ListenBrainz and paste the same token. If you use Last.fm, link your Last.fm account there too.\n"
        "  3. Play music as usual. In a few days ListenBrainz makes your playlists; they appear in Navidrome by themselves.\n"
        "naviList's own page is %s. Check on it with `sudo homelab-setup navilist status`." % url("navilist"))


def navilist_report_subscribe():
    done, waiting = navilist_subscribe()
    for name in done:
        good("Subscribed: %s. It is in Navidrome's Playlists now." % name)
    if waiting:
        say("Not there yet: %s. This is normal at first; they appear after a few days of listening. "
            "`sudo homelab-setup navilist subscribe` tries again (or tick them on naviList's page)." % "; ".join(waiting))
    elif not done:
        say("Everything is subscribed already.")


def navilist_subscribe_now():
    if not navilist_wanted():
        raise Abort("naviList is not set up on this machine. Run `sudo homelab-setup navilist`.")
    if "navilist" not in containers_running():
        raise Abort("The naviList container is not running. Run `sudo homelab-setup refresh` first.")
    if Opt.dry:
        say("This is a dry run: it would subscribe naviList to the ListenBrainz playlists and the Last.fm charts. Nothing was changed.")
        return
    navilist_report_subscribe()


def navilist_status():
    out("")
    if not navilist_wanted():
        say("naviList is not set up on this machine. `sudo homelab-setup navilist` sets it up.")
        return
    up = containers_running()
    say("Web page: %s" % url("navilist"))
    out("      %-20s %s" % ("navilist", "running" if "navilist" in up else "NOT running"))
    out("      %-20s %s" % ("ListenBrainz", Secrets.get("NAVILIST_LB_USER") or "not used"))
    out("      %-20s %s" % ("Last.fm", (Secrets.get("NAVILIST_LASTFM_USER") or "not used") if Secrets.get("LASTFM_APIKEY") else "no Last.fm key saved"))
    if "navilist" in up:
        js = http("GET", url("navilist", "/sync/lb-playlists/cached"), timeout=30)[1]
        lb = [p.get("title", "") for p in (js.get("playlists", []) if isinstance(js, dict) else []) if p.get("enabled")]
        js = http("GET", url("navilist", "/sync/lfm-playlists/cached"), timeout=30)[1]
        fm = [p.get("title", "") for p in (js.get("playlists", []) if isinstance(js, dict) else []) if p.get("enabled")]
        for name in lb + fm:
            out("      subscribed: %s" % name)
        if not lb and not fm:
            out("      no playlist is subscribed yet (sudo homelab-setup navilist subscribe)")


def navilist_remove():
    """`navilist remove`: remove the container. The playlists it made stay in Navidrome."""
    if not navilist_wanted():
        say("naviList is not set up. Nothing to remove.")
        return
    if Opt.dry:
        say("This is a dry run: it would remove the naviList container and forget the ListenBrainz and Last.fm names. Nothing was changed.")
        return
    if not yesno("Remove naviList (the playlists it made stay in Navidrome)?", False):
        say("Nothing was changed.")
        return
    if not Portainer.delete("navilist"):
        raise Abort("Portainer could not remove the stack 'navilist'. Remove it in Portainer (Stacks), then run this again.")
    for k in ("navilist", "navilist_stack"):
        State.data.pop(k, None)
    State.save()
    for k in NAVILIST_SECRETS:
        Secrets.vals.pop(k, None)
    Secrets.save()
    good("naviList is removed.")
    say("The playlists it made are still in Navidrome (you can delete them there). Its data is still in %s/navilist/data; to free the space: sudo rm -rf %s/navilist\n"
        "The Navidrome login called %s stays too; you can delete it on Navidrome's Users page." % (Ctx.home, Ctx.home, NAVILIST_ND_USER))
    cmd_refresh()


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
    """Make Homepage see the Main and Backup Pool (the two drive pills). sudo drives calls this by itself."""
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
        good("Homepage can see the Main and Backup Pool")
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


AUTO_EVERY = 20 * 60        # the quiet schedule looks at the checklist at most this often
AUTO_RETRY = 3 * 3600       # a step that failed in a quiet run is tried again after this long


def another_setup_running():
    """True when a person (or the background job) is running the installer right now: the quiet schedule then keeps out of the way."""
    me = os.getpid()
    for d in glob.glob("/proc/[0-9]*"):
        try:
            if int(os.path.basename(d)) == me:
                continue
            words = read_file(d + "/cmdline").split("\0")
        except (OSError, ValueError):
            continue
        if any(w.endswith("homelab-setup") for w in words[:3]) and any(w in ("install", "refresh", "finish", "upgrade", "uninstall", "fill", "growdisk") for w in words[1:5]):
            return True
    return False


def auto_continue(res):
    """The quiet schedule: do the steps that became possible by themselves (for example after MagicDNS was turned on), so nobody has to run
    `sudo homelab-setup refresh`. Steps that need the admin password stay open (the person does them with refresh), and a failed step is
    tried again only every few hours. Returns the new results."""
    if Mode.existing or State.readonly or not State.exists() or finish_running() or another_setup_running():
        return res
    tried = State.data.setdefault("auto_tried", {})
    now = int(time.time())
    skip = {s.id for s in STEPS if res[s.id].state == "failed" and now - int(tried.get(s.id, 0)) < AUTO_RETRY}
    ready = [s for s in STEPS if s.kind == "auto" and res[s.id].state in ("todo", "failed") and s.id not in skip]
    if not ready or not Finish.take_lock():
        return res
    Runtime.unattended = True
    try:
        for s in ready:
            tried[s.id] = now
        State.save()
        with open(os.devnull, "w") as quiet_out, contextlib.redirect_stdout(quiet_out):      # (nobody reads it; the log file keeps the details)
            run_pass(res, skip=skip)
        res = evaluate()
        for s in STEPS:
            if res[s.id].state == "done":
                tried.pop(s.id, None)
        State.save()
    finally:
        Runtime.unattended = False
        if Finish.lock_fd is not None:
            os.close(Finish.lock_fd)
            Finish.lock_fd = None
    return res


def cmd_progress():
    """`progress`: write the progress counts for the login screen.

    Run by the schedule it stays light: nothing in the first 10 minutes after a boot (apps are still
    starting, and a full check of every step would only slow the machine down), nothing while the saved
    counts are less than 20 minutes old, and once setup is finished the schedule line removes itself.
    """
    quiet = len(sys.argv) > 2 and sys.argv[2] == "--quiet"
    if quiet or started_by_cron():
        if uptime_seconds() < BOOT_GRACE:
            return
        try:
            if time.time() - os.path.getmtime(PROGRESS_FILE) < AUTO_EVERY:
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
    if quiet:
        Live.enabled = False
        res = auto_continue(res)
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
  status                   how far the last steps are that finish in the background after the install
  finish                   run those last steps again in this window (a failed one is listed by `status`)
  upgrade                  download the newest files from GitHub and put the new scripts on this machine (one step)
  growdisk                 give the unused space of the drive to the system volume (LVM, Ubuntu Server); it asks first
  verify                   check that every container and service is up (also shown when all steps are done)
  fill                     walk through the logins and keys that need you
  filebrowser              update FileBrowser's drive folders after a drive was connected or removed
  homepage                 let Homepage see the Main and Backup Pool, and move custom.css to the current layout
  adguard                  add AdGuard Home, if you skipped it during the install
  cards                    give every new service (a container with a web page) its Homepage card; also: cards list | move | ignore
  lastfm                   save your free Last.fm key so Navidrome can suggest similar songs; also: lastfm remove
  audiomuse                set up AudioMuse-AI (Navidrome suggests songs that sound alike); also: audiomuse memory | pause | resume | status | remove
  navilist                 set up naviList (Navidrome playlists from your ListenBrainz and Last.fm listening); also: navilist subscribe | status | remove
  uninstall                take HomeLab off this machine; asks whether to keep or wipe the apps' data and the drives (Tailscale, Docker and the drive programs stay); wiping also deletes the downloaded repository folder; add --dry-run to look first
  done STEP | skip STEP    mark a manual step as done, or as not wanted
  secrets                  show the generated passwords and keys
  progress | version | help

Options for install:  --yes  --backup FOLDER  --no-restore  --no-background  --repo FOLDER  --force-existing
The installer never formats or erases a drive and never saves the admin password. The one change it can make to the drive layout
is growing an LVM system volume into unused space of its drive, and only after you say yes.
"""


# every command that needs no more than its name (done STEP and skip STEP also take the step)
COMMANDS = {"checklist": cmd_checklist, "check": cmd_checklist, "install": cmd_install, "refresh": cmd_refresh, "fill": cmd_fill,
            "secrets": cmd_secrets, "progress": cmd_progress, "verify": cmd_verify, "filebrowser": cmd_filebrowser,
            "homepage": cmd_homepage, "adguard": cmd_adguard, "upgrade": cmd_upgrade, "growdisk": cmd_growdisk,
            "finish": cmd_finish, "status": cmd_status}
