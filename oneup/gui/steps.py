"""The five update steps, their keys, titles and order.

The run order both halves of the app share; the engine's own `LABEL` map in
`update_system.sh` mirrors it. A step whose tool is absent is skipped cleanly,
never errored — keep new steps tolerant of a missing binary.
"""
from __future__ import annotations

# key, title, one-line description. Order = run order.
TASKS = [
    ("system", "System packages", "Refresh repositories and upgrade openSUSE (zypper dup)."),
    ("flatpak", "Flatpak apps", "Update Flatpak apps and remove unused runtimes."),
    ("firmware", "Firmware", "Check for and apply device firmware updates (fwupd)."),
    ("orphans", "Leftover packages", "Remove leftover dependency packages nothing needs."),
    ("cache", "Package cache", "Clear the downloaded-package cache to free disk space."),
]

