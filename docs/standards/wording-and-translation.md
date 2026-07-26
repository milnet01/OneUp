# Wording & Translation Standard

**In one sentence:** OneUp talks to someone who is not a programmer and may be having a bad
day with their computer, so every message says plainly what happened and what to do next,
never blames them, never claims something it did not check — and is written so it can be
translated into another language later without rewriting the app.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `58ea3bc` — every quoted string and symbol name below was copied from the
tree on 2026-07-26, not recalled.

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
| "GPG key verification failed for repository." | "A repository signing key is out of date. Use \"Import signing key & retry\" to fix it." |
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
  months ago is still just "a package conflict — often a third-party repo".

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

Three reasons, in the design's order of weight: it keeps translation machinery out of the
half that runs as root; it protects gate G2, which compares v1's and v2's marker streams for
equality (an engine emitting translated text would differ on a German desktop, testing the
locale rather than the rewrite); and the GUI already owns presentation.

**Today this is not yet true** — `@@HINT@@` and `@@REMEDY@@` carry English prose, as every
quotation in §2.2 shows. The transition is deliberately ordered:

1. The engine rewrite (ONEUP-0054) ships with the contract **byte-identical**, English prose
   included, and passes its gate against unchanged tests.
2. **Then**, as part of ONEUP-0032, the prose payloads become codes in one deliberate,
   versioned change — marker reference, both test suites and the GUI updated in lockstep.

Never both at once — `docs/reference/marker-protocol.md` §5.1 is canonical for that rule
and says why.

**Once that lands:** a marker payload is an **identifier, not text**. It is never
translated, never shown to the user verbatim, and renaming one is a contract change
(`docs/reference/marker-protocol.md`). The engine's terminal output — the plain log lines a
user sees when running `./update_system.sh` in a terminal — stays English, because it is a
system tool's output and the engine has no locale machinery by design.

## 6. Writing a translatable string

2.0 ships **English only**, and the machinery to translate it (design §5.1, user decision
2026-07-26). Gate **G10** tests the machinery, because untested groundwork is
indistinguishable from no groundwork by the time somebody contributes Hebrew.

There are **0** `tr()` calls in `updater.py` today and roughly 112 string-setting call sites,
so this is written as the rule for the wrapping work, not a description of it.

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
| Extract | `pyside6-lupdate` over the `oneup/` package → `oneup/translations/oneup_<lang>.ts` |
| Translate | Qt Linguist, or any `.ts` editor |
| Compile | `pyside6-lrelease oneup_<lang>.ts -qm oneup_<lang>.qm` |
| Load | `QTranslator` installed on the `QApplication` at startup, before the first widget |
| Install | `/usr/share/oneup/translations/` |

Rules:

- **`.ts` files are tracked; `.qm` files are not.** The `.ts` is the source (it holds the
  translator's work and the source-line references); the `.qm` is a build artefact,
  regenerated by the packaging step, and `.gitignore`d.
- **Catalogues live in `oneup/translations/`** — inside the one package directory, so the
  AppImage, the RPM and a plain checkout all find them by the same relative path
  (`docs/standards/files-and-naming.md` §4).
- **The file name is `oneup_<lang>.ts`**, using the Qt locale code (`oneup_de.ts`,
  `oneup_he.ts`) — lowercase language, `_XX` region suffix only when the region actually
  differs (`pt_BR`).
- **A missing catalogue is not an error.** `QTranslator.load()` returning `False` means the
  app runs in English, which is the correct behaviour, not a condition to report.
- **Extraction runs in CI once the wrapping lands**, so a string added without `tr()` is
  caught by review rather than discovered by a translator.

## 8. Traps

- **A hint that ends at the diagnosis.** "A download failed." is not a message; "A download
  failed — check your internet connection, then retry." is.
- **Wrapping a fragment because it is repeated.** Duplication across two full sentences is
  cheaper than a fragment nobody can translate. The Rule of Three does not apply to prose.
- **An f-string inside `tr()`.** `self.tr(f"Found {n} updates")` extracts the *interpolated*
  string, so the catalogue gets one entry per value of `n` and none of them ever match.
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
- [ ] Counts use the plural form; placeholders are numbered.
- [ ] Anything ambiguous out of context has a disambiguation comment.
- [ ] It is not a tool's own output passed through.
- [ ] Read it aloud as if the update just failed. Would you be reassured or annoyed?

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §2 plain English | nothing automatic |
| §3 never blame the user | nothing automatic |
| §4 never claim what was not earned | `tests/run-tests.sh` — the reboot and success invariants. A failed step is recorded, gives a hint, and claims nothing; a package-only change offers a service restart rather than a reboot |
| §6.1 every user-facing string is wrapped for translation | nothing yet — there is no `tr()` anywhere in the tree. ONEUP-0032 is groundwork, and this rule binds the code it will produce |
| §6.2 no sentence assembled by concatenation | nothing automatic |
| §6.3 plurals go through the plural form | nothing automatic |
| §7 the catalogue workflow | nothing yet — no catalogue exists |

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
