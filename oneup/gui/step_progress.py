"""A step's progress, in two halves: downloading, then installing (ONEUP-0239 §4.1.1).

One value per step, from 0 to `FULL`: the first half for the download, the second
for the install. It lives on the window, in `win.step_progress`, and three places
show it — the step's own bar, the window's bar while that step runs, and the step's
badge — so the three can never disagree.

The value never moves backwards within a step. zypper's commit pass can report a
download line after the install began, and a bar that slid back would read as a
fault. `None` means busy: the step runs, but nothing yet says how far.

Nothing here imports the window module (`docs/specs/ONEUP-0034-gui-modules.md`
§4.3 rule 2); the window is handed in as `win`.
"""
from __future__ import annotations

import shiboken6
from PySide6.QtCore import QCoreApplication

from . import i18n, steps

FULL = 1000
HALF = FULL // 2


def reset(win) -> None:
    win.step_progress = {}
    win.waiting = set()


def wait(win, keys: list[str]) -> None:
    """A run's selected steps say Waiting until they start. Only a run's: a check
    keeps the badges it has always had."""
    word = QCoreApplication.translate("run", "Waiting")
    win.waiting = set(keys)
    for key in keys:
        row = win.rows.get(key)
        if row:
            row.set_badge(word)


def stop_waiting(win) -> None:
    """The run is over: a step it never reached is not waiting for anything."""
    for key in win.waiting:
        row = win.rows.get(key)
        if row:
            row.clear_badge()
    win.waiting = set()


def begin(win, key: str) -> None:
    """A step has started: busy until a PROGRESS line says how far."""
    win.waiting.discard(key)
    win.step_progress[key] = None
    _show(win, key, "")


def end(win, key: str) -> None:
    win.waiting.discard(key)
    win.step_progress[key] = FULL
    _show(win, key, "")


def download(win, key: str, got: int, bytes_total: int, done: int, total: int) -> None:
    """The download half, from the byte figure when the total is known, else from
    the package count, else busy."""
    if bytes_total:
        value = HALF * min(got, bytes_total) // bytes_total
    elif total:
        value = HALF * min(done, total) // total
    else:
        value = None
    _set(win, key, value, "download")


def install(win, key: str, done: int, total: int, has_bytes: bool) -> None:
    """Any install line fills the download half, so packages already in the cache
    skip it. Only an install line with a total and no byte fields — not a
    `Preloading:` or `Retrieving:` line of the commit pass — moves past it."""
    value = HALF
    if total and not has_bytes:
        value = HALF + HALF * min(done, total) // total
    _set(win, key, value, "install")


def _set(win, key: str, value: int | None, phase: str) -> None:
    old = win.step_progress.get(key)
    if old is not None:
        value = old if value is None else max(old, value)
    win.step_progress[key] = value
    _show(win, key, phase)


def half_of(win, key: str, phase: str) -> str:
    """The phase the window's words name: a download line once the value has passed
    the halfway mark still reads as installing, because the bar cannot go back and a
    word that disagreed with it would read as a fault (§4.1.1)."""
    value = win.step_progress.get(key)
    return "install" if phase == "download" and value is not None and value > HALF else phase


def shown_phase(win) -> str:
    """The running step's phase, as `half_of` words it."""
    return half_of(win, win.current_step, win._progress_phase)


def _show(win, key: str, phase: str) -> None:
    phase = half_of(win, key, phase)
    value = win.step_progress.get(key)
    row = win.rows.get(key)
    if row:
        if value is None:
            row.progress_busy()
        else:
            row.set_progress(value, FULL)
        if phase or value is None:
            row.set_badge(badge(key, phase, value))
    if key == win.current_step or value == FULL:
        # The window's bar follows the running step, and is full between steps.
        if value is None:
            win.bar.setRange(0, 0)
        else:
            win.bar.setRange(0, FULL)
            win.bar.setValue(value)
    # Spotlight's panel reads the same value, and the figures set beside it.
    host = getattr(win, "host", None)
    if host is not None and shiboken6.isValid(host):
        host.show_progress()


def badge(key: str, phase: str, value: int | None) -> str:
    """"Downloading · 35%" — the phase word and the whole step's percentage, or the
    phase word alone while the step is busy. A step with no phase yet says what it
    is doing, in its own words."""
    if phase == "download":
        word = QCoreApplication.translate("run", "Downloading")
    elif phase == "install":
        word = QCoreApplication.translate("run", "Installing")
    else:
        phrasing = steps.IN_PROGRESS.get(key)
        word = QCoreApplication.translate("steps", phrasing) if phrasing else key
    if value is None:
        return word
    return QCoreApplication.translate("run", "{phase} · {percent}%").format(
        phase=word, percent=round(value * 100 / FULL))


def time_left(win) -> str:
    """The system step's time left while it downloads (ONEUP-0239 §4.1.2): what the
    byte figure still lacks of `bytes_total`, over `run._tick_activity`'s rate — or ""
    while any of the three is missing, and in the install half, which has no size to
    time against."""
    if (win.current_step != "system" or shown_phase(win) != "download"
            or not win._dl_total or not win._dl_rate):
        return ""
    left = win._dl_total - min(win._dl_got, win._dl_total)
    return estimate(left / win._dl_rate) if left > 0 else ""


def estimate(secs: float) -> str:
    """Seconds worded as the estimate they are: to ten seconds under a minute, to the
    minute under an hour, then to the hour — "about 40 s left", "about 3 min left"."""
    tens = max(10, round(secs / 10) * 10)
    if tens < 60:
        return i18n.counted("left-seconds", tens)
    minutes = round(secs / 60)
    if minutes < 60:
        return i18n.counted("left-minutes", minutes)
    return i18n.counted("left-hours", round(secs / 3600))
