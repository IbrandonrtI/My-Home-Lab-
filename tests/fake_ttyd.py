#!/usr/bin/env python3
"""A stand-in for ttyd for the panel's tests: listens on a socket file like ttyd does and answers
  GET /terminal/        a small page (with an inline script, like ttyd's)
  GET /terminal/token   {"token": ""}
  GET /terminal/ws      the WebSocket handshake (101), then every byte it receives is sent back (an echo)
Run: fake_ttyd.py SOCKETFILE"""
import base64
import hashlib
import os
import socketserver
import sys

MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class H(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline().decode("latin-1").strip()
        hdr = {}
        while True:
            l = self.rfile.readline().decode("latin-1").strip()
            if not l:
                break
            k, _, v = l.partition(":")
            hdr[k.strip().lower()] = v.strip()
        path = line.split(" ")[1] if line.count(" ") >= 2 else ""
        if hdr.get("upgrade", "").lower() == "websocket" and path.startswith("/terminal/ws"):
            acc = base64.b64encode(hashlib.sha1((hdr.get("sec-websocket-key", "") + MAGIC).encode()).digest()).decode()
            self.wfile.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n"
                              "X-Seen-Host: %s\r\nX-Seen-Cookie: %s\r\nX-Seen-Origin: %s\r\n\r\n" % (acc, hdr.get("host", ""), hdr.get("cookie", ""), hdr.get("origin", ""))).encode())
            self.wfile.flush()
            while True:
                data = self.request.recv(4096)
                if not data:
                    return
                self.request.sendall(b"echo:" + data)
        if path == "/terminal/":
            body = b"<html><body>fake ttyd<script>var x=1;</script></body></html>"
            ctype = "text/html"
        elif path == "/terminal/token":
            body, ctype = b'{"token": ""}', "application/json"
        else:
            body, ctype = b"nope", "text/plain"
            self.wfile.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 4\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nnope")
            return
        self.wfile.write(("HTTP/1.1 200 OK\r\nContent-Length: %d\r\nContent-Type: %s\r\nX-Seen-Cookie: %s\r\nConnection: close\r\n\r\n" % (len(body), ctype, hdr.get("cookie", ""))).encode() + body)


class S(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


if __name__ == "__main__":
    sock = sys.argv[1]
    try:
        os.unlink(sock)
    except OSError:
        pass
    S(sock, H).serve_forever()
