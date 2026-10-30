"""The symbols the app draws itself, rather than asking a font for (ONEUP-0239 §4.3).

Noto Sans, openSUSE's interface font, has no tick, down arrow, clock, crosshair or
gear (`QRawFont`, ONEUP-0313, ONEUP-0320, ONEUP-0327), so a character would come from
whatever fallback the machine happens to carry, or be an empty box. Each shape is
drawn on a square of side 1 and scaled, so it follows the text size. None of them
points along the reading direction, so none mirrors (`ui-and-accessibility.md` §8.3).
"""
from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import Property, QEvent, QLineF, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QPushButton

from . import theme

_STROKE = 0.1       # of the square's side


def _clock(p: QPainter) -> None:
    p.drawEllipse(QPointF(0.5, 0.5), 0.4, 0.4)
    p.drawPolyline([QPointF(0.5, 0.25), QPointF(0.5, 0.5), QPointF(0.68, 0.6)])


def _arrow(p: QPainter, bottom: float = 0.85) -> None:
    p.drawLine(QPointF(0.5, 0.12), QPointF(0.5, bottom))
    p.drawPolyline([QPointF(0.22, bottom - 0.28), QPointF(0.5, bottom),
                    QPointF(0.78, bottom - 0.28)])


def _arrow_onto_line(p: QPainter) -> None:
    _arrow(p, 0.66)
    p.drawLine(QPointF(0.16, 0.88), QPointF(0.84, 0.88))


def _tick(p: QPainter) -> None:
    p.drawPolyline([QPointF(0.14, 0.54), QPointF(0.4, 0.8), QPointF(0.86, 0.22)])


def _cross(p: QPainter) -> None:
    p.drawLine(QPointF(0.2, 0.2), QPointF(0.8, 0.8))
    p.drawLine(QPointF(0.8, 0.2), QPointF(0.2, 0.8))


def _dash(p: QPainter) -> None:
    p.drawLine(QPointF(0.2, 0.5), QPointF(0.8, 0.5))


def crosshair(p: QPainter) -> None:
    """Recenter's symbol: a circle with four ticks (the user's choice, ONEUP-0320)."""
    p.drawEllipse(QPointF(0.5, 0.5), 0.27, 0.27)
    for x1, y1, x2, y2 in ((0.5, 0.04, 0.5, 0.3), (0.5, 0.7, 0.5, 0.96),
                           (0.04, 0.5, 0.3, 0.5), (0.7, 0.5, 0.96, 0.5)):
        p.drawLine(QLineF(x1, y1, x2, y2))


def gear(p: QPainter) -> None:
    """Settings' symbol: a ring with eight teeth."""
    p.drawEllipse(QPointF(0.5, 0.5), 0.25, 0.25)
    for tooth in range(8):
        a = tooth * math.pi / 4
        p.drawLine(QPointF(0.5 + 0.28 * math.cos(a), 0.5 + 0.28 * math.sin(a)),
                   QPointF(0.5 + 0.44 * math.cos(a), 0.5 + 0.44 * math.sin(a)))


# One shape per state a view shows, keyed as `steps.STATE_WORDS` is.
STATE_SHAPES: dict[str, Callable[[QPainter], None]] = {
    "queued": _clock,
    "downloading": _arrow,
    "downloaded": _arrow_onto_line,
    "installed": _tick,
    "removed": _cross,
    "unchanged": _dash,
}


def draw(painter: QPainter, shape: Callable[[QPainter], None], rect: QRectF, ink) -> None:
    """Draw `shape` in `ink`, scaled to the square centred in `rect`."""
    side = min(rect.width(), rect.height())
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.center().x() - side / 2, rect.center().y() - side / 2)
    painter.scale(side, side)
    painter.setPen(QPen(QColor(ink), _STROKE, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    shape(painter)
    painter.restore()


class SymbolButton(QPushButton):
    """A `#GhostBtn` whose symbol is drawn, in the colour its label would have.

    A stylesheet cannot reach an icon, so the sheet hands the ghost button's three
    label colours over as properties, as it does for `ToggleSwitch`, and the icon is
    redrawn when the button's state or the text size changes. Qt evaluates a
    `qproperty-` once, not per pseudo-state, so choosing between them is done here.
    """

    def __init__(self, shape: Callable[[QPainter], None], text: str = "") -> None:
        super().__init__(text)
        self._shape = shape
        p = theme.current_palette()
        # Set from the stylesheet; these defaults only show before the sheet arrives.
        self._inks = {"rest": QColor(p["ghostfg"]), "hover": QColor(p["ghosthov"]),
                      "focus": QColor(p["focusink"])}
        self._redraw()

    def _set(self, part: str, colour) -> None:
        self._inks[part] = QColor(colour)
        self._redraw()

    def get_rest_ink(self) -> QColor:
        return self._inks["rest"]

    def set_rest_ink(self, colour) -> None:
        self._set("rest", colour)

    def get_hover_ink(self) -> QColor:
        return self._inks["hover"]

    def set_hover_ink(self, colour) -> None:
        self._set("hover", colour)

    def get_focus_ink(self) -> QColor:
        return self._inks["focus"]

    def set_focus_ink(self, colour) -> None:
        self._set("focus", colour)

    restInk = Property(QColor, get_rest_ink, set_rest_ink)
    hoverInk = Property(QColor, get_hover_ink, set_hover_ink)
    focusInk = Property(QColor, get_focus_ink, set_focus_ink)

    def ink(self) -> QColor:
        """The label's colour now: focus outranks hover, as the sheet's order does."""
        if self.hasFocus():
            return self._inks["focus"]
        return self._inks["hover" if self.underMouse() else "rest"]

    def _redraw(self) -> None:
        side = self.fontMetrics().height()
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(QSize(side, side) * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        draw(painter, self._shape, QRectF(0, 0, side, side), self.ink())
        painter.end()
        self.setIconSize(QSize(side, side))
        # Normal and Active both: Qt draws a focused button's icon in the Active mode.
        icon = QIcon()
        icon.addPixmap(pixmap, QIcon.Mode.Normal)
        icon.addPixmap(pixmap, QIcon.Mode.Active)
        self.setIcon(icon)

    def event(self, e) -> bool:
        handled = super().event(e)
        if e.type() in (QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.FocusIn,
                        QEvent.Type.FocusOut, QEvent.Type.FontChange,
                        QEvent.Type.StyleChange):
            self._redraw()
        return handled
