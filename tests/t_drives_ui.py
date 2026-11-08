#!/usr/bin/env python3
"""Test of the Drives tab in the panel's page (panel/ui) with the real panel server and a FAKE drives tool (tests/fake_drives.py).
Looks at: the tab, the pools and drives, the Health and Check drop down under each connected drive, the dialogs of Add, Erase, Move and Take Out
(their questions, warnings and typed confirmations), what is sent to the drives tool, and that the page fits a phone.
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


def act(row, name):      # open the drive's menu (the three dots) and click one item
    row.locator("details.kebab > summary").first.click()
    row.get_by_role("menuitem", name=name, exact=True).click()


def main():
    tmp = tempfile.mkdtemp(prefix="hldrui-")
    log = os.path.join(tmp, "drives.log")
    env = {"HLP_DRIVES": os.path.join(HERE, "fake_drives.py"), "FAKE_DRIVES_LOG": log}
    p = tp.Panel(tmp, env)
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
                pg.wait_for_selector("text=Main Storage")

                def menu_of(name, pg=pg):      # the items of a drive's menu (the menu is closed, so its text is read from the page, not from the screen)
                    return pg.eval_on_selector_all(".drow:has-text('%s') .kmenu button" % name, "els => els.map(e => e.textContent)")

                body = pg.inner_text("#app")
                check("%s: the pools show with their state" % label, "Main Storage" in body and "Backup Storage" in body and "Online" in body and "Offline" in body, body[:300])
                check("%s: each pool is a card with a usage ring (25%%) and its drives in a tree below it" % label, pg.locator("details.pool svg.ring").count() == 1 and pg.locator("details.pool svg.ring").get_attribute("aria-label") == "25 percent used" and pg.locator("details.pool .tree .drow").count() == 4, pg.locator("details.pool .tree .drow").count())
                check("%s: temperature, health, hours on, model and serial show on the row without clicking anything" % label,
                      all(x in body for x in ("61 °C", "Failing", "12,345", "TOSHIBA DT01ACA100", "Serial X7ABCDEF")), body[:900])
                check("%s: the spare drive is in the Unassigned Disks card" % label, pg.locator("details.pool:has-text('Unassigned Disks') .drow:has-text('Cruzer')").count() == 1, "")
                check("%s: each drive has a three dots menu; a pool drive offers Move and Take Out, the spare offers Add and Erase" % label,
                      menu_of("1 TB Toshiba") == ["Rename", "Put to Sleep", "Move to Backup", "Take Out"]
                      and menu_of("Cruzer") == ["Add to Main", "Add to Backup", "Erase"], menu_of("1 TB Toshiba"))
                check("%s: the menu is closed until the dots are pressed" % label, pg.locator("details.kebab[open]").count() == 0, "")
                check("%s: the drives show with role, state and space" % label, "1 TB Toshiba HDD" in body and "Missing" in body and "250 GB used, 750 GB free" in body, body[:700])
                check("%s: the spare drive shows as not connected to a pool" % label, "63 GB Cruzer HDD" in body and "Not connected to a pool" in body, body[:900])
                check("%s: the last backup and the boot drive space show" % label, "Last backup: Never" in body and "boot drive" in body, body[-400:])
                btns = pg.eval_on_selector_all("#app > div > .card button, #app button", "els => els.map(e => e.textContent.trim())")
                want = ("Rename", "Put to Sleep", "Move to Backup", "Take Out", "Add to Main", "Add to Backup", "Erase", "Mount the Drives Again")
                check("%s: the drive buttons are there: %s" % (label, ", ".join(want)), all(b in btns for b in want), btns)
                check("%s: Health and Quick Check are not separate cards any more" % label, "Run Quick Check" not in " ".join(pg.eval_on_selector_all("#app > div > .card > h2", "els => els.map(e => e.textContent)")) and pg.locator("h2:has-text('Health')").count() == 0, "")
                check("%s: a Health and Check drop down sits under each connected drive (2), closed" % label,
                      pg.locator("details.dcheck").count() == 2 and pg.locator("details.dcheck[open]").count() == 0, pg.locator("details.dcheck").count())
                check("%s: no Save or Undo bar on this tab" % label, "Save" not in btns and "Undo" not in btns, btns)
                check("%s: the page does not scroll sideways" % label, pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]"))
                if SHOTS:
                    pg.screenshot(path=os.path.join(SHOTS, "drives-%s.png" % label), full_page=True)
                n = len(calls())
                # ---- health and quick check in the drop down of the first drive
                first = pg.locator("details.dcheck").first
                first.locator("summary").click()
                first.get_by_role("button", name="Check Health").click()
                pg.wait_for_selector("details.dcheck[open] >> text=Failing")
                t = first.inner_text()
                check("%s: Health shows inside the drive: failing, with its facts" % label, "Failing" in t and "61 °C" in t and "12,345 hours on" in t and "Copy its files to another drive soon" in t, t)
                other_t = pg.locator("details.dcheck").nth(1)
                other_t.locator("summary").click()
                check("%s: the other drive's drop down shows that it has no health report" % label, "did not report anything" in other_t.inner_text(), other_t.inner_text())
                first.get_by_role("button", name="Run Quick Check").click()
                pg.wait_for_selector("details.dcheck .result b:has-text('Quick Check')")
                t = first.inner_text()
                check("%s: the quick check shows inside the drive: OK" % label, "Quick Check" in t and "OK" in t, t)
                check("%s: still no sideways scroll with results" % label, pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]"))
                if SHOTS:
                    pg.screenshot(path=os.path.join(SHOTS, "drives-%s-open.png" % label), full_page=True)

                n = len(calls())

                def dialog_text(pg=pg):
                    return pg.inner_text("dialog")

                def typed_inputs(pg=pg):
                    return pg.locator("dialog input[type=text]")

                def ok_button(pg=pg):
                    return pg.locator("dialog .actions button").last

                def wait_calls(words, secs=6, pg=pg):
                    for _ in range(int(secs * 10)):
                        if words in calls():
                            return True
                        pg.wait_for_timeout(100)
                    return False

                def after_job(pg=pg):
                    pg.wait_for_selector(".card.working", state="detached", timeout=15000)

                # ---- add the spare drive to Main: keep is the default, no typing; erase asks for two words
                row = pg.locator(".drow", has_text="Cruzer")
                act(row, "Add to Main")
                pg.wait_for_selector("dialog")
                check("%s: Add to Main offers keep and erase, keep first" % label, "Keep the files" in dialog_text() and "Erase the drive and format it" in dialog_text(), dialog_text())
                check("%s: keep needs no typing" % label, typed_inputs().count() == 0 and ok_button().is_enabled() and ok_button().inner_text() == "Add Drive", dialog_text())
                pg.locator("dialog input[type=radio][value=erase]").check()
                check("%s: erase asks for the drive name and ERASE, and the button waits" % label, typed_inputs().count() == 2 and ok_button().is_disabled() and ok_button().inner_text() == "Erase and Add Drive" and "permanently deleted" in dialog_text(), dialog_text())
                typed_inputs().nth(0).fill("/dev/sdx")
                typed_inputs().nth(1).fill("ERASE")
                check("%s: a wrong drive name keeps the button disabled" % label, ok_button().is_disabled(), "")
                typed_inputs().nth(0).fill("/dev/sdc")
                typed_inputs().nth(1).fill("erase")
                check("%s: lowercase erase keeps the button disabled" % label, ok_button().is_disabled(), "")
                typed_inputs().nth(1).fill("ERASE")
                check("%s: both words right: the button works" % label, ok_button().is_enabled(), "")
                if SHOTS:
                    pg.screenshot(path=os.path.join(SHOTS, "drives-%s-add.png" % label))
                pg.locator("dialog .actions button").first.click()
                pg.wait_for_selector("dialog", state="detached")
                check("%s: Cancel sends nothing" % label, len(calls()) == n, calls()[n:])
                act(row, "Add to Backup")
                pg.wait_for_selector("dialog")
                ok_button().click()
                check("%s: Add to Backup with keep sends it" % label, wait_calls(["panel", "add", "sdc", "backup", "keep"]), calls()[n:])
                after_job()
                check("%s: the page went on after the job" % label, pg.locator("text=Main Storage").count() == 1, "")

                # ---- erase the spare drive
                row = pg.locator(".drow", has_text="Cruzer")
                act(row, "Erase")
                pg.wait_for_selector("dialog")
                check("%s: Erase offers formatted or empty and asks for both words" % label, "A new, empty drive (formatted)" in dialog_text() and typed_inputs().count() == 2 and ok_button().is_disabled(), dialog_text())
                pg.locator("dialog input[type=radio][value=empty]").check()
                typed_inputs().nth(0).fill("/dev/sdc"); typed_inputs().nth(1).fill("ERASE")
                ok_button().click()
                check("%s: Erase (empty) sends the words" % label, wait_calls(["panel", "wipe", "sdc", "empty", "/dev/sdc", "ERASE"]), calls()[n:])
                after_job()

                # ---- move the first pool drive (it has files, there is another Main drive)
                row = pg.locator(".drow", has_text="1 TB Toshiba")
                act(row, "Move to Backup")
                pg.wait_for_selector("dialog")
                d = dialog_text()
                check("%s: Move asks what happens to the files and whether to copy them first" % label, "What should happen to the files on this drive?" in d and "Copy its files to the other main drives first?" in d, d)
                check("%s: Move (keep, copy first) asks for KEEP only" % label, typed_inputs().count() == 1 and "KEEP" in d and ok_button().is_disabled() and ok_button().inner_text() == "Move Drive", d)
                pg.locator("dialog input[type=radio][name=dq-copy][value=no]").check()
                check("%s: not copying adds CONTINUE" % label, typed_inputs().count() == 2 and "CONTINUE" in dialog_text(), dialog_text())
                pg.locator("dialog input[type=radio][name=dq-keep][value=erase]").check()
                d = dialog_text()
                check("%s: erase + no copy says the files are lost and asks for the drive name, ERASE and CONTINUE" % label, typed_inputs().count() == 3 and "permanently lost" in d and ok_button().inner_text() == "Erase and Move Drive", d)
                if SHOTS:
                    pg.screenshot(path=os.path.join(SHOTS, "drives-%s-move.png" % label))
                for i, w in enumerate(("/dev/sdb", "ERASE", "CONTINUE")):
                    typed_inputs().nth(i).fill(w)
                check("%s: all three words typed: the button works" % label, ok_button().is_enabled(), "")
                ok_button().click()
                check("%s: Move (erase, no copy) sends all words" % label, wait_calls(["panel", "move", "MAIN1", "erase", "no", "/dev/sdb", "ERASE", "CONTINUE"]), calls()[n:])
                after_job()
                row = pg.locator(".drow", has_text="1 TB Toshiba")
                act(row, "Move to Backup")
                pg.wait_for_selector("dialog")
                typed_inputs().nth(0).fill("KEEP")
                ok_button().click()
                check("%s: Move (keep, copy first) sends KEEP" % label, wait_calls(["panel", "move", "MAIN1", "keep", "yes", "KEEP"]), calls()[n:])
                after_job()

                # ---- take a drive out: one with files asks about copying, one without does not
                row = pg.locator(".drow", has_text="1 TB Toshiba")
                act(row, "Take Out")
                pg.wait_for_selector("dialog")
                d = dialog_text()
                check("%s: Take Out (with files) offers to copy them first, recommended" % label, "Copy them to another main drive first (recommended)" in d and typed_inputs().count() == 0 and ok_button().is_enabled(), d)
                pg.locator("dialog input[type=radio][value=no]").check()
                check("%s: not copying asks for CONTINUE" % label, typed_inputs().count() == 1 and ok_button().is_disabled(), dialog_text())
                typed_inputs().nth(0).fill("CONTINUE")
                ok_button().click()
                check("%s: Take Out (no copy) sends CONTINUE" % label, wait_calls(["panel", "disconnect", "MAIN1", "no", "CONTINUE"]), calls()[n:])
                after_job()
                row = pg.locator(".drow", has_text="2 TB Seagate HDD 2")
                act(row, "Take Out")
                pg.wait_for_selector("dialog")
                check("%s: Take Out (no files) has no question and no typing" % label, "Copy them" not in dialog_text() and typed_inputs().count() == 0 and ok_button().is_enabled(), dialog_text())
                ok_button().click()
                check("%s: Take Out (no files) sends it" % label, wait_calls(["panel", "disconnect", "MAIN2", "no"]), calls()[n:])
                after_job()
                check("%s: no page errors" % label, not errors, errors)
                ctx.close()
            # ---- a pool with only one drive: the only Main drive cannot be moved or taken out
            p.stop()
            p.env["FAKE_DRIVES_MODE"] = "single"
            p.start()
            ctx = br.new_context(viewport={"width": 1280, "height": 900})
            pg = ctx.new_page()
            pg.goto("http://127.0.0.1:%d/" % p.port)
            pg.fill("input[type=password]", tp.PW)
            pg.click("text=Log In")
            pg.wait_for_selector("nav.tabs")
            pg.click("nav.tabs button:has-text('Drives')")
            pg.wait_for_selector("text=Main Storage")
            m = len(calls())
            act(pg.locator(".drow", has_text="1 TB Toshiba"), "Take Out")
            pg.wait_for_selector("dialog")
            check("single: the only Main drive cannot be taken out (only a Close button)", "only Main drive" in pg.inner_text("dialog") and pg.locator("dialog .actions button").last.inner_text() == "Close", pg.inner_text("dialog"))
            pg.locator("dialog .actions button").last.click()
            act(pg.locator(".drow", has_text="1 TB Toshiba"), "Move to Backup")
            pg.wait_for_selector("dialog")
            check("single: the only Main drive cannot be moved either", "only Main drive" in pg.inner_text("dialog") and pg.locator("dialog .actions button").last.inner_text() == "Close", pg.inner_text("dialog"))
            pg.locator("dialog .actions button").last.click()
            check("single: nothing was sent", len(calls()) == m, calls()[m:])
            # remount: the box asks first; Cancel sends nothing
            pg.click("button:has-text('Mount the Drives Again')")
            pg.wait_for_selector("dialog")
            pg.click("dialog button:has-text('Cancel')")
            pg.wait_for_timeout(300)
            check("remount: Cancel sends nothing", len(calls()) == m, calls()[m:])
            pg.click("button:has-text('Mount the Drives Again')")
            pg.wait_for_selector("dialog")
            pg.click("dialog button:has-text('Mount Again')")
            for _ in range(50):
                if ["panel", "remount"] in calls()[m:]:
                    break
                pg.wait_for_timeout(100)
            check("remount: Mount Again sends remount", ["panel", "remount"] in calls()[m:], calls()[m:])
            # rename (a quick action)
            pg.wait_for_selector(".card.working", state="detached")
            act(pg.locator(".drow", has_text="1 TB Toshiba"), "Rename")
            pg.wait_for_selector("dialog input")
            pg.fill("dialog input", "bad/name")
            pg.click("dialog button:has-text('OK')")
            pg.wait_for_selector("#toast.show.bad")
            check("rename: a bad name is refused on the page, nothing is sent", not any(c[1] == "rename" for c in calls()), calls()[m:])
            act(pg.locator(".drow", has_text="1 TB Toshiba"), "Rename")
            pg.wait_for_selector("dialog input")
            pg.fill("dialog input", "Photos Drive")
            pg.click("dialog button:has-text('OK')")
            for _ in range(50):
                if ["panel", "rename", "MAIN1", "Photos Drive"] in calls():
                    break
                pg.wait_for_timeout(100)
            check("rename: Rename sends the label and the name", ["panel", "rename", "MAIN1", "Photos Drive"] in calls(), calls()[m:])
            ctx.close()
            br.close()
    finally:
        p.stop()
    ok = all(results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
