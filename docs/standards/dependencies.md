# Dependency Policy & Known-Incompatibility Ledger

**In one sentence:** everything OneUp depends on runs at its latest stable version unless a
newer one demonstrably breaks us, and when that happens the breakage is written down with a
cue to re-test — so nobody has to remember why a version is old.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0004
**Branch:** v2
**Verified at:** `3aa4357` — the snapshot and the *How to check* commands below were re-run
against this tree on 2026-10-01, not recalled.

**Standing rule for OneUp.** Every dependency — CI actions, language runtimes, base
images, and Python packages — tracks the **latest stable version**, for security fixes as
much as for features. Staying current is the default; falling behind needs a reason.

## The rule

1. **Latest by default.** When adding or touching a dependency, use the newest stable
   release. On any release cycle (and whenever you edit a manifest/workflow for another
   reason), check what's behind and bump it.
2. **An older pin is allowed only when a newer version explicitly breaks something we rely
   on, or would drop a platform we deliberately support** — and there is genuinely no other
   way. A preference for a version you remember is not a reason.
   - **A security advisory against the pinned version ends the exemption.** If the version
     we are held back on has a known vulnerability, we move — and if the newer version
     genuinely breaks a feature, the feature gives way, not the security fix. Record what
     broke and why we accepted it; never sit on a vulnerable pin because the alternative is
     inconvenient.
3. **Every older pin must be documented in the ledger below**, with:
   - *what* is pinned and to which version,
   - *why* (the exact feature that breaks and how it manifests, or the platform a newer
     version drops),
   - the *first broken version*,
   - *when to re-test* (so a version newer than the broken one triggers a re-check).
4. **Re-test on the ledger's cue.** When a version newer than a recorded "first broken"
   version ships, re-test the feature. If it works, bump and delete the ledger row. The
   ledger is a to-do list, not an archive — a pin whose reason no longer holds gets removed.
5. **A bump updates the calling code in the same change** (idiom refresh), so the codebase
   doesn't rot into "compiles but nobody meant it." A Python runtime bump is the exception:
   the code's idioms follow the floor in `docs/standards/coding.md` §1, not the CI version.
6. **A CI action is pinned to a full commit SHA**, with the release it resolves to as a
   trailing `# vX.Y.Z` comment (ONEUP-0137). A bump changes both, and the SHA comes from the
   command under *How to check what's behind*.

## Known-incompatibility ledger

Pins that are **behind latest on purpose**. Empty rows mean "nothing is knowingly held
back." Add a row only for a *deliberate* older pin; a merely-not-yet-bumped dependency is a
backlog item, not a ledger entry.

| Dependency | Pinned to | Latest available | First broken version | Why held back | Re-test when |
|---|---|---|---|---|---|
| GitHub runner image (`runs-on`) | `ubuntu-22.04` | `ubuntu-24.04`+ | — (not a break) | **Compatibility floor.** The AppImage is built on an older glibc so it runs on older openSUSE/other distros; a newer runner would raise the minimum glibc and shrink the audience. | Only if we drop the "runs on old glibc" goal, or AppImage tooling changes the target. |

*Rows removed from this ledger, and why: `docs/history/dependencies.md`.*

## Current dependency snapshot (verified 2026-07-26; re-checked 2026-08-19, 2026-08-31 and 2026-10-01)

Recorded so the next sweep has a baseline:

- `actions/checkout` → **`3d3c42e5aac5ba805825da76410c181273ba90b1`** (`v7.0.1`) — current.
- `actions/setup-python` → **`5fda3b95a4ea91299a34e894583c3862153e4b97`** (`v7.0.0`) — current.
- `softprops/action-gh-release` → **`efb35369e0ad2afab669f228072c1b0d510eae64`** (`v3.0.3`) — current.

**Why a SHA (rule 6).** A major tag is mutable — its publisher can repoint
`v7` at any commit — so the tag says which release we *asked* for and not which
code runs. `zizmor` reports the tag form as `unpinned-uses`, High. The `# vX.Y.Z`
comment is **what the sweep below compares against**; the SHA itself is not a version and
cannot be read as one. Verified at the pin: every one of the three major tags
resolved to exactly the SHA recorded here, so pinning changed no behaviour.

This is **not** a ledger entry. Nothing is held back — each pin is the latest
release, spelled immutably. Rule 2's "older pin" test asks which release you are
on, and the answer is unchanged.

- `python-version` in `.github/workflows/release.yml` → **`3.14`** on `v2`, **`3.13`** on
  `main`. Bumped on `v2` as ONEUP-0004 on 2026-08-19, the 2.0 dependency refresh. `main`
  is frozen and takes only qualifying bug fixes, so it keeps 3.13 until the 2.0.0 merge —
  which is why this row names a branch where the others do not. Re-verified at the bump
  rather than recalled: 3.14 is the current stable series (3.14.7, EOL 2030-10-31), and
  PySide6 6.11.2 still ships `cp310-abi3` wheels at `requires_python <3.15,>=3.10`, so
  the 2026-07-26 sweep (`docs/history/dependencies.md`) still holds. The three action pins above were re-checked the same day
  and are all still current.
- **PySide6** → **`6.11.2`** and **PyInstaller** → **`6.22.3`** in the AppImage build — current
  (2026-10-01). `packaging/appimage/requirements.txt` pins the whole resolved set, so a
  rebuild of a release bundles the toolkit it shipped with (ONEUP-0060). Like the action
  pins, this is not a ledger entry: nothing is held back. The RPM takes the distro's
  `python3-pyside6` and pins nothing. Requires only Qt 6 idioms (new-style `connect`, scoped
  enums where practical).
- `zypper`, `flatpak`, `fwupd`, `snapper` — host tools, versioned by the user's openSUSE
  install; OneUp calls stable CLI surfaces.

## How to check what's behind

```bash
# CI actions — latest release tag. Compare each against the `# vX.Y.Z` comment
# beside its pin in .github/workflows/release.yml, never against the SHA.
for r in actions/checkout actions/setup-python softprops/action-gh-release; do
  echo "$r -> $(gh api repos/$r/releases/latest -q .tag_name)"
done
# …and the SHA a tag resolves to, when bumping a pin:
#   gh api repos/<owner>/<repo>/commits/<tag> -q .sha
# Python runtime — latest stable release; compare with python-version in release.yml:
curl -s https://endoflife.date/api/python.json | python3 -c 'import json,sys; print("python ->", json.load(sys.stdin)[0]["latest"])'
# AppImage build packages — latest on PyPI; compare with packaging/appimage/requirements.txt,
# and on a bump replace the whole set with the resolution that file's header names:
python3 -m pip index versions PySide6 | head -1; python3 -m pip index versions pyinstaller | head -1
# Host packages (openSUSE):
zypper search -s --provides --match-exact python3-pyside6
```

## What checks this

| Rule | What catches a breach |
| --- | --- |
| use the latest stable release | nothing automatic — the sweep under *How to check what's behind* is run by hand |
| a pin older than latest carries a written reason | nothing automatic |
| a security advisory against a held pin ends its exemption | nothing automatic |
| a CI action is pinned to a full commit SHA | nothing automatic — `zizmor` reports the tag form as `unpinned-uses`, and nothing runs it |
| a bump updates the calling code in the same change | nothing automatic |
| the ledger records each known incompatibility | nothing automatic |

**Nothing here is gated.** *"Is this the latest version?"* can only be answered by a
network call, which `docs/standards/testing.md` §2.3 allows only in an opt-in scenario,
and no scenario checks versions. The catcher is the sweep, and a sweep is a habit, not a
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
| 7 | 2026-10-01 | Packet build, then 2 lanes, cold, dispatched from outside the project; genre pinned standard; every lane held every question. Q1 3 · Q2 1 · Q3 1 — 5 verified, 0 dismissed, all 5 fixed: 2 found building the packet (`6a079a0`, `df43168`), 3 by the lanes | **A pure audit (ONEUP-0107): no change armed it, so there is no armed-span share.** The four-question gate's first read of this document. **Packet**: the host-package check `zypper info python3-pyside6` finds nothing — it is a capability, not a package name [Q1]; the tag-to-SHA command returns the tag object for an annotated tag, not the pinned commit [Q1, v2 only]. **Lanes**: rule 2 allowed an older pin only for a breakage while the runner row is a compatibility floor [Q2, both lanes]; What-checks said no suite makes a network call, where `testing.md` §2.3 carves out one opt-in scenario [Q1, both lanes]; the sweep named as the only catcher never checked the Python runtime [Q3]. Four open questions resolved clean. Per the user's document rules, the dated history moved to `docs/history/dependencies.md`; that move cut the host-tools bullet, caught on re-read and restored (`100e7e4`) |
| 8 | 2026-10-01 | 2 lanes, cold, briefed exactly as loop 7; every lane held every question. Q2 1 · Q3 2 — 3 verified, 0 dismissed, all 3 fixed | **[Q2], pre-existing**: rule 5 had every bump update the calling code, while `coding.md` §1 lets CI run a newer Python than the code may require; rule 5 now names the runtime bump as the exception. **[Q3]**: SHA pinning was described but was no rule and had no What-checks row — rule 6 states it, v2 only, and the row says nothing runs `zizmor`. **[Q3]**: rule 2's advisory clause had no What-checks row. Own-fix share: 0 of 3. Four open questions resolved clean |
| 9 | 2026-10-01 | 2 lanes, cold, briefed exactly as loop 8 plus one packet fact (nothing runs `zizmor`); every lane held every question. None — 0 verified, 0 dismissed | **Converged**: both lanes returned no findings, on the third loop of the run (the cap for a standard, reached empty). Two true-but-immaterial notes from both lanes, corrected by deletion or a date: the host-tools line no longer says `zypper` is skipped when absent (the RPM requires it), and the snapshot heading now carries 2026-10-01 |
