# Files & Naming Standard

**In one sentence:** this file says where a new file goes, what it is called, and what
else you are obliged to change once you have added it — so nobody has to guess, and
nothing is half-installed.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** v2
**Verified at:** `0fda0d4` — §1, §4, §5, §6, §7 and the *What checks this* table were
re-measured against this tree on 2026-10-01. Everything else was read out of the tree at
`58ea3bc`, not recalled.

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
| `oneup/` | The application: `engine/` (the Python engine) and `gui/` (the window). §4 owns its shape. |
| `data/` | Everything the desktop installs and the user never edits: the launcher entry, the icon, the app-store metadata. |
| `docs/design/` | Programme-level decisions that several items share. |
| `docs/history/` | History moved out of a document so the document stays a rule. One file: `claude-md.md`. |
| `docs/reviews/` | Review records kept outside the document they review. One file: `ONEUP-0072-fix-ledger.md`. |
| `docs/specs/` | One item's contract. |
| `docs/plans/` | One item's build steps. |
| `docs/standards/` | Standing rules, like this one. |
| `docs/reference/` | Frozen contracts (formats, protocols). One file: `marker-protocol.md`. |
| `packaging/rpm/` | `oneup.spec` — the `zypper`-installable package. |
| `packaging/appimage/` | `build-appimage.sh` — the single-file portable build — and `requirements.txt`, the exact packages it installs. |
| `packaging/obs/` | `_service` + `README.md` — the openSUSE Build Service recipe. |
| `tests/` | The whole suite: `run-tests.sh` (engine), `gui-smoke.py` (window), `imports-test.py` (the `oneup/` package's structural rules), `bump-test.py` (version lockstep), `parsers-test.py` (the engine's pure parsers), `differential-test.sh` (both engines against the same mocks — gate G2), `mock-env.sh` (the mock sandbox both engine suites source), `docs-check.py` (the documentation rules a script can settle). |
| `githooks/` | Repo-local git hooks. One file: `pre-push`. Not active until `git config core.hooksPath githooks`. |
| `screenshots/` | Images the README and the app-store metadata point at. |
| `branding/` | The OneUp wordmark, for pages outside this repository that show the project. Nothing in the app or its packages reads it. |
| `.github/` | `FUNDING.yml`, and `workflows/` — GitHub CI. One workflow: `release.yml`, triggered by a `v*` tag. |
| `.ants/`, `.obs/` | Tooling configuration, not application code. |
| *(root dotfiles)* | `.gitignore`, `.ants_review_falsepos.jsonl`, `.yamllint` — tooling state that has to sit at the root to be found. |

**The root is closed.** Adding a third program or a fourth developer script to the root
needs a reason written in the commit message. Everything else has a directory.

**There is no `src/`, no `lib/`, and no `bin/`** — do not create one out of habit. 2.0
introduces exactly one new source directory, `oneup/` (§4).

**2.0 adds two new root files, and both are lint configuration found by walking up from
the working directory** — the same reason §1's table already grants the root dotfiles.
Neither is a program or a developer script, so the closed root above still holds.

- **`pyproject.toml`** (ONEUP-0063, on `v2` since 2026-08-19 — `docs/standards/coding.md`
  §2.1 settles its contents). Lint configuration only, with no `[project]` table; OneUp
  stays not-pip-installable. `ruff` finds it by walking up, so anywhere else and it is not
  found.
- **`.yamllint`** (ONEUP-0136, 2026-08-31). Without it `yamllint` measures YAML against
  its own 80-column default, which no part of this project uses — §2.1 sets 100 and
  `pyproject.toml` sets ruff's `line-length` to match. Twelve of the fourteen line-length
  findings in the 2026-08-31 audit were lines already inside the project's own limit.
  `yamllint` auto-discovers it at the working directory only, so the root is the one place
  it works without a `-c` at every call site.

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
anything: `tests/run-tests.sh` runs the engine scenarios and no Python test file.
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

`translations/` holds data rather than code, and nothing loads it yet. Its runtime location
is `HERE/oneup/translations/` in every layout, and the loader ONEUP-0032 adds finds it
through `paths.py`, like the engine and the icon (§4.2). A checkout and the RPM get that
path from the package itself — the RPM's `cp -a oneup` puts it at
`/usr/share/oneup/oneup/translations/`. The AppImage gets it only from an `--add-data` whose
destination is `oneup/translations`, because PyInstaller follows imports and not data (§6).
`.ts` files are tracked; the compiled `.qm` files are build artefacts and are not — `.gitignore` has no rule for them
yet, so the change that first builds one adds it. See
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

### 4.2 The trap the split had to avoid — path resolution

The window finds the engine and the icon relative to `HERE`, the repo root. It is
computed in `paths.py` under `oneup/gui/`:

```python
# oneup/gui/paths.py, the HERE constant
if getattr(sys, "frozen", False):
    HERE = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    HERE = Path(__file__).resolve().parents[2]
```

Before the split this was `Path(__file__).resolve().parent` in `updater.py`, which gave
the repo root only because `updater.py` sits there. **A module under `oneup/gui/` that
computes that expression gets `oneup/gui/`** — and `_find_engine()` then looks for
`update_system.sh` in the wrong directory, falls through its
`~/Documents/update_system.sh` fallback, and returns a path that does not exist. The
window opens and the Run button fails.

**The rule:** `HERE` is computed in **exactly one place** in the package, `paths.py`, and
every other module reads it as `paths.HERE`, never binding it by name (§5.1). No other
module may build a path from its own `__file__`.

The same applies inside the AppImage, where PyInstaller unpacks bundled data flat into
`_MEIPASS` — a nested package directory does not exist there at all.

---

## 5. Runtime state, and which paths tests can actually redirect

Three directories hold everything OneUp writes at runtime:

- **`~/.local/state/oneup/`** — `history.json`, `logs/`, and the four state files in
  §5.1's table
- **`~/Documents/update-logs/`** — the engine's own copy of each run's log, kept in a
  place a user can find without being told where `.local/state` is
- **`~/.config/`** — the window's settings, through `QSettings("OneUp", "OneUp")`, and the
  autostart entry and systemd user timers the window can install. `QSettings` follows
  `XDG_CONFIG_HOME`; the autostart entry and the timers are built from `Path.home()`, so
  only rewriting `HOME` redirects them. None has an `ONEUP_*` override

`run.state` and `stop.request` are a **contract between the window and the engine** — each
file is defined independently in three places: the window's `RUN_STATE` / `STOP_REQUEST`
in `paths.py`, the Python engine's constants of the same names in `runstate.py`, and
`update_system.sh`'s `RUN_STATE_FILE` / `STOP_FILE`. Moving either means editing all
three. ONEUP-0044's `HOLD_STATE` / `GO_REQUEST` and `HOLD_STATE_FILE` / `GO_FILE` are the
same arrangement and carry the same obligation.

### 5.1 The override table — measured, and not what you would assume

Every environment override that exists, and every path in the first two directories above
that has none:

| Path or setting | Default | Used by | Override |
| --- | --- | --- | --- |
| Run record | `~/.local/state/oneup/run.state` | both | `ONEUP_RUN_STATE` — **engine only** |
| Stop request | `~/.local/state/oneup/stop.request` | both | `ONEUP_STOP_FILE` — **engine only** |
| Hold stamp | `~/.local/state/oneup/hold.state` | both | `ONEUP_HOLD_STATE` — **engine only** |
| Go-ahead request | `~/.local/state/oneup/go.request` | both | `ONEUP_GO_FILE` — **engine only** |
| The `~/.local/state` base of every `oneup/` path above | `~/.local/state` | both | `XDG_STATE_HOME` — taken only when ABSOLUTE; unset, empty or relative falls back (ONEUP-0059) |
| Hold ceiling | `120` seconds | engine | `ONEUP_HOLD_SECONDS` |
| Keep-alive refresh interval | `50` seconds | engine | `ONEUP_KEEPALIVE_SECONDS` |
| zypper lock probe | `/run/zypp.pid` | engine | `ONEUP_ZYPP_PID_FILE` |
| Passwordless-auth drop-in | `/etc/sudoers.d/oneup` | engine | `ONEUP_AUTH_FILE` |
| Download guard | `/usr/libexec/oneup-download-guard`, or `/usr/lib/oneup-download-guard` where `/usr/libexec` does not exist (Leap 15.x) | engine | `ONEUP_GUARD_FILE` |
| Graphical password helper | `/usr/libexec/ssh/ksshaskpass` | engine | `ONEUP_ASKPASS` |
| Per-repository refresh budget | `120` seconds | engine | `ONEUP_REFRESH_TIMEOUT` |
| Flatpak update-count query budget | `60` seconds | Python engine only | `ONEUP_FLATPAK_TIMEOUT` |
| Repository definitions | `/etc/zypp/repos.d` | engine | `ONEUP_REPOS_DIR` — **engine only** |
| Stop-request poll interval, download pass | `2` seconds | engine | `ONEUP_STOP_POLL_SECONDS` |
| Single-instance socket name | `OneUp-<uid>` | GUI | `ONEUP_INSTANCE_NAME` |
| Engine's user-visible log dir | `~/Documents/update-logs` | engine | **none** |
| GUI's log dir | `~/.local/state/oneup/logs` | GUI | `XDG_STATE_HOME` only, through the row above — no `ONEUP_*` |
| Run history | `~/.local/state/oneup/history.json` | GUI | `XDG_STATE_HOME` only, through the row above — no `ONEUP_*` |

**So the rule "everything has an override" is false, and writing it down as though it
were true would have misled the 2.0 implementer.** What is actually true:

- **The engine is isolated by environment variable.** `run_engine` in
  `tests/mock-env.sh` sets the four state-file overrides, `ONEUP_ZYPP_PID_FILE`,
  `ONEUP_GUARD_FILE` and `ONEUP_REPOS_DIR`, unless the scenario sets them itself;
  scenarios that need `ONEUP_AUTH_FILE` set it themselves.
  `ONEUP_REPOS_DIR` is seeded by `setup_common` rather than left empty, because download
  recovery declines when no `download.opensuse.org` baseurl is present — an empty
  directory would make every recovery scenario exercise the skip path while appearing to
  test recovery.
- **`ONEUP_ENGINE` is not in the table above either, and for the same reason.** It
  overrides no path or setting: it names *which engine* the window launches — `v2` for
  `python3 -m oneup.engine`, anything else (unset, `v1`, a typo) for the Bash engine.
  Read by the **window** alone, per call rather than at import, so a scenario can flip
  it (`ONEUP-0054` §4.7). It is **temporary**: stage 9 of that item flips the default and
  the variable goes with it. Not to be confused with the suite's `ONEUP_ENGINE_CMD`,
  which is a whole argv the test harness pins per side; one variable for both would let
  an export aimed at the suite reach the window.
- **`ONEUP_INHIBITED` is not in the table either: it is the engine's own re-exec guard,
  not a setting.** The engine exports it just before re-running itself under
  `systemd-inhibit`, so the second copy does not do it again. Set by hand, it skips the
  shutdown and sleep inhibitor for that run.
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

- **A new state path is redirectable at the moment it is added**, not later: an `ONEUP_*`
  override in each engine, and in the window a module-level constant in `paths.py` that
  the suite reassigns, as it does `RUN_STATE` (§5.1).
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
   `%files`. A file under `oneup/` needs neither: `%install` copies that directory whole
   (`cp -a oneup`) and `%files` owns `/usr/share/oneup/`. Any other new file does, and so
   does a file under `oneup/` that the build generates rather than git tracks — a `.qm`
   needs its compile step here and in the AppImage script.
2. `packaging/appimage/build-appimage.sh` — PyInstaller follows the window's `import`
   statements by itself, but **data files need an explicit `--add-data`** — the script's
   two `--add-data` flags do this for `update_system.sh` and the icon. `oneup/engine/` is
   not reached: the window launches it as a separate process and never imports it, so it
   is not in the AppImage until ONEUP-0054 stage 9 adds it (that spec's §4.7).
3. `packaging/obs/_service` — rolls the tarball the RPM spec expects; a layout change
   means checking it still matches.

**Any new file that carries a version number** — four more places, and the tests:

- `bump.py` must learn to edit it — the six `edit(...)` calls in `main()`.
- `local-CI.sh`'s lockstep gate must read it — the `# --- version lockstep` step. Note
  that gate greps **`oneup/__init__.py` by name** for `APP_VERSION`, so moving the
  constant means editing the `v_py=` line in the same change.
- `tests/bump-test.py` must cover it.
- `docs/standards/workflow.md` §5.1's list of six sites becomes seven. The count is
  repeated across the tree — `git grep -nE "six (version |lockstep )?sites"` finds every
  copy; update the live ones and leave changelogs and dated records as they are.

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
covers the paths with no XDG equivalent — the engine's `~/Documents/update-logs`, and the
autostart entry and timers built from `Path.home()` (§5).

**Trap 4 — `_find_engine`'s fallback leaves each caller to notice.** It tries
`HERE/update_system.sh`, then `~/Documents/update_system.sh`, then returns the first path
regardless of whether it exists — so whether a packaging mistake is legible depends on the
caller. `start_run` in the window's `run.py` checks and names the missing engine; the tray check does not, and
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
- If it writes at runtime, can the suite redirect it (§5.2), and does a test do so?
- Does it need any of the three packaging paths (§6)?
- Does it carry a version number? If so, all of `bump.py`, `local-CI.sh`,
  `tests/bump-test.py` and `docs/standards/workflow.md` §5.1.

---

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §1 the root is closed | nothing automatic — the reason for a new root file goes in the commit message, where a reader finds it and a script does not |
| §2.1 the naming rules | nothing automatic |
| §4.1 the rules the `oneup/` split must obey | `tests/imports-test.py` covers **rule 2 in full** — it fails the build on any `oneup.gui` import under `oneup/engine/`. It also fails when `oneup/` is absent, which covers part of rule 5. Rules 1 and 3 — the shim stays at the root, `snake_case.py` names that say what a module does — and rule 5's *lowercase, singular* are checked by **nothing**; they held through ONEUP-0034 by review |
| §4.2 `HERE` is computed in exactly one place | `tests/imports-test.py` fails the build on `__file__` anywhere under `oneup/` but `paths.py`, and on a `from …paths import <name>` that would bind a path constant by value. `tests/gui-smoke.py` adds the two the AST cannot see: that `paths.ENGINE` resolves to the repo root's `update_system.sh`, and that `_headless_command`'s last-resort branch names the root entry point rather than a package module |
| §5 runtime state paths, and which are redirectable | `run_engine` in `tests/mock-env.sh` redirects the engine's on every scenario of both engine suites; `tests/gui-smoke.py` redirects the window's by rewriting `HOME` before import. Nothing checks that a new state path is redirectable (§5.2) |
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
| 5 | 2026-10-01 | Packet build, then 2 lanes, cold, dispatched from outside the project; genre pinned standard; every lane held every question. Q1 13 · Q2 3 · Q3 1 — 17 verified, 1 dismissed, all 17 fixed: 12 found building the packet (`44efd32`), 5 by the lanes | **A pure audit (ONEUP-0107): no change armed it, so there is no armed-span share.** The four-question gate's first read of this document. **Building the packet by running each claim on v2 found twelve [Q1]s before any lane ran**, all text still describing `main`'s tree: §1 omitted `oneup/` while saying anything unlisted does not exist; §4.2 quoted the pre-split `HERE`; §5 named two definers of the state-file contract where v2 has three; §5.1 put `run_engine` in the wrong file; §6 said the RPM installs two source files by name where it copies `oneup/` whole, and that the lockstep gate greps `updater.py`. **Lanes, three [Q2]s that change what gets built**: §5.2 required an `ONEUP_*` override in both halves while every existing window state path has none (both lanes); §4.2 said modules import `HERE`, which `tests/imports-test.py` INV-2 fails; §4 said translations resolve by one relative path in the AppImage, which §4.2 says has no nested package. [Q1]: §5's "everything OneUp writes" omitted `~/.config`. [Q3]: a generated `.qm` under `oneup/` still needs a build step. **Dismissed:** the "six" `edit(...)` calls in `bump.py` (nine on both branches) — a stale figure; a conformer adds the same call. Four open questions resolved clean. Out of scope, carried to its own run: `wording-and-translation.md` §7 repeats the one-relative-path claim, says `.qm` is git-ignored, and installs to a path the RPM does not use |
| 6 | 2026-10-01 | 2 lanes, cold, briefed exactly as loop 5 plus one corrected packet fact (`ONEUP_ENGINE_CMD` is only named in a `paths.py` docstring; a loop-5 lane disputed it and was right); every lane held every question. Q1 2 · Q2 1 — 3 verified, 0 dismissed, all 3 fixed | **[Q1], both lanes, pre-existing since ONEUP-0059**: §5.1 gave the window's log dir and run history no override, and Trap 3 kept that as the reason `HOME` is redirected — both are built from `STATE_DIR`, so `XDG_STATE_HOME` moves them. What only `HOME` covers is the engine's `~/Documents/update-logs` and the autostart entry and timers, which `autostart.py` builds from `Path.home()`; loop 5's `~/.config` bullet had credited `XDG_CONFIG_HOME` with those too. **[Q2], on loop 5's own text**: §4 said the translations path "is resolved" in `paths.py` — no loader exists — and fixed nothing against `wording-and-translation.md` §7's install path, which the RPM's `cp -a oneup` does not produce. §4 now leaves the install path to §7 and says what the ONEUP-0032 loader must do. **[Q1]**: §6 said PyInstaller follows imports, read beside "a file under `oneup/` needs neither" — the window never imports `oneup/engine/`, so the AppImage carries no Python engine until ONEUP-0054 stage 9. Own-fix share: 1 of 3, plus half of the first. Two open questions resolved clean |
| 7 | 2026-10-01 | 2 lanes, cold, briefed exactly as loop 6, plus a window listing the tracked files under four directories §1 names; every lane held every question. Q1 2 · Q2 1 — 3 verified, 0 dismissed, all 3 fixed. **Cap reached (3 for a standard)** | **A calm cap: findings ran 17 → 3 → 3, and this loop's own-fix share was 1 of 3.** **[Q2], both lanes, on loop 6's text**: §4 left the translations install path to `wording-and-translation.md` §7 while §6 said a file under `oneup/` needs no RPM line — so the loader, the RPM and the AppImage `--add-data` would each pick a directory. §4 now pins `HERE/oneup/translations/` in every layout and the AppImage destination that produces it; §7's Install row still disagrees and is carried to that document's own run. **[Q1]**: §6 said `workflow.md` §5.1 is the only place the six-site list is written out — the count is in `local-CI.sh`, `bump.py` and `oneup/__init__.py`; §6 now gives the `git grep` that finds every copy. **[Q1]**: the What-checks-this row said rule 5 is checked by nothing — `tests/imports-test.py` fails when `oneup/` is absent. Out of scope, filed: `CLAUDE.md` §4 forbids backticking a v2-only path in a scanned document, which every v2 standard does and `tests/docs-check.py` passes |
