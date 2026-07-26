# Security Standard

**In one sentence:** this file says which half of OneUp is allowed to become root, how it
asks the user for permission, what it must check before passing a value to a root command,
and what may be written to a log — because OneUp's whole job is running privileged
commands, and every bug in this file is a root bug.

**Status:** Draft — cold-eyes loop 1 applied; see §11
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `58ea3bc` — every count and rule below was measured against the tree on
2026-07-26, not recalled. Where a claim was checked and turned out different from the
project's own prior description, the correction is stated in place.

**Sections:** 1 the privilege boundary · 2 one authentication per run · 3 attributable
prompts · 4 validate at the boundary · 5 the passwordless drop-in · 6 cooperative
stopping · 7 logs · 8 supply chain · 9 traps · 10 before you commit · 11 cold-eyes log

---

## 1. The privilege boundary

This is rule one. Everything else in this document exists to keep it true.

**1.1 — The GUI process never becomes root, and never calls `sudo`.** Measured: `updater.py`
contains **zero** `sudo` invocations. Root work is delegated, never assumed.

**1.2 — The engine is the only thing that runs privileged commands during an update.**
Measured at `58ea3bc`, `update_system.sh` makes **34** privileged invocations: **14**
through `sudo_capture` (§2.2) and **20** direct `sudo` calls at command position. (A
thirty-fifth and thirty-sixth `sudo` appear *inside* `sudo_capture` itself — they are the
helper, not call sites.) The direct calls are the streaming and fire-and-forget ones that
**must** stay at top level: `sudo … | tee` keeps sudo as the caller's own child, which is
exactly what §2.2 requires.

The GUI launches the engine with `QProcess` and reads its output; it never launches a
**privileged** `zypper`. It does make one direct, unprivileged call — `read_repos` runs
`zypper --non-interactive lr -u` to list repositories, which needs no root.

**1.3 — The engine never imports Qt.** It is Bash, so it imports nothing; measured, the
only occurrences of a Qt name in `update_system.sh` are two comments mentioning
`QProcess`. The property that matters, and the one gate **G5** tests, is that the engine
runs with **PySide6 absent**. This is gate **G5** in the 2.0 design, and it is what keeps the split
honest — the moment the privileged half can draw a window, "the GUI is not root" stops
being structural and becomes a promise.

**1.4 — But the GUI *may* ask polkit to run a specific program as root.** This is the part
the project's own documentation previously overstated, so state it exactly:

> The GUI never *becomes* root. It may ask **`pkexec`** to run a named program as root, at
> a small fixed set of sites, with every argument validated first (§4).

There are exactly **three** such sites, all user-initiated, all one-shot, none part of an
update run:

| Site | Command | Guard |
| --- | --- | --- |
| `RepoManagerDialog._build_apply_command` | `pkexec sh -c "zypper … modifyrepo/removerepo <aliases>"` | every alias must match `_ALIAS_RE`, else the whole command is `None` and nothing runs |
| `Updater.restart_services` | `pkexec systemctl restart <units>` — **argv form, no shell** | each unit matched against a unit-name pattern; anything starting `-` dropped |
| `Updater.rollback` | `pkexec sh -c "snapper rollback <id> && systemctl reboot"` | `id` must satisfy `str.isdigit()` |

One more privileged action does not go through `pkexec` at all and must not be forgotten
when this list is checked:

| Site | Command | Guard |
| --- | --- | --- |
| `Updater.restart_now` | `QProcess.startDetached("systemctl", ["reboot"])` — argv form | **no arguments, so nothing to validate**; logind's own polkit policy decides whether an active local session may reboot |

It is listed because the *shape* is the risk: a future `startDetached` that interpolates a
value would be a privileged call with no validation and no `pkexec` to make it obvious.

**1.5 — The rule that follows from 1.4.** Anything belonging to *an update run* goes
through the engine, always. `pkexec` is reserved for short administrative actions the user
explicitly asks for, outside a run. A new privileged call in the GUI is not automatically
forbidden — but it must be argued for against this rule, argv-form if it possibly can be,
and validated at the boundary. **When in doubt, it goes in the engine.**

**1.6 — Two of the three sites build a shell command string**, which is why §4 exists and
is not optional. `pkexec sh -c "…"` runs a *shell* as root: a value interpolated into it
without validation is a root shell injection, full stop.

---

## 2. One authentication per run

**2.1 — The engine authenticates once, up front.** `sudo_init` in `update_system.sh`
raises a single graphical prompt via `sudo -A -v`, then starts a keep-alive that refreshes
the credential every 50 seconds for the life of the run. **Zero** prompts, and no
keep-alive at all, when §5's passwordless drop-in is active — `sudo_init` probes for it
and returns early.

**2.2 — Privileged output is captured with `sudo_capture`, never a subshell.** This is the
most expensive trap in the project's history and the reason the helper exists:

With no terminal — and there is none, because the GUI runs the engine through `QProcess` —
sudo keys its cached credential to the **parent process id** (`sudoers(5)`, `timestamp_type`:
the `tty` default falls back to the ppid when no tty is present). Bash forks a *real*
subshell for `$(cmd | other)`, `$(a; b)`, `$(cmd "$(nested)")` and `< <(cmd | other)`. A
`sudo` inside one therefore has a different parent, is authenticated **separately**, and
raises another password dialog.

Measured, not theorised: a full run once asked **seven times** (ONEUP-0038).

```bash
# WRONG — a subshell, so a second prompt
out=$(sudo zypper --dry-run dup | awk '/download size/ {print $NF}')

# RIGHT — sudo stays in the caller's own shell; process the captured text after
sudo_capture -e out env LC_ALL=C zypper --non-interactive dup --dry-run
size=$(awk '/download size/ {print $NF}' <<<"$out")
```

A **top-level** `sudo … | tee` is fine — sudo remains the caller's own child. That is how
`run_system_upgrade` streams.

**2.3 — In the Python engine (ONEUP-0054), the same trap takes a different shape.** There
is no subshell in Python, so the rule translates to: **one runner object owns every
privileged child process.** Do not scatter `subprocess.run(["sudo", …])` calls across
modules; route them through a single helper that is the sudo parent for the whole run,
exactly as `sudo_capture` is today. The failure mode is identical and so is the symptom —
extra password dialogs — but the cause will read differently, so write the reason down at
the helper.

**2.4 — Nothing the engine spawns may outlive it.** `cleanup`'s trap cannot run when the
engine is `SIGKILL`ed, so the keep-alive **also watches the engine's pid and exits on its
own**. It runs under `setsid` in its own process group so `cleanup` can kill the whole
group (`kill -- -PGID`) — a plain `kill` on the subshell orphans the inner `sleep 50`,
which reparents to init. It carries the tag `oneup-keepalive` in `$0` so a test can find it.

Measured: before this, two keep-alives were found still calling `sudo -n -v` every 50
seconds, **40 minutes after** the runs that spawned them had been killed (ONEUP-0041). Any
new background helper inherits this rule.

---

## 3. Every prompt must say who is asking, and why

A root password prompt the user cannot attribute is indistinguishable from a phishing
dialog, and the correct response to one is to refuse it. So:

**3.1 — Attribution comes from the exported environment, and the *authenticating* call
carries it explicitly.** Exactly one `sudo` in the engine passes `-A` and `-p`:
`sudo_init`'s `sudo -A -v`, which is the call that actually prompts. The other 20 are
plain `sudo` **on purpose** — they inherit the exported `SUDO_ASKPASS` and `SUDO_PROMPT`
(3.2, 3.3), so if any of them ever has to ask, the prompt is graphical and labelled
anyway. That is why the export is mandatory rather than a convenience: it is what makes
"every prompt is attributable" true of a call site that never mentions it.
`ASKPASS` defaults to `/usr/libexec/ssh/ksshaskpass` and is overridable via
`ONEUP_ASKPASS` so tests point it at a mock (the `ASKPASS=` constant near the top of
`update_system.sh`).

**3.2 — `SUDO_ASKPASS` is exported, not merely set.** sudo consults
the askpass helper only when it finds the variable **in the environment**. Without the
export, a `sudo` that cannot see the cached credential has no way to ask and dies with *"a
terminal is required to read the password"* — which is precisely what made "Show download
size" fail (ONEUP-0036).

**3.3 — `SUDO_PROMPT` is exported too**, so that even prompts we
did not pass `-p` to are labelled. This distro defaults to `targetpw`, under which sudo's
own wording is *"[sudo] password for root"* — an unlabelled request for the **root**
password shown to someone who only clicked "check the download size" (ONEUP-0037).

**3.4 — The same rule binds development.** Any privileged command run against this machine
uses `SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A -p "…"` with a short,
action-describing label. Never bare `sudo`; never an unlabelled `-p`.

**3.5 — A prompt nobody is waiting on is litter.** An askpass dialog whose `sudo` has gone
sits on the user's screen indefinitely. Eleven had piled up on one reporter's machine, one
still open **5.7 hours** after its run had exited cleanly — a large part of why "three
prompts in a row" felt like more than three. Code that can leave a prompt orphaned must
clean it up.

---

## 4. Validate at the boundary, by shape

**The rule: any value that reaches a privileged command is validated by shape, at the
boundary, before it is used — regardless of where it came from.**

"Where it came from" is the point. These values are not typed by a user, so they *feel*
trustworthy. They are not:

- The GUI reads markers from the engine's **merged stdout+stderr**. Interleaved output can
  splice a marker line, so a payload is not guaranteed to be what the engine meant to send.
- `SNAPSHOT_ITEM` descriptions come from `snapper`, which is to say from whatever text
  anyone ever put in a snapshot description.
- Repository aliases come from files under `/etc/zypp/repos.d/`.

**4.1 — The three live guards**, all verified in place. Note each one is a `fullmatch`
or an exact test, never a `search` — a `re.match` would accept trailing junk:

```python
# updater.py, the module-level _ALIAS_RE — repo aliases. The first character
# class excludes '-', so an alias can never be read as an option by zypper; no
# space, quote, ';', '&', '$' or backtick is permitted, so it cannot break out
# of the sh -c string either.
_ALIAS_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9:@._+-]*")
# …used as: if not _ALIAS_RE.fullmatch(alias): return None

# Updater.rollback — the rollback target is interpolated into a root shell.
if not target.isdigit(): return          # isdigit() also rejects empty

# Updater.restart_services — service units, argv form. Leading '-' rejected separately so a
# spliced token cannot become a systemctl option.
svcs = [s for s in self._services.split()
        if not s.startswith("-") and re.fullmatch(r"[A-Za-z0-9:@._\\-]+\.[a-z]+", s)]
```

**4.2 — Fail closed.** `_build_apply_command` returns `None` — cancelling the *entire*
operation — if any single alias fails validation. It does not filter the bad one out and
proceed. When a value that should be well-formed is not, something is wrong that
validation cannot diagnose, so nothing runs.

**4.3 — Prefer argv form to a shell string.** `pkexec systemctl restart <units>` cannot be
injected into, whatever the units contain; `pkexec sh -c "…"` can. Where a shell string is
genuinely needed (chaining with `&&`), the validation is load-bearing and must be stated as
such in a comment at the site.

**4.4 — Validation is not sanitisation.** Reject; do not clean up and continue. There is no
"escape it and pass it on" path in this codebase and there should not be one.

**4.5 — One observation, recorded rather than filed.** The unit-name pattern in 4.1 is
`[A-Za-z0-9:@._\\-]`, which inside a character class permits a literal **backslash** —
almost certainly a typo for `\-`. It is **not exploitable**: that site is argv-form, so a
backslash reaches `systemctl` as an ordinary character and the unit simply does not exist.
Worth tidying when the file is next touched for another reason; not worth a change to
frozen `main`.

---

## 5. The passwordless drop-in

Opt-in, never silent, scoped, revocable. All four properties are load-bearing.

**5.1 — What it is.** `--grant-auth` writes a `sudoers` drop-in that lets *this user* run
OneUp's update commands as root without a password. It stores **no password anywhere** —
not in a keyring, not in a file, not in memory.

**5.2 — The exact scope**, built from resolved absolute paths at grant time
(`build_auth_rule` in `update_system.sh`):

| Entry | Why |
| --- | --- |
| `zypper` (any arguments) | the update itself |
| `snapper` (any arguments) | snapshot create/list — the rule adds the bare resolved path, so it also permits `snapper delete` |
| `flatpak` (any arguments) | flatpak update/uninstall — likewise unrestricted by subcommand |
| `systemctl stop packagekit` | releases the package lock |
| `env LC_ALL=C zypper *` | the engine pins the locale via `sudo env …`, and sudo matches the rest of the argv literally, so the wrapper form needs its own entry |

**5.3 — State the risk plainly, in the UI, before granting.** This is approximately
passwordless root for OneUp's commands: `zypper` can install arbitrary packages, and a
package can run arbitrary code as root. That is not a flaw in the scoping — it is what
"may update the system without a password" *means*. The mitigation is informed consent, so
the warning must not be softened.

Note the scope is tighter than it looks in one respect worth keeping: `env LC_ALL=C zypper *`
matches that literal prefix only. `env PATH=/tmp/evil zypper …` does **not** match, so the
rule cannot be used to hand `env` an arbitrary environment.

**5.4 — Validate before installing; a broken drop-in can lock the user out of `sudo`
entirely.** The rule is written to a temp file, checked with `visudo -cf` **in isolation**,
and only then placed with `install -o root -g root -m 0440` — atomic, root-owned, and the
mode sudo requires. If validation fails, nothing is changed.

**5.5 — Revocation is immediate and complete**: `--revoke-auth` deletes the file. There is
no "disabled but retained" state.

**5.6 — Report real state, never a saved preference.** `--auth-status` probes with
`sudo -k -n <zypper> --version`: `-k` ignores any cached credential so a recent run cannot
produce a false positive, and `-n` refuses to prompt, so the probe succeeds only when the
NOPASSWD rule is genuinely active. If the rule were removed outside OneUp, the toggle must
show off. A settings toggle that reports what it *stored* rather than what *is* is a
security bug.

---

## 6. Stopping is cooperative — and that is a safety decision

**6.1 — Never signal the engine to stop a transaction.** `SIGTERM` mid-`zypper dup` either
leaves rpm half-applied or orphans a zypper that carries on regardless. Both outcomes can
leave packages broken, and the abandoned lock blocks the next run. See ONEUP-0039/0042 for
what this cost in practice.

**6.2 — Stop requests are honoured at safe boundaries only**: between steps, and after the
repo refresh but *before* a transaction starts. The engine then skips the remaining steps
and still prints its summary, so the user sees what did happen, and reports
`@@DONE@@|stopped` — neither success nor failure.

**A stop request older than `run.state` is a leftover and is ignored.** Staleness is
judged by modification time rather than by deleting the file at startup, because deleting
would swallow a stop the user clicked a moment earlier.

**6.3 — A run must survive the GUI going away.** The logging `exec` uses `tee -a -p`
(`--output-error=warn-nopipe`). Without `-p`, quitting the GUI kills `tee`, which `SIGPIPE`s
the engine on its next line, so `cleanup` never runs and zypper is orphaned mid-transaction.
`-p` is **probed, not assumed**, with a `PIPE` trap as the fallback. Correspondingly the GUI
warns before quitting during a run and explains that it continues in the background.

**Never add a code path that kills the engine mid-run.** Closing to the tray is not a quit
and needs no warning.

---

## 7. Logs, and what may go in them

**7.1 — Where.** Runtime state lives in `~/.local/state/oneup/` (`history.json`, `logs/`);
each run is also mirrored to `~/Documents/update-logs/`. (The mirror location is under
review — ONEUP-0058, ONEUP-0059.)

**7.2 — The engine writes logs as the user, never as root.** `--log=<path>` accepts an
arbitrary path and the log is opened by the engine's own `exec`, so the file is created
with the user's privileges. This is only safe because the engine as a whole does not run as
root — it *calls* `sudo` for individual commands. **The engine must never be run as root in
its entirety**; if it were, `--log=/etc/passwd` would be a trivially destructive argument.

**7.3 — Log the command and its outcome; do not echo captured privileged output
unreviewed.** Output captured from a root command may contain paths, package sets, or
repository URLs with embedded credentials. Anything routed to the log is a deliberate
choice, not a reflex `echo "$captured"`.

**7.4 — Anything leaving the machine is scrubbed.** The "Copy diagnostics" bundle
(`build_diagnostics` in `updater.py`) replaces the home path with `~` and the hostname
with `<host>` **across the whole payload, log body included**, and trims an oversized log to
its last `DIAG_LOG_CAP` (200 KiB of text, tail-first, because errors sit at the end). A user pasting
that into a public issue tracker must not thereby publish their username and machine name.
Any future "share this" feature inherits the rule.

---

## 8. Supply chain

**8.1 — Version policy lives in `docs/standards/dependencies.md`**, including the
known-incompatibility ledger. This section covers only what is security-specific.

**8.2 — Build inputs must be pinned.** A build that resolves "latest" at build time is a
build whose output nobody chose. Measured 2026-07-26: the AppImage build installs
`pyinstaller` and `PySide6` **unpinned**, so a tagged release is not reproducible and an
upstream compromise would ship automatically. Filed as **ONEUP-0060**; it is a 2.0 fix.

**8.3 — The two distribution paths have different trust bases.** The RPM depends on the
distro's `python3-pyside6`, so it inherits openSUSE's signing and review. The AppImage
bundles its own Python and Qt, so OneUp *is* the trust base for everything inside it — which
is exactly why 8.2 matters more for the AppImage than for the RPM.

**8.4 — Repository signing keys are a user-facing security decision, not an error to
paper over.** A rotated or expired key surfaces as `REMEDY|import-keys`, which the GUI
offers as a **warned, confirmed** action ("Import signing key & retry"). It is never
automatic, and `--no-gpg-checks` is not an acceptable remedy anywhere in this project.

That last one is enforced, not merely intended: the two `check_absent "…never disables gpg
checks"` assertions in `tests/run-tests.sh`
assert the flag never reaches zypper, including down the repository auto-skip path — the
place where "just get past it" is most tempting. Keep both tests when the engine is
rewritten.

---

## 9. Traps

**9.1 — "The GUI never runs a privileged command" is not quite true, and believing it is
dangerous.** It never runs `sudo`, and it never becomes root — but it does call `pkexec` at
three sites, two of which build a root shell string (§1.4). Code written under the
comfortable version of the rule will skip the validation those sites depend on. This
document states the accurate version; `docs/standards/coding.md` §5.1 and §10.6 were
corrected to match on 2026-07-26.

**9.2 — A `sudo` that works interactively can prompt twice under the GUI.** The subshell
trap (§2.2) is invisible in a terminal, because with a tty sudo keys its credential to the
tty rather than the ppid. Testing a change by running the engine in a terminal therefore
proves nothing about the path users actually take. The regression test models sudo's
per-parent-pid cache and fails if a run needs more than one prompt — do not weaken it.

**9.3 — `sudoers` wildcards match spaces.** `env LC_ALL=C zypper *` grants everything after
that literal prefix. This is intended here (§5.3) but is a general hazard: a wildcard in a
sudoers rule is almost always broader than the author pictured. Prefer exact commands; when
a wildcard is unavoidable, write down what it actually permits.

**9.4 — Validation that lives only at the call site is one refactor from being lost.**
Every guard in §4 sits immediately above the command it protects and says so in a comment.
When the GUI is split into modules (ONEUP-0034), a guard and its command must not end up in
different files with the assumption travelling between them implicitly.

**9.5 — `--check` must never authenticate.** It is strictly read-only, runs **without
root**, and must never call `zypper dup`/`update`. The mock in the test suite exits 99 if it
does, and a separate sentinel test asserts `--check` invokes `sudo` **zero** times. This is
what makes the background timer and the tray check safe to run unattended.

**9.6 — A test must not damage the machine it runs on.** Scenarios that invoke the engine —
or any code extracted from it — outside `run_engine` must redirect `ONEUP_ZYPP_PID_FILE`,
`ONEUP_RUN_STATE` and `ONEUP_STOP_FILE` by hand. Both defaults have bitten for real; the
incidents and the rule are `docs/standards/testing.md` §2, which is canonical.

---

## 10. Before you commit

- [ ] No new `sudo` in the GUI; any new `pkexec` — or privileged `startDetached` — argued against §1.5 and argv-form if possible.
- [ ] Every value reaching a privileged command validated by shape at the boundary (§4), failing closed.
- [ ] No privileged call inside a subshell — captured with `sudo_capture`, or the Python equivalent from §2.3.
- [ ] Any new background helper watches the engine's pid and dies with it (§2.4).
- [ ] `SUDO_ASKPASS` and `SUDO_PROMPT` still **exported**, and any new *authenticating* call labelled with `-p` (§3).
- [ ] No new code path that signals the engine during a transaction (§6.1).
- [ ] Nothing captured from a privileged command echoed to the log unreviewed — no bare `echo "$CAPTURED"` of a `sudo_capture` variable (§7.3).
- [ ] `--check` still authenticates zero times (§9.5).
- [ ] Tests redirect the three state-file overrides (§9.6).

---

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-07-26 | 9 critical, 19 high, 28 medium, 30 low (set-wide, batch 1) | all verified findings fixed; this document's share: §1.2's "21 of 22 through `sudo_capture`" was wrong (14 of 34) and contradicted §2.2's own top-level-`sudo` rule; "never launches `zypper` itself" was false (`read_repos`); §3.1 demanded `-A -p` on every call when 20 of 21 deliberately inherit it from the exported environment; and `Updater.restart_now`'s `systemctl reboot` was missing from the privileged-site inventory |

---

## Related

- `docs/standards/coding.md` — subprocess discipline, and why `shell=True` stays absent
- `docs/standards/testing.md` — the mock-`PATH` sandbox and machine isolation
- `docs/standards/dependencies.md` — version policy and the incompatibility ledger
- `docs/reference/marker-protocol.md` — the engine↔GUI contract these guards validate
- `docs/design/oneup-2.0.md` §7 — gate G5, the engine importing no Qt

