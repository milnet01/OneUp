# Changelog

All notable changes to OneUp are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and OneUp uses
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added

- **Each task row now shows how long the step took next to what it did — e.g. "3 installed · 42s".**

- **An "About" window (from the header) showing the version, MIT licence, GitHub and openSUSE package links, and a manual "check for updates" button that reports the result either way.**

- **A desktop notification when an update you started finishes — so a run you walked away from still tells you it's done (only pops up when the window isn't focused).**

- **The current version is shown in the window title and header.**

- **Flatpak reports how many apps it updated (counted before the update, like the check does).**

- **Each task row now shows what happened after a real update — e.g. "3 installed", "Up to date", "Updated", "Failed" — not just after a check.**

### Changed

- **The update engine now runs under bash strict mode (set -uo pipefail) so unset variables and mid-pipeline failures surface immediately instead of silently.**

### Fixed

- **The sudo keep-alive no longer leaves a short-lived background process behind when a run ends or is cancelled.**
  The keep-alive loop now runs in its own process group and is torn
  down as a group, so its idle `sleep` can't be orphaned (reparented to
  init for up to ~50s) after the run finishes.

## [1.0.1] - 2026-07-21

### Added

- **Added a dependency policy standard with a known-incompatibility ledger (docs/standards/dependencies.md).**

### Changed

- **RPM now requires sudo (the engine can't run any step without it); the launcher uses the packaged data path.**

- **RPM recommends snapper (the rollback feature depends on it); desktop and AppStream categories aligned.**

- **CI actions bumped to latest (checkout v7, setup-python v7, action-gh-release v3); Python build pinned to 3.13.**

### Fixed

- **"Restart services" now validates unit names before running them as root.**
  Service names come from the engine's output stream; only well-formed unit names are passed to the root systemctl, mirroring the rollback snapshot-id guard.

- **Corrected the OBS packaging guide to the home:milnet project (was home:milnet01).**

- **The weekly-check unit now also escapes $, backslash and quotes in the executable path (not just %).**

- **The sudo keep-alive survives a transient authentication blip instead of stopping for the rest of the run.**

- **Rollback validates the snapshot id before running it as root.**
  The snapshot number is checked to be numeric before it reaches the pkexec command, so a malformed value on the output stream can't be interpolated into a root shell command.

- **Ctrl-C (or SIGTERM) now cancels a run instead of cleaning up and continuing through the remaining steps.**
  The interrupt/terminate traps now exit the script, so an aborted run no longer plows on through flatpak/firmware/orphan-removal/cache after you cancel.

- **The self-update check tolerates a non-object JSON reply without throwing.**

- **The weekly-check systemd unit escapes '%' in the executable path so a '%' in the install path can't silently break the timer.**

- **An empty or unknown --steps value is rejected instead of reporting a clean run that did nothing.**

- **The sudo keep-alive is cleaned up on Ctrl-C / SIGTERM, not just normal exit.**
  trap now covers INT/TERM/HUP so an interrupted run can't leak a background loop that keeps root credentials warm.

- **Up-to-date detection is reliable on non-English systems (zypper output pinned to LC_ALL=C).**

- **Low-disk and duplicate-repo pre-flight warnings now surface in the GUI.**
  The engine emitted @@DISK@@/@@REPO@@ markers that the GUI had no handler for, so the advertised warning never appeared; both are now shown live.

- **Malformed progress markers can no longer throw out of the GUI's read slot.**
  A STEP_BEGIN line spliced by interleaved output raised an unhandled IndexError/ValueError that dropped the run's later markers; the field parse is now guarded.

- **Firmware step no longer reports success or forces a reboot when the flash actually failed.**
  fwupdmgr update failures were masked by `|| true` and always recorded as "updates applied" with a reboot nag; the step now gates success and the reboot advice on the real exit code.

## [1.0.0] - 2026-07-21

First public release — one-click updates for openSUSE system packages, Flatpaks
and firmware, plus leftover-package and cache cleanup.

### Added
- **Check for updates** — a read-only pass that reports how many updates are
  available per task (system / Flatpak / firmware) without installing anything.
- **Weekly background check** — an optional toggle that installs a systemd-user
  timer and raises a desktop notification when updates are ready.
- **Light/dark theme** — the window now follows the desktop colour scheme and
  switches live.
- **Restart services instead of rebooting** — after a package-only update, OneUp
  offers to restart just the affected services rather than the whole machine.
- **Retry failed steps** — re-run only the steps that errored.
- **Open log file** — jump straight to the saved log of the last run.
- **Roll back this update** — restore the pre-update snapshot (and reboot) from
  a labelled `OneUp pre-update <date>` snapper snapshot.
- **Pre-flight checks** — warn about low disk space (`/`, `/var`) and duplicate
  repository URLs before starting.
- **Plain-English error hints** — common zypper failures (disk full, bad GPG
  key, network, package conflict) are explained in one line.
- **Self-update check** — notice when a newer OneUp release is available.
- **Single-file AppImage** and an **RPM** package; a release workflow builds and
  attaches the AppImage to each tagged GitHub release.

### Fixed
- No longer advises a reboot when nothing was installed, or when a step failed
  (the false-"reboot needed" nag).
- Stops PackageKit holding the package lock before running zypper, so updates
  don't fail right after login.
- Cache clean-up runs non-interactively (no more "bad stream or EOF").

[1.0.1]: https://github.com/milnet01/OneUp/releases/tag/v1.0.1
[1.0.0]: https://github.com/milnet01/OneUp/releases/tag/v1.0.0
