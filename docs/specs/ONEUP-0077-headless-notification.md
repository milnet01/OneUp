# ONEUP-0077 — the window builds the timer notification

**Status:** Draft
**Kind:** implement
**Roadmap:** ONEUP-0077
**Branch:** v2
**Verified at:** `d18fbf2` — every claim naming a symbol below was resolved against this
tree, not recalled.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** The two headless entry points stop passing `--notify` and the window
composes the desktop notification itself — which is also where the stopped-run defect gets
fixed, because it is the same four-case fall-through.

**Split out of `docs/specs/ONEUP-0072-marker-codes.md` on 2026-08-03**, on the user's
decision. That item keeps the payload conversion; this one takes the notification. §11
carries the provenance row.

## 1. Goal

A weekly timer's notification is built by the half of the application that owns wording, from
the markers a run already emits, and it tells the truth about a run the user stopped. After
this, no user-facing sentence is composed on the root-privileged side of the boundary except
the engine's own terminal output.

## 2. Background

**The engine writes this notification today, and it is the last user-facing sentence it
composes for the window's benefit.** `update_system.sh`'s end-of-run block falls through four
cases — errors, a non-zero installed count, either changed flag, else *"Already up to
date"* — and `notify_send` raises it. The `--check` path has its own, fired only when the
total is above zero.

**It is wrong about a stopped run, and the engine already knows better twenty lines
earlier.** `marker DONE "stopped"` is emitted when `STOP_HONOURED` is true, deliberately
claiming neither success nor failure. The notification block below it has no stopped branch,
so an interrupted run that installed nothing announces *"Already up to date"*. Filed as
**ONEUP-0074**; `docs/specs/ONEUP-0072-marker-codes.md` §3.2 forbade that item repairing it,
because its gate was that behaviour did not change. This item is rebuilding the same
fall-through, so the branch is written once here rather than twice.

**Neither headless path can name a log file today.** They are the only engine runs the
window starts without `--log=`; every other call site passes one. Left alone the engine picks
`$HOME/Documents/update-logs/` and a timestamped name — a *different directory* from the
window's own `LOG_DIR` — so the failed-run text cannot name a file the window never chose.

**Neither path reads the engine's output at all.** Both run it and read only its exit status.
Capturing markers is new work this item adds, not existing behaviour it reuses.

## 3. Scope decisions

- **The engine keeps its `--notify` flag.** Somebody running `oneup --update` in a terminal
  still gets the notification; it is part of that tool's own English output, which
  `docs/standards/wording-and-translation.md` §5 keeps in English. What changes is that the
  two headless paths stop using it. The retained Bash `update_system.sh` is frozen and keeps
  everything it has.
- **No systemd unit changes and none needs regenerating.** `--notify` is not in either
  unit — `ExecStart` is `oneup --check` or `oneup --update`, and the flag is added afterwards
  inside the two entry points. What changes is the argument list those two functions build.
- **The stopped-run wording is settled here, not carried across.** This item is not a
  behaviour-preserving conversion, which is exactly why ONEUP-0072 could not fix it.

## 4. Design

### 4.1 What the window builds, and from which markers

**The headless paths stop passing `--notify`, and the window sends the notification.** The
flag is not in either systemd unit — the unit's `ExecStart` is `oneup --check` or
`oneup --update`, and `--notify` is added afterwards, inside the two headless entry points
that shell out to the engine. So no installed unit changes and none needs regenerating; what
changes is the argument list those two functions build. **The Python engine keeps its
`--notify` flag** for somebody running it in a terminal, where the notification is part of
its own English output (§10) — as does the retained Bash `update_system.sh`, which is frozen
and keeps everything it has.

**The markers it needs are not the ones a run's progress uses.** The engine's own
notification is built from the error count, the installed-package count, the two
system/firmware changed flags, and the set-aside sources — so the window reads `@@CHECK@@`
(the `--check` path's totals), `@@INSTALLED@@` (the count and both flags), `@@REPO_SKIPPED@@`
(each source set aside, which the engine's own comment calls the only place an unattended
run reports what it skipped) and `@@DONE@@` (the verdict). `@@STEP_END@@` is not among them.

**The failed-run notification names the log file, and neither path knows that name today —
so both start passing `--log=`.** They are the only engine runs the window starts without
one: `_tray_check_args` passes `--log=`, the auth, thin and size calls all pass `--log=`, and
these two do not. Left alone, the engine picks its own — `$HOME/Documents/update-logs/` and a
timestamped filename, a *different directory* from the window's own `LOG_DIR` — so the
window cannot name in a sentence a file it never chose. Each path chooses the path it already
would have and hands it over, which is existing practice everywhere else in the window.

**Both entry points must therefore capture the engine's output**, which today they do not —
they run it and read only its exit status. Reading the markers is new work this item adds,
not existing behaviour it reuses.

**The firing rules come across with the text, because they are not in the markers.** The
engine does not notify on every run, and an implementer rebuilding only the wording would
change behaviour by accident:

- The `--check` notification fires **only when the total is above zero**. Without that a
  timer would pop *"0 update(s) ready to install"* every week.
- The end-of-run notification **always** fires, and picks one of four texts by falling
  through: errors, then a non-zero installed count, then either changed flag, then
  *"Already up to date"*.
- A **stopped** run takes that same fall-through today — `@@DONE@@|stopped` with no errors
  and nothing installed notifies *"Already up to date"*, which is wrong about a run the user
  interrupted. **Carry it across unchanged.** §3.2 forbids this item rewording anything, and
  a wrong sentence is still a sentence to be moved, not repaired, in a conversion whose gate
  is that behaviour did not change. It is a real defect and it now has somewhere to go
  (§10).

**The notification must be raisable without a display**, because a timer may have no
display. So a tray message is not available to these two paths: they raise it the same way
the engine does today, through the desktop's notification service, and build its text
through the same tables as everything else.

**This item needs no application object, which is what makes landing first cheap.** Nothing
on either headless path touches Qt: the sentences they render are ordinary Python tables
until ONEUP-0032 marks them, and the notification is `notify-send` — the same subprocess
`notify_send` in `update_system.sh` calls today, invoked with the same `-a`/`-i` arguments so
it carries the app's name and icon. What ONEUP-0032 adds later is a `QCoreApplication` on
both paths, because `QCoreApplication.translate` refuses without an instance and `main`
dispatches `--check` and `--update` before one is built; that spec's §2.2 measured it and its
§4.2 owns it. So the dependency runs **this item → ONEUP-0032**, matching the order §3.3
settles: this item is what puts sentence-rendering on a headless path at all.

## 5. Correctness invariants

- **INV-1** A run the user stopped never notifies that the system was already up to date.
  *Test:* a scenario in `tests/run-tests.sh` stops a run at a step boundary and asserts the
  notification text is neither *"Already up to date"* nor *"Update complete"*. Breaks on
  today's behaviour, where `@@DONE@@|stopped` with no errors and nothing installed falls
  through to the up-to-date branch.

- **INV-2** Neither headless entry point passes `--notify`, and both pass `--log=`.
  *Test:* `tests/gui-smoke.py` asserts on the argv each path builds. Breaks if a path is
  added later that inherits the old argument list — which is how both came to lack `--log=`.

- **INV-3** The `--check` notification fires only when the total is above zero.
  *Test:* the same scenario set, driving a check that finds nothing and asserting no
  notification is raised. Breaks the moment the firing rule is rebuilt from the markers
  alone, because the markers do not carry it — a timer would then announce *"0 update(s)
  ready to install"* every week.

- **INV-4** The notification is raised without a display, through the desktop notification
  service, never as a tray message.
  *Test:* `tests/gui-smoke.py` runs both paths against the mock `notify-send` already on the
  suite's PATH and asserts it was called. Breaks if the implementation reaches for the tray,
  which a timer may have no display for.

- **INV-5** No `QCoreApplication` is required on either headless path.
  *Test:* `tests/gui-smoke.py` invokes both paths with no application instance built and
  asserts neither raises. Breaks if the sentence tables are marked for translation here
  rather than in `ONEUP-0032` — `QCoreApplication.translate` refuses without an instance,
  and that spec's §4.2 owns adding one.

## 6. Failure modes

- **The engine emits a marker the window has no entry for.** `ONEUP-0072` §4.3's
  unknown-code rule applies unchanged; the notification degrades to something readable rather
  than raising inside a headless path with nobody watching.
- **The engine produces no `@@DONE@@` at all** — killed, or the machine lost power. The path
  has an exit status and no verdict, and reports errors rather than success, matching
  `docs/reference/marker-protocol.md` §4 on a followed run.
- **`notify-send` is absent.** The same tolerance every optional tool gets: the run is not
  failed by a missing notifier.

## 7. Tests

| Invariant | Where | What it does |
| --- | --- | --- |
| INV-1, INV-3 | `tests/run-tests.sh` | drives the engine to each outcome and asserts the notification text |
| INV-2, INV-4, INV-5 | `tests/gui-smoke.py` | asserts the argv both paths build, and runs them against the mock `notify-send` |

## 8. Docs & release

- **`docs/specs/ONEUP-0072-marker-codes.md`** loses §4.4 and the §10 bullet that filed this
  defect; its §8 keeps the reference-section edits that belong to the conversion.
- **`docs/specs/ONEUP-0032-i18n.md`** says ONEUP-0072 *"builds the sentence tables and puts
  sentence-rendering on the two headless paths"*. The second half is this item's, and its
  §4.2's `QCoreApplication` note now depends on this item rather than on 0072.
- **`ROADMAP.md`** — ONEUP-0074 is folded in here and flipped when this lands.
- **`CHANGELOG.md`** gains an `[Unreleased]` entry under **Fixed** for the stopped-run text.

## 9. Alternatives considered (and rejected)

- **Leave the notification with the engine and fix only the stopped branch.** Cheaper today
  and it keeps a user-facing sentence on the root-privileged side, which `oneup-2.0.md` §5.1
  exists to end. It would also have to be undone by `ONEUP-0032`.
- **Fix the stopped-run text inside ONEUP-0072.** Forbidden by that spec's §3.2: its gate is
  that behaviour did not change, and a conversion that also repairs a sentence cannot be
  checked against that gate.
- **Have the engine emit a notification *code* the window renders.** Neat, and it adds a
  marker to a contract frozen for 2.0 for something the window can already derive from four
  markers it reads.

## 10. Out of scope

- **The payload conversion itself.** `docs/specs/ONEUP-0072-marker-codes.md`.
- **Translating any of this.** `ONEUP-0032`, last.
- **The engine's own terminal notification.** Stays English with the rest of its output.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 0-split | 2026-08-03 | — | **Provenance, not a review — no reviewer was dispatched to produce this row.** Split out of `docs/specs/ONEUP-0072-marker-codes.md` on 2026-08-03 on the user's decision, taking that document's §4.4. The parent had run three cold-eyes loops (24, 22, 20 verified) and **converged by cap rather than clean** at 654 lines; its §11 recommended splitting §4.4 rather than a fourth loop, and both of loop 3's criticals landed in §4.4 or the ordering paragraph beside it. **Those loops were run against a document that no longer exists, so none of their assurance transfers**: this spec runs the gate from loop 1 on its own bytes. The invariants here are new — the parent's INV-1…INV-5 are all about codes and stay with it — and **ONEUP-0074 is folded in** rather than left filed, because this item rebuilds the four-case fall-through that defect lives in. |
