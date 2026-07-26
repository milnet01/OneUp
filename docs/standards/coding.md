# Coding Standard

**In one sentence:** this file says which Python you may assume, how big a file is allowed
to get, how to run another program safely, and what to do when something fails — so that
2.0 code looks like it was written by one person who was paying attention.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `7fce9d6` — every version, line number and count below was measured on
2026-07-26, not recalled. Where a lookup was needed the source is named.

---

## 1. The Python floor: **3.13**

**You may write code that requires Python 3.13.** You may not require 3.14.

### 1.1 How that was established

The floor is not a preference. It is the oldest `/usr/bin/python3` on a distribution
OneUp still supports, because **that is the interpreter that actually runs the app** when
it is installed from the RPM:

```
packaging/rpm/oneup.spec:55   exec python3 %{_datadir}/oneup/updater.py "$@"
data/za.co.antsprojectshub.OneUp.desktop:6   Exec=oneup
```

The desktop entry launches a wrapper; the wrapper calls plain `python3`. So the floor is
whatever the distro calls `python3` — never a versioned interpreter we could pick.

| Target | Its `/usr/bin/python3` | Status | Source |
|---|---|---|---|
| openSUSE Tumbleweed | **3.13** | supported | measured on this machine, snapshot `20260723` |
| openSUSE Leap **16.0** | **3.13** | supported | Leap 16.0 release notes: *"`/usr/bin/python3` is currently set to use Python 3.13"* |
| openSUSE Leap **15.6** | — | **end-of-life 2026-04-30** | openSUSE lifecycle; EOL passed ~3 months before this was written |

Leap 15.6 going end-of-life is what makes 3.13 honest. While 15.6 was supported the floor
would have been much lower, and half this document would have been about avoiding modern
syntax. It is not supported, so we do not carry that weight.

`README.md:166` says "openSUSE Tumbleweed or Leap". With 15.6 retired, **Leap means Leap
16.0**, and both supported targets ship the same interpreter.

### 1.2 The ceiling: below 3.15

PySide6 — the only third-party thing the GUI needs — declares `requires_python:
<3.15,>=3.10` (measured against PyPI for 6.11.1; see `docs/standards/dependencies.md`).
So **3.14 is fine and 3.15 is not**, until PySide6 raises its own ceiling. This matters
for ONEUP-0004's pending CI bump: 3.13 → 3.14 is inside the ceiling; a later jump to 3.15
is not, and must wait for PySide6.

### 1.3 What the floor lets you write

Assume all of it, without a compatibility shim or a `sys.version_info` check:

```python
match marker:                      # structural pattern matching (3.10+)
    case "STEP_BEGIN": ...
    case "DONE": ...

def latest(log: Path) -> Path | None:      # X | Y unions (3.10+), not Optional[Path]
    ...

steps: list[str] = []                      # builtin generics (3.9+), not List[str]
```

The codebase already does this — `updater.py:161` is `-> Path | None`. Do not add
`from typing import Optional, List`; they are not needed and their presence in a new
module is a review comment.

### 1.4 When to re-check

Re-read this section when Leap 16.0 reaches end-of-life, or when its release notes
announce that `/usr/bin/python3` has moved. Both events can only raise the floor, never
lower it. Verify with `python3 -V` on the target, not from memory.

---

## 2. Lint and formatting

### 2.1 The decision: a `pyproject.toml` is added in 2.0

**Today there is no lint configuration file at all.** `ruff` is invoked with flags, from
one place only:

```
local-CI.sh:78   ruff check . --select F,B --exclude screenshots -q
```

That is a real problem and the reason this section exists. A developer who runs the
obvious command — `ruff check .` — gets **ruff's default rule set**, which is not `F,B`.
So the same tool, on the same code, gives one answer locally and a different one in CI.
Nobody is warned; the local run simply passes or fails for different reasons.

**The settled decision:** 2.0 adds a `pyproject.toml` at the repo root carrying the rule
set, so that a bare `ruff check` and CI agree. `local-CI.sh` then drops its `--select`
flags and calls plain `ruff check`. Writing that file is 2.0 work, not this document's —
but the content is settled here so the implementer has nothing to invent:

```toml
[tool.ruff]
target-version = "py313"          # matches the floor in §1
line-length = 100
exclude = ["screenshots"]

[tool.ruff.lint]
select = ["F", "B", "S", "E", "W", "I", "UP", "RUF"]
# F  pyflakes — real bugs (undefined name, unused import)
# B  bugbear — mutable default args, loop-variable capture
# S  bandit — subprocess/shell safety; see §5 and the existing noqa comments
# E,W pycodestyle; I import sorting; UP pyupgrade — keeps idioms at the floor
# RUF ruff's own, incl. RUF100 which flags a noqa that no longer suppresses anything
```

**Why `line-length = 100` and not ruff's default 88:** measured. At 100, exactly **13
lines** in the tree are too long (5 in `updater.py`, 8 across `bump.py` and
`tests/gui-smoke.py`); the longest line in the codebase is 106 characters. At 88, **135
lines** in `updater.py` alone would be flagged. 100 records what the code already does
and leaves 13 lines to wrap; 88 would be a reformatting project disguised as a lint
setting, and global rule 11 forbids drive-by reformatting.

**Why `S` is in the set even though CI does not run it today:** there are already **six**
`# noqa: S603` / `S607` comments in `updater.py` (lines 580, 583, 585, 985, 1925 and
3333). They suppress rules **that are not currently enabled**,
so today they do nothing at all — they read as safety review but no tool is checking.
Enabling `S` makes them mean what they appear to mean. **Do not delete them** on the
grounds that they are inert; they are inert because the config is missing, which is the
thing being fixed.

### 2.2 Shell code

`shellcheck` runs in `local-CI.sh:73` with `-e SC2001` on `update_system.sh`,
`tests/run-tests.sh` and the other shell scripts. Keep new shell clean under the same
flags. If the Python engine rewrite (ONEUP-0054) lands, shell shrinks but does not vanish
— `local-CI.sh`, `release.sh`, `bump.py`'s callers and `githooks/pre-push` stay.

---

## 3. Type hints

- **Required** on every public function and method: parameters and return type.
- **Optional** on local helpers and inside function bodies. Do not annotate every local
  variable; annotate where the type is not obvious from the line.
- **Required** on anything crossing a module boundary once the package split (ONEUP-0034)
  exists — that is the whole point of the split, and an unannotated public function makes
  the boundary guesswork.

Current coverage, measured: **51 of 174** function definitions in `updater.py` carry a
return annotation (~29%). New modules start at 100% on their public surface; existing
functions get annotated when you are already editing them, not in a sweep of their own.

---

## 4. Module and function size

### 4.1 The ceiling

**Soft ceiling: 600 lines per module.** Crossing it is not forbidden, but it is a prompt
to ask what second responsibility has moved in.

The reason is not taste. It is measured, and it is the reason ONEUP-0034 exists:

| Thing | Lines | Note |
|---|---|---|
| `updater.py` | **3,719** | one file |
| the `Updater` class inside it | **2,340** | lines 1292–3632 — one class |

A 2,340-line class cannot be held in a reader's head, cannot be reviewed as a unit, and
cannot be tested except through the whole application. Every argument for splitting it is
already written in `docs/specs/ONEUP-0034-gui-modules.md`; this standard's job is to stop
the next file getting there.

### 4.2 Split by responsibility, not by layer

When a module outgrows the ceiling, split it by **what it is responsible for**, not by
what kind of code it contains.

- **Good:** `rollback.py` (the snapshot picker and the engine call behind it),
  `repos.py` (reading and rendering repository state).
- **Bad:** `dialogs.py`, `handlers.py`, `helpers.py` — these group by technical category,
  so a single feature ends up smeared across three files and every change touches all of
  them.

Things that change together live together.

---

## 5. Subprocess discipline

OneUp's entire job is running other programs, so this section is load-bearing.

### 5.1 Rules

1. **Never `shell=True`. Never `os.system`.** Pass an argument list. There is no
   `shell=True` in the tree today (measured) — keep it that way.
2. **Fixed argv only.** No string interpolation of user or engine data into a command.
   Where a value must be passed, it is a separate list element, and it is validated first
   — the snapshot id reaching `snapper rollback` is checked to be a bare number before it
   is used (see `CLAUDE.md` and `docs/standards/security.md`).
3. **The GUI never runs a privileged command.** It shells out to the engine, which is the
   only part that touches root. This is the architecture, not a guideline.
4. **In the engine, every privileged call goes through one runner** — `sudo_capture` —
   and never sits inside a subshell. This is the most expensive trap in the project and
   §8.1 explains why.
5. **Long-running child processes use `QProcess`, not `subprocess`**, in the GUI. Qt's
   event loop reads its output without blocking the window; `subprocess.run` freezes it.
   `subprocess` is for short, immediate calls that answer a question (`systemctl
   --user is-enabled`) — currently at `updater.py:985`, `2257`, `2283`, `2293`, `2300`.

### 5.2 Annotating a suppression

If a `subprocess` call needs a `# noqa: S603`, the comment says **why it is safe**, not
just which rule to silence. The existing ones are the pattern to copy:

```python
subprocess.run(  # noqa: S603,S607 — fixed argv, no shell.
```

A bare `# noqa: S603` with no reason is a review comment.

---

## 6. Qt idioms (the GUI half)

The floor here is Qt 6 / PySide6 6.x, and the codebase is already clean — these rules
lock in what is true rather than asking for a migration.

- **New-style `connect` only.** Measured: **51** `.connect(...)` calls, **zero**
  `SIGNAL()` / `SLOT()` macros. Never reintroduce the string-based form; it fails at
  runtime instead of at import, which is the worst possible time to find a typo.
- **Parent every widget that owns a window** — dialogs, `QMenu`, `QMessageBox`. An
  unparented menu can be garbage-collected while it is on screen; the ONEUP-0018 review
  found exactly that. The one menu in the tree is parented today (`updater.py:2222`,
  `QMenu(self)`), and new ones must be.
- **Parent every `QProcess`.** Every one in the tree is (`QProcess(self)` — seven call
  sites). An unparented one is collected by Python while C++ still holds it, which
  surfaces as `RuntimeError: Internal C++ object (QProcess) already deleted`. That error
  is currently visible in `tests/gui-smoke.py` teardown, so this is not a hypothetical
  failure mode in this codebase — it is the one we already have.
- **Use `QPointer<T>` for a non-owning reference to a widget you did not parent.** There
  is no `QPointer` in the tree today; parenting has covered every case so far. If you find
  yourself storing a bare reference to a widget you do not own, that is what `QPointer` is
  for — it becomes null on deletion instead of dangling.
- **Scoped enums** (`Qt.AlignmentFlag.AlignLeft`) where the codebase already uses them;
  match the surrounding file.

---

## 7. Error handling

Global rule 1 — no workaround without a root-cause fix — applies with no exceptions.

- **No bare `except:`.** There are none (measured). Catch what you can name:
  `except (OSError, subprocess.SubprocessError)` — the form already used at
  `updater.py:588` and `990`.
- **No `except Exception: pass`.** There is exactly **one** `except Exception` in
  `updater.py`. One is a defensible number; keep it there.
- **A failure is reported, never silenced.** In the engine, a failed step is recorded,
  emits a plain-English `@@HINT@@`, and **the run continues to the next step** — so cache
  cleanup still happens and the summary is still useful. This is a tested invariant, not a
  style preference; `tests/run-tests.sh` locks it in.
- **Never claim success you did not earn.** Reboot advice fires only when something was
  actually installed, or when `zypper needs-rebooting` says so — never merely because a
  step errored. This is the single most important correctness rule in the project.
- **When a workaround is genuinely unavoidable**, leave a comment naming the constraint
  that forced it, so it reads as deliberate rather than as neglect.

---

## 8. Comments

Explain **why**, not what. The code already says what.

```python
# Bad — restates the line.
HERE = Path(__file__).resolve().parent   # get the directory of this file

# Good — records the constraint that shaped it.
# PyInstaller unpacks everything flat into _MEIPASS, so the nested package
# directories do not exist inside the AppImage; resolve from there instead.
```

**The six-month test:** if someone opens this file in six months, can they read the change
and understand why the code looks this way, without you? If not, the comment is missing —
or the code is too clever.

### 8.1 Comment the traps, always

Some of this project's rules look arbitrary until you know what they cost. Where the code
embodies one, say so at the call site. The three worth naming:

- **`sudo` inside a subshell re-authenticates.** With no terminal, sudo keys its cached
  credential to the **parent process id**, and bash forks a real subshell for `$(cmd |
  other)`. A measured run once needed **seven** password prompts. Hence `sudo_capture`.
- **Stopping is cooperative.** The engine checks for a stop request only at safe
  boundaries. Never signal it mid-transaction: SIGTERM during `zypper dup` leaves rpm
  half-applied or orphans a zypper that carries on regardless (ONEUP-0039/0042).
- **`tee -a -p` keeps a run alive when the GUI quits.** Without `-p`, quitting kills
  `tee`, then SIGPIPEs the engine, so its cleanup never runs and zypper is orphaned
  mid-transaction.

---

## 9. Reuse before rewriting

In order of preference:

1. **Call the existing code.**
2. **Refactor it to cover the new case, then call it** — existing call sites benefit too.
3. **Only if neither fits, write new code**, and justify the duplication in a comment or
   the commit message.

**Rule of Three:** extract a helper at the *third* call site, not the first or second.
Premature deduplication costs more than the duplication it prevents.

**Shortest correct implementation wins.** Fifty lines beat two hundred and fifty. No
scaffolding for hypothetical futures, no abstraction where a direct call works, no error
path for a situation that cannot arise at the call site.

---

## 10. Traps

Written down because each one has either bitten this project or is positioned to.

**10.1 — CI's Python version is not the floor.** `.github/workflows/release.yml:20` pins
`python-version: '3.13'`, and ONEUP-0004 will raise it to 3.14. **That bump does not
raise the floor.** CI's interpreter builds the AppImage, which bundles its own Python; the
RPM path runs the *distro's* `/usr/bin/python3` (`oneup.spec:55`). So a 3.14-only idiom
would pass CI, ship a working AppImage, and break for every user who installed via
`zypper`. The floor moves only when §1's table moves.

**10.2 — The AppImage and the RPM run different interpreters.** Following from 10.1:
"it works in the AppImage" is not evidence that it works when installed from the RPM or
OBS. Two distribution paths, two Pythons. Test the one you are claiming about.

**10.3 — `ruff check .` and CI disagree today.** Covered in §2.1. Until `pyproject.toml`
exists, run the CI command verbatim — `ruff check . --select F,B --exclude screenshots` —
or better, run `./local-CI.sh`, which is the only thing that agrees with CI by
construction.

**10.4 — The six `noqa: S` comments suppress nothing.** They name rules the current
invocation does not enable. Do not read them as evidence that a security rule set is
running, and do not delete them; §2.1 turns them on.

**10.5 — `python3-pyside6` looks like it does not exist, and does.** Checking with
`zypper info python3-pyside6` on Tumbleweed reports *"package not found"*, because the
real package is `python313-pyside6`. The RPM's `Requires: python3-pyside6`
(`oneup.spec:18`) nevertheless resolves correctly, because `python313-pyside6` carries
`Provides: python3-pyside6 = 6.11.1-1.2` (verified with `zypper info --provides`). **The
dependency is fine — do not "fix" it.** Search provides, not names:
`zypper search --provides --match-exact python3-pyside6`.

**10.6 — The GUI must never grow a privileged call.** It is tempting, when a value is
awkward to get out of the engine, to just run `sudo` from the GUI. That inverts the
project's central safety property. The value goes through a marker instead; see
`docs/reference/marker-protocol.md`.

---

## 11. Before you commit

- [ ] Nothing requires newer than Python **3.13** (§1); nothing needs 3.15+.
- [ ] Public functions on new code are annotated (§3).
- [ ] No module crossed 600 lines without a reason you can state (§4).
- [ ] No `shell=True`, no `os.system`, fixed argv, and any `noqa` says *why* (§5).
- [ ] New Qt objects that own a window, and every `QProcess`, are parented (§6).
- [ ] No bare `except:`, nothing silenced, no unearned success claim (§7).
- [ ] Comments explain why, and any trap touched is named at the call site (§8).
- [ ] `./local-CI.sh` is green (§2.1 — it is the only lint run that matches CI).
