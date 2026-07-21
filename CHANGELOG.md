# Changelog

All notable changes to OneUp are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and OneUp uses
[semantic versioning](https://semver.org/).

## [Unreleased]

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

## [1.0.0] - 2026-07-21
- First public release: one-click updates for openSUSE system packages,
  Flatpaks and firmware, plus leftover-package and cache cleanup.

[Unreleased]: https://github.com/milnet01/OneUp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/milnet01/OneUp/releases/tag/v1.0.0
