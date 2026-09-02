"""The whole-palette contrast check (ONEUP-0027 §4.7).

A pure computation over a palette — linearise, weight, ratio — with no Qt, no
rendering and no screenshot. That is what lets it run over every theme in the
suite in negligible time, and what makes it cover a theme nobody has written
yet: a palette added later is checked by the same table, with nobody having to
remember to run anything.

The ratio arithmetic itself is `theme.contrast`, which ONEUP-0076 landed. This
module is the TABLE, and the table is the substance — a contrast function with
no table checks nothing.

Four things are true of every colour token the sheet is substituted with
(INV-4). It is the foreground of a checked pair, the background of one, named on
the decorative or exempt list with its reason, or declared measured elsewhere
naming the item and invariant that measure it. A token in none of the four fails
the check, which is what stops a colour being added and quietly escaping
measurement.
"""
from __future__ import annotations

import re

from .theme import (
    _DARK,
    _HC_DARK,
    _HC_LIGHT,
    _LIGHT,
    FOCUS_MIN,
    INK_MIN,
    contrast,
    derived_keys,
    hc_focus_keys,
    warn_tint,
)

# The two floors, named for what they mean rather than for their values.
TEXT = INK_MIN        # SC 1.4.3 — a foreground that renders text
MARK = FOCUS_MIN      # SC 1.4.11 / 2.4.13 — a foreground that carries meaning

_STOP_RE = re.compile(r"stop:\d+(?:\.\d+)? (#[0-9a-fA-F]{6})")

# A surface that is not a plain token: the warning banner's ground is an alpha
# wash, so a control inside it has no hex to measure against until the tint is
# composited over what is beneath it.
WARN_GROUND = "«warn ground»"


def surfaces(palette: dict, name: str) -> list[str]:
    """Every concrete colour a surface name stands for.

    A stop pair and a gradient string both expand to their stops, because a
    gradient is governed by its worst pixel rather than by its declaration.
    """
    if name == WARN_GROUND:
        return list(warn_tint(palette))
    value = palette[name]
    if isinstance(value, tuple):
        return list(value)
    if value.startswith("qlineargradient"):
        return _STOP_RE.findall(value)
    return [value]


def worst(palette: dict, fg: str, bg: str) -> tuple[float, str, str]:
    """The worst ratio between any rendered pair of `fg` and `bg`, and which."""
    pairs = [(f, b) for f in surfaces(palette, fg) for b in surfaces(palette, bg)]
    return min(((contrast(f, b), f, b) for f, b in pairs), key=lambda r: r[0])


# ---------------------------------------------------------------------------
# The pair table.
#
# Each row is (foreground, backgrounds, floor). Where a token renders on more
# than one surface EVERY surface is a row: the task labels are read on a hovered
# row as well as a resting one, and an ink measured only against the card reads
# 4.53:1 there and 3.89:1 on a hovered row. The surface set is what makes the
# row mean anything.
# ---------------------------------------------------------------------------
LINK_SURFACES = ("card", "rowcard", "rowhov", WARN_GROUND)

PAIRS: list[tuple[str, tuple[str, ...], float]] = [
    # --- 4.5:1, the foreground renders text ------------------------------
    ("header", ("win",), TEXT),
    ("tag", ("win",), TEXT),
    ("tname", ("rowcard", "rowhov"), TEXT),
    ("tdesc", ("rowcard", "rowhov"), TEXT),
    ("badgefg", ("badgebg",), TEXT),
    ("logfg", ("logbg",), TEXT),
    ("status", ("card", "progbg"), TEXT),
    ("lastrun", ("card", "win"), TEXT),
    ("ghostfg", ("card",), TEXT),
    # `amber` is also the ThemeNote colour, which sits on the dialog root (`win`),
    # not on a card — and that is the one place a theme failure is reported, so it
    # is the text that must not be the hardest to read. Measured on `card` alone it
    # passed in every theme and failed on `win` in all four light ones.
    ("amber", ("card", "win"), TEXT),
    ("tipfg", ("tip",), TEXT),
    # The Run button's label against both stops of its own fill, and the same
    # ink on the danger family's fill — one token, two gradients.
    ("btnfg", ("btn_accent_stops", "btn_danger_stops"), TEXT),
    # ONEUP-0064 and ONEUP-0076 made these sheet literals into tokens. Each is
    # checked on every surface it lands on rather than on `card` alone; *Retry*
    # put the ghost button's hover ink on the warning banner's tint.
    ("linkfg", LINK_SURFACES, TEXT),
    ("linkhov", LINK_SURFACES, TEXT),
    ("ghosthov", LINK_SURFACES, TEXT),
    # Stop's fill is transparent, so its label is read against the card and NOT
    # against the danger family's fill.
    ("stopfg", ("card",), TEXT),
    ("stophov", ("card",), TEXT),

    # --- 3:1, the foreground carries meaning without being text ----------
    ("switchon", ("rowcard", "rowhov", "switchmark", "switchknob"), MARK),
    ("switchoff", ("rowcard", "rowhov", "switchmark", "switchknob"), MARK),
    ("switchtrackrim", ("switchon", "switchoff"), MARK),
    ("switchknobrim", ("switchknob",), MARK),
    ("trayattn", ("win", "card"), MARK),
    ("trayidle", ("win", "card"), MARK),
    ("trayrim", ("trayattn", "trayidle"), MARK),
    ("traymark", ("trayattn",), MARK),
    ("focus", ("win", "card"), MARK),
    # Ghost buttons rest on a row and on the settings rows, not only on `card`:
    # `#RowCard QPushButton#GhostBtn` and `QComboBox#ThemeCombo` both put this
    # border on `rowcard`/`rowhov`. Measured on `card` alone it cleared 3:1 by a
    # hair in every theme and failed on the other two surfaces in all eight — the
    # §4.7 rule that every surface a token renders on is its own row.
    ("ghostbd", ("card", "rowcard", "rowhov"), MARK),
    # The danger family's banner border, and the two boundaries ONEUP-0076 left
    # as borders: the ghost button's hover border shares one token with its ink
    # above, so moving one moves both.
    ("dangerbd", ("win", "card"), MARK),
    ("ghosthov", ("card",), MARK),
    ("stopfg", ("card",), MARK),
    ("stophov", ("card",), MARK),
]

# ---------------------------------------------------------------------------
# The exceptions. An exception is DATA, not a comment: each entry carries the
# pair, the reason, and a roadmap id where the reason is "not yet fixed" rather
# than "not in scope". The ratio is measured and recorded like any other — held
# to no threshold, but computed, because a pair nobody computes cannot be shown
# to have drifted. INV-3 validates the shape before the check uses it.
# ---------------------------------------------------------------------------
DECORATIVE: list[tuple[str, tuple[str, ...], str, str | None]] = [
    ("logbd", ("logbg",), "The log panel is identified by its own background, which "
     "differs from `card` in both palettes; the border adds nothing that "
     "identifies it.", None),
    ("logbd", ("rowcard", "rowhov", "win"),
     "ONEUP-0076 mechanism B: the cue is the border's CHANGE of colour, which "
     "that item's INV-2 measures against `logbd` itself. How far the resting "
     "border stands out from what is behind it carries no state.", None),
    ("accent", ("win",), "The 2px gradient ring around the card (`#Frame`) is trim; "
     "it shows nothing the card it surrounds does not already show.", None),
    ("rowringtint", ("card",), "The task row's gradient ring is resting decoration "
     "on the card behind it; no state of the row is carried by it.", None),
    ("rowringtint2", ("card",), "The row ring's second stop, same reason as its "
     "first.", None),
    ("rowringhovtint", ("rowringtint",), "The row's hover ring restates a state the "
     "cursor already carries, and hover also changes `rowcard` to `rowhov`, so the "
     "ring is not the cue on its own.", None),
    ("rowringhovtint2", ("rowringtint2",), "The hover ring's second stop, same "
     "reason as its first.", None),
    ("btn_accent_hov_stops", ("btn_accent_stops",),
     "The primary button's hover fill restates a state the cursor already "
     "carries.", None),
    ("btn_accent_press_stops", ("btn_accent_stops",),
     "The primary button's pressed fill restates a state the press already "
     "carries.", None),
    ("btn_danger_hov_stops", ("btn_danger_stops",),
     "The danger button's hover fill restates a state the cursor already "
     "carries.", None),
    ("tipbd", ("tip",), "The tooltip is identified by being a tooltip — it floats "
     "above everything and is its own surface; the border is trim.", None),
    ("infotint", ("win", "card"), "The information banner's wash and border are "
     "decoration around text that carries the message; `header` on the wash is "
     "what has to read.", None),
    ("infotint2", ("win", "card"), "The information banner's second wash stop, same "
     "reason as its first.", None),
    ("warntint", ("win", "card"), "The warning banner's wash and border, same reason "
     "— `header` on the composited ground is what has to read.", None),
    ("dangertint", ("win", "card"), "The reboot banner's wash; `dangerbd` is the "
     "boundary that is measured, at 3:1.", None),
]

EXEMPT: list[tuple[str, tuple[str, ...], str, str | None]] = [
    ("disfg", ("disbg",), "WCAG 2.2 SC 1.4.3 puts inactive components outside its "
     "scope.", None),
]

# Declared measured elsewhere — naming the item and the invariant that measure
# them. These are the focus keys ONEUP-0076 derives per palette: their values
# are recomputed by that item's derivation rather than fixed, so they cannot sit
# in a table of fixed pairs. A declaration that names no measuring invariant is
# not one, and fails the check like an undeclared key.
MEASURED_ELSEWHERE: dict[str, str] = {
    key: "ONEUP-0076 INV-2/INV-3, via theme.focus_report()"
    for key in ("focusfill", "focusink", "rowfocusfill", "rowfocusink",
                "winfocusfill", "winfocusink", "warnfocusfill", "warnfocusink",
                "logbdfocus", "accentfocus", "accentfocusink", "dangerfocus",
                "dangerfocusink", "switchfocuson", "switchfocusoff")
}

# Derived RESTATEMENTS of a token that is already checked: `build_theme` builds
# each of these from the authored key named beside it, so measuring both would
# measure one colour twice. Covered by their source, and listed rather than
# skipped so that adding a derived key without deciding where it belongs still
# fails INV-4.
DERIVED_FROM: dict[str, str] = {
    "btn_accent": "btn_accent_stops",
    "btn_accent_hov": "btn_accent_hov_stops",
    "btn_accent_press": "btn_accent_press_stops",
    "btn_danger": "btn_danger_stops",
    "btn_danger_hov": "btn_danger_hov_stops",
    "warnwash1": "warntint", "warnwash2": "warntint", "warnbd2": "warntint",
    "infowash1": "infotint", "infobd2": "infotint", "infowash2": "infotint2",
    "dangerwash1": "dangertint", "dangerwash2": "dangertint",
    "rowring": "rowringtint", "rowringhov": "rowringhovtint",
}

# The font metrics are substituted into the same template and are not colours.
NON_COLOUR = ("fs_header", "fs_med", "fs_body", "fs_small", "badgepad", "progmin")


def palette_for(dark: bool) -> dict:
    """One base palette as the sheet sees it: authored keys plus derived."""
    base = dict(_DARK if dark else _LIGHT)
    base.update(derived_keys(base))
    return base


def check_pairs(palette: dict) -> list[dict]:
    """Every measured pair, each with the floor it is held to."""
    rows = []
    for fg, bgs, floor in PAIRS:
        for bg in bgs:
            ratio, a, b = worst(palette, fg, bg)
            rows.append(dict(fg=fg, bg=bg, ratio=ratio, floor=floor,
                             fg_hex=a, bg_hex=b, decorative=False))
    for fg, bgs, _reason, _rid in DECORATIVE + EXEMPT:
        for bg in bgs:
            ratio, a, b = worst(palette, fg, bg)
            rows.append(dict(fg=fg, bg=bg, ratio=ratio, floor=None,
                             fg_hex=a, bg_hex=b, decorative=True))
    return rows


def short(palette: dict) -> list[str]:
    """Every pair that fails its floor, rendered for a test's failure message."""
    return [f"{r['fg']} on {r['bg']} = {r['ratio']:.2f}:1 < {r['floor']}"
            for r in check_pairs(palette)
            if r["floor"] is not None and r["ratio"] + 1e-9 < r["floor"]]


def bad_exceptions() -> list[str]:
    """Exception entries whose SHAPE is incomplete (INV-3).

    An entry missing its pair, its reason, or — where the reason is a deferral —
    its roadmap id is itself a failure. This is what stops the exception list
    becoming the place failures go to be forgotten.
    """
    bad = []
    for fg, bgs, reason, rid in DECORATIVE + EXEMPT:
        if not fg or not bgs:
            bad.append(f"{fg or '?'} on {bgs or '?'}: no pair")
        if not reason or len(reason.split()) < 4:
            bad.append(f"{fg} on {bgs}: no reason")
        deferral = any(w in (reason or "").lower()
                       for w in ("not yet", "until", "pending", "for now"))
        if deferral and not rid:
            bad.append(f"{fg} on {bgs}: deferral with no roadmap id")
    return bad


def uncovered(palette: dict) -> list[str]:
    """Colour tokens the four coverage routes do not reach (INV-4)."""
    named: set[str] = (set(MEASURED_ELSEWHERE) | set(NON_COLOUR)
                       | set(DERIVED_FROM))
    for fg, bgs, _floor in PAIRS:
        named.add(fg)
        named.update(bgs)
    for fg, bgs, _reason, _rid in DECORATIVE + EXEMPT:
        named.add(fg)
        named.update(bgs)
    named.discard(WARN_GROUND)
    # WARN_GROUND is `warntint` composited over `card`, so naming it covers both.
    named.update(("warntint", "card"))
    missing = [k for k in palette if k not in named]
    # A derived key rides on its source, so a source that nothing checks leaves
    # BOTH uncovered — otherwise DERIVED_FROM would be a way to launder a token
    # into coverage it never earned.
    checked = named - set(DERIVED_FROM) - set(MEASURED_ELSEWHERE) - set(NON_COLOUR)
    missing += [f"{k} (via {src}, which nothing checks)"
                for k, src in DERIVED_FROM.items() if src not in checked]
    return sorted(missing)


def hc_short(theme) -> list[str]:
    """The high-contrast half (§4.7), for ONE THEME.

    Two different jobs. The overlay's OWN pairs are checked once per base, since
    there are only two overlays and every theme shares them. The surfaces the
    overlay does NOT reach — the painted switch and the tray icon, which take no
    QSS at all — are checked per theme with the overlay on, because a theme whose
    switch track is legible on its own window can still fail against the
    overlay's pure black or white. That combination is the only part of the
    high-contrast surface a theme can still break.

    Takes the THEME, not a base flag. With a flag the painted set was rebuilt from
    `_DARK`/`_LIGHT`, so the per-theme half ran the same two checks four times over
    and proved nothing about the six themes ONEUP-0027 added — while reporting
    green. `trayattn` alone carries seven distinct values across the eight themes.
    """
    hc = dict(_HC_DARK if theme.dark else _HC_LIGHT)
    hc.update(hc_focus_keys(hc))
    base = theme.palette
    out = []

    for fg, bgs, floor in (
            ("text", ("win", "card"), TEXT),
            ("btntext", ("btn",), TEXT),
            ("link", ("win", "card"), TEXT),
            ("border", ("win", "card"), MARK),
            ("focus", ("win", "card"), MARK),
            ("errbd", ("win", "card"), MARK),
            ("warnbd", ("win", "card"), MARK),
            ("infobd", ("win", "card"), MARK)):
        for bg in bgs:
            r = contrast(hc[fg], hc[bg])
            if r + 1e-9 < floor:
                out.append(f"overlay {fg} on {bg} = {r:.2f}:1 < {floor}")

    # The progress caption is centred and the bar is FULL when it carries its final
    # wording, so the caption is read on the CHUNK, not on the trough. With the
    # chunk painted in `text` that was 1.00:1 — white on white in HC dark. Nothing
    # measured it: the PAIRS row for `status` names the trough (`progbg`) and stops.
    for fg, bg, floor in (("text", "progchunk", TEXT),
                          ("progchunk", "card", MARK)):
        r = contrast(hc[fg], hc[bg])
        if r + 1e-9 < floor:
            out.append(f"overlay {fg} on {bg} = {r:.2f}:1 < {floor}")

    # The painted set, against the overlay's surfaces rather than the theme's.
    for fg, bgs, floor in (
            ("switchon", ("win", "card"), MARK),
            ("switchoff", ("win", "card"), MARK),
            ("trayattn", ("win", "card"), MARK),
            ("trayidle", ("win", "card"), MARK)):
        for bg in bgs:
            r = contrast(base[fg], hc[bg])
            if r + 1e-9 < floor:
                out.append(f"painted {fg} on overlay {bg} = {r:.2f}:1 < {floor}")
    # The switch's high-contrast rims exist only for this state, and they are
    # base tokens: the overlay cannot reach a widget that paints itself.
    for fg, bg, floor in (("switchtrackrim", "switchon", MARK),
                          ("switchtrackrim", "switchoff", MARK),
                          ("switchknobrim", "switchknob", MARK)):
        r = contrast(base[fg], base[bg])
        if r + 1e-9 < floor:
            out.append(f"painted {fg} on {bg} (overlay on) = {r:.2f}:1 < {floor}")
    return out


def report(dark: bool) -> str:
    """Everything the check knows about one palette, as text. Used by the suite's
    failure output and runnable by hand when authoring a palette."""
    palette = palette_for(dark)
    lines = [f"--- {'dark' if dark else 'light'} ---"]
    for r in sorted(check_pairs(palette), key=lambda r: r["ratio"]):
        flag = "decor" if r["decorative"] else f"{r['floor']}"
        lines.append(f"  {r['ratio']:6.2f}:1  {flag:>5}  "
                     f"{r['fg']} ({r['fg_hex']}) on {r['bg']} ({r['bg_hex']})")
    return "\n".join(lines)
