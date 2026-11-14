# Tests

These tests run the installer against a simulated machine (fake `apt`, `docker`, Tailscale and web services), so nothing on the
machine running them is changed.

```bash
bash tests/run_all.sh          # everything, about 10 minutes
bash tests/run_all.sh quick    # a few scenarios, about 1 minute
bash tests/run_tests.sh S1     # one installer scenario (for example S1, S24, S41)
```

Needs `python3` and `bash`.

| File | What it is |
| --- | --- |
| `run_tests.sh` | The installer scenarios (S1 to S43, with gaps): full install, dry run, failures, restore, existing server, the last steps finishing in a background job (S41, `HLS_BG=1`), the quiet schedule that continues the install automatically (S42), Downtify and MeTube moved into the `music-downloader` Portainer stack, with a rollback when Portainer refuses (S43), and more. |
| `t_subst.py` | Unit test for the placeholder substitution (`subst()`). |
| `t_names.py` | Unit test for the drive names FileBrowser uses (sizes such as 1 TB, odd characters, duplicate names, the names file). |
| `t_drivenames.sh` | Tests the drive names in `scripts/drives` (size, brand, HDD or SSD, numbering of identical drives, a chosen name) against the installer's own code, and the pool options (fill one drive at a time). |
| `t_check.py` | Unit test for the secret scan in `scripts/homelab-repocheck` (real-looking values are reported, placeholders are not). |
| `t_homepage.sh` | `homelab theme` and `homelab bookmark` in a temporary copy of the Homepage files, with a local web server that simulates Brandfetch. |
| `t_power.sh` | `homelab-backup` keeps the backup drive awake while it runs and lets it sleep again afterwards (fake `hdparm`). |
| `t_widgets.sh` | The Homepage drive pills ("Main pool", "Backup pool", "Connect ... Drive") kept by `homelab-sample`. |
| `t_update.sh` | `homelab-update` against a fake Docker, registry and Portainer (`fakeupd.py`): new version numbers, upload check, database dump, updating through Portainer, the guards. |
| `t_alerts.py` | `homelab-alerts`, the file behind the notification bell: fake Docker and Tailscale, containers down, updates, drives, backups, temperatures. |
| `t_updates_tab.py`, `t_updates_ui.py` | The panel's Updates screen: the server side (the update job, the sudo commands) and the page in a browser. |
| `t_hlcards.py`, `t_hlcards_ui.py` | Customizing the cards HomeLab fills in (At a Glance, Storage, Calendar ...): rename, icon and color, hide, move, Add From HomeLab's List, Put Them Back, and the `customized` mark that stops an upgrade from rewriting them. The server side and the page in a browser. |
| `t_mythemes.py`, `t_mythemes_ui.py` | The theme creator: a custom theme holding the look, picture, layout and cards, applying it again, Undo, rename, delete. The server side and the page in a browser. |
| `t_uninstall.sh` | `sudo homelab-setup uninstall` on the fake machine: dry run and cancel change nothing; keep or wipe the app data; keep or erase the drives (typed words, a wrong word keeps the drive, a drive that was not in a pool is never offered); a RAID/ZFS array is left alone; a machine built by hand is refused; Tailscale, Docker and containers that are not part of the lab are kept. |
| `t_bootstorage.sh` | The boot drive as the default storage of Main (fake loop drives, real mergerfs): no drive means an open folder with the Immich marker files; connecting a drive copies the files first; `drives moveboot` copies again, checks, and asks before removing the old copies; `drives moveboot` from the panel (the Move button) runs the same flow without questions; a missing Main drive makes `drives guard` and Fix Drives run the services from the boot drive; when the drive is back the files saved meanwhile are offered, and a file that differs on both sides is never replaced. |
| `t_uninstall_drives.sh` | The same with the real drives tool, fake loop drives and real mergerfs: keeping the files (they stay readable after the pools are taken apart) and erasing drives one by one. Skipped where loop devices are missing. |
| `t_bell.py` | The notification bell on the dashboard, in a browser with a fake `alerts.json`. |
| `t_installring.py` | The install progress ring next to the bell, in a browser with a fake `install-status.json`: progress, failure, stale status, done, phone width. |
| `start.sh` | Builds the simulated machine and defines the `hls`, `fresh`, `wj` and `setw` helpers. |
| `simlib.py`, `server.py`, `fakecmd.py` | The simulated machine, its web services and its commands. |
| `mkbackup.sh`, `mkexisting.py` | Create a simulated backup and a simulated server that was already set up manually. |

The tests copy `installer/`, `scripts/`, `stacks/` and `homepage-config/` into a temporary folder
(`$TMPDIR/homelab-sim`), so run `tools/build.sh` first after changing anything under `src/`.

**Not covered:** real hardware, real Docker images, real Tailscale, Ubuntu Server. Test those on a disposable VM.
