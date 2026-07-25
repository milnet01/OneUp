#!/usr/bin/env python3
"""Headless smoke test for updater.py (the PySide6 GUI).

updater.py drives real update runs but has no automated coverage — a typo in
handle_marker or on_finished only shows up when a user runs it. This test builds
the window under Qt's "offscreen" platform (no display needed), feeds it the same
@@MARKER@@ lines the engine prints, and asserts the window neither throws nor
lands in the wrong state (badges, banners, summary).

It exits 0 on success, 1 on a failed assertion, and 77 (skip) if PySide6 isn't
installed — so a machine without Qt reports "skipped", not "failed", matching the
engine's own skip-cleanly-for-absent-tools convention.

Run directly, or via tests/run-tests.sh / local-CI.sh.
"""
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Redirect config/state into a throwaway dir *before* QApplication reads them, so
# on_finished's save_last_run() can't write to the real ~/.config / ~/.local/state.
_SANDBOX = tempfile.mkdtemp(prefix="oneup-guitest-")
os.environ["HOME"] = _SANDBOX
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SANDBOX, "config")
os.environ["XDG_STATE_HOME"] = os.path.join(_SANDBOX, "state")

# A mock notify-send on PATH: records its calls to a file so the test can assert a
# finished run notifies, without firing a real desktop notification on the machine.
_BIN = os.path.join(_SANDBOX, "bin")
os.makedirs(_BIN, exist_ok=True)
_NOTIFY_LOG = os.path.join(_SANDBOX, "notify.log")
_notify_mock = os.path.join(_BIN, "notify-send")
with open(_notify_mock, "w") as _f:
    _f.write(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> {_NOTIFY_LOG}\n')
os.chmod(_notify_mock, 0o755)
os.environ["PATH"] = _BIN + os.pathsep + os.environ.get("PATH", "")

try:
    from PySide6.QtCore import QProcess, Qt, QTimer
    from PySide6.QtGui import QAccessible, QCloseEvent, QFontInfo
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QMessageBox,
        QPushButton,
        QWidget,
    )
except ImportError as exc:  # PySide6 absent — skip, don't fail the suite.
    print(f"  SKIP - PySide6 not installed ({exc})")
    sys.exit(77)

REPO = Path(__file__).resolve().parent.parent


def _load_updater():
    spec = importlib.util.spec_from_file_location("updater", REPO / "updater.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PASS = 0
FAIL = 0


def check(name: str, cond: bool):
    global PASS, FAIL
    if cond:
        print(f"  ok   - {name}")
        PASS += 1
    else:
        print(f"  FAIL - {name}")
        FAIL += 1


def _wait_for_notify(timeout: float = 2.0) -> bool:
    """Poll for the mock notify-send to record a call (Popen is asynchronous)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(_NOTIFY_LOG) and os.path.getsize(_NOTIFY_LOG) > 0:
            return True
        time.sleep(0.02)
    return False


def main() -> int:
    updater = _load_updater()
    app = QApplication.instance() or QApplication([])
    app  # noqa: B018 — keep a reference so it isn't GC'd mid-test.

    # --- 1. A malformed / spliced marker never throws out of the read slot ------
    w = updater.Updater()
    for bad in ("@@STEP_BEGIN@@|system",          # too few fields
                "@@STEP_BEGIN@@|system|x|3|Label",  # non-numeric index
                "@@ -1,4 +1,4 @@ a diff hunk",       # looks like a marker, isn't
                "@@NOPE@@ no pipe at all",
                "an ordinary log line"):
        try:
            w.handle_line(bad)
            check(f"malformed line handled: {bad[:22]!r}", True)
        except Exception as exc:  # noqa: BLE001 — any throw is the failure.
            check(f"malformed line handled: {bad[:22]!r} ({exc})", False)

    # --- 2. A real run's markers land the right per-row badges + state ----------
    w = updater.Updater()
    for line in ("@@STEP_BEGIN@@|system|1|3|Updating system packages",
                 "@@STEP_END@@|system|ok|3 packages updated",
                 "@@TIMING@@|system|42",
                 "@@STEP_END@@|flatpak|ok|up to date",
                 "@@STEP_END@@|firmware|skip|fwupd not installed",
                 "@@STEP_END@@|orphans|fail|autoremove failed",
                 "@@STEP_END@@|cache|ok",
                 "@@FREED@@|cache|1.0G",
                 "@@TIMING@@|cache|3",
                 "@@SNAPSHOT@@|42",
                 "@@INSTALLED@@|3|yes|no",
                 "@@REBOOT@@|yes",
                 "@@DISK@@|warn|/|512 MiB"):
        w.handle_line(line)

    check("system row badge shows outcome + timing",
          w.rows["system"].badge.text() == "3 installed  ·  42s")
    check("_format_duration formats seconds", updater.Updater._format_duration(42) == "42s")
    check("_format_duration formats minutes", updater.Updater._format_duration(65) == "1m 5s")
    check("_format_duration handles sub-second", updater.Updater._format_duration(0) == "<1s")
    check("flatpak row badge = 'Up to date'", w.rows["flatpak"].badge.text() == "Up to date")
    check("firmware skip badge = 'Not installed'", w.rows["firmware"].badge.text() == "Not installed")
    check("orphans fail badge = 'Failed'", w.rows["orphans"].badge.text() == "Failed")
    check("cache FREED badge shows reclaimed size + timing, overriding 'Done'",
          w.rows["cache"].badge.text() == "Reclaimed 1.0G  ·  3s")
    check("failed step recorded", "orphans" in w._failed_steps)
    check("snapshot captured", w._snapshot == "42")
    check("installed count captured", w._installed_count == "3")
    check("sys_changed flag set", w._sys_changed is True)
    check("reboot flag set", w._reboot is True)
    # isVisibleTo(window): the banner's own visibility, independent of the never-shown window.
    check("disk warning banner shown", w.warn_banner.isVisibleTo(w))

    # --- @@PROGRESS@@: a long download must never look like a hang (ONEUP-0040) ---
    wP = updater.Updater()
    wP.handle_line("@@STEP_BEGIN@@|system|1|5|Updating system packages")
    caption = wP.bar.format()
    # zypper's preload phase gives no total, so the GUI must show a running tally
    # rather than inventing a denominator it doesn't have.
    wP.handle_line("@@PROGRESS@@|system|34|0|download")
    check("unknown total shows a running tally, not a fake ratio",
          "34 so far" in wP.status.text() and "of 0" not in wP.status.text())
    check("the bar keeps the step caption and adds the detail",
          caption in wP.bar.format() and "34 so far" in wP.bar.format())
    wP.handle_line("@@PROGRESS@@|system|12|141|download")
    check("a counted download reads as 'Downloading 12 of 141 packages'",
          wP.status.text() == "Downloading 12 of 141 packages…")
    check("the row badge tracks progress", wP.rows["system"].badge.text() == "12/141")
    wP.handle_line("@@PROGRESS@@|system|7|141|install")
    check("the install phase says Installing", wP.status.text() == "Installing 7 of 141 packages…")
    # One announcement per phase, not per package: 141 spoken lines would bury
    # everything else, but silence through the longest phase is what looked hung.
    check("a phase change is announced once", wP._last_announcement == "Installing packages.")
    wP._last_announcement = ""
    wP.handle_line("@@PROGRESS@@|system|8|141|install")
    check("further packages in the same phase are not re-announced",
          wP._last_announcement == "")
    # Same splice-safety contract as STEP_BEGIN: merged stdout/stderr can cut a marker.
    for bad in ("@@PROGRESS@@|system",
                "@@PROGRESS@@|system|x|141|download",
                "@@PROGRESS@@|system|12|y|download"):
        try:
            wP.handle_line(bad)
            check(f"malformed progress marker handled: {bad[-14:]!r}", True)
        except Exception as exc:  # noqa: BLE001 — any throw is the failure.
            check(f"malformed progress marker handled ({exc})", False)
    # A later step's caption must replace the previous one, not accumulate.
    wP.handle_line("@@STEP_BEGIN@@|cache|5|5|Cleaning package cache")
    check("a new step resets the progress caption",
          "141" not in wP.bar.format() and "Cleaning package cache" in wP.bar.format())

    # --- @@REFRESH@@ and the liveness line (ONEUP-0048) -------------------------
    # A run once sat 26 minutes on one repository whose server was delivering an 18 MB
    # index at 930 B/s, with nothing on screen the whole time: zypper reports that phase
    # as dots with no line ending, so there was never a complete line to draw and a
    # working run was indistinguishable from a frozen one.
    wL = updater.Updater()
    wL._run_active = True
    wL.handle_line("@@STEP_BEGIN@@|system|1|5|Updating system packages")
    wL.handle_line("@@REFRESH@@|6|9|games")
    check("the source being fetched is named, with its position",
          wL.status.text() == "Checking for updates from games (6 of 9 sources)…")
    check("the bar keeps the step caption and adds the source",
          "Updating system packages" in wL.bar.format() and "games" in wL.bar.format())
    check("the liveness line names what is being waited on",
          "Fetching games" in wL.activity.text())
    check("the liveness line is visible during a run", wL.activity.isVisibleTo(wL))
    # Bytes: the download phase is the only place in a run where a figure exists at all.
    wL.handle_line("@@PROGRESS@@|system|12|141|download|41943040|397410304")
    check("the download says how much of how much", "40 MB of 379 MB" in wL.activity.text())
    check("the byte total is remembered", wL._dl_total == 397410304)
    # A rate needs both movement and elapsed time to divide by.
    wL.handle_line("@@PROGRESS@@|system|24|141|download|83886080|397410304")
    wL._dl_at -= 10
    wL._tick_activity()
    check("a rate appears once bytes have moved", "/s" in wL.activity.text())
    # Going quiet is the signal that actually matters, and must be said in those terms.
    wL._activity_at = time.monotonic() - (updater.STALL_SECONDS + 5)
    wL._tick_activity()
    check("a stalled server is named as such", "may have stalled" in wL.activity.text())
    check("and the user is told stopping is safe", "safe" in wL.activity.text())
    check("the stall is announced once", "No response" in wL._last_announcement)
    wL._last_announcement = ""
    wL._tick_activity()
    check("a continuing stall is not re-announced every tick", wL._last_announcement == "")
    # Output arriving again means slow, not stalled — the wording has to go back.
    wL._activity_at = time.monotonic()
    wL._tick_activity()
    check("output arriving clears the stall wording",
          "may have stalled" not in wL.activity.text())
    # A new step is a new wait and a new download; neither figure may carry over.
    wL.handle_line("@@STEP_BEGIN@@|flatpak|2|5|Updating Flatpak apps")
    check("a new step drops the previous source", "games" not in wL.activity.text())
    check("a new step resets the byte counters", wL._dl_bytes == 0 and wL._dl_total == 0)
    # Same splice-safety contract as PROGRESS: merged stdout/stderr can cut a marker.
    for bad in ("@@REFRESH@@|6", "@@REFRESH@@|x|9|games", "@@REFRESH@@|6|y|games",
                "@@PROGRESS@@|system|1|2|download|notanumber"):
        try:
            wL.handle_line(bad)
            check(f"malformed liveness marker handled: {bad[-12:]!r}", True)
        except Exception as exc:  # noqa: BLE001 — any throw is the failure.
            check(f"malformed liveness marker handled ({exc})", False)
    wL.on_finished(0, None)
    check("the liveness line goes away when the run ends", not wL.activity.isVisibleTo(wL))

    # zypper's prefetch phase reports no sizes and no counter — one line per finished
    # package and nothing else — so the figure has to come from weighing its package
    # cache. That is world-readable, so no root is involved.
    cache_dir = tempfile.mkdtemp()
    _orig_cache = updater.ZYPP_PACKAGE_CACHE
    updater.ZYPP_PACKAGE_CACHE = Path(cache_dir)
    try:
        check("an empty cache weighs nothing", updater.cache_bytes() == 0)
        wC = updater.Updater()
        wC._run_active = True
        wC._reset_activity()        # baseline taken before anything is fetched
        wC.handle_line("@@STEP_BEGIN@@|system|1|5|Updating system packages")
        wC.handle_line("@@PROGRESS@@|system|1|0|download|0|90596966")
        check("a prefetch tally still invents no denominator",
              "1 so far" in wC.status.text() and "of 0" not in wC.status.text())
        (Path(cache_dir) / "pkg.rpm").write_bytes(b"x" * (20 * 1024 * 1024))
        wC._tick_activity()
        check("the download is measured even though zypper reported no size",
              "20 MB of 86 MB" in wC.activity.text())
        # Packages already cached sit inside the baseline: zypper won't re-fetch them, so
        # counting them would overstate progress and flatter the rate.
        wC2 = updater.Updater()
        wC2._run_active = True
        wC2._reset_activity()       # baseline now includes the 20 MB above
        wC2.handle_line("@@PROGRESS@@|system|1|0|download|0|90596966")
        wC2._tick_activity()
        check("already-cached packages are excluded from this run's figure",
              "20 MB" not in wC2.activity.text())
    finally:
        updater.ZYPP_PACKAGE_CACHE = _orig_cache
        shutil.rmtree(cache_dir, ignore_errors=True)

    # --- dialogs open over the window, on Wayland too (ONEUP-0049) --------------
    # Qt's move() is accepted and silently ignored on Wayland (the compositor owns
    # placement), which is why every dialog opened away from the window. X11 still moves
    # directly; Wayland has to ask KWin, so the one thing to prove here is that each
    # session type takes its own path and neither throws.
    _orig_session = os.environ.get("XDG_SESSION_TYPE", "")
    try:
        os.environ["XDG_SESSION_TYPE"] = "x11"
        check("the session type is read from the environment", not updater._on_wayland())
        host = updater.QWidget()
        host.setGeometry(100, 100, 800, 600)
        dlg = updater.QDialog(host)
        dlg.resize(200, 100)
        updater.center_on_parent(dlg)
        check("on X11 a dialog is moved onto its parent's centre",
              abs(dlg.frameGeometry().center().x() - host.frameGeometry().center().x()) <= 2
              and abs(dlg.frameGeometry().center().y() - host.frameGeometry().center().y()) <= 2)
        os.environ["XDG_SESSION_TYPE"] = "wayland"
        check("Wayland is detected", updater._on_wayland())
        moved_to = dlg.pos()
        updater.center_on_parent(dlg)   # queues a KWin request; must not move it itself
        check("on Wayland placement is left to the compositor, not a futile move()",
              dlg.pos() == moved_to)
    finally:
        os.environ["XDG_SESSION_TYPE"] = _orig_session

    # --- Stop button (ONEUP-0047) -----------------------------------------------
    # Stop is deliberately cooperative: it asks, and the engine honours it at a safe
    # point. The UI must promise exactly that and never imply an instant abort.
    wS = updater.Updater()
    check("Stop is hidden while idle", not wS.stop_btn.isVisibleTo(wS))
    check("Stop explains it waits for the current step",
          "after the current step" in wS.stop_btn.toolTip()
          and "never cut off half-way" in wS.stop_btn.toolTip())
    stop_dir = tempfile.mkdtemp()
    orig_stop, orig_rs = updater.STOP_REQUEST, updater.RUN_STATE
    updater.STOP_REQUEST = Path(stop_dir) / "stop.request"
    updater.RUN_STATE = Path(stop_dir) / "run.state"
    try:
        wS._run_active, wS._check_mode = True, False
        wS.set_controls_enabled(False)
        check("Stop appears once a real run is going", wS.stop_btn.isVisibleTo(wS))
        wS.request_stop()
        check("asking to stop creates the file the engine watches",
              updater.STOP_REQUEST.exists())
        check("the button reflects that the request is in", wS.stop_btn.text() == "Stopping…")
        check("it cannot be clicked twice", not wS.stop_btn.isEnabled())
        check("the status says what will actually happen",
              "after the current step" in wS.status.text())
        # A stopped run must claim neither success nor failure.
        wS.handle_line("@@DONE@@|stopped")
        wS.on_finished(0, None)
        check("a stopped run is reported as stopped", wS.bar.format() == "Stopped")
        check("a stopped run never says 'All done'", "All done" not in wS.status.text())
        check("a stopped run says what survived",
              "still installed" in wS.status.text())
        # A --check has nothing to stop.
        wS._run_active, wS._check_mode = True, True
        wS.set_controls_enabled(False)
        check("Stop is not offered for a read-only check", not wS.stop_btn.isVisibleTo(wS))
    finally:
        updater.STOP_REQUEST, updater.RUN_STATE = orig_stop, orig_rs
        shutil.rmtree(stop_dir, ignore_errors=True)

    # --- attaching to a run started by an earlier window (ONEUP-0045) -----------
    # Runs outlive the window on purpose, so a fresh window must find one in flight and
    # follow its log rather than offering a Run that could only fail on the lock.
    import subprocess as _sp
    attach_dir = tempfile.mkdtemp()
    attach_log = os.path.join(attach_dir, "run.log")
    # A stand-in engine: alive, so the pid check passes, and writing real marker lines.
    holder = _sp.Popen(["sleep", "60"])
    with open(attach_log, "w") as fh:
        fh.write("@@STEP_BEGIN@@|system|1|2|Updating system packages\n"
                 "@@PROGRESS@@|system|12|141|download\n")
    orig_state = updater.RUN_STATE
    updater.RUN_STATE = Path(attach_dir) / "run.state"
    updater.RUN_STATE.write_text(f"{holder.pid}\n{attach_log}\nsystem,cache\n0\n")
    try:
        wA = updater.Updater()
        check("a run already in flight is picked up", wA._run_active is True)
        check("the window says it is following an earlier run",
              "still running" in wA.status.text() or "141" in wA.status.text())
        check("the controls are locked while following", not wA.run_btn.isEnabled())
        check("the step count comes from the attached run's steps", wA._total == 2)
        check("markers already in the log are replayed",
              wA.rows["system"].badge.text() == "12/141")
        # New lines appended by the running engine must be picked up on the next poll.
        with open(attach_log, "a") as fh:
            fh.write("@@PROGRESS@@|system|99|141|install\n")
        wA._poll_attached_run()
        check("newly appended log lines are followed live",
              wA.status.text() == "Installing 99 of 141 packages…")
        # When the followed run ends there is no QProcess and no exit code to read — only
        # its @@DONE@@ line. This must not throw (it did: on_finished assumed self.proc).
        with open(attach_log, "a") as fh:
            fh.write("@@DONE@@|ok\n")
        holder.terminate(); holder.wait()
        try:
            wA._poll_attached_run()
            check("a followed run finishing is handled without a process object", True)
        except Exception as exc:  # noqa: BLE001 — any throw is the failure.
            check(f"a followed run finishing is handled ({exc})", False)
        check("the followed run's own verdict is used", wA._run_active is False)
        check("the record is cleared once the followed run ends",
              not updater.RUN_STATE.exists())
        # A stale record (pid long gone) must not lock a fresh window out.
        updater.RUN_STATE.write_text(f"{holder.pid}\n{attach_log}\nsystem\n0\n")
        wB = updater.Updater()
        check("a stale record does not lock the app", wB._run_active is False)
        check("a stale record is deleted", not updater.RUN_STATE.exists())
    finally:
        if holder.poll() is None:
            holder.terminate(); holder.wait()
        updater.RUN_STATE = orig_state
        shutil.rmtree(attach_dir, ignore_errors=True)

    # --- quitting mid-run warns first (ONEUP-0042) ------------------------------
    # The dialog itself is modal, so the decision is tested and _ask_quit_during_run
    # is stubbed — that split is why the method exists separately.
    wQ = updater.Updater()
    asked = []
    wQ._ask_quit_during_run = lambda: (asked.append(1), False)[1]
    wQ._run_active = False
    check("quitting while idle asks nothing", wQ._confirm_quit() is True and not asked)
    wQ._run_active = True
    check("quitting mid-run asks first, and 'keep open' blocks the quit",
          wQ._confirm_quit() is False and len(asked) == 1)
    wQ._ask_quit_during_run = lambda: True
    check("'close anyway' still allows the quit", wQ._confirm_quit() is True)
    # With no tray, closing the window IS quitting, so it must honour the same guard.
    wQ._tray = None
    wQ._ask_quit_during_run = lambda: False
    ev = QCloseEvent()
    ev.setAccepted(True)
    wQ.closeEvent(ev)
    check("a mid-run window close is refused when the user keeps OneUp open",
          not ev.isAccepted())

    # --- passwordless-authorization toggle (opt-in) ----------------------------
    check("auth toggle defaults to off", w.auth_btn.text() == "Passwordless: off")
    w._set_auth_checked(True)
    check("auth toggle reflects 'on' without firing grant",
          w.auth_btn.isChecked() and w.auth_btn.text() == "Passwordless: on")
    w._set_auth_checked(False)
    check("auth toggle reflects 'off'",
          not w.auth_btn.isChecked() and w.auth_btn.text() == "Passwordless: off")

    class _StubProc:  # stands in for the finished QProcess, returns canned stdout
        def __init__(self, text): self._b = text.encode()
        def readAllStandardOutput(self): return self._b
    w._on_auth_status_finished(_StubProc("log noise\n@@AUTH@@|on\n"))
    check("status marker 'on' turns the toggle on", w.auth_btn.isChecked())
    w._on_auth_status_finished(_StubProc("@@AUTH@@|off\n"))
    check("status marker 'off' turns the toggle off", not w.auth_btn.isChecked())

    # A REPO marker names the duplicate URL and flips the banner button to the
    # repo manager.
    w2 = updater.Updater()
    w2.handle_line("@@REPO@@|warn|duplicate|http://x.example/repo")
    check("repo warning names the duplicate URL",
          "http://x.example/repo" in w2.warn_label.text())
    check("repo warning arms the repo-manager action", w2._warn_repo_dup is True)
    check("repo warning button becomes 'Manage repositories…'",
          w2.warn_btn.text() == "Manage repositories…")

    # A SNAPSHOTS pre-flight advisory names the count and arms the "thin" action.
    w3 = updater.Updater()
    w3.handle_line("@@SNAPSHOTS@@|warn|30")
    check("snapshot advisory arms the thin action", w3._warn_snapshots is True)
    check("snapshot advisory captures the count", w3._snapshot_count == 30)
    check("snapshot advisory names the count", "30 system restore points" in w3.warn_label.text())
    check("snapshot advisory button becomes 'Thin snapshots…'",
          w3.warn_btn.text() == "Thin snapshots…")
    check("snapshot advisory shows the warning banner", w3.warn_banner.isVisibleTo(w3))

    # SNAPSHOT_ITEM markers feed the rollback picker (ONEUP-0020): well-formed ids
    # are captured, a non-numeric id is dropped, and the dialog lists them
    # newest-first with the pre-update snapshot pre-selected.
    w4 = updater.Updater()
    for line in ("@@SNAPSHOT@@|100",
                 "@@SNAPSHOT_ITEM@@|98|2026-07-20 09:00:00|OneUp pre-update 2026-07-20 09:00",
                 "@@SNAPSHOT_ITEM@@|99|2026-07-22 09:00:00|zypp(zypper)",
                 "@@SNAPSHOT_ITEM@@|100|2026-07-24 09:00:00|OneUp pre-update 2026-07-24 09:00",
                 "@@SNAPSHOT_ITEM@@|bogus|x|y"):
        w4.handle_line(line)
    check("rollback picker captures well-formed snapshots", len(w4._snapshots) == 3)
    check("rollback picker drops a non-numeric snapshot id",
          all(sid.isdigit() for sid, _, _ in w4._snapshots))
    dlg = updater.RollbackDialog(w4, w4._snapshots, w4._snapshot)
    check("picker lists the newest snapshot first", dlg.list.item(0).data(Qt.UserRole) == "100")
    check("picker pre-selects the pre-update snapshot", dlg.selected_id() == "100")
    dlg.list.setCurrentRow(dlg.list.count() - 1)   # choose the oldest listed
    check("picker returns the chosen snapshot id", dlg.selected_id() == "98")
    dlg.reject()

    # --- 3. on_finished promotes the accumulated state into the right banners ---
    w.proc = QProcess(w)   # on_finished releases self.proc; give it a real one.
    w.on_finished(0, QProcess.ExitStatus.NormalExit)
    check("reboot banner shown after a real install", w.reboot_banner.isVisibleTo(w))
    check("rollback offered after a system change", w.rollback_btn.isVisibleTo(w))
    check("retry offered after a failed step", w.retry_btn.isVisibleTo(w))
    # The window is never shown (not active), so a finished run notifies. The mock
    # notify-send on PATH records the call; Popen is async, so poll briefly.
    check("finished run fires a desktop notification", _wait_for_notify())

    # --- 4. A package-only change offers services, not a reboot ----------------
    w = updater.Updater()
    for line in ("@@STEP_END@@|system|ok|packages updated",
                 "@@INSTALLED@@|2|yes|no",
                 "@@SERVICES@@|foo.service bar.service",
                 "@@REBOOT@@|no"):
        w.handle_line(line)
    w.proc = QProcess(w)
    w.on_finished(0, QProcess.ExitStatus.NormalExit)
    check("services banner shown for a package-only change", w.services_banner.isVisibleTo(w))
    check("no reboot banner for a package-only change", not w.reboot_banner.isVisibleTo(w))

    # --- 4b. A reason-bearing REBOOT marker names the culprit in the banner ----
    w = updater.Updater()
    for line in ("@@STEP_END@@|system|ok|7 packages updated",
                 "@@INSTALLED@@|7|yes|no",
                 "@@REBOOT@@|yes|a new kernel and your NVIDIA graphics driver were installed"):
        w.handle_line(line)
    check("reboot reason captured from the marker",
          w._reboot_reason == "a new kernel and your NVIDIA graphics driver were installed")
    w.proc = QProcess(w)
    w.on_finished(0, QProcess.ExitStatus.NormalExit)
    check("reboot banner names the kernel + driver, keeping NVIDIA casing",
          "NVIDIA graphics driver" in w.reboot_label.text()
          and w.reboot_label.text().lstrip("⚠ ").startswith("A new kernel"))

    # --- 5. --check mode summarises available updates without banners ----------
    w = updater.Updater()
    w._check_mode = True
    for line in ("@@CHECK@@|system|2",
                 "@@CHECK@@|flatpak|0",
                 "@@CHECK@@|TOTAL|2"):
        w.handle_line(line)
    check("check: system row shows availability", w.rows["system"].badge.text() == "2 available")
    check("check: flatpak row shows up to date", w.rows["flatpak"].badge.text() == "up to date")
    w.proc = QProcess(w)
    w.on_finished(0, QProcess.ExitStatus.NormalExit)
    check("check: no reboot banner", not w.reboot_banner.isVisibleTo(w))

    # --- headless command builder shared by both timers ------------------------
    check("headless --check command ends in --check",
          updater.Updater._headless_command("--check").endswith("--check"))
    check("headless --update command ends in --update",
          updater.Updater._headless_command("--update").endswith("--update"))
    check("headless command quotes the executable path",
          updater.Updater._headless_command("--check").startswith('"'))

    # Regression guard: the GUI-only --update token must NEVER be forwarded to the
    # engine (it exits 2 on unknown flags, which would make the 2am weekly run
    # silently fail). _headless_update() runs the engine with --notify only.
    _captured = {}
    _orig_run = updater.subprocess.run
    updater.subprocess.run = lambda a, *args, **kw: (
        _captured.update(argv=a) or type("R", (), {"returncode": 0})())
    try:
        updater._headless_update()
    finally:
        updater.subprocess.run = _orig_run
    check("headless --update invokes the engine with --notify, not --update",
          "--notify" in _captured.get("argv", []) and "--update" not in _captured.get("argv", []))

    # --- Settings popup groups the three background toggles --------------------
    w = updater.Updater()
    check("Settings button exists in the header", hasattr(w, "settings_btn"))
    check("auto-update toggle defaults to off",
          hasattr(w, "autoupdate_btn") and not w.autoupdate_btn.isChecked()
          and w.autoupdate_btn.text() == "Automatic updates: off")
    dlg = updater.SettingsDialog(w)
    hosted = dlg.findChildren(QPushButton)
    check("Settings dialog hosts the weekly-check toggle", w.auto_btn in hosted)
    check("Settings dialog hosts the passwordless toggle", w.auth_btn in hosted)
    check("Settings dialog hosts the auto-update toggle", w.autoupdate_btn in hosted)

    # --- coupling: auto-update never enables without passwordless ---------------
    updater.QMessageBox.information = staticmethod(lambda *a, **k: 0)
    updater.QMessageBox.warning = staticmethod(lambda *a, **k: 0)

    # (a) enabling with passwordless OFF and cancelling the combined dialog installs nothing
    w = updater.Updater()
    installed_a = []
    w._install_user_timer = lambda *a, **k: (installed_a.append(a) or True)
    w._confirm_passwordless = lambda lead="": False          # user cancels
    w._set_auth_checked(False)                               # passwordless off
    w.on_autoupdate_toggled(True)
    check("cancel combined-enable installs no update timer", not installed_a)
    check("cancel combined-enable leaves auto-update off", not w.autoupdate_btn.isChecked())
    check("cancel combined-enable clears the pending latch", w._pending_autoupdate is False)

    # (b) a settle reporting passwordless OFF while a latch is pending must NOT install
    w = updater.Updater()
    installed_b = []
    w._install_user_timer = lambda *a, **k: (installed_b.append(a) or True)
    w._pending_autoupdate = True
    w._on_auth_status_finished(_StubProc("@@AUTH@@|off\n"))
    check("settle passwordless-off does not install the update timer (stale-switch guard)",
          not installed_b)
    check("settle passwordless-off consumes the latch", w._pending_autoupdate is False)

    # (c) a settle reporting passwordless ON with a pending latch installs + turns on
    w = updater.Updater()
    installed_c = []
    w._install_user_timer = lambda *a, **k: (installed_c.append(a) or True)
    w._pending_autoupdate = True
    w._on_auth_status_finished(_StubProc("@@AUTH@@|on\n"))
    check("settle passwordless-on installs the update timer", bool(installed_c))
    check("settle passwordless-on turns the auto-update toggle on", w.autoupdate_btn.isChecked())

    # (d) revoking passwordless while auto-update is on clears the schedule
    w = updater.Updater()
    removed_d = []
    w._autoupdate_enabled = lambda: True
    w._remove_user_timer = lambda name: removed_d.append(name)
    w._run_auth = lambda *a, **k: None                       # don't spawn a real process
    w._set_autoupdate_checked(True)
    w.on_auth_toggled(False)                                 # user revokes
    check("revoke passwordless removes the update timer", "oneup-update" in removed_d)
    check("revoke passwordless clears the auto-update toggle", not w.autoupdate_btn.isChecked())

    # --- 6. the About dialog opens and closes without error --------------------
    w = updater.Updater()
    check("About button exists in the header", hasattr(w, "about_btn"))
    # show_about() runs a modal exec(); schedule a close so the test doesn't block.
    def _dismiss_about():
        for tl in app.topLevelWidgets():
            if isinstance(tl, QMessageBox) and tl.isVisible():
                tl.done(0)
    QTimer.singleShot(50, _dismiss_about)
    try:
        w.show_about()
        check("About dialog opens and dismisses cleanly", True)
    except Exception as exc:  # noqa: BLE001
        check(f"About dialog opens and dismisses cleanly ({exc})", False)

    # --- 7. the Repositories manager: parse, duplicate flag, apply command ------
    check("Repositories button exists in the header", hasattr(w, "repos_btn"))

    sample = (
        "Repository priorities in effect:\n"
        "#  | Alias      | Name      | Enabled | GPG Check | Refresh | URI\n"
        "---+------------+-----------+---------+-----------+---------+----------\n"
        " 1 | oss        | Main OSS  | Yes     | (r ) Yes  | Yes     | http://d.o/oss/\n"
        " 2 | debug      | Debug     | No      | ----      | ----    | http://d.o/debug/\n"
        " 3 | debug-dup  | Debug 2   | No      | ----      | ----    | http://d.o/debug/\n"
    )
    repos = updater._parse_repos(sample)
    check("parse reads all repositories", len(repos) == 3)
    check("parse reads the enabled flag", repos[0]["enabled"] is True and repos[1]["enabled"] is False)
    check("parse reads the URL", repos[0]["url"] == "http://d.o/oss/")

    dlg = updater.RepoManagerDialog(None, repos)
    check("manager builds a row per repository", len(dlg._rows) == 3)
    check("repos dialog is wide enough not to clip URLs", dlg.minimumWidth() >= 720)
    # Only the two repos sharing a URL get a Remove button.
    remove_btns = [b for b in dlg.findChildren(QPushButton) if b.text() == "Remove"]
    check("only duplicate rows get a Remove action", len(remove_btns) == 2)

    # Each row carries a plain-English description of what the repo is for.
    row_labels = [b.text() for b in dlg.findChildren(QLabel)]
    check("manager row shows a repo description",
          any("Main openSUSE" in t for t in row_labels))
    P = updater._repo_purpose
    check("purpose: debug detected before oss",
          "Debug symbols" in P({"alias": "x-debug-oss", "name": "D", "url": "u", "enabled": False}))
    check("purpose: non-oss detected before oss",
          "Non-open-source" in P({"alias": "repo-non-oss", "name": "N", "url": "u", "enabled": True}))
    check("purpose: main oss collection",
          "Main openSUSE" in P({"alias": "repo-oss", "name": "O", "url": "u", "enabled": True}))
    check("purpose: unknown repo falls back",
          P({"alias": "zzz", "name": "Z", "url": "http://ex/", "enabled": True}) == "Software package repository.")

    # No change -> empty command; a disable + a remove -> one validated pkexec call.
    check("no changes yields an empty apply command", dlg._build_apply_command() == [])
    dlg._rows[0]["switch"].setChecked(False)   # disable oss
    dlg._rows[2]["remove"] = True              # remove the duplicate
    cmd = dlg._build_apply_command()
    check("apply command is a single pkexec invocation",
          bool(cmd) and cmd[0] == "pkexec" and cmd[1] == "sh")
    check("apply disables the toggled repo", "modifyrepo --disable oss" in cmd[3])
    check("apply removes the duplicate", "removerepo debug-dup" in cmd[3])

    # An unsafe alias must never reach the root shell.
    unsafe = [{"alias": "evil; rm -rf /", "name": "x", "enabled": False, "url": "u"},
              {"alias": "y", "name": "y", "enabled": False, "url": "u"}]
    dlg_bad = updater.RepoManagerDialog(None, unsafe)
    dlg_bad._rows[0]["switch"].setChecked(True)
    check("an unsafe repo alias refuses to build a command",
          dlg_bad._build_apply_command() is None)

    # --- failure-hint "Copy command" fallback ---------------------------------
    E = updater.Updater._extract_command
    check("extract_command pulls the runnable command",
          E("A repository signing key is still rejected after an automatic import — "
            "as a last resort run: sudo zypper --gpg-auto-import-keys refresh, then "
            "retry, or check the log for the offending repo.")
          == "sudo zypper --gpg-auto-import-keys refresh")
    check("extract_command returns empty when there is no command",
          E("A package conflict — check the log.") == "")
    w = updater.Updater()
    w._show_warning("Something failed — run: sudo zypper refresh, then retry.")
    check("copy button appears when a hint carries a command",
          w.warn_copy_btn.isVisibleTo(w.warn_banner)
          and w._hint_command == "sudo zypper refresh")
    w._show_warning("Low disk space — free some room and retry.")
    check("copy button hidden when a hint carries no command",
          not w.warn_copy_btn.isVisibleTo(w.warn_banner))
    try:
        w._show_warning("run: sudo zypper refresh, then retry.")
        w._copy_hint_command()   # must not throw under offscreen Qt
        check("copy command runs without error", True)
    except Exception as exc:  # noqa: BLE001
        check(f"copy command runs without error ({exc})", False)

    # --- signing-key remedy: the app fixes it, but only after a warned confirm ---
    w = updater.Updater()
    w.handle_line("@@REMEDY@@|import-keys")
    check("REMEDY marker arms the key-import remedy", w._remedy_keys is True)
    w._failed_steps = ["system"]
    w._hints = ['A repository signing key is out of date. Use "Import signing key & '
                'retry" to fix it, or run: sudo zypper --gpg-auto-import-keys refresh.']
    w.proc = QProcess(w)
    w.on_finished(1, QProcess.ExitStatus.NormalExit)
    check("warn button offers the key-import fix",
          w.warn_btn.text() == "Import signing key & retry")

    launched = {}
    w._launch = lambda steps, check=False, import_keys=False: launched.update(
        steps=list(steps), import_keys=import_keys)
    w._confirm_key_import = lambda: False          # user cancels the trust confirmation
    w._fix_keys_and_retry()
    check("cancelling the key-import confirmation does not retry", not launched)
    w._confirm_key_import = lambda: True           # user approves
    w._fix_keys_and_retry()
    check("confirming imports keys and retries the failed steps",
          launched.get("import_keys") is True and "system" in launched.get("steps", []))

    # --- ONEUP-0018: system-tray icon ------------------------------------------
    # (1) Autostart Exec targets --tray and quotes the executable.
    _orig_which = updater.shutil.which
    updater.shutil.which = lambda name: None            # force the sys.executable branch
    updater.os.environ.pop("APPIMAGE", None)
    try:
        exec_line = updater.Updater._autostart_exec()
    finally:
        updater.shutil.which = _orig_which
    check("autostart Exec ends in --tray", exec_line.endswith(" --tray"))
    check("autostart Exec double-quotes the executable", exec_line.startswith('"'))

    # (2) install/remove round-trips a real file under the sandbox HOME.
    w_tmp = updater.Updater()
    check("start-at-boot starts disabled", w_tmp._startboot_enabled() is False)
    ok_install = w_tmp._install_autostart()
    check("install_autostart writes the file", ok_install and w_tmp._startboot_enabled())
    body = w_tmp._autostart_path().read_text()
    check("autostart file targets --tray", "--tray" in body and "[Desktop Entry]" in body)
    w_tmp._remove_autostart()
    check("remove_autostart deletes the file", not w_tmp._startboot_enabled())

    _orig_exe = updater.sys.executable
    updater.sys.executable = "/opt/o$ne%up/oneup"
    updater.shutil.which = lambda name: None
    updater.os.environ.pop("APPIMAGE", None)
    try:
        line = updater.Updater._autostart_exec()
    finally:
        updater.sys.executable = _orig_exe
        updater.shutil.which = _orig_which
    check("Exec escapes '$' as backslash-backslash-'$' (not $$ or bare $)", r"\\$" in line and "$$" not in line)
    check("Exec escapes '%' as '%%'", "%%up" in line)

    # (3) The tray icon renders in both states and is never null.
    w = updater.Updater()
    check("neutral tray icon is non-null", not w._tray_icon(False).isNull())
    check("attention tray icon is non-null", not w._tray_icon(True).isNull())
    try:
        w._show_window()   # must not throw under offscreen Qt
        check("_show_window runs without error", True)
    except Exception as exc:  # noqa: BLE001
        check(f"_show_window runs without error ({exc})", False)

    # (4) The periodic check is silent and parses the real THREE-field TOTAL line.
    w = updater.Updater()
    args = w._tray_check_args("/tmp/x.log")
    check("tray check runs --check", "--check" in args)
    check("tray check is silent (no --notify)", "--notify" not in args)
    w._parse_tray_line("@@CHECK@@|TOTAL|3|updates available")
    check("tray parses field 1 of the three-field TOTAL line", w._tray_total == 3)
    w._parse_tray_line("@@CHECK@@|TOTAL|0|updates available")
    check("tray parses zero updates as neutral", w._tray_total == 0)
    w._parse_tray_line("@@STEP_BEGIN@@|system|1|3|x")   # non-CHECK line ignored
    check("tray parser ignores non-TOTAL lines", w._tray_total == 0)
    # (4b) The tray check reuses ONE rolling log, overwritten each run, so a resident
    # session doesn't accumulate a new file ~4x/day (ONEUP-0024).
    p1 = w._traycheck_log()
    p1.write_text("stale output from a previous tray check\n")
    p2 = w._traycheck_log()
    check("tray check reuses one fixed log file", p1 == p2 and p2.name == "traycheck.log")
    check("tray check rolls (truncates) the log each run", p2.read_text() == "")

    # (5) _ensure_tray no-ops when no system tray is available (offscreen CI case).
    w = updater.Updater()
    check("no system tray under offscreen Qt", w._tray_available is False)
    w._ensure_tray()
    check("_ensure_tray builds nothing without a tray", w._tray is None)
    # Force the 'available' path with a stub tray so teardown logic is exercised.
    w._tray = object()                 # pretend a tray exists
    w._tray_timer = updater.QTimer(w)
    w._tray_timer.start(999999)
    w._teardown_tray()
    check("teardown stops the timer", w._tray_timer is None)
    check("teardown drops the tray reference", w._tray is None)

    # (6) Settings dialog hosts the two new toggles; both default off.
    w = updater.Updater()
    check("tray toggle defaults off", not w.tray_btn.isChecked() and w.tray_btn.text() == "Tray icon: off")
    check("start-at-boot toggle defaults off",
          not w.startboot_btn.isChecked() and w.startboot_btn.text() == "Start at boot: off")
    dlg = updater.SettingsDialog(w)
    hosted = dlg.findChildren(QPushButton)
    check("Settings dialog hosts the tray toggle", w.tray_btn in hosted)
    check("Settings dialog hosts the start-at-boot toggle", w.startboot_btn in hosted)

    # (7) Coupling — enabling start-at-boot turns the tray on.
    w = updater.Updater()
    w._install_autostart = lambda: True
    w._ensure_tray = lambda: None
    w.on_startboot_toggled(True)
    check("boot-on turns the tray on", w.tray_btn.isChecked())
    check("boot-on persists tray_enabled", w.settings.value("tray_enabled", False, type=bool) is True)

    # (8) Coupling — turning the tray off removes start-at-boot.
    w = updater.Updater()
    removed = []
    w._remove_autostart = lambda: removed.append(True)
    w._teardown_tray = lambda: None
    w._set_startboot_checked(True)
    w.on_tray_toggled(False)
    check("tray-off removes autostart", removed == [True])
    check("tray-off clears the start-at-boot toggle", not w.startboot_btn.isChecked())

    # (9) Coupling — turning start-at-boot off leaves the tray on.
    w = updater.Updater()
    removed2 = []
    w._remove_autostart = lambda: removed2.append(True)
    w._set_tray_checked(True)
    w.on_startboot_toggled(False)
    check("boot-off removes autostart", removed2 == [True])
    check("boot-off leaves the tray on", w.tray_btn.isChecked())

    # (10) A failed autostart write reverts start-at-boot only (tray stays on).
    w = updater.Updater()
    w._install_autostart = lambda: False
    w._ensure_tray = lambda: None
    w.on_startboot_toggled(True)
    check("failed install reverts start-at-boot", not w.startboot_btn.isChecked())
    check("failed install leaves the tray on", w.tray_btn.isChecked())

    # (11) Close-to-tray: with a tray live, closeEvent hides (not quits) and hints once.
    w = updater.Updater()
    w._tray = object()                       # pretend resident
    hints = []
    w._notify_tray_hint = lambda: hints.append(True)
    class _Evt:
        def __init__(self): self.ignored = False
        def ignore(self): self.ignored = True
        def accept(self): pass
    w.show()   # show first so isHidden() below meaningfully proves closeEvent hid it
    check("window is visible before the tray-close", not w.isHidden())
    e1 = _Evt(); w.closeEvent(e1)
    check("close-to-tray ignores the close event", e1.ignored)
    check("close-to-tray hides the window", w.isHidden())
    check("close-to-tray fires the hint once", hints == [True])
    e2 = _Evt(); w.closeEvent(e2)
    check("close-to-tray does not re-hint on a second close", hints == [True])

    # (12) on_finished refreshes the tray: a successful run -> neutral; a check -> the count.
    w = updater.Updater()
    applied = []
    w._apply_tray_total = lambda n: applied.append(n)
    w.proc = QProcess(w)
    w._installed_count = "2"
    w.on_finished(0, QProcess.ExitStatus.NormalExit)     # a run
    check("successful run sets the tray neutral", applied and applied[-1] == 0)
    w = updater.Updater()
    applied2 = []
    w._apply_tray_total = lambda n: applied2.append(n)
    w._check_mode = True
    w._installed_count = "5"
    w.proc = QProcess(w)
    w.on_finished(0, QProcess.ExitStatus.NormalExit)     # a check
    check("finished check pushes the count to the tray", applied2 and applied2[-1] == 5)

    # --- ONEUP-0025: repo resilience — skip_repos threads through to the engine ---
    args = updater.Updater._engine_args(["system"], check=False, import_keys=False,
                                        skip_repos=["google-chrome"])
    check("skip_repos adds one --skip-repo per alias", "--skip-repo=google-chrome" in args)
    check("no skip_repos → no --skip-repo flag",
          "--skip-repo" not in " ".join(updater.Updater._engine_args(["system"], check=False)))

    # Unattended update passes --auto-skip-repos, additively alongside --notify (and
    # still never forwards the GUI-only --update token — mirrors the guard above).
    _cap = {}
    _orig = updater.subprocess.run
    updater.subprocess.run = lambda a, *ar, **kw: (
        _cap.update(argv=a) or type("R", (), {"returncode": 0})())
    try:
        updater._headless_update()
    finally:
        updater.subprocess.run = _orig
    check("headless update auto-skips broken sources",
          "--auto-skip-repos" in _cap.get("argv", []))
    check("headless update still passes --notify, not --update",
          "--notify" in _cap.get("argv", []) and "--update" not in _cap.get("argv", []))

    # --- ONEUP-0025: REPO_SKIPPED is recorded; skip-repo remedy arms a named
    # banner action ("Skip <source> & update the rest") -------------------------
    _orig_read_repos = updater.read_repos
    updater.read_repos = lambda: [{"alias": "google-chrome", "name": "Google Chrome",
                                   "enabled": True, "url": "http://c/"}]
    try:
        w = updater.Updater()
        w.handle_line("@@REPO_SKIPPED@@|google-chrome|signature")
        check("REPO_SKIPPED recorded", "google-chrome" in w._skipped_repos)

        w.handle_line("@@REMEDY@@|skip-repo|google-chrome")
        check("skip-repo remedy stores the alias", w._remedy_skips == ["google-chrome"])
        w._failed_steps = ["system"]
        w._hints = ["The 'google-chrome' repository failed — the rest can still update."]
        w.proc = QProcess(w)
        w.on_finished(1, QProcess.ExitStatus.NormalExit)
        check("banner offers a NAMED skip action",
              "Google Chrome" in w.warn_btn.text() and "Skip" in w.warn_btn.text())
        check("second banner button stays hidden when only one remedy is armed",
              not w.warn_btn2.isVisibleTo(w.warn_banner))

        # Clicking it re-launches with skip_repos = the alias, re-running the
        # failed steps.
        launched = {}
        w._launch = lambda steps, check=False, import_keys=False, skip_repos=None: (
            launched.update(steps=list(steps), skip=list(skip_repos or [])))
        w._skip_repo_and_retry()
        check("skip action re-launches with the alias", launched.get("skip") == ["google-chrome"])
        check("skip action re-runs the failed steps", launched.get("steps") == ["system"])

        # --- expired key: BOTH remedies armed at once — skip stays primary, the
        # key-import fix is reachable via a genuine second button --------------
        w2 = updater.Updater()
        w2.handle_line("@@REMEDY@@|skip-repo|google-chrome")
        w2.handle_line("@@REMEDY@@|import-keys")
        w2._failed_steps = ["system"]
        w2._hints = ["A repository signing key is out of date."]
        w2.proc = QProcess(w2)
        w2.on_finished(1, QProcess.ExitStatus.NormalExit)
        check("both remedies armed: primary button is the named skip action",
              w2.warn_btn.text() == "Skip Google Chrome & update the rest")
        check("both remedies armed: second button offers the key-import fix",
              w2.warn_btn2.isVisibleTo(w2.warn_banner)
              and w2.warn_btn2.text() == "Import signing key & retry")

        # The second button still goes through the same warned confirmation as
        # the single-remedy import-keys path (mirrors _fix_keys_and_retry's guard).
        launched2 = {}
        w2._launch = lambda steps, check=False, import_keys=False, skip_repos=None: (
            launched2.update(steps=list(steps), import_keys=import_keys))
        w2._confirm_key_import = lambda: True
        w2.warn_btn2.click()
        check("clicking the second button imports keys and retries",
              launched2.get("import_keys") is True and "system" in launched2.get("steps", []))

        # --- only import-keys armed: single-action path is unchanged, no 2nd btn -
        w3 = updater.Updater()
        w3.handle_line("@@REMEDY@@|import-keys")
        w3._failed_steps = ["system"]
        w3._hints = ["A repository signing key is out of date."]
        w3.proc = QProcess(w3)
        w3.on_finished(1, QProcess.ExitStatus.NormalExit)
        check("import-keys only: warn button keeps the original single-action text",
              w3.warn_btn.text() == "Import signing key & retry")
        check("import-keys only: second banner button stays hidden",
              not w3.warn_btn2.isVisibleTo(w3.warn_banner))
    finally:
        updater.read_repos = _orig_read_repos

    # --- ONEUP-0025 final-review fix: a skip remedy with NO accompanying hint
    # (a corrupt-metadata source failure arms @@REMEDY@@|skip-repo but emits no
    # @@HINT@@) must still surface the warn banner with a named skip action —
    # not stay hidden with a dead-end remedy the user never sees. -------------
    updater.read_repos = lambda: [{"alias": "chrome", "name": "Google Chrome",
                                   "enabled": True, "url": "http://c/"}]
    try:
        w5 = updater.Updater()
        w5.handle_line("@@REMEDY@@|skip-repo|chrome")
        w5._failed_steps = ["system"]
        # Deliberately do NOT seed w5._hints — this is the whole point of the test.
        w5.proc = QProcess(w5)
        w5.on_finished(1, QProcess.ExitStatus.NormalExit)
        check("banner shows even with no HINT, only a skip remedy",
              w5.warn_banner.isVisibleTo(w5))
        check("fallback banner names the source and offers Skip",
              "Google Chrome" in w5.warn_btn.text() and "Skip" in w5.warn_btn.text())
    finally:
        updater.read_repos = _orig_read_repos

    # --- ONEUP-0025 final-review fix: two broken repos both offer their skip
    # remedy (the engine emits one @@REMEDY@@|skip-repo per culprit, up to 2) —
    # both must be collected and both re-run, not just the last one. ----------
    updater.read_repos = lambda: [
        {"alias": "chrome", "name": "Google Chrome", "enabled": True, "url": "http://c/"},
        {"alias": "brave", "name": "Brave Browser", "enabled": True, "url": "http://b/"},
    ]
    try:
        w6 = updater.Updater()
        w6.handle_line("@@REMEDY@@|skip-repo|chrome")
        w6.handle_line("@@REMEDY@@|skip-repo|brave")
        check("both skip remedies are accumulated, not overwritten",
              w6._remedy_skips == ["chrome", "brave"])
        w6._failed_steps = ["system"]
        w6.proc = QProcess(w6)
        w6.on_finished(1, QProcess.ExitStatus.NormalExit)
        check("banner offers a combined skip action for multiple sources",
              "Skip 2 sources" in w6.warn_btn.text())

        launched6 = {}
        w6._launch = lambda steps, check=False, import_keys=False, skip_repos=None: (
            launched6.update(steps=list(steps), skip=list(skip_repos or [])))
        w6._skip_repo_and_retry()
        check("skip action re-launches with BOTH aliases",
              launched6.get("skip") == ["chrome", "brave"])
    finally:
        updater.read_repos = _orig_read_repos

    # A stale remedy from a prior run must never linger into the next one.
    _orig_qp_start = updater.QProcess.start
    updater.QProcess.start = lambda self, *a, **kw: None   # swallow the real engine launch
    try:
        w4 = updater.Updater()
        w4._remedy_skips = ["stale-alias"]
        w4.warn_btn2.setVisible(True)
        w4._launch(["system"], check=False)
        check("_launch resets a stale skip remedy", w4._remedy_skips == [])
        check("_launch hides a stale second banner button",
              not w4.warn_btn2.isVisibleTo(w4.warn_banner))
    finally:
        updater.QProcess.start = _orig_qp_start

    # --- Diagnostics bundle for a bug report (ONEUP-0031) ------------------
    _latest, _build = updater._latest_run_log, updater.build_diagnostics
    with tempfile.TemporaryDirectory() as _ld:
        _ldp = Path(_ld)
        for _n, _age in (("2026-07-24_100000.log", 300),       # older real run
                         ("2026-07-24_110000.check.log", 5),    # probe — ignore
                         ("traycheck.log", 1),                  # tray — ignore
                         ("2026-07-24_120000.log", 100)):       # newest real run
            _p = _ldp / _n
            _p.write_text("x")
            _t = time.time() - _age
            os.utime(_p, (_t, _t))
        check("diagnostics: latest run log skips probes and traycheck",
              _latest(_ldp) == _ldp / "2026-07-24_120000.log")
        check("diagnostics: missing log dir returns None", _latest(_ldp / "gone") is None)

    _rep = _build("1.1.0", "openSUSE Tumbleweed", ["system", "cache"],
                  "run.log", "path /home/ants/x on host boxname",
                  "2026-07-24 14:05", "/home/ants", "boxname")
    check("diagnostics: enabled tasks marked on", "system ✓" in _rep and "cache ✓" in _rep)
    check("diagnostics: disabled tasks marked off", "flatpak ✗" in _rep)
    check("diagnostics: home path scrubbed to ~", "/home/ants" not in _rep and "~/x" in _rep)
    check("diagnostics: hostname scrubbed", "boxname" not in _rep and "<host>" in _rep)
    check("diagnostics: no-run placeholder shown",
          "no update has been run yet" in _build("1", "x", [], None, None, "w", "", ""))
    _big = "H" * 20 + "T" * (updater.DIAG_LOG_CAP + 3000)
    _trim = _build("1", "x", [], "b.log", _big, "w", "", "")
    check("diagnostics: oversized log trimmed to its tail",
          "earlier output trimmed" in _trim and "H" * 20 not in _trim)

    wD = updater.Updater()
    wD.copy_diagnostics()
    check("diagnostics: button flips to Copied after a copy",
          wD.diag_btn.text() == "Copied ✓")
    check("diagnostics: clipboard receives the bundle",
          "OneUp diagnostics" in QApplication.clipboard().text())

    # --- ONEUP-0030: "last updated N days ago" nudge on the dashboard --------
    # refresh_last_run() derives a relative day-count from history.json and ambers
    # the line (dynamic stale property) once a run is STALE_AFTER_DAYS old.
    from datetime import timedelta
    updater.STATE_DIR.mkdir(parents=True, exist_ok=True)

    def _seed_history(days_ago: int, status: str = "OK"):
        when = updater.datetime.now() - timedelta(days=days_ago)
        updater.HISTORY.write_text(updater.json.dumps(
            {"when": when.isoformat(timespec="seconds"), "status": status}))

    wN = updater.Updater()
    _seed_history(0)
    wN.refresh_last_run()
    check("last-run nudge says 'today' for a same-day run", "today" in wN.last_run.text())
    check("a fresh run is not flagged stale", wN.last_run.property("stale") == "false")

    _seed_history(1)
    wN.refresh_last_run()
    check("last-run nudge says 'yesterday' for a one-day-old run",
          "yesterday" in wN.last_run.text())

    _seed_history(20)
    wN.refresh_last_run()
    check("last-run nudge counts the days for an older run", "20 days ago" in wN.last_run.text())
    check("a run past the threshold is flagged stale", wN.last_run.property("stale") == "true")

    _seed_history(updater.STALE_AFTER_DAYS - 1)
    wN.refresh_last_run()
    check("a run just under the threshold is not stale",
          wN.last_run.property("stale") == "false")

    _seed_history(20)
    wN.refresh_last_run()
    # ONEUP-0028: "overdue" must be in WORDS, not only the amber colour — colour
    # alone conveys nothing to a colour-blind user.
    check("an overdue run says so in words, not just in amber",
          "overdue" in wN.last_run.text())

    updater.HISTORY.unlink()
    wN.refresh_last_run()
    check("no history shows 'Last run: never'", wN.last_run.text() == "Last run: never")
    check("the 'never' state is not flagged stale", wN.last_run.property("stale") == "false")

    # --- ONEUP-0028: accessibility ---------------------------------------------
    wA = updater.Updater()

    # INV-1: nothing a user can reach may be nameless. Every focusable widget must
    # report an accessible name OR visible text. getattr for .text() is required,
    # not defensive: focusable non-buttons (the log is a QPlainTextEdit, the detail
    # scroll area and the rollback list) have no .text() at all.
    def unnamed(root):
        out = []
        for wid in root.findChildren(QWidget):
            if wid.focusPolicy() == Qt.NoFocus:
                continue
            label = wid.accessibleName() or (getattr(wid, "text", lambda: "")() or "")
            if not str(label).strip():
                out.append(f"{type(wid).__name__}#{wid.objectName()}")
        return out

    missing = unnamed(wA)
    check(f"every focusable widget in the window is named (unnamed: {missing})", not missing)

    repo_dlg = updater.RepoManagerDialog(wA, [
        {"alias": "oss", "name": "Main repository", "enabled": True, "url": "http://a/x"},
        {"alias": "up", "name": "Updates", "enabled": False, "url": "http://b/y"}])
    miss_repo = unnamed(repo_dlg)
    check(f"every focusable widget in Repositories is named (unnamed: {miss_repo})",
          not miss_repo)
    check("a repo switch does not bake its on/off state into its name",
          all("enabled" not in s.accessibleName()
              for s in repo_dlg.findChildren(updater.ToggleSwitch)))
    repo_dlg.reject()

    set_dlg = updater.SettingsDialog(wA)
    miss_set = unnamed(set_dlg)
    check(f"every focusable widget in Settings is named (unnamed: {miss_set})", not miss_set)
    set_dlg.reject()

    roll_dlg = updater.RollbackDialog(wA, [("41", "2026-07-24 09:00", "pre-update")], "41")
    miss_roll = unnamed(roll_dlg)
    check(f"every focusable widget in Rollback is named (unnamed: {miss_roll})", not miss_roll)
    roll_dlg.reject()

    # A checkable QAbstractButton maps to an accessible CheckBox WITH a checked
    # state, which is how on/off reaches a screen reader. Locking that in: if the
    # switch ever stopped being checkable, the state would silently disappear.
    sw = wA.rows["system"].switch
    iface = QAccessible.queryAccessibleInterface(sw)
    check("a task switch exposes a checkable role to assistive tech",
          iface is not None and iface.state().checkable == 1)
    check("a task switch reports its checked state",
          iface is not None and bool(iface.state().checked) == sw.isChecked())

    # INV-2 (switch): the state must be readable WITHOUT colour. Count near-white
    # pixels in the track half OPPOSITE the knob — that is where the bar/circle is
    # drawn. A colour-only track leaves that region a solid fill, so this fails on
    # a switch that lost its shape cue. NB a bare "checked vs unchecked images
    # differ" check would pass even then, because the knob itself moves.
    def shape_pixels(checked: bool) -> int:
        s = updater.ToggleSwitch()
        s.setChecked(checked)
        s._anim.stop()                      # settle the 130 ms knob slide first
        s.set_knob_pos(1.0 if checked else 0.0)
        img = s.grab().toImage()
        # Knob sits right when on, so inspect the LEFT third; and vice versa.
        xs = range(0, img.width() // 3) if checked else \
             range(img.width() * 2 // 3, img.width())
        n = 0
        for x in xs:
            for y in range(img.height()):
                c = img.pixelColor(x, y)
                if c.red() > 200 and c.green() > 200 and c.blue() > 200:
                    n += 1
        return n

    check("switch 'on' is shown by a shape, not only by green", shape_pixels(True) > 0)
    check("switch 'off' is shown by a shape, not only by red", shape_pixels(False) > 0)

    # INV-2 (tray): the attention badge must differ in SHAPE. Count near-white
    # pixels INSIDE the amber disc, inset to exclude the disc's own white outline.
    def badge_glyph_pixels() -> int:
        pm = wA._tray_icon(True).pixmap(64, 64).toImage()
        d, inset = 26, 5
        x0, y0 = pm.width() - d - 3 + inset, pm.height() - d - 3 + inset
        n = 0
        for x in range(x0, x0 + d - 2 * inset):
            for y in range(y0, y0 + d - 2 * inset):
                c = pm.pixelColor(x, y)
                if c.red() < 90 and c.green() < 90 and c.blue() < 90 and c.alpha() > 128:
                    n += 1
        return n

    check("the tray attention badge carries a glyph, not just amber",
          badge_glyph_pixels() > 0)

    # INV-3: no absolute pixel font size survives, and every size scales. The
    # regex targets the DECLARATION — a plain `"px" in line` test would false-fail
    # on the lines that legitimately keep a px length beside a font-size.
    qss_norm = updater.build_theme(True)
    qss_big = updater.build_theme(True, scale=1.45)
    check("no font size is a hard-coded pixel value",
          re.search(r"font-size:\s*[\d.]+px", qss_norm) is None)
    pts = lambda q: [float(m) for m in re.findall(r"font-size:\s*([\d.]+)pt", q)]  # noqa: E731
    check("every font size is expressed in points", len(pts(qss_norm)) >= 12)
    check("a larger text size really enlarges every font size",
          len(pts(qss_big)) == len(pts(qss_norm))
          and all(b > n for b, n in zip(pts(qss_big), pts(qss_norm), strict=True)))
    check("font sizes derive from the desktop's own default point size",
          abs(pts(qss_norm)[0]
              - QFontInfo(QApplication.instance().font()).pointSizeF() * 1.58) < 0.2)
    check("the badge padding scales with the text too",
          "padding: 3px 13px" in qss_big)

    # INV-4 (revised 2026-07-25 by explicit design decision): focus must NOT draw
    # a border or an outline ring — Qt ignores outline-radius, so a ring renders as
    # a square around our rounded buttons. Focus reuses the hover look instead.
    check("focus draws no outline ring", "outline:" not in qss_norm)
    check("focus still gives a cue by reusing the hover look",
          "QPushButton#GhostBtn:focus" in qss_norm)
    check("the focus rules come after the hover/checked rules they tie with",
          qss_norm.index("QPushButton#GhostBtn:focus")
          > qss_norm.index("QPushButton#GhostBtn:checked"))

    # INV-5: tab order follows VISUAL order (Repositories sits before Recenter).
    chain, node = [], wA.settings_btn
    for _ in range(40):
        node = node.nextInFocusChain()
        if node in (wA.repos_btn, wA.recenter_btn):
            chain.append(node)
        if len(chain) == 2:
            break
    check("tab order reaches Repositories before Recenter",
          chain[:1] == [wA.repos_btn])

    # INV-6: high contrast only ADDS an overlay — the base sheet is untouched.
    qss_hc = updater.build_theme(True, high_contrast=True)
    check("high contrast appends to the base sheet rather than replacing it",
          qss_hc.startswith(qss_norm))
    check("high contrast tells the painted switch to change too",
          "qproperty-highContrast: true" in qss_hc)
    check("the base sheet resets that property explicitly (it is not auto-reverted)",
          "qproperty-highContrast: false" in qss_norm)
    check("high contrast restates the hover rules it must beat on specificity",
          "QPushButton#RunBtn:hover" in qss_hc.replace(qss_norm, ""))

    # INV-7: progress and outcome are spoken. _announce records unconditionally,
    # since QAccessible.isActive() is False offscreen.
    wB = updater.Updater()
    wB.handle_line("@@STEP_BEGIN@@|system|1|3|Updating system packages")
    check("the step being started is announced",
          "Updating system packages" in wB._last_announcement
          and "step 1 of 3" in wB._last_announcement)
    wB.handle_line("@@STEP_END@@|system|ok|3 packages updated")
    check("the step outcome is announced",
          wB._last_announcement == "System packages: 3 installed")
    wB.handle_line("@@DISK@@|warn|/|512 MiB")
    check("a warning banner is announced when it appears",
          wB._last_announcement.startswith("Warning:"))
    wB.proc = QProcess(wB)
    wB._check_mode = False
    wB.on_finished(0, QProcess.ExitStatus.NormalExit)
    check("the final summary is announced", "All done" in wB._last_announcement)
    try:
        wB._announce("plain call must not throw when no reader is listening")
        check("_announce is safe with no screen reader attached", True)
    except Exception as exc:  # noqa: BLE001
        check(f"_announce is safe with no screen reader attached ({exc})", False)

    # A row's outcome must be reachable by keyboard, and must NOT survive into the
    # next run (clear_badge routes through _render_badge for exactly this reason).
    # The size probe's wait is announced, since the button label is invisible to a
    # screen reader (the figure itself can take tens of seconds to arrive).
    wB.rows["system"].size_requested.emit("system")
    check("the download-size wait is announced, and sets the expectation",
          "up to a minute" in wB._last_announcement)
    check("the size button says the wait is expected",
          "up to a minute" in wB.rows["system"].size_btn.text())

    check("the outcome is folded into the switch's description for a screen reader",
          "3 installed" in wB.rows["system"].switch.accessibleDescription())
    wB.rows["system"].clear_badge()
    check("a cleared badge does not leave last run's outcome on the switch",
          "3 installed" not in wB.rows["system"].switch.accessibleDescription())

    # INV-8: both settings persist and apply live, with no restart.
    app_inst = QApplication.instance()
    before = app_inst.styleSheet()
    wA.settings.setValue("text_scale", 1.45)
    updater.apply_app_theme(app_inst)
    check("a text-size change applies live", app_inst.styleSheet() != before)
    wA.settings.setValue("high_contrast", True)
    updater.apply_app_theme(app_inst)
    check("a high-contrast change applies live",
          "qproperty-highContrast: true" in app_inst.styleSheet())
    wA.settings.setValue("text_scale", 1.0)
    wA.settings.setValue("high_contrast", False)
    updater.apply_app_theme(app_inst)
    check("turning high contrast back off really reverts it",
          "qproperty-highContrast: true" not in app_inst.styleSheet())
    check("the text-size button cycles through the offered sizes",
          wA._text_scale_index() == 0)
    wA.on_textsize_clicked()
    check("cycling text size updates both the setting and the label",
          wA._text_scale_index() == 1 and "Large" in wA.textsize_btn.text())
    wA.settings.setValue("text_scale", 1.0)

    print()
    print("======================================")
    print(f"  Passed: {PASS}   Failed: {FAIL}")
    print("======================================")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(_SANDBOX, ignore_errors=True)
    sys.exit(code)
