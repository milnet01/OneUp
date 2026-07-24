# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

OneUp is a one-click update dashboard for openSUSE (Tumbleweed and Leap). It runs the
five update tasks openSUSE actually needs — system packages, Flatpaks, firmware,
leftover-package removal, and cache cleanup — the way the distro's docs recommend, behind
per-task toggles. See `README.md` for the user-facing rationale.

## Run & test

```bash
python3 updater.py                      # launch the GUI (needs PySide6 / Qt 6)
./update_system.sh                      # run the engine standalone in a terminal (all steps)
./update_system.sh --steps=system,cache # run only selected steps
./update_system.sh --check --notify     # read-only "updates available?" pass (no root)
tests/run-tests.sh                      # full test suite; non-zero exit on any failure
./local-CI.sh                           # local CI gates (tests/lint/validation/version-lockstep) — ~1s; run before every push
./local-CI.sh --full                    # also run the AppImage build (needs a good connection; 10-min timeout)
```

There is no build step for development — it's a Python script plus a Bash script. `python3
updater.py` from the checkout runs the live code directly. The tests take no arguments and
run every scenario; to focus on one, comment out the others in `tests/run-tests.sh` (there
is no per-test selector).

**Always run `./local-CI.sh` (green) before pushing.** It gates on the same test suite
GitHub CI runs, plus extra checks CI doesn't (lint, desktop/AppStream validation, and a
six-site **version-lockstep** check) — all in ~1 second. The **AppImage build** is opt-in
(`--full`): `appimagetool` downloads its runtime from GitHub each run and can stall on a
slow/filtered link, and GitHub CI builds + verifies the AppImage on every tag push anyway, so
the local build is a convenience (wrapped in a 10-min timeout). A `githooks/pre-push` hook
runs the fast gates automatically; enable it per clone with `git config core.hooksPath
githooks`. Keep `local-CI.sh` and `.github/workflows/release.yml` in sync — add a new gate to
both.

## Architecture: a thin GUI driving a privileged engine

The whole app is two files with a deliberate privilege split:

- **`update_system.sh`** — the engine. Does all the real work and is the only part that
  touches root. Authenticates **once** up front (`sudo -v` via the `ksshaskpass` popup) and
  keeps the credential warm for the run, so one password prompt covers everything. Fully
  usable on its own in a terminal.
- **`updater.py`** — a PySide6 (Qt 6) front-end. **Never runs as root.** It shells out to
  the engine via `QProcess` (`Updater._launch`), passing `--steps=…` and reads the engine's
  stdout line-by-line.

They communicate through a **line-based marker protocol**: the engine prints
`@@MARKER@@|payload` lines (defined in the header comment of `update_system.sh` around line
79); the GUI parses them in `Updater.handle_marker` (updater.py ~line 786) and updates
progress bars, badges, and banners. Non-marker lines are plain log output. The markers are
the contract between the two files — **changing a marker's name or field layout in one file
means updating the parser in the other, and the assertions in `tests/run-tests.sh`.**
Current markers: `STEP_BEGIN`, `STEP_END`, `TIMING`, `SNAPSHOT`, `CHECK`, `CHECK_ITEM`,
`SIZE`, `FREED`, `AUTH`, `DISK`, `REPO`, `REPO_SKIPPED`, `HINT`, `REMEDY`, `SERVICES`,
`INSTALLED`, `REBOOT`, `DONE`.
(`CHECK_ITEM|key|name|from|to` carries one changed package for the `--check` preview
panel; `SIZE|key|download` carries the on-demand download-size figure from `--size=<step>`;
`FREED|cache|human` carries the disk the cache clean reclaimed (measured before/after
`zypper clean --all`), which the GUI shows as the cache row's "Reclaimed 1.4G" badge;
`AUTH|on|off` reports whether the opt-in passwordless-authorization drop-in is active, for
the engine's `--grant-auth` / `--revoke-auth` / `--auth-status` actions; `REMEDY|import-keys`
signals a one-click GUI fix for a failure — a rotated/expired repo signing key — which the
warn banner offers as "Import signing key & retry", re-running the engine with `--import-keys`
after a warned confirmation. `REPO_SKIPPED|alias|reason` reports a source set aside for this
run — via the `--skip-repo=<alias>` flag (repeatable) or `--auto-skip-repos` unattended
auto-detection — and `REMEDY|skip-repo|alias` offers the matching "Skip <source> & update the
rest" retry.) (`INSTALLED|count|sys_changed|fw_changed`
carries the change summary the GUI uses to decide the reboot/rollback banners;
`REBOOT|yes|no[|reason]` carries an optional third field naming why a reboot is
advised — e.g. `yes|a new kernel and your NVIDIA graphics driver were installed`,
built by the engine from the system transaction log (kernel / graphics-driver /
DKMS-module names); the GUI shows it verbatim in the reboot banner, falling back
to the generic wording when the field is absent;
`TIMING|key|seconds` carries each step's duration, appended to its row badge.)

Step keys (the run order, shared by both files): `system, flatpak, firmware, orphans, cache`.
In `updater.py` they live in the `TASKS` list; in `update_system.sh` in the `LABEL` map.

### Correctness invariants the tests lock in

The test suite exists mainly to protect a specific class of bug — **a step must never claim
success or advise a reboot it didn't earn.** When editing engine logic, preserve these:

- Reboot advice (`@@REBOOT@@|yes`) fires **only** when something was actually installed **or**
  `zypper needs-rebooting` explicitly says so — never merely because a step errored.
- A **failed** step is recorded, emits a plain-English `@@HINT@@`, and the run **continues**
  to the next step (so cache cleanup still happens and the summary is useful).
- A package-only change (no kernel/core update) offers a **service restart** (`@@SERVICES@@`),
  not a reboot.
- `--check` mode is strictly read-only, runs **without root**, and must never call
  `zypper dup`/`update` (the test mock exits 99 if it does).

The tests build a throwaway `PATH` of mock tools (`zypper`, `flatpak`, `sudo`, `snapper`, …)
so the real machine is never touched — no root, no network. Add a regression test here for
any engine behaviour change.

## Packaging & versioning

Three distribution paths:

- **AppImage** — `packaging/appimage/build-appimage.sh`, built and attached to each release
  by the `v*`-tag GitHub workflow in `.github/workflows/release.yml`.
- **RPM** — `packaging/rpm/oneup.spec` (`BuildArch: noarch`).
- **OBS** (openSUSE Build Service) — `packaging/obs/` hosts a `zypper`-installable repo.
  `_service` clones the repo and rolls the tarball `oneup.spec`'s `Source0` expects; see
  `packaging/obs/README.md` for the `osc` publish flow.

App ID is `za.co.antsprojectshub.OneUp` — the desktop file, SVG icon, and AppStream metainfo
under `data/` all use it.

**The version lives in six places that must stay in lockstep** on a release:

1. `APP_VERSION` in `updater.py` (~line 59) — the GUI reads this to self-check for newer
   GitHub releases.
2. `Version:` in `packaging/rpm/oneup.spec`
3. the `%changelog` stanza in `packaging/rpm/oneup.spec` (rpmlint rejects a `Version:` that
   doesn't match the newest `%changelog` entry).
4. `versionformat` **and** `revision` (the release tag, e.g. `v1.0.0`) in `packaging/obs/_service`.
   The `revision` is pinned to the tag on purpose — leaving it on `main` would repackage
   post-release commits under the old version number.
5. the newest `<release version="…">` in `data/za.co.antsprojectshub.OneUp.metainfo.xml`
6. the newest `## [x.y.z]` heading (and its link at the bottom) in `CHANGELOG.md`

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/); the metainfo
`<release>` notes should mirror its entries. **Don't hand-edit the six sites** — run
`./bump.py X.Y.Z` (it rewrites all six, deriving the spec/metainfo notes from the CHANGELOG
`## [Unreleased]` bullets), or `./release.sh X.Y.Z` for the whole release: bump → `./local-CI.sh`
→ commit + tag + push to GitHub (builds the AppImage) → update the OBS package via `osc`
(rebuilds the `zypper` RPM). `local-CI.sh`'s version-lockstep gate fails a push if any site drifts.

Dependency policy (CI actions, runtimes, PySide6, base images) is a standing rule — see
`docs/standards/dependencies.md`, which also carries the known-incompatibility ledger.

## Conventions specific to this repo

- **Privileged commands** in the engine go through `ASKPASS=/usr/libexec/ssh/ksshaskpass`
  (`sudo -A`), never bare `sudo` — this raises the KDE graphical prompt instead of blocking
  on stdin. Match that pattern for any new privileged call.
- Steps for absent tools (`flatpak`, `fwupd`) are **skipped cleanly**, not errored — keep
  new steps tolerant of a missing binary.
- Runtime state lives in `~/.local/state/oneup/` (`history.json`, `logs/`); the engine also
  mirrors each run's log to `~/Documents/update-logs/`.
