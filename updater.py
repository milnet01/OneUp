#!/usr/bin/env python3
"""OneUp — a small Qt dashboard over update_system.sh.

The dashboard is a thin front-end: it never runs as root and contains no update
logic of its own. It shells out to the update_system.sh script that sits next to
it with a --steps list, reads that script's @@MARKER@@ progress lines to drive the
progress bar and per-step status, and shows the rest of the output in a log pane.
Each task has a phone-style on/off switch (green = on, red = off) instead of a
checkbox.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QProcess,
    QPropertyAnimation,
    QRectF,
    QSettings,
    Qt,
)
from PySide6.QtGui import QColor, QIcon, QPainter
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
    QWidget,
)

APP_ID = "za.co.antsprojectshub.OneUp"
APP_NAME = "OneUp"
HERE = Path(__file__).resolve().parent


def _find_engine() -> Path:
    """Locate update_system.sh. It normally sits next to this file (git checkout
    or Flatpak install); fall back to the legacy ~/Documents path so an existing
    hand-installed setup keeps working."""
    for candidate in (HERE / "update_system.sh",
                      Path.home() / "Documents" / "update_system.sh"):
        if candidate.exists():
            return candidate
    return HERE / "update_system.sh"  # default; start_run() warns if it's missing


ENGINE = _find_engine()
STATE_DIR = Path.home() / ".local" / "state" / "oneup"
HISTORY = STATE_DIR / "history.json"

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
# Theme — a dark "instrument panel". The signature is the azure→cyan gradient
# (echoing the app icon) used as a ring around the window and as a hover-lit
# border on each task card. Everything else stays quiet so the borders carry
# the personality. Selectors are keyed to object names so system dialogs
# (QMessageBox etc.) keep the desktop's native look.
# ---------------------------------------------------------------------------
ACCENT = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4aa3ff, stop:1 #22d3ee)"
THEME = f"""
* {{ font-family: "Inter", "Noto Sans", "Segoe UI", "Cantarell", sans-serif; }}
QMainWindow {{ background: #0f1216; }}

#Frame {{ border-radius: 16px; background: {ACCENT}; }}
#Card  {{ border-radius: 14px; background: #12161c; }}

QLabel#Header  {{ font-size: 21px; font-weight: 700; color: #f4f7fb; }}
QLabel#Tagline {{ font-size: 12px; color: #8b95a5; }}

#RowBorder {{
    border-radius: 12px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(74,163,255,0.65), stop:1 rgba(34,211,238,0.50));
}}
#RowBorder:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(104,184,255,1.0), stop:1 rgba(58,228,250,0.85));
}}
#RowCard {{ border-radius: 11px; background: #1a1f27; }}
#RowBorder:hover #RowCard {{ background: #1e242e; }}
QLabel#TaskName {{ font-size: 14px; font-weight: 600; color: #eef2f8; }}
QLabel#TaskDesc {{ font-size: 12px; color: #a7b0be; }}

QPushButton#RunBtn {{
    font-size: 14px; font-weight: 700; color: #ffffff; border: none;
    border-radius: 11px; padding: 12px 18px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4aa3ff, stop:1 #2f6fe0);
}}
QPushButton#RunBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5cb0ff, stop:1 #3a7cf0);
}}
QPushButton#RunBtn:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3d90ec, stop:1 #2560c8);
}}
QPushButton#RunBtn:disabled {{ color: #aeb7c4; background: #262b34; }}

QPushButton#GhostBtn {{
    color: #c7d0dd; font-weight: 600; background: transparent;
    border: 1px solid #38414f; border-radius: 8px; padding: 5px 13px;
}}
QPushButton#GhostBtn:hover {{ border-color: #4aa3ff; color: #eaf1fb; }}

QPushButton#LinkBtn {{
    color: #7fb2ff; font-weight: 600; text-align: left;
    background: transparent; border: none; padding: 4px 2px;
}}
QPushButton#LinkBtn:hover {{ color: #a9ccff; }}

QLabel#Status  {{ font-size: 12px; color: #c3ccd9; }}
QLabel#LastRun {{ font-size: 12px; color: #828d9d; }}

QProgressBar {{
    border: none; border-radius: 9px; background: #0c0f13;
    min-height: 20px; text-align: center; color: #dbe3ee; font-size: 12px;
}}
QProgressBar::chunk {{ border-radius: 9px; background: {ACCENT}; }}

QPlainTextEdit#Log {{
    background: #0b0e12; color: #cdd6e2;
    border: 1px solid #262d38; border-radius: 10px; padding: 6px;
    font-family: "JetBrains Mono", "Fira Code", "Noto Sans Mono", monospace; font-size: 11px;
}}

#RebootBanner {{
    border: 1px solid #e0553f; border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(231,76,60,0.22), stop:1 rgba(231,76,60,0.05));
}}
QLabel#RebootText {{ color: #ffb4a6; font-weight: 600; border: none; background: transparent; }}
QPushButton#RestartBtn {{
    color: #ffffff; font-weight: 700; border: none; border-radius: 8px; padding: 7px 15px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ef6a55, stop:1 #d6412a);
}}
QPushButton#RestartBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f47c68, stop:1 #e04a32);
}}

QToolTip {{
    background: #1a1f27; color: #e9edf3; border: 1px solid #4aa3ff;
    border-radius: 4px; padding: 4px 6px;
}}
"""


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
    outer frame shows the accent gradient, an inner card sits 1px inside it."""

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

        inner = QFrame()
        inner.setObjectName("RowCard")
        row = QHBoxLayout(inner)
        row.setContentsMargins(15, 12, 15, 12)
        row.setSpacing(12)
        row.addLayout(text, 1)
        row.addWidget(self.switch, 0, Qt.AlignVCenter)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)  # 1px gradient border
        outer.addWidget(inner)


class Updater(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(520)
        self.settings = QSettings("OneUp", "OneUp")
        self.proc: QProcess | None = None
        self._buf = ""
        self._total = 0
        self._reboot = False
        self._installed_count = ""   # system packages changed, as reported by the engine
        self._sys_changed = False

        # Gradient ring: a 2px accent border (outer #Frame) around the dark card.
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

        # Header: title + tagline on the left, Recenter on the right.
        header = QLabel(APP_NAME)
        header.setObjectName("Header")
        tagline = QLabel("Keep openSUSE, Flatpak and firmware up to date")
        tagline.setObjectName("Tagline")
        titleblock = QVBoxLayout()
        titleblock.setSpacing(2)
        titleblock.addWidget(header)
        titleblock.addWidget(tagline)

        self.recenter_btn = QPushButton("Recenter")
        self.recenter_btn.setObjectName("GhostBtn")
        self.recenter_btn.setCursor(Qt.PointingHandCursor)
        self.recenter_btn.setToolTip("Move the window back to the centre of the screen")
        self.recenter_btn.clicked.connect(self.recenter)

        header_row = QHBoxLayout()
        header_row.addLayout(titleblock, 1)
        header_row.addWidget(self.recenter_btn, 0, Qt.AlignTop)
        root.addLayout(header_row)
        root.addSpacing(2)

        # Task rows — each a gradient-bordered card.
        self.rows: dict[str, TaskRow] = {}
        for key, title, desc in TASKS:
            r = TaskRow(title, desc)
            self.rows[key] = r
            root.addWidget(r)

        root.addSpacing(4)

        # Primary action.
        self.run_btn = QPushButton("Run selected updates")
        self.run_btn.setObjectName("RunBtn")
        self.run_btn.setMinimumHeight(44)
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(self.start_run)
        root.addWidget(self.run_btn)

        # Progress + current step.
        self.status = QLabel("Ready.")
        self.status.setObjectName("Status")
        root.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        root.addWidget(self.bar)

        # Reboot banner (hidden until needed).
        self.reboot_banner = QFrame()
        self.reboot_banner.setObjectName("RebootBanner")
        rb = QHBoxLayout(self.reboot_banner)
        rb.setContentsMargins(14, 10, 12, 10)
        self.reboot_label = QLabel("⚠  A restart is recommended to finish updating.")
        self.reboot_label.setObjectName("RebootText")
        self.reboot_label.setWordWrap(True)
        self.restart_btn = QPushButton("Restart now")
        self.restart_btn.setObjectName("RestartBtn")
        self.restart_btn.setCursor(Qt.PointingHandCursor)
        self.restart_btn.clicked.connect(self.restart_now)
        rb.addWidget(self.reboot_label, 1)
        rb.addWidget(self.restart_btn, 0)
        self.reboot_banner.setVisible(False)
        root.addWidget(self.reboot_banner)

        # Collapsible log pane.
        self.log_toggle = QPushButton("Show details ▸")
        self.log_toggle.setObjectName("LinkBtn")
        self.log_toggle.setCursor(Qt.PointingHandCursor)
        self.log_toggle.clicked.connect(self.toggle_log)
        root.addWidget(self.log_toggle)

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
        name = "system_updater_center"
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js",
                                             prefix="su_center_", delete=False) as f:
                f.write(kwin_js)
                script_path = f.name
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
        show = not self.log.isVisible()
        self.log.setVisible(show)
        self.log_toggle.setText("Hide details ▾" if show else "Show details ▸")
        self.settings.setValue("log_shown", show)

    # ---- run --------------------------------------------------------------
    def selected_steps(self) -> list[str]:
        return [key for key, _t, _d in TASKS if self.rows[key].switch.isChecked()]

    def set_controls_enabled(self, enabled: bool):
        self.run_btn.setEnabled(enabled)
        for r in self.rows.values():
            r.switch.setEnabled(enabled)

    def start_run(self):
        steps = self.selected_steps()
        if not steps:
            QMessageBox.information(self, "Nothing selected",
                                    "Turn on at least one task before running.")
            return
        if not ENGINE.exists():
            QMessageBox.critical(self, "Engine missing",
                                 f"Could not find the update script at:\n{ENGINE}")
            return

        self.reboot_banner.setVisible(False)
        self._reboot = False
        self._installed_count = ""
        self._sys_changed = False
        self._buf = ""
        self._total = len(steps)
        self.log.clear()
        self.bar.setRange(0, self._total)
        self.bar.setValue(0)
        self.bar.setFormat("Starting…")
        self.status.setText("Authenticating… (approve the password popup)")
        self.set_controls_enabled(False)

        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.on_output)
        self.proc.finished.connect(self.on_finished)
        self.proc.errorOccurred.connect(self.on_error)
        self.proc.start("bash", [str(ENGINE), f"--steps={','.join(steps)}"])

    def on_output(self):
        self._buf += bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.handle_line(line)

    def handle_line(self, line: str):
        if line.startswith("@@"):
            self.handle_marker(line)
            return
        self.log.appendPlainText(line)

    def handle_marker(self, line: str):
        try:
            tag, rest = line[2:].split("@@|", 1)
        except ValueError:
            return
        parts = rest.split("|")
        if tag == "STEP_BEGIN":
            _key, index, total, label = parts[0], parts[1], parts[2], parts[3]
            self.status.setText(f"{label}…")
            self.bar.setFormat(f"{label}  (step {index} of {total})")
            self.bar.setValue(int(index) - 1)
        elif tag == "STEP_END":
            self.bar.setValue(self.bar.value() + 1)
        elif tag == "INSTALLED":
            # parts: count | sys_changed(yes/no) | fw_changed(yes/no)
            self._installed_count = parts[0]
            self._sys_changed = len(parts) > 1 and parts[1] == "yes"
        elif tag == "REBOOT":
            self._reboot = parts[0] == "yes"
        elif tag == "DONE":
            self._done_status = parts[0]

    def on_error(self, _err):
        self.status.setText("Could not start the update script.")
        self.set_controls_enabled(True)

    def on_finished(self, exit_code: int, _status):
        self.bar.setValue(self._total)
        ok = exit_code == 0
        self.bar.setFormat("Finished" if ok else "Finished with errors")

        # Describe whether anything was installed (drives reboot advice).
        n = self._installed_count
        if n and n not in ("", "0"):
            installed = f"{n} update(s) installed"
        elif self._sys_changed:
            installed = "updates installed"
        elif "system" in self.selected_steps():
            installed = "already up to date"
        else:
            installed = "finished"
        if ok:
            self.status.setText(f"All done — {installed}.")
        else:
            self.status.setText("Finished — some steps had errors (see details).")

        self.save_last_run("OK" if ok else "errors")
        self.set_controls_enabled(True)
        if self._reboot:
            if n and n not in ("", "0"):
                self.reboot_label.setText(
                    f"⚠  {n} update(s) installed — restart so everything uses the latest libraries."
                )
            else:
                self.reboot_label.setText(
                    "⚠  Updates were installed — a restart is recommended so everything "
                    "uses the latest libraries."
                )
            self.reboot_banner.setVisible(True)
        if not ok:
            self.log.setVisible(True)
            self.log_toggle.setText("Hide details ▾")

    def restart_now(self):
        if QMessageBox.question(self, "Restart now?",
                                "Save your work first. Restart the computer now?") \
                == QMessageBox.Yes:
            QProcess.startDetached("systemctl", ["reboot"])


def _app_icon() -> QIcon:
    """Prefer the installed theme icon (set once the .desktop/icon are in place,
    and inside the Flatpak); fall back to the bundled asset when running straight
    from a git checkout."""
    icon = QIcon.fromTheme(APP_ID)
    if icon.isNull():
        asset = HERE / "data" / f"{APP_ID}.svg"
        if asset.exists():
            icon = QIcon(str(asset))
    return icon


def main():
    app = QApplication([])
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)  # ties the window to its .desktop/icon
    app.setStyleSheet(THEME)
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
