# ONEUP-0072 — the engine's payloads become codes

**Status:** Draft
**Kind:** refactor
**Roadmap:** ONEUP-0072
**Branch:** v2
**Verified at:** `8d080b8` — every symbol and payload quoted below was read out of
`update_system.sh` and `updater.py` on 2026-07-27, not recalled.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** the engine stops sending sentences and starts sending identifiers, so
the window owns every word a user reads — which is what makes translation possible, and
which also removes a coupling that lets a reworded engine message silently change what a
task's badge says.

**This item was split out of ONEUP-0032** at that spec's fifth review loop, because the two
halves are two contracts: ONEUP-0032 keeps the catalogue machinery and right-to-left, and
this one takes the protocol change. `docs/specs/ONEUP-0032-i18n.md` §11 records what was
already found and settled for this content before the split.

**`docs/reference/marker-protocol.md` outranks this spec** and owns the protocol itself. §5
sets how the contract is changed, §5.1 freezes it for 2.0 with this conversion as the one
exception, and §5.2 reserves three questions to be answered here. §4.5 answers them.

## 1. Goal

After this ships, no marker payload the window renders contains a word. The window holds
every sentence, in tables it can translate, and the engine names situations rather than
describing them. A user on a Hebrew desktop sees Hebrew task badges, not English ones; and a
developer who rewords an engine message can no longer change a badge by accident, because
the badge no longer reads the message.

## 2. Background

### 2.1 The window already re-words the engine's English, by sniffing it

This is the evidence the whole item rests on, and it is not a translation argument.

`Updater._step_badge` takes `@@STEP_END@@`'s `status` and `detail` and returns its **own**
badge. It does so by matching English substrings against the engine's sentence — testing
`detail` for `"up to date"`, `"already"`, `"nothing"`, `"remov"`, `"applied"`, `"updated"`
— and by pulling the number back out with `re.search(r"\d+", detail)`.

So the engine composes an English phrase, sends it, and the window takes it apart again to
recover the two facts it wanted: which outcome, and how many. Every one of those substrings
is a coupling nothing tests. Change `end_step system ok "already up to date"` to *"no
changes"* — a wording nobody would think twice about — and it matches none of the branches,
so the badge silently becomes `Done`.

The same shape appears at `@@STEP_BEGIN@@`: the engine sends a `label`, the window shows it
verbatim in the status line — while already holding its own title for that step in `TASKS`.
Two owners for one piece of wording.

### 2.2 One user-facing sentence never travels as a marker at all

`notify_send` raises a desktop notification — *"Updates available"*, *"Update complete"*,
*"Already up to date"* — and the paths that reach it are the two systemd user timers, which
run `updater.py --check` and `--update`. Both shell straight through to the engine with
`--notify`, so the English is the engine's and no window is involved. It is a user-facing
string outside the protocol entirely, and it is the one string the user who never opens the
window actually reads.

## 3. Scope decisions

| Decision | Who, when |
| --- | --- |
| The conversion happens **after** the engine rewrite has passed its gate, never inside it | inherited — `docs/reference/marker-protocol.md` §5.1, design §5.1 |
| It is **one** deliberate, versioned change touching every file `marker-protocol.md` §5 lists, in one commit | inherited — that document's §5 |
| It converts **every payload the window renders as words**, not only `HINT` and `REMEDY` | this spec, and §3.1 says why |

### 3.1 Why this is wider than the reference reserves

`marker-protocol.md` §5.1 reserves this work for the `HINT` and `REMEDY` payloads. That is
too narrow to meet the gate it is meant to meet: design §7's **G10** is *"every user-facing
string is translatable"*, and converting only those two would leave every task badge, every
unreadable-source warning and every reboot reason in English on a Hebrew desktop.

§2.1 is the stronger argument, though, because it does not depend on translation at all: the
window is *already* re-deriving `STEP_END`'s meaning from English substrings, so the coupling
is a live defect whether or not a second language ever ships. `marker-protocol.md` §5.1 and
§5.2 are amended in the same commit, which is what that document's own §5 requires.

### 3.2 What this spec does not decide

- **How a sentence is worded.** `docs/standards/wording-and-translation.md` §2–§4 owns that.
  The conversion carries each sentence across as it stands; it is not a licence to rewrite
  messages.
- **How a sentence is wrapped for translation, or how a catalogue is loaded.** ONEUP-0032.
- **Whether the engine is Bash or Python.** ONEUP-0054 lands first, byte-identical, and this
  item changes what the rewritten engine emits.

## 4. Design

### 4.1 The three fates

Every field takes exactly one of three routes, decided by what the window does with it. The
rule is what matters; the field lists below are the application of it, checked one by one
against `docs/reference/marker-protocol.md` §3's table, which is the authority on which
fields exist.

**1 — The window already knows it, so the field is retired.**
`@@STEP_BEGIN@@`'s trailing `label`. The window holds a title for every step key in `TASKS`;
it gains the in-progress phrasing beside it and looks both up by `key`. The engine keeps its
own `LABEL` map for the terminal output a user sees when running `./update_system.sh`
directly, which stays English by design (`wording-and-translation.md` §5).

This one is **not** free, and the reason is worth stating: `STEP_BEGIN` is one of the three
markers with an explicit fixed-shape guard (`marker-protocol.md` §4.1), and both the
reference and the window's parser floor it at four fields. The marker becomes
`key|index|total`, so the floor moves to three in the same commit — otherwise every
well-formed `STEP_BEGIN` is silently ignored and the run appears to freeze while it is in
fact updating. Nothing is lost in the terminal: `begin_step` already prints the label on its
own line before emitting the marker.

**2 — The window renders it as words, so it becomes a code.** `@@HINT@@`'s sentence;
`@@REMEDY@@`'s action; `@@STEP_END@@`'s `detail`; `@@CHECK_UNKNOWN@@`'s `reason`;
`@@REBOOT@@`'s optional `reason`. `REMEDY` is the one already halfway there —
`import-keys` and `skip-repo` are codes today and only need the rule written down.

`@@STEP_END@@`'s `detail` carries a number today, and `_step_badge` recovers it with a
regular expression (§2.1). Under codes the number is an **argument** in its own trailing
field — `key|status|code|count` — so the window renders it through the plural form
(`wording-and-translation.md` §6.3), which is also how the badge stops saying `package(s)`
in English.

`@@CHECK_UNKNOWN@@`'s `reason` is three sentences in the engine, not one, and each becomes
its own code: sources that could not be read (the aliases follow as one space-separated
argument, replacing today's comma joining), zypper exiting with a code nobody can act on
(the exit status is the argument), and the Flatpak remotes that could not be reached. The
window joins a list of aliases the way the language joins lists, which is the point of
sending them as data.

`@@REBOOT@@`'s reason is the interesting one. `reboot_reason_from_log` composes a phrase
today — joining up to three components and agreeing the verb — which no other language
assembles the same way. Under codes it emits the **components**, and the window builds the
sentence, so the joining and the agreement happen where the language is known. They are
several values of one kind, so they share one space-separated field like `@@SERVICES@@`
does (§4.2). ONEUP-0054 §4.2 places that composition in `parsers.py`; this item changes what
it composes, from a phrase to a list.

**3 — It is data, an already-fixed token, or the window never renders it, so it does not
change.** Step keys, repository aliases, package names, counts, byte sizes, mount points,
snapshot ids and dates, and a Btrfs snapshot's own description are data. `STEP_END`'s
`status`, `PROGRESS`'s `phase` and `INSTALLED`'s two `yes`/`no` flags are already tokens the
window branches on rather than reads out; the English *it* chooses from them is a window
string, wrapped under ONEUP-0032 like any other. A translator must never see any of these,
and a code would be a lie about what they are.

**Two fields carry English prose and still belong here**, which is the case worth naming
because it looks like an oversight: `@@CHECK@@`'s `label` and `@@REPO_SKIPPED@@`'s `reason`.
Neither is read by the window at all — `handle_marker` takes `key` and `count` from the
first and only the `alias` from the second, building its own wording in both cases, and
`marker-protocol.md` §4.6 says so outright of the `label`. They are the engine's terminal
output, which stays English (`wording-and-translation.md` §5). Converting them would put a
bare token in front of the one reader they have.

### 4.2 The shape of a code, and its arguments

`marker-protocol.md` §5.2 reserved three questions for this spec. These are the answers.

**A code is `^[a-z0-9-]+$`** — lowercase ASCII, hyphen-separated, no spaces and no `|`. A
`HINT` code names the situation rather than the sentence — `repo-key-expired`, not
`use-the-import-button` — because the sentence is the window's to choose and will be
reworded without the engine hearing about it. A `REMEDY` code is the exception and always
was: it names an **action**, because that is what it selects (`import-keys`), not a
situation to describe. The constraint is not cosmetic — the protocol has no escaping
(`marker-protocol.md` §1.1), and a code that can never contain `|` or a space can never
shift a field.

**Arguments are data and travel in trailing fields.** A hint that names a repository sends
`HINT|repo-slow|packman`, and the window's entry for `repo-slow` declares the parameter
names in order, so the sentence uses named placeholders a translator can reorder
(`wording-and-translation.md` §6.2). Where several values of one kind travel together they
share one field, space-separated, as `@@SERVICES@@` already does.

**No argument is ever prose.** Where the engine interpolates an English fragment today it
gains a distinct code instead — the download-size failure, which selects one of four
sentences by zypper's exit code and interpolates it into a fifth, becomes four codes. This
is the rule that keeps English out of the privileged half rather than merely moving it into
a field.

**Free text still applies §1.1's substitution.** One argument is outside the engine's
control — the lock holder's process name, read from `/proc/<pid>/comm` — so the marker
emitter rewrites `|` to `/` in every argument, exactly as `SNAPSHOT_ITEM` already does for a
snapshot description. `oneup/engine/markers.py` is one place, so it is one guard.

**Allocating one.** A code is added in the same commit as the engine branch that emits it
and the window entry that renders it; the two are never separated. Once shipped, a code is
never reused for a different meaning — the same discipline as a roadmap id
(`docs/standards/workflow.md` §4). Retiring one means the window keeps rendering it for as
long as an older engine could still be installed.

### 4.3 Where the wording lives, and what an unknown code shows

The tables live in `oneup/gui/markers.py` — ONEUP-0034 §4.2 already gives that module
*"reading what the engine said, and saying it in English"*, and `_step_badge` is already its
own, so this replaces its substring matching with a lookup rather than adding a layer beside
it. One table per marker family, each entry pairing the code with its English and its
parameter names. ONEUP-0032 owns how that English is marked for translation.

**Some entries are not a template with placeholders, and the table has to admit it.** Three
render a *variable number* of things into one sentence — `@@REBOOT@@`'s components, and both
of `@@CHECK_UNKNOWN@@`'s list-bearing codes, the unreadable sources and the unreachable
Flatpak remotes. In English that is a comma-and-`and` join with a `was`/`were` agreement; in
another language it is whatever that language does. So those three entries carry a small
render function rather than a format string, and the sentence around the join goes through
the plural form (`wording-and-translation.md` §6.3) so the agreement is the catalogue's to
decide rather than English's. `CHECK_UNKNOWN`'s third code, the one carrying zypper's exit
status, is an ordinary substitution.

**A code with no entry renders a readable sentence, never the raw token and never an empty
banner** (`marker-protocol.md` §5.2). It says that this version of OneUp has no wording for
what the run reported, names the code so a bug report can quote it, and points at the log —
which is the only honest thing it can say. It is a bug in the window, not in the run, and
the run's own verdict is unaffected. This matters more than it looks: a user on a packaged
OneUp can have a newer engine than window, and the failure mode of the naive version is a
blank warning banner on a run that actually failed.

**Every reader of a converted marker goes through these tables, not just `handle_marker`.**
`updater.py` unpacks `@@HINT@@` in three further places on the side channels —
`_on_auth_finished` and `_on_thin_finished` put the payload straight into a `QMessageBox`,
and `_on_size_output` appends it to the log — each with `line.split("|", 1)[1]`. Left alone,
those three would show the user a bare `auth-write-failed` in a message box, which is the
raw token `marker-protocol.md` §5.2 forbids and INV-3 exists to prevent. They are the
easiest site in this item to miss, because they are nowhere near the marker handler.

### 4.4 The notification the timers raise

**The timers stop passing `--notify`, and the window sends the notification.** It already
launches the engine on those paths; it reads the run's `@@CHECK@@`, `@@STEP_END@@` and
`@@DONE@@` markers and builds the sentence through the same tables as everything else. The
engine keeps its `--notify` flag for somebody running `./update_system.sh` in a terminal,
where the notification is part of its own English output (§10).

Those two paths need an application object to render through, and `main` dispatches
`--check` and `--update` before one exists — **ONEUP-0032 §4.4 owns that**, because it is a
property of the translation machinery rather than of the protocol. This item depends on it
and does not restate it.

## 5. Correctness invariants

- **INV-1** Every code matches `^[a-z0-9-]+$`, and every payload field the window renders as
  words holds codes and nothing else — one code, or several space-separated, `@@REBOOT@@`
  being the only field that carries more than one. No field the window renders carries a
  sentence. (`@@SERVICES@@` is the space-separated *format* this borrows; its own contents
  are unit names, which are data — §4.1.)
  *Test:* `tests/run-tests.sh` splits each such field on spaces and asserts the shape of
  every element, on every `HINT`, `STEP_END` detail, `CHECK_UNKNOWN` reason, `REMEDY` action
  and `REBOOT` reason a scenario produces — the five families §4.1 routes to a code.
- **INV-2** No marker field contains a `|`: the emitter rewrites it to `/` in every argument
  before the line is printed.
  *Test:* `tests/run-tests.sh` — a lock-holder scenario whose process name contains a `|`
  produces a line the window's parser splits into the expected number of fields.
- **INV-3** A code the window has no entry for renders a non-empty sentence that is not the
  code alone, at **every** site that reads that marker.
  *Test:* `tests/gui-smoke.py` feeds an unknown code once for each of the five families §4.1
  converts, and once for each of the three side-channel `HINT` readers §4.3 names, and
  asserts the rendered text contains the code, contains a space, and is at least twice its
  length — the cheapest checkable proxy for "a sentence, not the token with something stuck
  to it".
- **INV-4** No user-facing sentence is composed by the engine on a path the window is on.
  The desktop notification the two timers raise is built by the window, and neither timer
  passes `--notify`.
  *Test:* `tests/i18n-check.py`, the notification check — `--notify` appears in no argument
  list the window builds; `tests/gui-smoke.py` asserts the headless paths produce the
  notification text themselves.
- **INV-5** A shipped code is never reused for a different meaning.
  *Test:* **nothing automatic.** A rename is visible in review as a changed entry in
  `oneup/gui/markers.py` and a changed assertion in `tests/run-tests.sh`; a *reuse* is not
  distinguishable from a correct edit by any script. §7 records it.

## 6. Failure modes

| When this breaks | What the user sees | Why it is survivable |
| --- | --- | --- |
| The engine emits a code the window does not know | A readable sentence naming the code, and the log | INV-3. The run's verdict, badges and reboot advice are unaffected — only the explanation is |
| The window is newer than the engine | An engine payload the window still has an entry for | Entries are retired only when no supported engine emits them (§4.2) |
| A `\|` reaches a marker argument | Nothing — it arrives as `/` | INV-2, in one place in the emitter |
| The `STEP_BEGIN` guard is not moved with the field | The run appears to freeze while it is in fact updating | Caught the moment a scenario runs: no step ever begins. §4.1 says so because it is the one part of this item that fails loudly rather than quietly |
| The window fails to build the timer's notification | No notification from an unattended run; the update itself is unaffected | INV-4. The engine's `--notify` still exists and a user who wants the old behaviour can call it directly (§10) |
| The retained Bash engine is run against a converted window | Prose where the window expects a code, so INV-3's fallback sentence | Deliberate and known: the fallback is frozen at the switch-over. `oneup-2.0.md` §4 requires it in the release notes, and §8 carries that |

## 7. Tests

| What it locks in | Where |
| --- | --- |
| INV-1, INV-2 — payload shape and the `\|` guard | `tests/run-tests.sh`, per-scenario assertions on every marker carrying a code |
| INV-3 — the unknown-code fallback, at all four reader sites | `tests/gui-smoke.py`, new checks |
| INV-4 — the notification is the window's | `tests/i18n-check.py` and `tests/gui-smoke.py` |
| INV-5 — a code is never reused | **nothing.** Review only |

`tests/i18n-check.py` is ONEUP-0032's suite; this item adds one check to it rather than a
second suite, and that suite is already named in `local-CI.sh` and
`.github/workflows/release.yml` by then (`docs/standards/files-and-naming.md` §2.2).

**The engine assertions are where the real coverage is**, because the conversion's failure
mode is a payload that still carries prose, and only a scenario that actually runs a step
produces one. `tests/gui-smoke.py` can prove the window renders a code correctly; it cannot
prove the engine stopped emitting sentences.

## 8. Docs & release

**All of it lands on `v2`, documentation included**, which is the one case
`docs/standards/workflow.md` §9 sends to the branch rather than to `main`: the reference edit
is bound by `marker-protocol.md` §5 to the same commit as engine, window and both suites, and
those are 2.0-only. A reference amended on `main` would describe a contract the 1.4.0 engine
`main` still ships does not implement.

- **`docs/reference/marker-protocol.md`** — §3's field table; §4.1, whose four-field guard
  this item moves; §4.2, §4.6, §4.8 and §4.10 for the payloads that become codes; and
  §5.1/§5.2, which currently reserve this work for `HINT` and `REMEDY` alone (§3.1). All in
  the same commit as the engine and both suites, per that document's §5.
- **`docs/standards/wording-and-translation.md`** — §5's "today this is not yet true"
  paragraph becomes the description of what shipped.
- **`CHANGELOG.md`** — one entry under *Changed*, naming the payload conversion as a
  contract change, and saying plainly that **the retained Bash engine stops being a drop-in
  for the window**: it is frozen at the switch-over, so from this item onward it emits prose
  to a window that expects codes. It still runs an update in a terminal. `oneup-2.0.md` §4
  assigns that sentence to this item rather than leaving it to be discovered.
- **The two systemd user timer units** — the `--notify` flag comes off both (§4.4).
- **No version-site change** — none of `docs/standards/workflow.md` §5.1's six sites moves.
  This lands inside 2.0, not as a release of its own.

## 9. Alternatives considered (and rejected)

- **Convert only `HINT` and `REMEDY`, as the reference reserves.** Rejected: §2.1 shows the
  window is already re-deriving `STEP_END`'s meaning from English substrings, so the coupling
  is a live defect independent of translation — and G10 would be met in name while every
  task badge stayed English.
- **Keep the English in the engine and have the window translate it by lookup.** Rejected:
  the key would be an English sentence, so every wording fix silently loses its translation,
  and the privileged half would still own the vocabulary.
- **Convert the payloads inside the engine rewrite.** Rejected by
  `marker-protocol.md` §5.1, and for a good reason: gate G2 compares v1's and v2's marker
  streams for equality, so a rewrite that changed the protocol could not be tested that way
  at all. A failing test would not say which change broke it.
- **Leave the timers' desktop notification with the engine.** Rejected: it is a sentence a
  user reads, on the one path where no window is open to read anything else, so leaving it
  would make §1's goal false for precisely the user the timers exist for — and it would put
  wording back in the privileged half.
- **Keep `@@CHECK@@`'s `label` and `@@REPO_SKIPPED@@`'s `reason` in the conversion for
  consistency.** Rejected: the window reads neither, so converting them would replace a
  sentence with a bare token in front of the terminal reader who is their only audience.

## 10. Out of scope

- **Translating the engine's terminal output.** `./update_system.sh` run directly is a
  system tool's output and stays English (`wording-and-translation.md` §5). Its `--notify`
  notification is part of that output and stays with it — what changes is that the timers
  stop using it, not that the flag goes (§4.4).
- **Wrapping the window's own strings, loading catalogues, right-to-left.** ONEUP-0032.
- **Re-wording any message.** The conversion carries each sentence across as it stands
  (§3.2).
- **Any change to a marker the window does not render as words.** The three fates are a
  routing rule, not an invitation to tidy the protocol (§4.1).

## 11. Cold-eyes loop log

This content was reviewed through five loops as part of `docs/specs/ONEUP-0032-i18n.md`
before the split; that document's §11 holds those rows and they are not copied here. The
table below records the loops run against **this** document.

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
