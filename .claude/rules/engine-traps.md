---
paths:
  - "update_system.sh"
  - "tests/run-tests.sh"
  - "docs/reference/marker-protocol.md"
---

# Engine traps

`CLAUDE.md` §6 keeps a one-line headline for each. Each of
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

- **A run must survive the GUI going away.** The logging `exec` uses `tee -a -p`; without
  `-p`, quitting the window kills `tee`, `SIGPIPE`s the engine, and leaves zypper orphaned
  mid-transaction. Never add a code path that kills the engine mid-run —
  `docs/standards/security.md` §6.3.

- **Nothing the engine spawns may outlive it.** A trap cannot run when the engine is
  `SIGKILL`ed, so a background helper must watch the engine's pid and exit on its own.
  Keep-alives were once found still running 40 minutes after their run was killed —
  `docs/standards/security.md` §2.4.

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
