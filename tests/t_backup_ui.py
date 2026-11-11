#!/usr/bin/env python3
"""Test of the Backups section of the Drives tab in the panel's page (panel/ui) with the real panel server, the real backup tool (on temporary folders)
and a FAKE drives tool. Looks at: the nightly task that is there from the start, making a task in the dialog, Run Now with its result, Preview,
Restore (version, browsing, bringing a file back), Edit, Turn Off, Delete, the other-computer and cloud parts of the dialog, an absent backup tool,
and that everything fits a phone.
Needs Playwright with Chromium; without it the test says so and passes.   Run: python3 tests/t_backup_ui.py   (last line is OK or FAIL)"""
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
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import t_panel as tp  # noqa: E402

results = []
SHOTS = os.environ.get("BACKUP_SHOTS")      # a folder: also keep screenshots


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   " + str(extra)))


def main():
    tmp = tempfile.mkdtemp(prefix="hlbui-")
    src, dst = os.path.join(tmp, "docs"), os.path.join(tmp, "drive", "copies")
    os.makedirs(os.path.join(src, "letters"))
    os.makedirs(os.path.dirname(dst))
    for name, text in (("notes.txt", "my notes\n"), ("letters/mom.txt", "dear mom\n")):
        with open(os.path.join(src, name), "w") as f:
            f.write(text)
    with open(os.path.join(tmp, "mounts"), "w") as f:
        f.write("/dev/sdz1 %s ext4 rw 0 0\n" % os.path.join(tmp, "drive"))
    legacy = os.path.join(tmp, "legacy")
    with open(legacy, "w") as f:
        f.write("#!/bin/bash\necho ok\n")
    os.chmod(legacy, 0o755)
    env = {"HLP_DRIVES": os.path.join(HERE, "fake_drives.py"), "FAKE_DRIVES_LOG": os.path.join(tmp, "drives.log"),
           "HLP_BACKUP": "%s %s panel" % (sys.executable, os.path.join(ROOT, "scripts", "homelab-backup-tasks")),
           "HLB_CONF": os.path.join(tmp, "tasks.json"), "HLB_STATE": os.path.join(tmp, "bstate"), "HLB_LOCK": os.path.join(tmp, "lock"),
           "HLB_LOGFILE": os.path.join(tmp, "log"), "HLB_ROOTS": tmp, "HLB_ALLOW_ROOTFS": "1", "HLB_LEGACY": legacy, "HLB_LEGACY_CONF": os.path.join(tmp, "none"),
           "HLB_KEY": os.path.join(tmp, "key"), "HLB_MOUNTS_FILE": os.path.join(tmp, "mounts"),
           "HLB_RCLONE": os.path.join(HERE, "fake_rclone.py"), "FAKE_RCLONE_DIR": os.path.join(tmp, "cloud"), "HLB_RCLONE_CONF": os.path.join(tmp, "rclone.conf"),
           "PATH": "/nonexistent-bin:" + os.environ.get("PATH", "")}
    env["PATH"] = os.environ.get("PATH", "")
    p = tp.Panel(tmp, env)
    p.set_password()
    p.start()

    def open_tab(br, w=1280, hgt=900, port=None):
        ctx = br.new_context(viewport={"width": w, "height": hgt}, device_scale_factor=1)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:%d/" % (port or p.port))
        pg.fill("input[type=password]", tp.PW)
        pg.click("text=Log In")
        pg.wait_for_selector("nav.tabs")
        pg.click("nav.tabs button:has-text('Drives')")
        return ctx, pg, errors

    def shot(pg, name, full=False):
        if SHOTS:
            os.makedirs(SHOTS, exist_ok=True)
            pg.screenshot(path=os.path.join(SHOTS, name + ".png"), full_page=full)

    def task(pg, name):
        return pg.locator(".bkt").filter(has_text=name)

    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            ctx, pg, errors = open_tab(br)
            pg.wait_for_selector(".bkt")
            check("backups: the section is on the Drives tab", pg.locator(".bk h2", has_text="Backups").count() == 1)
            nt = task(pg, "Nightly: Main to Backup")
            check("backups: the nightly task is there from the start", nt.count() == 1 and "Every day at 06:00" in nt.inner_text())
            check("backups: the nightly task has no Delete or Preview button", nt.get_by_role("button", name="Delete").count() == 0 and nt.get_by_role("button", name="Preview").count() == 0)

            shot(pg, "1-start", True)
            # ---- a new task
            pg.get_by_role("button", name="New Backup Task").click()
            pg.wait_for_selector("dialog.bkdlg")
            pg.fill("dialog input[placeholder='My documents']", "My documents")
            pg.fill("dialog input[list='bk-src']", src)
            pg.select_option("dialog select[aria-label='Choose a connected drive']", index=1)
            check("backups: picking a drive fills in the folder", pg.input_value("dialog input[placeholder='/mnt/backup/homelab-backups']").endswith("/drive/backups"))
            pg.fill("dialog input[placeholder='/mnt/backup/homelab-backups']", dst)
            pg.fill("dialog input[aria-label='Daily versions to keep']", "2")
            shot(pg, "2-new-task")
            pg.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_selector("dialog.bkdlg", state="detached")
            t = task(pg, "My documents")
            t.filter(has_text="Never run").wait_for()
            tx = t.inner_text()
            check("backups: the new task shows up with its schedule, source and place", t.count() == 1 and "Every day at 02:00" in tx and src in tx and dst in tx and "Never run" in tx, (t.count(), tx))
            check("backups: it says what it keeps", "2 daily, 4 weekly" in t.inner_text())

            pg.get_by_role("button", name="New Backup Task").click()
            pg.wait_for_selector("dialog.bkdlg")
            pg.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_selector("dialog.bkdlg p.badtext:not(:empty)")
            check("backups: a bad task is explained in the dialog (and the dialog stays)", "name" in pg.inner_text("dialog.bkdlg p.badtext").lower(), pg.inner_text("dialog.bkdlg"))
            pg.get_by_role("button", name="Cancel").click()

            # ---- preview, run
            t.get_by_role("button", name="Preview").click()
            pg.locator("#toast", has_text="first run would copy 2 files").wait_for(timeout=20000)
            check("backups: Preview says how much would be copied", True)
            check("backups: Preview made no copy", not os.path.exists(dst))
            t.get_by_role("button", name="Run Now").click()
            task(pg, "My documents").filter(has_text="Last run OK").wait_for(timeout=30000)
            t = task(pg, "My documents")
            shot(pg, "3-after-run", True)
            check("backups: Run Now ends well and the card says so", "Copied" in t.inner_text() and "Space used" in t.inner_text(), t.inner_text())
            tid = [x for x in os.listdir(dst) if x != "latest"] if os.path.isdir(dst) else []
            check("backups: the copy is on the drive", len(tid) == 1 and os.path.isdir(os.path.join(dst, tid[0])), tid)

            # ---- restore
            with open(os.path.join(src, "notes.txt"), "w") as f:
                f.write("changed\n")
            t.get_by_role("button", name="Restore").click()
            pg.wait_for_selector("dialog.bkdlg .bklist .item")
            shot(pg, "4-restore")
            names = pg.locator("dialog.bkdlg .bklist .item .txt").all_inner_texts()
            check("backups: Restore lists the top of the newest version", any("letters" in n for n in names) and any("notes.txt" in n for n in names), names)
            pg.locator("dialog.bkdlg .bklist button.link", has_text="letters").click()
            pg.locator("dialog.bkdlg .bklist", has_text="mom.txt").wait_for()
            check("backups: a folder can be opened", "Top" in pg.inner_text("dialog.bkdlg .bkcrumbs"))
            pg.locator("dialog.bkdlg .bkcrumbs button", has_text="Top").click()
            pg.locator("dialog.bkdlg .bklist", has_text="notes.txt").wait_for()
            pg.locator("dialog.bkdlg .item", has_text="notes.txt").get_by_role("button", name="Restore").click()
            pg.wait_for_selector("dialog.bkdlg", state="detached")
            pg.locator("#toast", has_text="Restored").wait_for(timeout=30000)
            found = [os.path.join(r, "notes.txt") for r, _, fs in os.walk(os.path.join(src, "_restored")) if "notes.txt" in fs]
            check("backups: the file came back into a safe folder", len(found) == 1 and open(found[0]).read() == "my notes\n" and open(os.path.join(src, "notes.txt")).read() == "changed\n", found)

            # ---- edit, turn off, delete
            t.get_by_role("button", name="Edit").click()
            pg.wait_for_selector("dialog.bkdlg")
            check("backups: Edit shows the saved values", pg.input_value("dialog input[list='bk-src']") == src and pg.input_value("dialog input[aria-label='Daily versions to keep']") == "2")
            pg.fill("dialog input[placeholder='My documents']", "Papers")
            pg.select_option("dialog select[aria-label='How often']", "weekly")
            pg.get_by_role("button", name="Save", exact=True).click()
            pg.wait_for_selector("dialog.bkdlg", state="detached")
            t = task(pg, "Papers")
            t.filter(has_text="Every Sunday").wait_for()
            check("backups: a task can be renamed and its schedule changed", t.count() == 1 and "Every Sunday at 02:00" in t.inner_text(), t.inner_text())
            t.get_by_role("button", name="Turn Off").click()
            task(pg, "Papers").filter(has_text="Turn On").wait_for()
            check("backups: Turn Off shows Off", task(pg, "Papers").locator(".pill", has_text="Off").count() == 1)
            task(pg, "Papers").get_by_role("button", name="Delete").click()
            pg.wait_for_selector("dialog")
            check("backups: Delete asks whether to keep the copies", "Keep Copies" in pg.inner_text("dialog") and "Erase Copies" in pg.inner_text("dialog"))
            pg.get_by_role("button", name="Delete Task and Erase Copies").click()
            task(pg, "Papers").wait_for(state="detached", timeout=20000)
            check("backups: the task is gone and its copies are erased", task(pg, "Papers").count() == 0 and not os.path.exists(os.path.join(dst, tid[0])) if tid else False)

            # ---- the other kinds of place
            pg.get_by_role("button", name="New Backup Task").click()
            pg.wait_for_selector("dialog.bkdlg")
            pg.select_option("dialog select[aria-label='Where the copies go']", "ssh")
            check("backups: another computer asks for the account and the folder", pg.locator("dialog input[placeholder^='user@computer']").count() == 1 and pg.get_by_role("button", name="Show the Key").count() == 1)
            pg.fill("dialog input[placeholder^='user@computer']", "bad host")
            pg.get_by_role("button", name="Test the Connection").click()
            pg.wait_for_selector("dialog.bkdlg p.badtext:not(:empty)")
            check("backups: a bad address is explained", "user@name" in pg.inner_text("dialog.bkdlg p.badtext"), pg.inner_text("dialog.bkdlg p.badtext"))
            pg.select_option("dialog select[aria-label='Where the copies go']", "cloud")
            check("backups: the cloud part lists the accounts rclone knows", pg.locator("dialog select[aria-label='Cloud account'] option").all_inner_texts() == ["gd"])
            check("backups: the cloud part keeps days, not versions", pg.locator("dialog input[aria-label='Days']").count() == 1 and pg.locator("dialog input[aria-label='Daily versions to keep']").count() == 0)
            check("backups: the cloud part says honestly what it keeps", "latest copy" in pg.inner_text("dialog.bkdlg"))
            shot(pg, "5-cloud")
            pg.get_by_role("button", name="Cancel").click()

            # ---- a phone
            ctx.close()
            ctx, pg, errors2 = open_tab(br, 390, 800)
            pg.wait_for_selector(".bkt")
            pg.get_by_role("button", name="New Backup Task").click()
            pg.wait_for_selector("dialog.bkdlg")
            shot(pg, "6-phone-dialog")
            over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            dl = pg.evaluate("(() => { const r = document.querySelector('dialog.bkdlg').getBoundingClientRect(); return [r.left, r.right, innerWidth]; })()")
            check("backups: the dialog fits a phone", over <= 1 and dl[0] >= 0 and dl[1] <= dl[2] + 1, (over, dl))
            pg.get_by_role("button", name="Cancel").click()
            over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("backups: the section fits a phone", over <= 1, over)
            ctx.close()
            check("backups: the page raised no errors", not errors and not errors2, errors + errors2)

            # ---- no backup tool
            p.stop()
            p.env["HLP_BACKUP"] = os.path.join(tmp, "no-such-tool")
            p.start()
            ctx, pg, errors3 = open_tab(br)
            pg.wait_for_selector(".bk p.badtext")
            pg.wait_for_selector(".tile")
            check("backups: a missing backup tool is explained and the rest of the tab works", "not installed" in pg.inner_text(".bk p.badtext") and pg.locator(".tile").count() > 0, pg.inner_text(".bk"))
            check("backups: ... with no New Backup Task button enabled", pg.get_by_role("button", name="New Backup Task").is_disabled())
            ctx.close()
            br.close()
    finally:
        p.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    ok = all(results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
