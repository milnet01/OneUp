# ONEUP-0034 — splitting the window into modules

**Status:** Draft
**Kind:** refactor
**Roadmap:** ONEUP-0034
**Branch:** v2
**Verified at:** `03435ba` — every figure below was measured against this tree, not recalled.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** `updater.py` is cut into a package of small modules that each do one
job, and the app behaves exactly as it does today — same window, same wording, same
behaviour, only the file boundaries move.

**The programme design owns everything 2.0's items share** — the `oneup/` package layout
(`docs/design/oneup-2.0.md` §4), the order the items are built in (§5.2), the branch each
lands on (§5.3), the `main` freeze (§5.4) and the release gate (§7). This spec settles only
what is particular to the window, and points at the design for the rest so the two cannot
drift.

## 1. Goal

The window lives in `oneup/gui/`, as modules a reader can hold in their head one at a time.
`updater.py` stays at the repo root and becomes the few lines that start it. Nothing the
user can see changes: the same widgets, the same wording, the same accessible names, the
same behaviour on every marker the engine prints. The existing GUI suite is what proves it,
because a behaviour-preserving change is exactly the kind the current assertions can judge.

## 2. Background

`updater.py` is **more than six times** `docs/standards/coding.md` §4.1's 600-line soft
ceiling, and one class inside it — `Updater(QMainWindow)` — is nearly four times the ceiling
on its own. (The measured line counts, dated, are `docs/design/oneup-2.0.md` §2;
`docs/standards/documentation.md` §6b.2 is why the multiple is quoted here and the count is
not.)

That single class holds, at least: the whole window's construction, the run it drives, the
`@@MARKER@@` handling, three banners and their remedy actions, the tray, the autostart
desktop file, two systemd user timers, the passwordless-sudo setting, snapshot thinning and
rollback, the text-size and contrast settings, the diagnostics dump and the update check.
No part of it can be read, reviewed or tested without the rest.

**Two obstacles were measured before this spec was written, and both change what the first
commit has to be.**

**The test harness breaks before any window code moves.** `tests/gui-smoke.py` loads the
window with `importlib.util.spec_from_file_location("updater", REPO / "updater.py")` and
never puts the repo root on `sys.path`. Run as `python3 tests/gui-smoke.py`, `sys.path[0]`
is `tests/`. The moment the root `updater.py` contains `from oneup.gui.app import main`,
that load raises `ModuleNotFoundError: No module named 'oneup'` — verified at `03435ba` by
building the same three-file shape (a root shim, a package beside it, a loader in a
subdirectory) in a scratch directory and running it. Inserting the repo root into `sys.path`
before the load fixes it, verified the same way. **The harness moves first, on its own, and
is proved green before a single symbol is extracted.**

**A test that patches a re-exported name silently stops patching anything.** The same
scratch run confirmed the mechanism: bind a name into a shim with `from … import STATE`,
then reassign `shim.STATE`, and the function that reads `STATE` in its own module still sees
the original. `tests/gui-smoke.py` does exactly this today, in three places that matter —
`updater.RUN_STATE`, `updater.STOP_REQUEST` and `updater.ZYPP_PACKAGE_CACHE` — and it does
it for the reason `docs/standards/testing.md` §2 exists: so the suite cannot touch the
machine it runs on. After a naive split those three assignments would land on a shim nobody
reads, the suite would stay green, and the window under test would delete the **real**
`~/.local/state/oneup/run.state` of whatever run the developer had going. That has happened
here before, which is why it is a trap in `CLAUDE.md` §6 and an invariant below.

## 3. Scope decisions (agreed with the user)

| Decision | Who, when | Consequence |
| --- | --- | --- |
| The split is a separate item from the engine rewrite, with its own spec | the user, 2026-07-26 | this spec exists; `ONEUP-0054` §3.1 states the other half |
| It lands on `v2`, not `main`, and is the first substantial work there | the user, 2026-07-26 | `docs/design/oneup-2.0.md` §5.3; it lands alone, so the GUI assertions judge it with nothing else in flight |
| It is **behaviour-preserving** — no user-visible change | the user, from the roadmap bullet | §5; the redesign is ONEUP-0064 and comes after |
| The on/off switches stay | the user, standing | `ToggleSwitch` moves as it is; nothing about it is reconsidered here |
| ONEUP-0059 (XDG paths) rides along | `docs/design/oneup-2.0.md` §6.5 | §4.6 |

### 3.1 What this spec does not decide

The package layout — `oneup/` with `gui/`, `engine/` and `translations/`, and `updater.py`
kept at the root — is `docs/design/oneup-2.0.md` §4, restated as rules in
`docs/standards/files-and-naming.md` §4. This spec obeys it and does not re-argue it.

## 4. Design

### 4.1 What does not change

- **The window never runs as root and calls no `sudo`.** `docs/standards/security.md` §1.4
  owns the boundary, including the window's three `pkexec` actions. No module moves a
  privileged call across it.
- **The marker protocol.** `docs/reference/marker-protocol.md` is frozen for 2.0. Every
  marker the window handles today it handles identically afterwards.
- **The step keys and their order** — `system, flatpak, firmware, orphans, cache`. `TASKS`
  moves file, not content.
- **Every user-visible string.** Translation is ONEUP-0032 and comes last (design §5.2);
  wrapping strings here would mean wrapping them twice.
- **`updater.py` is still the thing you launch.** The desktop entry's `Exec=oneup`, the
  RPM's `/usr/bin/oneup` wrapper (`exec python3 %{_datadir}/oneup/updater.py "$@"`), the
  AppImage's PyInstaller entry point and every hand-made launcher all name it.

### 4.2 The modules

One responsibility each, named for what it does
(`docs/standards/files-and-naming.md` §4.1 rule 3). The **owns** column is the contract:
every symbol named there has a home, and nothing in `updater.py` is left unplaced.

| Module | Owns | In one sentence |
| --- | --- | --- |
| `oneup/__init__.py` | `APP_ID`, `APP_NAME`, `APP_VERSION`, `REPO_SLUG` | who the application is, and the version site `bump.py` writes |
| `oneup/gui/__init__.py` | nothing | the package marker; no logic, no re-exports |
| `oneup/gui/paths.py` | `HERE`, `_find_engine`, `ENGINE`, `ENTRY_POINT`, `STATE_DIR`, `HISTORY`, `LOG_DIR`, `RUN_STATE`, `STOP_REQUEST`, `ZYPP_PACKAGE_CACHE` | where everything OneUp reads or writes lives |
| `oneup/gui/steps.py` | `TASKS` | the five update steps, their keys, titles and order |
| `oneup/gui/theme.py` | `_QSS`, `_HC_QSS`, `_DARK`, `_LIGHT`, `_HC_DARK`, `_HC_LIGHT`, `ACCENT`, `BTN_ACCENT`, `GREEN`, `RED`, `TEXT_SCALES`, `_FONT_SCALE`, `_font_metrics`, `build_theme`, `apply_app_theme`, `current_is_dark` | what the app looks like |
| `oneup/gui/placement.py` | `_on_wayland`, `run_kwin_script`, `center_on_parent` | putting a window where the user expects to find it |
| `oneup/gui/markers.py` | splitting a marker line into its name and fields; `_step_badge`, `_format_duration`, `_format_size` | reading what the engine said, and saying it in English |
| `oneup/gui/diagnostics.py` | `_os_release_pretty`, `_latest_run_log`, `build_diagnostics`, `cache_bytes`, `DIAG_LOG_CAP` | describing this machine when the user reports a problem |
| `oneup/gui/toggle_switch.py` | `ToggleSwitch` | the phone-style on/off switch |
| `oneup/gui/task_row.py` | `TaskRow` | one task's row: its switch, badge, timing and details |
| `oneup/gui/repos.py` | `_ALIAS_RE`, `_parse_repos`, `_repo_purpose`, `read_repos`, `RepoManagerDialog` | reading and editing the machine's software sources |
| `oneup/gui/rollback.py` | `RollbackDialog`, snapshot thinning and the rollback call behind it | going back to a snapshot |
| `oneup/gui/autostart.py` | the autostart desktop file, both systemd user timers, `_headless_command` | running OneUp without being asked to |
| `oneup/gui/tray.py` | the tray icon, its background check, the single-instance socket, `TRAY_*` | living in the system tray |
| `oneup/gui/auth.py` | reading, enabling and disabling passwordless authentication | the "don't ask for my password" setting |
| `oneup/gui/banners.py` | the reboot, info and warning banners and their remedy actions | telling the user what went wrong and offering the one thing that fixes it |
| `oneup/gui/run.py` | the run's `QProcess`, its argv, marker application, the activity clock, end-of-run, `STALL_SECONDS` | one update run, from Run to the summary |
| `oneup/gui/settings_dialog.py` | `SettingsDialog` | the popup that hosts the background-behaviour toggles |
| `oneup/gui/window.py` | `Updater` — construction and layout, attaching to a run in flight, quitting, the dialog openers, run history, text size and contrast, `STALE_AFTER_DAYS` | the window itself |
| `oneup/gui/app.py` | `_app_icon`, `_headless_check`, `_headless_update`, `_raise_existing_instance`, `main` | starting OneUp, with a window or without one |
| `updater.py` (repo root) | imports `main` from `oneup.gui.app` and calls it | the thing you launch |

**`window.py` will not fit under the 600-line ceiling, and this spec does not pretend it
will.** The ceiling is soft — `docs/standards/coding.md` §4.1 calls it *"a prompt to ask
what second responsibility has moved in"* — and the honest answer is that a window's
construction and its layout are one responsibility that is simply large. Every **other**
module here fits, and the class stops being six times the ceiling. Getting `window.py`
itself under is the interface redesign's (ONEUP-0064) to attempt, and it is not promised
here.

**`SettingsDialog` is a host, not an owner.** It re-parents buttons the window builds and
owns — `tests/gui-smoke.py` asserts exactly that, checking `w.auth_btn` and
`w.autoupdate_btn` are among the dialog's children. It gets its own small module because it
is a dialog with a `showEvent`, not because it owns the settings.

### 4.3 The import direction

1. **No module under `oneup/engine/` imports from `oneup.gui`.** Gate **G5** proves the
   engine imports no Qt; it does **not** catch an engine module importing a Qt-free helper
   out of `oneup/gui/`, which would pass G5 and still invert the dependency.
   `docs/standards/files-and-naming.md` §4.1 rule 2 assigns that stronger check to this
   spec, and INV-3 is it. It is **vacuously true until `oneup/engine/` exists** — that is
   the point of writing it now, so it is already in place when ONEUP-0054 starts.
2. **`window.py` may import any other `oneup/gui/` module; none of them imports
   `window.py`.** A subsystem that needs the window is handed it, at construction, by the
   window. This is the rule that keeps the split from becoming a ring of files that can only
   be read together.
3. **`updater.py` imports from `oneup.gui.app` and nothing else, and nothing in `oneup/`
   imports `updater`.** Run as `python3 updater.py` the entry point is `__main__`, so an
   `import updater` from inside the package would execute the file a second time under a
   second name — two `QApplication` set-ups, two of everything.

### 4.4 Two rules about module-level names, both of which have a bug behind them

**A path constant is read through its module, never bound by name.** Write
`paths.RUN_STATE`, not `from .paths import RUN_STATE`.

`docs/standards/files-and-naming.md` §5.2 requires the `HOME`-rewriting trick to keep
working, which means these stay module-level constants computed once at import. §2 above
shows what a `from … import` does to that: the reader keeps its own binding, the test's
reassignment lands somewhere nobody reads, and the suite goes green while the window edits
the real file. Reading through the module is what leaves exactly one place to redirect. The
same applies to `ZYPP_PACKAGE_CACHE`, which `cache_bytes` reads, and to `STALL_SECONDS`.

**No module builds a path from its own `__file__`.** `HERE` is computed once, in `paths.py`,
and imported. `docs/standards/files-and-naming.md` §4.2 states the rule and why: a module
under `oneup/gui/` that computes the same expression gets `oneup/gui/`, so `_find_engine`
looks for `update_system.sh` in the wrong directory and the Run button fails.

There is a second, quieter instance of that trap in the tree, and it is in a method this
split moves. `Updater._headless_command` builds the command systemd's timers run, and its
last resort is `Path(__file__).resolve()` — the entry point today. Moved into
`oneup/gui/autostart.py` unchanged, it would write a unit that runs
`python3 …/oneup/gui/autostart.py --check`, which does nothing at all. **The existing
assertions pass either way** — they check the string ends with the flag and starts with a
quote. That branch is reached only when neither `$APPIMAGE` nor an `oneup` launcher is
found, so on a developer machine with the launcher installed it is not exercised at all.
`paths.ENTRY_POINT` exists for this: the root `updater.py`, resolved once, in the one module
allowed to know where things are.

### 4.5 What the tests reach for, and what that obliges

`tests/gui-smoke.py` reaches into the loaded module for more than the window class. Every
name below is used today, verified at `03435ba`; each needs a decided home, because a name
the tests read is part of this refactor's contract whether or not it is public.

| What the suite does | Where it must point afterwards |
| --- | --- |
| `updater.Updater()`, `updater.SettingsDialog`, `updater.RollbackDialog`, `updater.ToggleSwitch` | the classes' new modules |
| `updater.Updater._format_duration`, `._headless_command` | `markers.py` and `autostart.py` — both stop being methods |
| `updater.cache_bytes`, `updater.center_on_parent`, `updater._on_wayland` | `diagnostics.py` and `placement.py` |
| **assigns** `updater.RUN_STATE`, `.STOP_REQUEST`, `.ZYPP_PACKAGE_CACHE` | `paths.<NAME>` — and the code must read them the §4.4 way, or the redirect is a no-op |
| **reads** `updater.STALL_SECONDS` | `run.STALL_SECONDS` |
| **patches** `updater.subprocess.run`, then calls `updater._headless_update()` | `app.subprocess` and `app._headless_update` — the **same** module, or the patch misses (§6) |
| `updater.QWidget`, `updater.QDialog` | it already imports both from `PySide6.QtWidgets` directly; use those |

**The suite is updated in the same commit as the move it follows**, never in a separate
tidy-up. A green suite pointing at the old names is a suite that stopped testing.

### 4.6 ONEUP-0059 rides along, in one commit across both halves

`docs/design/oneup-2.0.md` §6.5 puts the XDG path change here, because `paths.py` is where
the window's path constants land. Honour `XDG_STATE_HOME` where it is set; the default is
unchanged where it is not. (`XDG_CONFIG_HOME` needs no work — settings go through
`QSettings("OneUp", "OneUp")`, which Qt already resolves under it.)

`run.state` and `stop.request` are a contract between the two halves, so **the Bash
engine's `RUN_STATE_FILE` and `STOP_FILE` move in the same commit**, even though the engine
rewrite is several items away. Move one side alone and, on a machine with `XDG_STATE_HOME`
set, the window writes `stop.request` where the engine never looks: Stop quietly stops
working, and nothing fails anywhere. `ONEUP-0054` §4.1.1 pins the files' layout; the design
settles their location.

### 4.7 Ordering, where it is a contract rather than a build plan

Only one ordering constraint is a contract, and it is the one §2 measured: **the test
harness moves first**, in its own commit, proved green before any window code is extracted.
Every other step is judged the same way — the GUI suite green, `./local-CI.sh` green — so
the order they are taken in is a build plan, and `docs/standards/documentation.md` §10 keeps
build plans out of specs.

## 5. Correctness invariants

- **INV-1** The GUI suite loads the window through the root `updater.py` with the repo root
  on `sys.path`, and a failure to import `oneup` fails the suite rather than skipping it.
  *Test:* `tests/gui-smoke.py` — the loader inserts the repo root before
  `spec_from_file_location`, and the existing `ImportError` handler continues to skip only
  on absent PySide6, never on an absent `oneup`.

- **INV-2** Every path constant is read through its module (`paths.RUN_STATE`), never bound
  by `from … import`. *Test:* a new grep gate in `local-CI.sh` fails on any
  `from …paths import <CONSTANT>` under `oneup/`; and `tests/gui-smoke.py` redirects
  `paths.RUN_STATE`, `paths.STOP_REQUEST` and `paths.ZYPP_PACKAGE_CACHE` and asserts the
  window acted on the redirected path, not merely that the redirected path changed.

- **INV-3** No module under `oneup/engine/` imports from `oneup.gui`. *Test:*
  `tests/imports-test.py` walks `oneup/engine/` and fails on any `oneup.gui` import.
  Vacuously true until that directory exists, which is why it is written now.

- **INV-4** `HERE` and every path derived from it are computed in `paths.py` alone; no other
  module builds a path from its own `__file__`. *Test:* `tests/imports-test.py` fails on
  `__file__` under `oneup/` outside `paths.py`; `tests/gui-smoke.py` asserts `paths.ENGINE`
  resolves to the repo root's `update_system.sh` and that `_headless_command`'s last-resort
  branch names the root entry point, not a package module.

- **INV-5** Every focusable widget still reports a non-empty accessible name or visible
  text. *Test:* the existing sweep in `tests/gui-smoke.py`, which walks
  `findChildren(QWidget)`, keeps those whose `focusPolicy()` is not `Qt.NoFocus`, and
  asserts a name is present. It is not modified by this work.

- **INV-6** Every `QDialog` subclass still centres on its parent through `center_on_parent`
  in its `showEvent`, and the hand-built `QMessageBox` call sites still centre through
  `Updater._center_child` deferred one tick. *Test:* the existing centring checks in
  `tests/gui-smoke.py`, plus a new check that every `QDialog` subclass under `oneup/gui/`
  overrides `showEvent`.

- **INV-7** `read_repos` still runs `zypper` with `LC_ALL=C`. *Test:* new in
  `tests/gui-smoke.py` — patch `repos.subprocess.run`, call `read_repos`, assert the `env`
  it was handed pins `LC_ALL` to `C`; and feed `_parse_repos` a localised table to show what
  the pin prevents. The GUI has no locale coverage today while the engine does, so dropping
  the pin during the move would stay green in CI and break only for non-English users.

- **INV-8** `_headless_update` invokes the engine with `--notify` and never forwards the
  GUI-only `--update` token. *Test:* the existing regression check in `tests/gui-smoke.py`,
  retargeted so the patch and the function are in the same module (§4.5).

- **INV-9** The window handles every marker it handles today, with the same fields and the
  same effect. *Test:* the existing marker feeds in `tests/gui-smoke.py`, unchanged — they
  are the reason a behaviour-preserving split is judgeable at all. **They do not cover the
  whole protocol:** measured at `03435ba` by comparing the `@@…@@` tokens in the suite
  against `docs/reference/marker-protocol.md` §3's table, two markers the reference lists are
  never fed — `@@SIZE@@` and `@@CHECK_ITEM@@`. (`@@NAME@@` in that document is the generic
  placeholder, not a marker.) The move of those two handlers is covered by review, not by a
  test, unless a feed for each is added while the marker code is being moved — which is the
  cheaper option and the recommended one.

- **INV-10** The six version sites still agree with `APP_VERSION` living in
  `oneup/__init__.py`. *Test:* `local-CI.sh`'s version-lockstep gate, updated to read the
  new location, and `tests/bump-test.py`. A half-done move fails loudly: the gate's
  extraction returns empty and the comparison cannot pass.

- **INV-11** A guard and the command it protects stay in the same module.
  *Test:* **nothing** — this is judgement, and `docs/standards/security.md` §9.4 states it
  as a trap for exactly that reason. It belongs in the review of each extraction commit.

## 6. Failure modes

- **A test patch lands on a name nobody reads.** The suite goes green and the window uses
  the real path. Worst case, the window deletes a live run's `run.state` — which is why
  `docs/standards/testing.md` §2 exists and why INV-2 checks the *effect* of the redirect,
  not the redirect.
- **`updater.subprocess.run` is patched while `_headless_update` lives elsewhere.** The
  patch misses, the real `subprocess.run` fires, and the smoke test starts a **real system
  update** on the developer's machine. The assertion fails afterwards, long after the damage.
  This is the sharpest instance of the failure above; INV-8 fixes the target.
- **A module computes its own `HERE`.** The engine is not found, `_find_engine` falls
  through to its `~/Documents/update_system.sh` fallback and returns a path that does not
  exist. The window opens and Run fails. INV-4.
- **The systemd unit names a package module.** `_headless_command` writes a command that
  runs nothing; the weekly timer fires and silently does no work, on a branch nobody watches
  because the assertions still pass. §4.4, INV-4.
- **The locale pin is dropped in the move.** `_parse_repos` decides enabled from the first
  letter of a column, so a German desktop's "Ja" reads as disabled and every repository
  appears off. Green in CI, broken for every non-English user. INV-7.
- **`window.py` and a subsystem import each other.** Python raises on the cycle at import,
  so this one fails loudly and early — the cheapest of the six. §4.3 rule 2.
- **A guard is separated from its command.** The assumption travels implicitly between two
  files and the next edit to either loses it. `docs/standards/security.md` §9.4; nothing
  catches it but review, which INV-11 says plainly.

## 7. Tests

| Locks in | Test | New? |
| --- | --- | --- |
| INV-1 | `tests/gui-smoke.py` — the loader | changed |
| INV-2 | `local-CI.sh` grep gate + `tests/gui-smoke.py` redirect checks | new gate, changed checks |
| INV-3, INV-4 | `tests/imports-test.py` | new |
| INV-5, INV-6, INV-9 | `tests/gui-smoke.py` — the existing sweeps and marker feeds | unchanged, and that is the point |
| INV-7 | `tests/gui-smoke.py` — the locale checks | new |
| INV-8 | `tests/gui-smoke.py` — the `--update` regression check | retargeted |
| INV-10 | `local-CI.sh` version lockstep, `tests/bump-test.py` | changed |
| INV-11 | nothing — review | — |

`tests/imports-test.py` follows `docs/standards/files-and-naming.md` §2.1's
`<subject>-<kind>` rule and is called by name from `tests/run-tests.sh`; nothing here
discovers tests.

Two things the suite must keep doing while the modules move, both from
`docs/standards/testing.md`: the `HOME` redirect stays module-level and runs **before**
`QApplication` is constructed (§2.2), and a passing run stays silent apart from the known
teardown noise (§7).

**`./local-CI.sh` is green at every commit**, not only at the end — the split's whole safety
argument is that each step is judged by assertions written before it.

## 8. Docs & release

- **`CHANGELOG.md`** — one `Changed` entry. A refactor with no user-visible effect still
  ships in a release users install.
- **`docs/standards/files-and-naming.md`** — §4's package block stops describing a directory
  that does not exist; its **What checks this** row for §4.1 currently reads *"nothing yet —
  the package does not exist (ONEUP-0034)"* and gains the gates INV-3 and INV-4 add.
- **`docs/standards/coding.md`** §4.1 says this spec *"is not written yet"*.
- **`docs/standards/workflow.md`** §5.1 and **`bump.py`** — the `APP_VERSION` site moves to
  `oneup/__init__.py`, along with `local-CI.sh`'s lockstep gate. Six sites, still six.
- **`CLAUDE.md`** §4 describes the app as two files; it becomes a package and an engine.
- **`docs/reference/marker-protocol.md`** names `updater.py` as the parser's home.
- **`local-CI.sh`** — the py_compile step compiles `updater.py` and `bump.py`; it must
  compile the package too.
- **Packaging, all three paths, in the same commit as the layout change**
  (`docs/design/oneup-2.0.md` §4): `packaging/rpm/oneup.spec` installs exactly two files
  today and needs a directory install; `packaging/appimage/build-appimage.sh` points
  PyInstaller at `updater.py` and needs its analysis to follow the new imports;
  `packaging/obs/_service` rolls a tarball whose layout the RPM spec expects. Verified with
  `./local-CI.sh --full`, which builds the AppImage.
- **No version bump of its own.** This ships as part of 2.0.0, which the design's §7 gate
  governs.

## 9. Alternatives considered (and rejected)

- **Mixin classes** — `class Updater(TrayMixin, AutostartMixin, …)`. The most mechanical
  possible split and the safest diff. Rejected because it moves lines without moving
  responsibility: a mixin still reaches any attribute of the whole object, so the class
  remains untestable except through the whole application, and a reader still needs all of
  it. It buys the file count and none of the point.
- **Grouping by kind — `dialogs.py`, `handlers.py`, `helpers.py`.** Rejected by
  `docs/standards/coding.md` §4.2 by name: a single feature ends up smeared across three
  files and every change touches all of them.
- **A shared `engine_args.py` for every argv builder.** Rejected: the three builders belong
  with their callers, because `docs/standards/security.md` §9.4 asks that a guard and the
  command it protects stay together. Collecting them by shape is the refactor that rule
  warns about.
- **Making `updater.py` a package (`updater/`)** rather than a root shim over `oneup/`.
  Rejected by `docs/design/oneup-2.0.md` §4: the desktop entry, the RPM wrapper, the
  AppImage and every user's launcher name `updater.py` as a file.
- **Splitting opportunistically over several releases**, as the roadmap bullet originally
  proposed. Rejected by the design's §5.2: the split has to land alone, so the existing GUI
  assertions judge it with nothing else in flight. Spread across releases it would always be
  in flight with something.

## 10. Out of scope

- **Any change a user could notice.** Layout, wording, colour, behaviour on any marker.
- **The interface redesign (ONEUP-0064)**, which comes after and is where `window.py`'s own
  size is addressed, if it is.
- **Themes (ONEUP-0027), translation (ONEUP-0032), the engine rewrite (ONEUP-0054).**
  `theme.py` and `markers.py` are where two of those will land; neither is started here.
- **Type-annotating what moves.** `docs/standards/coding.md` §3 requires annotations on
  anything crossing a module boundary — that applies to the public surface of each new
  module, not to a sweep of every function that happens to move.
- **Unit tests for the extracted helpers.** `docs/standards/testing.md` §8 makes them
  possible and worthwhile; they are not what proves this change, and adding them here would
  mean new assertions landing in the one commit whose argument is that the old ones suffice.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
