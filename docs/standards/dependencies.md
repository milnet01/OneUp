# Dependency Policy & Known-Incompatibility Ledger

**In one sentence:** everything OneUp depends on runs at its latest stable version unless a
newer one demonstrably breaks us, and when that happens the breakage is written down with a
cue to re-test — so nobody has to remember why a version is old.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0004
**Branch:** main
**Verified at:** `58ea3bc` — the snapshot below was checked on 2026-07-26, not recalled.

**Standing rule for OneUp.** Every dependency — CI actions, language runtimes, base
images, and Python packages — tracks the **latest stable version**, for security fixes as
much as for features. Staying current is the default; falling behind needs a reason.

## The rule

1. **Latest by default.** When adding or touching a dependency, use the newest stable
   release. On any release cycle (and whenever you edit a manifest/workflow for another
   reason), check what's behind and bump it.
2. **An older pin is allowed only when a newer version explicitly breaks something we rely
   on** — and there is genuinely no other way. A preference for a version you remember is
   not a reason.
   - **A security advisory against the pinned version ends the exemption.** If the version
     we are held back on has a known vulnerability, we move — and if the newer version
     genuinely breaks a feature, the feature gives way, not the security fix. Record what
     broke and why we accepted it; never sit on a vulnerable pin because the alternative is
     inconvenient.
3. **Every older pin must be documented in the ledger below**, with:
   - *what* is pinned and to which version,
   - *why* (the exact feature that breaks and how it manifests),
   - the *first broken version*,
   - *when to re-test* (so a version newer than the broken one triggers a re-check).
4. **Re-test on the ledger's cue.** When a version newer than a recorded "first broken"
   version ships, re-test the feature. If it works, bump and delete the ledger row. The
   ledger is a to-do list, not an archive — a pin with no live breakage gets removed.
5. **A bump updates the calling code in the same change** (idiom refresh), so the codebase
   doesn't rot into "compiles but nobody meant it."

## Known-incompatibility ledger

Pins that are **behind latest on purpose**. Empty rows mean "nothing is knowingly held
back." Add a row only for a *deliberate* older pin; a merely-not-yet-bumped dependency is a
backlog item, not a ledger entry.

| Dependency | Pinned to | Latest available | First broken version | Why held back | Re-test when |
|---|---|---|---|---|---|
| GitHub runner image (`runs-on`) | `ubuntu-22.04` | `ubuntu-24.04`+ | — (not a break) | **Compatibility floor, not a breakage.** The AppImage is built on an older glibc so it runs on older openSUSE/other distros; a newer runner would raise the minimum glibc and shrink the audience. | Only if we drop the "runs on old glibc" goal, or AppImage tooling changes the target. |

*The `python-version` row was removed on 2026-07-26 — see the sweep below. It recorded a
suspected breakage that turned out not to exist, so by rule 4 it had no business in the
ledger.*

## Current dependency snapshot (verified 2026-07-26; re-checked 2026-08-19 and 2026-08-31)

Recorded so the next sweep has a baseline:

- `actions/checkout` → **`3d3c42e5aac5ba805825da76410c181273ba90b1`** (`v7.0.1`) — current.
- `actions/setup-python` → **`5fda3b95a4ea91299a34e894583c3862153e4b97`** (`v7.0.0`) — current.
- `softprops/action-gh-release` → **`efb35369e0ad2afab669f228072c1b0d510eae64`** (`v3.0.3`) — current.

**The three actions are pinned to a commit SHA rather than a major tag, since
2026-08-31 (ONEUP-0137).** A major tag is mutable — its publisher can repoint
`v7` at any commit — so the tag says which release we *asked* for and not which
code runs. `zizmor` reports the tag form as `unpinned-uses`, High. Each `uses:`
line carries the version as a trailing `# vX.Y.Z` comment, and **that comment is
what the sweep below compares against**; the SHA itself is not a version and
cannot be read as one. Verified at the pin: every one of the three major tags
resolved to exactly the SHA recorded here, so pinning changed no behaviour.

This is **not** a ledger entry. Nothing is held back — each pin is the latest
release, spelled immutably. Rule 2's "older pin" test asks which release you are
on, and the answer is unchanged.

*The `v3.0.2` recorded on 2026-08-19 was superseded by `v3.0.3` upstream. The
`@v3` tag had already moved, so the workflow had been running `v3.0.3` since it
published — the figure was stale, not the pin.*
- `python-version` in `.github/workflows/release.yml` → **`3.14`** on `v2`, **`3.13`** on
  `main`. Bumped on `v2` as ONEUP-0004 on 2026-08-19, the 2.0 dependency refresh. `main`
  is frozen and takes only qualifying bug fixes, so it keeps 3.13 until the 2.0.0 merge —
  which is why this row names a branch where the others do not. Re-verified at the bump
  rather than recalled: 3.14 is the current stable series (3.14.7, EOL 2030-10-31), and
  PySide6 6.11.2 still ships `cp310-abi3` wheels at `requires_python <3.15,>=3.10`, so
  the sweep below still holds. The three action pins above were re-checked the same day
  and are all still current.
- **PySide6** — intentionally *unpinned*: the RPM uses the distro's `python3-pyside6`, and the
  AppImage build `pip install`s the latest. It tracks upstream automatically; no manifest pin
  to bump. Requires only Qt 6 idioms (new-style `connect`, scoped enums where practical).

### Sweep, 2026-07-26 — why the Python row died

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
- `zypper`, `flatpak`, `fwupd`, `snapper` — host tools, versioned by the user's openSUSE
  install; OneUp calls stable CLI surfaces and skips cleanly when a tool is absent.

## How to check what's behind

```bash
# CI actions — latest release tag. Compare each against the `# vX.Y.Z` comment
# beside its pin in .github/workflows/release.yml, never against the SHA.
for r in actions/checkout actions/setup-python softprops/action-gh-release; do
  echo "$r -> $(gh api repos/$r/releases/latest -q .tag_name)"
done
# …and the SHA a tag resolves to, when bumping a pin:
#   gh api repos/<owner>/<repo>/git/ref/tags/<tag> -q .object.sha
# Host packages (openSUSE):
zypper info python3-pyside6 | grep -i version
```

## What checks this

| Rule | What catches a breach |
| --- | --- |
| use the latest stable release | nothing automatic — the sweep under *How to check what's behind* is run by hand |
| a pin older than latest carries a written reason | nothing automatic |
| a bump updates the calling code in the same change | nothing automatic |
| the ledger records each known incompatibility | nothing automatic |

**Nothing here is gated, and that is structural rather than neglect.** *"Is this the latest
version?"* can only be answered by a network call, and no suite in this project makes one
(`docs/standards/testing.md` §2.3). The catcher is the sweep, and a sweep is a habit, not a
gate — so the honest reading of a green `local-CI.sh` is that it says nothing whatever about
whether these dependencies are current.

## Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: it carried neither the Status header block nor the one-sentence opener that `docs/standards/documentation.md` §3 and §8.2 require of every standard |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged. Nothing from loop 1 resurfaced in this lane, which is the proof those fixes held. The two findings that verified are logged against `files-and-naming.md` and `workflow.md` |
| 3 | 2026-07-26 | none | clean. |
| 4 | 2026-07-26 | none | clean. |
| 5 | 2026-07-26 | none | clean. |
| 6 | 2026-07-26 | none | converged. |
