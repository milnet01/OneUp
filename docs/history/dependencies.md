# Dependency policy — history

Dated records moved out of `docs/standards/dependencies.md`, which states the rules.
Nothing here is a rule.

## 2026-07-26 — the `python-version` row removed

The `python-version` row was removed on 2026-07-26 — see the sweep below. It recorded a
suspected breakage that turned out not to exist, so by rule 4 it had no business in the
ledger.

## 2026-07-26 — the sweep: why the Python row died

The ledger claimed 3.13 was held back pending "PySide6 wheels for 3.14". Checked against
PyPI rather than recalled, and **the premise was wrong**: PySide6 ships **stable-ABI**
wheels, so there is no per-version wheel to wait for.

```
$ curl -s https://pypi.org/pypi/PySide6/6.11.1/json | ... ['urls'] → filename
pyside6-6.11.1-cp310-abi3-manylinux_2_34_x86_64.whl      ← cp310-abi3, not cp313/cp314
requires_python: <3.15,>=3.10
```

`cp310-abi3` installs on **any** CPython from 3.10 up to the `<3.15` ceiling — 3.14
included — and `manylinux_2_34` is satisfied by the `ubuntu-22.04` runner (glibc 2.35). So
nothing was ever broken; the pin was caution with no measurement behind it, which rule 4
says must not sit in the ledger. Removed.

**The lesson, worth more than the bump:** an unverified suspicion written into a ledger
reads exactly like a verified breakage six months later, and nobody re-checks it because
the ledger looks authoritative. A row goes in only when something has been *observed* to
break — a hunch is a backlog item.

## 2026-08-31 — `action-gh-release` was already on `v3.0.3`

The `v3.0.2` recorded on 2026-08-19 was superseded by `v3.0.3` upstream. The `@v3` tag had
already moved, so the workflow had been running `v3.0.3` since it published — the figure
was stale, not the pin.
