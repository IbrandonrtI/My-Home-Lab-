#!/usr/bin/env python3
import http.server
import json
import os
import sys
import threading
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("skipped: Playwright is not installed")
    print("OK")
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, "..", "homepage-config", "custom.js")
CSS = os.path.join(HERE, "..", "homepage-config", "custom.css")

PAGE = b"""<!doctype html><html><head><style>ul{margin:0;padding:0;list-style:none}button{font:inherit}</style><link rel="stylesheet" href="/custom.css"></head><body>
<div id="inner_wrapper"><div class="container">
<div id="tabs"><ul id="myTab"><li><button id="Home-tab" aria-selected="true">Home</button></li><li><button id="Stats-tab" aria-selected="false">Stats</button></li><li><button id="Customize-tab" aria-selected="false">Customize</button></li></ul></div>
<div id="layout-groups"><div class="services-group"><div class="service-group-name">Group</div><ul class="services-list"><li class="service"><div class="service-card"><div class="service-title">A</div></div></li></ul></div></div>
</div></div><script src="/custom.js"></script></body></html>"""

STATUS = {"data": None}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        code = 200
        if path == "/custom.js":
            body, kind = open(JS, "rb").read(), "application/javascript"
        elif path == "/custom.css":
            body, kind = open(CSS, "rb").read(), "text/css"
        elif path == "/images/install-status.json":
            if STATUS["data"] is None:
                body, kind, code = b"{}", "application/json", 404
            else:
                body, kind = json.dumps(STATUS["data"]).encode(), "application/json"
        elif path == "/images/alerts.json":
            body, kind, code = b"{}", "application/json", 404
        else:
            body, kind = PAGE, "text/html"
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)


bad = 0


def check(name, cond, detail=""):
    global bad
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "   " + str(detail)))
    bad += not cond


def status(state, done, steps, updated=None):
    return {"state": state, "started": int(time.time()) - 300, "updated": int(time.time()) if updated is None else updated,
            "total": len(steps), "done": done, "now": "", "steps": steps}


RUN = [{"t": "System packages upgraded", "s": "done"}, {"t": "Immich stack", "s": "done"}, {"t": "Nextcloud finished its first install", "s": "now"},
       {"t": "Beszel hub account created", "s": "wait"}, {"t": "<img src=x onerror=window.__pwned=1>", "s": "wait"}]

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/" % srv.server_address[1]


def load(pg):
    pg.goto(URL)
    pg.locator("#hl-bell").wait_for()
    pg.wait_for_timeout(800)


try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_context(viewport={"width": 1000, "height": 800}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        load(pg)
        check("without a status file there is no ring", not pg.is_visible("#hl-install"))

        STATUS["data"] = status("running", 2, RUN)
        load(pg)
        check("while the install finishes, the ring is shown", pg.is_visible("#hl-install"))
        check("the ring sits right of the bell", pg.evaluate("document.getElementById('hl-bell').nextElementSibling.id") == "hl-install")
        check("there is only one ring", pg.evaluate("document.querySelectorAll('#hl-install').length") == 1)
        check("the ring says how many steps are done", pg.inner_text("#hl-install .hl-ring-n") == "2/5", pg.inner_text("#hl-install .hl-ring-n"))
        check("the ring is in the normal color while it runs", not pg.evaluate("document.getElementById('hl-install').classList.contains('hl-warn')"))
        arc = pg.get_attribute("#hl-install .hl-ring-arc", "stroke-dasharray")
        check("the arc is 2 of 5 of the circle", abs(float(arc.split()[0]) - 94.25 * 0.4) < 0.1, arc)
        check("the list is closed until the ring is pressed", not pg.is_visible("#hl-install .hl-bellpop"))
        pg.locator("#hl-install > button").click()
        pg.wait_for_timeout(200)
        check("pressing the ring opens the list", pg.is_visible("#hl-install .hl-bellpop") and pg.get_attribute("#hl-install > button", "aria-expanded") == "true")
        rows = pg.locator("#hl-install .hl-steprow")
        check("every step is a row", rows.count() == 5, rows.count())
        check("the running step is marked", "hl-st-now" in rows.nth(2).get_attribute("class") and "Nextcloud" in rows.nth(2).inner_text())
        check("a done step is marked", "hl-st-done" in rows.nth(0).get_attribute("class"))
        check("step names are shown as text, never as markup", pg.evaluate("window.__pwned") is None and "<img" in rows.nth(4).inner_text())
        check("the list says the terminal can be closed", "terminal can be closed" in pg.inner_text("#hl-install .hl-bellpop"))
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(100)
        check("Escape closes the list", not pg.is_visible("#hl-install .hl-bellpop"))
        pg.locator("#hl-bell > button").click()
        pg.wait_for_timeout(200)
        pg.locator("#hl-install > button").click()
        pg.wait_for_timeout(200)
        check("only one of the two lists is open at a time", pg.is_visible("#hl-install .hl-bellpop") and not pg.is_visible("#hl-bell .hl-bellpop"))
        pg.keyboard.press("Escape")

        STATUS["data"] = status("failed", 3, [{"t": "A", "s": "done"}, {"t": "B", "s": "done"}, {"t": "C", "s": "done"}, {"t": "FileBrowser widget login", "s": "failed"}, {"t": "E", "s": "wait"}])
        load(pg)
        check("after a failure the ring stays", pg.is_visible("#hl-install"))
        check("after a failure the ring turns amber", pg.evaluate("document.getElementById('hl-install').classList.contains('hl-warn')"))
        pg.locator("#hl-install > button").click()
        pg.wait_for_timeout(200)
        txt = pg.inner_text("#hl-install .hl-bellpop")
        check("the failed step is named and the command is given", "FileBrowser widget login" in txt and "sudo homelab-setup status" in txt, txt)
        check("the failed step is marked", pg.locator("#hl-install .hl-st-failed").count() == 1)

        STATUS["data"] = status("running", 2, RUN, updated=int(time.time()) - 3600)
        load(pg)
        check("a status that has not changed for a long time turns the ring amber", pg.evaluate("document.getElementById('hl-install').classList.contains('hl-warn')"))
        pg.locator("#hl-install > button").click()
        pg.wait_for_timeout(200)
        check("a stale status tells how to check", "has not changed for a while" in pg.inner_text("#hl-install .hl-bellpop"))

        STATUS["data"] = status("waiting", 4, RUN)
        load(pg)
        check("steps that wait for the person keep the ring amber", pg.is_visible("#hl-install") and pg.evaluate("document.getElementById('hl-install').classList.contains('hl-warn')"))

        STATUS["data"] = status("done", 5, RUN)
        load(pg)
        check("when the install is done the ring disappears", not pg.is_visible("#hl-install"))

        STATUS["data"] = status("running", 3, RUN)
        load(pg)
        check("the ring follows the latest numbers after a reload", pg.inner_text("#hl-install .hl-ring-n") == "3/5")

        ph = browser.new_context(viewport={"width": 390, "height": 800}, is_mobile=True, has_touch=True).new_page()
        ph.on("pageerror", lambda e: errors.append(str(e)))
        load(ph)
        check("on a phone the ring is shown", ph.is_visible("#hl-install"))
        ph.locator("#hl-install > button").click()
        ph.wait_for_timeout(200)
        box = ph.evaluate("(() => { const r = document.querySelector('#hl-install .hl-bellpop').getBoundingClientRect(); return [r.left, r.right, r.top, r.bottom, innerWidth]; })()")
        check("on a phone the list fits the screen", box[0] >= 0 and box[1] <= box[4] and box[2] >= 0, box)
        check("on a phone the page does not scroll sideways", ph.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        bar = ph.evaluate("(() => { const t = document.getElementById('myTab').getBoundingClientRect(), r = document.getElementById('hl-install').getBoundingClientRect(); return [t.right, r.left, r.right, innerWidth]; })()")
        check("on a phone the tabs, the bell and the ring share the bar", bar[0] <= bar[1] + 1 and bar[2] <= bar[3], bar)
        check("no script errors", not errors, errors)
        browser.close()
finally:
    srv.shutdown()
print("OK" if not bad else "FAIL")
sys.exit(1 if bad else 0)
