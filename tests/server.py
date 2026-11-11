#!/usr/bin/env python3
"""Fake web services for the homelab-setup simulation. They only answer while their container is 'running'."""
import base64
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(__file__))
from simlib import World, deploy_stack, event, hostpath, running  # noqa

NC_DELAY = int(os.environ.get("SIM_NC_DELAY", "3"))
NC_TOKEN_LAG = int(os.environ.get("SIM_NC_TOKEN_LAG", "0"))   # a token that was only just set is refused this many times (Nextcloud caches the old one for a while)
BESZEL_MODE = os.environ.get("SIM_BESZEL_CREATE", "confirm")     # confirm | plain | never
PORTAINER_NO_LOCAL = os.environ.get("SIM_PORTAINER_NO_LOCAL") == "1"


class H(BaseHTTPRequestHandler):
    svc = ""
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    # --- helpers
    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode() if n else ""
        ct = self.headers.get("Content-Type", "")
        if "json" in ct:
            try:
                return json.loads(raw)
            except ValueError:
                return {}
        if "multipart" in ct:
            return dict(re.findall(r'name="([^"]+)"\r\n\r\n(.*?)\r\n--', raw, re.S))
        return raw

    def send(self, code, data=None, ctype="application/json"):
        if data is None:
            payload = b""
        elif isinstance(data, (dict, list)):
            payload = json.dumps(data).encode()
        else:
            payload = str(data).encode()
            if ctype == "application/json":
                ctype = "text/plain"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def basic(self):
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                u, _, p = base64.b64decode(h[6:]).decode().partition(":")
                return u, p
            except Exception:
                pass
        return None, None

    def handle_any(self, method):
        u = urllib.parse.urlparse(self.path)
        path, q = u.path, dict(urllib.parse.parse_qsl(u.query))
        body = self.body() if method in ("POST", "PUT") else {}
        with World() as w:
            names = {"portainer": ["portainer"], "adguard": ["adguardhome"], "immich": ["immich_server"],
                     "beszel": ["beszel"], "nextcloud": ["nextcloud"], "speedtest": ["speedtest-tracker"],
                     "filebrowser": ["filebrowser-filebrowser-1"], "netdata": ["netdata-netdata-1"], "navidrome": ["navidrome"], "audiomuse": ["audiomuse-flask"], "navilist": ["navilist"],
                     "tsapi": [], "homepage": ["homepage"]}[self.svc]
            if names and not all(running(w, n) for n in names):
                return self.send(502, "not running")
            fn = getattr(self, "s_" + self.svc)
            return fn(w, method, path, q, body)

    do_GET = lambda self: self.handle_any("GET")
    do_POST = lambda self: self.handle_any("POST")
    do_PUT = lambda self: self.handle_any("PUT")
    do_DELETE = lambda self: self.handle_any("DELETE")

    # --- Portainer
    def s_portainer(self, w, m, path, q, b):
        P = w["portainer"]
        if path == "/api/status":
            return self.send(200, {"Version": "2.33.0"})
        if path == "/api/users/admin/check":
            if P["admin"]:
                return self.send(204)
            return self.send(303 if P["window_closed"] else 404)
        if path == "/api/users/admin/init" and m == "POST":
            if P["admin"]:
                return self.send(409, {"message": "An administrator user already exists"})
            if P["window_closed"]:
                return self.send(403, {"message": "timed out"})
            if P["setup_token"] and self.headers.get("X-Setup-Token", "") != P["setup_token"]:
                return self.send(403, {"message": "Invalid or missing setup token. Provide the X-Setup-Token header with the token printed in the server logs at startup.", "details": "Invalid or missing setup token"})
            if len(b.get("Password", "")) < 12:
                return self.send(400, {"message": "Invalid user data", "details": "Password must be at least 12 characters"})
            P["admin"], P["pw"] = b["Username"], b["Password"]
            if not PORTAINER_NO_LOCAL:
                P["endpoints"].append({"Id": 1, "Name": "local"})
            event(w, "portainer admin created")
            return self.send(200, {"Id": 1, "Username": b["Username"]})
        if path == "/api/auth" and m == "POST":
            if P["admin"] == b.get("Username") and P["pw"] == b.get("Password"):
                P["jwt"] = "jwt-" + secrets.token_hex(8)
                return self.send(200, {"jwt": P["jwt"]})
            return self.send(422, {"message": "Invalid credentials"})
        auth = self.headers.get("Authorization", "")
        key = self.headers.get("X-API-Key", "")
        ok = (auth == "Bearer " + str(P["jwt"]) and P["jwt"]) or key in P["tokens"]
        if not ok:
            return self.send(401, {"message": "Unauthorized"})
        if path == "/api/users/me":
            return self.send(200, {"Id": 1, "Username": P["admin"], "Role": 1})
        if path == "/api/users/1/tokens" and m == "POST":
            if b.get("password") != P["pw"]:
                return self.send(400, {"message": "Invalid password"})
            tok = "ptr_" + secrets.token_urlsafe(30)
            P["tokens"][tok] = b.get("description", "")
            return self.send(201, {"rawAPIKey": tok, "apiKey": {"id": len(P["tokens"])}})
        if path == "/api/endpoints" and m == "GET":
            return self.send(200, P["endpoints"])
        if path == "/api/endpoints" and m == "POST":
            nid = len(P["endpoints"]) + 1
            P["endpoints"].append({"Id": nid, "Name": b.get("Name", "local")})
            return self.send(200, {"Id": nid})
        mm = re.fullmatch(r"/api/endpoints/(\d+)", path)
        if mm:
            return self.send(200, {"Id": int(mm.group(1))}) if any(e["Id"] == int(mm.group(1)) for e in P["endpoints"]) else self.send(404)
        if path == "/api/stacks" and m == "GET":
            return self.send(200, P["stacks"])
        if path == "/api/stacks/create/standalone/string" and m == "POST":
            if not any(str(e["Id"]) == q.get("endpointId") for e in P["endpoints"]):
                return self.send(400, {"message": "bad endpoint"})
            if any(s["Name"] == b.get("name") for s in P["stacks"]):
                return self.send(409, {"message": "A stack with this name already exists"})
            ok, msg = deploy_stack(w, b["name"], b["stackFileContent"], b.get("env") or [])
            if not ok:
                return self.send(500, {"message": "Unable to deploy", "details": msg})
            P["stacks"].append({"Id": len(P["stacks"]) + 1, "Name": b["name"], "EndpointId": int(q["endpointId"]), "Status": 1,
                                "Env": b.get("env") or [], "Text": b["stackFileContent"]})
            event(w, "stack created: " + b["name"])
            return self.send(200, {"Id": len(P["stacks"]), "Name": b["name"]})
        mm = re.fullmatch(r"/api/stacks/(\d+)", path)
        if mm and m == "PUT":
            st = next((s for s in P["stacks"] if s["Id"] == int(mm.group(1))), None)
            if not st:
                return self.send(404)
            ok, msg = deploy_stack(w, st["Name"], b["stackFileContent"], b.get("env") or [])
            if not ok:
                return self.send(500, {"message": "Unable to deploy", "details": msg})
            st["Text"] = b["stackFileContent"]
            event(w, "stack updated: " + st["Name"])
            return self.send(200, st)
        mm = re.fullmatch(r"/api/stacks/(\d+)", path)
        if mm and m == "DELETE":
            st = next((s for s in P["stacks"] if s["Id"] == int(mm.group(1))), None)
            if not st:
                return self.send(404)
            for cn in [c for c, v in w["containers"].items() if v.get("stack") == st["Name"]]:
                del w["containers"][cn]
            P["stacks"].remove(st)
            event(w, "stack deleted: " + st["Name"])
            return self.send(204)
        mm = re.fullmatch(r"/api/stacks/(\d+)/file", path)
        if mm and m == "GET":
            st = next((s for s in P["stacks"] if s["Id"] == int(mm.group(1))), None)
            return self.send(200, {"StackFileContent": st.get("Text", "")}) if st else self.send(404)
        return self.send(404, {"message": "no such route " + path})

    # --- AdGuard Home
    def s_adguard(self, w, m, path, q, b):
        A = w["adguard"]
        yml = hostpath("/opt/adguard-docker/conf/AdGuardHome.yaml")
        if path == "/control/install/configure" and m == "POST":
            if A["configured"]:
                return self.send(403, "already configured")
            if b.get("web", {}).get("port") != 3000 or b.get("dns", {}).get("port") != 53:
                return self.send(400, "wrong ports")
            if len(b.get("password", "")) < 8:
                return self.send(422, "password too weak")
            A.update(configured=True, user=b["username"], pw=b["password"])
            os.makedirs(os.path.dirname(yml), exist_ok=True)
            open(yml, "w").write("http:\n  address: 0.0.0.0:3000\nusers:\n  - name: %s\n    password: $2a$10$fakehash\n"
                                 "dns:\n  upstream_dns:\n    - https://dns10.quad9.net/dns-query\n"
                                 "filters:\n  - enabled: true\n    url: https://adguardteam.github.io/hostlists/adguard.txt\n    name: AdGuard DNS filter\n    id: 1\n"
                                 "  - enabled: false\n    url: https://adaway.org/hosts.txt\n    name: AdAway Default Blocklist\n    id: 2\n"
                                 "whitelist_filters: []\nuser_rules: []\n" % b["username"])
            return self.send(200, {})
        if not A["configured"]:
            return self.send(404, "install mode")
        u, p = self.basic()
        if (u, p) != (A.get("user"), A.get("pw")):
            return self.send(401, "Unauthorized")
        if path == "/control/status":
            return self.send(200, {"running": True, "version": "v0.107.79"})
        if path == "/control/stats":
            return self.send(200, {"num_dns_queries": 5, "top_clients": A.get("clients", [])})
        if path == "/control/filtering/status":
            txt = open(yml).read()
            fl = [{"enabled": e == "true", "url": u, "name": n, "id": int(i)}
                  for e, u, n, i in re.findall(r"  - enabled: (\w+)\n    url: (.*)\n    name: (.*)\n    id: (\d+)\n", txt)]
            return self.send(200, {"enabled": True, "interval": 24, "filters": fl, "whitelist_filters": [], "user_rules": []})
        if path == "/control/filtering/add_url" and m == "POST":
            txt = open(yml).read()
            if b.get("url") in txt:
                return self.send(400, "filter with this URL already exists")
            if A.get("filter_fail"):
                return self.send(500, "could not download the list")
            nid = max([int(i) for i in re.findall(r"    id: (\d+)\n", txt)] or [0]) + 1
            entry = "  - enabled: true\n    url: %s\n    name: %s\n    id: %d\n" % (b["url"], b["name"], nid)
            txt = txt.replace("whitelist_filters:", entry + "whitelist_filters:", 1)
            open(yml, "w").write(txt)
            return self.send(200, "OK: 1000 rules added")
        if path == "/control/filtering/set_url" and m == "POST":
            txt = open(yml).read()
            d = b.get("data", {})
            txt = re.sub(r"(  - enabled: )\w+(\n    url: %s\n)" % re.escape(b.get("url", "")),
                         lambda x: x.group(1) + ("true" if d.get("enabled") else "false") + x.group(2), txt)
            open(yml, "w").write(txt)
            return self.send(200, "OK")
        if path == "/control/dns_config" and m == "POST":
            txt = open(yml).read()
            txt = re.sub(r"upstream_dns:\n(    - .*\n)+", "upstream_dns:\n" + "".join("    - %s\n" % x for x in b.get("upstream_dns", [])), txt)
            open(yml, "w").write(txt)
            return self.send(200, {})
        return self.send(404, "no route")

    # --- Homepage
    def s_homepage(self, w, m, path, q, b):
        return self.send(200, "<html>Homepage</html>", "text/html")

    # --- Immich
    def s_immich(self, w, m, path, q, b):
        I = w["immich"]
        if path == "/api/server/ping":
            return self.send(200, {"res": "pong"})
        if path == "/api/server/config":
            if I.get("down_config", 0) > 0:      # still starting after a reboot: the first answers are errors
                I["down_config"] -= 1
                return self.send(503, {"message": "starting"})
            return self.send(200, {"isInitialized": bool(I["user"])})
        if path == "/api/auth/admin-sign-up" and m == "POST":
            if I["user"]:
                return self.send(400, {"message": "The server already has an admin"})
            I["user"] = {"email": b["email"], "pw": b["password"], "name": b["name"]}
            return self.send(201, {"email": b["email"]})
        if path == "/api/auth/login" and m == "POST":
            if I["user"] and I["user"]["email"] == b.get("email") and I["user"]["pw"] == b.get("password"):
                I["token"] = "imtok-" + secrets.token_hex(6)
                return self.send(201, {"accessToken": I["token"], "isAdmin": True})
            return self.send(401, {"message": "Incorrect email or password"})
        if path == "/api/system-config":
            if self.headers.get("Authorization") != "Bearer " + str(I.get("token")):
                return self.send(401, {"message": "Unauthorized"})
            cfg = I.setdefault("config", {"machineLearning": {"enabled": True, "ocr": {"enabled": True, "modelName": "PP-OCRv5_mobile"}}, "trash": {"enabled": True}})
            if m == "PUT":
                I["config"] = b
                return self.send(200, b)
            return self.send(200, cfg)
        if path == "/api/api-keys" and m == "POST":
            if self.headers.get("Authorization") != "Bearer " + str(I.get("token")):
                return self.send(401, {"message": "Unauthorized"})
            if not b.get("permissions"):
                return self.send(400, {"message": "permissions required"})
            sec = "imkey-" + secrets.token_urlsafe(24)
            I["keys"][sec] = b.get("permissions")
            return self.send(201, {"secret": sec, "apiKey": {"name": b.get("name")}})
        if path == "/api/server/statistics":
            perms = I["keys"].get(self.headers.get("x-api-key", ""))
            if perms and ("all" in perms or "server.statistics" in perms):
                return self.send(200, {"photos": 0, "videos": 0, "usage": 0})
            return self.send(401, {"message": "Invalid API key"})
        return self.send(404)

    # --- Beszel
    def s_beszel(self, w, m, path, q, b):
        Z = w["beszel"]
        if path == "/api/beszel/first-run":
            return self.send(200, {"firstRun": not Z["users"]})
        if path == "/api/beszel/create-user" and m == "POST":
            if Z["users"] or BESZEL_MODE == "never":
                return self.send(404 if Z["users"] else 400, {"message": "nope"})
            if BESZEL_MODE == "confirm" and "passwordConfirm" not in b:
                return self.send(400, {"message": "passwordConfirm required"})
            Z["users"][b["email"]] = b["password"]
            return self.send(200, {})
        if path == "/api/collections/users/auth-with-password" and m == "POST":
            if Z["users"].get(b.get("identity")) == b.get("password"):
                tok = "bz-" + secrets.token_hex(6)
                Z["token"] = tok
                return self.send(200, {"token": tok})
            return self.send(400, {"message": "Failed to authenticate."})
        if path in ("/api/collections/_superusers/auth-with-password", "/api/admins/auth-with-password") and m == "POST":
            if path.endswith("admins/auth-with-password"):
                return self.send(404)
            if Z["superusers"].get(b.get("identity")) == b.get("password"):
                return self.send(200, {"token": "su-" + secrets.token_hex(4)})
            return self.send(400, {"message": "Failed to authenticate."})
        if self.headers.get("Authorization") != Z.get("token"):
            return self.send(401)
        if path == "/api/beszel/info":
            return self.send(200, {"key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAISIMKEY", "v": "0.21.0"})
        if path == "/api/beszel/universal-token":
            Z["universal"] = q.get("token")
            return self.send(200, {"token": q.get("token"), "active": True, "permanent": True})
        return self.send(404)

    # --- Nextcloud
    def s_nextcloud(self, w, m, path, q, b):
        N = w["nc"]
        if path == "/status.php":
            N["calls"] += 1
            return self.send(200, {"installed": N["calls"] > NC_DELAY, "version": "35.0.2.2"})
        if path.startswith("/ocs/v2.php/apps/serverinfo/api/v1/info"):
            if N["token"] and self.headers.get("NC-Token") == N["token"]:
                N["seen"] = N.get("seen", 0) + 1
                if N["seen"] <= NC_TOKEN_LAG:
                    return self.send(401, {"ocs": {"meta": {"statuscode": 401}}})
                return self.send(200, {"ocs": {"meta": {"statuscode": 200}, "data": {}}})
            return self.send(401, {"ocs": {"meta": {"statuscode": 401}}})
        return self.send(404)

    # --- Speedtest Tracker
    def s_speedtest(self, w, m, path, q, b):
        if w["speedtest"].get("down"):                  # busy or restarting: every request fails
            return self.send(503, {"message": "Service Unavailable"})
        if path == "/api/v1/results/latest":
            tok = self.headers.get("Authorization", "").replace("Bearer ", "")
            if tok in w["speedtest"]["tokens"]:
                if w["speedtest"].get("results", 0) > 0:
                    return self.send(200, {"data": {"id": 1, "download": 554640000}, "message": "ok"})
                return self.send(404, {"message": "No results found"})
            return self.send(401, {"message": "Unauthenticated."})
        return self.send(404)

    # --- FileBrowser
    def s_filebrowser(self, w, m, path, q, b):
        F = w["fb"]
        if path == "/api/login" and m == "POST":
            if b.get("username") == F["user"] and b.get("password") == F["pw"]:
                F["tok"] = "fbtok-" + secrets.token_hex(5)
                return self.send(200, F["tok"], "text/plain")
            return self.send(403, "Forbidden")
        if self.headers.get("X-Auth") != F.get("tok"):
            return self.send(401)
        if path == "/api/users/1":
            if m == "GET":
                return self.send(200, {"id": 1, "username": F["user"], "password": "", "scope": "."})
            if m == "PUT":
                if b.get("current_password") != F["pw"]:
                    return self.send(400, "Bad Request", "text/plain")
                d = b["data"]
                F["user"] = d["username"]
                if d.get("password"):
                    F["pw"] = d["password"]
                return self.send(200, {})
        return self.send(404)

    # --- Navidrome: the first admin is made through /auth/createAdmin (403 once there is one), then /auth/login
    def s_navidrome(self, w, m, path, q, b):
        N = w["navidrome"]
        if path == "/" and m == "GET":
            return self.send(200, "<html>Navidrome</html>", "text/html")
        if path == "/auth/createAdmin" and m == "POST":
            if N["user"]:
                return self.send(403, {"error": "admin exists"})
            N["user"], N["pw"] = b.get("username"), b.get("password")
            return self.send(200, {"username": N["user"], "isAdmin": True})
        if path == "/auth/login" and m == "POST":
            if N["user"] and b.get("username") == N["user"] and b.get("password") == N["pw"]:
                return self.send(200, {"username": N["user"], "isAdmin": True, "token": "ndtoken-admin"})
            if N.get("users", {}).get(b.get("username")) == b.get("password") and b.get("password"):
                return self.send(200, {"username": b["username"], "isAdmin": False, "token": "ndtoken-user"})
            return self.send(401, {"error": "Invalid username or password"})
        if path == "/api/user" and m == "POST":
            if self.headers.get("X-ND-Authorization") != "Bearer ndtoken-admin":
                return self.send(401, {"error": "not logged in as admin"})
            if b.get("userName") in N.setdefault("users", {}) or b.get("userName") == N["user"]:
                return self.send(400, {"errors": {"userName": "ra.validation.unique"}})
            N["users"][b["userName"]] = b.get("password")
            return self.send(200, {"id": "u-" + b["userName"]})
        return self.send(404)

    # --- AudioMuse-AI: /api/health is open, the rest wants the bearer token the installer saved
    def s_audiomuse(self, w, m, path, q, b):
        if path == "/api/health":
            return self.send(200, {"status": "ok"})
        want = (w.get("stack_env", {}).get("audiomuse") or {}).get("AUDIOMUSE_TOKEN", "")
        if path == "/api/last_task":
            return self.send(200, {"status": "NO_PREVIOUS_MAIN_TASK"}) if want and self.headers.get("Authorization") == "Bearer " + want else self.send(401)
        return self.send(200, "<html>AudioMuse-AI</html>", "text/html") if path == "/" else self.send(404)

    # --- naviList: keeps its settings, answers the library sync and the ListenBrainz / Last.fm playlist routes
    #     (the file $SIM_DIR/navilist.lb means ListenBrainz has made the person's playlists already)
    def s_navilist(self, w, m, path, q, b):
        N = w.setdefault("navilist_app", {"settings": {}, "lb_subs": [], "lfm_subs": [], "library_syncs": 0})
        S = N["settings"]
        lb_on = os.path.exists(os.path.join(os.environ.get("SIM_DIR", os.path.join(os.environ.get("TMPDIR", "/tmp"), "homelab-sim")), "navilist.lb"))
        if path == "/health":
            return self.send(200, {"ok": True})
        if path == "/settings/api":
            return self.send(200, {"ok": True, "settings": S})
        if path == "/settings/test-navidrome" and m == "POST":
            for k in ("navidrome_url", "navidrome_user", "navidrome_password"):
                S[k] = b.get(k, "")
            good = w["navidrome"].get("users", {}).get(S["navidrome_user"]) == S["navidrome_password"] and S["navidrome_password"]
            return self.send(200, {"ok": True} if good else {"ok": False, "error": "Auth failed"})
        if path == "/settings" and m == "POST":
            S.update({k: v for k, v in b.items() if v is not None})
            return self.send(200, "<html>settings</html>", "text/html")
        if path == "/sync/library" and m == "POST":
            N["library_syncs"] += 1
            return self.send(200, {"ok": True, "message": "Sync started"})
        lb = [{"lb_mbid": "mbid-wj", "title": "Weekly Jams for tester", "playlist_type": "generated", "source_patch": "weekly-jams"},
              {"lb_mbid": "mbid-we", "title": "Weekly Exploration for tester", "playlist_type": "generated", "source_patch": "weekly-exploration"},
              {"lb_mbid": "mbid-mine", "title": "My road trip", "playlist_type": "user", "source_patch": None}] if lb_on else []
        if path == "/sync/lb-playlists" and m == "POST":
            if not S.get("listenbrainz_token") or not S.get("listenbrainz_username"):
                return self.send(200, {"ok": False, "error": "ListenBrainz credentials required"})
            return self.send(200, {"ok": True, "message": "LB playlists synced"})
        if path == "/sync/lb-playlists/cached":
            return self.send(200, {"ok": True, "playlists": [dict(p, enabled=1 if p["lb_mbid"] in N["lb_subs"] else 0) for p in lb]})
        mm = re.fullmatch(r"/sync/lb-playlists/([^/]+)/import", path)
        if mm and m == "POST":
            if mm.group(1) in N["lb_subs"]:
                return self.send(200, {"ok": False, "error": "Already subscribed"})
            N["lb_subs"].append(mm.group(1))
            return self.send(200, {"ok": True, "navidrome_id": "pl-" + mm.group(1)})
        lfm = [{"lfm_id": "weekly", "title": "Last.fm: This week"}, {"lfm_id": "top_7day", "title": "Last.fm: Top 7 days"},
               {"lfm_id": "top_1month", "title": "Last.fm: Top of the month"}]
        if path == "/sync/lfm-playlists" and m == "POST":
            if not S.get("lastfm_api_key") or not S.get("lastfm_username"):
                return self.send(200, {"ok": False, "error": "Last.fm credentials required"})
            N["lfm_known"] = True
            return self.send(200, {"ok": True})
        if path == "/sync/lfm-playlists/cached":
            return self.send(200, {"ok": True, "playlists": [dict(p, enabled=1 if p["lfm_id"] in N["lfm_subs"] else 0) for p in lfm] if N.get("lfm_known") else []})
        mm = re.fullmatch(r"/sync/lfm-playlists/([^/]+)/import", path)
        if mm and m == "POST":
            N["lfm_subs"].append(mm.group(1))
            return self.send(200, {"ok": True, "navidrome_id": "pl-" + mm.group(1)})
        return self.send(404)

    def s_netdata(self, w, m, path, q, b):
        if w.get("netdata_fail", 0) > 0:
            w["netdata_fail"] -= 1
            return self.send(503)
        return self.send(200, {"version": "2.0"}) if path == "/api/v1/info" else self.send(404)

    def s_tsapi(self, w, m, path, q, b):
        if path == "/v1/search":
            name = q.get("name", "")
            cities = {"new york": [{"name": "New York", "admin1": "New York", "country": "United States", "latitude": 40.71427, "longitude": -74.00597}],
                      "springfield": [{"name": "Springfield", "admin1": "Illinois", "country": "United States", "latitude": 39.80172, "longitude": -89.64371},
                                      {"name": "Springfield", "admin1": "Massachusetts", "country": "United States", "latitude": 42.10148, "longitude": -72.58981}],
                      "queens": [{"name": "Queens", "admin1": "New York", "country": "United States", "latitude": 40.68149, "longitude": -73.83652}]}
            r = cities.get(name.strip().lower())
            return self.send(200, {"results": r} if r else {"generationtime_ms": 0.5})
        u, p = self.basic()
        if u == w["ts_api_key"] and re.fullmatch(r"/api/v2/device/nTESTCNTRL", path):
            return self.send(200, {"id": "nTESTCNTRL"})
        return self.send(401)


PORTS = {"portainer": 9000, "adguard": 3000, "immich": 2283, "beszel": 8090, "nextcloud": 8082,
         "speedtest": 8088, "filebrowser": 8081, "netdata": 19999, "tsapi": 9999, "homepage": 3001, "navidrome": 4533, "audiomuse": 8100, "navilist": 8200}


def main():
    bind = os.environ.get("HLS_HOST", "127.0.0.1")
    servers = []
    for svc, port in PORTS.items():
        cls = type("H_" + svc, (H,), {"svc": svc})
        srv = ThreadingHTTPServer((bind, port), cls)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
    open(os.environ.get("SIM_DIR", os.path.join(os.environ.get("TMPDIR", "/tmp"), "homelab-sim")) + "/server.ready", "w").write("ok")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
