#!/usr/bin/env python3
"""Test of the Updates tab (panel/ui) with the real panel server and FAKE update commands (nothing real is run).
Looks at: the tab is there and the bell's link (#updates) opens it, what is waiting, Check Now and Update buttons running a job with its lines,
the restart asking first, "up to date" when nothing waits, and that the screen fits a phone.
Needs Playwright with Chromium; without it the test says so and passes.   Run: python3 tests/t_updates_ui.py   (last line is OK or FAIL)
Set UPDATES_SHOTS=/some/folder to also keep screenshots."""
import json
import os
import shutil
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
SHOTS = os.environ.get("UPDATES_SHOTS")


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   " + str(extra)))


def main():
    tmp = tempfile.mkdtemp(prefix="hlupdui-")
    state = os.path.join(tmp, "hlstate")
    os.makedirs(state)
    slow = os.path.join(tmp, "slow.sh")
    with open(slow, "w") as f:
        f.write("#!/bin/sh\necho 'updating immich'\nsleep 2\necho 'all done'\n")
    os.chmod(slow, 0o755)
    steps = {"check": [[slow]], "containers": [[slow]], "system": [[slow]], "restart": [[slow]]}
    reboot = os.path.join(tmp, "reboot-required")
    with open(os.path.join(state, "image-updates"), "w") as f:
        f.write("1700000000\nimmich  ghcr.io/immich=new\nnextcloud  nc=new\n")
    with open(os.path.join(state, "apt"), "w") as f:
        f.write("7|2\n")
    open(reboot, "w").close()
    p = tp.Panel(tmp, {"HLP_UPDATE_STATE": state, "HLP_REBOOT_FILE": reboot, "HLP_UPDATE_STEPS": json.dumps(steps), "HLP_DRIVES": os.path.join(HERE, "fake_drives.py"),
                       "FAKE_DRIVES_LOG": os.path.join(tmp, "drives.log"), "HLP_BACKUP": os.path.join(tmp, "no-such-tool")})
    p.set_password()
    p.start()

    def shot(pg, name):
        if SHOTS:
            os.makedirs(SHOTS, exist_ok=True)
            pg.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=True)

    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            ctx = br.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto("http://127.0.0.1:%d/#updates" % p.port)
            pg.fill("input[type=password]", tp.PW)
            pg.click("text=Log In")
            pg.wait_for_selector("nav.tabs")
            pg.wait_for_selector(".upd h2")
            check("updates: the link from the bell (#updates) opens the Updates tab", pg.get_attribute("nav.tabs button[aria-selected=true]", "role") == "tab" and "Updates" in pg.inner_text("nav.tabs button[aria-selected=true]"))
            pg.locator(".upd .bkt").first.wait_for()
            txt = pg.inner_text(".upd")
            check("updates: the waiting containers are named", "2 waiting" in txt and "immich, nextcloud" in txt, txt)
            check("updates: the system count and the restart need are shown", "7 waiting" in txt and "Needed" in txt, txt)
            shot(pg, "1-waiting")
            pg.locator(".upd .bkt").first.locator("button:has-text('Update Containers')").click()
            pg.wait_for_selector(".updlog")
            check("updates: a running update shows its progress and locks the other buttons", pg.locator(".upd button:has-text('Update System')").is_disabled() if pg.locator(".upd button:has-text('Update System')").count() else True)
            pg.locator(".upd .updlog").filter(has_text="updating immich").wait_for(timeout=10000)
            shot(pg, "2-running")
            pg.locator(".upd .updlog").wait_for(state="detached", timeout=15000)
            pg.locator(".toast, #toast").filter(has_text="all done").wait_for(timeout=8000)
            check("updates: when it ends the last line is told", True)
            pg.locator(".upd .bkt").nth(2).locator("button:has-text('Restart Machine')").click()
            pg.locator("dialog").filter(has_text="Restart the machine?").wait_for()
            check("updates: a restart asks first", pg.locator("dialog button:has-text('Restart Now')").count() == 1)
            pg.locator("dialog button:has-text('Cancel')").click()
            check("updates: Cancel starts nothing", pg.locator(".updlog").count() == 0)
            # all up to date
            os.remove(os.path.join(state, "image-updates"))
            with open(os.path.join(state, "apt"), "w") as f:
                f.write("0|0\n")
            os.remove(reboot)
            pg.locator(".upd .ph button:has-text('Refresh')").click()
            pg.locator(".upd .pill", has_text="Not needed").wait_for()
            txt = pg.inner_text(".upd")
            check("updates: nothing waiting says up to date and the update buttons are off", txt.count("Up to date") == 2 and pg.locator(".upd button:has-text('Update Containers')").is_disabled() and pg.locator(".upd button:has-text('Update System')").is_disabled(), txt)
            shot(pg, "3-uptodate")
            ph = br.new_context(viewport={"width": 390, "height": 800}, device_scale_factor=1).new_page()
            ph.goto("http://127.0.0.1:%d/#updates" % p.port)
            ph.fill("input[type=password]", tp.PW)
            ph.click("text=Log In")
            ph.wait_for_selector(".upd .bkt")
            check("updates: the screen fits a phone", ph.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            check("updates: no script errors", not errors, errors)
            br.close()
    finally:
        p.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    ok = all(results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
