# Cold-eyes loop log — `.claude/rules/engine-traps.md`

Kept outside the file because a rule file loads into a session whole, and a review table is
not what that session came for (`docs/standards/documentation.md` §7.1).

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-10-14 | 2 lanes, cold, dispatched with `neutral-lane`, every lane holding every question; genre standard; Q2 2 — 2 verified, 0 dismissed, both fixed | **Gate on ONEUP-0196's new trap, and both lanes found the same two defects, both mine.** The trap ended *"a new call that can time out or be killed does the same"*, which reaches the sudo keep-alive — `security.md` §2.4 gives a background helper a new process group and never a session, or its refresh renews the wrong credential record (ONEUP-0231) — and reaches a privileged call, which `kill_group`'s docstring says is bounded by `sudo timeout` because a root child is not ours to signal. The trap now covers bounded unprivileged children only and names both exceptions with their homes. |
| 2 | 2026-10-14 | 2 lanes, cold, dispatched with `neutral-lane`, every lane holding every question; genre standard; none | **Converged.** Neither lane raised loop 1's two defects again. Both noted, as not material, that the file's opening *"Moved verbatim from `CLAUDE.md` §6"* is false of the new trap, which was written here; it now says only that `CLAUDE.md` §6 keeps a headline for each. Four open questions, none became a finding. |
