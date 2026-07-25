# ONEUP-0028 — Make OneUp usable for blind, partially-sighted, and colour-blind users

**Status:** draft (pre-cold-eyes).
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

All citations verified against `updater.py` at the commit this spec was written on
(2842 lines; `git rev-parse --short HEAD` = `2f240fd`).

### Blind / screen reader

| Gap | Where | Effect with Orca |
| --- | --- | --- |
| `ToggleSwitch` is a `QAbstractButton` with **no text and no accessible name** | `updater.py:357-403` | The five task switches — the app's primary controls — announce as an unnamed button. A blind user cannot tell which task they are toggling. |
| The disclosure arrow is an icon-only `QToolButton` (arrow type only, no text) | `updater.py:440-446` | Announces unnamed. |
| Progress bar, log pane, banners, badges carry no accessible name | `updater.py:1148-1152`, `1214-1220`, `_make_banner` `1245-1260` | Progress is announced as a bare percentage with no context; a banner that *appears* is never announced at all. |
| Nothing is announced when a step starts/ends or a run finishes | `handle_marker` `2338`, `on_finished` `2499` | A blind user gets silence for the whole run, then must hunt for the outcome. |
| Repo-manager switches carry no name | `_make_row` `696-730` | 20+ unnamed switches in the Repositories dialog. |

### Partially sighted

| Gap | Where | Effect |
| --- | --- | --- |
| Every font size in the stylesheet is an **absolute pixel value** (`21px`, `14px`, `12px`, `11px`) | `_QSS` `202-318` | A user who raises their desktop font size sees **no change in OneUp** — the QSS pixel value overrides the inherited font. This is the single biggest low-vision failure. |
| No high-contrast option | — | Body text is mid-grey on near-black (`tdesc="#a7b0be"` on `rowcard="#1a1f27"`, `updater.py:322-323`); banners are translucent gradient washes (`282-304`). |
| **No `:focus` rule anywhere in the QSS** | `_QSS` `240-312` | Once a stylesheet styles a `QPushButton`, Qt's native focus decoration is gone. Keyboard focus is therefore *invisible* on every button in the app (WCAG 2.4.7 failure). |
| `ToggleSwitch.paintEvent` never draws a focus ring | `updater.py:388-403` | Same, for the primary controls. |
| Header tab order does not match visual order | created `settings, recenter, repos, about` (`1073-1096`), laid out `settings, repos, recenter, about` (`1100-1103`) | Tabbing jumps sideways. |

### Colour-blind

| Gap | Where | Effect |
| --- | --- | --- |
| Task on/off is signalled **only** by track colour (green/red) | `updater.py:392` `track = GREEN if self.isChecked() else RED` | Red/green is the classic confusion pair (deuteranopia/protanopia): the *primary* control state is unreadable. |
| The tray "updates waiting" badge is an amber dot — colour only | `_tray_icon` `1492-1499` | Attention state indistinguishable from the normal icon. (The tooltip does carry text — `1566-1567` — but only on hover.) |
| The overdue last-run line is signalled only by turning amber | QSS `268`, `refresh_last_run` `1943-1947` | "Overdue" is invisible. |

Already correct, and must stay that way: per-step outcomes are **text** badges
("Failed", "Up to date", "3 installed" — `_step_badge` `2311-2327`), and the
reboot/warning banners carry a `⚠` glyph plus prose (`1282`, `2551-2558`).

## Design

### 1. Accessible names — a name for everything a user can reach

`TaskRow.__init__` (`updater.py:416`) names its own controls, so every task row is
self-describing:

```python
self.switch.setAccessibleName(f"{title} — include in this update")
self.switch.setAccessibleDescription(description)
self.disclosure.setAccessibleName(f"Show which packages {title.lower()} will change")
```

`Updater.__init__` names the non-text widgets: progress bar ("Update progress"),
log pane ("Update log"), last-run line, and each banner frame + its label.
`RepoManagerDialog._make_row` names each repo switch
(`f"{repo['name']} — enabled"`).

Buttons that already carry visible text need nothing: Qt derives the accessible
name from the button text, and the accessible *description* from the tooltip when
none is set explicitly (verified: an explicit `setAccessibleDescription` wins;
otherwise `QAccessibleWidget` falls back to `toolTip()`).

**Outcome reachability.** `TaskRow._render_badge` (`542`) also refreshes the
switch's accessible description to `f"{description} {badge}"` — so a blind user
tabbing to a switch after a run hears *"System packages … 3 installed · 42s"*
rather than having to find a separate, unfocusable badge label.

### 2. Announcements — one helper, degrading cleanly

Qt 6.8 added `QAccessibleAnnouncementEvent` (a "speak this now" event). PySide6 is
**intentionally unpinned** (`docs/standards/dependencies.md:44` — the RPM uses the
distro's `python3-pyside6`, and Leap may ship an older one), so it is imported
conditionally and the pre-6.8 path degrades to an `Alert` event on the status
label, which Orca reads:

```python
try:                                   # Qt 6.8+
    from PySide6.QtGui import QAccessibleAnnouncementEvent
except ImportError:                    # older PySide6 (e.g. Leap) — alert fallback
    QAccessibleAnnouncementEvent = None
```

```python
def _announce(self, text: str):
    """Speak `text` to a screen reader, if one is listening.

    _last_announcement is kept unconditionally so the headless smoke test can
    assert what *would* be spoken (QAccessible.isActive() is False offscreen).
    """
    self._last_announcement = text
    if not text or not QAccessible.isActive():
        return
    if QAccessibleAnnouncementEvent is not None:
        QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(self, text))
    else:
        self.status.setAccessibleName(text)
        QAccessible.updateAccessibility(
            QAccessibleEvent(self.status, QAccessible.Event.Alert))
```

Announced (and only these — enough to follow a run, not a monologue):

| When | Text |
| --- | --- |
| `STEP_BEGIN` | `"<label>, step <i> of <n>"` |
| `STEP_END` | `"<task title>: <badge>"` |
| `_show_warning` | `"Warning: <text>"` |
| `on_finished` (run) | the summary line already set on `self.status` |
| `on_finished` (check) | the "N update(s) available" / "up to date" line |

### 3. Text that scales

`build_theme` gains two keyword arguments and derives every font size from the
**desktop's own default point size**, so OneUp follows the system font setting for
free and the in-app control multiplies on top of it:

```python
def build_theme(dark: bool, scale: float = 1.0, high_contrast: bool = False) -> str:
```

```python
base = QFontInfo(QApplication.font()).pointSizeF() or 10.0   # QFontInfo resolves a
                                                             # pixel-specified font
```

Four derived sizes replace the eleven hard-coded pixel values, keeping today's
relative hierarchy (ratios taken against a 10 pt / ≈13.3 px default, so
`scale=1.0` reproduces the current look):

| Key | Multiplier | Replaces |
| --- | --- | --- |
| `fs_header` | `1.60` | `21px` (Header) |
| `fs_med` | `1.05` | `14px` (TaskName, RunBtn) |
| `fs_body` | `0.90` | `12px` (Tagline, TaskDesc, Status, LastRun, ProgressBar, SizeResult) |
| `fs_small` | `0.85` | `11px` (Badge, DetailList, Log) |

Emitted as `f"{base * mult * scale:.1f}pt"`. Fractional `pt` in a Qt stylesheet is
verified to work (`font-size: 14.5pt` → `QFont.pointSizeF() == 14.5`).

**Text size** is a three-state cycling `#GhostBtn` in Settings, matching the
existing toggle-button idiom (`auto_btn`, `tray_btn`, …) rather than introducing a
combo box the QSS doesn't style:

```python
TEXT_SCALES = [("Normal", 1.0), ("Large", 1.2), ("Larger", 1.45)]
```

Persisted as `text_scale` in the existing `QSettings("OneUp", "OneUp")`.

*No clipping risk at `Larger`:* the only fixed geometry is `ToggleSwitch`'s
56×30 (it holds no text — `updater.py:365`); `run_btn`'s 44 px and the log's 180 px
are **minimums** (`1126`, `1218`), and the detail list's `setMaximumHeight(180)`
(`474`) is a scroll area that already scrolls.

### 4. High contrast — an overlay, not a third palette

The HC option appends a small override stylesheet **after** the base sheet. Qt
resolves equal-specificity conflicts the way CSS does — the later rule wins
(verified: two `QLabel#T { font-size }` rules, the second took effect) — so the
overlay redefines only the ~15 rules that need it and the two existing palettes
stay untouched.

The overlay: pure black/white surfaces, `#000`/`#fff` text, **solid** button and
banner fills replacing the gradients and translucent washes, 2 px solid borders in
place of the 1 px translucent ones, and a stronger focus ring. Its colours come
from `_HC_DARK` / `_HC_LIGHT`, so HC composes with the light/dark switch instead
of replacing it. Persisted as `high_contrast` in `QSettings`.

`ToggleSwitch` is painted in code, so the stylesheet cannot reach it. It exposes a
`highContrast` Qt property that the sheet sets — the mechanism the class already
uses for `knobPos` (`updater.py:386`):

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

- QSS `:focus` rules for `#RunBtn`, `#GhostBtn`, `#LinkBtn`, `#BannerBtn`,
  `#RestartBtn`, `#Disclose` — a 2 px accent outline (HC overlay: 3 px, palette
  `hcfocus`).
- `ToggleSwitch.paintEvent` draws a **double** ring (white outer, dark inner) when
  `hasFocus()`, so it reads against both the green and the red track. Verified:
  `QAbstractButton` already has `Qt.StrongFocus` (11), so the switch is tab-
  reachable today — only the indicator was missing.

### 6. Tab order

`setTabOrder` after the header row is laid out, fixing the visual/tab mismatch:
`settings_btn → repos_btn → recenter_btn → about_btn → (first task switch)`, and
`check_btn → run_btn` in the action row.

### 7. Colour never alone

| Cue | Pairing added |
| --- | --- |
| Switch on/off | A shape drawn opposite the knob: a **vertical bar** when on, an **open circle** when off (the iOS convention). Drawn with `QPainter` primitives, not a font glyph, so it cannot fall back to a missing character. |
| Tray attention badge | A white `!` drawn inside the amber disc, so the attention icon differs in *shape*, not just colour. |
| Overdue last-run line | The text itself gains a `⚠` prefix and an `overdue` word, matching the banner idiom (`_show_warning` `1282`). |

## Correctness invariants (the tests lock these in)

- **INV-1** Every focusable widget in the main window and in `RepoManagerDialog`
  reports a non-empty accessible name **or** non-empty visible text.
  *Test:* walk `findChildren(QWidget)`, filter `focusPolicy() != NoFocus`, assert
  `accessibleName() or text()`.
- **INV-2** No state is conveyed by colour alone: `ToggleSwitch` paints a
  state shape, the attention tray icon differs from the plain one pixel-wise, and
  a stale last-run line contains the word `overdue`.
  *Test:* the two tray pixmaps differ; `refresh_last_run` with a 20-day-old
  history yields `"overdue" in text`; `ToggleSwitch` paints differently checked
  vs unchecked when rendered to a `QImage` with colour channels equalised.
- **INV-3** The stylesheet contains **no** absolute `font-size: …px` declaration,
  and every font size scales with `scale`.
  *Test:* `"px" not in` any `font-size` line of `build_theme(...)`; the `pt`
  numbers for `scale=1.45` are strictly larger than for `scale=1.0`.
- **INV-4** Every styled focusable control has a focus rule: `build_theme` output
  contains a `:focus` selector for each of the six object names above.
- **INV-5** Tab order matches visual order in the header and action rows.
  *Test:* `nextInFocusChain` walk from `settings_btn` reaches `repos_btn` before
  `recenter_btn`.
- **INV-6** High contrast changes appearance only. The overlay is appended after
  the base sheet, `build_theme(hc=True)` is a strict superset of the base
  (`base in result`), and it sets `qproperty-highContrast: true` while the base
  sets `false`.
- **INV-7** Progress and outcome are announced: `_last_announcement` is non-empty
  and names the step after `STEP_BEGIN`, the outcome after `STEP_END`, and the
  summary after `on_finished`; `_announce` never throws when `QAccessible` is
  inactive (the headless case).
- **INV-8** The two accessibility settings persist and apply live: writing
  `text_scale` / `high_contrast` and calling `apply_app_theme(app)` changes the
  installed stylesheet with no restart and no window rebuild.

## Tests (`tests/gui-smoke.py`)

A new section, in the existing `check(name, cond)` style; no engine test changes
(`tests/run-tests.sh` is untouched — this feature adds no marker and no engine
flag).

1. INV-1 sweep over the main window, then over `RepoManagerDialog` built from two
   stub repo dicts.
2. `build_theme` assertions: INV-3, INV-4, INV-6 (including the `qproperty`
   pair).
3. Marker-driven announcements: feed `STEP_BEGIN` / `STEP_END`, then
   `on_finished`, asserting `_last_announcement` after each (INV-7).
4. `_tray_icon(True)` vs `_tray_icon(False)` pixmaps differ (INV-2).
5. A 20-day-old `history.json` → last-run text contains `overdue` (INV-2). The
   test already redirects `HOME`/`XDG_STATE_HOME` into a sandbox
   (`tests/gui-smoke.py:29-31`), so writing one is safe.
6. Tab-order walk (INV-5).
7. `apply_app_theme` round-trip with both settings (INV-8).

## Docs & release

- `README.md` — a short **Accessibility** section: Orca support, the two Settings
  controls, and the fact that OneUp follows the desktop font size.
- `CLAUDE.md` — one line under "Conventions specific to this repo": new
  interactive widgets need an accessible name, and state must never be
  colour-only.
- `CHANGELOG.md` — `### Added` entry under `[Unreleased]`.
- No version bump in this change (release tooling handles the six lockstep sites).

## Out of scope (deliberate)

- **Extra keyboard shortcuts** (e.g. `Ctrl+R` to run). Every control is already
  keyboard-reachable via Tab once INV-4/INV-5 land; inventing accelerators risks
  clashing with the desktop's own and adds surface with no accessibility gain.
- **Themes beyond light/dark/high-contrast** — that is ONEUP-0027, which must
  keep WCAG-AA contrast for any theme it adds.
- **A live Orca audit pass.** This spec cannot assert the result of a manual
  screen-reader session; the roadmap bullet's "audit pass with Orca" stays open as
  a follow-up verification task, and the automated INV-1/INV-7 checks are what CI
  can enforce.
- **Engine (`update_system.sh`) changes.** The engine's output is already plain
  text; nothing about it is visual.
