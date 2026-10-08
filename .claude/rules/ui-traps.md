---
paths:
  - "updater.py"
  - "oneup/gui/**"
  - "tests/gui-smoke.py"
  - "docs/standards/ui-and-accessibility.md"
---

# Window traps

Moved verbatim from `CLAUDE.md` §6, which keeps a one-line headline for each. Each of
these cost a real bug. They are terse on purpose — the reasoning, the measurement and the
exact shape of the rule are in the document named beside each.

- **The app draws no focus ring — and the cue is DERIVED, not copied from hover.** No ring
  is the user-facing design decision, and it is the half that cost the bug: Qt ignores
  `outline-radius` so a ring draws square around rounded buttons, and a border added on
  focus resizes the widget. It is about focus *highlighting* only — ordinary borders are
  fine. The cue is derived rather than copied for a measured reason, not a preference:
  hover lightens, and pure white measures 2.63:1 against the accent button's top gradient
  stop, so no lighter shade reaches SC 2.4.13's 3:1 there at any saturation. A focused
  control's fill is blended toward black or white until it clears 3:1 against every surface
  it rests on. Copying a `:hover` rule into a `:focus` one lands a cue of about 1.2:1 —
  `docs/standards/ui-and-accessibility.md` §5.
