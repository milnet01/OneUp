"""Spotlight: large type about what is happening now (ONEUP-0239 §4.3).

Below the header: the five rows as tiles side by side, the spotlight panel — a
small "Now · {step}" heading, the latest package as a sentence in large type with
its description, source and versions under it, the step's percentage at the
trailing end, the bar, the status line, and three figure boxes — then the package
area as two lists, *Up next* and *Done*, the size link at the trailing end of the
first's heading, the message strip, and the footer with the action slot at its
trailing end. The panel stays in view when the log takes the package area's place.
"""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from . import package_views as pv
from . import step_progress, steps
from .elided_label import ElidedLabel
from .layout_host import LayoutHost
from .markers import _format_size
from .step_progress import FULL


def _of(part: str, whole: str) -> str:
    return QCoreApplication.translate("layout_spotlight", "{part} of {whole}").format(
        part=part, whole=whole)


def _heading(word: str, count: int) -> str:
    return QCoreApplication.translate("layout_spotlight", "{list} · {count}").format(
        list=word, count=count)


class SpotlightLayout(LayoutHost):
    LAYOUT_ID = "spotlight"
    FORM = "tile"
    PACKAGE_ROWS = 6

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

        # The panel. It paints a raised surface of its own (§4.8), so it holds no
        # button: the size link sits on the Up next heading instead (§4.6).
        self.panel = QFrame()
        self.panel.setObjectName("SpotlightPanel")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(20, 16, 20, 16)
        pl.setSpacing(6)
        self.now_heading = ElidedLabel("")
        self.now_heading.setObjectName("SpotlightNow")
        pl.addWidget(self.now_heading)
        top = QHBoxLayout()
        top.setSpacing(16)
        lines = QVBoxLayout()
        lines.setSpacing(2)
        self.headline = ElidedLabel("")
        self.headline.setObjectName("SpotlightHeadline")
        self.about = ElidedLabel("")
        self.about.setObjectName("SpotlightAbout")
        lines.addWidget(self.headline)
        lines.addWidget(self.about)
        top.addLayout(lines, 1)
        # As wide as "100%" at its font (apply_metrics), so a new figure moves
        # nothing beside it.
        self.percent = ElidedLabel("")
        self.percent.setObjectName("SpotlightPercent")
        self.percent.setAlignment(Qt.AlignmentFlag.AlignTrailing)
        top.addWidget(self.percent, 0)
        pl.addLayout(top)
        # The bar, then the status line under it, which the sketch lacks but which
        # stays in view so a stall is never hidden (§4.3 Spotlight item 2).
        for w in (win.bar, win.status):
            pl.addWidget(w)
        figures = QHBoxLayout()
        figures.setSpacing(12)
        self.figures: list[ElidedLabel] = []
        for label in (QCoreApplication.translate("layout_spotlight", "Packages"),
                      QCoreApplication.translate("layout_spotlight", "Downloaded"),
                      QCoreApplication.translate("layout_spotlight", "Time left")):
            box = QFrame()
            box.setObjectName("FigureBox")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(14, 10, 14, 10)
            bl.setSpacing(2)
            name = ElidedLabel(label)
            name.setObjectName("FigureLabel")
            value = ElidedLabel("")
            value.setObjectName("FigureValue")
            bl.addWidget(name)
            bl.addWidget(value)
            figures.addWidget(box, 1)
            self.figures.append(value)
        pl.addLayout(figures)
        v.addWidget(self.panel)
        v.addWidget(win.package_area, 1)
        v.addWidget(win.message_strip)
        v.addLayout(self.footer(with_actions=True))

        # The package page: two lists side by side, one line per package, each
        # headed with its count.
        model = win.packages

        def line(p):
            return pv.join_parts(pv.state_word(model, p), pv.name_text(win, p), pv.size_text(p))

        def parts(p):
            return model.shown_state(p), pv.name_text(win, p), pv.size_text(p)

        self.next_items = pv.PackageItems(model, [line], has_details=win.details.has_details)
        self.done_items = pv.PackageItems(model, [line], has_details=win.details.has_details)
        self.next_list = pv.package_list(self.next_items, QCoreApplication.translate(
            "layout_spotlight", "Up next"), parts)
        self.done_list = pv.package_list(self.done_items, QCoreApplication.translate(
            "layout_spotlight", "Done"), parts)
        self.opens_details(self.next_list, self.next_items)
        self.opens_details(self.done_list, self.done_items)
        self.next_heading = ElidedLabel("")
        self.done_heading = ElidedLabel("")
        self.heads: list[QWidget] = []
        lists = QWidget()
        ll = QHBoxLayout(lists)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(12)
        for heading, view, link in ((self.next_heading, self.next_list, win.size_link),
                                    (self.done_heading, self.done_list, None)):
            heading.setObjectName("GroupHeading")
            col = QVBoxLayout()
            col.setSpacing(4)
            head = QWidget()
            self.heads.append(head)
            hl = QHBoxLayout(head)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(heading, 1)
            if link is not None:
                hl.addWidget(link, 0)
            col.addWidget(head)
            col.addWidget(view, 1)
            ll.addLayout(col, 1)
        pg = QVBoxLayout(self.page)
        pg.setContentsMargins(0, 0, 0, 0)
        pg.addWidget(self.body(lists), 1)
        self.listen()

    def refresh(self) -> None:
        model = self.win.packages
        every = model.packages()
        state = {id(p): model.shown_state(p) for p in every}
        upcoming = [p for p in every if pv.GROUP[state[id(p)]] != "done"]
        done = [p for p in every if pv.GROUP[state[id(p)]] == "done"]
        self.next_items.set_packages(upcoming)
        self.done_items.set_packages(done)
        self.next_heading.setText(_heading(
            QCoreApplication.translate("layout_spotlight", "Up next"), len(upcoming)))
        self.done_heading.setText(_heading(
            QCoreApplication.translate("layout_spotlight", "Done"), len(done)))
        self.show_progress()
        self.show_bodies(bool(every))

    def show_progress(self) -> None:
        """The panel: the running step, the latest package, the step's percentage
        and the three figures, from the running step's last PROGRESS (§4.3.1)."""
        win = self.win
        key = win.current_step
        title = {k: t for k, t, _d in steps.TASKS}.get(key, key)
        self.now_heading.setText(QCoreApplication.translate(
            "layout_spotlight", "Now · {step}").format(
            step=QCoreApplication.translate("steps", title)) if key else "")
        self.headline.setText("")
        self.about.setText("")
        package = self._latest()
        if package is not None:
            self.headline.setText(self._sentence(package))
            about = win.details.about(package.name) if package.key == "system" else None
            self.about.setText(pv.join_parts(about.summary if about else "", package.repo,
                                             pv.versions(package)))
        value = win.step_progress.get(key) if key else None
        self.percent.setText("" if value is None else QCoreApplication.translate(
            "layout_spotlight", "{percent}%").format(percent=round(value * 100 / FULL)))
        unknown = QCoreApplication.translate("layout_spotlight", "not known")
        done, total = win._progress_count
        if total:
            self.figures[0].setText(_of(str(done), str(total)))
        elif done:
            # A total of 0 means not known, and renders as a running tally
            # (marker-protocol.md §4.3).
            self.figures[0].setText(QCoreApplication.translate(
                "layout_spotlight", "{n} so far").format(n=done))
        else:
            self.figures[0].setText(unknown)
        self.figures[1].setText(_of(_format_size(win._dl_got), _format_size(win._dl_total))
                                if win._dl_total else unknown)
        self.figures[2].setText(step_progress.time_left(win) or unknown)

    def _latest(self):
        """The package the last PKG line named, or None while there is none."""
        latest = self.win.latest_package
        if latest is None:
            return None
        for p in self.win.packages.packages(latest[0]):
            if (p.name, p.edition) == latest[1:]:
                return p
        return None

    def _sentence(self, package) -> str:
        """One whole sentence per phase, or the name alone outside one (§4.3.3)."""
        win = self.win
        phase = step_progress.shown_phase(win) if package.key == win.current_step else ""
        if phase == "download":
            return QCoreApplication.translate("layout_spotlight", "Downloading {name}").format(
                name=package.name)
        if phase == "install":
            return QCoreApplication.translate("layout_spotlight", "Installing {name}").format(
                name=package.name)
        return package.name

    def apply_metrics(self) -> None:
        super().apply_metrics()
        self.percent.setMinimumWidth(self.percent.fontMetrics().horizontalAdvance(
            QCoreApplication.translate("layout_spotlight", "{percent}%").format(percent=100)))
        # Both headings stand as tall as the one holding the size link, so the two
        # lists start level.
        for head in self.heads:
            head.setMinimumHeight(self.win.size_link.sizeHint().height())
        for view in (self.next_list, self.done_list):
            pv.hold_rows(view, self.PACKAGE_ROWS, view.itemDelegate().height(view.fontMetrics()))

    def focus_chain(self) -> list[QWidget]:
        win = self.win
        return [*(win.rows[k].switch for k, _t, _d in steps.TASKS),
                win.size_link.size_btn, self.next_list, self.done_list, win.log,
                *self.tail_chain(actions_last=True)]
