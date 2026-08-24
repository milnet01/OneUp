"""The popup that hosts the background-behaviour toggles.

A host, not an owner: every button it lays out is built and owned by the
window, and re-parented here on the first open. It gets a module of its own
because it is a dialog with a `showEvent`, not because it owns the settings.
"""
from __future__ import annotations

import itertools

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
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
        # The old intro said "Each is off until you turn it on", which is true of
        # the first heading's five toggles and false of the other two headings'
        # rows — the same defect the original had once the groups existed.
        intro = QLabel("How OneUp behaves on its own, how it looks, and what it "
                       "does on this machine.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        # Three headings rather than a flat column of ghost buttons. The grouping
        # is exhaustive over every row: a row with no home here is a defect in
        # this list rather than a judgement call (ONEUP-0064 §4.1).
        _tray_note = "" if parent._tray_available else "  (your desktop has no system tray)"
        root.addWidget(self._heading("Automatic behaviour"))
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
        root.addWidget(self._row(
            "Show a small icon near the clock that turns amber when updates are waiting."
            + _tray_note, parent.tray_btn))
        root.addWidget(self._row(
            "Start OneUp automatically at login, hidden in the tray." + _tray_note,
            parent.startboot_btn))

        root.addWidget(self._heading("Appearance"))
        root.addWidget(self._row(
            "Colour scheme for the whole app. Follow system uses your desktop's "
            "light or dark setting; the rest are fixed.", parent.theme_combo))
        # Only shown when a theme could not be applied — a control that silently
        # does nothing is the one outcome ui-and-accessibility.md §7 forbids.
        parent._show_theme_error()
        root.addWidget(parent.theme_note)
        root.addWidget(self._row(
            "Make all text bigger. OneUp already follows your desktop's font size — "
            "this enlarges it further.", parent.textsize_btn))
        root.addWidget(self._row(
            "Switch to high-contrast colours: plain black and white with strong "
            "outlines, for easier reading.", parent.contrast_btn))

        # Repositories and Recenter arrive here from the header. `_row` takes a
        # description per row and does not read a tooltip, so both need one.
        root.addWidget(self._heading("This machine"))
        root.addWidget(self._row(
            "Choose which software sources OneUp updates from.", parent.repos_btn))
        root.addWidget(self._row(
            "Put the window back in the middle of the screen.", parent.recenter_btn))
        root.addWidget(self._row(
            "Copy a bug report — version info plus your latest update log — to the "
            "clipboard, so filing an issue doesn't mean hunting through hidden folders.",
            parent.diag_btn))
        self.status = QLabel("")
        self.status.setObjectName("Tagline")
        root.addWidget(self.status)
        # Named so the focus derivation can tell a button strip resting on `win`
        # from one nested in a row card; a strip is otherwise the one surface
        # with no container of its own to qualify on.
        strip = QFrame()
        strip.setObjectName("DialogButtons")
        btns = QHBoxLayout(strip)
        btns.setContentsMargins(0, 0, 0, 0)
        btns.addStretch(1)
        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("GhostBtn")
        self.close_btn.clicked.connect(self.reject)
        btns.addWidget(self.close_btn)
        root.addWidget(strip)

        # A QDialog has its own focus chain — Qt's is per top-level widget, so
        # the window's chain can never reach in here and this half has to be
        # stated on its own.
        for a, b in itertools.pairwise(self.focus_chain()):
            self.setTabOrder(a, b)

    def focus_chain(self) -> list[QWidget]:
        """This dialog's controls, in the order the headings lay them out."""
        p = self.parent()
        return [p.auto_btn, p.auth_btn, p.autoupdate_btn, p.tray_btn, p.startboot_btn,
                p.theme_combo, p.textsize_btn, p.contrast_btn,
                p.repos_btn, p.recenter_btn, p.diag_btn, self.close_btn]

    def _heading(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("GroupHeading")
        return lbl

    def _row(self, description: str, control: QWidget) -> QFrame:
        fr = QFrame()
        fr.setObjectName("RowBorder")
        lay = QHBoxLayout(card_inside(fr))
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)
        lbl = QLabel(description)
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)
        lay.addWidget(control, 0, Qt.AlignVCenter)
        return fr

    def showEvent(self, event):
        # Centre over the main window each time it opens (mirrors RepoManagerDialog).
        super().showEvent(event)
        center_on_parent(self)
