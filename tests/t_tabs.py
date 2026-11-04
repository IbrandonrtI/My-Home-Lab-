#!/usr/bin/env python3
"""Tests for the Homepage tabs: settings_with_layout (layout: block, hideVersion, language) and css_tabs_block (managed tab styles).
Run: python3 tests/t_tabs.py   (last line is OK or FAIL)"""
import importlib.machinery
import importlib.util
import os
import re

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

print("OK" if not bad else "FAIL (%d)" % bad)
