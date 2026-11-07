#!/usr/bin/env python3
"""Test of scripts/homelab-panel (the control panel's server): login, protection, the look, the background, the layout, cards, links, undo.

The panel runs for real (on a free port, as a child process) with a copy of the shipped Homepage files in a temporary folder.
Run: python3 tests/t_panel.py   (last line is OK or FAIL)"""
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PANEL = os.path.join(ROOT, "scripts", "homelab-panel")
SHIPPED = os.path.join(ROOT, "homepage-config")
PW = "correct horse battery"

results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   " + str(extra)))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Panel:
    def __init__(self, tmp, extra_env=None):
        self.tmp = tmp
        self.hp = os.path.join(tmp, "homepage-config")
        shutil.copytree(SHIPPED, self.hp)
        self.state = os.path.join(tmp, "state")
        self.port = free_port()
        self.env = dict(os.environ, HLP_HOME=tmp, HOMELAB_HOMEPAGE_DIR=self.hp, HLP_STATE=self.state, HLP_PORT=str(self.port),
                        HLP_UI=os.path.join(ROOT, "panel", "ui"), HLP_COOKIE_PLAIN="1", HLP_NO_DOCKER="1",
                        HLP_HOSTS="lab.example.ts.net:1100", HLP_FRAME="https://lab.example.ts.net:1000")
        self.env.update(extra_env or {})
        self.cookie = ""
        self.proc = None

    def set_password(self, pw=PW):
        return subprocess.run([sys.executable, PANEL, "set-password", "--stdin"], input=pw + "\n", text=True, env=self.env, capture_output=True)

    def start(self):
        self.proc = subprocess.Popen([sys.executable, PANEL, "serve"], env=self.env, stderr=subprocess.PIPE)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("the panel did not start")

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(5)

    def req(self, method, path, body=None, headers=None, raw=None, host=None, cookie=True):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or "localhost:%d" % self.port}
        if headers is not False:
            h["X-Panel"] = "1"
        if cookie and self.cookie:
            h["Cookie"] = self.cookie
        h.update(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        txt = r.read()
        hdrs = dict(r.getheaders())
        c.close()
        try:
            js = json.loads(txt)
        except ValueError:
            js = None
        return r.status, js, txt, hdrs

    def login(self, pw=PW):
        st, js, _, hd = self.req("POST", "/api/login", {"password": pw}, cookie=False)
        if st == 200:
            self.cookie = hd["Set-Cookie"].split(";")[0]
        return st, js

    def state_now(self):
        return self.req("GET", "/api/state")[1]

    def read(self, fn):
        with open(os.path.join(self.hp, fn), encoding="utf-8") as f:
            return f.read()

    def write(self, fn, text):
        with open(os.path.join(self.hp, fn), "w", encoding="utf-8") as f:
            f.write(text)


def main():
    tmp = tempfile.mkdtemp(prefix="hlpanel-")
    p = Panel(tmp)
    tsock = os.path.join(tmp, "t.sock")
    p.env["HLP_TERM_SOCK"] = tsock
    fake = subprocess.Popen([sys.executable, os.path.join(HERE, "fake_ttyd.py"), tsock])
    try:
        # ---- before a password exists
        p.start()
        st, js, _, _ = p.req("GET", "/api/session")
        check("session: no password yet is reported", st == 200 and js["passwordSet"] is False and js["loggedIn"] is False, js)
        st, js = p.login("whatever1234")
        check("login: with no password set the answer tells how to set it", st == 403 and "homelab panel password" in js["error"], js)
        p.stop()

        r = p.set_password("short")
        check("password: under 10 characters is refused", r.returncode != 0 and "10 characters" in r.stderr, r.stderr)
        r = p.set_password()
        pf = os.path.join(p.state, "password")
        check("password: saved hashed, file private, folder private", r.returncode == 0 and PW not in open(pf).read() and oct(os.stat(pf).st_mode & 0o777) == "0o600"
              and oct(os.stat(p.state).st_mode & 0o777) == "0o700", r.stderr)
        p.start()

        # ---- protection
        st, js, _, _ = p.req("GET", "/api/state")
        check("protection: state needs a login", st == 401, st)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {}})
        check("protection: changes need a login", st == 401, st)
        st, js, _, _ = p.req("GET", "/", host="evil.example.com")
        check("protection: an unknown Host header is refused (no DNS rebinding)", st == 421, st)
        st, js, _, _ = p.req("GET", "/", host="lab.example.ts.net:1100")
        check("protection: the Tailscale address is accepted", st == 200, st)
        st, js, _, hd = p.req("GET", "/", host="lab.example.ts.net:1100")
        check("protection: the page may be framed only by the dashboard", "frame-ancestors 'self' https://lab.example.ts.net:1000" in hd.get("Content-Security-Policy", ""), hd)
        check("protection: scripts only from the panel itself", "script-src 'self'" in hd.get("Content-Security-Policy", "") and hd.get("Cache-Control") == "no-store", hd)
        st, js = p.login("a wrong password")
        check("login: a wrong password is refused", st == 401, (st, js))
        st, js, _, _ = p.req("POST", "/api/login", {"password": PW}, headers={"Origin": "https://evil.example.com"}, cookie=False)
        check("login: a request from another website is refused", st == 403, st)
        st, js, _, _ = p.req("POST", "/api/login", {"password": PW}, headers=False, cookie=False)
        check("login: a request without the panel header is refused", st == 403, st)
        st, js = p.login()
        check("login: the right password works", st == 200, (st, js))
        st, js, _, hd = p.req("POST", "/api/login", {"password": PW}, cookie=False)
        sc = hd.get("Set-Cookie", "")
        check("login: the cookie is HttpOnly, SameSite=Lax, Path=/", "HttpOnly" in sc and "SameSite=Lax" in sc and "Path=/" in sc, sc)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {}}, headers={"Origin": "https://evil.example.com"})
        check("csrf: a change that comes from another website is refused", st == 403, st)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {}}, headers={"Origin": "https://lab.example.ts.net:1100"})
        check("csrf: a change from the Tailscale address of the panel is accepted", st == 200, (st, js))
        st, js, _, _ = p.req("POST", "/api/look", {"look": {}}, headers={"X-Panel": "0"})
        check("csrf: a change without the panel header is refused", st == 403, st)

        s0 = p.state_now()
        check("state: has the look, background, layout, cards and links", all(k in s0 for k in ("look", "background", "layout", "services", "links")), list(s0))
        tabs = [t["name"] for t in s0["layout"]["tabs"]]
        check("state: the tabs come in file order", tabs == ["Home", "Stats", "Links", "Customize"], tabs)

        # ---- the look
        css0 = p.read("custom.css")
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"accent": "#ff8fb5", "glassOpacity": 30, "radius": 22, "tabs": {"Stats": "#ffffff"}}})
        css = p.read("custom.css")
        check("look: saved as a marked block in custom.css", st == 200 and "/* >>> homelab look >>>" in css and "--lk-accent: 255, 143, 181;" in css and "--lk-glass-a: 0.3;" in css
              and "--lk-radius: 22px;" in css and 'html[data-tab="Stats"] body #inner_wrapper { --lk-accent: 255, 255, 255; }' in css, css[-900:])
        check("look: everything above the block is untouched", css.startswith(css0.rstrip("\n")), "")
        check("look: the tabs block of the installer is untouched", css0[css0.index("/* >>> homelab tabs >>>"):css0.index("/* <<< homelab tabs <<< */")]
              == css[css.index("/* >>> homelab tabs >>>"):css.index("/* <<< homelab tabs <<< */")])
        l = p.state_now()["look"]
        check("look: read back", l["custom"]["accent"] == "#ff8fb5" and l["values"]["radius"] == 22 and l["values"]["glass"] == "#0d121e", l)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"accent": "red"}})
        check("look: a bad color is refused in plain words", st == 400 and "color" in js["error"], js)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"radius": 400}})
        check("look: a number out of range is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"tabs": {"x\"}body{display:none}": "#ffffff"}}})
        check("look: a tab name cannot carry CSS", st == 400, js)
        # a theme block written by `homelab theme` stays behind the look block
        theme = "/* >>> homelab theme >>> written by: homelab theme. Remove it with: homelab theme reset */\n.service-card { background: rgba(1, 2, 3, 0.5) !important; }\n/* <<< homelab theme <<< */\n"
        p.write("custom.css", css0.rstrip("\n") + "\n\n" + theme)
        p.req("POST", "/api/look", {"look": {"accent": "#112233"}})
        css = p.read("custom.css")
        check("look: the block goes in front of the theme command's block", css.index("homelab look >>>") < css.index("homelab theme >>>") and css.endswith(theme), css[-600:])
        p.req("POST", "/api/look", {"look": {"accent": "#445566"}})
        css = p.read("custom.css")
        check("look: saving again replaces the block (only one)", css.count("homelab look >>>") == 1 and "68, 85, 102" in css and "17, 34, 51" not in css, css[-500:])
        p.req("POST", "/api/look/reset", {})
        css = p.read("custom.css")
        check("look: reset removes the block and keeps the rest", "homelab look" not in css and css.endswith(theme), css[-400:])

        # ---- transparent glass, colors for cards / bookmarks / labels, label icons
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"glassClear": True, "glassLevel": 100}})
        css = p.read("custom.css")
        check("transparent: fully clear glass writes an alpha of 0", st == 200 and "--lk-glass-a: 0;" in css, css[-500:])
        p.req("POST", "/api/look", {"look": {"glassClear": True, "glassLevel": 0}})
        check("transparent: level 0 is the least clear (0.4)", "--lk-glass-a: 0.4;" in p.read("custom.css"))
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"glassLevel": 120}})
        check("transparent: a level out of range is refused", st == 400, js)
        paint = p.state_now()["paint"]
        check("paint: lists cards, stats, calendar, links and labels", all(paint.get(k) for k in ("cards", "stats", "links", "labels")), {k: len(v) for k, v in paint.items()})
        check("paint: every item lists its default color", all(re.fullmatch(r"#[0-9a-f]{6}", x.get("color", "")) for k in ("cards", "stats", "calendar", "links") for x in paint[k]), paint["cards"][:2])
        check("paint: a card shows the color the shipped CSS gives it", any(x["id"] == "portainer-card" and x["color"] == "#171514" for x in paint["cards"]))
        check("paint: the panel's own cards are never listed", not any(c["id"] in ("customize-card", "navidrome-card", "linkedit-card", "terminal-card") for c in paint["cards"] + paint["stats"] + paint["calendar"]), paint["cards"])
        cid, stat = paint["cards"][0]["id"], paint["stats"][0]["id"]
        bm, label = paint["links"][0]["name"], paint["labels"][0]
        slug = re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", label.lower()))
        full = {"paintAll": "#112233", "paintStrength": 55, "labelIcon": "circle", "cards": {cid: "#ff0000", stat: "#00ff00"}, "links": {bm: "#0000ff"},
                "labels": {label: {"text": "#ffffff", "icon": "#ffcc00"}}}
        st, js, _, _ = p.req("POST", "/api/look", {"look": full})
        css = p.read("custom.css")
        check("colors: saved (all, cards, stats, bookmark, label)", st == 200 and "homelab look >>>" in css, js)
        check("colors: a card gets a color (strong to faint gradient), a border and a glow", "#%s{--accent:255, 0, 0;--hl-a1:0.558;--hl-a2:0.136;}" % cid in css, css[-1500:])
        check("colors: the border and glow are on the card", "box-shadow:0 0 0 1px rgba(255, 0, 0," in css and "#%s .service-card{border-color:rgba(255, 0, 0," % cid in css, css[-1500:])
        check("colors: one color for everything leaves out the panel's cards", ':not([id="customize-card"]):not([id="navidrome-card"]):not([id="linkedit-card"]):not([id="terminal-card"])' in css and "17, 34, 51" in css, css[-1500:])
        check("colors: a bookmark is found by its name tag", 'a[data-bm="' in css and "0, 0, 255" in css, css[-1500:])
        check("colors: a label has its own text and icon colors", 'data-group="%s"' % slug in css and "color:#ffffff!important" in css and "--icon-color:#ffcc00" in css, css[-1500:])
        check("colors: the circle label icon style is written", "border-radius:50%;background:rgba(var(--hl-label,var(--lk-accent)),.20)" in css, css[-1500:])
        check("colors: read back", p.state_now()["look"]["custom"]["cards"] == {cid: "#ff0000", stat: "#00ff00"}, p.state_now()["look"]["custom"])
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"cards": {"bad id!": "#ff0000"}}})
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"paintAll": "#102030", "paintStrength": 100, "paintStyle": "solid"}})
        css = p.read("custom.css")
        check("colors: solid is the same strength on both ends (0.72 at the strongest)", st == 200 and "--hl-a1:0.72;--hl-a2:0.72;" in css, css[-700:])
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"paintAll": "#102030", "paintStrength": 100}})
        css = p.read("custom.css")
        check("colors: a gradient is strong on one end and faint on the other (0.9 to 0.22)", st == 200 and "--hl-a1:0.9;--hl-a2:0.22;" in css, css[-700:])
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"paintStrength": 80}})
        css = p.read("custom.css")
        check("colors: the strength also reaches cards, tiles and bookmarks that keep their default color", st == 200 and "--hl-a1:0.753;--hl-a2:0.184;" in css and ".bookmark>a{--hl-a1:0.753" in css and "--accent" not in css.split("--hl-a1:0.756")[0].split("\n")[-1], css[-500:])
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"paintStyle": "solid"}})
        check("colors: the solid style also reaches them (same strength on both ends)", st == 200 and "--hl-a1:0.346;--hl-a2:0.346;" in p.read("custom.css"), p.read("custom.css")[-400:])
        st, js, _, _ = p.req("POST", "/api/look/css", {"look": {}})
        check("colors: a preview back at the default clears the saved strength", st == 200 and "--hl-a1:initial" in js["css"], js)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {}})
        check("colors: the default strength and style write nothing for the cards that keep their color", st == 200 and "homelab look >>>" not in p.read("custom.css"))
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"paintStrength": 0}})
        css = p.read("custom.css")
        check("colors: 0% strength is no color at all (not the same as the default)", st == 200 and "--hl-a1:0;--hl-a2:0;" in css, css[-400:])
        shipped = p.read("custom.css")
        check("colors: the page's own CSS has exactly the 40% strength when nothing is set", "var(--hl-a1, 0.432)" in shipped and "var(--hl-a2, 0.106)" in shipped and "var(--hl-a1, 0.30)" not in shipped and "var(--hl-a1, 0.10)" not in shipped)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"paintStrength": 40, "cards": {cid: "#ff0000"}}})
        css = p.read("custom.css")
        check("colors: a card painted at the default strength gets the same alphas as the page's own CSS (0.432 and 0.106)", st == 200 and "#%s{--accent:255, 0, 0;--hl-a1:0.432;--hl-a2:0.106;}" % cid in css, css[-500:])
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"paintStyle": "stripes"}})
        check("colors: an unknown color style is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/look", {"look": full})
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"cards": {"bad id!": "#ff0000"}}})
        check("colors: a card id with odd characters is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"links": {"x": "blue"}}})
        check("colors: a bad bookmark color is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"labelIcon": "star"}})
        check("colors: an unknown label icon style is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"labels": {label: {"text": "</style>"}}}})
        check("colors: a label color cannot carry CSS", st == 400, js)
        # preview rules for a look that drops colors: the page puts everything back at once
        st, js, _, _ = p.req("POST", "/api/look/css", {"look": {"cards": {stat: "#00ff00"}, "labelIcon": "ring"}})
        pc = (js or {}).get("css", "")
        check("preview: a removed card color is reset", st == 200 and "#%s{--accent:" % cid in pc and "--hl-a1:initial;--hl-a2:initial;" in pc and "border-color:var(--lk-line)!important" in pc, pc[:900])
        check("preview: a removed bookmark color is reset", 'data-bm="' in pc and "--accent:inherit" in pc, pc[:900])
        check("preview: a removed label color is reset", "color:var(--lk-text)!important" in pc and "--icon-color:#c9d6f2" in pc, pc[:1500])
        check("preview: the full set of values is written", "--lk-accent:" in pc and "--lk-radius:" in pc, pc[:600])
        check("preview: the ring style replaces the circle one", "border:1.5px solid" in pc, pc[:1500])
        st, js, _, _ = p.req("POST", "/api/look/css", {"look": {"accent": "nope"}})
        check("preview: a bad look is refused", st == 400, js)
        p.req("POST", "/api/look/reset", {})
        check("colors: reset removes it all", "homelab look" not in p.read("custom.css"))

        # ---- names and logo
        import base64 as b64
        png = "data:image/png;base64," + b64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 40).decode()
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"names": {"homelab": "  Vault   One ", "main": "Main Pool", "backup": "Cold Copy"}, "logo": {"src": png, "link": "https://example.com/x", "size": 60}}})
        css = p.read("custom.css")
        check("names: saved as page values, the shipped name is not written", st == 200 and '--hl-name-homelab: "Vault One";' in css and '--hl-name-backup: "Cold Copy";' in css and "--hl-name-main" not in css, css[-900:])
        check("names: the logo and its link and size are written", '--hl-logo-src: "data:image/png;base64,' in css and '--hl-logo-link: "https://example.com/x";' in css and "--hl-logo-size: 60px;" in css, css[-900:])
        cs = p.state_now()["look"]["custom"]
        check("names: read back", cs["names"] == {"homelab": "Vault One", "backup": "Cold Copy"} and cs["logo"]["link"] == "https://example.com/x" and cs["logo"]["size"] == 60, cs)
        st, js, _, _ = p.req("POST", "/api/look/css", {"look": {"names": {"homelab": "X"}}})
        check("names: a preview leaves them out of the CSS (the page gets them as a message)", st == 200 and "--hl-name" not in js["css"], js)
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"logo": {"src": png, "link": "https://example.com/x", "off": True}}})
        css = p.read("custom.css")
        check("names: a logo that is switched off is kept but not written as page values", st == 200 and "--hl-logo" not in css and p.state_now()["look"]["custom"]["logo"].get("off") is True and p.state_now()["look"]["custom"]["logo"]["link"] == "https://example.com/x", css[-400:])
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"logo": {"src": png, "off": False}}})
        check("names: switched on again it shows", st == 200 and "--hl-logo-src" in p.read("custom.css") and "off" not in p.state_now()["look"]["custom"]["logo"])
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"logo": {"src": "https://example.com/logo.png"}}})
        css = p.read("custom.css")
        check("names: a web address works as a logo, without link, at the default size", st == 200 and '--hl-logo-src: "https://example.com/logo.png";' in css and "--hl-logo-link" not in css and "--hl-logo-size: 48px;" in css, css[-500:])
        for bad, why in (({"names": {"homelab": 'a"b'}}, "a quote in a name"), ({"names": {"main": "x" * 25}}, "a long name"), ({"names": {"other": "x"}}, "an unknown name"),
                         ({"names": {"main": "a\\b"}}, "a backslash"), ({"logo": {"src": "javascript:alert(1)"}}, "a script address"),
                         ({"logo": {"src": "https://a.b/c.png", "link": "ftp://x"}}, "a link that is not a web address"), ({"logo": {"src": "data:image/png;base64,AAAA"}}, "a picture that is not a picture"),
                         ({"logo": {"src": "data:image/svg+xml;base64,AAAA"}}, "an svg data address"), ({"logo": {"src": "https://a.b/c\\d.png"}}, "a backslash in the address"),
                         ({"logo": {"src": png, "size": 500}}, "a huge size"), ({"logo": {"src": "data:image/png;base64," + "A" * 200000}}, "a huge picture")):
            st, js, _, _ = p.req("POST", "/api/look", {"look": bad})
            check("names: refused: " + why, st == 400, (st, js))
        st, js, _, _ = p.req("POST", "/api/look", {"look": {"names": {"main": ""}, "logo": {"link": "https://example.com/only-link"}}})
        check("names: a link without a picture is dropped", st == 200 and "--hl-logo" not in p.read("custom.css") and "--hl-name" not in p.read("custom.css"), p.read("custom.css")[-300:])
        p.req("POST", "/api/look", {"look": {"names": {"backup": "Cold Copy"}}})
        p.req("POST", "/api/look/reset", {})
        check("names: the reset takes them away", "--hl-name" not in p.read("custom.css") and p.state_now()["look"]["custom"] == {})

        # the icon library (lists given by a file, so the test needs no internet)
        tree = os.path.join(tmp, "tree.json")
        mdi = os.path.join(tmp, "mdi.json")
        with open(tree, "w") as f:
            json.dump({"svg": ["plex.svg", "portainer.svg", "bad name.svg", "<x>.svg"], "png": ["plex.png", "old-app.png"]}, f)
        with open(mdi, "w") as f:
            json.dump([{"name": "home-outline"}, {"name": "Bad Name"}, {"name": "server"}], f)
        p2 = Panel(os.path.join(tmp, "icons"), {"HLP_ICON_TREE": tree, "HLP_ICON_MDI": mdi})
        p2.set_password()
        p2.start()
        try:
            st, js, _, _ = p2.req("GET", "/api/icons", cookie=False)
            check("icons: need a login", st == 401, st)
            p2.login()
            st, js, _, _ = p2.req("GET", "/api/icons")
            check("icons: apps (svg first, png only if there is no svg) and mdi names, bad names dropped",
                  st == 200 and js["apps"] == ["old-app.png", "plex.svg", "portainer.svg"] and js["mdi"] == ["home-outline", "server"], js)
        finally:
            p2.stop()

        # ---- the web terminal (ttyd on a socket, behind the panel's login)
        for _ in range(50):
            if os.path.exists(tsock):
                break
            time.sleep(0.05)

        def ws(cookie=True, origin="http://localhost:%d" % p.port, send=b"hello"):
            """A WebSocket handshake to /terminal/ws by hand. Returns (the head of the answer, the bytes that came back after it)."""
            c = socket.create_connection(("127.0.0.1", p.port), timeout=5)
            lines = ["GET /terminal/ws HTTP/1.1", "Host: localhost:%d" % p.port, "Upgrade: websocket", "Connection: Upgrade",
                     "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==", "Sec-WebSocket-Version: 13"]
            if origin:
                lines.append("Origin: " + origin)
            if cookie and p.cookie:
                lines.append("Cookie: " + p.cookie)
            c.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
            buf = b""
            while b"\r\n\r\n" not in buf:
                d = c.recv(4096)
                if not d:
                    break
                buf += d
            head, _, rest = buf.partition(b"\r\n\r\n")
            if head.startswith(b"HTTP/1.1 101"):
                c.sendall(send)
                while len(rest) < len(b"echo:" + send):
                    d = c.recv(4096)
                    if not d:
                        break
                    rest += d
            c.close()
            return head.decode("latin-1"), rest

        st, js, txt, hd = p.req("GET", "/terminal/", cookie=False)
        check("terminal: without the login the page says to log in (and nothing from the terminal is passed)", st == 401 and b"log in" in txt and b"fake ttyd" not in txt, (st, txt[:200]))
        head, _ = ws(cookie=False)
        check("terminal: without the login the WebSocket is refused", head.startswith("HTTP/1.1 401"), head[:80])
        st, js, txt, hd = p.req("GET", "/terminal/")
        csp = hd.get("Content-Security-Policy", "")
        check("terminal: with the login the terminal's page comes through", st == 200 and b"fake ttyd" in txt and "text/html" in hd.get("Content-Type", ""), (st, txt[:100]))
        check("terminal: its page may run its own script and may be framed only by the dashboard", "script-src 'self' 'unsafe-inline'" in csp and "frame-ancestors 'self' https://lab.example.ts.net:1000" in csp, csp)
        check("terminal: a line is added to its page so the dashboard does not move when it reaches its top or bottom", b"overscroll-behavior:contain" in txt and b"fake ttyd" in txt, txt[:300])
        check("terminal: the panel's login cookie is not given to the terminal", "X-Seen-Cookie" not in hd and b"hlpanel" not in txt)
        st, js, txt, hd = p.req("GET", "/terminal/token")
        check("terminal: the token address comes through", st == 200 and js == {"token": ""}, (st, txt))
        st, js, txt, hd = p.req("GET", "/terminal")
        check("terminal: /terminal goes to /terminal/", st == 302 and hd.get("Location") == "/terminal/", (st, hd))
        st, js, txt, hd = p.req("GET", "/terminal/nothing-here")
        check("terminal: an address the terminal does not have is not found", st == 404, st)
        st, js, txt, hd = p.req("GET", "/terminal/", host="evil.example.com")
        check("terminal: another host name is refused", st == 421, st)
        st, js, txt, hd = p.req("POST", "/terminal/", body={})
        check("terminal: only GET goes through (a POST does not reach the terminal)", st != 200 and b"fake ttyd" not in txt, st)
        head, _ = ws(origin="https://evil.example.com")
        check("terminal: a WebSocket from another website is refused", head.startswith("HTTP/1.1 403"), head[:80])
        head, _ = ws(origin=None)
        check("terminal: a WebSocket with no origin is refused", head.startswith("HTTP/1.1 403"), head[:80])
        head, back = ws(origin="https://lab.example.ts.net:1100")
        check("terminal: a WebSocket from the panel's own address is passed on, and bytes go both ways", head.startswith("HTTP/1.1 101") and back == b"echo:hello", (head[:60], back))
        check("terminal: the login cookie is not given to the terminal here either", "X-Seen-Cookie: \r\n" in head + "\r\n" and "hlpanel" not in head, head)
        fake.terminate()
        fake.wait(5)
        try:
            os.unlink(tsock)
        except OSError:
            pass
        st, js, txt, hd = p.req("GET", "/terminal/")
        check("terminal: when it is not running the card says so in plain words", st == 502 and b"homelab-terminal" in txt, (st, txt[:200]))
        head, _ = ws()
        check("terminal: ... and so does the WebSocket", head.startswith("HTTP/1.1 502"), head[:80])

        # ---- the background
        st, js, _, _ = p.req("POST", "/api/background", {"blur": "xl", "brightness": 30, "saturate": 90, "opacity": 70})
        bg = p.state_now()["background"]
        check("background: sliders are saved in settings.yaml", st == 200 and bg["blur"] == "xl" and bg["brightness"] == 30 and bg["saturate"] == 90 and bg["opacity"] == 70, bg)
        settings = p.read("settings.yaml")
        check("background: the layout block of settings.yaml is intact", "layout:" in settings and "  Customize:" in settings and "language: en" in settings)
        st, js, _, _ = p.req("POST", "/api/background", {"blur": "huge"})
        check("background: a bad blur is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/background", {"brightness": 500})
        check("background: a number over 100 is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/background", {"url": "https://example.com/a b.jpg"})
        check("background: an address with spaces is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/background", {"url": "javascript:alert(1)"})
        check("background: only http(s) addresses are accepted", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/background", {"url": "https://example.com/night.jpg?w=1&q=2"})
        check("background: a web address is saved", st == 200 and p.state_now()["background"]["image"] == "https://example.com/night.jpg?w=1&q=2", st)
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
        st, js, _, _ = p.req("POST", "/api/background/upload", raw=png, headers={"Content-Type": "application/octet-stream"})
        img = p.state_now()["background"]["image"]
        check("background: an uploaded picture is stored in the images folder and used", st == 200 and re.fullmatch(r"/images/background-\d{14}\.png", img)
              and os.path.exists(os.path.join(p.hp, img.lstrip("/"))), (st, js, img))
        st, js, _, _ = p.req("POST", "/api/background/upload", raw=b"<html>not a picture</html>", headers={"Content-Type": "application/octet-stream"})
        check("background: a file that is not a picture is refused", st == 400, (st, js))
        p.req("POST", "/api/background/reset", {})
        bg = p.state_now()["background"]
        check("background: reset puts the sliders back to the shipped values", bg["blur"] == "md" and bg["brightness"] == 42 and bg["saturate"] == 60 and bg["opacity"] == 80, bg)

        # ---- undo
        before = p.read("settings.yaml")
        p.req("POST", "/api/background", {"brightness": 11})
        st, js, _, _ = p.req("POST", "/api/undo", {})
        check("undo: the last change is taken back", st == 200 and p.read("settings.yaml") == before and js["undone"] == "Background changed", (st, js))
        check("undo: the panel says what Undo would do", p.state_now()["undo"] != "")

        # ---- layout
        lay = p.state_now()["layout"]
        home = next(t for t in lay["tabs"] if t["name"] == "Home")
        names = [g["name"] for g in home["groups"]]
        check("layout: Home has its four groups (the calendar is at the bottom)", names == ["Network & DNS", "Monitoring & Management", "Files & Photos", "Media & Entertainment", "Calendar"], names)
        want = json.loads(json.dumps(lay))
        h = next(t for t in want["tabs"] if t["name"] == "Home")
        h["groups"].insert(0, h["groups"].pop(2))                      # Files & Photos first
        stt = next(t for t in want["tabs"] if t["name"] == "Stats")
        h["groups"].remove(next(g for g in h["groups"] if g["name"] == "Media & Entertainment"))
        stt["groups"].append({"name": "Media & Entertainment", "icon": "mdi-play", "style": "row", "columns": 3})
        st, js, _, _ = p.req("POST", "/api/layout", want)
        s = p.read("settings.yaml")
        check("layout: groups can be reordered and moved to another tab", st == 200 and s.index("  Files & Photos:") < s.index("  Network & DNS:")
              and re.search(r"  Media & Entertainment:\n    tab: Stats\n    icon: mdi-play\n    style: row\n    columns: 3", s), (st, js, s[s.index("layout:"):][:600]))
        check("layout: the rest of settings.yaml is untouched", "headerStyle: boxedWidgets" in s and "quicklaunch:" in s and "language: en" in s)
        bad = json.loads(json.dumps(lay))
        bad["tabs"][0]["groups"].pop()
        st, js, _, _ = p.req("POST", "/api/layout", bad)
        check("layout: a layout that loses a group is refused", st == 400 and "missing" in js["error"], js)
        bad = json.loads(json.dumps(lay))
        bad["tabs"][0]["groups"].append({"name": "Made up group"})
        st, js, _, _ = p.req("POST", "/api/layout", bad)
        check("layout: an unknown group is refused", st == 400, js)
        bad = json.loads(json.dumps(lay))
        bad["tabs"][0]["name"] = "Ho:me"
        st, js, _, _ = p.req("POST", "/api/layout", bad)
        check("layout: a tab name with a colon is refused", st == 400, js)
        ren = json.loads(json.dumps(p.state_now()["layout"]))
        ren["tabs"][0]["name"] = "Main"
        ren["tabs"].append({"name": "Work", "groups": []})
        st, js, _, _ = p.req("POST", "/api/layout", ren)
        check("layout: a tab can be renamed (an empty tab is not kept)", st == 200 and [t["name"] for t in p.state_now()["layout"]["tabs"]][0] == "Main"
              and "Work" not in [t["name"] for t in p.state_now()["layout"]["tabs"]], js)
        p.req("POST", "/api/undo", {})
        p.req("POST", "/api/undo", {})

        # ---- cards
        blank0 = p.read("services.yaml").count("\n\n\n")
        st, js, _, _ = p.req("POST", "/api/card", {"op": "add", "group": "Tools", "name": "Router", "href": "http://192.168.1.1", "icon": "mdi-router",
                                                    "description": "Home router", "dot": True, "tab": "Home"})
        svcs = p.read("services.yaml")
        check("cards: a new card makes its group (and puts it on a tab)", st == 200 and "- Tools:" in svcs and "    - Router:" in svcs and "href: http://192.168.1.1" in svcs
              and "siteMonitor: http://192.168.1.1" in svcs and re.search(r"  Tools:\n    tab: Home", p.read("settings.yaml")), (js, svcs[-500:]))
        check("cards: the other cards and their widgets are untouched", "widget:\n          type: adguard" in svcs and "key: your-own-key" in svcs)
        st, js, _, _ = p.req("POST", "/api/card", {"op": "add", "group": "Tools", "name": "Router", "href": "http://x.example"})
        check("cards: the same name twice is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/card", {"op": "add", "group": "Tools", "name": "Bad", "href": "ftp://x"})
        check("cards: an address that is not http(s) is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/card", {"op": "add", "group": "Storage", "name": "Mine", "href": "http://x.example"})
        check("cards: a group the lab keeps up to date is refused", st == 400 and "kept up to date" in js["error"], js)
        st, js, _, _ = p.req("POST", "/api/card", {"op": "add", "group": "Tools", "name": "Printer: HP", "href": "http://printer.local"})
        check("cards: a name with a colon is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/card", {"op": "edit", "group": "Tools", "old": "Router", "name": "Main router", "href": "http://192.168.1.254",
                                                    "icon": "", "description": "The router: upstairs"})
        svcs = p.read("services.yaml")
        check("cards: edit changes name, address, text; an empty icon removes the line", st == 200 and "    - Main router:" in svcs and "http://192.168.1.254" in svcs
              and 'description: "The router: upstairs"' in svcs and "mdi-router" not in svcs and "siteMonitor" not in svcs.split("- Main router:")[1], svcs[-400:])
        st, js, _, _ = p.req("POST", "/api/card", {"op": "edit", "group": "Network & DNS", "old": "AdGuard Home", "name": "AdGuard", "icon": "adguard-home.svg",
                                                    "description": "Ad blocking", "href": "http://evil.example"})
        svcs = p.read("services.yaml")
        check("cards: a lab card keeps its address (only name, icon and text change)", st == 200 and "    - AdGuard:" in svcs and "href: https://pc.your-tailnet.ts.net:1004" in svcs
              and "http://evil.example" not in svcs and "description: Ad blocking" in svcs, svcs[svcs.index("- Network"):][:500])
        st, js, _, _ = p.req("POST", "/api/card", {"op": "edit", "group": "Storage", "old": "Storage", "name": "x"})
        check("cards: a lab-managed group is refused", st == 400, js)
        st, js, _, _ = p.req("POST", "/api/card", {"op": "move", "group": "Tools", "name": "Main router", "to": "Network & DNS", "before": "Tailscale"})
        s0 = p.state_now()["services"]
        nd = next(g for g in s0 if g["group"] == "Network & DNS")
        check("cards: a card moves to another group, in front of a card", st == 200 and nd["cards"][0]["name"] == "Main router" and not any(g["group"] == "Tools" for g in s0)
              and "Tools" not in [g["name"] for t in p.state_now()["layout"]["tabs"] for g in t["groups"]], (js, [c["name"] for c in nd["cards"]]))
        st, js, _, _ = p.req("POST", "/api/card", {"op": "move", "group": "Network & DNS", "name": "Main router", "to": "Network & DNS", "before": "Speedtest Tracker"})
        nd = next(g for g in p.state_now()["services"] if g["group"] == "Network & DNS")
        check("cards: a card moves within its group", st == 200 and [c["name"] for c in nd["cards"]][-2:] == ["Main router", "Speedtest Tracker"] or [c["name"] for c in nd["cards"]].index("Main router") < [c["name"] for c in nd["cards"]].index("Speedtest Tracker"), [c["name"] for c in nd["cards"]])
        st, js, _, _ = p.req("POST", "/api/card", {"op": "remove", "group": "Network & DNS", "name": "Main router"})
        check("cards: a card is removed", st == 200 and "Main router" not in p.read("services.yaml"), js)
        check("cards: removing leaves no double blank lines", p.read("services.yaml").count("\n\n\n") <= blank0)
        st, js, _, _ = p.req("POST", "/api/card", {"op": "remove", "group": "Customize", "name": "Control panel"})
        check("cards: the panel's own card cannot be removed", st == 400, js)
        # the file still reads
        try:
            import yaml
            ok = isinstance(yaml.safe_load(p.read("services.yaml")), list) and isinstance(yaml.safe_load(p.read("settings.yaml")), dict)
        except ImportError:
            ok = True
        check("cards: both files are still valid YAML", ok)

        # ---- links
        s1 = p.state_now()["links"]
        check("links: the shipped groups are read", [g["group"] for g in s1][:3] == ["Entertainment", "Online Shopping", "Productivity"] and s1[0]["links"][0]["href"] == "https://youtube.com/", s1[:1])
        st, js, _, _ = p.req("POST", "/api/link", {"op": "add", "group": "Job Hunt", "name": "Indeed", "href": "https://www.indeed.com", "icon": "", "tab": "Links"})
        marks = p.read("bookmarks.yaml")
        check("links: a link in a new group, with a short label made from the name", st == 200 and "- Job Hunt:" in marks and "    - Indeed:" in marks and "- abbr: INDE" in marks
              and re.search(r"  Job Hunt:\n    tab: Links", p.read("settings.yaml")), (js, marks[-400:]))
        check("links: the comment lines at the top of the file are kept", marks.startswith("# A short example list"))
        check("links: the other links keep their icon address", "https://cdn.brandfetch.io/idVfYwcuQz/theme/dark/symbol.svg?c=1dxbfHSJFAPEGdCLU4o5B" in marks)
        st, js, _, _ = p.req("POST", "/api/link", {"op": "edit", "group": "Job Hunt", "old": "Indeed", "name": "Indeed", "href": "https://indeed.com/jobs", "abbr": "IND", "icon": "si-indeed"})
        marks = p.read("bookmarks.yaml")
        check("links: edit", st == 200 and "href: https://indeed.com/jobs" in marks and "abbr: IND\n" in marks and "icon: si-indeed" in marks, (js, marks[-300:]))
        st, js, _, _ = p.req("POST", "/api/link", {"op": "add", "group": "Job Hunt", "name": "LinkedIn", "href": "https://linkedin.com"})
        st, js, _, _ = p.req("POST", "/api/link", {"op": "move", "group": "Job Hunt", "name": "LinkedIn", "to": "Job Hunt", "before": "Indeed"})
        jh = next(g for g in p.state_now()["links"] if g["group"] == "Job Hunt")
        check("links: reorder", [e["name"] for e in jh["links"]] == ["LinkedIn", "Indeed"], jh)
        st, js, _, _ = p.req("POST", "/api/link", {"op": "move", "group": "Job Hunt", "name": "LinkedIn", "to": "Productivity"})
        check("links: move to another group", "LinkedIn" in [e["name"] for g in p.state_now()["links"] if g["group"] == "Productivity" for e in g["links"]], js)
        st, js, _, _ = p.req("POST", "/api/link", {"op": "group-rename", "group": "Job Hunt", "to": "Careers"})
        check("links: a group is renamed (the layout follows)", st == 200 and "Careers" in [g["name"] for t in p.state_now()["layout"]["tabs"] for g in t["groups"]], js)
        st, js, _, _ = p.req("POST", "/api/link", {"op": "remove", "group": "Careers", "name": "Indeed"})
        check("links: removing the last link removes the group and its layout line", st == 200 and "Careers" not in [g["name"] for t in p.state_now()["layout"]["tabs"] for g in t["groups"]], js)
        st, js, _, _ = p.req("POST", "/api/link", {"op": "add", "group": "X", "name": "Bad", "href": "http://a.b/\"quote"})
        check("links: an address with a quote is refused", st == 400, js)
        try:
            import yaml
            ok = isinstance(yaml.safe_load(p.read("bookmarks.yaml")), list)
        except ImportError:
            ok = True
        check("links: bookmarks.yaml is still valid YAML", ok)

        # ---- whole groups, passwords, logout
        p.req("POST", "/api/card", {"op": "add", "group": "Temp", "name": "T1", "href": "http://t.example"})
        st, js, _, _ = p.req("POST", "/api/group", {"op": "rename", "group": "Temp", "to": "Temporary"})
        check("groups: a group of cards is renamed in services.yaml and the layout", st == 200 and "- Temporary:" in p.read("services.yaml") and "  Temporary:" in p.read("settings.yaml"), js)
        st, js, _, _ = p.req("POST", "/api/group", {"op": "remove", "group": "Temporary"})
        check("groups: a group is removed from services.yaml and the layout", st == 200 and "Temporary" not in p.read("services.yaml") + p.read("settings.yaml"), js)
        st, js, _, _ = p.req("POST", "/api/group", {"op": "remove", "group": "Storage"})
        check("groups: a group the lab keeps up to date cannot be removed", st == 400, js)

        r = p.set_password("another long password")
        st, js, _, _ = p.req("GET", "/api/state")
        check("password: a new password logs a running panel's sessions out", r.returncode == 0 and st == 401, st)
        st, js = p.login(PW)
        check("password: the old password no longer works", st == 401, st)
        st, js = p.login("another long password")
        check("password: the new password works", st == 200, st)
        st, js, _, _ = p.req("POST", "/api/logout", {})
        st2, js2, _, _ = p.req("GET", "/api/state")
        check("logout: the session ends", st == 200 and st2 == 401, (st, st2))

        # ---- too many wrong passwords
        p.cookie = ""
        codes = [p.login("wrong password %d" % i)[0] for i in range(7)]
        check("login: after several wrong passwords the panel makes the person wait", 429 in codes, codes)
        st, js = p.login("another long password")
        check("login: the wait also applies to the right password", st == 429, st)
    finally:
        p.stop()
        fake.terminate()
        shutil.rmtree(tmp, ignore_errors=True)
    ok = all(results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
