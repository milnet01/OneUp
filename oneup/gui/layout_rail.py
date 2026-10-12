"""Rail: the steps down one side, the packages as a board of cards (ONEUP-0239 §4.3).

Below the header: two columns — the rail of five rows and the board, which is the
package area — then the message strip, the status with Run and Check/Stop, and the
footer. The board follows the step running now, and shows every package between
steps.
"""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from . import package_views as pv
from . import steps
from .elided_label import ElidedLabel
from .layout_host import LayoutHost


class RailLayout(LayoutHost):
    LAYOUT_ID = "rail"
    FORM = "rail"

    def __init__(self, win) -> None:
        super().__init__(win)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        cols = QHBoxLayout()
        cols.setSpacing(12)
        # The rail's width comes from the font, never from what the badges say
        # (apply_metrics); the badges elide to fit it.
        self.rail = QWidget()
        self.rail.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        rl = QVBoxLayout(self.rail)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        for key, _t, _d in steps.TASKS:
            rl.addWidget(win.rows[key])
        rl.addStretch(1)
        cols.addWidget(self.rail, 0)
        cols.addWidget(win.package_area, 1)
        v.addLayout(cols, 1)
        v.addWidget(win.message_strip)
        v.addLayout(self.status_block())
        v.addLayout(self.footer())

        # The board's page: a summary with the size link, the counts, the size
        # strip and its legend, then the cards.
        summary = QFrame()
        summary.setObjectName("PackageSummary")
        sl = QHBoxLayout(summary)
        sl.setContentsMargins(0, 0, 0, 0)
        self.summary = ElidedLabel("")
        self.summary.setObjectName("Tagline")
        sl.addWidget(self.summary, 1)
        sl.addWidget(win.size_link, 0)
        self.counts = ElidedLabel("")
        self.counts.setObjectName("Tagline")
        self.strip = pv.SizeStrip()
        self.legend = pv.strip_legend(self.strip)

        model = win.packages
        self.items = pv.PackageItems(model, [lambda p: "\n".join((
            p.name, pv.versions(p),
            pv.join_parts(pv.size_text(p), p.repo, pv.state_word(model, p))))])
        self.board = pv.package_board(self.items, QCoreApplication.translate(
            "layout_rail", "Packages of the step running now"))

        pl = QVBoxLayout(self.page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)
        pl.addWidget(summary)
        pl.addWidget(self.counts)
        pl.addWidget(self.strip)
        pl.addWidget(self.legend)
        pl.addWidget(self.body(self.board), 1)
        self.listen()

    def _shown(self) -> tuple[str, list]:
        """The step whose packages the board shows, by title, and those packages:
        the running step's, or every package when none runs or it has none."""
        model = self.win.packages
        key = self.win.current_step
        if key and model.packages(key):
            title = {k: t for k, t, _d in steps.TASKS}.get(key, key)
            return QCoreApplication.translate("steps", title), model.packages(key)
        return QCoreApplication.translate("layout_rail", "All updates"), model.packages()

    def refresh(self) -> None:
        model = self.win.packages
        title, shown = self._shown()
        self.items.set_packages(shown)
        self.summary.setText(pv.summary_sentence(title, shown))
        sentence = pv.counts_sentence(pv.counts(model, shown))
        self.counts.setText(sentence)
        self.strip.setAccessibleName(sentence)
        self.strip.set_blocks([(pv.GROUP[model.shown_state(p)], p.size) for p in shown])
        self.show_bodies(bool(model.packages()))

    def focus_chain(self) -> list[QWidget]:
        win = self.win
        return [*(win.rows[k].switch for k, _t, _d in steps.TASKS),
                win.size_link.size_btn, self.board, win.log, *self.tail_chain()]

    def apply_metrics(self) -> None:
        super().apply_metrics()
        win = self.win
        # The widest step title, plus the switch and the row's own padding.
        row = win.rows[steps.TASKS[0][0]]
        fm = row.name.fontMetrics()
        widest = max(fm.horizontalAdvance(r.title) for r in win.rows.values())
        card = row.card.layout().contentsMargins()
        frame = row.layout().contentsMargins()
        self.rail.setMinimumWidth(widest + row.switch.sizeHint().width() + 10
                                  + card.left() + card.right() + frame.left() + frame.right())
        pv.fit_board(self.board)
