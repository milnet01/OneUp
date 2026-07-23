# ONEUP-0022 — Unattended (scheduled) updates — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an off-by-default weekly "install everything automatically" schedule that runs the whole update engine headless, backed by the ONEUP-0023 passwordless rule and the existing snapshot/rollback safety net.

**Architecture:** Two additive engine changes (skip the interactive `sudo -v` bootstrap when the passwordless drop-in is active; fire an end-of-run desktop notification on a full run) plus GUI plumbing that reuses the existing weekly-check timer machinery for a new `oneup-update` timer, all fronted by a new **Settings** popup that groups the three background-behaviour toggles. No new engine markers, no new step keys.

**Tech Stack:** Bash (`update_system.sh` engine), Python 3 + PySide6/Qt 6 (`updater.py` GUI), systemd-user timers, bash mock-PATH test harness (`tests/run-tests.sh`), offscreen-Qt smoke test (`tests/gui-smoke.py`).

## Global Constraints

- **Design spec is the contract:** `docs/specs/ONEUP-0022-unattended-updates.md` — every task traces to it.
- **Privileged engine calls** go through `SUDO_ASKPASS="$ASKPASS"` (`ASKPASS=/usr/libexec/ssh/ksshaskpass`), `sudo -A` — never bare `sudo`. New privileged calls match this.
- **No new markers / step keys.** The `@@MARKER@@` contract in `CLAUDE.md` stays byte-identical.
- **`--update` is GUI-only.** It is consumed by `updater.py`'s `main()` and **never** passed to the engine (the engine's arg parser rejects unknown flags with `exit 2` at `update_system.sh:79`).
- **Off by default.** Auto-update starts off; the auto-update timer is never enabled while passwordless is off.
- **A failed step never claims success or forces a reboot** — unchanged engine invariant; the timer runs the same engine path as a manual run.
- **Layman's-language user-facing copy** (dialogs, notifications, changelog).
- **`./local-CI.sh` must be green before any push** (it runs both test suites + lint + validation + version-lockstep).
- **Commit locally per task; do not push** until the whole feature is landed and the user approves the batch (public repo, but batching to avoid mid-feature CI runs).

---

## File Structure

- `update_system.sh` — engine. Modify `sudo_init` (skip when drop-in active); add end-of-run notify near the run summary.
- `updater.py` — GUI. Add `SettingsDialog`; restructure the header; generalise the timer/command helpers; add the auto-update toggle, coupling logic, and the `--update` headless entrypoint.
- `tests/run-tests.sh` — engine tests. Add two scenarios (end-of-run notify; bootstrap-skip regression).
- `tests/gui-smoke.py` — GUI smoke. Add Settings/auto-update assertions (dialog hosts three toggles; command builder; coupling stubs).
- `CHANGELOG.md`, `README.md`, `ROADMAP.md` — docs.

---

## Task 1: Engine — skip the interactive bootstrap when passwordless is active

**Files:**
- Modify: `update_system.sh:285-303` (`sudo_init`)
- Test: `tests/run-tests.sh` (new scenario)

**Interfaces:**
- Consumes: the scoped non-interactive probe pattern the engine already uses at `update_system.sh:416` (`sudo -k -n "$zypper" --version`).
- Produces: a `sudo_init` that returns early (no interactive `-v`, no keep-alive) when the drop-in is active; unchanged otherwise.

- [ ] **Step 1: Write the failing test** — append to `tests/run-tests.sh` (after the `--auth-status` scenario, ~line 328):

```bash
# ---------------------------------------------------------------------------
echo "TEST: with the passwordless drop-in active, a full run skips the interactive sudo -v"
d=$(mktemp -d); setup_common "$d"
cat > "$d/zypper" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "--version" ]] && { echo v; exit 0; }
case "$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "Nothing to do."; exit 0 ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$d/zypper"
# Drop-in ACTIVE: the scoped `-n` probe succeeds, so the engine must NOT reach the
# interactive `sudo -A … -v`. The mock aborts loudly (exit 99) if `-A` is ever passed.
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
for a in "$@"; do [[ "$a" == "-A" ]] && { echo "BUG: interactive sudo -A invoked" >&2; exit 99; }; done
while [[ $# -gt 0 ]]; do case "$1" in -n|-v|-k|-E) shift;; -p) shift 2;; --) shift; break;; -*) shift;; *) break;; esac; done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
chmod +x "$d/sudo"
out=$(run_engine "$d" --steps=system,cache)
check_absent "drop-in active: no interactive sudo -A -v" "BUG: interactive sudo -A invoked" "$out"

# Drop-in ABSENT: the scoped `-n` probe fails, so the engine still performs the ONE
# interactive validate exactly as today (marker printed by the mock when `-A` is seen).
cat > "$d/sudo" <<'EOF'
#!/usr/bin/env bash
nonint=false; interactive=false
for a in "$@"; do [[ "$a" == "-n" ]] && nonint=true; [[ "$a" == "-A" ]] && interactive=true; done
$nonint && exit 1                         # scoped probe fails -> drop-in absent
$interactive && echo "INTERACTIVE_VALIDATE_RAN"
while [[ $# -gt 0 ]]; do case "$1" in -n|-v|-k|-E) shift;; -p) shift 2;; --) shift; break;; -*) shift;; *) break;; esac; done
[[ $# -eq 0 ]] && exit 0
exec "$@"
EOF
chmod +x "$d/sudo"
out=$(run_engine "$d" --steps=system,cache)
check "drop-in absent: still performs the interactive validate" "INTERACTIVE_VALIDATE_RAN" "$out"
rm -rf "$d"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash tests/run-tests.sh 2>&1 | grep -A1 "skips the interactive"`
Expected: `FAIL - drop-in active: no interactive sudo -A -v` (today `sudo_init` always runs `sudo -A … -v`, so the mock's `exit 99` fires and the BUG line appears).

- [ ] **Step 3: Write the minimal implementation** — edit `sudo_init` at `update_system.sh:285`, inserting the guard as the first lines of the function body:

```bash
sudo_init() {
    # If the ONEUP-0023 passwordless drop-in is active, every privileged command
    # below is individually NOPASSWD, so no cached credential is needed — and the
    # interactive `sudo -A … -v` here would prompt ANYWAY: sudo's `verifypw` defaults
    # to `all`, so a bare `-v` validate is only password-free when EVERY one of the
    # user's sudoers entries is NOPASSWD (a normal %wheel user's isn't). Skipping it
    # is what lets a headless timer run authenticate. Same non-interactive scoped
    # probe --auth-status uses (auth_status, ~line 416).
    local _zypper
    if _zypper=$(command -v zypper) && sudo -k -n "$_zypper" --version >/dev/null 2>&1; then
        return 0
    fi
    if ! SUDO_ASKPASS="$ASKPASS" sudo -A \
            -p "System Updater: authenticate to update the system" -v; then
        echo "Authentication failed or cancelled — aborting." >&2
        exit 1
    fi
    # ... (existing keep-alive loop unchanged) ...
```

Leave the rest of `sudo_init` (the `setsid` keep-alive at lines 300-302) exactly as-is.

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash tests/run-tests.sh 2>&1 | grep -E "interactive validate|no interactive sudo"`
Expected: both `ok   - drop-in active: no interactive sudo -A -v` and `ok   - drop-in absent: still performs the interactive validate`.

- [ ] **Step 5: Run the full engine suite (nothing else regressed)**

Run: `bash tests/run-tests.sh; echo "exit=$?"`
Expected: `exit=0`, no `FAIL` lines. (The existing manual-run scenarios use `setup_common`'s sudo mock whose `-n` probe path returns success only for real commands — verify the up-to-date/reboot scenarios still pass; if `setup_common`'s sudo makes the new probe succeed spuriously and changes an existing assertion, that is a signal, not a workaround — investigate before proceeding.)

- [ ] **Step 6: Commit**

```bash
git add update_system.sh tests/run-tests.sh
git commit -m "ONEUP-0022: skip interactive sudo bootstrap when passwordless drop-in is active"
```

---

## Task 2: Engine — end-of-run desktop notification on a full run

**Files:**
- Modify: `update_system.sh` (end-of-run summary block, ~line 765, before `echo "  Log saved: $LOG_FILE"`)
- Test: `tests/run-tests.sh` (new scenario)

**Interfaces:**
- Consumes: `notify_send` helper (`update_system.sh:115-117`), and the summary variables already computed by this point — `ERRORS` (defined line 150), `SYS_COUNT` (line 152), `SYS_CHANGED` (line 151), `FW_CHANGED` (line 153), `LOG_FILE`.
- Produces: exactly one `notify-send` call at the end of a full run when `--notify` is set. `--check`/`--size`/auth actions exit earlier (`update_system.sh:277`, `:436`, `:429`), so this code path is full-run-only and cannot double-fire with the existing check-mode notify at line 229.

- [ ] **Step 1: Write the failing test** — append to `tests/run-tests.sh`:

```bash
# ---------------------------------------------------------------------------
echo "TEST: a full run fires an end-of-run desktop notification with the outcome"
_notify_case() {  # zypper-dup-output, expected-title, extra-step-mock(optional)
    local dup_out="$1" want="$2"
    local d; d=$(mktemp -d); setup_common "$d"
    cat > "$d/zypper" <<EOF
#!/usr/bin/env bash
[[ "\$1" == "--version" ]] && { echo v; exit 0; }
case "\$*" in
  *refresh*)         exit 0 ;;
  *dup*|*update*)    echo "$dup_out"; exit ${3:-0} ;;
  *needs-rebooting*) exit 0 ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$d/zypper"
    cat > "$d/notify-send" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$d/notify.log"
EOF
    chmod +x "$d/notify-send"
    run_engine "$d" --steps=system,cache --notify >/dev/null 2>&1
    check "full run notifies: $want" "$want" "$(cat "$d/notify.log" 2>/dev/null)"
    rm -rf "$d"
}
_notify_case "3 packages to upgrade." "Update complete"
_notify_case "Nothing to do."         "Already up to date"
_notify_case "boom"                   "Update failed" 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash tests/run-tests.sh 2>&1 | grep "full run notifies"`
Expected: three `FAIL` lines (today a full run never calls `notify_send`).

- [ ] **Step 3: Write the minimal implementation** — in `update_system.sh`, insert this block after the reboot/services advice (after line 765, immediately before `echo "  Log saved: $LOG_FILE"`):

```bash
# End-of-run desktop notification (full runs only; --check has its own at line ~229).
# Fires for the unattended weekly timer so a 2am run still reports its outcome.
if $NOTIFY; then
    if ((ERRORS > 0)); then
        notify_send "Update failed" "One or more steps failed — see the log: $LOG_FILE"
    elif [[ -n "$SYS_COUNT" && "$SYS_COUNT" != "0" ]]; then
        notify_send "Update complete" "$SYS_COUNT system package(s) installed."
    elif $SYS_CHANGED || $FW_CHANGED; then
        notify_send "Update complete" "Updates were installed."
    else
        notify_send "Already up to date" "No updates were needed."
    fi
fi
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash tests/run-tests.sh 2>&1 | grep "full run notifies"`
Expected: three `ok` lines (`Update complete`, `Already up to date`, `Update failed`).

- [ ] **Step 5: Confirm check-mode notify is untouched**

Run: `bash tests/run-tests.sh; echo "exit=$?"`
Expected: `exit=0`; the existing `--check --notify` assertions stay green (no double notification).

- [ ] **Step 6: Commit**

```bash
git add update_system.sh tests/run-tests.sh
git commit -m "ONEUP-0022: notify with the outcome at the end of a full run"
```

---

## Task 3: GUI — shared timer/command helpers + the `--update` headless entrypoint

**Files:**
- Modify: `updater.py:1017-1080` (rename/extract the weekly-check helpers), `updater.py:1042-1045` (`_autocheck_enabled`), `updater.py:1715-1726` (`_headless_check` + `main`)
- Test: `tests/gui-smoke.py` (command-builder assertions)

**Interfaces:**
- Produces (relied on by Tasks 4 & 5):
  - `Updater._headless_command(flag: str) -> str` — quoted `ExecStart` string for `--check` or `--update`.
  - `Updater._install_user_timer(basename: str, description: str, exec_flag: str) -> bool` — writes+enables a weekly timer; returns `True` iff `systemctl --user is-enabled <basename>.timer` reports `enabled`.
  - `Updater._remove_user_timer(basename: str) -> None` — disables+deletes the unit pair.
  - `Updater._timer_enabled(timer: str) -> bool` — `is-enabled` probe.
  - `_headless_update() -> int` (module-level) and `main()` dispatch of `--update`.

- [ ] **Step 1: Write the failing test** — in `tests/gui-smoke.py`, add after the `--check` section (after line 193, before the About section):

```python
    # --- headless command builder shared by both timers ------------------------
    check("headless --check command ends in --check",
          updater.Updater._headless_command("--check").endswith("--check"))
    check("headless --update command ends in --update",
          updater.Updater._headless_command("--update").endswith("--update"))
    check("headless command quotes the executable path",
          updater.Updater._headless_command("--check").startswith('"'))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 tests/gui-smoke.py 2>&1 | grep -i "headless"`
Expected: `FAIL`/traceback — `_headless_command` does not exist yet (only `_autocheck_command`).

- [ ] **Step 3: Write the minimal implementation.**

**3a.** Replace `_autocheck_command` (`updater.py:1021-1040`) with the generalised builder:

```python
    @staticmethod
    def _headless_command(flag: str) -> str:
        """A stable command that re-launches OneUp headless with `flag`
        (`--check` or `--update`). Each path is quoted (for spaces) and any '%',
        '$', '"' or backslash is escaped: systemd does C-unescaping plus env-var
        and specifier expansion inside double quotes, so an unescaped one in an
        install path would silently corrupt the unit."""
        def _arg(p) -> str:
            s = str(p).replace("\\", "\\\\").replace('"', '\\"')
            s = s.replace("$", "$$").replace("%", "%%")
            return '"' + s + '"'
        appimage = os.environ.get("APPIMAGE")
        if appimage:
            return f"{_arg(appimage)} {flag}"
        launcher = shutil.which("oneup")
        if launcher:
            return f"{_arg(launcher)} {flag}"
        return f"{_arg(sys.executable)} {_arg(Path(__file__).resolve())} {flag}"
```

**3b.** Extract the install/remove/probe helpers. Replace `_autocheck_enabled` (`updater.py:1042-1045`) and `on_autocheck_toggled` (`updater.py:1051-1080`) with:

```python
    def _timer_enabled(self, timer: str) -> bool:
        r = subprocess.run(["systemctl", "--user", "is-enabled", timer],
                           capture_output=True, text=True)
        return r.stdout.strip() == "enabled"

    def _autocheck_enabled(self) -> bool:
        return self._timer_enabled("oneup-check.timer")

    def _autoupdate_enabled(self) -> bool:
        return self._timer_enabled("oneup-update.timer")

    def _install_user_timer(self, basename: str, description: str, exec_flag: str) -> bool:
        """Write + enable a weekly systemd-user timer. Returns True iff it ends up
        enabled (an OSError writing the unit, or a failed enable, returns False)."""
        units = self._user_units_dir()
        try:
            units.mkdir(parents=True, exist_ok=True)
            (units / f"{basename}.service").write_text(
                f"[Unit]\nDescription={description}\n\n"
                f"[Service]\nType=oneshot\n"
                f"ExecStart={self._headless_command(exec_flag)}\n"
            )
            (units / f"{basename}.timer").write_text(
                f"[Unit]\nDescription={description}\n\n"
                "[Timer]\nOnCalendar=weekly\nPersistent=true\n\n"
                "[Install]\nWantedBy=timers.target\n"
            )
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            subprocess.run(["systemctl", "--user", "enable", "--now",
                            f"{basename}.timer"], check=False)
        except OSError as exc:
            QMessageBox.warning(self, "Could not change the schedule", str(exc))
            return False
        return self._timer_enabled(f"{basename}.timer")

    def _remove_user_timer(self, basename: str):
        units = self._user_units_dir()
        subprocess.run(["systemctl", "--user", "disable", "--now",
                        f"{basename}.timer"], check=False)
        for name in (f"{basename}.timer", f"{basename}.service"):
            try:
                (units / name).unlink()
            except OSError:
                pass
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)

    def on_autocheck_toggled(self, on: bool):
        # Weekly-check behaviour is unchanged: install/remove and refresh the label.
        # It deliberately does NOT revert its toggle on a failed install (see the
        # ONEUP-0022 spec's "Open questions" — hardening weekly-check is a separate item).
        if on:
            self._install_user_timer("oneup-check", "OneUp weekly update check", "--check")
        else:
            self._remove_user_timer("oneup-check")
        self._refresh_autocheck_label()
```

**3c.** Add the `--update` headless entrypoint. Replace the `main()` head (`updater.py:1724-1726`) and add `_headless_update` next to `_headless_check` (`updater.py:1715`):

```python
def _headless_update() -> int:
    """`oneup --update`: run the FULL engine + its end-of-run notification, no GUI.
    This is what the optional weekly systemd-user UPDATE timer invokes. `--update`
    is a GUI-only token — the engine is run with just --notify (its default STEPS is
    every step) and is NEVER handed --update (its arg parser would reject it)."""
    if not ENGINE.exists():
        print(f"OneUp: update script not found at {ENGINE}", file=sys.stderr)
        return 1
    return subprocess.run(["bash", str(ENGINE), "--notify"]).returncode


def main():
    if "--check" in sys.argv[1:]:
        sys.exit(_headless_check())
    if "--update" in sys.argv[1:]:
        sys.exit(_headless_update())
    # ... existing GUI startup unchanged ...
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/gui-smoke.py 2>&1 | grep -iE "headless|Passed|Failed"`
Expected: three `ok` headless lines; `Failed: 0`. (Existing weekly-check-timer behaviour is exercised only indirectly here — its unchanged handlers keep the suite green.)

- [ ] **Step 5: Commit**

```bash
git add updater.py tests/gui-smoke.py
git commit -m "ONEUP-0022: extract shared user-timer helpers + add --update headless entrypoint"
```

---

## Task 4: GUI — the Settings popup + header restructure

**Files:**
- Modify: `updater.py:718-811` (`Updater.__init__`: min-width, the three toggle buttons, header row), add `SettingsDialog` class near `RepoManagerDialog` (`updater.py:552`), add `open_settings` near `open_repos` (`updater.py:1187`)
- Test: `tests/gui-smoke.py` (Settings/dialog assertions)

**Interfaces:**
- Consumes: `Updater.auto_btn`, `Updater.auth_btn` (existing), `Updater.autoupdate_btn` (new, added here).
- Produces (relied on by Task 5 & tests): `Updater.settings_btn`, `Updater._settings_dialog` (created lazily, `None` until first open), `Updater.open_settings()`, `SettingsDialog(parent)`, `Updater._settings_status(text)`, `Updater._set_autoupdate_checked(on)`, `Updater._refresh_autoupdate_label()`.

- [ ] **Step 1: Write the failing test** — in `tests/gui-smoke.py`, add after the headless-command section:

```python
    # --- Settings popup groups the three background toggles --------------------
    w = updater.Updater()
    check("Settings button exists in the header", hasattr(w, "settings_btn"))
    check("auto-update toggle defaults to off",
          hasattr(w, "autoupdate_btn") and not w.autoupdate_btn.isChecked()
          and w.autoupdate_btn.text() == "Automatic updates: off")
    dlg = updater.SettingsDialog(w)
    hosted = dlg.findChildren(QPushButton)
    check("Settings dialog hosts the weekly-check toggle", w.auto_btn in hosted)
    check("Settings dialog hosts the passwordless toggle", w.auth_btn in hosted)
    check("Settings dialog hosts the auto-update toggle", w.autoupdate_btn in hosted)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 tests/gui-smoke.py 2>&1 | grep -iE "Settings|auto-update"`
Expected: `FAIL`/traceback — `settings_btn`, `autoupdate_btn`, `SettingsDialog` don't exist yet.

- [ ] **Step 3: Write the minimal implementation.**

**3a.** Add the `SettingsDialog` class (place immediately before or after `RepoManagerDialog`, `updater.py:552`):

```python
class SettingsDialog(QDialog):
    """Groups OneUp's three background-behaviour toggles (weekly check,
    passwordless, automatic updates) behind one popup, modelled on
    RepoManagerDialog. The toggle buttons and their handlers stay owned by the
    Updater window; this dialog only lays them out. It is created once, so the
    buttons live here permanently after the first open."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        intro = QLabel("Background behaviours. Each is off until you turn it on.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        root.addWidget(self._row(
            "Check weekly in the background and notify you when updates are ready.",
            parent.auto_btn))
        root.addWidget(self._row(
            "Skip the password prompt for OneUp's update commands (opt-in; you can "
            "switch it off to revoke instantly).", parent.auth_btn))
        root.addWidget(self._row(
            "Install all updates automatically on a weekly schedule. Needs the "
            "passwordless setting, and keeps the snapshot/rollback safety net.",
            parent.autoupdate_btn))
        self.status = QLabel("")
        self.status.setObjectName("Tagline")
        root.addWidget(self.status)
        btns = QHBoxLayout()
        btns.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("GhostBtn")
        close_btn.clicked.connect(self.reject)
        btns.addWidget(close_btn)
        root.addLayout(btns)

    def _row(self, description: str, button: QPushButton) -> QFrame:
        fr = QFrame()
        fr.setObjectName("RowBorder")
        lay = QHBoxLayout(fr)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)
        lbl = QLabel(description)
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)
        lay.addWidget(button, 0, Qt.AlignVCenter)
        return fr

    def showEvent(self, event):
        # Centre over the main window each time it opens (mirrors RepoManagerDialog).
        super().showEvent(event)
        parent = self.parent()
        if parent:
            fg = self.frameGeometry()
            fg.moveCenter(parent.frameGeometry().center())
            self.move(fg.topLeft())
```

**3b.** In `Updater.__init__`, change the min-width (`updater.py:722-724`):

```python
        # Four header controls (Settings · Repositories · Recenter · About); the
        # three background toggles now live inside the Settings popup.
        self.setMinimumWidth(560)
```

**3c.** Initialise the dialog handle and the new toggle. Add near the other init state (after `updater.py:739`):

```python
        self._settings_dialog: SettingsDialog | None = None
        self._pending_autoupdate = False   # one-shot latch: an enable awaiting a fresh auth settle
```

Add the auto-update button next to `auth_btn` (after `updater.py:784`):

```python
        # Automatic weekly updates (ONEUP-0022). Off by default; enabling it needs
        # the passwordless rule (coupling enforced in on_autoupdate_toggled). Real
        # state is read from the systemd-user timer.
        self.autoupdate_btn = QPushButton()
        self.autoupdate_btn.setObjectName("GhostBtn")
        self.autoupdate_btn.setCheckable(True)
        self.autoupdate_btn.setCursor(Qt.PointingHandCursor)
        self.autoupdate_btn.setToolTip("Install all updates automatically every week "
                                       "(needs Passwordless)")
        self.autoupdate_btn.setChecked(self._autoupdate_enabled())
        self._refresh_autoupdate_label()
        self.autoupdate_btn.toggled.connect(self.on_autoupdate_toggled)
```

Add the Settings header button (replacing the `auto_btn`/`auth_btn` header slots). Change the header block (`updater.py:786-811`) so the two toggle buttons are **not** added to `header_row`, and add `settings_btn` first:

```python
        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.setObjectName("GhostBtn")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setToolTip("Background behaviours: weekly check, "
                                     "passwordless, automatic updates")
        self.settings_btn.clicked.connect(self.open_settings)

        # ... recenter_btn, repos_btn, about_btn unchanged ...

        header_row = QHBoxLayout()
        header_row.addLayout(titleblock, 1)
        header_row.addWidget(self.settings_btn, 0, Qt.AlignTop)
        header_row.addWidget(self.repos_btn, 0, Qt.AlignTop)
        header_row.addWidget(self.recenter_btn, 0, Qt.AlignTop)
        header_row.addWidget(self.about_btn, 0, Qt.AlignTop)
        root.addLayout(header_row)
```

(The `auto_btn` and `auth_btn` objects are still constructed exactly as before — they are simply no longer added to `header_row`; `SettingsDialog` reparents them into itself on first open.)

**3d.** Add `open_settings`, `_settings_status`, and the auto-update label/reflect helpers. Place `open_settings` near `open_repos` (`updater.py:1187`):

```python
    def open_settings(self):
        """Open (or re-raise) the Settings popup — created once so the three
        toggle buttons live in it permanently."""
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _settings_status(self, text: str):
        if self._settings_dialog is not None:
            self._settings_dialog.status.setText(text)
```

Place the auto-update label helpers next to `_refresh_autocheck_label` (`updater.py:1047`):

```python
    def _refresh_autoupdate_label(self):
        on = self.autoupdate_btn.isChecked()
        self.autoupdate_btn.setText(
            "Automatic updates: on" if on else "Automatic updates: off")

    def _set_autoupdate_checked(self, on: bool):
        """Reflect the real state on the toggle WITHOUT re-firing on_autoupdate_toggled."""
        self.autoupdate_btn.blockSignals(True)
        self.autoupdate_btn.setChecked(on)
        self.autoupdate_btn.blockSignals(False)
        self._refresh_autoupdate_label()
```

**3e.** Add a placeholder `on_autoupdate_toggled` so the button's `toggled` connection resolves (the real coupling body lands in Task 5):

```python
    def on_autoupdate_toggled(self, on: bool):
        # Real coupling logic added in Task 5. Placeholder keeps the signal valid.
        self._set_autoupdate_checked(on)
```

Confirm `QDialog` is imported at the top of `updater.py` (it is used by `RepoManagerDialog`). No new imports needed.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/gui-smoke.py 2>&1 | grep -iE "Settings|auto-update|Passed|Failed"`
Expected: all Settings/auto-update lines `ok`; `Failed: 0`. Existing passwordless-toggle assertions (they reference `w.auth_btn`) stay green — the button object is unchanged, only its parent layout moved.

- [ ] **Step 5: Commit**

```bash
git add updater.py tests/gui-smoke.py
git commit -m "ONEUP-0022: group the three background toggles behind a Settings popup"
```

---

## Task 5: GUI — the passwordless↔auto-update coupling

**Files:**
- Modify: `updater.py` — replace the Task-4 placeholder `on_autoupdate_toggled`; factor the passwordless warning out of `on_auth_toggled` (`updater.py:1116-1142`) into `_confirm_passwordless`; add the install gate to `_on_auth_status_finished` (`updater.py:1112-1114`); hook the revoke coupling into `on_auth_toggled`'s `on=False` branch; route `_run_auth` status to the dialog.
- Test: `tests/gui-smoke.py` (coupling stubs)

**Interfaces:**
- Consumes: `_pending_autoupdate` latch (init in Task 4), `_install_user_timer`/`_remove_user_timer`/`_autoupdate_enabled`/`_timer_enabled` (Task 3), `_set_autoupdate_checked` (Task 4), `_query_auth_status`/`_run_auth`/`_set_auth_checked` (existing).
- Produces: `Updater._confirm_passwordless(lead: str = "") -> bool`; the settle (`_on_auth_status_finished`) as the single install gate; revoke removing the update timer.

- [ ] **Step 1: Write the failing test** — in `tests/gui-smoke.py`, add after the Settings section. It stubs the process-driven bits (mirroring the existing `_StubProc` pattern) and monkeypatches the message boxes so nothing blocks:

```python
    # --- coupling: auto-update never enables without passwordless ---------------
    updater.QMessageBox.information = staticmethod(lambda *a, **k: 0)
    updater.QMessageBox.warning = staticmethod(lambda *a, **k: 0)

    # (a) enabling with passwordless OFF and cancelling the combined dialog installs nothing
    w = updater.Updater()
    installed_a = []
    w._install_user_timer = lambda *a, **k: (installed_a.append(a) or True)
    w._confirm_passwordless = lambda lead="": False          # user cancels
    w._set_auth_checked(False)                               # passwordless off
    w.on_autoupdate_toggled(True)
    check("cancel combined-enable installs no update timer", not installed_a)
    check("cancel combined-enable leaves auto-update off", not w.autoupdate_btn.isChecked())
    check("cancel combined-enable clears the pending latch", w._pending_autoupdate is False)

    # (b) a settle reporting passwordless OFF while a latch is pending must NOT install
    w = updater.Updater()
    installed_b = []
    w._install_user_timer = lambda *a, **k: (installed_b.append(a) or True)
    w._pending_autoupdate = True
    w._on_auth_status_finished(_StubProc("@@AUTH@@|off\n"))
    check("settle passwordless-off does not install the update timer (stale-switch guard)",
          not installed_b)
    check("settle passwordless-off consumes the latch", w._pending_autoupdate is False)

    # (c) a settle reporting passwordless ON with a pending latch installs + turns on
    w = updater.Updater()
    installed_c = []
    w._install_user_timer = lambda *a, **k: (installed_c.append(a) or True)
    w._pending_autoupdate = True
    w._on_auth_status_finished(_StubProc("@@AUTH@@|on\n"))
    check("settle passwordless-on installs the update timer", bool(installed_c))
    check("settle passwordless-on turns the auto-update toggle on", w.autoupdate_btn.isChecked())

    # (d) revoking passwordless while auto-update is on clears the schedule
    w = updater.Updater()
    removed_d = []
    w._autoupdate_enabled = lambda: True
    w._remove_user_timer = lambda name: removed_d.append(name)
    w._run_auth = lambda *a, **k: None                       # don't spawn a real process
    w._set_autoupdate_checked(True)
    w.on_auth_toggled(False)                                 # user revokes
    check("revoke passwordless removes the update timer", "oneup-update" in removed_d)
    check("revoke passwordless clears the auto-update toggle", not w.autoupdate_btn.isChecked())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 tests/gui-smoke.py 2>&1 | grep -iE "combined-enable|stale-switch|settle passwordless|revoke passwordless"`
Expected: `FAIL`s — the placeholder `on_autoupdate_toggled` just mirrors the toggle; the settle has no install gate; revoke doesn't touch the update timer.

- [ ] **Step 3: Write the minimal implementation.**

**3a.** Factor the passwordless warning out of `on_auth_toggled` into `_confirm_passwordless`, and wire the revoke coupling. Replace `on_auth_toggled` (`updater.py:1116-1142`) with:

```python
    def _confirm_passwordless(self, lead: str = "") -> bool:
        """The ONEUP-0023 passwordless consent dialog. `lead` prepends a caller-
        specific sentence (e.g. auto-update's reason) before the shared caveat, so
        both call sites present the SAME security warning — never a shortened rewrite."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Skip the password prompt for updates?")
        box.setText("Let OneUp run updates without asking for your password?")
        box.setInformativeText(
            lead +
            "OneUp will add a system rule so its update commands — zypper, "
            "Flatpak, firmware and snapshots — can run without a password.\n\n"
            "Your password is never stored. The system only remembers the "
            "decision, and only for these specific commands.\n\n"
            "Because updates run as administrator, this is effectively "
            "passwordless administrator access on this machine — enable it "
            "only on a computer you trust and control. You can switch it off "
            "at any time to revoke it instantly.")
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        box.button(QMessageBox.Ok).setText("Enable")
        box.setDefaultButton(QMessageBox.Cancel)
        return box.exec() == QMessageBox.Ok

    def on_auth_toggled(self, on: bool):
        if not ENGINE.exists():
            self._set_auth_checked(False)
            return
        if on:
            if not self._confirm_passwordless():
                self._set_auth_checked(False)   # user backed out
                return
            self._run_auth("--grant-auth", "Setting up… (approve the password popup)")
        else:
            # Coupling rule 3: a schedule can't outlive the passwordless rule it needs.
            # Hooked to the revoke ACTION (not the toggle signal), so the programmatic
            # blockSignals reflects can't trip it. Removal is a local systemd-user op,
            # independent of the revoke process's own outcome.
            if self._autoupdate_enabled():
                self._remove_user_timer("oneup-update")
                self._set_autoupdate_checked(False)
                QMessageBox.information(
                    self, "Automatic updates turned off",
                    "Automatic weekly updates were switched off because they need "
                    "the passwordless setting to run unattended.")
            self._pending_autoupdate = False    # a revoke mid-enable can't leave a stale latch
            self._run_auth("--revoke-auth", "Revoking authorization…")
```

**3b.** Replace the Task-4 placeholder `on_autoupdate_toggled` with the real coupling:

```python
    def on_autoupdate_toggled(self, on: bool):
        # Up-front engine guard MIRRORS on_auth_toggled: with the engine absent the
        # async chain hits _query_auth_status's early return and NO settle ever fires,
        # so we must revert-and-return BEFORE any latch/disable, or the toggle would be
        # stuck disabled forever.
        if not ENGINE.exists():
            self._set_autoupdate_checked(False)
            return
        if on:
            # The reflected passwordless switch is only used to pick the entry branch;
            # the install itself always waits for a FRESH auth settle (never trusts the
            # possibly-stale switch). Disable the toggle for the async op (closes the
            # mirror race where the user un-clicks mid-probe); re-enabled in the settle.
            self._pending_autoupdate = True
            self.autoupdate_btn.setEnabled(False)
            if self.auth_btn.isChecked():
                # Looks on — verify with a fresh probe; the settle installs iff truly on.
                self._query_auth_status()
            else:
                # Offer to enable BOTH at once, with the shared consent caveat.
                if self._confirm_passwordless(
                        lead="Automatic updates need OneUp to run without a password.\n\n"):
                    self._run_auth("--grant-auth",
                                   "Setting up… (approve the password popup)")
                    # _run_auth -> _on_auth_finished -> _query_auth_status -> settle installs.
                else:
                    self._pending_autoupdate = False
                    self.autoupdate_btn.setEnabled(True)
                    self._set_autoupdate_checked(False)
        else:
            # User turns auto-update off: remove the timer, clear any stray latch.
            self._remove_user_timer("oneup-update")
            self._pending_autoupdate = False
            self._refresh_autoupdate_label()
```

**3c.** Make the settle the single install gate. Replace `_on_auth_status_finished` (`updater.py:1112-1114`) with:

```python
    def _on_auth_status_finished(self, proc: QProcess):
        out = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        is_on = "@@AUTH@@|on" in out
        self._set_auth_checked(is_on)
        # Re-enable the auto-update toggle if a pending enable had disabled it.
        self.autoupdate_btn.setEnabled(True)
        if self._pending_autoupdate:
            self._pending_autoupdate = False        # consume unconditionally
            if is_on:
                enabled = self._install_user_timer(
                    "oneup-update", "OneUp weekly automatic update", "--update")
                self._set_autoupdate_checked(enabled)
                if not enabled:
                    QMessageBox.warning(
                        self, "Could not enable automatic updates",
                        "The weekly update timer could not be enabled.")
            else:
                # Passwordless came back off (popup cancelled / visudo rejected / failed).
                # The grant's @@HINT@@ was already surfaced in _on_auth_finished.
                self._set_autoupdate_checked(False)
```

**3d.** Route the auth-flow status to the Settings dialog. In `_run_auth` (`updater.py:1149`) add after `self.status.setText(status_text)`:

```python
        self._settings_status(status_text)
```

And in `_on_auth_finished` (`updater.py:1161`) after `self.status.setText("Ready.")`:

```python
        self._settings_status("")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tests/gui-smoke.py 2>&1 | grep -iE "combined-enable|stale-switch|settle passwordless|revoke passwordless|Passed|Failed"`
Expected: all coupling lines `ok`; `Failed: 0`. The existing passwordless assertions (which drive `_on_auth_status_finished` with no latch set) stay green — with `_pending_autoupdate` False the settle's new branch is a no-op.

- [ ] **Step 5: Full GUI smoke (nothing regressed)**

Run: `python3 tests/gui-smoke.py; echo "exit=$?"`
Expected: `exit=0`.

- [ ] **Step 6: Commit**

```bash
git add updater.py tests/gui-smoke.py
git commit -m "ONEUP-0022: couple auto-update to passwordless (enable both / revoke both)"
```

---

## Task 6: Docs — CHANGELOG, README, ROADMAP

**Files:**
- Modify: `CHANGELOG.md:9` (`[Unreleased] / Added`), `README.md:44-50` (feature bullets under "What it does"), `ROADMAP.md` (flip ONEUP-0022 to shipped)

**Interfaces:** none (docs only). No version bump — versioning is a separate release step (`./bump.py`).

- [ ] **Step 1: Add the CHANGELOG bullet** — under `## [Unreleased]` → `### Added` in `CHANGELOG.md` (after line 24):

```markdown
- **An optional "Automatic updates" setting that installs everything on a weekly schedule — off by default.**
  When turned on, OneUp runs the full update once a week in the background,
  with the same pre-update snapshot and one-click rollback a manual run gets.
  It needs the "Passwordless" setting (an unattended run can't stop to ask for
  a password), so switching Automatic updates on offers to enable both at once;
  switching Passwordless off turns Automatic updates off too, so you're never
  left with a schedule that would silently fail. The three background settings
  (weekly check, passwordless, automatic updates) now live behind a single
  **⚙ Settings** button in the header.
```

- [ ] **Step 2: Add the README feature bullet** — under "What it does" in `README.md`, add to the bullet list (after the Passwordless bullet at line 45-48):

```markdown
- **Update automatically every week** — optionally (off by default). A
  "Automatic updates" setting runs the whole update on a weekly schedule in the
  background, keeping the snapshot/rollback safety net. It needs the
  "Passwordless" setting, so an unattended run doesn't stop to ask for a password.
```

- [ ] **Step 3: Flip the ROADMAP item** — mark ONEUP-0022 shipped with a one-line resolution note. Use the roadmap tool:

Run (via `mcp__ants__roadmap_log`): `op: flip`, `id: ONEUP-0022`, `to_status: shipped`, `note: "Resolved (2026-07-23): weekly unattended full-update timer (oneup-update.{service,timer}), off by default, gated on ONEUP-0023 passwordless. Engine skips the interactive sudo -v bootstrap when the drop-in is active + notifies at end of a full run; GUI groups the three background toggles behind a Settings popup and couples auto-update on/off to passwordless. See docs/specs/ONEUP-0022-unattended-updates.md."`, `caller_cwd: /mnt/Games/Scripts/Linux/OneUp`.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md README.md ROADMAP.md
git commit -m "ONEUP-0022: document automatic weekly updates + flip roadmap to shipped"
```

---

## Task 7: Full local CI gate

**Files:** none (verification only).

- [ ] **Step 1: Run the fast local CI gates**

Run: `./local-CI.sh`
Expected: green — the full engine suite, the GUI smoke test, lint, desktop/AppStream validation, and the version-lockstep check all pass in ~1s. (Do **not** run `--full`/the AppImage build; GitHub CI builds it on the release tag.)

- [ ] **Step 2: If anything is red, fix at root cause** — no `--no-verify`, no silencing. A lockstep failure here would be unexpected (no version change), so treat it as a signal. Re-run until green.

- [ ] **Step 3: Manual on-box acceptance (optional but recommended, not CI)** — on the real machine: `./update_system.sh --grant-auth`, then a manual `./update_system.sh --steps=cache` completes with **zero** password prompts (confirms the `sudo_init` skip + `verifypw=all` reasoning hold against the live sudoers); `./update_system.sh --revoke-auth` restores the single prompt. Report the result to the user; do not gate the commit on it.

---

## Self-Review (completed against the spec)

**Spec coverage:**
- Engine change 1 (skip bootstrap) → Task 1. Engine change 2 (end-of-run notify) → Task 2.
- Shared timer helper / command builder / `oneup-update` timer pair / `--update` GUI-only entrypoint / auto-update state read → Task 3.
- Settings popup + header restructure + min-width 720→560 → Task 4.
- Coupling rule 2 (enable, with the engine-missing up-front guard, disable-during-async, reflected-switch-picks-branch-only, settle-is-single-install-gate, install-success check) and rule 3 (revoke removes timer + clears latch, hooked to the action) → Task 5.
- Shared consent caveat factored so both call sites share it → Task 5 (`_confirm_passwordless`).
- Correctness invariants (no silent broken schedule; safety net preserved; Persistent catch-up; marker contract untouched) → satisfied by Tasks 1/3/5 + `OnCalendar=weekly Persistent=true` in `_install_user_timer`.
- Failure-mode table rows → Task 5 (engine-missing revert, cancel, popup-cancel/visudo-reject, OSError revert via `_install_user_timer` returning False, non-zero enable via `_timer_enabled` re-probe, revoke) + Task 2 (2am failure notify).
- Tests (engine notify; engine bootstrap-skip regression; GUI Settings + coupling stubs; manual on-box acceptance) → Tasks 1, 2, 3, 4, 5, 7.
- Docs & release → Task 6; no version bump (Task 6 note).

**Placeholder scan:** the Task-4 `on_autoupdate_toggled` is an intentional, labelled placeholder replaced in Task 5 (not a plan gap — it keeps the signal valid between commits). No other TBDs.

**Type consistency:** `_headless_command(flag)`, `_install_user_timer(basename, description, exec_flag) -> bool`, `_remove_user_timer(basename)`, `_timer_enabled(timer) -> bool`, `_autoupdate_enabled()`, `_set_autoupdate_checked(on)`, `_refresh_autoupdate_label()`, `_confirm_passwordless(lead="") -> bool`, `_pending_autoupdate: bool`, `_settings_dialog`, `_settings_status(text)` — names identical across Tasks 3/4/5 and the tests.

**Deliberate non-changes (from the spec):** weekly-check's toggle is not hardened (its handler keeps current behaviour); the `sudo_init` change intentionally also removes the manual-run bootstrap prompt under passwordless — flag both to the user at review.
