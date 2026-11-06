# ================================================================ Homepage config files
HP_FILES = ["services.yaml", "settings.yaml", "widgets.yaml", "bookmarks.yaml", "custom.css"]


def widgets_for_machine(body):
    """widgets.yaml for a new machine: its first resources pill carries this machine's name (the repository file calls it
    "Server"), and the weather city chosen at the start is put in."""
    body = re.sub(r"(- resources:\n\s+label:) Server\b", lambda m: "%s %s" % (m.group(1), Ctx.hostname), body, count=1)
    w = State.data["answers"].get("weather")
    if w:
        new = weather_apply(body, w)
        if new is not None:
            body = new
            State.data["weather_set"] = w["name"]
            State.save()
    return body


@step
class HomepageFiles(Step):
    id, group, title = "homepage-files", "Homepage", "Homepage config files in place for this machine"
    needs = ("folders", "tailscale-login", "restore-configs")

    def probe(self):
        if not all(os.path.exists(hp_path(f)) for f in HP_FILES):
            return "todo"
        txt = read_file(hp_path())
        if PH_LAN in txt or PH_FQDN in txt:
            return "todo"
        if OLD_LAN and OLD_LAN in txt and OLD_LAN != Ctx.lan:
            return "todo"
        if OLD_FQDN and OLD_FQDN in txt and OLD_FQDN != Ctx.fqdn:
            return "todo"
        return "done"

    def run(self):
        for f in HP_FILES:
            dst = hp_path(f)
            if not os.path.exists(dst):
                body = subst(read_file(repo_file("homepage-config", f)))
                if not body:
                    raise Abort("The repository file homepage-config/%s is missing." % f)
                if f == "services.yaml":
                    body = hp_strip_widgets(body)
                    if not adguard_wanted():
                        body = hp_remove_card(body, "adguard-card")
                if f == "widgets.yaml":
                    body = widgets_for_machine(body)
                write_file(dst, body, 0o644, (Ctx.uid, Ctx.gid))
            elif f in ("services.yaml", "bookmarks.yaml"):
                old = read_file(dst)
                new = subst(old)
                if new != old:
                    write_file(dst, new, 0o644, (Ctx.uid, Ctx.gid))


@step
class HomepageTabs(Step):
    id, group, title = "homepage-tabs", "Homepage", "Homepage tabs (Home, Stats, Links), group icons, bookmark cards, the STATS cards and their styles"
    needs = ("homepage-files", "scripts")

    def applies(self):
        return not Mode.existing and os.path.exists(hp_path("settings.yaml")) and os.path.exists(hp_path("custom.css")) and bool(read_file(repo_file("homepage-config", "settings.yaml")))

    def wanted(self):
        """(new settings.yaml, new custom.css, groups now known, new custom.js, new services.yaml) for this machine. The tabs are offered
        once: after that, taking the layout: block out of settings.yaml is respected. A group of this machine that no tab knows yet is put
        on one. The STATS groups are added to services.yaml (also offered once) when the tabs are on."""
        sett, css = read_file(hp_path("settings.yaml")), read_file(hp_path("custom.css"))
        if not State.ran("homepage-tabs"):
            sett = settings_with_layout(sett, read_file(repo_file("homepage-config", "settings.yaml")))
        svc = read_file(hp_path("services.yaml"))
        if re.search(r"(?m)^layout:", sett):
            shipped_svc = subst(read_file(repo_file("homepage-config", "services.yaml")))
            if not State.ran("homepage-stats") or STATS_BEGIN in svc:
                svc = services_stats_block(svc, shipped_svc)
            if not State.ran("homepage-calendar") or CAL_BEGIN in svc:
                svc = services_calendar_block(svc, shipped_svc)
            if not State.ran("homepage-customize") or CUSTOM_BEGIN in svc:         # the control panel's card: offered once, then kept up to date
                svc = services_customize_block(svc, shipped_svc)
        sett = layout_renamed(sett)
        sett, seen = layout_complete(sett, group_names(svc), group_names(read_file(hp_path("bookmarks.yaml"))), State.data.get("layout_seen", []))
        if re.search(r"(?m)^layout:", sett):
            sett, seen = layout_storage_wide(sett, seen)
            sett, seen = layout_music_wide(sett, seen)
            sett, seen = layout_calendar_on_stats(sett, seen)
            sett, seen = layout_calendar_on_home(sett, seen)
            sett, seen = layout_stats_before_links(sett, seen)
        sett, seen = settings_quicklaunch(sett, seen)
        new_css = css_tabs_block(css, read_file(repo_file("homepage-config", "custom.css")))
        new_js = js_groups_block(read_file(hp_path("custom.js")), read_file(repo_file("homepage-config", "custom.js")))
        return sett, new_css, seen, new_js, svc

    def remember(self, seen):
        if seen != State.data.get("layout_seen", []):
            State.data["layout_seen"] = seen
            State.save()

    def probe(self):
        sett, css, seen, js, svc = self.wanted()
        if (sett != read_file(hp_path("settings.yaml")) or css != read_file(hp_path("custom.css")) or js != read_file(hp_path("custom.js"))
                or svc != read_file(hp_path("services.yaml"))):
            return "todo"
        if not Opt.dry:
            self.remember(seen)                  # already in place (a new machine): a later removal of a group or of the tabs is respected
            for k in ("homepage-tabs", "homepage-stats", "homepage-calendar", "homepage-customize"):
                if not State.ran(k):
                    State.mark(k)
        return "done"

    def run(self):
        old_sett, old_css, old_js, old_svc = (read_file(hp_path(n)) for n in ("settings.yaml", "custom.css", "custom.js", "services.yaml"))
        sett, css, seen, js, svc = self.wanted()
        own = (Ctx.uid, Ctx.gid)
        if Opt.dry:
            out("      would add the tabs (Home, Stats, Links), the group icons, the bookmark cards, the STATS cards and their styles to the Homepage files")
            return
        for name, old, new in (("settings.yaml", old_sett, sett), ("custom.css", old_css, css), ("custom.js", old_js, js), ("services.yaml", old_svc, svc)):
            if new == old:
                continue
            if old and not os.path.exists(hp_path(name) + ".before-tabs"):          # the first copy is the one worth keeping
                write_file(hp_path(name) + ".before-tabs", old, 0o644, own)
            write_file(hp_path(name), new, 0o644, own)
        self.remember(seen)
        State.mark("homepage-tabs")
        State.mark("homepage-stats")
        State.mark("homepage-calendar")
        State.mark("homepage-customize")
        stats_file = hp_path("images/stats.json")
        if not FAKE and not os.path.exists(stats_file) and os.path.exists(P("/usr/local/sbin/homelab-stats")):
            # Homepage only serves a file that was there when it started, so the first stats.json is made now, before the restart below
            os.makedirs(os.path.dirname(stats_file), exist_ok=True)
            run_as_root_stats(stats_file)
        if CAL_BEGIN in svc and os.path.exists(P("/usr/local/bin/homelab-calendar")):
            # the same for the calendar files: they must exist before Homepage starts
            os.makedirs(hp_path("images"), exist_ok=True)
            run_calendar_build()
        if not FAKE and "homepage" in containers_all():
            act(["docker", "restart", "homepage"], timeout=120)
        out("      Reload the dashboard (Ctrl+Shift+R). The old files are saved as settings.yaml.before-tabs, custom.css.before-tabs, custom.js.before-tabs and services.yaml.before-tabs")
        if STATS_BEGIN in svc:
            out("      The Stats tab fills in within 15 minutes (the folder sizes take a little longer). To fill it in now:  sudo homelab-stats")
        if CUSTOM_BEGIN in svc:
            out("      The Customize tab is the control panel: change the look, the layout, the cards and the links by clicking. Choose its password with:  homelab panel password")
        if CAL_BEGIN in svc:
            out("      The Calendar is at the bottom of the Home tab, under the service cards. Add your own events with:  homelab event add 2026-12-25 \"Family dinner\"")


def fetch_picture(addr):
    """The bytes of a picture from the web (None when it cannot be had or is not a picture). FAKE mode: the file named in HLS_FAKE_BG_FILE."""
    if FAKE:
        f = os.environ.get("HLS_FAKE_BG_FILE", "")
        data = open(f, "rb").read() if f and os.path.isfile(f) else None
    else:
        try:
            req = urllib.request.Request(addr, headers={"User-Agent": "homelab-setup"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read(30 * 1024 * 1024)
        except (urllib.error.URLError, OSError, ValueError):
            return None
    return data if data and (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")) else None


@step
class HomepageBackground(Step):
    id, group, title = "homepage-background", "Homepage", "The dashboard's background picture is saved on this server (loads fast, works offline)"
    needs = ("homepage-tabs",)

    def applies(self):
        return not Mode.existing and os.path.exists(hp_path("settings.yaml"))

    def probe(self):
        cur = background_image(read_file(hp_path("settings.yaml")))
        tried = time.time() - State.data.get("background_tried", 0) < 7 * 86400          # a failed attempt is repeated a week later, not on every run
        return "done" if State.ran(self.id) or tried or not re.match(r"https?://", cur) else "todo"

    def detail(self):
        return background_image(read_file(hp_path("settings.yaml")))[:60]

    def run(self):
        sett = read_file(hp_path("settings.yaml"))
        cur = background_image(sett)
        if Opt.dry:
            out("      would download the background picture into %s and use it from there" % hp_path("images"))
            return
        data = fetch_picture(cur)
        if data is None:
            warn("Could not download the background picture (%s). It stays as it is; an upgrade a week from now tries again." % cur[:70])
            State.data["background_tried"] = int(time.time())
            State.save()
            return
        ext = ".png" if data[:4] == b"\x89PNG" else ".webp" if data[:4] == b"RIFF" else ".jpg"
        name = "background" + ext
        os.makedirs(hp_path("images"), exist_ok=True)
        path = hp_path("images/" + name)
        with open(path, "wb") as f:
            f.write(data)
        os.chmod(path, 0o644)
        chown(path, Ctx.uid, Ctx.gid)
        if not os.path.exists(hp_path("settings.yaml") + ".before-background"):
            write_file(hp_path("settings.yaml") + ".before-background", sett, 0o644, (Ctx.uid, Ctx.gid))
        write_file(hp_path("settings.yaml"), settings_with_background(sett, "/images/" + name), 0o644, (Ctx.uid, Ctx.gid))
        State.mark(self.id)
        if not FAKE and "homepage" in containers_all():
            act(["docker", "restart", "homepage"], timeout=120)       # Homepage only serves a new picture after a restart
        out("      The background is now %s in the images folder (the old settings.yaml is kept as settings.yaml.before-background). "
            "To use another picture later:  homelab theme background URL-or-FILE" % name)


def run_calendar_build():
    """Make the calendar files (holidays, observances, your events) in the images folder of Homepage."""
    run([P("/usr/local/bin/homelab-calendar"), "build"], env=dict(os.environ, HP_DIR=P(hp_dir())), timeout=60)


def run_as_root_stats(stats_file):
    """Make the first stats.json (without counting folder sizes, which takes minutes)."""
    run([P("/usr/local/sbin/homelab-stats"), "quick"], env=dict(os.environ, HOMELAB_STATS_OUT=stats_file), timeout=180)
