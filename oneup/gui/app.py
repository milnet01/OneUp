"""Starting OneUp, with a window or without one.

`--check` and `--update` are the headless modes the two optional systemd user
timers invoke; everything else builds the window. A launch always defers to a
copy that is already running, tray or no tray (ONEUP-0084).
"""
from __future__ import annotations

import subprocess
import sys

from PySide6.QtCore import QSettings
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .. import APP_ID, APP_NAME
from . import paths, tray
from .theme import _app_icon, apply_app_theme
from .window import Updater


def _headless_check() -> int:
    """`oneup --check`: run the engine's read-only check + notification, no GUI.
    This is what the optional weekly systemd-user timer invokes."""
    if not paths.ENGINE.exists():
        print(f"OneUp: update script not found at {paths.ENGINE}", file=sys.stderr)
        return 1
    return subprocess.run(  # noqa: S603
        ["bash", str(paths.ENGINE), "--check", "--notify"]  # noqa: S607
    ).returncode


def _headless_update() -> int:
    """`oneup --update`: run the FULL engine + its end-of-run notification, no GUI.
    This is what the optional weekly systemd-user UPDATE timer invokes. `--update`
    is a GUI-only token — the engine is run with just --notify (its default STEPS is
    every step) and is NEVER handed --update (its arg parser would reject it).
    Also passes --auto-skip-repos (additive): an unattended run should set a single
    broken software source aside and finish the rest, not fail the whole update."""
    if not paths.ENGINE.exists():
        print(f"OneUp: update script not found at {paths.ENGINE}", file=sys.stderr)
        return 1
    return subprocess.run(  # noqa: S603
        ["bash", str(paths.ENGINE), "--notify", "--auto-skip-repos"]  # noqa: S607
    ).returncode


def _raise_existing_instance(intent: str) -> bool:
    """True if another OneUp for this user answered, and was told what we wanted.

    `intent` is "show" for a person launching OneUp — raise the running window — or
    "tray" for the autostart entry, which must NOT throw a window up over whatever
    the user is doing at login; it only needs to learn that someone is resident.
    """
    sock = QLocalSocket()
    sock.connectToServer(tray.single_instance_name())
    if not sock.waitForConnected(tray.SINGLE_INSTANCE_TIMEOUT_MS):
        return False
    sock.write(intent.encode())
    sock.waitForBytesWritten(tray.SINGLE_INSTANCE_TIMEOUT_MS)
    sock.disconnectFromServer()
    return True


def main():
    if "--check" in sys.argv[1:]:
        sys.exit(_headless_check())
    if "--update" in sys.argv[1:]:
        sys.exit(_headless_update())

    app = QApplication([])
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)  # ties the window to its .desktop/icon

    # One theming entry point (module-level apply_app_theme): it folds in the
    # user's text-size and high-contrast settings, and the Settings controls call
    # the same function, so every path stays consistent.
    apply_app_theme(app)
    try:  # re-theme live when the desktop switches light/dark (Qt 6.5+)
        app.styleHints().colorSchemeChanged.connect(lambda *_: apply_app_theme(app))
    except (AttributeError, TypeError):
        pass

    argv = sys.argv[1:]
    # Defer to a copy that is already running — ALWAYS, not only when the tray is on.
    # At login KDE starts two (the autostart entry and Plasma's session restore of
    # the window left open at logout); previously neither deferred and the user got
    # two tray icons, two check timers, and two engines able to race for the zypper
    # lock (ONEUP-0084).
    if _raise_existing_instance("tray" if "--tray" in argv else "show"):
        sys.exit(0)   # the running copy has been told; nothing left for us to do

    tray_wanted = (QSettings("OneUp", "OneUp").value("tray_enabled", False, type=bool)
                   and QSystemTrayIcon.isSystemTrayAvailable())

    icon = _app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    win = Updater()
    if not icon.isNull():
        win.setWindowIcon(icon)
    # Claim the socket for the whole life of the process, tray or no tray, so the
    # NEXT launch has something to defer to (ONEUP-0084). Idempotent — _ensure_tray
    # calls it too, for a mid-session Settings enable.
    tray._arm_single_instance(win)
    if tray_wanted:
        tray._ensure_tray(win)                 # owns quit-behaviour, server, and the check timer
        if "--tray" not in argv:
            win.show()                     # autostart (--tray) starts hidden; a normal launch shows
    else:
        win.show()   # no tray wanted/available (incl. --tray with no tray): degrade
    app.exec()
