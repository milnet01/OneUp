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

from . import theme


class ToggleSwitch(QAbstractButton):
    """A sliding on/off switch. Track is green when on, red when off — plus a
    SHAPE (a bar when on, an open circle when off) so the state survives colour
    blindness. Keyboard focus DARKENS the track to a colour the stylesheet
    derives and hands over as a Qt property; no ring is drawn (ONEUP-0076).

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
        # The two focused tracks, likewise set from the stylesheet. No colour rule
        # can reach what paintEvent draws, so a Qt property is the only seam —
        # the same one highContrast already uses. Defaulting them to the resting
        # tracks means an unstyled switch simply shows no cue rather than a wrong
        # one; the sheet always assigns both.
        pal = theme.current_palette()
        self._focus_on = QColor(pal["switchon"])
        self._focus_off = QColor(pal["switchoff"])
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

    def get_focus_on(self) -> QColor:
        return self._focus_on

    def set_focus_on(self, value: QColor):
        self._focus_on = QColor(value)
        self.update()

    focusTrackOn = Property(QColor, get_focus_on, set_focus_on)

    def get_focus_off(self) -> QColor:
        return self._focus_off

    def set_focus_off(self, value: QColor):
        self._focus_off = QColor(value)
        self.update()

    focusTrackOff = Property(QColor, get_focus_off, set_focus_off)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update()

    def _paint_state_shape(self, p: QPainter, diameter: float):
        """A bar for on, an open circle for off, drawn in the track half OPPOSITE
        the knob (the iOS convention). Painted as geometry rather than a text
        glyph: a painted widget has no font-fallback chain, so a missing character
        would silently vanish and take the only colour-independent cue with it."""
        cx = (self._margin + diameter / 2 if self.isChecked()
              else self.width() - self._margin - diameter / 2)
        cy = self.height() / 2
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(theme.current_palette()["switchmark"]), 2))
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
        pal = theme.current_palette()
        if self.hasFocus():
            track = self._focus_on if self.isChecked() else self._focus_off
        else:
            track = QColor(pal["switchon" if self.isChecked() else "switchoff"])
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
            p.setPen(QPen(QColor(pal["switchtrackrim"]), 2))
            p.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2),
                              radius, radius)
            p.setPen(QPen(QColor(pal["switchknobrim"]), 1))
        else:
            p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal["switchknob"]))
        p.drawEllipse(QRectF(x, self._margin, diameter, diameter))

        # No focus ring is drawn, by explicit design decision (2026-07-25): rings
        # and outlines around these controls were rejected as visual clutter. The
        # sighted keyboard cue is the DARKENED TRACK chosen at the top of this
        # method — a colour change to pixels that were already painted, which is
        # what keeps the geometry fixed and the state SHAPE readable on top of it
        # (ONEUP-0076 derives the track so the shape still clears 3:1 on it).
