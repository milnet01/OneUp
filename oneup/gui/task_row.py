"""One task's row: its switch, badge, timing and details."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
)

from .toggle_switch import ToggleSwitch


class TaskRow(QFrame):
    """One task, drawn as a card with a hover-lit gradient border: the 1px
    outer frame shows the accent gradient, an inner card sits 1px inside it. A
    badge on the right shows how many updates a --check found; an expandable
    panel below lists the exact packages that will change (fed by the engine's
    @@CHECK_ITEM@@ markers), with a "Show download size" link on the system row."""

    # Emitted when the user clicks "Show download size"; carries the step key.
    size_requested = Signal(str)

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
        self.switch.setAccessibleName(f"{title} — include in this update")
        self.switch.setAccessibleDescription(description)

        name = QLabel(title)
        name.setObjectName("TaskName")
        desc = QLabel(description)
        desc.setObjectName("TaskDesc")
        desc.setWordWrap(True)

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(name)
        text.addWidget(desc)

        self.badge = QLabel("")
        self.badge.setObjectName("Badge")
        self.badge.setVisible(False)
        self._badge_text = ""   # the outcome ("3 installed"); timing is appended
        self._timing = ""       # "42s" — kept apart so a repeated marker can't stack

        # Disclosure arrow: revealed only once there are detail items to show.
        self.disclosure = QToolButton()
        self.disclosure.setObjectName("Disclose")
        self.disclosure.setArrowType(Qt.ArrowType.RightArrow)
        self.disclosure.setCheckable(True)
        self.disclosure.setCursor(Qt.CursorShape.PointingHandCursor)
        self.disclosure.setVisible(False)
        self.disclosure.toggled.connect(self._on_disclosure)
        # An arrow-only button is unnamed to a screen reader. State-agnostic
        # wording, since the control toggles — Qt reports expanded/collapsed itself.
        self.disclosure.setAccessibleName(f"Packages that {title.lower()} will change")

        inner = QFrame()
        inner.setObjectName("RowCard")
        row = QHBoxLayout(inner)
        row.setContentsMargins(15, 12, 15, 12)
        row.setSpacing(10)
        row.addLayout(text, 1)
        row.addWidget(self.badge, 0, Qt.AlignVCenter)
        row.addWidget(self.disclosure, 0, Qt.AlignVCenter)
        row.addWidget(self.switch, 0, Qt.AlignVCenter)

        # Collapsible detail panel: the changed-package list, plus (system only)
        # a link that fetches the exact download size on demand.
        self._items: list[str] = []
        self.details = QFrame()
        self.details.setObjectName("RowDetails")
        self.details.setVisible(False)
        dcol = QVBoxLayout(self.details)
        dcol.setContentsMargins(16, 0, 16, 12)
        dcol.setSpacing(8)

        self._items_label = QLabel("")
        self._items_label.setObjectName("DetailList")
        self._items_label.setTextFormat(Qt.TextFormat.PlainText)
        scroll = QScrollArea()
        scroll.setObjectName("DetailScroll")
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(180)
        scroll.setWidget(self._items_label)
        # Focusable (it scrolls), so it needs a name of its own — the arrow key
        # user lands here and would otherwise hear an unnamed scroll area.
        scroll.setAccessibleName(f"List of packages that {title.lower()} will change")
        dcol.addWidget(scroll)

        self.size_btn = QPushButton("Show download size")
        self.size_btn.setObjectName("LinkBtn")
        self.size_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.size_btn.clicked.connect(lambda: self.size_requested.emit(self.key))
        self.size_result = QLabel("")
        self.size_result.setObjectName("SizeResult")
        self.size_result.setVisible(False)
        self._has_size = False  # explicit — survives the panel being collapsed
        if key == "system":
            srow = QHBoxLayout()
            srow.setSpacing(10)
            srow.addWidget(self.size_btn, 0)
            srow.addWidget(self.size_result, 0)
            srow.addStretch(1)
            dcol.addLayout(srow)
        else:
            self.size_btn.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)  # 1px gradient border
        outer.setSpacing(0)
        outer.addWidget(inner)
        outer.addWidget(self.details)

    def _on_disclosure(self, on: bool):
        self.details.setVisible(on)
        self.disclosure.setArrowType(
            Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)

    def add_detail_item(self, name: str, frm: str, to: str):
        """Append one changed package to the panel (name  old → new)."""
        line = f"{name:<32}  {frm}  →  {to}" if (frm or to) else name
        self._items.append(line)
        self._items_label.setText("\n".join(self._items))
        self.disclosure.setVisible(True)

    def set_size_result(self, text: str):
        """Show the download-size figure and retire the "Show download size" link."""
        self.size_btn.setVisible(False)
        self.size_result.setText(text)
        self.size_result.setVisible(True)
        self._has_size = True

    def size_pending(self):
        # Name the expected wait. Getting the figure means asking zypper's solver to
        # work out the WHOLE transaction (a --dry-run), which takes tens of seconds
        # on a big Tumbleweed upgrade; a bare "Calculating…" for that long reads as
        # a hung button, so the label says up front that it's normal.
        self.size_btn.setEnabled(False)
        self.size_btn.setText("Calculating… (up to a minute)")

    def size_failed(self):
        """Re-arm the link so the user can retry after a failed size fetch."""
        self.size_btn.setEnabled(True)
        self.size_btn.setText("Show download size")

    def has_size(self) -> bool:
        return self._has_size

    def set_badge(self, text: str):
        self._badge_text = text
        self._render_badge()

    def set_timing(self, text: str):
        """Append how long the step took, e.g. '3 installed · 42s'."""
        self._timing = text
        self._render_badge()

    def _render_badge(self):
        parts = [p for p in (self._badge_text, self._timing) if p]
        text = "  ·  ".join(parts)
        self.badge.setText(text)
        self.badge.setVisible(bool(parts))
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

    def clear_details(self):
        """Reset the expandable panel between runs."""
        self._items = []
        self._items_label.setText("")
        self.disclosure.setChecked(False)
        self.disclosure.setVisible(False)
        self.details.setVisible(False)
        self.size_result.setVisible(False)
        self.size_result.setText("")
        self._has_size = False
        if self.key == "system":
            self.size_btn.setVisible(True)
            self.size_btn.setEnabled(True)
            self.size_btn.setText("Show download size")
