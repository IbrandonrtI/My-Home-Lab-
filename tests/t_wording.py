#!/usr/bin/env python3
"""The words Homepage writes itself, as custom.js says them: the error line of a service card and the pill of an empty pool.
Run: python3 tests/t_wording.py   (last line is OK or FAIL). Needs playwright with chromium (skipped without)."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, "..", "homepage-config", "custom.js")
try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("skipped: playwright is not available")
    print("OK")
    sys.exit(0)

PAGE = """<html><body><div id="inner_wrapper">
<div id="information-widgets">
  <div class="widget-container"><div class="information-widget-resource"><svg></svg><div>Main Pool</div><div>12%</div></div></div>
  <div class="widget-container"><div class="flex flex-col justify-center" id="empty"><div class="flex flex-row self-center"><div class="flex flex-col justify-center"><div class="flex flex-row items-center"><svg></svg><div class="flex flex-col ml-3"><span class="primary-text" id="err">API Error</span></div></div></div></div><div class="ml-6 pt-1 text-center">Connect Backup Drive</div></div></div>
  <div class="widget-container"><div class="flex flex-col justify-center" id="named"><div class="flex flex-row items-center"><svg></svg><div class="flex flex-col ml-3"><span class="primary-text" id="err2">API Error</span></div></div><div class="ml-6 pt-1 text-center">Connect Photos Drive</div></div></div>
  <div class="widget-container"><div class="flex flex-col justify-center" id="other"><div class="flex flex-row items-center"><svg></svg><div class="flex flex-col ml-3"><span class="primary-text" id="err3">API Error</span></div></div><div class="ml-6 pt-1 text-center">Network</div></div></div>
</div>
<ul>
  <li class="service" id="nc"><details><summary><div><svg></svg>API Error Information</div></summary><p>x</p></details></li>
  <li class="service" id="ok"><details><summary><div>Fine</div></summary></details></li>
</ul></div></body></html>"""

bad = 0


def check(name, cond, got=""):
    global bad
    if not cond:
        bad += 1
        print("FAIL", name, got)


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.set_content(PAGE)
    # Homepage writes the error line as separate pieces of text: "API Error", " ", "Information"
    pg.evaluate("""() => { const d = document.querySelector('#nc summary div'); d.lastChild.remove(); d.append('API Error', ' ', 'Information'); }""")
    pg.add_script_tag(path=JS)
    pg.wait_for_timeout(400)
    check("a card's 'API Error Information' says Service Unavailable", pg.inner_text("#nc summary div").strip() == "Service Unavailable", pg.inner_text("#nc summary div"))
    check("an empty pool's pill says No Drive, not API Error", pg.inner_text("#err") == "No Drive", pg.inner_text("#err"))
    check("... also with a name you chose", pg.inner_text("#err2") == "No Drive", pg.inner_text("#err2"))
    check("another pill's error is left alone", pg.inner_text("#err3") == "API Error", pg.inner_text("#err3"))
    check("a good card is not touched", pg.inner_text("#ok summary div") == "Fine")
    b.close()

print("OK" if bad == 0 else "FAIL (%d)" % bad)
sys.exit(1 if bad else 0)
