#!/usr/bin/env python3
"""Test of the bell in homepage-config/custom.js and custom.css (needs Playwright with Chromium; without it the test says so and passes).

A small page with Homepage's tab markup stands in for it, with a changeable images/alerts.json. The checks: the bell sits next to the tabs, the count and its
color follow the worst alert, the list shows what the file says (as text only), update and drive alerts get a button to the control panel's own screen, a missing
file is explained, an empty list says all is well, a click outside or Escape closes it, and it fits a phone.
Screenshots (when BELL_SHOTS names a folder) are for looking at. Run: python3 tests/t_bell.py   (last line is OK or FAIL)"""
import http.server
import importlib.machinery
import importlib.util
import json
import os
import sys
import threading

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("skipped: Playwright is not installed")
    print("OK")
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, "..", "homepage-config", "custom.js")
CSS = os.path.join(HERE, "..", "homepage-config", "custom.css")
SHOTS = os.environ.get("BELL_SHOTS")
_ld = importlib.machinery.SourceFileLoader("homelab_panel", os.path.join(HERE, "..", "scripts", "homelab-panel"))
_sp = importlib.util.spec_from_loader("homelab_panel", _ld)
PANEL = importlib.util.module_from_spec(_sp)
_ld.exec_module(PANEL)

# contrast of every piece of text in the open list against what is really behind it (the real colors, mixed down to plain RGB by a canvas)
CONTRAST_JS = """(() => {
  var cv = document.createElement('canvas'); cv.width = cv.height = 1; var cx = cv.getContext('2d', { willReadFrequently: true });
  function rgba(c) { cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#000'; cx.fillStyle = c; cx.fillRect(0, 0, 1, 1); var d = cx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; }
  function over(top, bot) { var a = top[3]; return [top[0] * a + bot[0] * (1 - a), top[1] * a + bot[1] * (1 - a), top[2] * a + bot[2] * (1 - a), 1]; }
  function lum(c) { var f = function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); }
  function behind(el) { var chain = []; for (var e = el; e; e = e.parentElement) chain.push(rgba(getComputedStyle(e).backgroundColor)); var acc = [255, 255, 255, 1]; for (var i = chain.length - 1; i >= 0; i--) acc = over(chain[i], acc); return acc; }
  var out = [];
  document.querySelectorAll('#hl-bell .hl-bellpop .hl-bellsub, #hl-bell .hl-bellpop .hl-belltitle, #hl-bell .hl-bellpop .hl-belldetail, #hl-bell .hl-bellpop a.hl-bellbtn, #hl-bell .hl-bellpop .hl-bellhead > *:first-child').forEach(function (el) {
    var fg = rgba(getComputedStyle(el).color), bg = behind(el); fg = over(fg, bg);
    var l1 = lum(fg), l2 = lum(bg), hi = Math.max(l1, l2), lo = Math.min(l1, l2);
    out.push([el.className || el.tagName, Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100, (el.textContent || '').slice(0, 24)]);
  });
  var pop = document.querySelector('#hl-bell .hl-bellpop'), pb = rgba(getComputedStyle(pop).backgroundColor);
  return { rows: out, popAlpha: pb[3] };
})()"""

PAGE = b"""<!doctype html><html><head><style>ul{margin:0;padding:0;list-style:none}button{font:inherit}</style><link rel="stylesheet" href="/custom.css"></head><body>
<div id="inner_wrapper"><div class="container">
<div id="tabs"><ul id="myTab"><li><button id="Home-tab" aria-selected="true">Home</button></li><li><button id="Stats-tab" aria-selected="false">Stats</button></li><li><button id="Customize-tab" aria-selected="false">Customize</button></li></ul></div>
<div id="layout-groups"><div class="services-group"><div class="service-group-name" data-group="x">Group</div><ul class="services-list"><li class="service" id="a-card"><div class="service-card"><div class="service-title">A</div></div></li><li class="service"><div class="service-card"><div class="service-title">Card 2</div></div></li><li class="service"><div class="service-card"><div class="service-title">Card 3</div></div></li><li class="service"><div class="service-card"><div class="service-title">Card 4</div></div></li><li class="service"><div class="service-card"><div class="service-title">Card 5</div></div></li><li class="service"><div class="service-card"><div class="service-title">Card 6</div></div></li><li class="service"><div class="service-card"><div class="service-title">Card 7</div></div></li><li class="service"><div class="service-card"><div class="service-title">Card 8</div></div></li></ul></div></div>
</div></div><script src="/custom.js"></script></body></html>"""

ALERTS = {"data": None}


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
        elif path == "/images/alerts.json":
            if ALERTS["data"] is None:
                body, kind, code = b"{}", "application/json", 404
            else:
                body, kind = json.dumps(ALERTS["data"]).encode(), "application/json"
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


def it(iid, level, title, detail="", action=""):
    return {"id": iid, "level": level, "title": title, "detail": detail, "action": action}


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/" % srv.server_address[1]
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1000, "height": 800})
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        # no file yet
        pg.goto(URL)
        pg.locator("#hl-bell").wait_for()
        check("the bell sits right after the tabs", pg.evaluate("document.getElementById('myTab').nextElementSibling.id") == "hl-bell")
        check("there is only one bell", pg.evaluate("document.querySelectorAll('#hl-bell').length") == 1)
        pg.locator("#hl-bell > button").click()
        pg.wait_for_timeout(400)
        check("a missing file is explained", "not there yet" in pg.inner_text("#hl-bell .hl-bellpop"), pg.inner_text("#hl-bell .hl-bellpop"))
        check("no count is shown without a list", pg.evaluate("document.querySelector('.hl-bell-n').hidden"))

        # a list with all three levels, an update, drives, and text that must stay text
        ALERTS["data"] = {"version": 1, "updated": 4102444800, "counts": {"bad": 1, "warn": 1, "info": 2}, "items": [
            it("down:immich", "bad", "Immich server is not running", "Exited (1) 3 minutes ago"),
            it("restart", "warn", "A restart is needed", "A system update asked for it.", "update"),
            it("updates:containers", "info", "2 container updates waiting", "immich, nextcloud", "update"),
            it("x", "info", "<img src=x onerror=window.__pwned=1>", "<b>bold</b>", "drives")]}
        pg.reload()
        pg.locator("#hl-bell").wait_for()
        pg.wait_for_timeout(600)
        check("the count is the number of alerts", pg.inner_text(".hl-bell-n") == "4", pg.inner_text(".hl-bell-n"))
        check("the count has the color of the worst alert", "hl-lv-bad" in pg.evaluate("document.querySelector('.hl-bell-n').className"))
        check("the list is closed until the bell is pressed", not pg.is_visible("#hl-bell .hl-bellpop"))
        pg.locator("#hl-bell > button").click()
        pg.wait_for_timeout(200)
        check("pressing the bell opens the list", pg.is_visible("#hl-bell .hl-bellpop") and pg.get_attribute("#hl-bell > button", "aria-expanded") == "true")
        over = pg.evaluate("""(() => { var r = document.querySelector('#hl-bell .hl-bellpop').getBoundingClientRect(), bad = 0, n = 0;
            [[0.15, 0.2], [0.5, 0.5], [0.85, 0.8], [0.5, 0.95]].forEach(function (f) { var e = document.elementFromPoint(r.left + r.width * f[0], r.top + r.height * f[1]); n++; if (!e || !e.closest('#hl-bell')) bad++; });
            return bad; })()""")
        check("the list lies above the cards (nothing covers it)", over == 0, over)
        bg = pg.evaluate("getComputedStyle(document.querySelector('#hl-bell .hl-bellpop')).backgroundColor")
        check("the list is solid, so the cards behind it do not show through", pg.evaluate(CONTRAST_JS)["popAlpha"] == 1, bg)

        # every theme of the panel (and a few extreme colors the Colors screen allows): all the text in the list must be easy to read
        looks = [(t["id"], t["look"]) for t in PANEL.LOOK_THEMES]
        looks += [("custom: white glass, black text", {"glass": "#ffffff", "glassOpacity": 100, "text": "#000000", "muted": "#222222", "accent": "#ffffff"}),
                  ("custom: yellow accent, light glass", {"glass": "#fff7c2", "glassOpacity": 90, "accent": "#ffe600", "text": "#fffbe0", "muted": "#fff2a0"}),
                  ("custom: black glass, black text", {"glass": "#000000", "glassOpacity": 100, "text": "#101010", "muted": "#202020", "accent": "#000000"})]
        worst = 99
        for name, look in looks:
            css_text = PANEL.look_css(look, full=True)
            h = pg.add_style_tag(content=css_text)
            pg.wait_for_timeout(60)
            res = pg.evaluate(CONTRAST_JS)
            low = [r for r in res["rows"] if r[1] < 4.5]
            worst = min([worst] + [r[1] for r in res["rows"]])
            check("theme %s: the list is solid and all its text has a contrast of 4.5 or more (%d texts)" % (name, len(res["rows"])), res["popAlpha"] == 1 and len(res["rows"]) >= 8 and not low, (low, res["popAlpha"]))
            if SHOTS:
                os.makedirs(SHOTS, exist_ok=True)
                pg.screenshot(path=os.path.join(SHOTS, "theme-%s.png" % "".join(c if c.isalnum() else "-" for c in name)), clip={"x": 0, "y": 0, "width": 1000, "height": 520})
            h.evaluate("e => e.remove()")
        print("     lowest contrast in any theme: %s" % worst)
        rows = pg.locator("#hl-bell .hl-bellrow")
        check("every alert is a row, the worst first", rows.count() == 4 and "Immich server is not running" in rows.nth(0).inner_text(), rows.count())
        check("the detail is shown", "Exited (1)" in rows.nth(0).inner_text())
        check("text from the file stays text", pg.evaluate("window.__pwned") is None and pg.evaluate("document.querySelectorAll('#hl-bell img, #hl-bell b').length") == 0)
        btns = pg.evaluate("[...document.querySelectorAll('#hl-bell a.hl-bellbtn')].map(a => [a.textContent, a.getAttribute('href'), a.target, a.rel])")
        check("update alerts have an Update button to the panel's Updates screen", btns[0][0] == "Update" and btns[0][1].endswith(":1100/#updates") and btns[0][1].startswith("https://127.0.0.1"), btns)
        check("... which opens in a new tab safely", btns[0][2] == "_blank" and "noopener" in btns[0][3], btns)
        check("drive alerts have an Open Drives button", btns[2][0] == "Open Drives" and btns[2][1].endswith("#drives"), btns)
        check("an alert with no action has no button", rows.nth(0).locator("a").count() == 0)
        if SHOTS:
            os.makedirs(SHOTS, exist_ok=True)
            pg.screenshot(path=os.path.join(SHOTS, "bell-open.png"), clip={"x": 0, "y": 0, "width": 1000, "height": 520})
        pg.keyboard.press("Escape")
        check("Escape closes the list", not pg.is_visible("#hl-bell .hl-bellpop"))
        pg.locator("#hl-bell > button").click()
        pg.mouse.click(40, 700)
        check("a click elsewhere closes the list", not pg.is_visible("#hl-bell .hl-bellpop"))
        check("the tabs still work next to the bell", pg.evaluate("document.querySelectorAll('#myTab button').length") == 3)

        # all good
        ALERTS["data"]["items"], ALERTS["data"]["counts"] = [], {"bad": 0, "warn": 0, "info": 0}
        pg.reload()
        pg.locator("#hl-bell").wait_for()
        pg.wait_for_timeout(600)
        pg.locator("#hl-bell > button").click()
        check("an empty list says all is good and shows no count", "All good" in pg.inner_text("#hl-bell .hl-bellpop") and pg.evaluate("document.querySelector('.hl-bell-n').hidden"))

        # an old file
        ALERTS["data"]["updated"] = 1000
        pg.reload()
        pg.locator("#hl-bell").wait_for()
        pg.wait_for_timeout(600)
        pg.locator("#hl-bell > button").click()
        check("an old file is said to be old", "Not updated for a while" in pg.inner_text("#hl-bell .hl-bellhead"), pg.inner_text("#hl-bell .hl-bellhead"))

        # a phone
        ALERTS["data"]["updated"] = 4102444800
        ALERTS["data"]["items"] = [it("down:immich", "bad", "Immich server is not running", "Exited (1) 3 minutes ago"), it("u", "info", "2 container updates waiting", "immich, nextcloud", "update")]
        ph = browser.new_context(viewport={"width": 390, "height": 760}, device_scale_factor=2).new_page()
        ph.goto(URL)
        ph.add_style_tag(content="#inner_wrapper #tabs { position: fixed; left: 0; right: 0; bottom: 0; margin: 0 !important; }")      # (Homepage's real page keeps the bar at the bottom of the screen)
        ph.locator("#hl-bell").wait_for()
        ph.wait_for_timeout(600)
        ph.locator("#hl-bell > button").click()
        ph.wait_for_timeout(200)
        box = ph.evaluate("(() => { const r = document.querySelector('#hl-bell .hl-bellpop').getBoundingClientRect(); return [r.left, r.right, r.top, r.bottom, innerWidth]; })()")
        check("on a phone the list fits the screen", box[0] >= 0 and box[1] <= box[4] and box[2] >= 0, box)
        check("on a phone the page does not scroll sideways", ph.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        tab = ph.evaluate("(() => { const r = document.getElementById('myTab').getBoundingClientRect(), b = document.getElementById('hl-bell').getBoundingClientRect(); return [r.right, b.left, b.right, innerWidth]; })()")
        check("on a phone the tabs and the bell share the bar", tab[0] <= tab[1] + 1 and tab[2] <= tab[3], tab)
        if SHOTS:
            ph.screenshot(path=os.path.join(SHOTS, "bell-phone.png"))
        check("no script errors", not errors, errors)
        browser.close()
finally:
    srv.shutdown()
print("OK" if not bad else "FAIL")
sys.exit(1 if bad else 0)
