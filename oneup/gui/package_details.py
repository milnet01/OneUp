"""Where a package's details come from: zypper's About and rpm's change notes.

`docs/specs/ONEUP-0260-package-details.md` §4.1 and §4.3. Plain Python, with no
Qt, so `tests/parsers-test.py` can import it and stay stdlib-only; the process
and the dialog that use it live in `details_dialog.py`.

Every call here is an unprivileged read: a fixed list argv, no shell, the locale
pinned to C (`docs/standards/security.md` §4.3). Every package name passes
`_NAME_RE` and every edition `_EDITION_RE` before it reaches an argv or a glob.
"""
from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# An rpm package name. The first character excludes "-", so a name can never be
# read as an option; neither class holds a glob character.
_NAME_RE = re.compile(r"[A-Za-z0-9_+][A-Za-z0-9._+-]*")
# An edition once its epoch is removed: rpm file names and `rpm -q` names carry
# none, so ":" is not allowed here.
_EDITION_RE = re.compile(r"[A-Za-z0-9._+~^-]+")
_EPOCH_RE = re.compile(r"\d+:")

# rpm's --qf does not expand an escape for these, so the characters themselves
# go in the argv (§2): one between entries, one between an entry's fields, so a
# multi-line text stays one field.
_E, _F = "\x1e", "\x1f"
_ENTRIES_QF = f"[%{{CHANGELOGTIME}}{_F}%{{CHANGELOGNAME}}{_F}%{{CHANGELOGTEXT}}{_E}]"
# Unbracketed, a changelog tag is the newest entry; one record per installed
# version, so a multiversion package prints several.
_BASELINE_QF = (f"%{{NAME}}{_F}%{{VERSION}}-%{{RELEASE}}{_F}%{{CHANGELOGTIME}}{_F}"
                f"%{{CHANGELOGNAME}}{_F}%{{CHANGELOGTEXT}}{_E}")
_FALLBACK = 20          # entries shown when OneUp cannot tell which are new
RPM_TIMEOUT = 5         # seconds; rpm answers in well under one (§2)
ENV = {**os.environ, "LC_ALL": "C"}


@dataclass(frozen=True)
class About:
    summary: str
    description: str
    url: str


@dataclass(frozen=True)
class Entry:
    time: int
    author: str
    text: str


@dataclass
class WhatChanged:
    """`kind` is "entries", "no-notes", "not-found" or "not-yet". `known` is
    False when OneUp could not tell which entries are new (§4.3)."""
    kind: str
    entries: list[Entry] = field(default_factory=list)
    known: bool = True


def valid_name(name: str) -> bool:
    return bool(_NAME_RE.fullmatch(name))


def strip_epoch(edition: str) -> str:
    return _EPOCH_RE.sub("", edition, count=1)


def _edition(edition: str) -> str | None:
    bare = strip_epoch(edition)
    return bare if _EDITION_RE.fullmatch(bare) else None


def packages_dir() -> str:
    return os.environ.get("ONEUP_ZYPP_PACKAGES") or "/var/cache/zypp/packages"


# --- About: zypper info --------------------------------------------------------

def build_info_argv(names: list[str]) -> list[str] | None:
    """One batched `zypper info` for the valid names, or None if there are none."""
    keep = [n for n in names if valid_name(n)]
    if not keep:
        return None
    return ["zypper", "--no-refresh", "--non-interactive", "info", *keep]


_BLOCK_RE = re.compile(r"^Information for package (\S+):\s*$", re.M)
_FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s*:\s?(.*)$")


def parse_info(text: str) -> dict[str, About]:
    """`{name: About}` from zypper's `Key : value` blocks. A block with neither a
    summary nor a description is no About; a name with no block is absent."""
    out: dict[str, About] = {}
    heads = list(_BLOCK_RE.finditer(text))
    for n, head in enumerate(heads):
        body = text[head.end():heads[n + 1].start() if n + 1 < len(heads) else len(text)]
        fields: dict[str, str] = {}
        desc: list[str] = []
        in_desc = False
        for line in body.splitlines():
            if in_desc:
                if line.startswith(" ") or not line:
                    desc.append(line.strip())
                    continue
                in_desc = False
            m = _FIELD_RE.match(line)
            if not m:
                continue
            key, value = m.group(1).strip(), m.group(2).strip()
            if key == "Description":
                in_desc = True
                if value:
                    desc.append(value)
            else:
                fields[key] = value
        description = "\n".join(desc).strip()
        summary = fields.get("Summary", "")
        if summary or description:
            out[head.group(1)] = About(summary, description, fields.get("Upstream URL", ""))
    return out


# --- the baseline: the old version's newest entry --------------------------------

def build_baseline_argv(names: list[str]) -> list[str] | None:
    keep = [n for n in names if valid_name(n)]
    if not keep:
        return None
    return ["rpm", "-q", "--qf", _BASELINE_QF, *keep]


def _records(text: str):
    """Split rpm output into records of fields. A line rpm prints between records
    (`package x is not installed`) lands before the next record's first field,
    and is cut off at its last newline."""
    for chunk in text.split(_E):
        parts = chunk.split(_F)
        if len(parts) < 2:
            continue
        parts[0] = parts[0].rsplit("\n", 1)[-1]
        yield parts


def parse_baseline(text: str, olds: dict[str, str]) -> dict[str, Entry]:
    """`{name: Entry}`: for each name, the line whose version-release equals that
    package's old version with any epoch removed. `(none)` gives no entry."""
    out: dict[str, Entry] = {}
    for parts in _records(text):
        if len(parts) != 5:
            continue
        name, vr, when, author, body = parts
        old = olds.get(name)
        if old is None or vr != strip_epoch(old) or not when.isdecimal():
            continue
        out[name] = Entry(int(when), author, body)
    return out


# --- What changed -------------------------------------------------------------------

def parse_entries(text: str) -> list[Entry]:
    out = []
    for parts in _records(text):
        if len(parts) == 3 and parts[0].isdecimal():
            out.append(Entry(int(parts[0]), parts[1], parts[2]))
    return out


def new_entries(entries: list[Entry], baseline: Entry | None) -> tuple[list[Entry], bool]:
    """The entries before the first one equal to the baseline, matched on time,
    author and text: two entries on one day share a time, and one packager often
    writes both. No baseline, or one never met, is the newest few, unknown."""
    if baseline is not None:
        for n, e in enumerate(entries):
            if e == baseline:
                return entries[:n], True
    return entries[:_FALLBACK], False


def find_download(name: str, edition: str, root: str | None = None) -> str | None:
    """The one downloaded file for this name and edition, or None."""
    bare = _edition(edition)
    if not valid_name(name) or bare is None:
        return None
    hits = list(Path(root or packages_dir()).glob(f"**/{name}-{bare}.*.rpm"))
    return str(hits[0]) if len(hits) == 1 else None


def _rpm(argv: list[str], run: Callable) -> str | None:
    try:
        # Lenient: a packager's changelog need not be UTF-8 (ONEUP-0334).
        out = run(argv, capture_output=True, text=True, errors="replace",
                  timeout=RPM_TIMEOUT, env=ENV)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout


def changelog(name: str, edition: str, state: str, baseline: Entry | None,
              run: Callable = subprocess.run, root: str | None = None) -> WhatChanged:
    """What the new version adds (§4.3), read from the rpm database once the
    package is installed, or from the downloaded file before that."""
    bare = _edition(edition)
    if not valid_name(name) or bare is None:
        return WhatChanged("not-yet")
    if state == "installed":
        text = _rpm(["rpm", "-q", "--qf", _ENTRIES_QF, f"{name}-{bare}"], run)
    elif state == "downloaded":
        path = find_download(name, edition, root)
        if path is None:
            return WhatChanged("not-found")
        text = _rpm(["rpm", "-qp", "--qf", _ENTRIES_QF, path], run)
    else:
        return WhatChanged("not-yet")
    entries = parse_entries(text or "")
    if not entries:
        return WhatChanged("no-notes")
    shown, known = new_entries(entries, baseline)
    return WhatChanged("entries", shown, known)
