# ONEUP-0260 — the package details dialog: About and What changed for one package

**Status:** Draft
**Kind:** feature
**Roadmap:** ONEUP-0260
**Branch:** v2
**Verified at:** `61482d3` — every symbol below was opened on 2026-10-12, and every figure
is a measurement taken on this machine that day.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes loop log

**In one sentence:** clicking a system package in any of the three layouts opens a dialog
that says what the package is and, once its new version has downloaded or installed, what
changed in that version — and a package OneUp knows nothing about shows no way to open one.

**Part 3 of 3**, split from ONEUP-0239 by the user on 2026-10-12. ONEUP-0259 (the package
model) and ONEUP-0239 (the layouts) are both `Implemented`; this part reads the first and
opens from the second.

## 1. Goal

A modal dialog, opened from a package in Rows' table, Rail's board or Spotlight's two
lists. It has two sections. **About** is the package's summary, description and upstream
address, from `zypper --no-refresh info`. **What changed** is the changelog entries the new
version adds over the old one, from the downloaded package file or, once installed, from
the rpm database. Neither needs root, and neither changes the engine or the marker contract.

## 2. Background

**The window holds every package's name, versions, size, source and state, and nothing
else.** `Package` in `oneup/gui/packages.py` has the fields `key`, `name`, `edition`, `old`,
`size`, `repo` and `state`. `repo` is the repository's display name, not its alias
(`docs/reference/marker-protocol.md` §4.6).

**The package views cannot be opened today, and show no current item.** `_quiet` in
`oneup/gui/package_views.py` sets `NoEditTriggers` and `NoSelection` on all three views, and
`LinesDelegate.paint` clears `State_HasFocus`, which drops Qt's focus frame on the current
item — correctly, because that frame is a ring (`docs/standards/ui-and-accessibility.md`
§5). So arrow keys move a current item that nothing draws. A keyboard user cannot see which
package Enter would open.

**The window already runs one rootless zypper query.** `read_repos` in `oneup/gui/repos.py`
runs `zypper --non-interactive lr -u` with `LC_ALL=C`, a fixed argv and a timeout
(`docs/standards/security.md` names it as the window's one direct zypper call).

**What was measured, without root, on 2026-10-12** (libzypp 17.38.16, zypper 1.14.101):

- `LC_ALL=C zypper --no-refresh --non-interactive info bash` prints `Summary`,
  `Description` (indented continuation lines), `Upstream URL` and more, in 1.8 s. Three
  names in one call took the same 1.8 s. 1,500 names in one call took 13.5 s and printed
  1,499 `Information for package` blocks (`rpm -qa --qf '%{NAME}\n' | sort -u | head -1500`
  for the names). An unknown name prints `package 'x' not found.` and the call still exits 0.
- With `ZYPP_LOCKFILE_ROOT` pointing at a lock file naming a live process, the same call
  exited 0 and printed the package, and libzypp's log (`ZYPP_LOGFILE`) showed no global-lock
  line. Read as: a rootless `info` does not wait on a running update's lock.
- `rpm -q --qf` with `%{CHANGELOGTIME}` and `%{CHANGELOGNAME}` answered three installed
  packages and one missing one in 0.054 s. A Packman package (`libavcodec62`) answered
  `(none)`: it carries no changelog. `bash` carries 122 entries
  (`rpm -q --qf '[%{CHANGELOGTIME}\x1e]' bash | tr '\x1e' '\n' | wc -l`).
- Changelog times are dates: every `bash` entry reads `14:00:00`. Two entries on one day
  share a time.
- All six repositories here set `keeppackages=0`
  (`grep -h keeppackages /etc/zypp/repos.d/*.repo | sort | uniq -c`), so a downloaded
  package file exists only between its download and the end of the run's commit.
  `/var/cache/zypp/packages` is mode 755. It was empty, so the file's path under it is
  **not measured** (§4.3, §6).

**The marker contract is frozen for 2.0** (`docs/reference/marker-protocol.md` §5.1). This
item adds nothing to it.

## 3. Scope decisions (agreed with the user)

1. **A modal dialog, never an inline panel** — user, 2026-10-10.
2. **A package with neither About nor What changed shows no way to open one** — user,
   2026-10-12.
3. **What changed shows only once the package has downloaded or installed**, from the
   downloaded package file or `rpm --changelog`; no repository change notes are fetched —
   user, 2026-10-12.
4. **About comes from `zypper --no-refresh info`, without root** — user, 2026-10-12.

Decided here, each for the reason given in §4 or §9:

5. **System packages only.** Flatpak apps show no details mark; zypper knows nothing about
   them. What a Flatpak can report is ONEUP-0241's question.
6. **No engine change.** The window runs `zypper info` and `rpm` itself, as `read_repos`
   does. §9 records the engine route and why it lost.
7. **The upstream address is shown as text, not a link.** It comes from a repository, and
   opening it is one copy-paste away.

## 4. Design

### 4.1 Where the details come from — `oneup/gui/package_details.py`

A new module, plain Python apart from one `QProcess`, holding three things:

- **`build_info_argv(names)`** → `["zypper", "--no-refresh", "--non-interactive", "info",
  *names]`, and **`parse_info(text)`** → `{name: About}`, where `About` holds `summary`,
  `description` and `url`. It splits on `Information for package <name>:` lines; a name
  with no block, or a block with an empty summary and description, has no About.
- **`build_baseline_argv(names)`** → an `rpm -q --qf` call printing each name with its
  newest changelog entry's time and author, and **`parse_baseline(text)`** →
  `{name: (time, author)}`. `(none)` and `is not installed` lines give no entry.
- **`changelog(package, baseline)`** → the entries the new version adds (§4.3), read with
  `subprocess.run` and a 5 s timeout. rpm answers in well under a second (§2), so a
  synchronous read is the `read_repos` idiom, not a stall.

**Every name passes `_NAME_RE` before it reaches an argv**, an rpm package-name pattern
(`^[A-Za-z0-9_+][A-Za-z0-9._+-]*$`). A name that fails it gets no details and runs nothing.
The first character excludes `-`, so a name can never be read as an option. Every argv is a
list, run with no shell and `LC_ALL=C` (`docs/standards/security.md` §4.3). They are
unprivileged reads, not part of a run, so §1.5's "it goes in the engine" does not reach
them; §9 records the engine route anyway.

### 4.2 When About is fetched

**`DetailsStore`**, one per window beside the `PackageModel`, subscribes to it. When the
model gains system packages whose About has not been asked for, it starts a 500 ms
single-shot timer, restarted by each addition. When the timer fires it runs one batched
`zypper info` for every such name, through `QProcess`, and one batched baseline `rpm -q` for
the same names.

- **The timer is what makes it one call.** A check sends its `CHECK_ITEM` lines in one
  burst, and a run sends its `queued` lines in one burst after its refresh
  (`docs/reference/marker-protocol.md` §4.12), so each burst becomes one call.
- **A fetch is bounded at 60 s**, or `ONEUP_DETAILS_TIMEOUT` seconds where a test sets it.
  1,500 names took 13.5 s (§2). Past the deadline the
  process is killed; names it had not answered stay without About and are not asked again
  this session. One fetch runs at a time; names that arrive during it wait for the next.
- **The baseline is taken before the run can change it.** After a check, nothing has been
  installed. During a run, the `queued` burst comes after the refresh and before the
  commit. A package first seen after its install has no baseline (§4.3).
- **The window closing kills a running fetch.** Nothing the window spawns outlives it.
- **`PackageModel.reset()` keeps the store.** About for a name does not change between a
  check and the run that follows it, so the run re-asks nothing.

### 4.3 What changed — the entries the new version adds

**Where the new version's changelog is read from**, first match wins:

1. The package's state is `installed`: `rpm -q --qf <entries> <name>`.
2. The state is `downloaded` or `downloading`: `rpm -qp --qf <entries> <file>`, where
   `<file>` is the one match of `<name>-<edition>.*.rpm` under any directory below
   `$ONEUP_ZYPP_PACKAGES` (default `/var/cache/zypp/packages`). `<edition>` must match
   `^[A-Za-z0-9._+~^:-]+$` first, and neither part may hold a glob character. Zero
   matches, or more than one, is "not found".
3. Anything else: no What changed yet.

`<entries>` prints each entry's time, author and text, separated by `\x1e` between entries
and `\x1f` between fields, so a multi-line text stays one field.

**Which entries are new.** Walk the new version's entries newest first and stop at the
first whose time and author equal the baseline's. The entries before it are what changed.
Time alone is not enough: two entries on one day share a time (§2).

- **No baseline** (a new package, a package first seen after its install, or an old
  version with no changelog): show at most the newest 20 entries, under the sentence
  *"OneUp could not tell which of these are new."*
- **The baseline entry is never met** (the packager rewrote history): the same.
- **The new version has no entries** (the Packman case, §2): *"This package has no change
  notes."*

### 4.4 Which packages can be opened

A package **has details** when it is a system package and either `DetailsStore` holds an
About for its name, or its state is `downloading`, `downloaded` or `installed`. The second
half says What changed may exist; the dialog says so when it does not (§4.3).

**A package with details shows a mark; one without shows nothing** (§3 item 2). The mark is
`ⓘ` (U+24D8) after the name on the item's first line, in every layout. `PackageItems.data`
adds it. Its `AccessibleTextRole` text gains the words *"details available"*, so a screen
reader hears what the glyph shows, and the mark is a shape, never only a colour
(`docs/standards/ui-and-accessibility.md` §3). When About arrives the views redraw, through
the model's existing subscription.

### 4.5 Opening it

**Each view's `activated` signal opens the dialog** for the package at that index, if it
has details; otherwise nothing happens. `activated` follows the desktop's single- or
double-click setting and fires on Enter, so mouse and keyboard reach it the same way.

**The current item gets a focus cue.** While a package view has focus, `LinesDelegate`
fills the current item with the derived focus fill and draws its text in the derived ink —
`docs/standards/ui-and-accessibility.md` §5.1, with `$logbg`, the view's own background, as
both the source and the one rest pixel. It is a fill, so the no-ring rule holds. The view's
own border cue (mechanism B, ONEUP-0239 §4.8) is unchanged; the two answer different
questions — which view, and which package in it.

### 4.6 The dialog — `PackageDetailsDialog`

- Parented to the window and centred by `docs/standards/ui-and-accessibility.md` §6.2's
  idiom, with no stylesheet of its own (§6.4).
- Title: the package's name. Under it, one line: the old and new versions and the source,
  as `package_views.versions` and the repository name already read.
- One read-only `QPlainTextEdit`, object name `Log`, so it takes the log's theme and focus
  treatment. It holds an *About* heading with the summary, description and upstream
  address, then a *What changed* heading with the entries (§4.3) or the sentence saying why
  there are none. A missing About reads *"zypper has no description of this package."*
- A Close button (`#GhostBtn`); Escape closes too.
- **It reads its data once, when it opens.** It does not follow the package's state while
  open; closing and reopening reads again.
- Every sentence goes through `QCoreApplication.translate`, per
  `docs/standards/wording-and-translation.md`.

## 5. Correctness invariants

- **INV-1** No details query runs as root or through a shell: every `zypper` and `rpm` call
  the window makes for this item is a fixed list argv with `LC_ALL=C`, and none starts with
  `sudo` or `pkexec`.
  *Test:* `tests/gui-smoke.py` — the mock `zypper` and `rpm` on `_BIN` record their argv;
  after a check and a dialog open, every recorded call is checked, and the existing mock
  `sudo` records no call.
  *Breaks when:* a details call is routed through privilege, or built as a string.

- **INV-2** A package name or edition that fails its pattern reaches no argv and no glob.
  *Test:* `tests/parsers-test.py` — `build_info_argv(["bash", "-rf", "a*b"])` holds `bash`
  only, and `changelog` for a package whose edition holds `*` returns no entries without
  calling `rpm`. The leading `-` is what isolates the rule: the other two would also fail a
  plain shell-quoting check.
  *Breaks when:* `_NAME_RE` is dropped, or allows a leading `-`.

- **INV-3** What changed lists exactly the entries newer than the baseline entry, matched
  on time **and** author.
  *Test:* `tests/parsers-test.py` — a new-version changelog whose two newest entries share
  the baseline's date, one by the baseline's author and one by another; the result holds
  the other author's entry and every newer one, and not the baseline's.
  *Breaks when:* the walk compares time alone (it then stops one entry early).

- **INV-4** A system package has a details mark exactly when it has details (§4.4), and a
  Flatpak never has one.
  *Test:* `tests/gui-smoke.py` — a check whose mock `zypper info` answers one of two system
  packages; after the fetch, the answered package's item text carries `ⓘ` and its
  accessible text *"details available"*, the other's carries neither, and a Flatpak
  `CHECK_ITEM`'s item carries neither. Then a `PKG|system|installed|…` line for the second
  package gives it the mark.
  *Breaks when:* the mark is added unconditionally, or the state half of §4.4 is missing.

- **INV-5** Activating a package with details opens one dialog for that package; activating
  one without opens nothing.
  *Test:* `tests/gui-smoke.py` — in each of the three layouts, emit the view's `activated`
  for both packages of INV-4's fixture; the first opens a `PackageDetailsDialog` titled with
  its name (closed by the scheduled-dismiss idiom of §6.4), the second opens none.
  *Breaks when:* a layout's view is not connected, or the has-details test is skipped.

- **INV-6** The current item of a focused package view is drawn in the derived focus fill,
  and that fill measures at least 3:1 against `$logbg` in every theme, high contrast
  included.
  *Test:* `tests/gui-smoke.py` — `theme.focus_report` gains a row for the current-item
  pair, and the scenario asserts that row clears 3:1 for every theme, with and without high
  contrast. A grab of a focused view's current item differs from the same item unfocused.
  An item is not a widget, so ONEUP-0076's widget sweep cannot see it; the report row is
  what reaches it.
  *Breaks when:* the delegate draws no fill for the current item, or copies the hover look.

- **INV-7** A details fetch never outlives its deadline or the window.
  *Test:* `tests/gui-smoke.py` — a mock `zypper` that sleeps past a test deadline set by
  `ONEUP_DETAILS_TIMEOUT=1`; the fetch ends, the packages have no mark, and no mock process
  is left running. A second fetch closed by closing the window leaves none either.
  *Breaks when:* the `QProcess` has no deadline, or the window does not kill it on close.

- **INV-8** No test reads the real machine's rpm database or package cache.
  *Test:* `tests/gui-smoke.py` sets `ONEUP_ZYPP_PACKAGES` to a scenario directory and puts
  mock `zypper` and `rpm` on `_BIN` before the window is built; a mock that is not reached
  fails the scenario that expected it.
  *Breaks when:* a path under `/var/cache/zypp` is hard-coded, or a scenario runs before the
  mocks are in place (`docs/standards/testing.md` §2).

## 6. Failure modes

| Assumption | When it breaks | What the user sees |
| --- | --- | --- |
| A rootless `zypper info` does not wait on an update's lock | Measured against a held lock file (§2), not against a real running update | If it does wait, About arrives when the lock frees or the 60 s deadline passes; the run is unaffected |
| The downloaded file is `<name>-<edition>.<arch>.rpm` somewhere below the packages directory | Not measured: the cache was empty (§2) | What changed is "not found" while downloaded, and appears once installed |
| Every system package in the list is known to zypper | A package from a repository removed since the check | No About; it gains a mark only once downloaded or installed |
| The package carries a changelog | Packman and some third-party packages (§2) | *"This package has no change notes."* |
| The baseline was taken before the install | A window that attached to a run already past its commit | The newest 20 entries, with the sentence saying OneUp could not tell which are new |
| The font has `ⓘ` | A font with no U+24D8 | Qt's fallback font draws it; the accessible text says the same either way |
| zypper's text layout stays `Key : value` | A zypper release that changes `info`'s output | The parse finds no About: no marks until installed, never a wrong description |

## 7. Tests

Each invariant's test is named in §5. Where they live:

- `tests/parsers-test.py` — `parse_info`, `parse_baseline`, the name and edition patterns
  and the new-entries walk (INV-2, INV-3), called directly, with no process.
- `tests/gui-smoke.py` — INV-1, INV-4, INV-5, INV-6, INV-7 and INV-8. The suite gains mock
  `zypper` and `rpm` scripts on `_BIN` beside its mock `notify-send` and `sudo`, each
  printing a fixture and recording its argv, and sets `ONEUP_ZYPP_PACKAGES` to a scenario
  directory holding one fixture `.rpm` name.

Each new test is seen failing first: the parser tests against stubs returning nothing, the
window scenarios before the store, the mark or the connection exists.

## 8. Docs & release

- `docs/specs/ONEUP-0076-ringless-focus-cue.md` §4.2 — a row for the package views'
  current item: fill, source `$logbg`, rest pixel `$logbg`.
- `docs/standards/security.md` — §1's paragraph naming `read_repos` as the window's one
  direct zypper call gains `zypper info` and the `rpm` queries, and §4's pattern list gains
  `_NAME_RE` and the edition pattern.
- `docs/standards/testing.md` §2.1 — `ONEUP_ZYPP_PACKAGES` and `ONEUP_DETAILS_TIMEOUT` join
  the redirect list.
- `docs/standards/files-and-naming.md` — `package_details.py` is a new file inside
  `oneup/gui/`, so no packaging change (§6 there).
- `CHANGELOG.md` `[Unreleased]` — one line: clicking a package shows what it is and what
  changed.
- ONEUP-0239 flips to shipped once this ships (its `open_parts` refusal names this item).

No marker, engine, sudoers or download-guard change.

## 9. Alternatives considered (and rejected)

- **The engine fetches the details and sends them as markers.** It keeps every system call
  in the engine, but it reopens the frozen contract a third time (§2), needs a new engine
  mode for a dialog opened after a run ends, and gains nothing: neither query needs root,
  and `read_repos` is the precedent for the window asking zypper directly.
- **Fetch About when the dialog opens.** One package at a time costs 1.8 s per open, and
  §3 item 2 needs to know *before* the click whether a package has details.
- **A Details button beside each list, acting on a chosen package.** A second control for
  what activating the item already says, and the views have no selection to act on.
- **A `QTabWidget` with About and What changed tabs.** ONEUP-0239 §9 rejected `QTabBar` for
  its platform focus frame; one scrolling text box needs no new focus treatment.
- **The upstream address as a link.** A repository-supplied address opened with one click.
  Text costs a copy-paste and opens nothing unasked.
- **The repository's `other.xml` for the new version's notes before download.** The user
  ruled it out (§3 item 3); it is also not cached here (ONEUP-0239's measurements).
- **Comparing changelog times alone.** Two entries on one day share a time (§2).

## 10. Out of scope

- Details for Flatpak apps — ONEUP-0241 decides what Flatpak can report.
- Following a package's state while its dialog is open.
- Translating package descriptions or change notes; they are shown as zypper and rpm give
  them.
- The download-size link, the scrollbars (ONEUP-0262), and the trailer (ONEUP-0261).

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
