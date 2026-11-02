#!/usr/bin/env python3
"""Fakes for testing scripts/homelab-update: a Docker command, a registry and Portainer. Nothing real is touched.

  fakeupd.py docker ARGS...      the docker command (state in $FAKE_DIR/state.json)
  fakeupd.py registry PORT       registry: /v2/<repo>/tags/list (token login, two pages) from state["tags"]
  fakeupd.py portainer PORT      Portainer: stacks, stack files, redeploy (changes the fake containers)
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

D = os.environ.get("FAKE_DIR", ".")
SF = os.path.join(D, "state.json")


def load():
    return json.load(open(SF))


def save(st):
    json.dump(st, open(SF, "w"), indent=1)


def img_id(st, ref):
    return st["images"].get(ref, {}).get("id")


def cname(st, ident):
    for n, c in st["containers"].items():
        if ident in (n, c["id"]):
            return n
    return None


def docker(a):
    st = load()
    with open(os.path.join(D, "docker.log"), "a") as lg:
        lg.write(" ".join(a) + "\n")
    cmd = a[0]
    if cmd == "ps":
        flt = [x for x in a if x.startswith("label=com.docker.compose.project=")]
        names = [n for n, c in st["containers"].items() if not flt or c["stack"] == flt[0].split("=")[-1]]
        if "-q" in a or "-aq" in a:
            print("\n".join(st["containers"][n]["id"] for n in names))
        else:
            print("\n".join(names))
        return 0
    if cmd == "inspect":
        fmt = a[a.index("--format") + 1] if "--format" in a else ""
        ids = [x for x in a[1:] if not x.startswith("-") and x != fmt]
        for i in ids:
            n = cname(st, i)
            if n is None:
                return 1
            c = st["containers"][n]
            if "compose.project" in fmt:
                print("%s|/%s|%s|%s|%s" % (c["id"], n, c["image"], c["imgid"], c["stack"]))
            elif ".State.Status" in fmt:
                print("%s %s" % (c.get("state", "running"), c.get("health", "none")))
            elif ".Mounts" in fmt:
                for v in c.get("anon", []):
                    print("%s %s" % ("a" * 64, v))
            elif "RestartPolicy" in fmt or "PortBindings" in fmt or ".Args" in fmt:
                print(c.get("run", ""))
        return 0
    if cmd == "image" and a[1] == "inspect":
        ref = a[-1]
        im = st["images"].get(ref)
        if im is None:
            return 1
        if "RepoDigests" in " ".join(a):
            for d in im.get("digests", []):
                print(d)
        elif "{{.Id}}" in " ".join(a):
            print(im["id"])
        elif "org.opencontainers" in " ".join(a):
            print(im.get("version", "<no value>"))
        return 0
    if cmd == "buildx":
        ref = a[-1]
        d = st["remote"].get(ref)
        if not d:
            return 1
        print("Name: %s\nDigest: %s" % (ref, d))
        return 0
    if cmd == "pull":
        ref = a[1]
        r = st["remote"].get(ref) or st["remote_tags"].get(ref)
        if not r:
            print("Error: not found", file=sys.stderr)
            return 1
        st["images"][ref] = {"id": "sha256:id-" + ref.replace("/", "_").replace(":", "_") + "-" + r[-6:], "digests": ["x@" + r]}
        save(st)
        print("Status: Downloaded newer image for " + ref)
        return 0
    if cmd == "tag":
        return 0
    if cmd == "info":
        return 0
    if cmd == "exec":
        n = a[1]
        rest = a[2:]
        if rest[0] == "printenv":
            print({"POSTGRES_USER": "dbuser", "POSTGRES_DB": "dbname"}.get(rest[1], ""))
            return 0
        if rest[0] == "pg_dump":
            if st.get("dump_fails"):
                return 1
            print("-- dump of %s\n%s" % (n, "x" * 400))
            return 0
        if rest[0] == "cat":
            print("$OC_VersionString = '%s';" % st.get("nc_old", "35.0.1"))
            return 0
        return 1
    if cmd == "run":
        if "--entrypoint" in a:
            print("$OC_VersionString = '%s';" % st.get("nc_new", "35.0.2"))
            return 0
        return 0
    if cmd in ("stop", "rename", "rm", "start", "image-rm"):
        return 0
    return 0


def deploy(st, name, text):
    """What 'Update the stack' does: containers whose image: line changed get the new image."""
    refs = re.findall(r"^\s*image:\s*(\S+)", text, re.M)
    for _n, c in st["containers"].items():
        if c["stack"] != name:
            continue
        for r in refs:
            if r.rsplit(":", 1)[0] == c["image"].rsplit(":", 1)[0] or r == c["image"]:
                if r in st["images"] and (r != c["image"] or c.get("imgid") != st["images"][r]["id"]):
                    c["image"] = r
                    c["imgid"] = st["images"][r]["id"]
                    c["recreated"] = c.get("recreated", 0) + 1


class Portainer(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def ok(self):
        if self.headers.get("X-API-Key") != "good-key":
            self.send(401, {"message": "bad key"})
            return False
        return True

    def do_GET(self):
        if self.path == "/api/status":
            return self.send(200, {"Version": "2"})
        if not self.ok():
            return
        st = load()
        if self.path == "/api/stacks":
            return self.send(200, [{"Id": i + 1, "Name": n, "EndpointId": 1, "Env": s["env"]} for i, (n, s) in enumerate(st["stacks"].items())])
        m = re.match(r"/api/stacks/(\d+)/file", self.path)
        if m:
            name = list(st["stacks"])[int(m.group(1)) - 1]
            return self.send(200, {"StackFileContent": st["stacks"][name]["file"]})
        self.send(404, {})

    def do_PUT(self):
        if not self.ok():
            return
        st = load()
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        m = re.match(r"/api/stacks/(\d+)", self.path)
        name = list(st["stacks"])[int(m.group(1)) - 1]
        st["stacks"][name]["file"] = body["stackFileContent"]
        st["stacks"][name]["env_sent"] = body["env"]
        st.setdefault("puts", []).append(name)
        deploy(st, name, body["stackFileContent"])
        save(st)
        self.send(200, {})


class Registry(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/token"):
            raw = json.dumps({"token": "tok"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if self.headers.get("Authorization") != "Bearer tok":
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Bearer realm="http://127.0.0.1:%d/token",service="fake",scope="repository:x:pull"' % self.server.server_port)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        m = re.match(r"/v2/(.+)/tags/list", self.path)
        tags = load()["tags"].get(m.group(1), []) if m else []
        page2 = "last=" in self.path
        part = tags[len(tags) // 2:] if page2 else tags[:len(tags) // 2 or len(tags)]
        raw = json.dumps({"name": m.group(1) if m else "", "tags": part}).encode()
        self.send_response(200)
        if not page2 and len(tags) > 1:
            self.send_header("Link", '</v2/%s/tags/list?n=1000&last=x>; rel="next"' % m.group(1))
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    if sys.argv[1] == "docker":
        sys.exit(docker(sys.argv[2:]))
    cls = Portainer if sys.argv[1] == "portainer" else Registry
    HTTPServer(("127.0.0.1", int(sys.argv[2])), cls).serve_forever()
