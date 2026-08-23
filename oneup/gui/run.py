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

import shutil
import subprocess
import time
from datetime import datetime
from functools import partial

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QMessageBox

from .. import APP_ID, APP_NAME
from . import banners, markers, paths, tray
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


def request_stop(win):
    """Ask the engine to stop at its next safe point by creating the file it watches.
    Not a signal: signalling mid-transaction would either leave rpm half-applied or
    orphan a zypper that carries on anyway (ONEUP-0047)."""
    try:
        paths.RUN_STATE.parent.mkdir(parents=True, exist_ok=True)
        paths.STOP_REQUEST.touch()
    except OSError as exc:
        QMessageBox.warning(win, "Stop", f"Could not ask the update to stop:\n{exc}")
        return
    win.stop_btn.setEnabled(False)
    win.stop_btn.setText("Stopping…")
    win.status.setText("Stopping after the current step — nothing new will start…")
    win._announce("Stopping after the current step.")


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
        if _adopt_held_engine(win):
            return
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
    if not first.isdigit() or int(first) != proc.processId():
        return False
    steps = win.selected_steps()
    # The steps travel WITH the go-ahead rather than being fixed at preview time: the
    # preview is started for `system` alone, but the run uses whatever is selected when
    # Update is pressed, which may have changed in between (§4.6).
    try:
        paths.GO_REQUEST.parent.mkdir(parents=True, exist_ok=True)
        paths.GO_REQUEST.write_text(",".join(steps) + "\n")
    except OSError as exc:
        QMessageBox.warning(win, "Update", f"Could not start the update:\n{exc}")
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
    win.bar.setFormat("Starting…")
    win.status.setText("Starting the update…")
    win.set_controls_enabled(False)
    proc.readyReadStandardOutput.disconnect()
    proc.finished.disconnect()
    proc.readyReadStandardOutput.connect(partial(on_output, win))
    proc.finished.connect(partial(on_finished, win))
    proc.errorOccurred.connect(partial(on_error, win))
    win.proc = proc
    win._size_proc = None
    return True


def _wait_for_hold(win):
    """The middle row of §4.5's table: a preview is running but has not reached its hold
    yet, so wait for it rather than starting a second engine (which is the defect) or
    writing a go-ahead the engine would discard as stale."""
    if getattr(win, "_hold_wait", None) is None:
        win._hold_wait = QTimer(win)
        win._hold_wait.setInterval(HOLD_WAIT_POLL_MS)
        win._hold_wait.timeout.connect(partial(_hold_wait_tick, win))
    win.status.setText("Working out the download size first — the update starts "
                       "as soon as that finishes…")
    win._announce("Working out the download size first. The update will start "
                  "as soon as that finishes.")
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
    if _adopt_held_engine(win):
        win._hold_wait.stop()


def retry_failed(win):
    if win._failed_steps:
        _launch(win, list(win._failed_steps), check=False)


def request_size(win, key: str):
    """Fetch the exact download size for a step on demand (system only). Runs
    the engine's --size mode, which authenticates and does a `zypper dup
    --dry-run`, so it stays out of the password-free --check path."""
    if key != "system" or not paths.ENGINE.exists():
        return
    row = win.rows.get(key)
    if not row:
        return
    proc = getattr(win, "_size_proc", None)
    if proc is not None and proc.state() != QProcess.NotRunning:
        return  # a fetch is already in flight
    row.size_pending()
    # The button's "up to a minute" label is invisible to a screen reader, so
    # say it out loud too — otherwise a blind user gets silence for the wait.
    win._announce("Working out the download size — this can take up to a minute.",
                   row.size_btn)
    win._size_buf = ""
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    # Named as a RUN log, not `<stamp>.size.log`, because --hold means this preview may
    # become the run. The engine writes its --log= value verbatim into `run.state` for
    # run-following, so a run that logged to a `.size.log` would be followed at a path
    # `_log_path` does not name and "Open log file" would show the wrong file. Naming it
    # correctly up front costs nothing and needs no extra payload in `go.request`
    # (ONEUP-0044 §4.5). Held here rather than in `_log_path`, which must keep pointing
    # at the last real run until this preview actually becomes one.
    size_log = paths.LOG_DIR / f"{stamp}.log"
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
    p.start("bash", [str(paths.ENGINE), f"--size={key}", "--hold", f"--log={size_log}"])


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
                    row.set_size_result(f"↓ {parts[1]} to download")
        elif line.startswith("@@HINT@@|"):
            # The size probe failed (busy package manager, cancelled password
            # prompt). Say why in the log — the link re-arms itself for a retry
            # in _on_size_finished, but a silent re-arm looks like a dead button.
            win.log.appendPlainText(line.split("|", 1)[1])
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
    row = win.rows.get("system")
    if not row or row.has_size():
        return
    # No SIZE marker arrived. Exit 0 = solver found nothing to fetch; non-zero
    # = auth cancelled or an error, so re-arm the link for a retry.
    if exit_code == 0:
        row.set_size_result("Nothing to download")
    else:
        row.size_failed()


def _engine_args(steps: list[str], check: bool = False, import_keys: bool = False,
                  skip_repos: list[str] | None = None) -> list[str]:
    """Build the engine argv for the stable flags (steps/check/import_keys), plus
    one --skip-repo=<alias> per entry in skip_repos. `_launch` inserts --log=<path>
    into the result at call time — this helper doesn't know about the log path."""
    args = [str(paths.ENGINE), f"--steps={','.join(steps)}"]
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
    win.warn_btn.setText("Show details")
    win.warn_btn.setEnabled(True)
    win._hint_command = ""
    win._remedy_keys = False
    win._remedy_skips = []
    win._run_active = not check   # a real run guards the standalone thin action
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
        QMessageBox.information(win, "Nothing selected",
                                "Turn on at least one task first.")
        return
    if not paths.ENGINE.exists():
        QMessageBox.critical(win, "Engine missing",
                             f"Could not find the update script at:\n{paths.ENGINE}")
        return
    # Never start a second engine while a download-size preview is in flight. Doing so
    # IS the ONEUP-0044 defect: with no terminal sudo keys its cached credential to the
    # parent process id, so two engines are two timestamp records and two password
    # dialogs. `start_run` routes to the held engine instead of coming here; this guard
    # covers the other ways in — Check for updates, and Retry failed steps.
    size_proc = getattr(win, "_size_proc", None)
    if size_proc is not None and size_proc.state() != QProcess.NotRunning:
        QMessageBox.information(
            win, "Just a moment",
            "OneUp is working out the download size.\n\n"
            "That takes up to a minute. Try again once it has finished.")
        return

    _reset_for_run(win, steps, check)

    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    win._log_path = paths.LOG_DIR / (f"{stamp}.check.log" if check else f"{stamp}.log")

    if check:
        win.bar.setRange(0, 0)  # indeterminate
        win.bar.setFormat("Checking…")
        win.status.setText("Checking for available updates…")
    else:
        win.bar.setRange(0, win._total)
        win.bar.setValue(0)
        win.bar.setFormat("Starting…")
        win.status.setText("Authenticating… (approve the password popup)")
    win.set_controls_enabled(False)

    args = _engine_args(steps, check, import_keys, skip_repos)
    args.insert(2, f"--log={win._log_path}")  # after --steps, before --check/etc.
    win.proc = QProcess(win)
    win.proc.setProcessChannelMode(QProcess.MergedChannels)
    win.proc.readyReadStandardOutput.connect(partial(on_output, win))
    win.proc.finished.connect(partial(on_finished, win))
    win.proc.errorOccurred.connect(partial(on_error, win))
    win.proc.start("bash", args)


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
    if not win._run_active:
        return
    now = time.monotonic()
    bits = []
    if win._activity_what and win._activity_since:
        waited = markers._format_duration(int(now - win._activity_since))
        bits.append(f"{win._activity_what} — {waited}")
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
    if stalled:
        bits.append(f"nothing received for {markers._format_duration(quiet)}"
                    " — the server may have stalled. Stopping now is safe.")
    elif bits:
        bits.append("still working")
    _set_activity(win, " · ".join(bits))
    # Announced on the transition only — a live region that speaks every tick would
    # bury the rest of the run, but going quiet for minutes is genuinely news.
    if stalled != win._activity_stalled:
        win._activity_stalled = stalled
        if stalled:
            win._announce("No response from the server. Stopping now is safe.")


def handle_marker(win, line: str):
    split = markers.split_marker(line)
    if split is None:
        # A line that starts with @@ but isn't a real marker (e.g. a diff hunk
        # header "@@ -1,4 +1,4 @@") is ordinary output — log it, don't drop it.
        win.log.appendPlainText(line)
        return
    tag, parts, rest = split
    if tag == "STEP_BEGIN":
        # Guard the fixed 4-field unpack + int(): the engine's output is merged
        # stdout+stderr, so a marker line can be spliced by interleaved text. A
        # malformed STEP_BEGIN must never throw out of the QProcess read slot —
        # that would abort parsing and drop the run's later markers.
        if len(parts) < 4 or not parts[1].isdigit():
            return
        _key, index, total, label = parts[0], parts[1], parts[2], parts[3]
        win.status.setText(f"{label}…")
        # Kept so @@PROGRESS@@ can rebuild the bar's caption without re-deriving
        # the step's label and position from a marker it doesn't carry.
        win._step_caption = f"{label}  (step {index} of {total})"
        win._progress_phase = ""
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
        win._announce(f"{label}, step {index} of {total}")
    elif tag == "STEP_END":
        # Clamp: a duplicate/orphaned STEP_END (markers can be spliced) must not
        # push the bar past the run's total step count.
        win.bar.setValue(min(win.bar.value() + 1, win._total))
        key = parts[0]
        status = parts[1] if len(parts) >= 2 else ""
        detail = parts[2] if len(parts) >= 3 else ""
        # Badge the task row with what actually happened (mirrors the "N available"
        # badge --check shows, but for a real run: "3 installed", "Up to date", …).
        row = win.rows.get(key)
        if row:
            badge = markers._step_badge(status, detail)
            row.set_badge(badge)
            # The outcome, spoken once. A later TIMING/FREED marker refines the
            # badge but is NOT re-announced — it stays reachable by Tab via the
            # switch's accessible description. Two utterances per step is the budget.
            win._announce(f"{row.title}: {badge}", row.badge)
        if status == "fail":
            win._failed_steps.append(key)
    elif tag == "TIMING":
        # How long the step took, appended to its row badge ("3 installed · 42s").
        key = parts[0]
        secs = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
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
            row.set_badge(f"Reclaimed {human}")
    elif tag == "CHECK":
        key, count = parts[0], (parts[1] if len(parts) > 1 else "0")
        if key == "TOTAL":
            win._installed_count = count
        else:
            row = win.rows.get(key)
            if row:
                n = int(count) if count.isdigit() else 0
                row.set_badge(f"{n} available" if n > 0 else "up to date")
    elif tag == "CHECK_UNKNOWN":
        # This step couldn't read one of its sources, so its count is a floor,
        # not an answer. Recorded so on_finished can refuse the "up to date"
        # summary — the whole point of the marker (ONEUP-0056).
        reason = parts[1] if len(parts) > 1 else "a source couldn't be read"
        win._unchecked.append(reason)
        row = win.rows.get(parts[0])
        if row:
            # Text, not colour: the badge must read as unknown to everyone.
            row.set_badge("couldn't check")
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
        if parts and parts[0].isdigit():
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
        if len(parts) < 4 or not parts[1].isdigit() or not parts[2].isdigit():
            return
        key, phase = parts[0], parts[3]
        n, total = int(parts[1]), int(parts[2])
        verb = "Downloading" if phase == "download" else "Installing"
        # total 0 = zypper's preload phase, which reports no denominator. Show the
        # honest running tally rather than inventing one.
        detail = f"{verb} {n} of {total} packages" if total else f"{verb} packages — {n} so far"
        win.status.setText(f"{detail}…")
        win.bar.setFormat(f"{win._step_caption} — {detail}"
                           if win._step_caption else f"{detail}…")
        row = win.rows.get(key)
        if row:
            row.set_badge(f"{n}/{total}" if total else str(n))
        # Spoken once per phase, not per package: a screen reader announcing all
        # 141 packages would bury everything else, but silence through the run's
        # longest stretch is exactly what made it look hung.
        announce = phase != win._progress_phase
        win._progress_phase = phase
        # Optional trailing byte fields: how much zypper says has come down, and its
        # total for the transaction. Either may be 0 for "not known" — during the
        # prefetch phase zypper reports no sizes at all, and the liveness line falls
        # back to weighing the package cache. Set the phase FIRST: that fallback is
        # gated on it, so a stale phase would skip the very first measurement.
        if len(parts) > 4 and parts[4].isdigit():
            win._dl_bytes = max(win._dl_bytes, int(parts[4]))
            if len(parts) > 5 and parts[5].isdigit() and int(parts[5]):
                win._dl_total = int(parts[5])
            _tick_activity(win)
        if announce:
            win._announce(f"{verb} packages.")
    elif tag == "REFRESH":
        # Which source is being fetched, and how far through the list (ONEUP-0048).
        # This phase used to be a blank several minutes: zypper reports it as dots
        # with no line ending, so there was nothing for the log pane to draw, and a
        # crawling mirror was indistinguishable from a hung app.
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            return
        n, total, alias = int(parts[0]), int(parts[1]), parts[2]
        detail = f"Checking for updates from {alias} ({n} of {total} sources)"
        win.status.setText(f"{detail}…")
        win.bar.setFormat(f"{win._step_caption} — {detail}"
                           if win._step_caption else f"{detail}…")
        win._activity_what = f"Fetching {alias}"
        win._activity_since = time.monotonic()
        _tick_activity(win)
    elif tag == "SERVICES":
        win._services = rest.strip()
    elif tag == "HINT":
        win._hints.append(rest.strip())
    elif tag == "REPO_SKIPPED":
        # A source was set aside for this run (disabled, upgrade ran, will be
        # re-enabled by the engine on exit — see --skip-repo/--auto-skip-repos).
        if parts:
            alias = parts[0]
            win._skipped_repos.append(alias)
            win.log.appendPlainText(f"  Set aside this run: {alias} (will retry next time)")
    elif tag == "REMEDY":
        # The engine says a one-click fix is available for this run's failure:
        # "import-keys" (a rotated/expired repo signing key) and/or "skip-repo"
        # (a single broken source — offer to set it aside and update the rest).
        # Armed here; the warn banner offers them in on_finished, the key-import
        # one behind a confirmation.
        if parts and parts[0] == "import-keys":
            win._remedy_keys = True
        elif parts and parts[0] == "skip-repo" and len(parts) >= 2:
            win._remedy_skips.append(parts[1])
    elif tag == "REBOOT":
        win._reboot = parts[0] == "yes"
        # Optional field: a plain-English reason naming what makes the reboot
        # matter (a new kernel, graphics driver, …). Absent for a plain reboot.
        win._reboot_reason = parts[1] if len(parts) > 1 else ""
    elif tag == "SNAPSHOTS" and parts and parts[0] == "warn":
        # Pre-flight: a lot of Btrfs restore points have piled up and may be using
        # disk. Offer a one-click thin (snapper's own retention cleanup) via the
        # warn banner. The "thinned|N" variant comes from the dedicated
        # --thin-snapshots process and is read in _on_thin_finished, not here.
        win._snapshot_count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        win._warn_snapshots = True
        win.warn_btn.setText("Thin snapshots…")
        banners._show_warning(win,
            f"{win._snapshot_count} system restore points (snapshots) are stored. "
            "On Tumbleweed these build up with each update and can use a lot of disk "
            "space — you can safely thin the older ones.")
    elif tag in ("DISK", "REPO"):
        # Pre-flight warnings (low disk / duplicate repos). Surface immediately so
        # the advertised warning is visible during the run, not buried in the log.
        if tag == "DISK" and len(parts) >= 3:
            msg = f"Low disk space on {parts[1]} — only {parts[2]} free. Updating may fail."
        elif tag == "REPO":
            # parts: warn|duplicate|<space-joined urls>. Name the culprit(s) and
            # point the banner's button at the repo manager to fix it in-app.
            urls = parts[2].strip() if len(parts) >= 3 else ""
            if urls:
                msg = (f"Duplicate repository URL(s): {urls}. Open Repositories to "
                       "turn off or remove the extra copy.")
            else:
                msg = "Duplicate repository URLs detected — a common cause of update conflicts."
            win._warn_repo_dup = True
            win.warn_btn.setText("Manage repositories…")
        else:
            msg = "Pre-flight warning — see the log for details."
        banners._show_warning(win, msg)
    elif tag == "DONE":
        # The overall result normally comes from the process exit code in
        # on_finished (the two always agree). It is recorded here as well for the
        # one case with no exit code to read: a run started by an earlier OneUp
        # window that this one attached to and is following through its log
        # (_attach_to_running_engine).
        win._done_status = parts[0] if parts else ""


def on_error(win, _err):
    win.status.setText("Could not start the update script.")
    win.bar.setRange(0, 1)
    win.set_controls_enabled(True)
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


def on_finished(win, exit_code: int, _status):
    # Flush any final line the engine emitted without a trailing newline before
    # computing the summary, so a last marker can't be silently dropped.
    if win._buf.strip():
        handle_line(win, win._buf)
    win._buf = ""
    win._run_active = False
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
        win.bar.setFormat("Check complete")
        n = win._installed_count
        total = int(n) if n.isdigit() else 0
        # A count built on sources we couldn't read is a floor, not an answer, so
        # it must never be dressed up as an all-clear — that is the bug this whole
        # marker exists to prevent: the app said "up to date 🎉" while 8 updates
        # were waiting, because a repository it silently skipped held them all
        # (ONEUP-0056). Say what we found AND what we couldn't see.
        if win._unchecked:
            win.status.setText(
                f"{total} update(s) found, but some sources couldn't be checked."
                if total else "Couldn't check for updates — no sources could be read.")
            banners._show_warning(win, win._unchecked[0] if len(win._unchecked) == 1
                               else "  ".join(win._unchecked))
        else:
            win.status.setText(
                f"{total} update(s) available — turn on what you want and hit Run."
                if total else "Everything is up to date. 🎉")
        win._announce(win.status.text())
        _notify_when_away(win,
            f"{total} update(s) available." if total
            else ("Couldn't check for updates." if win._unchecked
                  else "Everything is up to date."))
        tray._apply_tray_total(win, total, uncertain=bool(win._unchecked))
        win._check_mode = False
        return

    # A stopped run is neither: nothing went wrong, but it didn't do what was asked.
    # Claiming "All done" would be a success it never earned.
    stopped = win._done_status == "stopped"
    win.bar.setValue(win._total)
    win.bar.setFormat("Stopped" if stopped else
                       ("Finished" if ok else "Finished with errors"))
    if stopped:
        win.status.setText("Stopped — anything already installed is still installed.")
        win._announce(win.status.text())
        win.save_last_run("stopped")
        win.refresh_last_run()
        if win._hints:
            banners._show_warning(win, win._hints[0])
        if win._sys_changed and win._snapshot:
            win.rollback_btn.setVisible(True)
        return

    n = win._installed_count
    if n and n not in ("", "0"):
        installed = f"{n} update(s) installed"
    elif win._sys_changed:
        installed = "updates installed"
    elif "system" in win.selected_steps():
        installed = "already up to date"
    else:
        installed = "finished"
    win.status.setText(f"All done — {installed}." if ok
                        else "Finished — some steps had errors (see details).")
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
            # driver were installed — restart …". Capitalise the first letter only
            # (str.capitalize() would lower-case "NVIDIA").
            r = win._reboot_reason
            win.reboot_label.setText(
                f"⚠  {r[0].upper()}{r[1:]} — restart so everything uses the latest version.")
        elif n and n not in ("", "0"):
            win.reboot_label.setText(
                f"⚠  {n} update(s) installed — restart so everything uses "
                "the latest libraries.")
        else:
            win.reboot_label.setText(
                "⚠  Updates were installed — a restart is recommended so everything "
                "uses the latest libraries.")
        win.reboot_banner.setVisible(True)
    else:
        if svc_safe:
            n_s = len(svc_safe)
            win.services_label.setText(
                f"{n_s} service(s) should restart to use the new libraries."
                if svc_risky else
                f"No reboot needed — but {n_s} service(s) should restart to use the "
                "new libraries.")
            win.services_btn.setToolTip(" ".join(svc_safe))
            win.services_banner.setVisible(True)
        if svc_risky:
            n_r = len(svc_risky)
            win.reboot_label.setText(
                f"⚠  {n_r} service(s) still using the old libraries are part of your "
                "desktop session — restart the computer to finish.")
            win.restart_btn.setToolTip(" ".join(svc_risky))
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
    if win._hints or win._remedy_skips or win._remedy_keys:
        if win._hints:
            banners._show_warning(win, win._hints[0])
        elif win._remedy_skips:
            names = ", ".join(banners._repo_display_name(a) for a in win._remedy_skips)
            if len(win._remedy_skips) == 1:
                banners._show_warning(win,
                    f"{names} is failing — skip it and update everything else, "
                    "or check the log.")
            else:
                banners._show_warning(win,
                    f"These sources are failing: {names} — skip them and update "
                    "everything else, or check the log.")
        else:
            banners._show_warning(win, "A repository signing key is out of date.")
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
                    f"Skip {banners._repo_display_name(win._remedy_skips[0])} & update the rest")
            else:
                win.warn_btn.setText(
                    f"Skip {len(win._remedy_skips)} sources & update the rest")
        elif win._remedy_keys:
            win.warn_btn.setText("Import signing key & retry")
        if both_armed:
            win.warn_btn2.setText("Import signing key & retry")
            win.warn_btn2.setVisible(True)

    # Retry now lives INSIDE the warning banner (ONEUP-0064), so the banner's
    # rule has to match Retry's own. It was raised above only for a failure
    # carrying a hint or an armed remedy, while Retry was revealed for any failed
    # step — so a run whose steps failed with neither showed Retry with the banner
    # hidden, and reparenting it unchanged would have left no way to retry at all.
    # A stopped run is untouched: the `if stopped:` branch returns before here.
    if win._failed_steps:
        if not win.warn_banner.isVisible():
            banners._show_warning(win, "Some steps did not finish. Open the log to "
                                       "see what went wrong, or retry them.")
        win.retry_btn.setVisible(True)
    if not ok:
        win._show_log(True)

    # Tell the user a run they walked away from has finished.
    _notify_when_away(win,
        f"All done — {installed}." if ok else "Finished — some steps had errors.",
        urgency="normal" if ok else "critical")

    # Keep the ambient tray icon honest: a clean run just installed updates.
    if ok:
        tray._apply_tray_total(win, 0)


