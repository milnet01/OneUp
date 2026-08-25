# Files & Naming Standard

**In one sentence:** this file says where a new file goes, what it is called, and what
else you are obliged to change once you have added it — so nobody has to guess, and
nothing is half-installed.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `58ea3bc` — every path, name and figure below was read out of the tree,
not recalled.

**Sections:** 1 the repository · 2 naming · 3 the app ID · 4 the `oneup/` package ·
5 runtime state · 6 what a new file obliges you to update · 7 traps · 8 quick check ·
what checks this · 9 cold-eyes log

---

## 1. The repository, directory by directory

This is the tree as it is today, not as it might be. Anything not listed here does not
exist yet, and saying so is the point.

| Path | What belongs there |
| --- | --- |
| *(repo root)* | The two programs (`updater.py`, `update_system.sh`), the three developer scripts (`bump.py`, `local-CI.sh`, `release.sh`), and the four documents every reader starts from (`README.md`, `CLAUDE.md`, `ROADMAP.md`, `CHANGELOG.md`) plus `LICENSE`. |
| `data/` | Everything the desktop installs and the user never edits: the launcher entry, the icon, the app-store metadata. |
| `docs/design/` | Programme-level decisions that several items share. |
| `docs/specs/` | One item's contract. |
| `docs/plans/` | One item's build steps. |
| `docs/standards/` | Standing rules, like this one. |
| `docs/reference/` | Frozen contracts (formats, protocols). One file: `marker-protocol.md`. |
| `packaging/rpm/` | `oneup.spec` — the `zypper`-installable package. |
| `packaging/appimage/` | `build-appimage.sh` — the single-file portable build. |
| `packaging/obs/` | `_service` + `README.md` — the openSUSE Build Service recipe. |
| `tests/` | The whole suite: `run-tests.sh` (engine), `gui-smoke.py` (window), `imports-test.py` (the `oneup/` package's structural rules), `bump-test.py` (version lockstep), `parsers-test.py` (the engine's pure parsers), `docs-check.py` (the documentation rules a script can settle). |
| `githooks/` | Repo-local git hooks. One file: `pre-push`. Not active until `git config core.hooksPath githooks`. |
| `screenshots/` | Images the README and the app-store metadata point at. |
| `.github/workflows/` | GitHub CI. One file: `release.yml`, triggered by a `v*` tag. |
| `.ants/`, `.obs/` | Tooling configuration, not application code. |
| *(root dotfiles)* | `.gitignore`, `.ants_review_falsepos.jsonl` — tooling state that has to sit at the root to be found. |

**The root is closed.** Adding a third program or a fourth developer script to the root
needs a reason written in the commit message. Everything else has a directory.

**There is no `src/`, no `lib/`, and no `bin/`** — do not create one out of habit. 2.0
introduces exactly one new source directory, `oneup/` (§4).

**2.0 also adds exactly one new root file: `pyproject.toml`** (ONEUP-0063, on `v2` since
2026-08-19 — `docs/standards/coding.md` §2.1 settles its contents). It is lint
configuration only, with no `[project]` table, and OneUp stays not-pip-installable. It is
at the root for the same reason §1's table already grants the root dotfiles: `ruff` finds
it by walking up from the working directory, so anywhere else and it is not found.

---

## 2. Naming

### 2.1 The rules

| Kind of file | Rule | Examples in the tree |
| --- | --- | --- |
| Python module | `snake_case.py` | `updater.py`, `bump.py` |
| Shell script | `kebab-case.sh` | `build-appimage.sh`, `run-tests.sh`, `release.sh` |
| Test file | `<subject>-<kind>` | `gui-smoke.py`, `bump-test.py`, `docs-check.py` |
| Spec / plan | `ONEUP-NNNN-<kebab-topic>.md` | `ONEUP-0028-accessibility.md` |
| Standard | `<subject>.md`, no ID | `documentation.md`, `dependencies.md` |
| Anything under `data/` | `za.co.antsprojectshub.OneUp.<ext>` | all three files |

### 2.2 The exceptions, which are described and not renamed

Two shell scripts break the kebab-case rule, and both stay as they are:

- **`update_system.sh`** — snake_case, because the user's own launcher, the RPM's
  `%files` list and the AppImage's `--add-data` line all name it. Renaming it breaks
  installed copies for no benefit.
- **`local-CI.sh`** — carries an uppercase `CI`, because that is what it is. Also named
  in `CLAUDE.md`, `githooks/pre-push` and the plan documents.

**`run-tests.sh` is verb-first, not `<subject>-<kind>`** — it is the suite's entry point
rather than one subject's test file, and it reads as a command because it is one. A new
*test file* follows §2.1; a new *runner* may follow this.

**`githooks/pre-push` has no extension and cannot get one** — git will only run a hook
whose filename is exactly the hook's name.

**Test files do not follow `test_*.py`.** There is no pytest here, and nothing discovers
anything: `tests/run-tests.sh` runs the engine scenarios and calls no Python file at all.
`local-CI.sh` names every Python suite by hand, and `.github/workflows/release.yml` names
again the ones a tag must run. Do not add a pytest-style name expecting discovery to pick it
up — a suite in neither script runs nowhere, and one in `local-CI.sh` alone never runs in
CI.

### 2.3 Roadmap IDs

Specs and plans are named after the roadmap item they serve, zero-padded to four digits:
`ONEUP-0034`, not `ONEUP-34`. The next ID comes from `.roadmap-counter` via `roadmap_log`;
`ROADMAP.md` itself is generated from the roadmap store, and a hand edit does not survive
(`workflow.md` §4). The counter is **deliberately git-ignored** — see `.gitignore` for why,
and for the one-liner that rebuilds it on a fresh clone.

---

## 3. The app ID

`za.co.antsprojectshub.OneUp`, and **every file under `data/` carries it verbatim**:

```
data/za.co.antsprojectshub.OneUp.desktop
data/za.co.antsprojectshub.OneUp.metainfo.xml
data/za.co.antsprojectshub.OneUp.svg
```

The RPM spec (`packaging/rpm/oneup.spec`) installs all three through an `%{app_id}`
macro, and the AppImage build copies them by the same name — so a file under `data/` that
does *not* start with the app ID is installed nowhere and shipped to nobody.

The package name (`oneup`), the binary name (`oneup`), and the install directory
(`/usr/share/oneup/`) are lowercase and unqualified. Only `data/` uses the reverse-DNS
form; that is the desktop convention, not ours.

---

## 4. The `oneup/` package — 2.0's one new directory

From `docs/design/oneup-2.0.md` §4. **The engine spec (ONEUP-0054) and the GUI-split spec
(ONEUP-0034) must
follow it exactly**, because they split the two halves independently and would otherwise
disagree.

```
oneup/
  __init__.py
  engine/          the Python replacement for update_system.sh
  gui/             the split-up updater.py
  translations/    oneup_<lang>.ts catalogues (ONEUP-0032)
updater.py         thin entry point — stays at the root
update_system.sh   stays through 2.0 as a documented fallback, goes in 2.1
```

`translations/` holds data rather than code, and sits inside the package so a plain
checkout, the RPM and the AppImage all resolve it by the same relative path. `.ts` files
are tracked; the compiled `.qm` files are build artefacts and are git-ignored — see
`docs/standards/wording-and-translation.md` §7.

### 4.1 Rules the split must obey

1. **`updater.py` stays at the repo root, and stays the thing you launch.** The desktop
   entry, the RPM's `/usr/bin/oneup` wrapper and every user's hand-made launcher all name
   it. It becomes a few lines that import from `oneup/` and call it.
2. **No engine module imports from `oneup/gui/`.** The engine must stay runnable in a
   terminal with no Qt installed. Design gate **G5** covers half of this: it proves the
   engine imports no Qt and runs with PySide6 absent. It does **not** catch an engine
   module importing a Qt-free helper out of `oneup/gui/`, which would pass G5 and still
   invert the dependency. The stronger check — no `oneup.gui` import anywhere under
   `oneup/engine/` — belongs to ONEUP-0034's spec, which owns the test.
3. **Module names are `snake_case.py`** and say what they *do*, not what they *are*:
   `refresh.py`, not `refresh_manager.py`; `markers.py`, not `protocol_utils.py`.
4. **One responsibility per module.** If you cannot say what a module is for in one
   sentence without "and", split it.
5. **The package directory is `oneup/`, lowercase, singular** — matching the installed
   `/usr/share/oneup/` and the `oneup` command.

### 4.2 The trap that will bite the split — path resolution

`updater.py` finds the engine and the icon relative to **its own file**:

```python
# updater.py, the HERE constant
if getattr(sys, "frozen", False):
    HERE = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    HERE = Path(__file__).resolve().parent
```

`HERE` is the repo root today because `updater.py` sits in the repo root. **A module
moved to `oneup/gui/` that computes the same expression gets `oneup/gui/`** — and
`_find_engine()` then looks for `update_system.sh` in the wrong directory,
falls through its `~/Documents/update_system.sh` fallback, and returns a path that does
not exist. The window opens and the Run button fails.

**The rule:** `HERE` is computed in **exactly one place** in the package, and every other
module imports it. No module may build a path from its own `__file__`.

The same applies inside the AppImage, where PyInstaller unpacks bundled data flat into
`_MEIPASS` — a nested package directory does not exist there at all.

---

## 5. Runtime state, and which paths tests can actually redirect

Two directories hold everything OneUp writes at runtime:

- **`~/.local/state/oneup/`** — `history.json`, `logs/`, `run.state`, `stop.request`
- **`~/Documents/update-logs/`** — the engine's own copy of each run's log, kept in a
  place a user can find without being told where `.local/state` is

`run.state` and `stop.request` are a **contract between the two halves** — each file is
defined independently in both programs, with a comment in each saying it must match the
other — `updater.py`'s `RUN_STATE` / `STOP_REQUEST` constants and `update_system.sh`'s
`RUN_STATE_FILE` / `STOP_FILE`. Moving either means editing both. ONEUP-0044's
`HOLD_STATE` / `GO_REQUEST` and `HOLD_STATE_FILE` / `GO_FILE` are the same arrangement
and carry the same obligation.

### 5.1 The override table — measured, and not what you would assume

Every environment override that exists, and every path that has none:

| Path or setting | Default | Used by | Override |
| --- | --- | --- | --- |
| Run record | `~/.local/state/oneup/run.state` | both | `ONEUP_RUN_STATE` — **engine only** |
| Stop request | `~/.local/state/oneup/stop.request` | both | `ONEUP_STOP_FILE` — **engine only** |
| Hold stamp | `~/.local/state/oneup/hold.state` | both | `ONEUP_HOLD_STATE` — **engine only** |
| Go-ahead request | `~/.local/state/oneup/go.request` | both | `ONEUP_GO_FILE` — **engine only** |
| Hold ceiling | `120` seconds | engine | `ONEUP_HOLD_SECONDS` |
| Keep-alive refresh interval | `50` seconds | engine | `ONEUP_KEEPALIVE_SECONDS` |
| zypper lock probe | `/run/zypp.pid` | engine | `ONEUP_ZYPP_PID_FILE` |
| Passwordless-auth drop-in | `/etc/sudoers.d/oneup` | engine | `ONEUP_AUTH_FILE` |
| Download guard | `/usr/libexec/oneup-download-guard`, or `/usr/lib/oneup-download-guard` where `/usr/libexec` does not exist (Leap 15.x) | engine | `ONEUP_GUARD_FILE` |
| Graphical password helper | `/usr/libexec/ssh/ksshaskpass` | engine | `ONEUP_ASKPASS` |
| Per-repository refresh budget | `120` seconds | engine | `ONEUP_REFRESH_TIMEOUT` |
| Repository definitions | `/etc/zypp/repos.d` | engine | `ONEUP_REPOS_DIR` — **engine only** |
| Engine's user-visible log dir | `~/Documents/update-logs` | engine | **none** |
| GUI's log dir | `~/.local/state/oneup/logs` | GUI | **none** |
| Run history | `~/.local/state/oneup/history.json` | GUI | **none** |

**So the rule "everything has an override" is false, and writing it down as though it
were true would have misled the 2.0 implementer.** What is actually true:

- **The engine is isolated by environment variable.** `run_engine` in
  `tests/run-tests.sh` sets the first three, plus `ONEUP_REPOS_DIR`, unless the scenario
  sets them itself; scenarios that need `ONEUP_AUTH_FILE` set it themselves.
  `ONEUP_REPOS_DIR` is seeded by `setup_common` rather than left empty, because download
  recovery declines when no `download.opensuse.org` baseurl is present — an empty
  directory would make every recovery scenario exercise the skip path while appearing to
  test recovery.
- **`ONEUP_TEST_NETWORK` is not in the table above, because it is not an engine
  override.** It is read by `tests/run-tests.sh` alone, and opts in to the network-dependent
  checks (ONEUP-0094 T-1). `local-CI.sh` defaults it to 1, the release workflow leaves it
  unset, and `githooks/pre-push` passes 0 — explicitly, because the hook runs `local-CI.sh`
  and inherited its default until 2026-08-07, which meant a push could be failed by
  somebody else's outage (ONEUP-0097). **An inherited default is not a decision**; the hook
  states its own.
- **The GUI is isolated by rewriting `HOME`.** `tests/gui-smoke.py`'s sandbox block sets
  `HOME` to a throwaway directory *before* the window is imported, because the GUI's paths
  are module-level constants (`STATE_DIR`, `STATE_LOG_DIR`, `RUN_STATE`, `STOP_REQUEST`)
  evaluated at import time. Individual tests then reassign them on the module that owns
  them (`paths.STOP_REQUEST = …`), which is why every reader goes through `paths.` and
  never binds one by name — a bound copy would leave the redirect landing where nobody
  reads, and `tests/imports-test.py` fails the build on one.

### 5.2 What that obliges 2.0 to do

- **A new state path gets a `ONEUP_*` override at the moment it is added**, in both
  halves, not later. The two GUI paths without one are the reason this section exists.
- **The `HOME`-rewriting trick must keep working**, which means state paths stay as
  module-level constants computed once at import — or move to a single accessor that
  reads the environment each call. Half-and-half is what breaks: a constant captured in
  one module while another reads the environment gives two different answers in the same
  process.
- **Prefer `XDG_STATE_HOME` when it is set. Done in ONEUP-0059 on 2026-08-20, in both
  halves at once.** Each takes it only when it is ABSOLUTE, as the specification requires,
  and falls back to `~/.local/state` when it is unset, empty or relative. Trap 3 below
  records what the app did before.

---

## 6. What a new file obliges you to update

Adding a file is rarely one change. Work down this list:

**Any new file that must reach the user's disk** — all three packaging paths, or it
ships in none of them:

1. `packaging/rpm/oneup.spec` — an `install -D…` line in `%install` **and** an entry in
   `%files`. The spec currently installs exactly two source files by name
   (`updater.py`, `update_system.sh`); a package needs a directory install instead.
2. `packaging/appimage/build-appimage.sh` — PyInstaller follows `import` statements by
   itself, but **data files need an explicit `--add-data`** — the script's two
   `--add-data` flags do this for `update_system.sh` and the icon.
3. `packaging/obs/_service` — rolls the tarball the RPM spec expects; a layout change
   means checking it still matches.

**Any new file that carries a version number** — four more places, and the tests:

- `bump.py` must learn to edit it — the six `edit(...)` calls in `main()`.
- `local-CI.sh`'s lockstep gate must read it — the `# --- version lockstep` step. Note
  that gate greps **`updater.py` by name** for `APP_VERSION`, so moving the constant into
  the package means editing the `v_py=` line in the same change.
- `tests/bump-test.py` must cover it.
- `docs/standards/workflow.md` §5.1's list of six sites becomes seven. It is the only
  place that list is written out, so nothing else needs editing with it.

**Any new document** — `docs/standards/documentation.md` says which directory, and
whether it needs a `review-contract` pass before it counts as written.

**Any new interactive widget** — an accessible name, or `tests/gui-smoke.py` fails the
build. See the UI standard.

---

## 7. Traps found in the tree while writing this

Measured, not suspected. Recorded here so 2.0 does not reproduce them.

**Trap 1 — `LOG_DIR` named two different directories. CLOSED on `v2` by ONEUP-0054
stage 2.** In `update_system.sh` it is `~/Documents/update-logs`; in the window it was
`~/.local/state/oneup/logs`. While the two halves were in separate languages they could
not collide; in one package they would. The window's is now `STATE_LOG_DIR` and the Python
engine's is `USER_LOG_DIR`, renamed in one commit so the collision could not simply move.
**`update_system.sh` keeps `LOG_DIR`** — it is Bash, no Python imports it, and it retires
with the file. On frozen `main` both halves are unchanged and the trap stands as written.

**Trap 2 — the engine's log directory is created on the real machine during tests.
CLOSED on `v2` by ONEUP-0054 stage 2, and live on `main`.** `update_system.sh`'s
logging preamble ran `mkdir -p "$LOG_DIR"` *before* checking whether `--log=` was
passed, and `run_engine` does not redirect `HOME`. So the suite created
`~/Documents/update-logs` on any machine it ran on, including one that had never
installed OneUp — and on frozen `main` it still does. It writes nothing there — `--log=`
is always supplied — but it is still the suite touching the box, which the testing
standard forbids. Filed as **ONEUP-0058**.
On `v2` both engines now create the directory only when about to default into it, and a
scenario asserts it; frozen `main` keeps the old shape.

**Trap 3 — `XDG_STATE_HOME` was set by the tests and ignored by the app. CLOSED by
ONEUP-0059 on 2026-08-20.** The sandbox block exported `XDG_CONFIG_HOME` and
`XDG_STATE_HOME` while the window built `STATE_DIR` from `Path.home()` and read neither, so
the isolation worked only because `HOME` was redirected too and the two exports read as
protection they did not provide. Both halves now honour an absolute `XDG_STATE_HOME`, so
the `XDG_STATE_HOME` export is load-bearing. **`XDG_CONFIG_HOME` still is not the app's
doing** — settings go through `QSettings("OneUp", "OneUp")`, which Qt resolves under it
already. **What has not changed is the reason `HOME` is still redirected**: it is what
covers the paths with no XDG equivalent, and §5.1's table still shows two GUI paths with no
override at all.

**Trap 4 — `_find_engine`'s fallback leaves each caller to notice.** It tries
`HERE/update_system.sh`, then `~/Documents/update_system.sh`, then returns the first path
regardless of whether it exists — so whether a packaging mistake is legible depends on the
caller. `Updater.start_run` checks and names the missing file; the tray check does not, and
there it surfaces as nothing happening. Any 2.0 equivalent must say which paths it tried, so
that no caller has to.

**Trap 5 — three of the four root scripts are not in any packaging list.** `bump.py`,
`local-CI.sh` and `release.sh` are developer tools and are correctly absent from the RPM
and the AppImage. Do not "fix" this by adding them; do check, when adding a root script,
which category it is in — the answer decides whether §6 applies at all.

---

## 8. Quick check before you commit a new file

- Is it in the right directory, per §1? (If no directory fits, the standard is wrong —
  change it here, not by inventing a folder.)
- Does its name follow §2, or is it a documented exception?
- If it is under `data/`, does it start with the app ID?
- If it writes at runtime, does it have a `ONEUP_*` override and a test that uses it?
- Does it need any of the three packaging paths (§6)?
- Does it carry a version number? If so, all of `bump.py`, `local-CI.sh`,
  `tests/bump-test.py` and `docs/standards/workflow.md` §5.1.

---

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §1 the root is closed | nothing automatic — the reason for a new root file goes in the commit message, where a reader finds it and a script does not |
| §2.1 the naming rules | nothing automatic |
| §4.1 the rules the `oneup/` split must obey | `tests/imports-test.py` covers **rule 2 only** — it fails the build on any `oneup.gui` import under `oneup/engine/`, vacuously true until that directory exists. Rules 1, 3 and 5 — the shim stays at the root, `snake_case.py` names that say what a module does, the directory called `oneup/` — are checked by **nothing**; they held through ONEUP-0034 by review |
| §4.2 `HERE` is computed in exactly one place | `tests/imports-test.py` fails the build on `__file__` anywhere under `oneup/` but `paths.py`, and on a `from …paths import <name>` that would bind a path constant by value. `tests/gui-smoke.py` adds the two the AST cannot see: that `paths.ENGINE` resolves to the repo root's `update_system.sh`, and that `_headless_command`'s last-resort branch names the root entry point rather than a package module |
| §5 runtime state paths, and which are redirectable | `tests/run-tests.sh` — `run_engine` redirects three of them on every scenario. The fourth, `HOME`, cannot be redirected today (ONEUP-0058) |
| §6 what a new file obliges you to update | nothing automatic. §8's checklist is the only catcher, and it works only if the author opens it |

**Nothing here is gated, and most of it could be.** Naming, the closed root and the packaging
manifests are all patterns a script can match. This is the standard most likely to be worth a
gate next, by `docs/standards/workflow.md` §6.1's rule — the second time a review catches a
misnamed or unregistered file.

## 9. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: `docs/reference/` was described as not existing when it does, four bare line-number citations survived the `documentation.md` §6a sweep, gate G5 was credited with a check it does not make, and the root was said to hold three programs when it holds two |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged (polish only). Verified here: "From design §4" never named the design document. The two line-number citations two lanes reported are in `CLAUDE.md`, not in this document — dismissed, and already covered by ONEUP-0065 and Task 11 |
| 3 | 2026-07-26 | none | clean. Collateral only: the `tests/` row and the test-file naming row gained `docs-check.py`. |
| 4 | 2026-07-26 | none | converged. |
