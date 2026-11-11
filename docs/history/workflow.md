# Workflow standard — history

Sections moved out of `docs/standards/workflow.md`, which states the rules. Nothing here is
a rule.

## 2026-11-11 — the v1 freeze and the 2.0 branch tree, retired with `v2`

2.0.0 was released on 2026-11-06. On 2026-11-11 `main` held every commit `v2` had, and `v2`
was deleted. The two sections below were moved verbatim; their section references point at
the standard as it stood then.

### 1. The v1 freeze

**`main` is frozen at 1.4.0.** This is the single most important thing in this document,
because it decides where *every* change goes.

*This section is canonical for the rule.* `docs/design/oneup-2.0.md` §5.4 carries the
programme framing — why the freeze exists and what it costs — and defers here for the test.

1.4.0 was released first on purpose. `CHANGELOG.md`'s `## [1.4.0]` section is what it
carried; `docs/design/oneup-2.0.md` §5.4 is why it went out before the freeze rather than
after it.

#### 1.1 What still qualifies for `main`

The user's definition, 2026-07-26:

> If people can no longer use OneUp to install system updates, Flatpak updates or firmware
> updates, we fix it and ship a 1.4.x.

Two readings live **inside** that definition. They are written down so nobody re-argues
them later:

- **A silent wrong answer is a failure to do the job.** ONEUP-0056 is the precedent: OneUp
  said "Everything is up to date" while eight updates waited. Nothing got updated and
  nobody knew — the same outcome as a crash, only quieter.
- **Leaving the machine damaged is worse than not doing the job.** A half-applied rpm
  transaction, or an abandoned lock that blocks the *next* run, means updating is now
  actively broken.

One likely trigger is worth naming because it is not a bug in OneUp at all: **openSUSE can
break OneUp from underneath it.** The engine reads zypper's output, and zypper's wording is
not a promised interface — ONEUP-0046 exists precisely because it can change. If a zypper
update blinds 1.x, that qualifies and ships as a 1.4.x.

**Widened by the user 2026-08-18, and this reading now governs:**

> This is a fix, so we can still update the v1 code to fix any issue. If it were a feature
> request, that goes in v2.

**So the test is the change's KIND, not its severity.** A fix lands on `main` whether or not
it blocks installing updates; a feature request waits for 2.0 however small it looks. The
2026-07-26 definition above is not withdrawn — it still explains *why* the freeze exists and
it still settles the hard cases it was written for — but it is no longer the bar a fix has
to clear.

**The precedent is ONEUP-0110.** The *Restart services* button did nothing at all, and under
the 2026-07-26 definition alone it did not qualify: system, Flatpak and firmware updates all
installed correctly. It was raised as not qualifying and the user ruled otherwise, which is
what produced the wording above. ONEUP-0111 followed it on the same ground.

**What has not changed:** a feature request is still 2.0's, and *"it is only a small
feature"* is not an argument. `docs/design/oneup-2.0.md` §5.4 carries the programme framing
and defers here for the test.

#### 1.2 What does not

Every **feature request** — a missing convenience, a nice idea, a redesign — waits for 2.0,
however small it looks. **No feature work lands on `main` during the freeze.** A *defect* is
not on this list: §1.1's test is the change's kind, so a misplaced dialog or awkward wording
is a fix and lands on `main` — except a defect in `tests/` or the push gate, which is one
only where the exceptions below grant it (§9). **Work that is neither — a missing test scenario, a refactor,
a dependency bump — waits for 2.0 with the features**, which is why ONEUP-0070 lands on
`v2` below: `main` is open to a fix, not to everything that is not a feature.

These are not feature work and are unaffected:

- **Documentation.** It is not a release. This whole standards set lands on `main` normally,
  because the rules govern 1.x maintenance too and `v2` inherits them by merge (design §5.3).
- **One named, behaviour-neutral test-harness change**, granted 2026-07-27 at the user's
  decision: the
  `ONEUP_ENGINE_CMD` indirection that lets the suite drive either engine
  (`docs/specs/ONEUP-0054-python-engine.md` §4.4). Its justification is that the suite must
  be *seen* to stay green on `main` before anything on `v2` depends on it.

  **This exception names a change; it does not describe a category.** Touching only files
  under `tests/` is a *necessary* condition, not a sufficient one — the absent-tool scenario
  ONEUP-0070 owes is also tests-only, and it lands on `v2` like everything else. Written here,
  in the standard that owns the freeze, precisely so that each one is granted rather than
  inferred: the ones below were decisions taken with the user, in this section, and neither
  was drawn as a precedent from this one.

- **The test-suite fixes from the 2026-08-03 `/test-audit` sweep** — the second exception,
  granted that day at the user's decision, by the route the paragraph above requires. The
  sweep found defects in the suites themselves: a documentation check that could fail a
  correctly-formed row, an unmocked `df` letting the real machine's free space reach every
  system-step scenario, and assertions weaker than the claims they carried. The user's
  words: *"You can fix main, it just means we have to publish a new release for v1."* So
  these land on `main` and owe a 1.4.x.

  Same caveat, restated because it is the whole point: this names a batch of changes, not a
  category. It does not make `tests/` generally open, and ONEUP-0070 still lands on `v2`.

- **ONEUP-0097, the pre-push hook's inherited network opt-in** — the third exception,
  granted 2026-08-07 at the user's decision, by the same route. `githooks/pre-push` runs
  `local-CI.sh`, which opted into ONEUP-0094's live CDN check, so a push was gated on a
  third party's server being up — while four documents stated the hook declined it. The fix
  is two lines: `local-CI.sh` honours `ONEUP_TEST_NETWORK` instead of forcing it, and the
  hook passes 0.

  **What made this one qualify is not that it is small.** It is that the *push gate itself*
  was unreliable for a reason outside the project, and a gate that fails on somebody else's
  outage teaches people to reach for `--no-verify` — which disarms every other gate too
  (§6.1). Nothing user-facing changed, so **no 1.4.x is owed**, unlike the second exception.

  Same caveat, third time: a batch of changes, not a category. `tests/` is still not
  generally open and ONEUP-0070 still lands on `v2`.

- **ONEUP-0216, the pre-push hook's secret scan and pushed-commit gate** — the fourth
  exception, granted 2026-10-01 at the user's decision. The machine-wide `local-gate.md`
  standard (§2.1) requires a project's own hook to scan the pushed commits for secrets and
  to gate those commits rather than the working tree; `githooks/pre-push` did neither. It
  qualifies for the ONEUP-0097 reason: the hook runs from whichever branch is checked out,
  so a fix on `v2` alone leaves every push made from `main` unscanned. Nothing user-facing
  changed, so **no 1.4.x is owed**. A batch of changes, not a category.

- **ONEUP-0224, the window suite's mock `sudo`** — the fifth exception, granted 2026-10-01
  at the user's decision. `tests/gui-smoke.py`'s download-size scenario launched the real
  engine, whose real `sudo` opened a password dialog on the desktop on every run, push gates
  included: §2 of `testing.md`, broken by the suite itself. It qualifies for the ONEUP-0097
  reason, since `main`'s gate runs this suite on every push of `main`. Nothing user-facing
  changed, so **no 1.4.x is owed**. A batch of changes, not a category.

- **ONEUP-0203, two gate runs at once** — the sixth exception, granted 2026-10-07 at the
  user's decision. `local-CI.sh` wrote every suite's log to a fixed `/tmp/local-ci-*` name
  that any gate run on the machine shared. The engine suite's keep-alive leak check counted
  every keep-alive on the machine, so another run's read as this run's leak and was killed.
  Two runs side by side failed that way (measured 2026-10-02). It qualifies for the
  ONEUP-0097 reason, since `main`'s gate runs both on every push of `main`. Nothing
  user-facing changed, so **no 1.4.x is owed**. A batch of changes, not a category.

- **ONEUP-0200, the refresh-budget grant check** — the seventh exception, granted
  2026-10-13 at the user's decision, after it had landed on `main` without one. The engine
  suite's check that a non-numeric `ONEUP_REFRESH_TIMEOUT` blocks a passwordless grant ran
  under mocks that failed every grant, so it could not fail. It qualifies for the
  ONEUP-0097 reason, since `main`'s gate runs that suite on every push of `main`. Nothing
  user-facing changed, so **no 1.4.x is owed**. A batch of changes, not a category.

- **ONEUP-0273, the OBS package's move to `home:milnet:oneup`** — the eighth exception,
  granted 2026-10-13 at the user's decision. It is neither a fix nor a feature, so on its
  own it would wait for 2.0. It qualifies because `main`'s `release.sh` publishes every
  1.4.x, so a move on `v2` alone would leave 1.4.x releases going to the old location. It
  also removes the GitHub → OBS webhook and its OBS workflow file (ONEUP-0255). No 1.4.x
  is owed for it. A batch of changes, not a category.

- **ONEUP-0129 and ONEUP-0126, two docs- and engine-suite checks** — the ninth and tenth
  exceptions, granted 2026-10-14 at the user's decision. ONEUP-0129 makes
  `tests/docs-check.py` walk `docs/plans/`, which `main` holds as well as `v2`. ONEUP-0126
  pins each marker's field layout in the engine suite, so a field added to one marker
  fails the suite. Both qualify for the ONEUP-0097 reason: `main`'s gate runs them on every
  push of `main`. Nothing user-facing changes, so **no 1.4.x is owed**. Two named changes,
  not a category.

- **The regression tests for ONEUP-0275, ONEUP-0276, ONEUP-0277 and ONEUP-0093** — the
  eleventh exception, granted 2026-10-14 at the user's decision. The four fixes are defects
  and land on `main` by §1.1; what needs the grant is their tests in `tests/run-tests.sh`
  and `tests/gui-smoke.py`, each proven red on the unfixed code. ONEUP-0093's changes a
  window check that had asserted the defect. The fixes owe a 1.4.x; the tests add nothing to
  it. Four named changes, not a category.

- **The regression tests for ONEUP-0341 to ONEUP-0346, and the ONEUP-0348 test fix** — the
  twelfth exception, granted 2026-10-29 at the user's decision. The six fixes came from PR #1
  and land on `main` by §1.1, as does ONEUP-0347's; what needs the grant is their tests in
  `tests/run-tests.sh` and `tests/gui-smoke.py`, and ONEUP-0348, a defect in a
  `tests/run-tests.sh` failure message. The fixes owe a 1.4.x; the tests add nothing to it.
  Named changes, not a category.

- **The ONEUP-0349 test fix** — the thirteenth exception, granted 2026-10-29 at the user's
  decision. `tests/gui-smoke.py` hung when the machine's passwordless rule read off, because
  the real startup probe answered during its passwordless block. The fix stubs that probe
  there. It changes no shipped code and adds nothing to a 1.4.x. One named change, not a
  category.

**Why the freeze is stated as a testable question rather than a preference:** the failure
mode of any freeze is a slow slide back into 1.x work, one "small" fix at a time. *Is it a
fix, a feature request, or neither?* has an answer; "is this important enough?" does not.

### 9. Where a 2.0 change goes

While the freeze holds, the decision is short:

```
Is it documentation?
├── does a rule bind it to code that only exists on v2?      → v2 (below)
└── no                                   → main → merge main into v2 (§1.2, §2)
Is it *the* ONEUP_ENGINE_CMD harness
  change — the FIRST exception §1.2 names?  → main first, then v2 (§1.2)
Otherwise — the test is the change's KIND, not its severity (§1.1):
Is it a fix, a feature request, or neither?
├── a fix     → main → 1.4.x if a user would notice it → merge main into
│                v2, however small. A defect in tests/ or the push gate
│                is a fix only where §1.2 grants it, and then owes a
│                1.4.x only where that grant says so; otherwise "neither"
├── a feature → v2         → ships when the whole gate passes (design §7)
└── neither   → v2         → a refactor, a dependency bump, a missing test
                 scenario: main is open to a fix, not to everything that
                 is not a feature (§1.2)
```

**Three things bind documentation to `v2`, and none is a loophole.**

**A marker change made as 2.0 work.** `docs/reference/marker-protocol.md` §5 requires it
to touch the emitter, the window, both suites *and* the reference **in one commit** — that
is what makes the change reviewable at all. That work is 2.0-only, so the reference edit goes
with it, onto `v2`, and reaches `main` at the 2.0.0 merge (design §5.3). A §1.1 fix on
`main` that changes a marker keeps the same one-commit rule on `main`. The reason is not
convenience: `main` still ships the 1.4.0 engine, so a reference amended on `main` would
describe a contract `main`'s own engine does not implement. ONEUP-0072 is the item.

**A document `tests/docs-check.py` checks that must NAME a file 2.0 creates** — a
standard, a reference, `CLAUDE.md` or `README.md`. Its §9
check reads `docs/standards/`, `docs/reference/`, `CLAUDE.md` and `README.md`, and fails a
backticked path that carries **both** a directory separator and a file extension and does
not resolve — deliberately, because
those documents describe the tree as it is today, where a spec or a design document may name
a file it is going to create. So a standard here cannot name a file that exists only on
`v2`, and the edit goes with the code. ONEUP-0034 is the first item: `files-and-naming.md`'s
`tests/` row, §5.1's version sites and `marker-protocol.md`'s pointer at the window's parser
all name package files. **Describing the package's *shape* is unaffected** — a backticked
directory carries no extension and is not checked, which is how `files-and-naming.md` §4
already sits on `main`. A bare *filename* escapes the pattern too, for want of the
separator; that is a gap in the check and not licence to evade it by dropping the
directory.

**A passage whose truth depends on code only `v2` has** — a gate, a test file or a
constant that `v2` added or renamed — even where it names no `v2`-only path. Here there is
no wording true of both branches, so each branch carries its own. `main` keeps the text that
is true of `main`; `v2` corrects its own copy; the two differ by design until the 2.0.0
merge. When `main` is merged into `v2`, keep `v2`'s side of such a passage. Live cases
include §6 of this standard and the `LOG_DIR` passages of `files-and-naming.md`
(ONEUP-0130).

**Documentation goes to `main` unless a rule binds it to code that cannot.** Those three
are the rules that bind it today; a fourth would need naming here before it counted.

**No partial 2.0 releases** — the user's rule, 2026-07-26. `docs/design/oneup-2.0.md` §7
states it and owns what "complete" means.

