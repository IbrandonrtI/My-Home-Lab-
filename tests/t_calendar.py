#!/usr/bin/env python3
"""Tests of scripts/homelab-calendar: the holiday dates, the calendar files, and the event commands (add, list, remove).
Everything happens in a temp folder.
Run: python3 tests/t_calendar.py   (last line is OK or FAIL)"""
import datetime
import importlib.machinery
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.join(HERE, "..", "scripts", "homelab-calendar")
loader = importlib.machinery.SourceFileLoader("hlcal", PROG)
spec = importlib.util.spec_from_loader("hlcal", loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)
D = datetime.date
bad = 0


def check(name, ok, extra=""):
    global bad
    bad += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "   " + str(extra)[:600]))


def names(rows):
    return {n: d for d, n in rows}


# ---- holiday dates (checked against the real calendars of 2026 and 2027)
o26, o27 = names(m.official(2026)), names(m.official(2027))
check("New Year's Day, Juneteenth, Independence Day, Veterans Day, Christmas", o26["New Year's Day"] == D(2026, 1, 1) and o26["Juneteenth"] == D(2026, 6, 19)
      and o26["Independence Day"] == D(2026, 7, 4) and o26["Veterans Day"] == D(2026, 11, 11) and o26["Christmas Day"] == D(2026, 12, 25))
check("Martin Luther King Jr. Day is the 3rd Monday of January", o26["Martin Luther King Jr. Day"] == D(2026, 1, 19) and o27["Martin Luther King Jr. Day"] == D(2027, 1, 18))
check("Presidents' Day is the 3rd Monday of February", o26["Presidents' Day"] == D(2026, 2, 16) and o27["Presidents' Day"] == D(2027, 2, 15))
check("Memorial Day is the last Monday of May", o26["Memorial Day"] == D(2026, 5, 25) and o27["Memorial Day"] == D(2027, 5, 31))
check("Labor Day is the 1st Monday of September", o26["Labor Day"] == D(2026, 9, 7) and o27["Labor Day"] == D(2027, 9, 6))
check("Columbus Day / Indigenous Peoples' Day is the 2nd Monday of October", o26["Columbus Day / Indigenous Peoples' Day"] == D(2026, 10, 12))
check("Thanksgiving is the 4th Thursday of November", o26["Thanksgiving"] == D(2026, 11, 26) and o27["Thanksgiving"] == D(2027, 11, 25))
check("Election Day is the Tuesday after the first Monday of November", o26["Election Day (NY)"] == D(2026, 11, 3) and o27["Election Day (NY)"] == D(2027, 11, 2))
check("Lincoln's Birthday is February 12", o26["Lincoln's Birthday (NY)"] == D(2026, 2, 12))
b26 = names(m.observances(2026))
check("Mother's Day (2nd Sunday of May) and Father's Day (3rd Sunday of June)", b26["Mother's Day"] == D(2026, 5, 10) and b26["Father's Day"] == D(2026, 6, 21))
check("Valentine's Day and Halloween", b26["Valentine's Day"] == D(2026, 2, 14) and b26["Halloween"] == D(2026, 10, 31))
check("Lunar New Year and Diwali of 2026", b26["Lunar New Year"] == D(2026, 2, 17) and b26["Diwali"] == D(2026, 11, 8))
check("every year from 2026 to 2035 has a Lunar New Year and a Diwali in the right month",
      all(D(y, *m.LUNAR_NEW_YEAR[y]).month in (1, 2) and D(y, *m.DIWALI[y]).month in (10, 11) for y in range(2026, 2036)))
check("the thirteen official holidays are in every year", all(len(m.official(y)) == 13 for y in range(2024, 2040)))
check("a year outside the Lunar New Year / Diwali list simply has none of them", "Diwali" not in names(m.observances(2040)) and "Halloween" in names(m.observances(2040)))

# ---- dates typed by a person
t = D(2026, 11, 4)
check("2026-12-25, 12/25/2026, 12/25/26", m.parse_date("2026-12-25", t) == D(2026, 12, 25) and m.parse_date("12/25/2026", t) == D(2026, 12, 25) and m.parse_date("12/25/26", t) == D(2026, 12, 25))
check("12/25 is the next 12/25, and 1/5 is next year's", m.parse_date("12/25", t) == D(2026, 12, 25) and m.parse_date("1/5", t) == D(2027, 1, 5))
check("11/4 (today) is today", m.parse_date("11/4", t) == t)
check("2/29 waits for a leap year", m.parse_date("2/29", t) == D(2028, 2, 29))
for bad_text in ("2026-02-30", "13/1/2026", "tomorrow", "Dec 25", ""):
    try:
        m.parse_date(bad_text, t)
        check("'%s' is refused" % bad_text, False)
    except m.Fail:
        check("'%s' is refused" % bad_text, True)

# ---- the .ics text
ev = m.ics("Mine", [(D(2026, 12, 25), "Family dinner, with Mom; Dad", False), (D(2026, 11, 20), "Mom's birthday", True)])
check("lines end with CRLF and the file is a calendar", ev.startswith("BEGIN:VCALENDAR\r\n") and ev.endswith("END:VCALENDAR\r\n") and "\n" not in ev.replace("\r\n", ""))
check("all-day events: the end is the next day", "DTSTART;VALUE=DATE:20261225\r\nDTEND;VALUE=DATE:20261226" in ev)
check("commas and semicolons in the text are escaped", "SUMMARY:Family dinner\\, with Mom\\; Dad" in ev)
check("a yearly event repeats", ev.count("RRULE:FREQ=YEARLY") == 1)
empty = m.ics("Mine", [])
check("a calendar without events still holds one note far in the past (an empty calendar would show an error)", empty.count("BEGIN:VEVENT") == 1 and "DTSTART;VALUE=DATE:20000101" in empty)
long_one = m.ics("x", [(D(2026, 1, 1), "A" * 200, False)])
check("long lines are folded to 75 characters", all(len(l) <= 75 for l in long_one.split("\r\n")))
check("the text is the same after unfolding", "A" * 200 in long_one.replace("\r\n ", ""))
check("the same input gives the same text", m.ics("Mine", [(D(2026, 12, 25), "x", False)]) == m.ics("Mine", [(D(2026, 12, 25), "x", False)]))

# ---- the commands
T = tempfile.mkdtemp(prefix="t_calendar_")
try:
    hp = os.path.join(T, "hp")
    os.makedirs(hp)
    env = dict(os.environ, HP_DIR=hp, HOMELAB_STATE_DIR=os.path.join(T, "state"))

    def run(*a):
        return subprocess.run([sys.executable, PROG] + list(a), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=60)

    def rd(f):
        with open(os.path.join(hp, f)) as fh:
            return fh.read()

    r = run("build")
    img = os.path.join(hp, "images")
    check("build makes the three files", r.returncode == 0 and sorted(os.listdir(img)) == ["events.ics", "holidays.ics", "observances.ics"], r.stdout)
    check("the files can be read by everyone", all(os.stat(os.path.join(img, f)).st_mode & 0o044 == 0o044 for f in os.listdir(img)))
    hol = rd("images/holidays.ics")
    y = datetime.date.today().year
    check("the holidays cover last year to five years ahead", hol.count("SUMMARY:Thanksgiving") == 7 and "DTSTART;VALUE=DATE:%d1126" % 2026 in hol, hol.count("SUMMARY:Thanksgiving"))
    check("a new calendar has no events of its own yet", "No events yet" in rd("images/events.ics"))
    before = {f: os.stat(os.path.join(img, f)).st_mtime_ns for f in os.listdir(img)}
    run("build")
    check("building again changes no file", before == {f: os.stat(os.path.join(img, f)).st_mtime_ns for f in os.listdir(img)})

    r = run("add", "2026-12-25", "Family", "dinner")
    check("add works with or without quotes", r.returncode == 0 and "Added: Fri Dec 25, 2026  Family dinner" in r.stdout, r.stdout)
    check("add writes events.txt and events.ics", "2026-12-25 | once | Family dinner" in rd("events.txt") and "SUMMARY:Family dinner" in rd("images/events.ics")
          and "No events yet" not in rd("images/events.ics"))
    r = run("add", "2026-11-20", "Mom's", "birthday", "yearly")
    check("add ... yearly repeats it every year", r.returncode == 0 and "2026-11-20 | yearly | Mom's birthday" in rd("events.txt") and "RRULE:FREQ=YEARLY" in rd("images/events.ics"), r.stdout)
    r = run("add", "2026-12-25", "Family dinner")
    check("the same event twice is added once", "already in the calendar" in r.stdout and rd("events.txt").count("| once | Family dinner") == 1)
    r = run("add", "2026-12-25", "a|b")
    check("a bar in the text is replaced (it is the separator of events.txt)", r.returncode == 0 and "a/b" in rd("events.txt"))
    r = run("list")
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    check("list numbers them in date order", len(lines) == 3 and lines[0].lstrip().startswith("1  ") and "Mom's birthday" in lines[0] and "every year" in lines[0], r.stdout)
    r = run("remove", "1")
    check("remove NUMBER takes it away from both files", r.returncode == 0 and "Mom's birthday" not in rd("events.txt") and "Mom's birthday" not in rd("images/events.ics")
          and "Family dinner" in rd("images/events.ics"), r.stdout)
    r = run("remove", "9")
    check("a wrong number is refused", r.returncode == 1 and "no event number 9" in r.stdout, r.stdout)
    r = run("remove", "dinner")
    check("a word instead of a number is refused", r.returncode == 1 and "Usage" in r.stdout)
    r = run("add", "2026-12-25")
    check("add without a text is refused", r.returncode == 1 and "Usage" in r.stdout)
    r = run("add", "someday", "x")
    check("add with a date that cannot be read is refused and changes nothing", r.returncode == 1 and "someday" not in rd("events.txt"))
    with open(os.path.join(hp, "events.txt"), "a") as fh:
        fh.write("nonsense line\n2026-13-45 | once | broken\n2027-01-01 | once | New plan\n")
    r = run("list")
    check("a hand-edited file: lines that cannot be read are skipped, the rest is kept", "New plan" in r.stdout and "broken" not in r.stdout and "nonsense" not in r.stdout, r.stdout)
    r = run("holidays")
    check("holidays lists the coming ones", r.returncode == 0 and len([l for l in r.stdout.splitlines() if l.strip()]) == 12, r.stdout)
    r = run("nonsense")
    check("an unknown word is refused with the list of what works", r.returncode == 1 and "add | list | remove | holidays" in r.stdout, r.stdout)
    r = run("version")
    check("version", r.stdout.startswith("homelab-calendar "))
    shutil.rmtree(hp)
    r = run("list")
    check("no Homepage folder: a plain message, no crash", r.returncode == 1 and "does not exist" in r.stdout and "Traceback" not in r.stdout, r.stdout)
finally:
    shutil.rmtree(T, ignore_errors=True)

check("the help text names the commands", all(w in m.__doc__ for w in ("homelab event add", "homelab event list", "homelab event remove", "yearly")))
check("no stray year numbers in the years() range", list(m.years(D(2026, 11, 4))) == list(range(2025, 2032)), list(m.years(D(2026, 11, 4))))
check("nothing in the file looks like a secret", not re.search(r"(password|secret|api[_-]?key)", open(PROG).read(), re.I))

print("OK" if bad == 0 else "FAIL (%d)" % bad)
sys.exit(1 if bad else 0)
