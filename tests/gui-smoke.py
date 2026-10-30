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
import contextlib
import functools
import importlib.util
import inspect
import io
import itertools
import os
import pkgutil
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import types
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
# A mock sudo beside it: records each call and refuses, as a cancelled password prompt
# does. A scenario that makes the window launch the engine (the download-size probe)
# otherwise reached the REAL sudo, which opened a real password dialog on the desktop on
# every run of this suite, push gates included (ONEUP-0224).
_SUDO_LOG = os.path.join(_SANDBOX, "sudo.log")
# A scenario that writes this file makes `sudo -n -l …` succeed and print it, as a
# real listing would (ONEUP-0293).
_SUDO_LIST = os.path.join(_SANDBOX, "sudo-list.txt")
_sudo_mock = os.path.join(_BIN, "sudo")
with open(_sudo_mock, "w") as _f:
    _f.write(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> {_SUDO_LOG}\n'
             f'[[ $1 == -n && $2 == -l && -f {_SUDO_LIST} ]] && cat {_SUDO_LIST} && exit 0\n'
             'exit 1\n')
os.chmod(_sudo_mock, 0o755)  # noqa: S103 — a PATH mock must be executable.
# A mock zypper and rpm beside them, for the package details (ONEUP-0260 INV-8): a
# check's system packages start a details fetch, which otherwise read the REAL rpm
# database and repositories. Each records "$LC_ALL|argv" and prints its fixture file,
# which a scenario writes; with none it prints nothing. ONEUP_MOCK_ZYPPER_SLEEP makes
# zypper hang, by exec so that killing it leaves no child behind.
_DETAILS = os.path.join(_SANDBOX, "details")
os.makedirs(os.path.join(_DETAILS, "packages"), exist_ok=True)
_ZYPPER_LOG = os.path.join(_SANDBOX, "zypper.log")
_RPM_LOG = os.path.join(_SANDBOX, "rpm.log")
with open(os.path.join(_BIN, "zypper"), "w") as _f:
    _f.write(f'#!/usr/bin/env bash\nprintf "%s|%s\\n" "$LC_ALL" "$*" >> {_ZYPPER_LOG}\n'
             '[[ -n $ONEUP_MOCK_ZYPPER_SLEEP ]] && exec sleep "$ONEUP_MOCK_ZYPPER_SLEEP"\n'
             f'cat {_DETAILS}/zypper-info.txt 2>/dev/null\nexit 0\n')
with open(os.path.join(_BIN, "rpm"), "w") as _f:
    _f.write(f'#!/usr/bin/env bash\nprintf "%s|%s\\n" "$LC_ALL" "$*" >> {_RPM_LOG}\n'
             f'case "$3" in *%{{NAME}}*) f=baseline ;; *) f=changelog ;; esac\n'
             f'cat {_DETAILS}/rpm-$f.txt 2>/dev/null\nexit 0\n')
for _mock in ("zypper", "rpm"):
    os.chmod(os.path.join(_BIN, _mock), 0o755)  # noqa: S103 — a PATH mock must be executable.
os.environ["ONEUP_ZYPP_PACKAGES"] = os.path.join(_DETAILS, "packages")
os.environ["PATH"] = _BIN + os.pathsep + os.environ.get("PATH", "")
# The sudo route, as tests/run-tests.sh's run_engine pins it. Once OneUp's RPM is
# installed here the window would otherwise take the service route, and every
# Passwordless scenario would test a switch it does not show (ONEUP-0249 §4.10).
os.environ["ONEUP_BACKEND"] = "sudo"

try:
    import shiboken6
    from PySide6.QtCore import QEvent, QObject, QPoint, QProcess, Qt, QTimer
    from PySide6.QtGui import QAccessible, QCloseEvent, QColor, QFont, QFontInfo, QPalette
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
from oneup.engine import route as route_mod  # noqa: E402 — after the sandbox block.
from oneup.gui import (  # noqa: E402 — same reason.
    app as gui_app,  # `app` is the QApplication in main(); the module needs its own name
)
from oneup.gui import (  # noqa: E402 — same reason.
    app_update,
    auth,
    autostart,
    banners,
    contrast,
    details_dialog,
    diagnostics,
    elided_label,
    i18n,
    markers,
    package_details,
    package_views,
    packages,
    paths,
    placement,
    repos,
    rollback,
    run,
    settings_dialog,
    steps,
    symbols,
    theme,
    toggle_switch,
    tray,
    window,
)

# The old Passwordless guard's two paths, in the sandbox: the window's offer to remove
# one (ONEUP-0249 §4.10) must never read this machine's real guard.
auth.OLD_GUARDS = (os.path.join(_SANDBOX, "guard-libexec"), os.path.join(_SANDBOX, "guard-lib"))

PASS = 0
FAIL = 0


def _drawn(text: str) -> str:
    """A button label as Qt draws it: "&&" is a literal ampersand, and a lone "&" marks
    the next character as the keyboard shortcut and is not drawn — so "Roll back &
    reboot" showed as "Roll back _reboot" (ONEUP-0251)."""
    return re.sub(r"&(.)", r"\1", text)


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


def _block_network() -> list:
    """Replace every QNetworkAccessManager request method with one that records the call
    and sends nothing. Returns the record; it is never restored, so the whole run is
    covered."""
    from PySide6.QtNetwork import QNetworkAccessManager
    calls = []
    for name in ("get", "post", "put", "head", "deleteResource", "sendCustomRequest",
                 "connectToHost", "connectToHostEncrypted"):
        def _refuse(self, *args, _name=name, **kwargs):
            url = args[0].url().toString() if args and hasattr(args[0], "url") else args
            calls.append(f"{_name} {url}")
        setattr(QNetworkAccessManager, name, _refuse)
    return calls


# Every window this file builds, so the finished ones can be deleted (ONEUP-0267). They
# never free themselves: each wires its controls to a functools.partial holding the
# window, and PySide keeps a connected callable alive from C++, where gc cannot see the
# cycle. Left alone, ~125 windows and 18,000 widgets reached every app-wide setStyleSheet
# at ~4.5 s each, most of the suite's run time.
_BUILT = []


def _track_windows():
    """Record every Updater as it is built — on the class, so a window built inside a
    helper is caught too. Never restored, like _block_network."""
    init = window.Updater.__init__

    def _init(self, *args, **kwargs):
        init(self, *args, **kwargs)
        _BUILT.append(self)
    window.Updater.__init__ = _init


def _reachable(frame) -> set:
    """Ids of what scenario code can still reach from `frame` and its callers: their
    locals, two levels into containers, closures, partials and bound methods, and every
    QObject's parents — a dialog a scenario still holds keeps the window it sits in."""
    seen, todo = set(), []
    while frame is not None:
        if frame.f_code.co_name != "<module>":   # module globals hold _BUILT itself
            todo.extend(frame.f_locals.values())
        frame = frame.f_back
    for _depth in range(3):
        nxt = []
        for obj in todo:
            if obj is _BUILT or id(obj) in seen:
                continue
            seen.add(id(obj))
            if isinstance(obj, (list, tuple, set, frozenset)):
                nxt.extend(obj)
            elif isinstance(obj, dict):
                nxt.extend(obj.values())
            elif isinstance(obj, functools.partial):
                nxt.extend((*obj.args, *obj.keywords.values()))
            elif isinstance(obj, types.FunctionType):
                for cell in obj.__closure__ or ():
                    with contextlib.suppress(ValueError):   # an unfilled cell
                        nxt.append(cell.cell_contents)
            elif isinstance(obj, types.MethodType):
                nxt.append(obj.__self__)
            elif isinstance(obj, QObject) and shiboken6.isValid(obj):
                parent = obj.parent()
                while parent is not None:
                    seen.add(id(parent))
                    parent = parent.parent()
        todo = nxt
    return seen


def _reap_windows():
    """Delete every built window nothing on the stack can reach, with the parentless
    controls it lends to the Settings dialog. Deleted, not closed: closeEvent asks
    whether to quit, or hides to the tray. A visible window is left alone."""
    live = _reachable(sys._getframe(1))
    kept, doomed = [], []
    for win in _BUILT:
        if not shiboken6.isValid(win):
            continue
        lent = [v for v in vars(win).values()
                if isinstance(v, QWidget) and shiboken6.isValid(v) and v.parent() is None]
        if win.isVisible() or any(id(o) in live for o in (win, *lent)):
            kept.append(win)
        else:
            doomed.append((win, lent))
    _BUILT[:] = kept
    if not doomed:
        return
    for win, _lent in doomed:
        # A running process would be killed by its destructor, which emits finished
        # into a handler whose window is half gone. The details fetch is not the
        # window's child, so it is ended as closeEvent ends it.
        win.details.stop()
        for proc in win.findChildren(QProcess):
            proc.blockSignals(True)
            if proc.state() != QProcess.ProcessState.NotRunning:
                proc.kill()
                proc.waitForFinished(1000)
        # The window filters its own buttons' events (and a size link its link's). As
        # the children are torn down one by one, a later one's event reaches a filter
        # that reads an earlier one, already deleted — so unhook the filters first.
        watched = [win, *win.findChildren(QObject)]
        if win.windowHandle() is not None:
            watched.append(win.windowHandle())
        filters = [o for o in (*watched, *vars(win).values())
                   if isinstance(o, QObject) and type(o).__module__.startswith("oneup.")
                   and "eventFilter" in type(o).__dict__]
        for obj in watched:
            for flt in filters:
                obj.removeEventFilter(flt)
    # Those filters queue zero-delay re-measures on a theme change, and a scenario that
    # applies two themes back to back reaps between them — so the queue is run while
    # every window is still whole.
    QApplication.processEvents()
    for win, lent in doomed:
        for obj in (*lent, win):
            obj.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def main() -> int:
    # The shim is loaded for what loading it PROVES — that the thing every launcher
    # names still starts the app — not for anything read off the module afterwards;
    # the package modules imported above are where the names live now.
    _load_updater()

    # The gate under the stub below (ONEUP-0098). That stub covers one known caller, and
    # only from the line it sits on: a window built above it, or a new network call
    # anywhere in the window, reached GitHub with nothing turning red. So the transport is
    # replaced instead — on the class, so a module that imported it by name is covered
    # too — every request is recorded and refused, and the end of the run asserts none
    # was made. Installed first, so it is above every window this file builds.
    network_calls = _block_network()

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

    # sys.argv, so a `-reverse` run reaches Qt: built with [] the second pass would
    # run left to right while reporting a pass (ONEUP-0032 §4.2, INV-5).
    app = QApplication.instance() or QApplication(sys.argv)
    app  # noqa: B018 — keep a reference so it isn't GC'd mid-test.
    # ONEUP-0032 INV-5: the second pass runs this whole suite with Qt's -reverse. Its
    # FIRST assertion is that the direction really is right-to-left — a pass that
    # silently ran left to right would prove nothing.
    if "-reverse" in sys.argv[1:]:
        check("INV-5 the -reverse pass really is right-to-left", app.isRightToLeft())

    # Finished windows are deleted just before each app-wide theme apply, the one step
    # whose cost grows with every widget alive (ONEUP-0267). Above the first Updater(),
    # so every window is tracked; never restored, so the whole run is covered.
    _track_windows()
    _apply_app_theme = theme.apply_app_theme

    def _apply_after_reaping(*args, **kwargs):
        _reap_windows()
        return _apply_app_theme(*args, **kwargs)
    theme.apply_app_theme = _apply_after_reaping

    # --- 0. A 1.x number on v2 is the 2.0 preview, and the window says so -------
    # (ONEUP-0272). The number itself stays 1.x: the lockstep gate and the in-app
    # update check compare it, so only what is shown changes.
    import oneup as _oneup
    w = window.Updater()
    if _oneup.APP_VERSION.startswith("1."):
        check("a 1.x build titles itself the 2.0 preview (ONEUP-0272)",
              "2.0 preview" in w.windowTitle()
              and _oneup.APP_VERSION not in w.windowTitle())

    # --- 1. A malformed / spliced marker never throws out of the read slot ------
    for bad in ("@@STEP_BEGIN@@|system",          # too few fields
                "@@STEP_BEGIN@@|system|1",        # still too few: the floor is three
                "@@STEP_BEGIN@@|system|x|3",  # non-numeric index
                "@@ -1,4 +1,4 @@ a diff hunk",       # looks like a marker, isn't
                "@@NOPE@@ no pipe at all",
                "an ordinary log line"):
        try:
            run.handle_line(w, bad)
            check(f"malformed line handled: {bad[:22]!r}", True)
        except Exception as exc:  # noqa: BLE001 — any throw is the failure.
            check(f"malformed line handled: {bad[:22]!r} ({exc})", False)

    # --- 1b. A step key the window has no phrasing for (ONEUP-0108 INV-1) -------
    # ONEUP-0072 retired STEP_BEGIN's label, so an unfamiliar key (a newer engine's
    # new step) has no wording at all. Each site takes its own fallback form: a
    # sentence where there is room, the bare key in the progress caption.
    wK = window.Updater()
    _key = "zzz-new-step"
    run.handle_line(wK, f"@@STEP_BEGIN@@|{_key}|2|5")
    _st, _cap, _ann = wK.status.text(), wK.bar.format(), wK._last_announcement
    # The proxy alone is too weak here: "zzz-new-step, step 2 of 5" is long and has
    # spaces, so the announcement must carry the fallback sentence itself.
    _long = markers.fallback_long(_key)
    check("an unknown step key gives the status line a sentence naming it",
          _long in _st and len(_long) >= 2 * len(_key))
    check("and the announcement the same sentence", _long in _ann)
    check("the progress caption carries the bare key, not a sentence",
          _cap.startswith(_key) and "OneUp" not in _cap)
    run.handle_line(wK, "@@STEP_BEGIN@@|system|3|5")
    check("parsing continues after an unknown step key",
          wK.status.text().startswith("Updating system packages"))

    # --- 1a. A digit isdigit() accepts but int() rejects (ONEUP-0153) ----------
    # "²".isdigit() is True while int("²") raises: isdecimal() is the property
    # int() actually needs. stdout and stderr are merged, so a spliced field can
    # carry any character, and the throw would land inside the QProcess read slot
    # — which marker-protocol.md §1.2 names as the thing that must not happen,
    # since it aborts parsing and drops every remaining marker while the run
    # carries on. One superscript per numeric field of every handler that ints.
    w = window.Updater()
    for bad in ("@@STEP_BEGIN@@|system|²|3",
                "@@TIMING@@|system|²",
                "@@CHECK@@|system|²|packages",
                "@@SNAPSHOT_ITEM@@|²|2026-01-01|a restore point",
                "@@PROGRESS@@|system|²|141|download",
                "@@PROGRESS@@|system|12|²|download",
                "@@PROGRESS@@|system|12|141|download|²|397410304",
                "@@PROGRESS@@|system|12|141|download|41943040|²",
                "@@REFRESH@@|²|9|games",
                "@@REFRESH@@|6|²|games",
                "@@SNAPSHOTS@@|warn|²"):
        try:
            run.handle_line(w, bad)
            check(f"superscript digit handled: {bad[:34]!r}", True)
        except Exception as exc:  # noqa: BLE001 — any throw is the failure.
            check(f"superscript digit handled: {bad[:34]!r} ({exc})", False)
    # @@SNAPSHOT_ITEM@@ does not int() its id, it CAPTURES it — and the id is
    # interpolated into a root `snapper rollback`. isdigit() accepts "²" at the
    # capture, at the picker's re-check and at the rollback guard, so a spliced
    # superscript clears all three and reaches the root shell. Nothing throws;
    # that is why this one needs its own assertion rather than a no-throw check.
    check("a superscript snapshot id is never captured",
          all(sid.isdecimal() for sid, _d, _x in w._snapshots))
    # on_finished reads the same way: @@CHECK@@|TOTAL's count reaches int() there,
    # after the read slot has returned, so the guard has to hold in both places.
    wD = window.Updater()
    wD._run_active, wD._check_mode = True, True
    run.handle_line(wD, "@@CHECK@@|TOTAL|²")
    try:
        run.on_finished(wD, 0, None)
        check("superscript digit handled: the check-mode summary", True)
    except Exception as exc:  # noqa: BLE001 — any throw is the failure.
        check(f"superscript digit handled: the check-mode summary ({exc})", False)

    # --- 2. A real run's markers land the right per-row badges + state ----------
    w = window.Updater()
    for line in ("@@STEP_BEGIN@@|system|1|3",
                 "@@STEP_END@@|system|ok|installed|3",
                 "@@TIMING@@|system|42",
                 "@@STEP_END@@|flatpak|ok|up-to-date",
                 "@@STEP_END@@|firmware|skip|not-installed",
                 "@@STEP_END@@|orphans|fail|failed",
                 "@@STEP_END@@|cache|ok|done",
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
    # ONEUP-0190: sizes are binary, so they carry binary unit names. ONEUP-0325: KiB
    # and MiB carry one decimal place, a whole number included, as every sketch
    # prints them ("57.6 KiB", "1.0 MiB"); bytes stay whole.
    _sizes = tuple(markers._format_size(n) for n in
                   (900, 512 << 10, 59000, 41 << 20, 15518924, 3 << 29))
    check(f"_format_size labels binary units, with one decimal for KiB and MiB ({_sizes})",
          _sizes == ("900 B", "512.0 KiB", "57.6 KiB", "41.0 MiB", "14.8 MiB", "1.5 GiB"))
    # ONEUP-0190: a status outside ok / skip / fail earned no "Done".
    check("an unrecognised step status badges as unknown, not a success",
          markers._step_badge("spliced", "installed", ["3"]) == "Result unknown")
    # ONEUP-0108 INV-1, the STEP_END family: a code the table does not know, or a
    # known one whose arguments do not fit, shows the bare code — the short form,
    # since a badge has no room for a sentence — and never raises.
    check("an unknown STEP_END code shows itself as the badge",
          markers._step_badge("ok", "zzz-new-outcome", []) == "zzz-new-outcome")
    check("a known STEP_END code with an argument too few shows the bare code",
          markers._step_badge("ok", "installed", []) == "installed")
    check("a known STEP_END code with an argument too many shows the bare code",
          markers._step_badge("ok", "installed", ["3", "4"]) == "installed")
    check("an empty STEP_END code still badges something readable",
          markers._step_badge("ok", "", []) == "Result unknown")
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
    run.handle_line(wP, "@@STEP_BEGIN@@|system|1|5")
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
    check("a counted download reads as 'Downloading 12 of 141' on the step's line "
          "(ONEUP-0317)", wP.status.text() == "System packages · Downloading 12 of 141")
    # The badge names the half and the whole step's percentage (ONEUP-0239 §4.1.1).
    _badge = wP.rows["system"].badge.text()
    check(f"the row badge tracks progress ({_badge!r})",
          _badge.startswith(app.translate("run", "Downloading") + " · ") and _badge.endswith("%"))
    run.handle_line(wP, "@@PROGRESS@@|system|7|141|install")
    check("the install phase says Installing",
          wP.status.text() == "System packages · Installing 7 of 141")
    # One announcement per phase, not per package: 141 spoken lines would bury
    # everything else, but silence through the longest phase is what looked hung.
    check("a phase change is announced once", wP._last_announcement == "Installing packages.")
    wP._last_announcement = ""
    run.handle_line(wP, "@@PROGRESS@@|system|8|141|install")
    check("further packages in the same phase are not re-announced",
          wP._last_announcement == "")

    # ONEUP-0239 INV-20 (ONEUP-0336): each Flatpak pass is worded as its own, never as
    # installing; one announcement per pass; the bars stay busy and Stop stays usable.
    wF = window.Updater()
    run._reset_for_run(wF, ["flatpak"], check=False)
    _spoken = []
    _orig_announce = wF._announce
    wF._announce = lambda text, *a, **kw: (_spoken.append(text), _orig_announce(text, *a, **kw))
    run.handle_line(wF, "@@STEP_BEGIN@@|flatpak|1|1")
    _spoken.clear()   # the step's own start is announced already, by STEP_BEGIN
    for _marker, _part in (("0|0|user", "Updating your apps"),
                           ("3|12|user", "Updating your apps: 3 of 12"),
                           ("4|12|user", "Updating your apps: 4 of 12"),
                           ("3|20|system", "Updating system apps: 3 of 20"),
                           ("0|0|unused", "Removing unused runtimes")):
        run.handle_line(wF, f"@@PROGRESS@@|flatpak|{_marker}")
        check(f"INV-20 PROGRESS|flatpak|{_marker} reads {_part!r} ({wF.status.text()!r})",
              wF.status.text() == f"Flatpak apps · {_part}")
        check(f"INV-20 after {_marker} both bars are busy and Stop is usable",
              wF.rows["flatpak"].progress.maximum() == 0 and wF.bar.maximum() == 0
              and wF.stop_btn.isEnabled())
    check(f"INV-20 one announcement per pass ({_spoken})",
          _spoken == ["Updating your Flatpak apps.", "Updating system Flatpak apps.",
                           "Removing unused Flatpak runtimes."])
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
    run.handle_line(wP, "@@STEP_BEGIN@@|cache|5|5")
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
        run.handle_line(wL, "@@STEP_BEGIN@@|system|1|5")
        run.handle_line(wL, "@@REFRESH@@|6|9|games")
        check("the source being fetched is named, with its position",
              wL.status.text().startswith("Checking for updates from games (6 of 9 sources)…"))
        check("the bar keeps the step caption and adds the source",
              "Updating system packages" in wL.bar.format() and "games" in wL.bar.format())
        check("the liveness line names what is being waited on",
              "Fetching games" in wL.activity.text())
        # ONEUP-0317: the line itself is never shown; the status carries what it must.
        check("the status carries the liveness clock during a run",
              "Fetching games" in wL.status.text())
        # Bytes: the download phase is the only place in a run where a figure exists at all.
        run.handle_line(wL, "@@PROGRESS@@|system|12|141|download|41943040|397410304")
        check("the download says how much of how much",
              "40.0 MiB of 379.0 MiB" in wL.activity.text())
        # ONEUP-0284: a real run read "Fetching science_GPU_ROCm — 2m 15s · 670 MiB of
        # 670 MiB" through the whole download, long after that refresh had finished.
        check("the download no longer names the source fetched before it",
              "Fetching games" not in wL.activity.text())
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
        run.handle_line(wL, "@@STEP_BEGIN@@|flatpak|2|5")
        check("a new step drops the previous source", "games" not in wL.activity.text())
        check("a new step resets the byte counters", wL._dl_bytes == 0 and wL._dl_total == 0)
        # ONEUP-0232: a quiet step that is not known to be downloading — flatpak deploying
        # to a busy disk, measured on a real run — must not blame the server, and must not
        # promise the prompt stop ONEUP-0085 gives only while downloading.
        wL._activity_at = time.monotonic() - (run.STALL_SECONDS + 5)
        run._tick_activity(wL)
        check("a quiet step with no download does not blame the server",
              "server" not in wL.activity.text() and "still working" in wL.activity.text())
        check("nor does it promise a prompt stop", "Stopping now is safe" not in wL.activity.text())
        check("nor is the quiet announced as the server's",
              "server" not in wL._last_announcement)
        # The system step's install phase is past the download, so the same holds there,
        # even though a source was fetched earlier in the step.
        wL._activity_at = time.monotonic()
        run._tick_activity(wL)
        run.handle_line(wL, "@@STEP_BEGIN@@|system|1|5")
        run.handle_line(wL, "@@REFRESH@@|9|9|games")
        run.handle_line(wL, "@@PROGRESS@@|system|3|141|install")
        check("the label goes at once, not on the next tick (ONEUP-0284)",
              "Fetching games" not in wL.activity.text())
        wL._activity_at = time.monotonic() - (run.STALL_SECONDS + 5)
        run._tick_activity(wL)
        check("a quiet install does not blame the server", "server" not in wL.activity.text())
        check("the install no longer names the source fetched before it (ONEUP-0284)",
              "Fetching games" not in wL.activity.text())
        wL._activity_at = time.monotonic()
        run._tick_activity(wL)
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
        run.handle_line(wC, "@@STEP_BEGIN@@|system|1|5")
        run.handle_line(wC, "@@PROGRESS@@|system|1|0|download|0|90596966")
        check("a prefetch tally still invents no denominator",
              "1 so far" in wC.status.text() and "of 0" not in wC.status.text())
        (Path(cache_dir) / "pkg.rpm").write_bytes(b"x" * (20 * 1024 * 1024))
        run._tick_activity(wC)
        check("the download is measured even though zypper reported no size",
              "20.0 MiB of 86.4 MiB" in wC.activity.text())
        # Packages an earlier, stopped run left in the cache are still inside zypper's
        # total (measured 2026-10-14: 166 MiB cached, total 695.5 MiB), so they count as
        # fetched, or the figure lags and never reaches the total (ONEUP-0093). This
        # check asserted the opposite until then: it had written the defect down.
        wC2 = window.Updater()
        wC2._run_active = True
        # The liveness line has its own flag since it must also run on a
        # --check, where _run_active is False by design.
        wC2._liveness_active = True
        run._reset_activity(wC2)       # baseline now includes the 20 MB above
        run.handle_line(wC2, "@@PROGRESS@@|system|1|0|download|0|90596966")
        run._tick_activity(wC2)
        check("already-cached packages count as fetched (ONEUP-0093)",
              "20.0 MiB of 86.4 MiB" in wC2.activity.text())
        check("the rate is anchored on that figure, so it counts only new bytes",
              wC2._dl_from == 20 * 1024 * 1024)
        # Exactly the rest of the total: whole-MiB sizes once hid a 0.4 MiB gap here.
        (Path(cache_dir) / "pkg2.rpm").write_bytes(b"x" * (90596966 - 20 * 1024 * 1024))
        run._tick_activity(wC2)
        check("a warm-cache download reaches its total",
              "86.4 MiB of 86.4 MiB" in wC2.activity.text())
        (Path(cache_dir) / "pkg3.rpm").write_bytes(b"x" * (10 * 1024 * 1024))
        run._tick_activity(wC2)
        check("leftovers the transaction does not need never run past the total",
              "86.4 MiB of 86.4 MiB" in wC2.activity.text())
        (Path(cache_dir) / "pkg2.rpm").unlink()
        (Path(cache_dir) / "pkg3.rpm").unlink()
        # The cache holds thousands of files by mid-download, and PROGRESS markers can
        # arrive several times a second; weighing it on each one stalled the window
        # (ONEUP-0155). Only the 5-second timer weighs; a marker reuses its figure.
        # run.py imports cache_bytes by name, so the name is patched there.
        weighed = []
        _real_weigh = run.cache_bytes
        run.cache_bytes = lambda: weighed.append(1) or _real_weigh()
        try:
            for n in range(1, 11):
                run.handle_line(wC, f"@@PROGRESS@@|system|{n}|0|download|{n}|90596966")
            check("a burst of progress markers does not re-weigh the package cache",
                  not weighed)
            check("a marker-driven redraw keeps the last weighed figure",
                  "20.0 MiB of 86.4 MiB" in wC.activity.text())
            run._tick_activity(wC)
            check("the timer's tick does re-weigh it", len(weighed) == 1)
        finally:
            run.cache_bytes = _real_weigh
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
    # ONEUP-0181: the session is Qt's platform plugin, not XDG_SESSION_TYPE — a Wayland
    # session launched without that variable would take the X11 branch, where move() is
    # accepted and ignored. The platform name is stubbed through updater._platform_name.
    _orig_session = os.environ.get("XDG_SESSION_TYPE", "")
    _orig_platform = getattr(placement, "_platform_name", None)
    try:
        os.environ["XDG_SESSION_TYPE"] = "wayland"
        placement._platform_name = lambda: "xcb"
        check("the session follows Qt's platform, not XDG_SESSION_TYPE (ONEUP-0181)",
              not placement._on_wayland())
        os.environ["XDG_SESSION_TYPE"] = "x11"     # both signals agree from here on
        host = QWidget()
        host.setGeometry(100, 100, 800, 600)
        dlg = QDialog(host)
        dlg.resize(200, 100)
        placement.center_on_parent(dlg)
        check("on X11 a dialog is moved onto its parent's centre",
              abs(dlg.frameGeometry().center().x() - host.frameGeometry().center().x()) <= 2
              and abs(dlg.frameGeometry().center().y() - host.frameGeometry().center().y()) <= 2)
        tall = QDialog(host)
        tall.resize(200, 4000)               # taller than any screen the suite runs on
        placement.center_on_parent(tall)
        area = host.screen().availableGeometry()
        check("on X11 a dialog taller than its parent stays on the screen (ONEUP-0181)",
              tall.frameGeometry().top() >= area.top())
        os.environ["XDG_SESSION_TYPE"] = ""
        placement._platform_name = lambda: "wayland"
        check("Wayland is detected from the platform alone (ONEUP-0181)",
              placement._on_wayland())
        moved_to = dlg.pos()
        placement.center_on_parent(dlg)   # queues a KWin request; must not move it itself
        check("on Wayland placement is left to the compositor, not a futile move()",
              dlg.pos() == moved_to)
        # ONEUP-0254: the script once centred every dialog of ours, so a message box
        # pulled back a dialog the user had moved. It must pick only the widget being
        # centred — by its size, newest first — and stop there.
        scripts = []
        _orig_run = placement.run_kwin_script
        placement.run_kwin_script = scripts.append
        try:
            shown = QDialog(host)
            shown.resize(321, 123)
            shown.show()
            placement.center_on_parent(shown)
            deadline = time.monotonic() + 2
            while not scripts and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.01)
            shown.close()
            # Hidden before the script runs: KWin no longer lists it, so an older
            # same-size dialog would be the one moved. No script at all.
            hidden = QDialog(host)
            hidden.show()
            placement.center_on_parent(hidden)
            hidden.hide()
            before = len(scripts)
            deadline = time.monotonic() + 0.3
            while time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.01)
        finally:
            placement.run_kwin_script = _orig_run
        js = scripts[0] if scripts else ""
        check("on Wayland only the dialog being centred is moved, not every one of ours "
              "(ONEUP-0254)",
              "cg.width - 321" in js and "cg.height - 123" in js and "break;" in js
              and "pc.width - 800" in js and "pc.height - 600" in js)
        check("a dialog hidden before its centring runs is not centred (ONEUP-0254)",
              len(scripts) == before)
    finally:
        os.environ["XDG_SESSION_TYPE"] = _orig_session
        placement._platform_name = _orig_platform

    # --- Message boxes from QMessageBox's static helpers are centred (ONEUP-0247) ----
    # QMessageBox.information(win, ...) builds, shows and runs its own box, so no call
    # site can centre it; on Wayland it then opened in the screen's corner. An
    # app-wide filter centres every message box with a parent as it is shown.
    _orig_center = placement.center_on_parent
    centred = []
    try:
        placement.install_message_box_centring(app)
        # Record whether the call came from inside the Show event: it must not, because
        # the box sizes to its content on show and is centred a tick later.
        placement.center_on_parent = lambda w: centred.append(
            (w, any(f.function == "eventFilter" for f in inspect.stack())))
        host = QWidget()
        host.setGeometry(100, 100, 800, 600)
        host.show()

        def _close_box():
            for w in QApplication.topLevelWidgets():
                if isinstance(w, QMessageBox) and w.isVisible():
                    w.done(0)

        QTimer.singleShot(200, _close_box)
        QMessageBox.information(host, "Check for updates", "You're on the latest version.")
        check("a message box from QMessageBox.information is centred on its window (ONEUP-0247)",
              any(isinstance(w, QMessageBox) for w, _ in centred))
        check("the centring waits a tick, not inside the Show event (ONEUP-0247)",
              bool(centred) and not any(inside for _, inside in centred))
        host.close()
    finally:
        placement.center_on_parent = _orig_center
        app.removeEventFilter(app._message_box_centrer)

    # --- An absurd rate-limit reset time cannot crash the update check (ONEUP-0191) --
    # int() takes any length of digits, but localtime() raises OverflowError past
    # time_t, and that escaped the reply slot: the manual check then showed nothing.
    class _RateLimitedReply:
        def __init__(self, reset):
            self._reset = reset

        def attribute(self, _attr):
            return 403

        def rawHeader(self, _name):
            return self._reset

    try:
        msg = app_update._update_check_error(_RateLimitedReply(b"9" * 20))
        absurd_ok = "GitHub limits" in msg and "Try again" not in msg
    except Exception:  # noqa: BLE001 — any escape is the defect under test
        absurd_ok = False
    check("an absurd x-ratelimit-reset gives the plain rate-limit message (ONEUP-0191)",
          absurd_ok)
    check("a real x-ratelimit-reset still says when to try again (ONEUP-0089)",
          "Try again after" in app_update._update_check_error(_RateLimitedReply(b"1760000000")))

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
        # ONEUP-0095: while rpm installs, nothing can stop it until the step ends, so a
        # click there would sit on "Stopping…" for minutes. Stop greys out and says why.
        run.handle_line(wS, "@@PROGRESS@@|system|3|141|download")
        check("Stop stays usable while packages download", wS.stop_btn.isEnabled())
        run.handle_line(wS, "@@PROGRESS@@|system|7|141|install")
        check("Stop is greyed out while packages install", not wS.stop_btn.isEnabled())
        check("the greyed-out Stop says why",
              "cannot be stopped safely" in wS.stop_btn.toolTip())
        run.handle_line(wS, "@@STEP_BEGIN@@|flatpak|2|5")
        check("Stop comes back once the install is over",
              wS.stop_btn.isEnabled() and "after the current step" in wS.stop_btn.toolTip())
        run.request_stop(wS)
        check("asking to stop creates the file the engine watches",
              paths.STOP_REQUEST.exists())
        check("the button reflects that the request is in", wS.stop_btn.text() == "Stopping…")
        check("it cannot be clicked twice", not wS.stop_btn.isEnabled())
        check("the status says what will actually happen",
              "after the current step" in wS.status.text())
        # An install phase ending must not re-offer a stop that was already asked for.
        run.handle_line(wS, "@@PROGRESS@@|flatpak|1|4|install")
        run.handle_line(wS, "@@STEP_BEGIN@@|firmware|3|5")
        check("a stop already asked for is not offered again",
              not wS.stop_btn.isEnabled() and wS.stop_btn.text() == "Stopping…")
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
        fh.write("@@STEP_BEGIN@@|system|1|2\n"
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
        check(f"markers already in the log are replayed ({wA.rows['system'].badge.text()!r})",
              wA.rows["system"].badge.text().startswith(app.translate("run", "Downloading")))
        # New lines appended by the running engine must be picked up on the next poll.
        with open(attach_log, "a") as fh:
            fh.write("@@PROGRESS@@|system|99|141|install\n")
        wA._poll_attached_run()
        check("newly appended log lines are followed live",
              wA.status.text() == "System packages · Installing 99 of 141")
        # A line the engine is still writing must wait for its newline: read in two
        # halves, the marker was parsed short and its tail logged as junk (ONEUP-0346).
        with open(attach_log, "a") as fh:
            fh.write("@@PROGRESS@@|system|100|1")
        wA._poll_attached_run()
        check("ONEUP-0346 a half-written line is not parsed yet",
              wA.status.text() == "System packages · Installing 99 of 141")
        with open(attach_log, "a") as fh:
            fh.write("41|install\n")
        wA._poll_attached_run()
        check("ONEUP-0346 the line is parsed whole once its newline arrives",
              wA.status.text() == "System packages · Installing 100 of 141")
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

    # ONEUP-0204: a probe's `finished` can be delivered after Qt destroyed the QProcess —
    # quitting mid-probe, or a window torn down at exit. The slot must then do nothing,
    # not raise "Internal C++ object (QProcess) already deleted".
    for slot in (auth._on_auth_status_finished, auth._on_auth_finished,
                 rollback._on_thin_finished):
        dead = QProcess(w)
        shiboken6.delete(dead)
        try:
            slot(w, dead)
            quiet = True
        except RuntimeError:
            quiet = False
        check(f"{slot.__name__} ignores a QProcess Qt already destroyed", quiet)
    # The same when the whole window is gone: its rows and its tray-check process go with it.
    wZ = window.Updater()
    if getattr(wZ, "_authstat_proc", None) is not None:
        wZ._authstat_proc.waitForFinished(5000)     # so deleting wZ kills no probe
    wZ._traycheck_proc = QProcess(wZ)
    shiboken6.delete(wZ)
    for slot, call in (("_on_size_finished", lambda: run._on_size_finished(wZ, 1, None)),
                       ("_on_traycheck_finished", lambda: tray._on_traycheck_finished(wZ))):
        try:
            call()
            quiet = True
        except RuntimeError:
            quiet = False
        check(f"{slot} ignores a window Qt already destroyed", quiet)

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
    # ONEUP-0154: a later warning replaces the text, so it must replace the button's role
    # too — never "A download failed…" above a button that thins snapshots.
    run.handle_line(w3, "@@DISK@@|warn|/|1.0G")
    check("a later pre-flight warning resets the button's label",
          w3.warn_btn.text() == "Show details")
    check("a later pre-flight warning disarms the thin action", w3._warn_snapshots is False)
    run.handle_line(w3, "@@REPO@@|warn|duplicate|http://a")
    banners._show_warning(w3, "A download failed — check your internet connection, then retry.")
    check("a failure hint resets the button after a repository advisory",
          w3.warn_btn.text() == "Show details" and w3._warn_repo_dup is False)

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
    check("the rollback button reads \"Roll back & reboot\", not a mnemonic underline",
          any(_drawn(b.text()) == "Roll back & reboot" for b in dlg.findChildren(QPushButton)))
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
    for line in ("@@STEP_END@@|system|ok|updated",
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
    for line in ("@@STEP_END@@|system|ok|updated",
                 "@@INSTALLED@@|2|yes|no",
                 "@@SERVICES@@|sshd cups getty@tty1 avahi-daemon -f",
                 "@@REBOOT@@|no"):
        run.handle_line(w, line)
    launched = []
    _orig_question = QMessageBox.question
    _orig_launch = banners._start_service_restart
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    # The one launch seam (ONEUP-0229): replaced so no test starts a real pkexec.
    banners._start_service_restart = lambda _w, prog, args: launched.append((prog, list(args)))
    try:
        banners.restart_services(w)
    finally:
        QMessageBox.question = _orig_question
        banners._start_service_restart = _orig_launch
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

    # --- 4a-i. The restart says how it went (ONEUP-0229) -------------------------
    # Reported by the user 2026-10-02: the button gave no sign of whether the services
    # restarted. Their choice: a box when it finishes, success or the reason, closed with
    # OK. pkexec's 126 and 127 are its own (pkexec(1)); anything else is systemctl's.
    shown = []
    _orig_info, _orig_warn = QMessageBox.information, QMessageBox.warning
    QMessageBox.information = staticmethod(
        lambda *a, **k: shown.append(("info", a[2])) or 0)
    QMessageBox.warning = staticmethod(
        lambda *a, **k: shown.append(("warn", a[2])) or 0)
    try:
        outcome = {}
        for code, out in ((0, ""), (126, ""), (127, ""), (1, "Job for cups.service failed.")):
            banners._on_services_restarted(w, code, out, ["sshd", "cups"])
            outcome[code] = shown[-1]
        # The wiring, not just the handler: a real child's exit status and output reach
        # the box. `sh` stands in for pkexec; nothing privileged runs.
        banners._start_service_restart(w, "sh", ["-c", "echo boom; exit 3"])
        w._restart_proc.waitForFinished(5000)
        wired = shown[-1]
    finally:
        QMessageBox.information, QMessageBox.warning = _orig_info, _orig_warn
    check("a successful restart says so, naming the services",
          outcome[0][0] == "info" and "sshd, cups" in outcome[0][1])
    check("a dismissed password prompt is given as the reason",
          outcome[126][0] == "warn" and "password prompt was closed" in outcome[126][1])
    check("a refused authorisation is given as the reason",
          outcome[127][0] == "warn" and "refused" in outcome[127][1])
    check("systemctl's own failure carries its message",
          outcome[1][0] == "warn" and "Job for cups.service failed." in outcome[1][1])
    check("a failed restart brings the banner back for a retry",
          w.services_banner.isVisibleTo(w))
    check("a real child's exit status and output reach the report",
          wired[0] == "warn" and "boom" in wired[1])

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
        for ln in ("@@STEP_END@@|system|ok|updated",
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
        _ls = banners._start_service_restart
        banners._start_service_restart = lambda _w, prog, args: calls.append([prog, *args])
        try:
            banners.restart_services(win)
        finally:
            (QMessageBox.question, QMessageBox.information,
             QProcess.startDetached) = _q, _i, _d
            banners._start_service_restart = _ls
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
    for line in ("@@STEP_END@@|system|ok|installed|7",
                 "@@INSTALLED@@|7|yes|no",
                 "@@REBOOT@@|yes|kernel-new graphics-driver-nvidia"):
        run.handle_line(w, line)
    check("reboot reason worded from the marker's codes",
          w._reboot_reason == "A new kernel and your NVIDIA graphics driver were installed")
    w.proc = QProcess(w)
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)
    check("reboot banner names the kernel + driver, keeping NVIDIA casing",
          "NVIDIA graphics driver" in w.reboot_label.text()
          and w.reboot_label.text().lstrip("⚠ ").startswith("A new kernel"))

    # --- 4c. ONEUP-0108 §4.4: the reboot reason's rows, INV-2 and INV-3 ----------
    def _reason(field):
        wR = window.Updater()
        run.handle_line(wR, "@@REBOOT@@|yes" + (f"|{field}" if field is not None else ""))
        return wR._reboot_reason
    # INV-2: the verb agrees with what the sentence lists, unknown codes included. The
    # reason opens the banner's sentence, so it arrives in that form — written into
    # the table, never derived by a case change (ONEUP-0032 §4.5).
    check("INV-2 one component reads 'was'",
          _reason("kernel-new") == "A new kernel was installed")
    check("INV-2 two components read 'were', joined with ' and '",
          _reason("kernel-new kernel-modules")
          == "A new kernel and kernel driver modules were installed")
    check("INV-2 one known plus one unknown reads 'were', the unknown as its code",
          _reason("kernel-new gpu-firmware-blob")
          == "A new kernel and gpu-firmware-blob were installed")
    check("three components take the serial comma, as the engine joins them",
          _reason("kernel-new graphics-driver-generic kernel-modules")
          == "A new kernel, your graphics driver, and kernel driver modules were installed")
    # INV-3: a known standalone reason is its own sentence — no join, no fallback.
    for _code in ("firmware-updated", "core-packages-updated"):
        _r = _reason(_code)
        check(f"INV-3 {_code} renders its own sentence",
              _r == markers.REBOOT_STANDALONE[_code] and "installed" not in _r
              and "no wording" not in _r)
    check("an absent reason is no sentence, never the fallback", _reason(None) == "")
    check("both vocabularies in one field is the long fallback, naming every element",
          _reason("firmware-updated kernel-new")
          == markers.fallback_long("firmware-updated", "kernel-new"))
    check("no known element is the long fallback, never the join",
          _reason("zzz-a zzz-b") == markers.fallback_long("zzz-a", "zzz-b"))
    check("a known standalone beside an unknown names only the unknown",
          _reason("firmware-updated zzz-c") == markers.fallback_long("zzz-c"))
    w = window.Updater()
    for line in ("@@STEP_END@@|firmware|ok|updated", "@@REBOOT@@|yes|firmware-updated"):
        run.handle_line(w, line)
    w.proc = QProcess(w)
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)
    check("a firmware-only reboot banner reads as before",
          w.reboot_label.text()
          == "⚠  Firmware was updated — restart so everything uses the latest version.")

    # --- 4d. ONEUP-0072 INV-4: the log pane is the engine's, verbatim ------------
    # Ordinary engine lines stay English and are never looked up — even one that is
    # spelled exactly like a code — and no code field's raw text reaches any widget
    # but the log pane (ONEUP-0108 §4.3's bare-code fallbacks being the exception,
    # which these known codes never take).
    w = window.Updater()
    _plain = ["Refreshing repository 'oss'…", "  Hint: this line is the engine's own",
              "disk-full", "kernel-new graphics-driver-nvidia"]
    for line in (_plain[0], "@@STEP_BEGIN@@|system|1|1", _plain[1],
                 "@@HINT@@|network-failed", _plain[2],
                 "@@STEP_END@@|system|fail|failed", _plain[3],
                 "@@REBOOT@@|yes|kernel-new graphics-driver-nvidia", "@@DONE@@|errors"):
        run.handle_line(w, line)
    w.proc = QProcess(w)
    run.on_finished(w, 1, QProcess.ExitStatus.NormalExit)
    _log = w.log.toPlainText().splitlines()
    check("INV-4 every plain engine line is in the log pane verbatim",
          all(line in _log for line in _plain))
    check("INV-4 a log line spelled like a code is not looked up",
          markers.HINTS["disk-full"][1] not in w.log.toPlainText())
    _shown = []
    for _wd in w.findChildren(QWidget):
        if _wd is w.log:
            continue
        for _get in ("text", "toolTip", "accessibleName", "accessibleDescription",
                     "windowTitle"):
            _v = getattr(_wd, _get, None)
            if callable(_v):
                with contextlib.suppress(TypeError):
                    _t = _v()
                    if isinstance(_t, str):
                        _shown.append(_t)
    _codes = ("network-failed", "kernel-new", "graphics-driver-nvidia")
    check("INV-4 no known code field's raw text reaches a widget but the log",
          not [c for c in _codes for t in _shown if c in t])
    check("INV-4 and the codes were worded, not dropped",
          any("A new kernel" in t for t in _shown)
          and w._hints == [markers.HINTS["network-failed"][1]])

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

    # ONEUP-0329 INV-10: a count carrying `at-least` is a floor, and says so; a zero
    # says "up to date" with or without it.
    w = window.Updater()
    w._check_mode = True
    _patch(tray, "_apply_tray_total", lambda win, n, uncertain=False, **kw: _tray_calls.append(kw))
    _tray_calls = []
    for line in ("@@CHECK@@|system|7|system package(s)|at-least",
                 "@@CHECK@@|flatpak|0|Flatpak app(s)",
                 "@@CHECK@@|TOTAL|7|updates available|at-least"):
        run.handle_line(w, line)
    check("INV-10 an at-least count's badge says at least",
          w.rows["system"].badge.text() == "at least 7 available")
    w.proc = QProcess(w)
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)
    check("INV-10 the check's summary says at least",
          w.status.text().startswith("At least 7 update(s) available"))
    check("INV-10 the tray hears the basis", _tray_calls == [{"at_least": True}])
    _unpatch_all()
    w = window.Updater()
    w._check_mode = True
    run.handle_line(w, "@@CHECK@@|system|0|system package(s)|at-least")
    check("INV-10 an at-least zero still reads up to date",
          w.rows["system"].badge.text() == "up to date")

    # --- 5b. CHECK_ITEM: each package reaches the package page -----------------
    # CHECK_ITEM was the one marker in handle_marker's dispatch that no GUI scenario fed,
    # so nothing proved the window still shows the packages --check emits it for.
    def _package_lines(win):
        """Every package line the current layout's views show, one string per
        package per view, its columns joined — read from the views' own models."""
        out = []
        for items in vars(win.host).values():
            if isinstance(items, package_views.PackageItems):
                for r in range(items.rowCount()):
                    out.append(" | ".join(items.data(items.index(r, c))
                                          for c in range(items.columnCount())))
        return out

    wI = window.Updater()
    wI._check_mode = True
    run.handle_line(wI, "@@CHECK_ITEM@@|system|bash|5.2.21|5.2.37")
    run.handle_line(wI, "@@CHECK_ITEM@@|system|zypper")
    _detail = _package_lines(wI)
    check("a changed package lands in the package page with both versions",
          any("bash" in t and "5.2.21" in t and "5.2.37" in t for t in _detail))
    check("a package with no version pair still lists its name",
          any("zypper" in t for t in _detail))
    _body = wI.host.bodies[0]
    check("the package page shows its view once there are packages, not the sentence",
          _body.currentWidget() is _body.content)

    # --- 5b-i. ONEUP-0259: the package model -----------------------------------
    # The engine's CHECK_ITEM and PKG lines land in one model, which the row's
    # list is drawn from. Words, never colour (INV-13); never "installed" without
    # the package's own line saying so (INV-7); never backwards (INV-9); and a
    # malformed line changes nothing (INV-8).
    def _word(state):     # the word the row shows: translated where shown
        return app.translate("steps", steps.STATE_WORDS[state])

    # ONEUP-0329 INV-5: a package the check lists as `remove` keys on its own edition,
    # so the run's `removed` line lands on the same row rather than adding a second.
    wR = window.Updater()
    run.handle_line(wR, "@@CHECK_ITEM@@|system|foo|1.0-1.1|1.0-1.1|0||remove")
    run.handle_line(wR, "@@PKG@@|system|removed|foo|1.0-1.1")
    _foo = wR.packages.packages("system")
    check("INV-5 a listed removal and the run's removed line are one row",
          [(f.name, f.state, f.change) for f in _foo] == [("foo", "removed", "remove")])
    check("INV-5 a removal reads as one",
          package_views.versions(_foo[0]) == "1.0-1.1, to be removed")
    run.handle_line(wR, "@@CHECK_ITEM@@|system|bar||2-1|0|Main|new")
    run.handle_line(wR, "@@CHECK_ITEM@@|system|baz|2-1|1-1|0|Main|downgrade")
    run.handle_line(wR, "@@CHECK_ITEM@@|system|qux|1-1|2-1|0|Main|sideways")
    _by = {f.name: f for f in wR.packages.packages("system")}
    check("a new package reads as new", package_views.versions(_by["bar"]) == "new 2-1")
    check("a downgrade keeps the arrow", package_views.versions(_by["baz"]) == "2-1 → 1-1")
    check("a change word outside the four drops the row", "qux" not in _by)

    # ONEUP-0335 (d): the run's own list carries the change too, so a removal and a
    # new package read as one from the run's first line; a word outside the four
    # drops the line, and a line with no change keeps an upgrade.
    wQ = window.Updater()
    run.handle_line(wQ, "@@PKG@@|system|queued|old|2-1|0|2-1||remove")
    run.handle_line(wQ, "@@PKG@@|system|queued|fresh|1-1|0||Main|new")
    run.handle_line(wQ, "@@PKG@@|system|queued|odd|1-1|0||Main|sideways")
    run.handle_line(wQ, "@@PKG@@|system|queued|plain|2-1|0|1-1|Main")
    _by = {f.name: f for f in wQ.packages.packages("system")}
    check("a run's queued removal reads as one",
          "old" in _by and package_views.versions(_by["old"]) == "2-1, to be removed")
    check("a run's queued new package reads as new",
          "fresh" in _by and package_views.versions(_by["fresh"]) == "new 1-1")
    check("a run's change word outside the four drops the line", "odd" not in _by)
    run.handle_line(wQ, "@@PKG@@|system|queued|odd|1-1|0||Main|sideways")
    check("and Spotlight does not name the dropped line",
          wQ.latest_package == ("system", "plain", "2-1"))
    check("a run's line with no change stays an upgrade",
          "plain" in _by and _by["plain"].change == "upgrade")

    wP = window.Updater()
    run.handle_line(wP, "@@CHECK_ITEM@@|system|vlc|3.0-1.1|3.0-2.1|222|Packman")
    _vlc = wP.packages.packages("system")
    check("ONEUP-0259 CHECK_ITEM fills the model with versions, size and source",
          len(_vlc) == 1 and (_vlc[0].old, _vlc[0].edition, _vlc[0].size, _vlc[0].repo)
          == ("3.0-1.1", "3.0-2.1", 222, "Packman"))
    _detail = _package_lines(wP)
    check("ONEUP-0259 the package page shows the size and the state as a word",
          any("222 B" in t and _word("queued") in t for t in _detail))
    _before = [(p.name, p.state) for p in wP.packages.packages()]
    for bad in ("@@PKG@@|system|installed",                 # too few fields
                "@@PKG@@|system|exploded|vlc|3.0-2.1",       # not a state
                "@@PKG@@|system|downloading|vlc|3.0-2.1|lots",   # bytes not a number
                "@@CHECK_ITEM@@|system|x|1|2|lots"):
        run.handle_line(wP, bad)
    check("ONEUP-0259 INV-8 a malformed CHECK_ITEM or PKG changes nothing",
          [(p.name, p.state) for p in wP.packages.packages()] == _before)
    for line in ("@@PKG@@|system|queued|a|1-1|0||Main",
                 "@@PKG@@|system|queued|b|1-1|0||Main",
                 "@@PKG@@|system|installed|a|1-1",
                 "@@PKG@@|system|downloaded|a|1-1"):
        run.handle_line(wP, line)
    _state = {p.name: wP.packages.shown_state(p) for p in wP.packages.packages("system")}
    check("ONEUP-0259 INV-9 a package's state never moves backwards",
          _state["a"] == "installed")
    run.handle_line(wP, "@@STEP_END@@|system|ok|installed|1")
    _state = {p.name: wP.packages.shown_state(p) for p in wP.packages.packages("system")}
    check("ONEUP-0259 INV-7 after STEP_END, only a package said to be installed reads so",
          _state["a"] == "installed" and _state["b"] == "unchanged")
    _words = [_word(state) for state in steps.STATE_WORDS]
    check("ONEUP-0259 INV-13 every state the model accepts, plus unchanged, has a word",
          set(steps.STATE_WORDS) == {*packages.STATES, "unchanged"} and all(_words))
    check("ONEUP-0259 INV-13 no two states share a word", len(set(_words)) == len(_words))
    # ONEUP-0259 INV-13's "the redrawn list shows the table's word" moved to
    # ONEUP-0239 INV-3, which reads every layout's views (ONEUP-0239 §7).
    _calls = []
    wP.packages.subscribe(_calls.append)
    run._reset_for_run(wP, ["system"], check=True)
    check("ONEUP-0259 a new check or run empties the model and says so once, with None",
          wP.packages.packages() == [] and _calls == [None]
          and _package_lines(wP) == [])

    # --- 5c. @@HINT@@ goes through the parser, not straight into _hints ---------
    # Every other hint scenario assigns w._hints directly, so the dispatch line that
    # actually populates it was never exercised by anything.
    wH = window.Updater()
    run.handle_line(wH, "@@HINT@@|repo-key-expired")
    check("a @@HINT@@ code is parsed into _hints as the window's own sentence",
          wH._hints == [markers.render_hint(["repo-key-expired"])]
          and wH._hints[0].startswith("A source's signing key is out of date."))

    # ONEUP-0343: a read can end part-way through a multi-byte character. Each half
    # decoded on its own became two U+FFFD; the stream decoder must carry the half
    # character into the next read. A CRLF split across two reads must not add a
    # blank line either.
    class _ChunkProc:  # one canned read per call, like a QProcess draining its pipe
        def __init__(self, *chunks): self._c = list(chunks)
        def readAllStandardOutput(self): return self._c.pop(0)
    wU = window.Updater()
    run._reset_for_run(wU, ["system"], check=False)
    raw = "Stopped — safely.\r\n".encode()
    cut = raw.index("—".encode()) + 1          # inside the three-byte em dash
    wU.proc = _ChunkProc(raw[:cut], raw[cut:-1], raw[-1:])
    for _ in range(3):
        run.on_output(wU)
    _logged = wU.log.toPlainText().splitlines()
    check(f"ONEUP-0343 an em dash split across two reads survives decoding ({_logged[-2:]!r})",
          "Stopped — safely." in _logged)
    check("ONEUP-0343 a CRLF split across two reads leaves no blank line",
          _logged and _logged[-1] == "Stopped — safely." and wU._buf == "")
    # ONEUP-0218: a repository is a "source" to the user (wording-and-translation.md
    # §2.1). Both signing-key hints, and the banner the window builds itself when only
    # the key-import remedy is armed, must say so.
    for code in ("repo-key-expired", "repo-key-still-rejected"):
        sentence = markers.render_hint([code])
        check(f"the {code} hint says 'source', never 'repository' (ONEUP-0218)",
              "source" in sentence and "repositor" not in sentence.lower())
    wK = window.Updater()
    run.handle_line(wK, "@@REMEDY@@|import-keys")
    wK._failed_steps = ["system"]
    wK.proc = QProcess(wK)
    # Shown, as in a real run: on a never-shown window every banner reads as hidden,
    # so the generic "Some steps did not finish" banner would overwrite this one.
    wK.show()
    run.on_finished(wK, 1, QProcess.ExitStatus.NormalExit)
    check("the key-only banner says 'source', never 'repository' (ONEUP-0218)",
          "A source's signing key is out of date." in wK.warn_label.text()
          and "repositor" not in wK.warn_label.text().lower())
    wK.hide()
    # ONEUP-0331: after a half-finished system update the warning that the system is
    # part-updated leads the summary, even where a hint arrived earlier in the run —
    # the banner shows only the first (docs/standards/testing.md §5 item 2).
    wP = window.Updater()
    run.handle_line(wP, "@@HINT@@|repo-slow|packman")
    run.handle_line(wP, "@@HINT@@|system-incomplete")
    run.handle_line(wP, "@@DONE@@|errors")
    wP._failed_steps = ["system"]
    wP.proc = QProcess(wP)
    wP.show()
    run.on_finished(wP, 1, QProcess.ExitStatus.NormalExit)
    check(f"ONEUP-0331 the part-updated warning leads, ahead of an earlier hint "
          f"({wP.warn_label.text()!r})", "partly updated" in wP.warn_label.text())
    wP.hide()
    # ONEUP-0337: the password box could not start, so the engine stops before DONE.
    # The banner still says why and offers the command to finish in a terminal.
    wQ = window.Updater()
    run.handle_line(wQ, "@@HINT@@|askpass-unavailable")
    wQ._failed_steps = ["system"]
    wQ.proc = QProcess(wQ)
    wQ.show()
    run.on_finished(wQ, 1, QProcess.ExitStatus.NormalExit)
    check(f"ONEUP-0337 a box that could not start is said in the banner "
          f"({wQ.warn_label.text()!r})",
          "could not start" in wQ.warn_label.text()
          and "sudo zypper dup" in wQ.warn_label.text())
    check("ONEUP-0337 and its command is the one Copy command copies",
          run._first_hint_command(wQ) == "sudo zypper dup")
    wQ.hide()
    # ONEUP-0256: the rest of 0218's class — the package-conflict hint and all three
    # texts of the key-import confirmation. "repo" is matched as a word, as well as
    # "repositor", because the conflict hint said "a third-party repo".
    _jargon = re.compile(r"\brepos?\b|repositor", re.IGNORECASE)
    _conflict = markers.render_hint(["package-conflict"])
    check("the package-conflict hint says 'source', never 'repo' (ONEUP-0256)",
          "source" in _conflict and not _jargon.search(_conflict))
    _seen = []

    class _CapturedBox(banners.QMessageBox):
        def exec(self):
            _seen.extend([self.windowTitle(), self.text(), self.informativeText()])
            return banners.QMessageBox.Cancel

    _patch(banners, "QMessageBox", _CapturedBox)
    _approved = banners._confirm_key_import(wK)
    _unpatch_all()
    check("the key-import dialog says 'source', never 'repository' (ONEUP-0256)",
          len(_seen) == 3 and not _approved
          and "source" in " ".join(_seen) and not any(_jargon.search(t) for t in _seen))
    # ONEUP-0222: the engine's stale-firmware-list hint has a sentence of the window's
    # own, not the unknown-code fallback.
    check("the firmware-list-stale hint has its own sentence (ONEUP-0222)",
          "firmware-list-stale" in markers.HINTS
          and markers.render_hint(["firmware-list-stale"])
          == markers.HINTS["firmware-list-stale"][1])
    check("the command a hint names is filled into its sentence (ONEUP-0235)",
          "run: sudo zypper --gpg-auto-import-keys refresh, then retry." in wH._hints[0]
          and wH._hint_commands == ["sudo zypper --gpg-auto-import-keys refresh"])
    run.handle_line(wH, "@@HINT@@|repo-slow|packman")
    check("a hint's argument is substituted into its sentence",
          "The 'packman' source is serving updates too slowly" in wH._hints[-1])

    # --- 5c-a. ONEUP-0235: a translated hint still offers Copy command -----------
    # The command is the hint's data, never found by an English cue in its sentence.
    # The stand-in translation does what a real one does: keeps the command (as the
    # {command} slot, where the source has one) and drops the English around it.
    from PySide6.QtCore import QCoreApplication, QTranslator

    class _Hebrew(QTranslator):
        def isEmpty(self):
            return False

        def translate(self, context, source, disambiguation=None, n=-1):
            # None, not "": Qt takes an empty string as a translation and blanks
            # the message, where None passes it on untranslated.
            if context != "markers" or "signing key is out of date" not in source:
                return None
            cmd = "{command}" if "{command}" in source else \
                "sudo zypper --gpg-auto-import-keys refresh"
            return f"מפתח החתימה של המאגר פג תוקף. הריצו {cmd} ואז נסו שוב."

    _he = _Hebrew()
    QCoreApplication.installTranslator(_he)
    try:
        wT = window.Updater()
        run.handle_line(wT, "@@HINT@@|repo-key-expired")
        run.handle_line(wT, "@@DONE@@|errors")
        wT.proc = QProcess(wT)
        run.on_finished(wT, 1, QProcess.ExitStatus.NormalExit)
        check("the stand-in translation reached the banner",
              "מפתח החתימה" in wT.warn_label.text())
        check("a translated hint still shows Copy command (ONEUP-0235)",
              wT.warn_copy_btn.isVisibleTo(wT.warn_banner))
        check("and copies the command itself",
              wT._hint_command == "sudo zypper --gpg-auto-import-keys refresh")
    finally:
        QCoreApplication.removeTranslator(_he)

    # --- 5c-i. ONEUP-0108 INV-1 for @@HINT@@ and @@REMEDY@@ ----------------------
    # A code the window has no entry for, or a known one whose arguments do not fit,
    # renders a sentence naming the code — never the bare token, never a throw.
    def _long_for(text, *codes):
        return (all(c in text for c in codes) and " " in text
                and len(text) >= 2 * len(" ".join(codes)))
    for _line, _code, _why in (("@@HINT@@|zzz-new-hint", "zzz-new-hint", "an unknown hint"),
                               ("@@HINT@@|repo-slow", "repo-slow", "an argument too few"),
                               ("@@HINT@@|repo-slow|a|b", "repo-slow", "an argument too many")):
        wU = window.Updater()
        run.handle_line(wU, _line)
        run.handle_line(wU, "@@HINT@@|disk-full")
        check(f"{_why} renders a sentence naming the code",
              _long_for(wU._hints[0], _code) and _code != wU._hints[0])
        check(f"{_why}: parsing continues", wU._hints[1] == markers.HINTS["disk-full"][1])
    # The three side-channel readers put a hint in front of the user away from
    # handle_marker (ONEUP-0108 §4.5); each must go through the table too.
    _shown = []
    _orig_warn = QMessageBox.warning
    _orig_reprobe = auth._query_auth_status
    QMessageBox.warning = staticmethod(lambda *a, **k: _shown.append(a[2]) or 0)
    auth._query_auth_status = lambda *a, **k: None
    try:
        wA = window.Updater()
        auth._on_auth_finished(wA, _StubProc("@@HINT@@|zzz-auth-code\n"))
        auth._on_auth_finished(wA, _StubProc("@@HINT@@|auth-write-failed|/etc/sudoers.d/oneup\n"))
        wR = window.Updater()
        rollback._on_thin_finished(wR, _StubProc("@@HINT@@|zzz-thin-code\n"))
    finally:
        QMessageBox.warning = _orig_warn
        auth._query_auth_status = _orig_reprobe
    check("the authorization reader words an unknown hint as a sentence",
          len(_shown) >= 1 and _long_for(_shown[0], "zzz-auth-code"))
    check("the authorization reader words a known hint, argument included",
          len(_shown) >= 2 and _shown[1] == "Could not write the authorization rule "
                                            "(/etc/sudoers.d/oneup).")
    check("the snapshot reader words an unknown hint as a sentence",
          len(_shown) >= 3 and _long_for(_shown[2], "zzz-thin-code"))
    wZ = window.Updater()
    wZ._size_buf = ""
    wZ._size_proc = _StubProc("@@HINT@@|zzz-size-code\n")
    run._on_size_output(wZ)
    check("the download-size reader words an unknown hint as a sentence",
          _long_for(wZ.log.toPlainText(), "zzz-size-code"))
    # An unknown REMEDY arms no button; the banner says there is no fix instead.
    wM = window.Updater()
    # No failed STEP_END here: with the window unshown, on_finished's failed-step
    # banner tests warn_banner.isVisible(), which is False, and replaces the text.
    for _ln in ("@@HINT@@|disk-full", "@@REMEDY@@|zzz-new-fix", "@@DONE@@|errors"):
        run.handle_line(wM, _ln)
    wM.proc = QProcess(wM)
    run.on_finished(wM, 1, QProcess.ExitStatus.NormalExit)
    check("an unknown REMEDY arms no button",
          not wM._remedy_keys and not wM._remedy_skips)
    check("and the banner names it, beside the run's own hint",
          "zzz-new-fix" in wM.warn_label.text()
          and markers.HINTS["disk-full"][1] in wM.warn_label.text())

    # --- 5c-ii. @@CHECK_UNKNOWN@@ carries a code (ONEUP-0072 step 5) ------------
    # The warning banner must read as it did when the engine sent English: one name,
    # two names joined ", ", a name with spaces kept whole, and each code's tail.
    _was = (" — this list may be incomplete. Running an update refreshes them.")
    for _ln, _want in (
            ("@@CHECK_UNKNOWN@@|system|sources-unreadable|packman",
             "OneUp couldn't read these software sources: packman" + _was),
            ("@@CHECK_UNKNOWN@@|system|sources-unreadable|My Repo|packman",
             "OneUp couldn't read these software sources: My Repo, packman" + _was),
            ("@@CHECK_UNKNOWN@@|system|sources-unknown-error|7",
             "OneUp couldn't read the software sources (zypper exited 7)" + _was),
            ("@@CHECK_UNKNOWN@@|flatpak|flatpak-remotes-unreachable|fedora|kde",
             "OneUp couldn't reach these Flatpak sources: fedora, kde"
             " — this list may be incomplete."),
            ("@@CHECK_UNKNOWN@@|firmware|fwupd-unreachable", "OneUp couldn't ask fwupd"),
            # Zero names is an engine defect, not a version mismatch (ONEUP-0108 §4.3).
            ("@@CHECK_UNKNOWN@@|system|sources-unreadable",
             "OneUp couldn't read these software sources: " + _was)):
        wK = window.Updater()
        run.handle_line(wK, _ln)
        check(f"CHECK_UNKNOWN words {_ln.split('|', 2)[2]!r} as before",
              wK._unchecked == [_want])
        check(f"and badges {_ln.split('|')[1]} as unknown",
              wK.rows[_ln.split("|")[1]]._badge_text == "couldn't check")
    # INV-1: an unknown code, or a fixed-arity one with the wrong count, is the long
    # fallback naming it — and the parse carries on to the next marker.
    for _ln, _code in (("@@CHECK_UNKNOWN@@|system|zzz-new-reason|x", "zzz-new-reason"),
                       ("@@CHECK_UNKNOWN@@|system|sources-unknown-error", "sources-unknown-error"),
                       ("@@CHECK_UNKNOWN@@|firmware|fwupd-unreachable|extra",
                        "fwupd-unreachable")):
        wK = window.Updater()
        run.handle_line(wK, _ln)
        run.handle_line(wK, "@@CHECK@@|TOTAL|3|updates available")
        check(f"CHECK_UNKNOWN {_code!r} out of table is the long fallback",
              len(wK._unchecked) == 1 and _long_for(wK._unchecked[0], _code))
        check(f"and parsing continues after {_code!r}", wK._installed_count == "3")

    # --- 5d. the download-size side channel ------------------------------------
    # A separate QProcess from the main run, with its own parser. The engine half is
    # covered in tests/run-tests.sh; this is the window half.
    wS = window.Updater()
    wS._size_buf = ""
    wS._size_proc = _StubProc("weighing things up\n@@SIZE@@|system|412 MB\n")
    run._on_size_output(wS)
    # The link and its result are one window-level slot since ONEUP-0239 §4.6.
    check("a SIZE marker reaches the download-size slot",
          "412 MB" in wS.size_link.size_result.text())
    # isVisibleTo(the slot) isolates the button's own visibility from the window's.
    check("a SIZE marker retires the 'Show download size' link",
          not wS.size_link.size_btn.isVisibleTo(wS.size_link))
    check("a SIZE marker records that the slot now carries a size",
          wS.size_link.has_size())
    check("a non-marker line from the size probe is logged",
          "weighing things up" in wS.log.toPlainText())

    # Exit 0 with no SIZE marker means the solver found nothing to fetch — but a
    # non-zero exit must NEVER be reported as "nothing to download". Same
    # never-claim-what-you-didn't-earn rule the engine's step tests enforce.
    wS0 = window.Updater()
    run._on_size_finished(wS0, 0, None)
    check("size probe exiting 0 with no marker reports nothing to download",
          wS0.size_link.size_result.text() == "Nothing to download")
    wS1 = window.Updater()
    run._on_size_finished(wS1, 1, None)
    check("a failed size probe never claims a size it didn't earn",
          not wS1.size_link.has_size())

    # ONEUP-0300: on the service route the size costs no password, so the link is
    # hidden and a check that found system updates fetches it unasked — asking
    # polkit with no box (ONEUP_NONINTERACTIVE=1), so a policy wanting a password
    # fails quietly and the link comes back. The sudo route keeps today's link.
    _launched = []
    _orig_argv, _orig_route = paths.engine_argv, auth.service_route

    def _after_check(service, system_n):
        auth.service_route = lambda: service
        try:
            wA = window.Updater()
        finally:
            auth.service_route = _orig_route
        hidden = not wA.size_link.size_btn.isVisibleTo(wA.size_link)
        _launched.clear()
        wA._check_mode = True
        for line in (f"@@CHECK@@|system|{system_n}", f"@@CHECK@@|TOTAL|{system_n}"):
            run.handle_line(wA, line)
        wA.proc = QProcess(wA)
        run.on_finished(wA, 0, QProcess.ExitStatus.NormalExit)
        sized = [env for argv, env in _launched if "--size=system" in argv]
        proc = getattr(wA, "_size_proc", None)
        if proc is not None:
            proc.waitForFinished(5000)
            QApplication.processEvents()
        return wA, hidden, sized

    paths.engine_argv = lambda *a, env=None: (
        _launched.append((a, env or {})) or ["sh", "-c", "echo aborting-noise; exit 1"])
    try:
        wA, hidden, sized = _after_check(True, 3)
        check("ONEUP-0300 the service route hides the 'Show download size' link", hidden)
        check(f"ONEUP-0300 a check with system updates fetches the size unasked, with no "
              f"password box ({sized})",
              len(sized) == 1 and sized[0].get("ONEUP_NONINTERACTIVE") == "1")
        check("ONEUP-0300 a failed unasked fetch brings the link back",
              wA.size_link.size_btn.isVisibleTo(wA.size_link)
              and wA.size_link.size_btn.isEnabled() and not wA.size_link.has_size())
        check("ONEUP-0300 a failed unasked fetch writes nothing to the log",
              "aborting-noise" not in wA.log.toPlainText())
        _w, _h, sized = _after_check(True, 0)
        check(f"ONEUP-0300 nothing is fetched when the system is up to date ({sized})",
              not sized)
        _w, hidden, sized = _after_check(False, 3)
        check("ONEUP-0300 the sudo route keeps the link", not hidden)
        check(f"ONEUP-0300 the sudo route fetches nothing unasked ({sized})", not sized)
    finally:
        paths.engine_argv, auth.service_route = _orig_argv, _orig_route

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

    # ONEUP-0333: a real run (2026-10-23) on the service route said "approve the password
    # popup" for a minute while polkit allowed it silently and no popup ever came. Only
    # a run that will really prompt may ask for one. `true` stands in for the engine:
    # the status line is set before the process starts.
    _real_argv = paths.engine_argv
    paths.engine_argv = lambda *_a: ["true"]
    for _label, _service, _passwordless, _prompts in (
            ("the service route", True, False, False),
            ("the sudo route with passwordless on", False, True, False),
            ("the sudo route with passwordless off", False, False, True)):
        wA = window.Updater()
        wA._service_route = _service
        # Signals blocked: toggling it for real opens the passwordless confirmation box.
        wA.auth_btn.blockSignals(True)
        wA.auth_btn.setChecked(_passwordless)
        wA.auth_btn.blockSignals(False)
        run._launch(wA, ["system"], check=False)
        _said = wA.status.text()
        check(f"ONEUP-0333 {_label} {'asks' if _prompts else 'does not ask'} for a "
              f"password popup ({_said!r})", ("password popup" in _said) == _prompts)
        wA.proc.waitForFinished(5000)
    paths.engine_argv = _real_argv

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

    # ONEUP-0156: a go.request that cannot be written must be reported ONCE. The wait
    # timer used to retry the failed write every tick, and each retry raised another
    # modal box, which on a full or read-only state directory the user could not
    # dismiss their way out of. Staged through the wait path, because that is the loop:
    # Update is pressed before the hold exists, then the hold appears.
    wW = window.Updater()
    wW._size_proc = _SizeProc(27182)
    wW._hold_log = paths.STATE_LOG_DIR / "full-disk.log"
    paths.HOLD_STATE.unlink(missing_ok=True)
    _warnings, _launched = [], []
    _real_warning, _real_go = QMessageBox.warning, paths.GO_REQUEST
    QMessageBox.warning = staticmethod(lambda *a, **k: _warnings.append(a) or 0)
    # A parent that is a file, not a directory: every write under it fails, as on a
    # full or read-only state directory.
    paths.GO_REQUEST = Path(os.devnull) / "go.request"
    run._launch = lambda w, st, check, **kw: _launched.append((list(st), check))
    try:
        run.start_run(wW)
        paths.HOLD_STATE.write_text(f"27182\n{wW._hold_log}\n412 MB\n")
        for _ in range(3):
            if wW._hold_wait.isActive():
                run._hold_wait_tick(wW)
        check("ONEUP-0156 a failed go-ahead write is reported once, not per tick",
              len(_warnings) == 1)
        check("ONEUP-0156 the wait stops once the write has failed",
              not wW._hold_wait.isActive())
        check("ONEUP-0156 and the window falls back to a fresh engine (INV-7)",
              len(_launched) == 1 and _launched[0][1] is False)
    finally:
        QMessageBox.warning = _real_warning
        paths.GO_REQUEST = _real_go
        run._launch = _real_launch
    paths.HOLD_STATE.unlink(missing_ok=True)

    # ONEUP-0266: once the size is known the preview engine HOLDS, alive for up to two
    # minutes so Update can adopt it. `_launch`'s guard read "alive" as "still working
    # out the size", so Check for updates said so and refused. A check never asks for a
    # password, so it may run beside a hold; it still waits while the size is being
    # worked out, because both drive zypper. A retry IS a run, so it still waits — but
    # says why. `log_dir_ready` returning False stops `_launch` just past the guard, so
    # no engine is started and the guard's decision is the whole of what is measured.
    wH = window.Updater()               # built before the stubs: its start-up probe
    wH._size_proc = _SizeProc(14142)    # reads log_dir_ready(quiet=True) for real
    _boxes, _reached = [], []
    _real_info, _real_ready = QMessageBox.information, paths.log_dir_ready
    QMessageBox.information = staticmethod(lambda *a, **k: _boxes.append(a[2]) or 0)
    paths.log_dir_ready = lambda *_a, **_k: _reached.append(True) and False

    def _guard(win, check):
        del _boxes[:], _reached[:]
        run._launch(win, ["system"], check=check)
        return (_boxes[0] if _boxes else None), bool(_reached)

    try:
        paths.HOLD_STATE.write_text(f"14142\n{paths.STATE_LOG_DIR / 'h.log'}\n104.5 MiB\n")
        _box, _went = _guard(wH, check=True)
        check("ONEUP-0266 Check for updates runs while a known size is held",
              _box is None and _went)
        _box, _went = _guard(wH, check=False)
        check("ONEUP-0266 a retry still waits while the size is held",
              _box is not None and not _went)
        check("ONEUP-0266 and does not claim the size is still being worked out",
              _box is not None and "working out" not in _box)
        paths.HOLD_STATE.unlink(missing_ok=True)
        _box, _went = _guard(wH, check=True)
        check("ONEUP-0266 Check still waits while the size is being worked out",
              _box is not None and "working out" in _box and not _went)
        # A hold another engine left behind is not ours, so the size is not known yet.
        paths.HOLD_STATE.write_text(f"424242\n{paths.STATE_LOG_DIR / 'x.log'}\n1 MB\n")
        _box, _went = _guard(wH, check=True)
        check("ONEUP-0266 a hold.state from another engine does not count as ours",
              _box is not None and not _went)
    finally:
        QMessageBox.information = _real_info
        paths.log_dir_ready = _real_ready
    paths.HOLD_STATE.unlink(missing_ok=True)

    # ONEUP-0238: a waiting window says what it waits for and how long it has waited, so
    # nobody closes it believing nothing is happening (the user's rule, 2026-10-08). The
    # clock counts up, because the dry run's length cannot be known in advance.
    wC = window.Updater()
    wC._size_proc = _SizeProc(16180)
    paths.HOLD_STATE.unlink(missing_ok=True)
    _launched = []
    run._launch = lambda w, st, check, **kw: _launched.append((list(st), check))
    _real_monotonic = time.monotonic
    try:
        run.start_run(wC)
        _first = wC.status.text()
        _start = _real_monotonic()
        time.monotonic = lambda: _start + 65.2   # as if the dry run had run a while
        run._hold_wait_tick(wC)
        time.monotonic = _real_monotonic
        _later = wC.status.text()
        check("ONEUP-0238 the wait names what it is waiting for", "download size" in _first)
        check("ONEUP-0238 the wait shows how long it has waited so far",
              "so far" in _first and "1m 5s so far" in _later)
        check("ONEUP-0238 a tick keeps waiting rather than starting a second engine",
              wC._hold_wait.isActive() and not _launched)
    finally:
        time.monotonic = _real_monotonic
        if getattr(wC, "_hold_wait", None) is not None:
            wC._hold_wait.stop()
        run._launch = _real_launch

    # --- 5e. --thin-snapshots outcomes -----------------------------------------
    # Each branch decides whether the advisory banner stays up for a retry — and, since
    # ONEUP-0230, each says how it went in ONE message box closed with OK: the status line
    # alone was easy to miss, and a failure with no hint said nothing at all.
    _boxes = []
    _orig_info, _orig_warn = QMessageBox.information, QMessageBox.warning
    QMessageBox.information = staticmethod(lambda *a, **k: _boxes.append(("info", a[2])) or 0)
    QMessageBox.warning = staticmethod(lambda *a, **k: _boxes.append(("warn", a[2])) or 0)
    try:
        for _out, _want, _banner_stays, _box, _says in (
                ("@@SNAPSHOTS@@|thinned|7\n", "7", False, "info", "7"),
                ("@@SNAPSHOTS@@|thinned|0\n", "No old snapshots", False, "info",
                 "No old snapshots"),
                ("", "Ready.", True, "warn", "not thinned"),
                ("@@HINT@@|zzz-thin-code\n", "Ready.", True, "warn", "zzz-thin-code")):
            _label = _out.strip() or "(no marker — cancelled or error)"
            wT = window.Updater()
            wT._warn_snapshots = True
            wT.warn_banner.setVisible(True)
            # Move the status off its constructor default first. It is built as
            # QLabel("Ready."), which is exactly what the no-marker branch sets — so
            # without this the third case would pass even if that branch never ran.
            wT.status.setText("(the handler did not set this)")
            _boxes.clear()
            rollback._on_thin_finished(wT, _StubProc(_out))
            check(f"thin {_label}: status reports it", _want in wT.status.text())
            check(f"thin {_label}: banner still up = {_banner_stays}",
                  wT.warn_banner.isVisibleTo(wT) is _banner_stays)
            check(f"thin {_label}: one {_box} box saying so (ONEUP-0230)",
                  len(_boxes) == 1 and _boxes[0][0] == _box and _says in _boxes[0][1])
    finally:
        QMessageBox.information, QMessageBox.warning = _orig_info, _orig_warn

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

    # ONEUP-0344: any other error arrives while the engine is still running (or just
    # ending, when `finished` follows). Treating it as a failed start deleted the
    # QProcess, and deleting a running QProcess kills the engine mid-transaction.
    wE2 = window.Updater()
    wE2.proc = QProcess(wE2)
    wE2.set_controls_enabled(False)
    wE2.status.setText("Updating system packages…")
    run.on_error(wE2, QProcess.ProcessError.ReadError)
    check("ONEUP-0344 a read error mid-run is not reported as a failed start",
          "Could not start" not in wE2.status.text())
    check("ONEUP-0344 a read error mid-run leaves the run controls locked",
          not wE2.run_btn.isEnabled())

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
    # its own file gets oneup/gui/, so the engine would not be found and Run would
    # fail; and a systemd unit built from a package module's __file__ would
    # run `python3 …/oneup/gui/autostart.py --check`, which does nothing whatever, on a
    # weekly timer nobody watches.
    # ONEUP-0054 stage 9 replaced `paths.ENGINE` with a resolver; INV-4 is now that the
    # checkout arm finds the engine package under HERE and puts HERE on PYTHONPATH.
    paths._reset_engine_cache()
    _argv = paths.engine_argv("--help")
    check("the engine resolves from the repo root (INV-4)",
          paths.engine_available() and _argv[0] == "env"
          and _argv[1].split("=", 1)[1].split(os.pathsep)[0] == str(REPO)
          and _argv[2:] == [sys.executable, "-m", "oneup.engine", "--help"])
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

    # --- ONEUP-0054 stage 9: the AppImage runs a copy of the engine outside its bundle.
    # The bundle's mount goes when the window exits, so an engine read from inside it
    # could lose its own files mid-run (INV-5). Faked here: sys.frozen set, HERE a
    # sandbox holding the source the build puts under engine-src/, state sandboxed.
    _fz = Path(tempfile.mkdtemp(dir=_SANDBOX))
    _src = _fz / "engine-src" / "oneup"
    (_src / "engine").mkdir(parents=True)
    shutil.copyfile(REPO / "oneup" / "__init__.py", _src / "__init__.py")
    for _f in (REPO / "oneup" / "engine").glob("*.py"):
        shutil.copyfile(_f, _src / "engine" / _f.name)
    _copies_dir = _fz / "state" / "engine"
    _saved = (paths.HERE, paths.STATE_DIR, paths.shutil.which, sys.__dict__.get("frozen"),
              os.environ.pop("LD_LIBRARY_PATH_ORIG", None))
    paths.HERE, paths.STATE_DIR, sys.frozen = _fz, _fz / "state", True
    try:
        paths._reset_engine_cache()
        _a = paths.engine_argv("--help")
        _copies = sorted(_copies_dir.iterdir())
        check("the frozen arm copies the engine source out of the bundle",
              len(_copies) == 1 and (_copies[0] / "oneup" / "engine" / "__main__.py").is_file())
        check("and runs the machine's python3 from that copy",
              f"PYTHONPATH={_copies[0]}" in _a and _a[-3:] == ["-m", "oneup.engine", "--help"])
        check("and removes the bundle's LD_LIBRARY_PATH",
              _a[:3] == ["env", "-u", "LD_LIBRARY_PATH"])
        check("INV-10 (ONEUP-0249) and forces the sudo route",
              "ONEUP_BACKEND=sudo" in _a[:_a.index("-m")])
        os.environ["ONEUP_BACKEND"] = "service"
        _act = Path(tempfile.mkstemp(dir=_SANDBOX)[1])
        _saved_act, route_mod.ACTIVATION_FILE = route_mod.ACTIVATION_FILE, str(_act)
        try:
            check("INV-10 so the window keeps the switch even where the service is installed",
                  paths.engine_environ()["ONEUP_BACKEND"] == "sudo" and not auth.service_route())
        finally:
            route_mod.ACTIVATION_FILE = _saved_act
            os.environ["ONEUP_BACKEND"] = "sudo"
        # Run from outside the repo: `-m` puts the working directory first on the
        # path, so from the repo root the checkout's own package would answer.
        _help = subprocess.run(_a, capture_output=True, text=True,  # noqa: S603
                               timeout=60, cwd=_fz)
        check("the copied engine answers --help",
              _help.returncode == 0 and "Usage:" in _help.stdout)
        paths._reset_engine_cache()
        paths.engine_argv()
        check("a second resolve reuses the copy", sorted(_copies_dir.iterdir()) == _copies)
        os.environ["LD_LIBRARY_PATH_ORIG"] = "/orig/lib"
        check("an original LD_LIBRARY_PATH is restored instead",
              paths.engine_argv()[:2] == ["env", "LD_LIBRARY_PATH=/orig/lib"])
        os.environ.pop("LD_LIBRARY_PATH_ORIG")
        with (_src / "engine" / "markers.py").open("a") as _fh:
            _fh.write("\n# one more byte\n")
        paths.engine_argv()
        check("an edited source gets a copy of its own", len(list(_copies_dir.iterdir())) == 2)
        paths.shutil.which = lambda _name: None
        paths._reset_engine_cache()
        _err = io.StringIO()
        with contextlib.redirect_stderr(_err):
            _avail = paths.engine_available()
            paths.engine_available()
            _tried = paths.engine_tried()
        check("with no usable python3 the engine is unavailable", not _avail)
        check("and what was tried names the interpreter", "python3 of 3.13 or newer" in _tried)
        check("and stderr says so once, not per call", _err.getvalue().count("not found") == 1)
    finally:
        paths.HERE, paths.STATE_DIR, paths.shutil.which = _saved[0], _saved[1], _saved[2]
        if _saved[3] is None:
            del sys.frozen
        else:
            sys.frozen = _saved[3]
        if _saved[4] is not None:
            os.environ["LD_LIBRARY_PATH_ORIG"] = _saved[4]
        paths._reset_engine_cache()

    # INV-18 (ONEUP-0249, ONEUP-0286): the window follows the engine's PackageKit check,
    # so a computer without PackageKit keeps the Passwordless switch. The suite pins
    # ONEUP_BACKEND=sudo and may lack jeepney; either would answer before the check.
    _saved_backend = os.environ.pop("ONEUP_BACKEND", None)
    _saved_jeepney = sys.modules.get("jeepney")
    sys.modules["jeepney"] = types.ModuleType("jeepney")
    _act = Path(tempfile.mkstemp(dir=_SANDBOX)[1])
    _saved_act, route_mod.ACTIVATION_FILE = route_mod.ACTIVATION_FILE, str(_act)
    _saved_check = route_mod.__dict__.get("packagekit_registered")
    try:
        route_mod.packagekit_registered = lambda _environ: False
        check("INV-18 (ONEUP-0249) without PackageKit's action the window keeps the switch",
              not auth.service_route())
        route_mod.packagekit_registered = lambda _environ: True
        check("INV-18 and with it the window follows the service route", auth.service_route())
    finally:
        if _saved_check is None:
            route_mod.__dict__.pop("packagekit_registered", None)
        else:
            route_mod.packagekit_registered = _saved_check
        route_mod.ACTIVATION_FILE = _saved_act
        if _saved_jeepney is None:
            sys.modules.pop("jeepney", None)
        else:
            sys.modules["jeepney"] = _saved_jeepney
        if _saved_backend is not None:
            os.environ["ONEUP_BACKEND"] = _saved_backend

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
    _read_py_paths = (f"import sys;sys.path.insert(0, {str(REPO)!r});"
                      "import oneup.engine.runstate as R;print(R.RUN_STATE);print(R.STOP_REQUEST)")
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
        # The Python engine is the one the window runs since ONEUP-0054 stage 9; the
        # Bash comparison above stays while update_system.sh ships as the fallback.
        _py = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _read_py_paths],
            capture_output=True, text=True, env=_env).stdout.split()
        check(f"window and Python engine agree on run.state / stop.request ({_label})",
              len(_py) == 2 and _py == _win)

    # --- ONEUP-0061: a 1.x settings file is still honoured ------------------------
    # 1.x keeps its preferences in ~/.config/OneUp/OneUp.conf, through
    # QSettings("OneUp", "OneUp"). Renaming that organisation to the app ID would make
    # 2.0 read an empty file and silently reset every upgrading user's choices. A fresh
    # process gets a config directory holding only the file 1.x writes — this process's
    # QSettings has long since cached its own — and the window must pick every key up.
    _old = Path(tempfile.mkdtemp(dir=_SANDBOX))
    (_old / "config" / "OneUp").mkdir(parents=True)
    (_old / "config" / "OneUp" / "OneUp.conf").write_text(
        "[General]\nhigh_contrast=true\nlog_shown=false\ntext_scale=1.45\ntray_enabled=true\n")
    _read_old = (
        f"import sys;sys.path.insert(0, {str(REPO)!r})\n"
        "from PySide6.QtWidgets import QApplication\n"
        "from oneup.gui import theme, window\n"
        "app = QApplication([])\n"
        "theme.apply_app_theme(app)\n"
        "w = window.Updater()\n"
        "print(w.tray_btn.isChecked(), w.contrast_btn.isChecked(),\n"
        "      w.package_area.currentWidget() is w.log, w.host.LAYOUT_ID,\n"
        "      w._text_scale_index(),\n"
        "      'qproperty-highContrast: true' in app.styleSheet())\n")
    _old_env = {"HOME": str(_old), "XDG_CONFIG_HOME": str(_old / "config"),
                "XDG_STATE_HOME": str(_old / "state"), "PATH": os.environ["PATH"],
                "QT_QPA_PLATFORM": "offscreen",
                # PySide6 may sit in the user's own site-packages, which a new HOME hides.
                "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    _seen = subprocess.run(  # noqa: S603 — the running interpreter, a fixed script.
        [sys.executable, "-c", _read_old],
        capture_output=True, text=True, env=_old_env, timeout=60).stdout.split()
    # `log_shown` is deliberately no longer read: the window opens on the packages
    # every launch, and a 1.x user gets Rows, the default (ONEUP-0239 §3).
    check("a 1.x OneUp.conf is honoured: tray, contrast, text size, stylesheet; "
          "it opens on the packages, in Rows",
          _seen == ["True", "True", "False", "rows", "2", "True"])
    # The window's own reads are not every reader: the tray decision at start-up and the
    # repository dialog's size build their own QSettings. Each must name the same file.
    _orgs = sorted({m for _f in (REPO / "oneup" / "gui").glob("*.py")
                    for m in re.findall(r"QSettings\(([^)]*)\)", _f.read_text())})
    check("every QSettings in the window package names the 1.x file",
          _orgs == ['"OneUp", "OneUp"'])

    # --- ONEUP-0077: the timers' two headless paths build their own notification ----
    # A mock engine stands in for the real one through the resolver, so no real check or
    # update runs (docs/standards/testing.md §2): it records its argv, prints what the
    # case gives it and exits with the case's status. The mock notify-send on PATH
    # records each notification.
    _mock_engine = os.path.join(_SANDBOX, "mock-engine.py")
    with open(_mock_engine, "w") as _f:
        _f.write("import os, sys\n"
                 "open(os.environ['ONEUP_MOCK_ARGV'], 'w').write('\\n'.join(sys.argv[1:]))\n"
                 "open(os.environ['ONEUP_MOCK_ARGV'] + '.env', 'w')"
                 ".write(os.environ.get('ONEUP_NONINTERACTIVE', 'unset'))\n"
                 "sys.stdout.write(open(os.environ['ONEUP_MOCK_OUT']).read())\n"
                 "sys.exit(int(os.environ.get('ONEUP_MOCK_RC', '0')))\n")
    _mock_env = {"ONEUP_MOCK_ARGV": os.path.join(_SANDBOX, "mock-engine.argv"),
                 "ONEUP_MOCK_OUT": os.path.join(_SANDBOX, "mock-engine.out")}
    def _mock_resolve():
        return [sys.executable, _mock_engine], ["the mock engine"]

    def _headless(fn, lines, rc=0):
        """Run one headless path against the mock; (exit, engine argv, stdout, notes)."""
        with open(_mock_env["ONEUP_MOCK_OUT"], "w") as f:
            f.write("".join(f"{ln}\n" for ln in lines))
        with contextlib.suppress(FileNotFoundError):
            os.remove(_NOTIFY_LOG)
        saved = {k: os.environ.get(k) for k in (*_mock_env, "ONEUP_MOCK_RC")}
        os.environ.update(_mock_env, ONEUP_MOCK_RC=str(rc))
        _patch(paths, "_resolve_engine", _mock_resolve)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = fn()
        finally:
            _unpatch_all()
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        argv = Path(_mock_env["ONEUP_MOCK_ARGV"]).read_text().split("\n")
        notes = (Path(_NOTIFY_LOG).read_text().splitlines()
                 if os.path.exists(_NOTIFY_LOG) else [])
        return code, argv, out.getvalue(), notes

    def _is_note(notes, key):
        """Exactly one notification, and it is that table entry's title."""
        head = f"-a OneUp -i {gui_app.APP_ID} {markers.NOTIFICATIONS[key][0]} "
        return len(notes) == 1 and notes[0].startswith(head)

    # INV-2: each path's argv, field by field — no --notify, no --update, a --log= under
    # the window's own log folder, and --auto-skip-repos still on the update path.
    _stamp = r"\d{4}-\d\d-\d\d_\d{6}"
    _c, _argv, _, _ = _headless(gui_app._headless_check, ["@@CHECK@@|TOTAL|0|updates available"])
    check("INV-2 --check argv is --check and a log under LOG_DIR, nothing else",
          len(_argv) == 2 and _argv[0] == "--check"
          and re.fullmatch(rf"--log={re.escape(str(paths.STATE_LOG_DIR))}/{_stamp}\.check\.log",
                           _argv[1]) is not None)
    _c, _argv, _, _ = _headless(gui_app._headless_update, ["@@DONE@@|ok"])
    check("INV-16 (ONEUP-0249) a timer run tells the engine nobody is there to ask",
          Path(_mock_env["ONEUP_MOCK_ARGV"] + ".env").read_text() == "1")
    check("INV-2 --update argv is --auto-skip-repos and a log under LOG_DIR, nothing else",
          len(_argv) == 2 and _argv[0] == "--auto-skip-repos"
          and re.fullmatch(rf"--log={re.escape(str(paths.STATE_LOG_DIR))}/{_stamp}\.log",
                           _argv[1]) is not None)

    # INV-1 and INV-7: DONE decides, never the exit status; with no DONE the run did
    # not finish. A stopped run exits 0 and is its own entry, never a success.
    for _done, _key in (("ok", "run.uptodate"), ("errors", "run.failed"),
                        ("stopped", "run.stopped"), (None, "run.failed")):
        for _rc in (0, 1):
            _lines = ["@@INSTALLED@@|0|no|no"] + ([f"@@DONE@@|{_done}"] if _done else [])
            _c, _, _, _notes = _headless(gui_app._headless_update, _lines, _rc)
            check(f"INV-7 DONE={_done} exit={_rc} notifies {_key}", _is_note(_notes, _key))
            check(f"and returns the engine's exit status ({_rc})", _c == _rc)
    _c, _argv, _, _notes = _headless(gui_app._headless_update,
                                     ["@@INSTALLED@@|0|no|no", "@@DONE@@|stopped"])
    check("INV-1 a stopped run with nothing installed names the log, not 'up to date'",
          _is_note(_notes, "run.stopped") and _argv[1].removeprefix("--log=") in _notes[0])
    _c, _, _, _notes = _headless(gui_app._headless_update,
                                 ["@@INSTALLED@@|7|yes|no", "@@DONE@@|stopped"])
    check("INV-7 a stopped run that installed something is still never a success",
          _is_note(_notes, "run.stopped"))
    # The rest of the fall-through, and the set-aside note on exactly three texts.
    _c, _, _, _notes = _headless(gui_app._headless_update,
                                 ["@@REPO_SKIPPED@@|games|unreachable",
                                  "@@INSTALLED@@|7|yes|no", "@@DONE@@|ok"])
    check("an installed count reads as the engine wrote it, with the set-aside source",
          _is_note(_notes, "run.installed")
          and _notes[0].endswith("7 system package(s) installed. "
                                 "(skipped: games — will retry next time)"))
    _c, _, _, _notes = _headless(gui_app._headless_update,
                                 ["@@INSTALLED@@|0|no|yes", "@@DONE@@|ok"])
    check("firmware alone reads 'Updates were installed.'",
          _is_note(_notes, "run.changed") and _notes[0].endswith("Updates were installed."))
    _c, _, _, _notes = _headless(gui_app._headless_update,
                                 ["@@REPO_SKIPPED@@|games|x", "@@DONE@@|errors"])
    check("a failure never carries the set-aside note", _is_note(_notes, "run.failed")
          and "skipped:" not in _notes[0])

    # INV-3: --check is silent only on a zero total with every source read.
    _c, _, _, _notes = _headless(gui_app._headless_check, ["@@CHECK@@|TOTAL|0|updates available"])
    check("INV-3 a clean zero is silent", _notes == [])
    _c, _, _, _notes = _headless(gui_app._headless_check, ["@@CHECK@@|TOTAL|3|updates available"])
    check("INV-3 a non-zero total notifies, as the engine worded it",
          _is_note(_notes, "check.available")
          and _notes[0].endswith("3 update(s) ready to install. Open OneUp to update."))
    _c, _, _, _notes = _headless(gui_app._headless_check,
                                 ["@@CHECK_UNKNOWN@@|system|sources-unreadable|packman",
                                  "@@CHECK@@|TOTAL|0|updates available"])
    check("INV-3 an unreadable source with a zero total notifies and names it",
          _is_note(_notes, "check.partial") and "packman" in _notes[0])
    _c, _, _, _notes = _headless(gui_app._headless_check,
                                 ["@@CHECK_UNKNOWN@@|system|sources-unreadable|packman",
                                  "@@CHECK@@|TOTAL|4|updates available"])
    check("INV-3 an unreadable source beside a count gives both",
          _is_note(_notes, "check.partial_count") and "packman" in _notes[0]
          and "4 update(s)" in _notes[0])
    # ONEUP-0329 INV-10: the weekly notification says at least for a floor.
    _c, _, _, _notes = _headless(gui_app._headless_check,
                                 ["@@CHECK@@|TOTAL|7|updates available|at-least"])
    check("INV-10 an at-least total notifies with at least",
          _is_note(_notes, "check.available_at_least")
          and _notes[0].endswith("At least 7 update(s) ready to install. Open OneUp to update."))
    _c, _, _, _notes = _headless(gui_app._headless_check,
                                 ["@@CHECK@@|TOTAL|0|updates available|at-least"])
    check("INV-10 an at-least zero is silent", _notes == [])

    # INV-6: every line the engine prints reaches this path's stdout, in order.
    _plain = ["Refreshing repository 'oss'…", "  Hint: kept as the engine wrote it"]
    for _fn, _lines in ((gui_app._headless_update,
                         [_plain[0], "@@INSTALLED@@|0|no|no", _plain[1], "@@DONE@@|ok"]),
                        (gui_app._headless_check,
                         [_plain[0], "@@CHECK@@|TOTAL|0|x", _plain[1]])):
        _c, _, _out, _ = _headless(_fn, _lines)
        check(f"INV-6 {_fn.__name__} writes every engine line back out, in order",
              _out.splitlines() == _lines)

    # INV-4: no tray message on either path — only the notification service.
    _trays = []

    class _RecordingTray(tray.QSystemTrayIcon):
        def __init__(self, *a, **kw):
            _trays.append(1)
            super().__init__(*a, **kw)

    for _fn, _lines in ((gui_app._headless_update, ["@@INSTALLED@@|2|yes|no", "@@DONE@@|ok"]),
                        (gui_app._headless_check, ["@@CHECK@@|TOTAL|2|x"])):
        _patch(tray, "QSystemTrayIcon", _RecordingTray)
        _patch(gui_app, "QSystemTrayIcon", _RecordingTray)
        try:
            _c, _, _, _notes = _headless(_fn, _lines)
        finally:
            _unpatch_all()
        check(f"INV-4 {_fn.__name__} raised its notification through notify-send",
              len(_notes) == 1)
    check("INV-4 and constructed no tray icon on either path", _trays == [])

    # ONEUP-0032 INV-9 (it replaced ONEUP-0077's INV-5, which asserted the opposite):
    # in a process of its own, each path builds an application object and offers the
    # catalogues BEFORE it composes its sentence. The child reports both itself, at
    # the moment the sentence is composed, because a clean exit would prove nothing.
    _child = (
        "import os, sys\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})\n"
        "from PySide6.QtCore import QCoreApplication\n"
        "from oneup.gui import app, i18n, markers, paths\n"
        f"paths._resolve_engine = lambda: ([sys.executable, {_mock_engine!r}], ['mock'])\n"
        "seen = []\n"
        "def spy(real):\n"
        "    def wrapped(*a, **kw):\n"
        "        seen.append(QCoreApplication.instance() is not None and i18n.called)\n"
        "        return real(*a, **kw)\n"
        "    return wrapped\n"
        "markers.run_notification = spy(markers.run_notification)\n"
        "markers.check_notification = spy(markers.check_notification)\n"
        "getattr(app, sys.argv[1])()\n"
        "print('READY' if seen == [True] else f'NOT-READY {seen}')\n")
    for _name, _lines in (("_headless_update", ["@@INSTALLED@@|2|yes|no", "@@DONE@@|ok"]),
                          ("_headless_check", ["@@CHECK@@|TOTAL|2|x"])):
        with open(_mock_env["ONEUP_MOCK_OUT"], "w") as _f:
            _f.write("".join(f"{ln}\n" for ln in _lines))
        with contextlib.suppress(FileNotFoundError):
            os.remove(_NOTIFY_LOG)
        _r = subprocess.run(  # noqa: S603 — this interpreter, a fixed script.
            [sys.executable, "-c", _child, _name], capture_output=True, text=True,
            # The suite rewrites HOME, which hides a per-user PySide6 from a fresh
            # interpreter; the child gets this one's module search path instead.
            env={**os.environ, **_mock_env, "ONEUP_MOCK_RC": "0",
                 "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}, timeout=60)
        check(f"INV-9 {_name} has an application object and loaded the catalogues "
              "before its sentence", _r.returncode == 0 and _r.stdout.rstrip().endswith("READY"))
        check(f"INV-9 and still raised its notification ({_name})", _wait_for_notify())

    # --- ONEUP-0032 INV-2 and INV-4: the catalogue pair, and the translators' life ---
    # A hand-written catalogue compiled with pyside6-lrelease — a freshly extracted one
    # translates nothing — loaded for a left-to-right language with both directories
    # pointed at throwaway copies, never at a real Qt installation.
    _lrelease = shutil.which("pyside6-lrelease")
    if not _lrelease:
        print("  SKIP - INV-2/INV-4 need pyside6-lrelease, which is not installed")
    else:
        import gc

        from PySide6.QtCore import QCoreApplication, QLocale
        _i18n_dir = tempfile.mkdtemp(dir=_SANDBOX)

        def _qm(name, context, source, translation):
            ts = os.path.join(_i18n_dir, f"{name}.ts")
            with open(ts, "w") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'
                        '<TS version="2.1" language="de_DE"><context>'
                        f"<name>{context}</name><message><source>{source}</source>"
                        f"<translation>{translation}</translation></message>"
                        "</context></TS>\n")
            # The tool is a Python script; under the rewritten HOME it needs this
            # interpreter's module path to find PySide6, as INV-9's child does.
            subprocess.run([_lrelease, ts, "-qm", ts[:-3] + ".qm"],  # noqa: S603
                           capture_output=True, check=True,
                           env={**os.environ,
                                "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)})
            return ts[:-3] + ".qm"

        _ours_qm = _qm("oneup_de", "I18nTest", "Hello", "Hallo")
        _qt_qm = _qm("qtbase_de", "I18nQtTest", "Yes", "Ja")
        _locale = QLocale()
        QLocale.setDefault(QLocale("de_DE"))
        try:
            for _ours, _qt, _want in ((True, True, True), (False, True, False),
                                      (True, False, False), (False, False, False)):
                _o, _q = tempfile.mkdtemp(dir=_SANDBOX), tempfile.mkdtemp(dir=_SANDBOX)
                if _ours:
                    shutil.copy(_ours_qm, _o)
                if _qt:
                    shutil.copy(_qt_qm, _q)
                _got = i18n.load(_o, _q)
                _ours_on = QCoreApplication.translate("I18nTest", "Hello") == "Hallo"
                _qt_on = QCoreApplication.translate("I18nQtTest", "Yes") == "Ja"
                _label = f"ours={'yes' if _ours else 'no'} qtbase={'yes' if _qt else 'no'}"
                check(f"INV-2 {_label}: installed only as a pair",
                      _got is _want and _ours_on is _want and _qt_on is _want)
                if _want:
                    gc.collect()
                    check("INV-4 the installed catalogue still translates after gc.collect()",
                          QCoreApplication.translate("I18nTest", "Hello") == "Hallo")
                i18n.unload()
            check("INV-2 unloading leaves the window in English",
                  QCoreApplication.translate("I18nTest", "Hello") == "Hello")
        finally:
            i18n.unload()
            QLocale.setDefault(_locale)

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

    # --- The start-up version check can be switched off (ONEUP-0191) -------------
    # OneUp asked GitHub for a newer version at every start, login included, with no
    # way to decline. The switch defaults on; off, a new window must not ask.
    check("Settings dialog hosts the new-version-check toggle", w.appcheck_btn in hosted)
    _stub_check = app_update._check_app_update
    asked = []
    app_update._check_app_update = lambda self, manual=False: asked.append(manual)
    try:
        w.settings.remove("app_update_check")
        w_on = window.Updater()
        check("the new-version check defaults on, and a window started with it on asks",
              w_on.appcheck_btn.isChecked() and asked == [False]
              and w_on.appcheck_btn.text() == "New-version check: on")
        w_on.appcheck_btn.setChecked(False)
        check("switching the new-version check off is remembered",
              w_on.settings.value("app_update_check", True, type=bool) is False
              and w_on.appcheck_btn.text() == "New-version check: off")
        asked.clear()
        w_off = window.Updater()
        check("a window started with the new-version check off does not ask GitHub",
              not w_off.appcheck_btn.isChecked() and asked == [])
    finally:
        app_update._check_app_update = _stub_check
        w.settings.remove("app_update_check")

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

    # (h) ONEUP-0178: a probe asked for while another is still running must not be
    # dropped. The window's startup probe is in flight when the user enables automatic
    # updates; the grant succeeds and asks for a fresh probe. The startup probe's answer
    # predates the grant, so letting it consume the latch reverts the toggle.
    w = window.Updater()
    if getattr(w, "_authstat_proc", None) is not None:
        w._authstat_proc.waitForFinished(5000)       # settle the real startup probe first
    installed_h = []
    _patch(autostart, "_install_user_timer", lambda *a, **k: (installed_h.append(a) or True))

    class _Running:
        def state(self): return QProcess.Running

    w._authstat_proc = _Running()                    # a probe that started before the grant
    auth._query_auth_status(w)                       # the grant's re-probe arrives
    reprobes = []
    _patch(auth, "_query_auth_status", lambda win: reprobes.append(1))
    w._pending_autoupdate = True
    auth._on_auth_status_finished(w, _StubProc("@@AUTH@@|off\n"))   # the pre-grant answer
    check("ONEUP-0178: a stale probe's answer does not consume the enable latch",
          w._pending_autoupdate is True and not installed_h)
    check("ONEUP-0178: a probe dropped while one ran is asked again", reprobes == [1])
    auth._on_auth_status_finished(w, _StubProc("@@AUTH@@|on\n"))    # the fresh answer
    check("ONEUP-0178: the fresh answer installs the update timer", bool(installed_h))
    _unpatch_all()

    # (i) ONEUP-0249 §4.10: on a service install the switch gives way to one line, and
    # automatic updates follow polkit's answer, which OneUp cannot grant. Each window is
    # built with the route forced, since the suite pins ONEUP_BACKEND=sudo.
    _infos = []
    QMessageBox.information = staticmethod(lambda *a, **k: _infos.append(a[1:]) or 0)
    _patch(auth, "service_route", lambda: True)
    wS = window.Updater()
    _unpatch_all()
    _dlgS = settings_dialog.SettingsDialog(wS)
    check("ONEUP-0249 a service install shows the permission line in Settings",
          "software-update permission" in getattr(_dlgS, "service_note", QLabel()).text())
    check("ONEUP-0249 and lays out no Passwordless switch",
          wS.auth_btn.window() is not _dlgS and wS.auth_btn not in _dlgS.focus_chain())
    check("ONEUP-0249 and its automatic-update row does not name Passwordless",
          not any("passwordless" in lbl.text().lower() for lbl in _dlgS.findChildren(QLabel)))
    wP = window.Updater()
    _dlgP = settings_dialog.SettingsDialog(wP)
    check("ONEUP-0249 the sudo route keeps the switch",
          not hasattr(_dlgP, "service_note") and wP.auth_btn in _dlgP.focus_chain())

    _asked, _consent, _installed_i = [], [], []
    _patch(auth, "_query_auth_status", lambda win: _asked.append(1))
    _patch(auth, "_confirm_passwordless", lambda win, lead="": _consent.append(1) or False)
    _patch(autostart, "_install_user_timer", lambda *a, **k: (_installed_i.append(a) or True))
    auth._set_auth_checked(wS, False)
    autostart.on_autoupdate_toggled(wS, True)
    check("ONEUP-0249 enabling automatic updates asks polkit, never offers a grant",
          _asked == [1] and not _consent and wS._pending_autoupdate is True)
    auth._on_auth_status_finished(wS, _StubProc("@@AUTH@@|off\n"))
    check("ONEUP-0249 a no from polkit installs no timer and says why",
          not _installed_i and not wS.autoupdate_btn.isChecked()
          and any("password" in str(i) for i in _infos))
    _unpatch_all()

    # The old drop-in: offered once on a service install, never on the sudo route.
    _offers, _revokes = [], []
    _orig_exec = QMessageBox.exec
    QMessageBox.exec = lambda self: _offers.append(self.text()) or QMessageBox.Ok
    _patch(auth, "_run_auth", lambda win, action, text, env=None: _revokes.append((action, env)))
    try:
        Path(auth.OLD_GUARDS[1]).write_text("guard\n")
        auth.offer_old_dropin_removal(wP)
        check("ONEUP-0249 the sudo route never offers to remove its own rule", not _offers)
        wS.settings.remove("old_dropin_offered")
        auth.offer_old_dropin_removal(wS)
        check("ONEUP-0249 a guard on a service install brings the offer",
              len(_offers) == 1 and "Passwordless" in _offers[0])
        check("ONEUP-0249 removing runs --revoke-auth on the sudo route",
              _revokes == [("--revoke-auth", {"ONEUP_BACKEND": "sudo"})])
        auth.offer_old_dropin_removal(wS)
        check("ONEUP-0249 the offer comes once", len(_offers) == 1)
        Path(auth.OLD_GUARDS[1]).unlink()
        wS.settings.remove("old_dropin_offered")
        with contextlib.suppress(FileNotFoundError):
            os.remove(_SUDO_LOG)
        auth.offer_old_dropin_removal(wS)
        _sudo_calls = Path(_SUDO_LOG).read_text() if os.path.exists(_SUDO_LOG) else ""
        check("ONEUP-0249 with no guard, sudo is asked only to list (-n -l)",
              _sudo_calls.startswith("-n -l") and _sudo_calls.count("\n") == 1)
        check("ONEUP-0249 and its refusal brings no offer", len(_offers) == 1)

        # ONEUP-0293: a general password-free rule lets zypper run too, but it is not
        # OneUp's. The listings are the shape sudo 1.9.17 printed in the clean VM.
        _zypper = shutil.which("zypper")
        _general = ("User linux may run the following commands on localhost:\n"
                    "    (ALL) ALL\n    (ALL) NOPASSWD: ALL\n")
        _oneup = (f"    (root) NOPASSWD: {_zypper}, /usr/bin/snapper, /usr/bin/env "
                  "LC_ALL\\=C zypper *, /usr/libexec/oneup-download-guard\n")
        # In the VM, `which` found /bin/zypper while sudo listed /usr/bin/zypper, one
        # file through Tumbleweed's /bin -> /usr/bin link.
        _linked = os.path.join(_SANDBOX, "linked-bin")
        with contextlib.suppress(FileExistsError):
            os.symlink(os.path.dirname(_zypper), _linked)
        for _listing, _want, _name in (
                (_general, 0, "a general NOPASSWD: ALL rule brings no offer"),
                (_general + _oneup, 1, "OneUp's own rule beside it brings the offer"),
                (f"    (ALL) ALL\n    (root) NOPASSWD: {_linked}/zypper\n", 1,
                 "OneUp's rule naming zypper through a linked directory brings the offer"),
                (f"User linux may run:\n    (ALL) ALL\n    (root) {_zypper}\n", 0,
                 "a zypper rule that asks for a password brings no offer")):
            Path(_SUDO_LIST).write_text(_listing)
            wS.settings.remove("old_dropin_offered")
            _offers.clear()
            auth.offer_old_dropin_removal(wS)
            check(f"ONEUP-0293 {_name}", len(_offers) == _want)

        # ONEUP-0280: the removal's own finish says whether the rule went. Only that
        # run's: another --revoke-auth finishing says nothing extra.
        _warns = []
        QMessageBox.warning = staticmethod(lambda *a, **k: _warns.append(a[1:]) or 0)
        _patch(auth, "_query_auth_status", lambda win: None)
        _removal = _StubProc("")
        for _present, _name in ((False, "removed"), (True, "still there")):
            _infos.clear()
            _warns.clear()
            _patch(auth, "_old_dropin_present", lambda p=_present: p)
            wS._old_dropin_proc = _removal
            auth._on_auth_finished(wS, _removal)
            _said = [str(m) for m in _infos + _warns]
            check(f"ONEUP-0280 a removal that left the rule {_name} says so",
                  len(_said) == 1 and ("still" in _said[0]) == _present
                  and (bool(_warns) == _present))
        _infos.clear()
        _warns.clear()
        wS._old_dropin_proc = _removal
        auth._on_auth_finished(wS, _StubProc(""))
        check("ONEUP-0280 another auth run finishing says nothing about the old rule",
              not _infos and not _warns)
        _infos.clear()
        _warns.clear()
        _explained = _StubProc("@@HINT@@|auth-remove-failed|/etc/sudoers.d/oneup\n")
        wS._old_dropin_proc = _explained
        auth._on_auth_finished(wS, _explained)
        check("ONEUP-0280 a failure the engine explained is not said twice",
              len(_warns) == 1 and not _infos)
    finally:
        QMessageBox.exec = _orig_exec
        wS.settings.remove("old_dropin_offered")
        with contextlib.suppress(FileNotFoundError):
            os.remove(_SUDO_LIST)
        _unpatch_all()

    QMessageBox.information = _orig_msg_info
    QMessageBox.warning = _orig_msg_warn

    # --- 6. the About dialog opens and closes without error --------------------
    w = window.Updater()
    check("About button exists in the header", hasattr(w, "about_btn"))
    # show_about() runs a modal exec(); schedule a close so the test doesn't block.
    _about_text = []
    def _dismiss_about():
        for tl in app.topLevelWidgets():
            if isinstance(tl, QMessageBox) and tl.isVisible():
                _about_text.append(tl.informativeText())
                tl.done(0)
    QTimer.singleShot(50, _dismiss_about)
    try:
        w.show_about()
        check("About dialog opens and dismisses cleanly", True)
    except Exception as exc:  # noqa: BLE001
        check(f"About dialog opens and dismisses cleanly ({exc})", False)
    # The project's house disclaimer, 2026-10-16: OneUp is not openSUSE's or SUSE's.
    check("About says OneUp is not an official openSUSE or SUSE product",
          bool(_about_text) and "not an official openSUSE or SUSE product" in _about_text[0]
          and "not endorsed by the openSUSE Project or SUSE" in _about_text[0])

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

    # ONEUP-0157: one copy of a duplicated URL always stays.
    dlg_f = repos.RepoManagerDialog(None, parsed)
    dlg_f._mark_removed(dlg_f._rows[1])
    check("removing one copy disables Remove on the last copy",
          not dlg_f._rows[2]["rm"].isEnabled())
    dlg_f._mark_removed(dlg_f._rows[2])
    check("the last copy of a URL cannot be marked for removal",
          dlg_f._rows[2]["remove"] is False
          and "removerepo debug-dup" not in (dlg_f._build_apply_command() or ["", "", "", ""])[3])

    # ONEUP-0157: a failed apply re-reads the machine and says what it found.
    def _failed_apply(code, now_repos):
        d = repos.RepoManagerDialog(None, parsed)
        said = []
        _w, _r = QMessageBox.warning, repos.read_repos
        QMessageBox.warning = staticmethod(lambda _p, _t, text, *a, **k: said.append(text))
        repos.read_repos = lambda: now_repos
        try:
            d._on_applied(code, None)
        finally:
            QMessageBox.warning, repos.read_repos = _w, _r
        return d, " ".join(said)
    half = [dict(r) for r in parsed]
    half[0]["enabled"] = False                  # the disable landed ...
    # ... the remove didn't:
    half = [r for r in half if r["alias"] != "debug-dup"] + [dict(parsed[2])]
    d, said = _failed_apply(1, half)
    check("a half-applied change is reported as partly applied",
          "Some of the changes were applied" in said and "cancelled" not in said)
    check("after a half-applied change the rows show the real state",
          d._rows[0]["switch"].isChecked() is False)
    _d, said = _failed_apply(126, [dict(r) for r in parsed])
    check("a dismissed prompt with nothing changed says so",
          "Nothing was changed" in said and "cancelled" in said)
    _d, said = _failed_apply(1, [dict(r) for r in parsed])
    check("a failure that changed nothing does not blame a cancel",
          "Nothing was changed" in said and "cancelled" not in said)
    _d, said = _failed_apply(1, [])
    check("an unreadable result claims neither outcome",
          "couldn't re-read" in said)

    # ONEUP-0157: a rollback reports which half failed instead of saying nothing.
    wr = window.Updater()
    wr._snapshot = "42"
    started, said = [], []
    _warn, _info, _start = QMessageBox.warning, QMessageBox.information, QProcess.start
    QMessageBox.warning = staticmethod(
        lambda _p, _t, text, *a, **k: (said.append(text), QMessageBox.Yes)[1])
    QMessageBox.information = staticmethod(lambda _p, _t, text, *a, **k: said.append(text))
    QProcess.start = lambda self, prog, args=None, *a, **k: started.append([prog, *(args or [])])
    try:
        rollback.rollback(wr)
        check("rollback gives each half its own exit code",
              bool(started) and started[0][-1]
              == "snapper rollback 42 || exit 3; systemctl reboot || exit 4")
        for code, want in ((126, "cancelled"), (3, "couldn't roll back"),
                           (4, "restart failed"), (9, "exit code 9")):
            said.clear()
            rollback._on_rollback_finished(wr, code, "42")
            check(f"rollback exit {code} is explained", want in " ".join(said))
        said.clear()
        rollback._on_rollback_finished(wr, 0, "42")
        check("a rollback that is restarting says nothing", said == [])
    finally:
        QMessageBox.warning, QMessageBox.information, QProcess.start = _warn, _info, _start

    # --- failure-hint "Copy command" ------------------------------------------
    # The command is each hint's data (ONEUP-0235). A hint telling the user to run
    # something must take it from HINT_COMMANDS through {command}: one typed into the
    # sentence would show, and never reach the Copy button.
    _typed = [c for c, (_a, s) in markers.HINTS.items()
              if "run: " in s and "{command}" not in s]
    check("no hint types a command into its sentence instead of {command}", _typed == [])
    _stray = [c for c in markers.HINT_COMMANDS
              if c not in markers.HINTS or "{command}" not in markers.HINTS[c][1]]
    check("every hint command belongs to a hint whose sentence names it", _stray == [])
    check("a hint that names no command offers none",
          markers.hint_command(["disk-full"]) == ""
          and markers.hint_command(["zzz-new-hint"]) == ""
          and markers.hint_command(["repo-key-expired", "extra"]) == "")
    w = window.Updater()
    banners._show_warning(w, "Something failed — run it, then retry.", "sudo zypper refresh")
    check("copy button appears when a hint carries a command",
          w.warn_copy_btn.isVisibleTo(w.warn_banner)
          and w._hint_command == "sudo zypper refresh")
    banners._show_warning(w, "Low disk space — free some room and retry.")
    check("copy button hidden when a hint carries no command",
          not w.warn_copy_btn.isVisibleTo(w.warn_banner))
    try:
        banners._show_warning(w, "Retry.", "sudo zypper refresh")
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
          _drawn(w.warn_btn.text()) == "Import signing key & retry")

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

    # ONEUP-0158: an entry installed by an older copy names an executable an AppImage
    # upgrade deleted, so start-at-boot and the timer stop while their toggles read on.
    # A window starting up rewrites any installed entry that names something else.
    # The daemon-reload is spied, so the suite never reaches the user's systemd.
    stale_ap = autostart._autostart_path()
    stale_ap.parent.mkdir(parents=True, exist_ok=True)
    stale_ap.write_text('[Desktop Entry]\nExec="/gone/OneUp-1.4.5.AppImage" --tray\n')
    units = autostart._user_units_dir()
    units.mkdir(parents=True, exist_ok=True)
    stale_svc = units / "oneup-check.service"
    stale_svc.write_text('[Service]\nExecStart="/gone/OneUp-1.4.5.AppImage" --check\n')
    reloads = []
    _orig_run = autostart.subprocess.run

    def _spy_run(args, *a, **k):
        if list(args[:3]) == ["systemctl", "--user", "daemon-reload"]:
            reloads.append(args)
            return autostart.subprocess.CompletedProcess(args, 0)
        return _orig_run(args, *a, **k)

    autostart.subprocess.run = _spy_run
    try:
        window.Updater()
        check("ONEUP-0158: a stale start-at-boot entry is rewritten at startup",
              f"Exec={autostart._autostart_exec()}\n" in stale_ap.read_text())
        check("ONEUP-0158: a stale timer service is rewritten at startup",
              f"ExecStart={autostart._headless_command('--check')}\n"
              in stale_svc.read_text())
        check("ONEUP-0158: a rewritten service reloads systemd once", len(reloads) == 1)
        check("ONEUP-0158: a timer that was never installed is not created",
              not (units / "oneup-update.service").exists())
        reloads.clear()
        window.Updater()
        check("ONEUP-0158: entries already current are left alone", not reloads)
    finally:
        autostart.subprocess.run = _orig_run
        stale_ap.unlink(missing_ok=True)
        stale_svc.unlink(missing_ok=True)

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
    # ONEUP-0329 INV-10: the tray reads the TOTAL's basis, and words it.
    tray._parse_tray_line(w, "@@CHECK@@|TOTAL|7|updates available|at-least")
    check("INV-10 tray keeps an at-least total's basis", w._tray_at_least is True)
    check("INV-10 tray tooltip says at least",
          tray._tooltip(7, at_least=True).endswith("at least 7 update(s) waiting"))
    check("INV-10 tray tooltip at zero says up to date",
          tray._tooltip(0, at_least=True).endswith("up to date"))
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

    # (11b) ONEUP-0246: the window reopens where it was left. On Wayland Qt cannot read its
    # own position (it reports 0,0), so the window asks KWin for its frame before it hides
    # and replays it on the next show. Quit from the tray menu never reaches closeEvent, so
    # before this item it saved nothing at all.
    from PySide6.QtCore import QSettings
    _gs = QSettings("OneUp", "OneUp")
    def _pump(ms, until=lambda: False):
        # Waits on the condition, not a fixed time: the replay is a 50 ms timer, and a
        # loaded run reached it only after 200 ms.
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end and not until():
            QApplication.processEvents()
            time.sleep(0.005)
    w = window.Updater()
    w.show()
    _gs.remove("geometry")
    _patch(window.QApplication, "quit", lambda: None)
    w._quit_requested()
    check("ONEUP-0246: Quit from the tray saves the window's size", _gs.contains("geometry"))
    _unpatch_all()
    w.hide()

    asked = []
    def _frame():
        asked.append(True)
        return (333, 222)
    _patch(placement, "_platform_name", lambda: "wayland")
    _patch(placement, "main_frame_position", _frame)
    _patch(placement, "run_kwin_script", lambda js: True)   # nothing reaches the real KWin
    _gs.remove("frame_pos")
    w = window.Updater()
    w._tray = object()
    w.show()
    w.closeEvent(_Evt())
    check("ONEUP-0246: on Wayland, closing to the tray saves KWin's frame position",
          _gs.value("frame_pos") == "333,222")
    asked.clear()
    _patch(window.QApplication, "quit", lambda: None)
    w._quit_requested()
    check("ONEUP-0246: a hidden window does not ask KWin, which no longer knows it",
          asked == [] and _gs.value("frame_pos") == "333,222")
    _unpatch_all()

    scripts = []
    _patch(placement, "_platform_name", lambda: "wayland")
    _patch(placement, "run_kwin_script", lambda js: scripts.append(js) or True)
    _gs.setValue("frame_pos", "333,222")
    w = window.Updater()
    w.show()
    _pump(3000, until=lambda: not w._placement_pending)
    placed = [js for js in scripts if "var x = 333" in js and "var y = 222" in js]
    check("ONEUP-0246: on Wayland the saved position is replayed through KWin once per show",
          len(placed) == 1)
    check("ONEUP-0246: the replay clamps to the usable area with KWin.PlacementArea",
          bool(placed) and "KWin.PlacementArea" in placed[0])
    w.hide()
    w.show()
    _pump(3000, until=lambda: not w._placement_pending)
    check("ONEUP-0246: showing again from the tray replays it again",
          len([js for js in scripts if "var x = 333" in js]) == 2)
    w.hide()
    _unpatch_all()

    scripts = []
    _patch(placement, "_platform_name", lambda: "xcb")
    _patch(placement, "run_kwin_script", lambda js: scripts.append(js) or True)
    w = window.Updater()
    w.show()
    _pump(100)
    check("ONEUP-0246: off Wayland nothing is sent to KWin (restoreGeometry places it)",
          scripts == [])
    w.hide()
    _unpatch_all()
    _gs.remove("frame_pos")

    check("ONEUP-0246: KWin's answer is read from its own marked journal line",
          placement._frame_from_journal("noise\nkwin: oneup_frame_ab 1447 -12\n",
                                        "oneup_frame_ab") == (1447, -12))
    check("ONEUP-0246: an answer that is not two numbers is no position",
          placement._frame_from_journal("oneup_frame_ab here there\n", "oneup_frame_ab")
          is None and placement._frame_from_journal("", "oneup_frame_ab") is None)

    # (12) on_finished refreshes the tray: a successful run -> neutral; a check -> the count.
    w = window.Updater()
    applied = []
    _patch(tray, "_apply_tray_total", lambda win, n, uncertain=False, **_: applied.append(n))
    w.proc = QProcess(w)
    w._installed_count = "2"
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)     # a run
    check("successful run sets the tray neutral", applied and applied[-1] == 0)
    w = window.Updater()
    applied2 = []
    _patch(tray, "_apply_tray_total", lambda win, n, uncertain=False, **_: applied2.append(n))
    w._check_mode = True
    w._installed_count = "5"
    w.proc = QProcess(w)
    run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)     # a check
    check("finished check pushes the count to the tray", applied2 and applied2[-1] == 5)
    _unpatch_all()

    # ONEUP-0345: a run or check that left out a step the tray counts knows nothing
    # about that step's updates, so it must not reset the tray to "up to date".
    for _mode in (False, True):
        w = window.Updater()
        applied3 = []
        _patch(tray, "_apply_tray_total",
               lambda win, n, uncertain=False, a=applied3, **_: a.append(n))
        w.rows["flatpak"].switch.setChecked(False)
        w._check_mode = _mode
        w._installed_count = "0"
        w.proc = QProcess(w)
        run.on_finished(w, 0, QProcess.ExitStatus.NormalExit)
        check(f"ONEUP-0345 a {'check' if _mode else 'run'} without flatpak leaves the "
              "tray count alone", applied3 == [])
        w.rows["flatpak"].switch.setChecked(True)
        _unpatch_all()

    # (12b) ONEUP-0056: a check that couldn't read a source knows nothing about it,
    # and "I don't know" must never reach the user as "Everything is up to date. 🎉".
    # That exact false all-clear shipped: the window said it while 8 updates waited,
    # because the sources holding them had been silently skipped.
    w = window.Updater()
    _patch(tray, "_apply_tray_total", lambda win, n, uncertain=False, **_: None)
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
    _patch(tray, "_apply_tray_total", lambda win, n, uncertain=False, **_: None)
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
        "@@CHECK_UNKNOWN@@|system|sources-unreadable|packman")
    tray._parse_tray_line(w, "@@CHECK@@|TOTAL|0|updates available")
    check("tray records the qualified total", w._tray_total == 0)
    check("tray flagged the check as uncertain", w._traycheck_unknown is True)

    # --- ONEUP-0025: repo resilience — skip_repos threads through to the engine ---
    args = run._engine_args(["system"], check=False, import_keys=False,
                                        skip_repos=["google-chrome"])
    check("skip_repos adds one --skip-repo per alias", "--skip-repo=google-chrome" in args)
    check("no skip_repos → no --skip-repo flag",
          "--skip-repo" not in " ".join(run._engine_args(["system"], check=False)))

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
        # ONEUP-0144: the alias goes back to the engine as `--skip-repo=`, so the window
        # checks it at the marker boundary too. `-` first would be an option, not a name.
        run.handle_line(w, "@@REMEDY@@|skip-repo|--plus-content")
        check("an unsafe skip-repo alias is not armed", w._remedy_skips == ["google-chrome"])
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
              _drawn(w2.warn_btn.text()) == "Skip Google Chrome & update the rest")
        check("both remedies armed: second button offers the key-import fix",
              w2.warn_btn2.isVisibleTo(w2.warn_banner)
              and _drawn(w2.warn_btn2.text()) == "Import signing key & retry")

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
              _drawn(w3.warn_btn.text()) == "Import signing key & retry")
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
    # ONEUP-0159: openSUSE host names are often words the log also uses, so the scrub
    # matches the name only where it stands alone, never inside a longer token or path.
    _short = _build("1", "x", [], "r.log",
                    "repo-oss refreshed\nhttps://download.opensuse.org/tumbleweed/repo/oss/ ok\n"
                    "oss sudo[42]: session opened\nreached oss.lan\n",
                    "w", "", "oss")
    check("diagnostics: a host name inside a repo alias survives (ONEUP-0159)",
          "repo-oss refreshed" in _short)
    check("diagnostics: a host name inside a URL path survives (ONEUP-0159)",
          "/repo/oss/ ok" in _short)
    check("diagnostics: a standalone host name is still scrubbed (ONEUP-0159)",
          "<host> sudo[42]" in _short and "<host>.lan" in _short)
    check("diagnostics: a host name prefixing a package name survives (ONEUP-0159)",
          "linux-firmware updated" in _build("1", "x", [], "r.log", "linux-firmware updated",
                                             "w", "", "linux"))
    check("diagnostics: no-run placeholder shown",
          "no update has been run yet" in _build("1", "x", [], None, None, "w", "", ""))
    _big = "H" * 20 + "T" * (diagnostics.DIAG_LOG_CAP + 3000)
    _trim = _build("1", "x", [], "b.log", _big, "w", "", "")
    check("diagnostics: oversized log trimmed to its tail",
          "earlier output trimmed" in _trim and "H" * 20 not in _trim)

    # --- ONEUP-0082: old run logs are pruned, never the live run's or the newest -------
    # The log folder grows by one file per run, and the weekly timers write unattended,
    # so every path that makes the folder prunes it by age. Ages are set with utime: the
    # file's own name carries a timestamp too, and pruning must not read that instead.
    _orig_dir, _orig_rs = paths.STATE_LOG_DIR, paths.RUN_STATE
    with tempfile.TemporaryDirectory() as _pd:
        _pdp = Path(_pd)
        paths.STATE_LOG_DIR, paths.RUN_STATE = _pdp / "logs", _pdp / "run.state"
        paths.STATE_LOG_DIR.mkdir()
        _now = time.time()

        def _aged(name: str, days: float) -> Path:
            _p = paths.STATE_LOG_DIR / name
            _p.write_text("x")
            os.utime(_p, (_now - days * 86400, _now - days * 86400))
            return _p

        try:
            _stale = _aged("2026-01-01_100000.check.log", 40)
            _fresh = _aged("2026-02-01_100000.check.log", 2)
            _live = _aged("2026-01-02_100000.log", 50)      # a run still going
            _newest = _aged("2026-01-03_100000.log", 45)    # the newest real run
            _older = _aged("2026-01-01_090000.log", 60)
            paths.RUN_STATE.write_text(f"{os.getpid()}\n{_live}\nsystem\n")
            from PySide6.QtCore import QSettings
            _gs82 = QSettings("OneUp", "OneUp")
            _gs82.remove("log_keep_days")
            check("ONEUP-0082: making the log folder succeeds", paths.log_dir_ready(quiet=True))
            check("ONEUP-0082: a log older than the default 30 days is deleted",
                  not _stale.exists() and not _older.exists())
            check("ONEUP-0082: a recent log is kept", _fresh.exists())
            check("ONEUP-0082: the running run's log is kept, however old", _live.exists())
            check("ONEUP-0082: the newest update-run log is kept, however old",
                  _newest.exists())
            _mid = _aged("2026-01-10_100000.check.log", 20)
            _gs82.setValue("log_keep_days", 14)
            paths.log_dir_ready(quiet=True)
            check("ONEUP-0082: the Settings choice sets the age", not _mid.exists())
            _mid = _aged("2026-01-10_100000.check.log", 20)
            _gs82.setValue("log_keep_days", "nonsense")
            paths.log_dir_ready(quiet=True)
            check("ONEUP-0082: an unreadable choice falls back to 30 days", _mid.exists())
            paths.RUN_STATE.write_bytes(b"\xff\xfe not text\n")
            check("ONEUP-0082: a garbled run.state does not stop the log folder being made",
                  paths.log_dir_ready(quiet=True))
            _gs82.setValue("log_keep_days", 9)
            check("ONEUP-0082: a value not on offer falls back to 30 days",
                  paths.log_keep_days(_gs82.value("log_keep_days")) == 30)
        finally:
            _gs82.remove("log_keep_days")
            paths.STATE_LOG_DIR, paths.RUN_STATE = _orig_dir, _orig_rs
    # The control: a button that cycles, as Text size does, and shows the choice.
    w82 = window.Updater()
    w82.settings.remove("log_keep_days")
    w82._refresh_logkeep_label()
    check("ONEUP-0082: Keep logs starts at 30 days", "30" in w82.logkeep_btn.text())
    w82.logkeep_btn.click()
    check("ONEUP-0082: clicking Keep logs stores and shows the next choice",
          w82.settings.value("log_keep_days", type=int) == 90 and "90" in w82.logkeep_btn.text())
    for _ in range(len(paths.LOG_KEEP_DAYS) - 1):
        w82.logkeep_btn.click()
    check("ONEUP-0082: Keep logs cycles round to where it began",
          w82.settings.value("log_keep_days", type=int) == 30)
    w82.settings.remove("log_keep_days")
    _sd82 = settings_dialog.SettingsDialog(w82)
    check("ONEUP-0082: Keep logs is in the Settings dialog and its tab order",
          w82.logkeep_btn.window() is _sd82 and w82.logkeep_btn in _sd82.focus_chain())
    _sd82.reject()

    # --- ONEUP-0184: a bad saved value or an unwritable disk degrades, never raises ----
    # (a) a log rotated away between the glob and the stat is skipped, not raised.
    with tempfile.TemporaryDirectory() as _ld:
        _ldp = Path(_ld)
        (_ldp / "2026-07-24_120000.log").write_text("x")
        (_ldp / "2026-07-24_130000.log").symlink_to(_ldp / "gone")   # stat() raises
        try:
            _got = diagnostics._latest_run_log(_ldp)
        except OSError:
            _got = "raised"
        check("ONEUP-0184: a log that vanished mid-call is skipped",
              _got == _ldp / "2026-07-24_120000.log")
    # (b) a corrupt saved geometry opens the dialog and the window at their defaults.
    from PySide6.QtCore import QSettings
    _gs = QSettings("OneUp", "OneUp")
    _gs.setValue("repos_geometry", "not a geometry")
    _gs.setValue("geometry", "not a geometry")
    try:
        _dg = repos.RepoManagerDialog(None, [])
        _ok = (_dg.width(), _dg.height()) == (780, 560)
        window.Updater()
    except TypeError:
        _ok = False
    finally:
        _gs.remove("repos_geometry")
        _gs.remove("geometry")
    check("ONEUP-0184: a corrupt saved geometry does not stop a dialog or the window opening",
          _ok)
    # (c) a write that fails part-way leaves the previous file, and no temporary behind.
    with tempfile.TemporaryDirectory() as _wd:
        _target = Path(_wd) / "unit.service"
        _target.write_text("old")
        _orig_replace = paths.os.replace
        paths.os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
        try:
            getattr(paths, "write_whole", lambda p, t: p.write_text(t[:3]))(
                _target, "new contents")
        except OSError:
            pass
        finally:
            paths.os.replace = _orig_replace
        check("ONEUP-0184: a failed write keeps the previous file whole",
              _target.read_text() == "old" and sorted(os.listdir(_wd)) == ["unit.service"])
    # (d) an unwritable log folder leaves every launcher's state as it was.
    _orig_logdir = paths.STATE_LOG_DIR
    _blocker = Path(tempfile.mkstemp()[1])          # a FILE, so mkdir under it fails
    paths.STATE_LOG_DIR = _blocker / "logs"
    warned = []
    _orig_warn = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a[1]) or 0)
    try:
        wF = window.Updater()
        raised = False
        try:
            auth._set_auth_checked(wF, True)            # the user just switched it on
            auth._run_auth(wF, "--grant-auth", "Setting up…")
            run.request_size(wF, "system")
            run._launch(wF, ["system"], check=True)
            tray._tray_check(wF)
        except OSError:
            raised = True
        check("ONEUP-0184: an unwritable log folder raises out of no launcher", not raised)
        check("ONEUP-0184: a failed grant puts the password toggle back and re-enables it",
              not wF.auth_btn.isChecked() and wF.auth_btn.isEnabled())
        check("ONEUP-0184: a user action that could not start says so", len(warned) == 3)
        check("ONEUP-0184: a run that could not start leaves no run in progress",
              wF.proc is None or wF.proc.state() == QProcess.NotRunning)
    finally:
        paths.STATE_LOG_DIR = _orig_logdir
        QMessageBox.warning = _orig_warn
        _blocker.unlink(missing_ok=True)

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

    # ONEUP-0182: the month name comes from the user's locale, in the day-month-year
    # layout the user chose (2026-10-02); Python's %b is always the C locale's "Mar".
    from PySide6.QtCore import QLocale
    _orig_locale = QLocale()
    QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Germany))
    try:
        paths.HISTORY.write_text(window.json.dumps(
            {"when": "2026-03-05T14:05:00", "status": "OK"}))
        wN.refresh_last_run()
        _month = QLocale().monthName(3, QLocale.FormatType.ShortFormat)
        check("the last-run date names the month in the user's locale",
              _month != "Mar" and f"05 {_month} 2026, 14:05" in wN.last_run.text())
    finally:
        QLocale.setDefault(_orig_locale)

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
    def shape_pixels(checked: bool, knob_end: bool = False) -> int:
        s = toggle_switch.ToggleSwitch()
        s.setChecked(checked)
        s._anim.stop()                      # settle the 130 ms knob slide first
        s.set_knob_pos(1.0 if checked else 0.0)
        img = s.grab().toImage()
        # The state shape sits opposite the knob: at the LEFT when on in a
        # left-to-right window, at the right when on in a mirrored one (ONEUP-0032
        # §8); `knob_end` samples the knob's own third instead. Picking the third
        # from `checked` alone would look in the wrong place
        # on the -reverse pass, or pass without having looked at the shape.
        at_left = (checked != QApplication.isRightToLeft()) != knob_end
        xs = range(0, img.width() // 3) if at_left else \
             range(img.width() * 2 // 3, img.width())
        # Middle rows only. The grab paints the window background outside the
        # track's rounded ends, and that background is near-white too: counted
        # over the full height, each outer third held ~84 such pixels with no
        # shape at all, so `> 0` could not fail (measured 2026-10-02).
        n = 0
        for x in xs:
            for y in range(img.height() // 3, img.height() * 2 // 3):
                c = img.pixelColor(x, y)
                if c.red() > 200 and c.green() > 200 and c.blue() > 200:
                    n += 1
        return n

    check("switch 'on' is shown by a shape, not only by green", shape_pixels(True) > 0)
    check("switch 'off' is shown by a shape, not only by red", shape_pixels(False) > 0)
    # The knob is white as well, so a knob at the wrong end would sit in the
    # sampled third and pass the two checks above. Its own end must be the whiter.
    for _on in (True, False):
        check(f"the knob sits at the {'on' if _on else 'off'} end for the reading direction",
              shape_pixels(_on, knob_end=True) > shape_pixels(_on))

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
    # `outline: none` is allowed: it switches the desktop style's ring OFF (ONEUP-0304).
    outlines = set(re.findall(r"outline:\s*([^;}]+)", qss_norm))
    check(f"focus draws no outline ring (outlines: {outlines})", outlines <= {"none"})
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
    # Recenter and the walk compares against visual order. (ONEUP-0245 has since
    # put Recenter back in the header for now; the window's chain covers it.)

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
    run.handle_line(wB, "@@STEP_BEGIN@@|system|1|3")
    check("the step being started is announced",
          "Updating system packages" in wB._last_announcement
          and "step 1 of 3" in wB._last_announcement)
    run.handle_line(wB, "@@STEP_END@@|system|ok|installed|3")
    check("the step outcome is announced",
          wB._last_announcement == "System packages: 3 installed")
    run.handle_line(wB, "@@DISK@@|warn|/|512 MiB")
    check("a warning banner is announced when it appears",
          wB._last_announcement.startswith("Warning:"))
    wB.proc = QProcess(wB)
    wB._check_mode = False
    run.on_finished(wB, 0, QProcess.ExitStatus.NormalExit)
    check("the final summary is announced", "All done" in wB._last_announcement)
    # ONEUP-0277: a run that installed Flatpak updates and no system ones told the user it
    # was "already up to date" (measured 2026-10-14: 4 Flatpak updates installed).
    for key, end, label, said in (("flatpak", "installed|4", "Flatpak",
                                   "All done. 4 Flatpak app(s) updated."),
                                  ("firmware", "updated", "firmware",
                                   "All done. Firmware updated.")):
        wFp = window.Updater()
        run.handle_line(wFp, "@@STEP_BEGIN@@|system|1|2")
        run.handle_line(wFp, "@@STEP_END@@|system|ok|up-to-date")
        run.handle_line(wFp, f"@@STEP_BEGIN@@|{key}|2|2")
        run.handle_line(wFp, f"@@STEP_END@@|{key}|ok|{end}")
        run.handle_line(wFp, "@@INSTALLED@@|0|no|no")
        wFp.proc = QProcess(wFp)
        wFp._check_mode = False
        run.on_finished(wFp, 0, QProcess.ExitStatus.NormalExit)
        check(f"a {label}-only run is not called already up to date (ONEUP-0277)",
              "already up to date" not in wFp.status.text()
              and wFp.status.text() == said)
    # ONEUP-0288: the headline counted only system packages (run 2026-10-16_082648
    # said 122 for 126 system packages and 3 Flatpak apps). One sentence per source.
    wSp = window.Updater()
    for line in ("@@STEP_BEGIN@@|system|1|3", "@@STEP_END@@|system|ok|installed|126",
                 "@@STEP_BEGIN@@|flatpak|2|3", "@@STEP_END@@|flatpak|ok|installed|3",
                 "@@STEP_BEGIN@@|firmware|3|3", "@@STEP_END@@|firmware|ok|updated",
                 "@@INSTALLED@@|126|yes|yes"):
        run.handle_line(wSp, line)
    wSp.proc = QProcess(wSp)
    wSp._check_mode = False
    run.on_finished(wSp, 0, QProcess.ExitStatus.NormalExit)
    check("the summary counts each source on its own (ONEUP-0288)",
          wSp.status.text() == "All done. 126 system package(s) installed. "
                               "3 Flatpak app(s) updated. Firmware updated.")
    # ONEUP-0296: a run that removed leftover packages and installed nothing said
    # "already up to date" (VM run 2, 2026-10-16). Removals earn their own sentence.
    for lines, said in (
            (("@@STEP_END@@|system|ok|up-to-date", "@@STEP_END@@|orphans|ok|removed|3",
              "@@INSTALLED@@|0|no|no"),
             "All done. 3 leftover package(s) removed."),
            (("@@STEP_END@@|system|ok|installed|2", "@@STEP_END@@|orphans|ok|removed|1",
              "@@INSTALLED@@|2|yes|no"),
             "All done. 2 system package(s) installed. 1 leftover package(s) removed.")):
        wOr = window.Updater()
        for line in lines:
            run.handle_line(wOr, line)
        wOr.proc = QProcess(wOr)
        wOr._check_mode = False
        run.on_finished(wOr, 0, QProcess.ExitStatus.NormalExit)
        check(f"removed leftovers earn their own sentence (ONEUP-0296: "
              f"{wOr.status.text()!r})", wOr.status.text() == said)
    try:
        wB._announce("plain call must not throw when no reader is listening")
        check("_announce is safe with no screen reader attached", True)
    except Exception as exc:  # noqa: BLE001
        check(f"_announce is safe with no screen reader attached ({exc})", False)

    # A row's outcome must be reachable by keyboard, and must NOT survive into the
    # next run (clear_badge routes through _render_badge for exactly this reason).
    # The size probe's wait is announced, since the button label is invisible to a
    # screen reader (the figure itself can take tens of seconds to arrive).
    wB.size_link.size_btn.click()
    check("the download-size wait is announced, and sets the expectation",
          "up to a minute" in wB._last_announcement)
    check("the size button says the wait is expected",
          "up to a minute" in wB.size_link.size_btn.text())
    # ONEUP-0224: that click launched the real engine. Its sudo must be this suite's mock,
    # refusing as a cancelled prompt does — never the system one, which opens a real
    # password dialog on the desktop.
    wB._size_proc.waitForFinished(30000)
    sudo_calls = Path(_SUDO_LOG).read_text() if os.path.exists(_SUDO_LOG) else ""
    check("the size probe's sudo is the suite's mock, not the system's",
          "-A" in sudo_calls.split())

    check("the outcome is folded into the switch's description for a screen reader",
          "3 installed" in wB.rows["system"].switch.accessibleDescription())
    wB.rows["system"].clear_badge()
    check("a cleared badge does not leave last run's outcome on the switch",
          "3 installed" not in wB.rows["system"].switch.accessibleDescription())

    # --- ONEUP-0183: window defects from review-code 2026-08-31 ----------------
    # Labels the engine feeds show text as typed. Under Qt's default AutoText, a
    # repository name or URL holding a known HTML tag renders as markup instead.
    wT = window.Updater()
    for _name, _lbl in (("status", wT.status), ("progress caption", wT.bar_caption),
                        ("activity", wT.activity), ("theme note", wT.theme_note),
                        ("warning banner", wT.warn_label),
                        ("row badge", wT.rows["system"].badge),
                        ("size result", wT.size_link.size_result)):
        check(f"the {_name} label shows engine text as plain text",
              _lbl.textFormat() == Qt.TextFormat.PlainText)

    # A question that restarts the machine or its services makes No the button Enter
    # picks — the choice the three sibling questions already make deliberately.
    asked_q = []
    _orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(
        lambda *a, **k: asked_q.append((a, k)) or QMessageBox.No)
    try:
        banners.restart_now(wT)
        wT._services = "cups.service"
        banners.restart_services(wT)
    finally:
        QMessageBox.question = _orig_q
    check("both restart questions were asked", len(asked_q) == 2)
    check("Enter on a restart question picks No, never Yes",
          len(asked_q) == 2
          and all(k.get("defaultButton", a[4] if len(a) > 4 else None)
                  == QMessageBox.No for a, k in asked_q))

    # A size line with no line ending is still a line, and the finished process is
    # released. The last chunk used to be dropped, so a real size read as "Nothing to
    # download" — a result the probe did not earn.
    wSF = window.Updater()
    wSF._size_buf = ""
    pSF = QProcess(wSF)
    pSF.setProcessChannelMode(QProcess.MergedChannels)
    pSF.readyReadStandardOutput.connect(lambda: run._on_size_output(wSF))
    pSF.finished.connect(lambda c, st: run._on_size_finished(wSF, c, st))
    wSF._size_proc = pSF
    pSF.start("printf", ["%s", "@@SIZE@@|system|9 MB"])
    pSF.waitForFinished(5000)
    check("a SIZE marker with no line ending still reaches the size slot",
          "9 MB" in wSF.size_link.size_result.text())
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    check("the finished size process is released", not shiboken6.isValid(pSF))

    # An admin action whose program cannot start gives its button back and says why.
    # An empty PATH makes pkexec and the engine's interpreter unfindable, so start()
    # fails as it does on a machine without them. The windows are built first: they
    # start probes too.
    wAu = window.Updater()
    wRb = window.Updater()
    wRb._snapshots, wRb._snapshot = [], "42"
    dRp = repos.RepoManagerDialog(None, parsed)
    dRp._rows[1]["switch"].setChecked(not dRp._rows[1]["switch"].isChecked())
    said = []
    _orig_mb = (QMessageBox.question, QMessageBox.warning, QMessageBox.information)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.warning = staticmethod(
        lambda *a, **k: said.append(" ".join(map(str, a))) or QMessageBox.Yes)
    QMessageBox.information = staticmethod(
        lambda *a, **k: said.append(" ".join(map(str, a))))
    empty_bin = tempfile.mkdtemp()
    saved_path = os.environ["PATH"]
    os.environ["PATH"] = empty_bin
    try:
        dRp._apply()
        dRp._proc.waitForStarted(2000)
        check("Apply comes back when pkexec cannot start", dRp.apply_btn.isEnabled())
        check("the repository dialog says pkexec could not start",
              any("could not be started" in s for s in said))
        said.clear()
        rollback.rollback(wRb)
        wRb._rollback_proc.waitForStarted(2000)
        check("a rollback whose pkexec cannot start says so",
              any("could not be started" in s for s in said))
        said.clear()
        auth._run_auth(wAu, "--grant-auth", "Setting up…")
        wAu._authchg_proc.waitForStarted(2000)
        check("the passwordless switch comes back when its engine cannot start",
              wAu.auth_btn.isEnabled())
        check("the passwordless change says its engine could not start",
              any("could not be started" in s for s in said))
    finally:
        os.environ["PATH"] = saved_path
        QMessageBox.question, QMessageBox.warning, QMessageBox.information = _orig_mb
        shutil.rmtree(empty_bin, ignore_errors=True)

    # A followed run that ends between the window reading its log and asking whether
    # its pid is alive keeps its own verdict. Read-then-probe saw no @@DONE@@ and a
    # dead pid, and recorded a successful run as failed.
    race_dir = tempfile.mkdtemp()
    race_log = os.path.join(race_dir, "run.log")
    Path(race_log).write_text("@@STEP_BEGIN@@|system|1|1\n")
    racer = _sp.Popen(["sleep", "60"])  # noqa: S607 — fixed argv.
    orig_rs = paths.RUN_STATE
    paths.RUN_STATE = Path(race_dir) / "run.state"
    paths.RUN_STATE.write_text(f"{racer.pid}\n{race_log}\nsystem\n0\n")
    real_kill, real_finished = os.kill, run.on_finished

    def _ends_in_the_gap(pid, sig):
        if pid == racer.pid and sig == 0:
            with open(race_log, "a") as fh:
                fh.write("@@DONE@@|ok\n")
            raise ProcessLookupError
        return real_kill(pid, sig)

    try:
        wR = window.Updater()
        verdicts = []
        run.on_finished = lambda _win, code, _status: verdicts.append(code)
        os.kill = _ends_in_the_gap
        try:
            wR._poll_attached_run()
        finally:
            os.kill, run.on_finished = real_kill, real_finished
        check("a run ending between the log read and the pid check keeps its verdict",
              verdicts == [0])
    finally:
        racer.terminate()
        racer.wait()
        paths.RUN_STATE = orig_rs
        shutil.rmtree(race_dir, ignore_errors=True)

    # The windows nothing below reads, released so _reap_windows can delete them before
    # the app-wide theme applies that follow (ONEUP-0267). Each name still bound holds
    # its window through every apply; a closure's names stay, as a slot may yet read one.
    del wQ, wI, wP, wK, wS0, wS1, wO, wW, wH, wE, w_on, w_off, wr, w_tmp, w2, w82

    # INV-8: both settings persist and apply live, with no restart.
    app_inst = QApplication.instance()
    before = app_inst.styleSheet()
    # ONEUP-0294: at the window's narrowest, no header button is narrower than its own
    # label. The VM's 605-pixel window showed "etti", "cent" and ".bou".
    def _clipped_header(w=wA):
        w.show()
        for _ in range(3):
            app_inst.processEvents()
        w.resize(w.minimumWidth(), w.height())
        for _ in range(3):
            app_inst.processEvents()
        return [b.text() for b in (w.settings_btn, w.recenter_btn, w.about_btn)
                if b.width() < b.sizeHint().width()]
    _clipped = _clipped_header()
    check(f"ONEUP-0294 no header button clips its label at the narrowest ({_clipped})",
          not _clipped)
    wA.settings.setValue("text_scale", 1.45)
    theme.apply_app_theme(app_inst)
    check("a text-size change applies live", app_inst.styleSheet() != before)
    # A window built under the sheet and never re-themed, as a real launch is. The
    # checks above ran with no app sheet at all, so they never met the sheet's
    # min-width, which the buttons' reparenting re-applies over a pin taken before
    # it: the VM still showed "etti" after the first fix.
    wFresh = window.Updater()
    _clipped = _clipped_header(wFresh)
    check(f"ONEUP-0294 a freshly built window clips no header label ({_clipped})",
          not _clipped)

    # ONEUP-0324: the three header buttons are one height. A borrowed gear once made
    # Settings stand taller than the other two; a drawn symbol must not do the same.
    def _header_heights(w):
        return {b.text(): b.height() for b in (w.settings_btn, w.recenter_btn, w.about_btn)}

    _heights = _header_heights(wFresh)
    check(f"ONEUP-0324 the header buttons are one height ({_heights})",
          len(set(_heights.values())) == 1)
    wFresh.close()
    del wFresh
    _clipped = _clipped_header()
    check(f"ONEUP-0294 nor at a larger text size ({_clipped})", not _clipped)
    _heights = _header_heights(wA)
    check(f"ONEUP-0324 and at a larger text size ({_heights})",
          len(set(_heights.values())) == 1)
    # ONEUP-0302: Settings shorter than its content still shows every description
    # whole. A 960-pixel screen held the VM's dialog 107 px under its own minimum,
    # and the layout took that out of every row, so a three-line description
    # showed two. The fixed height stands in for the screen's limit; it is short
    # of every tab's page (ONEUP-0303), so no tab passes by fitting.
    wA.open_settings()
    s_dlg = wA._settings_dialog
    s_dlg.setFixedHeight(300)
    _cut, _fits = [], []
    for _i in range(s_dlg.tabs.count()):
        s_dlg.tabs.setCurrentIndex(_i)
        for _ in range(3):
            app_inst.processEvents()
        _page = s_dlg.pages.currentWidget()
        if _page.widget().height() <= _page.viewport().height():
            _fits.append(s_dlg.tabs.tabText(_i))
        _cut += [lbl.text()[:30] for fr in _page.findChildren(QFrame, "RowBorder")
                 for lbl in fr.findChildren(QLabel)
                 if lbl.wordWrap() and lbl.height() < lbl.heightForWidth(lbl.width())]
    check(f"ONEUP-0302 every tab's rows are taller than the shortened dialog "
          f"(fit: {_fits})", not _fits)
    check(f"ONEUP-0302 a Settings dialog shorter than its content cuts no "
          f"description short ({_cut})", not _cut)
    s_dlg.tabs.setCurrentIndex(0)
    s_dlg.setMinimumHeight(0)
    s_dlg.setMaximumHeight(16777215)
    s_dlg.reject()
    wA.settings.setValue("high_contrast", True)
    theme.apply_app_theme(app_inst)
    check("a high-contrast change applies live",
          "qproperty-highContrast: true" in app_inst.styleSheet())
    wA.settings.setValue("text_scale", 1.0)
    wA.settings.setValue("high_contrast", False)
    theme.apply_app_theme(app_inst)
    check("turning high contrast back off really reverts it",
          "qproperty-highContrast: true" not in app_inst.styleSheet())
    # The focus derivation is the expensive part of a theme change — two gradients of
    # up to 100 steps x 101 samples, six pow() calls each — and its input never
    # changes for a given theme. apply_app_theme ran it in build_theme and again for
    # the painters' palette, on every apply (ONEUP-0180). Two more applies of the
    # same theme must run it at most once between them.
    derivations = []
    _real_focus_keys = theme.focus_keys
    theme.focus_keys = lambda p: derivations.append(1) or _real_focus_keys(p)
    try:
        theme.apply_app_theme(app_inst)
        theme.apply_app_theme(app_inst)
    finally:
        theme.focus_keys = _real_focus_keys
    check("re-applying the same theme does not re-run the focus derivation",
          len(derivations) <= 1)
    check("the painters' palette still carries the derived focus keys",
          "focusfill" in theme.current_palette() and "accentfocus" in theme.current_palette())
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
        # The track, sampled where the knob is not: the knob sits at the far end
        # when on — the right in a left-to-right window, the left when mirrored.
        x = img.width() // 6
        if QApplication.isRightToLeft():
            x = img.width() - 1 - x
        return img.pixelColor(x, img.height() // 2)

    _mid = _track_pixel("midnight")
    _for = _track_pixel("forest")
    _exp = theme.BY_ID["forest"].palette["switchon"]
    check("INV-6 the painted switch takes the new theme's track colour",
          _for.name().lower() == _exp.lower())
    check("INV-6 and it is not the colour it started with",
          _mid.name().lower() == theme.BY_ID["midnight"].palette["switchon"].lower())

    # ONEUP-0262: the scrollbar handle is drawn in the theme's own token, in every
    # theme and with the overlay on. Sampled from real pixels: a rule the sheet
    # carries but Qt does not apply to the sub-control would pass a text check.
    # The contrast table measures the token; this proves the handle wears it.
    # The sheet goes on the probe widget, not the app: an app-wide setStyleSheet
    # re-polishes every widget the suite has built so far (18k by here, ~4.5 s a
    # call), and a widget's own sheet outranks the app's whatever the specificity,
    # so the probe is painted by exactly the sheet `apply_app_theme` would install.
    def _handle_pixel(theme_id, hc):
        from PySide6.QtWidgets import QPlainTextEdit
        ed = QPlainTextEdit()
        ed.setStyleSheet(theme.build_theme(theme.BY_ID[theme_id], high_contrast=hc))
        ed.setPlainText("\n".join(f"line {i}" for i in range(200)))
        ed.resize(240, 160)
        # Away from the offscreen pointer at the origin: mirrored, the bar sits on
        # the left edge under it, and the handle would wear its hover colour.
        ed.move(400, 400)
        ed.show()
        QApplication.processEvents()
        sb = ed.verticalScrollBar()
        img = sb.grab().toImage()
        # The handle rests at the top of the trough, centred across its width.
        c = img.pixelColor(img.width() // 2, 12)
        ed.close()
        ed.deleteLater()
        return c.name().lower()

    _bad = []
    for _th in theme.THEMES:
        for _on, _want in ((False, _th.palette["ghostbd"]),
                           (True, (theme._HC_DARK if _th.dark
                                   else theme._HC_LIGHT)["text"])):
            _got = _handle_pixel(_th.id, _on)
            if _got != _want.lower():
                _bad.append(f"{_th.id} overlay {'on' if _on else 'off'}: "
                            f"{_got} != {_want}")
    _qs.setValue("high_contrast", False)
    check(f"ONEUP-0262 the scrollbar handle wears its theme's token "
          f"({len(_bad)} wrong)", not _bad)
    for line in _bad[:6]:
        print(f"       {line}")

    # ONEUP-0123: Retry's rest border sits on the warning banner's amber wash, not
    # on the card, so it is measured against both of the wash's composited stops,
    # in every theme. Real pixels, from a banner built as the window builds it: a
    # qualified rule the sheet carries but Qt does not apply would pass a text
    # check. The banner rule must not swallow hover or disabled either, and with
    # the overlay on the button keeps the overlay's own border.
    # In a fresh process: by this point in the suite QTest.mouseMove reaches the
    # button and Qt still sends it no Enter, so :hover never paints (measured
    # 2026-10-22; no grab, popup, modal or override cursor was set). The same
    # probe hovers on every window of a fresh application.
    _probe = r"""
import sys
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QPushButton
app = QApplication([])
from oneup.gui import theme
for th in theme.THEMES:
    for hc, state in ((False, "rest"), (False, "hover"), (False, "disabled"), (True, "rest")):
        banner = QFrame(objectName="WarnBanner")
        banner.setStyleSheet(theme.build_theme(th, high_contrast=hc))
        btn = QPushButton("Retry failed steps", objectName="GhostBtn")
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setEnabled(state != "disabled")
        QHBoxLayout(banner).addWidget(btn)
        banner.resize(700, 200)
        banner.show()
        QTest.qWaitForWindowExposed(banner)
        # Off the button first: a window opening under a resting cursor gets no Enter.
        QTest.mouseMove(banner, banner.rect().bottomRight())
        app.processEvents()
        if state == "hover":
            QTest.mouseMove(btn, btn.rect().center())
            app.processEvents()
        # The middle of the top edge, clear of the rounded corners.
        c = btn.grab().toImage().pixelColor(btn.width() // 2, 0).name()
        print(th.id, int(hc), state, c, int(btn.underMouse() == (state == "hover")))
        # Leave the cursor off the button, or the next window opens under it hovered.
        QTest.mouseMove(banner, banner.rect().bottomRight())
        banner.close()
        banner.deleteLater()
"""
    _res = subprocess.run(  # noqa: S603 — our own interpreter and probe text.
        [sys.executable, "-c", _probe], cwd=REPO, capture_output=True,
        text=True, timeout=120,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    _seen = {}
    for _line in _res.stdout.splitlines():
        _id, _hc, _state, _c, _ok = _line.split()
        _seen[(_id, _hc == "1", _state)] = _c if _ok == "1" else f"{_c} (state not set)"
    _bad = [] if _res.returncode == 0 else [f"probe exited {_res.returncode}: "
                                            f"{_res.stderr.strip()[-300:]}"]
    for _th in theme.THEMES:
        _got = _seen.get((_th.id, False, "rest"), "missing")
        for _ground in theme.warn_tint(_th.palette):
            if _got == "missing" or theme.contrast(_got, _ground) < theme.FOCUS_MIN:
                _bad.append(f"{_th.id}: {_got} on {_ground}"
                            + ("" if _got == "missing"
                               else f" = {theme.contrast(_got, _ground):.2f}:1"))
        _hc_want = (theme._HC_DARK if _th.dark else theme._HC_LIGHT)["border"]
        for _hc, _state, _want in ((False, "hover", _th.palette["ghosthov"]),
                                   (False, "disabled", _th.palette["disbg"]),
                                   (True, "rest", _hc_want)):
            _got = _seen.get((_th.id, _hc, _state), "missing")
            if _got != _want.lower():
                _bad.append(f"{_th.id} {_state}{' overlay on' if _hc else ''}: "
                            f"{_got} != {_want}")
    check(f"ONEUP-0123 Retry's border clears 3:1 on the warning banner "
          f"({len(_bad)} wrong)", not _bad)
    for line in _bad[:8]:
        print(f"       {line}")

    # ONEUP-0303: a focused Settings tab wears the derived focus fill, in every
    # theme and with the overlay on, and at rest the colour it replaces. Real
    # pixels, sampled through the dialog: a sub-control rule Qt does not apply
    # would pass a text check, and a grab of the bar alone leaves out the `win`
    # behind its transparent tabs. The sheet goes on the dialog, as above.
    _tdlg = settings_dialog.SettingsDialog(wA)
    _tdlg.show()

    def _tab_pixel():
        QApplication.processEvents()
        r = _tdlg.tabs.tabRect(0)
        p = _tdlg.tabs.mapTo(_tdlg, r.topLeft())
        return _tdlg.grab().toImage().pixelColor(p.x() + 8, p.y() + r.height() // 2).name()

    # §3: the current tab is told apart by a shape as well as by colour — its
    # label is underlined. Only strong ink counts, so anti-aliasing cannot join
    # glyphs into a line: a glyph row breaks at the gaps between letters, and an
    # underline is one solid run as wide as most of the label (measured: 124 px
    # on the current tab, 6 on the others).
    def _underline(i):
        img = _tdlg.grab().toImage()
        r = _tdlg.tabs.tabRect(i)
        p = _tdlg.tabs.mapTo(_tdlg, r.topLeft())
        x0, x1 = p.x() + 10, p.x() + r.width() - 10
        # Inside the drawn tab, clear of its border: the rect also holds the
        # 6 px bottom margin, under the border line.
        ys = range(p.y() + 4, p.y() + r.height() - 6 - 4)
        bg = img.pixelColor(x0, p.y() + r.height() // 2).lightness()
        dist = {(x, y): abs(img.pixelColor(x, y).lightness() - bg)
                for x in range(x0, x1) for y in ys}
        cut = 0.6 * max(dist.values())
        best = 0
        for y in ys:
            run = 0
            for x in range(x0, x1):
                run = run + 1 if dist[x, y] > cut else 0
                best = max(best, run)
        return best > (x1 - x0) * 0.4

    _bad = []
    for _th in theme.THEMES:
        _hcp = theme._HC_DARK if _th.dark else theme._HC_LIGHT
        _derived = theme.derived_keys(dict(_th.palette))
        # Tab 0 is the current tab: transparent on `win` at rest, `btn` with the
        # overlay on, which takes the pair derived against `btn`.
        for _on, _rest, _focus in ((False, _th.palette["win"], _derived["winfocusfill"]),
                                   (True, _hcp["btn"],
                                    theme.hc_focus_keys(_hcp)["hcfocusfill"])):
            _tdlg.setStyleSheet(theme.build_theme(_th, high_contrast=_on))
            _tdlg.close_btn.setFocus()
            _got_rest = _tab_pixel()
            _lines = [_underline(i) for i in range(_tdlg.tabs.count())]
            if not (_lines[0] and not any(_lines[1:])):
                _bad.append(f"{_th.id} overlay {'on' if _on else 'off'}: underlined "
                            f"{_lines}, want only the current tab")
            _tdlg.tabs.setFocus()
            _got_focus = _tab_pixel()
            if (_got_rest, _got_focus) != (_rest.lower(), _focus.lower()):
                _bad.append(f"{_th.id} overlay {'on' if _on else 'off'}: rest "
                            f"{_got_rest} want {_rest}, focused {_got_focus} want {_focus}")
    check(f"ONEUP-0303 a focused Settings tab wears the derived fill, and only "
          f"the current tab is underlined ({len(_bad)} wrong)", not _bad)
    for line in _bad[:6]:
        print(f"       {line}")

    # ONEUP-0305: with the overlay on, a switched-on ghost toggle rests on `btn`,
    # as the current tab does, so focused it takes the pair derived against
    # `btn`; the ghost pair's `btnhov` measured 1.43:1 dark and 1.87:1 light
    # there. Switched off it rests on `card` and keeps the ghost pair. Signals
    # are blocked so the probe writes no autostart file.
    _tog = wA.auto_btn
    _was = _tog.isChecked()

    def _tog_pixel():
        QApplication.processEvents()
        p = _tog.mapTo(_tdlg, _tog.rect().topLeft())
        return _tdlg.grab().toImage().pixelColor(p.x() + 6, p.y() + _tog.height() // 2).name()

    _bad = []
    for _th in theme.THEMES:
        _hcp = theme._HC_DARK if _th.dark else theme._HC_LIGHT
        _tdlg.setStyleSheet(theme.build_theme(_th, high_contrast=True))
        for _on, _rest, _focus in ((True, _hcp["btn"],
                                    theme.hc_focus_keys(_hcp)["hcfocusfill"]),
                                   (False, _hcp["card"], _hcp["btnhov"])):
            _tog.blockSignals(True)
            _tog.setChecked(_on)
            _tog.blockSignals(False)
            _tdlg.close_btn.setFocus()
            _got_rest = _tog_pixel()
            _tog.setFocus()
            _got_focus = _tog_pixel()
            if (_got_rest, _got_focus) != (_rest.lower(), _focus.lower()):
                _bad.append(f"{_th.id} toggle {'on' if _on else 'off'}: rest "
                            f"{_got_rest} want {_rest}, focused {_got_focus} want {_focus}")
    _tog.blockSignals(True)
    _tog.setChecked(_was)
    _tog.blockSignals(False)
    _tdlg.reject()
    check(f"ONEUP-0305 with high contrast on, a focused switched-on ghost toggle "
          f"wears the fill derived against its own rest ({len(_bad)} wrong)", not _bad)
    for line in _bad[:6]:
        print(f"       {line}")

    # ONEUP-0198: the progress fill stands out from its own trough at 3:1 in every
    # theme. Real pixels, half-full bar, one sample on the fill and one on the
    # trough: the table measures `progfill` on `progbg`, and this proves the
    # chunk is painted in it rather than in a token the table does not hold.
    def _bar_pixels(theme_id):
        from PySide6.QtWidgets import QProgressBar
        bar = QProgressBar()
        # On the probe, not the app, for the reason `_handle_pixel` gives.
        bar.setStyleSheet(theme.build_theme(theme.BY_ID[theme_id]))
        bar.setRange(0, 100)
        bar.setValue(50)
        bar.setTextVisible(False)
        bar.resize(240, 24)
        bar.move(400, 400)
        bar.show()
        QApplication.processEvents()
        img = bar.grab().toImage()
        # The fill grows from the leading edge: the left, or the right mirrored.
        xf, xt = img.width() // 4, img.width() * 3 // 4
        if QApplication.isRightToLeft():
            xf, xt = xt, xf
        y = img.height() // 2
        fill = img.pixelColor(xf, y).name()
        trough = img.pixelColor(xt, y).name()
        bar.close()
        bar.deleteLater()
        return fill, trough

    _bad = []
    for _th in theme.THEMES:
        _f, _t = _bar_pixels(_th.id)
        _r = theme.contrast(_f, _t)
        if _r + 1e-9 < contrast.MARK or _t.lower() != _th.palette["progbg"].lower():
            _bad.append(f"{_th.id}: fill {_f} on trough {_t} = {_r:.2f}:1")
    check(f"ONEUP-0198 the progress fill clears 3:1 on its trough in every theme "
          f"({len(_bad)} short)", not _bad)
    for line in _bad[:8]:
        print(f"       {line}")

    # ONEUP-0301: a label the sheet names no colour for takes the DESKTOP's text
    # colour, while the sheet paints the dialog in the theme's. A dark theme on a light
    # desktop drew every message box's text black on near-black (1.1:1, measured), and
    # a light theme on a dark desktop the reverse. So under both desktop palettes,
    # every theme's message box and a plain dialog label clear 4.5:1 on `win`.
    def _label_inks(theme_id, desktop):
        from PySide6.QtWidgets import QVBoxLayout
        sheet = theme.build_theme(theme.BY_ID[theme_id])
        box = QMessageBox()
        box.setText("Main text")
        box.setInformativeText("Informative text")
        dlg = QDialog()
        QVBoxLayout(dlg).addWidget(QLabel("A dialog's own intro"))
        inks = []
        # The desktop's palette goes on the app, as the platform puts it there: set on
        # the probe, its own sheet discards it. The sheet stays on the probe, for the
        # reason `_handle_pixel` gives.
        _was = QApplication.palette()
        QApplication.setPalette(desktop)
        for w in (box, dlg):
            w.setStyleSheet(sheet)
            for lab in w.findChildren(QLabel):
                if lab.text():
                    lab.ensurePolished()
                    inks.append((lab.text(), lab.palette().color(lab.foregroundRole()).name()))
            w.deleteLater()
        QApplication.setPalette(_was)
        return inks

    _light = QApplication.style().standardPalette()
    _dark = QPalette(_light)
    for _role, _c in ((QPalette.Window, "#202020"), (QPalette.WindowText, "#eeeeee"),
                      (QPalette.Text, "#eeeeee"), (QPalette.Base, "#151515")):
        _dark.setColor(_role, QColor(_c))
    _bad = []
    for _th in theme.THEMES:
        for _name, _desktop in (("light", _light), ("dark", _dark)):
            for _text, _ink in _label_inks(_th.id, _desktop):
                _r = theme.contrast(_ink, _th.palette["win"])
                if _r + 1e-9 < contrast.TEXT:
                    _bad.append(f"{_th.id} on a {_name} desktop: {_text!r} "
                                f"{_ink} = {_r:.2f}:1")
    check(f"ONEUP-0301 dialog text clears 4.5:1 whatever the desktop's colours "
          f"({len(_bad)} short)", not _bad)
    for line in _bad[:8]:
        print(f"       {line}")

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
    # retry_btn, warn_copy_btn, warn_btn2 and rollback_btn,
    # is constructed hidden — and visual order and geometry are both undefined for
    # a widget that has never been laid out, so a walk that skipped them would
    # pass vacuously rather than prove anything.
    def reveal(w):
        for b in (w.reboot_banner, w.services_banner, w.warn_banner, w.appupdate_banner):
            b.setVisible(True)
        for btn in (w.stop_btn, w.retry_btn, w.warn_copy_btn, w.warn_btn2, w.rollback_btn):
            btn.setVisible(True)
        QApplication.processEvents()

    # A layout tree flattened to visual order: top to bottom, then along the
    # layout direction within a row. A scroll area is a leaf — recursing into one
    # would collect Qt's own viewport and scrollbars, which are not our controls —
    # except the message strip, which takes no focus itself and holds the
    # banners' buttons (ONEUP-0239 §4.4): the walk steps into its widget().
    def visual_order(widget):
        from PySide6.QtWidgets import QAbstractScrollArea, QScrollArea
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
                if (isinstance(w, QScrollArea) and w.widget() is not None
                        and w.focusPolicy() == Qt.FocusPolicy.NoFocus):
                    walk_widget(w.widget())
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
    # and a single-walk test would pass the dialog half vacuously. Run once per
    # layout, each with packages in its views (ONEUP-0239 INV-9), ending on Rows.
    run.handle_line(wR, "@@CHECK_ITEM@@|system|bash|5.2|5.3")
    for _lid in ("rail", "spotlight", "rows"):
        wR.apply_layout(_lid)
        reveal(wR)
        expect = [x for x in wR.focus_chain() if x.isVisible()]
        actual = walk_chain(wR.settings_btn)
        check(f"INV-1 the window's tab order follows its visual order ({_lid})",
              actual == expect)
        if actual != expect:
            print(f"       expected {describe(expect)}")
            print(f"       actual   {describe(actual)}")
        laid_out = visual_order(wR.centralWidget())
        check(f"INV-1 that order is the one the layout tree actually draws ({_lid})",
              laid_out == expect)
        if laid_out != expect:
            print(f"       layout   {describe(laid_out)}")
            print(f"       chain    {describe(expect)}")

    # INV-1, dialog half. Once per tab (ONEUP-0303): the chain holds every
    # page's controls, and Tab passes over the pages not showing.
    wR.open_settings()
    set_dlg = wR._settings_dialog
    set_dlg.show()
    for _i in range(set_dlg.tabs.count()):
        set_dlg.tabs.setCurrentIndex(_i)
        QApplication.processEvents()
        _tab = set_dlg.tabs.tabText(_i)
        dlg_expect = [x for x in set_dlg.focus_chain() if x.isVisible()]
        dlg_actual = walk_chain(dlg_expect[0])
        check(f"INV-1 SettingsDialog's own tab order follows its visual order ({_tab})",
              dlg_actual == dlg_expect)
        if dlg_actual != dlg_expect:
            print(f"       expected {describe(dlg_expect)}")
            print(f"       actual   {describe(dlg_actual)}")
        check(f"INV-1 that dialog's order is the one its layout draws ({_tab})",
              visual_order(set_dlg) == dlg_expect)
    # ONEUP-0303: the three groups of ONEUP-0064 §4.1, a tab each, and every
    # row on the tab of its group.
    _groups = {
        "Automatic behaviour": [wR.auto_btn, wR.autoupdate_btn, wR.tray_btn,
                                wR.startboot_btn, wR.appcheck_btn]
        + ([] if wR._service_route else [wR.auth_btn]),
        "Appearance": [wR.theme_combo, wR.layout_btn, wR.textsize_btn, wR.contrast_btn],
        "This machine": [wR.repos_btn, wR.diag_btn, wR.logkeep_btn],
    }
    check("ONEUP-0303 Settings has a tab per group, in order",
          [set_dlg.tabs.tabText(i) for i in range(set_dlg.tabs.count())] == list(_groups))
    _misplaced = [f"{c.objectName()}:{c.text() if hasattr(c, 'text') else ''}"
                  for i, ctls in enumerate(_groups.values()) for c in ctls
                  if not set_dlg.pages.widget(i).isAncestorOf(c)]
    check(f"ONEUP-0303 every row is on its group's tab (misplaced: {_misplaced})",
          not _misplaced)
    set_dlg.tabs.setCurrentIndex(2)
    QApplication.processEvents()
    check("ONEUP-0303 choosing a tab shows its rows and hides the others'",
          wR.repos_btn.isVisible() and not wR.auto_btn.isVisible())
    set_dlg.tabs.setCurrentIndex(0)
    QApplication.processEvents()
    # ONEUP-0245: Recenter is back in the header for now, so it sits in the
    # window's own chain, between Settings and About.
    win_chain = wR.focus_chain()
    check("ONEUP-0245 Recenter is in the window's chain between Settings and About",
          win_chain[:3] == [wR.settings_btn, wR.recenter_btn, wR.about_btn])

    # INV-6: the moves are where the spec says, and none of them is half-done —
    # the one class of defect here that changes nothing measurable and everything
    # visible. header_row is asserted BY LAYOUT INDEX: "children of the header"
    # names nothing testable, since `header` is the object-named QLabel and the
    # buttons' Qt parent is the card.
    check("INV-6 Repositories is a child of SettingsDialog",
          wR.repos_btn.window() is set_dlg)
    check("ONEUP-0245 Recenter is in the main window, not SettingsDialog",
          wR.recenter_btn.window() is wR)
    header_items = [wR.header_row.itemAt(i) for i in range(wR.header_row.count())]
    check("INV-6 the header carries the title block, then Settings, Recenter "
          "(ONEUP-0245) and About",
          len(header_items) == 4
          and header_items[0].layout() is not None
          and header_items[1].widget() is wR.settings_btn
          and header_items[2].widget() is wR.recenter_btn
          and header_items[3].widget() is wR.about_btn)
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

    # ONEUP-0240: the swap moves nothing. Stop takes Check's width, and so does
    # "Stopping…", so neither Stop nor the Run button beside it changes size.
    wS._check_mode = False
    wS.set_controls_enabled(True)
    QApplication.processEvents()
    _idle = (wS.check_btn.width(), wS.run_btn.width())
    wS.set_controls_enabled(False)
    QApplication.processEvents()
    _run = (wS.stop_btn.width(), wS.run_btn.width())
    wS.stop_btn.setText(QCoreApplication.translate("run", "Stopping…"))
    QApplication.processEvents()
    _stopping = (wS.stop_btn.width(), wS.run_btn.width())
    check(f"ONEUP-0240 Stop keeps Check's width and Run keeps its own "
          f"(idle {_idle}, run {_run}, stopping {_stopping})",
          _idle == _run == _stopping)
    # A bigger desktop font widens every label; the two must still match afterwards.
    wS.set_controls_enabled(True)
    _font0 = QApplication.font()
    _font1 = QFont(_font0)
    _font1.setPointSizeF(_font0.pointSizeF() * 2)
    QApplication.setFont(_font1)
    theme.apply_app_theme(QApplication.instance())
    QApplication.processEvents()
    _big = wS.check_btn.width()
    wS.set_controls_enabled(False)
    QApplication.processEvents()
    check(f"ONEUP-0240 with a bigger desktop font too ({_big} vs {wS.stop_btn.width()})",
          _big == wS.stop_btn.width() and _big > _idle[0])
    QApplication.setFont(_font0)
    theme.apply_app_theme(QApplication.instance())
    wS._run_active = False
    wS.set_controls_enabled(True)

    # INV-6, the case today's code gets wrong: a run that FINISHED with a failed
    # step carrying no hint and no armed remedy. Retry was revealed for any
    # failure while the banner was raised only for a hint or a remedy, so
    # reparenting Retry unchanged would have left the user no way to retry at all.
    wF = window.Updater()
    wF.show()          # isVisible() is False for every child of a hidden window
    wF._run_active, wF._check_mode = True, False
    _patch(run, "_notify_when_away", lambda *a, **k: None)
    for line in ("@@STEP_BEGIN@@|orphans|1|1",
                 "@@STEP_END@@|orphans|fail|failed"):
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
    # carry no font-size, so their geometry follows the application font directly
    # and 6 pt puts both paths at their tightest in one run.
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
               ("size", wT.size_link.size_btn),
               ("restart", wT.restart_btn), ("services", wT.services_btn),
               ("warn", wT.warn_btn), ("warn 2", wT.warn_btn2),
               ("app update", wT.appupdate_btn)]
    # Rows' filter buttons (ONEUP-0239 §7); layout_btn is in the dialog's chain below.
    targets += [(f"filter {i}", b) for i, b in enumerate(wT.host.filter_buttons)]
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
    # Once per form: a row holds the same children in every layout, arranged
    # differently, and the body's edge moves with the arrangement (ONEUP-0239 §7).
    wC = window.Updater()
    wC.show()
    row = wC.rows["system"]
    row.badge.setText("3 waiting")
    QApplication.processEvents()
    fired = []
    row.switch.toggled.connect(lambda on: fired.append(on))

    def clicks_at(widget, point=None):
        fired.clear()
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         point if point is not None else widget.rect().center())
        QApplication.processEvents()
        return len(fired)

    for _lid in ("rows", "rail", "spotlight"):
        wC.apply_layout(_lid)
        QApplication.processEvents()
        # Over the title, which starts every form.
        body = row.name.mapTo(row, QPoint(4, row.name.height() // 2))
        check(f"INV-4 clicking a row's body toggles its switch exactly once ({row.form})",
              clicks_at(row, body) == 1)
        check(f"INV-4 clicking the switch itself toggles exactly once, not twice ({row.form})",
              clicks_at(row.switch) == 1)
        check(f"INV-4 clicking the badge does not toggle ({row.form})",
              clicks_at(row, row.badge.mapTo(row, row.badge.rect().center())) == 0)
        wC.set_controls_enabled(False)
        check(f"INV-4 a body click is inert while the switch is disabled ({row.form})",
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
    # Named rather than discovered. The list is empty since ONEUP-0239 removed
    # the two names it held; an exemption must show its base rule sets no colour,
    # so the appended overlay has nothing to leak.
    exceptions: set[str] = set()
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

    # Every reference key colours something: the stylesheet substitutes it, or a
    # module reads it by name. contrast.py does not count — measuring a key is not
    # using it. ONEUP-0326: Stop's stopfg and stophov outlived ONEUP-0317's fill,
    # every palette carrying them and contrast.py measuring two colours nothing drew.
    _sheet_keys = {m.group("named") or m.group("braced")
                   for m in theme._QSS.pattern.finditer(theme._QSS.template)}
    _gui_src = "\n".join(p.read_text(encoding="utf-8")
                         for p in (REPO / "oneup" / "gui").rglob("*.py")
                         if p.name != "contrast.py")
    _named = set(re.findall(r"""["']([a-z0-9_]+)["']""", _gui_src))
    _unused = sorted(theme.REFERENCE_KEYS - _sheet_keys - _named)
    check(f"every palette key colours something (unused {_unused})", not _unused)

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
        "RunBtn": None, "BannerBtn": None, "RestartBtn": None, "StopBtn": None,
        "Log": None, "RepoScroll": None, "RollbackList": None,
        # ONEUP-0239's package views: mechanism B, the log's rest border.
        "PackageTable": None, "PackageBoard": None, "PackageLists": None,
        "GhostBtn": {"PackageFilter", "Card", "RowCard", "DialogButtons", "WarnBanner"},
        "LinkBtn": {"Card", "RowCard", "WarnBanner"},
        # ONEUP-0027's picker and its popup. Both rules are unqualified,
        # because the picker only ever appears in one place.
        "ThemeCombo": None, "ThemeList": None,
        # Settings' tabs (ONEUP-0303), unqualified for the same reason.
        "SettingsTabs": None,
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
    run.handle_line(wU, "@@CHECK_ITEM@@|system|bash|5.2|5.3")   # so the views show
    gaps = []
    for _lid in ("rail", "spotlight", "rows"):
        wU.apply_layout(_lid)
        reveal(wU)
        gaps += uncovered(wU)
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

    # ONEUP-0304: no focusable widget asks its style for a focus rectangle. The
    # sheet's own cue is the fill; a rule that sets no `outline` hands the
    # rectangle back to the desktop style, and Fusion draws it as a translucent
    # box round the label once focus has moved by keyboard. Seen in the Live VM,
    # whose PySide6 runs Fusion. Asserted on the REQUEST, not on pixels: whether a
    # style paints anything for it varies by style (Breeze 6.7 paints nothing),
    # and a request any style may answer with a box is the defect.
    from PySide6.QtWidgets import QProxyStyle, QStyle

    class _FocusRectRecorder(QProxyStyle):
        def __init__(self):
            super().__init__()
            self.asked = []

        def drawPrimitive(self, element, option, painter, widget=None):
            if element == QStyle.PrimitiveElement.PE_FrameFocusRect and widget is not None:
                self.asked.append(f"{type(widget).__name__}#{widget.objectName()}")
            super().drawPrimitive(element, option, painter, widget)

    def focus_rect_requests(root):
        rec = _FocusRectRecorder()
        for wid in root.findChildren(QWidget):
            if wid.focusPolicy() == Qt.FocusPolicy.NoFocus or not wid.isVisible():
                continue
            if isinstance(wid.window(), QMessageBox):
                continue   # Qt's own About chrome, INV-1's one exclusion
            wid.setStyle(rec)
            wid.setFocus(Qt.FocusReason.TabFocusReason)
            QApplication.processEvents()
            wid.grab()
            wid.setStyle(None)
        return rec.asked

    asked = []
    for _lid in ("rail", "spotlight", "rows"):
        wU.apply_layout(_lid)
        reveal(wU)
        asked += focus_rect_requests(wU)
    wU.open_settings()
    su = wU._settings_dialog
    su.show()
    QApplication.processEvents()
    asked += focus_rect_requests(su)
    su.reject()
    ru = repos.RepoManagerDialog(wU, [
        {"alias": "oss", "name": "Main", "enabled": True, "url": "http://a/x"}])
    ru.show()
    QApplication.processEvents()
    asked += focus_rect_requests(ru)
    ru.reject()
    ko = rollback.RollbackDialog(wU, [("41", "2026-07-24 09:00", "pre-update")], "41")
    ko.show()
    QApplication.processEvents()
    asked += focus_rect_requests(ko)
    ko.reject()
    check(f"ONEUP-0304 no focused widget asks its style for a focus rectangle "
          f"({sorted(set(asked))})", not asked)

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
    # came back (docs/design/oneup-2.0.md §7, G3's row). Since stage 9 the Python
    # engine is the window's only engine, so this runs whenever one resolves.
    #
    # --auth-status is the probe because it cannot hurt the machine running it:
    # read-only, and its privileged leg is sudo -k -n, which refuses to prompt
    # (oneup/engine/actions.py's auth_current, whose comment records that -k
    # leaves a warm credential intact).
    paths._reset_engine_cache()
    if not paths.engine_available():
        print("  SKIP - G3 pairing: no engine resolves from this tree")
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

    # --- ONEUP-0239: three fixed layouts -----------------------------------------
    # docs/specs/ONEUP-0239-fixed-layouts.md §5. Every layout is built by
    # apply_layout, the one path the window and the Settings button both take.
    from PySide6.QtCore import QRect, QSettings
    from PySide6.QtWidgets import QAbstractScrollArea
    _qs = QSettings("OneUp", "OneUp")
    _ids = [lid for lid, _n, _c in window.LAYOUTS]
    _patch(run, "_notify_when_away", lambda *a, **k: None)

    def _at_minimum(lid):
        """A window in layout `lid`, shown at that layout's minimum size."""
        wL = window.Updater()
        wL.apply_layout(lid)
        wL.show()
        QApplication.processEvents()
        wL.resize(wL.minimumSize())
        QApplication.processEvents()
        return wL

    # INV-1: nothing moves or resizes as a check or a run proceeds.
    def _tracked(wL):
        out = {f"row {k}": r for k, r in wL.rows.items()}
        out.update({"package area": wL.package_area, "message strip": wL.message_strip})
        if hasattr(wL.host, "panel"):
            out["spotlight panel"] = wL.host.panel
        for name in ("status", "bar", "bar_caption", "activity", "action_bar", "run_btn",
                     "check_btn", "stop_btn", "last_run", "rollback_btn", "log_toggle",
                     "openlog_btn", "size_link"):
            out[name] = getattr(wL, name)
        for k, r in wL.rows.items():
            for part in ("name", "badge", "switch", "progress"):
                out[f"{k} {part}"] = getattr(r, part)
        return out

    def _geometry(wL, wd):
        return QRect(wd.mapTo(wL, QPoint(0, 0)), wd.size())

    for _lid in _ids:
        wM = _at_minimum(_lid)
        tracked, first, moved = _tracked(wM), {}, []

        def stage(label, wM=wM, tracked=tracked, first=first, moved=moved):
            QApplication.processEvents()
            for name, wd in tracked.items():
                if not wd.isVisible():
                    continue          # never laid out, or hidden: not a place (§5 INV-1)
                g = _geometry(wM, wd)
                if name not in first:
                    first[name] = g
                elif g != first[name]:
                    moved.append(f"{name} at {label}: {first[name].getRect()} -> {g.getRect()}")

        stage("idle")
        run._reset_for_run(wM, ["system", "flatpak"], check=True)
        wM.set_controls_enabled(False)
        for i in range(200):
            run.handle_line(
                wM, f"@@CHECK_ITEM@@|system|package-{i}|1.{i}|1.{i + 1}|{i * 997}|repo-{i}")
        run.handle_line(wM, "@@CHECK@@|system|200")
        run.handle_line(wM, "@@CHECK@@|TOTAL|200")
        stage("check")
        run.on_finished(wM, 0, None)
        stage("check finished")
        run._reset_for_run(wM, ["system", "flatpak"], check=False)
        wM._run_active = True
        wM.set_controls_enabled(False)
        stage("run started")
        for line in ("@@STEP_BEGIN@@|system|1|2", "@@PROGRESS@@|system|3|200|download",
                     *(f"@@PKG@@|system|downloading|package-{i}|1.{i + 1}|{i * 997}|1.{i}|repo-{i}"
                       for i in range(40)),
                     "@@PROGRESS@@|system|40|200|install"):
            run.handle_line(wM, line)
        stage("run progress")
        run._set_activity(wM, "Fetching repo-oss — 4m · 12 MiB of 40 MiB · still working")
        stage("activity")
        # No reboot flag: with one, on_finished offers the reboot alone. "dbus" is
        # session-critical, so it raises the reboot banner; "cups" the services one.
        wM._reboot, wM._services = False, "cups dbus"
        wM._hints, wM._hint_commands = ["Something failed."], ["sudo zypper refresh"]
        wM._remedy_skips, wM._remedy_keys = ["repo-oss"], True
        wM._failed_steps = ["system"]
        wM._sys_changed, wM._snapshot = True, "42"
        wM.appupdate_label.setText("OneUp 9.9 is available.")
        wM.appupdate_banner.setVisible(True)
        run.on_finished(wM, 1, None)
        stage("finished with every banner")
        wM._show_log(True)
        stage("log page")
        check(f"ONEUP-0239 INV-1 nothing moves or resizes as a check and a run proceed "
              f"({_lid}: {len(moved)} moved)", not moved)
        for m in moved[:8]:
            print(f"       {m}")
        check(f"ONEUP-0239 INV-1 the stages showed every banner and Stop ({_lid})",
              all(wd.isVisible() for wd in (wM.reboot_banner, wM.services_banner,
                                             wM.warn_banner, wM.appupdate_banner))
              and "stop_btn" in first and "rollback_btn" in first)

    # INV-2: no text outside a scroll area is cut off, at every text size.
    _scale0 = _qs.value("text_scale", 1.0, type=float)
    for _label, _mult in theme.TEXT_SCALES:
        _qs.setValue("text_scale", _mult)
        theme.apply_app_theme(QApplication.instance())
        for _lid in _ids:
            wC2 = _at_minimum(_lid)
            run.handle_line(wC2, "@@CHECK_ITEM@@|system|bash|5.2|5.3|1024|repo-oss")
            run._set_activity(wC2, "Fetching repo-oss — 4m")
            QApplication.processEvents()
            cut = []
            for lbl in wC2.findChildren(QLabel):
                if not lbl.isVisible() or not lbl.text():
                    continue
                node, scrolled = lbl.parentWidget(), False
                while node is not None:
                    if isinstance(node, QAbstractScrollArea):
                        scrolled = True
                        break
                    node = node.parentWidget()
                if scrolled:
                    continue
                if lbl.wordWrap():
                    need = lbl.heightForWidth(lbl.width())
                elif isinstance(lbl, elided_label.ElidedLabel) and lbl.toolTip() == lbl.text():
                    need = lbl.fontMetrics().height()   # elided across, never cut down
                else:
                    need = lbl.sizeHint().height()
                if lbl.height() < need:
                    cut.append(f"{lbl.objectName() or type(lbl).__name__} "
                               f"{lbl.height()} < {need}")
            check(f"ONEUP-0239 INV-2 no text is cut off ({_lid}, {_label}: {cut})", not cut)
    _qs.setValue("text_scale", _scale0)
    theme.apply_app_theme(QApplication.instance())

    # INV-3: every package view shows every package's state as a word.
    def _six_states(wL):
        run._reset_for_run(wL, ["system", "flatpak"], check=False)
        for name in ("pkg-queued", "pkg-downloading", "pkg-downloaded", "pkg-installed",
                     "pkg-removed"):
            run.handle_line(wL, f"@@CHECK_ITEM@@|system|{name}|1|2|10|repo")
        for name, state in (("pkg-downloading", "downloading"), ("pkg-downloaded", "downloaded"),
                            ("pkg-installed", "installed"), ("pkg-removed", "removed")):
            run.handle_line(wL, f"@@PKG@@|system|{state}|{name}|2")
        run.handle_line(wL, "@@CHECK_ITEM@@|flatpak|pkg-unchanged|1|2|10|flathub")
        run.handle_line(wL, "@@STEP_END@@|flatpak|ok|updated|0")    # supplies `unchanged`
        return {"pkg-queued": "queued", "pkg-downloading": "downloading",
                "pkg-downloaded": "downloaded", "pkg-installed": "installed",
                "pkg-removed": "removed", "pkg-unchanged": "unchanged"}

    for _lid in _ids:
        w3 = window.Updater()
        w3.apply_layout(_lid)
        expected = _six_states(w3)
        lines = _package_lines(w3)
        wrong = [name for name, state in expected.items()
                 if not [t for t in lines if name in t]
                 or any(app.translate("steps", steps.STATE_WORDS[state]) not in t
                        for t in lines if name in t)]
        check(f"ONEUP-0239 INV-3 every view shows each package's state as a word "
              f"({_lid}: wrong {wrong})", not wrong)

    # ONEUP-0322 INV-3: six states, six drawn shapes, each leaving ink. Rows and Spotlight
    # give the state's word to the tooltip and the screen reader, and paint the symbol.
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QIcon, QImage, QPainter
    def _shape_pixels(shape, side=32):
        img = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        symbols.draw(p, shape, QRectF(0, 0, side, side), "#000000")
        p.end()
        return bytes(img.constBits())

    _shapes = {state: _shape_pixels(symbols.STATE_SHAPES[state]) for state in steps.STATE_WORDS}
    check(f"ONEUP-0322 INV-3 every state has a shape that leaves ink ({sorted(_shapes)})",
          all(any(px) for px in _shapes.values()))
    check("ONEUP-0322 INV-3 no two states share a shape",
          len(set(_shapes.values())) == len(steps.STATE_WORDS))

    def _symbol_ink(view, rect, ink):
        """How many pixels of `rect` in the view's viewport carry the text's colour."""
        img = view.viewport().grab(rect).toImage()
        want = QColor(ink)
        return sum(
            abs(QColor(img.pixel(x, y)).red() - want.red()) < 24
            and abs(QColor(img.pixel(x, y)).green() - want.green()) < 24
            and abs(QColor(img.pixel(x, y)).blue() - want.blue()) < 24
            for x in range(img.width()) for y in range(img.height()))

    for _lid, _view_of, _column in (("rows", lambda h: (h.table, h.items), 0),
                                    ("spotlight", lambda h: (h.next_list, h.next_items), 0)):
        wS3 = _at_minimum(_lid)
        _states = _six_states(wS3)
        QApplication.processEvents()
        _v3, _i3 = _view_of(wS3.host)
        _bad3 = []
        for _r in range(_i3.rowCount()):
            _pkg = _i3.packages()[_r]
            _ix = _i3.index(_r, _column)
            _word = app.translate("steps", steps.STATE_WORDS[_states[_pkg.name]])
            for _role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
                if _word not in (_i3.data(_ix, _role) or ""):
                    _bad3.append(f"{_pkg.name} {_role}")
        check(f"ONEUP-0322 INV-3 the state's word is the tooltip and the accessible text "
              f"({_lid}: {_bad3})", _i3.rowCount() > 0 and not _bad3)
        _cell = _v3.visualRect(_i3.index(0, _column))
        if _lid == "spotlight":
            _cell = _v3.itemDelegate().line_rects(_v3, _cell)["state"]
        _ink3 = _symbol_ink(_v3, _cell, _v3.palette().color(QPalette.ColorRole.Text))
        check(f"ONEUP-0322 INV-3 {_lid} paints the symbol, in the text's colour ({_ink3} px)",
              _ink3 > 0)
        wS3.hide()     # never close(): mid-run that opens the quit box

    # ONEUP-0320, ONEUP-0327: Recenter's and Settings' symbols are drawn, in the colour
    # the label has at rest, on hover and on focus.
    wSym = _at_minimum("rows")
    _rc, _set_btn = wSym.recenter_btn, wSym.settings_btn
    check(f"ONEUP-0320 Recenter has no text and keeps its name and tooltip "
          f"({_rc.text()!r}, {_rc.accessibleName()!r})",
          _rc.text() == "" and _rc.accessibleName() == app.translate("window", "Recenter")
          and bool(_rc.toolTip()))
    check(f"ONEUP-0327 Settings is the word alone, its gear drawn ({_set_btn.text()!r})",
          _set_btn.text() == app.translate("window", "Settings") and not _set_btn.icon().isNull())
    check("ONEUP-0320 Recenter is narrower than About, the button beside it",
          _rc.width() < wSym.about_btn.width())

    def _icon_ink(btn):
        img = btn.icon().pixmap(btn.iconSize(), QIcon.Mode.Normal).toImage()
        return {QColor(img.pixel(x, y)).name() for x in range(img.width())
                for y in range(img.height()) if QColor.fromRgba(img.pixel(x, y)).alpha() == 255}

    _qsS = _qs
    _themeS, _hcS = _qsS.value("theme", theme.SYSTEM), _qsS.value("high_contrast", False)
    _inkbad = []
    for _th in theme.THEMES:
        for _hc in (False, True):
            _qsS.setValue("theme", _th.id)
            _qsS.setValue("high_contrast", _hc)
            theme.apply_app_theme(QApplication.instance())
            QApplication.processEvents()
            _p = theme.current_palette()
            _ov = (theme._HC_DARK if _th.dark else theme._HC_LIGHT)
            _want = ((_ov["text"], _ov["btntext"], _ov["btntext"]) if _hc
                     else (_p["ghostfg"], _p["ghosthov"], _p["focusink"]))
            for _b in (_rc, _set_btn):
                _got = (_b.get_rest_ink().name(), _b.get_hover_ink().name(),
                        _b.get_focus_ink().name())
                if _got != tuple(QColor(c).name() for c in _want):
                    _inkbad.append(f"{_th.id} hc={_hc}: {_got} != {_want}")
            if _rc.ink().name() not in _icon_ink(_rc):
                _inkbad.append(f"{_th.id} hc={_hc}: the icon is not drawn in {_rc.ink().name()}")
    check(f"ONEUP-0320 the symbol takes the label's colours in every theme ({_inkbad[:3]})",
          not _inkbad)
    _qsS.setValue("theme", _themeS)
    _qsS.setValue("high_contrast", _hcS)
    theme.apply_app_theme(QApplication.instance())
    QApplication.processEvents()
    _rc.setFocus()
    QApplication.processEvents()
    check(f"ONEUP-0320 focus redraws the symbol in the focus ink ({_icon_ink(_rc)})",
          not _rc.hasFocus() or _rc.get_focus_ink().name() in _icon_ink(_rc))
    _rc.clearFocus()
    # Deep in this suite a real mouse move brings no Enter, so the state is set by hand:
    # what is under test is the redraw, and the sheet's :hover has its own checks.
    _rc.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, True)
    QApplication.sendEvent(_rc, QEvent(QEvent.Type.Enter))
    check(f"ONEUP-0320 hover redraws the symbol in the hover ink ({_icon_ink(_rc)})",
          _rc.get_hover_ink().name() in _icon_ink(_rc))
    _rc.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, False)
    QApplication.sendEvent(_rc, QEvent(QEvent.Type.Leave))
    check(f"ONEUP-0320 and leaving puts the rest ink back ({_icon_ink(_rc)})",
          _rc.get_rest_ink().name() in _icon_ink(_rc))
    wSym.hide()

    # INV-4: no layout writes to the package model.
    for _lid in _ids:
        w4 = window.Updater()
        w4.apply_layout(_lid)
        _six_states(w4)
        writes = []
        for name in ("reset", "add_check_item", "apply", "end_step"):
            setattr(w4.packages, name, lambda *a, _n=name, _w=writes: _w.append(_n))
        for callback in list(w4.packages._callbacks):
            callback("system")
            callback(None)
        w4.host.refresh()
        for name in ("reset", "add_check_item", "apply", "end_step"):
            delattr(w4.packages, name)
        check(f"ONEUP-0239 INV-4 a redraw writes nothing to the model ({_lid}: {writes})",
              not writes)

    # INV-5: a change to the model does not scroll a view.
    for _lid in _ids:
        w5 = _at_minimum(_lid)
        run._reset_for_run(w5, ["system"], check=True)
        for i in range(200):
            run.handle_line(w5, f"@@CHECK_ITEM@@|system|package-{i}|1|2|{i + 1}|repo")
        QApplication.processEvents()
        views = [v for v in (getattr(w5.host, n, None)
                             for n in ("table", "board", "next_list")) if v is not None]
        for v in views:
            v.scrollToBottom()
        QApplication.processEvents()
        before = [v.verticalScrollBar().value() for v in views]
        run.handle_line(w5, "@@PKG@@|system|downloading|package-0|2|1|1|repo")
        QApplication.processEvents()
        after = [v.verticalScrollBar().value() for v in views]
        check(f"ONEUP-0239 INV-5 a model change does not scroll a view "
              f"({_lid}: {before} -> {after})",
              views and all(b > 0 for b in before) and before == after)

    # INV-6: switching layout during a run keeps the run's state on screen.
    w6 = window.Updater()
    w6.show()
    run._reset_for_run(w6, ["system", "flatpak"], check=False)
    w6._run_active = True
    w6.set_controls_enabled(False)
    for line in ("@@CHECK_ITEM@@|system|alpha|1|2|10|repo",
                 "@@CHECK_ITEM@@|system|beta|1|2|10|repo",
                 "@@STEP_BEGIN@@|system|1|2", "@@PROGRESS@@|system|1|2|download",
                 "@@PKG@@|system|downloading|alpha|2"):
        run.handle_line(w6, line)
    banners._show_warning(w6, "A warning that must survive a layout change.")
    w6._show_log(True)
    QApplication.processEvents()

    def _run_state(wL):
        return (tuple((r.badge.text(), r.progress.value(), r.progress.maximum())
                      for r in wL.rows.values()),
                wL.status.text(), wL.bar.value(), wL.warn_banner.isVisible(),
                wL.package_area.currentWidget() is wL.log, wL.current_step, wL.latest_package,
                tuple((p.name, wL.packages.shown_state(p)) for p in wL.packages.packages()))

    for _lid in (*_ids[1:], _ids[0]):
        held = _run_state(w6)
        w6.apply_layout(_lid)
        QApplication.processEvents()
        check(f"ONEUP-0239 INV-6 a switch to {_lid} mid-run keeps the run's state",
              _run_state(w6) == held)
        try:
            run.handle_line(w6, "@@PKG@@|system|downloaded|alpha|2")
            raised = ""
        except Exception as exc:  # noqa: BLE001 — the point is that nothing raises
            raised = repr(exc)
        check(f"ONEUP-0239 INV-6 and a PKG line after it raises nothing ({_lid}: {raised})",
              not raised)
        check(f"ONEUP-0239 INV-6 and reaches the new layout's views ({_lid})",
              any("alpha" in t and app.translate("steps", "downloaded") in t
                  for t in _package_lines(w6)))
        check(f"ONEUP-0239 INV-6 only the current layout listens to the model ({_lid})",
              # The details store listens for the window's whole life (ONEUP-0260).
              len([c for c in w6.packages._callbacks if c != w6.details._on_model]) == 1)
        run.handle_line(w6, "@@PKG@@|system|downloading|beta|2")   # a fresh state to carry

    # INV-7: each layout lays out every shared control exactly once.
    def _layout_tree(lay, out):
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item.widget() is not None:
                out.append(item.widget())
                if item.widget().layout() is not None:
                    _layout_tree(item.widget().layout(), out)
            elif item.layout() is not None:
                out.append(item.layout())
                _layout_tree(item.layout(), out)
        return out

    for _lid in _ids:
        w7 = window.Updater()
        w7.apply_layout(_lid)
        reached = _layout_tree(w7.host.layout(), [])
        shared = [*w7.rows.values(), w7.action_bar, w7.status, w7.bar,
                  w7.message_strip, w7.package_area, w7.log, w7.last_run,
                  w7.rollback_btn, w7.log_toggle, w7.openlog_btn, w7.size_link]
        counts = {wd.objectName() or type(wd).__name__: sum(x is wd for x in reached)
                  for wd in shared}
        check(f"ONEUP-0239 INV-7 every shared control is laid out exactly once "
              f"({_lid}: {counts})", all(n == 1 for n in counts.values()))
        stack = _layout_tree(w7.message_strip.widget().layout(), [])
        check(f"ONEUP-0239 INV-7 the four banners are laid out in the message strip ({_lid})",
              all(sum(x is b for x in stack) == 1
                  for b in (w7.reboot_banner, w7.services_banner, w7.warn_banner,
                            w7.appupdate_banner)))
        check(f"ONEUP-0239 INV-7 the header is in no layout ({_lid})",
              not any(x is w7.header_row or x is w7.settings_btn for x in reached))

    # INV-8: the setting stores an id, cycles in order, and survives an unknown value.
    _layout0 = _qs.value("layout")
    _qs.remove("layout")
    w8 = window.Updater()
    check("ONEUP-0239 INV-8 with no stored value the window builds Rows",
          w8.host.LAYOUT_ID == "rows")
    seen = []
    for _ in range(3):
        w8.layout_btn.click()
        seen.append((_qs.value("layout"), w8.host.LAYOUT_ID))
    check(f"ONEUP-0239 INV-8 three clicks store and apply rail, spotlight, rows ({seen})",
          seen == [("rail", "rail"), ("spotlight", "spotlight"), ("rows", "rows")])
    _qs.setValue("layout", "nonsense")
    w8b = window.Updater()
    check("ONEUP-0239 INV-8 an unknown stored id builds Rows and is left as stored",
          w8b.host.LAYOUT_ID == "rows" and _qs.value("layout") == "nonsense"
          and "Rows" in w8b.layout_btn.text())
    if _layout0 is None:
        _qs.remove("layout")
    else:
        _qs.setValue("layout", _layout0)

    # INV-9's walks are the ONEUP-0064 INV-1 walks above, run once per layout and in
    # SettingsDialog. This pins the one place the dialog's chain gained a control.
    w9 = window.Updater()
    _chain = settings_dialog.SettingsDialog(w9).focus_chain()
    check("ONEUP-0239 INV-9 the Layout button follows the theme picker in Settings",
          _chain[_chain.index(w9.theme_combo) + 1] is w9.layout_btn)

    # INV-21 (ONEUP-0335): "now" is only what is downloading; a downloaded package waiting
    # to install is still to go (the user's decision, 2026-10-23).
    w21 = window.Updater()
    run._reset_for_run(w21, ["system"], check=False)
    for _name in ("q", "dl-ing", "dl-ed", "inst"):
        run.handle_line(w21, f"@@CHECK_ITEM@@|system|{_name}|1|2|10|repo")
    for _name, _state in (("dl-ing", "downloading"), ("dl-ed", "downloaded"),
                          ("inst", "installed")):
        run.handle_line(w21, f"@@PKG@@|system|{_state}|{_name}|2")
    _c21 = package_views.counts(w21.packages, w21.packages.packages("system"))
    check(f"ONEUP-0239 INV-21 downloaded is to go, downloading is now ({_c21})",
          _c21 == {"togo": 2, "now": 1, "done": 1})

    # INV-10: each state group has its own fill, and blocks run in the reading direction.
    fills = package_views.SizeStrip.FILLS
    check("ONEUP-0239 INV-10 the three state groups have three different fills",
          len({fills["done"], fills["now"], fills["togo"]}) == 3)
    strip = package_views.SizeStrip()
    strip.resize(200, 12)
    strip.set_blocks([("done", 100)] + [("togo", 10)] * 10)
    image = strip.grab().toImage()
    # The done fill is solid, in its own colour since ONEUP-0315 (§4.3.2).
    ink = strip.get_done_fill().rgb()
    near_start = image.pixelColor(*((194, 6) if app.isRightToLeft() else (5, 6))).rgb()
    near_end = image.pixelColor(*((5, 6) if app.isRightToLeft() else (194, 6))).rgb()
    check(f"ONEUP-0239 INV-10 the first package's block starts the reading direction "
          f"({'right' if app.isRightToLeft() else 'left'} edge done, the other to go)",
          near_start == ink and near_end != ink)

    # INV-11: a row's progress bar follows its own step only.
    w11 = window.Updater()
    sysbar, fpbar = w11.rows["system"].progress, w11.rows["flatpak"].progress
    run.handle_line(w11, "@@STEP_BEGIN@@|system|1|2")
    check("ONEUP-0239 INV-11 STEP_BEGIN makes its own row's bar busy and no other",
          sysbar.maximum() == 0 and fpbar.maximum() == 1 and fpbar.value() == 0)
    run.handle_line(w11, "@@PROGRESS@@|system|3|10|download")
    check(f"ONEUP-0239 INV-11 PROGRESS sets its download half to 150 of 1000 "
          f"({sysbar.value()} of {sysbar.maximum()})",
          (sysbar.value(), sysbar.maximum()) == (150, 1000))
    run.handle_line(w11, "@@STEP_END@@|system|ok|installed|3")
    check("ONEUP-0239 INV-11 STEP_END fills it",
          sysbar.maximum() > 0 and sysbar.value() == sysbar.maximum())
    run.handle_line(w11, "@@STEP_BEGIN@@|flatpak|2|2")
    run.handle_line(w11, "@@PROGRESS@@|flatpak|1|0|download")
    check("ONEUP-0239 INV-11 a total of 0 leaves the bar busy rather than at 1 of 0",
          fpbar.maximum() == 0 and sysbar.value() == sysbar.maximum())

    # INV-12: a step's progress fills in two halves, never moves backwards, and the
    # window's bar shows the running step's value. The package cache weighs nothing,
    # so this machine's own cache cannot change the byte figure. Restored by hand:
    # _unpatch_all would also lift this section's stub of _notify_when_away.
    _cache_bytes0, run.cache_bytes = run.cache_bytes, lambda: 0
    w12 = window.Updater()
    run._reset_for_run(w12, ["system", "flatpak"], check=False)
    sys12, fp12 = w12.rows["system"], w12.rows["flatpak"]

    def _bars12(row):
        return ((row.progress.value(), row.progress.maximum()),
                (w12.bar.value(), w12.bar.maximum()))

    run.handle_line(w12, "@@STEP_BEGIN@@|system|1|5")
    run.handle_line(w12, "@@PROGRESS@@|system|1|4|download|600|1000")
    check(f"ONEUP-0239 INV-12 the download half follows the bytes, not the count "
          f"({_bars12(sys12)})", _bars12(sys12) == ((300, 1000), (300, 1000)))
    check(f"ONEUP-0239 INV-12 the badge says Downloading ({sys12.badge.text()!r})",
          sys12.badge.text().startswith(app.translate("run", "Downloading")))
    run.handle_line(w12, "@@PROGRESS@@|system|2|4|install")
    check(f"ONEUP-0239 INV-12 the install half starts at 500 ({_bars12(sys12)})",
          _bars12(sys12) == ((750, 1000), (750, 1000)))
    check(f"ONEUP-0239 INV-12 the badge says Installing ({sys12.badge.text()!r})",
          sys12.badge.text().startswith(app.translate("run", "Installing")))
    run.handle_line(w12, "@@PROGRESS@@|system|3|4|download|700|1000")
    check(f"ONEUP-0239 INV-12 a lower figure never lowers the bar ({_bars12(sys12)})",
          _bars12(sys12) == ((750, 1000), (750, 1000)))
    # ONEUP-0322: the words follow the half the value is in, not the line that arrived.
    _late12 = (sys12.badge.text(), w12.status.text())
    check(f"ONEUP-0322 INV-12 a late download line leaves the words on Installing ({_late12})",
          all(app.translate("run", "Installing") in t
              and app.translate("run", "Downloading") not in t for t in _late12))
    run.handle_line(w12, "@@STEP_END@@|system|ok")
    check(f"ONEUP-0239 INV-12 STEP_END fills both ({_bars12(sys12)})",
          _bars12(sys12) == ((1000, 1000), (1000, 1000)))
    run.handle_line(w12, "@@STEP_BEGIN@@|flatpak|2|5")
    check(f"ONEUP-0239 INV-12 the next step makes its bar and the window's busy "
          f"({_bars12(fp12)}, system {sys12.progress.value()})",
          fp12.progress.maximum() == 0 and w12.bar.maximum() == 0
          and sys12.progress.value() == 1000)
    run.cache_bytes = _cache_bytes0

    # ONEUP-0314 (§3 item 13, §4.1.1): each step's description is the short one, and
    # during a run a selected step not yet started says Waiting. An unselected step
    # says nothing, a check keeps today's badges, and Waiting never outlives the run.
    _short = {"system": "Packages from your repositories",
              "flatpak": "Flatpak apps and runtimes",
              "firmware": "Device firmware (fwupd)",
              "orphans": "Dependencies nothing needs",
              "cache": "Free up disk space"}
    w14 = window.Updater()
    _descs14 = {k: r.desc.text() for k, r in w14.rows.items()}
    check(f"ONEUP-0314 every step's description is the short one ({_descs14})",
          _descs14 == {k: app.translate("steps", t) for k, t in _short.items()})
    _waiting = app.translate("run", "Waiting")
    run._reset_for_run(w14, ["system", "flatpak", "cache"], check=False)
    _badges14 = {k: r.badge.text() for k, r in w14.rows.items()}
    check(f"ONEUP-0314 a run's selected steps say Waiting, the others nothing ({_badges14})",
          _badges14 == {"system": _waiting, "flatpak": _waiting, "firmware": "",
                        "orphans": "", "cache": _waiting})
    check("ONEUP-0314 and the switch's accessible description says so",
          w14.rows["flatpak"].switch.accessibleDescription().endswith(_waiting))
    run.handle_line(w14, "@@STEP_BEGIN@@|system|1|3")
    check(f"ONEUP-0314 a started step stops saying Waiting "
          f"({w14.rows['system'].badge.text()!r})",
          w14.rows["system"].badge.text() not in ("", _waiting)
          and w14.rows["flatpak"].badge.text() == _waiting)
    run.handle_line(w14, "@@STEP_END@@|system|ok|uptodate")
    run.on_finished(w14, 1, None)       # stopped before flatpak and cache began
    _after14 = {k: w14.rows[k].badge.text() for k in ("system", "flatpak", "cache")}
    check(f"ONEUP-0314 Waiting is gone once the run ends ({_after14})",
          _after14["system"] not in ("", _waiting)
          and _after14["flatpak"] == "" and _after14["cache"] == "")
    run._reset_for_run(w14, ["system", "flatpak"], check=True)
    check(f"ONEUP-0314 a check never says Waiting "
          f"({[r.badge.text() for r in w14.rows.values()]})",
          all(r.badge.text() == "" for r in w14.rows.values()))

    def _start_run(wL):
        """A real run, up to the first step's STEP_BEGIN, as the window starts one."""
        run._reset_for_run(wL, ["system", "flatpak"], check=False)
        wL._run_active = True
        wL.set_controls_enabled(False)
        run.handle_line(wL, "@@STEP_BEGIN@@|system|1|2")
        QApplication.processEvents()

    def _outside(wL):
        """Every visible widget that is not wholly inside the window. A widget inside
        a scroll area is that area's to clip, so only the area itself counts."""
        frame, out = wL.rect(), []
        for wd in wL.findChildren(QWidget):
            if not wd.isVisible() or wd.isWindow():
                continue
            node, scrolled = wd.parentWidget(), False
            while node is not None and node is not wL:
                if isinstance(node, QAbstractScrollArea):
                    scrolled = True
                    break
                node = node.parentWidget()
            if not scrolled and not frame.contains(_geometry(wL, wd)):
                out.append(f"{wd.objectName() or type(wd).__name__} "
                           f"{_geometry(wL, wd).getRect()}")
        return out

    # INV-13: no visible control extends past the window during a run, in any layout
    # at any text size. Twice each: the layout chosen before the run, and switched to
    # after Stop is shown — the order that put Stop past the edge in the test VM
    # (ONEUP-0307).
    _scale0 = _qs.value("text_scale", 1.0, type=float)
    for _label, _mult in theme.TEXT_SCALES:
        _qs.setValue("text_scale", _mult)
        theme.apply_app_theme(QApplication.instance())
        for _lid in _ids:
            w13 = _at_minimum(_lid)
            _start_run(w13)
            before = _outside(w13)
            w13b = _at_minimum(_ids[(_ids.index(_lid) + 1) % len(_ids)])
            _start_run(w13b)
            w13b.apply_layout(_lid)
            QApplication.processEvents()
            switched = _outside(w13b)
            check(f"ONEUP-0239 INV-13 nothing extends past the window during a run "
                  f"({_lid}, {_label}: {before})", not before)
            check(f"ONEUP-0239 INV-13 nor after a switch to it mid-run "
                  f"({_lid}, {_label}: {switched})", not switched)
            for wL in (w13, w13b):
                wL._run_active = False
    _qs.setValue("text_scale", _scale0)
    theme.apply_app_theme(QApplication.instance())

    # INV-17, its titles half: at the minimum size no step title is cut short, in any
    # layout or text size. The package views' floor is ONEUP-0310's.
    def _whole_title(lbl):
        if lbl.wordWrap():
            return lbl.heightForWidth(lbl.width()) <= lbl.height()
        # What the paint does, not a sum beside it: a width equal to the rounded advance
        # still elided "Firmware" to "Firmwa…" in a real window (ONEUP-0322).
        return lbl.fontMetrics().elidedText(lbl.text(), Qt.TextElideMode.ElideRight,
                                            lbl.contentsRect().width()) == lbl.text()

    _scale0 = _qs.value("text_scale", 1.0, type=float)
    for _label, _mult in theme.TEXT_SCALES:
        _qs.setValue("text_scale", _mult)
        theme.apply_app_theme(QApplication.instance())
        for _lid in _ids:
            w17 = _at_minimum(_lid)
            cut = [f"{r.name.text()} {r.name.width()}" for r in w17.rows.values()
                   if not _whole_title(r.name)]
            check(f"ONEUP-0239 INV-17 no step title is cut short ({_lid}, {_label}: {cut})",
                  not cut)
    _qs.setValue("text_scale", _scale0)
    theme.apply_app_theme(QApplication.instance())

    # INV-17, its viewport half (ONEUP-0310): at the minimum size, with 200 packages,
    # each view's viewport holds its floor of its own rows — three table rows in Rows
    # and fewer than four, three card rows in Rail, six lines in each Spotlight list.
    def _floors(wL):
        """(name, viewport height, row height, floor, ceiling or None) per view."""
        h = wL.host
        if hasattr(h, "table"):
            row = h.table.verticalHeader().defaultSectionSize()
            return [("table", h.table, row, 3, 4)]
        if hasattr(h, "board"):
            return [("board", h.board, h.board.gridSize().height(), 3, None)]
        row = h.next_list.sizeHintForRow(0)
        return [("next", h.next_list, row, 6, None), ("done", h.done_list, row, 6, None)]

    _scale0 = _qs.value("text_scale", 1.0, type=float)
    for _label, _mult in theme.TEXT_SCALES:
        _qs.setValue("text_scale", _mult)
        theme.apply_app_theme(QApplication.instance())
        for _lid in _ids:
            w17 = _at_minimum(_lid)
            run._reset_for_run(w17, ["system"], check=True)
            for i in range(200):
                run.handle_line(w17, f"@@CHECK_ITEM@@|system|package-{i}|1|2|{i + 1}|repo")
            QApplication.processEvents()
            w17.resize(w17.minimumSize())
            QApplication.processEvents()
            for name, view, row, floor, ceiling in _floors(w17):
                tall = view.viewport().height()
                check(f"ONEUP-0239 INV-17 the {name} view holds {floor} of its rows "
                      f"({_lid}, {_label}: viewport {tall}, row {row})",
                      view.isVisible() and row > 0 and tall >= floor * row)
                if ceiling:
                    check(f"ONEUP-0239 INV-17 the {name} view holds under {ceiling} rows "
                          f"({_lid}, {_label}: viewport {tall}, row {row})",
                          tall < ceiling * row)
    _qs.setValue("text_scale", _scale0)
    theme.apply_app_theme(QApplication.instance())

    # ONEUP-0323: each package view's rows grow with the text size (§4.2 item 1). The
    # views once set no font size, so every row kept the app's default at all three.
    _scale0 = _qs.value("text_scale", 1.0, type=float)
    _rows_at = {}
    for _label, _mult in theme.TEXT_SCALES:
        _qs.setValue("text_scale", _mult)
        theme.apply_app_theme(QApplication.instance())
        for _lid in _ids:
            w23 = _at_minimum(_lid)
            run._reset_for_run(w23, ["system"], check=True)
            run.handle_line(w23, "@@CHECK_ITEM@@|system|package|1|2|1|repo")
            QApplication.processEvents()
            for name, _view, row, _floor, _ceiling in _floors(w23):
                _rows_at.setdefault((_lid, name), []).append(row)
    for (_lid, name), rows in _rows_at.items():
        check(f"ONEUP-0323 the {name} view's rows grow with the text size ({_lid}: {rows})",
              all(a < b for a, b in itertools.pairwise(rows)))
    _qs.setValue("text_scale", _scale0)
    theme.apply_app_theme(QApplication.instance())

    # INV-18 (ONEUP-0312): no package list scrolls sideways, even for a package whose
    # name is 200 characters long. Spotlight's two lists each hold one.
    for _lid in _ids:
        w18 = _at_minimum(_lid)
        run._reset_for_run(w18, ["system"], check=True)
        run.handle_line(w18, f"@@CHECK_ITEM@@|system|{'n' * 200}|1.0|2.0|1000|repo")
        run.handle_line(w18, f"@@CHECK_ITEM@@|system|{'q' * 200}|1.0|2.0|1000|repo")
        run.handle_line(w18, f"@@PKG@@|system|installed|{'n' * 200}|2.0|1000|1.0|repo")
        QApplication.processEvents()
        for name, view, _row, _floor, _ceiling in _floors(w18):
            bar = view.horizontalScrollBar()
            check(f"ONEUP-0239 INV-18 the {name} view does not scroll sideways "
                  f"({_lid}: maximum {bar.maximum()}, {view.model().rowCount()} rows)",
                  view.isVisible() and view.model().rowCount() > 0 and bar.maximum() == 0)

    # ONEUP-0313, §4.3 Rows item 2: the tabs read All, System and Flatpak, each with
    # its count, and follow the model; the total sits at the strip's trailing end.
    wT3 = _at_minimum("rows")
    run._reset_for_run(wT3, ["system", "flatpak"], check=True)
    for line in ("@@CHECK_ITEM@@|system|a|1|2|1048576|repo",
                 "@@CHECK_ITEM@@|system|b|1|2|1048576|repo",
                 "@@CHECK_ITEM@@|flatpak|c|1|2|0|flathub"):
        run.handle_line(wT3, line)
    QApplication.processEvents()
    _tabs = [b.text() for b in wT3.host.filter_buttons]
    check(f"ONEUP-0313 the tabs read All, System and Flatpak with counts ({_tabs})",
          _tabs == ["All · 3", "System · 2", "Flatpak · 1"])
    _strip = wT3.host.filter_buttons[0].parentWidget()
    check("ONEUP-0313 the total and the size link sit in the tab strip",
          wT3.host.total.parentWidget() is _strip and wT3.size_link.parentWidget() is _strip
          and "some sizes not known" in wT3.host.total.text())
    wT3.host.filter_buttons[1].click()
    QApplication.processEvents()
    _sys_total = package_views.total_phrase(wT3.packages.packages("system"))
    check(f"ONEUP-0313 the total follows the tab ({wT3.host.total.text()})",
          wT3.host.total.text() == _sys_total and "not known" not in _sys_total)
    run.handle_line(wT3, "@@CHECK_ITEM@@|flatpak|d|1|2|0|flathub")
    QApplication.processEvents()
    _tabs = [b.text() for b in wT3.host.filter_buttons]
    check(f"ONEUP-0313 a new package updates the counts ({_tabs})",
          _tabs == ["All · 4", "System · 2", "Flatpak · 2"])
    # §4.2 item 3: a control whose label changes keeps one width, so a growing count
    # moves no tab.
    _before = [b.geometry().getRect() for b in wT3.host.filter_buttons]
    for i in range(2000):
        run.handle_line(wT3, f"@@CHECK_ITEM@@|system|p{i}|1|2|1|repo")
    QApplication.processEvents()
    _after = [b.geometry().getRect() for b in wT3.host.filter_buttons]
    check(f"ONEUP-0313 a growing count moves no tab ({_before} -> {_after})",
          _before == _after and wT3.host.filter_buttons[0].text() == "All · 2004")

    # §4.3 Rows item 2 and §4.8: the checked tab is filled and the others are not,
    # and a focused tab wears the fill derived from what it rests on — the checked
    # tab's own fill, as #RunBtn's is derived from its own. Real pixels, in every
    # theme with the overlay off and on; the sheet goes on the window, as the
    # Settings tabs' check puts it on the dialog. An unchecked tab shows no border
    # at rest: its edge pixel is the card.
    def _tab_pixels(btn):
        QApplication.processEvents()
        p = btn.mapTo(wT3, btn.rect().topLeft())
        img = wT3.grab().toImage()
        y = p.y() + btn.height() // 2
        return img.pixelColor(p.x() + 6, y).name(), img.pixelColor(p.x(), y).name()

    _checked, _plain = wT3.host.filter_buttons[1], wT3.host.filter_buttons[2]
    _bad = []
    for _th in theme.THEMES:
        _p = dict(_th.palette)
        _p.update(theme.derived_keys(_p))
        _hcp = theme._HC_DARK if _th.dark else theme._HC_LIGHT
        _tabfocus, _ = theme.derive_focus(_p["ghosthov"], (_p["ghosthov"],))
        for _on, _want in (
                (False, {"checked": (_p["ghosthov"], _tabfocus),
                         "unchecked": (_p["card"], _p["focusfill"])}),
                (True, {"checked": (_hcp["btn"], theme.hc_focus_keys(_hcp)["hcfocusfill"]),
                        "unchecked": (_hcp["card"], _hcp["btnhov"])})):
            wT3.setStyleSheet(theme.build_theme(_th, high_contrast=_on))
            # The overlay's 2px border resizes the tabs, and mirrored they are
            # anchored on the right, so their left edges move: let the layout
            # settle before sampling, or the first sample reads the old place.
            wT3.layout().activate()
            QApplication.processEvents()
            for _which, _btn in (("checked", _checked), ("unchecked", _plain)):
                _btn.clearFocus()
                _rest, _edge = _tab_pixels(_btn)
                _btn.setFocus()
                _focus, _ = _tab_pixels(_btn)
                _btn.clearFocus()
                _got = (_rest, _focus)
                _exp = tuple(c.lower() for c in _want[_which])
                if _got != _exp:
                    _bad.append(f"{_th.id} overlay {'on' if _on else 'off'} {_which}: "
                                f"rest/focused {_got} want {_exp}")
                if not _on and _which == "unchecked" and _edge != _p["card"].lower():
                    _bad.append(f"{_th.id} unchecked tab edge {_edge}, want the card "
                                f"{_p['card']}")
    wT3.setStyleSheet("")
    check(f"ONEUP-0313 only the checked tab is filled, and each tab's focus fill is "
          f"derived from its own rest ({len(_bad)} wrong)", not _bad)
    for line in _bad[:6]:
        print(f"       {line}")
    # The checked tab's pair is measured with every other focus pair (ONEUP-0076
    # INV-2/3 above), in every theme and both modes.
    _tab_rows = {(t.id, hc) for t in theme.THEMES for hc in (False, True)
                 for r in theme.focus_report(t, hc)
                 if r["control"].startswith("checked package tab")}
    check("ONEUP-0313 the focus report measures the checked tab in every theme, both modes",
          len(_tab_rows) == 2 * len(theme.THEMES))

    # §4.3 "Common to all three" and Rows item 2: a package's cell is one line — its
    # name, then its source in a rounded label, styled in both sheets — and a long
    # source elides to one fixed width. Versions read old → new in a fixed-pitch
    # font, so two versions of one length draw one width. Real pixels, in every
    # theme with the overlay off (the badge's fill) and on (the badge's rim).
    wS3 = _at_minimum("rows")
    # Taller than the minimum, whose table holds three rows: this one compares four.
    wS3.resize(1200, wS3.height() + 300)
    run._reset_for_run(wS3, ["system", "flatpak"], check=True)
    # The name carrying a label is a Flatpak and its twin with no label a system
    # package, so the two differ only by the label: no Flatpak has details (ONEUP-0260).
    for line in ("@@CHECK_ITEM@@|flatpak|kernel-default|iiiiii|iiiiij|1048576|Packman",
                 "@@CHECK_ITEM@@|system|vlc|MMMMMM|MMMMMW|1048576|" + "r" * 30,
                 "@@CHECK_ITEM@@|system|vlc-b|1|2|1048576|" + "r" * 60,
                 "@@CHECK_ITEM@@|system|kernel-default|1|2|1048576|"):
        run.handle_line(wS3, line)
    _tbl = wS3.host.table
    _rtl = QApplication.isRightToLeft()
    _at = {(p.key, p.name): n for n, p in enumerate(wS3.host.items.packages())}
    _short, _twin = _at["flatpak", "kernel-default"], _at["system", "kernel-default"]
    _long, _longer = _at["system", "vlc"], _at["system", "vlc-b"]
    QApplication.processEvents()
    check("ONEUP-0313 all four rows are in view",
          all(_tbl.viewport().rect().contains(_tbl.visualRect(_tbl.model().index(r, 1)))
              for r in range(4)))
    check("ONEUP-0313 neither kernel-default row carries the details mark",
          not any(wS3.details.has_details(p) for p in wS3.host.items.packages()
                  if p.name == "kernel-default"))

    def _cell(row, col):
        """The cell's (x, colour) pixels along its middle line, and its ground."""
        img = _tbl.viewport().grab().toImage()
        r = _tbl.visualRect(_tbl.model().index(row, col))
        ground = img.pixelColor(r.left() + 1, r.top() + 1).name()
        y = r.center().y()
        return [(x, img.pixelColor(x, y).name()) for x in range(r.left(), r.right())], ground

    def _span(xs):
        return (max(xs) - min(xs)) if xs else -1

    _bad = []
    for _th in theme.THEMES:
        _p = dict(_th.palette)
        _p.update(theme.derived_keys(_p))
        _hcp = theme._HC_DARK if _th.dark else theme._HC_LIGHT
        for _on, _mark in ((False, _p["badgebg"]), (True, _hcp["border"])):
            wS3.setStyleSheet(theme.build_theme(_th, high_contrast=_on))
            wS3.layout().activate()
            QApplication.processEvents()
            _tbl.clearFocus()
            QApplication.processEvents()
            _where = f"{_th.id} overlay {'on' if _on else 'off'}"
            _labels = []
            for row in (_short, _long, _longer):
                px, ground = _cell(row, 1)
                ink = [x for x, c in px if c != ground]
                lab = [x for x, c in px if c == _mark.lower()]
                _labels.append(_span(lab))
                if not lab:
                    _bad.append(f"{_where} row {row}: no source label in the package cell")
                    continue
                # The name comes first in reading order, so its ink starts at least
                # the name's width before the label does.
                lead = (max(ink) - max(lab)) if _rtl else (min(lab) - min(ink))
                _name = wS3.host.items.packages()[row].name
                if lead < _tbl.fontMetrics().horizontalAdvance(_name):
                    _bad.append(f"{_where} row {row}: the label does not follow the whole name "
                                f"(lead {lead})")
            # The name beside its label draws exactly as its twin with no label:
            # whole, never elided while the cell has room.
            px0, _g0 = _cell(_short, 1)
            px1, _g1 = _cell(_twin, 1)
            lab0 = [x for x, c in px0 if c == _mark.lower()]
            if lab0:
                edge = max(lab0) if _rtl else min(lab0)
                beside = [c for x, c in px0 if (x > edge if _rtl else x < edge)]
                alone = [c for x, c in px1 if (x > edge if _rtl else x < edge)]
                if beside != alone:
                    _diff = [n for n, (a, b)
                             in enumerate(zip(beside, alone, strict=False)) if a != b]
                    _bad.append(f"{_where}: the name beside its label is not drawn whole "
                                f"(edge {edge}, {len(beside)}/{len(alone)} px, differ at "
                                f"{_diff[:6]})")
            if not (0 < _labels[0] < _labels[1] == _labels[2]):
                _bad.append(f"{_where}: label widths {_labels}, want a short one, then two "
                            f"long ones elided to one width")
            _vers = []
            for row in (_short, _long):
                px, ground = _cell(row, 2)
                _vers.append(_span([x for x, c in px if c != ground]))
            if min(_vers) <= 0 or min(_vers) / max(_vers) < 0.85:
                _bad.append(f"{_where}: versions iiiiii/MMMMMM draw {_vers} px wide, want "
                            f"one width (a fixed-pitch font)")
    wS3.setStyleSheet("")
    _row_h = _tbl.rowHeight(0)
    check(f"ONEUP-0313 a package row is one line tall (row {_row_h}, line "
          f"{_tbl.fontMetrics().lineSpacing()})",
          0 < _row_h < 2 * _tbl.fontMetrics().lineSpacing())
    check(f"ONEUP-0313 the source label sits after the name, styled in both sheets and "
          f"elided to one width; versions are fixed-pitch ({len(_bad)} wrong)", not _bad)
    for line in _bad[:8]:
        print(f"       {line}")

    # ONEUP-0313, §4.3 Rows item 2: the row of win.latest_package is drawn highlighted
    # while its state is `downloading` — every cell of it, and no other row, not even
    # an earlier package still downloading. Once it is downloaded, no row is. Real
    # pixels, in every theme with the overlay off (the checked tab's pair) and on.
    wH = _at_minimum("rows")
    wH.resize(1200, wH.height() + 300)
    run._reset_for_run(wH, ["system"], check=False)
    for line in ("@@CHECK_ITEM@@|system|alpha|1|2|1048576|repo",
                 "@@CHECK_ITEM@@|system|beta|1|2|1048576|repo",
                 "@@CHECK_ITEM@@|system|gamma|1|2|1048576|repo",
                 "@@STEP_BEGIN@@|system|1|1",
                 "@@PKG@@|system|downloading|alpha|2",
                 "@@PKG@@|system|downloading|beta|2"):
        run.handle_line(wH, line)
    _htbl = wH.host.table
    _hrow = {p.name: n for n, p in enumerate(wH.host.items.packages())}

    def _grounds(row):
        """Each cell's ground in `row`, read just inside its top-left corner."""
        img = _htbl.viewport().grab().toImage()
        out = []
        for col in range(_htbl.model().columnCount()):
            r = _htbl.visualRect(_htbl.model().index(row, col))
            x = r.right() - 1 if QApplication.isRightToLeft() else r.left() + 1
            out.append(img.pixelColor(x, r.top() + 1).name())
        return out

    def _inks(row, col):
        img = _htbl.viewport().grab().toImage()
        r = _htbl.visualRect(_htbl.model().index(row, col))
        return {img.pixelColor(x, y).name()
                for x in range(r.left(), r.right()) for y in range(r.top(), r.bottom())}

    def _dist(a, b):
        ca, cb = QColor(a), QColor(b)
        return (abs(ca.red() - cb.red()) + abs(ca.green() - cb.green())
                + abs(ca.blue() - cb.blue()))

    _hbad = []
    for _th in theme.THEMES:
        _p = dict(_th.palette)
        _p.update(theme.derived_keys(_p))
        _hcp = theme._HC_DARK if _th.dark else theme._HC_LIGHT
        for _on, _fill, _ink in ((False, _p["ghosthov"], _p["tabink"]),
                                 (True, _hcp["btn"], _hcp["btntext"])):
            _fill, _ink = _fill.lower(), _ink.lower()
            wH.setStyleSheet(theme.build_theme(_th, high_contrast=_on))
            wH.layout().activate()
            QApplication.processEvents()
            _htbl.clearFocus()
            QApplication.processEvents()
            _where = f"{_th.id} overlay {'on' if _on else 'off'}"
            if _grounds(_hrow["beta"]) != [_fill] * 4:
                _hbad.append(f"{_where}: the downloading latest row's cells are "
                             f"{_grounds(_hrow['beta'])}, want {_fill} in each")
            # Glyph edges are smoothed, and mirroring moves them, so the word's
            # nearest pixel is close to its ink rather than on it: within a quarter
            # of the way to the fill. The table's own ink lands far off.
            _near = min(_dist(c, _ink) for c in _inks(_hrow["beta"], 0))
            if _near > _dist(_fill, _ink) // 4:
                _hbad.append(f"{_where}: the highlighted row's state word is not in {_ink} "
                             f"(nearest pixel {_near} away)")
            for _other in ("alpha", "gamma"):
                if _fill in _grounds(_hrow[_other]):
                    _hbad.append(f"{_where}: {_other}'s row is highlighted too")
    run.handle_line(wH, "@@PKG@@|system|downloaded|beta|2")
    for _th in theme.THEMES:
        _p = dict(_th.palette)
        _p.update(theme.derived_keys(_p))
        wH.setStyleSheet(theme.build_theme(_th, high_contrast=False))
        wH.layout().activate()
        QApplication.processEvents()
        _htbl.clearFocus()
        QApplication.processEvents()
        if any(_p["ghosthov"].lower() in _grounds(_hrow[n]) for n in ("alpha", "beta", "gamma")):
            _hbad.append(f"{_th.id}: a row stays highlighted once the latest is downloaded")
    wH.setStyleSheet("")
    check(f"ONEUP-0313 the downloading latest package's row, and only it, is highlighted "
          f"in both sheets ({len(_hbad)} wrong)", not _hbad)
    for line in _hbad[:8]:
        print(f"       {line}")

    # INV-14: during a run Stop alone holds the action slot, and the slot neither moves
    # nor resizes between idle, the run and its end.
    def _slot(wL):
        return (_geometry(wL, wL.action_bar).getRect(),
                tuple(b.isVisible() for b in (wL.run_btn, wL.check_btn, wL.stop_btn)))

    for _lid in _ids:
        w14 = _at_minimum(_lid)
        idle = _slot(w14)
        _start_run(w14)
        running = _slot(w14)
        run.on_finished(w14, 0, None)
        QApplication.processEvents()
        finished = _slot(w14)
        check(f"ONEUP-0239 INV-14 idle shows Run and Check, and not Stop ({_lid}: {idle[1]})",
              idle[1] == (True, True, False))
        check(f"ONEUP-0239 INV-14 a run shows Stop alone ({_lid}: {running[1]})",
              running[1] == (False, False, True))
        check(f"ONEUP-0239 INV-14 the end of the run is as idle ({_lid}: {finished[1]})",
              finished[1] == idle[1])
        check(f"ONEUP-0239 INV-14 the action slot keeps its place and size "
              f"({_lid}: {idle[0]}, {running[0]}, {finished[0]})",
              idle[0] == running[0] == finished[0])

    # Rail's cards: a card is its grid cell's width whatever its text, so a long
    # line elides inside the card rather than running into the next one (§4.3 Rail).
    wB = _at_minimum("rail")
    for i in range(3):
        run.handle_line(wB, f"@@CHECK_ITEM@@|system|package-{i}-{'x' * 60}|1.0|1.1|99|"
                            f"repository-{'y' * 60}")
    QApplication.processEvents()
    _cell = wB.host.board.gridSize().width()
    _wide = [wB.host.board.visualRect(wB.host.items.index(i, 0)).width() for i in range(3)]
    check(f"ONEUP-0239 a Rail card stays inside its grid cell (cell {_cell}: {_wide})",
          all(0 < wd <= _cell for wd in _wide))

    # ONEUP-0315, §4.3 Rail item 1 and §4.3.2: the board's page as sketched. The
    # step's title in large type; under it the count and size with the size link,
    # the counts at the trailing end; the strip's groups in the theme's green and
    # blue as well as their patterns, and the legend's line; cards in two columns,
    # each a dot, the name with its size trailing, the versions in the fixed-pitch
    # font, and the source label with the state word trailing; and the downloading
    # latest package's card ringed in the accent, at the width every card's rim has.
    wR = _at_minimum("rail")
    rtlR = QApplication.isRightToLeft()
    run._reset_for_run(wR, ["system"], check=False)
    for line in ("@@CHECK_ITEM@@|system|alpha|1.0|2.0|1048576|Packman",
                 "@@CHECK_ITEM@@|system|beta|1.0|2.0|1048576|Packman",
                 "@@CHECK_ITEM@@|system|gamma|1.0|2.0|0|Main",
                 "@@CHECK_ITEM@@|system|delta|1.0|2.0|1048576|Main",
                 "@@STEP_BEGIN@@|system|1|1",
                 "@@PKG@@|system|installed|alpha|2.0",
                 "@@PKG@@|system|downloading|beta|2.0"):
        run.handle_line(wR, line)
    QApplication.processEvents()
    hR = wR.host
    _title = getattr(hR, "title", None)
    check(f"ONEUP-0315 the board's heading is the step's title "
          f"({_title.text() if _title else None!r})",
          _title is not None and _title.objectName() == "BoardTitle"
          and _title.text() == "System packages")
    check("ONEUP-0315 the heading is in large type",
          _title is not None
          and _title.font().pointSizeF() > 1.3 * hR.summary.font().pointSizeF())
    check(f"ONEUP-0315 the summary is the count and what there is to download "
          f"({hR.summary.text()!r})",
          hR.summary.text().startswith(
              f"{i18n.counted('package-count', 4)} · 3.0 MiB to download")
          and "some sizes not known" in hR.summary.text()
          and "System packages" not in hR.summary.text())
    _line = hR.summary.parentWidget()
    check("ONEUP-0315 the counts share the summary's line, at its trailing end",
          hR.counts.parentWidget() is _line and wR.size_link.parentWidget() is _line
          and hR.counts.text() == "1 done · 1 now · 2 to go"
          and (hR.counts.x() > wR.size_link.x()) != rtlR)
    check("ONEUP-0315 the legend says what a block is",
          "Each block is one package, sized by its download"
          in [lb.text() for lb in hR.legend.findChildren(QLabel)])

    # Two columns, at the minimum size and wider.
    def _columns(board):
        return len({board.visualRect(board.model().index(i, 0)).x()
                    for i in range(board.model().rowCount())})

    _cols = [_columns(hR.board)]
    wR.resize(wR.width() + 700, wR.height())
    QApplication.processEvents()
    _cols.append(_columns(hR.board))
    _grid, _port = hR.board.gridSize().width(), hR.board.viewport().width()
    check(f"ONEUP-0315 the cards stand in two columns that fill the board "
          f"(columns {_cols}, cell {_grid} of {_port})",
          _cols == [2, 2] and 2 * _grid <= _port <= 2 * _grid + 2)

    # The card's parts, in reading order and mirrored.
    _cd = hR.board.itemDelegate()
    _shape = []
    if not isinstance(_cd, getattr(package_views, "CardDelegate", ())):
        _shape.append(f"the board's delegate is {type(_cd).__name__}")
    else:
        _r = _cd.card_rects(hR.board, hR.board.visualRect(hR.items.index(1, 0)))

        def _after(a, b):
            """`a` stands after `b` in the reading direction."""
            return a.left() >= b.right() if not rtlR else a.right() <= b.left()

        if not (_after(_r["name"], _r["dot"]) and _after(_r["size"], _r["name"])):
            _shape.append("line 1 is not dot, name, then size")
        if not (_r["name"].bottom() < _r["versions"].top()
                and _r["versions"].bottom() < _r["label"].top()):
            _shape.append("the lines are not name, versions, then source")
        if not (_after(_r["state"], _r["label"])
                and abs(_r["state"].center().y() - _r["label"].center().y()) <= 2):
            _shape.append("the state word does not trail the source label")
        _fonts = _cd.fonts(hR.board)
        if _fonts["versions"].family() != package_views.fixed_font(hR.board.font()).family():
            _shape.append(f"the versions are in {_fonts['versions'].family()}")
        if _fonts["name"].weight() < QFont.Weight.DemiBold:
            _shape.append("the name is not bold")
    check(f"ONEUP-0315 a card is the sketch's shape ({_shape})", not _shape)

    # The theme's colours, read back as painted pixels in every theme, overlay off
    # and on. Glyph and curve edges are smoothed, so a colour counts as present when
    # a pixel lies within a quarter of the way from it to the board's own ground.
    def _dist(a, b):
        ca, cb = QColor(a), QColor(b)
        return (abs(ca.red() - cb.red()) + abs(ca.green() - cb.green())
                + abs(ca.blue() - cb.blue()))

    def _near(img, rect, colour, ground):
        best = min(_dist(img.pixelColor(x, y).name(), colour)
                   for x in range(max(rect.left(), 0), min(rect.right(), img.width() - 1))
                   for y in range(max(rect.top(), 0), min(rect.bottom(), img.height() - 1)))
        return best <= _dist(colour, ground) // 4

    _row = {p.name: n for n, p in enumerate(hR.items.packages())}
    _cbad = []
    for _th in theme.THEMES:
        _p = dict(_th.palette)
        _p.update(theme.derived_keys(_p))
        _hcp = theme._HC_DARK if _th.dark else theme._HC_LIGHT
        for _on, _done, _now, _ground in (
                (False, _p["switchon"], _p["ghosthov"], _p["logbg"]),
                (True, _hcp["text"], _hcp["link"], _hcp["card"])):
            _where = f"{_th.id} overlay {'on' if _on else 'off'}"
            wR.setStyleSheet(theme.build_theme(_th, high_contrast=_on))
            wR.layout().activate()
            QApplication.processEvents()
            hR.board.clearFocus()
            QApplication.processEvents()
            _strip = hR.strip.grab().toImage()
            _whole = QRect(0, 0, _strip.width(), _strip.height())
            for _c, _what in ((_done, "done"), (_now, "now")):
                if not _near(_strip, _whole, _c, _ground):
                    _cbad.append(f"{_where}: no {_what} block in {_c}")
            _img = hR.board.viewport().grab().toImage()
            for _name, _want in (("beta", True), ("alpha", False), ("delta", False)):
                _cell = hR.board.visualRect(hR.items.index(_row[_name], 0))
                _rim = QRect(_cell.center().x() - 10, _cell.top(), 20, 8)
                if _near(_img, _rim, _now, _ground) != _want:
                    _cbad.append(f"{_where}: {_name}'s card is "
                                 f"{'not ' if _want else ''}ringed in {_now}")
    wR.setStyleSheet("")
    check(f"ONEUP-0315 the strip and the downloading card wear the theme's colours "
          f"({len(_cbad)} wrong)", not _cbad)
    for line in _cbad[:8]:
        print(f"       {line}")

    # ONEUP-0316, §4.3 Spotlight and §4.3.1, §4.3.3: Spotlight as sketched. Tiles
    # with short titles; a raised panel with "Now · {step}", the latest package as a
    # sentence in large type, its description, source and versions, the step's
    # percentage large at the trailing end, and three figure boxes; under it, the two
    # lists headed with their counts, the size link at the trailing end of Up next,
    # each line the state, the name and the size at the trailing end. The package
    # cache weighs nothing, so this machine's own cannot change the byte figure.
    _cache_bytes0, run.cache_bytes = run.cache_bytes, lambda: 0
    wS = _at_minimum("spotlight")
    rtlS = QApplication.isRightToLeft()
    _patch(wS.details, "about", lambda name: package_details.About(
        "Video codec library", "", "") if name == "beta" else None)
    run._reset_for_run(wS, ["system"], check=False)
    for line in ("@@CHECK_ITEM@@|system|alpha|1.0|2.0|1048576|Packman",
                 "@@CHECK_ITEM@@|system|beta|1.0|2.0|1048576|Packman",
                 "@@CHECK_ITEM@@|system|gamma|1.0|2.0|0|Main",
                 "@@CHECK_ITEM@@|system|delta|1.0|2.0|1048576|Main",
                 "@@STEP_BEGIN@@|system|1|1",
                 "@@PROGRESS@@|system|1|4|download|1048576|3145728",
                 "@@PKG@@|system|installed|alpha|2.0",
                 "@@PKG@@|system|downloading|beta|2.0"):
        run.handle_line(wS, line)
    QApplication.processEvents()
    hS = wS.host

    def _txt(name):
        w = getattr(hS, name, None)
        return w.text() if w is not None else None

    _shorts = [r.name.text() for r in wS.rows.values()]
    check(f"ONEUP-0316 the tiles carry the short titles ({_shorts})",
          _shorts == ["System", "Flatpak", "Firmware", "Leftovers", "Cache"]
          and wS.rows["orphans"].switch.accessibleName().startswith("Leftover packages"))
    check(f"ONEUP-0316 the panel's heading names the step ({_txt('now_heading')!r})",
          _txt("now_heading") == "Now · System packages")
    check(f"ONEUP-0316 the latest package is a sentence of its phase "
          f"({_txt('headline')!r})", _txt("headline") == "Downloading beta")
    _about = [p.strip() for p in (_txt("about") or "").split("·")]
    check(f"ONEUP-0316 under it, the description, source and versions ({_about})",
          _about == ["Video codec library", "Packman", "1.0 → 2.0"])
    _pct = round(wS.step_progress.get("system", 0) * 100 / 1000)
    _head, _per = getattr(hS, "headline", None), getattr(hS, "percent", None)
    check(f"ONEUP-0316 the step's percentage, large, trails the headline "
          f"({_txt('percent')!r}, want {_pct}%)",
          _head is not None and _per is not None and _per.text() == f"{_pct}%"
          and _head.font().pointSizeF() > 1.3 * hS.about.font().pointSizeF()
          and _per.font().pointSizeF() > _head.font().pointSizeF()
          and (_per.mapTo(wS, _per.rect().center()).x()
               > _head.mapTo(wS, _head.rect().center()).x()) != rtlS)
    _boxes = hS.panel.findChildren(QFrame, "FigureBox")
    _fig = [[lb.text() for lb in b.findChildren(QLabel)] for b in _boxes]
    _one, _three = markers._format_size(1048576), markers._format_size(3145728)
    check(f"ONEUP-0316 three figure boxes: packages, downloaded, time left ({_fig})",
          _fig == [["Packages", "1 of 4"], ["Downloaded", f"{_one} of {_three}"],
                   ["Time left", "not known"]])
    run.handle_line(wS, "@@PROGRESS@@|system|2|4|install")
    QApplication.processEvents()
    _fig2 = [b.findChildren(QLabel)[1].text() for b in _boxes]
    check(f"ONEUP-0316 a progress line redraws the panel ({_txt('headline')!r}, "
          f"{_txt('percent')!r}, {_fig2[:1]})",
          _txt("headline") == "Installing beta" and _txt("percent") == "75%"
          and _fig2[:1] == ["2 of 4"])
    check("ONEUP-0316 the size link has left the panel",
          not hS.panel.isAncestorOf(wS.size_link))
    _nh, _dh = getattr(hS, "next_heading", None), getattr(hS, "done_heading", None)
    check(f"ONEUP-0316 the lists are headed with their counts "
          f"({_nh.text() if _nh else None!r}, {_dh.text() if _dh else None!r})",
          _nh is not None and _dh is not None
          and _nh.text() == "Up next · 3" and _dh.text() == "Done · 1")
    check("ONEUP-0316 the size link trails the Up next heading",
          _nh is not None and wS.size_link.parentWidget() is _nh.parentWidget()
          and (wS.size_link.x() > _nh.x()) != rtlS)

    # A list line: the state, the name, then the size at the trailing end; its
    # tooltip, which a screen reader hears too, is the whole line.
    _ld = hS.next_list.itemDelegate()
    _lbad = []
    if not hasattr(_ld, "line_rects"):
        _lbad.append(f"the list's delegate is {type(_ld).__name__}")
    else:
        _cell = hS.next_list.visualRect(hS.next_items.index(0, 0))
        _r = _ld.line_rects(hS.next_list, _cell)

        def _after(a, b):
            return a.left() >= b.right() if not rtlS else a.right() <= b.left()

        if not (_after(_r["name"], _r["state"]) and _after(_r["size"], _r["name"])):
            _lbad.append("not state, name, then size")
        _gap = (_cell.right() - _r["size"].right() if not rtlS
                else _r["size"].left() - _cell.left())
        if _gap > 12:
            _lbad.append(f"the size stops {_gap} px short of the line's trailing end")
    _tip = hS.next_items.data(hS.next_items.index(0, 0), Qt.ItemDataRole.ToolTipRole)
    if [p.strip() for p in (_tip or "").split("·")] != ["downloading", "beta", _one]:
        _lbad.append(f"the tooltip is {_tip!r}")
    check(f"ONEUP-0316 a list line is the state, the name and the size ({_lbad})",
          not _lbad)

    # The panel's raised surface and its boxes, read back as pixels in every theme,
    # overlay off and on: inside the panel's margin, and inside a box's.
    _pbad = []
    for _th in theme.THEMES:
        _p = dict(_th.palette)
        _p.update(theme.derived_keys(_p))
        _hcp = theme._HC_DARK if _th.dark else theme._HC_LIGHT
        for _on, _raised, _box in ((False, _p["rowcard"], _p["logbg"]),
                                   (True, _hcp["card"], _hcp["card"])):
            _where = f"{_th.id} overlay {'on' if _on else 'off'}"
            wS.setStyleSheet(theme.build_theme(_th, high_contrast=_on))
            wS.layout().activate()
            QApplication.processEvents()
            _pimg = hS.panel.grab().toImage()
            _got = _pimg.pixelColor(8, _pimg.height() // 2).name()
            if _got != _raised:
                _pbad.append(f"{_where}: panel {_got}, want {_raised}")
            if _boxes:
                _bimg = _boxes[0].grab().toImage()
                _bgot = _bimg.pixelColor(5, _bimg.height() // 2).name()
                if _bgot != _box:
                    _pbad.append(f"{_where}: box {_bgot}, want {_box}")
            else:
                _pbad.append(f"{_where}: no figure box")
    wS.setStyleSheet("")
    check(f"ONEUP-0316 the panel is raised and its boxes sunk, in every theme "
          f"({len(_pbad)} wrong)", not _pbad)
    for line in _pbad[:8]:
        print(f"       {line}")
    run.cache_bytes = _cache_bytes0
    _unpatch_all()

    # ONEUP-0317, §4.1.3 and §4.8: one status line, one log link, a filled Stop.
    # The status carries the step, the phase and its count and the byte figure, each
    # only when known; a stall's sentence ends it. During a refresh it keeps the
    # refresh's own text and adds the moving clock, so a mirror trickling dots is not
    # a hang (ONEUP-0322 item 4); a total of 0 is a running tally (item 5). The
    # caption and the activity line are in no host, and never shown. The cache weighs
    # nothing, so this machine's own cannot change the byte figure.
    _cache_bytes0, run.cache_bytes = run.cache_bytes, lambda: 0
    _patch(paths, "STOP_REQUEST", Path(tempfile.mkdtemp()) / "stop.request")
    wF = _at_minimum("rows")
    _start_run(wF)
    wF._liveness_active = True
    run._reset_activity(wF)
    run.handle_line(wF, "@@REFRESH@@|6|9|games")
    _refresh = wF.status.text()
    check(f"ONEUP-0317 a refresh keeps its text and adds the clock ({_refresh!r})",
          _refresh.startswith("Checking for updates from games (6 of 9 sources)…")
          and "Fetching games" in _refresh)
    _got, _total = 6501171, 18350080
    run.handle_line(wF, f"@@PROGRESS@@|system|4|24|download|{_got}|{_total}")
    _line = (f"System packages · Downloading 4 of 24 · {markers._format_size(_got)} of "
             f"{markers._format_size(_total)}")
    check(f"ONEUP-0317 the status is one line: step, phase and count, bytes "
          f"({wF.status.text()!r})", wF.status.text() == _line)
    wF._dl_at -= 10
    run._tick_activity(wF)
    check(f"ONEUP-0317 the rate and 'still working' stay off the line "
          f"({wF.status.text()!r})", wF.status.text() == _line)
    wF._activity_at = time.monotonic() - (run.STALL_SECONDS + 5)
    run._tick_activity(wF)
    _stalled = wF.status.text()
    check(f"ONEUP-0317 a stall's sentence ends the line ({_stalled!r})",
          _stalled.startswith(_line + " · ") and _stalled.endswith("Stopping now is safe."))
    check("ONEUP-0317 the activity line is never shown, though it has text",
          bool(wF.activity.text()) and not wF.activity.isVisible())
    wF._activity_at = time.monotonic()
    run.handle_line(wF, "@@PROGRESS@@|system|7|24|install")
    check(f"ONEUP-0317 the install half says so, with no byte figure "
          f"({wF.status.text()!r})", wF.status.text() == "System packages · Installing 7 of 24")
    run.handle_line(wF, "@@STEP_BEGIN@@|system|1|2")
    run.handle_line(wF, "@@PROGRESS@@|system|34|0|download")
    check(f"ONEUP-0317 a total of 0 is a running tally ({wF.status.text()!r})",
          wF.status.text().startswith("System packages · ") and "34 so far" in wF.status.text()
          and "of 0" not in wF.status.text())
    run.request_stop(wF)
    run._tick_activity(wF)
    check(f"ONEUP-0317 a tick does not overwrite the stop request ({wF.status.text()!r})",
          wF.status.text().startswith("Stopping after the current step"))
    run.on_finished(wF, 0, None)
    run.cache_bytes = _cache_bytes0
    _unpatch_all()

    _hidden_bad, _log_bad = [], []
    for _lid in _ids:
        wF = _at_minimum(_lid)
        for _name in ("bar_caption", "activity"):
            _wd = getattr(wF, _name)
            if wF.host.isAncestorOf(_wd) or _wd.window() is not wF or _wd.isVisible():
                _hidden_bad.append(f"{_lid}: {_name}")
        # One log link: Open log file only while the log is shown, in a slot that
        # keeps its size, so nothing beside it moves.
        _before = (wF.openlog_btn.isVisible(), _geometry(wF, wF.log_toggle))
        wF.toggle_log()
        QApplication.processEvents()
        _after = (wF.openlog_btn.isVisible(), _geometry(wF, wF.log_toggle))
        if _before[0] or not _after[0] or _before[1] != _after[1]:
            _log_bad.append(f"{_lid}: {_before}, {_after}")
    check(f"ONEUP-0317 the caption and the activity line are in no host and hidden "
          f"({_hidden_bad})", not _hidden_bad)
    check(f"ONEUP-0317 Open log file shows only with the log, and moves nothing "
          f"({_log_bad})", not _log_bad)

    # ONEUP-0299: the two log controls are small buttons, not links — the ghost
    # button's look, shorter than Check for updates, on one line with each other.
    _small_bad = []
    for _lid in _ids:
        wF = _at_minimum(_lid)
        wF.toggle_log()
        QApplication.processEvents()
        _tog, _open = wF.log_toggle, wF.openlog_btn
        for _b in (_tog, _open):
            if _b.objectName() != "GhostBtn" or _b.property("small") is not True:
                _small_bad.append(f"{_lid}: {_b.text()!r} is {_b.objectName()}")
            elif _b.height() >= wF.check_btn.height():
                _small_bad.append(f"{_lid}: {_b.text()!r} {_b.height()} high, "
                                  f"Check {wF.check_btn.height()}")
        if _geometry(wF, _tog).center().y() != _geometry(wF, _open).center().y():
            _small_bad.append(f"{_lid}: the two are not on one line")
    check(f"ONEUP-0299 the log controls are small ghost buttons on one line "
          f"({_small_bad})", not _small_bad)
    check("ONEUP-0299 the sheet has a rule for the small ghost button",
          'QPushButton#GhostBtn[small="true"]' in theme.build_theme(True))

    # ONEUP-0318, INV-15: the time left, only in the system step's download half, with a
    # known total and rate, worded as an estimate — on the status line and in Spotlight's
    # Time left box. The clock is run.py's alone, and the cache weighs nothing.
    _clock = [1000.0]
    _patch(run, "time", types.SimpleNamespace(monotonic=lambda: _clock[0]))
    _patch(run, "cache_bytes", lambda: 0)
    _patch(paths, "STOP_REQUEST", Path(tempfile.mkdtemp()) / "stop.request")
    wT = _at_minimum("spotlight")
    _start_run(wT)
    wT._liveness_active = True
    run._reset_activity(wT)
    _left = wT.host.figures[2]
    run.handle_line(wT, "@@STEP_BEGIN@@|system|1|5")
    run.handle_line(wT, "@@PROGRESS@@|system|1|4|download|100|1000")
    check(f"ONEUP-0318 no time left before there is a rate ({wT.status.text()!r}, "
          f"{_left.text()!r})", "left" not in wT.status.text() and _left.text() == "not known")
    _clock[0] += 10
    run.handle_line(wT, "@@PROGRESS@@|system|2|4|download|200|1000")
    _est = "about 1 min left"            # 800 bytes to go at 10 bytes a second
    check(f"ONEUP-0318 the time left ends the status line ({wT.status.text()!r})",
          wT.status.text().endswith(" · " + _est))
    check(f"ONEUP-0318 and fills Spotlight's Time left box ({_left.text()!r})",
          _left.text() == _est)
    _clock[0] += 30                      # the 5s tick alone: 100 bytes in 40 s now
    run._tick_activity(wT)
    check(f"ONEUP-0318 a tick with no new line redraws both from its own rate "
          f"({wT.status.text()!r}, {_left.text()!r})", _left.text() == "about 5 min left"
          and wT.status.text().endswith(" · about 5 min left"))
    _clock[0] += 50
    run.handle_line(wT, "@@PROGRESS@@|system|3|4|download|900|1000")
    check(f"ONEUP-0318 under a minute, it counts in seconds ({_left.text()!r})",
          _left.text() == "about 10 s left")
    wT._activity_at = _clock[0] - (run.STALL_SECONDS + 5)
    run._tick_activity(wT)
    check(f"ONEUP-0318 a stall's sentence takes the time left's place "
          f"({wT.status.text()!r})", "left" not in wT.status.text()
          and wT.status.text().endswith("Stopping now is safe."))
    wT._activity_at = _clock[0]
    run.handle_line(wT, "@@PROGRESS@@|system|3|4|install")
    check(f"ONEUP-0318 the first install figure removes it ({wT.status.text()!r}, "
          f"{_left.text()!r})", "left" not in wT.status.text() and _left.text() == "not known")
    # ONEUP-0322: a download line once the bar is in its install half brings none of the
    # download half's words back: no estimate, no byte figure, no sentence, no announcement.
    run.handle_line(wT, "@@CHECK_ITEM@@|system|pkg-late|1|2|10|repo")
    run.handle_line(wT, "@@PKG@@|system|downloading|pkg-late|2")
    _spoken = []
    wT._announce = _spoken.append
    _clock[0] += 10
    run.handle_line(wT, "@@PROGRESS@@|system|4|4|download|950|1000")
    check(f"ONEUP-0322 INV-15 a late download line brings no time left back "
          f"({wT.status.text()!r}, {_left.text()!r})",
          "left" not in wT.status.text() and _left.text() == "not known")
    check(f"ONEUP-0322 nor a byte figure, nor Downloading on the line ({wT.status.text()!r})",
          " of 1" not in wT.status.text().replace("4 of 4", "")
          and "Downloading" not in wT.status.text())
    check(f"ONEUP-0322 Spotlight's sentence stays on Installing ({wT.host.headline.text()!r})",
          wT.host.headline.text() == "Installing pkg-late")
    check(f"ONEUP-0322 and nothing announces Downloading ({_spoken})",
          not any("Downloading" in said for said in _spoken))
    del wT._announce
    run.handle_line(wT, "@@STEP_BEGIN@@|system|1|5")
    run.handle_line(wT, "@@PROGRESS@@|system|37|0|download")
    check(f"ONEUP-0322 Spotlight's Packages box shows the running tally with no total "
          f"({wT.host.figures[0].text()!r})", wT.host.figures[0].text() == "37 so far")
    run.handle_line(wT, "@@STEP_BEGIN@@|system|1|5")
    run.handle_line(wT, "@@PROGRESS@@|system|1|4|download|100|0")
    _clock[0] += 10
    run.handle_line(wT, "@@PROGRESS@@|system|2|4|download|200|0")
    check(f"ONEUP-0318 no total, no time left ({wT.status.text()!r}, {_left.text()!r})",
          "left" not in wT.status.text() and _left.text() == "not known")
    run.on_finished(wT, 0, None)
    _unpatch_all()
    _words = []
    for _secs, _want in ((4, "about 10 s left"), (44, "about 40 s left"),
                         (58, "about 1 min left"), (200, "about 3 min left"),
                         (3599, "about 1 h left"), (9500, "about 3 h left")):
        _said = getattr(run.step_progress, "estimate", lambda _s: None)(_secs)
        if _said != _want:
            _words.append(f"{_secs}s: {_said!r}, want {_want!r}")
    check(f"ONEUP-0318 the estimate is rounded and worded as one ({_words})", not _words)

    # The filled Stop, read back as pixels in every theme: `btn_danger`'s gradient
    # with the overlay off, the overlay's `btn` with it on.
    wF = _at_minimum("rows")
    _start_run(wF)
    _sbad = []
    for _th in theme.THEMES:
        _p = dict(_th.palette)
        _hcp = theme._HC_DARK if _th.dark else theme._HC_LIGHT
        for _on in (False, True):
            wF.setStyleSheet(theme.build_theme(_th, high_contrast=_on))
            wF.layout().activate()
            QApplication.processEvents()
            # The window's pixels, not the button's own grab: a transparent fill
            # grabbed alone reads black, which would pass the overlay's black `btn`.
            _at = wF.stop_btn.mapTo(wF, QPoint(6, wF.stop_btn.height() // 2))
            _px = wF.grab().toImage().pixelColor(_at)
            if _on:
                _ok = _px.name() == _hcp["btn"]
            else:
                _a, _b = (QColor(s) for s in _p["btn_danger_stops"])
                _ok = all(min(x, y) - 3 <= z <= max(x, y) + 3 for x, y, z in (
                    (_a.red(), _b.red(), _px.red()), (_a.green(), _b.green(), _px.green()),
                    (_a.blue(), _b.blue(), _px.blue())))
            if not _ok:
                _sbad.append(f"{_th.id} overlay {'on' if _on else 'off'}: {_px.name()}")
    wF.setStyleSheet("")
    check(f"ONEUP-0317 Stop is filled, in every theme ({len(_sbad)} wrong)", not _sbad)
    for line in _sbad[:8]:
        print(f"       {line}")
    run.on_finished(wF, 0, None)

    # --- ONEUP-0260: the package details dialog --------------------------------
    # The mock zypper and rpm on _BIN answer from fixtures written here; the patches
    # record every program details_dialog launches, which is what catches a shell
    # string (INV-1): `sh -c` hands the mock the same argv.
    _sep, _ent = "\x1f", "\x1e"
    _old_entry = f"1700000000{_sep}Pat <pat@example.org>{_sep}- the old entry{_ent}"
    _new_entry = f"1700000000{_sep}Pat <pat@example.org>{_sep}- the new entry{_ent}"
    for _fname, _body in (
            ("zypper-info.txt",
             "Loading repository data...\nReading installed packages...\n\n\n"
             "Information for package alpha:\n------------------------------\n"
             "Repository     : Main\nName           : alpha\nSummary        : The alpha "
             "tool\nDescription    :\n    Alpha does things.\n    On two lines.\n"
             "Upstream URL   : https://example.org/alpha\n\npackage 'beta' not found.\n"),
            ("rpm-baseline.txt", f"alpha{_sep}1{_sep}{_old_entry}"),
            ("rpm-changelog.txt", _new_entry + _old_entry)):
        Path(_DETAILS, _fname).write_text(_body)
    _cache = Path(_DETAILS, "packages", "main", "x86_64")
    _cache.mkdir(parents=True, exist_ok=True)
    (_cache / "alpha-2.x86_64.rpm").write_text("")
    for _log in (_ZYPPER_LOG, _RPM_LOG):
        Path(_log).write_text("")
    _sudo_before = Path(_SUDO_LOG).read_text() if os.path.exists(_SUDO_LOG) else ""
    _launched = []
    _orig_start, _orig_drun = details_dialog._start, details_dialog._run

    def _rec_start(proc, argv):
        _launched.append(argv)
        _orig_start(proc, argv)

    def _rec_run(argv, **kw):
        _launched.append(argv)
        return _orig_drun(argv, **kw)

    _patch(details_dialog, "_start", _rec_start)
    _patch(details_dialog, "_run", _rec_run)

    def _fetch_done(wD, timeout=8.0):
        """Wait out the batching timer and the zypper call it starts."""
        QTest.qWait(details_dialog.BATCH_MS + 100)
        deadline = time.monotonic() + timeout
        while ((wD.details._proc is not None or wD.details._timer.isActive())
               and time.monotonic() < deadline):
            QTest.qWait(50)
        return wD.details._proc is None

    def _details_check(wD):
        wD._check_mode = True
        for line in ("@@CHECK_ITEM@@|system|alpha|1|2|10|Main",
                     "@@CHECK_ITEM@@|system|beta|1|2|10|Main",
                     "@@CHECK_ITEM@@|flatpak|alpha|1|2|10|flathub"):
            run.handle_line(wD, line)

    def _rows_of(wD):
        """(package, display, accessible, column) for every cell of every view."""
        out = []
        for items in vars(wD.host).values():
            if isinstance(items, package_views.PackageItems):
                for r, pkg in enumerate(items.packages()):
                    for c in range(items.columnCount()):
                        ix = items.index(r, c)
                        out.append((pkg, items.data(ix) or "",
                                    items.data(ix, Qt.ItemDataRole.AccessibleTextRole) or "",
                                    c))
        return out

    wD = window.Updater()
    _details_check(wD)
    _early = _rows_of(wD)
    check("ONEUP-0260 INV-4 no package is marked before the fetch completes",
          not any(package_views.MARK in d for _p, d, _a, _c in _early))
    check("ONEUP-0260 the fetch ends", _fetch_done(wD))

    # ONEUP-0334: rpm prints a package's changelog in whatever encoding its packager
    # used, and a real run (2026-10-23) met bytes that are not UTF-8: the baseline
    # read raised UnicodeDecodeError out of _fetch. Both rpm readers must decode
    # leniently. printf stands in for rpm, so the bytes are exactly these.
    def _latin1_rpm(_argv, **kw):
        return subprocess.run(["printf", r"alpha\037\341\370\n"], **kw)  # noqa: S607

    def _raises(call):
        """What `call` raised on undecodable bytes, or "" (UnicodeDecodeError is a ValueError)."""
        try:
            call()
        except ValueError as exc:
            return repr(exc)
        return ""

    _raised = _raises(lambda: package_details._rpm(["rpm"], _latin1_rpm))
    check(f"ONEUP-0334 a changelog that is not UTF-8 is read, not raised {_raised}",
          not _raised)
    _patch(details_dialog, "_run", _latin1_rpm)
    wD.details._based.clear()
    _raised = _raises(wD.details._fetch)
    check(f"ONEUP-0334 the baseline read survives rpm output that is not UTF-8 {_raised}",
          not _raised)
    _patch(details_dialog, "_run", _rec_run)
    _said = app.translate("package_views", "{text}, details available").format(text="")
    for _lid in ("rows", "rail", "spotlight"):
        wD.apply_layout(_lid)
        QApplication.processEvents()
        _cells = _rows_of(wD)
        _sys_alpha = [(d, a, c) for p, d, a, c in _cells if p.key == "system" and p.name == "alpha"]
        _marked = [(d, a, c) for d, a, c in _sys_alpha if package_views.MARK in d]
        check(f"ONEUP-0260 INV-4 the described package carries the mark ({_lid})",
              len(_marked) == 1 and _said.strip(", ") in _marked[0][1]
              and package_views.MARK not in _marked[0][1])
        check(f"ONEUP-0260 INV-4 the undescribed package and the Flatpak carry neither ({_lid})",
              not any(package_views.MARK in d or _said.strip(", ") in a
                      for p, d, a, _c in _cells
                      if not (p.key == "system" and p.name == "alpha")))
        if _lid == "rows":
            check("ONEUP-0260 INV-4 in Rows the mark is in the package column",
                  _marked and _marked[0][2] == 1)

    # ONEUP-0297: the mark is a character Noto Sans, openSUSE's interface font,
    # draws itself. U+24D8 is in no font a stock KDE Live install carries, so it
    # drew as an empty box there; this host may carry a fallback that hides that,
    # so the check asks Noto Sans alone. Skipped where Noto Sans is absent.
    # QRawFont, not QFontMetrics.inFontUcs4: the latter answers for the whole
    # fallback chain, and passed U+24D8 here.
    from PySide6.QtGui import QFontDatabase, QRawFont
    if "Noto Sans" in QFontDatabase.families():
        _noto = QRawFont.fromFont(QFont("Noto Sans"))
        check("ONEUP-0297 the details mark is a character Noto Sans draws",
              _noto.familyName() == "Noto Sans"
              and all(_noto.supportsCharacter(ord(ch)) for ch in package_views.MARK))
    else:
        print("  skip - ONEUP-0297: Noto Sans is not installed on this machine")

    # INV-5: activating a package with details opens one dialog for it; one without
    # opens none. Closed by the scheduled-dismiss idiom of ui-and-accessibility §6.4.
    _opened = []

    def _dismiss_details():
        for tl in app.topLevelWidgets():
            if isinstance(tl, details_dialog.PackageDetailsDialog) and tl.isVisible():
                _opened.append((tl.windowTitle(), tl.text.toPlainText()))
                tl.done(0)

    def _activate(view, items, name, key="system"):
        row = next(n for n, p in enumerate(items.packages()) if p.name == name and p.key == key)
        _opened.clear()
        QTimer.singleShot(50, _dismiss_details)
        view.activated.emit(items.index(row, 0))
        QTest.qWait(100)
        return list(_opened)

    for _lid, _views in (("rows", lambda h: [(h.table, h.items)]),
                         ("rail", lambda h: [(h.board, h.items)]),
                         ("spotlight", lambda h: [(h.next_list, h.next_items)])):
        wD.apply_layout(_lid)
        QApplication.processEvents()
        for _view, _items in _views(wD.host):
            _got = _activate(_view, _items, "alpha")
            check(f"ONEUP-0260 INV-5 activating a described package opens its dialog ({_lid})",
                  len(_got) == 1 and _got[0][0] == "alpha")
            check(f"ONEUP-0260 INV-5 activating an undescribed one opens none ({_lid})",
                  _activate(_view, _items, "beta") == [])
            check(f"ONEUP-0260 INV-5 nor does the Flatpak of the same name ({_lid})",
                  _activate(_view, _items, "alpha", "flatpak") == [])
    wD.apply_layout("rows")
    QApplication.processEvents()
    _first = _activate(wD.host.table, wD.host.items, "alpha")
    check("ONEUP-0260 the dialog shows About and says the notes are not there yet",
          _first and "The alpha tool" in _first[0][1] and "On two lines." in _first[0][1]
          and "https://example.org/alpha" in _first[0][1]
          and app.translate("details_dialog",
                            "The notes show once the new version has downloaded.")
          in _first[0][1])
    run.handle_line(wD, "@@PKG@@|system|downloaded|alpha|2")
    _got = _activate(wD.host.table, wD.host.items, "alpha")
    check("ONEUP-0260 INV-8 a downloaded package's notes are read from the redirected cache",
          any("-qp" in line and str(_cache / "alpha-2.x86_64.rpm") in line
              for line in Path(_RPM_LOG).read_text().split("\n"))
          and _got and "the new entry" in _got[0][1] and "the old entry" not in _got[0][1])
    run.handle_line(wD, "@@PKG@@|system|installed|alpha|2")
    _got = _activate(wD.host.table, wD.host.items, "alpha")
    check("ONEUP-0260 an installed package lists only the entries after its baseline",
          _got and "the new entry" in _got[0][1] and "the old entry" not in _got[0][1]
          and any(line.startswith("C|-q --qf ") and line.endswith(" alpha-2")
                  for line in Path(_RPM_LOG).read_text().split("\n")))

    # INV-1: every program launched is zypper or rpm with a list argv, every mock
    # call ran under LC_ALL=C, and nothing went through the mock sudo.
    # Split on newlines alone: str.splitlines also splits on rpm's U+001E and U+001F.
    _calls = [c for c in (Path(_ZYPPER_LOG).read_text().split("\n")
                          + Path(_RPM_LOG).read_text().split("\n")) if c]
    check(f"ONEUP-0260 INV-1 every details launch is zypper or rpm with a list argv "
          f"({len(_launched)} launches)",
          _launched and all(isinstance(a, list) and a[0] in ("zypper", "rpm")
                            for a in _launched))
    check(f"ONEUP-0260 INV-1 every details call ran with LC_ALL=C ({len(_calls)} calls)",
          _calls and all(c.startswith("C|") for c in _calls))
    for _c in _calls:
        if not _c.startswith("C|"):
            print(f"       not under LC_ALL=C: {_c[:160]!r}")
    _sudo_after = Path(_SUDO_LOG).read_text() if os.path.exists(_SUDO_LOG) else ""
    # The engine an earlier scenario launched may still be probing sudo, so the
    # check is that no sudo call carries a details query, not that there are none.
    _via_sudo = [c for c in _sudo_after[len(_sudo_before):].split("\n")
                 if "rpm" in c or "zypper --no-refresh" in c or " info " in c]
    check("ONEUP-0260 INV-1 no details call went through sudo", not _via_sudo)
    for _c in _via_sudo:
        print(f"       sudo: {_c[:160]!r}")
    check("ONEUP-0260 INV-8 the mock zypper and rpm were both reached, the cache redirected",
          Path(_ZYPPER_LOG).read_text() and Path(_RPM_LOG).read_text()
          and package_details.packages_dir() == os.path.join(_DETAILS, "packages"))
    wD.details.stop()

    # INV-6: the current package of a focused view is drawn in the derived fill. An
    # item is not a widget, so the focus report's row is what reaches it, in every
    # theme with and without the overlay; the grab shows the delegate paints it.
    _rows_seen = {(t.id, hc) for t in theme.THEMES for hc in (False, True)
                  for r in theme.focus_report(t, hc)
                  if r["control"].startswith("current package") and r["kind"] == "fill"
                  and r["ratio"] + 1e-9 >= 3.0}
    check("ONEUP-0260 INV-6 the current-package fill clears 3:1 in every theme, both modes",
          len(_rows_seen) == 2 * len(theme.THEMES))
    wF = window.Updater()
    _details_check(wF)
    wF.show()
    QApplication.processEvents()
    _table = wF.host.table
    _ix = wF.host.items.index(0, 1)
    _table.setCurrentIndex(_ix)

    def _grab_current():
        QApplication.processEvents()
        return _table.viewport().grab(_table.visualRect(_ix)).toImage()

    _table.setFocus()
    _focused = _grab_current()
    _was_focused = _table.hasFocus()
    wF.check_btn.setFocus()
    _unfocused = _grab_current()
    check("ONEUP-0260 INV-6 a focused view's current package differs from it unfocused",
          _was_focused and not _table.hasFocus() and _focused != _unfocused)
    _fill = QColor(_table.palette().color(QPalette.ColorRole.Highlight))
    _sheet_fills = re.findall(r"selection-background-color: (#[0-9a-fA-F]{6})",
                              app.styleSheet())
    check("ONEUP-0260 INV-6 and is drawn in the fill the sheet hands the view",
          _focused.pixelColor(2, 2) == _fill and _sheet_fills
          and _fill.name() == _sheet_fills[-1].lower())
    wF.hide()
    wF.details.stop()

    # INV-7: a fetch never outlives its deadline or a quitting window, and survives
    # the window hiding to the tray. The mock sleeps by exec, so a killed fetch
    # leaves no child; a distinctive duration makes its process findable.
    # The duration carries this process's pid: pgrep is machine-wide, and with a
    # fixed one a second suite running at the same time counted this one's
    # sleeper as its own leak (ONEUP-0264). Not an ancestry filter — a leaked
    # sleeper reparents to systemd --user, and that is exactly the one to find.
    _nap = f"29.{os.getpid()}"
    os.environ["ONEUP_MOCK_ZYPPER_SLEEP"] = _nap

    def _sleepers():
        out = subprocess.run(["pgrep", "-fx", f"sleep {re.escape(_nap)}"],  # noqa: S603, S607 — fixed argv
                             capture_output=True, text=True).stdout
        return out.split()

    def _slow_window():
        wS = window.Updater()
        wS._check_mode = True
        run.handle_line(wS, "@@CHECK_ITEM@@|system|slowpkg|1|2|10|Main")
        QTest.qWait(details_dialog.BATCH_MS + 300)
        return wS

    os.environ["ONEUP_DETAILS_TIMEOUT"] = "1"
    wT = _slow_window()
    _started = wT.details._proc is not None
    _ended = _fetch_done(wT, timeout=5.0)
    check("ONEUP-0260 INV-7 a fetch past its deadline is killed, and marks nothing",
          _started and _ended and not any(package_views.MARK in d
                                          for _p, d, _a, _c in _rows_of(wT)))
    check("ONEUP-0260 INV-7 and leaves no mock process running", not _sleepers())
    os.environ["ONEUP_DETAILS_TIMEOUT"] = "60"
    wN = _slow_window()
    wN._tray = None
    _running = wN.details._proc is not None and bool(_sleepers())
    _ev = QCloseEvent()
    _ev.setAccepted(True)
    wN.closeEvent(_ev)
    QTest.qWait(100)
    check("ONEUP-0260 INV-7 closing a window with no tray ends its fetch",
          _running and _ev.isAccepted() and wN.details._proc is None and not _sleepers())
    wY = _slow_window()
    wY._tray = object()             # resident: closing hides to the tray
    wY._tray_hint_shown = True
    _ev = QCloseEvent()
    wY.closeEvent(_ev)
    QTest.qWait(100)
    check("ONEUP-0260 INV-7 hiding to the tray leaves the fetch running",
          not _ev.isAccepted() and wY.details._proc is not None and bool(_sleepers()))
    wY.details.stop()
    check("ONEUP-0260 INV-7 and quitting then ends it", not _sleepers())
    for _var in ("ONEUP_MOCK_ZYPPER_SLEEP", "ONEUP_DETAILS_TIMEOUT"):
        os.environ.pop(_var, None)
    _unpatch_all()

    # ONEUP-0204: nothing this suite starts may outlive it. With no event loop running, a
    # probe that has exited is never reaped, so at interpreter exit Qt destroys it as
    # "still running" and kills its bash. Collect every one before the summary — with its
    # signals BLOCKED, so reaping runs none of its slots: some windows above carry the real
    # _stand_down_autoupdate with _autoupdate_enabled forced true, and the dialog stubs are
    # restored by now, so a late "@@AUTH@@|off" opened a real modal that nothing closes and
    # hung the suite (ONEUP-0225). Not finished.disconnect(): that segfaulted in Qt.
    left = [p for top in QApplication.topLevelWidgets() for p in top.findChildren(QProcess)
            if shiboken6.isValid(p) and p.state() != QProcess.NotRunning]
    for p in left:
        p.blockSignals(True)
        p.waitForFinished(5000)
    check("every probe a window started has finished before the suite exits",
          all(p.state() == QProcess.NotRunning for p in left if shiboken6.isValid(p)))

    check("no window in the suite tried to reach the network (testing.md §2.3)",
          not network_calls)
    for call in network_calls:
        print(f"         {call}")

    print()
    print("======================================")
    print(f"  Passed: {PASS}   Failed: {FAIL}")
    print("======================================")
    return 1 if FAIL else 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    except Exception:  # noqa: BLE001 — any crash; reported, then exits 1
        # A crash skips every check after it. Say how far the run got, so a crash near
        # the top and one near the bottom stop looking the same (ONEUP-0079).
        traceback.print_exc()
        print()
        print("======================================")
        print(f"  ABORTED after {PASS + FAIL} checks — Passed: {PASS}   Failed: {FAIL}")
        print("======================================")
    finally:
        shutil.rmtree(_SANDBOX, ignore_errors=True)
    sys.exit(code)
