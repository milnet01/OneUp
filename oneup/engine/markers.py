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
