"""Each pending package's download size, from zypper's own copy of the repository data.

`docs/specs/ONEUP-0259-package-model.md` §4.5. zypper keeps every repository's
metadata under `/var/cache/zypp/raw/<alias>/repodata/`, readable by any user, and
its `primary` file carries `<size package="…">` for every package — the download
size `list-updates` does not report. Reading it needs no password, so a check can
show sizes and stay rootless.

Never raises: a size this cannot find is simply absent, and the caller reports 0.
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
import zlib
from collections.abc import Iterable
from pathlib import Path

from . import proc

# One budget for the whole lookup, across every repository. The main Tumbleweed
# repository alone took 3.6 s to scan with ElementTree (2026-10-12) and 0.59 s with
# the byte pattern below (53,080 packages, 2026-11-15).
SIZE_LOOKUP_SECONDS = float(os.environ.get("ONEUP_SIZE_LOOKUP_TIMEOUT") or "15")

_REPO = "{http://linux.duke.edu/metadata/repo}"
_COMMON = "{http://linux.duke.edu/metadata/common}"

Key = tuple[str, str, str, str]     # (alias, name, edition, arch)


def raw_root() -> Path:
    """Where zypper keeps the raw repository data. The suite redirects it (INV-3)."""
    return Path(os.environ.get("ONEUP_ZYPP_RAW") or "/var/cache/zypp/raw")


def download_sizes(wanted: Iterable[Key], deadline: float) -> dict[Key, int]:
    """(alias, name, edition, arch) -> bytes, for each one found within `deadline`
    seconds. Only repositories holding a wanted package are opened."""
    started = time.monotonic()
    by_alias: dict[str, set[tuple[str, str, str]]] = {}
    for alias, name, edition, arch in wanted:
        by_alias.setdefault(alias, set()).add((name, edition, arch))
    root = raw_root()
    found: dict[Key, int] = {}
    for alias, keys in by_alias.items():
        left = deadline - (time.monotonic() - started)
        if left <= 0:
            break
        # The alias comes from zypper's output, and is joined onto a path: one that
        # could climb out of the root is refused rather than followed (INV-3).
        if not alias or "/" in alias or alias in (".", ".."):
            continue
        primary = _primary(root / alias)
        if primary is None:
            continue
        for key, size in _scan(primary, keys, left).items():
            found[(alias, *key)] = size
    return found


def _primary(repo: Path) -> Path | None:
    """The repository's `primary` file, as its `repomd.xml` names it."""
    try:
        # Repository metadata zypper fetched and verified before caching it; expat
        # resolves no external entity and refuses amplification (parsers.py).
        index = ET.parse(repo / "repodata" / "repomd.xml")  # noqa: S314 — see above
    except (OSError, ET.ParseError):
        return None
    for data in index.getroot().iter(f"{_REPO}data"):
        if data.get("type") != "primary":
            continue
        location = data.find(f"{_REPO}location")
        href = location.get("href", "") if location is not None else ""
        path = (repo / href).resolve()
        if href and path.is_relative_to(repo.resolve()) and path.is_file():
            return path
    return None


def _edition(version: ET.Element) -> str:
    """zypper's spelling: version-release, with `epoch:` only when it is not 0."""
    epoch = version.get("epoch", "0")
    edition = f"{version.get('ver', '')}-{version.get('rel', '')}"
    return edition if epoch in ("", "0") else f"{epoch}:{edition}"


# createrepo's layout of one package's head, as every repository this was measured on
# writes it (12 repositories, 2026-11-15). A block whose packages this does not all
# match is read by ElementTree instead, so another layout costs time, never a size.
_PACKAGE = re.compile(
    rb'<package type="rpm">\s*<name>([^<&]*)</name>\s*<arch>([^<&]*)</arch>\s*'
    rb'<version epoch="([^"&]*)" ver="([^"&]*)" rel="([^"&]*)"/>.*?<size package="(\d+)"',
    re.S)
_CHUNK = 1 << 20


def _scan(primary: Path, keys: set[tuple[str, str, str]],
          budget: float) -> dict[tuple[str, str, str], int]:
    """The size of each wanted (name, edition, arch) in `primary`.

    A byte pattern first, five times faster than ElementTree on the main Tumbleweed
    repository (0.66 s against 3.55 s, ONEUP-0386); ElementTree when the pattern does
    not account for every package."""
    ends = time.monotonic() + budget
    found = _read(primary, keys, ends, _pattern_pass)
    if found is None:
        found = _read(primary, keys, ends, _tree_pass) or {}
    return found


def _pattern_pass(stream, keys, ends) -> dict[tuple[str, str, str], int] | None:
    """None as soon as a block holds a package the pattern does not match."""
    found: dict[tuple[str, str, str], int] = {}
    buf = b""
    while chunk := stream.read(_CHUNK):
        buf += chunk
        cut = buf.rfind(b"</package>")
        if cut < 0:
            continue
        cut += len(b"</package>")
        block, buf = buf[:cut], buf[cut:]
        matched = 0
        for m in _PACKAGE.finditer(block):
            matched += 1
            # `replace`: one byte that is not UTF-8 must not cost every other
            # package its size, or escape this module (ONEUP-0425).
            name, arch, epoch, ver, rel, size = (g.decode(errors="replace")
                                                 for g in m.groups())
            edition = f"{ver}-{rel}" if epoch in ("", "0") else f"{epoch}:{ver}-{rel}"
            if (name, edition, arch) in keys:
                found[(name, edition, arch)] = int(size)
        if matched != block.count(b"<package "):
            return None
        if len(found) == len(keys) or time.monotonic() > ends:
            break
    return found


def _tree_pass(stream, keys, ends) -> dict[tuple[str, str, str], int]:
    found: dict[tuple[str, str, str], int] = {}
    for _event, node in ET.iterparse(stream):  # noqa: S314 — see _primary
        if node.tag != f"{_COMMON}package":
            continue
        version = node.find(f"{_COMMON}version")
        size = node.find(f"{_COMMON}size")
        key = (node.findtext(f"{_COMMON}name", ""),
               _edition(version) if version is not None else "",
               node.findtext(f"{_COMMON}arch", ""))
        if key in keys and size is not None and size.get("package", "").isdecimal():
            found[key] = int(size.get("package", "0"))
        node.clear()
        if len(found) == len(keys) or time.monotonic() > ends:
            break
    return found


def _read(primary: Path, keys, ends, reader):
    """Open `primary` decompressed and hand it to `reader`; {} on any read failure."""
    child = None
    timer = None
    budget = max(ends - time.monotonic(), 0.0)
    try:
        if primary.name.endswith(".gz"):
            stream = gzip.open(primary)
        elif primary.name.endswith(".zst") and (zstdcat := shutil.which("zstdcat")):
            # Its own session, so the watchdog's one killpg reaches it; a zstdcat
            # whose reader died exits on SIGPIPE, so it cannot outlive the engine.
            child = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
                [zstdcat, "--", str(primary)], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, start_new_session=True,
            )
            stream = child.stdout
            # A watchdog, because a reader that never gets a byte never reaches
            # the per-package time check.
            timer = threading.Timer(budget, proc.kill_group, (child.pid,))
            timer.start()
        else:
            return {}
        with stream:
            return reader(stream, keys, ends)
    # zlib.error is not an OSError: a corrupt deflate stream raises it from inside the
    # gzip read, and it escaped into the system step and --check (ONEUP-0397).
    except (OSError, ET.ParseError, EOFError, zlib.error):
        return {}
    finally:
        if timer is not None:
            timer.cancel()
        if child is not None:
            proc.kill_group(child.pid)
            child.wait()
