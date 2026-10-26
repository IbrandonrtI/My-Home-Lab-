# Runs the installer on a real pseudo-terminal (so the live status line and the Enter pause are used) and saves
# everything it printed to $SIM_DIR/pty.out. Answers are sent whenever the last line on screen ends with ":".
import os, pty, select, time, fcntl, termios, struct, re
sim = os.environ["SIM_DIR"]
answers = ["Tester", "tester@example.com", "", "", "", "CorrectHorse1234", "CorrectHorse1234", "yes", "", "y", "", "", "", ""]
cols, rows = 100, 40
pid, fd = pty.fork()
if pid == 0:
    os.environ.update(COLUMNS="200", TERM="xterm", LANG="C.UTF-8")   # a stale copy of the width, as `sudo` passes on; the real window is `cols` wide
    os.execvp("python3", ["python3", os.environ["HLS_REPO"] + "/installer/homelab-setup", "install"])
fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
BAR = re.compile(rb"\x1b7\x1b\[\d+;1H.*?\x1b8", re.S)
seen = 0
raw, idx, t0, last = b"", 0, time.time(), time.time()
while time.time() - t0 < 170:
    r, _, _ = select.select([fd], [], [], 0.5)
    if r:
        try:
            d = os.read(fd, 65536)
        except OSError:
            break
        if not d:
            break
        raw += d
        shown = len(BAR.sub(b"", raw))               # the pinned bar repaints several times a second: only other output counts
        if shown != seen:
            seen = shown
            last = time.time()
    if time.time() - last > 0.6:
        tail = re.sub(rb"\x1b\[[0-9;?]*[a-zA-Z]", b"", BAR.sub(b"", raw)).decode("utf-8", "replace").rstrip().splitlines()[-1:] or [""]
        if tail[0].rstrip().endswith(":") and idx < len(answers):
            os.write(fd, (answers[idx] + "\n").encode())
            idx += 1
            last = time.time()
open(sim + "/pty.out", "wb").write(raw)
