# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

**This file is a map and a trap list.** It is the second-lowest-ranked document in the set,
above only the global default set at `~/.claude/standards/`
(`docs/standards/documentation.md` §1.1) — except `roadmap-format.md`'s bullet grammar,
which outranks that whole table and no project may override (§1.2): where it restates a rule, the standard is
canonical and this file is wrong. What it holds that nothing else does is §6 — the traps,
each of which cost a real bug to learn.

## 1. What OneUp is

A one-click update dashboard for openSUSE (Tumbleweed and Leap). It runs the five update
tasks openSUSE actually needs — system packages, Flatpaks, firmware, leftover-package
removal, and cache cleanup — the way the distro's docs recommend, behind per-task toggles.
`README.md` has the user-facing rationale.

## 2. Run & test

```bash
python3 updater.py                      # launch the GUI (needs PySide6 / Qt 6)
./update_system.sh                      # run the engine standalone in a terminal (all steps)
./update_system.sh --steps=system,cache # run only selected steps
./update_system.sh --check --notify     # read-only "updates available?" pass (no root)
tests/run-tests.sh                      # engine suite; non-zero exit on any failure
python3 tests/gui-smoke.py              # window suite (needs PySide6; exit 77 = skipped)
./local-CI.sh                           # every gate that runs before a push (workflow.md §6)
./local-CI.sh --full                    # also build the AppImage (needs a good connection)
```

There is no build step: a Python script plus a Bash script, run directly from the
checkout. The suites take no arguments and run every scenario; to focus on one, comment
out the others in `tests/run-tests.sh` — there is no per-test selector.

**`./local-CI.sh` must be green before every push.** What it gates, why the AppImage build
is opt-in, and how to add a gate: `docs/standards/workflow.md` §6. The `githooks/pre-push`
hook runs the fast gates for you — enable it per clone with `git config core.hooksPath
githooks`.

## 3. Where the rules live

Read the one that covers what you are about to change. Every standard and the marker
reference carries a **What checks this** table, just before its loop log, naming what
catches a breach of each of its rules — and, honestly, which rules nothing catches.

| Subject | Document |
| --- | --- |
| Which document owns which decision; how a document is verified and reviewed | `docs/standards/documentation.md` |
| Branches, commits, roadmap IDs, versions, the push gate, releasing | `docs/standards/workflow.md` |
| The privilege boundary, authentication, validation, stopping, logs | `docs/standards/security.md` |
| Python floor, lint, module size, subprocess discipline, Qt idioms | `docs/standards/coding.md` |
| What a test may depend on, the mock sandbox, the invariants that must never regress | `docs/standards/testing.md` |
| Where a new file goes, what it is called, what adding it obliges you to update | `docs/standards/files-and-naming.md` |
| Accessible names, colour, scaling, focus, dialogs, themes, right-to-left | `docs/standards/ui-and-accessibility.md` |
| What the app says to the user, and how to keep it translatable | `docs/standards/wording-and-translation.md` |
| Version policy for CI actions, runtimes and packages, plus the incompatibility ledger | `docs/standards/dependencies.md` |
| The engine↔window contract — every marker, field layout and ordering rule | `docs/reference/marker-protocol.md` |
| What 2.0 is and what its items share | `docs/design/oneup-2.0.md` |

`ROADMAP.md` is the record of intended work; every change needs a bullet on it — appended
with `roadmap_log`, never by editing the file, which is generated output (§6).

## 4. Architecture: a thin window driving a privileged engine

**Read the branch you are on.** On `main` the app is the two files below. On `v2`, as of
ONEUP-0034, the window is a package — `oneup/gui/`, a module per job, behind a shim still
called `updater.py` — and the state paths in **both halves** honour `XDG_STATE_HOME`
when it is set to an ABSOLUTE path, falling back to `~/.local/state/oneup/` when it is
unset, empty or relative (ONEUP-0059).
The privilege split, the marker contract, the step keys and everything else in this
section are unchanged by that; only the file boundaries moved.

**No document `tests/docs-check.py` scans may backtick a path that exists only on `v2`** —
and it scans four: `docs/standards/`, `docs/reference/`, this file and `README.md`. Its §9
check fails a backticked path that carries **both** a directory separator and a file
extension and does not resolve, so a standard here cannot name `oneup/gui/…py`. Neither a
bare directory nor a bare filename matches that pattern, which is how
`docs/standards/files-and-naming.md` §4 already describes the package's shape and rules on
`main`, correctly — and is not licence to evade the check by dropping the directory. Where a standard must name a package file, that is a rule binding it
to code `main` does not have; `docs/standards/workflow.md` §9 decides the branch, and this
file does not restate it.

Two files, split by privilege:

- **`update_system.sh`** — the engine. Does all the real work and is the only part that
  becomes root. Authenticates once up front and keeps the credential warm for the run.
  Fully usable on its own in a terminal.
- **`updater.py`** — a PySide6 (Qt 6) front-end. **Never runs as root.** It shells out to
  the engine with `QProcess` and reads its stdout line by line.

They speak in one direction only, in `@@MARKER@@|payload` lines. **The whole contract —
every marker, its fields, the ordering rules and the traps — is
`docs/reference/marker-protocol.md`**, which outranks both halves of the app. Changing a
marker means changing every file §5 lists — the emitter, the window's parser and BOTH
suites — plus the reference itself, in one commit. §5 names them; this file does not.

Step keys, the run order both halves share: `system, flatpak, firmware, orphans, cache` —
the `TASKS` list (in `updater.py` on `main`; inside the package on `v2`, where `updater.py`
is only the shim) and the `LABEL` map in `update_system.sh`.

A step whose tool is absent (`flatpak`, `fwupd`) is **skipped cleanly, never errored**.
Keep new steps tolerant of a missing binary.

The four correctness invariants the test suite exists to protect — chiefly that a step
must never claim success or advise a reboot it did not earn — are
`docs/standards/testing.md` §5. Add a regression test for any engine behaviour change.

Runtime state lives in `~/.local/state/oneup/`, and four files there are a contract between
the two halves rather than mere state: `docs/reference/marker-protocol.md` §8. `run.state`
and `stop.request` are the original pair; `hold.state` and `go.request` were added by
ONEUP-0044 so one engine can span the size preview and the run. (On `v2`
that directory follows an absolute `XDG_STATE_HOME` — in **both** halves, in one commit,
because moving one side alone leaves Stop writing where the engine never looks.)

**2.0 replaces both files** — the engine becomes Python, the window has become a package
(ONEUP-0034, on `v2`).
`docs/design/oneup-2.0.md` is the programme; `main` is frozen at 1.4.0 and takes only
qualifying bug fixes (`docs/standards/workflow.md` §1).

## 5. Packaging & versioning

Three distribution paths: an **AppImage** (`packaging/appimage/build-appimage.sh`, built
and attached by the `v*`-tag workflow in `.github/workflows/release.yml`), an **RPM**
(`packaging/rpm/oneup.spec`), and **OBS** for a `zypper`-installable repo
(`packaging/obs/`, flow in `packaging/obs/README.md`).

App ID: `za.co.antsprojectshub.OneUp` — the desktop file, icon and AppStream metainfo
under `data/` all use it.

**The version lives in six places that must agree, and none of them is hand-edited.** Run
`./bump.py X.Y.Z`, or `./release.sh X.Y.Z` for the whole release. The six sites, why each
exists, and what the lockstep gate checks: `docs/standards/workflow.md` §5.1.

## 6. The traps

Each of these cost a real bug. They are terse here on purpose — the reasoning, the
measurement and the exact shape of the rule are in the document named beside each.

- **Never signal the engine to stop a transaction.** `SIGTERM` mid-`zypper dup` either
  leaves rpm half-applied or orphans a zypper that carries on regardless, and its
  abandoned lock blocks the next run. Stopping is cooperative, at safe boundaries only —
  `docs/standards/security.md` §6.

- **A privileged call must not sit inside a subshell.** With no terminal, sudo keys its
  cached credential to the parent process id, and bash forks a real subshell for
  `$(cmd | other)` and friends — so each one authenticates again, which the user sees as
  another password dialog. Capture with `sudo_capture` and process the text afterwards —
  `docs/standards/security.md` §2.2, and §2.3 for the shape this takes in the Python
  engine.

- **A run must survive the GUI going away.** The logging `exec` uses `tee -a -p`; without
  `-p`, quitting the window kills `tee`, `SIGPIPE`s the engine, and leaves zypper orphaned
  mid-transaction. Never add a code path that kills the engine mid-run —
  `docs/standards/security.md` §6.3.

- **Nothing the engine spawns may outlive it.** A trap cannot run when the engine is
  `SIGKILL`ed, so a background helper must watch the engine's pid and exit on its own.
  Keep-alives were once found still running 40 minutes after their run was killed —
  `docs/standards/security.md` §2.4.

- **To ask "has my parent gone?", `kill -0` the pid you captured — never read `$PPID`
  again.** Bash sets `PPID` once at shell start and never refreshes it on reparenting, so
  comparing `$PPID` against a startup copy of itself can never fire; and testing it against
  `1` never fires either, because systemd reparents a user session's orphans to
  `systemd --user`. Measured: a child whose parent exited kept `$PPID=170203` for its whole
  life while its real parent moved to `1309`. Both spellings read as a guard and are dead
  code, and both have now been written on this engine — the pid-1 form in
  `reap_orphaned_askpass`, the change-detection form in a spec draft that two review loops
  caught. The keep-alive in `sudo_init` already does it correctly (`while kill -0 "$1"`) —
  `docs/specs/ONEUP-0044-one-authentication.md` §4.2.

- **The suite's prompt counters cannot see a second `sudo_init` inside ONE process.** The
  three counting sudo mocks key their timestamp file to `$PPID`, which is how they model
  sudo's real no-tty behaviour — so two `sudo_init` calls from the same engine share one
  timestamp and log one prompt. Measured: deleting the `HELD_AUTH` guard that suppresses
  the second `sudo_init` on ONEUP-0044's held path left the one-prompt test **green**.
  What caught it was the keep-alive scenario, because the second `sudo_init` spawns a
  second `setsid` group and overwrites `SUDO_KEEPALIVE`, so `cleanup`'s group kill reaches
  only the later one and a keep-alive is orphaned. So a change that could re-enter
  `sudo_init` is covered by INV-9, never by INV-1. Re-measured 2026-09-02: removing the
  `HELD_AUTH` guard fails exactly one check, *"a keep-alive survived a held run (INV-9)"*,
  and leaves the one-prompt scenario green. The `$PPID` half is
  `docs/specs/ONEUP-0044-one-authentication.md` §7.1; INV-9 itself is that spec's invariant
  list, not §7.1.

- **A shape check on a field of codes does not catch English — check membership instead.**
  A `^[a-z0-9-]+$` test looks like it forbids prose, and against a *space-separated* field it
  does not: every word of *"core system packages were updated"* matches it one at a time, so
  a half-converted payload passes and the suite stays green. Where a closed vocabulary
  exists, assert membership of it; shape only tells you a token is well-formed, never that it
  is one of yours. Caught in review rather than in production, by running the regex instead
  of reading it — `docs/specs/ONEUP-0072-marker-codes.md` INV-1.

- **A test must never depend on, or damage, the state of the machine it runs on.** Both
  defaults have bitten for real: the lock probe reads `/run/zypp.pid`, and `run.state`
  defaults to the user's own — so the suite once deleted a live run's record. A scenario
  that invokes the engine outside `run_engine` must redirect those paths by hand —
  `docs/standards/testing.md` §2.

- **A slow server must never be indistinguishable from a hang.** Measured, not assumed:
  one mirror served a repository index at under a kilobyte a second and the app showed
  nothing whatever, because zypper prints that phase as dots with no line ending. Three
  defences exist and all three are needed — a per-repository timeout in the engine, a
  liveness line in the GUI, and a stall clock stamped on the raw chunk before any line
  splitting. ONEUP-0048; the invariant is `docs/specs/ONEUP-0054-python-engine.md`.

- **The app draws no focus ring — and the cue is DERIVED, not copied from hover.** No ring
  is the user-facing design decision, and it is the half that cost the bug: Qt ignores
  `outline-radius` so a ring draws square around rounded buttons, and a border added on
  focus resizes the widget. It is about focus *highlighting* only — ordinary borders are
  fine. What replaced *"focus reuses the hover look"* is a measurement, not a preference:
  hover lightens, and pure white measures 2.63:1 against the accent button's top gradient
  stop, so no lighter shade reaches SC 2.4.13's 3:1 there at any saturation. A focused
  control's fill is blended toward black or white until it clears 3:1 against every surface
  it rests on. Copying a `:hover` rule into a `:focus` one lands a cue of about 1.2:1 —
  `docs/standards/ui-and-accessibility.md` §5.

- **Rewriting a repository URL must never touch the alias — the alias is the cache key.**
  libzypp keys `/var/cache/zypp/packages/<alias>/` by repository alias, and an openSUSE
  repo's alias usually *contains* the host name (`download.opensuse.org-oss`), so a
  blanket substitution renames it and silently discards every package already downloaded —
  defeating ONEUP-0087 on the one path where the kept cache matters most. Anchor the
  substitution to `baseurl=` lines. Nothing in the code announces this; it was found by
  running `zypper --reposd-dir` against a copy and reading the aliases back —
  `docs/specs/ONEUP-0094-download-recovery.md` §4.2.

- **A privileged call added without a matching drop-in entry is invisible until a
  passwordless user meets it.** Nothing fails: the new `sudo …` line is correct code that
  simply prompts, and only someone who turned *Passwordless* on ever finds out — mid-run,
  in sudo's own bare wording. Three such calls accumulated that way (ONEUP-0092). A new
  privileged shape needs an entry in `auth_cmnds`, and the structural check in
  `tests/run-tests.sh` that pins the engine's privileged call-site count is what stops the
  fourth — `docs/standards/security.md` §5.2.

- **Editing the download guard's text is a re-grant for every existing user.** The engine
  compares the installed guard against what it would emit now, so a whitespace or comment
  change invalidates every live grant: those users' toggles read off, their weekly updates
  stand down, and they must switch *Passwordless* on again. Correct — the file really is no
  longer the one the engine expects — but it means `download_guard_src` is not a place for
  cosmetic edits. `docs/standards/security.md` §5.7.

- **`.roadmap-counter` is git-ignored on purpose**, because a tracked one-line counter
  makes every branch that allocates an ID conflict. On a fresh clone it is absent and
  appending a bullet refuses rather than restarting at 1 —
  `docs/standards/workflow.md` §4.

- **`ROADMAP.md` is generated output — do not hand-edit it.** Migrated to the Ants roadmap
  store on 2026-08-18, which is now the source of truth. Every `roadmap_log` write renders
  all of it from the store over the file, so a hand edit survives only until the next write
  and then vanishes with no error and no diff to explain it. Use `roadmap_log`
  (`append` / `flip` / `annotate`); read with `roadmap_query`, which answers `source:"store"`.
  Two consequences that are not visible in the file. **`roadmap_log op:"amend_headline"` no
  longer works here** — it refuses with `unsupported_format`, because the headline is a store
  column and its locate key; to change one, edit the store. And **the store is machine-global**
  (`~/.local/share/ants-terminal/roadmap.sqlite`), not in this repo, so a fresh clone has the
  markdown and not the history behind it. The migration was verified lossless: normalising
  whitespace makes the rendered file character-for-character identical to its pre-migration
  content. Recorded on `ONEUP-0057`.

- **A spec's `Reviewed` stamp does not survive another item editing it, and nothing in the
  file says so.** ONEUP-0044 pinned `hold.state` and `go.request` into
  `docs/specs/ONEUP-0054-python-engine.md` §4.1.1 on 2026-08-23 — a change to what the
  Python engine's implementer must build — and the stamp still read `Reviewed` from July,
  with no diff and no error to show the gate had lapsed. The next session to open it would
  have built from a contract nobody had re-read. `spec_query mode:"gate_drift"` reports
  which specs are stale and names the commit that did it; six were on 2026-08-24, so this
  is the normal state of a busy branch rather than an incident. Run it before trusting a
  stamp, and before starting any item whose spec was written more than a few items ago —
  `docs/standards/documentation.md` §7 owns the gate itself, and `CLAUDE.md` rule 14 in the
  global set owns when it re-arms. Recorded on `ONEUP-0127`.
