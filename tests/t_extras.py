#!/usr/bin/env python3
"""Test of the extras block in homepage-config/custom.js (needs Playwright with Chromium; without it the test says so and passes).

A small web page with the same markup as Homepage's stands in for it. The checks: a card whose service does not answer is marked, the shrink button on the music card folds it and is remembered, every group gets a count and a fold button that is
remembered, a percentage gets a bar (amber from 85, red from 95), the tab you are on is written on the page, and the phone's search button works.
Run: python3 tests/t_extras.py   (last line is OK or FAIL)"""
import http.server
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

PAGE = b"""<!doctype html><html><head><style>.services-group > div{overflow:hidden}</style><link rel="stylesheet" href="/custom.css"></head><body>
<div id="inner_wrapper"><div class="container">
<div id="information-widgets"><div id="widgets-wrap"><div id="information-widgets-right"><form class="information-widget-search"><input type="text"></form></div></div></div>
<div id="tabs"><ul id="myTab"><li><button id="Home-tab" aria-selected="true">Home</button></li><li><button id="Stats-tab" aria-selected="false">Stats</button></li></ul></div>
<div id="layout-groups">
  <div class="services-group"><button disabled><h2 class="service-group-name">Music</h2></button><div><ul class="services-list">
    <li class="service" id="navidrome-card" data-name="Navidrome"><div class="service-card"><div class="service-title">Navidrome<div class="site-monitor-status"><div class="rounded-full bg-emerald-500"></div></div></div></div></li>
    <li class="service" data-name="Downtify"><div class="service-card"><div class="service-title">Downtify<div class="site-monitor-status"><div class="rounded-full bg-emerald-500"></div></div></div></div></li>
  </ul></div></div>
  <div class="services-group"><button disabled><h2 class="service-group-name">Files</h2></button><div><ul class="services-list">
    <li class="service" id="immich-card" data-name="Immich"><div class="service-card"><div class="service-title">Immich<div class="site-monitor-status"><div id="immich-dot" class="rounded-full bg-emerald-500"></div></div></div></div></li>
  </ul></div></div>
  <div class="services-group"><button disabled><h2 class="service-group-name">Storage</h2></button><div><ul class="services-list">
    <li class="service" id="stat-storage"><div class="service-card"><div class="service-block a"><div class="service-block-value">47%</div></div><div class="service-block b"><div class="service-block-value">88%</div></div><div class="service-block c"><div class="service-block-value">97%</div></div><div class="service-block d"><div class="service-block-value">12 GB</div></div></div></li>
  </ul></div></div>
</div></div></div><script src="/custom.js"></script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/custom.js"):
            body, kind = open(JS, "rb").read(), "application/javascript"
        elif self.path.startswith("/custom.css"):
            body, kind = open(CSS, "rb").read(), "text/css"
        else:
            body, kind = PAGE, "text/html"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)


bad = 0


def check(name, cond, detail=""):
    global bad
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "   " + str(detail)))
    bad += not cond


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
        pg.goto(URL)
        pg.wait_for_timeout(700)
        check("there is no health line any more", pg.evaluate("document.getElementById('hl-health')") is None)
        pg.evaluate("document.getElementById('immich-dot').className = 'rounded-full bg-rose-500'")
        pg.wait_for_timeout(3600)
        check("the card of a service that does not answer is marked", pg.evaluate("document.querySelector('#immich-card').classList.contains('hl-down')") and pg.evaluate("document.querySelectorAll('.hl-down').length") == 1)
        pg.evaluate("document.getElementById('immich-dot').className = 'rounded-full bg-emerald-500'")
        pg.wait_for_timeout(3600)
        check("the mark is gone when the service answers again", pg.evaluate("document.querySelectorAll('.hl-down').length") == 0)
        # groups
        counts = pg.evaluate("[...document.querySelectorAll('.service-group-name')].map(h => h.getAttribute('data-count')).join(',')")
        check("every group has the count of its cards", counts == "2,1,1", counts)
        check("every group has one fold button", pg.evaluate("document.querySelectorAll('.services-group > .hl-gfold').length") == 3)
        pg.locator(".services-group").nth(1).locator("> .hl-gfold").click()
        check("a click folds the group", pg.evaluate("document.querySelectorAll('.services-group')[1].classList.contains('hl-folded')"))
        pg.wait_for_timeout(100)
        mid = pg.evaluate("document.querySelectorAll('.services-group')[1].children[1].getBoundingClientRect().height")
        check("the fold is not instant: a moment after the click the group is still part way shut", 0 < mid, mid)
        pg.wait_for_timeout(700)
        check("when the animation is over the group is shut", pg.evaluate("document.querySelectorAll('.services-group')[1].children[1].getBoundingClientRect().height") == 0 and pg.evaluate("document.querySelectorAll('.services-group')[1].children[1].style.maxHeight") == "")
        pg.reload()
        pg.wait_for_timeout(700)
        check("the fold is remembered after a reload", pg.evaluate("document.querySelectorAll('.services-group')[1].classList.contains('hl-folded')") and pg.evaluate("document.querySelectorAll('.hl-folded').length") == 1)
        pg.locator(".services-group").nth(1).locator("> .hl-gfold").click()
        check("a second click opens it again", pg.evaluate("document.querySelectorAll('.hl-folded').length") == 0)
        pg.wait_for_timeout(300)
        check("one fold button per group after the changes", pg.evaluate("document.querySelectorAll('.services-group > .hl-gfold').length") == 3)
        # shrink button
        check("the Navidrome card has one shrink button", pg.evaluate("document.querySelectorAll('#navidrome-card .hl-shrink').length") == 1)
        pg.click(".hl-shrink")
        check("a click shrinks the player", pg.evaluate("document.documentElement.classList.contains('hl-player-min')"))
        pg.reload()
        pg.wait_for_timeout(700)
        check("the shrink is remembered after a reload", pg.evaluate("document.documentElement.classList.contains('hl-player-min')"))
        pg.click(".hl-shrink")
        check("a second click shows the player again", not pg.evaluate("document.documentElement.classList.contains('hl-player-min')"))
        # bars
        bars = pg.evaluate("[...document.querySelectorAll('#stat-storage .service-block')].map(b => b.className.split(' ').filter(c => c.indexOf('hl-') == 0).join('+'))")
        check("percentages get bars: plain, amber from 85, red from 95, and a non-percentage gets none", bars == ["hl-bar", "hl-bar+hl-amber", "hl-bar+hl-red", ""], bars)
        check("the bar length is the percentage", pg.evaluate("document.querySelector('#stat-storage .service-block').style.getPropertyValue('--hl-pct')") == "47%")
        # tab name and search button
        check("the tab you are on is written on the page", pg.evaluate("document.documentElement.getAttribute('data-tab')") == "Home")
        pg.evaluate("document.getElementById('Home-tab').setAttribute('aria-selected','false'); document.getElementById('Stats-tab').setAttribute('aria-selected','true')")
        pg.evaluate("document.body.appendChild(document.createElement('i'))")        # a change on the page makes the script look again
        pg.wait_for_timeout(300)
        check("... and follows a tab change", pg.evaluate("document.documentElement.getAttribute('data-tab')") == "Stats")
        check("the search button exists once", pg.evaluate("document.querySelectorAll('#hl-search-btn').length") == 1)
        pg.set_viewport_size({"width": 600, "height": 800})          # the button is for phone-width windows
        pg.click("#hl-search-btn")
        check("a click on it opens the search (page marked)", pg.evaluate("document.documentElement.classList.contains('hl-search-open')"))
        check("and puts the cursor in the search field", pg.evaluate("document.activeElement.tagName") == "INPUT")
        check("the night value is set between 0 and 1", 0 <= float(pg.evaluate("document.documentElement.style.getPropertyValue('--hl-night')")) <= 1)
        check("no script errors", not errors, errors)
        browser.close()
finally:
    srv.shutdown()
print("OK" if not bad else "FAIL")
sys.exit(1 if bad else 0)
