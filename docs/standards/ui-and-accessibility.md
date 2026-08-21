# UI & Accessibility Standard

**In one sentence:** OneUp must be usable by someone who cannot see the screen, cannot
distinguish red from green, needs the text twice as large, or reads right-to-left — and it
must stay that way without anyone having to remember to check, which is why every rule
below names the test that enforces it.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `58ea3bc` — every symbol name, count, QSS rule and contrast ratio below
was measured against the tree on 2026-07-26, not recalled.

**Sections:** 1 the one-line version · 2 accessible names · 3 never colour alone ·
4 text that scales · 5 focus · 6 dialogs · 7 themes · 8 right-to-left · 9 traps ·
10 before you commit · what checks this · 11 cold-eyes log

**Absorbs** the former `dialogs.md` standard (deleted in the same commit) and the standing rules
of `docs/specs/ONEUP-0028-accessibility.md`. The spec remains the record of *why* and of how
each invariant is tested; this file is the rule a new widget must obey.

## 1. The one-line version

| Rule | Enforced by |
| --- | --- |
| Everything focusable has a name a screen reader can read | `tests/gui-smoke.py` INV-1, the `unnamed()` sweep — walks every widget, keeps `focusPolicy() != Qt.NoFocus`, fails on a nameless one |
| No state is signalled by colour alone | `gui-smoke.py` INV-2 checks |
| No hard-coded pixel font size | `gui-smoke.py` INV-3 — a regex over the built stylesheet |
| Focus never draws a ring or adds a border, and every focusable control HAS a cue | `gui-smoke.py` INV-4 — asserts no ring, that no `:focus` rule moves anything but colour, and that the `:focus` rules are emitted after `:hover`/`:checked`; ONEUP-0076 INV-1 fails any focusable widget with no treatment at all (§5) |
| Dialogs inherit the app theme and open centred on the window | `gui-smoke.py`'s X11 and Wayland `center_on_parent` assertions (§6) |
| Every theme passes the same contrast checks | **half enforced** — ONEUP-0076's focus computation runs over the palette dictionary; the whole-palette 4.5:1 sweep is still ONEUP-0027's to write (§7) |
| The window mirrors for Hebrew and Arabic | §8, gate G10 |

## 2. Accessible names — a name for everything reachable

**Every widget a user can focus reports a non-empty accessible name.** The sweep is the
rule; the current call count is not worth citing, because nothing pins it and the next
widget changes it.

- A name says **what the control is**, in the words on screen: "Run selected updates", not
  "runBtn".
- A description says **what happens if you use it** — reserve it for controls whose effect
  is not obvious from the name.
- **Set the name regardless of enabled state.** `set_controls_enabled(False)` disables the
  five switches for the length of a run; a screen reader still has to be able to describe a
  greyed-out control, so names are set at construction, never conditionally.
- An icon-only button *must* have a name — there is no visible text to fall back on.

The smoke test accepts `accessibleName()` **or** visible `text()`, so a plain labelled
button needs nothing extra. Add the call when the label is an icon, an ambiguous word, or
absent.

## 3. State is never signalled by colour alone

Roughly one man in twelve cannot reliably separate red from green — the exact two colours a
"done / failed" badge reaches for first. **Every colour cue is paired with text or a
shape.** The three live pairings:

**The on/off switch form is a fixed design point, not a candidate for change.** The
phone-style `ToggleSwitch` stays; checkboxes are not an alternative to propose. It was
chosen because on and off read at a glance, and the state *shape* below is what makes that
true for a colour-blind user — so a redesign may restyle the switch, and may not replace
it. (User's decision, standing; restated in `docs/design/oneup-2.0.md` §1 as a constraint
on ONEUP-0076.)

| Cue | Pairing |
| --- | --- |
| Switch on / off | A shape drawn in the track opposite the knob — a **vertical bar** when on, an **open circle** when off. Drawn with `QPainter` primitives, not a font glyph: a painted widget has no font-fallback chain, so a missing character would vanish silently. |
| Tray attention badge | A dark `!` (`#3a2600`) inside the amber disc, drawn in `Updater._tray_icon` — the icon differs in *shape*, not only colour. (The white pen in that method draws the disc's rim.) |
| Overdue last-run line | The text gains a `⚠` prefix and the word `overdue`. Text is safe here because it is an ordinary `QLabel` in the app's font stack. |

**The test for a new cue:** describe the two states out loud without using a colour word.
If you cannot, the pairing is missing.

## 4. Text scales — never a hard-coded pixel font size

Font sizes in the QSS derive from the desktop's default point size, multiplied by the
user's text-scale setting (`_font_metrics(scale)`, substituted into the stylesheet by
`build_theme`). A `font-size: 13px` ignores both, so a user who has set a large system font
gets small text anyway.

- **`pt`, never `px`, for font sizes.** Other pixel lengths are fine — `padding: 2px 9px`
  and `min-height: 20px` are legitimate and the test is written to allow them (it matches
  the `font-size:` declaration specifically, not any line containing "px").
- **Never set a pixel size on a widget font in code** for on-screen text. The one exception
  in the tree is the tray icon's `!` glyph in `Updater._tray_icon`, which is painted into a
  fixed-size pixmap and is not text the user reads.
- **Nothing that contains text may have a fixed height that text can outgrow.** A button
  sized to fit 10 pt text clips at 15 pt. A wholly painted widget with no text may be
  fixed-size — `ToggleSwitch` is `setFixedSize(56, 30)` and that is legitimate, because
  nothing inside it grows with the font.

## 5. Focus — no ring, no added border

This is a user-facing design decision (2026-07-25), and it is narrower than it first
sounds, so read the scope carefully.

### 5.1 The rule

> **Focus is never signalled by drawing a border or an outline.** It is signalled by a
> **derived** fill: the focused control's own fill changes to the smallest blend of the
> colour it replaces toward black or toward white — whichever reaches it at the lower blend
> fraction — that measures at least 3:1 against every colour the control rests on. Its text
> is redrawn in whichever of black or white contrasts more with that fill.

*This rule read "by reusing the hover appearance" until ONEUP-0076 measured it. Hover
lightens, and pure white measures 2.63:1 against the accent button's top gradient stop, so
on these palettes no lighter shade of anything reaches 3:1 there at any saturation. The two
rules were in conflict and the measurable one won. A new control copied from the old
sentence lands a cue of about 1.2:1.*

### 5.2 What the rule does *not* say

**Ordinary borders are entirely fine.** A button may look like a button, a card may have an
edge, a banner may have a coloured rim. The rule is about the *highlight*, not the control.
`#GhostBtn` carries `border: 1px solid $ghostbd` at rest in the base stylesheet, and
always has.

*This scope was clarified by the user on 2026-07-26 after an earlier draft of the 2.0
documents widened it to "no borders on buttons or links at all". That was a misreading and
is recorded here so it cannot recur.*

### 5.3 The testable form

**Focus must not change the box model — only colour and fill.** That single sentence
captures both halves and can be checked by reading a rule:

```css
/* base sheet — the fill moves to a DERIVED colour, and any border the control
   keeps takes the new ink. A border left at its rest colour would sit at about
   1:1 against the fill and disappear. */
QPushButton#GhostBtn        { border: 1px solid $ghostbd; }
QPushButton#GhostBtn:focus  { background: $focusfill; color: $focusink;
                              border-color: $focusink; }

/* base sheet — a borderless gradient button, same rule, one blend fraction
   applied to both stops */
QPushButton#RunBtn        { border: none; background: $btn_accent; }
QPushButton#RunBtn:focus  { background: $accentfocus; color: $accentfocusink; }
```

**One object name can rest on several surfaces, and each takes a selector qualified by the
nearest container unique to it** — never a rename, which would move names other documents
key to. A qualified rule outranks a bare one on specificity, so the unqualified rule is the
default surface and the qualified ones are the exceptions.

**Two extra conditions, both of which look like details and are not.** The changed area must
be at least the area of a **2 px perimeter** of the control (SC 2.4.13), which is what rules
out recolouring a 1 px border: a panel that holds its own scrolling content — where
recolouring the fill would recolour the content — carries a 2 px rest border and moves only
its colour. And a control **already** clearing 3:1 is kept rather than re-derived; the rule
is a floor, not a replacement. The high-contrast overlay's ghost button goes
`$card` → `$btnhov`, which is 14.67:1 dark and 11.22:1 light, and "the smallest blend
reaching 3:1" would weaken that roughly fourfold in the one appearance mode that exists for
low-vision users.

**The overlay obeys the same rule**, and is worth stating because it looks like an
exception: every high-contrast button carries `border: 2px solid $border` at rest, and what
focus moves is still the **fill**. Recolouring that border would not work anyway — `$border`
→ `$focus` measures 1.43:1 dark and 1.87:1 light. **No border is added on focus** in either
sheet.

### 5.4 Why, and what it costs

Two measured reasons, both visual bugs rather than preferences:

- An `outline` draws a **square** around OneUp's rounded buttons, because Qt ignores
  `outline-radius` (verified, PySide6 6.11).
- A `border` added on focus **resizes the widget** — measured 33 px → 37 px — so the layout
  twitches as you tab through it.

**What this cost until ONEUP-0076, stated as it was rather than as it was hoped.** This
section used to say *"WCAG 2.2 SC 2.4.7 (Focus Visible) is still met"*. That was false, and
the sentence was written when only four styled controls were in view: a sweep of the whole
window found **sixteen of its thirty-four focusable widgets with no `:focus` rule at all**,
five of them the on/off switches, which are painted rather than styled and whose painter drew
no focus indication. A keyboard-operable control with no visible indicator fails SC 2.4.7,
which is Level **AA**. The honest statement is that OneUp failed 2.4.7 for those sixteen,
that ONEUP-0076 is what makes it true, and that **SC 2.4.13 (Focus Appearance, Level AAA)**
is met on top of it.

The ratios this section used to table — 1.14:1 to 3.91:1, only one of four clearing 3:1 —
are superseded. **The current figures are not transcribed here**: they are the output of the
app's own focus computation, which prints every pair it measures, and
`docs/specs/ONEUP-0076-ringless-focus-cue.md` §4.3 carries the table. Copying them into a
second document is how a measured figure becomes a stale one; what belongs here is the
rule and the floor. The switch's track darkens rather than changing hue, so the red/green
distinction and the bar-and-circle shape both survive focus untouched — §3 is not weakened
by the cue landing on the same surface.

### 5.5 Ordering, which is easy to get wrong

`:focus` ties with `:hover` and `:checked` on CSS specificity, so **the `:focus` rules must
be emitted after all `:hover` / `:checked` / `:pressed` rules for the same selector.**
Emitted earlier, a focused *checked* control — exactly what a keyboard user lands on — shows
no cue at all. Both stylesheets order it correctly, and each carries a comment saying why.
**The overlay is appended rather than swapped**, so its own `:focus` rules must come after
its own `:hover` and `:checked` rules as well; a base rule qualified by a container also
outranks a bare overlay rule, so the overlay restates every qualified selector the base
sheet uses.

### 5.6 Tab order follows visual order

`setTabOrder` is called for **every** focusable control and not only the first few, because
what it does not state falls back to parenting order — which is how the warning banner's
chain came to visit *Show details* before *Copy command* that sits to its left. If a new
control is inserted into a row, its place in the tab chain is set in
the same commit — a keyboard user who tabs from the top-left to the bottom-right and back to
the middle cannot build a mental model of the window.

## 6. Dialogs and popups

**Every popup matches the app's theme and opens centred over the main window.** Reuse the
two helpers; do not invent a third centring path and do not set a per-dialog palette.

### 6.1 Theme comes free — do not fight it

The whole app is themed once, application-wide, through `apply_app_theme(app)`, which is
re-applied live when the desktop switches light/dark
(`app.styleHints().colorSchemeChanged`, wired in `main()`). Because the stylesheet lives on
the `QApplication`, **every child widget — `QDialog` subclasses and `QMessageBox` instances
alike — inherits it automatically.**

**One thing did not come free, and it is the dialog's own background.** A window inherits
the *sheet*, not a declaration written for another selector, so `QMainWindow { background:
$win; }` alone left a bare dialog painting Qt's platform grey rather than a palette colour.
Measured by `docs/specs/ONEUP-0076-ringless-focus-cue.md`: `#efefef` under the base sheet in
**both** palettes, which is why every dialog used to be light grey in dark mode. **Both
sheets now carry `QMainWindow, QDialog { background: $win; }`** — the base sheet gained it
with `docs/specs/ONEUP-0064-interface-redesign.md`, and the high-contrast overlay always had
it. It matters beyond the one visual defect: a dialog painting a colour no palette controls
is a surface §5.1's derivation cannot blend from. **It changes nothing below**: a new dialog
still reuses the object names and still sets no stylesheet of its own.

- **Do** reuse the object names the QSS already styles (`#Card`, `#RowBorder`, `#GhostBtn`,
  `QLabel#Tagline`, …) so a new dialog looks native.
- **Don't** call `setStyleSheet` or `setPalette` on an individual dialog. A per-dialog
  override desyncs it from the live light/dark switch, and is the one way to break this.

### 6.2 Centring — the two idioms

Wayland places top-level windows itself and ignores `move()` on an already-mapped window,
which is why these helpers exist at all (ONEUP-0049).

**A `QDialog` subclass** — `RepoManagerDialog`, `SettingsDialog`, `RollbackDialog` —
calls the module-level helper from its `showEvent`. Position is re-centred every time it
opens; only `RepoManagerDialog` also restores its *size* (`repos_geometry` in `QSettings`,
saved in `done()`), and the other two persist nothing:

```python
def showEvent(self, event):
    super().showEvent(event)
    center_on_parent(self)
```

**`center_on_parent` is the canonical helper** and the only one that handles Wayland;
`Updater._center_child` is a one-line wrapper around it for the deferred case below. Do not
hand-roll `frameGeometry().moveCenter(...)` + `move(...)` — that is the X11-only path
ONEUP-0049 replaced, and on Wayland it silently does nothing.

**A `QMessageBox` we build and `exec()` ourselves** cannot use `showEvent` cleanly, because
the box sizes to its content only once shown. Centre it via `Updater._center_child`
deferred one event-loop tick — the four live call sites are `Updater._confirm_passwordless`,
`Updater._confirm_key_import`, `Updater._thin_snapshots` and `Updater.show_about`:

```python
box = QMessageBox(self)
...                                    # setText / buttons / etc.
QTimer.singleShot(0, lambda: self._center_child(box))
box.exec()
```

### 6.3 Which rule applies

| Popup kind | Theme | Centre |
| --- | --- | --- |
| `QDialog` subclass | inherited app QSS | `showEvent` override |
| Hand-built `QMessageBox` we `exec()` | inherited app QSS | `QTimer.singleShot(0, _center_child)` before `exec()` |
| Static `QMessageBox.warning/information/question/critical(self, …)` | inherited app QSS | Qt's parent-relative default — acceptable for a transient one-line notice; do **not** rewrite these into hand-built boxes just to centre them |

**Rule of thumb:** if you construct the box and hold a reference to it, centre it. If it is
a one-line convenience call, parenting to `self` is enough.

### 6.4 Adding a dialog — the four steps

1. Parent it to the `Updater` window (`QDialog(parent)` / `QMessageBox(self)`). Never a
   parentless popup — it loses the theme, the centring and the taskbar grouping at once.
2. No per-dialog stylesheet; reuse the existing QSS object names.
3. Centre it by the matching idiom from §6.2.
4. `tests/gui-smoke.py` opens dialogs headless — if the new one blocks on `exec()`, schedule
   its close in the smoke test the way `_dismiss_about` does, or the suite hangs.

## 7. Themes (ONEUP-0027)

2.0 adds user-selectable themes. **A theme is not a free-form colour scheme; it is a palette
that must pass the same checks the two built-in ones pass.** A theme that cannot is not
shipped — there is no "it's only optional" exemption, because a user who picks it is using
the whole app through it.

A theme is a palette dictionary of the same shape as `updater.py`'s `_DARK` and `_LIGHT`,
substituted into the one `_QSS` template by `build_theme`. Consequences,
which are also the rules:

- **A theme supplies colours only — never structure.** It cannot add a border, change a
  padding, or introduce a selector. Everything in §5 stays true by construction, in every
  theme, because no theme can reach the box model.
- **Every key is supplied.** A missing key is a `KeyError` at substitution time, which is
  the desired behaviour — a theme that half-applies is worse than one that refuses to load.
- **Contrast is checked, not eyeballed:** body text at least **4.5:1** against its
  background, and any colour that carries meaning — a border, a badge rim, a switch track —
  at least **3:1** (WCAG 2.2 SC 1.4.3 and 1.4.11).

  **Half of this check now exists, and the half that does is ONEUP-0076's.** Its focus
  computation runs over the palette dictionary — so it already covers a theme nobody has
  written yet, which is the property that makes it worth having — but it measures only the
  colours that item introduces or moves, plus every derived focus pair. **The whole-palette
  4.5:1 sweep is still ONEUP-0027's to write**, and is still the first thing that item
  should do, because it is what makes "a theme that cannot pass is not shipped" enforceable
  rather than aspirational.

  **The two shipped palettes are not both clean, so "pass what the built-ins pass" is the
  wrong bar.** Measured: light `lastrun` `#8a94a2` is **3.07:1** on `card` `#ffffff` and
  **2.71:1** on `win` `#eef1f5` — below 4.5:1 for what `QLabel#LastRun` renders as body
  text. (Dark's equivalent is 5.4:1 and fine.) Either the light palette's `lastrun` is
  darkened when the check lands, or it is recorded as an accepted exception with a reason —
  ONEUP-0027 decides which. It must not be discovered by the check and quietly ignored.
- **The colour-never-alone rule is per-theme.** A theme whose "on" and "off" track colours
  are close is still legible, because §3's shapes carry the state — but a theme must not
  remove or recolour a shape into invisibility against its own track.
- **High contrast stays an overlay, not a theme.** It is appended after the base sheet
  (`build_theme(…, high_contrast=True)`), so it must keep working on top of *every* theme,
  not just the two shipped today. A new theme is checked with the overlay on as well as off.

## 8. Right-to-left languages (ONEUP-0032)

2.0 ships English only, but the machinery must work, and gate **G10** requires the GUI suite
to pass with the layout direction forced right-to-left. Qt mirrors *layouts* automatically;
it mirrors nothing else. These four rules are what "nothing else" means in practice.

### 8.1 Never use a directional stylesheet property

`margin-left`, `margin-right`, `padding-left`, `padding-right`, `border-left`,
`border-right` — **and `text-align: left` / `right`, and `qproperty-alignment`**. Qt does
not mirror stylesheets, so each one is a bug that appears only in Arabic or Hebrew and is
invisible to everyone testing in English.

The six margin/padding/border properties are at **0** in `updater.py`. `text-align` is
**not**: `QPushButton#LinkBtn` in `_QSS` carries `text-align: left`, which will not mirror.
That is one known site, to be resolved by ONEUP-0032 along with the painting in §8.3 —
`text-align: center` on the progress bar is fine, because centre has no handedness. The
rule exists to keep the count from growing: use the symmetric form, or set alignment in
code from the application's layout direction.

### 8.2 Never hard-code `AlignLeft` or `AlignRight` for translatable text

Also **0** today. Use the default alignment, or `Qt.AlignmentFlag` combined with the
application's layout direction — never a fixed side. A left-aligned label in a mirrored
window points away from the text it labels.

### 8.3 Custom painting must apply the direction itself

Qt mirrors layouts, not `paintEvent`. There is exactly one custom-painted *widget* in the
layout — `ToggleSwitch` — and it is the one thing that would mirror wrongly. (The tray icon
is painted too, but it is an icon in a system tray, not a widget in a mirrored layout, so
it is unaffected.)

**Two places inside `ToggleSwitch` are handed, not one, and they are handed differently.**
The knob is the obvious one, and it is unconditionally left-anchored.
`ToggleSwitch._paint_state_shape` is the second, and it picks its edge from the *state*:
checked measures from the left, unchecked from `self.width()`. That shape is §3's
colour-blind cue — an RTL fix that mirrors the knob and forgets the shape breaks the state
cue in Arabic and Hebrew while looking correct in English, and the fix is not the same
expression in both places.

```python
# ToggleSwitch.paintEvent — the knob position is computed from the LEFT
# edge, unconditionally:
x = self._margin + self._pos * travel

# ToggleSwitch._paint_state_shape — the state picks the edge, so BOTH
# branches have to swap when the window is mirrored:
cx = (self._margin + diameter / 2 if self.isChecked()
      else self.width() - self._margin - diameter / 2)
```

In a right-to-left window the switch must travel the other way, or "on" sits on the side the
user reads as "off". A new painted widget either computes its geometry from the layout
direction or states in a comment why it is direction-independent.

The tray icon is painted the same way (`Updater._tray_icon`) but is not laid out by Qt at
all, so it
is out of scope — named here so its absence reads as a decision.

### 8.4 Read the direction from the application, never assume it

`QApplication.isRightToLeft()` — one source, so every widget agrees. Do not read
`self.layoutDirection()` on a widget that may have inherited a stale value, and never infer
direction from the current language code. There are **0** direction reads in `updater.py`
today; the RTL work adds them, and this is the form they take.

## 9. Traps

- **"It's only a small label, it doesn't need a name."** The smoke test disagrees, and so
  does the user hearing "button" read out with no further information.
- **Adding a focus border because a linter or a WCAG checklist asked for it.** It is a
  documented deviation (§5.4), not an oversight. Propose a *subtler* cue and let the user
  decide; do not restore a ring.
- **Emitting `:focus` before `:hover`.** Silent — everything looks right until you tab onto
  a checked control.
- **A per-dialog stylesheet.** It looks correct in whichever theme you tested and desyncs
  the moment the desktop switches.
- **A directional QSS property.** Passes every test, looks perfect, and is broken in Arabic
  only.
- **Colour as the only difference between two badges.** The most common accessibility
  regression there is, because it looks obviously distinct to the person who wrote it.
- **A theme that ships "for now" without the contrast check.** Whoever selects it is using
  the whole application through it; there is no low-stakes theme.

## 10. Before you commit a UI change

- [ ] Every new focusable widget has an accessible name.
- [ ] No new state is distinguishable by colour alone.
- [ ] No `font-size` in `px`; nothing has a fixed height that text can outgrow.
- [ ] Focus changes colour or fill only — no ring, no added border, no size change.
- [ ] Any new `:focus` rule is emitted after that selector's `:hover` / `:checked` rules.
- [ ] A new control is placed in the tab chain in the same commit.
- [ ] A new dialog is parented, unstyled, centred by the matching idiom, and closable
      headless.
- [ ] No directional QSS property, no hard-coded `AlignLeft` / `AlignRight`.
- [ ] Custom painting reads the layout direction, or says why it need not.
- [ ] `./local-CI.sh` is green — the GUI suite is where most of the above is enforced.

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §2 every focusable widget has an accessible name | `tests/gui-smoke.py` — four sweeps, over the main window and the Repositories, Rollback and Settings pages, each naming the widgets that failed |
| §3 state is never signalled by colour alone | nothing automatic |
| §4 no hard-coded `px` font size | `tests/gui-smoke.py` — every font size is in points, and derives from the desktop's own default |
| §5 focus draws no ring | `tests/gui-smoke.py` — *"focus draws no outline ring"*, paired with *"focus still gives a cue"*, so the rule cannot be satisfied by removing the cue altogether. ONEUP-0076 INV-4 adds the half a stylesheet parse cannot see: the focused and unfocused renders of the painted switch must be related by a consistent colour-to-colour mapping, which a ring drawn inside its fixed rect breaks |
| §5.3 focus changes no box | `tests/gui-smoke.py` — ONEUP-0076 INV-4 expands every `border` shorthand and asserts a `:focus` rule sets no width, style or radius its rest rule does not already set to the same value; colour is the only thing it may move |
| §5.3 the 2 px area floor | **nothing directly.** The four panels carry a 2 px rest border in both sheets and INV-4 would catch a `:focus` rule narrowing one, but nothing fails a rest border authored at 1 px in the first place |
| §5.4 the 3:1 focus-indicator ratio | **ONEUP-0076's focus computation, driven from `tests/gui-smoke.py`** — 910 pairs over both palettes and both overlay states, each against the floor it is held to. It replaces *"nothing computes contrast anywhere in the suite"*, which is what this row said until that item shipped |
| §5.1 every focusable control HAS a treatment | `tests/gui-smoke.py` — ONEUP-0076 INV-1 sweeps the window and each dialog and fails any focusable widget matching no row of that spec's table, by object name, class **and** containing surface. Its one exclusion is Qt-supplied chrome with no name of ours and no rule in either sheet |
| §5.6 tab order follows visual order | `tests/gui-smoke.py` — ONEUP-0064 INV-1 flattens the layout tree to visual order and walks the focus chain end to end against it, once for the window and once for `SettingsDialog`, which has a chain of its own. It is the first thing to actually check this rule |
| §6.1 a dialog inherits the theme | `tests/gui-smoke.py` catches the half that is a rule breach — no widget carries a stylesheet of its own. **Nothing checks the background a dialog actually paints**, which is why `_QSS`'s missing `QDialog` rule went unnoticed; ONEUP-0076 §8 prescribes the rule and ONEUP-0027 INV-7 is the nearest test to it |
| §7 themes | ONEUP-0027 — the contrast check is that item's to write, and the light theme's `lastrun` text sits at 3.07:1 today |
| §8.1 no directional QSS property | nothing automatic |
| §8.2 no hard-coded `AlignLeft` / `AlignRight` | nothing automatic. Nothing violates it today — the `#LinkBtn` violation is §8.1's `text-align: left`, not this rule |
| §8.3 custom painting applies the direction | **nothing** — the toggle knob does not apply it (ONEUP-0032) |

**The gated half is the half a script can see.** A name is present or absent; a font size is
points or pixels; an outline is drawn or not. Everything left ungated needs a judgement made
(is this cue really more than colour?). **The contrast half stopped being manual with
ONEUP-0076**, whose computation runs over a palette nobody has written yet — which is what
ONEUP-0027's six new themes are checked against, rather than against a screenshot.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: §6.2's dialog example was the hand-rolled X11 path ONEUP-0049 replaced and never named `center_on_parent`; the tray glyph is dark, not white; §7's contrast check was described in the present tense although nothing computes it, and its "the built-ins pass" premise is false at 3.07:1; and the focus cue's state-change contrast was measured at 1.14–1.62:1 in three of four cases |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged. Nothing from loop 1 resurfaced in this lane, which is the proof those fixes held. The two findings that verified are logged against `files-and-naming.md` and `workflow.md` |
| 3 | 2026-07-26 | none | clean. Collateral only: a pointer to the deleted `dialogs.md` became a plain mention, so it no longer reads as a live path. |
| 4 | 2026-07-26 | none | converged. |
