# Changelog

All notable changes to this project are written here, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project has no version numbers; entries are dated.

## 2026-10 - Repository reorganisation

This release reorganises the whole repository, rewrites the documentation and adds automatic checks. The installer itself is the version with the progress bar pinned to the bottom row ("upload 23"). Read **Changed behaviour** before you update a machine that already runs the lab.

### Changed behaviour

These change what the scripts or stacks do on a live machine:

- **Stack images are pinned.** `homepage` (v2.6.0), `speedtest-tracker` (1.15.1), `filebrowser` (v2.63.23), `beszel` and `beszel-agent` (0.21), `nextcloud` (35-apache, both containers) and `netdata` (stable) no longer use `latest` or no tag. A redeploy from these files pulls those exact versions. The tags could not be checked against the registries while the files were prepared: **deploy each on a test machine first**, and see [updating services](docs/updating.md) for how to move to a newer version.
- **`beszel-agent` keeps its data in a named volume** (`beszel_agent_data`) instead of the relative folder `./beszel_agent_data`. A redeploy starts with an empty agent folder; the agent registers again with its `KEY` and `TOKEN`.
- **FileBrowser card on Homepage.** The link now opens FileBrowser's root (`:1006`) instead of `/files/750GB_HDD`, a path that did not exist. The description no longer names a drive.
- **Installed scripts name the user.** The installer now writes the machine's user name into the scripts it installs (`drives`, `homelab-backup`). A hand-installed copy is no longer byte-identical to what the installer would install, so on a machine built by hand the "scripts" step shows as not done until the scripts are reinstalled (`sudo bash setup.sh refresh`).
- **Scripts look up the user themselves.** `drives` uses `DRIVES_OWNER`, then the user who ran `sudo`, then the first normal user. `homelab-backup` uses `HOMELAB_USER`, then the first normal user, for the folders it copies. They no longer contain a personal user name.
- **Values of an earlier server are optional.** The installer used to recognise the original author's user name, address and Tailscale name in a restored backup. Now it recognises them only when you set `HOMELAB_OLD_USER`, `HOMELAB_OLD_LAN` and `HOMELAB_OLD_FQDN`.
- **`homelab` terminal width.** The login screen asks the terminal for its width first (`stty size`, then `tput cols`, then `$COLUMNS`), so it fits after a window resize.
- **Help texts.** `homelab-update --help` prints its whole header block (it is longer than before). `setup.sh --help` prints its header and then the installer's help.
- **`setup.sh`** stops when it is run through a pipe, and installs Python 3 without prompting.
- **Script versions:** `homelab` 1.8, `drives` 1.2, `homelab-update` 1.2, `homelab-sample` 1.1, `homelab-check` 2.0.

### Changed

- New folder layout: `installer/`, `scripts/`, `stacks/`, `docs/` (with `docs/images/`), `src/`, `tests/`, `tools/` and `.github/`. Where the old files went:

  | Old location | New location |
| :--- | :--- |
  | `homelab-setup/homelab-setup` | `installer/homelab-setup` |
  | `homelab-setup/DESIGN.md` | `docs/installer-design.md` |
  | `homelab-setup/VM-TEST-GUIDE.md` | `docs/vm-test-guide.md` |
  | `homelab-drives/*` | `scripts/*` |
  | `Portainer-code/*.yaml` | `stacks/*.yaml` |
  | `Services-screenshot/*.png` | `docs/images/*.png` |
  | `SECRETS-CHECKLIST.md` | `docs/secrets-checklist.md` |
  | `README.md` (sections 1 to 16) | `docs/build-guide.md`, `docs/storage.md`, `docs/nextcloud-clients.md`, `docs/maintenance.md` |
  | `TROUBLESHOOTING.md` | `docs/troubleshooting.md`, `docs/updating.md`, `docs/history/` |
  | `README.md` (section 19, the script appendix) | removed: the scripts in `scripts/` are the only copy |
- The installer is now built from `src/p01_core.py` to `src/p09_main.py` with `tools/build.sh` into `installer/homelab-setup`. The two are identical; `tools/build.sh --check` fails if they are not.
- The documentation is split by topic. The old README (3,800 lines, including a copy of every script) and the old TROUBLESHOOTING.md (3,800 lines) became the front-page [README](README.md) and the guides in [`docs/`](docs/): build guide, storage, Nextcloud clients, maintenance, updating, troubleshooting, security, history.
- The build guide no longer repeats the stack files; it links to them in [`stacks/`](stacks/).
- All personal values (user name, home address range, Tailscale network name, disk UUID) were replaced by placeholders in every file.
- Every stack file and Homepage config file starts with a comment that says what it is for and what to change.
- `homelab docs` lists the README and every guide in `docs/`.
- `homelab-check` checks the new layout: every Markdown file's links (relative to the file), the scripts and `SHA256SUMS` in `scripts/`, that the installer matches `src/`, and secrets in all files. The old comparison with a script appendix in the README is gone because the appendix is gone.
- In the build guide, AnyDesk is installed with a keyring file instead of the deprecated `apt-key add`, and Tailscale's install script is downloaded before it is run.

### Added

- `CHANGELOG.md`, `CONTRIBUTING.md`, `docs/security.md`, `tests/README.md`, `tools/build.sh`, `ruff.toml`.
- Automatic checks on every push and pull request (`.github/workflows/checks.yml`) and issue forms for bugs and questions.
- Simulation tests: scenario S24 (a server that already runs the lab is only read), S25 (placeholder substitution), and `tests/run_all.sh`.
- `tests/t_check.py` (tests of the secret scan in `scripts/homelab-check`) and two new rounds in the [VM test guide](docs/vm-test-guide.md): a real backup drive with the daily backup, and a restore onto a new machine, plus an exact procedure for the "devices use AdGuard Home" step.
- Notes in the guides about the `docker` group being root-equivalent, and about the Docker socket and the `/` mount in Homepage.

### Fixed

- A latent Homepage link (FileBrowser) and a typo in the FileBrowser description.
- The installer's label for the first Homepage resources pill now matches the shipped `widgets.yaml`.
- The weekly/daily contradiction about the backup in the Nextcloud guide.
- Unused imports and implicit exception chaining in the installer (no change in behaviour).
- Wrong step numbers in several cross-references.

### Not done on purpose

- No `LICENSE`, `SECURITY.md` or `.gitignore` were added. Without a licence, others have no permission to reuse the code.
- The structure of `custom.css` (duplicate media blocks, `!important`) is unchanged because it could not be checked by eye.
