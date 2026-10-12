"""The package details: the store that fetches them, and the dialog that shows them.

`docs/specs/ONEUP-0260-package-details.md` §4.2 and §4.6. The parsers and argv
builders are Qt-free in `package_details.py`; this module runs them. Every call
is an unprivileged read: a fixed list argv, no shell, the locale pinned to C.
"""
from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, QObject, QProcess, QProcessEnvironment, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from . import package_details, package_views
from .packages import Package, PackageModel
from .placement import center_on_parent

# Only system packages have details (§3 item 5): zypper knows nothing of a Flatpak.
SYSTEM = "system"
BATCH_MS = 500          # a burst of additions becomes one call (§4.2)
FETCH_TIMEOUT = 60      # seconds; ONEUP_DETAILS_TIMEOUT overrides it in a test


def _run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Every synchronous rpm call goes through here, so a test can record it."""
    return subprocess.run(argv, **kwargs)  # noqa: S603 — a fixed list argv, no shell.


def _start(proc: QProcess, argv: list[str]) -> None:
    """Every `zypper info` goes through here, for the same reason."""
    proc.start(argv[0], argv[1:])


def _fetch_timeout() -> int:
    try:
        return max(1, int(os.environ.get("ONEUP_DETAILS_TIMEOUT", "")))
    except ValueError:
        return FETCH_TIMEOUT


class DetailsStore(QObject):
    """Every system package's About, and the baseline its What changed is read
    against. One per window, beside the `PackageModel` it subscribes to."""

    def __init__(self, model: PackageModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = model
        self._about: dict[str, package_details.About] = {}
        self._asked: set[str] = set()       # About asked for, answered or not
        self._baselines: dict[str, package_details.Entry] = {}
        self._based: set[str] = set()       # baseline asked for since the last reset
        self._callbacks: list[Callable[[], None]] = []
        self._proc: QProcess | None = None
        self._stopped = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(BATCH_MS)
        self._timer.timeout.connect(self._fetch)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self._expire)
        model.subscribe(self._on_model)

    # --- what the views and the dialog read -------------------------------------

    def has_details(self, package: Package) -> bool:
        return package.key == SYSTEM and package.name in self._about

    def about(self, name: str) -> package_details.About | None:
        return self._about.get(name)

    def baseline(self, name: str) -> package_details.Entry | None:
        return self._baselines.get(name)

    def subscribe(self, callback: Callable[[], None]) -> None:
        """Called after a fetch lands; the model's own subscription does not fire then."""
        self._callbacks.append(callback)

    def unsubscribe(self, callback: Callable[[], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def stop(self) -> None:
        """Kill a running fetch and start no more. The window calls it on quit
        only, never on hide."""
        self._stopped = True
        self._timer.stop()
        self._deadline.stop()
        if self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
            self._proc.waitForFinished(1000)

    # --- fetching ---------------------------------------------------------------

    def _system(self) -> list[Package]:
        return self._model.packages(SYSTEM)

    def _wanting_baseline(self) -> list[Package]:
        """Only before the install: after it `rpm -q` answers the NEW version."""
        return [p for p in self._system() if p.name not in self._based
                and p.state not in ("installed", "removed")]

    def _wanting_about(self) -> list[str]:
        return sorted({p.name for p in self._system()} - self._asked)

    def _on_model(self, key: str | None) -> None:
        if key is None:
            # A baseline is true only until the next install; About does not change.
            self._baselines.clear()
            self._based.clear()
            return
        if key == SYSTEM and (self._wanting_baseline() or self._wanting_about()):
            self._timer.start()

    def _fetch(self) -> None:
        if self._stopped:
            return
        # The baseline first, and synchronously: it must not wait behind zypper.
        wanting = self._wanting_baseline()
        if wanting:
            olds = {p.name: p.old for p in wanting}
            self._based.update(olds)
            argv = package_details.build_baseline_argv(sorted(olds))
            if argv is not None:
                try:
                    out = _run(argv, capture_output=True, text=True,
                               timeout=package_details.RPM_TIMEOUT, env=_c_locale_env())
                    self._baselines.update(package_details.parse_baseline(out.stdout, olds))
                except (OSError, subprocess.SubprocessError):
                    pass
        if self._proc is not None:
            return                  # one zypper at a time; the rest wait for it
        names = self._wanting_about()
        self._asked.update(names)
        argv = package_details.build_info_argv(names)
        if argv is None:
            return
        proc = self._proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("LC_ALL", "C")
        proc.setProcessEnvironment(env)
        proc.finished.connect(lambda *_: self._landed(proc))
        proc.errorOccurred.connect(lambda err: self._failed(proc, err))
        _start(proc, argv)
        self._deadline.start(_fetch_timeout() * 1000)

    def _expire(self) -> None:
        if self._proc is not None:
            self._proc.kill()

    def _failed(self, proc: QProcess, error) -> None:
        # A program that never started sends no finished signal.
        if error == QProcess.ProcessError.FailedToStart:
            self._landed(proc)

    def _landed(self, proc: QProcess) -> None:
        if proc is not self._proc:
            return
        self._deadline.stop()
        self._proc = None
        text = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        proc.deleteLater()
        found = package_details.parse_info(text)
        self._about.update(found)
        if self._wanting_about() or self._wanting_baseline():
            self._timer.start()
        if found:
            for callback in list(self._callbacks):
                callback()


def _c_locale_env() -> dict[str, str]:
    return {**os.environ, "LC_ALL": "C"}


# --- the dialog -----------------------------------------------------------------------

def _entry_lines(entry: package_details.Entry) -> list[str]:
    when = time.strftime("%Y-%m-%d", time.gmtime(entry.time))
    return [package_views.join_parts(when, entry.author), entry.text.strip(), ""]


def details_text(about: package_details.About | None,
                 changed: package_details.WhatChanged) -> str:
    """The text box's whole content: an About heading, then a What changed one.
    The description and the notes are shown as zypper and rpm give them (§10)."""
    lines = [QCoreApplication.translate("details_dialog", "About")]
    if about is None:
        lines.append(QCoreApplication.translate(
            "details_dialog", "zypper has no description of this package."))
    else:
        lines += [p for p in (about.summary, about.description, about.url) if p]
    lines += ["", QCoreApplication.translate("details_dialog", "What changed")]
    if changed.kind == "entries":
        if not changed.known:
            lines.append(QCoreApplication.translate(
                "details_dialog", "OneUp could not tell which of these are new."))
        for entry in changed.entries:
            lines += _entry_lines(entry)
    elif changed.kind == "no-notes":
        lines.append(QCoreApplication.translate(
            "details_dialog", "This package has no change notes."))
    elif changed.kind == "not-found":
        lines.append(QCoreApplication.translate(
            "details_dialog", "The downloaded package is not in the cache; its notes "
            "show once it is installed."))
    else:
        lines.append(QCoreApplication.translate(
            "details_dialog", "The notes show once the new version has downloaded."))
    return "\n".join(lines).rstrip()


def open_details(win, package: Package) -> None:
    """Open the dialog for a package with details; for one without, nothing."""
    if win.details.has_details(package):
        PackageDetailsDialog(win, win.details, package).exec()


class PackageDetailsDialog(QDialog):
    """What one package is, and what its new version changed (§4.6). It reads
    its data once, when it opens; closing and reopening reads again."""

    def __init__(self, parent, store: DetailsStore, package: Package) -> None:
        super().__init__(parent)
        self.setWindowTitle(package.name)
        self.setMinimumWidth(560)
        root = QVBoxLayout(self)

        title = QLabel(package.name)
        title.setObjectName("GroupHeading")
        root.addWidget(title)
        line = QLabel(package_views.join_parts(package_views.versions(package), package.repo))
        line.setObjectName("Tagline")
        line.setWordWrap(True)
        root.addWidget(line)

        changed = package_details.changelog(
            package.name, package.edition, package.state, store.baseline(package.name),
            run=_run)
        self.text = QPlainTextEdit(details_text(store.about(package.name), changed))
        self.text.setObjectName("Log")          # the log's theme and focus treatment
        self.text.setReadOnly(True)
        self.text.setAccessibleName(QCoreApplication.translate("details_dialog", "Package details"))
        root.addWidget(self.text, 1)

        strip = QFrame()
        strip.setObjectName("DialogButtons")
        btns = QHBoxLayout(strip)
        btns.setContentsMargins(0, 0, 0, 0)
        btns.addStretch(1)
        close = QPushButton(QCoreApplication.translate("details_dialog", "Close"))
        close.setObjectName("GhostBtn")
        close.clicked.connect(self.reject)
        btns.addWidget(close)
        root.addWidget(strip)

    def showEvent(self, event):
        super().showEvent(event)
        center_on_parent(self)
