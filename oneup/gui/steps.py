"""The five update steps, their keys, titles and order.

The run order both halves of the app share; the engine's own `LABEL` map (its
step module) mirrors it. A step whose tool is absent is skipped cleanly, never
errored — keep new steps tolerant of a missing binary.
"""
from __future__ import annotations

from PySide6.QtCore import QT_TRANSLATE_NOOP

# key, title, short description (ONEUP-0239 §3 item 13). Order = run order. Marked
# here and translated where shown, so the language can change without the table
# being rebuilt (ONEUP-0032 §4.3).
TASKS = [
    ("system", QT_TRANSLATE_NOOP("steps", "System packages"),
     QT_TRANSLATE_NOOP("steps", "Packages from your repositories")),
    ("flatpak", QT_TRANSLATE_NOOP("steps", "Flatpak apps"),
     QT_TRANSLATE_NOOP("steps", "Flatpak apps and runtimes")),
    ("firmware", QT_TRANSLATE_NOOP("steps", "Firmware"),
     QT_TRANSLATE_NOOP("steps", "Device firmware (fwupd)")),
    ("orphans", QT_TRANSLATE_NOOP("steps", "Leftover packages"),
     QT_TRANSLATE_NOOP("steps", "Dependencies nothing needs")),
    ("cache", QT_TRANSLATE_NOOP("steps", "Package cache"),
     QT_TRANSLATE_NOOP("steps", "Free up disk space")),
]

# What a Spotlight tile calls its step (ONEUP-0239 §4.3 Spotlight item 1). The full
# title stays the switch's accessible name.
SHORT_TITLES = {
    "system": QT_TRANSLATE_NOOP("steps", "System"),
    "flatpak": QT_TRANSLATE_NOOP("steps", "Flatpak"),
    "firmware": QT_TRANSLATE_NOOP("steps", "Firmware"),
    "orphans": QT_TRANSLATE_NOOP("steps", "Leftovers"),
    "cache": QT_TRANSLATE_NOOP("steps", "Cache"),
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


# What a package's state reads as, wherever a package is shown (ONEUP-0259 §4.7).
# Whole words, never a colour: two states always read differently. Keyed by the
# package model's states, plus `unchanged` — what a package reads as once its step
# has ended without installing or removing it.
STATE_WORDS = {
    "queued": QT_TRANSLATE_NOOP("steps", "waiting"),
    "downloading": QT_TRANSLATE_NOOP("steps", "downloading"),
    "downloaded": QT_TRANSLATE_NOOP("steps", "downloaded"),
    "installed": QT_TRANSLATE_NOOP("steps", "installed"),
    "removed": QT_TRANSLATE_NOOP("steps", "removed"),
    "unchanged": QT_TRANSLATE_NOOP("steps", "not changed"),
}
