#!/usr/bin/env python3
"""Test of the Drives tab in the panel's page (panel/ui) with the real panel server and a FAKE drives tool (tests/fake_drives.py).
Looks at: the tab is there, the pools and drives show with their states, Rename / Sleep / Automatic Name / Mount Again send the right words,
Health and Quick Check show their rows, nothing can erase or remove a drive, and the page fits a phone (no sideways scroll).
Needs Playwright with Chromium; without it the test says so and passes.   Run: python3 tests/t_drives_ui.py   (last line is OK or FAIL)
Set DRIVES_SHOTS=/some/folder to also keep screenshots."""
import json
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
sys.path.insert(0, HERE)
import t_panel as tp  # noqa: E402

results = []
SHOTS = os.environ.get("DRIVES_SHOTS")


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   " + str(extra)))


def main():
    tmp = tempfile.mkdtemp(prefix="hldrui-")
    log = os.path.join(tmp, "drives.log")
    p = tp.Panel(tmp, {"HLP_DRIVES": os.path.join(HERE, "fake_drives.py"), "FAKE_DRIVES_LOG": log})
    p.set_password()
    p.start()

    def calls():
        if not os.path.exists(log):
            return []
        with open(log) as f:
            return [json.loads(x) for x in f if x.strip()]

    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for label, vp in (("desktop", {"width": 1280, "height": 900}), ("phone", {"width": 390, "height": 800})):
                ctx = br.new_context(viewport=vp, device_scale_factor=1)
                pg = ctx.new_page()
                errors = []
                pg.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                pg.goto("http://127.0.0.1:%d/" % p.port)
                pg.fill("input[type=password]", tp.PW)
                pg.click("text=Log In")
                pg.wait_for_selector("nav.tabs")
                tabs = pg.eval_on_selector_all("nav.tabs button", "els => els.map(e => e.textContent)")
                check("%s: the tabs are Look, Layout, Cards, Drives" % label, tabs == ["Look", "Layout", "Cards", "Drives"], tabs)
                pg.click("nav.tabs button:has-text('Drives')")
                pg.wait_for_selector("text=Storage Pools")
                body = pg.inner_text("#app")
                check("%s: the pools show with their state" % label, "Main Storage" in body and "Backup Storage" in body and "Mounted" in body and "Not Mounted" in body, body[:300])
                check("%s: the drives show with role, state and space" % label, "1 TB Toshiba HDD" in body and "Missing" in body and "232.8 GB" not in body and "GB used" in body.replace("used,", "used"), body[:600])
                check("%s: the last backup and the boot drive space show" % label, "Last backup: Never" in body and "boot drive" in body, body[-400:])
                btns = pg.eval_on_selector_all("#app button", "els => els.map(e => e.textContent.trim())")
                check("%s: the buttons are there: Rename, Automatic Name, Put to Sleep, Check Health, Run Quick Check, Mount the Drives Again" % label,
                      all(b in btns for b in ("Rename", "Automatic Name", "Put to Sleep", "Check Health", "Run Quick Check", "Mount the Drives Again")), btns)
                check("%s: nothing offers to erase, remove, move or eject a drive" % label, not any(w in " ".join(btns).lower() for w in ("erase", "wipe", "remove", "disconnect", "eject", "format", "move")), btns)
                check("%s: no Save or Undo bar on this tab" % label, "Save" not in btns and "Undo" not in btns, btns)
                check("%s: the page does not scroll sideways" % label, pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]"))
                if SHOTS:
                    pg.screenshot(path=os.path.join(SHOTS, "drives-%s.png" % label), full_page=True)
                n = len(calls())
                # rename
                pg.click("button:has-text('Rename')")
                pg.wait_for_selector("dialog input")
                pg.fill("dialog input", "bad/name")
                pg.click("dialog button:has-text('OK')")
                pg.wait_for_selector("#toast.show.bad")
                check("%s: a bad name is refused on the page, nothing is sent" % label, len(calls()) == n, calls()[n:])
                pg.click("button:has-text('Rename')")
                pg.wait_for_selector("dialog input")
                pg.fill("dialog input", "Photos Drive")
                pg.click("dialog button:has-text('OK')")
                for _ in range(50):
                    if ["panel", "rename", "MAIN1", "Photos Drive"] in calls():
                        break
                    pg.wait_for_timeout(100)
                check("%s: Rename sends the label and the name" % label, ["panel", "rename", "MAIN1", "Photos Drive"] in calls(), calls()[n:])
                pg.wait_for_selector("text=Storage Pools")
                # sleep
                pg.wait_for_selector(".card.working", state="detached")
                pg.click("button:has-text('Put to Sleep')")
                for _ in range(50):
                    if ["panel", "sleep", "sdb"] in calls():
                        break
                    pg.wait_for_timeout(100)
                check("%s: Put to Sleep sends the drive" % label, ["panel", "sleep", "sdb"] in calls(), calls()[n:])
                # automatic name (asks first)
                pg.wait_for_selector(".card.working", state="detached")
                pg.click("button:has-text('Automatic Name')")
                pg.wait_for_selector("dialog")
                pg.click("dialog button:has-text('Use Automatic Name')")
                for _ in range(50):
                    if ["panel", "rename", "BACKUP1", "auto"] in calls():
                        break
                    pg.wait_for_timeout(100)
                check("%s: Automatic Name asks first, then sends auto" % label, ["panel", "rename", "BACKUP1", "auto"] in calls(), calls()[n:])
                # health + check
                pg.wait_for_selector(".card.working", state="detached")
                pg.click("button:has-text('Check Health')")
                pg.wait_for_selector("text=Failing")
                body = pg.inner_text("#app")
                check("%s: Health shows the failing drive with its facts and a warning" % label, "61 °C" in body and "12,345 hours on" in body and "Copy its files to another drive soon" in body, body[-700:])
                pg.click("button:has-text('Run Quick Check')")
                pg.wait_for_selector("text=Problem")
                body = pg.inner_text("#app")
                check("%s: Quick Check shows each drive's result" % label, "It is not connected or not mounted" in body and "OK" in body, body[-500:])
                check("%s: still no sideways scroll with results" % label, pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]"))
                if SHOTS:
                    pg.screenshot(path=os.path.join(SHOTS, "drives-%s-results.png" % label), full_page=True)
                # remount: the box asks first; Cancel sends nothing
                m = len(calls())
                pg.click("button:has-text('Mount the Drives Again')")
                pg.wait_for_selector("dialog")
                pg.click("dialog button:has-text('Cancel')")
                pg.wait_for_timeout(300)
                check("%s: Cancel on the remount question sends nothing" % label, len(calls()) == m, calls()[m:])
                pg.click("button:has-text('Mount the Drives Again')")
                pg.wait_for_selector("dialog")
                pg.click("dialog button:has-text('Mount Again')")
                for _ in range(50):
                    if ["panel", "remount"] in calls()[m:]:
                        break
                    pg.wait_for_timeout(100)
                check("%s: Mount Again sends remount" % label, ["panel", "remount"] in calls()[m:], calls()[m:])
                check("%s: no page errors" % label, not errors, errors)
                ctx.close()
            br.close()
    finally:
        p.stop()
    ok = all(results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
