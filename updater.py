#!/usr/bin/env python3
"""OneUp — a small Qt dashboard over update_system.sh.

The dashboard is a thin front-end: it never runs as root and contains no update
logic of its own. It shells out to the update_system.sh script that sits next to
it with a --steps list, reads that script's @@MARKER@@ progress lines to drive the
progress bar and per-step status, and shows the rest of the output in a log pane.
Each task has a phone-style on/off switch (green = on, red = off) instead of a
checkbox.

Run headless as `oneup --check` (or `updater.py --check`) to perform a read-only
"updates available?" check and a desktop notification, with no window — this is
what the optional weekly systemd-user timer calls.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from string import Template

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QProcess,
    QPropertyAnimation,
    QRectF,
    QSettings,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import (
    QLocalServer,
    QLocalSocket,
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

APP_ID = "za.co.antsprojectshub.OneUp"
APP_NAME = "OneUp"
APP_VERSION = "1.2.0"
REPO_SLUG = "milnet01/OneUp"

# Where our bundled files (update_system.sh, the icon) live. Normally next to
# this module; inside a PyInstaller/AppImage bundle they are unpacked to _MEIPASS.
if getattr(sys, "frozen", False):
    HERE = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    HERE = Path(__file__).resolve().parent


def _find_engine() -> Path:
    """Locate update_system.sh. It normally sits next to this file (git checkout,
    RPM or AppImage install); fall back to the legacy ~/Documents path so an
    existing hand-installed setup keeps working."""
    for candidate in (HERE / "update_system.sh",
                      Path.home() / "Documents" / "update_system.sh"):
        if candidate.exists():
            return candidate
    return HERE / "update_system.sh"  # default; start_run() warns if it's missing


ENGINE = _find_engine()
STATE_DIR = Path.home() / ".local" / "state" / "oneup"
HISTORY = STATE_DIR / "history.json"
LOG_DIR = STATE_DIR / "logs"

# Tray: one QTimer drives both the short initial check and the recurring one, so a
# single .stop() on tray-off cancels everything (no stray one-shot survives).
TRAY_INITIAL_DELAY_MS = 4000                 # first check ~4s after launch (don't slow login)
TRAY_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000  # then every 6 hours
TRAY_ATTENTION_COLOR = "#f5a623"             # amber "updates waiting" badge

# The last-run line turns amber once the last run is this old, nudging the user
# that an update is overdue (ONEUP-0030).
STALE_AFTER_DAYS = 14

# key, title, one-line description. Order = run order.
TASKS = [
    ("system", "System packages", "Refresh repositories and upgrade openSUSE (zypper dup)."),
    ("flatpak", "Flatpak apps", "Update Flatpak apps and remove unused runtimes."),
    ("firmware", "Firmware", "Check for and apply device firmware updates (fwupd)."),
    ("orphans", "Leftover packages", "Remove leftover dependency packages nothing needs."),
    ("cache", "Package cache", "Clear the downloaded-package cache to free disk space."),
]

# Cap the log slice pasted into a bug report so a long `zypper dup` can't push a
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
                      for key, _t, _d in TASKS)
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


GREEN = QColor("#2ecc71")
RED = QColor("#e74c3c")

# ---------------------------------------------------------------------------
# Theme — a gradient-ringed "instrument panel" that follows the desktop's
# light/dark preference. The signature azure→cyan accent (echoing the app icon)
# stays constant; only the neutral surfaces swap between the two palettes below.
# The stylesheet is a $-template so the swap is a plain dict substitution with no
# brace-escaping. Selectors are keyed to object names so system dialogs keep the
# desktop's native look.
# ---------------------------------------------------------------------------
ACCENT = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4aa3ff, stop:1 #22d3ee)"
BTN_ACCENT = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4aa3ff, stop:1 #2f6fe0)"

_QSS = Template(r"""
* { font-family: "Inter", "Noto Sans", "Segoe UI", "Cantarell", sans-serif; }
QMainWindow { background: $win; }

#Frame { border-radius: 16px; background: $accent; }
#Card  { border-radius: 14px; background: $card; }

QLabel#Header  { font-size: 21px; font-weight: 700; color: $header; }
QLabel#Tagline { font-size: 12px; color: $tag; }

#RowBorder {
    border-radius: 12px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(74,163,255,0.65), stop:1 rgba(34,211,238,0.50));
}
#RowBorder:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(104,184,255,1.0), stop:1 rgba(58,228,250,0.85));
}
#RowCard { border-radius: 11px; background: $rowcard; }
#RowBorder:hover #RowCard { background: $rowhov; }
QLabel#TaskName { font-size: 14px; font-weight: 600; color: $tname; }
QLabel#TaskDesc { font-size: 12px; color: $tdesc; }
QLabel#Badge {
    background: $badgebg; color: $badgefg; border-radius: 9px;
    padding: 2px 9px; font-size: 11px; font-weight: 600;
}
QToolButton#Disclose {
    background: transparent; border: none; padding: 0px;
}
#RowDetails { background: transparent; }
QLabel#DetailList {
    color: $tdesc; background: $logbg; border-radius: 8px; padding: 6px 8px;
    font-family: "JetBrains Mono", "Fira Code", "Noto Sans Mono", monospace; font-size: 11px;
}
QScrollArea#DetailScroll { border: none; background: transparent; }
QLabel#SizeResult { color: $tname; font-size: 12px; font-weight: 600; }

QPushButton#RunBtn {
    font-size: 14px; font-weight: 700; color: #ffffff; border: none;
    border-radius: 11px; padding: 12px 18px; background: $btn_accent;
}
QPushButton#RunBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5cb0ff, stop:1 #3a7cf0);
}
QPushButton#RunBtn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3d90ec, stop:1 #2560c8);
}
QPushButton#RunBtn:disabled { color: $disfg; background: $disbg; }

QPushButton#GhostBtn {
    color: $ghostfg; font-weight: 600; background: transparent;
    border: 1px solid $ghostbd; border-radius: 8px; padding: 8px 14px;
}
QPushButton#GhostBtn:hover { border-color: #4aa3ff; color: #4aa3ff; }
QPushButton#GhostBtn:checked { border-color: #4aa3ff; color: #4aa3ff; }
QPushButton#GhostBtn:disabled { color: $disfg; border-color: $disbg; }

QPushButton#LinkBtn {
    color: #4aa3ff; font-weight: 600; text-align: left;
    background: transparent; border: none; padding: 4px 2px;
}
QPushButton#LinkBtn:hover { color: #6fb6ff; }

QLabel#Status  { font-size: 12px; color: $status; }
QLabel#LastRun { font-size: 12px; color: $lastrun; }
QLabel#LastRun[stale="true"] { color: $amber; }

QProgressBar {
    border: none; border-radius: 9px; background: $progbg;
    min-height: 20px; text-align: center; color: $status; font-size: 12px;
}
QProgressBar::chunk { border-radius: 9px; background: $accent; }

QPlainTextEdit#Log {
    background: $logbg; color: $logfg;
    border: 1px solid $logbd; border-radius: 10px; padding: 6px;
    font-family: "JetBrains Mono", "Fira Code", "Noto Sans Mono", monospace; font-size: 11px;
}

#RebootBanner {
    border: 1px solid #e0553f; border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(231,76,60,0.22), stop:1 rgba(231,76,60,0.05));
}
QPushButton#RestartBtn {
    color: #ffffff; font-weight: 700; border: none; border-radius: 8px; padding: 7px 15px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ef6a55, stop:1 #d6412a);
}
QPushButton#RestartBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f47c68, stop:1 #e04a32);
}

#InfoBanner {
    border: 1px solid rgba(74,163,255,0.55); border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(74,163,255,0.20), stop:1 rgba(34,211,238,0.05));
}
#WarnBanner {
    border: 1px solid rgba(233,178,63,0.6); border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(233,178,63,0.20), stop:1 rgba(233,178,63,0.04));
}
QLabel#BannerText { color: $header; font-weight: 600; border: none; background: transparent; }
QPushButton#BannerBtn {
    color: #ffffff; font-weight: 700; border: none; border-radius: 8px; padding: 7px 15px;
    background: $btn_accent;
}
QPushButton#BannerBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5cb0ff, stop:1 #3a7cf0);
}

QToolTip {
    background: $tip; color: $tipfg; border: 1px solid #4aa3ff;
    border-radius: 4px; padding: 4px 6px;
}
""")

_DARK = dict(
    win="#0f1216", card="#12161c", header="#f4f7fb", tag="#8b95a5",
    rowcard="#1a1f27", rowhov="#1e242e", tname="#eef2f8", tdesc="#a7b0be",
    badgebg="#20304a", badgefg="#cfe0ff", logbg="#0b0e12", logfg="#cdd6e2",
    logbd="#262d38", status="#c3ccd9", lastrun="#828d9d", amber="#f5a623", progbg="#0c0f13",
    ghostbd="#38414f", ghostfg="#c7d0dd", disbg="#262b34", disfg="#aeb7c4",
    tip="#1a1f27", tipfg="#e9edf3",
)
_LIGHT = dict(
    win="#eef1f5", card="#ffffff", header="#1b2027", tag="#5c6673",
    rowcard="#f4f6f9", rowhov="#eaeef3", tname="#1b2027", tdesc="#5c6673",
    badgebg="#dbe8ff", badgefg="#1f4e9c", logbg="#f6f8fa", logfg="#2a2f36",
    logbd="#d5dbe2", status="#3a424d", lastrun="#8a94a2", amber="#b5730a", progbg="#dfe4ea",
    ghostbd="#c4ccd6", ghostfg="#3a424d", disbg="#d5dbe2", disfg="#9aa3ad",
    tip="#ffffff", tipfg="#1b2027",
)


def build_theme(dark: bool) -> str:
    palette = dict(_DARK if dark else _LIGHT)
    palette["accent"] = ACCENT
    palette["btn_accent"] = BTN_ACCENT
    return _QSS.substitute(palette)


def current_is_dark(app: QApplication) -> bool:
    """Follow the desktop's colour scheme (Qt 6.5+); default to dark if unknown."""
    try:
        return app.styleHints().colorScheme() != Qt.ColorScheme.Light
    except Exception:
        return True


def _version_tuple(v: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", v)] or [0]


class ToggleSwitch(QAbstractButton):
    """A sliding on/off switch. Track is green when on, red when off."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(56, 30)
        self._margin = 3
        self._pos = 1.0  # 0.0 = off (left), 1.0 = on (right)
        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.toggled.connect(self._slide)

    def _slide(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def get_knob_pos(self) -> float:
        return self._pos

    def set_knob_pos(self, value: float):
        self._pos = value
        self.update()

    knobPos = Property(float, get_knob_pos, set_knob_pos)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        radius = self.height() / 2
        track = GREEN if self.isChecked() else RED
        if not self.isEnabled():
            track = track.lighter(140)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), radius, radius)

        diameter = self.height() - 2 * self._margin
        travel = self.width() - 2 * self._margin - diameter
        x = self._margin + self._pos * travel
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, self._margin, diameter, diameter))


class TaskRow(QFrame):
    """One task, drawn as a card with a hover-lit gradient border: the 1px
    outer frame shows the accent gradient, an inner card sits 1px inside it. A
    badge on the right shows how many updates a --check found; an expandable
    panel below lists the exact packages that will change (fed by the engine's
    @@CHECK_ITEM@@ markers), with a "Show download size" link on the system row."""

    # Emitted when the user clicks "Show download size"; carries the step key.
    size_requested = Signal(str)

    def __init__(self, key: str, title: str, description: str):
        super().__init__()
        self.key = key
        self.setObjectName("RowBorder")
        self.switch = ToggleSwitch()

        name = QLabel(title)
        name.setObjectName("TaskName")
        desc = QLabel(description)
        desc.setObjectName("TaskDesc")
        desc.setWordWrap(True)

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(name)
        text.addWidget(desc)

        self.badge = QLabel("")
        self.badge.setObjectName("Badge")
        self.badge.setVisible(False)
        self._badge_text = ""   # the outcome ("3 installed"); timing is appended
        self._timing = ""       # "42s" — kept apart so a repeated marker can't stack

        # Disclosure arrow: revealed only once there are detail items to show.
        self.disclosure = QToolButton()
        self.disclosure.setObjectName("Disclose")
        self.disclosure.setArrowType(Qt.ArrowType.RightArrow)
        self.disclosure.setCheckable(True)
        self.disclosure.setCursor(Qt.CursorShape.PointingHandCursor)
        self.disclosure.setVisible(False)
        self.disclosure.toggled.connect(self._on_disclosure)

        inner = QFrame()
        inner.setObjectName("RowCard")
        row = QHBoxLayout(inner)
        row.setContentsMargins(15, 12, 15, 12)
        row.setSpacing(10)
        row.addLayout(text, 1)
        row.addWidget(self.badge, 0, Qt.AlignVCenter)
        row.addWidget(self.disclosure, 0, Qt.AlignVCenter)
        row.addWidget(self.switch, 0, Qt.AlignVCenter)

        # Collapsible detail panel: the changed-package list, plus (system only)
        # a link that fetches the exact download size on demand.
        self._items: list[str] = []
        self.details = QFrame()
        self.details.setObjectName("RowDetails")
        self.details.setVisible(False)
        dcol = QVBoxLayout(self.details)
        dcol.setContentsMargins(16, 0, 16, 12)
        dcol.setSpacing(8)

        self._items_label = QLabel("")
        self._items_label.setObjectName("DetailList")
        self._items_label.setTextFormat(Qt.TextFormat.PlainText)
        scroll = QScrollArea()
        scroll.setObjectName("DetailScroll")
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(180)
        scroll.setWidget(self._items_label)
        dcol.addWidget(scroll)

        self.size_btn = QPushButton("Show download size")
        self.size_btn.setObjectName("LinkBtn")
        self.size_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.size_btn.clicked.connect(lambda: self.size_requested.emit(self.key))
        self.size_result = QLabel("")
        self.size_result.setObjectName("SizeResult")
        self.size_result.setVisible(False)
        self._has_size = False  # explicit — survives the panel being collapsed
        if key == "system":
            srow = QHBoxLayout()
            srow.setSpacing(10)
            srow.addWidget(self.size_btn, 0)
            srow.addWidget(self.size_result, 0)
            srow.addStretch(1)
            dcol.addLayout(srow)
        else:
            self.size_btn.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)  # 1px gradient border
        outer.setSpacing(0)
        outer.addWidget(inner)
        outer.addWidget(self.details)

    def _on_disclosure(self, on: bool):
        self.details.setVisible(on)
        self.disclosure.setArrowType(
            Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)

    def add_detail_item(self, name: str, frm: str, to: str):
        """Append one changed package to the panel (name  old → new)."""
        line = f"{name:<32}  {frm}  →  {to}" if (frm or to) else name
        self._items.append(line)
        self._items_label.setText("\n".join(self._items))
        self.disclosure.setVisible(True)

    def set_size_result(self, text: str):
        """Show the download-size figure and retire the "Show download size" link."""
        self.size_btn.setVisible(False)
        self.size_result.setText(text)
        self.size_result.setVisible(True)
        self._has_size = True

    def size_pending(self):
        self.size_btn.setEnabled(False)
        self.size_btn.setText("Calculating…")

    def size_failed(self):
        """Re-arm the link so the user can retry after a failed size fetch."""
        self.size_btn.setEnabled(True)
        self.size_btn.setText("Show download size")

    def has_size(self) -> bool:
        return self._has_size

    def set_badge(self, text: str):
        self._badge_text = text
        self._render_badge()

    def set_timing(self, text: str):
        """Append how long the step took, e.g. '3 installed · 42s'."""
        self._timing = text
        self._render_badge()

    def _render_badge(self):
        parts = [p for p in (self._badge_text, self._timing) if p]
        self.badge.setText("  ·  ".join(parts))
        self.badge.setVisible(bool(parts))

    def clear_badge(self):
        self._badge_text = ""
        self._timing = ""
        self.badge.setVisible(False)

    def clear_details(self):
        """Reset the expandable panel between runs."""
        self._items = []
        self._items_label.setText("")
        self.disclosure.setChecked(False)
        self.disclosure.setVisible(False)
        self.details.setVisible(False)
        self.size_result.setVisible(False)
        self.size_result.setText("")
        self._has_size = False
        if self.key == "system":
            self.size_btn.setVisible(True)
            self.size_btn.setEnabled(True)
            self.size_btn.setText("Show download size")


# --- repository listing / management ---------------------------------------
# Repo aliases are the identifiers passed to a root `zypper modifyrepo/removerepo`;
# validate them against this before they reach a shell (defence in depth, mirroring
# the rollback snapshot-id and service-name guards).
_ALIAS_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9:@._+-]*")


def _parse_repos(text: str) -> list[dict]:
    """Parse `zypper lr -u` table output into [{alias, name, enabled, url}].
    Rows look like '# | Alias | Name | Enabled | GPG Check | Refresh | URI'; the
    header, separator, and the priority preamble are skipped (their first column
    isn't a number)."""
    repos = []
    for line in text.splitlines():
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 7 or not cols[0].isdigit():
            continue
        repos.append({
            "alias": cols[1],
            "name": cols[2] or cols[1],
            "enabled": cols[3][:1].lower() == "y",
            "url": cols[-1],
        })
    return repos


def _repo_purpose(repo: dict) -> str:
    """A one-line, plain-English guess at what a repository is for. openSUSE repos
    carry no description field, so this maps well-known naming patterns (alias / name
    / URL); an unrecognised repo falls back to a generic line. Order matters — the
    narrower patterns (debug, source) come before the broad ones (oss)."""
    hay = f"{repo['alias']} {repo['name']} {repo['url']}".lower()
    if "debug" in hay:
        return "Debug symbols — for diagnosing crashes. Usually left off."
    if "source" in hay or "/src" in hay:
        return "Source-code packages — for building software yourself. Usually left off."
    if "packman" in hay:
        return "Packman — extra multimedia codecs and media apps."
    if "nvidia" in hay:
        return "NVIDIA graphics drivers."
    if "packages.microsoft.com" in hay or "vscode" in hay:
        return "Microsoft — e.g. Visual Studio Code."
    if "dl.google.com" in hay or "google-chrome" in hay:
        return "Google Chrome browser."
    if "brave" in hay:
        return "Brave browser."
    if "non-oss" in hay or "nonoss" in hay:
        return "Non-open-source packages — some drivers, firmware and codecs."
    if "update" in hay:
        return "Official security and bug-fix updates."
    if "home:" in hay or "/repositories/" in hay:
        return "Community package repository (openSUSE Build Service)."
    if "oss" in hay or "repo-main" in hay or "-main" in hay:
        return "Main openSUSE package collection."
    return "Software package repository."


def read_repos() -> list[dict]:
    """Read the system's repositories (read-only — no root needed)."""
    if not shutil.which("zypper"):
        return []
    try:
        out = subprocess.run(  # noqa: S603,S607 — fixed argv, no shell.
            ["zypper", "--non-interactive", "lr", "-u"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "LC_ALL": "C"},  # pin the 'Yes'/'No' + column text
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return _parse_repos(out)


class RepoManagerDialog(QDialog):
    """Turn repositories on/off, and remove ones whose URL duplicates another's.
    Listing is read-only; applying the changes needs one admin (pkexec) prompt."""

    def __init__(self, parent, repos: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Repositories")
        self.setMinimumWidth(720)   # wide enough that repo URLs aren't cut off
        self._rows: list[dict] = []   # {repo, switch, remove(bool), frame}
        self._proc: QProcess | None = None

        # Remember the size the user last left this dialog at (position is always
        # re-centred over the main window in showEvent).
        self._settings = QSettings("OneUp", "OneUp")
        geo = self._settings.value("repos_geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(780, 560)

        # A URL used by more than one repository is the duplicate we can clean up.
        url_counts = Counter(r["url"] for r in repos if r["url"])

        root = QVBoxLayout(self)
        intro = QLabel(
            "Turn repositories on or off. ⚠ marks a URL used by more than one "
            "repository — a common cause of update conflicts; you can remove the "
            "extra copy. Nothing changes until you press Apply.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        inner = QWidget()
        lst = QVBoxLayout(inner)
        lst.setSpacing(6)
        for repo in repos:
            is_dup = bool(repo["url"]) and url_counts[repo["url"]] > 1
            lst.addWidget(self._make_row(repo, is_dup))
        lst.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        scroll.setMinimumHeight(280)
        root.addWidget(scroll, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.apply_btn = QPushButton("Apply changes")
        self.apply_btn.setObjectName("RunBtn")
        self.apply_btn.clicked.connect(self._apply)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("GhostBtn")
        close_btn.clicked.connect(self.reject)
        btns.addWidget(self.apply_btn)
        btns.addWidget(close_btn)
        root.addLayout(btns)

    def _make_row(self, repo: dict, is_dup: bool) -> QFrame:
        fr = QFrame()
        fr.setObjectName("RowBorder")
        lay = QHBoxLayout(fr)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(1)
        name = QLabel(("⚠  " if is_dup else "") + repo["name"])
        name.setObjectName("TaskName")
        # A plain-English line describing what the repo is for, then its URL (dim).
        purpose = QLabel(_repo_purpose(repo))
        purpose.setWordWrap(True)
        url = QLabel(repo["url"])
        url.setObjectName("TaskDesc")
        url.setWordWrap(True)
        text.addWidget(name)
        text.addWidget(purpose)
        text.addWidget(url)
        lay.addLayout(text, 1)

        entry: dict = {"repo": repo, "remove": False, "frame": fr}
        if is_dup:
            rm = QPushButton("Remove")
            rm.setObjectName("LinkBtn")
            rm.setCursor(Qt.PointingHandCursor)
            rm.clicked.connect(lambda _=False, e=entry: self._mark_removed(e))
            lay.addWidget(rm, 0)
        switch = ToggleSwitch()
        switch.setChecked(repo["enabled"])
        lay.addWidget(switch, 0, Qt.AlignVCenter)
        entry["switch"] = switch
        self._rows.append(entry)
        return fr

    def _mark_removed(self, entry: dict):
        entry["remove"] = True
        entry["frame"].setEnabled(False)   # grey it out; excluded from the toggle diff

    def _build_apply_command(self) -> list[str] | None:
        """The single pkexec command that applies every change, [] if there's
        nothing to do, or None if an alias fails validation (so it never reaches a
        root shell)."""
        enable, disable, remove = [], [], []
        for e in self._rows:
            alias = e["repo"]["alias"]
            if e["remove"]:
                remove.append(alias)
            elif e["switch"].isChecked() != e["repo"]["enabled"]:
                (enable if e["switch"].isChecked() else disable).append(alias)
        changes = enable + disable + remove
        if not changes:
            return []
        if any(not _ALIAS_RE.fullmatch(a) for a in changes):
            return None
        parts = []
        if disable:
            parts.append("zypper --non-interactive modifyrepo --disable " + " ".join(disable))
        if enable:
            parts.append("zypper --non-interactive modifyrepo --enable " + " ".join(enable))
        if remove:
            parts.append("zypper --non-interactive removerepo " + " ".join(remove))
        return ["pkexec", "sh", "-c", " && ".join(parts)]

    def _apply(self):
        cmd = self._build_apply_command()
        if cmd == []:
            self.accept()
            return
        if cmd is None:
            QMessageBox.warning(self, "Repositories",
                                "A repository name looked unsafe — nothing was changed.")
            return
        if QMessageBox.question(
                self, "Apply repository changes",
                "OneUp will apply your repository changes. This needs administrator "
                "rights and is reversible.\n\nApply now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.apply_btn.setEnabled(False)
        self._proc = QProcess(self)
        self._proc.finished.connect(self._on_applied)
        self._proc.start(cmd[0], cmd[1:])

    def _on_applied(self, code: int, _status):
        if code == 0:
            QMessageBox.information(self, "Repositories", "Repository changes applied.")
            self.accept()
        else:
            QMessageBox.warning(self, "Repositories",
                                "Couldn't apply the changes — they may have been cancelled.")
            self.apply_btn.setEnabled(True)

    def showEvent(self, event):
        # Centre over the main window each time it opens (size is restored from
        # settings; only the position is re-centred).
        super().showEvent(event)
        parent = self.parent()
        if parent:
            fg = self.frameGeometry()
            fg.moveCenter(parent.frameGeometry().center())
            self.move(fg.topLeft())

    def done(self, result: int):
        # done() is the funnel for Apply/Close/× — persist the size on the way out.
        self._settings.setValue("repos_geometry", self.saveGeometry())
        super().done(result)


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
        _tray_note = "" if parent._tray_available else "  (your desktop has no system tray)"
        root.addWidget(self._row(
            "Show a small icon near the clock that turns amber when updates are waiting."
            + _tray_note, parent.tray_btn))
        root.addWidget(self._row(
            "Start OneUp automatically at login, hidden in the tray." + _tray_note,
            parent.startboot_btn))
        root.addWidget(self._row(
            "Copy a bug report — version info plus your latest update log — to the "
            "clipboard, so filing an issue doesn't mean hunting through hidden folders.",
            parent.diag_btn))
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


class RollbackDialog(QDialog):
    """Pick which pre-update restore point to roll back to (ONEUP-0020).

    Listing only — the destructive rollback itself is confirmed and run (via one
    pkexec prompt) back in ``Updater.rollback``. Each ``snapshots`` entry is an
    (id, date, description) tuple sourced from @@SNAPSHOT_ITEM@@ markers; the
    engine already trimmed and ordered them oldest→newest, so we show them
    newest-first and pre-select the pre-update snapshot."""

    def __init__(self, parent, snapshots: list[tuple[str, str, str]], preselect_id: str):
        super().__init__(parent)
        self.setWindowTitle("Roll back this update")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Choose the restore point to return to. OneUp will restore the system "
            "to that snapshot and then reboot — anything changed since then will be "
            "lost. The point taken just before this update is selected for you.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.list = QListWidget()
        for sid, date, desc in reversed(snapshots):
            item = QListWidgetItem(f"{date}  —  {desc or 'snapshot'}   (#{sid})")
            item.setData(Qt.UserRole, sid)
            self.list.addItem(item)
            if sid == preselect_id:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)   # newest, if the pre-update id wasn't listed
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        root.addWidget(self.list, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton("Roll back & reboot")
        ok.setObjectName("RunBtn")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("GhostBtn")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        root.addLayout(btns)

    def selected_id(self) -> str:
        """The chosen snapshot number, or "" if nothing valid is selected. Re-checks
        isdigit() so a spliced non-numeric payload can never reach the root shell."""
        item = self.list.currentItem()
        sid = item.data(Qt.UserRole) if item else ""
        return sid if isinstance(sid, str) and sid.isdigit() else ""

    def showEvent(self, event):
        # Centre over the main window each time it opens (dialog standard).
        super().showEvent(event)
        parent = self.parent()
        if parent:
            fg = self.frameGeometry()
            fg.moveCenter(parent.frameGeometry().center())
            self.move(fg.topLeft())


class Updater(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        # Four header controls (Settings · Repositories · Recenter · About); the
        # three background toggles now live inside the Settings popup.
        self.setMinimumWidth(560)
        self.settings = QSettings("OneUp", "OneUp")
        self.proc: QProcess | None = None
        self._buf = ""
        self._total = 0
        self._check_mode = False
        self._reboot = False
        self._reboot_reason = ""     # optional "why a reboot matters" phrase from the engine
        self._installed_count = ""   # system packages changed, as reported by the engine
        self._sys_changed = False
        self._failed_steps: list[str] = []
        self._services = ""
        self._snapshot = ""
        self._snapshots: list[tuple[str, str, str]] = []  # (id, date, desc) for the rollback picker
        self._hints: list[str] = []
        self._hint_command = ""   # a runnable command parsed from the shown hint, for Copy
        self._remedy_keys = False  # engine flagged a fixable signing-key error (@@REMEDY@@)
        self._skipped_repos: list[str] = []  # aliases set aside this run (@@REPO_SKIPPED@@)
        self._remedy_skips: list[str] = []  # aliases to offer "Skip … & update the rest" for
        self._log_path: Path | None = None
        self._latest_tag = ""
        self._warn_repo_dup = False   # is the current warning a duplicate-repo one?
        self._warn_snapshots = False  # pre-flight: many Btrfs snapshots may be using disk
        self._snapshot_count = 0      # how many, for the banner text
        self._run_active = False      # is a full update run in flight? (guards the thin action)
        self._settings_dialog: SettingsDialog | None = None
        self._pending_autoupdate = False   # one-shot latch: an enable awaiting a fresh auth settle
        self._tray = None
        self._tray_timer = None
        self._tray_total = 0
        self._tray_checked_at = None
        self._tray_hint_shown = False
        self._local_server = None
        self._traycheck_proc = None
        self._traycheck_buf = ""
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()

        # Gradient ring: a 2px accent border (outer #Frame) around the card.
        outer_frame = QFrame()
        outer_frame.setObjectName("Frame")
        self.setCentralWidget(outer_frame)
        frame_lay = QVBoxLayout(outer_frame)
        frame_lay.setContentsMargins(2, 2, 2, 2)
        card = QFrame()
        card.setObjectName("Card")
        frame_lay.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # Header: title + tagline on the left; weekly-check + recenter on the right.
        header = QLabel(APP_NAME)
        header.setObjectName("Header")
        tagline = QLabel(f"Keep openSUSE, Flatpak and firmware up to date  ·  v{APP_VERSION}")
        tagline.setObjectName("Tagline")
        titleblock = QVBoxLayout()
        titleblock.setSpacing(2)
        titleblock.addWidget(header)
        titleblock.addWidget(tagline)

        self.auto_btn = QPushButton()
        self.auto_btn.setObjectName("GhostBtn")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setCursor(Qt.PointingHandCursor)
        self.auto_btn.setToolTip("Check weekly in the background and notify you when updates are ready")
        self.auto_btn.setChecked(self._autocheck_enabled())
        self._refresh_autocheck_label()
        self.auto_btn.toggled.connect(self.on_autocheck_toggled)

        # Opt-in "remember my authorization": stop prompting for the password on
        # every update. Off by default; the real state is probed from the engine
        # after the window is built (_query_auth_status).
        self.auth_btn = QPushButton()
        self.auth_btn.setObjectName("GhostBtn")
        self.auth_btn.setCheckable(True)
        self.auth_btn.setCursor(Qt.PointingHandCursor)
        self.auth_btn.setToolTip("Stop asking for your password on every update "
                                 "(opt-in; can be switched off to revoke instantly)")
        self._refresh_auth_label()
        self.auth_btn.toggled.connect(self.on_auth_toggled)

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

        # Laid out inside the Settings dialog (like the toggle buttons above), but
        # owned here so it persists across dialog opens.
        self.diag_btn = QPushButton("Copy diagnostics")
        self.diag_btn.setObjectName("GhostBtn")
        self.diag_btn.setCursor(Qt.PointingHandCursor)
        self.diag_btn.setToolTip("Copy version info and your latest update log to "
                                 "the clipboard, ready to paste into a bug report")
        self.diag_btn.clicked.connect(self.copy_diagnostics)

        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.setObjectName("GhostBtn")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setToolTip("Background behaviours: weekly check, "
                                     "passwordless, automatic updates")
        self.settings_btn.clicked.connect(self.open_settings)

        self.recenter_btn = QPushButton("Recenter")
        self.recenter_btn.setObjectName("GhostBtn")
        self.recenter_btn.setCursor(Qt.PointingHandCursor)
        self.recenter_btn.setToolTip("Move the window back to the centre of the screen")
        self.recenter_btn.clicked.connect(self.recenter)

        self.repos_btn = QPushButton("Repositories")
        self.repos_btn.setObjectName("GhostBtn")
        self.repos_btn.setCursor(Qt.PointingHandCursor)
        self.repos_btn.setToolTip("Turn software repositories on/off and clean up duplicates")
        self.repos_btn.clicked.connect(self.open_repos)

        self.about_btn = QPushButton("About")
        self.about_btn.setObjectName("GhostBtn")
        self.about_btn.setCursor(Qt.PointingHandCursor)
        self.about_btn.setToolTip("Version, licence, links and a manual update check")
        self.about_btn.clicked.connect(self.show_about)

        header_row = QHBoxLayout()
        header_row.addLayout(titleblock, 1)
        header_row.addWidget(self.settings_btn, 0, Qt.AlignTop)
        header_row.addWidget(self.repos_btn, 0, Qt.AlignTop)
        header_row.addWidget(self.recenter_btn, 0, Qt.AlignTop)
        header_row.addWidget(self.about_btn, 0, Qt.AlignTop)
        root.addLayout(header_row)
        root.addSpacing(2)

        # Task rows — each a gradient-bordered card.
        self.rows: dict[str, TaskRow] = {}
        for key, title, desc in TASKS:
            r = TaskRow(key, title, desc)
            r.size_requested.connect(self.request_size)
            self.rows[key] = r
            root.addWidget(r)

        root.addSpacing(4)

        # Action row: Check (secondary) + Run (primary).
        self.check_btn = QPushButton("Check for updates")
        self.check_btn.setObjectName("GhostBtn")
        self.check_btn.setCursor(Qt.PointingHandCursor)
        self.check_btn.setToolTip("See what would update — installs nothing")
        self.check_btn.clicked.connect(self.start_check)

        self.run_btn = QPushButton("Run selected updates")
        self.run_btn.setObjectName("RunBtn")
        self.run_btn.setMinimumHeight(44)
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(self.start_run)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self.check_btn, 0)
        actions.addWidget(self.run_btn, 1)
        root.addLayout(actions)

        # Retry-failed (hidden until a run has failures).
        self.retry_btn = QPushButton("Retry failed steps")
        self.retry_btn.setObjectName("GhostBtn")
        self.retry_btn.setCursor(Qt.PointingHandCursor)
        self.retry_btn.clicked.connect(self.retry_failed)
        self.retry_btn.setVisible(False)
        root.addWidget(self.retry_btn)

        # Progress + current step.
        self.status = QLabel("Ready.")
        self.status.setObjectName("Status")
        root.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        root.addWidget(self.bar)

        # Banners (all hidden until needed).
        self.reboot_banner, self.reboot_label, self.restart_btn = self._make_banner(
            "RebootBanner", "RestartBtn", "Restart now", self.restart_now)
        root.addWidget(self.reboot_banner)

        self.services_banner, self.services_label, self.services_btn = self._make_banner(
            "InfoBanner", "BannerBtn", "Restart services", self.restart_services)
        root.addWidget(self.services_banner)

        self.warn_banner, self.warn_label, self.warn_btn = self._make_banner(
            "WarnBanner", "BannerBtn", "Show details", self._warn_action)
        # A copy-the-suggested-command button, shown only when a hint carries a
        # runnable command the app couldn't run for you — the copy-fallback.
        self.warn_copy_btn = QPushButton("Copy command")
        self.warn_copy_btn.setObjectName("LinkBtn")
        self.warn_copy_btn.setCursor(Qt.PointingHandCursor)
        self.warn_copy_btn.setToolTip("Copy the suggested command to the clipboard")
        self.warn_copy_btn.clicked.connect(self._copy_hint_command)
        self.warn_copy_btn.setVisible(False)
        self.warn_banner.layout().insertWidget(1, self.warn_copy_btn)
        # A second action button, shown only when two remedies are armed at once (an
        # expired signing key on the culprit source: primary warn_btn offers "Skip
        # <source> & update the rest", this offers the alternative "Import signing
        # key & retry"). Hidden the rest of the time — the single-action path is
        # unchanged when only one remedy is armed.
        self.warn_btn2 = QPushButton("")
        self.warn_btn2.setObjectName("BannerBtn")
        self.warn_btn2.setCursor(Qt.PointingHandCursor)
        self.warn_btn2.clicked.connect(self._fix_keys_and_retry)
        self.warn_btn2.setVisible(False)
        self.warn_banner.layout().addWidget(self.warn_btn2)
        root.addWidget(self.warn_banner)

        self.appupdate_banner, self.appupdate_label, self.appupdate_btn = self._make_banner(
            "InfoBanner", "BannerBtn", "View release", self._open_release)
        root.addWidget(self.appupdate_banner)

        # Rollback link (shown after the system actually changed).
        self.rollback_btn = QPushButton("Roll back this update…")
        self.rollback_btn.setObjectName("LinkBtn")
        self.rollback_btn.setCursor(Qt.PointingHandCursor)
        self.rollback_btn.clicked.connect(self.rollback)
        self.rollback_btn.setVisible(False)
        root.addWidget(self.rollback_btn)

        # Log controls: show/hide on the left, open-file on the right.
        self.log_toggle = QPushButton("Show details ▸")
        self.log_toggle.setObjectName("LinkBtn")
        self.log_toggle.setCursor(Qt.PointingHandCursor)
        self.log_toggle.clicked.connect(self.toggle_log)
        self.openlog_btn = QPushButton("Open log file")
        self.openlog_btn.setObjectName("LinkBtn")
        self.openlog_btn.setCursor(Qt.PointingHandCursor)
        self.openlog_btn.clicked.connect(self.open_log)
        logrow = QHBoxLayout()
        logrow.addWidget(self.log_toggle, 0)
        logrow.addStretch(1)
        logrow.addWidget(self.openlog_btn, 0)
        root.addLayout(logrow)

        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Update details will appear here when you run an update.")
        self.log.setMinimumHeight(180)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.log, 1)

        # Restore the log show/hide preference (shown by default on first run).
        show_log = self.settings.value("log_shown", True, type=bool)
        self.log.setVisible(show_log)
        self.log_toggle.setText("Hide details ▾" if show_log else "Show details ▸")

        # Last-run line.
        self.last_run = QLabel()
        self.last_run.setObjectName("LastRun")
        root.addWidget(self.last_run)
        self.refresh_last_run()

        # Restore the last size + position, if we saved one before.
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

        # Non-blocking: is there a newer OneUp release?
        self._check_app_update()

        # Non-blocking: reflect whether passwordless authorization is active.
        self._query_auth_status()

    # ---- banner helper ----------------------------------------------------
    def _make_banner(self, frame_obj: str, btn_obj: str, btn_text: str, slot):
        fr = QFrame()
        fr.setObjectName(frame_obj)
        lay = QHBoxLayout(fr)
        lay.setContentsMargins(14, 10, 12, 10)
        lbl = QLabel("")
        lbl.setObjectName("BannerText")
        lbl.setWordWrap(True)
        btn = QPushButton(btn_text)
        btn.setObjectName(btn_obj)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(slot)
        lay.addWidget(lbl, 1)
        lay.addWidget(btn, 0)
        fr.setVisible(False)
        return fr, lbl, btn

    @staticmethod
    def _extract_command(hint: str) -> str:
        """Pull a runnable command out of a failure hint of the form
        '… run: <command>, then …'. Returns '' when the hint carries no command,
        so the Copy button only appears when there's actually something to copy."""
        marker = "run: "
        i = hint.find(marker)
        if i == -1:
            return ""
        rest = hint[i + len(marker):]
        cut = len(rest)
        for sep in (", then", ", or", ";"):   # the command ends at the first clause break
            j = rest.find(sep)
            if j != -1:
                cut = min(cut, j)
        return rest[:cut].strip().rstrip(".").strip()

    def _show_warning(self, text: str):
        """Show the warning banner with `text`, exposing a Copy button when the
        text contains a runnable command."""
        self.warn_label.setText("⚠  " + text)
        cmd = self._extract_command(text)
        self._hint_command = cmd
        self.warn_copy_btn.setVisible(bool(cmd))
        if cmd:
            self.warn_copy_btn.setText("Copy command")
        self.warn_banner.setVisible(True)

    def _copy_hint_command(self):
        if not self._hint_command:
            return
        QApplication.clipboard().setText(self._hint_command)
        self.warn_copy_btn.setText("Copied ✓")

    # ---- window geometry --------------------------------------------------
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

    def recenter(self):
        # On Wayland an app is not allowed to move itself — the compositor owns
        # window placement — so self.move() is silently ignored. We ask KWin to
        # do it via a one-shot script. On X11, the direct move works fine.
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            self._kwin_recenter()
        else:
            screen = self.screen() or QApplication.primaryScreen()
            if screen:
                frame = self.frameGeometry()
                frame.moveCenter(screen.availableGeometry().center())
                self.move(frame.topLeft())

    def _kwin_recenter(self):
        # Center via KWin scripting (Plasma 5 & 6). We match our own window by
        # PID and use workspace.PlacementArea for the usable screen rectangle —
        # the approach proven to work on this machine's KDE Wayland session.
        if not shutil.which("dbus-send"):
            return
        pid = os.getpid()
        kwin_js = f"""\
var clients = workspace.windowList();
for (var i = 0; i < clients.length; i++) {{
    var c = clients[i];
    if (c.pid === {pid}) {{
        var area = workspace.clientArea(workspace.PlacementArea, c);
        c.frameGeometry = {{
            x: area.x + Math.round((area.width - c.frameGeometry.width) / 2),
            y: area.y + Math.round((area.height - c.frameGeometry.height) / 2),
            width: c.frameGeometry.width,
            height: c.frameGeometry.height
        }};
        break;
    }}
}}
"""
        script_path = None
        name = "oneup_center"
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js",
                                             prefix="oneup_center_", delete=False) as f:
                script_path = f.name   # capture before write so a write error still cleans up
                f.write(kwin_js)
            base = ["dbus-send", "--session", "--dest=org.kde.KWin",
                    "--print-reply", "/Scripting"]
            subprocess.run(base + ["org.kde.kwin.Scripting.loadScript",
                                   f"string:{script_path}", f"string:{name}"],
                           capture_output=True, timeout=3)
            subprocess.run(base + ["org.kde.kwin.Scripting.start"],
                           capture_output=True, timeout=3)
            subprocess.run(base + ["org.kde.kwin.Scripting.unloadScript",
                                   f"string:{name}"],
                           capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            if script_path:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass

    # ---- weekly auto-check (systemd user timer) ---------------------------
    @staticmethod
    def _user_units_dir() -> Path:
        return Path.home() / ".config" / "systemd" / "user"

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
        self._traycheck_buf = ""
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self._on_traycheck_output)
        p.finished.connect(self._on_traycheck_finished)
        self._traycheck_proc = p
        p.start("bash", self._tray_check_args(self._traycheck_log()))

    def _traycheck_log(self):
        """One rolling log for the silent tray check, truncated each run (ONEUP-0024).
        A resident tray checks ~4x/day indefinitely; a per-run timestamped file would
        pile up. The engine's `tee -a` starts from the truncated file, so reusing one
        fixed name still overwrites (the output is silent, so no history is lost)."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / "traycheck.log"
        path.write_text("")   # roll: overwrite the previous check's output
        return path

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
        # Parent the menu to self: setContextMenu does not reparent it, and an
        # unparented QMenu can be garbage-collected out from under the tray icon.
        menu = QMenu(self)
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

    def _refresh_autocheck_label(self):
        on = self.auto_btn.isChecked()
        self.auto_btn.setText("Weekly check: on" if on else "Weekly check: off")

    def on_autocheck_toggled(self, on: bool):
        # Weekly-check behaviour is unchanged: install/remove and refresh the label.
        # It deliberately does NOT revert its toggle on a failed install (see the
        # ONEUP-0022 spec's "Open questions" — hardening weekly-check is a separate item).
        if on:
            self._install_user_timer("oneup-check", "OneUp weekly update check", "--check")
        else:
            self._remove_user_timer("oneup-check")
        self._refresh_autocheck_label()

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

    # ---- system-tray icon + start-at-boot (ONEUP-0018) ---------------------
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

    # ---- passwordless authorization (opt-in, ONEUP-0023) ------------------
    def _refresh_auth_label(self):
        on = self.auth_btn.isChecked()
        self.auth_btn.setText("Passwordless: on" if on else "Passwordless: off")

    def _set_auth_checked(self, on: bool):
        """Reflect the real state on the toggle WITHOUT re-triggering grant/revoke."""
        self.auth_btn.blockSignals(True)
        self.auth_btn.setChecked(on)
        self.auth_btn.blockSignals(False)
        self._refresh_auth_label()

    def _query_auth_status(self):
        """Probe the engine for whether the drop-in is active and set the toggle to
        match — so it always shows the truth, not a saved preference (which could
        drift if the rule were removed outside OneUp). Output is tiny, so it's read
        once on finish (no incremental slot that could fire after teardown)."""
        if not ENGINE.exists():
            return
        p = getattr(self, "_authstat_proc", None)
        if p is not None and p.state() != QProcess.NotRunning:
            return
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.finished.connect(lambda _c, _s, pr=p: self._on_auth_status_finished(pr))
        self._authstat_proc = p
        p.start("bash", [str(ENGINE), "--auth-status", f"--log={LOG_DIR / f'{stamp}.auth.log'}"])

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
        # Centre over the main window once laid out (mirrors show_about).
        QTimer.singleShot(0, lambda: self._center_child(box))
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

    def _run_auth(self, action: str, status_text: str):
        p = getattr(self, "_authchg_proc", None)
        if p is not None and p.state() != QProcess.NotRunning:
            return
        self.auth_btn.setEnabled(False)
        self.status.setText(status_text)
        self._settings_status(status_text)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.finished.connect(lambda _c, _s, pr=p: self._on_auth_finished(pr))
        self._authchg_proc = p
        p.start("bash", [str(ENGINE), action, f"--log={LOG_DIR / f'{stamp}.auth.log'}"])

    def _on_auth_finished(self, proc: QProcess):
        out = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        self.auth_btn.setEnabled(True)
        self.status.setText("Ready.")
        self._settings_status("")
        for line in out.splitlines():
            if line.startswith("@@HINT@@|"):
                QMessageBox.warning(self, "Couldn't change the setting",
                                    line.split("|", 1)[1])
        # Re-probe the real state rather than trusting the toggle: a cancelled
        # password prompt or a failure must leave the switch showing the truth.
        self._query_auth_status()

    # ---- last-run history -------------------------------------------------
    def refresh_last_run(self):
        stale = False
        try:
            data = json.loads(HISTORY.read_text())
            when = datetime.fromisoformat(data["when"])
            days = (datetime.now().date() - when.date()).days
            relative = ("today" if days <= 0 else
                        "yesterday" if days == 1 else f"{days} days ago")
            stale = days >= STALE_AFTER_DAYS
            self.last_run.setText(
                f"Last run: {when:%d %b %Y, %H:%M}  ·  {relative}  —  {data['status']}")
        except (OSError, ValueError, KeyError):
            self.last_run.setText("Last run: never")
        # Amber the line once a run is overdue: flip the dynamic property and
        # repolish so the QLabel#LastRun[stale="true"] stylesheet rule re-evaluates.
        self.last_run.setProperty("stale", "true" if stale else "false")
        self.last_run.style().unpolish(self.last_run)
        self.last_run.style().polish(self.last_run)

    def save_last_run(self, status: str):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY.write_text(
            json.dumps({"when": datetime.now().isoformat(timespec="seconds"), "status": status})
        )
        self.refresh_last_run()

    # ---- repositories -----------------------------------------------------
    def open_repos(self):
        """Open the repository manager (on/off switches + duplicate cleanup)."""
        repos = read_repos()
        if not repos:
            QMessageBox.information(
                self, "Repositories",
                "Couldn't read the repository list. Is zypper available?")
            return
        RepoManagerDialog(self, repos).exec()

    # ---- settings popup -----------------------------------------------------
    def open_settings(self):
        """Open (or re-raise) the Settings popup — created once so the three
        toggle buttons live in it permanently."""
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self)
        self.diag_btn.setText("Copy diagnostics")  # reset any lingering "Copied ✓"
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _settings_status(self, text: str):
        if self._settings_dialog is not None:
            self._settings_dialog.status.setText(text)

    def copy_diagnostics(self):
        """Bundle version info + the latest run log onto the clipboard for a bug
        report (the Settings dialog's 'Copy diagnostics' button)."""
        log = _latest_run_log(LOG_DIR)
        log_name = log_text = None
        if log is not None:
            log_name = log.name
            try:
                log_text = log.read_text(errors="replace")
            except OSError as e:
                log_text = f"(could not read {log.name}: {e})"
        report = build_diagnostics(
            APP_VERSION, _os_release_pretty(), self.selected_steps(),
            log_name, log_text, datetime.now().strftime("%Y-%m-%d %H:%M"),
            str(Path.home()), socket.gethostname())
        QApplication.clipboard().setText(report)
        self.diag_btn.setText("Copied ✓")
        self._settings_status("Diagnostics copied — paste them into your bug report.")

    def _warn_action(self):
        """The warning banner's button adapts to the warning: offer to skip a broken
        source, offer the one-click signing-key fix, open the repo manager for a
        duplicate, else show the log. When both a skip and a key-import remedy are
        armed (an expired key), skip is primary here and import stays reachable via
        warn_btn2 (see on_finished)."""
        if self._remedy_skips:
            self._skip_repo_and_retry()
        elif self._remedy_keys:
            self._fix_keys_and_retry()
        elif self._warn_repo_dup:
            self.open_repos()
        elif self._warn_snapshots:
            self._thin_snapshots()
        else:
            self._show_log()

    def _confirm_key_import(self) -> bool:
        """Warn about the trust decision before importing a repository signing key,
        and return whether the user approved."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Import the repository's signing key?")
        box.setText("Import the new signing key and retry the update?")
        box.setInformativeText(
            "A repository's signing key has changed or expired, which is why the "
            "update was refused.\n\n"
            "To continue, OneUp will import the repository's new key and run the "
            "update again. Importing a key means trusting it — only do this for "
            "repositories you set up and trust. A key you don't recognise could let "
            "unverified software be installed on your computer.")
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        box.button(QMessageBox.Ok).setText("Import && retry")
        box.setDefaultButton(QMessageBox.Cancel)
        # Centre over the main window once laid out (mirrors show_about).
        QTimer.singleShot(0, lambda: self._center_child(box))
        return box.exec() == QMessageBox.Ok

    def _fix_keys_and_retry(self):
        """Re-run the failed update with signing-key import enabled, after the user
        confirms the trust decision."""
        if not self._confirm_key_import():
            return
        steps = list(self._failed_steps) or ["system"]
        self._launch(steps, check=False, import_keys=True)

    def _repo_display_name(self, alias: str) -> str:
        """Resolve a repo alias to its human-readable name for the banner text;
        fall back to the raw alias if it can't be found (repo removed, zypper
        unavailable, …)."""
        for r in read_repos():
            if r.get("alias") == alias:
                return r.get("name") or alias
        return alias

    def _skip_repo_and_retry(self):
        """Re-run the failed steps with the flagged source(s) set aside for this run
        only — the engine re-enables them on exit (--skip-repo in update_system.sh)."""
        aliases = list(self._remedy_skips)
        if not aliases:
            return
        steps = list(self._failed_steps) or ["system"]
        self._launch(steps, check=False, skip_repos=aliases)

    def _thin_snapshots(self):
        """Thin accumulated Btrfs snapshots via the engine's guarded snapper cleanup
        (retention policy only — never a hand-picked delete), after the user confirms.
        Runs as its own privileged engine process so the recent rollback points stay."""
        p = getattr(self, "_thin_proc", None)
        if p is not None and p.state() != QProcess.NotRunning:
            return  # a thin is already in flight
        if self._run_active:
            QMessageBox.information(
                self, "Update in progress",
                "Let the current update finish, then thin the snapshots.")
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Thin old snapshots?")
        box.setText("Remove older system restore points to free disk space?")
        box.setInformativeText(
            "OneUp will ask Btrfs's snapshot tool (snapper) to clear out the older "
            "restore points its own retention policy considers expendable. Your most "
            "recent restore points are kept, so you can still roll back a bad update.")
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        box.button(QMessageBox.Ok).setText("Thin snapshots")
        box.setDefaultButton(QMessageBox.Cancel)
        QTimer.singleShot(0, lambda: self._center_child(box))
        if box.exec() != QMessageBox.Ok:
            return
        self.warn_btn.setEnabled(False)
        self.status.setText("Thinning snapshots… (approve the password popup)")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.finished.connect(lambda _c, _s, pr=p: self._on_thin_finished(pr))
        self._thin_proc = p
        p.start("bash", [str(ENGINE), "--thin-snapshots",
                         f"--log={LOG_DIR / f'{stamp}.thin.log'}"])

    def _on_thin_finished(self, proc: QProcess):
        """Report the outcome of a --thin-snapshots run and clear the advisory banner."""
        out = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        self.warn_btn.setEnabled(True)
        removed = None
        for line in out.splitlines():
            if line.startswith("@@SNAPSHOTS@@|thinned|"):
                n = line.split("|")[-1]
                removed = int(n) if n.isdigit() else None
            elif line.startswith("@@HINT@@|"):
                QMessageBox.warning(self, "Couldn't thin snapshots", line.split("|", 1)[1])
        if removed:
            self.status.setText(f"Thinned {removed} old snapshot(s).")
            self._warn_snapshots = False
            self.warn_banner.setVisible(False)
        elif removed == 0:
            self.status.setText("No old snapshots needed thinning.")
            self._warn_snapshots = False
            self.warn_banner.setVisible(False)
        else:
            # No marker (auth cancelled / error): leave the banner so it can be retried.
            self.status.setText("Ready.")

    # ---- log pane ---------------------------------------------------------
    def toggle_log(self):
        self._show_log(not self.log.isVisible())

    def _show_log(self, show: bool = True):
        self.log.setVisible(show)
        self.log_toggle.setText("Hide details ▾" if show else "Show details ▸")
        self.settings.setValue("log_shown", show)

    def open_log(self):
        if self._log_path and self._log_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._log_path)))
        else:
            QMessageBox.information(self, "No log yet",
                                    "Run an update or a check first — then the log opens here.")

    # ---- run / check ------------------------------------------------------
    def selected_steps(self) -> list[str]:
        return [key for key, _t, _d in TASKS if self.rows[key].switch.isChecked()]

    def set_controls_enabled(self, enabled: bool):
        self.run_btn.setEnabled(enabled)
        self.check_btn.setEnabled(enabled)
        for r in self.rows.values():
            r.switch.setEnabled(enabled)

    def start_check(self):
        self._launch(self.selected_steps(), check=True)

    def start_run(self):
        self._launch(self.selected_steps(), check=False)

    def retry_failed(self):
        if self._failed_steps:
            self._launch(list(self._failed_steps), check=False)

    def request_size(self, key: str):
        """Fetch the exact download size for a step on demand (system only). Runs
        the engine's --size mode, which authenticates and does a `zypper dup
        --dry-run`, so it stays out of the password-free --check path."""
        if key != "system" or not ENGINE.exists():
            return
        row = self.rows.get(key)
        if not row:
            return
        proc = getattr(self, "_size_proc", None)
        if proc is not None and proc.state() != QProcess.NotRunning:
            return  # a fetch is already in flight
        row.size_pending()
        self._size_buf = ""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        size_log = LOG_DIR / f"{stamp}.size.log"
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self._on_size_output)
        p.finished.connect(self._on_size_finished)
        self._size_proc = p
        p.start("bash", [str(ENGINE), f"--size={key}", f"--log={size_log}"])

    def _on_size_output(self):
        chunk = bytes(self._size_proc.readAllStandardOutput()).decode(errors="replace")
        self._size_buf = (self._size_buf + chunk).replace("\r\n", "\n").replace("\r", "\n")
        while "\n" in self._size_buf:
            line, self._size_buf = self._size_buf.split("\n", 1)
            if line.startswith("@@SIZE@@|"):
                parts = line[len("@@SIZE@@|"):].split("|")
                if len(parts) >= 2:
                    row = self.rows.get(parts[0])
                    if row:
                        row.set_size_result(f"↓ {parts[1]} to download")
            elif not line.startswith("@@"):
                self.log.appendPlainText(line)

    def _on_size_finished(self, exit_code: int, _status):
        row = self.rows.get("system")
        if not row or row.has_size():
            return
        # No SIZE marker arrived. Exit 0 = solver found nothing to fetch; non-zero
        # = auth cancelled or an error, so re-arm the link for a retry.
        if exit_code == 0:
            row.set_size_result("Nothing to download")
        else:
            row.size_failed()

    @staticmethod
    def _engine_args(steps: list[str], check: bool = False, import_keys: bool = False,
                      skip_repos: list[str] | None = None) -> list[str]:
        """Build the engine argv for the stable flags (steps/check/import_keys), plus
        one --skip-repo=<alias> per entry in skip_repos. `_launch` inserts --log=<path>
        into the result at call time — this helper doesn't know about the log path."""
        args = [str(ENGINE), f"--steps={','.join(steps)}"]
        if check:
            args.append("--check")
        elif import_keys:
            args.append("--import-keys")
        for alias in (skip_repos or []):
            args.append(f"--skip-repo={alias}")
        return args

    def _launch(self, steps: list[str], check: bool, import_keys: bool = False,
                skip_repos: list[str] | None = None):
        if not steps:
            QMessageBox.information(self, "Nothing selected",
                                    "Turn on at least one task first.")
            return
        if not ENGINE.exists():
            QMessageBox.critical(self, "Engine missing",
                                 f"Could not find the update script at:\n{ENGINE}")
            return

        # Reset per-run state and any banners/badges from a previous run.
        self._check_mode = check
        self._reboot = False
        self._reboot_reason = ""
        self._installed_count = ""
        self._sys_changed = False
        self._failed_steps = []
        self._services = ""
        self._snapshot = ""
        self._snapshots = []
        self._hints = []
        self._skipped_repos = []
        self._buf = ""
        self._total = len(steps)
        for b in (self.reboot_banner, self.services_banner, self.warn_banner):
            b.setVisible(False)
        # Reset the warning banner's button back to its default "Show details" role
        # (a previous run may have switched it to the repo-manager action).
        self._warn_repo_dup = False
        self._warn_snapshots = False
        self.warn_btn.setText("Show details")
        self.warn_btn.setEnabled(True)
        self._hint_command = ""
        self._remedy_keys = False
        self._remedy_skips = []
        self._run_active = not check   # a real run guards the standalone thin action
        self.warn_copy_btn.setVisible(False)
        self.warn_btn2.setVisible(False)
        self.retry_btn.setVisible(False)
        self.rollback_btn.setVisible(False)
        for r in self.rows.values():
            r.clear_badge()
            r.clear_details()
        self.log.clear()

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self._log_path = LOG_DIR / (f"{stamp}.check.log" if check else f"{stamp}.log")

        if check:
            self.bar.setRange(0, 0)  # indeterminate
            self.bar.setFormat("Checking…")
            self.status.setText("Checking for available updates…")
        else:
            self.bar.setRange(0, self._total)
            self.bar.setValue(0)
            self.bar.setFormat("Starting…")
            self.status.setText("Authenticating… (approve the password popup)")
        self.set_controls_enabled(False)

        args = self._engine_args(steps, check, import_keys, skip_repos)
        args.insert(2, f"--log={self._log_path}")  # after --steps, before --check/etc.
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.on_output)
        self.proc.finished.connect(self.on_finished)
        self.proc.errorOccurred.connect(self.on_error)
        self.proc.start("bash", args)

    def on_output(self):
        chunk = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        # Normalise carriage returns to newlines on the ACCUMULATED buffer (so a CRLF
        # straddling two read chunks doesn't become a spurious blank line) — this keeps
        # a tool's \r progress output from prepending text to a marker and hiding it.
        self._buf = (self._buf + chunk).replace("\r\n", "\n").replace("\r", "\n")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.handle_line(line)

    def handle_line(self, line: str):
        if line.startswith("@@"):
            self.handle_marker(line)
            return
        self.log.appendPlainText(line)

    @staticmethod
    def _step_badge(status: str, detail: str) -> str:
        """A short per-row badge for a finished step, from its @@STEP_END@@ status +
        detail — e.g. '3 installed', 'Up to date', 'Updated', 'Failed', 'Skipped'."""
        if status == "fail":
            return "Failed"
        if status == "skip":
            return "Not installed" if "not installed" in detail.lower() else "Skipped"
        d = detail.lower()
        if any(w in d for w in ("up to date", "already", "nothing")):
            return "Up to date"
        m = re.search(r"\d+", detail)
        if m:
            return f"{m.group()} removed" if "remov" in d else f"{m.group()} installed"
        if any(w in d for w in ("applied", "updated", "update")):
            return "Updated"
        return "Done"

    @staticmethod
    def _format_duration(secs: int) -> str:
        """A compact human duration: '<1s', '42s', '1m 5s'."""
        if secs < 1:
            return "<1s"
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m {secs % 60}s"

    def handle_marker(self, line: str):
        try:
            tag, rest = line[2:].split("@@|", 1)
        except ValueError:
            # A line that starts with @@ but isn't a real marker (e.g. a diff hunk
            # header "@@ -1,4 +1,4 @@") is ordinary output — log it, don't drop it.
            self.log.appendPlainText(line)
            return
        parts = rest.split("|")
        if tag == "STEP_BEGIN":
            # Guard the fixed 4-field unpack + int(): the engine's output is merged
            # stdout+stderr, so a marker line can be spliced by interleaved text. A
            # malformed STEP_BEGIN must never throw out of the QProcess read slot —
            # that would abort parsing and drop the run's later markers.
            if len(parts) < 4 or not parts[1].isdigit():
                return
            _key, index, total, label = parts[0], parts[1], parts[2], parts[3]
            self.status.setText(f"{label}…")
            self.bar.setFormat(f"{label}  (step {index} of {total})")
            self.bar.setValue(int(index) - 1)
        elif tag == "STEP_END":
            # Clamp: a duplicate/orphaned STEP_END (markers can be spliced) must not
            # push the bar past the run's total step count.
            self.bar.setValue(min(self.bar.value() + 1, self._total))
            key = parts[0]
            status = parts[1] if len(parts) >= 2 else ""
            detail = parts[2] if len(parts) >= 3 else ""
            # Badge the task row with what actually happened (mirrors the "N available"
            # badge --check shows, but for a real run: "3 installed", "Up to date", …).
            row = self.rows.get(key)
            if row:
                row.set_badge(self._step_badge(status, detail))
            if status == "fail":
                self._failed_steps.append(key)
        elif tag == "TIMING":
            # How long the step took, appended to its row badge ("3 installed · 42s").
            key = parts[0]
            secs = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            row = self.rows.get(key)
            if row:
                row.set_timing(self._format_duration(secs))
        elif tag == "FREED":
            # Disk the cache clean reclaimed, shown as the cache row's badge
            # ("Reclaimed 1.4G  ·  <1s"). Emitted after STEP_END, so it replaces
            # the generic "Done" badge the step-end set.
            key = parts[0]
            human = parts[1] if len(parts) > 1 else ""
            row = self.rows.get(key)
            if row and human:
                row.set_badge(f"Reclaimed {human}")
        elif tag == "CHECK":
            key, count = parts[0], (parts[1] if len(parts) > 1 else "0")
            if key == "TOTAL":
                self._installed_count = count
            else:
                row = self.rows.get(key)
                if row:
                    n = int(count) if count.isdigit() else 0
                    row.set_badge(f"{n} available" if n > 0 else "up to date")
        elif tag == "CHECK_ITEM":
            # One changed package for the expandable preview: key|name|from|to.
            if len(parts) >= 2:
                row = self.rows.get(parts[0])
                if row:
                    frm = parts[2] if len(parts) > 2 else ""
                    to = parts[3] if len(parts) > 3 else ""
                    row.add_detail_item(parts[1], frm, to)
        elif tag == "INSTALLED":
            self._installed_count = parts[0]
            self._sys_changed = len(parts) > 1 and parts[1] == "yes"
        elif tag == "SNAPSHOT":
            self._snapshot = parts[0]
        elif tag == "SNAPSHOT_ITEM":
            # One recent restore point for the rollback picker: id|date|description.
            # Keep only well-formed numeric ids (the id is later interpolated into a
            # root `snapper rollback`, so a spliced non-numeric payload must never
            # be captured). Oldest→newest as the engine emits them.
            if parts and parts[0].isdigit():
                date = parts[1] if len(parts) > 1 else ""
                desc = parts[2] if len(parts) > 2 else ""
                self._snapshots.append((parts[0], date, desc))
        elif tag == "SERVICES":
            self._services = rest.strip()
        elif tag == "HINT":
            self._hints.append(rest.strip())
        elif tag == "REPO_SKIPPED":
            # A source was set aside for this run (disabled, upgrade ran, will be
            # re-enabled by the engine on exit — see --skip-repo/--auto-skip-repos).
            if parts:
                alias = parts[0]
                self._skipped_repos.append(alias)
                self.log.appendPlainText(f"  Set aside this run: {alias} (will retry next time)")
        elif tag == "REMEDY":
            # The engine says a one-click fix is available for this run's failure:
            # "import-keys" (a rotated/expired repo signing key) and/or "skip-repo"
            # (a single broken source — offer to set it aside and update the rest).
            # Armed here; the warn banner offers them in on_finished, the key-import
            # one behind a confirmation.
            if parts and parts[0] == "import-keys":
                self._remedy_keys = True
            elif parts and parts[0] == "skip-repo" and len(parts) >= 2:
                self._remedy_skips.append(parts[1])
        elif tag == "REBOOT":
            self._reboot = parts[0] == "yes"
            # Optional field: a plain-English reason naming what makes the reboot
            # matter (a new kernel, graphics driver, …). Absent for a plain reboot.
            self._reboot_reason = parts[1] if len(parts) > 1 else ""
        elif tag == "SNAPSHOTS" and parts and parts[0] == "warn":
            # Pre-flight: a lot of Btrfs restore points have piled up and may be using
            # disk. Offer a one-click thin (snapper's own retention cleanup) via the
            # warn banner. The "thinned|N" variant comes from the dedicated
            # --thin-snapshots process and is read in _on_thin_finished, not here.
            self._snapshot_count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            self._warn_snapshots = True
            self.warn_btn.setText("Thin snapshots…")
            self._show_warning(
                f"{self._snapshot_count} system restore points (snapshots) are stored. "
                "On Tumbleweed these build up with each update and can use a lot of disk "
                "space — you can safely thin the older ones.")
        elif tag in ("DISK", "REPO"):
            # Pre-flight warnings (low disk / duplicate repos). Surface immediately so
            # the advertised warning is visible during the run, not buried in the log.
            if tag == "DISK" and len(parts) >= 3:
                msg = f"Low disk space on {parts[1]} — only {parts[2]} free. Updating may fail."
            elif tag == "REPO":
                # parts: warn|duplicate|<space-joined urls>. Name the culprit(s) and
                # point the banner's button at the repo manager to fix it in-app.
                urls = parts[2].strip() if len(parts) >= 3 else ""
                if urls:
                    msg = (f"Duplicate repository URL(s): {urls}. Open Repositories to "
                           "turn off or remove the extra copy.")
                else:
                    msg = "Duplicate repository URLs detected — a common cause of update conflicts."
                self._warn_repo_dup = True
                self.warn_btn.setText("Manage repositories…")
            else:
                msg = "Pre-flight warning — see the log for details."
            self._show_warning(msg)
        # @@DONE@@ is intentionally not handled here — the run's overall result comes
        # from the process exit code in on_finished (the two always agree).

    def on_error(self, _err):
        self.status.setText("Could not start the update script.")
        self.bar.setRange(0, 1)
        self.set_controls_enabled(True)
        # Release the process object on a start failure too (finished never fires here).
        self.proc.deleteLater()

    def _notify_when_away(self, body: str, urgency: str = "normal"):
        """Fire a desktop notification for a finished run, but only when the window
        isn't focused — you started an update and tabbed away, so tell you it's done.
        Best-effort: skipped if notify-send is absent (like the engine's own hint)."""
        if self.isActiveWindow() or not shutil.which("notify-send"):
            return
        try:
            subprocess.Popen(  # noqa: S603,S607 — fixed argv, no shell.
                ["notify-send", "-a", APP_NAME, "-i", APP_ID, "-u", urgency, APP_NAME, body],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def on_finished(self, exit_code: int, _status):
        # Flush any final line the engine emitted without a trailing newline before
        # computing the summary, so a last marker can't be silently dropped.
        if self._buf.strip():
            self.handle_line(self._buf)
        self._buf = ""
        self._run_active = False
        # Release the finished process so QProcess instances don't accumulate on the
        # window across a long session (each run parents a new one to self).
        self.proc.deleteLater()
        ok = exit_code == 0
        self.set_controls_enabled(True)

        if self._check_mode:
            self.bar.setRange(0, 1)
            self.bar.setValue(1)
            self.bar.setFormat("Check complete")
            n = self._installed_count
            total = int(n) if n.isdigit() else 0
            self.status.setText(
                f"{total} update(s) available — turn on what you want and hit Run."
                if total else "Everything is up to date. 🎉")
            self._notify_when_away(
                f"{total} update(s) available." if total else "Everything is up to date.")
            self._apply_tray_total(total)
            self._check_mode = False
            return

        self.bar.setValue(self._total)
        self.bar.setFormat("Finished" if ok else "Finished with errors")

        n = self._installed_count
        if n and n not in ("", "0"):
            installed = f"{n} update(s) installed"
        elif self._sys_changed:
            installed = "updates installed"
        elif "system" in self.selected_steps():
            installed = "already up to date"
        else:
            installed = "finished"
        self.status.setText(f"All done — {installed}." if ok
                            else "Finished — some steps had errors (see details).")
        self.save_last_run("OK" if ok else "errors")

        # Reboot vs the lighter "just restart these services" path.
        if self._reboot:
            if self._reboot_reason:
                # Name what triggered it, e.g. "A new kernel and your NVIDIA graphics
                # driver were installed — restart …". Capitalise the first letter only
                # (str.capitalize() would lower-case "NVIDIA").
                r = self._reboot_reason
                self.reboot_label.setText(
                    f"⚠  {r[0].upper()}{r[1:]} — restart so everything uses the latest version.")
            elif n and n not in ("", "0"):
                self.reboot_label.setText(
                    f"⚠  {n} update(s) installed — restart so everything uses the latest libraries.")
            else:
                self.reboot_label.setText(
                    "⚠  Updates were installed — a restart is recommended so everything "
                    "uses the latest libraries.")
            self.reboot_banner.setVisible(True)
        elif self._services:
            count = len(self._services.split())
            self.services_label.setText(
                f"No reboot needed — but {count} service(s) should restart to use the new libraries.")
            self.services_btn.setToolTip(self._services)
            self.services_banner.setVisible(True)

        # Rollback offer once the system actually changed.
        if self._sys_changed and self._snapshot:
            self.rollback_btn.setVisible(True)

        # Surface the first plain-English failure hint, if any (with a Copy button
        # when it carries a command the app couldn't run for you) — OR, when a
        # remedy is armed with no accompanying hint (a corrupt-metadata source
        # failure arms @@REMEDY@@|skip-repo with no @@HINT@@), a GUI-built
        # fallback naming the culprit(s) so the skip/import action is never a
        # dead end behind an invisible banner.
        if self._hints or self._remedy_skips or self._remedy_keys:
            if self._hints:
                self._show_warning(self._hints[0])
            elif self._remedy_skips:
                names = ", ".join(self._repo_display_name(a) for a in self._remedy_skips)
                if len(self._remedy_skips) == 1:
                    self._show_warning(
                        f"{names} is failing — skip it and update everything else, "
                        "or check the log.")
                else:
                    self._show_warning(
                        f"These sources are failing: {names} — skip them and update "
                        "everything else, or check the log.")
            else:
                self._show_warning("A repository signing key is out of date.")
            # When a one-click remedy is available, the banner button offers it
            # (behind a warned confirmation for the key import) rather than just
            # showing the log. A skip remedy takes the primary button; when a
            # key-import remedy is ALSO armed (an expired key: both a skip and a
            # real fix exist), it gets a genuine second button rather than being
            # dropped, since a single button can't offer two actions.
            both_armed = bool(self._remedy_skips) and self._remedy_keys
            if self._remedy_skips:
                if len(self._remedy_skips) == 1:
                    self.warn_btn.setText(
                        f"Skip {self._repo_display_name(self._remedy_skips[0])} & update the rest")
                else:
                    self.warn_btn.setText(
                        f"Skip {len(self._remedy_skips)} sources & update the rest")
            elif self._remedy_keys:
                self.warn_btn.setText("Import signing key & retry")
            if both_armed:
                self.warn_btn2.setText("Import signing key & retry")
                self.warn_btn2.setVisible(True)

        if self._failed_steps:
            self.retry_btn.setVisible(True)
        if not ok:
            self._show_log(True)

        # Tell the user a run they walked away from has finished.
        self._notify_when_away(
            f"All done — {installed}." if ok else "Finished — some steps had errors.",
            urgency="normal" if ok else "critical")

        # Keep the ambient tray icon honest: a clean run just installed updates.
        if ok:
            self._apply_tray_total(0)

    # ---- actions ----------------------------------------------------------
    def restart_now(self):
        if QMessageBox.question(self, "Restart now?",
                                "Save your work first. Restart the computer now?") \
                == QMessageBox.Yes:
            QProcess.startDetached("systemctl", ["reboot"])

    def restart_services(self):
        # _services is sourced from an @@SERVICES@@ marker on the merged output stream,
        # so keep only well-formed unit names: a spliced token (e.g. a leading-dash
        # option) must not reach the root `systemctl` as an argument. Mirrors the
        # snapshot-id guard in rollback().
        svcs = [s for s in self._services.split()
                if not s.startswith("-")
                and re.fullmatch(r"[A-Za-z0-9:@._\\-]+\.[a-z]+", s)]
        if not svcs:
            return
        if QMessageBox.question(
                self, "Restart services?",
                "Restart these services now?\n\n" + ", ".join(svcs)) == QMessageBox.Yes:
            QProcess.startDetached("pkexec", ["systemctl", "restart", *svcs])
            self.services_banner.setVisible(False)

    def rollback(self):
        # The rollback target defaults to the pre-update snapshot, but when the
        # engine enumerated recent restore points (@@SNAPSHOT_ITEM@@) the user can
        # pick an older one — e.g. to undo a problem that started two updates ago
        # (ONEUP-0020). Both the picker and the guard below re-check the id is a
        # bare number: it is interpolated into a root shell, so a spliced
        # non-numeric payload must never reach it. (isdigit() also covers empty.)
        target = self._snapshot
        if self._snapshots:
            dlg = RollbackDialog(self, self._snapshots, self._snapshot)
            if dlg.exec() != QDialog.Accepted:
                return
            target = dlg.selected_id()
        if not target.isdigit():
            return
        answer = QMessageBox.warning(
            self, "Roll back this update?",
            f"This restores the system to restore point #{target} and then "
            "REBOOTS. Anything changed since that snapshot will be lost."
            "\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            QProcess.startDetached(
                "pkexec", ["sh", "-c",
                           f"snapper rollback {target} && systemctl reboot"])

    # ---- About dialog -----------------------------------------------------
    def show_about(self):
        """A small About window: version, licence, links, and a manual update check."""
        box = QMessageBox(self)
        box.setWindowTitle(f"About {APP_NAME}")
        icon = _app_icon()
        if not icon.isNull():
            box.setIconPixmap(icon.pixmap(64, 64))
        box.setTextFormat(Qt.RichText)
        box.setText(f"<b>{APP_NAME} {APP_VERSION}</b>")
        box.setInformativeText(
            "One-click updates for openSUSE — system packages, Flatpaks, firmware, "
            "leftover-package removal and cache cleanup.<br><br>"
            "Released under the <b>MIT Licence</b>.<br><br>"
            f'<a href="https://github.com/{REPO_SLUG}">GitHub repository</a> &nbsp;·&nbsp; '
            '<a href="https://software.opensuse.org/package/oneup">openSUSE package (OBS)</a>')
        for lbl in box.findChildren(QLabel):
            lbl.setOpenExternalLinks(True)  # let the links open in the browser.
        check_btn = box.addButton("Check for updates", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        # Centre over the main window once it's laid out (a QMessageBox sizes to its
        # content on show, so we re-position from inside the event loop).
        QTimer.singleShot(0, lambda: self._center_child(box))
        box.exec()
        if box.clickedButton() is check_btn:
            self._check_app_update(manual=True)

    def _center_child(self, widget):
        """Move a child popup so its centre sits over the main window's centre."""
        fg = widget.frameGeometry()
        fg.moveCenter(self.frameGeometry().center())
        widget.move(fg.topLeft())

    # ---- self-update check ------------------------------------------------
    def _check_app_update(self, manual: bool = False):
        # manual=True (the About dialog's button) reports the result either way;
        # the automatic startup check stays silent unless a newer release exists.
        self._manual_update_check = manual
        self._nam = QNetworkAccessManager(self)
        req = QNetworkRequest(QUrl(f"https://api.github.com/repos/{REPO_SLUG}/releases/latest"))
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        self._nam.finished.connect(self._on_app_update_reply)
        self._nam.get(req)

    def _on_app_update_reply(self, reply: QNetworkReply):
        manual = getattr(self, "_manual_update_check", False)
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                if manual:
                    QMessageBox.warning(self, "Check for updates",
                                        "Couldn't reach GitHub to check for a newer OneUp.")
                return
            data = json.loads(bytes(reply.readAll()).decode(errors="replace"))
            tag = str(data.get("tag_name", "")).lstrip("vV")
            if tag and _version_tuple(tag) > _version_tuple(APP_VERSION):
                self._latest_tag = tag
                self.appupdate_label.setText(
                    f"A newer OneUp ({tag}) is available — you have {APP_VERSION}.")
                self.appupdate_banner.setVisible(True)
                if manual:
                    QMessageBox.information(self, "Check for updates",
                                            f"A newer OneUp ({tag}) is available — "
                                            f"you have {APP_VERSION}.")
            elif manual:
                QMessageBox.information(self, "Check for updates",
                                        f"You're on the latest version ({APP_VERSION}).")
        except (ValueError, KeyError, AttributeError, TypeError):
            # ValueError/KeyError: bad JSON / missing key; AttributeError/TypeError:
            # a non-object JSON body (list, string, null) has no .get(). A flaky
            # update check must never throw out of this network slot.
            if manual:
                QMessageBox.warning(self, "Check for updates",
                                    "Couldn't read GitHub's reply while checking for updates.")
        finally:
            reply.deleteLater()

    def _open_release(self):
        QDesktopServices.openUrl(QUrl(f"https://github.com/{REPO_SLUG}/releases/latest"))


def _app_icon() -> QIcon:
    """Prefer the installed theme icon (set once the .desktop/icon are in place,
    and inside a package); fall back to the bundled asset when running from a
    git checkout."""
    icon = QIcon.fromTheme(APP_ID)
    if icon.isNull():
        asset = HERE / "data" / f"{APP_ID}.svg"
        if asset.exists():
            icon = QIcon(str(asset))
    return icon


def _headless_check() -> int:
    """`oneup --check`: run the engine's read-only check + notification, no GUI.
    This is what the optional weekly systemd-user timer invokes."""
    if not ENGINE.exists():
        print(f"OneUp: update script not found at {ENGINE}", file=sys.stderr)
        return 1
    return subprocess.run(["bash", str(ENGINE), "--check", "--notify"]).returncode


def _headless_update() -> int:
    """`oneup --update`: run the FULL engine + its end-of-run notification, no GUI.
    This is what the optional weekly systemd-user UPDATE timer invokes. `--update`
    is a GUI-only token — the engine is run with just --notify (its default STEPS is
    every step) and is NEVER handed --update (its arg parser would reject it).
    Also passes --auto-skip-repos (additive): an unattended run should set a single
    broken software source aside and finish the rest, not fail the whole update."""
    if not ENGINE.exists():
        print(f"OneUp: update script not found at {ENGINE}", file=sys.stderr)
        return 1
    return subprocess.run(["bash", str(ENGINE), "--notify", "--auto-skip-repos"]).returncode


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


def main():
    if "--check" in sys.argv[1:]:
        sys.exit(_headless_check())
    if "--update" in sys.argv[1:]:
        sys.exit(_headless_update())

    app = QApplication([])
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)  # ties the window to its .desktop/icon

    def apply_theme():
        app.setStyleSheet(build_theme(current_is_dark(app)))

    apply_theme()
    try:  # re-theme live when the desktop switches light/dark (Qt 6.5+)
        app.styleHints().colorSchemeChanged.connect(lambda *_: apply_theme())
    except (AttributeError, TypeError):
        pass

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


if __name__ == "__main__":
    main()
