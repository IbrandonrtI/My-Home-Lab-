#!/usr/bin/env python3
"""Test of the Navidrome player block in homepage-config/custom.js (needs Playwright with Chromium; without it the test says so and passes).

A small web page stands in for Homepage. Its Home view has the Navidrome card with the player frame; its Stats view has no card, because
Homepage removes the cards of the tab you leave. The checks: the sound keeps running and the player page is not reloaded when the view
changes, there is only ever one player, and the player lies exactly over the card while the card is shown.
Run: python3 tests/t_player.py   (last line is OK or FAIL)"""
import http.server
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

DASHBOARD = b"""<!doctype html><html><head><style>
body{margin:0;font-family:sans-serif} #root{padding:40px 60px}
#navidrome-card{width:420px;border:1px solid #888;padding:12px;margin-top:300px}
#navidrome-card div:has(> iframe){overflow:hidden !important;border-radius:10px}
#navidrome-card iframe{width:calc(100% + 32px) !important;max-width:none !important;border:0 !important;height:384px}
</style></head><body><div id="root"></div>
<script>
function showHome() { document.getElementById("root").innerHTML = '<div id="navidrome-card"><a href="/">Navidrome</a><div class="w"><iframe src="/player.html" loading="lazy"></iframe></div></div>'; }
function showStats() { document.getElementById("root").innerHTML = "<h1>Stats</h1><p>no player here</p>"; }
showHome();
</script><script src="/custom.js"></script></body></html>"""

INNER = DASHBOARD.replace(b"<body>", b'<body><div id="scroller" style="position:fixed;inset:0;overflow:auto">').replace(
    b'<script src="/custom.js"></script>', b'<div style="height:1500px"></div></div><script src="/custom.js"></script>')

PLAYER = b"""<!doctype html><body style="margin:0;background:#123"><h3>player</h3><script>
window.__id = Math.random();
var ctx = new (window.AudioContext || window.webkitAudioContext)(); var o = ctx.createOscillator(); o.connect(ctx.destination); o.start();
window.__ctx = ctx; ctx.resume();
</script></body>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/custom.js"):
            body, kind = open(JS, "rb").read(), "application/javascript"
        elif self.path.startswith("/player.html"):
            body, kind = PLAYER, "text/html"
        elif self.path.startswith("/inner"):
            body, kind = INNER, "text/html"
        else:
            body, kind = DASHBOARD, "text/html"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)


bad = 0


def check(name, cond, detail=""):
    global bad
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "   " + str(detail)))
    bad += not cond


def players(pg):
    return [f for f in pg.frames if f.url.endswith("/player.html")]


def over(pg):
    card = pg.locator("#navidrome-card .w").bounding_box()
    box = pg.locator("#hl-player-box").bounding_box()
    return all(abs(card[k] - box[k]) <= 1 for k in ("x", "y", "width", "height")), (card, box)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/" % srv.server_address[1]
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        pg = browser.new_page(viewport={"width": 1000, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL)
        pg.wait_for_timeout(1500)
        check("one persistent player frame is made", pg.locator("#hl-player").count() == 1)
        check("the frame Homepage puts in the card is emptied", pg.locator("#navidrome-card iframe").get_attribute("src") == "about:blank")
        check("exactly one live player page", len(players(pg)) == 1, [f.url for f in pg.frames])
        first = players(pg)[0]
        id1, t1 = first.evaluate("window.__id"), first.evaluate("window.__ctx.currentTime")
        check("the player lies over the card", *over(pg))
        pg.evaluate("window.scrollTo(0, 120)")
        pg.wait_for_timeout(700)
        check("it still lies over the card after scrolling", *over(pg))
        pg.evaluate("window.scrollTo(0, 0)")
        pg.evaluate("showStats()")
        pg.wait_for_timeout(1500)
        check("away from the card the player is moved out of sight", "hl-away" in (pg.locator("#hl-player-box").get_attribute("class") or ""))
        same = players(pg)
        check("the tab change did not reload the player page", len(same) == 1 and same[0].evaluate("window.__id") == id1)
        time.sleep(1.2)
        t2 = same[0].evaluate("window.__ctx.currentTime")
        check("the sound keeps running while the tab is away", t2 > t1 + 1.0, (t1, t2))
        pg.evaluate("showHome()")
        pg.wait_for_timeout(1500)
        back = players(pg)
        check("back on Home it is the same player page", len(back) == 1 and back[0].evaluate("window.__id") == id1)
        check("only one player frame exists after returning", pg.locator("#hl-player").count() == 1)
        check("it lies over the new card again", *over(pg))
        check("the new card's own frame is emptied too", pg.locator("#navidrome-card iframe").get_attribute("src") == "about:blank")
        check("the sound is still running", back[0].evaluate("window.__ctx.currentTime") > t2)
        for _ in range(6):
            pg.evaluate("showStats()")
            pg.wait_for_timeout(200)
            pg.evaluate("showHome()")
            pg.wait_for_timeout(300)
        check("quick tab changes leave one player", pg.locator("#hl-player").count() == 1 and len(players(pg)) == 1)
        check("no script errors", not errors, errors)
        # when the page's own scrolling box moves (not the whole page), the player must follow at once, not half a second later
        pg2 = browser.new_page(viewport={"width": 1000, "height": 900})
        pg2.goto(URL + "inner")
        pg2.wait_for_timeout(1500)
        check("inner scrolling box: the player lies over the card to begin with", *over(pg2))
        late = []
        for top in (150, 0, 220, 40, 300, 0):                      # several scrolls, each looked at 60 ms later (the old half-second timer cannot catch them all)
            pg2.evaluate("document.getElementById('scroller').scrollTop = %d" % top)
            pg2.wait_for_timeout(60)
            ok_, detail = over(pg2)
            if not ok_:
                late.append((top, detail))
        check("inner scrolling box: the player follows the card within a moment of every scroll", not late, late[:1])
        # the player sits inside the scrolling box, so the browser moves it together with the cards: even in the very same instant as the scroll
        check("inner scrolling box: the player frame lives inside the scrolling box", pg2.evaluate("document.getElementById('hl-player-box').parentNode.id") == "scroller")
        same_instant = pg2.evaluate("""() => { var s = document.getElementById('scroller'); s.scrollTop = 333;
            var c = document.querySelector('#navidrome-card .w').getBoundingClientRect(), b = document.getElementById('hl-player-box').getBoundingClientRect();
            return Math.abs(c.top - b.top) < 1 && Math.abs(c.left - b.left) < 1; }""")
        check("inner scrolling box: the player moves in the same instant as the cards (nothing is left to catch up)", same_instant)
        id_before = players(pg2)[0].evaluate("window.__id")
        pg2.evaluate("showStats()")
        pg2.wait_for_timeout(800)
        pg2.evaluate("showHome()")
        pg2.wait_for_timeout(1200)
        check("inner scrolling box: a tab change still does not reload the player", len(players(pg2)) == 1 and players(pg2)[0].evaluate("window.__id") == id_before)
        check("inner scrolling box: after the tab change it lies over the card", *over(pg2))
        browser.close()
finally:
    srv.shutdown()
print("OK" if not bad else "FAIL")
sys.exit(1 if bad else 0)
