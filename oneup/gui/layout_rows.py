"""Rows: the five step rows above a table of packages (ONEUP-0239 §4.3).

The default layout. Below the header: the rows in their full form, the package
area, the message strip, the status with the action slot, and the footer.
"""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import package_views as pv
from . import steps
from .elided_label import ElidedLabel
from .layout_host import LayoutHost

# The three tabs: the step key each shows, or None for all of them, and its short word.
_FILTERS = (
    (None, lambda: QCoreApplication.translate("layout_rows", "All")),
    ("system", lambda: QCoreApplication.translate("layout_rows", "System")),
    ("flatpak", lambda: QCoreApplication.translate("layout_rows", "Flatpak")),
)


# A tab is as wide as its label with this count, so a count that grows moves no tab
# (§4.2 item 3).
_WIDEST_COUNT = 9999


def _tab_text(word: str, count: int) -> str:
    return QCoreApplication.translate("layout_rows", "{tab} · {count}").format(
        tab=word, count=count)


class RowsLayout(LayoutHost):
    LAYOUT_ID = "rows"
    FORM = "full"

    def __init__(self, win) -> None:
        super().__init__(win)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        for key, _t, _d in steps.TASKS:
            v.addWidget(win.rows[key])
        v.addWidget(win.package_area, 1)
        v.addWidget(win.message_strip)
        v.addLayout(self.status_block())
        v.addLayout(self.footer())

        # The package page: the tab strip, with the total and the size link at its
        # trailing end, then a table.
        bar = QFrame()
        bar.setObjectName("PackageFilter")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 0, 0)
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.filter_buttons: list[QPushButton] = []
        for n, (key, label) in enumerate(_FILTERS):
            btn = QPushButton(label())
            btn.setObjectName("GhostBtn")
            btn.setCheckable(True)
            btn.setChecked(n == 0)
            btn.setProperty("step", key)
            self.filter_group.addButton(btn, n)
            self.filter_buttons.append(btn)
            bl.addWidget(btn)
        self.total = ElidedLabel("")
        self.total.setObjectName("Tagline")
        self.total.setAlignment(Qt.AlignmentFlag.AlignTrailing)
        bl.addWidget(self.total, 1)
        bl.addWidget(win.size_link, 0)
        self.filter_group.idToggled.connect(lambda _i, on: on and self.refresh())

        model = win.packages
        self.items = pv.PackageItems(model, [
            lambda p: pv.state_word(model, p),
            lambda p: "\n".join(x for x in (pv.name_text(win, p), p.repo) if x),
            pv.versions,
            pv.size_text,
        ], [QCoreApplication.translate("layout_rows", "State"),
            QCoreApplication.translate("layout_rows", "Package"),
            QCoreApplication.translate("layout_rows", "Versions"),
            QCoreApplication.translate("layout_rows", "Size")],
            has_details=win.details.has_details, mark_column=1)
        self.table = pv.package_table(self.items, QCoreApplication.translate(
            "layout_rows", "Packages this update changes"))
        self.opens_details(self.table, self.items)

        pl = QVBoxLayout(self.page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)
        pl.addWidget(bar)
        pl.addWidget(self.body(self.table), 1)
        self.listen()

    def _filter_key(self):
        return self.filter_buttons[self.filter_group.checkedId()].property("step")

    def refresh(self) -> None:
        model = self.win.packages
        key = self._filter_key()
        shown = model.packages(key)
        self.items.set_packages(shown)
        for btn, (k, word) in zip(self.filter_buttons, _FILTERS, strict=True):
            btn.setText(_tab_text(word(), len(model.packages(k))))
        self.total.setText(pv.total_phrase(shown))
        self.show_bodies(bool(model.packages()))

    def focus_chain(self) -> list[QWidget]:
        win = self.win
        return [*(win.rows[k].switch for k, _t, _d in steps.TASKS),
                *self.filter_buttons, win.size_link.size_btn, self.table, win.log,
                *self.tail_chain()]

    def apply_metrics(self) -> None:
        super().apply_metrics()
        fm = self.table.fontMetrics()
        header = self.table.verticalHeader()
        header.setDefaultSectionSize(fm.lineSpacing() * 2 + 8)
        header.setSectionResizeMode(header.ResizeMode.Fixed)
        for btn, (_k, word) in zip(self.filter_buttons, _FILTERS, strict=True):
            shown = btn.text()
            btn.setText(_tab_text(word(), _WIDEST_COUNT))
            btn.setMinimumWidth(btn.sizeHint().width())
            btn.setText(shown)
        pv.hold_rows(self.table, self.PACKAGE_ROWS, header.defaultSectionSize())
