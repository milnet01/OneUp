# ONEUP-0018 — System-tray icon that goes "ready" when updates are waiting

**Status:** design
**Date:** 2026-07-23
**Kind:** feature
**Depends on:** nothing new. Reuses the existing read-only `--check` engine mode and the
existing systemd/`_headless_command` plumbing. **No engine (`update_system.sh`) change.**

## Goal

A small, ambient status icon near the clock (a `QSystemTrayIcon`) that quietly turns amber
when updates are waiting, so you notice without having to catch a transient weekly popup.
Right-click gives Check now / Update now / Open / Quit. Off by default. Tolerates desktops
with no system tray.

## Why this needs OneUp to run in the background

The weekly *check* (ONEUP earlier work) runs as a **separate, throwaway** process — a
systemd-user timer invokes `oneup --check` → the engine's read-only pass, which fires a
`notify-send` popup and **persists nothing**. Nothing in the app is resident, so today closing
the window quits the whole app (`main()` at updater.py:2045–2046 does `win.show(); app.exec()`
with the default quit-on-last-window-closed).

A tray icon only earns its keep if it is present **when the window is closed**. That requires
a resident process. The agreed model (with the user) is therefore:

- The tray icon is shown while a resident OneUp runs.
- Closing the window **hides to the tray** instead of quitting.
- An opt-in **Start at boot** installs an autostart entry so the resident copy launches
  (hidden, into the tray) at login.

## Scope decisions (agreed with the user)

1. **Residency:** resident + starts at login. Two independent, opt-in toggles (below), both
   **off by default**.
2. **Two Settings toggles**, not one:
   - **Show a tray icon** — governs whether a tray icon is shown *and* whether closing the
     window hides-to-tray (for any launch). Persisted in `QSettings` as `tray_enabled`.
   - **Start at boot** — installs/removes an autostart `.desktop` entry running
     `oneup --tray`. Its on/off truth is the **existence of that file** (mirroring how the
     other toggles read real systemd state, not a saved preference).
3. **Coupling (mirrors the ONEUP-0022 passwordless/auto-update coupling):**
   - Enabling **Start at boot** while the tray is off turns the **tray on** too (a boot
     launch with no tray behaviour would be a hidden ghost process).
   - Turning the **tray off** also removes **Start at boot** (can't start hidden into a tray
     that won't be shown).
4. **"Update now"** (tray menu): opens/raises the window and starts a normal run, so the user
   still sees progress and the reboot / service-restart / rollback banners (those live only in
   the window). It does **not** run headlessly.
5. **The tray check is silent.** Finding updates only recolors the icon + updates the tooltip;
   it fires **no** `notify-send`. The ambient icon *replaces* the popup (that is the whole
   point). The separate weekly-check timer, if a user has it on, still fires its own popup —
   the two features stay independent.
6. **State source:** the resident tray runs its **own** periodic read-only `--check` (reusing
   the engine unchanged) and reads the total from `@@CHECK@@|TOTAL|<n>|updates available`. It
   does **not** depend on the weekly systemd check persisting anything. Deliberate independence;
   see Alternatives.

## New CLI entrypoint

`main()` (updater.py:2020) gains a third headless-ish token, consumed by `updater.py` (never
passed to the engine, exactly like `--check`/`--update`):

- **`--tray`** — start the GUI in **resident tray mode**: build the window but do **not**
  `show()` it; create the tray icon; kick off an initial check and the periodic timer. This is
  what the autostart entry runs.

Dispatch order in `main()`: `--check` and `--update` stay first (unchanged). `--tray` is
handled inside the GUI branch (it still needs a `QApplication`), by starting the window hidden
rather than shown.

## Behaviour matrix

| Launch | `tray_enabled` | System tray present | Result |
|--------|----------------|---------------------|--------|
| normal (`oneup`) | off | — | today's behaviour: window shown, close quits. |
| normal (`oneup`) | on | yes | window shown **and** tray icon shown; close hides to tray; app stays resident. |
| `oneup --tray` (autostart) | on | yes | **window hidden**, tray icon shown, resident. |
| `oneup --tray` or normal | on | **no** | degrade gracefully: run as a normal window (shown), no tray, close quits. |

`QSystemTrayIcon.isSystemTrayAvailable()` (static; valid once the `QApplication` exists) is the
availability gate. When it is false, the two new Settings toggles are **disabled** with a
"your desktop has no system tray" note, and no tray is created regardless of `tray_enabled`.

A launch with `--tray` but `tray_enabled` **off** is not in the matrix because the coupling
prevents it (turning boot on forces the tray on; turning the tray off removes autostart). The
only way to reach it is a stale autostart file left by a failed `_remove_autostart` unlink; it
is treated as tray-not-wanted (main()'s `tray_wanted` is false), so main() shows a normal window
— degrading safely rather than starting a hidden, tray-less ghost.

## GUI change (`updater.py`) — components

All changes are in `updater.py`. New Qt imports: `QSystemTrayIcon`, `QMenu` (QtWidgets);
`QPixmap` (QtGui — `QPainter`, `QColor`, `QIcon` are already imported at updater.py:42).

### 1. Two new toggles in the Settings popup

`SettingsDialog` (updater.py:718) currently lays out three `_row(...)` entries (weekly check,
passwordless, automatic updates) at updater.py:733–742. Add two rows — **Show a tray icon** and
**Start at boot** — bound to two new buttons owned by the `Updater` window, created alongside
the existing toggles in `__init__` (near updater.py:827–859) with the same recipe
(`GhostBtn`, checkable, `PointingHandCursor`, `_refresh_*_label`, `toggled.connect(...)`):

- `self.tray_btn` — checked initial state = `self.settings.value("tray_enabled", False, type=bool)`.
- `self.startboot_btn` — checked initial state = `self._startboot_enabled()`.

When the tray is unavailable, both buttons are `setEnabled(False)` and the row descriptions
gain a "(your desktop has no system tray)" suffix. The availability check happens once in
`__init__` and is stored (e.g. `self._tray_available`).

### 2. Tray-preference persistence + toggle handlers

Follow the established `_set_*_checked` / `_refresh_*_label` / `on_*_toggled` shape:

- **`on_tray_toggled(on)`**
  - `on=True`: persist `tray_enabled=True`; if a tray is available, call `_ensure_tray()` —
    which owns **all** resident setup (icon, single-instance server, initial + periodic check,
    and `setQuitOnLastWindowClosed(False)`); see §4. It is idempotent, so a redundant call is a
    no-op.
  - `on=False`: persist `tray_enabled=False`; **also remove Start at boot** (call
    `_remove_autostart()` and reflect `startboot_btn` off via a `blockSignals` set, mirroring
    `_set_autoupdate_checked` at updater.py:1229); then tear down everything `_ensure_tray()`
    set up (the reverse of §4): **stop `self._tray_timer`** (so the periodic check stops
    shelling out once the feature is off), **close the single-instance `QLocalServer`**
    (residency is ending), hide the tray icon (`self._tray.hide()`, drop the reference),
    `setQuitOnLastWindowClosed(True)`, and if the **window is currently hidden, `show()` it**
    (never leave the app invisible with no tray and no way back).
- **`on_startboot_toggled(on)`**
  - `on=True`: **first** ensure the tray is on — if `not tray_btn.isChecked()`, set it on
    (which runs `on_tray_toggled(True)`); then `_install_autostart()`. If the install fails
    (`OSError`), warn and revert `startboot_btn` to off via a `blockSignals` set. The tray, if
    this handler just turned it on, **stays on** — that is the valid "resident this session, not
    at boot" state, not a broken half-state; only `startboot_btn` reverts. (The user can turn
    the tray off separately, which also clears boot.)
  - `on=False`: `_remove_autostart()`. (Does **not** turn the tray off — you can be resident
    this session without launching at boot.)

Coupling reverts always use `blockSignals` sets (like `_set_auth_checked` at updater.py:1276)
so a programmatic reflect never re-fires the other handler.

### 3. Autostart entry (`~/.config/autostart/za.co.antsprojectshub.OneUp-tray.desktop`)

- **`_autostart_path() -> Path`** → `Path.home() / ".config" / "autostart" /
  f"{APP_ID}-tray.desktop"`.
- **`_startboot_enabled() -> bool`** → `self._autostart_path().exists()`.
- **`_install_autostart() -> bool`** — write the file; return success. Content:
  ```
  [Desktop Entry]
  Type=Application
  Name=OneUp (tray)
  Comment=OneUp update status in the system tray
  Exec=<exec> --tray
  Icon=za.co.antsprojectshub.OneUp
  Terminal=false
  NoDisplay=true
  X-GNOME-Autostart-enabled=true
  ```
- **`_remove_autostart()`** — unlink the file, ignoring a missing file (like
  `_remove_user_timer` at updater.py:1199).

**Exec quoting is NOT the systemd form.** `_headless_command(flag)` (updater.py:1146) escapes
for **systemd** unit files — it doubles `$`→`$$` and `%`→`%%` because systemd does env-var and
specifier expansion. A **Desktop Entry** `Exec` uses *different* rules (freedesktop Desktop
Entry spec § "The Exec key"): a literal `%` is escaped as `%%`, but `$` is **literal** (must
**not** be doubled); reserved characters inside a double-quoted argument are backslash-escaped
(`"`, `` ` ``, `$`, `\`). So a new helper is required — do **not** reuse `_headless_command`
verbatim for the `.desktop` line:

- **`_autostart_exec() -> str`** — same executable resolution as `_headless_command`
  (`$APPIMAGE` → `oneup` on `PATH` → `sys.executable <script>`), but quoting each path for a
  **Desktop Entry** `Exec` per the freedesktop Desktop Entry Spec's "The Exec key" section.
  That section is explicit that the general string-value backslash-unescape (`\\`→`\`) is
  applied **before** the Exec quote-unescape, so the byte-exact literals in the file are:
  wrap the arg in double quotes; write a literal `$` as **`\\$`** (two backslashes then `$` —
  the spec's stated "unambiguous" form), a literal backslash as `\\\\`, a literal `"` as `\\"`,
  a backtick as `` \\` ``; and a literal `%` (a field code) as `%%`. Append ` --tray`.
  - **Worked example** (pin the exact bytes so the test below can assert them): a path
    `/opt/o$ne%up/oneup` becomes `"/opt/o\\$ne%%up/oneup"` — the `$` is `\\$` (the file's
    string-unescape turns `\\`→`\`, then the Exec unquote turns `\$`→`$`), the `%` is `%%`, the
    whole arg is double-quoted. Contrast `_headless_command`, which emits `$$` and `%%` for the
    same path (systemd form). Emitting the systemd `$$` here would corrupt the autostart line.

Autostart is a plain file drop — no `systemctl daemon-reload`, no enable step.

### 4. The tray icon itself

- **`_tray_icon(attention: bool) -> QIcon`** — base pixmap from `_app_icon()`
  (updater.py:1988) at 64px; when `attention`, paint a filled amber disc
  (`QColor("#f5a623")` or similar) in the lower-right quadrant with a thin contrasting ring,
  via `QPainter` on a copy of the pixmap. No new asset files; works on any theme because the
  badge is drawn, not themed. When `_app_icon()` is null (unlikely), fall back to a plain
  drawn disc so the tray is never blank.
- **`_ensure_tray()` — the single "become resident" entry point.** Idempotent: guarded by
  `self._tray is None` and `self._tray_available`, so calling it twice is a no-op. **Every** path
  that makes OneUp resident — the autostart `--tray` launch, a normal launch with `tray_enabled`
  on, and a mid-session Settings enable (`on_tray_toggled(True)`) — funnels through it, so all
  resident-setup responsibilities live in exactly one place. It:
  1. builds `QSystemTrayIcon(self)`, attaches the context menu, and connects `activated` so a
     left-click (`QSystemTrayIcon.Trigger`) calls `_show_window()`;
  2. sets the initial (neutral) icon + tooltip and `show()`s the icon;
  3. **arms the single-instance `QLocalServer`** (§8) if it isn't already listening — so a later
     second launch raises this copy instead of duplicating it, whether residency began at boot
     or mid-session (this is the fix for "a Settings-enabled tray has no server");
  4. **starts the periodic check** — the single `self._tray_timer` (§5), whose short first fire
     runs the initial `_tray_check()` — so the amber-when-waiting behaviour actually fires for
     every enable path, not just the autostart one;
  5. **`setQuitOnLastWindowClosed(False)`** so hiding the window doesn't quit the app.
  The matching teardown is `on_tray_toggled(on=False)` (§2), which reverses steps 1–5.
- **Context menu** (`QMenu`): **Check now** → `_tray_check()`; **Update now** →
  `_tray_update()` (raise window + `start_run()`); **Open OneUp** → `_show_window()`;
  separator; **Quit** → `QApplication.quit()`.
- **`_show_window()`** — `showNormal(); raise_(); activateWindow()` (also used by left-click
  and Open). Un-hiding is reliable; the *focus-raise* is best-effort — subject to the same
  Wayland limitation the app already documents for `recenter` (updater.py:1079–1082), where a
  compositor may ignore an app's self-raise. The window is shown regardless.

State is conveyed by **both** color and tooltip text (not color alone), for accessibility:

- neutral: tooltip `"OneUp — up to date"` (or `"OneUp — not checked yet"` before the first
  check completes).
- attention: tooltip `"OneUp — N update(s) waiting"`.

### 5. The periodic tray check (silent, independent of the window's Check button)

Modelled on `request_size`/`_on_size_output` (updater.py:1511–1548) — a **dedicated** QProcess
whose output parser reads only the one marker it cares about, so it never disturbs the main
window's task rows / progress bar / interactive-check state:

- **`_tray_check()`** — no-op if `ENGINE` is missing or a tray-check is already in flight
  (guard a `self._traycheck_proc` like `_size_proc`). Start `bash <ENGINE> --check
  --log=<LOG_DIR>/<stamp>.traycheck.log` with merged channels, wiring
  `readyReadStandardOutput`→`_on_traycheck_output` and `finished`→`_on_traycheck_finished`.
  **No `--notify`** (silent).
- **`_on_traycheck_output()`** — line-buffer like `_on_size_output` (updater.py:1535). The
  engine emits the **three-field** line `@@CHECK@@|TOTAL|<n>|updates available` (see
  `update_system.sh`'s `marker CHECK "TOTAL|$total|updates available"`), so parse it the way
  `handle_marker` already does at updater.py:1709–1712: strip the `@@CHECK@@|` prefix, `split("|")`,
  and when field 0 is `TOTAL` read the integer in **field 1** (ignore the trailing
  `updates available` label). Do **not** do a naïve `int(<everything after the prefix>)` — that
  would choke on the third field. Call `_apply_tray_total(n)`; ignore every other line (do
  **not** append to the window log).
- **`_on_traycheck_finished()`** — release the finished `QProcess` (`deleteLater()` + drop
  `self._traycheck_proc`), mirroring `_on_size_finished` (updater.py:1549), so a weeks-long
  resident session (~4 checks/day) doesn't accumulate dead QProcess objects on the window.
- **`_apply_tray_total(n: int)`** — store `self._tray_total = n` and `self._tray_checked_at =
  now`; if the tray exists, set `_tray_icon(n > 0)` and the matching tooltip.
- **Cadence:** **one** `QTimer` (`self._tray_timer`) started by `_ensure_tray()` (§4, step 4).
  Its first fire is short — `TRAY_INITIAL_DELAY_MS` (a few seconds, so login isn't slowed) — and
  its `timeout` handler runs `_tray_check()` then resets the interval to `TRAY_CHECK_INTERVAL_MS`
  (6 hours) for every fire thereafter. Both are module constants, not user settings (YAGNI).
  Using the **one** timer for both the initial and recurring checks means the teardown's single
  `self._tray_timer.stop()` (§2) cancels any pending initial check — no stray one-shot survives
  tray-off. `--check` reads cached repo metadata (`zypper --no-refresh list-updates`), so a finer
  cadence would not surface fresher data.

**Keep the ambient icon consistent with in-window activity:** when the window's own flows learn
a fresh total, refresh the tray too, so the icon doesn't lie while the window is open:

These hooks live in `on_finished` (updater.py:1785), which already branches on
`self._check_mode` (updater.py:1797):
- **Check branch** (`_check_mode` true): `_apply_tray_total(int(self._installed_count) if
  self._installed_count.isdigit() else 0)` — mirror the `.isdigit()` guard `on_finished` itself
  uses at updater.py:1802 (`_installed_count` is a free-form string, so a bare `int(...)` can
  raise). The count came from the CHECK/TOTAL handling at updater.py:1709–1712.
- **Run branch** (`_check_mode` false) **and only when the run succeeded** (`ok`): set the tray
  neutral (updates were just installed → nothing waiting): `_apply_tray_total(0)`. On a **failed**
  run, do **not** touch the tray — its last known state stands (blanking it would falsely claim
  "up to date" after a failure).

### 6. Close-to-tray

`closeEvent` (updater.py:1074) becomes: **if** the tray is live (`self._tray is not None`),
save geometry, `event.ignore()`, `self.hide()`, and — **once per session** — fire a
close-to-tray hint ("OneUp is still running in the tray — right-click the icon to quit."),
gated by a `self._tray_hint_shown` flag. That hint is a **direct** `notify-send` — the same
fixed-argv `Popen` pattern as `_notify_when_away` (updater.py:1778–1783), keeping that method's
`shutil.which("notify-send")` presence check (updater.py:1776) but dropping its `isActiveWindow()`
half — **not** a call to `_notify_when_away` itself, whose active-window guard (updater.py:1776)
would suppress it, since the window is still the active window at close time. (A missing
`notify-send` is doubly safe: skipped by the `which` check and, failing that, swallowed by the
pattern's `except OSError`.) **Else** unchanged (save geometry +
`super().closeEvent(event)`; the app quits because a tray isn't holding it open).

### 7. `main()` wiring

- Keep `--check` / `--update` dispatch first (updater.py:2021–2024), unchanged.
- After `QApplication([])`, decide tray intent: `tray_wanted = QSettings("OneUp","OneUp")
  .value("tray_enabled", False, type=bool)` **and** `QSystemTrayIcon.isSystemTrayAvailable()`.
- If `tray_wanted`: **first run the single-instance client check** (§8) — if another resident
  copy answers, raise it and `sys.exit(0)`. Otherwise build the window and call
  `win._ensure_tray()`, which owns the quit-behaviour, the single-instance server, and the
  initial + periodic check (§4) — main() does **not** set `setQuitOnLastWindowClosed` or start
  the timer separately. Then `show()` the window **only if `--tray` is not present** (autostart
  starts hidden; a normal launch still shows it).
- Else (no tray wanted/available): today's path — `win.show()`; if `--tray` was passed but no
  tray is available, still `show()` the window (degrade, never a silent no-op).

### 8. Single-instance guard (resident-app correctness)

A resident tray copy means a second launch (app-menu click) must **raise the existing copy**,
not spawn a second icon + second check timer. Minimal `QLocalServer`/`QLocalSocket` guard, split
across the two natural owners:

- **Server name** is per-user to avoid cross-user collisions: `f"OneUp-{os.getuid()}"`.
- **Client check — in `main()`, for any tray-wanted launch (before building the window):**
  `QLocalSocket().connectToServer(name)`; if it connects within a short timeout, a resident copy
  already exists — write a one-byte token and `sys.exit(0)`. The resident instance, on
  `newConnection`, calls `win._show_window()`.
- **Server — armed by `_ensure_tray()` (§4, step 3), not by main():**
  `QLocalServer.removeServer(name)` (clears a stale socket left by a crash), then `listen(name)`;
  connect `newConnection` to raise the window. Arming it inside `_ensure_tray()` — the **single**
  point where OneUp becomes resident — means it covers **both** an autostart/normal-enabled launch
  **and** a mid-session Settings enable; there is no resident state without a live server (this
  closes the "Settings-enabled tray has no server, so a second launch duplicates" gap).
- Guard touches **only resident sessions** — a plain `oneup` with the tray off never calls
  `_ensure_tray()`, so it starts no server and keeps today's multi-window behaviour. (A headless
  `--check`/`--update` never reaches this code.)
- **Accepted races:** (a) two near-simultaneous cold launches can both fail `connectToServer`
  then both `listen()`; last writer wins, the loser keeps its own icon. (b) two processes each
  started tray-off that both enable the tray mid-session will each try to `listen()` on the same
  name; the second fails and simply keeps its own icon. Both are rare double-launch corners,
  harmless at this scale, not worth a lock file.
- **Server lifetime:** the server is closed in the `on_tray_toggled(on=False)` teardown (§2) and
  otherwise dies with the process on quit — no single-instance lock outlives residency.

## Correctness invariants

- **No engine/marker change.** No `@@…@@` marker is added, renamed, or re-laid-out; the
  marker contract in `CLAUDE.md`, the engine, and `tests/run-tests.sh` are untouched. The tray
  reads only the existing `@@CHECK@@|TOTAL|<n>|updates available` line.
- **Tray is opt-in and reversible.** With `tray_enabled` false (default), `main()` and
  `closeEvent` behave exactly as today. Turning the tray off tears down the icon, stops the
  periodic check timer, restores quit-on-close, and removes any autostart entry.
- **Never invisible + unquittable *by user action*.** Turning the tray off while the window is
  hidden re-shows the window. In tray mode the menu's **Quit** is always present. Graceful
  degradation shows the window when no tray exists. The one case outside user control — the
  desktop's own tray host (panel) crashing while the window is hidden — is bounded, not
  guaranteed away: relaunching `oneup` re-shows the window via the single-instance guard (§8),
  and Qt re-attaches the icon when a new tray host appears. See the matching failure-mode row.
- **The tray check never mutates the window's interactive state.** It runs on its own QProcess
  and its parser touches only the tray icon/tooltip (the `_on_size_output` pattern), so an
  ambient check can't clobber a run in progress or the task-row badges.
- **The ambient icon does not double-notify.** The tray check is silent; only the independently
  toggled weekly-check timer fires a popup.
- **Desktop Entry `Exec` is correctly escaped** (`%%` for `%`, `$` left literal, quoted paths)
  — distinct from the systemd escaping, so a `$`/`%`/space in the install path can't corrupt
  the autostart line.

## Failure modes

| Situation | Behaviour |
|-----------|-----------|
| No system tray on this desktop | `isSystemTrayAvailable()` false → both new toggles disabled with a note; no tray built; `--tray`/`tray_enabled` degrade to a normal shown window. |
| `_install_autostart` raises `OSError` (can't write `~/.config/autostart`) | Caught, `QMessageBox.warning`, `startboot_btn` reverted to off (never shows on after a failed write) — mirrors the `_install_user_timer` OSError catch/warn at updater.py:1194–1196 (the button revert is added by this handler). |
| `ENGINE` missing when a tray check fires | `_tray_check()` early-returns (like `request_size` at updater.py:1515); icon stays at its last known state; tooltip unchanged. |
| `--check` exits non-zero / emits no `TOTAL` | No `_apply_tray_total` call → icon unchanged (last known / neutral). No crash: the parser only acts on a well-formed `TOTAL` line. |
| Second `oneup` launched while resident | Single-instance guard raises the existing window and the second process exits 0 — no duplicate tray icon. |
| Tray turned off mid-session with window hidden | Window is re-shown; quit-on-last-window-closed restored; autostart removed. |
| Tray host (panel) crashes while the window is hidden | App is briefly invisible with no menu (outside user control). Recovery: relaunch `oneup` — the single-instance guard (§8) re-shows the window; Qt also re-attaches the icon when a new tray host registers. Bounds the "never invisible" invariant. |
| `_app_icon()` returns a null icon (bare checkout, no theme) | `_tray_icon()` falls back to a drawn disc so the tray is never blank. |

## Tests (`tests/gui-smoke.py`)

CI runs headless (offscreen), where `isSystemTrayAvailable()` is typically false and no real
tray exists. Tests therefore target the **pure/file helpers and coupling**, stubbing the tray
build (the existing suite already monkeypatches `_install_user_timer` etc.):

- **Autostart file, install/remove:** with `HOME` pointed at the sandbox, `_install_autostart()`
  writes `…/autostart/za.co.antsprojectshub.OneUp-tray.desktop` containing `--tray`;
  `_startboot_enabled()` is then true; `_remove_autostart()` deletes it and the flag goes false.
- **Desktop-Entry Exec escaping:** `_autostart_exec()` on a path containing `%` and `$` yields
  `%%` for `%` and the `$` written as **`\\$`** (the freedesktop-unambiguous form) — assert
  exactly `\\$`, **not** a bare `$`, **not** single-backslash `\$`, and **not** the systemd
  doubled `$$` — with the path double-quoted (per the §3 worked example `"/opt/o\\$ne%%up/oneup"`).
  This is the regression that locks the "not the systemd escaping" rule; any looser assertion
  would rubber-stamp a wrong implementation.
- **Settings dialog hosts both new toggles:** `tray_btn` and `startboot_btn` are in the
  `SettingsDialog`'s laid-out buttons; both default off.
- **Coupling — enable boot turns tray on:** stub `_install_autostart` to succeed; toggling
  `startboot_btn` on sets `tray_btn` on and persists `tray_enabled`.
- **Coupling — tray off removes boot:** with `startboot_btn` on, toggling `tray_btn` off calls
  `_remove_autostart` and reflects `startboot_btn` off (no re-fire).
- **Tray total → attention state:** feeding `_on_traycheck_output` the **real three-field** line
  `@@CHECK@@|TOTAL|3|updates available\n` sets `self._tray_total == 3` (attention);
  `@@CHECK@@|TOTAL|0|updates available` sets it 0 (neutral) — proving the parser reads field 1
  and tolerates the trailing label (a two-field fixture would hide the crash the real line
  causes). (Assert the state var, not the icon pixels.)
- **Tray check is silent (no double-notify):** `_tray_check()` launches the engine with `--check`
  and **without** `--notify` (inspect the started argv) — pins the "ambient icon does not
  double-notify" invariant, the one promised behaviour that otherwise has no test.
- **`OSError` on install reverts boot only:** stub `_install_autostart` to raise `OSError`;
  toggling `startboot_btn` on leaves `startboot_btn` off but leaves the tray on (the valid
  "resident, not at boot" state).
- **Coupling — boot-off keeps tray on:** with both on, toggling `startboot_btn` off calls
  `_remove_autostart` and leaves `tray_btn` **on** (the reverse-direction coupling: boot off
  does not turn the tray off).
- **Close-to-tray:** with a tray live (stubbed), `closeEvent` ignores the event and hides the
  window (rather than quitting), and sets `self._tray_hint_shown` so a second close fires no
  second hint.
- Existing weekly-check / passwordless / auto-update assertions stay green (their handlers are
  unchanged).

**On-box acceptance (manual, not CI):** on the real desktop, enable **Start at boot**, log out
and back in → OneUp is absent from the taskbar but its tray icon is present; with updates
pending the icon is amber and its tooltip names the count; right-click **Update now** opens the
window and runs; **Quit** removes the icon; disabling the toggle stops it launching next login.

## Docs & release

- `CHANGELOG.md` `[Unreleased] / Added`: a plain-English bullet — an optional system-tray icon
  that turns amber when updates are waiting, with a right-click Check/Update/Open/Quit menu and
  an optional "start at boot"; off by default; degrades cleanly where there's no tray.
- `README.md`: a feature bullet under "What it does".
- `ROADMAP.md`: flip ONEUP-0018 to shipped with a resolution note once landed. The bullet's
  original gloss ("reflect the **weekly background check** result"; menu item "dismiss") is
  superseded by this spec's decisions — the tray runs its **own** independent `--check`, and the
  menu is Check now / Update now / Open OneUp / **Quit** — so say so in the resolution note.
- The AppStream `<release>` notes mirror the CHANGELOG on the next release (via `./bump.py`).
- No version bump in this change — versioning is a separate release step.

## Alternatives considered (and rejected)

- **Couple the tray to the weekly-check timer's result** (have the engine's `--check` persist a
  `check-status.json` the tray reads). Rejected: it forces an **engine change** and a new
  on-disk contract, for no user-visible gain over the tray running its own cheap read-only
  check. Independence keeps the blast radius inside `updater.py`.
- **Tray only while the window is open** (no residency). Rejected by the user — it doesn't
  deliver the ambient "instead of the popup" value.
- **Ship a second amber SVG asset.** Rejected: drawing an amber badge at runtime avoids a new
  packaged file and works regardless of the base icon's colours/theme.
- **Fire a notification when the tray first sees updates.** Rejected (YAGNI + intent): the icon
  *is* the ambient signal; adding a popup re-introduces the thing the tray replaces.

## Out of scope

- Configurable check cadence / a time-of-day picker (fixed 6-hourly constant).
- A tray-menu snapshot/rollback submenu (that lives in the window; ONEUP-0020 covers snapshot
  selection separately).
- Any change to the engine, its steps, its markers, or its output.
- Per-step tray detail (the tray shows a single aggregate "N waiting"; the window shows the
  per-task breakdown).
