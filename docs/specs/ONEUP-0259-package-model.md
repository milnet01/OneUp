# ONEUP-0259 — one package model: name, versions, size and live state for every update

**Status:** Reviewed
**Kind:** feature
**Roadmap:** ONEUP-0259
**Branch:** v2
**Verified at:** `c475e52` — every symbol below was opened on 2026-10-12, and every figure
is a dated measurement taken on this machine that day.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes loop log

**In one sentence:** after a check, and all through a run, the window holds one list of the
packages being updated — each with its old and new version, its download size and its
source — and each package moves from waiting to installed as zypper actually does the work.

**Part 1 of 3**, split from ONEUP-0239 by the user on 2026-10-12. This part builds the data.
ONEUP-0239 builds the three fixed layouts that show it; ONEUP-0260 builds the package
details dialog. Neither may start before this one is `Implemented`.

## 1. Goal

The window keeps a single package model, in a module of its own, that the three ONEUP-0239
layouts will read and never write. It is filled by two engine markers: `CHECK_ITEM`, which
gains a size and a source, and a new `PKG` marker, which seeds the list when a run starts
and then reports each package's progress. Until ONEUP-0239 ships, the existing per-row
package list shows the model: name, versions, size and state, as words.

## 2. Background

**What the window knows about a package today is one preformatted string.**
`TaskRow.add_detail_item` in `oneup/gui/task_row.py` formats `name`, `frm` and `to` into a
line and appends it to the row's `_items`. Nothing else holds per-package data. The
`CHECK_ITEM` branch of `handle_marker` in `oneup/gui/run.py` is its only caller.

**Only a check produces that list.** `_check_system` in `oneup/engine/actions.py` reads the
text table of `zypper --no-refresh --non-interactive list-updates` and emits
`CHECK_ITEM|system|name|from|to` per row; `_check_flatpak` emits one per app with an empty
`from`. A run emits no package list at all. Only "Check for updates" starts a check
(`check_btn` is connected to `run.start_check` in `oneup/gui/window.py`), and
`_reset_for_run` calls `clear_details` on every row before any engine starts. So a user who
presses Update without checking sees no packages, and one who checks first loses the list
the moment the run starts.

**No per-package size reaches the window.** `stream_filtered` in `oneup/engine/proc.py`
reads each `Retrieving:` line's own size with `parsers.retrieving_bytes`, but only adds it
to a running total for `@@PROGRESS@@`. `run_size` in `oneup/engine/actions.py` reports one
human-readable total for the whole transaction, as `@@SIZE@@|system|<text>`.

**No per-package progress reaches the window.** `stream_filtered` turns zypper's
`Retrieving:` and `( n/N) Installing:` lines into `@@PROGRESS@@|key|done|total|phase…`, which
carries counts and bytes but no package name. The names are on the lines it already reads:

```
Preloading: libglfw3-3.4-67.34.x86_64.rpm [done]
Retrieving: cpupower-lang-7.1.4-17.noarch (devel-tools) (1/77),  31.0 KiB
( 1/77) Installing: cpupower-lang-7.1.4-17.noarch [...done]
```

(The three shapes are quoted from the comment above `_RETRIEVED_BYTES` in
`oneup/engine/parsers.py`.)

**The sizes exist on disk, readable without a password.** Measured 2026-10-12:

- `/var/cache/zypp/raw/<alias>/repodata/` held a `primary.xml` for each of the eleven
  repository directories under `/var/cache/zypp/raw` (`ls -d /var/cache/zypp/raw/*` and
  `ls /var/cache/zypp/raw/*/repodata/repomd.xml`, both 11). Its files are `root:root`, mode
  `0644`.
- Each `<package>` in it carries `<size package="…">`, the download size in bytes. For
  `vlc` 3.0.24-2.1 in the main repository it read `155920`.
- Packman's `primary.xml.gz` and its `solv` index file both carried the modification time
  2026-10-12 14:05:11, so on this machine the raw copy was as fresh as zypper's index.
- A streaming parse of the main repository's `primary.xml.zst` (52,972 packages), looking
  up three packages, took 3.59 s under Python 3.13.15, decompressing through `zstdcat`.

**zypper's XML output carries the rest without root.** `/usr/share/zypper/xml/xmlout.rnc`
defines `list-updates`' `<update>` element with `name`, `edition`, `edition-old`, `arch`,
a `<summary>`, a `<description>` and a `<source alias=…>`; `zypper --xmlout repos` gives
each repository's `alias` and display `name` ("Main Repository (NON-OSS)" for
`download.opensuse.org-non-oss`, measured). Neither carries a package's download size.

**The marker contract is frozen for 2.0** (`docs/reference/marker-protocol.md` §5.1), with
one exception already used by ONEUP-0072. §3 below records the user's second.

## 3. Scope decisions (agreed with the user)

All made by the user on 2026-10-12 unless dated otherwise.

1. **Split ONEUP-0239 into three**, built in order: this item, then ONEUP-0239's layouts,
   then ONEUP-0260's details dialog.
2. **Each package shows its own state live during a run.** Approved as a second exception
   to §5.1's freeze: one new marker (`PKG`) plus two trailing optional fields on
   `CHECK_ITEM` (`bytes`, `repo`), landed in one commit with every file §5 of the
   reference lists. The user approved the `CHECK_ITEM` fields separately, after being
   told they were a change on top of the new marker.
3. **Sizes and sources show right after a check**, without a password — the reason for
   the `CHECK_ITEM` fields.
4. **Flatpak apps show no size** until ONEUP-0241 has measured a real Flatpak update. That
   item, not this one, decides what a Flatpak size means.
5. **Show the updates the way Discover does** — each package with versions and size — but
   in OneUp's own layout (2026-10-10, recorded on ONEUP-0239). This spec supplies the data;
   the look is ONEUP-0239's.

Everything else below follows from §2.

## 4. Design

### 4.1 What one package is

A package is identified by **(step key, name, edition)**. The edition is zypper's own
string — `version-release`, with an `epoch:` prefix when the epoch is not zero — so the
engine never rebuilds one from parts for the window to match against.

| Field | Meaning | Unknown is |
| --- | --- | --- |
| `key` | the step: `system` or `flatpak` | never unknown |
| `name` | the package or Flatpak application id | never unknown |
| `edition` | the version being installed | `""` — a Flatpak row can carry none |
| `old` | the version installed now | `""` |
| `size` | download size in bytes | `0` |
| `repo` | the source's display name: a repository name, or a Flatpak remote | `""` |
| `state` | see §4.4 | never unknown |

### 4.2 The markers

Two field layouts. Both are pipe-separated with no escaping (reference §1.1), so every
field the engine writes passes the checks in INV-11.

```
CHECK_ITEM|key|name|from|to[|bytes|repo]          --check only, as today
PKG|key|state|name|edition[|bytes|from|repo]       a run only
```

- `CHECK_ITEM` keeps its four fields and their meaning, and gains `bytes` (decimal, `0` for
  unknown) and `repo`. Reference §5 calls a trailing optional field the cheap change. A
  `CHECK_ITEM` carrying only `key` and `name` stays valid, as today; its versions are
  `""`.
- `PKG` is new. A `queued` line carries all seven fields; a later state needs only the
  first four. `bytes` on a `downloading` line is the size zypper printed on that line.

### 4.3 Where the engine gets each field

**The system check** (`_check_system`):

1. The listing becomes `zypper --xmlout --no-refresh --non-interactive list-updates`,
   still `LC_ALL=C`, with stderr **kept apart from stdout**: the XML parser reads stdout
   alone, so a warning on stderr cannot make it ill-formed. `proc.run` returns stdout
   only, or both merged, so this needs a capture that returns them separately — a new
   `proc` helper this spec creates. The count is the number of `<update kind="package">`
   elements. `_SKIPPED` searches stderr, and the text of each `<message>` element parsed
   from stdout. The parser returns that text unescaped, so an `&apos;` cannot hide the
   quote `_SKIPPED` matches. Which of the two carries the warning in XML mode has not
   been measured — no repository could be made to fail here without altering the
   system. The non-zero exit status stays the signal either way (§6).
2. One `zypper --xmlout repos` call maps each alias to its display name. A repository with
   no name, or a call that fails, falls back to the alias.
3. The sizes come from `oneup/engine/pkgsizes.py` (§4.5). A run always looks them up. A
   `--check` looks them up only when the engine is also given a new `--sizes` option.
   The window's own check passes it: `_engine_args` in
   `oneup/gui/run.py` appends it beside `--check`. The tray's background
   check does not: `_tray_check_args` in `oneup/gui/tray.py` passes `--check` and
   `--log=` alone. Nor does the headless `--check --notify`.
   `Options` in `oneup/engine/__main__.py` gains `sizes`, and `usage()` a line for it.
4. One `CHECK_ITEM|system|name|edition-old|edition|bytes|repo` per update, in zypper's
   order.

The parsing of step 1's XML is a function of its own in `oneup/engine/parsers.py`, so
`tests/parsers-test.py` calls it directly (`docs/standards/testing.md` §8).

**The Flatpak check** (`_check_flatpak`): `steps.flatpak_updates` returns one row per app
and version, carrying the first remote that listed it and the set of scopes (`--user`,
`--system`) that did. An app pending in both scopes is therefore one row, and the counts
follow the rows: `CHECK|flatpak|n` and `run_flatpak`'s count are both the number of rows.
The marker becomes `CHECK_ITEM|flatpak|app||version|0|remote`. `bytes` stays `0` (§3
item 4).

**A run, system step**: after the repository refresh and before `_download_pass`, the step
lists its updates exactly as the check does — the same function, unprivileged, with the
size lookup — and emits one `PKG|system|queued|…` per update. Then `stream_filtered` emits,
in addition to its `PROGRESS` markers and never instead of them:

| zypper line | `PKG` state |
| --- | --- |
| `Retrieving: <nvra> …, <size>` | `downloading`, with `bytes` from `parsers.retrieving_bytes` |
| `Preloading: <nvra>.rpm [done]` or `[already in cache]` | `downloaded` |
| `( n/N) Installing:` or `Upgrading: <nvra> …done]` | `installed` |
| `( n/N) Removing: <nvra> …done]` | `removed` |

A `Preloading:` name drops its trailing `.rpm` first. Then `<nvra>` is split from the
right: the architecture after the last `.`, then the release
after the last `-`, then the version after the `-` before it. What is left is the name.
This works because neither a version nor a release may contain `-`. The edition is
`version-release`, which keeps any `epoch:` prefix inside `version`. A `Retrieving:` line
needs no particular ending to emit. A `Preloading:` line emits only when it ends in `[done]` or
`[already in cache]`; an `Installing:`, `Upgrading:` or `Removing:` line only when its
action ends in `done]`.

**A package's own script can split that line.** Measured in a OneUp run log of
2026-10-12: `(117/320) Installing: xorg-x11-server-21.1.24-2.1.x86_64 [...`, then the
script's output (`Updating /etc/sysconfig/displaymanager ...`), then `done]` alone on
its line; another package's closed with `.done]`. So an action line with no ending is
held, and the next line that ends in `done]` and is not itself a zypper action line
completes it. The next action line, or the end of the stream, drops it unemitted.
Upgrades print `Installing:` for the new edition and no `Removing:` for the old one: in
that log, every `Removing:` line belonged to a separate removal counter (`(1/6)`).
`stream_filtered` runs only for the system step, so these are always `PKG|system|…`.

**A run, Flatpak step**: `run_flatpak` already lists the updates before updating, to count
them. It emits `PKG|flatpak|queued|app|version|0||remote` for each row. It then runs
`flatpak update --user -y` and `flatpak update --system -y` separately, and either can fail
alone. It emits `PKG|flatpak|installed|app|version` for a row only when the update of
every scope in that row's set returned 0.

**No new privileged call.** Every command above runs as the user. So no sudoers drop-in
line changes, and `.claude/rules/engine-traps.md`'s drop-in trap does not fire.

### 4.4 States, and how they move

```
queued → downloading → downloaded → installed
                                  ↘ removed
```

- A state never moves backwards. The commit pass reprints `Preloading: … [already in
  cache]` for packages already `installed`; the window ignores it.
- A package the window has never seen is added on its first `PKG` line, whatever the
  state. zypper's `dup` can change more than `list-updates` lists — a new dependency, a
  removal — so this is a normal path, not an error. Its `old`, `size` and `repo` stay
  unknown unless that line carries them.
- **After the step's `STEP_END`, a package that is not `installed` or `removed` reads as
  "not changed".** The model never infers success from the step's status (INV-7).

### 4.5 The size lookup — `oneup/engine/pkgsizes.py`

```python
SIZE_LOOKUP_SECONDS: float   # from ONEUP_SIZE_LOOKUP_TIMEOUT, default 15

def download_sizes(wanted: Iterable[tuple[str, str, str, str]],
                   deadline: float) -> dict[tuple[str, str, str, str], int]:
    """(alias, name, edition, arch) -> bytes, for each one found. Never raises."""
```

- The root is `$ONEUP_ZYPP_RAW`, defaulting to `/var/cache/zypp/raw`. Nothing else under
  `/var` is read.
- Only repositories that hold a wanted package are opened. For each,
  `<alias>/repodata/repomd.xml` names the `primary` file.
- `.gz` is read with `gzip`. `.zst` is read through `zstdcat`, streamed, the way
  `stream_filtered` streams a child: a process group of its own, killed by
  `proc.kill_group` when the deadline passes. If `zstdcat` is not on `PATH`, that
  repository yields nothing. Any other compression yields nothing.
- The parse is `xml.etree.ElementTree.iterparse`, clearing each `<package>` after reading
  it. A match needs name, architecture and edition. The edition is built from
  `<version epoch ver rel>`, with no prefix when `epoch="0"`.
- One deadline covers the whole lookup. When it passes, every package not yet found is
  `0`.

### 4.6 The window's model — `oneup/gui/packages.py`

Plain Python. It imports nothing from Qt, so a test can drive it without a window.

```python
@dataclass
class Package:
    key: str
    name: str
    edition: str
    old: str = ""
    size: int = 0
    repo: str = ""
    state: str = "queued"     # queued | downloading | downloaded | installed | removed

class PackageModel:
    def reset(self) -> None
    def add_check_item(self, parts: list[str]) -> None   # a CHECK_ITEM payload
    def apply(self, parts: list[str]) -> None            # a PKG payload
    def end_step(self, key: str) -> None                 # on STEP_END
    def packages(self, key: str | None = None) -> list[Package]   # engine order
    def finished(self, key: str) -> bool                 # STEP_END seen for key
    def subscribe(self, callback: Callable[[str | None], None]) -> None
        # called with the step key that changed; reset() calls it once with None
```

- `Updater` owns one, as `win.packages`. `_reset_for_run` calls `reset()` for a check and
  a run alike, so the model always describes the engine that is running.
- `handle_marker` feeds it: `CHECK_ITEM` to `add_check_item`, `PKG` to `apply`, and
  `STEP_END` to `end_step` in addition to what that branch does today.
- A malformed payload — fewer than two fields for `CHECK_ITEM` or four for `PKG`, an
  unknown state, a non-decimal `bytes` — changes nothing and raises nothing (INV-8). This is how `handle_marker` already guards
  `STEP_BEGIN` and `PROGRESS`.

### 4.7 Until ONEUP-0239: the per-row list shows the model

`TaskRow` drops `add_detail_item` and `_items`. It subscribes to the model and redraws its
list from `packages(key)`, one line per package: name, `old → edition`, size, and a state
word. The size uses `_format_size` in `oneup/gui/markers.py`. An unknown size prints
nothing.

The state words live in one table, `STATE_WORDS` in `oneup/gui/steps.py`, marked with
`QT_TRANSLATE_NOOP` and translated where shown, as `IN_PROGRESS` beside it is. Its keys
are the five states plus `unchanged`; its words are "waiting", "downloading",
"downloaded", "installed", "removed" and "not changed". Whole words, never colour.
ONEUP-0239's layouts read the same table.

The disclosure arrow appears when the row's first package arrives, from either marker, as
it does today on the first `CHECK_ITEM`. The list keeps `DetailScroll`'s maximum height.
ONEUP-0239 replaces this list, so nothing here is designed to outlive it.

## 5. Correctness invariants

- **INV-1** A `--check` stays read-only and rootless with the new calls in place:
  `list-updates`, `repos` and the size lookup all run without `sudo`.
  *Test:* `tests/run-tests.sh`'s existing `--check` scenarios, whose mock `zypper` exits 99
  on `dup` or `update`, plus a new scenario whose `sudo` mock fails the test if called
  during `--check`.
  *Breaks when:* any of the three is routed through `privilege.sudo`.

- **INV-2** A `CHECK_ITEM` or `queued` size is the `<size package>` of the entry with the
  same name, architecture and edition in that repository's `primary.xml`, or `0`. It is
  never another edition's size.
  *Test:* `tests/run-tests.sh` — a fixture `primary.xml.gz` under a scenario
  `ONEUP_ZYPP_RAW` holding two editions of one package with different sizes, the edition
  `list-updates` does NOT name listed first; the marker carries the size of the edition it
  does name. The order is what isolates the rule: a name-only match takes the first entry.
  *Breaks when:* the lookup matches on name alone, or on name and architecture.

- **INV-3** The size lookup reads only under `$ONEUP_ZYPP_RAW`, and the engine suite sets
  it for every invocation.
  *Test:* `run_engine` in `tests/mock-env.sh` defaults `ONEUP_ZYPP_RAW` to the scenario's
  mock directory, beside the redirects `docs/standards/testing.md` §2.1 lists; a scenario
  with an empty directory there gets `0` sizes on a machine whose real cache is full.
  *Breaks when:* a path under `/var/cache/zypp` is hard-coded, or `run_engine` misses the
  default.

- **INV-4** The size lookup is bounded. Past its deadline, every unfound size is `0` and
  the check's count and package list are unchanged.
  *Test:* `tests/run-tests.sh` — a mock `zstdcat` that sleeps past
  `ONEUP_SIZE_LOOKUP_TIMEOUT=1`; the check finishes, its `CHECK` count matches the mock
  listing, every `bytes` is `0`, and no `zstdcat` process outlives the engine.
  *Breaks when:* the read has no deadline, or the deadline drops packages from the list.

- **INV-5** A `--check` without `--sizes` does no size lookup, so the tray's background
  check never pays for one.
  *Test:* `tests/run-tests.sh` — a mock `zstdcat` that records being called; it is called
  under `--check --sizes` and not under `--check`.
  *Breaks when:* the lookup ignores `Options.sizes`, or the tray passes `--sizes`.

- **INV-6** The engine emits `installed` or `removed` only for an action that completed:
  an `Installing:`, `Upgrading:` or `Removing:` line whose action ends in `done]`, on its
  own line or on a later one (§4.3).
  *Test:* `tests/parsers-test.py` — the NVRA split and the line-to-state reader are
  called directly, over line sequences: `[...done]` and `[..done]` yield a state;
  `[...error]` does not; an action cut at `[...`, followed by a script's line and then
  `done]` alone, yields one; one cut and followed by the next action line yields none;
  and `Preloading: a-1-2.x86_64.rpm [done]` yields name `a`, edition `1-2`.
  *Breaks when:* any `Installing:` line counts as installed, a split action is lost, or
  `.rpm` is left on a `Preloading:` name.

- **INV-7** The model never shows a package as installed or removed without its own `PKG`
  line saying so. After `STEP_END`, a package in any other state reads "not changed",
  whatever the step's status.
  *Test:* `tests/gui-smoke.py` — queue `a` and `b`, install `a`, then
  `STEP_END|system|ok|…`; `a` reads "installed" and `b` reads "not changed".
  *Breaks when:* `end_step` promotes leftovers on an `ok` step.

- **INV-8** A malformed `CHECK_ITEM` or `PKG` line changes nothing and raises nothing.
  *Test:* `tests/gui-smoke.py` feeds `PKG` with three fields, an unknown state and a
  non-decimal `bytes`, then a valid line; only the valid one lands.
  *Breaks when:* a field is read without its length or type guard.

- **INV-9** A package's state never moves backwards.
  *Test:* `tests/gui-smoke.py` — `installed`, then `downloaded` for the same package; it
  stays "installed".
  *Breaks when:* `apply` assigns the state without comparing order.

- **INV-10** Every `PROGRESS` marker the engine printed before this change, it still
  prints, with the same fields and in the same order relative to the zypper lines.
  *Test:* `tests/run-tests.sh`'s existing `PROGRESS` and ONEUP-0046 canary assertions pass
  unmodified. They cover the `PROGRESS` lines
  their scenarios assert on, not every line a run can print; nothing checks the rest.
  *Breaks when:* `PKG` emission replaces a `PROGRESS` emission or changes `seen`.

- **INV-11** Every `name` the engine writes into `CHECK_ITEM` or `PKG` passes
  `steps.valid_package` — rows that fail are dropped. **This is the trust boundary**:
  package names and repository names come from repository metadata the user does not
  write, and a `|` would shift every later field. The existing defences stay:
  `markers.marker` replaces a `|` inside any field with `/`, and strips line breaks
  (`_LINE_BREAKS`).
  *Test:* `tests/run-tests.sh` — a mock repository named `Main | Extra` arrives as
  `Main / Extra`, and a listed name `-rf` produces no marker.
  *Breaks when:* a field is written without the check.

- **INV-12** A Flatpak app is `installed` only after the `flatpak update` of every scope
  that listed it returned 0, and its `bytes` is `0`.
  *Test:* `tests/run-tests.sh` — one user-only app, one system-only app, and one app
  pending in both; mock `flatpak update --user` exits 0 and `--system` exits 1; only the
  user-only app gets an `installed` line.
  *Breaks when:* `installed` is emitted before the update, regardless of its result, or
  on one scope's result for an app both scopes listed.

- **INV-13** Every state word in §4.7 is translatable, and two states never differ only by
  colour.
  *Test:* `tests/gui-smoke.py` asserts `STATE_WORDS` has a non-empty word for every state
  `PackageModel.apply` accepts plus `unchanged`, that all six words differ, and that the
  redrawn list shows the table's word for each package. **Partial**: nothing checks that
  each entry is wrapped in `QT_TRANSLATE_NOOP`; that rests on review, as it does for
  `IN_PROGRESS`.
  *Breaks when:* a state is shown by colour or an icon alone, two states share a word, or
  a word is built from pieces.

## 6. Failure modes

| Assumption | When it breaks | What the user sees |
| --- | --- | --- |
| The raw cache exists | A repository type with no `repodata/` (e.g. `plaindir`), or a cache cleaned by hand | That repository's packages show no size. The count and list are unaffected |
| `zstdcat` is installed | `zstd` is not a libzypp dependency | `.zst` repositories show no size. Nothing fails |
| The cache matches the index | A refresh between the check and the lookup | The new edition is not found; size `0`. Never a stale edition's size (INV-2) |
| `list-updates` names what `dup` installs | Tumbleweed's `dup` adds, removes or changes vendor | Extra packages appear as zypper reaches them. Listed ones zypper skips read "not changed" |
| The NVRA split matches zypper's edition | An edition string formatted differently in the two outputs | The package appears twice: the queued entry ends "not changed", and the run's entry shows the real state. Visible, and never a false "installed" |
| The window reads every marker | A window that attaches to a run already in progress (ONEUP-0045) | The list holds only packages from the markers it read. Same limit as today's badges |
| `flatpak update -y` exits non-zero when any one app fails | Not measured; no Flatpak update could be made to fail here | If it can exit 0 after one app failed, that app reads "installed". The step's own result is unaffected |
| The lookup finishes in time | A slow disk, or a very large repository | Sizes still unfound at the deadline show nothing; the check finishes on time (INV-4) |
| zypper's XML is well-formed | Output cut short by a crash | The parse fails: the check emits `CHECK_UNKNOWN|system|sources-unknown-error|<exit status>`, the code a non-zero `list-updates` exit already uses, and the badge reads "couldn't check" |

## 7. Tests

Each invariant's test is named in §5. Where they live:

- `tests/parsers-test.py` — the XML listing parser and the NVRA split (INV-6). Unit tests,
  called directly, per `docs/standards/testing.md` §8.
- `tests/run-tests.sh` — INV-1, INV-2, INV-3, INV-4, INV-5, INV-10, INV-11 and INV-12,
  through the mock sandbox. Each scenario that reaches the system listing writes its own
  mock `zypper` (the `--check` scenario's prints the text table), so each of those mocks
  gains `--xmlout list-updates` and `--xmlout repos` output; a scenario directory gains
  an `ONEUP_ZYPP_RAW` tree where it tests sizes. The existing `CHECK_ITEM` assertions are
  not changed: the suite's `check` matches a substring
  (`grep -qF`), so they still pass with the new trailing fields.
- `tests/gui-smoke.py` — INV-7, INV-8, INV-9 and INV-13's distinct words. Scenario 5b
  ("CHECK_ITEM: the expandable per-package preview") is rewritten to read the model and
  the redrawn list instead of `_items`. Its two-field `CHECK_ITEM`, and the assertion
  that such a package still lists its name, stay (§4.2).

Each new test is seen failing first: the parser tests against a stub returning nothing, the
engine and window scenarios before the emitter or the model branch exists.

## 8. Docs & release

In the commit that changes the markers, per `docs/reference/marker-protocol.md` §5:

- `docs/reference/marker-protocol.md` — §3's table gains `PKG` and `CHECK_ITEM`'s new
  fields; §4 gains a `PKG` entry with §4.4's state order and the "not changed" rule;
  §5.1 names this as the second exception.
- `docs/standards/testing.md` §2.1 — `ONEUP_ZYPP_RAW` joins the redirect list.
- `CLAUDE.md` §2 — a new example line for `--check --sizes`, beside the `usage()` line
  §4.3 adds.
- `CHANGELOG.md` `[Unreleased]` — one user-facing line: the package list shows each
  package's size, source and progress.

No sudoers or download-guard text changes (§4.3). `update_system.sh` is frozen and gains
neither marker (reference §5 item 1).

## 9. Alternatives considered (and rejected)

- **The libsolv Python bindings (`python3-solv`).** They read zypper's own index, sizes
  included. Rejected: a new runtime dependency, not installed here, and
  `docs/standards/dependencies.md` asks for none without need.
- **A privileged `zypper --xmlout dup --dry-run` at check time.** Gives the exact
  transaction. Rejected: it needs a password, and a rootless check is invariant 4 of
  `docs/standards/testing.md` §5. Its XML has no per-package size either (`xmlout.rnc`'s
  `solvable` element).
- **Sizes only from `Retrieving:` lines during a run.** No password, no cache reading.
  Rejected by the user (§3 item 3): sizes would appear only as each package downloads.
- **The window parsing zypper's lines from the log.** Rejected: the window reads markers,
  never zypper's text. That split is what lets the engine's parsing change without the
  window noticing.
- **`zypper info` per package.** Rejected: one call per package, and its size is the
  installed size, not the download (measured on ONEUP-0239: Discover's figures are
  installed sizes for the same reason).
- **Inferring "installed" for a system step's leftovers from a successful `STEP_END`.**
  Rejected: a step must never claim what it did not earn (`docs/standards/testing.md` §5).
  Flatpak differs (INV-12) because no per-app line is parsed, so the update's exit status
  is the only evidence there is (§6).

## 10. Out of scope

- The three layouts, the totals they show, and the Settings choice — ONEUP-0239.
- About and What changed for a package — ONEUP-0260.
- What a Flatpak size means — ONEUP-0241.
- A per-package download percentage. zypper prints no progress within one package; the
  `downloading` state has no percentage. Deferred; not yet queued.
- Live per-app Flatpak states during the update. Apps move from `queued` to `installed`
  together, when the update succeeds. Deferred; not yet queued.
- Package lists for firmware, leftover packages and the cache. Those steps keep their
  step-level badges. Deferred; not yet queued.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-10-12 | Q1 4 · Q2 1 · Q3 4 — 9 verified, 0 dismissed | all 9 fixed. Two lanes, each holding every question; both found the `Retrieving:` contradiction, the empty-edition gap, the merged-stderr parse risk and the Flatpak two-scope identity. Three Q1s came from settling the lanes' open questions: the tray check passes no `--notify`, the G1 citation, and the `i18n-check.py` test wording. Two measurements stay open and are written as such: zypper's XML-mode warning stream, and whether `flatpak update -y` can exit 0 after one app fails |
| 2 | 2026-10-12 | Q1 4 · Q2 2 · Q3 1 · Q4 1 — 8 verified, 0 dismissed | all 8 fixed; the cap for a spec, so this loop's fixes are read by no lane, and implementation reads them. Two lanes, each holding every question; both found the run-versus-`--sizes` contradiction and the untestable state words. One Q1 came from a measurement a lane asked for: a OneUp run log of 2026-10-12 shows a package script splitting an `Installing:` line before its `done]`. Own-fix share 5 of 8, read as a calm cap: unpropagated consequences of loop 1's decisions, not repairs of repairs. No second share: the gated change was the whole document |
