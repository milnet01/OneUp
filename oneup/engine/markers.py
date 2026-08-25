"""Every marker the engine emits, in one place.

`docs/reference/marker-protocol.md` is the contract; this module is its only
emitter, so a marker cannot be spelled two ways in two files.

Flushed on every call, deliberately. The window reads the engine's stdout line
by line through `QProcess`, and Python block-buffers a pipe: without the flush a
marker arrives when the buffer fills or the process exits, whichever comes
first, and a running engine looks silent. A one-shot script hides this — CPython
flushes at interpreter shutdown — so it is the long run that breaks.
"""

from __future__ import annotations

import re
import sys


def marker(name: str, payload: str = "") -> None:
    """Emit one `@@NAME@@|payload` line."""
    print(f"@@{name}@@|{payload}", flush=True)


def hint(text: str) -> None:
    """A plain-English failure hint for the user."""
    marker("HINT", text)


def out(text: str = "") -> None:
    """Ordinary console output, flushed like a marker so ordering is preserved."""
    print(text, flush=True)


def err(text: str) -> None:
    """Console output on stderr."""
    print(text, file=sys.stderr, flush=True)


def emit_check(key: str, count: int, label: str, unreadable: str = "") -> None:
    """One step's check result — the reason first, never a confident zero.

    A bare `CHECK|key|0` when a source could not be read is the ONEUP-0056 bug:
    "I couldn't look" rendered as "you're up to date". A non-zero count still
    ships, because knowing about 7 updates beats knowing about none while a
    repository is broken.
    """
    if unreadable:
        marker("CHECK_UNKNOWN", f"{key}|{unreadable}")
    if not unreadable or count > 0:
        marker("CHECK", f"{key}|{count}|{label}")


_FRACTION = re.compile(r"^([0-9]+)/([0-9]+)$")


def emit_progress(step: str, frac: str, phase: str,
                  got: str = "", want: str = "") -> bool:
    """Live per-package progress. False when there was no counter to parse.

    The caller needs to tell *emitted* from *skipped*: that distinction is the
    whole input to the ONEUP-0046 stale-parser canary, which reports a
    transaction that installed packages while no progress line was recognised.

    `frac` arrives already extracted — the filter strips zypper's parentheses
    before calling — so only spaces are removed here. Do NOT widen the pattern
    to swallow a parenthesis: it would also accept an unterminated `( 1/77`,
    and the canary loses the only signal it has.

    The two byte fields are optional. Only the download phase can count them,
    and only once zypper has printed a size; a `want` of 0 means "not known
    yet".
    """
    hit = _FRACTION.match(frac.replace(" ", ""))
    if not hit:
        return False
    payload = f"{step}|{hit.group(1)}|{hit.group(2)}|{phase}"
    if got:
        payload += f"|{got}|{want or 0}"
    marker("PROGRESS", payload)
    return True
