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
        check("look: a bad colour is refused in plain words", st == 400 and "colour" in js["error"], js)
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
        shutil.rmtree(tmp, ignore_errors=True)
    ok = all(results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
