# ================================================================ dashboard layout: tabs, groups, styles and settings edits (managed blocks)
CSS_LAYOUT_MARK = "How this file is organised"      # in the header of the shipped custom.css since it was tidied up
THEME_BEGIN, THEME_END = "/* >>> homelab theme >>>", "/* <<< homelab theme <<< */"      # the block `homelab theme` writes


def css_new_layout(live, shipped):
    """This machine's custom.css moved to the shipped, tidier layout, with everything that is this machine's own kept:
    the accent colour of every card, the numbers in :root that were changed (the last value wins, like in the browser) and
    the block `homelab theme` wrote. A file that is already in the new layout is returned as it is (it may have been edited)."""
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


TABS_BEGIN, TABS_END = "/* >>> homelab tabs >>>", "/* <<< homelab tabs <<< */"      # the block of tab styles in the shipped custom.css
LAYOUT_MARK = "# Tabs and group icons"      # the comment above the layout: block at the end of the shipped settings.yaml


def css_tabs_block(live, shipped):
    """This machine's custom.css with the managed tab-style block put in, or brought up to date. Everything outside the block
    is left alone. The block goes in front of the block `homelab theme` writes, or at the end."""
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


JS_BEGIN, JS_END = "/* >>> homelab groups >>>", "/* <<< homelab groups <<< */"      # the block in the shipped custom.js
PLAYER_JS_BEGIN, PLAYER_JS_END = "/* >>> homelab player >>>", "/* <<< homelab player <<< */"      # the second block: keeps the music playing
EXTRAS_JS_BEGIN, EXTRAS_JS_END = "/* >>> homelab extras >>>", "/* <<< homelab extras <<< */"      # the third block: health line, fold and shrink buttons, Stats bars
PANEL_JS_BEGIN, PANEL_JS_END = "/* >>> homelab panel >>>", "/* <<< homelab panel <<< */"      # the fourth block: the live preview of the control panel (Customize tab)
JS_BLOCKS = [(JS_BEGIN, JS_END), (PLAYER_JS_BEGIN, PLAYER_JS_END), (EXTRAS_JS_BEGIN, EXTRAS_JS_END), (PANEL_JS_BEGIN, PANEL_JS_END)]


def js_put_block(live, shipped, begin, end):
    """The live custom.js with one managed block of the shipped file put in, or brought up to date."""
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
    """This machine's custom.js with the managed blocks put in, or brought up to date: the group tags (they let custom.css colour each
    bookmark group), the player (it keeps the Navidrome music playing when the tab changes) and the extras (health line, fold and shrink
    buttons, bars on the Stats tab). Anything else in the file is left alone.
    A missing file becomes the shipped file."""
    for begin, end in JS_BLOCKS:
        live = js_put_block(live, shipped, begin, end)
    return live


STATS_BEGIN, STATS_END = "# >>> homelab stats >>>", "# <<< homelab stats <<<"      # the block of STATS groups in the shipped services.yaml
# The STATS groups: name -> (icon, columns). layout_complete puts them on the Stats tab (never on Home).
STATS_GROUPS = {"At a Glance": ("mdi-view-dashboard", 4), "Music Library": ("mdi-music", 2), "Library Totals": ("mdi-image-multiple", 2),
                "Storage": ("mdi-harddisk", 3), "Backup & Updates": ("mdi-backup-restore", 2), "Folder Sizes": ("mdi-folder-multiple", 1)}
STATS_AFTER = {"Music Library": "At a Glance"}          # a STATS group that is added later goes right under this one, not at the end
MUSIC_WIDE = "~music-2-columns"                         # the same for the Music Library row (two cards)
STORAGE_WIDE = "~storage-3-columns"                     # in the groups-seen list: the Storage row was widened to three cards (done once)
# Names and tab names used before they were capitalised: layout_renamed() renames them in a layout: block that has them.
OLD_NAMES = {"At a glance": "At a Glance", "Library totals": "Library Totals", "Backup & updates": "Backup & Updates", "Folder sizes": "Folder Sizes"}
OLD_TABS = {"HOME": "Home", "LINKS": "Links", "STATS": "Stats"}


CAL_BEGIN, CAL_END = "# >>> homelab calendar >>>", "# <<< homelab calendar <<<"      # the block with the Calendar group in the shipped services.yaml
CUSTOM_BEGIN, CUSTOM_END = "# >>> homelab customize >>>", "# <<< homelab customize <<<"      # the block with the Customize group (the control panel) in the shipped services.yaml
CUSTOMIZE_GROUPS = {"Customize": ("mdi-tune", 1)}      # name -> (icon, columns): a tab of its own, after the others, one big card
LINKEDIT_GROUPS = {"Edit Links": ("mdi-pencil-box-multiple", 1)}      # name -> (icon, columns): on the Links tab, above the bookmarks, one drop-down card
CALENDAR_GROUPS = {"Calendar": ("mdi-calendar-month", 2)}      # name -> (icon, columns): on the Home tab, in a row of its own, last


def services_block(live, shipped, begin, end):
    """This machine's services.yaml with a managed block (the lines between two marker lines of the shipped file) put in at the end, or
    brought up to date. Everything outside the block is left alone. `shipped` already has this machine's address filled in."""
    a = shipped.find(begin)
    z = shipped.find(end, a) if a >= 0 else -1
    if a < 0 or z < 0:
        return live
    block = shipped[a:z + len(end)]
    la = live.find(begin)
    lz = live.find(end, la) if la >= 0 else -1
    if la >= 0 and lz >= 0:
        return live[:la] + block + live[lz + len(end):]
    return live.rstrip("\n") + "\n\n" + block + "\n"


def services_stats_block(live, shipped):
    """The STATS groups (see services_block)."""
    return services_block(live, shipped, STATS_BEGIN, STATS_END)


def services_customize_block(live, shipped):
    """The Customize group, the control panel's card (see services_block)."""
    return services_block(live, shipped, CUSTOM_BEGIN, CUSTOM_END)


def services_calendar_block(live, shipped):
    """The Calendar group (see services_block)."""
    return services_block(live, shipped, CAL_BEGIN, CAL_END)


def settings_with_layout(live, shipped):
    """This machine's settings.yaml with the tabs and group icons (the layout: block) and the small settings (hideVersion, language)
    added when they are missing. Nothing that is already there is changed."""
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


QUICKLAUNCH_DONE = "~quicklaunch"                        # in the groups-seen list: Quick Launch was offered once
QUICKLAUNCH_BLOCK = ("# Quick Launch: start typing anywhere on the page to jump to a card, search the web or open an address.\n"
                     "quicklaunch:\n  searchDescriptions: true\n  hideInternetSearch: false\n  showSearchSuggestions: true\n  provider: google\n\n")


def settings_quicklaunch(settings, seen):
    """Quick Launch is added to settings.yaml once (a machine without a quicklaunch: setting). Taking it out later is respected.
    Returns (settings, seen)."""
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
    """The picture of the background: block of settings.yaml (a web address or /images/name), or ''."""
    m = re.search(r"(?m)^background:[ \t]*\n((?:[ \t]+.*\n|[ \t]*\n)*)", settings)
    i = re.search(r"(?m)^[ \t]+image:[ \t]*(.*?)\s*$", m.group(1)) if m else None
    return i.group(1).strip("'\"") if i else ""


def settings_with_background(settings, value):
    """settings.yaml with the picture of the background: block set to `value` (the block is not changed otherwise)."""
    m = re.search(r"(?m)^background:[ \t]*\n((?:[ \t]+.*\n|[ \t]*\n)*)", settings)
    if not m:
        return settings
    block = re.sub(r"(?m)^([ \t]+image:[ \t]*).*$", lambda x: x.group(1) + value, m.group(1), count=1)
    return settings[:m.start(1)] + block + settings[m.end(1):]


def group_names(text):
    """The names of the top level groups of a services.yaml or bookmarks.yaml (the lines that start with '- Name:')."""
    return [m.group(1).strip().strip("'\"") for m in re.finditer(r"(?m)^- ([^\n#]+?):\s*(?:#.*)?$", text)]


def yaml_key(name):
    """A group name as a YAML key (quoted when it has a character YAML would misread)."""
    if re.search(r"[:#\[\]{},*!|>'\"%@`]|^[&?-]|^\s|\s$", name):
        return "'%s'" % name.replace("'", "''")
    return name


def layout_renamed(settings):
    """Older layout: blocks name the STATS groups and the tabs in capitals / small letters ("At a glance", "tab: HOME"). Rename them in place
    (their icon and every other line stay) so the layout and the services.yaml block agree. Only the shipped names are touched."""
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
            break                      # the layout: block ends at the next top level key
    return head + "\n".join(lines)


def layout_complete(settings, service_groups, bookmark_groups, seen):
    """Put the groups of this machine that the layout: block does not know yet on a tab (a service group on Home, a bookmark group on
    Links), so they do not show up on every tab. Only groups that were never offered before (not in `seen`) are added, so a group
    that was taken out of the layout on purpose stays out. Returns (settings, seen)."""
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
        elif g in CUSTOMIZE_GROUPS:                              # the control panel has a tab of its own, after the others
            icon_g, cols_g = CUSTOMIZE_GROUPS[g]
            new = ["  %s:" % yaml_key(g), "    tab: Customize", "    icon: %s" % icon_g, "    style: row", "    columns: %d" % cols_g]
        elif g in LINKEDIT_GROUPS:                               # the link editor is on the Links tab
            icon_g, cols_g = LINKEDIT_GROUPS[g]
            new = ["  %s:" % yaml_key(g), "    tab: Links", "    icon: %s" % icon_g, "    style: row", "    columns: %d" % cols_g]
        elif g in CALENDAR_GROUPS:                               # the Calendar is on the Home tab, in a row of its own, last
            icon_g, cols_g = CALENDAR_GROUPS[g]
            new = ["  %s:" % yaml_key(g), "    tab: Home", "    icon: %s" % icon_g, "    style: row", "    columns: %d" % cols_g]
        else:
            new = ["  %s:" % yaml_key(g), "    tab: %s" % tab, "    icon: %s" % ("mdi-dots-horizontal-circle" if g.lower() == "others" else icon)]
        at = end
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


STATS_BEFORE_LINKS = "~stats-before-links"               # in the groups-seen list: the Stats tab was put in front of the Links tab (done once)
CALENDAR_ON_STATS = "~calendar-on-stats"                 # the Calendar was moved from Home to the end of the Stats tab (done once)
CALENDAR_ON_HOME = "~calendar-on-home"                   # ... and then to the end of the Home tab, where it is seen first (done once)


def layout_entries(settings):
    """(head, entries, tail, rest) of the layout: block: head is the text up to and including the line "layout:", entries is a list of groups
    (each a list of lines: the "  Name:" line and what belongs to it) and tail is the list of lines after the block. None without a layout."""
    m = re.search(r"(?m)^layout:[ \t]*(?:#.*)?$", settings)
    if not m:
        return None
    head = settings[:m.end()]
    lines = settings[m.end():].split("\n")            # lines[0] is the rest of the "layout:" line (empty)
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
    """The Calendar group moves from the Home tab to the end of the Stats tab (right under Folder Sizes), once. A Calendar that was put
    somewhere else on purpose later is left alone. Returns (settings, seen)."""
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
    """The Calendar group moves from the Stats tab to the end of the Home tab (after the last Home group), once. A Calendar that was put
    somewhere else on purpose later is left alone. Returns (settings, seen)."""
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
    """The tabs are shown in the order their groups come in the layout: the Stats groups are put in front of the first Links group, so
    the tabs read Home, Stats, Links. Once; an order you chose later is left alone. Returns (settings, seen)."""
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


def layout_columns_changed(settings, seen, group, old, new, marker):
    """`columns: old` of one group of the layout becomes `columns: new`, once (the marker is put in the groups-seen list, so a later change
    by the owner is left alone). Returns (settings, seen)."""
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
    """The Storage row holds three cards since the drive temperatures were added: columns 2 becomes 3, once."""
    return layout_columns_changed(settings, seen, "Storage", 2, 3, STORAGE_WIDE)


def layout_music_wide(settings, seen):
    """The Music Library row holds two cards since Recently Saved Songs was added: columns 1 becomes 2, once."""
    return layout_columns_changed(settings, seen, "Music Library", 1, 2, MUSIC_WIDE)
