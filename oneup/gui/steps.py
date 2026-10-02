"""The five update steps, their keys, titles and order.

The run order both halves of the app share; the engine's own `LABEL` map (its
step module) mirrors it. A step whose tool is absent is skipped cleanly, never
errored — keep new steps tolerant of a missing binary.
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

# What the status line, the progress caption and the screen reader say while a
# step runs. The engine sent this as @@STEP_BEGIN@@'s label until ONEUP-0072 retired
# that field: the window owns its wording now, keyed by step like TASKS. Carried
# across from the engine's LABEL map unchanged — the engine keeps its own copy for
# its terminal output, which stays English.
IN_PROGRESS = {
    "system": "Updating system packages",
    "flatpak": "Updating Flatpak apps",
    "firmware": "Checking firmware updates",
    "orphans": "Removing leftover packages",
    "cache": "Cleaning package cache",
}

