# Tests

These tests check the installer and the login screen **without touching the machine they run on**. The installer is
pointed at a fake machine (fake `apt`, `docker`, Tailscale and web services); the login screen reads fake state files.

```bash
bash tests/run_all.sh          # everything, about 10 minutes
bash tests/run_all.sh quick    # a few scenarios, about 1 minute
bash tests/run_tests.sh S1     # one installer scenario (S1 ... S25)
bash tests/run_login_tests.sh  # the login screen (scripts/homelab)
```

Needs `python3`, `bash`, and `pyte` (`pip install pyte`) for the terminal-emulator checks.

| File | What it is |
| --- | --- |
| `run_tests.sh` | The installer scenarios S1 to S27: full install, dry run, failures, restore, existing server, and more. |
| `run_login_tests.sh` | Checks of the login screen against fake state files. |
| `t_subst.py` | Unit test for the placeholder substitution (`subst()`). |
| `t_names.py` | Unit test for the drive names FileBrowser uses (sizes such as 1 TB, odd characters, duplicate names, the names file). |
| `t_check.py` | Unit test for the secret scan in `scripts/homelab-check` (real-looking values are reported, placeholders are not). |
| `t_homepage.sh` | `homelab theme` and `homelab bookmark` in a temporary copy of the Homepage files, with a local web server playing Brandfetch. |
| `t_pinned.py` | The progress bar stays on the bottom row (checked in a terminal emulator). |
| `t_pty.sh`, `t_pty.py`, `t_frames.py` | An install on a pseudo-terminal, and a reader for saved captures. |
| `start.sh` | Builds the fake machine and defines the `hls`, `fresh`, `wj` and `setw` helpers. |
| `simlib.py`, `server.py`, `fakecmd.py` | The fake machine, its web services and its commands. |
| `mkbackup.sh`, `mkexisting.py` | Build a fake backup and a fake hand-built server. |

The tests copy `installer/`, `scripts/`, `stacks/` and `homepage-config/` from this repository into a temporary
folder (`$TMPDIR/homelab-sim`), so run `tools/build.sh` first if you changed anything under `src/`.

**Not covered:** real hardware, real Docker images, real Tailscale, Ubuntu Server. Test those on a throwaway VM
(see `docs/vm-test-guide.md`).
