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
content delivery network — which answers directly instead of selecting a mirror that may not have the
file yet — and the update completes, instead of installing nothing.

## 1. Goal

A run whose download pass fails with a *transfer* error completes anyway, without the user
doing anything, learning anything, or being told to retry. When recovery is impossible the
run still fails — but names the package that could not be fetched, wherever one can be
identified from the log, rather than offering "check your internet connection" to someone
whose connection is fine.

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

Nothing is installed. Measured on the 2026-08-07 run and recorded in ROADMAP `ONEUP-0096`:
82 packages preloaded, **one** — `kernel-default`, routed to the slow origin — could not
be fetched, and the transaction installed nothing at all.

### 2.2 The measured failure

The failure reproduced **four times** on the maintainer's machine on 2026-08-07
(`docs/specs/ONEUP-0085-stoppable-download.md` §2.2), two of them through OneUp, every one
on `kernel-default-7.1.6`. From
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

**The file that actually failed was measured too, on the day, and that measurement is the
stronger one.** ROADMAP `ONEUP-0094`'s `DIAGNOSED (2026-08-07)` note records
`kernel-default-7.1.6` itself: `downloadcontentcdn.opensuse.org` at 1,013,554 B/s against
`downloadcontent.opensuse.org` at 228,452 B/s, the CDN answering `HTTP 200` with the
correct `content-length: 210194084` — while the metalink for that file offered **exactly
one** source, the slow origin, with no mirrors to fall back to. That is the failure's own
routing, not an inference from it. The `7.1.5` figures above are the same comparison
re-run on the current build once `7.1.6` had been superseded, and they corroborate it
rather than stand in for it.

4.0× on throughput, and — the property that actually matters — the CDN host answers
directly rather than redirecting, so "no mirror has this file yet" cannot arise. It serves
repository metadata too, so it is a complete substitute and not merely a package store:

```
$ curl -s -o /dev/null -m 20 -w '%{http_code} %{size_download}\n' \
    http://downloadcontentcdn.opensuse.org/tumbleweed/repo/oss/repodata/repomd.xml
200 14119
```

**Over HTTPS as well as HTTP** — which matters because most of this machine's openSUSE
baseurls are `https://`, and the §4.2 rewrite preserves the scheme:

```
$ curl -s -o /dev/null -m 25 -r 0-10000000 \
    -w 'code=%{http_code} speed=%{speed_download} ssl_verify=%{ssl_verify_result}\n' \
    "https://downloadcontentcdn.opensuse.org/tumbleweed/repo/oss/x86_64/$K"
code=206 speed=1951181 ssl_verify=0
$ curl -s -o /dev/null -m 20 -w '%{http_code} %{size_download} %{ssl_verify_result}\n' \
    https://downloadcontentcdn.opensuse.org/tumbleweed/repo/oss/repodata/repomd.xml
200 14119 0
```

`ssl_verify_result=0` is a valid certificate chain. A rewrite that produced an `https://`
URL the host could not serve would leave recovery inert on most repositories while
appearing to work, so this is measured rather than assumed.

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
existing early return. All five conditions must hold:

1. The download pass failed — `$ok` false, which for this pass means `SYS_DL_RC` was
   neither 0 nor 143.
2. The failure is **transfer-shaped**: `$SYS_LOG` matches
   `bytes missing|returned error: 404|Download.*failed|Curl error|connection failed`, and
   does **not** match the shapes that recovery cannot help and must not mask —
   `No space left|disk full|conflict|nothing provides|not installable|signature|GPG`.
3. No stop is pending (`stop_pending` false). A user who asked to stop is not served by
   another download pass.
4. Recovery has not already run this run (`DL_RECOVERED` false).
5. There is something to redirect —
   `grep -qiE '^baseurl[[:space:]]*=[[:space:]]*https?://download\.opensuse\.org' "$REPOS_DIR"/*.repo`
   succeeds, where `REPOS_DIR` is the repository directory defined in §4.2. Checked
   *before* the copy, so a machine on a local mirror skips recovery without the §4.2 `sed`
   ever running against an unexpanded glob.
   **This probe and §4.2's substitution must match the same strings, and are written to.**
   A looser probe (`^baseurl.*download\.opensuse\.org`) also accepts
   `baseurl=http://mirror.local/download.opensuse.org/tumbleweed/…`, where the substitution
   rewrites nothing — so recovery would fire and run a byte-identical second attempt, the
   plain retry §9 rejects, on exactly the local-mirror machines §6's first row means to
   skip. Both patterns are case-insensitive (`-i` / `sed` `I`), matching the `grep -qiE`
   the engine's own hint chain and `repo_scoped_failure` already use.

Then: snapshot `$SYS_LOG` (§4.4 needs it), build the redirected repository directory
(§4.2), set `REPOSD_OVERRIDE`, set `DL_RECOVERED=true`, and call `run_system_download`
again. If it now succeeds, the step continues into `run_system_commit` exactly as a
first-time success would.

**`REPOSD_OVERRIDE` is cleared at the end of `run_system_upgrade`, on every path, not just
the retry-failed one.** The caller's repo-skip path can call `run_system_upgrade` a third
time after disabling a repository, and that attempt must run against the user's own
repository set. Two routes reach it and only one is obvious: the retry failing, and — the
one a narrower rule misses — the retry *succeeding* and `run_system_commit` then failing,
which also leaves `$ok` false and admits the step to the repo-skip probe. Clearing at the
function's end covers both. `DL_RECOVERED` stays true, so no third attempt gets a second
recovery.

That interaction is also why the clearing is not optional bookkeeping: `disable_repo`
edits the **real** repository directory, so a third attempt still reading the redirected
copy would not see the repository the caller had just disabled, and would repeat the
failure the disable was meant to route around.

`REPOSD_OVERRIDE`, `DL_RECOVERED` and `SYS_LOG_FIRST` are file-scope globals declared and
reset beside `SYS_TXN` and `SYS_DL_RC`, for the same reason those are: the engine runs them
across functions and a `local` would not survive.

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

**Only `baseurl=` is in scope.** A `.repo` file may also carry `metalink=` or `mirrorlist=`
naming the same host, and those are deliberately left alone: they are the mirror-selection
mechanism this item is recovering *from*, so redirecting them would either be a no-op or
would point libzypp at a mirror list the CDN host does not publish. A repository defined
*only* by `metalink=`/`mirrorlist=` has no `baseurl` to match, so §4.1 condition 5 declines
recovery for it — correctly, and without a special case.

**The engine prints the copied directory's path** as an ordinary log line
(`Recovery: retrying downloads via downloadcontentcdn.opensuse.org (repositories copied to
<dir>)`) rather than a marker, so the run log records what was attempted and INV-9 has
something to read. It is not a marker because nothing in the window needs to act on it —
`marker-protocol.md` §2 is the rule that a marker exists for its reader.

The directory is removed with **`rm -rf`** — `rm -f` does not remove a directory, so
writing it that way would leave INV-9 failing and one directory per recovered run under
`/tmp`. It is removed at **both** of the caller's existing cleanup sites: the `$SYS_STOPPED`
branch's `rm -f "$SYS_LOG" "$PROGRESS_SEEN_FILE"` and the one at the end of the step. The
`$SYS_LOG` snapshot (§4.4) is removed at the same two places.

### 4.3 Where the flag is added

`system_txn_argv` — the single place the transaction argv is built, which ONEUP-0085's
INV-5 requires and which this item must not break. `--reposd-dir` is a global option, so
it is inserted after `zypper` and before the command verb, and only when
`REPOSD_OVERRIDE` is non-empty.

**Both branches take it.** `system_txn_argv` has a Leap arm and a Tumbleweed arm, and
ONEUP-0085's INV-5 is explicit that the argv is stated in one place *on both distros*.
Patching only the `dup` line would leave Leap with recovery that silently does nothing —
a retry byte-identical to the attempt that just failed, which is the "plain retry" §9
rejects:

```sh
system_txn_argv() {
    local -a reposd=()
    [[ -n "$REPOSD_OVERRIDE" ]] && reposd=(--reposd-dir "$REPOSD_OVERRIDE")
    if [[ -f /etc/os-release ]] && grep -q "Leap" /etc/os-release; then
        SYS_TXN=(zypper --non-interactive "${reposd[@]}" update)
    else
        SYS_TXN=(zypper --non-interactive "${reposd[@]}" dup --allow-vendor-change)
    fi
}
```

An explicitly-empty array rather than a `${VAR:+…}` expansion: under `set -u` a
`"${reposd[@]}"` on an empty array is safe in bash 4.4+, and the array form keeps a path
containing spaces intact without relying on how quoting nests inside a parameter expansion.

Building it there means the retry download pass and the commit pass that follows it read
the *same* repository set — the solver would otherwise resolve against one configuration
and install from another. The `--size` probe is unaffected: it runs before any download,
so `REPOSD_OVERRIDE` is always empty when it builds its argv.

### 4.4 What the user is told

On recovery success, after the step ends `ok`:

> Recovered from a failed download — some packages were fetched from openSUSE's content
> delivery network instead of the mirror that failed.

On recovery failure, a new arm in the caller's existing hint ladder names the file, because
"check your internet connection" is actively misleading when 81 of 82 packages arrived:

> Could not download <package> — openSUSE's servers are still catching up with this
> update. Nothing was installed and everything already downloaded has been kept; try again
> later.

**The arm's guard is `$DL_RECOVERED`, and its position is second — immediately after
`systemic_repo_fail`, before every log-pattern arm.** Both halves are decisions, not
details. The guard must be the flag rather than a log signature: condition 5 can decline
recovery entirely, and an arm keyed on the log would then tell a user "openSUSE's servers
are still catching up" about a retry that never happened. And it sits *after*
`systemic_repo_fail` because a multi-repository outage is transfer-shaped by definition
(`Curl`, `Download.*failed`), so a first-position arm would answer a whole-network failure
with a single-package sentence — the more specific-sounding message being the less true
one. Every remaining arm is a log-pattern arm and is therefore less specific than this one.

Both hints go through `marker HINT`, which the window already renders, and which the engine
already emits on a *successful* step for the set-aside-repository note — so a HINT on
success is existing behaviour, not a new marker usage (§8 records the one row of
`marker-protocol.md` that describes it too narrowly).

**The package name comes from the snapshot, not the live log.** `run_system_download`
pipes through `tee "$SYS_LOG"` **without `-a`**, so the retry truncates the file and the
first failure's evidence with it. §4.1 therefore copies `$SYS_LOG` to `$SYS_LOG_FIRST`
before the retry, and the name is the first `Preloading:`/`Retrieving:` line in *that*
snapshot carrying a bracketed error. When no name can be extracted the sentence drops that
clause rather than printing an empty one.

Wording: the failure hint follows `wording-and-translation.md` — it says what happened and
what to do. **The success hint deliberately does not**, and that is not a breach of the
same rule: it reports a run that already succeeded, so there is nothing for the user to do.
The rule governs hints that accompany a failure.

### 4.5 What recovery must never make worse

Recovery is an extra attempt, so the *outcome* must be the one that was already happening.
If the copy cannot be made, if `$REPOS_DIR` holds no rewritable repository, or if the
retry fails for any reason, the step still ends `fail` and the run ends as it does today.
Nothing about the outcome may be worse for having tried.

**"The same outcome" is not "the same log."** The retry truncates `$SYS_LOG` (§4.4), so
after a failed recovery the hint chain and `repo_scoped_failure` read the *second*
attempt's output — which is the correct evidence for what the machine is now doing, and is
why §6's "a different failure is reported as the failure it is" row does not contradict
this section. What must survive the truncation is the first attempt's package name, and
`$SYS_LOG_FIRST` is why it does.

Package integrity is unchanged and is not this item's to guarantee: the retry runs
`zypper`, not a hand-rolled fetch, so libzypp still checks each package's checksum against
the signed repository metadata and its GPG signature under the `gpgcheck` settings the
copied `.repo` files carry verbatim. That is the whole reason §9 rejects placing files
into `/var/cache/zypp/packages` by hand.

## 5. Correctness invariants

The suite is `tests/run-tests.sh` throughout. All clauses assert engine behaviour except
INV-6, which is structural and is marked as such.

- **INV-1** Recovery runs only when the download failure is transfer-shaped.
  *Test:* two scenarios sharing one mock shape, because condition 2 has two halves and one
  fixture cannot exercise both. (a) A `--download-only` invocation printing
  `nothing provides libfoo` and exiting 1 — the positive list does not match. (b) One
  printing **both** `bytes missing` **and** `No space left on device` — the positive list
  matches and the exclusion must still suppress recovery, which is the half a
  single-signature fixture leaves untested. Each asserts the step ends `fail` and that
  `--download-only` was invoked exactly **once** (the mock appends a line per call to a
  counter file). Breaks if the trigger tests only the exit status, which would retry every
  solver conflict and disk-full over a slower path to the same failure.

- **INV-2** Recovery is attempted at most once per run.
  *Test:* a mock `zypper` whose `--download-only` invocation always prints
  `bytes missing` and exits 1. The counter file holds exactly **2** lines, and the step
  ends `fail`. Breaks on a retry loop, which would turn a failed update into a hang —
  the ONEUP-0048 failure this project has already paid for once.

- **INV-3** The retry preserves every repository alias.
  *Test:* the scenario's `ONEUP_REPOS_DIR` holds a `.repo` file whose alias contains the
  host name (`[download.opensuse.org-oss]`, `baseurl=http://download.opensuse.org/…`).
  The mock `zypper`'s `--download-only` branch **copies its `--reposd-dir` argument's
  contents to a fixture path on its second `--download-only` invocation** (not its second
  invocation overall — a refresh call would consume the count), and the scenario asserts
  against that
  fixture — the alias line **unchanged**, the baseurl line naming
  `downloadcontentcdn.opensuse.org`. The capture-during-the-run shape is required, not
  stylistic: INV-9 deletes the directory before the engine exits, so a post-run assertion
  against it could only ever pass by INV-9 being broken. Breaks on an unanchored
  substitution, which renames the alias, moves the package cache and silently discards
  every package ONEUP-0087 kept.

- **INV-4** The engine never writes to the real repository directory.
  *Test:* the scenario records `ls -1 "$ONEUP_REPOS_DIR"` **and** `md5sum
  "$ONEUP_REPOS_DIR"/*.repo` before and after a recovered run, and asserts both match —
  `md5sum` over the directory itself errors rather than hashing it, and digests alone
  would not notice a file added to or removed from the directory. Breaks if the rewrite is
  applied in place instead of to a copy, which would permanently repoint the user's
  machine at one host.

- **INV-5** Only openSUSE's own host is redirected.
  *Test:* the scenario's repository directory also holds a third-party repo
  (`baseurl=https://ftp.gwdg.de/pub/linux/misc/packman/…`). In the INV-3 fixture — the
  same capture, for the same reason — that baseurl is byte-identical to the original.
  Breaks on a host-agnostic rewrite, which would send every third-party repository to a
  host that has never heard of it, turning one failed package into a failed refresh of
  every source.

- **INV-6** The transaction argv is still built in exactly one place.
  *Test (structural):* `grep -cE '^\s*system_txn_argv' update_system.sh` returns **4** —
  one definition plus three callers. → returns `4` on `87a3ba9`, before this change.
  Breaks if the retry builds its own argv rather than re-using `system_txn_argv`, which is
  the natural way to write it and is exactly what ONEUP-0085's INV-5 forbids. **This is a
  re-assertion of that invariant, not a new one** — it is carried here because this item is
  the most likely thing to break it, and the clause is deliberately identical so the two
  cannot drift.

- **INV-7** A recovered run is reported as a success, and says how.
  *Test:* a mock `zypper` that fails the first `--download-only` with `bytes missing` and
  succeeds on the second. The scenario asserts `@@STEP_END@@|system|ok` and a
  `@@HINT@@` containing `content delivery network`. Breaks if the first failure's `ok=false`
  is not cleared before the commit pass, which would install the update and then report it
  as failed.

- **INV-8** A stop asked for during the failed download is not answered with another
  download.
  *Test:* the INV-2 mock, extended so its `--download-only` branch **touches
  `$ONEUP_STOP_FILE` itself** before printing `bytes missing` and exiting 1. The scenario
  asserts the counter file holds exactly **1** line, and that the step ends **`fail`**.
  The mock must create the stop file, not the scenario: `stop_pending`'s staleness rule is
  `"$stop_file" -nt "$run_state"`, so a stop file touched before the engine starts is older
  than the `run.state` the engine writes and is never pending. And the outcome is `fail`
  rather than `skip` because the download exited 1, not 143, so `$ok` is false and
  `run_system_upgrade`'s `$ok || return 0` fires before `SYS_STOPPED` can be set — existing
  engine behaviour this item does not change. What the invariant asserts is that recovery
  was *suppressed*, which the counter proves. Breaks if the trigger checks only the log
  signature — a user who pressed Stop would be answered with another download.

- **INV-9** The temporary repository directory does not outlive the run — on **every**
  outcome.
  *Test:* three scenarios, each reading the copied directory's path from the `Recovery:`
  log line §4.2 requires the engine to print, then asserting the directory is gone after
  the engine exits: INV-7's (recovery succeeded), INV-2's (recovery ran and the retry
  failed), and INV-8's (a stop, which leaves via the `$SYS_STOPPED` branch's separate
  cleanup site). All three are required because the break-mode this invariant exists to
  catch — a cleanup written on the success path only — **passes** a test bound to the
  success scenario alone. A test that cannot fail on the bug it names is the shape
  `documentation.md` §5 calls a wish. Also breaks on `rm -f`, which cannot remove a
  directory.

- **INV-10** The retry does not re-download what the first attempt already fetched.
  *Test:* the INV-7 mock records, per call, the package files present in its fake cache
  directory; the scenario seeds that directory before the run and asserts the retry's
  invocation still sees the seeded files. This is the invariant behind §4.2's alias
  argument, and it is stated as an invariant because the argument rests on an
  **assumption this spec does not measure**: that libzypp keys `/var/cache/zypp/packages`
  by repository alias, so an unchanged alias keeps the cache across a changed baseurl.
  What *is* measured is that the anchored `sed` leaves aliases unchanged; the cache
  consequence is inferred from it. If the assumption is false the item still works — the
  retry re-downloads — but it stops being cheap, and §9's rejection of the plain retry
  weakens with it. Breaks if the implementation renames aliases, or points
  `--reposd-dir` at definitions whose alias differs from the user's in any way.

## 6. Failure modes

| Situation | Behaviour |
| --- | --- |
| `$REPOS_DIR` unreadable, or holds no `download.opensuse.org` baseurl | Recovery is skipped; the original failure is reported exactly as today (§4.5). A machine on a local mirror has nothing to redirect to, and that is not an error. |
| `downloadcontentcdn.opensuse.org` is unreachable or renamed | The retry fails; the original failure is reported. One wasted attempt, never a worse outcome. The host is not a promised interface — the same class as ONEUP-0046's zypper wording — and §7 T-1 is what would catch it going away. |
| The retry hits a *different* failure (disk full during the second pass) | Reported as the failure it is. Recovery does not re-classify what it did not cause. |
| `--reposd-dir` unsupported by a forked or older zypper | zypper exits with a usage error, the retry fails, the original failure is reported. Same degradation as the §4.5 rule; no minimum version is imposed. |
| The retry re-downloads repository metadata because the URL changed | Accepted cost. It happens once, only on a run that has already failed, and only for openSUSE-hosted repositories. **It is not silent:** the retry is an ordinary `run_system_download`, so `@@PROGRESS@@` and the GUI's stall clock cover it exactly as they cover the first pass — which is what keeps ONEUP-0048's rule (a slow server must never be indistinguishable from a hang) true across a doubled download phase. No separate time budget is imposed for the same reason none is imposed on the first pass: the per-repository refresh timeout and the liveness line are the budget. |
| The retry rewrites `PROGRESS_SEEN_FILE` | Correct, and deliberate. That file is truncated by whichever download pass writes last, and the retry's tally is the one that describes the packages actually fetched. A recovered run therefore ends with a non-zero count, so ONEUP-0046's stale-parser canary ("packages installed but no progress recognised") stays quiet on a healthy recovery. |
| The user presses Stop *during* the retry | The retry is an ordinary `run_system_download`, so ONEUP-0085's stop path applies unchanged — `SYS_DL_RC` 143, nothing installed. |
| Recovery succeeds but the commit then fails | The commit's own failure is reported. The HINT for a recovered download is emitted only on a step that ended `ok` (§4.4), and `REPOSD_OVERRIDE` is cleared on this path like every other (§4.1) — the caller's repo-skip retry must not inherit it. |
| The failure really was repo-scoped (a dead third-party repo) | Recovery fires first and costs one extra download pass before `repo_scoped_failure` reaches the remedy that works. Accepted, and the ordering is still right: an unreachable repository is transfer-shaped by any regex that can see a truncated download, so distinguishing the two before trying is not possible from the log alone — and the repo-skip path is not lost, only deferred by one pass. The reverse order would send every transfer failure through `find_failing_repos`, which refreshes each repository under `sudo` and is far more expensive than one retry. |
| Recovery failed **and** several repositories are failing at once | `systemic_repo_fail` wins — its arm sits ahead of the recovery arm in the ladder (§4.4). A whole-network failure answered with a single-package sentence would be the more specific-sounding message and the less true one. |

## 7. Tests

§5 owns the invariant clauses. Two further requirements, one on the harness and one on a
fact the invariants assume.

**`run_engine` must pre-set `ONEUP_REPOS_DIR`, alongside `ONEUP_STOP_FILE`,
`ONEUP_RUN_STATE`, `ONEUP_ZYPP_PID_FILE` and `ONEUP_INHIBITED`**, and `setup_common` must
seed that directory with **one `.repo` file carrying a `download.opensuse.org` baseurl and
one carrying a third-party host**. The seed is not decoration: §4.1 condition 5 declines
recovery when no openSUSE baseurl is present, so against an empty directory INV-2's counter
reads 1 instead of 2 and every recovery scenario silently tests the skip path while
appearing to test recovery. Stating the fixture once in the harness is what stops each
invariant restating it. Not just in the recovery
scenarios — in the harness, so every scenario inherits it. Two reasons, and the second is
the one that bites: `testing.md` §2 and `CLAUDE.md` §6 forbid a test that reads the state of
the machine it runs on, and without the redirection every recovery scenario would read the
developer's real `/etc/zypp/repos.d`. That would make INV-2's "exactly 2 lines" depend on
whether the tester's machine happens to have a `download.opensuse.org` baseurl at all —
§6's first row skips recovery when it does not — so the suite would pass or fail on the
tester's repository list. That is precisely the class this project has already paid for
twice (ONEUP-0050, ONEUP-0055).

- **T-1 — the CDN host is real, and the check is skippable.** A scenario that resolves
  `downloadcontentcdn.opensuse.org` and requests `repodata/repomd.xml`, asserting HTTP
  200. It is **network-dependent, so it is gated on `ONEUP_TEST_NETWORK=1` and SKIPs
  loudly otherwise** — `testing.md` §2 forbids a test that depends on the machine's
  state, and a silent skip is the ONEUP-0068 shape. **`local-CI.sh` sets
  `ONEUP_TEST_NETWORK=1`; the pre-push hook and the release workflow do not.** An opt-in
  nobody opts into catches nothing, so the run that owns it is named here rather than left
  to whoever writes the scenario. Its value is that it fails loudly the day openSUSE
  retires the host, rather than leaving recovery quietly inert. It requests
  `repodata/repomd.xml` over **`https://`**, the scheme §2.4 measured and the one most of
  the machine's baseurls carry.

The suite's mock `zypper` already dispatches on `"$*"` with `*download-only*` matched
before the general `*dup*` case; the recovery scenarios add a per-call counter file to
that mock, which is what INV-1, INV-2 and INV-8 assert on. None of these scenarios exists
yet — every one of them ships with the implementation.

## 8. Docs & release

- `CHANGELOG.md` — a `Fixed` entry under `[Unreleased]`, in the user's language: an update
  that failed because one package would not download now fetches it from openSUSE's
  content delivery network instead of giving up.
- **ROADMAP ONEUP-0094 carries a claim this spec disproves** — that `ZYPP_MULTICURL=0` was
  verified to fix a run. §2.3 shows the variable is absent from libzypp 17.38.14. The
  bullet is annotated, not rewritten: the measurement it records is real, its attribution
  is not. The same annotation corrects its opening count — the bullet says "Observed twice
  on 2026-08-07", where the failure reproduced four times (§2.2), two of them through
  OneUp.
- **The bullet's `Kind:` must change from `enhancement` to `fix`, in the same annotation.**
  It is not clerical: `workflow.md` §1.2 bars feature work from `main` during the freeze, so
  a bullet reading `enhancement` and a spec reading `fix` is a live contradiction about
  where this work is allowed to land. §3 records why the §1.1 test is met — the update
  installs nothing — and the bullet must say the same.
- **Two new environment overrides join the engine's documented set** — `ONEUP_REPOS_DIR`
  (the repository directory, redirected by the suite) and `ONEUP_TEST_NETWORK` (the T-1
  opt-in). They go wherever the existing `ONEUP_*` overrides are recorded, beside
  `ONEUP_STOP_FILE` and `ONEUP_RUN_STATE`.
- **`docs/reference/marker-protocol.md`'s `@@HINT@@` row says "anywhere a failure is
  reported", and that is already too narrow** — the engine emits a HINT on a *successful*
  step for the set-aside-repository note, and §4.4 adds a second such use. The row is
  corrected to say a hint accompanies any step outcome. This is a pre-existing inaccuracy
  this item surfaces rather than creates; no field, order or payload changes, so no version
  of the protocol moves.
- `CLAUDE.md` §6 gains the alias trap from §4.2 — rewriting a repository URL must never
  touch the alias, because the alias is the cache key. It cost a real measurement to find
  and nothing in the code would announce it.
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
  for this machine. Rejected on the measurement in §2.4: it is a redirector, so it offers
  no guarantee the file is there, which is precisely the property that failed.
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
| 2 | 2026-08-07 | 2 lanes; 0 critical, 7 high, 6 medium, 9 low — **22 verified, 0 dismissed** — 14 draft defects vs 8 fix collateral (all fixed). Dimensions: dim 5×8, dim 6×3, dim 4×2, dim 10×2, dim 11×2, dim 15×2, dim 1×1, dim 2×1, dim 8×1 | **No criticals, and the sharpest finding was a test that could not fail on the bug it named.** Both lanes independently caught INV-9: it asserted the temporary directory was gone using the *recovery-succeeded* scenario, so a cleanup written on the success path only — the exact break-mode the clause named — would ship green. It now binds to three scenarios covering success, failed retry and stop. The most consequential draft defect was a scheme gap: every CDN measurement in §2.4 was HTTP, the §4.2 rewrite preserves the scheme, and **nine of this machine's ten openSUSE baseurls are `https://`** — so recovery could have been inert on almost every repository while appearing to work. Measured before fixing: HTTPS returns 206 at 1,951,181 B/s with `ssl_verify_result=0`, repodata 200. Two more contract holes closed: `REPOSD_OVERRIDE` was cleared only when the *retry* failed, missing the reachable retry-succeeds-then-commit-fails path into the repo-skip retry; and condition 5's probe (`^baseurl.*download\.opensuse\.org`) accepted strings the §4.2 substitution would not rewrite, which would have fired recovery as the byte-identical plain retry §9 rejects. One assumption was demoted rather than defended — that libzypp keys the package cache by alias — and is now INV-10 with its inference stated as an inference. |
| 1 | 2026-08-07 | 2 lanes; 4 critical, 3 high, 8 medium, 7 low — **22 verified, 2 dismissed** — 22 draft defects vs 0 fix collateral (all fixed). Dimensions: dim 5×6, dim 2×5, dim 7×4, dim 15×2, dim 6×2, dim 1×1, dim 4×1, dim 9×1, dim 10×1 | **The draft patched one branch of a two-branch function, and wrote three invariants that could not all pass.** §4.3 inserted `--reposd-dir` into the Tumbleweed `dup` line only, leaving Leap with a retry byte-identical to the attempt that had just failed — the exact "plain retry" §9 rejects, and a breach of ONEUP-0085's INV-5 "on both distros". Both lanes led with it. Separately, INV-3 and INV-5 asserted against the copied repository directory *after* the run while INV-9 required it deleted before the engine exits; the fix captures the copy from inside the mock instead. Three more the packet's code windows settled and no careful read would have: `run_system_download` uses `tee` **without** `-a`, so the retry truncates the first failure's log and the named-package hint needed a snapshot; `rm -f` cannot remove a directory; and INV-8's stop fixture was doubly wrong — a stop file touched before the engine starts is older than `run.state`, so `stop_pending`'s `-nt` test never fires, and the expected outcome was `fail`, not `skip`. Two lane claims were **dismissed on measurement**, not on judgement: `conflict`/`signature` as "ordinary noise" in a dup log (zero occurrences across two real run logs) and word-splitting in `${VAR:+…}` (bash preserves the inner quotes — executed both branches under the engine's own `set -uo pipefail` before the replacement landed). |
