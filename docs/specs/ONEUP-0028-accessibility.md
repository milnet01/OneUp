# ONEUP-0028 — Make OneUp usable for blind, partially-sighted, and colour-blind users

**Status:** Cold-eyes converged (2 loops — loop 1: 8 HIGH / 10 MEDIUM / 9 LOW, 28
verified and fixed, 1 dismissed; loop 2: polish only, 7 verified and fixed, 5
dismissed). Ready to implement.
**Roadmap:** ONEUP-0028 (🚧)
**Kind:** accessibility (GUI only — no engine or marker change)

## Goal

Three groups, one pass:

1. **Blind** — OneUp is fully operable and *comprehensible* with a screen reader
   (Orca over AT-SPI): every control has an accessible name, run progress and the
   final outcome are spoken, and no control is an unlabelled icon.
2. **Partially sighted** — text follows the desktop's font size *and* can be
   enlarged from inside OneUp; a high-contrast option is available; every control
   is keyboard-reachable with a **visible focus indicator**.
3. **Colour-blind** — no state is signalled by colour alone. Every colour cue is
   paired with text or shape.

## Background — what is broken today

All citations verified against `updater.py` at commit `2f240fd` (2842 lines).

### Blind / screen reader

| Gap | Where | Effect with Orca |
| --- | --- | --- |
| `ToggleSwitch` is a `QAbstractButton` with **no text and no accessible name** | `updater.py:357-403` | The five task switches — the app's primary controls — announce as an unnamed check box. A blind user cannot tell which task they are toggling. |
| The disclosure arrow is an icon-only `QToolButton` (arrow type only, no text) | `updater.py:440-446` | Announces unnamed. |
| Progress bar, log pane, banners, badges carry no accessible name | `updater.py:1148-1152`, `1214-1220`, `_make_banner` `1245-1260` | Progress is announced as a bare percentage with no context; a banner that *appears* is never announced at all. |
| Nothing is announced when a step starts/ends or a run finishes | `handle_marker` `2338`, `on_finished` `2499` | A blind user gets silence for the whole run, then must hunt for the outcome. |
| Repo-manager switches carry no name | `_make_row` `696-730` | 20+ unnamed switches in the Repositories dialog. |

**Roles are already correct — do not add machinery for them.** The roadmap bullet
asks for "accessible names/**roles** on every control". Verified empirically on
PySide6 6.11: a checkable `QAbstractButton` is mapped by
`QAccessibleWidget`/`QAccessibleButton` to `QAccessible.Role.CheckBox` with
`state().checkable == 1` and `state().checked` tracking `isChecked()`. So Orca
already announces *"<name>, check box, checked"* — the role and the on/off state
come for free once the **name** exists. No custom `QAccessibleInterface` is
needed, and none should be written.

### Partially sighted

| Gap | Where | Effect |
| --- | --- | --- |
| Every font size in the stylesheet is an **absolute pixel value** — **twelve** `font-size: …px` declarations (`21px`, `14px`×2, `12px`×6, `11px`×3) | `_QSS` `202-318` | A user who raises their desktop font size sees **no change in OneUp** — the QSS pixel value overrides the inherited font. This is the single biggest low-vision failure. |
| No high-contrast option | — | Body text is mid-grey on near-black (`tdesc="#a7b0be"` on `rowcard="#1a1f27"`, `updater.py:322-323`); banners are translucent gradient washes (`282-304`). |
| **No `:focus` rule anywhere in the QSS** | `_QSS` `240-312` | Once a stylesheet styles a `QPushButton`, Qt's native focus decoration is gone. Keyboard focus is therefore *invisible* on every button in the app (WCAG 2.4.7 failure). |
| `ToggleSwitch.paintEvent` never draws a focus ring | `updater.py:388-403` | Same, for the primary controls. |
| Header tab order does not match visual order | created `settings, recenter, repos, about` (`1073-1096`), laid out `settings, repos, recenter, about` (`1100-1103`) | Tabbing jumps sideways. |

### Colour-blind

| Gap | Where | Effect |
| --- | --- | --- |
| Task on/off is signalled by track colour (green/red) as the **only deliberate cue** | `updater.py:392` `track = GREEN if self.isChecked() else RED` | Red/green is the classic confusion pair (deuteranopia/protanopia): the *primary* control state is unreadable. The knob's left/right position is a second-order cue, but at 56×30 px with no reference point beside it (`updater.py:365`) it is easy to miss — it reads as decoration, not state. |
| The tray "updates waiting" badge is an amber dot — colour only | `_tray_icon` `1492-1499` | Attention state indistinguishable from the normal icon. (The tooltip does carry text — `1566-1567` — but only on hover.) |
| The overdue last-run line is signalled only by turning amber | QSS `268`, `refresh_last_run` `1943-1947` | "Overdue" is invisible. |

**Already correct — no change needed here, despite the roadmap naming it.** The
bullet lists "red/green step badges" as a colour-only gap, but per-step outcomes
are already **text**: `_step_badge` returns "Failed", "Up to date", "3 installed"
(`2311-2327`), and the badge's colours come from one theme pair
(`badgebg`/`badgefg`) that does not vary by outcome. The reboot/warning banners
likewise already carry a `⚠` glyph plus prose (`1282`, `2551-2558`). So the
colour-blind work is the three rows above — switch, tray badge, overdue line —
and an implementer should not go looking for badge colours to fix. What matters
for the badges is that this stays true.

## Design

### 1. Accessible names — a name for everything a user can reach

`TaskRow.__init__` (`updater.py:416`) names its own controls, so every task row is
self-describing. The description is **stored** (today it is only a local, `424`)
because `_render_badge` needs it:

```python
self._description = description
self.switch.setAccessibleName(f"{title} — include in this update")
self.switch.setAccessibleDescription(description)
self.disclosure.setAccessibleName(f"Packages that {title.lower()} will change")
```

The disclosure name is deliberately state-agnostic ("Packages that … will change",
not "Show …"): the control toggles, so an imperative name would read backwards
once the panel is open. Qt reports the expanded/collapsed state separately.

`Updater.__init__` names the non-text widgets: progress bar ("Update progress"),
log pane ("Update log"), the last-run line ("Last update run"), and each banner
frame plus its label — named for its role, not its styling:

| Widget | Accessible name |
| --- | --- |
| `reboot_banner` / `reboot_label` | "Restart recommended" |
| `services_banner` / `services_label` | "Services should restart" |
| `warn_banner` / `warn_label` | "Warning" |
| `appupdate_banner` / `appupdate_label` | "OneUp update available" |
| `RollbackDialog.list` (`897`) | "Restore points" |

`RepoManagerDialog._make_row` names each repo switch
`f"{repo['name']} — include this repository"`. The name must **not** bake in the
on/off state (`"… — enabled"` would announce "enabled" for a disabled repo);
state comes from `state().checked`, per the roles note above.

The two new Settings controls (§3, §4) are ordinary text buttons and are named by
their text, like the existing toggles.

Buttons that already carry visible text need nothing: Qt derives the accessible
name from the button text, and the accessible *description* from the tooltip when
none is set explicitly (verified: an explicit `setAccessibleDescription` wins;
otherwise `QAccessibleWidget` falls back to `toolTip()`).

**Outcome reachability.** `TaskRow._render_badge` (`542`) also refreshes the
switch's accessible description, so a blind user tabbing to a switch after a run
hears *"System packages … 3 installed · 42s"* rather than having to find a
separate, unfocusable badge label:

```python
def _render_badge(self):
    parts = [p for p in (self._badge_text, self._timing) if p]
    text = "  ·  ".join(parts)
    self.badge.setText(text)
    self.badge.setVisible(bool(parts))
    # The outcome is only otherwise on an unfocusable label — put it where a
    # screen reader will reach it, on the row's own control.
    self.switch.setAccessibleDescription(
        f"{self._description} {text}".strip() if text else self._description)
```

**`clear_badge` must route through `_render_badge`** rather than clearing the
fields inline as it does today (`547-550`): `_launch` calls it on every row at the
start of each run (`2267-2269`), and without the re-render the switch would keep
announcing the *previous* run's outcome on a row that has not run yet.

### 2. Announcements — one helper, degrading cleanly

Qt 6.8 added `QAccessibleAnnouncementEvent` (a "speak this now" event). PySide6 is
**intentionally unpinned** (`docs/standards/dependencies.md:44` — the RPM uses the
distro's `python3-pyside6`, and Leap may ship an older one), so it is imported
conditionally and the pre-6.8 path degrades to an `Alert` event on the widget
**whose visible text already carries the message**, which Orca reads:

```python
try:                                   # Qt 6.8+
    from PySide6.QtGui import QAccessibleAnnouncementEvent
except ImportError:                    # older PySide6 (e.g. Leap) — alert fallback
    QAccessibleAnnouncementEvent = None
```

```python
def _announce(self, text: str, source: QWidget | None = None):
    """Speak `text` to a screen reader, if one is listening.

    `source` is the widget whose on-screen text IS this message — the pre-6.8
    fallback fires an Alert on it and lets the screen reader read that text. It
    must never be given a widget whose text says something else.

    _last_announcement is kept unconditionally so the headless smoke test can
    assert what *would* be spoken (QAccessible.isActive() is False offscreen).
    """
    self._last_announcement = text
    if not text or not QAccessible.isActive():
        return
    if QAccessibleAnnouncementEvent is not None:
        QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(self, text))
    else:
        QAccessible.updateAccessibility(
            QAccessibleEvent(source or self.status, QAccessible.Event.Alert))
```

The fallback deliberately does **not** call `setAccessibleName` on the borrowed
label: an explicit accessible name on a `QLabel` is permanent, so every later
`status.setText` (`2278-2283`, `2519-2540`) would become invisible to AT.

Announced (and only these — enough to follow a run, not a monologue). The roadmap
bullet also asks for the **live log** to be announced; that is a deliberate,
reasoned exclusion rather than an oversight — see the first entry under *Out of
scope*:

| When | Text | `source` |
| --- | --- | --- |
| `STEP_BEGIN` | `"<label>, step <i> of <n>"` | `self.status` (set immediately before) |
| `STEP_END` | `"<task title>: <badge>"` | the row's `badge` label |
| `_show_warning` | `"Warning: <text>"` | `self.warn_label` |
| `on_finished` (run) | the summary line already set on `self.status` | `self.status` |
| `on_finished` (check) | the "N update(s) available" / "up to date" line | `self.status` |

Three ordering rules, because `_show_warning` fires from four sites — two of them
*inside* `on_finished` (`2453`, `2475`, `2579`, `2591`) — and
`QAccessibleAnnouncementEvent` defaults to **Polite** priority, meaning a later
announcement can supersede an earlier one:

1. In `on_finished`, announce the summary **where `status.setText` happens**, and
   let the warning announcement come **after** it — the warning is the more
   urgent message, so it must be the one left standing.
2. `_notify_when_away`'s desktop-notification text (`2618-2620`) is **not**
   re-announced. It duplicates the summary; a screen-reader user would hear it
   twice.
3. `TIMING` and `FREED` rewrite a row's badge *after* `STEP_END`
   (`2372-2387`; asserted at `tests/gui-smoke.py:128-129`) — so the spoken
   `STEP_END` text is the badge **as it stood at that moment** ("Cache cleanup:
   Done"), while the final badge reads "Reclaimed 1.0G · 3s". The refresh updates
   the switch's accessible description (§1) so the final figure is reachable by
   Tab, but it is **not** re-spoken. Two utterances per step is the budget.

*Known, accepted wording seam:* `STEP_BEGIN` speaks the **engine's** step label
while `STEP_END` speaks the `TASKS` title, so one step can be named two ways in
consecutive utterances ("Updating system packages…" then "System packages: 3
installed"). Both are accurate; unifying them would mean the GUI second-guessing
the engine's own label.

### 3. Text that scales

`build_theme` gains two keyword arguments and derives every font size from the
**desktop's own default point size**, so OneUp follows the system font setting and
the in-app control multiplies on top of it:

```python
def build_theme(dark: bool, scale: float = 1.0, high_contrast: bool = False) -> str:
```

```python
# QFontInfo resolves a font specified in pixels; the clamp defends against both
# Qt's "not set in points" sentinel (-1 — note `or` would NOT catch it, -1 is
# truthy) and an absurd desktop font that would make the app unusable.
base = QFontInfo(QApplication.font()).pointSizeF()
if not 6.0 <= base <= 30.0:
    base = 10.0
```

**Ordering constraint:** `QApplication.font()` is only meaningful once the
`QApplication` exists, so `build_theme` must never be called before it. Both call
paths already satisfy this — `main()` constructs `QApplication([])` before
theming (`2807-2814`), and the Settings handlers run long after — but the clamp
above is also what keeps a too-early call from emitting a negative point size
rather than crashing.

Four derived sizes replace the twelve hard-coded pixel values. The multipliers are
the current px values over a 10 pt (≈13.3 px at 96 dpi) default, so `scale=1.0`
reproduces today's hierarchy to within a fraction of a point:

| Key | Multiplier | Replaces |
| --- | --- | --- |
| `fs_header` | `1.58` | `21px` (Header) |
| `fs_med` | `1.05` | `14px` (TaskName, RunBtn) |
| `fs_body` | `0.90` | `12px` (Tagline, TaskDesc, Status, LastRun, ProgressBar, SizeResult) |
| `fs_small` | `0.83` | `11px` (Badge, DetailList, Log) |

Emitted as `f"{base * mult * scale:.1f}pt"`. Fractional `pt` in a Qt stylesheet is
verified to work (`font-size: 14.5pt` → `QFont.pointSizeF() == 14.5`).

**Two metrics scale with the text, not just the fonts**, or enlarged text crowds
fixed padding: `QLabel#Badge`'s `padding: 2px 9px` (`226-229`) and
`QProgressBar`'s `min-height: 20px` (`271-273`) become `$badgepad` /
`$progmin`, multiplied by the same `scale`. Every other length (border radii,
layout margins) is decoration that does not bound text, and stays absolute.

**Text size** is a three-state cycling `#GhostBtn` in Settings, matching the
existing toggle-button idiom (`auto_btn`, `tray_btn`, …) rather than introducing a
combo box the QSS doesn't style:

```python
TEXT_SCALES = [("Normal", 1.0), ("Large", 1.2), ("Larger", 1.45)]
```

Persisted as `text_scale` in the existing `QSettings("OneUp", "OneUp")`.

**The single theming entry point.** `main()`'s local `apply_theme` closure
(`2811-2812`) reads neither setting and is unreachable from a Settings handler or
from the test, so it is replaced by a module-level function:

```python
def apply_app_theme(app: QApplication):
    """Install the stylesheet for the current desktop scheme + the user's
    accessibility preferences. The ONE place the QSS is applied."""
    s = QSettings("OneUp", "OneUp")
    app.setStyleSheet(build_theme(
        current_is_dark(app),
        scale=float(s.value("text_scale", 1.0, type=float)),
        high_contrast=bool(s.value("high_contrast", False, type=bool))))
```

`main()` calls it at startup and rewires `colorSchemeChanged` (`2815-2818`) to it;
the two new Settings buttons write their `QSettings` key and then call it, so a
change applies live with no restart and no window rebuild.

*Caveat, stated so nobody over-claims it:* the desktop font size is sampled **when
the theme is applied** — startup, a light/dark switch, or a text-size/contrast
change. Qt has no font-changed signal wired here, so a desktop font change made
while OneUp is open takes effect on the next of those events.

*No clipping risk at `Larger`:* the only fixed geometry is `ToggleSwitch`'s
56×30 (it holds no text — `365`); `run_btn`'s 44 px and the log's 180 px are
**minimums** (`1126`, `1218`), and the detail list's `setMaximumHeight(180)`
(`474`) is a scroll area that already scrolls. The main window sets
`setMinimumWidth`, not a fixed size (`944`).

### 4. High contrast — an overlay, not a third palette

The HC option appends a small override stylesheet **after** the base sheet. Qt
resolves equal-specificity conflicts the way CSS does — the later rule wins
(verified: two `QLabel#T { font-size }` rules, the second took effect) — so the
overlay redefines only the rules that need it and the two existing palettes stay
untouched. Its colours come from `_HC_DARK` / `_HC_LIGHT`, so HC composes with the
light/dark switch instead of replacing it. Persisted as `high_contrast`.

**Specificity is the trap here, and it sets the real size of the overlay.** Qt
follows CSS2 specificity, so a bare `QPushButton#RunBtn` overlay rule does **not**
beat the base's `QPushButton#RunBtn:hover` — a pseudo-state selector outranks it.
An overlay that only restates the plain rules would leak the gradient back the
moment the pointer touches a button. The overlay must therefore restate **every
pseudo-state and attribute variant** the base defines:

| Base rule to beat | `updater.py` |
| --- | --- |
| `#RunBtn:hover`, `#RunBtn:pressed`, `#RunBtn:disabled` | `244-250` |
| `#GhostBtn:hover`, `#GhostBtn:checked`, `#GhostBtn:disabled` | `256-258` |
| `#LinkBtn:hover` | `264` |
| `#RestartBtn:hover` | `291-293` |
| `#BannerBtn:hover` | `310-312` |
| `#RowBorder:hover`, `#RowBorder:hover #RowCard` | `217-222` |
| `QLabel#LastRun[stale="true"]` | `268` |

Plus the plain rules for surfaces, text, badges, banners, progress, log and
tooltips: **~27 rules**, not the dozen a first pass would guess.

`ToggleSwitch` is painted in code, so the stylesheet cannot reach it. It exposes a
`highContrast` Qt property that the sheet sets — the mechanism the class already
uses for `knobPos` (`386`):

```
ToggleSwitch { qproperty-highContrast: false; }   /* base sheet — see caveat */
ToggleSwitch { qproperty-highContrast: true;  }   /* HC overlay */
```

**Caveat that makes the explicit `false` mandatory:** a `qproperty-` assignment is
*not* reverted when the rule stops matching (verified — clearing the stylesheet
left the property `true`). Without the base sheet stating `false`, turning HC off
would leave the switches stuck in HC paint. In HC the switch draws a 2 px outline
around the track and a black rim on the knob, so it is distinguishable from its
surface.

### 5. Focus visibility

QSS `:focus` rules for the **eight** styled focusable controls — the six buttons
`#RunBtn`, `#GhostBtn`, `#LinkBtn`, `#BannerBtn`, `#RestartBtn`, `#Disclose`, plus
`QPlainTextEdit#Log` (`276-280`) and `QScrollArea#DetailScroll` (`237`), whose
native focus rects the stylesheet has also replaced. A 2 px accent outline (HC
overlay: 3 px, palette key `hcfocus`).

> **Corrected 2026-08-21, and this paragraph was wrong in three ways when it was
> written** — recorded rather than rewritten, because this spec is shipped and the
> record is what it is for. **The count was never true:** `#Disclose`,
> `QPlainTextEdit#Log` and `QScrollArea#DetailScroll` carried no `:focus` rule at
> all, so it was five, not eight — a sweep of the whole window found **sixteen of
> its thirty-four focusable widgets with no cue whatever**, five of them the on/off
> switches. **The outline was never built and is forbidden:** the 2026-07-25
> no-focus-ring decision rules out a ring or an outline outright, and the palette
> key `hcfocus` does not exist. **ONEUP-0076 is what makes this section true**, by
> a different mechanism than the one described here — a derived fill, or a derived
> colour on an existing 2 px border for the panels that hold their own content.
> `docs/standards/ui-and-accessibility.md` §5 is canonical.

**Placement matters:** `#GhostBtn:focus` and `#GhostBtn:checked` have equal
specificity, so the `:focus` rules must be emitted **after** all `:hover` /
`:checked` / `:pressed` rules. Emitted before them, a focused *checked* toggle
("Passwordless: on") would show no ring — precisely the state a keyboard user
lands on.

`ToggleSwitch.paintEvent` draws a **double** ring (white outer, dark inner) when
`hasFocus()`, so it reads against both the green and the red track. Verified:
`QAbstractButton` already has `Qt.StrongFocus` (11), so the switch is
tab-reachable today — only the indicator was missing.

> **Corrected 2026-08-21.** No ring was ever drawn, and none may be: that method's
> own closing comment said so, which made this the claim a reader would most
> reasonably have trusted and the one furthest from the code. What ONEUP-0076
> built instead is a **darkened track** — the same pixels, a derived colour — so
> the state shape and the knob still read on it. The rest of the paragraph holds:
> the switch was always tab-reachable, and only the indicator was missing.

### 6. Tab order

`setTabOrder` after the header row is laid out, fixing the visual/tab mismatch:
`settings_btn → repos_btn → recenter_btn → about_btn → (first task switch)`, and
`check_btn → run_btn` in the action row.

### 7. Colour never alone

| Cue | Pairing added |
| --- | --- |
| Switch on/off | A shape drawn in the track **opposite the knob**: a **vertical bar** when on, an **open circle** when off (the iOS convention). Drawn with `QPainter` primitives in the knob's white, not a font glyph — a painted widget has no font-fallback chain, so a missing character would silently vanish. |
| Tray attention badge | A white `!` drawn inside the amber disc, so the attention icon differs in *shape*, not just colour. |
| Overdue last-run line | The text itself gains a `⚠` prefix and the word `overdue`. Text is safe here (unlike the switch) because this is a `QLabel` in the app's normal font stack, and the app already relies on `⚠` in exactly this way (`1282`, `2551-2558`). |

Also affected: `set_controls_enabled(False)` disables the five switches for the
duration of a run (`2145-2149`), so the "Tab to a switch to hear its outcome"
affordance from §1 applies once `on_finished` re-enables them (`2510`). Names and
descriptions are set regardless of enabled state, which is what a screen reader
needs to describe a greyed-out control.

## Correctness invariants (the tests lock these in)

Each invariant states the test that would **fail on today's code** and pass only
on a correct implementation.

- **INV-1** Every focusable widget in the main window, `RepoManagerDialog`,
  `SettingsDialog` and `RollbackDialog` reports a non-empty accessible name **or**
  non-empty visible text.
  *Test:* walk `findChildren(QWidget)`, keep `focusPolicy() != Qt.NoFocus`, and
  assert `w.accessibleName() or getattr(w, "text", lambda: "")()`. The `getattr`
  is required, not defensive: focusable non-buttons have no `.text()` — the log is
  a `QPlainTextEdit` (`toPlainText()`), and `QScrollArea#DetailScroll` plus its
  viewport (`469-476`) and `RollbackDialog`'s `QListWidget` (`897`) have no text at
  all. Those three container widgets are named (§1) rather than exempted, so the
  sweep needs no exemption list.
- **INV-2** No state is conveyed by colour alone, and each check **must be able to
  fail**:
  - *Switch:* stop the 130 ms knob animation (`369-378`) and set `_pos` to its
    settled value, render with `QWidget.grab()`, then count near-white pixels in
    the track half **opposite the knob** — `> 0` in both the checked and unchecked
    render. A plain colour-only track leaves that region a solid fill, so today's
    code fails. (A bare "checked and unchecked images differ" check would **pass
    today**: the knob already translates. That is not the invariant.)
  - *Tray:* count near-white pixels **inside the amber disc, inset by 4 px** in
    `_tray_icon(True)` — `> 0` only once a glyph is drawn. The inset excludes the
    disc's existing white outline pen (`1495`). (A bare "attention and plain
    pixmaps differ" check would **pass today** — the disc alone differs.)
  - *Last run:* a 20-day-old history yields `"overdue" in last_run.text()`.
- **INV-3** The stylesheet contains **no** absolute pixel font size, and every
  font size scales with `scale`.
  *Test:* `re.search(r"font-size:\s*[\d.]+px", qss) is None` — a *regex on the
  declaration*, not `"px" not in <line containing font-size>`, which would
  false-fail on the two lines that legitimately keep a px length beside a
  font-size (`padding: 2px 9px` at `227`, `min-height: 20px` at `272`). Plus:
  every `pt` number for `scale=1.45` is strictly larger than its `scale=1.0`
  counterpart.
- **INV-4** All eight styled focusable controls have a `:focus` rule, and each
  `:focus` rule appears **after** the last `:hover`/`:checked`/`:pressed` rule for
  the same selector (the specificity-tie ordering from §5).
  **Superseded 2026-08-21 by ONEUP-0076 INV-1**, which sweeps every focusable
  widget in the window and in each dialog rather than a list of eight — the count
  above was never right. The ordering half is unchanged and still checked.
- **INV-5** Tab order matches visual order in the header and action rows.
  *Test:* a `nextInFocusChain` walk from `settings_btn` reaches `repos_btn` before
  `recenter_btn`. Fails today (creation order puts `recenter` first).
  **Superseded 2026-08-21 by ONEUP-0064 INV-1.** That item moves *Repositories*
  and *Recenter* into `SettingsDialog`, and a `QDialog` has its own focus chain, so
  a walk rooted in the window can no longer reach either control and would collect
  an empty list. The replacement flattens the layout tree to visual order and walks
  the whole chain against it — twice, once for the window and once for the dialog —
  which covers the same guarantee and every other control besides.
- **INV-6** High contrast changes appearance only: `build_theme(dark,
  high_contrast=False)` is a strict **prefix** of `build_theme(dark,
  high_contrast=True)`, the overlay sets `qproperty-highContrast: true` while the
  base sets `false`, and the overlay restates every pseudo-state selector listed
  in §4. *What this does not prove:* that the HC colours meet a contrast ratio —
  that is a design review, not a unit test.
- **INV-7** Progress and outcome are announced: `_last_announcement` is non-empty
  and names the step after `STEP_BEGIN`, the outcome after `STEP_END`, and the
  summary after `on_finished`; `_announce` never throws when `QAccessible` is
  inactive. *Coverage limit, stated honestly:* offscreen `QAccessible.isActive()`
  is `False`, so CI exercises the **message construction and the no-throw
  contract**, never the 6.8 event dispatch nor the pre-6.8 Alert fallback. Both
  dispatch paths are manual-verification territory (see Out of scope).
- **INV-8** The two accessibility settings persist and apply live: writing
  `text_scale` / `high_contrast` and calling `apply_app_theme(app)` changes
  `app.styleSheet()` with no restart and no window rebuild.

## Tests (`tests/gui-smoke.py`)

A new section, in the existing `check(name, cond)` style; no engine test changes
(`tests/run-tests.sh` is untouched — this feature adds no marker and no engine
flag).

1. INV-1 sweep over the main window, then over `RepoManagerDialog` built from two
   stub repo dicts, `SettingsDialog`, and `RollbackDialog`. All four are
   constructed, never `exec()`-ed — the pattern the suite already uses for
   `RollbackDialog` (`tests/gui-smoke.py` rollback-picker block), so nothing
   blocks headless.
2. `build_theme` assertions: INV-3, INV-4 (presence **and** ordering), INV-6.
3. Marker-driven announcements: feed `STEP_BEGIN` / `STEP_END`, then
   `on_finished`, asserting `_last_announcement` after each, plus a direct
   `_announce("x")` no-throw call (INV-7).
4. `_tray_icon` disc-interior white-pixel count (INV-2).
5. **Extend the existing stale-last-run block** (`tests/gui-smoke.py:788-821`,
   added for ONEUP-0030 — it already has a `_seed_history(days_ago)` helper and
   asserts the `stale` dynamic property) with the new `"overdue"` text assertion.
   Do not add a second seeded-history block.
6. `ToggleSwitch` state-shape pixel count, animation stopped (INV-2).
7. Tab-order walk (INV-5).
8. `apply_app_theme` round-trip with both settings (INV-8).

## Docs & release

- `README.md` — a short **Accessibility** section: Orca support, the two Settings
  controls, and the fact that OneUp follows the desktop font size.
- `CLAUDE.md` — one line under "Conventions specific to this repo": new
  interactive widgets need an accessible name, and state must never be
  colour-only.
- The two new Settings controls live inside the existing `SettingsDialog`, so
  `docs/standards/ui-and-accessibility.md` §6 needs no change — but its checklist
  (inherit the app
  QSS, no per-dialog stylesheet) governs them, and the HC overlay must stay an
  **application-wide** sheet for exactly that reason.
- `CHANGELOG.md` — `### Added` entry under `[Unreleased]`.
- No version bump in this change (release tooling handles the six lockstep sites).

## Out of scope (deliberate)

- **The log pane as a live region.** The roadmap bullet asks for "the live log and
  progress announced". Progress *is* announced (§2); the log deliberately is not.
  It streams hundreds of `zypper` lines per run — announcing them would make the
  app unusable with a screen reader, and the log is already reachable as a named,
  focusable text area a user can read on demand at their own pace.
- **Extra keyboard shortcuts** (e.g. `Ctrl+R` to run). Every control is already
  keyboard-reachable via Tab once INV-4/INV-5 land; inventing accelerators risks
  clashing with the desktop's own and adds surface with no accessibility gain.
- **Themes beyond light/dark/high-contrast** — that is ONEUP-0027, which must keep
  WCAG-AA contrast for any theme it adds.
- **A live Orca audit pass**, and with it the runtime verification of both
  announcement dispatch paths (INV-7's coverage limit). CI cannot assert what a
  screen reader says; the roadmap bullet's "audit pass with Orca" stays open as a
  follow-up verification task.
- **Engine (`update_system.sh`) changes.** The engine's output is already plain
  text; nothing about it is visual.
