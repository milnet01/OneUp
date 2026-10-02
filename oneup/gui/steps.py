"""The five update steps, their keys, titles and order.

The run order both halves of the app share; the engine's own `LABEL` map (its
step module) mirrors it. A step whose tool is absent is skipped cleanly, never
errored — keep new steps tolerant of a missing binary.
"""
from __future__ import annotations

from PySide6.QtCore import QT_TRANSLATE_NOOP

# key, title, one-line description. Order = run order. Marked here and translated
# where shown, so the language can change without the table being rebuilt
# (ONEUP-0032 §4.3).
TASKS = [
    ("system", QT_TRANSLATE_NOOP("steps", "System packages"),
     QT_TRANSLATE_NOOP("steps", "Refresh repositories and upgrade openSUSE (zypper dup).")),
    ("flatpak", QT_TRANSLATE_NOOP("steps", "Flatpak apps"),
     QT_TRANSLATE_NOOP("steps", "Update Flatpak apps and remove unused runtimes.")),
    ("firmware", QT_TRANSLATE_NOOP("steps", "Firmware"),
     QT_TRANSLATE_NOOP("steps", "Check for and apply device firmware updates (fwupd).")),
    ("orphans", QT_TRANSLATE_NOOP("steps", "Leftover packages"),
     QT_TRANSLATE_NOOP("steps", "Remove leftover dependency packages nothing needs.")),
    ("cache", QT_TRANSLATE_NOOP("steps", "Package cache"),
     QT_TRANSLATE_NOOP("steps", "Clear the downloaded-package cache to free disk space.")),
]

# The two screen-reader names of a row's package list, written out per step. They
# were built from the title with a case change, which a language without case
# cannot do (ONEUP-0032 §4.5).
DETAIL_NAMES = {
    "system": (QT_TRANSLATE_NOOP("steps", "Packages that system packages will change"),
               QT_TRANSLATE_NOOP("steps", "List of packages that system packages will change")),
    "flatpak": (QT_TRANSLATE_NOOP("steps", "Packages that Flatpak apps will change"),
                QT_TRANSLATE_NOOP("steps", "List of packages that Flatpak apps will change")),
    "firmware": (QT_TRANSLATE_NOOP("steps", "Packages that firmware will change"),
                 QT_TRANSLATE_NOOP("steps", "List of packages that firmware will change")),
    "orphans": (QT_TRANSLATE_NOOP("steps", "Packages that leftover packages will change"),
                QT_TRANSLATE_NOOP("steps",
                                  "List of packages that leftover packages will change")),
    "cache": (QT_TRANSLATE_NOOP("steps", "Packages that package cache will change"),
              QT_TRANSLATE_NOOP("steps", "List of packages that package cache will change")),
}

# What the status line, the progress caption and the screen reader say while a
# step runs. The engine sent this as @@STEP_BEGIN@@'s label until ONEUP-0072 retired
# that field: the window owns its wording now, keyed by step like TASKS. Carried
# across from the engine's LABEL map unchanged — the engine keeps its own copy for
# its terminal output, which stays English.
IN_PROGRESS = {
    "system": QT_TRANSLATE_NOOP("steps", "Updating system packages"),
    "flatpak": QT_TRANSLATE_NOOP("steps", "Updating Flatpak apps"),
    "firmware": QT_TRANSLATE_NOOP("steps", "Checking firmware updates"),
    "orphans": QT_TRANSLATE_NOOP("steps", "Removing leftover packages"),
    "cache": QT_TRANSLATE_NOOP("steps", "Cleaning package cache"),
}

