"""One update run, from Run to the summary.

The engine's QProcess and its argv, the marker application that drives the
window, the activity clock that keeps a slow mirror distinguishable from a hang
(ONEUP-0048), and the end-of-run summary.

Two rules this module exists to keep. A step must never claim a success or
advise a reboot it did not earn — `docs/standards/testing.md` §5 owns the four
invariants. And the engine is never signalled to stop: `request_stop` creates
the file the engine watches, because signalling mid-transaction would leave rpm
half-applied or orphan a zypper that carries on regardless (ONEUP-0047).
"""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from functools import partial

import shiboken6
from PySide6.QtCore import QCoreApplication, QProcess, QTimer
from PySide6.QtWidgets import QMessageBox

from .. import APP_ID, APP_NAME
from . import banners, i18n, markers, paths, repos, steps, tray
from .diagnostics import cache_bytes

# How long the engine may produce NOTHING before the liveness line calls it stalled
# (ONEUP-0048). Generously past a normal gap — a big repository's cache rebuild is quiet
# for a while — so the wording is trustworthy when it does appear.
STALL_SECONDS = 45

# How often we look for a held engine's `hold.state` while its dry run is still going
# (ONEUP-0044 §4.5, the middle row of the Update table). That wait is seconds to a
# minute — the whole dry run — and it is the state a user who presses Show download size
# and then immediately presses Update is in.
HOLD_WAIT_POLL_MS = 200


def stop_tooltip(installing: bool) -> str:
    """Stop's tooltip. Which one is true depends on what the run is doing (ONEUP-0095)."""
    if installing:
        return QCoreApplication.translate(
            "run",
            "Packages are being installed, and that cannot be stopped safely "
            "part-way. Stop comes back as soon as this step finishes.")
    return QCoreApplication.translate(
        "run",
        "Stop after the current step. Anything already installed stays "
        "installed — an install is never cut off half-way, because that "
        "can break programs.")


def sync_stop(win):
    """Stop is clickable only while a click can take effect soon (ONEUP-0095). In the
    install phase rpm is mid-transaction, which is never interrupted (security.md
    §6.1), so a click there would sit on "Stopping…" until the step ends — grey it
    out and say why instead. Re-run whenever _progress_phase changes."""
    if win._stop_asked:
        return
    installing = win._progress_phase == "install"
    win.stop_btn.setEnabled(not installing)
    tip = stop_tooltip(installing)
    win.stop_btn.setToolTip(tip)
    win.stop_btn.setAccessibleDescription(tip)


def request_stop(win):
    """Ask the engine to stop at its next safe point by creating the file it watches.
    Not a signal: signalling mid-transaction would either leave rpm half-applied or
    orphan a zypper that carries on anyway (ONEUP-0047)."""
    try:
        paths.RUN_STATE.parent.mkdir(parents=True, exist_ok=True)
        paths.STOP_REQUEST.touch()
    except OSError as exc:
        QMessageBox.warning(win, QCoreApplication.translate(
            "run", "Stop"), QCoreApplication.translate(
            "run",
            "Could not ask the update to stop:\n{exc}").format(exc=exc))
        return
    win._stop_asked = True
    win.stop_btn.setEnabled(False)
    win.stop_btn.setText(QCoreApplication.translate("run", "Stopping…"))
    win.status.setText(QCoreApplication.translate(
        "run",
        "Stopping after the current step — nothing new will start…"))
    win._announce(QCoreApplication.translate("run", "Stopping after the current step."))


def start_check(win):
    _launch(win, win.selected_steps(), check=True)


def start_run(win):
    """Update. The window is in exactly one of three states, and this is the table from
    ONEUP-0044 §4.5 — the fix's whole window side.

    No preview running, or nothing selected -> `_launch`, exactly as today.

    Preview running, `hold.state` present and its line 1 is our own `_size_proc` pid ->
    adopt that process as the run's, so the credential it already cached is the one the
    run uses. That is the fix.

    Preview running, no `hold.state` yet -> WAIT. It must not write `go.request` here:
    the engine's freshness rule compares a go-ahead against a stamp that does not exist
    yet, so an early request is provably stale and would be ignored, leaving the user
    with a dead button.
    """
    proc = getattr(win, "_size_proc", None)
    if proc is not None and proc.state() != QProcess.NotRunning and win.selected_steps():
        win._go_write_failed = False
        if _adopt_held_engine(win):
            return
        if not win._go_write_failed:
            _wait_for_hold(win)
            return
    _launch(win, win.selected_steps(), check=False)


def _adopt_held_engine(win) -> bool:
    """Turn a held preview into the run. False means "cannot adopt" — never an error."""
    proc = getattr(win, "_size_proc", None)
    if proc is None or proc.state() == QProcess.NotRunning:
        return False
    try:
        first = paths.HOLD_STATE.read_text().splitlines()[0].strip()
    except (OSError, IndexError):
        return False       # no hold yet, or a file with no line 1, which is not a hold
    # Line 1 must be OUR engine's pid. That one test refuses both of §6's impostors: a
    # `hold.state` a SIGKILLed engine left behind, and a second window's hold — which
    # has no `_size_proc` of ours to match, so it launches its own engine rather than
    # adopting a hold it did not start.
    if not first.isdecimal() or int(first) != proc.processId():
        return False
    steps = win.selected_steps()
    # The steps travel WITH the go-ahead rather than being fixed at preview time: the
    # preview is started for `system` alone, but the run uses whatever is selected when
    # Update is pressed, which may have changed in between (§4.6).
    try:
        _write_go_request(",".join(steps) + "\n")
    except OSError as exc:
        # Latched, so the caller stops asking (ONEUP-0156). `_wait_for_hold` would
        # otherwise retry a write that has already failed every 200 ms, and on a full
        # or read-only state directory each retry is another modal box.
        win._go_write_failed = True
        QMessageBox.warning(win, QCoreApplication.translate(
            "run", "Update"), QCoreApplication.translate(
            "run",
            "Could not start the update:\n{exc}").format(exc=exc))
        return False
    # Anything the preview read but has not yet split into a whole line. Dropping it
    # would lose the head of whatever marker follows.
    carried = getattr(win, "_size_buf", "")
    _reset_for_run(win, steps, check=False)
    win._buf = carried
    # `_log_path` is assigned from what `request_size` already passed as `--log=`, NOT
    # recomputed from a fresh stamp — see `_reset_for_run`'s docstring.
    win._log_path = win._hold_log
    win.bar.setRange(0, win._total)
    win.bar.setValue(0)
    win.bar.setFormat(QCoreApplication.translate("run", "Starting…"))
    win.status.setText(QCoreApplication.translate("run", "Starting the update…"))
    win.set_controls_enabled(False)
    proc.readyReadStandardOutput.disconnect()
    proc.finished.disconnect()
    proc.readyReadStandardOutput.connect(partial(on_output, win))
    proc.finished.connect(partial(on_finished, win))
    proc.errorOccurred.connect(partial(on_error, win))
    win.proc = proc
    win._size_proc = None
    return True


def _write_go_request(text: str) -> None:
    """Write `go.request` whole. The engine reads its first line the moment the file is
    newer than its hold stamp, so a truncate-then-write could be read empty — and an
    empty go-ahead is refused. A rename is atomic: the engine sees all of it or none."""
    target = paths.GO_REQUEST
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(name, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(name)
        raise


def _wait_for_hold(win):
    """The middle row of §4.5's table: a preview is running but has not reached its hold
    yet, so wait for it rather than starting a second engine (which is the defect) or
    writing a go-ahead the engine would discard as stale."""
    if getattr(win, "_hold_wait", None) is None:
        win._hold_wait = QTimer(win)
        win._hold_wait.setInterval(HOLD_WAIT_POLL_MS)
        win._hold_wait.timeout.connect(partial(_hold_wait_tick, win))
    win.status.setText(QCoreApplication.translate(
        "run",
        "Working out the download size first — the update starts as soon "
        "as that finishes…"))
    win._announce(QCoreApplication.translate(
        "run",
        "Working out the download size first. The update will start as "
        "soon as that finishes."))
    win.set_controls_enabled(False)
    win._hold_wait.start()


def _hold_wait_tick(win):
    proc = getattr(win, "_size_proc", None)
    if proc is None or proc.state() == QProcess.NotRunning:
        # The preview failed or was cancelled before it ever held. Fall back to starting
        # a fresh engine, which is today's behaviour and today's two prompts — the fix
        # degrades to the status quo, never to an error (INV-7).
        win._hold_wait.stop()
        win.set_controls_enabled(True)
        _launch(win, win.selected_steps(), check=False)
        return
    win._go_write_failed = False
    if _adopt_held_engine(win):
        win._hold_wait.stop()
    elif win._go_write_failed:
        # The go-ahead could not be written and would fail again. Fall back to a fresh
        # engine — the status quo, as for a preview that never held (INV-7).
        win._hold_wait.stop()
        win.set_controls_enabled(True)
        _launch(win, win.selected_steps(), check=False)


def retry_failed(win):
    if win._failed_steps:
        _launch(win, list(win._failed_steps), check=False)


def request_size(win, key: str):
    """Fetch the exact download size for a step on demand (system only). Runs
    the engine's --size mode, which authenticates and does a `zypper dup
    --dry-run`, so it stays out of the password-free --check path."""
    if key != "system" or not paths.engine_available():
        return
    row = win.rows.get(key)
    if not row:
        return
    proc = getattr(win, "_size_proc", None)
    if proc is not None and proc.state() != QProcess.NotRunning:
        return  # a fetch is already in flight
    if not paths.log_dir_ready(win):
        return
    row.size_pending()
    # The button's "up to a minute" label is invisible to a screen reader, so
    # say it out loud too — otherwise a blind user gets silence for the wait.
    win._announce(QCoreApplication.translate(
        "run",
        "Working out the download size — this can take up to a minute."),
                   row.size_btn)
    win._size_buf = ""
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    # Named as a RUN log, not `<stamp>.size.log`, because --hold means this preview may
    # become the run. The engine writes its --log= value verbatim into `run.state` for
    # run-following, so a run that logged to a `.size.log` would be followed at a path
    # `_log_path` does not name and "Open log file" would show the wrong file. Naming it
    # correctly up front costs nothing and needs no extra payload in `go.request`
    # (ONEUP-0044 §4.5). Held here rather than in `_log_path`, which must keep pointing
    # at the last real run until this preview actually becomes one.
    size_log = paths.STATE_LOG_DIR / f"{stamp}.log"
    win._hold_log = size_log
    p = QProcess(win)
    p.setProcessChannelMode(QProcess.MergedChannels)
    p.readyReadStandardOutput.connect(partial(_on_size_output, win))
    p.finished.connect(partial(_on_size_finished, win))
    win._size_proc = p
    # --hold keeps this process alive after it has quoted the size, so the run that
    # follows reuses the credential it has already cached. Two engines are two sudo
    # timestamp records and therefore two password dialogs, because with no terminal sudo
    # keys its cache to the PARENT process id (ONEUP-0044).
    argv = paths.engine_argv(f"--size={key}", "--hold", f"--log={size_log}")
    p.start(argv[0], argv[1:])


def _on_size_output(win):
    chunk = bytes(win._size_proc.readAllStandardOutput()).decode(errors="replace")
    win._size_buf = (win._size_buf + chunk).replace("\r\n", "\n").replace("\r", "\n")
    while "\n" in win._size_buf:
        line, win._size_buf = win._size_buf.split("\n", 1)
        if line.startswith("@@SIZE@@|"):
            parts = line[len("@@SIZE@@|"):].split("|")
            if len(parts) >= 2:
                row = win.rows.get(parts[0])
                if row:
                    row.set_size_result(QCoreApplication.translate(
                        "run", "↓ {size} to download").format(size=parts[1]))
        elif line.startswith("@@HINT@@|"):
            # The size probe failed (busy package manager, cancelled password
            # prompt). Say why in the log — the link re-arms itself for a retry
            # in _on_size_finished, but a silent re-arm looks like a dead button.
            win.log.appendPlainText(markers.render_hint(line.split("|")[1:]))
        elif not line.startswith("@@"):
            win.log.appendPlainText(line)


def _on_size_finished(win, exit_code: int, _status):
    # Clear the held-engine state FIRST. The early return below fires whenever a size
    # arrived — which is exactly when a hold existed — so anything placed after it would
    # never run for a held engine, and the window would go on offering a process that has
    # gone. Expiry, Cancel and a killed engine all land here, and all three must degrade
    # to today's behaviour rather than to an error: the next Update simply launches a
    # fresh engine (ONEUP-0044 §4.2, INV-7).
    win._size_proc = None
    win._hold_log = None
    # A window Qt already destroyed (quitting mid-probe, or teardown at exit) has nothing
    # left to update, and touching its row raises (ONEUP-0204).
    if not shiboken6.isValid(win):
        return
    row = win.rows.get("system")
    if not row or not shiboken6.isValid(row) or row.has_size():
        return
    # No SIZE marker arrived. Exit 0 = solver found nothing to fetch; non-zero
    # = auth cancelled or an error, so re-arm the link for a retry.
    if exit_code == 0:
        row.set_size_result(QCoreApplication.translate("run", "Nothing to download"))
    else:
        row.size_failed()


def _engine_args(steps: list[str], check: bool = False, import_keys: bool = False,
                  skip_repos: list[str] | None = None) -> list[str]:
    """Build the engine ARGUMENTS for the stable flags (steps/check/import_keys),
    plus one --skip-repo=<alias> per entry in skip_repos. The engine itself is not
    in here: `_launch` hands these to `paths.engine_argv`, which decides which
    engine runs (ONEUP-0054 §4.7). `_launch` also inserts --log=<path> at call
    time — this helper doesn't know about the log path."""
    args = [f"--steps={','.join(steps)}"]
    if check:
        args.append("--check")
    elif import_keys:
        args.append("--import-keys")
    for alias in (skip_repos or []):
        args.append(f"--skip-repo={alias}")
    return args


def _reset_for_run(win, steps: list[str], check: bool):
    """Everything a run needs cleared before it starts, factored out of `_launch`
    because ONEUP-0044's adopt path needs it too.

    An adopt path that only re-pointed `on_output`, `on_finished` and `on_error` would
    ship a run with no progress range, stale banners and badges from the previous run,
    and `_run_active` false — which leaves the standalone thin-snapshots action
    unguarded (§4.5).

    `_log_path` is deliberately NOT here, and that exclusion is the point of the
    paragraph above it in the spec. `_launch` computes it from a fresh
    `datetime.now()` stamp, so a shared block run on the adopt path would overwrite it
    with a path no engine ever wrote to — and disagree with `run.state` line 2, so a
    window following the run would look for the log in the wrong place and "Open log
    file" would show the wrong file. The stamp and the assignment stay in `_launch`;
    the adopt path keeps the path `request_size` already passed as `--log=`.
    """
    # Reset per-run state and any banners/badges from a previous run.
    win._check_mode = check
    win._reboot = False
    win._reboot_reason = ""
    win._installed_count = ""
    win._sys_changed = False
    win._step_caption = ""
    win._progress_phase = ""
    win._done_status = ""
    _reset_activity(win)
    win._failed_steps = []
    win._services = ""
    win._snapshot = ""
    win._snapshots = []
    win._hints = []
    win._hint_commands = []
    win._skipped_repos = []
    win._unchecked = []
    win._buf = ""
    win._total = len(steps)
    for b in (win.reboot_banner, win.services_banner, win.warn_banner):
        b.setVisible(False)
    # Reset the warning banner's button back to its default "Show details" role
    # (a previous run may have switched it to the repo-manager action).
    win._warn_repo_dup = False
    win._warn_snapshots = False
    win.warn_btn.setText(QCoreApplication.translate("run", "Show details"))
    win.warn_btn.setEnabled(True)
    win._hint_command = ""
    win._remedy_keys = False
    win._remedy_skips = []
    win._remedy_unknown = []
    win._run_active = not check   # a real run guards the standalone thin action
    # Separate from `_run_active`, which answers "may the standalone thin action
    # run?" and is False on a check. The liveness line has to work on BOTH paths:
    # a check is the metadata-refresh phase ONEUP-0048 was written for, and its
    # progress bar is indeterminate, so it animates whether or not the engine is
    # alive. One flag cannot answer both questions.
    win._liveness_active = True
    win._activity_timer.start()   # stopped again in on_finished
    win.warn_copy_btn.setVisible(False)
    win.warn_btn2.setVisible(False)
    win.retry_btn.setVisible(False)
    win.rollback_btn.setVisible(False)
    for r in win.rows.values():
        r.clear_badge()
        r.clear_details()
    win.log.clear()


def _launch(win, steps: list[str], check: bool, import_keys: bool = False,
            skip_repos: list[str] | None = None):
    if not steps:
        QMessageBox.information(win, QCoreApplication.translate("run", "Nothing selected"),
                                QCoreApplication.translate(
                                    "run",
                                    "Turn on at least one task first."))
        return
    if not paths.engine_available():
        QMessageBox.critical(win, QCoreApplication.translate("run", "Engine missing"),
                             QCoreApplication.translate(
                                 "run", "Could not find the update engine:\n{tried}").format(
                                     tried=paths.engine_tried()))
        return
    # Never start a second engine while a download-size preview is in flight. Doing so
    # IS the ONEUP-0044 defect: with no terminal sudo keys its cached credential to the
    # parent process id, so two engines are two timestamp records and two password
    # dialogs. `start_run` routes to the held engine instead of coming here; this guard
    # covers the other ways in — Check for updates, and Retry failed steps.
    size_proc = getattr(win, "_size_proc", None)
    if size_proc is not None and size_proc.state() != QProcess.NotRunning:
        QMessageBox.information(
            win, QCoreApplication.translate("run", "Just a moment"),
            QCoreApplication.translate(
                "run",
                "OneUp is working out the download size.\n\nThat takes up to a "
                "minute. Try again once it has finished."))
        return

    if not paths.log_dir_ready(win):
        return
    _reset_for_run(win, steps, check)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    win._log_path = paths.STATE_LOG_DIR / (f"{stamp}.check.log" if check else f"{stamp}.log")

    if check:
        win.bar.setRange(0, 0)  # indeterminate
        win.bar.setFormat(QCoreApplication.translate("run", "Checking…"))
        win.status.setText(QCoreApplication.translate("run", "Checking for available updates…"))
    else:
        win.bar.setRange(0, win._total)
        win.bar.setValue(0)
        win.bar.setFormat(QCoreApplication.translate("run", "Starting…"))
        win.status.setText(QCoreApplication.translate(
            "run",
            "Authenticating… (approve the password popup)"))
    win.set_controls_enabled(False)

    args = _engine_args(steps, check, import_keys, skip_repos)
    args.insert(1, f"--log={win._log_path}")  # after --steps, before --check/etc.
    win.proc = QProcess(win)
    win.proc.setProcessChannelMode(QProcess.MergedChannels)
    win.proc.readyReadStandardOutput.connect(partial(on_output, win))
    win.proc.finished.connect(partial(on_finished, win))
    win.proc.errorOccurred.connect(partial(on_error, win))
    argv = paths.engine_argv(*args)
    win.proc.start(argv[0], argv[1:])


def on_output(win):
    chunk = bytes(win.proc.readAllStandardOutput()).decode(errors="replace")
    # Stamped on the raw chunk, before any line splitting: zypper's progress is a
    # stream of dots with no line ending, so a partial line is the only proof of life
    # during a metadata fetch. Waiting for a complete line would call a working
    # download stalled (ONEUP-0048).
    if chunk:
        win._activity_at = time.monotonic()
    # Normalise carriage returns to newlines on the ACCUMULATED buffer (so a CRLF
    # straddling two read chunks doesn't become a spurious blank line) — this keeps
    # a tool's \r progress output from prepending text to a marker and hiding it.
    win._buf = (win._buf + chunk).replace("\r\n", "\n").replace("\r", "\n")
    while "\n" in win._buf:
        line, win._buf = win._buf.split("\n", 1)
        handle_line(win, line)


def _show_detail(win, detail: str):
    """One progress sentence on the status line and the bar's caption, which
    carries the step's caption in front of it when there is one."""
    win.status.setText(QCoreApplication.translate("run", "{detail}…").format(detail=detail))
    win.bar.setFormat(QCoreApplication.translate("run", "{caption} — {detail}").format(
        caption=win._step_caption, detail=detail) if win._step_caption
        else QCoreApplication.translate("run", "{detail}…").format(detail=detail))


def handle_line(win, line: str):
    if line.startswith("@@"):
        handle_marker(win, line)
        return
    win.log.appendPlainText(line)


def _set_activity(win, text: str):
    win.activity.setText(text)
    win.activity.setVisible(bool(text))


def _reset_activity(win):
    """Clear the liveness line and start its clock. Called as a run begins — the
    first thing being waited on is the password prompt, which counts as activity."""
    win._activity_at = time.monotonic()
    win._activity_what = ""
    win._activity_since = 0.0
    win._activity_stalled = False
    win._dl_at = win._dl_from = win._dl_bytes = win._dl_total = 0
    # Weighed once, before anything is fetched, so later samples measure THIS run's
    # download. Packages already cached are inside the baseline and rightly excluded —
    # zypper won't re-fetch them, and counting them would flatter the rate.
    win._dl_base = cache_bytes()
    _set_activity(win, "")


def _tick_activity(win):
    """Redraw the liveness line: what we're waiting on, for how long, and how fast
    it's moving. Runs every 5s for the length of a run, and again whenever fresh
    figures arrive, so the answer to "has it stalled?" is always on screen."""
    if not getattr(win, "_liveness_active", False):
        return
    now = time.monotonic()
    bits = []
    if win._activity_what and win._activity_since:
        waited = markers._format_duration(int(now - win._activity_since))
        bits.append(QCoreApplication.translate("run", "{what} — {waited}").format(
            what=win._activity_what, waited=waited))
    # Two byte sources, whichever is further along: what zypper printed (per-package
    # sizes, when it prints them at all) and what its package cache actually weighs.
    # The cache is the only one that covers the prefetch phase — the phase a big
    # download spends its time in, and the one that reports nothing whatsoever.
    got = win._dl_bytes
    if win._progress_phase == "download":
        got = max(got, cache_bytes() - win._dl_base)
    if got > 0:
        human = markers._format_size(got)
        bits.append(f"{human} of {markers._format_size(win._dl_total)}"
                    if win._dl_total else human)
        if not win._dl_at:                       # anchor the rate on first sight
            win._dl_at, win._dl_from = now, got
        # Averaged over the whole download, not sampled: an average is steady enough
        # to read, and the question being asked is "will this ever finish?".
        secs, moved = now - win._dl_at, got - win._dl_from
        if secs >= 1 and moved > 0:
            bits.append(f"{markers._format_size(int(moved / secs))}/s")
    quiet = int(now - win._activity_at) if win._activity_at else 0
    stalled = quiet >= STALL_SECONDS
    # The server is blamed only while something is known to be downloading: a source
    # being fetched before any package phase, or the system step's download phase
    # (ONEUP-0232). Anything else going quiet — flatpak deploying to a busy disk, an
    # install — is not the server's, and Stop is prompt only while downloading
    # (ONEUP-0085), so neither claim is made there.
    fetching = (win._progress_phase == "download"
                or (not win._progress_phase and bool(win._activity_what)))
    if stalled and fetching:
        bits.append(QCoreApplication.translate(
            "run", "nothing received for {duration} — the server may have stalled. "
            "Stopping now is safe.").format(duration=markers._format_duration(quiet)))
    elif stalled:
        bits.append(QCoreApplication.translate(
            "run", "nothing new for {duration} — still working").format(
                duration=markers._format_duration(quiet)))
    elif bits:
        bits.append(QCoreApplication.translate("run", "still working"))
    separator = QCoreApplication.translate(
        "run", " · ", "separator between the parts of the activity line")
    _set_activity(win, separator.join(bits))
    # Announced on the transition only — a live region that speaks every tick would
    # bury the rest of the run, but going quiet for minutes is genuinely news.
    if stalled != win._activity_stalled:
        win._activity_stalled = stalled
        if stalled:
            win._announce(QCoreApplication.translate(
                "run",
                "No response from the server. Stopping now is safe.")
                          if fetching else QCoreApplication.translate(
                              "run",
                              "No new output for a while. Still working."))


def handle_marker(win, line: str):
    split = markers.split_marker(line)
    if split is None:
        # A line that starts with @@ but isn't a real marker (e.g. a diff hunk
        # header "@@ -1,4 +1,4 @@") is ordinary output — log it, don't drop it.
        win.log.appendPlainText(line)
        return
    tag, parts, rest = split
    if tag == "STEP_BEGIN":
        # Guard the fixed 3-field unpack + int(): the engine's output is merged
        # stdout+stderr, so a marker line can be spliced by interleaved text. A
        # malformed STEP_BEGIN must never throw out of the QProcess read slot —
        # that would abort parsing and drop the run's later markers. Three since
        # ONEUP-0072 retired the label: a floor of four would ignore every one.
        if len(parts) < 3 or not parts[1].isdecimal():
            return
        key, index, total = parts[0], parts[1], parts[2]
        # The window's own phrasing, keyed by step. A key it has no entry for gets
        # the long fallback where there is room for a sentence and the bare key in
        # the caption, which has none (ONEUP-0108 §4.3, ONEUP-0072 §4.1's table).
        phrasing = steps.IN_PROGRESS.get(key)
        if phrasing:
            phrasing = QCoreApplication.translate("steps", phrasing)
        label = phrasing or markers.fallback_long(key)
        win.status.setText(QCoreApplication.translate(
            "run",
            "{phrasing}…").format(phrasing=phrasing) if phrasing else label)
        # Kept so @@PROGRESS@@ can rebuild the bar's caption without re-deriving
        # the step's label and position from a marker it doesn't carry.
        win._step_caption = QCoreApplication.translate(
            "run", "{phrasing}  (step {index} of {total})").format(
                phrasing=phrasing or key, index=index, total=total)
        win._progress_phase = ""
        sync_stop(win)
        # A new step is a new thing to wait on, and its own download: carrying the
        # previous step's elapsed time or byte rate over would misreport both.
        win._activity_what = ""
        win._activity_since = 0.0
        win._dl_at = win._dl_from = win._dl_bytes = win._dl_total = 0
        _tick_activity(win)   # redraw now; a 5s-stale line would name the old step
        win.bar.setFormat(win._step_caption)
        win.bar.setValue(int(index) - 1)
        # Progress out loud: without this a blind user gets silence for the
        # whole run. Announced AFTER status.setText, so the fallback path's
        # Alert reads text that already matches.
        win._announce(QCoreApplication.translate(
            "run",
            "{label}, step {index} of {total}").format(label=label, index=index, total=total))
    elif tag == "STEP_END":
        # Clamp: a duplicate/orphaned STEP_END (markers can be spliced) must not
        # push the bar past the run's total step count.
        win.bar.setValue(min(win.bar.value() + 1, win._total))
        key = parts[0]
        status = parts[1] if len(parts) >= 2 else ""
        # The code and its arguments (ONEUP-0072 §4.1); the window words the badge.
        code, args = (parts[2] if len(parts) >= 3 else ""), parts[3:]
        # Badge the task row with what actually happened (mirrors the "N available"
        # badge --check shows, but for a real run: "3 installed", "Up to date", …).
        row = win.rows.get(key)
        if row:
            badge = markers._step_badge(status, code, args)
            row.set_badge(badge)
            # The outcome, spoken once. A later TIMING/FREED marker refines the
            # badge but is NOT re-announced — it stays reachable by Tab via the
            # switch's accessible description. Two utterances per step is the budget.
            win._announce(QCoreApplication.translate(
                "run",
                "{title}: {badge}").format(title=row.title, badge=badge), row.badge)
        if status == "fail":
            win._failed_steps.append(key)
    elif tag == "TIMING":
        # How long the step took, appended to its row badge ("3 installed · 42s").
        key = parts[0]
        secs = int(parts[1]) if len(parts) > 1 and parts[1].isdecimal() else 0
        row = win.rows.get(key)
        if row:
            row.set_timing(markers._format_duration(secs))
    elif tag == "FREED":
        # Disk the cache clean reclaimed, shown as the cache row's badge
        # ("Reclaimed 1.4G  ·  <1s"). Emitted after STEP_END, so it replaces
        # the generic "Done" badge the step-end set.
        key = parts[0]
        human = parts[1] if len(parts) > 1 else ""
        row = win.rows.get(key)
        if row and human:
            row.set_badge(QCoreApplication.translate(
                "run",
                "Reclaimed {human}").format(human=human))
    elif tag == "CHECK":
        key, count = parts[0], (parts[1] if len(parts) > 1 else "0")
        if key == "TOTAL":
            win._installed_count = count
        else:
            row = win.rows.get(key)
            if row:
                n = int(count) if count.isdecimal() else 0
                row.set_badge(QCoreApplication.translate("run", "{count} available").format(
                    count=n) if n > 0 else QCoreApplication.translate("run", "up to date"))
    elif tag == "CHECK_UNKNOWN":
        # This step couldn't read one of its sources, so its count is a floor,
        # not an answer. Recorded so on_finished can refuse the "up to date"
        # summary — the whole point of the marker (ONEUP-0056).
        win._unchecked.append(markers.render_check_unknown(parts[1:]))
        row = win.rows.get(parts[0])
        if row:
            # Text, not colour: the badge must read as unknown to everyone.
            row.set_badge(QCoreApplication.translate("run", "couldn't check"))
    elif tag == "CHECK_ITEM":
        # One changed package for the expandable preview: key|name|from|to.
        if len(parts) >= 2:
            row = win.rows.get(parts[0])
            if row:
                frm = parts[2] if len(parts) > 2 else ""
                to = parts[3] if len(parts) > 3 else ""
                row.add_detail_item(parts[1], frm, to)
    elif tag == "INSTALLED":
        win._installed_count = parts[0]
        win._sys_changed = len(parts) > 1 and parts[1] == "yes"
    elif tag == "SNAPSHOT":
        win._snapshot = parts[0]
    elif tag == "SNAPSHOT_ITEM":
        # One recent restore point for the rollback picker: id|date|description.
        # Keep only well-formed numeric ids (the id is later interpolated into a
        # root `snapper rollback`, so a spliced non-numeric payload must never
        # be captured). Oldest→newest as the engine emits them.
        if parts and parts[0].isdecimal():
            date = parts[1] if len(parts) > 1 else ""
            desc = parts[2] if len(parts) > 2 else ""
            win._snapshots.append((parts[0], date, desc))
    elif tag == "PROGRESS":
        # Live per-package progress inside a step (ONEUP-0040). Without this the
        # app shows one static line for the whole download — a user reasonably
        # read a working 379 MiB fetch as a hang and quit mid-transaction.
        # Guarded like STEP_BEGIN: the engine's stdout and stderr are merged, so
        # any marker can arrive spliced, and a throw here would abort parsing and
        # drop the rest of the run's markers.
        if len(parts) < 4 or not parts[1].isdecimal() or not parts[2].isdecimal():
            return
        key, phase = parts[0], parts[3]
        n, total = int(parts[1]), int(parts[2])
        downloading = phase == "download"
        # total 0 = zypper's preload phase, which reports no denominator. Show the
        # honest running tally rather than inventing one. Whole sentences per phase,
        # never a verb dropped into a frame (wording-and-translation.md §6.2).
        if total:
            detail = (QCoreApplication.translate("run", "Downloading {n} of {total} packages")
                      if downloading else
                      QCoreApplication.translate("run", "Installing {n} of {total} packages"))
        else:
            detail = (QCoreApplication.translate("run", "Downloading packages — {n} so far")
                      if downloading else
                      QCoreApplication.translate("run", "Installing packages — {n} so far"))
        detail = detail.format(n=n, total=total)
        _show_detail(win, detail)
        row = win.rows.get(key)
        if row:
            row.set_badge(QCoreApplication.translate(
                "run",
                "{n}/{total}").format(n=n, total=total) if total else str(n))
        # Spoken once per phase, not per package: a screen reader announcing all
        # 141 packages would bury everything else, but silence through the run's
        # longest stretch is exactly what made it look hung.
        announce = phase != win._progress_phase
        win._progress_phase = phase
        sync_stop(win)
        # Optional trailing byte fields: how much zypper says has come down, and its
        # total for the transaction. Either may be 0 for "not known" — during the
        # prefetch phase zypper reports no sizes at all, and the liveness line falls
        # back to weighing the package cache. Set the phase FIRST: that fallback is
        # gated on it, so a stale phase would skip the very first measurement.
        if len(parts) > 4 and parts[4].isdecimal():
            win._dl_bytes = max(win._dl_bytes, int(parts[4]))
            if len(parts) > 5 and parts[5].isdecimal() and int(parts[5]):
                win._dl_total = int(parts[5])
            _tick_activity(win)
        if announce:
            win._announce(QCoreApplication.translate("run", "Downloading packages.")
                          if downloading else
                          QCoreApplication.translate("run", "Installing packages."))
    elif tag == "REFRESH":
        # Which source is being fetched, and how far through the list (ONEUP-0048).
        # This phase used to be a blank several minutes: zypper reports it as dots
        # with no line ending, so there was nothing for the log pane to draw, and a
        # crawling mirror was indistinguishable from a hung app.
        if len(parts) < 3 or not parts[0].isdecimal() or not parts[1].isdecimal():
            return
        n, total, alias = int(parts[0]), int(parts[1]), parts[2]
        _show_detail(win, QCoreApplication.translate(
            "run", "Checking for updates from {alias} ({n} of {total} sources)").format(
                alias=alias, n=n, total=total))
        win._activity_what = QCoreApplication.translate("run", "Fetching {alias}").format(
            alias=alias)
        win._activity_since = time.monotonic()
        _tick_activity(win)
    elif tag == "SERVICES":
        win._services = rest.strip()
    elif tag == "HINT":
        # A code and its arguments; the window holds the sentence (ONEUP-0108), and
        # the command it names beside it, for Copy command (ONEUP-0235).
        win._hints.append(markers.render_hint(parts))
        win._hint_commands.append(markers.hint_command(parts))
    elif tag == "REPO_SKIPPED":
        # A source was set aside for this run (disabled, upgrade ran, will be
        # re-enabled by the engine on exit — see --skip-repo/--auto-skip-repos).
        if parts:
            alias = parts[0]
            win._skipped_repos.append(alias)
            win.log.appendPlainText(QCoreApplication.translate(
                "run", "  Set aside this run: {alias} (will retry next time)").format(
                    alias=alias))
    elif tag == "REMEDY":
        # The engine says a one-click fix is available for this run's failure:
        # "import-keys" (a rotated/expired repo signing key) and/or "skip-repo"
        # (a single broken source — offer to set it aside and update the rest).
        # Armed here; the warn banner offers them in on_finished, the key-import
        # one behind a confirmation.
        if parts and parts[0] == "import-keys":
            win._remedy_keys = True
        elif (parts and parts[0] == "skip-repo" and len(parts) >= 2
              and repos._ALIAS_RE.fullmatch(parts[1])):
            # Checked because the alias goes back to the engine as --skip-repo=
            # (security.md §4, ONEUP-0144): the same guard the repository editor uses.
            win._remedy_skips.append(parts[1])
        elif parts and parts[0] not in ("import-keys", "skip-repo"):
            # A fix this window does not know: arm no button — there is no action it
            # can perform — and say so in the banner (ONEUP-0072 §4.1). The two known
            # actions above are this family's register; a retired one stays as a
            # commented-out arm there (§4.2).
            win._remedy_unknown.append(parts[0])
    elif tag == "REBOOT":
        win._reboot = parts[0] == "yes"
        # Optional field: the codes naming what makes the reboot matter (a new
        # kernel, a graphics driver, …), worded here. Absent for a plain reboot.
        win._reboot_reason = markers.render_reboot_reason(parts[1] if len(parts) > 1 else "")
    elif tag == "SNAPSHOTS" and parts and parts[0] == "warn":
        # Pre-flight: a lot of Btrfs restore points have piled up and may be using
        # disk. Offer a one-click thin (snapper's own retention cleanup) via the
        # warn banner. The "thinned|N" variant comes from the dedicated
        # --thin-snapshots process and is read in _on_thin_finished, not here.
        win._snapshot_count = int(parts[1]) if len(parts) > 1 and parts[1].isdecimal() else 0
        win._warn_snapshots = True
        win.warn_btn.setText(QCoreApplication.translate("run", "Thin snapshots…"))
        banners._show_warning(win,
            QCoreApplication.translate(
                "run",
                "{snapshot_count} system restore points (snapshots) are stored. "
                "On Tumbleweed these build up with each update and can use a lot "
                "of disk space — you can safely thin the older ones.").format(
                    snapshot_count=win._snapshot_count))
    elif tag in ("DISK", "REPO"):
        # Pre-flight warnings (low disk / duplicate repos). Surface immediately so
        # the advertised warning is visible during the run, not buried in the log.
        if tag == "DISK" and len(parts) >= 3:
            msg = QCoreApplication.translate(
                "run", "Low disk space on {mount} — only {free} free. Updating may fail.").format(
                    mount=parts[1], free=parts[2])
        elif tag == "REPO":
            # parts: warn|duplicate|<space-joined urls>. Name the culprit(s) and
            # point the banner's button at the repo manager to fix it in-app.
            urls = parts[2].strip() if len(parts) >= 3 else ""
            if urls:
                msg = QCoreApplication.translate(
                    "run", "Duplicate repository URL(s): {urls}. Open Repositories to "
                    "turn off or remove the extra copy.").format(urls=urls)
            else:
                msg = QCoreApplication.translate(
                    "run",
                    "Duplicate repository URLs detected — a common cause of update conflicts.")
            win._warn_repo_dup = True
            win.warn_btn.setText(QCoreApplication.translate("run", "Manage repositories…"))
        else:
            msg = QCoreApplication.translate("run", "Pre-flight warning — see the log for details.")
        banners._show_warning(win, msg)
    elif tag == "DONE":
        # The overall result normally comes from the process exit code in
        # on_finished (the two always agree). It is recorded here as well for the
        # one case with no exit code to read: a run started by an earlier OneUp
        # window that this one attached to and is following through its log
        # (_attach_to_running_engine).
        win._done_status = parts[0] if parts else ""


def on_error(win, _err):
    win.status.setText(QCoreApplication.translate("run", "Could not start the update script."))
    win.bar.setRange(0, 1)
    win.set_controls_enabled(True)
    # QProcess does not emit `finished` after a start failure, so nothing else
    # clears these — and a window left mid-run blocks the thin action for the rest
    # of the session and warns "an update is still running" on every quit.
    win._run_active = False
    win._liveness_active = False
    win._activity_timer.stop()
    # Release the process object on a start failure too (finished never fires here).
    win.proc.deleteLater()


def _notify_when_away(win, body: str, urgency: str = "normal"):
    """Fire a desktop notification for a finished run, but only when the window
    isn't focused — you started an update and tabbed away, so tell you it's done.
    Best-effort: skipped if notify-send is absent (like the engine's own hint)."""
    if win.isActiveWindow() or not shutil.which("notify-send"):
        return
    try:
        subprocess.Popen(  # noqa: S603 — fixed argv, no shell.
            ["notify-send", "-a", APP_NAME, "-i", APP_ID,  # noqa: S607
             "-u", urgency, APP_NAME, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def _first_hint_command(win) -> str:
    """The command the first hint names, recorded beside it as it arrived, or ''."""
    return win._hint_commands[0] if win._hints and win._hint_commands else ""


def on_finished(win, exit_code: int, _status):
    # Flush any final line the engine emitted without a trailing newline before
    # computing the summary, so a last marker can't be silently dropped.
    if win._buf.strip():
        handle_line(win, win._buf)
    win._buf = ""
    win._run_active = False
    win._liveness_active = False
    win._activity_timer.stop()
    _set_activity(win, "")
    # Release the finished process so QProcess instances don't accumulate on the
    # window across a long session (each run parents a new one to win). There may be
    # no process at all: a run we merely FOLLOWED belongs to another window, and this
    # is called from _poll_attached_run with only the log to go on (ONEUP-0045).
    proc = getattr(win, "proc", None)
    if proc is not None:
        proc.deleteLater()
    ok = exit_code == 0
    win.set_controls_enabled(True)

    if win._check_mode:
        win.bar.setRange(0, 1)
        win.bar.setValue(1)
        win.bar.setFormat(QCoreApplication.translate("run", "Check complete"))
        n = win._installed_count
        total = int(n) if n.isdecimal() else 0
        # A count built on sources we couldn't read is a floor, not an answer, so
        # it must never be dressed up as an all-clear — that is the bug this whole
        # marker exists to prevent: the app said "up to date 🎉" while 8 updates
        # were waiting, because a repository it silently skipped held them all
        # (ONEUP-0056). Say what we found AND what we couldn't see.
        if win._unchecked:
            win.status.setText(
                i18n.counted("updates-partial", total) if total
                else QCoreApplication.translate(
                    "run", "Couldn't check for updates — no sources could be read."))
            between = QCoreApplication.translate(
                "run", "  ", "separator between whole sentences in one banner")
            banners._show_warning(win, between.join(win._unchecked))
        else:
            win.status.setText(
                i18n.counted("updates-available-run", total) if total
                else QCoreApplication.translate("run", "Everything is up to date. 🎉"))
        win._announce(win.status.text())
        if total:
            away = i18n.counted("updates-available", total)
        elif win._unchecked:
            away = QCoreApplication.translate("run", "Couldn't check for updates.")
        else:
            away = QCoreApplication.translate("run", "Everything is up to date.")
        _notify_when_away(win, away)
        tray._apply_tray_total(win, total, uncertain=bool(win._unchecked))
        win._check_mode = False
        return

    # A stopped run is neither: nothing went wrong, but it didn't do what was asked.
    # Claiming "All done" would be a success it never earned.
    stopped = win._done_status == "stopped"
    win.bar.setValue(win._total)
    if stopped:
        win.bar.setFormat(QCoreApplication.translate("run", "Stopped"))
    elif ok:
        win.bar.setFormat(QCoreApplication.translate("run", "Finished"))
    else:
        win.bar.setFormat(QCoreApplication.translate("run", "Finished with errors"))
    if stopped:
        win.status.setText(QCoreApplication.translate(
            "run",
            "Stopped — anything already installed is still installed."))
        win._announce(win.status.text())
        win.save_last_run("stopped")
        win.refresh_last_run()
        if win._hints:
            banners._show_warning(win, win._hints[0], _first_hint_command(win))
        if win._sys_changed and win._snapshot:
            win.rollback_btn.setVisible(True)
        return

    n = win._installed_count
    count = int(n) if n.isdecimal() else 0
    # A source set aside this run is named in the summary. Without it a run that
    # skipped an entire software source still ended "All done", which claims more
    # than the run earned (ONEUP-0025 promises the skip reaches the summary).
    aside = ""
    if win._skipped_repos:
        aside = i18n.counted("sources-set-aside", len(win._skipped_repos)).format(
            names=i18n.join_names(win._skipped_repos))
    # Whole sentences, one per outcome — never a fragment dropped into a frame.
    if not ok:
        summary = QCoreApplication.translate(
            "run", "Finished — some steps had errors (see details).")
    elif count:
        summary = QCoreApplication.translate("run", "All done — {installed}.").format(
            installed=i18n.counted("updates-installed", count))
    elif win._sys_changed:
        summary = QCoreApplication.translate("run", "All done — updates installed.")
    elif "system" in win.selected_steps():
        summary = QCoreApplication.translate("run", "All done — already up to date.")
    else:
        summary = QCoreApplication.translate("run", "All done — finished.")
    win.status.setText(QCoreApplication.translate(
        "run", "{summary}{aside}", "the run's summary, then any sources set aside").format(
            summary=summary, aside=aside))
    # Announced here, where the summary is set. Any warning banner below
    # announces afterwards and so supersedes this (announcements are Polite
    # priority, and the warning is the message that matters more).
    win._announce(win.status.text())
    win.save_last_run("OK" if ok else "errors")

    # Reboot vs the lighter "just restart these services" path.
    #
    # The service list is split HERE as well as in the button (ONEUP-0115). A unit
    # this window will never restart (ONEUP-0111) is not advice the user can act on
    # from the services banner, so where the honest answer is a reboot the reboot is
    # what gets offered — rather than a banner whose button opens a dialog naming
    # what it refuses to touch. Both halves can be true at once, and then both
    # banners show: restart the safe ones now, reboot for the rest.
    svc_safe, svc_risky = banners._split_session_critical(banners._service_units(win))
    if win._reboot:
        if win._reboot_reason:
            # Name what triggered it, e.g. "A new kernel and your NVIDIA graphics
            # driver were installed — restart …". The reason arrives already in its
            # sentence-start form: deriving one with a case change would break every
            # language without case (ONEUP-0032 §4.5).
            r = win._reboot_reason
            # The fallback (ONEUP-0108 §4.3) is already a whole sentence.
            win.reboot_label.setText(
                QCoreApplication.translate(
                    "run", "⚠  {reason} Restart so everything uses the latest version.")
                .format(reason=r) if r.endswith(".") else
                QCoreApplication.translate(
                    "run", "⚠  {reason} — restart so everything uses the latest version.")
                .format(reason=r))
        elif count:
            win.reboot_label.setText(i18n.counted("reboot-updates-installed", count))
        else:
            win.reboot_label.setText(
                QCoreApplication.translate(
                    "run",
                    "⚠  Updates were installed — a restart is recommended so "
                    "everything uses the latest libraries."))
        win.reboot_banner.setVisible(True)
    else:
        # The unit names are listed space-separated, as they always were; the
        # separator is still the language's to choose.
        units_sep = QCoreApplication.translate(
            "run", " ", "separator between service names in a button's tooltip")
        if svc_safe:
            win.services_label.setText(i18n.counted(
                "services-restart" if svc_risky else "services-restart-no-reboot",
                len(svc_safe)))
            win.services_btn.setToolTip(units_sep.join(svc_safe))
            win.services_banner.setVisible(True)
        if svc_risky:
            win.reboot_label.setText(i18n.counted("services-session", len(svc_risky)))
            win.restart_btn.setToolTip(units_sep.join(svc_risky))
            win.reboot_banner.setVisible(True)

    # Rollback offer once the system actually changed.
    if win._sys_changed and win._snapshot:
        win.rollback_btn.setVisible(True)

    # Surface the first plain-English failure hint, if any (with a Copy button
    # when it carries a command the app couldn't run for you) — OR, when a
    # remedy is armed with no accompanying hint (a corrupt-metadata source
    # failure arms @@REMEDY@@|skip-repo with no @@HINT@@), a GUI-built
    # fallback naming the culprit(s) so the skip/import action is never a
    # dead end behind an invisible banner.
    if win._hints or win._remedy_skips or win._remedy_keys or win._remedy_unknown:
        if win._remedy_unknown:
            between = QCoreApplication.translate(
                "run", "  ", "separator between whole sentences in one banner")
            sentences = [*win._hints[:1],
                         *(markers.fallback_remedy(c) for c in win._remedy_unknown)]
            banners._show_warning(win, between.join(sentences), _first_hint_command(win))
        elif win._hints:
            banners._show_warning(win, win._hints[0], _first_hint_command(win))
        elif win._remedy_skips:
            names = i18n.join_names(banners._repo_display_name(a) for a in win._remedy_skips)
            if len(win._remedy_skips) == 1:
                banners._show_warning(win,
                    QCoreApplication.translate(
                        "run",
                        "{names} is failing — skip it and update everything else, or "
                        "check the log.").format(names=names))
            else:
                banners._show_warning(win,
                    QCoreApplication.translate(
                        "run",
                        "These sources are failing: {names} — skip them and update "
                        "everything else, or check the log.").format(names=names))
        else:
            banners._show_warning(win, QCoreApplication.translate(
                "run",
                "A repository signing key is out of date."))
        # When a one-click remedy is available, the banner button offers it
        # (behind a warned confirmation for the key import) rather than just
        # showing the log. A skip remedy takes the primary button; when a
        # key-import remedy is ALSO armed (an expired key: both a skip and a
        # real fix exist), it gets a genuine second button rather than being
        # dropped, since a single button can't offer two actions.
        both_armed = bool(win._remedy_skips) and win._remedy_keys
        if win._remedy_skips:
            if len(win._remedy_skips) == 1:
                win.warn_btn.setText(
                    QCoreApplication.translate("run", "Skip {source} & update the rest").format(
                        source=banners._repo_display_name(win._remedy_skips[0])))
            else:
                win.warn_btn.setText(
                    QCoreApplication.translate("run", "Skip {count} sources & update the rest")
                    .format(count=len(win._remedy_skips)))
        elif win._remedy_keys:
            win.warn_btn.setText(QCoreApplication.translate("run", "Import signing key & retry"))
        if both_armed:
            win.warn_btn2.setText(QCoreApplication.translate("run", "Import signing key & retry"))
            win.warn_btn2.setVisible(True)

    # Retry now lives INSIDE the warning banner (ONEUP-0064), so the banner's
    # rule has to match Retry's own. It was raised above only for a failure
    # carrying a hint or an armed remedy, while Retry was revealed for any failed
    # step — so a run whose steps failed with neither showed Retry with the banner
    # hidden, and reparenting it unchanged would have left no way to retry at all.
    # A stopped run is untouched: the `if stopped:` branch returns before here.
    if win._failed_steps:
        if not win.warn_banner.isVisible():
            banners._show_warning(win, QCoreApplication.translate(
                "run",
                "Some steps did not finish. Open the log to see what went wrong, "
                "or retry them."))
        win.retry_btn.setVisible(True)
    if not ok:
        win._show_log(True)

    # Tell the user a run they walked away from has finished.
    _notify_when_away(win,
        summary if ok
        else QCoreApplication.translate("run", "Finished — some steps had errors."),
        urgency="normal" if ok else "critical")

    # Keep the ambient tray icon honest: a clean run just installed updates.
    if ok:
        tray._apply_tray_total(win, 0)


