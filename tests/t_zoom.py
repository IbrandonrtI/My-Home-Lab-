#!/usr/bin/env python3
"""Test of the automatic 80% look on 1080p screens: the panel's own style sheet and the managed block of the dashboard's custom.css.
It checks that a 1920x1080 screen gets the 80% look (the page lays out as wide as at 80% browser zoom), that a bigger screen, a laptop and a browser that is
already zoomed to 80% do not, and that the panel inside the dashboard's zoomed page is not shrunk a second time.
Needs Playwright with Chromium; without it the test says so and passes.   Run: python3 tests/t_zoom.py   (last line is OK or FAIL)"""
import os
import re
import sys
import tempfile

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("skipped: Playwright is not installed")
    print("OK")
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import t_panel as tp  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   " + str(extra)))


def main():
    css = open(os.path.join(ROOT, "homepage-config", "custom.css"), encoding="utf-8").read()
    a, z = css.find("/* >>> homelab tabs >>>"), css.find("/* <<< homelab tabs <<< */")
    block = css[a:z]
    rule = re.search(r"@media \(min-width: 1800px\) and \(max-width: 2100px\) and \(max-device-height: 1100px\) \{\s*html \{ zoom: 0\.8; --hl-vh: 1\.25vh; \}", block)
    check("the dashboard's custom.css has the 1080p rule inside the managed block (an upgrade puts it on this machine)", a >= 0 and z > a and bool(rule), block[-600:])
    check("the dashboard's heights use --hl-vh, so they come out right under the zoom", "calc(88 * var(--hl-vh, 1vh))" in block and "calc(54 * var(--hl-vh, 1vh))" in block and "min(88vh" not in block, "")
    js = open(os.path.join(ROOT, "homepage-config", "custom.js"), encoding="utf-8").read()
    check("the height sliders divide the window height by the page zoom", "getComputedStyle(document.documentElement).zoom" in js, "")

    tmp = tempfile.mkdtemp(prefix="hlzoom-")
    p = tp.Panel(tmp, {})
    p.set_password()
    p.start()
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()

            def panel_at(w, h):
                ctx = br.new_context(viewport={"width": w, "height": h}, screen={"width": w, "height": h})
                pg = ctx.new_page()
                pg.goto("http://127.0.0.1:%d/" % p.port)
                pg.wait_for_selector("input[type=password]")
                info = pg.evaluate("[parseFloat(getComputedStyle(document.documentElement).zoom), document.querySelector('#app').getBoundingClientRect().width, window.devicePixelRatio]")      # (#app is at most 2000 wide, so it measures 1600 on screen when the page is at 80%)
                ctx.close()
                return info

            z1080 = panel_at(1920, 1080)
            check("panel on 1920x1080: shown at 80% (its 2000 wide content area measures 1600 on screen, like at browser zoom 80%)", z1080[0] == 0.8 and abs(z1080[1] - 1600) <= 2, z1080)
            z1440 = panel_at(2560, 1440)
            check("panel on 2560x1440: normal size", z1440[0] == 1, z1440)
            zlap = panel_at(1536, 864)
            check("panel on a 1536x864 laptop screen: normal size", zlap[0] == 1, zlap)
            zphone = panel_at(390, 800)
            check("panel on a phone: normal size", zphone[0] == 1, zphone)
            # a browser that is already zoomed to 80% on 1080p lays out 2400 wide: no second shrink
            z80 = panel_at(2400, 1350)
            check("panel at 80% browser zoom (2400 wide): not shrunk again", z80[0] == 1, z80)
            ctx = br.new_context(viewport={"width": 1920, "height": 1080}, screen={"width": 1920, "height": 1080})
            pg = ctx.new_page()
            pg.goto("http://127.0.0.1:%d/" % p.port)
            pg.fill("input[type=password]", tp.PW)
            pg.click("text=Log In")
            pg.wait_for_selector("nav.tabs")
            dlg = pg.evaluate("document.querySelector('dialog') ? 1 : 0")
            check("panel at 1080p: logged in and the header fits on one line", pg.evaluate("document.querySelector('header.top').getBoundingClientRect().height") < 70 and dlg == 0, pg.evaluate("document.querySelector('header.top').getBoundingClientRect().height"))
            check("panel at 1080p: no sideways scroll", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), "")
            ctx.close()
            # the dashboard page with the managed block, the panel inside an iframe (the page is served from the panel's own address, which it allows as a frame parent)
            dash = "http://127.0.0.1:%d/__dash" % p.port
            parent = "<!doctype html><html><head><style>%s</style></head><body style='margin:0'><iframe id=f src='/' style='width:100%%;height:700px;border:0'></iframe></body></html>" % block
            ctx = br.new_context(viewport={"width": 1920, "height": 1080}, screen={"width": 1920, "height": 1080})
            pg = ctx.new_page()
            pg.route(dash, lambda r: r.fulfill(status=200, content_type="text/html", body=parent))
            pg.goto(dash)
            pg.wait_for_selector("iframe")
            fr = pg.frame_locator("#f")
            fr.locator("input[type=password]").wait_for()
            pz = pg.evaluate("[parseFloat(getComputedStyle(document.documentElement).zoom), document.documentElement.clientWidth, getComputedStyle(document.documentElement).getPropertyValue('--hl-vh').trim()]")
            check("dashboard page on 1080p: shown at 80%, with --hl-vh 1.25vh", pz[0] == 0.8 and pz[2] == "1.25vh", pz)
            iz = pg.frames[1].evaluate("[parseFloat(getComputedStyle(document.documentElement).zoom), window.innerWidth]")
            check("the panel inside it is not shrunk a second time (it already lays out like 80%% zoom: %s wide)" % iz[1], iz[0] == 1 and iz[1] >= 2300, iz)
            ctx.close()
            ctx = br.new_context(viewport={"width": 2560, "height": 1440}, screen={"width": 2560, "height": 1440})
            pg = ctx.new_page()
            pg.route(dash, lambda r: r.fulfill(status=200, content_type="text/html", body=parent))
            pg.goto(dash)
            pz = pg.evaluate("parseFloat(getComputedStyle(document.documentElement).zoom)")
            check("dashboard page on 1440p: normal size", pz == 1, pz)
            ctx.close()
            br.close()
    finally:
        p.stop()
    ok = all(results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
