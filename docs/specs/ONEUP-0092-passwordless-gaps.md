# ONEUP-0092 — Passwordless actually runs without a password

**Status:** Reviewed
**Kind:** fix
**Roadmap:** ONEUP-0092
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

**ONEUP-0099 is implemented by §4.7 of this spec and has no spec of its own.** It is what
the prompt does to automatic updates, which cannot run at all while one appears — the same
mistake seen from the GUI side, so its one design question is answered in §4.7 and
`documentation.md` §2 says an item with no open design question gets a bullet, not a spec.
Its roadmap bullet points here. The header names one id because every sibling in
`docs/specs/` does and `documentation.md` §3's template is singular.

## 1. Goal

A user who turns *Passwordless* on sees no password box for the rest of a normal run —
**the four steps that elevate through sudo: system, Flatpak, orphans and cache** — and the
weekly automatic update, which exists only because passwordless does, completes unattended.
The firmware step is deliberately not in that list: it runs `fwupdmgr` with no `sudo` and
elevates through **polkit**, which a sudoers rule cannot speak to (§10). The engine already
draws this line — `needs_sudo` is computed over `system flatpak orphans cache`, above the
comment *"Firmware uses polkit for its own elevation"*. When the rule is missing,
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

Three call shapes, not the two ONEUP-0092 was filed against — the cache one runs twice:

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
  says nothing about it. **The argument is made per half, because §1.2 names "a misplaced
  dialog" as archetypal 2.0 work and §4.7 adds one.** The engine half qualifies because a
  passwordless run meets a prompt it was promised it would not. The ONEUP-0099 half
  qualifies on its own and not by association: an enabled weekly update whose rule has
  stopped working installs nothing, every week, silently. Its dialog is not new UI — it is
  the informational box the click path has always raised, on the other route that reaches
  the same state, differing only in its opening sentence (§4.7), and it exists precisely to
  end the silence §1.1 names.
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
by a user. So the two shapes this item adds get **one definition each, used by both the
call and the rule**, and the probe is replaced by one that cannot be satisfied by a subset.

**Be exact about how far that goes.** The five existing entries stay hand-written against
call sites elsewhere in the engine — moving them into `auth_cmnds` gives them one *home*,
not one definition, and they can still drift. INV-2 is their only guard, and it is a
count, so it catches a new call site rather than a changed one. The one-definition
treatment is affordable here because the refresh and cache argv are fixed strings; `zypper`
is granted with any arguments, so there is nothing to pin.

### 4.2 One definition per shape

Two new file-scope arrays, declared **after** `REFRESH_TIMEOUT` (the engine runs under
`set -uo pipefail`, so the expansion must follow the assignment):

```bash
# The refresh and the cache measurement both run under sudo, so the ONEUP-0023 drop-in
# must grant the EXACT argv each types or passwordless silently keeps prompting
# (ONEUP-0092). One definition each, used by the call site and by auth_cmnds, so the
# rule cannot drift from the call.
REFRESH_SUDO_ARGV=("$(command -v timeout)" "$REFRESH_TIMEOUT" zypper)
CACHE_DU_ARGV=("$(command -v du)" -sB1 /var/cache/zypp)
```

**No bare-name fallback**, and that is measured rather than stylistic: a `Cmnd` that is
not a fully-qualified path is a sudoers *parse error*, so a drop-in carrying one is
rejected whole. Run 2026-08-07 against `visudo -cf`, which `grant_auth` already uses:

```
Cmnd_Alias ONEUP_BARE = timeout 120 zypper *, /usr/bin/du -sB1 /var/cache/zypp
                        ^~~~~~~   expected a fully-qualified path name        (rc 1)
```

The same file with `/usr/bin/timeout` parses. So an unresolvable `timeout` or `du` must
make `build_auth_rule` **fail** — the existing "zypper was not found" arm of `grant_auth`
is the pattern — rather than emit a name that would take the whole rule down with it.

**Two mechanics that decide whether that refusal actually happens:**

- **`auth_cmnds`' non-zero status has to survive reaching `build_auth_rule`.** Declare and
  assign separately (`local joined; joined=$(auth_cmnds) || return 1`), never
  `local joined=$(auth_cmnds)` — in the combined form `local`'s own status wins and the
  failure is swallowed. Run 2026-08-07: the combined form reports `rc=0` against a failing
  substitution, the split form `rc=1`. `grant_auth`'s existing `if ! build_auth_rule >
  "$tmp"` then does the rest.
- **`REFRESH_TIMEOUT` is validated as `^[0-9]+$` inside `auth_cmnds`, before it is written
  into a `Cmnd`** — not "before it is used", which is not available: `REFRESH_SUDO_ARGV` is
  a file-scope assignment, so the value is consumed at load time on every invocation
  including `--check`. `auth_cmnds` returns 1 on a non-numeric budget, which reaches
  `build_auth_rule` by the split-assignment rule above, and the grant refuses with a hint of
  its own (§6) rather than the "zypper was not found" text, which would be actively wrong
  here. The budget comes from `${ONEUP_REFRESH_TIMEOUT:-120}`, so it is environment-supplied,
  and it lands in the one slot this section spends a paragraph proving is dangerous: `5 *`
  would generate `/usr/bin/timeout 5 * zypper *`, restoring the exact
  wildcard-before-the-command shape, and `visudo -cf` would accept it as syntactically fine.
  A malformed budget in a run that never grants is a *refresh* failure, not a security one,
  and §6 carries it.
- **`auth_cmnds` tests the arrays for emptiness, not `command -v` for status.** `timeout`
  and `du` are resolved at file scope, where a failure leaves an empty first element rather
  than a non-zero return — so the check is `[[ -n "${REFRESH_SUDO_ARGV[0]}" ]]` and its
  `CACHE_DU_ARGV` twin. The "zypper was not found" arm is the *shape* to copy, not the
  mechanism: that one can test `command -v` directly because it resolves inside the function.

At **run** time an unresolvable `timeout` is a different failure: the engine runs
`set -uo pipefail` without `-e`, so `REFRESH_SUDO_ARGV[0]` is the empty string and the
refresh fails outright. That is worse than a prompt and is not this item's to fix — it is
recorded in §6 so nobody reads the grant-time refusal as covering both.

**One difference this rewrite does introduce, stated rather than glossed:** `command -v`
resolves against the **user's** `PATH`, while the bare `timeout` the engine types today is
resolved by sudo under `secure_path`. So a `timeout` shadowed earlier on the user's path at
grant time would be both baked into the call and granted. `build_auth_rule` has always
resolved `zypper`, `snapper` and `flatpak` this way, so the property is not new — and it is
not an escalation *route*, because a user who can set their own `PATH` at grant time is the
same user the drop-in already grants unrestricted `zypper` to. It is recorded here because
§4.6 makes a per-entry argument and this is part of the honest version of it.

`refresh_repos` becomes `sudo "${REFRESH_SUDO_ARGV[@]}" --non-interactive "${gpg[@]}"
refresh "$alias"`; **both** cache call sites — before and after `zypper clean` — become
`sudo_capture CACHE_DU "${CACHE_DU_ARGV[@]}"`. Neither changes behaviour: the command is
the one that runs today, with `timeout` and `du` spelled as the absolute paths sudo
resolves them to anyway.

`auth_cmnds` (new) echoes the comma-joined `Cmnd` list and becomes the only place the
granted scope is written:

| Entry | Source |
| --- | --- |
| `<zypper>`, `<snapper>`, `<flatpak>`, `<systemctl> stop packagekit`, `<env> LC_ALL=C zypper *` | unchanged, moved out of `build_auth_rule` |
| `${REFRESH_SUDO_ARGV[*]} *` | the refresh call, verbatim, plus its arguments |
| `${CACHE_DU_ARGV[*]}` | the cache measurement, verbatim. No wildcard — the argv is fixed |
| `$GUARD_FILE` | §4.3. **No argument spec at all**, which in sudoers permits *any* arguments — required, because the transaction argv varies. The guard restricts itself (§4.3); the entry does not, and must not be pinned by analogy with the `du` row above |

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
what runs.

**The guard's argv, which is the contract an implementer builds against:**

| Position | Value | Notes |
| --- | --- | --- |
| `$1` | the stop file | `$STOP_FILE` |
| `$2` | the run-state file | `$RUN_STATE_FILE` |
| `$3` | the poll interval | `$STOP_POLL_SECONDS` |
| `$4` | the literal word `zypper` | validated; anything else exits **2**, running nothing |
| `$5…` | the rest of `${SYS_TXN[@]}` | `--non-interactive`, any `--reposd-dir`, `dup`/`update`, … |

`$1`–`$3` are deliberately unvalidated: they reach the guard only as operands of `-e`/`-nt`
tests and `sleep`, so a bad value makes the stop poll useless rather than dangerous. `$4` is
the only position that decides what gets executed, which is why it is the only one checked.

**Only the `sudo env LC_ALL=C bash -c '…' _` prefix is replaced. Everything downstream of
it stays**, so the call in full is:

```bash
sudo "$GUARD_FILE" "$STOP_FILE" "$RUN_STATE_FILE" "$STOP_POLL_SECONDS" "${SYS_TXN[@]}" 2>&1 \
    | tee "$SYS_LOG" | progress_filter system download
SYS_DL_RC=${PIPESTATUS[0]}
```

Written out because the tail is load-bearing three times over and an abbreviated call is
the one an implementer copies: `tee "$SYS_LOG"` is where a download failure's evidence
lives, which `SYS_LOG_FIRST` snapshots for ONEUP-0094's retry; `progress_filter` is
ONEUP-0040's defence against a long download looking like a hang; and `PIPESTATUS[0]` is
what ONEUP-0085 §4.4 discriminates rc 143 with — it says *"Keeping the pipeline in the
FOREGROUND is what preserves `PIPESTATUS[0]`"*.

The guard does `shift 4` before running `"$ZYPPER" "$@" --download-only`. **The `_`
placeholder is dropped**: it exists today only to fill `$0` for `bash -c`, and a script
file has its own `$0`. Getting this wrong is silent — the guard would read the *poll
interval* as its stop file and never see a stop — which is why the positions are tabulated
rather than described.

It differs from today's inline script in three ways, all of them the point:

- it pins the interpreter and the locale itself — `#!/bin/bash`, an absolute path for the
  same reason §4.2 pins the sudoers entries, and `export LC_ALL=C` — so the invocation
  needs no `env` wrapper. (Not `#!/usr/bin/env bash`, which is a `PATH` lookup: the
  opposite of pinning, however conventional it looks.)
- it **carries the zypper path resolved at grant time**, frozen into the file when it is
  written, and validates `$4` as above. So the guard's authority is exactly "run this
  zypper as root", which the drop-in's first entry already grants — the wrapper adds no
  privilege, which is the whole argument for granting it;
- it carries `# oneup-auth-scope: <auth_cmnds output>` as a comment (§4.4).

Everything else is preserved verbatim from the current wrapper, because each line was paid
for: the stop-file staleness rule, `kill -TERM` on the zypper child only, and `wait` before
exit so no root child is left unreaped (the ONEUP-0041 shape, one level down).

**Where it lives.** `/usr/libexec/oneup-download-guard` where `/usr/libexec` exists —
openSUSE Tumbleweed adopted it in 2020, following FHS 3.0 — and
`/usr/lib/oneup-download-guard` otherwise, so Leap 15.x still works. The path is one
variable, `GUARD_FILE`, overridable as `ONEUP_GUARD_FILE` so the suite never writes to a
real system directory (`testing.md` §2, and §7 for the default redirect that makes that
true by construction rather than by each scenario remembering).

**Where the new functions are defined.** `auth_cmnds`, `download_guard_src`,
`guard_current` and `auth_current` are declared **above the `AUTH_ACTION` dispatch** — the
`grant) grant_auth ;; revoke) revoke_auth ;; status) auth_status ;;` block, which is the
earliest thing that can call one and which sits *above* the `$needs_sudo && sudo_init`
bootstrap, not below it. The engine already carries this trap in a comment of its own: a
dispatch that runs and exits partway down the file has never executed anything defined
after it, so placing these beside `sudo_init` would leave `--auth-status`, `--grant-auth`
and `--revoke-auth` dying on "command not found" — the three actions this spec's own
invariants exercise most.

**Grant installs it; revoke removes it; and the order is fixed** because two of the three
steps can fail:

1. `visudo -cf` validates the generated rule in isolation — unchanged, and it stays
   **first**, so a malformed rule costs nothing;
2. `sudo install -o root -g root -m 0755` writes the guard, from a second `mktemp` file
   `download_guard_src` was written to — the drop-in already works this way, and both temp
   files are removed on every exit arm;
3. `sudo install -o root -g root -m 0440` writes the drop-in.

**Any failure at 2 or 3 removes the guard again.** Validating first is what keeps step 2
from stranding a root-owned executable behind a rule that was never going to install, and
the explicit removal at 3 covers the rest. The stranding matters more than it looks:
afterwards the toggle reads off, which makes `on_auth_toggled`'s revoke arm unreachable —
the user has consented to a root-owned file they can no longer withdraw through the UI.

`revoke_auth` removes the drop-in and **both** candidate guard paths in one `sudo rm -f`.
Both, not just today's: `GUARD_FILE` is recomputed per run from a directory test, so a
`/usr/libexec` created by some other package after the grant would move it and leave the
`/usr/lib` copy beyond the reach of a revoke. **When `ONEUP_GUARD_FILE` is set the two-path
removal collapses to that one path** — the override exists so the suite never touches a real
system directory, and a revoke that reached past it would defeat that.

**Editing the guard's text is a re-grant for every existing user**, and that is worth
knowing before touching it. §4.4 compares the whole text (trailing newlines aside — command
substitution strips those on both sides), so a whitespace or
comment change to `download_guard_src` invalidates every live grant: those users' toggles
read off, their weekly updates stand down (§4.7), and they must switch passwordless on
again. Correct — the file on disk really is no longer the one this engine expects — but it
means the guard text is not a place for cosmetic edits. §8 files it as a `CLAUDE.md` trap.

### 4.4 The guard file is also the drop-in's version stamp

The drop-in is `0440 root:root`, so the engine cannot read back what it granted. The guard
can be read by anyone, and both files are written by the same grant — so *"the installed
guard is byte-identical to what `download_guard_src` would emit now"* is evidence about
the drop-in beside it.

**State the claim exactly, because it is an inference and not a reading.** A matching
guard means: *this file was written by an OneUp whose `auth_cmnds` output, on this machine
as it is configured right now, is the same as this engine's.* The `# oneup-auth-scope:`
comment is what carries the second half — the whole `Cmnd` list, so a changed refresh
budget, a moved binary, an added entry or a new OneUp version all break the match.

Two things it is **not**, both of which §6 now carries as rows rather than leaving to be
discovered:

- It is not proof that sudo *matches* those entries. `visudo -cf` (§5.4) is what catches a
  malformed rule, at grant time, and §4.2's no-bare-name rule is what keeps an unmatchable
  entry from being generated in the first place.
- It cannot see a drop-in **replaced** after the guard was written — by an older OneUp,
  which §6 carries as a row. A knowing blind spot, not an oversight: closing it needs the
  drop-in itself to be readable, which its `0440` mode exists to prevent.

Two functions, because the two readers need different halves:

```bash
guard_current() {         # pure file comparison — no sudo, safe to call mid-run
    [[ -r "$GUARD_FILE" ]] && [[ "$(<"$GUARD_FILE")" == "$(download_guard_src)" ]]
}

auth_current() {          # the drop-in is live AND it grants what this engine needs
    local zypper
    zypper=$(command -v zypper) || return 1
    sudo -k -n "$zypper" --version >/dev/null 2>&1 || return 1
    guard_current
}
```

`sudo -k` here is the existing `auth_status` idiom and is safe to issue at any point in a
run: measured 2026-08-07, a warm credential survives it. `sudo -A -v` to warm, `sudo -n
true` → ok, `sudo -k -n true` → fails as designed, `sudo -n true` again → **still ok**. So
`-k` suppresses the cache for its own invocation without invalidating it, which is what
lets `auth_status` report real state without costing the next call a prompt.

Both existing readers switch to `auth_current`:

- **`sudo_init`** early-returns only when `auth_current` succeeds. A stale or absent
  drop-in now falls through to the ordinary path — one labelled prompt up front, plus the
  keep-alive — instead of skipping the bootstrap and meeting sudo's own bare prompt in the
  middle of step 1. **This is the safety net for the whole change**: whatever the drop-in
  turns out not to cover, the failure is one honest dialog at the start.
- **`auth_status`** emits `@@AUTH@@|on` only when `auth_current` succeeds. `security.md`
  §5.6 already requires the toggle to report what *is* rather than what was stored; this
  extends "is" from "a rule exists" to "the rule works", which is what the toggle claims.

**Both readers' claims — `sudo_init`'s and `auth_status`'s — are scoped to an ordinary
run.** `grant_auth` and `revoke_auth` issue `sudo
visudo`, `sudo install` and `sudo rm`, none of which the drop-in grants and none of which
it should — changing the authorization rule is exactly the act that ought to cost a
password. So "no prompt" means the four sudo-elevating steps of §1, never the settings
actions — and never firmware's own polkit dialog (§10).

### 4.5 When the download uses the guard, and when it does not

`run_system_download` uses the guard when **`guard_current`** says it is current, and
otherwise runs **today's inline `sudo env LC_ALL=C bash -c` wrapper unchanged**. It asks
`guard_current`, not `auth_current`: the only question at that point is whether the file on
disk is the script this engine expects, and the drop-in probe would add a `sudo` call in
the middle of a run for an answer nothing there uses. Users who never
granted passwordless have a warm credential from `sudo_init`, so that path costs them
nothing and is not new code.

**The two routes are two texts implementing one contract, not one text run two ways** —
which is why the fallback is left byte-for-byte alone rather than regenerated from
`download_guard_src`. They differ exactly as §4.3 lists: the guard pins its own interpreter
and locale, carries a frozen zypper path, validates `$4`, and shifts 4 where the inline
script shifts 3. Feeding one's text into the other's invocation would misalign every
position — the silent failure §4.3 tabulates positions to prevent. `download_guard_src` is
the single source **of the guard file**; INV-8 is what holds the two routes to the same
observable behaviour.

### 4.6 The grant is slightly wider, and the dialog must still say so

Three entries are added to a rule the user consents to, and the argument has to be made per
entry rather than in a sentence:

- **`timeout <budget> zypper *`** grants no more than the existing unrestricted
  `zypper` entry — the same binary, reachable only under a fixed time limit.
- **`$GUARD_FILE`** is equal to it, by §4.3's construction: the guard can run that zypper
  and nothing else.
- **`du -sB1 /var/cache/zypp`** is genuinely new — `du` is a different binary, not a subset
  of anything already granted. It is read-only, takes no sub-command, and its argv is
  pinned whole, so what it adds is "may measure one directory as root".

So the honest summary — *approximately passwordless root, because zypper can install
anything and a package can run code as root* — is unchanged, and `_confirm_passwordless`'s
wording stands as written rather than being softened (`security.md` §5.3). §5.2's table
gains the three rows.

### 4.7 Automatic updates stand down whenever passwordless is off (ONEUP-0099)

`on_auth_toggled`'s off arm and `_on_auth_status_finished` need the same steps, so they get
one helper rather than a second copy — `_stand_down_autoupdate`, holding the existing
`if self._autoupdate_enabled():` guard, the `_remove_user_timer("oneup-update")` call, the
uncheck and the message box verbatim. The `self._pending_autoupdate = False` line stays at
the `on_auth_toggled` call site: it is about a revoke racing an enable, not about standing
the timer down, and `_on_auth_status_finished` already consumes that latch itself.

**Standing down requires an explicit `@@AUTH@@|off`, not merely a missing
`@@AUTH@@|on`.** Today `_on_auth_status_finished` decides with `is_on = "@@AUTH@@|on" in
out`, so *every* way the probe can fail to say anything — the engine crashing, `bash`
missing, the `QProcess` killed, output truncated — reads as "off". That is currently
harmless, because the only consequence is a toggle reflect that the next probe corrects.
§4.7 makes the consequence destructive: it would delete the user's weekly timer and raise a
dialog because a subprocess did not start. `auth_status` always emits one marker or the
other, so the off case is positively identifiable and must be identified positively. The
toggle reflect keeps its existing rule — a probe that says nothing still shows *off*, which
is the safe reading for a switch — and only the stand-down demands the explicit marker.

The helper is then called **before** the existing `if self._pending_autoupdate:` block, and
only when no enable is in flight.

**That second condition lives at the `_on_auth_status_finished` call site, never inside the
helper**, and the distinction is the difference between a fix and a regression. The helper
is shared with `on_auth_toggled`'s off arm, which stands the timer down *regardless* of the
latch and clears it afterwards. Move the check inside and that click path inherits it: a
user who toggles automatic updates on and then, while the probe is still in flight, toggles
Passwordless off would keep an enabled weekly timer across a revoke — exactly the coupling
§2.5 describes as already correct, silently broken by a fix aimed elsewhere. So the helper
stays the three existing statements behind their existing `_autoupdate_enabled()` guard,
and the call site reads `if not is_on and not self._pending_autoupdate:`.

The latch condition is needed on the discovery path because `_autoupdate_enabled()` shells
out to `systemctl --user is-enabled` and so reports the machine, not the toggle: a timer
enabled outside OneUp, or a stale reflect, would make it true *during* a pending enable, and
the user's attempt to switch automatic updates **on** would answer with a box saying they
had been switched off.

**The box needs its own opening line on this path.** The click path says *"Automatic weekly
updates were switched off because they need the passwordless setting to run unattended."*
— true when the user just clicked Passwordless off, and false on the commonest discovery
trigger, which is an upgraded OneUp whose rule is merely no longer current (§6). Same box,
same explanation of the coupling, different first sentence: *"OneUp's passwordless rule is
no longer active, so automatic weekly updates have been switched off."* `_confirm_passwordless`'s
`lead` parameter is the pattern — one box, a caller-specific opening (`wording-and-translation.md`).

Because `_query_auth_status` already runs in `Updater.__init__`, a rule removed behind
OneUp's back is caught the next time the app opens, not the next time someone opens
Settings. **That means the box can appear at launch**, which is intended — the user's
weekly update has stopped working and nothing else would say so — but it is a modal at
startup, so it must be the same informational box the click path shows and no more. It is
also why INV-11 to INV-13 stub it, and why §7 neutralises it suite-wide:
`QMessageBox.information` blocks.

## 5. Correctness invariants

The engine suite is `tests/run-tests.sh` and the GUI suite is `tests/gui-smoke.py`.
Neither may call real `sudo` (`testing.md` §2.3), so the engine clauses below assert
against the mock-PATH sandbox and the GUI clauses against stubs — the real-sudo matching
evidence is §4.2's measurement, recorded there because no test may reproduce it.

- **INV-1** Every privileged command shape the engine issues in a run is granted by the
  drop-in it installs.
  *Test:* `--grant-auth` under a redirected `ONEUP_AUTH_FILE`, then the generated rule is
  asserted to contain each of these, for the shapes the mock PATH provides:
  the resolved `zypper` path, `LC_ALL=C zypper *`, `stop packagekit`, the refresh argv
  followed by ` *`, the cache `du` argv, and the guard path — plus `snapper` and `flatpak`
  when the scenario's mock directory carries them, since `auth_cmnds` skips an absent
  optional binary by design. Breaks the moment a granted shape is dropped, which is the
  defect this spec exists to close.

- **INV-2** No privileged call site escapes that list unnoticed.
  *Test (structural):* `grep -cE '^[[:space:]]*(sudo|sudo_capture) ' update_system.sh`
  returns the count the scenario pins, with this invariant named beside it, so a
  **new** privileged call fails the suite until it is granted or explicitly recorded as
  interactive (grant/revoke's own `visudo`/`install`/`rm`). Breaks on exactly the way
  ONEUP-0092 was introduced: a call site added without a matching entry.
  **Anchored to command position on purpose.** The obvious pattern, `grep -cE
  '\bsudo(_capture)? '`, returns **70** on `9fe90e9` against **26** at command position,
  because the engine discusses sudo constantly in comments — 28 of the 70 matching lines
  are comments. A count dominated by prose fails when a comment is reworded, which teaches
  the next person to bump the number rather than read it. Two things the anchored form
  still cannot see, stated so nobody reads it as complete: a `sudo` inside a pipeline or
  substitution, and two calls on one line (`grep -c` counts lines).

- **INV-3** A granted argv and the call that types it cannot drift apart.
  *Test (structural):* counted with comment lines stripped, for the reason INV-2 gives —
`grep -vE '^[[:space:]]*#' update_system.sh | grep -c '<array>'` for each of the two
  arrays returns the count the scenario pins. The numbers live in the test, which fails when
  they move, and **not also here** — a spec that restates a figure the test owns has two
  copies of it and only one gate (`documentation.md` §6b.3). What the reader needs is the
  shape: each array is written once and read by its call site, by the rule that grants it,
  and by `auth_cmnds`' validation, so a respelling on either side cannot drift unnoticed —
  and the cache array has *two* call sites, before and after `zypper clean`, which is what
  catches only one of them being converted. Breaks if either side is respelled in place, which is how a pinned budget
  silently stops matching, and the `du` count is what catches only one of the two cache
  sites being converted. Without the strip these counts would fail on a reworded comment,
  which is the failure INV-2 exists to name.

- **INV-4** The drop-in never grants a general-purpose binary with an unpinned command slot.
  *Test:* the generated rule is asserted **not** to match `timeout \*`, ` bash`, ` sh -c`,
  or an `env` entry whose assignment carries a wildcard; and the refresh entry is asserted
  to match `timeout [0-9]+ zypper \*` exactly. A second scenario grants with
  `ONEUP_REFRESH_TIMEOUT='5 *'` and asserts **no** drop-in is written and a `@@HINT@@` is
  emitted — the budget reaches that slot from the environment, so a shape assertion made
  only against a well-formed run would never see it. Breaks on the escalation shape §4.2
  measured, from either direction.

- **INV-5** The guard runs zypper and nothing else.
  *Test:* the text `download_guard_src` emits is written to a scratch file, made
  executable, and run with the **real argv of §4.3** — `<guard> "$stop" "$state" 1 bash -c
  id` — where `$4` is `bash` rather than `zypper`. It exits **2** and the mock records no
  invocation. Run again as `<guard> "$stop" "$state" 1 zypper --non-interactive dup`, it
  invokes zypper with `--download-only` appended and **exits with that child's status**. A
  third run touches the stop file after launch, against a mock zypper that sleeps: the child
  receives `SIGTERM`, the guard reaps it and **leaves no live process behind**. The third
  run is what makes the claim honest — the first two never create a stop file, so
  `kill -TERM` is never reached and a clause resting on them would assert coverage its
  fixture cannot produce. These are the `wait`-before-exit and signal-the-child-only halves
  of §4.3's preserved list, the rules with the most scar tissue on them
  (`security.md` §2.4). Breaks if the guard ever
  executes `"$@"` unvalidated, which would turn one sudoers entry into a root shell.

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
  once without — and both assert the same outcome: the system step ends `skip` with
  `stopped before installing anything`, `@@DONE@@|stopped` is emitted, and the mock zypper
  received `--download-only`. (`skip` is the *step* outcome ONEUP-0085 §4.4's table maps rc
  143 to; `stopped` is the run value.) Breaks if the guard drops the stop poll, silently
  removing Stop for the users who enabled passwordless.

- **INV-9** Either install failure leaves neither file.
  *Test:* two scenarios, each starting from **no existing drop-in and no existing guard**,
  so that "absent afterwards" means this grant wrote nothing rather than that a previous
  one survived. (a) A mock `install` that fails for the guard path — `ONEUP_AUTH_FILE` and
  `ONEUP_GUARD_FILE` are both absent, `@@AUTH@@|on` is absent, a `@@HINT@@` is emitted.
  (b) A mock `install` that fails for the drop-in path only — **both** are absent again,
  which is the half INV-9 gained after review: a stranded root-owned guard cannot be
  revoked through the UI, because the toggle reads off and the revoke arm is unreachable.

- **INV-10** Revoking removes both files.
  *Test:* grant then revoke under redirected paths — neither `ONEUP_AUTH_FILE` nor
  `ONEUP_GUARD_FILE` exists, and `@@AUTH@@|off` is emitted. Breaks a revoke that leaves a
  root-owned executable behind after the user withdrew consent (`security.md` §5.5).

- **INV-11** An enabled weekly update never outlives the passwordless rule it needs.
  *Test (GUI):* with `_autoupdate_enabled` stubbed true, `_remove_user_timer` spied and
  the informational box stubbed, `_on_auth_status_finished` is fed output carrying
  `@@AUTH@@|off`; the test asserts `_remove_user_timer` was called with `oneup-update` and
  the toggle is unchecked. Both stubs are required, not tidiness: the real
  `_remove_user_timer` shells out to `systemctl --user disable --now` and would disable the
  developer's own timer (`testing.md` §2), and `QMessageBox.information` blocks. Breaks the
  ONEUP-0099 case exactly: a rule removed outside OneUp leaves a timer firing weekly into a
  dialog nobody answers.

- **INV-12** A failed *enable* does not trigger the stand-down.
  *Test (GUI):* two scenarios, because the guard has two halves and one fixture cannot
  exercise both. (a) `_autoupdate_enabled` stubbed **false** with `_pending_autoupdate`
  set — the ordinary failed enable. (b) `_autoupdate_enabled` stubbed **true** with
  `_pending_autoupdate` set — a timer the toggle did not know about, which is the half a
  false-only fixture leaves untested and the one that would answer an *enable* with a
  "turned off" dialog. Both assert `_remove_user_timer` was not called, no box was raised,
  and `_set_autoupdate_checked` (spied) was called exactly once, with `False`.

- **INV-13** A probe that failed to run never stands the timer down.
  *Test (GUI):* `_on_auth_status_finished` is fed empty output — the shape a crashed or
  killed engine produces — with `_autoupdate_enabled` stubbed true. `_remove_user_timer`
  is **not** called and no box is raised, while the toggle still reflects off. Breaks the
  `"@@AUTH@@|on" in out` reading of "off", which would delete a working weekly update
  because a subprocess failed to start.

## 6. Failure modes

| Assumption | When it breaks | What happens |
| --- | --- | --- |
| `timeout` / `du` resolve at grant time | a stripped image lacking coreutils | **the grant refuses** — `build_auth_rule` fails rather than emitting a bare name, because `visudo -cf` rejects a non-absolute `Cmnd` and would take the whole rule down (§4.2, measured). The user gets a `@@HINT@@`, in the shape of the existing "zypper was not found, so passwordless authorization can't be set up." Separately, a machine with no `timeout` cannot refresh at all, which is a bigger failure than a prompt |
| The user's OneUp installed the live drop-in | upgrading OneUp with passwordless already on | the guard text no longer matches, so the toggle reads *off* and the timer stands down (INV-11); re-toggling grants the new scope. One visible, correctable state — not a silent half-grant |
| …and no *older* OneUp re-granted since | an AppImage or checkout of 1.4.2 runs `--grant-auth` after this version did | the drop-in is narrowed back to five entries while this guard stays on disk, so `auth_current` wrongly returns true and the mid-run prompt returns. §4.4 states this blind spot; the symptom is exactly today's bug, and re-toggling on the newer build fixes it |
| The granted scope reflects the machine at run time | `snapper` or `flatpak` is installed or removed after granting | `auth_cmnds` skips absent optional binaries, so the `# oneup-auth-scope:` line changes and the stamp stops matching. Installing one *should* re-grant (there is a new shape to cover); **removing** one is a false negative — nothing became uncovered, yet the toggle flips off and the timer stands down. Correctable by re-toggling, and it fails safe |
| `REFRESH_TIMEOUT` is the same at grant and at run | a user or scenario sets `ONEUP_REFRESH_TIMEOUT` (`files-and-naming.md` §5.1) | the budget is pinned literally into the rule, so the two disagree — and the scope comment catches it: the stamp mismatches, `auth_current` fails, and the run takes the one-labelled-prompt path instead of prompting per repository. The override is documented in `files-and-naming.md` §5.1 with no test-only marking, so a user who exports it gets passwordless permanently reading off — the labelled prompt is what keeps that from being silent, and this mismatch is why the budget is in the stamp |
| `timeout` resolves at **run** time | the same stripped image, after a grant made elsewhere | different failure from the row above: `set -uo pipefail` carries no `-e`, so `REFRESH_SUDO_ARGV[0]` is empty and the refresh fails outright rather than prompting. Named so the grant-time refusal is not read as covering both |
| `REFRESH_TIMEOUT` is numeric | `ONEUP_REFRESH_TIMEOUT` is set to something else | at **grant** time `auth_cmnds` refuses and the drop-in is not written, with a hint naming the budget — not the "zypper was not found" text, which would be wrong here. In a run that never grants it is a *refresh* failure, not a security one: `sudo /usr/bin/timeout '5 *' zypper …` simply fails |
| The guard is still current when the download starts | it is revoked from a second window, or replaced by a package upgrade, between `sudo_init` and the download pass | `guard_current` goes false mid-run and the fallback wrapper runs — but `sudo_init` already early-returned, so there is no warm credential and no keep-alive, and the user meets one askpass dialog mid-download. Accepted: the window is seconds wide, it needs a concurrent revoke, and the alternative is warming a credential on every passwordless run to insure against it |
| The guard's users are the drop-in's users | a second account on the same machine grants or revokes | the drop-in is per-user (`$user ALL=(root) NOPASSWD:`) but the guard is one machine-wide file, so user B's revoke deletes the guard user A's grant relies on. A degrades to the fallback wrapper and their toggle reads off, for a cause invisible from A's session. Correctable by re-toggling; recorded because nothing in the UI explains it |
| Removing a half-installed guard succeeds | the `sudo rm` in grant's failure arm itself fails | the stranded root-owned executable §4.3 warns about survives, and the hint says the grant failed. Rare (it needs a working `sudo install` and a failing `sudo rm`) and it fails loudly rather than silently, but it is the one path §4.3's atomicity claim cannot cover |
| The probe process ran at all | the engine crashes, is killed, or emits nothing | the toggle reflects *off* (unchanged, and the safe reading for a switch) but the timer is **not** stood down — INV-13. Without that split, a subprocess that failed to start would delete a working weekly update |
| `/usr/libexec` exists | Leap 15.x | `GUARD_FILE` falls back to `/usr/lib/oneup-download-guard`, and the rule is generated from the same variable |
| …and does not appear later | some other package creates `/usr/libexec` after the grant | `GUARD_FILE` is recomputed per run, so it moves: `guard_current` reads a path that never existed and the toggle flips off. Revoke removes **both** candidate paths (§4.3) so the older one cannot be stranded |
| `PATH` is the same at grant and at run | the grant runs from the desktop-launched GUI and the run from a terminal, with different `PATH`s | `command -v` could resolve a binary differently, changing the `# oneup-auth-scope:` line and mismatching the stamp. Fails safe — one labelled prompt, and re-toggling re-grants — but it is a false negative with no user-visible cause, which is why §4.2 records the resolution difference |
| The guard survives as root-owned | someone chmods it writable | it stops matching only if its *content* changes; a writable guard is a machine already compromised at root level — the drop-in's `zypper` entry is the larger hole either way |
| `_remove_user_timer` succeeds | no user bus, or `systemctl --user disable` fails | `_autoupdate_enabled()` stays true, so the box re-appears on the probe that follows, and on each later one — visible and repeating rather than silent. Not made worse than the existing click path, which has always had this shape |
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
| an explicit `@@AUTH@@|off` stands an enabled update timer down | INV-11 |
| an off reply during a pending enable does not, with or without a timer present | INV-12 |
| a probe that emitted nothing does not | INV-13 |

**The GUI suite needs a module-wide neutralisation, for the same reason and in the same
place as the network stub.** `Updater.__init__` calls `_query_auth_status`, and
`tests/gui-smoke.py` constructs the window 56 times — so once §4.7 lands, any of those
probes can reach `_stand_down_autoupdate` and the real `_remove_user_timer`, which shells
out to `systemctl --user disable --now` against the developer's own session. `main()`
already replaces `Updater._check_app_update` with a no-op before its first
`updater.Updater()` (`tests/gui-smoke.py`, the ONEUP-0090 stub); `_stand_down_autoupdate`
gets the same treatment there, and INV-11 to INV-13 re-enable it locally with a spy. Two
of 56 constructions being careful is not the same property.

The mock `sudo` gains one capability it does not have today: it must model *which* argv
shapes are password-free, not merely whether the drop-in file exists. The existing
drop-in-aware mock (`tests/run-tests.sh`, the `--auth-status` scenario) is the pattern to
extend, and it stays a mock — `testing.md` §2.3 forbids real `sudo` unconditionally.

**One mechanism, named once, for how a scenario gets the guard text.** INV-5 to INV-8 all
need it, and `download_guard_src` is an internal function with no entry point: the engine
gains a hidden `--emit-guard` action that writes it to stdout. Routing through
`--grant-auth` instead would not work — those scenarios mock `install`, so no guard file is
produced.

**The emit must run under the same environment as the run that will read it, and this is
the trap in the whole test design.** The emitted text embeds `# oneup-auth-scope:
<auth_cmnds output>`, which contains `$GUARD_FILE`, the resolved binary paths and
`$REFRESH_TIMEOUT` — so a `--emit-guard` invoked with different values produces text that
can never match, and `guard_current` silently returns false. Every "with a current guard"
clause would then pass through the *stale* branch and assert nothing it claims to. So the
emit is invoked with the same `ONEUP_GUARD_FILE`, the same `PATH` (mock directory first, so
the frozen zypper path is the mock's) and the same `ONEUP_REFRESH_TIMEOUT` as the
`run_engine` call that follows — and the "current guard" scenarios assert positively that
the guard branch was taken, rather than inferring it from an outcome the fallback would
also produce.

Two details that make that reproducible. `run_engine` **prefixes** `PATH`
(`PATH="$mockdir:$PATH"`), so the real `/usr/bin/timeout` and `/usr/bin/du` stay reachable
and the grant scenarios resolve them — `auth_cmnds` requires both (§4.2), so a mock
directory that *replaced* `PATH` would make every grant refuse. And **two existing scenarios
already set `ONEUP_REFRESH_TIMEOUT=1`** (ONEUP-0048's slow-mirror pair); they never grant,
so the budget in the scope stamp does not reach them.

**`run_engine` gains a fourth default redirect, `ONEUP_GUARD_FILE`**, alongside the three
`testing.md` §2.1 pins. This is not optional tidiness: `guard_current` **reads**
`GUARD_FILE` on every run that reaches the download pass, so without a default the suite's
result depends on whether the developer's own machine happens to have OneUp granted — the
`/run/zypp.pid` bite `testing.md` §2 exists to prevent, in a new place. A scenario that
invokes the engine outside `run_engine` repeats it by hand, like the other three.

## 8. Docs & release

| Document | Change |
| --- | --- |
| `docs/standards/security.md` §2.1 | the early return is now conditioned on `auth_current`, so "**Zero** prompts, and no keep-alive at all, when §5's passwordless drop-in is active" becomes true only of a *current* drop-in — a stale one takes the prompt-plus-keep-alive path on purpose |
| `docs/standards/security.md` §5.2 | three rows: the refresh entry, the cache entry, the guard — with §4.2's reason the refresh entry pins its budget, and the guard row's "no argument spec" note |
| `docs/standards/security.md` §5.4 | "validate before installing" now describes an ordered pair — guard first, drop-in second, and neither survives the other's failure |
| `docs/standards/security.md` §5.5 | revocation removes the guard as well as the rule |
| `docs/standards/security.md` §5.6 | the probe is now `auth_current`, not the bare zypper probe; say what "on" means, and that `sudo -k` does not invalidate a warm credential (§4.4, measured) |
| `docs/standards/testing.md` §2.1 | the redirect list becomes four — `ONEUP_GUARD_FILE` joins it, and the heading itself reads "The three redirects", so it is renamed rather than only extended |
| `docs/standards/testing.md` §2.3 | the throwaway-directory claim, which this spec's new scenarios change — rewritten as the sweep (create/remove must agree) rather than a total, per `documentation.md` §6b.2, since the figure there had already gone stale |
| `docs/standards/files-and-naming.md` | the paths table gains `GUARD_FILE` / `ONEUP_GUARD_FILE`, with both defaults spelled out |
| `security.md` and `testing.md` **`What checks this`** | a row per new rule, naming the INV that catches it — the revoke removing the guard, the ordered install, "on" meaning `auth_current`, the fourth redirect. `documentation.md` §4 requires the section and `tests/docs-check.py` gates its presence; a new rule with no row is the shape it exists to prevent |
| `ROADMAP.md` | ONEUP-0092 and ONEUP-0099 both flip to shipped |
| `CLAUDE.md` §2 | the `--emit-guard` action, alongside the other engine invocations listed there — a hidden action nothing documents is one the next person re-invents |
| `docs/standards/wording-and-translation.md` | nothing normative changes, but the stand-down box gains a second opening line (§4.7) — both strings are user-facing and translatable, and the standard is where that obligation lives |
| `README.md` | the two passages naming the Passwordless setting: automatic updates now switch themselves off when it stops working |
| `CLAUDE.md` §6 | two traps: a privileged call added without a drop-in entry is invisible until a passwordless user meets it; and editing the guard text is a re-grant for every existing user (§4.3) |
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

- **The firmware step, and polkit generally.** `fwupdmgr` is invoked with no `sudo` and
  elevates through polkit, which no sudoers rule can suppress — the engine excludes
  firmware from `needs_sudo` for exactly this reason. A firmware update may therefore still
  raise its own authentication dialog with passwordless on, and unattended runs that select
  firmware inherit that. Making polkit passwordless is a different mechanism, a different
  consent conversation, and not this item.
- **The `--check` path.** It is rootless by design and prompts for nothing.
- **Weekly-check hardening.** ONEUP-0022's open question about `on_autocheck_toggled` not
  reverting its toggle on a failed install is untouched; the weekly *check* needs no
  passwordless rule.
- **Making `sudo_init` warm a credential when the drop-in is current.** It deliberately does
  not, and with §4.2 and §4.3 in place there is nothing left in an ordinary run for a
  cached credential to cover. `--grant-auth` and `--revoke-auth` still authenticate, by
  design (§4.4).
- **ONEUP-0098's network guard** for the GUI suite — deferred separately, and its freeze
  question is the user's to answer.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Verified | Fixed | Notes |
| --- | --- | --- | --- | --- | --- |
| impl | 2026-08-07 | 2 (both MEDIUM) | 2 | 2 | **No reviewer dispatched — this row records what building the spec found, not a review loop.** INV-3's clause pinned `REFRESH_SUDO_ARGV` at 3 and `CACHE_DU_ARGV` at 4; a conforming implementation returns **5 and 5**, because the validation §4.2 requires (`auth_cmnds` testing both arrays for emptiness, and the budget for digits) is itself a reference to each array that the clause had not counted. INV-2's count was left unpinned by design. Both clauses now name the command and leave the number to the test that fails when it moves, rather than carrying a second copy the suite cannot gate (`documentation.md` §6b.3) — a change the user asked for on the same day, after the stale directory count in `testing.md` surfaced. No design decision moved, so §9 is untouched |
| 3 | 2026-08-07 | 26 (CRITICAL 1 · HIGH 6 · MEDIUM 11 · LOW 8) | 24 | 24 | 3 lanes, briefed cold. Dimensions: 5×8, 10×6, 4×5, 2×3, 6×3, 15×3. **Collateral-dominated, which is why the run stops here** (`/cold-eyes` loop economics): all three lanes independently found the same CRITICAL, and it was loop 2's own fix — §4.7 gained "and no enable is in flight" beside a sentence saying the helper holds the click path's statements verbatim, and the in-helper reading would have made a revoke racing an enable leave the weekly timer standing. The `--emit-guard` mechanism loop 2 introduced had the same shape of defect: it never pinned `ONEUP_GUARD_FILE`, so every "current guard" clause would have passed through the stale branch. Verified by opening the tree: the `AUTH_ACTION` dispatch sits **above** the `sudo_init` bootstrap (so loop 2's function-placement sentence was wrong), and `run_engine` **prefixes** `PATH` (so grant scenarios do resolve the real `timeout`/`du`). Dismissed with evidence: `release_zypper_lock` types `systemctl stop packagekit`, matching the drop-in exactly — no fourth uncovered shape; and the `Branch:` header's parenthetical follows sibling ONEUP-0094 rather than breaching the template. Deferred: INFO only — no anchor list on an 800-line doc. A fourth cold pass over loop 3's own fixes was not run |
| 2 | 2026-08-07 | 34 (CRITICAL 2 · HIGH 8 · MEDIUM 11 · LOW 13) | 32 | 32 | 3 lanes, briefed cold. Dimensions: 5×11, 10×9, 4×4, 15×4, 7×3, 6×3, 2×2, 1×1. No loop-1 finding was raised again. Two lanes independently found the CRITICAL: §4.3's guard invocation had dropped `2>&1 \| tee "$SYS_LOG" \| progress_filter` and `SYS_DL_RC=${PIPESTATUS[0]}` — collateral from loop 1's own argv rewrite, and it would have cost the download log, ONEUP-0040's progress markers and ONEUP-0085's rc-143 discrimination. Draft defects the loop also caught: the Goal promised no password box for **firmware**, which elevates through polkit and cannot be covered by a sudoers rule; the stand-down fired on any probe that emitted nothing, not on an explicit `@@AUTH@@\|off`; and the GUI suite's 56 window constructions could reach the real `systemctl --user disable`. Verified by running: `local x=$(false)` masks the status where a split assignment preserves it, and `make_cdn_reposd` contains no `sudo` (so §2.2's enumeration stands — dismissed) |
| 1 | 2026-08-07 | 27 (CRITICAL 2 · HIGH 9 · MEDIUM 6 · LOW 7 · dismissed 3) | 24 | 24 | 3 lanes. Dimensions: 10×7, 5×5, 6×3, 15×2, 7×2, 2×2, 4×1, 8×1, 12×1. All three lanes independently found the same CRITICAL — §4.3's guard had no argv contract and contradicted the wrapper it claimed to preserve. Two claims were settled by running them rather than reading them: `visudo -cf` **rejects** a non-absolute `Cmnd` (so §6's bare-name fallback row described an impossible state), and `sudo -k` does **not** invalidate a warm credential. INV-2's grep was measured at 70 matches against 26 at command position — 28 of them comments. Dismissed: an unowned `/usr/libexec` file (the drop-in already has that property), the exhaustiveness of §2.2's three call sites (re-scanned: it is exhaustive), and a probe-cost observation (INFO) |
