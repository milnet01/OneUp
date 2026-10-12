"""The "Show download size" link and the figure that replaces it (ONEUP-0239 §4.6).

Moved out of the system step's row unchanged: one control the window owns, which
each layout places in its own package summary or panel. The link and its result
take turns in one slot, so the slot is pinned to the widest text either can show,
the way Check and Stop are — neither keeps its space while hidden, or each would
hold a slot of its own.
"""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from .elided_label import ElidedLabel


def _link_text() -> str:
    return QCoreApplication.translate("size_link", "Show download size")


def _pending_text() -> str:
    # Name the expected wait. Getting the figure means asking zypper's solver to
    # work out the WHOLE transaction (a --dry-run), which takes tens of seconds on
    # a big Tumbleweed upgrade; a bare "Calculating…" for that long reads as a hung
    # button, so the label says up front that it's normal.
    return QCoreApplication.translate("size_link", "Calculating… (up to a minute)")


class SizeLink(QWidget):
    """The link, or the figure it fetched — one slot, one width."""

    def __init__(self, on_click) -> None:
        super().__init__()
        self.size_btn = QPushButton(_link_text())
        self.size_btn.setObjectName("LinkBtn")
        self.size_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.size_btn.clicked.connect(on_click)
        self.size_result = ElidedLabel("")
        self.size_result.setObjectName("SizeResult")
        self.size_result.setVisible(False)
        self._has_size = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.size_btn)
        lay.addWidget(self.size_result, 1)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._pin_width()
        self.size_btn.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.StyleChange, QEvent.Type.FontChange):
            QTimer.singleShot(0, self._pin_width)
        return super().eventFilter(obj, event)

    def _pin_width(self) -> None:
        """The slot's width: the widest of the link's two labels and the result's
        two usual sentences. A longer figure than these elides, whole in its tooltip."""
        shown = self.size_btn.text()
        widths = []
        for label in (_link_text(), _pending_text()):
            self.size_btn.setText(label)
            widths.append(self.size_btn.sizeHint().width())
        self.size_btn.setText(shown)
        fm = self.size_result.fontMetrics()
        m = self.size_result.contentsMargins()
        for sentence in (QCoreApplication.translate("run", "Nothing to download"),
                         QCoreApplication.translate("run", "↓ {size} to download").format(
                             size="9999.9 MiB")):
            widths.append(fm.horizontalAdvance(sentence) + m.left() + m.right())
        self.setMinimumWidth(max(widths))

    def set_size_result(self, text: str) -> None:
        """Show the download-size figure and retire the link."""
        self.size_btn.setVisible(False)
        self.size_result.setText(text)
        self.size_result.setVisible(True)
        self._has_size = True

    def size_pending(self) -> None:
        self.size_btn.setEnabled(False)
        self.size_btn.setText(_pending_text())

    def size_failed(self) -> None:
        """Re-arm the link so the user can retry after a failed size fetch."""
        self.size_btn.setEnabled(True)
        self.size_btn.setText(_link_text())

    def has_size(self) -> bool:
        return self._has_size

    def reset(self) -> None:
        """Back to the link, between runs."""
        self.size_result.setVisible(False)
        self.size_result.setText("")
        self._has_size = False
        self.size_btn.setVisible(True)
        self.size_btn.setEnabled(True)
        self.size_btn.setText(_link_text())
