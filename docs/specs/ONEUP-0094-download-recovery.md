# ONEUP-0094 — A truncated download recovers itself instead of failing the update

**Status:** Draft
**Kind:** fix
**Roadmap:** ONEUP-0094
**Branch:** main (1.4.x — qualifies under `workflow.md` §1.1: the update installs nothing)
**Verified at:** `87a3ba9` — every claim naming a symbol below was resolved against this
tree, not recalled. Every measurement names the command that produced it and the date it
was run.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** When the package download fails because openSUSE routed a file to a
host that will not serve it, the engine fetches the same packages once more from the
content CDN — which always holds them — and the update completes, instead of installing
nothing.

## 1. Goal

A run whose download pass fails with a *transfer* error completes anyway, without the user
doing anything, learning anything, or being told to retry. When recovery is impossible the
run still fails — but names the package that could not be fetched, rather than offering
"check your internet connection" to someone whose connection is fine.

## 2. Background

### 2.1 What happens today

The system step runs `run_system_download` then `run_system_commit` (`update_system.sh`,
the split ONEUP-0085 introduced). A non-zero, non-143 exit from the download pass sets
`ok=false`; `run_system_upgrade` returns immediately and the caller reports the step
failed. The only recovery path that exists is `repo_scoped_failure` →
`find_failing_repos` → `disable_repo`, which is aimed at *one bad repository* — a rejected
signing key, unreachable metadata — and disables it for the run.

A single package that will not transfer is not a bad repository. Every other package in
the same repository downloaded fine, so disabling it would throw away a working source to
work around one file. The failure therefore falls through to the hint chain, matches
`Download.*failed`, and the user is told to check a connection that is not the problem.

Nothing is installed. On a `zypper dup` with 82 packages queued, 81 of them already
downloaded, one unfetchable file discards the entire transaction.

### 2.2 The measured failure

Two runs on the maintainer's machine, 2026-08-07, both on `kernel-default-7.1.6`. From
`~/.local/state/oneup/logs/2026-08-07_083514.log`, quoted in
`docs/specs/ONEUP-0085-stoppable-download.md` §2.2:

```
Preloading: kernel-default-7.1.6-1.1.x86_64.rpm [end of response with 194225024 bytes missing]
Installation has completed with error.
@@STEP_END@@|system|fail|zypper reported an error
```

The same shape, without the truncation, is already in the corpus of run logs — the
terminal form carries no "trying next mirror" clause:

```
$ grep -rhoE 'Preloading: \S+ \[[^]]*404[^]]*\]' ~/Documents/update-logs/*.log | head -2
Preloading: util-linux-systemd-2.42.2-1.1.x86_64.rpm [The requested URL returned error: 404]
Preloading: typelib-1_0-Fwupd-2_0-2.1.7-1.1.x86_64.rpm [The requested URL returned error: 404]
```

### 2.3 Two hypotheses were tested and both were wrong — and one is now explained

`docs/specs/ONEUP-0085-stoppable-download.md` §2.2 records that mirror striping
(`ZYPP_MULTICURL=0`) and libzypp's transfer timeout (`download.transfer_timeout` raised to
3600) each **failed identically**. This spec adds the reason the first one could not have
worked, and it retires the claim in the ROADMAP bullet that the same variable fixed a run:

```
$ rpm -q libzypp                                            # 2026-08-07
libzypp-17.38.14-1.2.x86_64
$ strings /usr/lib64/libzypp.so.* | grep -c '^ZYPP_MULTICURL$'
0
```

`ZYPP_MULTICURL` is not read by this libzypp — it is absent from the binary, while
`ZYPP_MEDIANETWORK`, `ZYPP_CURL2` and `ZYPP_CONF` are all present. Setting it changes
nothing, so the run that "completed under `ZYPP_MULTICURL=0`" completed for some other
reason. **ROADMAP ONEUP-0094's proposal — retry with striping disabled — is inert on this
libzypp and is not what this spec builds.** §8 records the correction owed to the bullet.

The timeout result matters just as much: at 3600 seconds the transfer still ended 180 MB
short, so the connection is being dropped by the far end, not abandoned by libzypp. No
client-side patience setting can fix a server that stops sending.

### 2.4 The host that always has the file

openSUSE serves packages from mirrors, selected per-file by MirrorCache. For a
just-published snapshot no mirror has synced yet, so the metalink degrades to the origin —
and the origin is slow enough, and drops connections often enough, to produce §2.2.
Behind it sits a CDN-fronted copy of the same content that is neither mirror-selected nor
sync-lagged. Measured the same minute, same file, 2026-08-07:

```
$ K=kernel-default-7.1.5-1.1.x86_64.rpm
$ for H in downloadcontentcdn.opensuse.org downloadcontent.opensuse.org; do
    curl -s -o /dev/null -m 25 -r 0-20000000 \
      -w "$H %{http_code} %{speed_download} B/s\n" "http://$H/tumbleweed/repo/oss/x86_64/$K"
  done
downloadcontentcdn.opensuse.org 206 996083 B/s
downloadcontent.opensuse.org    206 246000 B/s
```

4.0× on throughput, and — the property that actually matters — the CDN host answers
directly rather than redirecting, so "no mirror has this file yet" cannot arise. It serves
repository metadata too, so it is a complete substitute and not merely a package store:

```
$ curl -s -o /dev/null -m 20 -w '%{http_code} %{size_download}\n' \
    http://downloadcontentcdn.opensuse.org/tumbleweed/repo/oss/repodata/repomd.xml
200 14119
```

For completeness, the geoip service already points this machine at a CDN entry point, and
that entry point is a *redirector* — it hands back a mirror, which is the routing this
item is recovering from:

```
$ curl -s https://download.opensuse.org/geoip
<geoip><region>af</region><country>za</country><host>cdn.opensuse.org</host></geoip>
```

So `cdn.opensuse.org` is the wrong target for a recovery attempt and
`downloadcontentcdn.opensuse.org` is the right one — §9 records that decision.

## 3. Scope decisions (agreed with the user)

- **The app handles it; the user is never asked to.** User, 2026-08-07: *"This should all
  be seamless — we are offering this to other users and they shouldn't have to struggle
  through this."* So the deliverable is not a hint, a documented workaround, or a setting.
  A HINT is emitted, but only to *say what already happened*.
- **Recovery is bounded at one attempt.** A loop that keeps retrying a failing download is
  the stall ONEUP-0048 exists to prevent, wearing a different hat.
- **The user's configuration is never edited.** OneUp has so far only ever changed a
  repository it disabled during the run itself, and put it back. Rewriting baseurls in
  `/etc/zypp/repos.d` — option (b) in the ROADMAP bullet — is a permanent change to the
  machine and is rejected in §9.
- **The freeze test is met.** `workflow.md` §1.1: the update installs nothing, which is
  the definition of no longer being able to update. This lands on `main` and owes a 1.4.x.

## 4. Design

### 4.1 When recovery triggers

Inside `run_system_upgrade`, after `run_system_download` reports failure and before the
existing early return. All four conditions must hold:

1. The download pass failed — `$ok` false, `SYS_DL_RC` neither 0 nor 143.
2. The failure is **transfer-shaped**: `$SYS_LOG` matches
   `bytes missing|returned error: 404|Download.*failed|Curl error|connection failed`, and
   does **not** match the shapes that recovery cannot help and must not mask —
   `No space left|disk full|conflict|nothing provides|not installable|signature|GPG`.
3. No stop is pending (`stop_pending` false). A user who asked to stop is not served by
   another download pass.
4. Recovery has not already run this run (`DL_RECOVERED` false).

Then: build the redirected repository directory (§4.2), set `REPOSD_OVERRIDE`, set
`DL_RECOVERED=true`, and call `run_system_download` again. If it now succeeds, the step
continues into `run_system_commit` exactly as a first-time success would.

Ordering is deliberate: recovery runs **before** `repo_scoped_failure`. That probe's
remedy is to disable a repository, and a transfer failure is the one case where doing so
throws away a working source.

### 4.2 The redirected repository directory

`zypper --reposd-dir <DIR>` (a global option of zypper 1.14.98, `zypper --help`) reads
repository definitions from a directory of the engine's choosing. The engine copies
`$REPOS_DIR` (default `/etc/zypp/repos.d`, overridable as `ONEUP_REPOS_DIR` for the test
suite) into a `mktemp -d` directory and rewrites **only** `baseurl=` lines whose host is
`download.opensuse.org`:

```sh
sed -i -E '/^baseurl[[:space:]]*=/ s#(https?://)download\.opensuse\.org#\1downloadcontentcdn.opensuse.org#' "$dir"/*.repo
```

Two properties of that expression carry the design, and both were measured rather than
assumed (2026-08-07, `zypper --reposd-dir "$T" lr -u`):

- **The `^baseurl` anchor preserves every alias.** A blanket substitution also rewrites
  the `[section]` header and the filename-derived alias, turning
  `download.opensuse.org-oss` into `downloadcontentcdn.opensuse.org-oss`. libzypp keys
  both the metadata cache and `/var/cache/zypp/packages/<alias>/` by alias, so a renamed
  repository re-downloads everything — discarding exactly the cache ONEUP-0087 exists to
  keep, on the one path where the cache matters most. Anchored, the listing shows the
  original aliases against the new URLs.
- **Third-party repositories are untouched.** The pattern names one host, so `packman`
  (`ftp.gwdg.de`) and `repo-openh264` (`codecs.opensuse.org`) keep their own baseurls.
  OneUp has no basis for assuming any other host has a CDN twin.

The directory is removed on every exit path, in the same `rm -f "$SYS_LOG"` cleanup that
already runs whichever way the step ends.

### 4.3 Where the flag is added

`system_txn_argv` — the single place the transaction argv is built, which ONEUP-0085's
INV-5 requires and which this item must not break. `--reposd-dir` is a global option, so
it is inserted after `zypper` and before the command verb, and only when
`REPOSD_OVERRIDE` is non-empty:

```sh
SYS_TXN=(zypper --non-interactive ${REPOSD_OVERRIDE:+--reposd-dir "$REPOSD_OVERRIDE"} dup --allow-vendor-change)
```

Building it there means the retry download pass and the commit pass that follows it read
the *same* repository set — the solver would otherwise resolve against one configuration
and install from another. The `--size` probe is unaffected: it runs before any download,
so `REPOSD_OVERRIDE` is always empty when it builds its argv.

### 4.4 What the user is told

On recovery success, after the step ends `ok`:

> Recovered from a failed download — some packages were fetched from openSUSE's content
> delivery network instead of the mirror that failed.

On recovery failure, the existing hint is replaced by one that names the file, because
"check your internet connection" is actively misleading when 81 of 82 packages arrived:

> Could not download <package> — openSUSE's servers are still catching up with this
> update. Nothing was installed and everything already downloaded has been kept; try again
> later.

Both go through `marker HINT`, which the window already renders. The package name is the
first `Preloading:`/`Retrieving:` line in `$SYS_LOG` carrying a bracketed error; when no
name can be extracted the sentence drops that clause rather than printing an empty one.
Wording follows `wording-and-translation.md` — a hint says what happened and what to do,
and never ends at the diagnosis.

### 4.5 What recovery must never make worse

Recovery is an extra attempt, so its failure mode must be *the failure that was already
happening*. If the copy cannot be made, if `$REPOS_DIR` holds no rewritable repository, or
if the retry fails for any reason, the engine reports the original failure and the run
ends exactly as it does today. Nothing about the outcome may be worse for having tried.

Package integrity is unchanged and is not this item's to guarantee: the retry runs
`zypper`, not a hand-rolled fetch, so libzypp still checks each package's checksum against
the signed repository metadata and its GPG signature under the `gpgcheck` settings the
copied `.repo` files carry verbatim. That is the whole reason §9 rejects placing files
into `/var/cache/zypp/packages` by hand.

## 5. Correctness invariants

The suite is `tests/run-tests.sh` throughout. All clauses assert engine behaviour except
INV-6, which is structural and is marked as such.

- **INV-1** Recovery runs only when the download failure is transfer-shaped.
  *Test:* a mock `zypper` whose `--download-only` invocation prints
  `nothing provides libfoo` and exits 1. The scenario asserts the step ends `fail` and
  that `--download-only` was invoked exactly **once** (the mock appends a line per call to
  a counter file). Breaks if the trigger tests only the exit status, which would retry
  every solver conflict and disk-full over a slower path to the same failure.

- **INV-2** Recovery is attempted at most once per run.
  *Test:* a mock `zypper` whose `--download-only` invocation always prints
  `bytes missing` and exits 1. The counter file holds exactly **2** lines, and the step
  ends `fail`. Breaks on a retry loop, which would turn a failed update into a hang —
  the ONEUP-0048 failure this project has already paid for once.

- **INV-3** The retry preserves every repository alias.
  *Test:* the scenario's `ONEUP_REPOS_DIR` holds a `.repo` file whose alias contains the
  host name (`[download.opensuse.org-oss]`, `baseurl=http://download.opensuse.org/…`).
  After a recovered run it asserts the copied directory's alias line is **unchanged** and
  its baseurl line names `downloadcontentcdn.opensuse.org`. Breaks on an unanchored
  substitution, which renames the alias, moves the package cache and silently discards
  every package ONEUP-0087 kept.

- **INV-4** The engine never writes to the real repository directory.
  *Test:* the scenario records `md5sum` over `$ONEUP_REPOS_DIR` before and after a
  recovered run and asserts they match. Breaks if the rewrite is applied in place instead
  of to a copy — which would permanently repoint the user's machine at one host.

- **INV-5** Only openSUSE's own host is redirected.
  *Test:* the scenario's repository directory also holds a third-party repo
  (`baseurl=https://ftp.gwdg.de/pub/linux/misc/packman/…`). After a recovered run that
  baseurl is byte-identical in the copy. Breaks on a host-agnostic rewrite, which would
  send every third-party repository to a host that has never heard of it — turning one
  failed package into a failed refresh of every source.

- **INV-6** The transaction argv is still built in exactly one place.
  *Test (structural):* `grep -cE '^\s*system_txn_argv' update_system.sh` returns **4** —
  one definition plus three callers. → returns `4` on `87a3ba9`, before this change.
  Breaks if the retry builds its own argv rather than re-using `system_txn_argv`, which is
  the natural way to write it and is exactly what ONEUP-0085's INV-5 forbids.

- **INV-7** A recovered run is reported as a success, and says how.
  *Test:* a mock `zypper` that fails the first `--download-only` with `bytes missing` and
  succeeds on the second. The scenario asserts `@@STEP_END@@|system|ok` and a
  `@@HINT@@` containing `content delivery network`. Breaks if the first failure's `ok=false`
  is not cleared before the commit pass, which would install the update and then report it
  as failed.

- **INV-8** A stop asked for during the failed download is honoured instead of retried.
  *Test:* the INV-2 mock, with the scenario touching `$ONEUP_STOP_FILE` before the engine
  runs. It asserts the counter file holds exactly **1** line and the step ends `skip`.
  Breaks if the trigger checks only the log signature — a user who pressed Stop would be
  answered with another download.

- **INV-9** The temporary repository directory does not outlive the run.
  *Test:* the INV-7 scenario captures the copied directory's path from the run log and
  asserts it does not exist after the engine exits. Breaks if the cleanup is placed on the
  success path only, leaving a directory per failed run under `/tmp`.

## 6. Failure modes

| Situation | Behaviour |
| --- | --- |
| `$REPOS_DIR` unreadable, or holds no `download.opensuse.org` baseurl | Recovery is skipped; the original failure is reported exactly as today (§4.5). A machine on a local mirror has nothing to redirect to, and that is not an error. |
| `downloadcontentcdn.opensuse.org` is unreachable or renamed | The retry fails; the original failure is reported. One wasted attempt, never a worse outcome. The host is not a promised interface — the same class as ONEUP-0046's zypper wording — and §7 T-1 is what would catch it going away. |
| The retry hits a *different* failure (disk full during the second pass) | Reported as the failure it is. Recovery does not re-classify what it did not cause. |
| `--reposd-dir` unsupported by a forked or older zypper | zypper exits with a usage error, the retry fails, the original failure is reported. Same degradation as the §4.5 rule; no minimum version is imposed. |
| The retry re-downloads repository metadata because the URL changed | Accepted cost. It happens once, only on a run that has already failed, and only for openSUSE-hosted repositories. |
| The user presses Stop *during* the retry | The retry is an ordinary `run_system_download`, so ONEUP-0085's stop path applies unchanged — `SYS_DL_RC` 143, nothing installed. |
| Recovery succeeds but the commit then fails | The commit's own failure is reported. The HINT for a recovered download is emitted only on a step that ended `ok` (§4.4). |

## 7. Tests

§5 owns the invariant clauses. One further scenario exists for a fact the invariants
assume:

- **T-1 — the CDN host is real, and the check is skippable.** A scenario that resolves
  `downloadcontentcdn.opensuse.org` and requests `repodata/repomd.xml`, asserting HTTP
  200. It is **network-dependent, so it is gated on `ONEUP_TEST_NETWORK=1` and SKIPs
  loudly otherwise** — `testing.md` §2 forbids a test that depends on the machine's
  state, and a silent skip is the ONEUP-0068 shape. Its value is that it fails loudly the
  day openSUSE retires the host, rather than leaving recovery quietly inert.

The suite's mock `zypper` already dispatches on `"$*"` with `*download-only*` matched
before the general `*dup*` case; the recovery scenarios add a per-call counter file to
that mock, which is what INV-1, INV-2 and INV-8 assert on.

## 8. Docs & release

- `CHANGELOG.md` — a `Fixed` entry under `[Unreleased]`, in the user's language: an update
  that failed because one package would not download now fetches it from openSUSE's
  content network instead of giving up.
- **ROADMAP ONEUP-0094 carries a claim this spec disproves** — that `ZYPP_MULTICURL=0` was
  verified to fix a run. §2.3 shows the variable is absent from libzypp 17.38.14. The
  bullet is annotated, not rewritten: the measurement it records is real, its attribution
  is not.
- `CLAUDE.md` §6 gains the alias trap from §4.2 — rewriting a repository URL must never
  touch the alias, because the alias is the cache key. It cost a real measurement to find
  and nothing in the code would announce it.
- No marker changes: `HINT` and `STEP_END` are used exactly as specified in
  `docs/reference/marker-protocol.md`, so no version of the protocol moves.
- Ships as a 1.4.x under `workflow.md` §1.1; `release.sh` owns the six version sites.

## 9. Alternatives considered (and rejected)

- **Retry with `ZYPP_MULTICURL=0`** — the ROADMAP bullet's own proposal. Rejected as
  inert: §2.3 shows the variable is not read by libzypp 17.38.14.
- **Raise `download.transfer_timeout` or `download.max_silent_tries`** via a `ZYPP_CONF`
  file or an `/etc/zypp/zypp.conf.d/` drop-in. Rejected on two counts. The timeout was
  already tested at 3600 and failed identically (§2.3), so the premise is disproved; and
  `ZYPP_CONF` replaces the entire configuration rather than layering on it (`man 5
  zypp.conf`, ENVIRONMENT), which on this machine would drop
  `multiversion = provides:multiversion(kernel)` from the vendor file — silently changing
  how kernels are retained, during a kernel update, to work around a download.
- **A plain retry with no change of host.** Cheapest possible fix, and it is what the
  ROADMAP bullet's evidence actually supports once the `ZYPP_MULTICURL` attribution is
  removed. Rejected because the failure reproduced four times in one day
  (`ONEUP-0085` §2.2): a retry down the same route is a second wait for the same outcome.
  Changing the host is what makes the second attempt different from the first.
- **Point the retry at `cdn.opensuse.org`** — the host openSUSE's own geoip service names
  for this machine (§2.4). Rejected because it is a redirector: it hands back a mirror,
  which is the selection this item is recovering *from*. Measured 2026-08-07, it redirected
  to `opensuse.mirror.liteserver.nl`. Fast when it works, and no guarantee the file is
  there — which is precisely the property that failed.
- **Rewrite the user's `/etc/zypp/repos.d` baseurls permanently** — option (b) in the
  ROADMAP bullet. Rejected: a permanent, invisible change to the user's machine, forfeiting
  mirror redundancy for every future update to fix one failed one, and one that outlives
  OneUp's uninstallation.
- **Fetch the failed package directly and place it in `/var/cache/zypp/packages`** —
  option (a) in the ROADMAP bullet. Rejected: it puts OneUp in the business of deriving
  cache paths and verifying checksums that libzypp already verifies, for no gain over
  letting zypper do the fetch (§4.5).
- **Commit in heaps** so a partial transaction survives — already considered and rejected
  as ONEUP-0096, on the grounds that it salvages a half-finished upgrade instead of fixing
  the download. Its reasoning is unchanged by this item.

## 10. Out of scope

- **The progress bar's mismatched numerator and denominator** — ONEUP-0093. It shares this
  item's log lines and nothing else.
- **Making the Stop button phase-aware** — ONEUP-0095, and 2.0 work under the freeze.
- **Recovery for the Flatpak or firmware steps.** Neither uses openSUSE's mirror
  infrastructure, so neither has this failure to recover from.
- **Diagnosing why the origin drops connections.** That is openSUSE's, not OneUp's;
  ONEUP-0085 §2.2 already establishes that OneUp's obligation is to cope, not to explain.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
