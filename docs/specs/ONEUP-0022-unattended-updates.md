# ONEUP-0022 — Optional unattended (scheduled) updates

**Status:** design
**Date:** 2026-07-21
**Kind:** feature
**Depends on:** ONEUP-0023 (opt-in passwordless authorization) — a hard runtime dependency.

## Goal

A true set-and-forget option: run the *whole* update on a weekly schedule, with the
existing snapshot + rollback safety net, for people who never want to think about it.
Off by default.

## Why it depends on Passwordless (ONEUP-0023)

A full update needs root. It runs from a **systemd-user timer** with no terminal and no
guaranteed graphical session, so the `ksshaskpass` password popup cannot appear and nobody
is watching to answer it. An unattended run can therefore only succeed when the passwordless
sudoers drop-in from ONEUP-0023 is active. This is a technical constraint, not a preference,
and it drives the two coupling rules below.

## Scope decisions (agreed with the user)

1. **Schedule granularity:** weekly only — one toggle, `OnCalendar=weekly`,
   `Persistent=true`. Mirrors the existing weekly *check* exactly. A finer schedule
   (daily / time-of-day picker) is explicitly deferred (YAGNI).
2. **Enabling Auto-update while Passwordless is off:** one dialog offers to enable **both**
   at once (routes through the existing passwordless warning + grant flow); a single
   approval turns both on. Cancel leaves both off.
3. **Turning Passwordless off while Auto-update is on:** Auto-update is also switched off,
   with a short note, so the user is never left with a schedule that would silently fail.

## UI restructure — a Settings popup

The header currently carries two background-behaviour toggles (Weekly check, Passwordless)
plus Repositories / Recenter / About. Adding a third toggle would crowd it, so the three
toggles move into a **Settings** popup:

- **Header** loses the two toggle buttons and gains a single **⚙ Settings** button.
  Final header: `Settings · Repositories · Recenter · About` (4 controls). The window
  minimum width, raised to 720 for five controls in ONEUP-0023, drops back to 560.
- **`SettingsDialog(QDialog)`** — modeled on `RepoManagerDialog`: created lazily, re-centred
  over the main window on show. Three rows, each a one-line plain-English description plus a
  toggle:
  - **Weekly check** — the existing `oneup-check.*` timer toggle (behaviour unchanged).
  - **Passwordless** — the existing ONEUP-0023 grant/revoke toggle (behaviour unchanged).
  - **Automatic updates** — new (this feature).
  The dialog shows a small inline status line for the async passwordless/auto-update work
  (grant/revoke and probe), so progress is visible while the dialog is focused.

The three existing toggle *controls and their handlers* stay owned by the `Updater` window
(minimising churn and keeping the ONEUP-0023 auth flow and its tests intact); the dialog
lays the controls out and is created once, so the buttons live in it permanently.

## Engine change (`update_system.sh`)

Today `--notify` fires only in `--check` mode ("Updates available"). Extend it to also fire
**at the end of a full run** with the outcome, reusing the existing `notify_send` helper and
the run summary the engine already computes:

- something installed → `notify_send "Update complete" "<n> packages installed…"`
- nothing to do → `notify_send "Already up to date" "…"`
- one or more steps failed → `notify_send "Update failed" "See the log: <path>"`

No new markers, no new step keys, no change to the marker contract. `--notify` remains a
no-op without `notify-send` present (as it is today).

## GUI change (`updater.py`)

- **Shared timer helper.** The weekly-check install/remove code in `on_autocheck_toggled`
  is refactored into `_install_user_timer(basename, description, exec_flag)` /
  `_remove_user_timer(basename)`, then called for both `oneup-check` (`--check`) and the new
  `oneup-update` (`--update`). Existing weekly-check behaviour is unchanged (the extracted
  helper produces the same unit files).
- **Shared command builder.** `_autocheck_command()` is generalised to
  `_headless_command(flag)` taking `--check` or `--update`, so both timers share the existing
  AppImage / `oneup` launcher / python path-resolution and `%`/`$`/quote escaping.
- **New timer pair** `oneup-update.{service,timer}`: `OnCalendar=weekly`, `Persistent=true`,
  `Type=oneshot`, `ExecStart=<headless command> --update`. `--update` runs the engine full
  (all steps) with `--notify`.
- **New headless entrypoint.** `main()` gains `--update` alongside `--check`:
  `_headless_update()` runs `bash <engine> --notify` (all steps) and returns its exit code —
  twin of `_headless_check()`.
- **Auto-update state** is read like weekly-check: `systemctl --user is-enabled
  oneup-update.timer`.
- **Coupling (rule 2 — enable):** `on_autoupdate_toggled(on=True)` first checks the real
  passwordless state (the engine `--auth-status` probe already used by ONEUP-0023). If
  passwordless is **off**, show one dialog ("Automatic updates need Passwordless…"); on
  approval, run the passwordless grant, and on its success install the update timer; on
  cancel, revert the auto-update toggle to off. If passwordless is already **on**, install
  the timer directly.
- **Coupling (rule 3 — revoke):** in the passwordless-off path of `on_auth_toggled`
  (revoke), if the auto-update timer is enabled, remove it and reflect the auto-update
  toggle as off, with a one-line note.

## Correctness invariants

- **No silent broken schedule.** The two coupling rules guarantee the auto-update timer is
  never enabled while passwordless is off.
- **Unattended run keeps the safety net.** The timer runs the same engine path as a manual
  run, so the pre-update snapshot and rollback advice (`@@SNAPSHOT@@`, reboot/rollback logic)
  apply unchanged. Reboot advice still fires only when something was installed or
  `needs-rebooting` says so.
- **Missed runs catch up.** `Persistent=true` runs a schedule missed while the machine was
  off at next boot.
- **Marker contract untouched.** No engine marker is added, renamed, or re-laid-out, so
  `CLAUDE.md`'s marker list and the parser need no change.

## Tests

- **Engine (`tests/run-tests.sh`):** a full run with `--notify` and a mock `notify-send`
  asserts one notification fires with the outcome text (installed / up-to-date / failed
  variants). `--check --notify` behaviour is unchanged (existing tests stay green).
- **GUI smoke (`tests/gui-smoke.py`):** Auto-update defaults off; enabling it with
  passwordless off triggers the combined-enable path (stubbed) and does not install the
  timer on cancel; turning passwordless off with auto-update on clears the auto-update
  toggle. Existing weekly-check and passwordless assertions stay green (their handlers are
  unchanged).

## Docs & release

- `CHANGELOG.md` `[Unreleased] / Added`: a plain-English bullet for automatic weekly updates
  (off by default; needs Passwordless; keeps the snapshot/rollback safety net).
- `README.md`: a feature bullet under "What it does".
- `ROADMAP.md`: flip ONEUP-0022 to shipped with a resolution note once landed.
- No version bump here — versioning is a separate release step (`./bump.py`).

## Out of scope

- Daily / time-of-day scheduling (deferred).
- A first-run "your first automatic update is due <date>" preview.
- Any change to how manual runs behave.
