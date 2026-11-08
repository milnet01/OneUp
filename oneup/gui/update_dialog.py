"""The What's new pop-up: every version's notes since yours, and what can be done about it.

`docs/specs/ONEUP-0112-self-update.md` §4.4. Non-modal — shown with `show()`, never
`exec()`, so a run's output keeps flowing (INV-18). It fetches nothing and decides
nothing: `app_update.py` fills it and answers its buttons. A link or an image in the
notes does nothing, because nothing in this feature opens a browser (INV-5).
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from .. import APP_VERSION
from . import self_update
from .placement import center_on_parent


def notes_markdown(releases, installed: tuple[int, int, int], complete: bool) -> str:
    """Each release's notes under a "Version X.Y.Z" heading, newest first. `complete` is
    false when the list does not reach back to `installed`, which the last line says."""
    parts = []
    for release in releases:
        heading = QCoreApplication.translate("update_dialog", "Version {version}").format(
            version=self_update.version_text(release.version))
        body = release.body.strip() or QCoreApplication.translate(
            "update_dialog", "No notes were published for this version.")
        parts.append(f"## {heading}\n\n{body}")
    if not complete:
        parts.append(QCoreApplication.translate(
            "update_dialog", "Notes for earlier versions are not shown."))
    return "\n\n".join(parts)


def _kind_message(kind: str) -> str:
    if kind == "package":
        return QCoreApplication.translate(
            "update_dialog", "Run the System update to install it.")
    if kind == "checkout":
        return QCoreApplication.translate(
            "update_dialog",
            "This copy of OneUp runs from its source folder. Update it with git.")
    return ""


class UpdateDialog(QDialog):
    """`kind` is self_update.install_kind()'s answer; only an AppImage gets Update now."""

    def __init__(self, parent, offered: str, kind: str, on_update: Callable[[], None],
                 on_skip: Callable[[], None], on_cancel: Callable[[], None]) -> None:
        super().__init__(parent)
        self.setWindowTitle(QCoreApplication.translate("update_dialog", "What's new in OneUp"))
        self._on_cancel = on_cancel
        self.heading = QLabel(QCoreApplication.translate(
            "update_dialog", "OneUp {offered} is available — you have {installed}.").format(
                offered=offered, installed=APP_VERSION))
        self.heading.setWordWrap(True)
        self.notes = QTextBrowser()
        self.notes.setOpenLinks(False)
        self.notes.setOpenExternalLinks(False)
        self.notes.setAccessibleName(QCoreApplication.translate("update_dialog",
                                                                "Release notes"))
        self.notes.setPlainText(QCoreApplication.translate(
            "update_dialog", "Fetching the release notes…"))
        self.message = QLabel(_kind_message(kind))
        self.message.setWordWrap(True)
        self.message.setVisible(bool(self.message.text()))
        self.progress = QProgressBar()
        self.progress.setAccessibleName(QCoreApplication.translate(
            "update_dialog", "Download progress"))
        self.progress.setVisible(False)

        self.update_btn = QPushButton(QCoreApplication.translate("update_dialog",
                                                                 "Update now"))
        self.update_btn.setAccessibleName(QCoreApplication.translate(
            "update_dialog", "Update OneUp now"))
        self.update_btn.clicked.connect(on_update)
        self.update_btn.setVisible(kind == "appimage")
        self.skip_btn = QPushButton(QCoreApplication.translate("update_dialog",
                                                               "Skip this version"))
        self.skip_btn.setAccessibleName(QCoreApplication.translate(
            "update_dialog", "Skip this version of OneUp"))
        self.skip_btn.clicked.connect(on_skip)
        self.close_btn = QPushButton(
            QCoreApplication.translate("update_dialog", "Later") if kind == "appimage"
            else QCoreApplication.translate("update_dialog", "Close"))
        self.close_btn.setAccessibleName(self.close_btn.text())
        self.close_btn.clicked.connect(self.close)
        self.cancel_btn = QPushButton(QCoreApplication.translate("update_dialog", "Cancel"))
        self.cancel_btn.setAccessibleName(QCoreApplication.translate(
            "update_dialog", "Cancel the download"))
        self.cancel_btn.clicked.connect(on_cancel)
        self.cancel_btn.setVisible(False)
        self._actions = [b for b in (self.update_btn, self.skip_btn, self.close_btn)
                         if not b.isHidden()]

        row = QHBoxLayout()
        row.addStretch(1)
        for btn in (self.update_btn, self.skip_btn, self.close_btn, self.cancel_btn):
            row.addWidget(btn)
        lay = QVBoxLayout(self)
        for widget in (self.heading, self.notes, self.message, self.progress):
            lay.addWidget(widget)
        lay.addLayout(row)
        (self.update_btn if kind == "appimage" else self.close_btn).setDefault(True)

    def set_notes(self, markdown: str) -> None:
        self.notes.setMarkdown(markdown)

    def set_notes_unavailable(self) -> None:
        self.notes.setPlainText(QCoreApplication.translate(
            "update_dialog", "The release notes could not be fetched."))

    def set_run_active(self, active: bool) -> None:
        """Update now waits for a run to finish (§3 item 8, INV-12)."""
        self.update_btn.setEnabled(not active)
        self.update_btn.setToolTip(QCoreApplication.translate(
            "update_dialog", "Available once the update run has finished.") if active else "")

    def show_message(self, text: str) -> None:
        self.message.setText(text)
        self.message.setVisible(bool(text))

    def downloading(self, total: int) -> None:
        """Swap the actions for a progress bar and Cancel. A size of 0 shows a busy bar."""
        self.progress.setRange(0, max(total, 0))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        for btn in self._actions:
            btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setFocus()
        self.show_message(QCoreApplication.translate("update_dialog", "Downloading OneUp…"))

    def set_progress(self, received: int, total: int) -> None:
        if total > 0 and self.progress.maximum() != total:
            self.progress.setRange(0, total)
        if self.progress.maximum() > 0:
            self.progress.setValue(min(received, self.progress.maximum()))

    def download_ended(self, message: str) -> None:
        """Bring the actions back after a download that did not install."""
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        for btn in self._actions:
            btn.setVisible(True)
        self.show_message(message)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        center_on_parent(self)

    def closeEvent(self, event) -> None:
        if self.cancel_btn.isVisible():
            self._on_cancel()
        super().closeEvent(event)
