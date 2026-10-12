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

from . import package_views, steps

# The buttons inside the message strip, in the order its banners stack and each
# banner lays them out. Layout order does NOT set the focus chain — parenting
# order does — so every host states it from this list (ONEUP-0064).
BANNER_BUTTONS = ("restart_btn", "services_btn", "warn_copy_btn", "warn_btn", "warn_btn2",
                  "retry_btn", "appupdate_btn")

# The package area holds at least this many lines of a package view (§4.2 item 2).
PACKAGE_LINES = 6


class LayoutHost(QWidget):
    """The base every layout shares. A subclass builds its arrangement in its own
    `__init__`, fills `self.page`, and keeps its views current in `refresh`."""

    LAYOUT_ID = ""
    FORM = "full"

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

    def release(self) -> None:
        """Give back every callback this layout took. The window calls it before
        deleting the layout, or the next marker calls into a deleted widget from
        inside `handle_marker`, which must never raise."""
        for callback in self._listening:
            self.win.packages.unsubscribe(callback)
        self._listening.clear()

    def _on_model(self, _key) -> None:
        self.refresh()

    def refresh(self) -> None:
        """Redraw every view from the model and the window's run state."""
        raise NotImplementedError

    # --- the pieces every layout lays out the same way ---------------------------

    def status_column(self) -> QVBoxLayout:
        win = self.win
        col = QVBoxLayout()
        col.setSpacing(6)
        for w in (win.status, win.bar, win.bar_caption, win.activity):
            col.addWidget(w)
        return col

    def status_block(self) -> QHBoxLayout:
        """Status, bar, caption and activity, with Run and Check/Stop beside them."""
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addLayout(self.status_column(), 1)
        row.addWidget(self.win.action_bar, 0)
        return row

    def footer(self) -> QHBoxLayout:
        win = self.win
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(win.last_run, 1)
        row.addWidget(win.rollback_btn, 0)
        row.addWidget(win.log_toggle, 0)
        row.addWidget(win.openlog_btn, 0)
        return row

    def body(self, content: QWidget) -> package_views.EmptyOr:
        """A view, or the sentence a page shows when it has no packages."""
        b = package_views.EmptyOr(content)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.bodies.append(b)
        return b

    def tail_chain(self) -> list[QWidget]:
        """The message strip, the action bar and the footer, in that order."""
        win = self.win
        return [*(getattr(win, n) for n in BANNER_BUTTONS),
                win.run_btn, win.check_btn, win.stop_btn,
                win.rollback_btn, win.log_toggle, win.openlog_btn]

    def focus_chain(self) -> list[QWidget]:
        raise NotImplementedError

    def apply_metrics(self) -> None:
        """Every size that comes from the font (§4.2). Called when the layout is
        built and again when the text size or the desktop font changes."""
        win = self.win
        for r in win.rows.values():
            r.apply_metrics()
        win.message_strip.apply_metrics()
        lines = win.log.fontMetrics().lineSpacing() * PACKAGE_LINES
        win.log.setMinimumHeight(lines)
        for b in self.bodies:
            b.setMinimumHeight(lines)

    def show_bodies(self, any_packages: bool) -> None:
        sentence = package_views.empty_sentence(self.win)
        for b in self.bodies:
            b.show_packages(any_packages, sentence)
