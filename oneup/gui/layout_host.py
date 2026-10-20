"""What the three window layouts share (ONEUP-0239 §4.1).

A layout is a host, not an owner — `SettingsDialog`'s idiom applied to the
window's body. Every control and every piece of run state belongs to the window;
a layout re-parents the shared controls into its own arrangement, builds a
package page of its own, and gives back every model callback it took before the
window deletes it. That is what lets a layout change mid-run keep the badges, the
progress and the messages: none of them lives here.

Nothing here imports the window module (`docs/specs/ONEUP-0034-gui-modules.md`
§4.3 rule 2); the window is handed in as `win`.
"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from . import details_dialog, package_views, steps

# The buttons inside the message strip, in the order its banners stack and each
# banner lays them out. Layout order does NOT set the focus chain — parenting
# order does — so every host states it from this list (ONEUP-0064).
BANNER_BUTTONS = ("restart_btn", "services_btn", "warn_copy_btn", "warn_btn", "warn_btn2",
                  "retry_btn", "appupdate_btn")

# The log holds at least this many of its own lines.
LOG_LINES = 6


class LayoutHost(QWidget):
    """The base every layout shares. A subclass builds its arrangement in its own
    `__init__`, fills `self.page`, and keeps its views current in `refresh`."""

    LAYOUT_ID = ""
    FORM = "full"
    # The package view's floor, in the view's own rows (§4.2 item 2).
    PACKAGE_ROWS = 3

    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self.page = QWidget()       # this layout's page of the package area
        self._listening = []
        self.bodies: list[package_views.EmptyOr] = []
        for key, _t, _d in steps.TASKS:
            win.rows[key].set_form(self.FORM)

    # --- the package model ------------------------------------------------------

    def listen(self) -> None:
        self.win.packages.subscribe(self._on_model)
        self._listening.append(self._on_model)
        # About lands in the details store, not the model: its own subscription
        # is what redraws the marks (ONEUP-0260 §4.2).
        self.win.details.subscribe(self._on_details)

    def release(self) -> None:
        """Give back every callback this layout took. The window calls it before
        deleting the layout, or the next marker calls into a deleted widget from
        inside `handle_marker`, which must never raise."""
        for callback in self._listening:
            self.win.packages.unsubscribe(callback)
        self._listening.clear()
        self.win.details.unsubscribe(self._on_details)

    def _on_model(self, _key) -> None:
        self.refresh()

    def _on_details(self) -> None:
        self.refresh()

    def opens_details(self, view, items: package_views.PackageItems) -> None:
        """Activating a package with details opens its dialog; one without does
        nothing. `activated` follows the desktop's click setting and fires on
        Enter, so mouse and keyboard reach it alike (ONEUP-0260 §4.5)."""
        def open_one(index) -> None:
            rows = items.packages()
            if index.isValid() and index.row() < len(rows):
                details_dialog.open_details(self.win, rows[index.row()])
        view.activated.connect(open_one)

    def refresh(self) -> None:
        """Redraw every view from the model and the window's run state."""
        raise NotImplementedError

    def show_progress(self) -> None:
        """A step's progress moved (`step_progress`). Only a layout that shows more
        than the bars, which follow it themselves, has anything to redraw."""

    # --- the pieces every layout lays out the same way ---------------------------

    def status_column(self) -> QVBoxLayout:
        win = self.win
        col = QVBoxLayout()
        col.setSpacing(6)
        for w in (win.status, win.bar):
            col.addWidget(w)
        return col

    def status_block(self) -> QHBoxLayout:
        """The status line and the bar, with the action slot beside them."""
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addLayout(self.status_column(), 1)
        row.addWidget(self.win.action_bar, 0)
        return row

    def footer(self, with_actions: bool = False) -> QHBoxLayout:
        """The last run, Undo and the log link — Open log file beside it only while
        the log is shown — and, where the layout puts it there, the action slot at
        the trailing end."""
        win = self.win
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(win.last_run, 1)
        row.addWidget(win.rollback_btn, 0)
        row.addWidget(win.log_toggle, 0)
        row.addWidget(win.openlog_btn, 0)
        if with_actions:
            row.addWidget(win.action_bar, 0)
        return row

    def body(self, content: QWidget) -> package_views.EmptyOr:
        """A view, or the sentence a page shows when it has no packages."""
        b = package_views.EmptyOr(content)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.bodies.append(b)
        return b

    def tail_chain(self, actions_last: bool = False) -> list[QWidget]:
        """The message strip, the action bar and the footer, in that order — or the
        footer before the action bar, where the bar ends the footer's line."""
        win = self.win
        actions = [win.run_btn, win.check_btn, win.stop_btn]
        footer = [win.rollback_btn, win.log_toggle, win.openlog_btn]
        return [*(getattr(win, n) for n in BANNER_BUTTONS),
                *(footer + actions if actions_last else actions + footer)]

    def focus_chain(self) -> list[QWidget]:
        raise NotImplementedError

    def apply_metrics(self) -> None:
        """Every size that comes from the font (§4.2). Called when the layout is
        built and again when the text size or the desktop font changes."""
        win = self.win
        for r in win.rows.values():
            r.apply_metrics()
        win.message_strip.apply_metrics()
        win.log.setMinimumHeight(win.log.fontMetrics().lineSpacing() * LOG_LINES)

    def show_bodies(self, any_packages: bool) -> None:
        sentence = package_views.empty_sentence(self.win)
        for b in self.bodies:
            b.show_packages(any_packages, sentence)
