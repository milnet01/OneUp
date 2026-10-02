# ONEUP-0072 + ONEUP-0108 — marker payloads become codes — build plan

**Specs:** [docs/specs/ONEUP-0072-marker-codes.md](../specs/ONEUP-0072-marker-codes.md) (the
engine side) and [docs/specs/ONEUP-0108-window-wording.md](../specs/ONEUP-0108-window-wording.md)
(the window side). One plan, because the two land in one commit (`docs/reference/marker-protocol.md` §5).
**Status:** not started.

## Scope of this file

The specs own what is built and why; this file holds the order and the checks. Both specs
were written against the Bash engine and the single-file window. They land on `v2`, where
the engine is the `oneup.engine` package (ONEUP-0054, the window's only engine since its
stage 9) and the window is the `oneup/gui/` package (ONEUP-0034). Each step names the `v2`
site that stands where a spec names a Bash or `updater.py` one.

**Branch: `v2` for every code, test and document edit** (ONEUP-0072 §8: the reference is
bound to the same commit as the engine and both suites, and all of it is 2.0-only). This
plan file takes the `main`-then-merge route, as ONEUP-0054's did.

**One commit on `v2`.** `marker-protocol.md` §5 makes the conversion one versioned change.
Steps 1–9 may be built and committed locally in sequence, but they are squashed into one
commit before anything is pushed, and no intermediate commit is pushed: an engine sending
codes to a window without the tables shows the user raw tokens, which §5.2 forbids.

**`update_system.sh` is not converted.** It is frozen at the switch-over
(`docs/design/oneup-2.0.md` §4), and from this commit on it emits prose to a window that
expects codes — ONEUP-0072 §6's last row, and the CHANGELOG says so (step 9).

### Four sites the specs do not name, settled here

1. **A fourth `@@CHECK_UNKNOWN@@` reason.** The firmware step of `--check` emits
   `firmware|OneUp couldn't ask fwupd`. ONEUP-0072 §4.1 lists three reasons; this one is
   allocated by §4.2's own rule, with the branch: code `fwupd-unreachable`, no arguments.
2. **The lock-holder hint's fallback name.** `repos.lock_holder` falls back to the English
   `another program` when the holder's name cannot be read, and the hint interpolates it.
   §4.2 forbids a prose argument, so the unnamed case gets its own code (the pid alone).
3. **Hints that reach the terminal only through the marker.** Several hint sites print no
   English line of their own; today a terminal reader reads the sentence inside the raw
   `@@HINT@@` line. ONEUP-0072 §4.1 keeps the engine's English for its terminal reader, so
   the hint helper prints the English line as well wherever the site did not already. The
   progress canary in `steps.py` is the case to watch: it prints a line of its own, but that
   line says *"(see @@HINT@@ above)"*, which after this commit points at a bare code — so its
   hint passes the sentence too, and the line points at the hint rather than the marker.
4. **The set-aside hint's alias list.** `Updated everything except: <aliases>` lists
   repository aliases. `repos.valid_alias` forbids a space in one, so they travel as one
   space-separated argument (§4.2's rule for values that cannot contain a space), which
   keeps the code fixed-arity (ONEUP-0108 §4.1).

## Steps

1. **The emitter takes fields, not a payload (ONEUP-0072 §4.2, INV-2).**
   `oneup/engine/markers.py`'s `marker(name, *fields)` joins the fields with `|` itself,
   rewrites `|` to `/` inside every field, keeps the line-break folding (ONEUP-0152), drops
   trailing `None` fields, and raises on a `None` before a non-`None` one. Every call site in
   `oneup/engine/` passes fields rather than an f-string joined with `|`. `emit_check`,
   `emit_progress` and `end_step` change with it. **Behaviour-neutral apart from the `|`
   guard**: no payload changes for any input without a `|`.
   → **verify:** the engine suite unchanged, 0 failed. Direct calls: `marker("REBOOT", "no",
   None)` prints `@@REBOOT@@|no`; `marker("X", "a", None, "b")` raises; `marker("X",
   "a|b")` prints `@@X@@|a/b`.

2. **`@@STEP_BEGIN@@` loses its label (ONEUP-0072 §4.1, fate 1).** `steps.begin_step`
   emits `key|index|total`; it keeps printing the label on its own terminal line. The
   window's in-progress phrasing goes into `oneup/gui/steps.py` beside `TASKS`, keyed by
   step, carrying the engine's `LABEL` English unchanged. `run.handle_marker`'s
   `STEP_BEGIN` branch floors at three fields and looks the phrasing up; an unknown key
   takes ONEUP-0108 §4.3's long form in the status line and the announcement and the bare
   key in the progress caption.
   Each family's assertions and tests move **in the step that converts it**, so every step
   below ends with its own family green: this step rewrites the suites' `STEP_BEGIN` feeds
   and adds ONEUP-0108 INV-1's unknown-step-key check.
   → **verify:** a run's status line, caption and announcement read as before; the
   unknown-key check passes and is seen red with the fallback removed; both suites green.

3. **`@@STEP_END@@` carries a code (ONEUP-0072 §4.1's table).** Each `end_step` call
   passes a code and, for `installed`/`removed`, a count; `steps.DETAIL` keeps the English
   for the end-of-run summary. The mapping from today's detail, by the badge
   `_step_badge` gives it now:

   | Today's detail | Code |
   | --- | --- |
   | `already up to date`, `up to date`, `nothing to remove` | `up-to-date` |
   | `N package(s) updated`, `N app(s) updated` | `installed` N |
   | `removed N package(s)` | `removed` N |
   | `packages updated`, `updates applied` | `updated` |
   | the cache step's empty detail | `done` |
   | `not installed` | `not-installed` |
   | `stopped before …`, `kept the downloads for a retry` | `skipped` |
   | every `fail` | `failed` |

   `oneup/gui/markers.py`'s `_step_badge` becomes a table lookup; an unknown code or an
   arity mismatch shows the bare code (ONEUP-0108 §4.3, short form). `status` still
   decides `fail`.
   The suites' `STEP_END` assertions and feeds move to codes in this step, with INV-1's
   unknown-code and arity checks for this family.
   → **verify:** every badge in the window suite's existing run scenarios reads as before;
   both suites green; the new checks seen red with the lookup's fallback removed.

4. **`@@HINT@@` and `@@REMEDY@@` carry codes (ONEUP-0072 §4.1, §4.2).** One code per
   hint branch, allocated with the branch and its window entry in the same edit, carrying
   that branch's sentence across unchanged (§3.2). **A branch is a sentence, not a call
   site**: `_note`'s three callers each get a code, and `_failure`'s download branch gets two —
   one with the package's name as its argument, one without — since a code is fixed-arity
   (ONEUP-0108 §4.1). `markers.hint(code, *args, say=None)`
   prints `say` to the terminal where the site did not already print the sentence (site 3
   above) and emits the code. The engine's 20 hint call sites, including `_failure`'s seven
   branches and the download-size failure's four codes (`*`'s carries the exit status).
   `REMEDY`'s `skip-repo` passes its alias as a separate field. The window's `HINT` table
   lives in `oneup/gui/markers.py`; `run.handle_marker`, `auth._on_auth_finished`,
   `rollback._on_thin_finished` and `run._on_size_output` render through it (ONEUP-0108
   §4.5). An unknown `REMEDY` arms no button and the banner carries the long form.
   `banners._extract_command` keeps working because it reads the rendered sentence.
   The suites' hint and remedy assertions move to codes in this step, with INV-1's checks
   for `HINT` (and its three side-channel readers) and `REMEDY`.
   → **verify:** every hint the window suite shows reads as before; both suites green; the
   terminal still prints each sentence once; the new checks seen red with the fallback
   removed.

5. **`@@CHECK_UNKNOWN@@` carries a code (ONEUP-0072 §4.1, site 1 above).**
   `sources-unreadable` and `flatpak-remotes-unreachable` take one name per trailing field;
   `sources-unknown-error` takes zypper's exit status; `fwupd-unreachable` takes nothing.
   The window renders each through ONEUP-0108 §4.2's list function with today's joins and
   tails. `tray._parse_tray_line` is untouched (§4.5).
   The suites move to codes for this family in this step, with its INV-1 check.
   → **verify:** the unreadable-source warning banner reads as before for one name and
   for two; a name containing spaces stays one name; both suites green.

6. **`@@REBOOT@@`'s reason becomes components or a standalone code (ONEUP-0072 §4.1).**
   `parsers.reboot_reason` returns the components; `__main__._reboot_and_services` emits
   them space-separated, or `core-packages-updated` / `firmware-updated`, and keeps
   composing the English phrase for its own summary line. The window renders per
   ONEUP-0108 §4.4's rows, with the was/were branch (§4.2), into `run.py`'s reboot banner.
   This step writes ONEUP-0108 INV-2 and INV-3's checks and the §4.4 mixes, and moves the
   suites' reboot assertions to codes; the firmware-only reboot's standalone reason is
   asserted by no engine scenario today, so it gains one.
   → **verify:** the reboot banner reads as before for a kernel, a kernel and a driver, and
   firmware; INV-2 and INV-3 pass and are seen red against a render keyed on the element
   count; both suites green.

7. **The checks that cross families.** Steps 2–6 each converted their own family's
   assertions; this step adds what spans them.
   - `tests/run-tests.sh` (ONEUP-0072 INV-1, INV-2): a shape-or-membership check on the code
     field of every `HINT`, `REMEDY`, `STEP_END`, `CHECK_UNKNOWN` and `REBOOT` the suite
     produces; a lock-holder name containing a `|`; `REBOOT|no` with one field; two source
     names as two fields; and a direct emitter call raising on a middle `None`.
   - `tests/gui-smoke.py` (ONEUP-0072 INV-4): the log pane still shows ordinary engine lines
     verbatim and looks none up.
   → **verify:** each new check seen red against the code with that behaviour removed; both
   suites green.

8. **Retire the differential harness (ONEUP-0072 §7).** Delete
   `tests/differential-test.sh`; remove it from `local-CI.sh` (its step and the
   `shellcheck` list), from `docs/standards/testing.md` §1's table, from
   `docs/standards/workflow.md` §6's table with the range re-measured, from
   `docs/standards/files-and-naming.md` §1's `tests/` row, and from the comments in
   `tests/mock-env.sh` and `tests/run-tests.sh` that name it. `release.yml` never ran it.
   **Two mentions stay**: `docs/design/oneup-2.0.md` §7's G2 row records where that gate
   was measured, and `docs/reference/marker-protocol.md`'s loop-log row 8 is a landed record,
   which is never edited. The reference is one of the documents `tests/docs-check.py` §9
   checks for backticked paths that do not resolve, and it reads every line, so that row
   would fail it. The check therefore skips lines inside a `## … loop log` section: a
   review row describes the tree as it was, and the check exists for documents describing
   the tree as it is — the same ground that already keeps specs and plans outside it.
   → **verify:** `./local-CI.sh` green with the step gone; `python3 tests/docs-check.py`
   clean with the file deleted; a search finds the file named only in dated records (specs,
   plans, reviews, the roadmap, the design's G2 row and the reference's loop log).

9. **The documents (ONEUP-0072 §8, ONEUP-0108 §8).** `docs/reference/marker-protocol.md`:
   §1.1 and §6's free-text trap (the guard now covers every field), §2's table gains the
   tray check, §3's table, §4.1's guard, §4.2/§4.6/§4.8/§4.10, §5.1/§5.2, and its *What
   checks this* row for §1.1. `docs/standards/wording-and-translation.md` §5 and §6.2's
   carve-out. `docs/standards/testing.md` §5's invariant 2. `CHANGELOG.md`: one *Changed*
   entry naming the conversion and that the retained Bash engine stops being a drop-in for
   the window. Both roadmap bullets flip together.
   → **verify:** `python3 tests/docs-check.py` clean; `./local-CI.sh` green on `v2` with the
   measured time in the commit body.

## Definition of done

Both specs' invariants are tested and green; no converted call site builds a string for a
marker (ONEUP-0072 §4.1's *Done when*); the differential harness is gone from every gate;
the documents in step 9 read true; `./local-CI.sh` is green on `v2`; and it is all one
commit.

## Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-10-02 | 2 lanes, cold, each holding every question; genre pinned plan; Q1 0 · Q2 0 · Q3 4 · Q4 0 — 4 verified, 0 dismissed, all 4 fixed | First gate on this plan. **Both lanes led with the same defect**: steps 2–6 named verifies (INV-1–3, "the suite's assertions read codes") that only step 7 wrote, so no step could be confirmed done in order — each family's assertions and tests now move in the step that converts it, and step 7 keeps only what crosses families. One lane found step 8 would leave `docs/reference/marker-protocol.md`'s loop-log row naming the deleted harness, which `tests/docs-check.py` §9 reads (measured: that check skips no section) — the check now skips loop-log sections, and the design's G2 row stays as the gate's record. The other found the progress canary's own line pointing at "@@HINT@@ above", which would become a bare code; the site is named. A lane's open question became the fourth: hint codes are per sentence, not per call site (`_note`'s three callers; the download branch with and without a package name). Resolved clean: `repos.DISABLED` is filled only after `valid_alias` passes, so site 4's alias list cannot hold a space. Lane spend 1.15 + 1.08 USD |
