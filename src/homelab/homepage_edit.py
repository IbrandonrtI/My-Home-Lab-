import difflib
import os
import re
import shutil
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

HP = os.environ["HP_DIR"]
DOCS = os.environ.get("HP_DOCS_DIR", "")
BASE = os.environ.get("HOMELAB_BRANDFETCH_BASE", "https://cdn.brandfetch.io").rstrip("/")
SETTINGS = os.path.join(HP, "settings.yaml")
CSS = os.path.join(HP, "custom.css")
MARKS = os.path.join(HP, "bookmarks.yaml")
SERVICES_FILE = os.path.join(HP, "services.yaml")
IMAGES = os.path.join(HP, "images")
IDFILE = os.path.join(HP, ".brandfetch-client-id")
B1, B2 = "/* >>> homelab theme >>>", "/* <<< homelab theme <<< */"
COLORS = {
    "slate": (14, 19, 31), "black": (0, 0, 0), "white": (255, 255, 255), "gray": (58, 58, 58), "grey": (58, 58, 58),
    "blue": (30, 58, 138), "navy": (15, 23, 60), "green": (20, 83, 45), "teal": (19, 78, 74), "red": (127, 29, 29),
    "purple": (59, 7, 100), "pink": (131, 24, 67), "orange": (124, 45, 18), "yellow": (113, 63, 18), "brown": (68, 40, 22),
}
ACCENT = {
    "blue": (36, 140, 255), "green": (104, 186, 72), "red": (209, 18, 18), "purple": (147, 51, 234), "orange": (214, 90, 22),
    "pink": (236, 72, 153), "teal": (20, 184, 166), "yellow": (234, 179, 8), "cyan": (0, 197, 253), "white": (255, 255, 255),
    "gray": (148, 163, 184), "grey": (148, 163, 184), "black": (23, 21, 20),
}
DEFAULT_SERVICES = [("AdGuard Home", "adguard-card"), ("Tailscale", "tailscale-card"), ("Beszel", "beszel-card"), ("Netdata", "netdata-card"),
                    ("Speedtest Tracker", "speedtest-card"), ("Portainer", "portainer-card"), ("FileBrowser", "filebrowser-card"),
                    ("Immich", "immich-card"), ("Nextcloud", "nextcloud-card")]
DEFAULT_WORDS = ("default", "reset", "normal", "shipped")
CARD_TABLE = dict(COLORS)
CARD_TABLE.update(ACCENT)
BLURS = ("sm", "md", "lg", "xl", "2xl", "3xl")
NO_BLUR = ("none", "off")


class Fail(Exception):
    pass


def read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def write(p, text):
    if os.path.exists(p) and not os.path.exists(p + ".before-theme") and p != IDFILE:
        shutil.copy2(p, p + ".before-theme")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)


def need_dir():
    if not os.path.isdir(HP):
        raise Fail("The Homepage folder %s does not exist. Set HOMELAB_HOMEPAGE_DIR to the folder that holds settings.yaml." % HP)


def parse_color(s, table, what):
    s = s.strip().lower()
    if s in table:
        return table[s]
    m = re.fullmatch(r"#?([0-9a-f]{6})", s)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    raise Fail("Unknown %s color '%s'. Use a name (%s) or a hex code such as #1e3a8a." % (what, s, ", ".join(sorted(table))))


def bg_block(text):
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if re.match(r"^background:\s*(#.*)?$", l):
            j = i + 1
            while j < len(lines) and (lines[j].startswith(" ") or lines[j].startswith("\t") or lines[j].strip() == "" and j + 1 < len(lines) and lines[j + 1].startswith(" ")):
                j += 1
            return lines, i, j
    return lines, None, None


def bg_get(text):
    lines, i, j = bg_block(text)
    d = {}
    if i is None:
        return d
    for l in lines[i + 1:j]:
        m = re.match(r"^\s+([A-Za-z0-9_]+):\s*(.*?)\s*$", l)
        if m:
            d[m.group(1)] = m.group(2)
    return d


def bg_set(text, key, value):
    lines, i, j = bg_block(text)
    if i is None:
        if value is None:
            return text
        if not text.endswith("\n") and text:
            text += "\n"
        return text + "background:\n  %s: %s\n" % (key, value)
    for k in range(i + 1, j):
        if re.match(r"^\s+%s:" % re.escape(key), lines[k]):
            if value is None:
                del lines[k]
            else:
                lines[k] = "  %s: %s" % (key, value)
            return "\n".join(lines)
    if value is not None:
        lines.insert(j, "  %s: %s" % (key, value))
    return "\n".join(lines)


def quote(s):
    return "'" + s.replace("'", "''") + "'"


def number(s, what, lo=0, hi=100):
    try:
        n = int(s)
    except ValueError:
        raise Fail("%s must be a whole number from %d to %d." % (what, lo, hi)) from None
    if not lo <= n <= hi:
        raise Fail("%s must be from %d to %d." % (what, lo, hi))
    return n


def css_split(text):
    a = text.find(B1)
    if a < 0:
        return text, ""
    b = text.find(B2, a)
    if b < 0:
        return text, ""
    return text[:a].rstrip("\n") + "\n", text[a:b + len(B2)]


def fmt_alpha(a):
    return str(int(a)) if a in (0, 1) else ("%.2f" % a).rstrip("0").rstrip(".")


def css_state(block):
    st = {"cards": None, "links": {}}
    for m in re.finditer(r'(?m)^\.bookmark-group\[data-group="([a-z0-9-]+)"\]\s*\{\s*--accent:\s*(\d+),\s*(\d+),\s*(\d+);', block):
        st["links"][m.group(1)] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
    m = re.search(r"(?m)^\.service-card\s*\{\s*background:\s*rgba\((\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\)", block)
    if m:
        st["cards"] = (int(m.group(1)), int(m.group(2)), int(m.group(3)), float(m.group(4)))
    return st


def css_build(st):
    if not st["cards"] and not st.get("links"):
        return ""
    out = [B1 + " written by: homelab theme. Remove it with: homelab theme reset */"]
    if st["cards"]:
        c = st["cards"][:3] + (fmt_alpha(st["cards"][3]),)
        out.append(".service-card { background: rgba(%d, %d, %d, %s) !important; }" % c)
        out.append(".bookmark > a { background: rgba(%d, %d, %d, %s) !important; }" % c)
    for tag, rgb in sorted(st.get("links", {}).items()):
        out.append('.bookmark-group[data-group="%s"] { --accent: %d, %d, %d; }' % ((tag,) + tuple(rgb)))
    out.append(B2)
    return "\n".join(out) + "\n"


ACCENT_LINE = r"(?m)^(#%s-card\s*\{\s*--accent:\s*)(\d+),\s*(\d+),\s*(\d+);\s*\}(?:[ \t]*/\*.*?\*/)?"


def accent_get(text):
    return {m.group(1): (int(m.group(2)), int(m.group(3)), int(m.group(4)))
            for m in re.finditer(r"(?m)^#([\w-]+)-card\s*\{\s*--accent:\s*(\d+),\s*(\d+),\s*(\d+);", text)}


def accent_set(text, key, rgb, label):
    nums = "%-5s%-5s%-6s}" % ("%d," % rgb[0], "%d," % rgb[1], "%d;" % rgb[2])
    return re.subn(ACCENT_LINE % re.escape(key), lambda m: m.group(1) + nums + "   /* %s */" % label, text, count=1)


def shipped_copy(name, current):
    shipped = read(os.path.join(DOCS, "homepage-config", name)) if DOCS else ""
    return shipped or read(current + ".before-theme")


def shipped_css():
    return shipped_copy("custom.css", CSS)


def split_head():
    return css_split(read(CSS))[0]


def css_save(st, change=None):
    head = split_head()
    if change:
        head = change(head)
    block = css_build(st)
    write(CSS, head + ("\n" + block if block else ""))


def cur_css():
    return css_state(css_split(read(CSS))[1])


REFRESH = "Done. Refresh the Homepage page in the browser (Ctrl+Shift+R) to see it."


def theme_show():
    """Print the current theme settings: background, colors and cards."""
    need_dir()
    bg = bg_get(read(SETTINGS))
    st = cur_css()
    names = {i[:-5]: n for n, i in known_services() if i}
    print("  Background    %s" % bg.get("image", "(none)").strip("'"))
    print("  Dimming       brightness %s, saturation %s, opacity %s, blur %s" % (bg.get("brightness", "default"), bg.get("saturate", "default"), bg.get("opacity", "default"), bg.get("blur", "none")))
    if st["cards"]:
        r, g, b, a = st["cards"]
        print("  All cards     rgb(%d, %d, %d), %d%% solid" % (r, g, b, round(a * 100)))
    else:
        print("  All cards     the shipped look (dark slate, 58% solid)")
    now, was = accent_get(split_head()), accent_get(shipped_css())
    changed = ["%s rgb(%d, %d, %d)" % ((names.get(k, k),) + v) for k, v in sorted(now.items()) if k in was and was[k] != v]
    print("  Card colors  " + (", ".join(changed) if changed else "the default colors"))
    mine = {tag: "rgb(%d, %d, %d)" % rgb for tag, rgb in st["links"].items()}
    names = {group_tag(g[0]): g[0] for g in marks_groups(read(MARKS))[0]}
    print("  Link colors  " + (", ".join("%s %s" % (names.get(t, t), c) for t, c in sorted(mine.items())) if mine else "the default colors"))
    print()
    print("  Change it with:")
    print("    homelab theme background [BLUR] URL-or-FILE   a picture from the web, or one on this machine, with an optional BLUR")
    print("    homelab theme brightness 0-100           how dark the picture is (shipped: 42)")
    print("    homelab theme blur none|sm|md|lg|xl|2xl|3xl   only the blur, low to high (shipped: md)")
    print("    homelab theme saturate 0-100 | opacity 0-100")
    print("    homelab theme cards COLOR NUMBER         all cards: the color and opacity (NUMBER 0-100)")
    print("    homelab theme cards SERVICE COLOR        ONE card, for example:  homelab theme cards AdGuard Home blue")
    print("    homelab theme cards SERVICE default      that card goes back to its default color")
    print("    homelab theme links GROUP COLOR          the color of one bookmark group on the Links tab, e.g.  homelab theme links Productivity green")
    print("    homelab theme links GROUP default        that group goes back to its default color")
    print("    homelab theme reset                      the shipped look again, everywhere")
    print("  Colour names: " + ", ".join(sorted(CARD_TABLE)) + "  (or a hex code such as #1e3a8a)")
    print("  Services: " + ", ".join(n for n, i in known_services() if i))
    print("  Link groups: " + ", ".join(g[0] for g in marks_groups(read(MARKS))[0]))


def images_mounted():
    try:
        r = subprocess.run(["docker", "inspect", "homepage", "--format", "{{range .Mounts}}{{.Destination}} {{end}}"],
                           capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return "/app/public/images" in r.stdout.split()


def theme_background(src, blur=None):
    """Set the Homepage background from a web address or a file, with an optional blur."""
    need_dir()
    if blur is not None:
        blur = (blur_value(blur),)
    if re.match(r"^https?://", src):
        value = quote(src)
    else:
        p = os.path.expanduser(src)
        if not os.path.isfile(p):
            raise Fail("'%s' is neither a web address (https://...) nor a file on this machine." % src)
        ext = os.path.splitext(p)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg"):
            raise Fail("Use a picture file (.jpg, .png, .webp, .gif, .avif or .svg).")
        os.makedirs(IMAGES, exist_ok=True)
        name = "background" + ext
        shutil.copyfile(p, os.path.join(IMAGES, name))
        value = "/images/" + name
    text = bg_set(read(SETTINGS), "image", value)
    if blur is not None:
        text = bg_set(text, "blur", blur[0])
    write(SETTINGS, text)
    print("Background set to %s%s. %s" % (value.strip("'") if value.startswith("/") else src,
                                         "" if blur is None else (", blur %s" % blur[0] if blur[0] else ", no blur"), REFRESH))
    if value.startswith("/images/"):
        mounted = images_mounted()
        if mounted is False:
            print("But Homepage cannot see that folder yet. In Portainer, add this line under 'volumes:' of the homepage stack, then update the stack:")
            print("  %s:/app/public/images" % IMAGES)
        else:
            print("Homepage only notices a new local picture after a restart:  docker restart homepage")


def is_blur(word):
    return word.lower() in BLURS + NO_BLUR


def blur_value(arg):
    a = arg.lower()
    if a in NO_BLUR:
        return None
    if a in BLURS:
        return a
    raise Fail("blur must be none, " + ", ".join(BLURS) + " (low to high; the shipped look is md).")


def theme_key(key, arg):
    need_dir()
    if key == "blur":
        write(SETTINGS, bg_set(read(SETTINGS), "blur", blur_value(arg)))
    else:
        write(SETTINGS, bg_set(read(SETTINGS), key, str(number(arg, key))))
    print("%s changed. %s" % (key.capitalize(), REFRESH))


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def known_services():
    out, name = [], None
    for line in read(SERVICES_FILE).split("\n"):
        m = re.match(r"^    - (.+?):\s*$", line)
        if m:
            if name:
                out.append((name, None))
            name = m.group(1)
            continue
        m = re.match(r"^ {8}id:\s*['\"]?([A-Za-z0-9_-]+)['\"]?\s*$", line)
        if m and name:
            out.append((name, m.group(1) if m.group(1).endswith("-card") else None))
            name = None
    if name:
        out.append((name, None))
    return out or list(DEFAULT_SERVICES)


def find_service(words, quiet=False):
    """Return the (name, id) of the card the words point at. Case and spaces are ignored and a small typo is forgiven."""
    sv = known_services()
    usable = [(n, i) for n, i in sv if i]
    t = norm(words)
    if not t:
        raise Fail("Which service? One of: %s." % ", ".join(n for n, _ in usable))
    keys = {}
    for n, i in usable:
        keys.setdefault(norm(n), (n, i))
        keys.setdefault(norm(i[:-5]), (n, i))
    if t in keys:
        return keys[t]
    hits = sorted({keys[k] for k in keys if k.startswith(t)}) or sorted({keys[k] for k in keys if len(t) >= 3 and t in k})
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise Fail("'%s' could mean %s. Type a little more of the name." % (words, " or ".join(n for n, _ in hits)))
    close = difflib.get_close_matches(t, list(keys), n=1, cutoff=0.75)
    if close:
        return keys[close[0]]
    for n, i in sv:
        if not i and norm(n) == t:
            raise Fail("'%s' has no 'id:' line in services.yaml, so its card cannot be colored. Add this line under it:  id: %s-card" % (n, slug(n)))
    if quiet:
        return None
    raise Fail("Unknown service '%s'. The services are: %s." % (words, ", ".join(n for n, _ in usable)))


def theme_cards(color, opacity):
    need_dir()
    r, g, b = parse_color(color, COLORS, "card")
    st = cur_css()
    a = st["cards"][3] if st["cards"] else 0.58
    if opacity is not None:
        a = number(opacity, "How solid the cards are", 0, 100) / 100.0
    st["cards"] = (r, g, b, a)
    css_save(st)
    print("All cards set to rgb(%d, %d, %d), %d%% solid. %s" % (r, g, b, round(a * 100), REFRESH))


def theme_service_color(words, color):
    need_dir()
    name, cid = find_service(words)
    key = cid[:-5]
    st = cur_css()
    if color.lower() in DEFAULT_WORDS:
        line = next((x for x in shipped_css().split("\n") if re.match(r"#%s-card\s*\{\s*--accent:" % re.escape(key), x)), None)
        if not line:
            raise Fail("The shipped custom.css has no color line for %s." % name)
        rgb = accent_get(line).get(key)
        text, n = re.subn(r"(?m)^#%s-card\s*\{\s*--accent:.*$" % re.escape(key), lambda _m: line, split_head(), count=1)
    else:
        rgb, label = parse_color(color, CARD_TABLE, "card"), "%s %s" % (name, color.lower())
        text, n = accent_set(split_head(), key, rgb, label)
    if not n:
        raise Fail("custom.css has no color line for the %s card. The lines are in the list that starts with '/* accent colors (R, G, B) */'; "
                   "the glow rules there only cover the cards that came with the lab." % name)
    css_save(st, lambda _head: text)
    print("The %s card is now %s: --accent: %d, %d, %d in custom.css. %s" % (name, color if color.lower() not in DEFAULT_WORDS else "its default color", rgb[0], rgb[1], rgb[2], REFRESH))


def theme_cards_cmd(words):
    """homelab theme cards COLOR [NUMBER] or homelab theme cards SERVICE COLOR: set card accent colors. The service name may contain spaces and needs no quotes."""
    words = list(words)
    opacity = None
    if len(words) >= 2 and re.fullmatch(r"\d{1,3}%?", words[-1]):
        opacity = words.pop().rstrip("%")
    color = words.pop()
    if not words or norm(" ".join(words)) == "all":
        if not words and color.lower() not in DEFAULT_WORDS:
            try:
                parse_color(color, COLORS, "card")
            except Fail:
                if find_service(color, quiet=True):
                    raise Fail("Which color? For example:  homelab theme cards %s blue" % color) from None
                raise
        if color.lower() in DEFAULT_WORDS:
            raise Fail("To put every card back to the shipped look, use:  homelab theme reset")
        theme_cards(color, opacity)
    else:
        if opacity is not None:
            raise Fail("A number (how solid) only goes with the all-cards form:  homelab theme cards COLOR NUMBER")
        theme_service_color(" ".join(words), color)


def theme_accent_cmd(words):
    name = " ".join(words[:-1])
    if norm(name) != "all":
        theme_service_color(name, words[-1])
        return
    have = accent_get(split_head())
    for service, cid in known_services():
        if cid and cid[:-5] in have:
            theme_service_color(service, words[-1])


def group_tag(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def find_link_group(words):
    """Return the name of the bookmark group the words point at. Case and spaces are ignored and a small typo is forgiven."""
    names = [g[0] for g in marks_groups(read(MARKS))[0]]
    t = norm(words)
    if not names:
        raise Fail("There are no bookmark groups yet. Add a bookmark first:  homelab bookmark add NAME URL CATEGORY")
    if not t:
        raise Fail("Which group? One of: %s." % ", ".join(names))
    keys = {}
    for n in names:
        keys.setdefault(norm(n), n)
    if t in keys:
        return keys[t]
    hits = sorted({keys[k] for k in keys if k.startswith(t)}) or sorted({keys[k] for k in keys if len(t) >= 3 and t in k})
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise Fail("'%s' could mean %s. Type a little more of the name." % (words, " or ".join(hits)))
    close = difflib.get_close_matches(t, list(keys), n=1, cutoff=0.75)
    if close:
        return keys[close[0]]
    raise Fail("Unknown bookmark group '%s'. The groups are: %s." % (words, ", ".join(names)))


def theme_links_cmd(words):
    need_dir()
    words = list(words)
    if len(words) < 2:
        raise Fail("Which group and which color? For example:  homelab theme links Productivity green   (groups: %s)"
                   % ", ".join(g[0] for g in marks_groups(read(MARKS))[0]))
    color = words.pop()
    group = find_link_group(" ".join(words))
    tag = group_tag(group)
    st = cur_css()
    if color.lower() in DEFAULT_WORDS:
        st["links"].pop(tag, None)
        css_save(st)
        print("The %s group is back to its default color. %s" % (group, REFRESH))
        return
    rgb = parse_color(color, CARD_TABLE, "link")
    st["links"][tag] = rgb
    css_save(st)
    print("The %s group is now %s: --accent: %d, %d, %d in the marked block at the end of custom.css. %s" % (group, color, rgb[0], rgb[1], rgb[2], REFRESH))


def theme_reset():
    need_dir()
    def restore(head):
        a = head.find("/* >>> homelab look >>>")
        z = head.find("/* <<< homelab look <<< */", a) if a >= 0 else -1
        if a >= 0 and z >= 0:
            head = head[:a].rstrip("\n") + "\n" + head[z + len("/* <<< homelab look <<< */"):].lstrip("\n")
        for line in shipped_css().split("\n"):
            m = re.match(r"#([\w-]+)-card\s*\{\s*--accent:", line)
            if m:
                head = re.sub(r"(?m)^#%s-card\s*\{\s*--accent:.*$" % re.escape(m.group(1)), lambda _m, keep=line: keep, head, count=1)
        return head
    css_save({"cards": None, "links": {}}, restore)
    sb = bg_get(shipped_copy("settings.yaml", SETTINGS))
    text = read(SETTINGS)
    for k in ("image", "blur", "saturate", "brightness", "opacity"):
        text = bg_set(text, k, sb.get(k))
    write(SETTINGS, text)
    print("The shipped look is back. %s" % REFRESH)


def marks_groups(text):
    """Return [(group, [(name, start, end)])], where start and end are line numbers in text.split('\n') (end excluded)."""
    lines = text.split("\n")
    groups, cur, ent = [], None, None
    for i, l in enumerate(lines):
        m = re.match(r"^- (.+?):\s*$", l)
        if m:
            if ent:
                cur[1].append((ent[0], ent[1], i))
                ent = None
            if cur:
                cur[2] = i
            cur = [m.group(1), [], len(lines)]
            groups.append(cur)
            continue
        m = re.match(r"^    - (.+?):\s*$", l)
        if m and cur is not None:
            if ent:
                cur[1].append((ent[0], ent[1], i))
            ent = (m.group(1), i)
    if ent and cur:
        cur[1].append((ent[0], ent[1], len(lines)))
    return groups, lines


def entry_field(lines, start, end, field):
    for l in lines[start:end]:
        m = re.match(r"^\s+(?:- )?%s:\s*(.*?)\s*$" % field, l)
        if m:
            return m.group(1)
    return ""


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "site"


def get_id():
    return os.environ.get("HOMELAB_BRANDFETCH_ID", "").strip() or read(IDFILE).strip()


GENERIC_ICON = "mdi-web"


def image_kind(data):
    head = data[:300].lstrip().lower()
    if len(data) > 100 and (head.startswith(b"<svg") or head.startswith(b"<?xml")) and b"<svg" in data[:2000].lower():
        return "svg"
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) > 100:
        return "png"
    if data.startswith(b"\xff\xd8\xff") and len(data) > 100:
        return "jpeg"
    return None


def brandfetch_icon(domain):
    cid = get_id()
    if not cid:
        return None, "No Brandfetch client ID is saved, so it got the plain globe icon. Save yours once with:  homelab bookmark brandfetch YOUR-CLIENT-ID"
    last = ""
    for ext in ("svg", "png", "jpeg"):
        for kind in ("symbol", "logo", "icon"):
            url = "%s/%s/theme/dark/%s.%s?c=%s" % (BASE, domain, kind, ext, cid)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "homelab-bookmark/1"})
                with urllib.request.urlopen(req, timeout=12) as r:
                    data = r.read(3000000)
            except (urllib.error.URLError, OSError, ValueError) as e:
                last = str(e)
                continue
            if image_kind(data) == ext:
                return url, "Logo: Brandfetch (%s, %s)." % (kind, ext.upper())
    return None, "Brandfetch has no SVG, PNG or JPEG for %s (%s), so it got the plain globe icon." % (domain, last or "not found")


def looks_like_icon(t):
    return bool(t.lower() == "generic" or re.match(r"https?://", t) or t.startswith("/")
                or re.fullmatch(r"(si|mdi|sh)-[\w-]+", t) or re.search(r"\.(svg|png|jpe?g|webp|ico|gif|avif)$", t, re.I))


def make_abbr(name):
    words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", name)
    if len(words) > 1:
        return "".join(w[0] for w in words)[:4].upper()
    return (words[0] if words else "?")[:4].upper()


def tty_path():
    return os.environ.get("HOMELAB_TTY", "") or ("/dev/tty" if sys.stdout.isatty() else "")


_TTY = []


def ask(question):
    path = tty_path()
    if not path:
        return None
    try:
        if not _TTY:
            _TTY.append(open(path, encoding="utf-8"))
        sys.stdout.write(question)
        sys.stdout.flush()
        line = _TTY[0].readline()
    except OSError:
        return None
    return line.strip() if line else None


def find_group(groups, wanted):
    t = norm(wanted)
    for g in groups:
        if norm(g[0]) == t:
            return g
    close = difflib.get_close_matches(t, [norm(g[0]) for g in groups], n=1, cutoff=0.8)
    return next((g for g in groups if norm(g[0]) == close[0]), None) if close else None


def pick_group(groups, what, allow_new):
    if not tty_path():
        return None
    print(what)
    for i, g in enumerate(groups, 1):
        print("  %d) %s" % (i, g[0]))
    if allow_new:
        print("  %d) A new category (you type its name)" % (len(groups) + 1))
    ans = ask("Number%s: " % (" (Enter = Others)" if allow_new else ""))
    if ans is None:
        return None
    if ans == "" and allow_new:
        return "Others"
    if ans.isdigit() and 1 <= int(ans) <= len(groups):
        return groups[int(ans) - 1]
    if allow_new and ans.isdigit() and int(ans) == len(groups) + 1:
        new = ask("Name of the new category: ")
        return new if new else None
    raise Fail("'%s' is not one of the numbers above. Nothing was changed." % ans)


def place(lines, group, entry, order):
    groups, _ = marks_groups("\n".join(lines))
    target = find_group(groups, group)
    if not target:
        body = list(lines)
        while body and body[-1].strip() == "":
            body.pop()
        return body + ([""] if body else []) + ["- %s:" % group] + entry, False
    if order and order <= len(target[1]):
        at = target[1][order - 1][1]
        return lines[:at] + entry + [""] + lines[at:], True
    at = target[2]
    while at > 0 and lines[at - 1].strip() == "":
        at -= 1
    return lines[:at] + [""] + entry + lines[at:], True


def split_extras(extra, what):
    group = icon = order = None
    words = []
    for t in extra:
        if re.fullmatch(r"\d+", t):
            if order is not None:
                raise Fail("Two numbers were given. One number (the place in the category) is enough.")
            order = int(t)
            if order < 1:
                raise Fail("The place number starts at 1 (1 = first in the category).")
        elif what == "add" and looks_like_icon(t):
            if icon is not None:
                raise Fail("Two icons were given. One is enough.")
            icon = t
        else:
            words.append(t)
    group = " ".join(words) if words else None
    return group, icon, order


def layout_add_group(group, others):
    """Put a new bookmark category on the same tab as the other bookmark categories (settings.yaml layout:) so it is not shown on every tab. Does nothing without a layout block or a known tab."""
    try:
        text = read(SETTINGS)
    except OSError:
        return
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if re.match(r"^layout:\s*(#.*)?$", l)), None)
    if start is None:
        return
    end = start + 1
    while end < len(lines) and (lines[end].strip() == "" or lines[end][0] in " \t#"):
        end += 1
    while end > start + 1 and lines[end - 1].strip() == "":
        end -= 1
    tab, cur = None, None
    for l in lines[start + 1:end]:
        m = re.match(r"^  ('?)([^\s#'][^:]*?)\1:\s*$", l)
        if m:
            cur = m.group(2).strip()
            if cur.lower() == group.lower():
                return
            continue
        t = re.match(r"^    tab:\s*(\S+)", l)
        if t and cur in others and tab is None:
            tab = t.group(1)
    if not tab:
        return
    key = "'%s'" % group.replace("'", "''") if re.search(r"[:#\[\]{},*!|>'\"%@`]|^[&?-]|^\s|\s$", group) else group
    icon = "mdi-dots-horizontal-circle" if group.lower() == "others" else "mdi-bookmark-multiple"
    lines[end:end] = ["  %s:" % key, "    tab: %s" % tab, "    icon: %s" % icon]
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    shutil.copymode(SETTINGS, tmp)
    os.replace(tmp, SETTINGS)


def marks_add(name, url, extra):
    """`homelab bookmarks add NAME URL [options]`: add a bookmark, creating its group if needed."""
    need_dir()
    group, icon, order = split_extras(extra, "add")
    if not re.match(r"^https?://", url):
        url = "https://" + url
    parts = urlparse(url)
    if not parts.netloc or " " in url:
        raise Fail("'%s' is not a web address." % url)
    if not parts.path and not parts.query and not parts.fragment:
        url += "/"
    domain = re.sub(r"^www\.", "", parts.netloc.lower().split(":")[0])
    text = read(MARKS)
    groups, lines = marks_groups(text)
    if group is None:
        choice = pick_group(groups, "Which category should '%s' go in?" % name, True) if groups else "Others"
        group = choice if choice is not None else "Others"
        if not isinstance(group, str):
            group = group[0]
    target = find_group(groups, group)
    if target:
        group = target[0]
    for g in groups:
        for n, _s, _e in g[1]:
            if n.lower() == name.lower() and g is target:
                raise Fail("A bookmark named '%s' is already in '%s'. Remove it first:  homelab bookmark remove \"%s\" \"%s\"" % (n, g[0], n, g[0]))
    if icon is None:
        icon, msg = brandfetch_icon(domain)
    elif icon.lower() == "generic":
        icon, msg = None, "Icon: the plain globe."
    else:
        msg = "Icon: %s." % icon
    entry = ["    - %s:" % name, "        - abbr: %s" % make_abbr(name), "          href: %s" % url, "          icon: %s" % (icon or GENERIC_ICON)]
    new, existed = place(lines, group, entry, order)
    write(MARKS, "\n".join(new).rstrip("\n") + "\n")
    where, _ = marks_groups("\n".join(new))
    spot = next((i + 1 for g in where if g[0] == group for i, (n, _s, _e) in enumerate(g[1]) if n == name), 1)
    print("Added '%s' to '%s' as number %d (%s). %s" % (name, group, spot, url, msg))
    if not existed:
        layout_add_group(group, [g[0] for g in groups])
    if not existed and groups:
        print("'%s' is a new category (it did not exist yet). The ones before: %s." % (group, ", ".join(g[0] for g in groups)))
    print("Refresh the Homepage page in the browser to see it.")


def marks_list():
    need_dir()
    groups, lines = marks_groups(read(MARKS))
    if not groups:
        print("There are no bookmarks yet. Add one with:  homelab bookmark add NAME URL [CATEGORY]")
        return
    for g in groups:
        print("  %s" % g[0])
        for i, (n, s, e) in enumerate(g[1], 1):
            print("    %2d. %-20s %s" % (i, n, entry_field(lines, s, e, "href")))


def marks_pick(name, group, verb):
    text = read(MARKS)
    groups, lines = marks_groups(text)
    if group is not None:
        want = find_group(groups, group)
        if not want:
            raise Fail("There is no category '%s'. The categories are: %s." % (group, ", ".join(g[0] for g in groups) or "(none)"))
        groups = [want]
    hits = [(g, n, s, e) for g in groups for n, s, e in g[1] if n.lower() == name.lower()]
    if not hits:
        where = " in '%s'" % groups[0][0] if group is not None else ""
        raise Fail("No bookmark named '%s'%s. See them with:  homelab bookmark list" % (name, where))
    if len(hits) > 1:
        cats = [h[0] for h in hits]
        choice = pick_group(cats, "'%s' is in %d categories. Which one to %s?" % (name, len(cats), verb), False)
        if choice is None:
            raise Fail("'%s' is in %s. Say which one:  homelab bookmark %s \"%s\" \"CATEGORY\"" % (name, " and ".join("'%s'" % c[0] for c in cats), verb, name))
        hits = [h for h in hits if h[0] is choice]
    return hits[0], text, lines


def clean_marks(lines):
    out = "\n".join(lines)
    out = re.sub(r"([^\n])\n(- )", r"\1\n\n\2", out)
    out = re.sub(r"\n{3,}", "\n\n", out).rstrip("\n") + "\n"
    g2, l2 = marks_groups(out)
    for gg in g2:
        if not gg[1]:
            del l2[l2.index("- %s:" % gg[0])]
            out = re.sub(r"\n{3,}", "\n\n", "\n".join(l2)).strip("\n") + "\n"
            break
    return out if out.strip() else ""


def marks_remove(name, group):
    need_dir()
    (g, n, s, e), text, lines = marks_pick(name, group, "remove")
    icon = entry_field(lines, s, e, "icon")
    out = clean_marks(lines[:s] + lines[e:])
    write(MARKS, out)
    if icon.startswith("/images/") and icon not in out:
        p = os.path.join(IMAGES, os.path.basename(icon))
        if os.path.isfile(p):
            os.remove(p)
    print("Removed '%s' from '%s'. Refresh the Homepage page in the browser." % (n, g[0]))


def marks_move(name, to, extra):
    need_dir()
    group, _, order = split_extras(extra, "move")
    (g, n, s, e), text, lines = marks_pick(name, group, "move")
    if norm(to) == norm(g[0]) and order is None:
        raise Fail("'%s' is already in '%s'. To change its place there, add a number:  homelab bookmark move \"%s\" \"%s\" 1" % (n, g[0], n, g[0]))
    entry = lines[s:e]
    while entry and entry[-1].strip() == "":
        entry.pop()
    rest = lines[:s] + lines[e:]
    groups2, _ = marks_groups("\n".join(rest))
    dest = find_group(groups2, to)
    new, existed = place(rest, dest[0] if dest else to, entry, order)
    write(MARKS, clean_marks(new))
    out_name = dest[0] if dest else to
    print("Moved '%s' from '%s' to '%s'%s%s. Refresh the Homepage page in the browser." % (n, g[0], out_name, "" if existed else " (a new category)", " as number %d" % order if order else ""))


def marks_id(cid):
    need_dir()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", cid):
        raise Fail("A Brandfetch client ID is letters, numbers, - and _ (8 to 64 characters). Copy it from your Brandfetch developer page.")
    with open(IDFILE, "w") as f:
        f.write(cid + "\n")
    os.chmod(IDFILE, 0o600)
    print("Brandfetch client ID saved in %s. New bookmarks now get their logo from Brandfetch." % IDFILE)


USAGE_M = """Bookmarks on the Homepage dashboard (a NAME with spaces goes in quotes; a CATEGORY does not need them):
  homelab bookmark list                           every category, with the number of each bookmark
  homelab bookmark add NAME URL [CATEGORY] [ICON LINK] [NUMBER]
        CATEGORY   where it goes; leave it out to pick from a list (a new name makes a new category)
        ICON LINK  a web address of a picture, a Homepage icon name (si-youtube, mdi-web), or the word generic.
                   Left out: the logo comes from Brandfetch, or the plain globe if you have no Brandfetch ID
        NUMBER     its place in the category (1 = first). Left out: last
  homelab bookmark remove NAME [CATEGORY]         take one away. If the name is in more than one category, give it
  homelab bookmark move NAME CATEGORY [NUMBER]    put it in another category (the same one, plus a NUMBER: change its place)
                                                  a category with spaces needs no quotes: Online Shopping
  homelab bookmark brandfetch CLIENT-ID           save your Brandfetch client ID once, so logos can be found
For example:  homelab bookmark add YouTube youtube.com Entertainment
              homelab bookmark add Netflix netflix.com Entertainment si-netflix 2"""


SIMPLE_BEGIN = "/* >>> homelab simple >>>"
SIMPLE_END = "/* <<< homelab simple <<< */"
SIMPLE_BLOCK = (SIMPLE_BEGIN + " written by: homelab simple on. Remove it with: homelab simple off */\n"
                ".service-description { display: none !important; }\n" + SIMPLE_END + "\n")


def simple_css(css, on):
    css = re.sub(r"\n*" + re.escape(SIMPLE_BEGIN) + r".*?" + re.escape(SIMPLE_END) + r"\n?", "\n", css, flags=re.S)
    css = css.rstrip("\n") + "\n" if css.strip() else ""
    return css + ("\n" if css else "") + SIMPLE_BLOCK if on else css


def simple_cmd(args):
    need_dir()
    css = read(CSS)
    now = SIMPLE_BEGIN in css
    word = args[0].lower() if args else "status"
    if len(args) > 1 or word not in ("on", "off", "status"):
        raise Fail("Usage: homelab simple on | off | status")
    if word == "status":
        print("Less busy cards are %s. %s" % ("ON (the small text under card names is hidden)" if now else "OFF (the shipped look)",
                                              "Turn them off with:  homelab simple off" if now else "Turn them on with:  homelab simple on"))
        return
    if (word == "on") == now:
        print("Less busy cards are already %s." % word)
        return
    write(CSS, simple_css(css, word == "on"))
    print("Less busy cards are now %s. %s" % (word.upper(), REFRESH))


def main(a):
    """Read the command line and run the requested command."""
    try:
        if not a:
            raise Fail("nothing to do")
        if a[0] == "simple":
            simple_cmd(a[1:])
        elif a[0] == "theme":
            a = a[1:]
            c = a[0] if a else ""
            if c == "":
                theme_show()
            elif c in ("background", "bg") and len(a) == 2:
                theme_background(a[1])
            elif c in ("background", "bg") and len(a) == 3:
                if not is_blur(a[1]):
                    raise Fail("'%s' is not a blur. Use:  homelab theme background BLUR URL-or-FILE   (BLUR: none, %s)" % (a[1], ", ".join(BLURS)))
                theme_background(a[2], a[1])
            elif c in ("brightness", "blur", "saturate", "opacity") and len(a) == 2:
                theme_key(c, a[1])
            elif c == "cards" and len(a) >= 2:
                theme_cards_cmd(a[1:])
            elif c == "accent" and len(a) >= 3:
                theme_accent_cmd(a[1:])
            elif c == "links":
                theme_links_cmd(a[1:])
            elif c == "reset" and len(a) == 1:
                theme_reset()
            else:
                theme_show()
                return 2
        else:
            a = a[1:]
            c = a[0] if a else ""
            if c == "add" and 3 <= len(a) <= 9:
                marks_add(a[1], a[2], a[3:])
            elif c == "add" and len(a) > 9:
                raise Fail("Too many words. If the name has spaces, put it in quotes:  homelab bookmark add \"My Bank\" mybank.com Productivity")
            elif c == "list" and len(a) == 1:
                marks_list()
            elif c in ("remove", "rm", "delete") and 2 <= len(a) <= 5:
                marks_remove(a[1], " ".join(a[2:]) if len(a) > 2 else None)
            elif c == "move" and 3 <= len(a) <= 7:
                to_words = a[2:]
                if len(to_words) > 1 and re.fullmatch(r"\d+", to_words[-1]):
                    marks_move(a[1], " ".join(to_words[:-1]), [to_words[-1]])
                else:
                    marks_move(a[1], " ".join(to_words), [])
            elif c == "brandfetch" and len(a) == 2:
                marks_id(a[1])
            else:
                print(USAGE_M)
                return 2 if c else 0
    except Fail as e:
        print("homelab: %s" % e, file=sys.stderr)
        return 1
    return 0


signal.signal(signal.SIGPIPE, signal.SIG_DFL)
sys.exit(main(sys.argv[1:]))
