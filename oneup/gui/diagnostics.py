"""Describing this machine when the user reports a problem.

The clipboard bug-report bundle and the two figures it needs — the newest real
run log, and what zypper's package cache weighs.
"""
from __future__ import annotations

import socket
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .. import APP_VERSION
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
    return max(runs, key=lambda p: p.stat().st_mtime, default=None)


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
    machine name. An oversized log is trimmed to its last DIAG_LOG_CAP chars.
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
    else:
        if len(log_text) > DIAG_LOG_CAP:
            log_text = "[… earlier output trimmed …]\n" + log_text[-DIAG_LOG_CAP:]
        out.append(f"--- latest run log ({log_name}) ---")
        out.append(log_text)
    report = "\n".join(out)
    if home:
        report = report.replace(home, "~")
    if host:
        report = report.replace(host, "<host>")
    return report



def cache_bytes() -> int:
    """Weigh zypper's package cache. Sampled against a baseline taken as the run starts,
    the growth is how much has been downloaded — the only figure available while zypper is
    prefetching, because that phase prints no sizes and no progress of any kind."""
    total = 0
    try:
        for p in paths.ZYPP_PACKAGE_CACHE.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                continue        # a file zypper moved or removed mid-walk
    except OSError:
        return 0                # no cache directory, or not readable — figure unavailable
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
    report = build_diagnostics(
        APP_VERSION, _os_release_pretty(), win.selected_steps(),
        log_name, log_text, datetime.now().strftime("%Y-%m-%d %H:%M"),
        str(Path.home()), socket.gethostname())
    QApplication.clipboard().setText(report)
    win.diag_btn.setText("Copied ✓")
    win._settings_status("Diagnostics copied — paste them into your bug report.")
