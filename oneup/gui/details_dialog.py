"""The package details: the store that fetches them, and the dialog that shows them.

`docs/specs/ONEUP-0260-package-details.md` §4.2, §4.6 and §4.7. The parsers and
argv builders are Qt-free in `package_details.py` and `flatpak_details.py`; this
module runs them. Every call is an unprivileged read: a fixed list argv, no shell,
the locale pinned to C.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import (
    QCoreApplication,
    QObject,
    QProcess,
    QProcessEnvironment,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from . import flatpak_details, package_details, package_views
from .packages import Package, PackageModel
from .placement import center_on_parent

# System packages take their details from zypper and rpm (§4.1), Flatpaks from
# their remote's AppStream catalogue (§4.7). Firmware and leftovers have none.
SYSTEM = "system"
FLATPAK = "flatpak"
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
    against; every Flatpak's catalogue entries, and the versions installed before
    the run. One per window, beside the `PackageModel` it subscribes to."""

    # The catalogue read's result, sent from its worker thread; Qt queues it
    # to this object's thread, so the store is only ever touched there.
    _catalogue_read = Signal(object)

    def __init__(self, model: PackageModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = model
        self._about: dict[str, package_details.About] = {}
        self._asked: set[str] = set()       # About asked for, answered or not
        self._baselines: dict[str, package_details.Entry] = {}
        self._based: set[str] = set()       # baseline asked for since the last reset
        self._flatpaks: dict[str, list[flatpak_details.Component]] = {}
        self._fp_asked: set[str] = set()    # catalogue asked for, answered or not
        self._installed: dict[str, set[str]] = {}
        self._fp_based: set[str] = set()    # installed versions read since the last reset
        self._reading = False               # one catalogue read at a time
        self._catalogue_read.connect(self._catalogue_landed)
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
        if package.key == FLATPAK:
            return package.name in self._flatpaks
        return package.key == SYSTEM and package.name in self._about

    def about(self, name: str) -> package_details.About | None:
        return self._about.get(name)

    def baseline(self, name: str) -> package_details.Entry | None:
        return self._baselines.get(name)

    def flatpak(self, package: Package) -> flatpak_details.Component | None:
        return flatpak_details.choose(self._flatpaks.get(package.name, []), package.edition)

    def installed(self, name: str) -> set[str] | None:
        """The versions installed before this run, or None if never read for it."""
        return self._installed.get(name) if name in self._fp_based else None

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

    def _flatpak_rows(self) -> list[Package]:
        return [p for p in self._model.packages(FLATPAK) if flatpak_details.valid_id(p.name)]

    def _wanting_installed(self) -> list[Package]:
        """Only before the install, for the same reason as the system baseline."""
        return [p for p in self._flatpak_rows() if p.name not in self._fp_based
                and p.state not in ("installed", "removed")]

    def _wanting_catalogue(self) -> list[Package]:
        return [p for p in self._flatpak_rows() if p.name not in self._fp_asked]

    def _on_model(self, key: str | None) -> None:
        if key is None:
            # A baseline is true only until the next install; About does not change.
            self._baselines.clear()
            self._based.clear()
            self._installed.clear()
            self._fp_based.clear()
            return
        if key == SYSTEM and (self._wanting_baseline() or self._wanting_about()):
            self._timer.start()
        if key == FLATPAK and (self._wanting_installed() or self._wanting_catalogue()):
            self._timer.start()

    def _fetch(self) -> None:
        if self._stopped:
            return
        self._fetch_flatpak()
        # The baseline first, and synchronously: it must not wait behind zypper.
        wanting = self._wanting_baseline()
        if wanting:
            olds = {p.name: p.old for p in wanting}
            self._based.update(olds)
            argv = package_details.build_baseline_argv(sorted(olds))
            if argv is not None:
                try:
                    # A changelog is in whatever encoding its packager used, and a
                    # real one was not UTF-8 (ONEUP-0334): never let it raise here.
                    out = _run(argv, capture_output=True, text=True, errors="replace",
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
            self._notify()

    def _notify(self) -> None:
        for callback in list(self._callbacks):
            callback()

    def _fetch_flatpak(self) -> None:
        """The installed versions synchronously, as the system baseline is; the
        catalogue on a worker thread, because parsing it takes most of a second."""
        wanting = self._wanting_installed()
        if wanting:
            self._fp_based.update(p.name for p in wanting)
            try:
                out = _run(flatpak_details.build_installed_argv(), capture_output=True,
                           text=True, errors="replace",
                           timeout=package_details.RPM_TIMEOUT, env=_c_locale_env())
                found = flatpak_details.parse_installed(out.stdout)
                self._installed.update({p.name: found.get(p.name, set()) for p in wanting})
            except (OSError, subprocess.SubprocessError):
                pass
        if self._reading:
            return                  # one read at a time; the rest wait for it
        rows = self._wanting_catalogue()
        if not rows:
            return
        ids = {p.name for p in rows}
        self._fp_asked.update(ids)
        files = flatpak_details.appstream_files({p.repo for p in rows})
        if not files:
            return
        self._reading = True

        def work() -> None:
            # A failure must still land, or `_reading` would block every later read.
            found: dict = {}
            try:
                found = flatpak_details.read(files, ids)
            finally:
                with contextlib.suppress(RuntimeError):     # the window already gone
                    self._catalogue_read.emit(found)

        # A daemon thread: a local file read with no lock or network to wait on,
        # so it ends on its own, and quitting the window never waits for it.
        threading.Thread(target=work, name="oneup-appstream", daemon=True).start()

    def _catalogue_landed(self, found: dict) -> None:
        self._reading = False
        if self._stopped:
            return
        self._flatpaks.update(found)
        if self._wanting_catalogue() or self._wanting_installed():
            self._timer.start()
        if found:
            self._notify()


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


def _release_lines(release: flatpak_details.Release) -> list[str]:
    when = time.strftime("%Y-%m-%d", time.gmtime(release.time)) if release.time else ""
    return [package_views.join_parts(release.version, when), release.text]


def flatpak_text(comp: flatpak_details.Component | None,
                 changed: flatpak_details.WhatChanged) -> str:
    """A Flatpak's text box: About, then What changed, from its remote's catalogue.
    The catalogue's own words are shown as it gives them (§4.7)."""
    lines = [QCoreApplication.translate("details_dialog", "About")]
    if comp is not None:
        lines += [p for p in (comp.name, comp.summary, comp.description, comp.url) if p]
    lines += ["", QCoreApplication.translate("details_dialog", "What changed")]
    if changed.kind == "no-notes":
        lines.append(QCoreApplication.translate(
            "details_dialog", "The Flatpak source lists no versions for this item."))
    elif changed.known and not changed.entries:
        lines.append(QCoreApplication.translate(
            "details_dialog", "The Flatpak source lists no version newer than the one "
            "installed; this update changes its files only."))
    else:
        if not changed.known:
            lines.append(QCoreApplication.translate(
                "details_dialog", "OneUp could not tell which of these are new."))
        for release in changed.entries:
            lines += [p for p in _release_lines(release) if p] + [""]
    return "\n".join(lines).rstrip()


def _text_for(store: DetailsStore, package: Package) -> str:
    if package.key == FLATPAK:
        comp = store.flatpak(package)
        return flatpak_text(comp, flatpak_details.what_changed(
            comp, store.installed(package.name)))
    changed = package_details.changelog(
        package.name, package.edition, package.state, store.baseline(package.name), run=_run)
    return details_text(store.about(package.name), changed)


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

        self.text = QPlainTextEdit(_text_for(store, package))
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
