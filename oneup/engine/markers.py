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

# Everything Python treats as a line break. The payload is interpolated straight
# into the output, so any one of these fabricates a second marker line that the
# window then parses as real — the emitter substituted nothing at all before
# ONEUP-0152. Folded to a space rather than dropped, so the text stays readable.
_LINE_BREAKS = str.maketrans(dict.fromkeys("\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029", " "))


def marker(name: str, payload: str = "") -> None:
    """Emit one `@@NAME@@|payload` line — one call, one line, always."""
    print(f"@@{name}@@|{payload.translate(_LINE_BREAKS)}", flush=True)


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


# `\Z`, not `$`: `$` also matches just before a trailing newline, so `$` would
# accept "1/77\n" where the Bash `case` pattern does not — and a pattern that
# accepts more than the Bash blinds the ONEUP-0046 canary (ONEUP-0152).
_FRACTION = re.compile(r"^([0-9]+)/([0-9]+)\Z")


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
    # Emptiness, not truthiness: "0" is a real reading ("nothing has come down
    # yet") and the two byte fields travel together, so a truth test would drop
    # BOTH of them for the whole transaction on any falsy value (ONEUP-0152).
    if got != "":
        payload += f"|{got}|{want or 0}"
    marker("PROGRESS", payload)
    return True
