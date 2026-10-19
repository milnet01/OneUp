"""One task's row: its switch, badge, timing and progress."""
from __future__ import annotations

import shiboken6
from PySide6.QtCore import QCoreApplication, QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
)

from . import steps
from .elided_label import ElidedLabel
from .toggle_switch import ToggleSwitch

# The badge's width in the full form, in average characters at its own font:
# room for "3 installed  ·  42s" and its kind. Longer text elides (ONEUP-0239 §4.1).
_BADGE_CHARS = 20
FORMS = ("full", "rail", "tile")


class _RowBar(QProgressBar):
    """A thin bar: a quarter of a text line tall at the current font, so it grows
    with the text size and never with anything else (ONEUP-0239 §4.2)."""

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), max(4, self.fontMetrics().height() // 4))

    def minimumSizeHint(self) -> QSize:
        return QSize(super().minimumSizeHint().width(), self.sizeHint().height())


class TaskRow(QFrame):
    """One task, drawn as a card with a hover-lit gradient border: the 1px
    outer frame shows the accent gradient, an inner card sits 1px inside it. A
    badge shows what a check found or a run did, and a thin bar along the row
    shows that step's own progress.

    The row holds the same children in every layout; `set_form` only arranges
    them (ONEUP-0239 §4.1). The packages the step changes are shown by the
    layout's package page, not here."""

    def __init__(self, key: str, title: str, description: str):
        super().__init__()
        self.key = key
        self.title = title
        self._description = description   # kept: _render_badge folds it into the
                                          # switch's accessible description
        self.setObjectName("RowBorder")
        self.switch = ToggleSwitch()
        # The switch carries no text, so without a name a screen reader announces
        # the app's PRIMARY control as an unnamed check box (ONEUP-0028).
        self.switch.setAccessibleName(QCoreApplication.translate(
            "task_row",
            "{title} — include in this update").format(title=title))
        self.switch.setAccessibleDescription(description)

        self.name = ElidedLabel(title)
        self.name.setObjectName("TaskName")
        self.desc = ElidedLabel(description)
        self.desc.setObjectName("TaskDesc")

        # Never hidden, and as wide in the full form whatever it says: a badge that
        # appeared, or grew from "3/10" to "3 installed · 42s", moved the row's other
        # children. Empty, it paints nothing in its space.
        self.badge = ElidedLabel("")
        self.badge.setObjectName("Badge")
        self._badge_text = ""   # the outcome ("3 installed"); timing is appended
        self._timing = ""       # "42s" — kept apart so a repeated marker can't stack

        # This step's own progress. Its meaning is in the badge's words too, so the
        # bar is never the only signal (ui-and-accessibility.md §3).
        self.progress = _RowBar()
        self.progress.setObjectName("RowProgress")
        self.progress.setTextVisible(False)
        self.progress.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.progress.setAccessibleName(QCoreApplication.translate(
            "task_row", "Progress of {title}").format(title=title))
        self.clear_progress()

        self.card = QFrame()
        self.card.setObjectName("RowCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)  # 1px gradient border
        outer.setSpacing(0)
        outer.addWidget(self.card)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.form = ""
        self.set_form("full")

    # --- forms (ONEUP-0239 §4.1, §4.3) ----------------------------------------

    def set_form(self, form: str) -> None:
        """Arrange the row's own children for one layout. Never changes what the
        row holds: the badge, the switch and the bar keep their state."""
        if form not in FORMS:
            raise ValueError(form)
        old = self.card.layout()
        if old is not None:
            shiboken6.delete(old)       # a widget takes a new layout only once the old is gone
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(15, 12, 15, 10)
        lay.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(10)
        badge_policy = QSizePolicy.Policy.Fixed
        if form == "full":
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(self.name)
            text.addWidget(self.desc)
            top.addLayout(text, 1)
            top.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)
            top.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)
            lay.addLayout(top)
        else:
            top.addWidget(self.name, 1)
            top.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignTop)
            lay.addLayout(top)
            lay.addWidget(self.badge)
            badge_policy = QSizePolicy.Policy.Expanding   # as wide as the row, not its text
        lay.addWidget(self.progress)
        self.badge.setSizePolicy(badge_policy, QSizePolicy.Policy.Fixed)
        self.desc.setVisible(form == "full")
        # A tile names its step in a word (§4.3 Spotlight item 1).
        short = steps.SHORT_TITLES.get(self.key)
        self.name.setText(QCoreApplication.translate("steps", short)
                          if form == "tile" and short else self.title)
        self.form = form
        self.apply_metrics()

    def apply_metrics(self) -> None:
        """Sizes from the current font, never from the text (§4.2). Called again
        when the text size or the desktop font changes."""
        fm = self.badge.fontMetrics()
        m = self.badge.contentsMargins()
        self.badge.setMinimumWidth(
            fm.averageCharWidth() * _BADGE_CHARS + m.left() + m.right()
            if self.form == "full" else 0)
        # A tile's short title is never cut short (INV-17).
        self.name.setMinimumWidth(self.name.fontMetrics().horizontalAdvance(self.name.text())
                                  if self.form == "tile" else 0)

    # --- the row itself is the click target (ONEUP-0064) ---------------------
    # The switch is 56x30 in a row as wide as the window, so the wider the user
    # makes the window the smaller the fraction of a row that answers a click.
    # That ratio, not any one width, is the argument: the whole body now toggles.

    _EXCLUDED = ("switch", "badge")

    def _is_body(self, point) -> bool:
        """Is `point` in the row's BODY rather than one of its own controls?

        The switch is excluded so one click is not counted twice — it already
        handles its own, and a double toggle leaves the app's primary control
        looking dead rather than throwing. The badge is not clickable at all.
        """
        if not self.rect().contains(point):
            return False
        excluded = tuple(getattr(self, n) for n in self._EXCLUDED)
        w = self.childAt(point)
        while w is not None and w is not self:
            if w in excluded:
                return False
            w = w.parentWidget()
        return True

    def mousePressEvent(self, event):
        # Accepted here, not merely acted on in the release: a QFrame ignores a
        # press by default, and an ignored press means the release is delivered
        # to the parent instead and never reaches this row at all.
        if event.button() == Qt.MouseButton.LeftButton and self._is_body(
                event.position().toPoint()):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._is_body(
                event.position().toPoint()):
            # Inert while the switch is disabled — a run disables each switch but
            # leaves the row frame enabled, and a disabled ToggleSwitch still
            # emits `toggled` from toggle(); only click() is ignored. Without this
            # a user could re-select tasks mid-run by clicking a row's text.
            if self.switch.isEnabled():
                self.switch.toggle()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # --- progress (ONEUP-0239 §4.1, INV-11) ------------------------------------

    def progress_busy(self) -> None:
        self.progress.setRange(0, 0)

    def set_progress(self, done: int, total: int) -> None:
        """`done` of `total`; a total of 0 says nothing about how far, so the bar
        stays busy rather than divide by it."""
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(min(done, total))

    def progress_done(self) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(1)

    def clear_progress(self) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

    # --- the badge --------------------------------------------------------------

    def set_badge(self, text: str):
        self._badge_text = text
        self._render_badge()

    def set_timing(self, text: str):
        """Append how long the step took, e.g. '3 installed · 42s'."""
        self._timing = text
        self._render_badge()

    def _render_badge(self):
        parts = [p for p in (self._badge_text, self._timing) if p]
        text = QCoreApplication.translate(
            "task_row", "  ·  ", "separator between a row's outcome and its timing").join(parts)
        self.badge.setText(text)
        # The outcome otherwise lives only on an unfocusable label. Fold it into
        # the row's own control so a screen-reader user can Tab to it and hear
        # "System packages … 3 installed · 42s" (ONEUP-0028).
        self.switch.setAccessibleDescription(
            f"{self._description} {text}".strip() if text else self._description)

    def clear_badge(self):
        self._badge_text = ""
        self._timing = ""
        # Routed through _render_badge, not cleared inline: _launch calls this on
        # every row at the start of each run, and without the re-render the switch
        # would keep announcing the PREVIOUS run's outcome on a row that hasn't run.
        self._render_badge()
