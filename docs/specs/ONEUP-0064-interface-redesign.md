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

```bash
# builds the window offscreen, keeps every widget whose focusPolicy() != Qt.NoFocus,
# and asks whether the stylesheet carries a :focus rule for its objectName
python3 tests/gui-smoke.py            # the harness this reuses
```

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
application, and they are painted rather than styled, so no stylesheet can reach them at
all. `ToggleSwitch.paintEvent` ends with a comment saying so.

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

### 2.3 Three smaller things the same sweep measured

- **The warning banner's tab order runs backwards.** The banner lays out
  `[text · Copy command · Show details · <second remedy>]`, but focus visits *Show details*
  first, then jumps left to *Copy command*. `_make_banner` parents its own button before
  `warn_copy_btn` is inserted ahead of it in the layout, and Qt builds the focus chain from
  parenting order. That is a breach of `docs/standards/ui-and-accessibility.md` §5.6.

- **The light theme's link text already fails ordinary text contrast.** `#LinkBtn` is
  `#4aa3ff` and sits on `#Card`, which is `#ffffff` in `_LIGHT`: **2.63:1** against a 4.5:1
  requirement. `docs/specs/ONEUP-0027-themes.md` §4.7 checks this pair and its §4.8, which
  lists every pair the check fails today, does not include it. This item lands first and
  recolours the control, so the redesign fixes it; §8 carries the correction to 0027.

- **The disclosure arrow is small but conforming, which is not the same thing.** All five
  measure 19×19, under SC 2.5.8's 24×24. The nearest other target's centre is **47.0 px**
  away, so a 24 px circle on each does not intersect and the spacing exception applies
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

**It always succeeds.** For a colour of relative luminance `L`, the contrast against black
is `(L+0.05)/0.05` and against white `1.05/(L+0.05)`. The larger of the two is smallest
where they are equal, at `L = 0.1791`, where both are **4.58:1**. So every colour in sRGB
can reach 3:1 in at least one of the two directions, and the search cannot fail to
terminate. An exhaustive sweep of a 3-step sRGB lattice (636,056 colours) confirms it, with
the worst case at `#5d60ff` → 4.58:1.

**The same bound gives the text for free.** 4.58 is also above 4.5, so "black or white,
whichever contrasts more with the fill" always clears the 4.5:1 body-text requirement
against it. That matters because deriving a fill and leaving the label alone breaks the
label: light `#GhostBtn`'s `$ghostfg` measures 10.16:1 on `card` and **3.35:1** on the fill
derived from it. The fill and its ink are one derived pair, never separable.

**Gradients take one blend fraction, not one per stop.** Blending toward black is a
per-channel scale, so applying a single fraction to both stops scales every interpolated
pixel by the same amount. Taking the larger of the two stops' required fractions, the worst
pixel anywhere down the Run button's gradient measures **3.00:1**.

### 4.2 Two mechanisms, because a log pane is not a button

Mechanism A is §4.1: **the fill and its ink change.** It suits anything whose whole area is
chrome, and it satisfies SC 2.4.13's area half without arithmetic — the requirement is an
area at least that of a 2 px perimeter of the component, and a whole fill exceeds it.

Mechanism B is for the two widgets that hold their own scrolling text, where recolouring
every pixel would recolour the content: **an existing rest border changes colour.** No
border is added, so fixed point 1 holds and §5.3 of the standard already permits it. The
area half is what makes this work only at width: a 1 px border is *less* than a 2 px
perimeter and would not qualify, so both panels carry a **2 px** border at rest. That is an
ordinary border, present focused or not, and only its colour moves.

| Control | Mechanism | Rest surface the cue is derived from |
| --- | --- | --- |
| `#RunBtn`, `#BannerBtn` | A | `btn_accent`, both gradient stops |
| `#RestartBtn` | A | the danger gradient, both stops |
| `#GhostBtn`, `#LinkBtn` | A | `card` |
| `QToolButton#Disclose` | A | `rowcard` **and** `rowhov` |
| `ToggleSwitch` | A, in `paintEvent` | its own track — `switchon` or `switchoff` |
| `QPlainTextEdit#Log` | B | `logbd`, at 2 px |
| `QScrollArea#DetailScroll` | B | `logbd`, at 2 px — the panel gains a rest border |

**The disclosure is the reason the rule says *every* surface.** Its row lightens to
`rowhov` under the mouse, so a focused disclosure can sit on either. A fill derived from
`rowcard` alone measures 3.09:1 there and **2.91:1** on `rowhov` — a fail. Raising the
blend until it clears both gives `#6a6d73` at 3.01:1 against the worse of them. One extra
percent of blend, and the rule that produces it is the one written in §4.1.

### 4.3 What that comes to, in the two palettes that exist today

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

Two of these are worth reading twice. The Run button's focused fill is a **dark navy**,
which is the opposite of what the app does today and the whole point of §2.2. And the
switch's track darkens rather than changing hue, so the red/green distinction and the
bar-and-circle shape both survive focus untouched — `ui-and-accessibility.md` §3 is not
weakened by the cue landing on the same surface.

**High contrast needs no separate treatment and gains one anyway.** Its buttons keep the
2 px border they already carry at rest, so mechanism B applies to them unchanged; measured,
today's high-contrast focus fill fails the same way the ordinary one does — dark
`#ffffff` → `#ffd400` is **1.43:1**, light `#000000` → `#0000cc` is **1.87:1** — so the
overlay's `:focus` rules are derived by the same function rather than left as they are.

### 4.4 The check

A pure computation, in `oneup/gui/theme.py` beside the derivation it verifies, driven from
`tests/gui-smoke.py`. No rendering and no screenshot, which is what lets it run over a
theme nobody has written yet.

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
ghost outline but takes the danger family's colour, which the reboot banner already uses.

**A whole task row toggles its task.** Today the only hit target in a row is the switch at
its far right — measured 56×30 in a row of 716×61, with the window at its 760 px starting
width — and the name and description beside it do nothing.
Clicking anywhere in the row that is not the badge or the disclosure toggles the switch.
The switch stays exactly what it is and remains the thing that shows the state — fixed
point 2 — it simply stops being the only place you may click.

**The disclosure arrow grows to 24×24**, which §2.3 establishes is an ergonomics fix rather
than a conformance one, and gets the hover and focus treatment the rest of the controls
have.

**The tab chain is set for every control, not the first thirteen.** `setTabOrder` today
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

- **INV-1** Every widget in the main window with `focusPolicy() != Qt.NoFocus` is covered
  by a row of §4.2's mechanism table.
  *Test:* `tests/gui-smoke.py` builds the window offscreen, collects those widgets, and
  fails naming any whose object name and class match no row. Breaks the moment a control is
  added without a focus treatment — the state §2.1 measured at sixteen widgets.

- **INV-2** For every control in §4.2, in every theme, with the high-contrast overlay on
  and off, the focus fill measures at least 3:1 against **every** rest surface that control
  can sit on.
  *Test:* the §4.4 computation, driven from `tests/gui-smoke.py`. Breaks on a fill derived
  from one surface but rendered over another — the disclosure-on-`rowhov` case, which
  measures 2.91:1 if the rule is written against `rowcard` alone.

- **INV-3** For every control that carries text, the focused ink measures at least 4.5:1
  against the focus fill.
  *Test:* the same computation. Breaks if a fill is derived and its label left at the
  theme's resting colour: light `$ghostfg` on its own derived fill measures 3.35:1.

- **INV-4** No focus state changes any widget's geometry, and no `:focus` rule introduces a
  `border` or `outline` property that its rest rule does not already set.
  *Test:* `tests/gui-smoke.py` parses the built stylesheet, expands every `border`
  shorthand into its width, style and colour parts, and for each selector carrying a
  `:focus` rule asserts that rule sets no width, style or radius its rest rule does not
  already set to the same value. Colour is what a focus rule may move. Breaks on a focus
  ring, on a border present only when focused, and on a `2px` focus border over a `1px`
  rest border — the 33 px → 37 px resize `ui-and-accessibility.md` §5.4 measured.

- **INV-5** The focus derivation terminates and returns a pair for every sRGB colour.
  *Test:* a unit check over a 3-step sRGB lattice asserting a pair is returned for each and
  that both its ratios clear their thresholds. Breaks if the search is written in one
  direction only — toward white alone fails at `#4aa3ff`, which reaches 2.63:1 at most.

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

- **INV-10** Clicking a task row's body toggles that row's switch; clicking its badge or
  its disclosure does not.
  *Test:* `tests/gui-smoke.py` posts a mouse click at the row's text area and asserts the
  switch's `isChecked()` flipped, then clicks the disclosure and asserts it did not.
  Breaks if the row-level handler is attached to the whole frame without excluding its
  children.

## 6. Failure modes

- **A theme is added whose surface sits at the 4.58:1 worst case.** The derivation still
  returns a pair; the fill is simply near-grey. Nothing fails, and INV-2 records the actual
  ratio, so a palette that produces an ugly-but-conforming cue is visible rather than
  silent.
- **A control is added with no rest fill to derive from.** The §4.4 sweep fails it by name
  (INV-1) rather than letting it inherit nothing. The fix is a row in §4.2, which forces the
  question of what surface it rests on.
- **The high-contrast overlay is appended after the base sheet and overrides it.** Its
  `:focus` rules must still be emitted after its own `:hover` and `:checked` rules, or a
  focused checked control shows nothing — `ui-and-accessibility.md` §5.5. INV-4's parse
  reads the built sheet, overlay included, so an ordering mistake is caught in the same
  place.
- **A user's desktop font is small enough to shrink a control below 24×24.** Sizes derive
  from the desktop point size, so the figures in §2.3 are this machine's. The redesign sets
  a minimum height on interactive controls rather than letting the font decide alone.
- **`Qt` reports a widget as focusable that the user can never reach**, such as a scroll
  area inside a collapsed panel. INV-1 covers it anyway, which costs a row in §4.2 and
  nothing else. Over-covering is the safe direction.

## 7. Tests

| Invariant | Where | What it does |
| --- | --- | --- |
| INV-1, INV-6, INV-7, INV-8, INV-10 | `tests/gui-smoke.py` | builds the window offscreen and sweeps its widget tree |
| INV-2, INV-3, INV-5 | `oneup/gui/theme.py` computation, driven from `tests/gui-smoke.py` | the ratio arithmetic, over every theme and both overlay states |
| INV-4, INV-9 | `tests/gui-smoke.py` | parses the built stylesheet rather than rendering it |

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
  §5.4's table of four ratios is replaced by §4.3's, and its closing sentence — that the cue
  is *"visible but weak"* — stops being true. The section's conformance note is sharpened
  while it is open: SC 2.4.7 (Focus Visible) is Level **AA** and was already met; SC 2.4.13
  (Focus Appearance) is Level **AAA** and is what this item now meets.
- **`CLAUDE.md` §6** repeats *"focus reuses the hover look"* in its trap list and is
  corrected in the same commit. The trap that stays is the one that cost the bug: no focus
  ring, because Qt draws it square and a focus border resizes the widget.
- **`docs/specs/ONEUP-0027-themes.md` §4.8** gains the light `#LinkBtn`-on-`card` row §2.3
  measured at 2.63:1, marked fixed by this item. Its §4.7 already defers the focus
  measurement here and needs no change.
- **`docs/specs/ONEUP-0034-gui-modules.md` §4.2** predicts `window.py` will not fit the
  600-line ceiling and hands the attempt here; §3.2 records what this spec does and does not
  promise about that.
- **`CHANGELOG.md`** gains an `[Unreleased]` entry under **Changed**. It ships inside 2.0;
  there is no 1.4.x release of it, and no version site moves.
- **No marker, no engine change, no packaging change.** The window's argv to the engine is
  untouched, so `docs/reference/marker-protocol.md` is not in scope.

## 9. Alternatives considered (and rejected)

- **Keep lightening, pick a stronger light.** Impossible rather than unattractive: pure
  white measures 2.63:1 against the Run button's fill, so no lighter colour exists that
  reaches 3:1 (§2.2).
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

The rule-14 gate has not run against this document yet. No row is written until a loop
closes.

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
