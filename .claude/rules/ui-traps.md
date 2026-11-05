---
paths:
  - "updater.py"
  - "tests/gui-smoke.py"
  - "docs/standards/ui-and-accessibility.md"
---

# Window traps

`CLAUDE.md` §6 keeps a one-line headline for each. Each of
these cost a real bug. They are terse on purpose — the reasoning, the measurement and the
exact shape of the rule are in the document named beside each.

- **The app draws no focus ring.** Keyboard focus reuses the hover look. This is a
  user-facing design decision, and it is about focus *highlighting* only — ordinary
  borders are fine. `docs/standards/ui-and-accessibility.md` §5.
