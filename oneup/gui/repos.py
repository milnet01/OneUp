"""Reading and editing the machine's software sources.

Listing is read-only; applying the changes needs one admin (pkexec) prompt, and
`_ALIAS_RE` is the guard on the alias that reaches it — the guard and the
command it protects stay in one module on purpose
(`docs/standards/security.md` §9.4).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections import Counter

from PySide6.QtCore import QProcess, QSettings, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .placement import center_on_parent
from .theme import card_inside
from .toggle_switch import ToggleSwitch

# --- repository listing / management ---------------------------------------
# Repo aliases are the identifiers passed to a root `zypper modifyrepo/removerepo`;
# validate them against this before they reach a shell (defence in depth, mirroring
# the rollback snapshot-id and service-name guards).
_ALIAS_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9:@._+-]*")

def _parse_repos(text: str) -> list[dict]:
    """Parse `zypper lr -u` table output into [{alias, name, enabled, url}].
    Rows look like '# | Alias | Name | Enabled | GPG Check | Refresh | URI'; the
    header, separator, and the priority preamble are skipped (their first column
    isn't a number)."""
    repos = []
    for line in text.splitlines():
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 7 or not cols[0].isdigit():
            continue
        repos.append({
            "alias": cols[1],
            "name": cols[2] or cols[1],
            "enabled": cols[3][:1].lower() == "y",
            "url": cols[-1],
        })
    return repos


def _repo_purpose(repo: dict) -> str:
    """A one-line, plain-English guess at what a repository is for. openSUSE repos
    carry no description field, so this maps well-known naming patterns (alias / name
    / URL); an unrecognised repo falls back to a generic line. Order matters — the
    narrower patterns (debug, source) come before the broad ones (oss)."""
    hay = f"{repo['alias']} {repo['name']} {repo['url']}".lower()
    if "debug" in hay:
        return "Debug symbols — for diagnosing crashes. Usually left off."
    if "source" in hay or "/src" in hay:
        return "Source-code packages — for building software yourself. Usually left off."
    if "packman" in hay:
        return "Packman — extra multimedia codecs and media apps."
    if "nvidia" in hay:
        return "NVIDIA graphics drivers."
    if "packages.microsoft.com" in hay or "vscode" in hay:
        return "Microsoft — e.g. Visual Studio Code."
    if "dl.google.com" in hay or "google-chrome" in hay:
        return "Google Chrome browser."
    if "brave" in hay:
        return "Brave browser."
    if "non-oss" in hay or "nonoss" in hay:
        return "Non-open-source packages — some drivers, firmware and codecs."
    if "update" in hay:
        return "Official security and bug-fix updates."
    if "home:" in hay or "/repositories/" in hay:
        return "Community package repository (openSUSE Build Service)."
    if "oss" in hay or "repo-main" in hay or "-main" in hay:
        return "Main openSUSE package collection."
    return "Software package repository."


def read_repos() -> list[dict]:
    """Read the system's repositories (read-only — no root needed)."""
    if not shutil.which("zypper"):
        return []
    try:
        out = subprocess.run(
            ["zypper", "--non-interactive", "lr", "-u"],  # noqa: S607 — fixed argv.
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "LC_ALL": "C"},  # pin the 'Yes'/'No' + column text
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return _parse_repos(out)


class RepoManagerDialog(QDialog):
    """Turn repositories on/off, and remove ones whose URL duplicates another's.
    Listing is read-only; applying the changes needs one admin (pkexec) prompt."""

    def __init__(self, parent, repos: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Repositories")
        self.setMinimumWidth(720)   # wide enough that repo URLs aren't cut off
        self._rows: list[dict] = []   # {repo, switch, remove(bool), frame}
        self._proc: QProcess | None = None

        # Remember the size the user last left this dialog at (position is always
        # re-centred over the main window in showEvent).
        self._settings = QSettings("OneUp", "OneUp")
        geo = self._settings.value("repos_geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(780, 560)

        # A URL used by more than one repository is the duplicate we can clean up.
        url_counts = Counter(r["url"] for r in repos if r["url"])

        root = QVBoxLayout(self)
        intro = QLabel(
            "Turn repositories on or off. ⚠ marks a URL used by more than one "
            "repository — a common cause of update conflicts; you can remove the "
            "extra copy. Nothing changes until you press Apply.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        inner = QWidget()
        lst = QVBoxLayout(inner)
        lst.setSpacing(6)
        for repo in repos:
            is_dup = bool(repo["url"]) and url_counts[repo["url"]] > 1
            lst.addWidget(self._make_row(repo, is_dup))
        lst.addStretch(1)
        scroll = QScrollArea()
        # Named as well as described (ONEUP-0076): the focus cue is keyed to
        # object names, and an unnamed OneUp-built focusable widget is a widget
        # the sweep fails rather than one it excuses.
        scroll.setObjectName("RepoScroll")
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        scroll.setMinimumHeight(280)
        scroll.setAccessibleName("Repository list")
        self.scroll = scroll
        root.addWidget(scroll, 1)

        strip = QFrame()
        strip.setObjectName("DialogButtons")
        btns = QHBoxLayout(strip)
        btns.setContentsMargins(0, 0, 0, 0)
        btns.addStretch(1)
        self.apply_btn = QPushButton("Apply changes")
        self.apply_btn.setObjectName("RunBtn")
        self.apply_btn.clicked.connect(self._apply)
        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("GhostBtn")
        self.close_btn.clicked.connect(self.reject)
        btns.addWidget(self.apply_btn)
        btns.addWidget(self.close_btn)
        root.addWidget(strip)

    def _make_row(self, repo: dict, is_dup: bool) -> QFrame:
        fr = QFrame()
        fr.setObjectName("RowBorder")
        lay = QHBoxLayout(card_inside(fr))
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(1)
        name = QLabel(("⚠  " if is_dup else "") + repo["name"])
        name.setObjectName("TaskName")
        # A plain-English line describing what the repo is for, then its URL (dim).
        purpose = QLabel(_repo_purpose(repo))
        purpose.setWordWrap(True)
        url = QLabel(repo["url"])
        url.setObjectName("TaskDesc")
        url.setWordWrap(True)
        text.addWidget(name)
        text.addWidget(purpose)
        text.addWidget(url)
        lay.addLayout(text, 1)

        entry: dict = {"repo": repo, "remove": False, "frame": fr}
        if is_dup:
            rm = QPushButton("Remove")
            rm.setObjectName("LinkBtn")
            rm.setCursor(Qt.PointingHandCursor)
            rm.clicked.connect(lambda _=False, e=entry: self._mark_removed(e))
            lay.addWidget(rm, 0)
        switch = ToggleSwitch()
        switch.setChecked(repo["enabled"])
        # Named, but NOT with the on/off state baked in ("… — enabled" would
        # announce "enabled" for a disabled repo). Qt reports checked state itself.
        switch.setAccessibleName(f"{repo['name']} — include this repository")
        lay.addWidget(switch, 0, Qt.AlignVCenter)
        entry["switch"] = switch
        self._rows.append(entry)
        return fr

    def _mark_removed(self, entry: dict):
        entry["remove"] = True
        entry["frame"].setEnabled(False)   # grey it out; excluded from the toggle diff

    def _build_apply_command(self) -> list[str] | None:
        """The single pkexec command that applies every change, [] if there's
        nothing to do, or None if an alias fails validation (so it never reaches a
        root shell)."""
        enable, disable, remove = [], [], []
        for e in self._rows:
            alias = e["repo"]["alias"]
            if e["remove"]:
                remove.append(alias)
            elif e["switch"].isChecked() != e["repo"]["enabled"]:
                (enable if e["switch"].isChecked() else disable).append(alias)
        changes = enable + disable + remove
        if not changes:
            return []
        if any(not _ALIAS_RE.fullmatch(a) for a in changes):
            return None
        parts = []
        if disable:
            parts.append("zypper --non-interactive modifyrepo --disable " + " ".join(disable))
        if enable:
            parts.append("zypper --non-interactive modifyrepo --enable " + " ".join(enable))
        if remove:
            parts.append("zypper --non-interactive removerepo " + " ".join(remove))
        return ["pkexec", "sh", "-c", " && ".join(parts)]

    def _apply(self):
        cmd = self._build_apply_command()
        if cmd == []:
            self.accept()
            return
        if cmd is None:
            QMessageBox.warning(self, "Repositories",
                                "A repository name looked unsafe — nothing was changed.")
            return
        if QMessageBox.question(
                self, "Apply repository changes",
                "OneUp will apply your repository changes. This needs administrator "
                "rights and is reversible.\n\nApply now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.apply_btn.setEnabled(False)
        self._proc = QProcess(self)
        self._proc.finished.connect(self._on_applied)
        self._proc.start(cmd[0], cmd[1:])

    def _on_applied(self, code: int, _status):
        if code == 0:
            QMessageBox.information(self, "Repositories", "Repository changes applied.")
            self.accept()
        else:
            QMessageBox.warning(self, "Repositories",
                                "Couldn't apply the changes — they may have been cancelled.")
            self.apply_btn.setEnabled(True)

    def showEvent(self, event):
        # Centre over the main window each time it opens (size is restored from
        # settings; only the position is re-centred).
        super().showEvent(event)
        center_on_parent(self)

    def done(self, result: int):
        # done() is the funnel for Apply, Close and the title-bar close — persist
        # the size on the way out.
        self._settings.setValue("repos_geometry", self.saveGeometry())
        super().done(result)
