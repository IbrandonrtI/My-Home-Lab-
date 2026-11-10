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
import re
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
    return ("""<!doctype html><html><head><title>host</title><style>#inner_wrapper{--lk-accent:138, 180, 255;--lk-radius:16px}</style><link rel="stylesheet" href="/api/config/custom.css"></head><body>
<div id="background" style="background-image:url('/x.jpg')"></div>
<div id="inner_wrapper"><div id="widgets-wrap"><div class="widget-container"><div>CPU 31</div><div>HomeLab</div></div><div class="widget-container"><div>Main Pool</div></div><div class="widget-container"><div>Connect Backup Drive</div></div></div><ul><li id="customize-card"><iframe id="panel" src="http://localhost:%d/" style="width:1000px;height:760px;border:0"></iframe></li></ul></div>
<ul><li id="linkedit-card"><iframe id="linkpanel" src="http://localhost:%d/?only=links" style="width:1000px;height:760px;border:0"></iframe></li></ul>
<iframe id="stranger" src="about:blank" style="width:10px;height:10px"></iframe>
<script src="/custom.js"></script></body></html>""" % (panel_port, panel_port)).encode()


def serve_host(port_holder, panel_port, cssfile):
    page = host_page(panel_port)
    js = open(JS, "rb").read()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/api/config/custom.css"):
                whole = open(cssfile, "rb").read()                    # (only the look block of it: the page of this test has no use for the rest of the shipped styles)
                a, b = whole.find(b"/* >>> homelab look >>>"), whole.find(b"/* <<< homelab look <<< */")
                body, ctype = (whole[a:b + 26] if a >= 0 and b >= 0 else b""), "text/css"
            elif self.path == "/api/hash":
                import hashlib
                body, ctype = ('{"hash":"%s"}' % hashlib.sha256(open(cssfile, "rb").read()).hexdigest()).encode(), "application/json"
            else:
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
    host = serve_host(holder, p.port, os.path.join(p.hp, "custom.css"))
    p.env["HLP_FRAME"] = "http://localhost:%d" % holder[0]
    p.set_password()
    p.start()
    p.login()                 # an API session of its own, to read what the page saved
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            ctx = b.new_context(viewport={"width": 1300, "height": 1700})
            ctx.add_init_script("try { if (location.port != '%d') localStorage.setItem('hlp-auto', '0'); } catch (e) {}" % holder[0])     # the panel does not reload the dashboard by itself (tested at the end)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://localhost:%d/" % holder[0])
            fr = pg.frame_locator("#panel")
            fr.locator("input[type=password]").fill("not the password")
            fr.get_by_role("button", name="Log In").click()
            pg.wait_for_timeout(500)
            check("login: a wrong password shows a message", "not the password" in fr.locator(".err").inner_text(), fr.locator(".err").inner_text())
            fr.locator("input[type=password]").fill(tp.PW)
            fr.get_by_role("button", name="Log In").click()
            fr.locator("nav.tabs").wait_for(timeout=5000)
            check("login: the right password shows the panel inside the dashboard's frame", fr.get_by_role("heading", name="Customize Your Dashboard").count() == 1)

            # ---- one Look screen: the order of its parts, and no separate Colors and Background screens
            tabs_now = fr.locator("nav.tabs button").all_inner_texts()
            check("screens: Look, Layout, Cards and Drives only (Colors and Background are part of Look)", tabs_now == ["Look", "Layout", "Cards", "Drives"], tabs_now)
            heads = fr.locator(".card h2, details.card > summary b").all_inner_texts()
            want = ["Themes", "Preview and Shape", "Colors and Glass", "Color Strength", "Background Picture", "How the Background Looks Behind the Cards", "Names and Logo", "Colors of Cards, Tiles and Bookmarks", "Service Cards"]
            pos = [heads.index(x) if x in heads else -1 for x in want]
            check("look: Themes first, then Preview and Shape, Colors and Glass, the background, Names and Logo, and the colors of cards below", -1 not in pos and pos == sorted(pos), heads)

            # ---- the look
            acc = lambda: pg.evaluate("getComputedStyle(document.getElementById('inner_wrapper')).getPropertyValue('--lk-accent').trim()")
            check("look: the dashboard starts with the shipped accent", acc() == "138, 180, 255", acc())
            fr.get_by_role("button", name="Sunset").click()
            pg.wait_for_timeout(300)
            check("look: a ready-made look is previewed on the dashboard around the panel", acc() == "255, 166, 107", acc())
            check("look: the preview also carries the tab colors", "Stats" in pg.evaluate("document.getElementById('hl-live-look').textContent"))
            fr.locator('input[aria-label="How Round the Corners Are"]').fill("33")
            pg.wait_for_timeout(200)
            check("look: a slider changes the dashboard at once", pg.evaluate("getComputedStyle(document.getElementById('inner_wrapper')).getPropertyValue('--lk-radius').trim()") == "33px")
            check("look: the css file is not touched by a preview", "homelab look" not in p.read("custom.css"))
            fr.get_by_role("button", name="Discard Changes").click()
            pg.wait_for_timeout(300)
            check("look: throw away brings the saved look back", acc() == "138, 180, 255" and pg.evaluate("document.getElementById('hl-live-look')") is None, acc())
            # ---- the themes
            check("themes: the Look screen starts with eight theme tiles, Calm Night chosen", fr.locator("button.theme").count() == 8 and fr.locator('button.theme[aria-pressed="true"]').inner_text().startswith("Calm Night"))
            fr.get_by_role("button", name="Frosted Glass").click()
            pg.wait_for_timeout(500)
            ps = fr.locator("body").evaluate("() => [getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(), document.documentElement.classList.contains('glassy')]")
            check("themes: a theme changes the panel too (its background and its glass blur)", ps[0].startswith("linear-gradient") and ps[1] is True, ps)
            check("themes: the dashboard around the panel gets the theme's blur and radius at once", pg.evaluate("getComputedStyle(document.getElementById('inner_wrapper')).getPropertyValue('--lk-blur').trim()") == "30px" and pg.evaluate("getComputedStyle(document.getElementById('inner_wrapper')).getPropertyValue('--lk-radius').trim()") == "24px")
            live = pg.evaluate("document.getElementById('hl-live-look').textContent")
            check("themes: a theme gives the cards its colors (the first group gets the first color of the palette)", "--accent:10, 132, 255" in live, live[-300:])
            check("themes: picking one is only a draft (the files do not change)", "homelab look" not in p.read("custom.css"))
            names = fr.locator("button.theme b").all_inner_texts()
            check("themes: Liquid Glass is a tile, Forest is not", "Liquid Glass" in names and "Forest" not in names, names)
            box = fr.get_by_label("Also change the background picture")
            picbg = lambda: fr.locator(".pic").first.evaluate("e => e.style.backgroundImage")
            check("themes: the picture of the theme is shown as a draft (the box is ticked)", box.is_checked() and "photo-1756909688538" in picbg(), picbg())
            check("themes: the draft with a picture counts as unsaved changes", "Unsaved" in fr.locator(".state").inner_text())
            box.uncheck()
            pg.wait_for_timeout(200)
            check("themes: with the box unticked the picture stays as it was", "photo-1756909688538" not in picbg())
            box.check()
            pg.wait_for_timeout(200)
            check("themes: ticking it again brings the theme's picture back", "photo-1756909688538" in picbg(), picbg())
            fr.get_by_role("button", name="Liquid Glass").click()
            pg.wait_for_timeout(500)
            rim = pg.evaluate("getComputedStyle(document.getElementById('inner_wrapper')).getPropertyValue('--lk-rim').trim()")
            check("themes: Liquid Glass puts a shining edge on the dashboard and the panel", rim.startswith("inset 1px 1px 0") and fr.locator("body").evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--prim').trim()").startswith("inset 1px 1px 0"), rim)
            check("themes: the sliders of the picture follow the theme", fr.locator('input[aria-label="Picture Brightness"]').input_value() == "58" and "photo-1603847734015" in picbg())
            ga = lambda: pg.evaluate("getComputedStyle(document.getElementById('inner_wrapper')).getPropertyValue('--lk-glass-a').trim()")
            check("tint: a theme starts with No Tint (the glass color layer is gone on the dashboard)", fr.get_by_role("button", name="No Tint").get_attribute("aria-pressed") == "true" and ga() == "0", ga())
            fr.get_by_role("button", name="Tint On").click()
            pg.wait_for_timeout(500)
            check("tint: Tint On brings the glass layer back, with its sliders", ga() not in ("0", "") and fr.locator('input[aria-label="How Transparent"]').count() == 1, ga())
            fr.get_by_role("button", name="No Tint").click()
            pg.wait_for_timeout(500)
            check("tint: No Tint again, and the glass sliders are hidden", ga() == "0" and fr.locator('input[aria-label="How Transparent"]').count() == 0, ga())
            check("look: the Shine on the Glass Edge slider is there and follows the theme", fr.locator('input[aria-label="Shine on the Glass Edge"]').input_value() == "70")
            fr.get_by_role("button", name="Calm Night").click()
            pg.wait_for_timeout(400)
            ps = fr.locator("body").evaluate("() => [getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(), document.documentElement.classList.contains('glassy')]")
            check("themes: Calm Night puts the panel and the dashboard back", ps == ["#0a0f19", False] or (ps[0] == "" and ps[1] is False) or (ps[0] in ("#0a0f19", "") and ps[1] is False), ps)
            pg.evaluate("window.__stay = 1")
            fr.locator('input[aria-label="Main Color (hex code)"]').fill("#5ec8ff")
            fr.locator('input[aria-label="Main Color (hex code)"]').dispatch_event("change")
            fr.locator('input[aria-label="How Round the Corners Are"]').fill("8")
            fr.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_timeout(1200)
            css = p.read("custom.css")
            check("look: Save writes the block to custom.css", "--lk-accent: 94, 200, 255;" in css and "--lk-radius: 8px;" in css, css[-500:])
            import hashlib
            want = hashlib.sha256(css.encode()).hexdigest()
            check("save: the dashboard page is not reloaded, Homepage is told the new version is known, and the new style sheet replaces the preview",
                  pg.evaluate("window.__stay") == 1 and pg.evaluate("localStorage.getItem('hash')") == want and "hl=" in pg.evaluate("document.querySelector('link[rel=stylesheet][href*=\"custom.css\"]').getAttribute('href')")
                  and pg.evaluate("document.querySelectorAll('link[rel=stylesheet][href*=\"custom.css\"]').length") == 1 and pg.evaluate("document.getElementById('hl-live-look')") is None, pg.evaluate("[window.__stay, localStorage.getItem('hash'), document.querySelector('link[rel=stylesheet]').getAttribute('href'), !!document.getElementById('hl-live-look')]") + [want])
            ub = fr.get_by_role("button", name="Undo", exact=True)
            check("look: Undo is a plain button that says what it would undo when you point at it", ub.count() == 1 and ub.get_attribute("title") == "Undo: Look changed", ub.get_attribute("title"))
            names = fr.locator("header.top .hactions").locator("button, a").all_inner_texts()
            check("top: Undo, Save and Open in Tab, then Log Out, are together in the top line", [n for n in names if n in ("Undo", "Save", "Open in New Tab", "Log Out")] == ["Undo", "Save", "Open in New Tab", "Log Out"], names)
            check("top: it has the Reset All Settings button on the Look screen", "Reset All Settings" in names, names)
            check("top: the title and tabs are in a section that stays in place", fr.locator(".stickytop header.top nav.tabs").count() == 1 and fr.locator("header.top h1").count() == 1 and fr.locator(".sub").count() == 0
                  and fr.locator(".stickytop").evaluate("e => getComputedStyle(e).position") == "sticky")

            # ---- names and logo (the top card of the Look screen)
            check("look: Names and Logo and the colors of single cards start closed (less to scroll past)", fr.locator("details.card", has=fr.locator("summary b", has_text="Names and Logo")).get_attribute("open") is None and fr.locator("details.card", has=fr.locator("summary b", has_text="Service Cards")).get_attribute("open") is None)
            fr.locator("details.card > summary", has_text="Names and Logo").click()
            openmenu = lambda: fr.locator("details.logo-menu").evaluate("e => { e.open = true; e.closest('details.card').open = true; }")
            wrap = lambda: pg.evaluate("document.getElementById('widgets-wrap').textContent")
            fr.locator('input[aria-label="Server Name"]').fill("Vault")
            fr.locator('input[aria-label="Main Pool Name"]').fill("Data")
            fr.locator('input[aria-label="Backup Pool Name"]').fill("Spare")
            pg.wait_for_timeout(300)
            check("names: typed names show on the dashboard at once, also in 'Connect ... Drive'", "Vault" in wrap() and "HomeLab" not in wrap() and "Data" in wrap() and "Connect Spare Drive" in wrap() and "Main Pool" not in wrap(), wrap())
            check("names: an unsaved name is not written to the css", "--hl-name" not in p.read("custom.css"))
            openmenu()
            fr.locator('input[aria-label="Address of a logo picture on the web"]').fill("https://example.com/l.png")
            fr.locator("details.logo-menu").get_by_role("button", name="Use This Address").click()
            pg.wait_for_timeout(300)
            lg = "(() => { const e = document.getElementById('hl-logo'); return e ? [e.tagName, e.firstChild.getAttribute('src'), document.querySelector('#widgets-wrap > .widget-container').firstElementChild === e, e.firstChild.style.height] : null; })()"
            check("logo: a web address shows as the first thing of the top bar, without a link", pg.evaluate(lg) == ["SPAN", "https://example.com/l.png", True, "48px"], pg.evaluate(lg))
            fr.locator('input[aria-label="Web address the logo opens"]').fill("https://example.com/home")
            fr.locator('input[aria-label="Logo size"]').fill("70")
            pg.wait_for_timeout(300)
            got = pg.evaluate(lg)
            check("logo: a link makes it a link that opens in a new tab, and the size slider changes the height", got and got[0] == "A" and got[3] == "70px" and pg.evaluate("document.getElementById('hl-logo').getAttribute('target')") == "_blank", got)
            fr.get_by_role("button", name="Discard Changes").click()
            pg.wait_for_timeout(300)
            check("names: throw away brings the shipped names back and takes the logo off", "HomeLab" in wrap() and "Vault" not in wrap() and "Main Pool" in wrap() and "Connect Backup Drive" in wrap() and pg.evaluate(lg) is None, wrap())
            openmenu()
            fr.get_by_role("button", name="Use the Server logo").click()
            pg.wait_for_timeout(600)
            got = pg.evaluate(lg)
            check("logo: a ready-made logo is made into a picture and shown", got and got[1].startswith("data:image/png;base64,") and got[1] != "https://example.com/l.png", got)
            fr.get_by_role("button", name="Logo: On").click()
            pg.wait_for_timeout(300)
            check("logo: the Logo button turned off takes it off the dashboard (the logo itself is kept in the panel)", pg.evaluate(lg) is None and fr.get_by_role("button", name="Logo: Off").count() == 1 and fr.get_by_role("button", name="Remove Logo").count() == 0)
            fr.get_by_role("button", name="Logo: Off").click()
            pg.wait_for_timeout(300)
            check("logo: the Logo button turned on shows it again", pg.evaluate(lg) is not None)
            fr.locator('input[aria-label="Color of the built-in logos"]').evaluate("e => { e.value = '#ff0000'; e.dispatchEvent(new Event('input', {bubbles: true})); }")
            pg.wait_for_timeout(600)
            check("logo: another color redraws the ready-made logo, and the logos on offer show it", pg.evaluate(lg)[1].startswith("data:image/png") and "ff0000" in fr.locator(".logo-tile img").first.get_attribute("src").lower().replace("%23", "#"), fr.locator(".logo-tile img").first.get_attribute("src")[:200])
            fr.locator('details.logo-menu input[type=file]').set_input_files(files=[{"name": "l.png", "mimeType": "image/png", "buffer": PNG}])
            pg.wait_for_timeout(800)
            got = pg.evaluate(lg)
            check("logo: a picture from the computer is made small in the browser and shown", got and got[1].startswith("data:image/png;base64,"), got)
            fr.locator('input[aria-label="Server Name"]').fill("Vault")
            fr.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_timeout(800)
            css = p.read("custom.css")
            check("names: Save writes the names and the logo to custom.css", '--hl-name-homelab: "Vault";' in css and '--hl-logo-src: "data:image/png;base64,' in css, css[-400:])
            openmenu()
            fr.get_by_role("button", name="Logo: On").click()
            fr.get_by_role("button", name="Restore Original Names").click()
            fr.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_timeout(800)
            check("names: removing them and saving takes them out of custom.css again", "--hl-name" not in p.read("custom.css") and "--hl-logo" not in p.read("custom.css"), p.read("custom.css")[-300:])
            check("names: the shipped names are back on the dashboard", "HomeLab" in wrap() and pg.evaluate(lg) is None, wrap())

            # ---- transparent glass and the Colors screen
            ga = lambda: pg.evaluate("getComputedStyle(document.getElementById('inner_wrapper')).getPropertyValue('--lk-glass-a').trim()")
            fr.get_by_role("button", name="Transparent", exact=True).click()
            pg.wait_for_timeout(300)
            check("transparent: the level slider replaces the solid slider", fr.locator('input[aria-label="How Transparent"]').count() == 1 and fr.locator('input[aria-label="How Solid the Glass Is"]').count() == 0)
            fr.get_by_role("button", name="Very", exact=True).click()
            pg.wait_for_timeout(300)
            check("transparent: a level button changes the dashboard glass at once (80% -> 0.08)", ga() == "0.08", ga())
            fr.locator('input[aria-label="How Transparent"]').fill("100")
            pg.wait_for_timeout(200)
            check("transparent: 100% is fully clear", ga() == "0", ga())
            pg.wait_for_timeout(300)
            fr.locator("details.card > summary", has_text="Colors of Cards, Tiles and Bookmarks").click()
            fr.locator("details.card > summary", has_text="Service Cards").click()
            check("colors: the screen lists service cards and bookmarks", fr.get_by_text("Service Cards", exact=True).count() >= 1 and fr.get_by_text("Bookmarks", exact=True).count() >= 1)
            tsc = fr.locator('input[aria-label="Color of Tailscale"]')
            check("colors: a card's box shows its own default color, not one blue for all", tsc.input_value().lower() == "#248cff", tsc.input_value())
            pick = fr.locator('input[aria-label="One color for everything"]')
            pick.evaluate("e => { e.dataset.same = '1'; }")
            pick.fill("#223344")
            pg.wait_for_timeout(200)
            pick.fill("#336699")
            pg.wait_for_timeout(300)
            check("colors: the picker for everything stays the same element while you move (so it stays open)", fr.locator('input[aria-label="One color for everything"][data-same="1"]').count() == 1)
            tsc.evaluate("e => { e.dataset.same = '1'; }")
            tsc.fill("#ff8800")
            pg.wait_for_timeout(300)
            check("colors: a card's picker also stays put, and the row says Custom", fr.locator('input[aria-label="Color of Tailscale"][data-same="1"]').count() == 1
                  and fr.locator(".prow", has_text="Tailscale").locator(".badge").inner_text() == "Custom")
            fr.locator(".prow", has_text="Tailscale").get_by_role("button", name="Reset").click()
            check("colors: Reset puts the picker back to the color for everything", tsc.input_value().lower() == "#336699", tsc.input_value())
            check("colors: the Labels card is a dropdown that starts closed", fr.locator("details.card", has=fr.locator("summary b", has_text="Labels")).count() == 1 and fr.locator("details.card", has=fr.locator("summary b", has_text="Labels")).get_attribute("open") is None)
            fr.locator("details.card > summary", has_text="Labels").click()
            lab = fr.locator('input[aria-label="Text of Network & DNS"]')
            lab.evaluate("e => { e.dataset.same = '1'; }")
            lab.fill("#ffeeaa")
            pg.wait_for_timeout(300)
            check("colors: a label's picker stays put too", fr.locator('input[aria-label="Text of Network & DNS"][data-same="1"]').count() == 1)
            fr.get_by_role("button", name="Solid", exact=True).click()
            pg.wait_for_timeout(300)
            live = pg.evaluate("(document.getElementById('hl-live-look') || {}).textContent || ''")
            check("colors: Solid gives the same strength on both ends", re.search(r"--hl-a1:([0-9.]+);--hl-a2:\1;", live) is not None, live[-500:])
            fr.get_by_role("button", name="Gradient", exact=True).click()
            pg.wait_for_timeout(300)
            live = pg.evaluate("(document.getElementById('hl-live-look') || {}).textContent || ''")
            check("colors: Gradient fades out", re.search(r"--hl-a1:([0-9.]+);--hl-a2:(?!\1;)", live) is not None, live[-500:])
            pg.wait_for_timeout(100)
            pg.wait_for_timeout(300)
            live = pg.evaluate("(document.getElementById('hl-live-look') || {}).textContent || ''")
            check("colors: one color for everything is previewed", "51, 102, 153" in live and ".service-card" in live, live[-400:])
            fr.get_by_role("button", name="Circle Badge").click()
            pg.wait_for_timeout(300)
            live = pg.evaluate("(document.getElementById('hl-live-look') || {}).textContent || ''")
            check("colors: a label icon style is previewed", "border-radius:50%" in live, live[-400:])
            fr.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_timeout(800)
            css = p.read("custom.css")
            check("colors: Save writes the colors and the transparent glass", "51, 102, 153" in css and "--lk-glass-a: 0;" in css, css[-700:])
            fr.locator("details.card", has=fr.locator("summary b", has_text="Colors of Cards")).evaluate("e => { e.open = true; }")
            fr.get_by_role("button", name="Turn Off").first.click()
            fr.get_by_role("button", name="Discard Changes").click()
            pg.wait_for_timeout(300)
            p.req("POST", "/api/look", {"look": {"accent": "#5ec8ff", "radius": 8}})        # back to the look the next checks expect

            # ---- the background
            fr.locator('input[aria-label="Picture Brightness"]').fill("20")
            pg.wait_for_timeout(300)
            bf = pg.evaluate("document.getElementById('inner_wrapper').style.backdropFilter")
            check("background: a slider changes the dashboard's backdrop at once", "brightness(0.2)" in bf and "blur(12px)" in bf, bf)
            fr.locator('input[aria-label="Picture Blur"]').fill("0")
            pg.wait_for_timeout(300)
            bf = pg.evaluate("document.getElementById('inner_wrapper').style.backdropFilter")
            check("background: blur set to none is really no blur", "blur(0px)" in bf, bf)
            fr.locator('input[aria-label="Picture Blur"]').fill("3")
            fr.locator('input[aria-label="Picture Brightness"]').fill("20")
            pg.wait_for_timeout(300)
            fr.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_timeout(600)
            check("background: Save writes the sliders to settings.yaml", p.state_now()["background"]["brightness"] == 20)
            fr.locator('.card:has(h2:text-is("Background Picture")) input[type=file]').set_input_files({"name": "night.png", "mimeType": "image/png", "buffer": PNG})
            pg.wait_for_timeout(1000)
            check("background: an uploaded picture becomes the background", p.state_now()["background"]["image"].startswith("/images/background-"), p.state_now()["background"])
            fr.locator('input[aria-label="Picture address"]').fill("https://example.com/a.jpg")
            fr.locator('.card:has(h2:text-is("Background Picture"))').get_by_role("button", name="Use This Address").click()
            fr.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_timeout(600)
            check("background: a web address can be used", p.state_now()["background"]["image"] == "https://example.com/a.jpg")

            # ---- the layout
            fr.locator("nav.tabs").get_by_text("Layout", exact=True).click()
            sel = fr.locator('select[aria-label="Move Files & Photos to a tab"]')
            sel.select_option("Stats")
            fr.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_timeout(800)
            check("layout: a group is moved to another tab with a click", "  Files & Photos:\n    tab: Stats" in p.read("settings.yaml"), p.read("settings.yaml")[-900:])
            fr.locator('button[aria-label="Move Calendar up"]').click()
            fr.get_by_role("button", name="Discard Changes").click()
            check("layout: throw away forgets the change in progress", fr.get_by_role("button", name="Save", exact=True).is_disabled())

            # ---- cards
            fr.locator("nav.tabs").get_by_text("Cards", exact=True).click()
            fr.get_by_role("button", name="+ Add a Card", exact=True).click()
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
            fr.locator("dialog").get_by_role("button", name="Remove It").click()
            pg.wait_for_timeout(800)
            check("cards: a card is removed after the question", "Main router" not in p.read("services.yaml"))

            # ---- links (the link editor is its own frame: the drop-down card on the Links tab of the dashboard)
            check("links: the main panel no longer has a Links screen", fr.locator("nav.tabs").get_by_text("Links", exact=True).count() == 0)
            pg.evaluate("document.getElementById('linkpanel').src = document.getElementById('linkpanel').src")
            fr = pg.frame_locator("#linkpanel")
            fr.get_by_role("button", name="+ Add a Link", exact=True).wait_for(timeout=5000)
            check("links: the editor frame shows only the links (no tabs, no header)", fr.locator("nav.tabs").count() == 0 and fr.get_by_role("heading", name="Customize Your Dashboard").count() == 0)
            fr.get_by_role("button", name="+ Add a Link", exact=True).click()
            fr.locator('dialog input[aria-label="Name"]').fill("Indeed")
            fr.locator('dialog input[aria-label="Address"]').fill("https://www.indeed.com")
            fr.locator('dialog select[aria-label="Group"]').select_option("__new")
            fr.locator('dialog input[aria-label="New group name"]').fill("Job Hunt")
            fr.locator("dialog").get_by_role("button", name="Add", exact=True).click()
            pg.wait_for_timeout(800)
            check("links: a link in a new group is added", "- Job Hunt:" in p.read("bookmarks.yaml") and "href: https://www.indeed.com" in p.read("bookmarks.yaml"))
            check("links: the new group is on the Links tab", "  Job Hunt:\n    tab: Links" in p.read("settings.yaml"), p.read("settings.yaml")[-300:])

            # ---- undo (the Undo button is in the main panel)
            before = p.read("bookmarks.yaml")
            fr = pg.frame_locator("#panel")
            pg.evaluate("document.getElementById('panel').src = document.getElementById('panel').src")
            fr.get_by_role("button", name="Undo", exact=True).wait_for(timeout=5000)
            check("undo: the button names the last change when you point at it", fr.get_by_role("button", name="Undo", exact=True).get_attribute("title") == "Undo: Link added", fr.get_by_role("button", name="Undo", exact=True).get_attribute("title"))
            fr.get_by_role("button", name="Undo", exact=True).click()
            pg.wait_for_timeout(800)
            check("undo: the button brings the last change back", p.read("bookmarks.yaml") != before and "Job Hunt" not in p.read("bookmarks.yaml"))

            # ---- the dashboard refreshes by itself after a change when that is on
            pg.evaluate("window.__marker = 1")
            pg.evaluate("document.getElementById('linkpanel').src = document.getElementById('linkpanel').src")
            fr = pg.frame_locator("#linkpanel")
            fr.get_by_role("button", name="+ Add a Link", exact=True).wait_for(timeout=5000)
            [f for f in pg.frames if "only=links" in f.url][0].evaluate("localStorage.setItem('hlp-auto', '1')")      # (the setting of the main panel's checkbox, which this frame shares)
            fr.get_by_role("button", name="+ Add a Link", exact=True).click()
            fr.locator('dialog input[aria-label="Name"]').fill("Glassdoor")
            fr.locator('dialog input[aria-label="Address"]').fill("https://www.glassdoor.com")
            fr.locator("dialog").get_by_role("button", name="Add", exact=True).click()
            pg.wait_for_timeout(2500)
            check("refresh: after a change the dashboard page reloads itself (and the link editor is back)",
                  pg.evaluate("window.__marker") is None and pg.frame_locator("#linkpanel").get_by_role("heading", name="Links (Bookmarks)").count() == 1)

            # ---- a frame that is not the panel cannot change the page
            pg.evaluate("document.getElementById('stranger').contentWindow.eval(\"parent.postMessage({hlp:1,type:'css',css:'body{display:none}'},'*')\")")
            pg.wait_for_timeout(300)
            check("security: a frame that is not the panel cannot change the dashboard", pg.evaluate("document.getElementById('hl-live-look')") is None
                  and pg.evaluate("getComputedStyle(document.body).display") != "none")

            # ---- the page fits a phone
            ph = b.new_context(viewport={"width": 390, "height": 800}, is_mobile=True, has_touch=True).new_page()
            ph.goto("http://localhost:%d/" % p.port)
            ph.locator("input[type=password]").fill(tp.PW)
            ph.get_by_role("button", name="Log In").click()
            ph.locator("nav.tabs").wait_for(timeout=5000)
            for v in ("Look", "Layout", "Cards", "Drives"):
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
