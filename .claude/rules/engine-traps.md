---
paths:
  - "update_system.sh"
  - "oneup/engine/**"
  - "tests/run-tests.sh"
  - "tests/mock-env.sh"
  - "tests/parsers-test.py"
  - "docs/reference/marker-protocol.md"
---

# Engine traps

Moved verbatim from `CLAUDE.md` §6, which keeps a one-line headline for each. Each of
these cost a real bug. They are terse on purpose — the reasoning, the measurement and the
exact shape of the rule are in the document named beside each.

- **Never signal the engine to stop a transaction.** `SIGTERM` mid-`zypper dup` either
  leaves rpm half-applied or orphans a zypper that carries on regardless, and its
  abandoned lock blocks the next run. Stopping is cooperative, at safe boundaries only —
  `docs/standards/security.md` §6.

- **A privileged call must not sit inside a subshell.** With no terminal, sudo keys its
  cached credential to the parent process id, and bash forks a real subshell for
  `$(cmd | other)` and friends — so each one authenticates again, which the user sees as
  another password dialog. Capture with `sudo_capture` and process the text afterwards —
  `docs/standards/security.md` §2.2, and §2.3 for the shape this takes in the Python
  engine.

- **A run must survive the GUI going away.** The Bash engine's logging `exec` uses `tee -a
  -p`; without `-p`, quitting the window kills `tee`, `SIGPIPE`s the engine, and leaves
  zypper orphaned mid-transaction. The Python engine's log mirror catches the
  `BrokenPipeError` instead and carries on, and no child it starts inherits the window's
  pipe. Never add a code path that kills the engine mid-run —
  `docs/standards/security.md` §6.3.

- **Nothing the engine spawns may outlive it.** A trap cannot run when the engine is
  `SIGKILL`ed, so a background helper must watch the engine's pid and exit on its own.
  Keep-alives were once found still running 40 minutes after their run was killed —
  `docs/standards/security.md` §2.4.

- **To ask "has my parent gone?", `kill -0` the pid you captured — never read `$PPID`
  again.** Bash sets `PPID` once at shell start and never refreshes it on reparenting, so
  comparing `$PPID` against a startup copy of itself can never fire; and testing it against
  `1` never fires either, because systemd reparents a user session's orphans to
  `systemd --user`. Measured: a child whose parent exited kept `$PPID=170203` for its whole
  life while its real parent moved to `1309`. Both spellings read as a guard and are dead
  code, and both have now been written on this engine — the pid-1 form in
  `reap_orphaned_askpass`, the change-detection form in a spec draft that two review loops
  caught. The keep-alive in `sudo_init` already does it correctly (`while kill -0 "$1"`) —
  `docs/specs/ONEUP-0044-one-authentication.md` §4.2.

- **The suite's prompt counters cannot see a second `sudo_init` inside ONE process.** The
  three counting sudo mocks key their timestamp file to `$PPID`, which is how they model
  sudo's real no-tty behaviour — so two `sudo_init` calls from the same engine share one
  timestamp and log one prompt. Measured: deleting the `HELD_AUTH` guard that suppresses
  the second `sudo_init` on ONEUP-0044's held path left the one-prompt test **green**.
  What caught it was the keep-alive scenario, because the second `sudo_init` spawns a
  second keep-alive group and overwrites `SUDO_KEEPALIVE`, so `cleanup`'s group kill reaches
  only the later one and a keep-alive is orphaned. So a change that could re-enter
  `sudo_init` is covered by INV-9, never by INV-1. Removing the `HELD_AUTH` guard fails
  exactly one check, *"a keep-alive survived a held run (INV-9)"*, and leaves the one-prompt
  scenario green. The `$PPID` half is
  `docs/specs/ONEUP-0044-one-authentication.md` §7.1; INV-9 itself is that spec's invariant
  list, not §7.1.

- **A shape check on a field of codes does not catch English — check membership instead.**
  A `^[a-z0-9-]+$` test looks like it forbids prose, and against a *space-separated* field it
  does not: every word of *"core system packages were updated"* matches it one at a time, so
  a half-converted payload passes and the suite stays green. Where a closed vocabulary
  exists, assert membership of it; shape only tells you a token is well-formed, never that it
  is one of yours. Run the regex rather than reading it —
  `docs/specs/ONEUP-0072-marker-codes.md` INV-1.

- **A slow server must never be indistinguishable from a hang.** Measured, not assumed:
  one mirror served a repository index at under a kilobyte a second and the app showed
  nothing whatever, because zypper prints that phase as dots with no line ending. Three
  defences exist and all three are needed — a per-repository timeout in the engine, a
  liveness line in the GUI, and a stall clock stamped on the raw chunk before any line
  splitting. ONEUP-0048; the invariant is `docs/specs/ONEUP-0054-python-engine.md`.

- **Rewriting a repository URL must never touch the alias — the alias is the cache key.**
  libzypp keys `/var/cache/zypp/packages/<alias>/` by repository alias, and an openSUSE
  repo's alias usually *contains* the host name (`download.opensuse.org-oss`), so a
  blanket substitution renames it and silently discards every package already downloaded —
  defeating ONEUP-0087 on the one path where the kept cache matters most. Anchor the
  substitution to `baseurl=` lines. Nothing in the code announces this; it was found by
  running `zypper --reposd-dir` against a copy and reading the aliases back —
  `docs/specs/ONEUP-0094-download-recovery.md` §4.2.

- **A privileged call added without a matching drop-in entry is invisible until a
  passwordless user meets it.** Nothing fails: the new `sudo …` line is correct code that
  simply prompts, and only someone who turned *Passwordless* on ever finds out — mid-run,
  in sudo's own bare wording. Three such calls accumulated that way (ONEUP-0092). A new
  privileged shape needs an entry in `auth_cmnds`, and the structural check in
  `tests/run-tests.sh` that pins the engine's privileged call-site count is what stops the
  fourth — `docs/standards/security.md` §5.2.

- **Editing the download guard's text is a re-grant for every existing user.** The engine
  compares the installed guard against what it would emit now, so a whitespace or comment
  change invalidates every live grant: those users' toggles read off, their weekly updates
  stand down, and they must switch *Passwordless* on again. Correct — the file really is no
  longer the one the engine expects — but it means `download_guard_src` is not a place for
  cosmetic edits. `docs/standards/security.md` §5.7.
