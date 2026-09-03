"""Running OneUp without being asked to.

The autostart desktop entry and the two systemd user timers — the weekly check
and the weekly unattended update. `_headless_command` builds the command a unit
runs, and takes the entry point from `paths.ENTRY_POINT` rather than from its
own `__file__`: a unit built here from `__file__` would run
`python3 …/oneup/gui/autostart.py --check`, which does nothing at all, and the
existing assertions pass either way (spec §4.4).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from .. import APP_ID
from . import auth, paths


def _user_units_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


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
    return f"{_arg(sys.executable)} {_arg(paths.ENTRY_POINT)} {flag}"


def _autostart_path() -> Path:
    return Path.home() / ".config" / "autostart" / f"{APP_ID}-tray.desktop"


def _startboot_enabled() -> bool:
    return _autostart_path().exists()


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
    return f"{_arg(sys.executable)} {_arg(paths.ENTRY_POINT)} --tray"


def _install_autostart(win) -> bool:
    """Write the autostart .desktop entry; return True iff it lands on disk.
    A plain file drop — no systemctl reload (unlike the update timers)."""
    path = _autostart_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=OneUp (tray)\n"
            "Comment=OneUp update status in the system tray\n"
            f"Exec={_autostart_exec()}\n"
            f"Icon={APP_ID}\n"
            "Terminal=false\n"
            "NoDisplay=true\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
    except OSError as exc:
        QMessageBox.warning(win, "Could not change start-at-boot", str(exc))
        return False
    return path.exists()


def _remove_autostart():
    try:
        _autostart_path().unlink()
    except OSError:      # already gone — fine (mirrors _remove_user_timer)
        pass


def _timer_enabled(timer: str) -> bool:
    r = subprocess.run(["systemctl", "--user", "is-enabled", timer],  # noqa: S603,S607
                       capture_output=True, text=True)
    return r.stdout.strip() == "enabled"


def _autocheck_enabled() -> bool:
    return _timer_enabled("oneup-check.timer")


def _autoupdate_enabled() -> bool:
    return _timer_enabled("oneup-update.timer")


def _install_user_timer(win, basename: str, description: str, exec_flag: str) -> bool:
    """Write + enable a weekly systemd-user timer. Returns True iff it ends up
    enabled (an OSError writing the unit, or a failed enable, returns False)."""
    units = _user_units_dir()
    try:
        units.mkdir(parents=True, exist_ok=True)
        (units / f"{basename}.service").write_text(
            f"[Unit]\nDescription={description}\n\n"
            f"[Service]\nType=oneshot\n"
            f"ExecStart={_headless_command(exec_flag)}\n"
        )
        (units / f"{basename}.timer").write_text(
            f"[Unit]\nDescription={description}\n\n"
            "[Timer]\nOnCalendar=weekly\nPersistent=true\n\n"
            "[Install]\nWantedBy=timers.target\n"
        )
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)  # noqa: S607
        subprocess.run(["systemctl", "--user", "enable", "--now",  # noqa: S603,S607
                        f"{basename}.timer"], check=False)
    except OSError as exc:
        QMessageBox.warning(win, "Could not change the schedule", str(exc))
        return False
    return _timer_enabled(f"{basename}.timer")


def _remove_user_timer(basename: str):
    units = _user_units_dir()
    subprocess.run(["systemctl", "--user", "disable", "--now",  # noqa: S603,S607
                    f"{basename}.timer"], check=False)
    for name in (f"{basename}.timer", f"{basename}.service"):
        try:
            (units / name).unlink()
        except OSError:
            pass
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)  # noqa: S607


def _refresh_autocheck_label(win):
    on = win.auto_btn.isChecked()
    win.auto_btn.setText("Weekly check: on" if on else "Weekly check: off")


def on_autocheck_toggled(win, on: bool):
    # Weekly-check behaviour is unchanged: install/remove and refresh the label.
    # It deliberately does NOT revert its toggle on a failed install (see the
    # ONEUP-0022 spec's "Open questions" — hardening weekly-check is a separate item).
    if on:
        _install_user_timer(win, "oneup-check", "OneUp weekly update check", "--check")
    else:
        _remove_user_timer("oneup-check")
    _refresh_autocheck_label(win)


def _refresh_autoupdate_label(win):
    on = win.autoupdate_btn.isChecked()
    win.autoupdate_btn.setText(
        "Automatic updates: on" if on else "Automatic updates: off")


def _set_autoupdate_checked(win, on: bool):
    """Reflect the real state on the toggle WITHOUT re-firing on_autoupdate_toggled."""
    win.autoupdate_btn.blockSignals(True)
    win.autoupdate_btn.setChecked(on)
    win.autoupdate_btn.blockSignals(False)
    _refresh_autoupdate_label(win)


def on_autoupdate_toggled(win, on: bool):
    # Up-front engine guard MIRRORS on_auth_toggled: with the engine absent the
    # async chain hits _query_auth_status's early return and NO settle ever fires,
    # so we must revert-and-return BEFORE any latch/disable, or the toggle would be
    # stuck disabled forever.
    if not paths.engine_available():
        _set_autoupdate_checked(win, False)
        return
    if on:
        # The reflected passwordless switch is only used to pick the entry branch;
        # the install itself always waits for a FRESH auth settle (never trusts the
        # possibly-stale switch). Disable the toggle for the async op (closes the
        # mirror race where the user un-clicks mid-probe); re-enabled in the settle.
        win._pending_autoupdate = True
        win.autoupdate_btn.setEnabled(False)
        if win.auth_btn.isChecked():
            # Looks on — verify with a fresh probe; the settle installs iff truly on.
            auth._query_auth_status(win)
        else:
            # Offer to enable BOTH at once, with the shared consent caveat.
            if auth._confirm_passwordless(win,
                    lead="Automatic updates need OneUp to run without a password.\n\n"):
                auth._run_auth(win, "--grant-auth",
                               "Setting up… (approve the password popup)")
                # _run_auth -> _on_auth_finished -> _query_auth_status -> settle installs.
            else:
                win._pending_autoupdate = False
                win.autoupdate_btn.setEnabled(True)
                _set_autoupdate_checked(win, False)
    else:
        # User turns auto-update off: remove the timer, clear any stray latch.
        _remove_user_timer("oneup-update")
        win._pending_autoupdate = False
        _refresh_autoupdate_label(win)


def _refresh_startboot_label(win):
    win.startboot_btn.setText(
        "Start at boot: on" if win.startboot_btn.isChecked() else "Start at boot: off")


def _set_startboot_checked(win, on: bool):
    win.startboot_btn.blockSignals(True)
    win.startboot_btn.setChecked(on)
    win.startboot_btn.blockSignals(False)
    _refresh_startboot_label(win)


def on_startboot_toggled(win, on: bool):
    if on:
        # Start-at-boot needs the tray on; enabling it turns the tray on first.
        if not win.tray_btn.isChecked():
            win.tray_btn.setChecked(True)   # fires on_tray_toggled(True) -> _ensure_tray
        if not _install_autostart(win):
            _set_startboot_checked(win, False)   # write failed; tray stays on (valid)
    else:
        _remove_autostart()             # does NOT turn the tray off
    _refresh_startboot_label(win)
