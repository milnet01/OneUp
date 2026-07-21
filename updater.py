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
import subprocess
import sys
import tempfile
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
    QUrl,
)
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

APP_ID = "za.co.antsprojectshub.OneUp"
APP_NAME = "OneUp"
APP_VERSION = "1.0.1"
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

# key, title, one-line description. Order = run order.
TASKS = [
    ("system", "System packages", "Refresh repositories and upgrade openSUSE (zypper dup)."),
    ("flatpak", "Flatpak apps", "Update Flatpak apps and remove unused runtimes."),
    ("firmware", "Firmware", "Check for and apply device firmware updates (fwupd)."),
    ("orphans", "Leftover packages", "Remove leftover dependency packages nothing needs."),
    ("cache", "Package cache", "Clear the downloaded-package cache to free disk space."),
]

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
    logbd="#262d38", status="#c3ccd9", lastrun="#828d9d", progbg="#0c0f13",
    ghostbd="#38414f", ghostfg="#c7d0dd", disbg="#262b34", disfg="#aeb7c4",
    tip="#1a1f27", tipfg="#e9edf3",
)
_LIGHT = dict(
    win="#eef1f5", card="#ffffff", header="#1b2027", tag="#5c6673",
    rowcard="#f4f6f9", rowhov="#eaeef3", tname="#1b2027", tdesc="#5c6673",
    badgebg="#dbe8ff", badgefg="#1f4e9c", logbg="#f6f8fa", logfg="#2a2f36",
    logbd="#d5dbe2", status="#3a424d", lastrun="#8a94a2", progbg="#dfe4ea",
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
    badge on the right shows how many updates a --check found."""

    def __init__(self, title: str, description: str):
        super().__init__()
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

        inner = QFrame()
        inner.setObjectName("RowCard")
        row = QHBoxLayout(inner)
        row.setContentsMargins(15, 12, 15, 12)
        row.setSpacing(10)
        row.addLayout(text, 1)
        row.addWidget(self.badge, 0, Qt.AlignVCenter)
        row.addWidget(self.switch, 0, Qt.AlignVCenter)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)  # 1px gradient border
        outer.addWidget(inner)

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


class Updater(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumWidth(560)
        self.settings = QSettings("OneUp", "OneUp")
        self.proc: QProcess | None = None
        self._buf = ""
        self._total = 0
        self._check_mode = False
        self._reboot = False
        self._installed_count = ""   # system packages changed, as reported by the engine
        self._sys_changed = False
        self._failed_steps: list[str] = []
        self._services = ""
        self._snapshot = ""
        self._hints: list[str] = []
        self._log_path: Path | None = None
        self._latest_tag = ""

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

        self.recenter_btn = QPushButton("Recenter")
        self.recenter_btn.setObjectName("GhostBtn")
        self.recenter_btn.setCursor(Qt.PointingHandCursor)
        self.recenter_btn.setToolTip("Move the window back to the centre of the screen")
        self.recenter_btn.clicked.connect(self.recenter)

        self.about_btn = QPushButton("About")
        self.about_btn.setObjectName("GhostBtn")
        self.about_btn.setCursor(Qt.PointingHandCursor)
        self.about_btn.setToolTip("Version, licence, links and a manual update check")
        self.about_btn.clicked.connect(self.show_about)

        header_row = QHBoxLayout()
        header_row.addLayout(titleblock, 1)
        header_row.addWidget(self.auto_btn, 0, Qt.AlignTop)
        header_row.addWidget(self.recenter_btn, 0, Qt.AlignTop)
        header_row.addWidget(self.about_btn, 0, Qt.AlignTop)
        root.addLayout(header_row)
        root.addSpacing(2)

        # Task rows — each a gradient-bordered card.
        self.rows: dict[str, TaskRow] = {}
        for key, title, desc in TASKS:
            r = TaskRow(title, desc)
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
            "WarnBanner", "BannerBtn", "Show details", self._show_log)
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

    # ---- window geometry --------------------------------------------------
    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)

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
    def _autocheck_command() -> str:
        """A stable command that re-launches OneUp in headless --check mode.
        Each path is quoted (for spaces) and any '%' is doubled: systemd treats '%'
        as a specifier prefix inside ExecStart= even within quotes, so an unescaped
        '%' in an install path would silently corrupt or fail the unit."""
        def _arg(p) -> str:
            # systemd does C-unescaping plus env-var ($FOO) and specifier (%x) expansion
            # inside double quotes, so escape all four — backslash first, then quote,
            # then dollar and percent — before wrapping the path in quotes.
            s = str(p).replace("\\", "\\\\").replace('"', '\\"')
            s = s.replace("$", "$$").replace("%", "%%")
            return '"' + s + '"'
        appimage = os.environ.get("APPIMAGE")
        if appimage:
            return f"{_arg(appimage)} --check"
        launcher = shutil.which("oneup")
        if launcher:
            return f"{_arg(launcher)} --check"
        return f"{_arg(sys.executable)} {_arg(Path(__file__).resolve())} --check"

    def _autocheck_enabled(self) -> bool:
        r = subprocess.run(["systemctl", "--user", "is-enabled", "oneup-check.timer"],
                           capture_output=True, text=True)
        return r.stdout.strip() == "enabled"

    def _refresh_autocheck_label(self):
        on = self.auto_btn.isChecked()
        self.auto_btn.setText("Weekly check: on" if on else "Weekly check: off")

    def on_autocheck_toggled(self, on: bool):
        units = self._user_units_dir()
        try:
            if on:
                units.mkdir(parents=True, exist_ok=True)
                (units / "oneup-check.service").write_text(
                    "[Unit]\nDescription=OneUp weekly update check\n\n"
                    "[Service]\nType=oneshot\n"
                    f"ExecStart={self._autocheck_command()}\n"
                )
                (units / "oneup-check.timer").write_text(
                    "[Unit]\nDescription=OneUp weekly update check\n\n"
                    "[Timer]\nOnCalendar=weekly\nPersistent=true\n\n"
                    "[Install]\nWantedBy=timers.target\n"
                )
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
                subprocess.run(["systemctl", "--user", "enable", "--now",
                                "oneup-check.timer"], check=False)
            else:
                subprocess.run(["systemctl", "--user", "disable", "--now",
                                "oneup-check.timer"], check=False)
                for name in ("oneup-check.timer", "oneup-check.service"):
                    try:
                        (units / name).unlink()
                    except OSError:
                        pass
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        except OSError as exc:
            QMessageBox.warning(self, "Could not change the schedule", str(exc))
        self._refresh_autocheck_label()

    # ---- last-run history -------------------------------------------------
    def refresh_last_run(self):
        try:
            data = json.loads(HISTORY.read_text())
            when = datetime.fromisoformat(data["when"]).strftime("%d %b %Y, %H:%M")
            self.last_run.setText(f"Last run: {when}  —  {data['status']}")
        except (OSError, ValueError, KeyError):
            self.last_run.setText("Last run: never")

    def save_last_run(self, status: str):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY.write_text(
            json.dumps({"when": datetime.now().isoformat(timespec="seconds"), "status": status})
        )
        self.refresh_last_run()

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

    def _launch(self, steps: list[str], check: bool):
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
        self._installed_count = ""
        self._sys_changed = False
        self._failed_steps = []
        self._services = ""
        self._snapshot = ""
        self._hints = []
        self._buf = ""
        self._total = len(steps)
        for b in (self.reboot_banner, self.services_banner, self.warn_banner):
            b.setVisible(False)
        self.retry_btn.setVisible(False)
        self.rollback_btn.setVisible(False)
        for r in self.rows.values():
            r.clear_badge()
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

        args = [str(ENGINE), f"--steps={','.join(steps)}", f"--log={self._log_path}"]
        if check:
            args.append("--check")
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
        elif tag == "CHECK":
            key, count = parts[0], (parts[1] if len(parts) > 1 else "0")
            if key == "TOTAL":
                self._installed_count = count
            else:
                row = self.rows.get(key)
                if row:
                    n = int(count) if count.isdigit() else 0
                    row.set_badge(f"{n} available" if n > 0 else "up to date")
        elif tag == "INSTALLED":
            self._installed_count = parts[0]
            self._sys_changed = len(parts) > 1 and parts[1] == "yes"
        elif tag == "SNAPSHOT":
            self._snapshot = parts[0]
        elif tag == "SERVICES":
            self._services = rest.strip()
        elif tag == "HINT":
            self._hints.append(rest.strip())
        elif tag == "REBOOT":
            self._reboot = parts[0] == "yes"
        elif tag in ("DISK", "REPO"):
            # Pre-flight warnings (low disk / duplicate repos). Surface immediately so
            # the advertised warning is visible during the run, not buried in the log.
            if tag == "DISK" and len(parts) >= 3:
                msg = f"Low disk space on {parts[1]} — only {parts[2]} free. Updating may fail."
            elif tag == "REPO":
                msg = "Duplicate repository URLs detected — a common cause of update conflicts."
            else:
                msg = "Pre-flight warning — see the log for details."
            self.warn_label.setText("⚠  " + msg)
            self.warn_banner.setVisible(True)
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
            if n and n not in ("", "0"):
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

        # Surface the first plain-English failure hint, if any.
        if self._hints:
            self.warn_label.setText("⚠  " + self._hints[0])
            self.warn_banner.setVisible(True)

        if self._failed_steps:
            self.retry_btn.setVisible(True)
        if not ok:
            self._show_log(True)

        # Tell the user a run they walked away from has finished.
        self._notify_when_away(
            f"All done — {installed}." if ok else "Finished — some steps had errors.",
            urgency="normal" if ok else "critical")

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
        # _snapshot is taken verbatim from an @@SNAPSHOT@@ marker on the merged output
        # stream, so validate it is a bare snapshot number before it reaches the root
        # shell below — a spliced non-numeric payload must never be interpolated into
        # the pkexec command line. (isdigit() also covers the empty/unset case.)
        if not self._snapshot.isdigit():
            return
        answer = QMessageBox.warning(
            self, "Roll back this update?",
            "This restores the system to the snapshot taken before the update "
            f"(#{self._snapshot}) and then REBOOTS. Anything changed since the "
            "update will be lost.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            QProcess.startDetached(
                "pkexec", ["sh", "-c",
                           f"snapper rollback {self._snapshot} && systemctl reboot"])

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
        box.exec()
        if box.clickedButton() is check_btn:
            self._check_app_update(manual=True)

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


def main():
    if "--check" in sys.argv[1:]:
        sys.exit(_headless_check())

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

    icon = _app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    win = Updater()
    if not icon.isNull():
        win.setWindowIcon(icon)
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
