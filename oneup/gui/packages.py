"""The package model: every package an update touches, with its versions, size and state.

`docs/specs/ONEUP-0259-package-model.md` §4.6. One instance per window, filled from
the engine's `@@CHECK_ITEM@@` and `@@PKG@@` lines; every view of the packages reads
it and none writes it. Plain Python, with no Qt, so a test can drive it without a
window.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# The order a package moves through. A state never moves backwards: the commit
# pass reprints `Preloading: … [already in cache]` for packages already installed.
_ORDER = {"queued": 0, "downloading": 1, "downloaded": 2, "installed": 3, "removed": 3}
STATES = tuple(_ORDER)


@dataclass
class Package:
    key: str
    name: str
    edition: str
    old: str = ""
    size: int = 0
    repo: str = ""
    state: str = "queued"


class PackageModel:
    """Packages keyed by (step key, name, edition), kept in the engine's order."""

    def __init__(self) -> None:
        self._packages: dict[tuple[str, str, str], Package] = {}
        self._finished: set[str] = set()
        self._callbacks: list[Callable[[str | None], None]] = []

    def reset(self) -> None:
        self._packages.clear()
        self._finished.clear()
        self._notify(None)

    def add_check_item(self, parts: list[str]) -> None:
        """`key|name|from|to[|bytes|repo]`. Only key and name are required."""
        if len(parts) < 2 or not parts[0] or not parts[1]:
            return
        size = parts[4] if len(parts) > 4 else "0"
        if not size.isdecimal():
            return
        key, name = parts[0], parts[1]
        edition = parts[3] if len(parts) > 3 else ""
        self._packages[(key, name, edition)] = Package(
            key, name, edition, old=parts[2] if len(parts) > 2 else "", size=int(size),
            repo=parts[5] if len(parts) > 5 else "")
        self._notify(key)

    def apply(self, parts: list[str]) -> None:
        """`key|state|name|edition[|bytes|from|repo]`. A package not yet seen is
        added, whatever its state: `dup` can change more than the list named."""
        if len(parts) < 4 or not parts[0] or not parts[2] or parts[1] not in _ORDER:
            return
        size = parts[4] if len(parts) > 4 and parts[4] else "0"
        if not size.isdecimal():
            return
        key, state, name, edition = parts[0], parts[1], parts[2], parts[3]
        package = self._packages.get((key, name, edition))
        if package is None:
            package = self._packages[(key, name, edition)] = Package(key, name, edition)
        if len(parts) > 4 and int(size):
            package.size = int(size)
        if len(parts) > 5 and parts[5]:
            package.old = parts[5]
        if len(parts) > 6 and parts[6]:
            package.repo = parts[6]
        if _ORDER[state] >= _ORDER[package.state]:
            package.state = state
        self._notify(key)

    def end_step(self, key: str) -> None:
        self._finished.add(key)
        self._notify(key)

    def packages(self, key: str | None = None) -> list[Package]:
        return [p for p in self._packages.values() if key is None or p.key == key]

    def finished(self, key: str) -> bool:
        return key in self._finished

    def shown_state(self, package: Package) -> str:
        """The state a view shows: after its step ended, a package that was not
        installed or removed reads `unchanged` — never inferred from the step's
        status (INV-7)."""
        if self.finished(package.key) and package.state not in ("installed", "removed"):
            return "unchanged"
        return package.state

    def subscribe(self, callback: Callable[[str | None], None]) -> None:
        """Called with the step key that changed; `reset()` calls it once with None."""
        self._callbacks.append(callback)

    def unsubscribe(self, callback: Callable[[str | None], None]) -> None:
        """The inverse of `subscribe`. A view about to be deleted calls it, or the
        next change calls into a deleted widget (ONEUP-0239 §4.1)."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify(self, key: str | None) -> None:
        for callback in self._callbacks:
            callback(key)
