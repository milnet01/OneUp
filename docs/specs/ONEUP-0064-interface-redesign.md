# ONEUP-0064 — the interface redesign

**Status:** Draft
**Kind:** ux
**Roadmap:** ONEUP-0064
**Branch:** v2
**Verified at:** `d18fbf2` — every figure below was computed or measured against this tree,
on PySide6 6.11.0, not recalled.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** Every control that can take keyboard focus says so, with a cue the app
**derives** from the surface underneath it rather than one anybody authors — because the
obvious cue, the one the app uses today, cannot be made strong enough at any shade.

**`docs/standards/ui-and-accessibility.md` owns the rules this works under** — no focus
border (§5), colour never alone (§3), text derived from the desktop point size (§4). None
of it is re-argued here. What this spec adds is the part §5.4 explicitly leaves to this
item: a focus treatment that measures, the computation that proves it, and the layout the
sweep for it turned up reasons to change.

## 1. Goal

A keyboard user can always see where they are, in every theme, without a ring or an outline
ever being drawn — and the app can prove it rather than assert it. Sixteen controls that
show a keyboard user nothing today show them something. The window they appear in reads as
one screen with an obvious next action, rather than a stack of buttons that all look
equally important.

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
whether or not they are showing. The sixteen are not
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

Neither WCAG exception in SC 2.4.13 covers this. The second exception applies only where
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

**The instinct that produced all six is lightening, and it has a ceiling.** Every one of
these focus colours is a lighter version of its rest colour, because focus reuses hover and
hover lightens. Measured against the strongest possible lightening — pure white:

| Rest fill | vs `#ffffff` |
| --- | --- |
| `btn_accent` top stop `#4aa3ff` | **2.63:1** |
| accent cyan stop `#22d3ee` | 1.81:1 |
| switch track on `#2ecc71` | 2.10:1 |
| `#RestartBtn` top stop `#ef6a55` | 3.06:1 |

White itself is 2.63:1 against the Run button's fill, so **no lighter shade of anything
reaches 3:1 on that button at any saturation.** This is the measurement taken on the
roadmap bullet before the spec was written, and it is why the design below darkens.

**The Restart button's top stop is the one row that clears 3:1, and it is why the answer
has to be a rule rather than a colour.** A hand-picked lightening could be made to work
there and nowhere else; the ceiling binds hardest on the accent, which is the most visible
surface in the application and the one every theme keeps. A cue that works on one control
and fails on the other five is not a cue.

### 2.3 Three smaller things the same sweep measured

- **The warning banner's tab order runs backwards.** The banner lays out
  `[text · Copy command · Show details · <second remedy>]`, but focus visits *Show details*
  first, then jumps left to *Copy command*. `_make_banner` parents its own button before
  `warn_copy_btn` is inserted ahead of it in the layout, and Qt builds the focus chain from
  parenting order. That is a breach of `docs/standards/ui-and-accessibility.md` §5.6.

- **The light theme's link text already fails ordinary text contrast.** `#LinkBtn` is
  `#4aa3ff` and sits on `#Card`, which is `#ffffff` in `_LIGHT`: **2.63:1** against a 4.5:1
  requirement. `docs/specs/ONEUP-0027-themes.md` §4.7 checks this pair and its §4.8, which
  lists every pair the check fails today, does not include it. §4.3 gives the light link a
  new rest colour and INV-11 measures it, so this item closes the pair rather than merely
  noticing it; §8 carries the row to 0027.

- **The disclosure arrow is small but conforming, which is not the same thing.** All five
  measure 19×19, under SC 2.5.8's 24×24. Its nearest other target is its row's switch,
  **47.0 px** away centre to centre. The switch is not itself undersized, so the test is a
  24 px circle on the arrow against the switch's own bounding box — 47.0 − 28 = 19 px of
  clearance against a 12 px radius — and the spacing exception applies
  (*Source:* <https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html>). It is
  an ergonomics defect, not a conformance one, and §4.5 treats it as such.

## 3. Scope decisions

### 3.1 The three fixed points (the user, 2026-07-26)

1. **No focus borders.** Ordinary borders are fine and always were; what must not appear is
   a border or an outline drawn *to mark* the focused control. Restated at its original
   width, not widened — `ui-and-accessibility.md` §5.2.
2. **The phone-style on/off switches stay.** A long-standing preference over check boxes,
   because on/off reads at a glance. A fixed point, not a candidate.
3. **Free rein otherwise** — propose and build, tweak afterwards. So this spec brings
   recommendations rather than questions.

**Fixed point 1 survives this design untouched.** Darkening a fill draws no ring, adds no
outline, and changes no geometry.

**One sentence in the standard does not survive it.** §5.1 says focus is signalled *"by
reusing the hover appearance"*. Hover lightens, and §2.2 shows lightening cannot reach 3:1
on these palettes, so the two rules are in conflict and the measurable one wins. §8 carries
the correction into the standard and into `CLAUDE.md`, which repeats it.

### 3.2 What this spec does not decide

- **The six new palettes.** `docs/specs/ONEUP-0027-themes.md` authors them and lands after
  this item (`docs/design/oneup-2.0.md` §5.2). This spec ships the derivation and the check,
  which is what makes a palette nobody has written yet still get a working focus cue.
- **Any wording.** Translation is ONEUP-0032 and comes last; strings this item changes are
  wrapped once, there.
- **Whether `oneup/gui/window.py` reaches the 600-line ceiling.**
  `docs/specs/ONEUP-0034-gui-modules.md` §4.2 hands the attempt here and promises nothing;
  this spec keeps that posture — §4.5 splits what the layout change naturally separates and
  claims no figure.

## 4. Design

### 4.1 One cue, derived from the surface rather than authored

> **A focused control's own fill changes to a colour derived from the colour it replaces:
> the smallest blend toward black — or toward white, when black cannot get there — that
> measures at least 3:1 against every surface the control can rest on. Its text is redrawn
> in whichever of black or white contrasts more with that fill.**

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
cannot fail. A complete sweep of a 3-step sRGB lattice (636,056 colours) agrees with the
analytic bound, worst case `#5d60ff` → 4.58:1.

**Against a *set* of surfaces it can fail, and the spec says so rather than assuming
otherwise.** Each surface forbids a band of luminances around itself, and two surfaces far
enough apart can forbid everything: measured, `#000000` and `#989898` admit no colour at
all that clears 3:1 against both, and a coarse sweep of grey pairs finds 192 such pairs. It
does not arise for the surfaces this design actually pairs — `rowcard` and `rowhov` differ
by a hover lift and sit 0.02 apart in luminance — but "cannot happen here" is a property of
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

Mechanism B is for the two widgets that hold their own scrolling text, where recolouring
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

| Control | Mechanism | Rest surface(s) the cue is derived from |
| --- | --- | --- |
| `#RunBtn`, `#BannerBtn` | A | `btn_accent`, both gradient stops |
| `#RestartBtn` | A | the danger gradient, both stops |
| `#StopBtn` (new — §4.5) | A | `card` |
| `#GhostBtn`, in the header and the action row | A | `card` |
| `#GhostBtn`, moved into `SettingsDialog` (§4.5) | A | the dialog's own surface, which is `card` — the sheet is set on the application, so the dialog inherits it |
| `#LinkBtn`, on the card (`log_toggle`, `openlog_btn`, `rollback_btn`) | A | `card` |
| `#LinkBtn` in a banner (`warn_copy_btn`) | A | `#WarnBanner`, `#InfoBanner` — its banner is re-used for both roles |
| `#LinkBtn` inside a row's detail panel (`size_btn`) | A | `rowcard` **and** `rowhov` |
| `QToolButton#Disclose` | A | `rowcard` **and** `rowhov` |
| `ToggleSwitch` | A, in `paintEvent` | its own track — `GREEN` / `RED` today, which `ONEUP-0027` §4.3 renames `switchon` / `switchoff` |
| `QPlainTextEdit#Log` | B | `logbd`, widened to 2 px |
| `QScrollArea#DetailScroll` | B | `logbd`, at 2 px — the panel gains a rest border |
| Every button under the high-contrast overlay | A | `$btn` for the primary family, `$card` for `#GhostBtn` — §4.3 has the figures |

**The painted switch needs a seam, and there is exactly one that already works.** A
stylesheet cannot colour what `paintEvent` draws, but it can set a Qt property on the class:
`ToggleSwitch { qproperty-highContrast: … }` is that pattern in the code today. The focus
pair arrives the same way — `build_theme` computes it and the sheet assigns it as a
property, with the same mandatory explicit default the existing setter carries, because a
`qproperty-` assignment is not reverted when its rule stops matching.

**The disclosure is the reason the rule says *every* surface.** Its row lightens to
`rowhov` under the mouse, so a focused disclosure can sit on either. In the dark palette a
fill derived from `rowcard` alone is `#66696e`, which measures 3.00:1 there and **2.83:1**
on `rowhov` — a fail. Raising the blend from `t = 0.33` to `t = 0.35` gives `#6a6d73` at
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
| Link button rest text, light (§2.3's failing pair) | `#3779bd` on `#ffffff`, **4.53:1** | — | — | — |
| High contrast, dark — primary buttons | `$btn` `#ffffff` | `#949494` | 3.03:1 | `#000000` 6.92:1 |
| High contrast, dark — `#GhostBtn` | `$card` `#000000` | `#5c5c5c` | 3.14:1 | `#ffffff` 6.69:1 |
| High contrast, light — primary buttons | `$btn` `#000000` | `#5c5c5c` | 3.14:1 | `#ffffff` 6.69:1 |
| High contrast, light — `#GhostBtn` | `$card` `#ffffff` | `#949494` | 3.03:1 | `#000000` 6.92:1 |

Four of these are worth reading twice. The Run button's focused fill is a **dark navy**,
which is the opposite of what the app does today and the whole point of §2.2. The switch's
track darkens rather than changing hue, so the red/green distinction and the bar-and-circle
shape both survive focus untouched — `ui-and-accessibility.md` §3 is not weakened by the cue
landing on the same surface. **The Stop button's rest colour is per-palette, not one danger
red**: `#d6412a` reads at 4.52:1 on the light card but only 4.02:1 on the dark one, so dark
takes `#e0553f` at 4.79:1. And the light **link button's rest text moves** from `#4aa3ff` to
`#3779bd`, which is what closes §2.3's 2.63:1 pair; on the dark card `#3779bd` measures
4.00:1, so the dark palette keeps `#4aa3ff` at 6.89:1 rather than adopting it.

**High contrast takes mechanism A, like every other button — its rest border is not the
cue.** The overlay's buttons do carry a 2 px border at rest, which is why an earlier reading
of this looked like mechanism B; but the pixels the overlay actually moves on focus are the
*fill* (`background: $btnhov`), and recolouring that border would not work anyway — dark
`$border` `#ffffff` → `$focus` `#ffd400` is **1.43:1** and light `#000000` → `#0000cc` is
**1.87:1**. Today's overlay `:focus` rules therefore fail 3:1 exactly as the ordinary sheet's
do, and they are replaced by the derived fills in the four rows above.

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
   the control has (≥ 3:1), and the ink against the fill (≥ 4.5:1). Gradients are sampled
   down their length, not only at the stops.
2. **Every focusable widget is accounted for.** The window is built offscreen, every widget
   with `focusPolicy() != Qt.NoFocus` is collected, and each must be covered by a row of
   §4.2's table — by object name for a styled one, by class for a painted one. A widget
   matching nothing fails the check. This is what stops a control being added later with no
   cue, which is exactly how the sixteen in §2.1 accumulated.

**It is deliberately a superset of what `ONEUP-0027` needs.** That spec's §4.7 defers the
focus measurement here and says its own job is to supply palettes that pass it; the
per-theme loop above is what it passes them to.

### 4.5 The layout

Free rein, with the reasons the sweep produced. Nothing here changes what a control *does*.

**The header carries two buttons instead of four.** *Settings* and *About* stay;
*Repositories* and *Recenter* move inside Settings. Four buttons of identical weight beside
the app title make none of them findable, and of the four only Settings is used routinely —
*Recenter* exists because a Wayland compositor owns window placement and `move()` is
silently ignored, as `Updater.recenter`'s own comment says. That is a workaround, not a
feature that has earned a place in the header.

**Settings gains three headings** rather than staying a flat column of ghost buttons:
*Automatic behaviour* (weekly check, passwordless, automatic updates), *Appearance* (text
size, high contrast — and the theme picker `ONEUP-0027` §4.6 adds next), *This machine*
(Repositories, Recenter, Copy diagnostics). The dialog stays a host, not an owner
(`ONEUP-0034` §4.2): the window still builds and owns the controls.

**The action row reads primary-first.** *Run selected updates* leads, *Check for updates*
follows it, and *Stop* replaces *Check* in place while a run is going rather than appearing
as a third button beside it. Today three identically-styled ghost buttons — *Check*, *Stop*
and *Retry failed steps* — are indistinguishable from *About*, so the one that interrupts a
running update looks exactly like the one that opens a version dialog. *Stop* keeps the
ghost outline but takes the danger family's colour, which the reboot banner already uses. It
becomes its own object name, `#StopBtn`, because INV-1 matches a styled control by object
name and a restyled control still called `#GhostBtn` would be invisible to the check; §4.2
and §4.3 carry its rows, and its rest colour differs by palette.

**A whole task row toggles its task.** Today the only hit target in a row is the switch at
its far right — measured 56×30 in a row of 716×61, with the window at its 760 px starting
width — and the name and description beside it do nothing.
Clicking anywhere in the row toggles the switch **except** on the switch itself, the badge,
the disclosure arrow, and anything inside the expanded detail panel — the switch is excluded
because it already toggles itself, and a row handler that also fired would toggle twice and
leave the primary control looking dead. INV-10 asserts exactly that. The switch stays what
it is and remains the thing that shows the state — fixed point 2 — it simply stops being the
only place you may click.

**The disclosure arrow grows to 24×24**, which §2.3 establishes is an ergonomics fix rather
than a conformance one, and gets the hover and focus treatment the rest of the controls
have. **24×24 is the floor for every interactive control**, width as well as height, and
INV-12 measures it — a minimum height alone settles only half of SC 2.5.8.

**The tab chain is set for every control, not the first eleven.** `setTabOrder` today
covers the header buttons, the five switches, *Check* and *Run*, and everything after that
falls back to parenting order — which is where §2.3's backwards banner comes from. The
chain is stated end to end, and the banner's remedy buttons are ordered as they are laid
out.

### 4.6 What deliberately does not change

- **The five task rows, their keys and their order.** `system, flatpak, firmware, orphans,
  cache` is a contract shared with the engine (`CLAUDE.md` §4).
- **Every accessible name and description.** ONEUP-0028's floor is a regression bar. A name
  may be reworded by ONEUP-0032 later; none is removed here.
- **The marker protocol, and every behaviour behind a control.** This item changes what the
  window looks like and where its controls sit. A button that ran a check still runs the
  same check.
- **Font sizes stay derived from the desktop point size.** No hard-coded `px` for text —
  `ui-and-accessibility.md` §4.

## 5. Correctness invariants

- **INV-1** Every widget with `focusPolicy() != Qt.NoFocus` — in the main window **and in
  every dialog the window opens** — is covered by a row of §4.2's mechanism table.
  *Test:* `tests/gui-smoke.py` builds the window offscreen, opens each dialog in turn,
  collects those widgets, and fails naming any whose object name and class match no row.
  Breaks the moment a control is added without a focus treatment — the state §2.1 measured
  at sixteen widgets. The dialog half is not padding: §4.5 moves *Repositories* and
  *Recenter* into `SettingsDialog`, so a window-only sweep would stop covering two controls
  it covers today.

- **INV-2** For every row of §4.2, in every theme, with the high-contrast overlay on and
  off, the pixels the focus state changes — the fill under mechanism A, the border under
  mechanism B — measure at least 3:1 against **every** rest surface named in that row.
  *Test:* the §4.4 computation, driven from `tests/gui-smoke.py`. Breaks on a fill derived
  from one surface but rendered over another — the disclosure-on-`rowhov` case, which
  measures 2.83:1 if the rule is written against `rowcard` alone.

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
  not already set to the same value — colour is the only thing a focus rule may move. For
  the painted controls, which no stylesheet parse can see, it asserts `ToggleSwitch`'s
  `sizeHint()` and rendered image bounds are identical focused and unfocused. Breaks on a
  focus ring in either path, on a border present only when focused, and on a `2px` focus
  border over a `1px` rest border — the 33 px → 37 px resize `ui-and-accessibility.md` §5.4
  measured.

- **INV-5** The single-surface derivation returns a pair for every sRGB colour, and the
  multi-surface search either returns a pair clearing the threshold against every surface or
  fails with a named error identifying the control and the surfaces. It never returns a pair
  that fails.
  *Test:* a unit check over a **16-step** sRGB lattice (4,096 colours, measured at ~1.5 s;
  the 3-step lattice of §4.1 costs ~226 s in pure Python and is a one-off, not a suite
  check) asserting a pair is returned for each single-surface case and that both its ratios
  clear their thresholds; plus the pair `#000000` / `#989898`, which admits no fill at 3:1
  and must raise rather than return. Breaks if the search is written in one direction only —
  toward white alone fails at `#4aa3ff`, which reaches 2.63:1 at most — and breaks if an
  unsatisfiable surface set returns a best-effort colour instead of raising.

- **INV-6** Tab order follows visual order for every focusable control in the window and in
  each banner.
  *Test:* `tests/gui-smoke.py` walks the focus chain from the window and asserts each
  widget's position matches its layout position within its parent. Breaks on today's
  warning banner, whose chain visits *Show details* before *Copy command*.

- **INV-7** Every focusable widget still reports a non-empty accessible name.
  *Test:* the existing `tests/gui-smoke.py` name sweep, unchanged — ONEUP-0028's guarantee,
  re-run against the redesigned tree. Breaks if a control is rebuilt during the redesign and
  its `setAccessibleName` call is dropped.

- **INV-8** No state is signalled by colour alone: the switch keeps its bar-and-circle
  shape, and every badge keeps its text.
  *Test:* `tests/gui-smoke.py` asserts `ToggleSwitch._paint_state_shape` is reached in both
  checked states and that each badge's text is non-empty. Breaks if the focus treatment is
  implemented by replacing the painter rather than recolouring its track.

- **INV-9** No text size is expressed in `px`.
  *Test:* the existing assertion in `tests/gui-smoke.py` that the built stylesheet contains
  no `font-size:` followed by a `px` length. Breaks if a redesigned control hard-codes a
  size instead of taking one from `_font_metrics`.

- **INV-10** Clicking a task row's body toggles that row's switch exactly once; clicking the
  switch itself also toggles exactly once; clicking its badge or its disclosure does not
  toggle it at all.
  *Test:* `tests/gui-smoke.py` posts a mouse click at the row's text area and asserts
  `isChecked()` flipped, clicks the switch directly and asserts it flipped once rather than
  twice, then clicks the badge and the disclosure and asserts neither moved it. Breaks if
  the row-level handler is attached to the whole frame without excluding its children —
  which for the switch shows up as a double toggle, leaving the primary control looking
  dead rather than throwing.

- **INV-11** Every user-facing text colour measures at least 4.5:1 against the surface it
  rests on, at rest as well as focused, in every theme.
  *Test:* the §4.4 computation, extended to the rest pairs. Breaks on the light link button
  as it stands today — `#4aa3ff` on `#ffffff` is 2.63:1 — which is the pair §2.3 measured
  and §4.3 closes with `#3779bd` at 4.53:1.

- **INV-12** Every interactive control measures at least 24×24, width and height, at the
  smallest supported text scale.
  *Test:* `tests/gui-smoke.py` builds the window offscreen at the smallest entry in
  `TEXT_SCALES`, walks the same widget set INV-1 collects, and asserts both dimensions.
  Breaks on today's 19×19 disclosure arrow, and breaks on any control whose size is left to
  the desktop font alone — §2.3's measurements are this machine's font, not a floor.

## 6. Failure modes

- **A theme is added whose surface sits at the 4.58:1 worst case.** The derivation still
  returns a pair; the fill is simply near-grey. Nothing fails, and INV-2 records the actual
  ratio, so a palette that produces an ugly-but-conforming cue is visible rather than
  silent.
- **A control is added with no rest fill to derive from.** The §4.4 sweep fails it by name
  (INV-1) rather than letting it inherit nothing. The fix is a row in §4.2, which forces the
  question of what surface it rests on.
- **A control's rest surfaces are too far apart for any fill to clear 3:1 against all of
  them.** Real and measured — `#000000` and `#989898` admit none, and 192 such grey pairs
  exist (§4.1). The derivation raises rather than returning a best-effort colour, naming the
  control and both surfaces, and the theme does not ship. It cannot arise from today's two
  palettes, where the only multi-surface control pairs `rowcard` with `rowhov` and those sit
  0.02 apart in luminance; it is guarded because `ONEUP-0027` authors six more palettes and
  nothing stops one of them separating a row's two states widely.
- **The high-contrast overlay is appended after the base sheet and overrides it.** Its
  `:focus` rules must still be emitted after its own `:hover` and `:checked` rules, or a
  focused checked control shows nothing — `ui-and-accessibility.md` §5.5. INV-4's parse
  reads the built sheet, overlay included, so an ordering mistake is caught in the same
  place.
- **A user's desktop font is small enough to shrink a control below 24×24.** Sizes derive
  from the desktop point size, so the figures in §2.3 are this machine's. The redesign sets a
  24×24 floor on interactive controls rather than letting the font decide alone, and INV-12
  measures it at the smallest supported text scale.
- **`Qt` reports a widget as focusable that the user can never reach**, such as a scroll
  area inside a collapsed panel. INV-1 covers it anyway, which costs a row in §4.2 and
  nothing else. Over-covering is the safe direction.

## 7. Tests

| Invariant | Where | What it does |
| --- | --- | --- |
| INV-1, INV-6, INV-7, INV-8, INV-10, INV-12 | `tests/gui-smoke.py` | builds the window and each dialog offscreen and sweeps the widget tree |
| INV-2, INV-3, INV-5, INV-11 | `oneup/gui/theme.py` computation, driven from `tests/gui-smoke.py` | the ratio arithmetic, over every theme and both overlay states |
| INV-4, INV-9 | `tests/gui-smoke.py` | parses the built stylesheet; INV-4's second half renders `ToggleSwitch` to compare its focused and unfocused bounds |

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
  invariants — `documentation.md` §4 requires every standard to carry one, and §5's rows are
  exactly what this item changes.
- **§5.4's conformance claim is wrong today and is corrected, not merely sharpened.** It
  says *"WCAG 2.2 SC 2.4.7 (Focus Visible) is still met"*. §2.1 measures sixteen focusable
  widgets with no cue at all, five of them the on/off switches, whose `paintEvent` draws the
  whole control and no focus indication — a keyboard-operable control with no visible
  indicator fails SC 2.4.7, which is Level **AA**. The standard's sentence was written when
  only the four styled controls were in view. So the honest statement is that OneUp fails
  2.4.7 (AA) today for those sixteen, that this item is what makes 2.4.7 true, and that SC
  2.4.13 (Focus Appearance, Level **AAA**) is met on top of it.
- **`CLAUDE.md` §6** repeats *"focus reuses the hover look"* in its trap list and is
  corrected in the same commit. The trap that stays is the one that cost the bug: no focus
  ring, because Qt draws it square and a focus border resizes the widget.
- **`docs/specs/ONEUP-0027-themes.md` §4.8** gains the light `#LinkBtn`-on-`card` row §2.3
  measured at 2.63:1, recorded as closed by this item — which §4.3's `#3779bd` and INV-11
  make true, and which is the disposition §4.8's own preamble already anticipates when it
  says a pair the redesign has already fixed needs nothing. Its §4.7 also gains `logbd` as a
  second rendering surface, because §4.2 gives `#DetailScroll` a border drawn in it and §4.7
  rules that a token rendering on more than one surface takes a row per surface; and the
  danger family gains `#StopBtn` as a third consumer beside the restart button and the
  reboot banner. Its §4.7's deferral of the focus measurement to this item needs no change.
- **`docs/specs/ONEUP-0034-gui-modules.md` §4.2** predicts `window.py` will not fit the
  600-line ceiling and hands the attempt here; §3.2 records what this spec does and does not
  promise about that.
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

- **Authoring the six new palettes.** `ONEUP-0027`, which lands after this item and passes
  its palettes to this item's check (§3.2).
- **Wrapping any string for translation.** `ONEUP-0032`, last (`oneup-2.0.md` §5.2).
- **Right-to-left mirroring.** Also `ONEUP-0032` §4. The layout changes here use no
  directional stylesheet property, so they add nothing for that item to undo, but the
  mirroring itself is not built here.
- **A new theme, a new colour scheme, or any change to what the app *does*.** This item
  moves controls and changes how focus is drawn.
- **Reaching the 600-line module ceiling for `window.py`** as a promise. §3.2.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-08-03 | 3 lanes; 2 critical, 7 high, 8 medium, 9 low, 2 info — **24 verified, 4 dismissed** — 22 actionable fixed, 2 info carried | The first review of this document. **Both criticals were the same defect seen from two sides: a claim about another document that this one had not earned.** §2.3 and §8 said the redesign fixed the light link button's 2.63:1 rest text and instructed `ONEUP-0027` §4.8 to record it closed — while §4 specified only a *focus* fill and never touched the rest colour, so §8 would have written a false row into a reviewed spec. §4.3 now carries `#3779bd` at 4.53:1 and INV-11 measures rest text, in every theme. The second was the mirror of it pointing at a standard: §8 called SC 2.4.7 *"already met"*, copying `ui-and-accessibility.md` §5.4 — but this document's own §2.1 measures sixteen focusable widgets with no cue at all, and a keyboard-operable control with no visible indicator fails 2.4.7, which is Level **AA**. The standard has been wrong since it was written for the four styled controls; §8 now corrects it rather than propagating it. **The most valuable finding was one all three lanes reached and the author had proved the opposite of:** §4.1 claimed the derivation "always succeeds", on an analytic bound that is only true for a *single* surface, while §4.1's own rule demands every surface a control rests on. Measured during verification — `#000000` and `#989898` admit no colour clearing 3:1 against both, and a coarse grey sweep finds **192** such pairs. The claim is now scoped, the search raises a named error instead of returning a best-effort colour, §6 carries the failure mode and INV-5 tests both halves. Three more were contract gaps an implementer would have had to invent: the high-contrast overlay was assigned mechanism B and mechanism A in one sentence, with no rows in either table (it is A, and the four rows exist); `#GhostBtn`/`#LinkBtn` derived from `card` alone when one link sits on the warning banner and another inside a task row, which is the exact defect §4.2 argues against for the disclosure; and `ToggleSwitch`'s row named `switchon`/`switchoff`, tokens `ONEUP-0027` creates *after* this item, with no seam stated for reaching a painted widget at all. **Two numbers were wrong and one was expensive.** The disclosure's 3.09:1/2.91:1 came from a derivation step the prose never describes — the reproduced figures are 3.00:1 and 2.83:1, and INV-2 had locked the wrong one into a test. And INV-5's 3-step lattice was measured at **~226 s** of pure Python inside the suite; it is now a 16-step lattice at ~1.5 s, with the fine sweep kept as a one-off. **Dismissed: four**, each checked rather than waved away. A lane held that Qt orders the focus chain by *creation*; a two-widget probe parenting them in reverse order showed the chain follows **parenting** order, so the document was right. A lane flagged `ONEUP-0034` §4.2 as cited for two different claims — both are in §4.2. *"Copy diagnostics"* was called undefined; it is `diag_btn` in the window. And an objection that §1's goal prose has no measurable referent was dropped: a Goal section is not an invariant. **Carried as INFO:** the switch's state shape is checked against its *resting* track by `ONEUP-0027` §4.7 but against no *focused* one (6.46:1 today, unchecked once `switchmark` becomes per-theme); and §4.5 making a whole row a click target would collapse §2.3's 47.0 px spacing-exception clearance, moot only because the arrow grows to 24×24. The document left this loop at **623 lines**, up from 495. |
