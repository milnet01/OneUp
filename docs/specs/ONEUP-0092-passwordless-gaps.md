# ONEUP-0092 — Passwordless actually runs without a password

**Status:** Draft
**Kind:** fix
**Roadmap:** ONEUP-0092, ONEUP-0099
**Branch:** main (1.4.x — qualifies under `workflow.md` §1.1: with automatic updates on, the
weekly run installs nothing and says nothing)
**Verified at:** `9fe90e9` — every claim naming a symbol below was resolved against this
tree, not recalled. Every measurement names the command that produced it and the date it
was run.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** Turning on *Passwordless* stops the password box appearing, because
the rule OneUp installs finally covers every privileged command a run actually issues —
and because OneUp now decides "passwordless is on" by checking that, rather than by asking
about one command out of six.

**Two roadmap items, one umbrella** (`documentation.md` §2 permits this where the items
share a cause). ONEUP-0092 is the prompt itself. ONEUP-0099 is what that prompt does to
automatic updates, which cannot run at all while one appears. Both come from the same
mistake: deciding passwordless is on from something narrower than what a run performs.

## 1. Goal

A user who turns *Passwordless* on sees no password box for the rest of a normal run —
system, Flatpak, firmware, orphans and cache — and the weekly automatic update, which
exists only because passwordless does, completes unattended. When the rule is missing,
removed behind OneUp's back, or too old to cover what this OneUp needs, the app says so and
asks once, up front, in its own labelled dialog — and the weekly update switches itself off
rather than firing into a dialog nobody is looking at.

## 2. Background

### 2.1 What the drop-in grants today

`build_auth_rule` in `update_system.sh` writes a `Cmnd_Alias` from binaries resolved on the
machine at grant time. Five entries, listed in `security.md` §5.2: `zypper` (any
arguments), `snapper`, `flatpak`, `systemctl stop packagekit`, and `env LC_ALL=C zypper *`.

`sudo_init` and `auth_status` both decide whether that rule is live with a single probe —
`sudo -k -n "$zypper" --version`. When it succeeds, `sudo_init` returns immediately: no
up-front prompt, and **no keep-alive**, on the stated grounds that "every privileged
command below is individually NOPASSWD".

### 2.2 The measured failure

That claim is false, and the probe cannot see it, because it asks about the one command
that *is* covered.

Measured 2026-08-07 on the reporter's machine, with the drop-in live. `sudo -k -n <argv>`
runs the command only when it needs no password — `-k` ignores any cached credential, so a
recent run cannot produce a false positive:

```
$ for c in "zypper --version" "env LC_ALL=C zypper --version" \
           "timeout 5 zypper --version" "du -sB1 /var/cache/zypp" \
           "env LC_ALL=C bash -c true"; do
      printf '%-34s' "$c"; sudo -k -n $c >/dev/null 2>&1 && echo FREE || echo PROMPTS; done
zypper --version                  FREE
env LC_ALL=C zypper --version     FREE
timeout 5 zypper --version        PROMPTS
du -sB1 /var/cache/zypp           PROMPTS
env LC_ALL=C bash -c true         PROMPTS
```

Three call sites, not the two ONEUP-0092 was filed against:

| Call site | The call | Step |
| --- | --- | --- |
| `refresh_repos` | `sudo timeout "$REFRESH_TIMEOUT" zypper … refresh "$alias"` | every repository, step 1 |
| `run_system_download` | `sudo env LC_ALL=C bash -c '…'` — the root-side stop wrapper (ONEUP-0085) | the download pass |
| the cache step | `sudo_capture CACHE_DU du -sB1 /var/cache/zypp`, twice | step 5 |

The reporter's screenshot is the first of these, at *"Checking for updates from devel-tools
(1 of 10)"*.

### 2.3 Why the third one decides the shape of the fix

Only one dialog appears in practice, because the first `sudo` to prompt warms sudo's
credential cache for the rest of the run — sudo keys it to the parent process id when there
is no terminal (`security.md` §2.2), and every later call sits in the engine's own shell.

So closing only the two filed gaps would **move** the prompt to the download pass, not
remove it. The `bash -c` wrapper is load-bearing, and it is the one that cannot be granted
by pattern: `env LC_ALL=C bash -c *` is a root shell in sudoers clothing.

### 2.4 What it costs the unattended run

`_install_user_timer` in `updater.py` writes `oneup-update.service` as a `systemd --user`
oneshot running the engine headless, and ONEUP-0022 gated that feature on passwordless
precisely so no dialog could appear. With these gaps, one does: the timer fires weekly, the
engine reaches the first repository refresh, `sudo` finds no terminal, launches the askpass
helper it exports (`ASKPASS`), and waits — for a dialog nobody is looking at, on a run
nobody started. Nothing is installed and nothing is said. That is `workflow.md` §1.1's
"silent wrong answer", once a week.

### 2.5 The half of the coupling that is missing (ONEUP-0099)

`on_auth_toggled`'s off arm already stands the timer down when the user **clicks**
*Passwordless* off: `_remove_user_timer("oneup-update")`, uncheck, and a message saying
why. It is deliberately hooked to the revoke action rather than the toggle signal.

Nothing stands it down when the app merely **discovers** passwordless is off.
`_query_auth_status` → `_on_auth_status_finished` → `_set_auth_checked` reflects the switch
under `blockSignals`, exactly so a reflect cannot fire grant/revoke — so the coupling arm
never runs. Two ways to reach it: the rule removed outside OneUp, and (new, below) a rule
too old to cover what this OneUp needs.

## 3. Scope decisions (agreed with the user)

- **This lands on `main` as a 1.4.x**, on the standing `workflow.md` §1.1 test rather than
  as a fourth §1.2 exception. §1.2's exceptions exist for changes that do *not* qualify;
  this one does, on both readings named in §1.1 — updates are not installed, and the run
  says nothing about it.
- **Automatic updates must switch themselves off whenever passwordless is off** — the
  user's rule, 2026-08-07, prompted by this fix and filed as ONEUP-0099. Not just when the
  toggle is clicked.
- **Stop must keep working during the download for passwordless users.** ONEUP-0085 shipped
  it; a fix that bought silence by dropping it would be a regression for exactly the people
  who opted in.
- **The rule keeps stating its risk plainly.** `security.md` §5.3 forbids softening the
  consent dialog, and this change widens the grant slightly (§4.6), so the wording is
  reviewed, not relaxed.

## 4. Design

### 4.1 The root cause, and what it implies

Two lists have to agree with the engine's privileged calls, and neither is derived from
them: what `build_auth_rule` grants, and what the `sudo -k -n zypper --version` probe
concludes. Adding three entries fixes today's three gaps and leaves the fourth to be found
by a user. So each shape gets **one definition, used by both the call and the rule**, and
the probe is replaced by one that cannot be satisfied by a subset.

### 4.2 One definition per shape

Two new file-scope arrays, beside `REFRESH_TIMEOUT`'s existing declaration:

```bash
# The refresh and the cache measurement both run under sudo, so the ONEUP-0023 drop-in
# must grant the EXACT argv each types or passwordless silently keeps prompting
# (ONEUP-0092). One definition each, used by the call site and by build_auth_rule, so
# the rule cannot drift from the call.
REFRESH_SUDO_ARGV=("$(command -v timeout || echo timeout)" "$REFRESH_TIMEOUT" zypper)
CACHE_DU_ARGV=("$(command -v du || echo du)" -sB1 /var/cache/zypp)
```

`refresh_repos` becomes `sudo "${REFRESH_SUDO_ARGV[@]}" --non-interactive "${gpg[@]}"
refresh "$alias"`; the cache step becomes `sudo_capture CACHE_DU "${CACHE_DU_ARGV[@]}"`.
Neither changes behaviour — the argv is byte-identical to today's, with `timeout` and `du`
now spelled as the absolute paths sudo resolves them to anyway.

`auth_cmnds` (new) echoes the comma-joined `Cmnd` list and becomes the only place the
granted scope is written:

| Entry | Source |
| --- | --- |
| `<zypper>`, `<snapper>`, `<flatpak>`, `<systemctl> stop packagekit`, `<env> LC_ALL=C zypper *` | unchanged, moved out of `build_auth_rule` |
| `${REFRESH_SUDO_ARGV[*]} *` | the refresh call, verbatim, plus its arguments |
| `${CACHE_DU_ARGV[*]}` | the cache measurement, verbatim. No wildcard — the argv is fixed |
| `$GUARD_FILE` | §4.3 |

**Why the refresh entry is safe**, and why it is written this way rather than as
`/usr/bin/timeout * zypper *`: sudoers matches a command's arguments as one
space-joined string, so a wildcard *before* the pinned command name can swallow one.
`timeout * zypper *` is satisfied by `timeout 5 /bin/sh -c 'zypper x'` — root shell. With
the budget pinned literally, nothing an attacker supplies precedes `zypper`.

Measured 2026-08-07, by installing a throwaway drop-in carrying exactly these patterns and
probing it with `sudo -k -n`, then removing it:

| Probe | Result |
| --- | --- |
| `timeout 120 zypper --version` | password-free |
| `du -sB1 /var/cache/zypp` | password-free |
| `<guard> a b c` | password-free |
| `timeout 120 /bin/sh -c 'zypper x'` | **not** password-free |
| `timeout 120 /bin/sh` | **not** password-free |
| `timeout 999 zypper --version` | **not** password-free |
| `du -sB1 /etc` | **not** password-free |

`secure_path` is in force on this machine — a `zypper` planted earlier on `PATH` did not run
under `sudo` — which is what makes the bare word `zypper` in these patterns resolve to the
real binary. The existing `env LC_ALL=C zypper *` entry has always depended on the same
property.

### 4.3 The download guard

`run_system_download`'s root-side wrapper cannot be granted as a pattern, so it stops being
an argument to `bash` and becomes a file: a small script, **root-owned and root-only
writable**, whose one job is the wrapper's job. The drop-in grants that path.

`download_guard_src` (new) emits the text; it is the single source, and the same text is
what runs. It differs from today's inline script in three ways, all of them the point:

- it pins the interpreter and the locale itself (`#!/usr/bin/env bash`, `export LC_ALL=C`),
  so the invocation needs no `env` wrapper;
- it **hardcodes the zypper path resolved at grant time** and refuses any first argument
  that is not the literal word `zypper` the engine's `system_txn_argv` builds, exiting 2
  without running anything. So the guard's authority is exactly "run this zypper as root",
  which the drop-in's first entry already grants — the wrapper adds no privilege;
- it carries `# oneup-auth-scope: <auth_cmnds output>` as a comment (§4.4).

Everything else is preserved verbatim from the current wrapper, because each line was paid
for: the stop-file staleness rule, `kill -TERM` on the zypper child only, and `wait` before
exit so no root child is left unreaped (the ONEUP-0041 shape, one level down).

**Where it lives.** `/usr/libexec/oneup-download-guard` where `/usr/libexec` exists —
openSUSE Tumbleweed adopted it in 2020, following FHS 3.0 — and `/usr/lib/…` otherwise, so
Leap 15.x still works. The path is one variable, `GUARD_FILE`, overridable as
`ONEUP_GUARD_FILE` so the suite never writes to a real system directory (`testing.md` §2).

**Grant installs it; revoke removes it; the pair is atomic.** `grant_auth` writes the guard
with `sudo install -o root -g root -m 0755` *before* the drop-in, and on failure writes no
drop-in at all — a rule granting a path that does not exist would be a rule that silently
never matches. `revoke_auth` removes both files in one `sudo rm -f`.

### 4.4 The guard file is also the drop-in's version stamp

The drop-in is `0440 root:root`, so the engine cannot read back what it granted. The guard
can be read by anyone, and is written by the same grant — so *"the installed guard is
byte-identical to what `download_guard_src` would emit now"* answers **"was this drop-in
written by an OneUp that grants what this run needs?"** without reading it.

The `# oneup-auth-scope:` comment is what makes that true rather than approximate: it
carries the whole `Cmnd` list, so a changed refresh budget, a moved binary, an added entry
or a new OneUp version all break the match.

```bash
auth_current() {          # the drop-in is live AND it grants what this engine needs
    local zypper
    zypper=$(command -v zypper) || return 1
    sudo -k -n "$zypper" --version >/dev/null 2>&1 || return 1
    [[ -r "$GUARD_FILE" ]] && [[ "$(<"$GUARD_FILE")" == "$(download_guard_src)" ]]
}
```

Both existing readers switch to it:

- **`sudo_init`** early-returns only when `auth_current` succeeds. A stale or absent
  drop-in now falls through to the ordinary path — one labelled prompt up front, plus the
  keep-alive — instead of skipping the bootstrap and meeting sudo's own bare prompt in the
  middle of step 1. **This is the safety net for the whole change**: whatever the drop-in
  turns out not to cover, the failure is one honest dialog at the start.
- **`auth_status`** emits `@@AUTH@@|on` only when `auth_current` succeeds. `security.md`
  §5.6 already requires the toggle to report what *is* rather than what was stored; this
  extends "is" from "a rule exists" to "the rule works", which is what the toggle claims.

### 4.5 What non-passwordless users run

`run_system_download` uses the guard when `auth_current` says it is current, and otherwise
runs **today's inline `sudo env LC_ALL=C bash -c` wrapper unchanged**. Users who never
granted passwordless have a warm credential from `sudo_init`, so that path costs them
nothing and is not new code. Both routes run the same script text and must behave
identically, which INV-8 pins.

### 4.6 The grant is slightly wider, and the dialog must still say so

Three entries are added to a rule the user consents to. Two are strictly narrower than what
is already granted (`timeout <budget> zypper *` and `du -sB1 /var/cache/zypp` can each do
less than the existing unrestricted `zypper` entry). The guard is equal to it, by §4.3's
construction. So the honest summary — *approximately passwordless root, because zypper can
install anything and a package can run code as root* — is unchanged, and
`_confirm_passwordless`'s wording stands as written. `security.md` §5.2's table gains the
three rows.

### 4.7 Automatic updates stand down whenever passwordless is off (ONEUP-0099)

`on_auth_toggled`'s off arm and `_on_auth_status_finished` need the same three steps, so
they get one helper rather than a second copy — `_stand_down_autoupdate`, holding the
existing removal, uncheck and message box verbatim.

`_on_auth_status_finished` calls it whenever the probe comes back off **and a timer is
actually enabled**. That condition is what keeps a failed *enable* quiet: during a pending
enable no timer has been installed yet, so `_autoupdate_enabled()` is false, the helper does
not run, and the existing "came back off" handling is untouched — no second dialog.

Because `_query_auth_status` already runs at startup, a rule removed behind OneUp's back is
caught the next time the app opens, not the next time someone opens Settings.

## 5. Correctness invariants

The engine suite is `tests/run-tests.sh` and the GUI suite is `tests/gui-smoke.py`.
Neither may call real `sudo` (`testing.md` §2.3), so every clause below asserts against the
mock-PATH sandbox — the real-sudo matching evidence is §4.2's measurement, recorded there
because no test may reproduce it.

- **INV-1** Every privileged command shape the engine issues in a run is granted by the
  drop-in it installs.
  *Test:* `--grant-auth` under a redirected `ONEUP_AUTH_FILE`, then the generated rule is
  asserted to contain each of: the resolved `zypper` path, `LC_ALL=C zypper *`, the refresh
  argv followed by ` *`, the cache `du` argv, and the guard path. Breaks the moment a
  granted shape is dropped, which is the defect this spec exists to close.

- **INV-2** No privileged call site escapes that list unnoticed.
  *Test (structural):* `grep -cE '\bsudo(_capture)? ' update_system.sh` returns a pinned
  count, with this invariant named beside it, so a **new** privileged call fails the suite
  until it is granted or explicitly recorded as interactive (grant/revoke's own
  `visudo`/`install`/`rm`). Breaks on exactly the way ONEUP-0092 was introduced: a call site
  added without a matching entry.

- **INV-3** The refresh grant and the refresh call cannot drift apart.
  *Test (structural):* `grep -c 'REFRESH_SUDO_ARGV' update_system.sh` returns **3** — one
  definition, one call site, one rule entry. Breaks if either side is respelled in place,
  which is how a pinned budget silently stops matching.

- **INV-4** The drop-in never grants a general-purpose binary with an unpinned command slot.
  *Test:* the generated rule is asserted **not** to match `timeout \*`, ` bash`, ` sh -c`,
  or an `env` entry whose assignment carries a wildcard; and the refresh entry is asserted to
  match `timeout [0-9]+ zypper \*` exactly. Breaks on the escalation shape §4.2 measured —
  `timeout * zypper *`, satisfiable by `timeout 5 /bin/sh -c 'zypper x'`.

- **INV-5** The guard runs zypper and nothing else.
  *Test:* the text `download_guard_src` emits is written to a scratch file and run directly
  with a first argument of `bash` — it exits **2**, and the mock records no invocation.
  Run again with `zypper`, it invokes the mock zypper with `--download-only` appended.
  Breaks if the guard ever executes `"$@"`, which would turn one sudoers entry into a root
  shell.

- **INV-6** A drop-in that does not cover this engine is treated as absent.
  *Test:* a scenario whose mock `sudo` models a live drop-in (the `-n` probe succeeds) but
  whose guard file holds different text — the engine performs the interactive
  `sudo -A … -v` bootstrap, which the mock records. Breaks on a currency check that trusts
  the zypper probe alone: the run would then meet sudo's own prompt mid-step-1, which is
  today's bug.

- **INV-7** `@@AUTH@@|on` means passwordless works, not that a file exists.
  *Test:* `--auth-status` three times — probe succeeds with a current guard → `on`; probe
  succeeds with a stale guard → `off`; probe fails → `off`. Breaks a toggle that reports a
  rule's existence rather than its sufficiency (`security.md` §5.6).

- **INV-8** The download behaves identically whichever wrapper carries it.
  *Test:* the ONEUP-0085 stop scenario is run twice — once with a current guard installed,
  once without — and both assert the same outcome: the step ends `stopped`, and the mock
  zypper received `--download-only`. Breaks if the guard drops the stop poll, silently
  removing Stop for the users who enabled passwordless.

- **INV-9** Granting is atomic: a guard that cannot be installed leaves no drop-in.
  *Test:* a mock `install` that fails for the guard path only — `ONEUP_AUTH_FILE` does not
  exist afterwards, `@@AUTH@@|on` is absent, and a `@@HINT@@` is emitted. Breaks on a grant
  that writes a rule pointing at a file that was never created.

- **INV-10** Revoking removes both files.
  *Test:* grant then revoke under redirected paths — neither `ONEUP_AUTH_FILE` nor
  `ONEUP_GUARD_FILE` exists, and `@@AUTH@@|off` is emitted. Breaks a revoke that leaves a
  root-owned executable behind after the user withdrew consent (`security.md` §5.5).

- **INV-11** An enabled weekly update never outlives the passwordless rule it needs.
  *Test (GUI):* with `_autoupdate_enabled` stubbed true, `_on_auth_status_finished` is fed
  output **without** `@@AUTH@@|on`; the test asserts `_remove_user_timer` was called with
  `oneup-update` and the toggle is unchecked. Breaks the ONEUP-0099 case exactly: a rule
  removed outside OneUp leaves a timer firing weekly into a dialog nobody answers.

- **INV-12** A failed *enable* does not trigger the stand-down.
  *Test (GUI):* with `_autoupdate_enabled` stubbed false and `_pending_autoupdate` set,
  the same off-reply asserts `_remove_user_timer` was **not** called and the toggle is
  unchecked once. Breaks a stand-down that fires on every off-reply, which would show a
  "turned off" dialog for a feature the user had just failed to turn on.

## 6. Failure modes

| Assumption | When it breaks | What happens |
| --- | --- | --- |
| `timeout` / `du` resolve at grant time | a stripped image lacking coreutils | the entry falls back to the bare name, never matches, and `auth_current` fails → one up-front labelled prompt (§4.4), never a mid-run one |
| The user's OneUp installed the live drop-in | upgrading OneUp with passwordless already on | the guard text no longer matches, so the toggle reads *off* and the timer stands down (INV-11); re-toggling grants the new scope. One visible, correctable state — not a silent half-grant |
| `/usr/libexec` exists | Leap 15.x | `GUARD_FILE` falls back to `/usr/lib`, and the rule is generated from the same variable |
| The guard survives as root-owned | someone chmods it writable | it stops matching only if its *content* changes; a writable guard is a machine already compromised at root level — the drop-in's `zypper` entry is the larger hole either way |
| `sudo` honours `secure_path` | a site that disabled it | the bare `zypper` word in two entries could resolve elsewhere. Pre-existing (`env LC_ALL=C zypper *` has always relied on it) and recorded in `security.md` §5.2 rather than newly introduced |

## 7. Tests

Engine scenarios in `tests/run-tests.sh`, beside the existing `--grant-auth` scenario that
already redirects `ONEUP_AUTH_FILE` and mocks `visudo`/`install`:

| Scenario | Invariants |
| --- | --- |
| the drop-in grants every shape the engine issues | INV-1, INV-4 |
| the guard refuses a non-zypper argv, and runs zypper with `--download-only` | INV-5 |
| a stale guard makes the engine authenticate up front | INV-6 |
| `--auth-status` across live/stale/absent | INV-7 |
| the ONEUP-0085 stop scenario, with and without a current guard | INV-8 |
| a failing guard install leaves no drop-in | INV-9 |
| revoke removes both files | INV-10 |
| structural greps | INV-2, INV-3 |

GUI scenarios in `tests/gui-smoke.py`, beside the existing auto-update coupling tests
(`cancel combined-enable installs no update timer`, and the stale-switch guard):

| Scenario | Invariants |
| --- | --- |
| an off auth reply stands an enabled update timer down | INV-11 |
| an off auth reply during a pending enable does not | INV-12 |

The mock `sudo` gains one capability it does not have today: it must model *which* argv
shapes are password-free, not merely whether the drop-in file exists. The existing
drop-in-aware mock (`tests/run-tests.sh`, the `--auth-status` scenario) is the pattern to
extend, and it stays a mock — `testing.md` §2.3 forbids real `sudo` unconditionally.

## 8. Docs & release

| Document | Change |
| --- | --- |
| `docs/standards/security.md` §5.2 | three rows: the refresh entry, the cache entry, the guard — with §4.2's reason the refresh entry pins its budget |
| `docs/standards/security.md` §5.6 | the probe is now `auth_current`, not the bare zypper probe; say what "on" means |
| `docs/standards/security.md` §5.5 | revocation removes the guard as well as the rule |
| `docs/standards/files-and-naming.md` | the paths table gains `GUARD_FILE` / `ONEUP_GUARD_FILE` |
| `CLAUDE.md` §6 | one trap: a privileged call added without a drop-in entry is invisible until a passwordless user meets it |
| `CHANGELOG.md` | an `### Fixed` entry under `[Unreleased]`, in the user's words |
| the six version sites | a 1.4.3 release via `./release.sh` — this is user-facing and `workflow.md` §1.1 says a qualifying fix ships |

## 9. Alternatives considered (and rejected)

- **Give `refresh_repos` a libzypp timeout instead of `sudo timeout`** — the roadmap
  research's own suggestion, and it would delete the escalation question rather than answer
  it. Rejected on three counts. `download.transfer_timeout` bounds **one transfer**, not the
  whole `zypper refresh <alias>` invocation, so a repository serving several files could take
  a multiple of the 120 s budget the engine promises. `timeout`'s exit 124 is what tells a
  slow server from a broken repository, and it is what raises the "gave up on '<alias>'" hint
  and the `skip-repo` remedy — ONEUP-0048's defences, with tests. And delivering it needs
  `sudo env ZYPP_CONF=… zypper`, whose sudoers pattern would carry a wildcard *before* the
  command name — the very shape §4.2 measured as exploitable.
- **Route the refresh through the guard too**, leaving no general-purpose binary in the rule
  at all. Genuinely tidier, and rejected as too large for the freeze: it rewrites the
  most-tested function in the engine and gives the guard a second mode, to remove a pattern
  §4.2 measured as safe.
- **Drop `sudo` from the cache `du`.** `/var/cache/zypp` is world-readable here and an
  unprivileged `du -sB1` returned a full total with no stderr (measured 2026-08-07) —
  which would need no sudoers entry at all. Rejected because `packages/` was **empty** at
  measurement time, so the claim is unproven exactly where the bytes live, and a `du` that
  hits one unreadable directory returns a partial total the step would report as freed
  space. A wrong number is worse than a granted `du`.
- **Ship the guard in the RPM** instead of installing it at grant time. It would not exist
  for AppImage or from-checkout users, which is most of them.
- **Pin the wrapper by writing the whole `bash -c` script into the sudoers entry.** The text
  is fixed, so in principle it pins. In practice it contains newlines, quotes and `[`/`*`,
  which are sudoers separators and fnmatch metacharacters; one character of drift would
  silently stop matching. Unmaintainable by the six-month test.
- **Leave the prompt and only make it up-front** (§4.4's fallback, as the whole fix).
  Rejected: it fixes the surprise but not the feature — the unattended run, which is the
  qualifying failure, still cannot complete.

## 10. Out of scope

- **The `--check` path.** It is rootless by design and prompts for nothing.
- **Weekly-check hardening.** ONEUP-0022's open question about `on_autocheck_toggled` not
  reverting its toggle on a failed install is untouched; the weekly *check* needs no
  passwordless rule.
- **Making `sudo_init` warm a credential when the drop-in is current.** It deliberately does
  not, and with §4.2 and §4.3 in place there is nothing left for a cached credential to
  cover.
- **ONEUP-0098's network guard** for the GUI suite — deferred separately, and its freeze
  question is the user's to answer.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Verified | Fixed | Notes |
| --- | --- | --- | --- | --- | --- |
