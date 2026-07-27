# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

**This file is a map and a trap list.** It is the lowest-ranked document in the set
(`docs/standards/documentation.md` §1.1): where it restates a rule, the standard is
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
tests/run-tests.sh                      # full test suite; non-zero exit on any failure
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

Read the one that covers what you are about to change. Each ends with a **What checks
this** table naming what catches a breach of each of its rules — and, honestly, which
rules nothing catches.

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

`ROADMAP.md` is the record of intended work; every change needs a bullet on it.

## 4. Architecture: a thin window driving a privileged engine

Two files, split by privilege:

- **`update_system.sh`** — the engine. Does all the real work and is the only part that
  becomes root. Authenticates once up front and keeps the credential warm for the run.
  Fully usable on its own in a terminal.
- **`updater.py`** — a PySide6 (Qt 6) front-end. **Never runs as root.** It shells out to
  the engine with `QProcess` and reads its stdout line by line.

They speak in one direction only, in `@@MARKER@@|payload` lines. **The whole contract —
every marker, its fields, the ordering rules and the traps — is
`docs/reference/marker-protocol.md`**, which outranks both halves of the app. Changing a
marker means changing the engine, the parser in the GUI, and the assertions in
`tests/run-tests.sh` in the same commit.

Step keys, the run order both files share: `system, flatpak, firmware, orphans, cache` —
the `TASKS` list in `updater.py`, the `LABEL` map in `update_system.sh`.

A step whose tool is absent (`flatpak`, `fwupd`) is **skipped cleanly, never errored**.
Keep new steps tolerant of a missing binary.

The four correctness invariants the test suite exists to protect — chiefly that a step
must never claim success or advise a reboot it did not earn — are
`docs/standards/testing.md` §5. Add a regression test for any engine behaviour change.

Runtime state lives in `~/.local/state/oneup/`, and two files there are a contract between
the two halves rather than mere state: `docs/reference/marker-protocol.md` §8.

**2.0 replaces both files** — the engine becomes Python, the window becomes a package.
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

- **The app draws no focus ring.** Keyboard focus reuses the hover look. This is a
  user-facing design decision, and it is about focus *highlighting* only — ordinary
  borders are fine. `docs/standards/ui-and-accessibility.md` §5.

- **`.roadmap-counter` is git-ignored on purpose**, because a tracked one-line counter
  makes every branch that allocates an ID conflict. On a fresh clone it is absent and
  appending a bullet refuses rather than restarting at 1 —
  `docs/standards/workflow.md` §4.
