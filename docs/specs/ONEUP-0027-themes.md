# ONEUP-0027 — selectable themes

**Status:** Implemented
**Kind:** feature
**Roadmap:** ONEUP-0027
**Branch:** v2
**Verified at:** `e7d3718` for the contrast figures in §2, which are pre-ONEUP-0064/0076
and are re-taken when this item starts (§2). Every claim about the CODE was re-checked
against `69df2ac` on 2026-08-24.

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
this spec keeps it. **A dialog's own background is themed, and ONEUP-0076 is what themed
it** — `_QSS` carries `QMainWindow, QDialog { background: $win; }`, because a child window
inherits the *sheet* and not a declaration written for another selector, so without the
rule a bare `QDialog` painted Qt's platform grey in both palettes. What a dialog does
inherit is every object-name selector its children match, which is why
`docs/standards/ui-and-accessibility.md` §6.1 still forbids a per-dialog stylesheet.

**Two things are still missing. The figures below are `e7d3718`'s, and ONEUP-0064 and
ONEUP-0076 have shipped since — so every count and ratio here is a starting point the
implementer re-takes, not a description of the tree.**

**The theme reaches only the `$tokens`, and a great many colours are not tokens.** Two
places, both measured at `e7d3718`.

A stylesheet cannot touch a widget that paints itself, and two of them do.
`ToggleSwitch.paintEvent` fills its track from the module constants `GREEN` and `RED`,
draws the state shape and the knob with a literal `QColor("#ffffff")`, and rims them with
`#ffffff` and `#000000` under high contrast. `tray.py`'s `_tray_icon` paints the attention disc
`TRAY_ATTENTION_COLOR`, its rim `#ffffff`, its `!` `#3a2600`, and — only when the app icon
cannot be loaded at all — a plain `#888888` disc in place of it. Ten colours, and the ones
that matter are the surfaces carrying state meaning: two of the three
cue pairings `docs/standards/ui-and-accessibility.md` §3 lists are painted here, the third
being an ordinary label.

**And the stylesheet itself is not all tokens.** `_QSS` carries hex literals that no
substitution touches: the Run button's white label and its hover and pressed gradients, the
danger-button family, and the tooltip's border. A theme that set `accent` and left those
would recolour the application around a button that stayed azure. **The set is what INV-5's
gate prints on its first run, and that is the list to work from** — ONEUP-0064 has already
turned some of these into palette keys (`linkfg`, `linkhov`, `stopfg`, `stophov`,
`ghosthov`), so a group named here may already be discharged and a literal not named here
may have arrived.

Between them that is the whole of what a theme would fail to reach: the two controls that
show state, and the one button the user presses.

**Half the check §7 requires exists, and the palettes shipping today do not all pass the
half that does not.** ONEUP-0076 landed the ratio arithmetic — `contrast()`, `composite()`
and `focus_report()` in `oneup/gui/theme.py`, driven from `tests/gui-smoke.py` — but it
measures only the colours that item moves plus every derived focus pair. **The
whole-palette sweep is what this item writes, and it reuses `contrast()` rather than
implementing the formula a second time.** Computed at `e7d3718` with the WCAG 2.2 formula — relative luminance
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
spec obeys them and discharges the four jobs §7 hands it: write the whole-palette check,
settle the `lastrun` case, surface a theme that cannot be applied, and turn
`apply_app_theme`'s no-op into a real fallback (§4.5).

The ringless focus treatment is **ONEUP-0076**'s to pick, and `docs/design/oneup-2.0.md`
§5.2 lands that item **before** this one. So by the time this work starts the treatment
exists and its measurement is in the suite — `docs/standards/ui-and-accessibility.md` §5.4
and the design's interface-redesign row are where that obligation is written. This spec inherits
the gate and owes it six more palettes; it does not choose the treatment, and it does not
carry the gap as an exception.

**The redesign landing first has a wider consequence.** Every figure in §2 was measured
before it. ONEUP-0076 and ONEUP-0064 may move any of those colours, so §4.8 states rules rather than fixed
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
Settings shows; it and §4.6's failure message are this item's translatable strings
(ONEUP-0032), and the `id` is neither shown nor translated.

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
them. The ten below are read by a `paintEvent` or an icon painter; the three gradients are read
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
| `trayidle` | `#888888` | `tray.py`'s `_tray_icon` — the plain disc drawn **only when the app icon cannot be loaded** |
| `trayattn` | `TRAY_ATTENTION_COLOR` | the amber "updates waiting" disc |
| `trayrim` | the `#ffffff` pen | the disc's rim |
| `traymark` | `#3a2600` | the `!` inside the disc |
| `accent`, `btn_accent`, `btn_danger` | `ACCENT`, `BTN_ACCENT`, `BTN_DANGER` | the gradient on a hovered row, the fill of the Run button, and the fill of the restart button and reboot banner |

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

**The stylesheet's own literals become tokens too**, each named for what it colours rather
than what colour it is: the primary button's **label**, its **hover** and **pressed**
fills, the **danger** family the restart button and reboot banner share, and the tooltip's
**border**. Naming them is the implementer's, bounded by two things — INV-5 leaves no
literal behind, and INV-4 gives every resulting token a home in §4.7.

**A solid-colour literal does not become `accent`.** `accent` holds a
`qlineargradient(…)` string, so substituting it into a `border: 1px solid $…` declaration
emits QSS Qt cannot parse. A literal that happens to equal one of the accent's stops needs
its own token for the surface it colours.

`GREEN`, `RED` and `TRAY_ATTENTION_COLOR` stop being module constants, as do `ACCENT`,
`BTN_ACCENT` and `BTN_DANGER` — `build_theme` injects those three into the palette today,
which is the seam this widens. **`BTN_DANGER` is the one to watch**: it is
`_vgradient(BTN_DANGER_STOPS)` and so contains no hex literal at all, which means INV-5's
gate cannot see it. Left behind, the restart button and reboot banner keep one fill across
all eight themes while the danger family's other literals become per-theme tokens.

**For the two BUTTON gradients a palette authors the stop PAIR, and `build_theme` derives
the string.** They are one fact written twice — `BTN_ACCENT = _vgradient(BTN_ACCENT_STOPS)`
today, and the code says the pair is kept "so the derivation and the sheet cannot drift
apart". So `btn_accent_stops` and `btn_danger_stops` are the authored keys, and
`btn_accent`/`btn_danger` are built from them by `_vgradient` where the focus keys are
built. A theme authoring both could disagree with itself, and nothing would compare them.

**`accent` is not one of those two and is authored whole.** It is the row-hover gradient
and it is *diagonal* — `x2:1, y2:1` against `_vgradient`'s `x2:0, y2:1` — with its own
second stop (`#22d3ee`, where `BTN_ACCENT_STOPS` ends `#2f6fe0`). No stop pair exists for
it today and `_vgradient` cannot express it, so it stays a full QSS string in the palette.
§4.7 measures it as decoration, so nothing derives a focus cue from it and the drift the
paragraph above guards against cannot arise.

**Which means a palette value is not always one colour**, and INV-1 and the check both see
that: a stop-pair key holds two colours, and a derived gradient key holds a QSS function.
The check reads a gradient key as its stops — §4.7 already measures the Run button's label
"against both gradient stops" — and never as a single colour.

**The focus derivation reads those constants, and it moves in the same commit.**
`focus_keys()` derives `switchfocuson` and `switchfocusoff` from `GREEN`/`RED`,
`accentfocus` from `BTN_ACCENT_STOPS`, `dangerfocus` from `BTN_DANGER_STOPS` and
`warnfocus*` from `WARN_TINT` via `warn_tint()`; `focus_report()` reads `GREEN`/`RED`
again. `docs/standards/ui-and-accessibility.md` §7 states the consequence of missing this:
"a palette that sets a track and leaves the derivation alone gets a focused track derived
from a colour it no longer paints" — and it would pass INV-12 while doing so, because the
derivation would still clear 3:1 against the colour it derived from. So every input to
`focus_keys()` and `derive_focus_gradient` is palette-resolved, and
`BTN_ACCENT_STOPS`/`BTN_DANGER_STOPS`/`WARN_TINT` become palette keys alongside the rest.

### 4.4 How a painted widget gets its colours

**`current_palette()` returns the BASE palette, with the overlay never merged into it.**
The painted widgets need base keys under high contrast, not overlay ones —
`switchtrackrim` and `switchknobrim` exist only for that state and are §4.3 base tokens —
and the overlay's key set collapses many base tokens onto a few, so merging would replace
keys a painter depends on with ones it cannot use. A painter that needs to know whether
high contrast is on reads the `highContrast` property it is already handed, as
`ToggleSwitch` does today. Painters bind to this function, so this is a contract rather
than a local detail.

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
icon: `tray.py`'s module-level `_tray_icon` builds a `QIcon` and the result is handed to `setIcon` at two
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

**A theme that cannot be applied falls back, and says so.** `docs/standards/ui-and-accessibility.md`
§7 makes a `FocusDerivationError` refuse the theme; `apply_app_theme` catches it and today
applies **nothing**, which is correct only because `build_theme` takes no theme argument and
the built-in palette is what failed. Once it takes one — §4.4 — the branch has somewhere to
go, and §7 hands both halves to this item. So: **fall back to Follow system, leave the
stored id alone, and tell the user in the picker** rather than only on the console. Leaving
the stored value is §4.5's rule above, for the same reason — a theme that fails to derive on
this version may derive on the next. The three effects are ordered: the sheet already
installed stays until a replacement is built, so the user's text size and high-contrast
choice survive a failed switch by construction.

INV-2 makes this unreachable for the eight built-in themes, which is why it is a fallback
and not a feature. It is specified because the picker is a control the user operates, and a
control that silently does nothing is the one outcome §7 forbids.

### 4.6 The picker

A combo box, built by the window and re-parented into `SettingsDialog` alongside the text
size and contrast controls — the pattern that dialog already uses, and the reason
`docs/specs/ONEUP-0034-gui-modules.md` §4.2 calls it a host rather than an owner. It lists
**Follow system** first, then the eight in §4.2's order. Choosing an entry applies it
immediately: there is no OK button to press, matching every other control in that dialog.

**The picker adds one string that is not a label**: the message §4.5 requires when a theme
cannot be applied. It is a user-facing sentence, so ONEUP-0032 wraps it with the rest, and
§10's translation note covers it as it covers the labels.

The control carries an accessible name like every other
(`docs/standards/ui-and-accessibility.md` §2), and the labels are the other strings this
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
  **ONEUP-0064 and ONEUP-0076 add five keys to this class, and each is checked on every
  surface it lands on rather than on `card` alone** — an ink measured against the card
  reads 4.53:1 there and 3.89:1 on a hovered row, so the surface set is what makes the row
  mean anything. `linkfg` and `linkhov` are the link button's rest and hover text, now
  tokens rather than sheet literals, on `card`, `rowcard`, `rowhov` and the warning
  banner's composited tint. `ghosthov` is the ghost button's `:hover` / `:checked` ink on
  the same four, because *Retry* now sits on that tint. `stopfg` and `stophov` are the Stop
  button's rest and hover label on `card`; its fill is transparent, so it is read against
  the card and **not** against the danger family's fill row above.
- **3:1**, the foreground carries meaning without being text — `switchon` and `switchoff`
  against `rowcard`, against `rowhov`, and against `switchmark` and `switchknob`;
  `switchtrackrim` against `switchon` and `switchoff`; `switchknobrim` against
  `switchknob`; `trayattn` and `trayidle` against both window colours; `trayrim` against
  `trayattn` and `trayidle`; `traymark` against `trayattn`; `focus` against `win` and
  `card`; `ghostbd` against `card`; and the danger family's banner borders against `win`
  and `card`.
  **Three more from ONEUP-0064 and ONEUP-0076**, each a boundary rather than text:
  `ghosthov` as the ghost button's hover *border* against `card` — it shares one literal
  with the ink above, so moving one moves both — and `stopfg` and `stophov` as the Stop
  button's rest and hover border against `card`.
- **Declared decorative** — held to no threshold, and each carrying its reason. **A
  decorative or exempt row is still measured, and it is an exception entry**: it is
  computed, it records its ratio, and it is compared against nothing. That is what lets
  INV-3 ask every entry for a ratio, and it is what makes the list auditable — a pair
  nobody computes cannot be shown to have drifted. The rows: `logbd` on
  `logbg`, `accent` on `win`, and the primary button's hover and pressed fills, which
  restate a state the cursor and the press already carry.
  **ONEUP-0076 puts `logbd` on three further surfaces and all three join this list for the
  same reason the `logbg` row is already on it** — `rowcard` and `rowhov`, where the detail
  panel's new border is read against the row beneath it because the panel is transparent,
  and `win`, where the two dialog panels sit. Under mechanism B the cue is the border's
  **change** of colour, which that item's INV-2 measures against `logbd` itself; how far
  the resting border stands out from what is behind it carries no state.
- **Declared exempt** — `disfg` on `disbg`. WCAG 2.2 SC 1.4.3 puts inactive components
  outside its scope.

**The check's universe is every colour `$token` substituted into the sheet, which is wider
than the reference set** — measured at HEAD, 53 keys go into `_QSS`: 29 authored, the 3
gradients `build_theme` injects, the 15 derived focus keys, and 6 font metrics. The metrics
are not colours and are out. The other 47 are in, and that is the set INV-4 iterates.
**Saying "the reference set" would exempt exactly the tokens most likely to escape
measurement** — the derived ones, which no theme author ever sees. The overlay's own keys
are checked by the high-contrast paragraph below, including the three `hc_focus_keys()`
derives (`hcfocusfill`, `hcfocusink`, `hcbdfocus`), and are not INV-4's.

**Every token in that universe is covered**, in one of four ways: it is the foreground
of a checked pair, it is the background of one, it is named on the decorative or exempt
list, or it is declared **measured elsewhere** — naming the item and the invariant that
measures it. That fourth route exists because `ONEUP-0076` lands first and adds a focus pair per control
family: their values are recomputed per palette by that item's derivation rather than fixed,
so they cannot sit in a table of fixed pairs, and they are measured by its INV-2 and INV-3,
so they are not decorative. **As built (2026-08-21) that is fifteen keys, named here so this
check can see them rather than left as a description**: `focusfill` / `focusink` for the
card family, `rowfocusfill` / `rowfocusink` for a row's two hover states, `winfocusfill` /
`winfocusink` for a dialog's button strip, `warnfocusfill` / `warnfocusink` for the warning
banner, `accentfocus` / `accentfocusink` and `dangerfocus` / `dangerfocusink` for the two
gradients, `logbdfocus` for every mechanism-B border, and `switchfocuson` / `switchfocusoff`
for the painted switch. **They are computed, not authored**, so a new palette does not
supply them and cannot omit them — but computed *from what* is the point.
`switchfocuson`/`switchfocusoff` derive from `GREEN`/`RED`, and
`accentfocus`/`accentfocusink`/`dangerfocus`/`dangerfocusink` from the two stop pairs;
none of those six reads the palette at all, so **until §4.3's move lands they are identical
in every theme.** `warnfocus*` sits in between — `warn_tint()` composites `WARN_TINT` over
`palette["card"]`, so the fill follows the theme and the ink need not. A declaration that
names no measuring invariant is not one, and fails the check like an undeclared key. A surface like `card` or `switchknob` is covered by being something else's
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
rest-to-focus **ONEUP-0076**'s obligation, "with the measurement added to the suite" — and
`docs/design/oneup-2.0.md` §5.2 lands that item **before** this one. So the gate already
exists when this work starts, and what this spec owes it is six more palettes that pass it.
That is a different measurement from `focus` against `win` and `card` above: this one
compares a control's focused state to its own resting one, the other is ordinary non-text
contrast.

**A token that is checked by nothing is declared, not omitted** — by one of the four routes
above, never by two of them. A key covered by none fails the check, which is what stops a
new token being added and quietly escaping measurement.

### 4.8 Every pair the check fails today, and what happens to it

The check is written first, so this list is what it prints on the first run. Nothing here
is left to be noticed later.

**These are the figures at `e7d3718`, and ONEUP-0076 and ONEUP-0064 land first.** The redesign is free to
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
| `ghostbd` on `card`, both palettes | **Fixed, or raised.** The ghost button's border is its boundary and 3:1 is right. ONEUP-0076 lands first and closes it (its INV-8); if the redesigned button still fails, that is a defect in shipped work and gets its own roadmap bullet — it cannot be deferred to an item that has already shipped |
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

- **INV-4** Every colour token substituted into the sheet is covered by §4.7 — as the
  foreground of a checked pair, as the background of one, by name on the decorative or
  exempt list, or by a *measured elsewhere* declaration naming the item and invariant that
  measures it. **The universe is §4.7's, not the reference set**: authored keys, the
  gradients `build_theme` injects, and the derived focus keys, less the font metrics.
  *Test:* the check gathers the tokens its lists mention, on either side of a pair, and
  fails on a substituted colour key it did not gather. Breaks when a token is added to the
  palette and forgotten, which would otherwise leave a new colour measured by nothing while
  the check still reported green.

- **INV-5** No colour literal survives outside a palette: not in a painter, and not in the
  stylesheet template either. *Test:* a grep gate in `local-CI.sh` fails on a `#rrggbb`
  string, a `QColor(` with a literal argument in any form, and `Qt.white`/`Qt.black` and
  their siblings — anywhere under `oneup/gui/`. **Three exemptions, and they are the whole
  list**: the palette dictionaries themselves, including the two high-contrast overlays;
  the derivation's blend anchors `_BLACK` and `_WHITE`, which are the ends of the sRGB
  range rather than colours anyone chose; and a comment. Every other module-level colour
  constant is converted rather than exempted — §4.3 moves `GREEN`, `RED`,
  `TRAY_ATTENTION_COLOR`, `ACCENT`, `BTN_ACCENT`, `BTN_ACCENT_STOPS`, `BTN_DANGER_STOPS`
  and `WARN_TINT` into palettes. **`focus_keys()`'s own literal `"#ffffff"` is a surface
  SET, not one token** — it is the third argument of
  `derive_focus(track, (track, "#ffffff"))`, and it stands for both white things drawn on
  the track. §4.3 splits those into two independently themed keys, so it resolves to
  **both**: `(track, switchmark, switchknob)`. Resolving it to `switchmark` alone would
  leave the focused track measured against nothing that constrains the knob, and a theme
  with a tinted `switchknob` would ship a focused switch its knob disappears into — passing
  INV-2, INV-4 and INV-12 on the way. `focus_report()` carries the same literal for the
  same reason and moves with it. **The exemption list is stated here because the gate is in
  `local-CI.sh`**: one written from the old wording turns CI red on shipped, correct code
  the moment it lands. **It does not catch a colour computed at run time**; nothing does,
  and INV-6's repaint check is what would notice the effect. Breaks two ways, and both
  exist today: a painted widget written the way the two existing ones were, and a literal
  dropped into the stylesheet beside the ones already there.

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
  focus measurement ONEUP-0076 adds to the suite (`docs/standards/ui-and-accessibility.md`
  §5.4), extended to run over all eight palettes rather than the two it was written
  against. Breaks on a palette whose focus colour sits close to the rest colour of the
  control it lands on. This is a plain gate and not an exception, because the design lands
  ONEUP-0076 first: the treatment that can pass it already exists, and six new palettes
  have to meet it.

- **INV-13** A theme whose focus pair cannot be derived falls back to Follow system,
  leaves the stored id alone, and says so. *Test:* `tests/gui-smoke.py` registers a
  deliberately underivable palette — **not one of the eight**, so INV-2 stays the gate that
  keeps such a theme out of the product — selects it, and asserts three things: the applied
  stylesheet is Follow system's, the stored `theme` value is still the underivable id, and
  the message reached the picker. Breaks in both directions, which is why all three are
  asserted: an implementation that rewrites the stored id makes a downgrade one-way, and
  one that applies nothing leaves a control that does nothing. **Without this invariant the
  branch ships unexercised** — §10 rules out user-authored themes and INV-2 keeps the eight
  clean, so nothing else can ever reach it.

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
| INV-12 | ONEUP-0076's focus measurement, widened from two palettes to eight | inherited, widened |
| INV-13 | `tests/gui-smoke.py` — an underivable palette falls back, keeps the stored id, and reports | new |
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
arrives with ONEUP-0076 and is already green on two palettes, and each new palette has to
keep it that way.

## 8. Docs & release

- **`CHANGELOG.md`** — one `Added` entry for the picker, and one `Fixed` for the contrast
  corrections §4.8 makes to the two shipped palettes. The second is a user-visible change
  in a spec that is otherwise additive, and it should not hide inside the first.
- **`docs/standards/ui-and-accessibility.md`** — §7's "**Half of this check now exists**"
  paragraph, and its statement that ONEUP-0027 decides the `lastrun` case, both become
  history, as does its "once a theme can reach the switch at all" clause. **One
  **What checks this** row goes stale: §7's**, which says the whole-palette sweep is this
  item's to write. **§5.4's row is already correct and is not touched** — ONEUP-0076
  rewrote it when it shipped the ratio arithmetic. §3's tray-badge row names `#3a2600` as a
  literal, which becomes `traymark`.
- **`docs/specs/ONEUP-0034-gui-modules.md`** §4.2 — its module table is the contract for
  where each module-level name lives, and this work deletes the colour names it places:
  `GREEN`, `RED`, `ACCENT`/`BTN_ACCENT`/`BTN_DANGER`, the two stop pairs
  `BTN_ACCENT_STOPS` and `BTN_DANGER_STOPS`, and `WARN_TINT` from the `theme.py` row, and `TRAY_ATTENTION_COLOR`
  from `tray.py`'s `TRAY_*`. `theme.py` gains `current_palette()` and the palette table in
  their place, and keeps `_BLACK`/`_WHITE` as INV-5's named exemption.
- **`docs/reference/`** — nothing. A theme is not a contract between the two halves.
- **`docs/standards/testing.md`** §1's suite table gains nothing new: the check is driven
  from `tests/gui-smoke.py` rather than being its own programme.
- **`docs/design/oneup-2.0.md`** §1's one-line description of this item. Its ONEUP-0027
  row already cites this spec by path and needs nothing.
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
- **Routing the REST tracks and the tray through `qproperty-` assignments in the QSS.**
  ONEUP-0076 already hands the switch two painted colours that way — `_QSS` sets
  `qproperty-focusTrackOn: $switchfocuson` and `qproperty-focusTrackOff: $switchfocusoff`,
  alongside `qproperty-highContrast` — so this is a live mechanism rather than a
  hypothetical one, and the "not reverted when its rule stops matching" hazard is handled
  there by the template emitting every assignment unconditionally. Rejected for the rest
  anyway, on the one count that still holds: the tray icon is a `QIcon` built in a method,
  with no widget to carry a property, so a `qproperty-` route themes the switch and leaves
  the tray needing `current_palette()` regardless.
  **The two shipped assignments stay as they are.** `switchfocuson`/`switchfocusoff` are
  derived keys that already reach the sheet by substitution, and moving them would buy
  nothing; `switchon`, `switchoff`, `switchmark` and `switchknob` are read through
  `current_palette()` per §4.4. So the switch has two routes on purpose — derived focus
  colours by property, authored palette colours by function — and INV-6's gate forbids
  only the third: a token bound by name at import.
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
- **Choosing the ringless focus treatment.** ONEUP-0076's, and it lands before this item
  (design §5.2), so this spec inherits both the treatment and the measurement and only owes
  it six more palettes that pass.
- **Changing any layout, spacing or wording.** A theme supplies colours only — §7's first
  consequence. The redesign is ONEUP-0064.
- **Translating the eight labels and §4.6's failure message.** ONEUP-0032 comes last and
  wraps every string at once; wrapping these now would mean wrapping them twice. §4.1 keeps
  the id separate from the label so that item changes nothing but what is shown.

## 10a. What the build proved (amendment, 2026-08-24)

Recorded after implementation, per `CLAUDE.md` rule 14: this records what was
BUILT and does not re-arm the gate.

- **The check found three failing pairs no section had listed**, and they were
  the ones that mattered: the Run button's white label at **2.63:1** on its own
  fill, the Restart button's at **3.06:1**, and the tray badge at **1.79:1** on
  a light window. §2's table had measured the accent gradient against `win` and
  never the LABEL against the gradient. All three were fixed rather than
  excepted, decided with the user: both button fills darken at their top stop
  only, since both bottom stops already cleared.
- **§4.8's "fixed by tokenising" worked exactly as written.** The white
  bar-and-circle stays white and the TRACK moved, per palette — `#26a95e` dark
  and `#239b56` light, from one shared `#2ecc71`. Light needed a darker green
  than dark did, which is the whole argument for the token.
- **INV-4's universe had to be the substituted set, not the reference set.**
  Measured at build time: 53 keys reach `_QSS` — 29 authored, 3 injected
  gradients, 15 derived focus keys, 6 font metrics. Checking the reference set
  alone would have exempted the 18 derived tokens, which are exactly the ones no
  theme author ever sees.
- **A derived key needed a fifth coverage route.** `btn_accent` and the banner
  washes are restatements of an authored token, so measuring both measures one
  colour twice; `DERIVED_FROM` records which. It cannot launder coverage — a
  derived key whose source nothing checks leaves both reported uncovered.
- **INV-8 caught a defect in the six new palettes**: they had all kept one tray
  badge, because they were generated by tinting SURFACES only. A theme that
  cannot recolour the badge makes §6's "the tray stays in the old palette"
  undetectable. Each palette carries its own badge, rim and mark now — a modest
  shift inside the amber register, since "attention" is the meaning.
- **INV-5's gate was written with `\b`, which awk's ERE does not support.** The
  `Qt.white` branch matched nothing while the gate looked complete and tested
  two of its three cases. Found by seeding a literal and running it. This is
  `CLAUDE.md` §6's shape-check trap in a second place, and the same remedy:
  run the pattern, do not read it.
- **Adding one focusable control turned three invariants red** — no `:focus`
  rule, an anonymous focusable popup, and no slot in the tab order. That is
  ONEUP-0076's and ONEUP-0064's contracts doing their job on the first control
  added after they shipped.
- **§4.6's picker adds a second string**, not just labels: the message §4.5
  requires when a theme cannot be applied.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-27 | 3 lanes; 2 critical, 3 high, 3 medium, 1 low — **9 verified, 0 dismissed** | Both criticals were the check's own reach. `switchrim` stood for two different colours — the white pen outlining the track and the black one rimming the knob — so one key could not hold it, under exactly the high-contrast setting the token exists to serve; it is two tokens now. And "checked twice, overlay off and on" was undefined: the overlay carries a disjoint key set and overrides nearly every selector, so a base-palette pair has no meaning with it on. §4.7 now says what it does mean — the overlay's own pairs once per base, and the painted set per theme, which is the only part of the high-contrast surface a theme can still break. §4.7's pair list also turned out to omit five pairs §2 and §4.8 both treat as checked, plus two the stylesheet has and nobody had named: the progress bar's text on its own fill, and the task labels on a hovered row. Verifying that found the larger miss — **§2 counted the ten literals in the painters and none of the thirty inside `_QSS`**, including `#4aa3ff` written out in eight places, so a theme could set `accent` and leave the Run button azure. INV-5 now covers the template as well as the painters |
| 2 | 2026-07-27 | 3 lanes; 1 critical, 4 high, 4 medium, 1 low — **9 verified, 1 dismissed** | Most of this loop was loop 1's own blast radius. Widening INV-5 to forbid a colour literal in the stylesheet left eleven of the twelve distinct literals with no token to become — the button label, both gradients, the link hover and the danger family — so the invariant demanded something the design never named; §4.3 now names the groups and lets the implementer name the keys. Splitting `switchrim` in two left "the nine painted tokens" over a table of ten, in two places. And "exactly one of four lists" was too rigid to be true: a surface like `card` or `switchknob` is covered by being something else's background, so INV-4 now asks for coverage rather than membership. Two findings were older than loop 1. `build_theme` still took `dark: bool` and picked between two module dicts — with eight palettes there is nothing for a boolean to select, and no section said so. And `trayidle`'s `#888888` is the disc drawn when the app icon **cannot be loaded**, not "the quiet disc": the ordinary idle tray icon is the app's own SVG, which no theme touches, so INV-8's test had to name the attention badge or it would have passed unchanged either way. Worst of all, the design lands ONEUP-0064 **before** this item, and three passages deferred to it as though it were still to come — INV-12 carried a whole exception mechanism for a gate that will already exist. Dismissed: that §8 should draft the README's replacement wording; §8 names what goes stale |
| 3 | 2026-07-27 | 3 lanes; 3 medium — **3 verified, 0 dismissed** | Converging: no critical, no high, and the cross-document lane clean. All three were loop 2's own blast radius. Naming the four groups of stylesheet literals in §4.3 left two of them — the link button's hover and the danger family — with no home in §4.7, so §4.3's claim that "§4.7 places every one of them" had stopped being true the moment it was written. Saying `build_theme` picks the overlay "from the theme's Base column" left `base` nowhere to live: §4.1 defined a theme as a triple of id, label and palette, and a palette holds colours. It is a fourth field now. And §4.4 said `apply_app_theme` repaints "what the stylesheet cannot reach — which is the tray icon", which quietly assumed the switch repaints itself; nothing tells a painter reading `current_palette()` that its colours moved, and INV-6's whole test rests on it. `apply_app_theme` now calls `update()` on every top-level widget and says why |
| 4 | 2026-07-27 | 3 lanes; 1 medium — **1 verified, 0 dismissed** | **Converged.** Two lanes clean, and nothing from an earlier loop returned. The one finding was precision: §7 said "the check lands and passes ... before the first new palette", which reads as covering INV-12 as well, when the focus measurement is a separate gate arriving with ONEUP-0064 and already green on two palettes. `Draft` → `Reviewed`; implementation of ONEUP-0027 is unblocked, after ONEUP-0034 and ONEUP-0064 |
| 5 | 2026-08-24 | 3 lanes, cold; genre pinned `spec`; first loop of a new run — Q1 7 · Q2 1 · Q3 3 · Q4 0, 11 verified, 0 dismissed, all fixed (no severity scale under the four-question gate, so nothing here for §7's tally check to balance; ONEUP-0100). Six open questions resolved clean; one became a finding | **The gate re-armed because the two items this spec defers to were BUILT.** ONEUP-0064 and ONEUP-0076 shipped on 2026-08-21, and every present-tense claim about the tree had to be re-taken against it. **All three lanes independently found the same defect, and it is the one with teeth:** §4.3 said `GREEN`/`RED` "have one call site between them, in `ToggleSwitch.paintEvent`", so an implementer would move the tracks into the palette, repoint `paintEvent`, and leave `focus_keys()` deriving `switchfocuson`/`switchfocusoff` from a colour no theme paints — **and INV-12 would stay green**, because the derivation still clears 3:1 against whatever it derived from. `ui-and-accessibility.md` §7 had warned of exactly this in terms; the spec had not been updated to match. Two more were work already done: `_QSS` has carried `QMainWindow, QDialog { background: $win; }` since 0064, so §8's "the one code change here that is not a theme" was discharged and is deleted, and half the contrast check exists — `contrast()`, `composite()` and `focus_report()` are in `theme.py` and driven from the suite — so §2's "the check does not exist" invited a second WCAG implementation. §8 also sent the implementer to rewrite `ui-and-accessibility.md` §5.4's **What checks this** row, which 0076 had already rewritten correctly. The §2 literal census was stale in both directions (**14 occurrences, 10 distinct**, not thirty and twelve; `#4aa3ff` once as a *tooltip border*, not the accent's stop "in eight places"), and §4.3's four literal groups included the link button's hover, which is already the palette key `linkhov`. The one Q2 was §4.7 calling decorative pairs "measured by nothing" while §4.8 and INV-3 require every exception entry to carry a measured ratio — settled toward measure-and-record-but-compare-against-nothing, since a pair nobody computes cannot be shown to have drifted. Both Q3s were inventions other code binds to: INV-5's gate exempted only "the palette dictionaries themselves" and would have gone red on `_BLACK`/`_WHITE`/`WARN_TINT`/the stop pairs in `local-CI.sh` on day one, and §4.3 mapped a solid-colour literal to `accent`, which holds a `qlineargradient(…)` string that Qt cannot parse in a `border` shorthand. **A fix of mine was caught by 4a step 3 before it landed**: it claimed five of the fifteen focus keys are palette-invariant; running `focus_keys()` over both palettes returned **seven**, and showed `warnfocusfill` varies while `warnfocusink` does not — the sentence names sources now instead of a count. **The eleventh finding came from the 4b sweep rather than a lane**: §7 hands this item four jobs and §3.1 claimed it discharges two, so nothing specified what a picker does when a theme's focus pair cannot be derived — `apply_app_theme` catches that today and applies nothing, a silently dead control, and the except branch names ONEUP-0027 as the item that turns it into a real fallback |
| 6 | 2026-08-24 | 3 lanes, cold; identical brief, packet and scrubbed copy rebuilt from disk; loop 2 of this run, so the spec cap binds — Q1 3 · Q2 3 · Q3 3 · Q4 1, 10 verified, 0 dismissed, all fixed (no severity scale under the four-question gate, so nothing here for §7's tally check to balance; ONEUP-0100) | **A CALM cap: 3 of the 10 landed on text loop 5 wrote, so seven were defects the document already held and the run was not oscillating.** At 740 lines it sits between its siblings (ONEUP-0108's 473, ONEUP-0072's 859), so size is not the signal here; the spec ships and implementation is the third reviewer. **All three lanes converged on §4.7's closing paragraph**, which restated the coverage rule with two of its four routes — a validator built from it turns CI red on `disfg` and on all fifteen *measured elsewhere* keys before a new theme exists. The deepest finding was the coverage UNIVERSE: §4.1 pins the reference set to `midnight`'s authored keys while INV-4's fourth route names only derived keys, which are not in it — so INV-4 could never fire on them and 18 derived tokens escaped the check entirely. Measured at HEAD, 53 keys reach `_QSS`: 29 authored + 3 injected gradients + 15 derived focus + 6 font metrics; INV-4's universe is now the 47 colours and INV-1 keeps the authored set. **`BTN_DANGER` appeared in no list anywhere** — not §4.3's table, its constants sentence, INV-5's conversion list or §8's — and being `_vgradient(BTN_DANGER_STOPS)` it holds no hex, so INV-5's grep could not have caught it either: the restart button would have kept one fill across all eight themes. `Updater._tray_icon` has been the module-level `tray.py::_tray_icon` since ONEUP-0034, and §4.3's *Painted by* column is the map of which module gains `current_palette()` calls, so four tray tokens pointed at `window.py`. **Three findings were loop 5's own collateral, and one was the run's best:** loop 5 resolved `focus_keys()`'s literal `"#ffffff"` to `switchmark`, and that literal is a surface SET standing for both white things on the track — so the focused track would never have been measured against `switchknob`, and a theme with a tinted knob ships a focus state the knob vanishes into while passing INV-2, INV-4 and INV-12. It resolves to both now. Loop 5's fallback paragraph also collided with §4.1/§4.6/§10's claim that the labels are the only strings this item adds, and shipped with no invariant at all — INV-13 now injects a deliberately underivable palette and asserts all three effects, because §10 rules out user-authored themes and INV-2 keeps the eight clean, so nothing else could ever reach that branch. **4a step 3 caught a second bad fix of mine mid-loop**: it said `accent` derives from a stop pair via `_vgradient`, and `ACCENT` is DIAGONAL (`x2:1, y2:1`) with a different second stop, so no stop pair exists for it and `_vgradient` cannot express it |
