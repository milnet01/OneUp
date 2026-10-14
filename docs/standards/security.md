# Security Standard

**In one sentence:** this file says which half of OneUp is allowed to become root, how it
asks the user for permission, what it must check before passing a value to a root command,
and what may be written to a log — because OneUp's whole job is running privileged
commands, and every bug in this file is a root bug.

**Status:** Reviewed
**Kind:** doc
**Roadmap:** ONEUP-0057
**Branch:** main
**Verified at:** `58ea3bc` — every count and rule below was measured against the tree on
2026-07-26, not recalled. Where a claim was checked and turned out different from the
project's own prior description, the correction is stated in place.

**Sections:** the threat model · 1 the privilege boundary · 2 one authentication per run · 3 attributable
prompts · 4 validate at the boundary · 5 the passwordless drop-in · 6 cooperative
stopping · 7 logs · 8 supply chain · 9 traps · 10 before you commit · what checks this · 11 cold-eyes log

---

## The threat model

Unnumbered, and first because everything after it derives from it. Added
2026-09-02 on the user's decision (ONEUP-0185). Until then this document named no
attacker and no trust boundary, so the model had to be inferred from §1, §4 and
§7 — and three review lanes inferred three different ones.

**The first asset is root.** OneUp's job is running privileged commands, so any
defect that changes which command runs as root, or with what argument, is a root
defect.

**The second is what passes through the logs.** Captured privileged output can
carry repository URLs with embedded credentials, and the diagnostics bundle
carries the user's name and hostname. §7 is that asset's rule, and §7.4's *"any
future 'share this' feature inherits the rule"* is what makes it an asset rather
than one feature's problem.

**The attacker is the data, not the person.** In scope is everything OneUp did
not write and cannot vouch for: repository metadata, package and repository
names, the output of every tool it shells out to, and mirror responses. **§4
governs such a value where it reaches a privileged command**, which is §4's own
rule and is narrower than "all untrusted input". Elsewhere a malformed value is
a correctness defect, not a security one.

**The person at the keyboard is trusted, and so is every account on the machine.**
A hostile local user is **out of scope**: OneUp is a single-user desktop tool.
That is a decision about whom OneUp defends, not a claim about what a local
account can already do. Under `targetpw` (§3.3) `sudo` asks for the **root**
password rather than the user's, and §5's drop-in is a user-granted exception
giving *this* account password-free root for OneUp's commands — the exclusion
rests on the single-user decision above, and on neither of those. Three
consequences, named so they are not re-argued: the permissions on
`~/.local/state/oneup/`, the predictability of the tray's `QLocalServer` socket
name, and the fixed temporary paths in `local-CI.sh` are not defended here.
`local-CI.sh` is the gate runner rather than a test, so `docs/standards/testing.md`
§2.3 binds the suites it invokes and not the runner itself.

**The exclusion does not reach §5 — that is what §5 is for.** The drop-in grants
*this* account password-free root, and it is exercised with no person present, by
processes running as the trusted user. So §5.2's rule that a budget is a literal
and never a wildcard, and §9.3's preference for exact commands, stand unchanged.
Nothing here relaxes them.

**Out of scope is about whose input is trusted, never about correctness.** A
symlink followed without care, or a race that corrupts a real run, is still a
defect — filed as correctness rather than as security. A file OneUp wrote is read
back defensively for that reason: a run that was killed leaves a truncated one,
which is malformed without being an attack.

**Also out of scope:** a distribution mirror serving signed-but-malicious
packages, which is the distribution's signing chain rather than OneUp's; §8
answers OneUp's own supply chain. Physical access, and a hostile kernel or init.

---

## 1. The privilege boundary

This is rule one. Everything else in this document exists to keep it true.

**1.1 — The GUI process never becomes root, and never calls `sudo`.** Measured: the window
package `oneup/gui/` and the `updater.py` shim contain **zero** `sudo` invocations.
Root work is delegated, never assumed.

**1.2 — The engine is the only thing that runs privileged commands during an update.**
Measured at `58ea3bc`, `update_system.sh` made **34** privileged invocations: **14**
through `sudo_capture` (§2.2) and **20** direct `sudo` calls at command position. (Two more
`sudo` lines sit *inside* `sudo_capture` itself — they are the helper, not call sites.) That
is a measurement of one commit and not a standing figure
(`docs/standards/documentation.md` §6b.4); the **split** is the rule, and it holds at any
count. **This document owns the breakdown and how it was taken.**
`docs/design/oneup-2.0.md` §2 carries the total as one of its dated 2.0 baselines and cites
this section rather than repeating the derivation — the earlier arrangement, where both
stated the split, is what produced the 21-of-22 against 14-of-34 contradiction the first
review found. The direct calls are the streaming and fire-and-forget ones that
**must** stay at top level: `sudo … | tee` keeps sudo as the caller's own child, which is
exactly what §2.2 requires.

The GUI launches the engine with `QProcess` and reads its output; it never launches a
**privileged** `zypper`. It does make direct, unprivileged calls, none of which needs
root: `read_repos` runs `zypper --non-interactive lr -u` to list repositories, and the
package details (ONEUP-0260) run `zypper --no-refresh --non-interactive info` and
`rpm -q` / `rpm -qp` queries, each a fixed list argv with `LC_ALL=C` (§4.5).

**On a packaged install the engine asks rather than runs** (ONEUP-0249). Where OneUp's
system service is installed, the engine sends it an operation's name and arguments, and
the service runs the command as root (§12). The engine still decides every root command a
run makes; it no longer runs them itself. Which route a run takes is
`oneup/engine/route.py`'s `engine_route`, chosen once per run.

**1.3 — The engine never imports Qt.** The Python engine imports nothing from PySide6 or
from the window's package (`tests/imports-test.py`'s INV-3 fails on the second); the Bash
fallback imports nothing at all. The property that matters, and the one gate **G5** tests, is that the engine
runs with **PySide6 absent**. This is gate **G5** in the 2.0 design, and it tests HALF of
the split — the dependency direction. The other half is the import rule,
`docs/standards/files-and-naming.md` §4.1 rule 2: an engine module importing a Qt-free
helper out of the GUI package passes G5 and breaches the split anyway. The moment the
privileged half can draw a window, "the GUI is not root" stops being structural and
becomes a promise.

**1.4 — But the GUI *may* ask polkit to run a specific program as root.** This is the part
the project's own documentation previously overstated, so state it exactly:

> The GUI never *becomes* root. It may ask **`pkexec`** to run a named program as root, at
> a small fixed set of sites, with every argument validated first (§4).

There are exactly **three** such sites, all user-initiated, all one-shot, none part of an
update run:

| Site | Command | Guard |
| --- | --- | --- |
| `RepoManagerDialog._build_apply_command` | `pkexec sh -c "zypper … modifyrepo/removerepo <aliases>"` | every alias must match `_ALIAS_RE`, else the whole command is `None` and nothing runs |
| `banners.restart_services` | `pkexec systemctl restart <units>` — **argv form, no shell** | each unit matched against a unit-name pattern; anything starting `-` dropped; and every **session-critical** unit removed before the command is built (§4.6) |
| `rollback.rollback` | `pkexec sh -c "snapper rollback <id> \|\| exit 3; systemctl reboot \|\| exit 4"` | `id` must satisfy `str.isdecimal()` — never `isdigit()`, which also accepts superscript digits such as `²` |

One more privileged action does not go through `pkexec` at all and must not be forgotten
when this list is checked:

| Site | Command | Guard |
| --- | --- | --- |
| `banners.restart_now` | `QProcess.startDetached("systemctl", ["reboot"])` — argv form | **no arguments, so nothing to validate**; logind's own polkit policy decides whether an active local session may reboot |

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

**2.1 — The engine authenticates once, up front.** The engine's `sudo_init` (in its
privilege module; the Bash fallback has a function of the same name) raises a single graphical prompt via `sudo -A -p "<label>" -v`, then starts a keep-alive that refreshes
the credential every 50 seconds for the life of the run. **Zero** prompts, and no
keep-alive at all, when §5's passwordless drop-in is active **and covers what this engine
issues** — `sudo_init` asks `auth_current`, not merely whether a rule exists, and returns
early only then.

That distinction is ONEUP-0092. A drop-in installed by an older OneUp is live, satisfies a
`sudo -n zypper --version` probe, and still leaves three calls prompting — so the old early
return skipped the bootstrap and the user met sudo's own bare prompt in the middle of step
1, on a run they had told OneUp to do without one. Falling through instead costs one
labelled prompt up front, which is the honest failure and the safety net for anything the
rule turns out not to cover.

**2.2 — In the Bash engine, privileged output is captured with `sudo_capture`, never a
subshell.** It binds `main`'s engine and the retained fallback; §2.3 is the Python form.
This is the most expensive trap in the project's history and the reason the helper exists:

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
modules; route them through a single helper that is the sudo parent for the whole run, as
`sudo_capture` is in the Bash engine. That helper is the privilege module's `sudo`. **The failure mode carries over; the symptom does
NOT.** In Python every `subprocess.run(["sudo", …])` has the one engine process as sudo's
parent, so scattered calls share a credential and raise no extra dialog — the Bash symptom
exists only because bash forks a real subshell with its own pid (§2.2). **So prompt
counting cannot detect this shape, and nothing gates it today.** The reason to route through
one helper is a single sudo parent, one exported askpass environment and one keep-alive
owner. Write that down at the helper.

**2.4 — Nothing the engine spawns may outlive it.** `cleanup`'s trap cannot run when the
engine is `SIGKILL`ed, so the keep-alive **also watches the engine's pid and exits on its
own**. It runs in its own process group so `cleanup` can kill the whole group
(`kill -- -PGID`) — a plain `kill` on the subshell orphans the inner `sleep 50`, which
reparents to `systemd --user` rather than to pid 1, so an orphan check written against
pid 1 can never fire. The live idiom is polling `kill -0` on the captured engine pid, never
a re-read of `$PPID`. It carries the tag `oneup-keepalive` in `$0` so a test can find it.

That group is a new process group, **never a new session**. Started from a terminal, sudo
keys the cached credential to that terminal's session. A helper in a new session has no
terminal, so its refresh renews a different record. Measured 2026-10-02 on a run started
from Konsole: the real credential expired after five minutes, and the next call needing it
prompted unseen in the terminal (ONEUP-0231). The Bash engine gets the group by turning on
job control for that one launch (`set -m`), not with `setsid`; the Python engine passes
`process_group=0`, not `start_new_session=True`.

Measured: before this, two keep-alives were found still calling `sudo -n -v` every 50
seconds, **40 minutes after** the runs that spawned them had been killed (ONEUP-0041). Any
new background helper inherits this rule.

**2.5 — On the service route, the one authentication is one polkit check.** `sudo_init`
opens a session with the service, which asks polkit once (§12.4), and starts no
keep-alive. Discover's rule decides: under openSUSE's default policy a user at the desktop
sees no box (ONEUP-0249 §2.4). When polkit answers `challenge`, because it had no way to ask
the caller, the run falls back to the sudo route and its one prompt (§4.7). That an SSH
shell gets `challenge` is not yet measured (§4.12 item 1).

---

## 3. Every prompt must say who is asking, and why

A root password prompt the user cannot attribute is indistinguishable from a phishing
dialog, and the correct response to one is to refuse it. So:

**3.1 — Attribution comes from the exported environment, and the *authenticating* call
carries it explicitly.** Exactly one `sudo` in the engine passes `-A` and `-p`:
`sudo_init`'s `sudo -A -p "<label>" -v`, which is the call that actually prompts. Rendered
with the `-p` it asserts, because this is the worked form §2.3 tells the Python engine to
reproduce. Every other
privileged call — direct or through `sudo_capture`, §1.2 owning the breakdown — is
plain `sudo` **on purpose**: each inherits the exported `SUDO_ASKPASS` and `SUDO_PROMPT`
(3.2, 3.3), so if any of them ever has to ask, the prompt is graphical and labelled
anyway. That is why the export is mandatory rather than a convenience: it is what makes
"every prompt is attributable" true of a call site that never mentions it.
`ASKPASS` defaults to `/usr/libexec/ssh/ksshaskpass` and is overridable via
`ONEUP_ASKPASS` so tests point it at a mock (the engine's `ASKPASS` constant in its
privilege module; the Bash fallback's near the top of `update_system.sh`).

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
# oneup/gui/repos.py, the module-level _ALIAS_RE — repo aliases. The first character
# class excludes '-', so an alias can never be read as an option by zypper; no
# space, quote, ';', '&', '$' or backtick is permitted, so it cannot break out
# of the sh -c string either.
_ALIAS_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9:@._+-]*")
# …used as: if not _ALIAS_RE.fullmatch(alias): return None

# rollback.rollback — the rollback target is interpolated into a root shell.
if not target.isdecimal(): return        # isdecimal() also rejects empty
# Not isdigit(): it also accepts superscript digits ('²'), which int() refuses (ONEUP-0153).

# banners._service_units, behind restart_services — service units, argv form. The first character class excludes
# '-' so a spliced token cannot be read as a systemctl option; the startswith test repeats
# that structurally. No ".service" suffix is required, because `zypper ps -sss` prints bare
# unit names (ONEUP-0110).
return [s for s in win._services.split()
        if not s.startswith("-") and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:@._-]*", s)]
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

**4.5 — The unprivileged details reads take the same shape test.** A package name or
edition from the package list reaches a `zypper` or `rpm` argv, and an rpm file glob,
in `oneup/gui/package_details.py`. Neither command is privileged, but a name read as an
option would still change what runs:

```python
# oneup/gui/package_details.py — a package name. The first character excludes '-',
# so a name can never be read as an option; neither class holds a glob character.
_NAME_RE = re.compile(r"[A-Za-z0-9_+][A-Za-z0-9._+-]*")
# An edition once its epoch ("N:") is removed; rpm file names carry none.
_EDITION_RE = re.compile(r"[A-Za-z0-9._+~^-]+")
```

A name that fails `_NAME_RE` is left out of the batched argv; an edition that fails
`_EDITION_RE` gets no What changed and runs nothing. `tests/parsers-test.py` covers
both (ONEUP-0260 INV-2).

**4.5 — Resolved 2026-08-18 (ONEUP-0110).** The unit-name pattern in 4.1 permitted a
literal **backslash** — a typo for `\-`, never exploitable, since that site is argv-form and
a backslash simply names a unit that does not exist. It was recorded here rather than filed,
to be tidied when the file was next touched for another reason. That happened: the same
pattern was rejecting every name the engine actually sends, and the fix removed the
backslash in the same edit. The pattern now leads with `[A-Za-z0-9]`, which is the shape
`_ALIAS_RE` already used and which excludes a leading `-` structurally rather than by the
separate test alone.

**4.6 — A privileged command may be correct and still be unsafe to run.** Validation
answers *can this value hurt me on the way to root*. It does not answer *should this run at
all*, and `banners.restart_services` is where the difference bites: `systemctl restart
display-manager` is perfectly well-formed and ends the user's session.

`zypper ps -sss` reports whatever holds a replaced library, so after a glibc, systemd, Qt or
dbus update it names the longest-running processes on the box — which are the ones that *are*
the session. The window therefore removes them before building the command, rather than
warning about them:

- the **display manager**, resolved from `/etc/systemd/system/display-manager.service`
  rather than guessed, with a literal fallback list;
- **`user@<uid>`**, the user's own systemd session — which contains the window, so a restart
  kills OneUp while its own `startDetached` command is still running;
- the system **`dbus`** and **`systemd-logind`**;
- **`polkit`**, which is the agent that just authorised the `pkexec` carrying the command.

**They are not offered behind a confirmation.** A dialog cannot make losing unsaved work a
reasonable thing to click, and the window already owns a reboot affordance, which is the
honest advice. Decided with the user 2026-08-18 (ONEUP-0111). `NetworkManager` and `wickedd`
are deliberately *not* in the set: disruptive, recoverable, and legitimate to restart.

**And where the honest advice is a reboot, the reboot is what the window offers**
(ONEUP-0115, user 2026-08-19). Removing a unit from the command is only half the job: an
exclusion the user cannot act on is a dead end. So the split is made when the banners are
drawn, not only inside the handler — every unit session-critical shows the **reboot** banner
and not the services one; a mixed list shows both, because the safe half can genuinely be
restarted now. Recommending a restart and then leaving the user to find the control is the
failure this closes.

**The split is made once, from one list.** `banners._service_units` filters the marker
payload and both the banner and the handler read it. ONEUP-0110 was invisible for months
because the banner was drawn from the raw payload while the handler acted on a filtered
copy, so the two could disagree with nothing on screen to show it.

**The general rule this instances: a guard that only checks shape will pass a
well-formed command that should never be issued.** When a privileged call takes a *name*
supplied by another program, ask what the worst legal name does.

**4.7 — A bad refresh budget fails the refresh; it never falls back.**
`ONEUP_REFRESH_TIMEOUT` comes from the environment and reaches `sudo timeout <budget>
zypper …` on every refresh. `docs/specs/ONEUP-0092-passwordless-gaps.md` §6 decides that a
non-numeric budget fails the refresh, rather than quietly falling back to the default. A
check that substituted the default would hide the user's broken setting.

`oneup/engine/rootops.py` builds that command and refuses any budget but a positive whole
number of seconds (ONEUP-0249 §4.2). So a bad budget runs nothing, and each refresh fails
with one line saying why.

The budget is also pinned to digits where it reaches the sudoers rule, in `auth_cmnds`,
because there a wildcard would make it exploitable (§5).

---

---

## 5. The passwordless drop-in

Opt-in, never silent, scoped, revocable. All four properties are load-bearing.

**The drop-in belongs to the sudo route**: the AppImage, and any install without the system
service. On the service route the engine never consults it (§2.5, §12).

**5.1 — What it is.** `--grant-auth` writes a `sudoers` drop-in that lets *this user* run
OneUp's update commands as root without a password. It stores **no password anywhere** —
not in a keyring, not in a file, not in memory.

**5.2 — The exact scope**, built from resolved absolute paths at grant time
(`build_auth_rule` in the engine's actions module; the Bash fallback has its own):

| Entry | Why |
| --- | --- |
| `zypper` (any arguments) | the update itself |
| `snapper` (any arguments) | snapshot create/list — the rule adds the bare resolved path, so it also permits `snapper delete` |
| `flatpak` (any arguments) | flatpak update/uninstall — likewise unrestricted by subcommand |
| `systemctl stop packagekit` | releases the package lock |
| `env LC_ALL=C zypper *` | the engine pins the locale via `sudo env …`, and sudo matches the rest of the argv literally, so the wrapper form needs its own entry |
| `timeout <budget> zypper *` | `refresh_repos` bounds each repository with `sudo timeout`, because zypper has none of its own. **The budget is a literal, never a wildcard**: sudoers matches arguments as one space-joined string, so `timeout * zypper *` is satisfied by `timeout 5 /bin/sh -c 'zypper x'` — a root shell. Measured against that exact string before it shipped (ONEUP-0092) |
| `du -sB1 /var/cache/zypp` | the cache step measures the package cache before and after the clean. Fixed argv, no wildcard: `du` takes no sub-command, so there is nothing to escape into |
| the download guard (`/usr/libexec/oneup-download-guard`, `/usr/lib/…` on Leap) | §5.7. **No argument spec**, so any arguments are permitted — required, because the transaction argv varies. The guard restricts itself instead |

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

**The grant installs two files, and the order is part of the rule.** Validate first, then
the guard (§5.7), then the drop-in — and **any failure after the guard lands removes it
again**. A stranded root-owned executable is worse than a failed grant: afterwards the
toggle reads off, which makes the GUI's revoke arm unreachable, so the user has consented
to a file they can no longer withdraw. Equally, a `Cmnd` that is not a fully-qualified path
is a sudoers *parse error* that takes the whole rule down, so an unresolvable binary makes
the grant **refuse** rather than emit a bare name.

**5.5 — Revocation is immediate and complete**: `--revoke-auth` deletes the drop-in **and
the download guard** — both candidate paths, since `/usr/libexec` may have appeared after
the grant and moved it. There is no "disabled but retained" state, and no root-owned file
left behind after consent is withdrawn.

**5.6 — Report real state, never a saved preference.** `--auth-status` reports `on` only
when `auth_current` succeeds, which is two questions rather than one: the rule is live —
`sudo -k -n <zypper> --version`, where `-k` ignores any cached credential so a recent run
cannot produce a false positive and `-n` refuses to prompt — **and** it grants what this
engine issues, which §5.7's guard is the evidence for. If the rule were removed outside
OneUp, or was written by a OneUp that granted less, the toggle must show off. A settings
toggle that reports what it *stored* rather than what *is* is a security bug, and so is one
that reports a rule's existence rather than its sufficiency.

`sudo -k` suppresses the cache for its own invocation without invalidating it — measured,
so the probe costs the next call nothing.

**5.7 — The download guard: a scoped script, never a general-purpose binary.** The download
pass needs a root-side wrapper that can signal its own zypper child, and `env LC_ALL=C bash
-c *` cannot be granted — it is a root shell in sudoers clothing. So the wrapper is a file
instead: root-owned, `0755`, installed by the grant and removed by the revoke, carrying a
zypper path frozen at grant time and refusing any argument that is not that zypper. Its
authority is therefore exactly the drop-in's own `zypper` entry, and no more.

It doubles as the drop-in's **version stamp**. The drop-in is `0440 root:root`, so the
engine cannot read back what it granted; the guard is world-readable, written by the same
grant, and carries the whole granted scope in a `# oneup-auth-scope:` comment. "The
installed guard is the text this engine would emit" therefore answers "was this rule
written by a OneUp that grants what this run needs". Two things it cannot see, both
recorded rather than papered over: it is not proof that sudo *matches* the entries
(`visudo -cf` is), and it cannot detect a drop-in **replaced** afterwards by an older
OneUp. **Editing the guard's text is a re-grant for every existing user**, because the
comparison is over the whole text.

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

**6.3 — A run must survive the GUI going away.** The Python engine mirrors its own log:
when the window's end of stdout goes, the mirror catches the `BrokenPipeError`, marks the
console gone and carries on writing the log, and no child it starts inherits the window's
pipe, so none can be `SIGPIPE`d by the quit. The Bash engine's logging `exec` uses `tee -a
-p` (`--output-error=warn-nopipe`); without `-p`, quitting the GUI kills `tee`, which
`SIGPIPE`s the engine on its next line, so `cleanup` never runs and zypper is orphaned
mid-transaction. There `-p` is **probed, not assumed**, with a `PIPE` trap as the fallback. Correspondingly the GUI
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
(`build_diagnostics` in `oneup/gui/diagnostics.py`) replaces the home path with `~` and the hostname
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
**It sees a second prompt caused by a subshell, and not a second `sudo_init` inside one
process**: the mock keys its timestamp to `$PPID`, so two calls from one engine share a
record and log a single prompt. That shape is caught by the keep-alive scenario instead —
ONEUP-0044's **INV-9**, not its §7.1, which is about the mocks' `-k` handling. Re-measured
2026-09-02: removing the `HELD_AUTH` guard fails exactly one check, *"a keep-alive survived
a held run (INV-9)"*, and leaves the one-prompt scenario green.

**9.3 — `sudoers` wildcards match spaces.** `env LC_ALL=C zypper *` grants everything after
that literal prefix. This is intended here (§5.3) but is a general hazard: a wildcard in a
sudoers rule is almost always broader than the author pictured. Prefer exact commands; when
a wildcard is unavoidable, write down what it actually permits.

**9.4 — Validation that lives only at the call site is one refactor from being lost.**
Every guard in §4 sits immediately above the command it protects and says so in a comment.
When the GUI is split into modules (ONEUP-0034, done on `v2` on 2026-08-20), a guard and its
command must not end up in different files with the assumption travelling between them
implicitly. That is what kept `_split_session_critical` with `restart_services`, the alias
guard with the repository apply command, and the snapshot-id check with the rollback call:
each pair moved into one module together.

**9.5 — `--check` must never authenticate.** It is strictly read-only, runs **without
root**, and must never call `zypper dup`/`update`. The mock in the test suite exits 99 if it
does, and a separate sentinel test asserts `--check` invokes `sudo` **zero** times. This is
what makes the background timer and the tray check safe to run unattended.

**9.6 — A test must not damage the machine it runs on.** Scenarios that invoke the engine —
or any code extracted from it — outside `run_engine` must redirect **every** `ONEUP_*` state
path that helper sets. **Read the set out of `run_engine`, never out of a count in prose:**
this rule was written as a fixed number twice and went stale both times, most recently when
ONEUP-0044 added `hold.state` and `go.request`. Two of the paths have bitten for real;
`ONEUP_GUARD_FILE` is among them because `guard_current` reads it on every run that reaches
the download pass, so a scenario leaving it alone passes or fails according to whether the
developer happens to have granted passwordless. The incidents and the current list are
`docs/standards/testing.md` §2.1, which is canonical.

---

## 10. Before you commit

- [ ] No new `sudo` in the GUI; any new `pkexec` — or privileged `startDetached` — argued against §1.5 and argv-form if possible.
- [ ] Every value reaching a privileged command validated by shape at the boundary (§4), failing closed.
- [ ] No privileged call inside a subshell — captured with `sudo_capture`, or the Python equivalent from §2.3.
- [ ] Any new background helper watches the engine's pid and dies with it (§2.4).
- [ ] `SUDO_ASKPASS` and `SUDO_PROMPT` still **exported**, and any new *authenticating* call labelled with `-p` (§3).
- [ ] No new code path that signals the engine during a transaction (§6.1).
- [ ] Nothing captured from a privileged command echoed to the log unreviewed — no bare `echo "$CAPTURED"` of a `sudo_capture` variable (§7.3).
- [ ] `--check` still invokes `sudo` zero times (§9.5).
- [ ] Tests redirect every state-file override `run_engine` sets (§9.6).

---

## 12. The system service

On a packaged install, the engine's root commands run in OneUp's system service,
`oneup/service/`, instead of under `sudo` (ONEUP-0249). The spec,
`docs/specs/ONEUP-0249-system-service.md` §4, holds the design. These are the rules a change
to the service must keep.

**12.1 — The service takes an operation's name, never a command.** It builds every argv from
`oneup/engine/rootops.py`'s table, after that operation's validators pass. An unknown
operation, an unknown or missing argument, or a wrong D-Bus type is refused, and no child
starts (INV-1).

**12.2 — The checks that need state live in the service.** An alias must name a repository
in the repository files. `repo-enable` undoes only the session's own disable.
`orphans-remove` takes only names that zypper itself just listed as unneeded (INV-6, INV-7).

**12.3 — No operation takes a path, and no client sets the environment.** The service builds
its own CDN copy of the repository files. Its test overrides come from its own environment,
which only the unit or a test harness sets (§5.1 of `files-and-naming.md`).

**12.4 — Who may is polkit's answer to Discover's permission.** The action is
`org.freedesktop.packagekit.system-update`, and the subject is the caller's unique bus name,
never a pid. Any error is a refusal, and a caller who left during the check is refused.
Importing signing keys also needs `system-trust-signing-key`, and nothing sent after
`OpenSession` widens a session (INV-2, INV-3). **The package ships no polkit file of any
kind** (INV-13).

**12.5 — Caps.** One session per caller, eight in all, and one running job in the whole
service (INV-9).

**12.6 — A job is never killed by its caller leaving or by the service dying.** The child
writes to a job file under `/run/oneup/`, never to a pipe. The unit sets `KillMode=process`.
Only `system-download` can be stopped, by `SIGTERM`; `system-commit` is never signalled
(INV-5, §6.1).

**12.7 — When a session ends, its repository changes are undone**, once no job holds zypp's
lock (INV-6).

**12.8 — Every session opened or refused, and every job started and ended, writes one
journal line** (INV-14). With no session and no job for the idle period, the service exits
(INV-15).

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §1 the GUI never runs as root | nothing automatic |
| §2 one authentication per run | `tests/run-tests.sh` — *"a full run asks for the password exactly once"*, against a mock that models sudo's per-parent-pid credential cache |
| §2 no `sudo` inside a subshell | the same scenario, because a subshell **is** a second prompt. The rule and its symptom are the same thing, which is what makes this the strongest gate in the set. It does **not** see a re-entrant `sudo_init` inside one process — the mock keys on `$PPID`, so that shape belongs to the keep-alive row |
| §2.3 one runner object owns every privileged child (Python engine) | nothing automatic — and prompt counting cannot see it, because one Python process is one sudo parent |
| §3 every prompt says who is asking | nothing automatic |
| §4 validate at the boundary, by shape — the alias guard | `tests/run-tests.sh` — an unsafe repo alias is refused and never reaches a privileged command, whether it arrives as `--skip-repo=` or in zypper's own repository list; `tests/gui-smoke.py` — an unsafe alias in a skip-repo remedy is not armed, so the window never forwards it. The list half was added 2026-09-18 (ONEUP-0144); until then only `disable_repo` checked, and the refresh took the list unchecked |
| §4.6 no session-critical service is ever restarted | `tests/gui-smoke.py` — a mixed list restarts the safe units and **no** critical one, and an all-critical list restarts nothing; `tests/run-tests.sh` asserts the engine's printed advice splits them the same way |
| §4.6 where the advice is a reboot, the reboot is offered | `tests/gui-smoke.py` — an all-critical list draws the reboot banner and not the services banner, a mixed list draws both, and the handler's all-critical path launches `systemctl reboot` rather than an information dialog; `tests/run-tests.sh` asserts the engine prints the same recommendation |
| §4.6 the banner and the handler read the same filtered list | **nothing directly.** `_service_units` is the shared source, and the tests exercise both sides of it, but nothing fails if a future edit re-reads the raw payload in one of them — which is exactly how ONEUP-0110 hid |
| §4 validate at the boundary, by shape — the window's service-unit guard | `tests/gui-smoke.py` — the units the engine really sends reach `systemctl`, and an option-shaped token does not. **Added 2026-08-18 (ONEUP-0110); until then this half had no gate**, and the guard rejected every real name for months while the alias row above stayed green. A validator is only as good as the population it was tested against: the one scenario that fed this field used `foo.service`, a shape `zypper ps -sss` never prints |
| §5 the passwordless drop-in | `tests/run-tests.sh` — grant, revoke and status, and the generated file is put through a real `visudo -cf` |
| §5.2 the rule covers every shape a run issues | `tests/run-tests.sh` — the grant scenario asserts each entry by name, **and** a structural check pins the engine's privileged call-site count, so a *new* `sudo …` line fails the suite until it is granted. Nothing behavioural can catch that: an ungranted call is correct code that merely prompts, and only a passwordless user ever finds out |
| §5.2 no general-purpose binary with an unpinned command slot | `tests/run-tests.sh` — the generated rule is asserted not to match `timeout *`, ` bash` or ` sh -c`, and the timeout entry is asserted to pin its budget to digits. The real-sudo evidence is the ONEUP-0092 measurement, which no test may reproduce (`testing.md` §2.3 forbids real `sudo`) |
| §5.4 the grant is all-or-nothing | `tests/run-tests.sh` — an `install` that refuses the drop-in leaves neither file, and a non-numeric refresh budget is refused with a hint |
| §5.5 revocation removes the guard too | `tests/run-tests.sh` — revoke deletes both files |
| §5.6 "on" means passwordless works | `tests/run-tests.sh` — `--auth-status` across live-and-current, live-but-stale, and absent |
| §5.7 the guard runs zypper and nothing else | `tests/run-tests.sh` — it refuses a non-zypper argv with exit 2, appends `--download-only`, TERMs its child on a stop request and reaps it. The stop scenario also runs over **both** wrappers, so the guard cannot silently drop the stop poll for the users who enabled passwordless |
| §9.5 `--check` invokes `sudo` zero times | `tests/run-tests.sh` — *"`--check` performs NO privileged auth"*, backed by a mock that exits 99 if a transaction is attempted, plus the sentinel that counts `sudo` invocations. **Invoking and authenticating are not the same test** — §5.6's `auth_current` probe (`sudo -k -n … --version`) is a `sudo` invocation that authenticates nothing |
| §6 stopping is cooperative | `tests/run-tests.sh` |
| §7.4 the diagnostics bundle carries no identifiers | `tests/gui-smoke.py` — the bundle has its hostname scrubbed |
| §7.3 captured privileged output is not echoed to the log | nothing automatic — the §10 checklist is the only gate |
| §8 supply chain | nothing automatic |
| nothing the engine spawns outlives it | `tests/run-tests.sh` — the sudo keep-alive leaves no orphaned process when a run ends |
| §12.1–12.8 the system service's rules | `tests/service-test.py` — a private bus, a fake polkit and mock binaries; each invariant the section cites has its own scenario there. INV-13 is a structural check in `tests/run-tests.sh` |
| §1.2 and §2.5 the service route runs no `sudo` and prints what the sudo route prints | `tests/run-tests.sh` — the same update on both routes against one set of mocks: zero `sudo` calls on the service route, and equal marker streams (INV-8) |
| §2.4 a new process group, never a new session | `tests/run-tests.sh` — run under `script` for a real terminal, the keep-alive's refresh comes from the engine's session and terminal, and from a group that is not the engine's |

**This is the best-gated standard in the set**, and the reason is worth copying rather than
admiring: each rule was written so that breaking it produces a *visible symptom* — a second
password prompt, an orphaned process, a mutation during a read-only pass. A rule whose breach
shows up as nothing in particular cannot be tested, however carefully it is worded.

## 11. Cold-eyes loop log

The rows are in [`docs/reviews/security-loop-log.md`](../reviews/security-loop-log.md).

## Related

- `docs/standards/coding.md` — subprocess discipline, and why `shell=True` stays absent
- `docs/standards/testing.md` — the mock-`PATH` sandbox and machine isolation
- `docs/standards/dependencies.md` — version policy and the incompatibility ledger
- `docs/reference/marker-protocol.md` — the engine↔GUI contract these guards validate
- `docs/design/oneup-2.0.md` §7 — gate G5, the engine importing no Qt

