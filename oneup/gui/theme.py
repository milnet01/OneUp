"""What the app looks like.

The stylesheet, the two colour palettes and their high-contrast counterparts,
the font-size derivation, and the two small helpers that exist only because of
how the sheet paints — `card_inside`, which nests the surface a `#RowBorder`
needs, and `_app_icon`, which resolves the icon the window and the tray both
draw.

`_app_icon` lives here rather than in `app.py`, where
`docs/specs/ONEUP-0034-gui-modules.md` §4.2 places it: both `window.py` and
`tray.py` need it, and `app.py` imports `window.py`, so putting it there makes
those two import the starter and inverts the direction §4.3 rule 2 exists to
keep one-way.
"""
from __future__ import annotations

from string import Template

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QFontInfo, QIcon
from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout

from .. import APP_ID
from . import paths

GREEN = QColor("#2ecc71")
RED = QColor("#e74c3c")

# ---------------------------------------------------------------------------
# Theme — a gradient-ringed "instrument panel" that follows the desktop's
# light/dark preference. The signature azure→cyan accent (echoing the app icon)
# stays constant; only the neutral surfaces swap between the two palettes below.
# The stylesheet is a $-template so the swap is a plain dict substitution with no
# brace-escaping. Selectors are keyed to object names so system dialogs keep the
# desktop's native look.
#
# Accessibility (ONEUP-0028): font sizes are DERIVED from the desktop's own
# default point size times the user's text-size setting — never hard-coded
# pixels — so OneUp follows the system font and can be enlarged from Settings.
# A high-contrast overlay (_HC_QSS) is appended after the base sheet when the
# user asks for it; Qt resolves equal-specificity conflicts the CSS way, so the
# later rule wins. Focus rings use `outline`, not `border`: a border changes the
# widget's box and makes buttons visibly resize when focused.
# ---------------------------------------------------------------------------
ACCENT = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4aa3ff, stop:1 #22d3ee)"
BTN_ACCENT = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4aa3ff, stop:1 #2f6fe0)"

# Text-size choices offered in Settings. The multiplier scales every font size
# plus the two metrics that BOUND text (badge padding, progress-bar height) —
# every other length is decoration that doesn't crowd at a larger size.
TEXT_SCALES = [("Normal", 1.0), ("Large", 1.2), ("Larger", 1.45)]

# Font sizes as multiples of the desktop's default point size. The ratios are the
# app's original pixel sizes over a 10 pt (~13.3 px at 96 dpi) default, so
# "Normal" reproduces the pre-ONEUP-0028 look to within a fraction of a point.
_FONT_SCALE = dict(fs_header=1.58, fs_med=1.05, fs_body=0.90, fs_small=0.83)

_QSS = Template(r"""
* { font-family: "Inter", "Noto Sans", "Segoe UI", "Cantarell", sans-serif; }
QMainWindow { background: $win; }

/* The painted ToggleSwitch can't be reached by a stylesheet, so the sheet hands
   it the contrast state as a Qt property. The explicit `false` is MANDATORY: a
   qproperty- assignment is not reverted when its rule stops matching, so without
   it a switch would stay stuck in high-contrast paint after HC is turned off. */
ToggleSwitch { qproperty-highContrast: false; }

#Frame { border-radius: 16px; background: $accent; }
#Card  { border-radius: 14px; background: $card; }

QLabel#Header  { font-size: $fs_header; font-weight: 700; color: $header; }
QLabel#Tagline { font-size: $fs_body; color: $tag; }

#RowBorder {
    border-radius: 12px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(74,163,255,0.65), stop:1 rgba(34,211,238,0.50));
}
#RowBorder:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(104,184,255,1.0), stop:1 rgba(58,228,250,0.85));
}
#RowCard { border-radius: 11px; background: $rowcard; }
#RowBorder:hover #RowCard { background: $rowhov; }
QLabel#TaskName { font-size: $fs_med; font-weight: 600; color: $tname; }
QLabel#TaskDesc { font-size: $fs_body; color: $tdesc; }
QLabel#Badge {
    background: $badgebg; color: $badgefg; border-radius: 9px;
    padding: $badgepad; font-size: $fs_small; font-weight: 600;
}
QToolButton#Disclose {
    background: transparent; border: none; padding: 0px;
}
#RowDetails { background: transparent; }
QLabel#DetailList {
    color: $tdesc; background: $logbg; border-radius: 8px; padding: 6px 8px;
    font-family: "JetBrains Mono", "Fira Code", "Noto Sans Mono", monospace; font-size: $fs_small;
}
QScrollArea#DetailScroll { border: none; background: transparent; }
QLabel#SizeResult { color: $tname; font-size: $fs_body; font-weight: 600; }

QPushButton#RunBtn {
    font-size: $fs_med; font-weight: 700; color: #ffffff; border: none;
    border-radius: 11px; padding: 12px 18px; background: $btn_accent;
}
QPushButton#RunBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5cb0ff, stop:1 #3a7cf0);
}
QPushButton#RunBtn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3d90ec, stop:1 #2560c8);
}
QPushButton#RunBtn:disabled { color: $disfg; background: $disbg; }

QPushButton#GhostBtn {
    color: $ghostfg; font-weight: 600; background: transparent;
    border: 1px solid $ghostbd; border-radius: 8px; padding: 8px 14px;
}
QPushButton#GhostBtn:hover { border-color: #4aa3ff; color: #4aa3ff; }
QPushButton#GhostBtn:checked { border-color: #4aa3ff; color: #4aa3ff; }
QPushButton#GhostBtn:disabled { color: $disfg; border-color: $disbg; }

QPushButton#LinkBtn {
    color: #4aa3ff; font-weight: 600; text-align: left;
    background: transparent; border: none; padding: 4px 2px;
}
QPushButton#LinkBtn:hover { color: #6fb6ff; }

QLabel#Status  { font-size: $fs_body; color: $status; }
QLabel#LastRun { font-size: $fs_body; color: $lastrun; }
QLabel#LastRun[stale="true"] { color: $amber; }

QProgressBar {
    border: none; border-radius: 9px; background: $progbg;
    min-height: $progmin; text-align: center; color: $status; font-size: $fs_body;
}
QProgressBar::chunk { border-radius: 9px; background: $accent; }

QPlainTextEdit#Log {
    background: $logbg; color: $logfg;
    border: 1px solid $logbd; border-radius: 10px; padding: 6px;
    font-family: "JetBrains Mono", "Fira Code", "Noto Sans Mono", monospace; font-size: $fs_small;
}

#RebootBanner {
    border: 1px solid #e0553f; border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(231,76,60,0.22), stop:1 rgba(231,76,60,0.05));
}
QPushButton#RestartBtn {
    color: #ffffff; font-weight: 700; border: none; border-radius: 8px; padding: 7px 15px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ef6a55, stop:1 #d6412a);
}
QPushButton#RestartBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f47c68, stop:1 #e04a32);
}

#InfoBanner {
    border: 1px solid rgba(74,163,255,0.55); border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(74,163,255,0.20), stop:1 rgba(34,211,238,0.05));
}
#WarnBanner {
    border: 1px solid rgba(233,178,63,0.6); border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(233,178,63,0.20), stop:1 rgba(233,178,63,0.04));
}
QLabel#BannerText { color: $header; font-weight: 600; border: none; background: transparent; }
QPushButton#BannerBtn {
    color: #ffffff; font-weight: 700; border: none; border-radius: 8px; padding: 7px 15px;
    background: $btn_accent;
}
QPushButton#BannerBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5cb0ff, stop:1 #3a7cf0);
}

QToolTip {
    background: $tip; color: $tipfg; border: 1px solid #4aa3ff;
    border-radius: 4px; padding: 4px 6px;
}

/* Keyboard focus reuses the HOVER look — a colour change, never a border or an
   outline ring (a deliberate design decision: an outline draws a square around
   our rounded buttons, because Qt ignores `outline-radius`, and a border resizes
   the widget). So a keyboard user gets exactly the cue a mouse user gets.
   Emitted LAST because :focus ties with :hover / :checked on specificity —
   placed earlier, a focused *checked* toggle would show no cue at all. */
QPushButton#RunBtn:focus {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5cb0ff, stop:1 #3a7cf0);
}
QPushButton#GhostBtn:focus { border-color: #4aa3ff; color: #4aa3ff; }
QPushButton#LinkBtn:focus  { color: #6fb6ff; }
QPushButton#BannerBtn:focus {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5cb0ff, stop:1 #3a7cf0);
}
QPushButton#RestartBtn:focus {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f47c68, stop:1 #e04a32);
}
""")

# High-contrast overlay, appended AFTER the base sheet (later rule wins). It has
# to restate every :hover / :checked / :pressed / [attr] variant the base defines
# — a bare `QPushButton#RunBtn` rule does NOT beat `QPushButton#RunBtn:hover`,
# because Qt follows CSS2 specificity and a pseudo-state selector outranks it.
# Miss one and high contrast leaks the gradient back on exactly the interaction a
# low-vision user performs.
_HC_QSS = Template(r"""
ToggleSwitch { qproperty-highContrast: true; }

QMainWindow, QDialog { background: $win; }
#Frame { background: $border; }
#Card  { background: $card; }
#RowBorder { background: $border; }
#RowCard   { background: $card; }
#RowBorder:hover { background: $focus; }
#RowBorder:hover #RowCard { background: $card; }

/* Catch-all FIRST, so a label nobody remembered to name still gets full-contrast
   text instead of the base sheet's dim grey — the exact failure HC exists to
   prevent, and the one that made the Settings rows unreadable (ONEUP-0088). The
   named rules below still win: an ID selector outranks a bare type selector. */
QLabel { color: $text; }
QLabel#Header, QLabel#TaskName, QLabel#SizeResult, QLabel#BannerText { color: $text; }
QLabel#Tagline, QLabel#TaskDesc, QLabel#Status, QLabel#LastRun, QLabel#DetailList { color: $text; }
QLabel#LastRun[stale="true"] { color: $text; font-weight: 700; }
QLabel#Badge {
    background: $card; color: $text; border: 1px solid $border;
    padding: $badgepad; font-size: $fs_small; font-weight: 700;
}
QLabel#DetailList { background: $card; border: 1px solid $border; }
QPlainTextEdit#Log { background: $card; color: $text; border: 1px solid $border; }
QProgressBar { background: $card; border: 1px solid $border; color: $text; }
QProgressBar::chunk { background: $text; }
QToolTip { background: $card; color: $text; border: 1px solid $border; }

QPushButton#RunBtn, QPushButton#RestartBtn, QPushButton#BannerBtn {
    background: $btn; color: $btntext; border: 2px solid $border; font-weight: 700;
}
QPushButton#RunBtn:hover, QPushButton#RunBtn:pressed,
QPushButton#RestartBtn:hover, QPushButton#BannerBtn:hover {
    background: $btnhov; color: $btntext; border: 2px solid $focus;
}
QPushButton#RunBtn:disabled { background: $card; color: $text; border: 2px dashed $border; }
QPushButton#GhostBtn { background: $card; color: $text; border: 2px solid $border; }
QPushButton#GhostBtn:hover   { background: $btn; color: $btntext; border: 2px solid $focus; }
QPushButton#GhostBtn:checked { background: $btn; color: $btntext; border: 2px solid $border; }
QPushButton#GhostBtn:disabled { background: $card; color: $text; border: 2px dashed $border; }
QPushButton#LinkBtn { color: $link; text-decoration: underline; }
QPushButton#LinkBtn:hover { color: $text; }

#RebootBanner { background: $card; border: 2px solid $errbd; }
#InfoBanner   { background: $card; border: 2px solid $infobd; }
#WarnBanner   { background: $card; border: 2px solid $warnbd; }

/* Focus reuses the hover look here too — no outline ring (see the base sheet). */
QPushButton#RunBtn:focus, QPushButton#RestartBtn:focus, QPushButton#BannerBtn:focus,
QPushButton#GhostBtn:focus {
    background: $btnhov; color: $btntext; border: 2px solid $focus;
}
QPushButton#LinkBtn:focus { color: $text; }
""")

_DARK = dict(
    win="#0f1216", card="#12161c", header="#f4f7fb", tag="#8b95a5",
    rowcard="#1a1f27", rowhov="#1e242e", tname="#eef2f8", tdesc="#a7b0be",
    badgebg="#20304a", badgefg="#cfe0ff", logbg="#0b0e12", logfg="#cdd6e2",
    logbd="#262d38", status="#c3ccd9", lastrun="#828d9d", amber="#f5a623", progbg="#0c0f13",
    ghostbd="#38414f", ghostfg="#c7d0dd", disbg="#262b34", disfg="#aeb7c4",
    tip="#1a1f27", tipfg="#e9edf3", focus="#66b8ff",
)
_LIGHT = dict(
    win="#eef1f5", card="#ffffff", header="#1b2027", tag="#5c6673",
    rowcard="#f4f6f9", rowhov="#eaeef3", tname="#1b2027", tdesc="#5c6673",
    badgebg="#dbe8ff", badgefg="#1f4e9c", logbg="#f6f8fa", logfg="#2a2f36",
    logbd="#d5dbe2", status="#3a424d", lastrun="#8a94a2", amber="#b5730a", progbg="#dfe4ea",
    ghostbd="#c4ccd6", ghostfg="#3a424d", disbg="#d5dbe2", disfg="#9aa3ad",
    tip="#ffffff", tipfg="#1b2027", focus="#0b5fd0",
)

# High-contrast palettes: pure black/white surfaces and text (21:1), one saturated
# focus/attention hue, and no dimmed secondary text — "dim" grey is the first thing
# that fails for a low-vision user, so HC deliberately has none.
_HC_DARK = dict(
    win="#000000", card="#000000", text="#ffffff", border="#ffffff",
    focus="#ffd400", btn="#ffffff", btntext="#000000", btnhov="#ffd400",
    link="#7fd4ff", errbd="#ff8080", warnbd="#ffd400", infobd="#7fd4ff",
)
_HC_LIGHT = dict(
    win="#ffffff", card="#ffffff", text="#000000", border="#000000",
    focus="#0000cc", btn="#000000", btntext="#ffffff", btnhov="#0000cc",
    link="#0000cc", errbd="#a00000", warnbd="#7a4f00", infobd="#00008b",
)


def _font_metrics(scale: float) -> dict:
    """Font sizes (in pt) and the two text-bounding metrics, for `scale`.

    Sizes are derived from the DESKTOP's default point size so OneUp follows the
    system font setting; `scale` is the user's own text-size choice on top. The
    clamp defends against Qt's "font was specified in pixels" sentinel — that is
    -1, which is TRUTHY, so `pointSizeF() or 10.0` would silently pass it through
    and emit negative point sizes that Qt discards, leaving the app unstyled.
    """
    base = QFontInfo(QApplication.font()).pointSizeF() if QApplication.instance() else 0.0
    if not 6.0 <= base <= 30.0:
        base = 10.0
    metrics = {k: f"{base * mult * scale:.1f}pt" for k, mult in _FONT_SCALE.items()}
    metrics["badgepad"] = f"{round(2 * scale)}px {round(9 * scale)}px"
    metrics["progmin"] = f"{round(20 * scale)}px"
    return metrics


def build_theme(dark: bool, scale: float = 1.0, high_contrast: bool = False) -> str:
    palette = dict(_DARK if dark else _LIGHT)
    palette["accent"] = ACCENT
    palette["btn_accent"] = BTN_ACCENT
    metrics = _font_metrics(scale)
    palette.update(metrics)
    qss = _QSS.substitute(palette)
    if high_contrast:
        hc = dict(_HC_DARK if dark else _HC_LIGHT)
        hc.update(metrics)
        qss += _HC_QSS.substitute(hc)
    return qss


def apply_app_theme(app: QApplication):
    """Install the stylesheet for the desktop's colour scheme plus the user's
    accessibility preferences. The single place the QSS is applied — startup, a
    light/dark switch, and the two Settings controls all route through here, so a
    change takes effect live with no restart and no window rebuild."""
    s = QSettings("OneUp", "OneUp")
    app.setStyleSheet(build_theme(
        current_is_dark(app),
        scale=float(s.value("text_scale", 1.0, type=float)),
        high_contrast=bool(s.value("high_contrast", False, type=bool))))


def current_is_dark(app: QApplication) -> bool:
    """Follow the desktop's colour scheme (Qt 6.5+); default to dark if unknown."""
    try:
        return app.styleHints().colorScheme() != Qt.ColorScheme.Light
    except Exception:  # noqa: BLE001 — any failure here just means "assume dark".
        return True


def card_inside(border: QFrame) -> QFrame:
    """Nest the #RowCard that paints a #RowBorder's interior, and return it.

    RowBorder is a BORDER, not a surface: the high-contrast sheet fills it solid
    ($border — white in HC dark) and only the RowCard child painting over it leaves
    the 1px edge showing. A row that uses RowBorder alone therefore renders as a
    solid white block with unreadable text (ONEUP-0088). Put every row's content
    inside the frame this returns, never in the RowBorder itself.
    """
    outer = QVBoxLayout(border)
    outer.setContentsMargins(1, 1, 1, 1)   # 1px gradient border
    outer.setSpacing(0)
    inner = QFrame()
    inner.setObjectName("RowCard")
    outer.addWidget(inner)
    return inner


def _app_icon() -> QIcon:
    """Prefer the installed theme icon (set once the .desktop/icon are in place,
    and inside a package); fall back to the bundled asset when running from a
    git checkout."""
    icon = QIcon.fromTheme(APP_ID)
    if icon.isNull():
        asset = paths.HERE / "data" / f"{APP_ID}.svg"
        if asset.exists():
            icon = QIcon(str(asset))
    return icon
