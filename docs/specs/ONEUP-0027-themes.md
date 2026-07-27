# ONEUP-0027 — selectable themes

**Status:** Reviewed
**Kind:** feature
**Roadmap:** ONEUP-0027
**Branch:** v2
**Verified at:** `e7d3718` — every contrast figure below was computed against this tree,
not recalled.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** Settings gains a picker offering **Follow system** and eight themes,
each a complete palette that a contrast check in the suite has to pass — including the two
palettes that ship today, which do not all pass it now.

**`docs/standards/ui-and-accessibility.md` §7 already owns what a theme is** and what it
must pass. This spec does not re-argue any of it. What it adds is the part §7 leaves to
this item: the check itself, the tokens the painted widgets need, the picker, and a
decision on every pair the check turns out to fail.

## 1. Goal

A user picks a theme in Settings and the whole application takes it at once — window,
dialogs, message boxes, the on/off switches and the tray badge — with no restart. The
choice survives a restart, and a stored value the application does not recognise starts in
**Follow system** rather than failing. No theme can ship that a user cannot read: the check
that decides that is a computation over the palette, so it covers themes added later
without anyone remembering to run it.

## 2. Background

Theming today is one stylesheet, built once and set on the `QApplication`. `build_theme`
substitutes either `_DARK` or `_LIGHT` into the `_QSS` template, `apply_app_theme` installs
the result, and `main()` re-applies it on `colorSchemeChanged`. That machinery is sound and
this spec keeps it — `docs/standards/ui-and-accessibility.md` §6.1 is why dialogs need no
work of their own: the sheet lives on the application, so every `QDialog` and `QMessageBox`
inherits it.

**Two things are missing, and both were measured before this spec was written.**

**The theme reaches only the `$tokens`, and a great many colours are not tokens.** Two
places, both measured at `e7d3718`.

A stylesheet cannot touch a widget that paints itself, and two of them do.
`ToggleSwitch.paintEvent` fills its track from the module constants `GREEN` and `RED`,
draws the state shape and the knob with a literal `QColor("#ffffff")`, and rims them with
`#ffffff` and `#000000` under high contrast. `Updater._tray_icon` paints the attention disc
`TRAY_ATTENTION_COLOR`, its rim `#ffffff`, its `!` `#3a2600`, and — only when the app icon
cannot be loaded at all — a plain `#888888` disc in place of it. Ten colours, and the ones
that matter are the surfaces carrying state meaning: two of the three
cue pairings `docs/standards/ui-and-accessibility.md` §3 lists are painted here, the third
being an ordinary label.

**And the stylesheet itself is not all tokens.** `_QSS` carries **thirty** hex literals,
twelve of them distinct, that no substitution touches: the Run button's white label and its
hover and pressed gradients, the link button's hover, the danger-button family, and
`#4aa3ff` — the accent's own first stop — written out directly in eight places. A theme
that set `accent` and left those would recolour the application around a button that stayed
azure.

Between them that is the whole of what a theme would fail to reach: the two controls that
show state, and the one button the user presses.

**The check §7 requires does not exist, and the palettes shipping today do not all pass
it.** Computed at `e7d3718` with the WCAG 2.2 formula — relative luminance
`0.2126R + 0.7152G + 0.0722B` over linearised sRGB, ratio `(L1 + 0.05) / (L2 + 0.05)`
(*Source:* <https://www.w3.org/TR/WCAG20-TECHS/G18.html>):

| Pair | Light | Dark | Needs |
| --- | --- | --- | --- |
| `lastrun` on `card` | **3.07:1** | 5.40:1 | 4.5:1 |
| `lastrun` on `win` | **2.71:1** | 5.58:1 | 4.5:1 |
| `amber` on `card` | **3.87:1** | 8.95:1 | 4.5:1 |
| `ghostbd` on `card` | **1.62:1** | **1.76:1** | 3:1 |
| `logbd` on `logbg` | **1.31:1** | **1.40:1** | 3:1 |
| `disfg` on `disbg` | **1.83:1** | 7.02:1 | 4.5:1 |
| switch track "on" vs its state shape | **2.10:1** | **2.10:1** | 3:1 |
| switch track "on" vs `rowcard` | **1.94:1** | 7.87:1 | 3:1 |
| accent, both gradient stops, vs `win` | **2.32:1**, **1.60:1** | 7.13:1, 10.39:1 | 3:1 |

§7 already knew about `lastrun` and says it "must not be discovered by the check and
quietly ignored". The rest are found here for the first time, and the same rule applies to
each: §4.8 decides every one of them by name.

The switch row is the one that matters most. The white bar-and-circle **is** the
colour-blind cue, and at 2.10:1 on the green track it is the weakest thing on screen
carrying meaning.

## 3. Scope decisions (agreed with the user)

| Decision | Who, when | Consequence |
| --- | --- | --- |
| **Eight** themes to start with | the user, 2026-07-27 | §4.2 lists them; the count is a starting point, not a ceiling — §4.1's contract is what makes a ninth cheap |
| **Follow system** is the initial default | the user, 2026-07-27 | §4.5; it is not a theme but a mode, and it is what an unrecognised stored value falls back to |
| The picker lives in **Settings** | the user, 2026-07-27 | §4.6 |
| Themes are **required for 2.0**, not optional | the user, 2026-07-26 | `docs/design/oneup-2.0.md` §1. `docs/standards/ui-and-accessibility.md` §7 owns the consequence: a theme that cannot pass is not shipped, optional or not |
| The on/off switch form is not reconsidered | the user, standing | `docs/standards/ui-and-accessibility.md` §3; a theme recolours the switch and may not replace it |

**The eight names in §4.2 are this spec's proposal, not the user's.** They can be changed
without touching anything else here — a name is a label and an id, and §4.1's contract is
indifferent to both.

### 3.1 What this spec does not decide

What a theme *is*, that it supplies colours and never structure, that every key is
supplied, the two contrast thresholds, that colour-never-alone is per-theme, and that high
contrast stays an overlay — all six are `docs/standards/ui-and-accessibility.md` §7. This
spec obeys them and discharges the two jobs §7 hands it: write the check, and settle the
`lastrun` case.

The ringless focus treatment is **ONEUP-0064**'s to pick, and `docs/design/oneup-2.0.md`
§5.2 lands that item **before** this one. So by the time this work starts the treatment
exists and its measurement is in the suite — `docs/standards/ui-and-accessibility.md` §5.4
and the design's ONEUP-0064 row are where that obligation is written. This spec inherits
the gate and owes it six more palettes; it does not choose the treatment, and it does not
carry the gap as an exception.

**The redesign landing first has a wider consequence.** Every figure in §2 was measured
before it. ONEUP-0064 may move any of those colours, so §4.8 states rules rather than fixed
edits and the check re-measures when this item starts.

## 4. Design

### 4.1 What a theme is here

A theme is `(id, label, base, palette)`. **`base`** is `dark` or `light` — §4.2's Base
column — and it is what still decides which of the two high-contrast overlays is appended
and what Follow system matches against; nothing else reads it.
**The reference set is `midnight`'s key set** —
not a list written down here, which would rot the first time a token was added. Every other
theme carries exactly those keys, and §4.3 says what the set has to grow to cover.
`docs/standards/ui-and-accessibility.md` §7 wants a missing key to raise at substitution
rather than half-apply, and that stays true — the reference-set assertion in §5 fails first
and more usefully.

The high-contrast overlay is **not** part of the reference set. §7 keeps it an overlay
rather than a theme, so there are two of them — one dark, one light — shared by all eight,
and they carry their own smaller key set. §4.7 says what checking them means.

The `id` is a lowercase slug, is what gets stored, and never changes. The `label` is what
Settings shows and is the only translatable part (ONEUP-0032).

### 4.2 The eight

Four dark and four light, because the picker's job is to be visibly different eight times
over. The two shipped palettes are two of the eight, so six are authored rather than eight,
and **Follow system chooses between `midnight` and `daylight`** exactly as light/dark works
today — nothing changes for a user who never opens the picker.

| id | Label | Base | Character |
| --- | --- | --- | --- |
| `midnight` | Midnight | dark | today's `_DARK`, unchanged but for §4.8's fixes |
| `carbon` | Carbon | dark | neutral greys, no blue cast |
| `forest` | Forest | dark | green-tinted surfaces |
| `plum` | Plum | dark | violet-tinted surfaces |
| `daylight` | Daylight | light | today's `_LIGHT`, unchanged but for §4.8's fixes |
| `paper` | Paper | light | warm off-white, low blue |
| `sky` | Sky | light | cool blue-tinted light |
| `sand` | Sand | light | warm sand, higher warmth than Paper |

**A named theme is one palette, not a light/dark pair.** Choosing one means choosing not to
follow the desktop; that is what Follow system is for. The alternative — eight themes each
with two variants — is §9.

**The accent moves into the palette.** `ACCENT` and `BTN_ACCENT` are constant across
light and dark today, and if they stayed constant across eight themes the most visible
surface in the application would be identical in all of them. `midnight` and `daylight`
keep today's azure→cyan, so the signature is preserved where it is the default.

### 4.3 The painted tokens

The palette gains a key for every colour §2 found outside it, and §4.7 places every one of
them. The ten below are read by a `paintEvent` or an icon painter; the two accents are read
by the stylesheet, and are here because `build_theme` injects them rather than taking them
from the palette.

| Token | Replaces | Painted by |
| --- | --- | --- |
| `switchon` | `GREEN` | `ToggleSwitch.paintEvent` — track when on |
| `switchoff` | `RED` | `ToggleSwitch.paintEvent` — track when off |
| `switchmark` | the `#ffffff` pen in `_paint_state_shape` | the bar-and-circle state cue |
| `switchknob` | the `#ffffff` brush in `paintEvent` | the knob |
| `switchtrackrim` | the `#ffffff` pen under high contrast | the HC outline around the track |
| `switchknobrim` | the `#000000` pen under high contrast | the HC rim around the knob |
| `trayidle` | `#888888` | `Updater._tray_icon` — the plain disc drawn **only when the app icon cannot be loaded** |
| `trayattn` | `TRAY_ATTENTION_COLOR` | the amber "updates waiting" disc |
| `trayrim` | the `#ffffff` pen | the disc's rim |
| `traymark` | `#3a2600` | the `!` inside the disc |
| `accent`, `btn_accent` | `ACCENT`, `BTN_ACCENT` | the gradient on a hovered row, and the fill of the Run button |

**The two high-contrast rims are two tokens, not one.** They are different colours today
and for a reason: the white pen outlines the track against a coloured fill, the black pen
rims the knob against the white knob beneath it. One token would paint both the same, and
against a light `switchknob` the knob's rim would vanish under exactly the setting it
exists to serve.

**Only the tray's badge is themeable, and `trayidle` is a fallback.** `_tray_icon` composes
the app icon and paints an amber badge over it; the plain grey disc is drawn only when
`_app_icon()` returns nothing. So the idle tray icon on a working install is the app's own
SVG, which no theme touches and none should. `trayidle` is a token because it is a literal,
not because a user will often see it — and INV-8 tests the badge for that reason.

**The stylesheet's own literals become tokens too.** §2 counted thirty of them. `#4aa3ff`
is `accent`; the rest fall into four groups, each named for what it colours rather than
what colour it is: the primary button's **label**, its **hover** and **pressed** fills, the
link button's **hover**, and the **danger** family the restart button and reboot banner
share. Naming them is the implementer's, bounded by two things — INV-5 leaves no literal
behind, and INV-4 gives every resulting token a home in §4.7.

`GREEN`, `RED` and `TRAY_ATTENTION_COLOR` stop being module constants. Nothing else reads
them — `GREEN`/`RED` have one call site between them, in `ToggleSwitch.paintEvent`.
`ACCENT` and `BTN_ACCENT` stop being module constants too: `build_theme` injects them into
the palette today, which is the seam this widens.

### 4.4 How a painted widget gets its colours

`oneup/gui/theme.py` gains one function, `current_palette()`, returning the palette
`apply_app_theme` last resolved. A painter calls it; nothing binds a colour at import.

This is `docs/specs/ONEUP-0034-gui-modules.md` §4.4's rule applied to a second kind of
value, and for the same reason: a name bound with `from … import` keeps its own copy, so a
theme change would leave the binding on the old colour and the switch would stay the colour
it was at start-up. A function has no binding to go stale.

**`build_theme` takes the theme, not `dark: bool`.** Today it takes a boolean and picks
`_DARK` or `_LIGHT` itself; with eight palettes chosen by id there is nothing for a boolean
to select. It keeps `scale` and `high_contrast`, and it picks the overlay from the theme's
`base` — §4.1's fourth field, which exists for exactly this.

`apply_app_theme` stays the single entry point, and it does four things in order: resolve
the id to a theme, store its palette where `current_palette()` will find it, set the
stylesheet, and **repaint what the stylesheet does not repaint by itself.**

That last step is not decoration. Setting the application stylesheet re-polishes the
widgets it styles, but a painter reading `current_palette()` is not styled by it — nothing
tells the switch its colours moved. So `apply_app_theme` calls `update()` on every
top-level widget, which reaches the switches through their parents, and rebuilds the tray
icon: `Updater._tray_icon` builds a `QIcon` and the result is handed to `setIcon` at two
call sites only, neither of which fires on a theme change. Verified at `e7d3718`. A window
holding a tray icon rebuilds it when the theme changes; a window with no tray does nothing.

### 4.5 The preference

Stored in `QSettings("OneUp", "OneUp")` under `theme`, as the **id**, defaulting to
`system`.

**The default argument is not the fallback.** Qt returns whatever is stored, valid or not —
a `theme` key holding `Forrest`, or an id from a later version, comes back verbatim
(*Source:* <https://doc.qt.io/qt-6/qsettings.html>). So the value is looked up in the theme
table and an unknown id resolves to `system`. The stored value is **not** rewritten: a user
who downgrades, starts once, and upgrades again gets their theme back.

Follow system keeps today's behaviour exactly — `current_is_dark(app)` chooses `midnight`
or `daylight`, and `colorSchemeChanged` re-applies. Under a named theme that signal
changes nothing, because there is nothing left to follow.

### 4.6 The picker

A combo box, built by the window and re-parented into `SettingsDialog` alongside the text
size and contrast controls — the pattern that dialog already uses, and the reason
`docs/specs/ONEUP-0034-gui-modules.md` §4.2 calls it a host rather than an owner. It lists
**Follow system** first, then the eight in §4.2's order. Choosing an entry applies it
immediately: there is no OK button to press, matching every other control in that dialog.

The control carries an accessible name like every other
(`docs/standards/ui-and-accessibility.md` §2), and the labels are the only strings this
item adds.

### 4.7 The check

A pure computation over a palette: linearise, weight, ratio. No Qt, no rendering, no
screenshot — which is what lets it run over every theme in the suite in negligible time and
what makes it cover a theme nobody has written yet.

It is driven by a **table of pairs**, and that table is the substance of the check — a
contrast function with no table checks nothing. Each row names a foreground token, the
background token it is drawn on, and its threshold. **Where a token renders on more than
one surface, every surface is a row**: the task labels are read on a hovered row as well as
a resting one, and the progress bar's text is read on the bar, not on the card.

- **4.5:1**, the foreground renders text — `header` on `win`; `tag` on `win`; `tname` and
  `tdesc` on `rowcard` and on `rowhov`; `badgefg` on `badgebg`; `logfg` on `logbg`;
  `status`, `lastrun`, `ghostfg` and `amber` on `card`; `lastrun` on `win`; `status` on
  `progbg`; `tipfg` on `tip`; the Run button's label on `btn_accent`, against both gradient
  stops; the link button's text on `card` in both its rest and hover colours; and the
  danger family's button label on its own fill.
- **3:1**, the foreground carries meaning without being text — `switchon` and `switchoff`
  against `rowcard`, against `rowhov`, and against `switchmark` and `switchknob`;
  `switchtrackrim` against `switchon` and `switchoff`; `switchknobrim` against
  `switchknob`; `trayattn` and `trayidle` against both window colours; `trayrim` against
  `trayattn` and `trayidle`; `traymark` against `trayattn`; `focus` against `win` and
  `card`; `ghostbd` against `card`; and the danger family's banner borders against `win`
  and `card`.
- **Declared decorative**, measured by nothing and each carrying its reason — `logbd` on
  `logbg`, `accent` on `win`, and the primary button's hover and pressed fills, which
  restate a state the cursor and the press already carry.
- **Declared exempt** — `disfg` on `disbg`. WCAG 2.2 SC 1.4.3 puts inactive components
  outside its scope.

**Every token in the reference set is covered**, in one of three ways: it is the foreground
of a checked pair, it is the background of one, or it is named on the decorative or exempt
list. A surface like `card` or `switchknob` is covered by being something else's
background; it needs no row of its own. That is INV-4, and it is what stops a token being
added and quietly escaping measurement. §4.8's decisions are decisions about pairs these
lists contain, never about pairs the check does not compute.

**High contrast is checked separately, and it is not eight more runs of the same thing.**
The overlay is appended after the base sheet and overrides nearly every selector the base
styles, so with it on most surfaces come from the shared overlay rather than from the
theme — and the overlay carries its own smaller key set. Three of its keys are also base
keys (`win`, `card`, `focus`); the rest — `text`, `border`, `btn`, `btntext` and their
siblings — collapse many base tokens onto a few, so a base pair like `header` on `win` has
no counterpart with the overlay on. Two consequences, and the check does both:

- The overlay's own pairs are checked **once per base**, dark and light, because there are
  only two overlays and all eight themes share them.
- The surfaces the overlay does **not** reach are checked **per theme, with the overlay
  on**. That is the painted set — the switch and the tray icon take no QSS at all — so a
  theme whose switch track is legible on its own window can still fail against the
  overlay's pure black or white. That combination is the one §7 means when it says a new
  theme is checked with the overlay on as well as off, and it is the only part of the
  high-contrast surface a theme can still break.

**The focus measurement is separate and per-theme, and it is not this item's to invent.**
`docs/standards/ui-and-accessibility.md` §5.4 makes the ringless treatment measuring ≥3:1
rest-to-focus **ONEUP-0064**'s obligation, "with the measurement added to the suite" — and
`docs/design/oneup-2.0.md` §5.2 lands that item **before** this one. So the gate already
exists when this work starts, and what this spec owes it is six more palettes that pass it.
That is a different measurement from `focus` against `win` and `card` above: this one
compares a control's focused state to its own resting one, the other is ordinary non-text
contrast.

**A token that is checked by nothing is declared, not omitted.** Every palette key is
either in the pair table or on an explicit decorative list carrying its reason. A key in
neither fails the check — which is what stops a new token being added and quietly escaping
measurement.

### 4.8 Every pair the check fails today, and what happens to it

The check is written first, so this list is what it prints on the first run. Nothing here
is left to be noticed later.

**These are the figures at `e7d3718`, and ONEUP-0064 lands first.** The redesign is free to
move any colour in the two shipped palettes, so the check re-measures when this item starts
and the decisions below are rules rather than fixed dispositions: a pair the redesign has
already fixed needs nothing, and a pair it moved the wrong way is decided the same way its
neighbours are. The ratios are §2's; they are not restated here.

| Pair | Decision |
| --- | --- |
| light `lastrun` on `card` and on `win` | **Darkened** until both clear 4.5:1. It is ordinary body text and there is no reason to except it. This is the choice §7 asked ONEUP-0027 to make |
| light `amber` on `card` | **Darkened** until it clears 4.5:1. It is warning text |
| switch track "on" vs `switchmark` | **Fixed by tokenising.** `switchmark` is chosen per theme to clear 3:1 against both tracks — today it is a literal white with no say in the matter |
| light switch track "on" vs `rowcard` | **Fixed by tokenising**, same mechanism |
| `ghostbd` on `card`, both palettes | **Fixed, or raised.** The ghost button's border is its boundary and 3:1 is right. ONEUP-0064 lands first and may already have fixed it; if the redesigned button still fails, that is a defect in shipped work and gets its own roadmap bullet — it cannot be deferred to an item that has already shipped |
| `logbd` on `logbg`, both palettes | **Exception, decoration.** The log panel is identified by its own background, which differs from `card` in both palettes; the border adds nothing that identifies it |
| `disfg` on `disbg`, light | **Exception, out of WCAG's scope.** SC 1.4.3 exempts inactive components |
| the accent gradient against `win`, light | **Exception, decoration.** The row's gradient border is a hover cue, and hover also changes `rowcard` to `rowhov`, so the border is not the cue on its own |

**An exception is data, not a comment.** Each entry carries the pair, the measured ratio,
the reason, and a roadmap id where the reason is "not yet fixed" rather than "not in
scope". An entry missing any of those fails the check — which is what stops the exception
list becoming the place failures go to be forgotten.

## 5. Correctness invariants

- **INV-1** Every theme supplies every key in the reference set, and no extra. *Test:*
  `tests/gui-smoke.py` compares each theme's palette keys against the reference set and
  builds every theme through `build_theme`. Breaks when a theme is added by copying
  another and one key is missed — today that surfaces as a `KeyError` deep inside
  `Template.substitute`; this names the key and the theme.

- **INV-2** Every theme passes the contrast check on every pair §4.7 gives it — the base
  lists, and the painted set again with the high-contrast overlay on — or the pair carries
  an exception. *Test:* the new check, run over all eight from `tests/gui-smoke.py`, plus
  the two overlays checked once each. Breaks on a theme authored by eye.

- **INV-3** Every exception entry names its pair, its measured ratio, its reason, and a
  roadmap id where it is a deferral. *Test:* the check validates the entries' shape before
  it uses them, and fails on one that is incomplete. Breaks when a failing pair is
  silenced by appending it bare.

- **INV-4** Every token in the reference set is covered by §4.7 — as the foreground of a
  checked pair, as the background of one, or by name on the decorative or exempt list.
  *Test:* the check gathers the tokens its lists mention, on either side of a pair, and
  fails on a reference-set key it did not gather. Breaks when a token is added to the
  palette and forgotten, which would otherwise leave a new colour measured by nothing while
  the check still reported green.

- **INV-5** No colour literal survives outside a palette: not in a painter, and not in the
  stylesheet template either. *Test:* a grep gate in `local-CI.sh` fails on a `#rrggbb`
  string, a `QColor(` with a literal argument in any form, and `Qt.white`/`Qt.black` and
  their siblings — anywhere under `oneup/gui/` except inside the palette dictionaries
  themselves. **It does not catch a colour computed at run time**; nothing does, and INV-6's
  repaint check is what would notice the effect. Breaks two ways, and both exist today: a
  painted widget written the way the two existing ones were, and a literal dropped into the
  stylesheet where thirty already sit.

- **INV-6** A painted widget reads its colours through the module, never a name bound at
  import. *Test:* the same gate fails on `from …theme import` of any palette token; and
  `tests/gui-smoke.py` switches theme and samples the switch's rendered pixels, asserting
  the track is the new theme's colour and not the start-up one — the suite already samples
  a `ToggleSwitch`'s pixels for the colour-never-alone check, so the technique is in place.
  Breaks silently otherwise: the app looks themed everywhere except the control that shows
  state.

- **INV-7** Switching theme applies to the window and to every open dialog at once, with
  no restart. *Test:* `tests/gui-smoke.py` opens each dialog, switches theme, and asserts
  the application stylesheet changed and that **no** widget among the application's
  top-level windows and their children carries a stylesheet of its own. Breaks the way
  `docs/standards/ui-and-accessibility.md` §6.1 names: a per-widget `setStyleSheet`.

- **INV-8** A theme change rebuilds the tray icon. *Test:* `tests/gui-smoke.py` enables the
  tray, captures the pixmap of `_tray_icon(attention=True)`, switches theme, and asserts it
  differs. **The attention state is the one to capture**: the idle icon is the app's own
  SVG, which no theme touches, so an idle comparison would pass unchanged whether the
  invariant held or not. Breaks today by construction — `setIcon` is called on a check
  result and in `_ensure_tray`, and by nothing else.

- **INV-9** Under Follow system the desktop's light/dark switch still re-applies the theme
  live; under a named theme it does not. *Test:* `tests/gui-smoke.py` drives
  `colorSchemeChanged` under both settings and asserts the stylesheet changes only under
  Follow system. Breaks by wiring the signal to re-read the desktop unconditionally, which
  would override the user's choice every time they locked their screen.

- **INV-10** An unrecognised stored theme id starts the application in Follow system, and
  leaves the stored value alone. *Test:* `tests/gui-smoke.py` writes a junk id into
  `QSettings`, constructs the window, asserts it starts in Follow system and that the
  stored value is unchanged. Breaks because Qt returns a stored value in preference to the
  default, so `value("theme", "system")` is not the fallback it looks like.

- **INV-11** What is stored is the theme's id, never its displayed label. *Test:*
  `tests/gui-smoke.py` selects a theme, reads the raw `QSettings` value, and asserts it is
  the id. Breaks when the label is stored and the user then changes language: the stored
  theme stops resolving, and INV-10 silently returns them to Follow system.

- **INV-12** Every theme's focus cue reaches 3:1 against its own rest state. *Test:* the
  focus measurement ONEUP-0064 adds to the suite (`docs/standards/ui-and-accessibility.md`
  §5.4), extended to run over all eight palettes rather than the two it was written
  against. Breaks on a palette whose focus colour sits close to the rest colour of the
  control it lands on. This is a plain gate and not an exception, because the design lands
  ONEUP-0064 first: the treatment that can pass it already exists, and six new palettes
  have to meet it.

## 6. Failure modes

- **A theme is authored by eye and one pair is unreadable.** A user picks it and cannot
  read the last-run line. INV-2; and the reason the check is written before the first new
  palette, not after the eighth.
- **A colour is left outside the palette.** The application repaints around an unchanged
  switch, or around a Run button that stayed azure — the one control showing state, and the
  one the user presses. INV-5 and INV-6. Three ways in, and a gate for each: a literal in a
  painter, a literal in the stylesheet template, and a token bound by name at import.
- **The exception list becomes a silencer.** Each failure gets appended, the check goes
  green, and it now proves nothing. INV-3 — an entry without a reason is itself a failure.
- **A dialog sets its own stylesheet.** It desyncs from every later theme change and from
  the light/dark switch. `docs/standards/ui-and-accessibility.md` §6.1 forbids it; INV-7
  catches it.
- **A stored theme id is unknown.** Either from a downgrade or a hand-edited config. The
  application must start; it must not rewrite the value, or the downgrade is one-way.
  INV-10.
- **The label is stored instead of the id.** Nothing breaks until translation lands, and
  then every user's theme resets on a language change. INV-11.
- **The tray badge stays in the old palette.** It is small, it is the only thing on screen
  when the window is closed, and nothing points at it. INV-8.

## 7. Tests

| Locks in | Test | New? |
| --- | --- | --- |
| INV-1 | `tests/gui-smoke.py` — the key-set and build sweep | new |
| INV-2, INV-3, INV-4 | the contrast check, driven from `tests/gui-smoke.py` | new |
| INV-12 | ONEUP-0064's focus measurement, widened from two palettes to eight | inherited, widened |
| INV-5, INV-6 | `local-CI.sh` grep gate, plus a repaint check in `tests/gui-smoke.py` | new gate, new check |
| INV-7 | `tests/gui-smoke.py` — dialog open across a theme switch | new |
| INV-8 | `tests/gui-smoke.py` — tray pixmap across a theme switch | new |
| INV-9 | `tests/gui-smoke.py` — `colorSchemeChanged` under both settings | new |
| INV-10, INV-11 | `tests/gui-smoke.py` — the stored-value checks | new |

The check is a module under `oneup/gui/`, not a test helper, because it is a computation
the application could also expose and because a helper living in `tests/` cannot be
imported by anything else. `tests/gui-smoke.py` drives it.

Two things the suite must keep doing while this lands, both from
`docs/standards/testing.md`: the `HOME` redirect stays module-level and runs before
`QApplication` is constructed (§2.2), and a passing run stays silent apart from the known
teardown noise (§7). The theme tests write to `QSettings`, which the `HOME` redirect
already sandboxes.

**`./local-CI.sh` is green at every commit.** The contrast check — INV-2, INV-3, INV-4 —
lands and passes against the exception list §4.8 settles, before the first new palette is
authored. INV-12's focus measurement is a separate gate and not this item's to build: it
arrives with ONEUP-0064 and is already green on two palettes, and each new palette has to
keep it that way.

## 8. Docs & release

- **`CHANGELOG.md`** — one `Added` entry for the picker, and one `Fixed` for the contrast
  corrections §4.8 makes to the two shipped palettes. The second is a user-visible change
  in a spec that is otherwise additive, and it should not hide inside the first.
- **`docs/standards/ui-and-accessibility.md`** — §7's "**This check does not exist yet**"
  paragraph, and its statement that ONEUP-0027 decides the `lastrun` case, both become
  history. Two **What checks this** rows go stale together: §7's, which says the check is
  this item's to write, and §5.4's, which says *"nothing computes contrast anywhere in the
  suite"* — after this lands, something does, and 0064's remaining obligation is the
  treatment rather than the measurement. §3's tray-badge row names `#3a2600` as a literal,
  which becomes `traymark`.
- **`docs/specs/ONEUP-0034-gui-modules.md`** §4.2 — its module table is the contract for
  where each module-level name lives, and this work deletes the colour names it places:
  `GREEN`, `RED` and `ACCENT`/`BTN_ACCENT` from the `theme.py` row, and
  `TRAY_ATTENTION_COLOR` from `tray.py`'s `TRAY_*`. `theme.py` gains `current_palette()`
  and the palette table in their place.
- **`docs/reference/`** — nothing. A theme is not a contract between the two halves.
- **`docs/standards/testing.md`** §1's suite table gains nothing new: the check is driven
  from `tests/gui-smoke.py` rather than being its own programme.
- **`docs/design/oneup-2.0.md`** §1's one-line description of this item, and the ONEUP-0027
  row naming the spec as *to be written*.
- **`README.md`** — it describes OneUp as following *"your desktop's **light/dark** theme"*
  and says the high-contrast mode "works with both the light and the dark scheme". Both
  stay true and both stop being the whole truth.
- **No version bump of its own.** This ships as part of 2.0.0, which the design's §7 gate
  governs.

## 9. Alternatives considered (and rejected)

- **Eight themes each with a light and a dark variant.** Sixteen palettes, and Follow
  system would then mean two things — which pair, and which half of it. Rejected as twice
  the authoring and twice the check surface for a choice the picker already offers: a user
  who wants the desktop followed picks Follow system.
- **Deriving the eight from a base hue programmatically.** Attractive, and it fails exactly
  where it matters: a generated palette has no way to satisfy a 3:1 boundary except by
  luck, so every generated theme would need the same check, hand-corrected. Authoring six
  palettes against a check is less work than debugging a generator against it.
- **Handing painted colours to widgets as `qproperty-` assignments in the QSS**, the way
  `highContrast` is handed to `ToggleSwitch` today. Rejected on two counts: the tray icon is
  a `QIcon` built in a method, with no widget to carry a property; and, as the `_QSS`
  comment records, a `qproperty-` assignment is not reverted when its rule stops matching,
  so every theme would have to restate every one of them or inherit the last theme's.
- **A `QPalette` per theme instead of a palette dictionary.** Qt's palette roles cover
  window, base, text and highlight — not `rowcard`, `badgebg`, `switchmark`, or the rest of
  the switch and tray set. Half the palette would live in `QPalette` and half in a dictionary,
  which is the split that produces "themed everywhere except one widget".
- **Shipping the check as a review step rather than a test.** Rejected by
  `docs/standards/ui-and-accessibility.md` §7 in terms: a computation over the palette
  covers themes added later, and a review step covers the themes somebody remembered.

## 10. Out of scope

- **Custom or user-authored themes.** Reading a palette from a file is a new input to
  validate and a new failure mode at start-up. The eight are built in.
- **Per-widget or per-dialog theming.** `docs/standards/ui-and-accessibility.md` §6.1
  forbids it and INV-7 tests for it.
- **Choosing the ringless focus treatment.** ONEUP-0064's, and it lands before this item
  (design §5.2), so this spec inherits both the treatment and the measurement and only owes
  it six more palettes that pass.
- **Changing any layout, spacing or wording.** A theme supplies colours only — §7's first
  consequence. The redesign is ONEUP-0064.
- **Translating the eight labels.** ONEUP-0032 comes last and wraps every string at once;
  wrapping these now would mean wrapping them twice. §4.1 keeps the id separate from the
  label so that item changes nothing but the label.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-27 | 3 lanes; 2 critical, 3 high, 3 medium, 1 low — **9 verified, 0 dismissed** | Both criticals were the check's own reach. `switchrim` stood for two different colours — the white pen outlining the track and the black one rimming the knob — so one key could not hold it, under exactly the high-contrast setting the token exists to serve; it is two tokens now. And "checked twice, overlay off and on" was undefined: the overlay carries a disjoint key set and overrides nearly every selector, so a base-palette pair has no meaning with it on. §4.7 now says what it does mean — the overlay's own pairs once per base, and the painted set per theme, which is the only part of the high-contrast surface a theme can still break. §4.7's pair list also turned out to omit five pairs §2 and §4.8 both treat as checked, plus two the stylesheet has and nobody had named: the progress bar's text on its own fill, and the task labels on a hovered row. Verifying that found the larger miss — **§2 counted the ten literals in the painters and none of the thirty inside `_QSS`**, including `#4aa3ff` written out in eight places, so a theme could set `accent` and leave the Run button azure. INV-5 now covers the template as well as the painters |
| 2 | 2026-07-27 | 3 lanes; 1 critical, 4 high, 4 medium, 1 low — **9 verified, 1 dismissed** | Most of this loop was loop 1's own blast radius. Widening INV-5 to forbid a colour literal in the stylesheet left eleven of the twelve distinct literals with no token to become — the button label, both gradients, the link hover and the danger family — so the invariant demanded something the design never named; §4.3 now names the groups and lets the implementer name the keys. Splitting `switchrim` in two left "the nine painted tokens" over a table of ten, in two places. And "exactly one of four lists" was too rigid to be true: a surface like `card` or `switchknob` is covered by being something else's background, so INV-4 now asks for coverage rather than membership. Two findings were older than loop 1. `build_theme` still took `dark: bool` and picked between two module dicts — with eight palettes there is nothing for a boolean to select, and no section said so. And `trayidle`'s `#888888` is the disc drawn when the app icon **cannot be loaded**, not "the quiet disc": the ordinary idle tray icon is the app's own SVG, which no theme touches, so INV-8's test had to name the attention badge or it would have passed unchanged either way. Worst of all, the design lands ONEUP-0064 **before** this item, and three passages deferred to it as though it were still to come — INV-12 carried a whole exception mechanism for a gate that will already exist. Dismissed: that §8 should draft the README's replacement wording; §8 names what goes stale |
| 3 | 2026-07-27 | 3 lanes; 3 medium — **3 verified, 0 dismissed** | Converging: no critical, no high, and the cross-document lane clean. All three were loop 2's own blast radius. Naming the four groups of stylesheet literals in §4.3 left two of them — the link button's hover and the danger family — with no home in §4.7, so §4.3's claim that "§4.7 places every one of them" had stopped being true the moment it was written. Saying `build_theme` picks the overlay "from the theme's Base column" left `base` nowhere to live: §4.1 defined a theme as a triple of id, label and palette, and a palette holds colours. It is a fourth field now. And §4.4 said `apply_app_theme` repaints "what the stylesheet cannot reach — which is the tray icon", which quietly assumed the switch repaints itself; nothing tells a painter reading `current_palette()` that its colours moved, and INV-6's whole test rests on it. `apply_app_theme` now calls `update()` on every top-level widget and says why |
| 4 | 2026-07-27 | 3 lanes; 1 medium — **1 verified, 0 dismissed** | **Converged.** Two lanes clean, and nothing from an earlier loop returned. The one finding was precision: §7 said "the check lands and passes ... before the first new palette", which reads as covering INV-12 as well, when the focus measurement is a separate gate arriving with ONEUP-0064 and already green on two palettes. `Draft` → `Reviewed`; implementation of ONEUP-0027 is unblocked, after ONEUP-0034 and ONEUP-0064 |
