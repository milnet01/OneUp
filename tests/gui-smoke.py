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
import inspect
import os
import pkgutil
import re
import shutil
import subprocess
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
os.chmod(_notify_mock, 0o755)  # noqa: S103 — a PATH mock must be executable.
os.environ["PATH"] = _BIN + os.pathsep + os.environ.get("PATH", "")

try:
    from PySide6.QtCore import QPoint, QProcess, Qt, QTimer
    from PySide6.QtGui import QAccessible, QCloseEvent, QFont, QFontInfo
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QFrame,
        QLabel,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # PySide6 absent — skip, don't fail the suite.
    print(f"  SKIP - PySide6 not installed ({exc})")
    sys.exit(77)

REPO = Path(__file__).resolve().parent.parent
# The repo root must be importable BEFORE updater.py is loaded. Run as
# `python3 tests/gui-smoke.py`, sys.path[0] is tests/, so the root shim's
# `from oneup.gui.app import main` would raise ModuleNotFoundError. Inserting the
# root here is the whole of INV-1 (docs/specs/ONEUP-0034-gui-modules.md); a
# failure to import `oneup` then fails the suite rather than skipping it, because
# the ImportError handler above covers the PySide6 imports only.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load_updater():
    """Load the window the way a user launches it — through the root shim.

    Deliberately still the root `updater.py` and not `oneup.gui.app` directly:
    that file is what the desktop entry, the RPM wrapper, the AppImage and every
    hand-made launcher name, so loading it is what proves the entry point still
    works. Executing it imports the whole package, so the modules imported below
    are the same objects this returns a view of.
    """
    spec = importlib.util.spec_from_file_location("updater", REPO / "updater.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The window's subsystems, each reached through its own module. A name is NEVER
# bound by value here: the redirects below (paths.RUN_STATE, paths.STOP_REQUEST,
# paths.ZYPP_PACKAGE_CACHE) work only because every reader goes through the
# module too, and a `from … import` on either side would leave the redirect
# landing somewhere nobody reads — green suite, real file deleted
# (docs/specs/ONEUP-0034-gui-modules.md §4.4, INV-2).
from oneup.gui import (  # noqa: E402 — must follow the sandbox + sys.path block above.
    app as gui_app,  # `app` is the QApplication in main(); the module needs its own name
)
from oneup.gui import (  # noqa: E402 — same reason.
    app_update,
    auth,
    autostart,
    banners,
    contrast,
    diagnostics,
    markers,
    paths,
    placement,
    repos,
    rollback,
    run,
    settings_dialog,
    theme,
    toggle_switch,
    tray,
    window,
)

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


_PATCHES = []


def _patch(mod, name, fn):
    """Replace a module-level function for the scenario in hand.

    The split turned the window's subsystem methods into module-level functions
    taking the window (docs/specs/ONEUP-0034-gui-modules.md §4.2), so setting an
    attribute on the instance intercepts nothing — every caller goes through the
    module now. Patching the module is what a spy means here, and because that
    is process-wide it has to be undone: _unpatch_all() closes each scenario, in
    reverse order, so a stub can never leak into the next one.
    """
    _PATCHES.append((mod, name, getattr(mod, name)))
    setattr(mod, name, fn)


def _unpatch_all():
    while _PATCHES:
        mod, name, orig = _PATCHES.pop()
        setattr(mod, name, orig)


def _wait_for_notify(timeout: float = 5.0) -> bool:
    """Poll for the mock notify-send to record a call (Popen is asynchronous).

    The deadline is racing two real process spawns (Popen → bash → the mock script
    writing to disk), not an in-process signal, so it is set well clear of the time
    that takes on an idle box. Timing out fails the caller's check red rather than
    green, so a generous ceiling costs nothing but a loaded runner's patience.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(_NOTIFY_LOG) and os.path.getsize(_NOTIFY_LOG) > 0:
            return True
        time.sleep(0.02)
    return False


def main() -> int:
    # The shim is loaded for what loading it PROVES — that the thing every launcher
    # names still starts the app — not for anything read off the module afterwards;
    # the package modules imported above are where the names live now.
    _load_updater()

    # Updater.__init__ asks GitHub whether a newer OneUp exists, and this file builds
    # 56 windows — so an unstubbed run fires 56 unauthenticated requests at
    # api.github.com, whose limit is 60 an hour PER ADDRESS. A few runs therefore
    # exhaust the budget the user's own "Check for updates" button needs, and the
    # suite fails outright with no network (ONEUP-0090). Nothing here asserts on the
    # check or its reply handler, so stubbing it costs no coverage. Must happen
    # before the first Updater() below.
    app_update._check_app_update = lambda self, manual=False: None

    # Same argument, same place, for the same reason (ONEUP-0099). Every Updater() runs
    # _query_auth_status, whose settle can now reach _stand_down_autoupdate — and that
    # calls the REAL _remove_user_timer, which shells out to `systemctl --user disable
    # --now` against the developer's own session. Across 56 constructions, "the scenarios
    # that care are careful" is not the same property as "the suite cannot touch the
    # machine" (testing.md §2). Scenarios that assert on it re-enable it locally with a spy.
    _real_stand_down = auth._stand_down_autoupdate
    auth._stand_down_autoupdate = lambda self, lead="": None

    # Likewise the single-instance socket: left alone, the guard would connect to the
    # user's LIVE OneUp and pop its window open mid-test (testing.md §2).
    os.environ["ONEUP_INSTANCE_NAME"] = f"OneUp-test-{os.getpid()}"

    app = QApplication.instance() or QApplication([])
    app  # noqa: B018 — keep a reference so it isn't GC'd mid-test.

    # --- 1. A malformed / spliced marker never throws out of the read slot ------
    w = window.Updater()
    for bad in ("@@STEP_BEGIN@@|system",          # too few fields
                "@@STEP_BEGIN@@|system|x|3|Label",  # non-numeric index
                "@@ -1,4 +1,4 @@ a diff hunk",       # looks like a marker, isn't
                "@@NOPE@@ no pipe at all",
                "an ordinary log line"):
        try:
            run.handle_line(w, bad)
            check(f"malformed line handled: {bad[:22]!r}", True)
        except Exception as exc:  # noqa: BLE001 — any throw is the failure.
            check(f"malformed line handled: {bad[:22]!r} ({exc})", False)

    # --- 2. A real run's markers land the right per-row badges + state ----------
    w = window.Updater()
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
        run.handle_line(w, line)

    check("system row badge shows outcome + timing",
          w.rows["system"].badge.text() == "3 installed  ·  42s")
    check("_format_duration formats seconds", markers._format_duration(42) == "42s")
    check("_format_duration formats minutes", markers._format_duration(65) == "1m 5s")
    check("_format_duration handles sub-second", markers._format_duration(0) == "<1s")
    check("flatpak row badge = 'Up to date'", w.rows["flatpak"].badge.text() == "Up to date")
    check("firmware skip badge = 'Not installed'",
          w.rows["firmware"].badge.text() == "Not installed")
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
    wP = window.Updater()
    run.handle_line(wP, "@@STEP_BEGIN@@|system|1|5|Updating system packages")
    caption = wP.bar.format()
    # zypper's preload phase gives no total, so the GUI must show a running tally
    # rather than inventing a denominator it doesn't have.
    run.handle_line(wP, "@@PROGRESS@@|system|34|0|download")
    check("unknown total shows a running tally, not a fake ratio",
          "34 so far" in wP.status.text() and "of 0" not in wP.status.text())
    check("the bar keeps the step caption and adds the detail",
          caption in wP.bar.format() and "34 so far" in wP.bar.format())
    # ONEUP-0163: the caption is a label under the bar, never text on the fill.
    # Centred on `accent` it measured 1.63:1 against `status`, and no accent a
    # theme would want reads under body text. Both halves are asserted: the bar
    # must draw nothing, AND the label must carry what `format()` reports —
    # either alone passes with the caption invisible or with it in two places.
    check("the bar paints no caption on its fill", not wP.bar.isTextVisible())
    check("the caption label carries what the bar reports",
          wP.bar_caption.text() == wP.bar.format() and "34 so far" in wP.bar_caption.text())
    run.handle_line(wP, "@@PROGRESS@@|system|12|141|download")
    check("a counted download reads as 'Downloading 12 of 141 packages'",
          wP.status.text() == "Downloading 12 of 141 packages…")
    check("the row badge tracks progress", wP.rows["system"].badge.text() == "12/141")
    run.handle_line(wP, "@@PROGRESS@@|system|7|141|install")
    check("the install phase says Installing", wP.status.text() == "Installing 7 of 141 packages…")
    # One announcement per phase, not per package: 141 spoken lines would bury
    # everything else, but silence through the longest phase is what looked hung.
    check("a phase change is announced once", wP._last_announcement == "Installing packages.")
    wP._last_announcement = ""
    run.handle_line(wP, "@@PROGRESS@@|system|8|141|install")
    check("further packages in the same phase are not re-announced",
          wP._last_announcement == "")
    # Same splice-safety contract as STEP_BEGIN: merged stdout/stderr can cut a marker.
    for bad in ("@@PROGRESS@@|system",
                "@@PROGRESS@@|system|x|141|download",
                "@@PROGRESS@@|system|12|y|download"):
        try:
            run.handle_line(wP, bad)
            check(f"malformed progress marker handled: {bad[-14:]!r}", True)
        except Exception as exc:  # noqa: BLE001 — any throw is the failure.
            check(f"malformed progress marker handled ({exc})", False)
    # A later step's caption must replace the previous one, not accumulate.
    run.handle_line(wP, "@@STEP_BEGIN@@|cache|5|5|Cleaning package cache")
    check("a new step resets the progress caption",
          "141" not in wP.bar.format() and "Cleaning package cache" in wP.bar.format())

    # --- @@REFRESH@@ and the liveness line (ONEUP-0048) -------------------------
    # A run once sat 26 minutes on one repository whose server was delivering an 18 MB
    # index at 930 B/s, with nothing on screen the whole time: zypper reports that phase
    # as dots with no line ending, so there was never a complete line to draw and a
    # working run was indistinguishable from a frozen one.
    # Weigh an empty directory, not the machine's real package cache: _tick_activity
    # falls back to `cache_bytes() - _dl_base` during a download, so whatever zypper
    # happened to leave in /var/cache/zypp/packages would otherwise decide the figures
    # asserted below. It bit for real — 44 MB of leftovers turned "40 MB of 379 MB"
    # into "44 MB of 379 MB" and the suite went red on an unrelated commit (ONEUP-0055).
    _live_cache = tempfile.mkdtemp()
    _orig_live_cache = paths.ZYPP_PACKAGE_CACHE
    paths.ZYPP_PACKAGE_CACHE = Path(_live_cache)
    try:
        wL = window.Updater()
        wL._run_active = True
        # The liveness line has its own flag since it must also run on a
        # --check, where _run_active is False by design.
        wL._liveness_active = True
        run._reset_activity(wL)        # a real run always baselines before markers arrive
        run.handle_line(wL, "@@STEP_BEGIN@@|system|1|5|Updating system packages")
        run.handle_line(wL, "@@REFRESH@@|6|9|games")
        check("the source being fetched is named, with its position",
              wL.status.text() == "Checking for updates from games (6 of 9 sources)…")
        check("the bar keeps the step caption and adds the source",
              "Updating system packages" in wL.bar.format() and "games" in wL.bar.format())
        check("the liveness line names what is being waited on",
              "Fetching games" in wL.activity.text())
        check("the liveness line is visible during a run", wL.activity.isVisibleTo(wL))
        # Bytes: the download phase is the only place in a run where a figure exists at all.
        run.handle_line(wL, "@@PROGRESS@@|system|12|141|download|41943040|397410304")
        check("the download says how much of how much", "40 MB of 379 MB" in wL.activity.text())
        check("the byte total is remembered", wL._dl_total == 397410304)
        # A rate needs both movement and elapsed time to divide by.
        run.handle_line(wL, "@@PROGRESS@@|system|24|141|download|83886080|397410304")
        wL._dl_at -= 10
        run._tick_activity(wL)
        check("a rate appears once bytes have moved", "/s" in wL.activity.text())
        # Going quiet is the signal that actually matters, and must be said in those terms.
        wL._activity_at = time.monotonic() - (run.STALL_SECONDS + 5)
        run._tick_activity(wL)
        check("a stalled server is named as such", "may have stalled" in wL.activity.text())
        check("and the user is told stopping is safe", "safe" in wL.activity.text())
        check("the stall is announced once", "No response" in wL._last_announcement)
        wL._last_announcement = ""
        run._tick_activity(wL)
        check("a continuing stall is not re-announced every tick", wL._last_announcement == "")
        # Output arriving again means slow, not stalled — the wording has to go back.
        wL._activity_at = time.monotonic()
        run._tick_activity(wL)
        check("output arriving clears the stall wording",
              "may have stalled" not in wL.activity.text())
        # A new step is a new wait and a new download; neither figure may carry over.
        run.handle_line(wL, "@@STEP_BEGIN@@|flatpak|2|5|Updating Flatpak apps")
        check("a new step drops the previous source", "games" not in wL.activity.text())
        check("a new step resets the byte counters", wL._dl_bytes == 0 and wL._dl_total == 0)
        # Same splice-safety contract as PROGRESS: merged stdout/stderr can cut a marker.
        for bad in ("@@REFRESH@@|6", "@@REFRESH@@|x|9|games", "@@REFRESH@@|6|y|games",
                    "@@PROGRESS@@|system|1|2|download|notanumber"):
            try:
                run.handle_line(wL, bad)
                check(f"malformed liveness marker handled: {bad[-12:]!r}", True)
            except Exception as exc:  # noqa: BLE001 — any throw is the failure.
                check(f"malformed liveness marker handled ({exc})", False)
        run.on_finished(wL, 0, None)
        check("the liveness line goes away when the run ends", not wL.activity.isVisibleTo(wL))
    finally:
        # Matches the identical block below: a throw in the body must not leave
        # ZYPP_PACKAGE_CACHE pointing at a directory that is about to vanish.
        paths.ZYPP_PACKAGE_CACHE = _orig_live_cache
        shutil.rmtree(_live_cache, ignore_errors=True)

    # zypper's prefetch phase reports no sizes and no counter — one line per finished
    # package and nothing else — so the figure has to come from weighing its package
    # cache. That is world-readable, so no root is involved.
    cache_dir = tempfile.mkdtemp()
    _orig_cache = paths.ZYPP_PACKAGE_CACHE
    paths.ZYPP_PACKAGE_CACHE = Path(cache_dir)
    try:
        check("an empty cache weighs nothing", diagnostics.cache_bytes() == 0)
        wC = window.Updater()
        wC._run_active = True
        # The liveness line has its own flag since it must also run on a
        # --check, where _run_active is False by design.
        wC._liveness_active = True
        run._reset_activity(wC)        # baseline taken before anything is fetched
        run.handle_line(wC, "@@STEP_BEGIN@@|system|1|5|Updating system packages")
        run.handle_line(wC, "@@PROGRESS@@|system|1|0|download|0|90596966")
        check("a prefetch tally still invents no denominator",
              "1 so far" in wC.status.text() and "of 0" not in wC.status.text())
        (Path(cache_dir) / "pkg.rpm").write_bytes(b"x" * (20 * 1024 * 1024))
        run._tick_activity(wC)
        check("the download is measured even though zypper reported no size",
              "20 MB of 86 MB" in wC.activity.text())
        # Packages already cached sit inside the baseline: zypper won't re-fetch them, so
        # counting them would overstate progress and flatter the rate.
        wC2 = window.Updater()
        wC2._run_active = True
        # The liveness line has its own flag since it must also run on a
        # --check, where _run_active is False by design.
        wC2._liveness_active = True
        run._reset_activity(wC2)       # baseline now includes the 20 MB above
        run.handle_line(wC2, "@@PROGRESS@@|system|1|0|download|0|90596966")
        run._tick_activity(wC2)
        check("already-cached packages are excluded from this run's figure",
              "20 MB" not in wC2.activity.text())
    finally:
        paths.ZYPP_PACKAGE_CACHE = _orig_cache
        shutil.rmtree(cache_dir, ignore_errors=True)

    # The liveness line must arm on a CHECK as well as a run. A check IS the
    # metadata-refresh phase ONEUP-0048 was written for, and its progress bar is
    # indeterminate, so it animates whether or not the engine is still alive — the
    # liveness line is the only thing that can tell the user apart from a hang.
    # The fixtures above set the flag by hand, so only this proves _reset_for_run
    # actually sets it; gating on _run_active looked right and was dead here.
    wK = window.Updater()
    run._reset_for_run(wK, ["system"], check=True)
    check("a check arms the liveness line", wK._liveness_active is True)
    check("a check still leaves the thin-action guard down", wK._run_active is False)
    run._reset_for_run(wK, ["system"], check=False)
    check("a full run arms both", wK._liveness_active is True and wK._run_active is True)

    # --- dialogs open over the window, on Wayland too (ONEUP-0049) --------------
    # Qt's move() is accepted and silently ignored on Wayland (the compositor owns
    # placement), which is why every dialog opened away from the window. X11 still moves
    # directly; Wayland has to ask KWin, so the one thing to prove here is that each
    # session type takes its own path and neither throws.
    _orig_session = os.environ.get("XDG_SESSION_TYPE", "")
    try:
        os.environ["XDG_SESSION_TYPE"] = "x11"
        check("the session type is read from the environment", not placement._on_wayland())
        host = QWidget()
        host.setGeometry(100, 100, 800, 600)
        dlg = QDialog(host)
        dlg.resize(200, 100)
        placement.center_on_parent(dlg)
        check("on X11 a dialog is moved onto its parent's centre",
              abs(dlg.frameGeometry().center().x() - host.frameGeometry().center().x()) <= 2
              and abs(dlg.frameGeometry().center().y() - host.frameGeometry().center().y()) <= 2)
        os.environ["XDG_SESSION_TYPE"] = "wayland"
        check("Wayland is detected", placement._on_wayland())
        moved_to = dlg.pos()
        placement.center_on_parent(dlg)   # queues a KWin request; must not move it itself
        check("on Wayland placement is left to the compositor, not a futile move()",
              dlg.pos() == moved_to)
    finally:
        os.environ["XDG_SESSION_TYPE"] = _orig_session

    # --- Stop button (ONEUP-0047) -----------------------------------------------
    # Stop is deliberately cooperative: it asks, and the engine honours it at a safe
    # point. The UI must promise exactly that and never imply an instant abort.
    wS = window.Updater()
    check("Stop is hidden while idle", not wS.stop_btn.isVisibleTo(wS))
    check("Stop explains it waits for the current step",
          "after the current step" in wS.stop_btn.toolTip()
          and "never cut off half-way" in wS.stop_btn.toolTip())
    stop_dir = tempfile.mkdtemp()
    orig_stop, orig_rs = paths.STOP_REQUEST, paths.RUN_STATE
    paths.STOP_REQUEST = Path(stop_dir) / "stop.request"
    paths.RUN_STATE = Path(stop_dir) / "run.state"
    try:
        wS._run_active, wS._check_mode = True, False
        wS.set_controls_enabled(False)
        check("Stop appears once a real run is going", wS.stop_btn.isVisibleTo(wS))
        run.request_stop(wS)
        check("asking to stop creates the file the engine watches",
              paths.STOP_REQUEST.exists())
        check("the button reflects that the request is in", wS.stop_btn.text() == "Stopping…")
        check("it cannot be clicked twice", not wS.stop_btn.isEnabled())
        check("the status says what will actually happen",
              "after the current step" in wS.status.text())
        # A stopped run must claim neither success nor failure.
        run.handle_line(wS, "@@DONE@@|stopped")
        run.on_finished(wS, 0, None)
        check("a stopped run is reported as stopped", wS.bar.format() == "Stopped")
        check("a stopped run never says 'All done'", "All done" not in wS.status.text())
        check("a stopped run says what survived",
              "still installed" in wS.status.text())
        # A --check has nothing to stop.
        wS._run_active, wS._check_mode = True, True
        wS.set_controls_enabled(False)
        check("Stop is not offered for a read-only check", not wS.stop_btn.isVisibleTo(wS))
    finally:
        paths.STOP_REQUEST, paths.RUN_STATE = orig_stop, orig_rs
        shutil.rmtree(stop_dir, ignore_errors=True)

    # --- attaching to a run started by an earlier window (ONEUP-0045) -----------
    # Runs outlive the window on purpose, so a fresh window must find one in flight and
    # follow its log rather than offering a Run that could only fail on the lock.
    import subprocess as _sp
    attach_dir = tempfile.mkdtemp()
    attach_log = os.path.join(attach_dir, "run.log")
    # A stand-in engine: alive, so the pid check passes, and writing real marker lines.
    holder = _sp.Popen(["sleep", "60"])  # noqa: S607 — fixed argv.
    with open(attach_log, "w") as fh:
        fh.write("@@STEP_BEGIN@@|system|1|2|Updating system packages\n"
                 "@@PROGRESS@@|system|12|141|download\n")
    orig_state = paths.RUN_STATE
    paths.RUN_STATE = Path(attach_dir) / "run.state"
    paths.RUN_STATE.write_text(f"{holder.pid}\n{attach_log}\nsystem,cache\n0\n")
    try:
        wA = window.Updater()
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
        holder.terminate()
        holder.wait()
        try:
            wA._poll_attached_run()
            check("a followed run finishing is handled without a process object", True)
        except Exception as exc:  # noqa: BLE001 — any throw is the failure.
            check(f"a followed run finishing is handled ({exc})", False)
        check("the followed run's own verdict is used", wA._run_active is False)
        check("the record is cleared once the followed run ends",
              not paths.RUN_STATE.exists())
        # A stale record (pid long gone) must not lock a fresh window out.
        paths.RUN_STATE.write_text(f"{holder.pid}\n{attach_log}\nsystem\n0\n")
        wB = window.Updater()
        check("a stale record does not lock the app", wB._run_active is False)
        check("a stale record is deleted", not paths.RUN_STATE.exists())
    finally:
        if holder.poll() is None:
            holder.terminate()
            holder.wait()
        paths.RUN_STATE = orig_state
        shutil.rmtree(attach_dir, ignore_errors=True)

    # --- quitting mid-run warns first (ONEUP-0042) ------------------------------
    # The dialog itself is modal, so the decision is tested and _ask_quit_during_run
    # is stubbed — that split is why the method exists separately.
    wQ = window.Updater()
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
    auth._set_auth_checked(w, True)
    check("auth toggle reflects 'on' without firing grant",
          w.auth_btn.isChecked() and w.auth_btn.text() == "Passwordless: on")
    auth._set_auth_checked(w, False)
    check("auth toggle reflects 'off'",
          not w.auth_btn.isChecked() and w.auth_btn.text() == "Passwordless: off")

    class _StubProc:  # stands in for the finished QProcess, returns canned stdout
        def __init__(self, text): self._b = text.encode()
        def readAllStandardOutput(self): return self._b
    auth._on_auth_status_finished(w, _StubProc("log noise\n@@AUTH@@|on\n"))
    check("status marker 'on' turns the toggle on", w.auth_btn.isChecked())
    auth._on_auth_status_finished(w, _StubProc("@@AUTH@@|off\n"))
    check("status marker 'off' turns the toggle off", not w.auth_btn.isChecked())

    # A REPO marker names the duplicate URL and flips the banner button to the
    # repo manager.
    w2 = window.Updater()
    run.handle_line(w2, "@@REPO@@|warn|duplicate|http://x.example/repo")
    check("repo warning names the duplicate URL",
          "http://x.example/repo" in w2.warn_label.text())
    check("repo warning arms the repo-manager action", w2._warn_repo_dup is True)
    check("repo warning button becomes 'Manage repositories…'",
          w2.warn_btn.text() == "Manage repositories…")

    # A SNAPSHOTS pre-flight advisory names the count and arms the "thin" action.
    w3 = window.Updater()
    run.handle_line(w3, "@@SNAPSHOTS@@|warn|30")
    check("snapshot advisory arms the thin action", w3._warn_snapshots is True)
    check("snapshot advisory captures the count", w3._snapshot_count == 30)
    check("snapshot advisory names the count", "30 system restore points" in w3.warn_label.text())
    check("snapshot advisory button becomes 'Thin snapshots…'",
          w3.warn_btn.text() == "Thin snapshots…")
    check("snapshot advisory shows the warning banner", w3.warn_banner.isVisibleTo(w3))

    # SNAPSHOT_ITEM markers feed the rollback picker (ONEUP-0020): well-formed ids
    # are captured, a non-numeric id is dropped, and the dialog lists them
    # newest-first with the pre-update snapshot pre-selected.
    w4 = window.Updater()
    for line in ("@@SNAPSHOT@@|100",
                 "@@SNAPSHOT_ITEM@@|98|2026-07-20 09:00:00|OneUp pre-update 2026-07-20 09:00",
                 "@@SNAPSHOT_ITEM@@|99|2026-07-22 09:00:00|zypp(zypper)",
                 "@@SNAPSHOT_ITEM@@|100|2026-07-24 09:00:00|OneUp pre-update 2026-07-24 09:00",
                 "@@SNAPSHOT_ITEM@@|bogus|x|y"):
        run.handle_line(w4, line)
    check("rollback picker captures well-formed snapshots", len(w4._snapshots) == 3)
    check("rollback picker drops a non-numeric snapshot id",
          all(sid.isdigit() for sid, _, _ in w4._snapshots))
    dlg = rollback.RollbackDialog(w4, w4._snapshots, w4._snapshot)
    check("picker lists the newest snapshot first", dlg.list.item(0).data(Qt.UserRole) == "100")
    check("picker pre-selects the pre-update snapshot", dlg.selected_id() == "100")
    dlg.list.setCurrentRow(dlg.list.count() - 1)   # choose the oldest listed
    check("picker returns the chosen snapshot id", dlg.selected_id() == "98")
    dlg.reject()

    # --- 3. on_finished promotes the accumulated state into the right banners ---
    w.proc = QProcess(w)   # on_finished releases self.proc; give it a real one.
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)
    check("reboot banner shown after a real install", w.reboot_banner.isVisibleTo(w))
    check("rollback offered after a system change", w.rollback_btn.isVisibleTo(w))
    check("retry offered after a failed step", w.retry_btn.isVisibleTo(w))
    # The window is never shown (not active), so a finished run notifies. The mock
    # notify-send on PATH records the call; Popen is async, so poll briefly.
    check("finished run fires a desktop notification", _wait_for_notify())

    # --- 4. A package-only change offers services, not a reboot ----------------
    w = window.Updater()
    for line in ("@@STEP_END@@|system|ok|packages updated",
                 "@@INSTALLED@@|2|yes|no",
                 "@@SERVICES@@|foo.service bar.service",
                 "@@REBOOT@@|no"):
        run.handle_line(w, line)
    w.proc = QProcess(w)
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)
    check("services banner shown for a package-only change", w.services_banner.isVisibleTo(w))
    check("no reboot banner for a package-only change", not w.reboot_banner.isVisibleTo(w))

    # --- 4a. The services button actually restarts them (ONEUP-0110) -----------
    # Regression, reported 2026-08-18: clicking "Restart services" did nothing at all.
    # restart_services() guards what reaches a root systemctl, and the guard demanded a
    # "name.suffix" shape — but `zypper ps -sss` prints BARE unit names, because libzypp
    # captures the name BEFORE ".service" when it reads the cgroup. So every real token
    # was filtered out, svcs came back empty, and the handler returned before doing
    # anything: no dialog, no error, no log line. The banner still appeared, because its
    # branch reads the raw marker string while the handler reads the filtered one.
    #
    # Scenario 4 above feeds "foo.service bar.service" — a shape the engine never emits —
    # so it passed throughout. This one feeds what the engine really sends. Do not delete:
    # it is the only assertion that the button does anything, and the last two checks are
    # what stop the fix widening the guard into an argument-injection hole.
    #
    # Every name here is deliberately one ONEUP-0111 considers SAFE — `getty@tty1` carries
    # the '@' coverage that `user@1000` used to, without being the user's own session
    # manager. Feeding a session-critical name here would assert the behaviour ONEUP-0111
    # exists to prevent; that split is covered by the scenario below.
    w = window.Updater()
    for line in ("@@STEP_END@@|system|ok|packages updated",
                 "@@INSTALLED@@|2|yes|no",
                 "@@SERVICES@@|sshd cups getty@tty1 avahi-daemon -f",
                 "@@REBOOT@@|no"):
        run.handle_line(w, line)
    launched = []
    _orig_question = QMessageBox.question
    _orig_detached = QProcess.startDetached
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QProcess.startDetached = staticmethod(
        lambda prog, args=None, *a, **k: (launched.append((prog, list(args or []))), True)[1])
    try:
        banners.restart_services(w)
    finally:
        QMessageBox.question = _orig_question
        QProcess.startDetached = _orig_detached
    check("restart services launches something for bare unit names", bool(launched))
    check("restart services passes every bare unit name to systemctl",
          bool(launched)
          and launched[0][1][:2] == ["systemctl", "restart"]
          and ["sshd", "cups", "getty@tty1", "avahi-daemon"] == [
              a for a in launched[0][1][2:]])
    check("restart services still drops an option-shaped token",
          all("-f" not in call[1] for call in launched))
    check("restart services hides the banner once it has launched",
          bool(launched) and not w.services_banner.isVisibleTo(w))

    # --- 4a-ii. A session-critical service is never restarted (ONEUP-0111) -----
    # Asked by the user the day ONEUP-0110 made this button work: what if it restarts
    # something that logs you out? It would have. `zypper ps -sss` reports whatever holds
    # a deleted library, and after a glibc/systemd/Qt/dbus update that includes the
    # processes that ARE the session — display-manager tears down the desktop, user@<uid>
    # is the user's whole systemd session (OneUp included, so the window dies mid-restart),
    # dbus and systemd-logind break a running session, and polkit is the agent that just
    # authorised the pkexec carrying the command.
    #
    # Decided with the user: never restart these, on any path. Not behind a confirmation,
    # not behind a warning. The safe ones are restarted and a reboot is advised for the
    # rest. These assertions are what stop that being softened later.
    def _run_restart(marker_payload, click=True):
        """Feed a SERVICES payload, accept the dialog, and return what was launched.

        `click=False` stops at the drawn banners, which is the state ONEUP-0115 is
        about: what the window OFFERS before anything is clicked.
        """
        win = window.Updater()
        for ln in ("@@STEP_END@@|system|ok|packages updated",
                   "@@INSTALLED@@|2|yes|no",
                   f"@@SERVICES@@|{marker_payload}",
                   "@@REBOOT@@|no"):
            run.handle_line(win, ln)
        win.proc = QProcess(win)
        run.on_finished(win, 0, QProcess.ExitStatus.NormalExit)   # draws the banner
        if not click:
            return win, []
        calls = []
        _q, _i, _d = (QMessageBox.question, QMessageBox.information,
                      QProcess.startDetached)
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        QMessageBox.information = staticmethod(lambda *a, **k: 0)
        QProcess.startDetached = staticmethod(
            lambda prog, args=None, *a, **k: (calls.append([prog, *(args or [])]), True)[1])
        try:
            banners.restart_services(win)
        finally:
            (QMessageBox.question, QMessageBox.information,
             QProcess.startDetached) = _q, _i, _d
        return win, [a for call in calls for a in call]

    CRITICAL = ["display-manager", "user@1000", "dbus", "systemd-logind", "polkit"]

    _w, args = _run_restart("sshd cups " + " ".join(CRITICAL))
    check("mixed list still restarts the safe services",
          "sshd" in args and "cups" in args)
    check("mixed list restarts NO session-critical service",
          not any(c in args for c in CRITICAL))

    _w2, args2 = _run_restart(" ".join(CRITICAL))
    check("an all-critical list restarts no service at all",
          not any(c in args2 for c in CRITICAL) and "restart" not in args2)

    # --- 4a-iii. Where the advice is a reboot, OFFER the reboot (ONEUP-0115) --
    # Asked by the user 2026-08-19. ONEUP-0111 refuses to restart a session-critical
    # unit and says a reboot is the honest advice; where the WHOLE list is critical
    # that left the services banner up over a button whose only outcome was an
    # information dialog naming units the app will never touch. The reboot the dialog
    # recommends must be the thing on offer, not something the user has to go and find.
    _w3, _ = _run_restart(" ".join(CRITICAL), click=False)
    check("an all-critical list offers the reboot banner",
          _w3.reboot_banner.isVisibleTo(_w3))
    check("an all-critical list does NOT offer the services banner",
          not _w3.services_banner.isVisibleTo(_w3))

    _w4, _ = _run_restart("sshd cups " + " ".join(CRITICAL), click=False)
    check("a mixed list offers the services banner for the safe half",
          _w4.services_banner.isVisibleTo(_w4))
    check("a mixed list ALSO offers the reboot for the rest",
          _w4.reboot_banner.isVisibleTo(_w4))
    check("a mixed list counts only the safe services in the services banner",
          "2 service(s)" in _w4.services_label.text())

    _w5, _ = _run_restart("sshd cups", click=False)
    check("an all-safe list offers no reboot", not _w5.reboot_banner.isVisibleTo(_w5))

    # The button on the all-critical path reboots rather than dead-ending in an
    # information dialog. QMessageBox.question is patched to Yes above.
    check("the all-critical path offers a reboot instead of a dead end",
          "systemctl" in args2 and "reboot" in args2)

    # --- 4b. A reason-bearing REBOOT marker names the culprit in the banner ----
    w = window.Updater()
    for line in ("@@STEP_END@@|system|ok|7 packages updated",
                 "@@INSTALLED@@|7|yes|no",
                 "@@REBOOT@@|yes|a new kernel and your NVIDIA graphics driver were installed"):
        run.handle_line(w, line)
    check("reboot reason captured from the marker",
          w._reboot_reason == "a new kernel and your NVIDIA graphics driver were installed")
    w.proc = QProcess(w)
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)
    check("reboot banner names the kernel + driver, keeping NVIDIA casing",
          "NVIDIA graphics driver" in w.reboot_label.text()
          and w.reboot_label.text().lstrip("⚠ ").startswith("A new kernel"))

    # --- 5. --check mode summarises available updates without banners ----------
    w = window.Updater()
    w._check_mode = True
    for line in ("@@CHECK@@|system|2",
                 "@@CHECK@@|flatpak|0",
                 "@@CHECK@@|TOTAL|2"):
        run.handle_line(w, line)
    check("check: system row shows availability", w.rows["system"].badge.text() == "2 available")
    check("check: flatpak row shows up to date", w.rows["flatpak"].badge.text() == "up to date")
    w.proc = QProcess(w)
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)
    check("check: no reboot banner", not w.reboot_banner.isVisibleTo(w))

    # --- 5b. CHECK_ITEM: the expandable per-package preview ---------------------
    # CHECK_ITEM was the one marker in handle_marker's dispatch that no GUI scenario fed,
    # so nothing proved the window still builds the detail rows --check emits for it.
    wI = window.Updater()
    wI._check_mode = True
    run.handle_line(wI, "@@CHECK_ITEM@@|system|bash|5.2.21|5.2.37")
    run.handle_line(wI, "@@CHECK_ITEM@@|system|zypper")
    _detail = wI.rows["system"]._items_label.text()
    check("a changed package lands in the detail panel with both versions",
          "bash" in _detail and "5.2.21" in _detail and "5.2.37" in _detail)
    check("a package with no version pair still lists its name",
          any(ln.strip() == "zypper" for ln in _detail.splitlines()))
    check("the detail disclosure appears once there is something to show",
          not wI.rows["system"].disclosure.isHidden())

    # --- 5c. @@HINT@@ goes through the parser, not straight into _hints ---------
    # Every other hint scenario assigns w._hints directly, so the dispatch line that
    # actually populates it was never exercised by anything.
    wH = window.Updater()
    run.handle_line(wH, "@@HINT@@|A repository signing key is out of date.")
    check("a @@HINT@@ line is parsed into _hints",
          wH._hints == ["A repository signing key is out of date."])

    # --- 5d. the download-size side channel ------------------------------------
    # A separate QProcess from the main run, with its own parser. The engine half is
    # covered in tests/run-tests.sh; this is the window half.
    wS = window.Updater()
    wS._size_buf = ""
    wS._size_proc = _StubProc("weighing things up\n@@SIZE@@|system|412 MB\n")
    run._on_size_output(wS)
    check("a SIZE marker reaches the system row",
          "412 MB" in wS.rows["system"].size_result.text())
    # isVisibleTo(row) would be False here whatever set_size_result did — size_btn lives
    # inside the collapsed `details` frame, so the row is the wrong ancestor to ask about.
    # Ask about the frame it actually sits in, which isolates the button's own visibility.
    check("a SIZE marker retires the 'Show download size' link",
          not wS.rows["system"].size_btn.isVisibleTo(wS.rows["system"].details))
    check("a SIZE marker records that the row now carries a size",
          wS.rows["system"].has_size())
    check("a non-marker line from the size probe is logged",
          "weighing things up" in wS.log.toPlainText())

    # Exit 0 with no SIZE marker means the solver found nothing to fetch — but a
    # non-zero exit must NEVER be reported as "nothing to download". Same
    # never-claim-what-you-didn't-earn rule the engine's step tests enforce.
    wS0 = window.Updater()
    run._on_size_finished(wS0, 0, None)
    check("size probe exiting 0 with no marker reports nothing to download",
          wS0.rows["system"].size_result.text() == "Nothing to download")
    wS1 = window.Updater()
    run._on_size_finished(wS1, 1, None)
    check("a failed size probe never claims a size it didn't earn",
          not wS1.rows["system"].has_size())

    # --- 5d-i. ONEUP-0044: the held engine, and what Update does with it --------
    # The engine half is covered in tests/run-tests.sh; this is the window half of
    # §4.5's three-state table. Nothing here starts a real engine: what is being
    # asserted is which branch Update takes, and that is decided by `_size_proc`'s
    # state and by `hold.state`'s line 1.
    class _Sig:                       # a signal that records nothing and refuses nothing
        def connect(self, *_a): pass
        def disconnect(self, *_a): pass

    class _SizeProc:
        def __init__(self, pid, running=True):
            self._pid, self._running = pid, running
            self.readyReadStandardOutput = _Sig()
            self.finished = _Sig()
            self.errorOccurred = _Sig()

        def state(self):
            return QProcess.Running if self._running else QProcess.NotRunning

        def processId(self): return self._pid

    # INV-7: expiry, a killed engine and a stale hold.state must all degrade to today's
    # behaviour, never to an error. The failure being guarded is the opposite — a window
    # that writes go.request and waits for a process that is not there, which the user
    # experiences as a dead Update button.
    wF = window.Updater()
    wF._size_proc = _SizeProc(4242, running=False)
    _launched = []
    _real_launch = run._launch
    run._launch = lambda w, st, check, **kw: _launched.append((list(st), check))
    try:
        run.start_run(wF)
        check("INV-7 Update starts a fresh engine when the preview has already exited",
              len(_launched) == 1 and _launched[0][1] is False)
    finally:
        run._launch = _real_launch

    # §6, two rows at once: a hold.state a SIGKILLed engine left behind, and a second
    # window's hold. One test refuses both — line 1 must be OUR OWN _size_proc's pid.
    paths.HOLD_STATE.parent.mkdir(parents=True, exist_ok=True)
    paths.HOLD_STATE.write_text(f"424242\n{paths.STATE_LOG_DIR / 'elsewhere.log'}\n412 MB\n")
    paths.GO_REQUEST.unlink(missing_ok=True)
    wO = window.Updater()
    wO._size_proc = _SizeProc(999999)
    wO._hold_log = paths.STATE_LOG_DIR / "elsewhere.log"
    check("a hold.state belonging to another engine is not adopted",
          run._adopt_held_engine(wO) is False)
    check("and no go-ahead is written for it",
          not paths.GO_REQUEST.exists())

    # The adopt path itself. The steps travel WITH the go-ahead rather than being fixed
    # at preview time: the preview is started for `system` alone, but the run uses
    # whatever is selected when Update is pressed, which may have changed in between.
    wA = window.Updater()
    wA._size_proc = _SizeProc(31337)
    _held_log = paths.STATE_LOG_DIR / "held-preview.log"
    wA._hold_log = _held_log
    wA._size_buf = "partial-mark"
    for _k in ("flatpak", "firmware", "orphans"):
        if wA.rows[_k].switch.isChecked():
            wA.rows[_k].switch.setChecked(False)
    paths.HOLD_STATE.write_text(f"31337\n{_held_log}\n412 MB\n")
    paths.GO_REQUEST.unlink(missing_ok=True)
    check("a hold started by our own engine is adopted", run._adopt_held_engine(wA) is True)
    check("the go-ahead carries the steps selected NOW, not the preview's step",
          paths.GO_REQUEST.read_text().strip() == ",".join(wA.selected_steps()))
    check("the adopted process becomes the run's process", wA.proc is not None)
    check("the window stops offering the preview process", wA._size_proc is None)
    # _log_path must be the path the engine was actually given. Recomputing it from a
    # fresh stamp would name a file no engine ever wrote to and disagree with run.state
    # line 2, so "Open log file" would show the wrong file (§4.5).
    check("the run keeps the log path the preview engine was started with",
          wA._log_path == _held_log)
    # Whatever the preview had read but not yet split into a whole line carries over —
    # dropping it would lose the head of the next marker.
    check("a partial line read by the preview is not dropped on adoption",
          wA._buf == "partial-mark")
    paths.GO_REQUEST.unlink(missing_ok=True)
    paths.HOLD_STATE.unlink(missing_ok=True)

    # --- 5e. --thin-snapshots outcomes -----------------------------------------
    # Three branches, and each decides whether the advisory banner stays up for a retry.
    for _out, _want, _banner_stays in (("@@SNAPSHOTS@@|thinned|7\n", "7", False),
                                       ("@@SNAPSHOTS@@|thinned|0\n", "No old snapshots", False),
                                       ("", "Ready.", True)):
        _label = _out.strip() or "(no marker — cancelled or error)"
        wT = window.Updater()
        wT._warn_snapshots = True
        wT.warn_banner.setVisible(True)
        # Move the status off its constructor default first. It is built as QLabel("Ready."),
        # which is exactly what the no-marker branch sets — so without this the third case
        # would pass even if that branch never ran.
        wT.status.setText("(the handler did not set this)")
        rollback._on_thin_finished(wT, _StubProc(_out))
        check(f"thin {_label}: status reports it", _want in wT.status.text())
        check(f"thin {_label}: banner still up = {_banner_stays}",
              wT.warn_banner.isVisibleTo(wT) is _banner_stays)

    # --- 5f. the engine failing to start ---------------------------------------
    wE = window.Updater()
    wE.proc = QProcess(wE)
    wE.set_controls_enabled(False)
    # A live run leaves the bar indeterminate; __init__ already leaves it at (0, 1), so
    # without this the reset assertion below would pass without on_error doing anything.
    wE.bar.setRange(0, 0)
    run.on_error(wE, QProcess.ProcessError.FailedToStart)
    check("a failed engine start says so in the status line",
          "Could not start" in wE.status.text())
    check("a failed engine start stops the indeterminate progress bar",
          (wE.bar.minimum(), wE.bar.maximum()) == (0, 1))

    # --- headless command builder shared by both timers ------------------------
    check("headless --check command ends in --check",
          autostart._headless_command("--check").endswith("--check"))
    check("headless --update command ends in --update",
          autostart._headless_command("--update").endswith("--update"))
    check("headless command quotes the executable path",
          autostart._headless_command("--check").startswith('"'))

    # --- ONEUP-0034 INV-4: HERE is computed in exactly one place ---------------
    # Both of these pass whatever the answer is under the assertions above, which is
    # why they are written out. A module under oneup/gui/ that computes the parent of
    # its own file gets oneup/gui/, so ENGINE would name a file that does not exist and
    # Run would fail; and a systemd unit built from a package module's __file__ would
    # run `python3 …/oneup/gui/autostart.py --check`, which does nothing whatever, on a
    # weekly timer nobody watches.
    check("paths.ENGINE resolves to the repo root's update_system.sh",
          paths.ENGINE == REPO / "update_system.sh" and paths.ENGINE.exists())
    check("paths.HERE is the repo root, not the package directory", paths.HERE == REPO)
    # The last-resort branch: no $APPIMAGE, no `oneup` launcher on PATH. It is the one
    # branch that names a file rather than a launcher, and on a developer machine with
    # the launcher installed nothing else reaches it.
    _orig_which2 = autostart.shutil.which
    _orig_appimage = autostart.os.environ.pop("APPIMAGE", None)
    autostart.shutil.which = lambda name: None
    try:
        _cmd = autostart._headless_command("--check")
    finally:
        autostart.shutil.which = _orig_which2
        if _orig_appimage is not None:
            autostart.os.environ["APPIMAGE"] = _orig_appimage
    check("the last-resort headless command names the ROOT entry point, not a package module",
          str(REPO / "updater.py") in _cmd and "oneup/gui" not in _cmd)

    # --- ONEUP-0059: both halves must resolve the state directory identically ---
    # run.state and stop.request are a contract between the window and the engine
    # (docs/design/oneup-2.0.md §6.5). Move one side alone and, on a machine with
    # XDG_STATE_HOME set, the window writes stop.request where the engine never
    # looks: Stop quietly stops working and nothing fails anywhere. So this asserts
    # AGREEMENT rather than either answer, and it reads the engine's own lines out
    # of update_system.sh instead of restating the rule a third time.
    _engine_lines, _taking = [], False
    for _ln in (REPO / "update_system.sh").read_text().splitlines():
        if _ln.startswith("if [[ ${XDG_STATE_HOME"):
            _taking = True
        if _taking:
            _engine_lines.append(_ln)
        if _taking and _ln.startswith("STOP_FILE="):
            break
    _engine_block = "\n".join(_engine_lines)
    check("the engine's state-path resolution was found in update_system.sh",
          "XDG_STATE_HOME" in _engine_block and "STOP_FILE=" in _engine_block)
    _report = '\nprintf "%s\\n%s\\n" "$RUN_STATE_FILE" "$STOP_FILE"'
    _read_paths = (f"import sys;sys.path.insert(0, {str(REPO)!r});"
                   "import oneup.gui.paths as P;print(P.RUN_STATE);print(P.STOP_REQUEST)")
    for _label, _xdg in (("unset", None), ("absolute", str(Path(_SANDBOX) / "xdg-probe")),
                         ("relative — must be ignored", "not/absolute")):
        _env = {"HOME": "/home/oneup-probe", "PATH": os.environ["PATH"]}
        if _xdg is not None:
            _env["XDG_STATE_HOME"] = _xdg
        _engine = subprocess.run(  # noqa: S603
            ["bash", "-c", _engine_block + _report],  # noqa: S607 — fixed argv.
            capture_output=True, text=True, env=_env).stdout.split()
        _win = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _read_paths],
            capture_output=True, text=True, env=_env).stdout.split()
        check(f"window and engine agree on run.state / stop.request ({_label})",
              len(_engine) == 2 and _engine == _win)

    # Regression guard: the GUI-only --update token must NEVER be forwarded to the
    # engine (it exits 2 on unknown flags, which would make the 2am weekly run
    # silently fail). _headless_update() runs the engine with --notify only.
    _captured = {}
    _orig_run = gui_app.subprocess.run          # the module _headless_update lives in
    gui_app.subprocess.run = lambda a, *args, **kw: (
        _captured.update(argv=a) or type("R", (), {"returncode": 0})())
    try:
        gui_app._headless_update()
    finally:
        gui_app.subprocess.run = _orig_run
    check("headless --update invokes the engine with --notify, not --update",
          "--notify" in _captured.get("argv", []) and "--update" not in _captured.get("argv", []))

    # --- Settings popup groups the three background toggles --------------------
    w = window.Updater()
    check("Settings button exists in the header", hasattr(w, "settings_btn"))
    check("auto-update toggle defaults to off",
          hasattr(w, "autoupdate_btn") and not w.autoupdate_btn.isChecked()
          and w.autoupdate_btn.text() == "Automatic updates: off")
    dlg = settings_dialog.SettingsDialog(w)
    hosted = dlg.findChildren(QPushButton)
    check("Settings dialog hosts the weekly-check toggle", w.auto_btn in hosted)
    check("Settings dialog hosts the passwordless toggle", w.auth_btn in hosted)
    check("Settings dialog hosts the auto-update toggle", w.autoupdate_btn in hosted)

    # --- coupling: auto-update never enables without passwordless ---------------
    # Stubbed so the checks below never block on a modal. Captured and restored at the
    # end of the block: every other module-level patch in this file is, and a dialog stub
    # left installed would silently no-op a later scenario that wanted the real thing.
    _orig_msg_info = QMessageBox.information
    _orig_msg_warn = QMessageBox.warning
    QMessageBox.information = staticmethod(lambda *a, **k: 0)
    QMessageBox.warning = staticmethod(lambda *a, **k: 0)

    # (a) enabling with passwordless OFF and cancelling the combined dialog installs nothing
    w = window.Updater()
    installed_a = []
    _patch(autostart, "_install_user_timer", lambda *a, **k: (installed_a.append(a) or True))
    _patch(auth, "_confirm_passwordless", lambda win, lead="": False)   # user cancels
    auth._set_auth_checked(w, False)                               # passwordless off
    autostart.on_autoupdate_toggled(w, True)
    check("cancel combined-enable installs no update timer", not installed_a)
    check("cancel combined-enable leaves auto-update off", not w.autoupdate_btn.isChecked())
    check("cancel combined-enable clears the pending latch", w._pending_autoupdate is False)
    _unpatch_all()

    # (b) a settle reporting passwordless OFF while a latch is pending must NOT install
    w = window.Updater()
    installed_b = []
    _patch(autostart, "_install_user_timer", lambda *a, **k: (installed_b.append(a) or True))
    w._pending_autoupdate = True
    auth._on_auth_status_finished(w, _StubProc("@@AUTH@@|off\n"))
    check("settle passwordless-off does not install the update timer (stale-switch guard)",
          not installed_b)
    check("settle passwordless-off consumes the latch", w._pending_autoupdate is False)
    _unpatch_all()

    # (c) a settle reporting passwordless ON with a pending latch installs + turns on
    w = window.Updater()
    installed_c = []
    _patch(autostart, "_install_user_timer", lambda *a, **k: (installed_c.append(a) or True))
    w._pending_autoupdate = True
    auth._on_auth_status_finished(w, _StubProc("@@AUTH@@|on\n"))
    check("settle passwordless-on installs the update timer", bool(installed_c))
    check("settle passwordless-on turns the auto-update toggle on", w.autoupdate_btn.isChecked())
    _unpatch_all()

    # (d) revoking passwordless while auto-update is on clears the schedule
    w = window.Updater()
    removed_d = []
    _patch(auth, "_stand_down_autoupdate", _real_stand_down)   # neutralised suite-wide
    _patch(autostart, "_autoupdate_enabled", lambda: True)
    _patch(autostart, "_remove_user_timer", lambda name: removed_d.append(name))
    _patch(auth, "_run_auth", lambda *a, **k: None)          # don't spawn a real process
    autostart._set_autoupdate_checked(w, True)
    auth.on_auth_toggled(w, False)                                 # user revokes
    check("revoke passwordless removes the update timer", "oneup-update" in removed_d)
    check("revoke passwordless clears the auto-update toggle", not w.autoupdate_btn.isChecked())
    _unpatch_all()

    # (e) ONEUP-0099 INV-11: the timer must also stand down when the app merely DISCOVERS
    # passwordless is off — the rule removed outside OneUp, or one too old to cover what
    # this OneUp needs. The reflect runs under blockSignals precisely so it cannot fire
    # grant/revoke, so (d)'s coupling arm never sees this route. Without it, a weekly timer
    # keeps firing into a password dialog nobody is looking at and installs nothing.
    # The real helper is neutralised suite-wide (see main()); restore it on this instance.
    w = window.Updater()
    removed_e = []
    _patch(auth, "_stand_down_autoupdate", _real_stand_down)
    _patch(autostart, "_autoupdate_enabled", lambda: True)
    _patch(autostart, "_remove_user_timer", lambda name: removed_e.append(name))
    autostart._set_autoupdate_checked(w, True)
    auth._on_auth_status_finished(w, _StubProc("@@AUTH@@|off\n"))
    check("a discovered passwordless-off removes the update timer", "oneup-update" in removed_e)
    check("a discovered passwordless-off clears the auto-update toggle",
          not w.autoupdate_btn.isChecked())
    _unpatch_all()

    # (f) INV-12: a failed ENABLE must not answer with "we turned it off". Two halves, and
    # the second is the one a false-only fixture misses: _autoupdate_enabled shells out to
    # systemctl, so it reports the MACHINE, and a timer enabled outside OneUp would make it
    # true while the user's own enable is still in flight.
    for label, enabled in (("no timer present", False),
                           ("a timer the toggle didn't know about", True)):
        w = window.Updater()
        removed_f = []
        _patch(auth, "_stand_down_autoupdate", _real_stand_down)
        _patch(autostart, "_autoupdate_enabled", lambda e=enabled: e)
        _patch(autostart, "_remove_user_timer", lambda name, acc=removed_f: acc.append(name))
        w._pending_autoupdate = True
        auth._on_auth_status_finished(w, _StubProc("@@AUTH@@|off\n"))
        check(f"a failed enable ({label}) removes no timer", not removed_f)
        _unpatch_all()

    # (g) INV-13: a probe that failed to SPEAK is not a probe that said "off". A crashed
    # engine, a killed QProcess or truncated output all produce output without the marker,
    # and deleting the user's weekly timer because a subprocess did not start is
    # destructive where the toggle reflect is merely cosmetic and self-correcting.
    w = window.Updater()
    removed_g = []
    _patch(auth, "_stand_down_autoupdate", _real_stand_down)
    _patch(autostart, "_autoupdate_enabled", lambda: True)
    _patch(autostart, "_remove_user_timer", lambda name: removed_g.append(name))
    auth._on_auth_status_finished(w, _StubProc(""))
    check("a probe that emitted nothing removes no timer", not removed_g)
    check("a probe that emitted nothing still reflects passwordless as off",
          not w.auth_btn.isChecked())
    _unpatch_all()

    QMessageBox.information = _orig_msg_info
    QMessageBox.warning = _orig_msg_warn

    # --- 6. the About dialog opens and closes without error --------------------
    w = window.Updater()
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
    parsed = repos._parse_repos(sample)
    check("parse reads all repositories", len(parsed) == 3)
    check("parse reads the enabled flag",
          parsed[0]["enabled"] is True and parsed[1]["enabled"] is False)
    check("parse reads the URL", parsed[0]["url"] == "http://d.o/oss/")

    # --- ONEUP-0034 INV-7: the locale pin read_repos has always carried ---------
    # _parse_repos decides enabled from the FIRST LETTER of a column, so a German
    # desktop's "Ja" reads as "j" and every repository shows as disabled. The engine
    # has a non-English regression test; the GUI had none, so dropping the env kwarg
    # while moving this code would stay green in CI and break only for the users who
    # cannot read the English it silently assumed.
    _seen_env = {}
    _orig_repos_run = repos.subprocess.run
    repos.subprocess.run = lambda a, *_ar, **kw: (
        _seen_env.update(kw.get("env") or {})
        or type("R", (), {"stdout": sample})())
    try:
        _localised = repos.read_repos()
    finally:
        repos.subprocess.run = _orig_repos_run
    check("read_repos pins zypper's output language to C",
          _seen_env.get("LC_ALL") == "C")
    check("read_repos still parses the table it asked for", len(_localised) == 3)
    # What the pin prevents, shown rather than asserted about: the same table in German.
    _german = repos._parse_repos(sample.replace("| Yes ", "| Ja  ").replace("| No  ", "| Nein"))
    check("without the pin a localised 'Ja' would read as disabled — the pin is load-bearing",
          _german and _german[0]["enabled"] is False)

    dlg = repos.RepoManagerDialog(None, parsed)
    check("manager builds a row per repository", len(dlg._rows) == 3)
    check("repos dialog is wide enough not to clip URLs", dlg.minimumWidth() >= 720)
    # Only the two repos sharing a URL get a Remove button.
    remove_btns = [b for b in dlg.findChildren(QPushButton) if b.text() == "Remove"]
    check("only duplicate rows get a Remove action", len(remove_btns) == 2)

    # Each row carries a plain-English description of what the repo is for.
    row_labels = [b.text() for b in dlg.findChildren(QLabel)]
    check("manager row shows a repo description",
          any("Main openSUSE" in t for t in row_labels))
    P = repos._repo_purpose
    check("purpose: debug detected before oss",
          "Debug symbols" in P({"alias": "x-debug-oss", "name": "D", "url": "u", "enabled": False}))
    check("purpose: non-oss detected before oss",
          "Non-open-source" in P({"alias": "repo-non-oss", "name": "N", "url": "u",
                                  "enabled": True}))
    check("purpose: main oss collection",
          "Main openSUSE" in P({"alias": "repo-oss", "name": "O", "url": "u", "enabled": True}))
    check("purpose: unknown repo falls back",
          P({"alias": "zzz", "name": "Z", "url": "http://ex/", "enabled": True})
          == "Software package repository.")

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
    dlg_bad = repos.RepoManagerDialog(None, unsafe)
    dlg_bad._rows[0]["switch"].setChecked(True)
    check("an unsafe repo alias refuses to build a command",
          dlg_bad._build_apply_command() is None)

    # --- failure-hint "Copy command" fallback ---------------------------------
    E = banners._extract_command
    check("extract_command pulls the runnable command",
          E("A repository signing key is still rejected after an automatic import — "
            "as a last resort run: sudo zypper --gpg-auto-import-keys refresh, then "
            "retry, or check the log for the offending repo.")
          == "sudo zypper --gpg-auto-import-keys refresh")
    check("extract_command returns empty when there is no command",
          E("A package conflict — check the log.") == "")
    w = window.Updater()
    banners._show_warning(w, "Something failed — run: sudo zypper refresh, then retry.")
    check("copy button appears when a hint carries a command",
          w.warn_copy_btn.isVisibleTo(w.warn_banner)
          and w._hint_command == "sudo zypper refresh")
    banners._show_warning(w, "Low disk space — free some room and retry.")
    check("copy button hidden when a hint carries no command",
          not w.warn_copy_btn.isVisibleTo(w.warn_banner))
    try:
        banners._show_warning(w, "run: sudo zypper refresh, then retry.")
        banners._copy_hint_command(w)   # must not throw under offscreen Qt
        check("copy command runs without error", True)
    except Exception as exc:  # noqa: BLE001
        check(f"copy command runs without error ({exc})", False)

    # --- signing-key remedy: the app fixes it, but only after a warned confirm ---
    w = window.Updater()
    run.handle_line(w, "@@REMEDY@@|import-keys")
    check("REMEDY marker arms the key-import remedy", w._remedy_keys is True)
    w._failed_steps = ["system"]
    w._hints = ['A repository signing key is out of date. Use "Import signing key & '
                'retry" to fix it, or run: sudo zypper --gpg-auto-import-keys refresh.']
    w.proc = QProcess(w)
    run.on_finished(w, 1, QProcess.ExitStatus.NormalExit)
    check("warn button offers the key-import fix",
          w.warn_btn.text() == "Import signing key & retry")

    launched = {}
    _patch(run, "_launch",
           lambda win, steps, check=False, import_keys=False, skip_repos=None:
           launched.update(steps=list(steps), import_keys=import_keys))
    _patch(banners, "_confirm_key_import", lambda win: False)  # user cancels the trust dialog
    banners._fix_keys_and_retry(w)
    check("cancelling the key-import confirmation does not retry", not launched)
    _patch(banners, "_confirm_key_import", lambda win: True)   # user approves
    banners._fix_keys_and_retry(w)
    check("confirming imports keys and retries the failed steps",
          launched.get("import_keys") is True and "system" in launched.get("steps", []))
    _unpatch_all()

    # --- ONEUP-0018: system-tray icon ------------------------------------------
    # (1) Autostart Exec targets --tray and quotes the executable.
    _orig_which = autostart.shutil.which
    autostart.shutil.which = lambda name: None            # force the sys.executable branch
    autostart.os.environ.pop("APPIMAGE", None)
    try:
        exec_line = autostart._autostart_exec()
    finally:
        autostart.shutil.which = _orig_which
    check("autostart Exec ends in --tray", exec_line.endswith(" --tray"))
    check("autostart Exec double-quotes the executable", exec_line.startswith('"'))

    # (2) install/remove round-trips a real file under the sandbox HOME.
    w_tmp = window.Updater()
    check("start-at-boot starts disabled", autostart._startboot_enabled() is False)
    ok_install = autostart._install_autostart(w_tmp)
    check("install_autostart writes the file", ok_install and autostart._startboot_enabled())
    body = autostart._autostart_path().read_text()
    check("autostart file targets --tray", "--tray" in body and "[Desktop Entry]" in body)
    autostart._remove_autostart()
    check("remove_autostart deletes the file", not autostart._startboot_enabled())

    _orig_exe = autostart.sys.executable
    autostart.sys.executable = "/opt/o$ne%up/oneup"
    autostart.shutil.which = lambda name: None
    autostart.os.environ.pop("APPIMAGE", None)
    try:
        line = autostart._autostart_exec()
    finally:
        autostart.sys.executable = _orig_exe
        autostart.shutil.which = _orig_which
    check("Exec escapes '$' as backslash-backslash-'$' (not $$ or bare $)",
          r"\\$" in line and "$$" not in line)
    check("Exec escapes '%' as '%%'", "%%up" in line)

    # (3) The tray icon renders in both states and is never null.
    w = window.Updater()
    check("neutral tray icon is non-null", not tray._tray_icon(False).isNull())
    check("attention tray icon is non-null", not tray._tray_icon(True).isNull())
    try:
        tray._show_window(w)   # must not throw under offscreen Qt
        check("_show_window runs without error", True)
    except Exception as exc:  # noqa: BLE001
        check(f"_show_window runs without error ({exc})", False)

    # (4) The periodic check is silent and parses the real THREE-field TOTAL line.
    w = window.Updater()
    args = tray._tray_check_args("/tmp/x.log")  # noqa: S108 — an argument value, never opened.
    check("tray check runs --check", "--check" in args)
    check("tray check is silent (no --notify)", "--notify" not in args)
    tray._parse_tray_line(w, "@@CHECK@@|TOTAL|3|updates available")
    check("tray parses field 1 of the three-field TOTAL line", w._tray_total == 3)
    tray._parse_tray_line(w, "@@CHECK@@|TOTAL|0|updates available")
    check("tray parses zero updates as neutral", w._tray_total == 0)
    tray._parse_tray_line(w, "@@STEP_BEGIN@@|system|1|3|x")   # non-CHECK line ignored
    check("tray parser ignores non-TOTAL lines", w._tray_total == 0)
    # (4b) The tray check reuses ONE rolling log, overwritten each run, so a resident
    # session doesn't accumulate a new file ~4x/day (ONEUP-0024).
    p1 = tray._traycheck_log()
    p1.write_text("stale output from a previous tray check\n")
    p2 = tray._traycheck_log()
    check("tray check reuses one fixed log file", p1 == p2 and p2.name == "traycheck.log")
    check("tray check rolls (truncates) the log each run", p2.read_text() == "")

    # (5) _ensure_tray no-ops when no system tray is available (offscreen CI case).
    w = window.Updater()
    check("no system tray under offscreen Qt", w._tray_available is False)
    tray._ensure_tray(w)
    check("_ensure_tray builds nothing without a tray", w._tray is None)
    # Force the 'available' path with a stub tray so teardown logic is exercised.
    w._tray = object()                 # pretend a tray exists
    w._tray_timer = QTimer(w)
    w._tray_timer.start(999999)
    _timer = w._tray_timer             # _teardown_tray nulls the attribute; keep the object
    tray._teardown_tray(w)
    # Dropping the reference is not the same as stopping it — a regression that removed the
    # .stop() call would leave the QTimer running (it is still parented to w) and sail past
    # an `is None` check. Assert both halves.
    check("teardown stops the timer", w._tray_timer is None and not _timer.isActive())
    check("teardown drops the tray reference", w._tray is None)

    # (6) Settings dialog hosts the two new toggles; both default off.
    w = window.Updater()
    check("tray toggle defaults off",
          not w.tray_btn.isChecked() and w.tray_btn.text() == "Tray icon: off")
    check("start-at-boot toggle defaults off",
          not w.startboot_btn.isChecked() and w.startboot_btn.text() == "Start at boot: off")
    dlg = settings_dialog.SettingsDialog(w)
    hosted = dlg.findChildren(QPushButton)
    check("Settings dialog hosts the tray toggle", w.tray_btn in hosted)
    check("Settings dialog hosts the start-at-boot toggle", w.startboot_btn in hosted)

    # (7) Coupling — enabling start-at-boot turns the tray on.
    w = window.Updater()
    _patch(autostart, "_install_autostart", lambda win: True)
    _patch(tray, "_ensure_tray", lambda win: None)
    autostart.on_startboot_toggled(w, True)
    check("boot-on turns the tray on", w.tray_btn.isChecked())
    check("boot-on persists tray_enabled",
          w.settings.value("tray_enabled", False, type=bool) is True)
    # Every Updater() in this process shares QSettings("OneUp", "OneUp") and updater.py reads
    # tray_enabled on construction, so leaving this True would silently arm the tray for any
    # later scenario asserting the default-off state.
    w.settings.setValue("tray_enabled", False)
    _unpatch_all()

    # (8) Coupling — turning the tray off removes start-at-boot.
    w = window.Updater()
    removed = []
    _patch(autostart, "_remove_autostart", lambda: removed.append(True))
    _patch(tray, "_teardown_tray", lambda win: None)
    autostart._set_startboot_checked(w, True)
    tray.on_tray_toggled(w, False)
    check("tray-off removes autostart", removed == [True])
    check("tray-off clears the start-at-boot toggle", not w.startboot_btn.isChecked())
    _unpatch_all()

    # (9) Coupling — turning start-at-boot off leaves the tray on.
    w = window.Updater()
    removed2 = []
    _patch(autostart, "_remove_autostart", lambda: removed2.append(True))
    tray._set_tray_checked(w, True)
    autostart.on_startboot_toggled(w, False)
    check("boot-off removes autostart", removed2 == [True])
    check("boot-off leaves the tray on", w.tray_btn.isChecked())
    _unpatch_all()

    # (10) A failed autostart write reverts start-at-boot only (tray stays on).
    w = window.Updater()
    _patch(autostart, "_install_autostart", lambda win: False)
    _patch(tray, "_ensure_tray", lambda win: None)
    autostart.on_startboot_toggled(w, True)
    check("failed install reverts start-at-boot", not w.startboot_btn.isChecked())
    check("failed install leaves the tray on", w.tray_btn.isChecked())
    _unpatch_all()

    # (11) Close-to-tray: with a tray live, closeEvent hides (not quits) and hints once.
    w = window.Updater()
    w._tray = object()                       # pretend resident
    hints = []
    _patch(tray, "_notify_tray_hint", lambda win: hints.append(True))
    class _Evt:
        def __init__(self): self.ignored = False
        def ignore(self): self.ignored = True
        def accept(self): pass
    w.show()   # show first so isHidden() below meaningfully proves closeEvent hid it
    check("window is visible before the tray-close", not w.isHidden())
    e1 = _Evt()
    w.closeEvent(e1)
    check("close-to-tray ignores the close event", e1.ignored)
    check("close-to-tray hides the window", w.isHidden())
    check("close-to-tray fires the hint once", hints == [True])
    e2 = _Evt()
    w.closeEvent(e2)
    check("close-to-tray does not re-hint on a second close", hints == [True])
    _unpatch_all()

    # (12) on_finished refreshes the tray: a successful run -> neutral; a check -> the count.
    w = window.Updater()
    applied = []
    _patch(tray, "_apply_tray_total", lambda win, n, uncertain=False: applied.append(n))
    w.proc = QProcess(w)
    w._installed_count = "2"
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)     # a run
    check("successful run sets the tray neutral", applied and applied[-1] == 0)
    w = window.Updater()
    applied2 = []
    _patch(tray, "_apply_tray_total", lambda win, n, uncertain=False: applied2.append(n))
    w._check_mode = True
    w._installed_count = "5"
    w.proc = QProcess(w)
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)     # a check
    check("finished check pushes the count to the tray", applied2 and applied2[-1] == 5)
    _unpatch_all()

    # (12b) ONEUP-0056: a check that couldn't read a source knows nothing about it,
    # and "I don't know" must never reach the user as "Everything is up to date. 🎉".
    # That exact false all-clear shipped: the window said it while 8 updates waited,
    # because the sources holding them had been silently skipped.
    w = window.Updater()
    _patch(tray, "_apply_tray_total", lambda win, n, uncertain=False: None)
    w._check_mode = True
    w._installed_count = "0"
    w._unchecked = ["OneUp couldn't read these software sources: packman"]
    w.proc = QProcess(w)
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)
    check("no false all-clear when a source was unreadable",
          "up to date" not in w.status.text())
    check("says it couldn't check instead", "ouldn't check" in w.status.text())
    check("the unreadable source is named in the warning",
          w.warn_banner.isVisibleTo(w) and "packman" in w.warn_label.text())
    # A clean check still gets its cheerful summary — the fix must not cry wolf.
    w = window.Updater()
    _patch(tray, "_apply_tray_total", lambda win, n, uncertain=False: None)
    w._check_mode = True
    w._installed_count = "0"
    w.proc = QProcess(w)
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)
    check("a complete check still reports up to date", "up to date" in w.status.text())
    _unpatch_all()

    # (12c) The tray makes the same claim from the same markers, so it needs the same
    # guard: CHECK_UNKNOWN arrives before the TOTAL it qualifies.
    w = window.Updater()
    tray._parse_tray_line(
        w,
        "@@CHECK_UNKNOWN@@|system|OneUp couldn't read these software sources: packman")
    tray._parse_tray_line(w, "@@CHECK@@|TOTAL|0|updates available")
    check("tray records the qualified total", w._tray_total == 0)
    check("tray flagged the check as uncertain", w._traycheck_unknown is True)

    # --- ONEUP-0025: repo resilience — skip_repos threads through to the engine ---
    args = run._engine_args(["system"], check=False, import_keys=False,
                                        skip_repos=["google-chrome"])
    check("skip_repos adds one --skip-repo per alias", "--skip-repo=google-chrome" in args)
    check("no skip_repos → no --skip-repo flag",
          "--skip-repo" not in " ".join(run._engine_args(["system"], check=False)))

    # Unattended update passes --auto-skip-repos, additively alongside --notify (and
    # still never forwards the GUI-only --update token — mirrors the guard above).
    _cap = {}
    _orig = gui_app.subprocess.run              # same module as _headless_update
    gui_app.subprocess.run = lambda a, *_ar, **kw: (
        _cap.update(argv=a) or type("R", (), {"returncode": 0})())
    try:
        gui_app._headless_update()
    finally:
        gui_app.subprocess.run = _orig
    check("headless update auto-skips broken sources",
          "--auto-skip-repos" in _cap.get("argv", []))
    check("headless update still passes --notify, not --update",
          "--notify" in _cap.get("argv", []) and "--update" not in _cap.get("argv", []))

    # --- ONEUP-0025: REPO_SKIPPED is recorded; skip-repo remedy arms a named
    # banner action ("Skip <source> & update the rest") -------------------------
    _orig_read_repos = repos.read_repos
    repos.read_repos = lambda: [{"alias": "google-chrome", "name": "Google Chrome",
                                   "enabled": True, "url": "http://c/"}]
    try:
        w = window.Updater()
        run.handle_line(w, "@@REPO_SKIPPED@@|google-chrome|signature")
        check("REPO_SKIPPED recorded", "google-chrome" in w._skipped_repos)

        run.handle_line(w, "@@REMEDY@@|skip-repo|google-chrome")
        check("skip-repo remedy stores the alias", w._remedy_skips == ["google-chrome"])
        w._failed_steps = ["system"]
        w._hints = ["The 'google-chrome' repository failed — the rest can still update."]
        w.proc = QProcess(w)
        run.on_finished(w, 1, QProcess.ExitStatus.NormalExit)
        check("banner offers a NAMED skip action",
              "Google Chrome" in w.warn_btn.text() and "Skip" in w.warn_btn.text())
        check("second banner button stays hidden when only one remedy is armed",
              not w.warn_btn2.isVisibleTo(w.warn_banner))

        # Clicking it re-launches with skip_repos = the alias, re-running the
        # failed steps.
        launched = {}
        _patch(run, "_launch",
               lambda win, steps, check=False, import_keys=False, skip_repos=None: (
                   launched.update(steps=list(steps), skip=list(skip_repos or []))))
        banners._skip_repo_and_retry(w)
        check("skip action re-launches with the alias", launched.get("skip") == ["google-chrome"])
        check("skip action re-runs the failed steps", launched.get("steps") == ["system"])
        _unpatch_all()

        # --- expired key: BOTH remedies armed at once — skip stays primary, the
        # key-import fix is reachable via a genuine second button --------------
        w2 = window.Updater()
        run.handle_line(w2, "@@REMEDY@@|skip-repo|google-chrome")
        run.handle_line(w2, "@@REMEDY@@|import-keys")
        w2._failed_steps = ["system"]
        w2._hints = ["A repository signing key is out of date."]
        w2.proc = QProcess(w2)
        run.on_finished(w2, 1, QProcess.ExitStatus.NormalExit)
        check("both remedies armed: primary button is the named skip action",
              w2.warn_btn.text() == "Skip Google Chrome & update the rest")
        check("both remedies armed: second button offers the key-import fix",
              w2.warn_btn2.isVisibleTo(w2.warn_banner)
              and w2.warn_btn2.text() == "Import signing key & retry")

        # The second button still goes through the same warned confirmation as
        # the single-remedy import-keys path (mirrors _fix_keys_and_retry's guard).
        launched2 = {}
        _patch(run, "_launch",
               lambda win, steps, check=False, import_keys=False, skip_repos=None: (
                   launched2.update(steps=list(steps), import_keys=import_keys)))
        _patch(banners, "_confirm_key_import", lambda win: True)
        w2.warn_btn2.click()
        check("clicking the second button imports keys and retries",
              launched2.get("import_keys") is True and "system" in launched2.get("steps", []))
        _unpatch_all()

        # --- only import-keys armed: single-action path is unchanged, no 2nd btn -
        w3 = window.Updater()
        run.handle_line(w3, "@@REMEDY@@|import-keys")
        w3._failed_steps = ["system"]
        w3._hints = ["A repository signing key is out of date."]
        w3.proc = QProcess(w3)
        run.on_finished(w3, 1, QProcess.ExitStatus.NormalExit)
        check("import-keys only: warn button keeps the original single-action text",
              w3.warn_btn.text() == "Import signing key & retry")
        check("import-keys only: second banner button stays hidden",
              not w3.warn_btn2.isVisibleTo(w3.warn_banner))
    finally:
        repos.read_repos = _orig_read_repos

    # --- ONEUP-0025 final-review fix: a skip remedy with NO accompanying hint
    # (a corrupt-metadata source failure arms @@REMEDY@@|skip-repo but emits no
    # @@HINT@@) must still surface the warn banner with a named skip action —
    # not stay hidden with a dead-end remedy the user never sees. -------------
    repos.read_repos = lambda: [{"alias": "chrome", "name": "Google Chrome",
                                   "enabled": True, "url": "http://c/"}]
    try:
        w5 = window.Updater()
        run.handle_line(w5, "@@REMEDY@@|skip-repo|chrome")
        w5._failed_steps = ["system"]
        # Deliberately do NOT seed w5._hints — this is the whole point of the test.
        w5.proc = QProcess(w5)
        run.on_finished(w5, 1, QProcess.ExitStatus.NormalExit)
        check("banner shows even with no HINT, only a skip remedy",
              w5.warn_banner.isVisibleTo(w5))
        check("fallback banner names the source and offers Skip",
              "Google Chrome" in w5.warn_btn.text() and "Skip" in w5.warn_btn.text())
    finally:
        repos.read_repos = _orig_read_repos

    # --- ONEUP-0025 final-review fix: two broken repos both offer their skip
    # remedy (the engine emits one @@REMEDY@@|skip-repo per culprit, up to 2) —
    # both must be collected and both re-run, not just the last one. ----------
    repos.read_repos = lambda: [
        {"alias": "chrome", "name": "Google Chrome", "enabled": True, "url": "http://c/"},
        {"alias": "brave", "name": "Brave Browser", "enabled": True, "url": "http://b/"},
    ]
    try:
        w6 = window.Updater()
        run.handle_line(w6, "@@REMEDY@@|skip-repo|chrome")
        run.handle_line(w6, "@@REMEDY@@|skip-repo|brave")
        check("both skip remedies are accumulated, not overwritten",
              w6._remedy_skips == ["chrome", "brave"])
        w6._failed_steps = ["system"]
        w6.proc = QProcess(w6)
        run.on_finished(w6, 1, QProcess.ExitStatus.NormalExit)
        check("banner offers a combined skip action for multiple sources",
              "Skip 2 sources" in w6.warn_btn.text())

        launched6 = {}
        _patch(run, "_launch",
               lambda win, steps, check=False, import_keys=False, skip_repos=None: (
                   launched6.update(steps=list(steps), skip=list(skip_repos or []))))
        banners._skip_repo_and_retry(w6)
        check("skip action re-launches with BOTH aliases",
              launched6.get("skip") == ["chrome", "brave"])
        _unpatch_all()
    finally:
        repos.read_repos = _orig_read_repos

    # A stale remedy from a prior run must never linger into the next one.
    _orig_qp_start = QProcess.start
    QProcess.start = lambda self, *a, **kw: None   # swallow the real engine launch
    try:
        w4 = window.Updater()
        w4._remedy_skips = ["stale-alias"]
        w4.warn_btn2.setVisible(True)
        run._launch(w4, ["system"], check=False)
        check("_launch resets a stale skip remedy", w4._remedy_skips == [])
        check("_launch hides a stale second banner button",
              not w4.warn_btn2.isVisibleTo(w4.warn_banner))
    finally:
        QProcess.start = _orig_qp_start

    # --- Diagnostics bundle for a bug report (ONEUP-0031) ------------------
    _latest, _build = diagnostics._latest_run_log, diagnostics.build_diagnostics
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
    _big = "H" * 20 + "T" * (diagnostics.DIAG_LOG_CAP + 3000)
    _trim = _build("1", "x", [], "b.log", _big, "w", "", "")
    check("diagnostics: oversized log trimmed to its tail",
          "earlier output trimmed" in _trim and "H" * 20 not in _trim)

    wD = window.Updater()
    diagnostics.copy_diagnostics(wD)
    check("diagnostics: button flips to Copied after a copy",
          wD.diag_btn.text() == "Copied ✓")
    check("diagnostics: clipboard receives the bundle",
          "OneUp diagnostics" in QApplication.clipboard().text())

    # --- ONEUP-0030: "last updated N days ago" nudge on the dashboard --------
    # refresh_last_run() derives a relative day-count from history.json and ambers
    # the line (dynamic stale property) once a run is STALE_AFTER_DAYS old.
    from datetime import timedelta
    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Both sides of the day-count read the clock independently: _seed_history stamps
    # history.json from window.datetime.now(), and refresh_last_run() subtracts calendar
    # DATES using its own now(). Straddle local midnight between the two and every count
    # below shifts by one, flipping the threshold assertions for a reason unconnected to
    # the code under test. Freeze the clock for this block.
    _real_datetime = window.datetime

    class _FrozenDatetime(_real_datetime):
        _AT = _real_datetime.now()

        @classmethod
        def now(cls, tz=None):
            return cls._AT

    window.datetime = _FrozenDatetime

    def _seed_history(days_ago: int, status: str = "OK"):
        when = window.datetime.now() - timedelta(days=days_ago)
        paths.HISTORY.write_text(window.json.dumps(
            {"when": when.isoformat(timespec="seconds"), "status": status}))

    wN = window.Updater()
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

    _seed_history(window.STALE_AFTER_DAYS - 1)
    wN.refresh_last_run()
    check("a run just under the threshold is not stale",
          wN.last_run.property("stale") == "false")

    _seed_history(20)
    wN.refresh_last_run()
    # ONEUP-0028: "overdue" must be in WORDS, not only the amber colour — colour
    # alone conveys nothing to a colour-blind user.
    check("an overdue run says so in words, not just in amber",
          "overdue" in wN.last_run.text())

    paths.HISTORY.unlink()
    wN.refresh_last_run()
    check("no history shows 'Last run: never'", wN.last_run.text() == "Last run: never")
    check("the 'never' state is not flagged stale", wN.last_run.property("stale") == "false")

    window.datetime = _real_datetime

    # --- ONEUP-0034 INV-6: every dialog the package defines centres on its parent -
    # The X11 and Wayland checks above prove the HELPER, on a dialog this file builds
    # itself. They say nothing about whether a dialog the app ships remembered to call
    # it — and the split moved all three into modules of their own, where a dropped
    # showEvent would look like nothing at all. Walked rather than listed, so a dialog
    # added later is covered without anyone remembering to add it here.
    _dialogs, _missing = [], []
    for _mi in pkgutil.iter_modules([str(REPO / "oneup" / "gui")]):
        _mod = __import__(f"oneup.gui.{_mi.name}", fromlist=["_"])
        for _name, _obj in vars(_mod).items():
            if (inspect.isclass(_obj) and issubclass(_obj, QDialog) and _obj is not QDialog
                    and _obj.__module__ == _mod.__name__):
                _dialogs.append(f"{_mi.name}.{_name}")
                _src = inspect.getsource(_obj.showEvent) if "showEvent" in vars(_obj) else ""
                if "center_on_parent" not in _src:
                    _missing.append(f"{_mi.name}.{_name}")
    check(f"the package defines dialogs to check ({', '.join(_dialogs) or 'none'})",
          len(_dialogs) >= 3)
    check("every QDialog under oneup/gui/ centres on its parent in its own showEvent "
          f"({', '.join(_missing) or 'none missing'})", not _missing)

    # --- ONEUP-0028: accessibility ---------------------------------------------
    wA = window.Updater()

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

    repo_dlg = repos.RepoManagerDialog(wA, [
        {"alias": "oss", "name": "Main repository", "enabled": True, "url": "http://a/x"},
        {"alias": "up", "name": "Updates", "enabled": False, "url": "http://b/y"}])
    miss_repo = unnamed(repo_dlg)
    check(f"every focusable widget in Repositories is named (unnamed: {miss_repo})",
          not miss_repo)
    check("a repo switch does not bake its on/off state into its name",
          all("enabled" not in s.accessibleName()
              for s in repo_dlg.findChildren(toggle_switch.ToggleSwitch)))
    repo_dlg.reject()

    set_dlg = settings_dialog.SettingsDialog(wA)
    miss_set = unnamed(set_dlg)
    check(f"every focusable widget in Settings is named (unnamed: {miss_set})", not miss_set)
    set_dlg.reject()

    roll_dlg = rollback.RollbackDialog(wA, [("41", "2026-07-24 09:00", "pre-update")], "41")
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
        s = toggle_switch.ToggleSwitch()
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
        pm = tray._tray_icon(True).pixmap(64, 64).toImage()
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
    qss_norm = theme.build_theme(True)
    qss_big = theme.build_theme(True, scale=1.45)
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
    # a square around our rounded buttons. What it moves is the control's own fill,
    # to a DERIVED colour (ONEUP-0076); "reuses the hover look" was the rule until
    # that item measured it and found lightening cannot reach 3:1 on these palettes.
    check("focus draws no outline ring", "outline:" not in qss_norm)
    check("focus still gives a cue", "QPushButton#GhostBtn:focus" in qss_norm)
    check("the focus rules come after the hover/checked rules they tie with",
          qss_norm.index("QPushButton#GhostBtn:focus")
          > qss_norm.index("QPushButton#GhostBtn:checked"))

    # INV-5's old form — a walk from the window looking for Repositories before
    # Recenter — is SUPERSEDED and removed rather than repaired: ONEUP-0064 moves
    # both controls into SettingsDialog, and a QDialog has its own focus chain, so
    # a walk rooted in the window can no longer reach either and would collect an
    # empty list. That dialog's chain is asserted whole by ONEUP-0064 INV-1 below,
    # which covers the same guarantee — the grouping puts Repositories above
    # Recenter and the walk compares against visual order.

    # INV-6: high contrast only ADDS an overlay — the base sheet is untouched.
    qss_hc = theme.build_theme(True, high_contrast=True)
    check("high contrast appends to the base sheet rather than replacing it",
          qss_hc.startswith(qss_norm))
    check("high contrast tells the painted switch to change too",
          "qproperty-highContrast: true" in qss_hc)
    check("the base sheet resets that property explicitly (it is not auto-reverted)",
          "qproperty-highContrast: false" in qss_norm)
    check("high contrast restates the hover rules it must beat on specificity",
          "QPushButton#RunBtn:hover" in qss_hc.replace(qss_norm, ""))

    # ONEUP-0088: #RowBorder is a BORDER, not a surface. The HC overlay fills it
    # solid ($border — white in HC dark) and only a #RowCard child painting over it
    # leaves the 1px edge showing, so a row built on RowBorder alone renders as a
    # solid white block with unreadable text. Both dialogs did exactly that.
    overlay = qss_hc.replace(qss_norm, "")
    check("high contrast colours labels nobody gave an object name",
          "\nQLabel { color:" in overlay)
    check("high contrast paints dialog backgrounds, not only the main window",
          "QDialog { background:" in overlay)
    repo_rows = [
        {"alias": "oss", "name": "Main Repository (OSS)", "enabled": True,
         "url": "http://download.opensuse.org/tumbleweed/repo/oss/"},
        # Same URL twice, so the duplicate branch of _make_row is exercised too.
        {"alias": "oss-copy", "name": "Main Repository (copy)", "enabled": False,
         "url": "http://download.opensuse.org/tumbleweed/repo/oss/"},
    ]
    for title, dlg in (("Settings", settings_dialog.SettingsDialog(wA)),
                       ("Repositories", repos.RepoManagerDialog(wA, repo_rows))):
        borders = [f for f in dlg.findChildren(QFrame) if f.objectName() == "RowBorder"]
        check(f"{title} builds rows at all", len(borders) > 0)
        check(f"every {title} RowBorder paints a RowCard over itself",
              all(f.findChild(QFrame, "RowCard") is not None for f in borders))

    # INV-7: progress and outcome are spoken. _announce records unconditionally,
    # since QAccessible.isActive() is False offscreen.
    wB = window.Updater()
    run.handle_line(wB, "@@STEP_BEGIN@@|system|1|3|Updating system packages")
    check("the step being started is announced",
          "Updating system packages" in wB._last_announcement
          and "step 1 of 3" in wB._last_announcement)
    run.handle_line(wB, "@@STEP_END@@|system|ok|3 packages updated")
    check("the step outcome is announced",
          wB._last_announcement == "System packages: 3 installed")
    run.handle_line(wB, "@@DISK@@|warn|/|512 MiB")
    check("a warning banner is announced when it appears",
          wB._last_announcement.startswith("Warning:"))
    wB.proc = QProcess(wB)
    wB._check_mode = False
    run.on_finished(wB, 0, QProcess.ExitStatus.NormalExit)
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
    theme.apply_app_theme(app_inst)
    check("a text-size change applies live", app_inst.styleSheet() != before)
    wA.settings.setValue("high_contrast", True)
    theme.apply_app_theme(app_inst)
    check("a high-contrast change applies live",
          "qproperty-highContrast: true" in app_inst.styleSheet())
    wA.settings.setValue("text_scale", 1.0)
    wA.settings.setValue("high_contrast", False)
    theme.apply_app_theme(app_inst)
    check("turning high contrast back off really reverts it",
          "qproperty-highContrast: true" not in app_inst.styleSheet())
    check("the text-size button cycles through the offered sizes",
          wA._text_scale_index() == 0)
    wA.on_textsize_clicked()
    check("cycling text size updates both the setting and the label",
          wA._text_scale_index() == 1 and "Large" in wA.textsize_btn.text())
    wA.settings.setValue("text_scale", 1.0)

    # --- ONEUP-0027: the picker, the preference and the fallback ----------------
    _qs = wA.settings
    _saved_theme = _qs.value("theme", theme.SYSTEM)

    # INV-7: switching theme applies to the window AND to every open dialog at
    # once, with no restart, and NO widget carries a stylesheet of its own —
    # a per-widget setStyleSheet is what desyncs a dialog from every later change.
    _dlg = settings_dialog.SettingsDialog(wA)
    _dlg.show()
    QApplication.processEvents()
    _before = app_inst.styleSheet()
    _qs.setValue("theme", "forest")
    theme.apply_app_theme(app_inst)
    check("INV-7 a theme change applies live, with a dialog open",
          app_inst.styleSheet() != _before)
    _own = [w.objectName() or type(w).__name__
            for top in app_inst.topLevelWidgets()
            for w in [top, *top.findChildren(QWidget)] if w.styleSheet()]
    check(f"INV-7 no widget carries a stylesheet of its own (found: {_own})", not _own)
    _dlg.reject()
    QApplication.processEvents()

    # INV-11: what is STORED is the id, never the displayed label. Storing the
    # label would make every user's theme stop resolving on a language change.
    _idx = wA.theme_combo.findData("plum")
    wA.theme_combo.setCurrentIndex(_idx)
    QApplication.processEvents()
    check("INV-11 selecting a theme stores its id, not its label",
          _qs.value("theme") == "plum" and wA.theme_combo.currentText() == "Plum")

    # INV-9: under Follow system the desktop's light/dark switch still re-applies;
    # under a NAMED theme it must not, or the user's choice is overridden every
    # time they lock the screen.
    _qs.setValue("theme", "carbon")
    theme.apply_app_theme(app_inst)
    _named = app_inst.styleSheet()
    theme.apply_app_theme(app_inst)     # what colorSchemeChanged would trigger
    check("INV-9 a scheme change does not move a named theme",
          app_inst.styleSheet() == _named)
    _qs.setValue("theme", theme.SYSTEM)
    theme.apply_app_theme(app_inst)
    check("INV-9 Follow system resolves to one of the two built-ins",
          theme.system_theme(app_inst).id in ("midnight", "daylight"))

    # INV-10: an unrecognised stored id starts in Follow system and LEAVES THE
    # STORED VALUE ALONE — Qt returns what is stored in preference to the
    # default, so value("theme", "system") is not the fallback it looks like.
    _qs.setValue("theme", "Forrest")
    theme.apply_app_theme(app_inst)
    _resolved, _known = theme.chosen_theme(app_inst)
    check("INV-10 an unknown id falls back to Follow system",
          not _known and _resolved.id == theme.system_theme(app_inst).id)
    check("INV-10 an unknown id is NOT rewritten", _qs.value("theme") == "Forrest")
    wA._refresh_theme_combo()
    check("INV-10 the picker shows Follow system for an unknown id",
          wA.theme_combo.currentIndex() == 0)

    # INV-13: a theme whose focus pair cannot be derived falls back to Follow
    # system, keeps the stored id, and SAYS SO. Nothing shipped can reach this —
    # INV-2 keeps the eight clean and §10 rules out user-authored themes — so it
    # ships unexercised unless a deliberately underivable palette is injected.
    _bad = dict(theme._DARK)
    _bad["card"] = "#000000"
    _bad["rowcard"] = "#000000"
    _bad["rowhov"] = "#989898"
    _broken = theme.Theme("broken", "Broken", "dark", _bad)
    theme.THEMES.append(_broken)
    theme.BY_ID["broken"] = _broken
    try:
        _qs.setValue("theme", "broken")
        theme.last_theme_error = ""
        theme.apply_app_theme(app_inst)
        check("INV-13 an underivable theme falls back rather than half-applying",
              theme.current_palette() is not _bad)
        check("INV-13 the fallback leaves the stored id alone",
              _qs.value("theme") == "broken")
        check("INV-13 the fallback says so, for the picker to surface",
              bool(theme.last_theme_error) and "Broken" in theme.last_theme_error)
        # Opened rather than merely constructed: Qt's isVisible() is
        # hierarchy-dependent, so asserting it on a note whose parent is hidden
        # tests nothing about what the user sees.
        _d2 = settings_dialog.SettingsDialog(wA)
        _d2.show()
        QApplication.processEvents()
        check("INV-13 the picker shows the message rather than failing silently",
              wA.theme_note.isVisible() and bool(wA.theme_note.text()))
        _d2.reject()
        QApplication.processEvents()
    finally:
        theme.THEMES.remove(_broken)
        del theme.BY_ID["broken"]
    # INV-6: a painted widget reads its colours THROUGH the module, never a name
    # bound at import — a `from ... import` keeps its own copy, so the switch
    # would stay the colour it was at start-up. Sampled from real pixels, because
    # that is the only thing that proves the repaint reached it.
    def _track_pixel(theme_id):
        _qs.setValue("theme", theme_id)
        theme.apply_app_theme(app_inst)
        sw = toggle_switch.ToggleSwitch()
        sw.setChecked(True)
        sw._anim.stop()
        sw.set_knob_pos(1.0)
        img = sw.grab().toImage()
        # The track, sampled where the knob is not: knob sits right when on.
        return img.pixelColor(img.width() // 6, img.height() // 2)

    _mid = _track_pixel("midnight")
    _for = _track_pixel("forest")
    _exp = theme.BY_ID["forest"].palette["switchon"]
    check("INV-6 the painted switch takes the new theme's track colour",
          _for.name().lower() == _exp.lower())
    check("INV-6 and it is not the colour it started with",
          _mid.name().lower() == theme.BY_ID["midnight"].palette["switchon"].lower())

    # INV-8: a theme change rebuilds the tray icon. The ATTENTION state is what to
    # capture — the idle icon is the app's own SVG, which no theme touches, so an
    # idle comparison would pass unchanged whether the invariant held or not.
    _qs.setValue("theme", "midnight")
    theme.apply_app_theme(app_inst)
    _icon_a = tray._tray_icon(attention=True).pixmap(64, 64).toImage()
    _qs.setValue("theme", "sand")
    theme.apply_app_theme(app_inst)
    _icon_b = tray._tray_icon(attention=True).pixmap(64, 64).toImage()
    check("INV-8 a theme change rebuilds the tray badge", _icon_a != _icon_b)

    _qs.setValue("theme", _saved_theme)
    theme.last_theme_error = ""
    theme.apply_app_theme(app_inst)
    _d3 = settings_dialog.SettingsDialog(wA)
    _d3.show()
    QApplication.processEvents()
    check("INV-13 a good theme clears the message again",
          not wA.theme_note.isVisible() and not wA.theme_note.text())
    _d3.reject()
    QApplication.processEvents()

    # --- ONEUP-0064: the interface redesign ------------------------------------
    # Every sweep below REVEALS before it walks. Each banner, and stop_btn,
    # retry_btn, warn_copy_btn, warn_btn2, rollback_btn and each row's disclosure,
    # is constructed hidden — and visual order and geometry are both undefined for
    # a widget that has never been laid out, so a walk that skipped them would
    # pass vacuously rather than prove anything.
    def reveal(w):
        for b in (w.reboot_banner, w.services_banner, w.warn_banner, w.appupdate_banner):
            b.setVisible(True)
        for btn in (w.stop_btn, w.retry_btn, w.warn_copy_btn, w.warn_btn2, w.rollback_btn):
            btn.setVisible(True)
        for r in w.rows.values():
            r.badge.setVisible(True)
            r.disclosure.setVisible(True)
            r.disclosure.setChecked(True)     # expands the detail panel
        QApplication.processEvents()

    # A layout tree flattened to visual order: top to bottom, then along the
    # layout direction within a row. A scroll area is a leaf — recursing into one
    # would collect Qt's own viewport and scrollbars, which are not our controls.
    def visual_order(widget):
        from PySide6.QtWidgets import QAbstractScrollArea
        out = []

        def walk_layout(lay):
            for i in range(lay.count()):
                item = lay.itemAt(i)
                if item.widget() is not None:
                    walk_widget(item.widget())
                elif item.layout() is not None:
                    walk_layout(item.layout())

        def walk_widget(w):
            if not w.isVisible():
                return
            if w.focusPolicy() != Qt.FocusPolicy.NoFocus:
                out.append(w)
            if isinstance(w, QAbstractScrollArea):
                return
            if w.layout() is not None:
                walk_layout(w.layout())

        walk_widget(widget)
        return out

    # The chain walked end to end from `start`, terminating when it returns there
    # so a cyclic chain cannot loop forever. A WHOLE-chain comparison, not a
    # per-parent one: a per-parent check cannot see an inversion BETWEEN
    # containers, which is exactly what this redesign moves.
    def walk_chain(start, limit=400):
        out, node = [start], start
        for _ in range(limit):
            node = node.nextInFocusChain()
            if node is start:
                break
            if node.isVisible() and node.focusPolicy() != Qt.FocusPolicy.NoFocus:
                out.append(node)
        return out

    def describe(widgets):
        return [f"{type(x).__name__}#{x.objectName()}" for x in widgets]

    wR = window.Updater()
    wR.show()
    reveal(wR)
    # INV-1, window half. Two walks and not one: Qt's focus chain is per
    # top-level widget, so a walk rooted in the window can never enter a dialog,
    # and a single-walk test would pass the dialog half vacuously.
    expect = [x for x in wR.focus_chain() if x.isVisible()]
    actual = walk_chain(wR.settings_btn)
    check("INV-1 the window's tab order follows its visual order",
          actual == expect)
    if actual != expect:
        print(f"       expected {describe(expect)}")
        print(f"       actual   {describe(actual)}")
    laid_out = visual_order(wR.centralWidget())
    check("INV-1 that order is the one the layout tree actually draws",
          laid_out == expect)
    if laid_out != expect:
        print(f"       layout   {describe(laid_out)}")
        print(f"       chain    {describe(expect)}")

    # INV-1, dialog half.
    wR.open_settings()
    set_dlg = wR._settings_dialog
    set_dlg.show()
    QApplication.processEvents()
    dlg_expect = set_dlg.focus_chain()
    dlg_actual = walk_chain(dlg_expect[0])
    check("INV-1 SettingsDialog's own tab order follows its visual order",
          dlg_actual == dlg_expect)
    if dlg_actual != dlg_expect:
        print(f"       expected {describe(dlg_expect)}")
        print(f"       actual   {describe(dlg_actual)}")
    check("INV-1 that dialog's order is the one its layout draws",
          visual_order(set_dlg) == dlg_expect)
    # The guarantee the removed window-rooted assertion used to carry.
    check("INV-1 Repositories still comes before Recenter",
          dlg_expect.index(wR.repos_btn) < dlg_expect.index(wR.recenter_btn))

    # INV-6: the moves are where the spec says, and none of them is half-done —
    # the one class of defect here that changes nothing measurable and everything
    # visible. header_row is asserted BY LAYOUT INDEX: "children of the header"
    # names nothing testable, since `header` is the object-named QLabel and the
    # buttons' Qt parent is the card.
    check("INV-6 Repositories and Recenter are children of SettingsDialog",
          wR.repos_btn.window() is set_dlg and wR.recenter_btn.window() is set_dlg)
    header_items = [wR.header_row.itemAt(i) for i in range(wR.header_row.count())]
    check("INV-6 the header carries the title block and two buttons, in that order",
          len(header_items) == 3
          and header_items[0].layout() is not None
          and header_items[1].widget() is wR.settings_btn
          and header_items[2].widget() is wR.about_btn)
    check("INV-6 the action row is Run, then Check, then Stop",
          [wR.action_row.itemAt(i).widget() for i in range(wR.action_row.count())]
          == [wR.run_btn, wR.check_btn, wR.stop_btn])
    check("INV-6 Stop has an object name of its own", wR.stop_btn.objectName() == "StopBtn")
    check("INV-6 Retry lives inside the warning banner",
          wR.retry_btn.parent() is wR.warn_banner)
    set_dlg.reject()

    # INV-6, the swap: exactly one of Check and Stop is ever visible, and Stop is
    # for a real run only — a --check installs nothing, so there is nothing to stop.
    wS = window.Updater()
    wS.show()
    wS.set_controls_enabled(True)
    idle = (wS.check_btn.isVisible(), wS.stop_btn.isVisible())
    wS._run_active, wS._check_mode = True, False
    wS.set_controls_enabled(False)
    running = (wS.check_btn.isVisible(), wS.stop_btn.isVisible())
    wS._check_mode = True
    wS.set_controls_enabled(False)
    checking = (wS.check_btn.isVisible(), wS.stop_btn.isVisible())
    check("INV-6 idle shows Check and not Stop", idle == (True, False))
    check("INV-6 a run replaces Check with Stop", running == (False, True))
    check("INV-6 a check keeps Check in the slot, disabled",
          checking == (True, False) and not wS.check_btn.isEnabled())

    # INV-6, the case today's code gets wrong: a run that FINISHED with a failed
    # step carrying no hint and no armed remedy. Retry was revealed for any
    # failure while the banner was raised only for a hint or a remedy, so
    # reparenting Retry unchanged would have left the user no way to retry at all.
    wF = window.Updater()
    wF.show()          # isVisible() is False for every child of a hidden window
    wF._run_active, wF._check_mode = True, False
    _patch(run, "_notify_when_away", lambda *a, **k: None)
    for line in ("@@STEP_BEGIN@@|orphans|1|1|Removing leftovers",
                 "@@STEP_END@@|orphans|fail|autoremove failed"):
        run.handle_line(wF, line)
    run.on_finished(wF, 1, None)
    _unpatch_all()
    check("INV-6 a hintless failed run still raises the banner",
          wF.warn_banner.isVisible())
    check("INV-6 and Retry is visible inside it", wF.retry_btn.isVisible())
    check("INV-6 the banner says what happened",
          "did not finish" in wF.warn_label.text())

    # INV-5: 24x24 is SC 2.5.8's floor for a POINTER target, width as well as
    # height. Measured at a 6 pt application font — the floor below which
    # _font_metrics stops honouring the desktop font at all, because it
    # SUBSTITUTES 10.0 outright outside 6-30 pt rather than clamping, so pinning
    # 4 pt would silently test at 10 pt and prove less. #GhostBtn, #LinkBtn and
    # #Disclose carry no font-size, so their geometry follows the application
    # font directly and 6 pt puts both paths at their tightest in one run.
    _app = QApplication.instance()
    _font_before = _app.font()
    _small = QFont(_font_before)
    _small.setPointSizeF(6.0)
    _app.setFont(_small)
    theme.apply_app_theme(_app)
    wT = window.Updater()
    wT.show()
    reveal(wT)
    wT.open_settings()
    tiny_dlg = wT._settings_dialog
    tiny_dlg.show()
    QApplication.processEvents()
    targets = [("run", wT.run_btn), ("check", wT.check_btn), ("stop", wT.stop_btn),
               ("settings", wT.settings_btn), ("about", wT.about_btn),
               ("retry", wT.retry_btn), ("close", tiny_dlg.close_btn),
               ("log toggle", wT.log_toggle), ("open log", wT.openlog_btn),
               ("rollback", wT.rollback_btn), ("copy command", wT.warn_copy_btn),
               ("size", wT.rows["system"].size_btn),
               ("restart", wT.restart_btn), ("services", wT.services_btn),
               ("warn", wT.warn_btn), ("warn 2", wT.warn_btn2),
               ("app update", wT.appupdate_btn)]
    targets += [(f"{k} disclosure", wT.rows[k].disclosure) for k in wT.rows]
    targets += [(f"{k} switch", wT.rows[k].switch) for k in wT.rows]
    targets += [(f"settings row {i}", b) for i, b in enumerate(tiny_dlg.focus_chain()[:-1])]
    undersized = [f"{n} {b.width()}x{b.height()}" for n, b in targets
                  if b.width() < 24 or b.height() < 24]
    check(f"INV-5 every pointer target measures at least 24x24 at 6 pt "
          f"(undersized: {undersized})", not undersized)
    tiny_dlg.reject()
    _app.setFont(_font_before)
    theme.apply_app_theme(_app)

    # INV-4: a whole row is the click target. Counted by EMISSIONS, not by
    # comparing isChecked() before and after — a state comparison cannot tell one
    # toggle from three, and the double-toggle this guards against shows up as a
    # dead-looking control rather than as a throw.
    wC = window.Updater()
    wC.show()
    row = wC.rows["system"]
    row.badge.setText("3 waiting")
    row.badge.setVisible(True)
    row.add_detail_item("bash", "5.2", "5.3")       # reveals the disclosure
    row.disclosure.setChecked(True)                 # expands the panel
    QApplication.processEvents()
    fired = []
    row.switch.toggled.connect(lambda on: fired.append(on))

    def clicks_at(widget, point=None):
        fired.clear()
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         point if point is not None else widget.rect().center())
        QApplication.processEvents()
        return len(fired)

    body = QPoint(20, row.height() // 4)   # over the name/description column
    check("INV-4 clicking a row's body toggles its switch exactly once",
          clicks_at(row, body) == 1)
    check("INV-4 clicking the switch itself toggles exactly once, not twice",
          clicks_at(row.switch) == 1)
    check("INV-4 clicking the badge does not toggle",
          clicks_at(row, row.badge.geometry().center()
                    + row.badge.parentWidget().pos()) == 0)
    check("INV-4 clicking the disclosure does not toggle",
          clicks_at(row, row.disclosure.geometry().center()
                    + row.disclosure.parentWidget().pos()) == 0)
    check("INV-4 clicking inside the detail panel does not toggle",
          clicks_at(row, row.details.geometry().center()) == 0)
    wC.set_controls_enabled(False)
    check("INV-4 a body click is inert while the switch is disabled",
          clicks_at(row, body) == 0)
    wC.set_controls_enabled(True)

    # INV-7: every object name styled in the base sheet has a counterpart rule in
    # the overlay. Extracted from SELECTOR POSITION only — both templates carry
    # #rrggbb literals in DECLARATIONS, so a naive #(\w+) scan over the raw text
    # collects colour values as names and the test is red on its first run.
    def styled_names(template_text):
        stripped = re.sub(r"/\*.*?\*/", "", template_text, flags=re.S)
        names = set()
        for selector, _decls in re.findall(r"([^{}]*)\{([^}]*)\}", stripped):
            names.update(re.findall(r"#(\w+)", selector))
        return names

    base_names = styled_names(theme._QSS.template)
    hc_names = styled_names(theme._HC_QSS.template)
    # Named rather than discovered: three names were base-only before this item,
    # and a parity assertion that is red on arrival gets weakened rather than
    # believed. #Disclose came off the list here (the 24 px floor gives it a rule
    # in both). The other two are safe because their base rule sets no colour, so
    # the appended overlay has nothing to leak — that is the criterion a third
    # exemption would have to meet, and both now carry overlay rules anyway.
    exceptions = {"RowDetails", "DetailScroll"}
    missing_hc = sorted((base_names - exceptions) - hc_names)
    check(f"INV-7 every styled object name has a high-contrast rule "
          f"(missing: {missing_hc})", not missing_hc)
    check("INV-7 the Stop button is styled in BOTH sheets",
          "StopBtn" in base_names and "StopBtn" in hc_names)

    # --- ONEUP-0027: the whole-palette contrast check ---------------------------
    # INV-2, INV-3, INV-4. The check is a module under oneup/gui/ rather than a
    # helper in tests/, because it is a computation the application could also
    # expose and a helper living here cannot be imported by anything else.
    #
    # INV-3 runs FIRST and validates the exception list's SHAPE before the check
    # uses it: an entry without a pair, a reason, or — where the reason is a
    # deferral — a roadmap id is itself a failure. That is what stops the list
    # becoming the place failing pairs go to be forgotten.
    bad_shape = contrast.bad_exceptions()
    check(f"INV-3 every exception entry is complete ({len(bad_shape)} malformed)",
          not bad_shape)
    for line in bad_shape[:6]:
        print(f"       {line}")

    # INV-1: every theme supplies every key in the reference set, and no extra,
    # and every one of them builds. Breaks when a theme is added by copying
    # another and one key is missed — which surfaces today as a KeyError deep
    # inside Template.substitute; this names the key and the theme.
    for _th in theme.THEMES:
        _missing = sorted(theme.REFERENCE_KEYS - set(_th.palette))
        _extra = sorted(set(_th.palette) - theme.REFERENCE_KEYS)
        check(f"INV-1 {_th.id} supplies every reference key and no extra "
              f"(missing {_missing}, extra {_extra})", not _missing and not _extra)
        try:
            theme.build_theme(_th)
            theme.build_theme(_th, high_contrast=True)
            _built = True
        except Exception as exc:                                  # noqa: BLE001
            _built = False
            print(f"       {_th.id}: {type(exc).__name__}: {exc}")
        check(f"INV-1 {_th.id} builds, overlay off and on", _built)

    for _th in theme.THEMES:
        _name = _th.id
        _pal = dict(_th.palette)
        _pal.update(theme.derived_keys(_pal))

        # INV-4: a token covered by none of the four routes fails, which is what
        # stops a colour being added to a palette and quietly escaping the check.
        _uncovered = contrast.uncovered(_pal)
        check(f"INV-4 every {_name} colour token is covered by §4.7 "
              f"({len(_uncovered)} uncovered)", not _uncovered)
        for line in _uncovered[:6]:
            print(f"       {line}")

        # INV-2: every pair the table gives this palette clears its floor, or
        # carries an exception. Breaks on a theme authored by eye.
        _short = contrast.short(_pal)
        check(f"INV-2 every {_name} pair clears its floor ({len(_short)} short)",
              not _short)
        for line in _short[:8]:
            print(f"       {line}")

        # INV-2, the high-contrast half. Two different jobs: the overlay's own
        # pairs once per base, and the surfaces the overlay does NOT reach — the
        # painted switch and tray — per theme with the overlay on. A theme whose
        # track is legible on its own window can still fail against pure black.
        _hc = contrast.hc_short(_th)
        check(f"INV-2 {_name} clears its floors with the overlay ON "
              f"({len(_hc)} short)", not _hc)
        for line in _hc[:8]:
            print(f"       {line}")

    # --- ONEUP-0076: the ringless focus cue ------------------------------------
    # INV-2, INV-3, INV-7, INV-8 — the ratio arithmetic, over every theme and
    # both overlay states. The computation lives in oneup/gui/theme.py beside the
    # derivation it verifies and prints every pair it measures, so §4.3's table is
    # regenerated rather than re-derived by hand.
    measured = 0
    short = []
    for _theme in theme.THEMES:
        for _hc in (False, True):
            for r in theme.focus_report(_theme, _hc):
                measured += 1
                if r["ratio"] + 1e-9 < r["floor"]:
                    short.append(f"{_theme.id}"
                                 f"{'+hc' if _hc else ''} {r['control']} {r['kind']} "
                                 f"{r['value']} on {r['against']} = {r['ratio']:.2f}:1 "
                                 f"< {r['floor']}")
    check(f"INV-2/3/7/8 all {measured} measured focus pairs clear their floor "
          f"({len(short)} short)", not short)
    for line in short[:8]:
        print(f"       {line}")

    # INV-5: the derivation returns a pair for every sRGB colour, and fails loudly
    # rather than returning a best-effort one where no fill can satisfy the set.
    # A stride-16 lattice: the stride-3 one costs about 230 s of pure-Python
    # derivation and is a one-off, not a suite check.
    lattice_bad = []
    for r_ in range(0, 256, 17):
        for g_ in range(0, 256, 17):
            for b_ in range(0, 256, 17):
                c = f"#{r_:02x}{g_:02x}{b_:02x}"
                fill, ink = theme.derive_focus(c, (c,))
                if (theme.contrast(fill, c) + 1e-9 < theme.FOCUS_MIN
                        or theme.contrast(ink, fill) + 1e-9 < theme.INK_MIN):
                    lattice_bad.append(c)
    check(f"INV-5 every sRGB colour yields a conforming pair "
          f"(4096 sampled, {len(lattice_bad)} bad)", not lattice_bad)
    # Breaks if the search is written in one direction only: toward white alone
    # fails at #4aa3ff, which reaches 2.63:1 at most.
    one_way, _ = theme.derive_focus("#4aa3ff", ("#4aa3ff",))
    check("INV-5 the search tries both directions",
          theme.contrast(one_way, "#4aa3ff") >= theme.FOCUS_MIN)
    try:
        theme.derive_focus("#000000", ("#000000", "#989898"))
        raised = False
    except theme.FocusDerivationError:
        raised = True
    check("INV-5 an unsatisfiable surface set raises rather than guessing", raised)

    # INV-1: every focusable widget, in the window AND in every dialog it can
    # open, is covered by a row of §4.2's mechanism table — by object name for a
    # styled control, by class for a painted one, and BY SURFACE as well where a
    # name carries qualified rows. Reaching the top of the parent chain on a
    # surface no row lists is a failure, not a fallback: an unconditional fallback
    # makes this half decorative, because a name with a default row would then
    # match on every surface in the application.
    #
    # `None` means the row's rest pixels are the control's own fill or border, so
    # no ancestor decides them; a set of container names means the walk must
    # reach one of them.
    FOCUS_TABLE = {
        "RunBtn": None, "BannerBtn": None, "RestartBtn": None,
        "Log": None, "DetailScroll": None, "RepoScroll": None, "RollbackList": None,
        "StopBtn": {"Card"},
        "Disclose": {"RowCard"},
        "GhostBtn": {"Card", "RowCard", "DialogButtons", "WarnBanner"},
        "LinkBtn": {"Card", "RowCard", "RowDetails", "WarnBanner"},
        # ONEUP-0027's picker and its popup. Both rules are unqualified,
        # because the picker only ever appears in one place.
        "ThemeCombo": None, "ThemeList": None,
    }
    PAINTED = {"ToggleSwitch"}

    def surface_of(widget, wanted):
        node = widget.parentWidget()
        while node is not None:
            if node.objectName() in wanted:
                return node.objectName()
            node = node.parentWidget()
        return None

    def uncovered(root):
        out = []
        for wid in root.findChildren(QWidget):
            if wid.focusPolicy() == Qt.FocusPolicy.NoFocus or not wid.isVisible():
                continue
            name = wid.objectName()
            if name in FOCUS_TABLE:
                wanted = FOCUS_TABLE[name]
                if wanted is not None and surface_of(wid, wanted) is None:
                    out.append(f"{name} on a surface no row lists")
                continue
            if type(wid).__name__ in PAINTED:
                continue
            # The one exclusion, and it turns on CONSTRUCTION rather than on
            # appearance: a focusable widget with no object name of ours, built by
            # a Qt convenience class, carrying no rule in either sheet. That is the
            # About box's four and nothing else — covering them would mean styling
            # by private names Qt is free to rename. An unnamed widget OneUp builds
            # is a missing name and fails here, which is what named #RepoScroll
            # and #RollbackList.
            qt_chrome = (isinstance(wid.window(), QMessageBox)
                         and (not name or name.startswith("qt_"))
                         and name not in base_names and name not in hc_names)
            if not qt_chrome:
                out.append(f"{type(wid).__name__}#{name}")
        return out

    wU = window.Updater()
    wU.show()
    reveal(wU)
    gaps = uncovered(wU)
    wU.open_settings()
    su = wU._settings_dialog
    su.show()
    QApplication.processEvents()
    gaps += uncovered(su)
    su.reject()
    ru = repos.RepoManagerDialog(wU, [
        {"alias": "oss", "name": "Main", "enabled": True, "url": "http://a/x"},
        {"alias": "dup", "name": "Copy", "enabled": True, "url": "http://a/x"}])
    ru.show()
    QApplication.processEvents()
    gaps += uncovered(ru)
    ru.reject()
    ko = rollback.RollbackDialog(wU, [("41", "2026-07-24 09:00", "pre-update")], "41")
    ko.show()
    QApplication.processEvents()
    gaps += uncovered(ko)
    ko.reject()
    # About is a QMessageBox built and exec()d inside show_about, which would
    # block, so the check builds the equivalent box. That is the cost of the
    # exclusion, said plainly: no assertion here can fail on the real About box —
    # this covers the exclusion RULE, not that dialog's contents.
    about = QMessageBox(wU)
    about.setText("<b>OneUp</b>")
    about.setInformativeText("about")
    about.addButton("Check for updates", QMessageBox.ActionRole)
    about.addButton(QMessageBox.Close)
    about.show()
    QApplication.processEvents()
    gaps += uncovered(about)
    about.close()
    check(f"INV-1 every focusable widget has a focus treatment (uncovered: {gaps})",
          not gaps)

    # INV-4: focus moves colour and nothing else. Two halves, because the window
    # has two rendering paths.
    full = theme.build_theme(True) + theme.build_theme(True, high_contrast=True)

    def rules(text):
        stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return re.findall(r"([^{}]*)\{([^}]*)\}", stripped)

    def box_parts(decls):
        """A border shorthand expanded into the parts a focus rule may not move."""
        parts = {}
        for prop, value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", decls):
            prop, value = prop.strip(), value.strip()
            if prop == "border":
                bits = value.split()
                if bits and bits[0] != "none":
                    parts["border-width"], parts["border-style"] = bits[0], bits[1]
                else:
                    parts["border-width"], parts["border-style"] = "0px", "none"
            elif prop in ("border-width", "border-style", "border-radius",
                          "min-width", "min-height", "padding", "outline"):
                parts[prop] = value
        return parts

    # Keyed on the LAST compound selector, because that is what Qt's cascade
    # resolves a box property against: `#RowCard QPushButton#GhostBtn:focus` is
    # held to `QPushButton#GhostBtn`'s rest rule, which is the only one there is.
    # Run per sheet rather than on the concatenation, so an overlay rest rule
    # cannot stand in for a base one the base sheet never wrote.
    moved, outlined = [], []
    for sheet_name, sheet in (("base", theme.build_theme(True)),
                              ("overlay", theme.build_theme(True, high_contrast=True))):
        rest_parts, focus_parts = {}, {}
        for selector, decls in rules(sheet):
            for sel in (s.strip() for s in selector.split(",")):
                if not sel:
                    continue
                base, _, state = sel.partition(":")
                key = base.split()[-1] if base.split() else base
                if state == "focus":
                    if "outline" in box_parts(decls):
                        outlined.append(sel)
                    focus_parts.setdefault(key, {}).update(box_parts(decls))
                elif not state:
                    rest_parts.setdefault(key, {}).update(box_parts(decls))
        for key, parts in focus_parts.items():
            rest = rest_parts.get(key, {})
            for prop, value in parts.items():
                if rest.get(prop) != value:
                    moved.append(f"{sheet_name} {key}:focus {prop}: {value} "
                                 f"(rest: {rest.get(prop)})")
    check("INV-4 no :focus rule sets an outline", not outlined)
    check(f"INV-4 no :focus rule changes a widget's box (moved: {moved})", not moved)
    ordered = []
    for name in ("QPushButton#GhostBtn", "QPushButton#RunBtn", "QPushButton#StopBtn",
                 "QPushButton#LinkBtn", "QPushButton#BannerBtn",
                 "QPushButton#RestartBtn"):
        for state in (":hover", ":checked"):
            if name + state in full and full.rindex(name + ":focus") < full.rindex(name + state):
                ordered.append(name + state)
    check(f"INV-4 every :focus rule is emitted after the :hover / :checked rules "
          f"it ties with ({ordered})", not ordered)

    # The painted half, which no stylesheet parse can see. The focused render must
    # be the unfocused one under a CONSISTENT COLOUR-TO-COLOUR MAPPING: any two
    # pixels sharing a colour unfocused still share one focused. Darkening the
    # track satisfies that by construction; a ring drawn inside the fixed rect
    # breaks it, because two pixels that were both track become one track and one
    # ring. Neither weaker form works — "introduces no new colour" is red against
    # this very design, and "moves only colour, never which pixels are painted" is
    # vacuous, because an inset ring repaints pixels the track already painted.
    def switch_image(checked, focused):
        holder = QWidget()
        lay = QVBoxLayout(holder)
        other = QPushButton("focus me")
        sw2 = toggle_switch.ToggleSwitch()
        lay.addWidget(other)
        lay.addWidget(sw2)
        holder.show()
        QApplication.processEvents()
        sw2.setChecked(checked)
        sw2._anim.stop()
        sw2.set_knob_pos(1.0 if checked else 0.0)
        sw2.set_focus_on("#186c3c")
        sw2.set_focus_off("#66211a")
        (sw2 if focused else other).setFocus()
        QApplication.processEvents()
        got = sw2.hasFocus()
        img = sw2.grab().toImage()
        holder.hide()
        return img, got

    mapping_broken, focus_seen = [], True
    for checked in (True, False):
        plain, _ = switch_image(checked, False)
        lit, had_focus = switch_image(checked, True)
        focus_seen = focus_seen and had_focus
        # Within 2 per channel, not byte-identical: two pixels that quantise to
        # the SAME 8-bit colour unfocused can come from different sub-pixel
        # coverages, and rounding the antialiased blend of the darker focused
        # track lands them 1 apart. Measured: 3 such pairs out of 44 distinct
        # colours, every one off by exactly 1 on one channel. A ring is nothing
        # like that — it would put a whole second colour where the track was.
        seen = {}
        for x in range(plain.width()):
            for y in range(plain.height()):
                a = plain.pixelColor(x, y).getRgb()
                b = lit.pixelColor(x, y).getRgb()
                first = seen.setdefault(a, b)
                if max(abs(p - q) for p, q in zip(first, b, strict=True)) > 2:
                    mapping_broken.append(
                        f"checked={checked} at {x},{y}: {a} -> {first} and {b}")
                    break
            if mapping_broken:
                break
    check("INV-4 the switch really takes focus in the harness", focus_seen)
    check(f"INV-4 the focused switch is the unfocused one recoloured, with no ring "
          f"({mapping_broken[:1]})", not mapping_broken)

    # INV-6: no state is signalled by colour alone, and the state shape still
    # reads on the FOCUSED track — the resting tracks are ONEUP-0027 §4.7's, where
    # the white mark measures 2.10:1 on #2ecc71 and is that item's to close.
    shape_states = []
    _orig_shape = toggle_switch.ToggleSwitch._paint_state_shape

    def _spy_shape(self, p, diameter):
        shape_states.append(self.isChecked())
        return _orig_shape(self, p, diameter)

    toggle_switch.ToggleSwitch._paint_state_shape = _spy_shape
    for checked in (True, False):
        sw3 = toggle_switch.ToggleSwitch()
        sw3.setChecked(checked)
        sw3.grab()
    toggle_switch.ToggleSwitch._paint_state_shape = _orig_shape
    check("INV-6 the state shape is painted in both checked states",
          set(shape_states) == {True, False})
    check("INV-6 every badge keeps its text",
          all(r.badge.text() for r in (row,)))
    keys76 = theme.focus_keys(dict(theme._DARK))
    check("INV-6 the state shape still reads on the focused track",
          theme.contrast("#ffffff", keys76["switchfocuson"]) >= theme.FOCUS_MIN
          and theme.contrast("#ffffff", keys76["switchfocusoff"]) >= theme.FOCUS_MIN)

    # --- ONEUP-0054 stage 7, gate G3: the window DRIVING the new engine -------
    # Every other scenario in this file feeds the window marker lines it wrote
    # itself, so the suite proves the window and not the pair. This one launches
    # the real Python engine through the window's own code path and reads what
    # came back (docs/design/oneup-2.0.md §7, G3's row).
    #
    # It READS the ambient switch rather than setting one. A self-setting
    # scenario would run in both of local-CI.sh's window passes, leaving the
    # second pass nothing it alone can prove and no way to fail.
    #
    # --auth-status is the probe because it cannot hurt the machine running it:
    # read-only, and its privileged leg is sudo -k -n, which refuses to prompt
    # (oneup/engine/actions.py's auth_current, whose comment records that -k
    # leaves a warm credential intact).
    if os.environ.get("ONEUP_ENGINE", "") != "v2":
        print("  SKIP - G3 pairing: ONEUP_ENGINE is not v2 "
              "(local-CI.sh's second window pass runs it)")
    else:
        wG3 = window.Updater()
        # _on_auth_status_finished calls this on an explicit @@AUTH@@|off, and it
        # opens a modal QMessageBox that would block the suite wherever the weekly
        # timer is enabled and the drop-in is not.
        _orig_stand_down = auth._stand_down_autoupdate
        auth._stand_down_autoupdate = lambda *_a, **_k: None
        # The window's own finish handler DRAINS the process buffer, so reading it
        # afterwards yields nothing — and an empty payload makes every `in out`
        # test False, which reads as agreement. Spy on what the handler was
        # given, then hand the real handler the same bytes through the _StubProc
        # shape used above, so the code path under test still runs.
        _seen = {}
        _orig_finished = auth._on_auth_status_finished

        class _Captured:
            def __init__(self, text): self._b = text.encode()
            def readAllStandardOutput(self): return self._b

        def _spy(win_, proc_):
            _seen["out"] = bytes(proc_.readAllStandardOutput()).decode(errors="replace")
            _orig_finished(win_, _Captured(_seen["out"]))

        auth._on_auth_status_finished = _spy
        try:
            auth._query_auth_status(wG3)
            proc = getattr(wG3, "_authstat_proc", None)
            check("G3 the window launched an engine process", proc is not None)
            check("G3 the engine run finished",
                  proc is not None and proc.waitForFinished(20000))
            check("G3 the engine exited 0", proc is not None and proc.exitCode() == 0)
            out = _seen.get("out", "")
            # Assert AGREEMENT, never `on` or `off`: the answer is a property of
            # whatever machine this runs on. Exactly one verdict, so an empty
            # payload fails here instead of passing both ways below.
            saw_on, saw_off = "@@AUTH@@|on" in out, "@@AUTH@@|off" in out
            check("G3 the Python engine emitted exactly one @@AUTH@@ verdict",
                  saw_on != saw_off)
            check("G3 the window's toggle agrees with the payload the engine sent",
                  wG3.auth_btn.isChecked() == saw_on)
        finally:
            auth._on_auth_status_finished = _orig_finished
            auth._stand_down_autoupdate = _orig_stand_down

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
