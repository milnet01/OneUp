# ONEUP-0329 — the check counts what the update will really change

**Status:** Reviewed
**Kind:** fix
**Roadmap:** ONEUP-0329
**Branch:** v2
**Verified at:** `432261c` — every symbol below was opened on 2026-10-23, and every figure is
a dated measurement taken on this machine that day, with the command beside it.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes loop log

**In one sentence:** on a packaged install the check asks OneUp's system service to run the
update as a dry run, so its count and its package list are what the update will really do;
where that cannot happen, the check says "at least N".

**Amends, by pointer:** `docs/specs/ONEUP-0259-package-model.md` §4.3 and INV-1, and
`docs/specs/ONEUP-0249-system-service.md` §4.2 (§8 below).

## 1. Goal

After this ships, Check's count on a packaged install is the number of packages the update
will change — upgrades, downgrades, new packages and removals — and the package list shows
each of them. On the AppImage, or when the service cannot answer, the count is still the
rootless one, and every place that shows it says "at least".

## 2. Background

**The count is wrong on a Tumbleweed snapshot that changes the package stack.**
`steps.system_updates` reads `zypper --xmlout --no-refresh --non-interactive list-updates`,
as the user. `list-updates` lists only newer versions of installed packages that its solver
will take without removing or adding anything. The update itself runs `zypper dup`
(`steps.system_txn_argv`), whose solver does both.

Measured in the run log `~/.local/state/oneup/logs/2026-10-23_074231.log`
(`grep -n 'to upgrade,' <log>`): the check before that run said 524. The dry run inside
the run said `883 packages to upgrade, 3 to downgrade, 41 new, 26 to remove, 3  to change
vendor, 1 to change arch.` So the
check missed 359 upgrades and every new and removed package.

**An exact count needs root.** `zypper dup --dry-run` refuses an ordinary user. A run in a
user namespace was tried and fails on `/run/zypp.pid` and on key import (ONEUP-0329's
roadmap body).

**The service can already run a dry run without a password box.** `rootops.OPS` has
`size-dry-run`, the transaction plus `--dry-run`. Measured 2026-10-23 with a scratch script
that called `service_client.open_session(interactive=False, import_keys=False)` and then
`service_client.run("size-dry-run", {"cdn": False}, merge_stderr=True)` from a desktop
terminal: the session opened in 0.2 s with no box. The job exited 0 after 27.6 s, most of
it zypper refreshing four repositories as root before solving.

**polkit says yes to the desk, and no to the restrictive profile.** `pkaction --verbose
--action-id org.freedesktop.packagekit.system-update` on 2026-10-23: implicit active `yes`.
`/usr/etc/polkit-default-privs/profiles/standard` gives `auth_admin_keep:auth_admin_keep:yes`;
`profiles/restrictive` gives `auth_admin_keep`, so there a non-interactive check is refused.
ONEUP-0249 §4.4 measured that a `systemd --user` process gets the desk's answer.

**zypper's XML names every change.** `/usr/share/zypper/xml/xmlout.rnc` (zypper 1.14.101)
defines `install-summary` with child elements `to-install`, `to-remove`, `to-upgrade`,
`to-downgrade`, `to-upgrade-change-arch`, `to-downgrade-change-arch`, `to-reinstall` and
`to-change-arch`, each holding `solvable` elements with `name`, `edition`, `edition-old`,
`arch` and `repository`. Measured 2026-10-23 with `sudo env LC_ALL=C zypper --xmlout
--no-refresh --non-interactive dup --allow-vendor-change --dry-run`: exit 0, one
`to-upgrade` element holding 31 `solvable` elements, `packages-to-change="31"`. Two
differences from the schema:

- the attribute is **`type="package"`**, where the schema says `kind`. The parser follows
  the output.
- every `repository` read `packman`, a repository whose alias and display name are the same
  word, so this run cannot say which of the two the attribute holds (§4.8).

The editions matched `list-updates`' for the same packages: `libavcodec62` read
`edition="8.1.3-1699.9.pm.11"` and `edition-old="8.1.3-1699.9.pm.10"` in both. That run had
no stack change, so `list-updates` also counted 31.

**The marker contract is frozen for 2.0** (`docs/reference/marker-protocol.md` §5.1). The
fields this needs are §4.5's.

## 3. Scope decisions (agreed with the user)

1. **The service route runs the real `zypper dup --dry-run`; the AppImage keeps the rootless
   count, worded "at least N".** The user, 2026-10-23, recorded on ONEUP-0329.
2. **The count is every change: upgrades, downgrades, new packages and removals** — 953 for
   the 23 October update, not the 927 it downloaded. The user, 2026-10-23.
3. **The package list comes from the dry run too**, so it shows new and removed packages.
   This reopens the frozen marker contract for this item. The user, 2026-10-23.
4. **The check's dry run refreshes the repositories first**, as the update does, rather
   than reading only the cached metadata. The user, 2026-10-23, knowing it adds tens of
   seconds and network use as root.
5. **A zero on the AppImage still says "up to date".** The user, 2026-10-23.
6. **How "at least" travels is a trailing field on `CHECK`, not `CHECK_UNKNOWN`** (§4.5,
   §9). Not the user's call; derived from items 1 and 5, because `CHECK_UNKNOWN` refuses
   "up to date".
7. **The dry run bounds itself with `timeout`, as `repo-refresh` does**, instead of being
   stopped by the service (§9). Not the user's call.
8. **A check stands down while an update is running**: it takes the fallback without asking
   the service (§4.2 step 0). The user, 2026-10-23, over two alternatives: the window not
   starting a check during a run, and the service refusing `check-dry-run` while another
   session exists.

## 4. Design

### 4.1 The new root operation

`oneup/engine/rootops.py` gains one row, `check-dry-run`, with no arguments:

```python
CHECK_DRY_RUN_SECONDS = int(os.environ.get("ONEUP_CHECK_DRY_RUN_SECONDS") or "180")

"check-dry-run": Op({}, _check_dry_run),
```

`_check_dry_run` returns:

```
<timeout> <CHECK_DRY_RUN_SECONDS> env LC_ALL=C zypper --xmlout <rest of system_txn_argv("")> --dry-run
```

- `<timeout>` is the path `_refresh` uses: `privilege.REFRESH_SUDO_ARGV[0]`, or the bare
  name where none was found.
- `--xmlout` goes straight after `zypper`, because it is a global option. Everything after
  it is `steps.system_txn_argv("")` with its leading `zypper` removed. So the check solves
  the same transaction the update runs, on Tumbleweed and on Leap alike.
- No `--no-refresh`, by §3 item 4.
- The environment variable is read in the process that builds the argv. On the service
  route that is the service, whose environment only its unit or a test harness sets
  (`security.md` §12.3).

The sudo route never runs this operation (§4.2), so `actions.auth_cmnds` and the
passwordless drop-in do not change. The engine-traps rule for a new privileged shape does
not fire: no new `sudo` call site exists.

### 4.2 Who runs it: the check, on the service route only

`actions._check_system` calls a new `steps.system_changes(sizes) -> SystemListing`. It
returns the existing `SystemListing` with two added fields:

```python
class SystemListing(NamedTuple):
    rc: int
    readable: bool
    count: int
    rows: list[Pending]
    skipped: list[str]
    exact: bool = False      # True only when the dry run answered (§4.3)
    why: str = ""            # the terminal line's reason when it did not
```

`Pending` gains `change: str = "upgrade"` (§4.4).

`system_changes`:

0. **A live run.** If `runstate.run_state_holder()` names a live engine, it returns
   `system_updates(sizes)` with `exact` false and `why` `"an update is running"`, and
   opens no session. So a tray or weekly check never refreshes repositories as root
   between a run's root operations. A run not yet holding `run.state` — before
   `claim_run_state` — is not seen here; §4.7's wait covers that window.
1. **Route.** If `route.engine_route(os.environ)` is not `route.SERVICE`, it returns
   `system_updates(sizes)` with `exact` false and `why` `"needs the system service"`.
   The AppImage always lands here (ONEUP-0249 INV-10), and never touches the system bus.
2. **Session.** It calls `service_client.open_session(interactive=False,
   import_keys=False)` **always**, whatever `ONEUP_NONINTERACTIVE` says. A check is never
   the moment for a password box, even one started from the window.
3. **Job.** `service_client.run("check-dry-run", {}, merge_stderr=False)`, then
   `job.read()` and `job.wait()`. The read is bounded by the argv's own `timeout` (§4.1).
4. **Close.** `service_client.close()`, on every path, success or not.
5. **Fallback.** Any of these returns `system_updates(sizes)` with `exact` false and a
   `why` naming the cause: `service_client.Unreachable`; `service_client.Refused` of any
   code (`NotAuthorized`, `Busy`, `Invalid`, `NoSession`); an exit status outside
   `{0, 100, 101, 102, 103, 106}`, `124` (the timeout) included; or stdout
   `parsers.change_list` returns None for (§4.3).

**`system_changes` never calls `privilege.sudo_init`, `privilege.root` or
`privilege.sudo`.** Those fall back to sudo on the `auto` route (ONEUP-0249 §4.7); the
check must never.

**The run is unchanged by this item.** Its `queued` list still comes from
`system_updates` (ONEUP-0259 §4.3). Seeding it from the dry run is ONEUP-0335 (d) (§10).

### 4.3 Reading the dry run

A new `parsers.change_list(xml_text) -> tuple[list[Change], list[str]] | None` reads the
job's stdout, in the shape of `parsers.update_list`: None when it is not well-formed,
**holds no `install-summary` element, holds a child of `install-summary` not in the table
below, or holds a `solvable` with neither a `type` nor a `kind` attribute**; else the
changes and the text of every `<message>`, unescaped. So a summary it cannot fully read
takes §4.2's fallback and never reads as zero.

```python
class Change(NamedTuple):
    name: str
    edition: str        # the model's key edition (below)
    old: str            # edition-old, or "" where there is none
    arch: str
    repo: str           # the repository attribute, as printed (§4.8)
    change: str         # upgrade | downgrade | new | remove
```

- Only `solvable` elements with `type="package"` count, or `kind="package"` where `type`
  is absent, as the schema spells it. A product, pattern or patch is
  skipped: the 23 October run upgraded the `openSUSE Tumbleweed` product, which is not a
  package.
- Each element maps to one change word:

  | Element | `change` |
  | --- | --- |
  | `to-upgrade`, `to-upgrade-change-arch`, `to-reinstall`, `to-change-arch` | `upgrade` |
  | `to-downgrade`, `to-downgrade-change-arch` | `downgrade` |
  | `to-install` | `new` |
  | `to-remove` | `remove` |

- **A removal's key edition is the removed package's own edition**, and `old` is that same
  edition. The run's `Removing:` line names the installed package (ONEUP-0259 §4.3's
  table), so its `PKG|system|removed|name|edition` lands on the check's row.
- **One change per `(name, edition)`**, the first in document order. A package listed under
  two elements is one change.

`system_changes` then builds `SystemListing`:

- `count` is the number of changes, every package one, whatever its name.
- `rows` are the changes whose name passes `steps.valid_package`, as today's rows.
- `skipped` is `SKIPPED_REPO` searched over the messages alone. With `merge_stderr` false
  the job's stderr goes to the service's journal (`oneup/service/jobs.py`), and merging it
  would break the XML. Exit 106 keeps the rows and the count. The caller emits
  `CHECK_UNKNOWN|system|sources-unreadable|…` when a message names the repository, and
  `sources-unknown-error|106` when none does, `_check_system`'s existing branch.
- `rc` is 106 when the dry run exited 106, and 0 for every other exit §4.2 accepts.
  `readable` is true.
- `exact` is true.

### 4.4 Sizes and repositories

With `sizes`, `system_changes` calls `pkgsizes.download_sizes` with
`(alias, name, edition, arch)` for every change but a removal. A removal's size is `0`: it
downloads nothing.

`repo` resolves through one `zypper --xmlout repos` call (`parsers.repo_names`), because
§2 could not tell which name the attribute holds:

- a value that is a known alias is that alias, and the row's `repo` is its display name;
- else a value that is the display name of exactly one repository is that repository's
  alias, and the row's `repo` is the value;
- else the alias is unknown, the size is `0`, and the row's `repo` is the value.

A removal's `repo` is `""`: the installed system is not a repository.

### 4.5 The markers

Two trailing optional fields, the change `docs/reference/marker-protocol.md` §5 calls cheap:

```
CHECK|key|count|label[|basis]
CHECK_ITEM|key|name|from|to|bytes|repo[|change]
```

- **`basis`** is the code `at-least`, or absent. `actions._check_system` adds it to
  `CHECK|system|…` when `exact` is false, and `actions.check` adds it to `CHECK|TOTAL|…`
  when the system count carried it. Flatpak and firmware counts are exact and never carry
  it. The terminal line says *"at least N update(s)"* and gives `why`.
- **`change`** is `upgrade`, `downgrade`, `new` or `remove`; absent means `upgrade`. Today's
  rows, the fallback's and Flatpak's, carry none. For `new`, `from` is `""`. For
  `remove`, `from` and `to` are both the removed edition (§4.3) and `bytes` is `0`.

The fallback's `CHECK_ITEM` lines are today's, byte for byte.

### 4.6 The window

- `oneup/gui/run.py::handle_marker`: `CHECK` reads `parts[3]` when present. A row badge with
  basis `at-least` reads *"at least {count} available"*, or *"up to date"* at zero (§3
  item 5). The TOTAL's basis is kept beside `_installed_count` for every place that words
  the total.
- `oneup/gui/tray.py::_parse_tray_line` reads the TOTAL's basis, and `_tooltip` gains
  *"{app} — at least %n update(s) waiting"*. Zero still reads *"up to date"*.
- `oneup/gui/app.py::_headless_check` passes the basis to `markers.check_notification`,
  whose `check.available` notification gains an at-least body.
- `oneup/gui/packages.py`: `Package` gains `change: str = "upgrade"`, and
  `add_check_item` reads `parts[6]` when it is one of the four words. Any other value
  leaves the row out, as a malformed size does (ONEUP-0259 INV-8).
- `oneup/gui/package_views.py::versions`: `new` reads *"new {new}"*; `remove` reads
  *"{old}, to be removed"*; the other two keep *"{old} → {new}"*. A removal sits in "to go"
  until its `PKG|…|removed` moves it to "done", as `package_views.GROUP` already does.

Every new string is translatable (`docs/standards/wording-and-translation.md`), and a
plural one goes through `i18n.counted`.

### 4.7 A run that meets a running check

The service runs one job at a time (ONEUP-0249 INV-9). A check's dry run can hold it for
up to `CHECK_DRY_RUN_SECONDS`, and a run started meanwhile would fail its first root
operation with `Busy`.

So `privilege._service_job`, on `Refused` with code `Busy` and reason `a job is running`,
prints one line — *"Waiting for another OneUp task to finish…"* — and retries every 2 s
for up to `BUSY_WAIT_SECONDS`:

```python
BUSY_WAIT_SECONDS = float(os.environ.get("ONEUP_BUSY_WAIT_SECONDS") or "210")
```

Its default is `CHECK_DRY_RUN_SECONDS`' plus a margin for the dry run's start-up; a change
to one changes the other. Past it, the operation fails as
`Busy` fails today. Any other refusal, `Busy` with reason `the service is stopping`
included, fails as today.

### 4.8 Measured before the code relies on it

Each is one root dry run on the development machine, by hand, at the start of the build.
The design above is safe under every outcome; each measurement decides which branch the
tests pin.

1. **Which name `repository` holds.** `zypper --xmlout install --dry-run --force <a package
   from download.opensuse.org-oss>`, whose alias and display name differ.
2. **A removal's `edition`.** `zypper --xmlout remove --dry-run <an installed leaf
   package>`: the `to-remove` solvable's `edition` against `rpm -q`'s.
3. **What "nothing to do" prints in XML**, on the VM of
   `~/.claude/projects/-mnt-Games-Scripts-Linux-OneUp/memory/vm-test-kit.md` after a full
   update. If it prints no `install-summary`, a fully updated machine takes the fallback
   on every check, and "at least 0" reads "up to date" — correct, but the build then adds
   a branch for zypper's own nothing-to-do message so the count stays exact.

## 5. Correctness invariants

- **INV-1** `--check` invokes `sudo` zero times on either route.
  *Test:* `tests/run-tests.sh`'s existing sentinel scenario, plus an in-process scenario
  that replaces `privilege.sudo_init`, `privilege.root` and `privilege.sudo` with
  functions that fail it, then runs `steps.system_changes` on the service route against
  the `tests/service-test.py --serve` fake service.
  *Breaks when:* `system_changes` reaches root through `privilege.root` or `sudo_init`,
  whose `auto` route falls back to sudo on `challenge`.

- **INV-2** The check opens its session with `interactive` false and `import_keys` false,
  even with `ONEUP_NONINTERACTIVE` unset.
  *Test:* `tests/run-tests.sh`, against `--serve` — the fake polkit records the flags of each
  `CheckAuthorization`; a `--check` run with `ONEUP_NONINTERACTIVE` unset records flags 0.
  The unset environment is what isolates the rule: with it set, today's run path would
  pass the same flags.
  *Breaks when:* the check reuses the run's `interactive` choice.

- **INV-3** `check-dry-run`'s argv is `system-commit`'s with `cdn` false, plus a leading
  `<timeout> <CHECK_DRY_RUN_SECONDS>`, `--xmlout` after `zypper`, and a trailing
  `--dry-run`, on Tumbleweed and on Leap.
  *Test:* `tests/run-tests.sh` — builds both with `rootops.build`, with `steps._is_leap`
  replaced to answer each way, and compares them.
  *Breaks when:* the row builds its own transaction argv instead of deriving it from
  `steps.system_txn_argv`.

- **INV-4** On a dry run that answered, the system count is the number of distinct
  `(name, edition)` package solvables across every element in §4.3's table, and the rows
  carry each one's change word; `CHECK|system` carries no basis.
  *Test:* `tests/parsers-test.py` — a fixture with one distinct package in each of the
  eight elements, one of them named so it fails `valid_package`; a product; and a second
  listing of one of the eight under another element; its `packages-to-change` reads 99.
  `change_list` returns eight changes with the table's words; the count is 8 and the rows
  are 7. The product, the repeat and the 99 isolate the rule: a parser counting
  `<solvable>` tags returns ten.
  *Breaks when:* the count reads `packages-to-change`, or only `to-upgrade`, or counts a
  product.

- **INV-5** A package the check lists as `remove` and the run then removes is one row in
  the window's model, in state `removed`.
  *Test:* `tests/gui-smoke.py` — feeds `CHECK_ITEM|system|foo|1.0-1.1|1.0-1.1|0||remove`
  then `PKG|system|removed|foo|1.0-1.1`; the model holds one `foo`, state `removed`,
  change `remove`.
  *Breaks when:* a removal's `to` is `""`, so the run's line keys a second row.

- **INV-6** Every §4.2 fallback cause still emits today's `CHECK_ITEM` rows, a
  `CHECK|system` count, and the `at-least` basis on it and on `CHECK|TOTAL`, and the check
  exits 0.
  *Test:* `tests/run-tests.sh`, against `--serve` — one scenario per cause: service absent from the bus,
  polkit answering no, a second session holding a job (`Busy`), mock `zypper` exiting 4,
  mock `zypper` printing malformed XML, well-formed XML with no `install-summary`, and a
  summary holding an element not in §4.3's table.
  Each emits the mock `list-updates` count with `at-least`.
  *Breaks when:* a cause emits a zero, emits no `CHECK`, or omits the basis.

- **INV-7** The dry run ends by `CHECK_DRY_RUN_SECONDS`, and the check then takes the
  fallback.
  *Test:* `tests/run-tests.sh` — the `--serve` service started with
  `ONEUP_CHECK_DRY_RUN_SECONDS=1` and a mock `zypper` that sleeps 30 s; the job ends with
  status 124 within 5 s, and the check emits `at-least`.
  *Breaks when:* the argv carries no `timeout`.

- **INV-8** With `ONEUP_BACKEND=sudo`, as on the AppImage, the check never opens the
  system bus.
  *Test:* `tests/run-tests.sh` — the check on the sudo route under an import blocker that
  fails the scenario on any import of `jeepney`, as ONEUP-0249 INV-12's scenario does; it
  completes with `at-least`.
  *Breaks when:* `system_changes` calls `service_client` before asking the route.

- **INV-9** A run's root operation that meets `Busy` with reason `a job is running` waits
  for that job and then runs, up to `BUSY_WAIT_SECONDS`; past it, it fails as before.
  *Test:* `tests/run-tests.sh`, against `--serve` — a second session starts a mock job
  sleeping 3 s, then the engine's `release-lock` runs: with `ONEUP_BUSY_WAIT_SECONDS=10`
  it succeeds after the job ends and prints the waiting line once; with `=1` it fails.
  *Breaks when:* `_service_job` treats `Busy` as an immediate failure.

- **INV-10** The window, the tray and the weekly notification say "at least" for a count
  carrying `at-least`, and "up to date" for a zero, with or without it.
  *Test:* `tests/gui-smoke.py` — `CHECK|system|7|…|at-least` sets the badge to the
  at-least text; `CHECK|TOTAL|7|…|at-least` sets the tray tooltip and
  `check_notification`'s body to theirs; the same with `0` sets "up to date" and no
  notification.
  *Breaks when:* a reader ignores `parts[3]`.

- **INV-11** A `repository` value resolves to an alias by §4.4's order, whether it is the
  alias or the display name.
  *Test:* `tests/run-tests.sh` — a mock `zypper --xmlout repos` with alias `oss`, name
  `Main Repository (OSS)`, and two mock changes naming each form; under `--sizes`, both
  get the fixture `primary.xml` size and the display name.
  *Breaks when:* the lookup assumes either form alone.

- **INV-12** While another live engine holds `run.state`, the check opens no service
  session and emits the fallback with `at-least`.
  *Test:* `tests/run-tests.sh`, against `--serve` — the scenario's `ONEUP_RUN_STATE`
  names the pid of a process started as `bash -c 'exec -a oneup.engine sleep 30'`, whose
  command line `run_state_holder` accepts; the check emits the mock `list-updates` count
  with `at-least`, and the fake service logs no `OpenSession`. A second run with that
  process killed opens a session. The live-versus-dead pair isolates the rule: a stale
  record alone must not stand the check down.
  *Breaks when:* the check asks the service without reading `run.state`, or stands down on
  a record whose pid is dead.

## 6. Failure modes

| What breaks | What happens |
| --- | --- |
| The restrictive polkit profile | `NotAuthorized` `challenge` on every check: the fallback, "at least N". The run still asks, as today |
| Another program holds zypp's lock | zypper exits 7: the fallback. The check never waits for the lock |
| A repository's refresh fails or needs a new key | non-interactive zypper skips it and exits 106: the dry run's rows, plus `CHECK_UNKNOWN`, naming it where a `<message>` does (§4.3) |
| A crawling mirror | `timeout` ends the dry run at `CHECK_DRY_RUN_SECONDS`: the fallback. A run started meanwhile waits up to `BUSY_WAIT_SECONDS` |
| The solver cannot settle without a choice | zypper exits 4 in non-interactive mode: the fallback, and the terminal line names the status. The update will meet the same problem |
| The user starts an update during a check | the run's first root operation waits, with one line saying why (§4.7) |
| A tray or weekly check starts during an update | it stands down: the fallback, "at least N", and no service session (§4.2 step 0) |
| The service dies mid-dry-run | `Read` fails: the fallback |
| The check's process is killed | the dry run finishes or times out in the service, as any job does (ONEUP-0249 INV-5) |
| A future zypper renames an element or the kind attribute | the fallback (§4.3). Never reads as zero |
| While the dry run holds zypp's lock | a `zypper` the user runs by hand reports the lock, for up to `CHECK_DRY_RUN_SECONDS` |

## 7. Tests

- **`tests/parsers-test.py`**: INV-4.
- **`tests/run-tests.sh`**: INV-1, INV-2, INV-3, INV-6, INV-7, INV-8, INV-9, INV-11 and
  INV-12.
  The service-route scenarios run against `tests/service-test.py --serve` with
  `ONEUP_BACKEND=service` on their own command, and their mock `zypper` gains a
  `--xmlout … dup … --dry-run` mode printing a fixture install summary.
- **`tests/gui-smoke.py`**: INV-5 and INV-10.
- **Each new test is seen to fail first**, against the tree before this item.
- **By hand**: §4.8's three measurements before the parser is written; then, on a packaged
  install, one check from the window and one from the tray, each reading the count of
  distinct packages in the XML of a root dry run of the same transaction, run beside it.

## 8. Docs & release

- **`docs/reference/marker-protocol.md`**: §3's rows for `CHECK` and `CHECK_ITEM`, §4.6
  for both fields, and a fourth §5.1 exception approved by the user on 2026-10-23.
- **`docs/standards/security.md`**: §9.5 becomes *"`--check` never authenticates and never
  calls `sudo`. On the service route it asks the service, non-interactively, for the one
  operation `check-dry-run`, and on any refusal it counts as the user"*; its What-checks-this
  row adds INV-1's service scenario.
- **`docs/specs/ONEUP-0259-package-model.md`**: a pointer under §4.3's system check and
  under INV-1, naming this spec's §4.2 for the service route.
- **`docs/specs/ONEUP-0249-system-service.md`**: a pointer under §4.2's table naming this
  spec's §4.1 for `check-dry-run`.
- **`CHANGELOG.md`** `[Unreleased]`: one Fixed line, in the user's words.
- **The translation catalogues**: the new strings of §4.6.

The two spec edits are pointers, so they ride this spec's gate. The two non-spec edits apply
the wording this spec's gate reviewed.

## 9. Alternatives considered (and rejected)

- **Reuse `size-dry-run`.** It prints text, and the text names upgraded packages without
  versions, so the list could not key against the run's rows (ONEUP-0259 §4.1).
- **Count from the text summary line.** It gives the count, not the list §3 item 3 asks for.
- **Mark the floor with `CHECK_UNKNOWN`.** It already means "a source could not be read":
  the window shows "couldn't check" and refuses "up to date", which §3 item 5 rules out for
  the AppImage's ordinary zero.
- **The service stops a check's dry run when its caller leaves.** That contradicts
  ONEUP-0249 INV-5. The argv's own `timeout` bounds it instead, as `repo-refresh`'s does.
- **The check waits on `Busy`.** A run in progress holds the service for many minutes; the
  check's job is to answer now.
- **OneUp's own polkit action for a read-only check.** ONEUP-0249 INV-13: the package ships
  no polkit file.
- **`--no-refresh`.** Faster and quieter; the user chose freshness (§3 item 4).

## 10. Out of scope

- **The run's header count and `queued` list from the dry run** — ONEUP-0335 (d), which
  waits on this item.
- **The phantom package from `Retrieving: x.rpm [done]`** — filed on ONEUP-0335.
- **An exact count on the AppImage** — §3 item 1.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-10-23 | Q1 3 · Q3 1 · Q4 5 — 9 verified, 0 dismissed | all 9 fixed. Two lanes, each holding every question. One Q1 came from building the packet: the check's job runs with stderr apart, so a skipped repository is named only where a `<message>` names it. Both lanes found the engine tests placed in `tests/service-test.py`, which never starts the engine; the unfalsifiable INV-1 and INV-8 breaks-when clauses; the unpinned `rc` of an answered dry run; and the session-cap `Busy` reasons, which `Run` never sends. One lane found the waiting line naming a check for any job, and the unpinned `packages-to-change` in INV-4's fixture. One Q4 came from settling a lane's open question: no test mocks `/etc/os-release`. Four other open questions resolved clean. Root-only measurements are an unrunnable region here |
| 2 | 2026-10-23 | Q2 2 · Q3 2 · Q4 1 — 5 verified, 0 dismissed | 4 fixed, 1 surfaced to the user; the cap for a spec, so this loop's fixes are read by no lane, and implementation reads them. Two lanes, each holding every question; both found that a renamed element or a `kind`/`type` drift gave an exact zero against §6's promise. One lane each found INV-8 overclaiming on the `auto` route, §8 cataloguing the engine's English waiting line, and the log quote cut before its arch change. Surfaced, not fixed: a tray or timer check can land between a run's root operations and refresh repositories as root mid-run; settled from a lane's open question by reading `_tray_check`, which has no run guard. Own-fix share 0 of 5, read as a calm cap. No second share: the gated change was the whole document |
