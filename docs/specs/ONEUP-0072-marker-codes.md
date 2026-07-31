# ONEUP-0072 — the engine's payloads become codes

**Status:** Draft
**Kind:** refactor
**Roadmap:** ONEUP-0072
**Branch:** v2
**Verified at:** `83345ef` — every symbol and payload quoted below was read out of
`update_system.sh` and `updater.py` on 2026-07-31, not recalled. Neither file has changed
since `8d080b8`, when they were first read for this spec.

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
exception, and §5.2 reserves three questions to be answered here. §4.2 and §4.3 answer them.

## 1. Goal

After this ships, no marker payload the window renders **as wording** contains a word. Data
the window renders — a package name, a snapshot description — is untouched (§4.1). The window holds
every sentence, in tables it can translate, and the engine names situations rather than
describing them. A user on a Hebrew desktop sees Hebrew task badges, not English ones; and a
developer who rewords an engine message can no longer change a badge by accident, because
the badge no longer reads the message.

## 2. Background

### 2.1 The window already re-words the engine's English, by sniffing it

This is the evidence the whole item rests on, and it is not a translation argument.

`Updater._step_badge` takes `@@STEP_END@@`'s `status` and `detail` and returns its **own**
badge. It does so by matching English substrings against the engine's sentence — testing
`detail` for `"up to date"`, `"already"`, `"nothing"`, `"remov"`, `"applied"`, `"updated"`,
`"update"`, and `"not installed"` on the `skip` branch — and by pulling the number back out
with `re.search(r"\d+", detail)`.

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
*"Already up to date"*, and *"Update failed"*, which is the one carrying the log path — and
the paths that reach it are the two systemd user timers, which run `updater.py --check` and
`--update`. Both shell straight through to the engine with `--notify`, so the English is the
engine's and no window is involved. It is a user-facing string outside the protocol
entirely, and it is the one string the user who never opens the window actually reads.

## 3. Scope decisions

| Decision | Who, when |
| --- | --- |
| The conversion happens **after** the engine rewrite has passed its gate, never inside it | inherited — `docs/reference/marker-protocol.md` §5.1, design §5.1 |
| It is **one** deliberate, versioned change touching every file `marker-protocol.md` §5 lists, in one commit | inherited — that document's §5 |
| It converts **every payload the window renders as words**, not only `HINT` and `REMEDY` | this spec, and §3.1 says why |
| Where this item sits **relative to ONEUP-0032** | **open — §3.3** |

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

### 3.3 Open: this item and ONEUP-0032 each depend on the other landing first

**This is not yet decided, and it has to be before either is built.** The two specs
currently state dependencies running in opposite directions:

- This spec puts ONEUP-0032 first. §4.4 defers the application object to ONEUP-0032 §4.4,
  and §7 adds its check to `tests/i18n-check.py`, calling it a suite already wired into
  `local-CI.sh` "by then".
- ONEUP-0032 puts this item first. Its §4.1 gives `oneup/gui/markers.py` "the marking of its
  sentence tables for translation — ONEUP-0072 builds the tables", and `oneup/gui/steps.py`
  the phrasing "which ONEUP-0072 stops the engine sending".
- `docs/design/oneup-2.0.md` §5.2 owns the order of work and settles neither: its diagram
  ends at translation (ONEUP-0032) as the last item and **does not place ONEUP-0072 at all**,
  because it predates the split.

Neither order works as both specs are currently written, so one of three things has to
happen: this item lands first and owns its own application object and a home for INV-4's
check; ONEUP-0032 lands first and stops claiming this item built the tables; or the two ship
as one change, which `marker-protocol.md` §5 permits since it already requires the payload
conversion to be a single versioned commit. **`docs/design/oneup-2.0.md` §5.2 is where the
answer belongs**, and its diagram needs this item placed in it either way.

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

Retiring the field removes the only wording an **unfamiliar** step key could have supplied,
so a newer engine adding a step would leave the status line and the progress caption blank.
A step key with no entry in `TASKS` therefore falls back exactly as an unknown code does
(INV-3): the key is named, the run is unaffected. It is the same failure and it gets the
same answer.

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

Two shapes have to be written down rather than inferred, because `detail` today **may be
empty** — `marker-protocol.md` §4.2 says so, and names the cache step's success as the case.
**Every `STEP_END` carries a code**, including that one: a step that finished with nothing
to report emits `done`, which is what `_step_badge` already falls through to. An empty code
field is not a legal payload, and without this rule the cache step of every successful run
would trip INV-3's unknown-code banner. And **`count` is optional and trailing** — absent,
not empty, when the step counted nothing — so a step with no number emits three fields.

`@@CHECK_UNKNOWN@@`'s `reason` is three sentences in the engine, not one, and each becomes
its own code: sources that could not be read (the source names follow as arguments), zypper
exiting with a code nobody can act on (the exit status is the argument), and the Flatpak
remotes that could not be reached. The window joins the list the way the language joins
lists, which is the point of sending it as data. All three sentences today end in a shared
tail — *"this list may be incomplete"*, and for the first two *"Running an update refreshes
them"* — which is **part of each code's wording**, not a fourth code: the window has exactly
as many entries as the engine has branches.

**Those names cannot travel in a space-separated field.** They are not the step-key-shaped
tokens `@@SERVICES@@` carries. The engine recovers them from zypper's own prose —
`Skipping repository '…'` — and zypper puts the repository **name** there, not its alias:
measured against `zypper --root` on an isolated root, and this machine's stock openSUSE
repositories are named `Main Repository (OSS)`, `Main Update Repository` and `Open H.264
Codec (openSUSE Tumbleweed)`. `valid_alias` forbids a space but guards only the
`--skip-repo` path, not this one. Today's comma-and-space join survives them; splitting on
spaces would turn one broken source into three.

So these two codes take **one name per trailing field** — `CHECK_UNKNOWN|system|sources-unreadable|Main Repository (OSS)|packman` —
rather than a joined list in one. Positional trailing fields are what the protocol already
is (`@@PROGRESS@@`'s optional pair works this way), they need no separator and therefore no
character that a name must not contain, and the window gets the list's length by counting
fields rather than parsing text. The `|` substitution still applies to each (§4.2), so a
name can hold anything but a pipe. This is the one place a code's argument list is
deliberately variable-length; INV-3's arity rule (§4.3) exempts it, because here a differing
count is the data rather than a version mismatch.

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
`status`, `PROGRESS`'s `phase`, `INSTALLED`'s two `yes`/`no` flags, and every other
fixed-vocabulary field in `marker-protocol.md` §3's table — `AUTH`, `DONE`, `SNAPSHOTS`,
`DISK` and `REPO`'s leading words among them — are already tokens the window branches on
rather than reads out; the English *it* chooses from them is a window string, wrapped under
ONEUP-0032 like any other. A translator must never see any of these,
and a code would be a lie about what they are.

**Done when no call site interpolates text into a converted payload.** The routing rule
above decides each *field*; this is how an implementer knows the *work* is finished. Today
that means 13 `marker HINT` call sites, `end_step`'s `detail` at every call, three
`CHECK_UNKNOWN` reasons, `REMEDY`'s two actions and `reboot_reason_from_log`'s composed
phrase — and the download-size failure's four sentences, which §4.2 splits into four codes.
A converted call site passes a code and arguments; if it still builds a string, it is not
done. INV-1 is the runtime half of the same test.

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
share one field, space-separated, as `@@SERVICES@@` already does — but **only where the
values cannot themselves contain a space.** That holds for a step key, a unit name and
`@@REBOOT@@`'s four fixed components, which the engine chooses. It does **not** hold for
anything recovered from another tool's output: those take one value per trailing field
instead, and §4.1's repository names are the case that forced the distinction.

**No argument is ever prose.** Where the engine interpolates an English fragment today it
gains a distinct code instead — the download-size failure, which selects one of four
sentences by zypper's exit code and interpolates it into a fifth, becomes four codes. This
is the rule that keeps English out of the privileged half rather than merely moving it into
a field.

**Free text still applies §1.1's substitution.** Several arguments are outside the engine's
control — the lock holder's process name from `/proc/<pid>/comm`, and every value recovered
from another tool's output, of which zypper's repository names are the one that changed a
wire shape (§4.1) — so the marker emitter rewrites `|` to `/` in every argument, exactly as
`SNAPSHOT_ITEM` already does for a snapshot description. `oneup/engine/markers.py` is one
place, so it is one guard.

**Allocating one.** Whoever writes the engine branch allocates the code, in the same commit
as the branch that emits it and the window entry that renders it; the three are never
separated, and there is no register to reserve one from — the window's tables are the
register. Once shipped, a code is never reused for a different meaning — the same discipline
as a roadmap ID (`docs/standards/workflow.md` §4). Retiring one means the window keeps
rendering it for as long as an older engine could still be installed.

### 4.3 Where the wording lives, and what an unknown code shows

The tables live in `oneup/gui/markers.py` — ONEUP-0034 §4.2 already gives that module
*"reading what the engine said, and saying it in English"*, and `_step_badge` already lives
there, so this replaces its substring matching with a lookup rather than adding a layer
beside it. One table per marker family, each entry pairing the code with its English and its
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
the run's own verdict is unaffected. The failure mode of the naive version is a blank
warning banner on a run that actually failed, which is why `marker-protocol.md` §5.2
requires the fallback outright rather than leaving it to taste. (All three packaging paths
ship both halves together — `files-and-naming.md` §6 — so a mismatched pair comes from a
development checkout or a part-applied upgrade, not from an ordinary install.)

**The same fallback answers a code whose arguments do not fit its entry.** A known code can
arrive with more or fewer arguments than the window's table expects, for exactly the reason
§6 already contemplates a newer engine: an argument was added or dropped on the engine side.
Substituting a placeholder that has no value must not raise — `marker-protocol.md` §1.2
forbids a throw in the read slot outright, and §6 ranks it as a trap, because it aborts
parsing and drops the rest of the run's markers. A mismatch renders the same
no-wording-for-this sentence as an unknown code.

**A table entry declares its arguments as a fixed list or as a variable tail**, and the
arity rule applies only to the fixed part. The two list-bearing `CHECK_UNKNOWN` codes are
the variable case (§4.1) — any number of trailing names is valid data there, and only zero
of them is a defect. Every other converted code is fixed-arity.

**Every reader of a converted marker goes through these tables, not just `handle_marker`.**
`updater.py` unpacks `@@HINT@@` in three further places on the side channels —
`_on_auth_finished` and `_on_thin_finished` put the payload straight into a `QMessageBox`,
and `_on_size_output` appends it to the log — each with `line.split("|", 1)[1]`. Left alone,
those three would show the user a bare `auth-write-failed` in a message box, which is the
raw token `marker-protocol.md` §5.2 forbids and INV-3 exists to prevent. They are the
easiest site in this item to miss, because they are nowhere near the marker handler.

### 4.4 The notification the timers raise

**The headless paths stop passing `--notify`, and the window sends the notification.** The
flag is not in either systemd unit — the unit's `ExecStart` is `oneup --check` or
`oneup --update`, and `--notify` is added afterwards, inside the two headless entry points
that shell out to the engine. So no installed unit changes and none needs regenerating; what
changes is the argument list those two functions build. The engine keeps its `--notify` flag
for somebody running `./update_system.sh` in a terminal, where the notification is part of
its own English output (§10).

**The markers it needs are not the ones a run's progress uses.** The engine's own
notification is built from the error count, the installed-package count, the two
system/firmware changed flags, and the set-aside sources — so the window reads `@@CHECK@@`
(the `--check` path's totals), `@@INSTALLED@@` (the count and both flags), `@@REPO_SKIPPED@@`
(each source set aside, which the engine's own comment calls the only place an unattended
run reports what it skipped) and `@@DONE@@` (the verdict). `@@STEP_END@@` is not among them.
The failed-run notification names the log file; the window already knows that path and does
not need one sent.

**Both entry points must therefore capture the engine's output**, which today they do not —
they run it and read only its exit status. Reading the markers is new work this item adds,
not existing behaviour it reuses.

**The notification must be raisable without a display.** These two paths get a
`QCoreApplication`, not a `QApplication` — a timer may have no display — so a tray message
is not available to them. The window raises the notification the same way the engine does
today, through the desktop's notification service, and builds its text through the same
tables as everything else.

Those two paths need an application object to render through, and `main` dispatches
`--check` and `--update` before one exists — **ONEUP-0032 §4.4 owns that**, because it is a
property of the translation machinery rather than of the protocol. This item depends on it
and does not restate it. **That dependency runs the opposite way to ONEUP-0032 §4.1's**,
which has this item building the sentence tables that item then marks for translation; §3
records the ordering question the two raise together as open.

## 5. Correctness invariants

- **INV-1** Every code matches `^[a-z0-9-]+$`, and every payload field the window renders as
  words holds codes and nothing else — one code, or several space-separated, `@@REBOOT@@`
  being the only field that carries more than one. No field the window renders as words
  carries a sentence, and every `@@STEP_END@@` carries a code even where its `detail` was
  empty (§4.1). (`@@SERVICES@@` is the space-separated *format* this borrows; its own
  contents are unit names, which are data — §4.1.)
  *Test:* `tests/run-tests.sh` asserts the shape of **the code field only** — field 3 on
  `@@STEP_END@@`, field 2 on `@@CHECK_UNKNOWN@@`, field 1 on `@@HINT@@` and `@@REMEDY@@`,
  and every space-separated element of `@@REBOOT@@`'s reason — on every marker of those five
  families a scenario produces. The argument fields beside them are deliberately **not**
  shape-checked: they carry data that legitimately breaks the pattern, such as a repository
  name with spaces and capitals (§4.1) or zypper's exit status.
- **INV-2** No marker field contains a `|`: the emitter rewrites it to `/` in every argument
  before the line is printed.
  *Test:* `tests/run-tests.sh` — a lock-holder scenario whose process name contains a `|`
  produces a line the window's parser splits into the expected number of fields.
- **INV-3** A code the window has no entry for — or a known code whose arguments do not fit
  its entry (§4.3), or a step key with no entry in `TASKS` (§4.1) — renders a non-empty
  sentence that is not the code alone, at **every** site that reads that marker, and never
  raises out of the read slot.
  *Test:* `tests/gui-smoke.py` feeds an unknown code once for each of the five families §4.1
  converts, and once for each of the three side-channel `HINT` readers §4.3 names; feeds a
  known code with one argument too few and one too many; and feeds a `@@STEP_BEGIN@@` whose
  key is not in `TASKS`. Each asserts the rendered text contains the code (or key), contains
  a space, and is at least twice its length — the cheapest checkable proxy for "a sentence,
  not the token with something stuck to it" — and that parsing continues afterwards.
- **INV-4** No sentence the window *renders as its own wording* is composed by the engine.
  The desktop notification the two headless paths raise is built by the window, and neither
  passes `--notify` to the engine. The engine's ordinary terminal output is **excluded and
  stays English** — the window shows it verbatim in the log pane (`marker-protocol.md` §1),
  which §10 keeps deliberately.
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
| A known code arrives with more or fewer arguments than its entry expects | The same readable sentence naming the code | INV-3. The alternative is a throw in the read slot, which `marker-protocol.md` §1.2 forbids because it drops the rest of the run's markers |
| A step key arrives that the window has no title for | A readable sentence naming the key, in place of the step's title | INV-3. The step still runs, still badges and still counts toward the total (§4.1) |
| A source name containing a space reaches `@@CHECK_UNKNOWN@@` | Nothing — it is the final field and arrives whole | §4.1. Splitting it on spaces would report one broken source as several |
| A `\|` reaches a marker argument | Nothing — it arrives as `/` | INV-2, in one place in the emitter |
| The `STEP_BEGIN` guard is not moved with the field | The run appears to freeze while it is in fact updating | Caught the moment a scenario runs: no step ever begins. §4.1 says so because it is the one part of this item that fails loudly rather than quietly |
| The window fails to build the headless run's notification | No notification from an unattended run; the update itself is unaffected | INV-4. The engine's `--notify` still exists and a user who wants the old behaviour can call it directly (§10) |
| The retained Bash engine is run against a converted window | Prose where the window expects a code, so INV-3's fallback sentence | Deliberate and known: the fallback is frozen at the switch-over. `oneup-2.0.md` §4 requires it in the release notes, and §8 carries that |

## 7. Tests

| What it locks in | Where |
| --- | --- |
| INV-1, INV-2 — the code field's shape and the `\|` guard | `tests/run-tests.sh`, per-scenario assertions on every marker carrying a code |
| INV-3 — the fallback, at every reader of every converted family, and for an unfitting argument list and an unknown step key | `tests/gui-smoke.py`, new checks |
| INV-4 — the notification is the window's | `tests/i18n-check.py` and `tests/gui-smoke.py` |
| INV-5 — a code is never reused | **nothing.** Review only |

`tests/i18n-check.py` is ONEUP-0032's suite, and this item adds one check to it rather than
standing up a second suite — a suite has to be named by hand in `local-CI.sh` and again in
`.github/workflows/release.yml` or it runs nowhere
(`docs/standards/files-and-naming.md` §2.2). **That assumes ONEUP-0032 has already landed,
which §3.3 records as undecided**; if this item goes first, INV-4's check needs a home that
exists at the time, and §3.3's resolution is what says which.

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
  this item moves; §4.2, §4.6, §4.8 and §4.10 for the payloads that become codes; §5.1/§5.2,
  which currently reserve this work for `HINT` and `REMEDY` alone (§3.1); and **§1.1 and §6's
  free-text trap**, both of which state the `|` substitution for one field where §4.2 now
  applies it to every argument. All in the same commit as the engine and both suites, per
  that document's §5.
- **`docs/standards/wording-and-translation.md`** — §5's "today this is not yet true"
  paragraph becomes the description of what shipped.
- **`CHANGELOG.md`** — one entry under *Changed*, naming the payload conversion as a
  contract change, and saying plainly that **the retained Bash engine stops being a drop-in
  for the window**: it is frozen at the switch-over, so from this item onward it emits prose
  to a window that expects codes. It still runs an update in a terminal. `oneup-2.0.md` §4
  assigns that sentence to this item rather than leaving it to be discovered.
- **The two headless entry points** — `--notify` comes out of the argument list each builds,
  and each gains the marker capture the notification needs (§4.4). **No systemd unit
  changes**, so nothing already installed on a user's machine needs regenerating.
- **No version-site change** — none of `docs/standards/workflow.md` §5.1's six sites moves.
  This lands inside 2.0, not as a release of its own.

## 9. Alternatives considered (and rejected)

- **Convert only `HINT` and `REMEDY`, as the reference reserves.** Rejected for the two
  reasons §3.1 gives.
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
  consistency.** Rejected for the reason §4.1 gives.
- **Send `@@CHECK_UNKNOWN@@`'s source names space-separated, as `@@SERVICES@@` does.**
  Rejected: zypper names repositories in prose that routinely contains spaces (§4.1), so the
  window would report one broken source as several.

## 10. Out of scope

- **Translating the engine's terminal output.** `./update_system.sh` run directly is a
  system tool's output and stays English (`wording-and-translation.md` §5) — including the
  ordinary log lines the window shows verbatim in its log pane, which INV-4 excludes for
  this reason. Its `--notify` notification is part of that output and stays with it: what
  changes is that the headless paths stop using it, not that the flag goes (§4.4).
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
| 1 | 2026-07-31 | 2 lanes; 2 critical, 5 high, 6 medium, 11 low, 1 info — **24 verified, 0 dismissed** | The first review of this document in its own right. The critical that only running the thing could settle: §4.1 sent `@@CHECK_UNKNOWN@@`'s unreadable-source list as one **space-separated** argument, but the engine recovers those names from zypper's `Skipping repository '…'` prose, and an isolated `zypper --root` run proved zypper puts the repository **name** there — this machine's stock repositories are `Main Repository (OSS)`, `Main Update Repository`, `Open H.264 Codec (openSUSE Tumbleweed)`. `valid_alias` forbids a space but guards only the `--skip-repo` path. One broken source would have been reported as three; the names now take one trailing field each. The second critical is **surfaced, not fixed** (§3.3): this spec defers the application object to ONEUP-0032 §4.4 and adds its check to that item's suite, while ONEUP-0032 §4.1 has *this* item building the tables it marks — and `oneup-2.0.md` §5.2, which owns the order of work, ends at ONEUP-0032 and never places this item at all. Three more were contract gaps an implementer would have had to invent an answer to: `detail` **may be empty** (`marker-protocol.md` §4.2, the cache step), which would have put INV-3's unknown-code banner on every successful run; a known code arriving with the wrong number of arguments had no rule, and the substitution that follows would throw inside the read slot, which §1.2 forbids outright; and retiring `STEP_BEGIN`'s `label` left an unknown step key with no wording at all. §4.4's notification list could not rebuild what it replaces — the count and both changed-flags ride on `@@INSTALLED@@` and the set-aside sources on `@@REPO_SKIPPED@@`, neither of which it named, while `@@STEP_END@@` (which it did) is unused — and §8 sent the implementer to the systemd units, which never carried `--notify` in the first place. Dismissed: none. One lane finding was checked and found **wrong** before it was acted on — that §7 cites the wrong section of `files-and-naming.md`; §2.2 does carry the suite-naming rule. |
