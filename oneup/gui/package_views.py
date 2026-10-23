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
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QPainter,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QLayout,
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
# "Now" is only what is downloading: a downloaded package waiting to install is still
# to go (ONEUP-0239 §4.3.1, the user's decision of 2026-10-23).
GROUP = {"queued": "togo", "downloading": "now", "downloaded": "togo",
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


def downloading_now(win, package: Package) -> bool:
    """The package the last PKG line named, while its state is `downloading` (§4.3)."""
    return (win.latest_package == (package.key, package.name, package.edition)
            and win.packages.shown_state(package) == "downloading")


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


def download_sentence(packages: list[Package]) -> str:
    """How many, and what there is to download: "24 updates · 17.5 MiB to
    download" (§4.3 Rail). A total counts only known sizes, and says so."""
    count = i18n.counted("package-count", len(packages))
    total = sum(p.size for p in packages)
    unknown = any(not p.size for p in packages)
    if total and unknown:
        return QCoreApplication.translate(
            "package_views", "{count} · {size} to download, some sizes not known").format(
            count=count, size=_format_size(total))
    if total:
        return QCoreApplication.translate(
            "package_views", "{count} · {size} to download").format(
            count=count, size=_format_size(total))
    if unknown:
        return QCoreApplication.translate("package_views", "{count} · size not known").format(
            count=count)
    return count


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


# True on every cell of a package whose row is drawn highlighted.
NOW_ROLE = Qt.ItemDataRole.UserRole + 1
# The package itself, for a delegate that lays out its parts (CardDelegate).
PACKAGE_ROLE = Qt.ItemDataRole.UserRole + 2


class PackageItems(QAbstractTableModel):
    """A list of packages for one view, one column per `columns` entry."""

    def __init__(self, model: PackageModel, columns: list[Callable[[Package], str]],
                 headers: list[str] | None = None, *,
                 has_details: Callable[[Package], bool] | None = None,
                 mark_column: int = 0,
                 now: Callable[[Package], bool] | None = None) -> None:
        super().__init__()
        self._model = model
        self._columns = columns
        self._headers = headers or []
        self._rows: list[Package] = []
        # The column carrying the details mark, and what says a package has one.
        self._has_details = has_details
        self._mark_column = mark_column
        # What says a package's row is drawn highlighted (NOW_ROLE).
        self._now = now

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
        if role == NOW_ROLE:
            return self._now is not None and self._now(self._rows[index.row()])
        if role == PACKAGE_ROLE:
            return self._rows[index.row()]
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

    def _ground(self, painter, option, index) -> tuple[QStyleOptionViewItem, list[str]]:
        """Paint the item's ground, and its focus fill when current; return the
        option its text is drawn with, and that text's lines."""
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        # initStyleOption has already turned each newline into U+2028.
        lines = (opt.text or "").replace("\u2028", "\n").split("\n")
        ground = QStyleOptionViewItem(opt)
        ground.text = ""
        _style(opt).drawControl(QStyle.ControlElement.CE_ItemViewItem, ground, painter,
                                opt.widget)
        view = self.parent()
        if index.data(NOW_ROLE) and isinstance(view, PackageTable):
            # The package downloading now: a fill and its ink from the sheet. The
            # focus fill below still wins on the current package.
            painter.fillRect(opt.rect, view.get_now_fill())
            opt.palette.setColor(QPalette.ColorRole.Text, view.get_now_ink())
        if self._current(opt, index):
            # The derived focus fill and ink, which the sheet hands the view as its
            # selection colours (ONEUP-0260 §4.5). A fill, never a ring.
            painter.fillRect(opt.rect, opt.palette.color(QPalette.ColorRole.Highlight))
            opt.palette.setColor(QPalette.ColorRole.Text,
                                 opt.palette.color(QPalette.ColorRole.HighlightedText))
        return opt, lines

    @staticmethod
    def _line(painter, opt, text: str, rect: QRect) -> None:
        """One line of text in `rect`, through the style, with no ground of its own."""
        one = QStyleOptionViewItem(opt)
        one.text = text
        one.backgroundBrush = QBrush()
        one.state &= ~QStyle.StateFlag.State_Selected
        one.rect = rect
        _style(opt).drawControl(QStyle.ControlElement.CE_ItemViewItem, one, painter, opt.widget)

    def paint(self, painter, option, index) -> None:
        opt, lines = self._ground(painter, option, index)
        h = self._line_height(opt)
        top = opt.rect.top() + (opt.rect.height() - h * len(lines)) // 2
        for n, line in enumerate(lines):
            self._line(painter, opt, line,
                       QRect(opt.rect.left(), top + n * h, opt.rect.width(), h))


def _direction() -> Qt.LayoutDirection:
    """The application's reading direction, read as `ToggleSwitch` reads it
    (`ui-and-accessibility.md` §8.3), never a widget's own."""
    return (Qt.LayoutDirection.RightToLeft if QApplication.isRightToLeft()
            else Qt.LayoutDirection.LeftToRight)


def _style(opt) -> QStyle:
    return opt.widget.style() if opt.widget else QApplication.style()


def fixed_font(font: QFont) -> QFont:
    """The desktop's fixed-pitch font at `font`'s size, so it follows the text size."""
    fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    if font.pointSizeF() > 0:
        fixed.setPointSizeF(font.pointSizeF())
    else:
        fixed.setPixelSize(font.pixelSize())
    return fixed


class FixedPitchDelegate(LinesDelegate):
    """Rows' versions: one line, old → new, in the fixed-pitch font (§4.3)."""

    def __init__(self, parent=None) -> None:
        super().__init__(1, parent)

    def height(self, fm) -> int:
        view = self.parent()
        fixed = QFontMetrics(fixed_font(view.font())) if view else fm
        return max(fm.lineSpacing(), fixed.lineSpacing()) + 8

    def initStyleOption(self, option, index) -> None:
        super().initStyleOption(option, index)
        option.font = fixed_font(option.font)
        option.fontMetrics = QFontMetrics(option.font)


class SourceDelegate(LinesDelegate):
    """Rows' package cell: the name, then its source in a small rounded label on
    the same line (§4.3). The item's text is the name, then the source on a second
    line, so its tooltip and the words a screen reader hears carry both."""

    # The label elides past this many average character widths.
    SOURCE_CHARS = 16
    GAP = 8          # pixels between the name and its label

    def __init__(self, parent=None) -> None:
        super().__init__(1, parent)

    def paint(self, painter, option, index) -> None:
        opt, lines = self._ground(painter, option, index)
        name, source = lines[0], (lines[1] if len(lines) > 1 else "")
        rect = opt.rect
        if not source:
            self._line(painter, opt, name, rect)
            return
        font = QFont(opt.font)
        font.setWeight(QFont.Weight.DemiBold)
        lfm = QFontMetrics(font)
        text = lfm.elidedText(source, Qt.TextElideMode.ElideRight,
                              lfm.averageCharWidth() * self.SOURCE_CHARS)
        pad = lfm.averageCharWidth()
        label_w = min(lfm.horizontalAdvance(text) + 2 * pad, rect.width() // 2)
        label_h = lfm.height() + 4
        # The name's natural width, asked of the style that draws it: its margins
        # around item text are its own, and a guess at them elided short names.
        alone = QStyleOptionViewItem(opt)
        alone.text = name
        natural = _style(opt).sizeFromContents(QStyle.ContentsType.CT_ItemViewItem, alone,
                                               QSize(), opt.widget).width()
        name_w = min(natural, rect.width() - label_w - self.GAP)
        # Laid out in reading order, then mirrored when the view runs right to left.
        name_rect = QStyle.visualRect(opt.direction, rect,
                                      QRect(rect.left(), rect.top(), name_w, rect.height()))
        label = QStyle.visualRect(opt.direction, rect, QRect(
            rect.left() + name_w + self.GAP, rect.top() + (rect.height() - label_h) // 2,
            label_w, label_h))
        self._line(painter, opt, name, name_rect)
        view = self.parent()
        fill, ink, rim = view.get_label_fill(), view.get_label_ink(), view.get_label_rim()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(rim, 1))
        painter.setBrush(fill)
        radius = label_h / 3
        painter.drawRoundedRect(QRectF(label).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        painter.setFont(font)
        painter.setPen(ink)
        painter.drawText(label, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


class CardDelegate(LinesDelegate):
    """Rail's card (§4.3 Rail): a state dot, then the name with its size at the
    trailing end; the versions in the fixed-pitch font; the source label with the
    state word at the trailing end. The item's text — its tooltip and the words a
    screen reader hears — stays the lines the model gives; the parts are read from
    the package, through `parts`."""

    GAP = 8     # pixels between neighbouring cards
    PAD = 10    # inside the card's rim
    RIM = 2     # every card's rim, so the accent one moves nothing
    SPACE = 4   # between the card's lines
    SIZE_TEXT = "999.9 MiB"    # the widest size, which sets the size's place

    def __init__(self, parts: Callable[[Package], tuple[str, str, str, str, str, str]],
                 parent=None) -> None:
        super().__init__(3, parent)
        # The name, size, versions, source and state word, and the state's GROUP.
        self._parts = parts

    @staticmethod
    def fonts(view) -> dict[str, QFont]:
        base = view.font()
        bold = QFont(base)
        bold.setWeight(QFont.Weight.DemiBold)
        return {"name": bold, "body": QFont(base), "versions": fixed_font(base), "label": bold}

    def _line_heights(self, view) -> tuple[int, int, int]:
        """The height of each of the card's three lines."""
        f = self.fonts(view)
        return (QFontMetrics(f["name"]).lineSpacing(),
                QFontMetrics(f["versions"]).lineSpacing(),
                max(QFontMetrics(f["label"]).height() + 4,
                    QFontMetrics(f["body"]).lineSpacing()))

    def card_height(self, view) -> int:
        return self.GAP + 2 * self.PAD + 2 * self.SPACE + sum(self._line_heights(view))

    def height(self, fm) -> int:
        return self.card_height(self.parent())

    def card_rects(self, view, cell: QRect) -> dict[str, QRect]:
        """Where each part of the card in `cell` goes, mirrored for a right-to-left
        view. The source label's is the most it may take."""
        f = self.fonts(view)
        body, label = QFontMetrics(f["body"]), QFontMetrics(f["label"])
        half = self.GAP // 2
        card = cell.adjusted(half, half, half - self.GAP, half - self.GAP)
        inner = card.adjusted(self.PAD, self.PAD, -self.PAD, -self.PAD)
        left, right, width = inner.left(), inner.right(), inner.width()
        one, two, three = self._line_heights(view)
        dot = QFontMetrics(f["name"]).height() // 2
        size_w = body.horizontalAdvance(self.SIZE_TEXT)
        state_w = max(body.horizontalAdvance(QCoreApplication.translate("steps", w))
                      for w in steps.STATE_WORDS.values())
        y1 = inner.top()
        y2 = y1 + one + self.SPACE
        y3 = y2 + two + self.SPACE
        label_w = min(label.averageCharWidth() * (SourceDelegate.SOURCE_CHARS + 2),
                      width - state_w - self.SPACE)
        rects = {
            "card": card,
            "dot": QRect(left, y1 + (one - dot) // 2, dot, dot),
            "name": QRect(left + dot + 6, y1, width - dot - 6 - size_w - 8, one),
            "size": QRect(right - size_w + 1, y1, size_w, one),
            "versions": QRect(left, y2, width, two),
            "label": QRect(left, y3, max(label_w, 0), three),
            "state": QRect(right - state_w + 1, y3, state_w, three),
        }
        return {k: QStyle.visualRect(_direction(), cell, r) for k, r in rects.items()}

    def sizeHint(self, option, index) -> QSize:
        view = self.parent()
        return QSize(view.gridSize().width(), self.card_height(view))

    def paint(self, painter, option, index) -> None:
        view = self.parent()
        package = index.data(PACKAGE_ROLE)
        if package is None:
            return
        name, size, versions_, source, state, group = self._parts(package)
        r = self.card_rects(view, option.rect)
        f = self.fonts(view)
        ink = option.palette.color(QPalette.ColorRole.Text)
        current = self._current(option, index)
        # Leading and trailing, which the painter mirrors with the window.
        lead, trail = Qt.AlignmentFlag.AlignLeading, Qt.AlignmentFlag.AlignTrailing
        middle = Qt.AlignmentFlag.AlignVCenter
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # The rim, in the accent while this is the package downloading now. When the
        # card is current, the derived focus fill and its ink (ONEUP-0260 §4.5) —
        # a fill, never a ring.
        rim = view.get_now_fill() if index.data(NOW_ROLE) else view.get_rim()
        fill = QBrush()
        if current:
            fill = QBrush(option.palette.color(QPalette.ColorRole.Highlight))
            ink = option.palette.color(QPalette.ColorRole.HighlightedText)
        painter.setPen(QPen(rim, self.RIM))
        painter.setBrush(fill)
        edge = self.RIM / 2
        painter.drawRoundedRect(QRectF(r["card"]).adjusted(edge, edge, -edge, -edge), 8, 8)
        # The dot, filled as the size strip fills the package's group: a shape, as
        # well as a colour, and the state word says it again.
        painter.setPen(QPen(ink, 1))
        painter.setBrush({"done": view.get_done_fill(), "now": view.get_now_fill()}
                         .get(group, QBrush()))
        painter.drawEllipse(QRectF(r["dot"]).adjusted(0.5, 0.5, -0.5, -0.5))

        def text(rect, font, words, align):
            fm = QFontMetrics(font)
            painter.setFont(font)
            painter.drawText(rect, int(align | middle),
                             fm.elidedText(words, Qt.TextElideMode.ElideRight, rect.width()))

        painter.setPen(ink)
        text(r["name"], f["name"], name, lead)
        text(r["size"], f["body"], size, trail)
        text(r["versions"], f["versions"], versions_, lead)
        text(r["state"], f["body"], state, trail)
        if source:
            lfm = QFontMetrics(f["label"])
            pad = lfm.averageCharWidth()
            shown = lfm.elidedText(source, Qt.TextElideMode.ElideRight,
                                   max(r["label"].width() - 2 * pad, 0))
            tag = QRect(r["label"])
            tag.setWidth(min(lfm.horizontalAdvance(shown) + 2 * pad, r["label"].width()))
            tag.setHeight(lfm.height() + 4)
            tag.moveTop(r["label"].top() + (r["label"].height() - tag.height()) // 2)
            if QApplication.isRightToLeft():
                tag.moveRight(r["label"].right())
            # On the focus fill the label is ringed in its ink, as the overlay's is.
            painter.setPen(QPen(ink if current else view.get_label_rim(), 1))
            painter.setBrush(QBrush() if current else QBrush(view.get_label_fill()))
            radius = tag.height() / 3
            painter.drawRoundedRect(QRectF(tag).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
            painter.setPen(ink if current else view.get_label_ink())
            painter.setFont(f["label"])
            painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, shown)
        painter.restore()


class ListLineDelegate(LinesDelegate):
    """Spotlight's list line (§4.3 Spotlight item 3): the state, the name, and the
    size at the trailing end. Until the drawn state symbols land (ONEUP-0322), the
    state word stands where the symbol goes, as it does in Rows. The item's text —
    its tooltip and the words a screen reader hears — stays the whole line."""

    GAP = 8     # pixels between the parts, and inside the line's ends

    def __init__(self, parts: Callable[[Package], tuple[str, str, str]], parent=None) -> None:
        super().__init__(1, parent)
        # The state word, the name and the size.
        self._parts = parts

    def line_rects(self, view, cell: QRect) -> dict[str, QRect]:
        """Where each part of the line in `cell` goes, mirrored for a right-to-left
        view. The state and the size take their widest text, so neither moves."""
        fm = view.fontMetrics()
        inner = cell.adjusted(self.GAP, 0, -self.GAP, 0)
        # The style draws each part inside its own text margin, one per side.
        pad = 2 * (view.style().pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None,
                                            view) + 1)
        state_w = pad + max(fm.horizontalAdvance(QCoreApplication.translate("steps", w))
                            for w in steps.STATE_WORDS.values())
        size_w = pad + fm.horizontalAdvance(CardDelegate.SIZE_TEXT)
        left, top, h = inner.left(), inner.top(), inner.height()
        rects = {
            "state": QRect(left, top, state_w, h),
            "name": QRect(left + state_w + self.GAP, top,
                          max(inner.width() - state_w - size_w - 2 * self.GAP, 0), h),
            "size": QRect(inner.right() - size_w + 1, top, size_w, h),
        }
        return {k: QStyle.visualRect(_direction(), cell, r) for k, r in rects.items()}

    def paint(self, painter, option, index) -> None:
        package = index.data(PACKAGE_ROLE)
        if package is None:
            return
        opt, _lines = self._ground(painter, option, index)
        state, name, size = self._parts(package)
        r = self.line_rects(self.parent(), opt.rect)
        lead, trail = Qt.AlignmentFlag.AlignLeading, Qt.AlignmentFlag.AlignTrailing
        for text, rect, align in ((state, r["state"], lead), (name, r["name"], lead),
                                  (size, r["size"], trail)):
            one = QStyleOptionViewItem(opt)
            one.displayAlignment = align | Qt.AlignmentFlag.AlignVCenter
            self._line(painter, one, text, rect)


class PackageTable(QTableView):
    """Rows' table. Its source labels and the downloading package's row are
    painted, so their colours arrive from the stylesheet as properties, as the
    size strip's ink does."""

    def __init__(self) -> None:
        super().__init__()
        # Set from the stylesheet; these defaults only show before the sheet arrives.
        p = theme.current_palette()
        self._label = {"fill": QColor(p["badgebg"]), "ink": QColor(p["badgefg"]),
                       "rim": QColor(p["badgebg"]), "nowfill": QColor(p["ghosthov"]),
                       "nowink": QColor(p["tabink"])}

    def _set(self, part: str, colour) -> None:
        self._label[part] = QColor(colour)
        self.viewport().update()

    def get_label_fill(self) -> QColor:
        return self._label["fill"]

    def set_label_fill(self, colour) -> None:
        self._set("fill", colour)

    def get_label_ink(self) -> QColor:
        return self._label["ink"]

    def set_label_ink(self, colour) -> None:
        self._set("ink", colour)

    def get_label_rim(self) -> QColor:
        return self._label["rim"]

    def set_label_rim(self, colour) -> None:
        self._set("rim", colour)

    labelFill = Property(QColor, get_label_fill, set_label_fill)
    labelInk = Property(QColor, get_label_ink, set_label_ink)
    labelRim = Property(QColor, get_label_rim, set_label_rim)

    def get_now_fill(self) -> QColor:
        return self._label["nowfill"]

    def set_now_fill(self, colour) -> None:
        self._set("nowfill", colour)

    def get_now_ink(self) -> QColor:
        return self._label["nowink"]

    def set_now_ink(self, colour) -> None:
        self._set("nowink", colour)

    nowFill = Property(QColor, get_now_fill, set_now_fill)
    nowInk = Property(QColor, get_now_ink, set_now_ink)


class PackageBoard(QListView):
    """Rail's board: cards in two columns that share its width (§4.3 Rail). Its
    cards are painted, so their colours arrive from the stylesheet as properties,
    as the size strip's do."""

    MIN_CARD_CHARS = 22    # the narrowest card, in average character widths

    def __init__(self) -> None:
        super().__init__()
        # Set from the stylesheet; these defaults only show before the sheet arrives.
        p = theme.current_palette()
        self._colour = {"done": QColor(p["switchon"]), "now": QColor(p["ghosthov"]),
                        "rim": QColor(p["logbd"]), "fill": QColor(p["badgebg"]),
                        "ink": QColor(p["badgefg"]), "labelrim": QColor(p["badgebg"])}

    def _set(self, part: str, colour) -> None:
        self._colour[part] = QColor(colour)
        self.viewport().update()

    def get_done_fill(self) -> QColor:
        return self._colour["done"]

    def set_done_fill(self, colour) -> None:
        self._set("done", colour)

    def get_now_fill(self) -> QColor:
        return self._colour["now"]

    def set_now_fill(self, colour) -> None:
        self._set("now", colour)

    def get_rim(self) -> QColor:
        return self._colour["rim"]

    def set_rim(self, colour) -> None:
        self._set("rim", colour)

    def get_label_fill(self) -> QColor:
        return self._colour["fill"]

    def set_label_fill(self, colour) -> None:
        self._set("fill", colour)

    def get_label_ink(self) -> QColor:
        return self._colour["ink"]

    def set_label_ink(self, colour) -> None:
        self._set("ink", colour)

    def get_label_rim(self) -> QColor:
        return self._colour["labelrim"]

    def set_label_rim(self, colour) -> None:
        self._set("labelrim", colour)

    doneFill = Property(QColor, get_done_fill, set_done_fill)
    nowFill = Property(QColor, get_now_fill, set_now_fill)
    rim = Property(QColor, get_rim, set_rim)
    labelFill = Property(QColor, get_label_fill, set_label_fill)
    labelInk = Property(QColor, get_label_ink, set_label_ink)
    labelRim = Property(QColor, get_label_rim, set_label_rim)

    def fit(self) -> None:
        """Two cards to a row, each half the viewport wide; as tall as the font."""
        delegate = self.itemDelegate()
        if not isinstance(delegate, CardDelegate):
            return
        # Qt wraps a row whose cells reach the viewport's last pixel, so two cells
        # share one pixel less than the width.
        grid = QSize(max(1, (self.viewport().width() - 1) // 2), delegate.card_height(self))
        if grid != self.gridSize():
            self.setGridSize(grid)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit()


def row_height(view: QTableView) -> int:
    """A table row's height from the font: the tallest of its columns' lines."""
    fm = view.fontMetrics()
    delegates = [view.itemDelegateForColumn(c) or view.itemDelegate()
                 for c in range(view.model().columnCount())]
    return max(d.height(fm) for d in delegates)


def _quiet(view: QAbstractItemView, lines: int) -> None:
    """What every package view shares: nothing to edit or select, no focus frame."""
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    view.setTextElideMode(Qt.TextElideMode.ElideRight)
    view.setItemDelegate(LinesDelegate(lines, view))
    view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


def package_table(items: PackageItems, name: str) -> PackageTable:
    """Rows' table: state, package with its source label beside the name, versions
    in the fixed-pitch font, size. One line per package."""
    view = PackageTable()
    view.setObjectName("PackageTable")
    view.setAccessibleName(name)
    view.setModel(items)
    _quiet(view, 1)
    view.setItemDelegateForColumn(1, SourceDelegate(view))
    view.setItemDelegateForColumn(2, FixedPitchDelegate(view))
    view.setShowGrid(False)
    view.setWordWrap(False)
    view.verticalHeader().setVisible(False)
    view.horizontalHeader().setStretchLastSection(False)
    view.horizontalHeader().setSectionResizeMode(1, view.horizontalHeader().ResizeMode.Stretch)
    return view


def package_board(items: PackageItems, name: str,
                  parts: Callable[[Package], tuple[str, str, str, str, str, str]]
                  ) -> PackageBoard:
    """Rail's board: one card per package, two to a row (§4.3 Rail)."""
    view = PackageBoard()
    view.setObjectName("PackageBoard")
    view.setAccessibleName(name)
    view.setModel(items)
    _quiet(view, 3)
    view.setItemDelegate(CardDelegate(parts, view))
    view.setFlow(QListView.Flow.LeftToRight)
    view.setWrapping(True)
    view.setResizeMode(QListView.ResizeMode.Adjust)
    view.setMovement(QListView.Movement.Static)
    view.setUniformItemSizes(True)
    # Qt lays a wrapping list out as if a scroll bar might appear, which pushed the
    # second card to a row of its own; with the bar always shown, two fit. It also
    # shows that the board scrolls, which the sketch writes as "+ 14 more".
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    return view


def package_list(items: PackageItems, name: str,
                 parts: Callable[[Package], tuple[str, str, str]]) -> QListView:
    """One of Spotlight's two lists: one line per package."""
    view = QListView()
    view.setObjectName("PackageLists")
    view.setAccessibleName(name)
    view.setModel(items)
    _quiet(view, 1)
    view.setItemDelegate(ListLineDelegate(parts, view))
    view.setUniformItemSizes(True)
    return view


def fit_board(view: PackageBoard) -> None:
    """Room for two of the narrowest cards side by side, and each card's size, from
    the font. Called again when the text size changes."""
    card = view.fontMetrics().averageCharWidth() * view.MIN_CARD_CHARS
    bar = view.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, None, view)
    view.setMinimumWidth(2 * card + bar + 2 * view.frameWidth())
    view.fit()


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


def _invalidate(layout: QLayout) -> None:
    """A layout's cached sizes, and those of every layout nested in it. Found as
    the layout's QObject children: `itemAt(i).layout()` once handed back a
    QWidgetItem mid-suite, a wrapper PySide had cached at that address."""
    layout.invalidate()
    for child in layout.findChildren(QLayout):
        child.invalidate()


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
    outlined in one ink. The fills also take the theme's colours (§4.3.2) — done
    solid, now hatched, to go left empty. Blocks run in the reading direction, which the strip reads
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
        # Set from the stylesheet; these defaults only show before the sheet arrives.
        p = theme.current_palette()
        self._ink = QColor(p["tname"])
        self._fill = {"done": QColor(p["switchon"]), "now": QColor(p["ghosthov"])}

    def get_ink(self) -> QColor:
        return self._ink

    def set_ink(self, colour) -> None:
        self._ink = QColor(colour)
        self.update()

    ink = Property(QColor, get_ink, set_ink)

    def get_done_fill(self) -> QColor:
        return self._fill["done"]

    def set_done_fill(self, colour) -> None:
        self._fill["done"] = QColor(colour)
        self.update()

    def get_now_fill(self) -> QColor:
        return self._fill["now"]

    def set_now_fill(self, colour) -> None:
        self._fill["now"] = QColor(colour)
        self.update()

    doneFill = Property(QColor, get_done_fill, set_done_fill)
    nowFill = Property(QColor, get_now_fill, set_now_fill)

    def brush(self, group: str) -> QBrush:
        """A group's fill: its pattern, in its colour. To go has none."""
        return QBrush(self._fill.get(group, self._ink), self.FILLS[group])

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
            p.setBrush(self.brush(group))
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
        p.setPen(QPen(self._strip.get_ink(), 1))
        p.setBrush(self._strip.brush(self._group))
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
    what = QLabel(QCoreApplication.translate(
        "package_views", "Each block is one package, sized by its download"))
    what.setObjectName("Tagline")
    lay.addWidget(what)
    return box
