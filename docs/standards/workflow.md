# Workflow Standard

<!-- OWNED-HERE workflow.md — OneUp's own standard, read instead of the global one, not a copy of it; decided 2026-10-22 (ONEUP-0236) -->

**In one sentence:** this is how a change gets from an idea to somebody's computer — which
branch it belongs on, what the commit says, how it earns a version number, and the one
gate it must pass green before it leaves this machine.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `8d4c93e` — every command, path and figure below was run or read against
the tree on 2026-07-27, not recalled.

**Sections:** 1 one branch · 2 branches · 3 commits · 4 roadmap IDs · 5 versions ·
6 the gate before a push · 7 pushing · 8 releasing · 9 where a change goes · 10 traps ·
11 before you commit and push · what checks this · 12 cold-eyes log

## 1. One branch

**Every change lands on `main`.** From 2026-07-26 `main` was frozen at 1.x while the 2.0
programme ran on a branch called `v2`. 2.0.0 was released on 2026-11-06, and `v2` was
deleted on 2026-11-11 once `main` held every commit it had. The freeze, its exceptions and
the tree that sent each change to a branch are in `docs/history/workflow.md`.

## 2. Branches

| Branch | What it is |
| --- | --- |
| `main` | The only long-lived branch, shared with `origin`, and **never rebased**. Every change lands here (§1) |

Rules:

- **`main` is never rebased and never force-pushed.** It exists on the remote, so rewriting
  its history breaks every clone of it. Merge instead, always.
- **Feature branches are optional and short.** If one is used, name it
  `<ONEUP-id>-<topic>` and merge it into `main` when its item is done. There is no
  requirement to branch for every item — the project has one developer and zero merge
  commits in its history.

**No pull-request gate.** The repository has no `CODEOWNERS`, no branch protection, and
no merge commits; commits land directly on their branch. Reviews happen through
`review-contract` on the documents and `local-CI.sh` on the code, not through GitHub review.

## 3. Commits

**Subject: `<ONEUP-id>: <what changed, in the imperative>`.**

```
ONEUP-0056: never report "up to date" for a source the check couldn't read
```

Exceptions, both real and both narrow:

- **A release commit is `OneUp X.Y.Z`** — the version is the identifier. `release.sh`
  writes it (`release.sh`, the `git commit` on the bump). **This deliberately differs from
  `~/.claude/standards/commits.md` §1.2**, which gives a release commit as
  `X.Y.Z: theme — short summary`. OneUp owns its commit rules — this section is read
  instead of that file (`docs/standards/documentation.md` §1.2) — and the form here is what
  five releases used and what the script writes. Recorded so that neither reader is
  surprised, rather than left as silent drift.
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

**`ROADMAP.md` is generated output — never hand-edit it.** Since 2026-08-18 the record
lives in the Ants roadmap store (machine-global, not in this repo), and every `roadmap_log`
write renders the whole file from the store over it. A hand edit therefore survives only
until the next write and then vanishes, with no error and no diff to explain it. Append,
flip and annotate with `roadmap_log`; read with `roadmap_query`, which answers
`source:"store"`. The shape below is what the store **renders**, not a template to type.

IDs are still allocated from `.roadmap-counter`, a one-line file holding the last number
handed out — `roadmap_log` bumps it. It is **deliberately git-ignored**: tracking it means
every branch that allocates an ID conflicts on the same line.

On a fresh clone the counter is absent, and appending a bullet **refuses** rather than
restarting at 1 — so a collision is impossible, but you must rebuild it first. The
one-liner lives in `.gitignore` alongside the ignore rule:

```bash
grep -oE 'ONEUP-[0-9]+' ROADMAP.md | grep -oE '[0-9]+' \
    | sort -n | tail -1 | sed 's/^0*//' > .roadmap-counter
```

**A bullet's shape** — status emoji, ID, bold headline, body, then the labelled lines.
An open bullet carries three; `Resolved` is added when it closes. **Prescriptive from
2026-07-26**: older ✅ bullets predate the rule and are left as they are, like
`docs/standards/documentation.md` §3's grandfathered specs.

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
close-out is a gotcha that gets lost. This is why ONEUP-0058 through 0063 exist: each was
filed in the task that surfaced it, not in a tidy-up pass afterwards.

## 5. Versions

**Semantic versioning**, as `CHANGELOG.md` states. What counts as breaking here is
`docs/standards/versioning-overrides.md`. For this project concretely:

- **Major** — 2.0.0, because the engine is replaced. A user's mental model of the app does
  not change, but everything underneath it does.
- **Minor** — a new capability inside 1.x (1.3.0 → 1.4.0: the Stop button, run-following).
- **Patch** — a fix that restores stated behaviour.

### 5.1 The six version sites

One version number lives in six places, and they must agree:

| # | Site |
| --- | --- |
| 1 | `APP_VERSION` in `oneup/__init__.py` — the in-app update check reads it. It was `updater.py` until ONEUP-0034 moved the window into the package; still six sites, not seven |
| 2 | `Version:` in `packaging/rpm/oneup.spec` |
| 3 | the newest `%changelog` stanza in the same spec — rpmlint rejects a mismatch, though nothing in this repository runs rpmlint; the lockstep gate is what catches it here |
| 4 | `versionformat` **and** `revision` in `packaging/obs/_service` |
| 5 | the newest `<release version="…">` in `data/za.co.antsprojectshub.OneUp.metainfo.xml` |
| 6 | the newest `## [x.y.z]` heading in `CHANGELOG.md`, **and the two links at its foot** — the `[x.y.z]:` release link, and the `[Unreleased]:` compare base, which must point at the tag just cut |

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

**`./local-CI.sh` must be green before every push.** It runs everything GitHub CI runs except
the AppImage build, plus the gates CI never runs. Measured on `v2` on the development
machine, a timed `./local-CI.sh` took **5m03s** on one run on 2026-10-02, after ONEUP-0032
added the right-to-left window pass and the translation checks. Earlier that day it took
**4m25s** once ONEUP-0072 retired the differential harness, and **5m46s** with the harness
after ONEUP-0054 stage 9 cut the window suite to one pass. Its parts were last measured on
their own on 2026-09-03: the engine suite **2m52s**, the window suite **~32s a pass**.

**The 34–38 seconds recorded here at `8d4c93e` was a `main`-era figure and had gone stale by
roughly six times** — the engine suite grew with the 2.0 build, and nothing re-measured it.
Minutes rather than seconds, so skipping it is tempting in a way the original figure did not
convey; the pre-push hook is what makes that unnecessary, and the markdown-only path below
is what keeps a documentation push cheap.

**A documentation-only push runs the markdown gates instead, and takes 0.14 s** (ONEUP-0114).
`githooks/pre-push` reads the refs on its stdin and, when it can prove every changed path
ends in `.md`, calls `./local-CI.sh --docs`: the version lockstep, `bump.py`'s functional
test and `tests/docs-check.py`. That set is *"every gate that can read a markdown file"*
rather than *"the documentation one"* — `CHANGELOG.md` is one of §5.1's six version sites,
and `bump.py` rewrites its heading and both compare links, so a malformed `[Unreleased]`
fails there and nowhere else. The engine suite, the GUI smoke test, `py_compile`, lint and
packaging validation cannot be reached by a `.md` edit.

**The fallback direction is the point.** A new remote branch, a range git cannot resolve, an
unreadable stdin — every uncertain case runs the full suite. A wrong guess must cost time
rather than coverage. The hook chooses the *mode*; `local-CI.sh` remains the one place that
says what each gate is.

**The hook gates the commits being pushed, not the working tree** (ONEUP-0216). A pushed
tip that is `HEAD` on a clean tree is gated in place; any other — an uncommitted edit, an
untracked file, a push of the branch you are not on — is checked out into a throwaway
worktree under the user's cache directory and gated there. **Before any gate, it scans the
pushed commits for secrets** by handing its stdin to the machine-wide hook's
`--secrets-only` mode; a find aborts the push. On a machine without that hook it prints
`NO SECRET SCAN` and carries on.

| Gate | What it proves |
| --- | --- |
| `Engine test suite` | `tests/run-tests.sh` — the markers the engine prints; the `oneup.engine` package by default since ONEUP-0054 stage 9 |
| `Engine parser unit tests` | `tests/parsers-test.py` — the pure half of the engine (`oneup/engine/parsers.py`): `to_bytes`, the two download-size wordings, the progress wordings, `zypper lr -u` output and the lock file's text, table-driven against real captured output |
| `System service suite` | `tests/service-test.py` — the system service (ONEUP-0249) against a private `dbus-daemon` and a fake polkit authority, with mock binaries in place of the root tools; exit 77 = `dbus-daemon` or `jeepney` absent, a skip. Has a `release.yml` leg |
| `GUI smoke test (offscreen)` | `tests/gui-smoke.py` — the window's state after being fed those markers (exit 77 = PySide6 absent, a skip), plus its G3 pairing scenario, which launches the Python engine through the window's own code path and reads what came back, where every other scenario feeds the window lines the suite wrote itself. Gate G3 of ONEUP-0054, with a `release.yml` leg. Run a second time as `tests/gui-smoke.py -reverse`, mirrored right-to-left, in both gates (ONEUP-0032 INV-5) |
| `Package structure (oneup/)` | `tests/imports-test.py` — the package rules a reader passes by eye: no path constant bound by name, no engine module importing `oneup/gui/`, no module building paths from its own `__file__`, the entry point never imported from inside the package, and every engine launch going through `paths.engine_argv` |
| `Translation groundwork (oneup/)` | `tests/i18n-check.py` — ONEUP-0032's source rules: no translation machinery in the engine, no explicit layout direction, font fallback never switched off, no size cap a translation could outgrow |
| `Python compile (updater.py, bump.py, oneup/)` | `py_compile updater.py bump.py` plus `compileall oneup` — `compileall` over the package rather than a file list, because a module nobody has imported yet is exactly the one a split leaves broken |
| `bump.py functional test` | `tests/bump-test.py` — a real bump in a throwaway copy still parses the five real version sites, and rewrites the (synthetic) `CHANGELOG.md`'s heading and both links correctly |
| `Lint` | `shellcheck`, then `ruff check .` with `pyproject.toml`'s rule set — best-effort |
| `Packaging validation` | desktop file and AppStream metainfo |
| `Version lockstep (six sites must agree)` | the **version numbers** at the six sites of §5.1 agree |
| `Documentation` | `tests/docs-check.py` — the rules of `docs/standards/documentation.md` that a script can settle, the `CHANGELOG.md` links §5.1's site 6 depends on, and the marker table in `docs/reference/marker-protocol.md` §3 against both the engine's `marker NAME` call sites and the markers the engine suite asserts on |

Listed in the order `local-CI.sh` runs them, so the table can be read against the script.

Deliberate design points:

- **A gate whose tool is not installed is reported as skipped, never silently passed.** A
  green run that quietly checked nothing is worse than a red one.
- **The AppImage build is opt-in** (`./local-CI.sh --full`, wrapped in a 10-minute
  timeout). `appimagetool` downloads its runtime from GitHub on every run and can stall on
  a slow or filtered link; the tag workflow builds and attaches it anyway (§7), so the local build is a convenience,
  not a gate. **Neither CI nor `--full`
  launches the result** — that check is a person, once, per `docs/design/oneup-2.0.md` §7's
  G8.
- **A red suite keeps its evidence** (ONEUP-0263). It prints every `FAIL` line under its
  `TEST:` heading, then its last lines and the machine's load average. The full logs are
  kept under `~/.local/state/oneup-ci/`, not `/tmp`, which is emptied at boot.

`githooks/pre-push` runs the fast gates automatically. Enable it once per clone:

```bash
git config core.hooksPath githooks
```

**`--no-verify` is not a way past a red gate.** It exists for the case where the hook
itself is broken. A failing test is fixed, not bypassed.

**The two gate sets are not identical, deliberately.** `release.yml` runs the test gates —
the engine suite, the parser unit tests, the `bump.py` functional test, the package structure
check, the translation groundwork check, the GUI smoke test and the system service suite — and the AppImage build, and nothing else. So **every other
gate in the §6 table has never run in GitHub CI**: the compile check, lint, packaging validation, version lockstep and
documentation. Written as names rather than a count, because a count goes stale
silently.

- **The extras stay local**, so understand what that costs: **a lint failure is
  caught before a push or not at all.** The pre-push hook is what makes that reliable.

### 6.1 A gate is how a rule stops being a wish

**When a reviewer or a human catches the same *class* of error twice, it becomes a gate.**
A rule nothing checks is a wish (`docs/standards/documentation.md` §5), and a cold reader is
the scarcest thing in this process — never spend one on what `grep -c` can settle.

Adding a gate:

1. **Add the check to `local-CI.sh`**, using its `ok` / `bad` / `skip` helpers, so a missing
   tool is reported as skipped and never silently passed. If editing a markdown file can
   break it, put it outside the `if ! $DOCS` blocks, so a documentation-only push runs it.
2. **Add a row to §6's table** saying what it proves. Name the gate the way the script
   labels it, so the table can be read against `local-CI.sh` line by line, and put the row
   in the position the script runs it.
3. **If it is a *test* gate, add it to `.github/workflows/release.yml` as well** — a test
   gate that runs only locally catches its first regression after the tag is pushed.
   **A test gate is a suite `docs/standards/testing.md` §1 lists**: a program that asserts on
   what OneUp or its release tooling does. A check that documents, packaging metadata or the
   version sites (§5.1) are well-formed or agree is not one — so `tests/docs-check.py` is not,
   though it lives under `tests/`. A new suite goes in that table first; the table is what
   makes it a test gate.
4. **Prove it fails.** Break the thing it checks, run it, see red, put the thing back. A gate
   nobody has seen fail is a gate nobody knows works — this is the same rule as
   `docs/standards/testing.md` §9's trap *"confirm a new test fails before it passes"*,
   applied to the gate itself.

**A gate reports, it does not repair.** `tests/docs-check.py` names the file, the line and the
rule, and changes nothing; the author decides what the right text is. A gate that edits prose
would quietly rewrite a claim it does not understand.

## 7. Pushing

**The repository is public** (`milnet01/OneUp`), so Linux runner minutes are free and there
is no reason to batch pushes. Push each commit as it lands, once local CI is green.

The only workflow is `release.yml`, and it triggers on `push: tags: ['v*']` — an ordinary
commit push runs no CI at all. A tag push runs the test gates §6 names, builds the AppImage and
attaches it to the GitHub release.

## 8. Releasing

`./release.sh X.Y.Z` does the whole thing. `--no-obs` skips OBS. The OBS step updates
`home:milnet:oneup`; the old `home:milnet` had its last update at 2.0.0 (`packaging/obs/README.md`).

It validates its arguments first — `X.Y.Z` or nothing happens, and every option after it
must be `--no-obs` or it refuses. Then its preconditions, which are checks rather than suggestions, and it
exits on any of them:

1. a clean working tree,
2. on `main`,
3. the tag `vX.Y.Z` does not already exist.

Then, in order: bump the six sites → `./local-CI.sh` → show the diffstat → **ask for
confirmation** → commit `OneUp X.Y.Z`, tag, push → update the OBS package via `osc` → sign
the AppImage.

**A red gate stops it there, with the bump already written to your tree** — the same state a
declined confirmation leaves. **The recovery is ordered, and the order matters**, because
`release.sh`'s first precondition is a clean tree: discard the bump with `git checkout -- .`
first, fix what was wrong, **commit the fix**, and only then re-run. The precondition applies
to your fix exactly as it applies to the bump — an uncommitted fix is refused the same way.

**A refusal part-way through the bump leaves a partial one.** `bump.py` writes the six
sites one at a time and stops at the first whose format has drifted, so the sites before it
are already rewritten. Each file is written whole or not at all, so an interruption never
leaves one empty. Same recovery, same order: discard, fix the drifted file, re-run.

**A failed `git push` is the awkward one**, because it fires after the commit *and* the tag.
The push is `--atomic`, so when it fails neither the branch nor the tag reached GitHub.
`git checkout -- .` recovers nothing there. Undo is `git tag -d vX.Y.Z`, then
`git reset HEAD~1` — a mixed reset, so the bump lands back in the working tree — then
`git checkout -- .` to discard it, and only then re-run. A `--soft` reset leaves everything
staged, which the clean-tree precondition refuses just the same.

Three things about that sequence are worth knowing before you run it:

- **It stops and waits for a yes.** A release is not unattended. Answering anything but
  `y` or `Y` aborts and leaves the bump in your tree; `git checkout -- .` discards it.
- **The commit takes only the five files `bump.py` writes**, by name. The clean-tree
  precondition runs before the bump, local CI and the prompt, so it cannot see a file the
  suites leave behind or an edit made while the prompt waits. Any change outside those
  five files stops the release before the commit, naming the files.
- **The OBS step needs `osc` configured.** If `osc` is missing, or the checkout fails, or
  the commit fails, it says so and points at `packaging/obs/README.md` for the web-UI route.
  The GitHub release has already happened by then and is unaffected. The run then ends with
  *"OBS was NOT updated"* and exit status 3, never *"Released"*.
- **The signing step waits for GitHub's build.** It runs after OBS, `--no-obs` included,
  so neither failure skips the other. It waits for the tag's Release workflow, downloads
  the AppImage into a temporary folder, signs it with the key on this PC, checks the
  signature against the committed public key and uploads `OneUp-x86_64.AppImage.sig`.
  Without that file no installed AppImage is offered the release (ONEUP-0112). With any
  step failing, it says so in red and exits 4, which wins over OBS's 3.
  `./release.sh --sign-only X.Y.Z` runs this step alone.
- **The key is checked before anything changes.** A missing signing key, or one that is
  not the private half of the committed public key, stops the release at the start,
  `--sign-only` included. `python3 packaging/sign-release.py --check-key` runs the same
  check by hand.

**Once, before the first signed release, make the signing key:**
`python3 packaging/sign-release.py --generate`. It writes the private key to
`~/.config/oneup-release/signing.key` and prints a line to put in
`oneup/gui/update_key.py`; commit that line. `$ONEUP_SIGNING_KEY` points `release.sh`
elsewhere. **Back the key up.** `docs/standards/security.md` §13.5 says why.

**A release that fails to publish is fixed, never re-versioned.** The user's rule,
2026-11-06: *"A new version means we added something which we haven't."* When the tag's
workflow or an OBS build fails, fix it, move the tag onto the fix, push it again, and re-run
both OBS packages from the moved tag, so every copy of that version is the same source.
The moved tag rebuilds the AppImage, so its old `.sig` no longer matches: finish with
`./release.sh --sign-only X.Y.Z`, which replaces it.
2.0.0 was finished this way twice (ONEUP-0378, ONEUP-0379).

**What the user still has to do by hand:** nothing on the GitHub side — CI builds and
publishes. The OBS rebuild is the one step that can need finishing manually.

**Three distribution paths ship each release**, and all three must work: the AppImage (from
the tag workflow), the RPM (`packaging/rpm/oneup.spec`), and the OBS repository users
install from with `zypper`.

### 8.1 There is no fourth path, and there is not going to be one

**OneUp is not published on Flathub, and is not packaged for any distribution other than
openSUSE.** The user's decision, 2026-07-27. It is a decision on the merits, not a
deferral — recorded here so that *"why isn't this on Flathub?"* has a dated answer instead
of looking like an oversight.

Two independent reasons, either of which is sufficient:

- **A Flatpak is sandboxed, and every one of OneUp's five steps acts on the host.**
  `zypper` and `flatpak update --system` are run through `sudo`; `fwupdmgr` is not, because
  it reaches the same host state through fwupd's own system daemon. Different routes, same
  destination: the machine outside any sandbox. A sandboxed build would have to hole its
  own confinement to do the one thing it exists for, leaving a package that is either
  useless or dishonest about being confined. The boundary in
  `docs/standards/security.md` §1 assumes the engine is an ordinary host process that
  `sudo` elevates. A Flatpak is not that.
- **The other distributions do not need it.** The user tested them: their update systems
  are already fine. OneUp exists because keeping openSUSE current means running several
  different commands, some of which the graphical tools get wrong on Tumbleweed
  (`README.md` says which). That problem is openSUSE's, so the answer is too.

**What this does and does not close.** It closes packaging OneUp *for* other systems. It
does not touch the `flatpak` **step** — OneUp updates the Flatpaks already installed on
your machine, and that is unaffected. The two share a word and nothing else.

Reopening this needs a new reason, not a new opinion: a distribution whose own update path
is genuinely broken in the way Tumbleweed's was, or a confinement technology that can grant
host package-manager access without pretending to be a sandbox. Filed as **ONEUP-0071**,
status *considered*, so the reasoning stays findable.

## 9. Where a change goes

To `main` (§1). The 2.0 programme's branch tree that stood here is in
`docs/history/workflow.md`.

## 10. Traps

- **Rebasing `main`.** It is shared with the remote. The damage is not to your clone.
- **Hand-editing one version site.** The other five then disagree with it; the lockstep gate
  catches it, but only if you run local CI — and the RPM `%changelog` one is the easiest to
  forget, because nothing else references it.
- **Committing `.roadmap-counter`.** It is ignored for a reason. If it ever appears in
  `git status`, something removed the ignore rule.
- **Allocating an ID on a fresh clone without rebuilding the counter.** The append refuses
  — that is the design working, not a bug. Run the one-liner in §4.
- **Releasing with an empty `## [Unreleased]`.** `bump.py` has nothing to derive the
  packaging notes from and stops. Write the entries as the work lands, not at release time.
- **Adding a *test* gate to `local-CI.sh` but not to `release.yml`.** The release build is
  what actually ships; a test gate it does not run is a test gate that fires too late. (The
  non-test extras staying local is deliberate, not this trap — §6.)

## 11. Before you commit and push

- [ ] Every commit subject carries its `ONEUP-` id (or is a release commit).
- [ ] The body says *why*, and records any figure that was measured.
- [ ] The roadmap bullet exists, and is annotated if this closes it.
- [ ] `CHANGELOG.md` has an `## [Unreleased]` entry with its plain-English line, if a user
      would notice this change.
- [ ] You are on `main`, or on a feature branch that merges into it (§2).
- [ ] `./local-CI.sh` is green — the whole thing, not the part you thought was affected.
      A push the hook proves documentation-only runs `--docs` instead (§6).

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §2 `main` is never rebased or force-pushed | **nothing, and the damage is off this machine.** No branch protection exists (the repository has none), so a `git push --force` on `main` would succeed and break every clone. It is the one trap in this document with no net under it at all |
| §3 the commit subject format, the `Co-Authored-By:` trailer, and one thing per commit | nothing automatic, for all three. There is no `commit-msg` hook, and adding one is cheap if the format ever drifts |
| §5.2 released CHANGELOG entries are never rewritten | nothing automatic — `git` will happily let you edit a shipped entry. The tag is the only record that contradicts you |
| §4 a commit's ID names a bullet that exists | **nothing.** `tests/docs-check.py` never opens `ROADMAP.md`, so a subject citing an ID nobody ever filed reads exactly like one that was |
| §4 roadmap IDs come from `.roadmap-counter` | the allocator itself: on a fresh clone the file is absent and appending **refuses**, rather than restarting at 1 and colliding |
| §5 the version increment matches the change | **nothing.** `release.sh` takes `X.Y.Z` as an argument and never questions it; calling a breaking change a patch release is caught by a person or not at all |
| §5.1 the six version sites agree | `local-CI.sh`'s version-lockstep gate — for the version **numbers**, at all six sites. `tests/bump-test.py` covers a *different* failure: it runs a real bump in a throwaway copy where five of the six sites are the real files copied verbatim, so a site whose format has drifted makes `bump.py` refuse ("no match … file drifted from the expected format") and the test fail. Since 2026-08-03 it also reads every site back after the bump and asserts the new version landed at that site's own pattern (`APP_VERSION = "…"`, `^Version:`, the newest `%changelog` stanza, `versionformat`/`revision`, the newest `<release>`) — an exit code alone proves only that the regexes *matched*, not that they wrote the right value. Its target version is deliberately one no shipped file already contains, because `bump.py` prepends to the `%changelog` and `<releases>` lists and a colliding version makes those two read-backs match the old entry and pass regardless |
| §5.1 site 6's two `CHANGELOG.md` links match its newest heading | `tests/docs-check.py`. Added 2026-07-26: the lockstep gate reads only the heading, and a hand-edit could leave the release link missing or the `[Unreleased]` compare base pointing at the previous tag — which is ONEUP-0033, a bug this project shipped once already |
| §5.2 a release needs a non-empty `## [Unreleased]` | `bump.py` — it refuses outright: *"CHANGELOG.md has no non-empty '## [Unreleased]' section to release"*. One of the few rules here with a hard automatic stop |
| §6 the pushed commits carry no secret | `githooks/pre-push`, through the machine-wide hook's `--secrets-only` gitleaks scan — on this machine only. Elsewhere the hook says `NO SECRET SCAN` and nothing else checks |
| §6 local CI is green before a push | `githooks/pre-push` — but only once per clone, after `git config core.hooksPath githooks`. **Nothing enforces that it is enabled**, so on a fresh clone this rule is a habit |
| §7 push each commit once local CI is green | nothing automatic, and nothing needs to be — the repository is public, so a wasted push costs no runner minutes and an unpushed commit harms only its author |
| §6.1 the same *class* of error caught twice becomes a gate | nothing automatic — it is a judgement made in a review pass, and the only evidence it was made is that the gate exists |
| §6.1 a new gate is proved to fail before it is trusted | nothing automatic |
| §6.1 step 2 — a new gate's row is named as the script labels it, in script order | nothing automatic. The table and the script are compared by a reader or not at all |
| §6.1 a gate reports and does not repair | nothing automatic, but it is self-punishing: a gate that edited prose would be rewriting a claim it does not understand, and the next cold read finds it |
| §6 a gate whose tool is absent is reported skipped, never silently passed | the `skip` helper. GUI smoke, Lint and Packaging validation reach for it; every other gate depends only on `bash` and `python3`. Nothing checks that a new optional-tool gate reaches for it rather than a bare `ok` |
| §6 `--no-verify` is not a way past a red gate | **nothing, by construction** — it is the flag that turns the check off. Only the author's intent stands behind this one |
| §3 the body says *why*, and records any measurement | nothing automatic |
| §4 a finding is filed the moment it is found | nothing automatic, and by its nature nothing could: an unfiled finding leaves no trace to check |
| §2 a feature branch is named `<ONEUP-id>-<topic>` | nothing automatic, and it has never been exercised — the repository has no feature branches |
| §4 a bullet's shape, its `**Layman:**` / `Kind:` / `Source:` lines, and closing by annotation rather than deletion | **nothing.** `tests/docs-check.py` never reads `ROADMAP.md`. A malformed or deleted bullet is caught by a reader or not at all |
| §5.2 a CHANGELOG entry's shape — bold summary, id, then the plain-English line | nothing automatic. `bump.py` reads the bold summaries to build the packaging notes, so a missing `**` silently drops an entry from the release notes rather than failing |
| §6.1 step 3 — a new **test** gate goes in `release.yml` too | nothing automatic. Nothing compares the two gate sets, and the failure is silent by construction: the gate passes locally, so the omission only shows up as a regression that reached a tag |
| §8 the release preconditions | `release.sh` — three fatal checks before it touches anything: a clean tree, on `main`, and the tag not already existing |
| §8 all three distribution paths work | **nothing automatic.** `./local-CI.sh --full` builds the AppImage and does not launch it; nothing anywhere builds the RPM or the OBS package. They are proven by a real release, which is why `docs/design/oneup-2.0.md` §7's G8 makes all three launches a manual condition |
| §8.1 no fourth distribution path | **nothing, and nothing should.** Adding a packaging path is a deliberate act by a person, not something that happens by accident, so there is no breach for a script to catch. What the row is for is the opposite failure: somebody proposing one without knowing it was already weighed. ONEUP-0071 is the answer to that |

**The gap worth knowing about is §6.** Every other gate in this project runs *because*
`local-CI.sh` runs, and `local-CI.sh` runs automatically only if the hook path was set. On a
clone where nobody ran that one command, a green push proves nothing at all.

## 12. Cold-eyes loop log

The rows are in [`docs/reviews/workflow-loop-log.md`](../reviews/workflow-loop-log.md).
