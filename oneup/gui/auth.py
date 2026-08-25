"""The "don't ask for my password" setting.

Reading, enabling and disabling the opt-in passwordless authorisation
(ONEUP-0023), and the coupling that keeps an unattended weekly update from
outliving the rule it needs (ONEUP-0099). The window never runs as root and
never calls sudo: every one of these routes through the engine
(`docs/standards/security.md` §1.4).
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QMessageBox

from . import autostart, paths


def _refresh_auth_label(win):
    on = win.auth_btn.isChecked()
    win.auth_btn.setText("Passwordless: on" if on else "Passwordless: off")


def _set_auth_checked(win, on: bool):
    """Reflect the real state on the toggle WITHOUT re-triggering grant/revoke."""
    win.auth_btn.blockSignals(True)
    win.auth_btn.setChecked(on)
    win.auth_btn.blockSignals(False)
    _refresh_auth_label(win)


def _query_auth_status(win):
    """Probe the engine for whether the drop-in is active and set the toggle to
    match — so it always shows the truth, not a saved preference (which could
    drift if the rule were removed outside OneUp). Output is tiny, so it's read
    once on finish (no incremental slot that could fire after teardown)."""
    if not paths.ENGINE.exists():
        return
    p = getattr(win, "_authstat_proc", None)
    if p is not None and p.state() != QProcess.NotRunning:
        return
    paths.STATE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    p = QProcess(win)
    p.setProcessChannelMode(QProcess.MergedChannels)
    p.finished.connect(lambda _c, _s, pr=p: _on_auth_status_finished(win, pr))
    win._authstat_proc = p
    p.start("bash", [str(paths.ENGINE), "--auth-status",
                     f"--log={paths.STATE_LOG_DIR / f'{stamp}.auth.log'}"])


def _on_auth_status_finished(win, proc: QProcess):
    out = bytes(proc.readAllStandardOutput()).decode(errors="replace")
    is_on = "@@AUTH@@|on" in out
    _set_auth_checked(win, is_on)
    # ONEUP-0099: an enabled weekly update must not outlive the rule it needs, and the
    # reflect above cannot do it — it runs under blockSignals precisely so it can't
    # fire grant/revoke, so on_auth_toggled's coupling arm never sees this route.
    #
    # Keyed on an EXPLICIT off marker, not on a missing "on". Every way the probe can
    # fail to speak — a crashed engine, a killed QProcess, truncated output — reads as
    # "not on", and deleting the user's weekly timer because a subprocess didn't start
    # is destructive where the toggle reflect above is merely cosmetic and win-
    # correcting. Not while an enable is in flight either: _autoupdate_enabled() shells
    # out to systemctl and so reports the machine, not the toggle, so a timer enabled
    # outside OneUp would answer the user's "on" click with "we switched it off".
    if "@@AUTH@@|off" in out and not win._pending_autoupdate:
        _stand_down_autoupdate(win, "OneUp's passwordless rule is no longer active.\n\n")
    # Re-enable the auto-update toggle if a pending enable had disabled it.
    win.autoupdate_btn.setEnabled(True)
    if win._pending_autoupdate:
        win._pending_autoupdate = False        # consume unconditionally
        if is_on:
            enabled = autostart._install_user_timer(win,
                "oneup-update", "OneUp weekly automatic update", "--update")
            autostart._set_autoupdate_checked(win, enabled)
            if not enabled:
                QMessageBox.warning(
                    win, "Could not enable automatic updates",
                    "The weekly update timer could not be enabled.")
        else:
            # Passwordless came back off (popup cancelled / visudo rejected / failed).
            # The grant's @@HINT@@ was already surfaced in _on_auth_finished.
            autostart._set_autoupdate_checked(win, False)


def _confirm_passwordless(win, lead: str = "") -> bool:
    """The ONEUP-0023 passwordless consent dialog. `lead` prepends a caller-
    specific sentence (e.g. auto-update's reason) before the shared caveat, so
    both call sites present the SAME security warning — never a shortened rewrite."""
    box = QMessageBox(win)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("Skip the password prompt for updates?")
    box.setText("Let OneUp run updates without asking for your password?")
    box.setInformativeText(
        lead +
        "OneUp will add a system rule so its update commands — zypper, "
        "Flatpak, firmware and snapshots — can run without a password.\n\n"
        "Your password is never stored. The system only remembers the "
        "decision, and only for these specific commands.\n\n"
        "Because updates run as administrator, this is effectively "
        "passwordless administrator access on this machine — enable it "
        "only on a computer you trust and control. You can switch it off "
        "at any time to revoke it instantly.")
    box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
    box.button(QMessageBox.Ok).setText("Enable")
    box.setDefaultButton(QMessageBox.Cancel)
    # Centre over the main window once laid out (mirrors show_about).
    QTimer.singleShot(0, lambda: win._center_child(box))
    return box.exec() == QMessageBox.Ok


def _stand_down_autoupdate(win, lead: str = ""):
    """Remove the weekly update timer, uncheck it, and say why — the three steps both
    routes that learn passwordless is off must take (ONEUP-0099). `lead` prepends a
    route-specific opening sentence; the shared one explains the coupling, so neither
    route rewrites the other's wording (mirrors _confirm_passwordless).

    The `_pending_autoupdate` test deliberately does NOT live here. The click path
    stands the timer down regardless of the latch and clears it afterwards, so moving
    the check inside would let a revoke racing an enable leave an enabled weekly timer
    behind — the exact coupling this method exists to guarantee."""
    if not autostart._autoupdate_enabled():
        return
    autostart._remove_user_timer("oneup-update")
    autostart._set_autoupdate_checked(win, False)
    QMessageBox.information(
        win, "Automatic updates turned off", lead +
        "Automatic weekly updates were switched off because they need "
        "the passwordless setting to run unattended.")


def on_auth_toggled(win, on: bool):
    if not paths.ENGINE.exists():
        _set_auth_checked(win, False)
        return
    if on:
        if not _confirm_passwordless(win):
            _set_auth_checked(win, False)   # user backed out
            return
        _run_auth(win, "--grant-auth", "Setting up… (approve the password popup)")
    else:
        # Coupling rule 3: a schedule can't outlive the passwordless rule it needs.
        # Hooked to the revoke ACTION (not the toggle signal), so the programmatic
        # blockSignals reflects can't trip it. Removal is a local systemd-user op,
        # independent of the revoke process's own outcome.
        _stand_down_autoupdate(win)
        win._pending_autoupdate = False    # a revoke mid-enable can't leave a stale latch
        _run_auth(win, "--revoke-auth", "Revoking authorization…")


def _run_auth(win, action: str, status_text: str):
    p = getattr(win, "_authchg_proc", None)
    if p is not None and p.state() != QProcess.NotRunning:
        return
    win.auth_btn.setEnabled(False)
    win.status.setText(status_text)
    win._settings_status(status_text)
    paths.STATE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    p = QProcess(win)
    p.setProcessChannelMode(QProcess.MergedChannels)
    p.finished.connect(lambda _c, _s, pr=p: _on_auth_finished(win, pr))
    win._authchg_proc = p
    log = paths.STATE_LOG_DIR / f"{stamp}.auth.log"
    p.start("bash", [str(paths.ENGINE), action, f"--log={log}"])


def _on_auth_finished(win, proc: QProcess):
    out = bytes(proc.readAllStandardOutput()).decode(errors="replace")
    win.auth_btn.setEnabled(True)
    win.status.setText("Ready.")
    win._settings_status("")
    for line in out.splitlines():
        if line.startswith("@@HINT@@|"):
            QMessageBox.warning(win, "Couldn't change the setting",
                                line.split("|", 1)[1])
    # Re-probe the real state rather than trusting the toggle: a cancelled
    # password prompt or a failure must leave the switch showing the truth.
    _query_auth_status(win)


