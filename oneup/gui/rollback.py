"""Going back to a snapshot, and thinning the ones that piled up.

The picker is listing only; the destructive rollback and the guarded snapper
cleanup are the two privileged calls, and each stays in the same module as the
guard that protects it (`docs/standards/security.md` §9.4). `selected_id` and
`rollback` both re-check that the snapshot id is a bare number, because it is
interpolated into a root shell.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from . import paths
from .placement import center_on_parent


class RollbackDialog(QDialog):
    """Pick which pre-update restore point to roll back to (ONEUP-0020).

    Listing only — the destructive rollback itself is confirmed and run (via one
    pkexec prompt) back in ``Updater.rollback``. Each ``snapshots`` entry is an
    (id, date, description) tuple sourced from @@SNAPSHOT_ITEM@@ markers; the
    engine already trimmed and ordered them oldest→newest, so we show them
    newest-first and pre-select the pre-update snapshot."""

    def __init__(self, parent, snapshots: list[tuple[str, str, str]], preselect_id: str):
        super().__init__(parent)
        self.setWindowTitle("Roll back this update")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Choose the restore point to return to. OneUp will restore the system "
            "to that snapshot and then reboot — anything changed since then will be "
            "lost. The point taken just before this update is selected for you.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.list = QListWidget()
        self.list.setObjectName("RollbackList")   # see RepoScroll (ONEUP-0076)
        self.list.setAccessibleName("Restore points")
        for sid, date, desc in reversed(snapshots):
            item = QListWidgetItem(f"{date}  —  {desc or 'snapshot'}   (#{sid})")
            item.setData(Qt.UserRole, sid)
            self.list.addItem(item)
            if sid == preselect_id:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)   # newest, if the pre-update id wasn't listed
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        root.addWidget(self.list, 1)

        strip = QFrame()
        strip.setObjectName("DialogButtons")
        btns = QHBoxLayout(strip)
        btns.setContentsMargins(0, 0, 0, 0)
        btns.addStretch(1)
        ok = QPushButton("Roll back & reboot")
        ok.setObjectName("RunBtn")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("GhostBtn")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        root.addWidget(strip)

    def selected_id(self) -> str:
        """The chosen snapshot number, or "" if nothing valid is selected. Re-checks
        isdigit() so a spliced non-numeric payload can never reach the root shell."""
        item = self.list.currentItem()
        sid = item.data(Qt.UserRole) if item else ""
        return sid if isinstance(sid, str) and sid.isdigit() else ""

    def showEvent(self, event):
        # Centre over the main window each time it opens (dialog standard).
        super().showEvent(event)
        center_on_parent(self)


def rollback(win):
    # The rollback target defaults to the pre-update snapshot, but when the
    # engine enumerated recent restore points (@@SNAPSHOT_ITEM@@) the user can
    # pick an older one — e.g. to undo a problem that started two updates ago
    # (ONEUP-0020). Both the picker and the guard below re-check the id is a
    # bare number: it is interpolated into a root shell, so a spliced
    # non-numeric payload must never reach it. (isdigit() also covers empty.)
    target = win._snapshot
    if win._snapshots:
        dlg = RollbackDialog(win, win._snapshots, win._snapshot)
        if dlg.exec() != QDialog.Accepted:
            return
        target = dlg.selected_id()
    if not target.isdigit():
        return
    answer = QMessageBox.warning(
        win, "Roll back this update?",
        f"This restores the system to restore point #{target} and then "
        "REBOOTS. Anything changed since that snapshot will be lost."
        "\n\nContinue?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if answer == QMessageBox.Yes:
        QProcess.startDetached(
            "pkexec", ["sh", "-c",
                       f"snapper rollback {target} && systemctl reboot"])


def _thin_snapshots(win):
    """Thin accumulated Btrfs snapshots via the engine's guarded snapper cleanup
    (retention policy only — never a hand-picked delete), after the user confirms.
    Runs as its own privileged engine process so the recent rollback points stay."""
    p = getattr(win, "_thin_proc", None)
    if p is not None and p.state() != QProcess.NotRunning:
        return  # a thin is already in flight
    if win._run_active:
        QMessageBox.information(
            win, "Update in progress",
            "Let the current update finish, then thin the snapshots.")
        return
    box = QMessageBox(win)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle("Thin old snapshots?")
    box.setText("Remove older system restore points to free disk space?")
    box.setInformativeText(
        "OneUp will ask Btrfs's snapshot tool (snapper) to clear out the older "
        "restore points its own retention policy considers expendable. Your most "
        "recent restore points are kept, so you can still roll back a bad update.")
    box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
    box.button(QMessageBox.Ok).setText("Thin snapshots")
    box.setDefaultButton(QMessageBox.Cancel)
    QTimer.singleShot(0, lambda: win._center_child(box))
    if box.exec() != QMessageBox.Ok:
        return
    win.warn_btn.setEnabled(False)
    win.status.setText("Thinning snapshots… (approve the password popup)")
    paths.STATE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    p = QProcess(win)
    p.setProcessChannelMode(QProcess.MergedChannels)
    p.finished.connect(lambda _c, _s, pr=p: _on_thin_finished(win, pr))
    win._thin_proc = p
    p.start("bash", [str(paths.ENGINE), "--thin-snapshots",
                     f"--log={paths.STATE_LOG_DIR / f'{stamp}.thin.log'}"])


def _on_thin_finished(win, proc: QProcess):
    """Report the outcome of a --thin-snapshots run and clear the advisory banner."""
    out = bytes(proc.readAllStandardOutput()).decode(errors="replace")
    win.warn_btn.setEnabled(True)
    removed = None
    for line in out.splitlines():
        if line.startswith("@@SNAPSHOTS@@|thinned|"):
            n = line.split("|")[-1]
            removed = int(n) if n.isdigit() else None
        elif line.startswith("@@HINT@@|"):
            QMessageBox.warning(win, "Couldn't thin snapshots", line.split("|", 1)[1])
    if removed:
        win.status.setText(f"Thinned {removed} old snapshot(s).")
        win._warn_snapshots = False
        win.warn_banner.setVisible(False)
    elif removed == 0:
        win.status.setText("No old snapshots needed thinning.")
        win._warn_snapshots = False
        win.warn_banner.setVisible(False)
    else:
        # No marker (auth cancelled / error): leave the banner so it can be retried.
        win.status.setText("Ready.")
