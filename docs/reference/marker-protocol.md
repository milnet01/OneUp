# Marker Protocol — the engine↔window contract

**In one sentence:** the part of OneUp that does the work and the part you look at are two
separate programs, and this file is the entire vocabulary they share — one line of text at
a time, in one direction.

**Status:** Reviewed
**Kind:** reference
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `58ea3bc` — every marker, field and behaviour below was read out of
`update_system.sh` and `updater.py` on 2026-07-26, not recalled.

**Sections:** 1 the shape of a line · 2 reading order · 3 the markers · 4 the ones with
traps · 5 changing the contract · 6 traps · 7 drift in the engine's header comment ·
8 the two state files · what checks this · 9 cold-eyes log

This is a **reference**, not a standard: it records a contract, not a rule about how to
work. Where it and the engine's own header comment disagree, **this document is right** —
see §7.

## 1. The shape of a line

```
@@NAME@@|field|field|field
```

- The engine writes it to **stdout**. Nothing travels the other way: the window's only
  reply channel is the `stop.request` file, which is not part of this protocol.
- Fields are separated by `|` and are **positional** — there are no names and no defaults.
- Everything the engine prints that is *not* a marker is ordinary log text, and the window
  shows it verbatim in the log pane.
- **A marker is also readable by a human.** The engine is usable standalone in a terminal,
  where these lines are harmless one-liners.

Both sides are written by one helper each, which is why the format cannot drift:

- Engine: `marker()` — `printf '@@%s@@|%s\n' "$1" "$2"`.
- Window: `Updater.handle_line` sends any line starting with `@@` to
  `Updater.handle_marker`, which splits on the first `@@|` and then on `|`.

**A line that starts with `@@` but is not a marker is logged, not dropped.** A diff hunk
header (`@@ -1,4 +1,4 @@`) is the real case that made this necessary.

### 1.1 There is no escaping — except one substitution

A payload cannot contain a `|`, and the protocol offers no way to quote one. The one place
where user data could contain one — a Btrfs snapshot description — the engine rewrites `|`
to `/` before emitting `SNAPSHOT_ITEM`. **Any new field carrying free text must do the
same, or must be last.**

### 1.2 Markers arrive spliced, and the parser must survive it

The engine's stdout and stderr are merged, so another program's output can land in the
middle of a marker line. Every parser that unpacks a fixed number of fields or calls
`int()` therefore **checks first and returns quietly on a malformed line**. A throw inside
the read slot would abort parsing and silently drop the rest of the run's markers —
the run would appear to freeze while it was in fact still updating.

Three markers carry that guard explicitly — `STEP_BEGIN`, `PROGRESS` and `REFRESH`, the
three that unpack a fixed shape (see their notes below); the rest read fields defensively
with `len(parts) > n` tests.

## 2. Reading order

Four channels use this protocol, and only the first goes through `handle_marker`:

| Channel | How the engine is invoked | Who reads it |
| --- | --- | --- |
| A run | `--steps=…` | `Updater.handle_marker` |
| Download size | `--size=<step>` | `Updater._on_size_output` — reads `SIZE` only |
| Authorization state | `--auth-status` / `--grant-auth` / `--revoke-auth` | `Updater._query_auth_status` — matches `@@AUTH@@|on` in the whole output |
| Snapshot thinning | `--thin-snapshots` | `Updater._on_thin_finished` — reads `SNAPSHOTS|thinned` only |

This matters when adding a marker: **a marker emitted only on a side channel is not seen
by `handle_marker`**, and one emitted during a run is not seen by the side-channel readers.

## 3. The markers

23 in total. `key` is always a step key — `system`, `flatpak`, `firmware`, `orphans`,
`cache` — except where noted.

| Marker | Fields | Emitted by | Read by |
| --- | --- | --- | --- |
| `@@STEP_BEGIN@@` | `key\|index\|total\|label` | `begin_step` | `handle_marker` |
| `@@STEP_END@@` | `key\|status\|detail` | `end_step` | `handle_marker` |
| `@@TIMING@@` | `key\|seconds` | `end_step` | `handle_marker` |
| `@@PROGRESS@@` | `key\|done\|total\|phase[\|bytes\|bytes_total]` | `emit_progress`, `progress_filter` | `handle_marker` |
| `@@REFRESH@@` | `done\|total\|alias` | `refresh_repos` | `handle_marker` |
| `@@SNAPSHOT@@` | `id` | the pre-update snapshot block | `handle_marker` |
| `@@SNAPSHOT_ITEM@@` | `id\|date\|description` | the same block, once per restore point | `handle_marker` |
| `@@SNAPSHOTS@@` | `warn\|count` *or* `thinned\|removed` | pre-flight; `--thin-snapshots` | `handle_marker`; `_on_thin_finished` |
| `@@CHECK@@` | `key\|count\|label` | `emit_check` | `handle_marker` |
| `@@CHECK_ITEM@@` | `key\|name\|from\|to` | the `--check` pass | `handle_marker` |
| `@@CHECK_UNKNOWN@@` | `key\|reason` | `emit_check` | `handle_marker` |
| `@@SIZE@@` | `key\|download` | the `--size` pass | `_on_size_output` |
| `@@FREED@@` | `cache\|human` | the cache step | `handle_marker` |
| `@@AUTH@@` | `on` *or* `off` | the auth actions | `_query_auth_status` |
| `@@DISK@@` | `warn\|mount\|free` | pre-flight | `handle_marker` |
| `@@REPO@@` | `warn\|duplicate\|urls` | pre-flight | `handle_marker` |
| `@@REPO_SKIPPED@@` | `alias\|reason` | the skip path | `handle_marker` |
| `@@HINT@@` | `plain-English sentence` | anywhere a failure is reported | `handle_marker` |
| `@@REMEDY@@` | `import-keys` *or* `skip-repo\|alias` | the system step; `refresh_repos` | `handle_marker` |
| `@@SERVICES@@` | `svc1 svc2 …` | the summary | `handle_marker` |
| `@@INSTALLED@@` | `count\|sys_changed\|fw_changed` | the summary | `handle_marker` |
| `@@REBOOT@@` | `yes[\|reason]` *or* `no` | the summary | `handle_marker` |
| `@@DONE@@` | `ok` *or* `errors` *or* `stopped` | the exit paths | `handle_marker` |

**Every marker the engine emits is read, and every marker the window reads is emitted.**
Checked both directions at `58ea3bc`; the two side-channel markers (`SIZE`, `AUTH`) are the
only ones absent from `handle_marker`, and that is by design.

## 4. The ones with traps

### 4.1 `STEP_BEGIN|key|index|total|label`

`index` is 1-based and `total` is the number of steps *this run* selected, not five. The
window sets the progress bar to `index - 1` and keeps `label` so `PROGRESS` can rebuild the
bar's caption without re-deriving it.

**Guarded:** fewer than four fields, or a non-numeric `index`, and the line is ignored.

### 4.2 `STEP_END|key|status|detail`

`status` is exactly one of **`ok`**, **`skip`**, **`fail`**. `detail` is a short phrase for
the row's badge (`"3 package(s) updated"`, `"not installed"`) and **may be empty** — the
cache step's success emits none.

`skip` is not a failure. A step for a tool that is not installed is skipped cleanly, and
the run's verdict is unaffected.

`TIMING` follows immediately, always, as a separate marker — deliberately, so the
`status|detail` layout never had to grow a field.

### 4.3 `PROGRESS|key|done|total|phase[|bytes|bytes_total]`

The marker that stops a working download looking like a hang (ONEUP-0040/0048).

- **`phase` is `download` or `install`.** The window announces a *change* of phase to a
  screen reader, never each package — announcing all 141 would bury everything else.
- **`total` of 0 means "unknown", and must be rendered as a running tally** —
  "Downloading packages — 37 so far" — never as an invented denominator. Zypper's parallel
  prefetch (`Preloading:`) reports no counter at all.
- **The two byte fields are optional**, present only in the download phase once zypper has
  printed a size. **`bytes_total` of 0 means "not known yet."** When they are absent the
  window weighs `/var/cache/zypp/packages` itself — world-readable, so no root is involved.
- The engine derives all of this by parsing zypper's own output, which is why `LC_ALL=C` is
  pinned on the transaction: the three wordings (`Preloading:`, `Retrieving: … (12/77)`,
  `( 7/77) Installing:`) would otherwise change on a non-English desktop.
- The transaction total is printed once as **`Package download size:` *or* `Overall
  download size:`** depending on the backend, and **both wordings are parsed**. The first
  is what `classic_rpmtrans` prints.

**Guarded:** fewer than four fields, or a non-numeric `done`/`total`, and the line is
ignored.

### 4.4 `REFRESH|done|total|alias`

Note the field order: **this marker leads with the counter, not the key** — it is not
scoped to a step. It exists because the metadata fetch is otherwise *completely invisible*:
zypper reports it as dots with no line ending, so a line-based reader draws nothing at all
and a mirror trickling at 930 B/s looks identical to a frozen app.

**Byte figures are impossible here** and no field should be added for them: zypper's
metadata staging directory is root-only, so the window's cache-weighing fallback — which
needs no root — cannot see it.

The engine refreshes **one repository at a time** precisely so this marker, a per-source
time budget and a stop check can exist.

**Guarded:** fewer than three fields, or non-numeric counters, and the line is ignored.

### 4.5 `SNAPSHOT` and `SNAPSHOTS` are different markers

A documented trap, because the names differ by one letter and mean unrelated things:

- **`SNAPSHOT|id`** (singular) — the restore point taken *before* this run. It is the
  rollback target.
- **`SNAPSHOT_ITEM|id|date|description`** — one recent restore point for the rollback
  **picker**; the engine emits up to the 12 newest, oldest-first, skipping snapshot 0 (the
  live "current" pseudo-entry, which is not a rollback target).
- **`SNAPSHOTS|warn|count`** (plural) — a pre-flight advisory that restore points have
  piled up and may be using disk. Threshold: `SNAP_WARN_COUNT` in the engine.
- **`SNAPSHOTS|thinned|removed`** — how many a `--thin-snapshots` pass removed. Read by
  `_on_thin_finished`, **not** by `handle_marker`.

**Only the `id` is trusted downstream.** The window re-validates it as a bare number before
it can reach a root `snapper rollback`; `date` and `description` are display-only, and the
description has had any `|` rewritten to `/` (§1.1).

### 4.6 `CHECK|key|count|label` and `CHECK_UNKNOWN|key|reason`

The pair that exists because of ONEUP-0056 — OneUp once reported "Everything is up to date"
while eight updates waited.

- **`CHECK_UNKNOWN` means this step's count is a floor, not an answer.** A source could not
  be read. The window records the reason and refuses the "up to date" summary.
- **A bare zero is withheld when something was unreadable.** The engine emits `CHECK` only
  when everything was readable *or* the count is greater than zero: knowing about 7 updates
  beats knowing about none while a repository is broken.
- **`key` of `TOTAL`** carries the run-wide total rather than a step's.
- `label` is a human phrase (`"firmware update(s)"`). The window **does not use it** — it
  builds its own badge text. It is there for the terminal reader.

`CHECK_ITEM|key|name|from|to` carries one changed package for the preview panel. **`from`
is empty for Flatpaks** — the Flatpak path knows the new version only.

### 4.7 `INSTALLED|count|sys_changed|fw_changed`

`sys_changed` and `fw_changed` are the literal strings `yes` or `no`. The window reads
`count` and `sys_changed`; **`fw_changed` is emitted and currently unread** — it is part of
the layout (a positional regression test pins all three) and must keep its position.

### 4.8 `REBOOT|yes[|reason]` or `REBOOT|no`

The payload is `yes` or `no`, and **`no` never carries anything after it**. The trailing
`reason` is **optional**, appears only alongside `yes`, and is a
plain-English phrase built from the run's system transaction log naming what makes the
restart matter — *"a new kernel and your NVIDIA graphics driver were installed"*. The
window shows it **verbatim**, falling back to generic wording when it is absent.

It is cosmetic by design: it *names* a decision the engine has already made and can never
change it. The invariant it must not break — **reboot advice fires only when something was
actually installed, or when `zypper needs-rebooting` says so; never merely because a step
errored** — belongs to the engine, not to this field.

### 4.9 `DONE|ok|errors|stopped`

- **`stopped` means the user asked to stop**, and the window must claim **neither success
  nor failure**. A stop never interrupts a transaction; it takes effect at a safe boundary.
- Normally the window takes its verdict from the engine's **exit code**, and `DONE` is
  belt-and-braces — the two always agree.
- **The exception is a run the window merely *followed***
  (`Updater._attach_to_running_engine`): there is no exit code to read, so `DONE` is the
  only verdict there is. **A followed run that never printed one is reported as errors,
  never as success.**

### 4.10 `REMEDY` — the one-click fixes

Two forms, and they arm buttons in the warning banner rather than doing anything
themselves:

- **`REMEDY|import-keys`** — a repository signing key has rotated or expired. The banner
  offers *"Import signing key & retry"*, which re-runs the engine with `--import-keys`
  **after a warned confirmation**. It is opt-in per run for a reason: it changes what the
  machine trusts.
- **`REMEDY|skip-repo|alias`** — one source is broken. The banner offers *"Skip &lt;source&gt;
  & update the rest"*. `REPO_SKIPPED|alias|reason` is the matching report that a source
  *was* set aside for this run.

**`--no-gpg-checks` is never a remedy** and no marker will ever offer it.

## 5. Changing the contract

**A marker's name and field layout are a contract between four files.** Changing one means
changing all four **in the same commit**:

1. `update_system.sh` — the emitter,
2. `updater.py` — `Updater.handle_marker` or the relevant side-channel reader,
3. `tests/run-tests.sh` — the engine assertions,
4. `tests/gui-smoke.py` — the window assertions.

Then this document, in the same commit.

**Adding a trailing optional field is the cheap change**; every reader already tests
`len(parts) > n` before reading. **Reordering or renaming is the expensive one** and needs
a reason better than tidiness.

### 5.1 During 2.0 the contract is frozen

The engine rewrite (ONEUP-0054) ships with this contract **byte-identical**, English hint
prose included, and is measured against it: gate **G2** compares v1's and v2's marker
streams under identical mocks and requires them to be equal. A rewrite that changed the
protocol could not be tested this way at all.

**One exception, deliberately sequenced after the rewrite has passed its gate:**
ONEUP-0032 turns the `HINT` and `REMEDY` payloads from English prose into stable codes, so
the window can translate them. That is a single versioned change touching all four files
plus this document
(`docs/standards/wording-and-translation.md` §5).

Never both at once. A rewrite and a contract change in the same step means a failing test
cannot tell you which one broke it.

### 5.2 What the codes must define, when they land

ONEUP-0032 turns `HINT` and `REMEDY` payloads into codes, and three questions have to be
answered *in that spec* rather than discovered during implementation. They are reserved
here so the reference is where a reader looks for them:

1. **The shape of a code** — a stable identifier, ASCII, no spaces or `|`, chosen so it
   never needs translating and never reads as prose.
2. **Where the code→sentence map lives** — in the window, per
   `docs/standards/wording-and-translation.md` §5, and how a code with no entry renders.
   **It must render as something readable**, never as the raw token and never as an empty
   banner; a code the window does not know about is a bug in the window, not in the run.
3. **Who allocates one**, and the rule that a code is never reused for a different meaning
   once shipped — the same discipline as a roadmap ID.

Until that lands, the payloads are English prose (§4.10, §5.1).

## 6. Traps

- **Adding a field in the middle.** Positions are the whole protocol. Append, or rename.
- **Free text in a non-final field.** There is no escaping (§1.1). A `|` in the payload
  silently shifts every field after it.
- **Reading a field without checking it is there.** Markers arrive spliced (§1.2); an
  exception in the read slot drops the rest of the run.
- **Treating `total: 0` as a denominator.** `PROGRESS` and only `PROGRESS`: zero means
  unknown, and dividing by it invents a percentage out of nothing.
- **Confusing `SNAPSHOT` with `SNAPSHOTS`** (§4.5).
- **Assuming a new marker reaches the window.** If it is emitted on a side channel, only
  that channel's reader sees it (§2).
- **Emitting a marker from inside a subshell that also runs `sudo`.** Not a protocol rule,
  but it bites here: privileged capture goes through `sudo_capture`, never `$(sudo …)` —
  see `docs/standards/security.md`.

## 7. Known drift in the engine's own header comment

`update_system.sh` carries an abbreviated marker list in its header. It is convenient and
mostly right, but **three entries are inaccurate at `58ea3bc`**, and a reader who trusts
them writes a wrong parser:

| Entry | The header says | Actually |
| --- | --- | --- |
| step end | `key\|ok\|skip\|fail\|detail` | three fields — `key\|status\|detail`, where `status` is one *of* `ok`/`skip`/`fail` |
| repo warning | `warn\|reason` | three fields — `warn\|duplicate\|urls`, and the window reads the third |
| done | `ok\|errors` | `stopped` is a third value, and the one with a behaviour rule attached (§4.9) |

Left as-is rather than patched: `main` is frozen (`docs/standards/workflow.md` §1) and none
of the three is a defect in running code. **ONEUP-0066** tracks carrying the corrected list
into the Python engine, where the rewrite replaces this comment anyway. Until then, this
document is the authority.

## 8. The two state files — a contract this protocol does *not* cover

`~/.local/state/oneup/run.state` and `stop.request` are also a contract between the two
halves, and neither is a marker: the window **writes** them, which nothing in §1 permits.
They are named here because the obvious place to look for "how do the halves agree" is
this file, and finding nothing would suggest there is nothing to agree on.

- **`run.state`** — written by the engine when a run commits, cleared on exit. Carries the
  pid, the log path and the selected steps, so a window opened mid-run can find that run
  and follow its log (`Updater._attach_to_running_engine`).
- **`stop.request`** — created by the *window* to ask for a stop. The engine reads it only
  at safe boundaries (`docs/standards/security.md` §6). A request older than `run.state` is
  a leftover and is ignored.

Both paths are overridable — `ONEUP_RUN_STATE`, `ONEUP_STOP_FILE` — in the **engine only**;
the window resolves them from `Path.home()` and is isolated in tests by rewriting `HOME`
(`docs/standards/files-and-naming.md` §5).

**Their field layout is not pinned anywhere, including here.** The Python engine must
reproduce it exactly or run-following breaks silently, so ONEUP-0054's spec has to write it
down before the rewrite — either in that spec, or as a new subsection added here.

## What checks this

| Rule | What catches a breach |
| --- | --- |
| the engine emits each marker | `tests/run-tests.sh` — **for 22 of the 23**. `DISK` is asserted by no engine scenario (ONEUP-0069); `tests/docs-check.py` fails if any *other* marker joins it |
| the window reacts to each marker | `tests/gui-smoke.py` — for the markers it exercises, which is not the whole table. Nothing enumerates what `handle_marker` accepts, so this row cannot yet be made exact |
| §3's table matches the markers the engine emits | `tests/docs-check.py`, both ways: a marker the engine emits and this table omits, and a marker this table names that the engine never emits. It reads the `marker NAME` **call sites**, not the `@@NAME@@` literals in the engine's header comment — §7 records three inaccuracies in that comment, so comparing against it would validate one stale list against another |
| §1.1 a payload contains no `\|` | nothing automatic. The engine rewrites `\|` to `/` before emitting `SNAPSHOT_ITEM`; a new free-text field that forgets to is caught by nobody |
| §1.2 a marker read must survive being spliced with stderr | nothing automatic — the three guards are in the engine, and nothing checks a fourth has one |
| §5.1 the contract is frozen for 1.x | nothing automatic |

**The gap left is the GUI half.** The engine's side of the contract is now compared against
this table on every push, but nothing proves the window *handles* each marker it is told to.
`tests/gui-smoke.py` feeds the window marker lines and asserts what it does with them, which
covers the markers it happens to exercise — not the whole table. Closing that needs a list of
handled names the GUI can be asked for, which the 2.0 split (ONEUP-0034) makes easy and the
current single file does not.

**`DISK` is worth knowing about as a pattern, not just an omission.** It reads as covered
when you grep the whole suite, because `tests/gui-smoke.py` does feed it — so the *window*
is proven to react to a marker the *engine* is not proven to send. A marker needs both
halves, and only checking them separately shows which one is missing.

## 9. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document was one of three lanes the breadth pass accepted clean, and its share was additive rather than corrective: the `HINT`/`REMEDY` code vocabulary (§5.2) and the two state files (§8) were relied on by other documents and defined by none |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged. Nothing from loop 1 resurfaced in this lane, which is the proof those fixes held. The two findings that verified are logged against `files-and-naming.md` and `workflow.md` |
| 3 | 2026-07-26 | 1 high — **1 verified** | the What-checks-this row claimed `tests/run-tests.sh` proves the engine emits each marker. It proves 22 of 23 — `DISK` is asserted by no engine scenario, and reads as covered only because `gui-smoke.py` feeds it (**ONEUP-0069**). The gate meant to protect this table was itself comparing against the engine's *header comment*, which §7 of this document records as stale, rather than the `marker` call sites. |
| 4 | 2026-07-26 | none | clean. |
| 5 | 2026-07-26 | 1 medium — **1 verified** | converged (polish only). §3 wrote the REBOOT payload as `yes|no[|reason]`, which reads as three fields where the house style elsewhere is *or*. The ambiguity had already propagated into §4.8's prose, which called the reason 'the third field'. |
