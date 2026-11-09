#!/usr/bin/env python3
"""Test of the Drives tab in the panel's page (panel/ui) with the real panel server and a FAKE drives tool (tests/fake_drives.py).
Looks at: the tab (a box of loose drives, a Main box and a Backup box; every drive is a tile with a symbol, a green or red dot, its name and its used space),
dragging tiles between the boxes, picking several tiles (Ctrl or Shift click, the Select button), the card that opens when a tile is pressed (health, temperature,
hours on, buttons), the dialogs of Add, Erase, Move and Take Out (their questions, warnings and the box to tick), what is sent to the drives tool,
the progress bar on each tile while a change runs, the "Go Ahead Anyway" question when a pool is being written to, and that the page fits a phone.
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
ROOT = os.path.dirname(HERE)
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
    env = {"HLP_DRIVES": os.path.join(HERE, "fake_drives.py"), "FAKE_DRIVES_LOG": log}
    p = tp.Panel(tmp, env)
    p.set_password()
    p.start()

    def calls():
        if not os.path.exists(log):
            return []
        with open(log) as f:
            return [json.loads(x) for x in f if x.strip()]

    def open_drives(br, w=1280, hgt=900):
        ctx = br.new_context(viewport={"width": w, "height": hgt}, device_scale_factor=1)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:%d/" % p.port)
        pg.fill("input[type=password]", tp.PW)
        pg.click("text=Log In")
        pg.wait_for_selector("nav.tabs")
        pg.click("nav.tabs button:has-text('Drives')")
        pg.wait_for_selector(".tile")
        return ctx, pg, errors

    def tile(pg, ident):
        return pg.locator(".tile[data-id='%s']" % ident)

    def dialog_text(pg):
        return pg.inner_text("dialog")

    def sure_box(pg):      # the "I understand" box that stands where typing used to be
        return pg.locator("dialog label.sure input[type=checkbox]")

    def ok_button(pg):
        return pg.locator("dialog .actions button").last

    def cancel_dialog(pg):
        pg.locator("dialog .actions button").first.click()
        pg.wait_for_selector("dialog", state="detached")

    def wait_calls(pg, words, secs=6):
        for _ in range(int(secs * 10)):
            if words in calls():
                return True
            pg.wait_for_timeout(100)
        return False

    def after_job(pg):
        pg.wait_for_selector(".card.working", state="detached", timeout=20000)

    def card_button(pg, ident, name):      # press the tile, then a button on its card
        tile(pg, ident).click()
        pg.wait_for_selector("dialog.dcard")
        pg.locator("dialog.dcard").get_by_role("button", name=name, exact=True).click()
        pg.wait_for_selector("dialog.dcard", state="detached")

    def move_to(pg, label, ident, zone, button):      # on the desktop a drag and drop; a phone has no mouse drag, so its card buttons do the same
        if label == "desktop":
            tile(pg, ident).drag_to(pg.locator(".zone-" + zone))
        else:
            card_button(pg, ident, button)

    def no_side_scroll(pg):
        return pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")

    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for label, (w, hgt) in (("desktop", (1280, 900)), ("phone", (390, 800))):
                ctx, pg, errors = open_drives(br, w, hgt)
                tabs = pg.eval_on_selector_all("nav.tabs button", "els => els.map(e => e.textContent)")
                check("%s: the tabs are Look, Layout, Cards, Drives" % label, tabs == ["Look", "Layout", "Cards", "Drives"], tabs)
                try:
                    pg.wait_for_selector(".tile .warnmark", timeout=15000)      # the health of each drive comes a moment after the list
                except Exception:
                    pass
                body = pg.inner_text("#app")
                # ---- the three boxes
                heads = pg.eval_on_selector_all(".dzone h2", "els => els.map(e => e.textContent)")
                check("%s: three boxes: Drives, Main Storage and Backup Storage" % label, heads == ["Drives", "Main Storage", "Backup Storage"], heads)
                check("%s: the spare drive is in the Drives box, the Main drives in Main, the other in Backup" % label,
                      ids_of(pg, "drives") == ["sdc"] and ids_of(pg, "main") == ["MAIN1", "MAIN2"] and ids_of(pg, "backup") == ["BACKUP1"], [ids_of(pg, "drives"), ids_of(pg, "main"), ids_of(pg, "backup")])
                check("%s: the Main box shows Online and its ring (25%%), the Backup box Offline" % label,
                      "Online" in body and "Offline" in body and pg.locator(".zone-main svg.ring").get_attribute("aria-label") == "25 percent used", body[:300])
                check("%s: the old tree, three dots menu and drop downs are gone" % label, pg.locator(".kebab, .trow, details.dcheck, details.pool").count() == 0, "")
                # ---- what a tile shows
                t1 = tile(pg, "MAIN1")
                check("%s: a tile has the name above a drive symbol and the used space below it" % label,
                      t1.locator(".tname").inner_text() == "1 TB Toshiba HDD" and t1.locator("svg.hdd").count() == 1 and "250 GB of" in t1.locator(".tused").inner_text()
                      and t1.locator(".tname").bounding_box()["y"] < t1.locator("svg.hdd").bounding_box()["y"] < t1.locator(".tused").bounding_box()["y"], t1.inner_text())
                dot, sym = t1.locator(".dot").bounding_box(), t1.locator(".ticon").bounding_box()
                check("%s: the dot sits at the top right of the symbol" % label, dot["x"] + dot["width"] / 2 > sym["x"] + sym["width"] * 0.8 and dot["y"] + dot["height"] / 2 < sym["y"] + sym["height"] * 0.3, [dot, sym])
                check("%s: a connected drive has a green dot, a missing one a red dot" % label, "ok" in t1.locator(".dot").get_attribute("class") and "bad" in tile(pg, "BACKUP1").locator(".dot").get_attribute("class"), "")
                check("%s: a long name is cut with dots (full name on hover)" % label, t1.locator(".tname").evaluate("e => getComputedStyle(e).textOverflow") == "ellipsis" and t1.get_attribute("title").startswith("1 TB Toshiba HDD"), "")
                check("%s: temperature and the other stats are not on the tile (they open with a press)" % label, "61" not in t1.inner_text() and "Failing" not in t1.inner_text(), t1.inner_text())
                check("%s: only a connected pool drive or a spare can be dragged; a missing one cannot" % label,
                      t1.get_attribute("draggable") == "true" and tile(pg, "sdc").get_attribute("draggable") == "true" and tile(pg, "BACKUP1").get_attribute("draggable") == "false", "")
                check("%s: the last backup and the boot drive space show" % label, "Last backup: Never" in body and "boot drive" in body, body[-400:])
                btns = pg.eval_on_selector_all("#app button", "els => els.map(e => e.textContent.trim())")
                check("%s: the bar has Select, Refresh and Mount the Drives Again; no Save or Undo" % label, all(b in btns for b in ("Select", "Refresh", "Mount the Drives Again")) and "Save" not in btns and "Undo" not in btns, btns)
                check("%s: the page does not scroll sideways" % label, no_side_scroll(pg), pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]"))
                if SHOTS:
                    pg.screenshot(path=os.path.join(SHOTS, "drives-%s.png" % label), full_page=True)
                # ---- the card of a pool drive
                n = len(calls())
                t1.click()
                pg.wait_for_selector("dialog.dcard")
                t = pg.inner_text("dialog.dcard")
                check("%s: pressing a drive opens its card with status, power, temperature, health, hours on, model and serial" % label,
                      all(x in t for x in ("Connected", "Awake", "61 °C", "Failing", "12,345", "TOSHIBA DT01ACA100", "Serial X7ABCDEF", "Main Storage")), t)
                cbtns = pg.eval_on_selector_all("dialog.dcard button", "els => els.map(e => e.textContent.trim())")
                check("%s: the card has the buttons Check Health, Quick Check, Rename, Put to Sleep, Move to Backup, Take Out" % label,
                      all(b in cbtns for b in ("Check Health Again", "Run Quick Check", "Rename", "Put to Sleep", "Move to Backup", "Take Out", "Close")), cbtns)
                pg.get_by_role("button", name="Check Health Again").click()
                pg.wait_for_selector("dialog.dcard >> text=Copy its files to another drive soon")
                pg.get_by_role("button", name="Run Quick Check").click()
                pg.wait_for_selector("dialog.dcard .result b:has-text('Quick Check')")
                t = pg.inner_text("dialog.dcard")
                check("%s: Health and Quick Check show inside the card" % label, "Failing" in t and "Quick Check" in t and "OK" in t, t)
                check("%s: the card does not make the page scroll sideways" % label, no_side_scroll(pg), "")
                if SHOTS:
                    pg.screenshot(path=os.path.join(SHOTS, "drives-%s-card.png" % label))
                pg.locator("dialog.dcard .actions button").last.click()
                pg.wait_for_selector("dialog.dcard", state="detached")
                tile(pg, "MAIN2").click()
                pg.wait_for_selector("dialog.dcard")
                check("%s: a drive that reports nothing says so on its card" % label, "-" in pg.inner_text("dialog.dcard") and "Failing" not in pg.inner_text("dialog.dcard"), pg.inner_text("dialog.dcard"))
                pg.keyboard.press("Escape")
                pg.wait_for_selector("dialog.dcard", state="detached")
                tile(pg, "sdc").click()
                pg.wait_for_selector("dialog.dcard")
                cbtns = pg.eval_on_selector_all("dialog.dcard button", "els => els.map(e => e.textContent.trim())")
                check("%s: the spare drive's card offers Add to Main, Add to Backup and Erase" % label, all(b in cbtns for b in ("Add to Main", "Add to Backup", "Erase")), cbtns)
                pg.keyboard.press("Escape")
                pg.wait_for_selector("dialog.dcard", state="detached")

                # ---- add the spare drive: keep is the default, no typing; erase asks to tick one box
                n = len(calls())
                card_button(pg, "sdc", "Add to Main")
                pg.wait_for_selector("dialog")
                check("%s: Add to Main offers keep and erase, keep first" % label, "Keep the files" in dialog_text(pg) and "Erase the drive and format it" in dialog_text(pg), dialog_text(pg))
                check("%s: keep needs no typing and no box to tick" % label, pg.locator("dialog input[type=text]").count() == 0 and sure_box(pg).count() == 0 and ok_button(pg).is_enabled() and ok_button(pg).inner_text() == "Add Drive", dialog_text(pg))
                pg.locator("dialog input[type=radio][value=erase]").check()
                check("%s: erase asks to tick one box, and the button waits" % label, sure_box(pg).count() == 1 and ok_button(pg).is_disabled() and ok_button(pg).inner_text() == "Erase and Add Drive" and "permanently deleted" in dialog_text(pg), dialog_text(pg))
                sure_box(pg).check()
                check("%s: the box ticked: the button works" % label, ok_button(pg).is_enabled(), "")
                sure_box(pg).uncheck()
                check("%s: the box cleared: the button waits again" % label, ok_button(pg).is_disabled(), "")
                sure_box(pg).check()
                pg.locator("dialog input[type=radio][value=keep]").check()
                pg.locator("dialog input[type=radio][value=erase]").check()
                check("%s: changing the choice clears the box" % label, sure_box(pg).is_checked() is False and ok_button(pg).is_disabled(), "")
                if SHOTS:
                    pg.screenshot(path=os.path.join(SHOTS, "drives-%s-add.png" % label))
                cancel_dialog(pg)
                check("%s: Cancel sends nothing" % label, len(calls()) == n, calls()[n:])

                # ---- drag and drop: the spare drive into the Backup box
                move_to(pg, label, "sdc", "backup", "Add to Backup")
                pg.wait_for_selector("dialog")
                check("%s: dropping the spare drive in the Backup box asks about keeping its files" % label, "Add Drive to Backup Storage" in dialog_text(pg), dialog_text(pg))
                ok_button(pg).click()
                check("%s: the drop sends: add, keep" % label, wait_calls(pg, ["panel", "add", "sdc", "backup", "keep"]), calls()[n:])
                after_job(pg)
                check("%s: the message after a change is one short sentence" % label, pg.inner_text("#toast") == "63 GB Cruzer HDD was added to the Backup Storage.", pg.inner_text("#toast"))
                js_ = open(os.path.join(ROOT, "panel", "ui", "app.js"), encoding="utf-8").read()
                drive_code = js_[js_.index("async function jobFinished"):js_.index("// ---- a dialog with questions")]
                check("%s: a drive change does not reload the whole dashboard" % label, "reload" not in drive_code, "")
                m = len(calls())
                if label == "desktop":
                    tile(pg, "sdc").drag_to(pg.locator(".zone-drives"))
                    pg.wait_for_timeout(300)
                    check("%s: dropping a drive back where it is does nothing" % label, pg.locator("dialog").count() == 0 and len(calls()) == m, calls()[m:])
                    tile(pg, "MAIN1").drag_to(pg.locator(".zone-main"))
                    pg.wait_for_timeout(300)
                    check("%s: dropping a Main drive in the Main box does nothing" % label, pg.locator("dialog").count() == 0 and len(calls()) == m, calls()[m:])
                    tile(pg, "BACKUP1").drag_to(pg.locator(".zone-main"), force=True)
                    pg.wait_for_timeout(300)
                    check("%s: a missing drive cannot be dragged" % label, pg.locator("dialog").count() == 0 and len(calls()) == m, calls()[m:])
                    over = pg.evaluate("""async () => { const t = document.querySelector('.tile[data-id=sdc]'); t.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: new DataTransfer() }));
                      await new Promise(r => setTimeout(r, 350)); const r = { box: document.querySelector('.dzone.zone-backup'), own: document.querySelector('.dzone.zone-drives') }; const out = { backup: getComputedStyle(r.box).borderTopColor, own: getComputedStyle(r.own).borderTopColor };
                      t.dispatchEvent(new DragEvent('dragend', { bubbles: true })); return out; }""")
                    check("desktop: while a drive is dragged, the boxes that take it light up and the others do not", over["backup"] != over["own"], over)

                # ---- drag a Main drive into the Backup box: Move
                move_to(pg, label, "MAIN1", "backup", "Move to Backup")
                pg.wait_for_selector("dialog")
                d = dialog_text(pg)
                check("%s: Move asks what happens to the files and whether to copy them first" % label, "Move Drive to the Backup Storage" in d and "What should happen to the files on this drive?" in d and "Copy its files to the other main drives first?" in d, d)
                check("%s: Move (keep, copy first) has nothing to tick" % label, sure_box(pg).count() == 0 and ok_button(pg).is_enabled() and ok_button(pg).inner_text() == "Move Drive", d)
                pg.locator("dialog input[type=radio][name=dq-copy][value=no]").check()
                check("%s: not copying adds the box to tick" % label, sure_box(pg).count() == 1 and ok_button(pg).is_disabled() and "will lose the files of this drive" in dialog_text(pg), dialog_text(pg))
                pg.locator("dialog input[type=radio][name=dq-keep][value=erase]").check()
                d = dialog_text(pg)
                check("%s: erase + no copy says the files are lost" % label, "permanently lost" in d and "not copied anywhere" in d and ok_button(pg).inner_text() == "Erase and Move Drive" and ok_button(pg).is_disabled(), d)
                sure_box(pg).check()
                ok_button(pg).click()
                check("%s: Move (erase, no copy) sends all words" % label, wait_calls(pg, ["panel", "move", "MAIN1", "erase", "no", "/dev/sdb", "ERASE", "CONTINUE"]), calls()[n:])
                after_job(pg)
                card_button(pg, "MAIN1", "Move to Backup")
                pg.wait_for_selector("dialog")
                ok_button(pg).click()
                check("%s: Move (keep, copy first) sends KEEP by itself" % label, wait_calls(pg, ["panel", "move", "MAIN1", "keep", "yes", "KEEP"]), calls()[n:])
                after_job(pg)

                # ---- drag a Backup-less drive out of Main into the Drives box: Take Out
                move_to(pg, label, "MAIN1", "drives", "Take Out")
                pg.wait_for_selector("dialog")
                d = dialog_text(pg)
                check("%s: dropping a pool drive in the Drives box takes it out; with files it offers to copy them first" % label, "Take Drive Out of the Main Storage" in d and "Copy them to another main drive first (recommended)" in d and ok_button(pg).is_enabled(), d)
                pg.locator("dialog input[type=radio][value=no]").check()
                check("%s: not copying asks to tick the box" % label, sure_box(pg).count() == 1 and ok_button(pg).is_disabled(), dialog_text(pg))
                sure_box(pg).check()
                ok_button(pg).click()
                check("%s: Take Out (no copy) sends CONTINUE" % label, wait_calls(pg, ["panel", "disconnect", "MAIN1", "no", "CONTINUE"]), calls()[n:])
                after_job(pg)
                card_button(pg, "MAIN2", "Take Out")
                pg.wait_for_selector("dialog")
                check("%s: Take Out (no files) has no question and no box" % label, "Copy them" not in dialog_text(pg) and sure_box(pg).count() == 0 and ok_button(pg).is_enabled(), dialog_text(pg))
                ok_button(pg).click()
                check("%s: Take Out (no files) sends it" % label, wait_calls(pg, ["panel", "disconnect", "MAIN2", "no"]), calls()[n:])
                after_job(pg)

                # ---- erase the spare drive
                card_button(pg, "sdc", "Erase")
                pg.wait_for_selector("dialog")
                check("%s: Erase offers formatted or empty and asks to tick the box" % label, "A new, empty drive (formatted)" in dialog_text(pg) and sure_box(pg).count() == 1 and ok_button(pg).is_disabled(), dialog_text(pg))
                pg.locator("dialog input[type=radio][value=empty]").check()
                sure_box(pg).check()
                ok_button(pg).click()
                check("%s: Erase (empty) sends the words" % label, wait_calls(pg, ["panel", "wipe", "sdc", "empty", "/dev/sdc", "ERASE"]), calls()[n:])
                after_job(pg)

                # ---- picking several drives
                t1 = tile(pg, "MAIN1")
                t1.click(modifiers=["Control"])
                check("%s: Ctrl-click picks a drive instead of opening its card" % label, pg.locator("dialog").count() == 0 and "sel" in t1.get_attribute("class") and pg.locator(".selbar").count() == 1 and "1 Drive selected" in pg.inner_text(".selbar"), pg.inner_text("#app")[:200])
                tile(pg, "MAIN2").click(modifiers=["Shift"])
                sb = pg.inner_text(".selbar")
                check("%s: Shift-click picks another; the bar offers Move to Backup and Take Out" % label, "2 Drives selected" in sb and "Move to Backup" in sb and "Take Out" in sb, sb)
                tile(pg, "sdc").click(modifiers=["Control"])
                check("%s: a drive from another box cannot be picked together" % label, "Pick drives from one place" in pg.inner_text("#toast") and "sel" not in tile(pg, "sdc").get_attribute("class"), pg.inner_text("#toast"))
                if SHOTS:
                    pg.screenshot(path=os.path.join(SHOTS, "drives-%s-picked.png" % label), full_page=True)
                m = len(calls())
                pg.locator(".selbar").get_by_role("button", name="Move to Backup").click()
                pg.wait_for_selector("dialog")
                check("%s: moving all the Main drives is refused (at least one must stay)" % label, "These are all the Main drives" in dialog_text(pg) and ok_button(pg).inner_text() == "Close", dialog_text(pg))
                ok_button(pg).click()
                pg.wait_for_selector("dialog", state="detached")
                check("%s: nothing was sent" % label, len(calls()) == m, calls()[m:])
                check("%s: the picked drives stay picked after a Close or Cancel" % label, pg.locator(".tile.sel").count() == 2, "")
                pg.locator(".selbar").get_by_role("button", name="Clear").click()
                check("%s: Clear puts them back" % label, pg.locator(".selbar").count() == 0 and pg.locator(".tile.sel").count() == 0, "")
                pg.get_by_role("button", name="Select", exact=True).click()
                check("%s: the Select button turns picking on (pressed)" % label, pg.get_by_role("button", name="Done Selecting").get_attribute("aria-pressed") == "true", "")
                tile(pg, "MAIN2").click()
                check("%s: with Select on, a plain press picks a drive" % label, pg.locator("dialog").count() == 0 and "sel" in tile(pg, "MAIN2").get_attribute("class") and "1 Drive selected" in pg.inner_text(".selbar"), "")
                pg.locator(".selbar").get_by_role("button", name="Take Out").click()
                pg.wait_for_selector("dialog")
                check("%s: Take Out from the bar asks the same question for the picked drive" % label, "Take Drive Out of the Main Storage" in dialog_text(pg), dialog_text(pg))
                cancel_dialog(pg)
                pg.get_by_role("button", name="Done Selecting").click()
                check("%s: no page errors" % label, not errors, errors)
                ctx.close()

            # ---- two spare drives picked and added together; each tile gets its own progress bar
            p.stop()
            p.env["FAKE_DRIVES_MODE"] = "twospares"
            p.start()
            ctx, pg, errors = open_drives(br)
            check("two spares: both are in the Drives box", ids_of(pg, "drives") == ["sdc", "sde"], ids_of(pg, "drives"))
            tile(pg, "sdc").click(modifiers=["Control"])
            tile(pg, "sde").click(modifiers=["Control"])
            pg.locator(".selbar").get_by_role("button", name="Add to Main").click()
            pg.wait_for_selector("dialog")
            d = dialog_text(pg)
            check("two spares: one dialog asks about each drive; the one that cannot keep its files has to be erased", "Add 2 Drives to Main Storage" in d and "32 GB Kingston HDD" in d and "This drive has to be erased first" not in d and pg.locator("dialog input[type=radio][name='dq-m-sde'][value=keep]").count() == 0, d)
            check("two spares: erasing one asks to tick the box", sure_box(pg).count() == 1 and ok_button(pg).is_disabled() and ok_button(pg).inner_text() == "Erase and Add Drives", dialog_text(pg))
            if SHOTS:
                pg.screenshot(path=os.path.join(SHOTS, "drives-two-add.png"))
            cancel_dialog(pg)
            ctx.close()
            p.stop()
            p.env["FAKE_DRIVES_MODE"] = "jobslow,twospares"
            p.start(); p.login()
            ctx, pg, errors = open_drives(br)
            m = len(calls())
            tile(pg, "sdc").click(modifiers=["Control"])
            tile(pg, "sde").click(modifiers=["Control"])
            pg.locator(".selbar").get_by_role("button", name="Add to Backup").click()
            pg.wait_for_selector("dialog")
            pg.locator("dialog input[type=radio][name='dq-m-sdc'][value=erase]").check()
            sure_box(pg).check()
            ok_button(pg).click()
            check("two spares: the words are each drive with its choice, the backup pool, 'each', then the erase words",
                  wait_calls(pg, ["panel", "add", "sdc:erase,sde:erase", "backup", "each", "/dev/sdc", "/dev/sde", "ERASE"]), calls()[m:])
            pg.wait_for_selector(".tile.working .tprog", timeout=8000)
            check("progress: both picked tiles get a loading bar, the others do not", pg.locator(".tile .tprog").count() == 2 and tile(pg, "MAIN1").locator(".tprog").count() == 0, pg.locator(".tile .tprog").count())
            bar = tile(pg, "sdc").locator(".tprog")
            check("progress: a bar has words and is a progress bar for screen readers", bar.get_attribute("role") == "progressbar" and bar.inner_text().strip() != "", bar.inner_text())
            pg.wait_for_function("() => { const b = document.querySelector('.tile[data-id=sdc] .tprog'); return b && Number(b.getAttribute('aria-valuenow')) >= 60; }", timeout=15000)
            check("progress: the first drive's bar moves forward", int(bar.get_attribute("aria-valuenow")) >= 60, bar.get_attribute("aria-valuenow"))
            check("progress: the other tiles wait (dimmed and not draggable)", tile(pg, "MAIN1").get_attribute("draggable") == "false" and "dim" in tile(pg, "MAIN1").get_attribute("class"), "")
            if SHOTS:
                pg.screenshot(path=os.path.join(SHOTS, "drives-progress.png"), full_page=True)
            pg.wait_for_selector(".tile.working", state="detached", timeout=30000)
            after_job(pg)
            check("progress: when it is over the bars are gone and the list is fresh", pg.locator(".tprog").count() == 0 and pg.locator(".tile").count() >= 5, "")
            ctx.close()

            # ---- a page opened while a change is running shows its progress (no error), and the list comes by itself when it is over
            p.req("POST", "/api/drives/move", {"ids": ["MAIN1"], "keep": "keep", "copy": "yes", "typed": ["KEEP"]})
            ctx = br.new_context(viewport={"width": 1280, "height": 900})
            pg = ctx.new_page()
            pg.goto("http://127.0.0.1:%d/" % p.port)
            pg.fill("input[type=password]", tp.PW)
            pg.click("text=Log In")
            pg.wait_for_selector("nav.tabs")
            pg.click("nav.tabs button:has-text('Drives')")
            pg.wait_for_selector(".card.working", timeout=8000)
            check("busy: a page opened during a change shows its progress, not 'The Drives Could Not Be Read'", "Could Not Be Read" not in pg.inner_text("#app") and "Moving the drive" in pg.inner_text("#app"), pg.inner_text("#app")[:300])
            pg.wait_for_selector(".card.working", state="detached", timeout=25000)
            pg.wait_for_selector(".tile", timeout=10000)
            check("busy: the list comes by itself when the change is over", pg.locator(".tile").count() >= 3 and "Could Not Be Read" not in pg.inner_text("#app"), pg.inner_text("#app")[:300])
            ctx.close()

            # ---- a pool is being written to: say so, and offer to go ahead anyway
            p.stop()
            p.env["FAKE_DRIVES_MODE"] = "jobbusy"
            p.start()
            ctx, pg, errors = open_drives(br)
            m = len(calls())
            card_button(pg, "sdc", "Add to Backup")
            pg.wait_for_selector("dialog")
            ok_button(pg).click()
            pg.wait_for_selector("dialog:has-text('Go Ahead Anyway')", timeout=10000)
            d = dialog_text(pg)
            check("busy pool: the question says what is happening and nothing was changed", "Not a Good Moment" in d and "files are being written to a storage pool" in d.lower() and "Nothing was changed" in d, d)
            if SHOTS:
                pg.screenshot(path=os.path.join(SHOTS, "drives-busy.png"))
            pg.locator("dialog .actions button").first.click()
            pg.wait_for_selector("dialog", state="detached")
            check("busy pool: Cancel does not try again", not any("NOW" in c for c in calls()[m:]) and len([c for c in calls()[m:] if c[1] == "add"]) == 1, calls()[m:])
            card_button(pg, "sdc", "Add to Backup")
            pg.wait_for_selector("dialog")
            ok_button(pg).click()
            pg.wait_for_selector("dialog:has-text('Go Ahead Anyway')", timeout=10000)
            pg.get_by_role("button", name="Go Ahead Anyway").click()
            check("busy pool: Go Ahead Anyway sends the same change again with the word NOW", wait_calls(pg, ["panel", "add", "sdc", "backup", "keep", "NOW"]), calls()[m:])
            after_job(pg)
            check("busy pool: it then ends well", pg.inner_text("#toast") == "63 GB Cruzer HDD was added to the Backup Storage.", pg.inner_text("#toast"))
            ctx.close()

            # ---- the Abort button
            p.stop()
            p.env["FAKE_DRIVES_MODE"] = "jobslow"
            p.start(); p.login()
            ctx, pg, errors = open_drives(br)
            m = len(calls())
            card_button(pg, "MAIN1", "Move to Backup")
            pg.wait_for_selector("dialog")
            ok_button(pg).click()
            pg.wait_for_selector(".card.working button:has-text('Abort')", timeout=8000)
            check("abort: a running move shows an Abort button", pg.get_by_role("button", name="Abort", exact=True).count() == 1, pg.inner_text(".card.working"))
            if SHOTS:
                pg.screenshot(path=os.path.join(SHOTS, "drives-abort.png"))
            pg.get_by_role("button", name="Abort", exact=True).click()
            pg.wait_for_selector("dialog:has-text('Abort This Change?')")
            check("abort: it asks first and says what happens to the drives", "put back" in dialog_text(pg) and "stays where it is" in dialog_text(pg), dialog_text(pg))
            pg.locator("dialog .actions button").first.click()
            pg.wait_for_selector("dialog", state="detached")
            check("abort: Cancel does not stop anything", ["panel", "abort"] not in calls()[m:], calls()[m:])
            pg.get_by_role("button", name="Abort", exact=True).click()
            pg.wait_for_selector("dialog:has-text('Abort This Change?')")
            pg.locator("dialog .actions button").last.click()
            check("abort: Abort sends Stop to the tool", wait_calls(pg, ["panel", "abort"]), calls()[m:])
            pg.wait_for_selector(".card.working:has-text('Stopping')", timeout=8000)
            check("abort: the card says it is stopping and the button waits", pg.get_by_role("button", name="Stopping...").is_disabled(), pg.inner_text(".card.working"))
            pg.wait_for_selector(".card.working", state="detached", timeout=20000)
            t = pg.inner_text("#toast")
            check("abort: when it has stopped, the answer says what was stopped (and is not an error)", "Stopped as you asked" in t and "bad" not in (pg.get_attribute("#toast", "class") or ""), t)
            check("abort: the tiles are back to normal", pg.locator(".tile.working, .tprog").count() == 0 and tile(pg, "MAIN1").get_attribute("draggable") == "true", "")
            ctx.close()

            # ---- the files of the drives that leave do not fit on the drives that stay
            p.stop()
            p.env["FAKE_DRIVES_MODE"] = "tight"
            p.start()
            ctx, pg, errors = open_drives(br)
            m = len(calls())
            card_button(pg, "MAIN1", "Take Out")
            pg.wait_for_selector("dialog")
            d = dialog_text(pg)
            check("room: a take out that does not fit warns with the numbers", "not enough free room" in d and "250 GB to copy" in d and "1.0 GB free" in d and "A drive whose files do not fit is not taken out" in d, d)
            check("room: it can still be sent (the tool leaves the drive alone if it cannot copy)", ok_button(pg).is_enabled(), "")
            pg.locator("dialog input[type=radio][value=no]").check()
            check("room: choosing not to copy replaces the room warning with the usual one", "not enough free room" not in dialog_text(pg), dialog_text(pg))
            cancel_dialog(pg)
            ctx.close()

            # ---- a boot drive section: its status word fits in the card
            p.stop()
            p.env["FAKE_DRIVES_MODE"] = "bootsec"
            p.start()
            ctx, pg, errors = open_drives(br)
            tile(pg, "BACKUPBOOT").click()
            pg.wait_for_selector("dialog.dcard")
            pill = pg.locator("dialog.dcard .st:has-text('Status') .pill")
            box = pg.locator("dialog.dcard .st:has-text('Status')").bounding_box()
            pb = pill.bounding_box()
            check("boot section: the status word is just Connected", pill.inner_text() == "Connected", pill.inner_text())
            check("boot section: the status word stays inside its box", pb["x"] + pb["width"] <= box["x"] + box["width"] + 0.5, [pb, box])
            pg.keyboard.press("Escape")
            pg.wait_for_selector("dialog.dcard", state="detached")

            # ---- the Boot Drive tile: lend part of the boot drive to Main (Backup already has a section), move or take out the section
            check("boot tile: the Boot Drive tile is in the Drives box", tile(pg, "BOOTFREE").count() == 1 and "to lend" in tile(pg, "BOOTFREE").inner_text(), tile(pg, "BOOTFREE").inner_text())
            m = len(calls())
            tile(pg, "BOOTFREE").drag_to(pg.locator(".zone-main"))
            pg.wait_for_selector("dialog")
            d = dialog_text(pg)
            check("boot tile: dropping it on Main asks for a size with the limits", "Boot Drive for the Main Storage" in d and "10 to 30 GB" in d and "LAST place" in d, d)
            size = pg.locator("dialog input[type=number]")
            size.fill("5")
            check("boot tile: a size below the limit is refused", "whole number from 10 to 30" in dialog_text(pg) and ok_button(pg).is_disabled(), dialog_text(pg))
            size.fill("20")
            check("boot tile: the I-understand box is needed", sure_box(pg).count() == 1 and ok_button(pg).is_disabled(), "")
            sure_box(pg).check()
            check("boot tile: a good size and the box enable the button", ok_button(pg).is_enabled(), "")
            ok_button(pg).click()
            check("boot tile: the tool gets role, size and CONTINUE", wait_calls(pg, ["panel", "bootadd", "main", "20", "CONTINUE"]), calls()[m:])
            pg.wait_for_selector(".card.working", state="detached", timeout=20000)

            # Backup has a section already: the tile cannot go there, and Take Out of that section copies first
            tile(pg, "BOOTFREE").click()
            pg.wait_for_selector("dialog.dcard")
            btns = pg.locator("dialog.dcard button").all_inner_texts()
            check("boot tile: its card offers Add to Main and Add to Backup", "Add to Main" in btns and "Add to Backup" in btns, btns)
            check("boot tile: Add to Backup is greyed out because Backup already has a section", pg.locator("dialog.dcard").get_by_role("button", name="Add to Backup", exact=True).is_disabled(), "")
            pg.keyboard.press("Escape")
            pg.wait_for_selector("dialog.dcard", state="detached")
            m = len(calls())
            card_button(pg, "BACKUPBOOT", "Move to Main")
            pg.wait_for_selector("dialog")
            d = dialog_text(pg)
            check("boot section move: the choices talk about the space, not a drive", "Keep the files in the space" in d and "Start with a new, empty space" in d and "Erase the drive" not in d, d)
            pg.locator("dialog input[type=radio][value=erase]").check()
            d = dialog_text(pg)
            check("boot section move: erasing names the space, no device word", "the boot drive space will be permanently deleted" in d, d)
            cancel_dialog(pg)
            card_button(pg, "BACKUPBOOT", "Take Out")
            pg.wait_for_selector("dialog")
            d = dialog_text(pg)
            check("boot section take out: the files are copied first and the space goes back to the boot drive", "copied to the other backup drives first" in d.lower() or "nowhere to go" in d, d)
            check("boot section take out: no question about copying (it always copies)", pg.locator("dialog input[type=radio][value=no]").count() == 0, d)
            pg.locator("dialog .actions button").last.click() if ok_button(pg).is_disabled() or "nowhere to go" in d else cancel_dialog(pg)
            check("boot section: nothing but the first add was sent", [c for c in calls()[m:] if c[1] in ("move", "disconnect", "bootadd")] == [], calls()[m:])
            check("boot tile: only one Boot Drive tile (the system drive has no second tile of its own)", pg.locator(".tile:has-text('Boot Drive')").count() == 2 and pg.locator(".tile[data-id=BOOTFREE]").count() == 1, pg.locator(".tile").all_inner_texts())
            check("boot tile: the part in the pool is called Boot Drive Space", "Boot Drive Space" in tile(pg, "BACKUPBOOT").inner_text(), tile(pg, "BACKUPBOOT").inner_text())
            ctx.close()

            # ---- a boot drive space that is alone in its pool and holds files can still be taken out: its files are deleted, after a clear warning
            p.stop()
            p.env["FAKE_DRIVES_MODE"] = "bootsec-alone"
            p.start()
            ctx, pg, errors = open_drives(br)
            m = len(calls())
            card_button(pg, "BACKUPBOOT", "Move to Main")
            pg.wait_for_selector("dialog")
            d = dialog_text(pg)
            check("boot space alone: it can be moved to Main (keep its files), nothing is refused", "Keep the files in the space" in d and ok_button(pg).inner_text() == "Move Drive", d)
            sure_box(pg).check()
            ok_button(pg).click()
            check("boot space alone: the move is sent with KEEP and REMOVE (nothing to copy to)", wait_calls(pg, ["panel", "move", "BACKUPBOOT", "keep", "no", "KEEP", "REMOVE"]) or wait_calls(pg, ["panel", "move", "BACKUPBOOT", "keep", "yes", "KEEP", "REMOVE"]), calls()[m:])
            pg.wait_for_selector(".card.working", state="detached", timeout=20000)
            m = len(calls())
            card_button(pg, "BACKUPBOOT", "Take Out")
            pg.wait_for_selector("dialog")
            d = dialog_text(pg)
            check("boot space alone: taking it out warns that its files are permanently lost", "no other backup drive to copy the files" in d and "permanently lost" in d, d)
            check("boot space alone: it is not refused (a Cancel and a Take Out button, and the box to tick)", sure_box(pg).count() == 1 and ok_button(pg).is_disabled() and ok_button(pg).inner_text() == "Take Drive Out", d)
            sure_box(pg).check()
            ok_button(pg).click()
            check("boot space alone: it goes with the words ERASE and REMOVE and the files are not copied", wait_calls(pg, ["panel", "disconnect", "BACKUPBOOT", "yes", "ERASE", "REMOVE"]) or wait_calls(pg, ["panel", "disconnect", "BACKUPBOOT", "no", "ERASE", "REMOVE"]), calls()[m:])
            pg.wait_for_selector(".card.working", state="detached", timeout=20000)
            ctx.close()

            # ---- a change that fails leaves a "What Happened" card that stays until it is dismissed
            p.stop()
            p.env["FAKE_DRIVES_MODE"] = "jobfail"
            p.start()
            ctx, pg, errors = open_drives(br)
            card_button(pg, "sdc", "Add to Backup")
            pg.wait_for_selector("dialog")
            ok_button(pg).click()
            pg.wait_for_selector(".failcard", timeout=20000)
            pg.wait_for_timeout(9000)      # longer than a toast lasts
            fc = pg.inner_text(".failcard")
            check("failure card: it stays after the toast is gone and says what failed", "What Happened" in fc and "Adding the drive did not work" in fc and "Cancelled. Nothing was changed." in fc, fc)
            check("failure card: it has the steps and a Dismiss button", pg.locator(".failcard details summary").count() == 1 and pg.locator(".failcard button:has-text('Dismiss')").count() == 1, fc)
            check("failure card: no side scroll", no_side_scroll(pg), "")
            pg.click(".failcard button:has-text('Dismiss')")
            check("failure card: Dismiss removes it", pg.locator(".failcard").count() == 0, "")
            ctx.close()

            # ---- a pool with only one drive: the only Main drive cannot be moved or taken out
            p.stop()
            p.env["FAKE_DRIVES_MODE"] = "single"
            p.start()
            ctx, pg, errors = open_drives(br)
            m = len(calls())
            card_button(pg, "MAIN1", "Take Out")
            pg.wait_for_selector("dialog")
            d = pg.inner_text("dialog")
            check("single: the only Main drive CAN be taken out, with a warning that the services stay stopped", "Main storage will be empty" in d and "stay stopped until you add a Main drive again" in d and "nothing is deleted" in d, d)
            check("single: it needs the I-understand box", sure_box(pg).count() == 1 and ok_button(pg).is_disabled(), d)
            sure_box(pg).check()
            ok_button(pg).click()
            check("single: the drive goes out with the word REMOVE", wait_calls(pg, ["panel", "disconnect", "MAIN1", "no", "REMOVE"]), calls()[m:])
            pg.wait_for_selector(".card.working", state="detached", timeout=20000)
            m = len(calls())
            card_button(pg, "MAIN1", "Move to Backup")
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
            pg.wait_for_selector(".card.working", state="detached")
            # rename (a quick action) from the card
            card_button(pg, "MAIN1", "Rename")
            pg.wait_for_selector("dialog input")
            pg.fill("dialog input", "bad/name")
            pg.click("dialog button:has-text('OK')")
            pg.wait_for_selector("#toast.show.bad")
            check("rename: a bad name is refused on the page, nothing is sent", not any(c[1] == "rename" for c in calls()), calls()[m:])
            card_button(pg, "MAIN1", "Rename")
            pg.wait_for_selector("dialog input")
            pg.fill("dialog input", "Photos Drive")
            pg.click("dialog button:has-text('OK')")
            for _ in range(50):
                if ["panel", "rename", "MAIN1", "Photos Drive"] in calls():
                    break
                pg.wait_for_timeout(100)
            check("rename: Rename sends the label and the name", ["panel", "rename", "MAIN1", "Photos Drive"] in calls(), calls()[m:])
            ctx.close()
            # ---- Configure Drives: scan, a recommended setup, the others from best to worst, a confirmation before anything is erased
            for cfg_mode in ("ok", "blocked"):
                p.stop()
                p.env["FAKE_DRIVES_MODE"] = cfg_mode
                p.start()
                ctx, pg, errors = open_drives(br)
                m = len(calls())
                pg.click("button:has-text('Configure Drives')")
                pg.wait_for_selector(".cfg .cfgrec")
                txt = pg.inner_text(".cfg")
                check("configure (%s): the scan names the drives and the recommended setup" % cfg_mode, "Recommended: ZFS, RAIDZ1" in txt and "3 drives" in txt.replace("Scanned 3 drives", "3 drives"), txt[:300])
                opts = pg.eval_on_selector_all(".cfgsel option", "els => els.map(e => [e.textContent, e.disabled])")
                check("configure (%s): the dropdown lists the others from best to worst, the ones that do not fit are greyed out" % cfg_mode,
                      len(opts) == 4 and "SnapRAID" in opts[1][0] and "Plain pool" in opts[2][0] and "RAIDZ2" in opts[3][0] and opts[3][1] and "needs 4 drives" in opts[3][0] and not opts[1][1], opts)
                check("configure (%s): nothing is sent by only looking" % cfg_mode, not any(c[1] in ("setup", "add", "wipe") for c in calls()[m:]), calls()[m:])
                check("configure (%s): no side scroll" % cfg_mode, no_side_scroll(pg), "")
                pg.click("button:has-text('Build Recommended Setup')")
                pg.wait_for_selector("dialog")
                dt = dialog_text(pg)
                if cfg_mode == "ok":
                    check("configure: the dialog says what is erased and what you get", "/dev/sdc, /dev/sde, /dev/sdf will be permanently deleted" in dt and "64.0 GB" in dt.replace("64 GB", "64.0 GB") or "GB of the" in dt, dt[:400])
                    check("configure: the OK button waits for the I understand box", ok_button(pg).is_disabled(), "")
                    sure_box(pg).check()
                    ok_button(pg).click()
                    check("configure: the setup is sent with its name and ERASE", wait_calls(pg, ["panel", "setup", "zfs-raidz1", "sdc,sde,sdf", "zfs-raidz1", "ERASE"]), calls()[m:])
                    after_job(pg)
                else:
                    check("configure (blocked): the dialog explains why and has only a Close button", "take the drives out of Main first" in dt and ok_button(pg).inner_text() == "Close", dt[:300])
                    ok_button(pg).click()
                    pg.wait_for_selector("dialog", state="detached")
                    check("configure (blocked): nothing was sent", not any(c[1] == "setup" for c in calls()[m:]), calls()[m:])
                pg.select_option(".cfgsel", "pool")
                pg.wait_for_selector("dialog")
                dt = dialog_text(pg)
                check("configure (%s): picking another setup from the dropdown opens its own dialog" % cfg_mode, "Build: Plain pool" in dt, dt[:200])
                check("configure (%s): a plain pool lets the drives that hold files keep them" % cfg_mode, "can keep them" in dt and "Keep the files" in dt and "Erase the drive and format it" in dt, dt)
                if cfg_mode == "ok":
                    m = len(calls())
                    sure_box(pg).check()
                    ok_button(pg).click()
                    check("configure: a plain pool is added to Main, the drive with files kept and the empty ones formatted", wait_calls(pg, ["panel", "add", "sdc:keep,sde:erase,sdf:erase", "main", "each", "/dev/sde", "/dev/sdf", "ERASE"]), calls()[m:])
                    after_job(pg)
                else:
                    cancel_dialog(pg)
                ctx.close()

            br.close()
    finally:
        p.stop()
    ok = all(results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


def ids_of(pg, zone):
    return pg.eval_on_selector_all(".zone-%s .tile" % zone, "els => els.map(e => e.dataset.id)")


if __name__ == "__main__":
    sys.exit(main())
