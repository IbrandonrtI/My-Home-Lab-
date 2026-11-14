def card_range(lines, card_id):
    """Start and end line of the card with this id in services.yaml, or None."""
    idx = next((i for i, l in enumerate(lines) if re.match(r"^\s*id:\s*%s\s*$" % re.escape(card_id), l)), None)
    if idx is None:
        return None
    ind = len(lines[idx]) - len(lines[idx].lstrip())
    start = idx
    while start > 0 and not (re.match(r"^\s*- .+:\s*$", lines[start]) and len(lines[start]) - len(lines[start].lstrip()) < ind):
        start -= 1
    end = idx + 1
    while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) >= ind):
        end += 1
    while end > idx + 1 and not lines[end - 1].strip():
        end -= 1
    return start, end


def card_widget_type(text, card_id):
    lines = text.split("\n")
    r = card_range(lines, card_id)
    if not r:
        return None
    block = "\n".join(lines[r[0]:r[1]])
    m = re.search(r"(?m)^\s+widget:\s*\n\s+type:\s*(\S+)", block)
    return m.group(1) if m else ""


def card_to_top(text, card_id):
    lines = text.split("\n")
    r = card_range(lines, card_id)
    if not r:
        return text
    head = next((i for i in range(r[0], -1, -1) if re.match(r"^- .+:\s*$", lines[i])), None)
    if head is None:
        return text
    first = next((i for i in range(head + 1, len(lines)) if re.match(r"^\s+- .+:\s*$", lines[i])), None)
    if first is None or first >= r[0]:
        return text
    block = lines[r[0]:r[1]]
    del lines[r[0]:r[1]]
    while r[0] < len(lines) and r[0] > 0 and not lines[r[0]].strip() and not lines[r[0] - 1].strip():
        del lines[r[0]]
    lines[first:first] = block + [""]
    return "\n".join(lines)


def card_retitled(text, card_id, old_title, new_title, old_desc, new_desc):
    lines = text.split("\n")
    r = card_range(lines, card_id)
    if not r:
        return text
    m = re.match(r"^(\s+- )(.+?):\s*$", lines[r[0]])
    if m and m.group(2) == old_title:
        lines[r[0]] = "%s%s:" % (m.group(1), new_title)
    for i in range(*r):
        m = re.match(r"^(\s+description:\s*)(.*?)\s*$", lines[i])
        if m and m.group(2).strip("\"'") == old_desc:
            lines[i] = m.group(1) + new_desc
    return "\n".join(lines)


NAVIDROME_TITLE, NAVIDROME_DESC = "Navidrome", "Music Streaming Server"


def navidrome_card_named(text):
    text = card_retitled(text, "navidrome-card", "navidrome", NAVIDROME_TITLE, "Music streaming server", NAVIDROME_DESC)
    return card_retitled(text, "navidrome-card", NAVIDROME_TITLE, NAVIDROME_TITLE, "Spotify Music Player", NAVIDROME_DESC)


CARD_WORDING = [("filebrowser-card", "FileBrowser", "View and edit the backups", "Browse and Edit Files")]


def cards_worded(text):
    for cid, title, old, new in CARD_WORDING:
        text = card_retitled(text, cid, title, title, old, new)
    return text


PLAYER_ID = "navidrome-player"


def navidrome_iframe_widget(lan):
    return ["type: iframe", "name: navidrome-player", "src: http://%s:%d" % (lan, PORTS["navidrome"]),
            "classes: h-96 sm:h-96 md:h-96 lg:h-96 xl:h-96 2xl:h-96", "allowPolicy: autoplay; fullscreen", "loadingStrategy: lazy"]


def services_with_iframe_widget(text, card_id, lan):
    lines = text.split("\n")
    r = card_range(lines, card_id)
    if not r or card_widget_type(text, card_id) == "iframe":
        return text
    w = next((i for i in range(*r) if re.match(r"^\s+widget:\s*$", lines[i])), None)
    if w is not None:
        wind = len(lines[w]) - len(lines[w].lstrip())
        end = w + 1
        while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) > wind):
            end += 1
        while end > w + 1 and not lines[end - 1].strip():
            end -= 1
        del lines[w:end]
        r = card_range(lines, card_id)
    ind = len(lines[r[0] + 1]) - len(lines[r[0] + 1].lstrip()) if r[0] + 1 < len(lines) else 8
    pad = " " * ind
    lines[r[1]:r[1]] = [pad + "widget:"] + [pad + "  " + l for l in navidrome_iframe_widget(lan)]
    return "\n".join(lines)


def services_without_card(text, card_id):
    lines = text.split("\n")
    r = card_range(lines, card_id)
    if not r:
        return text
    s = r[0]
    while s > 0 and not lines[s - 1].strip():
        s -= 1
    del lines[s:r[1]]
    return "\n".join(lines)


def navidrome_card_first(text):
    return card_to_top(text, "navidrome-card") == text


HP_CARDS = {
    "adguard-card": ("adguard", ["username", "password"]),
    "tailscale-card": ("tailscale", ["deviceid", "key"]),
    "beszel-card": ("beszel", ["username", "password"]),
    "speedtest-card": ("speedtest", ["key"]),
    "portainer-card": ("portainer", ["env", "key"]),
    "filebrowser-card": ("filebrowser", ["username", "password"]),
    "immich-card": ("immich", ["key"]),
    "nextcloud-card": ("nextcloud", ["key"]),
}


def hp_dir():
    return Ctx.home + "/homepage-config"


def hp_path(name="services.yaml"):
    return P(hp_dir() + "/" + name)


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def hp_ranges(lines, card_id):
    """Find a card in services.yaml: the card's line range and its widget's line range (the widget range may be None)."""
    idx = None
    for i, l in enumerate(lines):
        if re.match(r"^\s*id:\s*%s\s*$" % re.escape(card_id), l):
            idx = i
            break
    if idx is None:
        return None
    id_ind = _indent(lines[idx])
    start = idx
    while start > 0 and not (re.match(r"^\s*- .+:\s*$", lines[start]) and _indent(lines[start]) < id_ind):
        start -= 1
    hind = _indent(lines[start])
    end = idx + 1
    while end < len(lines) and (not lines[end].strip() or _indent(lines[end]) > hind):
        end += 1
    while end > idx + 1 and not lines[end - 1].strip():
        end -= 1
    ws = we = None
    for i in range(start, end):
        if re.match(r"^\s*widget:\s*$", lines[i]):
            ws = i
            wi = _indent(lines[i])
            we = i + 1
            while we < end and (not lines[we].strip() or _indent(lines[we]) > wi):
                we += 1
            while we > ws + 1 and not lines[we - 1].strip():
                we -= 1
            break
    return start, end, ws, we


def hp_template_widget(card_id):
    text = subst(read_file(repo_file("homepage-config", "services.yaml")))
    lines = text.split("\n")
    r = hp_ranges(lines, card_id)
    if not r or r[2] is None:
        return []
    return lines[r[2]:r[3]]


def hp_get(card_id, field, path=None):
    lines = read_file(path or hp_path()).split("\n")
    r = hp_ranges(lines, card_id)
    if not r or r[2] is None:
        return None
    for i in range(r[2], r[3]):
        m = re.match(r"^\s+%s:\s*(.*?)\s*$" % re.escape(field), lines[i])
        if m:
            return m.group(1).strip("\"'")
    return None


def hp_has_widget(card_id):
    lines = read_file(hp_path()).split("\n")
    r = hp_ranges(lines, card_id)
    return bool(r and r[2] is not None)


def is_placeholder(v):
    return v is None or v == "" or PH_KEY in v or PH_MAIL in v or "X.X" in v or v in ("yours",)


def hp_set_widget(card_id, values):
    path = hp_path()
    lines = read_file(path).split("\n")
    r = hp_ranges(lines, card_id)
    if not r:
        raise Abort("Card %s is not in %s." % (card_id, path))
    block = hp_template_widget(card_id)
    if not block:
        raise Abort("The repository has no widget block for %s." % card_id)
    new = []
    for l in block:
        m = re.match(r"^(\s+)([A-Za-z]+):\s*(.*)$", l)
        if m and m.group(2) in values:
            l = "%s%s: %s" % (m.group(1), m.group(2), values[m.group(2)])
        new.append(l)
    start, end, ws, we = r
    ind = " " * (_indent(lines[ws]) if ws is not None else _indent(lines[start]) + 4)
    new = [ind + l.lstrip(" ") if i == 0 else l for i, l in enumerate(new)]
    if ws is not None:
        lines[ws:we] = new
    else:
        lines[end:end] = new
    write_file(path, "\n".join(lines), owner=(Ctx.uid, Ctx.gid))


def hp_remove_card(text, card_id):
    lines = text.split("\n")
    r = hp_ranges(lines, card_id)
    if r:
        del lines[r[0]:r[1]]
        if r[0] < len(lines) and not lines[r[0]].strip():
            del lines[r[0]]
    return "\n".join(lines)


def hp_add_card(card_id):
    """Copy a card from the repository's services.yaml into this machine's file, without its widget, placing it before the card that follows it in the repository file."""
    lines = read_file(hp_path()).split("\n")
    if hp_ranges(lines, card_id):
        return False
    tmpl = subst(read_file(repo_file("homepage-config", "services.yaml"))).split("\n")
    r = hp_ranges(tmpl, card_id)
    if not r:
        return False
    block = tmpl[r[0]:r[1]]
    if r[2] is not None:
        block = block[:r[2] - r[0]] + block[r[3] - r[0]:]
    at = None
    for l in tmpl[r[1]:]:
        m = re.match(r"^\s*id:\s*(\S+)\s*$", l)
        if m:
            nxt = hp_ranges(lines, m.group(1))
            if nxt:
                at = nxt[0]
                break
    if at is None:
        lines += [""] + block
    else:
        lines[at:at] = block + [""]
    write_file(hp_path(), "\n".join(lines), owner=(Ctx.uid, Ctx.gid))
    return True


def hp_strip_widgets(text):
    lines = text.split("\n")
    for cid in HP_CARDS:
        r = hp_ranges(lines, cid)
        if r and r[2] is not None:
            del lines[r[2]:r[3]]
    return "\n".join(lines)
