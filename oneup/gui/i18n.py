"""Loading the translation catalogues (ONEUP-0032 §4.2).

The one thing that must happen before any translatable string is evaluated, so
every entry point calls `load` straight after building its application object.
2.0 ships English only, so on every desktop today `load` finds no catalogue and
installs nothing — which is correct, not a fault (`wording-and-translation.md` §7).

Three rules here are measurements, not taste (ONEUP-0032 §2.2):

- **Both catalogues or neither.** Qt's own `qtbase` catalogue alone flips the
  layout to right-to-left, which would mirror a window still full of English.
- **The translators are held for the process's lifetime**, in `_installed`. One
  that nothing references is garbage-collected and the application silently
  reverts to English.
- **Nothing here sets the layout direction.** Qt derives it from the installed
  catalogues, and an explicit call would override `-reverse`, making the
  right-to-left test pass while running left to right.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

from . import paths

_installed: list[QTranslator] = []
# Set by the first call, so a test can tell a path rendered its sentences after
# the catalogues were offered rather than before (ONEUP-0032 INV-9).
called = False


def load(ours_dir: Path | str | None = None, qt_dir: Path | str | None = None) -> bool:
    """Install OneUp's catalogue and Qt's for the system language, as a pair.

    The language is the system locale's, matched by Qt's own fallback chain
    (`de_AT` falls back to `de`). True when both were installed. The two
    directories are arguments so a test can point them somewhere harmless."""
    global called
    called = True
    app = QCoreApplication.instance()
    if app is None:
        return False
    ours_dir = str(paths.TRANSLATIONS_DIR if ours_dir is None else ours_dir)
    qt_dir = str(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
                 if qt_dir is None else qt_dir)
    ours, qt = QTranslator(), QTranslator()
    if not (ours.load(QLocale(), "oneup", "_", ours_dir)
            and qt.load(QLocale(), "qtbase", "_", qt_dir)):
        return False
    unload()
    if not app.installTranslator(ours):
        return False
    if not app.installTranslator(qt):
        app.removeTranslator(ours)
        return False
    _installed[:] = [ours, qt]
    return True


def unload() -> None:
    """Remove whatever `load` installed. Used by the tests; the application keeps
    its catalogues for its whole life."""
    app = QCoreApplication.instance()
    if app is not None:
        for translator in _installed:
            app.removeTranslator(translator)
    _installed.clear()
