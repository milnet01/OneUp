"""The popup that hosts the background-behaviour toggles.

A host, not an owner: every button it lays out is built and owned by the
window, and re-parented here on the first open. It gets a module of its own
because it is a dialog with a `showEvent`, not because it owns the settings.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .placement import center_on_parent
from .theme import card_inside


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
        root.addWidget(self._row(
            "Make all text bigger. OneUp already follows your desktop's font size — "
            "this enlarges it further.", parent.textsize_btn))
        root.addWidget(self._row(
            "Switch to high-contrast colours: plain black and white with strong "
            "outlines, for easier reading.", parent.contrast_btn))
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
        lay = QHBoxLayout(card_inside(fr))
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
        center_on_parent(self)
