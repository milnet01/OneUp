"""The "don't ask for my password" setting.

Reading, enabling and disabling the opt-in passwordless authorisation
(ONEUP-0023), and the coupling that keeps an unattended weekly update from
outliving the rule it needs (ONEUP-0099). The window never runs as root and
never runs sudo as a command: every one of these routes through the engine
(`docs/standards/security.md` §1.1, §1.4).

On a packaged install the engine reaches root through OneUp's system service, and
the setting is this computer's software-update permission instead (ONEUP-0249 §4.10).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime

import shiboken6
from PySide6.QtCore import QCoreApplication, QProcess, QTimer
from PySide6.QtWidgets import QMessageBox

from ..engine import route
from . import autostart, markers, paths

# Where a Passwordless grant put its guard: the two paths the engine's `--revoke-auth`
# sweeps (`actions.revoke_auth`). Module constants so a test can point them at scratch.
OLD_GUARDS = ("/usr/libexec/oneup-download-guard", "/usr/lib/oneup-download-guard")


def service_route() -> bool:
    """Would the engine take OneUp's system service? Asked with the engine's own
    environment, so the AppImage's `ONEUP_BACKEND=sudo` keeps its switch (§4.10)."""
    return route.engine_route(paths.engine_environ()) == route.SERVICE


def _refresh_auth_label(win):
    on = win.auth_btn.isChecked()
    win.auth_btn.setText(QCoreApplication.translate("auth", "Passwordless: on") if on
                         else QCoreApplication.translate("auth", "Passwordless: off"))


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
    if not paths.engine_available():
        return
    p = getattr(win, "_authstat_proc", None)
    if p is not None and p.state() != QProcess.NotRunning:
        # ONEUP-0178: the caller wants an answer from after its own change, and the
        # probe in flight started before it. Ask again when that one finishes.
        win._authstat_rerun = True
        return
    if not paths.log_dir_ready(quiet=True):
        return
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    p = QProcess(win)
    p.setProcessChannelMode(QProcess.MergedChannels)
    p.finished.connect(lambda _c, _s, pr=p: _on_auth_status_finished(win, pr))
    win._authstat_proc = p
    argv = paths.engine_argv(
        "--auth-status", f"--log={paths.STATE_LOG_DIR / f'{stamp}.auth.log'}")
    p.start(argv[0], argv[1:])


def _on_auth_status_finished(win, proc: QProcess):
    # The probe can finish after Qt destroyed the window or the process (quitting
    # mid-probe, or teardown at exit); reading either then raises (ONEUP-0204).
    if not (shiboken6.isValid(win) and shiboken6.isValid(proc)):
        return
    if getattr(win, "_authstat_rerun", False):
        # ONEUP-0178: this probe started before a change that asked for a fresh one,
        # so its answer is stale. Acting on it would settle the enable latch with the
        # pre-grant state and revert the toggle. Discard it and probe again.
        win._authstat_rerun = False
        _query_auth_status(win)
        return
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
        _stand_down_autoupdate(win, QCoreApplication.translate(
            "auth", "This computer no longer allows updates without a password.\n\n")
            if win._service_route else QCoreApplication.translate(
            "auth", "OneUp's passwordless rule is no longer active.\n\n"))
    # Re-enable the auto-update toggle if a pending enable had disabled it.
    win.autoupdate_btn.setEnabled(True)
    if win._pending_autoupdate:
        win._pending_autoupdate = False        # consume unconditionally
        if is_on:
            enabled = autostart._install_user_timer(
                win, "oneup-update", *autostart.TIMERS["oneup-update"])
            autostart._set_autoupdate_checked(win, enabled)
            if not enabled:
                QMessageBox.warning(
                    win, QCoreApplication.translate("auth", "Could not enable automatic updates"),
                    QCoreApplication.translate(
                        "auth",
                        "The weekly update timer could not be enabled."))
        else:
            # Passwordless came back off (popup cancelled / visudo rejected / failed).
            # The grant's @@HINT@@ was already surfaced in _on_auth_finished. On the
            # service route there was no grant, so nothing has said why yet.
            autostart._set_autoupdate_checked(win, False)
            if win._service_route:
                QMessageBox.information(
                    win, QCoreApplication.translate(
                        "auth", "Automatic updates can't be turned on"),
                    QCoreApplication.translate(
                        "auth",
                        "This computer asks for a password before it installs "
                        "updates, and nobody is there to type it during an automatic "
                        "update. Ask whoever looks after this computer to allow "
                        "updates without a password, then try again."))


def _confirm_passwordless(win, lead: str = "") -> bool:
    """The ONEUP-0023 passwordless consent dialog. `lead` prepends a caller-
    specific sentence (e.g. auto-update's reason) before the shared caveat, so
    both call sites present the SAME security warning — never a shortened rewrite."""
    box = QMessageBox(win)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(QCoreApplication.translate(
        "auth",
        "Skip the password prompt for updates?"))
    box.setText(QCoreApplication.translate(
        "auth",
        "Let OneUp run updates without asking for your password?"))
    box.setInformativeText(QCoreApplication.translate(
        "auth",
        "{lead}OneUp will add a system rule so its update commands — zypper, "
        "Flatpak, firmware and snapshots — can run without a password.\n\n"
        "Your password is never stored. The system only remembers the "
        "decision, and only for these specific commands.\n\n"
        "Because updates run as administrator, this is effectively "
        "passwordless administrator access on this machine — enable it "
        "only on a computer you trust and control. You can switch it off "
        "at any time to revoke it instantly.").format(lead=lead))
    box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
    box.button(QMessageBox.Ok).setText(QCoreApplication.translate("auth", "Enable"))
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
    if win._service_route:
        text = QCoreApplication.translate(
            "auth",
            "{lead}Automatic weekly updates were switched off because they need this "
            "computer to allow updates without a password.").format(lead=lead)
    else:
        text = QCoreApplication.translate(
            "auth",
            "{lead}Automatic weekly updates were switched off because they need "
            "the passwordless setting to run unattended.").format(lead=lead)
    QMessageBox.information(
        win, QCoreApplication.translate("auth", "Automatic updates turned off"), text)


def on_auth_toggled(win, on: bool):
    if not paths.engine_available():
        _set_auth_checked(win, False)
        return
    if on:
        if not _confirm_passwordless(win):
            _set_auth_checked(win, False)   # user backed out
            return
        _run_auth(win, "--grant-auth", QCoreApplication.translate(
            "auth", "Setting up… (approve the password popup)"))
    else:
        # Coupling rule 3: a schedule can't outlive the passwordless rule it needs.
        # Hooked to the revoke ACTION (not the toggle signal), so the programmatic
        # blockSignals reflects can't trip it. Removal is a local systemd-user op,
        # independent of the revoke process's own outcome.
        _stand_down_autoupdate(win)
        win._pending_autoupdate = False    # a revoke mid-enable can't leave a stale latch
        _run_auth(win, "--revoke-auth",
                  QCoreApplication.translate("auth", "Revoking authorization…"))


def _run_auth(win, action: str, status_text: str,
              env: dict[str, str] | None = None) -> QProcess | None:
    """Start the engine on `action`; return its process, or None if none started."""
    p = getattr(win, "_authchg_proc", None)
    if p is not None and p.state() != QProcess.NotRunning:
        return None
    if not paths.log_dir_ready(win):
        # Nothing changed, so put both toggles back as they were (ONEUP-0184). On the
        # service route the switch shows polkit's answer, which a revoke never moved.
        if not win._service_route:
            _set_auth_checked(win, action == "--revoke-auth")
        if win._pending_autoupdate:
            win._pending_autoupdate = False
            win.autoupdate_btn.setEnabled(True)
            autostart._set_autoupdate_checked(win, False)
        return None
    win.auth_btn.setEnabled(False)
    win.status.setText(status_text)
    win._settings_status(status_text)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    p = QProcess(win)
    p.setProcessChannelMode(QProcess.MergedChannels)
    p.finished.connect(lambda _c, _s, pr=p: _on_auth_finished(win, pr))
    p.errorOccurred.connect(lambda err, pr=p: err == QProcess.FailedToStart
                            and _on_auth_not_started(win, pr))
    win._authchg_proc = p
    log = paths.STATE_LOG_DIR / f"{stamp}.auth.log"
    argv = paths.engine_argv(action, f"--log={log}", env=env)
    p.start(argv[0], argv[1:])
    return p


def _old_dropin_present() -> bool:
    """Is a Passwordless rule from before the service still here? A guard at either
    path, or sudo saying it would run zypper without a password, which also finds a
    rule older than the guard. `sudo -n -l` only lists: it never prompts and never
    runs anything as root (`docs/standards/security.md` §1.1)."""
    if any(os.path.exists(path) for path in OLD_GUARDS):
        return True
    zypper = shutil.which("zypper")
    if not zypper:
        return False
    try:
        return subprocess.run(  # noqa: S603 — fixed argv, no shell.
            ["sudo", "-n", "-l", zypper], stdout=subprocess.DEVNULL,  # noqa: S607
            stderr=subprocess.DEVNULL, timeout=10, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def offer_old_dropin_removal(win):
    """On a service install, offer once to remove the old Passwordless rule (§4.10).

    Once means once: the answer is remembered whichever it was. Removing runs the
    sudo route's `--revoke-auth`, which asks for the administrator password once."""
    if not win._service_route or win.settings.value("old_dropin_offered", False, type=bool):
        return
    if not _old_dropin_present():
        return
    win.settings.setValue("old_dropin_offered", True)
    box = QMessageBox(win)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(QCoreApplication.translate(
        "auth", "Remove OneUp's old password setting?"))
    box.setText(QCoreApplication.translate(
        "auth",
        "OneUp now follows this computer's software-update permission, the same one "
        "Discover uses. The Passwordless rule from an earlier OneUp is still on this "
        "computer, and OneUp no longer needs it."))
    box.setInformativeText(QCoreApplication.translate(
        "auth",
        "Removing it asks for the administrator password once. If you keep it, "
        "OneUp will not ask again."))
    box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
    box.button(QMessageBox.Ok).setText(QCoreApplication.translate("auth", "Remove"))
    box.button(QMessageBox.Cancel).setText(QCoreApplication.translate("auth", "Keep"))
    box.setDefaultButton(QMessageBox.Ok)
    QTimer.singleShot(0, lambda: win._center_child(box))
    if box.exec() == QMessageBox.Ok:
        # ONEUP-0280: remember which run is the removal, so its finish can say whether
        # the rule went. The service route has no switch whose flip would say it.
        win._old_dropin_proc = _run_auth(win, "--revoke-auth", QCoreApplication.translate(
            "auth", "Removing the old password setting… (approve the password popup)"),
            env={"ONEUP_BACKEND": route.SUDO})


def _on_auth_not_started(win, proc: QProcess):
    """The engine could not start, so `finished` never comes. Give the switch back and
    say so, rather than leave it greyed out (ONEUP-0183)."""
    if not (shiboken6.isValid(win) and shiboken6.isValid(proc)):
        return
    win.auth_btn.setEnabled(True)
    win.status.setText(QCoreApplication.translate("auth", "Ready."))
    win._settings_status("")
    QMessageBox.warning(win, QCoreApplication.translate("auth", "Couldn't change the setting"),
                        QCoreApplication.translate(
                            "auth",
                            "Nothing was changed — OneUp's engine could not be started."))
    _query_auth_status(win)


def _on_auth_finished(win, proc: QProcess):
    if not (shiboken6.isValid(win) and shiboken6.isValid(proc)):   # ONEUP-0204
        return
    out = bytes(proc.readAllStandardOutput()).decode(errors="replace")
    win.auth_btn.setEnabled(True)
    win.status.setText(QCoreApplication.translate("auth", "Ready."))
    win._settings_status("")
    hinted = False
    for line in out.splitlines():
        if line.startswith("@@HINT@@|"):
            hinted = True
            QMessageBox.warning(win, QCoreApplication.translate(
                "auth",
                "Couldn't change the setting"),
                                markers.render_hint(line.split("|")[1:]))
    if proc is getattr(win, "_old_dropin_proc", None):
        # ONEUP-0280: say whether the old rule went, asking the machine rather than the
        # exit code. A failure the engine already explained is not said twice.
        win._old_dropin_proc = None
        if not _old_dropin_present():
            QMessageBox.information(
                win, QCoreApplication.translate("auth", "Old password setting removed"),
                QCoreApplication.translate(
                    "auth", "The Passwordless rule from an earlier OneUp is gone."))
        elif not hinted:
            QMessageBox.warning(
                win, QCoreApplication.translate("auth", "Couldn't change the setting"),
                QCoreApplication.translate(
                    "auth",
                    "The Passwordless rule from an earlier OneUp is still on this "
                    "computer. Nothing was removed."))
    # Re-probe the real state rather than trusting the toggle: a cancelled
    # password prompt or a failure must leave the switch showing the truth.
    _query_auth_status(win)


