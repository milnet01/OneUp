"""Starting OneUp, with a window or without one.

`--check` and `--update` are the headless modes the two optional systemd user
timers invoke; everything else builds the window. A launch always defers to a
copy that is already running, tray or no tray (ONEUP-0084).
"""
from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
from datetime import datetime

from PySide6.QtCore import QSettings
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .. import APP_ID, APP_NAME
from . import markers, paths, tray
from .theme import _app_icon, apply_app_theme
from .window import Updater


def _headless_engine(args: list[str], read) -> int:
    """Run the engine for a timer, echoing every line it prints and handing each marker
    to `read`. Returns its exit status.

    The output is read line by line and written straight back out, so a terminal user
    and the systemd journal still see the run go past (ONEUP-0077 INV-6) and nothing
    buffers a whole transcript. stderr is left inherited: it carries no markers, and
    redirecting it would swallow the engine's own refusals."""
    proc = subprocess.Popen(  # noqa: S603 — the resolver's argv, no shell.
        paths.engine_argv(*args), stdout=subprocess.PIPE, text=True,
        errors="replace", bufsize=1)
    for line in proc.stdout or ():
        sys.stdout.write(line)
        sys.stdout.flush()
        if line.startswith("@@"):
            parsed = markers.split_marker(line.rstrip("\n"))
            if parsed:
                read(parsed[0], parsed[1])
    return proc.wait()


def _notify(title: str, body: str) -> None:
    """Raise a desktop notification with no display and no Qt: the desktop's
    notification service, as the engine did (ONEUP-0077 INV-4). Never fatal."""
    if not shutil.which("notify-send"):
        return
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(  # noqa: S603 — fixed argv, no shell.
            ["notify-send", "-a", APP_NAME, "-i", APP_ID, title, body],  # noqa: S607
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)


def _headless_log(suffix: str) -> str | None:
    """A timestamped log under the window's own log folder, so a notification can
    name it (ONEUP-0077 §4). None, said on stderr, when the folder can't be made."""
    if not paths.log_dir_ready(quiet=True):
        return None
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return str(paths.STATE_LOG_DIR / f"{stamp}{suffix}")


def _headless_check() -> int:
    """`oneup --check`: the engine's read-only check, and the window's notification.
    This is what the optional weekly systemd-user timer invokes."""
    if not paths.engine_available():     # the resolver has said what it tried, on stderr
        return 1
    log = _headless_log(".check.log")
    if log is None:
        return 1
    seen = {"total": 0, "reasons": []}

    def read(tag: str, parts: list[str]) -> None:
        if tag == "CHECK" and len(parts) > 1 and parts[0] == "TOTAL":
            seen["total"] = int(parts[1]) if parts[1].isdecimal() else 0
        elif tag == "CHECK_UNKNOWN":
            seen["reasons"].append(markers.render_check_unknown(parts[1:]))

    rc = _headless_engine(["--check", f"--log={log}"], read)
    note = markers.check_notification(seen["total"], seen["reasons"])
    if note:
        _notify(*note)
    return rc


def _headless_update() -> int:
    """`oneup --update`: the FULL engine and the window's end-of-run notification, no
    GUI. This is what the optional weekly systemd-user UPDATE timer invokes. `--update`
    is a GUI-only token — the engine runs its default steps, which is every step, and
    is NEVER handed --update (its arg parser would reject it). --auto-skip-repos is
    additive: an unattended run should set a single broken software source aside and
    finish the rest, not fail the whole update."""
    if not paths.engine_available():     # the resolver has said what it tried, on stderr
        return 1
    log = _headless_log(".log")
    if log is None:
        return 1
    seen = {"done": None, "count": "", "changed": False, "skipped": []}

    def read(tag: str, parts: list[str]) -> None:
        if tag == "DONE" and parts:
            seen["done"] = parts[0]
        elif tag == "INSTALLED" and parts:
            seen["count"] = parts[0]
            seen["changed"] = "yes" in parts[1:3]
        elif tag == "REPO_SKIPPED" and parts and parts[0]:
            seen["skipped"].append(parts[0])

    rc = _headless_engine(["--auto-skip-repos", f"--log={log}"], read)
    _notify(*markers.run_notification(seen["done"], seen["count"], seen["changed"],
                                      seen["skipped"], log))
    return rc


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
    def _rethemed(*_):
        """The desktop switched light/dark: re-theme, then rebuild the tray icon.

        `apply_app_theme` deliberately does not touch the tray — the icon has no
        parent widget and belongs to its window — so without this second half the
        icon keeps the old palette's colours on this route (ONEUP-0027 INV-8).
        """
        apply_app_theme(app)
        for widget in app.topLevelWidgets():
            if getattr(widget, "_tray", None) is not None:
                tray.refresh_icon(widget)

    try:  # re-theme live when the desktop switches light/dark (Qt 6.5+)
        app.styleHints().colorSchemeChanged.connect(_rethemed)
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
    # Honour the answer. The deferral above ran before this window existed, so a
    # copy started at the same instant got past it; this is the point at which the
    # loser finds out (ONEUP-0084's simultaneous case).
    if not tray._arm_single_instance(win):
        _raise_existing_instance("tray" if "--tray" in argv else "show")
        sys.exit(0)
    if tray_wanted:
        tray._ensure_tray(win)                 # owns quit-behaviour, server, and the check timer
        if "--tray" not in argv:
            win.show()                     # autostart (--tray) starts hidden; a normal launch shows
    else:
        win.show()   # no tray wanted/available (incl. --tray with no tray): degrade
    app.exec()
