# Dependency Policy & Known-Incompatibility Ledger

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
| `python-version` (release workflow) | `3.13` | `3.14` (verify) | *unverified* | Held one series back pending confirmation that **PySide6 publishes wheels for 3.14**; a build Python without a matching PySide6 wheel fails `pip install` in the AppImage step. This is *unverified caution*, not a confirmed break. | Next release: check PyPI for a PySide6 wheel on 3.14; if present, bump and drop this row. |

## Current dependency snapshot (verified 2026-07-21)

Bumped to latest during the 2026-07-21 audit; recorded so the next sweep has a baseline:

- `actions/checkout` → **v7** (was v4)
- `actions/setup-python` → **v7** (was v5)
- `softprops/action-gh-release` → **v3** (was v2)
- **PySide6** — intentionally *unpinned*: the RPM uses the distro's `python3-pyside6`, and the
  AppImage build `pip install`s the latest. It tracks upstream automatically; no manifest pin
  to bump. Requires only Qt 6 idioms (new-style `connect`, scoped enums where practical).
- `zypper`, `flatpak`, `fwupd`, `snapper` — host tools, versioned by the user's openSUSE
  install; OneUp calls stable CLI surfaces and skips cleanly when a tool is absent.

## How to check what's behind

```bash
# CI actions — latest release tag:
for r in actions/checkout actions/setup-python softprops/action-gh-release; do
  echo "$r -> $(gh api repos/$r/releases/latest -q .tag_name)"
done
# Host packages (openSUSE):
zypper info python3-pyside6 | grep -i version
```
