# ONEUP-0249 — a system service that runs OneUp's root commands

**Status:** Reviewed
**Kind:** feature
**Roadmap:** ONEUP-0249
**Branch:** v2
**Verified at:** `3b2d5cd` — every claim naming a symbol below was resolved against this
tree, not recalled. Every measurement names the command that produced it.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes log

**In one sentence:** On a packaged install, OneUp's root commands are run by a small
system service that asks openSUSE the same permission question Discover asks, so a user
sitting at the computer updates without a password box.

## 1. Goal

On a computer where OneUp was installed as a package (RPM or the OBS repository), a user
at the computer starts an update and no password box appears. Whether they may is decided
by the polkit permission openSUSE already applies to Discover's system updates, so an
administrator who tightens or loosens Discover tightens or loosens OneUp with it. The
engine's logic, its markers and the window are unchanged in behaviour. Only the way a root
command gets run is new. The AppImage keeps today's route.

## 2. Background

### 2.1 How root is reached today

The engine runs as the user and runs each root command through `sudo`. Every such call
goes through `oneup/engine/privilege.py`: `sudo` for a captured or streamed call, and
`sudo_argv` for the transaction passes that `proc.stream_filtered` reads line by line.
`privilege.sudo_init` asks for the password once, up front, and starts a keep-alive.

There are two ways to avoid the password box, and both have costs:

1. **The Passwordless setting** (ONEUP-0023, ONEUP-0092). `actions.grant_auth` installs
   `/etc/sudoers.d/oneup` and the download guard. The rule grants `zypper` with any
   arguments, among others (`actions.auth_cmnds`). `docs/standards/security.md` §5.3
   states the cost plainly: approximately passwordless root.
2. **Nothing else.** Without the drop-in, every run shows sudo's password box.

### 2.2 What the user asked for

The roadmap item records the user's decisions of 2026-10-10. OneUp gets its own root
service, a second service beside PackageKit rather than a replacement. The API is
narrow, with no arbitrary package names or commands. Only authorised users may update. The
design must say how the AppImage gets the service. The user's decisions of 2026-10-14 are
§3.

### 2.3 What prior art teaches

Each lesson below shaped a clause in §4.

- **A shipped polkit rule that grants a group is itself a vulnerability.** openSUSE fixed
  CVE-2018-1106 by removing a rule that let `wheel` install packages without the root
  password. The polkit(8) manual says packages "must never include any authorization
  rules". Source: https://www.suse.com/security/cve/CVE-2018-1106.html,
  https://polkit.pages.freedesktop.org/polkit/polkit.8.html
- **Identify the caller by its bus name, and deny on any error.** CVE-2013-4288 was a
  race in the pid-based subject. CVE-2021-3560 treated a caller who disconnected
  mid-check as root. Source: https://bugzilla.redhat.com/show_bug.cgi?id=1002375,
  https://github.blog/security/vulnerability-research/privilege-escalation-polkit-root-on-linux-with-bug/
- **Accept no configuration or paths from a client.** dnf5daemon's CVE-2024-1929 and
  CVE-2024-2746 let a client set `pluginpath` and then `reposdir`. Source:
  https://openwall.com/lists/oss-security/2024/03/04/2,
  https://openwall.com/lists/oss-security/2024/04/03/5
- **Cap concurrent requests.** dnf5daemon's CVE-2024-1930 was unlimited sessions. Same
  source.
- **Run exactly what was authorised.** PackageKit's CVE-2026-41651 changed a
  transaction's flags after the check. Source:
  https://github.com/PackageKit/PackageKit/security/advisories/GHSA-f55j-vvr9-69xv
- **Do not install system D-Bus or polkit files from outside the package system.**
  openSUSE removed Deepin from Tumbleweed for doing so. Source:
  https://security.opensuse.org/2025/05/07/deepin-desktop-removal.html

### 2.4 Discover's permission on this machine

Read from `/usr/etc/polkit-default-privs/profiles/standard` on the development machine
(polkit-default-privs 1550+20261009), with
`grep -h -E "packagekit|Flatpak" /usr/etc/polkit-default-privs/profiles/standard`:

```
org.freedesktop.packagekit.system-update             auth_admin_keep:auth_admin_keep:yes
org.freedesktop.packagekit.system-trust-signing-key  auth_admin
```

The three fields are: any session, an inactive session, the active local session. So
someone at the computer may update without a password. A remote or background session
needs the administrator password. Accepting a signing key always needs it.

## 3. Scope decisions (agreed with the user)

1. **Who may update: Discover's rule.** Decided by the user on 2026-10-14. It replaced
   their earlier choice that day of an approved `oneup` group. The service asks polkit
   about `org.freedesktop.packagekit.system-update`, the action Discover's system updates
   use. OneUp ships no polkit rule and no polkit action of its own.
2. **One rule for the whole run.** Decided by the user on 2026-10-14. Flatpak updates for
   everyone and leftover-package removal have no exact Discover match. Discover's nearest
   actions on openSUSE (`org.freedesktop.Flatpak.app-update`,
   `org.freedesktop.packagekit.package-remove`) ask for the password. The user chose the
   system-update rule for every step of a run. Accepting a signing key keeps
   `system-trust-signing-key`, which always asks.
3. **The AppImage keeps today's route.** Decided by the user on 2026-10-14. It never uses
   the service and keeps `sudo` and the Passwordless setting (§2.3, last bullet).
4. **The service replaces the Passwordless setting where it is installed.** Decided by the
   user on 2026-10-14. On a packaged install, the setting's switch is replaced by a line
   saying updates follow the computer's software-update permission. The window offers to
   remove an old drop-in once.
5. **No background refresh of the update lists in this item.** Decided by the user on
   2026-10-14. It is a separate roadmap item.
6. **A second service beside PackageKit, stopping it before a transaction as the engine
   does today.** Decided by the user on 2026-10-10 (roadmap item body).

## 4. Design

### 4.1 The shape: the engine stays the user's, root commands go to the service

The engine keeps running as the user, exactly as now. Its logic, its parsers, its log,
its state files and its markers stay on the user's side. Only the commands it runs as
root change route. Instead of `sudo <argv>`, the engine asks the service to run a named
operation, and the service builds the command itself.

```
window ──QProcess──▶ engine (user) ──D-Bus──▶ oneup-service (root) ──▶ zypper, snapper, …
                         │                         │
                         │◀── output bytes, exit ──┘
                         └─▶ markers, log, run.state (user side, unchanged)
```

Three properties follow, and each is load-bearing:

1. **Network data is never parsed as root.** zypper's output is read by the user-side
   engine, as now. The threat model in `docs/standards/security.md` says "The attacker is
   the data, not the person." The service relays bytes; it does not interpret them, with
   one bounded exception: `orphans-remove`'s validator reads zypper's list of unneeded
   packages with `steps._package_column` (§4.2), which refuses an unreadable name.
2. **`docs/standards/security.md` §7.2 holds unchanged.** The engine is never root in its
   entirety, and the service never takes a path from the engine.
3. **The marker stream cannot change.** The engine emits it, and the engine's logic is
   untouched. The window cannot tell which route ran a command.

### 4.2 One table of root operations, shared by both routes

A new module, `oneup/engine/rootops.py`, holds the only definition of every root command
the engine runs. Each entry is a name, the typed arguments it accepts, a validator for
each, and a function that builds the argv. It imports only the standard library and
engine siblings.

Both routes build their argv from it. The sudo route prefixes `sudo`. The service runs the
argv itself. **So the two routes cannot drift**, the same property ONEUP-0092 INV-3 gives
the drop-in. One operation differs by route: on the sudo route, `system-download` keeps the argv
`steps._download_pass` builds today, the guard or the stop wrapper around
`system_txn_argv()`, because there the engine cannot signal a root child. Its table row is
the service route's. `timeout` and `du` are the absolute paths today's call sites resolve
(`privilege.REFRESH_SUDO_ARGV`, `privilege.CACHE_DU_ARGV`), because the drop-in grants
those paths.

The table (the argv column is what the builder returns, before any `sudo`):

| Operation | Arguments | argv |
| --- | --- | --- |
| `size-dry-run` | `cdn: b` | `env LC_ALL=C` + `steps.system_txn_argv()` + `--dry-run` |
| `system-download` | `cdn: b` | `env LC_ALL=C` + the transaction argv + `--download-only`. Stoppable (§4.6) |
| `system-commit` | `cdn: b` | `env LC_ALL=C` + the transaction argv. Never stoppable |
| `repo-refresh` | `alias: s`, `import_keys: b`, `budget: u` | `timeout <budget> zypper --non-interactive [--gpg-auto-import-keys] refresh <alias>` |
| `repo-refresh-all` | `import_keys: b` | `zypper --non-interactive [--gpg-auto-import-keys] refresh`, with no `timeout`, as `repos.refresh_repos`'s fallback runs it |
| `repo-disable` | `alias: s` | `zypper --non-interactive modifyrepo --disable <alias>` |
| `repo-enable` | `alias: s` | `zypper --non-interactive modifyrepo --enable <alias>` |
| `release-lock` | none | `systemctl stop packagekit` |
| `snapshot-create` | none | `snapper create --description "OneUp pre-update <date>" --cleanup-algorithm number --print-number` |
| `snapshot-list` | `csv: b` | `snapper --no-headers list`, or the `--machine-readable csv` form `__main__._pre_update_snapshot` uses |
| `snapshot-thin` | `algorithm: s` | `snapper cleanup <algorithm>` |
| `restart-list` | none | `zypper ps -sss` |
| `flatpak-system-update` | none | `flatpak update --system -y` |
| `flatpak-system-unused` | none | `flatpak uninstall --system --unused -y` |
| `orphans-unneeded` | none | `zypper --non-interactive --no-refresh packages --unneeded` |
| `orphans-orphaned` | none | `zypper --non-interactive --no-refresh packages --orphaned` |
| `orphans-remove` | `names: as` | `zypper --non-interactive remove --clean-deps <names>` |
| `cache-clean` | none | `zypper --non-interactive clean` |
| `cache-size` | none | `du -sB1 /var/cache/zypp` |

The argv column restates the argvs the engine runs today, which
`steps`, `repos`, `actions` and `__main__` build at their call sites. Where a row and the
call site disagree when this is built, the call site is the truth and the row is
corrected (§8). The sudo route's calls that are about sudo itself stay outside the table:
`sudo_init`'s validate, the keep-alive, `actions.auth_current`'s probe, and
`actions.grant_auth` / `revoke_auth`.

**Validators.** Every one fails closed (`security.md` §4.2):

- `alias` must pass `repos.valid_alias`, and must name a repository in
  `/etc/zypp/repos.d` when the service reads it. `repo-enable` also requires that this
  session disabled that alias (§4.5). So the service can never enable a repository an
  administrator turned off.
- `budget` is a positive integer, the same digits-only shape the drop-in pins it to.
- `algorithm` is `number` or `timeline`.
- `names` is non-empty. Each name must be in the set the service itself just computed by
  running `orphans-unneeded`, read with the engine's own parser. So a client can only
  remove what zypper already calls unneeded.
- `cdn` makes the service build the CDN repository directory itself, with
  `repos.make_cdn_reposd`, in its own private `/tmp`. **No operation takes a path.**
- An unknown operation, an unknown argument key, or a missing or wrong-typed argument is
  refused.

`<date>` in `snapshot-create` is the service's own clock. The engine passes no text.

### 4.3 The D-Bus interface

Bus name `za.co.antsprojectshub.OneUp1` on the system bus, object
`/za/co/antsprojectshub/OneUp1`, interface `za.co.antsprojectshub.OneUp1`. The `1` is
the interface version. An incompatible change takes a new name.

```
OpenSession(options a{sv}) -> ()
    options: interactive b (default true), import_keys b (default false)
Run(op s, args a{sv}, merge_stderr b) -> ()
Read(offset t) -> (data ay, status i)   # status -1 until offset is at the end of an ended job
Stop() -> ()
CloseSession() -> ()
CanUpdate() -> (answer s)          # "yes" | "no"; never prompts
Version  property u = 1
```

Errors are `za.co.antsprojectshub.OneUp1.Error.NotAuthorized`, `.Busy`, `.Invalid`,
`.NoSession` and `.NotStoppable`.

- **A session belongs to one caller's unique bus name.** A unique name is never reused,
  so the session dies with the caller's connection. The service watches
  `NameOwnerChanged` and ends the session when its owner leaves.
- **No message carries a file descriptor.** The client pulls the job's output with
  `Read`. Measured 2026-10-16 on the development machine (§9): with SELinux enforcing,
  a descriptor in the service's reply makes `dbus-broker` disconnect the service.
- **`Read(offset)` returns the job's output from byte `offset` on.** That is the child's
  stdout, and its stderr too when `merge_stderr` is true, in one ordered stream, as
  `proc.run`'s `merge_stderr` gives today. Unmerged stderr goes to the service's journal.
  The bytes are raw, with no line splitting, at most 64 KiB per reply. The client
  advances `offset` by the length of each `data`, so a repeated `Read` is harmless.
- **`Read` answers as soon as there is something to say**: bytes past `offset`, or the
  job's end. With neither, it answers with empty `data` after at most 1 second. So a
  chunk reaches the client about as soon as the child writes it, unsplit, as a pipe
  would deliver it (`.claude/rules/engine-traps.md`, "A slow server").
- **`status` is -1 until the job has ended and `offset` is at the end of its output.**
  So a reply carrying bytes always has `status` -1, and the reply with the final
  `status` carries no bytes. That `status` is the exit status, or `128+N` for a child killed by signal `N`, the shell's
  convention the engine already reads (143 is a stopped download).
- **`Read` reads the caller's own session's job**, so no session can read another's. A
  caller with no session gets `NoSession`. A session with no job of its own gets
  `Invalid`, and so does an `offset` past the end of the output.
- **The client treats a failed `Read` as a failed job**, status 1, as it does a refused
  `Run`. That covers a service that died mid-job (§6).
- **The child writes to a file, never to a pipe.** Its output goes to a job file in the
  service's runtime directory, `/run/oneup/`, and `Read` reads that file. A child writing
  to a pipe whose reader vanished dies of `SIGPIPE` mid-`zypper dup`, the shape of the
  first engine trap. With a file, neither the client leaving nor the service dying can
  reach the child.
- **The job file is deleted** when the job has ended and either its session has ended or
  its session starts another `Run`. Until then a repeated `Read` at the end returns the
  same `status`. A service that
  starts deletes any job file an earlier instance left; a child still writing to it is
  unaffected, because an unlinked file stays writable.
- **`CanUpdate` answers the non-interactive question** (§4.4), so `--auth-status` reports
  what an automatic update would actually get.

The D-Bus library is `jeepney`, on both sides (§9). It is pure Python, gives the
sender's unique name on every message. Neither side enables descriptor passing on its
connection, so a descriptor sent by mistake fails on the sender's side. It is packaged as
`python313-jeepney` on Tumbleweed and Leap 16.0. The development machine has 0.9.0
(`python3 -c "import jeepney; print(jeepney.__version__)"` → `0.9.0`).

### 4.4 Who may: the polkit check

`OpenSession` decides, once, and nothing else does:

1. The subject is the caller's unique bus name, as a `system-bus-name` subject.
2. The action is `org.freedesktop.packagekit.system-update`, with empty details.
3. With `interactive` true, the flag `AllowUserInteraction` is set, so polkit's agent may
   ask a remote or background user for the administrator password. That is one box, at
   the start of the run. A caller with no polkit agent, such as an SSH shell, cannot be
   asked: polkit answers with a challenge it could not put, and §4.7 sends that caller
   to the sudo route.
4. With `interactive` false, no flag is set, so polkit never puts a box on the screen for
   a run nobody started by hand. The engine sends `interactive` false exactly when its
   environment carries `ONEUP_NONINTERACTIVE=1`. `oneup/gui/app.py::_headless_engine` sets
   no environment today; it is changed to set that variable for every headless check and
   update, which the timer's `ExecStart` reaches.
5. With `import_keys` true, the service also requires
   `org.freedesktop.packagekit.system-trust-signing-key`, under the same flag rule.
6. **Any error is a refusal**: polkit unreachable, the action not registered, the
   caller's uid unresolvable, or the caller gone. `NotAuthorized` carries a short reason
   code, never a path: `dismissed` when polkit reports the user dismissed its box,
   `challenge` when it wanted to ask and could not, and `denied` otherwise.

**A timer's process gets the same answer as the desktop.** Measured on the development
machine (polkit 127): a process under `user@1000.service`, started with `systemd-run
--user`, checked with `pkcheck --action-id org.freedesktop.packagekit.system-update
--process` → `polkit\56result=yes`, exit 0, while the user's Wayland session was active.
polkit places such a process in the user's display session. So an automatic update is
allowed exactly when Discover's rule allows the user at the desk, and the service adds no
rule of its own.

A session records what was authorised: `import_keys` and the caller's uid. `Run` refuses
either refresh operation with `import_keys` true in a session not opened with it. Nothing a client
sends after `OpenSession` widens a session (§2.3, PackageKit's CVE-2026-41651).

### 4.5 Sessions, jobs and caps

- **At most one session per caller**, and at most 8 sessions in total. A second
  `OpenSession` from the same caller, or a ninth overall, gets `Busy`.
- **At most one running job in the whole service.** zypp's lock allows no more anyway.
  `Run` while any job runs gets `Busy`. A job that has ended no longer counts, even while
  its output waits to be read.
- **A session's repository changes are undone when it ends.** The service records each
  alias a session disabled. On `CloseSession`, or when the caller leaves the bus, it
  re-enables each one this session disabled and has not re-enabled. That closes a gap in
  today's route, where an engine killed with `SIGKILL` never runs `repos.restore_disabled`.
- **A session's CDN directory is deleted when it ends.** The commit after a download
  recovery reuses it, so it lives for the session.
- **A job outlives its session, and so does the session's clean-up.** A running job is
  never stopped because its caller left (§4.6). The two clean-ups above run once no job
  is running in the service: a re-enable cannot take zypp's lock while a job holds it,
  and a running commit may be reading the CDN directory.
- **Argument limits.** `names` at most 5000 entries; each string at most 255 bytes.
  Anything larger is `Invalid`.

### 4.6 Stopping, and what is never stopped

- **`system-download` is the one stoppable operation.** `Stop` sends `SIGTERM` to that
  child, which zypper turns into exit 105, as the inline wrapper's own `kill -TERM` does
  today. The engine's 105-means-stopped rule in `steps._download_status` is unchanged.
- **`Stop` on any other job is `NotStoppable`.** `system-commit` is never signalled
  (`security.md` §6.1). `Stop` from any session but the one that started the job is
  `NoSession`.
- **The engine forwards the user's Stop.** The service cannot read `stop.request`: it is
  in the user's home, and the unit hides home directories (§4.8). So on the service
  route, while `system-download` runs, the engine polls `proc.stop_requested` every
  `STOP_POLL_SECONDS` and calls `Stop` once. The stop wrapper and the download guard text
  are untouched; the service route simply does not use them.
- **Bounded calls stay bounded the way they are today.** `repo-refresh` carries its own
  `timeout`, and `repo-refresh-all` carries none, as today. The service adds no other
  deadline, because each of the rest is bounded by
  zypper's or snapper's own behaviour today, and a new deadline on a root child would be
  a new way to kill one.

### 4.7 Which route the engine takes

`privilege.py` chooses once per run, before the first root command, by calling
`oneup/engine/route.py::engine_route(environ)`, a standard-library function returning
`sudo` or `service` from this table:

| Condition | Route |
| --- | --- |
| `ONEUP_BACKEND=sudo` | sudo |
| `ONEUP_BACKEND=service` | service, or the run fails if it is unreachable |
| unset or `auto`, the activation file `/usr/share/dbus-1/system-services/za.co.antsprojectshub.OneUp1.service` exists, and `jeepney` imports | service |
| otherwise | sudo |

- **The AppImage always sets `ONEUP_BACKEND=sudo`.** `oneup/gui/paths.py`
  `_resolve_engine`'s frozen branch adds it to the env prefix it already builds.
- **Falling back to sudo happens only on the `auto` route, and only interactively.** It
  happens when the session cannot open for a transport reason (the service missing from
  the bus, or a D-Bus error that is not `NotAuthorized`), or on `NotAuthorized` with
  reason `challenge` (a caller polkit had no agent to ask, §4.4). The engine writes one
  line saying so and continues on the sudo route, which asks on the terminal or through
  askpass as today: one password box, never a failed run.
- **Everything else ends the run without a box.** `ONEUP_BACKEND=service` never falls
  back. `NotAuthorized` with reason `dismissed` or `denied` ends the run as a cancelled
  `sudo_init` does today. Without interaction there is nobody to answer a box, so any
  failure to open a session makes an automatic update stand down.
- **No route switch mid-run.** If the service fails after the session opened, the
  operation returns a failure status and the step fails in the ordinary way.

`sudo_init` on the service route opens the session, or reuses the one this engine already
holds, and starts no keep-alive.
`actions.auth_status` on the service route emits `@@AUTH@@|on` when `CanUpdate` answers
`yes`, and `@@AUTH@@|off` otherwise. The marker and its two values are unchanged.

### 4.8 The service process and its unit

`oneup/service/` is a new package. It is started by `/usr/libexec/oneup-service`, a
script run with `python3 -I` that puts `/usr/share/oneup` first on `sys.path` and then
imports `oneup.service`. `-I` means the environment and the user's site-packages cannot
change what it imports. `-I` alone cannot find the package: measured, `python3 -I -m
oneup` run from a directory holding `oneup/` prints `No module named oneup`, because
`-I` leaves the current directory off `sys.path`. The service imports `oneup/engine/`
modules, `steps` and `parsers` among them (`steps._package_column` is the orphans parser),
and nothing from `oneup/gui/`.

Files the RPM installs:

```
/usr/share/dbus-1/system.d/za.co.antsprojectshub.OneUp1.conf
    root may own the name; anyone may send to it, interface by interface
/usr/share/dbus-1/system-services/za.co.antsprojectshub.OneUp1.service
    [D-BUS Service] Name=… Exec=/bin/false User=root SystemdService=oneup-service.service
/usr/lib/systemd/system/oneup-service.service
    Type=dbus, BusName=za.co.antsprojectshub.OneUp1, ExecStart=/usr/libexec/oneup-service,
    no [Install] section
/usr/libexec/oneup-service
    the launcher above
```

The unit starts with this hardening. Each directive stays only if a real Tumbleweed
update that includes a kernel passes under it (§7):

```
ProtectHome=yes  PrivateTmp=yes  ProtectClock=yes  ProtectHostname=yes
ProtectKernelLogs=yes  ProtectControlGroups=yes  RestrictRealtime=yes
LockPersonality=yes  SystemCallArchitectures=native
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK
KillMode=process  TimeoutStopSec=30min
RuntimeDirectory=oneup  RuntimeDirectoryPreserve=yes
```

These are left out on purpose, because each would break a package transaction:
`ProtectSystem=`, `ProtectKernelModules=`, `RestrictSUIDSGID=`, `PrivateDevices=` and
`ProtectKernelTunables=`. systemd.exec(5) itself excludes services "involved with system
updates" from `ProtectSystem`.

- **`KillMode=process`** means that if the service dies or is stopped, systemd does not
  kill the zypper it started, and the job file (§4.3) means the child has nothing that
  dies with the service. `RuntimeDirectory=oneup` with `RuntimeDirectoryPreserve=yes`
  keeps `/run/oneup/` across a restart. A killed service must never become a killed
  transaction.
- **Idle exit.** With no session and no job for 60 seconds, the service releases its bus
  name and exits. D-Bus starts it again on the next call.
- **On `SIGTERM`** it refuses new sessions, and `Run` gets `Busy`. A session whose job's
  final `status` has not yet been returned stays open until a `Read` returns it, so a
  running job's output stays readable (§4.3). Every other session ends at once. It exits
  when no session is left, so a stop waits for the running job, never for a whole run.
- **The RPM never restarts it on upgrade.** The service may be the very thing running the
  zypper that upgrades OneUp. The `%postun` uses `%service_del_postun_without_restart`.
  The next start after idle exit loads the new code.
- **The environment is the unit's.** The service reads no environment variable that a
  client could set, because a client sets none. Test-only overrides are read from the
  service's own environment, which only the unit or a test harness sets.

### 4.9 Audit

The service writes one line to its journal for each of these:

- a session opened, with the caller's uid, user name and unique name;
- a session refused, with the same and the reason code;
- a job started, with uid, operation and arguments;
- a job ended, with its status;
- a session ended, with any repository it re-enabled.

`journalctl -u oneup-service` answers "who updated this computer, and when".

### 4.10 The window

- **The Passwordless switch** (`oneup/gui/auth.py`). When the service route is the one the
  engine would take, the switch is replaced by one line saying updates follow this
  computer's software-update permission, the same as Discover's. The window answers that
  with the engine's own `engine_route` (§4.7), called with the environment
  `_resolve_engine` gives the engine. The frozen window imports it like any other module,
  so PyInstaller bundles it. So the frozen build, whose engine environment holds
  `ONEUP_BACKEND=sudo`, keeps the switch even on a computer that also has the RPM.
- **An old drop-in.** On a service install, the window offers once to remove the old
  setting when a guard exists at either path `actions.revoke_auth` removes
  (`/usr/libexec/oneup-download-guard`, `/usr/lib/oneup-download-guard`), or when
  `sudo -n -l <zypper>` succeeds, which also finds a drop-in older than the guard.
  `/etc/sudoers.d` itself is not readable by users. Removing runs today's
  `--revoke-auth` with `ONEUP_BACKEND=sudo`: one administrator password box.
- **Automatic updates keep their coupling** (ONEUP-0092 §4.7). They are offered only
  while `@@AUTH@@|on`, and on the service route that means `CanUpdate` says `yes`.

### 4.11 Packaging

- **RPM** (`packaging/rpm/oneup.spec`): installs §4.8's four files and `oneup/service/`.
  It adds `Requires: python3-jeepney` and `Requires: dbus-1`. It ships no polkit file of
  any kind.
- **OBS**: the home project builds as now. openSUSE's rpmlint reports the D-Bus files as
  `dbus-file-unauthorized`. That is not fatal outside openSUSE:Factory, where only the
  `rpmlint-strict` flavour fails the build. Getting into Factory would need a SUSE
  security review, which is out of scope (§10).
- **AppImage**: unchanged. It does not bundle `oneup/service/`.

### 4.12 Measured before the code relies on it

Four facts the design leans on have not been measured. Each is measured first, and a
result that contradicts the design is a fold-back to this spec, not a workaround in code:

1. **polkit answers `challenge`, not `dismissed`, for a caller with no agent.** §4.7's
   sudo fallback for an SSH run leans on telling the two apart. Measure with the
   service's own call from an SSH session.
2. **A real Tumbleweed `dup` with a kernel update succeeds under the §4.8 unit.** Measure
   with each directive in, and drop any that fails.
3. **PackageKit started by Discover mid-run waits on zypp's lock.** Measure by opening
   Discover during a real run's commit.
4. **`Run` and `Read` work on the real system bus with SELinux enforcing.** No test
   reaches it: `tests/service-test.py` runs a private bus with no SELinux, which is how
   the descriptor design passed its tests and failed its first real run (§9). Measure
   with a read-only operation, `restart-list`, through `oneup/engine/service_client.py`
   on a packaged install.

## 5. Correctness invariants

- **INV-1** The service runs no command that is not built by `oneup/engine/rootops.py`
  from an operation in its table and arguments that passed that operation's validators.
  An unknown operation, an unknown argument, or a failed validation starts no child.
  *Test:* `tests/service-test.py` sends a bogus operation, an extra argument, an alias
  with a space and a path-shaped `alias`. Each must return `Invalid` and leave the mock
  binaries' call log empty.
  *Breaks when:* the service accepts an argv, a path or a free-form flag from a client.
  The fixture isolates the validator, because the session is open and no job is running.

- **INV-2** No operation runs without a session, and a session opens only when polkit
  answers `yes` for `org.freedesktop.packagekit.system-update` under §4.4's rules.
  *Test:* `tests/service-test.py`, with a fake polkit on a private bus answering `yes`,
  `no`, `challenge`, a dismissed box and an error in turn. Only `yes` opens a session, and
  each refusal carries the reason code §4.4 step 6 names. `Run` with no session is
  `NoSession`.
  *Breaks when:* the check is skipped, cached past its session, or an error reads as
  success (CVE-2021-3560's shape).

- **INV-3** A session opened without `import_keys` cannot run either refresh operation
  with `import_keys` true, and opening with it requires the signing-key action too.
  *Test:* `tests/service-test.py`, a fake polkit that allows system-update and refuses
  the signing-key action.
  *Breaks when:* a session's authorisation can be widened after `OpenSession`.

- **INV-4** For every operation but `system-download`, built with `cdn` false, the sudo
  route's argv, after `sudo` and sudo's own flags, equals the service's argv.
  `system-download`'s sudo route stays exactly what `steps._download_pass` builds today
  (§4.2).
  *Test:* `tests/run-tests.sh`, a structural scenario that builds each table entry with
  fixed arguments through both routes and compares.
  *Breaks when:* a call site builds its own argv instead of using the table, so the two
  routes run different commands.

- **INV-5** A job is never stopped by its caller leaving or by the service dying, and
  `system-commit` is never signalled.
  *Test:* `tests/service-test.py` starts a mock commit that sleeps then writes a done
  file, kills the client, and asserts the done file appears. A second run kills the
  service instead. `Stop` during that job is `NotStoppable`.
  *Breaks when:* the child writes to a pipe that dies with the client or the service and
  takes `SIGPIPE`, or `Stop` reaches a commit.

- **INV-6** `repo-enable` succeeds only for an alias this session disabled, and ending a
  session re-enables every alias it disabled and has not re-enabled.
  *Test:* `tests/service-test.py` enables an alias the session never disabled (`Invalid`).
  Then it disables one and drops the connection, and asserts the mock `zypper` log shows
  the re-enable.
  *Breaks when:* a client can enable a repository an administrator disabled, or a killed
  engine leaves a repository off.

- **INV-7** `orphans-remove` runs only when every name is in the set the service computed
  from `orphans-unneeded` in the same call.
  *Test:* `tests/service-test.py`, with a mock `zypper` listing two unneeded packages. A
  request naming a third is `Invalid`, and no removal appears in the call log.
  *Breaks when:* the service trusts the client's list of names.

- **INV-8** On the service route, a full run issues no `sudo` at all and emits the same
  marker stream as the same scenario on the sudo route.
  *Test:* `tests/run-tests.sh`, one scenario run on both routes against the same mocks.
  The sudo mock's call count is zero on the service route, and the two marker streams
  are equal.
  *Breaks when:* any root call bypasses `privilege`'s route choice, or the service route
  changes what the engine prints.

- **INV-9** At most one job runs in the service, at most one session exists per caller,
  and at most 8 sessions exist.
  *Test:* `tests/service-test.py` opens a second session from one connection, and nine
  from nine connections, and starts a second `Run` during a sleeping mock job. Each extra
  is `Busy`.
  *Breaks when:* a cap is missing or counts the wrong thing.

- **INV-10** The AppImage's engine always takes the sudo route.
  *Test:* `tests/gui-smoke.py` checks that `_resolve_engine`'s frozen branch puts
  `ONEUP_BACKEND=sudo` in the argv it returns.
  *Breaks when:* a frozen build reaches for a service whose version it does not match.

- **INV-11** `@@AUTH@@|on` on the service route means `CanUpdate` returned `yes` just now.
  *Test:* `tests/run-tests.sh`, `--auth-status` against a fake service answering `yes`,
  then `no`.
  *Breaks when:* the status reports that the service exists rather than that it would
  allow an update.

- **INV-12** The engine on the sudo route runs with `jeepney` absent.
  *Test:* `tests/run-tests.sh` runs one sudo-route scenario with an import blocker on the
  path that makes `import jeepney` fail.
  *Breaks when:* a module imports `jeepney` at the top level, which would break the
  AppImage's copied-out engine on a machine without it.

- **INV-13** The package ships no polkit file, and the service's unit has no `[Install]`
  section and sets `KillMode=process`.
  *Test:* `tests/run-tests.sh`, a structural check over `packaging/rpm/oneup.spec` and
  the unit file.
  *Breaks when:* someone adds a convenience `.rules` file (CVE-2018-1106's shape), or an
  install-time enable, or lets systemd kill the transaction with the service.

- **INV-14** Every session opened or refused, and every job started and ended, writes one
  audit line.
  *Test:* `tests/service-test.py` reads the service's stdout, which is the journal under
  systemd, after an allowed and a refused session.
  *Breaks when:* a refusal or a job end leaves no trace.

- **INV-15** With no session and no job for the idle period, the service exits.
  *Test:* `tests/service-test.py` with the idle period set to 2 seconds through the
  service's own environment.
  *Breaks when:* the service lingers as root for no one.

- **INV-16** A headless run opens its session with `interactive` false, and a run started
  by hand opens it with `interactive` true.
  *Test:* `tests/gui-smoke.py` checks that `_headless_engine` passes
  `ONEUP_NONINTERACTIVE=1` in the engine's environment; `tests/run-tests.sh` checks, against
  the fake service, that the engine sends `interactive` false with that variable and true
  without it.
  *Breaks when:* the variable is not set, so polkit may put a box on screen for a timer
  run, or the engine ignores it.

- **INV-17** A job's output and status reach the client only through `Read`, byte for
  byte, and only the session that started the job may read it. No message the service
  sends carries a file descriptor.
  *Test:* `tests/service-test.py` runs a mock that writes a chunk with no line ending,
  sleeps, writes more, then exits 3. The bytes `Read` returns, joined, equal what the
  mock wrote, and the first chunk arrives before the mock exits. The final `status` is 3,
  and 143 for a mock killed by `SIGTERM`; a second `Read` at the end returns the same
  `status`. A `Read` from a connection with no session is `NoSession`, and from a second
  session with no job of its own `Invalid`. The service's introspection shows no `h` in
  any signature, and no `open_dbus_connection` call in `oneup/service/` or
  `oneup/engine/service_client.py` passes `enable_fds=True`.
  *Breaks when:* the reply carries a descriptor again, which a private bus without
  SELinux accepts (§4.12 item 4); or `Read` holds a chunk back until a line ends;
  or another caller can read a job's output.

## 6. Failure modes

| What breaks | What happens |
| --- | --- |
| The service is not installed, or `jeepney` is missing | `auto` takes the sudo route. Nothing changes from today |
| The bus call fails before the session opens | interactively on the `auto` route: one line, then the sudo route. Otherwise the run ends, or an automatic update stands down (§4.7) |
| polkit refuses, interactively | `dismissed` or `denied`: the run ends as a cancelled `sudo_init` does today. `challenge`, a caller with no agent: the sudo route (§4.7) |
| polkit refuses, non-interactively | an automatic update stands down, as it does today when Passwordless is off |
| PackageKit's policy file is absent | polkit reports the action unregistered, which is a refusal. The window's line then reads not allowed, and the user can still use `ONEUP_BACKEND=sudo` |
| The service dies mid-job | `KillMode=process` and the job file (§4.3) leave zypper running. The engine's next `Read` fails, with no reply or with `NoSession` from a restarted service; the engine treats that as failure, and the step fails. The journal has the job-start line and no end line |
| The window quits mid-run | unchanged: the engine survives it. If the engine also dies, the service finishes the job and re-enables the session's repositories |
| Another program holds the zypp lock | unchanged: `release-lock`, then the engine's existing `repos.lock_holder` check |
| Discover starts PackageKit mid-run | PackageKit waits on zypp's lock, which zypper holds for the transaction. Measured as §4.12 item 3 |
| OneUp upgrades itself mid-run | the running service and engine keep the code they loaded. The RPM does not restart the service (§4.8) |

## 7. Tests

- **`tests/service-test.py`** (new): starts a private `dbus-daemon`, a fake polkit
  authority on that bus, and the service with mock binaries on its `PATH`. It needs no
  root, because the mocks only log their argv. It locks INV-1, INV-2, INV-3, INV-5,
  INV-6, INV-7, INV-9, INV-14, INV-15 and INV-17. It joins `./local-CI.sh`. It exits 77
  (skipped) when `dbus-daemon` or `jeepney` is missing, like `tests/gui-smoke.py`
  without PySide6.
- **`tests/run-tests.sh`**: new scenarios for INV-4, INV-8, INV-11, INV-12, INV-13 and
  INV-16's engine half.
  INV-8's service-route arm runs the engine against the same fake service.
- **`tests/gui-smoke.py`**: INV-10, and INV-16's window half.
- **The existing ONEUP-0092 and ONEUP-0044 scenarios keep running on the sudo route.**
  They are the AppImage's contract, and nothing in this item retires them.
- **Each new test is seen to fail first**: against the tree before the feature for
  INV-4, INV-8 and INV-10, and against a deliberately broken service for the rest.
- **By hand**, before 2.0.0: §4.12's four measurements, then one real run from the window
  on a packaged install with no password box, and one from an SSH session, which takes
  the sudo route and its password request (§4.7).

## 8. Docs & release

Each of these is amended in the commit that lands the matching code:

- **`docs/design/oneup-2.0.md`**: §1 gains ONEUP-0249, and §3 item 4 gains the service as
  the packaged install's root half. This amendment is gated by `review-contract` before
  any code is built.
- **`docs/standards/security.md`**: §1.2 (the service runs root commands for the engine),
  §2 (one authentication per run: one polkit check, or one sudo validate), §5 (the drop-in
  is the AppImage's route), and a new section for the service's rules (§4.4 to §4.9 here).
- **`docs/reference/marker-protocol.md`**: no marker changes. §8's state files are
  unchanged.
- **`docs/standards/files-and-naming.md`**: `ONEUP_BACKEND`, `ONEUP_NONINTERACTIVE`, and
  the service's test overrides.
- **`docs/standards/dependencies.md`**: a row for `jeepney`.
- **`CLAUDE.md`** §4 and `.claude/rules/engine-traps.md`: the second route. The trap
  about a privileged call without a drop-in entry now also reads "or without a
  `rootops` entry".
- **`README.md`** and **CHANGELOG**: what a packaged install now does about passwords, in
  plain words.
- **If a §4.2 row disagrees with its call site**, the row is corrected in this spec as a
  Step 8 fold-back, with an implementation row in §11.

## 9. Alternatives considered (and rejected)

- **Run the whole engine as root inside the service.** Smaller change to the engine, but
  every parser would read network data as root, the log would need a root-side writer,
  and user-scope Flatpak would need a privilege drop back to the user. Rejected for the
  first reason alone: the threat model's attacker is the data.
- **Accept argv from the engine and match it against a list, like sudoers.** It would
  avoid the table, but it repeats the drop-in's weakness: `zypper *` is approximately
  root. The user's brief forbids arbitrary commands.
- **Ship a polkit rule granting a `oneup` group.** The user's first choice on 2026-10-14,
  replaced the same day by Discover's rule. A shipped group rule is CVE-2018-1106's shape,
  and the group would have been one more thing to administer.
- **Ship OneUp's own polkit action.** It would work without PackageKit's policy file. But
  it would be a second permission for the same act, which an administrator who
  configured Discover would not know to configure. It also draws openSUSE's
  `polkit-untracked-privilege` and, with `yes`, `polkit-user-privilege`.
- **Let the AppImage install the service.** Rejected by the user on 2026-10-14. It is
  the Deepin pattern (§2.3), and a service file left behind by one AppImage version would
  serve the next.
- **D-Bus libraries.** `dbus-python` needs a GLib main loop. PyGObject is a large
  dependency for a few methods. QtDBus would put Qt into the engine, against
  `security.md` §1.3. `dbus-next` is unmaintained since 2021. `dbus-fast` hides the
  sender in its high-level API. `sdbus` is not packaged for openSUSE. `jeepney` is small,
  pure Python, packaged for both distributions, and exposes the sender.
- **`Run` returns two file descriptors, the output and the status.** The design until
  2026-10-16, and its premise was false. It passed `tests/service-test.py` and failed
  the user's first real run on 2026-10-15. Measured 2026-10-16 (ONEUP-0282): the unit
  runs as `unconfined_service_t`; the policy has no rule letting `system_dbusd_t` read
  that type's pipes, and a `dontaudit domain unconfined_service_t:fifo_file` rule
  hides the denial (`sesearch` on selinux-policy 20261006). The kernel drops the
  descriptors, `dbus-broker` disconnects the service, systemd stops it, and every later
  call is `NoSession`. Reproduced with `restart-list`. Not reproduced on the session
  bus, an unconfined `unconfined_dbusd_t` passing pipes made by `unconfined_t`.
- **Keep the descriptors and ship an SELinux policy module allowing them.** Declined by
  the user on 2026-10-16. OneUp would change the system's security policy, and the allow
  would cover every `unconfined_service_t` pipe, not only OneUp's.
- **Push the output to the client as D-Bus signals.** A slow or vanished client would
  leave the service queueing messages for it, and a lost signal is lost bytes. A pull by
  `offset` lets the client set the pace, and a repeated `Read` is harmless.

## 10. Out of scope

- Refreshing the update lists in the background — the user's decision 5. Deferred; not yet
  queued.
- Getting OneUp into openSUSE:Factory, which would need a SUSE security review of the
  D-Bus files — deferred; not yet queued.
- The window's own `pkexec` actions (`security.md` §1.4) stay as they are.
- `--grant-auth` keeps working for the AppImage and the sudo route.
- `--check` is unchanged. It never needed root (`security.md` §9.5).
- The firmware step is unchanged. `fwupdmgr` already asks fwupd's own polkit actions.

## 11. Cold-eyes loop log

| Loop | Date | Lanes | Q1 | Q2 | Q3 | Q4 | Outcome |
|------|------|-------|----|----|----|----|---------|
| 1 | 2026-10-14 | 2, cold, via `neutral-lane`; genre pinned `spec`; every lane held every question; each read all 625 lines; project's `tests/docs-check.py` ran at 1d (0 failed) | 4 | 6 | 3 | 0 | **Thirteen verified, thirteen fixed, none dismissed.** Eleven came from the lanes and two from settling their open questions. **Both lanes found the same three defects independently**: INV-4 demanded `sudo` plus the table's argv for the download, which on the sudo route is wrapped by the guard or the stop wrapper, so the test could never pass without breaking Stop for passwordless users; the `system-download` row dropped the `env LC_ALL=C` pin today's download carries, which would have starved the progress parser on a non-English system; and the shared `locate.py` lived in a package the AppImage does not ship, while checking only the activation file, so an AppImage window would have failed to import it or shown the service line beside a sudo engine (now `oneup/engine/route.py::engine_route`, which both builds carry). **Both also flagged `python3 -I -m oneup.service`, and the orchestrator measured it**: `-I` leaves the current directory off `sys.path`, so it prints `No module named oneup`; a launcher at `/usr/libexec/oneup-service` now sets the path. One lane alone found that two output descriptors cannot be merged back into the single ordered stream every parser reads, with no encoding for a signal death; that session clean-up would re-enable repositories under a still-running job's zypp lock; that `Stop` named no owner; and that a headless run falling back to sudo would raise a password box nobody can answer. The other found that nothing said what makes the engine non-interactive, so every automatic update would have stood down (now `ONEUP_NONINTERACTIVE=1`, set by `_headless_engine`, which the timer's `ExecStart` reaches), and that the bulk refresh's empty alias failed the alias validator. **The two from open questions**: the service must import `steps`, because `_package_column` lives there; and the 600-second budget cap would have failed a refresh budget only on the service route. Four open questions resolved clean: `_snapshot_count` runs the `snapshot-list` argv, `cache-clean` matches `run_cache`, and the remaining two became the findings above. Lanes arrived holding the global `CLAUDE.md`, the lane prompt and hook text; no project `CLAUDE.md`, memory or git snapshot. Spend: 0.89 and 0.87 USD, four turns each. |
| 2 | 2026-10-14 | 2, cold, via `neutral-lane`; genre pinned `spec`; every lane held every question; each read the whole document; packet rebuilt from disk with windows for every symbol loop 1's fixes named; `tests/docs-check.py` 0 failed | 4 | 5 | 3 | 2 | **Fourteen verified, fourteen fixed, none dismissed. Cap reached (2 for a spec), and the user said on 2026-10-14 not to review these fixes, so they are read by no lane; implementation is the third reviewer.** **A calm cap**: 4 of the 14 landed on text loop 1 wrote (the `_headless_engine` claim, INV-4's download wording, the fallback bullet, INV-4's `sudo -n`); the rest were in the draft. **The most consequential finding was settled by measurement, not argument.** §4.4 step 4 asked polkit again with the user's `unix-session` when a timer's bus-name check failed; one lane showed any process of that user, an SSH shell included, could claim it by setting the variable, a widening Discover's rule does not grant, and that nothing could test it. Measured: `systemd-run --user` → `pkcheck --action-id org.freedesktop.packagekit.system-update --process` → `polkit\56result=yes`, because polkit 127 places a `user@.service` process in the user's display session. Step 4 was deleted: the service adds no rule of its own. **Both lanes found** that `_headless_engine` sets no environment today, so the spec now says it is changed (INV-16), and that nothing registers a polkit agent for an SSH caller; a `challenge` reason now sends an interactive `auto` run to the sudo route (§4.12 item 1 measures it). **One lane alone found** that `KillMode=process` did not save the transaction, because a child writing to the dead service's pipe still takes `SIGPIPE`: children now write to a job file under `/run/oneup/`. The same lane found INV-4 would have stripped `restore_disabled`'s `sudo -n`, the `orphans-remove` validator parsing zypper output as root against property 1, `sudo_init` re-entry hitting `Busy`, a pre-guard drop-in going undetected, and a §6 row citing a measurement §4.12 never listed. The other found the forced-service route and §6's row both contradicting the interactive-only fallback, and that the sudo route's download wraps `system_txn_argv()`, not the table's argv. **From open questions**: `timeout` and `du` are absolute paths today (`REFRESH_SUDO_ARGV`, `CACHE_DU_ARGV`), now stated. One open question corrected by narrowing outside the tally: the AppImage window imports `engine_route` because PyInstaller follows imports, not because `engine-src/` carries it. Spend: 0.93 and 0.87 USD, four turns each. Run total: 27 verified, 27 fixed, over two loops. |
| impl | 2026-10-16 | none: an implementation fold-back (write-spec Step 8), no reviewer dispatched | – | – | – | – | **The user's first real run on a packaged install (2026-10-15) failed at its first root command, and the cause is §4.3's descriptor design (ONEUP-0282).** On SELinux the system bus cannot take pipes from `unconfined_service_t`; `dbus-broker` disconnected the service and every later call was `NoSession`. Reproduced 2026-10-16 with `restart-list`; the policy facts are in §9. `tests/service-test.py` could not see it: a private `dbus-daemon` with no SELinux. **A design premise moved, not a detail**, so §9 records the rejected design and why. User's decisions that day: the client pulls the output with `Read(offset)`, and no SELinux policy module ships. Changed: §4.3 (the interface, `Read`, deletion of the job file), §4.5 (an ended job frees the slot), §4.12 item 4 (the real bus is measured, because no test reaches it), INV-17, §6's dying-service row, §7, §9. **The gate re-arms**: the service, the client and the service suite are still to be built against the new interface. |
| 3 | 2026-10-16 | 2, cold, via `neutral-lane`; genre pinned `spec`; every lane held every question; each read all 737 lines; re-gate of the ONEUP-0282 fold-back (d6e83c8) | 1 | 4 | 0 | 1 | **Six findings: five verified and fixed, one dismissed.** The run's first loop. **From the packet build (Q1)**: the spec said `proc.stream_filtered` has a stall clock; the clock is the window's, `oneup/gui/run.py` `on_output`; the clause was deleted. **Both lanes found** that §4.8's `SIGTERM` bullet (and `server.py`'s loop, which ends every session on stop) would lose a running job's unread output under `Read`, so a commit under `systemctl stop` would report failure: open sessions now stay open and the service exits once no job runs and no session is left. **One lane alone**: a session with no job got `Invalid` in §4.3 but `NoSession` in INV-17's test (`Read` has no job handle; now `NoSession` only for a caller with no session); a lost final reply, retried, found the job file deleted and read as failure (the file now lives until the session ends or runs again, and a repeated end `Read` returns the same `status`); INV-17's test named no observable for descriptor passing being off (now a source check for `enable_fds=True`). **Dismissed**: 143 against §4.6's exit 105, because `steps._download_pass` already reads both as a stop. Two open questions resolved clean: `proc.stop_pending` and `stop_requested` both exist; both routes split lines in the engine, so `Read`'s unsplit delivery matches a pipe's. Second share: 6 of 6 anchors inside the armed span or binding to it (the `SIGTERM` bullet predates it but its harm is the amendment's). Mechanical: `spec_lint` (17 invariants), `doc_citations` 0 stale. Lanes arrived holding the global `CLAUDE.md`, the lane file and hook text; no project `CLAUDE.md`, memory or git snapshot. Spend: 0.53 and 0.13 USD, two turns each, no denials. |
| 4 | 2026-10-16 | 2, cold, via `neutral-lane`; genre pinned `spec`; every lane held every question; each read all 742 lines; packet rebuilt from disk, adding windows on `proc.stop_requested`/`stop_pending`, `stream_filtered` and `steps._download_status` | 2 | 2 | 1 | 0 | **Five verified, five fixed, none dismissed. Cap reached (2 loops for a spec in this run); these five fixes are read by no lane, and implementation is the next reviewer.** **Both lanes found**: §4.6 named `proc.stop_pending` for the Stop forwarder, which announces the stop inside the download output; the code and the spec now say `proc.stop_requested` (loop 3 wrongly resolved this as clean). And loop 3's own `SIGTERM` text let a stop wait on an engine holding its session for a whole run: now `Run` gets `Busy`, a session ends once its job's final `status` is returned, and a stop waits for the running job only. **One lane alone**: the 105 rule lives in `steps._download_status`, not `_download_pass` (loop 3's dismissal named the wrong owner too); §4.5's clean-ups waited for the session's own job, where `server._clean_up` waits for no job at all, which zypp's lock requires; and §4.3 gave two tests for when `status` arrives (now: only on a reply at the end, which carries no bytes). G1, G2 and G4 are outside the armed span and fixed in the run as exempt records of existing code. One open question resolved clean: the service answers `Introspect`. **A calm cap**: 1 of 5 landed on text this run wrote (the `SIGTERM` bullet). Second share: 5 of the run's 10 verified findings inside the armed span, 2 more binding to it, 3 outside. Spend: 0.56 and 0.16 USD, two turns each, no denials. |
