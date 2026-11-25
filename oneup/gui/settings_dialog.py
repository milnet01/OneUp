"""The Settings popup: three tabs of the controls the window owns.

A host, not an owner: every control it lays out is built and owned by the
window, and re-parented here on the first open. It gets a module of its own
because it is a dialog with a `showEvent`, not because it owns the settings.

Also two small helpers the window's dialogs share: the button strip along a
dialog's foot, and setting a hosted switch without firing its handler.
"""
from __future__ import annotations

import itertools

import shiboken6
from PySide6.QtCore import QCoreApplication, QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from .placement import center_on_parent
from .theme import card_inside


def set_quietly(button, on: bool) -> None:
    """Show `on` on a switch WITHOUT running its toggled handler — the reflect every
    setting uses when it reports the machine's real state. The caller then refreshes
    the switch's label, which the handler would otherwise have done."""
    button.blockSignals(True)
    button.setChecked(on)
    button.blockSignals(False)


def button_strip(*buttons: QWidget) -> QFrame:
    """A dialog's row of buttons, pushed to the right, for the bottom of its layout.

    Named so the focus derivation can tell a button strip resting on `win` from one
    nested in a row card; a strip is otherwise the one surface with no container of
    its own to qualify on. Every dialog builds its strip here, so the name holds."""
    strip = QFrame()
    strip.setObjectName("DialogButtons")
    row = QHBoxLayout(strip)
    row.setContentsMargins(0, 0, 0, 0)
    row.addStretch(1)
    for button in buttons:
        row.addWidget(button)
    return strip


class _RowsScroll(QScrollArea):
    """Asks for its rows' whole height at its own width. QScrollArea caps its
    hint at 24 lines of text, so the dialog opened scrolling on a screen with
    room for every row. Qt still holds a new window to two thirds of the screen."""

    def sizeHint(self) -> QSize:
        rows = self.widget()
        width = self.viewport().width() if self.isVisible() else rows.sizeHint().width()
        return QSize(rows.sizeHint().width(), rows.heightForWidth(width))


class SettingsDialog(QDialog):
    """Groups OneUp's settings in tabs behind one popup, modelled on
    RepoManagerDialog. The toggle buttons and their handlers stay owned by the
    Updater window; this dialog only lays them out. It is created once, so the
    buttons live here permanently after the first open."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(QCoreApplication.translate("settings_dialog", "Settings"))
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        intro = QLabel(QCoreApplication.translate(
            "settings_dialog",
            "How OneUp behaves on its own, how it looks, and what it does on "
            "this machine."))
        intro.setWordWrap(True)
        root.addWidget(intro)

        # One tab per group, each a page of its own (ONEUP-0303). The grouping is
        # exhaustive over every row: a row with no home here is a defect in this
        # list rather than a judgement call (ONEUP-0064 §4.1, which drew the
        # groups as headings). A plain tab bar over a stack rather than a
        # QTabWidget, whose tab bar is its focus proxy: two widgets answering for
        # one stop.
        self.tabs = QTabBar()
        self.tabs.setObjectName("SettingsTabs")
        self.tabs.setAccessibleName(QCoreApplication.translate(
            "settings_dialog", "Settings sections"))
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.pages = QStackedWidget()
        self._scrolls: list[_RowsScroll] = []
        self._controls: list[QWidget] = []     # every row's control, in layout order
        self.tabs.currentChanged.connect(self.pages.setCurrentIndex)
        root.addWidget(self.tabs)
        root.addWidget(self.pages, 1)
        # Qt does not scroll a control into view when Tab arrives from outside
        # its page — from the tabs or Close — so the dialog does.
        QApplication.instance().focusChanged.connect(self._on_focus)
        self._automatic_page(parent)
        self._appearance_page(parent)
        self._machine_page(parent)
        # A page taller than its rows keeps them at the top, at their own height.
        for scroll in self._scrolls:
            scroll.widget().layout().addStretch(1)
        self.status = QLabel("")
        self.status.setObjectName("Tagline")
        root.addWidget(self.status)
        self.close_btn = QPushButton(QCoreApplication.translate("settings_dialog", "Close"))
        self.close_btn.setObjectName("GhostBtn")
        self.close_btn.clicked.connect(self.reject)
        root.addWidget(button_strip(self.close_btn))

        # A QDialog has its own focus chain — Qt's is per top-level widget, so
        # the window's chain can never reach in here and this half has to be
        # stated on its own.
        for a, b in itertools.pairwise(self.focus_chain()):
            self.setTabOrder(a, b)

    def _automatic_page(self, parent) -> None:
        _tray_note = ("" if parent._tray_available else QCoreApplication.translate(
            "settings_dialog", "  (your desktop has no system tray)"))
        body = self._page(QCoreApplication.translate(
            "settings_dialog",
            "Automatic behaviour"))
        body.addWidget(self._row(
            QCoreApplication.translate(
                "settings_dialog",
                "Check weekly in the background and notify you when updates are "
                "ready."),
            parent.auto_btn))
        if parent._service_route:
            # A service install has no switch to offer: who may update is this
            # computer's permission, the one Discover uses (ONEUP-0249 §4.10).
            self.service_note = QLabel(QCoreApplication.translate(
                "settings_dialog",
                "Updates follow this computer's software-update permission, the same "
                "one Discover uses, so OneUp has no password setting of its own."))
            self.service_note.setWordWrap(True)
            body.addWidget(self.service_note)
            autoupdate_text = QCoreApplication.translate(
                "settings_dialog",
                "Install all updates automatically on a weekly schedule. Needs this "
                "computer to allow updates without a password, and keeps the "
                "snapshot/rollback safety net.")
        else:
            body.addWidget(self._row(
                QCoreApplication.translate(
                    "settings_dialog",
                    "Skip the password prompt for OneUp's update commands (opt-in; "
                    "you can switch it off to revoke instantly)."), parent.auth_btn))
            autoupdate_text = QCoreApplication.translate(
                "settings_dialog",
                "Install all updates automatically on a weekly schedule. Needs "
                "the passwordless setting, and keeps the snapshot/rollback safety "
                "net.")
        body.addWidget(self._row(autoupdate_text, parent.autoupdate_btn))
        body.addWidget(self._row(QCoreApplication.translate(
            "settings_dialog",
            "Show a small icon near the clock that turns amber when updates are "
            "waiting.{note}").format(note=_tray_note), parent.tray_btn))
        body.addWidget(self._row(QCoreApplication.translate(
            "settings_dialog",
            "Start OneUp automatically at login, hidden in the tray.{note}").format(
                note=_tray_note), parent.startboot_btn))
        body.addWidget(self._row(QCoreApplication.translate(
            "settings_dialog",
            "Ask GitHub whether a newer OneUp exists each time OneUp starts. "
            "Check for updates in About works either way."), parent.appcheck_btn))

    def _appearance_page(self, parent) -> None:
        body = self._page(QCoreApplication.translate("settings_dialog", "Appearance"))
        self._appearance_tab = self.tabs.count() - 1
        body.addWidget(self._row(
            QCoreApplication.translate(
                "settings_dialog",
                "Colour scheme for the whole app. Follow system uses your "
                "desktop's light or dark setting; the rest are fixed."), parent.theme_combo))
        # Only shown when a theme could not be applied — a control that silently
        # does nothing is the one outcome ui-and-accessibility.md §7 forbids.
        parent._show_theme_error()
        body.addWidget(parent.theme_note)
        body.addWidget(self._row(
            QCoreApplication.translate(
                "settings_dialog",
                "How the main window is arranged. Changing it keeps whatever is "
                "running."), parent.layout_btn))
        body.addWidget(self._row(
            QCoreApplication.translate(
                "settings_dialog",
                "Make all text bigger. OneUp already follows your desktop's font "
                "size — this enlarges it further."), parent.textsize_btn))
        body.addWidget(self._row(
            QCoreApplication.translate(
                "settings_dialog",
                "Switch to high-contrast colours: plain black and white with "
                "strong outlines, for easier reading."), parent.contrast_btn))

    def _machine_page(self, parent) -> None:
        # Each row carries its own description: `_row` does not read a tooltip.
        body = self._page(QCoreApplication.translate(
            "settings_dialog",
            "This machine"))
        body.addWidget(self._row(
            QCoreApplication.translate(
                "settings_dialog",
                "Choose which software sources OneUp updates from."), parent.repos_btn))
        body.addWidget(self._row(
            QCoreApplication.translate(
                "settings_dialog",
                "Copy a bug report — version info plus your latest update log — "
                "to the clipboard, so filing an issue doesn't mean hunting "
                "through hidden folders."),
            parent.diag_btn))
        body.addWidget(self._row(
            QCoreApplication.translate(
                "settings_dialog",
                "Delete OneUp's update logs once they are this old. The log of "
                "your latest update is always kept."),
            parent.logkeep_btn))

    def focus_chain(self) -> list[QWidget]:
        """This dialog's controls, in the order the pages lay them out — `_row`
        records each — between the tabs and Close. Tab passes over the controls of
        the pages not showing, as Qt skips any hidden widget."""
        return [self.tabs, *self._controls, self.close_btn]

    def _page(self, title: str) -> QVBoxLayout:
        """Add a tab and its page, and return the layout its rows go into.

        Each page scrolls (ONEUP-0302): a dialog taller than the screen is
        squeezed to fit it, and the layout took the difference out of every row,
        so a 960-pixel screen cut three-line descriptions to two."""
        scroll = _RowsScroll()
        scroll.setObjectName("SettingsScroll")
        # Not a stop of its own, its controls are — as MessageStrip.
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("SettingsBody")
        body = QVBoxLayout(inner)
        body.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(inner)
        self.pages.addWidget(scroll)
        self.tabs.addTab(title)
        self._scrolls.append(scroll)
        return body

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
        self._controls.append(control)
        return fr

    def _on_focus(self, _old, new) -> None:
        if new is None or not shiboken6.isValid(self):
            return
        for scroll in self._scrolls:
            if scroll.widget().isAncestorOf(new):
                scroll.ensureWidgetVisible(new)

    def showEvent(self, event):
        # Centre over the main window each time it opens (mirrors RepoManagerDialog).
        super().showEvent(event)
        # The picker is where a theme that failed to apply is reported
        # (ui-and-accessibility.md §7), so Settings opens on its tab rather than
        # leaving the message out of sight.
        if not self.parent().theme_note.isHidden():
            self.tabs.setCurrentIndex(self._appearance_tab)
        center_on_parent(self)
