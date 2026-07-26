# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

OneUp is a one-click update dashboard for openSUSE (Tumbleweed and Leap). It runs the
five update tasks openSUSE actually needs — system packages, Flatpaks, firmware,
leftover-package removal, and cache cleanup — the way the distro's docs recommend, behind
per-task toggles. See `README.md` for the user-facing rationale.

## Run & test

```bash
python3 updater.py                      # launch the GUI (needs PySide6 / Qt 6)
./update_system.sh                      # run the engine standalone in a terminal (all steps)
./update_system.sh --steps=system,cache # run only selected steps
./update_system.sh --check --notify     # read-only "updates available?" pass (no root)
tests/run-tests.sh                      # full test suite; non-zero exit on any failure
./local-CI.sh                           # local CI gates (tests/lint/validation/version-lockstep) — ~1s; run before every push
./local-CI.sh --full                    # also run the AppImage build (needs a good connection; 10-min timeout)
```

There is no build step for development — it's a Python script plus a Bash script. `python3
updater.py` from the checkout runs the live code directly. The tests take no arguments and
run every scenario; to focus on one, comment out the others in `tests/run-tests.sh` (there
is no per-test selector).

**Always run `./local-CI.sh` (green) before pushing.** It gates on the same test suite
GitHub CI runs, plus extra checks CI doesn't (lint, desktop/AppStream validation, and a
six-site **version-lockstep** check) — all in ~1 second. The **AppImage build** is opt-in
(`--full`): `appimagetool` downloads its runtime from GitHub each run and can stall on a
slow/filtered link, and GitHub CI builds + verifies the AppImage on every tag push anyway, so
the local build is a convenience (wrapped in a 10-min timeout). A `githooks/pre-push` hook
runs the fast gates automatically; enable it per clone with `git config core.hooksPath
githooks`. Keep `local-CI.sh` and `.github/workflows/release.yml` in sync — add a new gate to
both.

## Architecture: a thin GUI driving a privileged engine

The whole app is two files with a deliberate privilege split:

- **`update_system.sh`** — the engine. Does all the real work and is the only part that
  touches root. Authenticates **once** up front (`sudo -v` via the `ksshaskpass` popup) and
  keeps the credential warm for the run, so one password prompt covers everything. Fully
  usable on its own in a terminal.
- **`updater.py`** — a PySide6 (Qt 6) front-end. **Never runs as root.** It shells out to
  the engine via `QProcess` (`Updater._launch`), passing `--steps=…` and reads the engine's
  stdout line-by-line.

They communicate through a **line-based marker protocol**: the engine prints
`@@MARKER@@|payload` lines (defined in the header comment of `update_system.sh` around line
79); the GUI parses them in `Updater.handle_marker` (updater.py ~line 786) and updates
progress bars, badges, and banners. Non-marker lines are plain log output. The markers are
the contract between the two files — **changing a marker's name or field layout in one file
means updating the parser in the other, and the assertions in `tests/run-tests.sh`.**
Current markers: `STEP_BEGIN`, `STEP_END`, `TIMING`, `PROGRESS`, `REFRESH`, `SNAPSHOT`, `SNAPSHOT_ITEM`, `SNAPSHOTS`, `CHECK`,
`CHECK_ITEM`, `CHECK_UNKNOWN`, `SIZE`, `FREED`, `AUTH`, `DISK`, `REPO`, `REPO_SKIPPED`, `HINT`, `REMEDY`,
`SERVICES`, `INSTALLED`, `REBOOT`, `DONE`.
(`DONE|ok|errors|stopped` — the third value means the user asked to stop, so the GUI must
report neither success nor failure. The GUI normally takes the verdict from the engine's
exit code and `DONE` is belt-and-braces, **except** for a run it merely *followed*
(`Updater._attach_to_running_engine`), where there is no exit code to read and `DONE` is
the only verdict; a followed run that never printed one is reported as errors, never as
success.)
(`PROGRESS|key|done|total|phase` carries live per-package progress *within* a step, so a
long download can't look like a hang — `phase` is `download` or `install`, and a **total of
0 means "unknown"**, which the GUI must render as a running tally rather than inventing a
denominator. The engine derives it in `progress_filter` by parsing zypper's own output
(`Preloading:` has no counter, `Retrieving: … (12/77)` and `( 7/77) Installing:` do), so the
three phase wordings are a dependency on zypper's output format — `LC_ALL=C` is pinned on the
transaction to keep them stable on a non-English desktop. The GUI announces a phase *change*
only, never each package. Two **optional** trailing fields —
`PROGRESS|key|done|total|phase|bytes|bytes_total` — carry the download figures; either may be
`0` for "not known". zypper's total is printed once as `Package download size:` *or*
`Overall download size:` (which one depends on the transaction backend, so **both wordings
are parsed** — the first is what `classic_rpmtrans` prints).)
(`REFRESH|done|total|alias` names the repository being fetched and the position in the list,
because that phase is otherwise **completely invisible**: zypper reports it as undelimited
dots with no line ending, so the GUI's line-based reader draws nothing at all. See
`refresh_repos` — the engine refreshes one repository at a time precisely so this marker,
a per-source time budget, and a stop check can exist. Byte figures are impossible here:
zypper's metadata staging directory is root-only, so the GUI's fallback of weighing
`/var/cache/zypp/packages` (world-readable, hence no root) only helps the *package*
download.)
(`CHECK_ITEM|key|name|from|to` carries one changed package for the `--check` preview
panel; `SIZE|key|download` carries the on-demand download-size figure from `--size=<step>`;
`FREED|cache|human` carries the disk the cache clean reclaimed (measured before/after
`zypper clean --all`), which the GUI shows as the cache row's "Reclaimed 1.4G" badge;
`AUTH|on|off` reports whether the opt-in passwordless-authorization drop-in is active, for
the engine's `--grant-auth` / `--revoke-auth` / `--auth-status` actions; `REMEDY|import-keys`
signals a one-click GUI fix for a failure — a rotated/expired repo signing key — which the
warn banner offers as "Import signing key & retry", re-running the engine with `--import-keys`
after a warned confirmation. `REPO_SKIPPED|alias|reason` reports a source set aside for this
run — via the `--skip-repo=<alias>` flag (repeatable) or `--auto-skip-repos` unattended
auto-detection — and `REMEDY|skip-repo|alias` offers the matching "Skip <source> & update the
rest" retry.) (`SNAPSHOT_ITEM|id|date|description` enumerates one recent Btrfs restore point
for the GUI's rollback **picker** — the engine emits up to the 12 newest (skipping snapshot 0,
the live "current" entry) alongside the singular pre-update `SNAPSHOT|id`, so `Updater.rollback`
can offer `RollbackDialog` to roll back to a chosen older snapshot, not just the last one
(ONEUP-0020). The GUI validates the id is a bare number before it reaches the root `snapper
rollback`; date/description are display-only.) (Note the plural `SNAPSHOTS` marker is distinct
from the singular `SNAPSHOT|id` rollback-target one: `SNAPSHOTS|warn|count` is a pre-flight
advisory that a lot of Btrfs
restore points have piled up and may be using disk — the GUI's warn banner offers a "Thin
snapshots…" button that re-runs the engine with `--thin-snapshots`; `SNAPSHOTS|thinned|removed`
reports how many that guarded `snapper cleanup number/timeline` pass removed. Threshold:
`SNAP_WARN_COUNT` in the engine.) (`INSTALLED|count|sys_changed|fw_changed`
carries the change summary the GUI uses to decide the reboot/rollback banners;
`REBOOT|yes|no[|reason]` carries an optional third field naming why a reboot is
advised — e.g. `yes|a new kernel and your NVIDIA graphics driver were installed`,
built by the engine from the system transaction log (kernel / graphics-driver /
DKMS-module names); the GUI shows it verbatim in the reboot banner, falling back
to the generic wording when the field is absent;
`TIMING|key|seconds` carries each step's duration, appended to its row badge.)

Step keys (the run order, shared by both files): `system, flatpak, firmware, orphans, cache`.
In `updater.py` they live in the `TASKS` list; in `update_system.sh` in the `LABEL` map.

### Correctness invariants the tests lock in

The test suite exists mainly to protect a specific class of bug — **a step must never claim
success or advise a reboot it didn't earn.** When editing engine logic, preserve these:

- Reboot advice (`@@REBOOT@@|yes`) fires **only** when something was actually installed **or**
  `zypper needs-rebooting` explicitly says so — never merely because a step errored.
- A **failed** step is recorded, emits a plain-English `@@HINT@@`, and the run **continues**
  to the next step (so cache cleanup still happens and the summary is useful).
- A package-only change (no kernel/core update) offers a **service restart** (`@@SERVICES@@`),
  not a reboot.
- `--check` mode is strictly read-only, runs **without root**, and must never call
  `zypper dup`/`update` (the test mock exits 99 if it does).

The tests build a throwaway `PATH` of mock tools (`zypper`, `flatpak`, `sudo`, `snapper`, …)
so the real machine is never touched — no root, no network. Add a regression test here for
any engine behaviour change.

## Packaging & versioning

Three distribution paths:

- **AppImage** — `packaging/appimage/build-appimage.sh`, built and attached to each release
  by the `v*`-tag GitHub workflow in `.github/workflows/release.yml`.
- **RPM** — `packaging/rpm/oneup.spec` (`BuildArch: noarch`).
- **OBS** (openSUSE Build Service) — `packaging/obs/` hosts a `zypper`-installable repo.
  `_service` clones the repo and rolls the tarball `oneup.spec`'s `Source0` expects; see
  `packaging/obs/README.md` for the `osc` publish flow.

App ID is `za.co.antsprojectshub.OneUp` — the desktop file, SVG icon, and AppStream metainfo
under `data/` all use it.

**The version lives in six places that must stay in lockstep** on a release:

1. `APP_VERSION` in `updater.py` (~line 59) — the GUI reads this to self-check for newer
   GitHub releases.
2. `Version:` in `packaging/rpm/oneup.spec`
3. the `%changelog` stanza in `packaging/rpm/oneup.spec` (rpmlint rejects a `Version:` that
   doesn't match the newest `%changelog` entry).
4. `versionformat` **and** `revision` (the release tag, e.g. `v1.0.0`) in `packaging/obs/_service`.
   The `revision` is pinned to the tag on purpose — leaving it on `main` would repackage
   post-release commits under the old version number.
5. the newest `<release version="…">` in `data/za.co.antsprojectshub.OneUp.metainfo.xml`
6. the newest `## [x.y.z]` heading (and its link at the bottom) in `CHANGELOG.md`

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/); the metainfo
`<release>` notes should mirror its entries. **Don't hand-edit the six sites** — run
`./bump.py X.Y.Z` (it rewrites all six, deriving the spec/metainfo notes from the CHANGELOG
`## [Unreleased]` bullets), or `./release.sh X.Y.Z` for the whole release: bump → `./local-CI.sh`
→ commit + tag + push to GitHub (builds the AppImage) → update the OBS package via `osc`
(rebuilds the `zypper` RPM). `local-CI.sh`'s version-lockstep gate fails a push if any site drifts.

Dependency policy (CI actions, runtimes, PySide6, base images) is a standing rule — see
`docs/standards/dependencies.md`, which also carries the known-incompatibility ledger.

## Conventions specific to this repo

- **Privileged commands** in the engine go through `ASKPASS=/usr/libexec/ssh/ksshaskpass`
  (`sudo -A`), never bare `sudo` — this raises the KDE graphical prompt instead of blocking
  on stdin. Match that pattern for any new privileged call.
- Steps for absent tools (`flatpak`, `fwupd`) are **skipped cleanly**, not errored — keep
  new steps tolerant of a missing binary.
- Runtime state lives in `~/.local/state/oneup/` (`history.json`, `logs/`); the engine also
  mirrors each run's log to `~/Documents/update-logs/`. Two files there are a **contract
  between the GUI and the engine**, so moving either means changing both files:
  `run.state` (pid, log path, steps — written when a run commits, cleared on exit; lets a
  window that opens mid-run find and follow that run) and `stop.request` (the GUI creates
  it to ask for a stop). Both are overridable via `ONEUP_RUN_STATE` / `ONEUP_STOP_FILE` so
  tests never touch the real ones.
- **Stopping is cooperative, and that's a safety decision.** The engine looks for
  `stop.request` only at safe boundaries — between steps, and after the repo refresh but
  *before* a transaction starts — then skips the remaining steps and still prints its
  summary, so the user sees what did happen. **Never signal the engine to stop a
  transaction**: SIGTERM mid-`zypper dup` either leaves rpm half-applied or orphans a zypper
  that carries on regardless — see ONEUP-0039/0042 for what that cost in practice. A request
  older than `run.state` is a leftover and is ignored; staleness is judged by mtime rather
  than by deleting the file at startup, because deleting would swallow a stop clicked a
  moment earlier. A stopped run reports `@@DONE@@|stopped` and the GUI claims neither
  success nor failure.
- **`.roadmap-counter` is deliberately git-ignored** — it is local allocator state, and
  tracking a one-line counter means every branch that allocates a roadmap ID conflicts on
  it. `ROADMAP.md` is the real record. On a fresh clone the file is absent, and appending a
  bullet refuses (rather than restarting IDs at 1, so a collision is impossible); recreate
  it with the one-liner documented in `.gitignore`.
- **Accessibility is a standing requirement (ONEUP-0028).** Any new interactive widget
  needs an accessible name (`setAccessibleName`) — `tests/gui-smoke.py` sweeps every
  focusable widget and fails on a nameless one. **State must never be signalled by
  colour alone**: pair every colour cue with text or a shape. Font sizes in the QSS are
  derived from the desktop's default point size (never hard-coded `px`) so text scales.
  Note the app deliberately draws **no focus ring** (a user-facing design decision,
  2026-07-25) — focus reuses the hover look. That rule is about **focus** highlighting
  only: ordinary borders are fine, and the testable form is *focus changes colour or fill,
  never the box model*. The full rules — names, colour-never-alone, scaling, focus,
  dialogs, themes and right-to-left — are `docs/standards/ui-and-accessibility.md`;
  `docs/specs/ONEUP-0028-accessibility.md` is the record of why and how each is tested.
- **Privileged calls must stay out of subshells — capture with `sudo_capture`.** With no
  terminal (the GUI runs the engine through `QProcess`) sudo keys its cached credential to
  the **parent process id** (`sudoers(5)` `timestamp_type`), and bash forks a real subshell
  for `$(cmd | other)`, `$(a; b)`, `$(cmd "$(nested)")` and `< <(cmd | other)` — so a `sudo`
  inside one authenticates *again*, i.e. another password popup. Measured, not assumed: a
  full run once needed seven. Use `sudo_capture [-e] VAR cmd …` (writes to a temp file we
  own, no subshell) and do the text processing on the captured text — `awk … <<<"$VAR"` —
  never in a pipeline wrapped around `sudo`. A *top-level* `sudo … | tee` is fine (sudo stays
  the caller's child), which is how `run_system_upgrade` streams. The regression test models
  sudo's per-parent-pid credential cache and fails if a run needs more than one prompt.
  `SUDO_ASKPASS`/`SUDO_PROMPT` are exported so any prompt is graphical and labelled as
  OneUp's.
- **Anything the engine spawns must not outlive it.** `cleanup`'s trap can't run when the
  engine is SIGKILLed, so the sudo keep-alive also watches the engine's pid and exits on its
  own; it's tagged `oneup-keepalive` in `$0` so tests can find it. Before this, an interrupted
  run left a loop validating sudo every 50 seconds indefinitely. Same reasoning applies to any
  new background helper.
- **A run must survive the GUI going away, and never be interrupted mid-transaction.** The
  engine's stdout is a pipe to the GUI, so the logging `exec` uses `tee -a -p`
  (`--output-error=warn-nopipe`) — without it, a quit kills `tee`, then SIGPIPEs the engine on
  its next line, so `cleanup` never runs and zypper is left orphaned half-way through an rpm
  transaction (which can leave packages broken, and whose abandoned lock blocks the next run).
  `-p` is probed, not assumed, and a `PIPE` trap is the fallback. Correspondingly the GUI
  **warns before quitting during a run** (`Updater._confirm_quit`) and tells the user it
  finishes in the background — so never add a code path that kills the engine mid-run.
  Closing to the tray is not a quit and needs no warning.
- **A slow server must never be indistinguishable from a hang (ONEUP-0048).** Measured, not
  assumed: one mirror served an 18 MB repository index at **930 B/s** and another 86 MB of
  packages at **~18 KB/s**, and through both the app showed nothing whatever — zypper prints
  the metadata fetch as dots with no line ending (so there is no complete line to draw) and
  its package prefetch as one line per *finished* package (ten minutes apart at that speed).
  Three defences, and all three are needed: the engine refreshes **one repository at a time**
  under `sudo timeout "$REFRESH_TIMEOUT"` (as root, so it can actually kill its own zypper
  child) and offers the existing `REMEDY|skip-repo` when it gives up; the GUI keeps a
  **liveness line** under the progress bar (`Updater._tick_activity`) showing what is being
  waited on, for how long, the size and the rate; and its stall clock is stamped on the raw
  **chunk** in `on_output`, before any line splitting, because during a metadata fetch a
  partial line is the only proof of life there is. When zypper reports no byte figures, the
  GUI weighs `/var/cache/zypp/packages` against a baseline taken at run start — it is
  world-readable, so no root is involved, and already-cached packages stay inside the
  baseline rather than flattering the rate.
- **A test must never depend on, or damage, the state of the machine it runs on.** `run_engine`
  redirects `ONEUP_ZYPP_PID_FILE`, `ONEUP_RUN_STATE` and `ONEUP_STOP_FILE` into the mock dir
  unless the scenario sets them itself. Both defaults bit for real: the lock probe reads
  `/run/zypp.pid`, so **40 tests failed merely because the machine happened to be running
  zypper** — precisely when someone is working on an update tool; and `run.state` defaults to
  the user's own, which `cleanup` deletes as its owner, so running the suite during a real
  update **deleted that run's record** and the window could no longer follow it (ONEUP-0045).
  A new scenario that invokes the engine directly rather than through `run_engine` must repeat
  those overrides by hand.
