"""Views of the package model, shared by the three layouts (ONEUP-0239 §4.3).

Every view reads `win.packages` and none writes it (INV-4). A view's item model
changes in place — rows inserted, removed and redrawn, never reset — so a package
arriving or changing state does not scroll the view the user is reading (INV-5).
Every package view shows each package's state as a word (INV-3).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from PySide6.QtCore import (
    Property,
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    QRect,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QListView,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

from . import i18n, steps, theme
from .markers import _format_size
from .packages import Package, PackageModel

# The three groups every count and the size strip use, by the state a view shows.
GROUP = {"queued": "togo", "downloading": "now", "downloaded": "now",
         "installed": "done", "removed": "done", "unchanged": "done"}

# Between the parts of one line of a package's text — name, versions, size, state.
# Layout between data; no language words it differently.
_PARTS = "  ·  "
# After the name of a package that has details: a shape, never only a colour
# (ONEUP-0260 §4.4). The words a screen reader hears replace it. U+2139, INFORMATION
# SOURCE, because Noto Sans draws it and no stock font draws U+24D8 (ONEUP-0297).
MARK = "\u2139"


def state_word(model: PackageModel, package: Package) -> str:
    return QCoreApplication.translate("steps", steps.STATE_WORDS[model.shown_state(package)])


def versions(package: Package) -> str:
    if package.old and package.edition:
        return QCoreApplication.translate("package_views", "{old} → {new}").format(
            old=package.old, new=package.edition)
    return package.edition or package.old


def join_parts(*parts: str) -> str:
    """The parts of one line of a package's text, the empty ones left out."""
    return _PARTS.join(p for p in parts if p)


def name_text(win, package: Package) -> str:
    """The package's name, marked when it has details to open (ONEUP-0260 §4.4)."""
    if not win.details.has_details(package):
        return package.name
    return QCoreApplication.translate(
        "package_views", "{name} \u2139", "a package name, marked as having details"
    ).format(name=package.name)


def size_text(package: Package) -> str:
    return _format_size(package.size) if package.size else ""


def counts(model: PackageModel, packages: list[Package]) -> dict[str, int]:
    out = {"done": 0, "now": 0, "togo": 0}
    for p in packages:
        out[GROUP[model.shown_state(p)]] += 1
    return out


def total_phrase(packages: list[Package]) -> str:
    """The packages' total size. A total counts only known sizes, and says so."""
    total = sum(p.size for p in packages)
    unknown = any(not p.size for p in packages)
    if not total:
        return QCoreApplication.translate("package_views", "size not known") if unknown else ""
    if unknown:
        return QCoreApplication.translate("package_views", "{size}, some sizes not known").format(
            size=_format_size(total))
    return _format_size(total)


def summary_sentence(what: str, packages: list[Package]) -> str:
    """What is shown, how many, and their size: "System packages · 24 updates ·
    17.5 MiB". It names the filter or the step in words, never by a look alone."""
    count = i18n.counted("package-count", len(packages))
    size = total_phrase(packages)
    if size:
        return QCoreApplication.translate("package_views", "{what} · {count} · {size}").format(
            what=what, count=count, size=size)
    return QCoreApplication.translate("package_views", "{what} · {count}").format(
        what=what, count=count)


def counts_sentence(c: dict[str, int]) -> str:
    return QCoreApplication.translate(
        "package_views", "{done} done · {now} now · {togo} to go").format(**c)


def empty_sentence(win) -> str:
    """What a package page says while it has no packages (§4.3.1)."""
    if win.engine_finished:
        return QCoreApplication.translate("package_views", "No package updates.")
    if win._liveness_active:
        return ""
    return QCoreApplication.translate(
        "package_views", "Press Check for updates to see what will change.")


class PackageItems(QAbstractTableModel):
    """A list of packages for one view, one column per `columns` entry."""

    def __init__(self, model: PackageModel, columns: list[Callable[[Package], str]],
                 headers: list[str] | None = None, *,
                 has_details: Callable[[Package], bool] | None = None,
                 mark_column: int = 0) -> None:
        super().__init__()
        self._model = model
        self._columns = columns
        self._headers = headers or []
        self._rows: list[Package] = []
        # The column carrying the details mark, and what says a package has one.
        self._has_details = has_details
        self._mark_column = mark_column

    def rowCount(self, parent=QModelIndex()):   # noqa: B008 — Qt's signature
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):   # noqa: B008 — Qt's signature
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return self._columns[index.column()](self._rows[index.row()])
        if (role == Qt.ItemDataRole.AccessibleTextRole and self._has_details is not None
                and index.column() == self._mark_column
                and self._has_details(self._rows[index.row()])):
            text = self._columns[index.column()](self._rows[index.row()])
            return QCoreApplication.translate(
                "package_views", "{text}, details available").format(
                text=text.replace(MARK, "").strip())
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal
                and section < len(self._headers)):
            return self._headers[section]
        return None

    def packages(self) -> list[Package]:
        return list(self._rows)

    def set_packages(self, new: list[Package]) -> None:
        """Become `new`, by inserting and removing rows — never a reset, which
        would throw away the view's scroll position. `new` and the rows held are
        both in the model's engine order, so the rows kept are a subsequence of it."""
        keep = {id(p) for p in new}
        i = len(self._rows) - 1
        while i >= 0:
            if id(self._rows[i]) in keep:
                i -= 1
                continue
            j = i
            while j > 0 and id(self._rows[j - 1]) not in keep:
                j -= 1
            self.beginRemoveRows(QModelIndex(), j, i)
            del self._rows[j:i + 1]
            self.endRemoveRows()
            i = j - 1
        k = 0
        n = 0
        while n < len(new):
            if k < len(self._rows) and self._rows[k] is new[n]:
                k += 1
                n += 1
                continue
            run = n
            while run < len(new) and not (k < len(self._rows) and self._rows[k] is new[run]):
                run += 1
            self.beginInsertRows(QModelIndex(), k, k + run - n - 1)
            self._rows[k:k] = new[n:run]
            self.endInsertRows()
            k += run - n
            n = run
        if self._rows:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._rows) - 1, len(self._columns) - 1))


class LinesDelegate(QStyledItemDelegate):
    """Draws an item's text one line at a time, each through Qt's own item drawing.

    It sizes an item from the font — a fixed number of lines, and on a board the
    grid's width — and elides each line on its own. It drops the focus frame Qt
    draws on the current item: a ring, which the app never draws
    (`ui-and-accessibility.md` §5). Handing each line to the style keeps Qt's
    eliding and its right-to-left mirroring, which is why this is not a painter of
    its own.
    """

    def __init__(self, lines: int, parent=None) -> None:
        super().__init__(parent)
        self._lines = lines

    def _line_height(self, option) -> int:
        return option.fontMetrics.lineSpacing()

    def height(self, fm) -> int:
        """An item's height in the font `fm`."""
        return self._lines * fm.lineSpacing() + 8

    def sizeHint(self, option, index) -> QSize:
        base = super().sizeHint(option, index)
        # On a board the grid sets a card's width, never its text: a card as wide
        # as its longest line ran into the next card. Its lines elide instead.
        # A plain list's line asks for no width: Qt makes it as wide as the list, so a
        # long line elides rather than scrolling the list sideways (ONEUP-0312).
        view = self.parent()
        grid = view.gridSize() if isinstance(view, QListView) else QSize()
        if grid.isValid():
            width = grid.width() - 8
        else:
            width = 0 if isinstance(view, QListView) else base.width()
        return QSize(width, self.height(option.fontMetrics))

    @staticmethod
    def _current(opt, index) -> bool:
        """The view has focus and this is its current package. A table's current
        index is one cell; its whole row is the package, so the row is current."""
        view = opt.widget
        if not isinstance(view, QAbstractItemView) or not view.hasFocus():
            return False
        current = view.currentIndex()
        return current.isValid() and current.row() == index.row()

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        current = self._current(opt, index)
        # initStyleOption has already turned each newline into U+2028.
        lines = (opt.text or "").replace("\u2028", "\n").split("\n")
        style = opt.widget.style() if opt.widget else QApplication.style()
        # The item's own ground once, then each line with no ground of its own.
        ground = QStyleOptionViewItem(opt)
        ground.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, ground, painter, opt.widget)
        if current:
            # The derived focus fill and ink, which the sheet hands the view as its
            # selection colours (ONEUP-0260 §4.5). A fill, never a ring.
            painter.fillRect(opt.rect, opt.palette.color(QPalette.ColorRole.Highlight))
            opt.palette.setColor(QPalette.ColorRole.Text,
                                 opt.palette.color(QPalette.ColorRole.HighlightedText))
        h = self._line_height(opt)
        top = opt.rect.top() + (opt.rect.height() - h * len(lines)) // 2
        for n, line in enumerate(lines):
            one = QStyleOptionViewItem(opt)
            one.text = line
            one.backgroundBrush = QBrush()
            one.state &= ~QStyle.StateFlag.State_Selected
            one.rect = QRect(opt.rect.left(), top + n * h, opt.rect.width(), h)
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, one, painter, opt.widget)


def _quiet(view: QAbstractItemView, lines: int) -> None:
    """What every package view shares: nothing to edit or select, no focus frame."""
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    view.setTextElideMode(Qt.TextElideMode.ElideRight)
    view.setItemDelegate(LinesDelegate(lines, view))
    view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


def package_table(items: PackageItems, name: str) -> QTableView:
    """Rows' table: state, package with its source under the name, versions, size."""
    view = QTableView()
    view.setObjectName("PackageTable")
    view.setAccessibleName(name)
    view.setModel(items)
    _quiet(view, 2)
    view.setShowGrid(False)
    view.setWordWrap(False)
    view.verticalHeader().setVisible(False)
    view.horizontalHeader().setStretchLastSection(False)
    view.horizontalHeader().setSectionResizeMode(1, view.horizontalHeader().ResizeMode.Stretch)
    return view


def package_board(items: PackageItems, name: str) -> QListView:
    """Rail's board: one card per package, three lines each, wrapping in rows."""
    view = QListView()
    view.setObjectName("PackageBoard")
    view.setAccessibleName(name)
    view.setModel(items)
    _quiet(view, 3)
    view.setFlow(QListView.Flow.LeftToRight)
    view.setWrapping(True)
    view.setResizeMode(QListView.ResizeMode.Adjust)
    view.setMovement(QListView.Movement.Static)
    view.setUniformItemSizes(True)
    return view


def package_list(items: PackageItems, name: str) -> QListView:
    """One of Spotlight's two lists: one line per package."""
    view = QListView()
    view.setObjectName("PackageLists")
    view.setAccessibleName(name)
    view.setModel(items)
    _quiet(view, 1)
    view.setUniformItemSizes(True)
    return view


def fit_board(view: QListView) -> None:
    """A card's size, from the font: three lines tall, a fixed number of
    characters wide. Called again when the text size changes."""
    fm = view.fontMetrics()
    view.setGridSize(QSize(fm.averageCharWidth() * 26, fm.lineSpacing() * 3 + 16))


def hold_rows(view: QAbstractItemView, rows: int, row: int) -> None:
    """Room for `rows` of the view's own rows, each `row` tall, below its header and
    inside its frame: the layout's floor (ONEUP-0239 §4.2 item 2)."""
    header = 0
    if isinstance(view, QTableView) and not view.horizontalHeader().isHidden():
        header = view.horizontalHeader().sizeHint().height()
    view.setMinimumHeight(rows * row + header + 2 * view.frameWidth())
    # Qt stops passing a size change up at a hidden widget — Spotlight's lists, while
    # the page shows its sentence — so the window would measure its minimum without
    # this floor. Drop every cached size from the view up to the window instead.
    node = view
    while node is not None:
        node.updateGeometry()
        if node.layout() is not None:
            _invalidate(node.layout())
        node = node.parentWidget()


def _invalidate(layout) -> None:
    """A layout's cached sizes, and those of every layout nested in it."""
    layout.invalidate()
    for i in range(layout.count()):
        child = layout.itemAt(i).layout()
        if child is not None:
            _invalidate(child)


class _Sentence(QLabel):
    """A wrapping label that does not ask its layout for height-for-width.

    QLabel turns height-for-width on with word wrap, again on every new text and
    font. Inside the package area that switched the whole window into Qt's
    height-for-width pass, which at the window's minimum squeezed Spotlight's
    fixed-height panel whenever the sentence page was current (ONEUP-0239 INV-1).
    The area's own height is set by the font (§4.2), so the sentence needs none.
    """

    def _drop_height_for_width(self) -> None:
        policy = self.sizePolicy()
        if policy.hasHeightForWidth():
            policy.setHeightForWidth(False)
            self.setSizePolicy(policy)

    def setText(self, text: str) -> None:
        super().setText(text)
        self._drop_height_for_width()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        self._drop_height_for_width()


class EmptyOr(QStackedWidget):
    """A view, or the one sentence a page shows in place of an empty one."""

    def __init__(self, content: QWidget) -> None:
        super().__init__()
        self.content = content
        self.sentence = _Sentence("")
        self.sentence.setObjectName("Tagline")
        self.sentence.setWordWrap(True)
        self.sentence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sentence.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.addWidget(content)
        self.addWidget(self.sentence)

    def show_packages(self, any_packages: bool, sentence: str) -> None:
        self.sentence.setText(sentence)
        self.setCurrentWidget(self.content if any_packages else self.sentence)


class SizeStrip(QWidget):
    """Rail's size strip: one block per package, in engine order, each as wide as
    its share of the download (§4.3.2).

    State is never colour alone: each group has its own fill, and every block is
    drawn in one ink. Blocks run in the reading direction, which the strip reads
    from the application as `ToggleSwitch` does (`ui-and-accessibility.md` §8.3).
    """

    FILLS: ClassVar[dict[str, Qt.BrushStyle]] = {
        "done": Qt.BrushStyle.SolidPattern, "now": Qt.BrushStyle.BDiagPattern,
        "togo": Qt.BrushStyle.NoBrush}
    MIN_BLOCK = 2     # pixels: the narrowest block, which a package of unknown size gets

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("SizeStrip")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._blocks: list[tuple[str, int]] = []
        # Set from the stylesheet; this default only shows before the sheet arrives.
        self._ink = QColor(theme.current_palette()["tname"])

    def get_ink(self) -> QColor:
        return self._ink

    def set_ink(self, colour) -> None:
        self._ink = QColor(colour)
        self.update()

    ink = Property(QColor, get_ink, set_ink)

    def sizeHint(self) -> QSize:
        return QSize(self.fontMetrics().averageCharWidth() * 10, self.fontMetrics().height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def set_blocks(self, blocks: list[tuple[str, int]]) -> None:
        """(group, size in bytes) per package, in engine order."""
        self._blocks = blocks
        self.update()

    def _laid_out(self) -> list[tuple[str, int]]:
        """Neighbouring blocks of one group merge when there are more blocks than
        the strip has room for at the narrowest width."""
        if len(self._blocks) * self.MIN_BLOCK <= self.width():
            return self._blocks
        merged: list[tuple[str, int]] = []
        for group, size in self._blocks:
            if merged and merged[-1][0] == group:
                merged[-1] = (group, merged[-1][1] + size)
            else:
                merged.append((group, size))
        return merged

    def paintEvent(self, _event) -> None:
        blocks = self._laid_out()
        if not blocks:
            return
        p = QPainter(self)
        width, height = self.width(), self.height()
        spare = max(0, width - len(blocks) * self.MIN_BLOCK)
        total = sum(size for _g, size in blocks)
        rtl = QApplication.isRightToLeft()
        x = 0.0
        for group, size in blocks:
            share = (size / total) if total else (1 / len(blocks))
            w = self.MIN_BLOCK + spare * share
            left = width - x - w if rtl else x
            rect = QRectF(left, 0, w, height).adjusted(0.5, 0.5, -0.5, -0.5)
            p.setPen(QPen(self._ink, 1))
            p.setBrush(QBrush(self._ink, self.FILLS[group]))
            p.drawRect(rect)
            x += w


class _Swatch(QWidget):
    """One group's fill in the legend, beside its word."""

    def __init__(self, strip: SizeStrip, group: str) -> None:
        super().__init__()
        self._strip = strip
        self._group = group
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        h = self.fontMetrics().height()
        return QSize(h * 2, h)

    def paintEvent(self, _event) -> None:
        # Symmetric, so it needs no direction of its own.
        p = QPainter(self)
        ink = self._strip.get_ink()
        p.setPen(QPen(ink, 1))
        p.setBrush(QBrush(ink, SizeStrip.FILLS[self._group]))
        p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))


def strip_legend(strip: SizeStrip) -> QWidget:
    """Each fill beside its word, so the strip never relies on its fills alone."""
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    for group, word in (("done", QCoreApplication.translate("package_views", "done")),
                        ("now", QCoreApplication.translate("package_views", "now")),
                        ("togo", QCoreApplication.translate("package_views", "to go"))):
        lay.addWidget(_Swatch(strip, group))
        label = QLabel(word)
        label.setObjectName("Tagline")
        lay.addWidget(label)
        lay.addSpacing(8)
    lay.addStretch(1)
    return box
