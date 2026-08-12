# ONEUP-0108 — the window's wording, and what an unknown code shows

**Status:** Draft
**Kind:** refactor
**Roadmap:** ONEUP-0108
**Branch:** v2
**Verified at:** `1432888` — every symbol named below was re-read out of `updater.py` and
`update_system.sh` on 2026-08-12, not carried forward from the parent document's stamp. A
split is not a licence to inherit a verification: `_step_badge`, `handle_marker`,
`_parse_tray_line`, `_on_auth_finished`, `_on_thin_finished`, `_on_size_output` and `TASKS`
are all in `updater.py`, `reboot_reason_from_log` is in `update_system.sh`, and the three
side-channel `line.split("|", 1)[1]` reads were each opened and checked against what §4.5
says they do.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** every English sentence a marker used to carry lives in the window, in
tables it can translate — and a code the window has never heard of produces a readable
sentence rather than a raw token, a blank banner, or an exception that drops the rest of
the run.

**This document was split out of `docs/specs/ONEUP-0072-marker-codes.md` on 2026-08-12**,
under roadmap item ONEUP-0101, which holds the measurement. That spec's fourth cold review
loop spent four of its six verified findings repairing the third loop's own fixes, against
a stop condition written down two loops earlier; §4 was 54% of an 859-line document, and
the same seam — `@@REBOOT@@`'s two disjoint vocabularies — had produced findings in three
separate loops. The split is along the halves the design already had: **ONEUP-0072 keeps
the engine side**, which field becomes a code (its §4.1) and the wire shape of one (its
§4.2); **this document takes the window side**, which is where the wording lives and what
happens when the lookup misses.

**It lands in the same commit as ONEUP-0072, and never on its own.**
`docs/reference/marker-protocol.md` §5 requires the payload conversion to be one
deliberate, versioned change across the engine, the window and both suites; splitting the
*document* does not split the *commit*. Two roadmap bullets flip together. A window
carrying these tables against an engine still sending prose renders §4.3's fallback on
every run, and an engine sending codes to a window without them shows the user raw tokens —
which is the failure `marker-protocol.md` §5.2 forbids outright.

**`docs/reference/marker-protocol.md` outranks this spec** and owns the protocol itself.
Its §5.2 reserves three questions; ONEUP-0072 §4.2 answers the two about the wire, and §4.3
below answers the one about an unrecognised code.

## 1. Goal

After this ships, the window holds every sentence it renders from a marker, in one module,
keyed by code — so a user on a Hebrew desktop sees Hebrew task badges once a catalogue for
Hebrew exists, and a developer who rewords an engine message can no longer change a badge
by accident. And the window never shows a user a bare identifier or an empty banner: a code
with no entry, a known code whose arguments do not fit it, and a step key with no title all
produce something a person can read and act on.

## 2. Background

**The evidence that the window already re-words the engine's English is ONEUP-0072 §2.1**,
and it is not restated here. What it leaves this document is the consequence: `_step_badge`
recovers a badge by testing the engine's sentence for `"up to date"`, `"already"`,
`"nothing"`, `"remov"`, `"applied"`, `"updated"`, `"update"` and `"not installed"`, and
pulls the number back out with `re.search(r"\d+", detail)`. Those substrings *are* the
window's wording table today — undeclared, untested, and keyed on an English phrase the
engine is free to change. Replacing them with a lookup is this half of the work.

**There is no fallback today, because there is nothing that can miss.** Substring matching
degrades quietly: a `detail` matching none of the branches falls through to `Done`, which
is wrong but readable. A lookup fails differently — the entry is there or it is not — so
the moment the table exists, the miss has to be designed. `marker-protocol.md` §5.2
requires it rather than leaving it to taste, and the failure mode it is guarding against is
a blank warning banner on a run that actually failed.

**Three readers of `@@HINT@@` sit nowhere near the marker handler**, on the window's side
channels, and each puts the payload in front of the user with `line.split("|", 1)[1]`.
They are the easiest site in this work to miss, and §4.5 names them.

## 3. Scope decisions

| Decision | Who, when |
| --- | --- |
| This lands in the **same commit** as ONEUP-0072, though it is a separate document | inherited — `docs/reference/marker-protocol.md` §5 |
| The fallback has **two forms**, long and short, chosen per site | this spec, §4.3 |
| `@@REBOOT@@`'s render function carries an **explicit English branch** beside the plural call | user, 2026-08-12 — §4.2 says what it costs and §9 records the two ways out not taken |
| The document is split from ONEUP-0072 rather than reviewed a fifth time | recorded in roadmap item ONEUP-0101, against a stop condition set two loops earlier |

### 3.1 What this spec does not decide

- **Which marker fields become codes.** `docs/specs/ONEUP-0072-marker-codes.md` §4.1 owns
  the routing rule, and the closed vocabularies this document renders — `@@STEP_END@@`'s
  code set and `@@REBOOT@@`'s two — are tabulated there.
- **The shape of a code, its arguments, or how one is allocated and retired.** That spec's
  §4.2.
- **How a sentence is worded.** `docs/standards/wording-and-translation.md` §2–§4. The
  conversion carries each sentence across as it stands.
- **How a sentence is marked for translation, or how a catalogue is loaded.**
  `docs/specs/ONEUP-0032-i18n.md`, which lands after this.

### 3.2 What the split costs, and what it does not

Splitting the document does not divide the work, the commit, or the review history. **Each
half runs the review gate from loop 1 on its own bytes** — the parent's four loops ran
against a document that no longer exists, and neither half may claim them. What the split
buys is that a cold reader can reach every part of each half, which is what stopped being
true of the combined document.

**ONEUP-0072's INV-3 is this document's INV-1**, renumbered because carrying a lone `INV-3`
into a three-invariant document reads as two missing invariants. §5 holds the mapping, and
that spec's INV-1, INV-2, INV-4 and INV-5 keep their numbers — `CLAUDE.md` §6 cites INV-1
by number.

## 4. Design

### 4.1 Where the tables live, and what an entry holds

The tables live in `oneup/gui/markers.py` — `docs/specs/ONEUP-0034-gui-modules.md` §4.2
already gives that module *"reading what the engine said, and saying it in English"*, and
ONEUP-0034 lands `_step_badge` there — it is in `updater.py` today — so this replaces its
substring matching with a lookup rather than adding a layer beside it. One table per marker
family the window renders as wording: four of the five ONEUP-0072 §4.1 converts,
`@@REMEDY@@` having none, because the window renders no part of its payload and the branch
that arms each action's button is its register instead (that spec's §4.2). Each entry pairs
the code with its English and its parameter names. `docs/specs/ONEUP-0032-i18n.md` owns how
that English is marked for translation.

**Step titles and in-progress phrasing are not in these tables.** They live in
`oneup/gui/steps.py` and are keyed by step, not by code (ONEUP-0072 §4.1). They are named
here only because a step key with no entry takes §4.3's fallback exactly as an unknown code
does, so an implementer will meet both rules at once.

**A table entry declares its arguments as a fixed list or as a variable tail**, and §4.3's
arity rule applies only to the fixed part. The two list-bearing `@@CHECK_UNKNOWN@@` codes
are the variable case: any number of trailing names is valid data there, so no count of
them is a mismatch. Every other converted code is fixed-arity, `@@STEP_END@@`'s included —
a step with no number emits a different code, not the same one with the field left off
(ONEUP-0072 §4.1).

### 4.2 The three entries that render a list, and the one that agrees a verb

**Some entries are not a template with placeholders, and the table has to admit it.** Three
render a *variable number* of things into one sentence — `@@REBOOT@@`'s components, and
both of `@@CHECK_UNKNOWN@@`'s list-bearing codes, `sources-unreadable` and
`flatpak-remotes-unreachable`. In another language a list is joined however that language
joins one, so all three carry a small render function rather than a format string.

**The English join is today's, reproduced exactly** — §3.1 forbids this item re-wording these
sentences, and a list separator is wording. `reboot_reason_from_log` joins one component
bare, two with ` and `, and three as `a, b, and c` with the serial comma. **Four or more
extend that last form** — `a, b, c, and d` — which the engine never produces (it reaches at
most three components) but the window can, because §4.4 inlines unknown elements into the
same join; stating it is what stops two implementers picking different separators for a case
neither can test against the engine. The two `@@CHECK_UNKNOWN@@` lists join with `, `: the
Flatpak one via `unreadable+="${unreadable:+, }$remote"`, the system one via
`tr '\n' ',' | sed 's/,$//; s/,/, /g'`. An
implementer who joins everything with `", "` has re-worded the reboot sentence, and nothing
but this paragraph and INV-2's test would catch it.

**What differs between them is the agreement, and only one has it.** `@@REBOOT@@`'s
sentence ends *"was/were installed"*, so its entry goes through the plural form
(`docs/standards/wording-and-translation.md` §6.3) and the agreement becomes the
catalogue's to decide rather than a hard-coded English rule's. **Today the engine decides
it itself** — `reboot_reason_from_log` sets `verb="were"` and then `(( ${#parts[@]} == 1 ))
&& verb="was"` — so this entry has to reproduce that behaviour, not delegate it away. That
is what the paragraph below turns on.

The two `@@CHECK_UNKNOWN@@` lists carry **no verb after the list, but they do carry
wording after it** — the list sits mid-sentence. Today the system one reads *"OneUp couldn't
read these software sources: A, B — this list may be incomplete. Running an update refreshes
them."* and the Flatpak one *"OneUp couldn't reach these Flatpak sources: A, B — this list
may be incomplete."* That trailing text is **part of each code's own wording**, not a fourth
code (ONEUP-0072 §4.1), so the render function joins the names **into** the entry's sentence
rather than terminating at them; §3.1 forbids this item dropping or re-wording the tail.
What these two lack, unlike `@@REBOOT@@`, is a verb that has to agree with the list. That
family's third code, `sources-unknown-error`, carries zypper's exit status and is an ordinary
substitution.

**The plural form alone does not cover English, so `@@REBOOT@@`'s render function carries
an explicit English branch beside the plural call.** Decided with the user 2026-08-12, from
the three options the measurement below left open.

Measured against PySide6 6.11 on 2026-08-05, with a compiled `.qm` loaded:
`QCoreApplication.translate(ctx, src, "", n)` **does** select a numerus form even when the
source string contains no `%n` — so for any language with a catalogue, the agreement works
exactly as described above. With **no** catalogue loaded it returns the source string
verbatim for every `n`. `docs/design/oneup-2.0.md` §5.1 ships 2.0 **English only** — *"No
`.ts`/`.qm` locale file for another language is written, reviewed or shipped as part of
2.0"* — and §9 records the user's decision not to build one for English either. So no
catalogue is loaded at launch, the English path is the only path that runs, and on it a
single source string cannot yield both *was* and *were* — there is no `(s)` idiom for a
verb. Left at the plural call alone, this item would **regress** wording the engine gets
right today.

So the entry keeps the plural call as its mechanism — every language with a catalogue still
gets its own forms decided there — and the render function selects *was* or *were* from **the
number of elements it renders into the sentence**: known components and inlined unknown codes
alike, because agreement follows what the sentence actually lists. §4.4's components-join
row is the case that settles it — *"a new kernel and gpu-firmware-blob were installed"* lists two things
and takes *were*, though only one of them is a component the window knows.

**This item lands before `docs/specs/ONEUP-0032-i18n.md`, which builds `oneup/gui/i18n.py`
and every catalogue load there is**, so at this item's landing no translator can be installed
and the branch is unconditional. Making it conditional is that item's, in the commit that
first installs one. **What this spec requires is INV-2's observable behaviour and nothing
more** — where the branch sits relative to the plural call is a review matter, and stating it
as a requirement would put a clause in this document that nothing could falsify.

**This is not the English branching `wording-and-translation.md` §6.3 forbids.** That rule
forbids branching *instead of* the plural form, because branching cannot produce a
language's third and fourth forms; it names `(s)` as the English fallback the source string
carries. A verb has no `(s)` idiom, so for this one sentence the branch **is** that
fallback. The two ways out not taken are in §9.

### 4.3 What an unknown code shows — the two forms

**A code with no entry renders a readable sentence, never the raw token and never an empty
banner** (`marker-protocol.md` §5.2). It says that this version of OneUp has no wording for
what the run reported, names the codes behind it, and points at the log — which is the only
honest thing it can say. **Which codes it names has three cases**, because the fallback is
reached three ways:

- **Something was unrecognised** — it names **every** code it did not recognise, all of them
  where a `@@REBOOT@@` reason carried several unknown elements, since a bug report needs the
  ones the window dropped as much as the first.
- **Everything was recognised and the field is still unrenderable** — the mixed-vocabulary
  row of §4.4 is the only case, and there is no unrecognised code to name, so it names
  **every element of the field**. Without this the sentence would name nothing and INV-1's
  length proxy would measure against an empty set.
- **A known code's arguments did not fit its entry** (below) — the code itself was
  recognised, so it names **that code**. This is the case where "unknown code" is the wrong
  words for what happened, and the sentence still has to say which code it could not
  render. It is a bug in the window, not in the run, and the run's own verdict is
unaffected. **A mismatched pair is not an exotic state: an ordinary 2.0 install ships one.**
`docs/design/oneup-2.0.md` §4 retains `update_system.sh` through 2.0 as a documented
fallback, frozen emitting prose, so running it against a converted window puts this fallback
on every worded line — which ONEUP-0072 §6's last row already records as deliberate and
known. That is the reason this rule has to be good enough to read, not merely safe.

**The same fallback answers a code whose arguments do not fit its entry.** A known code can
arrive with more or fewer arguments than the window's table expects, for the reason §6
already contemplates a newer engine: an argument was added or dropped on the engine side.
Substituting a placeholder that has no value must not raise — `marker-protocol.md` §1.2
forbids a throw in the read slot outright, and its §6 ranks it as a trap, because it aborts
parsing and drops the rest of the run's markers. A mismatch renders the same fallback as an
unknown code, **in whichever of the two forms that site takes** — so an arity-mismatched
`@@STEP_END@@` shows the bare code in its badge, exactly as an unknown one does, and never a
sentence in a slot with no room for one.

Zero names on a list-bearing `@@CHECK_UNKNOWN@@` code is the one case that should never
happen — the engine emits the code only when it has at least one — but it is a defect in
the engine, not a version mismatch, so it renders as that code's sentence with an empty
list rather than as the fallback.

**The fallback has two forms, because some of these families render into a few words rather
than a sentence. This section is the only place the choice between them is stated; §4.1, §6
and INV-1 point here rather than restating it.**

- **Long** — the sentence above. Anywhere with room for one: a hint, a warning banner, a
  remedy, the status line, the screen-reader announcement.
- **Short** — the bare code, and nothing else. It is already a short lowercase token, so it
  fits where a sentence would not: a `@@STEP_END@@` badge (beside `3 installed`), the
  progress-bar caption, and each element of a `@@REBOOT@@` join.

INV-1's *"contains a space and is at least twice the combined length of the codes or key it
names"* proxy therefore applies to the long form only; the short form is checked for being
non-empty and containing that code or key.

### 4.4 `@@REBOOT@@` — the one that renders element-wise

`@@REBOOT@@` applies the short form **element-wise** rather than to the whole field, and
the rule turns on **which vocabulary the field matches and how much of it the window
knows**, not on how many elements arrived. ONEUP-0072 §4.1 holds the two vocabularies and
the fact that they are disjoint; this is what the window does with them. The rows are tried
in order:

| The reason field | Renders |
| --- | --- |
| **absent** — `@@REBOOT@@\|yes` carrying no reason at all, which the emission shape permits: `marker REBOOT "$REBOOT${REBOOT_REASON:+\|$REBOOT_REASON}"` appends the field only when it has one. **Not the unexplained reboot** — that one emits `core-packages-updated` and takes the standalone row (ONEUP-0072 §4.1) | the reboot advice **with no reason sentence**, and never the fallback. Nothing was reported, so there is nothing the window failed to word — saying otherwise fabricates a bug report on an ordinary reboot |
| exactly one element, and it is a **known standalone reason** | that entry's own sentence, with no join frame at all — the standalone set is tested first, because it is disjoint from the components and holds zero of them by definition |
| **more than one element, and any of them is a known standalone reason** | the **long** form. The two vocabularies are disjoint by construction (ONEUP-0072 §4.1), so a field holding both is a newer engine or a bug, not data — and the join would print *"firmware-updated and a new kernel were installed"*, which is the sentence the standalone row above exists to prevent, reached the long way round |
| one or more **known components**, and no standalone reason among them | the join, with each unknown element appearing **as its own bare code** beside the ones it knows — *"a new kernel and gpu-firmware-blob were installed"*: ugly, honest, and still advice |
| one or more elements, and neither vocabulary matches any of them | the **long** form, never the join — joining would assert the unknown tokens are components, which is how *"firmware-updated was installed"* reaches a user |

**Testing the standalone set first is what makes the common non-kernel reboot work.** A
firmware-only run emits `@@REBOOT@@|yes|firmware-updated`, which holds **zero** components;
a rule keyed on how many components the window knows renders the fallback for it, on a
machine that genuinely needs rebooting. That is INV-3.

### 4.5 Every reader of a converted marker goes through these tables

Not just `handle_marker`. `updater.py` unpacks `@@HINT@@` in three further places on the
side channels, each with `line.split("|", 1)[1]`:

| Reader | What it does with the payload today |
| --- | --- |
| `_on_auth_finished` | puts it straight into a `QMessageBox` titled *"Couldn't change the setting"* |
| `_on_thin_finished` | puts it straight into a `QMessageBox` titled *"Couldn't thin snapshots"* |
| `_on_size_output` | appends it to the log pane |

Left alone, those three would show the user a bare `auth-write-failed` in a message box,
which is the raw token `marker-protocol.md` §5.2 forbids and INV-1 exists to prevent. They
are the easiest site in this item to miss, because they are nowhere near the marker
handler.

**One further reader touches a converted family and deliberately needs no table.** The tray
check runs the engine's `--check` on its own `QProcess` and parses the result in
`_parse_tray_line`, outside `handle_marker` entirely. It reads `@@CHECK_UNKNOWN@@` only to
set `self._traycheck_unknown`, a boolean — it never renders the payload — and takes
`@@CHECK@@`'s count, which is data. So it survives the conversion untouched, and it is
named here because an implementer grepping for readers will find it and needs to be told
that, rather than adding a table lookup it has no use for. It is also a reader
`marker-protocol.md` §2's table does not list at all, which §8 carries.

## 5. Correctness invariants

**INV-1 was ONEUP-0072's INV-3** and is renumbered by §3.2's rule; that document's INV-1,
INV-2, INV-4 and INV-5 keep their numbers and stay there. INV-2 and INV-3 below are new,
and both guard behaviour that spec's invariants never asserted.

- **INV-1** A code the window has no entry for — or a known code whose fixed arguments do
  not fit its entry, or a step key with no entry in `TASKS` — renders **something readable
  and non-empty** at **every** site that renders that marker, and never raises out of the
  read slot. **Which of the two forms each site takes is §4.3's.** The one case that is
  about *where* the obligation is discharged rather than which form it takes:
  **`@@REMEDY@@`**, whose payload the window renders nowhere — an unknown code arms no
  button, and the banner carries the long form instead (ONEUP-0072 §4.1). It is the only
  family whose fallback appears somewhere other than where the wording would have gone.
  *Test:* `tests/gui-smoke.py` feeds an unknown code once for each of the five families
  ONEUP-0072 §4.1 converts, and once for each of the three side-channel `@@HINT@@` readers
  §4.5 names; feeds a known code with one argument too few and one too many, asserting each
  names **that code** (§4.3's third case — the code was recognised, so there is no unknown
  one to name); feeds a
  `@@REBOOT@@` with one known and one unknown component, and one whose elements are **all**
  unknown; feeds `@@REBOOT@@|yes|firmware-updated kernel-new`, the mixed-vocabulary case
  where nothing is unrecognised, and asserts the long form names **both** elements; and feeds
  a `@@STEP_BEGIN@@` whose key is not in `TASKS`. Each asserts the
  rendered text is non-empty and contains **every** unknown code it was fed (or the key),
  and that parsing continues afterwards. **Wherever §4.3 says long form**, it also asserts
  the text contains a space and is at least twice the combined length of the codes or key
  it names — the cheapest checkable proxy for "a sentence, not the token with something
  stuck to it". The `@@REMEDY@@` case additionally asserts **no button was armed**.
- **INV-2** With no catalogue loaded, a joined `@@REBOOT@@` sentence agrees its verb with
  the number of elements it **renders** — one element reads *was*, two or more read *were* —
  counting inlined unknown codes alongside known components, because agreement follows what
  the sentence lists (§4.2, §4.4). Breaks the moment the render function is left at the
  plural call alone, which is the shape §4.2 measured and which would silently regress
  wording `reboot_reason_from_log` gets right today.
  *Test:* `tests/gui-smoke.py`, with no translator installed, feeds `@@REBOOT@@|yes|kernel-new`
  and asserts *was*; `@@REBOOT@@|yes|kernel-new kernel-modules` and asserts *were*; and
  `@@REBOOT@@|yes|kernel-new gpu-firmware-blob` — one known component, one unknown — and
  asserts *were*, which is the case that distinguishes rendered-element agreement from
  known-component agreement. All three are needed: a hard-coded *were* passes the last two,
  and known-component counting passes the first two. The two-element case additionally
  asserts the elements are joined with ` and ` rather than `, `, which is the join the engine
  produces today (§4.2) and which §3.1 forbids this item changing.
- **INV-3** A `@@REBOOT@@` reason that is a single **known standalone reason** renders that
  reason's own sentence — never the components' join frame, and never INV-1's fallback.
  Breaks the moment the render rule is keyed on how many components the field holds, since
  a standalone reason holds none; the user then sees *"OneUp has no wording for…"* on a
  machine that needs rebooting.
  *Test:* `tests/gui-smoke.py` feeds `@@REBOOT@@|yes|firmware-updated` and
  `@@REBOOT@@|yes|core-packages-updated` — both members of ONEUP-0072 §4.1's standalone
  vocabulary — and asserts each renders its own sentence, contains no *"installed"* join
  frame, and is not INV-1's fallback text.

## 6. Failure modes

| When this breaks | What the user sees | Why it is survivable |
| --- | --- | --- |
| The engine emits a `HINT` or `CHECK_UNKNOWN` code the window does not know | A readable sentence naming the code, and the log | INV-1. The run's verdict, badges and reboot advice are unaffected — only the explanation is |
| The engine emits a `REMEDY` code the window does not know | No button is offered; the banner says in the long form that this version has no fix for what the run reported, beside the run's own `HINT` | INV-1 (ONEUP-0072 §4.1). A remedy the window cannot perform is one it must not offer — arming a button for an unknown action is the worse failure |
| The engine emits an unknown `STEP_END` code, whose wording *is* the badge | The badge shows the code itself, which is a short lowercase token and fits the slot; the row still reads `ok`/`skip`/`fail` from `status`, which is a token, not a code | INV-1's short form (§4.3). The run's verdict is carried by `status`, never by the badge |
| The engine emits an unknown `@@REBOOT@@` component beside known ones | The sentence renders with the components the window does know, and names the one it does not | INV-1 per element (§4.4). `REBOOT`'s `yes`/`no` is a token, not a code, so the *advice to reboot* survives an unrenderable reason |
| The `@@REBOOT@@` reason is a **single** element the window does not know | The long fallback sentence naming the code — never the components' *"…was/were installed"* frame | §4.4's last row, the one for a field matching neither vocabulary. An unknown one-element reason belongs to neither, so joining it would assert it is a component and print *"gpu-firmware-blob was installed"*. The example has to be an **unknown** token: a known standalone reason like `firmware-updated` never reaches this row, because §4.4's standalone row catches it first and INV-3 pins that |
| A known code arrives with more or fewer arguments than its entry expects | The same readable sentence naming the code | INV-1. The alternative is a throw in the read slot, which `marker-protocol.md` §1.2 forbids because it drops the rest of the run's markers |
| A step key arrives that the window has no title for | A readable sentence naming the key in the status line and the announcement; the bare key in the progress-bar caption, which has no room for a sentence | INV-1, per site — ONEUP-0072 §4.1's table says which site takes which form, and those three are the whole of it. The step still runs and still counts toward the total. **It gets no task row and therefore no badge**: rows are built from `TASKS` and `handle_marker` reads them with `self.rows.get(key)`, which misses and returns. That is unchanged by this item, and the three sites above are the ones where the fallback has somewhere to go |
| A list-bearing `CHECK_UNKNOWN` code arrives with no names | That code's own sentence with an empty list, not the fallback | §4.3. Zero names is an engine defect, not a version mismatch, and rendering the fallback would misattribute it |

## 7. Tests

| What it locks in | Where |
| --- | --- |
| INV-1 — the fallback, at every reader of every converted family, and for an unfitting argument list and an unknown step key | `tests/gui-smoke.py`, new checks |
| INV-2 — `@@REBOOT@@`'s *was/were* agreement with no catalogue loaded | `tests/gui-smoke.py` |
| INV-3 — a known standalone reason renders its own sentence | `tests/gui-smoke.py` |

**Every check this half adds goes in `tests/gui-smoke.py`.** ONEUP-0072 §7 owns why no new
suite is stood up — `tests/i18n-check.py` is ONEUP-0032's and does not exist yet, and a
suite has to be named by hand in `local-CI.sh` and again in
`.github/workflows/release.yml` or it runs nowhere (`docs/standards/files-and-naming.md`
§2.2). That reasoning binds this half unchanged, and `tests/gui-smoke.py` is already named
in both.

**What this half's tests cannot prove is that the engine stopped emitting sentences.**
`tests/gui-smoke.py` drives the window against a mock engine, so it proves the window
renders a code correctly and nothing about what a real engine sent. That coverage is
ONEUP-0072's INV-1, in `tests/run-tests.sh`, and it is the reason neither half's suite
substitutes for the other's.

## 8. Docs & release

**All of it lands on `v2`, documentation included** — the same commit as ONEUP-0072, per
`docs/reference/marker-protocol.md` §5. `docs/standards/workflow.md` §9 sends a reference
edit to the branch rather than to `main` for exactly this case: a reference amended on
`main` would describe a contract the 1.4.0 engine `main` still ships does not implement.

- **`docs/reference/marker-protocol.md`** — **§2's reading-order table**, which lists four
  channels and gains the **tray check** it already omits today (§4.5). The rest of that
  document's edits are ONEUP-0072's, listed in its §8, and are not repeated here.
- **`ROADMAP.md`** — the ONEUP-0108 and ONEUP-0072 bullets flip to shipped **together**, in
  the one commit.
- **`CHANGELOG.md`** — no entry of its own. ONEUP-0072 §8 assigns the single *Changed*
  entry that covers the conversion; two entries for one commit would read as two changes.

**Already made, with this split** — a pointer the split itself falsified has to be corrected
at the moment it is falsified, or the two documents disagree until the code lands:

- **`docs/reference/marker-protocol.md` §5.2** reserved three questions to be answered *"in
  that spec"*, singular, when ONEUP-0072 was one document. Question 2 — where the
  code→sentence map lives, and how a code with no entry renders — is now this document's.
  §5.2 names both specs and says which question belongs to which. The substantive widening
  of §5.1 and §5.2, from `HINT` and `REMEDY` to every converted payload, is still
  ONEUP-0072 §8's and still happens in the landing commit; this was a pointer, not a
  contract change.

**One thing this section deliberately does not carry.** The `@@REBOOT@@` fragment carve-out
in `docs/standards/wording-and-translation.md` §6.2 is ONEUP-0072 §8's, because that spec's
§4.1 is where the components are defined and the carve-out is about wrapping them. This
document's §4.2 relies on it and does not re-amend it.

## 9. Alternatives considered (and rejected)

- **Ship a compiled English `.qm`, so English reaches its *was/were* forms by the same
  route every other language does.** Rejected with the user 2026-08-12: it makes 2.0 build
  and ship a translation artifact for the one language that needs none, against a §5.1 that
  ships 2.0 English-only and writes no locale file for another language. This is the
  decision that closes the gap §5.1 itself leaves open — it rules out an English one too.
  §4.2 takes the English branch instead.
- **Re-word `@@REBOOT@@`'s sentence so no agreement is needed** (*"Installed: a new kernel,
  your graphics driver"*). Rejected with the user the same day, and §3.1 forbids this item
  deciding it alone: it changes what a user reads, so it belongs to ONEUP-0064.
- **Render an unknown code as the raw token everywhere, rather than two forms.** Rejected:
  `marker-protocol.md` §5.2 forbids the raw token where a sentence would have gone, and the
  sites that genuinely have no room for a sentence — a badge, a progress caption — are few
  enough to name. One form for both would either put a paragraph in a badge or a token in a
  banner.
- **Key `@@REBOOT@@`'s render rule on the element count.** Rejected: it cannot tell a
  single known standalone reason from a single unknown token, which is the distinction that
  decides between a correct sentence and *"firmware-updated was installed"*. INV-3 is what
  holds the replacement in place.
- **Leave the three side-channel `@@HINT@@` readers rendering the payload directly**, on
  the grounds that they are error paths a user rarely meets. Rejected: they are the paths a
  user meets when something has already gone wrong, and a bare `auth-write-failed` in a
  message box is exactly the failure INV-1 exists to prevent.

## 10. Out of scope

- **Which marker fields become codes, and the wire shape of one.**
  `docs/specs/ONEUP-0072-marker-codes.md` §4.1 and §4.2.
- **Wrapping the window's own strings, loading catalogues, right-to-left.**
  `docs/specs/ONEUP-0032-i18n.md`.
- **Re-wording any message.** The conversion carries each sentence across as it stands
  (§3.1).
- **The engine's terminal output.** `./update_system.sh` run directly stays English
  (`docs/standards/wording-and-translation.md` §5), and the log pane shows those lines
  verbatim. That boundary is ONEUP-0072's INV-4, which is why it stayed there.
- **The notification the timers raise.**
  `docs/specs/ONEUP-0077-headless-notification.md`.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 0-split | 2026-08-12 | — | **Provenance, not a review — no reviewer was dispatched to produce this row.** This document was split out of `docs/specs/ONEUP-0072-marker-codes.md` under roadmap item ONEUP-0101, taking that document's §4.3 and its INV-3. The parent's four loops ran against a document that no longer exists and **are not inherited**: this one runs the gate from loop 1 on its own bytes. Three things are new here and have never been reviewed in any form — INV-2, INV-3, and §9's last three alternatives. Two are carried across as they converged: §4.2's English-branch decision (settled with the user 2026-08-12) and §4.4's render table, whose components-join and neither-vocabulary rows were the parent's loop 4 fix and is therefore the newest text in the document. The parent keeps §4.1, §4.2, INV-1, INV-2, INV-4 and INV-5, and its §11 records the split from its side. |
| 1 | 2026-08-12 | 2 lanes; Q1 2 · Q2 2 · Q3 1 · Q4 1, all 6 verified, 0 dismissed (1 of the Q1s raised by the packet build, not a lane) — no severity scale under the four-question gate, so nothing here for §7's tally check to balance (ONEUP-0100) | **Both lanes independently led with the same three, and the most valuable had survived four loops inside the parent.** §4.2 said the two `@@CHECK_UNKNOWN@@` lists' render functions *"join and stop"*; the engine puts the list **mid-sentence** — `unreadable+=" — this list may be incomplete. Running an update refreshes them."` — and ONEUP-0072 §4.1 already called that tail part of each code's wording, so an implementer would have silently dropped it, re-wording a message §3.1 forbids re-wording. Second, the verb rule was stated on the **known-component** count while §4.4's own example renders *were* for one known component beside one unknown; both readings passed INV-2's test, which fed no unknown elements. Agreement is now on **rendered** elements, and the mixed case is the third assertion in the test. Third, a reason field holding a known standalone reason **beside** known components matched no row — row 1 needs exactly one element and the join row only defined *unknown* ones — so `firmware-updated kernel-new` from a newer engine would have printed *"firmware-updated and a new kernel were installed"*, the exact sentence the table exists to prevent; §4.4 gained a row of its own for it. A lane-only Q1: §4.2 said the plural form makes agreement the catalogue's *"which is also what the engine does today"* — `reboot_reason_from_log` computes the verb itself and delegates nothing, and the paragraph four lines below rests on the opposite. And a Q4: *"the branch be written where the condition can later be added"* was a requirement nothing could falsify; deleted, with INV-2's observable behaviour left as the whole obligation. The packet build caught one no lane could: `oneup-2.0.md` §5.1 says no locale file **for another language**, which this document had twice rendered as *any* language — the distinction the whole English-branch argument turns on. **Blast-radius sweep caught four of its own**, one created inside this loop: adding §4.4's fourth row invalidated two ordinal citations (*"§4.4's second row"*, *"§4.4's third row"*) and the 0-split row's *"three-row render table"*, and §9 still carried the second copy of the locale-file overstatement. All four now cite rows by content rather than by number, which is what made them rot. Four lane open questions resolved clean: `tests/gui-smoke.py` is named in both `local-CI.sh` and `release.yml`, its `_StubProc` already drives `_on_thin_finished` so INV-1's side-channel clause is reachable, `oneup-2.0.md` §4 does support the packaging claim, and the PySide6 6.11 numerus measurement is a past-tense stamped measurement (`documentation.md` §6b.4) carried from the parent, not re-run here. |
| 2 | 2026-08-12 | 2 lanes; Q1 2 · Q2 1 · Q3 3, all 6 verified, 0 dismissed — no severity scale under the four-question gate, so nothing here for §7's tally check to balance (ONEUP-0100) | **Both lanes independently led with the same gap, and it was the one case the render table never had a row for: an absent reason field.** The engine emits `marker REBOOT "$REBOOT${REBOOT_REASON:+\|$REBOOT_REASON}"`, appending the reason only when it has one, so `@@REBOOT@@\|yes` with nothing after it is an ordinary emission — and every row of §4.4 was keyed on elements present, so it fell through to *neither vocabulary matches, whatever the element count* and rendered the no-wording-for-this banner on a machine that simply needed rebooting. A fabricated bug report, on the commonest reboot there is. The table now opens with that row and the fallback row is scoped to *one or more* elements. **One finding was this document's own loop-1 collateral**: the mixed-vocabulary row added last loop renders the long form, and the long form was defined as naming *every code it did not recognise* — in that row every element can be known, so the sentence named nothing and INV-1's length proxy measured against an empty set. §4.3 now states both ways the fallback is reached and what it names in each, and INV-1's test feeds the case. Two Q1s neither lane could have found without opening the window: *"the step still runs, still badges and still counts toward the total"* was false for an unknown step key — rows are built from `TASKS` and `handle_marker` reads them with `self.rows.get(key)`, which misses and returns, so there is no badge site at all; and the parenthetical claiming a mismatched engine/window pair *"comes from a development checkout … not from an ordinary install"* contradicted ONEUP-0072 §6's own last row, since `oneup-2.0.md` §4 retains the Bash engine through 2.0 as a documented fallback — an ordinary install ships exactly that pair, which makes this rule's readability load-bearing rather than a safety net. That sentence had been carried across from the parent, where it contradicted the same row for four loops. Also closed: an arity mismatch was said to render *the same sentence*, which puts a sentence in a `@@STEP_END@@` badge that §4.3 gives the short form; and the English **join** was nowhere pinned, so an implementer joining with `", "` would have re-worded *"a new kernel, your graphics driver, and kernel driver modules"* — §3.1 forbids that, and nothing checked it. Two lane open questions resolved clean: `handle_marker` does render `@@CHECK_UNKNOWN@@` (its dispatch has a branch for it), so that family's table is not dead; and the PySide6 numerus measurement remains a stamped past-tense measurement rather than something this run re-ran. |
| 3 | 2026-08-12 | 2 lanes; Q1 1 · Q2 2 · Q3 2, all 5 verified, 0 dismissed — no severity scale under the four-question gate, so nothing here for §7's tally check to balance (ONEUP-0100) | **The run stops at its cap, and the shape of this loop is why that is the right call rather than a shortfall: four of the five were this run's own collateral, and all four landed in one structure.** §4.4's table and the §4.3 bullets that describe it have been edited in every loop, and each edit invalidated a pointer into them. Loop 2's new top row shifted every ordinal, so *"the sentence row 1 exists to prevent"* — written in loop 1, correct then — came to name the absent-reason row instead of the standalone one; that is the **third** time an ordinal in this document has rotted, so every row is now cited by content and no ordinal reference to §4.4 remains outside the loop log. Loop 2's own absent-reason row carried a causal clause both lanes rejected: *"which the engine emits whenever it advises a reboot it cannot explain"* — the unexplained reboot emits `core-packages-updated` (ONEUP-0072 §4.1) and takes the standalone row, so the clause would have had an implementer treat that code as unreachable, which is what INV-3 exists to prevent. And loop 2's *"two cases"* for what the long form names missed the arity mismatch, which §4.3 introduces three paragraphs later — a known code, so no unrecognised one to name and INV-1's proxy measuring an empty set again. It now names that code, and the blast-radius sweep caught the count word this fix stranded (*"two cases"* heading three bullets) inside the same loop. The one finding that was **not** this run's doing came across from the parent, where it had survived four loops: §6's single-unknown-element row illustrated itself with *"firmware-updated was installed"*, and `firmware-updated` is a **known** standalone reason that never reaches that row. Genuine Q3 the completed table first made visible: the join was pinned for one, two and three elements, but the window inlines unknown elements into the same join, so four or more is reachable where the engine never goes — now stated as `a, b, c, and d`. **Out of scope, repaired in place:** the split commit left four references to `INV-3` in ONEUP-0072 after tombstoning it (§4.1 twice, §4.2 and §6's last row); all four now name this document's INV-1. Four lane open questions resolved clean — the system-sources list really is joined `, ` (`tr '\n' ',' \| sed 's/,$//; s/,/, /g'`), `sources-unreadable` really is emitted only with at least one name (the empty case emits `sources-unknown-error` instead), `handle_marker` does render `@@CHECK_UNKNOWN@@`, and the PySide6 numerus measurement stays a stamped past-tense one. **Status stays Draft: no loop returned empty.** At 473 lines this document is not oversized — the parent split at 859 — so the cap here is not the size signal; it is one section still settling, and the remedy already applied (cite rows by content, never by number) is what stops the next edit doing the same. |
