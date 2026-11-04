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
check("exactly two tabs are used: HOME and LINKS", sorted(set(tabs)) == ["HOME", "LINKS"], str(set(tabs)))
check("every group in layout has an icon", len(re.findall(r"(?m)^    icon: mdi-[\w-]+$", S)) == len(tabs))
svc_groups = re.findall(r"(?m)^- ([^:\n]+):\s*$", rd("services.yaml"))
book_groups = re.findall(r"(?m)^- ([^:\n]+):\s*$", rd("bookmarks.yaml"))
lay = re.findall(r"(?m)^  ([^\s:][^:\n]*):\s*$", S[S.index("\nlayout:"):])
check("every shipped service group is on the HOME tab", all(g in lay for g in svc_groups), str(svc_groups))
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
base = "title: X\nlayout:\n  Network & DNS:\n    tab: HOME\n    icon: mdi-lan\n  Productivity:\n    tab: LINKS\n"
r, seen = m.layout_complete(base, ["Network & DNS", "My Apps"], ["Productivity", "Others"], [])
check("a new service group goes on HOME and a new bookmark group on LINKS",
      "  My Apps:\n    tab: HOME\n    icon: mdi-apps" in r and "  Others:\n    tab: LINKS\n    icon: mdi-dots-horizontal-circle" in r)
check("groups already in the layout are not added twice", r.count("Network & DNS:") == 1 and r.count("Productivity:") == 1)
check("every group is now remembered", seen == ["My Apps", "Network & DNS", "Others", "Productivity"], str(seen))
check("the file before the layout is kept", r.startswith("title: X\nlayout:"))
r2, seen2 = m.layout_complete(r, ["Network & DNS", "My Apps"], ["Productivity", "Others"], seen)
check("a second run changes nothing", r2 == r and seen2 == seen)
gone = r.replace("  Others:\n    tab: LINKS\n    icon: mdi-dots-horizontal-circle\n", "")
r3, _ = m.layout_complete(gone, ["Network & DNS", "My Apps"], ["Productivity", "Others"], seen)
check("a group that was taken out on purpose is not put back", "Others" not in r3)
r4, _ = m.layout_complete(r, ["Network & DNS", "My Apps", "Third"], ["Productivity", "Others"], seen)
check("a group that is new later is added once", r4.count("  Third:\n    tab: HOME") == 1)
check("no layout block: nothing is added, the groups are still remembered", m.layout_complete("title: X\n", ["A"], ["B"], [])[0] == "title: X\n" and m.layout_complete("title: X\n", ["A"], ["B"], [])[1] == ["A", "B"])
tail = base + "\n# comment\nhideVersion: true\n"
r5, _ = m.layout_complete(tail, ["Z"], [], [])
check("the group goes inside the layout block, before the keys that follow it", r5.index("  Z:") < r5.index("hideVersion") and r5.index("  Z:") > r5.index("Productivity"))
check("a name with a colon is quoted", m.yaml_key("A: b") == "'A: b'" and m.yaml_key("Plain & Name") == "Plain & Name")
check("group_names reads the top level groups", m.group_names("- Net & DNS:\n\n    - Card:\n        id: x\n- Files:\n  - A:\n") == ["Net & DNS", "Files"])
check("group_names skips comments", m.group_names("# - Not:\n- Real:  # note\n") == ["Real"])

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
