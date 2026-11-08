"""Asking whether a newer OneUp exists, and acting on the answer.

`docs/specs/ONEUP-0112-self-update.md`. **The only module under `oneup/` that makes
network requests** (INV-15): the release list, and on an AppImage its signature and
the AppImage itself. Judging the bytes — versions, the signature, the swap, the
relaunch — is `self_update.py`'s; the pop-up is `update_dialog.py`.

Best-effort and non-blocking: a failed request never throws out of a network slot, and
the automatic check stays silent unless there is something to offer (INV-19). Every
read is capped as it arrives, never on `Content-Length` alone (INV-11).
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from functools import partial

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QMessageBox

from .. import APP_VERSION, REPO_SLUG
from . import self_update
from .update_dialog import UpdateDialog, notes_markdown

LIST_URL = f"https://api.github.com/repos/{REPO_SLUG}/releases?per_page=30"
LIST_CAP = 1 << 20          # 1 MiB
SIG_CAP = 1 << 10           # 1 KiB; the signature itself must be exactly 64 bytes
APPIMAGE_CAP = 256 << 20    # three times the 2.0.0 AppImage (§4.5)
SKIP_KEY = "app_update_skip"


def _installed() -> tuple[int, int, int]:
    return self_update.parse_version(APP_VERSION) or (0, 0, 0)


def _update_check_error(reply: QNetworkReply) -> str:
    """Say what actually stopped the update check, in the user's terms.

    Qt surfaces an HTTP 403 through error() just like a dead network, so branching
    on error() alone told the user GitHub was unreachable when GitHub had answered
    perfectly well — nearly always to say the unauthenticated 60-per-hour budget for
    this address is spent (ONEUP-0089). Blaming the connection sends someone to
    check their wifi over a problem that fixes itself on the hour.
    """
    status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
    if status in (403, 429):
        reset = bytes(reply.rawHeader(b"x-ratelimit-reset")).decode(errors="replace")
        when = ""
        if reset.isdecimal():
            try:
                when = QCoreApplication.translate(
                    "app_update", " Try again after {time}.").format(
                        time=time.strftime("%H:%M", time.localtime(int(reset))))
            except (OverflowError, OSError, ValueError):   # a reset time past time_t (ONEUP-0191)
                pass
        return QCoreApplication.translate(
            "app_update",
            "GitHub limits how often OneUp may check for a new version — 60 times "
            "an hour from one address, shared with anything else here that uses "
            "GitHub.{when}\n\nThis doesn't affect updating your system.").format(when=when)
    if status:
        return QCoreApplication.translate(
            "app_update",
            "GitHub answered with an error (HTTP {status}) when asked for the "
            "latest OneUp version.").format(status=status)
    return QCoreApplication.translate("app_update",
                                      "Couldn't reach GitHub to check for a newer OneUp.")


def _title() -> str:
    """The title every update-check message box carries."""
    return QCoreApplication.translate("app_update", "Check for updates")


def _unreadable() -> str:
    return QCoreApplication.translate(
        "app_update", "Couldn't read GitHub's reply while checking for updates.")


# --- One capped request -------------------------------------------------------------

class _Fetch:
    """One GET, read as it arrives and abandoned past `cap` bytes. `done(fetch)` is
    called once, with `data` the whole body, or None when the request failed, was
    cancelled or ran over its cap."""

    def __init__(self, cap: int, done: Callable[[_Fetch], None]) -> None:
        self.cap = cap
        self.done = done
        self.reply = None
        self.data: bytes | None = None
        self.over = False
        self.cancelled = False
        self._buf = bytearray()

    def on_ready(self) -> None:
        chunk = bytes(self.reply.readAll())
        if self.over or self.cancelled:
            return
        if len(self._buf) + len(chunk) > self.cap:
            self.over = True
            self._buf.clear()
            self.reply.abort()
            return
        self._buf += chunk

    def on_finished(self) -> None:
        try:
            if not (self.over or self.cancelled):
                self.on_ready()          # anything that arrived with the end
            ok = (not (self.over or self.cancelled)
                  and self.reply.error() == QNetworkReply.NetworkError.NoError)
            self.data = bytes(self._buf) if ok else None
            self._buf.clear()
            self.done(self)
        finally:
            self.reply.deleteLater()

    def cancel(self) -> None:
        self.cancelled = True
        if self.reply is not None:
            self.reply.abort()


def _get(win, url: str, cap: int, done: Callable[[_Fetch], None],
         progress: Callable[[int, int], None] | None = None) -> _Fetch:
    """Start a capped GET on a QNetworkAccessManager of its own, so no reply reaches
    another request's handler. The window keeps the fetch alive until it ends."""
    fetches = win._update_fetches

    def _ended(fetch: _Fetch) -> None:
        if fetch in fetches:
            fetches.remove(fetch)
        nam.deleteLater()
        done(fetch)

    fetch = _Fetch(cap, _ended)
    nam = QNetworkAccessManager(win)
    req = QNetworkRequest(QUrl(url))
    if url.startswith("https://api.github.com/"):
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
    fetch.reply = nam.get(req)
    if fetch.reply is None:          # a transport the test suite has refused
        return fetch
    fetches.append(fetch)
    fetch.reply.readyRead.connect(fetch.on_ready)
    fetch.reply.finished.connect(fetch.on_finished)
    if progress is not None:
        fetch.reply.downloadProgress.connect(progress)
    return fetch


def _releases_from(data: bytes | None) -> list[self_update.Release] | None:
    if data is None:
        return None
    try:
        return self_update.releases_from_json(json.loads(data.decode(errors="replace")))
    except ValueError:
        return None


# --- The check -------------------------------------------------------------------------

def attach(win, check: bool) -> None:
    """Wire the window up: the package offer follows the check's rows, and the GitHub
    check runs at start-up when allowed — except on a package install, where the
    software source decides what is offered (§3 item 4)."""
    win._update_releases = None
    win._update_offer = None          # the offered (X, Y, Z), or None
    win._update_release = None        # the offered Release, on an AppImage
    win._update_mode = ""             # "", "offer" or "restart"
    win._update_dialog = None
    win._update_download = None
    win._update_fetches = []          # requests in flight, kept alive until they end
    # Listens for the window's whole life, as the details store does.
    win._update_on_packages = partial(_on_packages, win)
    win.packages.subscribe(win._update_on_packages)
    if check and self_update.install_kind() != "package":
        _check_app_update(win)


def _check_app_update(win, manual: bool = False):
    # manual=True (the About dialog's button) reports the result either way;
    # the automatic startup check stays silent unless a newer release exists.
    _get(win, LIST_URL, LIST_CAP, partial(_on_releases, win, manual))


def _offered_release(releases, kind: str):
    """The newest release newer than this one, and on an AppImage only a signed one."""
    for release in releases:
        if release.version <= _installed():
            return None
        if kind != "appimage" or (release.appimage_url and release.sig_url):
            return release
    return None


def _on_releases(win, manual: bool, fetch: _Fetch):
    if fetch.data is None and not fetch.over:
        if manual:
            QMessageBox.warning(win, _title(), _update_check_error(fetch.reply))
        return
    releases = _releases_from(fetch.data)
    if releases is None:                 # over the cap, not JSON, or not a list (INV-19)
        if manual:
            QMessageBox.warning(win, _title(), _unreadable())
        return
    win._update_releases = releases
    kind = self_update.install_kind()
    if kind == "package":
        if manual:
            _report_package_check(win, releases)
        return
    release = _offered_release(releases, kind)
    win._update_release = release
    _set_offer(win, release.version if release else None, ignore_skip=manual)
    if manual and release is not None:
        open_dialog(win)
    elif manual:
        _say_latest(win)


def _report_package_check(win, releases):
    """The About box's check on a package install (§4.3)."""
    offer = _package_offer(win)
    if offer is not None:
        _set_offer(win, offer, ignore_skip=True)
        QMessageBox.information(win, _title(), QCoreApplication.translate(
            "app_update", "The software source offers OneUp {version}.").format(
                version=self_update.version_text(offer)))
        open_dialog(win)
    elif releases and releases[0].version > _installed():
        QMessageBox.information(win, _title(), QCoreApplication.translate(
            "app_update",
            "OneUp {version} is released, but your software source doesn't carry it yet. "
            "The System update will offer it once it does.").format(
                version=self_update.version_text(releases[0].version)))
    else:
        _say_latest(win)


def _say_latest(win):
    QMessageBox.information(win, _title(), QCoreApplication.translate(
        "app_update", "You're on the latest version ({version}).").format(version=APP_VERSION))


def _package_offer(win) -> tuple[int, int, int] | None:
    """The newer `oneup` the software source will install, from the check's rows."""
    for pkg in win.packages.packages("system"):
        if pkg.name == "oneup" and pkg.state != "installed":
            version = self_update.parse_version(pkg.edition.split("-", 1)[0])
            if version is not None and version > _installed():
                return version
    return None


def _on_packages(win, key: str | None) -> None:
    if key in (None, "system") and self_update.install_kind() == "package":
        _set_offer(win, _package_offer(win))


# --- The banner -------------------------------------------------------------------------

def _skipped(win, version) -> bool:
    return win.settings.value(SKIP_KEY, "", type=str) == self_update.version_text(version)


def _set_offer(win, version, ignore_skip: bool = False) -> None:
    """Show or hide the banner's offer. The restart form takes precedence (§4.8)."""
    win._update_offer = version
    if win._update_mode == "restart":
        return
    if version is None or (not ignore_skip and _skipped(win, version)):
        if win._update_mode == "offer":
            win.appupdate_banner.setVisible(False)
            win._update_mode = ""
        return
    win._update_mode = "offer"
    win.appupdate_label.setText(QCoreApplication.translate(
        "app_update", "A newer OneUp ({tag}) is available — you have {version}.").format(
            tag=self_update.version_text(version), version=APP_VERSION))
    win.appupdate_btn.setText(QCoreApplication.translate("app_update", "What's new"))
    win.appupdate_btn.setEnabled(True)
    win.appupdate_btn.setToolTip("")
    win.appupdate_banner.setVisible(True)


def banner_clicked(win) -> None:
    if win._update_mode == "restart":
        restart(win)
    else:
        open_dialog(win)


def refresh_restart(win) -> None:
    """Put the banner in its restart form when the OneUp on disk is newer than this
    window (§4.8, INV-13). Asked when a run ends and when the tray shows the window.
    Never on an AppImage, whose own swap relaunches it."""
    if not hasattr(win, "_update_mode") or self_update.install_kind() == "appimage":
        return
    on_disk = self_update.disk_version()
    if on_disk is None or on_disk <= _installed():
        return
    win._update_mode = "restart"
    win.appupdate_label.setText(QCoreApplication.translate(
        "app_update", "OneUp was updated to {version}. Restart OneUp to use it.").format(
            version=self_update.version_text(on_disk)))
    win.appupdate_btn.setText(QCoreApplication.translate("app_update", "Restart OneUp"))
    win.appupdate_banner.setVisible(True)
    sync_run_state(win)


def sync_run_state(win) -> None:
    """Update now and Restart OneUp wait for a run to finish (§3 item 8, INV-12).
    Called whenever the window's controls change with a run."""
    if not hasattr(win, "_update_mode"):
        return
    active = win._run_active
    if win._update_dialog is not None:
        win._update_dialog.set_run_active(active)
    if win._update_mode == "restart":
        win.appupdate_btn.setEnabled(not active)
        win.appupdate_btn.setToolTip(QCoreApplication.translate(
            "app_update", "Available once the update run has finished.") if active else "")


# --- The pop-up -------------------------------------------------------------------------

def open_dialog(win) -> None:
    if win._update_offer is None:
        return
    if win._update_dialog is not None:
        win._update_dialog.raise_()
        win._update_dialog.activateWindow()
        return
    dlg = UpdateDialog(win, self_update.version_text(win._update_offer),
                       self_update.install_kind(), partial(_update_now, win),
                       partial(_skip, win), partial(_cancel_download, win))
    win._update_dialog = dlg
    dlg.finished.connect(partial(_dialog_closed, win, dlg))
    dlg.set_run_active(win._run_active)
    if win._update_releases is not None:
        _fill_notes(win)
    elif win.appcheck_btn.isChecked():
        _fetch_notes(win)
    else:
        dlg.set_notes_unavailable()
    dlg.show()


def _dialog_closed(win, dlg, *_args) -> None:
    if win._update_dialog is dlg:
        win._update_dialog = None
    dlg.deleteLater()


def _fill_notes(win) -> None:
    releases = win._update_releases
    installed = _installed()
    win._update_dialog.set_notes(notes_markdown(
        self_update.changelog(releases, installed, win._update_offer), installed,
        complete=any(r.version <= installed for r in releases)))


def _fetch_notes(win) -> None:
    """A package install's pop-up asks GitHub for the notes alone; the offer stands
    whatever the answer, since it came from the software source."""
    _get(win, LIST_URL, LIST_CAP, partial(_on_notes, win))


def _on_notes(win, fetch: _Fetch) -> None:
    releases = _releases_from(fetch.data)
    if win._update_dialog is None:
        return
    if releases is None:
        win._update_dialog.set_notes_unavailable()
        return
    win._update_releases = releases
    _fill_notes(win)


def _skip(win) -> None:
    """Skip this version: remembered across windows; a newer one is offered again."""
    win.settings.setValue(SKIP_KEY, self_update.version_text(win._update_offer))
    if win._update_mode == "offer":
        win.appupdate_banner.setVisible(False)
        win._update_mode = ""
    if win._update_dialog is not None:
        win._update_dialog.close()


# --- Download, verify, swap, relaunch (AppImage only) -----------------------------------

def _didnt_finish() -> str:
    return QCoreApplication.translate("app_update", "The download didn't finish.")


def _update_now(win) -> None:
    release = win._update_release
    dlg = win._update_dialog
    if (release is None or dlg is None or win._run_active
            or self_update.install_kind() != "appimage"):
        return
    dlg.downloading(release.appimage_size)
    _start_download(win, release)


def _start_download(win, release) -> None:
    """The signature first, then the AppImage — both into memory (§4.5)."""
    win._update_download = _get(win, release.sig_url, SIG_CAP, partial(_on_sig, win, release))


def _on_sig(win, release, fetch: _Fetch) -> None:
    dlg = win._update_dialog
    win._update_download = None
    if dlg is None:
        return
    if fetch.data is None:
        dlg.download_ended(_didnt_finish())
        return
    if len(fetch.data) != self_update.SIG_BYTES:
        dlg.download_ended(_not_proved())
        return
    size = release.appimage_size

    def _progress(received: int, total: int) -> None:
        if win._update_dialog is not None:
            win._update_dialog.set_progress(received, total if total > 0 else size)

    win._update_download = _get(win, release.appimage_url, APPIMAGE_CAP,
                                partial(_on_appimage, win, release, fetch.data), _progress)


def _not_proved() -> str:
    return QCoreApplication.translate(
        "app_update",
        "This download couldn't be proved to come from OneUp's author, so it was not installed.")


def _on_appimage(win, release, sig: bytes, fetch: _Fetch) -> None:
    """Verify, and only then write: the bytes verified are the bytes written (INV-7)."""
    dlg = win._update_dialog
    win._update_download = None
    if dlg is None:
        return
    if fetch.data is None:
        dlg.download_ended(_didnt_finish())
        return
    try:
        self_update.verify(fetch.data, sig, self_update.version_text(release.version))
    except self_update.UpdateVerificationError:
        dlg.download_ended(_not_proved())
        return
    if win._run_active:
        dlg.download_ended(QCoreApplication.translate(
            "app_update",
            "An update run started, so OneUp was not replaced. Try again once it has finished."))
        return
    try:
        target = self_update.install(fetch.data, os.environ.get("APPIMAGE", ""))
    except self_update.UpdateInstallError as exc:
        dlg.download_ended(QCoreApplication.translate(
            "app_update", "OneUp can't replace itself in {folder}.").format(folder=exc.args[0]))
        return
    except OSError as exc:
        dlg.download_ended(QCoreApplication.translate(
            "app_update", "OneUp couldn't be replaced: {error}").format(
                error=exc.strerror or exc))
        return
    # The new AppImage is in place: quit whether or not the relaunch starts (§6).
    _relaunch_and_quit(win, [str(target)], quit_anyway=True)


def _cancel_download(win) -> None:
    if win._update_download is not None:
        win._update_download.cancel()


def restart(win) -> None:
    """Restart OneUp on a package install or a checkout (§4.8)."""
    if win._run_active:
        return
    _relaunch_and_quit(win, self_update.restart_argv(), quit_anyway=False)


def _relaunch_and_quit(win, argv: list[str], quit_anyway: bool) -> None:
    if getattr(win, "_tray", None) is not None and not win.isVisible():
        argv = [*argv, "--tray"]       # a resident OneUp comes back resident
    try:
        self_update.relaunch(argv)
    except OSError as exc:
        if not quit_anyway:
            QMessageBox.warning(
                win, QCoreApplication.translate("app_update", "Restart OneUp"),
                QCoreApplication.translate(
                    "app_update", "OneUp couldn't restart itself: {error}").format(
                        error=exc.strerror or exc))
            return
    win._quit_requested()
