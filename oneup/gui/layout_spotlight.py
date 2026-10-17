"""Spotlight: large type about what is happening now (ONEUP-0239 §4.3).

Below the header: the five rows as tiles side by side, the spotlight panel — the
status in large type, the bar, the latest package, three figures and the size
link — then the package area as two lists, *Up next* and *Done*, the message
strip, and the footer with the action slot at its trailing end. The panel stays in view when the log
takes the package area's place.
"""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import package_views as pv
from . import steps
from .elided_label import ElidedLabel
from .layout_host import LayoutHost
from .markers import _format_size

# The states a package has reached once its download is behind it.
_FETCHED = ("downloaded", "installed", "removed")
_CHANGED = ("installed", "removed")


def _figure(label: str, value: str) -> str:
    return QCoreApplication.translate("layout_spotlight", "{label}: {value}").format(
        label=label, value=value)


def _of(part: str, whole: str) -> str:
    return QCoreApplication.translate("layout_spotlight", "{part} of {whole}").format(
        part=part, whole=whole)


class SpotlightLayout(LayoutHost):
    LAYOUT_ID = "spotlight"
    FORM = "tile"

    def __init__(self, win) -> None:
        super().__init__(win)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        tiles = QHBoxLayout()
        tiles.setSpacing(8)
        for key, _t, _d in steps.TASKS:
            tiles.addWidget(win.rows[key], 1)
        v.addLayout(tiles)

        # The panel: the status in large type (a selector on #SpotlightPanel), the
        # bar, its caption and the activity line, then the latest package, three
        # figures and the size link.
        self.panel = QFrame()
        self.panel.setObjectName("SpotlightPanel")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)
        pl.addLayout(self.status_column())
        self.latest = ElidedLabel("")
        self.latest.setObjectName("Tagline")
        pl.addWidget(self.latest)
        figures = QHBoxLayout()
        figures.setSpacing(16)
        self.figures = [ElidedLabel("") for _ in range(3)]
        for f in self.figures:
            f.setObjectName("Tagline")
            figures.addWidget(f, 1)
        figures.addWidget(win.size_link, 0)
        pl.addLayout(figures)
        v.addWidget(self.panel)
        v.addWidget(win.package_area, 1)
        v.addWidget(win.message_strip)
        v.addLayout(self.footer(with_actions=True))

        # The package page: two lists side by side, one line per package.
        model = win.packages

        def line(p):
            return pv.join_parts(pv.name_text(win, p), pv.versions(p), pv.size_text(p),
                                 p.repo, pv.state_word(model, p))

        self.next_items = pv.PackageItems(model, [line], has_details=win.details.has_details)
        self.done_items = pv.PackageItems(model, [line], has_details=win.details.has_details)
        self.next_list = pv.package_list(self.next_items, QCoreApplication.translate(
            "layout_spotlight", "Up next"))
        self.done_list = pv.package_list(self.done_items, QCoreApplication.translate(
            "layout_spotlight", "Done"))
        self.opens_details(self.next_list, self.next_items)
        self.opens_details(self.done_list, self.done_items)
        lists = QWidget()
        ll = QHBoxLayout(lists)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(12)
        for title, view in ((QCoreApplication.translate("layout_spotlight", "Up next"),
                             self.next_list),
                            (QCoreApplication.translate("layout_spotlight", "Done"),
                             self.done_list)):
            col = QVBoxLayout()
            col.setSpacing(4)
            heading = QLabel(title)
            heading.setObjectName("GroupHeading")
            col.addWidget(heading)
            col.addWidget(view, 1)
            ll.addLayout(col, 1)
        pg = QVBoxLayout(self.page)
        pg.setContentsMargins(0, 0, 0, 0)
        pg.addWidget(self.body(lists), 1)
        self.listen()

    def refresh(self) -> None:
        win = self.win
        model = win.packages
        every = model.packages()
        state = {id(p): model.shown_state(p) for p in every}
        self.next_items.set_packages([p for p in every if pv.GROUP[state[id(p)]] != "done"])
        self.done_items.set_packages([p for p in every if pv.GROUP[state[id(p)]] == "done"])
        total = len(every)
        fetched = [p for p in every if state[id(p)] in _FETCHED]
        changed = sum(1 for p in every if state[id(p)] in _CHANGED)
        all_bytes = sum(p.size for p in every)
        self.figures[0].setText(_figure(
            QCoreApplication.translate("layout_spotlight", "Downloaded"),
            _of(str(len(fetched)), str(total))))
        self.figures[1].setText(_figure(
            QCoreApplication.translate("layout_spotlight", "Installed"),
            _of(str(changed), str(total))))
        self.figures[2].setText(_figure(
            QCoreApplication.translate("layout_spotlight", "Download"),
            _of(_format_size(sum(p.size for p in fetched)), _format_size(all_bytes))
            if all_bytes else QCoreApplication.translate("layout_spotlight", "not known")))
        self.latest.setText(self._latest_line())
        self.show_bodies(bool(every))

    def _latest_line(self) -> str:
        """The package the last PKG line named: its state, versions and source.
        Blank while there is none; the line keeps its height (§4.3.3)."""
        latest = self.win.latest_package
        if latest is None:
            return ""
        model = self.win.packages
        for p in model.packages(latest[0]):
            if (p.name, p.edition) == latest[1:]:
                return pv.join_parts(p.name, pv.state_word(model, p), pv.versions(p), p.repo)
        return ""

    def focus_chain(self) -> list[QWidget]:
        win = self.win
        return [*(win.rows[k].switch for k, _t, _d in steps.TASKS),
                win.size_link.size_btn, self.next_list, self.done_list, win.log,
                *self.tail_chain(actions_last=True)]
