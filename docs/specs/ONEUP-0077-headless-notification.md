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
fixed, because it is the same fall-through being rebuilt.

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

**It is wrong about a stopped run, and the engine already knows better in the verdict block
just above it.** `marker DONE "stopped"` is emitted when `STOP_HONOURED` is true, deliberately
claiming neither success nor failure. The notification block below it has no stopped branch,
so an interrupted run that installed nothing announces *"Already up to date"*. Filed as
**ONEUP-0074**; `docs/specs/ONEUP-0072-marker-codes.md` §3.2 forbade that item repairing it,
because its gate was that behaviour did not change. This item is rebuilding the same
fall-through, so the branch is written once here rather than twice.

**Neither headless path can name a log file today, and neither reads the engine's output at
all.** They are the only engine runs the window starts without `--log=`, and both call
`subprocess.run` on the engine and read nothing but its exit status. §4 states what each of
those costs and what replaces it.

## 3. Scope decisions

- **The engine keeps its `--notify` flag.** Somebody running the engine directly —
  `./update_system.sh --notify`, or the Python engine's own CLI — still gets it, because it
  is part of that tool's own English output, which
  `docs/standards/wording-and-translation.md` §5 keeps in English. **`oneup --update` is not
  that case**: it is one of the two headless paths, so after this item it gets the
  window-built notification like `oneup --check` does. The retained Bash `update_system.sh`
  is frozen and keeps everything it has.
- **No systemd unit changes and none needs regenerating.** `--notify` is not in either
  unit — `ExecStart` is `oneup --check` or `oneup --update`, and the flag is added afterwards
  inside the two entry points. What changes is the argument list those two functions build.
- **The stopped-run wording is settled here, not carried across.** This item is not a
  behaviour-preserving conversion, which is exactly why ONEUP-0072 could not fix it.
- **This item lands after `ONEUP-0072` and before `ONEUP-0032`.** It renders its sentences
  through the marker tables 0072 builds (`oneup/gui/markers.py`, that spec's §4.3), so 0072
  is a precondition; and it is what puts sentence-rendering on a headless path at all, which
  is what 0032 then marks for translation. So the tail of `docs/design/oneup-2.0.md` §5.2's
  order runs **0054 → 0072 → 0077 → 0032**; that section owns the order of work and §8
  places this item in it, which it does not do today.

## 4. Design — what the window builds, and from which markers

**The headless paths stop passing `--notify`, and the window sends the notification.** It is
built in `oneup/gui/markers.py`, beside the tables `ONEUP-0072` §4.3 puts there, and raised
by the two entry points in `oneup/gui/app.py`. The exact argument list each builds after this
item is:

| Entry point | Engine argv today | After this item |
| --- | --- | --- |
| `oneup --check` | `--check --notify` | `--check --log=<LOG_DIR>/<stamp>.check.log` |
| `oneup --update` | `--notify --auto-skip-repos` | `--auto-skip-repos --log=<LOG_DIR>/<stamp>.log` |

`--auto-skip-repos` stays: an unattended run sets a single broken source aside and finishes
the rest, and it is what produces the `@@REPO_SKIPPED@@` lines the notification reports.

**The markers it needs are not the ones a run's progress uses.** The window reads `@@CHECK@@`
(the `--check` path's totals) and `@@CHECK_UNKNOWN@@` (a source that could not be read),
`@@INSTALLED@@` (the installed count and both changed flags), `@@REPO_SKIPPED@@` (each source
set aside, which the engine's own comment calls the only place an unattended run reports what
it skipped) and `@@DONE@@` (the verdict — including which of `ok`, `errors` and `stopped` it
was, since no marker carries an error *count* and none needs to: the failure text names the
log, not a number). `@@STEP_END@@` is not among them.

**A check that could not read a source never announces an all-clear.** `@@CHECK_UNKNOWN@@`
makes the total a floor rather than an answer (`docs/reference/marker-protocol.md` §4.6), so
the zero-total silence INV-3 requires is wrong in exactly that case — it is the ONEUP-0056
shape, reported as *"couldn't check everything"* with the unreadable sources named, not as
silence and not as *"up to date"*.

**The failed-run notification names the log file, and neither path knows that name today —
so both start passing `--log=`.** They are the only engine runs the window starts without
one: `_tray_check_args` passes `--log=`, the auth, thin and size calls all pass `--log=`, and
these two do not. Left alone, the engine picks its own — `$HOME/Documents/update-logs/` and a
timestamped filename, a *different directory* from the window's own `LOG_DIR` — so the
window cannot name in a sentence a file it never chose. Each path chooses the path it already
would have and hands it over, which is existing practice everywhere else in the window.

**Both entry points must therefore capture the engine's output**, which today they do not —
`subprocess.run` inherits stdout, so a terminal user and the systemd journal see the run go
past. **Capturing must not end that.** Each path reads the engine's stdout **line by line**
and writes every line straight back out, keeping only the handful of marker fields the
notification needs; nothing buffers a whole `zypper dup` transcript in memory, and the
journal keeps the record it has today. Reading the markers is new work this item adds, not
existing behaviour it reuses.

**The firing rules come across with the text, because they are not in the markers.** The
engine does not notify on every run, and an implementer rebuilding only the wording would
change behaviour by accident:

- The `--check` notification fires **only when the total is above zero**. Without that a
  timer would pop *"0 update(s) ready to install"* every week.
- The end-of-run notification **always** fires, and picks its text by falling through:
  errors, then a non-zero installed count, then either changed flag, then *"Already up to
  date"*. The window rebuilds those four and inserts a fifth, below.
- The engine appends the set-aside sources to **three** of those four texts, not to the
  failure one — the notification is the only place an unattended run reports what it
  skipped. The window keeps that placement.
- A **stopped** run takes that same fall-through today — `@@DONE@@|stopped` with no errors
  and nothing installed notifies *"Already up to date"*, which is wrong about a run the user
  interrupted. **This item adds the branch that is missing**, ahead of the up-to-date case:
  `@@DONE@@|stopped` claims neither success nor failure, exactly as
  `docs/reference/marker-protocol.md` §4.9 requires of the window, and says what did happen —
  the run was stopped and the steps that ran are in the log. This is the ONEUP-0074 fix, and
  it is why this item is not a behaviour-preserving conversion (§3).

**The notification must be raisable without a display**, because a timer may have no
display. So a tray message is not available to these two paths: they raise it the same way
the engine does today, through the desktop's notification service, and build its text
through the same tables as everything else.

**This item needs no application object, which is what makes it cheap to land ahead of
translation.** Nothing
on either headless path touches Qt: the sentences they render are ordinary Python tables
until ONEUP-0032 marks them, and the notification is `notify-send` — the same subprocess
`notify_send` in `update_system.sh` calls today, invoked with the same `-a`/`-i` arguments so
it carries the app's name and icon. What ONEUP-0032 adds later is a `QCoreApplication` on
both paths, because `QCoreApplication.translate` refuses without an instance and `main`
dispatches `--check` and `--update` before one is built; that spec's §2.2 measured it and its
§4.2 owns it. So the dependency runs **this item → ONEUP-0032**, matching the slot §3 fixes:
this item is what puts sentence-rendering on a headless path at all.

## 5. Correctness invariants

The suite is `tests/gui-smoke.py` throughout, because after this item the **window** composes
every sentence below. `tests/run-tests.sh` drives the engine, whose own `--notify` output
this item does not touch (§10), so it cannot assert any of these.

- **INV-1** A headless run the user stopped never notifies that the system was already up to
  date.
  *Test:* `tests/gui-smoke.py` feeds the update path a mock engine emitting
  `@@DONE@@|stopped` with no errors and nothing installed, and asserts the recorded
  `notify-send` title is neither *"Already up to date"* nor *"Update complete"*. Breaks on
  today's behaviour, where that case falls through to the up-to-date branch.

- **INV-2** Each headless entry point builds exactly the argv §4 tabulates — no `--notify`,
  a `--log=` under the window's own `LOG_DIR`, and `--auto-skip-repos` still on the update
  path.
  *Test:* `tests/gui-smoke.py` asserts on the argv each path builds, field by field. Breaks
  if a path is added later that inherits an older argument list, and breaks if
  `--auto-skip-repos` is dropped — which would silently empty the set-aside report.

- **INV-3** The `--check` notification fires only when the total is above zero **and every
  source was readable**; an unreadable source is reported rather than swallowed.
  *Test:* `tests/gui-smoke.py` drives the check path twice against a mock engine — once
  emitting `@@CHECK@@|TOTAL|0|…` alone and asserting no `notify-send` call, once emitting
  `@@CHECK_UNKNOWN@@` with a zero total and asserting a call naming the unreadable source.
  Breaks the moment the firing rule is rebuilt from the markers alone: a timer would announce
  *"0 update(s) ready to install"* every week, or go silent on a broken repository, which is
  ONEUP-0056.

- **INV-4** The notification is raised without a display, through the desktop notification
  service, never as a tray message.
  *Test:* `tests/gui-smoke.py` runs both paths against the mock `notify-send` already on the
  suite's PATH, asserts it recorded a call, and asserts no `QSystemTrayIcon` was constructed
  on either path. The engine is a mock on both, so no real update runs
  (`docs/standards/testing.md` §2). Breaks if the implementation reaches for the tray, which
  a timer may have no display for.

- **INV-5** No `QCoreApplication` is required on either headless path.
  *Test:* `tests/gui-smoke.py` runs each entry point in a **subprocess** with no Qt
  application constructed, and asserts it exits cleanly and records its `notify-send` call.
  It must be a subprocess: the suite builds its own application at import
  (`QApplication.instance() or QApplication([])`), so an in-process call would pass while
  proving nothing. Breaks if the sentence tables are marked for translation here rather than
  in `ONEUP-0032` — `QCoreApplication.translate` refuses without an instance, and that spec's
  §4.2 owns adding one.

## 6. Failure modes

- **The engine emits a marker the window has no entry for.** `ONEUP-0072` §4.3's
  unknown-code rule applies unchanged; the notification degrades to something readable rather
  than raising inside a headless path with nobody watching.
- **The engine produces no `@@DONE@@` at all** — killed, or the machine lost power. Unlike a
  *followed* run, a headless path has the engine's **exit status**, which
  `docs/reference/marker-protocol.md` §4.9 makes the normal authority with `@@DONE@@` as
  belt-and-braces. So the verdict comes from the exit status; a non-zero one with no verdict
  reports errors, and a zero one with no verdict also reports errors rather than success,
  because a run that ended without saying so did not finish.
- **`notify-send` is absent.** The same tolerance every optional tool gets: the run is not
  failed by a missing notifier.

## 7. Tests

Every invariant here is checked in `tests/gui-smoke.py`, because the window is what composes
the sentence after this item. The engine suite is not involved: `update_system.sh`'s own
`--notify` output is unchanged and out of scope (§10).

| Invariant | What the case does |
| --- | --- |
| INV-1 | mock engine emits `@@DONE@@\|stopped`; asserts the recorded title is neither *"Already up to date"* nor *"Update complete"* |
| INV-2 | asserts each path's argv field by field against §4's table |
| INV-3 | drives the check path twice — zero total alone, then zero total with `@@CHECK_UNKNOWN@@` — and asserts silence, then a call naming the source |
| INV-4 | asserts the mock `notify-send` recorded a call and that no `QSystemTrayIcon` was constructed |
| INV-5 | runs each entry point in a subprocess with no Qt application built |

## 8. Docs & release

**All of it lands on `v2` with the code**, for the reason `ONEUP-0072` §8 gives: a reference
amended on `main` would describe a contract the 1.4.0 engine `main` still ships does not
implement.

- **`docs/reference/marker-protocol.md`** — **§2's reading-order table**, which opens *"Four
  channels use this protocol"* and gains **two**: the two headless paths, which parse a run's
  markers with no window. And **§4.7**, which records `fw_changed` as *"emitted and currently
  unread"* — this item is what reads it. Both edits are **this item's**, in this item's
  commit, per that reference's §5; `ONEUP-0072` §8 currently lists them and gives them up.
- **`docs/design/oneup-2.0.md`** — §5.2 credits `ONEUP-0072` with landing "its notification
  check in `tests/gui-smoke.py`" and needing "no application object at all"; that is this
  item's INV-4 and INV-5, and the sentence moves. §5.2's order diagram does not contain this
  item at all and gains it, between the codes and translation (§3).
- **`docs/specs/ONEUP-0072-marker-codes.md`** — its §8 gives up the two
  `marker-protocol.md` edits above and the **two headless entry points** bullet, all of which
  describe work this item does. Its §4.4 and its §10 split bullet already record the split
  correctly and are left alone.
- **`ROADMAP.md`** — ONEUP-0074 is folded in here and flipped when this lands.
- **`CHANGELOG.md`** gains an `[Unreleased]` entry under **Fixed** for the stopped-run text.

## 9. Alternatives considered (and rejected)

- **Leave the notification with the engine and fix only the stopped branch.** Cheaper today
  and it keeps a user-facing sentence on the root-privileged side, which `oneup-2.0.md` §5.1
  exists to end. It would also have to be undone by `ONEUP-0032`.
- **Fix the stopped-run text inside ONEUP-0072.** Forbidden by that spec's §3.2: its gate is
  that behaviour did not change, and a conversion that also repairs a sentence cannot be
  checked against that gate.
- **Have the engine emit a notification *code* the window renders.** Neat, but it adds a
  marker to a contract frozen for 2.0 for something the window can already derive from four
  markers it reads.

## 10. Out of scope

- **The payload conversion itself.** `docs/specs/ONEUP-0072-marker-codes.md`.
- **Translating any of this.** `ONEUP-0032`, last.
- **The engine's own terminal notification.** Stays English with the rest of its output.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-08-03 | 2 lanes; 1 critical, 7 high, 8 medium, 6 low — **21 verified, 1 dismissed** — 21 draft defects vs 0 fix collateral (21 actionable fixed) | The first review of this document on its own bytes, and **both lanes led with the same critical: a paragraph the split carried across unedited.** §4's firing rules still said of the stopped run *"Carry it across unchanged"*, citing a §3.2 that forbids rewording — which is `ONEUP-0072`'s section number, not this document's, whose §3 is a flat bullet list. Its `(§10)` pointed at 0072's out-of-scope bullet, where the defect was filed *to here*. So the most confidently-worded paragraph in the spec instructed the implementer to ship the exact bug the item exists to fix, against §1, §2, §3, INV-1, §8's CHANGELOG-under-Fixed entry and §9. It now states the branch this item adds, per `marker-protocol.md` §4.9. **Three of the five invariants were untestable as written, which is the class that costs most because it surfaces at test-writing time.** INV-1 and INV-3 were assigned to `tests/run-tests.sh` — the engine suite — when this item moves the sentence into the window and leaves the engine's own `--notify` untouched, so those cases could only ever have asserted against text this item does not write. And INV-5 (*no `QCoreApplication` is required*) was to be checked in `tests/gui-smoke.py`, which builds one at import (`QApplication.instance() or QApplication([])`): the assertion would have passed while proving nothing. It is a subprocess now, with the reason recorded beside it. **The most useful finding pair was about ownership, and both halves were real.** `ONEUP-0072` §8 schedules the two `marker-protocol.md` edits this item causes — §4.7's *"emitted and currently unread"* `fw_changed`, and §2's reading-order table gaining the two headless readers — and also claims the entry-point argument changes outright; `docs/design/oneup-2.0.md` §5.2 credits 0072 with landing "its notification check in `tests/gui-smoke.py`" and needing "no application object at all", which is this item's INV-4 and INV-5 verbatim, in the section that owns the order of work — and never places this item in its diagram at all. All four now sit with this item; 0072 §8 gives them up and the diagram gains a `timer notification (0077)` node between the codes and translation. Smaller draft defects: §3 offered *"somebody running `oneup --update` in a terminal"* as the case that keeps `--notify`, when `oneup --update` **is** one of the two paths INV-2 strips it from; the marker list omitted `@@CHECK_UNKNOWN@@`, so INV-3's zero-total silence would have reproduced ONEUP-0056 on a broken repository; "the error count" is carried by no marker (`@@DONE@@|errors` is the verdict, and the failure text names the log rather than a number); the capture requirement never said the inherited stdout a terminal user and the journal see today must survive it; `--auto-skip-repos` — load-bearing for the `@@REPO_SKIPPED@@` report — was pinned nowhere, so §4 now tabulates both argvs in full; and the module that composes the notification was never named. §6 cited `marker-protocol.md` §4 for a followed-run rule that is §4.9 and turns on there being **no exit code**, which a headless path has. **Dismissed: one.** A lane proposed numbering §3's bullets so the `§3.2`/`§3.3` references would resolve; checked, those references belong to another document entirely, so qualifying them is the fix and numbering §3 would have made two documents' section numbers collide. Two lane open questions resolved in the document's favour and are recorded so a later loop does not re-ask: `tests/gui-smoke.py` does carry a mock `notify-send` on its PATH, and the auth, thin and size calls do all pass `--log=`. The document left this loop at 270 lines, up from 209. |
| 0-split | 2026-08-03 | — | **Provenance, not a review — no reviewer was dispatched to produce this row.** Split out of `docs/specs/ONEUP-0072-marker-codes.md` on 2026-08-03 on the user's decision, taking that document's §4.4. The parent had run three cold-eyes loops (24, 22, 20 verified) and **converged by cap rather than clean** at 654 lines; its §11 recommended splitting §4.4 rather than a fourth loop, and both of loop 3's criticals landed in §4.4 or the ordering paragraph beside it. **Those loops were run against a document that no longer exists, so none of their assurance transfers**: this spec runs the gate from loop 1 on its own bytes. The invariants here are new — the parent's INV-1…INV-5 are all about codes and stay with it — and **ONEUP-0074 is folded in** rather than left filed, because this item rebuilds the four-case fall-through that defect lives in. |
