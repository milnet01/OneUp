# Workflow Standard

**In one sentence:** this is how a change gets from an idea to somebody's computer — which
branch it belongs on, what the commit says, how it earns a version number, and the one
gate it must pass green before it leaves this machine.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `58ea3bc` — every command, path and figure below was run or read against
the tree on 2026-07-26, not recalled.

**Sections:** 1 the v1 freeze · 2 branches · 3 commits · 4 roadmap IDs · 5 versions ·
6 the gate before a push · 7 pushing · 8 releasing · 9 where a 2.0 change goes · 10 traps ·
11 before you push · what checks this · 12 cold-eyes log

## 1. The v1 freeze

**`main` is frozen at 1.4.0.** This is the single most important thing in this document,
because it decides where *every* change goes.

*This section is canonical for the rule.* `docs/design/oneup-2.0.md` §5.4 carries the
programme framing — why the freeze exists and what it costs — and defers here for the test.

1.4.0 was released first on purpose: it carries eight finished improvements — the Stop
button, following a run already in progress, making a slow mirror legible, Wayland dialog
placement, and the false "up to date" fix. The version people sit on for the length of the
2.0 build should be the best one available.

### 1.1 What still qualifies for `main`

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

### 1.2 What does not

Everything else. A misplaced dialog, awkward wording, a missing convenience, a nice idea —
all wait for 2.0. **No feature work lands on `main` during the freeze.**

Documentation is not a release and is unaffected: this whole standards set lands on `main`
normally, because the rules govern 1.x maintenance too and `v2` inherits them by merge
(design §5.3).

**Why the freeze is stated as a testable question rather than a preference:** the failure
mode of any freeze is a slow slide back into 1.x work, one "small" fix at a time. *Can
people still install their updates?* has an answer; "is this important enough?" does not.

## 2. Branches

| Branch | What it is |
| --- | --- |
| `main` | Released 1.x. Frozen (§1). Documentation and qualifying bug fixes only |
| `v2` | The 2.0 programme. Long-lived, shared with `origin`, and **never rebased** |

Rules:

- **`v2` is never rebased and never force-pushed.** It exists on the remote, so rewriting
  its history breaks every clone of it. Merge instead, always.
- **`main` merges *into* `v2`, never the reverse.** After any 1.4.x release, merge `main`
  into `v2` so the branch picks the fix up. Nothing travels the other way until 2.0 ships.
- **Feature branches are optional and short.** If one is used, name it
  `<ONEUP-id>-<topic>` and merge it into `v2` when its item is done. There is no
  requirement to branch for every item — the project has one developer and zero merge
  commits in its history.

**No pull-request gate.** The repository has no `CODEOWNERS`, no branch protection, and
no merge commits; commits land directly on their branch. Reviews happen through
`/cold-eyes` on the documents and `local-CI.sh` on the code, not through GitHub review.

## 3. Commits

**Subject: `<ONEUP-id>: <what changed, in the imperative>`.**

```
ONEUP-0056: never report "up to date" for a source the check couldn't read
```

Exceptions, both real and both narrow:

- **A release commit is `OneUp X.Y.Z`** — the version is the identifier. `release.sh`
  writes it.
- **A commit that closes several items names them all**, slash-separated:
  `ONEUP-0048/0049/0050: make a slow mirror legible; centre dialogs on Wayland`.

**Body: explain *why*, not *what*.** The diff already says what changed. The body is where
the next reader — including you, in six months — finds the reason. When a claim was
measured, put the measurement in the body: it is the only record that it *was* measured.

**Every commit ends with the `Co-Authored-By:` trailer** when Claude wrote it.

**One document or one behaviour per commit.** A commit that settles two unrelated things
cannot be reverted, and cannot be explained in one subject line.

## 4. Roadmap IDs

**Work that is not on the roadmap did not happen.** Every commit subject carries an ID, so
every commit is traceable to a bullet that says why the work was wanted.

IDs are allocated from `.roadmap-counter`, a one-line file holding the last number handed
out. It is **deliberately git-ignored**: tracking it means every branch that allocates an
ID conflicts on the same line. `ROADMAP.md` is the real record.

On a fresh clone the counter is absent, and appending a bullet **refuses** rather than
restarting at 1 — so a collision is impossible, but you must rebuild it first. The
one-liner lives in `.gitignore` alongside the ignore rule:

```bash
grep -oE 'ONEUP-[0-9]+' ROADMAP.md | grep -oE '[0-9]+' \
    | sort -n | tail -1 | sed 's/^0*//' > .roadmap-counter
```

**A bullet's shape** — status emoji, ID, bold headline, body, then the four labelled lines:

```markdown
- 📋 [ONEUP-0065] **Convert the remaining line-number citations to symbol names.**
  <what and why, with the measurement>
  **Layman:** <one sentence a non-programmer can act on>
  Kind: doc-fix.
  Source: <where this came from — a review lane, a user request, a session>
  Resolved (YYYY-MM-DD): <what actually happened, incl. the commit>
```

Status is `📋` planned, `🚧` in progress, `✅` shipped, `💭` considered. **A bullet is
closed by annotating it, never by deleting it** — the resolution note is how a later
reader learns what was actually done, and it is frequently different from what was
planned.

**File a finding at the moment you find it.** A gotcha noticed mid-task and held until
close-out is a gotcha that gets lost. This is why ONEUP-0058 through 0065 exist: each was
filed in the task that surfaced it, not in a tidy-up pass afterwards.

## 5. Versions

**Semantic versioning**, as `CHANGELOG.md` states. For this project concretely:

- **Major** — 2.0.0, because the engine is replaced. A user's mental model of the app does
  not change, but everything underneath it does.
- **Minor** — a new capability inside 1.x (1.3.0 → 1.4.0: the Stop button, run-following).
- **Patch** — a fix that restores stated behaviour. Under the freeze, 1.4.x is *only* ever
  a §1.1 fix.

### 5.1 The six version sites

One version number lives in six places, and they must agree:

| # | Site |
| --- | --- |
| 1 | `APP_VERSION` in `updater.py` — the in-app update check reads it |
| 2 | `Version:` in `packaging/rpm/oneup.spec` |
| 3 | the newest `%changelog` stanza in the same spec — rpmlint rejects a mismatch |
| 4 | `versionformat` **and** `revision` in `packaging/obs/_service` |
| 5 | the newest `<release version="…">` in `data/za.co.antsprojectshub.OneUp.metainfo.xml` |
| 6 | the newest `## [x.y.z]` heading **and its link** at the foot of `CHANGELOG.md` |

`_service`'s `revision` is pinned to the release tag on purpose. Left on `main` it would
repackage post-release commits under the old version number — a build that claims to be
1.4.0 and is not.

**Never hand-edit the six.** `./bump.py X.Y.Z` rewrites all of them, deriving the RPM and
AppStream release notes from the CHANGELOG's `## [Unreleased]` bullets so that section is
the single source of truth. `local-CI.sh`'s version-lockstep gate then reads all six back
and fails if any disagrees.

### 5.2 The CHANGELOG

Keep a Changelog format. Entries are written **as the work lands**, under
`## [Unreleased]`, in the shape `bold summary (ONEUP-id)` followed by a plain-English line:

```markdown
- **Add a Stop button that never interrupts an install half-way.** (ONEUP-0047)
  You can now stop an update. It finishes the step it is on first, so nothing is left
  half-installed.
```

The second line is the one users read. Write it for them, not for the diff.

**Released entries are never rewritten.** They are a record of what people actually
received. An unreleased entry may be edited freely.

An empty `## [Unreleased]` section stops a release: `bump.py` derives the packaging release
notes from it, so there is nothing to derive.

## 6. The gate before a push

**`./local-CI.sh` must be green before every push.** It runs in about a second and covers
more than GitHub CI does:

| Gate | What it proves |
| --- | --- |
| `tests/run-tests.sh` | the engine suite — the markers `update_system.sh` prints |
| `tests/gui-smoke.py` | the offscreen GUI suite — the window's state after being fed those markers (exit 77 = PySide6 absent, a skip) |
| `tests/bump-test.py` | a real bump in a throwaway copy advances every version site |
| Python syntax | `updater.py` and `bump.py` parse |
| lint | `ruff` and `shellcheck`, best-effort |
| packaging validation | desktop file and AppStream metainfo |
| version lockstep | the six sites of §5.1 agree |
| documentation | `check-docs.py` — the rules of `docs/standards/documentation.md` that a script can settle |

Two deliberate design points:

- **A gate whose tool is not installed is reported as skipped, never silently passed.** A
  green run that quietly checked nothing is worse than a red one.
- **The AppImage build is opt-in** (`./local-CI.sh --full`, wrapped in a 10-minute
  timeout). `appimagetool` downloads its runtime from GitHub on every run and can stall on
  a slow or filtered link; GitHub CI builds and verifies the AppImage on every tag push
  anyway, so the local build is a convenience, not a gate.

`githooks/pre-push` runs the fast gates automatically. Enable it once per clone:

```bash
git config core.hooksPath githooks
```

**`--no-verify` is not a way past a red gate.** It exists for the case where the hook
itself is broken. A failing test is fixed, not bypassed.

**The two gate sets are not identical, deliberately.** `release.yml` runs the three test
suites and the AppImage build. `local-CI.sh` runs those three suites **plus** lint,
packaging validation, version lockstep and the documentation check — and those four extras
have never run in GitHub CI.

- **A new *test* gate goes in both.** Otherwise the first thing it catches is caught after
  the tag is already pushed, which is the expensive moment.
- **The four extras stay local**, so understand what that costs: **a lint failure is
  caught before a push or not at all.** The pre-push hook is what makes that reliable, and
  is why `git push --no-verify` is not a way past a red gate (§6).

### 6.1 A gate is how a rule stops being a wish

**When a reviewer or a human catches the same *class* of error twice, it becomes a gate.**
A rule nothing checks is a wish (`docs/standards/documentation.md` §5), and a cold reader is
the scarcest thing in this process — never spend one on what `grep -c` can settle.

Adding a gate:

1. **Add the check to `local-CI.sh`**, using its `ok` / `bad` / `skip` helpers, so a missing
   tool is reported as skipped and never silently passed.
2. **Add a row to §6's table** saying what it proves, in the same words the gate prints.
3. **If it is a *test* gate, add it to `.github/workflows/release.yml` as well** — a test
   gate that runs only locally catches its first regression after the tag is pushed.
4. **Prove it fails.** Break the thing it checks, run it, see red, put the thing back. A gate
   nobody has seen fail is a gate nobody knows works — this is the same rule as
   `docs/standards/testing.md` §4, applied to the gate itself.

**A gate reports, it does not repair.** `check-docs.py` names the file, the line and the
rule, and changes nothing; the author decides what the right text is. A gate that edits prose
would quietly rewrite a claim it does not understand.

## 7. Pushing

**The repository is public** (`milnet01/OneUp`), so Linux runner minutes are free and there
is no reason to batch pushes. Push each commit as it lands, once local CI is green.

The only workflow is `release.yml`, and it triggers on `push: tags: ['v*']` — an ordinary
commit push runs no CI at all. A tag push runs the suite, builds the AppImage and attaches
it to the GitHub release.

## 8. Releasing

`./release.sh X.Y.Z` does the whole thing. `--no-obs` stops after GitHub.

Its preconditions are checks, not suggestions, and it exits on any of them:

1. a clean working tree,
2. on `main`,
3. the tag `vX.Y.Z` does not already exist.

Then, in order: bump the six sites → `./local-CI.sh` → show the diffstat → **ask for
confirmation** → commit `OneUp X.Y.Z`, tag, push → update the OBS package via `osc`.

Three things about that sequence are worth knowing before you run it:

- **It stops and waits for a yes.** A release is not unattended. Answering anything but
  `y` aborts and leaves the bump in your tree; `git checkout -- .` discards it.
- **The clean-tree precondition is what makes its `git add -A` safe.** With a clean tree,
  everything staged is exactly what `bump.py` wrote. Starting from a dirty tree would sweep
  unrelated edits into a release commit — which is why the check comes first and is fatal.
- **The OBS step needs `osc` configured, and degrades rather than failing.** If `osc` is
  missing or the commit fails, it says so and points at `packaging/obs/README.md` for the
  web-UI route. The GitHub release has already happened by then and is unaffected.

**What the user still has to do by hand:** nothing on the GitHub side — CI builds and
publishes. The OBS rebuild is the one step that can need finishing manually.

**Three distribution paths ship each release**, and all three must work: the AppImage (from
the tag workflow), the RPM (`packaging/rpm/oneup.spec`), and the OBS repository users
install from with `zypper`.

## 9. Where a 2.0 change goes

While the freeze holds, the decision is short:

```
Can people still install system, Flatpak and firmware updates?
├── no  → it is a §1.1 fix → main → 1.4.x → merge main into v2
└── yes → it is 2.0 work   → v2   → ships when the whole gate passes (design §7)
```

**No partial 2.0 releases.** No beta cut from the branch mid-way. Users stay on frozen
1.4.0 until 2.0.0 arrives complete — the user's rule, 2026-07-26, recorded in design §7.

## 10. Traps

- **Rebasing `v2`.** It is shared with the remote. The damage is not to your clone.
- **Hand-editing one version site.** Five of the six then disagree; the lockstep gate
  catches it, but only if you run local CI — and the RPM `%changelog` one is the easiest to
  forget, because nothing else references it.
- **Committing `.roadmap-counter`.** It is ignored for a reason. If it ever appears in
  `git status`, something removed the ignore rule.
- **Allocating an ID on a fresh clone without rebuilding the counter.** The append refuses
  — that is the design working, not a bug. Run the one-liner in §4.
- **Releasing with an empty `## [Unreleased]`.** `bump.py` has nothing to derive the
  packaging notes from and stops. Write the entries as the work lands, not at release time.
- **A "small fix" on `main` during the freeze.** Test it against §1.1 honestly. If people
  can still update, it is 2.0 work no matter how small it is.
- **Adding a gate to `local-CI.sh` but not to `release.yml`.** The release build is what
  actually ships; a gate it does not run is a gate that fires too late.

## 11. Before you push

- [ ] Every commit subject carries its `ONEUP-` id (or is a release commit).
- [ ] The body says *why*, and records any figure that was measured.
- [ ] The roadmap bullet exists, and is annotated if this closes it.
- [ ] `CHANGELOG.md` has an `## [Unreleased]` entry with its plain-English line, if a user
      would notice this change.
- [ ] The branch is right: `main` only if §1.1 says so.
- [ ] `./local-CI.sh` is green — the whole thing, not the part you thought was affected.

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §1 the v1 freeze | nothing automatic — the branch a commit lands on is a human decision |
| §3 the commit subject format | nothing automatic. There is no `commit-msg` hook, and adding one is cheap if the format ever drifts |
| §4 roadmap IDs come from `.roadmap-counter` | the allocator itself: on a fresh clone the file is absent and appending **refuses**, rather than restarting at 1 and colliding |
| §5.1 the six version sites agree | `local-CI.sh`'s version-lockstep gate, and `tests/bump-test.py` proves `bump.py` advances all six in a throwaway copy |
| §6 local CI is green before a push | `githooks/pre-push` — but only once per clone, after `git config core.hooksPath githooks`. **Nothing enforces that it is enabled**, so on a fresh clone this rule is a habit |
| §6.1 a new gate is proved to fail before it is trusted | nothing automatic |
| §8 the release preconditions | `release.sh` — three fatal checks before it touches anything: a clean tree, on `main`, and the tag not already existing |

**The gap worth knowing about is §6.** Every other gate in this project runs *because*
`local-CI.sh` runs, and `local-CI.sh` runs automatically only if the hook path was set. On a
clone where nobody ran that one command, a green push proves nothing at all.

## 12. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: §6's gate table called the engine suite's 205 *assertions* 205 scenarios (it has 76), and §1 restated the freeze in full alongside `docs/design/oneup-2.0.md` §5.4 — this document is now canonical for the rule and the design carries the programme framing |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged (polish only). Verified here: §6 told the reader to keep `local-CI.sh` and `release.yml` in step, while three of `local-CI.sh`'s gates have never run in CI — now stated as the deliberate split it is, with what it costs |
