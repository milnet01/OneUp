# Coding Standard

**In one sentence:** this file says which Python you may assume, how big a file is allowed
to get, how to run another program safely, and what to do when something fails — so that
2.0 code looks like it was written by one person who was paying attention.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `58ea3bc` — every version and count below was measured on 2026-07-26,
not recalled. Where a lookup was needed the source is named.

**Sections:** 1 the Python floor · 2 lint configuration · 3 type hints · 4 module size ·
5 subprocess discipline · 6 Qt idioms · 7 error handling · 8 comments · 9 reuse ·
10 traps · 11 before you commit · what checks this · 12 cold-eyes log

---

## 1. The Python floor: **3.13**

**You may write code that requires Python 3.13.** You may not require 3.14 — not because
3.14 is unsupported (§1.2 shows it is inside PySide6's ceiling), but because the *floor*
is what every supported target actually ships, and both ship 3.13.

### 1.1 How that was established

The floor is not a preference. It is the oldest `/usr/bin/python3` on a distribution
OneUp still supports, because **that is the interpreter that actually runs the app** when
it is installed from the RPM:

```
packaging/rpm/oneup.spec, the %{_bindir}/oneup wrapper:
    exec python3 %{_datadir}/oneup/updater.py "$@"
data/za.co.antsprojectshub.OneUp.desktop:
    Exec=oneup
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

`README.md`'s requirements section says "openSUSE Tumbleweed or Leap". With 15.6 retired, **Leap means Leap
16.0**, and both supported targets ship the same interpreter.

### 1.2 The ceiling: below 3.15

PySide6 — the only third-party thing the GUI needs — declares `requires_python:
<3.15,>=3.10` (measured against PyPI for 6.11.1; see `docs/standards/dependencies.md`).
So **3.14 is permitted by the ceiling and 3.15 is not**, until PySide6 raises it. Ceiling
and floor are different questions: CI and the AppImage may *run* 3.14, while code may not
*require* it (§1). This is what ONEUP-0004's pending CI bump turns on — 3.13 → 3.14 is
inside the ceiling; a later jump to 3.15 is not, and must wait for PySide6.

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

The codebase already does this — `_latest_run_log` is annotated `-> Path | None`. Do not add
`from typing import Optional, List`; they are not needed and their presence in a new
module is a review comment.

### 1.4 When to re-check

Re-read this section when Leap 16.0 reaches end-of-life, or when its release notes
announce that `/usr/bin/python3` has moved. Both events can only raise the floor, never
lower it. Verify with `python3 -V` on the target, not from memory.

---

## 2. Lint and formatting

### 2.1 The decision: a `pyproject.toml` is added in 2.0

**Adopted on `v2` as ONEUP-0063, 2026-08-19.** The decision below is unchanged and is
still what the file must contain; what has moved on is the *state it was settled against*,
which is still `main`'s. On `v2` the file exists and the gate calls a bare `ruff check`.
§2.1.1's measurement was re-taken before the adoption, and what it found is recorded
there.

**Before it, there was no lint configuration file at all.** `ruff` was invoked with flags,
from one place only:

```
local-CI.sh's Lint gate, before ONEUP-0063:
    ruff check . --select F,B --exclude screenshots -q
```

That is a real problem and the reason this section exists. A developer who runs the
obvious command — `ruff check .` — gets **ruff's default rule set**, which is not `F,B`.
So the same tool, on the same code, gives one answer to a bare invocation and a different
one to the gate. Nobody is warned; the local run simply passes or fails for different
reasons.

**Note what "the gate" means here.** Lint runs in `local-CI.sh` **only**. GitHub CI
(`.github/workflows/release.yml`) runs the three test suites and the AppImage build — it
has never run `ruff` or `shellcheck`. So the divergence is `ruff check .` versus
`./local-CI.sh`, not versus CI; a lint failure is caught before a push or not at all (`docs/standards/workflow.md` §6 owns that split and what it costs).

**The settled decision:** 2.0 adds a `pyproject.toml` at the repo root carrying the rule
set, so that a bare `ruff check` and the gate agree. `local-CI.sh` then drops its
`--select` flags and calls plain `ruff check`. Writing that file is 2.0 work, not this
document's — but the content is settled here so the implementer has nothing to invent:

```toml
[tool.ruff]
target-version = "py313"          # matches the floor in §1
line-length = 100
exclude = ["screenshots"]

[tool.ruff.lint]
select = ["F", "B", "S", "E", "W", "I", "UP", "RUF", "BLE"]
# F  pyflakes — real bugs (undefined name, unused import)
# B  bugbear — mutable default args, loop-variable capture
# S  bandit — subprocess/shell safety; see §5 and the existing noqa comments
# E,W pycodestyle; I import sorting; UP pyupgrade — keeps idioms at the floor
# RUF ruff's own, incl. RUF100 which flags a noqa that no longer suppresses anything
# BLE blind-except — enabled because tests/gui-smoke.py already carries 8
#     `# noqa: BLE001` comments; without BLE, RUF100 flags every one of them
```

**Why `line-length = 100` and not ruff's default 88:** measured at `58ea3bc`. At 100,
**14** lines in the tree are too long — 5 in `updater.py`, 8 in `tests/gui-smoke.py`, 1 in
`tests/bump-test.py` (`bump.py` has none); the longest is 115 characters, in
`tests/gui-smoke.py`. At 88, **135 lines in `updater.py` alone** would be flagged. 100
records what the code already does and leaves 14 lines to wrap; 88 would be a reformatting
project disguised as a lint setting. Reformatting code you are not otherwise changing is
not this project's habit: every changed line should trace to the change you set out to
make.

**Why `S` is in the set even though the gate does not run it today:** `updater.py` already
carries **six** `# noqa: S603` / `S607` comments — three in `run_kwin_script`, and one each
on the `subprocess.run` in `read_repos` and the two `subprocess.Popen` calls in `Updater`.
They suppress rules **that are not currently enabled**, so today they do nothing at all —
they read as safety review, but no tool is checking. Enabling `S` makes them mean what they
appear to mean. **Do not delete them** on the grounds that they are inert; they are inert
because the config is missing, which is the thing being fixed.

### 2.1.1 What adopting it actually costs — measured, not estimated

**The config above does not go green on today's tree.** Run against `58ea3bc` with ruff
0.15.11 it reported **47 errors** — a measurement of that commit, not a standing claim
(`docs/standards/documentation.md` §6b.4). Re-run it before acting on the breakdown:

| Rule | Count | What it is |
| --- | --- | --- |
| `E501` | 14 | the long lines above |
| `S607` | 11 | partial executable path (`"systemctl"`, not `/usr/bin/systemctl`) |
| `S603` | 6 | `subprocess` call without `shell=False` proof |
| `E702` | 4 | two statements on one line, separated by `;` |
| `RUF100` | 3 | `noqa` comments that suppress nothing (below) |
| `RUF005`, `RUF003`, `RUF007` | 6 | literal concatenation, ambiguous unicode in a comment, `zip` instead of `pairwise` |
| `S103`, `S108`, `BLE001` | 3 | a permissive file mode, a hard-coded `/tmp` path, and one unsuppressed blind `except` — all in tests |

**Leaving `BLE` out of the set makes it worse, not better: 54 rather than 47.** Drop `BLE`
and the one real `BLE001` error goes away (47 → 46), but every one of `tests/gui-smoke.py`'s
eight `# noqa: BLE001` comments becomes a `RUF100` "unused noqa" (46 + 8 = 54) — a rule set
that punishes the code for suppressing a rule the rule set declined to enable. Both figures
were measured, not derived; that is why `BLE` is in the list above.

**Three of the six `# noqa` comments do not work where they sit** — a trap worth naming,
because it is invisible until `S` is on. Ruff anchors `S607` to the line carrying the
executable literal, which is the line *after* the `subprocess.run(` / `subprocess.Popen(`
that the comment is attached to. So the directive suppresses nothing (`RUF100: unused
noqa`) **and** the underlying `S607` fires unsuppressed — two errors where the author
intended none. The three in `run_kwin_script` are fine; the ones in `read_repos` and the
two `Updater` `Popen` calls are not. **Re-anchor them to the reported line as part of
enabling `S`.**

Adopting the config is therefore a small, bounded piece of work — wrap 14 lines, re-anchor
3 comments, resolve or explicitly ignore the rest — and **not** a one-line config drop.
Filed as **ONEUP-0063**. An implementer who adds the file without doing the rest turns the
gate red on the next commit.

### 2.2 Shell code

`shellcheck` runs in `local-CI.sh`'s Lint gate with `-e SC2001` on `update_system.sh`,
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

Current coverage, measured on `main`: **51 of 174** function definitions in `updater.py`
carry a return annotation (~29%). New modules start at 100% on their public surface; existing
functions get annotated when you are already editing them, not in a sweep of their own.

**On `v2` this rule is now live, and one thing it does not yet cover is recorded rather than
quietly skipped.** The split moved each subsystem's functions into their own module, so their
parameters and returns cross a real boundary — the annotations they already carried came with
them. The window they are handed is the exception: annotating it means naming the window's
class in every subsystem, which is the import direction ONEUP-0034 §4.3 rule 2 keeps one-way.
It is left unannotated on purpose, and ONEUP-0122 records the question.

---

## 4. Module and function size

### 4.1 The ceiling

**Soft ceiling: 600 lines per module.** Crossing it is not forbidden, but it is a prompt
to ask what second responsibility has moved in.

The reason is not taste, and it is the reason ONEUP-0034 exists: **`updater.py` is more than
six times the ceiling, and a single class inside it — `Updater(QMainWindow)`, running to the
module-level `_app_icon` — is nearly four times it on its own.**

A class that size cannot be held in a reader's head, cannot be reviewed as a unit, and cannot
be tested except through the whole application. Splitting it is ONEUP-0034, specced in
`docs/specs/ONEUP-0034-gui-modules.md` and **done on `v2` on 2026-08-20**; the figures above
describe `main`, which still ships the single file. This standard's job is to stop the next
file getting there — and the split's own outcome is the honest test of the ceiling: every
module it produced fits except the window itself, which the spec said up front it would
not.

*(The exact line counts are deliberately not quoted — `docs/standards/documentation.md` §6b.
They change with every commit, and the multiple is what carries the argument. The measured
figures, dated, are in `docs/design/oneup-2.0.md` §2.)*

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
   is used (`docs/standards/security.md` §4).
3. **The GUI never calls `sudo` and never becomes root** — measured: zero `sudo`
   invocations in `updater.py`. Update work shells out to the engine, which is the only
   part that touches root during a run. It *may* ask `pkexec` to run a named program as
   root for a short user-initiated action outside a run, and **every argument is validated
   first, at every such site**. Corrected 2026-07-26: an earlier revision of this line said
   the GUI "never runs a privileged command", which is not accurate and is the more
   dangerous belief to code under. The full rule is `docs/standards/security.md` §1.
4. **No privileged call ever sits inside a subshell.** In the engine, a call whose
   *output* is needed goes through `sudo_capture`; every other one is a direct `sudo` at
   top level, which is safe precisely because sudo stays the caller's own child. This is
   the most expensive trap in the project and §8.1 explains why. In Python the rule
   becomes: one runner object owns every privileged child process.
   (`docs/standards/security.md` §1.2 owns the counts and how they were taken.)
5. **Long-running child processes use `QProcess`, not `subprocess`**, in the GUI. Qt's
   event loop reads its output without blocking the window; `subprocess.run` freezes it.
   `subprocess` is for short, immediate calls that answer a question (`systemctl
   --user is-enabled`). There are **13** such call sites in `updater.py` today — among
   them `read_repos`, `run_kwin_script`, `Updater._timer_enabled`,
   `Updater._install_user_timer`, `Updater._remove_user_timer`, and the two
   `subprocess.Popen` sites in `Updater`.

### 5.2 Annotating a suppression

If a `subprocess` call needs a `# noqa: S603`, the comment says **why it is safe**, not
just which rule to silence. The existing ones are the pattern to copy:

```python
subprocess.run(  # noqa: S603,S607 — fixed argv, no shell.
```

A bare `# noqa: S603` with no reason is a review comment. Two of the six are exactly that
today — the second and third calls in `run_kwin_script` — and they are the counterexample,
not the pattern. Give each a reason when §2.1's config lands.

---

## 6. Qt idioms (the GUI half)

The floor here is Qt 6 / PySide6 6.x, and the codebase is already clean — these rules
lock in what is true rather than asking for a migration.

- **New-style `connect` only.** Measured: **51** `.connect(...)` calls, **zero**
  `SIGNAL()` / `SLOT()` macros. Never reintroduce the string-based form; it fails at
  runtime instead of at import, which is the worst possible time to find a typo.
- **Parent every widget that owns a window** — dialogs, `QMenu`, `QMessageBox`. An
  unparented menu can be garbage-collected while it is on screen; the ONEUP-0018 review
  found exactly that. The one menu in the tree is parented today (`QMenu(self)` in
  `Updater._ensure_tray`), and new ones must be.
- **Parent every `QProcess`.** Every one in the tree is (`QProcess(self)`). An unparented
  one is collected by Python while C++ still holds it, which surfaces as
  `RuntimeError: Internal C++ object (QProcess) already deleted`.
- **Parenting is not the whole answer, and the tree proves it.** That same `RuntimeError`
  is printed dozens of times by a *passing* `tests/gui-smoke.py` run, from the `finished` lambda
  in `Updater._query_auth_status` — where the `QProcess` **is** parented.
  (`docs/standards/testing.md` §7 owns the measurement and says how to take it; the count
  varies run to run, so it is not quoted here.) Parenting is
  what kills it: the test drops the window, Qt deletes the child C++ object, and the
  pending connection then fires into a Python wrapper whose C++ side is gone. Parent *and*
  make sure nothing outlives the parent — disconnect in the handler, or hold the reference
  through a `QPointer` and check it. Filed as **ONEUP-0062**.
- **Use `QPointer` for a non-owning reference to an object you did not parent, or one that
  may be destroyed before your callback runs.** There is none in the tree today, which is
  precisely why the bug above survives. It becomes null on deletion instead of dangling,
  so the handler can test it.
- **Scoped enums** (`Qt.AlignmentFlag.AlignLeft`) where the codebase already uses them;
  match the surrounding file.

---

## 7. Error handling

**No workaround without a root-cause fix** — silencing a warning, `try/except: pass`,
`--no-verify`, commenting out the broken part. Last resort, never the default, and when it
genuinely is the only option, a comment names the constraint so it reads as deliberate.

- **No bare `except:`.** There are none (measured). Catch what you can name:
  `except (OSError, subprocess.SubprocessError)` — the form already used in
  `run_kwin_script` and `read_repos`.
- **No `except Exception: pass`.** There is exactly **one** `except Exception` in
  `updater.py`. One is a defensible number; keep it there.
- **A failure is reported, never silenced**, and **never claim success you did not earn.**
  These are not style preferences — they are the four correctness invariants the engine
  suite exists to protect, and `docs/standards/testing.md` §5 states them in full and owns
  them. Read them before changing any engine path that decides what to tell the user.
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

**10.1 — CI's Python version is not the floor.** `.github/workflows/release.yml` pins
`python-version: '3.13'`, and ONEUP-0004 will raise it to 3.14. **That bump does not
raise the floor.** CI's interpreter builds the AppImage, which bundles its own Python; the
RPM path runs the *distro's* `/usr/bin/python3` (the spec's `oneup` wrapper). So a 3.14-only idiom
would pass CI, ship a working AppImage, and break for every user who installed via
`zypper`. The floor moves only when §1's table moves.

**10.2 — The AppImage and the RPM run different interpreters.** Following from 10.1:
"it works in the AppImage" is not evidence that it works when installed from the RPM or
OBS. Two distribution paths, two Pythons. Test the one you are claiming about.

**10.3 — `ruff check .` and the gate disagree today.** Covered in §2.1. Until
`pyproject.toml` exists, run the gate's command verbatim —
`ruff check . --select F,B --exclude screenshots` — or better, run `./local-CI.sh`, which
is where lint actually runs. **GitHub CI never lints**, so a `ruff` failure that gets past
`local-CI.sh` gets past everything.

**10.4 — The six `noqa: S` comments suppress nothing.** They name rules the current
invocation does not enable. Do not read them as evidence that a security rule set is
running, and do not delete them; §2.1 turns them on — and §2.1.1 explains why three of
them still will not work until they are re-anchored.

**10.5 — `python3-pyside6` looks like it does not exist, and does.** Checking with
`zypper info python3-pyside6` on Tumbleweed reports *"package not found"*, because the
real package is `python313-pyside6`. The RPM's `Requires: python3-pyside6`
nevertheless resolves correctly, because `python313-pyside6` carries
`Provides: python3-pyside6 = 6.11.1-1.2` (verified with `zypper info --provides`). **The
dependency is fine — do not "fix" it.** Search provides, not names:
`zypper search --provides --match-exact python3-pyside6`.

**10.6 — Don't reach for `sudo` in the GUI when a marker is what you want.** It is
tempting, when a value is awkward to get out of the engine, to just run the privileged
command from the GUI instead. That inverts the project's central safety property: the
value goes through a marker (see `docs/reference/marker-protocol.md`).

Corrected 2026-07-26: this trap previously read "the GUI must never grow a privileged
call", which is both wrong and misleading — the GUI already calls `pkexec` at three sites
(`RepoManagerDialog._build_apply_command`, `Updater.restart_services`,
`Updater.rollback`), two of which build a root shell string. Coding to the
absolute version means not writing the boundary validation those sites depend on, which is
the opposite of safe. `docs/standards/security.md` §1.4–1.6 and §4 carry the accurate rule
and the guards it requires.

---

## 11. Before you commit

- [ ] Nothing requires newer than Python **3.13** (§1).
- [ ] Public functions on new code are annotated (§3).
- [ ] No module crossed 600 lines without a reason you can state (§4).
- [ ] No `shell=True`, no `os.system`, fixed argv, and any `noqa` says *why* (§5).
- [ ] New Qt objects that own a window, and every `QProcess`, are parented (§6).
- [ ] No bare `except:`, nothing silenced, no unearned success claim (§7).
- [ ] Comments explain why, and any trap touched is named at the call site (§8).
- [ ] `./local-CI.sh` is green (§2.1 — it is the only place lint runs at all).

---

## What checks this

| Rule | What catches a breach |
| --- | --- |
| the code parses | `python3 -m py_compile updater.py bump.py` in `local-CI.sh` |
| §1 the 3.13 floor and the below-3.15 ceiling | **nothing** — no `python_requires` is declared anywhere in the tree. ONEUP-0063's `pyproject.toml` is what will declare it |
| §2.1 the select list | **nothing** — `local-CI.sh` runs `ruff check . --select F,B`, the bug classes only, because there is no config for `ruff` to read. ONEUP-0063 closes this |
| §2.2 shell code | `shellcheck -e SC2001` in `local-CI.sh`, over the six shell scripts it names |
| §3 type hints | nothing automatic |
| §4 module and function size | nothing automatic, deliberately. It is a soft ceiling, and a hard one is met by splitting badly |
| §5 subprocess discipline | half-covered. `tests/run-tests.sh` proves an unsafe repo alias never reaches a privileged command; `ruff`'s `S` rules would cover the rest, but only after ONEUP-0063 |
| §6 Qt idioms | nothing automatic |
| §7 error handling | `ruff`'s `BLE` rule, again only after ONEUP-0063 |
| §8 comments | nothing automatic |
| §9 reuse before rewriting | nothing automatic |

**Almost nothing in this standard is gated today, and one roadmap item fixes most of it.**
ONEUP-0063's `pyproject.toml` turns §2.1, §5 and §7 from prose into `ruff` rules that run on
every push. Until it lands, this standard is enforced by review alone — which is worth
stating plainly here rather than leaving a reader to discover it from a green `local-CI.sh`
that checked two rule families out of eight.

## 12. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: §2.1 said the divergence was with GitHub CI, which does not lint at all; the prescribed ruff config was measured and reports far more than the 14 wrappable lines then claimed (§2.1.1 carries the figures, and owns them); three `# noqa` comments were found anchored one line above their diagnostic; and the `QProcess` teardown error was attributed to *un*parented objects when every one in the tree is parented |
| 2 | 2026-07-26 | 1 high, 6 medium, 1 info — **2 verified, 5 dismissed, 1 info left** | converged. Nothing from loop 1 resurfaced in this lane, which is the proof those fixes held. The two findings that verified are logged against `files-and-naming.md` and `workflow.md` |
| 3 | 2026-07-26 | 1 medium — **1 verified** | §7 restated two of the four correctness invariants that `testing.md` §5 owns. Replaced with a pointer. |
| 4 | 2026-07-26 | none | clean. |
| 5 | 2026-07-26 | 1 medium — **1 verified** | the loop-1 row above carried 54 as the prescribed ruff config's error count. 54 is the figure *without* `BLE`; §2.1.1 owns both, and the row now defers to it. |
| 6 | 2026-07-26 | 1 low — **1 verified** | converged (polish only). §6 quoted the teardown-traceback count as '~30'. It varies run to run, so `testing.md` §7 owns it and this file no longer states a number (§6b). |
