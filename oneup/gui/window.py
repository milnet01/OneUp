"""The window itself.

Construction and layout, attaching to a run another window started, quitting,
the dialog openers, the run history, and the two accessibility settings.

Every subsystem this window drives lives in its own module and is handed the
window when it needs one; nothing under `oneup/gui/` imports this file
(`docs/specs/ONEUP-0034-gui-modules.md` §4.3 rule 2). This module will not fit
`docs/standards/coding.md` §4.1's 600-line ceiling and the spec does not
pretend it will — a window's construction and its layout are one
responsibility that is simply large. ONEUP-0064 is where that is attempted.
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from datetime import datetime
from functools import partial
from pathlib import Path

import shiboken6
from PySide6.QtCore import (
    QT_TRANSLATE_NOOP,
    Property,
    QByteArray,
    QCoreApplication,
    QDate,
    QDateTime,
    QEvent,
    QLocale,
    QProcess,
    QSettings,
    QSize,
    Qt,
    QTime,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAccessible,
    QAccessibleEvent,
    QColor,
    QDesktopServices,
    QPainter,
)

try:  # Qt 6.8+: "speak this now" for a screen reader.
    from PySide6.QtGui import QAccessibleAnnouncementEvent
except ImportError:  # older PySide6 (e.g. Leap) — _announce falls back to an Alert.
    QAccessibleAnnouncementEvent = None
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION_LABEL, REPO_SLUG
from . import (
    app_update,
    auth,
    autostart,
    banners,
    diagnostics,
    i18n,
    markers,
    paths,
    placement,
    repos,
    rollback,
    run,
    step_progress,
    steps,
    tray,
)
from . import theme as theme_mod
from .details_dialog import DetailsStore
from .elided_label import ElidedLabel
from .layout_rail import RailLayout
from .layout_rows import RowsLayout
from .layout_spotlight import SpotlightLayout
from .packages import PackageModel
from .settings_dialog import SettingsDialog
from .size_link import SizeLink
from .task_row import TaskRow
from .theme import TEXT_SCALES, _app_icon, apply_app_theme

# The last-run line turns amber once the last run is this old, nudging the user
# that an update is overdue (ONEUP-0030).
STALE_AFTER_DAYS = 14

# The window's layouts, in the order the Settings button cycles through them
# (ONEUP-0239 §4.7). The id is what is stored; the name is only ever shown.
LAYOUTS = (
    ("rows", QT_TRANSLATE_NOOP("window", "Rows"), RowsLayout),
    ("rail", QT_TRANSLATE_NOOP("window", "Rail"), RailLayout),
    ("spotlight", QT_TRANSLATE_NOOP("window", "Spotlight"), SpotlightLayout),
)
DEFAULT_LAYOUT = "rows"
# The window's narrowest, whatever the layout: room for the header's three buttons.
MIN_WIDTH = 560


class _ProgressBar(QProgressBar):
    """A progress bar that hands its caption to a label instead of painting it.

    `setFormat` stays the only way the caption is set — every call site and the
    suite still read `bar.format()` — but the text is mirrored into `caption`
    and the bar draws none of it.

    Centred on the fill, the caption was read against `accent`: 1.63:1 at the
    left gradient stop and 1.12:1 at the right in the dark themes, against SC
    1.4.3's 4.5:1, on live text carrying the download detail. No accent a theme
    would want is readable under body text, so the words move rather than the
    colour (ONEUP-0163).
    """

    def __init__(self, caption: QLabel) -> None:
        super().__init__()
        self._caption = caption
        self.setTextVisible(False)
        self.setObjectName("RunProgress")
        # Set from the stylesheet; this default only shows before the sheet arrives.
        self._mark = QColor(theme_mod.current_palette()["card"])

    def setFormat(self, fmt: str) -> None:
        super().setFormat(fmt)
        self._caption.setText(fmt)

    def get_mark(self) -> QColor:
        return self._mark

    def set_mark(self, colour) -> None:
        self._mark = QColor(colour)
        self.update()

    mark = Property(QColor, get_mark, set_mark)

    def paintEvent(self, event) -> None:
        """While the bar shows a step's two halves, a notch in the surface's colour
        marks where installing starts, so the bar itself says which half it is in
        (ONEUP-0239 §4.1.1). The middle is the middle in either direction."""
        super().paintEvent(event)
        if self.maximum() != step_progress.FULL:
            return
        notch = max(2, self.height() // 6)
        painter = QPainter(self)
        painter.fillRect((self.width() - notch) // 2, 0, notch, self.height(), self._mark)
        painter.end()


def _retain_space(widget: QWidget) -> None:
    """Hidden, `widget` keeps its place, so showing it moves nothing (ONEUP-0239 §4.2)."""
    policy = widget.sizePolicy()
    policy.setRetainSizeWhenHidden(True)
    widget.setSizePolicy(policy)


def _log_toggle_text(log_shown: bool) -> str:
    return (QCoreApplication.translate("window", "Show packages") if log_shown
            else QCoreApplication.translate("window", "Show technical log"))


def _last_run_outcome(status: str) -> str:
    """The saved outcome of the last run, in words. The history file stores a
    fixed token, so the wording stays the window's; an unknown one shows as stored."""
    return {
        "OK": QCoreApplication.translate("window", "OK"),
        "errors": QCoreApplication.translate("window", "errors"),
        "stopped": QCoreApplication.translate("window", "stopped"),
    }.get(status, status)


class Updater(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(QCoreApplication.translate(
            "window",
            "{APP_NAME} {APP_VERSION}").format(APP_NAME=APP_NAME, APP_VERSION=APP_VERSION_LABEL))
        # Three header controls (Settings · Recenter · About); the background
        # toggles and Repositories live inside the Settings popup. The current
        # layout may need more, and _fit_minimum raises the floor to it.
        self.setMinimumWidth(MIN_WIDTH)
        self.settings = QSettings("OneUp", "OneUp")
        self.proc: QProcess | None = None
        self._buf = ""
        self._dec = markers.utf8_decoder()
        self._total = 0
        self._check_mode = False
        self._unchecked = []         # reasons a --check couldn't read a source (ONEUP-0056)
        self._reboot = False
        self._reboot_reason = ""     # optional "why a reboot matters" phrase from the engine
        self._installed_count = ""   # system packages changed, as reported by the engine
        self._installed_basis = ""   # a check's TOTAL basis: "at-least" or "" (ONEUP-0329)
        self._system_pending = 0     # system updates a check found (ONEUP-0300)
        self._sys_changed = False
        self._other_changed = {}     # Flatpak/firmware/leftover step → its count, if it acted
        self._step_caption = ""      # current step's bar caption, so @@PROGRESS@@ can extend it
        self._progress_phase = ""    # download/install; a change is what gets announced
        self._stop_asked = False     # Stop was pressed this run; never offer it again
        # Liveness state (ONEUP-0048). _activity_at is the last time ANY output arrived —
        # including a partial line, which is all zypper's dots ever are — so "quiet for
        # 4m" means genuinely nothing, not merely nothing complete enough to draw.
        self._activity_at = 0.0
        self._activity_what = ""     # what we're waiting on, e.g. "Fetching the games source"
        self._activity_since = 0.0   # when that wait started
        self._activity_stalled = False   # announced on the transition, not every tick
        self._dl_at = 0.0            # first byte reading of this download, for the rate
        self._dl_from = 0            # bytes already fetched at that reading
        self._dl_bytes = 0           # bytes fetched so far, as reported by zypper
        self._dl_total = 0           # transaction's total download size (0 = unknown)
        self._dl_base = 0            # package-cache weight before the run started
        self._dl_grown = 0           # its growth at the last weighing (ONEUP-0155)
        self._dl_got = 0             # the byte figure the line and the bar both show
        self._dl_rate = 0.0          # bytes a second over the whole download, 0 = none yet
        self._progress_count = (0, 0)  # the last PROGRESS line's done and total
        # The one status line (ONEUP-0239 §4.1.3, run._show_status): the text it was
        # last given, what it last showed, and the clock and stall sentence it ends with.
        self._status_base = self._status_shown = ""
        self._status_clock = self._status_stall = ""
        self._done_status = ""       # the run's own @@DONE@@ verdict; the only result
                                     # available for a run we attached to (no exit code)
        self._attached_pid = 0       # engine we're following that another window started
        self._attached_log = None
        self._attached_pos = 0
        self._attach_timer = None
        self._failed_steps: list[str] = []
        self._services = ""
        self._snapshot = ""
        self._snapshots: list[tuple[str, str, str]] = []  # (id, date, desc) for the rollback picker
        self._hints: list[str] = []
        self._hint_commands: list[str] = []   # the command each hint names, or '' (ONEUP-0235)
        self._hint_command = ""   # the command the shown hint names, for Copy
        self._remedy_keys = False  # engine flagged a fixable signing-key error (@@REMEDY@@)
        self._skipped_repos: list[str] = []  # aliases set aside this run (@@REPO_SKIPPED@@)
        self._remedy_skips: list[str] = []  # aliases to offer "Skip … & update the rest" for
        self._remedy_unknown: list[str] = []  # REMEDY codes this window has no action for
        self._log_path: Path | None = None
        self._latest_tag = ""
        self._warn_repo_dup = False   # is the current warning a duplicate-repo one?
        self._warn_snapshots = False  # pre-flight: many Btrfs snapshots may be using disk
        self._snapshot_count = 0      # how many, for the banner text
        self._run_active = False      # is a full update run in flight? (guards the thin action)
        self._liveness_active = False # is ANY engine in flight? (drives the ONEUP-0048 line)
        self._settings_dialog: SettingsDialog | None = None
        self._pending_autoupdate = False   # one-shot latch: an enable awaiting a fresh auth settle
        self._tray = None
        self._tray_timer = None
        self._tray_total = 0
        self._tray_at_least = False  # the last total was the rootless floor (ONEUP-0329)
        self._tray_checked_at = None
        self._tray_hint_shown = False
        self._local_server = None
        self._traycheck_proc = None
        self._traycheck_buf = ""
        self._traycheck_dec = markers.utf8_decoder()
        self._traycheck_unknown = False
        self._size_buf = ""
        self._size_dec = markers.utf8_decoder()
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self._last_announcement = ""   # what _announce last spoke (see _announce)
        # Run state the layouts read and never own (ONEUP-0239 §4.1), so a layout
        # change mid-run keeps it. All of it is cleared by run._reset_for_run.
        self.current_step = ""         # the step running now, or ""
        self.latest_package = None     # (key, name, edition) of the last PKG line
        self.engine_finished = False   # set by on_finished; the empty pages read it
        self.step_progress = {}        # key -> 0..1000, or None while busy (§4.1.1)
        self.waiting = set()           # selected steps of this run not yet started
        self.host = None               # the current layout (layout_host.LayoutHost)
        # Set here, not after construction: eventFilter reads it, and the controls it
        # filters receive events while the layout is being built.
        self._placement_pending = False

        # Gradient ring: a 2px accent border (outer #Frame) around the card.
        outer_frame = QFrame()
        outer_frame.setObjectName("Frame")
        self.setCentralWidget(outer_frame)
        frame_lay = QVBoxLayout(outer_frame)
        frame_lay.setContentsMargins(2, 2, 2, 2)
        card = QFrame()
        card.setObjectName("Card")
        frame_lay.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # Header: title + tagline on the left; weekly-check + recenter on the right.
        header = QLabel(APP_NAME)
        header.setObjectName("Header")
        tagline = QLabel(QCoreApplication.translate(
            "window",
            "Keep openSUSE, Flatpak and firmware up to date  ·  "
            "v{APP_VERSION}").format(APP_VERSION=APP_VERSION_LABEL))
        tagline.setObjectName("Tagline")
        titleblock = QVBoxLayout()
        titleblock.setSpacing(2)
        titleblock.addWidget(header)
        titleblock.addWidget(tagline)

        autostart._refresh_stale_launchers()
        self.auto_btn = QPushButton()
        self.auto_btn.setObjectName("GhostBtn")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setCursor(Qt.PointingHandCursor)
        self.auto_btn.setToolTip(
            QCoreApplication.translate(
                "window",
                "Check weekly in the background and notify you when updates are "
                "ready"))
        self.auto_btn.setChecked(autostart._autocheck_enabled())
        autostart._refresh_autocheck_label(self)
        self.auto_btn.toggled.connect(partial(autostart.on_autocheck_toggled, self))

        # Opt-in "remember my authorization": stop prompting for the password on
        # every update. Off by default; the real state is probed from the engine
        # after the window is built (_query_auth_status). On a service install the
        # Settings dialog shows one line in its place, and the button stays as the
        # probe's state for the automatic-update coupling (ONEUP-0249 §4.10).
        self._service_route = auth.service_route()
        self.auth_btn = QPushButton()
        self.auth_btn.setObjectName("GhostBtn")
        self.auth_btn.setCheckable(True)
        self.auth_btn.setCursor(Qt.PointingHandCursor)
        self.auth_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Stop asking for your password on every update (opt-in; can be "
            "switched off to revoke instantly)"))
        auth._refresh_auth_label(self)
        self.auth_btn.toggled.connect(partial(auth.on_auth_toggled, self))

        # Automatic weekly updates (ONEUP-0022). Off by default; enabling it needs
        # the passwordless rule (coupling enforced in on_autoupdate_toggled). Real
        # state is read from the systemd-user timer.
        self.autoupdate_btn = QPushButton()
        self.autoupdate_btn.setObjectName("GhostBtn")
        self.autoupdate_btn.setCheckable(True)
        self.autoupdate_btn.setCursor(Qt.PointingHandCursor)
        self.autoupdate_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Install all updates automatically every week (needs this computer to "
            "allow updates without a password)") if self._service_route
            else QCoreApplication.translate(
            "window",
            "Install all updates automatically every week (needs "
            "Passwordless)"))
        self.autoupdate_btn.setChecked(autostart._autoupdate_enabled())
        autostart._refresh_autoupdate_label(self)
        self.autoupdate_btn.toggled.connect(partial(autostart.on_autoupdate_toggled, self))

        # System-tray icon + start-at-boot (ONEUP-0018). Both off by default; disabled
        # when the desktop has no tray. tray_enabled is a QSettings preference; start-at-boot
        # reads the real autostart-file existence.
        self.tray_btn = QPushButton()
        self.tray_btn.setObjectName("GhostBtn")
        self.tray_btn.setCheckable(True)
        self.tray_btn.setCursor(Qt.PointingHandCursor)
        self.tray_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Show a small tray icon that turns amber when updates are waiting"))
        self.tray_btn.setChecked(self.settings.value("tray_enabled", False, type=bool))
        tray._refresh_tray_label(self)
        self.tray_btn.toggled.connect(partial(tray.on_tray_toggled, self))

        self.startboot_btn = QPushButton()
        self.startboot_btn.setObjectName("GhostBtn")
        self.startboot_btn.setCheckable(True)
        self.startboot_btn.setCursor(Qt.PointingHandCursor)
        self.startboot_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Start OneUp automatically at login (needs the tray icon)"))
        self.startboot_btn.setChecked(autostart._startboot_enabled())
        autostart._refresh_startboot_label(self)
        self.startboot_btn.toggled.connect(partial(autostart.on_startboot_toggled, self))

        if not self._tray_available:
            self.tray_btn.setEnabled(False)
            self.startboot_btn.setEnabled(False)

        # Laid out inside the Settings dialog (like the toggle buttons above), but
        # owned here so it persists across dialog opens.
        self.diag_btn = QPushButton(QCoreApplication.translate("window", "Copy diagnostics"))
        self.diag_btn.setObjectName("GhostBtn")
        self.diag_btn.setCursor(Qt.PointingHandCursor)
        self.diag_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Copy version info and your latest update log to the clipboard, "
            "ready to paste into a bug report"))
        self.diag_btn.clicked.connect(partial(diagnostics.copy_diagnostics, self))

        # Accessibility controls (ONEUP-0028), laid out in the Settings popup but
        # owned here like the toggles above. Text size cycles through TEXT_SCALES
        # rather than using a combo box, matching the existing button idiom.
        self.textsize_btn = QPushButton()
        self.textsize_btn.setObjectName("GhostBtn")
        self.textsize_btn.setCursor(Qt.PointingHandCursor)
        self.textsize_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Make all text larger (on top of your desktop's font size)"))
        self._refresh_textsize_label()
        self.textsize_btn.clicked.connect(self.on_textsize_clicked)

        # How long OneUp keeps its own logs (ONEUP-0082). Cycles like Text size: five
        # choices fit the idiom, and the button names the current one.
        self.logkeep_btn = QPushButton()
        self.logkeep_btn.setObjectName("GhostBtn")
        self.logkeep_btn.setCursor(Qt.PointingHandCursor)
        self.logkeep_btn.setToolTip(QCoreApplication.translate(
            "window",
            "How long OneUp keeps its update logs before deleting them"))
        self._refresh_logkeep_label()
        self.logkeep_btn.clicked.connect(self.on_logkeep_clicked)

        # Which of the three layouts the window uses (ONEUP-0239 §4.7). Cycles like
        # Text size; laid out in Settings, owned here.
        self.layout_btn = QPushButton()
        self.layout_btn.setObjectName("GhostBtn")
        self.layout_btn.setCursor(Qt.PointingHandCursor)
        self.layout_btn.setToolTip(QCoreApplication.translate(
            "window",
            "How the main window is arranged"))
        self._refresh_layout_label()
        self.layout_btn.clicked.connect(self.on_layout_clicked)

        self.contrast_btn = QPushButton()
        self.contrast_btn.setObjectName("GhostBtn")
        self.contrast_btn.setCheckable(True)
        self.contrast_btn.setCursor(Qt.PointingHandCursor)
        self.contrast_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Plain black-and-white colours with strong outlines"))
        self.contrast_btn.setChecked(self.settings.value("high_contrast", False, type=bool))
        self._refresh_contrast_label()
        self.contrast_btn.toggled.connect(self.on_contrast_toggled)

        # Whether OneUp asks GitHub for a newer version as it starts — at login too,
        # when it starts in the tray. On by default; the About dialog's button checks
        # either way, because pressing it is the asking (ONEUP-0191).
        self.appcheck_btn = QPushButton()
        self.appcheck_btn.setObjectName("GhostBtn")
        self.appcheck_btn.setCheckable(True)
        self.appcheck_btn.setCursor(Qt.PointingHandCursor)
        self.appcheck_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Look for a newer OneUp each time it starts"))
        self.appcheck_btn.setChecked(self.settings.value("app_update_check", True, type=bool))
        self._refresh_appcheck_label()
        self.appcheck_btn.toggled.connect(self.on_appcheck_toggled)

        # The theme picker (ONEUP-0027 §4.6). A combo box rather than the
        # cycling-button idiom the two controls above use: nine entries is too
        # many to cycle through, and a combo shows what else is on offer. Built
        # here and re-parented into SettingsDialog, which hosts rather than owns.
        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("ThemeCombo")
        self.theme_combo.setCursor(Qt.PointingHandCursor)
        self.theme_combo.setToolTip(QCoreApplication.translate(
            "window",
            "Colour scheme for the whole app"))
        self.theme_combo.setAccessibleName(QCoreApplication.translate("window", "Colour theme"))
        # The popup is a separate focusable child. It gets a name of ours so
        # it can be styled and so it is not an anonymous focusable widget,
        # which is the shape that named #RepoScroll and #RollbackList.
        self.theme_combo.view().setObjectName("ThemeList")
        self.theme_combo.view().setAccessibleName(QCoreApplication.translate(
            "window",
            "Colour theme choices"))
        self.theme_combo.addItem(QCoreApplication.translate(
            "window", "Follow system"), theme_mod.SYSTEM)
        for _th in theme_mod.THEMES:
            self.theme_combo.addItem(_th.label, _th.id)
        self._refresh_theme_combo()
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)

        # Where a theme that could not be applied is reported. §7 forbids the one
        # outcome of a control that silently does nothing, and the console line
        # apply_app_theme prints is not a user-visible report.
        self.theme_note = QLabel()
        self.theme_note.setObjectName("ThemeNote")
        self.theme_note.setTextFormat(Qt.TextFormat.PlainText)  # shown as typed (ONEUP-0183)
        self.theme_note.setWordWrap(True)
        self.theme_note.setVisible(False)

        self.settings_btn = QPushButton(QCoreApplication.translate("window", "⚙ Settings"))
        self.settings_btn.setObjectName("GhostBtn")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Background behaviours: weekly check, passwordless, automatic "
            "updates"))
        self.settings_btn.clicked.connect(self.open_settings)

        self.recenter_btn = QPushButton(QCoreApplication.translate("window", "Recenter"))
        self.recenter_btn.setObjectName("GhostBtn")
        self.recenter_btn.setCursor(Qt.PointingHandCursor)
        self.recenter_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Move the window back to the centre of the screen"))
        self.recenter_btn.clicked.connect(self.recenter)

        self.repos_btn = QPushButton(QCoreApplication.translate("window", "Repositories"))
        self.repos_btn.setObjectName("GhostBtn")
        self.repos_btn.setCursor(Qt.PointingHandCursor)
        self.repos_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Turn software repositories on/off and clean up duplicates"))
        self.repos_btn.clicked.connect(self.open_repos)

        self.about_btn = QPushButton(QCoreApplication.translate("window", "About"))
        self.about_btn.setObjectName("GhostBtn")
        self.about_btn.setCursor(Qt.PointingHandCursor)
        self.about_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Version, licence, links and a manual update check"))
        self.about_btn.clicked.connect(self.show_about)

        # Fewer than four buttons. Four of identical weight beside the app title
        # make none of them findable — the uniform weight is the complaint, not
        # the count — so Repositories moves into Settings (ONEUP-0064). Recenter
        # went with it and is back, by the user's request, until the window
        # opens centred after a reboot (ONEUP-0245, ONEUP-0246).
        header_row = QHBoxLayout()
        header_row.addLayout(titleblock, 1)
        header_row.addWidget(self.settings_btn, 0, Qt.AlignTop)
        header_row.addWidget(self.recenter_btn, 0, Qt.AlignTop)
        header_row.addWidget(self.about_btn, 0, Qt.AlignTop)
        self.header_row = header_row
        # ONEUP-0294: the sheet's `min-width` replaces each button's text-measured
        # minimum, so a narrow window squeezed these to "etti" and ".bou". Each is
        # pinned to its label instead, re-measured on a style or font change (the
        # filter is installed beside Check and Stop's), and the window's minimum grows
        # to hold them. The pin follows addLayout: that reparents the buttons, which
        # re-applies the sheet and would put its min-width back over an earlier pin.
        self._header_btns = (self.settings_btn, self.recenter_btn, self.about_btn)
        root.addLayout(header_row)
        self._pin_header_widths()
        root.addSpacing(2)
        self._card_root = root      # the current layout sits below the header

        # The packages this check or run touches (ONEUP-0259), which every view of
        # them reads.
        self.packages = PackageModel()
        # What each system package is, fetched without root (ONEUP-0260 §4.2).
        self.details = DetailsStore(self.packages, self)
        # Task rows — each a gradient-bordered card. Built here and laid out by the
        # current layout, which never owns them (ONEUP-0239 §4.1).
        self.rows: dict[str, TaskRow] = {}
        for key, title, desc in steps.TASKS:
            self.rows[key] = TaskRow(key, QCoreApplication.translate("steps", title),
                                     QCoreApplication.translate("steps", desc))

        # Action row: Check (secondary) + Run (primary).
        self.check_btn = QPushButton(QCoreApplication.translate("window", "Check for updates"))
        self.check_btn.setObjectName("GhostBtn")
        self.check_btn.setCursor(Qt.PointingHandCursor)
        self.check_btn.setToolTip(QCoreApplication.translate(
            "window",
            "See what would update — installs nothing"))
        self.check_btn.clicked.connect(partial(run.start_check, self))

        self.run_btn = QPushButton(QCoreApplication.translate("window", "Run selected updates"))
        self.run_btn.setObjectName("RunBtn")
        self.run_btn.setMinimumHeight(44)
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(partial(run.start_run, self))

        # Stop (only while a run is going). Deliberately not a "cancel" — it takes effect
        # at the next safe point, because interrupting an install can leave programs
        # broken. The label and tooltip say so rather than implying an instant abort.
        # Its own object name, not GhostBtn: it is filled with the danger colour
        # (ONEUP-0239 §4.1.3), and the focus derivation matches a styled control BY
        # NAME — a restyled control still called GhostBtn would be invisible to it
        # (ONEUP-0064).
        self.stop_btn = QPushButton(QCoreApplication.translate("window", "Stop"))
        self.stop_btn.setObjectName("StopBtn")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setAccessibleName(QCoreApplication.translate("window", "Stop the update"))
        self.stop_btn.setToolTip(run.stop_tooltip(installing=False))
        self.stop_btn.clicked.connect(partial(run.request_stop, self))
        self.stop_btn.setVisible(False)

        # Primary first. The row has three items for the window's whole life — a
        # hidden widget still holds its own layout item — and a run swaps Run and
        # Check out for Stop alone, at the trailing end (ONEUP-0239 §4.1.3). What
        # reads as one slot is the visibility rule plus the bar's fixed width.
        # The row sits on a widget of its own so each layout can place it whole
        # (ONEUP-0239 §4.1).
        self.action_bar = QWidget()
        actions = QHBoxLayout(self.action_bar)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)
        actions.addWidget(self.run_btn, 1)
        actions.addWidget(self.check_btn, 0)
        actions.addWidget(self.stop_btn, 0, Qt.AlignmentFlag.AlignTrailing)
        self.action_row = actions
        # Its width is its minimum, never a cap: a longer translation widens it.
        self.action_bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        # ONEUP-0240: Check and Stop share one width — the widest any of their labels
        # needs — and the bar holding all three is held at the widest it ever has to
        # be, so the swap moves nothing beside it. Re-measured when a style or font
        # change reaches either button.
        self._pin_check_stop_width()
        self.check_btn.installEventFilter(self)
        self.stop_btn.installEventFilter(self)
        for btn in self._header_btns:
            btn.installEventFilter(self)

        # Retry-failed (hidden until a run has failures). It lives INSIDE the
        # warning banner, appended below once that banner exists, so the remedy
        # sits beside the thing it remedies rather than reading as a fourth
        # member of the action row above while belonging to none of it.
        self.retry_btn = QPushButton(QCoreApplication.translate("window", "Retry failed steps"))
        self.retry_btn.setObjectName("GhostBtn")
        self.retry_btn.setCursor(Qt.PointingHandCursor)
        self.retry_btn.clicked.connect(partial(run.retry_failed, self))
        self.retry_btn.setVisible(False)

        # Progress + current step.
        self.status = ElidedLabel(QCoreApplication.translate("window", "Ready."))
        self.status.setObjectName("Status")
        self.status.setTextFormat(Qt.TextFormat.PlainText)  # shown as typed (ONEUP-0183)
        # NOT setAccessibleName: an explicit name on a QLabel is permanent, and this
        # label is `_announce`'s default `source` — so a name here makes the reader
        # say "Current status" for every run summary instead of the summary
        # (ONEUP-0028 § the fallback deliberately does not name the borrowed label).
        # A description carries the role without displacing the text.
        self.status.setAccessibleDescription(QCoreApplication.translate(
            "window",
            "Current status"))
        # The caption sits under the bar rather than on its fill (ONEUP-0163).
        # A description, not a name: this label's text is replaced on every
        # progress line, and an explicit name on a QLabel is permanent.
        self.bar_caption = ElidedLabel("")
        self.bar_caption.setObjectName("ProgressCaption")
        self.bar_caption.setTextFormat(Qt.TextFormat.PlainText)  # shown as typed (ONEUP-0183)
        self.bar_caption.setAccessibleDescription(QCoreApplication.translate(
            "window",
            "Update progress detail"))
        self.bar = _ProgressBar(self.bar_caption)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.bar.setAccessibleName(QCoreApplication.translate("window", "Update progress"))
        # Liveness (ONEUP-0048): how long the current phase has been going, the download
        # rate, and — when the engine has gone quiet — how long for. A slow mirror and a
        # hung one look identical without it: zypper reports a metadata fetch as
        # undelimited dots with no line ending, so there is nothing for the log pane to
        # draw, and a working run reads as frozen.
        self.activity = ElidedLabel("")
        self.activity.setObjectName("Activity")
        self.activity.setTextFormat(Qt.TextFormat.PlainText)  # shown as typed (ONEUP-0183)
        self.activity.setAccessibleName(QCoreApplication.translate("window", "Activity"))
        # The caption and the activity line are in no layout: the status line carries
        # the clock and the stall (ONEUP-0239 §4.1.3). They stay the window's, hidden,
        # so no host deletes them and neither ever shows as a window of its own.
        for label in (self.bar_caption, self.activity):
            label.setParent(self)
            label.hide()
        # Five seconds, not one: the label is a live region, and a screen reader reading a
        # ticking counter aloud would bury everything else. _tick_activity only re-announces
        # when the WORDING changes, so the elapsed figure updates silently.
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(5000)
        self._activity_timer.timeout.connect(partial(run._tick_activity, self))

        # Banners (all hidden until needed).
        # Each banner is named for its ROLE, so a screen reader describes what the
        # frame is rather than announcing an unnamed panel (ONEUP-0028).
        self.reboot_banner, self.reboot_label, self.restart_btn = banners._make_banner(self,
            "RebootBanner", "RestartBtn", QCoreApplication.translate("window", "Restart now"),
            partial(banners.restart_now, self),
            name=QCoreApplication.translate("window", "Restart recommended"))

        self.services_banner, self.services_label, self.services_btn = banners._make_banner(self,
            "InfoBanner", "BannerBtn", QCoreApplication.translate("window", "Restart services"),
            partial(banners.restart_services, self),
            name=QCoreApplication.translate("window", "Services should restart"))

        self.warn_banner, self.warn_label, self.warn_btn = banners._make_banner(self,
            "WarnBanner", "BannerBtn", QCoreApplication.translate("window", "Show details"),
            partial(banners._warn_action, self),
            name=QCoreApplication.translate("window", "Warning"))
        # A copy-the-suggested-command button, shown only when a hint carries a
        # runnable command the app couldn't run for you — the copy-fallback.
        self.warn_copy_btn = QPushButton(QCoreApplication.translate("window", "Copy command"))
        self.warn_copy_btn.setObjectName("LinkBtn")
        self.warn_copy_btn.setCursor(Qt.PointingHandCursor)
        self.warn_copy_btn.setToolTip(QCoreApplication.translate(
            "window",
            "Copy the suggested command to the clipboard"))
        self.warn_copy_btn.clicked.connect(partial(banners._copy_hint_command, self))
        self.warn_copy_btn.setVisible(False)
        self.warn_banner.layout().insertWidget(1, self.warn_copy_btn)
        # A second action button, shown only when two remedies are armed at once (an
        # expired signing key on the culprit source: primary warn_btn offers "Skip
        # <source> & update the rest", this offers the alternative "Import signing
        # key & retry"). Hidden the rest of the time — the single-action path is
        # unchanged when only one remedy is armed.
        self.warn_btn2 = QPushButton("")
        self.warn_btn2.setObjectName("BannerBtn")
        # Its label is set only when shown, so it needs a standing accessible name
        # — otherwise it is a nameless button in the widget tree.
        self.warn_btn2.setAccessibleName(QCoreApplication.translate(
            "window",
            "Alternative fix for this warning"))
        self.warn_btn2.setCursor(Qt.PointingHandCursor)
        self.warn_btn2.clicked.connect(partial(banners._fix_keys_and_retry, self))
        self.warn_btn2.setVisible(False)
        self.warn_banner.layout().addWidget(self.warn_btn2)
        # Retry, last of the banner's four buttons. Layout order does NOT set the
        # focus chain — parenting order does, which is how this banner's chain
        # came to run backwards — so the chain below states it explicitly.
        self.warn_banner.layout().addWidget(self.retry_btn)

        self.appupdate_banner, self.appupdate_label, self.appupdate_btn = banners._make_banner(self,
            "InfoBanner", "BannerBtn", QCoreApplication.translate("window", "View release"),
            partial(app_update._open_release, self),
            name=QCoreApplication.translate("window", "OneUp update available"))
        # The one fixed place the four banners show, in this order (ONEUP-0239 §4.4).
        self.message_strip = banners.MessageStrip(
            [self.reboot_banner, self.services_banner, self.warn_banner,
             self.appupdate_banner])

        # Rollback link (shown after the system actually changed).
        self.rollback_btn = QPushButton(QCoreApplication.translate(
            "window",
            "Roll back this update…"))
        self.rollback_btn.setObjectName("LinkBtn")
        self.rollback_btn.setCursor(Qt.PointingHandCursor)
        self.rollback_btn.clicked.connect(partial(rollback.rollback, self))
        self.rollback_btn.setVisible(False)
        _retain_space(self.rollback_btn)

        # Log controls: the swap between the packages and the log, and open-file.
        # Small ghost buttons rather than links (ONEUP-0299).
        self.log_toggle = QPushButton(_log_toggle_text(False))
        self.log_toggle.setObjectName("GhostBtn")
        self.log_toggle.setProperty("small", True)
        self.log_toggle.setCursor(Qt.PointingHandCursor)
        self.log_toggle.clicked.connect(self.toggle_log)
        self.openlog_btn = QPushButton(QCoreApplication.translate("window", "Open log file"))
        self.openlog_btn.setObjectName("GhostBtn")
        self.openlog_btn.setProperty("small", True)
        self.openlog_btn.setCursor(Qt.PointingHandCursor)
        self.openlog_btn.clicked.connect(self.open_log)
        # Shown only with the log, in a slot that keeps its size (ONEUP-0239 §4.1.3).
        self.openlog_btn.setVisible(False)
        _retain_space(self.openlog_btn)
        # Its label changes, so it is pinned to the wider one (ONEUP-0239 §4.2).
        self._pin_log_toggle_width()
        self.log_toggle.installEventFilter(self)

        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setPlaceholderText(QCoreApplication.translate(
            "window",
            "Update details will appear here when you run an update."))
        # Named, focusable and readable on demand. Deliberately NOT announced line
        # by line — a run emits hundreds of zypper lines (see the spec's Out of
        # scope): a screen reader would be unusable.
        self.log.setAccessibleName(QCoreApplication.translate("window", "Update log"))
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # The package area: the layout's own package page, or the log, in one place
        # of one size (ONEUP-0239 §4.5). It always opens on the packages; the old
        # `log_shown` setting is no longer read (§3).
        self.package_area = QStackedWidget()
        self.package_area.addWidget(self.log)

        # The download-size link and its result, moved out of the system row
        # (ONEUP-0239 §4.6). Each layout places it. On the service route the window
        # fetches the size itself after a check, so the link starts hidden (ONEUP-0300).
        self.size_link = SizeLink(partial(run.request_size, self, "system"),
                                  automatic=self._service_route)

        # Last-run line.
        self.last_run = ElidedLabel()
        self.last_run.setObjectName("LastRun")
        self.last_run.setAccessibleName(QCoreApplication.translate("window", "Last update run"))
        self.refresh_last_run()

        # Everything below the header is the current layout's to arrange. An
        # unknown stored id shows Rows and is left as stored (§4.7).
        self.apply_layout(self._layout_id())

        # Restore the last size + position, if we saved one before.
        geo = self.settings.value("geometry")
        if isinstance(geo, QByteArray):         # a corrupt value must not stop startup
            self.restoreGeometry(geo)
        # On Wayland restoreGeometry() brings back the size only; the position is replayed
        # through KWin on each show (ONEUP-0246, showEvent).

        # Non-blocking: is there a newer OneUp release? Only if the user lets it ask.
        if self.appcheck_btn.isChecked():
            app_update._check_app_update(self)

        # Non-blocking: reflect whether passwordless authorization is active.
        auth._query_auth_status(self)
        # Once the window is up: on a service install, offer to remove an old
        # Passwordless rule (ONEUP-0249 §4.10). It returns at once everywhere else.
        QTimer.singleShot(0, partial(auth.offer_old_dropin_removal, self))

        # A run started by an earlier window may still be going — they outlive the
        # window on purpose (ONEUP-0042). Pick it up and follow it, rather than showing
        # an idle app whose Run button could only fail on the package lock.
        self._attach_to_running_engine()


    def _announce(self, text: str, source: QWidget | None = None):
        """Speak `text` to a screen reader, if one is listening.

        `source` is the widget whose ON-SCREEN TEXT IS this message: the pre-Qt-6.8
        fallback fires an Alert on it and lets the reader read that text, so it must
        never be handed a widget whose text says something else. The fallback
        deliberately does not setAccessibleName() on the borrowed label — an
        explicit name on a QLabel is permanent, which would make every later
        setText() invisible to assistive tech.

        _last_announcement is recorded unconditionally so the headless smoke test
        can assert what WOULD be spoken (QAccessible.isActive() is False offscreen).
        """
        self._last_announcement = text
        if not text or not QAccessible.isActive():
            return
        if QAccessibleAnnouncementEvent is not None:
            QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(self, text))
        else:
            QAccessible.updateAccessibility(
                QAccessibleEvent(source or self.status, QAccessible.Event.Alert))

    def _read_run_state(self):
        """The engine's record of a run in flight: (pid, log path, steps). None when
        there is no run, or when the record is stale — a pid that no longer exists means
        the engine was killed before it could clean up, so the record is deleted."""
        try:
            lines = paths.RUN_STATE.read_text().splitlines()
        except OSError:
            return None
        if len(lines) < 3 or not lines[0].isdecimal():
            return None
        pid = int(lines[0])
        try:
            os.kill(pid, 0)          # signal 0 = "does this pid exist?", changes nothing
        except ProcessLookupError:
            paths.RUN_STATE.unlink(missing_ok=True)
            return None
        except PermissionError:
            pass                     # alive, just not ours to signal
        return pid, lines[1], lines[2]

    def _attach_to_running_engine(self):
        """Follow a run started by an earlier OneUp window. Runs deliberately outlive the
        window (ONEUP-0042), so without this the user is shown an idle app and a Run
        button whose only possible outcome is the package-lock message (ONEUP-0045).
        The engine's log carries the same @@MARKER@@ lines the live stream does, so
        replaying it through handle_line rebuilds the full display — progress, badges
        and banners included."""
        state = self._read_run_state()
        if state is None:
            return False
        pid, log_path, steps = state
        self._attached_pid = pid
        self._attached_log = Path(log_path)
        self._attached_pos = 0
        self._run_active = True
        self._liveness_active = True
        self._check_mode = False
        self._done_status = ""
        run._reset_activity(self)
        self._activity_timer.start()
        self._total = len([s for s in steps.split(",") if s])
        self.bar.setRange(0, max(self._total, 1))
        self.set_controls_enabled(False)
        self.status.setText(QCoreApplication.translate(
            "window",
            "An update started earlier is still running — following it…"))
        self._announce(self.status.text())
        self._attach_timer = QTimer(self)
        self._attach_timer.setInterval(1000)
        self._attach_timer.timeout.connect(self._poll_attached_run)
        self._attach_timer.start()
        self._poll_attached_run()
        return True

    def _poll_attached_run(self):
        """Read whatever the attached run has appended, then notice when it finishes.

        The pid is asked about BEFORE the log is read (ONEUP-0183). Read-then-ask let a
        run write its @@DONE@@ and exit in the gap: the read saw no verdict, the pid was
        gone, and a successful run was recorded as failed. Asked first, a run found
        gone has already written everything it will write, so the read below has it."""
        try:
            os.kill(self._attached_pid, 0)
            alive = True
        except PermissionError:
            alive = True                            # alive, just not ours to signal
        except ProcessLookupError:
            alive = False
        try:
            with self._attached_log.open("rb") as fh:
                fh.seek(self._attached_pos)
                data = fh.read()
        except OSError:
            data = b""
        if alive:
            # Only whole lines: the engine may be part-way through writing one, and a
            # marker read in two halves would be parsed short and then logged as junk
            # (ONEUP-0346).
            data = data[:data.rfind(b"\n") + 1]
        self._attached_pos += len(data)
        new = data.decode(errors="replace")
        if new:
            self._activity_at = time.monotonic()   # the log grew: the run is alive
        for line in new.splitlines():
            run.handle_line(self, line)
        if alive:
            return                                  # still going
        self._attach_timer.stop()
        paths.RUN_STATE.unlink(missing_ok=True)
        # No exit code to read for someone else's process, so the run's own @@DONE@@ is
        # the verdict. A run killed before printing one is reported as errors rather
        # than success — never claim an outcome the run didn't actually report.
        self._attached_pid = 0
        run.on_finished(self, 0 if self._done_status == "ok" else 1, None)

    def _ask_quit_during_run(self) -> bool:
        """Modal 'an update is still running' prompt. True = close anyway. Split out
        from _confirm_quit so the decision logic stays testable without a dialog."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(QCoreApplication.translate("window", "An update is still running"))
        box.setText(QCoreApplication.translate("window", "An update is still running."))
        box.setInformativeText(
            QCoreApplication.translate(
                "window",
                "Closing OneUp won't stop it. Interrupting an update half-way can "
                "leave programs broken, so it carries on in the background and "
                "finishes on its own — but you won't be able to watch it, and the "
                "next update can't start until it's done."))
        stay = box.addButton(QCoreApplication.translate(
            "window", "Keep OneUp open"), QMessageBox.ButtonRole.RejectRole)
        box.addButton(QCoreApplication.translate(
            "window", "Close anyway"), QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(stay)          # the safe choice is the one Enter picks
        box.exec()
        return box.clickedButton() is not stay

    def _confirm_quit(self) -> bool:
        """True when it's fine to quit now. A run in flight gets a warning first: a
        user who read a working 379 MiB download as a hang quit mid-transaction, which
        orphaned it and blocked the next two runs (ONEUP-0042)."""
        if not self._run_active:
            return True
        return self._ask_quit_during_run()

    def _quit_requested(self):
        if self._confirm_quit():
            # Quit from the tray menu never reaches closeEvent (ONEUP-0246).
            self._remember_geometry()
            self.details.stop()
            QApplication.quit()

    def _remember_geometry(self):
        """Save the size and, on Wayland, the position KWin has the frame at.

        Qt reports 0,0 for its own position on Wayland, so saveGeometry() keeps only the
        size there; KWin is asked instead. A hidden window is unknown to KWin, and the
        position saved when it hid is still the right one."""
        self.settings.setValue("geometry", self.saveGeometry())
        if placement._on_wayland() and self.isVisible():
            pos = placement.main_frame_position()
            if pos is not None:
                self.settings.setValue("frame_pos", f"{pos[0]},{pos[1]}")

    def _saved_frame_pos(self) -> tuple[int, int] | None:
        try:
            x, y = str(self.settings.value("frame_pos", "")).split(",")
            return int(x), int(y)
        except ValueError:                  # absent or corrupt: let KWin place it
            return None

    # Measured by LocalWebServerManager on real KWin (its ADR-0007): a script run as the
    # window shows is ignored, the first Expose alone is too early, and Expose plus one
    # event-loop tick works; 50 ms is the fallback when no Expose arrives.
    PLACEMENT_FALLBACK_MS = 50

    def showEvent(self, event):
        super().showEvent(event)
        if placement._on_wayland() and self._saved_frame_pos() is not None:
            self._placement_pending = True
            handle = self.windowHandle()
            if handle is not None:
                handle.installEventFilter(self)
            QTimer.singleShot(self.PLACEMENT_FALLBACK_MS, self._restore_position)

    def eventFilter(self, obj, event):
        if (event.type() in (QEvent.Type.StyleChange, QEvent.Type.FontChange)
                and obj in (self.check_btn, self.stop_btn)):
            QTimer.singleShot(0, self._pin_check_stop_width)
        if (event.type() in (QEvent.Type.StyleChange, QEvent.Type.FontChange)
                and obj in self._header_btns):
            QTimer.singleShot(0, self._refit_header)
        if (event.type() in (QEvent.Type.StyleChange, QEvent.Type.FontChange)
                and obj is self.log_toggle):
            # Every size a layout takes from the font is re-taken with it (§4.2).
            QTimer.singleShot(0, self._pin_log_toggle_width)
            QTimer.singleShot(0, self._remeasure_layout)
        if (self._placement_pending and event.type() == QEvent.Type.Expose
                and obj is self.windowHandle()):
            QTimer.singleShot(0, self._restore_position)
        return super().eventFilter(obj, event)

    def _pin_check_stop_width(self):
        """Give Check and Stop the width of the widest label either can show."""
        shown = self.stop_btn.text()
        widths = [self.check_btn.sizeHint().width()]
        for label in (QCoreApplication.translate("window", "Stop"),
                      QCoreApplication.translate("run", "Stopping…")):
            self.stop_btn.setText(label)
            widths.append(self.stop_btn.sizeHint().width())
        self.stop_btn.setText(shown)
        for btn in (self.check_btn, self.stop_btn):
            btn.setMinimumWidth(max(widths))
        # The slot is held at its widest (ONEUP-0239 §4.1.3). A layout switch re-polishes
        # the buttons, and the sheet's min-width replaces the pinned one until this runs
        # again — by then the row had placed Stop at its narrow width, and nothing moved
        # it: Stop grew from there past the window's edge (ONEUP-0307). So the row is
        # re-arranged here.
        self.action_bar.setMinimumWidth(self.run_btn.sizeHint().width()
                                        + self.action_row.spacing() + max(widths))
        # And as tall as its tallest button, or Run's leaving shrinks the slot's line.
        self.action_bar.setMinimumHeight(max(b.sizeHint().height() for b in (
            self.run_btn, self.check_btn, self.stop_btn)))
        self.action_row.invalidate()
        self.action_row.activate()
        if self.host is not None:
            self._fit_minimum()

    def _pin_header_widths(self):
        """Hold each header button at its label's width (ONEUP-0294), and all of
        them at the tallest one's height (ONEUP-0324): Noto Sans has no gear, so
        "⚙ Settings" borrows it from a font with a taller line."""
        height = max(btn.sizeHint().height() for btn in self._header_btns)
        for btn in self._header_btns:
            btn.setMinimumWidth(btn.sizeHint().width())
            btn.setMinimumHeight(height)

    def _refit_header(self):
        self._pin_header_widths()
        self._fit_minimum()

    def _remeasure_layout(self):
        if self.host is not None and shiboken6.isValid(self.host):
            self.host.apply_metrics()
            self._fit_minimum()

    def _fit_minimum(self):
        """The window's minimum is the layout's at the current text size, never
        below MIN_WIDTH (ONEUP-0239 §4.2 item 5). An explicit minimum stops Qt
        taking the layout's for itself, so it is set here; a window smaller than
        the new minimum is grown by Qt."""
        self.setMinimumSize(self.minimumSizeHint().expandedTo(QSize(MIN_WIDTH, 0)))

    def _restore_position(self):
        if not self._placement_pending:     # the Expose path or the fallback got here first
            return
        self._placement_pending = False
        pos = self._saved_frame_pos()
        if pos is not None:
            placement.kwin_restore_position(*pos)

    def closeEvent(self, event):
        self._remember_geometry()
        if self._tray is not None:
            # Resident: hide to the tray instead of quitting. The run stays visible on
            # reopening, so this needs no warning — it isn't a quit.
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                tray._notify_tray_hint(self)
            return
        # No tray: closing the window IS quitting, so it gets the same guard.
        if not self._confirm_quit():
            event.ignore()
            return
        self.details.stop()     # quitting, never hiding, ends a details fetch
        super().closeEvent(event)

    def recenter(self):
        # On Wayland an app is not allowed to move itself — the compositor owns
        # window placement — so self.move() is silently ignored. We ask KWin to
        # do it via a one-shot script. On X11, the direct move works fine.
        if placement._on_wayland():
            placement.kwin_recenter()
        else:
            screen = self.screen() or QApplication.primaryScreen()
            if screen:
                frame = self.frameGeometry()
                frame.moveCenter(screen.availableGeometry().center())
                self.move(frame.topLeft())

    def _text_scale_index(self) -> int:
        """Which TEXT_SCALES entry the saved setting corresponds to (0 if the
        stored value is absent or doesn't match one — a hand-edited config must
        never leave the button label disagreeing with the applied size)."""
        current = float(self.settings.value("text_scale", 1.0, type=float))
        for i, (_label, mult) in enumerate(TEXT_SCALES):
            if abs(mult - current) < 0.01:
                return i
        return 0

    def _refresh_textsize_label(self):
        self.textsize_btn.setText(QCoreApplication.translate(
            "window",
            "Text size: {value}").format(value=TEXT_SCALES[self._text_scale_index()][0]))

    def on_textsize_clicked(self):
        nxt = (self._text_scale_index() + 1) % len(TEXT_SCALES)
        self.settings.setValue("text_scale", TEXT_SCALES[nxt][1])
        self._refresh_textsize_label()
        apply_app_theme(QApplication.instance())

    def _log_keep_days(self) -> int:
        return paths.log_keep_days(self.settings.value("log_keep_days"))

    def _refresh_logkeep_label(self):
        self.logkeep_btn.setText(i18n.counted("keep-logs", self._log_keep_days()))

    def on_logkeep_clicked(self):
        days = paths.LOG_KEEP_DAYS
        nxt = days[(days.index(self._log_keep_days()) + 1) % len(days)]
        self.settings.setValue("log_keep_days", nxt)
        self._refresh_logkeep_label()

    def _refresh_theme_combo(self):
        """Point the combo at the stored id, without re-entering the handler.

        An unrecognised stored value selects Follow system and leaves the stored
        value ALONE (§4.5) — findData returns -1 for an id this version does not
        know, and index 0 is Follow system.
        """
        stored = str(self.settings.value("theme", theme_mod.SYSTEM))
        index = self.theme_combo.findData(stored)
        blocked = self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self.theme_combo.blockSignals(blocked)

    def on_theme_changed(self, _index: int):
        """Apply immediately — there is no OK button in that dialog to press.

        What is STORED is the id, never the displayed label: a label is
        translatable, so storing it would make every user's theme stop resolving
        the first time they changed language (INV-11).
        """
        self.settings.setValue("theme", self.theme_combo.currentData())
        apply_app_theme(QApplication.instance())
        self._show_theme_error()
        # The tray icon is a QIcon built in a method and handed to setIcon at two
        # call sites, neither of which fires on a theme change — so a window
        # holding one rebuilds it here (INV-8). A window with no tray does nothing.
        if getattr(self, "_tray", None) is not None:
            tray.refresh_icon(self)

    def _show_theme_error(self):
        note = theme_mod.last_theme_error
        self.theme_note.setText(note)
        self.theme_note.setVisible(bool(note))

    def _refresh_contrast_label(self):
        self.contrast_btn.setText(
            QCoreApplication.translate("window", "High contrast: on")
            if self.contrast_btn.isChecked()
            else QCoreApplication.translate("window", "High contrast: off"))

    def on_contrast_toggled(self, on: bool):
        self.settings.setValue("high_contrast", on)
        self._refresh_contrast_label()
        apply_app_theme(QApplication.instance())

    def _refresh_appcheck_label(self):
        self.appcheck_btn.setText(
            QCoreApplication.translate("window", "New-version check: on")
            if self.appcheck_btn.isChecked()
            else QCoreApplication.translate("window", "New-version check: off"))

    def on_appcheck_toggled(self, on: bool):
        self.settings.setValue("app_update_check", on)
        self._refresh_appcheck_label()

    def refresh_last_run(self):
        stale = False
        try:
            data = json.loads(paths.HISTORY.read_text())
            when = datetime.fromisoformat(data["when"])
            days = (datetime.now().date() - when.date()).days
            relative = (QCoreApplication.translate("window", "today") if days <= 0 else
                        QCoreApplication.translate("window", "yesterday") if days == 1
                        else i18n.counted("days-ago", days))
            stale = days >= STALE_AFTER_DAYS
            # "Overdue" in WORDS as well as amber: colour alone carries no meaning
            # for a colour-blind user. ⚠ matches the banners' existing idiom.
            overdue = QCoreApplication.translate("window", "  ·  ⚠ overdue") if stale else ""
            # The user's layout (day, month name, year — ONEUP-0182, 2026-10-02) with the
            # month name from their locale. strftime's %b is always the C locale's, since
            # Python never calls setlocale(LC_TIME); the full locale format was declined
            # because it renders all-numeric on this machine's en_ZA.
            stamp = QLocale().toString(
                QDateTime(QDate(when.year, when.month, when.day), QTime(when.hour, when.minute)),
                "dd MMM yyyy, HH:mm")
            self.last_run.setText(
                QCoreApplication.translate(
                    "window",
                    "Last run: {stamp}  ·  {relative}  —  {value}{overdue}").format(
                    stamp=stamp,
                    relative=relative,
                    value=_last_run_outcome(data['status']),
                    overdue=overdue))
        except (OSError, ValueError, KeyError):
            self.last_run.setText(QCoreApplication.translate("window", "Last run: never"))
        # Amber the line once a run is overdue: flip the dynamic property and
        # repolish so the QLabel#LastRun[stale="true"] stylesheet rule re-evaluates.
        self.last_run.setProperty("stale", "true" if stale else "false")
        self.last_run.style().unpolish(self.last_run)
        self.last_run.style().polish(self.last_run)

    def save_last_run(self, status: str):
        try:
            paths.write_whole(paths.HISTORY, json.dumps(
                {"when": datetime.now().isoformat(timespec="seconds"), "status": status}))
        except OSError as exc:        # a full disk keeps the previous record (ONEUP-0184)
            print(f"OneUp: could not record the run in {paths.HISTORY}: {exc}", file=sys.stderr)
        self.refresh_last_run()

    def open_repos(self):
        """Open the repository manager (on/off switches + duplicate cleanup)."""
        repo_list = repos.read_repos()
        if not repo_list:
            QMessageBox.information(
                self, QCoreApplication.translate("window", "Repositories"),
                QCoreApplication.translate(
                    "window",
                    "Couldn't read the repository list. Is zypper available?"))
            return
        repos.RepoManagerDialog(self, repo_list).exec()

    def open_settings(self):
        """Open (or re-raise) the Settings popup — created once so the three
        toggle buttons live in it permanently."""
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self)
        self.diag_btn.setText(QCoreApplication.translate(
            "window", "Copy diagnostics"))  # reset any lingering "Copied ✓"
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _settings_status(self, text: str):
        if self._settings_dialog is not None:
            self._settings_dialog.status.setText(text)

    def toggle_log(self):
        self._show_log(self.package_area.currentWidget() is not self.log)

    def _show_log(self, show: bool = True):
        """Swap the package area between the layout's package page and the log, in
        place (ONEUP-0239 §4.5). Nothing is stored: the window opens on the packages."""
        self.package_area.setCurrentWidget(self.log if show else self.host.page)
        self.log_toggle.setText(_log_toggle_text(show))
        self.openlog_btn.setVisible(show)

    def _pin_log_toggle_width(self):
        """Give the log toggle the width of the wider of its two labels."""
        shown = self.log_toggle.text()
        widths = []
        for label in (_log_toggle_text(False), _log_toggle_text(True)):
            self.log_toggle.setText(label)
            widths.append(self.log_toggle.sizeHint().width())
        self.log_toggle.setText(shown)
        self.log_toggle.setMinimumWidth(max(widths))

    # --- layouts (ONEUP-0239) -------------------------------------------------

    def _layout_id(self) -> str:
        """The stored layout id, or Rows for an id this version does not know."""
        stored = str(self.settings.value("layout", DEFAULT_LAYOUT))
        return stored if any(lid == stored for lid, _n, _c in LAYOUTS) else DEFAULT_LAYOUT

    def _refresh_layout_label(self):
        name = next(n for lid, n, _c in LAYOUTS if lid == self._layout_id())
        self.layout_btn.setText(QCoreApplication.translate("window", "Layout: {name}").format(
            name=QCoreApplication.translate("window", name)))

    def on_layout_clicked(self):
        ids = [lid for lid, _n, _c in LAYOUTS]
        nxt = ids[(ids.index(self._layout_id()) + 1) % len(ids)]
        # The id, never the label: a label is translatable (as on_theme_changed).
        self.settings.setValue("layout", nxt)
        self._refresh_layout_label()
        self.apply_layout(nxt)

    def _shared_widgets(self) -> list[QWidget]:
        """The window's controls a layout places directly. Their own children move
        with them."""
        return [*self.rows.values(), self.action_bar, self.status, self.bar,
                self.message_strip, self.package_area, self.size_link,
                self.last_run, self.rollback_btn, self.log_toggle, self.openlog_btn]

    def apply_layout(self, layout_id: str):
        """Arrange the window's body as `layout_id`, at once, even mid-run.

        The new layout re-parents the window's controls into itself, so nothing
        the run has drawn — badges, bars, banners, the log — is lost. The old
        layout gives back its model callbacks before it is deleted, or the next
        marker would call into a deleted widget (§4.1)."""
        cls = next((c for lid, _n, c in LAYOUTS if lid == layout_id), RowsLayout)
        # A re-parented widget is hidden by Qt until shown again, so each one's
        # own visibility is carried across by hand. "Hidden" means hidden on
        # purpose: a widget never yet shown also reports isHidden().
        explicit = Qt.WidgetAttribute.WA_WState_ExplicitShowHide
        hidden = {w: w.isHidden() and w.testAttribute(explicit) for w in self._shared_widgets()}
        old = self.host
        log_current = old is not None and self.package_area.currentWidget() is self.log
        if old is not None:
            old.release()
        new = cls(self)
        self.package_area.insertWidget(0, new.page)
        self.package_area.setCurrentWidget(self.log if log_current else new.page)
        if old is None:
            self._card_root.addWidget(new, 1)
        else:
            self._card_root.replaceWidget(old, new)
            self.package_area.removeWidget(old.page)
            shiboken6.delete(old.page)
            shiboken6.delete(old)
        self.host = new
        # Qt would show the new layout from the event queue; until then it counts
        # as empty, and the minimum below would be measured without it.
        new.setVisible(True)
        for w, was_hidden in hidden.items():
            w.setVisible(not was_hidden)
        new.apply_metrics()
        new.refresh()
        self._fit_minimum()
        # Tab order must follow the VISUAL order, for EVERY control: what
        # setTabOrder does not state falls back to parenting order, which is
        # where the warning banner's backwards chain came from (ONEUP-0064,
        # ui-and-accessibility.md §5.6).
        for a, b in itertools.pairwise(self.focus_chain()):
            self.setTabOrder(a, b)

    def open_log(self):
        if self._log_path and self._log_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._log_path)))
        else:
            QMessageBox.information(self, QCoreApplication.translate("window", "No log yet"),
                                    QCoreApplication.translate(
                                        "window",
                                        "Run an update or a check first — then the log "
                                        "opens here."))

    def focus_chain(self) -> list[QWidget]:
        """Every focusable control in the window, in the order it is laid out:
        the header's three buttons, then the current layout's own chain.

        Stated as one list because the chain is set from it AND asserted against
        the built layout tree — a control added without a place in the visual
        order is the failure this replaces, and a second hand-written list would
        drift. Each layout states its half (ONEUP-0239 §4.1).
        """
        return [self.settings_btn, self.recenter_btn, self.about_btn,
                *self.host.focus_chain()]

    def selected_steps(self) -> list[str]:
        return [key for key, _t, _d in steps.TASKS if self.rows[key].switch.isChecked()]

    def set_controls_enabled(self, enabled: bool):
        self.run_btn.setEnabled(enabled)
        self.check_btn.setEnabled(enabled)
        for r in self.rows.values():
            r.switch.setEnabled(enabled)
        # Stop is the mirror image: it only exists while a run does. Shown for a real run
        # only — a --check installs nothing, so there is nothing to stop. It REPLACES
        # Run and Check rather than sitting beside them, so during a run it stands
        # alone (ONEUP-0239 §4.1.3); during a check the slot holds both, disabled.
        stoppable = (not enabled) and self._run_active and not self._check_mode
        # The outgoing buttons are hidden first. Showing a widget lays its row out at
        # once, so showing first put both in the row for that pass and pushed the
        # status column aside (ONEUP-0239 INV-1).
        shown, gone = (([self.stop_btn], [self.run_btn, self.check_btn]) if stoppable
                       else ([self.run_btn, self.check_btn], [self.stop_btn]))
        for btn in gone:
            btn.setVisible(False)
        for btn in shown:
            btn.setVisible(True)
        if stoppable:
            self._stop_asked = False
            self.stop_btn.setText(QCoreApplication.translate("window", "Stop"))
            run.sync_stop(self)

    def show_about(self):
        """A small About window: version, licence, links, and a manual update check."""
        box = QMessageBox(self)
        box.setWindowTitle(QCoreApplication.translate(
            "window",
            "About {APP_NAME}").format(APP_NAME=APP_NAME))
        icon = _app_icon()
        if not icon.isNull():
            box.setIconPixmap(icon.pixmap(64, 64))
        box.setTextFormat(Qt.RichText)
        box.setText(QCoreApplication.translate(
            "window",
            "<b>{APP_NAME} {APP_VERSION}</b>").format(
                APP_NAME=APP_NAME, APP_VERSION=APP_VERSION_LABEL))
        box.setInformativeText(
            QCoreApplication.translate(
                "window",
                "One-click updates for openSUSE — system packages, Flatpaks, "
                "firmware, leftover-package removal and cache "
                "cleanup.<br><br>Released under the <b>MIT Licence</b>.<br><br>"
                "{APP_NAME} is an independent project, not an official openSUSE or "
                "SUSE product, and is not endorsed by the openSUSE Project or "
                "SUSE.<br><br><a "
                "href=\"https://github.com/{REPO_SLUG}\">GitHub repository</a> "
                "&nbsp;·&nbsp; <a "
                "href=\"https://software.opensuse.org/package/oneup\">openSUSE "
                "package (OBS)</a>").format(REPO_SLUG=REPO_SLUG, APP_NAME=APP_NAME))
        for lbl in box.findChildren(QLabel):
            lbl.setOpenExternalLinks(True)  # let the links open in the browser.
            # setOpenExternalLinks only grants LinksAccessibleByMouse, so without
            # this the two links above are reachable by mouse alone and there is no
            # other route to either URL — WCAG 2.2 SC 2.1.1 Keyboard, Level A.
            lbl.setTextInteractionFlags(Qt.TextBrowserInteraction)
        check_btn = box.addButton(QCoreApplication.translate(
            "window", "Check for updates"), QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        # Centre over the main window once it's laid out (a QMessageBox sizes to its
        # content on show, so we re-position from inside the event loop).
        QTimer.singleShot(0, lambda: self._center_child(box))
        box.exec()
        if box.clickedButton() is check_btn:
            app_update._check_app_update(self, manual=True)

    def _center_child(self, widget):
        """Move a child popup so its centre sits over the main window's centre."""
        placement.center_on_parent(widget)

