#!/usr/bin/env python3
"""Test of the control panel's page (panel/ui) together with the live preview in homepage-config/custom.js
(needs Playwright with Chromium; without it the test says so and passes).

The real panel server runs on a free port with a copy of the shipped Homepage files. A small page with the markup of Homepage's (#inner_wrapper,
#background, the card #customize-card with an iframe) stands in for the dashboard and loads the real custom.js, so the preview messages can be seen
arriving. The checks: login, the look (preview, save, throw away), the background (sliders, upload), the layout, cards, links, Undo, that a frame
which is not the panel cannot change the page, and that the page fits a phone.
Run: python3 tests/t_panel_ui.py   (last line is OK or FAIL)"""
import http.server
import os
import shutil
import sys
import tempfile
import threading

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("skipped: Playwright is not installed")
    print("OK")
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import t_panel as tp  # noqa: E402

JS = os.path.join(HERE, "..", "homepage-config", "custom.js")
results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   " + str(extra)))


PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82")


def host_page(panel_port):
    return ("""<!doctype html><html><head><title>host</title><style>#inner_wrapper{--lk-accent:138, 180, 255;--lk-radius:16px}</style></head><body>
<div id="background" style="background-image:url('/x.jpg')"></div>
<div id="inner_wrapper"><ul><li id="customize-card"><iframe id="panel" src="http://localhost:%d/" style="width:1000px;height:760px;border:0"></iframe></li></ul></div>
<iframe id="stranger" src="about:blank" style="width:10px;height:10px"></iframe>
<script src="/custom.js"></script></body></html>""" % panel_port).encode()


def serve_host(port_holder, panel_port):
    page = host_page(panel_port)
    js = open(JS, "rb").read()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body, ctype = (js, "application/javascript") if self.path == "/custom.js" else (page, "text/html")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    port_holder.append(srv.server_address[1])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    tmp = tempfile.mkdtemp(prefix="hlpui-")
    holder = []
    p = tp.Panel(tmp)
    host = serve_host(holder, p.port)
    p.env["HLP_FRAME"] = "http://localhost:%d" % holder[0]
    p.set_password()
    p.start()
    p.login()                 # an API session of its own, to read what the page saved
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            ctx = b.new_context(viewport={"width": 1300, "height": 900})
            ctx.add_init_script("try { if (location.port != '%d') localStorage.setItem('hlp-auto', '0'); } catch (e) {}" % holder[0])     # the panel does not reload the dashboard by itself (tested at the end)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://localhost:%d/" % holder[0])
            fr = pg.frame_locator("#panel")
            fr.locator("input[type=password]").fill("not the password")
            fr.get_by_role("button", name="Log in").click()
            pg.wait_for_timeout(500)
            check("login: a wrong password shows a message", "not the password" in fr.locator(".err").inner_text(), fr.locator(".err").inner_text())
            fr.locator("input[type=password]").fill(tp.PW)
            fr.get_by_role("button", name="Log in").click()
            fr.locator("nav.tabs").wait_for(timeout=5000)
            check("login: the right password shows the panel inside the dashboard's frame", fr.get_by_role("heading", name="Customize your dashboard").count() == 1)

            # ---- the look
            acc = lambda: pg.evaluate("getComputedStyle(document.getElementById('inner_wrapper')).getPropertyValue('--lk-accent').trim()")
            check("look: the dashboard starts with the shipped accent", acc() == "138, 180, 255", acc())
            fr.get_by_role("button", name="Sunset").click()
            pg.wait_for_timeout(300)
            check("look: a ready-made look is previewed on the dashboard around the panel", acc() == "255, 166, 107", acc())
            check("look: the preview also carries the tab colours", "Stats" in pg.evaluate("document.getElementById('hl-live-look').textContent"))
            fr.locator('input[aria-label="How round the corners are"]').fill("33")
            pg.wait_for_timeout(200)
            check("look: a slider changes the dashboard at once", pg.evaluate("getComputedStyle(document.getElementById('inner_wrapper')).getPropertyValue('--lk-radius').trim()") == "33px")
            check("look: the css file is not touched by a preview", "homelab look" not in p.read("custom.css"))
            fr.get_by_role("button", name="Throw away").click()
            pg.wait_for_timeout(300)
            check("look: throw away brings the saved look back", acc() == "138, 180, 255" and pg.evaluate("document.getElementById('hl-live-look')") is None, acc())
            fr.get_by_role("button", name="Ocean").click()
            fr.locator('input[aria-label="How round the corners are"]').fill("8")
            fr.get_by_role("button", name="Save this look").click()
            pg.wait_for_timeout(800)
            css = p.read("custom.css")
            check("look: Save writes the block to custom.css", "--lk-accent: 94, 200, 255;" in css and "--lk-radius: 8px;" in css, css[-500:])
            check("look: Undo is offered with what it would undo", fr.get_by_role("button", name="↶ Undo (Look changed)").count() == 1)

            # ---- the background
            fr.locator("nav.tabs").get_by_text("Background", exact=True).click()
            fr.locator('input[aria-label="Brightness"]').fill("20")
            pg.wait_for_timeout(300)
            bf = pg.evaluate("document.getElementById('inner_wrapper').style.backdropFilter")
            check("background: a slider changes the dashboard's backdrop at once", "brightness(0.2)" in bf and "blur(12px)" in bf, bf)
            fr.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_timeout(600)
            check("background: Save writes the sliders to settings.yaml", p.state_now()["background"]["brightness"] == 20)
            fr.locator('input[type=file]').set_input_files({"name": "night.png", "mimeType": "image/png", "buffer": PNG})
            pg.wait_for_timeout(1000)
            check("background: an uploaded picture becomes the background", p.state_now()["background"]["image"].startswith("/images/background-"), p.state_now()["background"])
            fr.locator('input[type=url]').fill("https://example.com/a.jpg")
            fr.get_by_role("button", name="Use this address").click()
            fr.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_timeout(600)
            check("background: a web address can be used", p.state_now()["background"]["image"] == "https://example.com/a.jpg")

            # ---- the layout
            fr.locator("nav.tabs").get_by_text("Layout", exact=True).click()
            sel = fr.locator('select[aria-label="Move Files & Photos to a tab"]')
            sel.select_option("Stats")
            fr.get_by_role("button", name="Save the layout").click()
            pg.wait_for_timeout(800)
            check("layout: a group is moved to another tab with a click", "  Files & Photos:\n    tab: Stats" in p.read("settings.yaml"), p.read("settings.yaml")[-900:])
            fr.locator('button[aria-label="Move Calendar up"]').click()
            fr.get_by_role("button", name="Throw away").click()
            check("layout: throw away forgets the change in progress", fr.get_by_role("button", name="Save the layout").is_disabled())

            # ---- cards
            fr.locator("nav.tabs").get_by_text("Cards", exact=True).click()
            fr.get_by_role("button", name="+ Add a card", exact=True).click()
            fr.locator('dialog input[aria-label="Name"]').fill("Router")
            fr.locator('dialog input[aria-label="Address"]').fill("http://192.168.1.1")
            fr.locator('dialog input[aria-label="Description"]').fill("Home router")
            fr.locator('dialog select[aria-label="Group"]').select_option("__new")
            fr.locator('dialog input[aria-label="New group name"]').fill("Tools")
            fr.locator("dialog").get_by_role("button", name="Add", exact=True).click()
            pg.wait_for_timeout(800)
            svc = p.read("services.yaml")
            check("cards: a new card with a new group is added", "- Tools:" in svc and "    - Router:" in svc and "href: http://192.168.1.1" in svc, svc[-400:])
            fr.locator(".item", has_text="Router").get_by_role("button", name="Change").click()
            fr.locator('dialog input[aria-label="Name"]').fill("Main router")
            fr.locator("dialog").get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_timeout(800)
            check("cards: a card is renamed", "    - Main router:" in p.read("services.yaml") and "    - Router:" not in p.read("services.yaml"))
            fr.locator(".item", has_text="Main router").get_by_role("button", name="Remove").click()
            fr.locator("dialog").get_by_role("button", name="Remove it").click()
            pg.wait_for_timeout(800)
            check("cards: a card is removed after the question", "Main router" not in p.read("services.yaml"))

            # ---- links
            fr.locator("nav.tabs").get_by_text("Links", exact=True).click()
            fr.get_by_role("button", name="+ Add a link", exact=True).click()
            fr.locator('dialog input[aria-label="Name"]').fill("Indeed")
            fr.locator('dialog input[aria-label="Address"]').fill("https://www.indeed.com")
            fr.locator('dialog select[aria-label="Group"]').select_option("__new")
            fr.locator('dialog input[aria-label="New group name"]').fill("Job Hunt")
            fr.locator("dialog").get_by_role("button", name="Add", exact=True).click()
            pg.wait_for_timeout(800)
            check("links: a link in a new group is added", "- Job Hunt:" in p.read("bookmarks.yaml") and "href: https://www.indeed.com" in p.read("bookmarks.yaml"))
            check("links: the new group is on the Links tab", "  Job Hunt:\n    tab: Links" in p.read("settings.yaml"), p.read("settings.yaml")[-300:])

            # ---- undo
            before = p.read("bookmarks.yaml")
            fr.get_by_role("button", name="↶ Undo (Link added)").click()
            pg.wait_for_timeout(800)
            check("undo: the button brings the last change back", p.read("bookmarks.yaml") != before and "Job Hunt" not in p.read("bookmarks.yaml"))

            # ---- the dashboard refreshes by itself after a change when that is on
            pg.evaluate("window.__marker = 1")
            fr.locator("#auto").check()
            fr.locator("nav.tabs").get_by_text("Links", exact=True).click()
            fr.get_by_role("button", name="+ Add a link", exact=True).click()
            fr.locator('dialog input[aria-label="Name"]').fill("Glassdoor")
            fr.locator('dialog input[aria-label="Address"]').fill("https://www.glassdoor.com")
            fr.locator("dialog").get_by_role("button", name="Add", exact=True).click()
            pg.wait_for_timeout(2500)
            check("refresh: after a change the dashboard page reloads itself (and the panel is back on the same screen)",
                  pg.evaluate("window.__marker") is None and pg.frame_locator("#panel").get_by_role("heading", name="Links (bookmarks)").count() == 1)

            # ---- a frame that is not the panel cannot change the page
            pg.evaluate("document.getElementById('stranger').contentWindow.eval(\"parent.postMessage({hlp:1,type:'css',css:'body{display:none}'},'*')\")")
            pg.wait_for_timeout(300)
            check("security: a frame that is not the panel cannot change the dashboard", pg.evaluate("document.getElementById('hl-live-look')") is None
                  and pg.evaluate("getComputedStyle(document.body).display") != "none")

            # ---- the page fits a phone
            ph = b.new_context(viewport={"width": 390, "height": 800}, is_mobile=True, has_touch=True).new_page()
            ph.goto("http://localhost:%d/" % p.port)
            ph.locator("input[type=password]").fill(tp.PW)
            ph.get_by_role("button", name="Log in").click()
            ph.locator("nav.tabs").wait_for(timeout=5000)
            for v in ("Look", "Background", "Layout", "Cards", "Links"):
                ph.locator("nav.tabs").get_by_text(v, exact=True).click()
                ph.wait_for_timeout(250)
                w = ph.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
                check("phone: the %s screen has no sideways scrolling" % v, w[0] <= w[1] + 1, w)
            check("page: no script errors", not errs, errs[:3])
            b.close()
    finally:
        p.stop()
        host.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    ok = all(results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
