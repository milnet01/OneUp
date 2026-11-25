"""The D-Bus object: sessions, the one running job, and what each method may do.

§4.3 to §4.9. One thread owns every piece of state: the main loop below. The bus
receiver thread only queues messages; polkit checks run on worker threads, because a
check that asks the user can take minutes; the job's waiter runs on its own. Each of
those posts its result back to the main loop's queue rather than touching state.
"""

from __future__ import annotations

import contextlib
import os
import pwd
import queue
import shutil
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from jeepney import (
    DBusAddress,
    HeaderFields,
    MatchRule,
    Message,
    MessageType,
    new_error,
    new_method_call,
    new_method_return,
)
from jeepney.io.threading import DBusRouter, open_dbus_connection

from oneup.engine import repos, rootops, steps
from oneup.engine.service_client import STILL_RUNNING

from . import jobs, polkit

BUS_NAME = "za.co.antsprojectshub.OneUp1"
OBJECT_PATH = "/za/co/antsprojectshub/OneUp1"
INTERFACE = BUS_NAME
VERSION = 1
_ERR = BUS_NAME + ".Error."

MAX_SESSIONS = 8                  # §4.5
MAX_CHECKS = 16                   # CanUpdate checks at once, each its own thread (ONEUP-0424)
_CHECK_SLOTS = threading.BoundedSemaphore(MAX_CHECKS)
READ_WAIT_SECONDS = 1.0           # the longest a `Read` with nothing to say waits (§4.3)
RETRY_FOR = 600.0                 # how long a failed re-enable is retried (§4.5)

_DBUS = DBusAddress("/org/freedesktop/DBus", bus_name="org.freedesktop.DBus",
                    interface="org.freedesktop.DBus")
_DO_NOT_QUEUE = 0x4               # RequestName's flag: refuse rather than wait in line
_PRIMARY_OWNER = 1                # RequestName's reply when the name is now ours
# A restored re-enable's owner: a previous service run's session, whose uid is not
# kept. The audit lines print it as uid=0, which here never means root.
_PREVIOUS_RUN = 0

_INTROSPECTION = f"""<node>
 <interface name="{INTERFACE}">
  <method name="OpenSession"><arg direction="in" type="a{{sv}}"/></method>
  <method name="Run"><arg direction="in" type="s"/><arg direction="in" type="a{{sv}}"/>
   <arg direction="in" type="b"/></method>
  <method name="Read"><arg direction="in" type="t"/><arg direction="out" type="ay"/>
   <arg direction="out" type="i"/></method>
  <method name="Stop"/>
  <method name="CloseSession"/>
  <method name="CanUpdate"><arg direction="out" type="s"/></method>
  <property name="Version" type="u" access="read"/>
 </interface>
</node>
"""


class Refusal(Exception):
    """A method's answer is one of the service's errors (§4.3)."""

    def __init__(self, code: str, text: str) -> None:
        super().__init__(text)
        self.code = code
        self.text = text


@dataclass
class Session:
    owner: str                    # the caller's unique bus name, never reused
    uid: int
    user: str
    import_keys: bool
    disabled: list[str] = field(default_factory=list)   # aliases to re-enable at the end
    found_off: set[str] = field(default_factory=set)    # disabled already when it asked
    cdn_dir: str = ""
    why: str = ""                 # how it ended, for the audit line
    job: jobs.Job | None = None   # its last job, running or ended, until read (§4.3)
    told: bool = False            # that job's final status has been returned once


def _env_seconds(name: str, default: float) -> float:
    """A test override from the SERVICE's own environment (§4.8), never a client's."""
    try:
        value = float(os.environ.get(name) or default)
    except ValueError:
        return default
    return value if value > 0 else default


def _user(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return "?"


def audit(text: str) -> None:
    """One journal line (§4.9). Stdout is the journal under systemd."""
    print(f"oneup-service: {text}", flush=True)


def _repo_aliases() -> set[str]:
    """The aliases the repository files define, read as the service, now (§4.2)."""
    aliases = set()
    for path in sorted(repos.REPOS_DIR.glob("*.repo")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                aliases.add(line[1:-1])
    return aliases


class Service:
    def __init__(self, router: DBusRouter) -> None:
        self.router = router
        self.events: queue.Queue = queue.Queue()
        self.sessions: dict[str, Session] = {}
        self.checking: set[str] = set()             # callers whose OpenSession is with polkit
        self.answering = 0                          # CanUpdate checks still with polkit
        self.job: jobs.Job | None = None
        self.ending: list[Session] = []             # sessions whose clean-up is still owed
        # Re-enables that failed at a session's end, each with when to give up (§4.5).
        self.retry: list[tuple[int, str, float]] = []
        self.retry_every = _env_seconds("ONEUP_SERVICE_RETRY_SECONDS", 5)
        self.retry_next = 0.0
        self.waiting: list[tuple[Message, Session, int, float]] = []   # parked Reads
        self.stopping = False
        self.idle_seconds = _env_seconds("ONEUP_SERVICE_IDLE_SECONDS", 60)
        self.runtime_dir = Path(os.environ.get("ONEUP_SERVICE_RUNTIME_DIR")
                                or os.environ.get("RUNTIME_DIRECTORY") or "/run/oneup")
        # §4.5: every alias a session switched off and the service has not switched back
        # on, on disk, so a service that dies (and a reboot after it) cannot strand a
        # source off for good (ONEUP-0406; /var/lib/oneup, the user's choice 2026-11-15).
        state_dir = Path(os.environ.get("ONEUP_SERVICE_STATE_DIR")
                         or os.environ.get("STATE_DIRECTORY") or "/var/lib/oneup")
        self.paused_file = state_dir / "paused-sources"
        self.gave_up: set[str] = set()     # retries that ran out, kept for the next start
        self.pending: str | None = None    # the alias a running repo-disable switches off
        self.last_busy = time.monotonic()

    def take_over(self) -> None:
        """Clear an earlier instance's job files and resume its restores.

        Only once this process owns the bus name: a second copy that is then refused
        it must not delete the live instance's job files (ONEUP-0426).
        """
        jobs.clear_stale(self.runtime_dir)
        restore = self._read_paused()
        if restore:
            audit(f"restoring sources a previous service left off: {','.join(sorted(restore))}")
            self.retry = [(_PREVIOUS_RUN, alias, time.monotonic() + RETRY_FOR)
                          for alias in sorted(restore)]

    # --- the loop ---------------------------------------------------------------

    def serve(self) -> int:
        while True:
            try:
                # A parked Read is answered as soon as its job writes or ends, so the
                # loop looks often while one waits.
                item = self.events.get(timeout=0.02 if self.waiting else 0.25)
            except queue.Empty:
                item = None
            if isinstance(item, Message):
                self._message(item)
            elif item is not None:
                try:
                    item()                             # a worker's result, run here
                except Exception as exc:  # noqa: BLE001 — a bug costs one result, never the service
                    audit(f"error in a worker's result: {exc!r}")
            self._answer_waiting()
            if self.stopping:
                # §4.8: a session keeps its job readable until the final status has
                # gone out once; every other session ends now.
                for session in list(self.sessions.values()):
                    if session.job is None or session.told:
                        self._end_session(session, "service stopping")
            self._clean_up()
            if (self.sessions or self.checking or self.answering or self.job or self.ending
                    or self.retry):
                self.last_busy = time.monotonic()
                continue
            if self.stopping:
                audit("stopping on SIGTERM")
                return 0
            if time.monotonic() - self.last_busy >= self.idle_seconds:
                audit("idle; exiting")
                return 0

    def _message(self, msg: Message) -> None:
        hdr = msg.header
        if hdr.message_type == MessageType.signal:
            self._signal(msg)
            return
        if hdr.message_type != MessageType.method_call:
            return
        iface = hdr.fields.get(HeaderFields.interface, "")
        member = hdr.fields.get(HeaderFields.member, "")
        if hdr.fields.get(HeaderFields.path) != OBJECT_PATH:
            self._error(msg, "org.freedesktop.DBus.Error.UnknownObject", "no such object")
            return
        handlers = {
            (INTERFACE, "OpenSession"): self._open_session,
            (INTERFACE, "Run"): self._run,
            (INTERFACE, "Read"): self._read,
            (INTERFACE, "Stop"): self._stop,
            (INTERFACE, "CloseSession"): self._close_session,
            (INTERFACE, "CanUpdate"): self._can_update,
            ("org.freedesktop.DBus.Properties", "Get"): self._get_property,
            ("org.freedesktop.DBus.Properties", "GetAll"): self._get_all,
            ("org.freedesktop.DBus.Introspectable", "Introspect"): self._introspect,
        }
        # The D-Bus specification lets a method call leave its interface out. Such a
        # call is resolved against this service's own interface only, never Properties
        # or Introspectable. `_INTROSPECTION` lists the same methods by hand.
        handler = handlers.get((iface or INTERFACE, member))
        if handler is None:
            self._error(msg, "org.freedesktop.DBus.Error.UnknownMethod", f"no method {member}")
            return
        try:
            handler(msg)
        except Refusal as exc:
            self._error(msg, _ERR + exc.code, exc.text)
        except Exception as exc:  # noqa: BLE001 — a bug answers one caller, never kills the rest
            audit(f"error in {member}: {exc!r}")
            self._error(msg, "org.freedesktop.DBus.Error.Failed", "internal error")

    def _signal(self, msg: Message) -> None:
        """A caller left the bus: its session ends (§4.3), its job does not (§4.6)."""
        fields = msg.header.fields
        if (fields.get(HeaderFields.sender) != "org.freedesktop.DBus"
                or fields.get(HeaderFields.member) != "NameOwnerChanged"):
            return
        name, _old, new = msg.body
        if new == "" and name in self.sessions:
            self._end_session(self.sessions[name], "caller left")

    # --- replies ------------------------------------------------------------------

    def _reply(self, msg: Message, signature: str | None = None, body: tuple = ()) -> None:
        with contextlib.suppress(OSError):
            self.router.send(new_method_return(msg, signature, body))

    def _error(self, msg: Message, name: str, text: str) -> None:
        with contextlib.suppress(OSError):
            self.router.send(new_error(msg, name, "s", (text,)))

    @staticmethod
    def _sender(msg: Message) -> str:
        return msg.header.fields.get(HeaderFields.sender, "")

    def _post(self, fn) -> None:
        self.events.put(fn)

    # --- OpenSession (§4.4) ---------------------------------------------------------

    def _open_session(self, msg: Message) -> None:
        caller = self._sender(msg)
        options = self._options(msg, "a{sv}", {"interactive": "b", "import_keys": "b"})
        interactive = options.get("interactive", True)
        import_keys = options.get("import_keys", False)
        # INV-14: a line for every refused session, these before polkit too (ONEUP-0426).
        refusal = None
        if self.stopping:
            refusal = ("stopping", "the service is stopping")
        elif caller in self.sessions or caller in self.checking:
            refusal = ("busy-own-session", "this caller already has a session")
        elif len(self.sessions) + len(self.checking) >= MAX_SESSIONS:
            refusal = ("busy-too-many", "too many sessions")
        if refusal:
            audit(f"session refused uid=? user=? caller={caller} reason={refusal[0]}")
            raise Refusal("Busy", refusal[1])
        self.checking.add(caller)

        def check() -> None:
            uid = polkit.caller_uid(self.router, caller)
            answer = polkit.DENIED
            if uid is not None:
                answer = polkit.check(self.router, caller, polkit.SYSTEM_UPDATE,
                                      interactive=interactive)
                if answer == polkit.YES and import_keys:
                    answer = polkit.check(self.router, caller, polkit.TRUST_SIGNING_KEY,
                                          interactive=interactive)
            self._post(lambda: self._opened(msg, caller, uid, import_keys, answer))

        threading.Thread(target=check, daemon=True).start()

    def _opened(self, msg: Message, caller: str, uid: int | None, import_keys: bool,
                answer: str) -> None:
        self.checking.discard(caller)
        if answer == polkit.YES and not self._has_owner(caller):
            answer = polkit.DENIED            # left mid-check: never a yes (CVE-2021-3560)
        who = f"uid={uid} user={_user(uid) if uid is not None else '?'} caller={caller}"
        if answer != polkit.YES:
            audit(f"session refused {who} reason={answer}")
            self._error(msg, _ERR + "NotAuthorized", answer)
            return
        if self.stopping:
            audit(f"session refused {who} reason=stopping")
            self._error(msg, _ERR + "Busy", "the service is stopping")
            return
        self.sessions[caller] = Session(caller, uid, _user(uid), import_keys)
        audit(f"session opened {who} import_keys={str(import_keys).lower()}")
        self._reply(msg)

    def _has_owner(self, name: str) -> bool:
        try:
            reply = self.router.send_and_get_reply(
                new_method_call(_DBUS, "NameHasOwner", "s", (name,)), timeout=10)
        except Exception:  # noqa: BLE001 — an unanswerable question is a no
            return False
        return reply.header.message_type == MessageType.method_return and reply.body[0] is True

    # --- Run (§4.2, §4.5) -----------------------------------------------------------

    def _run(self, msg: Message) -> None:
        session = self._session(msg)
        if self.stopping:
            raise Refusal("Busy", "the service is stopping")
        if self.job is not None:
            raise Refusal("Busy", "a job is running")
        op, raw_args, merge_stderr = self._body(msg, "sa{sv}b")
        spec = rootops.OPS.get(op)
        if spec is None:
            raise Refusal("Invalid", f"unknown operation {op!r}")
        args = self._variants(raw_args, spec.args)
        self._validate(op, args)
        if args.get("import_keys") is True and not session.import_keys:
            raise Refusal("NotAuthorized", polkit.DENIED)
        if op == "repo-enable" and args["alias"] not in session.disabled:
            raise Refusal("Invalid", "repo-enable undoes only this session's own disable")
        if op == "repo-disable":
            # INV-6: a repository an administrator switched off is never this
            # session's to switch on, so its disable is not recorded (ONEUP-0393).
            # One the service itself still owes a re-enable is off because of OneUp,
            # so this session takes it over; `_job_ended` drops the retry (ONEUP-0426).
            # Where a disable is tracked: `found_off`, set here, says whether to record
            # it; `pending`, set below, holds it while its job runs; `_job_ended` moves
            # it to `session.disabled`. `_paused_now` reads those last two.
            if args["alias"] in self._owed():
                session.found_off.discard(args["alias"])
            elif repos.repo_switched_off(args["alias"]):
                session.found_off.add(args["alias"])
            else:
                session.found_off.discard(args["alias"])
        if op == "orphans-remove":
            self._check_unneeded(args["names"])
        if args.get("cdn") is True and not session.cdn_dir:
            session.cdn_dir = repos.make_cdn_reposd()
            if not session.cdn_dir:
                raise Refusal("Invalid", "the CDN repository copy could not be staged")
        argv = rootops.build(op, args, cdn_dir=session.cdn_dir)
        if session.job is not None:      # its last job has ended; its output goes now
            session.job.discard()
            session.job = None
        # §4.5: the alias is on disk before its repo-disable starts (ONEUP-0426).
        if op == "repo-disable" and args["alias"] not in session.found_off:
            self.pending = args["alias"]
            self._save_paused()
        try:
            job = jobs.Job(op=op, args=args, argv=argv, merge_stderr=merge_stderr,
                           runtime_dir=self.runtime_dir, session=session,
                           on_end=lambda j: self._post(lambda: self._job_ended(j)))
        except OSError as exc:
            if self.pending == args.get("alias"):
                self.pending = None
                self._save_paused()
            raise Refusal("Invalid", f"could not start {op}: {exc.strerror}") from exc
        self.job = job
        session.job = job
        session.told = False
        audit(f"job started uid={session.uid} op={op} args={_args_text(args)}")
        self._reply(msg)

    # --- Read (§4.3) ----------------------------------------------------------------

    def _read(self, msg: Message) -> None:
        session = self._session(msg)
        (offset,) = self._body(msg, "t")
        job = session.job
        if job is None:
            raise Refusal("Invalid", "this session has no job to read")
        if offset > job.size():
            raise Refusal("Invalid", "offset is past the end of the output")
        if not self._answer(msg, session, offset):
            self.waiting.append((msg, session, offset, time.monotonic() + READ_WAIT_SECONDS))

    def _answer(self, msg: Message, session: Session, offset: int) -> bool:
        """Reply if there is something to say: bytes past `offset`, or the job's end."""
        job = session.job
        # First: once set, everything is in the file. But the end is told only once the
        # loop has run `_job_ended`, which frees the service for the next Run (§4.5); the
        # waiter thread sets `status` a moment before that (ONEUP-0387).
        status = job.status if job is not self.job else None
        data = job.read(offset)
        if data:
            self._reply(msg, "ayi", (data, STILL_RUNNING))
            return True
        if status is not None:
            self._reply(msg, "ayi", (b"", status))
            session.told = True
            return True
        return False

    def _answer_waiting(self) -> None:
        now = time.monotonic()
        parked, self.waiting = self.waiting, []
        for msg, session, offset, deadline in parked:
            if self.sessions.get(session.owner) is not session:
                self._error(msg, _ERR + "NoSession", "this caller has no session")
            elif not self._answer(msg, session, offset):
                if now < deadline:
                    self.waiting.append((msg, session, offset, deadline))
                else:
                    self._reply(msg, "ayi", (b"", STILL_RUNNING))

    @staticmethod
    def _validate(op: str, args: dict) -> None:
        """The table's shape checks, then the alias's existence, which needs state.

        The shape check builds with `cdn` false, because the CDN copy is staged only
        once everything else has passed.
        """
        try:
            rootops.build(op, {**args, **({"cdn": False} if "cdn" in args else {})})
        except rootops.Invalid as exc:
            raise Refusal("Invalid", str(exc)) from exc
        if "alias" in args and args["alias"] not in _repo_aliases():
            raise Refusal("Invalid", "no repository has that alias")

    def _check_unneeded(self, names: list[str]) -> None:
        """INV-7: every name must be one zypper calls unneeded, asked just now."""
        rc, out = jobs.run_captured(rootops.build("orphans-unneeded"))
        unneeded = steps._package_column(out) if rc == 0 else None
        if unneeded is None or not set(names) <= set(unneeded):
            raise Refusal("Invalid", "a name is not in zypper's list of unneeded packages")

    def _job_ended(self, job: jobs.Job) -> None:
        session = job.session
        alias = job.args.get("alias")
        if (job.status == 0 and job.op == "repo-disable" and alias not in session.disabled
                and alias not in session.found_off):
            session.disabled.append(alias)
            # Now the session's to switch on: a retry would do it under the live run.
            self.retry = [row for row in self.retry if row[1] != alias]
            self.gave_up.discard(alias)
        if job.status == 0 and job.op == "repo-enable" and alias in session.disabled:
            session.disabled.remove(alias)
        audit(f"job ended uid={session.uid} op={job.op} status={job.status}")
        if self.job is job:
            self.job = None
        if job.op in ("repo-disable", "repo-enable"):
            self.pending = None
            self._save_paused()

    # --- Stop, CloseSession, CanUpdate (§4.6, §4.4) ---------------------------------

    def _stop(self, msg: Message) -> None:
        session = self._session(msg)
        job = self.job
        if job is None:
            raise Refusal("NotStoppable", "nothing is running")
        if job.session is not session:
            raise Refusal("NoSession", "this session did not start the running job")
        if job.op != "system-download":
            raise Refusal("NotStoppable", f"{job.op} is never stopped")
        job.stop()
        audit(f"job stop asked uid={session.uid} op={job.op}")
        self._reply(msg)

    def _close_session(self, msg: Message) -> None:
        self._end_session(self._session(msg), "closed")
        self._reply(msg)

    def _can_update(self, msg: Message) -> None:
        caller = self._sender(msg)
        # Each check is bounded in time by polkit's own call, but nothing counted them:
        # a caller asking in a loop started a thread per call. Past the cap the answer
        # is Busy — "ask again", never a "no" OneUp did not establish (ONEUP-0424).
        if not _CHECK_SLOTS.acquire(blocking=False):
            self._error(msg, _ERR + "Busy", "too many checks at once")
            return

        # Counted until the loop sends the answer: a check still with polkit keeps the
        # service from exiting idle with the caller's reply owed.
        self.answering += 1

        def check() -> None:
            answer = polkit.DENIED
            try:
                answer = polkit.check(self.router, caller, polkit.SYSTEM_UPDATE,
                                      interactive=False)
            finally:
                _CHECK_SLOTS.release()
                self._post(lambda: self._can_update_answered(msg, answer))

        threading.Thread(target=check, daemon=True).start()

    def _can_update_answered(self, msg: Message, answer: str) -> None:
        self.answering -= 1
        self._reply(msg, "s", ("yes" if answer == polkit.YES else "no",))

    # --- sessions end ---------------------------------------------------------------

    def _session(self, msg: Message) -> Session:
        session = self.sessions.get(self._sender(msg))
        if session is None:
            raise Refusal("NoSession", "this caller has no session")
        return session

    def _end_session(self, session: Session, why: str) -> None:
        self.sessions.pop(session.owner, None)
        session.why = why
        self.ending.append(session)

    def _clean_up(self) -> None:
        """§4.5: re-enable what a session disabled, drop its CDN copy — once no job runs.

        A re-enable cannot take zypp's lock while a job holds it, and a running
        commit may still be reading the CDN directory.
        """
        if self.job is not None:
            return
        self._retry_reenables()
        while self.ending:
            session = self.ending.pop(0)
            enabled = []
            for alias in list(session.disabled):
                rc, _ = jobs.run_captured(rootops.build("repo-enable", {"alias": alias}))
                if rc == 0:
                    enabled.append(alias)
                else:
                    audit(f"re-enable failed uid={session.uid} alias={alias} status={rc}")
                    self.retry.append((session.uid, alias, time.monotonic() + RETRY_FOR))
                    self.retry_next = time.monotonic() + self.retry_every
            if session.cdn_dir:
                shutil.rmtree(session.cdn_dir, ignore_errors=True)
            if session.job is not None:      # ended: no job runs here
                session.job.discard()
            audit(f"session ended uid={session.uid} caller={session.owner} "
                  f"why={session.why} re-enabled={','.join(enabled) or '-'}")
            self._save_paused()

    def _retry_reenables(self) -> None:
        """Try a failed re-enable again until it works or `RETRY_FOR` runs out.

        A re-enable fails when something else holds zypp's lock at the session's
        end, PackageKit for one (§6); dropped, it left the repository off for good
        (ONEUP-0393). An alias a live session has disabled again is that
        session's to re-enable now, so it leaves this list.
        """
        now = time.monotonic()
        if not self.retry or now < self.retry_next:
            return
        self.retry_next = now + self.retry_every
        held = {alias for session in self.sessions.values() for alias in session.disabled}
        kept = []
        for uid, alias, give_up in self.retry:
            if alias in held:
                continue
            rc, _ = jobs.run_captured(rootops.build("repo-enable", {"alias": alias}))
            if rc == 0:
                audit(f"re-enabled on retry uid={uid} alias={alias}")
            elif now >= give_up:
                audit(f"re-enable gave up uid={uid} alias={alias} status={rc}")
                self.gave_up.add(alias)
            else:
                kept.append((uid, alias, give_up))
        self.retry = kept
        self._save_paused()

    # --- the paused-sources record (§4.5, ONEUP-0406) -------------------------------

    def _owed(self) -> set[str]:
        """Aliases a session switched off whose re-enable the service still owes."""
        return {alias for _uid, alias, _give_up in self.retry} | self.gave_up

    def _paused_now(self) -> set[str]:
        """Every alias switched off by a session and not yet back on."""
        held = {alias for session in [*self.sessions.values(), *self.ending]
                for alias in session.disabled}
        held.update(alias for _uid, alias, _give_up in self.retry)
        held.update(self.gave_up)
        if self.pending:
            held.add(self.pending)
        return held

    def _save_paused(self) -> None:
        """Write the record whole, or remove it when nothing is off. A failed write is
        audited and the run goes on: the record only matters if the service dies."""
        paused = self._paused_now()
        try:
            if not paused:
                self.paused_file.unlink(missing_ok=True)
                return
            self.paused_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.paused_file.with_suffix(".tmp")
            # Synced before the rename and the folder after it: the record exists to
            # survive the service dying, and a power cut is one way to die (ONEUP-0423).
            with tmp.open("w") as handle:
                handle.write("".join(f"{alias}\n" for alias in sorted(paused)))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.paused_file)
            with contextlib.suppress(OSError):      # best effort: the rename has happened
                folder = os.open(self.paused_file.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(folder)
                finally:
                    os.close(folder)
        except OSError as exc:
            audit(f"paused-sources record not written: {exc.strerror}")

    def _read_paused(self) -> set[str]:
        """The record a previous service left. Only names `rootops` would accept are
        taken: the file is root's, but the alias still reaches `zypper`."""
        try:
            # `replace`: a line that does not decode fails the shape check below,
            # rather than failing every start of the service (ONEUP-0426).
            lines = self.paused_file.read_text(errors="replace").split()
        except OSError:
            return set()
        kept, known = set(), _repo_aliases()
        for alias in lines:
            try:
                rootops.build("repo-enable", {"alias": alias})
            except rootops.Invalid:
                audit(f"paused-sources record: ignored {alias!r}")
                continue
            if alias in known:            # a repository removed since has nothing to restore
                kept.add(alias)
        return kept

    # --- properties -----------------------------------------------------------------

    def _get_property(self, msg: Message) -> None:
        iface, name = self._body(msg, "ss")
        if iface != INTERFACE or name != "Version":
            self._error(msg, "org.freedesktop.DBus.Error.UnknownProperty", name)
            return
        self._reply(msg, "v", (("u", VERSION),))

    def _get_all(self, msg: Message) -> None:
        (iface,) = self._body(msg, "s")
        self._reply(msg, "a{sv}", ({"Version": ("u", VERSION)} if iface == INTERFACE else {},))

    def _introspect(self, msg: Message) -> None:
        self._reply(msg, "s", (_INTROSPECTION,))

    # --- argument checks: fail closed (§4.2) ----------------------------------------

    @staticmethod
    def _body(msg: Message, signature: str) -> tuple:
        if msg.header.fields.get(HeaderFields.signature, "") != signature:
            raise Refusal("Invalid", f"expected arguments {signature}")
        return msg.body

    def _options(self, msg: Message, signature: str, allowed: dict[str, str]) -> dict:
        (raw,) = self._body(msg, signature)
        return self._variants(raw, allowed, required=False)

    @staticmethod
    def _variants(raw: dict, allowed: dict[str, str], *, required: bool = True) -> dict:
        """Unwrap a{sv}, refusing an unknown key, a wrong type or a missing argument."""
        out = {}
        for name, (sig, value) in raw.items():
            if name not in allowed:
                raise Refusal("Invalid", f"unknown argument {name!r}")
            if sig != allowed[name]:
                raise Refusal("Invalid", f"argument {name} must be {allowed[name]}")
            out[name] = value
        if required and set(out) != set(allowed):
            raise Refusal("Invalid", f"arguments must be {sorted(allowed)}")
        return out


def _args_text(args: dict) -> str:
    return " ".join(f"{k}={','.join(v) if isinstance(v, list) else v}"
                    for k, v in sorted(args.items())) or "-"


def main() -> int:
    bus = os.environ.get("ONEUP_SERVICE_BUS") or "SYSTEM"   # a test's private bus
    try:
        # No descriptor passing: SELinux stops the system bus taking one from this
        # service, and the bus then drops the connection (ONEUP-0282, INV-17).
        conn = open_dbus_connection(bus=bus)
    except OSError as exc:
        print(f"oneup-service: cannot reach the bus: {exc}", file=sys.stderr, flush=True)
        return 1
    router = DBusRouter(conn)
    service = Service(router)
    # Every message reaches the loop through one queue, in arrival order.
    # The handles are kept: a filter lives as long as its handle.
    handles = [router.filter(MatchRule(type="method_call"), queue=service.events)]
    # A caller leaving is how its session ends. Both halves are needed: the filter
    # routes the signal to the loop, and AddMatch asks the bus to send it at all.
    owner_changed = MatchRule(type="signal", sender="org.freedesktop.DBus",
                              interface="org.freedesktop.DBus", member="NameOwnerChanged")
    handles.append(router.filter(owner_changed, queue=service.events))
    router.send_and_get_reply(new_method_call(
        _DBUS, "AddMatch", "s", (owner_changed.serialise(),)), timeout=10)
    reply = router.send_and_get_reply(
        new_method_call(_DBUS, "RequestName", "su", (BUS_NAME, _DO_NOT_QUEUE)), timeout=10)
    if (reply.header.message_type != MessageType.method_return
            or reply.body[0] != _PRIMARY_OWNER):
        print("oneup-service: could not own the bus name", file=sys.stderr, flush=True)
        return 1
    service.take_over()

    def on_term(_signum, _frame) -> None:
        # §4.8: refuse new sessions, and exit once the running job has ended. A flag
        # only: the loop ends the sessions, because it owns them.
        service.stopping = True

    signal.signal(signal.SIGTERM, on_term)
    audit(f"started version={VERSION}")
    try:
        return service.serve()
    finally:
        with contextlib.suppress(Exception):
            router.send_and_get_reply(
                new_method_call(_DBUS, "ReleaseName", "s", (BUS_NAME,)), timeout=5)
        with contextlib.suppress(Exception):
            router.close()
        with contextlib.suppress(Exception):
            conn.close()
