CSS_LAYOUT_MARK = "How this file is organised"
THEME_BEGIN, THEME_END = "/* >>> homelab theme >>>", "/* <<< homelab theme <<< */"


def css_new_layout(live, shipped):
    """Move this machine's custom.css to the shipped layout while keeping its own card accent colors, :root values and theme block."""
    if CSS_LAYOUT_MARK in live or not shipped:
        return live
    out = shipped
    for m in re.finditer(r"(?m)^#([\w-]+)-card\s*\{\s*--accent:[^}]*\}[ \t]*(?:/\*.*?\*/)?", live):
        line = m.group(0)
        out = re.sub(r"(?m)^#%s-card\s*\{\s*--accent:[^}]*\}[ \t]*(?:/\*.*?\*/)?" % re.escape(m.group(1)), lambda _m, keep=line: keep, out, count=1)
    mine = {}
    for blk in re.finditer(r":root\s*\{(.*?)\}", live, re.S):
        for k, v in re.findall(r"(--[\w-]+):\s*([^;]+);", blk.group(1)):
            mine[k] = v.strip()
    for k, v in mine.items():
        out = re.sub(r"(?m)^(\s*%s:\s*)[^;]+;" % re.escape(k), lambda m, val=v: m.group(1) + val + ";", out, count=1)
    a = live.find(THEME_BEGIN)
    z = live.find(THEME_END, a) if a >= 0 else -1
    if a >= 0 and z >= 0:
        out = out.rstrip("\n") + "\n\n" + live[a:z + len(THEME_END)] + "\n"
    return out


TABS_BEGIN, TABS_END = "/* >>> homelab tabs >>>", "/* <<< homelab tabs <<< */"
LAYOUT_MARK = "# Tabs and group icons"


def css_tabs_block(live, shipped):
    a = shipped.find(TABS_BEGIN)
    z = shipped.find(TABS_END, a) if a >= 0 else -1
    if a < 0 or z < 0:
        return live
    block = shipped[a:z + len(TABS_END)]
    la = live.find(TABS_BEGIN)
    lz = live.find(TABS_END, la) if la >= 0 else -1
    if la >= 0 and lz >= 0:
        return live[:la] + block + live[lz + len(TABS_END):]
    t = live.find(THEME_BEGIN)
    if t >= 0:
        return live[:t].rstrip("\n") + "\n\n\n" + block + "\n\n" + live[t:]
    return live.rstrip("\n") + "\n\n\n" + block + "\n"


JS_BEGIN, JS_END = "/* >>> homelab groups >>>", "/* <<< homelab groups <<< */"
PLAYER_JS_BEGIN, PLAYER_JS_END = "/* >>> homelab player >>>", "/* <<< homelab player <<< */"
EXTRAS_JS_BEGIN, EXTRAS_JS_END = "/* >>> homelab extras >>>", "/* <<< homelab extras <<< */"
PANEL_JS_BEGIN, PANEL_JS_END = "/* >>> homelab panel >>>", "/* <<< homelab panel <<< */"
JS_BLOCKS = [(JS_BEGIN, JS_END), (PLAYER_JS_BEGIN, PLAYER_JS_END), (EXTRAS_JS_BEGIN, EXTRAS_JS_END), (PANEL_JS_BEGIN, PANEL_JS_END)]


def js_put_block(live, shipped, begin, end):
    a = shipped.find(begin)
    z = shipped.find(end, a) if a >= 0 else -1
    if a < 0 or z < 0:
        return live
    block = shipped[a:z + len(end)]
    la = live.find(begin)
    lz = live.find(end, la) if la >= 0 else -1
    if la >= 0 and lz >= 0:
        return live[:la] + block + live[lz + len(end):]
    if not live.strip():
        return block + "\n"
    return live.rstrip("\n") + "\n\n" + block + "\n"


def js_groups_block(live, shipped):
    for begin, end in JS_BLOCKS:
        live = js_put_block(live, shipped, begin, end)
    return live


STATS_BEGIN, STATS_END = "# >>> homelab stats >>>", "# <<< homelab stats <<<"
STATS_GROUPS = {"Preview": ("mdi-view-dashboard", 4), "Music Library": ("mdi-music", 2), "Library Totals": ("mdi-image-multiple", 2),
                "Storage": ("mdi-harddisk", 3), "Backup & Updates": ("mdi-backup-restore", 2), "Folder Sizes": ("mdi-folder-multiple", 1)}
STATS_AFTER = {"Music Library": "Preview"}
MUSIC_WIDE = "~music-2-columns"
STORAGE_WIDE = "~storage-3-columns"
OLD_NAMES = {"At a glance": "Preview", "At a Glance": "Preview", "Library totals": "Library Totals", "Backup & updates": "Backup & Updates", "Folder sizes": "Folder Sizes"}
OLD_TABS = {"HOME": "Home", "LINKS": "Links", "STATS": "Stats"}


CAL_BEGIN, CAL_END = "# >>> homelab calendar >>>", "# <<< homelab calendar <<<"
CUSTOM_BEGIN, CUSTOM_END = "# >>> homelab customize >>>", "# <<< homelab customize <<<"
CUSTOMIZE_GROUPS = {"Customize": ("mdi-tune", 1)}
LINKEDIT_GROUPS = {"Edit Links": ("mdi-pencil-box-multiple", 1), "Terminal": ("mdi-console", 1)}
TERMINAL_GROUPS = {"Terminal": ("mdi-console", 1)}
CALENDAR_GROUPS = {"Calendar": ("mdi-calendar-month", 2)}


def services_block(live, shipped, begin, end):
    """Insert or update a managed block of services.yaml (the lines between two marker lines of the shipped file); text outside the block is not touched."""
    a = shipped.find(begin)
    z = shipped.find(end, a) if a >= 0 else -1
    if a < 0 or z < 0:
        return live
    block = shipped[a:z + len(end)]
    la = live.find(begin)
    if la >= 0:
        eol = live.find("\n", la)
        if "customized" in live[la + len(begin):eol if eol >= 0 else len(live)]:
            return live
    lz = live.find(end, la) if la >= 0 else -1
    if la >= 0 and lz >= 0:
        return live[:la] + block + live[lz + len(end):]
    return live.rstrip("\n") + "\n\n" + block + "\n"


def services_stats_block(live, shipped):
    return services_block(live, shipped, STATS_BEGIN, STATS_END)


def services_customize_block(live, shipped):
    return services_block(live, shipped, CUSTOM_BEGIN, CUSTOM_END)


def services_calendar_block(live, shipped):
    return services_block(live, shipped, CAL_BEGIN, CAL_END)


def settings_with_layout(live, shipped):
    out = live
    if not re.search(r"(?m)^layout:", out):
        a = shipped.find(LAYOUT_MARK)
        if a >= 0:
            out = out.rstrip("\n") + "\n\n" + shipped[a:].rstrip("\n") + "\n"
    for key, val in (("hideVersion", "true"), ("language", "en")):
        if not re.search(r"(?m)^%s:" % key, out):
            m = re.search(r"(?m)^(theme|title):.*\n", out)
            line = "%s: %s\n" % (key, val)
            out = out[:m.end()] + line + out[m.end():] if m else line + out
    return out


QUICKLAUNCH_DONE = "~quicklaunch"
QUICKLAUNCH_BLOCK = ("quicklaunch:\n  searchDescriptions: true\n  hideInternetSearch: false\n  showSearchSuggestions: true\n  provider: google\n\n")


def settings_quicklaunch(settings, seen):
    if QUICKLAUNCH_DONE in seen:
        return settings, seen
    seen = sorted(set(seen) | {QUICKLAUNCH_DONE})
    if re.search(r"(?m)^quicklaunch:", settings):
        return settings, seen
    m = re.search(r"(?m)^%s" % re.escape(LAYOUT_MARK), settings) or re.search(r"(?m)^layout:", settings)
    if m:
        return settings[:m.start()] + QUICKLAUNCH_BLOCK + settings[m.start():], seen
    return settings.rstrip("\n") + "\n\n" + QUICKLAUNCH_BLOCK.rstrip("\n") + "\n", seen


def background_image(settings):
    m = re.search(r"(?m)^background:[ \t]*\n((?:[ \t]+.*\n|[ \t]*\n)*)", settings)
    i = re.search(r"(?m)^[ \t]+image:[ \t]*(.*?)\s*$", m.group(1)) if m else None
    return i.group(1).strip("'\"") if i else ""


def settings_with_background(settings, value):
    m = re.search(r"(?m)^background:[ \t]*\n((?:[ \t]+.*\n|[ \t]*\n)*)", settings)
    if not m:
        return settings
    block = re.sub(r"(?m)^([ \t]+image:[ \t]*).*$", lambda x: x.group(1) + value, m.group(1), count=1)
    return settings[:m.start(1)] + block + settings[m.end(1):]


def group_names(text):
    return [m.group(1).strip().strip("'\"") for m in re.finditer(r"(?m)^- ([^\n#]+?):\s*(?:#.*)?$", text)]


def yaml_key(name):
    if re.search(r"[:#\[\]{},*!|>'\"%@`]|^[&?-]|^\s|\s$", name):
        return "'%s'" % name.replace("'", "''")
    return name


def layout_renamed(settings):
    m = re.search(r"(?m)^layout:[ \t]*(?:#.*)?$", settings)
    if not m:
        return settings
    head, tail = settings[:m.end()], settings[m.end():]
    lines = tail.split("\n")
    for i, l in enumerate(lines):
        k = re.match(r"^  ([^\s#][^:]*?):\s*$", l)
        if k and k.group(1) in OLD_NAMES:
            lines[i] = "  %s:" % OLD_NAMES[k.group(1)]
        t = re.match(r"^    tab:\s*(\S+)\s*$", l)
        if t and t.group(1) in OLD_TABS:
            lines[i] = "    tab: %s" % OLD_TABS[t.group(1)]
        if l and l[0] not in " \t#":
            break
    return head + "\n".join(lines)


def linkedit_at(lines, start, end, g, default):
    keys = [i for i in range(start + 1, end) if re.match(r"^  \S", lines[i])]

    def block_end(i):
        n = [k for k in keys if k > i]
        return n[0] if n else end

    def tab_of(i):
        for j in range(i + 1, block_end(i)):
            m = re.match(r"^    tab:\s*(\S+)\s*$", lines[j])
            if m:
                return m.group(1)
        return None
    if g != "Edit Links":
        mine = next((i for i in keys if re.match(r"^  '?Edit Links'?:\s*$", lines[i]) and tab_of(i) == "Links"), None)
        if mine is not None:
            return block_end(mine)
    first = next((i for i in keys if tab_of(i) == "Links"), None)
    return default if first is None else first


def terminal_at(lines, start, end, default):
    keys = [i for i in range(start + 1, end) if re.match(r"^  \S", lines[i])]
    last = None
    for n, i in enumerate(keys):
        stop = keys[n + 1] if n + 1 < len(keys) else end
        if any(re.match(r"^    tab:\s*Customize\s*$", lines[j]) for j in range(i + 1, stop)):
            last = stop
    return default if last is None else last


def layout_complete(settings, service_groups, bookmark_groups, seen):
    """Add groups that the layout block does not list yet to a tab, so they do not appear on every tab. Groups already offered once are left alone."""
    m = re.search(r"(?m)^layout:[ \t]*(?:#.*)?$", settings)
    present = [g for g in service_groups + bookmark_groups if g]
    if not m:
        return settings, sorted(set(seen) | set(present))
    lines = settings.split("\n")
    start = settings[:m.start()].count("\n")
    end = start + 1
    while end < len(lines) and (lines[end].strip() == "" or lines[end][0] in " \t#"):
        end += 1
    while end > start + 1 and lines[end - 1].strip() == "":
        end -= 1
    known = set()
    for l in lines[start + 1:end]:
        k = re.match(r"^  ([^\s#][^:]*?):\s*$", l) or re.match(r"^  '([^']+)':\s*$", l)
        if k:
            known.add(k.group(1).strip())
    add = []
    for tab, icon, groups in (("Home", "mdi-apps", service_groups), ("Links", "mdi-bookmark-multiple", bookmark_groups)):
        for g in groups:
            if g and g not in known and g not in seen and g not in [a[0] for a in add]:
                add.append((g, "Stats" if g in STATS_GROUPS and tab == "Home" else tab, icon))
    for g, tab, icon in add:
        if tab == "Stats":
            icon_g, cols_g = STATS_GROUPS[g]
            new = ["  %s:" % yaml_key(g), "    tab: Stats", "    icon: %s" % icon_g, "    style: row", "    columns: %d" % cols_g]
        elif g in CUSTOMIZE_GROUPS:
            icon_g, cols_g = CUSTOMIZE_GROUPS[g]
            new = ["  %s:" % yaml_key(g), "    tab: Customize", "    icon: %s" % icon_g, "    style: row", "    columns: %d" % cols_g]
        elif g in TERMINAL_GROUPS:
            icon_g, cols_g = TERMINAL_GROUPS[g]
            new = ["  %s:" % yaml_key(g), "    tab: Customize", "    icon: %s" % icon_g, "    style: row", "    columns: %d" % cols_g]
        elif g in LINKEDIT_GROUPS:
            icon_g, cols_g = LINKEDIT_GROUPS[g]
            new = ["  %s:" % yaml_key(g), "    tab: Links", "    icon: %s" % icon_g, "    style: row", "    columns: %d" % cols_g]
        elif g in CALENDAR_GROUPS:
            icon_g, cols_g = CALENDAR_GROUPS[g]
            new = ["  %s:" % yaml_key(g), "    tab: Home", "    icon: %s" % icon_g, "    style: row", "    columns: %d" % cols_g]
        else:
            new = ["  %s:" % yaml_key(g), "    tab: %s" % tab, "    icon: %s" % ("mdi-dots-horizontal-circle" if g.lower() == "others" else icon)]
        at = end
        if g in TERMINAL_GROUPS:
            at = terminal_at(lines, start, end, at)
        elif g in LINKEDIT_GROUPS:
            at = linkedit_at(lines, start, end, g, at)
        after = STATS_AFTER.get(g)
        if tab == "Stats" and after:
            for i in range(start + 1, end):
                if re.match(r"^  '?%s'?:\s*$" % re.escape(after), lines[i]):
                    at = i + 1
                    while at < end and lines[at].startswith("    "):
                        at += 1
                    break
        lines[at:at] = new
        end += len(new)
    return "\n".join(lines), sorted(set(seen) | set(present))


STATS_BEFORE_LINKS = "~stats-before-links"
CALENDAR_ON_STATS = "~calendar-on-stats"
CALENDAR_ON_HOME = "~calendar-on-home"


def layout_entries(settings):
    """Split the layout block of settings.yaml into its head, the list of groups and the tail."""
    m = re.search(r"(?m)^layout:[ \t]*(?:#.*)?$", settings)
    if not m:
        return None
    head = settings[:m.end()]
    lines = settings[m.end():].split("\n")
    end = 1
    while end < len(lines) and (lines[end].strip() == "" or lines[end][0] in " \t#"):
        end += 1
    while end > 1 and lines[end - 1].strip() == "":
        end -= 1
    entries, cur = [], None
    for l in lines[1:end]:
        if re.match(r"^  \S", l):
            cur = [l]
            entries.append(cur)
        elif cur is not None:
            cur.append(l)
    return head, entries, lines[end:], lines[0]


def _entry_tab(e):
    for l in e:
        k = re.match(r"^    tab:\s*(\S+)\s*$", l)
        if k:
            return k.group(1)
    return None


def _entry_name(e):
    k = re.match(r"^  '?([^'#:][^']*?)'?:\s*$", e[0])
    return k.group(1).strip() if k else ""


def _entries_text(parts):
    head, entries, tail, rest = parts
    body = "\n".join(l for e in entries for l in e)
    return head + rest + ("\n" + body if body else "") + ("\n" + "\n".join(tail) if tail else "")


def layout_calendar_on_stats(settings, seen):
    if CALENDAR_ON_STATS in seen:
        return settings, seen
    seen = sorted(set(seen) | {CALENDAR_ON_STATS})
    parts = layout_entries(settings)
    if not parts:
        return settings, seen
    head, entries, tail, rest = parts
    cal = next((e for e in entries if _entry_name(e) == "Calendar" and _entry_tab(e) == "Home"), None)
    if cal is None:
        return settings, seen
    entries.remove(cal)
    for i, l in enumerate(cal):
        if re.match(r"^    tab:\s*\S+\s*$", l):
            cal[i] = "    tab: Stats"
    at = next((i + 1 for i, e in enumerate(entries) if _entry_name(e) == "Folder Sizes"), None)
    if at is None:
        stats_at = [i for i, e in enumerate(entries) if _entry_tab(e) == "Stats"]
        at = stats_at[-1] + 1 if stats_at else len(entries)
    entries.insert(at, cal)
    return _entries_text((head, entries, tail, rest)), seen


def layout_calendar_on_home(settings, seen):
    if CALENDAR_ON_HOME in seen:
        return settings, seen
    seen = sorted(set(seen) | {CALENDAR_ON_HOME})
    parts = layout_entries(settings)
    if not parts:
        return settings, seen
    head, entries, tail, rest = parts
    cal = next((e for e in entries if _entry_name(e) == "Calendar" and _entry_tab(e) == "Stats"), None)
    if cal is None:
        return settings, seen
    entries.remove(cal)
    for i, l in enumerate(cal):
        if re.match(r"^    tab:\s*\S+\s*$", l):
            cal[i] = "    tab: Home"
    home_at = [i for i, e in enumerate(entries) if _entry_tab(e) == "Home"]
    entries.insert(home_at[-1] + 1 if home_at else 0, cal)
    return _entries_text((head, entries, tail, rest)), seen


def layout_stats_before_links(settings, seen):
    if STATS_BEFORE_LINKS in seen:
        return settings, seen
    seen = sorted(set(seen) | {STATS_BEFORE_LINKS})
    parts = layout_entries(settings)
    if not parts:
        return settings, seen
    head, entries, tail, rest = parts
    first_links = next((i for i, e in enumerate(entries) if _entry_tab(e) == "Links"), None)
    if first_links is None:
        return settings, seen
    later = [e for e in entries[first_links:] if _entry_tab(e) == "Stats"]
    if not later:
        return settings, seen
    keep = [e for e in entries[first_links:] if _entry_tab(e) != "Stats"]
    entries = entries[:first_links] + later + keep
    return _entries_text((head, entries, tail, rest)), seen


LINKEDIT_FIRST = "~linkedit-first"


def layout_linkedit_first(settings, seen):
    if LINKEDIT_FIRST in seen:
        return settings, seen
    seen = sorted(set(seen) | {LINKEDIT_FIRST})
    parts = layout_entries(settings)
    if not parts:
        return settings, seen
    head, entries, tail, rest = parts
    mine = [e for e in entries if _entry_name(e) in LINKEDIT_GROUPS and _entry_tab(e) == "Links"]
    if not mine:
        return settings, seen
    mine.sort(key=lambda e: list(LINKEDIT_GROUPS).index(_entry_name(e)))
    others = [e for e in entries if e not in mine]
    first = next((i for i, e in enumerate(others) if _entry_tab(e) == "Links"), None)
    if first is None:
        return settings, seen
    entries = others[:first] + mine + others[first:]
    return _entries_text((head, entries, tail, rest)), seen


TERMINAL_MOVED = "~terminal-in-customize"


def layout_terminal_to_customize(settings, seen):
    if TERMINAL_MOVED in seen:
        return settings, seen
    seen = sorted(set(seen) | {TERMINAL_MOVED})
    parts = layout_entries(settings)
    if not parts:
        return settings, seen
    head, entries, tail, rest = parts
    mine = next((e for e in entries if _entry_name(e) in TERMINAL_GROUPS and _entry_tab(e) == "Links"), None)
    if mine is None:
        return settings, seen
    mine = [("    tab: Customize" if re.match(r"^    tab:\s*Links\s*$", l) else l) for l in mine]
    others = [e for e in entries if _entry_name(e) not in TERMINAL_GROUPS]
    last = max((i for i, e in enumerate(others) if _entry_tab(e) == "Customize"), default=None)
    entries = others + [mine] if last is None else others[:last + 1] + [mine] + others[last + 1:]
    return _entries_text((head, entries, tail, rest)), seen


HOME_ORDER = "~home-order"
HOME_FIRST = ["Network & DNS", "Monitoring & Management", "Files & Photos", "Media & Entertainment"]


def layout_home_order(settings, seen):
    if HOME_ORDER in seen:
        return settings, seen
    seen = sorted(set(seen) | {HOME_ORDER})
    parts = layout_entries(settings)
    if not parts:
        return settings, seen
    head, entries, tail, rest = parts
    slots = [i for i, e in enumerate(entries) if _entry_tab(e) == "Home"]
    home = [entries[i] for i in slots]
    first = [next(e for e in home if _entry_name(e) == n) for n in HOME_FIRST if any(_entry_name(e) == n for e in home)]
    ordered = first + [e for e in home if e not in first]
    if ordered == home:
        return settings, seen
    for i, e in zip(slots, ordered):
        entries[i] = e
    return _entries_text((head, entries, tail, rest)), seen


def layout_columns_changed(settings, seen, group, old, new, marker):
    if marker in seen:
        return settings, seen
    seen = sorted(set(seen) | {marker})
    lines = settings.split("\n")
    for i, l in enumerate(lines):
        if re.match(r"^  %s:\s*$" % re.escape(group), l):
            for j in range(i + 1, len(lines)):
                if lines[j] and not lines[j].startswith("    "):
                    break
                if re.match(r"^    columns:\s*%d\s*$" % old, lines[j]):
                    lines[j] = "    columns: %d" % new
                    break
            break
    return "\n".join(lines), seen


def layout_storage_wide(settings, seen):
    return layout_columns_changed(settings, seen, "Storage", 2, 3, STORAGE_WIDE)


def layout_music_wide(settings, seen):
    return layout_columns_changed(settings, seen, "Music Library", 1, 2, MUSIC_WIDE)
