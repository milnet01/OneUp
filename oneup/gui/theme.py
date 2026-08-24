"""What the app looks like.

The stylesheet, the two colour palettes and their high-contrast counterparts,
the font-size derivation, the focus-cue derivation (ONEUP-0076) and the two
small helpers that exist only because of how the sheet paints — `card_inside`,
which nests the surface a `#RowBorder` needs, and `_app_icon`, which resolves
the icon the window and the tray both draw.

`_app_icon` lives here rather than in `app.py`, where
`docs/specs/ONEUP-0034-gui-modules.md` §4.2 places it: both `window.py` and
`tray.py` need it, and `app.py` imports `window.py`, so putting it there makes
those two import the starter and inverts the direction §4.3 rule 2 exists to
keep one-way.
"""
from __future__ import annotations

from string import Template

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFontInfo, QIcon
from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout

from .. import APP_ID
from . import paths

# ONEUP-0027 moved every colour a theme has to reach into the palette
# dictionaries below. Nothing here holds one any more except `_BLACK` and
# `_WHITE`, which are the ends of the sRGB range rather than colours anyone
# chose — INV-5's gate names them as its only exemption.

# ---------------------------------------------------------------------------
# The focus cue, DERIVED rather than authored (ONEUP-0076).
#
# A focused control's own fill becomes the smallest blend of its resting colour
# toward black or toward white — whichever direction reaches it at the lower
# blend fraction — that measures at least 3:1 against EVERY colour the control
# rests on. Its text is redrawn in whichever of black or white contrasts more
# with that fill.
#
# It is a derivation and not a palette entry because SC 2.4.13 compares the
# focused and unfocused states of the SAME pixels: what counts is the distance
# from each control's own rest colour, so one authored token passes on the card
# and fails on the accent button in the same theme. And it DARKENS, because
# lightening has a ceiling — pure white measures 2.63:1 against the Run button's
# top gradient stop, so no lighter shade of anything reaches 3:1 there.
#
# Every figure in `docs/specs/ONEUP-0076-ringless-focus-cue.md` §4.3 is this
# code's output. The 1% step and the round-to-nearest are what make those hexes
# reproducible: a binary search or a finer step prints different ones.
# ---------------------------------------------------------------------------
FOCUS_MIN = 3.0    # SC 2.4.13 — the focus indicator against the rest pixels
INK_MIN = 4.5      # SC 1.4.3 — the label against the fill behind it
_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)


class FocusDerivationError(RuntimeError):
    """No fill clears the threshold against every surface a control rests on.

    Raised rather than returning a best-effort colour: a fill that fails is a
    cue that is not there, and shipping one silently is the state ONEUP-0076
    exists to end. `apply_app_theme` catches it at the boundary and falls back.
    """


def _rgb(value) -> tuple[int, int, int]:
    if isinstance(value, tuple):
        return value
    h = value.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(c: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*c)


def _luminance(c: tuple[int, int, int]) -> float:
    def channel(v: int) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    """WCAG relative-contrast ratio between two colours, hex or (r, g, b)."""
    la, lb = _luminance(_rgb(a)), _luminance(_rgb(b))
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def _blend(c: tuple[int, int, int], t: float, target: int) -> tuple[int, int, int]:
    return tuple(round(x + t * (target - x)) for x in c)


def composite(over: str, alpha: float, under: str) -> str:
    """`over` at `alpha` painted on `under` — a translucent rest colour resolved
    to the hex actually rendered, so the check stays a pure computation with no
    screenshot. The warning banner's tint is the only rest surface that needs it."""
    o, u = _rgb(over), _rgb(under)
    return _hex(tuple(round(alpha * o[k] + (1 - alpha) * u[k]) for k in range(3)))


def _ink_for(fills) -> str:
    """Black or white, whichever contrasts more with the WORST of `fills`.

    Always clears 4.5:1: the two directions are equal at relative luminance
    0.1791, where both measure 4.58:1, so the larger of them is never below that.
    """
    black = min(contrast(f, _BLACK) for f in fills)
    white = min(contrast(f, _WHITE) for f in fills)
    return _hex(_BLACK if black >= white else _WHITE)


def derive_focus(source: str, surfaces, *, label: str = "",
                 threshold: float = FOCUS_MIN) -> tuple[str, str]:
    """The focus (fill, ink) pair for a control resting on `surfaces`.

    `source` is the colour blended FROM — the first surface the control's row in
    §4.2 names. `surfaces` is the whole set the result is tested against; the two
    are different jobs, and a control with several rest pixels has no derivation
    at all until the source is pinned. Both directions are tried from that one
    source: anchoring on one surface and never retrying the other direction is
    how a satisfiable set gets reported as unsatisfiable.
    """
    src = _rgb(source)
    rest = [_rgb(s) for s in surfaces]
    best = None
    for target in (_BLACK[0], _WHITE[0]):
        for step in range(1, 101):
            t = step / 100.0
            fill = _blend(src, t, target)
            if all(contrast(fill, s) >= threshold for s in rest):
                if best is None or t < best[0]:
                    best = (t, fill)
                break
    if best is None:
        raise FocusDerivationError(
            f"no focus fill reaches {threshold}:1 for {label or source} against "
            f"{', '.join(str(s) for s in surfaces)}")
    fill = _hex(best[1])
    return fill, _ink_for([fill])


def _samples(a, b, n: int = 101):
    """`n` points down a two-stop gradient, endpoints included."""
    ra, rb = _rgb(a), _rgb(b)
    return [tuple(round(ra[k] + (i / (n - 1)) * (rb[k] - ra[k])) for k in range(3))
            for i in range(n)]


def derive_focus_gradient(stops, *, label: str = "",
                          threshold: float = FOCUS_MIN) -> tuple[list[str], str]:
    """The focus pair for a gradient fill: ONE blend fraction, not one per stop.

    Blending toward a fixed target is affine in the source colour, so it commutes
    with the interpolation between the stops — one fraction applied to both gives
    exactly the colour that fraction would give anywhere in between. ONE direction
    serves the whole gradient, because a gradient straddling L = 0.1791 could
    otherwise want to darken at one end and lighten at the other; it is chosen the
    same way `derive_focus` chooses it, by the SMALLER blend fraction across both.
    Sampled at 101 points, since a gradient is governed by its worst pixel and not
    by its stops, and each focused sample is compared against the rest sample it
    replaces — SC 2.4.13 compares the same pixels, so the top of the button is not
    held against the bottom of its own previous state.
    """
    rest = _samples(*stops)
    best = None
    for target in (_BLACK[0], _WHITE[0]):
        for step in range(1, 101):
            t = step / 100.0
            if all(contrast(_blend(p, t, target), p) >= threshold for p in rest):
                if best is None or t < best[0]:
                    best = (t, target)
                break
    if best is None:
        raise FocusDerivationError(
            f"no focus fill reaches {threshold}:1 for the {label or 'gradient'} "
            f"{stops[0]} → {stops[1]} in either direction")
    t, target = best
    fills = [_hex(_blend(_rgb(s), t, target)) for s in stops]
    return fills, _ink_for(_samples(*fills))


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
# The two BUTTON gradient fills a focus cue is derived from are authored in each
# palette as stop PAIRS rather than as sheet strings, so the derivation and the
# sheet cannot drift apart (ONEUP-0027 §4.3). `accent` is the diagonal row-hover
# gradient — different geometry, its own stops — and is authored whole.
def _vgradient(stops) -> str:
    return ("qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            f"stop:0 {stops[0]}, stop:1 {stops[1]})")


def _rgba(colour: str, alpha: str) -> str:
    """`colour` as a QSS `rgba(...)` at `alpha`.

    The banner washes were decimal `rgba()` triples in the sheet, restating hues
    that are also palette tokens — the warning one being the very colour the
    focus derivation blends from. Writing them from the token is what stops a
    theme moving the wash and leaving the cue behind.
    """
    r, g, b = _rgb(colour)
    # The alpha is a STRING so the sheet reads exactly as it was authored:
    # formatting 0.20 as a float prints "0.2", which Qt treats the same but
    # which makes a byte-comparison against the pre-tokenised sheet noisy.
    return f"rgba({r},{g},{b},{alpha})"


# The warning banner's ground is a two-stop ALPHA wash, not a flat token, so a
# control inside it has no hex to blend from until the tint is composited over
# the surface beneath (`card`). §4.4 resolves it that way rather than by
# rendering, which is what keeps the whole check a pure computation.
WARN_TINT_ALPHAS = (0.20, 0.04)

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
/* QDialog is named alongside QMainWindow because a dialog does NOT inherit a
   background written for another selector: without this rule it paints Qt's own
   platform grey (#efefef) in BOTH themes, measured. That is a defect in its own
   right in dark mode, and it also puts every dialog control on a surface no
   palette controls — which is what the focus derivation blends from. */
QMainWindow, QDialog { background: $win; }

/* The painted ToggleSwitch can't be reached by a stylesheet, so the sheet hands
   it the contrast state as a Qt property. The explicit `false` is MANDATORY: a
   qproperty- assignment is not reverted when its rule stops matching, so without
   it a switch would stay stuck in high-contrast paint after HC is turned off.
   The focused tracks arrive the same way and for the same reason — no stylesheet
   colour rule reaches what paintEvent draws, and the switches are the largest
   group of controls that had no focus cue at all. */
ToggleSwitch {
    qproperty-highContrast: false;
    qproperty-focusTrackOn: $switchfocuson;
    qproperty-focusTrackOff: $switchfocusoff;
}

#Frame { border-radius: 16px; background: $accent; }
#Card  { border-radius: 14px; background: $card; }

QLabel#Header  { font-size: $fs_header; font-weight: 700; color: $header; }
QLabel#GroupHeading { font-size: $fs_med; font-weight: 700; color: $header; }
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
/* 24x24 is SC 2.5.8's floor for a POINTER target, width as well as height, and a
   stylesheet minimum is what puts it in one place: the controls it applies to are
   built in five different methods across three dialogs, and the sheet is set on
   the application, so a dialog this spec does not check still gets the floor.
   These are BOX dimensions, not text sizes — the no-hard-coded-px rule is about
   `font-size` and is not engaged. */
QToolButton#Disclose {
    color: $tdesc; background: transparent; border: none; padding: 0px;
    min-width: 24px; min-height: 24px;
}
/* The arrow has neither a fill nor a border, so the only pixels it can move on
   hover are its ink. Both colours are existing palette keys, so every theme
   ONEUP-0027 authors gets this for free. */
QToolButton#Disclose:hover { color: $tname; }
#RowDetails { background: transparent; }
QLabel#DetailList {
    color: $tdesc; background: $logbg; border-radius: 8px; padding: 6px 8px;
    font-family: "JetBrains Mono", "Fira Code", "Noto Sans Mono", monospace; font-size: $fs_small;
}
/* A 2px rest border, present focused or not — mechanism B. Only its COLOUR moves
   on focus, because recolouring the fill of a panel that holds its own content
   would recolour the content. 2px and not 1px because SC 2.4.13's area half asks
   for at least a 2px perimeter, which a 1px recolour does not reach. */
QScrollArea#DetailScroll { border: 2px solid $logbd; background: transparent; }
QLabel#SizeResult { color: $tname; font-size: $fs_body; font-weight: 600; }

QPushButton#RunBtn {
    font-size: $fs_med; font-weight: 700; color: $btnfg; border: none;
    border-radius: 11px; padding: 12px 18px; background: $btn_accent;
}
QPushButton#RunBtn:hover {
    background: $btn_accent_hov;
}
QPushButton#RunBtn:pressed {
    background: $btn_accent_press;
}
QPushButton#RunBtn:disabled { color: $disfg; background: $disbg; }

QPushButton#GhostBtn {
    color: $ghostfg; font-weight: 600; background: transparent;
    border: 1px solid $ghostbd; border-radius: 8px; padding: 8px 14px;
    min-width: 24px; min-height: 24px;
}
QPushButton#GhostBtn:hover { border-color: $ghosthov; color: $ghosthov; }
QPushButton#GhostBtn:checked { border-color: $ghosthov; color: $ghosthov; }
QPushButton#GhostBtn:disabled { color: $disfg; border-color: $disbg; }

/* Stop leaves the ghost outline and the transparent fill alone and takes the
   danger family's colour for its BORDER and its LABEL — the construction
   #RebootBanner uses, a red edge over an all-but-transparent ground, not
   #RestartBtn's solid red fill. A filled Stop would break the `card` derivation
   the focus cue rests on. It has an object name of its own because a restyled
   control still called #GhostBtn would be invisible to that derivation, which
   matches by name. */
QPushButton#StopBtn {
    color: $stopfg; font-weight: 600; background: transparent;
    border: 1px solid $stopfg; border-radius: 8px; padding: 8px 14px;
    min-width: 24px; min-height: 24px;
}
QPushButton#StopBtn:hover { border-color: $stophov; color: $stophov; }
QPushButton#StopBtn:disabled { color: $disfg; border-color: $disbg; }

QPushButton#LinkBtn {
    color: $linkfg; font-weight: 600; text-align: left;
    background: transparent; border: none; padding: 4px 2px;
    min-width: 24px; min-height: 24px;
}
QPushButton#LinkBtn:hover { color: $linkhov; }

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
    border: 2px solid $logbd; border-radius: 10px; padding: 6px;
    font-family: "JetBrains Mono", "Fira Code", "Noto Sans Mono", monospace; font-size: $fs_small;
}
/* The two dialog panels, on `win` rather than on the card. Same mechanism, same
   2px rest border; both were unnamed until ONEUP-0076 named them, which is what
   let two OneUp-built focusable widgets sit outside the sweep entirely. */
QScrollArea#RepoScroll { border: 2px solid $logbd; border-radius: 10px; background: transparent; }
QListWidget#RollbackList {
    background: $logbg; color: $logfg;
    border: 2px solid $logbd; border-radius: 10px; padding: 4px;
}

#RebootBanner {
    border: 1px solid $dangerbd; border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 $dangerwash1, stop:1 $dangerwash2);
}
QPushButton#RestartBtn {
    color: $btnfg; font-weight: 700; border: none; border-radius: 8px; padding: 7px 15px;
    min-width: 24px; min-height: 24px; background: $btn_danger;
}
QPushButton#RestartBtn:hover {
    background: $btn_danger_hov;
}

#InfoBanner {
    border: 1px solid $infobd2; border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 $infowash1, stop:1 $infowash2);
}
#WarnBanner {
    border: 1px solid $warnbd2; border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 $warnwash1, stop:1 $warnwash2);
}
QLabel#BannerText { color: $header; font-weight: 600; border: none; background: transparent; }
QPushButton#BannerBtn {
    color: $btnfg; font-weight: 700; border: none; border-radius: 8px; padding: 7px 15px;
    min-width: 24px; min-height: 24px; background: $btn_accent;
}
QPushButton#BannerBtn:hover {
    background: $btn_accent_hov;
}

QToolTip {
    background: $tip; color: $tipfg; border: 1px solid $tipbd;
    border-radius: 4px; padding: 4px 6px;
}

/* Keyboard focus — never a border or an outline ring (a deliberate design
   decision: an outline draws a square around our rounded buttons, because Qt
   ignores `outline-radius`, and a border resizes the widget). What moves is the
   control's own FILL, to a colour DERIVED from the one it replaces; the label
   is redrawn in whichever of black or white reads on it, and any border the
   control keeps takes that same ink, because a border left at its rest colour
   sits at about 1:1 against the new fill and disappears.
   Focus does NOT reuse the hover look: hover lightens, and pure white measures
   2.63:1 against the accent's top stop, so no lighter shade of anything reaches
   3:1 there at any saturation.
   Emitted LAST because :focus ties with :hover / :checked on specificity —
   placed earlier, a focused *checked* toggle would show no cue at all.
   One object name can rest on several surfaces, and each of those takes a
   selector QUALIFIED by the nearest container unique to it, never a rename:
   #Card contains every on-card case and is useless as a qualifier, while
   #RowCard, #RowDetails, #WarnBanner and #DialogButtons each contain exactly
   one surface. Qt resolves them by specificity, so the qualified rule wins. */
QPushButton#RunBtn:focus, QPushButton#BannerBtn:focus {
    background: $accentfocus; color: $accentfocusink;
}
QPushButton#RestartBtn:focus { background: $dangerfocus; color: $dangerfocusink; }

QPushButton#GhostBtn:focus, QPushButton#StopBtn:focus {
    background: $focusfill; color: $focusink; border-color: $focusink;
}
#RowCard QPushButton#GhostBtn:focus {
    background: $rowfocusfill; color: $rowfocusink; border-color: $rowfocusink;
}
#DialogButtons QPushButton#GhostBtn:focus {
    background: $winfocusfill; color: $winfocusink; border-color: $winfocusink;
}
#WarnBanner QPushButton#GhostBtn:focus {
    background: $warnfocusfill; color: $warnfocusink; border-color: $warnfocusink;
}

QPushButton#LinkBtn:focus { background: $focusfill; color: $focusink; }
#RowCard QPushButton#LinkBtn:focus, #RowDetails QPushButton#LinkBtn:focus {
    background: $rowfocusfill; color: $rowfocusink;
}
#WarnBanner QPushButton#LinkBtn:focus { background: $warnfocusfill; color: $warnfocusink; }

QToolButton#Disclose:focus { background: $rowfocusfill; color: $rowfocusink; }

QPlainTextEdit#Log:focus, QScrollArea#DetailScroll:focus,
QScrollArea#RepoScroll:focus, QListWidget#RollbackList:focus {
    border-color: $logbdfocus;
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
QLabel#Header, QLabel#GroupHeading, QLabel#TaskName, QLabel#SizeResult,
QLabel#BannerText { color: $text; }
QLabel#Tagline, QLabel#TaskDesc, QLabel#Status, QLabel#LastRun, QLabel#DetailList { color: $text; }
QLabel#LastRun[stale="true"] { color: $text; font-weight: 700; }
QLabel#Badge {
    background: $card; color: $text; border: 1px solid $border;
    padding: $badgepad; font-size: $fs_small; font-weight: 700;
}
QLabel#DetailList { background: $card; border: 1px solid $border; }
/* 2px, not the 1px this rule used to restate: the overlay is APPENDED, so a 1px
   border here would override the base sheet's 2px rest border and drop the focus
   cue below SC 2.4.13's area threshold in exactly the appearance mode that most
   needs it. #DetailScroll and the two dialog panels carried no overlay rule at
   all, so theirs are created rather than widened. */
QPlainTextEdit#Log { background: $card; color: $text; border: 2px solid $border; }
QScrollArea#DetailScroll { background: transparent; border: 2px solid $border; }
QScrollArea#RepoScroll { background: transparent; border: 2px solid $border; }
QListWidget#RollbackList { background: $card; color: $text; border: 2px solid $border; }
QToolButton#Disclose { color: $text; min-width: 24px; min-height: 24px; }
QToolButton#Disclose:hover { color: $btnhov; }
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
/* Stop takes the shape the overlay gives every ghost button, with the danger
   token in place of the ordinary border — the overlay never carries a literal
   red. Without this set the rename would leave the one control that interrupts a
   running update unstyled in the one appearance mode that exists for low-vision
   users. */
QPushButton#StopBtn { background: $card; color: $text; border: 2px solid $errbd; }
QPushButton#StopBtn:hover   { background: $btn; color: $btntext; border: 2px solid $focus; }
QPushButton#StopBtn:checked { background: $btn; color: $btntext; border: 2px solid $errbd; }
QPushButton#StopBtn:disabled { background: $card; color: $text; border: 2px dashed $errbd; }
QPushButton#LinkBtn { color: $link; text-decoration: underline; }
QPushButton#LinkBtn:hover { color: $text; }

#RebootBanner { background: $card; border: 2px solid $errbd; }
#InfoBanner   { background: $card; border: 2px solid $infobd; }
#WarnBanner   { background: $card; border: 2px solid $warnbd; }

/* Focus here is mechanism A too, and for the same reason — no outline ring (see
   the base sheet). The overlay's buttons do carry a rest border, but the pixels
   focus moves are the FILL: recolouring that border would not work anyway, since
   $border → $focus measures 1.43:1 dark and 1.87:1 light.
   The primary family's pair is DERIVED. #GhostBtn's is not: $card → $btnhov
   already measures 14.67:1 dark and 11.22:1 light, and deriving it would replace
   that with the smallest blend reaching 3:1 — roughly a fourfold cut. A pair that
   already passes is kept. Its border moves to $btntext rather than $focus, which
   is identical to $btnhov in both overlay palettes and so vanished into the fill.
   Every qualified selector the base sheet uses is restated, because a qualified
   base rule outranks a bare overlay one and would otherwise win. */
QPushButton#RunBtn:focus, QPushButton#RestartBtn:focus, QPushButton#BannerBtn:focus {
    background: $hcfocusfill; color: $hcfocusink; border: 2px solid $hcfocusink;
}
QPushButton#GhostBtn:focus, QPushButton#StopBtn:focus,
#RowCard QPushButton#GhostBtn:focus,
#DialogButtons QPushButton#GhostBtn:focus,
#WarnBanner QPushButton#GhostBtn:focus {
    background: $btnhov; color: $btntext; border: 2px solid $btntext;
}
/* The overlay's own link rule is the one that fails outright rather than merely
   weakening: it moves text alone, $link → $text, which is 1.65:1 dark and 1.87:1
   light. No recolour of that text can carry the cue, so it takes a fill. */
QPushButton#LinkBtn:focus, QToolButton#Disclose:focus,
#RowCard QPushButton#LinkBtn:focus, #RowDetails QPushButton#LinkBtn:focus,
#WarnBanner QPushButton#LinkBtn:focus {
    background: $btnhov; color: $btntext;
}
QPlainTextEdit#Log:focus, QScrollArea#DetailScroll:focus,
QScrollArea#RepoScroll:focus, QListWidget#RollbackList:focus {
    border-color: $hcbdfocus;
}
""")

# `ghostbd`, `linkfg`, `linkhov` and `ghosthov` carry values ONEUP-0076 §4.3
# MOVED. The old ones were measured and failed: the light link's #4aa3ff read
# 2.63:1 on its own card against a 4.5:1 bar, and the ghost button's rest border
# 1.62:1 against a 3:1 one. `stopfg` / `stophov` are new keys rather than sheet
# literals because _QSS is one template substituted with either palette, so a
# value that differs between them cannot be written into the sheet (ONEUP-0064).
_DARK = dict(
    win="#0f1216", card="#12161c", header="#f4f7fb", tag="#8b95a5",
    rowcard="#1a1f27", rowhov="#1e242e", tname="#eef2f8", tdesc="#a7b0be",
    badgebg="#20304a", badgefg="#cfe0ff", logbg="#0b0e12", logfg="#cdd6e2",
    logbd="#262d38", status="#c3ccd9", lastrun="#828d9d", amber="#f5a623", progbg="#0c0f13",
    ghostbd="#5e6570", ghostfg="#c7d0dd", ghosthov="#4aa3ff",
    linkfg="#4aa3ff", linkhov="#6fb6ff", stopfg="#e0553f", stophov="#ef6a55",
    disbg="#262b34", disfg="#aeb7c4",
    tip="#1a1f27", tipfg="#e9edf3", focus="#66b8ff",
    # The painted controls (ONEUP-0027 §4.3). A stylesheet cannot reach these:
    # ToggleSwitch.paintEvent and tray._tray_icon draw them with QPainter.
    switchon="#2ecc71", switchoff="#e74c3c",
    switchmark="#ffffff", switchknob="#ffffff",
    switchtrackrim="#ffffff", switchknobrim="#000000",
    trayidle="#888888", trayattn="#f5a623", trayrim="#ffffff", traymark="#3a2600",
    # The sheet's own former literals.
    btnfg="#ffffff", dangerbd="#e0553f", tipbd="#4aa3ff",
    # Gradients. The two BUTTON fills are authored as stop pairs and built by
    # _vgradient, so the sheet and the focus derivation cannot drift apart;
    # `accent` is the diagonal row-hover gradient and is authored whole.
    accent="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4aa3ff, stop:1 #22d3ee)",
    btn_accent_stops=("#4aa3ff", "#2f6fe0"),
    btn_accent_hov_stops=("#5cb0ff", "#3a7cf0"),
    btn_accent_press_stops=("#3d90ec", "#2560c8"),
    btn_danger_stops=("#ef6a55", "#d6412a"),
    btn_danger_hov_stops=("#f47c68", "#e04a32"),
    # Banner washes. Each is a hue the sheet composites at two alphas; the
    # warning one is also what the focus derivation blends from, so a theme that
    # moved one and not the other would light a focus cue the banner never wears.
    warntint="#e9b23f", infotint="#4aa3ff", infotint2="#22d3ee", dangertint="#e74c3c",
)
_LIGHT = dict(
    win="#eef1f5", card="#ffffff", header="#1b2027", tag="#5c6673",
    rowcard="#f4f6f9", rowhov="#eaeef3", tname="#1b2027", tdesc="#5c6673",
    badgebg="#dbe8ff", badgefg="#1f4e9c", logbg="#f6f8fa", logfg="#2a2f36",
    logbd="#d5dbe2", status="#3a424d", lastrun="#8a94a2", amber="#b5730a", progbg="#dfe4ea",
    ghostbd="#8f959c", ghostfg="#3a424d", ghosthov="#326dab",
    linkfg="#326dab", linkhov="#446f9c", stopfg="#d6412a", stophov="#b5321d",
    disbg="#d5dbe2", disfg="#9aa3ad",
    tip="#ffffff", tipfg="#1b2027", focus="#0b5fd0",
    switchon="#2ecc71", switchoff="#e74c3c",
    switchmark="#ffffff", switchknob="#ffffff",
    switchtrackrim="#ffffff", switchknobrim="#000000",
    trayidle="#888888", trayattn="#f5a623", trayrim="#ffffff", traymark="#3a2600",
    btnfg="#ffffff", dangerbd="#e0553f", tipbd="#4aa3ff",
    accent="qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4aa3ff, stop:1 #22d3ee)",
    btn_accent_stops=("#4aa3ff", "#2f6fe0"),
    btn_accent_hov_stops=("#5cb0ff", "#3a7cf0"),
    btn_accent_press_stops=("#3d90ec", "#2560c8"),
    btn_danger_stops=("#ef6a55", "#d6412a"),
    btn_danger_hov_stops=("#f47c68", "#e04a32"),
    warntint="#e9b23f", infotint="#4aa3ff", infotint2="#22d3ee", dangertint="#e74c3c",
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


def warn_tint(palette: dict) -> tuple[str, str]:
    """The warning banner's two ground colours, composited over the card."""
    return tuple(composite(palette["warntint"], a, palette["card"])
                 for a in WARN_TINT_ALPHAS)


def focus_keys(palette: dict) -> dict:
    """Every derived focus pair for one BASE palette.

    One entry per control family of `docs/specs/ONEUP-0076-ringless-focus-cue.md`
    §4.2, keyed by the surface the family rests on rather than by object name —
    four object names share the `card` pair, and one object name (`#LinkBtn`)
    spans three surfaces. The sheet resolves that with a qualified selector; this
    table resolves it by not caring what the control is called.
    """
    tint = warn_tint(palette)
    keys: dict[str, str] = {}
    for name, source, surfaces in (
        # `card` — the header and action-row ghost buttons, Stop, and the three
        # link buttons that sit directly on the card.
        ("focus", palette["card"], (palette["card"],)),
        # A row's two hover states: the disclosure arrow, every SettingsDialog
        # row's ghost button, `size_btn` in a detail panel, and the repository
        # dialog's Remove link. One fill has to clear 3:1 on BOTH, which is what
        # the disclosure paragraph in §4.2 exists to show — a fill derived from
        # `rowcard` alone measures 2.83:1 on `rowhov`.
        ("rowfocus", palette["rowcard"], (palette["rowcard"], palette["rowhov"])),
        # A dialog's own Close / Cancel, in its button strip rather than a row.
        ("winfocus", palette["win"], (palette["win"],)),
        # Inside the warning banner: `warn_copy_btn` and, since ONEUP-0064,
        # `retry_btn`.
        ("warnfocus", tint[0], tint),
    ):
        fill, ink = derive_focus(source, surfaces, label=name)
        keys[name + "fill"] = fill
        keys[name + "ink"] = ink
    # Mechanism B — the panels that hold their own scrolling content. Recolouring
    # every pixel would recolour the CONTENT, so what moves is an existing 2px
    # rest border. No ink: their text does not move.
    keys["logbdfocus"], _ = derive_focus(
        palette["logbd"], (palette["logbd"],), label="logbd")
    # The two gradient fills.
    for name, stops in (("accentfocus", palette["btn_accent_stops"]),
                        ("dangerfocus", palette["btn_danger_stops"])):
        fills, ink = derive_focus_gradient(stops, label=name)
        keys[name] = _vgradient(fills)
        keys[name + "ink"] = ink
    # The painted switch. Its fill carries a second constraint nothing else has:
    # the state shape is drawn ON the track, so the focused track must also clear
    # 3:1 against the white mark and the white knob, or the one colour-independent
    # cue this app has stops reading.
    # The surface set is BOTH white things drawn on the track — the state shape
    # and the knob — which ONEUP-0027 §4.3 splits into two themeable tokens. A
    # focused track measured against only one of them can swallow the other.
    for name, key in (("switchfocuson", "switchon"), ("switchfocusoff", "switchoff")):
        track = palette[key]
        keys[name], _ = derive_focus(
            track, (track, palette["switchmark"], palette["switchknob"]), label=name)
    return keys


def hc_focus_keys(hc: dict) -> dict:
    """The overlay's derived pairs.

    Only the primary button family and the mechanism-B borders are derived. The
    overlay's own `#GhostBtn` focus pair — `$card` → `$btnhov` — already measures
    14.67:1 dark and 11.22:1 light, and §4.1's floor keeps a pair that passes:
    "the smallest blend reaching 3:1" would WEAKEN those roughly fourfold, in the
    one appearance mode that exists for low-vision users.
    """
    fill, ink = derive_focus(hc["btn"], (hc["btn"],), label="hc primary")
    border, _ = derive_focus(hc["border"], (hc["border"],), label="hc panel border")
    return dict(hcfocusfill=fill, hcfocusink=ink, hcbdfocus=border)


def focus_report(dark: bool, high_contrast: bool = False) -> list[dict]:
    """Every colour pair the focus contract measures, for one theme.

    A pure computation — no rendering and no screenshot — which is what lets it
    run over a palette nobody has written yet, and what makes ONEUP-0076 §4.3 the
    output of a check rather than a table somebody transcribed. Each row carries
    the floor it is held to, so the caller asserts rather than re-deciding:
    3:1 for an indicator or a boundary (SC 2.4.13, SC 1.4.11), 4.5:1 for text
    (SC 1.4.3).

    A translucent rest colour is composited over the token beneath it first, and a
    gradient is sampled at 101 points down its length rather than at its two
    stops, because a gradient is governed by its worst pixel.
    """
    rows: list[dict] = []

    def add(control, kind, value, against, floor):
        rows.append(dict(control=control, kind=kind, value=value, against=against,
                         ratio=contrast(value, against), floor=floor))

    if high_contrast:
        hc = dict(_HC_DARK if dark else _HC_LIGHT)
        hc.update(hc_focus_keys(hc))
        add("primary family (HC)", "fill", hc["hcfocusfill"], hc["btn"], FOCUS_MIN)
        add("primary family (HC)", "ink", hc["hcfocusink"], hc["hcfocusfill"], INK_MIN)
        add("primary family (HC)", "border", hc["hcfocusink"], hc["hcfocusfill"], FOCUS_MIN)
        # The overlay's ghost pair is KEPT, not derived — it already clears 3:1 by
        # a wide margin, and §4.1's floor supplies a cue rather than replacing one.
        add("ghost family (HC)", "fill", hc["btnhov"], hc["card"], FOCUS_MIN)
        add("ghost family (HC)", "ink", hc["btntext"], hc["btnhov"], INK_MIN)
        add("ghost family (HC)", "border", hc["btntext"], hc["btnhov"], FOCUS_MIN)
        add("panel border (HC)", "border", hc["hcbdfocus"], hc["border"], FOCUS_MIN)
        return rows

    palette = dict(_DARK if dark else _LIGHT)
    keys = focus_keys(palette)
    tint = warn_tint(palette)
    # Mechanism A, the four surface families. The fill is measured against EVERY
    # surface the family rests on, which is the whole point of the rule: a fill
    # derived from `rowcard` alone measures 2.83:1 on `rowhov`.
    for control, prefix, surfaces in (
        ("ghost / link / stop on the card", "focus", (palette["card"],)),
        ("disclosure and row buttons", "rowfocus",
         (palette["rowcard"], palette["rowhov"])),
        ("dialog Close / Cancel", "winfocus", (palette["win"],)),
        ("warning-banner buttons", "warnfocus", tint),
    ):
        fill, ink = keys[prefix + "fill"], keys[prefix + "ink"]
        for s in surfaces:
            add(control, "fill", fill, s, FOCUS_MIN)
        add(control, "ink", ink, fill, INK_MIN)
        # A control that keeps a rest border while its fill moves gives that
        # border the INK. It cannot keep its rest colour: `ghostbd` and the fill
        # are the smallest blend in the same direction, so they land on the same
        # luminance and measure about 1:1 against each other.
        add(control, "border", ink, fill, FOCUS_MIN)
    for control, prefix, stops in (
            ("Run / banner button", "accentfocus", palette["btn_accent_stops"]),
            ("Restart button", "dangerfocus", palette["btn_danger_stops"])):
        fills, _ = derive_focus_gradient(stops)
        rest, focused = _samples(*stops), _samples(*fills)
        for r, f in zip(rest, focused, strict=True):
            add(control, "fill", _hex(f), _hex(r), FOCUS_MIN)
            add(control, "ink", keys[prefix + "ink"], _hex(f), INK_MIN)
    for control, key, track in (("switch, on", "switchfocuson", palette["switchon"]),
                                ("switch, off", "switchfocusoff", palette["switchoff"])):
        add(control, "fill", keys[key], track, FOCUS_MIN)
        # The one control whose fill is constrained by something drawn ON it: the
        # state shape and the knob are both white, and a track that swallowed them
        # would take the only colour-independent cue this app has with it.
        add(control, "state shape", palette["switchmark"], keys[key], FOCUS_MIN)
        add(control, "knob", palette["switchknob"], keys[key], FOCUS_MIN)
    add("log / detail / dialog panels", "border",
        keys["logbdfocus"], palette["logbd"], FOCUS_MIN)

    # The rest and hover colours this item MOVED, on every surface they land on
    # — not only `card`. An ink measured against the card alone reads 4.53:1 and
    # 3.89:1 on a row, so the surface set is what makes this assertion mean
    # anything. The ghost border is here rather than with the palette-wide sweep
    # because its `:hover` value shares one literal with the ink it moves with.
    surfaces = (palette["card"], palette["rowcard"], palette["rowhov"], *tint)
    for control, colour, floor in (("link button, rest", palette["linkfg"], INK_MIN),
                                   ("link button, hover", palette["linkhov"], INK_MIN),
                                   ("ghost button, hover ink", palette["ghosthov"], INK_MIN)):
        for s in surfaces:
            add(control, "text", colour, s, floor)
    add("ghost button, rest border", "border", palette["ghostbd"], palette["card"], FOCUS_MIN)
    add("ghost button, hover border", "border", palette["ghosthov"],
        palette["card"], FOCUS_MIN)
    add("stop button, rest label", "text", palette["stopfg"], palette["card"], INK_MIN)
    add("stop button, hover label", "text", palette["stophov"], palette["card"], INK_MIN)
    add("stop button, rest border", "border", palette["stopfg"], palette["card"], FOCUS_MIN)
    add("stop button, hover border", "border", palette["stophov"],
        palette["card"], FOCUS_MIN)
    # The disclosure carries meaning without being text, so 3:1 is its floor;
    # both values clear 4.5:1 as well.
    for control, colour in (("disclosure, rest", palette["tdesc"]),
                            ("disclosure, hover", palette["tname"])):
        for s in (palette["rowcard"], palette["rowhov"]):
            add(control, "text", colour, s, FOCUS_MIN)
    return rows


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


def derived_keys(palette: dict) -> dict:
    """Everything `build_theme` computes from an authored palette.

    Kept separate from `build_theme` so the contrast check can reach exactly the
    key set the sheet is substituted with — ONEUP-0027 INV-4's universe is the
    authored keys plus these, and a check that iterated only the authored ones
    would exempt the tokens no theme author ever sees.
    """
    keys = {
        # The button fills, built from the stop pairs the palette authors so the
        # sheet and the focus derivation cannot disagree about what is painted.
        "btn_accent": _vgradient(palette["btn_accent_stops"]),
        "btn_accent_hov": _vgradient(palette["btn_accent_hov_stops"]),
        "btn_accent_press": _vgradient(palette["btn_accent_press_stops"]),
        "btn_danger": _vgradient(palette["btn_danger_stops"]),
        "btn_danger_hov": _vgradient(palette["btn_danger_hov_stops"]),
        # The banner washes, at the alphas the sheet used to spell in decimal.
        "warnwash1": _rgba(palette["warntint"], "0.20"),
        "warnwash2": _rgba(palette["warntint"], "0.04"),
        "warnbd2": _rgba(palette["warntint"], "0.6"),
        "infowash1": _rgba(palette["infotint"], "0.20"),
        "infowash2": _rgba(palette["infotint2"], "0.05"),
        "infobd2": _rgba(palette["infotint"], "0.55"),
        "dangerwash1": _rgba(palette["dangertint"], "0.22"),
        "dangerwash2": _rgba(palette["dangertint"], "0.05"),
    }
    # The focus pairs are computed rather than authored, so a palette gets its
    # cue with no further work — and fails loudly if it cannot have one, rather
    # than shipping a fill that does not read.
    keys.update(focus_keys({**palette, **keys}))
    return keys


_CURRENT_PALETTE: dict = {}


def current_palette() -> dict:
    """The palette `apply_app_theme` last resolved — authored keys plus derived.

    A painted widget calls this; it never binds a colour at import, because a
    name bound with `from … import` keeps its own copy and would leave the
    control on the colour it had at start-up (ONEUP-0034 §4.4, applied to
    colours). Returns the BASE palette: the high-contrast overlay is never
    merged in, because the painted widgets need base keys under high contrast
    (`switchtrackrim`, `switchknobrim`) and the overlay's smaller key set
    collapses many base tokens onto a few. A painter that needs to know whether
    high contrast is on reads the `highContrast` property the sheet hands it.

    Falls back to the dark palette before the first `apply_app_theme` — a
    painter constructed in a test, or during start-up, gets colours rather than
    a KeyError.
    """
    return _CURRENT_PALETTE or {**_DARK, **derived_keys(_DARK)}


def build_theme(dark: bool, scale: float = 1.0, high_contrast: bool = False) -> str:
    palette = dict(_DARK if dark else _LIGHT)
    palette.update(derived_keys(palette))
    metrics = _font_metrics(scale)
    palette.update(metrics)
    qss = _QSS.substitute(palette)
    if high_contrast:
        hc = dict(_HC_DARK if dark else _HC_LIGHT)
        hc.update(hc_focus_keys(hc))
        hc.update(metrics)
        qss += _HC_QSS.substitute(hc)
    return qss


def apply_app_theme(app: QApplication):
    """Install the stylesheet for the desktop's colour scheme plus the user's
    accessibility preferences. The single place the QSS is applied — startup, a
    light/dark switch, and the two Settings controls all route through here, so a
    change takes effect live with no restart and no window rebuild."""
    s = QSettings("OneUp", "OneUp")
    dark = current_is_dark(app)
    scale = float(s.value("text_scale", 1.0, type=float))
    high_contrast = bool(s.value("high_contrast", False, type=bool))
    try:
        qss = build_theme(dark, scale=scale, high_contrast=high_contrast)
    except FocusDerivationError as exc:
        # A palette whose surfaces are too far apart for any one fill to clear
        # 3:1 against all of them has no focus cue, and half-applying it would
        # ship the state ONEUP-0076 exists to end. So the theme is not applied at
        # all and the app keeps running on the sheet already installed — which
        # preserves the user's text size and high-contrast choice by construction.
        # Dropping those would take away the one appearance mode that exists for
        # low-vision users, which is the failure this whole item exists to end.
        #
        # RETRYING WOULD BE A LIE TODAY: `build_theme` takes no theme argument, so
        # the built-in palette IS what just failed and a second call raises the
        # same error. The branch is unreachable in shipped code — the suite proves
        # both built-in palettes derive — and it exists for ONEUP-0027, which adds
        # user-selectable themes. When it does, the fallback here becomes a real
        # one: re-apply the built-in palette instead of the chosen theme.
        print(f"OneUp: unusable theme — {exc}; the theme was NOT applied")
        return
    global _CURRENT_PALETTE
    base = dict(_DARK if dark else _LIGHT)
    base.update(derived_keys(base))
    _CURRENT_PALETTE = base
    app.setStyleSheet(qss)
    # Setting the sheet re-polishes the widgets it styles, but a painter
    # reading `current_palette()` is not styled by it — nothing tells the
    # switch its colours moved. So repaint what the sheet cannot reach.
    for w in app.topLevelWidgets():
        w.update()


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
