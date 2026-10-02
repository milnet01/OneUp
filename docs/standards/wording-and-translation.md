# Wording & Translation Standard

**In one sentence:** OneUp talks to someone who is not a programmer and may be having a bad
day with their computer, so every message says plainly what happened and what to do next,
never blames them, never claims something it did not check — and is written so it can be
translated into another language later without rewriting the app.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** v2
**Verified at:** `89c0b25` — §2.2's quotations, §4's markers, §6's PySide6 behaviour and §7's
commands were re-run against this tree on 2026-10-01, not recalled.

**Sections:** 1 who is reading · 2 plain English · 3 never blame the user · 4 never claim
what was not earned · 5 where wording lives · 6 writing a translatable string · 7 the
catalogue workflow · 8 traps · 9 before you commit · what checks this · 10 cold-eyes log

## 1. Who is reading

One person: the user of the app, sitting in front of a machine that is either updating or
has just failed to. They are **not** a programmer, they did not choose the wording of
zypper's error, and they cannot act on a stack trace.

Everything below follows from that. Where a rule seems fussy, the test is: **could the
person read this and know what to do?**

## 2. Plain English

### 2.1 The rules

**Two words are deliberately different inside and outside the app**, and neither is drift:
a *step* in the code and the marker protocol is a **task** on screen and in the README;
a *repository* to zypper is a **source** to the user. Keep each on its own side. Likewise
the code and these standards say **the GUI**; user-facing prose says **the window**.

- **Say what happened, in ordinary words.** Not "transaction aborted" — "the update
  stopped".
- **Then say what to do next.** A message that ends at the diagnosis leaves the user
  stuck. Every failure hint ends with an action, even when the action is "try again later".
- **Name the real thing.** The actual button ("Skip *packman* & update the rest"), the
  actual source, the actual command — not "the relevant option".
- **Short sentences.** Two short ones beat one with a semicolon.
- **Define a technical word inline the first time it is unavoidable**, or use a plainer one.
  "Source" beats "repository" for a user; "restore point" beats "snapshot".
- **No jargon leakage from the tools we drive.** zypper says "solver problem"; OneUp says
  "a package conflict".

### 2.2 What good looks like — from the live engine

These are the standard, not illustrations of it:

```
# update_system.sh — the held-lock hint, in the main flow
Something else is installing or removing software right now — <name> (process <pid>).
That is often OneUp's own earlier run still finishing in the background; it clears on
its own. Nothing was changed, so just run the update again in a minute.
```

Why it works: names the blocker, explains the most likely cause in the user's terms,
**states that nothing was changed** (the thing they actually want to know), and ends with an
action.

```
# update_system.sh, stop_pending — the user pressed Stop
Stopped at your request. Anything already installed stays installed — a stop never
interrupts an install half-way, because that can leave programs broken. Run the update
again whenever you like.
```

Why it works: reassures about the state of the machine before anything else, and gives the
*reason* for the cooperative-stop design in one clause rather than making it look like a
limitation.

```
# update_system.sh, refresh_repos — a slow mirror was abandoned
The '<alias>' source is serving updates too slowly to wait for, so OneUp moved on.
Use "Skip <alias> & update the rest" to leave it out of the next run, or try again later.
```

Why it works: quotes the button the user will actually click, and offers a second option
for the user who does not want to skip anything.

### 2.3 Before and after

| Don't | Do |
| --- | --- |
| "GPG key verification failed for repository." | "A source's signing key is out of date. Use \"Import signing key & retry\" to fix it." |
| "Transaction failed with exit code 4." | "The update stopped because a package conflicts with another. Check the log — you may need to turn off a third-party source." |
| "Invalid input." | "That doesn't look like a snapshot number. Pick one from the list." |
| "Operation completed successfully." | "All five tasks finished. Nothing needs a restart." |

## 3. Never blame the user

- **No "you must", "you failed to", "invalid".** The message describes the situation, not
  the person.
- **No exclamation marks on failures.** They read as scolding.
- **When the user is the cause, say it neutrally.** "Stopped at your request" — not "you
  cancelled the update".
- **Never imply carelessness.** A conflict caused by a third-party repository the user added
  months ago is still just "a package conflict — often a third-party source".

## 4. Never claim what was not earned

This is a correctness rule dressed as a wording rule, and it is the one with a bug behind
it.

**ONEUP-0056:** the check reported *"Everything is up to date. 🎉"* while the desktop's own
software centre listed eight pending updates. The check had discarded stderr and never
looked at an exit code, so it could not tell **"nothing to update"** from **"I could not
read the sources"** — and rendered the empty answer as a confident all-clear.

The rules that fall out of it:

- **An unknown is reported as an unknown.** `@@CHECK_UNKNOWN@@` exists precisely so the
  window can say "couldn't read this source" instead of counting it as zero.
- **"Up to date" is only ever said about sources that were actually read.** If one of five
  could not be read, the wording says so; it does not average the answer into a reassurance.
- **A step that failed never produces success wording**, and a run that was stopped reports
  neither success nor failure (`@@DONE@@|stopped`).
- **Never advise a reboot that was not earned** — the engine invariant (testing standard §5)
  has a wording half: no "restart recommended" appears because a step errored.
- **Numbers are what was measured.** "Reclaimed 1.4G" comes from a before/after measurement,
  not an estimate. If a figure is unknown, the sentence omits it rather than guessing.

## 5. Where wording lives

**All user-facing wording lives in the GUI. The engine emits stable codes.** (Design §5.1.)

Reasons, in the design's order of weight: it keeps translation machinery out of the half
that runs as root; an engine emitting translated text would make a marker stream depend on
the desktop's locale, so a test would be testing the locale; and the GUI already owns
presentation.

**This is true since ONEUP-0072.** The engine rewrite (ONEUP-0054) shipped with English
prose payloads, byte-identical to the Bash engine's; then ONEUP-0072 turned every payload
the window renders as its own wording into a code
(`docs/specs/ONEUP-0072-marker-codes.md` §3.1), in one change. The quotations in §2.2 are
the English those codes now carry in the window. `docs/reference/marker-protocol.md` §5.1
is canonical for why the two never happened at once.

A marker payload is an **identifier, not text**. It is never
translated, never shown to the user verbatim, and renaming one is a contract change
(`docs/reference/marker-protocol.md`). The engine's terminal output — the plain log lines a
user sees when running the engine (`python3 -m oneup.engine`) in a terminal — stays English, because it is a
system tool's output and the engine has no locale machinery by design.

## 6. Writing a translatable string

2.0 ships **English only**, and the machinery to translate it (design §5.1, user decision
2026-07-26). Gate **G10** tests the machinery, because untested groundwork is
indistinguishable from no groundwork by the time somebody contributes Hebrew.

No user-facing string is wrapped in `tr()` yet, so this is written as the rule for the
wrapping work, not a description of it.

### 6.1 Wrap every user-facing string

```python
self.tr("Run selected updates")
```

Wrapped: window titles, button and menu text, labels, tooltips, accessible names and
descriptions, banner and summary text, notification bodies, and every message built from a
marker.

Not wrapped: object names, QSS, marker names and payloads, log file contents, file paths,
step keys (`system`, `flatpak`, …), and anything only a developer reads.

### 6.2 Never assemble a sentence by concatenation

Word order differs between languages, and a fragment cannot be translated without its
sentence.

```python
# WRONG — the translator gets "updates from" with no idea what surrounds it
label = self.tr("Found ") + str(n) + self.tr(" updates from ") + alias

# RIGHT — one whole sentence; the count via tr's own plural form, the rest as
# NAMED fields the translator can reorder freely
label = self.tr("Found %n update(s) from {source}", "", n).format(source=alias)
```

- **Use placeholders, not `+` and not f-strings**, so a translator can reorder them.
- **Name the fields** (`{source}`), never positional `{}` — a translator who moves them must
  not have to track their order.
- **Never wrap a fragment** — no `self.tr("Skip ") + name`.

**One deliberate exception: `@@REBOOT@@`'s components.** The window joins them into one
*"… was/were installed"* sentence, because the alternative is a whole sentence for every
combination, which grows combinatorially with each new component
(`docs/specs/ONEUP-0072-marker-codes.md` §4.1). The table holding them,
`REBOOT_COMPONENTS` in `oneup/gui/markers.py`, says what they are joined into, and the
sentence's verb follows §6.3. Each component is written out twice — the form that opens
the sentence and the form that follows another — because a capital derived by a case
change does not exist in a language without case. One other thing may be joined from
parts.

**A list a user reads joins through a separator that is itself wrapped** —
`i18n.join_names`, or a separator wrapped where it is used, each with a
disambiguation naming the list it joins. English joins with `, `; a CJK catalogue
supplies `、` (ONEUP-0032 §4.5). A join of data no person reads as wording — an argv,
a command line, a log line — is outside this rule. Nothing else may assemble a
sentence from parts.

**A PySide6 detail worth stating, because the Qt/C++ documentation implies otherwise:**
`tr()` returns a plain Python `str`, not a `QString`, so **`.arg()` does not exist** —
verified at `879b29c` against PySide6 6.11. Qt's `%1` / `%2` placeholders therefore pass
straight through unsubstituted; use `str.format` with named fields instead. `%n` is the
exception: `tr()` substitutes it itself from the count argument.

### 6.3 Plurals go through the plural form

`self.tr("Found %n update(s)", "", n)` — not `"1 update" if n == 1 else f"{n} updates"`.
Several languages have three or more plural forms and no amount of English branching
produces them. The `(s)` is only the English fallback; the `.ts` file holds a separate,
properly inflected form per language.

**Only `self.tr(…, "", n)` inside a class extracts as a plural.** Measured 2026-10-02 on
PySide6 6.11: `QCoreApplication.translate(ctx, text, "", n)` is extracted as an ordinary
message with no plural forms, `win.tr(…)` records the variable name `win` as the context,
which never matches at run time, and PySide6 has no `QT_TRANSLATE_N_NOOP`. So a sentence
with a count that is built outside a widget class goes in `oneup/gui/i18n.py`'s `_Counted`
and is fetched with `i18n.counted(key, n)` (ONEUP-0032).

### 6.4 Add a translator comment where the string is ambiguous

A translator sees the string, not the screen. Anything that could be a noun or a verb, or
whose subject is off-screen, gets a comment — in PySide6 that is `tr()`'s second argument,
the disambiguation context:

```python
self.tr("Clean", "button that empties the package cache")
```

### 6.5 Do not build a string the user sees out of a tool's output

zypper's own wording is English, changes between versions, and is pinned to `LC_ALL=C` on
purpose (so parsing stays stable on a non-English desktop). Match on it, then write our own
sentence — never pass it through as the message.

## 7. The catalogue workflow

| Stage | Command / path |
| --- | --- |
| Extract | `pyside6-lupdate` given every `.py` file under `oneup/`, never the directory → `oneup/translations/oneup_<lang>.ts` |
| Translate | Qt Linguist, or any `.ts` editor |
| Compile | `pyside6-lrelease oneup_<lang>.ts -qm oneup_<lang>.qm` |
| Load | OneUp's catalogue and Qt's `qtbase` one, installed by `oneup/gui/i18n.py`'s `load` straight after the application object is built — the window's `QApplication`, or the `QCoreApplication` of the two timer paths — both or neither (`docs/specs/ONEUP-0032-i18n.md` INV-2, INV-9) |
| Install | `HERE/oneup/translations/` in every layout — `docs/standards/files-and-naming.md` §4 |

Rules:

- **Extract from a file list, never a directory.** Given a directory, `pyside6-lupdate`
  finds nothing and reports no error. Measured 2026-09-27 on PySide6 6.11.0: a directory,
  with or without `-recursive`, gave `Found 0 source text(s)`; the same file named directly
  gave 1. To refute, run both forms on one file holding a `QCoreApplication.translate`
  call (ONEUP-0118).
- **`.ts` files are tracked; `.qm` files are not.** The `.ts` is the source (it holds the
  translator's work and the source-line references); the `.qm` is a build artefact.
  No step builds one yet and `.gitignore` has no rule for them, so the change that first
  builds one adds that step and a `*.qm` rule.
- **Catalogues live in `oneup/translations/`.** Where each layout puts them at runtime, and
  the packaging step each one needs, is `docs/standards/files-and-naming.md` §4's.
- **The file name is `oneup_<lang>.ts`**, using the Qt locale code (`oneup_de.ts`,
  `oneup_he.ts`) — lowercase language, `_XX` region suffix only when the region actually
  differs (`pt_BR`).
- **A missing catalogue is not an error.** The app then runs in English, which is the correct
  behaviour, not a condition to report.
- **The catalogue check runs in both gates**: `tests/i18n-check.py`'s INV-8 extracts
  from the file list, finishes one message, compiles it and reads it back through Qt.
  A string added without `tr()` is never extracted; INV-7 catches it at the calls it
  lists, and only review catches one assembled into a variable first.

## 8. Traps

- **A hint that ends at the diagnosis.** "A download failed." is not a message; "A download
  failed — check your internet connection, then retry." is.
- **Wrapping a fragment because it is repeated.** Duplication across two full sentences is
  cheaper than a fragment nobody can translate. The Rule of Three does not apply to prose.
- **An f-string inside `tr()`.** `self.tr(f"Found {n} updates")` is looked up after `n` is
  filled in, so it never matches the one entry extraction recorded.
- **Reusing one string in two places with different meanings.** English collapses them,
  other languages do not; give each a disambiguation context.
- **"Up to date" as the default empty state.** The ONEUP-0056 bug in one sentence — empty is
  not the same as verified-empty.
- **Sneaking prose into a marker payload after the codes change lands** (design §5.1). It
  will pass every test and appear untranslated in every language.
- **Assuming text length.** A German string can be half again as long as its English
  original; a layout that only fits the English is broken in translation (see
  `docs/standards/ui-and-accessibility.md` §4 on fixed heights).

## 9. Before you commit user-facing text

- [ ] It says what happened and what to do next.
- [ ] It names the real button, source or command.
- [ ] It blames nobody, and has no exclamation mark on a failure.
- [ ] It claims nothing that was not actually checked or measured.
- [ ] It is one whole sentence per `tr()` call — no concatenation, no f-string.
- [ ] Counts use the plural form; placeholders are named.
- [ ] Anything ambiguous out of context has a disambiguation comment.
- [ ] It is not a tool's own output passed through.
- [ ] Read it aloud as if the update just failed. Would you be reassured or annoyed?

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §2 plain English | nothing automatic |
| §3 never blame the user | nothing automatic |
| §4 never claim what was not earned | `tests/run-tests.sh` — the reboot and success invariants. A failed step is recorded, gives a hint, and claims nothing; a package-only change offers a service restart rather than a reboot |
| §6.1 every user-facing string is wrapped for translation | **partly**: `tests/i18n-check.py` (ONEUP-0032 INV-7) fails an unwrapped literal or f-string at every call on its closed list of text-setting calls and helpers. A sentence assembled into a variable before the call is invisible to it, so review stays beside it |
| §6.2 no sentence assembled by concatenation | **partly**: the same INV-7 fails a `+`, a `%`, a `.format` on anything not translated, and a `.join` on a literal separator at those calls; INV-12 fails a literal-separator join or case change anywhere under `oneup/gui/` that is not on its list of data sites. Concatenation into a variable is review's |
| §6.3 plurals go through the plural form | **partly**: INV-8 asserts the `_Counted` sentences extract as plurals. Nothing catches a count written into an ordinary `translate` call |
| §7 the catalogue workflow | `tests/i18n-check.py` (ONEUP-0032 INV-8): extraction from the file list reaches the window and its tables, and a finished translation survives compile and load |

**§4 is the one rule here with real teeth, and it is not a wording rule by accident.** "Never
claim what was not earned" is testable because it is a claim about *state*, not about prose:
a marker either says a reboot is needed or it does not. The rest of this standard governs how
a true sentence is phrased, which no script can judge — so §9's checklist is the catcher, and
review is the backstop.

## 10. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document was one of three lanes the breadth pass accepted clean. Its share: a bare "§5.1" that meant the *design's* §5.1, and a paragraph restated verbatim from `docs/reference/marker-protocol.md` §5.1, now a pointer |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged. Nothing from loop 1 resurfaced in this lane, which is the proof those fixes held. The two findings that verified are logged against `files-and-naming.md` and `workflow.md` |
| 3 | 2026-07-26 | none | clean. |
| 4 | 2026-07-26 | none | converged. |
| 5 | 2026-10-01 | Packet build, then 2 lanes, cold, dispatched from outside the project; genre pinned standard; every lane held every question. Q1 2 · Q2 5 · Q3 1 — 8 verified, 1 dismissed, all 8 fixed: 4 found building the packet (`896420e`, `ea12b6e`), 4 by the lanes | **A pure audit (ONEUP-0107): no change armed it, so there is no armed-span share.** The four-question gate's first read of this document. **Packet**: §9 said placeholders are numbered where §6.2 requires named [Q2]; §7 said the `.qm` is rebuilt by packaging and git-ignored — neither exists [Q1]; §5 listed the codes change's files without the engine [Q2]; §7's Install path disagreed with the RPM's `cp -a oneup` and `files-and-naming.md` §4 [Q2, v2 only]. **Lanes**: §7 said CI extraction catches a string added without `tr()` — measured, an unwrapped string is never extracted [Q1, both lanes]; §7 loaded one translator where ONEUP-0032 INV-2 loads OneUp's and `qtbase` both or neither [Q2, both lanes]; §2.3 and §3 showed users "repository"/"repo", which §2.1 forbids [Q2]; the packet fix's "adds both" read two ways [Q3, own fix]. **Dismissed**: §8's f-string trap said lupdate extracts one entry per value of `n` — measured, it extracts the template once; the rule holds, the explanation was narrowed. Four open questions resolved clean. Code side surfaced, not edited: both engines' signing-key hint still says "repository" |
| 6 | 2026-10-01 | 2 lanes, cold, briefed exactly as loop 5 plus one entry under already-surfaced (the engines' "repository" hint); every lane held every question. Q1 2 — 2 verified, 0 dismissed, all 2 fixed | **[Q1], on loop 5's own text**: §7 said CI extraction proves the catalogue builds — ONEUP-0032 INV-8 compiles and round-trips a finished translation; the bullet now leaves what the check runs to INV-8. **[Q1], both lanes, pre-existing**: §5 named `@@HINT@@` and `@@REMEDY@@` as the prose payloads the codes change converts; `CHECK_UNKNOWN` carries prose too, and design §5.1 and ONEUP-0072 §3.1 convert every payload the window renders. Own-fix share: 1 of 2. Four open questions resolved clean. Out of scope, carried to its own run: `marker-protocol.md` §5.1 and §5.2 still limit ONEUP-0072 to `HINT` and `REMEDY` |
| 7 | 2026-10-01 | 2 lanes, cold, briefed exactly as loop 6; every lane held every question. None — 0 verified, 0 dismissed | **Converged**: both lanes returned no findings, on the third loop of the run (the cap for a standard, reached empty rather than binding). Five open questions resolved clean, two by measurement: `pyside6-lupdate` extracts a `#:` comment as `<extracomment>` and the second `tr()` argument as `<comment>`; a lookup with an edited second argument still found its translation. Out of scope, filed: `testing.md` §5 invariant 2 requires "a plain-English `@@HINT@@`", which ONEUP-0072's codes make false |
