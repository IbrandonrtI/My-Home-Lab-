#!/usr/bin/env python3
"""Test of the screen fit: a 1080p screen shows the dashboard and the panel at 90% and a 1440p screen at 110% (like the browser zoom), by the real width of the window in screen
pixels (window width x display scale). It runs the "Screen fit" block of the dashboard's custom.js and the panel's own copy in a real browser with the display scale of the
test machine (125%), and checks the dashboard's custom.css rules that go with it.
Needs Playwright with Chromium; without it the test says so and passes.   Run: python3 tests/t_zoom.py   (last line is OK or FAIL)"""
import os
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
    check("custom.css: the old screen-size zoom rule (it hit the wrong monitor) is gone", "max-device-height" not in css and "html { zoom: 0.8" not in css, "")
    check("custom.css: the top row of tiles has its sizes under the fit (0.70 on 1080p, 0.80 on 1440p)", 'html[data-hl-fit="1080"] #information-widgets { zoom: 0.70; }' in block and 'html[data-hl-fit="1440"] #information-widgets { zoom: 0.80; }' in block, "")
    check("custom.css: the space at the left and right is 70 px by default", "--lk-side: 70px;" in block, "")
    check("custom.css: heights use --hl-vh, so they come out right under the zoom", "calc(88 * var(--hl-vh, 1vh))" in block and "min(88vh" not in block, "")
    js = open(os.path.join(ROOT, "homepage-config", "custom.js"), encoding="utf-8").read()
    ja, jz = js.find("/* ---- Screen fit:"), js.find("/* <<< homelab extras <<< */")
    fit = js[ja:jz]
    check("custom.js: the Screen fit block is inside the managed block (an upgrade puts it on the machine)", 0 < ja < jz and "homelab extras >>>" in js[:ja], "")
    check("custom.js: the height sliders divide the window height by the page zoom", "getComputedStyle(document.documentElement).zoom" in js, "")

    tmp = tempfile.mkdtemp(prefix="hlzoom-")
    p = tp.Panel(tmp, {})
    p.set_password()
    p.start()
    page = "<!doctype html><html><head><style>%s</style></head><body style='margin:0'><div id=information-widgets>x</div><script>%s</script></body></html>" % (block, fit)
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()

            def ctx_at(w, h):
                # a window w css pixels wide at the display scale of 125% (Windows 125%): w * 1.25 screen pixels
                return br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1.25)

            def dash_info(w):
                ctx = ctx_at(w, 800)
                pg = ctx.new_page()
                pg.route("http://dash.test/", lambda r: r.fulfill(status=200, content_type="text/html", body=page))
                pg.goto("http://dash.test/")
                info = pg.evaluate("[parseFloat(getComputedStyle(document.documentElement).zoom), document.documentElement.getAttribute('data-hl-fit') || '', getComputedStyle(document.documentElement).getPropertyValue('--hl-vh').trim(), parseFloat(getComputedStyle(document.getElementById('information-widgets')).zoom), window.innerWidth, devicePixelRatio]")
                ctx.close()
                return info

            d1080 = dash_info(1536)      # a 1920 wide screen at 125%
            check("dashboard on a 1080p screen (1920 px at 125%, a window 1536 wide): page at 90%, top row of tiles 0.70, --hl-vh 1.1111vh", d1080[0] == 0.9 and d1080[1] == "1080" and d1080[2] == "1.1111vh" and d1080[3] == 0.7, d1080)
            d1440 = dash_info(2048)      # a 2560 wide screen at 125%
            check("dashboard on a 1440p screen (2560 px at 125%, a window 2048 wide): page at 110%, top row of tiles 0.80, --hl-vh 0.9091vh", d1440[0] == 1.1 and d1440[1] == "1440" and d1440[2] == "0.9091vh" and d1440[3] == 0.8, d1440)
            dsm = dash_info(1280)
            check("dashboard in a smaller window (1600 screen px): normal size", dsm[0] == 1 and dsm[1] == "", dsm)
            d4k = dash_info(3072)       # a 3840 wide screen at 125%
            check("dashboard on a 4K screen: normal size", d4k[0] == 1 and d4k[1] == "", d4k)
            # the same screens with Windows at 100% and at 150%: the same result (it goes by screen pixels, not by the scale)
            for scale, w1080, w1440 in ((1.0, 1920, 2560), (1.5, 1280, 1707)):
                ctx = br.new_context(viewport={"width": w1080, "height": 800}, device_scale_factor=scale)
                pg = ctx.new_page()
                pg.route("http://dash.test/", lambda r: r.fulfill(status=200, content_type="text/html", body=page))
                pg.goto("http://dash.test/")
                z1 = pg.evaluate("parseFloat(getComputedStyle(document.documentElement).zoom)")
                ctx.close()
                ctx = br.new_context(viewport={"width": w1440, "height": 800}, device_scale_factor=scale)
                pg = ctx.new_page()
                pg.route("http://dash.test/", lambda r: r.fulfill(status=200, content_type="text/html", body=page))
                pg.goto("http://dash.test/")
                z2 = pg.evaluate("parseFloat(getComputedStyle(document.documentElement).zoom)")
                ctx.close()
                check("Windows scale %d%%: the 1080p screen gets 0.9 and the 1440p screen gets 1.1 too" % int(scale * 100), z1 == 0.9 and z2 == 1.1, [z1, z2])
            # a window moved from one monitor to the other (the size changes): the page follows
            ctx = ctx_at(1536, 800)
            pg = ctx.new_page()
            pg.route("http://dash.test/", lambda r: r.fulfill(status=200, content_type="text/html", body=page))
            pg.goto("http://dash.test/")
            pg.set_viewport_size({"width": 2048, "height": 800})
            pg.wait_for_timeout(500)
            check("a window moved to the 1440p screen follows: 1.1", pg.evaluate("parseFloat(getComputedStyle(document.documentElement).zoom)") == 1.1, "")
            pg.set_viewport_size({"width": 1536, "height": 800})
            pg.wait_for_timeout(500)
            check("and back to the 1080p screen: 0.9", pg.evaluate("parseFloat(getComputedStyle(document.documentElement).zoom)") == 0.9, "")
            ctx.close()

            # the panel in its own tab
            def panel_zoom(w, scale=1.25):
                ctx = br.new_context(viewport={"width": w, "height": 800}, device_scale_factor=scale)
                pg = ctx.new_page()
                pg.goto("http://127.0.0.1:%d/" % p.port)
                pg.wait_for_selector("input[type=password]")
                r = pg.evaluate("[parseFloat(getComputedStyle(document.documentElement).zoom), getComputedStyle(document.documentElement).getPropertyValue('--vh').trim()]")
                ctx.close()
                return r

            check("panel on a 1080p screen: 0.9, --vh 1.1111vh", panel_zoom(1536) == [0.9, "1.1111vh"], panel_zoom(1536))
            check("panel on a 1440p screen: 1.1, --vh 0.9091vh", panel_zoom(2048) == [1.1, "0.9091vh"], panel_zoom(2048))
            check("panel in a smaller window and on a phone: normal size", panel_zoom(1280)[0] == 1 and panel_zoom(390, 3)[0] == 1, "")
            # logged in on the 1440p screen: the header fits on one line and nothing scrolls sideways
            ctx = ctx_at(2048, 800)
            pg = ctx.new_page()
            pg.goto("http://127.0.0.1:%d/" % p.port)
            pg.fill("input[type=password]", tp.PW)
            pg.click("text=Log In")
            pg.wait_for_selector("nav.tabs")
            check("panel at 1440p: no sideways scroll", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), "")
            ctx.close()
            # the panel inside the dashboard's frame: not zoomed a second time (the page around it has the zoom)
            dash = "http://127.0.0.1:%d/__dash" % p.port
            parent = "<!doctype html><html><head><style>%s</style></head><body style='margin:0'><iframe id=f src='/' style='width:100%%;height:700px;border:0'></iframe><script>%s</script></body></html>" % (block, fit)
            ctx = ctx_at(1536, 800)
            pg = ctx.new_page()
            pg.route(dash, lambda r: r.fulfill(status=200, content_type="text/html", body=parent))
            pg.goto(dash)
            pg.frame_locator("#f").locator("input[type=password]").wait_for()
            check("the dashboard page is at 0.9 and the panel in its frame is not shrunk a second time",
                  pg.evaluate("parseFloat(getComputedStyle(document.documentElement).zoom)") == 0.9 and pg.frames[1].evaluate("document.documentElement.style.zoom === '' && parseFloat(getComputedStyle(document.documentElement).zoom)") == 1, "")
            ctx.close()
            br.close()
    finally:
        p.stop()
    ok = all(results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
