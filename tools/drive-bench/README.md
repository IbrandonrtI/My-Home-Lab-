# drive-bench

A test run that tries **every drive command, every option and every answer** on fake drives, in many pool layouts, and then
writes a report: what works, what is refused and why, what is broken, and what could still be added.

## Start it

```bash
cd ~/My-Home-Lab-
sudo bash tools/drive-bench/drive-bench --level quick       # about 20 to 30 minutes: look at the result first
sudo bash tools/drive-bench/drive-bench                     # standard: a few hours
sudo bash tools/drive-bench/drive-bench --level full        # every layout, every scenario: many hours (leave it overnight)
```

The report is written to `/var/tmp/drive-bench/`:

| File | What it is |
|---|---|
| `report.html` | The report to read: problems (ranked), what works, a layout × command grid, every question asked, ideas to add. Open it in a browser. |
| `report.txt` | The same as plain text. Send this file (or its first part) when you want a bug or a feature looked at. |
| `findings.json` | The problems and ideas as data. |
| `results.jsonl` | One line per run with the full screen output. Everything else is made from this file. |

If the run is stopped (or the computer restarts) continue with the same command plus `--resume`.
To rebuild the report from an earlier run: `sudo bash tools/drive-bench/drive-bench --report-only`.

## What it touches

* **The drive tests** run the real `drives` script in its own test mode on **fake drives**: files turned into drives with `losetup`.
  The fake drives, their pools and their fstab live in `/var/tmp/drive-bench/env/`. Your real drives, pools, `/etc/fstab` and
  containers are **never touched** by these tests. `docker`, `hdparm`, `smartctl`, `udisksctl` and the drive model lookup are replaced
  by fakes that only exist inside that folder. The real drives of the machine are hidden from `drives` during the run, and the bench
  refuses to type the name of any drive that is not one of its own fake drives.
* **The other commands** (`homelab`, `homelab-sample`, `homelab-backup`, `homelab-update`, `homelab-restore-configs`,
  `homelab-selftest`, `hdd-recover`, `homelab-setup`, `drives`) first run on the fake layouts (they are pointed at the fake pools).
  Then they run **for real on this server** in tiers (`--real full`, the default):

  | Tier | What happens | Examples |
  |---|---|---|
  | safe | only prints | `version`, `help`, `status`, `list`, unknown words |
  | asks | the command is started and every question is answered "no" | `homelab-update` (every stack: no), `clean`, `restore-configs` |
  | real | really does its job | a backup, a self-test, `hdd-recover` (containers stop for about a minute), `homelab-update check`, `homelab-sample` |
  | dangerous | **never run**, listed in the report as NOT-RUN | `homelab-update --yes`, `restore-configs restore`, `homelab-setup install` / `refresh`, `homelab theme` / `bookmark` |

  Before the real tiers the bench stops, and says why, when **a backup is running** or **files are being uploaded**. It asks you to
  type `REAL` first (`--yes-real` skips the question). `--real safe` runs only the safe tier, `--real off` skips the real runs.

## Options

```
--level quick|standard|full   how much to try
--layout REGEX                only layouts whose name matches (repeatable), e.g. --layout '^m2-b1$' --layout boot
--flow NAME                   only this command (repeatable): menu status connect disconnect move adopt power recover replace
                              fillorder release bootsection restore, and cli, faults, wish
--budget N                    runs per command and layout
--timeout SECONDS             how long one run may take (default 120)
--no-other / --other-only     skip / only run the other commands
--real off|safe|full          the real runs on this server
--resume, --report-only, --work FOLDER, --out FOLDER
```

## What "a layout" is

Names look like `m3-b2`: 3 Main drives, 2 Backup drives. The standard level builds every combination of 0 to 5 drives in each pool
(36), plus 6, 8 and mixed bigger ones, drives of different makers, types (HDD, SSD, USB, NVMe, unknown) and sizes, drives that
already hold files, a nearly full drive, boot drive sections, the old single-data-drive setup (`legacy-single-drive`), an old pool
that does not fill drive by drive (`oldpool-…`), and spare drives that are blank, hold ext4 files or are formatted for Windows (vfat).
Every layout is built with the real `connect` flow, saved, and copied back before each run that changed it.

## What it tries

* **Every command, every question, every answer.** The first run answers nothing (so the first question is seen). Then every sensible
  answer to that question is tried, then the next question, and so on: most normal answers first, then "wrong" ones (Enter, `0`,
  a number that is too big, text instead of a number, `YES`, extra spaces, the wrong confirmation word).
* **Before the command starts:** a drive is unplugged, a backup drive is unplugged, both, a drive is full, a drive is read-only,
  something holds the pool busy.
* **In the middle of a command** (after the 1st, middle and last answer): a drive disappears, a drive fills up, a drive turns
  read-only, a program holds a drive or the pool, containers refuse to stop or to start, mounting fails.
* **The safety options**, on the normal path of every command that changes something: `--dry-run` (nothing may change, no container may
  stop, a plan must be printed), `--yes --confirm-erase` (must give the same result as typing the answers), and a backup that is
  running (the answer no stops with nothing changed, `--now` goes on, waiting ends when the backup ends, waiting too long gives up).
* **Words people might expect** (`rename`, `smart`, `sleep`, `balance`, …): reported as supported or not.
* **After every run that changed something:** fstab, mounts, pools, containers and files are checked, and `drives status` is run
  as a health check.

## How to read the report

* **Problems** are ordered by how serious they are (HIGH, MEDIUM, LOW). Each says how often it happened, in which layouts, exactly how to
  repeat it (layout, command, the answers typed, what went wrong first) and the last lines on the screen.
* **What works and what does not**: each ability of the drive tools, with the layouts where it worked.
* **What is refused, and why**: the explanations people see, with the layouts where they appear. This is the list of "not possible with
  this setup".
* **Layout × command**: `D` completed, `R` refused with a message, `B` bug, `o` ran without changing anything, `c` cancelled.
* **Ideas to add**: what a full set of drive controls would still need, based on what was found.

## Not covered (test mode skips them)

`drives` skips these steps in test mode, so the bench cannot see whether they work: the real `hdparm` power settings, SMART readings,
`udisksctl power-off`, and the Homepage / FileBrowser update after a change. The report lists them in its last section.

## Clean up

The bench removes its mounts and loop devices when it ends (also after an error). If it was killed:

```bash
sudo bash -c 'for m in $(findmnt -rn -o TARGET | grep ^/var/tmp/drive-bench | sort -r); do umount -l "$m"; done
  for d in $(losetup -ln -O NAME,BACK-FILE | awk "/drive-bench/ {print \$1}"); do losetup -d "$d"; done
  chattr -R -i /var/tmp/drive-bench/env; rm -rf /var/tmp/drive-bench/env'
```

## Disk space

About 1 GB at the standard level, up to 3 GB for the biggest layouts; the fake drives are sparse files. Needs `mergerfs`, `rsync`,
`parted`, `e2fsprogs` (`sudo apt install -y mergerfs rsync parted e2fsprogs util-linux`), Python 3 and root.
