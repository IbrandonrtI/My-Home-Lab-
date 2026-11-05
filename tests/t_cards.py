#!/usr/bin/env python3
"""Tests of scripts/homelab-cards: a card for every new service, put in the right section, with its colour, its Tailscale address
and its icon, kept right afterwards and removed with the service. Docker, Tailscale and the icon library are stand-ins; the web pages
of the "services" are real little servers on this machine. Nothing outside a temp folder is touched.
Run: python3 tests/t_cards.py   (last line is OK or FAIL)"""
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PROG = os.path.join(ROOT, "scripts", "homelab-cards")
try:
    import yaml
except ImportError:
    yaml = None

bad = 0


def check(name, ok, extra=""):
    global bad
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   " + str(extra)[:600]))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Web(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if not self.server.code else self.server.code)
        self.end_headers()
        self.wfile.write(b"hello")

    do_HEAD = do_GET

    def log_message(self, *a):
        pass


def serve_web(code=0):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Web)
    srv.code = code
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


class Icons(http.server.BaseHTTPRequestHandler):
    HAVE = {"/gh/homarr-labs/dashboard-icons/svg/jellyfin.svg", "/npm/simple-icons/icons/paperlessngx.svg"}

    def do_HEAD(self):
        self.send_response(200 if self.path in self.HAVE else 404)
        self.end_headers()

    def log_message(self, *a):
        pass


icons = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Icons)
threading.Thread(target=icons.serve_forever, daemon=True).start()

class Api(http.server.BaseHTTPRequestHandler):
    """Docker Hub and GitHub in miniature: the short text of an image or project."""
    DATA = {"/v2/repositories/someone/zzzapp": {"description": "A tiny: test app, with a colon #1"},
            "/repos/someone/gh-app": {"description": "Self-hosted gallery for [your photos](http://x) and videos, with many more words than fit"}}

    def do_GET(self):
        body = self.DATA.get(self.path)
        self.send_response(200 if body is not None else 404)
        self.end_headers()
        self.wfile.write(json.dumps(body or {}).encode())

    def log_message(self, *a):
        pass


api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Api)
threading.Thread(target=api.serve_forever, daemon=True).start()

FAKE_TS = '''#!%s
import json, os, sys
a = sys.argv[1:]
state = os.environ["TS_STATE"]
if os.path.exists(os.environ["TS_DOWN"]):
    sys.exit(1)
js = json.load(open(state))
if a[:2] == ["status", "--json"]:
    print(json.dumps({"Self": {"DNSName": open(os.environ["TS_NAME"]).read().strip() + "."}}))
elif a[:3] == ["serve", "status", "--json"]:
    print(json.dumps(js))
elif a[:2] == ["serve", "--bg"]:
    port = a[2].split("=")[1]
    js.setdefault("Web", {})["host:%%s" %% port] = {"Handlers": {"/": {"Proxy": a[3]}}}
    json.dump(js, open(state, "w"))
elif a[0] == "serve" and a[-1] == "off":
    js.get("Web", {}).pop("host:%%s" %% a[1].split("=")[1], None)
    json.dump(js, open(state, "w"))
''' % sys.executable

FAKE_DOCKER = '''#!/bin/sh
case "$1" in
  ps) %s -c "import json;print('\\n'.join(c['Id'] for c in json.load(open('$FAKE_DOCKER_JSON'))))" ;;
  inspect) cat "$FAKE_DOCKER_JSON" ;;
esac
''' % sys.executable


def container(name, image, port=None, status="running", labels=None, project=""):
    lab = dict(labels or {})
    if project:
        lab["com.docker.compose.project"] = project
    binds = {"8080/tcp": [{"HostIp": "", "HostPort": str(port)}]} if port else {}
    return {"Id": "id-" + name, "Name": "/" + name, "State": {"Status": status},
            "Config": {"Image": image, "Labels": lab}, "HostConfig": {"PortBindings": binds}}


class Lab:
    def __init__(self, services, css):
        self.d = tempfile.mkdtemp()
        self.hp = os.path.join(self.d, "hp")
        os.makedirs(self.hp)
        os.makedirs(os.path.join(self.d, "bin"))
        shutil.copy(services, os.path.join(self.hp, "services.yaml"))
        shutil.copy(css, os.path.join(self.hp, "custom.css"))
        for n, body in (("docker", FAKE_DOCKER), ("tailscale", FAKE_TS)):
            p = os.path.join(self.d, "bin", n)
            open(p, "w").write(body)
            os.chmod(p, 0o755)
        self.dj = os.path.join(self.d, "docker.json")
        self.ts = os.path.join(self.d, "ts.json")
        self.name = os.path.join(self.d, "tsname")
        self.down = os.path.join(self.d, "tsdown")
        open(self.name, "w").write("homelab.example.ts.net")
        self.set_ts({})
        self.lan = "192.168.1.198"
        self.cs = []
        self.servers = []

    def web(self, code=0):
        srv, port = serve_web(code)
        self.servers.append(srv)
        return port

    def set_ts(self, web):
        json.dump({"Web": web}, open(self.ts, "w"))

    def set_containers(self, cs):
        self.cs = cs
        json.dump(cs, open(self.dj, "w"))

    def env(self):
        e = dict(os.environ)
        e.update(HP_DIR=self.hp, HOMELAB_STATE_DIR=os.path.join(self.d, "state"), HOMELAB_DOCKER=os.path.join(self.d, "bin", "docker"),
                 HOMELAB_TAILSCALE=os.path.join(self.d, "bin", "tailscale"), FAKE_DOCKER_JSON=self.dj, TS_STATE=self.ts,
                 TS_NAME=self.name, TS_DOWN=self.down, HOMELAB_LAN_IP=self.lan, HOMELAB_CARDS_NOROOT="1",
                 HOMELAB_ICON_CDN="http://127.0.0.1:%d" % icons.server_address[1], HOMELAB_CARDS_LOG=os.path.join(self.d, "cards.log"),
                 HOMELAB_CARDS_LOCK=os.path.join(self.d, "lock"), HOMELAB_PROBE_HOST="127.0.0.1",
                 HOMELAB_DESC_HUB="http://127.0.0.1:%d" % api.server_address[1], HOMELAB_DESC_GITHUB="http://127.0.0.1:%d" % api.server_address[1],
                 HOMELAB_DESC_RETRY_SECS="0")
        return e

    def run(self, *args):
        p = subprocess.run([sys.executable, PROG] + list(args), capture_output=True, text=True, env=self.env(), timeout=120)
        return p.returncode, p.stdout + p.stderr

    def svc(self):
        return open(os.path.join(self.hp, "services.yaml")).read()

    def css(self):
        return open(os.path.join(self.hp, "custom.css")).read()

    def state(self):
        return json.load(open(os.path.join(self.d, "state", "cards.json")))

    def close(self):
        for s in self.servers:
            s.shutdown()
        shutil.rmtree(self.d, ignore_errors=True)


def valid(text):
    return yaml is None or bool(yaml.safe_load(text))


def groups(text):
    """{section: [card ids]} read from the YAML."""
    if yaml is None:
        return {}
    out = {}
    for g in yaml.safe_load(text):
        for k, v in g.items():
            out[k] = [c[list(c)[0]]["id"] for c in (v or [])]
    return out


LIVE_SVC = os.path.join(HERE, "fixtures", "live-services.yaml")
LIVE_CSS = os.path.join(HERE, "fixtures", "live-cards.css")
SHIPPED_SVC = os.path.join(ROOT, "homepage-config", "services.yaml")
SHIPPED_CSS = os.path.join(ROOT, "homepage-config", "custom.css")

# ---------------------------------------------------------------- 1. new services on a machine like Brandon's
lab = Lab(LIVE_SVC, LIVE_CSS)
try:
    check("the fixture services.yaml is valid", valid(lab.svc()))
    p_jelly, p_paper, p_weird, p_old, p_metube = lab.web(), lab.web(), lab.web(), lab.web(), lab.web()
    p_db, p_stopped = free_port(), lab.web()       # nothing listens on p_db: a database port is no web page
    lab.set_ts({"host:1009": {"Handlers": {"/": {"Proxy": "http://192.168.1.198:%d" % p_metube}}}})
    lab.set_containers([
        container("metube", "ghcr.io/alexta69/metube", p_metube),
        container("filebrowser", "filebrowser/filebrowser", lab.web(), project="filebrowser"),
        container("immich_postgres", "postgres:14", p_db, project="immich"),
        container("jellyfin", "lscr.io/linuxserver/jellyfin:latest", p_jelly, project="media"),
        container("paperless", "ghcr.io/paperless-ngx/paperless-ngx:latest", p_paper, project="docs"),
        container("zzzapp", "someone/zzzapp", p_weird),
        container("ghapp", "ghcr.io/someone/gh-app:latest", lab.web()),
        container("labelapp", "x/labelapp", lab.web(), labels={"org.opencontainers.image.description": "Scan and index documents"}),
        container("plainapp", "nobody/plainapp", lab.web(), project="stackname"),
        container("mydb", "postgres:16", p_db),
        container("stopped-thing", "lscr.io/linuxserver/sonarr", p_stopped, status="exited"),
        container("navidrome", "ghcr.io/navidrome/navidrome:0.64.2", lab.web(), labels={"org.opencontainers.image.title": "navidrome"}),
    ])
    before_svc, before_css = lab.svc(), lab.css()
    rc, out = lab.run("sync", "--dry-run")
    check("a dry run changes nothing", rc == 0 and lab.svc() == before_svc and lab.css() == before_css and "Added the card Jellyfin" in out, out)
    check("a dry run saves no state", not os.path.exists(os.path.join(lab.d, "state", "cards.json")))

    rc, out = lab.run()
    check("sync succeeds", rc == 0, out)
    svc, css = lab.svc(), lab.css()
    check("services.yaml is still valid YAML", valid(svc), svc)
    g = groups(svc)
    check("Jellyfin goes to Media & Entertainment", "jellyfin-card" in g.get("Media & Entertainment", []), g)
    check("Paperless goes to Files & Photos", "paperless-card" in g.get("Files & Photos", []), g)
    check("an unknown app goes to Monitoring & Management", "zzzapp-card" in g.get("Monitoring & Management", []), g)
    check("a database whose port is no web page gets no card", "mydb-card" not in svc and "immich_postgres-card" not in svc)
    check("a stopped container gets no card", "stopped-thing-card" not in svc)
    check("the lab's own containers get no card", "filebrowser-card" in svc and svc.count("id: filebrowser-card") == 1)
    check("the hand written Metube card is not touched", svc.count("id: metube-card") == 1 and "icon: metube.svg" in svc)
    check("the new cards keep the section order of the file", g.get("Media & Entertainment", [])[:4] == ["navidrome-card", "metube-card", "downtify-card", "jellyfin-card"], g)
    check("an image that calls itself navidrome gets the card Navidrome, described as Spotify Music Player",
          "    - Navidrome:\n        id: navidrome-card" in svc and "description: Spotify Music Player" in svc.split("id: navidrome-card")[1].split("\n\n")[0], svc)
    check("the Navidrome card is put first in its section, the others at the end", g.get("Media & Entertainment", [])[0] == "navidrome-card", g)
    ports = sorted(int(k.split(":")[1]) for k in json.load(open(lab.ts))["Web"])
    check("each new service got its own Tailscale port from 1009 on", ports == [1009, 1010, 1011, 1012, 1013, 1014, 1015, 1016], ports)
    jelly = svc.split("id: jellyfin-card")[1].split("\n\n")[0]
    check("the card links the Tailscale address and watches the local one", re.search(r"href: https://homelab\.example\.ts\.net:101\d", jelly)
          and "siteMonitor: http://192.168.1.198:%d" % p_jelly in jelly, jelly)
    check("the icon comes from the icon library", "icon: jellyfin.svg" in jelly, jelly)
    check("the second choice is Simple Icons", "icon: si-paperlessngx" in svc.split("id: paperless-card")[1].split("\n\n")[0])
    check("without an icon anywhere it is a Docker icon", "icon: mdi-docker" in svc.split("id: zzzapp-card")[1].split("\n\n")[0])
    check("a description from the image itself is used", "description: Scan and index documents" in svc)
    check("a known app's text wins over the web look-up", "description: Document archive" in svc)
    check("a known app gets its own text", "description: Movies, shows and music server" in svc)
    check("the text of the image on Docker Hub is used, quoted when needed", 'description: "A tiny: test app, with a colon 1"' in svc, svc)
    check("the text of a GitHub project is used, cut at a word", "description: Self-hosted gallery for your photos and videos, with many" in svc, svc)
    check("with no information the note names the stack", "description: Added automatically (stackname)" in svc)
    check("the card is named after the container", "- Jellyfin:" in svc and "- Zzzapp:" in svc)
    for cid in ("jellyfin-card", "paperless-card", "zzzapp-card"):
        for suf in ("", "::before", "::after"):
            check("custom.css lists %s%s with the others" % (cid, suf), re.search(r"#%s%s\s*[,{]" % (cid, re.escape(suf)), css), css[-800:])
        check("custom.css gives %s a colour" % cid, re.search(r"(?m)^#%s\s*\{ --accent: \d+, \d+, \d+; \}" % cid, css))
    check("Jellyfin has its known colour", "#jellyfin-card { --accent: 170, 92, 195; }" in css)
    new_cols = [re.search(r"#%s-card \{ --accent: (\d+, \d+, \d+);" % n, css).group(1) for n in ("jellyfin", "paperless", "zzzapp")]
    check("the three new cards have three different colours", len(set(new_cols)) == 3, new_cols)
    check("the old files are saved once", os.path.exists(os.path.join(lab.hp, "services.yaml.before-cards")) and os.path.exists(os.path.join(lab.hp, "custom.css.before-cards")))
    check("the hand written lists stay valid", css.count("{") == css.count("}"))
    st = lab.state()
    check("the state knows the seven cards", sorted(st["managed"]) == ["ghapp", "jellyfin", "labelapp", "navidrome", "paperless", "plainapp", "zzzapp"], st)
    check("the unsure one is flagged", st["managed"]["zzzapp"]["unsure"] and not st["managed"]["jellyfin"]["unsure"])
    summ = open(os.path.join(lab.d, "state", "cards-summary")).read()
    check("the login screen can read the summary", summ.count("managed|") == 7 and "managed|zzzapp|zzzapp-card|Monitoring & Management|1|" in summ, summ)
    check("it said it was not sure and how to move the card", "sudo homelab-cards move zzzapp" in out)

    # ---- idempotence
    snap = (lab.svc(), lab.css())
    rc, out = lab.run()
    check("a second look changes nothing", rc == 0 and (lab.svc(), lab.css()) == snap and "Nothing to do" in out, out)
    rc, out = lab.run("auto")
    check("auto is quiet when nothing changes", rc == 0 and out.strip() == "", out)

    # ---- the text is improved later when it can be found; a text the person wrote is never touched
    Api.DATA["/v2/repositories/nobody/plainapp"] = {"description": "Finally found"}
    t = lab.svc().replace("description: Movies, shows and music server", "description: My own words")
    open(os.path.join(lab.hp, "services.yaml"), "w").write(t)
    rc, out = lab.run("auto")
    check("a plain note is replaced once a better text exists", "description: Finally found" in lab.svc() and "Added automatically (stackname)" not in lab.svc(), lab.svc())
    check("a text written by the person stays", "description: My own words" in lab.svc())

    # ---- the address changes
    lab.lan = "10.0.0.5"
    rc, out = lab.run("auto")
    check("a new local address is written into every card it made", "siteMonitor: http://10.0.0.5:%d" % p_jelly in lab.svc() and "192.168.1.198:%d" % p_jelly not in lab.svc(), lab.svc())
    check("the hand written cards are left alone", "siteMonitor: http://192.168.1.198:%d" % 8185 in lab.svc())
    open(lab.name, "w").write("newname.example.ts.net")
    lab.run("auto")
    check("a new Tailscale name is written into the links", "https://newname.example.ts.net:101" in lab.svc().split("id: jellyfin-card")[1].split("\n\n")[0], lab.svc())
    lab.lan = "192.168.1.198"
    open(lab.name, "w").write("homelab.example.ts.net")
    lab.run("auto")
    open(lab.down, "w").write("1")
    lab.run("auto")
    check("while Tailscale does not answer the links stay as they are", "https://homelab.example.ts.net:101" in lab.svc().split("id: jellyfin-card")[1].split("\n\n")[0])
    os.remove(lab.down)

    # ---- moving, ignoring
    rc, out = lab.run("move", "zzzapp", "files")
    g = groups(lab.svc())
    check("move puts the card in the other section", rc == 0 and "zzzapp-card" in g["Files & Photos"] and "zzzapp-card" not in g["Monitoring & Management"], out + str(g))
    check("the moved card is valid YAML and no longer unsure", valid(lab.svc()) and not lab.state()["managed"]["zzzapp"]["unsure"])
    lab.run("auto")
    check("a later look keeps it where it was moved", "zzzapp-card" in groups(lab.svc())["Files & Photos"])
    rc, out = lab.run("move", "metube", "files")
    check("a hand written card cannot be moved by this command", rc != 0 and "not a card this command made" in out, out)
    rc, out = lab.run("move", "zzzapp", "nonsense")
    check("an unknown section is refused", rc != 0 and "not one of the sections" in out, out)
    rc, out = lab.run("ignore", "jellyfin")
    css = lab.css()
    check("ignore removes the card, its colour and its address", "jellyfin-card" not in lab.svc() and "jellyfin-card" not in css
          and ports != sorted(int(k.split(":")[1]) for k in json.load(open(lab.ts))["Web"]), out)
    check("the lists in custom.css are still well formed after a removal", css.count("{") == css.count("}") and valid(lab.svc()))
    lab.run("auto")
    check("an ignored service gets no card again", "jellyfin-card" not in lab.svc())
    lab.run("unignore", "jellyfin")
    lab.run("auto")
    check("unignore lets it come back", "jellyfin-card" in lab.svc())

    # ---- a service that is deleted
    lab.set_containers([c for c in lab.cs if c["Name"] != "/paperless"])
    lab.run("auto")
    check("one look with the container gone keeps the card (a redeploy takes a moment)", "paperless-card" in lab.svc())
    lab.run("auto")
    check("the second look removes the card", "paperless-card" not in lab.svc() and "paperless-card" not in lab.css() and "paperless" not in lab.state()["managed"])
    check("the other cards stay", "jellyfin-card" in lab.svc() and valid(lab.svc()))

    # ---- the person deletes a card by hand
    t = lab.svc()
    r0 = t.index("    - Zzzapp:")
    r1 = t.index("\n\n", r0) if "\n\n" in t[r0:] else len(t)
    open(os.path.join(lab.hp, "services.yaml"), "w").write(t[:r0] + t[r1 + 2:])
    rc, out = lab.run("sync")
    check("a card removed by hand is respected: the service is ignored", "zzzapp-card" not in lab.svc() and "zzzapp" in lab.state()["ignore"] and "you removed it" in out, out)

    # ---- check and list
    rc, out = lab.run("check")
    check("check reports each card", "ok: the card Jellyfin is in order" in out, out)
    rc, out = lab.run("list")
    check("list shows the cards and the services waiting", "Jellyfin" in out and "Ignored: zzzapp" in out, out)
    lab.set_containers([c for c in lab.cs if c["Name"] != "/jellyfin"] + [container("jellyfin", "lscr.io/linuxserver/jellyfin", p_jelly, status="exited")])
    rc, out = lab.run("check")
    check("check warns about a card whose service is not running", "warn: jellyfin (card Jellyfin) is not running" in out, out)
    open(os.path.join(lab.hp, "services.yaml"), "w").write("- Broken: [unclosed\n")
    rc, out = lab.run("sync")
    if yaml:
        check("a broken services.yaml is left alone", rc != 0 and "not valid YAML" in out and lab.svc() == "- Broken: [unclosed\n", out)
finally:
    lab.close()

# ---------------------------------------------------------------- 2. a fresh machine: the shipped files, no Media section yet, Tailscale not ready
lab = Lab(SHIPPED_SVC, SHIPPED_CSS)
try:
    # the shipped file may be the owner's current version: make sure it is valid for this part
    port = lab.web()
    lab.set_containers([container("jellyfin", "lscr.io/linuxserver/jellyfin", port)])
    open(lab.down, "w").write("1")
    rc, out = lab.run()
    svc = lab.svc()
    g = groups(svc)
    check("the Media & Entertainment section is created when it is missing", "jellyfin-card" in g.get("Media & Entertainment", []), svc[-500:])
    check("without Tailscale the card uses the local address and says so", "href: http://192.168.1.198:%d" % port in svc and "No Tailscale HTTPS address yet" in out, out)
    check("the shipped custom.css lists get the new card", re.search(r"#jellyfin-card::before\s*[,{]", lab.css()) and "#jellyfin-card { --accent:" in lab.css())
    os.remove(lab.down)
    lab.run("auto")
    check("when Tailscale is ready the link becomes the HTTPS address", re.search(r"href: https://homelab\.example\.ts\.net:\d+", svc_after := lab.svc()) is not None, svc_after[-400:])
    lab.set_containers([])
    lab.run("auto")
    lab.run("auto")
    check("when the only card of a section goes, the section goes too", "Media & Entertainment" not in groups(lab.svc()) and "jellyfin-card" not in lab.css() and valid(lab.svc()), lab.svc()[-300:])
    check("the rest of the shipped file is unchanged", lab.svc().rstrip() == open(SHIPPED_SVC).read().rstrip() or yaml is None, "")
finally:
    lab.close()

# ---------------------------------------------------------------- 3. a custom.css without the lists: the colour line still goes in, nothing breaks
lab = Lab(LIVE_SVC, LIVE_CSS)
try:
    open(os.path.join(lab.hp, "custom.css"), "w").write("/* mine */\n.service-card { color: red; }\n")
    port = lab.web()
    lab.set_containers([container("jellyfin", "lscr.io/linuxserver/jellyfin", port)])
    lab.run()
    css = lab.css()
    check("a css file without the lists gets the colour line at the end", css.startswith("/* mine */") and "#jellyfin-card { --accent: 170, 92, 195; }" in css, css)
finally:
    lab.close()

# ---------------------------------------------------------------- 4. words
rc = subprocess.run([sys.executable, PROG, "version"], capture_output=True, text=True).stdout
check("version prints", rc.startswith("homelab-cards "))
h = subprocess.run([sys.executable, PROG, "help"], capture_output=True, text=True).stdout
check("help mentions the four sections and move", "Network & DNS" in h and "homelab-cards move" in h)

print("OK" if bad == 0 else "FAIL")
sys.exit(1 if bad else 0)
