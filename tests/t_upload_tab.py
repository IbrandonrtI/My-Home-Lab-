#!/usr/bin/env python3
"""Test of the Upload card's server side in scripts/homelab-panel: the Immich key (checked, kept privately, forgotten), photos and videos passed on to
Immich piece by piece (a FAKE Immich), songs saved into the music folder (never replacing a song, never leaving the folder), and the plain-words
problems (Immich down, bad file kinds, no key).
Run: python3 tests/t_upload_tab.py   (last line is OK or FAIL)"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import t_panel  # noqa: E402  (the same panel harness)
from fake_immich import FakeImmich  # noqa: E402

check = t_panel.check


def main():
    tmp = tempfile.mkdtemp(prefix="hlupl-")
    music = os.path.join(tmp, "music")
    os.makedirs(music)
    fake = FakeImmich()
    p = t_panel.Panel(tmp, {"HLP_IMMICH_URL": "http://127.0.0.1:%d" % fake.port, "HLP_MUSIC_DIR": music})
    try:
        p.set_password()
        p.start()
        st, js, _, _ = p.req("GET", "/api/upload")
        check("upload: the state needs a login", st == 401, st)
        st, js, _, _ = p.req("POST", "/api/upload/song?name=a.mp3", raw=b"abc")
        check("upload: a song needs a login", st == 401, st)
        check("upload: nothing was saved without a login", os.listdir(music) == [])
        p.login()
        st, js, _, _ = p.req("POST", "/api/upload/song?name=a.mp3", raw=b"abc", headers={"Origin": "https://evil.example.com"})
        check("upload: an upload from another website is refused", st == 403 and os.listdir(music) == [], st)
        st, js, _, _ = p.req("POST", "/api/upload/song?name=a.mp3", raw=b"abc", headers={"X-Panel": ""})
        check("upload: an upload without the panel header is refused", st in (400, 401, 403), st)

        st, js, _, _ = p.req("GET", "/api/upload")
        check("upload: the state says Immich is up, not yet keyed, and the music folder is ready",
              st == 200 and js["immich"] == {"configured": False, "up": True} and js["music"]["dir"] == music and js["music"]["writable"] and "mp3" in js["song_ext"] and "jpg" in js["photo_ext"], (st, js))

        # ---- the key
        st, js, _, _ = p.req("POST", "/api/upload/photo?name=a.jpg&mtime=1700000000000", raw=b"x" * 100)
        check("upload: a photo without a key is told to paste one", st == 409 and "key" in js["error"].lower(), (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/immich-key", {"key": "short"})
        check("upload: a key that cannot be one is refused before Immich is asked", st == 400, (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/immich-key", {"key": "wrongkey" + "x" * 20})
        check("upload: a key Immich turns down is not kept", st == 409 and "turned that key down" in js["error"] and not os.path.exists(os.path.join(p.state, "uploads.json")), (st, js))
        GOOD = "goodkey" + "A1" * 16
        st, js, _, _ = p.req("POST", "/api/upload/immich-key", {"key": GOOD})
        check("upload: a good key is kept", st == 200 and js["configured"] and "Brandon" in js["message"], (st, js))
        f = os.path.join(p.state, "uploads.json")
        check("upload: the key file is private", oct(os.stat(f).st_mode)[-3:] == "600", oct(os.stat(f).st_mode))
        st, js, txt, _ = p.req("GET", "/api/upload")
        check("upload: the key is never shown again", js["immich"]["configured"] is True and GOOD not in txt.decode(), js)
        st, js, txt, _ = p.req("GET", "/api/state")
        check("upload: ... nor in the rest of the panel's state", GOOD not in txt.decode())

        # ---- photos
        data = os.urandom(3 * 1024 * 1024 + 17)
        st, js, _, _ = p.req("POST", "/api/upload/photo?name=holiday%20pic.JPG&mtime=1700000000000", raw=data)
        a = fake.assets[-1] if fake.assets else {}
        check("upload: a photo is passed on to Immich byte for byte", st == 200 and js["status"] == "created" and a.get("data") == data, (st, js))
        check("upload: ... with the key, its name and its own date", a.get("key") == GOOD and a["filename"] == "holiday pic.JPG" and a["fields"]["fileCreatedAt"].startswith("2023-11-14T22:13:20") and a["fields"]["deviceId"] == "homelab-panel", a.get("fields"))
        st, js, _, _ = p.req("POST", "/api/upload/photo?name=again.jpg&mtime=1700000000000", raw=data)
        check("upload: the same photo again is reported as already there", st == 200 and js["status"] == "duplicate", (st, js))
        big = os.urandom(40 * 1024 * 1024)
        st, js, _, _ = p.req("POST", "/api/upload/photo?name=video.mp4&mtime=1700000000000", raw=big)
        check("upload: a 40 MB video goes through", st == 200 and fake.assets[-1]["data"] == big, (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/photo?name=notes.txt", raw=b"hello")
        check("upload: a kind of file Immich does not take is refused", st == 415 and ".txt" in js["error"], (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/photo?name=a.jpg", raw=b"")
        check("upload: an empty file is refused", st == 400, (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/photo", raw=b"abc")
        check("upload: a file without a name is refused", st == 400, (st, js))
        n_before = len(fake.assets)
        st, js, _, _ = p.req("POST", "/api/upload/immich-key", {"key": "limitedkey" + "B2" * 12})
        check("upload: a key that may only upload is accepted", st == 200 and js["configured"], (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/immich-key", {"key": "revokedkey" + "C3" * 12})
        st2, js2, _, _ = p.req("POST", "/api/upload/photo?name=x.jpg&mtime=1", raw=b"abc")
        check("upload: a refused new key leaves the old one working", st == 409 and st2 == 200, (st, st2, js2))
        fake.assets = fake.assets[:n_before]
        st, js, _, _ = p.req("POST", "/api/upload/immich-key", {"key": ""})
        check("upload: the key can be forgotten", st == 200 and js["configured"] is False and "immich_key" not in open(f).read())
        p.stop()
        p.env["HLP_IMMICH_URL"] = "http://127.0.0.1:1"
        p.start(); p.login()
        with open(f, "w") as fh:
            fh.write('{"immich_key": "%s"}' % GOOD)
        st, js, _, _ = p.req("GET", "/api/upload")
        check("upload: state says Immich is not answering", js["immich"]["up"] is False and js["immich"]["configured"] is True, js)
        st, js, _, _ = p.req("POST", "/api/upload/photo?name=a.jpg&mtime=1", raw=b"abc")
        check("upload: a photo while Immich is down is explained", st == 502 and "does not answer" in js["error"], (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/immich-key", {"key": GOOD})
        check("upload: a key cannot be saved while Immich is down (it cannot be checked)", st == 502, (st, js))
        p.stop()

        # ---- songs
        p.env["HLP_IMMICH_URL"] = "http://127.0.0.1:%d" % fake.port
        p.start(); p.login()
        song = os.urandom(2 * 1024 * 1024)
        st, js, _, _ = p.req("POST", "/api/upload/song?name=My%20Song.mp3", raw=song)
        check("upload: a song is saved as it is", st == 200 and js["saved"] == "My Song.mp3" and open(os.path.join(music, "My Song.mp3"), "rb").read() == song, (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/song?name=My%20Song.mp3", raw=b"other")
        check("upload: a song with the same name is never replaced", js["saved"] == "My Song (2).mp3" and open(os.path.join(music, "My Song.mp3"), "rb").read() == song, js)
        st, js, _, _ = p.req("POST", "/api/upload/song?name=..%2F..%2Fetc%2Fevil.flac", raw=b"x")
        check("upload: a name with folders stays inside the music folder", st == 200 and js["saved"] == "evil.flac" and os.path.exists(os.path.join(music, "evil.flac")) and not os.path.exists(os.path.join(tmp, "evil.flac")), (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/song?name=..%5C..%5Cwin.mp3", raw=b"x")
        check("upload: a name with backslashes stays inside too", st == 200 and js["saved"] == "win.mp3", (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/song?name=.hidden.mp3", raw=b"x")
        check("upload: a leading dot is dropped (no hidden files)", js.get("saved") == "hidden.mp3", (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/song?name=virus.exe", raw=b"x")
        check("upload: a file that is not a song is refused", st == 415 and not os.path.exists(os.path.join(music, "virus.exe")), (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/song?name=noending", raw=b"x")
        check("upload: a name without an ending is refused in words", st == 415 and "ending" in js["error"], (st, js))
        st, js, _, _ = p.req("POST", "/api/upload/song?name=a.mp3", raw=b"")
        check("upload: an empty song is refused", st == 400, (st, js))
        check("upload: no half-written files are left", not [n for n in os.listdir(music) if n.startswith(".upload")], os.listdir(music))
        shutil.rmtree(music)
        st, js, _, _ = p.req("POST", "/api/upload/song?name=a.mp3", raw=b"abc")
        check("upload: a missing music folder is explained", st == 409 and "not there" in js["error"], (st, js))
        st, js, _, _ = p.req("GET", "/api/upload")
        check("upload: state says the folder is missing", js["music"]["exists"] is False, js)
    finally:
        p.stop()
        fake.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    ok = all(t_panel.results)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
