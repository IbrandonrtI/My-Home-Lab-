# Contributing

This is a personal home lab, but the repository is meant to be easy to read, test and change. This page explains how the pieces fit and what to run before you change something.

## Where things are

| Folder | What it holds | Edit by hand? |
| :--- | :--- | :--- |
| `src/` | The parts of the installer (`p01_core.py` to `p09_main.py`) | Yes |
| `installer/homelab-setup` | The installer, built from `src/` | **No**: run `bash tools/build.sh` |
| `stacks/` | One Compose file per Portainer stack | Yes |
| `homepage-config/` | Homepage settings, widgets and styles | Yes |
| `scripts/` | Server commands and `SHA256SUMS` | Yes, then regenerate `SHA256SUMS` |
| `tests/` | Simulation tests | Yes |
| `docs/` | The guides | Yes |

## Rules

- **No real values in any file.** Use `your-username`, `192.168.X.X`, `your-tailnet.ts.net` and `your-own-key`. `scripts/homelab-check` looks for anything that resembles a real key.
- **Never write a secret** into a repository file, a log or the installer's state file.
- **The installer never formats or modifies a drive**, and every command that changes the machine goes through `act()` so `--dry-run` works.
- **Pin image versions** in `stacks/` and say so in `CHANGELOG.md` when you change one.
- **A behaviour change gets a test** (see below) and a line in `CHANGELOG.md` under "Changed behaviour".
- **Line endings are LF.** `.gitattributes` enforces it.

## Before you open a pull request

```bash
bash tools/build.sh                        # rebuild installer/homelab-setup after editing src/
cd scripts && sha256sum $(ls | grep -v SHA256SUMS) > SHA256SUMS && cd ..   # after editing a script
python3 scripts/homelab-check .            # links, YAML, scripts, checksums, secrets
bash tests/run_all.sh quick                # a minute; run without "quick" (about 10 minutes) for the whole suite
```

The checks in `.github/workflows/checks.yml` run the same things on every push and pull request. They need `shellcheck`, `ruff`, `pyyaml` and `pyte` (`pip install ruff pyyaml pyte`).

Useful tools: `shellcheck scripts/*`, `ruff check installer tests`, and `markdownlint-cli2 "**/*.md"`.

## Testing on a real machine

The simulation cannot prove everything. For changes to the installer, run it on a throw-away virtual machine ([VM test guide](docs/vm-test-guide.md)) and write what you verified, and what you could not, in the pull request.

## Reporting a problem

Open an issue with the form that fits. Include the failing step's text from `sudo homelab-setup`, the last lines of `/var/log/homelab-setup.log` and your operating system version. **Never paste passwords, API keys or the contents of `secrets.env`.**
