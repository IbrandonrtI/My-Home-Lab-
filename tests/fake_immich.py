#!/usr/bin/env python3
"""A stand-in for Immich in tests (just the three calls the panel's Upload card makes). Keys: 'goodkey...' works, 'limitedkey...' may only upload
(users/me says 403), anything else is turned down. Uploaded files are kept in memory (FakeImmich.assets); the same bytes twice are a duplicate."""
import hashlib
import http.server
import json
import re
import threading


class FakeImmich:
    def __init__(self):
        self.assets = []
        self.seen = {}
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def reply(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def key_state(self):
                k = self.headers.get("x-api-key") or ""
                return "good" if k.startswith("goodkey") else "limited" if k.startswith("limitedkey") else "bad"

            def do_GET(self):
                if self.path == "/api/server/ping":
                    return self.reply(200, {"res": "pong"})
                if self.path == "/api/users/me":
                    st = self.key_state()
                    return self.reply(200, {"name": "Brandon", "email": "b@example.com"}) if st == "good" else self.reply(403 if st == "limited" else 401, {"message": "no"})
                self.reply(404, {"message": "not found"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n)
                if self.path != "/api/assets":
                    return self.reply(404, {"message": "not found"})
                if self.key_state() == "bad":
                    return self.reply(401, {"message": "Invalid API key"})
                ct = self.headers.get("Content-Type", "")
                m = re.search(r"boundary=(\S+)", ct)
                parts = body.split(("--" + m.group(1)).encode()) if m else []
                fields, data, filename = {}, b"", ""
                for part in parts:
                    if b"Content-Disposition" not in part:
                        continue
                    head, _, rest = part.partition(b"\r\n\r\n")
                    rest = rest[:-2] if rest.endswith(b"\r\n") else rest
                    nm = re.search(rb'name="([^"]+)"', head).group(1).decode()
                    if nm == "assetData":
                        data = rest
                        filename = re.search(rb'filename="([^"]*)"', head).group(1).decode()
                    else:
                        fields[nm] = rest.decode()
                digest = hashlib.sha1(data).hexdigest()
                outer.assets.append({"fields": fields, "filename": filename, "data": data, "key": self.headers.get("x-api-key")})
                if digest in outer.seen:
                    return self.reply(200, {"id": outer.seen[digest], "status": "duplicate"})
                outer.seen[digest] = "asset-%d" % len(outer.seen)
                self.reply(201, {"id": outer.seen[digest], "status": "created"})

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()
