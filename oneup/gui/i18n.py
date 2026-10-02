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

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QObject, QTranslator

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


def join_names(names) -> str:
    """Join a list of names a user reads — services, software sources — with the
    language's own separator. A literal ", " is English: a CJK catalogue joins with
    "、" (ONEUP-0032 §4.5), so the separator is itself a translatable string."""
    return QCoreApplication.translate("i18n", ", ", "separator between names in a list").join(names)


class _Counted(QObject):
    """Every sentence that carries a count, in one place.

    `self.tr(…, "", n)` is the only spelling `pyside6-lupdate` marks as a plural
    (measured 2026-10-02 on PySide6 6.11: `QCoreApplication.translate` with a count
    extracts as an ordinary message, and PySide6 has no `QT_TRANSLATE_N_NOOP`), so a
    language with several plural forms gets them only through a class method. Each
    entry is a lambda so only the one asked for is translated. `%n` is the count;
    any other value is a named field the caller fills with `.format`.
    """

    def phrase(self, key: str, n: int) -> str:
        return {
            "updates-partial": lambda: self.tr(
                "%n update(s) found, but some sources couldn't be checked.", "", n),
            "updates-available-run": lambda: self.tr(
                "%n update(s) available — turn on what you want and hit Run.", "", n),
            "updates-available": lambda: self.tr("%n update(s) available.", "", n),
            "updates-installed": lambda: self.tr("%n update(s) installed", "", n),
            "sources-set-aside": lambda: self.tr(" %n source(s) set aside: {names}.", "", n),
            "reboot-updates-installed": lambda: self.tr(
                "⚠  %n update(s) installed — restart so everything uses the latest "
                "libraries.", "", n),
            "services-restart": lambda: self.tr(
                "%n service(s) should restart to use the new libraries.", "", n),
            "services-restart-no-reboot": lambda: self.tr(
                "No reboot needed — but %n service(s) should restart to use the new "
                "libraries.", "", n),
            "services-session": lambda: self.tr(
                "⚠  %n service(s) still using the old libraries are part of your "
                "desktop session — restart the computer to finish.", "", n),
            "tray-waiting": lambda: self.tr("{app} — %n update(s) waiting", "", n),
            "tray-waiting-partial": lambda: self.tr(
                "{app} — %n update(s) waiting (some sources couldn't be checked)", "", n),
            "snapshots-thinned": lambda: self.tr("Thinned %n old snapshot(s).", "", n),
            "days-ago": lambda: self.tr("%n days ago", "", n),
            # No %n: the count picks the verb, not a number shown. Qt selects the
            # plural form from n all the same (ONEUP-0108 §4.2).
            "reboot-installed": lambda: self.tr("{items} were installed", "", n),
            "notify-installed": lambda: self.tr(
                "%n system package(s) installed.{skipped}", "", n),
            "notify-available": lambda: self.tr(
                "%n update(s) ready to install. Open OneUp to update.", "", n),
            "notify-partial-count": lambda: self.tr(
                "%n update(s) ready to install, and there may be more. {reasons} "
                "Open OneUp to update.", "", n),
        }[key]()


_counted: _Counted | None = None


def counted(key: str, n: int) -> str:
    """The sentence `key` for a count of `n`, in the plural form the language needs."""
    global _counted
    if _counted is None:
        _counted = _Counted()
    return _counted.phrase(key, n)
