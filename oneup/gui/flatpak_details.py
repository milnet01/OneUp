"""Where a Flatpak's details come from: the remote's AppStream catalogue (ONEUP-0365).

`docs/specs/ONEUP-0260-package-details.md` §4.7. Flatpak keeps each remote's
catalogue on disk and refreshes it as it updates, so the details need no root and
no network. Plain Python, with no Qt, so `tests/parsers-test.py` can import it and
stay stdlib-only; `details_dialog.py` runs `read` on a worker thread, because the
catalogue is large.
"""
from __future__ import annotations

import gzip
import os
import platform
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# A Flatpak application ID or remote name. The first character excludes "-" and
# ".", so neither can be read as an option or climb out of a directory.
_ID_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*")
_FALLBACK = 5           # releases shown when OneUp cannot tell which are new
_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_ARCH = {"amd64": "x86_64", "arm64": "aarch64"}     # platform's names → Flatpak's


@dataclass(frozen=True)
class Release:
    version: str
    time: int
    text: str


@dataclass(frozen=True)
class Component:
    name: str
    summary: str
    description: str
    url: str
    releases: tuple[Release, ...] = ()


@dataclass
class WhatChanged:
    """`kind` is "entries" or "no-notes". `known` is False when OneUp could not
    tell which releases are new; `entries` is then the newest few."""
    kind: str
    entries: list[Release] = field(default_factory=list)
    known: bool = True


def valid_id(name: str) -> bool:
    return bool(_ID_RE.fullmatch(name))


def installations() -> list[Path]:
    """The user installation, then the system one. `FLATPAK_USER_DIR` and
    `FLATPAK_SYSTEM_DIR` override them, as they do for Flatpak itself."""
    data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return [Path(os.environ.get("FLATPAK_USER_DIR") or os.path.join(data, "flatpak")),
            Path(os.environ.get("FLATPAK_SYSTEM_DIR") or "/var/lib/flatpak")]


def appstream_files(remotes: set[str]) -> list[str]:
    """Each named remote's catalogue for this machine's architecture, in each
    installation that has one: the plain file where it exists, else the gzip."""
    machine = platform.machine()
    arch = _ARCH.get(machine.lower(), machine)
    out: list[str] = []
    for base in installations():
        for remote in sorted(r for r in remotes if valid_id(r)):
            active = base / "appstream" / remote / arch / "active"
            for name in ("appstream.xml", "appstream.xml.gz"):
                if (active / name).is_file():
                    out.append(str(active / name))
                    break
    return out


# --- reading the catalogue --------------------------------------------------------

def _flat(el: ET.Element) -> str:
    return " ".join("".join(el.itertext()).split())


def _text(el: ET.Element | None) -> str:
    """AppStream markup as plain text: a paragraph per <p>, a bullet per <li>."""
    if el is None:
        return ""
    lines: list[str] = []
    for child in el:
        if child.tag == "p":
            lines += [_flat(child), ""]
        elif child.tag in ("ul", "ol"):
            lines += [f"• {_flat(li)}" for li in child if li.tag == "li"]
            lines.append("")
    return "\n".join(lines).strip() or _flat(el)


def _untranslated(el: ET.Element, tag: str) -> ET.Element | None:
    """The element in the catalogue's own language; a translation carries xml:lang."""
    return next((c for c in el.findall(tag) if _LANG not in c.attrib), None)


def _component(el: ET.Element) -> Component:
    def plain(tag: str) -> str:
        found = _untranslated(el, tag)
        return _flat(found) if found is not None else ""

    url = next((_flat(u) for u in el.findall("url") if u.get("type") == "homepage"), "")
    releases = []
    for rel in el.findall("releases/release"):
        stamp = rel.get("timestamp") or ""
        releases.append(Release(rel.get("version") or "", int(stamp) if stamp.isdigit() else 0,
                                _text(_untranslated(rel, "description"))))
    releases.sort(key=lambda r: r.time, reverse=True)   # stable: equal times keep file order
    return Component(plain("name"), plain("summary"),
                     _text(_untranslated(el, "description")), url, tuple(releases))


def read(files: list[str], ids: set[str]) -> dict[str, list[Component]]:
    """`{id: [Component]}` for the wanted IDs, one per distinct branch the catalogues list.
    A file that cannot be read or parsed contributes what it gave before failing.

    The catalogue is Flatpak's own, fetched and verified by it from a configured
    remote; expat expands no external entity, and the read is the window's own,
    unprivileged."""
    out: dict[str, list[Component]] = {}
    for path in files:
        try:
            with gzip.open(path) if path.endswith(".gz") else open(path, "rb") as fh:
                for _event, el in ET.iterparse(fh):  # noqa: S314 — see the docstring.
                    if el.tag != "component":
                        continue
                    cid = (el.findtext("id") or "").strip().removesuffix(".desktop")
                    found = out.setdefault(cid, []) if cid in ids else None
                    # A remote set up for both installations lists each branch twice.
                    if found is not None and (comp := _component(el)) not in found:
                        found.append(comp)
                    el.clear()
        except (OSError, EOFError, ET.ParseError):
            continue
    return out


# --- choosing what to show --------------------------------------------------------

def choose(components: list[Component], edition: str) -> Component | None:
    """The branch that lists the new version, else the first the catalogues give."""
    for comp in components:
        if edition and any(r.version == edition for r in comp.releases):
            return comp
    return components[0] if components else None


def build_installed_argv() -> list[str]:
    return ["flatpak", "list", "--columns=application,version"]


def parse_installed(text: str) -> dict[str, set[str]]:
    """`flatpak list --columns=application,version` as `{id: {versions}}`; a ref
    with no version is left out."""
    out: dict[str, set[str]] = {}
    for line in text.splitlines():
        app, _, version = (part.strip() for part in line.partition("\t"))
        if app and version:
            out.setdefault(app, set()).add(version)
    return out


def what_changed(comp: Component | None, installed: set[str] | None) -> WhatChanged:
    """The releases newer than the installed one. With none of them installed, the
    newest few, marked unknown (§4.7)."""
    if comp is None or not comp.releases:
        return WhatChanged("no-notes")
    for n, rel in enumerate(comp.releases):
        if installed and rel.version in installed:
            return WhatChanged("entries", list(comp.releases[:n]))
    return WhatChanged("entries", list(comp.releases[:_FALLBACK]), known=False)
