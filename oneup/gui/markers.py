"""Reading what the engine said, and saying it in English.

`docs/reference/marker-protocol.md` is the contract; this module holds the
splitting of a marker line into its name and fields, and the three formatters
that turn a payload into the words the window shows.
"""
from __future__ import annotations

import re


def split_marker(line: str) -> tuple[str, list[str], str] | None:
    """Split an `@@TAG@@|payload` line into (tag, fields, raw payload).

    None for a line that starts with `@@` but is not a marker: a diff hunk
    header ("@@ -1,4 +1,4 @@") is ordinary output and must be logged rather
    than dropped.
    """
    try:
        tag, rest = line[2:].split("@@|", 1)
    except ValueError:
        return None
    return tag, rest.split("|"), rest


def _step_badge(status: str, detail: str) -> str:
    """A short per-row badge for a finished step, from its @@STEP_END@@ status +
    detail — e.g. '3 installed', 'Up to date', 'Updated', 'Failed', 'Skipped'."""
    if status == "fail":
        return "Failed"
    if status == "skip":
        return "Not installed" if "not installed" in detail.lower() else "Skipped"
    d = detail.lower()
    if any(w in d for w in ("up to date", "already", "nothing")):
        return "Up to date"
    m = re.search(r"\d+", detail)
    if m:
        return f"{m.group()} removed" if "remov" in d else f"{m.group()} installed"
    if any(w in d for w in ("applied", "updated", "update")):
        return "Updated"
    return "Done"

def _format_duration(secs: int) -> str:
    """A compact human duration: '<1s', '42s', '1m 5s'."""
    if secs < 1:
        return "<1s"
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m {secs % 60}s"

def _format_size(n: int) -> str:
    """A compact human size: '900 B', '512 KB', '41 MB', '1.4 GB'."""
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f} GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.0f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.0f} KB"
    return f"{n} B"
