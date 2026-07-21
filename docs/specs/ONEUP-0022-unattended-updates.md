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
  minimum width (currently 720, sized for five header controls — updater.py:723) drops back
  to 560 now that the header carries four.
- **`SettingsDialog(QDialog)`** (distinct from the existing `self.settings` `QSettings`
  handle and the "Settings" header button) — modeled on `RepoManagerDialog`: created lazily,
  re-centred
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
- **New headless entrypoint.** `--update` is a **GUI-only** flag consumed by `updater.py`'s
  `main()` (twin of `--check`); it is **never passed to the engine**. `main()` dispatches it
  to `_headless_update()`, which runs `bash <engine> --notify` (no `--update`) — all steps,
  since the engine's default `STEPS` is every step — and returns the engine's exit code. The
  engine's arg parser rejects unknown flags with `exit 2` (update_system.sh:79), so the
  `--update` token must not reach it.
- **Auto-update state** is read like weekly-check: `systemctl --user is-enabled
  oneup-update.timer`.
- **Coupling (rule 2 — enable).** The passwordless grant is **asynchronous and gives no
  synchronous success return** — `_run_auth` starts a `QProcess`; `_on_auth_finished`
  re-probes via `_query_auth_status`, whose result settles later in
  `_on_auth_status_finished` (updater.py:1144–1168). A cancelled `ksshaskpass` popup and a
  successful grant both flow through that same re-probe. So the enable flow cannot "install
  the timer on grant success" inline; it must chain on the async settle:
  - `on_autoupdate_toggled(on=True)`: read the **reflected** passwordless state — the
    dialog's passwordless switch, which its open-time `--auth-status` probe already set.
    (No new synchronous state read is invented; the switch is the current truth.)
  - If passwordless is **already on** → install the update timer directly (synchronous, like
    weekly-check).
  - If passwordless is **off** → show one dialog ("Automatic updates need Passwordless…").
    On **cancel**, revert the auto-update toggle to off, no further action. On **approval**,
    set a one-shot `self._pending_autoupdate = True` latch and start the passwordless grant.
  - The settle point (`_on_auth_status_finished`) checks the latch: if set **and**
    passwordless is now **on**, install the update timer and set the auto-update toggle on;
    if set and passwordless came back **off** (popup cancelled, `visudo` rejected, grant
    failed), leave auto-update off and surface the same `@@HINT@@`/note the grant already
    shows. Clear the latch either way.
- **Coupling (rule 3 — revoke).** Hooked to the revoke **action** (the `on=False` branch of
  `on_auth_toggled`), not to the toggle signal — the programmatic `blockSignals` set used to
  reflect probed state must not trip it. When the user revokes passwordless, if the
  auto-update timer is enabled, remove it and reflect the auto-update switch as off via a
  `blockSignals` set (no re-fire of `on_autoupdate_toggled`), with a one-line note. Removal
  is a local systemd-user operation, independent of the revoke process's own outcome.

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

## Failure modes

Every path that does not end in a working, passwordless-backed timer must leave the
auto-update toggle **off** and tell the user why — never a silent half-state.

| Situation | Behaviour |
|-----------|-----------|
| Engine binary missing (`ENGINE.exists()` false) | Auto-update can't be enabled; toggle reverts to off (mirrors `_query_auth_status` returning early at updater.py:1101). |
| Combined-enable dialog cancelled | Both stay off; no grant started, no latch set. |
| Passwordless popup cancelled / `visudo` rejects / grant process fails | Re-probe reports passwordless **off**; the pending-enable latch resolves to "leave auto-update off" and surfaces the grant's `@@HINT@@`. |
| `_install_user_timer` raises `OSError` (can't write `~/.config/systemd/user`) | Caught and shown via `QMessageBox.warning`, mirroring `on_autocheck_toggled`'s existing handler (updater.py:1078); auto-update toggle reverts to off. |
| `systemctl --user enable` non-zero | Timer files exist but aren't active; treated as install failure — toggle reverts to off (same `check=False` + state re-read pattern as weekly-check). |
| Revoke of passwordless while auto-update on | Auto-update timer removed regardless of the revoke process's outcome (removal is a local systemd-user op); auto-update switch reflected off with a note. |
| Unattended run itself fails at 2am | Engine records the failure, continues remaining steps, and the end-of-run `--notify` fires "Update failed — see log" (no new behaviour — same engine path as a manual run). |

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
