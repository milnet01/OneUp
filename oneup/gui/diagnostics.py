"""Describing this machine when the user reports a problem.

The clipboard bug-report bundle and the two figures it needs — the newest real
run log, and what zypper's package cache weighs.
"""
from __future__ import annotations

import getpass
import os
import re
import socket
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from .. import APP_VERSION, APP_VERSION_LABEL
from . import paths, steps

# multi-megabyte blob onto the clipboard. Errors sit near the end, so keep the tail.
DIAG_LOG_CAP = 200 * 1024

def _latest_run_log(log_dir: Path) -> Path | None:
    """Newest real update-run log in log_dir, or None.

    Run logs are named ``<timestamp>.log`` (one dot). The check/auth/size probes
    add a middle segment (``.check.log``, ``.auth.log``, ``.size.log``) and the
    tray writes a fixed ``traycheck.log`` — exclude both so this returns an
    actual update run, not a probe.
    """
    try:
        runs = [p for p in log_dir.glob("*.log")
                if p.name.count(".") == 1 and p.name != "traycheck.log"]
    except OSError:
        return None
    stamped = []
    for p in runs:
        try:                           # a log rotated away mid-call is skipped (ONEUP-0184)
            stamped.append((p.stat().st_mtime, p))
        except OSError:
            continue
    return max(stamped, key=lambda tp: tp[0], default=(0.0, None))[1]


def _os_release_pretty() -> str:
    """PRETTY_NAME from /etc/os-release (e.g. 'openSUSE Tumbleweed 20260723')."""
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.partition("=")[2].strip().strip('"')
    except OSError:
        pass
    return "unknown"


def build_diagnostics(version: str, os_pretty: str, enabled: list[str],
                      log_name: str | None, log_text: str | None,
                      when: str, home: str, host: str) -> str:
    """Assemble the clipboard bug-report bundle (pure — no I/O, no clock).

    Scrubs the home path (-> ~) and hostname (-> <host>) across the whole
    payload, log body included, so a public paste doesn't leak the username or
    machine name. An oversized log is trimmed to its last DIAG_LOG_CAP chars after it
    is scrubbed, so the cut cannot split a login the scrub would have caught.
    """
    tasks = "  ".join(f"{key} {'✓' if key in enabled else '✗'}"
                      for key, _t, _d in steps.TASKS)
    out = [
        "=== OneUp diagnostics ===",
        f"OneUp:    {version}",
        f"openSUSE: {os_pretty}",
        f"Tasks:    {tasks}",
        f"When:     {when}",
        "",
    ]
    if log_text is None:
        out.append("--- no update has been run yet ---")
        return _scrub("\n".join(out), home, host)
    out.append(f"--- latest run log ({log_name}) ---")
    # Scrubbed apart from the header so no text is scrubbed twice: a user called "user"
    # would turn a "<user>" already written into "<<user>>".
    log_text = _scrub(log_text, home, host)
    if len(log_text) > DIAG_LOG_CAP:
        log_text = "[… earlier output trimmed …]\n" + log_text[-DIAG_LOG_CAP:]
    return _scrub("\n".join(out), home, host) + "\n" + log_text


def _scrub(report: str, home: str, host: str) -> str:
    """Take the home path, URL logins, the user name and the host name out of `report`."""
    if home:
        report = report.replace(home, "~")
    # The report is written to be pasted publicly (security.md §7.4). The home path
    # above is not the only place a user name appears — sudo's "user X is not
    # allowed" names it bare — and a repository URL can carry a login (ONEUP-0401).
    report = _URL_LOGIN.sub(r"\1<login>@", report)
    user = _user_name()
    if user:
        report = re.sub(rf"(?<![\w.-]){re.escape(user)}(?![\w-])", "<user>", report)
    if host:
        # Only where the name stands alone (ONEUP-0159): openSUSE host names are often
        # words the log uses too, and `oss` must not rewrite `repo-oss` or `/repo/oss/`.
        # A following `.` is allowed, so `oss.lan` is still scrubbed.
        report = re.sub(rf"(?<![\w./-]){re.escape(host)}(?![\w/-])", "<host>", report)
    return report



# `scheme://user:password@` or `scheme://user@`: everything between the scheme and
# the @ is the login, whatever it holds.
_URL_LOGIN = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^\s/@]+@", re.IGNORECASE)


def _user_name() -> str:
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return ""


def cache_bytes() -> int:
    """Weigh zypper's package cache. Sampled against a baseline taken as the run starts,
    the growth is how much has been downloaded — the only figure available while zypper is
    prefetching, because that phase prints no sizes and no progress of any kind."""
    # os.scandir rather than Path.rglob: this runs on the GUI thread every 5s across
    # thousands of files, and a DirEntry answers is_dir/is_file from the directory read
    # itself — one stat per file instead of two, and no Path object (ONEUP-0347).
    total = 0
    pending = [paths.ZYPP_PACKAGE_CACHE]
    while pending:
        try:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(entry.path)
                        elif entry.is_file():
                            total += entry.stat().st_size
                    except OSError:
                        continue    # a file zypper moved or removed mid-walk
        except OSError:
            continue                # no cache directory, or not readable — counts as 0
    return total




def copy_diagnostics(win):
    """Bundle version info + the latest run log onto the clipboard for a bug
    report (the Settings dialog's 'Copy diagnostics' button)."""
    log = _latest_run_log(paths.STATE_LOG_DIR)
    log_name = log_text = None
    if log is not None:
        log_name = log.name
        try:
            log_text = log.read_text(errors="replace")
        except OSError as e:
            log_text = f"(could not read {log.name}: {e})"
    # A preview build names the number underneath too, so a report says
    # exactly which merge of main it was built from (ONEUP-0272).
    version = (APP_VERSION if APP_VERSION_LABEL == APP_VERSION
               else f"{APP_VERSION_LABEL} ({APP_VERSION})")
    report = build_diagnostics(
        version, _os_release_pretty(), win.selected_steps(),
        log_name, log_text, datetime.now().strftime("%Y-%m-%d %H:%M"),
        str(Path.home()), socket.gethostname())
    QApplication.clipboard().setText(report)
    win.diag_btn.setText(QCoreApplication.translate("diagnostics", "Copied ✓"))
    win._settings_status(QCoreApplication.translate(
        "diagnostics",
        "Diagnostics copied — paste them into your bug report."))
