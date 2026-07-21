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

**A gap this feature must close first.** The drop-in makes the engine's *per-command* calls
passwordless — `sudo zypper …`, `sudo snapper …`, `sudo flatpak …`, `sudo systemctl stop
packagekit` all match the scoped `NOPASSWD` rule. But the engine's up-front bootstrap
`sudo_init` (update_system.sh:285–290) runs `sudo -A … -v` — a credential *validation*, not
one of those commands. `sudo -v` is governed by sudoers' `verifypw` option, whose **default
is `all`**: a password is skipped only when *every* one of the user's sudoers entries is
`NOPASSWD`. A normal user also has a password-required `%wheel` entry, so `sudo -v` prompts —
which aborts a headless run at update_system.sh:288–289, and even makes a *manual* run under
passwordless still prompt once. So the engine needs a change (below) to skip `sudo_init`'s
interactive validate when the drop-in is active; this both unblocks the unattended run and
completes ONEUP-0023's prompt-free promise for the GUI path.

**Firmware is the exception.** `fwupdmgr` elevates through **polkit**, not sudo
(update_system.sh:440, 617–623), so the sudoers drop-in does not cover it. Under an
unattended run the firmware step may be unable to authorize and will **fail cleanly** — the
run continues and the notification reports it. The four sudo-backed steps (system, flatpak,
orphans, cache) carry the bulk of the value and do run passwordless.

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
  minimum width (currently `setMinimumWidth(720)` at updater.py:724, sized for five header
  controls) drops back to 560 now that the header carries four.
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

Two changes, both additive; no new markers, no new step keys, no change to the marker
contract.

**1. Skip the interactive bootstrap when passwordless is active.** `sudo_init` currently
always runs `sudo -A … -v` + starts a keep-alive loop (update_system.sh:285–303). Add a
guard at the top: probe the drop-in with the **same non-interactive scoped check the engine
already uses** for `--auth-status` — `sudo -k -n "$(command -v zypper)" --version` (line 416)
— and if it succeeds, `return 0` immediately (no interactive `-v`, no keep-alive). Every
privileged command the engine issues is individually `NOPASSWD`, so no cached credential is
needed. This is correct whether or not `sudo -v` would have prompted: when the drop-in is
active, skipping the validate is at worst harmless and at best the thing that makes a headless
run possible. When the drop-in is **absent**, `sudo_init` is unchanged (one interactive
prompt + keep-alive, exactly as today).

**2. Notify at the end of a full run.** Today `--notify` fires only in `--check` mode
("Updates available"). Extend it to also fire **at the end of a full run** with the outcome,
reusing the existing `notify_send` helper (update_system.sh:115–117) and the run summary the
engine already computes — `SYS_COUNT` (the installed-package count, read for the summary at
~740), the `SYS_CHANGED` / `FW_CHANGED` booleans, and `ERRORS` (~683–766):

- something installed → `notify_send "Update complete" "<n> packages installed…"`
- nothing to do → `notify_send "Already up to date" "…"`
- one or more steps failed → `notify_send "Update failed" "See the log: <path>"`

`--notify` remains a no-op without `notify-send` present (as it is today).

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
  synchronous success return** — `_run_auth` (updater.py:1144) starts a `QProcess`;
  `_on_auth_finished` (1158) re-probes via `_query_auth_status`, whose result settles later
  in `_on_auth_status_finished` (1112). The open-time state on the dialog's passwordless
  switch is also set by an **async** probe (`_query_auth_status` → `_on_auth_status_finished`,
  1094–1113), so the switch can be **stale** — not yet settled, or out of date after an
  external `sudo` change. The install decision must therefore **never** trust the reflected
  switch; it always installs the update timer only after a **fresh** `--auth-status` settle
  confirms passwordless is on. The reflected switch is used solely to pick the *entry branch*
  (whether a grant dialog is needed), not to authorize the install:
  - `on_autoupdate_toggled(on=True)`: set the one-shot `self._pending_autoupdate = True` latch,
    **disable the auto-update toggle for the duration of the async op** (as `_run_auth` disables
    `auth_btn` at updater.py:1148 — this closes the mirror race where a user un-clicks mid-probe
    and the settle then forces the toggle back on; it is re-enabled in the settle). Then branch
    on the reflected switch:
    - reflected **off** → show the combined-enable dialog. It **presents the same passwordless
      security caveat** ONEUP-0023 shows (the "effectively passwordless administrator access …
      only on a computer you trust" text at updater.py:1125–1133), led by a line explaining
      automatic updates need it — the warning content is **factored so both call sites share
      it**, never a shortened re-write that drops the consent text. On **cancel**, clear the
      latch, re-enable and revert the auto-update toggle to off via a `blockSignals` set (as
      `_set_auth_checked` does at updater.py:1089–1091, so the revert doesn't re-fire
      `on_autoupdate_toggled`). On **approval**, start the passwordless grant (`_run_auth`,
      which re-probes on finish).
    - reflected **on** → start a fresh `--auth-status` probe (`_query_auth_status`) — **no**
      direct install — so a stale-on switch can't install a timer the drop-in won't back.
  - `on_autoupdate_toggled(on=False)` (user disables auto-update): remove the update timer
    (`_remove_user_timer`); if a `_pending_autoupdate` latch is somehow still set (an enable the
    user aborted), clear it so a late settle can't re-install. No passwordless change.
  - **The settle (`_on_auth_status_finished`) is the single install gate.** After it updates
    the passwordless switch and re-enables the auto-update toggle, **if `_pending_autoupdate`
    is set** it consumes the latch (clearing it unconditionally, so a startup or dialog-open
    probe that carries no latch is a no-op here): install the update timer + set the
    auto-update toggle on **iff** the just-settled state is passwordless-on; otherwise (popup
    cancelled, `visudo` rejected, grant or probe failed) leave auto-update off and surface the
    grant's `@@HINT@@`/note. The install gates on the **settled real state**, so it is correct
    regardless of which probe the re-entry guard (updater.py:1101–1103) let run.
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
| Engine binary missing (`ENGINE.exists()` false) | Auto-update can't be enabled; toggle reverts to off (as `_query_auth_status` returns early when the engine is absent, updater.py:1100). |
| Combined-enable dialog cancelled | Both stay off; no grant started, no latch set. |
| Passwordless popup cancelled / `visudo` rejects / grant process fails | Re-probe reports passwordless **off**; the pending-enable latch resolves to "leave auto-update off" and surfaces the grant's `@@HINT@@`. |
| `_install_user_timer` raises `OSError` (can't write `~/.config/systemd/user`) | Caught and shown via `QMessageBox.warning`, then the toggle is reverted to off. **New logic:** the existing `on_autocheck_toggled` catches `OSError` and warns but does *not* revert its toggle (updater.py:1078–1080); auto-update adds the explicit revert so it never shows on after a failed install. |
| `systemctl --user enable` non-zero | The `subprocess.run(..., check=False)` calls don't raise, so after install `_install_user_timer` **re-probes** with `systemctl --user is-enabled oneup-update.timer` and returns that boolean; a non-`enabled` result reverts the toggle to off. (This explicit post-op re-probe is new; weekly-check does not currently verify its enable — see Open questions.) |
| Revoke of passwordless while auto-update on | Auto-update timer removed regardless of the revoke process's outcome (removal is a local systemd-user op); auto-update switch reflected off with a note. |
| Unattended run itself fails at 2am | Engine records the failure, continues remaining steps, and the end-of-run `--notify` fires "Update failed — see log" (no new behaviour — same engine path as a manual run). |

## Tests

- **Engine (`tests/run-tests.sh`):** a full run with `--notify` and a mock `notify-send`
  asserts one notification fires with the outcome text (installed / up-to-date / failed
  variants). `--check --notify` behaviour is unchanged (existing tests stay green).
- **Engine — passwordless bootstrap skip:** with a mock `sudo` where `-k -n zypper --version`
  **succeeds** (drop-in active), a full run completes and issues **no interactive `sudo -A …
  -v`** (the mock exits non-zero if `-A` is ever invoked); with the probe **failing**
  (drop-in absent), the run still performs the one interactive `sudo -A … -v` as today. This
  is the regression that proves an unattended run can authenticate.
- **GUI smoke (`tests/gui-smoke.py`):** the header exposes the **Settings** button and the
  `SettingsDialog` hosts the three toggles (weekly check, passwordless, auto-update).
  Auto-update defaults off; enabling it with passwordless off triggers the combined-enable
  path (stubbed) and does not install the timer on cancel; a stubbed settle with
  passwordless-**off** while the pending latch is set does **not** install the timer (the
  stale-switch race guard); turning passwordless off with auto-update on clears the
  auto-update toggle. Existing weekly-check and passwordless assertions stay green (their
  handlers are unchanged).
- **On-box acceptance (manual, not CI):** after `--grant-auth` on the real machine, a manual
  full run completes with **zero** password prompts (confirming the `sudo_init` skip and the
  `verifypw=all` reasoning hold against the live sudoers), and `--revoke-auth` restores the
  single prompt.

## Docs & release

- `CHANGELOG.md` `[Unreleased] / Added`: a plain-English bullet for automatic weekly updates
  (off by default; needs Passwordless; keeps the snapshot/rollback safety net).
- `README.md`: a feature bullet under "What it does".
- `ROADMAP.md`: flip ONEUP-0022 to shipped with a resolution note once landed.
- No version bump here — versioning is a separate release step (`./bump.py`).

## Open questions & deliberate non-changes

- **Weekly-check's toggle is not hardened here.** `on_autocheck_toggled` neither reverts its
  toggle on an `OSError` nor verifies its `systemctl enable` succeeded (updater.py:1066–1080).
  Auto-update adds both for itself; weekly-check keeps its current behaviour. Whether to
  back-port the same robustness to weekly-check is a **separate** item, not folded into this
  feature (it would change shipped behaviour of an unrelated toggle). Flag for the user.
- **`sudo_init` change touches the manual path too.** Skipping the interactive validate when
  the drop-in is active also means a *manual* GUI/terminal run under passwordless no longer
  prompts at bootstrap — the intended completion of ONEUP-0023, but it is a behaviour change
  to the manual path, so an existing engine test must confirm the non-passwordless manual run
  is untouched.

## Out of scope

- Daily / time-of-day scheduling (deferred).
- A first-run "your first automatic update is due <date>" preview.
- Any change to the *content* of a manual run (the steps it runs, its markers, its output).
