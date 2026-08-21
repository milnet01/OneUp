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
import time
from datetime import datetime
from functools import partial
from pathlib import Path

from PySide6.QtCore import QProcess, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAccessible,
    QAccessibleEvent,
    QDesktopServices,
)

try:  # Qt 6.8+: "speak this now" for a screen reader.
    from PySide6.QtGui import QAccessibleAnnouncementEvent
except ImportError:  # older PySide6 (e.g. Leap) — _announce falls back to an Alert.
    QAccessibleAnnouncementEvent = None
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION, REPO_SLUG
from . import (
    app_update,
    auth,
    autostart,
    banners,
    diagnostics,
    paths,
    placement,
    repos,
    rollback,
    run,
    steps,
    tray,
)
from .settings_dialog import SettingsDialog
from .task_row import TaskRow
from .theme import TEXT_SCALES, _app_icon, apply_app_theme

# The last-run line turns amber once the last run is this old, nudging the user
# that an update is overdue (ONEUP-0030).
STALE_AFTER_DAYS = 14


class Updater(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        # Four header controls (Settings · Repositories · Recenter · About); the
        # three background toggles now live inside the Settings popup.
        self.setMinimumWidth(560)
        self.settings = QSettings("OneUp", "OneUp")
        self.proc: QProcess | None = None
        self._buf = ""
        self._total = 0
        self._check_mode = False
        self._unchecked = []         # reasons a --check couldn't read a source (ONEUP-0056)
        self._reboot = False
        self._reboot_reason = ""     # optional "why a reboot matters" phrase from the engine
        self._installed_count = ""   # system packages changed, as reported by the engine
        self._sys_changed = False
        self._step_caption = ""      # current step's bar caption, so @@PROGRESS@@ can extend it
        self._progress_phase = ""    # download/install; a change is what gets announced
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
        self._hint_command = ""   # a runnable command parsed from the shown hint, for Copy
        self._remedy_keys = False  # engine flagged a fixable signing-key error (@@REMEDY@@)
        self._skipped_repos: list[str] = []  # aliases set aside this run (@@REPO_SKIPPED@@)
        self._remedy_skips: list[str] = []  # aliases to offer "Skip … & update the rest" for
        self._log_path: Path | None = None
        self._latest_tag = ""
        self._warn_repo_dup = False   # is the current warning a duplicate-repo one?
        self._warn_snapshots = False  # pre-flight: many Btrfs snapshots may be using disk
        self._snapshot_count = 0      # how many, for the banner text
        self._run_active = False      # is a full update run in flight? (guards the thin action)
        self._settings_dialog: SettingsDialog | None = None
        self._pending_autoupdate = False   # one-shot latch: an enable awaiting a fresh auth settle
        self._tray = None
        self._tray_timer = None
        self._tray_total = 0
        self._tray_checked_at = None
        self._tray_hint_shown = False
        self._local_server = None
        self._traycheck_proc = None
        self._traycheck_buf = ""
        self._traycheck_unknown = False
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self._last_announcement = ""   # what _announce last spoke (see _announce)

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
        tagline = QLabel(f"Keep openSUSE, Flatpak and firmware up to date  ·  v{APP_VERSION}")
        tagline.setObjectName("Tagline")
        titleblock = QVBoxLayout()
        titleblock.setSpacing(2)
        titleblock.addWidget(header)
        titleblock.addWidget(tagline)

        self.auto_btn = QPushButton()
        self.auto_btn.setObjectName("GhostBtn")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setCursor(Qt.PointingHandCursor)
        self.auto_btn.setToolTip(
            "Check weekly in the background and notify you when updates are ready")
        self.auto_btn.setChecked(autostart._autocheck_enabled())
        autostart._refresh_autocheck_label(self)
        self.auto_btn.toggled.connect(partial(autostart.on_autocheck_toggled, self))

        # Opt-in "remember my authorization": stop prompting for the password on
        # every update. Off by default; the real state is probed from the engine
        # after the window is built (_query_auth_status).
        self.auth_btn = QPushButton()
        self.auth_btn.setObjectName("GhostBtn")
        self.auth_btn.setCheckable(True)
        self.auth_btn.setCursor(Qt.PointingHandCursor)
        self.auth_btn.setToolTip("Stop asking for your password on every update "
                                 "(opt-in; can be switched off to revoke instantly)")
        auth._refresh_auth_label(self)
        self.auth_btn.toggled.connect(partial(auth.on_auth_toggled, self))

        # Automatic weekly updates (ONEUP-0022). Off by default; enabling it needs
        # the passwordless rule (coupling enforced in on_autoupdate_toggled). Real
        # state is read from the systemd-user timer.
        self.autoupdate_btn = QPushButton()
        self.autoupdate_btn.setObjectName("GhostBtn")
        self.autoupdate_btn.setCheckable(True)
        self.autoupdate_btn.setCursor(Qt.PointingHandCursor)
        self.autoupdate_btn.setToolTip("Install all updates automatically every week "
                                       "(needs Passwordless)")
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
        self.tray_btn.setToolTip("Show a small tray icon that turns amber when updates are waiting")
        self.tray_btn.setChecked(self.settings.value("tray_enabled", False, type=bool))
        tray._refresh_tray_label(self)
        self.tray_btn.toggled.connect(partial(tray.on_tray_toggled, self))

        self.startboot_btn = QPushButton()
        self.startboot_btn.setObjectName("GhostBtn")
        self.startboot_btn.setCheckable(True)
        self.startboot_btn.setCursor(Qt.PointingHandCursor)
        self.startboot_btn.setToolTip("Start OneUp automatically at login (needs the tray icon)")
        self.startboot_btn.setChecked(autostart._startboot_enabled())
        autostart._refresh_startboot_label(self)
        self.startboot_btn.toggled.connect(partial(autostart.on_startboot_toggled, self))

        if not self._tray_available:
            self.tray_btn.setEnabled(False)
            self.startboot_btn.setEnabled(False)

        # Laid out inside the Settings dialog (like the toggle buttons above), but
        # owned here so it persists across dialog opens.
        self.diag_btn = QPushButton("Copy diagnostics")
        self.diag_btn.setObjectName("GhostBtn")
        self.diag_btn.setCursor(Qt.PointingHandCursor)
        self.diag_btn.setToolTip("Copy version info and your latest update log to "
                                 "the clipboard, ready to paste into a bug report")
        self.diag_btn.clicked.connect(partial(diagnostics.copy_diagnostics, self))

        # Accessibility controls (ONEUP-0028), laid out in the Settings popup but
        # owned here like the toggles above. Text size cycles through TEXT_SCALES
        # rather than using a combo box, matching the existing button idiom.
        self.textsize_btn = QPushButton()
        self.textsize_btn.setObjectName("GhostBtn")
        self.textsize_btn.setCursor(Qt.PointingHandCursor)
        self.textsize_btn.setToolTip("Make all text larger (on top of your desktop's font size)")
        self._refresh_textsize_label()
        self.textsize_btn.clicked.connect(self.on_textsize_clicked)

        self.contrast_btn = QPushButton()
        self.contrast_btn.setObjectName("GhostBtn")
        self.contrast_btn.setCheckable(True)
        self.contrast_btn.setCursor(Qt.PointingHandCursor)
        self.contrast_btn.setToolTip("Plain black-and-white colours with strong outlines")
        self.contrast_btn.setChecked(self.settings.value("high_contrast", False, type=bool))
        self._refresh_contrast_label()
        self.contrast_btn.toggled.connect(self.on_contrast_toggled)

        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.setObjectName("GhostBtn")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setToolTip("Background behaviours: weekly check, "
                                     "passwordless, automatic updates")
        self.settings_btn.clicked.connect(self.open_settings)

        self.recenter_btn = QPushButton("Recenter")
        self.recenter_btn.setObjectName("GhostBtn")
        self.recenter_btn.setCursor(Qt.PointingHandCursor)
        self.recenter_btn.setToolTip("Move the window back to the centre of the screen")
        self.recenter_btn.clicked.connect(self.recenter)

        self.repos_btn = QPushButton("Repositories")
        self.repos_btn.setObjectName("GhostBtn")
        self.repos_btn.setCursor(Qt.PointingHandCursor)
        self.repos_btn.setToolTip("Turn software repositories on/off and clean up duplicates")
        self.repos_btn.clicked.connect(self.open_repos)

        self.about_btn = QPushButton("About")
        self.about_btn.setObjectName("GhostBtn")
        self.about_btn.setCursor(Qt.PointingHandCursor)
        self.about_btn.setToolTip("Version, licence, links and a manual update check")
        self.about_btn.clicked.connect(self.show_about)

        # Two buttons, not four. Four of identical weight beside the app title
        # make none of them findable — the uniform weight is the complaint, not
        # the count — so Repositories and Recenter move into Settings, where the
        # second is a Wayland workaround rather than a feature that earned a
        # place in the header (ONEUP-0064).
        header_row = QHBoxLayout()
        header_row.addLayout(titleblock, 1)
        header_row.addWidget(self.settings_btn, 0, Qt.AlignTop)
        header_row.addWidget(self.about_btn, 0, Qt.AlignTop)
        self.header_row = header_row
        root.addLayout(header_row)
        root.addSpacing(2)

        # Task rows — each a gradient-bordered card.
        self.rows: dict[str, TaskRow] = {}
        for key, title, desc in steps.TASKS:
            r = TaskRow(key, title, desc)
            r.size_requested.connect(partial(run.request_size, self))
            self.rows[key] = r
            root.addWidget(r)

        root.addSpacing(4)

        # Action row: Check (secondary) + Run (primary).
        self.check_btn = QPushButton("Check for updates")
        self.check_btn.setObjectName("GhostBtn")
        self.check_btn.setCursor(Qt.PointingHandCursor)
        self.check_btn.setToolTip("See what would update — installs nothing")
        self.check_btn.clicked.connect(partial(run.start_check, self))

        self.run_btn = QPushButton("Run selected updates")
        self.run_btn.setObjectName("RunBtn")
        self.run_btn.setMinimumHeight(44)
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(partial(run.start_run, self))

        # Stop (only while a run is going). Deliberately not a "cancel" — it takes effect
        # at the next safe point, because interrupting an install can leave programs
        # broken. The label and tooltip say so rather than implying an instant abort.
        # Its own object name, not GhostBtn: it keeps the ghost outline and the
        # transparent fill but takes the danger colour for its border and label,
        # and the focus derivation matches a styled control BY NAME — a restyled
        # control still called GhostBtn would be invisible to it (ONEUP-0064).
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("StopBtn")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setAccessibleName("Stop the update")
        self.stop_btn.setToolTip(
            "Stop after the current step. Anything already installed stays installed — "
            "an install is never cut off half-way, because that can break programs.")
        self.stop_btn.clicked.connect(partial(run.request_stop, self))
        self.stop_btn.setVisible(False)

        # Primary first. Check and Stop do not share a layout position — a hidden
        # widget still holds its own layout item — so the row has three items for
        # the window's whole life and exactly one of indices 1 and 2 is ever
        # visible. What reads as one slot is the visibility rule, not the geometry.
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self.run_btn, 1)
        actions.addWidget(self.check_btn, 0)
        actions.addWidget(self.stop_btn, 0)
        self.action_row = actions
        root.addLayout(actions)

        # Retry-failed (hidden until a run has failures). It lives INSIDE the
        # warning banner, appended below once that banner exists, so the remedy
        # sits beside the thing it remedies rather than reading as a fourth
        # member of the action row above while belonging to none of it.
        self.retry_btn = QPushButton("Retry failed steps")
        self.retry_btn.setObjectName("GhostBtn")
        self.retry_btn.setCursor(Qt.PointingHandCursor)
        self.retry_btn.clicked.connect(partial(run.retry_failed, self))
        self.retry_btn.setVisible(False)

        # Progress + current step.
        self.status = QLabel("Ready.")
        self.status.setObjectName("Status")
        self.status.setAccessibleName("Current status")
        root.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.bar.setAccessibleName("Update progress")
        root.addWidget(self.bar)
        # Liveness, on its own line under the bar (ONEUP-0048): how long the current
        # phase has been going, the download rate, and — when the engine has gone quiet —
        # how long for. A slow mirror and a hung one look identical without this: zypper
        # reports a metadata fetch as undelimited dots with no line ending, so there is
        # nothing for the log pane to draw, and a working run reads as frozen.
        self.activity = QLabel("")
        self.activity.setObjectName("Activity")
        self.activity.setAccessibleName("Activity")
        self.activity.setVisible(False)
        root.addWidget(self.activity)
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
            "RebootBanner", "RestartBtn", "Restart now", partial(banners.restart_now, self),
            name="Restart recommended")
        root.addWidget(self.reboot_banner)

        self.services_banner, self.services_label, self.services_btn = banners._make_banner(self,
            "InfoBanner", "BannerBtn", "Restart services", partial(banners.restart_services, self),
            name="Services should restart")
        root.addWidget(self.services_banner)

        self.warn_banner, self.warn_label, self.warn_btn = banners._make_banner(self,
            "WarnBanner", "BannerBtn", "Show details", partial(banners._warn_action, self),
            name="Warning")
        # A copy-the-suggested-command button, shown only when a hint carries a
        # runnable command the app couldn't run for you — the copy-fallback.
        self.warn_copy_btn = QPushButton("Copy command")
        self.warn_copy_btn.setObjectName("LinkBtn")
        self.warn_copy_btn.setCursor(Qt.PointingHandCursor)
        self.warn_copy_btn.setToolTip("Copy the suggested command to the clipboard")
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
        self.warn_btn2.setAccessibleName("Alternative fix for this warning")
        self.warn_btn2.setCursor(Qt.PointingHandCursor)
        self.warn_btn2.clicked.connect(partial(banners._fix_keys_and_retry, self))
        self.warn_btn2.setVisible(False)
        self.warn_banner.layout().addWidget(self.warn_btn2)
        # Retry, last of the banner's four buttons. Layout order does NOT set the
        # focus chain — parenting order does, which is how this banner's chain
        # came to run backwards — so the chain below states it explicitly.
        self.warn_banner.layout().addWidget(self.retry_btn)
        root.addWidget(self.warn_banner)

        self.appupdate_banner, self.appupdate_label, self.appupdate_btn = banners._make_banner(self,
            "InfoBanner", "BannerBtn", "View release", partial(app_update._open_release, self),
            name="OneUp update available")
        root.addWidget(self.appupdate_banner)

        # Rollback link (shown after the system actually changed).
        self.rollback_btn = QPushButton("Roll back this update…")
        self.rollback_btn.setObjectName("LinkBtn")
        self.rollback_btn.setCursor(Qt.PointingHandCursor)
        self.rollback_btn.clicked.connect(partial(rollback.rollback, self))
        self.rollback_btn.setVisible(False)
        root.addWidget(self.rollback_btn)

        # Log controls: show/hide on the left, open-file on the right.
        self.log_toggle = QPushButton("Show details ▸")
        self.log_toggle.setObjectName("LinkBtn")
        self.log_toggle.setCursor(Qt.PointingHandCursor)
        self.log_toggle.clicked.connect(self.toggle_log)
        self.openlog_btn = QPushButton("Open log file")
        self.openlog_btn.setObjectName("LinkBtn")
        self.openlog_btn.setCursor(Qt.PointingHandCursor)
        self.openlog_btn.clicked.connect(self.open_log)
        logrow = QHBoxLayout()
        logrow.addWidget(self.log_toggle, 0)
        logrow.addStretch(1)
        logrow.addWidget(self.openlog_btn, 0)
        root.addLayout(logrow)

        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Update details will appear here when you run an update.")
        # Named, focusable and readable on demand. Deliberately NOT announced line
        # by line — a run emits hundreds of zypper lines (see the spec's Out of
        # scope): a screen reader would be unusable.
        self.log.setAccessibleName("Update log")
        self.log.setMinimumHeight(180)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.log, 1)

        # Restore the log show/hide preference (shown by default on first run).
        show_log = self.settings.value("log_shown", True, type=bool)
        self.log.setVisible(show_log)
        self.log_toggle.setText("Hide details ▾" if show_log else "Show details ▸")

        # Last-run line.
        self.last_run = QLabel()
        self.last_run.setObjectName("LastRun")
        self.last_run.setAccessibleName("Last update run")
        root.addWidget(self.last_run)
        self.refresh_last_run()

        # Tab order must follow the VISUAL order, for EVERY control rather than
        # the first eleven: what setTabOrder does not state falls back to
        # parenting order, which is where the warning banner's backwards chain
        # came from — its own button is parented before Copy command is inserted
        # ahead of it (ONEUP-0064, ui-and-accessibility.md §5.6).
        for a, b in itertools.pairwise(self.focus_chain()):
            self.setTabOrder(a, b)

        # Restore the last size + position, if we saved one before.
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

        # Non-blocking: is there a newer OneUp release?
        app_update._check_app_update(self)

        # Non-blocking: reflect whether passwordless authorization is active.
        auth._query_auth_status(self)

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
        if len(lines) < 3 or not lines[0].isdigit():
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
        self._check_mode = False
        self._done_status = ""
        run._reset_activity(self)
        self._activity_timer.start()
        self._total = len([s for s in steps.split(",") if s])
        self.bar.setRange(0, max(self._total, 1))
        self.set_controls_enabled(False)
        self.status.setText("An update started earlier is still running — following it…")
        self._announce(self.status.text())
        self._attach_timer = QTimer(self)
        self._attach_timer.setInterval(1000)
        self._attach_timer.timeout.connect(self._poll_attached_run)
        self._attach_timer.start()
        self._poll_attached_run()
        return True

    def _poll_attached_run(self):
        """Read whatever the attached run has appended, then notice when it finishes."""
        try:
            with self._attached_log.open("r", errors="replace") as fh:
                fh.seek(self._attached_pos)
                new = fh.read()
                self._attached_pos = fh.tell()
        except OSError:
            new = ""
        if new:
            self._activity_at = time.monotonic()   # the log grew: the run is alive
        for line in new.splitlines():
            run.handle_line(self, line)
        try:
            os.kill(self._attached_pid, 0)
            return                                  # still going
        except PermissionError:
            return
        except ProcessLookupError:
            pass
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
        box.setWindowTitle("An update is still running")
        box.setText("An update is still running.")
        box.setInformativeText(
            "Closing OneUp won't stop it. Interrupting an update half-way can leave "
            "programs broken, so it carries on in the background and finishes on its "
            "own — but you won't be able to watch it, and the next update can't start "
            "until it's done.")
        stay = box.addButton("Keep OneUp open", QMessageBox.ButtonRole.RejectRole)
        box.addButton("Close anyway", QMessageBox.ButtonRole.AcceptRole)
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
            QApplication.quit()

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
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
        self.textsize_btn.setText(f"Text size: {TEXT_SCALES[self._text_scale_index()][0]}")

    def on_textsize_clicked(self):
        nxt = (self._text_scale_index() + 1) % len(TEXT_SCALES)
        self.settings.setValue("text_scale", TEXT_SCALES[nxt][1])
        self._refresh_textsize_label()
        apply_app_theme(QApplication.instance())

    def _refresh_contrast_label(self):
        self.contrast_btn.setText(
            "High contrast: on" if self.contrast_btn.isChecked() else "High contrast: off")

    def on_contrast_toggled(self, on: bool):
        self.settings.setValue("high_contrast", on)
        self._refresh_contrast_label()
        apply_app_theme(QApplication.instance())

    def refresh_last_run(self):
        stale = False
        try:
            data = json.loads(paths.HISTORY.read_text())
            when = datetime.fromisoformat(data["when"])
            days = (datetime.now().date() - when.date()).days
            relative = ("today" if days <= 0 else
                        "yesterday" if days == 1 else f"{days} days ago")
            stale = days >= STALE_AFTER_DAYS
            # "Overdue" in WORDS as well as amber: colour alone carries no meaning
            # for a colour-blind user. ⚠ matches the banners' existing idiom.
            overdue = "  ·  ⚠ overdue" if stale else ""
            self.last_run.setText(
                f"Last run: {when:%d %b %Y, %H:%M}  ·  {relative}  —  {data['status']}{overdue}")
        except (OSError, ValueError, KeyError):
            self.last_run.setText("Last run: never")
        # Amber the line once a run is overdue: flip the dynamic property and
        # repolish so the QLabel#LastRun[stale="true"] stylesheet rule re-evaluates.
        self.last_run.setProperty("stale", "true" if stale else "false")
        self.last_run.style().unpolish(self.last_run)
        self.last_run.style().polish(self.last_run)

    def save_last_run(self, status: str):
        paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
        paths.HISTORY.write_text(
            json.dumps({"when": datetime.now().isoformat(timespec="seconds"), "status": status})
        )
        self.refresh_last_run()

    def open_repos(self):
        """Open the repository manager (on/off switches + duplicate cleanup)."""
        repo_list = repos.read_repos()
        if not repo_list:
            QMessageBox.information(
                self, "Repositories",
                "Couldn't read the repository list. Is zypper available?")
            return
        repos.RepoManagerDialog(self, repo_list).exec()

    def open_settings(self):
        """Open (or re-raise) the Settings popup — created once so the three
        toggle buttons live in it permanently."""
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self)
        self.diag_btn.setText("Copy diagnostics")  # reset any lingering "Copied ✓"
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _settings_status(self, text: str):
        if self._settings_dialog is not None:
            self._settings_dialog.status.setText(text)

    def toggle_log(self):
        self._show_log(not self.log.isVisible())

    def _show_log(self, show: bool = True):
        self.log.setVisible(show)
        self.log_toggle.setText("Hide details ▾" if show else "Show details ▸")
        self.settings.setValue("log_shown", show)

    def open_log(self):
        if self._log_path and self._log_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._log_path)))
        else:
            QMessageBox.information(self, "No log yet",
                                    "Run an update or a check first — then the log opens here.")

    def focus_chain(self) -> list[QWidget]:
        """Every focusable control in the window, in the order it is laid out.

        Top to bottom, then along each row: within a task row that is the
        disclosure and the switch, then the detail panel underneath it. Stated as
        one list because the chain is set from it AND asserted against the built
        layout tree — a control added here without a place in the visual order is
        the failure this replaces, and a second hand-written list would drift.
        """
        chain: list[QWidget] = [self.settings_btn, self.about_btn]
        for key, _t, _d in steps.TASKS:
            r = self.rows[key]
            chain += [r.disclosure, r.switch, r.detail_scroll]
            # Only the system row lays its size link out; the other four are
            # built, hidden and never given a parent, so they are not in the tree.
            if r.size_btn.parentWidget() is not None:
                chain.append(r.size_btn)
        chain += [self.run_btn, self.check_btn, self.stop_btn,
                  self.restart_btn, self.services_btn,
                  self.warn_copy_btn, self.warn_btn, self.warn_btn2, self.retry_btn,
                  self.appupdate_btn, self.rollback_btn,
                  self.log_toggle, self.openlog_btn, self.log]
        return chain

    def selected_steps(self) -> list[str]:
        return [key for key, _t, _d in steps.TASKS if self.rows[key].switch.isChecked()]

    def set_controls_enabled(self, enabled: bool):
        self.run_btn.setEnabled(enabled)
        self.check_btn.setEnabled(enabled)
        for r in self.rows.values():
            r.switch.setEnabled(enabled)
        # Stop is the mirror image: it only exists while a run does. Shown for a real run
        # only — a --check installs nothing, so there is nothing to stop. It REPLACES
        # Check in the row rather than sitting beside it, so the two are never on
        # screen at once; during a check the slot holds Check, disabled.
        stoppable = (not enabled) and self._run_active and not self._check_mode
        self.check_btn.setVisible(not stoppable)
        self.stop_btn.setVisible(stoppable)
        if stoppable:
            self.stop_btn.setEnabled(True)
            self.stop_btn.setText("Stop")

    def show_about(self):
        """A small About window: version, licence, links, and a manual update check."""
        box = QMessageBox(self)
        box.setWindowTitle(f"About {APP_NAME}")
        icon = _app_icon()
        if not icon.isNull():
            box.setIconPixmap(icon.pixmap(64, 64))
        box.setTextFormat(Qt.RichText)
        box.setText(f"<b>{APP_NAME} {APP_VERSION}</b>")
        box.setInformativeText(
            "One-click updates for openSUSE — system packages, Flatpaks, firmware, "
            "leftover-package removal and cache cleanup.<br><br>"
            "Released under the <b>MIT Licence</b>.<br><br>"
            f'<a href="https://github.com/{REPO_SLUG}">GitHub repository</a> &nbsp;·&nbsp; '
            '<a href="https://software.opensuse.org/package/oneup">openSUSE package (OBS)</a>')
        for lbl in box.findChildren(QLabel):
            lbl.setOpenExternalLinks(True)  # let the links open in the browser.
        check_btn = box.addButton("Check for updates", QMessageBox.ActionRole)
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

