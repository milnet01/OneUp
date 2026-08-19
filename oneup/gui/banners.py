"""Telling the user what went wrong, and offering the one thing that fixes it.

The reboot, info and warning banners, and the remedy actions their buttons run.
`_split_session_critical` and `restart_services` stay in one module because a
guard and the command it protects must not be separated
(`docs/standards/security.md` §9.4, spec INV-11); the same is true of
`_service_units` and both of its callers.
"""
from __future__ import annotations

import os
import re

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
)

from . import repos, rollback, run

# --- services that must never be restarted from the window -------------------
# Restarting one of these ends the user's graphical session, kills this window, or
# breaks the authorisation agent carrying out the restart. `zypper ps -sss` reports
# whatever holds a replaced library, so after a glibc, systemd, Qt or dbus update these
# are exactly what it names — they are the longest-running processes on the box and they
# link everything. `Updater.restart_services` restarts none of them on any path
# (ONEUP-0111); a reboot is the honest advice, and the window already has that button.
#
# NetworkManager and wickedd are deliberately absent: disruptive, recoverable, and a
# legitimate thing to restart without a reboot.
_SESSION_CRITICAL = frozenset({
    "display-manager", "sddm", "gdm", "gdm3", "lightdm", "xdm", "kdm", "lxdm", "greetd",
    "dbus", "dbus-broker", "systemd-logind", "polkit", "polkitd",
})
# `user@1000` and friends — the user's own systemd session, which contains this window.
_USER_MANAGER_RE = re.compile(r"user@\d+")

def _split_session_critical(svcs: list[str]) -> tuple[list[str], list[str]]:
    """Split validated unit names into (safe to restart, would end the session).

    The display manager is RESOLVED rather than guessed: `/etc/systemd/system/
    display-manager.service` is a symlink to whichever one the distro installed, so its
    target's name is added at call time. The literal names above are the fallback for a
    system without that symlink. A hardcoded list on its own would be the same shape of
    defect ONEUP-0110 fixed — a guard written against an assumed name — which is why the
    symlink is the mechanism and the list is the backstop.
    """
    critical = set(_SESSION_CRITICAL)
    try:
        target = os.path.realpath("/etc/systemd/system/display-manager.service")
        if target.endswith(".service"):
            critical.add(os.path.basename(target)[:-len(".service")])
    except OSError:
        pass                      # no symlink, or an unreadable /etc — the set stands
    safe, risky = [], []
    for s in svcs:
        base = s[:-len(".service")] if s.endswith(".service") else s
        (risky if base in critical or _USER_MANAGER_RE.fullmatch(base) else safe).append(s)
    return safe, risky


def _make_banner(win, frame_obj: str, btn_obj: str, btn_text: str, slot,
                 name: str = ""):
    fr = QFrame()
    fr.setObjectName(frame_obj)
    if name:
        fr.setAccessibleName(name)
    lay = QHBoxLayout(fr)
    lay.setContentsMargins(14, 10, 12, 10)
    lbl = QLabel("")
    lbl.setObjectName("BannerText")
    lbl.setWordWrap(True)
    if name:
        lbl.setAccessibleName(name)
    btn = QPushButton(btn_text)
    btn.setObjectName(btn_obj)
    btn.setCursor(Qt.PointingHandCursor)
    btn.clicked.connect(slot)
    lay.addWidget(lbl, 1)
    lay.addWidget(btn, 0)
    fr.setVisible(False)
    return fr, lbl, btn


def _extract_command(hint: str) -> str:
    """Pull a runnable command out of a failure hint of the form
    '… run: <command>, then …'. Returns '' when the hint carries no command,
    so the Copy button only appears when there's actually something to copy."""
    marker = "run: "
    i = hint.find(marker)
    if i == -1:
        return ""
    rest = hint[i + len(marker):]
    cut = len(rest)
    for sep in (", then", ", or", ";"):   # the command ends at the first clause break
        j = rest.find(sep)
        if j != -1:
            cut = min(cut, j)
    return rest[:cut].strip().rstrip(".").strip()


def _show_warning(win, text: str):
    """Show the warning banner with `text`, exposing a Copy button when the
    text contains a runnable command."""
    win.warn_label.setText("⚠  " + text)
    cmd = _extract_command(text)
    win._hint_command = cmd
    win.warn_copy_btn.setVisible(bool(cmd))
    if cmd:
        win.warn_copy_btn.setText("Copy command")
    win.warn_banner.setVisible(True)
    # A banner that merely appears is silent to a screen reader. Announced last
    # in on_finished's ordering, so the warning — the more urgent message —
    # is the one left standing rather than the summary.
    win._announce(f"Warning: {text}", win.warn_label)


def _copy_hint_command(win):
    if not win._hint_command:
        return
    QApplication.clipboard().setText(win._hint_command)
    win.warn_copy_btn.setText("Copied ✓")


def _warn_action(win):
    """The warning banner's button adapts to the warning: offer to skip a broken
    source, offer the one-click signing-key fix, open the repo manager for a
    duplicate, else show the log. When both a skip and a key-import remedy are
    armed (an expired key), skip is primary here and import stays reachable via
    warn_btn2 (see on_finished)."""
    if win._remedy_skips:
        _skip_repo_and_retry(win)
    elif win._remedy_keys:
        _fix_keys_and_retry(win)
    elif win._warn_repo_dup:
        win.open_repos()
    elif win._warn_snapshots:
        rollback._thin_snapshots(win)
    else:
        win._show_log()


def _confirm_key_import(win) -> bool:
    """Warn about the trust decision before importing a repository signing key,
    and return whether the user approved."""
    box = QMessageBox(win)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("Import the repository's signing key?")
    box.setText("Import the new signing key and retry the update?")
    box.setInformativeText(
        "A repository's signing key has changed or expired, which is why the "
        "update was refused.\n\n"
        "To continue, OneUp will import the repository's new key and run the "
        "update again. Importing a key means trusting it — only do this for "
        "repositories you set up and trust. A key you don't recognise could let "
        "unverified software be installed on your computer.")
    box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
    box.button(QMessageBox.Ok).setText("Import && retry")
    box.setDefaultButton(QMessageBox.Cancel)
    # Centre over the main window once laid out (mirrors show_about).
    QTimer.singleShot(0, lambda: win._center_child(box))
    return box.exec() == QMessageBox.Ok


def _fix_keys_and_retry(win):
    """Re-run the failed update with signing-key import enabled, after the user
    confirms the trust decision."""
    if not _confirm_key_import(win):
        return
    steps = list(win._failed_steps) or ["system"]
    run._launch(win, steps, check=False, import_keys=True)


def _repo_display_name(alias: str) -> str:
    """Resolve a repo alias to its human-readable name for the banner text;
    fall back to the raw alias if it can't be found (repo removed, zypper
    unavailable, …)."""
    for r in repos.read_repos():
        if r.get("alias") == alias:
            return r.get("name") or alias
    return alias


def _skip_repo_and_retry(win):
    """Re-run the failed steps with the flagged source(s) set aside for this run
    only — the engine re-enables them on exit (--skip-repo in update_system.sh)."""
    aliases = list(win._remedy_skips)
    if not aliases:
        return
    steps = list(win._failed_steps) or ["system"]
    run._launch(win, steps, check=False, skip_repos=aliases)


def _service_units(win) -> list[str]:
    r"""The `@@SERVICES@@` payload, filtered to names safe to hand to `systemctl`.

    Shared by the banner and the button deliberately. ONEUP-0110 was invisible for
    months because the banner was drawn from the RAW marker while the handler acted
    on a filtered copy, so the two could disagree with nothing on screen to show it.

    A spliced token (a leading-dash option, a path) must never reach a root
    `systemctl` as an argument — the same guard shape as the snapshot id in
    rollback(). The name is matched WITHOUT requiring a ".service" suffix, because
    `zypper ps -sss` does not print one: libzypp captures the unit name from the
    cgroup path with (.*)\.service, so what reaches us is bare — "sshd", "dbus",
    "user@1000". Requiring the suffix emptied this list on every real run and the
    button silently did nothing (ONEUP-0110). `systemctl` resolves a bare name to
    the .service unit itself, which is why the engine's own advice works.
    """
    return [s for s in win._services.split()
            if not s.startswith("-")
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:@._-]*", s)]


def _confirm_reboot(win, title: str, body: str):
    """Ask, and restart the machine on yes — the one place the window reboots."""
    if QMessageBox.question(win, title, body) == QMessageBox.Yes:
        QProcess.startDetached("systemctl", ["reboot"])


def restart_now(win):
    _confirm_reboot(win, "Restart now?",
                         "Save your work first. Restart the computer now?")


def restart_services(win):
    svcs = _service_units(win)
    if not svcs:
        return
    # Never restart a service that would end the session (ONEUP-0111).
    safe, critical = _split_session_critical(svcs)
    if not safe:
        # ONEUP-0115: where the advice is a reboot, OFFER the reboot. This used to be
        # an information dialog naming units this button refuses to touch, whose only
        # control was OK — a recommendation the user then had to go and act on
        # somewhere else. on_finished now shows the reboot banner instead of this one
        # in that state, so reaching here means something went round the banner.
        _confirm_reboot(win,
            "Restart the computer?",
            "Everything that needs restarting is part of what runs your desktop "
            "session, so restarting it here would break or end that session:\n\n"
            + ", ".join(critical)
            + "\n\nRestarting the computer is the clean way to pick up the new "
              "libraries. Save your work first. Restart now?")
        return
    body = "These will be restarted now:\n\n" + ", ".join(safe)
    if critical:
        body += ("\n\nThese need a restart of the computer instead, because "
                 "restarting them here would break or end your desktop session:"
                 "\n\n" + ", ".join(critical)
                 + "\n\nThe Restart now button above will do that when you are "
                   "ready.")
    if QMessageBox.question(win, "Restart services?", body) == QMessageBox.Yes:
        QProcess.startDetached("pkexec", ["systemctl", "restart", *safe])
        # Nothing is left for this button to do. Anything still needing a reboot is
        # carried by the reboot banner, which on_finished has already shown.
        win.services_banner.setVisible(False)


