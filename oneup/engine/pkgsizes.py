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
import shutil
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

from . import proc

# One budget for the whole lookup, across every repository. Measured 2026-10-12:
# the main Tumbleweed repository alone (52,972 packages) took 3.6 s to scan.
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


def _scan(primary: Path, keys: set[tuple[str, str, str]],
          budget: float) -> dict[tuple[str, str, str], int]:
    """Stream `primary`, keeping the size of each wanted (name, edition, arch)."""
    found: dict[tuple[str, str, str], int] = {}
    ends = time.monotonic() + budget
    child = None
    timer = None
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
            # the per-package time check below.
            timer = threading.Timer(budget, proc.kill_group, (child.pid,))
            timer.start()
        else:
            return found
        with stream:
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
    except (OSError, ET.ParseError, EOFError):
        pass        # what was found before the failure still stands
    finally:
        if timer is not None:
            timer.cancel()
        if child is not None:
            proc.kill_group(child.pid)
            child.wait()
    return found
