"""Turn zypper's text into values. Pure functions: no I/O, no privilege.

`docs/specs/ONEUP-0054-python-engine.md` §4.2 places this module, and §4.3.4
says why it is a module at all: as pure functions these become table-testable in
isolation, which is what `tests/parsers-test.py` does. Importing them must never
drag in the code that calls `sudo` — so nothing here imports a sibling.

Every function reproduces a construct in `update_system.sh` exactly, including
where two of them disagree. Where the Bash rounds, this rounds the same way.
"""

from __future__ import annotations

import re

# `to_bytes`' unit table. These four and no others: `progress_total_bytes` below
# admits a `[KMG]?i?B` unit, so `KB` reaches here and must come back 0 rather
# than 1000 — an invented figure is worse than a missing one.
_UNITS = {"B": 1, "KiB": 1024, "MiB": 1048576, "GiB": 1073741824}

_WHOLE = re.compile(r"[0-9]+")
_DIGIT = re.compile(r"[0-9]")


def to_bytes(number: str, unit: str) -> int:
    """`to_bytes`: "31.0", "KiB" -> 31744. Unparsable or unknown unit -> 0.

    Integer arithmetic, because the Bash has no floats. It keeps ONE fractional
    digit and computes `(whole * 10 + frac) * mult / 10` with truncating
    division; `float(number) * mult` rounds differently on some inputs, and this
    number reaches the window inside `@@PROGRESS@@`.
    """
    whole, _, rest = number.partition(".")
    frac = rest[:1] if "." in number else "0"
    if not _WHOLE.fullmatch(whole) or not _DIGIT.fullmatch(frac):
        return 0
    mult = _UNITS.get(unit)
    if mult is None:
        return 0
    return (int(whole) * 10 + int(frac)) * mult // 10


# --- the two download-size wordings, which are TWO parsers on purpose ---------
#
# zypper renamed this line and OneUp supports both distros:
#   older (Leap):         "Overall download size: 1.3 GiB. Already cached: 0 B."
#   current (TW 1.14.98)  "Package download size:   371.4 MiB"
# A parse for the first alone silently reported "nothing to fetch" on a
# 137-package upgrade (ONEUP-0035).
#
# The two call sites in `update_system.sh` do NOT accept the same text, and
# collapsing them would change what `@@SIZE@@` carries. Measured:
#   "Overall download size: 1.3 TiB."  -> run_size parses it, the filter does not
#   "Package download size:371.4MiB"   -> the filter parses it, run_size does not
# `run_size` wants the figure as TEXT (it is quoted verbatim in the marker);
# the progress filter wants BYTES.

# `run_size`'s sed: a greedy leading `.*`, so on a line with two matches it takes
# the last; exactly one space before the unit; any alphabetic unit.
_SIZE_TEXT = re.compile(r".*(?:Overall|Package) download size:[ \t]*([0-9.]+ [A-Za-z]+)")

# `progress_filter`'s regex: anchored at line start, any spacing, and only a
# unit `to_bytes` knows the shape of.
_SIZE_BYTES = re.compile(r"^(?:Overall|Package) download size: *([0-9.]+) *([KMG]?i?B)")


def download_size(text: str) -> str | None:
    """`run_size`'s parse: the first line carrying a figure, as text.

    Returns e.g. "371.4 MiB" — the exact string `@@SIZE@@|system|…` reports.
    None when no line matches, which is the "nothing to fetch" case the caller
    must tell apart from a failed run.
    """
    for line in text.splitlines():
        found = _SIZE_TEXT.match(line)
        if found:
            return found.group(1)
    return None


def progress_total_bytes(line: str) -> int | None:
    """`progress_filter`'s parse: the transaction total, in bytes.

    This is what lets the window show "19 MB of 86 MB" and a rate — the two
    numbers that tell a slow download from a stalled one.
    """
    found = _SIZE_BYTES.match(line)
    if not found:
        return None
    return to_bytes(found.group(1), found.group(2))


# --- the progress wordings ---------------------------------------------------
#
# zypper's three phases, verbatim (LC_ALL=C is pinned on the transaction, so
# these are stable on a non-English desktop too):
#
#   Preloading: libglfw3-3.4-67.34.x86_64.rpm [done]
#   Retrieving: cpupower-lang-7.1.4-17.noarch (devel-tools) (1/77),  31.0 KiB
#   ( 1/77) Installing: cpupower-lang-7.1.4-17.noarch [...done]
#
# Only the last two carry a counter. The preload — the parallel prefetch, and
# the phase a big download actually spends its time in — has none, which is why
# it reports a total of 0 meaning "unknown".

_RETRIEVED_BYTES = re.compile(r", *([0-9.]+) *([KMG]?i?B)")


def retrieving_fraction(line: str) -> str:
    """The counter out of a `Retrieving:` line — the LAST `(…)` on it.

    The package name can carry parentheses of its own, so the counter is taken
    from the right: `…(devel-tools) (1/77),  31.0 KiB` -> "1/77".
    """
    return line.rpartition("(")[2].partition(")")[0]


def retrieving_bytes(line: str) -> int:
    """That package's own size, in bytes. 0 when the line carries none.

    Summing these is the only running byte count available — zypper reports no
    total of its own during the fetch.
    """
    found = _RETRIEVED_BYTES.search(line)
    if not found:
        return 0
    return to_bytes(found.group(1), found.group(2))


def install_fraction(line: str) -> str:
    """The counter out of an `( 1/77) Installing:` line — the FIRST `(…)`."""
    return line.partition("(")[2].partition(")")[0]


# --- `zypper lr -u` output ---------------------------------------------------


def enabled_aliases(text: str) -> list[str]:
    """The alias of each ENABLED repository, from zypper's own table.

    Reproduces the awk in `enabled_repo_aliases`: fields trimmed, a row counted
    only when its first column is a number and its Enabled column starts with
    `y` or `Y`. The table is the only place the repository list comes from, so
    an unexpected format yields an empty list rather than a wrong one — and
    `refresh_repos` treats empty as "fall back to one bulk refresh".
    """
    aliases = []
    for line in text.splitlines():
        fields = [f.strip() for f in line.split("|")]
        if len(fields) < 4:
            continue
        if _WHOLE.fullmatch(fields[0]) and fields[3][:1].lower() == "y":
            aliases.append(fields[1])
    return aliases


# --- the lock file's text ----------------------------------------------------


def lock_pid(text: str) -> int | None:
    """The pid out of `/run/zypp.pid`, or None if it does not read as one.

    `read -r pid _` takes the first whitespace-separated word of the first line;
    the shape test is what stops a corrupt file reaching a `/proc` lookup.
    """
    first = text.split("\n", 1)[0].split()
    if not first or not _WHOLE.fullmatch(first[0]):
        return None
    return int(first[0])


# --- the reboot reason -------------------------------------------------------
#
# The optional reason field of `@@REBOOT@@` (`docs/reference/marker-protocol.md`
# §4.8). Cosmetic in itself, but it is the marker INV-1 governs, and losing the
# reason turns a correct verdict into an unexplained one.

_KERNEL = re.compile(r"\bkernel-(default|preempt|rt|64kb|lpae|kvmsmall|vanilla)\b")
_NVIDIA = re.compile(r"\bnvidia", re.IGNORECASE)
_GRAPHICS = re.compile(r"\b(Mesa|xf86-video-|libvulkan|libdrm)")
_MODULE = re.compile(r"(-kmp-|\bdkms\b)")
# The module filter's own nvidia test is `grep -vi nvidia` — no word boundary,
# unlike the category test above it. Kept as two patterns because the Bash uses
# two, and a line reading "xnvidia" falls on different sides of them.
_NVIDIA_ANYWHERE = re.compile(r"nvidia", re.IGNORECASE)


def reboot_reason(log: str) -> str:
    """Why a reboot is advised, in the user's words. "" when nothing qualifies.

    Reading the log is `steps.py`'s (§4.2); this turns the lines it found into
    the phrase.
    """
    parts = []
    if _KERNEL.search(log):
        parts.append("a new kernel")
    if _NVIDIA.search(log):
        parts.append("your NVIDIA graphics driver")
    elif _GRAPHICS.search(log):
        parts.append("your graphics driver")
    # DKMS / kernel-module packages OTHER than the NVIDIA one already named.
    if any(_MODULE.search(line) and not _NVIDIA_ANYWHERE.search(line)
           for line in log.splitlines()):
        parts.append("kernel driver modules")
    if not parts:
        return ""
    verb = "was" if len(parts) == 1 else "were"
    # At most three categories, so an explicit join is clearest — same shape as
    # the Bash `case ${#parts[@]}`.
    if len(parts) == 1:
        phrase = parts[0]
    elif len(parts) == 2:
        phrase = f"{parts[0]} and {parts[1]}"
    else:
        phrase = f"{parts[0]}, {parts[1]}, and {parts[2]}"
    return f"{phrase} {verb} installed"
