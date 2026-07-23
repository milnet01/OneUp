# System-Tray Icon (ONEUP-0018) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, ambient system-tray icon that turns amber when updates are waiting, with a right-click Check/Update/Open/Quit menu and an opt-in "start at boot" — off by default, degrading cleanly where there is no tray.

**Architecture:** All changes are in `updater.py` (the PySide6 GUI) plus `tests/gui-smoke.py` and docs. **No engine (`update_system.sh`) or marker change.** The resident tray runs the existing read-only `--check` itself and reads `@@CHECK@@|TOTAL|<n>|updates available`. A single method, `Updater._ensure_tray()`, owns *all* "become resident" setup (icon, single-instance server, check timer, quit-behaviour); every entry path (autostart `--tray`, a normal launch with the setting on, a mid-session Settings enable) funnels through it.

**Tech Stack:** Python 3, PySide6 (Qt 6) — `QSystemTrayIcon`, `QMenu`, `QTimer`, `QProcess`, `QLocalServer`/`QLocalSocket`, `QPainter`/`QPixmap`. Tests run under Qt's `offscreen` platform.

## Global Constraints

- Spec of record: `docs/specs/ONEUP-0018-system-tray-icon.md`. Read it before starting.
- The GUI **never** runs as root; the tray check is the unprivileged, read-only `--check` with **no `--notify`** (silent — the icon replaces the popup).
- No `@@…@@` marker is added, renamed, or re-laid-out. The tray reads only the existing `@@CHECK@@|TOTAL|<n>|updates available` line.
- Both new settings default **off**. Turning the tray off must fully reverse residency (stop timer, close server, restore quit-on-close, remove autostart) and never leave the app invisible + unquittable.
- Constants: `APP_ID = "za.co.antsprojectshub.OneUp"`, `APP_NAME = "OneUp"`.
- Follow existing `updater.py` idioms: `GhostBtn` object name for header toggles, `blockSignals` for programmatic reflects (never re-fire a handler), `subprocess`/`QProcess` fixed-argv (no shell), skip-cleanly for absent tools.
- Run the full test via `tests/run-tests.sh` (or just `python3 tests/gui-smoke.py`); run `./local-CI.sh` green before any push.

---

## File Structure

- **Modify `updater.py`** — imports, three module constants, ~20 new `Updater` methods + two toggle buttons + `SettingsDialog` rows + `closeEvent`/`main()` changes. All additive; no existing method is rewritten (only `closeEvent`, `on_finished`, and `main()` gain a few lines).
- **Modify `tests/gui-smoke.py`** — new `check(...)` blocks appended inside `main()` before the summary print.
- **Modify `CHANGELOG.md`, `README.md`** — user-facing notes (Task 7).

The test harness (`tests/gui-smoke.py`) is one `main()` that builds `updater.Updater()` under `offscreen` Qt and asserts with `check("desc", cond)`. Under offscreen Qt, `QSystemTrayIcon.isSystemTrayAvailable()` is **False**, so `_tray_available` is False and `_ensure_tray()` no-ops — tests exercise the pure/file helpers and the coupling logic (stubbing `_ensure_tray`/`_install_autostart` the way existing tests stub `_install_user_timer`).

---

### Task 1: Imports, constants, and autostart-file helpers

**Files:**
- Modify: `updater.py` (import block ~42–61; constants after `LOG_DIR` ~89; new methods on `Updater`)
- Test: `tests/gui-smoke.py`

**Interfaces:**
- Produces: `Updater._autostart_path(self) -> Path`, `Updater._startboot_enabled(self) -> bool`, `Updater._autostart_exec() -> str` (static), `Updater._install_autostart(self) -> bool`, `Updater._remove_autostart(self)`.

- [ ] **Step 1: Add imports and constants**

In `updater.py`, extend the existing import lines:

```python
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import (
    QLocalServer,
    QLocalSocket,
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)
```

Add `QMenu` and `QSystemTrayIcon` to the `from PySide6.QtWidgets import (...)` block (keep it alphabetical: `QMenu` after `QMainWindow`, `QSystemTrayIcon` after `QScrollArea`).

After the `LOG_DIR = STATE_DIR / "logs"` line, add:

```python
# Tray: one QTimer drives both the short initial check and the recurring one, so a
# single .stop() on tray-off cancels everything (no stray one-shot survives).
TRAY_INITIAL_DELAY_MS = 4000                 # first check ~4s after launch (don't slow login)
TRAY_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000  # then every 6 hours
TRAY_ATTENTION_COLOR = "#f5a623"             # amber "updates waiting" badge
```

- [ ] **Step 2: Write the failing tests** — append inside `tests/gui-smoke.py main()`, before the summary print:

```python
    # --- ONEUP-0018: system-tray icon ------------------------------------------
    # (1) Autostart Exec targets --tray and quotes the executable.
    _orig_which = updater.shutil.which
    updater.shutil.which = lambda name: None            # force the sys.executable branch
    updater.os.environ.pop("APPIMAGE", None)
    try:
        exec_line = updater.Updater._autostart_exec()
    finally:
        updater.shutil.which = _orig_which
    check("autostart Exec ends in --tray", exec_line.endswith(" --tray"))
    check("autostart Exec double-quotes the executable", exec_line.startswith('"'))

    # (2) install/remove round-trips a real file under the sandbox HOME.
    w_tmp = updater.Updater()
    check("start-at-boot starts disabled", w_tmp._startboot_enabled() is False)
    ok_install = w_tmp._install_autostart()
    check("install_autostart writes the file", ok_install and w_tmp._startboot_enabled())
    body = w_tmp._autostart_path().read_text()
    check("autostart file targets --tray", "--tray" in body and "[Desktop Entry]" in body)
    w_tmp._remove_autostart()
    check("remove_autostart deletes the file", not w_tmp._startboot_enabled())
```

Add a focused escaping assertion that pins `\\$` and `%%` without needing a `$`/`%` in the real path — test the private char-escaper via a crafted path by temporarily pointing `sys.executable`:

```python
    _orig_exe = updater.sys.executable
    updater.sys.executable = "/opt/o$ne%up/oneup"
    updater.shutil.which = lambda name: None
    updater.os.environ.pop("APPIMAGE", None)
    try:
        line = updater.Updater._autostart_exec()
    finally:
        updater.sys.executable = _orig_exe
        updater.shutil.which = _orig_which
    check("Exec escapes '$' as backslash-backslash-'$' (not $$ or bare $)", r"\\$" in line and "$$" not in line)
    check("Exec escapes '%' as '%%'", "%%up" in line)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 tests/gui-smoke.py`
Expected: FAIL — `AttributeError: 'Updater' object has no attribute '_autostart_exec'` (or `_install_autostart`).

- [ ] **Step 4: Implement the helpers** — add these methods to the `Updater` class (near the existing `_headless_command`, ~updater.py:1146):

```python
    def _autostart_path(self) -> Path:
        return Path.home() / ".config" / "autostart" / f"{APP_ID}-tray.desktop"

    def _startboot_enabled(self) -> bool:
        return self._autostart_path().exists()

    @staticmethod
    def _autostart_exec() -> str:
        """Executable (same resolution as _headless_command) quoted for a freedesktop
        Desktop Entry Exec key, then ' --tray'. This is NOT the systemd escaping:
        per the Desktop Entry Spec, the string-value backslash-unescape runs before the
        Exec quote-unescape, so a literal '$' in the file is '\\$', a literal backslash
        is '\\\\', and a literal '%' (a field code) is '%%'."""
        def _arg(p) -> str:
            out = ['"']
            for ch in str(p):
                if ch == "%":
                    out.append("%%")
                elif ch == "\\":
                    out.append("\\\\\\\\")   # four backslashes on disk
                elif ch == "$":
                    out.append("\\\\$")      # \\$ on disk (freedesktop-unambiguous)
                elif ch == '"':
                    out.append('\\"')
                elif ch == "`":
                    out.append("\\`")
                else:
                    out.append(ch)
            out.append('"')
            return "".join(out)

        appimage = os.environ.get("APPIMAGE")
        if appimage:
            return f"{_arg(appimage)} --tray"
        launcher = shutil.which("oneup")
        if launcher:
            return f"{_arg(launcher)} --tray"
        return f"{_arg(sys.executable)} {_arg(Path(__file__).resolve())} --tray"

    def _install_autostart(self) -> bool:
        """Write the autostart .desktop entry; return True iff it lands on disk.
        A plain file drop — no systemctl reload (unlike the update timers)."""
        path = self._autostart_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=OneUp (tray)\n"
                "Comment=OneUp update status in the system tray\n"
                f"Exec={self._autostart_exec()}\n"
                f"Icon={APP_ID}\n"
                "Terminal=false\n"
                "NoDisplay=true\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
        except OSError as exc:
            QMessageBox.warning(self, "Could not change start-at-boot", str(exc))
            return False
        return path.exists()

    def _remove_autostart(self):
        try:
            self._autostart_path().unlink()
        except OSError:      # already gone — fine (mirrors _remove_user_timer)
            pass
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 tests/gui-smoke.py`
Expected: PASS for all Task-1 checks.

- [ ] **Step 6: Commit**

```bash
git add updater.py tests/gui-smoke.py
git commit -m "ONEUP-0018: autostart .desktop helpers + Desktop-Entry Exec escaping"
```

---

### Task 2: Tray icon rendering + window raise

**Files:**
- Modify: `updater.py` (new methods on `Updater`)
- Test: `tests/gui-smoke.py`

**Interfaces:**
- Consumes: `_app_icon()` (updater.py:1988), `TRAY_ATTENTION_COLOR`.
- Produces: `Updater._tray_icon(self, attention: bool) -> QIcon`, `Updater._show_window(self)`.

- [ ] **Step 1: Write the failing tests**

```python
    # (3) The tray icon renders in both states and is never null.
    w = updater.Updater()
    check("neutral tray icon is non-null", not w._tray_icon(False).isNull())
    check("attention tray icon is non-null", not w._tray_icon(True).isNull())
    try:
        w._show_window()   # must not throw under offscreen Qt
        check("_show_window runs without error", True)
    except Exception as exc:  # noqa: BLE001
        check(f"_show_window runs without error ({exc})", False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/gui-smoke.py`
Expected: FAIL — `AttributeError: ... '_tray_icon'`.

- [ ] **Step 3: Implement** — add to `Updater`:

```python
    def _tray_icon(self, attention: bool) -> QIcon:
        """Compose the tray icon at runtime: the app icon, plus an amber badge when
        updates are waiting. Drawn (not themed), so it reads on any desktop theme;
        falls back to a plain disc if the app icon can't be found (never blank)."""
        base = _app_icon()
        if not base.isNull():
            pm = base.pixmap(64, 64)
        else:
            pm = QPixmap(64, 64)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#888888"))
            p.drawEllipse(8, 8, 48, 48)
            p.end()
        if attention:
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QColor("#ffffff"))
            p.setBrush(QColor(TRAY_ATTENTION_COLOR))
            d = 26
            p.drawEllipse(pm.width() - d - 3, pm.height() - d - 3, d, d)
            p.end()
        return QIcon(pm)

    def _show_window(self):
        """Un-hide + best-effort raise. Un-hiding is reliable; the focus-raise is
        subject to the same Wayland limitation the app documents for recenter."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/gui-smoke.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add updater.py tests/gui-smoke.py
git commit -m "ONEUP-0018: tray icon rendering (amber badge) + _show_window"
```

---

### Task 3: The silent periodic check

**Files:**
- Modify: `updater.py` (new methods; `__init__` gains `_traycheck_proc`/`_tray_total`/`_tray_checked_at` — added in Task 4, but referenced here; add a minimal init now)
- Test: `tests/gui-smoke.py`

**Interfaces:**
- Consumes: `ENGINE`, `LOG_DIR`, `datetime`, `QProcess`.
- Produces: `Updater._tray_check_args(self, log_path) -> list[str]`, `Updater._tray_check(self)`, `Updater._on_traycheck_output(self)`, `Updater._parse_tray_line(self, line: str)`, `Updater._on_traycheck_finished(self, *args)`, `Updater._apply_tray_total(self, n: int)`.

- [ ] **Step 1: Add the state fields** — in `Updater.__init__`, next to the other `self._…` initialisers (near updater.py:797, after `self._pending_autoupdate = False`):

```python
        self._tray = None
        self._tray_timer = None
        self._tray_total = 0
        self._tray_checked_at = None
        self._tray_hint_shown = False
        self._local_server = None
        self._traycheck_proc = None
        self._traycheck_buf = ""
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
```

- [ ] **Step 2: Write the failing tests**

```python
    # (4) The periodic check is silent and parses the real THREE-field TOTAL line.
    w = updater.Updater()
    args = w._tray_check_args("/tmp/x.log")
    check("tray check runs --check", "--check" in args)
    check("tray check is silent (no --notify)", "--notify" not in args)
    w._parse_tray_line("@@CHECK@@|TOTAL|3|updates available")
    check("tray parses field 1 of the three-field TOTAL line", w._tray_total == 3)
    w._parse_tray_line("@@CHECK@@|TOTAL|0|updates available")
    check("tray parses zero updates as neutral", w._tray_total == 0)
    w._parse_tray_line("@@STEP_BEGIN@@|system|1|3|x")   # non-CHECK line ignored
    check("tray parser ignores non-TOTAL lines", w._tray_total == 0)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 tests/gui-smoke.py`
Expected: FAIL — `AttributeError: ... '_tray_check_args'`.

- [ ] **Step 4: Implement** — add to `Updater`:

```python
    @staticmethod
    def _tray_check_args(log_path) -> list[str]:
        # The read-only check, WITHOUT --notify: the ambient icon replaces the popup.
        return [str(ENGINE), "--check", f"--log={log_path}"]

    def _tray_check(self):
        """Run the engine's read-only --check on its own QProcess and read only the
        TOTAL marker — never disturbs the window's task rows / progress / run state."""
        if not ENGINE.exists():
            return
        proc = self._traycheck_proc
        if proc is not None and proc.state() != QProcess.NotRunning:
            return  # a check is already in flight
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self._traycheck_buf = ""
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self._on_traycheck_output)
        p.finished.connect(self._on_traycheck_finished)
        self._traycheck_proc = p
        p.start("bash", self._tray_check_args(LOG_DIR / f"{stamp}.traycheck.log"))

    def _on_traycheck_output(self):
        chunk = bytes(self._traycheck_proc.readAllStandardOutput()).decode(errors="replace")
        self._traycheck_buf = (self._traycheck_buf + chunk).replace("\r\n", "\n").replace("\r", "\n")
        while "\n" in self._traycheck_buf:
            line, self._traycheck_buf = self._traycheck_buf.split("\n", 1)
            self._parse_tray_line(line)

    def _parse_tray_line(self, line: str):
        # Engine emits @@CHECK@@|TOTAL|<n>|updates available (three fields). Read field
        # 1 like handle_marker does; a naive int(after-prefix) would choke on field 2.
        if line.startswith("@@CHECK@@|"):
            parts = line[len("@@CHECK@@|"):].split("|")
            if len(parts) >= 2 and parts[0] == "TOTAL":
                self._apply_tray_total(int(parts[1]) if parts[1].isdigit() else 0)

    def _on_traycheck_finished(self, *args):
        if self._traycheck_proc is not None:
            self._traycheck_proc.deleteLater()   # don't accumulate over a long session
            self._traycheck_proc = None

    def _apply_tray_total(self, n: int):
        self._tray_total = n
        self._tray_checked_at = datetime.now()
        if self._tray is None:
            return
        self._tray.setIcon(self._tray_icon(n > 0))
        self._tray.setToolTip(
            f"{APP_NAME} — {n} update(s) waiting" if n > 0 else f"{APP_NAME} — up to date")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 tests/gui-smoke.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add updater.py tests/gui-smoke.py
git commit -m "ONEUP-0018: silent periodic tray check + three-field TOTAL parser"
```

---

### Task 4: Resident lifecycle — `_ensure_tray()` and single-instance server

**Files:**
- Modify: `updater.py` (new methods)
- Test: `tests/gui-smoke.py`

**Interfaces:**
- Consumes: `_tray_icon`, `_show_window`, `_tray_check`, `_apply_tray_total`, the Task-3 state fields, `QSystemTrayIcon`, `QMenu`, `QTimer`, `QLocalServer`, `TRAY_INITIAL_DELAY_MS`, `TRAY_CHECK_INTERVAL_MS`.
- Produces: `_ensure_tray`, `_on_tray_activated`, `_on_tray_timer`, `_tray_update`, `_teardown_tray`, `_single_instance_name`, `_arm_single_instance`, `_on_single_instance_connection`, `_close_single_instance`.

- [ ] **Step 1: Write the failing tests** (offscreen has no tray, so assert the availability guard + a clean teardown):

```python
    # (5) _ensure_tray no-ops when no system tray is available (offscreen CI case).
    w = updater.Updater()
    check("no system tray under offscreen Qt", w._tray_available is False)
    w._ensure_tray()
    check("_ensure_tray builds nothing without a tray", w._tray is None)
    # Force the 'available' path with a stub tray so teardown logic is exercised.
    w._tray = object()                 # pretend a tray exists
    w._tray_timer = updater.QTimer(w)
    w._tray_timer.start(999999)
    w._teardown_tray()
    check("teardown stops the timer", w._tray_timer is None)
    check("teardown drops the tray reference", w._tray is None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/gui-smoke.py`
Expected: FAIL — `AttributeError: ... '_ensure_tray'`.

- [ ] **Step 3: Implement** — add to `Updater`:

```python
    # ---- resident tray lifecycle (ONEUP-0018) -----------------------------
    def _single_instance_name(self) -> str:
        return f"OneUp-{os.getuid()}"

    def _arm_single_instance(self):
        """Listen so a later second launch raises THIS copy instead of duplicating.
        Armed here — the single point where OneUp becomes resident — so it covers
        both an autostart/normal-enabled launch and a mid-session Settings enable."""
        if self._local_server is not None:
            return
        name = self._single_instance_name()
        QLocalServer.removeServer(name)          # clear a stale socket from a crash
        server = QLocalServer(self)
        if server.listen(name):
            server.newConnection.connect(self._on_single_instance_connection)
            self._local_server = server

    def _on_single_instance_connection(self):
        conn = self._local_server.nextPendingConnection()
        if conn is not None:
            conn.close()
        self._show_window()

    def _close_single_instance(self):
        if self._local_server is not None:
            self._local_server.close()
            self._local_server = None

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:    # left-click
            self._show_window()

    def _on_tray_timer(self):
        self._tray_check()
        self._tray_timer.setInterval(TRAY_CHECK_INTERVAL_MS)  # short first fire, then 6h

    def _tray_update(self):
        self._show_window()
        self.start_run()

    def _ensure_tray(self):
        """The single 'become resident' entry point — idempotent. Every path that makes
        OneUp resident funnels through it, so all resident setup lives in one place."""
        if self._tray is not None or not self._tray_available:
            return
        self._tray = QSystemTrayIcon(self)
        menu = QMenu()
        menu.addAction("Check now", self._tray_check)
        menu.addAction("Update now", self._tray_update)
        menu.addAction("Open OneUp", self._show_window)
        menu.addSeparator()
        menu.addAction("Quit", QApplication.quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.setIcon(self._tray_icon(self._tray_total > 0))
        self._tray.setToolTip(
            f"{APP_NAME} — not checked yet" if self._tray_checked_at is None
            else f"{APP_NAME} — {self._tray_total} update(s) waiting" if self._tray_total > 0
            else f"{APP_NAME} — up to date")
        self._tray.show()
        self._arm_single_instance()
        self._tray_timer = QTimer(self)
        self._tray_timer.timeout.connect(self._on_tray_timer)
        self._tray_timer.start(TRAY_INITIAL_DELAY_MS)
        QApplication.setQuitOnLastWindowClosed(False)

    def _teardown_tray(self):
        """Reverse every _ensure_tray step. Never leaves the app invisible + unquittable."""
        if self._tray_timer is not None:
            self._tray_timer.stop()
            self._tray_timer = None
        self._close_single_instance()
        if self._tray is not None:
            if isinstance(self._tray, QSystemTrayIcon):
                self._tray.hide()
            self._tray = None
        QApplication.setQuitOnLastWindowClosed(True)
        if self.isHidden():
            self._show_window()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/gui-smoke.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add updater.py tests/gui-smoke.py
git commit -m "ONEUP-0018: _ensure_tray resident lifecycle + single-instance server"
```

---

### Task 5: Settings toggles + coupling

**Files:**
- Modify: `updater.py` (`__init__` toggle creation ~827–859; `SettingsDialog.__init__` rows; new handler methods)
- Test: `tests/gui-smoke.py`

**Interfaces:**
- Consumes: `_ensure_tray`, `_teardown_tray`, `_install_autostart`, `_remove_autostart`, `_startboot_enabled`, `self.settings`.
- Produces: `tray_btn`, `startboot_btn`, `_refresh_tray_label`, `_refresh_startboot_label`, `_set_tray_checked`, `_set_startboot_checked`, `on_tray_toggled`, `on_startboot_toggled`.

- [ ] **Step 1: Create the toggle buttons** — in `Updater.__init__`, after the `autoupdate_btn` block (~updater.py:859), add (note: `setChecked` **before** `toggled.connect`, so the initial state never fires the handler — mirror the existing toggles):

```python
        # System-tray icon + start-at-boot (ONEUP-0018). Both off by default; disabled
        # when the desktop has no tray. tray_enabled is a QSettings preference; start-at-boot
        # reads the real autostart-file existence.
        self.tray_btn = QPushButton()
        self.tray_btn.setObjectName("GhostBtn")
        self.tray_btn.setCheckable(True)
        self.tray_btn.setCursor(Qt.PointingHandCursor)
        self.tray_btn.setToolTip("Show a small tray icon that turns amber when updates are waiting")
        self.tray_btn.setChecked(self.settings.value("tray_enabled", False, type=bool))
        self._refresh_tray_label()
        self.tray_btn.toggled.connect(self.on_tray_toggled)

        self.startboot_btn = QPushButton()
        self.startboot_btn.setObjectName("GhostBtn")
        self.startboot_btn.setCheckable(True)
        self.startboot_btn.setCursor(Qt.PointingHandCursor)
        self.startboot_btn.setToolTip("Start OneUp automatically at login (needs the tray icon)")
        self.startboot_btn.setChecked(self._startboot_enabled())
        self._refresh_startboot_label()
        self.startboot_btn.toggled.connect(self.on_startboot_toggled)

        if not self._tray_available:
            self.tray_btn.setEnabled(False)
            self.startboot_btn.setEnabled(False)
```

- [ ] **Step 2: Add the handler methods** — add to `Updater` (near the other toggle handlers):

```python
    def _refresh_tray_label(self):
        self.tray_btn.setText("Tray icon: on" if self.tray_btn.isChecked() else "Tray icon: off")

    def _refresh_startboot_label(self):
        self.startboot_btn.setText(
            "Start at boot: on" if self.startboot_btn.isChecked() else "Start at boot: off")

    def _set_tray_checked(self, on: bool):
        self.tray_btn.blockSignals(True)
        self.tray_btn.setChecked(on)
        self.tray_btn.blockSignals(False)
        self._refresh_tray_label()

    def _set_startboot_checked(self, on: bool):
        self.startboot_btn.blockSignals(True)
        self.startboot_btn.setChecked(on)
        self.startboot_btn.blockSignals(False)
        self._refresh_startboot_label()

    def on_tray_toggled(self, on: bool):
        self.settings.setValue("tray_enabled", on)
        if on:
            if self._tray_available:
                self._ensure_tray()
        else:
            # Turning the tray off also clears start-at-boot and fully ends residency.
            self._remove_autostart()
            self._set_startboot_checked(False)
            self._teardown_tray()
        self._refresh_tray_label()

    def on_startboot_toggled(self, on: bool):
        if on:
            # Start-at-boot needs the tray on; enabling it turns the tray on first.
            if not self.tray_btn.isChecked():
                self.tray_btn.setChecked(True)   # fires on_tray_toggled(True) -> _ensure_tray
            if not self._install_autostart():
                self._set_startboot_checked(False)   # write failed; tray stays on (valid)
        else:
            self._remove_autostart()             # does NOT turn the tray off
        self._refresh_startboot_label()
```

- [ ] **Step 3: Add the two Settings rows** — in `SettingsDialog.__init__` (updater.py:725), after the third `_row(...)` (the auto-update row), add:

```python
        _tray_note = "" if parent._tray_available else "  (your desktop has no system tray)"
        root.addWidget(self._row(
            "Show a small icon near the clock that turns amber when updates are waiting."
            + _tray_note, parent.tray_btn))
        root.addWidget(self._row(
            "Start OneUp automatically at login, hidden in the tray." + _tray_note,
            parent.startboot_btn))
```

- [ ] **Step 4: Write the tests**

```python
    # (6) Settings dialog hosts the two new toggles; both default off.
    w = updater.Updater()
    check("tray toggle defaults off", not w.tray_btn.isChecked() and w.tray_btn.text() == "Tray icon: off")
    check("start-at-boot toggle defaults off",
          not w.startboot_btn.isChecked() and w.startboot_btn.text() == "Start at boot: off")
    dlg = updater.SettingsDialog(w)
    hosted = dlg.findChildren(QPushButton)
    check("Settings dialog hosts the tray toggle", w.tray_btn in hosted)
    check("Settings dialog hosts the start-at-boot toggle", w.startboot_btn in hosted)

    # (7) Coupling — enabling start-at-boot turns the tray on.
    w = updater.Updater()
    w._install_autostart = lambda: True
    w._ensure_tray = lambda: None
    w.on_startboot_toggled(True)
    check("boot-on turns the tray on", w.tray_btn.isChecked())
    check("boot-on persists tray_enabled", w.settings.value("tray_enabled", False, type=bool) is True)

    # (8) Coupling — turning the tray off removes start-at-boot.
    w = updater.Updater()
    removed = []
    w._remove_autostart = lambda: removed.append(True)
    w._teardown_tray = lambda: None
    w._set_startboot_checked(True)
    w.on_tray_toggled(False)
    check("tray-off removes autostart", removed == [True])
    check("tray-off clears the start-at-boot toggle", not w.startboot_btn.isChecked())

    # (9) Coupling — turning start-at-boot off leaves the tray on.
    w = updater.Updater()
    removed2 = []
    w._remove_autostart = lambda: removed2.append(True)
    w._set_tray_checked(True)
    w.on_startboot_toggled(False)
    check("boot-off removes autostart", removed2 == [True])
    check("boot-off leaves the tray on", w.tray_btn.isChecked())

    # (10) A failed autostart write reverts start-at-boot only (tray stays on).
    w = updater.Updater()
    w._install_autostart = lambda: False
    w._ensure_tray = lambda: None
    w.on_startboot_toggled(True)
    check("failed install reverts start-at-boot", not w.startboot_btn.isChecked())
    check("failed install leaves the tray on", w.tray_btn.isChecked())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 tests/gui-smoke.py`
Expected: PASS. (Write the tests first, watch them fail on the missing `tray_btn`, then wire Steps 1–3.)

- [ ] **Step 6: Commit**

```bash
git add updater.py tests/gui-smoke.py
git commit -m "ONEUP-0018: Settings tray + start-at-boot toggles with coupling"
```

---

### Task 6: Close-to-tray, on_finished hooks, and `main()` wiring

**Files:**
- Modify: `updater.py` (`closeEvent` ~1074; `on_finished` end ~1809 and ~1865; a module-level `_raise_existing_instance`; `main()` ~2020)
- Test: `tests/gui-smoke.py`

**Interfaces:**
- Consumes: `_tray`, `_tray_hint_shown`, `_apply_tray_total`, `_ensure_tray`, `QLocalSocket`, `QSystemTrayIcon`, `QSettings`.
- Produces: updated `closeEvent`; `_notify_tray_hint`; module `_raise_existing_instance() -> bool`; updated `main()`.

- [ ] **Step 1: Write the failing tests**

```python
    # (11) Close-to-tray: with a tray live, closeEvent hides (not quits) and hints once.
    w = updater.Updater()
    w._tray = object()                       # pretend resident
    hints = []
    w._notify_tray_hint = lambda: hints.append(True)
    class _Evt:
        def __init__(self): self.ignored = False
        def ignore(self): self.ignored = True
        def accept(self): pass
    e1 = _Evt(); w.closeEvent(e1)
    check("close-to-tray ignores the close event", e1.ignored)
    check("close-to-tray hides the window", w.isHidden())
    check("close-to-tray fires the hint once", hints == [True])
    e2 = _Evt(); w.closeEvent(e2)
    check("close-to-tray does not re-hint on a second close", hints == [True])

    # (12) on_finished refreshes the tray: a successful run -> neutral; a check -> the count.
    w = updater.Updater()
    applied = []
    w._apply_tray_total = lambda n: applied.append(n)
    w.proc = QProcess(w)
    w._installed_count = "2"
    w.on_finished(0, QProcess.ExitStatus.NormalExit)     # a run
    check("successful run sets the tray neutral", applied and applied[-1] == 0)
    w = updater.Updater()
    applied2 = []
    w._apply_tray_total = lambda n: applied2.append(n)
    w._check_mode = True
    w._installed_count = "5"
    w.proc = QProcess(w)
    w.on_finished(0, QProcess.ExitStatus.NormalExit)     # a check
    check("finished check pushes the count to the tray", applied2 and applied2[-1] == 5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/gui-smoke.py`
Expected: FAIL — `AttributeError: ... '_notify_tray_hint'` and the on_finished assertions.

- [ ] **Step 3: Update `closeEvent`** — replace the existing `closeEvent` (updater.py:1074–1076) with:

```python
    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        if self._tray is not None:
            # Resident: hide to the tray instead of quitting.
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self._notify_tray_hint()
            return
        super().closeEvent(event)

    def _notify_tray_hint(self):
        """A one-off 'still running in the tray' nudge. A DIRECT notify-send (keeps
        _notify_when_away's which-guard but drops its isActiveWindow guard, which would
        suppress it since the window is still active at close time)."""
        if not shutil.which("notify-send"):
            return
        try:
            subprocess.Popen(  # noqa: S603,S607 — fixed argv, no shell.
                ["notify-send", "-a", APP_NAME, "-i", APP_ID, APP_NAME,
                 "OneUp is still running in the tray — right-click the icon to quit."],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
```

- [ ] **Step 4: Add the `on_finished` tray hooks** — in `on_finished`, add one line just before the check-branch `return` (after updater.py:1807 `self._notify_when_away(...)`, before `self._check_mode = False`):

```python
            self._apply_tray_total(total)
```

And add, as the **last** statement of `on_finished` (after the `self._notify_when_away(...)` at ~1865):

```python
        # Keep the ambient tray icon honest: a clean run just installed updates.
        if ok:
            self._apply_tray_total(0)
```

- [ ] **Step 5: Add the single-instance client helper + wire `main()`** — add a module-level function near `_headless_update` (updater.py:2009):

```python
def _raise_existing_instance() -> bool:
    """True if a resident OneUp answered the socket (and was asked to show its window)."""
    sock = QLocalSocket()
    sock.connectToServer(f"OneUp-{os.getuid()}")
    if sock.waitForConnected(300):
        sock.write(b"1")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False
```

Update `main()` (updater.py:2020). Keep the `--check`/`--update` dispatch. After `app.setDesktopFileName(APP_ID)` and the theme setup, replace the tail (`icon = _app_icon() … win.show(); app.exec()`) with:

```python
    argv = sys.argv[1:]
    tray_wanted = (QSettings("OneUp", "OneUp").value("tray_enabled", False, type=bool)
                   and QSystemTrayIcon.isSystemTrayAvailable())
    if tray_wanted and _raise_existing_instance():
        sys.exit(0)   # a resident copy is already running — it raised its window

    icon = _app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    win = Updater()
    if not icon.isNull():
        win.setWindowIcon(icon)
    if tray_wanted:
        win._ensure_tray()                 # owns quit-behaviour, server, and the check timer
        if "--tray" not in argv:
            win.show()                     # autostart (--tray) starts hidden; a normal launch shows
    else:
        win.show()                         # no tray wanted/available (incl. --tray with no tray): degrade
    app.exec()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 tests/gui-smoke.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add updater.py tests/gui-smoke.py
git commit -m "ONEUP-0018: close-to-tray, on_finished tray refresh, --tray entry + single-instance client"
```

---

### Task 7: Docs

**Files:**
- Modify: `CHANGELOG.md` (`[Unreleased] / Added`), `README.md` ("What it does")

**Interfaces:** none (docs only).

- [ ] **Step 1: Add the CHANGELOG entry** — under `## [Unreleased]` → `### Added` in `CHANGELOG.md`:

```markdown
- **An optional system-tray icon that turns amber when updates are waiting.** Off by
  default. When on, OneUp keeps running quietly in the tray; the icon goes amber when a
  background check finds updates, and a right-click menu gives Check now / Update now /
  Open OneUp / Quit. An optional "Start at boot" launches it hidden at login. It checks
  every six hours using the same read-only, password-free check as the weekly popup, and
  degrades cleanly on desktops without a system tray.
```

Prefer the MCP helper to keep the Keep-a-Changelog format exact:
`changelog_log` with `op:"add"`, `category:"Added"`, `id:"ONEUP-0018"`, `caller_cwd` = repo root.

- [ ] **Step 2: Add the README bullet** — under "What it does" in `README.md`, add:

```markdown
- **Sit quietly in the system tray** and turn amber when updates are waiting, so you
  notice without catching a popup (optional; can also start at login).
```

- [ ] **Step 3: Run the full suite + local CI**

Run: `tests/run-tests.sh && ./local-CI.sh`
Expected: all green (the engine suite is unchanged; gui-smoke includes the new tray checks; lint/validation/version-lockstep pass — no version bump in this change).

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md README.md
git commit -m "ONEUP-0018: document the system-tray icon (CHANGELOG + README)"
```

- [ ] **Step 5: Flip the roadmap** — once landed, flip ONEUP-0018 to shipped with a resolution note (via `roadmap_log op:"flip"`), noting that the tray runs its **own** independent `--check` and the menu is Check/Update/Open/Quit — superseding the bullet's original "reflect the weekly check result" / "dismiss" gloss.

---

## Self-Review

**Spec coverage** — every spec section maps to a task:
- Two toggles + coupling → Task 5. Autostart entry + Exec escaping → Task 1. Tray icon + `_show_window` → Task 2. Silent periodic check + three-field parser + cadence → Task 3. `_ensure_tray` single owner + single-instance server + teardown → Task 4. Close-to-tray + on_finished hooks + `main()`/`--tray` + client check + graceful degradation → Task 6. Docs → Task 7. All spec correctness invariants (no marker change, opt-in/reversible, never invisible+unquittable, silent check) are pinned by tests in Tasks 1–6.
- Failure modes: no-tray (Task 5 disabled toggles + Task 6 degrade), install OSError (Task 1/Task 5 revert), engine-missing (Task 3 guard), second launch (Task 4 server + Task 6 client), tray-host crash (recovery via client raise — documented, not separately testable headlessly).

**Type consistency** — method names are stable across tasks: `_ensure_tray`, `_teardown_tray`, `_apply_tray_total`, `_tray_check`/`_tray_check_args`, `_parse_tray_line`, `_install_autostart`/`_remove_autostart`/`_startboot_enabled`/`_autostart_exec`, `on_tray_toggled`/`on_startboot_toggled`, `_set_tray_checked`/`_set_startboot_checked`, `_raise_existing_instance`. State fields (`_tray`, `_tray_timer`, `_tray_total`, `_tray_checked_at`, `_tray_hint_shown`, `_local_server`, `_traycheck_proc`, `_traycheck_buf`, `_tray_available`) are all declared once in `__init__` (Task 3, Step 1).

**Placeholder scan** — no TBD/TODO; every code step carries complete code.

**Ordering note for the executor:** Task 3 declares the `__init__` state fields that Tasks 4–6 rely on; keep Task order. `_ensure_tray` (Task 4) is stubbed in Task 5's coupling tests, so Task 5 does not depend on a working tray.
