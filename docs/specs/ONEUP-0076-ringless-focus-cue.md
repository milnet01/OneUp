# ONEUP-0076 — the ringless focus cue

**Status:** Draft
**Kind:** accessibility
**Roadmap:** ONEUP-0076
**Branch:** v2
**Verified at:** `d18fbf2`, and re-confirmed at `c8fb3f2` — every figure below was computed
or measured against the tree, on PySide6 6.11.0, not recalled. The two commits differ in
`updater.py`; every figure and the §2.1 census reproduce unchanged at both, and the measured
notes in §4.2 and §4.4 cite `c8fb3f2` because that is where they were taken.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** Every control that can take keyboard focus says so, with a cue the app
**derives** from the colours it replaces rather than one anybody authors — because the
obvious cue, the one the app uses today, cannot be made strong enough at any shade.

**Split out of `docs/specs/ONEUP-0064-interface-redesign.md` on 2026-08-03.** That item
keeps the layout redesign; this one takes the focus cue, the derivation and the check. §11
carries the provenance row.

**`docs/standards/ui-and-accessibility.md` owns the rules this works under** — no focus
border (§5), colour never alone (§3). None of it is re-argued here. What this spec adds is
the part §5.4 explicitly leaves to it: a focus treatment that measures, and the computation
that proves it.

## 1. Goal

A keyboard user can always see where they are, in every theme, without a ring or an outline
ever being drawn — and the app can prove it rather than assert it. Sixteen focusable widgets
that show a keyboard user nothing today show them something.

## 2. Background

### 2.1 Sixteen of the thirty-four focusable widgets have no focus cue at all

The standard's §5.4 measures four controls and reports that three of them are weak. The
measurement nobody had run is the one over the whole window:

The sweep below is **new work this item adds** (§4.4), not something the suite prints
today. It runs in `tests/gui-smoke.py`'s existing offscreen harness: build the window,
keep every widget whose `focusPolicy() != Qt.NoFocus`, and ask whether the built
stylesheet carries a `:focus` rule for its object name.

| Widget | Count | `:focus` rule in the sheet |
| --- | --- | --- |
| `QPushButton#GhostBtn` | 7 | yes |
| `QPushButton#LinkBtn` | 5 | yes |
| `QPushButton#BannerBtn` | 4 | yes |
| `QPushButton#RunBtn` | 1 | yes |
| `QPushButton#RestartBtn` | 1 | yes |
| `ToggleSwitch` | 5 | **no** |
| `QToolButton#Disclose` | 5 | **no** |
| `QScrollArea#DetailScroll` | 5 | **no** |
| `QPlainTextEdit#Log` | 1 | **no** |

Thirty-four focusable, eighteen with a rule, **sixteen without** — counted over the window
as constructed, before any run, so the conditional banners and their buttons are included
whether or not they are showing. **Hidden is not the same as unparented, and the sweep sees
only the first.** Measured at `c8fb3f2`: five `size_btn` objects exist, one per `TaskRow`,
all `#LinkBtn` — but only the system row's is parented, so `findChildren` returns that one
and the count above is 34 rather than 38. The four others are real, focusable and invisible
to this sweep. It changes none of the figures here, because `#LinkBtn` already carries a
`:focus` rule and the sixteen-without figure is unaffected; what it changes is INV-1's
guarantee, which cannot break on a control added without a parent. The sixteen are not
leftovers: five of them are the on/off switches, which are the primary control of the
application, and they are painted rather than styled — **no stylesheet colour rule reaches
what `ToggleSwitch` paints.** The one QSS declaration that does reach the class is
`ToggleSwitch { qproperty-highContrast: … }`, a property setter, and §4.2 uses exactly that
seam to hand the painter its focus colour. `ToggleSwitch.paintEvent` ends with a comment
confirming it draws no focus indication.

The class disagrees with itself about this, which is how it stayed unnoticed: the
`ToggleSwitch` docstring says the switch has *"a focus ring so keyboard users can see where
they are"*, and the closing comment in `paintEvent` says *"No focus ring is drawn, by
explicit design decision"*. The second one is true.

**For a widget with no cue at all the binding criterion is SC 2.4.7 (Focus Visible, Level
AA), not the AAA 2.4.13** — §8 carries that correction into the standard. Neither of
2.4.13's exceptions rescues these either: the second applies only where
*"the focus indicator and the indicator's background color are not modified by the
author"*, and these widgets are styled and painted by us throughout
(*Source:* <https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html>).

### 2.2 Where a cue does exist it is weak — and lightening cannot fix it

`docs/standards/ui-and-accessibility.md` §5.4's four figures reproduce exactly, and the two
controls its table omits are no better:

| Control | Rest → focus | Ratio |
| --- | --- | --- |
| `#RunBtn` | `#4aa3ff` → `#5cb0ff` | 1.14:1 |
| `#BannerBtn` | `#4aa3ff` → `#5cb0ff` | 1.14:1 |
| `#RestartBtn` | `#ef6a55` → `#f47c68` | 1.16:1 |
| `#LinkBtn` | `#4aa3ff` → `#6fb6ff` | 1.23:1 |
| `#GhostBtn`, light | `#c4ccd6` → `#4aa3ff` | 1.62:1 |
| `#GhostBtn`, dark | `#38414f` → `#4aa3ff` | 3.91:1 |

**The instinct that produced these is lightening, and it has a ceiling.** Five of the six
focus colours above are a lighter version of their rest colour, because focus reuses hover
and hover lightens. The sixth is the light ghost button, whose `#c4ccd6` → `#4aa3ff` is
actually a *darkening* (relative luminance 0.598 → 0.349) and still reaches only 1.62:1 —
darkening is necessary, not sufficient. Measured against the strongest possible lightening —
pure white:

| Rest fill | vs `#ffffff` |
| --- | --- |
| `btn_accent` top stop `#4aa3ff` | **2.63:1** |
| accent cyan stop `#22d3ee` | 1.81:1 |
| switch track on `#2ecc71` | 2.10:1 |
| `#RestartBtn` top stop `#ef6a55` | 3.06:1 |
| `btn_accent` bottom stop `#2f6fe0` | 4.70:1 |
| switch track off `#e74c3c` | 3.82:1 |

White itself is 2.63:1 against the Run button's **top** gradient stop, so **no lighter shade
of anything reaches 3:1 there at any saturation** — and because a gradient is governed by
its worst pixel, that settles the button. (Its bottom stop `#2f6fe0` reaches 4.70:1 against
white; the binding stop is the light one.) This is the measurement taken on the roadmap
bullet before the spec was written, and it is why the design below darkens.

**Three of these six rows do clear 3:1 against white — the Restart button's top stop at 3.06:1,
the Run button's bottom stop at 4.70:1, and the switch's off-track at 3.82:1 — and that is
the argument for a rule rather than a colour.** A hand-picked lightening could be made to
work on those and nowhere else; the ceiling binds hardest on the accent's top stop, which
governs the most visible surface in the application and the one every theme keeps. A cue
that works on three surfaces and fails on the rest is not a cue.

### 2.3 The light theme's link text already fails ordinary text contrast

`#LinkBtn` is `#4aa3ff` and sits on `#Card`, which is `#ffffff` in `_LIGHT`: **2.63:1**
against a 4.5:1 requirement, and its hover colour `#6fb6ff` is worse at **2.14:1**.
`docs/specs/ONEUP-0027-themes.md` §4.7 checks both pairs and its §4.8, which lists every
pair the check fails today, includes neither. It is in scope here rather than in the layout
item because it is a contrast defect and this is the contrast contract: §4.3 gives the light
link `#326dab` (4.61:1 on its worst surface) and `#446f9c` (4.51:1), and INV-7 measures
them against **every** surface a link rests on, not only `card` — §4.2 puts one on `rowcard`
and `rowhov` and one on the warning banner's tint.

## 3. Scope decisions

### 3.1 The fixed points inherited from ONEUP-0064 (the user, 2026-07-26)

1. **No focus borders.** Ordinary borders are fine and always were; what must not appear is
   a border or an outline drawn *to mark* the focused control. Restated at its original
   width, not widened — `ui-and-accessibility.md` §5.2.
2. **The phone-style on/off switches stay.** They are also the largest group of controls
   with no cue at all today (§2.1), so they are this item's main subject rather than an
   obstacle to it.

**Fixed point 1 survives this design untouched.** Darkening a fill draws no ring, adds no
outline, and changes no geometry.

**One sentence in the standard does not survive it.** §5.1 says focus is signalled *"by
reusing the hover appearance"*. Hover lightens, and §2.2 shows lightening cannot reach 3:1
on these palettes, so the two rules are in conflict and the measurable one wins. §8 carries
the correction into the standard and into `CLAUDE.md`, which repeats it.

### 3.2 What this spec does not decide

The boundaries live in §10. One is worth stating as a decision rather than an omission: the
**layout** — where controls sit, what the header carries, how a task row behaves — is
`ONEUP-0064`'s, and this spec touches it only where a control's rest colour is the input to
a derivation.

## 4. Design

### 4.1 One cue, derived from the surface rather than authored

**One term first, because the rule turns on it.** A control's **rest pixels** are the
colours actually rendered where the control is when it does not have focus — its own fill
where it has one (`btn_accent` for the Run button, the track for the switch), and the
surface behind it where it is transparent (`card` for a ghost or link button). A control has
more than one set of rest pixels when the thing behind it changes: the disclosure sits on
`rowcard` or on `rowhov` depending on the mouse.

> **A focused control's own fill changes to a colour derived from the colour it replaces:
> the smallest blend toward black or toward white — whichever of the two reaches it at the
> lower blend fraction — that measures at least 3:1 against every one of the control's rest
> pixels. Its text is redrawn in whichever of black or white contrasts more with that
> fill.**

**The procedure, stated once so two readings cannot diverge.** The blend fraction `t` runs
from 0.01 to 1.00 in 1% steps, mixing each channel toward the target and rounding to the
nearest integer — that quantisation is what makes §4.3's hexes reproducible, and a binary
search or a finer step would print different ones. Try **both** directions against the
**whole** set of the control's rest pixels, take the smallest `t` in either direction whose
result clears the threshold against every one of them, and raise §6's error only when
neither direction does. Anchoring on one surface and never retrying the other direction is
how a satisfiable set gets reported as unsatisfiable.

**A cue that already clears 3:1 *on pixels that meet SC 2.4.13's area half* is kept, never
re-derived.** The rule supplies a cue where none passes; it is a floor, not a replacement.
**Both halves of that qualification are load-bearing.** The dark `#GhostBtn`'s existing
rest→focus pair measures 3.91:1 (§2.2) and would be kept on ratio alone — but it is a 1 px
border recolour, which is less than the 2 px perimeter SC 2.4.13 requires, so it is
re-derived as a fill and §4.3 carries the result. A bare ratio floor would have kept it. This matters concretely: under the
high-contrast overlay `#GhostBtn` goes `$card` → `$btnhov`, which is `#000000` → `#ffd400`
(**14.67:1**) dark and `#ffffff` → `#0000cc` (**11.22:1**) light, and "smallest blend
reaching 3:1" would *weaken* those to 3.14:1 and 3.03:1 — roughly fourfold, in the one
appearance mode that exists for low-vision users.

Three properties matter, and each one is why it is a derivation and not a palette entry.

**It is relative, so no single authored colour can do the job.** SC 2.4.13 compares the
focused and unfocused states *of the same pixels*, so what counts is the distance from each
control's own rest colour. The palettes already carry an authored `focus` token; measured
as a fill it passes on some surfaces and fails on others in the same theme:

| Rest surface → `$focus` | Ratio | |
| --- | --- | --- |
| dark `card` `#12161c` → `#66b8ff` | 8.52:1 | pass |
| light `card` `#ffffff` → `#0b5fd0` | 5.90:1 | pass |
| `btn_accent` `#4aa3ff` → `#66b8ff` (dark) | 1.24:1 | **fail** |
| switch track on `#2ecc71` → `#66b8ff` (dark) | 1.01:1 | **fail** |

**Against one surface it always succeeds.** For a colour of relative luminance `L`, the
contrast against black is `(L+0.05)/0.05` and against white `1.05/(L+0.05)`. The larger of
the two is smallest where they are equal, at `L = 0.1791`, where both are **4.58:1**. So
every colour in sRGB can reach 3:1 in at least one of the two directions, and the search
cannot fail. A complete sweep of a stride-3 sRGB lattice (86³ = 636,056 colours) evaluating that bound agrees
with it, worst case `#5d60ff` → 4.58:1. (Evaluating the bound is cheap; running the full
*derivation* over the same lattice is the ~230 s figure INV-5 avoids.)

**Against a *set* of surfaces it can fail, and the spec says so rather than assuming
otherwise.** Each surface forbids a band of luminances around itself, and two surfaces far
enough apart can forbid everything: measured, `#000000` and `#989898` admit no colour at
all that clears 3:1 against both, and a coarse sweep of grey pairs finds 192 such pairs. It
does not arise for the surfaces this design actually pairs — `rowcard` and `rowhov` are two
hover states of one row, 0.004 apart in relative luminance in the dark palette and 0.069
apart in the light one — but "cannot happen here" is a property of
today's palettes, not of the rule, and `ONEUP-0027` is about to author six more. So the
search is defined to **fail loudly**: no fill, a named error identifying the control and the
two surfaces, and the theme does not ship. §6 carries the failure mode and INV-5 tests both
halves.

**The same bound gives the text for free.** 4.58 is also above 4.5, so "black or white,
whichever contrasts more with the fill" always clears the 4.5:1 body-text requirement
against it. That matters because deriving a fill and leaving the label alone breaks the
label: light `#GhostBtn`'s `$ghostfg` measures 10.16:1 on `card` and **3.35:1** on the fill
derived from it. The fill and its ink are one derived pair, never separable.

**Gradients take one blend fraction, not one per stop.** Blending toward a fixed target is
**affine** in the source colour, so it commutes with the linear interpolation between the
stops: applying one fraction to both stops gives exactly the colour that fraction would
give at any point in between. (That holds for the white direction as much as the black one
— toward black the blend is also a plain per-channel scale, but affinity is what the
argument needs.) Taking the larger of the two stops' required fractions, the worst pixel
anywhere down the Run button's gradient measures **3.00:1**.

### 4.2 Two mechanisms, because a log pane is not a button

Mechanism A is §4.1: **the fill and its ink change.** It suits anything whose whole area is
chrome, and it satisfies SC 2.4.13's area half without arithmetic — the requirement is an
area at least that of a 2 px perimeter of the component, and a whole fill exceeds it.

Mechanism B is for the two kinds of widget that hold their own scrolling text — one
`#Log` and five `#DetailScroll` panels, where recolouring
every pixel would recolour the content: **an existing rest border changes colour.** No
border is added *on focus*, so fixed point 1 holds and §5.3 of the standard already permits
it. The area half is what makes this work only at width: a 1 px border is *less* than a 2 px
perimeter and would not qualify, so both panels carry a **2 px** border at rest. Both are
rest-state changes this item makes and neither is a focus cue in itself — `#Log` carries
`border: 1px solid $logbd` today and is widened, and `#DetailScroll` carries `border: none`
and gains one. Present focused or not; only the colour moves.

**The surface column is the whole contract, because the rule is "every surface the control
can rest on".** A control that appears in more than one place has a row per surface, not one
row for its object name.
**An overlay row REPLACES its control's base row while the overlay is on; it does not add to
it.** The overlay restates most selectors, so a control's rest pixels under it come from the
overlay's own tokens — which is why deriving a fill for the high-contrast `#GhostBtn` from
the base `card` would be wrong, and why §4.1's floor keeps that pair instead.

| Control | Mechanism | Rest pixels the cue is derived from (§4.1) |
| --- | --- | --- |
| `#RunBtn`, `#BannerBtn` | A | `btn_accent`, both gradient stops |
| `#RestartBtn` | A | the danger gradient, both stops |
| `#StopBtn` (introduced by `docs/specs/ONEUP-0064-interface-redesign.md` §4.1) | A | `card` |
| `#GhostBtn`, in the header and the action row | A | `card` |
| `#GhostBtn`, moved into `SettingsDialog` by `docs/specs/ONEUP-0064-interface-redesign.md` §4.1 | A | the dialog's own surface, which is `card` — the sheet is set on the application, so the dialog inherits it |
| `#GhostBtn` in the warning banner (`retry_btn`), moved there by `docs/specs/ONEUP-0064-interface-redesign.md` §4.1, which keeps the object name | A | `#WarnBanner` only — the same composited tint `warn_copy_btn` takes, resolved the same way in §4.4 |
| `#LinkBtn`, on the card (`log_toggle`, `openlog_btn`, `rollback_btn`) | A | `card` |
| `#LinkBtn` in a banner (`warn_copy_btn`) | A | `#WarnBanner` only — it is inserted into that one banner and no other |
| `#LinkBtn` inside a row's detail panel (`size_btn`) | A | `rowcard` **and** `rowhov` |
| `QToolButton#Disclose` | A | `rowcard` **and** `rowhov` |
| `ToggleSwitch` | A, in `paintEvent` | its own track — `GREEN` / `RED` today, which `ONEUP-0027` §4.3 renames `switchon` / `switchoff` |
| `QPlainTextEdit#Log` | B | `logbd`, widened to 2 px |
| `QScrollArea#DetailScroll` | B | `logbd`, at 2 px — the panel gains a rest border |
| `QPlainTextEdit#Log` and `QScrollArea#DetailScroll`, high-contrast overlay on | B | `$border`, at 2 px. `logbd` is a base key the overlay does not carry, so the overlay row is the one that applies when it is on |
| The primary button family, high-contrast overlay on | A | `$btn`. The overlay's `#GhostBtn` rule already clears 3:1 and is kept unchanged — §4.1's floor, §4.3's note |
| `#StopBtn`, `QToolButton#Disclose` and `#LinkBtn`, high-contrast overlay on | A | `$card`. Every control the overlay does not give a `$btn` fill rests on `$card`, so all three take the `$card` → `$btnhov` pair §4.1's floor already keeps for `#GhostBtn`. `ONEUP-0064` §4.1 creates the overlay rules for the first two and delegates their focus colour here |

**⚠ OPEN — how one object name carries three derivations.** `#LinkBtn` has three rows above
with three different rest-pixel sets, and `#GhostBtn` now has three as well. But §4.4 matches
a styled widget to a row **by object name**, and `_QSS` keys its rules the same way — so
nothing here says how one name resolves to three fills.
`docs/specs/ONEUP-0064-interface-redesign.md` §4.1 hit this and answered it by *renaming*
(*Stop* became `#StopBtn`) "because `docs/specs/ONEUP-0076-ringless-focus-cue.md` matches a
styled control by object name". Two ways out, and the choice is not this document's to make
alone: **rename per surface**, which changes object names `ONEUP-0064` has just fixed and
`ONEUP-0027` keys palette entries to; or **descendant selectors**
(`#WarnBanner QPushButton#LinkBtn:focus`), which renames nothing but means INV-1's matcher
has to resolve a row by surface as well as by name. Until it is settled an implementer
would write one `#LinkBtn:focus` derived from `card` and render it over `rowcard`, `rowhov`
and the banner tint — the 2.83:1 shape §4.2 warns about two paragraphs down.

**The painted switch needs a seam, and there is exactly one that already works.** A
stylesheet cannot colour what `paintEvent` draws, but it can set a Qt property on the class:
`ToggleSwitch { qproperty-highContrast: … }` is that pattern in the code today. The focus
pair arrives the same way — `build_theme` computes it and the sheet assigns it as a
property, with the same mandatory explicit default the existing setter carries, because a
`qproperty-` assignment is not reverted when its rule stops matching.

**The disclosure is the reason the rule says *every* rest colour.** Its row lightens to
`rowhov` under the mouse, so a focused disclosure can sit on either. In the dark palette a
fill derived from `rowcard` alone is `#66696e`, which measures 3.00:1 there and **2.83:1**
on `rowhov` — a fail. Raising `t` from 0.33 to 0.35 gives `#6a6d73` at
3.01:1 against the worse of the two. Two extra percent of blend, and the rule that produces
it is the one written in §4.1.

### 4.3 What that comes to, in the two palettes and two overlays that exist today

Computed, not chosen. Every figure is the output of the check in §4.4.

| Control | Rest | Focus fill | Ratio | Ink |
| --- | --- | --- | --- | --- |
| Run / banner button | `#4aa3ff`→`#2f6fe0` | `#1c3e61`→`#122a55` | 3.00:1 (worst pixel) | `#ffffff` 10.99:1 |
| Restart button | `#ef6a55`→`#d6412a` | `#5d2921`→`#531910` | 3.07:1 (worst pixel) | `#ffffff` 11.64:1 |
| Ghost / link, dark | `#12161c` | `#606367` | 3.01:1 | `#ffffff` 6.04:1 |
| Ghost / link, light | `#ffffff` | `#949494` | 3.03:1 | `#000000` 6.92:1 |
| Disclosure, dark | `#1a1f27`/`#1e242e` | `#6a6d73` | 3.01:1 | `#ffffff` 5.19:1 |
| Disclosure, light | `#f4f6f9`/`#eaeef3` | `#868789` | 3.09:1 | `#000000` 5.84:1 |
| Switch track on | `#2ecc71` | `#186c3c` | 3.08:1 | — |
| Switch track off | `#e74c3c` | `#66211a` | 3.06:1 | — |
| Log / details border, dark | `#262d38` | `#72767e` | 3.04:1 | — |
| Log / details border, light | `#d5dbe2` | `#777b7f` | 3.06:1 | — |
| Stop button, light — ghost text and border on `card` | `#d6412a` at rest, 4.52:1 | `#949494` | 3.03:1 | `#000000` 6.92:1 |
| Stop button, dark — ghost text and border on `card` | `#e0553f` at rest, 4.79:1 | `#606367` | 3.01:1 | `#ffffff` 6.04:1 |
| Link button rest text, light (§2.3's failing pair — see below) | `#4aa3ff`, 2.63:1 on `card` | — | — | moves to `#326dab`: 5.37:1 on `card`, 4.96:1 on `rowcard`, **4.61:1** on `rowhov`, 4.75:1 on the banner tint |
| High contrast, dark — primary buttons | `$btn` `#ffffff` | `#949494` | 3.03:1 | `#000000` 6.92:1 |
| High contrast, light — primary buttons | `$btn` `#000000` | `#5c5c5c` | 3.14:1 | `#ffffff` 6.69:1 |
| High contrast, dark — `#GhostBtn` | `$card` `#000000` | **unchanged**, `$btnhov` `#ffd400` | **14.67:1** | unchanged |
| High contrast, light — `#GhostBtn` | `$card` `#ffffff` | **unchanged**, `$btnhov` `#0000cc` | **11.22:1** | unchanged |
| High contrast — `#StopBtn`, `#Disclose`, `#LinkBtn` | `$card` | `$btnhov` — the kept pair, not a derivation | **14.67:1** dark / **11.22:1** light | `$btntext`, 14.67:1 / 11.22:1 |
| High contrast — `#Log` / `#DetailScroll` border | `$border`, widened to 2 px in the overlay too | `#949494` / `#5c5c5c` | 3.03:1 / 3.14:1 | — |
| Link button hover text, light | `#6fb6ff` on `#ffffff`, **2.14:1** | — | — | moves to `#446f9c`: 5.25:1 on `card`, 4.85:1 on `rowcard`, **4.51:1** on `rowhov`, 4.64:1 on the banner tint |
| Ghost button `:hover` / `:checked` ink, light | `#4aa3ff` on `#ffffff`, **2.63:1** | — | — | moves to `#326dab`, the same ink as the link — `retry_btn` puts a ghost button on the banner tint too, so it takes the same worst surface |
| Ghost button `:hover` / `:checked` ink, dark | `#4aa3ff` on `#12161c`, **6.89:1** | — | — | unchanged — it already clears 4.5:1 |
| `#LinkBtn` in the warning banner | the banner tint composited over `card` | derived from that composite | ≥3:1 | black or white |
| `ghostbd` on `card` — the ghost button's rest border (`ONEUP-0027` §4.8 hands it here) | light `#c4ccd6` 1.62:1, dark `#38414f` 1.76:1 | moves to `#8f959c` / `#5e6570` | **3.02:1** / **3.09:1** | — |

Four of these are worth reading twice. The Run button's focused fill is a **dark navy**,
which is the opposite of what the app does today and the whole point of §2.2. The switch's
track darkens rather than changing hue, so the red/green distinction and the bar-and-circle
shape both survive focus untouched — `ui-and-accessibility.md` §3 is not weakened by the cue
landing on the same surface. **The Stop button's rest colour is per-palette, not one danger
red**: `#d6412a` reads at 4.52:1 on the light card but only 4.02:1 on the dark one, so dark
takes `#e0553f` at 4.79:1. **The danger colour is a rest-state affordance and does not
survive focus** — on focus the border takes the ink like every other retained outline,
because a border kept at its rest colour would sit at 1.49:1 against the fill and be
invisible. A focused stop button therefore looks like any other focused button on `card`,
and what identifies it is its **label**, which is where a control's identity belongs
(`ui-and-accessibility.md` §3 — never colour alone). And the light **link button's rest text moves** from `#4aa3ff` to
`#326dab`, which is what closes §2.3's 2.63:1 pair. **The light ink is one value for every
surface rather than one per row**, chosen as the smallest blend toward black clearing 4.5:1
against the worst of them — `rowhov` `#eaeef3` — which is what stops the object-name question
in §4.2 reaching the ink. The dark palette adopts nothing: `#4aa3ff` already measures 4.60:1
on its own worst surface (the banner tint over `card`) and `#326dab` would measure 2.26:1
there, so dark keeps `#4aa3ff` and `#6fb6ff`.

**High contrast takes mechanism A, like every other button — its rest border is not the
cue.** The overlay's buttons do carry a 2 px border at rest, which is why this looks at first
like mechanism B; but the pixels the overlay moves on focus are the *fill*
(`background: $btnhov`), and recolouring that border would not work anyway — dark `$border`
`#ffffff` → `$focus` `#ffd400` is **1.43:1** and light `#000000` → `#0000cc` is **1.87:1**.

**The overlay's `#LinkBtn:focus` is replaced rather than kept, and it is the one overlay
rule that fails outright.** It moves text alone (`color: $text` over the rest `$link`), which
measures **1.65:1** dark and **1.87:1** light — below 3:1 in both, so no recolour of that
text can carry the cue. It takes a fill on focus like every other overlay control, which is
the `$card` → `$btnhov` pair above.

**Only the overlay's primary family is derived, and its ghost button is left alone.** The
overlay groups `#GhostBtn:focus` with the primary buttons and sets `background: $btnhov`,
so its focus pair is `$card` → `$btnhov` — `#000000` → `#ffd400` at **14.67:1** dark and
`#ffffff` → `#0000cc` at **11.22:1** light. (`$btn`, pure white or pure black, is what
`:hover` sets; it is not the focus value.) Deriving these would replace them with the
smallest blend reaching 3:1 and cut the cue roughly fourfold, in the appearance mode that
exists for low-vision users. §4.1's floor is why it does not: a pair already clearing 3:1
is kept.

**The overlay also has to widen the log border, or mechanism B silently fails under it.**
`_HC_QSS` restates `QPlainTextEdit#Log` with `border: 1px solid $border`, which would
override the 2 px rest border §4.2 requires and drop the cue below SC 2.4.13's area
threshold in exactly the appearance mode that most needs it. That rule is widened to 2 px in
the same commit, and §4.3 carries its derived colour. `_HC_QSS` carries no
`QScrollArea#DetailScroll` rule at all, so the overlay's 2 px rest border for that panel is
**created** here rather than widened.

**Two rows above name colours that are not palette tokens, and both need a stated
resolution.** The warning banner's background is a two-stop **alpha** gradient
(`rgba(233,178,63,0.20)` → `rgba(233,178,63,0.04)`) rather than a flat token, so the link
button inside it has no hex to blend from. §4.4 resolves it by compositing the tint over the
token beneath — `card` — at each stop's alpha, and measuring against both ends; that keeps
the check a pure computation with no rendering. And `ghostbd` on `card` is the pair
`ONEUP-0027` §4.8 hands to this item with the instruction that it "cannot be deferred to an
item that has already shipped": the ghost button's rest border is its boundary, 3:1 is the
right bar, and it is met by moving `ghostbd` rather than by any focus treatment — `#c4ccd6` → `#8f959c` at 3.02:1 on `#ffffff`, and `#38414f` → `#5e6570` at 3.09:1 on
`#12161c`. INV-8 measures it.

### 4.4 The check

A pure computation, in `oneup/gui/theme.py` beside the derivation it verifies, driven from
`tests/gui-smoke.py`. No rendering and no screenshot, which is what lets it run over a
theme nobody has written yet.

**`oneup/gui/theme.py` and `oneup/gui/window.py` do not exist at the commit this spec is
verified against.** They are the module names `docs/specs/ONEUP-0034-gui-modules.md` §4.2
creates, and that item lands first (`oneup-2.0.md` §5.2). Every module path in this spec is
a post-split name, not a claim about today's tree, which is one file.

It has two halves, and the second is the one that catches a regression a palette change
cannot cause:

1. **Every derived pair is measured.** For each control in §4.2's table, in each theme and
   with the high-contrast overlay both on and off: the focus fill against every rest surface
   the control has (≥ 3:1), and the ink against the fill (≥ 4.5:1). Gradients are sampled at
   **101 points** down their length, not only at the stops — that is what produces §4.3's
   "worst pixel" figures. A **translucent** rest colour is resolved before measurement by
   compositing it over the token beneath it at its own alpha, at each stop; no rendering is
   involved, so the check stays a pure computation.
2. **Every focusable widget is accounted for.** The window is built offscreen **and each
   dialog it can open is opened in turn** — Settings, Repositories and Rollback, which are
   `QDialog` subclasses the check constructs directly, and About, which is **not**: it is a
   `QMessageBox` built and `exec()`d inside `Updater.show_about`, so the check builds the
   equivalent box rather than calling that method, which would block —
   every widget with `focusPolicy() != Qt.NoFocus` is collected, and each must be covered by
   a row of §4.2's table — by object name for a styled one, by class for a painted one. A widget
   matching nothing fails the check. This is what stops a control being added later with no
   cue, which is exactly how the sixteen in §2.1 accumulated.

**⚠ OPEN — the dialog half of that sweep is red on day one, and by how much is measured.**
Built offscreen at `c8fb3f2` and swept the way half 2 describes, the three dialogs and the
About box hold **21 focusable widgets**, of which **six match no row of §4.2**:
`RepoManagerDialog` has a `QScrollArea` with no object name (its other four are `#GhostBtn`,
`#RunBtn` and two `ToggleSwitch`); `RollbackDialog` has an unnamed `QListWidget` (its other
two are covered); and the About box contributes two unnamed `QPushButton`s and Qt's own
`QLabel#qt_msgbox_label` and `QLabel#qt_msgbox_informativelabel`. `SettingsDialog`'s nine
are all `#GhostBtn` and are covered.
None of the six is a control OneUp styles or paints — they are Qt-supplied chrome — and
`docs/specs/ONEUP-0064-interface-redesign.md` §10 excludes `RepoManagerDialog` and
`RollbackDialog` from its own sweeps, so no other item covers them either. §6 says
over-covering is the safe direction and costs "a row in §4.2 and nothing else", but a row
means deriving a focus fill for chrome the application does not own. The decision is
whether INV-1 **covers** those six with rows, or **excludes** unstyled Qt-supplied chrome by
a stated rule and §10 records it. It is not settled here because it changes what the check
asserts on day one.

**It is deliberately a superset of what `ONEUP-0027` needs.** That spec's §4.7 defers the
focus measurement here and says its own job is to supply palettes that pass it; the
per-theme loop above is what it passes them to.

## 5. Correctness invariants

- **INV-1** Every widget with `focusPolicy() != Qt.NoFocus` — in the main window **and in
  every dialog reachable from the window** — is covered by a row of §4.2's mechanism table.
  *Test:* `tests/gui-smoke.py` builds the window offscreen, opens each dialog in turn,
  collects those widgets, and fails naming any whose object name and class match no row. A row qualified by the
  overlay (the high-contrast entry) is matched as a variant of its object name, not as a
  name of its own.
  Breaks the moment a control is added without a focus treatment — the state §2.1 measured
  at sixteen widgets. The dialog half is not padding: `docs/specs/ONEUP-0064-interface-redesign.md` §4.1 moves *Repositories* and
  *Recenter* into `SettingsDialog`, so a window-only sweep would stop covering two controls
  it covers today.

- **INV-2** For every row of §4.2, in every theme, with the high-contrast overlay on and
  off, the pixels the focus state changes — the fill under mechanism A, the border under
  mechanism B — measure at least 3:1 against **every** rest pixel colour named in that row.
  Where a control keeps a rest **border** while its fill changes, that border **takes the
  ink colour** and is measured against the new fill — a triple, not a pair. It cannot keep
  its rest colour: `ghostbd`'s new value and the fill are both the smallest blend from
  `card` in the same direction, so they land on the same colour and measure 1.00:1 (light)
  and 1.03:1 (dark). Taking the ink instead inherits §4.1's 4.58 bound — 6.92:1 and 6.04:1
  on the two shipped palettes.
  *Test:* the §4.4 computation, driven from `tests/gui-smoke.py`. Breaks on a fill derived
  from one rest colour but rendered over another — the disclosure-on-`rowhov` case, which
  measures 2.83:1 if the rule is written against `rowcard` alone — and breaks on a retained
  border left unmeasured, which is the shape the stop and ghost buttons take: both keep an
  outline while their fill moves underneath it.

- **INV-3** For every mechanism-A control that carries text, the focused ink measures at
  least 4.5:1 against the focus fill. Mechanism-B controls are out of scope by construction:
  their fill and their text do not move.
  *Test:* the same computation. Breaks if a fill is derived and its label left at the
  theme's resting colour: light `$ghostfg` on its own derived fill measures 3.35:1.

- **INV-4** No focus state changes any widget's geometry, and no `:focus` rule introduces a
  `border` or `outline` property that its rest rule does not already set.
  *Test:* two halves, because the window has two rendering paths. For the styled controls,
  `tests/gui-smoke.py` parses the built stylesheet, expands every `border` shorthand into
  its width, style and colour parts, and for each selector carrying a `:focus` rule asserts
  that rule sets no `outline` at all and no border width, style or radius its rest rule does
  not already set to the same value — colour is the only thing a focus rule may move — and
  that each `:focus` rule is emitted **after** that same selector's `:hover` and `:checked`
  rules, which is the ordering §6 relies on this parse to catch. For
  the painted controls, which no stylesheet parse can see, it renders `ToggleSwitch` to an
  image focused and unfocused and asserts the focused image is the unfocused one under a
  **consistent colour-to-colour mapping**: any two pixels sharing a colour in the unfocused
  render still share one in the focused render. Darkening the track satisfies that by
  construction, and a ring drawn inside the fixed rect breaks it, because two pixels that
  were both track become one track and one ring.
  **Neither weaker form works, and both are worth naming because both look right.**
  "Introduces no colour the unfocused render does not contain" is red against this very
  design — §4.3 moves the on-track from `#2ecc71` to `#186c3c`, which is a new colour — and
  it is also blind to a ring drawn in a colour already on screen, such as the white knob or
  the white `_paint_state_shape` pen. "Differ only in pixel colour, never in which pixels
  are painted" is vacuous the other way: an inset ring repaints pixels the track had already
  painted, so it moves only their colour and passes. Asserting `sizeHint()` alone would be vacuous — `__init__` calls
  `setFixedSize(56, 30)`, so the size cannot move whatever the painter does; the thing worth
  guarding is a ring drawn *inside* that fixed rect. Breaks on a
  focus ring in either path, on a border present only when focused, and on a `2px` focus
  border over a `1px` rest border — the 33 px → 37 px resize `ui-and-accessibility.md` §5.4
  measured.

- **INV-5** The single-surface derivation returns a pair for every sRGB colour, and the
  multi-surface search either returns a pair clearing the threshold against every surface or
  fails with a named error identifying the control and the surfaces. It never returns a pair
  that fails.
  *Test:* a unit check over a **stride-16** sRGB lattice (16³ = 4,096 colours, ~1.5 s;
  the stride-3 lattice costs ~230 s of derivation in pure Python — extrapolated from a
  measured 1,331-colour run — and is a one-off, not a suite check) asserting a pair is returned for each single-surface case and that both its ratios
  clear their thresholds; plus the pair `#000000` / `#989898`, which admits no fill at 3:1
  and must raise rather than return. Breaks if the search is written in one direction only —
  toward white alone fails at `#4aa3ff`, which reaches 2.63:1 at most — and breaks if an
  unsatisfiable surface set returns a best-effort colour instead of raising.

- **INV-6** No state is signalled by colour alone: the switch keeps its bar-and-circle
  shape, and every badge keeps its text.
  *Test:* `tests/gui-smoke.py` asserts `ToggleSwitch._paint_state_shape` is reached in both
  checked states, that each badge's text is non-empty, and that the state shape measures at
  least 3:1 against the **focused** track as well as the resting one — 6.46:1 and 11.68:1
  today. Breaks if the focus treatment is implemented by replacing the painter rather than
  recolouring its track, and breaks if a later theme darkens a track until the white mark on
  it stops reading. `ONEUP-0027` §4.7 checks that shape against resting tracks only, so the
  focused pair has no other home.

- **INV-7** Every text colour **this item introduces or moves** measures at least 4.5:1
  against the pixels behind it, in each of its states — rest, hover and focus — in every
  theme. That is the link button's rest and hover text, the ghost and stop labels, and every
  derived focus ink.
  *Test:* the §4.4 computation, extended to those rest and hover pairs. Breaks on the light
  link button as it stands today — `#4aa3ff` on `#ffffff` is 2.63:1 at rest and `#6fb6ff` is
  **2.14:1** on hover — the pair §2.3 measured, which §4.3 closes with `#326dab` and
  `#446f9c`. **Every surface counts, not just `card`:** `#3779bd` would have read 4.53:1 on
  `card` and only 4.19:1 on `rowcard`, 3.89:1 on `rowhov` and 4.01:1 on the banner tint, so
  an ink measured against `card` alone is red on day one for `size_btn` and `warn_copy_btn`.
  It breaks equally on the ghost button's `:hover` and `:checked` ink,
  which is `#4aa3ff` on the same light `card` — the same colour on the same surface as the
  link's rest defect — so §4.3 closes all three the same way.
  **Scoped deliberately:** the whole-palette 4.5:1 sweep belongs to
  `ONEUP-0027` §4.7, which owns light `lastrun` (3.07:1 on `card`, 2.71:1 on `win`) and light
  `amber` under its §4.8, and which declares `disfg` on `disbg` exempt. That section also owns
  every non-text 3:1 pair this item does not introduce — the ghost's `:hover` **border**
  among them, which moves to the same `#4aa3ff` and is a border rather than ink. An unscoped version
  of this invariant would fail on day one against three pairs this item never touches.

- **INV-8** The ghost button's rest border measures at least 3:1 against the surface it is
  drawn on, in every theme.
  *Test:* the §4.4 computation, extended to that rest pair — §4.4's two halves measure a
  focus fill against its rest surfaces and an ink against that fill, and a rest border
  against the surface behind it is neither. Breaks on both shipped palettes as they stand — `#c4ccd6` on
  `#ffffff` is 1.62:1 and `#38414f` on `#12161c` is 1.76:1 — which is the pair
  `ONEUP-0027` §4.8 hands to this item with the instruction that it cannot be deferred to an
  item that has already shipped. §4.3 closes it at 3.02:1 and 3.09:1.

## 6. Failure modes

- **A theme is added whose surface sits at the 4.58:1 worst case.** The derivation still
  returns a pair; the fill is simply near-grey. Nothing fails, and INV-2 records the actual
  ratio, so a palette that produces an ugly-but-conforming cue is visible rather than
  silent.
- **A control is added with no rest fill to derive from.** The §4.4 sweep fails it by name
  (INV-1) rather than letting it inherit nothing. The fix is a row in §4.2, which forces the
  question of what surface it rests on.
- **A control's rest surfaces are too far apart for any fill to clear 3:1 against all of
  them.** §4.1 carries the evidence and the bound; what belongs here is the response. The
  derivation raises rather than returning a best-effort colour, naming the
  control and both surfaces, and the theme does not ship. **At runtime the app must not die
  of it:** `apply_app_theme` catches the error, falls back to Follow system, and reports the
  theme as unusable — the same posture `ONEUP-0027` §7 takes for a missing palette key, which
  is to fail loudly at the boundary rather than half-apply. It cannot arise from today's two
  palettes, where the only multi-surface control pairs `rowcard` with `rowhov`, which sit 0.004
  apart in the dark palette and 0.069 apart in the light one; it is guarded because `ONEUP-0027` authors six more palettes and
  nothing stops one of them separating a row's two states widely.
- **The high-contrast overlay is appended after the base sheet and overrides it.** Its
  `:focus` rules must still be emitted after its own `:hover` and `:checked` rules, or a
  focused checked control shows nothing — `ui-and-accessibility.md` §5.5. INV-4's parse
  reads the built sheet, overlay included, so an ordering mistake is caught in the same
  place.
- **A gradient whose two stops demand opposite directions.** The direction is decided per
  colour, so a gradient straddling `L = 0.1791` could have one stop needing to darken and one
  needing to lighten, and then no single blend fraction serves both. Both of today's
  gradients darken, but `ONEUP-0027` §4.2 moves the accent into the palette and authors six
  more. The direction is therefore chosen **once per gradient**, from the stop with the
  tighter constraint, and if that direction cannot carry the other stop to 3:1 the check
  fails the theme by the same route as the unsatisfiable surface set above.
- **`Qt` reports a widget as focusable that the user can never reach**, such as a scroll
  area inside a collapsed panel. INV-1 covers it anyway, which costs a row in §4.2 and
  nothing else. Over-covering is the safe direction.

## 7. Tests

| Invariant | Where | What it does |
| --- | --- | --- |
| INV-1 | `tests/gui-smoke.py` | builds the window and each dialog offscreen and sweeps the widget tree |
| INV-2, INV-3, INV-7 | `oneup/gui/theme.py` computation, driven from `tests/gui-smoke.py` | the ratio arithmetic, over every theme and both overlay states |
| INV-5 | `oneup/gui/theme.py` unit check | the stride-16 sRGB lattice, plus the `#000000` / `#989898` pair that must raise rather than return — neither is per-theme |
| INV-4 | `tests/gui-smoke.py` | parses the built stylesheet, including `:focus` rule ordering; its second half checks the focused and unfocused `ToggleSwitch` renders are related by a consistent colour-to-colour mapping |
| INV-6 | `tests/gui-smoke.py` | asserts the switch's state shape survives, against the focused track as well as the resting one |
| INV-8 | `oneup/gui/theme.py` computation | the ghost button's rest border against its surface |

**The figures in §4.3 are the check's output, not transcriptions.** The computation prints
every pair it measures, so the table is regenerated rather than re-derived by hand — which
is what keeps it true after `ONEUP-0027` adds six palettes.

**No new test file.** `docs/standards/testing.md` §2 applies unchanged: the sweep builds a
window, so it redirects `HOME` and the state paths the way `tests/gui-smoke.py` already
does.

## 8. Docs & release

- **`docs/standards/ui-and-accessibility.md` §5.** §5.1's *"reusing the hover appearance"*
  becomes the derived treatment; §5.3's testable form gains the area half of SC 2.4.13,
  which it does not currently state and which is what rules out a 1 px border recolour;
  §5.4's table of four ratios is replaced by §4.3's; §5.5 quotes the base sheet's comment
  *"Keyboard focus reuses the HOVER look"*, which this item deletes from the code, so the
  quotation goes with it. The section's **What checks this** table gains rows for the new
  invariants, and its §5.4 row — which today says nothing computes contrast anywhere in the
  suite — names this item's computation instead.
- **§5.4's conformance claim is wrong today and is corrected, not merely sharpened.** It
  says *"WCAG 2.2 SC 2.4.7 (Focus Visible) is still met"*. §2.1 measures sixteen focusable
  widgets with no cue at all, five of them the on/off switches, whose `paintEvent` draws the
  whole control and no focus indication — a keyboard-operable control with no visible
  indicator fails SC 2.4.7, which is Level **AA**. The standard's sentence was written when
  only the four styled controls were in view. So the honest statement is that OneUp fails
  2.4.7 (AA) today for those sixteen, that this item is what makes 2.4.7 true, and that SC
  2.4.13 (Focus Appearance, Level **AAA**) is met on top of it.
- **`docs/specs/ONEUP-0028-accessibility.md` §5 is stale in three ways and is corrected in
  the same commit.** It promises *"QSS `:focus` rules for the **eight** styled focusable
  controls"*, naming `#Disclose`, `#Log` and `#DetailScroll` among them — §2.1's sweep finds
  no `:focus` rule for any of those three. And it specifies *"A 2 px accent outline (HC
  overlay: 3 px, palette key `hcfocus`)"*, which the 2026-07-25 no-focus-ring decision
  forbids outright and which was never built. Third, it states that `ToggleSwitch.paintEvent`
  draws a *"**double** ring (white outer, dark inner) when `hasFocus()`"* — `hasFocus` appears
  nowhere in `updater.py`, and that method's own closing comment says no focus ring is drawn.
  That is the claim closest to this item's subject, and it is the one a reader would most
  reasonably trust. That spec is shipped, so this is a correction
  to a record rather than a change of plan — and that document already recorded the
  underlying defect itself, listing *"No `:focus` rule anywhere in the QSS"* as a
  *"WCAG 2.4.7 failure"*, the same conclusion this section draws above and independent
  corroboration of it. It is in its **Background — what is broken today** section, under
  *Partially sighted*, **not** in its §2, which is *Announcements*: that document leaves its
  `##` sections unnumbered and numbers only the `###` subsections under *Design*, so a bare
  "§2" resolves to the wrong place.
- **`CLAUDE.md` §6** repeats *"focus reuses the hover look"* in its trap list and is
  corrected in the same commit. The trap that stays is the one that cost the bug: no focus
  ring, because Qt draws it square and a focus border resizes the widget.
- **`docs/specs/ONEUP-0027-themes.md`.** Its §4.7 defers the focus measurement to this item
  and its §4.8 hands over `ghostbd` on `card`; both already name this item, so neither needs
  repointing. §4.7 does gain a row for `logbd` drawn on `rowcard` and on `rowhov` — §4.2 gives
  `#DetailScroll` a border in that token and the panel is `background: transparent`, so it
  is the row beneath that it is read against, not `logbg`. That adds a pair the existing
  decorative disposition does not cover; the `logbd`-on-`logbg` row stands unchanged.
- **The palettes gain keys.** `_QSS` is one template substituted with either `_DARK` or
  `_LIGHT`, so a colour that differs by palette cannot be a literal in the sheet:
  `ghostbd`'s new value and every derived focus pair are palette keys. `ONEUP-0027` §4.7
  requires every key to be covered by its pair table or declared decorative, and says a key
  in neither **fails** its check — so this item owes that classification rather than leaving
  it to be found. The derived keys are named `focusfill` and `focusink` per control family,
  and are declared to `ONEUP-0027` as a named class **measured elsewhere**, carrying this
  item's INV-2 and INV-3 as the reason. They cannot sit in that spec's pair table, whose
  pairs are fixed, because their values are recomputed per palette by the §4.4 computation;
  and they are not decorative, because they are measured.
- **`CHANGELOG.md`** gains an `[Unreleased]` entry under **Changed**. It ships inside 2.0;
  there is no 1.4.x release of it, and no version site moves.
- **No marker, no engine change, no packaging change.** The window's argv to the engine is
  untouched, so `docs/reference/marker-protocol.md` is not in scope.

## 9. Alternatives considered (and rejected)

- **Keep lightening, pick a stronger light.** Impossible on the accent rather than
  unattractive: pure white measures 2.63:1 against the Run button's fill, so no lighter
  colour exists that reaches 3:1 (§2.2). It is not impossible everywhere — the Restart
  button's top stop reaches 3.06:1 against white — which is the point: a lightening rule
  would work on one control and fail on the accent, the surface every theme keeps and the
  most visible in the application.
- **Use the palette's existing `focus` token as the fill.** It is authored per theme and
  already checked against `win` and `card`, so it looks like the answer. It fails because
  SC 2.4.13 is relative: the same token measures 8.52:1 on the dark card and 1.24:1 on the
  accent button (§4.1).
- **Change the accent so lightening works.** The azure→cyan is the application's signature
  and `ONEUP-0027` §4.2 keeps it for `midnight` and `daylight` deliberately. Recolouring the
  most visible surface in the app to work around a focus cue is the tail wagging the dog,
  and it would still leave every future theme free to reintroduce the problem.
- **A focus ring or outline.** Excluded by fixed point 1, and independently a bad fit: Qt
  ignores `outline-radius`, so a ring draws square around rounded buttons, and a border
  added on focus resizes the widget by 4 px (`ui-and-accessibility.md` §5.4).
- **Recolour an existing border everywhere instead of filling.** This is mechanism B, and it
  works only where the border is at least 2 px — SC 2.4.13's area half. Applying it to the
  buttons would mean widening every rest border to 2 px purely to carry a cue, which is a
  visible change to every control in service of an invisible one.
- **Animate the focused control** — a pulse or a glow. Rejected for two reasons that are not
  taste: a moving indicator is the one kind a still comparison of focused and unfocused
  pixels cannot measure, so it would take the whole of §4.4 away; and motion introduced as
  the *only* cue is worse for the users this item exists for than the static one it would
  replace.

## 10. Out of scope

- **The layout redesign.** `ONEUP-0064`, which this was split from: where controls sit, what
  the header carries, the task row's click target, tab order, and target sizes. The two
  land in the same slot of `oneup-2.0.md` §5.2, and that section states the dependency in
  one direction: **this item needs the layout and object names `ONEUP-0064` settles**, so
  0064 lands first. `ONEUP-0064` §10 carries the two named hooks; this is a pointer to it,
  not a second statement of it.
- **Authoring the six new palettes.** `ONEUP-0027`, which lands after this item and passes
  its palettes to this item's check.
- **Ordinary rest-state text contrast across the whole palette.** `ONEUP-0027` §4.7 owns it,
  including light `lastrun` and light `amber` under its §4.8, and the `disfg`/`disbg`
  exemption. This item measures only the colours it introduces or moves.
- **Wrapping any string for translation.** `ONEUP-0032`, last (`oneup-2.0.md` §5.2).
- **A new theme, or any change to what the app *does*.** This item changes how focus is
  drawn and nothing else.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 0-split | 2026-08-03 | — | **Provenance, not a review — no reviewer was dispatched to produce this row.** This document was split out of `docs/specs/ONEUP-0064-interface-redesign.md` on 2026-08-03, taking the focus cue, its derivation and its check; that item kept the layout redesign. The parent had run three cold-eyes loops (24, 34, 35 verified) and converged **by cap rather than clean** at 762 lines, with fix collateral outrunning draft defects two loops running — 24 → 13 → 8 draft against 0 → 21 → 27 collateral. Across those three loops and nine lanes essentially every finding fell in this half. **Those loops were run against a document that no longer exists, so none of their assurance transfers**: this spec runs the gate from loop 1 on its own bytes. Invariants were renumbered INV-1…INV-8 from the parent's INV-1, 2, 3, 4, 5, 8, 11 and 13; nothing outside the parent had cited them, and the parent's own numbering stays with it. |
| 1 | 2026-08-18 | 2 lanes, cold; genre pinned spec; Q1 4 · Q2 4 · Q3 5 · Q4 1 — all 14 verified, 0 dismissed, of which 12 fixed and 2 surfaced rather than fixed (no severity scale under the four-question gate, so nothing here for §7's tally check to balance; ONEUP-0100) | **The first gate on this document's own bytes, and the 0-split row was right that none of the parent's assurance transfers.** Both lanes independently led with the same defect, and it is a recurrence rather than a new one: §4.1 stated two different algorithms — the boxed rule preferred black (*"or toward white, when black cannot get there"*) while the procedure two paragraphs below took *"the smallest `t` in either direction"*. Reproduced: the two agree on all eleven surfaces the shipped palettes use, because every one has a single viable direction, and diverge on any mid-luminance surface — `#5c5c5c` derives `#070707` under the rule and `#aeaeae` under the procedure. `ONEUP-0027` authors six more palettes. The parent's own parent-3 row records fixing *"the rule box stated two different algorithms"* on 2026-08-03; it survived the split, which is the case for gating a split document from loop 1. **The findings the lanes could raise but not settle were settled by running the thing.** Both asked what the dialogs actually contain, neither having `Bash`. Built offscreen: the three dialogs and the About box hold 21 focusable widgets, six of which match no row of §4.2 — an unnamed `QScrollArea`, an unnamed `QListWidget`, and the About box's two unnamed `QPushButton`s plus Qt's own two message-box labels. So INV-1's dialog half is red on day one, and `ONEUP-0064` §10 excludes both dialogs from its sweeps, so nothing else owns them. **Three more came from measuring what the document only described.** The overlay's `#LinkBtn:focus` moves text alone, `$link` → `$text`, which is 1.65:1 dark and 1.87:1 light — below 3:1, so the overlay carried a control whose cue could not work at any colour, and §4.3 had no row for it. `_HC_QSS` carries no `QScrollArea#DetailScroll` rule at all, so *"both overlay rules are widened to 2 px"* named one rule that exists and one that has to be created. And §8 called `ONEUP-0028` §5 stale in two ways when it is stale in three — it also claims `ToggleSwitch.paintEvent` draws a double ring *"when `hasFocus()`"*, and `hasFocus` appears nowhere in `updater.py`. **Two were surfaced rather than fixed, both because they change what the check asserts and both reaching sibling items.** How one object name carries three rest-pixel sets, given §4.4 matches by object name and `ONEUP-0064` §4.1 answered the same question by renaming; and whether INV-1 covers the six uncovered dialog widgets with rows or excludes unstyled Qt chrome by a stated rule. Each now carries a ⚠ OPEN block holding the measurement. **Collateral swept and moved in the same commit:** the rewritten rule sentence was restated in `ROADMAP.md` twice and in `docs/plans/ONEUP-0057-documentation-set.md` once. `ONEUP-0064`'s loop-log rows carry the old wording and were deliberately left — a loop log records what that pass found. Status stays Draft: the run did not return an empty loop and two decisions are open. |
| 2 | 2026-08-18 | 2 lanes, cold; identical brief, packet rebuilt from disk; Q1 2 · Q2 3 · Q3 2 · Q4 1 — all 8 verified, 0 dismissed, all fixed. Cap reached (2 for a spec); the run files its tail and exits | **Both lanes independently led with the same defect, and it was loop 1's own fix.** Loop 1 rewrote INV-4's painted half to assert the focused render *"introduces no colour the unfocused one does not already contain"*. That is false against the design this document mandates — §4.3 moves the on-track from `#2ecc71` to `#186c3c`, which is a new colour — so the assertion is red on a correct implementation, and one lane added the other half: a ring drawn in a colour already on screen (the white knob, the white `_paint_state_shape` pen) adds nothing new, so the one failure it exists to catch passes. Both weaker forms are now stated and rejected by name, and the assertion is a consistent colour-to-colour mapping, which a recolour satisfies by construction and a ring breaks. §7 restated the rejected form and was aligned. **This is the 4a-min pattern exactly: loop 1's fix added assertive text, and the added text was what loop 2 spent its strongest finding on.** **The best pre-existing finding needed arithmetic no lane could run.** One lane worked out by hand that §4.3's light link ink `#3779bd` — measured only on `card` — fails on the row surfaces, estimating 4.19:1 and 3.89:1; executed, those are exactly right, and the banner tint is 4.01:1. §4.2 puts a `#LinkBtn` on `rowcard`/`rowhov` (`size_btn`) and one on the banner (`warn_copy_btn`), so INV-7 was red on day one against a pair this item moves. Both inks are now one value derived against the worst surface — `#326dab` and `#446f9c`, worst 4.61:1 and 4.51:1 on `rowhov` — which also keeps the object-name question in §4.2 away from the ink. The dark palette adopts neither: `#4aa3ff` already measures 4.60:1 on its own worst surface and `#326dab` would measure 2.26:1 there. **A lane's open question turned into the run's most interesting fact.** It asked whether five `size_btn` instances exist, which would make the census 38 rather than 34. Executed: five distinct objects do exist, one per `TaskRow`, all named `#LinkBtn` — but only the system row's is parented, so `findChildren` returns one and 34 is correct. Hidden is not the same as unparented, and §2.1 claimed the count included everything *"whether or not they are showing"*. The four others are real, focusable and invisible to the sweep, which is a hole in INV-1's guarantee rather than in the figures. **Two more contradictions with teeth.** §4.1's floor — *"a cue that already clears 3:1 is kept"* — is a bare ratio test, and the dark `#GhostBtn`'s existing 3.91:1 clears it while being a 1 px border that fails SC 2.4.13's area half; the floor now carries that qualification. And §4.2 had no overlay row for the two mechanism-B panels while §4.3 had one, so a builder would derive their overlay border from `logbd`, a base key the overlay does not carry; the row is added, with the general rule that an overlay row replaces its control's base row rather than adding to it. **One citation was wrong in a way worth recording:** §8 sent a reader to `ONEUP-0028` §2 for the corroborating defect record. Both quoted strings are verbatim, but they live in that document's *Background — what is broken today* section; its §2 is *Announcements*, because it leaves `##` sections unnumbered and numbers only the `###` subsections. My own packet window for that section was mis-cut the same way, which is how the lane reached the right conclusion by the wrong route. **Status stays Draft.** The run reached its cap rather than an empty loop, and the two ⚠ OPEN decisions from loop 1 are still open. |
