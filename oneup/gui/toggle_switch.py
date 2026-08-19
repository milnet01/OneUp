"""The phone-style on/off switch.

A fixed design point (the user, standing): OneUp does not use check boxes.
"""
from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton

from .theme import GREEN, RED


class ToggleSwitch(QAbstractButton):
    """A sliding on/off switch. Track is green when on, red when off — plus a
    SHAPE (a bar when on, an open circle when off) so the state survives
    colour blindness, and a focus ring so keyboard users can see where they are.

    Being a checkable QAbstractButton, Qt maps this to an accessible CheckBox
    with a real checked state, so a screen reader announces on/off for free —
    all it needs from the caller is an accessible name.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(56, 30)
        self._margin = 3
        self._pos = 1.0  # 0.0 = off (left), 1.0 = on (right)
        self._high_contrast = False   # set from the stylesheet (qproperty-highContrast)
        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.toggled.connect(self._slide)

    def _slide(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def get_knob_pos(self) -> float:
        return self._pos

    def set_knob_pos(self, value: float):
        self._pos = value
        self.update()

    knobPos = Property(float, get_knob_pos, set_knob_pos)

    def get_high_contrast(self) -> bool:
        return self._high_contrast

    def set_high_contrast(self, value: bool):
        self._high_contrast = bool(value)
        self.update()

    # Set by the stylesheet, not by code — see the qproperty- note in _QSS.
    highContrast = Property(bool, get_high_contrast, set_high_contrast)

    def _paint_state_shape(self, p: QPainter, diameter: float):
        """A bar for on, an open circle for off, drawn in the track half OPPOSITE
        the knob (the iOS convention). Painted as geometry rather than a text
        glyph: a painted widget has no font-fallback chain, so a missing character
        would silently vanish and take the only colour-independent cue with it."""
        cx = (self._margin + diameter / 2 if self.isChecked()
              else self.width() - self._margin - diameter / 2)
        cy = self.height() / 2
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#ffffff"), 2))
        if self.isChecked():
            half = diameter * 0.26
            p.drawLine(QPointF(cx, cy - half), QPointF(cx, cy + half))
        else:
            r = diameter * 0.22
            p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        radius = self.height() / 2
        track = GREEN if self.isChecked() else RED
        if not self.isEnabled():
            track = track.lighter(140)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), radius, radius)

        diameter = self.height() - 2 * self._margin
        travel = self.width() - 2 * self._margin - diameter
        x = self._margin + self._pos * travel
        self._paint_state_shape(p, diameter)

        if self._high_contrast:
            # Outline the track so the switch stays distinguishable from a pure
            # black/white surface, and rim the knob so it reads against the track.
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2),
                              radius, radius)
            p.setPen(QPen(QColor("#000000"), 1))
        else:
            p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, self._margin, diameter, diameter))

        # No focus ring is drawn, by explicit design decision (2026-07-25): rings
        # and outlines around these controls were rejected as visual clutter. The
        # state SHAPE above is what carries meaning; Qt still reports focus to a
        # screen reader, so keyboard operability is unaffected — only the sighted
        # keyboard-only cue is absent.
