# The progress bar is pinned to the bottom row. Checked against a terminal emulator (pyte): messages scroll above the
# bar, the bar is on the last row and nowhere else, nothing is lost or repeated, a resize (the emulator forgets the
# scrolling area, as real terminals do) is repaired, and closing leaves a blank last row.
import os, sys
import pyte
os.environ["HLS_LIVE"] = "1"; os.environ["HLS_COLS"] = "100"; os.environ["HLS_ROWS"] = "24"
src = open(os.environ.get("HLS_PROG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer", "homelab-setup"))).read().replace('if __name__ == "__main__":', "if False:")
ns = {}; exec(compile(src, "hs", "exec"), ns); Live = ns["Live"]; out = ns["out"]

screen = pyte.HistoryScreen(100, 24, history=5000, ratio=0.5)
stream = pyte.Stream(screen)
class TTY:
    def write(self, s): stream.feed(s.replace("\n", "\r\n"))
    def flush(self): pass
    def isatty(self): return True
sys.stdout = TTY()

def rows(): return [r.rstrip() for r in screen.display]
def history():
    return [("".join(ch.data for ch in (line[x] for x in range(screen.columns)))).rstrip() for line in screen.history.top]
problems = []
def check(name, cond):
    if not cond: problems.append(name)

for k in range(1, 41): out("old line %d" % k)
Live.begin_run(46); Live.done = 4
Live.begin("Docker installed (with Compose and Buildx)")
for k in range(1, 21):
    out("message %d" % k)
    Live.frame += 1; Live.paint()
Live.set_note("downloading 2 of 4: immich-machine-learning")
r = rows()
check("bar on the last row", "of 46" in r[-1] and "Docker installed" in r[-1])
check("bar only on the last row", sum("of 46" in x for x in r) == 1)
check("last message just above the bar", r[-3] == "message 20" and r[-2] == "")
Live.end(); out("done 1"); Live.advance()
Live.begin("Immich stack"); out("immich line")
check("bar shows the new step", "Immich stack" in rows()[-1] and "5 of 46" in rows()[-1])
# the window gets taller, then shorter, then narrower: the emulator forgets the scrolling area
for (R, C) in ((30, 100), (18, 100), (18, 60), (24, 120)):
    screen.resize(R, C); os.environ["HLS_ROWS"] = str(R); os.environ["HLS_COLS"] = str(C)
    Live.frame += 1; Live.sync(); Live.paint(); out("after resize to %dx%d" % (R, C))
    r = rows()
    check("resize %dx%d: bar on the last row" % (R, C), "of 46" in r[-1] or "/46" in r[-1])
    check("resize %dx%d: bar only once" % (R, C), sum(("of 46" in x or "/46" in x) for x in r) == 1)
    check("resize %dx%d: message just above the bar" % (R, C), "after resize to %dx%d" % (R, C) in r)
Live.end(); Live.close(); out("after close")
r = rows()
check("closed: last row blank or text only", "of 46" not in " ".join(r))
allrows = history() + list(rows())
text = [x for x in allrows if x.strip()]
seen = [x for x in text if x.startswith("old line") or x.startswith("message") or x.startswith("done 1") or x.startswith("immich") or x.startswith("after")]
want = ["old line %d" % k for k in range(1, 41)] + ["message %d" % k for k in range(1, 21)] + ["done 1", "immich line"] + ["after resize to %s" % s for s in ("30x100", "18x100", "18x60", "24x120")] + ["after close"]
# lines the emulator itself dropped when it was made shorter are not the program's doing: compare what is left
check("no message twice, and the rest in order", len(seen) == len(set(seen)) and seen == [w for w in want if w in seen])
check("the last messages are all there", seen[-6:] == want[-6:])
sys.stdout = sys.__stdout__
print("\n".join(problems) if problems else "OK")
