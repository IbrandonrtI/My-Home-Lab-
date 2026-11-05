#!/usr/bin/env python3
"""Tests for the Homepage tabs: settings_with_layout (layout: block, hideVersion, language) and css_tabs_block (managed tab styles).
Run: python3 tests/t_tabs.py   (last line is OK or FAIL)"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.join(HERE, "..", "installer", "homelab-setup")
os.environ["HLS_FAKE"] = "1"
loader = importlib.machinery.SourceFileLoader("hls", PROG)
spec = importlib.util.spec_from_loader("hls", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

bad = 0


def check(name, ok, extra=""):
    global bad
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   " + extra))


rd = lambda f: open(os.path.join(HERE, "..", "homepage-config", f)).read()
S, C = rd("settings.yaml"), rd("custom.css")

# ---- the shipped files
check("shipped settings.yaml has a layout: block", re.search(r"(?m)^layout:", S) is not None)
tabs = re.findall(r"(?m)^    tab: (\w+)$", S)
check("exactly three tabs are used: Home, Links and Stats", sorted(set(tabs)) == ["Home", "Links", "Stats"], str(set(tabs)))
check("every group in layout has an icon", len(re.findall(r"(?m)^    icon: mdi-[\w-]+$", S)) == len(tabs))
svc_groups = re.findall(r"(?m)^- ([^:\n]+):\s*$", rd("services.yaml"))
book_groups = re.findall(r"(?m)^- ([^:\n]+):\s*$", rd("bookmarks.yaml"))
lay = re.findall(r"(?m)^  ([^\s:][^:\n]*):\s*$", S[S.index("\nlayout:"):])
check("every shipped service group is on a tab", all(g in lay for g in svc_groups), str(svc_groups))
stat_groups = list(m.STATS_GROUPS)
check("the STATS groups of the code are the groups of the shipped block",
      stat_groups == [g for g in svc_groups if g in m.STATS_GROUPS] and len(svc_groups) - len(stat_groups) - len(m.CALENDAR_GROUPS) == 3, str(svc_groups))
for g in stat_groups:
    blk = re.search(r"(?m)^  %s:\n((?:    .*\n)+)" % re.escape(g), S).group(0)
    ok = "tab: Stats" in blk and "icon: %s" % m.STATS_GROUPS[g][0] in blk and "columns: %d" % m.STATS_GROUPS[g][1] in blk
    check("the shipped layout puts %s on the STATS tab" % g, ok, blk)
check("every shipped bookmark group is on the LINKS tab", all(g in lay for g in book_groups), str(book_groups))
check("all four card sections of homelab-cards are in the layout",
      all(g in lay for g in ["Network & DNS", "Monitoring & Management", "Files & Photos", "Media & Entertainment"]))
check("hideVersion and language are in the shipped file", "hideVersion: true" in S and "language: en" in S)
check("the background block still ends before the layout comment", S.index("opacity: 80") < S.index(m.LAYOUT_MARK))
check("the shipped custom.css has the managed tabs block", m.TABS_BEGIN in C and m.TABS_END in C)
check("a shipped file is already up to date", m.settings_with_layout(S, S) == S and m.css_tabs_block(C, C) == C)

# ---- an older settings.yaml
OLD = S[:S.index("hideVersion: true\n")] + S[S.index("background:"):S.index("\n" + m.LAYOUT_MARK)].lstrip("\n")
OLD = OLD.rstrip("\n") + "\n"
OLD = OLD.replace("title: Home Lab", "title: My Own Title")
check("(set up) the old file has no layout and no hideVersion", "layout:" not in OLD and "hideVersion" not in OLD and "language" not in OLD)
new = m.settings_with_layout(OLD, S)
check("layout, hideVersion and language are added", "\nlayout:" in new and "hideVersion: true" in new and "language: en" in new)
check("this machine's own title is kept", "title: My Own Title" in new)
check("the background block is kept", new.count("  brightness: 42") == 1 and "image: https://images.unsplash.com" in new)
check("the small settings sit at the top level, not inside another block", re.search(r"(?m)^hideVersion: true$", new) and re.search(r"(?m)^language: en$", new))
check("running it again changes nothing", m.settings_with_layout(new, S) == new)
check("a file with its own layout keeps it", m.settings_with_layout(OLD + "layout:\n  Mine:\n    tab: X\n", S).count("layout:") == 1)
check("an own hideVersion: false is not changed", "hideVersion: false" in m.settings_with_layout(OLD + "hideVersion: false\n", S))
check("a file without a newline at the end is handled", m.settings_with_layout(OLD.rstrip("\n"), S).count("\nlayout:") == 1)
check("an empty file gets the block", "layout:" in m.settings_with_layout("", S))

# ---- Quick Launch and the saved background picture
check("the shipped settings.yaml has Quick Launch above the layout", "\nquicklaunch:\n  searchDescriptions: true" in S and S.index("quicklaunch:") < S.index(m.LAYOUT_MARK))
ql, qs = m.settings_quicklaunch(OLD + "\n" + new[new.index(m.LAYOUT_MARK):], [])
check("an older settings.yaml gets Quick Launch once, above the layout comment", ql.count("quicklaunch:") == 1 and ql.index("quicklaunch:") < ql.index(m.LAYOUT_MARK) and m.QUICKLAUNCH_DONE in qs, ql)
ql2, qs2 = m.settings_quicklaunch(ql, qs)
check("and not twice", ql2 == ql and qs2 == qs)
gone_ql = ql.replace(m.QUICKLAUNCH_BLOCK, "")
check("taking it out is respected", "quicklaunch" not in m.settings_quicklaunch(gone_ql, qs)[0])
own = OLD + "quicklaunch:\n  provider: duckduckgo\n"
check("an own quicklaunch: setting is kept as it is", m.settings_quicklaunch(own, [])[0] == own)
check("a file without any layout gets it at the end", m.settings_quicklaunch("title: X\n", [])[0].endswith("provider: google\n"))
check("the background picture is read", m.background_image(S).startswith("https://images.unsplash.com") and m.background_image("title: X\n") == "")
bg = m.settings_with_background(S, "/images/background.jpg")
check("the background picture line is changed, the rest of the block is not", "  image: /images/background.jpg\n" in bg and "  brightness: 42" in bg and "unsplash" not in bg
      and bg.count("image:") == S.count("image:") and m.background_image(bg) == "/images/background.jpg", bg[:400])
check("a file without a background block is left alone", m.settings_with_background("title: X\n", "/images/a.jpg") == "title: X\n")

# ---- the Navidrome card: a widget put into a card that homelab-cards made
SV = ("- Media & Entertainment:\n\n    - Metube:\n        id: metube-card\n        href: x\n\n"
      "    - Navidrome:\n        id: navidrome-card\n        href: https://h.ts.net:1011\n        siteMonitor: http://192.168.1.5:4533\n        icon: navidrome.svg\n"
      "        description: Music streaming server\n\n    - Other:\n        id: other-card\n        href: y\n\n- Files & Photos:\n    - Nextcloud:\n        id: nextcloud-card\n")
nv = m.services_with_iframe_widget(SV, "navidrome-card", "192.168.1.5")
check("the player is put at the end of its own card, nowhere else", "        description: Music streaming server\n        widget:\n          type: iframe\n          name: navidrome-player\n"
      "          src: http://192.168.1.5:4533\n" in nv and nv.count("widget:") == 1 and "\n\n    - Other:" in nv and "id: other-card\n        href: y" in nv, nv)
check("a card that shows the player already is not changed", m.services_with_iframe_widget(nv, "navidrome-card", "192.168.1.5") == nv)
check("a file without that card is not changed", m.services_with_iframe_widget(SV, "nothing-card", "192.168.1.5") == SV)
check("the widget type of a card is read", m.card_widget_type(nv, "navidrome-card") == "iframe" and m.card_widget_type(SV, "navidrome-card") == "" and m.card_widget_type(SV, "zzz-card") is None)
old33 = SV.replace("        description: Music streaming server\n", "        description: Music streaming server\n        widget:\n          type: navidrome\n          url: http://192.168.1.5:4533\n          user: B\n          token: t\n          salt: s\n")
old33 = old33.replace("    - Other:", "    - Navidrome Player:\n        id: navidrome-player\n        icon: navidrome.svg\n        widget:\n          type: iframe\n          src: x\n\n    - Other:")
mig = m.services_without_card(m.services_with_iframe_widget(old33, "navidrome-card", "192.168.1.5"), "navidrome-player")
check("the live numbers of zip 33 are replaced by the player, in the same card", m.card_widget_type(mig, "navidrome-card") == "iframe" and "type: navidrome\n" not in mig and "token:" not in mig, mig)
check("the separate player card of zip 33 is taken out, the other cards stay", "navidrome-player\n        icon" not in mig and "id: navidrome-player" not in mig.replace("name: navidrome-player", "") and "id: other-card" in mig and "id: metube-card" in mig, mig)
check("taking out a card that is not there changes nothing", m.services_without_card(SV, "navidrome-player") == SV)
first = m.card_to_top(SV, "navidrome-card")
check("the Navidrome card moves to the top of its group", re.findall(r"(?m)^    - (.+):$", first.split("- Files")[0]) == ["Navidrome", "Metube", "Other"] and m.card_to_top(first, "navidrome-card") == first and m.navidrome_card_first(first) and not m.navidrome_card_first(SV), first)
lc = SV.replace("    - Navidrome:", "    - navidrome:")
fixed = m.navidrome_card_named(lc)
check("the card is called Navidrome and described as Spotify Music Player", "    - Navidrome:\n        id: navidrome-card" in fixed and "description: Spotify Music Player\n" in fixed and "Music streaming server" not in fixed, fixed)
check("a second pass changes nothing", m.navidrome_card_named(fixed) == fixed)
mine = lc.replace("description: Music streaming server", "description: My own words").replace("    - navidrome:", "    - My Music:")
check("a name or description written by you is left alone", m.navidrome_card_named(mine) == mine)
check("the other cards are not renamed", "    - Metube:" in fixed and "description: Spotify" not in fixed.split("id: other-card")[1].split("\n\n")[0])
check("the player card of the first version is no more", not hasattr(m, "navidrome_player_card"))
check("a card at the very end of the file gets the player", m.services_with_iframe_widget(SV, "nextcloud-card", "h").rstrip("\n").endswith("loadingStrategy: lazy"))
check("the shipped navidrome.yaml: pinned image, music folder read-only, its own port", re.search(r"image: ghcr\.io/navidrome/navidrome:\d+\.\d+\.\d+", open(os.path.join(HERE, "..", "stacks", "navidrome.yaml")).read())
      and ":/music:ro" in open(os.path.join(HERE, "..", "stacks", "navidrome.yaml")).read() and '"4533:4533"' in open(os.path.join(HERE, "..", "stacks", "navidrome.yaml")).read())

# ---- custom.css
BASE = C[:C.index(m.TABS_BEGIN)].rstrip("\n") + "\n"
check("(set up) an old css has no tabs block", m.TABS_BEGIN not in BASE)
r = m.css_tabs_block(BASE, C)
check("the tabs block is added at the end", r.count(m.TABS_BEGIN) == 1 and r.startswith(BASE.rstrip("\n")))
check("running it again changes nothing", m.css_tabs_block(r, C) == r)
theme = "\n/* >>> homelab theme >>> written by: homelab theme */\n.service-card { color: red; }\n/* <<< homelab theme <<< */\n"
r2 = m.css_tabs_block(BASE + theme, C)
check("the block goes in front of the theme block", r2.index(m.TABS_BEGIN) < r2.index(m.THEME_BEGIN) and r2.endswith(theme.lstrip("\n")) or r2.rstrip().endswith("/* <<< homelab theme <<< */"))
check("the theme block is kept as it was", ".service-card { color: red; }" in r2 and r2.count(m.THEME_BEGIN) == 1)
stale = BASE + "\n\n/* >>> homelab tabs >>> old\nbutton { color: pink; }\n/* <<< homelab tabs <<< */\n/* mine */\n.x { y: z; }\n"
r3 = m.css_tabs_block(stale, C)
check("an older tabs block is replaced by the new one", "color: pink" not in r3 and r3.count(m.TABS_BEGIN) == 1)
check("rules after the block are kept", "/* mine */\n.x { y: z; }" in r3)
check("no shipped block: the file is left alone", m.css_tabs_block(BASE, "") == BASE)

# ---- groups of this machine that the layout does not know yet
check("the tabs css keeps the side margins of the tab bar", re.search(r"#tabs\s*\{[^}]*margin:\s*[\d.]+px 0", C) is None and "margin-top: 6px" in C)
base = "title: X\nlayout:\n  Network & DNS:\n    tab: Home\n    icon: mdi-lan\n  Productivity:\n    tab: Links\n"
r, seen = m.layout_complete(base, ["Network & DNS", "My Apps"], ["Productivity", "Others"], [])
check("a new service group goes on Home and a new bookmark group on Links",
      "  My Apps:\n    tab: Home\n    icon: mdi-apps" in r and "  Others:\n    tab: Links\n    icon: mdi-dots-horizontal-circle" in r)
check("groups already in the layout are not added twice", r.count("Network & DNS:") == 1 and r.count("Productivity:") == 1)
check("every group is now remembered", seen == ["My Apps", "Network & DNS", "Others", "Productivity"], str(seen))
check("the file before the layout is kept", r.startswith("title: X\nlayout:"))
r2, seen2 = m.layout_complete(r, ["Network & DNS", "My Apps"], ["Productivity", "Others"], seen)
check("a second run changes nothing", r2 == r and seen2 == seen)
gone = r.replace("  Others:\n    tab: Links\n    icon: mdi-dots-horizontal-circle\n", "")
r3, _ = m.layout_complete(gone, ["Network & DNS", "My Apps"], ["Productivity", "Others"], seen)
check("a group that was taken out on purpose is not put back", "Others" not in r3)
r4, _ = m.layout_complete(r, ["Network & DNS", "My Apps", "Third"], ["Productivity", "Others"], seen)
check("a group that is new later is added once", r4.count("  Third:\n    tab: Home") == 1)
rs, _ = m.layout_complete(base, ["Network & DNS", "At a Glance", "Folder Sizes"], ["Productivity"], [])
check("the STATS groups go on the STATS tab with their icon and columns",
      "  At a Glance:\n    tab: Stats\n    icon: mdi-view-dashboard\n    style: row\n    columns: 4" in rs
      and "  Folder Sizes:\n    tab: Stats\n    icon: mdi-folder-multiple\n    style: row\n    columns: 1" in rs and "tab: Home" in rs, rs)
# a later STATS group (Music Library) goes right under At a Glance, not at the end
lay = "title: X\nlayout:\n  Network & DNS:\n    tab: Home\n  At a Glance:\n    tab: Stats\n    style: row\n    columns: 4\n  Library Totals:\n    tab: Stats\n  Folder Sizes:\n    tab: Stats\nhideVersion: true\n"
rm, sm = m.layout_complete(lay, ["Network & DNS", "At a Glance", "Music Library", "Library Totals", "Folder Sizes"], [], ["At a Glance", "Library Totals", "Folder Sizes", "Network & DNS"])
check("Music Library is put right under At a Glance, with its icon and two columns",
      "    columns: 4\n  Music Library:\n    tab: Stats\n    icon: mdi-music\n    style: row\n    columns: 2\n  Library Totals:" in rm and rm.endswith("hideVersion: true\n"), rm)
rm2, _ = m.layout_complete(rm, ["Network & DNS", "At a Glance", "Music Library", "Library Totals", "Folder Sizes"], [], sm)
check("and only once", rm2 == rm and rm.count("Music Library:") == 1)
rm3, _ = m.layout_complete(lay.replace("  At a Glance:\n    tab: Stats\n    style: row\n    columns: 4\n", ""), ["Music Library"], [], ["Network & DNS", "Library Totals", "Folder Sizes"])
check("without At a Glance in the layout it goes to the end of the layout", rm3.index("Music Library:") > rm3.index("Folder Sizes:") and rm3.endswith("hideVersion: true\n"), rm3)
# the Storage row holds three cards: columns 2 -> 3, once
st = "title: X\nlayout:\n  Storage:\n    tab: Stats\n    icon: mdi-harddisk\n    style: row\n    columns: 2\n  Folder Sizes:\n    tab: Stats\n    columns: 2\n"
sw, sws = m.layout_storage_wide(st, ["Storage"])
check("the Storage row gets three columns, the other groups keep theirs", "  Storage:\n    tab: Stats\n    icon: mdi-harddisk\n    style: row\n    columns: 3\n  Folder Sizes:\n    tab: Stats\n    columns: 2" in sw and m.STORAGE_WIDE in sws, sw)
sw2, sws2 = m.layout_storage_wide(sw.replace("columns: 3", "columns: 2"), sws)
check("it is done once: a later change by the owner stays", "columns: 2\n  Folder Sizes" in sw2 and sws2 == sws)
check("a layout without a Storage group is left alone", m.layout_storage_wide("title: X\nlayout:\n  A:\n    tab: Home\n", [])[0] == "title: X\nlayout:\n  A:\n    tab: Home\n")
ml = "title: X\nlayout:\n  Music Library:\n    tab: Stats\n    icon: mdi-music\n    style: row\n    columns: 1\n  Storage:\n    columns: 1\n"
mw, mws = m.layout_music_wide(ml, ["Music Library"])
check("the Music Library row gets two columns, once, and other groups keep theirs", "  Music Library:\n    tab: Stats\n    icon: mdi-music\n    style: row\n    columns: 2\n  Storage:\n    columns: 1" in mw
      and m.MUSIC_WIDE in mws and m.layout_music_wide(mw.replace("columns: 2", "columns: 1"), mws)[0] == mw.replace("columns: 2", "columns: 1"), mw)
check("the shipped layout has Music Library under At a Glance and three columns for Storage",
      "columns: 4\n  Music Library:" in rd("settings.yaml") and re.search(r"  Storage:\n(?:    .*\n)*?    columns: 3", rd("settings.yaml")) is not None)
check("the calendar card is no longer called Calendar like its group", "- Calendar:\n\n    - This Month:\n        id: cal-month" in rd("services.yaml"))
check("the stats css has the music and temperature colours and room between the rows", "#stat-music" in C and "#stat-temps" in C and ".services-group:has(" in C)
rs2, _ = m.layout_complete(rs, ["Network & DNS", "At a Glance", "Folder Sizes"], ["Productivity"], _)
check("and only once", rs2 == rs)
oldl = "title: X\nlayout:\n  Network & DNS:\n    tab: HOME\n    icon: mdi-lan\n  Productivity:\n    tab: LINKS\n  At a glance:\n    tab: STATS\n    icon: mdi-my-own\n    style: row\n    columns: 4\n  Folder sizes:\n    tab: STATS\nhideVersion: true\n"
rn = m.layout_renamed(oldl)
check("older capital tab names and group names are renamed in place",
      "  Network & DNS:\n    tab: Home\n" in rn and "    tab: Links\n" in rn and "  At a Glance:\n    tab: Stats\n    icon: mdi-my-own" in rn and "  Folder Sizes:\n    tab: Stats" in rn
      and "HOME" not in rn and "STATS" not in rn and "At a glance" not in rn and rn.endswith("hideVersion: true\n"), rn)
check("renaming twice changes nothing, and a file without a layout is left alone", m.layout_renamed(rn) == rn and m.layout_renamed("title: X\n") == "title: X\n")
check("a tab the user made up is kept", "tab: HOME2" in m.layout_renamed("layout:\n  A:\n    tab: HOME2\n"))
rnn, _s = m.layout_complete(rn, ["Network & DNS", "At a Glance", "Folder Sizes"], ["Productivity"], ["At a glance", "Folder sizes"])
check("after the rename the STATS groups are not added a second time", rnn.count("At a Glance:") == 1 and rnn.count("Folder Sizes:") == 1, rnn)

# ---- the STATS cards in services.yaml (a managed block at the end)
V = rd("services.yaml")
check("the shipped services.yaml has the STATS block", m.STATS_BEGIN in V and m.STATS_END in V and V.index(m.STATS_BEGIN) > V.index("- Files & Photos:"))
check("a shipped services.yaml is already up to date", m.services_stats_block(V, V) == V)
OLDV = V[:V.index(m.STATS_BEGIN)].rstrip("\n") + "\n"
newv = m.services_stats_block(OLDV, V)
check("a machine without the block gets it at the end and keeps everything before", newv.startswith(OLDV.rstrip("\n")) and newv.count(m.STATS_BEGIN) == 1)
check("running it again changes nothing", m.services_stats_block(newv, V) == newv)
stale = OLDV + "\n" + m.STATS_BEGIN + "\n- Old:\n" + m.STATS_END + "\n# mine\n"
rv = m.services_stats_block(stale, V)
check("an older block is replaced and what follows it is kept", "- Old:" not in rv and "# mine" in rv and rv.count(m.STATS_BEGIN) == 1)
check("no shipped block: the file is left alone", m.services_stats_block(OLDV, "") == OLDV)
check("the STATS cards use the address placeholder of the other cards", "http://192.168.X.X:3001/images/stats.json" in V)
ids = re.findall(r"(?m)^        id: (stat-[\w-]+)$", V)
check("every STATS card has an id that starts with stat-", len(ids) == 14 and len(set(ids)) == 14, str(ids))
check("every STATS card has its colour in the css", all(re.search(r"#%s\b[^{]*\{[^}]*--accent" % i, C) for i in ids if i not in ("stat-folders",)) and "#stat-folders" in C)
check("the icons of the groups and cards get a light colour, inside the managed block",
      "--icon-color" in C and ".service-group-icon > div" in C and ".bookmark-group-icon > div" in C and ".service-icon > div" in C
      and C.index("--icon-color") > C.index(m.TABS_BEGIN) and C.index("--icon-color") < C.index(m.TABS_END))
check("the STATS card styles are inside the managed block", C.index('li[id^="stat-"]::before') > C.index(m.TABS_BEGIN) and C.index('li[id^="stat-"]::before') < C.index(m.TABS_END))
check("no layout block: nothing is added, the groups are still remembered", m.layout_complete("title: X\n", ["A"], ["B"], [])[0] == "title: X\n" and m.layout_complete("title: X\n", ["A"], ["B"], [])[1] == ["A", "B"])
tail = base + "\n# comment\nhideVersion: true\n"
r5, _ = m.layout_complete(tail, ["Z"], [], [])
check("the group goes inside the layout block, before the keys that follow it", r5.index("  Z:") < r5.index("hideVersion") and r5.index("  Z:") > r5.index("Productivity"))
check("a name with a colon is quoted", m.yaml_key("A: b") == "'A: b'" and m.yaml_key("Plain & Name") == "Plain & Name")
check("group_names reads the top level groups", m.group_names("- Net & DNS:\n\n    - Card:\n        id: x\n- Files:\n  - A:\n") == ["Net & DNS", "Files"])
check("group_names skips comments", m.group_names("# - Not:\n- Real:  # note\n") == ["Real"])

# ---- the Calendar group in services.yaml (a second managed block) and in the layout
check("the Calendar group is on the Stats tab, in a row of its own, in the shipped layout",
      re.search(r"(?m)^  Calendar:\n    tab: Stats\n    icon: mdi-calendar-month\n    style: row\n    columns: 2\n", S) is not None)
check("the shipped services.yaml has the calendar block after the STATS block", m.CAL_BEGIN in V and m.CAL_END in V and V.index(m.CAL_BEGIN) > V.index(m.STATS_END))
check("a shipped services.yaml is up to date for the calendar too", m.services_calendar_block(V, V) == V)
NOCAL = V[:V.index(m.CAL_BEGIN)].rstrip("\n") + "\n"
nc = m.services_calendar_block(NOCAL, V)
check("a machine without the calendar block gets it at the end and keeps everything before", nc.startswith(NOCAL.rstrip("\n")) and nc.count(m.CAL_BEGIN) == 1 and m.STATS_BEGIN in nc)
check("running it again changes nothing", m.services_calendar_block(nc, V) == nc)
rv2 = m.services_calendar_block(NOCAL + "\n" + m.CAL_BEGIN + "\n- Old:\n" + m.CAL_END + "\n# mine\n", V)
check("an older calendar block is replaced and what follows it is kept", "- Old:" not in rv2 and "# mine" in rv2 and rv2.count(m.CAL_BEGIN) == 1)
check("the calendar reads the three files homelab-calendar writes",
      all("http://192.168.X.X:3001/images/%s.ics" % n in V for n in ("holidays", "observances", "events")))
rc, _s = m.layout_complete(base, ["Network & DNS", "Calendar"], ["Productivity"], [])
check("a Calendar group goes on Stats with its icon, in a row", "  Calendar:\n    tab: Stats\n    icon: mdi-calendar-month\n    style: row\n    columns: 2" in rc, rc)
names_in = lambda s: re.findall(r"(?m)^  (\S[^:]*):\n    tab:", s)
tabs_in = lambda s: [x for i, x in enumerate(re.findall(r"(?m)^    tab: (\S+)$", s)) if x not in re.findall(r"(?m)^    tab: (\S+)$", s)[:i]]
check("the tabs of the shipped layout read Home, Stats, Links, and the Calendar is the last group of Stats", tabs_in(S) == ["Home", "Stats", "Links"]
      and names_in(S)[names_in(S).index("Folder Sizes") + 1] == "Calendar" and names_in(S)[names_in(S).index("Calendar") + 1] == "Entertainment", names_in(S))
check("the shipped layout is already in the new order: the two moves change nothing", m.layout_stats_before_links(m.layout_calendar_on_stats(S, [])[0], [])[0] == S)
OLDL = ("title: X\nlayout:\n  Network & DNS:\n    tab: Home\n    icon: a\n  Calendar:\n    tab: Home\n    icon: c\n    style: row\n    columns: 2\n"
        "  Entertainment:\n    tab: Links\n    icon: e\n  Productivity:\n    tab: Links\n    icon: p\n  At a Glance:\n    tab: Stats\n    icon: g\n"
        "  Folder Sizes:\n    tab: Stats\n    icon: f\nhideVersion: true\n")
c1, s1 = m.layout_calendar_on_stats(OLDL, [])
c2, s2 = m.layout_stats_before_links(c1, s1)
check("an older layout (Calendar on Home, Links before Stats) is reordered: Home, Stats, Calendar, Links",
      names_in(c2) == ["Network & DNS", "At a Glance", "Folder Sizes", "Calendar", "Entertainment", "Productivity"] and tabs_in(c2) == ["Home", "Stats", "Links"], c2)
check("the Calendar is on the Stats tab now and keeps its icon and its row", "  Calendar:\n    tab: Stats\n    icon: c\n    style: row\n    columns: 2\n" in c2, c2)
check("the lines after the layout block are kept, and no line is lost", c2.endswith("hideVersion: true\n") and sorted(c2.split("\n")) == sorted(OLDL.replace("  Calendar:\n    tab: Home", "  Calendar:\n    tab: Stats").split("\n")), c2)
check("the two moves happen once: a second run changes nothing", m.layout_stats_before_links(m.layout_calendar_on_stats(c2, s2)[0], s2)[0] == c2 and m.CALENDAR_ON_STATS in s2 and m.STATS_BEFORE_LINKS in s2)
mine2 = c2.replace("  Calendar:\n    tab: Stats", "  Calendar:\n    tab: Home")
check("a Calendar you put back on Home later is left alone", m.layout_calendar_on_stats(mine2, s2)[0] == mine2)
check("a layout without Links groups, or without a Calendar, is not changed", m.layout_stats_before_links("layout:\n  A:\n    tab: Home\n  B:\n    tab: Stats\n", [])[0] == "layout:\n  A:\n    tab: Home\n  B:\n    tab: Stats\n"
      and m.layout_calendar_on_stats("layout:\n  A:\n    tab: Home\n", [])[0] == "layout:\n  A:\n    tab: Home\n")
check("a file without a layout block is not changed", m.layout_calendar_on_stats("title: X\n", [])[0] == "title: X\n" and m.layout_stats_before_links("title: X\n", [])[0] == "title: X\n")
check("the Calendar cards share the stats card look in the css", all(x in C for x in ('li[id^="cal-"]::before', 'li[id^="cal-"]::after', "#cal-month", "#cal-agenda")))
check("the calendar cards have ids that start with cal-", re.findall(r"(?m)^        id: (cal-[\w-]+)$", V) == ["cal-month", "cal-agenda"])

# ---- custom.js (tags every bookmark group with its name) and the bookmark card styles
J = rd("custom.js")
check("the shipped custom.js has the managed block", m.JS_BEGIN in J and m.JS_END in J)
check("no file yet: the shipped block becomes the file", m.js_groups_block("", J).strip() == J.strip())
check("a shipped file is already up to date", m.js_groups_block(J, J) == J)
own = "console.log('mine');\n"
r = m.js_groups_block(own, J)
check("an own script is kept and the block is added after it", r.startswith(own.rstrip("\n")) and r.count(m.JS_BEGIN) == 1)
check("running it again changes nothing", m.js_groups_block(r, J) == r)
stale = own + "\n/* >>> homelab groups >>> old\nvar old = 1;\n/* <<< homelab groups <<< */\nconsole.log('after');\n"
r = m.js_groups_block(stale, J)
check("an older block is replaced and the code around it is kept", "var old" not in r and "console.log('mine')" in r and "console.log('after')" in r and r.count(m.JS_BEGIN) == 1)
check("no shipped block: the file is left alone", m.js_groups_block(own, "") == own)
check("the css colours the groups by their name tag", all('.bookmark-group[data-group="%s"]' % g in C for g in ("entertainment", "online-shopping", "productivity")))
check("the css gives every bookmark the glass, glow and edge of a service card", all(x in C for x in (".bookmark > a {", ".bookmark > a::before", ".bookmark > a::after", "var(--accent)")))
check("the bookmark styles are inside the managed block", C.index(".bookmark > a {") > C.index(m.TABS_BEGIN) and C.index(".bookmark > a {") < C.index(m.TABS_END))
if shutil.which("node"):
    names = ["Entertainment", "Online Shopping", "Productivity", "Others", "Work & Play!", "  Spaces  ", "A--B", "Caf\u00e9 1"]
    code = J[J.index("function slug"):J.index("function label")] + "console.log(JSON.stringify(%s.map(slug)))" % json.dumps(names)
    got = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True).stdout or "[]")
    want = [re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-") for n in names]
    check("the script and the theme command make the same name tag for every name", got == want, "%s vs %s" % (got, want))
else:
    print("skip  (no node here) the script and the theme command make the same name tag")

print("OK" if not bad else "FAIL (%d)" % bad)
