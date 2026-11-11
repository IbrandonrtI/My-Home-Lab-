#!/usr/bin/env python3
"""Test of the Upload card on the Drives tab (panel/ui) with the real panel server, a FAKE Immich and a temporary music folder.
Looks at: the key box (a wrong key, a right key), sending photos and videos (with a refused kind in the list), the same photo again, sending songs
(a same-name song is kept apart), forgetting the key, and that the card fits a phone.
Needs Playwright with Chromium; without it the test says so and passes.   Run: python3 tests/t_upload_ui.py   (last line is OK or FAIL)
Set UPLOAD_SHOTS=/some/folder to also keep screenshots."""
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
from fake_immich import FakeImmich  # noqa: E402

results = []
SHOTS = os.environ.get("UPLOAD_SHOTS")


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   " + str(extra)))


def main():
    tmp = tempfile.mkdtemp(prefix="hlupui-")
    music, files = os.path.join(tmp, "music"), os.path.join(tmp, "files")
    os.makedirs(music)
    os.makedirs(files)
    for name, data in (("beach.jpg", os.urandom(200000)), ("clip.mp4", os.urandom(900000)), ("notes.txt", b"hello"), ("one.mp3", os.urandom(300000)), ("two.flac", os.urandom(100000))):
        with open(os.path.join(files, name), "wb") as f:
            f.write(data)
    shutil.copy(os.path.join(files, "one.mp3"), os.path.join(files, "same.mp3"))
    fake = FakeImmich()
    env = {"HLP_DRIVES": os.path.join(HERE, "fake_drives.py"), "FAKE_DRIVES_LOG": os.path.join(tmp, "drives.log"), "HLP_IMMICH_URL": "http://127.0.0.1:%d" % fake.port,
           "HLP_MUSIC_DIR": music, "HLP_BACKUP": os.path.join(tmp, "no-such-tool")}
    p = tp.Panel(tmp, env)
    p.set_password()
    p.start()
    GOOD = "goodkey" + "A1" * 16

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
            pg.goto("http://127.0.0.1:%d/" % p.port)
            pg.fill("input[type=password]", tp.PW)
            pg.click("text=Log In")
            pg.wait_for_selector("nav.tabs")
            pg.click("nav.tabs button:has-text('Drives')")
            pg.wait_for_selector(".upbox")
            photos = pg.locator(".upbox").filter(has_text="Go to Immich")
            songs = pg.locator(".upbox").filter(has_text="Saved in")
            check("upload: the card is on the Drives tab, above Backups", pg.locator(".up h2", has_text="Upload").count() == 1 and pg.evaluate("document.querySelector('.up').compareDocumentPosition(document.querySelector('.bk')) & 4") > 0)
            check("upload: the photo box asks for a key", "Needs a key" in photos.inner_text() and photos.locator("input[type=password]").count() == 1, photos.inner_text())
            check("upload: the song box is ready", "Ready" in songs.inner_text() and songs.locator("input[type=file]").count() == 1, songs.inner_text())
            shot(pg, "1-start")

            photos.locator("input[type=password]").fill("wrongkey" + "x" * 20)
            photos.get_by_role("button", name="Save the Key").click()
            photos.locator("p.badtext", has_text="turned that key down").wait_for()
            check("upload: a wrong key is explained", True)
            photos.locator("input[type=password]").fill(GOOD)
            photos.get_by_role("button", name="Save the Key").click()
            photos.locator("input[type=file]").wait_for(state="attached")
            check("upload: a right key opens the upload box", "Ready" in photos.inner_text() and photos.locator("input[type=password]").count() == 0, photos.inner_text())

            photos.locator("input[type=file]").set_input_files([os.path.join(files, n) for n in ("beach.jpg", "clip.mp4", "notes.txt")])
            photos.locator(".uplist", has_text="2 of 3 done, 1 failed").wait_for(timeout=30000)
            check("upload: the photo and the video were sent, the text file was refused in the list", len(fake.assets) == 2 and "Not accepted" in photos.inner_text(), (len(fake.assets), photos.inner_text()))
            check("upload: what Immich got is what was chosen", {a["filename"] for a in fake.assets} == {"beach.jpg", "clip.mp4"} and all(a["key"] == GOOD for a in fake.assets))
            shot(pg, "2-photos-done")
            photos.locator("input[type=file]").set_input_files([os.path.join(files, "beach.jpg")])
            photos.locator(".upit", has_text="Already in Immich").wait_for(timeout=20000)
            check("upload: the same photo again says it is already in Immich", True)
            photos.get_by_role("button", name="Clear the List").click()
            check("upload: Clear the List empties the list", photos.locator(".upit").count() == 0)

            songs.locator("input[type=file]").set_input_files([os.path.join(files, n) for n in ("one.mp3", "two.flac", "same.mp3")])
            songs.locator(".uplist", has_text="3 of 3 done").wait_for(timeout=30000)
            check("upload: the songs are in the music folder", sorted(os.listdir(music)) == ["one.mp3", "same.mp3", "two.flac"], os.listdir(music))
            songs.locator("input[type=file]").set_input_files([os.path.join(files, "one.mp3")])
            songs.locator(".upit", has_text="Saved as one (2).mp3").wait_for(timeout=20000)
            check("upload: a song with a name already there is kept apart", os.path.exists(os.path.join(music, "one (2).mp3")))
            shot(pg, "3-songs-done")

            photos.get_by_role("button", name="Forget the Immich key").click()
            pg.get_by_role("button", name="Forget It").click()
            photos.locator("input[type=password]").wait_for()
            check("upload: forgetting the key brings the key box back", "Needs a key" in photos.inner_text())
            check("upload: the page raised no errors", not errors, errors)
            ctx.close()

            ctx = br.new_context(viewport={"width": 390, "height": 800}, device_scale_factor=1)
            pg = ctx.new_page()
            pg.goto("http://127.0.0.1:%d/" % p.port)
            pg.fill("input[type=password]", tp.PW)
            pg.click("text=Log In")
            pg.wait_for_selector("nav.tabs")
            pg.click("nav.tabs button:has-text('Drives')")
            pg.wait_for_selector(".upbox")
            over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check("upload: the card fits a phone", over <= 1, over)
            shot(pg, "4-phone")
            ctx.close()
            br.close()
    finally:
        p.stop()
        fake.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    ok = all(results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
