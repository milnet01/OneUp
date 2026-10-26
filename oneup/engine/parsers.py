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
import xml.etree.ElementTree as ET
from typing import NamedTuple

# `to_bytes`' unit table. These four and no others: `progress_total_bytes` below
# admits a `[KMG]?i?B` unit, so `KB` reaches here and must come back 0 rather
# than 1000 — an invented figure is worse than a missing one.
_UNITS = {"B": 1, "KiB": 1024, "MiB": 1048576, "GiB": 1073741824}

_WHOLE = re.compile(r"[0-9]+")


def to_bytes(number: str, unit: str) -> int:
    """`to_bytes`: "31.0", "KiB" -> 31744. Unparsable or unknown unit -> 0.

    Integer arithmetic over EVERY fractional digit, truncating only the final
    byte: `float(number) * mult` rounds differently on some inputs, and this number
    reaches the window inside `@@PROGRESS@@`. The Bash engine keeps one digit, which
    read zypper's "1.75 GiB" as 1.7 GiB (ONEUP-0335).
    """
    whole, dot, frac = number.partition(".")
    if not dot:
        frac = "0"
    if not _WHOLE.fullmatch(whole) or not _WHOLE.fullmatch(frac):
        return 0
    mult = _UNITS.get(unit)
    if mult is None:
        return 0
    scale = 10 ** len(frac)
    return (int(whole) * scale + int(frac)) * mult // scale


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

# With part of the transaction cached, current zypper puts no number on that line.
# It prints a table instead, and the figure is the first column of the "already in
# cache" row: the bytes still to fetch (zypper src/Summary.cc, ONEUP-0223).
#   Package download size:
#                   |     105.7 MiB  overall package size
#         99.2 MiB  |  -    6.4 MiB  already in cache
# `run_size`'s second sed expression; [[:space:]] spelled out so \r counts and the
# Unicode spaces do not, as in the Bash.
_SIZE_CACHED_TEXT = re.compile(r"[ \t\r\f\v]*([0-9.]+ [A-Za-z]+)[ \t\r\f\v]*\|.*already in cache")
# `progress_filter`'s case arm: a line holding a "|" and ENDING "already in cache"
# (so `Preloading: … [already in cache]` never reaches it), then this regex.
_SIZE_CACHED_BYTES = re.compile(r" *([0-9.]+) *([KMG]?i?B) *\|")


def download_size(text: str) -> str | None:
    """`run_size`'s parse: the first line carrying a figure, as text.

    Returns e.g. "371.4 MiB" — the exact string `@@SIZE@@|system|…` reports.
    None when no line matches, which is the "nothing to fetch" case the caller
    must tell apart from a failed run.
    """
    # split("\n"), never splitlines(): the Bash reads these logs a line at a time
    # and a line ends at \n alone. splitlines() also breaks on \r, \v, \f and the
    # Unicode separators, which invents lines the other engine never sees
    # (ONEUP-0152). Every parser in this module splits the same way.
    for line in text.split("\n"):
        found = _SIZE_TEXT.match(line) or _SIZE_CACHED_TEXT.match(line)
        if found:
            return found.group(1)
    return None


def progress_total_bytes(line: str) -> int | None:
    """`progress_filter`'s parse: the transaction total, in bytes.

    This is what lets the window show "19 MB of 86 MB" and a rate — the two
    numbers that tell a slow download from a stalled one.
    """
    found = _SIZE_BYTES.match(line)
    if not found and "|" in line and line.endswith("already in cache"):
        found = _SIZE_CACHED_BYTES.match(line)
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


# Flatpak's own count, `Updating 3/12…`: one word, then the count and an ellipsis.
# The word is not read, so a translated Flatpak still counts (ONEUP-0239 §4.1.4).
_FLATPAK_COUNT = re.compile(r"^\S+ ([0-9]+)/([0-9]+)\u2026")


def flatpak_count(line: str) -> tuple[int, int] | None:
    """The update Flatpak has started and how many there are, or None.

    Flatpak prints the line as each update starts and again at each percentage
    step, so the same count arrives many times; the caller sends each once.
    """
    found = _FLATPAK_COUNT.match(line)
    return (int(found.group(1)), int(found.group(2))) if found else None


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
    for line in text.split("\n"):
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


# The reboot reason's component codes (ONEUP-0072 §4.1) and the English the
# terminal summary still prints for each; the window holds its own copy.
REBOOT_COMPONENTS = {
    "kernel-new": "a new kernel",
    "graphics-driver-nvidia": "your NVIDIA graphics driver",
    "graphics-driver-generic": "your graphics driver",
    "kernel-modules": "kernel driver modules",
}


def reboot_components(log: str) -> list[str]:
    """Which reboot-worthy components the transaction installed, as codes, in the
    order the reason names them. Empty when nothing qualifies.

    Reading the log is `steps.py`'s (§4.2); this picks the components from the
    lines it found.
    """
    parts = []
    if _KERNEL.search(log):
        parts.append("kernel-new")
    if _NVIDIA.search(log):
        parts.append("graphics-driver-nvidia")
    elif _GRAPHICS.search(log):
        parts.append("graphics-driver-generic")
    # DKMS / kernel-module packages OTHER than the NVIDIA one already named.
    if any(_MODULE.search(line) and not _NVIDIA_ANYWHERE.search(line)
           for line in log.split("\n")):
        parts.append("kernel-modules")
    return parts


def reboot_phrase(components: list[str]) -> str:
    """The terminal's English for those components. "" for none."""
    parts = [REBOOT_COMPONENTS[c] for c in components]
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



# --- one package at a time (ONEUP-0259) ----------------------------------------
# Unlike everything above, these reproduce nothing in `update_system.sh`: the
# Bash engine is frozen and never learnt to name a package. They are new parsers
# for the package model, kept here for the same reason the others are — pure,
# so `tests/parsers-test.py` can feed them lines.


class Update(NamedTuple):
    """One pending update, as `zypper --xmlout list-updates` names it."""

    name: str
    edition: str      # zypper's own string: version-release, `epoch:` kept
    old: str          # the installed edition, "" when zypper gives none
    arch: str
    alias: str        # the repository's alias, "" when zypper gives none


def update_list(xml_text: str) -> tuple[list[Update], list[str]] | None:
    """`zypper --xmlout list-updates`' stdout: the package updates, in zypper's
    order, and the text of every `<message>`. None when it is not well-formed.

    The messages come back unescaped, which is why a caller searches them rather
    than the raw text: an `&apos;` would otherwise hide the quote a pattern
    looks for (ONEUP-0259 §4.3).
    """
    try:
        # zypper's own stdout. ElementTree resolves no external entity, and the
        # expat it uses refuses entity amplification — both measured on expat 2.9.0.
        root = ET.fromstring(xml_text)  # noqa: S314 — local tool output, see above
    except ET.ParseError:
        return None
    updates = []
    for node in root.iter("update"):
        if node.get("kind") != "package":
            continue
        source = node.find("source")
        updates.append(Update(
            node.get("name", ""), node.get("edition", ""), node.get("edition-old", ""),
            node.get("arch", ""), source.get("alias", "") if source is not None else "",
        ))
    messages = [m.text or "" for m in root.iter("message")]
    return updates, messages


class Change(NamedTuple):
    """One package the update will change, from a dry run's install summary."""

    name: str
    edition: str      # the model's key edition: the new one, or a removal's own
    old: str          # edition-old; for a removal its own edition; "" for a new package
    arch: str
    repo: str         # the `repository` attribute as printed: an alias (ONEUP-0329 §4.8)
    change: str       # upgrade | downgrade | new | remove


# Each `install-summary` child zypper writes, and the word its packages count as
# (ONEUP-0329 §4.3). `to-change-vendor` is in no schema but zypper 1.14.101 prints
# it; it takes the word of the package's other listing, so it maps to None here.
_CHANGE_WORD = {
    "to-upgrade": "upgrade", "to-upgrade-change-arch": "upgrade",
    "to-reinstall": "upgrade", "to-change-arch": "upgrade",
    "to-downgrade": "downgrade", "to-downgrade-change-arch": "downgrade",
    "to-install": "new",
    "to-remove": "remove",
    "to-change-vendor": None,
}


def change_list(xml_text: str) -> tuple[list[Change], list[str]] | None:
    """A `zypper --xmlout … --dry-run`'s stdout: every package it would change, in
    zypper's order, and the text of every `<message>`, unescaped.

    None when the text is not well-formed, holds no `install-summary`, holds a
    summary child the table does not know, or a `solvable` with neither `type` nor
    `kind`: a summary this cannot fully read must never count as zero. With nothing
    to do, zypper prints an empty summary, which is an exact zero (§4.8, measured).

    One change per `(name, edition)`: a package listed twice is counted once, with
    the word of its first listing outside `to-change-vendor`, or `upgrade` if it
    has none.
    """
    try:
        root = ET.fromstring(xml_text)  # noqa: S314 — zypper's own stdout, see update_list
    except ET.ParseError:
        return None
    summaries = list(root.iter("install-summary"))
    if not summaries:
        return None
    found: dict[tuple[str, str], list] = {}     # (name, edition) -> [Change, word or None]
    for summary in summaries:
        for group in summary:
            if group.tag not in _CHANGE_WORD:
                return None
            word = _CHANGE_WORD[group.tag]
            for node in group.iter("solvable"):
                # The schema says `kind`; zypper 1.14.101 writes `type` (§2).
                kind = node.get("type", node.get("kind"))
                if kind is None:
                    return None
                if kind != "package":
                    continue
                name, edition = node.get("name", ""), node.get("edition", "")
                old = edition if word == "remove" else node.get("edition-old", "")
                entry = found.setdefault((name, edition), [
                    Change(name, edition, old, node.get("arch", ""),
                           node.get("repository", ""), ""), None])
                if entry[1] is None and word is not None:
                    entry[1] = word
                    entry[0] = entry[0]._replace(old=old)
    changes = [change._replace(change=word or "upgrade") for change, word in found.values()]
    messages = [m.text or "" for m in root.iter("message")]
    return changes, messages


def repo_names(xml_text: str) -> dict[str, str]:
    """`zypper --xmlout repos`: each alias's display name. Empty when unreadable."""
    try:
        root = ET.fromstring(xml_text)  # noqa: S314 — zypper's own stdout, see update_list
    except ET.ParseError:
        return {}
    return {repo.get("alias", ""): repo.get("name", "") for repo in root.iter("repo")
            if repo.get("alias")}


def split_nvra(nvra: str) -> tuple[str, str, str] | None:
    """`cpupower-lang-7.1.4-17.noarch` -> ("cpupower-lang", "7.1.4-17", "noarch").

    From the right: the architecture after the last `.`, the release after the
    last `-`, the version after the `-` before it. Neither a version nor a
    release may contain `-`, so what is left is the name. An `epoch:` stays inside
    the version, which is how zypper writes an edition. None when a part is
    missing.
    """
    rest, dot, arch = nvra.rpartition(".")
    if not dot or not arch:
        return None
    parts = rest.rsplit("-", 2)
    if len(parts) != 3 or not all(parts):
        return None
    name, version, release = parts
    return name, f"{version}-{release}", arch


# An action line: `( 7/77) Installing: <nvra> [...done]`. Upgrading counts as
# installing, as `stream_filtered` already counts it.
_ACTION = re.compile(r"^\( *[0-9]+/[0-9]+\) (Installing|Upgrading|Removing): (\S+)")
_ACTION_STATE = {"Installing": "installed", "Upgrading": "installed",
                 "Removing": "removed"}


def rpm_changed(text: str) -> bool:
    """Did rpm finish installing or removing at least one package in this log?

    Read through `PackageLines`, so a package cut by its own script's output still
    counts once its `done]` arrives, and one rpm abandoned never counts (ONEUP-0330).
    """
    lines = PackageLines()
    return any(row[0] in ("installed", "removed")
               for line in text.splitlines() for row in lines.feed(line))


class PackageLines:
    """Turns zypper's transaction lines into `(state, name, edition, bytes)`.

    One instance per pass, fed every line in order, because one fact spans
    lines: a package's own script can split an action line before its `done]`.
    Measured in a OneUp run log of 2026-10-12 —

        (117/320) Installing: xorg-x11-server-21.1.24-2.1.x86_64 [...
        Updating /etc/sysconfig/displaymanager ...
        done]

    so a cut action is held, and the next line ending in `done]` that is not
    itself an action completes it. The next action, or `finish`, drops it: an
    action never seen to complete is never reported as done (ONEUP-0259 INV-6).

    A package fetched by `Retrieving:` lines is `downloading` until its fetch ends:
    at the next package's `Retrieving:` line, the first action line, or `finish`.
    It is then `downloaded`, so it leaves "now" while it waits to install
    (ONEUP-0239 §4.3.1). So one line can settle two packages, and `feed` returns
    a list.
    """

    def __init__(self) -> None:
        self._held: tuple[str, str, str] | None = None
        self._fetching: tuple[str, str] | None = None

    def feed(self, line: str) -> list[tuple[str, str, str, int]]:
        text = line.rstrip()
        row = self._read(text)
        ends_fetch = (_ACTION.match(text) is not None
                      or (row is not None and row[0] == "downloading"
                          and row[1:3] != self._fetching))
        rows = self._end_fetch() if ends_fetch else []
        if row is not None:
            rows.append(row)
            if row[0] == "downloading":
                self._fetching = (row[1], row[2])
        return rows

    def finish(self) -> list[tuple[str, str, str, int]]:
        """The stream ended: anything still held never completed, and a fetch did."""
        self._held = None
        return self._end_fetch()

    def _end_fetch(self) -> list[tuple[str, str, str, int]]:
        if self._fetching is None:
            return []
        name, edition = self._fetching
        self._fetching = None
        return [("downloaded", name, edition, 0)]

    def _read(self, text: str) -> tuple[str, str, str, int] | None:
        """What this one line says of one package, if anything."""
        action = _ACTION.match(text)
        if action:
            self._held = None
            split = split_nvra(action.group(2))
            if split is None:
                return None
            state = _ACTION_STATE[action.group(1)]
            if text.endswith("done]"):
                return state, split[0], split[1], 0
            if "]" not in text[action.end():]:
                self._held = (state, split[0], split[1])
            return None
        if text.startswith("Retrieving:"):
            # A fetch can print a second line for the file itself, `<nvra>.rpm`.
            # It names the package already being fetched, so it says nothing new
            # (ONEUP-0335); read with `.rpm` as the architecture it was a phantom.
            token = text[len("Retrieving:"):].split(maxsplit=1)
            split = split_nvra(token[0].removesuffix(".rpm")) if token else None
            if split is None or (split[0], split[1]) == self._fetching:
                return None
            return "downloading", split[0], split[1], retrieving_bytes(text)
        if text.startswith("Preloading:"):
            if not (text.endswith("[done]") or text.endswith("[already in cache]")):
                return None
            token = text[len("Preloading:"):].split(maxsplit=1)
            split = split_nvra(token[0].removesuffix(".rpm")) if token else None
            return ("downloaded", split[0], split[1], 0) if split else None
        if self._held is not None and text.endswith("done]"):
            state, name, edition = self._held
            self._held = None
            return state, name, edition, 0
        return None
