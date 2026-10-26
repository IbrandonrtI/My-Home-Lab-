# Tests

These tests check the installer **without touching the machine they run on**. The installer is pointed at a fake
machine (fake `apt`, `docker`, Tailscale and web services).

```bash
bash tests/run_all.sh          # everything, about 10 minutes
bash tests/run_all.sh quick    # a few scenarios, about 1 minute
bash tests/run_tests.sh S1     # one installer scenario (S1 to S27, there is no S23)
```

Needs `python3` and `bash`.

| File | What it is |
| --- | --- |
| `run_tests.sh` | The installer scenarios (S1 to S27, no S23): full install, dry run, failures, restore, existing server, and more. |
| `t_subst.py` | Unit test for the placeholder substitution (`subst()`). |
| `t_names.py` | Unit test for the drive names FileBrowser uses (sizes such as 1 TB, odd characters, duplicate names, the names file). |
| `t_check.py` | Unit test for the secret scan in `scripts/homelab-check` (real-looking values are reported, placeholders are not). |
| `t_homepage.sh` | `homelab theme` and `homelab bookmark` in a temporary copy of the Homepage files, with a local web server playing Brandfetch. |
| `start.sh` | Builds the fake machine and defines the `hls`, `fresh`, `wj` and `setw` helpers. |
| `simlib.py`, `server.py`, `fakecmd.py` | The fake machine, its web services and its commands. |
| `mkbackup.sh`, `mkexisting.py` | Build a fake backup and a fake hand-built server. |

The tests copy `installer/`, `scripts/`, `stacks/` and `homepage-config/` from this repository into a temporary
folder (`$TMPDIR/homelab-sim`), so run `tools/build.sh` first if you changed anything under `src/`.

**Not covered:** real hardware, real Docker images, real Tailscale, Ubuntu Server. Test those on a throwaway VM
(see `docs/vm-test-guide.md`).
