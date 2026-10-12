"""A one-line label whose size never follows its text (ONEUP-0239 §4.2 item 4).

The text is elided when the label is painted, never with `setText`: `text()` keeps
the whole sentence, because `_announce` reads the status label and the tests read
every label's text. The whole text is also the tooltip, so nothing is lost to a
reader the ellipsis hides it from.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QSizePolicy

# The width the label asks for, in average characters. Small on purpose: the
# layout, not the text, decides how wide the label is.
_HINT_CHARS = 4


class ElidedLabel(QLabel):
    """One line of plain text, elided at the end that reads last.

    Its size hint is the same whatever it holds, so a new sentence moves nothing
    around it. An empty label paints no text, and carries `empty="true"` so the
    stylesheet drops its background — a badge with no outcome yet leaves a blank
    space rather than an empty pill.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.PlainText)   # engine text shown as typed (ONEUP-0183)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setToolTip(text)
        # Qt paints a styled background before paintEvent runs, so an empty
        # label's pill is the stylesheet's to drop, keyed on this property.
        empty = "true" if not text else "false"
        if self.property("empty") != empty:
            self.setProperty("empty", empty)
            self.style().unpolish(self)
            self.style().polish(self)

    # With word wrap on — a Spotlight tile's title — it is an ordinary wrapping
    # label: its height follows its width, and its area allows for that.

    def sizeHint(self) -> QSize:
        if self.wordWrap():
            return super().sizeHint()
        m = self.contentsMargins()
        fm = self.fontMetrics()
        return QSize(fm.averageCharWidth() * _HINT_CHARS + m.left() + m.right(),
                     fm.height() + m.top() + m.bottom())

    def minimumSizeHint(self) -> QSize:
        if self.wordWrap():
            return super().minimumSizeHint()
        return self.sizeHint()

    def paintEvent(self, event) -> None:
        if self.wordWrap():
            super().paintEvent(event)
            return
        if not self.text():
            return
        p = QPainter(self)
        self.drawFrame(p)               # the stylesheet's background and border
        rect = self.contentsRect()
        shown = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight,
                                              rect.width())
        # Alignment through the style, which mirrors a leading alignment for a
        # right-to-left window; the label never reads its own direction.
        self.style().drawItemText(p, rect, int(self.alignment() | Qt.AlignmentFlag.AlignVCenter),
                                  self.palette(), self.isEnabled(), shown,
                                  self.foregroundRole())
