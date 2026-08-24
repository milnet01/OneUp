"""Living in the system tray.

The tray icon and its silent background check, plus the single-instance socket
— which is armed on EVERY GUI launch and never torn down while the process
lives, because two copies are two check timers and two engines racing for the
zypper lock whether or not a tray icon is involved (ONEUP-0084).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from functools import partial

from PySide6.QtCore import QProcess, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import APP_ID, APP_NAME
from . import autostart, paths, run, theme
from .theme import _app_icon

# Single-instance handshake budget (ONEUP-0084). Both ends are local sockets on the
# same machine, so this is generous; it only has to be long enough that a copy still
# working through its own startup can still answer before we conclude it isn't there.
SINGLE_INSTANCE_TIMEOUT_MS = 500


# Tray: one QTimer drives both the short initial check and the recurring one, so a
# single .stop() on tray-off cancels everything (no stray one-shot survives).
TRAY_INITIAL_DELAY_MS = 4000                 # first check ~4s after launch (don't slow login)
TRAY_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000  # then every 6 hours


def single_instance_name() -> str:
    """Per-user, so two people logged into the same machine each get their own copy.

    Overridable so the suite can exercise the guard without connecting to the user's
    LIVE OneUp — which would pop their window open mid-test, and would make the
    result depend on whether they happen to have it running
    (docs/standards/testing.md §2).
    """
    return os.environ.get("ONEUP_INSTANCE_NAME") or f"OneUp-{os.getuid()}"


def _tray_icon(attention: bool) -> QIcon:
    """Compose the tray icon at runtime: the app icon, plus an amber badge when
    updates are waiting. Drawn (not themed), so it reads on any desktop theme;
    falls back to a plain disc if the app icon can't be found (never blank).

    Its four colours are palette tokens (ONEUP-0027 §4.3), read through
    `current_palette()` on every call so a theme change repaints the badge —
    which is why `apply_app_theme` rebuilds the icon rather than only the sheet."""
    pal = theme.current_palette()
    base = _app_icon()
    if not base.isNull():
        pm = base.pixmap(64, 64)
    else:
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal["trayidle"]))
        p.drawEllipse(8, 8, 48, 48)
        p.end()
    if attention:
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(pal["trayrim"]))
        p.setBrush(QColor(pal["trayattn"]))
        d = 26
        x, y = pm.width() - d - 3, pm.height() - d - 3
        p.drawEllipse(x, y, d, d)
        # An exclamation mark inside the disc, so "updates waiting" differs in
        # SHAPE and not only in colour — an amber dot alone is invisible to a
        # colour-blind user (ONEUP-0028).
        font = QFont()
        font.setBold(True)
        font.setPixelSize(int(d * 0.72))
        p.setFont(font)
        p.setPen(QColor(pal["traymark"]))
        p.drawText(QRectF(x, y, d, d), Qt.AlignCenter, "!")
        p.end()
    return QIcon(pm)


def _show_window(win):
    """Un-hide + best-effort raise. Un-hiding is reliable; the focus-raise is
    subject to the same Wayland limitation the app documents for recenter."""
    win.showNormal()
    win.raise_()
    win.activateWindow()


def _tray_check_args(log_path) -> list[str]:
    # The read-only check, WITHOUT --notify: the ambient icon replaces the popup.
    return [str(paths.ENGINE), "--check", f"--log={log_path}"]


def _tray_check(win):
    """Run the engine's read-only --check on its own QProcess and read only the
    TOTAL marker — never disturbs the window's task rows / progress / run state."""
    if not paths.ENGINE.exists():
        return
    proc = win._traycheck_proc
    if proc is not None and proc.state() != QProcess.NotRunning:
        return  # a check is already in flight
    win._traycheck_buf = ""
    win._traycheck_unknown = False
    p = QProcess(win)
    p.setProcessChannelMode(QProcess.MergedChannels)
    p.readyReadStandardOutput.connect(partial(_on_traycheck_output, win))
    p.finished.connect(partial(_on_traycheck_finished, win))
    win._traycheck_proc = p
    p.start("bash", _tray_check_args(_traycheck_log()))


def _traycheck_log():
    """One rolling log for the silent tray check, truncated each run (ONEUP-0024).
    A resident tray checks ~4x/day indefinitely; a per-run timestamped file would
    pile up. The engine's `tee -a` starts from the truncated file, so reusing one
    fixed name still overwrites (the output is silent, so no history is lost)."""
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = paths.LOG_DIR / "traycheck.log"
    path.write_text("")   # roll: overwrite the previous check's output
    return path


def _on_traycheck_output(win):
    chunk = bytes(win._traycheck_proc.readAllStandardOutput()).decode(errors="replace")
    win._traycheck_buf = ((win._traycheck_buf + chunk)
                           .replace("\r\n", "\n").replace("\r", "\n"))
    while "\n" in win._traycheck_buf:
        line, win._traycheck_buf = win._traycheck_buf.split("\n", 1)
        _parse_tray_line(win, line)


def _parse_tray_line(win, line: str):
    # Engine emits @@CHECK@@|TOTAL|<n>|updates available (three fields). Read field
    # 1 like handle_marker does; a naive int(after-prefix) would choke on field 2.
    # A source the check couldn't read makes the total a floor, not an answer —
    # the tray must not sit there quietly claiming "up to date" (ONEUP-0056).
    # Ordered first: the engine emits CHECK_UNKNOWN before the TOTAL it qualifies.
    if line.startswith("@@CHECK_UNKNOWN@@|"):
        win._traycheck_unknown = True
    elif line.startswith("@@CHECK@@|"):
        parts = line[len("@@CHECK@@|"):].split("|")
        if len(parts) >= 2 and parts[0] == "TOTAL":
            _apply_tray_total(win, int(parts[1]) if parts[1].isdigit() else 0,
                                   uncertain=win._traycheck_unknown)


def _on_traycheck_finished(win, *args):
    if win._traycheck_proc is not None:
        win._traycheck_proc.deleteLater()   # don't accumulate over a long session
        win._traycheck_proc = None


def _apply_tray_total(win, n: int, uncertain: bool = False):
    win._tray_total = n
    win._tray_checked_at = datetime.now()
    if win._tray is None:
        return
    win._tray.setIcon(_tray_icon(n > 0))
    if uncertain:
        tip = (f"{APP_NAME} — {n} update(s) waiting (some sources couldn't be checked)"
               if n > 0 else f"{APP_NAME} — couldn't check for updates")
    else:
        tip = (f"{APP_NAME} — {n} update(s) waiting" if n > 0
               else f"{APP_NAME} — up to date")
    win._tray.setToolTip(tip)


def _arm_single_instance(win):
    """Listen so a later launch raises THIS copy instead of starting a second.

    Armed on EVERY GUI launch, not only a resident one, and never torn down
    while the process lives: two copies are two check timers and two engines
    racing for the zypper lock whether or not a tray icon is involved.

    The order below is the whole fix. removeServer() unlinks whatever socket is
    there, including a LIVE one, so calling it up front made a second launch
    evict the first instead of deferring to it — at login KDE starts two copies
    (the autostart entry, plus Plasma restoring the window that was open at
    logout) and both survived, which is the two-tray-icon bug (ONEUP-0084). So:
    listen first, and clear the address only once a connect has PROVEN nobody
    is answering it.
    """
    if win._local_server is not None:
        return
    name = single_instance_name()
    server = QLocalServer(win)
    if not server.listen(name):
        probe = QLocalSocket()
        probe.connectToServer(name)
        if probe.waitForConnected(SINGLE_INSTANCE_TIMEOUT_MS):
            probe.disconnectFromServer()     # a live copy owns it — leave it be
            return
        QLocalServer.removeServer(name)      # proven stale (a crash left it)
        if not server.listen(name):
            return
    server.newConnection.connect(partial(_on_single_instance_connection, win))
    win._local_server = server


def _on_single_instance_connection(win):
    conn = win._local_server.nextPendingConnection()
    if conn is None:
        return
    intent = ""
    if conn.waitForReadyRead(SINGLE_INSTANCE_TIMEOUT_MS):
        intent = bytes(conn.readAll()).decode(errors="replace").strip()
    conn.close()
    # The autostart entry only needs to learn that someone is already resident.
    # Anything else is a person launching OneUp, and wants the window.
    if intent != "tray":
        _show_window(win)


def _on_tray_activated(win, reason):
    if reason == QSystemTrayIcon.Trigger:    # left-click
        _show_window(win)


def _on_tray_timer(win):
    _tray_check(win)
    win._tray_timer.setInterval(TRAY_CHECK_INTERVAL_MS)  # short first fire, then 6h


def _tray_update(win):
    _show_window(win)
    run.start_run(win)


def _ensure_tray(win):
    """The single 'become resident' entry point — idempotent. Every path that makes
    OneUp resident funnels through it, so all resident setup lives in one place."""
    if win._tray is not None or not win._tray_available:
        return
    win._tray = QSystemTrayIcon(win)
    # Parent the menu to win: setContextMenu does not reparent it, and an
    # unparented QMenu can be garbage-collected out from under the tray icon.
    menu = QMenu(win)
    menu.addAction("Check now", partial(_tray_check, win))
    menu.addAction("Update now", partial(_tray_update, win))
    menu.addAction("Open OneUp", partial(_show_window, win))
    menu.addSeparator()
    menu.addAction("Quit", win._quit_requested)
    win._tray.setContextMenu(menu)
    win._tray.activated.connect(partial(_on_tray_activated, win))
    win._tray.setIcon(_tray_icon(win._tray_total > 0))
    win._tray.setToolTip(
        f"{APP_NAME} — not checked yet" if win._tray_checked_at is None
        else f"{APP_NAME} — {win._tray_total} update(s) waiting" if win._tray_total > 0
        else f"{APP_NAME} — up to date")
    win._tray.show()
    _arm_single_instance(win)
    win._tray_timer = QTimer(win)
    win._tray_timer.timeout.connect(partial(_on_tray_timer, win))
    win._tray_timer.start(TRAY_INITIAL_DELAY_MS)
    QApplication.setQuitOnLastWindowClosed(False)


def _teardown_tray(win):
    """Reverse every _ensure_tray step. Never leaves the app invisible + unquittable.

    Deliberately does NOT release the single-instance server: that guard belongs
    to the process, not to residency (ONEUP-0084). Switching the tray off must
    not make a second copy launchable. It is parented to the window, so it dies
    with the process either way.
    """
    if win._tray_timer is not None:
        win._tray_timer.stop()
        win._tray_timer = None
    if win._tray is not None:
        if isinstance(win._tray, QSystemTrayIcon):
            win._tray.hide()
        win._tray = None
    QApplication.setQuitOnLastWindowClosed(True)
    if win.isHidden():
        _show_window(win)


def _refresh_tray_label(win):
    win.tray_btn.setText("Tray icon: on" if win.tray_btn.isChecked() else "Tray icon: off")


def _set_tray_checked(win, on: bool):
    win.tray_btn.blockSignals(True)
    win.tray_btn.setChecked(on)
    win.tray_btn.blockSignals(False)
    _refresh_tray_label(win)


def on_tray_toggled(win, on: bool):
    win.settings.setValue("tray_enabled", on)
    if on:
        if win._tray_available:
            _ensure_tray(win)
    else:
        # Turning the tray off also clears start-at-boot and fully ends residency.
        autostart._remove_autostart()
        autostart._set_startboot_checked(win, False)
        _teardown_tray(win)
    _refresh_tray_label(win)


def _notify_tray_hint(win):
    """A one-off 'still running in the tray' nudge. A DIRECT notify-send (keeps
    _notify_when_away's which-guard but drops its isActiveWindow guard, which would
    suppress it since the window is still active at close time)."""
    if not shutil.which("notify-send"):
        return
    try:
        subprocess.Popen(  # noqa: S603 — fixed argv, no shell.
            ["notify-send", "-a", APP_NAME, "-i", APP_ID, APP_NAME,  # noqa: S607
             "OneUp is still running in the tray — right-click the icon to quit."],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


