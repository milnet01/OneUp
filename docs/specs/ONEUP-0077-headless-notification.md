# ONEUP-0077 — the window builds the timer notification

**Status:** Reviewed
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
the engine's own output — its terminal text, the ordinary log lines the window mirrors
verbatim in its log pane, and the `--notify` notification that belongs with them when the
engine is run directly (§3, and `ONEUP-0072` §10).

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
all.** Both call `subprocess.run` on the engine and read nothing but its exit status. §4
states what each of those costs and what replaces it.

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
- **This item lands after `ONEUP-0072` and before `ONEUP-0032`.** 0072 is a precondition
  because `@@CHECK_UNKNOWN@@`'s reason is prose today and a **code** afterwards, and only
  0072's tables turn that code back into the words `check.partial` shows. (`@@REPO_SKIPPED@@`
  carries a reason too, but the notification renders only the aliases — the engine's own
  `skip_note` does the same — so that half is not part of the dependency.) The eight
  notification sentences are **this item's**, in a table of its own beside 0072's (§4); it is
  what puts sentence-rendering on a headless path at all, which is what 0032 then marks for
  translation. So the tail of `docs/design/oneup-2.0.md` §5.2's
  order runs **0054 → 0072 → 0077 → 0032**; that section owns the order of work and now
  carries this item in its diagram (§8).

## 4. Design — what the window builds, and from which markers

**The headless paths stop passing `--notify`, and the window sends the notification.**
*"The window"* throughout this spec means the **GUI half** of the application — the code that
owns wording — not a visible window: neither headless path opens one, and neither touches Qt
at all (below). It is
built in `oneup/gui/markers.py`, in a **notification table of its own**, sitting beside the
per-marker-family tables `docs/specs/ONEUP-0108-window-wording.md` §4.1 puts in the same
module, and raised by the two
entry points in `oneup/gui/app.py`. **The table has eight entries** — the end-of-run
fall-through's five and the check path's three — and every one of them is here, because a
count without the list is what an implementer builds short:

| Key | Path | English |
| --- | --- | --- |
| `run.failed` | update | *Update failed* — one or more steps failed; names the log file |
| `run.installed` | update | *Update complete* — N system package(s) installed |
| `run.changed` | update | *Update complete* — updates were installed |
| `run.stopped` | update | **new** — the run was stopped; the steps that ran are in the log |
| `run.uptodate` | update | *Already up to date* — no updates were needed |
| `check.available` | check | N update(s) ready to install |
| `check.partial` | check | **new** — couldn't check everything; names the unreadable sources |
| `check.partial_count` | check | **new** — N found, and the figure is a floor; names the sources |

The three `run.*` texts that carry one append the set-aside sources; `run.failed` does not,
matching the engine (the firing rules below). The exact wording is the window's to settle under
`docs/standards/wording-and-translation.md`; what is fixed here is that eight cases exist and
which marker state selects each. The exact argument list each path builds is:

| Entry point | Engine argv today | After this item |
| --- | --- | --- |
| `oneup --check` | `--check --notify` | `--check --log=<LOG_DIR>/<stamp>.check.log` |
| `oneup --update` | `--notify --auto-skip-repos` | `--auto-skip-repos --log=<LOG_DIR>/<stamp>.log` |

`--auto-skip-repos` stays: an unattended run sets a single broken source aside and finishes
the rest, and on this path it is what produces the `@@REPO_SKIPPED@@` lines the notification
reports (`--skip-repo=<alias>` produces them too, but no headless path passes one).

**The markers it needs are not the ones a run's progress uses.** The window reads `@@CHECK@@`
(the `--check` path's totals) and `@@CHECK_UNKNOWN@@` (a source that could not be read),
`@@INSTALLED@@` (the installed count and both changed flags), `@@REPO_SKIPPED@@` (each source
set aside; the engine's own comment calls the *notification* the only place an unattended run
reports what it skipped, which is why it survives the move) and `@@DONE@@` (the verdict — including which of `ok`, `errors` and `stopped` it
was, since no marker carries an error *count* and none needs to: the failure text names the
log, not a number). `@@STEP_END@@` is not among them.

**A check that could not read a source never announces an all-clear.** `@@CHECK_UNKNOWN@@`
makes the total a floor rather than an answer (`docs/reference/marker-protocol.md` §4.6), so
the engine's *"fire only above zero"* rule is not sufficient on its own — silence on a broken
repository is the ONEUP-0056 shape. Both cases the engine can produce get a sentence: with a
zero total it reads *"couldn't check everything"* and names the unreadable sources, and with a
non-zero one — which `emit_check` still emits alongside the warning, because knowing about 7
updates beats knowing about none — it gives the count **and** says the figure is a floor. Only
a zero total with every source readable is silent.

**The failed-run notification names the log file, and neither path knows that name today —
so both start passing `--log=`.** They are the only engine runs the window starts without
one: `_tray_check_args` passes `--log=`, the auth, thin and size calls all pass `--log=`, and
these two do not. Left alone, the engine picks its own — `$HOME/Documents/update-logs/` and a
timestamped filename, a *different directory* from the window's own `LOG_DIR` — so the
window cannot name in a sentence a file it never chose. Each path names a file under
`LOG_DIR` and hands it over, which is existing practice everywhere else in the window.
**Both are timestamped rather than rolling**, unlike the tray check's single `traycheck.log`:
a timer run is the one a user comes back to days later and needs a record of, and the tray
check rolls precisely because it repeats far more often. **Nothing deletes from `LOG_DIR`
today.** The window already writes a timestamped log per GUI run (`_launch`), and nothing
prunes them — `_latest_run_log` only reads. So unbounded growth is inherited, not started
here; what this item adds is an *unattended* source of it, roughly 52 files a year that no
one chose to create. Not this item's to fix, and filed as **ONEUP-0082** rather than left to
be discovered.

**Both entry points must therefore capture the engine's output**, which today they do not —
`subprocess.run` inherits stdout, so a terminal user and the systemd journal see the run go
past. **Capturing must not end that.** Each path reads the engine's stdout **line by line**
and writes every line straight back out, keeping only the handful of marker fields the
notification needs; nothing buffers a whole `zypper dup` transcript in memory, and the
journal keeps the record it has today. **stderr stays inherited** — it is not parsed, it
carries no markers, and redirecting it would swallow the engine's own refusals. Reading the markers is new work this item adds, not
existing behaviour it reuses.

**The firing rules come across with the text, because they are not in the markers.** The
engine does not notify on every run, and an implementer rebuilding only the wording would
change behaviour by accident:

- The `--check` notification fires **only when the total is above zero**. Without that a
  timer would pop *"0 update(s) ready to install"* every week. This item keeps that rule and
  widens it by one case, above: an unreadable source fires whatever the total.
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
both paths, because `installTranslator` refuses without an instance and `main`
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
  `notify-send` call is the window's **stopped** entry — the fifth case §4 adds — rather
  than any of the other four. Asserting only that two old English titles are absent would
  pass against any new wording, which is why the case is pinned to the table entry.
  Breaks on today's behaviour, where that case falls through to the up-to-date branch.

- **INV-2** Each headless entry point builds exactly the argv §4 tabulates — no `--notify`,
  a `--log=` under the window's own `LOG_DIR`, and `--auto-skip-repos` still on the update
  path.
  *Test:* `tests/gui-smoke.py` asserts on the argv each path builds, field by field, with
  the `--log=` value matched by pattern (a timestamp cannot be compared literally) and its
  directory asserted to be `LOG_DIR`. Breaks if a path is added later that inherits an older
  argument list is edited, and breaks if `--auto-skip-repos` is dropped — which would
  silently empty the set-aside report. It cannot catch a *third* headless path added later;
  nothing does, and that is worth knowing rather than implying cover.

- **INV-3** The `--check` notification is silent **only** when the total is zero *and* every
  source was readable. It fires when the total is above zero, and it fires on an unreadable
  source whatever the total.
  *Test:* `tests/gui-smoke.py` drives the check path three times against a mock engine —
  `@@CHECK@@|TOTAL|0|…` alone, asserting no `notify-send` call; `@@CHECK_UNKNOWN@@` with a
  zero total, asserting a call naming the unreadable source; and `@@CHECK_UNKNOWN@@`
  alongside a non-zero `@@CHECK@@`, asserting a call that gives the count *and* names the
  source. Breaks the moment the firing rule is rebuilt from the totals alone: a timer would
  announce *"0 update(s) ready to install"* every week, or go silent on a broken repository,
  which is ONEUP-0056.

- **INV-4** The notification is raised without a display, through the desktop notification
  service, never as a tray message.
  *Test:* `tests/gui-smoke.py` runs both paths against the mock `notify-send` already on the
  suite's PATH, asserts it recorded a call, and asserts no `QSystemTrayIcon` was constructed
  on either path. The check path's mock emits a **non-zero** total, or INV-3 makes it
  silent and the assertion is vacuous. The engine is a mock on both, so no real update runs
  (`docs/standards/testing.md` §2). Breaks if the implementation reaches for the tray, which
  a timer may have no display for. (INV-5 makes the stronger claim — no `QCoreApplication`
  at all — so on this item's code it entails this one; they are separate because INV-5 is
  transitional and this one outlives it.)

- **INV-5** *(transitional — `ONEUP-0032` retires it, see §8)* This item requires no
  `QCoreApplication` on either headless path, and constructs none.
  *Test:* `tests/gui-smoke.py` runs each entry point in a **subprocess** with no Qt
  application constructed. `ENGINE` is a module-level constant (`ENGINE = _find_engine()`)
  with **no environment override**, and an in-process patch does not cross `subprocess`, so
  the child gets the mock the way the suite already isolates everything else — by running with
  `HOME` rewritten, which is one of the two paths `_find_engine` searches
  (`docs/standards/testing.md` §2). The case asserts
  it exits cleanly, records its `notify-send` call, and **constructs no `QCoreApplication`
  and installs no translator**. It must be a subprocess: the suite builds its own application
  at import (`QApplication.instance() or QApplication([])`), so an in-process call would pass
  while proving nothing. The child reports the negative itself — it asserts
  `QCoreApplication.instance() is None` and prints a sentinel the parent checks — because
  **asserting only that nothing raised would prove nothing**: `ONEUP-0032` §2.2 measured that
  with no instance `installTranslator` refuses and returns `False` while
  `QCoreApplication.translate` quietly returns the English, so a path wrongly marked for
  translation would still exit cleanly. What breaks the invariant is the construction, not an
  exception. **This invariant is deliberately short-lived**: `ONEUP-0032` §4.2 gives both
  paths a `QCoreApplication`, and retires this check when it does — §8 says so, so the next
  item does not inherit a red suite.

- **INV-6** Capturing the engine's output does not stop it reaching the terminal and the
  journal: every line the engine writes to stdout is written on by the path that read it.
  *Test:* `tests/gui-smoke.py` drives each path against a mock engine emitting known
  **non-marker** lines among the markers, and asserts every one of them appears on the path's
  own stdout, in order. Breaks the moment an implementation reaches for `capture_output=True`,
  which is the natural way to write this and would silently mute `oneup --update` for every
  terminal user and every `journalctl` reader.

- **INV-7** `@@DONE@@` outranks the exit status: a run reporting `stopped` is never reported
  as a success, whatever it exited with.
  *Test:* `tests/gui-smoke.py` drives the update path over the verdict matrix — `@@DONE@@`
  present (`ok`, `errors`, `stopped`) against exit 0 and non-zero, and `@@DONE@@` absent
  against both — and asserts the notification each pair selects. Breaks on an exit-status-first
  reading, which is what `docs/reference/marker-protocol.md` §4.9's headline suggests and what
  would put ONEUP-0074 back: the engine's last statement is `((ERRORS == 0))`, so a stopped run
  exits **zero**.

## 6. Failure modes

- **The engine emits a marker the window has no entry for.**
  `docs/specs/ONEUP-0108-window-wording.md` §4.3's unknown-code rule applies unchanged; the notification degrades to something readable rather
  than raising inside a headless path with nobody watching.
- **The engine produces no `@@DONE@@` at all** — killed, or the machine lost power. Unlike a
  *followed* run, a headless path also has the engine's **exit status**, so the precedence
  has to be written down and it is not the one `docs/reference/marker-protocol.md` §4.9's
  headline suggests: **`@@DONE@@` decides whenever it arrives, and the exit status decides
  only when it does not.** `@@DONE@@` is the sole carrier of `stopped`, and the engine's
  final statement is `((ERRORS == 0))` — so a stopped run exits **zero**, and an
  exit-status-first reading would call it a success and put INV-1 straight back. With no
  `@@DONE@@` at all the path reports errors on either exit status, because a run that ended
  without saying so did not finish.
- **`notify-send` is absent.** The same tolerance every optional tool gets: the run is not
  failed by a missing notifier.

## 7. Tests

Every invariant is checked in **`tests/gui-smoke.py`**, and each one's case is written out in
its own `*Test:*` clause in §5 rather than summarised again here — two statements of the same
case are two that will disagree. The engine suite is not involved: `update_system.sh`'s own
`--notify` output is unchanged and out of scope (§10).

What the suite gains is a **mock engine** the two headless paths can be driven against: a
script emitting a chosen set of markers and exiting with a chosen status, placed where
`_find_engine` resolves — which for this suite means under the rewritten `HOME` it already
uses for isolation, not on `PATH` (`_find_engine` does not search `PATH`). Plus the
subprocess harness INV-5 and INV-6 need. The mock `notify-send` those cases assert against is
already on the suite's PATH.

## 8. Docs & release

**All of it lands on `v2` with the code**, for the reason `ONEUP-0072` §8 gives: a reference
amended on `main` would describe a contract the 1.4.0 engine `main` still ships does not
implement. Two of the edits below were exceptions, and are already made — a spec that claims
ownership of another document's sentence has to take it at the moment it claims it, or the
two disagree until the code lands.

**Already made, with this spec:**

- **`docs/design/oneup-2.0.md`** — §5.2 credited `ONEUP-0072` with landing "its notification
  check in `tests/gui-smoke.py`" and needing "no application object at all", which is this
  item's §7 and INV-5; that sentence now names this item. Its order diagram did not contain
  this item at all and now carries a `timer notification (0077)` node between the codes and
  translation.
- **`docs/specs/ONEUP-0072-marker-codes.md`** — its §8 has given up `marker-protocol.md`
  §4.7, the two headless rows in §2's table, and the **two headless entry points** bullet,
  all of which describe work this item does — the *work*, not the handover bullet, which
  stands. It keeps its own §2 edit (the tray-check row). Its §4.4 is already gone (the split
  took it) and its §10 bullet already records that correctly, so neither was touched.

**Made when the code lands:**

- **`docs/reference/marker-protocol.md`** — **§2's reading-order table**. It lists four
  channels today; `docs/specs/ONEUP-0108-window-wording.md` §8 adds the tray check in the
  ONEUP-0072 landing commit, so by the time this item
  edits it the table reads **five**, and this item takes it to **seven** with the two headless
  paths, which parse a run's markers with no window. And **§4.7**, which records `fw_changed`
  as *"emitted and currently unread"* — this item is what reads it. And **§4.9**, which says
  of the verdict *"the two always agree"*: they do not, for the one case this item turns on —
  a stopped run exits zero while `@@DONE@@` says `stopped` — so §4.9 gains the headless
  reader's precedence beside its followed-run exception (§6, INV-7). All three in this item's
  own commit, per that reference's §5.
- **`docs/specs/ONEUP-0032-i18n.md`** — its §4.2 still sends the reader to *"ONEUP-0072
  §4.4"* for why the headless paths need an application object. That section no longer
  exists: the split took it, and this item is what puts sentence-rendering on those paths.
  The pointer moves here. That spec also **retires INV-5** when it lands, since its §4.2
  gives both paths the `QCoreApplication` INV-5 forbids — recorded here so the next item does
  not inherit a red suite.
- **`ROADMAP.md`** — ONEUP-0074 is folded in here and flipped when this lands. ONEUP-0082
  (nothing prunes `LOG_DIR`, §4) is filed and stays open.
- **`CHANGELOG.md`** gains two `[Unreleased]` entries: one under **Changed** — the timer
  notification is composed by the GUI half rather than the engine, and the headless paths
  stop passing `--notify` — and one under **Fixed**, for the stopped-run text.

## 9. Alternatives considered (and rejected)

- **Leave the notification with the engine and fix only the stopped branch.** Cheaper today
  and it keeps a user-facing sentence on the root-privileged side, which `oneup-2.0.md` §5.1
  exists to end. It would also have to be undone by `ONEUP-0032`.
- **Fix the stopped-run text inside ONEUP-0072.** Forbidden by that spec's §3.2: its gate is
  that behaviour did not change, and a conversion that also repairs a sentence cannot be
  checked against that gate.
- **Have the engine emit a notification *code* the window renders.** Neat, but it adds a
  marker to a contract whose *shape* is frozen for 2.0 — `ONEUP-0072` converts its payloads
  once and adds nothing — for something the window can already derive from five
  markers it reads.

## 10. Out of scope

- **The payload conversion itself.** `docs/specs/ONEUP-0072-marker-codes.md`.
- **Translating any of this.** `ONEUP-0032`, last.
- **The engine's own terminal notification.** Stays with it, and stays English (§3).

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 3 | 2026-08-03 | 2 lanes; 1 critical, 4 high, 6 medium, 7 low, 2 info — **20 verified, 0 dismissed** — 6 draft defects vs 12 fix collateral (18 actionable fixed, 2 info carried) | **Converged by cap, not clean**, and the ratio says why that is the right exit rather than a fourth loop. Nothing from loops 1 or 2 came back. **Both lanes led with the same critical and it was loop 2's arithmetic:** loop 2 pinned the notification table at *"five entries — the four the engine falls through today plus the stopped one this item adds"*, counting only the **end-of-run** family, three sections above the same §4 mandating three `--check` sentences and an INV-3 that tests all three. An implementer builds a five-entry table and has nowhere to put half the item. The count is gone and the **eight entries are enumerated**, keyed and split by path, because a count without its list is exactly what gets built short. **The most valuable draft defect was one three loops had walked past.** INV-5 forbids a `QCoreApplication` on either headless path — and `ONEUP-0032` §4.2 gives both paths one, so the very next item in the order is specified to break a test this item writes, with nothing anywhere saying so. INV-5 is now marked transitional and 0032 §4.2 records that it retires the check, so the next item does not inherit a red suite. Its sibling was the same shape pointing the other way: 0032 §4.2 still sent a reader to *"ONEUP-0072 §4.4"* for why those paths need an application object, and that section **no longer exists** — the 2026-08-03 split took it. Fixed at the source. **The precedence rule loop 2 added turned out to contradict a rank-1 reference.** `marker-protocol.md` §4.9 says of the exit code and `@@DONE@@` that *"the two always agree"*; they do not for the one case this item turns on, and §8 had queued no amendment, so the reference would have been left asserting the opposite of shipped behaviour. §4.9 joins §2 and §4.7 in this item's commit. Two promises were also found carrying no check at all — the stdout pass-through loop 2 wrote (*"capturing must not end that"*), and the `@@DONE@@`-over-exit-status precedence itself, whose failure is precisely ONEUP-0074 returning. Both are invariants now, **INV-6** and **INV-7**. Smaller collateral: the negative-construction assertions in INV-4 and INV-5 named no observation mechanism, and INV-5's harness said to point `ENGINE` at the mock via the child's environment when `ENGINE` is a module-level constant with no override — the suite's rewritten `HOME` is one of the two paths `_find_engine` searches, and that is the mechanism. **A second measurement of mine was corrected, in the same class as loop 2's.** The ONEUP-0082 note called unpruned logs *"growth this item starts"*; `_launch` already writes a timestamped log per GUI run and nothing deletes any of them, so the growth is inherited and what this item adds is an unattended source of it. **Carried as INFO:** the streaming rule has no numeric budget, which both lanes raised and neither could make consequential — a line-at-a-time read with a bounded retained-field set is the constraint that matters, and it is stated. **The trend is the reason this stops here: draft defects 21 → 8 → 6, collateral 0 → 15 → 12.** The reads are finding steadily less that was ever in the draft, while two consecutive loops have spent most of themselves on the previous loop's fixes — the documented signal to stop looping and sweep, not to loop again. Unlike the two documents that reached this state before it, size is not the cause: at 377 lines this spec is less than half of either, so **it is filed and shipped rather than split**. Nothing is left verified and unfixed. |
| 2 | 2026-08-03 | 2 lanes; 2 critical, 4 high, 8 medium, 10 low — **23 verified, 1 dismissed** — 8 draft defects vs 15 fix collateral (23 actionable fixed) | **Nothing loop 1 fixed came back**, which is the proof those fixes held — the split's inherited paragraph, the three misplaced invariants and the ownership of the two `marker-protocol.md` edits were all absent. **What came back instead was loop 1's own damage, and both criticals were mine.** Both lanes led with INV-3: loop 1 rewrote it as *"fires only when the total is above zero **and** every source was readable"* — a conjunction, which mandates **silence** on a zero total with a broken repository — three lines above a test loop 1 also wrote asserting that exact case must fire. An implementer coding the invariant's headline rebuilds ONEUP-0056, the defect this project takes most seriously. It is now stated as the silence condition instead, and `emit_check` settles a case neither lane could see and the draft never covered: a count **is** still emitted alongside the warning when it is non-zero, so there are two unreadable-source sentences, not one. The second critical is the same shape. Loop 1 rewrote §6 to make the exit status the authority, citing `marker-protocol.md` §4.9's *"normally the window takes its verdict from the exit code"* — but the engine's final statement is `((ERRORS == 0))`, so a **stopped** run exits zero, and an exit-status-first reading calls it a success. Loop 1's fix would have put ONEUP-0074 straight back into the item that exists to fix it. `@@DONE@@` decides whenever it arrives; the exit status decides only when it does not. **The best draft defect was one loop 1 never touched.** INV-5's whole falsification mechanism read *"`QCoreApplication.translate` refuses without an instance"* — `ONEUP-0032` §2.2 measured the opposite: `installTranslator` refuses and returns `False`, while `translate` quietly hands back the English. So a path wrongly marked for translation would still exit cleanly and the invariant could not break. It now asserts the **construction** rather than the absence of an exception. Six more were collateral in §8, which loop 1 wrote before making the edits it prescribes: it told an implementer to add a `timer notification (0077)` node to `oneup-2.0.md` §5.2 that loop 1 had already added, claimed `ONEUP-0072` gives up its whole §2 edit when it keeps the tray-check row, and quoted *"Four channels use this protocol"* as the sentence this item edits — when 0072 lands first and makes it five, so this item takes it to seven. §8 is split into what is already made and what lands with the code. Also collateral: five markers were called four, INV-5's subprocess never redirected `ENGINE` at the mock (so it could have run a real update, which `testing.md` §2 forbids), INV-4's check-path assertion was vacuous without a non-zero total, INV-2 compared a timestamp literally, and §7 restated §5's clauses near-verbatim — now a pointer plus the mock engine the suite gains. **One fix was corrected during verification rather than after.** A retention sentence claimed the window's existing log pruning covers the 52 files a year a weekly timer adds; grepped, `updater.py` only ever *reads* `LOG_DIR`, through `_latest_run_log`, and nothing prunes anything. The claim was deleted, the gap stated, and **ONEUP-0082** filed. **Dismissed: one.** Both lanes hedged their §8 findings on the packet appearing to hold two copies of `oneup-2.0.md` §5.2; that was an artifact of the orchestrator's packet-refresh script, not anything in either document, and the underlying findings stood without it. The document left this loop at 313 lines, up from 270. |
| 1 | 2026-08-03 | 2 lanes; 1 critical, 7 high, 8 medium, 6 low — **21 verified, 1 dismissed** — 21 draft defects vs 0 fix collateral (21 actionable fixed) | The first review of this document on its own bytes, and **both lanes led with the same critical: a paragraph the split carried across unedited.** §4's firing rules still said of the stopped run *"Carry it across unchanged"*, citing a §3.2 that forbids rewording — which is `ONEUP-0072`'s section number, not this document's, whose §3 is a flat bullet list. Its `(§10)` pointed at 0072's out-of-scope bullet, where the defect was filed *to here*. So the most confidently-worded paragraph in the spec instructed the implementer to ship the exact bug the item exists to fix, against §1, §2, §3, INV-1, §8's CHANGELOG-under-Fixed entry and §9. It now states the branch this item adds, per `marker-protocol.md` §4.9. **Three of the five invariants were untestable as written, which is the class that costs most because it surfaces at test-writing time.** INV-1 and INV-3 were assigned to `tests/run-tests.sh` — the engine suite — when this item moves the sentence into the window and leaves the engine's own `--notify` untouched, so those cases could only ever have asserted against text this item does not write. And INV-5 (*no `QCoreApplication` is required*) was to be checked in `tests/gui-smoke.py`, which builds one at import (`QApplication.instance() or QApplication([])`): the assertion would have passed while proving nothing. It is a subprocess now, with the reason recorded beside it. **The most useful finding pair was about ownership, and both halves were real.** `ONEUP-0072` §8 schedules the two `marker-protocol.md` edits this item causes — §4.7's *"emitted and currently unread"* `fw_changed`, and §2's reading-order table gaining the two headless readers — and also claims the entry-point argument changes outright; `docs/design/oneup-2.0.md` §5.2 credits 0072 with landing "its notification check in `tests/gui-smoke.py`" and needing "no application object at all", which is this item's INV-4 and INV-5 verbatim, in the section that owns the order of work — and never places this item in its diagram at all. All four now sit with this item; 0072 §8 gives them up and the diagram gains a `timer notification (0077)` node between the codes and translation. Smaller draft defects: §3 offered *"somebody running `oneup --update` in a terminal"* as the case that keeps `--notify`, when `oneup --update` **is** one of the two paths INV-2 strips it from; the marker list omitted `@@CHECK_UNKNOWN@@`, so INV-3's zero-total silence would have reproduced ONEUP-0056 on a broken repository; "the error count" is carried by no marker (`@@DONE@@|errors` is the verdict, and the failure text names the log rather than a number); the capture requirement never said the inherited stdout a terminal user and the journal see today must survive it; `--auto-skip-repos` — load-bearing for the `@@REPO_SKIPPED@@` report — was pinned nowhere, so §4 now tabulates both argvs in full; and the module that composes the notification was never named. §6 cited `marker-protocol.md` §4 for a followed-run rule that is §4.9 and turns on there being **no exit code**, which a headless path has. **Dismissed: one.** A lane proposed numbering §3's bullets so the `§3.2`/`§3.3` references would resolve; checked, those references belong to another document entirely, so qualifying them is the fix and numbering §3 would have made two documents' section numbers collide. Two lane open questions resolved in the document's favour and are recorded so a later loop does not re-ask: `tests/gui-smoke.py` does carry a mock `notify-send` on its PATH, and the auth, thin and size calls do all pass `--log=`. The document left this loop at 270 lines, up from 209. |
| 0-split | 2026-08-03 | — | **Provenance, not a review — no reviewer was dispatched to produce this row.** Split out of `docs/specs/ONEUP-0072-marker-codes.md` on 2026-08-03 on the user's decision, taking that document's §4.4. The parent had run three cold-eyes loops (24, 22, 20 verified) and **converged by cap rather than clean** at 654 lines; its §11 recommended splitting §4.4 rather than a fourth loop, and both of loop 3's criticals landed in §4.4 or the ordering paragraph beside it. **Those loops were run against a document that no longer exists, so none of their assurance transfers**: this spec runs the gate from loop 1 on its own bytes. The invariants here are new — the parent's INV-1…INV-5 are all about codes and stay with it — and **ONEUP-0074 is folded in** rather than left filed, because this item rebuilds the four-case fall-through that defect lives in. |
