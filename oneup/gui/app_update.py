"""Asking GitHub whether a newer OneUp exists.

Best-effort and non-blocking: a flaky check must never throw out of the network
slot, and the automatic startup check stays silent unless a newer release
exists.
"""
from __future__ import annotations

import json
import re
import time
from functools import partial

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QMessageBox

from .. import APP_VERSION, REPO_SLUG


def _version_tuple(v: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", v)] or [0]


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
        when = (time.strftime(" Try again after %H:%M.", time.localtime(int(reset)))
                if reset.isdigit() else "")
        return ("GitHub limits how often OneUp may check for a new version — 60 times "
                "an hour from one address, shared with anything else here that uses "
                f"GitHub.{when}\n\nThis doesn't affect updating your system.")
    if status:
        return (f"GitHub answered with an error (HTTP {status}) when asked for the "
                "latest OneUp version.")
    return "Couldn't reach GitHub to check for a newer OneUp."


def _check_app_update(win, manual: bool = False):
    # manual=True (the About dialog's button) reports the result either way;
    # the automatic startup check stays silent unless a newer release exists.
    win._manual_update_check = manual
    win._nam = QNetworkAccessManager(win)
    req = QNetworkRequest(QUrl(f"https://api.github.com/repos/{REPO_SLUG}/releases/latest"))
    req.setRawHeader(b"Accept", b"application/vnd.github+json")
    win._nam.finished.connect(partial(_on_app_update_reply, win))
    win._nam.get(req)


def _on_app_update_reply(win, reply: QNetworkReply):
    manual = getattr(win, "_manual_update_check", False)
    try:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            if manual:
                QMessageBox.warning(win, "Check for updates",
                                    _update_check_error(reply))
            return
        data = json.loads(bytes(reply.readAll()).decode(errors="replace"))
        tag = str(data.get("tag_name", "")).lstrip("vV")
        if tag and _version_tuple(tag) > _version_tuple(APP_VERSION):
            win._latest_tag = tag
            win.appupdate_label.setText(
                f"A newer OneUp ({tag}) is available — you have {APP_VERSION}.")
            win.appupdate_banner.setVisible(True)
            if manual:
                QMessageBox.information(win, "Check for updates",
                                        f"A newer OneUp ({tag}) is available — "
                                        f"you have {APP_VERSION}.")
        elif manual:
            QMessageBox.information(win, "Check for updates",
                                    f"You're on the latest version ({APP_VERSION}).")
    except (ValueError, KeyError, AttributeError, TypeError):
        # ValueError/KeyError: bad JSON / missing key; AttributeError/TypeError:
        # a non-object JSON body (list, string, null) has no .get(). A flaky
        # update check must never throw out of this network slot.
        if manual:
            QMessageBox.warning(win, "Check for updates",
                                "Couldn't read GitHub's reply while checking for updates.")
    finally:
        reply.deleteLater()


def _open_release(win):
    QDesktopServices.openUrl(QUrl(f"https://github.com/{REPO_SLUG}/releases/latest"))


