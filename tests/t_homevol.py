#!/usr/bin/env python3
"""Unit tests for homepage_volumes (the Homepage stack file mounts /mnt with rslave) and mount_types.
Run: python3 tests/t_homevol.py   (last line is OK or FAIL)"""
import importlib.machinery
import importlib.util
import os

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


HEAD = "services:\n  homepage:\n    image: x:v2.6.0\n    volumes:\n      - /home/u/homepage-config:/app/config\n      - /var/run/docker.sock:/var/run/docker.sock:ro\n      - /:/host:ro\n"
TAIL = "    ports:\n      - 3001:3000\n"
NEW = "      - /mnt:/mnt:ro,rslave"

old = HEAD + "      - /mnt/storage:/mnt/storage:ro\n" + TAIL
r = m.homepage_volumes(old)
check("old stack: the single storage line becomes /mnt", NEW in r and "/mnt/storage:/mnt/storage" not in r, r)
check("old stack: everything else is kept", "image: x:v2.6.0" in r and "/:/host:ro" in r and "3001:3000" in r)
check("running it again changes nothing", m.homepage_volumes(r) == r)

mid = HEAD + "      - /mnt/storage:/mnt/storage:ro,rslave\n      - /mnt/backup:/mnt/backup:ro,rslave\n" + TAIL
r = m.homepage_volumes(mid)
check("the two single lines become one /mnt line", r.count("/mnt:/mnt") == 1 and "/mnt/backup:/mnt/backup" not in r and "/mnt/storage:/mnt/storage" not in r, r)

none = HEAD + TAIL
r = m.homepage_volumes(none)
check("no pool line: /mnt is added after the last volume", r.index(NEW) > r.index("/:/host:ro") and r.index(NEW) < r.index("ports:"), r)

plain = HEAD + "      - /mnt:/mnt:ro\n" + TAIL
r = m.homepage_volumes(plain)
check("a plain /mnt line gets rslave", "      - /mnt:/mnt:ro,rslave" in r and r.count("/mnt:/mnt") == 1, r)

quoted = HEAD + '      - "/mnt/storage:/mnt/storage:ro"   # Main\n      - "/mnt/backup:/mnt/backup:ro"\n' + TAIL
r = m.homepage_volumes(quoted)
check("quoted lines with comments are found", r.count("/mnt:/mnt") == 1 and "/mnt/storage:" not in r, r)

other = HEAD.replace("  homepage:", "  homepage:\n    container_name: homepage") + "      - /mnt/other:/mnt/other:ro\n" + TAIL
r = m.homepage_volumes(other)
check("an unrelated /mnt/other line is not touched", "/mnt/other:/mnt/other:ro" in r, r)

done = HEAD + NEW + "\n" + TAIL
check("a stack that already has it is returned untouched", m.homepage_volumes(done) == done)
check("text without volumes is returned untouched", m.homepage_volumes("services: {}\n") == "services: {}\n")

repo = open(os.path.join(HERE, "..", "stacks", "homepage.yaml")).read()
check("the shipped stack file needs no change", m.homepage_volumes(repo) == repo)

info = ("30 1 8:1 / / rw - ext4 /dev/sda1 rw\n"
        "41 30 0:40 / /mnt/backup rw,nosuid - fuse.mergerfs /mnt/disks/BACKUP1:/mnt/disks/BACKUPBOOT rw\n"
        "42 30 0:41 / /mnt/with\\040space rw - ext4 /dev/sdb1 rw\n")
t = m.mount_types(info)
check("mount_types reads the last mount on a path", t.get("/mnt/backup") == "fuse.mergerfs" and t.get("/") == "ext4" and t.get("/mnt/with space") == "ext4", str(t))

shipped_css = open(os.path.join(HERE, "..", "homepage-config", "custom.css")).read()
check("the shipped custom.css carries the layout mark", m.CSS_LAYOUT_MARK in shipped_css)
check("the shipped custom.css sets each knob in one place", all(shipped_css.count(k + ":") == 1 for k in
      ("--d-pill-height", "--d-search-top", "--d-search-space", "--m-gap", "--m-search-top", "--m-search-bottom", "--m-search-pad")))
check("the shipped custom.css has one :root block and no pill-layout patch block", shipped_css.count(":root {") == 1 and "pill layout" not in shipped_css)
check("every card has its accent line", shipped_css.count("{ --accent:") == 9)

THEME = m.THEME_BEGIN + " written by: homelab theme. Remove it with: homelab theme reset */\n.service-card { background: rgba(10, 10, 10, 0.9) !important; }\n" + m.THEME_END + "\n"
live = (shipped_css.replace("How this file is organised", "xx")
        .replace("#immich-card      { --accent: 209, 18,  18;   }   /* Immich red */", "#immich-card      { --accent: 1, 2, 3;   }   /* Immich my own */")
        .replace("--m-gap: 12px;", "--m-gap: 20px;"))
live = live + "\n" + THEME
r = m.css_new_layout(live, shipped_css)
check("moving an old file: the layout mark is there", m.CSS_LAYOUT_MARK in r)
check("moving an old file: the changed accent colour is kept", "#immich-card      { --accent: 1, 2, 3;   }   /* Immich my own */" in r and "209, 18" not in r)
check("moving an old file: the other accent colours are the shipped ones", "#adguard-card     { --accent: 104, 186, 72;" in r)
check("moving an old file: a number changed in :root is kept", "--m-gap: 20px;" in r and "--m-gap: 12px;" not in r)
check("moving an old file: the homelab theme block is kept at the end", r.rstrip().endswith(m.THEME_END) and "rgba(10, 10, 10, 0.9)" in r)
check("moving an old file: nothing else was taken from the old file", r.replace("--m-gap: 20px;", "--m-gap: 12px;").replace("1, 2, 3;   }   /* Immich my own */", "209, 18,  18;   }   /* Immich red */").replace("\n" + THEME, "") .rstrip("\n") == shipped_css.rstrip("\n"))
check("a file in the new layout is returned as it is", m.css_new_layout(r, shipped_css) == r and m.css_new_layout(shipped_css, shipped_css) == shipped_css)

# an older file that was patched with a second :root block: the last value of each number is the one that counts
two = live.replace(":root {", ":root {\n  --d-search-top: 80px;", 1) + "\n:root {\n  --d-search-top: 100px;\n}\n"
check("two :root blocks: the last value wins", "--d-search-top: 100px;" in m.css_new_layout(two, shipped_css) and "--d-search-top: 80px;" not in m.css_new_layout(two, shipped_css))
check("no shipped file: the file is left alone", m.css_new_layout(live, "") == live)

print("OK" if bad == 0 else "FAIL")
